---
phase: 18-consumer-module-updates
plan: 01
subsystem: data
tags: [polars, parquet, csv, data-loading, multi-year]

# Dependency graph
requires:
  - phase: 16-data-foundation
    provides: "filter_game_type(), _YEARS constant, DATA_DIR parameterization"
  - phase: 17-multi-year-loading
    provides: "Multi-year load_statcast() and load_agg_csvs() pattern"
provides:
  - "load_all_statcast(columns) - league-wide Statcast data across all years"
  - "load_full_agg(grain) - league-wide CSV aggregation data across all years"
affects: [18-02-consumer-module-updates, engine, resolver, scout]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Unfiltered league-wide loaders alongside pitcher-filtered loaders in data.py"
    - "Optional columns parameter for memory-efficient parquet reads"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/data.py
    - tests/test_data.py

key-decisions:
  - "load_all_statcast returns empty DataFrame (not error) when no files exist, matching skip-missing-year pattern"
  - "load_full_agg delegates to load_csv(filename, None) for game-type filtering and date parsing reuse"

patterns-established:
  - "League-wide data access through data.py public API (no direct pl.read_csv/read_parquet elsewhere)"

requirements-completed: []  # Functions added but consumer refactoring (CSMR-01/02/03) is in plan 18-02

# Metrics
duration: 2min
completed: 2026-04-02
---

# Phase 18 Plan 01: Data Foundation Functions Summary

**Two new league-wide data loaders (load_all_statcast, load_full_agg) for consumer module refactoring**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-03T03:16:28Z
- **Completed:** 2026-04-03T03:18:54Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added `load_all_statcast(columns=None)` to data.py -- loads all pitchers' Statcast parquet data across all years with game-type filtering and optional column selection
- Added `load_full_agg(grain)` to data.py -- loads all pitchers' CSV aggregation data for a grain across all years via `load_csv()` for consistent filtering and date parsing
- Both functions exported in `__all__`, follow existing multi-year/missing-file patterns from Phase 17
- 11 new tests covering multi-year concat, missing-year skip, game-type filtering, column selection, date parsing, all-pitchers return, and `__all__` exports

## Task Commits

Each task was committed atomically:

1. **Task 1: Add load_all_statcast() and load_full_agg() to data.py** (TDD)
   - RED: `5ed3faa` (test) - 11 failing tests for new functions
   - GREEN: `1279d11` (feat) - Implementation passing all 39 tests

**Plan metadata:** [pending final commit]

## Files Created/Modified
- `src/pitcher_narratives/data.py` - Added load_all_statcast() and load_full_agg() functions, updated __all__
- `tests/test_data.py` - Added 11 new tests for the two new functions

## Decisions Made
- `load_all_statcast()` returns `pl.DataFrame()` (empty) when no year files exist, consistent with the graceful-skip pattern rather than raising ValueError
- `load_full_agg()` delegates to `load_csv(filename, None)` rather than reimplementing CSV loading, ensuring game-type filtering and date parsing are applied consistently
- Both functions placed between `load_agg_csvs()` and `classify_appearances()` in data.py for logical grouping near existing loaders

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - both functions are fully implemented with real data access.

## Next Phase Readiness
- `load_all_statcast()` and `load_full_agg()` ready for Plan 18-02 consumer refactoring
- engine.py, resolver.py, and scout.py can now replace direct `pl.read_csv()`/`pl.read_parquet()` calls with these data.py functions

## Self-Check: PASSED

All artifacts found, all commits verified.

---
*Phase: 18-consumer-module-updates*
*Completed: 2026-04-02*
