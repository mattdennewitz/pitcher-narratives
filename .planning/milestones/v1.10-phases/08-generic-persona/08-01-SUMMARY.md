---
phase: 08-generic-persona
plan: 01
subsystem: personas
tags: [personas, hallucination-guard, testing, pipeline]

# Dependency graph
requires:
  - phase: 07-analyst-persona
    provides: ANALYST persona, per-persona allowlist pattern, test_personas.py analyst suite
provides:
  - GENERIC persona constant with sectioned + summary-table overlay (parent="scout", length_target=(300, 500))
  - _PERSONA_KNOWN_METRICS["generic"] frozenset entry in pipeline.py
  - assert_generic_shape helper and full generic test suite
  - Registry updated to len==3 with {scout, analyst, generic}
affects: [cli, pipeline, testing, phase-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "STRUCTURE OVERRIDE clause in overlay: child overlays explicitly override parent constraints rather than silently replacing them"
    - "Variable-row summary table in generic overlay: one row per populated KeySignals entry, not a fixed count"
    - "assert_generic_shape helper: structural validator for sectioned+table format, mirrors assert_analyst_shape pattern"

key-files:
  created:
    - tests/test_personas.py (new generic sections appended)
    - tests/test_hallucination_guard.py (new generic guard vectors appended)
  modified:
    - src/pitcher_narratives/personas.py
    - src/pitcher_narratives/pipeline.py

key-decisions:
  - "GENERIC overlay explicitly uses STRUCTURE OVERRIDE language to counteract inherited scout no-headers/no-tables rule"
  - "_PERSONA_KNOWN_METRICS['generic'] = frozenset() (empty): generic vocabulary covered by existing _KNOWN_METRICS; slot reserved for future regex evolution"
  - "assert_generic_shape skips row-count validation when populated_signal_count is None, enabling TestModel smoke test without shape assertion on canned output"

patterns-established:
  - "STRUCTURE OVERRIDE pattern: child persona overlays must include explicit override language when they contradict parent constraints"
  - "Shape assertion helpers (assert_analyst_shape, assert_generic_shape) validate structural constraints without LLM output"

requirements-completed: ["VOICE-03", "PERSONA-10", "TEST-05", "TEST-06", "TEST-07"]

# Metrics
duration: 18min
completed: 2026-04-14
---

# Phase 08 Plan 01: Generic Persona Summary

**GENERIC persona with six-section fixed format and summary table overlay (300-500 words, parent="scout"), per-persona allowlist entry, and full test suite including assert_generic_shape helper and guard regression vectors**

## Performance

- **Duration:** 18 min
- **Started:** 2026-04-14T01:14:00Z
- **Completed:** 2026-04-14T01:32:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Added GENERIC persona constant with `_GENERIC_OVERLAY` fixing six sections in order (Stuff, Location, Run Value & Execution, Trend, Game Shape, Summary Table), STRUCTURE OVERRIDE language permitting `##` headings and one Markdown table, FORBIDDEN h1 clause, and 500-word HARD LIMIT
- Extended `_PERSONA_KNOWN_METRICS` with `"generic": frozenset()` entry satisfying PERSONA-10 (key exists, additive-only)
- Created 20 new tests: registry update (len==3), GENERIC field/prompt/overlay unit tests, `assert_generic_shape` helper with 5 exercisers, TestModel pipeline smoke test, and 5 hallucination guard regression vectors

## Task Commits

Each task was committed atomically:

1. **Task 1: Define GENERIC persona constant and update registry** - `96fd539` (feat)
2. **Task 2: Add "generic" entry to _PERSONA_KNOWN_METRICS allowlist** - `99dd9f1` (feat)
3. **Task 3: Add generic tests — registry update, shape assertion, smoke test, guard vectors** - `161f723` (test)

## Files Created/Modified

- `/Users/matt/src/pitcher-narratives/.claude/worktrees/agent-a4bd7cc7/src/pitcher_narratives/personas.py` - Added `_GENERIC_OVERLAY`, `GENERIC` instance, registry update (len==3), `__all__` update
- `/Users/matt/src/pitcher-narratives/.claude/worktrees/agent-a4bd7cc7/src/pitcher_narratives/pipeline.py` - Added `"generic": frozenset()` to `_PERSONA_KNOWN_METRICS`
- `/Users/matt/src/pitcher-narratives/.claude/worktrees/agent-a4bd7cc7/tests/test_personas.py` - Replaced registry test, added GENERIC unit tests, `assert_generic_shape` helper + 5 exercisers, generic pipeline smoke test
- `/Users/matt/src/pitcher-narratives/.claude/worktrees/agent-a4bd7cc7/tests/test_hallucination_guard.py` - Added 5 generic guard regression vectors

## Decisions Made

- `_GENERIC_OVERLAY` uses explicit `STRUCTURE OVERRIDE` clause: without it the inherited scout overlay's "No bullet points, no headers, no tables. Prose only." would create an ambiguous prompt for the LLM. Override language resolves the contradiction explicitly.
- Empty frozenset for `"generic"` in `_PERSONA_KNOWN_METRICS`: research confirmed generic overlay vocabulary is already covered by `_KNOWN_METRICS` (S+, L+, P+, etc.); no additional tokens needed.
- `assert_generic_shape`'s `populated_signal_count` parameter is optional: TestModel returns canned non-structured output; shape validation on TestModel output would always fail and is not the intent of the smoke test.

## Deviations from Plan

None - plan executed exactly as written.

The only non-plan action was creating data symlinks in the worktree (`statcast_*.parquet`, `aggs/`) to enable the smoke tests to run — the worktree lacked the large untracked data files present in the main repo. This is a worktree infrastructure setup, not a code deviation.

## Issues Encountered

- Worktree was behind main (missing Phase 06/07 commits including `personas.py`). Resolved by merging main into the worktree branch before executing.
- Data files (parquet + aggs) absent from worktree — resolved by symlinking from main repo. Smoke tests pass after symlinks created.
- Pre-existing failure `tests/test_pipeline.py::TestAuditAndReviseSpecialists::test_clean_audit_returns_originals` (pydantic-ai TestModel assertion error) — not caused by this plan, carried forward per STATE.md blockers section.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 08 Plan 02 can proceed: GENERIC persona is fully registered, tested, and the hallucination guard is extended
- CLI wiring (if any) for `--persona generic` is the remaining phase 08 work
- DEFAULT_PERSONA unchanged; no regression risk to existing `--persona scout` users

---
*Phase: 08-generic-persona*
*Completed: 2026-04-14*
