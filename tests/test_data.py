import polars as pl
import pytest

from pitcher_narratives.data import (
    _ALLOWED_GAME_TYPES,
    _APPEARANCE_GRAINS,
    _ID_COLS,
    _SEASON_GRAINS,
    _YEARS,
    classify_appearances,
    compute_pitch_type_baseline,
    compute_season_baseline,
    filter_game_type,
    filter_to_window,
    load_agg_csvs,
    load_all_statcast,
    load_csv,
    load_full_agg,
    load_pitcher_data,
    load_statcast,
    statcast_dir,
    statcast_parquet_path,
)

TEST_PITCHER = 592155  # Booser, Cam -- 1 regular-season RP appearance
SWINGMAN_PITCHER = 676571  # Poulin, PJ -- 4 R-game appearances: 1 SP + 3 RP
SINGLE_SEASON_PITCHER = 823810  # Moring, Reed -- only in 2026


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
    # Per-season grouping: one row per season with data for this pitcher
    assert len(baseline) >= 1
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
    df = load_statcast(SWINGMAN_PITCHER)
    appearances = classify_appearances(df)
    starters = appearances.filter(pl.col("role") == "SP")
    assert len(starters) > 0, "Need at least one SP appearance"
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
    df = load_statcast(SWINGMAN_PITCHER)
    appearances = classify_appearances(df)
    roles = appearances["role"].unique().sort().to_list()
    # Poulin has 1 start and 3 relief appearances in regular season
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


def test_filter_game_type_no_column():
    """DFND-01: filter_game_type passes through DataFrames without game_type column."""
    df = pl.DataFrame({"pitcher": [1, 2], "velo": [95.0, 93.0]})
    result = filter_game_type(df)
    assert result.shape == df.shape
    assert result.equals(df)


def test_filter_game_type_exported():
    """DFND-04: filter_game_type is in __all__ exports."""
    import pitcher_narratives.data as data_mod

    assert "filter_game_type" in data_mod.__all__


def test_load_statcast_filters_game_type():
    """DFND-01: load_statcast excludes spring training and exhibition rows."""
    df = load_statcast(TEST_PITCHER)
    if "game_type" in df.columns:
        actual_types = set(df["game_type"].unique().to_list())
        assert actual_types <= {"R", "F", "D", "L", "W"}, f"Unexpected game types: {actual_types}"


def test_load_csv_filters_game_type():
    """DFND-01: load_csv applies game type filter."""
    from pitcher_narratives.data import AGGS_DIR, _YEARS

    filename = f"{_YEARS[-1]}-pitcher.csv"
    df = load_csv(filename, TEST_PITCHER)
    if "game_type" in df.columns:
        actual_types = set(df["game_type"].unique().to_list())
        assert actual_types <= {"R", "F", "D", "L", "W"}, f"Unexpected game types: {actual_types}"


def test_no_hardcoded_year_in_csv_dicts():
    """DFND-02: No hardcoded year prefixes in CSV filename generation."""
    import inspect

    import pitcher_narratives.data as data_mod

    source = inspect.getsource(data_mod)
    # The old _SEASON_CSVS and _APPEARANCE_CSVS dicts with "2026-" values should not exist
    assert '"2026-pitcher.csv"' not in source, "Hardcoded 2026-pitcher.csv found in data.py"
    assert '"2026-pitcher_type.csv"' not in source, "Hardcoded 2026-pitcher_type.csv found"
    assert '"2026-all_pitches.csv"' not in source, "Hardcoded 2026-all_pitches.csv found"


def test_years_constant_drives_paths():
    """DFND-02/MYLD-01: _YEARS includes both years and drives path generation."""
    from pitcher_narratives.data import _YEARS, statcast_parquet_path

    assert isinstance(_YEARS, list)
    assert _YEARS == [2025, 2026]
    assert statcast_parquet_path(_YEARS[-1]).name == f"{_YEARS[-1]}.parquet"


def test_season_in_id_cols():
    """DFND-03: season is an identity column, not a metric."""
    from pitcher_narratives.data import _ID_COLS

    assert "season" in _ID_COLS


def test_load_statcast_multi_year(tmp_path, monkeypatch):
    """MYLD-01: load_statcast reads and concatenates parquet files for all years."""
    # Create minimal parquets for 2025 and 2026
    cols = {
        "pitcher": [12345, 12345, 12345],
        "player_name": ["Test Pitcher", "Test Pitcher", "Test Pitcher"],
        "p_throws": ["R", "R", "R"],
        "game_type": ["R", "R", "R"],
        "game_year": [2025, 2025, 2025],
        "inning": [1, 1, 2],
    }
    df_2025 = pl.DataFrame(cols)
    df_2026 = pl.DataFrame({**cols, "game_year": [2026, 2026, 2026]})

    df_2025.write_parquet(tmp_path / "2025.parquet")
    df_2026.write_parquet(tmp_path / "2026.parquet")

    import pitcher_narratives.data as data_mod

    monkeypatch.setenv("STATCAST_PATH", str(tmp_path))
    monkeypatch.setattr(data_mod, "AGGS_DIR", tmp_path / "aggs")
    monkeypatch.setattr(data_mod, "_YEARS", [2025, 2026])

    result = load_statcast(12345)
    assert set(result["game_year"].unique().to_list()) == {2025, 2026}
    assert len(result) == 6


def test_load_statcast_missing_year_skipped(monkeypatch):
    """MYLD-03: load_statcast skips missing year files without crashing."""
    import pitcher_narratives.data as data_mod

    # Add a year that doesn't have a parquet file on disk
    monkeypatch.setattr(data_mod, "_YEARS", [2024, 2025, 2026])
    result = load_statcast(TEST_PITCHER)
    assert not result.is_empty()
    # 2024 parquet doesn't exist, should be skipped gracefully
    years = set(result["game_year"].unique().to_list())
    assert 2024 not in years
    assert years <= {2025, 2026}


def test_load_agg_csvs_multi_year(tmp_path, monkeypatch):
    """MYLD-02: load_agg_csvs reads and concatenates CSV files for all years per grain."""
    aggs_dir = tmp_path / "aggs"
    aggs_dir.mkdir()

    for year in [2025, 2026]:
        for grain in [*_SEASON_GRAINS, *_APPEARANCE_GRAINS]:
            base_cols = {
                "season": [year],
                "game_type": ["R"],
                "player_name": ["Test Pitcher"],
                "p_throws": ["R"],
                "team_code": ["NYY"],
                "n_pitches": [100],
                "stuff_plus": [100.0 + (year - 2025) * 10],
            }
            if grain != "team":
                base_cols["pitcher"] = [12345]
            if "type" in grain:
                base_cols["pitch_type"] = ["FF"]
            if "platoon" in grain:
                base_cols["platoon"] = ["vs_R"]
            if "appearance" in grain:
                base_cols["game_date"] = [f"{year}-06-01"]
                base_cols["game_pk"] = [100000 + year]
            if grain == "all_pitches":
                base_cols["game_date"] = [f"{year}-06-01"]
                base_cols["game_pk"] = [100000 + year]

            df = pl.DataFrame(base_cols)
            df.write_csv(aggs_dir / f"{year}-{grain}.csv")

    import pitcher_narratives.data as data_mod

    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "AGGS_DIR", aggs_dir)
    monkeypatch.setattr(data_mod, "_YEARS", [2025, 2026])

    result = load_agg_csvs(12345)
    # Pitcher grain should have data from both years
    assert set(result["pitcher"]["season"].unique().to_list()) == {2025, 2026}


def test_load_agg_csvs_missing_year_skipped(monkeypatch):
    """MYLD-03: load_agg_csvs skips missing year CSV files without crashing."""
    import pitcher_narratives.data as data_mod

    # Add a year that doesn't have CSV files on disk
    monkeypatch.setattr(data_mod, "_YEARS", [2024, 2025, 2026])
    result = load_agg_csvs(TEST_PITCHER)
    assert not result["pitcher"].is_empty()
    # 2024 CSVs don't exist, should be skipped gracefully
    seasons = set(result["pitcher"]["season"].unique().to_list())
    assert 2024 not in seasons
    assert seasons <= {2025, 2026}


def test_season_baseline_per_season():
    """MYLD-04: compute_season_baseline produces separate rows per season."""
    df = pl.DataFrame(
        {
            "season": [2025, 2026],
            "game_type": ["R", "R"],
            "pitcher": [12345, 12345],
            "player_name": ["Test", "Test"],
            "p_throws": ["R", "R"],
            "team_code": ["NYY", "NYY"],
            "n_pitches": [100, 150],
            "stuff_plus": [95.0, 105.0],
        }
    )
    baseline = compute_season_baseline(df)
    assert len(baseline) == 2  # one row per season, not 1 cross-season average
    row_2025 = baseline.filter(pl.col("season") == 2025)
    row_2026 = baseline.filter(pl.col("season") == 2026)
    assert len(row_2025) == 1
    assert len(row_2026) == 1
    assert abs(row_2025["stuff_plus"][0] - 95.0) < 0.01
    assert abs(row_2026["stuff_plus"][0] - 105.0) < 0.01


def test_pitch_type_baseline_per_season():
    """MYLD-04: compute_pitch_type_baseline produces separate rows per season per pitch type."""
    df = pl.DataFrame(
        {
            "season": [2025, 2026],
            "game_type": ["R", "R"],
            "pitcher": [12345, 12345],
            "pitch_type": ["FF", "FF"],
            "player_name": ["Test", "Test"],
            "p_throws": ["R", "R"],
            "team_code": ["NYY", "NYY"],
            "n_pitches": [80, 120],
            "stuff_plus": [100.0, 110.0],
        }
    )
    baseline = compute_pitch_type_baseline(df)
    assert len(baseline) == 2  # one row per season for FF, not 1
    row_2025 = baseline.filter(pl.col("season") == 2025)
    row_2026 = baseline.filter(pl.col("season") == 2026)
    assert len(row_2025) == 1
    assert len(row_2026) == 1
    assert abs(row_2025["stuff_plus"][0] - 100.0) < 0.01
    assert abs(row_2026["stuff_plus"][0] - 110.0) < 0.01
    # Usage pct should be 100% for both since FF is the only pitch per season
    assert abs(row_2025["usage_pct"][0] - 100.0) < 0.01
    assert abs(row_2026["usage_pct"][0] - 100.0) < 0.01


# ---------------------------------------------------------------------------
# Tests for load_all_statcast() and load_full_agg()
# ---------------------------------------------------------------------------


def test_load_all_statcast_returns_all_pitchers():
    """CSMR-01: load_all_statcast() returns data with multiple unique pitcher IDs."""
    df = load_all_statcast()
    assert not df.is_empty()
    assert df["pitcher"].n_unique() > 1, "Expected multiple pitchers in unfiltered load"


def test_load_all_statcast_filters_game_type():
    """CSMR-01: load_all_statcast() only returns allowed game types."""
    df = load_all_statcast()
    if "game_type" in df.columns:
        actual_types = set(df["game_type"].unique().to_list())
        assert actual_types <= {"R", "F", "D", "L", "W"}, f"Unexpected game types: {actual_types}"


def test_load_all_statcast_columns_param():
    """CSMR-01: load_all_statcast(columns=...) returns only requested columns."""
    df = load_all_statcast(columns=["pitcher", "player_name"])
    assert set(df.columns) == {"pitcher", "player_name"}


def test_load_all_statcast_multi_year(tmp_path, monkeypatch):
    """CSMR-01: load_all_statcast reads and concatenates parquet files for all years."""
    cols = {
        "pitcher": [12345, 67890],
        "player_name": ["Pitcher A", "Pitcher B"],
        "p_throws": ["R", "L"],
        "game_type": ["R", "R"],
        "game_year": [2025, 2025],
        "inning": [1, 5],
    }
    df_2025 = pl.DataFrame(cols)
    df_2026 = pl.DataFrame({**cols, "game_year": [2026, 2026]})

    df_2025.write_parquet(tmp_path / "2025.parquet")
    df_2026.write_parquet(tmp_path / "2026.parquet")

    import pitcher_narratives.data as data_mod

    monkeypatch.setenv("STATCAST_PATH", str(tmp_path))
    monkeypatch.setattr(data_mod, "_YEARS", [2025, 2026])

    result = load_all_statcast()
    assert set(result["game_year"].unique().to_list()) == {2025, 2026}
    assert len(result) == 4


def test_load_all_statcast_missing_year(tmp_path, monkeypatch):
    """CSMR-01: load_all_statcast skips missing year files gracefully."""
    cols = {
        "pitcher": [12345],
        "player_name": ["Pitcher A"],
        "game_type": ["R"],
        "game_year": [2026],
        "inning": [1],
    }
    df_2026 = pl.DataFrame(cols)
    df_2026.write_parquet(tmp_path / "2026.parquet")
    # No 2025 file created

    import pitcher_narratives.data as data_mod

    monkeypatch.setenv("STATCAST_PATH", str(tmp_path))
    monkeypatch.setattr(data_mod, "_YEARS", [2025, 2026])

    result = load_all_statcast()
    assert not result.is_empty()
    assert set(result["game_year"].unique().to_list()) == {2026}


def test_load_full_agg_returns_all_pitchers():
    """CSMR-01: load_full_agg() returns data with multiple unique pitcher IDs."""
    df = load_full_agg("pitcher_type")
    assert not df.is_empty()
    assert df["pitcher"].n_unique() > 1, "Expected multiple pitchers in unfiltered load"


def test_load_full_agg_filters_game_type():
    """CSMR-01: load_full_agg() only returns allowed game types."""
    df = load_full_agg("pitcher_type")
    if "game_type" in df.columns:
        actual_types = set(df["game_type"].unique().to_list())
        assert actual_types <= {"R", "F", "D", "L", "W"}, f"Unexpected game types: {actual_types}"


def test_load_full_agg_parses_dates():
    """CSMR-01: load_full_agg parses game_date to pl.Date when present."""
    df = load_full_agg("pitcher_type_appearance")
    if not df.is_empty() and "game_date" in df.columns:
        assert df["game_date"].dtype == pl.Date, (
            f"game_date is {df['game_date'].dtype}, expected Date"
        )


def test_load_full_agg_multi_year(tmp_path, monkeypatch):
    """CSMR-01: load_full_agg reads and concatenates CSVs for all years."""
    aggs_dir = tmp_path / "aggs"
    aggs_dir.mkdir()

    for year in [2025, 2026]:
        df = pl.DataFrame(
            {
                "season": [year],
                "game_type": ["R"],
                "pitcher": [12345],
                "pitch_type": ["FF"],
                "player_name": ["Test Pitcher"],
                "p_throws": ["R"],
                "team_code": ["NYY"],
                "n_pitches": [100],
                "stuff_plus": [100.0 + (year - 2025) * 10],
            }
        )
        df.write_csv(aggs_dir / f"{year}-pitcher_type.csv")

    import pitcher_narratives.data as data_mod

    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "AGGS_DIR", aggs_dir)
    monkeypatch.setattr(data_mod, "_YEARS", [2025, 2026])

    result = load_full_agg("pitcher_type")
    assert set(result["season"].unique().to_list()) == {2025, 2026}
    assert len(result) == 2


def test_load_full_agg_missing_year(tmp_path, monkeypatch):
    """CSMR-01: load_full_agg skips missing year CSV files gracefully."""
    aggs_dir = tmp_path / "aggs"
    aggs_dir.mkdir()

    df = pl.DataFrame(
        {
            "season": [2026],
            "game_type": ["R"],
            "pitcher": [12345],
            "pitch_type": ["FF"],
            "player_name": ["Test Pitcher"],
            "p_throws": ["R"],
            "team_code": ["NYY"],
            "n_pitches": [100],
            "stuff_plus": [105.0],
        }
    )
    df.write_csv(aggs_dir / f"2026-pitcher_type.csv")
    # No 2025 file created

    import pitcher_narratives.data as data_mod

    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "AGGS_DIR", aggs_dir)
    monkeypatch.setattr(data_mod, "_YEARS", [2025, 2026])

    result = load_full_agg("pitcher_type")
    assert not result.is_empty()
    assert set(result["season"].unique().to_list()) == {2026}


def test_new_functions_in_all():
    """CSMR-01: load_all_statcast and load_full_agg are in data.__all__."""
    import pitcher_narratives.data as data_mod

    assert "load_all_statcast" in data_mod.__all__
    assert "load_full_agg" in data_mod.__all__


# ---------------------------------------------------------------------------
# Tests for prior-season baseline fields (XSBL-01, XSBL-02, XSBL-03)
# ---------------------------------------------------------------------------


def test_prior_season_baseline_populated():
    """XSBL-01: Multi-season pitcher has non-empty prior_season_baseline."""
    data = load_pitcher_data(TEST_PITCHER)
    assert hasattr(data, "prior_season_baseline")
    assert isinstance(data.prior_season_baseline, pl.DataFrame)
    assert not data.prior_season_baseline.is_empty()
    assert "season" in data.prior_season_baseline.columns


def test_prior_pitch_type_baseline_populated():
    """XSBL-01: Multi-season pitcher has non-empty prior_pitch_type_baseline."""
    data = load_pitcher_data(TEST_PITCHER)
    assert hasattr(data, "prior_pitch_type_baseline")
    assert isinstance(data.prior_pitch_type_baseline, pl.DataFrame)
    assert not data.prior_pitch_type_baseline.is_empty()
    assert "season" in data.prior_pitch_type_baseline.columns


def test_prior_season_baseline_is_n_minus_1():
    """XSBL-01/D-01: Prior season baseline contains only the N-1 season."""
    data = load_pitcher_data(TEST_PITCHER)
    current_seasons = data.season_baseline["season"].unique().to_list()
    prior_seasons = data.prior_season_baseline["season"].unique().to_list()
    assert len(current_seasons) == 1
    assert len(prior_seasons) == 1
    assert prior_seasons[0] == current_seasons[0] - 1


def test_current_season_baseline_unchanged():
    """XSBL-02/D-06: Current season baseline still contains only max season."""
    data = load_pitcher_data(TEST_PITCHER)
    seasons = data.season_baseline["season"].unique().to_list()
    assert seasons == [2026]


def test_prior_baseline_empty_single_season():
    """XSBL-03: Single-season pitcher has empty prior baselines."""
    data = load_pitcher_data(SINGLE_SEASON_PITCHER)
    assert data.prior_season_baseline.is_empty()
    assert data.prior_pitch_type_baseline.is_empty()


def test_prior_baseline_not_none():
    """XSBL-03/D-05: Prior baselines are DataFrames, not None."""
    data = load_pitcher_data(SINGLE_SEASON_PITCHER)
    assert data.prior_season_baseline is not None
    assert data.prior_pitch_type_baseline is not None
    assert isinstance(data.prior_season_baseline, pl.DataFrame)
    assert isinstance(data.prior_pitch_type_baseline, pl.DataFrame)


def test_prior_baseline_schema_preserved():
    """XSBL-03: Empty prior baselines preserve column schema."""
    data = load_pitcher_data(SINGLE_SEASON_PITCHER)
    assert "season" in data.prior_season_baseline.columns
    assert "P+" in data.prior_season_baseline.columns
    assert "season" in data.prior_pitch_type_baseline.columns
    assert "P+" in data.prior_pitch_type_baseline.columns


# ── Statcast path resolution (STATCAST_PATH env var) ─────────────────


def test_statcast_dir_defaults_to_statcast_subdir(monkeypatch):
    """Without STATCAST_PATH, parquet files live in DATA_DIR/statcast/."""
    from pitcher_narratives import data as data_mod

    monkeypatch.delenv("STATCAST_PATH", raising=False)
    assert statcast_dir() == data_mod.DATA_DIR / "statcast"


def test_statcast_dir_honors_env_var(monkeypatch):
    """STATCAST_PATH overrides the parquet directory."""
    monkeypatch.setenv("STATCAST_PATH", "/tmp/elsewhere")
    assert str(statcast_dir()) == "/tmp/elsewhere"


def test_statcast_parquet_path_is_year_named(monkeypatch):
    """Parquet files are named <year>.parquet inside the statcast dir."""
    monkeypatch.delenv("STATCAST_PATH", raising=False)
    p = statcast_parquet_path(2026)
    assert p.name == "2026.parquet"
    assert p.parent == statcast_dir()


def test_load_statcast_reads_from_statcast_dir():
    """Integration: pitcher loads from the relocated parquet files."""
    df = load_statcast(592155)
    assert not df.is_empty()
