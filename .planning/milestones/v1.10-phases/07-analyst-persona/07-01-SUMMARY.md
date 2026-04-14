---
phase: 07-analyst-persona
plan: 01
subsystem: personas
tags: [personas, hallucination-guard, testing, pydantic-ai, writer-agent]

requires:
  - phase: 06-pipeline-integration-scout-parity-gate
    provides: Persona-aware pipeline factory, generate_pipeline_streaming with persona param
  - phase: 05-persona-module-scaffolding
    provides: Persona dataclass, SCOUT, build_writer_system_prompt, get_persona

provides:
  - ANALYST persona constant with newsletter overlay and parent='scout'
  - Per-persona hallucination guard allowlist mechanism (_PERSONA_KNOWN_METRICS)
  - Analyst smoke test (TEST-05) with TestModel
  - assert_analyst_shape structural validation helper (TEST-06)
  - Hallucination guard regression vectors for analyst vocabulary (TEST-07)

affects: [08-generic-persona, 09-cli-wiring]

tech-stack:
  added: []
  patterns:
    - "Per-persona vocabulary allowlist: _PERSONA_KNOWN_METRICS[persona_id] subtracted from unknown metrics"
    - "Overlay inheritance via parent field: ANALYST.parent='scout' causes scout overlay to compose first"
    - "Shape assertion helper in test file: assert_analyst_shape validates structural constraints on any text"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/personas.py
    - src/pitcher_narratives/pipeline.py
    - tests/test_personas.py
    - tests/test_hallucination_guard.py

key-decisions:
  - "Analyst uses parent='scout' overlay inheritance -- scout overlay composes before analyst overlay, teaching voice adds to not replaces scout discipline"
  - "Per-persona allowlist subtracted at check time, not stored in Persona object -- hallucination guard stays independent of Persona dataclass"
  - "check_hallucinated_metrics persona arg defaults to None -- all existing call sites unchanged, v1.9 backward compat verified"

patterns-established:
  - "Persona overlay composition: SHARED_WRITER_BASE + parent overlay (if any) + own overlay"
  - "Hallucination guard allowlist: _PERSONA_KNOWN_METRICS[persona] frozenset subtracted from found metrics"
  - "assert_analyst_shape helper: reusable structural validator for analyst output (no tables, no bullets, no h1)"

requirements-completed: ["VOICE-02", "PERSONA-10", "TEST-05", "TEST-06", "TEST-07"]

duration: 5min
completed: 2026-04-14
---

# Phase 07 Plan 01: Analyst Persona Summary

**ANALYST persona with newsletter overlay (450-800 words, teaching voice), per-persona hallucination guard allowlist, and full analyst test coverage (smoke test, shape assertion, guard regression vectors)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-14T00:10:54Z
- **Completed:** 2026-04-14T00:16:11Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added ANALYST persona constant with _ANALYST_OVERLAY (newsletter voice, 450-800 words, teaching vocabulary, 800-word hard limit)
- Updated PERSONAS registry to include "analyst" key; ANALYST exports in __all__
- Extended check_hallucinated_metrics with persona: str | None = None parameter and _PERSONA_KNOWN_METRICS allowlist
- Analyst vocabulary (playability, tunneling gap, pitch tree, arsenal depth) allowlisted for persona="analyst"
- 54 tests pass across test_personas.py, test_hallucination_guard.py, test_pipeline_persona_wiring.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Define ANALYST persona constant and update registry** - `233e045` (feat)
2. **Task 2: Add per-persona allowlist to check_hallucinated_metrics** - `241b496` (feat)
3. **Task 3: Add analyst tests (smoke, shape assertion, guard vectors, registry)** - `cea2ddb` (test)

## Files Created/Modified
- `src/pitcher_narratives/personas.py` - _ANALYST_OVERLAY constant, ANALYST persona instance, registry update, __all__ update
- `src/pitcher_narratives/pipeline.py` - _PERSONA_KNOWN_METRICS dict, check_hallucinated_metrics persona param and persona_known subtraction
- `tests/test_personas.py` - ANALYST import, registry test renamed, analyst unit tests, assert_analyst_shape helper, analyst smoke test
- `tests/test_hallucination_guard.py` - 4 analyst regression vector tests (TEST-07)

## Decisions Made
- Analyst uses parent='scout': teaching voice inherits scout's factual discipline rather than replacing it
- Per-persona allowlist in pipeline.py (not Persona dataclass): keeps hallucination guard independent of persona definitions
- check_hallucinated_metrics persona=None default: zero existing call sites need updating

## Deviations from Plan

None - plan executed exactly as written.

The worktree branch was behind main (missing Phase 05/06 work). Resolved via `git rebase main` before task execution. This was an environment setup step, not a plan deviation.

## Issues Encountered
- Worktree branch `worktree-agent-ad8f82eb` was behind `main` and missing personas.py and test_personas.py. Fixed by rebasing onto main before execution.
- Data files (statcast parquet) not in worktree directory; used `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` env var to point to main repo — same approach as Phase 06.
- Pre-existing test failure: `test_pipeline.py::TestAuditAndReviseSpecialists::test_clean_audit_returns_originals` (pydantic-ai TestModel assertion error). Documented in STATE.md; not caused by this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- ANALYST persona is fully registered, tested, and ready for Phase 09 (CLI wiring via --persona analyst)
- Pipeline accepts persona="analyst" in generate_pipeline_streaming today (Phase 06 wired this)
- Phase 08 (generic persona) can follow the same ANALYST pattern: add _GENERIC_OVERLAY, create GENERIC instance with parent=None, register in PERSONAS
- All 54 tests in the persona/guard/wiring test files pass; 364/365 in full suite (1 pre-existing failure)

## Self-Check: PASSED

All files confirmed present. All task commits verified in git history.

---
*Phase: 07-analyst-persona*
*Completed: 2026-04-14*
