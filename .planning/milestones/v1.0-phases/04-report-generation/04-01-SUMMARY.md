---
phase: 04-report-generation
plan: 01
subsystem: report-generation
tags: [pydantic-ai, claude, streaming, agent, prompt-engineering]

# Dependency graph
requires:
  - phase: 03-context-assembly
    provides: PitcherContext model with to_prompt() and role field
provides:
  - pydantic-ai Agent configured for Claude claude-sonnet-4-6
  - scout-voice system prompt with anti-recitation instructions
  - role-conditional user message builder (SP vs RP guidance)
  - generate_report_streaming function for CLI usage
affects: [04-02-cli-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns: [defer_model_check for import-time safety, run_stream_sync for streaming CLI output, TestModel for API-free testing]

key-files:
  created: [report.py, tests/test_report.py]
  modified: []

key-decisions:
  - "Used defer_model_check=True so Agent can be imported without ANTHROPIC_API_KEY (key only needed at runtime)"
  - "Role guidance passed in user message (not system prompt) -- simpler than dynamic instructions callback"
  - "System prompt fixed with persona + anti-recitation; user message carries role-specific analysis focus + data"

patterns-established:
  - "Agent-per-module with function wrapper: module-level Agent, thin function interface"
  - "TestModel override via _model_override kwarg for deterministic testing without API keys"

requirements-completed: [RPT-01, RPT-02, RPT-03, RPT-04]

# Metrics
duration: 2min
completed: 2026-03-26
---

# Phase 04 Plan 01: Report Generation Summary

**Pydantic-ai Agent with claude-sonnet-4-6, scout-voice system prompt, role-conditional SP/RP guidance, and streaming output via run_stream_sync**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-26T20:34:45Z
- **Completed:** 2026-03-26T20:37:18Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Agent configured with claude-sonnet-4-6 model, str output type, max_tokens=4096
- Scout-voice system prompt with anti-recitation ("Write insight, not stat lines") and data-grounding instructions
- SP/RP role-conditional guidance in user message alongside to_prompt() output
- Streaming generation function prints tokens as they arrive for responsive CLI
- 14 new tests all pass using TestModel without ANTHROPIC_API_KEY
- Full test suite 103/103 green

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for report module** - `4127731` (test)
2. **Task 1 GREEN: Implement report.py with Agent and streaming** - `f6541d8` (feat)

## Files Created/Modified
- `report.py` - pydantic-ai Agent, system prompt, _build_user_message, generate_report_streaming
- `tests/test_report.py` - 14 tests covering agent config, prompt content, role guidance, and streaming

## Decisions Made
- Used `defer_model_check=True` so the Agent can be constructed at import time without requiring ANTHROPIC_API_KEY -- the key is only needed at runtime when actually calling Claude
- Role-specific guidance delivered via user message (not dynamic system prompt) -- cleaner separation: system prompt carries persona/anti-recitation, user message carries analysis focus + data
- Streaming via `run_stream_sync` (not a context manager) with `stream_text(delta=True)` for token-by-token output

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added defer_model_check=True to Agent constructor**
- **Found during:** Task 1 GREEN (implementation)
- **Issue:** Agent construction validates API key at import time, causing ImportError in test environments without ANTHROPIC_API_KEY
- **Fix:** Added `defer_model_check=True` parameter to Agent constructor -- defers provider validation to runtime
- **Files modified:** report.py
- **Verification:** All tests pass without ANTHROPIC_API_KEY set
- **Committed in:** f6541d8 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for testability. The research mentioned this option but the plan didn't include it. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviation above.

## User Setup Required
None - no external service configuration required. ANTHROPIC_API_KEY will be needed at runtime (Phase 04 Plan 02 wires CLI integration).

## Next Phase Readiness
- report.py is ready to be imported by main.py
- generate_report_streaming(ctx) accepts PitcherContext, returns report string
- Phase 04 Plan 02 will wire main.py to call generate_report_streaming instead of the temporary verification print

---
*Phase: 04-report-generation*
*Completed: 2026-03-26*
