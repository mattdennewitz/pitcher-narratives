"""Computation engine for pitcher narratives.

Transforms PitcherData into pre-computed analysis with qualitative trend
strings ready for LLM consumption. Computes fastball quality deltas
(velocity, P+/S+/L+, movement), within-game velocity arcs, and shared
delta helpers used across all analysis facets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import polars as pl

from pitcher_narratives.data import AGGS_DIR, PARQUET_PATH, PitcherData, load_run_values


def _float(val: Any) -> float:
    """Cast a Polars scalar to float, satisfying mypy."""
    return float(cast(float, val))


__all__ = [
    "AppearanceWorkload",
    "ComponentAttribution",
    "ExecutionMetrics",
    "FastballSummary",
    "FirstPitchEntry",
    "FirstPitchWeaponry",
    "HardHitRate",
    "IntermediateProbabilities",
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
    "VelocityArc",
    "WorkloadContext",
    "compute_arsenal_summary",
    "compute_component_attribution",
    "compute_execution_metrics",
    "compute_fastball_summary",
    "compute_first_pitch_weaponry",
    "compute_hard_hit_rate",
    "compute_intermediate_probabilities",
    "compute_platoon_mix",
    "compute_release_point_metrics",
    "compute_tto_analysis",
    "compute_velocity_arc",
    "compute_workload_context",
    "LeagueBaseline",
    "compute_league_baselines",
    "format_s_variant_comparisons",
    "outlier_tag",
    "render_league_baselines",
]

# ── Constants ─────────────────────────────────────────────────────────

_FASTBALL_TYPES = frozenset({"FF", "SI", "FC"})
"""Standard Statcast fastball classification codes."""

_VELO_THRESHOLD = 0.5
"""MPH below which velocity delta is 'Steady' (noise floor)."""

_PPLUS_THRESHOLD = 5
"""Points below which P+/S+/L+ delta is 'Steady'."""

_SHARP_VELO_THRESHOLD = 2.0
"""MPH above which velocity delta is 'sharply'."""

_SHARP_PPLUS_THRESHOLD = 10
"""Points above which P+/S+/L+ delta is 'sharply'."""

_USAGE_THRESHOLD = 5.0
"""Percentage points below which usage delta is 'Steady'."""

_MOVEMENT_THRESHOLD = 0.5
"""Inches below which movement delta is 'Steady'."""

_MIN_PITCHES = 10
"""Minimum pitches for per-type analysis; below this flag small_sample=True."""

_COLD_START_STRING = "Full season in window -- no trend comparison"
"""Delta string used when window covers entire season."""

_CSW_DESCRIPTIONS = frozenset(
    {
        "called_strike",
        "swinging_strike",
        "swinging_strike_blocked",
    }
)
"""Descriptions that count as called + swinging strikes."""

_SWING_DESCRIPTIONS = frozenset(
    {
        "swinging_strike",
        "swinging_strike_blocked",
        "foul",
        "foul_tip",
        "hit_into_play",
        "foul_bunt",
        "bunt_foul_tip",
        "missed_bunt",
    }
)
"""All descriptions that count as a swing attempt."""

_ZONE_IN = list(range(1, 10))
"""Strike zone: zones 1-9."""

_ZONE_OUT = [11, 12, 13, 14]
"""Outside zone (chase zone)."""

_OUT_EVENTS = frozenset(
    {
        "strikeout",
        "field_out",
        "grounded_into_double_play",
        "force_out",
        "sac_fly",
        "sac_bunt",
        "fielders_choice",
        "double_play",
        "sac_fly_double_play",
        "strikeout_double_play",
    }
)
"""Events that produce at least one out."""

_DOUBLE_OUT_EVENTS = frozenset(
    {
        "grounded_into_double_play",
        "double_play",
        "sac_fly_double_play",
        "strikeout_double_play",
    }
)
"""Events that produce two outs."""


# ── League baselines ─────────────────────────────────────────────────

@dataclass
class LeagueBaseline:
    """League-average physical profile and S-variant benchmarks for a pitch type.

    Physical metrics (velo, movement, zone/chase) come from the Statcast parquet.
    S-variant benchmarks (S+, xSwing_S, xWhiff_S, xRV100_S) come from the
    pitcher_type CSV aggregated across all pitchers, weighted by n_pitches.
    """

    pitch_type: str
    pitch_name: str
    n_pitches: int
    # Physical averages
    avg_velo: float
    avg_pfx_x: float
    avg_pfx_z: float
    zone_pct: float
    chase_pct: float
    # Physical standard deviations (for outlier detection)
    velo_std: float
    pfx_x_std: float
    pfx_z_std: float
    # S-variant benchmarks (league averages weighted by n_pitches)
    avg_s_plus: float | None = None
    avg_xswing_s: float | None = None
    avg_xwhiff_s: float | None = None
    avg_xrv100_s: float | None = None


_league_baselines_cache: list[LeagueBaseline] | None = None


def compute_league_baselines() -> list[LeagueBaseline]:
    """Compute league-average velocity, movement, zone/chase, and S-variant benchmarks.

    Physical metrics and standard deviations come from the Statcast parquet.
    S-variant benchmarks (S+, xSwing_S, xWhiff_S, xRV100_S) are weighted
    averages from the pitcher_type CSV across all pitchers.

    Results are cached after first call. Only includes pitch types with
    at least 100 pitches in the dataset.

    Returns:
        List of LeagueBaseline sorted by pitch count descending.
    """
    global _league_baselines_cache
    if _league_baselines_cache is not None:
        return _league_baselines_cache

    df = pl.read_parquet(
        PARQUET_PATH,
        columns=["pitch_type", "pitch_name", "release_speed", "pfx_x", "pfx_z", "zone", "description"],
    )
    df = df.filter(pl.col("release_speed").is_not_null())

    is_in_zone = pl.col("zone").is_between(1, 9)
    is_swing = pl.col("description").is_in(list(_SWING_DESCRIPTIONS))

    agg = (
        df.group_by("pitch_type", "pitch_name")
        .agg(
            pl.len().alias("n"),
            pl.col("release_speed").mean().alias("avg_velo"),
            pl.col("release_speed").std().alias("velo_std"),
            pl.col("pfx_x").mean().alias("avg_pfx_x"),
            pl.col("pfx_x").std().alias("pfx_x_std"),
            pl.col("pfx_z").mean().alias("avg_pfx_z"),
            pl.col("pfx_z").std().alias("pfx_z_std"),
            (is_in_zone.mean() * 100).alias("zone_pct"),
            # Chase: swings on pitches outside zones 1-9
            ((is_in_zone.not_() & is_swing).sum()
             / (is_in_zone.not_()).sum() * 100).alias("chase_pct"),
        )
        .filter(pl.col("n") >= 100)
        .sort("n", descending=True)
    )

    # --- S-variant benchmarks from pitcher_type CSV ---
    s_variant_lookup: dict[str, dict[str, float]] = {}
    pitcher_type_path = AGGS_DIR / "2026-pitcher_type.csv"
    if pitcher_type_path.exists():
        pt_df = pl.read_csv(pitcher_type_path)
        # Weighted average across all pitchers per pitch type
        s_agg = (
            pt_df.filter(pl.col("n_pitches") >= 10)
            .group_by("pitch_type")
            .agg(
                (pl.col("S+") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
                (pl.col("xSwing_S") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
                (pl.col("xWhiff_S") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
                (pl.col("xRV100_S") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
            )
        )
        for row in s_agg.iter_rows(named=True):
            s_variant_lookup[row["pitch_type"]] = {
                "avg_s_plus": float(row["S+"]),
                "avg_xswing_s": float(row["xSwing_S"]),
                "avg_xwhiff_s": float(row["xWhiff_S"]),
                "avg_xrv100_s": float(row["xRV100_S"]),
            }

    results = []
    for row in agg.iter_rows(named=True):
        pt = row["pitch_type"]
        s_data = s_variant_lookup.get(pt, {})
        results.append(
            LeagueBaseline(
                pitch_type=pt,
                pitch_name=row["pitch_name"],
                n_pitches=row["n"],
                avg_velo=float(row["avg_velo"]),
                avg_pfx_x=float(row["avg_pfx_x"]),
                avg_pfx_z=float(row["avg_pfx_z"]),
                zone_pct=float(row["zone_pct"]),
                chase_pct=float(row["chase_pct"]),
                velo_std=float(row["velo_std"]) if row["velo_std"] is not None else 0.0,
                pfx_x_std=float(row["pfx_x_std"]) if row["pfx_x_std"] is not None else 0.0,
                pfx_z_std=float(row["pfx_z_std"]) if row["pfx_z_std"] is not None else 0.0,
                avg_s_plus=s_data.get("avg_s_plus"),
                avg_xswing_s=s_data.get("avg_xswing_s"),
                avg_xwhiff_s=s_data.get("avg_xwhiff_s"),
                avg_xrv100_s=s_data.get("avg_xrv100_s"),
            )
        )

    _league_baselines_cache = results
    return results


def outlier_tag(value: float, avg: float, std: float) -> str:
    """Return OUTLIER or NORMAL tag based on z-score from league average."""
    if std == 0:
        return "NORMAL"
    z = (value - avg) / std
    if abs(z) > 1.5:
        direction = "above" if z > 0 else "below"
        return f"OUTLIER ({direction} avg, z={z:+.1f})"
    return f"NORMAL (z={z:+.1f})"


def render_league_baselines(pitch_types: list[str]) -> str:
    """Render league-average baselines with normal ranges and S-variant benchmarks.

    Includes standard deviations so agents can determine whether a pitcher's
    metrics are outliers or within the normal range for that pitch type.
    """
    baselines = compute_league_baselines()
    lookup = {b.pitch_type: b for b in baselines}

    lines = [
        "## League Baselines (2026, all pitchers)",
        "Use these baselines to determine whether a metric is an outlier or normal.",
        "A metric within ±1.5 stddev of the league average is NORMAL for that pitch type.",
        "",
    ]
    for pt in pitch_types:
        b = lookup.get(pt)
        if b is None:
            continue
        lines.append(f"### {b.pitch_name} ({b.pitch_type})")
        lines.append(
            f"- Velocity: {b.avg_velo:.1f} mph (stddev {b.velo_std:.1f}, "
            f"normal range {b.avg_velo - 1.5 * b.velo_std:.1f}–{b.avg_velo + 1.5 * b.velo_std:.1f})"
        )
        lines.append(f"- Horizontal movement (pfx_x): {b.avg_pfx_x:.1f} in (stddev {b.pfx_x_std:.1f})")
        lines.append(f"- Vertical movement (pfx_z): {b.avg_pfx_z:.1f} in (stddev {b.pfx_z_std:.1f})")
        lines.append(f"- Zone%: {b.zone_pct:.1f}, Chase%: {b.chase_pct:.1f}")
        if b.avg_s_plus is not None:
            xswing = f"{b.avg_xswing_s * 100:.1f}%" if b.avg_xswing_s is not None else "--"
            xwhiff = f"{b.avg_xwhiff_s * 100:.1f}%" if b.avg_xwhiff_s is not None else "--"
            xrv = f"{b.avg_xrv100_s:.2f}" if b.avg_xrv100_s is not None else "--"
            lines.append(
                f"- S-variant league avg: S+ {b.avg_s_plus:.0f}, "
                f"xSwing_S {xswing}, xWhiff_S {xwhiff}, xRV100_S {xrv}"
            )
        lines.append("")
    return "\n".join(lines)


def format_s_variant_comparisons(
    baseline: LeagueBaseline | None,
    xswing_s: float | None,
    xwhiff_s: float | None,
    xrv100_s: float | None,
) -> list[str]:
    """Format S-variant predictions with league comparison deltas.

    Returns a list of formatted strings like:
        ["xSwing_S 37.0% (-7.5pp vs league)", "xWhiff_S 31.2% (-7.6pp vs league)", ...]
    """
    parts: list[str] = []
    b = baseline

    xswing_str = f"{xswing_s * 100:.1f}%" if xswing_s is not None else "--"
    if b and xswing_s is not None and b.avg_xswing_s is not None:
        d = (xswing_s - b.avg_xswing_s) * 100
        parts.append(f"xSwing_S {xswing_str} ({d:+.1f}pp vs league)")
    else:
        parts.append(f"xSwing_S {xswing_str}")

    xwhiff_str = f"{xwhiff_s * 100:.1f}%" if xwhiff_s is not None else "--"
    if b and xwhiff_s is not None and b.avg_xwhiff_s is not None:
        d = (xwhiff_s - b.avg_xwhiff_s) * 100
        parts.append(f"xWhiff_S {xwhiff_str} ({d:+.1f}pp vs league)")
    else:
        parts.append(f"xWhiff_S {xwhiff_str}")

    xrv_str = f"{xrv100_s:.2f}" if xrv100_s is not None else "--"
    if b and xrv100_s is not None and b.avg_xrv100_s is not None:
        d = xrv100_s - b.avg_xrv100_s
        parts.append(f"xRV100_S {xrv_str} ({d:+.2f} vs league)")
    else:
        parts.append(f"xRV100_S {xrv_str}")

    return parts


# ── Delta string helpers (private) ────────────────────────────────────


def _velo_delta_string(delta: float, threshold: float = _VELO_THRESHOLD) -> str:
    """Convert velocity delta to qualitative string.

    Args:
        delta: window_value - season_value (positive = faster).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 1.5 mph', 'Down sharply (-2.5 mph)',
        or 'Steady (+0.3)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f})"
    direction = "Up" if delta > 0 else "Down"
    if abs(delta) >= _SHARP_VELO_THRESHOLD:
        return f"{direction} sharply ({delta:+.1f} mph)"
    return f"{direction} {abs(delta):.1f} mph"


def _pplus_delta_string(delta: float, threshold: float = _PPLUS_THRESHOLD) -> str:
    """Convert P+/S+/L+ delta to qualitative string.

    Args:
        delta: window_value - season_value (positive = improved).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 8 points', 'Down sharply (-15 points)',
        or 'Steady (+3)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.0f})"
    direction = "Up" if delta > 0 else "Down"
    if abs(delta) >= _SHARP_PPLUS_THRESHOLD:
        return f"{direction} sharply ({delta:+.0f} points)"
    return f"{direction} {abs(delta):.0f} points"


def _usage_delta_string(delta: float, threshold: float = _USAGE_THRESHOLD) -> str:
    """Convert usage rate delta (percentage points) to qualitative string.

    Args:
        delta: window_pct - season_pct (positive = more usage).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up sharply (+12.0 pp)', 'Up 7.0 pp',
        or 'Steady (+2.0 pp)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f} pp)"
    direction = "Up" if delta > 0 else "Down"
    if abs(delta) >= 10.0:
        return f"{direction} sharply ({delta:+.1f} pp)"
    return f"{direction} {abs(delta):.1f} pp"


def _movement_delta_string(delta: float, threshold: float = _MOVEMENT_THRESHOLD) -> str:
    """Convert movement delta (inches) to qualitative string.

    Args:
        delta: window_value - season_value (positive = more movement).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 1.5 in' or 'Steady (+0.2 in)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f} in)"
    direction = "Up" if delta > 0 else "Down"
    return f"{direction} {abs(delta):.1f} in"


# ── Internal helpers ──────────────────────────────────────────────────


def _safe_metric(df: pl.DataFrame, col: str, default: float = 0.0) -> float:
    """Extract the first value of a metric column, or default if unavailable."""
    if df.is_empty() or col not in df.columns:
        return default
    return float(df[col][0])


def _pplus_delta_strings(
    cold_start: bool,
    season_p: float,
    season_s: float,
    season_l: float,
    window_p: float | None,
    window_s: float | None,
    window_l: float | None,
) -> tuple[str, str, str]:
    """Compute P+/S+/L+ delta strings with cold start and None handling."""
    if cold_start:
        return _COLD_START_STRING, _COLD_START_STRING, _COLD_START_STRING
    if window_p is None:
        return "No window data", "No window data", "No window data"
    return (
        _pplus_delta_string(window_p - season_p),
        _pplus_delta_string(window_s - season_s) if window_s is not None else "No window data",
        _pplus_delta_string(window_l - season_l) if window_l is not None else "No window data",
    )


def _build_name_map(statcast: pl.DataFrame) -> dict[str, str]:
    """Build pitch_type → pitch_name mapping from statcast data."""
    name_df = statcast.select(["pitch_type", "pitch_name"]).unique()
    return {row["pitch_type"]: row["pitch_name"] for row in name_df.iter_rows(named=True)}


def _identify_primary_fastball(pitch_type_baseline: pl.DataFrame) -> str | None:
    """Return the pitch_type code of the highest-usage fastball type.

    Filters pitch_type_baseline to rows where pitch_type is in
    _FASTBALL_TYPES, sorts by n_pitches descending, and returns the first.

    Args:
        pitch_type_baseline: Per-pitch-type weighted baselines from data.py.

    Returns:
        Pitch type code (e.g., 'FC') or None if no fastball types found.
    """
    fb_rows = pitch_type_baseline.filter(pl.col("pitch_type").is_in(list(_FASTBALL_TYPES)))
    if fb_rows.is_empty():
        return None
    return str(fb_rows.sort("n_pitches", descending=True)["pitch_type"][0])


def _get_window_game_dates(data: PitcherData) -> list[Any]:
    """Extract unique game_date values from window_appearances.

    Args:
        data: PitcherData bundle.

    Returns:
        List of game dates within the lookback window.
    """
    return data.window_appearances["game_date"].unique().to_list()


def _is_cold_start(data: PitcherData) -> bool:
    """Check if window covers the full season (cold start).

    Args:
        data: PitcherData bundle.

    Returns:
        True when window_appearances covers all appearances.
    """
    return len(data.window_appearances) >= len(data.appearances)


def _weighted_window_metrics(
    df: pl.DataFrame,
    metrics: tuple[str, ...],
    filters: pl.Expr,
) -> dict[str, float | int | None]:
    """Compute n_pitches-weighted averages for specified metrics in a window.

    Applies the given filter expression, then computes weighted averages
    for each metric column present. Returns None for missing columns or
    empty windows.

    Args:
        df: DataFrame with n_pitches and metric columns.
        metrics: Tuple of metric column names to average.
        filters: Polars expression combining all filter conditions.

    Returns:
        Dict keyed by metric names plus 'n_pitches'. Values are None
        if no data found.
    """
    window = df.filter(filters)

    empty: dict[str, float | int | None] = {m: None for m in metrics}
    empty["n_pitches"] = 0

    if window.is_empty():
        return empty

    total_pitches = window["n_pitches"].sum()
    if total_pitches == 0:
        return empty

    result: dict[str, float | int | None] = {"n_pitches": int(total_pitches)}
    for metric in metrics:
        if metric in window.columns:
            weighted = (window[metric] * window["n_pitches"]).sum()
            result[metric] = _float(weighted) / _float(total_pitches)
        else:
            result[metric] = None

    return result


def _stand_to_platoon(stand: str, p_throws: str) -> str:
    """Map batter handedness + pitcher handedness to platoon matchup label.

    Args:
        stand: Batter handedness ('L' or 'R').
        p_throws: Pitcher handedness ('L' or 'R').

    Returns:
        'same' if stand == p_throws, else 'opposite'.
    """
    return "same" if stand == p_throws else "opposite"


def _compute_platoon_baseline(pitcher_type_platoon_df: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted baseline per (pitch_type, platoon_matchup).

    Combines game_type rows using pitch-count weighting, same pattern as
    compute_pitch_type_baseline in data.py but grouped by platoon_matchup.

    Args:
        pitcher_type_platoon_df: The pitcher_type_platoon CSV DataFrame
            filtered to one pitcher.

    Returns:
        DataFrame with one row per (pitch_type, platoon_matchup) and
        weighted average metrics.
    """
    df = pitcher_type_platoon_df.filter(pl.col("pitch_type") != "")
    id_cols = frozenset(
        {
            "season",
            "level",
            "game_type",
            "pitcher",
            "player_name",
            "p_throws",
            "team_code",
            "n_pitches",
            "pitch_type",
            "platoon_matchup",
        }
    )
    metric_cols = [c for c in df.columns if c not in id_cols]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return df.group_by(["pitcher", "pitch_type", "platoon_matchup"]).agg(
        pl.col("n_pitches").sum(),
        *weighted_exprs,
    )


_PPLUS_METRICS = ("P+", "S+", "L+")
"""Pitching+ family metrics used in weighted-average computations."""

_XMETRICS = ("xWhiff_P", "xSwing_P", "xRV100_P")
"""Expected-outcome metrics used in execution computations."""

_INTERMEDIATE_P_COLS = (
    "xSwing_P", "xWhiff_P", "xGOr_P", "xPUr_P", "xHR100_P",
    "BBE_prob_P", "xSwSt_P", "xRV100_P",
)
"""P-variant intermediate probability columns (includes location)."""

_INTERMEDIATE_S_COLS = (
    "xSwing_S", "xWhiff_S", "xGOr_S", "xPUr_S", "xHR100_S",
    "BBE_prob_S", "xSwSt_S", "xRV100_S",
)
"""S-variant intermediate probability columns (stuff-only)."""

_INTERMEDIATE_COLS = _INTERMEDIATE_P_COLS + _INTERMEDIATE_S_COLS
"""All intermediate probability columns (P and S variants)."""

_OUTCOME_COLS_P = (
    "HBP_P", "called_ball_P", "called_strike_P", "whiff_P", "foul_P",
    "double_P", "ground_out_P", "home_run_P", "line_out_P",
    "low_line_out_P", "pop_out_P", "single_P", "triple_P",
)
"""P-variant raw probability columns for the 13 model outcomes."""

_OUTCOME_NAMES = (
    "HBP", "called_ball", "called_strike", "whiff", "foul",
    "double", "ground_out", "home_run", "line_out",
    "low_line_out", "pop_out", "single", "triple",
)
"""Canonical outcome names matching model_classes in RV_df.csv."""


# ── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class FastballSummary:
    """Pre-computed fastball quality analysis ready for LLM."""

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    season_velo: float
    window_velo: float
    velo_delta: str
    """E.g., 'Down 1.2 mph'."""

    season_p_plus: float
    window_p_plus: float | None
    p_plus_delta: str

    season_s_plus: float
    window_s_plus: float | None
    s_plus_delta: str

    season_l_plus: float
    window_l_plus: float | None
    l_plus_delta: str

    season_pfx_x: float
    window_pfx_x: float
    pfx_x_delta: str

    season_pfx_z: float
    window_pfx_z: float
    pfx_z_delta: str

    small_sample: bool
    """True when fewer than _MIN_PITCHES fastballs in window."""

    cold_start: bool
    """True when window covers the full season."""


@dataclass
class VelocityArc:
    """Within-game velocity progression for most recent appearance."""

    game_pk: int
    game_date: str
    """ISO date string."""

    available: bool
    early_velo: float | None
    late_velo: float | None
    drop: float | None
    """late - early (negative = velocity dropped)."""

    drop_string: str
    """E.g., 'Dropped 1.3 mph' or 'Single inning -- no velocity arc available'."""

    innings_pitched: int


@dataclass
class PitchTypeSummary:
    """Per-pitch-type arsenal breakdown ready for LLM."""

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    season_usage_pct: float
    """Season usage as percentage, e.g., 44.5."""

    window_usage_pct: float
    """Window usage as percentage."""

    usage_delta: str
    """Qualitative usage delta, e.g., 'Up 3.2 pp'."""

    season_p_plus: float
    window_p_plus: float | None
    p_plus_delta: str

    season_s_plus: float
    window_s_plus: float | None
    s_plus_delta: str

    season_l_plus: float
    window_l_plus: float | None
    l_plus_delta: str

    season_velo: float
    """Season average velocity (mph)."""
    window_velo: float
    """Window average velocity (mph)."""
    velo_delta: str
    """Qualitative velocity delta, e.g., 'Up 1.5 mph'."""

    season_pfx_x: float
    """Season average horizontal movement (inches)."""
    window_pfx_x: float
    """Window average horizontal movement (inches)."""
    pfx_x_delta: str

    season_pfx_z: float
    """Season average vertical movement (inches)."""
    window_pfx_z: float
    """Window average vertical movement (inches)."""
    pfx_z_delta: str

    n_pitches_season: int
    n_pitches_window: int
    small_sample: bool
    """True when fewer than _MIN_PITCHES of this type in window."""

    cold_start: bool
    """True when window covers the full season."""


@dataclass
class PlatoonSplit:
    """Usage breakdown for one pitch type against one platoon side."""

    pitch_type: str
    pitch_name: str
    platoon_side: str
    """'same' or 'opposite'."""

    season_usage_pct: float
    window_usage_pct: float | None
    usage_delta: str

    season_p_plus: float | None
    window_p_plus: float | None
    p_plus_delta: str

    available: bool
    """False if pitch not thrown to this side."""


@dataclass
class PlatoonMix:
    """Platoon mix shift analysis ready for LLM."""

    splits: list[PlatoonSplit]
    cold_start: bool


@dataclass
class FirstPitchEntry:
    """First-pitch usage for one pitch type."""

    pitch_type: str
    pitch_name: str
    season_pct: float
    window_pct: float
    delta: str
    n_first_pitches_season: int
    n_first_pitches_window: int


@dataclass
class FirstPitchWeaponry:
    """First-pitch strike weaponry analysis ready for LLM."""

    entries: list[FirstPitchEntry]
    """Ordered by window_pct descending."""

    total_first_pitches_season: int
    total_first_pitches_window: int
    cold_start: bool


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


def compute_fastball_summary(data: PitcherData) -> FastballSummary | None:
    """Compute fastball quality analysis with deltas and trend strings.

    Identifies the primary fastball type, computes season vs. window
    deltas for velocity, P+/S+/L+, and movement, and flags cold start
    and small sample conditions.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        FastballSummary dataclass or None if pitcher has no fastball types.
    """
    # Identify primary fastball
    primary = _identify_primary_fastball(data.pitch_type_baseline)
    if primary is None:
        return None

    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    # Filter statcast to primary fastball type
    fb_statcast = data.statcast.filter(pl.col("pitch_type") == primary)

    # ── Velocity ──────────────────────────────────────────────────
    season_velo = _float(fb_statcast["release_speed"].mean())
    window_fb = fb_statcast.filter(pl.col("game_date").is_in(window_dates))
    window_velo = _float(window_fb["release_speed"].mean())
    velo_delta = window_velo - season_velo

    velo_delta_str = _COLD_START_STRING if cold_start else _velo_delta_string(velo_delta)

    # ── Small sample ──────────────────────────────────────────────
    small_sample = len(window_fb) < _MIN_PITCHES

    # ── P+/S+/L+ ─────────────────────────────────────────────────
    # Season values from pitch_type_baseline
    pt_baseline = data.pitch_type_baseline.filter(pl.col("pitch_type") == primary)
    season_p_plus = _safe_metric(pt_baseline, "P+")
    season_s_plus = _safe_metric(pt_baseline, "S+")
    season_l_plus = _safe_metric(pt_baseline, "L+")

    # Window values from pitcher_type_appearance CSV
    window_pplus = _weighted_window_metrics(
        data.agg_csvs["pitcher_type_appearance"],
        _PPLUS_METRICS,
        _window_date_type_filter(window_dates, primary),
    )

    window_p_plus = window_pplus["P+"]
    window_s_plus = window_pplus["S+"]
    window_l_plus = window_pplus["L+"]

    p_plus_delta_str, s_plus_delta_str, l_plus_delta_str = _pplus_delta_strings(
        cold_start,
        season_p_plus,
        season_s_plus,
        season_l_plus,
        window_p_plus,
        window_s_plus,
        window_l_plus,
    )

    # ── Movement ──────────────────────────────────────────────────
    season_pfx_x = _float(fb_statcast["pfx_x"].mean())
    season_pfx_z = _float(fb_statcast["pfx_z"].mean())
    window_pfx_x = _float(window_fb["pfx_x"].mean())
    window_pfx_z = _float(window_fb["pfx_z"].mean())

    if cold_start:
        pfx_x_delta_str = _COLD_START_STRING
        pfx_z_delta_str = _COLD_START_STRING
    else:
        pfx_x_delta_str = _movement_delta_string(window_pfx_x - season_pfx_x)
        pfx_z_delta_str = _movement_delta_string(window_pfx_z - season_pfx_z)

    # ── Pitch name ────────────────────────────────────────────────
    name_rows = fb_statcast.select("pitch_name").unique()
    pitch_name = str(name_rows["pitch_name"][0]) if not name_rows.is_empty() else primary

    return FastballSummary(
        pitch_type=primary,
        pitch_name=pitch_name,
        season_velo=season_velo,
        window_velo=window_velo,
        velo_delta=velo_delta_str,
        season_p_plus=season_p_plus,
        window_p_plus=window_p_plus,
        p_plus_delta=p_plus_delta_str,
        season_s_plus=season_s_plus,
        window_s_plus=window_s_plus,
        s_plus_delta=s_plus_delta_str,
        season_l_plus=season_l_plus,
        window_l_plus=window_l_plus,
        l_plus_delta=l_plus_delta_str,
        season_pfx_x=season_pfx_x,
        window_pfx_x=window_pfx_x,
        pfx_x_delta=pfx_x_delta_str,
        season_pfx_z=season_pfx_z,
        window_pfx_z=window_pfx_z,
        pfx_z_delta=pfx_z_delta_str,
        small_sample=small_sample,
        cold_start=cold_start,
    )


def compute_velocity_arc(data: PitcherData, fastball_type: str) -> VelocityArc:
    """Compute within-game velocity progression for most recent appearance.

    Compares average fastball velocity in the first two innings vs. the last
    two innings of the most recent appearance. Returns a fallback message
    for single-inning outings.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.
        fastball_type: Pitch type code for the primary fastball (e.g., 'FC').

    Returns:
        VelocityArc dataclass with early/late velocity and drop string.
    """
    # Find most recent appearance
    recent = data.appearances.sort("game_date", descending=True).row(0, named=True)
    game_pk = int(recent["game_pk"])
    game_date = str(recent["game_date"])

    # Filter statcast to that game and fastball type
    game_fb = data.statcast.filter((pl.col("game_pk") == game_pk) & (pl.col("pitch_type") == fastball_type))

    innings = sorted(game_fb["inning"].unique().to_list())
    innings_pitched = len(innings)

    if innings_pitched < 2:
        return VelocityArc(
            game_pk=game_pk,
            game_date=game_date,
            available=False,
            early_velo=None,
            late_velo=None,
            drop=None,
            drop_string="Single inning -- no velocity arc available",
            innings_pitched=innings_pitched,
        )

    # First 2 and last 2 innings (may overlap if 2-3 innings total)
    early_innings = innings[:2]
    late_innings = innings[-2:]

    early_velo = _float(game_fb.filter(pl.col("inning").is_in(early_innings))["release_speed"].mean())
    late_velo = _float(game_fb.filter(pl.col("inning").is_in(late_innings))["release_speed"].mean())
    drop = late_velo - early_velo

    if abs(drop) < 0.5:
        drop_string = "Held steady"
    elif drop < 0:
        drop_string = f"Dropped {abs(drop):.1f} mph"
    else:
        drop_string = f"Gained {drop:.1f} mph"

    return VelocityArc(
        game_pk=game_pk,
        game_date=game_date,
        available=True,
        early_velo=early_velo,
        late_velo=late_velo,
        drop=drop,
        drop_string=drop_string,
        innings_pitched=innings_pitched,
    )


def compute_arsenal_summary(data: PitcherData) -> list[PitchTypeSummary]:
    """Compute per-pitch-type arsenal breakdown with usage and P+ deltas.

    Builds a PitchTypeSummary for every pitch type the pitcher throws,
    sorted by season usage descending. Each entry includes usage rates,
    P+/S+/L+ season vs window deltas, small sample flags, and cold start
    detection.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        List of PitchTypeSummary dataclasses ordered by season_usage_pct
        descending.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    # Get all pitch types from baseline sorted by n_pitches descending
    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    name_map = _build_name_map(data.statcast)

    # Total pitch counts
    total_season = len(data.statcast)
    window_statcast = data.statcast.filter(pl.col("game_date").is_in(window_dates))
    total_window = len(window_statcast)

    single_type = len(pitch_types) == 1

    results: list[PitchTypeSummary] = []
    for pt in pitch_types:
        # ── Usage rates ──────────────────────────────────────────
        pt_season = data.statcast.filter(pl.col("pitch_type") == pt)
        n_season = len(pt_season)
        season_usage_pct = n_season / total_season * 100.0

        pt_window = window_statcast.filter(pl.col("pitch_type") == pt)
        n_window = len(pt_window)
        window_usage_pct = n_window / total_window * 100.0 if total_window > 0 else 0.0

        # ── Usage delta ──────────────────────────────────────────
        if cold_start:
            usage_delta = _COLD_START_STRING
        elif single_type:
            usage_delta = "Only pitch type"
        else:
            usage_delta = _usage_delta_string(window_usage_pct - season_usage_pct)

        # ── P+/S+/L+ ────────────────────────────────────────────
        pt_baseline_row = baseline.filter(pl.col("pitch_type") == pt)
        season_p_plus = _safe_metric(pt_baseline_row, "P+")
        season_s_plus = _safe_metric(pt_baseline_row, "S+")
        season_l_plus = _safe_metric(pt_baseline_row, "L+")

        window_pplus = _weighted_window_metrics(
            data.agg_csvs["pitcher_type_appearance"],
            _PPLUS_METRICS,
            _window_date_type_filter(window_dates, pt),
        )
        window_p_plus = window_pplus["P+"]
        window_s_plus = window_pplus["S+"]
        window_l_plus = window_pplus["L+"]

        p_plus_delta, s_plus_delta, l_plus_delta = _pplus_delta_strings(
            cold_start,
            season_p_plus,
            season_s_plus,
            season_l_plus,
            window_p_plus,
            window_s_plus,
            window_l_plus,
        )

        # ── Pitch name ───────────────────────────────────────────
        pitch_name = name_map.get(pt, pt)

        # ── Velocity & movement ──────────────────────────────────
        season_velo = _float(pt_season["release_speed"].mean())
        window_velo = _float(pt_window["release_speed"].mean()) if n_window > 0 else season_velo

        season_pfx_x = _float(pt_season["pfx_x"].mean())
        window_pfx_x = _float(pt_window["pfx_x"].mean()) if n_window > 0 else season_pfx_x
        season_pfx_z = _float(pt_season["pfx_z"].mean())
        window_pfx_z = _float(pt_window["pfx_z"].mean()) if n_window > 0 else season_pfx_z

        if cold_start:
            velo_delta_str = _COLD_START_STRING
            pfx_x_delta_str = _COLD_START_STRING
            pfx_z_delta_str = _COLD_START_STRING
        else:
            velo_delta_str = _velo_delta_string(window_velo - season_velo)
            pfx_x_delta_str = _movement_delta_string(window_pfx_x - season_pfx_x)
            pfx_z_delta_str = _movement_delta_string(window_pfx_z - season_pfx_z)

        # ── Small sample ─────────────────────────────────────────
        small_sample = n_window < _MIN_PITCHES

        results.append(
            PitchTypeSummary(
                pitch_type=pt,
                pitch_name=pitch_name,
                season_usage_pct=season_usage_pct,
                window_usage_pct=window_usage_pct,
                usage_delta=usage_delta,
                season_p_plus=season_p_plus,
                window_p_plus=window_p_plus,
                p_plus_delta=p_plus_delta,
                season_s_plus=season_s_plus,
                window_s_plus=window_s_plus,
                s_plus_delta=s_plus_delta,
                season_l_plus=season_l_plus,
                window_l_plus=window_l_plus,
                l_plus_delta=l_plus_delta,
                season_velo=season_velo,
                window_velo=window_velo,
                velo_delta=velo_delta_str,
                season_pfx_x=season_pfx_x,
                window_pfx_x=window_pfx_x,
                pfx_x_delta=pfx_x_delta_str,
                season_pfx_z=season_pfx_z,
                window_pfx_z=window_pfx_z,
                pfx_z_delta=pfx_z_delta_str,
                n_pitches_season=n_season,
                n_pitches_window=n_window,
                small_sample=small_sample,
                cold_start=cold_start,
            )
        )

    # Sort by season usage descending
    results.sort(key=lambda x: x.season_usage_pct, reverse=True)
    return results


def compute_platoon_mix(data: PitcherData) -> PlatoonMix:
    """Compute platoon mix shift analysis with per-type per-side splits.

    For each pitch type and each platoon side (same/opposite), computes
    usage rates and P+ deltas. Handles missing combinations (e.g., a
    changeup only thrown to opposite-side batters).

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        PlatoonMix dataclass with list of PlatoonSplit entries.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    name_map = _build_name_map(data.statcast)

    # Add platoon_matchup column to statcast
    statcast_with_platoon = data.statcast.with_columns(
        pl.when(pl.col("stand") == pl.col("p_throws"))
        .then(pl.lit("same"))
        .otherwise(pl.lit("opposite"))
        .alias("platoon_matchup")
    )
    window_sc = statcast_with_platoon.filter(pl.col("game_date").is_in(window_dates))

    # Compute platoon baseline from season CSV
    platoon_baseline = _compute_platoon_baseline(data.agg_csvs["pitcher_type_platoon"])

    # Get pitch types ordered by usage
    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    splits: list[PlatoonSplit] = []

    for pt in pitch_types:
        for side in ("same", "opposite"):
            # ── Season usage: % of pitches to this side that are this type ──
            season_side = statcast_with_platoon.filter(pl.col("platoon_matchup") == side)
            season_side_total = len(season_side)
            season_side_type = season_side.filter(pl.col("pitch_type") == pt)
            n_season_side_type = len(season_side_type)

            if n_season_side_type == 0:
                # Pitch not thrown to this side at all
                splits.append(
                    PlatoonSplit(
                        pitch_type=pt,
                        pitch_name=name_map.get(pt, pt),
                        platoon_side=side,
                        season_usage_pct=0.0,
                        window_usage_pct=None,
                        usage_delta=f"Not thrown to {side}-side batters",
                        season_p_plus=None,
                        window_p_plus=None,
                        p_plus_delta=f"Not thrown to {side}-side batters",
                        available=False,
                    )
                )
                continue

            season_usage_pct = n_season_side_type / season_side_total * 100.0

            # ── Window usage ──
            window_side = window_sc.filter(pl.col("platoon_matchup") == side)
            window_side_total = len(window_side)
            window_side_type = window_side.filter(pl.col("pitch_type") == pt)
            n_window_side_type = len(window_side_type)

            if window_side_total > 0:
                window_usage_pct = n_window_side_type / window_side_total * 100.0
            else:
                window_usage_pct = None

            # ── Usage delta ──
            if cold_start:
                usage_delta = _COLD_START_STRING
            elif window_usage_pct is not None:
                usage_delta = _usage_delta_string(window_usage_pct - season_usage_pct)
            else:
                usage_delta = "No window data"

            # ── Season P+ from platoon baseline ──
            plat_row = platoon_baseline.filter(
                (pl.col("pitch_type") == pt) & (pl.col("platoon_matchup") == side)
            )
            season_p_plus: float | None = None
            if not plat_row.is_empty() and "P+" in plat_row.columns:
                season_p_plus = float(plat_row["P+"][0])

            # ── Window P+ from platoon appearance data ──
            window_plat_pplus = _weighted_window_metrics(
                data.agg_csvs["pitcher_type_platoon_appearance"],
                _PPLUS_METRICS,
                _window_date_type_filter(window_dates, pt) & (pl.col("platoon_matchup") == side),
            )
            window_p_plus = window_plat_pplus["P+"]

            # ── P+ delta ──
            if cold_start:
                p_plus_delta = _COLD_START_STRING
            elif season_p_plus is not None and window_p_plus is not None:
                p_plus_delta = _pplus_delta_string(window_p_plus - season_p_plus)
            else:
                p_plus_delta = "No window data"

            splits.append(
                PlatoonSplit(
                    pitch_type=pt,
                    pitch_name=name_map.get(pt, pt),
                    platoon_side=side,
                    season_usage_pct=season_usage_pct,
                    window_usage_pct=window_usage_pct,
                    usage_delta=usage_delta,
                    season_p_plus=season_p_plus,
                    window_p_plus=window_p_plus,
                    p_plus_delta=p_plus_delta,
                    available=True,
                )
            )

    return PlatoonMix(splits=splits, cold_start=cold_start)


def compute_first_pitch_weaponry(data: PitcherData) -> FirstPitchWeaponry:
    """Compute first-pitch strike weaponry analysis.

    Filters statcast to pitch_number == 1 (first pitch of each at-bat),
    computes per-type distribution for season vs window, and produces
    delta strings.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        FirstPitchWeaponry dataclass with entries ordered by window_pct
        descending.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    name_map = _build_name_map(data.statcast)

    # Filter to first pitches
    first_pitches = data.statcast.filter(pl.col("pitch_number") == 1)
    total_season = len(first_pitches)

    # Window first pitches
    fp_window = first_pitches.filter(pl.col("game_date").is_in(window_dates))
    total_window = len(fp_window)

    # Season counts by type
    season_counts = first_pitches["pitch_type"].value_counts().sort("pitch_type")

    # Window counts by type
    window_counts = fp_window["pitch_type"].value_counts().sort("pitch_type")
    window_count_map: dict[str, int] = {}
    for row in window_counts.iter_rows(named=True):
        window_count_map[row["pitch_type"]] = row["count"]

    entries: list[FirstPitchEntry] = []
    for row in season_counts.iter_rows(named=True):
        pt = row["pitch_type"]
        n_season = row["count"]
        season_pct = n_season / total_season * 100.0

        n_window = window_count_map.get(pt, 0)
        window_pct = n_window / total_window * 100.0 if total_window > 0 else 0.0

        delta = _COLD_START_STRING if cold_start else _usage_delta_string(window_pct - season_pct)

        entries.append(
            FirstPitchEntry(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                season_pct=season_pct,
                window_pct=window_pct,
                delta=delta,
                n_first_pitches_season=n_season,
                n_first_pitches_window=n_window,
            )
        )

    # Sort by window_pct descending
    entries.sort(key=lambda x: x.window_pct, reverse=True)

    return FirstPitchWeaponry(
        entries=entries,
        total_first_pitches_season=total_season,
        total_first_pitches_window=total_window,
        cold_start=cold_start,
    )


# ── Execution metrics helpers ────────────────────────────────────────


def _compute_ip(statcast: pl.DataFrame, game_pk: int) -> str:
    """Compute innings pitched for a single appearance as baseball notation.

    Counts outs generated by the pitcher's events in each inning. All
    innings except the last are assumed to be complete (3 outs). The last
    inning uses event-based out counting.

    Args:
        statcast: Full pitch-level Statcast DataFrame for the pitcher.
        game_pk: Unique game identifier.

    Returns:
        IP in baseball notation, e.g., '1.0', '0.2', '5.1'.
    """
    game = statcast.filter(pl.col("game_pk") == game_pk)
    innings = sorted(game["inning"].unique().to_list())

    if len(innings) == 0:
        return "0.0"

    n_full_innings = max(0, len(innings) - 1)

    # Count outs in the final inning from events
    final_inning = game.filter(pl.col("inning") == innings[-1])
    out_pitches = final_inning.filter(pl.col("events").is_in(list(_OUT_EVENTS)))
    outs_in_final = out_pitches.height
    # Double-out events count as 2 outs total (add 1 extra)
    double_outs = final_inning.filter(pl.col("events").is_in(list(_DOUBLE_OUT_EVENTS))).height
    outs_in_final += double_outs

    total_thirds = n_full_innings * 3 + outs_in_final
    whole = total_thirds // 3
    remainder = total_thirds % 3
    return f"{whole}.{remainder}"


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


def _window_date_type_filter(window_dates: list[Any], pitch_type: str) -> pl.Expr:
    """Build a standard filter for window dates + pitch type."""
    return (pl.col("game_date").is_in(window_dates)) & (pl.col("pitch_type") == pitch_type)


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
    full_pitcher_type_df = pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")
    if "game_date" in full_pitcher_type_df.columns:
        full_pitcher_type_df = full_pitcher_type_df.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))

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

    workload_entries: list[AppearanceWorkload] = []

    for i, row in enumerate(appearances.iter_rows(named=True)):
        game_pk = int(row["game_pk"])
        game_date = str(row["game_date"])
        role = str(row["role"])

        # Compute IP from statcast
        ip = _compute_ip(data.statcast, game_pk)

        # Pitch count from statcast (count rows per game_pk)
        pitch_count = data.statcast.filter(pl.col("game_pk") == game_pk).height

        workload_entries.append(
            AppearanceWorkload(
                game_pk=game_pk,
                game_date=game_date,
                role=role,
                ip=ip,
                pitch_count=pitch_count,
                rest_days=rest_days_list[i],
            )
        )

    return WorkloadContext(
        appearances=workload_entries,
        max_consecutive_days=max_consec,
        workload_concern=max_consec >= 3,
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
    rv_df = load_run_values()

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
