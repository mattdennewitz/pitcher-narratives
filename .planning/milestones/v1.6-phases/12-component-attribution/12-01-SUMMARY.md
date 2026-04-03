---
phase: 12-component-attribution
plan: 01
subsystem: data
tags: [polars, csv, run-values, component-attribution]

# Dependency graph
requires:
  - phase: 11-intermediate-probability-pipeline
    provides: "Intermediate probability columns in all_pitches.csv"
provides:
  - "load_run_values() function for 156-row count-outcome run values lookup"
  - "RV_DF_PATH constant for aggs/RV_df.csv"
  - "Validated all_pitches.csv with all 13 P/S outcome probability columns"
affects: [12-component-attribution, 13-tool-interface-updates]

# Tech tracking
tech-stack:
  added: []
  patterns: ["CSV loader function pattern matching load_statcast/load_agg_csvs"]

key-files:
  created: []
  modified: ["src/pitcher_narratives/data.py"]

key-decisions:
  - "Placed load_run_values between load_statcast and load_agg_csvs following existing loader grouping"

patterns-established:
  - "Top-level CSV path constants (RV_DF_PATH) for non-pitcher-scoped lookup tables"

requirements-completed: [DATA-03]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 12 Plan 01: Data Prerequisite Summary

**RV_df.csv (156-row run values lookup) validated and load_run_values() wired into data.py public API**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T21:18:25Z
- **Completed:** 2026-03-31T21:21:20Z
- **Tasks:** 1 (Task 1 was human-action checkpoint, completed before execution)
- **Files modified:** 1

## Accomplishments
- Validated aggs/RV_df.csv: 156 rows with balls, strikes, model_classes, delta_run_exp, n_observations columns
- Validated aggs/2026-all_pitches.csv: all 13 P-variant and 13 S-variant outcome probability columns present (95,107 rows, 81 columns)
- Added load_run_values() function and RV_DF_PATH constant to data.py with public API exports
- All 245 existing tests continue to pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Regenerate all_pitches.csv with all 13 outcome columns** - Human checkpoint (completed before execution)
2. **Task 2: Validate data files and add load_run_values to data.py** - `f6628c0` (feat)

## Files Created/Modified
- `src/pitcher_narratives/data.py` - Added RV_DF_PATH constant, load_run_values() function, updated __all__ exports

## Decisions Made
- Placed load_run_values() between load_statcast() and load_agg_csvs() to group all loader functions together
- Used simple pl.read_csv() without pitcher filtering since RV_df.csv is a global lookup table (not pitcher-scoped)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Worktree did not have aggs/ directory (data files not tracked in git) - resolved by symlinking from main repo

## User Setup Required

None - no external service configuration required. (Task 1 user setup was completed before this execution.)

## Next Phase Readiness
- load_run_values() ready for engine.py compute_component_attribution in Plan 12-02
- All 13 outcome columns available in all_pitches.csv for probability x run_value computation
- No blockers for Plan 12-02

## Self-Check: PASSED

- FOUND: src/pitcher_narratives/data.py
- FOUND: .planning/phases/12-component-attribution/12-01-SUMMARY.md
- FOUND: commit f6628c0

---
*Phase: 12-component-attribution*
*Completed: 2026-03-31*
