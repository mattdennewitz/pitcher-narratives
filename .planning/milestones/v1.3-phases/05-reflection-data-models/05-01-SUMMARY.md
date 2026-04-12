---
phase: 05-reflection-data-models
plan: 01
subsystem: report
tags: [pydantic, structured-output, pydantic-ai, anchor-check]

# Dependency graph
requires:
  - phase: 04-report-generation
    provides: ReportResult model, anchor check agent, generate_report_streaming pipeline
provides:
  - AnchorWarning Pydantic model with Literal category validation
  - AnchorResult Pydantic model with is_clean property
  - ReportResult.revision_count field (default 0)
  - Structured anchor agent (output_type=AnchorResult)
  - Separated agent factory (_StrAgents + anchor agent)
affects: [05-02-PLAN, reflection-loop, editor-revision]

# Tech tracking
tech-stack:
  added: []
  patterns: [structured-agent-output, separated-agent-factory, typed-warning-models]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/report.py
    - src/pitcher_narratives/cli.py
    - tests/test_report.py

key-decisions:
  - "Moved _make_agents and type aliases after model definitions to avoid forward reference errors at runtime"
  - "Used _AgentSet = tuple[_StrAgents, Agent[None, AnchorResult]] to separate str-agents from structured anchor agent"
  - "Removed text OUTPUT FORMAT from anchor prompt since JSON schema replaces it via output_type"

patterns-established:
  - "Separated agent factory: str-output agents in one tuple, structured-output agents separate"
  - "WarningCategory Literal type for anchor check categories"

requirements-completed: [MODEL-01, MODEL-02]

# Metrics
duration: 5min
completed: 2026-03-28
---

# Phase 5 Plan 1: Reflection Data Models Summary

**AnchorWarning/AnchorResult Pydantic models with structured anchor agent output_type, revision_count metadata, and typed CLI warning formatting**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-28T14:44:28Z
- **Completed:** 2026-03-28T14:49:42Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Replaced fragile string parsing of anchor check output with framework-enforced structured output via pydantic-ai output_type=AnchorResult
- Added AnchorWarning model with Literal["MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED"] category validation
- Added AnchorResult model with is_clean property following the HallucinationReport pattern
- Added revision_count field to ReportResult (default 0) for reflection loop metadata
- Separated anchor agent creation from str-agents in _make_agents to support different output_type
- Fixed all 8 broken 4-tuple unpackings in test suite (pre-existing bug)
- Added 10 new tests covering all new models, properties, and agent configuration

## Task Commits

Each task was committed atomically:

1. **Task 1: Define AnchorWarning/AnchorResult models, update ReportResult, separate anchor agent, update pipeline and CLI** - `2024d86` (feat)
2. **Task 2: Fix test unpacking bug and add tests for new models and agent** - `840cf58` (test)

## Files Created/Modified
- `src/pitcher_narratives/report.py` - Added AnchorWarning, AnchorResult, WarningCategory models; updated ReportResult with revision_count and typed anchor_warnings; separated anchor agent with output_type=AnchorResult; removed string parsing of anchor output
- `src/pitcher_narratives/cli.py` - Updated anchor warning printer to format typed AnchorWarning objects as "[CATEGORY] description"
- `tests/test_report.py` - Fixed 8 broken 4-tuple unpackings; added 10 new tests for models, properties, agent output_type

## Decisions Made
- Moved _make_agents function and type aliases to after model definitions to avoid NameError on forward-referenced AnchorResult at module level (from __future__ import annotations does not help with runtime variable assignments)
- Used _AgentSet = tuple[_StrAgents, Agent[None, AnchorResult]] to cleanly separate the str-output agents from the structured-output anchor agent
- Simplified _ANCHOR_PROMPT by removing the text OUTPUT FORMAT section (CLEAN/bracket lines) since JSON schema via output_type replaces it

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved type aliases after model definitions to fix NameError**
- **Found during:** Task 1 (agent factory refactoring)
- **Issue:** Plan placed _StrAgents/_AgentSet type aliases at the original location (after _EDITOR_PROMPT, line 328) but AnchorResult is defined later (line 454). Runtime NameError because `from __future__ import annotations` only affects function annotations, not module-level tuple[...] expressions used as variable values.
- **Fix:** Moved _StrAgents, _AgentSet, _agent_cache, and _make_agents to after the model definitions (after ReportResult) in a new AGENT FACTORY section
- **Files modified:** src/pitcher_narratives/report.py
- **Verification:** `uv run python -c "from pitcher_narratives.report import _make_agents, AnchorResult"` succeeds
- **Committed in:** 2024d86 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary code ordering change. No scope creep.

## Issues Encountered
- 3 pre-existing test failures detected (test_synthesizer_prompt_balanced_gains_and_drops, test_editor_prompt_has_skeptical_tone, test_editor_prompt_requires_platoon) -- these tests check for strings not present in the current prompts. Out of scope for Phase 5. Logged for future fix.
- Tests requiring data files (ctx fixture) error in this worktree. These are infrastructure issues unrelated to Phase 5 changes.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all models are fully implemented with correct fields, properties, and validation.

## Next Phase Readiness
- AnchorResult and AnchorWarning models ready for use in reflection loop (Phase 5 Plan 2)
- revision_count field available for tracking revision passes
- Anchor agent returns structured output; pipeline wired end-to-end
- _build_revision_message() function (Plan 2) can use AnchorWarning list directly

## Self-Check: PASSED

All files exist. All commits verified.

---
*Phase: 05-reflection-data-models*
*Completed: 2026-03-28*
