"""Computation engine for pitcher narratives.

Transforms PitcherData into pre-computed analysis with qualitative trend
strings ready for LLM consumption. Computes fastball quality deltas
(velocity, P+/S+/L+, movement), within-game velocity arcs, and shared
delta helpers used across all analysis facets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import polars as pl

from pitcher_narratives.data import PitcherData, load_run_values

# Shared internals — re-exported so the remaining compute code in this
# module, sibling concern modules, and the test suite resolve them by name.
from pitcher_narratives.engine._common import (  # noqa: F401
    _COLD_START_STRING,
    _CSW_DESCRIPTIONS,
    _DOUBLE_OUT_EVENTS,
    _FASTBALL_TYPES,
    _FEET_TO_INCHES,
    _INTERMEDIATE_COLS,
    _INTERMEDIATE_P_COLS,
    _INTERMEDIATE_S_COLS,
    _MIN_PITCHES,
    _MOVEMENT_THRESHOLD,
    _OUT_EVENTS,
    _OUTCOME_COLS_P,
    _OUTCOME_NAMES,
    _PPLUS_METRICS,
    _PPLUS_THRESHOLD,
    _SHARP_PPLUS_THRESHOLD,
    _SHARP_VELO_THRESHOLD,
    _SWING_DESCRIPTIONS,
    _USAGE_THRESHOLD,
    _VELO_THRESHOLD,
    _XMETRICS,
    _ZONE_IN,
    _ZONE_OUT,
    _build_name_map,
    _compute_platoon_baseline,
    _float,
    _get_window_game_dates,
    _identify_primary_fastball,
    _is_cold_start,
    _movement_delta_string,
    _per_season_velo,
    _pplus_delta_string,
    _pplus_delta_strings,
    _safe_metric,
    _stand_to_platoon,
    _usage_delta_string,
    _velo_delta_string,
    _weighted_window_metrics,
    _window_date_type_filter,
)
from pitcher_narratives.engine.arsenal import (
    ArsenalPitchTrend,
    ArsenalTrends,
    FastballSummary,
    FirstPitchEntry,
    FirstPitchWeaponry,
    PitchTypeSummary,
    PlatoonMix,
    PlatoonSplit,
    VelocityArc,
    compute_arsenal_summary,
    compute_arsenal_trends,
    compute_fastball_summary,
    compute_first_pitch_weaponry,
    compute_platoon_mix,
    compute_velocity_arc,
)
from pitcher_narratives.engine.baselines import (
    LeagueBaseline,
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
from pitcher_narratives.engine.execution import (
    ExecutionMetrics,
    IntermediateProbabilities,
    compute_execution_metrics,
    compute_intermediate_probabilities,
)
from pitcher_narratives.engine.mechanics import (
    ReleasePointMetrics,
    ReleasePointPitchType,
    compute_release_point_metrics,
)
from pitcher_narratives.engine.workload import (
    AppearanceWorkload,
    CrossSeasonSummary,
    TemporalContext,
    WorkloadContext,
    compute_cross_season_summary,
    compute_temporal_context,
    compute_workload_context,
)

_log = logging.getLogger(__name__)

__all__ = [
    "AppearanceWorkload",
    "ArsenalPitchTrend",
    "ArsenalTrends",
    "ComponentAttribution",
    "CrossSeasonSummary",
    "ExecutionMetrics",
    "FastballSummary",
    "FirstPitchEntry",
    "FirstPitchWeaponry",
    "HardHitRate",
    "IntermediateProbabilities",
    "LeagueBaseline",
    "OutcomeContribution",
    "PitchTypeSummary",
    "PlatoonMix",
    "PlatoonSplit",
    "ReleasePointMetrics",
    "ReleasePointPitchType",
    "TTOAnalysis",
    "TTOPitchType",
    "TTOPlatoonSplit",
    "TTOSplit",
    "TemporalContext",
    "VelocityArc",
    "WorkloadContext",
    "compute_arsenal_summary",
    "compute_arsenal_trends",
    "compute_component_attribution",
    "compute_cross_season_summary",
    "compute_execution_metrics",
    "compute_fastball_summary",
    "compute_first_pitch_weaponry",
    "compute_hard_hit_rate",
    "compute_intermediate_probabilities",
    "compute_league_baselines",
    "compute_platoon_mix",
    "compute_release_point_metrics",
    "compute_temporal_context",
    "compute_tto_analysis",
    "compute_velocity_arc",
    "compute_workload_context",
    "format_s_variant_comparisons",
    "outlier_tag",
    "render_league_baselines",
]





# ── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class OutcomeContribution:
    """A single outcome's contribution to xRV100."""

    outcome: str
    """Outcome name, e.g., 'whiff', 'home_run', 'called_strike'."""

    contribution: float
    """mean(p_i * rv_i) * 100, same scale as xRV100."""


@dataclass
class ComponentAttribution:
    """Per-pitch-type decomposition of xRV into 13 outcome contributions.

    Each pitch type's xRV100 is broken into 13 additive outcome-level
    contributions: contribution_i = mean(probability_i * delta_run_exp_i) * 100.
    The 13 contributions sum to the raw xRV100 total (pre-mean-subtraction).
    """

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    contributions: list[OutcomeContribution]
    """13 items, sorted by |contribution| descending."""

    total_xrv100: float
    """Sum of all 13 contribution values."""

    n_pitches: int
    """Number of pitches used in the computation."""


@dataclass
class HardHitRate:
    """Hard-hit rate analysis for batted balls with exit velo >= 95 mph."""

    hard_hit_pct: float
    """Window hard-hit rate, 0-100."""

    season_hard_hit_pct: float
    """Full-season hard-hit rate, 0-100."""

    delta: str
    """Qualitative delta string (window vs season)."""

    n_batted_balls: int
    """Batted balls in window (hit_into_play with non-null launch_speed)."""

    n_hard_hit: int
    """Hard-hit balls in window (launch_speed >= 95)."""

    small_sample: bool
    """True when n_batted_balls < _MIN_PITCHES."""

    cold_start: bool
    """True when window covers full season."""


# ── Public API ────────────────────────────────────────────────────────


# ── Execution metrics helpers ────────────────────────────────────────


def compute_hard_hit_rate(data: PitcherData) -> HardHitRate:
    """Compute hard-hit rate (% of batted balls with exit velo >= 95 mph).

    Filters to batted balls (description == 'hit_into_play' with non-null
    launch_speed) and computes window and season hard-hit percentages.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        HardHitRate dataclass with window/season rates, delta, and flags.
    """
    cold_start = _is_cold_start(data)
    window_dates = _get_window_game_dates(data)

    # Window batted balls
    window_sc = data.statcast.filter(pl.col("game_date").is_in(window_dates))
    window_bip = window_sc.filter(
        (pl.col("description") == "hit_into_play") & pl.col("launch_speed").is_not_null()
    )
    n_batted_balls = window_bip.height
    n_hard_hit = window_bip.filter(pl.col("launch_speed") >= 95.0).height
    hard_hit_pct = n_hard_hit / n_batted_balls * 100.0 if n_batted_balls > 0 else 0.0

    # Season batted balls
    season_bip = data.statcast.filter(
        (pl.col("description") == "hit_into_play") & pl.col("launch_speed").is_not_null()
    )
    season_n = season_bip.height
    season_hard = season_bip.filter(pl.col("launch_speed") >= 95.0).height
    season_hard_hit_pct = season_hard / season_n * 100.0 if season_n > 0 else 0.0

    delta = _COLD_START_STRING if cold_start else _usage_delta_string(hard_hit_pct - season_hard_hit_pct)

    return HardHitRate(
        hard_hit_pct=hard_hit_pct,
        season_hard_hit_pct=season_hard_hit_pct,
        delta=delta,
        n_batted_balls=n_batted_balls,
        n_hard_hit=n_hard_hit,
        small_sample=n_batted_balls < _MIN_PITCHES,
        cold_start=cold_start,
    )


# ── Times Through Order ───────────────────────────────────────────────


_TTO_SMALL_SAMPLE = 50
"""Pitches below which a TTO pass gets a small-sample caveat."""


@dataclass
class TTOPitchType:
    """Per-pitch-type breakdown within a TTO pass."""

    pitch_type: str
    pitches: int
    usage_pct: float
    """Usage percentage within this pass."""
    usage_delta: str
    """Delta vs this type's pass-1 usage (e.g., '+12.0pp')."""
    avg_p_plus: float | None
    p_plus_delta: str
    """Delta vs this type's pass-1 P+ (e.g., 'Down 8 points')."""


@dataclass
class TTOPlatoonSplit:
    """Per-pitch-type breakdown within a TTO pass for one platoon side."""

    pitch_type: str
    stand: str
    """Batter handedness: 'L' or 'R'."""
    pitches: int
    usage_pct: float
    avg_p_plus: float | None


@dataclass
class TTOSplit:
    """Metrics for a single pass through the order."""

    pass_number: int
    """1 = first time through, 2 = second, 3 = third+."""
    pitches: int
    avg_velo: float | None
    avg_p_plus: float | None
    avg_s_plus: float | None
    fb_p_plus: float | None
    """Fastball-only P+ for this pass (FF/SI/FC)."""
    sec_p_plus: float | None
    """Secondary-only P+ for this pass (non-fastball)."""
    velo_delta: str
    """Delta vs first pass (e.g., 'Down 1.8 mph')."""
    p_plus_delta: str
    """Delta vs first pass."""
    fb_p_plus_delta: str
    """Fastball P+ delta vs first pass."""
    sec_p_plus_delta: str
    """Secondary P+ delta vs first pass."""
    pitch_types: list[TTOPitchType]
    """Per-pitch-type breakdown within this pass."""
    platoon: list[TTOPlatoonSplit]
    """Per-pitch-type per-platoon breakdown within this pass."""
    small_sample: bool
    """True if < _TTO_SMALL_SAMPLE pitches."""


@dataclass
class TTOAnalysis:
    """Times-through-order breakdown for starters."""

    splits: list[TTOSplit]
    available: bool
    """False if pitcher never faces TTO 2+."""
    summary: str
    """Qualitative summary (e.g., 'FB P+ drops 14 pts; CH abandoned vs RHB by pass 3')."""
    mix_shifts: list[str]
    """Notable pitch mix changes across passes (e.g., 'SI drops 35% → 9% by pass 3')."""


def compute_tto_analysis(data: PitcherData) -> TTOAnalysis:
    """Compute times-through-order P+ and velocity degradation.

    Joins Statcast (has n_thruorder_pitcher, pitch_type) with all_pitches
    CSV (has P+/S+) to compute per-pass metrics with fastball/secondary
    split and per-pitch-type breakdown. Only uses window appearances.

    Args:
        data: PitcherData bundle.

    Returns:
        TTOAnalysis with per-pass splits, pitch-type breakdowns, and summary.
    """
    statcast = data.statcast
    all_pitches = data.agg_csvs.get("all_pitches")

    if all_pitches is None or all_pitches.is_empty():
        return TTOAnalysis(splits=[], available=False, summary="No pitch-level data", mix_shifts=[])

    # Filter statcast to window games only
    window_game_pks = data.window_appearances["game_pk"].unique().to_list()
    sc_window = statcast.filter(pl.col("game_pk").is_in(window_game_pks))

    if sc_window.is_empty():
        return TTOAnalysis(splits=[], available=False, summary="No window appearances", mix_shifts=[])

    # Join statcast (n_thruorder_pitcher, pitch_type, stand) with all_pitches (P+, S+)
    sc_cols = sc_window.select(
        "pitcher",
        "game_pk",
        "pitch_number",
        "n_thruorder_pitcher",
        "release_speed",
        "pitch_type",
        "stand",
    )
    ap_cols = all_pitches.select("pitcher", "game_pk", "pitch_number", "P+", "S+")

    joined = sc_cols.join(ap_cols, on=["pitcher", "game_pk", "pitch_number"], how="inner")
    joined = joined.filter(pl.col("pitch_type") != "")

    if joined.is_empty():
        return TTOAnalysis(splits=[], available=False, summary="No matched pitch data", mix_shifts=[])

    # Tag fastball vs secondary
    joined = joined.with_columns(pl.col("pitch_type").is_in(list(_FASTBALL_TYPES)).alias("is_fastball"))

    # ── Overall aggregation by TTO pass ──
    tto_overall = (
        joined.group_by("n_thruorder_pitcher")
        .agg(
            pl.col("release_speed").mean().alias("avg_velo"),
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.col("S+").mean().alias("avg_s_plus"),
            pl.len().alias("pitches"),
        )
        .sort("n_thruorder_pitcher")
    )

    # ── Fastball / secondary split by TTO pass ──
    fb_sec = (
        joined.group_by(["n_thruorder_pitcher", "is_fastball"])
        .agg(
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.len().alias("pitches"),
        )
        .sort(["n_thruorder_pitcher", "is_fastball"])
    )

    # ── Per pitch-type breakdown by TTO pass (with counts for usage %) ──
    pitch_type_breakdown = (
        joined.group_by(["n_thruorder_pitcher", "pitch_type"])
        .agg(
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.len().alias("pitches"),
        )
        .sort(["n_thruorder_pitcher", "pitch_type"])
    )

    # ── Platoon breakdown by TTO pass ──
    platoon_breakdown = (
        joined.group_by(["n_thruorder_pitcher", "stand", "pitch_type"])
        .agg(
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.len().alias("pitches"),
        )
        .sort(["n_thruorder_pitcher", "stand", "pitch_type"])
    )

    overall_rows = tto_overall.to_dicts()
    if len(overall_rows) < 2:
        return TTOAnalysis(
            splits=[],
            available=False,
            summary="Only faced batters once per game (no TTO comparison)",
            mix_shifts=[],
        )

    # Helper: extract fb/sec P+ for a pass
    def _get_fb_sec(pass_num: int) -> tuple[float | None, float | None]:
        fb_rows = fb_sec.filter((pl.col("n_thruorder_pitcher") == pass_num) & pl.col("is_fastball"))
        sec_rows = fb_sec.filter((pl.col("n_thruorder_pitcher") == pass_num) & ~pl.col("is_fastball"))
        fb_val = fb_rows["avg_p_plus"][0] if fb_rows.height > 0 else None
        sec_val = sec_rows["avg_p_plus"][0] if sec_rows.height > 0 else None
        return fb_val, sec_val

    # Helper: extract pitch-type breakdown for a pass
    def _get_pitch_types(pass_num: int, total_pitches: int) -> list[dict[str, Any]]:
        rows = pitch_type_breakdown.filter(pl.col("n_thruorder_pitcher") == pass_num).sort(
            "pitches", descending=True
        )
        result = rows.to_dicts()
        for r in result:
            r["usage_pct"] = (r["pitches"] / total_pitches * 100) if total_pitches > 0 else 0.0
        return result

    # Helper: extract platoon splits for a pass
    def _get_platoon(pass_num: int) -> list[TTOPlatoonSplit]:
        rows = platoon_breakdown.filter(pl.col("n_thruorder_pitcher") == pass_num)
        if rows.is_empty():
            return []
        # Compute per-stand totals for usage %
        stand_totals: dict[str, int] = {}
        for r in rows.to_dicts():
            stand_totals[r["stand"]] = stand_totals.get(r["stand"], 0) + r["pitches"]
        entries: list[TTOPlatoonSplit] = []
        for r in rows.sort("pitches", descending=True).to_dicts():
            total = stand_totals.get(r["stand"], 1)
            entries.append(
                TTOPlatoonSplit(
                    pitch_type=r["pitch_type"],
                    stand=r["stand"],
                    pitches=r["pitches"],
                    usage_pct=r["pitches"] / total * 100,
                    avg_p_plus=r["avg_p_plus"],
                )
            )
        return entries

    # Get pass-1 baselines for deltas
    first = overall_rows[0]
    first_fb, first_sec = _get_fb_sec(first["n_thruorder_pitcher"])

    # Get pass-1 per-type baselines (P+ and usage)
    first_by_type: dict[str, dict[str, Any]] = {}
    for pt in _get_pitch_types(first["n_thruorder_pitcher"], first["pitches"]):
        first_by_type[pt["pitch_type"]] = {
            "avg_p_plus": pt["avg_p_plus"],
            "usage_pct": pt["usage_pct"],
        }

    # Build splits
    splits: list[TTOSplit] = []
    for row in overall_rows:
        pass_num = row["n_thruorder_pitcher"]
        velo = row["avg_velo"]
        p_plus = row["avg_p_plus"]
        s_plus = row["avg_s_plus"]
        total_pitches = row["pitches"]
        fb_pp, sec_pp = _get_fb_sec(pass_num)

        if pass_num == first["n_thruorder_pitcher"]:
            vdelta = "--"
            pdelta = "--"
            fb_delta = "--"
            sec_delta = "--"
        else:
            vdelta = (
                _velo_delta_string(velo - first["avg_velo"])
                if velo is not None and first["avg_velo"] is not None
                else "--"
            )
            pdelta = (
                _pplus_delta_string(p_plus - first["avg_p_plus"])
                if p_plus is not None and first["avg_p_plus"] is not None
                else "--"
            )
            fb_delta = (
                _pplus_delta_string(fb_pp - first_fb) if fb_pp is not None and first_fb is not None else "--"
            )
            sec_delta = (
                _pplus_delta_string(sec_pp - first_sec)
                if sec_pp is not None and first_sec is not None
                else "--"
            )

        # Per-pitch-type breakdown with usage % and deltas
        pt_entries: list[TTOPitchType] = []
        for pt in _get_pitch_types(pass_num, total_pitches):
            pt_type = pt["pitch_type"]
            pt_pp = pt["avg_p_plus"]
            pt_usage = pt["usage_pct"]

            if pass_num == first["n_thruorder_pitcher"]:
                pt_p_delta = "--"
                pt_u_delta = "--"
            else:
                # P+ delta
                if pt_type in first_by_type and pt_pp is not None:
                    pt_p_delta = _pplus_delta_string(pt_pp - first_by_type[pt_type]["avg_p_plus"])
                else:
                    pt_p_delta = "New"
                # Usage delta
                if pt_type in first_by_type:
                    u_diff = pt_usage - first_by_type[pt_type]["usage_pct"]
                    pt_u_delta = f"{u_diff:+.1f}pp"
                else:
                    pt_u_delta = "New"

            pt_entries.append(
                TTOPitchType(
                    pitch_type=pt_type,
                    pitches=pt["pitches"],
                    usage_pct=pt_usage,
                    usage_delta=pt_u_delta,
                    avg_p_plus=pt_pp,
                    p_plus_delta=pt_p_delta,
                )
            )

        # Platoon splits for this pass
        platoon_entries = _get_platoon(pass_num)

        splits.append(
            TTOSplit(
                pass_number=pass_num,
                pitches=total_pitches,
                avg_velo=velo,
                avg_p_plus=p_plus,
                avg_s_plus=s_plus,
                fb_p_plus=fb_pp,
                sec_p_plus=sec_pp,
                velo_delta=vdelta,
                p_plus_delta=pdelta,
                fb_p_plus_delta=fb_delta,
                sec_p_plus_delta=sec_delta,
                pitch_types=pt_entries,
                platoon=platoon_entries,
                small_sample=total_pitches < _TTO_SMALL_SAMPLE,
            )
        )

    # ── Detect notable mix shifts ──
    mix_shifts: list[str] = []
    last = splits[-1]
    for entry in last.pitch_types:
        if entry.pitch_type in first_by_type:
            first_usage = first_by_type[entry.pitch_type]["usage_pct"]
            diff = entry.usage_pct - first_usage
            if abs(diff) >= 10.0:
                mix_shifts.append(
                    f"{entry.pitch_type} {first_usage:.0f}% → "
                    f"{entry.usage_pct:.0f}% by pass {last.pass_number}"
                )
        else:
            if entry.pitches >= 5:
                mix_shifts.append(
                    f"{entry.pitch_type} introduced in pass {last.pass_number} ({entry.usage_pct:.0f}%)"
                )
    # Detect pitches dropped in later passes
    for pt_type, baseline in first_by_type.items():
        if baseline["usage_pct"] >= 10.0:
            found = any(p.pitch_type == pt_type for p in last.pitch_types)
            if not found:
                mix_shifts.append(
                    f"{pt_type} abandoned by pass {last.pass_number} (was {baseline['usage_pct']:.0f}%)"
                )

    # Build summary — lead with fastball P+ degradation signal
    summary_parts: list[str] = []
    if first_fb and splits[-1].fb_p_plus:
        fb_drop = first_fb - splits[-1].fb_p_plus
        if abs(fb_drop) >= _PPLUS_THRESHOLD:
            summary_parts.append(f"Fastball P+ drops {fb_drop:.0f} points by pass {splits[-1].pass_number}")
        else:
            summary_parts.append(f"Fastball P+ holds through {len(splits)} passes ({fb_drop:+.0f})")

    if first_sec and splits[-1].sec_p_plus:
        sec_drop = first_sec - splits[-1].sec_p_plus
        if abs(sec_drop) >= _PPLUS_THRESHOLD:
            summary_parts.append(f"Secondary P+ drops {sec_drop:.0f} points")
        else:
            summary_parts.append(f"Secondary P+ holds ({sec_drop:+.0f})")

    if mix_shifts:
        summary_parts.append(f"{len(mix_shifts)} mix shift(s)")

    if splits[-1].small_sample:
        summary_parts.append(f"small sample in pass {splits[-1].pass_number} ({splits[-1].pitches} pitches)")

    summary = "; ".join(summary_parts) if summary_parts else f"{len(splits)} passes through the order"

    return TTOAnalysis(splits=splits, available=True, summary=summary, mix_shifts=mix_shifts)


# ── Component attribution ────────────────────────────────────────────


def compute_component_attribution(
    data: PitcherData,
    game_pk: int | None = None,
) -> list[ComponentAttribution]:
    """Decompose xRV into 13 outcome-level contributions per pitch type.

    For each pitch: contribution_i = p_i * delta_run_exp(outcome_i, balls, strikes).
    Per pitch type: mean(contribution_i) * 100 for each of 13 outcomes.

    The contributions sum to the RAW xRV100 (pre-mean-subtraction). This will
    differ from the mean-subtracted xRV100_P in the CSVs by a constant
    league-average offset.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.
        game_pk: If provided, compute for a single appearance only.
            If None, compute season-level (all pitches for this pitcher).

    Returns:
        List of ComponentAttribution, one per pitch type, sorted by
        n_pitches descending. Empty list if all_pitches CSV lacks
        required outcome columns.
    """
    all_pitches = data.agg_csvs["all_pitches"]

    # Check that all 13 outcome columns exist
    if not all(col in all_pitches.columns for col in _OUTCOME_COLS_P):
        return []

    # Load run values lookup table
    try:
        rv_df = load_run_values()
    except FileNotFoundError as exc:
        _log.warning("Skipping component attribution: %s", exc)
        return []

    # Filter to specific appearance if requested
    if game_pk is not None:
        all_pitches = all_pitches.filter(pl.col("game_pk") == game_pk)
        if all_pitches.is_empty():
            return []

    name_map = _build_name_map(data.statcast)

    # Get pitch types sorted by count descending
    type_counts = (
        all_pitches.group_by("pitch_type")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
    )
    pitch_types = type_counts["pitch_type"].to_list()

    results: list[ComponentAttribution] = []

    for pt in pitch_types:
        pitches = all_pitches.filter(pl.col("pitch_type") == pt)
        n_pitches = pitches.height
        if n_pitches == 0:
            continue

        # Unpivot the 13 probability columns to long format
        long = pitches.unpivot(
            on=list(_OUTCOME_COLS_P),
            index=["game_pk", "at_bat_number", "pitch_number", "balls", "strikes"],
            variable_name="outcome_col",
            value_name="probability",
        ).with_columns(
            pl.col("outcome_col").str.replace("_P$", "").alias("model_classes"),
        )

        # Join with run values on [balls, strikes, model_classes]
        joined = long.join(
            rv_df.select(["balls", "strikes", "model_classes", "delta_run_exp"]),
            on=["balls", "strikes", "model_classes"],
            how="inner",
        )

        # Compute per-pitch contribution = probability * delta_run_exp
        joined = joined.with_columns(
            (pl.col("probability") * pl.col("delta_run_exp")).alias("contribution"),
        )

        # Group by outcome and compute mean(contribution) * 100
        outcome_means = (
            joined.group_by("model_classes")
            .agg(pl.col("contribution").mean().alias("mean_contribution"))
            .with_columns(
                (pl.col("mean_contribution") * 100).alias("contribution_xrv100"),
            )
        )

        # Build list of OutcomeContribution, sorted by |contribution| descending
        contributions: list[OutcomeContribution] = []
        for row in outcome_means.iter_rows(named=True):
            contributions.append(
                OutcomeContribution(
                    outcome=row["model_classes"],
                    contribution=row["contribution_xrv100"],
                )
            )
        contributions.sort(key=lambda c: abs(c.contribution), reverse=True)

        total_xrv100 = sum(c.contribution for c in contributions)

        results.append(
            ComponentAttribution(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                contributions=contributions,
                total_xrv100=total_xrv100,
                n_pitches=n_pitches,
            )
        )

    results.sort(key=lambda x: x.n_pitches, reverse=True)
    return results
