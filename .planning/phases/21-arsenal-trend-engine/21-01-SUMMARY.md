---
phase: 21-arsenal-trend-engine
plan: "01"
subsystem: engine
tags: [polars, dataclass, yoy-delta, arsenal, pitch-type]

requires:
  - phase: 18-consumer-module-updates
    provides: Centralized data.py with multi-year loading and compute_pitch_type_baseline
provides:
  - compute_arsenal_trends() function for YoY per-pitch-type deltas
  - ArsenalTrend, PitchTrend, AddedDroppedPitch dataclasses
  - Added/dropped pitch detection with minimum-pitch threshold
affects: [22-context-assembly-prompt-rendering, pipeline, context]

tech-stack:
  added: []
  patterns: [synthetic PitcherData test helpers for multi-season scenarios]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - tests/test_engine.py

key-decisions:
  - "Compute prior-season baselines from agg_csvs['pitcher_type'] directly rather than depending on Phase 19 PitcherData changes"
  - "Use _MIN_PITCHES threshold (10) for added/dropped detection to filter experimental pitches"
  - "Source velocity from Statcast data for accuracy with agg CSV fallback"
  - "Compare only the two most recent seasons (not all available)"

patterns-established:
  - "Synthetic PitcherData factory helpers (_make_pitcher_data_for_trends, _make_pitcher_type_agg, _make_statcast) for isolated multi-season testing"
  - "YoY delta strings reuse existing qualitative helpers (_usage_delta_string, _pplus_delta_string, _velo_delta_string) for consistency"

requirements-completed: [ATRN-01, ATRN-02, ATRN-03]

duration: 6min
completed: 2026-04-03
---

# Phase 21 Plan 01: Arsenal Trend Engine Summary

**YoY per-pitch-type arsenal evolution engine with added/dropped detection and delta computation using existing qualitative string helpers**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-03T11:54:46Z
- **Completed:** 2026-04-03T12:00:53Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- compute_arsenal_trends() identifies pitches added/dropped between seasons using _MIN_PITCHES threshold
- Computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity with qualitative delta strings
- Returns None for single-season pitchers (no fabricated trends)
- 13 comprehensive tests covering all requirements with synthetic multi-season data

## Task Commits

Each task was committed atomically:

1. **Task 1: ArsenalTrend dataclasses and compute function** - `f909524` (feat)
2. **Task 2: Tests for arsenal trend computation** - `b48e4c9` (test)

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added ArsenalTrend, PitchTrend, AddedDroppedPitch dataclasses and compute_arsenal_trends() function (246 lines)
- `tests/test_engine.py` - Added 13 tests with synthetic PitcherData helpers for multi-season scenarios (449 lines)

## Decisions Made
- Computed prior-season baselines from agg_csvs["pitcher_type"] directly using existing compute_pitch_type_baseline, avoiding a hard dependency on Phase 19's PitcherData structural changes
- Used _MIN_PITCHES (10) as threshold for added/dropped pitch detection to filter noise from occasional experimental pitches
- Sourced velocity from Statcast pitch-level data for accuracy, with agg CSV fallback when statcast data unavailable for a pitch type
- Compared only the two most recent seasons when 3+ exist, matching how within-season deltas compare recent window to season

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Known Stubs

None -- all data paths are wired and functional.

## Next Phase Readiness
- ArsenalTrend dataclass ready for Phase 22 (Context Assembly) to integrate into PitcherContext and to_prompt()
- compute_arsenal_trends() callable from any consumer with a PitcherData bundle
- Delta strings use same qualitative language as within-season deltas, ensuring LLM prompt consistency

## Self-Check: PASSED

- engine.py: FOUND
- test_engine.py: FOUND
- 21-01-PLAN.md: FOUND
- 21-01-SUMMARY.md: FOUND
- f909524 (Task 1): FOUND
- b48e4c9 (Task 2): FOUND

---
*Phase: 21-arsenal-trend-engine*
*Completed: 2026-04-03*
