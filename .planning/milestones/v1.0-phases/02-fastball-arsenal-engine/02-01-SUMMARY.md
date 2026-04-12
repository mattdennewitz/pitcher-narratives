---
phase: 02-fastball-arsenal-engine
plan: 01
subsystem: engine
tags: [polars, dataclasses, fastball, velocity, pitching-plus, movement, delta-strings]

# Dependency graph
requires:
  - phase: 01-data-pipeline
    provides: PitcherData bundle with statcast, appearances, baselines, agg_csvs
provides:
  - FastballSummary dataclass with velocity, P+/S+/L+, movement deltas
  - VelocityArc dataclass with early/late inning velocity comparison
  - Delta string helpers (_velo_delta_string, _pplus_delta_string, _usage_delta_string, _movement_delta_string)
  - Primary fastball identification (_identify_primary_fastball)
  - Cold start detection and small sample flagging
affects: [02-02-arsenal-analysis, 03-context-assembly, 04-report-generation]

# Tech tracking
tech-stack:
  added: []
  patterns: [composable-engine-functions, delta-string-generation, n-pitches-weighted-averaging, cold-start-fallback]

key-files:
  created: [engine.py, tests/test_engine.py]
  modified: []

key-decisions:
  - "Used frozenset for _FASTBALL_TYPES constant (FF, SI, FC) for O(1) membership testing"
  - "Delta string vocabulary: directional + magnitude with 'sharply' threshold for large changes"
  - "Cold start produces explicit string rather than zero deltas to avoid misleading LLM"
  - "VelocityArc returns available=False for single-inning relievers with descriptive fallback"

patterns-established:
  - "Delta string pattern: threshold check -> direction -> magnitude with unit"
  - "Engine functions consume PitcherData, return dataclasses with string fields"
  - "Private helpers prefixed with _ but testable via direct import"
  - "Window P+ computed via n_pitches-weighted average of appearance-level data"

requirements-completed: [FB-01, FB-02, FB-03, FB-04]

# Metrics
duration: 3min
completed: 2026-03-26
---

# Phase 2 Plan 1: Fastball Quality Engine Summary

**Fastball quality engine with velocity/P+/movement delta strings, velocity arc analysis, cold start detection, and small sample flagging using polars computation on PitcherData**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-26T19:18:03Z
- **Completed:** 2026-03-26T19:21:24Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- engine.py with FastballSummary and VelocityArc dataclasses providing pre-computed analysis ready for LLM consumption
- Delta string helpers producing qualitative vocabulary ("Up 1.5 mph", "Down sharply", "Steady") for velocity, P+, usage, and movement
- Primary fastball identification (highest-usage FF/SI/FC), cold start detection, small sample flagging
- 22 new tests covering all fastball requirements and edge cases, 47 total tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for fastball engine** - `e250330` (test)
2. **Task 1 GREEN: Implement fastball quality engine** - `4d6ffbd` (feat)

_TDD task with RED-GREEN commits._

## Files Created/Modified
- `engine.py` - Fastball quality computation engine with FastballSummary, VelocityArc, delta helpers, and primary fastball identification
- `tests/test_engine.py` - 22 tests covering delta strings, fastball summary, velocity arc, cold start, and small sample edge cases

## Decisions Made
- Used `frozenset({"FF", "SI", "FC"})` for constant-time fastball type membership testing
- Velocity threshold 0.5 mph, P+ threshold 5 points, "sharply" at 2.0 mph / 10 points per user decisions
- Cold start string "Full season in window -- no trend comparison" replaces all delta strings when window covers full season
- VelocityArc.available=False with descriptive drop_string for single-inning appearances rather than raising errors
- Movement threshold 0.5 inches for "Steady" classification
- Usage rate threshold 5.0 percentage points per user decisions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- engine.py provides the foundation for Plan 02 (arsenal analysis) to build upon
- Delta string helpers and weighted averaging patterns are reusable for arsenal P+/usage computations
- All 47 tests pass with no regressions

## Self-Check: PASSED

- engine.py: FOUND
- tests/test_engine.py: FOUND
- Commit e250330 (RED): FOUND
- Commit 4d6ffbd (GREEN): FOUND
- class FastballSummary: FOUND (1)
- class VelocityArc: FOUND (1)
- def compute_fastball_summary: FOUND (1)
- def compute_velocity_arc: FOUND (1)

---
*Phase: 02-fastball-arsenal-engine*
*Completed: 2026-03-26*
