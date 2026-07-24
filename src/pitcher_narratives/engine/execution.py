"""Execution metrics: CSW%, zone rate, chase rate, expected whiff/swing,
xRV100 percentile, and intermediate P/S-variant probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _CSW_DESCRIPTIONS,
    _INTERMEDIATE_COLS,
    _MIN_PITCHES,
    _SWING_DESCRIPTIONS,
    _XMETRICS,
    _ZONE_IN,
    _ZONE_OUT,
    _build_name_map,
    _frame_pitch_type_filter,
    _get_frame_rows,
    _get_season_rows,
    _weighted_window_metrics,
    frame_sufficiency,
)


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

    P and count-marginalized S are distinct producer outputs. Their difference
    is a diagnostic contrast, not the formal independently centered L variant.
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


def _compute_xrv100_percentile(
    pitcher_xrv100: float | None,
    pitch_type: str,
    pitcher_type_df: pl.DataFrame,
    min_pitches: int = 10,
) -> int | None:
    """Compute percentile rank of pitcher's xRV100 vs all MLB pitchers for a type.

    Restricts the league distribution to MLB level: minor-league (A/AAA)
    and WBC rows are excluded so percentiles are not inflated against
    weaker competition. Weight-averages xRV100_P per (pitcher, pitch_type)
    across game_types. Lower (more negative) xRV100 = better pitcher =
    higher percentile.

    Args:
        pitcher_xrv100: The pitcher's weighted window xRV100_P for this type.
        pitch_type: Pitch type code.
        pitcher_type_df: pitcher_type DataFrame for the league distribution
            (restricted to MLB level here).
        min_pitches: Minimum pitches threshold for inclusion.

    Returns:
        Percentile (0-100) or None if pitcher_xrv100 is None.
    """
    if pitcher_xrv100 is None:
        return None

    # MLB-only league distribution for this pitch type, above the sample floor
    type_data = pitcher_type_df.filter(pl.col("pitch_type") == pitch_type)
    if "level" in type_data.columns:
        type_data = type_data.filter(pl.col("level") == "MLB")
    type_data = type_data.filter(pl.col("n_pitches") >= min_pitches)

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
    cold_start = frame_sufficiency(data) != "sufficient"

    window_statcast = _get_frame_rows(data)

    name_map = _build_name_map(_get_season_rows(data))

    # Get pitch types from baseline sorted by n_pitches descending
    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    # Percentiles consume only an emitted, manifest-covered reference population.
    full_pitcher_type_df = data.aggregates.get("pitcher_type_reference", data.aggregates["pitcher_type"])

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
            _get_frame_rows(data, data.aggregates["pitcher_type_appearance"]),
            _XMETRICS,
            _frame_pitch_type_filter(pt),
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
    cold_start = frame_sufficiency(data) != "sufficient"
    name_map = _build_name_map(_get_season_rows(data))

    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    results: list[IntermediateProbabilities] = []

    for pt in pitch_types:
        # Window values from appearance grain
        metrics = _weighted_window_metrics(
            _get_frame_rows(data, data.aggregates["pitcher_type_appearance"]),
            _INTERMEDIATE_COLS,
            _frame_pitch_type_filter(pt),
        )

        # Season values from baseline
        bl_row = baseline.filter(pl.col("pitch_type") == pt)

        def _bl(col: str, _row: pl.DataFrame = bl_row) -> float | None:
            if _row.is_empty() or col not in _row.columns:
                return None
            val = _row[col][0]
            return None if val is None else float(val)

        n_pitches = int(metrics.get("n_pitches", 0))

        results.append(
            IntermediateProbabilities(
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
            )
        )

    results.sort(key=lambda x: x.n_pitches, reverse=True)
    return results
