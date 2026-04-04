---
phase: 24-pipeline-re-architecture
plan: 01
subsystem: pipeline
tags: [specialist-agents, approach-analysis, platoon, count-splits, reliever-routing]

# Dependency graph
requires:
  - phase: 23-engine-foundation-data-enrichment
    provides: "CountSplits, PlatoonSplit, FirstPitchWeaponry dataclasses and PitcherContext render methods"
provides:
  - "_APPROACH_SPECIALIST_PROMPT constant for 6th specialist"
  - "_build_approach_input() wiring platoon/count/first-pitch into specialist input"
  - "_build_rp_workload_stub() for RP game shape routing"
  - "RP conditional guard on _build_game_shape_input()"
  - "'approach' registered in _get_specialist_input dispatch"
affects: [24-02-PLAN, 24-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RP conditional routing in specialist input builders"
    - "Approach specialist: strategy-first framing with cross-reference directive"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/pipeline.py
    - tests/test_pipeline.py

key-decisions:
  - "Approach prompt uses strategy-first framing (D-01) over data-first"
  - "Only notable shifts (10+ pp) in approach input, not full appendix (D-04)"
  - "RP game shape returns static workload stub instead of TTO analysis"

patterns-established:
  - "RP guard pattern: check ctx.role at top of input builder, return stub"
  - "Approach input assembles from 3 PitcherContext render methods plus baseline arsenal"

requirements-completed: [PIPE-01, PIPE-02, PIPE-03, PIPE-04]

# Metrics
duration: 6min
completed: 2026-04-04
---

# Phase 24 Plan 01: Pipeline Re-Architecture Summary

**Approach Specialist prompt and input builder with RP Game Shape conditional routing and location platoon verification**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-04T20:19:15Z
- **Completed:** 2026-04-04T20:25:48Z
- **Tasks:** 1 (TDD)
- **Files modified:** 2

## Accomplishments
- Added 6th specialist agent (Approach) with strategy-first prompt covering platoon, count-state, and first-pitch analysis
- RP Game Shape input builder returns workload stub instead of TTO analysis for relievers
- Verified Location specialist input contains no platoon data (PIPE-03)
- 16 new tests covering approach input, approach prompt, RP routing, and location platoon absence

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for approach specialist** - `1b7acd2` (test)
2. **Task 1 GREEN: Implement approach specialist and RP routing** - `e9900ac` (feat)

**Plan metadata:** (pending)

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Added _APPROACH_SPECIALIST_PROMPT, _build_approach_input, _build_rp_workload_stub, RP guard on _build_game_shape_input, approach in _get_specialist_input
- `tests/test_pipeline.py` - Extended _make_pipeline_ctx, added test helpers, 4 new test classes with 16 tests

## Decisions Made
- Approach prompt uses strategy-first framing (D-01): lead with pattern, then cite data
- Only notable shifts (10+ pp) flow to approach specialist, not full count-state appendix (D-04)
- RP game shape returns static workload stub with recent appearances table -- no LLM call needed for short-outing workload context
- Cross-reference directive (D-02) in prompt connects platoon + count-state observations when they tell the same story

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
None.

## Known Stubs
None -- all functions are fully implemented and wired.

## User Setup Required
None -- no external service configuration required.

## Next Phase Readiness
- Approach specialist prompt and input builder ready for integration into pipeline orchestration (24-02-PLAN)
- _build_rp_workload_stub available for pipeline routing logic
- All existing tests continue to pass

---
*Phase: 24-pipeline-re-architecture*
*Completed: 2026-04-04*
