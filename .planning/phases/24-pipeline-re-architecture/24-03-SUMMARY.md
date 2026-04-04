---
phase: 24-pipeline-re-architecture
plan: 03
subsystem: pipeline
tags: [specialist-agents, pipeline-orchestration, writer-prompt, auditor, approach-specialist, rp-routing]

# Dependency graph
requires:
  - phase: 24-pipeline-re-architecture
    plan: 01
    provides: "_APPROACH_SPECIALIST_PROMPT, _build_approach_input, _build_rp_workload_stub, RP guard on _build_game_shape_input"
  - phase: 24-pipeline-re-architecture
    plan: 02
    provides: "Raw data appendices in Stuff and Trend specialist inputs"
provides:
  - "SpecialistOutputs.approach field (6th specialist)"
  - "PipelineAgents.approach field between game_shape and writer"
  - "run_specialists dispatches 6 agents in parallel"
  - "audit_and_revise_specialists handles 6 specialists"
  - "_build_writer_prompt(role) with RP-conditional text"
  - "build_writer_input accepts and renders 6th specialist section"
  - "Auditor categories 8 (PLATOON_CLAIM_MISMATCH) and 9 (COUNT_STATE_CLAIM_MISMATCH)"
  - "Anchor synthesis includes APPROACH section with RP-conditional game shape label"
affects: [25-prompt-engineering]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Role-conditional writer prompt via _build_writer_prompt(role) function"
    - "Domain-specific auditor categories with conditional framing and chain-of-thought"
    - "RP-conditional anchor synthesis label (WORKLOAD vs GAME SHAPE)"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/pipeline.py
    - tests/test_pipeline.py

key-decisions:
  - "Writer prompt converted from constant to _build_writer_prompt(role) function for RP-conditional text"
  - "make_pipeline_agents accepts role param (default SP) to build role-specific writer prompt"
  - "Auditor categories 8-9 use conditional framing (apply ONLY when) to prevent false positives on non-Approach specialists"
  - "Chain-of-thought format for domain-specific auditor checks: state claim, cite data, Pass/Fail"

patterns-established:
  - "Role-conditional prompt builder pattern: function returns full prompt string with role-dependent sections"
  - "Conditional auditor category pattern: domain-specific checks gated on data presence"

requirements-completed: [PIPE-06, PIPE-07]

# Metrics
duration: 12min
completed: 2026-04-04
---

# Phase 24 Plan 03: Pipeline Orchestration Wiring Summary

**6-agent pipeline fully wired: approach specialist through run/audit/writer/anchor, with RP-conditional writer prompt and domain-specific auditor categories**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-04T20:36:30Z
- **Completed:** 2026-04-04T20:48:30Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Wired the Approach Specialist through the full pipeline: SpecialistOutputs, PipelineAgents, run_specialists (6 parallel agents), audit_and_revise_specialists (6 audits), anchor synthesis (APPROACH section), and write_pipeline_data_file (6 entries)
- Converted _WRITER_PROMPT constant to _build_writer_prompt(role) function with RP-conditional directives (no TTO fabrication, workload section replaces Game Shape)
- Added auditor categories 8 (PLATOON_CLAIM_MISMATCH) and 9 (COUNT_STATE_CLAIM_MISMATCH) with conditional framing and chain-of-thought verification format
- build_writer_input accepts and renders 6th specialist section (Approach)
- 21 new tests across 8 test classes, 97 total pipeline tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire Approach Specialist into SpecialistOutputs, PipelineAgents, run_specialists, and orchestration**
   - `5c8cf6a` (test) - RED: failing tests for 6-agent pipeline wiring
   - `e2e0ede` (feat) - GREEN: wire approach specialist into pipeline orchestration layer

2. **Task 2: Writer prompt (6 specialists + RP conditional), auditor categories 8-9, and build_writer_input 6th section**
   - `49c69cf` (test) - RED: failing tests for writer prompt, auditor categories, build_writer_input
   - `3d32dac` (feat) - GREEN: add writer prompt function, auditor categories, 6th writer input section

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Added approach to SpecialistOutputs/PipelineAgents/run_specialists/audit/anchor/write_pipeline_data_file; replaced _WRITER_PROMPT with _build_writer_prompt(role); added auditor categories 8-9; updated build_writer_input for 6 specialists; make_pipeline_agents accepts role param
- `tests/test_pipeline.py` - Added 8 new test classes (TestSpecialistOutputsApproach, TestPipelineAgentsApproach, TestRunSpecialistsApproach, TestAuditSixSpecialists, TestAnchorSynthesisApproach, TestBuildWriterInput, TestWriterPrompt, TestAuditorPrompt) with 21 total tests

## Decisions Made
- Writer prompt converted from module-level constant to function to support role-conditional text. make_pipeline_agents receives role and passes it through. Default remains "SP" for backward compatibility.
- Auditor categories 8-9 use "apply ONLY when" conditional framing to prevent false positives on specialists that don't receive platoon/count-state data (Pitfall 3 from research).
- Chain-of-thought verification format (D-13) requires auditor to explicitly state the claim, cite data, and issue Pass/Fail verdict for domain-specific checks.
- Anchor synthesis uses RP-conditional label (WORKLOAD vs GAME SHAPE) per Pitfall 2 from research.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed write_pipeline_data_file reference to removed _WRITER_PROMPT constant**
- **Found during:** Task 2 (writer prompt conversion)
- **Issue:** write_pipeline_data_file referenced _WRITER_PROMPT which was replaced by _build_writer_prompt function
- **Fix:** Updated to call _build_writer_prompt(ctx.role) instead
- **Files modified:** src/pitcher_narratives/pipeline.py
- **Committed in:** 3d32dac (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix to prevent NameError at runtime. No scope creep.

## Issues Encountered
None.

## Known Stubs
None -- all functions are fully implemented and wired.

## User Setup Required
None -- no external service configuration required.

## Next Phase Readiness
- Full 6-agent pipeline wired: run_specialists dispatches 6, audit validates 6, writer consumes 6, anchor checks 6
- Writer prompt dynamically built with role-conditional sections
- Auditor has 9 categories including domain-specific platoon/count-state checks
- Ready for Phase 25 (prompt engineering) or end-to-end integration testing

## Self-Check: PASSED

- FOUND: 24-03-SUMMARY.md
- FOUND: 5c8cf6a (Task 1 RED)
- FOUND: e2e0ede (Task 1 GREEN)
- FOUND: 49c69cf (Task 2 RED)
- FOUND: 3d32dac (Task 2 GREEN)
- FOUND: src/pitcher_narratives/pipeline.py
- FOUND: tests/test_pipeline.py

---
*Phase: 24-pipeline-re-architecture*
*Completed: 2026-04-04*
