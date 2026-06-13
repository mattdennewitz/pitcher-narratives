"""Computation engine for pitcher narratives.

Transforms PitcherData into pre-computed analysis with qualitative trend
strings ready for LLM consumption. Computes fastball quality deltas
(velocity, P+/S+/L+, movement), within-game velocity arcs, and shared
delta helpers used across all analysis facets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl

from pitcher_narratives.data import PitcherData, load_full_agg, load_run_values

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
class ExecutionMetrics:
    """Per-pitch-type execution metrics for the recent window."""

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    csw_pct: float
    """Called + Swinging Strike %, 0-100."""

    zone_rate: float
    """Percentage of pitches in zones 1-9 (null zones excluded), 0-100."""

    chase_rate: float
    """O-Swing%: swings on pitches in zones 11-14, 0-100."""

    xwhiff_p: float | None
    """xWhiff P+ from pitcher_type_appearance CSV window."""

    xswing_p: float | None
    """xSwing P+ from pitcher_type_appearance CSV window."""

    xrv100_p: float | None
    """xRV100 P+ from pitcher_type_appearance CSV window."""

    xrv100_percentile: int | None
    """Percentile vs all pitchers throwing this type (from pitcher_type.csv)."""

    n_pitches: int
    """Number of pitches of this type in window."""

    small_sample: bool
    """True when n_pitches < _MIN_PITCHES."""

    cold_start: bool
    """True when window covers the full season."""


@dataclass
class IntermediateProbabilities:
    """Per-pitch-type intermediate model probabilities (P and S variants).

    P-variants include location; S-variants are stuff-only.
    Location impact = P minus S for any metric.
    """

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    # Window values (from pitcher_type_appearance grain)
    xswing_p: float | None
    xswing_s: float | None
    xwhiff_p: float | None
    xwhiff_s: float | None
    xgor_p: float | None
    xgor_s: float | None
    xpur_p: float | None
    xpur_s: float | None
    xhr100_p: float | None
    xhr100_s: float | None
    bbe_prob_p: float | None
    bbe_prob_s: float | None
    xswst_p: float | None
    xswst_s: float | None
    xrv100_p: float | None
    xrv100_s: float | None

    # Season baseline values (from pitch_type_baseline)
    season_xswing_p: float | None
    season_xswing_s: float | None
    season_xwhiff_p: float | None
    season_xwhiff_s: float | None
    season_xgor_p: float | None
    season_xgor_s: float | None
    season_xpur_p: float | None
    season_xpur_s: float | None
    season_xhr100_p: float | None
    season_xhr100_s: float | None
    season_bbe_prob_p: float | None
    season_bbe_prob_s: float | None
    season_xswst_p: float | None
    season_xswst_s: float | None
    season_xrv100_p: float | None
    season_xrv100_s: float | None

    n_pitches: int
    """Number of pitches in window for this type."""

    small_sample: bool
    """True when n_pitches < _MIN_PITCHES."""

    cold_start: bool
    """True when window covers the full season."""


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
class AppearanceWorkload:
    """Workload data for a single appearance."""

    game_pk: int
    game_date: str
    """ISO date string."""

    role: str
    """'SP' or 'RP'."""

    ip: str
    """Baseball notation: '5.2', '1.0', '0.1'."""

    pitch_count: int
    rest_days: int | None
    """None for first appearance."""


@dataclass
class WorkloadContext:
    """Workload and rest context for the pitcher."""

    appearances: list[AppearanceWorkload]
    max_consecutive_days: int
    """Maximum consecutive calendar days pitched."""

    workload_concern: bool
    """True when max_consecutive_days >= 3."""


@dataclass
class TemporalContext:
    """Temporal grounding for LLM narratives -- prevents cross-season hallucination."""

    analysis_date: date
    current_season: int
    current_season_appearances: int
    current_season_first_date: str
    """ISO date of first appearance this season."""
    current_season_ip: str
    """Baseball-notation IP total for current season."""
    prior_season: int
    prior_season_appearances: int
    prior_season_ip: str
    """Baseball-notation IP total for prior season."""
    prior_year_relevance: str
    """'HIGH', 'MODERATE', or 'LOW'."""
    prior_year_relevance_reason: str
    """Human-readable explanation for the LLM."""


@dataclass
class CrossSeasonSummary:
    """Year-over-year pitcher-level metric deltas.

    Produced by compute_cross_season_summary(). None when the pitcher
    has only one season of data.
    """

    current_season: int
    prior_season: int

    # Velocity
    current_velo: float | None
    prior_velo: float | None
    velo_delta: str
    """Qualitative YoY velocity delta, e.g., 'Up 1.2 mph' or 'N/A'."""

    # P+ / S+ / L+
    current_p_plus: float
    prior_p_plus: float
    p_plus_delta: str

    current_s_plus: float
    prior_s_plus: float
    s_plus_delta: str

    current_l_plus: float
    prior_l_plus: float
    l_plus_delta: str


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


# ── Release Point ─────────────────────────────────────────────────────

_RELEASE_POS_THRESHOLD = 0.1
"""Feet below which release position delta is 'Steady' (~1.2 inches)."""

_EXTENSION_THRESHOLD = 0.2
"""Feet below which extension delta is 'Steady'."""


def _release_delta_string(delta: float, threshold: float = _RELEASE_POS_THRESHOLD) -> str:
    """Convert release position delta (feet) to qualitative string.

    Args:
        delta: window_value - season_value (positive = higher/more).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 0.15 ft' or 'Steady (+0.05 ft)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.2f} ft)"
    direction = "Up" if delta > 0 else "Down"
    return f"{direction} {abs(delta):.2f} ft"


def _extension_delta_string(delta: float, threshold: float = _EXTENSION_THRESHOLD) -> str:
    """Convert extension delta (feet) to qualitative string.

    Args:
        delta: window_value - season_value (positive = more extension).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 0.25 ft' or 'Steady (+0.10 ft)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.2f} ft)"
    direction = "Up" if delta > 0 else "Down"
    return f"{direction} {abs(delta):.2f} ft"


@dataclass
class ReleasePointPitchType:
    """Per-pitch-type release point metrics with window vs season deltas."""

    pitch_type: str
    pitch_name: str

    window_release_x: float
    """Mean horizontal release position (feet) in window."""

    season_release_x: float
    """Mean horizontal release position (feet) full season."""

    release_x_delta: str
    """Qualitative delta string for horizontal release."""

    window_release_z: float
    """Mean vertical release position (feet) in window."""

    season_release_z: float
    """Mean vertical release position (feet) full season."""

    release_z_delta: str
    """Qualitative delta string for vertical release."""

    window_extension: float
    """Mean release extension (feet) in window."""

    season_extension: float
    """Mean release extension (feet) full season."""

    extension_delta: str
    """Qualitative delta string for extension."""

    n_pitches_window: int
    """Number of pitches of this type in window."""

    small_sample: bool
    """True when n_pitches_window < _MIN_PITCHES."""

    cold_start: bool
    """True when window covers full season."""


@dataclass
class ReleasePointMetrics:
    """Release point analysis across all pitch types."""

    pitch_types: list[ReleasePointPitchType]
    """Per-pitch-type release point data, ordered by season usage descending."""

    cold_start: bool
    """True when window covers full season."""


# ── Public API ────────────────────────────────────────────────────────


# ── Execution metrics helpers ────────────────────────────────────────


def _compute_ip_all_games(statcast: pl.DataFrame) -> dict[int, str]:
    """Compute innings pitched for every game in one pass.

    Groups by game_pk, then for each game counts full innings (all
    innings except the last) and event-based outs in the final inning.

    Returns:
        dict mapping game_pk → IP in baseball notation ('5.1', '1.0', etc.).
    """
    out_list = list(_OUT_EVENTS)
    double_out_list = list(_DOUBLE_OUT_EVENTS)

    result: dict[int, str] = {}
    for game_pk, game in statcast.group_by("game_pk"):
        gpk = int(game_pk[0])  # type: ignore[index]
        innings = sorted(game["inning"].unique().to_list())
        if not innings:
            result[gpk] = "0.0"
            continue

        n_full_innings = max(0, len(innings) - 1)
        final_inning = game.filter(pl.col("inning") == innings[-1])
        outs_in_final = final_inning.filter(
            pl.col("events").is_in(out_list)
        ).height
        outs_in_final += final_inning.filter(
            pl.col("events").is_in(double_out_list)
        ).height

        total_thirds = n_full_innings * 3 + outs_in_final
        result[gpk] = f"{total_thirds // 3}.{total_thirds % 3}"

    return result


def _compute_ip(statcast: pl.DataFrame, game_pk: int) -> str:
    """Compute innings pitched for a single appearance as baseball notation.

    Prefer _compute_ip_all_games() for batch use. This wrapper exists
    for call sites that need IP for one game only.
    """
    return _compute_ip_all_games(statcast.filter(pl.col("game_pk") == game_pk)).get(
        game_pk, "0.0"
    )


def _compute_rest_days(appearance_dates: list[Any]) -> list[int | None]:
    """Compute rest days between consecutive appearances.

    First appearance returns None. Subsequent appearances return
    (date[i] - date[i-1]).days - 1 so that consecutive calendar days
    yield 0 rest days.

    Args:
        appearance_dates: List of date objects (will be sorted).

    Returns:
        List of rest day counts, same length as input.
    """
    sorted_dates = sorted(appearance_dates)
    result: list[int | None] = [None]
    for i in range(1, len(sorted_dates)):
        rest = (sorted_dates[i] - sorted_dates[i - 1]).days - 1
        result.append(rest)
    return result


def _max_consecutive_days(appearance_dates: list[Any]) -> int:
    """Compute maximum consecutive calendar days pitched.

    Args:
        appearance_dates: List of date objects (will be sorted).

    Returns:
        Maximum consecutive days (1 = single day, 2 = two consecutive days, etc.).
    """
    if not appearance_dates:
        return 0
    sorted_dates = sorted(appearance_dates)
    consecutive = 1
    max_run = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            consecutive += 1
            max_run = max(max_run, consecutive)
        else:
            consecutive = 1
    return max_run




def _compute_xrv100_percentile(
    pitcher_xrv100: float | None,
    pitch_type: str,
    full_pitcher_type_df: pl.DataFrame,
    min_pitches: int = 10,
) -> int | None:
    """Compute percentile rank of pitcher's xRV100 vs all pitchers for a type.

    Uses the full (unfiltered) pitcher_type DataFrame to get the league
    distribution. Weight-averages xRV100_P per (pitcher, pitch_type)
    across game_types. Lower (more negative) xRV100 = better pitcher
    = higher percentile.

    Args:
        pitcher_xrv100: The pitcher's weighted window xRV100_P for this type.
        pitch_type: Pitch type code.
        full_pitcher_type_df: Full unfiltered pitcher_type DataFrame for
            league distribution.
        min_pitches: Minimum pitches threshold for inclusion.

    Returns:
        Percentile (0-100) or None if pitcher_xrv100 is None.
    """
    if pitcher_xrv100 is None:
        return None

    # Filter to this pitch type and minimum pitches
    type_data = full_pitcher_type_df.filter(
        (pl.col("pitch_type") == pitch_type) & (pl.col("n_pitches") >= min_pitches)
    )

    if type_data.is_empty():
        return 50

    # Weight-average xRV100_P per pitcher across game_types
    weighted = type_data.group_by("pitcher").agg(
        (pl.col("xRV100_P") * pl.col("n_pitches")).sum() / pl.col("n_pitches").sum()
    )

    # Count pitchers with worse (higher) xRV100 -- negative is better
    n_worse = weighted.filter(pl.col("xRV100_P") > pitcher_xrv100).height
    total = len(weighted)

    return int(n_worse / total * 100) if total > 0 else 50


def compute_execution_metrics(data: PitcherData) -> list[ExecutionMetrics]:
    """Compute per-pitch-type execution metrics for the recent window.

    For each pitch type in the pitcher's arsenal, computes CSW%, zone rate,
    chase rate, xWhiff, xSwing, and xRV100 percentile ranking. Results are
    sorted by n_pitches descending.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        List of ExecutionMetrics dataclasses, one per pitch type.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    # Filter statcast to window
    window_statcast = data.statcast.filter(pl.col("game_date").is_in(window_dates))

    name_map = _build_name_map(data.statcast)

    # Get pitch types from baseline sorted by n_pitches descending
    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    # Load full pitcher_type CSV once for percentile computation
    full_pitcher_type_df = load_full_agg("pitcher_type")

    results: list[ExecutionMetrics] = []

    for pt in pitch_types:
        pt_window = window_statcast.filter(pl.col("pitch_type") == pt)
        n_pitches = len(pt_window)

        # ── CSW% ──────────────────────────────────────────────────
        if n_pitches > 0:
            csw_count = pt_window.filter(pl.col("description").is_in(list(_CSW_DESCRIPTIONS))).height
            csw_pct = csw_count / n_pitches * 100.0
        else:
            csw_pct = 0.0

        # ── Zone rate ─────────────────────────────────────────────
        pt_non_null_zone = pt_window.filter(pl.col("zone").is_not_null())
        non_null_total = len(pt_non_null_zone)
        if non_null_total > 0:
            in_zone = pt_non_null_zone.filter(pl.col("zone").is_in(_ZONE_IN)).height
            zone_rate = in_zone / non_null_total * 100.0
        else:
            zone_rate = 0.0

        # ── Chase rate (O-Swing%) ─────────────────────────────────
        pt_outside = pt_window.filter(pl.col("zone").is_in(_ZONE_OUT))
        outside_total = len(pt_outside)
        if outside_total > 0:
            outside_swings = pt_outside.filter(pl.col("description").is_in(list(_SWING_DESCRIPTIONS))).height
            chase_rate = outside_swings / outside_total * 100.0
        else:
            chase_rate = 0.0

        # ── xWhiff / xSwing / xRV100 from CSV ────────────────────
        xmetrics = _weighted_window_metrics(
            data.agg_csvs["pitcher_type_appearance"],
            _XMETRICS,
            _window_date_type_filter(window_dates, pt),
        )
        xwhiff_p = xmetrics["xWhiff_P"]
        xswing_p = xmetrics["xSwing_P"]
        xrv100_p = xmetrics["xRV100_P"]

        # ── xRV100 percentile ─────────────────────────────────────
        xrv100_percentile = _compute_xrv100_percentile(
            xrv100_p,
            pt,
            full_pitcher_type_df,
        )

        # ── Small sample / cold start ─────────────────────────────
        small_sample = n_pitches < _MIN_PITCHES

        results.append(
            ExecutionMetrics(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                csw_pct=csw_pct,
                zone_rate=zone_rate,
                chase_rate=chase_rate,
                xwhiff_p=xwhiff_p,
                xswing_p=xswing_p,
                xrv100_p=xrv100_p,
                xrv100_percentile=xrv100_percentile,
                n_pitches=n_pitches,
                small_sample=small_sample,
                cold_start=cold_start,
            )
        )

    # Sort by n_pitches descending
    results.sort(key=lambda x: x.n_pitches, reverse=True)
    return results


def compute_intermediate_probabilities(data: PitcherData) -> list[IntermediateProbabilities]:
    """Compute per-pitch-type intermediate probabilities for window and season.

    Extracts P and S variants of all intermediate probability columns from
    pitchingplus aggregation CSVs. Window values come from pitcher_type_appearance
    (weighted by n_pitches). Season values come from pitch_type_baseline.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        List of IntermediateProbabilities, one per pitch type, sorted by
        n_pitches descending.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)
    name_map = _build_name_map(data.statcast)

    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    results: list[IntermediateProbabilities] = []

    for pt in pitch_types:
        # Window values from appearance grain
        metrics = _weighted_window_metrics(
            data.agg_csvs["pitcher_type_appearance"],
            _INTERMEDIATE_COLS,
            _window_date_type_filter(window_dates, pt),
        )

        # Season values from baseline
        bl_row = baseline.filter(pl.col("pitch_type") == pt)

        def _bl(col: str, _row: pl.DataFrame = bl_row) -> float | None:
            if _row.is_empty() or col not in _row.columns:
                return None
            val = _row[col][0]
            return None if val is None else float(val)

        n_pitches = int(metrics.get("n_pitches", 0))

        results.append(IntermediateProbabilities(
            pitch_type=pt,
            pitch_name=name_map.get(pt, pt),
            # Window P-variants
            xswing_p=metrics.get("xSwing_P"),
            xwhiff_p=metrics.get("xWhiff_P"),
            xgor_p=metrics.get("xGOr_P"),
            xpur_p=metrics.get("xPUr_P"),
            xhr100_p=metrics.get("xHR100_P"),
            bbe_prob_p=metrics.get("BBE_prob_P"),
            xswst_p=metrics.get("xSwSt_P"),
            xrv100_p=metrics.get("xRV100_P"),
            # Window S-variants
            xswing_s=metrics.get("xSwing_S"),
            xwhiff_s=metrics.get("xWhiff_S"),
            xgor_s=metrics.get("xGOr_S"),
            xpur_s=metrics.get("xPUr_S"),
            xhr100_s=metrics.get("xHR100_S"),
            bbe_prob_s=metrics.get("BBE_prob_S"),
            xswst_s=metrics.get("xSwSt_S"),
            xrv100_s=metrics.get("xRV100_S"),
            # Season P-variants
            season_xswing_p=_bl("xSwing_P"),
            season_xwhiff_p=_bl("xWhiff_P"),
            season_xgor_p=_bl("xGOr_P"),
            season_xpur_p=_bl("xPUr_P"),
            season_xhr100_p=_bl("xHR100_P"),
            season_bbe_prob_p=_bl("BBE_prob_P"),
            season_xswst_p=_bl("xSwSt_P"),
            season_xrv100_p=_bl("xRV100_P"),
            # Season S-variants
            season_xswing_s=_bl("xSwing_S"),
            season_xwhiff_s=_bl("xWhiff_S"),
            season_xgor_s=_bl("xGOr_S"),
            season_xpur_s=_bl("xPUr_S"),
            season_xhr100_s=_bl("xHR100_S"),
            season_bbe_prob_s=_bl("BBE_prob_S"),
            season_xswst_s=_bl("xSwSt_S"),
            season_xrv100_s=_bl("xRV100_S"),
            # Metadata
            n_pitches=n_pitches,
            small_sample=n_pitches < _MIN_PITCHES,
            cold_start=cold_start,
        ))

    results.sort(key=lambda x: x.n_pitches, reverse=True)
    return results


def compute_workload_context(data: PitcherData) -> WorkloadContext:
    """Compute workload and rest context for the pitcher.

    Builds appearance workload entries with IP (baseball notation), pitch
    counts, rest days, and consecutive-days tracking.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        WorkloadContext dataclass with appearance list and flags.
    """
    # Sort appearances by game_date ascending
    appearances = data.appearances.sort("game_date")

    # Extract appearance dates for rest days and consecutive days
    appearance_dates = appearances["game_date"].to_list()
    rest_days_list = _compute_rest_days(appearance_dates)
    max_consec = _max_consecutive_days(appearance_dates)

    # Batch compute IP and pitch counts in one pass each
    ip_by_game = _compute_ip_all_games(data.statcast)
    pitch_counts = (
        data.statcast.group_by("game_pk")
        .agg(pl.len().alias("n"))
    )
    pc_map = dict(zip(
        pitch_counts["game_pk"].to_list(),
        pitch_counts["n"].to_list(),
        strict=False,
    ))

    workload_entries: list[AppearanceWorkload] = []

    for i, row in enumerate(appearances.iter_rows(named=True)):
        game_pk = int(row["game_pk"])
        workload_entries.append(
            AppearanceWorkload(
                game_pk=game_pk,
                game_date=str(row["game_date"]),
                role=str(row["role"]),
                ip=ip_by_game.get(game_pk, "0.0"),
                pitch_count=pc_map.get(game_pk, 0),
                rest_days=rest_days_list[i],
            )
        )

    return WorkloadContext(
        appearances=workload_entries,
        max_consecutive_days=max_consec,
        workload_concern=max_consec >= 3,
    )


def _sum_baseball_ip(ip_strings: list[str]) -> str:
    """Sum a list of baseball-notation IP strings.

    Each IP string is in the format "W.R" where W is whole innings and
    R is the remainder (0, 1, or 2 thirds of an inning). Converts each
    to thirds, sums, and converts back.

    Args:
        ip_strings: List of IP strings, e.g., ["5.1", "3.2", "6.0"].

    Returns:
        Summed IP in baseball notation, e.g., "15.0".
    """
    total_thirds = 0
    for ip in ip_strings:
        parts = ip.split(".")
        whole = int(parts[0])
        remainder = int(parts[1]) if len(parts) > 1 else 0
        total_thirds += whole * 3 + remainder
    return f"{total_thirds // 3}.{total_thirds % 3}"


def compute_temporal_context(
    data: PitcherData,
    workload: WorkloadContext,
) -> TemporalContext:
    """Compute temporal grounding for LLM narratives.

    Splits appearances by season year, counts per-season appearances and
    IP totals, and assigns a prior-year relevance tier that gates how
    much weight the LLM gives to last season's workload.

    Reuses IP values already computed by compute_workload_context() to
    avoid redundant statcast scans.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.
        workload: Pre-computed workload context (provides per-game IP).

    Returns:
        TemporalContext with per-season stats and relevance tier.
    """
    appearances = data.appearances.with_columns(
        pl.col("game_date").dt.year().alias("season_year")
    )

    current_season = int(appearances["season_year"].max())
    prior_season = current_season - 1

    # Build game_pk → IP lookup from workload (already computed)
    ip_by_game = {a.game_pk: a.ip for a in workload.appearances}

    # Current season appearances
    current_apps = appearances.filter(pl.col("season_year") == current_season)
    current_season_appearances = current_apps.height

    # Current season first date
    current_first_date = str(current_apps["game_date"].min())

    # Current season IP from workload lookup
    current_game_pks = current_apps["game_pk"].to_list()
    current_ip_strings = [ip_by_game.get(int(gpk), "0.0") for gpk in current_game_pks]
    current_season_ip = _sum_baseball_ip(current_ip_strings) if current_ip_strings else "0.0"

    # Prior season appearances
    prior_apps = appearances.filter(pl.col("season_year") == prior_season)
    prior_season_appearances = prior_apps.height

    # Prior season IP from workload lookup
    if prior_season_appearances > 0:
        prior_game_pks = prior_apps["game_pk"].to_list()
        prior_ip_strings = [ip_by_game.get(int(gpk), "0.0") for gpk in prior_game_pks]
        prior_season_ip = _sum_baseball_ip(prior_ip_strings)
    else:
        prior_season_ip = "0.0"

    # Prior-year relevance tier
    if prior_season_appearances == 0:
        relevance = "N/A"
        relevance_reason = (
            f"No {prior_season} data available. Current season sample "
            f"({current_season_appearances} appearances) stands alone -- "
            f"prior-year workload is not a factor."
        )
    elif current_season_appearances < 10:
        relevance = "HIGH"
        relevance_reason = (
            f"Current season sample is too small to establish its own workload "
            f"narrative. {prior_season} workload ({prior_season_appearances} G / "
            f"{prior_season_ip} IP) is plausible residual context, but do not "
            f"treat the two seasons as a continuous timeline."
        )
    elif current_season_appearances <= 30:
        relevance = "MODERATE"
        relevance_reason = (
            "Patterns are emerging but sample is still growing. Prior year "
            "adds context for year-over-year comparison."
        )
    else:
        relevance = "LOW"
        relevance_reason = (
            "Current season has enough volume to carry its own workload "
            "narrative. Use prior year for trend comparison only, not "
            "workload narrative."
        )

    return TemporalContext(
        analysis_date=date.today(),
        current_season=current_season,
        current_season_appearances=current_season_appearances,
        current_season_first_date=current_first_date,
        current_season_ip=current_season_ip,
        prior_season=prior_season,
        prior_season_appearances=prior_season_appearances,
        prior_season_ip=prior_season_ip,
        prior_year_relevance=relevance,
        prior_year_relevance_reason=relevance_reason,
    )


def compute_cross_season_summary(data: PitcherData) -> CrossSeasonSummary | None:
    """Compute cross-season YoY deltas for pitcher-level metrics.

    Compares current (max) season baselines with prior-season baselines
    to produce year-over-year delta strings for velocity, P+, S+, and L+.

    Per-season workload (appearances, IP) lives in TemporalContext — this
    function focuses on the metric deltas that TemporalContext does not cover.

    Returns None when prior-season data is missing (SDLT-03).

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        CrossSeasonSummary with YoY deltas, or None for single-season pitchers.
    """
    if data.prior_season_baseline.is_empty():
        return None

    # Extract season years
    current_season = int(data.season_baseline["season"][0])
    prior_seasons = data.prior_season_baseline["season"].unique().to_list()
    prior_season = int(max(prior_seasons))

    # P+ / S+ / L+ from season baselines (SDLT-01)
    current_p_plus = _safe_metric(data.season_baseline, "P+")
    current_s_plus = _safe_metric(data.season_baseline, "S+")
    current_l_plus = _safe_metric(data.season_baseline, "L+")

    prior_p_plus = _safe_metric(data.prior_season_baseline, "P+")
    prior_s_plus = _safe_metric(data.prior_season_baseline, "S+")
    prior_l_plus = _safe_metric(data.prior_season_baseline, "L+")

    # Velocity from statcast release_speed per season (SDLT-01)
    velo_by_season = _per_season_velo(data.statcast)
    current_velo = velo_by_season.get(current_season)
    prior_velo = velo_by_season.get(prior_season)

    # Delta strings reusing existing functions (SDLT-02)
    velo_delta = (
        _velo_delta_string(current_velo - prior_velo)
        if current_velo is not None and prior_velo is not None
        else "N/A"
    )
    p_plus_delta = _pplus_delta_string(current_p_plus - prior_p_plus)
    s_plus_delta = _pplus_delta_string(current_s_plus - prior_s_plus)
    l_plus_delta = _pplus_delta_string(current_l_plus - prior_l_plus)

    return CrossSeasonSummary(
        current_season=current_season,
        prior_season=prior_season,
        current_velo=current_velo,
        prior_velo=prior_velo,
        velo_delta=velo_delta,
        current_p_plus=current_p_plus,
        prior_p_plus=prior_p_plus,
        p_plus_delta=p_plus_delta,
        current_s_plus=current_s_plus,
        prior_s_plus=prior_s_plus,
        s_plus_delta=s_plus_delta,
        current_l_plus=current_l_plus,
        prior_l_plus=prior_l_plus,
        l_plus_delta=l_plus_delta,
    )


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


def compute_release_point_metrics(data: PitcherData) -> ReleasePointMetrics:
    """Compute per-pitch-type release point analysis with window vs season deltas.

    Computes mean release_pos_x, release_pos_z, and release_extension for
    each pitch type in both the lookback window and full season, then produces
    qualitative delta strings.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        ReleasePointMetrics with per-pitch-type entries ordered by season
        usage descending.
    """
    cold_start = _is_cold_start(data)
    window_dates = _get_window_game_dates(data)
    name_map = _build_name_map(data.statcast)

    _release_cols = ["release_pos_x", "release_pos_z", "release_extension"]

    # Filter to rows with non-null release data
    valid = data.statcast.filter(
        pl.col("release_pos_x").is_not_null()
        & pl.col("release_pos_z").is_not_null()
        & pl.col("release_extension").is_not_null()
    )

    # Season aggregates by pitch_type
    season_agg = valid.group_by("pitch_type").agg(
        pl.col("release_pos_x").mean().alias("season_x"),
        pl.col("release_pos_z").mean().alias("season_z"),
        pl.col("release_extension").mean().alias("season_ext"),
        pl.len().alias("n_season"),
    )

    # Window aggregates by pitch_type
    window_valid = valid.filter(pl.col("game_date").is_in(window_dates))
    window_agg = window_valid.group_by("pitch_type").agg(
        pl.col("release_pos_x").mean().alias("window_x"),
        pl.col("release_pos_z").mean().alias("window_z"),
        pl.col("release_extension").mean().alias("window_ext"),
        pl.len().alias("n_window"),
    )

    # Join window and season on pitch_type (only types present in both)
    joined = window_agg.join(season_agg, on="pitch_type", how="inner")

    # Sort by season pitch count descending (matches arsenal ordering)
    joined = joined.sort("n_season", descending=True)

    pitch_types: list[ReleasePointPitchType] = []
    for row in joined.iter_rows(named=True):
        pt = row["pitch_type"]
        n_window = int(row["n_window"])
        small_sample = n_window < _MIN_PITCHES

        if cold_start:
            x_delta = _COLD_START_STRING
            z_delta = _COLD_START_STRING
            ext_delta = _COLD_START_STRING
        else:
            x_delta = _release_delta_string(row["window_x"] - row["season_x"])
            z_delta = _release_delta_string(row["window_z"] - row["season_z"])
            ext_delta = _extension_delta_string(row["window_ext"] - row["season_ext"])

        pitch_types.append(
            ReleasePointPitchType(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                window_release_x=float(row["window_x"]),
                season_release_x=float(row["season_x"]),
                release_x_delta=x_delta,
                window_release_z=float(row["window_z"]),
                season_release_z=float(row["season_z"]),
                release_z_delta=z_delta,
                window_extension=float(row["window_ext"]),
                season_extension=float(row["season_ext"]),
                extension_delta=ext_delta,
                n_pitches_window=n_window,
                small_sample=small_sample,
                cold_start=cold_start,
            )
        )

    return ReleasePointMetrics(
        pitch_types=pitch_types,
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
