---
phase: 17-multi-year-loading
verified: 2026-04-02T00:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 17: Multi-Year Loading Verification Report

**Phase Goal:** The data pipeline loads and concatenates parquet and CSV files across all configured years, with per-season baselines that prevent cross-season averaging artifacts
**Verified:** 2026-04-02
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | load_statcast() returns pitch data spanning all configured years when files exist | VERIFIED | test_load_statcast_multi_year passes; synthetic 2-year parquet yields game_years {2025, 2026} |
| 2 | load_agg_csvs() returns CSV data spanning all configured years per grain | VERIFIED | test_load_agg_csvs_multi_year passes; pitcher grain shows seasons {2025, 2026} from tmp_path fixtures |
| 3 | When a year's parquet or CSV files are missing, the pipeline skips that year without crashing | VERIFIED | test_load_statcast_missing_year_skipped and test_load_agg_csvs_missing_year_skipped pass; real data returns only 2026 since statcast_2025.parquet and 2025-*.csv do not exist |
| 4 | A pitcher with data in 2025 and 2026 gets separate baseline rows per season, not a cross-season average | VERIFIED | test_season_baseline_per_season and test_pitch_type_baseline_per_season pass; synthetic 2-row DataFrame produces 2 baseline rows with correct per-season values |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/data.py` | Multi-year loading logic and per-season baseline computation | VERIFIED | 352 lines; contains `_YEARS: list[int] = [2025, 2026]` at line 38 |
| `tests/test_data.py` | Multi-year and per-season baseline tests | VERIFIED | 374 lines; contains all 7 required test functions (6 new + 1 updated) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| data.py::load_statcast | _YEARS iteration | `for year in _YEARS` loop with Path.exists() guard and pl.concat() | WIRED | Lines 145-156: loop present, `if not path.exists(): continue` at line 147, `pl.concat(frames)` at line 156 |
| data.py::load_agg_csvs | _YEARS iteration | `for year in _YEARS` loop per grain with Path.exists() guard | WIRED | Lines 185-197: nested loop, `if not path.exists(): continue` at line 190, `pl.concat(frames)` at line 195 |
| data.py::compute_season_baseline | group_by with season | group_by includes season column | WIRED | Line 249: `pitcher_df.group_by(["pitcher", "season"]).agg(...)` |
| data.py::compute_pitch_type_baseline | group_by with season | group_by includes season column | WIRED | Lines 279, 286, 289: `group_by(["pitcher", "season", "pitch_type"])`, `group_by(["pitcher", "season"])`, `join(..., on=["pitcher", "season"])` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| data.py::load_statcast | `frames` list | `pl.read_parquet(path)` per year in _YEARS | Yes — reads real parquet files from DATA_DIR | FLOWING |
| data.py::load_agg_csvs | `frames` list per grain | `load_csv(filename, pid)` per year in _YEARS | Yes — reads real CSV files from AGGS_DIR | FLOWING |
| data.py::compute_season_baseline | `pitcher_df` | agg_csvs["pitcher"] from load_agg_csvs | Yes — populated from real CSV data | FLOWING |
| data.py::compute_pitch_type_baseline | `pitcher_type_df` | agg_csvs["pitcher_type"] from load_agg_csvs | Yes — populated from real CSV data | FLOWING |

Behavioral spot-check confirmed: `load_statcast(592155)` returns 16 rows with `game_year=[2026]` (2025 parquet absent, skipped gracefully). `compute_season_baseline` returns 1 row for this single-season pitcher. `compute_pitch_type_baseline` returns 4 rows (4 pitch types, all 2026 season).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| _YEARS constant is [2025, 2026] | `python -c "from pitcher_narratives.data import _YEARS; print(_YEARS)"` | `[2025, 2026]` | PASS |
| PARQUET_PATH backward compat | `python -c "from pitcher_narratives.data import PARQUET_PATH; ..."` | ends with `statcast_2026.parquet: True` | PASS |
| load_statcast skips missing 2025 | `load_statcast(592155)` with no statcast_2025.parquet | game_years=[2026], 16 rows returned | PASS |
| load_agg_csvs skips missing 2025 CSVs | `load_agg_csvs(592155)` with no 2025-*.csv | pitcher seasons=[2026], non-empty | PASS |
| compute_season_baseline per-season | `compute_season_baseline(csvs["pitcher"])` | 1 row (single-season pitcher), season=[2026] | PASS |
| Full test suite | `pytest tests/test_data.py -x -q` | 28 passed in 1.35s | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MYLD-01 | 17-01-PLAN.md | load_statcast() reads and concatenates parquet files for all configured years | SATISFIED | `for year in _YEARS` loop in load_statcast (line 145); `pl.concat(frames)` at line 156; test_load_statcast_multi_year passes |
| MYLD-02 | 17-01-PLAN.md | load_agg_csvs() reads and concatenates CSV files for all configured years per grain | SATISFIED | Nested `for year in _YEARS` in load_agg_csvs (line 187); `pl.concat(frames)` per grain at line 195; test_load_agg_csvs_multi_year passes |
| MYLD-03 | 17-01-PLAN.md | Pipeline gracefully handles missing year files (skips without crashing) | SATISFIED | `if not path.exists(): continue` guards at lines 147 and 190; test_load_statcast_missing_year_skipped and test_load_agg_csvs_missing_year_skipped pass; confirmed with real data |
| MYLD-04 | 17-01-PLAN.md | Season baselines computed per-season (not cross-season averaged) using the season column | SATISFIED | `group_by(["pitcher", "season"])` at line 249 (compute_season_baseline); `group_by(["pitcher", "season", "pitch_type"])` at line 279 and `join(..., on=["pitcher", "season"])` at line 289 (compute_pitch_type_baseline); both per-season tests pass |

No orphaned requirements: REQUIREMENTS.md maps only MYLD-01 through MYLD-04 to Phase 17, and all four are claimed in 17-01-PLAN.md.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | No anti-patterns detected |

Scanned `src/pitcher_narratives/data.py` and `tests/test_data.py` for TODO/FIXME/placeholder comments, empty implementations, hardcoded empty data, and hollow props. None found.

### Human Verification Required

None. All truths are verifiable programmatically via test execution and static code analysis. No visual rendering, real-time behavior, or external service integration involved.

### Gaps Summary

No gaps. All 4 must-have truths are verified, all artifacts are substantive and wired, all key links are confirmed in code, all 4 requirement IDs are fully satisfied, and the complete test suite (28 tests) passes. The 4 documented commits (c6feda7, 38a63e6, 140c1b7, 9705794) exist in git history and correspond correctly to the TDD sequence: red-test, green-impl, red-test, green-impl.

---
_Verified: 2026-04-02_
_Verifier: Claude (gsd-verifier)_
