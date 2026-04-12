---
phase: 02-fastball-arsenal-engine
plan: 02
subsystem: engine
tags: [polars, dataclasses, arsenal, usage-rates, pitching-plus, platoon, first-pitch, delta-strings]

# Dependency graph
requires:
  - phase: 02-fastball-arsenal-engine
    plan: 01
    provides: FastballSummary, delta string helpers, _weighted_window_pplus, cold start detection
  - phase: 01-data-pipeline
    provides: PitcherData bundle with statcast, appearances, baselines, agg_csvs
provides:
  - PitchTypeSummary dataclass with per-type usage rates and P+/S+/L+ deltas
  - PlatoonMix/PlatoonSplit dataclasses with per-type per-side usage and P+ analysis
  - FirstPitchWeaponry/FirstPitchEntry dataclasses with first-pitch distribution analysis
  - compute_arsenal_summary, compute_platoon_mix, compute_first_pitch_weaponry functions
  - _stand_to_platoon, _compute_platoon_baseline, _weighted_window_platoon_pplus helpers
affects: [03-context-assembly, 04-report-generation]

# Tech tracking
tech-stack:
  added: []
  patterns: [platoon-matchup-mapping, first-pitch-filtering, platoon-baseline-weighting, missing-combo-handling]

key-files:
  created: []
  modified: [engine.py, tests/test_engine.py]

key-decisions:
  - "Platoon usage computed as % of pitches to that side that are this type (not % of all pitches)"
  - "Missing platoon combo (e.g., CH not thrown to same-side) returns available=False with descriptive string"
  - "Usage delta sharply threshold at 10 percentage points, consistent with P+ sharply threshold pattern"
  - "_stand_to_platoon maps batter handedness to same/opposite using p_throws comparison"

patterns-established:
  - "Platoon mapping: _stand_to_platoon(stand, p_throws) returns 'same'/'opposite'"
  - "Missing data handled with available=False flag and descriptive delta string"
  - "First-pitch identification via pitch_number == 1 (Statcast convention)"
  - "Platoon baseline uses same n_pitches-weighted pattern as pitch_type_baseline"

requirements-completed: [ARSL-01, ARSL-02, ARSL-03, ARSL-04]

# Metrics
duration: 4min
completed: 2026-03-26
---

# Phase 2 Plan 2: Arsenal Analysis Engine Summary

**Per-pitch-type arsenal breakdown with usage rate/P+ deltas, platoon mix shift analysis with missing combo handling, and first-pitch weaponry distribution using polars computation on PitcherData**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T19:23:54Z
- **Completed:** 2026-03-26T19:28:01Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- PitchTypeSummary with usage rates, P+/S+/L+ season vs window deltas, small sample flagging, and cold start detection for all pitch types
- PlatoonMix with per-type per-side (same/opposite) usage rates and P+ deltas, gracefully handling missing combinations (e.g., CH only thrown to opposite-side batters)
- FirstPitchWeaponry with pitch_number==1 distribution analysis, 42 first pitches validated against at-bat count for test pitcher
- 13 new tests covering all arsenal requirements and edge cases, 60 total tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for arsenal analysis** - `2423d9f` (test)
2. **Task 1 GREEN: Implement arsenal analysis engine** - `5b5162d` (feat)

_TDD task with RED-GREEN commits._

## Files Created/Modified
- `engine.py` - Arsenal analysis engine with PitchTypeSummary, PlatoonMix, PlatoonSplit, FirstPitchEntry, FirstPitchWeaponry dataclasses and compute functions; _stand_to_platoon, _compute_platoon_baseline helpers; updated _usage_delta_string with sharply threshold
- `tests/test_engine.py` - 13 new tests covering usage rate deltas, P+ deltas, pitch names, ordering, small sample, cold start, platoon mix shifts, missing combos, platoon mapping, first-pitch weaponry, first-pitch count, and first-pitch ordering

## Decisions Made
- Platoon usage is computed as % of pitches to that platoon side that are this type (not % of all pitches) -- this reflects how pitch selection adapts to batter handedness
- Missing platoon combinations return available=False with "Not thrown to {side}-side batters" instead of 0% usage delta -- avoids misleading the LLM
- Usage delta gets a "sharply" modifier at 10 percentage points, matching the established pattern for P+ (10 points) and velocity (2.0 mph)
- _stand_to_platoon is a simple equality check (stand == p_throws -> "same") matching P+ CSV convention

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added sharply threshold to _usage_delta_string**
- **Found during:** Task 1 (implementation)
- **Issue:** Plan specified `abs(delta) >= 10.0 -> sharply` but existing _usage_delta_string from Plan 01 did not have a sharply threshold
- **Fix:** Added `if abs(delta) >= 10.0` branch to _usage_delta_string returning sharply format
- **Files modified:** engine.py
- **Verification:** Existing usage delta tests still pass, new behavior consistent with P+ delta pattern
- **Committed in:** 5b5162d (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Minor enhancement to existing helper for consistency. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- engine.py provides complete fastball + arsenal analysis for Phase 3 (context assembly)
- All compute functions return dataclasses with string fields ready for LLM consumption
- All 60 tests pass with no regressions
- Phase 2 requirements fully complete: FB-01 through FB-04, ARSL-01 through ARSL-04

## Self-Check: PASSED

- engine.py: FOUND
- tests/test_engine.py: FOUND
- Commit 2423d9f (RED): FOUND
- Commit 5b5162d (GREEN): FOUND
- class PitchTypeSummary: FOUND (1)
- class PlatoonMix: FOUND (1)
- class FirstPitchWeaponry: FOUND (1)
- def compute_arsenal_summary: FOUND (1)
- def compute_platoon_mix: FOUND (1)
- def compute_first_pitch_weaponry: FOUND (1)
- pitch_number filter: FOUND (2)

---
*Phase: 02-fastball-arsenal-engine*
*Completed: 2026-03-26*
