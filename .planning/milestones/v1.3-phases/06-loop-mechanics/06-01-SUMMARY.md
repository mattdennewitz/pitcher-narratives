---
phase: 06-loop-mechanics
plan: 01
subsystem: report
tags: [pydantic-ai, revision-loop, anchor-check, editor, testing]

# Dependency graph
requires:
  - phase: 05-reflection-data-models
    provides: AnchorResult/AnchorWarning models, ReportResult.revision_count field, _build_revision_message() prompt builder
provides:
  - for/else revision loop in generate_report_streaming() bounded by MAX_REVISIONS
  - Silent revision passes via editor.run_sync() (not streamed)
  - Downstream capsule handoff (hook/fantasy receive final revised capsule)
  - Loop behavior tests including UX-04 capsule handoff verification
affects: [07-revision-ux-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [for/else revision loop with early break on clean, Agent.run_sync patch for testing capsule handoff]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/report.py
    - tests/test_report.py

key-decisions:
  - "for/else loop over while loop -- Python for/else gives clean exhaustion handling with final anchor check in else clause"
  - "No error handling in loop -- let exceptions propagate to caller per research Design Decisions"
  - "Reuse existing editor agent instance for revisions -- no new agent creation needed"

patterns-established:
  - "Revision loop pattern: for/else bounded by MAX_REVISIONS with break on is_clean"
  - "Silent revision via run_sync: streamed first draft uses run_stream_sync, revisions use run_sync"
  - "Agent.run_sync patch pattern: override str-output agents while leaving structured agents untouched for testing"

requirements-completed: [LOOP-01, LOOP-04, UX-01, UX-02, UX-04]

# Metrics
duration: 4min
completed: 2026-03-28
---

# Phase 6 Plan 1: Loop Mechanics Summary

**Editor-anchor for/else revision loop wired into generate_report_streaming() with MAX_REVISIONS=2, silent run_sync revisions, and downstream capsule handoff verified by Agent.run_sync patch test**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-28T16:17:07Z
- **Completed:** 2026-03-28T16:21:19Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Replaced single-pass anchor check with iterative for/else revision loop bounded by MAX_REVISIONS=2
- Revisions run silently via editor.run_sync() while first draft streams via run_stream_sync()
- Hook writer and fantasy analyst receive the final revised capsule, not the first draft
- UX-04 test patches Agent.run_sync to return distinct string, verifying capsule is actually overwritten after revision

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire the for/else revision loop into generate_report_streaming** - `89b7710` (feat)
2. **Task 2: Add loop behavior tests and update existing test expectations** - `168fc59` (test)

## Files Created/Modified
- `src/pitcher_narratives/report.py` - Added MAX_REVISIONS constant, for/else revision loop replacing single anchor check, updated module/function docstrings, added revision_count to ReportResult construction
- `tests/test_report.py` - Added MAX_REVISIONS import, Agent/mock imports, renamed clean_anchor test to revision_loop_exercises_full_path, added test_max_revisions_constant, added UX-04 downstream capsule handoff test

## Decisions Made
- Used Python for/else loop instead of while loop -- the else clause cleanly handles the "exhausted all revisions" case by running a final anchor check for surviving warnings
- Let exceptions propagate from anchor/editor calls rather than catching them -- per research Design Decisions, the caller handles errors
- Reused the existing editor agent instance for revision calls rather than creating a new agent

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
- Data files (parquet/CSV) missing from worktree since they are gitignored -- resolved by symlinking from main repo root (not a code change, just test infrastructure)

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- Phase 7 (Revision UX & Validation) can now wire stderr output for revision status
- The loop exposes revision_count and anchor_check.warnings needed for UX-03/LOOP-03
- All 194 tests pass with no regressions

## Self-Check: PASSED

- [x] src/pitcher_narratives/report.py exists
- [x] tests/test_report.py exists
- [x] .planning/phases/06-loop-mechanics/06-01-SUMMARY.md exists
- [x] Commit 89b7710 (Task 1) exists
- [x] Commit 168fc59 (Task 2) exists
- [x] 194/194 tests pass

---
*Phase: 06-loop-mechanics*
*Completed: 2026-03-28*
