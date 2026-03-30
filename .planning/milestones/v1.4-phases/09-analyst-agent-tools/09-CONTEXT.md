# Phase 9: Analyst Agent & Tools - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `analyst.py` — a tool-calling pydantic-ai agent that answers natural-language questions about pitchers. The agent has two tools (`get_pitcher_summary`, `get_pitch_detail`) that return data from the existing pipeline. Includes a static pitch-type mapping dictionary and streaming output. This module is consumed by the Phase 10 CLI.

</domain>

<decisions>
## Implementation Decisions

### Agent Architecture
- Tool-calling agent (not pre-assembled context) — agent decides which tool to call based on the question
- `RunContext[QADeps]` dependency injection — pass loaded PitcherData and PitcherContext through context; tools access it without re-loading
- Use `instructions` parameter (not `system_prompt`) — excludes from message history, making multi-turn a future freebie
- Output type: `str` — free-form analytical prose, same as report pipeline

### Tool Design
- `get_pitcher_summary` returns `PitcherContext.to_prompt()` string (~544 tokens) — proven format, agent cites directly
- `get_pitch_detail` returns filtered markdown: arsenal row + execution row + platoon splits + P+/S+/L+ for that specific pitch type only (~200 tokens)
- Static pitch-type mapping dictionary covering all Statcast codes: FF, SI, FC, SL, ST, CU, KC, CH, FS, KN, SC, EP + common synonyms ("fastball"→FF, "curve"→CU, "sweeper"→ST, "knuckle curve"→KC, "changeup"→CH, "cutter"→FC, "sinker"→SI, "slider"→SL, "splitter"→FS)
- If user asks about a pitch the pitcher doesn't throw, tool returns "No data for [pitch type] in [pitcher]'s arsenal. Available pitches: [list]"

### Grounding & Voice
- Strict data grounding — "Answer ONLY from the data provided. Never cite stats from training data."
- Analytical scout voice — same pragmatic, specific tone as the report pipeline. Cite numbers naturally, explain in plain language.
- Answer length: 2-4 paragraphs for broad questions, 1-2 for specific pitch questions — proportional to data scope
- Out-of-scope handling: explain what data IS available rather than just "I can't answer that"

### Claude's Discretion
- Exact system prompt wording (grounding instructions, voice calibration)
- QADeps dataclass field names
- Internal helper decomposition for pitch-detail rendering
- Test strategy (TestModel mocking vs integration)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `report.py` has `PROVIDERS` dict and `THINKING_LEVELS` list — reuse directly for multi-provider support
- `report.py` uses `Agent(model, ..., result_type=str)` pattern with `run_stream_sync` — same pattern for Q&A
- `context.py` has `PitcherContext.to_prompt()` returning ~544 token markdown — reuse for `get_pitcher_summary` tool
- `context.py` has `assemble_pitcher_context(pitcher_data)` — reuse to build context from loaded data
- `data.py` has `load_pitcher_data(pitcher_id, lookback_window)` — reuse to load pitcher data
- `engine.py` has all compute functions returning typed dataclasses — reuse for `get_pitch_detail` filtering
- `resolver.py` (Phase 8) has `resolve(query)` returning `ResolveResult` — consumed by Phase 10 CLI, not directly by this module

### Established Patterns
- Agents use `CachePoint` for prefix caching on reusable prompt segments
- `_make_agents()` factory creates agents per provider/thinking combo, cached in module-level dict
- `ModelSettings` with `thinking` parameter for configurable thinking effort
- Google models use `GoogleModelSettings` subclass
- Streaming via `agent.run_stream_sync(prompt)` with `async for chunk in result.stream_text(): print(chunk, end="", flush=True)`

### Integration Points
- New file: `src/pitcher_narratives/analyst.py`
- Imports from: `context.py` (PitcherContext, assemble_pitcher_context), `data.py` (load_pitcher_data, PitcherData), `report.py` (PROVIDERS, THINKING_LEVELS)
- Consumed by: Phase 10 CLI (`ask_cli.py`)
- Does NOT modify any existing module

</code_context>

<specifics>
## Specific Ideas

- The agent needs PitcherContext pre-loaded before the agent runs — the CLI (Phase 10) will handle loading data and passing it via RunContext deps
- `get_pitch_detail` should render a focused markdown section per pitch type by filtering PitcherContext's arsenal, execution, and platoon_mix lists
- Reuse `PROVIDERS` and `THINKING_LEVELS` from report.py rather than duplicating

</specifics>

<deferred>
## Deferred Ideas

- Cross-pitcher comparison tools (`search_pitchers`, `compare_metric`, `get_leaderboard`) — deferred to v1.5
- Multi-turn conversation with message history — deferred to v1.5

</deferred>
