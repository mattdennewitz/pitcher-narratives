"""Shared internal helpers and constants for the engine subpackage.

Private to the engine package. The concern modules (baselines, arsenal,
execution, workload, mechanics, contact, tto, attribution) import the
delta-string formatters, weighted-window helpers, name maps, and threshold
constants from here. Not part of the public engine API except where
__init__.py re-exports specific names for the test suite.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, cast

import polars as pl

from pitcher_narratives.data import PitcherData

_log = logging.getLogger(__name__)


def _float(val: Any) -> float:
    """Cast a Polars scalar to float, satisfying mypy."""
    return float(cast(float, val))
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

_FEET_TO_INCHES = 12.0
"""Raw Statcast pfx_x/pfx_z are in feet; all reported movement is inches."""

_MIN_PITCHES = 10
"""Minimum pitches for per-type analysis; below this flag small_sample=True."""

_THIN_APPEARANCES = 10
"""Below this many appearances the frame is too thin for a power comparison."""

_THIN_FRAME_STRING = "Underpowered comparison -- insufficient window sample"
"""Delta string used when the window is non-empty but underpowered."""

_EMPTY_FRAME_STRING = "No data for this frame"
"""Delta string used when the frame contains no data."""

_INSUFFICIENT_SAMPLE_STRING = "insufficient sample"
"""Delta string used when the window pitch count is below _MIN_PITCHES."""

FrameSufficiency = Literal["sufficient", "thin", "empty"]
"""Three-state classification of a frame's power to support a comparison."""

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


def _per_season_velo(statcast: pl.DataFrame) -> dict[int, float]:
    """Compute mean release_speed per season from statcast pitch-level data.

    Derives season from game_date year. Filters to non-null release_speed rows.

    Args:
        statcast: Pitch-level Statcast DataFrame with game_date and release_speed columns.

    Returns:
        Dict mapping season year (int) to mean velocity (float).
    """
    df = statcast.filter(pl.col("release_speed").is_not_null())
    if df.is_empty() or "game_date" not in df.columns:
        return {}
    agg = df.with_columns(
        pl.col("game_date").dt.year().alias("_season")
    ).group_by("_season").agg(
        pl.col("release_speed").mean().alias("mean_velo")
    )
    return {int(row["_season"]): float(row["mean_velo"]) for row in agg.iter_rows(named=True)}


def _pplus_delta_strings(
    sufficiency: FrameSufficiency,
    season_p: float,
    season_s: float,
    season_l: float,
    window_p: float | None,
    window_s: float | None,
    window_l: float | None,
) -> tuple[str, str, str]:
    """Compute P+/S+/L+ delta strings with frame-state and None handling."""
    if sufficiency == "empty":
        return _EMPTY_FRAME_STRING, _EMPTY_FRAME_STRING, _EMPTY_FRAME_STRING
    if sufficiency == "thin":
        return _THIN_FRAME_STRING, _THIN_FRAME_STRING, _THIN_FRAME_STRING
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


def _most_recent_row(appearances: pl.DataFrame) -> dict[str, Any]:
    """Return the most-recent appearance as a named dict, deterministically.

    Sorts by ``game_date`` then ``game_pk`` (both descending) so doubleheaders
    (two ``game_pk`` on one date) resolve to a single stable "most recent" pick.

    Args:
        appearances: Per-appearance DataFrame with ``game_date`` and ``game_pk``.

    Returns:
        Row 0 after the deterministic sort, as a column->value dict.
    """
    return (
        appearances.sort(
            ["game_date", "game_pk"], descending=True, nulls_last=True
        ).row(0, named=True)
    )


def frame_sufficiency(data: PitcherData) -> FrameSufficiency:
    """Classify a frame's power to support a season-vs-window comparison.

    Returns ``"empty"`` (no window appearances), ``"thin"`` (non-empty but
    underpowered: the window covers the whole season -- so there is no prior
    baseline to compare against -- or it holds fewer than ``_THIN_APPEARANCES``
    appearances), and ``"sufficient"`` otherwise. Replaces the previous
    day-window-shaped cold-start detector (design §15 G8).

    Args:
        data: PitcherData bundle.

    Returns:
        The frame's :data:`FrameSufficiency` classification.
    """
    n_window = len(data.window_appearances)
    n_total = len(data.appearances)
    if n_window == 0:
        return "empty"
    if n_window >= n_total or n_window < _THIN_APPEARANCES:
        return "thin"
    return "sufficient"


def _sufficiency_delta_string(sufficiency: FrameSufficiency, computed: str) -> str:
    """Return the frame-state string for a delta, or the computed string when sufficient."""
    if sufficiency == "empty":
        return _EMPTY_FRAME_STRING
    if sufficiency == "thin":
        return _THIN_FRAME_STRING
    return computed


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
def _window_date_type_filter(window_dates: list[Any], pitch_type: str) -> pl.Expr:
    """Build a standard filter for window dates + pitch type."""
    return (pl.col("game_date").is_in(window_dates)) & (pl.col("pitch_type") == pitch_type)
