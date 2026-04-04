---
phase: 25-prompt-engineering-heuristic-injection
plan: 03
subsystem: pipeline
tags: [prompt-engineering, specialist-input, adjacency, location-specialist]

requires:
  - phase: 25-01
    provides: Specialist prompt heuristics (stuff trade-off, location contradiction, trend release-point)
  - phase: 25-02
    provides: Writer causal hook requirement and auditor sabermetric whitelist
provides:
  - Per-pitch-type unified location input with zone_rate/xWhiff_P/chase_rate adjacency (D-04)
  - Graceful handling of missing execution data in location input
affects: [pipeline, location-specialist]

tech-stack:
  added: []
  patterns: [per-pitch-type unified input view, lookup-dict merging for cross-data-source joining]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/pipeline.py
    - tests/test_pipeline.py

key-decisions:
  - "Lookup-dict merging (exec_lookup, plus_lookup) for O(1) per-pitch joining instead of nested loops"
  - "Missing execution data renders '--' placeholders instead of crashing or omitting the pitch type"

patterns-established:
  - "Per-pitch-type unified view: group all metrics under ### PitchName (CODE) headings instead of separate sections per metric category"

requirements-completed: [PROMPT-06]

duration: 10min
completed: 2026-04-04
---

# Phase 25 Plan 03: Location Input Restructuring Summary

**Location Specialist input restructured to per-pitch-type unified view with zone_rate/xWhiff_P/chase_rate on same line per D-04 adjacency requirement**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-04T21:59:08Z
- **Completed:** 2026-04-04T22:09:30Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Replaced three separate sections (P vs S Location Impact, Execution Metrics, Plus Scores) with unified per-pitch-type blocks
- Zone%, xWhiff_P, and Chase% now appear on same line per pitch type, enabling LLM to cross-reference contradiction patterns
- Missing execution data renders gracefully with "--" placeholders instead of crashing
- 132 tests passing (7 new TestLocationInputAdjacency + 125 existing)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Write failing tests** - `b625c5c` (test)
2. **Task 1 GREEN: Implement restructuring** - `2b84216` (feat)

_TDD task: test commit followed by implementation commit_

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Restructured `_build_location_input()` from 3 separate sections to per-pitch-type unified view with adjacent contradiction metrics
- `tests/test_pipeline.py` - Added `TestLocationInputAdjacency` class with 7 tests verifying unified view, metric adjacency, graceful missing data handling

## Decisions Made
- Used lookup-dict merging pattern (exec_lookup, plus_lookup) for O(1) per-pitch joining -- avoids nested loops and handles missing data naturally via `.get()`
- Missing execution data renders "--" placeholders rather than omitting the pitch type entirely -- preserves intermediates data visibility

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] IntermediateProbabilities and ExecutionMetrics dataclass signatures**
- **Found during:** Task 1 RED phase
- **Issue:** Plan's test helper used incomplete constructor args -- IntermediateProbabilities has 19 additional season fields + n_pitches/small_sample/cold_start; ExecutionMetrics has n_pitches/small_sample/cold_start
- **Fix:** Added all required fields using _none_fields dict pattern for season fields
- **Files modified:** tests/test_pipeline.py
- **Verification:** All 7 tests construct properly
- **Committed in:** b625c5c (RED phase commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Test fixture fix necessary for correct test construction. No scope creep.

## Issues Encountered
- Merge conflicts when bringing in 25-01 and 25-02 dependencies (both modified overlapping STATE.md/ROADMAP.md/REQUIREMENTS.md sections) -- resolved by combining both branches' changes
- Data files (parquet/CSV) not present in worktree -- symlinked from main repo directory

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 3 plans in Phase 25 complete (PROMPT-01 through PROMPT-06)
- Phase 25 ready for verification and closure
- Location Specialist now receives optimally structured input for contradiction detection

## Self-Check: PASSED

- All key files exist (pipeline.py, test_pipeline.py)
- Both commits found (b625c5c, 2b84216)
- Unified header present in pipeline.py
- exec_lookup pattern present in pipeline.py
- TestLocationInputAdjacency class present in tests
- Old section headers confirmed removed from pipeline.py

---
*Phase: 25-prompt-engineering-heuristic-injection*
*Completed: 2026-04-04*
