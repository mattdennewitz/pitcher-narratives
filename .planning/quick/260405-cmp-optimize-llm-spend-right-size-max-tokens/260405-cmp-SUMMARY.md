---
phase: quick
plan: 260405-cmp
subsystem: llm-config
tags: [pydantic-ai, token-budget, thinking-effort, cost-optimization]

provides:
  - "TOKEN_BUDGET_SMALL/MEDIUM/LARGE constants for role-based max_tokens"
  - "cap_thinking() helper for role-based thinking effort ceilings"
  - "_make_qa_agent() dynamic factory replacing hardcoded analyst singleton"
affects: [pipeline, report, analyst, ask-cli]

tech-stack:
  added: []
  patterns: ["Role-based token budgets: small=1024, medium=2048, large=4096", "Thinking caps per agent role via cap_thinking()"]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/config.py
    - src/pitcher_narratives/pipeline.py
    - src/pitcher_narratives/report.py
    - src/pitcher_narratives/analyst.py
    - src/pitcher_narratives/ask_cli.py

key-decisions:
  - "Budget tiers: 1024 (anchor/auditor/summary), 2048 (specialists), 4096 (writer/editor/answerer/stuff-explainer)"
  - "Thinking caps: checker=low, specialist=medium, writer/answerer=uncapped"
  - "QA agent temperature set to 0.3 (was 1.0) for grounded analytical output"
  - "pitcher-ask CLI default thinking lowered from high to medium"

patterns-established:
  - "Token budget constants: use TOKEN_BUDGET_SMALL/MEDIUM/LARGE from config.py for all agent max_tokens"
  - "cap_thinking pattern: call cap_thinking(user_level, role_ceiling) before make_model_settings"

requirements-completed: []

duration: 4min
completed: 2026-04-05
---

# Quick 260405-cmp: Optimize LLM Spend Summary

**Right-sized max_tokens per agent role (1024/2048/4096), capped thinking effort by role, replaced hardcoded analyst singleton with dynamic factory, lowered ask CLI default thinking to medium**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-05T13:13:42Z
- **Completed:** 2026-04-05T13:17:30Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Token budgets prevent all 10+ agents from requesting 16384 max_tokens when most produce short output
- Thinking effort is capped per role so checkers/auditors don't burn extended reasoning tokens
- analyst.py QA agent now respects the caller's provider and thinking level instead of being hardcoded to openai:gpt-5.4-mini
- OpenAI branch in make_model_settings now passes max_tokens (was silently ignored)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add token budget constants, cap_thinking helper, fix OpenAI max_tokens** - `b721cbb` (feat)
2. **Task 2: Wire token budgets and thinking caps into pipeline, report, ask CLI** - `0c48f24` (feat)
3. **Task 3: Refactor analyst.py -- replace hardcoded singleton with dynamic factory** - `3c7bf6b` (refactor)

## Files Created/Modified
- `src/pitcher_narratives/config.py` - Added TOKEN_BUDGET_SMALL/MEDIUM/LARGE constants, cap_thinking() helper, fixed OpenAI max_tokens passthrough
- `src/pitcher_narratives/pipeline.py` - Wired role-based token budgets and thinking caps into make_pipeline_agents()
- `src/pitcher_narratives/report.py` - Wired role-based token budgets and thinking caps into _make_agents()
- `src/pitcher_narratives/analyst.py` - Replaced hardcoded _analyst_agent singleton with _make_qa_agent() cached factory
- `src/pitcher_narratives/ask_cli.py` - Changed --thinking default from high to medium

## Decisions Made
- Budget tiers: 1024 for short structured output (anchor, auditor, exec summary), 2048 for moderate analysis (specialists), 4096 for long-form prose (writer, editor, answerer, stuff explainer)
- QA agent temperature changed from 1.0 to 0.3 to match grounded analytical role
- Pipeline summary agent gets its own settings (TOKEN_BUDGET_SMALL) instead of sharing specialist settings

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] QA agent temperature was 1.0, changed to 0.3**
- **Found during:** Task 3
- **Issue:** The old _make_analyst() used temperature 1.0 for the QA agent. This is unnecessarily creative for a data-grounded analyst that should cite specific numbers.
- **Fix:** Set temperature to 0.3 in _make_qa_agent() to match the analyst role's precision requirement.
- **Files modified:** src/pitcher_narratives/analyst.py
- **Verification:** Factory constructs successfully for all providers
- **Committed in:** 3c7bf6b (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Temperature fix aligns QA agent with grounded analytical purpose. No scope creep.

## Issues Encountered
None

## Known Stubs
None

## Next Phase Readiness
- All agent factories construct without error for all three providers
- Token budget and thinking cap patterns established for future agents

---
*Plan: quick-260405-cmp*
*Completed: 2026-04-05*

## Self-Check: PASSED

All 5 modified files exist. All 3 task commits verified (b721cbb, 0c48f24, 3c7bf6b). SUMMARY.md exists.
