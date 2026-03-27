"""Data loading pipeline for pitcher narratives.

Loads Statcast parquet and Pitching+ CSV aggregations, classifies
appearances as start or relief, computes season baselines, and
filters to configurable lookback windows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import polars as pl

__all__ = [
    "PitcherData",
    "classify_appearances",
    "compute_pitch_type_baseline",
    "compute_season_baseline",
    "filter_to_window",
    "load_agg_csvs",
    "load_pitcher_data",
    "load_statcast",
]

DATA_DIR = Path(os.environ.get("PITCHER_NARRATIVES_DATA_DIR", Path(__file__).resolve().parent.parent.parent))
PARQUET_PATH = DATA_DIR / "statcast_2026.parquet"
AGGS_DIR = DATA_DIR / "aggs"

# CSV filenames organized by grain
_SEASON_CSVS = {
    "pitcher": "2026-pitcher.csv",
    "pitcher_type": "2026-pitcher_type.csv",
    "pitcher_type_platoon": "2026-pitcher_type_platoon.csv",
    "team": "2026-team.csv",
}
_APPEARANCE_CSVS = {
    "pitcher_appearance": "2026-pitcher_appearance.csv",
    "pitcher_type_appearance": "2026-pitcher_type_appearance.csv",
    "pitcher_type_platoon_appearance": "2026-pitcher_type_platoon_appearance.csv",
    "all_pitches": "2026-all_pitches.csv",
}

# Columns that are identifiers, not metrics (used in baseline computation)
_ID_COLS = frozenset(
    {
        "season",
        "level",
        "game_type",
        "pitcher",
        "player_name",
        "p_throws",
        "team_code",
        "n_pitches",
    }
)


@dataclass
class PitcherData:
    """Bundle of all loaded and processed data for a pitcher."""

    statcast: pl.DataFrame
    appearances: pl.DataFrame
    window_appearances: pl.DataFrame
    season_baseline: pl.DataFrame
    pitch_type_baseline: pl.DataFrame
    agg_csvs: dict[str, pl.DataFrame]
    pitcher_id: int
    pitcher_name: str
    throws: str


def _load_csv_with_dates(filename: str, pitcher_id: int | None) -> pl.DataFrame:
    """Load a CSV agg file, parse dates, and optionally filter to pitcher.

    Args:
        filename: CSV filename within the aggs directory.
        pitcher_id: If provided and 'pitcher' column exists, filter to this ID.
            Pass None for files without a pitcher column (e.g., team.csv).

    Returns:
        Filtered polars DataFrame with game_date parsed to Date type if present.
    """
    path = AGGS_DIR / filename
    df = pl.read_csv(path)
    if "game_date" in df.columns:
        df = df.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))
    if pitcher_id is not None and "pitcher" in df.columns:
        df = df.filter(pl.col("pitcher") == pitcher_id)
    return df


def load_statcast(pitcher_id: int) -> pl.DataFrame:
    """Load Statcast pitch-level data filtered to a single pitcher.

    Args:
        pitcher_id: MLB pitcher ID to filter on.

    Returns:
        Polars DataFrame containing only rows for the given pitcher.

    Raises:
        ValueError: If no rows found for the given pitcher ID.
    """
    df = pl.read_parquet(PARQUET_PATH)
    result = df.filter(pl.col("pitcher") == pitcher_id)
    if result.is_empty():
        raise ValueError(f"Pitcher {pitcher_id} not found")
    return result


def load_agg_csvs(pitcher_id: int) -> dict[str, pl.DataFrame]:
    """Load all 8 Pitching+ CSV aggregation files filtered to a pitcher.

    Args:
        pitcher_id: MLB pitcher ID to filter on.

    Returns:
        Dict keyed by logical name (e.g., 'pitcher', 'pitcher_type',
        'pitcher_appearance') with filtered polars DataFrames as values.
        The 'team' key contains unfiltered team-level data.
    """
    all_csvs = {**_SEASON_CSVS, **_APPEARANCE_CSVS}
    result: dict[str, pl.DataFrame] = {}
    for key, filename in all_csvs.items():
        pid = None if key == "team" else pitcher_id
        result[key] = _load_csv_with_dates(filename, pid)
    return result


def classify_appearances(statcast: pl.DataFrame) -> pl.DataFrame:
    """Classify each appearance as SP or RP based on first inning pitched.

    Groups Statcast pitch-level data by game, computes per-appearance
    aggregates, and assigns 'SP' (first_inning == 1) or 'RP' (first_inning > 1).

    Args:
        statcast: Pitch-level Statcast DataFrame for a single pitcher.

    Returns:
        Appearance-level DataFrame with columns: game_pk, game_date,
        first_inning, last_inning, n_pitches, player_name, role.
        Sorted by game_date ascending.
    """
    return (
        statcast.group_by(["game_pk", "game_date"])
        .agg(
            pl.col("inning").min().alias("first_inning"),
            pl.col("inning").max().alias("last_inning"),
            pl.len().alias("n_pitches"),
            pl.col("player_name").first(),
        )
        .with_columns(
            pl.when(pl.col("first_inning") == 1).then(pl.lit("SP")).otherwise(pl.lit("RP")).alias("role")
        )
        .sort("game_date")
    )


def compute_season_baseline(pitcher_df: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted season baseline across all game types.

    Combines game_type rows (S/C/R) into a single row per pitcher using
    pitch-count weighting for mathematically correct averaging.

    Args:
        pitcher_df: DataFrame from pitcher.csv filtered to one pitcher.

    Returns:
        Single-row DataFrame with weighted average metric values.
    """
    metric_cols = [c for c in pitcher_df.columns if c not in _ID_COLS]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return pitcher_df.group_by("pitcher").agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted_exprs,
    )


def compute_pitch_type_baseline(pitcher_type_df: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted baseline per pitch type across game types.

    Filters out empty pitch_type strings and combines game_type rows
    using pitch-count weighting.

    Args:
        pitcher_type_df: DataFrame from pitcher_type.csv filtered to one pitcher.

    Returns:
        DataFrame with one row per pitch type and weighted average metrics.
    """
    df = pitcher_type_df.filter(pl.col("pitch_type") != "")
    id_cols = _ID_COLS | {"pitch_type"}
    metric_cols = [c for c in df.columns if c not in id_cols]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return df.group_by(["pitcher", "pitch_type"]).agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted_exprs,
    )


def filter_to_window(df: pl.DataFrame, window_days: int) -> pl.DataFrame:
    """Filter DataFrame to rows within a lookback window from the max date.

    Uses the maximum date in the data as the reference point, not the
    current date, since data files are static.

    Args:
        df: DataFrame with a game_date column.
        window_days: Number of days to look back from the max date.

    Returns:
        Filtered DataFrame containing only rows within the window.
    """
    max_date_val = df["game_date"].max()
    if max_date_val is None:
        return df.clear()
    max_date = cast(date, max_date_val)
    cutoff = max_date - timedelta(days=window_days)
    return df.filter(pl.col("game_date") >= cutoff)


def load_pitcher_data(pitcher_id: int, window_days: int = 30) -> PitcherData:
    """Load and process all data for a pitcher.

    Orchestrates all loaders: reads Statcast parquet, loads CSV aggregations,
    classifies appearances, computes baselines, and filters to the lookback
    window.

    Args:
        pitcher_id: MLB pitcher ID.
        window_days: Lookback window in days (default 30).

    Returns:
        PitcherData bundle with all loaded and processed DataFrames.

    Raises:
        ValueError: If pitcher ID is not found in the Statcast data.
    """
    statcast = load_statcast(pitcher_id)
    agg_csvs = load_agg_csvs(pitcher_id)
    appearances = classify_appearances(statcast)
    window_appearances = filter_to_window(appearances, window_days)
    season_baseline = compute_season_baseline(agg_csvs["pitcher"])
    pitch_type_baseline = compute_pitch_type_baseline(agg_csvs["pitcher_type"])
    pitcher_name = str(statcast["player_name"][0])
    throws = str(statcast["p_throws"][0])

    return PitcherData(
        statcast=statcast,
        appearances=appearances,
        window_appearances=window_appearances,
        season_baseline=season_baseline,
        pitch_type_baseline=pitch_type_baseline,
        agg_csvs=agg_csvs,
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        throws=throws,
    )
