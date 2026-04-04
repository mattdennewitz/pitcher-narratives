---
phase: 25-prompt-engineering-heuristic-injection
plan: 02
subsystem: pipeline
tags: [prompt-engineering, sabermetrics, causal-hook, auditor-whitelist, anti-hallucination]

# Dependency graph
requires:
  - phase: 24-pipeline-re-architecture
    provides: 6-specialist pipeline with writer prompt builder and data auditor prompt
provides:
  - CAUSAL HOOK REQUIREMENT section in writer prompt requiring Stuff Specialist citation for S+ changes >= 10 points
  - ALLOWED HEURISTIC PATTERNS whitelist in auditor prompt evidence-gating inverse correlation, zone expansion, and approach angle patterns
affects: [25-prompt-engineering-heuristic-injection]

# Tech tracking
tech-stack:
  added: []
  patterns: [evidence-gated heuristic whitelist, causal hook honest fallback]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/pipeline.py
    - tests/test_pipeline.py

key-decisions:
  - "Causal hook placed after CONSTRAINTS section, before closing triple-quote — applies to both SP and RP writers"
  - "Auditor whitelist placed immediately before output format instructions for LLM recency effect (D-12)"
  - "Three whitelisted patterns (inverse correlation, zone expansion, approach angle) all gated on evidence citation"

patterns-established:
  - "Evidence-gated whitelist: heuristic patterns valid ONLY when specialist cites specific supporting metrics"
  - "Honest fallback: writer admits uncertainty when Stuff Specialist cannot explain S+ change rather than fabricating"

requirements-completed: [PROMPT-04, PROMPT-05]

# Metrics
duration: 3min
completed: 2026-04-04
---

# Phase 25 Plan 02: Causal Hook & Auditor Whitelist Summary

**Writer causal hook requirement for S+ changes >= 10 points with honest fallback, plus evidence-gated auditor whitelist for inverse correlation, zone expansion, and approach angle patterns**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-04T21:44:34Z
- **Completed:** 2026-04-04T21:48:16Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Writer prompt now requires citing physical drivers from Stuff Specialist for any pitch with S+ change >= 10 points, with honest fallback when change is unexplained
- Auditor prompt whitelists three sabermetric heuristic patterns (inverse correlation, zone expansion, approach angle) but only when evidence is cited — uncited claims still flagged as HALLUCINATED_CAUSATION
- Whitelist correctly placed before output format instructions for recency effect per D-12
- 13 new tests covering all aspects of both prompt modifications

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for writer causal hook and auditor whitelist** - `e4659a4` (test)
2. **Task 2: Implement writer causal hook and auditor whitelist** - `26ab2da` (feat)

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Added CAUSAL HOOK REQUIREMENT section to _build_writer_prompt() and ALLOWED HEURISTIC PATTERNS section to _DATA_AUDITOR_PROMPT
- `tests/test_pipeline.py` - Added TestWriterPromptCausalHook (6 tests) and TestAuditorWhitelist (7 tests)

## Decisions Made
- Causal hook applies to both SP and RP writers (not role-conditional) — large S+ changes need explanation regardless of role
- 10-point S+ threshold hardcoded in prompt text per D-08 (no Python pre-scanning)
- Whitelist evidence gate uses "ONLY when" phrasing to make the conditional crystal clear to the LLM

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all prompt sections are fully wired with complete content.

## Next Phase Readiness
- Writer and auditor prompts ready for Plan 03 (location input restructuring)
- Specialist prompt heuristics from Plan 01 can proceed independently

## Self-Check: PASSED

All files exist. All commits verified.

---
*Phase: 25-prompt-engineering-heuristic-injection*
*Completed: 2026-04-04*
