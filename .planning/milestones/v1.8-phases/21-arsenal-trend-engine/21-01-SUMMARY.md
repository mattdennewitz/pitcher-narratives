---
phase: 21-arsenal-trend-engine
plan: "01"
subsystem: engine
tags: [polars, dataclass, cross-season, yoy-delta, arsenal-trends]

requires:
  - phase: 18-consumer-module-updates
    provides: Centralized multi-year data access via data.py with agg_csvs containing per-season pitch-type CSVs
provides:
  - compute_arsenal_trends() function returning ArsenalTrends with added/dropped/continued pitch-type YoY deltas
  - ArsenalPitchTrend and ArsenalTrends dataclasses ready for context assembly
affects: [22-context-assembly-prompt-rendering, pipeline, context]

tech-stack:
  added: []
  patterns: [cross-season set-difference for added/dropped pitch detection, internal baseline recomputation from agg_csvs]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - tests/test_engine.py

key-decisions:
  - "Compute prior-season baselines internally from agg_csvs rather than depending on Phase 19 PitcherData changes -- enables parallel execution"
  - "Use set difference on pitch types above _MIN_PITCHES threshold to classify added/dropped/continued"
  - "Velocity deltas sourced from statcast (more accurate) rather than CSV aggregation averages"

patterns-established:
  - "Cross-season computation pattern: compute_pitch_type_baseline on agg_csvs, partition by max and max-1 season, set-diff for classification"

requirements-completed: [ATRN-01, ATRN-02, ATRN-03]

duration: 6min
completed: 2026-04-08
---

# Phase 21 Plan 01: Arsenal Trend Engine Summary

**YoY per-pitch-type delta engine identifying added/dropped/continued pitches with qualitative usage, P+/S+/L+, and velocity delta strings**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-08T21:58:09Z
- **Completed:** 2026-04-08T22:04:19Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Arsenal trend engine computes year-over-year per-pitch-type deltas from multi-season CSV aggregation data
- Correctly classifies pitches as added (new in current season), dropped (absent in current), or continued (present in both with full delta suite)
- Returns None for single-season pitchers, preventing fabricated comparisons
- 10 new tests covering all three ATRN requirements plus edge cases, 94 total engine tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Arsenal trend dataclasses and computation function** - `6e42a14` (feat)
2. **Task 2: Tests for arsenal trend engine** - `24880cf` (test)
3. **Task 3: Export and integration** - No commit needed (exports already in Task 1, full test suite verified passing)

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added ArsenalPitchTrend, ArsenalTrends dataclasses and compute_arsenal_trends() function (+281 lines)
- `tests/test_engine.py` - Added 10 tests for arsenal trend engine covering ATRN-01, ATRN-02, ATRN-03 (+196 lines)

## Decisions Made
- Computed prior-season baselines internally from agg_csvs["pitcher_type"] via compute_pitch_type_baseline() rather than depending on Phase 19's PitcherData structural changes. This enables parallel execution while using the same underlying data.
- Used _MIN_PITCHES (10) threshold for inclusion to exclude noise from small sample pitch types.
- Sourced velocity deltas from statcast parquet (per-pitch release_speed) rather than CSV aggregation averages for higher accuracy.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ArsenalTrends dataclass ready for Phase 22 context assembly integration
- compute_arsenal_trends() can be called alongside compute_arsenal_summary() in the pipeline
- Phase 22 will need to wire ArsenalTrends into PitcherContext and to_prompt() rendering

## Self-Check: PASSED

All files found, all commits verified, no stubs detected.

---
*Phase: 21-arsenal-trend-engine*
*Completed: 2026-04-08*
