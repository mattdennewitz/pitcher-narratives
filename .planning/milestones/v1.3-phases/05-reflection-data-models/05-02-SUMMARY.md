---
phase: 05-reflection-data-models
plan: 02
subsystem: report
tags: [pydantic-ai, prompt-builder, anchor-check, revision-loop]

# Dependency graph
requires:
  - phase: 05-01
    provides: AnchorWarning model, AnchorResult model, _UserPrompt type, _build_*_message() pattern
provides:
  - _build_revision_message() function for constructing targeted revision prompts from anchor warnings
affects: [06-loop-mechanics]

# Tech tracking
tech-stack:
  added: []
  patterns: [revision prompt builder following _build_*_message() convention]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/report.py
    - tests/test_report.py

key-decisions:
  - "Revision prompt uses same Data Analyst's Briefing / Current Capsule / Anchor Check Warnings structure matching existing prompt patterns"
  - "CachePoint placed after synthesis to enable provider-level prefix caching on stable content"

patterns-established:
  - "_build_revision_message() follows identical pattern to _build_anchor_message(), _build_editor_message() etc."
  - "Warning formatting as '- [CATEGORY] description' for consistent LLM parsing"

requirements-completed: [LOOP-02]

# Metrics
duration: 2min
completed: 2026-03-28
---

# Phase 5 Plan 02: Revision Prompt Builder Summary

**Pure function _build_revision_message() assembling fixed-size revision prompt from synthesis, capsule, and typed anchor warnings with CachePoint caching**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-28T14:53:14Z
- **Completed:** 2026-03-28T14:55:25Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Built _build_revision_message() function following existing _build_*_message() pattern
- Function accepts (synthesis, capsule, warnings) and returns _UserPrompt with CachePoint after synthesis
- Formats warnings as "- [CATEGORY] description" for consistent editor parsing
- Instruction text preserves voice, forbids new analysis, targets only flagged issues
- 7 tests covering synthesis inclusion, capsule inclusion, warning formatting, instruction text, CachePoint placement, list structure, and empty warnings

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Failing tests for _build_revision_message** - `e3b50bc` (test)
2. **Task 1 (TDD GREEN): Implement _build_revision_message** - `87daa88` (feat)

_TDD task: RED commit (failing tests) followed by GREEN commit (implementation passing all tests)_

## Files Created/Modified
- `src/pitcher_narratives/report.py` - Added _build_revision_message() function after _build_anchor_message()
- `tests/test_report.py` - Added 7 revision message builder tests and import

## Decisions Made
- Followed plan exactly -- no decisions needed beyond plan specification
- CachePoint after synthesis matches existing pattern for provider-level prefix caching

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

- Pre-existing test failure (`test_synthesizer_prompt_balanced_gains_and_drops`) due to case mismatch ("Regression Risks" vs "Regression risks" in prompt). Not caused by this plan's changes -- logged as out-of-scope.
- Data-dependent tests (those using the `ctx` fixture) error due to missing parquet data files in worktree. Pre-existing condition, not caused by this plan.

## Known Stubs

None -- function is fully implemented with no placeholder data or TODO markers.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- _build_revision_message() is ready for Phase 6 loop mechanics to call
- Phase 6 will wire the revision message into the editor-anchor while-loop
- All Phase 5 deliverables complete: AnchorResult/AnchorWarning models (Plan 01), ReportResult.revision_count (Plan 01), revision prompt builder (Plan 02)

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 05-reflection-data-models*
*Completed: 2026-03-28*
