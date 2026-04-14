---
phase: 06-pipeline-integration-scout-parity-gate
plan: 01
subsystem: pipeline
tags: [personas, pipeline, pydantic-ai, writer-agent, byte-parity]

requires:
  - phase: 05-persona-module-scaffolding
    provides: Persona dataclass, SCOUT, build_writer_system_prompt, get_persona, frozen fixture

provides:
  - Persona-aware pipeline factory (make_pipeline_agents accepts Persona)
  - Persona-threaded entry points (_run_pipeline, generate_pipeline_streaming accept persona string)
  - Scout byte-parity gate through full pipeline integration path
  - 5 pipeline integration tests in test_personas.py

affects: [07-analyst-persona, 08-generic-persona, 09-cli-wiring]

tech-stack:
  added: []
  patterns:
    - "Persona object accepted at factory level (make_pipeline_agents), string accepted at entry points"
    - "String-to-object resolution at boundary: get_persona(persona) in _run_pipeline"
    - "build_writer_system_prompt(persona) replaces hardcoded _WRITER_PROMPT constant"

key-files:
  created:
    - tests/test_pipeline_persona_wiring.py
  modified:
    - src/pitcher_narratives/pipeline.py
    - tests/test_signals.py
    - tests/test_personas.py

key-decisions:
  - "Persona object at factory, string at entry points -- factory callers (analyst.py) pass Persona directly, CLI callers pass string for simplicity"
  - "DEFAULT_PERSONA used in _render_pipeline_data_sections for data file writer prompt display (not parameterized)"

patterns-established:
  - "String-to-object resolution at boundary: public API accepts str, resolves to Persona internally"
  - "Writer prompt composed at agent creation time, not stored as module constant"

requirements-completed: [PERSONA-07, PERSONA-08, PERSONA-09, "TEST-05 (scout portion)"]

duration: 13min
completed: 2026-04-12
---

# Phase 06 Plan 01: Pipeline Integration & Scout Parity Gate Summary

**Persona-aware pipeline factory with _WRITER_PROMPT deleted, scout byte-parity verified through full pipeline path via TestModel smoke test**

## Performance

- **Duration:** 13 min
- **Started:** 2026-04-12T16:53:02Z
- **Completed:** 2026-04-12T17:06:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Deleted _WRITER_PROMPT constant (75 lines) from pipeline.py, replaced with build_writer_system_prompt(persona) call
- make_pipeline_agents accepts Persona with DEFAULT_PERSONA default, backward compatible with analyst.py:618
- _run_pipeline and generate_pipeline_streaming accept persona string with "scout" default, resolved via get_persona
- 5 pipeline integration tests verify byte-parity, prompt wiring, and full TestModel smoke test
- test_signals.py updated to import from personas module instead of deleted pipeline constant

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire persona through pipeline.py and fix test_signals.py import** - `231418e` (feat)
2. **Task 2: Add pipeline integration tests for scout persona parity** - `8f0eb59` (test)

_Note: TDD tasks also had RED-phase test commits prior to implementation_

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Persona imports, _WRITER_PROMPT deleted, make_pipeline_agents/generate_pipeline_streaming/run_pipeline accept persona parameter
- `tests/test_signals.py` - TestWriterPromptKeySignals updated to import from personas module
- `tests/test_personas.py` - 5 new pipeline integration tests appended (deletion, parity, wiring, fixture, smoke)
- `tests/test_pipeline_persona_wiring.py` - TDD RED-phase validation tests (5 tests)

## Decisions Made
- Persona object at factory level, string at entry points: analyst.py passes Persona directly; CLI callers will pass string for simplicity
- DEFAULT_PERSONA used in _render_pipeline_data_sections since data file display is not persona-parameterized (informational only)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Data files (statcast parquet) not present in worktree; used PITCHER_NARRATIVES_DATA_DIR env var to point to main repo for smoke tests
- Pre-existing test failures (test_analyst.py broken import, test_pipeline.py TestModel assertion error) documented in STATE.md -- not caused by this plan

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Pipeline is persona-aware and ready for Phase 07 (analyst persona) and Phase 08 (generic persona)
- make_pipeline_agents(provider, thinking, ANALYST) will work once ANALYST persona is defined
- CLI wiring (Phase 09) can thread persona string through to generate_pipeline_streaming(ctx, persona="analyst")
- All 352 tests pass (excluding 2 known pre-existing failures)

---
*Phase: 06-pipeline-integration-scout-parity-gate*
*Completed: 2026-04-12*
