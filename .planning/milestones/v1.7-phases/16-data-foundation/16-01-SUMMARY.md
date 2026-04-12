---
phase: 16-data-foundation
plan: 01
subsystem: data
tags: [polars, game-type-filter, parquet, csv, data-pipeline]

# Dependency graph
requires:
  - phase: 15-specialist-writer-architecture
    provides: data.py module with load_statcast, load_csv, load_agg_csvs
provides:
  - filter_game_type public function for consumer modules
  - _YEARS constant for multi-year path parameterization
  - _ALLOWED_GAME_TYPES frozenset for game type validation
  - Spring training and exhibition data excluded at load time
affects: [17-multi-year, 18-consumer-updates, engine, resolver, scout]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Allowlist filtering at data load boundary (filter once, all consumers get clean data)
    - Year-parameterized path generation via _YEARS constant and grain tuples

key-files:
  created: []
  modified:
    - src/pitcher_narratives/data.py
    - tests/test_data.py

key-decisions:
  - "Allowlist (is_in) over exclusion list for game type filtering -- safer against unknown game types"
  - "Grain tuples + f-string generation over hardcoded CSV filename dicts -- single _YEARS constant controls all paths"
  - "Pitcher 676571 (Poulin, PJ) as swingman test fixture -- 4 R-game appearances with SP+RP roles"

patterns-established:
  - "filter_game_type at load boundary: all data enters pipeline filtered, no downstream filtering needed"
  - "_YEARS constant drives all path generation: parquet and CSV filenames derived from single source"

requirements-completed: [DFND-01, DFND-02, DFND-03, DFND-04]

# Metrics
duration: 5min
completed: 2026-04-03
---

# Phase 16 Plan 01: Data Foundation Summary

**Game type filtering at load time (R/F/D/L/W allowlist) and year-parameterized path generation via _YEARS constant**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-03T02:25:50Z
- **Completed:** 2026-04-03T02:30:46Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- All parquet and CSV data now filtered to regular-season and postseason game types at load time, excluding 75.9% spring training and 6.3% exhibition data
- Hardcoded "2026-" string literals eliminated from CSV path mappings, replaced with _YEARS-derived f-string generation
- filter_game_type exported as public API for consumer module use in Phase 18
- 22 data tests passing (15 existing + 7 new DFND requirement tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add game type filter, year constant, and path parameterization** (TDD)
   - `191e37f` (test: add failing tests for game type filtering) - RED
   - `be88d02` (feat: add game type filter, year constant, path parameterization) - GREEN
2. **Task 2: Update test fixtures and verify full suite passes** - `822920d` (test)

## Files Created/Modified
- `src/pitcher_narratives/data.py` - Added _YEARS, _ALLOWED_GAME_TYPES, filter_game_type; replaced _SEASON_CSVS/_APPEARANCE_CSVS with grain tuples; updated load_statcast/load_csv with game type filtering; updated load_agg_csvs with _YEARS-derived filenames; updated __all__ to 14 exports
- `tests/test_data.py` - Added 7 new DFND tests, SWINGMAN_PITCHER fixture (676571), updated swingman and starter tests to use Poulin

## Decisions Made
- Used allowlist (is_in) over exclusion list for game type filtering -- unknown game types default to excluded, matching DFND-01 spec
- Replaced _SEASON_CSVS/_APPEARANCE_CSVS dicts with _SEASON_GRAINS/_APPEARANCE_GRAINS tuples + f-string generation -- eliminates all hardcoded year prefixes
- Selected pitcher 676571 (Poulin, PJ) as swingman test fixture -- 4 regular-season appearances with both SP and RP roles, most robust candidate

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed frame_equal -> equals for polars 1.39.3**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Plan specified `result.frame_equal(df)` but polars 1.39.3 removed `frame_equal` in favor of `equals`
- **Fix:** Changed to `result.equals(df)` in test_filter_game_type_no_column
- **Files modified:** tests/test_data.py
- **Verification:** Test passes with equals()
- **Committed in:** be88d02 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Trivial API rename. No scope creep.

## Issues Encountered
- Data files (parquet, CSVs) are gitignored and not present in worktree. Resolved by creating symlinks to main repo data files.
- test_engine.py::test_fastball_velocity_delta fails because Booser (592155) now has only 1 regular-season appearance after filtering. This is expected downstream impact -- test_engine.py fixture update is Phase 18 scope, not a regression from this plan.
- RV_df.csv missing in main repo causes test_analyst.py and some test_ask_cli.py tests to fail -- pre-existing issue, not caused by this plan.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- data.py game type filtering and year parameterization complete
- filter_game_type public API ready for consumer module adoption (Phase 18)
- _YEARS constant ready for multi-year expansion (Phase 17)
- Downstream test fixtures (test_engine.py, test_context.py) will need SWINGMAN_PITCHER or updated assertions in Phase 18

## Known Stubs
None - all functionality fully wired.

---
*Phase: 16-data-foundation*
*Completed: 2026-04-03*
