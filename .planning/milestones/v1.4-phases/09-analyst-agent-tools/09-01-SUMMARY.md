---
phase: 09-analyst-agent-tools
plan: 01
subsystem: agent
tags: [pydantic-ai, tool-calling, RunContext, streaming, pitch-type-mapping]

# Dependency graph
requires:
  - phase: 04-context-assembly
    provides: PitcherContext model with to_prompt() method
  - phase: 01-data-loading
    provides: PitcherData dataclass and load_pitcher_data()
provides:
  - Tool-calling analyst agent module (analyst.py)
  - PITCH_TYPE_MAP constant for synonym resolution
  - QADeps dataclass for dependency injection
  - ask_question_streaming public function for CLI consumption
affects: [10-ask-cli]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tool-calling agent with RunContext[QADeps] dependency injection"
    - "instructions= parameter (not system_prompt=) for multi-turn readiness"
    - "Static synonym map for pitch type resolution"

key-files:
  created:
    - src/pitcher_narratives/analyst.py
    - tests/test_analyst.py
  modified: []

key-decisions:
  - "Used _analyst_agent with model/settings passed at run call site instead of Agent.override() caching (override returns context manager, not agent clone)"
  - "Factory caches (model_name, settings) tuples rather than Agent instances"

patterns-established:
  - "Tool testing via direct function call with MagicMock RunContext"
  - "Agent instructions stored in _instructions list, verified via _instructions[0]"

requirements-completed: [AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06]

# Metrics
duration: 5min
completed: 2026-03-30
---

# Phase 9 Plan 1: Analyst Agent & Tools Summary

**Tool-calling pydantic-ai agent with get_pitcher_summary and get_pitch_detail tools, static PITCH_TYPE_MAP with 12 Statcast codes + 26 synonyms, and streaming output via run_stream_sync**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-30T15:22:24Z
- **Completed:** 2026-03-30T15:27:50Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files created:** 2

## Accomplishments
- PITCH_TYPE_MAP with all 12 Statcast codes (FF, SI, FC, SL, ST, CU, KC, CH, FS, KN, SC, EP) plus 26 synonyms for case-insensitive lookup
- get_pitcher_summary tool returns ctx.deps.context.to_prompt() for broad questions
- get_pitch_detail tool resolves synonyms, filters arsenal/execution/platoon data, renders focused markdown per pitch type
- Missing pitch gracefully returns "No data for" message with available pitches list
- Agent uses instructions= parameter with strict data-grounding directive and out-of-scope handling
- ask_question_streaming with run_stream_sync + stream_text(delta=True) pattern
- 10 new tests, 222 total suite green with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests** - `bb8b1ba` (test)
2. **Task 1 GREEN: Implementation** - `e2e50d7` (feat)

## Files Created/Modified
- `src/pitcher_narratives/analyst.py` - Tool-calling analyst agent module with QADeps, PITCH_TYPE_MAP, two tools, factory, and streaming public function
- `tests/test_analyst.py` - 10 unit tests covering AGENT-01 through AGENT-06

## Decisions Made
- Agent.override() returns a context manager (not an agent clone), so factory caches (model_name, ModelSettings) tuples and passes them at run call site
- Tool functions tested via direct call with MagicMock RunContext (not via TestModel agent run, which would call all tools indiscriminately)
- Instructions verified via _instructions private list since public .instructions is a method, not string attribute

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Agent.override() returns context manager, not Agent**
- **Found during:** Task 1 GREEN phase
- **Issue:** Plan specified `_analyst_agent.override(model=model, model_settings=settings)` to create cached agent clones, but pydantic-ai 1.72's `override()` returns a `_GeneratorContextManager` (context manager), not a new Agent instance
- **Fix:** Changed _make_analyst to cache `(model_name, ModelSettings)` tuples. ask_question_streaming passes model and model_settings directly to `_analyst_agent.run_stream_sync(**kwargs)` at the call site
- **Files modified:** src/pitcher_narratives/analyst.py
- **Verification:** test_ask_question_streaming passes with TestModel
- **Committed in:** e2e50d7

**2. [Rule 3 - Blocking] Tool decorator returns original function, not wrapper with .function**
- **Found during:** Task 1 GREEN phase
- **Issue:** Tests used `get_pitcher_summary.function(mock_ctx)` expecting a wrapper object, but pydantic-ai's `@agent.tool` decorator returns the original function unchanged
- **Fix:** Changed to direct calls: `get_pitcher_summary(mock_ctx)`
- **Files modified:** tests/test_analyst.py
- **Verification:** All 7 tool tests pass
- **Committed in:** e2e50d7

**3. [Rule 3 - Blocking] Agent.instructions is a method, not a string attribute**
- **Found during:** Task 1 GREEN phase
- **Issue:** Test asserted `isinstance(_analyst_agent.instructions, str)`, but pydantic-ai stores instructions in `_instructions` list and exposes a method
- **Fix:** Test checks `_analyst_agent._instructions[0]` is a non-empty string and `_system_prompts` is empty
- **Files modified:** tests/test_analyst.py
- **Verification:** test_agent_uses_instructions_not_system_prompt passes
- **Committed in:** e2e50d7

---

**Total deviations:** 3 auto-fixed (3 blocking issues from pydantic-ai API differences)
**Impact on plan:** All auto-fixes necessary to work with actual pydantic-ai 1.72 API. Core architecture and all requirements delivered as specified.

## Issues Encountered
None beyond the deviation auto-fixes above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- analyst.py exports `ask_question_streaming`, `QADeps`, and `PITCH_TYPE_MAP` for Phase 10 CLI consumption
- Phase 10 (ask_cli.py) can import from `pitcher_narratives.analyst` and wire up resolver + data loading + agent call
- No modifications to any existing module were made

## Self-Check: PASSED

- FOUND: src/pitcher_narratives/analyst.py
- FOUND: tests/test_analyst.py
- FOUND: 09-01-SUMMARY.md
- FOUND: bb8b1ba (RED commit)
- FOUND: e2e50d7 (GREEN commit)

---
*Phase: 09-analyst-agent-tools*
*Completed: 2026-03-30*
