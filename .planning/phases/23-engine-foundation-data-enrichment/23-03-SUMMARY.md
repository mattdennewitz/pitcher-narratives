---
phase: 23-engine-foundation-data-enrichment
plan: 03
subsystem: context
tags: [pydantic, rendering, count-state, arm-angle, prompt-engineering, section-ordering]

# Dependency graph
requires:
  - phase: 23-engine-foundation-data-enrichment (plan 01)
    provides: CountSplits, CountBucket, CountBucketUsage dataclasses and compute_count_splits function
  - phase: 23-engine-foundation-data-enrichment (plan 02)
    provides: Arm angle fields on ReleasePointPitchType (window_arm_angle, season_arm_angle, arm_angle_delta, arm_slot)
provides:
  - PitcherContext.count_splits field wired from compute_count_splits
  - _render_count_splits_section for inline notable shifts adjacent to platoon (D-13)
  - _render_count_splits_appendix for full usage table (D-10)
  - Arm angle rendering in _render_release_point_section
affects: [24-pipeline-re-architecture, 25-prompt-engineering, approach-specialist]

# Tech tracking
tech-stack:
  added: []
  patterns: [inline-plus-appendix rendering split, D-13 adjacency ordering, per-pitch-type arm angle line in table output]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/context.py
    - tests/test_context.py

key-decisions:
  - "Count splits rendered as two sections: inline notable shifts (D-13 adjacent to platoon) and full appendix table (D-10 near end of prompt)"
  - "Small sample buckets show '--' for delta column in appendix rather than potentially misleading percentage point values"
  - "Arm angle rendered as a separate line per pitch type below the release point table, not as additional table columns, to avoid table width bloat"

patterns-established:
  - "Inline-plus-appendix rendering: notable highlights near related section, full data table as appendix for LLM reference"
  - "Section adjacency per discussion decisions: D-13 places count-state after platoon for LLM correlation"

requirements-completed: [ENG-04]

# Metrics
duration: 7min
completed: 2026-04-04
---

# Phase 23 Plan 03: Context Wiring -- Count Splits + Arm Angle Summary

**PitcherContext wired with count_splits from compute_count_splits, to_prompt renders inline notable shifts adjacent to platoon (D-13) and full appendix table (D-10), arm angle with slot labels in release point section**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-04T18:20:59Z
- **Completed:** 2026-04-04T18:28:05Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- PitcherContext model extended with `count_splits: CountSplits | None` field
- assemble_pitcher_context calls compute_count_splits(data) and passes result to PitcherContext constructor
- _render_count_splits_section renders inline notable shifts (10pp+ deviations) immediately after platoon section per D-13 adjacency requirement
- _render_count_splits_appendix renders full per-bucket usage tables with Window%/Season%/Delta columns, small-sample gating on deltas
- _render_release_point_section enhanced to include arm angle degrees, slot label, season baseline, and delta for each pitch type
- to_prompt() section ordering updated: count-state inline after platoon and before first-pitch; appendix after YoY and before recent appearances
- 13 new tests covering field acceptance, section headers, D-13 adjacency ordering, appendix ordering, notable shifts rendering, small sample tags, empty shifts omission, and arm angle rendering

## Task Commits

Each task was committed atomically:

1. **Task 1: PitcherContext count_splits field and assemble wiring (RED)** - `517f24d` (test)
2. **Task 1: PitcherContext count_splits field and assemble wiring (GREEN)** - `852750f` (feat)

_TDD task: RED phase wrote failing tests, GREEN phase implemented to pass._

## Files Created/Modified
- `src/pitcher_narratives/context.py` - Added CountSplits import and compute_count_splits import; count_splits field on PitcherContext; _render_count_splits_section and _render_count_splits_appendix private methods; arm angle rendering in _render_release_point_section; updated to_prompt section ordering
- `tests/test_context.py` - Added 13 test functions: count_splits field acceptance, defaults to None, assemble populates it, inline section header, D-13 adjacency, appendix header, appendix ordering, notable shifts rendered, small sample tag, appendix table columns, empty shifts omits inline, arm angle in release point, arm angle per pitch type

## Decisions Made
- Count splits use inline-plus-appendix rendering split: notable highlights near platoon for LLM correlation, full table near end for reference
- Small sample buckets show "--" for delta values in appendix to avoid misleading statistics
- Arm angle rendered as separate lines below release point table rather than additional columns

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
- 2 pre-existing test failures in test_context.py (test_to_prompt_yoy_omits_all_steady_pitch, test_to_prompt_yoy_renders_movement_deltas) -- confirmed pre-existing from Plan 23-02 SUMMARY, not caused by this plan's changes

## Known Stubs
None -- all data sources are wired and functional. count_splits field populated by compute_count_splits, arm angle fields populated by compute_release_point_metrics.

## User Setup Required
None -- no external service configuration required.

## Next Phase Readiness
- PitcherContext now includes all Phase 23 engine enrichments: count splits + arm angle + percentile-ranked outlier tags
- Phase 24 Approach Specialist can consume count-state data from the context prompt
- Phase 25 Prompt Engineering can tune section ordering and content

## Self-Check: PASSED

All 2 modified files exist. Both task commits verified (517f24d, 852750f). 435 tests pass (2 pre-existing failures excluded).

---
*Phase: 23-engine-foundation-data-enrichment*
*Completed: 2026-04-04*
