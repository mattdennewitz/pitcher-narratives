---
phase: 09-analyst-agent-tools
verified: 2026-03-30T16:00:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 9: Analyst Agent Tools Verification Report

**Phase Goal:** Users can ask natural-language questions about a pitcher and receive analytical answers grounded exclusively in the existing data pipeline
**Verified:** 2026-03-30T16:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                    | Status     | Evidence                                                                                  |
| --- | ------------------------------------------------------------------------ | ---------- | ----------------------------------------------------------------------------------------- |
| 1   | Agent has two tools: get_pitcher_summary and get_pitch_detail            | VERIFIED | Both `@_analyst_agent.tool` functions present at lines 138-166 of analyst.py              |
| 2   | get_pitcher_summary returns the full PitcherContext.to_prompt() string   | VERIFIED | Line 141: `return ctx.deps.context.to_prompt()`; test passes with real fixture data       |
| 3   | get_pitch_detail resolves synonyms and filters to one pitch type         | VERIFIED | Lines 151-166 implement synonym lookup via PITCH_TYPE_MAP then arsenal filter; test passes |
| 4   | Asking about a pitch the pitcher doesn't throw returns available pitches | VERIFIED | Lines 159-164 return "No data for..." with available pitches; test_get_pitch_detail_missing_pitch passes |
| 5   | Agent uses instructions parameter (not system_prompt)                    | VERIFIED | Line 133: `instructions=_ANALYST_INSTRUCTIONS`; grep confirms 0 occurrences of system_prompt=; test_agent_uses_instructions_not_system_prompt passes |
| 6   | Agent streams answer to stdout via run_stream_sync                       | VERIFIED | Lines 319-324: `_analyst_agent.run_stream_sync(**kwargs)` + `stream.stream_text(delta=True)` with print per chunk |
| 7   | PITCH_TYPE_MAP covers all 12 Statcast codes plus common synonyms         | VERIFIED | Lines 29-71: all 12 codes (FF, SI, FC, SL, ST, CU, KC, CH, FS, KN, SC, EP) + 26 synonyms; test_pitch_type_map_contains_all_statcast_codes passes |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact                            | Expected                      | Status   | Details                                                                                  |
| ----------------------------------- | ----------------------------- | -------- | ---------------------------------------------------------------------------------------- |
| `src/pitcher_narratives/analyst.py` | Tool-calling analyst agent module | VERIFIED | 326 lines; exports PITCH_TYPE_MAP, QADeps, ask_question_streaming; substantive implementation with no stubs |
| `tests/test_analyst.py`             | Unit tests for analyst agent  | VERIFIED | 192 lines (min_lines: 80); 10 tests, all passing; covers all 6 requirement IDs          |

### Key Link Verification

| From                                | To                                  | Via                              | Status   | Details                                                            |
| ----------------------------------- | ----------------------------------- | -------------------------------- | -------- | ------------------------------------------------------------------ |
| `src/pitcher_narratives/analyst.py` | `src/pitcher_narratives/context.py` | `ctx.deps.context.to_prompt()`   | WIRED  | Line 141 confirmed; PitcherContext imported at line 17             |
| `src/pitcher_narratives/analyst.py` | `src/pitcher_narratives/report.py`  | PROVIDERS and THINKING_LEVELS import | WIRED  | Line 20: `from pitcher_narratives.report import PROVIDERS, THINKING_LEVELS`; PROVIDERS used in _make_analyst at lines 261-276 |
| `src/pitcher_narratives/analyst.py` | `src/pitcher_narratives/data.py`    | PitcherData type in QADeps       | WIRED  | Line 19: `from pitcher_narratives.data import PitcherData`; QADeps field at line 84 |

### Data-Flow Trace (Level 4)

The analyst module does not directly render UI or produce a final display artifact — it assembles text from injected PitcherContext data and passes it to the LLM as tool responses. The data-flow path from real data to tool output was verified via integration tests using a real fixture (TEST_PITCHER = 592155):

| Artifact               | Data Variable        | Source                                | Produces Real Data | Status    |
| ---------------------- | -------------------- | ------------------------------------- | ------------------ | --------- |
| `get_pitcher_summary`  | `ctx.deps.context`   | `assemble_pitcher_context(data)` fixture | Yes (pitcher name, "Scouting Context" in result) | FLOWING |
| `get_pitch_detail`     | `pc.arsenal`, `pc.execution`, `pc.platoon_mix.splits` | Real PitcherContext fixture | Yes (pitch_name in result for known pitch type) | FLOWING |
| `ask_question_streaming` | `stream.stream_text(delta=True)` | TestModel in test; real model at runtime | Yes (non-empty string returned) | FLOWING |

### Behavioral Spot-Checks

| Behavior                                        | Command                                                      | Result                   | Status |
| ----------------------------------------------- | ------------------------------------------------------------ | ------------------------ | ------ |
| Module imports cleanly                          | `uv run python -c "from pitcher_narratives.analyst import ask_question_streaming, QADeps, PITCH_TYPE_MAP"` | "import OK"              | PASS |
| All 10 analyst tests pass                       | `uv run pytest tests/test_analyst.py -x -v`                  | 10 passed, 0 failed      | PASS |
| Full 222-test suite green (no regressions)      | `uv run pytest tests/ -x -q`                                 | 222 passed, 1 warning    | PASS |
| PITCH_TYPE_MAP has 12 Statcast codes            | `grep -c "PITCH_TYPE_MAP"` + test                            | Values confirmed         | PASS |
| `system_prompt=` not used                       | `grep -c "system_prompt=" src/pitcher_narratives/analyst.py`  | 0 occurrences            | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description                                                                                     | Status    | Evidence                                                                                  |
| ----------- | ----------- | ----------------------------------------------------------------------------------------------- | --------- | ----------------------------------------------------------------------------------------- |
| AGENT-01    | 09-01-PLAN  | Tool-calling pydantic-ai agent answers questions using only provided pitcher data               | SATISFIED | `_analyst_agent` with `instructions=_ANALYST_INSTRUCTIONS` containing strict data-grounding rules; instructions forbid training-data citations |
| AGENT-02    | 09-01-PLAN  | Agent has `get_pitcher_summary` tool returning full PitcherContext for broad questions          | SATISFIED | `get_pitcher_summary` at line 138; returns `ctx.deps.context.to_prompt()`; test_get_pitcher_summary_returns_context passes |
| AGENT-03    | 09-01-PLAN  | Agent has `get_pitch_detail` tool returning focused arsenal/execution/platoon data for a pitch  | SATISFIED | `get_pitch_detail` at line 144; synonym resolution + multi-list filtering; _render_pitch_detail builds structured markdown; 4 tests pass |
| AGENT-04    | 09-01-PLAN  | Agent declines questions about data it doesn't have                                             | SATISFIED | `_ANALYST_INSTRUCTIONS` lines 101-121 explicitly list out-of-scope topics and instruct graceful decline; data grounding rules 1-3 enforced |
| AGENT-05    | 09-01-PLAN  | Pitch type extraction maps natural language to Statcast codes                                   | SATISFIED | PITCH_TYPE_MAP with 38 entries (12 codes + 26 synonyms); test_pitch_type_map_contains_all_statcast_codes and test_pitch_type_map_synonyms both pass |
| AGENT-06    | 09-01-PLAN  | Agent streams answer to stdout as it generates                                                  | SATISFIED | Lines 319-324: `run_stream_sync` + `stream_text(delta=True)` + `print(delta, end="", flush=True)`; test_ask_question_streaming passes |

No orphaned requirements — all 6 IDs claimed in the plan frontmatter are accounted for. REQUIREMENTS.md confirms all 6 are mapped to Phase 9 with status "Complete".

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| None found | — | — | — | — |

No TODO/FIXME/PLACEHOLDER comments, no stub implementations, no hardcoded empty returns, no console.log-only handlers found in either artifact.

### Human Verification Required

None. All must-haves are verifiable programmatically. The agent's grounding behavior (AGENT-01/AGENT-04) is enforced by static instruction text that was inspected directly. Runtime LLM behavior with a real model is deferred to Phase 10 integration testing.

### Gaps Summary

No gaps. All 7 must-have truths verified, both artifacts are substantive and wired, all 3 key links confirmed present in source, all 6 requirements satisfied with direct evidence. The full test suite (222 tests) passes with zero regressions.

**Notable deviation from plan** (auto-fixed, no impact on correctness): `_make_analyst` returns a `(model_name, ModelSettings)` tuple rather than an `Agent` clone because `Agent.override()` in pydantic-ai 1.72 returns a context manager, not an agent instance. The tuple is passed at the call site in `ask_question_streaming` instead. All requirements are still fully met and the streaming behavior is identical.

---

_Verified: 2026-03-30T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
