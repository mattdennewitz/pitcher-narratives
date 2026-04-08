---
phase: 19-cross-season-baseline-exposure
plan: 01
subsystem: data
tags: [polars, dataclass, baselines, cross-season, TDD]

# Dependency graph
requires:
  - phase: 17-multi-year-loading
    provides: "Multi-year data loading with per-season baseline grouping"
provides:
  - "PitcherData.prior_season_baseline field (N-1 season baseline DataFrame)"
  - "PitcherData.prior_pitch_type_baseline field (N-1 per-pitch-type baseline DataFrame)"
  - "Schema-preserving empty DataFrames for single-season pitchers"
affects: [20-season-delta-engine, 21-appearance-trends, 22-context-enrichment]

# Tech tracking
tech-stack:
  added: []
  patterns: ["N-1 season filtering via max_season - 1 on baseline_all DataFrames", "Schema-preserving .clear() for empty DataFrames"]

key-files:
  created: []
  modified:
    - "src/pitcher_narratives/data.py"
    - "tests/test_data.py"

key-decisions:
  - "Strictly N-1 season only (not all non-current seasons) per D-01/D-02"
  - "Empty DataFrames via .clear() instead of Optional[None] per D-05"
  - "Fields positioned after pitch_type_baseline, before agg_csvs in dataclass"

patterns-established:
  - "Prior-season extraction: filter baseline_all to max_season - 1, fallback to .clear()"

requirements-completed: [XSBL-01, XSBL-02, XSBL-03]

# Metrics
duration: 8min
completed: 2026-04-08
---

# Phase 19 Plan 01: Cross-Season Baseline Exposure Summary

**Prior-season baseline fields on PitcherData via N-1 filtering of existing multi-season baseline DataFrames**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-08T21:11:17Z
- **Completed:** 2026-04-08T21:19:32Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- PitcherData gains prior_season_baseline and prior_pitch_type_baseline fields populated from already-computed multi-season baseline DataFrames
- Multi-season pitchers (e.g., 592155/Booser) get N-1 season data (2025 when current is 2026)
- Single-season pitchers (e.g., 823810/Moring) get schema-preserving empty DataFrames, never None
- engine.py compute_cross_season_summary() can now access data.prior_season_baseline without changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Add tests for prior-season baseline fields** - `e50d032` (test)
2. **Task 2: Add prior-season baseline fields to PitcherData and populate in load_pitcher_data()** - `5cf9c5d` (feat)

_TDD: Task 1 wrote failing tests (RED), Task 2 made them pass (GREEN)._

## Files Created/Modified
- `src/pitcher_narratives/data.py` - Added prior_season_baseline and prior_pitch_type_baseline fields to PitcherData dataclass; populated in load_pitcher_data() via N-1 filtering
- `tests/test_data.py` - Added 7 new tests covering XSBL-01/02/03 requirements plus SINGLE_SEASON_PITCHER constant

## Decisions Made
- Strictly N-1 season only (not all non-current seasons) -- matches D-01/D-02 locked decisions from research
- Empty DataFrames via .clear() instead of Optional[None] -- matches D-05, preserves schema for downstream consumers
- Fields positioned between pitch_type_baseline and agg_csvs in the dataclass -- maintains logical grouping

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failures in test_analyst.py (import error), test_ask_cli.py, test_pipeline.py, and test_report.py -- all unrelated to this plan's changes. Data and engine test suites pass completely (130/130).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PitcherData now exposes prior-season data, enabling Phase 20 (season-delta-engine) to compute year-over-year deltas
- engine.py compute_cross_season_summary() already has scaffolding at line 2213 that accesses data.prior_season_baseline
- No blockers for downstream phases

## Self-Check: PASSED

- FOUND: src/pitcher_narratives/data.py
- FOUND: tests/test_data.py
- FOUND: .planning/phases/19-cross-season-baseline-exposure/19-01-SUMMARY.md
- FOUND: e50d032 (Task 1 commit)
- FOUND: 5cf9c5d (Task 2 commit)

---
*Phase: 19-cross-season-baseline-exposure*
*Completed: 2026-04-08*
