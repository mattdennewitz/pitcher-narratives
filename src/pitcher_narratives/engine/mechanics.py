"""Release-point mechanics: per-pitch-type horizontal/vertical release
position and extension, with window-vs-season deltas.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _MIN_PITCHES,
    _build_name_map,
    _get_frame_rows,
    _get_season_rows,
    _sufficiency_delta_string,
    frame_sufficiency,
)

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
    sufficiency = frame_sufficiency(data)
    cold_start = sufficiency != "sufficient"
    name_map = _build_name_map(_get_season_rows(data))

    _release_cols = ["release_pos_x", "release_pos_z", "release_extension"]

    # Filter to rows with non-null release data
    valid = _get_season_rows(data).filter(
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
    window_valid = _get_frame_rows(data).filter(
        pl.col("release_pos_x").is_not_null()
        & pl.col("release_pos_z").is_not_null()
        & pl.col("release_extension").is_not_null()
    )
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

        x_delta = _sufficiency_delta_string(
            sufficiency, _release_delta_string(row["window_x"] - row["season_x"])
        )
        z_delta = _sufficiency_delta_string(
            sufficiency, _release_delta_string(row["window_z"] - row["season_z"])
        )
        ext_delta = _sufficiency_delta_string(
            sufficiency, _extension_delta_string(row["window_ext"] - row["season_ext"])
        )

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
