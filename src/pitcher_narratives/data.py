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
    "AGGS_DIR",
    "RV_DF_PATH",
    "PitcherData",
    "classify_appearances",
    "compute_pitch_type_baseline",
    "compute_season_baseline",
    "filter_game_type",
    "filter_to_window",
    "load_agg_csvs",
    "load_all_statcast",
    "load_csv",
    "load_full_agg",
    "load_pitcher_data",
    "load_run_values",
    "load_statcast",
]

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent
_data_dir_override = os.environ.get("PITCHER_NARRATIVES_DATA_DIR")
DATA_DIR = Path(_data_dir_override) if _data_dir_override else _DEFAULT_DATA_DIR
_YEARS: list[int] = [2025, 2026]
PARQUET_PATH = DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"
AGGS_DIR = DATA_DIR / "aggs"
RV_DF_PATH = AGGS_DIR / "RV_df.csv"

# CSV grain names -- filenames derived as f"{year}-{grain}.csv"
_SEASON_GRAINS = ("pitcher", "pitcher_type", "pitcher_type_platoon", "team")
_APPEARANCE_GRAINS = (
    "pitcher_appearance",
    "pitcher_type_appearance",
    "pitcher_type_platoon_appearance",
    "all_pitches",
)

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

_ALLOWED_GAME_TYPES = frozenset({"R", "F", "D", "L", "W"})


@dataclass
class PitcherData:
    """Bundle of all loaded and processed data for a pitcher.

    Baseline fields:
        season_baseline: Current (max) season pitcher-level baselines.
        pitch_type_baseline: Current (max) season per-pitch-type baselines.
        prior_season_baseline: Previous season pitcher-level baselines.
            Empty DataFrame (same schema, zero rows) when only one season exists.
        prior_pitch_type_baseline: Previous season per-pitch-type baselines.
            Empty DataFrame (same schema, zero rows) when only one season exists.
    """

    statcast: pl.DataFrame
    appearances: pl.DataFrame
    window_appearances: pl.DataFrame
    season_baseline: pl.DataFrame
    pitch_type_baseline: pl.DataFrame
    prior_season_baseline: pl.DataFrame
    prior_pitch_type_baseline: pl.DataFrame
    agg_csvs: dict[str, pl.DataFrame]
    pitcher_id: int
    pitcher_name: str
    throws: str


def filter_game_type(df: pl.DataFrame) -> pl.DataFrame:
    """Filter DataFrame to regular-season and postseason game types.

    Retains rows where game_type is one of: R (Regular Season),
    F (Wild Card), D (Division Series), L (League Championship),
    W (World Series). Removes spring training, exhibition, and
    other non-competitive game types.

    If the DataFrame has no game_type column, returns it unchanged.

    Args:
        df: Input DataFrame, possibly containing a game_type column.

    Returns:
        Filtered DataFrame with only allowed game type rows.
    """
    if "game_type" not in df.columns:
        return df
    return df.filter(pl.col("game_type").is_in(list(_ALLOWED_GAME_TYPES)))


def load_csv(filename: str, pitcher_id: int | None) -> pl.DataFrame:
    """Load a CSV agg file, filter game types, parse dates, and optionally filter to pitcher.

    Args:
        filename: CSV filename within the aggs directory.
        pitcher_id: If provided and 'pitcher' column exists, filter to this ID.
            Pass None for files without a pitcher column (e.g., team.csv).

    Returns:
        Filtered polars DataFrame with game_date parsed to Date type if present.
    """
    path = AGGS_DIR / filename
    df = pl.read_csv(path)
    df = filter_game_type(df)
    if "game_date" in df.columns:
        df = df.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))
    if pitcher_id is not None and "pitcher" in df.columns:
        df = df.filter(pl.col("pitcher") == pitcher_id)
    return df


def load_statcast(pitcher_id: int) -> pl.DataFrame:
    """Load Statcast pitch-level data filtered to a single pitcher.

    Reads parquet files for all configured years in ``_YEARS``, filters
    each to allowed game types (excluding spring training and exhibition),
    filters to the given pitcher, and concatenates results. Missing year
    files are skipped gracefully.

    Args:
        pitcher_id: MLB pitcher ID to filter on.

    Returns:
        Polars DataFrame containing only regular-season rows for the given pitcher
        across all available years.

    Raises:
        ValueError: If no rows found for the given pitcher ID after filtering.
    """
    frames: list[pl.DataFrame] = []
    for year in _YEARS:
        path = DATA_DIR / f"statcast_{year}.parquet"
        if not path.exists():
            continue
        df = pl.read_parquet(path)
        df = filter_game_type(df)
        filtered = df.filter(pl.col("pitcher") == pitcher_id)
        if not filtered.is_empty():
            frames.append(filtered)
    if not frames:
        raise ValueError(f"Pitcher {pitcher_id} not found")
    return pl.concat(frames, how="diagonal_relaxed")


def load_run_values() -> pl.DataFrame:
    """Load the outcome-level run values lookup table.

    Returns:
        DataFrame with columns: balls, strikes, model_classes, delta_run_exp.
        156 rows: 12 counts x 13 outcomes.

    Raises:
        FileNotFoundError: If RV_df.csv is missing from the aggs directory.
    """
    return pl.read_csv(RV_DF_PATH)


def load_agg_csvs(pitcher_id: int) -> dict[str, pl.DataFrame]:
    """Load all 8 Pitching+ CSV aggregation files filtered to a pitcher.

    Reads year-prefixed CSV files for all configured years in ``_YEARS``
    and concatenates per grain. Missing year files are skipped gracefully.

    Args:
        pitcher_id: MLB pitcher ID to filter on.

    Returns:
        Dict keyed by logical name (e.g., 'pitcher', 'pitcher_type',
        'pitcher_appearance') with filtered polars DataFrames as values.
        The 'team' key contains unfiltered team-level data.
    """
    all_grains = [*_SEASON_GRAINS, *_APPEARANCE_GRAINS]
    result: dict[str, pl.DataFrame] = {}
    for grain in all_grains:
        frames: list[pl.DataFrame] = []
        for year in _YEARS:
            filename = f"{year}-{grain}.csv"
            path = AGGS_DIR / filename
            if not path.exists():
                continue
            pid = None if grain == "team" else pitcher_id
            frames.append(load_csv(filename, pid))
        if frames:
            result[grain] = pl.concat(frames, how="diagonal_relaxed")
        else:
            result[grain] = pl.DataFrame()
    return result


def load_all_statcast(columns: list[str] | None = None) -> pl.DataFrame:
    """Load Statcast pitch-level data for ALL pitchers across all years.

    Reads parquet files for all configured years in ``_YEARS``, filters
    each to allowed game types (excluding spring training and exhibition),
    and concatenates results. Missing year files are skipped gracefully.

    Unlike ``load_statcast()``, this does NOT filter by pitcher ID --
    it returns league-wide data suitable for baselines and percentile
    computation.

    Args:
        columns: Optional list of column names to read. When provided,
            only these columns are loaded from the parquet files,
            reducing memory usage for large datasets.

    Returns:
        Polars DataFrame containing regular-season rows for all pitchers
        across all available years.  Returns an empty DataFrame if no
        year files exist on disk.
    """
    frames: list[pl.DataFrame] = []
    for year in _YEARS:
        path = DATA_DIR / f"statcast_{year}.parquet"
        if not path.exists():
            continue
        read_cols = columns
        if read_cols is not None and "game_type" not in read_cols:
            read_cols = [*read_cols, "game_type"]
        if read_cols is not None:
            df = pl.read_parquet(path, columns=read_cols)
        else:
            df = pl.read_parquet(path)
        df = filter_game_type(df)
        if columns is not None and "game_type" not in columns:
            df = df.drop("game_type")
        if not df.is_empty():
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def load_full_agg(grain: str) -> pl.DataFrame:
    """Load a Pitching+ CSV aggregation for ALL pitchers across all years.

    Reads year-prefixed CSV files for all configured years in ``_YEARS``
    and concatenates results. Each file is loaded via ``load_csv()`` with
    ``pitcher_id=None`` so game-type filtering and date parsing are applied
    but no pitcher filter. Missing year files are skipped gracefully.

    Unlike ``load_agg_csvs()``, this loads a single grain rather than
    all 8 grains, and does NOT filter by pitcher ID.

    Args:
        grain: CSV grain name (e.g., 'pitcher_type', 'pitcher_appearance').

    Returns:
        Polars DataFrame containing all rows for the given grain across
        all available years.  Returns an empty DataFrame if no year
        files exist on disk.
    """
    frames: list[pl.DataFrame] = []
    for year in _YEARS:
        filename = f"{year}-{grain}.csv"
        path = AGGS_DIR / filename
        if not path.exists():
            continue
        df = load_csv(filename, None)
        if not df.is_empty():
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


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
    """Compute n_pitches-weighted per-season baseline for a pitcher.

    Data is already filtered to regular-season and postseason game types
    by load_csv(). Combines any remaining game_type rows into a single
    row per pitcher per season using pitch-count weighting.

    Args:
        pitcher_df: DataFrame from pitcher.csv filtered to one pitcher.

    Returns:
        DataFrame with one row per pitcher per season with weighted average
        metric values.
    """
    metric_cols = [c for c in pitcher_df.columns if c not in _ID_COLS]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return pitcher_df.group_by(["pitcher", "season"]).agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted_exprs,
    )


def compute_pitch_type_baseline(pitcher_type_df: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted baseline per pitch type per season.

    Filters out empty pitch_type strings and combines game_type rows
    using pitch-count weighting. Includes ``usage_pct`` -- the percentage
    of total pitches thrown with each pitch type within a season.

    Args:
        pitcher_type_df: DataFrame from pitcher_type.csv (one or many pitchers).

    Returns:
        DataFrame with one row per pitcher/season/pitch_type and weighted
        average metrics.
    """
    df = pitcher_type_df.filter(pl.col("pitch_type") != "")
    id_cols = _ID_COLS | {"pitch_type"}
    metric_cols = [c for c in df.columns if c not in id_cols]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    result = df.group_by(["pitcher", "season", "pitch_type"]).agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted_exprs,
    )
    pitcher_totals = df.group_by(["pitcher", "season"]).agg(
        pl.col("n_pitches").sum().alias("total_pitches"),
    )
    return result.join(pitcher_totals, on=["pitcher", "season"]).with_columns(
        (pl.col("n_pitches") / pl.col("total_pitches") * 100).alias("usage_pct"),
    ).drop("total_pitches")


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
    season_baseline_all = compute_season_baseline(agg_csvs["pitcher"])
    pitch_type_baseline_all = compute_pitch_type_baseline(agg_csvs["pitcher_type"])

    # Filter baselines to most recent season for engine consumption
    if "season" in season_baseline_all.columns and not season_baseline_all.is_empty():
        max_season = season_baseline_all["season"].max()
        season_baseline = season_baseline_all.filter(pl.col("season") == max_season)
    else:
        season_baseline = season_baseline_all

    if "season" in pitch_type_baseline_all.columns and not pitch_type_baseline_all.is_empty():
        max_season = pitch_type_baseline_all["season"].max()
        pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") == max_season)
    else:
        pitch_type_baseline = pitch_type_baseline_all
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
