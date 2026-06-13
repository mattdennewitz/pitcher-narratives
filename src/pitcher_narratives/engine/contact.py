"""Contact quality: hard-hit rate over batted balls in the window vs season.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _COLD_START_STRING,
    _MIN_PITCHES,
    _get_window_game_dates,
    _is_cold_start,
    _usage_delta_string,
)


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


