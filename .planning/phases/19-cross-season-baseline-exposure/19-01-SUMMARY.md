---
phase: 19-cross-season-baseline-exposure
plan: "01"
subsystem: data
tags: [polars, dataclass, baselines, multi-year, cross-season]

# Dependency graph
requires:
  - phase: 18-consumer-module-updates
    provides: centralized data.py with per-season baselines and multi-year loading
provides:
  - prior_season_baseline and prior_pitch_type_baseline fields on PitcherData
  - load_pitcher_data() splits baselines into current and prior season
  - empty DataFrame contract for single-season pitchers
affects: [20-season-delta-engine, 21-arsenal-trend-engine, 22-context-assembly-prompt-rendering]

# Tech tracking
tech-stack:
  added: []
  patterns: [current/prior season baseline splitting in load_pitcher_data]

key-files:
  created: []
  modified: [src/pitcher_narratives/data.py, tests/test_data.py]

key-decisions:
  - "Prior-season baselines use .clear() for empty DataFrames (preserves schema, zero rows) rather than None"
  - "season_baseline/pitch_type_baseline still contain max season only -- zero regression for downstream consumers"
  - "Prior baselines include ALL seasons before max (not just max-1) to support future 3+ year scenarios"

patterns-established:
  - "Current/prior baseline split: PitcherData.season_baseline = max season, PitcherData.prior_season_baseline = all earlier seasons"
  - "Empty DataFrame contract: prior_* fields are never None, always empty DataFrames with matching schema when no prior data exists"

requirements-completed: [XSBL-01, XSBL-02, XSBL-03]

# Metrics
duration: 4min
completed: 2026-04-03
---

# Phase 19 Plan 01: Cross-Season Baseline Exposure Summary

**PitcherData exposes prior-season baselines via prior_season_baseline and prior_pitch_type_baseline fields, enabling downstream YoY delta computation**

## Performance

- **Duration:** 3m 43s
- **Started:** 2026-04-03T05:02:00Z
- **Completed:** 2026-04-03T05:05:43Z
- **Tasks:** 4
- **Files modified:** 2

## Accomplishments
- Added prior_season_baseline and prior_pitch_type_baseline fields to PitcherData dataclass
- Modified load_pitcher_data() to split computed baselines into current (max season) and prior (all earlier seasons)
- Single-season pitchers get empty DataFrames (same schema, zero rows) for prior baselines -- no None, no crash
- 8 new tests covering XSBL-01, XSBL-02, XSBL-03 requirements plus regression safety

## Task Commits

Each task was committed atomically:

1. **Task 1: Add prior-season fields to PitcherData** - `85960b2` (feat)
2. **Task 2: Modify load_pitcher_data to split baselines** - `e3c5efb` (feat)
3. **Task 3: Add tests for multi-season baseline exposure** - `c97cc2a` (test)
4. **Task 4: Update __all__ exports and docstrings** - `514139f` (docs)

## Files Created/Modified
- `src/pitcher_narratives/data.py` - Added prior_season_baseline and prior_pitch_type_baseline to PitcherData; split baseline computation in load_pitcher_data()
- `tests/test_data.py` - 8 new XSBL tests with synthetic multi-year data fixtures

## Decisions Made
- Prior baselines use `.clear()` (polars method that preserves schema with zero rows) rather than `None` -- consumers can always call `.is_empty()` without type checking
- `season_baseline` and `pitch_type_baseline` still contain max season only, preserving all downstream engine/context/pipeline behavior
- Prior baselines include all seasons before max (using `< max_season` filter) rather than exactly `max_season - 1`, making the design forward-compatible for 3+ year data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 20 (Season-Delta Engine) can now access `data.prior_season_baseline` to compute YoY pitcher-level deltas
- Phase 21 (Arsenal Trend Engine) can now access `data.prior_pitch_type_baseline` to compute per-pitch-type YoY deltas
- Both phases depend on this plan's prior baseline fields being non-None and schema-consistent

## Self-Check: PASSED

- [x] src/pitcher_narratives/data.py exists and modified
- [x] tests/test_data.py exists and modified
- [x] Commit 85960b2 (Task 1) exists
- [x] Commit e3c5efb (Task 2) exists
- [x] Commit c97cc2a (Task 3) exists
- [x] Commit 514139f (Task 4) exists
- [x] 8 new XSBL tests pass

---
*Phase: 19-cross-season-baseline-exposure*
*Completed: 2026-04-03*
