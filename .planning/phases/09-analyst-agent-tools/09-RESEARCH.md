# Phase 9: Analyst Agent & Tools - Research

**Researched:** 2026-03-30
**Domain:** pydantic-ai tool-calling agents, RunContext dependency injection, streaming output
**Confidence:** HIGH

## Summary

Phase 9 builds `analyst.py` -- a single new module containing a pydantic-ai tool-calling agent that answers natural-language questions about a pitcher using two tools: `get_pitcher_summary` (broad context) and `get_pitch_detail` (single-pitch-type focus). The agent uses `RunContext[QADeps]` dependency injection to access pre-loaded `PitcherContext` and `PitcherData` without re-loading. This is the first agent in the project with tools -- all existing agents in `report.py` are prompt-only agents with no tools.

The implementation follows established project patterns exactly: `PROVIDERS` dict, `THINKING_LEVELS` list, `output_type=str`, `run_stream_sync()` without context manager, `stream_text(delta=True)` for streaming. The key new elements are the `@agent.tool` decorator with `RunContext[QADeps]`, the `instructions` parameter instead of `system_prompt`, and a static pitch-type synonym mapping dictionary.

**Primary recommendation:** Build a single `analyst.py` module with one `Agent` instance, two `@agent.tool`-decorated functions, a `QADeps` dataclass, a `PITCH_TYPE_MAP` constant, and an `ask_question_streaming()` public function. Follow the `_make_agents()` caching pattern from `report.py` for multi-provider support.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Tool-calling agent (not pre-assembled context) -- agent decides which tool to call based on the question
- `RunContext[QADeps]` dependency injection -- pass loaded PitcherData and PitcherContext through context; tools access it without re-loading
- Use `instructions` parameter (not `system_prompt`) -- excludes from message history, making multi-turn a future freebie
- Output type: `str` -- free-form analytical prose, same as report pipeline
- `get_pitcher_summary` returns `PitcherContext.to_prompt()` string (~544 tokens) -- proven format, agent cites directly
- `get_pitch_detail` returns filtered markdown: arsenal row + execution row + platoon splits + P+/S+/L+ for that specific pitch type only (~200 tokens)
- Static pitch-type mapping dictionary covering all Statcast codes: FF, SI, FC, SL, ST, CU, KC, CH, FS, KN, SC, EP + common synonyms ("fastball"->FF, "curve"->CU, "sweeper"->ST, "knuckle curve"->KC, "changeup"->CH, "cutter"->FC, "sinker"->SI, "slider"->SL, "splitter"->FS)
- If user asks about a pitch the pitcher doesn't throw, tool returns "No data for [pitch type] in [pitcher]'s arsenal. Available pitches: [list]"
- Strict data grounding -- "Answer ONLY from the data provided. Never cite stats from training data."
- Analytical scout voice -- same pragmatic, specific tone as the report pipeline
- Answer length: 2-4 paragraphs for broad questions, 1-2 for specific pitch questions
- Out-of-scope handling: explain what data IS available rather than just "I can't answer that"

### Claude's Discretion
- Exact system prompt wording (grounding instructions, voice calibration)
- QADeps dataclass field names
- Internal helper decomposition for pitch-detail rendering
- Test strategy (TestModel mocking vs integration)

### Deferred Ideas (OUT OF SCOPE)
- Cross-pitcher comparison tools (`search_pitchers`, `compare_metric`, `get_leaderboard`) -- deferred to v1.5
- Multi-turn conversation with message history -- deferred to v1.5
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGENT-01 | Tool-calling agent answers questions using only provided pitcher data (no hallucination) | Agent `instructions` with strict grounding directive; tools return only PitcherContext-derived data; no external data access |
| AGENT-02 | Agent has `get_pitcher_summary` tool returning full PitcherContext for broad questions | `@agent.tool` returning `ctx.deps.context.to_prompt()` string |
| AGENT-03 | Agent has `get_pitch_detail` tool returning focused data for a specific pitch type | `@agent.tool` with `pitch_type: str` parameter, filters PitcherContext.arsenal/execution/platoon_mix by pitch_type code |
| AGENT-04 | Agent declines questions about data it doesn't have | Instructions directive listing out-of-scope topics; out-of-scope handler returns available data description |
| AGENT-05 | Pitch type extraction maps natural language to Statcast codes | Static `PITCH_TYPE_MAP` dict with synonym resolution before tool call |
| AGENT-06 | Agent streams answer to stdout as it generates | `run_stream_sync()` + `stream_text(delta=True)` pattern from report.py |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-ai | 1.72.0 | Agent framework with tool-calling, RunContext, streaming | Already in pyproject.toml, all existing agents use it |
| pydantic | 2.12.5 | Data validation for QADeps and PitcherContext | Transitive via pydantic-ai, used throughout project |
| polars | 1.39.3 | Not directly used in analyst.py, but PitcherContext is built from it | Upstream dependency via data.py and engine.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic_ai.models.test.TestModel | 1.72.0 | Deterministic testing without API calls | All unit tests -- TestModel calls all tools by default |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Static PITCH_TYPE_MAP dict | LLM-based pitch name extraction | Dict is instant, deterministic, zero-cost; LLM adds latency and cost for a lookup problem |
| `instructions` param | `system_prompt` param | `instructions` excludes from message_history, enabling multi-turn in v1.5 without rework |

**Installation:**
No new packages needed -- all dependencies already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure
```
src/pitcher_narratives/
    analyst.py         # NEW: Agent, tools, QADeps, PITCH_TYPE_MAP, ask_question_streaming()
    context.py         # EXISTING: PitcherContext, assemble_pitcher_context (read-only)
    data.py            # EXISTING: load_pitcher_data, PitcherData (read-only)
    report.py          # EXISTING: PROVIDERS, THINKING_LEVELS (import only)
    engine.py          # EXISTING: PitchTypeSummary, ExecutionMetrics, PlatoonSplit (type refs)
```

### Pattern 1: Tool-Calling Agent with RunContext Dependencies
**What:** A pydantic-ai Agent with `deps_type=QADeps` that uses `@agent.tool` decorated functions receiving `RunContext[QADeps]` as their first parameter. Tools access pre-loaded data via `ctx.deps` without any I/O.
**When to use:** When the agent needs to decide which data to fetch based on the question, rather than receiving all data upfront.
**Example:**
```python
# Source: https://ai.pydantic.dev/dependencies/ + https://ai.pydantic.dev/tools/
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

@dataclass
class QADeps:
    context: PitcherContext
    data: PitcherData  # for future tools if needed

analyst_agent = Agent(
    'openai:gpt-5.4-mini',  # placeholder, overridden by _make_analyst()
    deps_type=QADeps,
    output_type=str,
    instructions="...",  # grounding + voice instructions
)

@analyst_agent.tool
def get_pitcher_summary(ctx: RunContext[QADeps]) -> str:
    """Get the full scouting context for the pitcher."""
    return ctx.deps.context.to_prompt()

@analyst_agent.tool
def get_pitch_detail(ctx: RunContext[QADeps], pitch_type: str) -> str:
    """Get detailed data for a specific pitch type (e.g., 'FF', 'slider')."""
    # resolve synonym -> Statcast code
    code = PITCH_TYPE_MAP.get(pitch_type.lower(), pitch_type.upper())
    # filter and render
    ...
```

### Pattern 2: Agent Factory with Caching (from report.py)
**What:** Module-level dict caching `Agent` instances keyed by `(provider, thinking)` tuple. Factory function creates agents on first call, returns cached on subsequent calls.
**When to use:** Always -- prevents re-creating Agent objects per question.
**Example:**
```python
# Mirrors report.py pattern exactly
_analyst_cache: dict[tuple[str, ThinkingEffort], Agent[QADeps, str]] = {}

def _make_analyst(
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
) -> Agent[QADeps, str]:
    key = (provider, thinking)
    if key in _analyst_cache:
        return _analyst_cache[key]
    # ... create agent with PROVIDERS[provider], model_settings
    _analyst_cache[key] = agent
    return agent
```

### Pattern 3: Streaming Output (from report.py)
**What:** `run_stream_sync()` returns a `StreamedRunResult` directly (NOT as context manager). Iterate with `stream_text(delta=True)` and print each chunk.
**When to use:** For the public `ask_question_streaming()` function.
**Example:**
```python
# Source: report.py lines 686-691 (established project pattern)
stream = agent.run_stream_sync(user_prompt=question, deps=deps)
chunks: list[str] = []
for delta in stream.stream_text(delta=True):
    print(delta, end="", flush=True)
    chunks.append(delta)
print()
return "".join(chunks)
```

**IMPORTANT:** The project uses `run_stream_sync()` WITHOUT a `with` statement. This is the established pattern in both `report.py` (line 686) and `curator.py` (line 112). Do NOT change to context manager style.

### Pattern 4: Instructions Parameter (not system_prompt)
**What:** Use `instructions=` on the Agent constructor. This excludes the instructions from message_history, making future multi-turn (v1.5) a clean addition.
**When to use:** Always for this agent. The report.py agents use `system_prompt=` but that's fine for single-shot pipeline agents. The analyst agent should use `instructions=` per CONTEXT.md decision.
**Example:**
```python
agent = Agent(
    model,
    deps_type=QADeps,
    output_type=str,
    instructions="You are an analytical baseball scout...",
    model_settings=settings,
    defer_model_check=True,
)
```

### Anti-Patterns to Avoid
- **Pre-assembling all context into the prompt:** The whole point of tools is that the agent decides what data it needs. Don't dump `to_prompt()` + all pitch details into the user message.
- **Using `system_prompt=` instead of `instructions=`:** Violates locked decision. Would make multi-turn harder in v1.5.
- **Re-loading data inside tools:** Tools access pre-loaded data from `ctx.deps`. Never call `load_pitcher_data()` or `assemble_pitcher_context()` inside a tool.
- **Using `@agent.tool_plain` for tools that need deps:** These tools need `RunContext[QADeps]` to access data. Use `@agent.tool`, not `@agent.tool_plain`.
- **Hardcoding pitch names in the mapping:** Use the CONTEXT.md-specified codes. The dict maps lowercase strings to uppercase Statcast codes.
- **Using a context manager for `run_stream_sync()`:** The project pattern calls it directly, not with `with`. Keep consistent.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tool-calling agent | Custom prompt parsing to decide which data to include | pydantic-ai `Agent` with `@agent.tool` | Tool-calling is the core value of the agent framework; hand-rolling loses schema validation, retry logic, and streaming |
| Pitch-type synonym resolution | LLM call to extract pitch type from question | Static `PITCH_TYPE_MAP` dict | Instant, deterministic, zero tokens, zero latency |
| Streaming output | Manual HTTP streaming or asyncio event loop | `run_stream_sync()` + `stream_text(delta=True)` | Established pattern, handles backpressure, works with all providers |
| Multi-provider support | Per-provider agent creation logic | `PROVIDERS` dict + `_make_agents()` pattern from report.py | Already tested across openai/claude/gemini |

**Key insight:** The agent framework handles tool schema generation, argument parsing, retry on malformed tool calls, and streaming natively. The only custom logic needed is the pitch-type mapping dict and the pitch-detail markdown renderer.

## Common Pitfalls

### Pitfall 1: TestModel Calls All Tools
**What goes wrong:** TestModel automatically calls every registered tool. For an agent with two tools, it will call both `get_pitcher_summary` AND `get_pitch_detail` in sequence, which means `get_pitch_detail` will receive TestModel-generated arguments (not meaningful pitch types).
**Why it happens:** TestModel generates schema-valid but semantically meaningless arguments to exercise all tools.
**How to avoid:** In tests, either (a) accept that TestModel exercises both tools and assert on the overall flow, or (b) use `FunctionModel` to control exactly which tools are called with which arguments for specific test scenarios.
**Warning signs:** Tests failing because `get_pitch_detail` receives a random string instead of a valid Statcast code. The tool should handle unknown codes gracefully (return "No data for [type]" message).

### Pitfall 2: Pitch-Type Lookup Case Sensitivity
**What goes wrong:** The LLM might pass "ff" or "FF" or "Fastball" to `get_pitch_detail`. If the mapping only handles one case, lookups fail silently.
**Why it happens:** LLMs are inconsistent with casing.
**How to avoid:** Normalize the input: `code = PITCH_TYPE_MAP.get(pitch_type.strip().lower(), pitch_type.strip().upper())`. Always lowercase the lookup key, uppercase the fallback.
**Warning signs:** Agent says "no data for FF" when the pitcher clearly throws a four-seam fastball.

### Pitfall 3: Forgetting to Pass deps at Runtime
**What goes wrong:** `TypeError` or `ValidationError` when calling `run_stream_sync()` without `deps=QADeps(...)`.
**Why it happens:** Easy to forget the `deps` kwarg, especially when copying from report.py which has no deps.
**How to avoid:** The public function signature should take `PitcherContext` and `PitcherData` and construct `QADeps` internally, so callers can't forget.
**Warning signs:** Runtime errors about missing or None deps.

### Pitfall 4: Tool Returns Must Be JSON-Serializable Strings
**What goes wrong:** If a tool returns a complex object that pydantic-ai can't serialize, the agent fails.
**Why it happens:** Tools can return "anything that Pydantic can serialize to JSON" per docs, but returning a `PitcherContext` Pydantic model directly would serialize ALL fields as JSON. The agent needs markdown text, not JSON.
**How to avoid:** Tools return `str` (markdown text). `get_pitcher_summary` returns `ctx.deps.context.to_prompt()` which is already a string. `get_pitch_detail` builds and returns a markdown string.
**Warning signs:** Agent receives JSON blobs instead of readable markdown.

### Pitfall 5: Agent Hallucinating Stats Despite Grounding Instructions
**What goes wrong:** The LLM cites statistics from its training data instead of the tool-provided data.
**Why it happens:** Grounding instructions are soft constraints. Strong models may override them when the question triggers training data retrieval.
**How to avoid:** Make instructions explicit and emphatic: "NEVER cite statistics unless they appear in the tool output. If the data doesn't contain what the user asked about, say so." Also, the tool output being the ONLY data source (no extra context in the prompt) helps constrain the model.
**Warning signs:** Agent cites ERA, WHIP, or win-loss records that don't appear in PitcherContext.

### Pitfall 6: Anthropic max_tokens Default Too Low with Thinking
**What goes wrong:** Claude responses truncate mid-sentence.
**Why it happens:** Anthropic's default `max_tokens` is 4096, which is consumed by thinking tokens before the response.
**How to avoid:** Use `ModelSettings(thinking=thinking, max_tokens=16384)` for Claude provider, same as report.py line 475.
**Warning signs:** Responses end abruptly with no trailing text.

## Code Examples

Verified patterns from the existing codebase and official documentation:

### QADeps Dataclass
```python
# Source: CONTEXT.md locked decision + https://ai.pydantic.dev/dependencies/
from dataclasses import dataclass
from pitcher_narratives.context import PitcherContext
from pitcher_narratives.data import PitcherData

@dataclass
class QADeps:
    """Dependencies for the analyst Q&A agent."""
    context: PitcherContext
    data: PitcherData
```

### PITCH_TYPE_MAP Constant
```python
# Source: CONTEXT.md locked decision (Statcast codes + synonyms)
PITCH_TYPE_MAP: dict[str, str] = {
    # Statcast codes (lowercase -> uppercase)
    "ff": "FF", "si": "SI", "fc": "FC", "sl": "SL", "st": "ST",
    "cu": "CU", "kc": "KC", "ch": "CH", "fs": "FS", "kn": "KN",
    "sc": "SC", "ep": "EP",
    # Common synonyms
    "fastball": "FF", "four-seam": "FF", "four seam": "FF", "4-seam": "FF",
    "sinker": "SI", "two-seam": "SI", "two seam": "SI", "2-seam": "SI",
    "cutter": "FC", "cut fastball": "FC",
    "slider": "SL",
    "sweeper": "ST", "sweep": "ST",
    "curveball": "CU", "curve": "CU",
    "knuckle curve": "KC", "knuckle-curve": "KC",
    "changeup": "CH", "change": "CH", "change-up": "CH",
    "splitter": "FS", "split-finger": "FS", "split finger": "FS",
    "knuckleball": "KN", "knuckle ball": "KN",
    "screwball": "SC",
    "eephus": "EP",
}
```

### get_pitch_detail Tool - Filtering PitcherContext
```python
# Source: context.py PitcherContext model fields (arsenal, execution, platoon_mix)
@analyst_agent.tool
def get_pitch_detail(ctx: RunContext[QADeps], pitch_type: str) -> str:
    """Get detailed arsenal, execution, and platoon data for one pitch type.

    Args:
        pitch_type: Pitch type name or Statcast code (e.g., 'slider', 'SL').
    """
    code = PITCH_TYPE_MAP.get(pitch_type.strip().lower(), pitch_type.strip().upper())
    pc = ctx.deps.context

    # Filter each list by pitch_type code
    arsenal_match = [a for a in pc.arsenal if a.pitch_type == code]
    execution_match = [e for e in pc.execution if e.pitch_type == code]
    platoon_match = [s for s in pc.platoon_mix.splits if s.pitch_type == code]

    if not arsenal_match:
        available = [f"{a.pitch_name} ({a.pitch_type})" for a in pc.arsenal]
        return (
            f"No data for {pitch_type} ({code}) in {pc.pitcher_name}'s arsenal. "
            f"Available pitches: {', '.join(available)}"
        )

    # Render focused markdown
    lines: list[str] = []
    # ... render arsenal row, execution row, platoon splits, P+/S+/L+
    return "\n".join(lines)
```

### Streaming Public Function
```python
# Source: report.py lines 637-691 (established streaming pattern)
def ask_question_streaming(
    question: str,
    context: PitcherContext,
    data: PitcherData,
    *,
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
    _model_override: Any = None,
) -> str:
    """Ask a natural-language question about a pitcher with streaming output."""
    agent = _make_analyst(provider, thinking)
    deps = QADeps(context=context, data=data)

    kwargs: dict[str, Any] = {"user_prompt": question, "deps": deps}
    if _model_override is not None:
        kwargs["model"] = _model_override

    stream = agent.run_stream_sync(**kwargs)
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end="", flush=True)
        chunks.append(delta)
    print()
    return "".join(chunks)
```

### Testing with TestModel
```python
# Source: https://ai.pydantic.dev/testing/ + tests/test_report.py pattern
from pydantic_ai.models.test import TestModel

def test_ask_question_returns_string(ctx, data):
    """Q&A agent returns a non-empty string using TestModel."""
    result = ask_question_streaming(
        "What's his best pitch?",
        context=ctx,
        data=data,
        _model_override=TestModel(),
    )
    assert isinstance(result, str)
    assert len(result) > 0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `system_prompt=` | `instructions=` | pydantic-ai ~0.50+ | instructions excludes from message_history, cleaner for multi-turn |
| `result_type=` | `output_type=` | pydantic-ai ~0.50+ | Parameter renamed; project already uses `output_type=` |
| Context manager `with agent.run_stream(...)` | Direct `stream = agent.run_stream_sync(...)` | Project convention | Both work; project uses non-context-manager style |

**Deprecated/outdated:**
- `result_type` parameter: Renamed to `output_type` in pydantic-ai. The project already uses the current name.
- `system_prompt` for new agents: Not deprecated in pydantic-ai, but `instructions` is recommended for new agents per official docs.

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Data format**: Static parquet + CSV files, no live API calls
- **Python version**: 3.14+
- **Naming**: `snake_case.py` modules, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- **Imports**: Absolute imports, grouped with blank lines, sorted alphabetically
- **Docstrings**: Google-style, type hints on all function signatures
- **Modules**: Use `__all__` for public APIs, prefix internal helpers with `_`
- **Error handling**: Specific exception types, catch `pydantic_ai` exceptions specifically
- **Entry point**: `uv run` for execution

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_analyst.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGENT-01 | Agent answers from tool data only, no hallucination | unit | `uv run pytest tests/test_analyst.py::test_agent_uses_tools -x` | Wave 0 |
| AGENT-02 | get_pitcher_summary returns to_prompt() string | unit | `uv run pytest tests/test_analyst.py::test_get_pitcher_summary_returns_context -x` | Wave 0 |
| AGENT-03 | get_pitch_detail returns filtered pitch data | unit | `uv run pytest tests/test_analyst.py::test_get_pitch_detail_filters_by_type -x` | Wave 0 |
| AGENT-04 | Agent declines out-of-scope questions | unit | `uv run pytest tests/test_analyst.py::test_out_of_scope_handling -x` | Wave 0 |
| AGENT-05 | Pitch type mapping resolves synonyms | unit | `uv run pytest tests/test_analyst.py::test_pitch_type_map_synonyms -x` | Wave 0 |
| AGENT-06 | Streaming output via run_stream_sync | unit | `uv run pytest tests/test_analyst.py::test_ask_question_streaming -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_analyst.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_analyst.py` -- covers AGENT-01 through AGENT-06
- No framework install needed (pytest 9.0.2 already configured)
- No conftest changes needed (existing `tests/__init__.py` present)

## Open Questions

1. **Tool call ordering with streaming**
   - What we know: `run_stream_sync()` handles tool calls internally before streaming the final text response. The agent makes tool calls, gets results, then streams the answer.
   - What's unclear: Whether tool calls show any output to stdout during the streaming phase, or only the final text streams. In report.py, there are no tools so this hasn't been tested.
   - Recommendation: Verify during implementation that tool calls happen silently before streaming begins. If tool call metadata appears in the stream, filter it out.

2. **Exact grounding instruction effectiveness**
   - What we know: Instructions like "Answer ONLY from the data provided" reduce but don't eliminate hallucination. STATE.md flags this as MEDIUM confidence.
   - What's unclear: How effective grounding is across providers (OpenAI vs Claude vs Gemini). Some models are more compliant with system-level constraints.
   - Recommendation: Test with real prompts during development. Consider adding a "Data provided:" prefix in the instructions that the agent sees before every question. The tools being the ONLY data source (not supplemented by prompt context) is the strongest grounding mechanism.

## Sources

### Primary (HIGH confidence)
- [Pydantic AI Agents docs](https://ai.pydantic.dev/agent/) - Agent constructor, instructions vs system_prompt, run_stream_sync
- [Pydantic AI Tools docs](https://ai.pydantic.dev/tools/) - @agent.tool, RunContext, tool return types, docstring-based schemas
- [Pydantic AI Dependencies docs](https://ai.pydantic.dev/dependencies/) - deps_type, RunContext[DepsType], dataclass deps
- [Pydantic AI Testing docs](https://ai.pydantic.dev/testing/) - TestModel, FunctionModel, capture_run_messages, Agent.override
- `src/pitcher_narratives/report.py` - Established patterns: PROVIDERS, THINKING_LEVELS, _make_agents(), run_stream_sync(), stream_text()
- `src/pitcher_narratives/context.py` - PitcherContext model, to_prompt(), field structure (arsenal, execution, platoon_mix)
- `src/pitcher_narratives/data.py` - PitcherData dataclass, load_pitcher_data() signature
- `src/pitcher_narratives/engine.py` - PitchTypeSummary, ExecutionMetrics, PlatoonSplit dataclass fields
- `tests/test_report.py` - TestModel usage pattern, _model_override pattern, fixture pattern

### Secondary (MEDIUM confidence)
- [Pydantic AI API Reference](https://ai.pydantic.dev/api/agent/) - Agent.__init__ full signature, run_stream_sync parameters

### Tertiary (LOW confidence)
- Grounding instruction effectiveness varies by provider -- empirical, needs testing during implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in pyproject.toml, patterns established in report.py
- Architecture: HIGH - Follows established project patterns exactly; tool-calling API verified against official docs
- Pitfalls: HIGH - Based on documented API behavior (TestModel calls all tools) and observed project patterns (max_tokens, case sensitivity)
- Grounding effectiveness: MEDIUM - Instructions-based grounding is standard practice but effectiveness varies by model

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable -- pydantic-ai 1.72.0 is locked in uv.lock)
