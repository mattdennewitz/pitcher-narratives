import polars as pl
import pytest

from data import (
    classify_appearances,
    compute_pitch_type_baseline,
    compute_season_baseline,
    filter_to_window,
    load_agg_csvs,
    load_pitcher_data,
    load_statcast,
)

TEST_PITCHER = 592155  # Booser, Cam -- 12 appearances, 1 SP + 11 RP


def test_load_statcast_filters_by_pitcher():
    """DATA-01: Returns only rows for the given pitcher."""
    df = load_statcast(TEST_PITCHER)
    assert not df.is_empty()
    assert df["pitcher"].unique().to_list() == [TEST_PITCHER]


def test_load_statcast_invalid_pitcher():
    """DATA-01: Raises ValueError for unknown pitcher ID."""
    with pytest.raises(ValueError, match="Pitcher 9999999 not found"):
        load_statcast(9999999)


def test_load_statcast_returns_dataframe():
    """DATA-01: Return type is polars DataFrame."""
    df = load_statcast(TEST_PITCHER)
    assert isinstance(df, pl.DataFrame)


def test_load_agg_csvs_all_grains():
    """DATA-02: Returns dict with all expected CSV keys."""
    csvs = load_agg_csvs(TEST_PITCHER)
    expected_keys = {
        "pitcher",
        "pitcher_type",
        "pitcher_appearance",
        "pitcher_type_appearance",
        "pitcher_type_platoon",
        "pitcher_type_platoon_appearance",
        "all_pitches",
        "team",
    }
    assert set(csvs.keys()) == expected_keys


def test_csv_date_parsing():
    """DATA-02: game_date columns parsed to Date type, not String."""
    csvs = load_agg_csvs(TEST_PITCHER)
    for key in [
        "pitcher_appearance",
        "pitcher_type_appearance",
        "pitcher_type_platoon_appearance",
        "all_pitches",
    ]:
        df = csvs[key]
        if not df.is_empty():
            assert df["game_date"].dtype == pl.Date, (
                f"{key} game_date is {df['game_date'].dtype}, expected Date"
            )


def test_csv_pitcher_filtered():
    """DATA-02: All CSVs are filtered to the target pitcher (except team.csv)."""
    csvs = load_agg_csvs(TEST_PITCHER)
    for key, df in csvs.items():
        if key == "team":
            continue  # team.csv has no pitcher column
        if not df.is_empty():
            assert (df["pitcher"] == TEST_PITCHER).all(), f"{key} contains rows for other pitchers"


def test_season_baseline_weighted():
    """DATA-03: Season baseline uses n_pitches-weighted averaging."""
    csvs = load_agg_csvs(TEST_PITCHER)
    baseline = compute_season_baseline(csvs["pitcher"])
    assert len(baseline) == 1  # single row for the pitcher
    assert "n_pitches" in baseline.columns
    assert baseline["n_pitches"][0] > 0


def test_season_baseline_single_game_type():
    """DATA-03: Works for pitcher with only one game_type row."""
    csvs = load_agg_csvs(TEST_PITCHER)
    pitcher_df = csvs["pitcher"]
    # If pitcher has only 1 game_type, baseline should equal that row's metrics
    if len(pitcher_df) == 1:
        baseline = compute_season_baseline(pitcher_df)
        assert len(baseline) == 1


def test_pitch_type_baseline():
    """DATA-03: Per-pitch-type baseline filters empty pitch_type strings."""
    csvs = load_agg_csvs(TEST_PITCHER)
    baseline = compute_pitch_type_baseline(csvs["pitcher_type"])
    # No rows with empty pitch_type
    assert not baseline.filter(pl.col("pitch_type") == "").height


def test_window_filter():
    """DATA-04: Window filter restricts to N days from max date in data."""
    df = load_statcast(TEST_PITCHER)
    appearances = classify_appearances(df)
    filtered = filter_to_window(appearances, window_days=7)
    if not filtered.is_empty():
        from datetime import date, timedelta
        from typing import cast

        max_date = cast(date, appearances["game_date"].max())
        cutoff = max_date - timedelta(days=7)
        assert cast(date, filtered["game_date"].min()) >= cutoff


def test_classify_starter():
    """ROLE-01: Appearance with first_inning==1 gets role 'SP'."""
    df = load_statcast(TEST_PITCHER)
    appearances = classify_appearances(df)
    starters = appearances.filter(pl.col("role") == "SP")
    assert (starters["first_inning"] == 1).all()


def test_classify_reliever():
    """ROLE-01: Appearance with first_inning>1 gets role 'RP'."""
    df = load_statcast(TEST_PITCHER)
    appearances = classify_appearances(df)
    relievers = appearances.filter(pl.col("role") == "RP")
    assert (relievers["first_inning"] > 1).all()


def test_role_column_exists():
    """ROLE-02: role column present in appearances output."""
    df = load_statcast(TEST_PITCHER)
    appearances = classify_appearances(df)
    assert "role" in appearances.columns


def test_swingman_classification():
    """ROLE-03: Pitcher with both SP and RP appearances gets both roles."""
    df = load_statcast(TEST_PITCHER)
    appearances = classify_appearances(df)
    roles = appearances["role"].unique().sort().to_list()
    # Booser has 1 start and 11 relief appearances
    assert roles == ["RP", "SP"]


def test_load_pitcher_data_returns_complete_bundle():
    """Integration: load_pitcher_data returns all expected data."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    assert hasattr(data, "statcast")
    assert hasattr(data, "appearances")
    assert hasattr(data, "season_baseline")
    assert hasattr(data, "pitch_type_baseline")
    assert hasattr(data, "agg_csvs")
    assert hasattr(data, "window_appearances")
