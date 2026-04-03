---
phase: 17-multi-year-loading
plan: 01
subsystem: data
tags: [polars, parquet, csv, multi-year, baselines, per-season]

requires:
  - phase: 16-data-foundation
    provides: game_type filtering, _YEARS constant, grain-based CSV loading, season in _ID_COLS
provides:
  - Multi-year parquet loading via _YEARS iteration with missing-file skip
  - Multi-year CSV loading per grain via _YEARS iteration with missing-file skip
  - Per-season baseline computation (group_by pitcher+season)
  - Per-season pitch type baseline with per-season usage_pct
affects: [18-consumer-updates, engine, resolver, scout, context]

tech-stack:
  added: []
  patterns: [multi-year iteration via explicit _YEARS list, Path.exists() guard for graceful skip, pl.concat for vertical concatenation]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/data.py
    - tests/test_data.py

key-decisions:
  - "Explicit _YEARS=[2025,2026] constant over glob-based auto-discovery -- simpler, predictable, matches research recommendation"
  - "Filter per-year-file before concat to minimize memory -- apply filter_game_type and pitcher filter per parquet before concatenation"
  - "Empty DataFrame for grains with all years missing -- acceptable because downstream pipeline fails on pitcher-not-found path"

patterns-established:
  - "Multi-year loading pattern: for year in _YEARS -> Path.exists() guard -> read -> filter -> append -> pl.concat(frames)"
  - "Per-season baseline grouping: group_by([pitcher, season]) instead of group_by(pitcher)"

requirements-completed: [MYLD-01, MYLD-02, MYLD-03, MYLD-04]

duration: 7min
completed: 2026-04-03
---

# Phase 17 Plan 01: Multi-Year Loading Summary

**Multi-year parquet/CSV loading across _YEARS=[2025,2026] with missing-file graceful skip and per-season baseline computation via pitcher+season grouping**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-03T02:49:53Z
- **Completed:** 2026-04-03T02:57:04Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- load_statcast() iterates _YEARS, reads each parquet if it exists, filters per-year, and concatenates -- missing files silently skipped
- load_agg_csvs() iterates _YEARS per grain, reads year-prefixed CSVs if they exist, and concatenates per grain -- missing files silently skipped
- compute_season_baseline() groups by ["pitcher", "season"] producing separate baseline rows per season instead of cross-season averages
- compute_pitch_type_baseline() groups by ["pitcher", "season", "pitch_type"] with per-season usage_pct calculation
- 6 new tests added (multi_year x2, missing_year x2, per_season x2), 1 test updated (years_constant) -- 28 total tests green in test_data.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Multi-year parquet and CSV loading with missing-file handling**
   - `c6feda7` (test) - Failing tests for multi-year loading
   - `38a63e6` (feat) - Implementation: _YEARS=[2025,2026], load_statcast/load_agg_csvs iterate years
2. **Task 2: Per-season baseline computation**
   - `140c1b7` (test) - Failing tests for per-season baselines
   - `9705794` (feat) - Implementation: group_by with season in both baseline functions

_Note: TDD tasks have RED (test) and GREEN (feat) commits._

## Files Created/Modified
- `src/pitcher_narratives/data.py` - Multi-year loading in load_statcast/load_agg_csvs, per-season grouping in compute_season_baseline/compute_pitch_type_baseline
- `tests/test_data.py` - 6 new tests for multi-year and per-season behavior, 1 updated test

## Decisions Made
- Used explicit `_YEARS` iteration (not glob auto-discovery) per research recommendation -- predictable, no surprises from unexpected files
- Filter per-year parquet before concat (game_type + pitcher filter applied per file) to minimize memory usage
- Return `pl.DataFrame()` (empty, no schema) when all years missing for a grain -- acceptable since pipeline fails elsewhere on pitcher-not-found

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

**Pre-existing test failures (not caused by Phase 17 changes):**
- `test_fastball_velocity_delta` (test_engine.py): Cold-start detection triggers for TEST_PITCHER because Phase 16 game_type filtering reduced data to 1 regular-season appearance fitting entirely within the 30-day window. Pre-existing from Phase 16.
- Multiple test files fail due to missing `aggs/RV_df.csv` (test_analyst.py, test_ask_cli.py, test_context.py, etc.). Pre-existing data availability issue.
- Several engine tests fail due to pitch type distribution changes when spring training data was excluded (Phase 16 regression). Pre-existing.

All pre-existing failures documented in `deferred-items.md`.

## User Setup Required

None -- no external service configuration required.

## Known Stubs

None -- all data loading paths are fully wired. The 2025 data files do not exist on disk yet, but the code correctly handles their absence via Path.exists() guards.

## Next Phase Readiness
- data.py multi-year foundation complete
- Phase 18 (consumer-updates) can now update engine.py, resolver.py, and scout.py to leverage multi-year data
- `PitcherData.season_baseline` now returns multiple rows per season -- Phase 18 consumers that assume single-row baseline need updating

## Self-Check: PASSED

- All key files exist (data.py, test_data.py, 17-01-SUMMARY.md)
- All 4 commits verified: c6feda7, 38a63e6, 140c1b7, 9705794
- 28 tests pass in test_data.py

---
*Phase: 17-multi-year-loading*
*Completed: 2026-04-03*
