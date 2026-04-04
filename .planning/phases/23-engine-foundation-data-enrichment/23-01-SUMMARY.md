---
phase: 23-engine-foundation-data-enrichment
plan: 01
subsystem: engine
tags: [polars, dataclass, count-state, usage-splits, sabermetrics]

# Dependency graph
requires:
  - phase: 22-context-assembly-prompt-rendering
    provides: PitcherData with statcast DataFrame (balls/strikes columns), _get_window_game_dates, _is_cold_start, _build_name_map helpers
provides:
  - CountBucketUsage, CountBucket, CountSplits dataclasses
  - compute_count_splits(data) function returning per-pitch-type usage across 5 count-state buckets
  - _COUNT_BUCKETS dict with polars filter expressions for bucket definitions
affects: [23-03-context-wiring, 24-pipeline-re-architecture, approach-specialist]

# Tech tracking
tech-stack:
  added: []
  patterns: [overlapping bucket filter expressions, bucket-level small sample suppression with delta-only gating, pre-rendered notable shift strings]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - tests/test_engine.py

key-decisions:
  - "Two-strike and first-pitch buckets overlap with primary buckets (D-01/D-02) - a pitch at 0-2 is in both ahead and two_strike"
  - "Small sample threshold (<10 pitches) suppresses notable_shifts only, not raw usage rates (D-03)"
  - "Notable shift threshold is 10 percentage points, matching Phase 24 PIPE-02 Approach Specialist lead-story threshold (D-11)"
  - "Test data corrected for bucket overlap semantics - 0-2 counts correctly classified as both ahead and two_strike"

patterns-established:
  - "_COUNT_BUCKETS dict pattern: module-level dict mapping bucket names to polars filter expressions"
  - "_bucket_usage helper: reusable per-pitch-type usage rate computation from filtered DataFrame"
  - "Pre-rendered notable_shifts strings: human-readable shift descriptions ready for prompt embedding"

requirements-completed: [ENG-01, ENG-05]

# Metrics
duration: 6min
completed: 2026-04-04
---

# Phase 23 Plan 01: CountSplits Engine Summary

**Per-pitch-type usage splits across 5 overlapping count-state buckets (ahead/behind/even/two-strike/first-pitch) with 10pp notable shift detection and small-sample gating**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-04T17:45:05Z
- **Completed:** 2026-04-04T17:51:40Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- CountBucketUsage, CountBucket, and CountSplits dataclasses added to engine.py with full docstrings
- compute_count_splits function computes per-pitch-type usage across 5 count-state buckets with window-vs-season comparison
- Overlap semantics correctly implemented: two-strike overlaps with ahead/behind/even (D-01), first-pitch (0-0) also in even bucket (D-02)
- Small sample flag (<10 window pitches) suppresses notable_shifts but preserves raw usage rates for transparency
- Notable shifts pre-rendered as human-readable strings for 10pp+ deviations from season baseline
- 9 comprehensive tests covering all bucket types, overlap, usage_pct sums, small sample, notable shifts, and cold start

## Task Commits

Each task was committed atomically:

1. **Task 1: CountSplits dataclasses and compute function (RED)** - `f89a7c0` (test)
2. **Task 1: CountSplits dataclasses and compute function (GREEN)** - `45ce6ee` (feat)

_TDD task: RED phase wrote failing tests, GREEN phase implemented to pass._

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added CountBucketUsage, CountBucket, CountSplits dataclasses; _COUNT_BUCKETS filter dict; compute_count_splits function; _bucket_usage helper; updated __all__ exports
- `tests/test_engine.py` - Added 9 test functions for count splits: bucket names, two-strike overlap, first-pitch overlap, usage_pct sums, small sample flag, season usage preservation, notable shifts, small-sample exclusion from shifts, cold start identity

## Decisions Made
- Two-strike and first-pitch are implemented as overlapping buckets using independent polars filter expressions, not mutually exclusive categories
- Notable shift strings include human-readable bucket labels ("Ahead in count", "Two-strike counts") rather than raw bucket names
- Also detect "disappeared" pitch types (season usage > 0 but absent from window) as notable shifts when season usage >= 10pp
- Test helper `_make_pitcher_data_for_count_splits` extends the existing pattern from `_make_pitcher_data_for_appearance_trends` with balls/strikes columns

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected test data for bucket overlap semantics**
- **Found during:** Task 1 GREEN phase
- **Issue:** Original test_count_splits_small_sample_flag assumed 0-1 pitches only went to "ahead" bucket, but 0-2 pitches (12 count) also mapped to ahead (strikes > balls), making the ahead bucket larger than expected
- **Fix:** Restructured test to use 0-2 count (which goes to both ahead + two_strike), correctly accounting for 17 total ahead pitches (5 from 0-1 + 12 from 0-2)
- **Files modified:** tests/test_engine.py
- **Verification:** All 9 count split tests pass
- **Committed in:** 45ce6ee (GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test data)
**Impact on plan:** Test data corrected for accurate bucket overlap semantics. No scope creep.

## Issues Encountered
None.

## Known Stubs
None - all data sources are wired and functional.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CountSplits computation ready for Plan 23-02 (arm angle, league baseline extension, outlier percentiles)
- CountSplits ready for Plan 23-03 (PitcherContext wiring and to_prompt rendering adjacent to PlatoonMix per D-13)
- Notable shifts format ready for Phase 24 Approach Specialist consumption

---
*Phase: 23-engine-foundation-data-enrichment*
*Completed: 2026-04-04*
