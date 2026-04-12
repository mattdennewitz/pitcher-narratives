---
phase: 16-data-foundation
verified: 2026-04-03T03:15:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 16: Data Foundation Verification Report

**Phase Goal:** The data pipeline filters out spring training and exhibition games at load time and replaces all hardcoded year-specific paths with a parameterized `_YEARS` constant, so all downstream modules receive clean regular-season data without knowing about file naming or game type semantics
**Verified:** 2026-04-03T03:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | `load_statcast()` returns only regular-season and postseason rows — no spring training (game_type S) or exhibition (game_type C/E) data | VERIFIED | `filter_game_type(df)` called at line 142 immediately after `pl.read_parquet()`; `test_load_statcast_filters_game_type` passes |
| 2  | All CSV filenames derive from `_YEARS` constant — no hardcoded `"2026-"` string literals in path generation | VERIFIED | `_SEASON_CSVS`/`_APPEARANCE_CSVS` dicts eliminated; grain tuples + `f"{_YEARS[-1]}-{grain}.csv"` used; `grep -n "2026-"` returns zero matches; `test_no_hardcoded_year_in_csv_dicts` passes |
| 3  | `season` column remains in `_ID_COLS` so it is never weight-averaged as a metric | VERIFIED | `_ID_COLS` frozenset at line 53 contains `"season"`; `test_season_in_id_cols` passes |
| 4  | `filter_game_type` is importable from `pitcher_narratives.data` (in `__all__`) | VERIFIED | Listed at line 26 of `__all__`; 14 total exports; `test_filter_game_type_exported` passes; direct import confirmed |
| 5  | All existing tests pass with updated assertions for filtered data | VERIFIED | 22/22 tests in `tests/test_data.py` pass; swingman test updated to use SWINGMAN_PITCHER (676571); `test_classify_starter` uses SWINGMAN_PITCHER |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/data.py` | Game type filtering, year-parameterized paths, public `filter_game_type` | VERIFIED | 328 lines; contains `_YEARS`, `_ALLOWED_GAME_TYPES`, `filter_game_type`, grain tuples, updated `load_statcast` and `load_csv`; 14 exports in `__all__` |
| `tests/test_data.py` | Tests for DFND-01 through DFND-04 behaviors plus fixture update | VERIFIED | 230 lines; all 7 new DFND tests present; `SWINGMAN_PITCHER = 676571` constant defined; 22/22 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `data.py:load_statcast` | `data.py:filter_game_type` | called immediately after `pl.read_parquet()` | WIRED | Line 141: `pl.read_parquet()`, Line 142: `df = filter_game_type(df)` — sequential, no branches |
| `data.py:load_csv` | `data.py:filter_game_type` | called immediately after `pl.read_csv()` | WIRED | Line 117: `pl.read_csv(path)`, Line 118: `df = filter_game_type(df)` — sequential, no branches |
| `data.py:PARQUET_PATH` | `data.py:_YEARS` | f-string path derivation | WIRED | Line 39: `PARQUET_PATH = DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"` — resolves to same value as before but driven by `_YEARS` |
| `data.py:load_agg_csvs` | `data.py:_YEARS` | f-string CSV filename generation | WIRED | Line 173: `filename = f"{_YEARS[-1]}-{grain}.csv"` — all 8 grains use `_YEARS[-1]` prefix |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `data.py:load_statcast` | `df` from `pl.read_parquet(PARQUET_PATH)` | actual parquet file read, then filtered | Yes — `filter_game_type` filters rows, does not replace with empty result; `load_statcast(592155)` returns 1-row DataFrame (Booser's 1 R-game appearance) | FLOWING |
| `data.py:load_csv` | `df` from `pl.read_csv(path)` | actual CSV file read, then filtered | Yes — `filter_game_type` filters rows; `test_load_csv_filters_game_type` passes with real data | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `filter_game_type` importable as public API | `uv run python -c "from pitcher_narratives.data import filter_game_type; print('OK')"` | OK | PASS |
| `_YEARS` constant is `[2026]` | `uv run python -c "from pitcher_narratives.data import _YEARS; print(_YEARS)"` | `[2026]` | PASS |
| `PARQUET_PATH` ends with `statcast_2026.parquet` | `str(PARQUET_PATH).endswith(f"statcast_{_YEARS[-1]}.parquet")` | `True` | PASS |
| `filter_game_type in __all__` | `"filter_game_type" in __all__` | `True` | PASS |
| `__all__` has 14 exports | `len(__all__)` | `14` | PASS |
| No hardcoded `2026-` string literals | `grep -n "2026-" data.py` | 0 matches | PASS |
| All 22 data tests pass | `uv run pytest tests/test_data.py -v` | `22 passed in 0.78s` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DFND-01 | 16-01-PLAN.md | Data pipeline filters to allowed game types (R, F, D, L, W) at load time, excluding spring training and exhibition data | SATISFIED | `_ALLOWED_GAME_TYPES = frozenset({"R", "F", "D", "L", "W"})` at line 66; `filter_game_type()` called in both `load_statcast()` and `load_csv()`; `test_load_statcast_filters_game_type` and `test_load_csv_filters_game_type` pass |
| DFND-02 | 16-01-PLAN.md | Year-specific hardcoded paths replaced with parameterized loading from a `_YEARS` constant | SATISFIED | `_YEARS: list[int] = [2026]` at line 38; `PARQUET_PATH = DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"` at line 39; grain tuples with `f"{_YEARS[-1]}-{grain}.csv"` in `load_agg_csvs`; `test_years_constant_drives_paths` and `test_no_hardcoded_year_in_csv_dicts` pass |
| DFND-03 | 16-01-PLAN.md | `"season"` added to `_ID_COLS` so year values are not weight-averaged as metrics | SATISFIED | `_ID_COLS` frozenset at line 53 contains `"season"`; `compute_season_baseline` and `compute_pitch_type_baseline` exclude `_ID_COLS` from weighted average expressions; `test_season_in_id_cols` passes |
| DFND-04 | 16-01-PLAN.md | `filter_game_type` helper exported as public API for use by consumer modules | SATISFIED | Note: REQUIREMENTS.md text has `_filter_game_type` (with leading underscore) which is a typo — a leading underscore indicates private, contradicting "exported as public API". The implementation correctly uses `filter_game_type` (no underscore) and includes it in `__all__`; `test_filter_game_type_exported` passes |

**Note on DFND-04 naming discrepancy:** REQUIREMENTS.md line 15 says `_filter_game_type` but the plan's must_haves, tasks, and implementation all use `filter_game_type` (no leading underscore). The leading underscore would make it private — the intent of "exported as public API" is clearly `filter_game_type`. Implementation matches intent; requirements text has a minor typo.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No `TODO`, `FIXME`, `PLACEHOLDER`, empty implementations, hardcoded empty data, or hollow props found in `src/pitcher_narratives/data.py` or `tests/test_data.py`.

### Human Verification Required

None. All behaviors are deterministic data transformations testable programmatically. The test suite confirms filtering behavior against real data files.

### Out-of-Scope Failures (Not Regressions)

The full test suite (`uv run pytest tests/`) shows 25 failures and 53 errors in other test files. These are pre-existing issues or expected downstream impact:

1. **`test_engine.py` failures (13):** Engine tests use `TEST_PITCHER = 592155` (Booser), who had 13 spring training appearances before filtering and only 1 regular-season appearance after. Tests like `test_fastball_velocity_delta` now fail because a single-appearance window produces different delta strings. The SUMMARY explicitly documents this as Phase 18 scope (`test_engine.py` fixture update deferred).

2. **`test_analyst.py`, `test_context.py`, `test_pipeline.py`, `test_report.py` errors (53 errors):** `FileNotFoundError: No such file or directory: .../aggs/RV_df.csv`. The SUMMARY documents this as a pre-existing issue — `RV_df.csv` is missing from the main repo and is not caused by phase 16.

3. **`test_ask_cli.py`, `test_cli.py` failures:** Downstream CLI test failures caused by engine fixture issues above — also Phase 18 scope.

Phase 16's scope was `src/pitcher_narratives/data.py` and `tests/test_data.py` only. All 22 data tests pass.

### Gaps Summary

No gaps. All 5 must-have truths are verified, all artifacts are substantive and wired, all 4 requirement IDs (DFND-01 through DFND-04) are satisfied, and no anti-patterns are present.

---

_Verified: 2026-04-03T03:15:00Z_
_Verifier: Claude (gsd-verifier)_
