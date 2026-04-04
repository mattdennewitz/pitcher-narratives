---
phase: 25-prompt-engineering-heuristic-injection
plan: 01
subsystem: pipeline
tags: [prompts, heuristics, specialist-agents, trade-offs, release-point]

# Dependency graph
requires:
  - phase: 24-pipeline-re-architecture
    provides: "6-specialist pipeline with approach agent, _build_writer_prompt pattern"
  - phase: 23-engine-foundation-data-enrichment
    provides: "ReleasePointMetrics with arm angle data, PitcherContext.release_point field"
provides:
  - "TRADE-OFF DETECTION directive in Stuff specialist prompt"
  - "CONTRADICTION DETECTION directive in Location specialist prompt"
  - "_build_trend_prompt(ctx) function with conditional RELEASE POINT FRAMING"
  - "ctx parameter on make_pipeline_agents for context-aware prompt building"
affects: [25-02-PLAN, 25-03-PLAN, prompt-engineering-heuristic-injection]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hybrid principle+examples directive format for heuristic injection"
    - "Conditional prompt section injection via Python function (not LLM conditional)"

key-files:
  created: []
  modified:
    - "src/pitcher_narratives/pipeline.py"
    - "tests/test_pipeline.py"

key-decisions:
  - "Used hybrid principle+examples format for all heuristic directives per D-02"
  - "Made _build_trend_prompt accept PitcherContext | None for backward compatibility"
  - "Conditional release-point vocabulary injected at Python level, not LLM-side"

patterns-established:
  - "Heuristic directive pattern: SECTION HEADER + governing principle + COMMON PATTERNS enumeration"
  - "Dynamic prompt function pattern: _build_X_prompt(ctx) with None-safe conditional sections"

requirements-completed: [PROMPT-01, PROMPT-02, PROMPT-03]

# Metrics
duration: 7min
completed: 2026-04-04
---

# Phase 25 Plan 01: Specialist Prompt Heuristics Summary

**Stuff/Location/Trend specialist prompts now encode sabermetric trade-off, contradiction, and release-point vocabulary directives**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-04T21:44:15Z
- **Completed:** 2026-04-04T21:51:30Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Stuff specialist prompt detects and narrates INVERSE velo/S+ trade-offs with pfx delta citations
- Location specialist prompt detects zone expansion contradictions (low zone% + high xWhiff) with chase% confirmation
- Trend specialist prompt dynamically includes release-point vocabulary only when arm angle data is present
- make_pipeline_agents accepts optional ctx for context-aware prompt building (backward-compatible)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for specialist prompt heuristics** - `a668584` (test)
2. **Task 2: Implement specialist prompt heuristics and trend function conversion** - `3399882` (feat)

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Added TRADE-OFF DETECTION to stuff prompt, CONTRADICTION DETECTION to location prompt, converted _TREND_SPECIALIST_PROMPT to _build_trend_prompt(ctx) function, updated 3 call sites
- `tests/test_pipeline.py` - Added 4 test classes (15 tests): TestStuffPromptHeuristics, TestLocationPromptHeuristics, TestTrendPromptFunction, TestMakePipelineAgentsCtx

## Decisions Made
- Used hybrid principle+examples format (D-02) consistently across all three directives
- Made _build_trend_prompt accept PitcherContext | None (not just PitcherContext) so backward compatibility is preserved for callers without ctx
- Conditional release-point vocabulary is injected at Python level, avoiding LLM conditional branches about absent data (D-05)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 25-02-PLAN ready: writer causal hook (D-07/D-08/D-09) and auditor whitelist (D-10/D-11/D-12) build on the same prompt modification pattern
- 25-03-PLAN ready: location input restructuring (D-04) is independent of prompt changes
- All 112 pipeline tests passing, no regressions

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 25-prompt-engineering-heuristic-injection*
*Completed: 2026-04-04*
