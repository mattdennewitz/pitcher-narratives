---
phase: 05-persona-module-scaffolding
plan: 01
subsystem: personas
tags: [frozen-dataclass, prompt-decomposition, personas, writer-agent, byte-identity]

# Dependency graph
requires: []
provides:
  - "Persona frozen dataclass with id, display_name, description, overlay, length_target, parent"
  - "SHARED_WRITER_BASE constant (analytical contract, no voice words, EXPLAIN THE MODEL)"
  - "SCOUT persona with overlay capturing v1.9 scout voice"
  - "PERSONAS registry and get_persona lookup"
  - "build_writer_system_prompt composer with parent overlay inheritance"
  - "DEFAULT_PERSONA = PERSONAS['scout']"
  - "Frozen fixture at tests/fixtures/writer_prompt_scout.txt"
  - "13 contract tests covering byte-identity, no-voice-words, explainer-section, frozen dataclass"
affects: [06-pipeline-integration, 07-analyst-persona, 08-generic-persona, 09-cli-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Frozen dataclass for immutable persona configuration"
    - "Module-level dict registry with typed lookup function"
    - "String concatenation composer (base + overlay) with parent inheritance"
    - "Byte-identity fixture testing for prompt regression gates"
    - "Voice word exclusion testing on shared base"

key-files:
  created:
    - src/pitcher_narratives/personas.py
    - tests/fixtures/writer_prompt_scout.txt
    - tests/test_personas.py
  modified: []

key-decisions:
  - "Resolution 1 for PERSONA-06 vs VOICE-01 tension: fixture captures composed scout prompt (base + overlay with EXPLAIN THE MODEL), not raw v1.9 _WRITER_PROMPT"
  - "Rewrote 'Stuff analysis' to 'Pitch quality analysis' in SHARED_WRITER_BASE to satisfy no-voice-words constraint"
  - "CRITICAL section appears in both base (reworded, no voice words) and scout overlay (original v1.9 voice-word items) -- intentional dual-presence for analytical contract + scout flavor"

patterns-established:
  - "Persona module pattern: frozen dataclass + registry dict + composer function"
  - "Prompt decomposition: analytical contract in base, voice/structure in overlay"
  - "Byte-identity fixture gate: build_writer_system_prompt(SCOUT) == fixture"

requirements-completed: [PERSONA-01, PERSONA-02, PERSONA-03, PERSONA-04, PERSONA-05, PERSONA-06, VOICE-01, TEST-01, TEST-02, TEST-03, TEST-04]

# Metrics
duration: 6min
completed: 2026-04-12
---

# Phase 05 Plan 01: Persona Module Scaffolding Summary

**Persona frozen dataclass, SHARED_WRITER_BASE extraction from v1.9 _WRITER_PROMPT, SCOUT overlay with byte-identity fixture gate, and 13 contract tests**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-12T15:57:25Z
- **Completed:** 2026-04-12T16:03:43Z
- **Tasks:** 2/2
- **Files created:** 3

## Accomplishments
- Created `personas.py` with Persona frozen dataclass, 6 public exports, and clean decomposition of the v1.9 `_WRITER_PROMPT` into `SHARED_WRITER_BASE` (analytical contract) + `_SCOUT_OVERLAY` (voice and structure)
- `SHARED_WRITER_BASE` contains the new "EXPLAIN THE MODEL" instruction and zero scout-specific voice words (stuff, feel, groove, tagged, elite, massive)
- Frozen fixture `tests/fixtures/writer_prompt_scout.txt` captures the canonical composed scout prompt for byte-identity regression testing
- 13 contract tests all pass: frozen dataclass, scout fields, default persona identity, get_persona lookup and error handling, fixture existence, byte-identity gate, no-voice-words, explainer section, overlay voice check, all exports, registry completeness, composition structure

## Task Commits

Each task was committed atomically:

1. **Task 1: Create personas.py module and frozen fixture** - `6320664` (feat)
2. **Task 2: Create test_personas.py contract tests** - `846c6db` (test)

## Files Created/Modified
- `src/pitcher_narratives/personas.py` - Persona dataclass, SHARED_WRITER_BASE, SCOUT overlay, PERSONAS registry, get_persona, build_writer_system_prompt, DEFAULT_PERSONA
- `tests/fixtures/writer_prompt_scout.txt` - Frozen byte-identity fixture for composed scout prompt (4,507 bytes)
- `tests/test_personas.py` - 13 contract tests covering all Phase 05 requirements

## Decisions Made
- **Resolution 1 for PERSONA-06 vs VOICE-01 tension:** The frozen fixture captures the COMPOSED scout prompt (SHARED_WRITER_BASE + scout overlay), which includes the new "EXPLAIN THE MODEL" section. The fixture is NOT byte-identical to the raw v1.9 `_WRITER_PROMPT` -- it is the canonical v1.10 scout prompt. TEST-01's "v1.9 verbatim" is interpreted as "the fixture is the canonical scout prompt for this milestone."
- **Rewrote "Stuff analysis" to "Pitch quality analysis" in base:** The INPUT section's "1. Stuff analysis" was reworded to "1. Pitch quality analysis" in SHARED_WRITER_BASE to satisfy TEST-03 (no voice words in base). The original "Stuff analysis" wording is preserved in the scout overlay.
- **Dual CRITICAL items:** The base CRITICAL section has reworded versions of the "Find the thread" and "Drop what's redundant" bullets (using "pitch characteristics" and "grades out well" instead of "stuff" and "elite"). The scout overlay includes the original v1.9 wording of those same items, intentionally providing both the neutral analytical contract and the scout-flavored voice.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Rewrote "Stuff analysis" in INPUT section**
- **Found during:** Task 1 (personas.py creation)
- **Issue:** Plan says Section 2 (INPUT list) goes to SHARED_WRITER_BASE as-is, but "1. Stuff analysis" contains the banned voice word "stuff" which would fail TEST-03
- **Fix:** Rewrote to "1. Pitch quality analysis" -- preserves the meaning while satisfying the no-voice-words constraint
- **Files modified:** src/pitcher_narratives/personas.py
- **Verification:** `assert 'stuff' not in SHARED_WRITER_BASE.lower()` passes
- **Committed in:** 6320664 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Necessary for TEST-03 to pass. The plan's Section 2 decomposition did not account for "Stuff analysis" containing a banned voice word. The reword is minimal and preserves semantics.

## Issues Encountered

None -- both tasks executed cleanly following TDD RED-GREEN flow.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `personas.py` is complete with all 6 public exports ready for Phase 06 pipeline integration
- Phase 06 can import `Persona`, `PERSONAS`, `DEFAULT_PERSONA`, `SHARED_WRITER_BASE`, `build_writer_system_prompt`, `get_persona` directly
- Phase 06 will replace `_WRITER_PROMPT` in pipeline.py with `build_writer_system_prompt(persona)` call
- All 13 contract tests serve as regression gates for future phases (07-analyst, 08-generic, 09-CLI)

## Self-Check: PASSED

- FOUND: src/pitcher_narratives/personas.py
- FOUND: tests/fixtures/writer_prompt_scout.txt
- FOUND: tests/test_personas.py
- FOUND: .planning/phases/05-persona-module-scaffolding/05-01-SUMMARY.md
- FOUND: commit 6320664
- FOUND: commit 846c6db

---
*Phase: 05-persona-module-scaffolding*
*Completed: 2026-04-12*
