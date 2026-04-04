---
phase: 23-engine-foundation-data-enrichment
plan: 02
subsystem: engine
tags: [polars, dataclass, arm-angle, percentile, outlier-tag, release-point, handedness]

# Dependency graph
requires:
  - phase: 23-engine-foundation-data-enrichment (plan 01)
    provides: CountSplits engine, established TDD pattern for engine additions
  - phase: 22-context-assembly-prompt-rendering
    provides: PitcherData with statcast DataFrame, compute_release_point_metrics, outlier_tag, LeagueBaseline
provides:
  - Per-pitch-type arm angle (window_arm_angle, season_arm_angle, arm_angle_delta, arm_slot) on ReleasePointPitchType
  - Slot label helpers (_compute_arm_angle, _arm_slot_label, _arm_angle_delta_string) with corrected thresholds (78/65/55/40)
  - LeagueBaseline extended with p_throws handedness field and 6 release point fields
  - outlier_tag with optional percentile parameter (backward compatible)
  - _percentile_from_z helper for CDF-based percentile approximation
  - _compute_metric_percentile helper for population-based ranking
  - Handedness-filtered baseline lookup in pipeline.py and report.py
  - Percentile-enriched outlier tags in all production output
affects: [23-03-context-wiring, 24-pipeline-re-architecture, 25-prompt-engineering]

# Tech tracking
tech-stack:
  added: []
  patterns: [math.erfc-based percentile from z-score, handedness-split baseline filtering, backward-compatible function signature extension]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - src/pitcher_narratives/pipeline.py
    - src/pitcher_narratives/report.py
    - tests/test_engine.py
    - tests/test_pipeline.py

key-decisions:
  - "Corrected arm angle slot thresholds from CONTEXT.md (78/65/55/40 instead of 50/35/15) based on empirical MLB distribution — CONTEXT.md thresholds classified 99% as Overhand"
  - "render_league_baselines uses RHP baselines for display (deterministic, larger population) — handedness-specific baselines used only for percentile computation"
  - "_percentile_from_z using math.erfc CDF approximation instead of per-pitcher population data — avoids needing raw pitcher-level aggregates, z-score already captures relative standing for normally distributed physical metrics"
  - "outlier_tag backward-compatible: 3-arg calls produce exact pre-Phase-23 format (no dash, no percentile text) — existing tests and callers unaffected"

patterns-established:
  - "Handedness-filtered baseline lookup: filter baselines by ctx.throws before building pitch_type dict"
  - "Z-score to percentile via math.erfc: _percentile_from_z(z) for CDF approximation without scipy"
  - "Backward-compatible function extension: optional parameter with None default preserves existing behavior"

requirements-completed: [ENG-02, ENG-03]

# Metrics
duration: 19min
completed: 2026-04-04
---

# Phase 23 Plan 02: Arm Angle + Percentile Outlier Tags Summary

**Per-pitch-type arm angle with slot labels on ReleasePointPitchType, percentile-ranked outlier tags (e.g., "OUTLIER - 98th percentile") in all pipeline and report output, handedness-split baselines**

## Performance

- **Duration:** 19 min
- **Started:** 2026-04-04T17:56:35Z
- **Completed:** 2026-04-04T18:16:17Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Arm angle computed per pitch type via atan2(release_z, abs(release_x)) with corrected slot thresholds (Overhand/High 3/4/Low 3/4/Sidearm/Submarine)
- LeagueBaseline extended with pitcher handedness (p_throws) and 6 release point fields for handedness-split percentile computation
- outlier_tag upgraded with optional percentile parameter producing format "OUTLIER - 98th percentile (above avg, z=+2.5)" while preserving exact backward compatibility
- All 6 production outlier_tag callers (3 in pipeline.py, 3 in report.py) now compute and pass percentile using handedness-filtered baselines
- 25 new tests across engine and pipeline covering arm angle helpers, outlier_tag formats, LeagueBaseline fields, percentile helpers, and integration

## Task Commits

Each task was committed atomically:

1. **Task 1: Arm angle fields on ReleasePointPitchType** - `7849302` (feat) - TDD: tests written first, implementation passes all
2. **Task 2: LeagueBaseline extension + outlier_tag percentile + helpers** - `9f1744c` (feat) - TDD: tests written first, implementation passes all
3. **Task 3: Wire percentile into pipeline.py and report.py callers** - `a1da4b6` (feat) - Integration with production callers

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added arm angle helpers (_compute_arm_angle, _arm_slot_label, _arm_angle_delta_string), extended ReleasePointPitchType with 4 arm angle fields, extended LeagueBaseline with p_throws + 6 release point fields, upgraded outlier_tag with optional percentile, added _percentile_from_z and _compute_metric_percentile helpers
- `src/pitcher_narratives/pipeline.py` - Updated _build_stuff_input to use handedness-filtered baselines and pass percentiles to all 3 outlier_tag calls
- `src/pitcher_narratives/report.py` - Updated _build_stuff_message to use handedness-filtered baselines and pass percentiles to all 3 outlier_tag calls
- `tests/test_engine.py` - 23 new tests: 7 arm angle tests, 7 outlier_tag format tests, 2 LeagueBaseline field tests, 7 percentile helper tests
- `tests/test_pipeline.py` - 2 new integration tests verifying percentile text appears in stuff specialist input

## Decisions Made
- Corrected arm angle slot thresholds from CONTEXT.md values (which classified 99% as Overhand) to empirically validated boundaries matching MLB distribution
- Used math.erfc for z-to-percentile conversion rather than per-pitcher population data -- physical metrics are approximately normal, so z-score captures relative standing correctly
- render_league_baselines deterministically uses RHP baselines for display to avoid ambiguity from 2x entries after handedness grouping
- _compute_metric_percentile test expectation corrected: value == population entry counts as "not strictly less than" (66th percentile, not 83rd) -- matches standard percentile rank definition

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected _compute_metric_percentile test expectation**
- **Found during:** Task 2 GREEN phase
- **Issue:** Plan specified 100.0 is greater than 5 of 6 values in [80, 85, 90, 95, 100, 105] yielding 83rd percentile, but 100.0 is strictly greater than only 4 values (100 == 100, not <), yielding 66th percentile
- **Fix:** Updated test assertion from 83 to 66 to match strict less-than comparison semantics
- **Files modified:** tests/test_engine.py
- **Verification:** All percentile tests pass
- **Committed in:** 9f1744c (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug in plan test specification)
**Impact on plan:** Test expectation corrected for accurate percentile semantics. No scope creep.

## Issues Encountered
- Data files (parquet) not present in worktree -- resolved by symlinking from main repo
- 2 pre-existing test failures in test_context.py (test_to_prompt_yoy_omits_all_steady_pitch, test_to_prompt_yoy_renders_movement_deltas) -- confirmed pre-existing by testing against unmodified code, not caused by this plan's changes

## Known Stubs
None -- all data sources are wired and functional. Arm angle fields are populated by compute_release_point_metrics. Percentile tags appear in production pipeline and report output.

## User Setup Required
None -- no external service configuration required.

## Next Phase Readiness
- Arm angle fields on ReleasePointPitchType ready for Plan 23-03 (PitcherContext wiring and to_prompt rendering)
- Percentile-ranked outlier tags already active in pipeline.py and report.py output
- LeagueBaseline handedness grouping ready for Phase 24 Approach Specialist baseline filtering
- Phase 25 Trend Specialist can use arm_slot labels for release-point framing vocabulary

## Self-Check: PASSED

All 5 modified files exist. All 3 task commits verified (7849302, 9f1744c, a1da4b6). 422 tests pass (2 pre-existing failures excluded).

---
*Phase: 23-engine-foundation-data-enrichment*
*Completed: 2026-04-04*
