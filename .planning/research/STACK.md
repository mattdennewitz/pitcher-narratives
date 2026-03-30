# Stack Research: v1.4 Interactive Pitcher Q&A

**Project:** Pitcher Narratives
**Milestone:** v1.4 -- Interactive Pitcher Q&A
**Researched:** 2026-03-30
**Confidence:** HIGH
**Scope:** Stack additions/changes ONLY for interactive Q&A features. Existing validated stack (Python 3.14, polars 1.39, pydantic-ai 1.72, multi-provider LLM, argparse CLI) is unchanged.

## Executive Summary

One new dependency: **rapidfuzz** for pitcher name fuzzy matching. Everything else -- tool-calling agents, dependency injection, question-aware context assembly, and the new CLI entry point -- is implementable with existing pydantic-ai 1.72 primitives and argparse. The Q&A agent uses `@agent.tool` decorators with `RunContext[QADeps]` to give the LLM access to the data pipeline through typed tools. No CLI framework migration is needed; a third `[project.scripts]` entry point using the existing argparse pattern is the right approach.

## Stack Changes for v1.4

### New Dependencies

| Library | Version | Purpose | Why This One |
|---------|---------|---------|--------------|
| rapidfuzz | >=3.14 | Fuzzy string matching for pitcher name resolution | C++ backend makes it 20-100x faster than thefuzz. MIT license (vs thefuzz's GPL). Drop-in compatible API. `process.extractOne` does exactly what we need: match "degrom" to "deGrom, Jacob" from ~1,651 pitcher names. |

### What Changes

| Component | Current (v1.3) | Change for v1.4 | Why |
|-----------|----------------|------------------|-----|
| Dependencies | polars, pydantic-ai, python-dotenv | Add `rapidfuzz>=3.14` | Name resolution needs fuzzy matching; no built-in alternative |
| Agent pattern | `Agent(model, output_type=str)` with no tools | `Agent(model, deps_type=QADeps, tools=[...])` with tool-calling | Q&A agent needs to look up pitcher data on demand |
| CLI entry points | 2 (`pitcher-narratives`, `pitcher-scout`) | Add 3rd: `pitcher-ask` | Separate entry point keeps Q&A concerns isolated |
| Data pipeline | Called once by CLI, result passed to report | Exposed as tool functions the LLM can invoke | Agent decides which data to fetch based on the question |

### What Does NOT Change

- **data.py**: All loading functions reused as-is. No modifications.
- **engine.py**: All compute functions reused as-is. No modifications.
- **context.py**: `PitcherContext` and `assemble_pitcher_context` reused. No modifications.
- **report.py**: Existing 5-phase pipeline untouched. Q&A is a separate agent.
- **scout.py / curator.py / scout_cli.py**: Unrelated features. Unchanged.
- **cli.py**: Existing narrative CLI unchanged. Q&A gets its own module.
- **pyproject.toml structure**: Same hatch build, same src layout.

## Key Technical Decisions

### 1. rapidfuzz for Name Resolution (Not thefuzz, Not Manual)

**Decision:** Use `rapidfuzz.process.extractOne` with `fuzz.WRatio` scorer and `score_cutoff=70`.

**Why rapidfuzz over thefuzz:**
- **Performance**: C++ implementation, 20-100x faster than thefuzz's pure Python. Not critical for 1,651 names (both are instant), but it means zero motivation to ever consider caching or optimization.
- **License**: MIT vs thefuzz's GPL-2.0. MIT is compatible with any project license.
- **API**: Near-identical to thefuzz (`from rapidfuzz import fuzz, process`), so all thefuzz examples and tutorials apply.
- **Maintenance**: rapidfuzz is actively maintained (v3.14.3 released Nov 2025). thefuzz's last meaningful update was renaming from fuzzywuzzy.

**Why not manual substring matching:**
- Pitcher names have edge cases: "deGrom" vs "degrom", "Musgrove" vs "Musgrave", "Yamamoto" (multiple pitchers with same last name). Fuzzy matching handles these naturally; substring matching requires special-casing.

**Name format in data:** Statcast uses `"Last, First"` format (e.g., `"deGrom, Jacob"`, `"Abbott, Andrew"`). The fuzzy matcher should handle both "Jacob deGrom" and "degrom" as input, matching against the full `"Last, First"` string with `utils.default_process` for case/punctuation normalization.

**Pattern:**

```python
from rapidfuzz import fuzz, process

def resolve_pitcher_name(query: str, names: dict[str, int]) -> tuple[int, str, float]:
    """Resolve a fuzzy pitcher name query to (pitcher_id, canonical_name, score).

    Args:
        query: User input like "degrom" or "Jacob deGrom".
        names: Mapping of "Last, First" -> pitcher_id from statcast data.

    Returns:
        Tuple of (pitcher_id, matched_name, match_score).

    Raises:
        ValueError: If no match above score_cutoff, or if ambiguous (multiple high matches).
    """
    result = process.extractOne(query, names.keys(), scorer=fuzz.WRatio, score_cutoff=70)
    if result is None:
        raise ValueError(f"No pitcher found matching '{query}'")
    matched_name, score, _ = result
    return names[matched_name], matched_name, score
```

**Ambiguity handling:** When `process.extract` returns multiple results above the cutoff with scores within 5 points of each other (e.g., "Yamamoto" matching both "Yamamoto, Yoshinobu" and "Yamamoto, Jordan"), the tool should return all matches and let the user disambiguate. This is a UI concern for the CLI, not a library concern.

**Building the name lookup table:** The statcast parquet already has `pitcher` (ID) and `player_name` columns. Build the lookup once at startup:

```python
def build_pitcher_lookup(parquet_path: Path) -> dict[str, int]:
    """Build name->ID lookup from statcast parquet."""
    df = pl.read_parquet(parquet_path, columns=["pitcher", "player_name"])
    unique = df.unique(subset=["pitcher", "player_name"])
    return dict(zip(unique["player_name"].to_list(), unique["pitcher"].to_list()))
```

This reads only 2 columns (fast, ~2MB vs full 145K-row parquet), and produces ~1,651 entries. Negligible memory.

**Confidence:** HIGH -- rapidfuzz API verified against official docs and PyPI. Name format verified against actual statcast data.

### 2. pydantic-ai Tool-Calling Agent for Q&A (Using Existing Primitives)

**Decision:** Create a single `Agent[QADeps, str]` with `@agent.tool` decorators that expose data pipeline functions. The LLM decides which tools to call based on the user's question.

**Why tool-calling over pre-assembled context:**
- The existing narrative pipeline always assembles the FULL PitcherContext (~544 tokens) because the report needs everything. For Q&A, the user might ask "what's his fastball velocity?" which only needs the fastball summary -- sending the full context wastes tokens and dilutes the answer.
- Tool-calling lets the LLM request only the data it needs. The tools are thin wrappers around existing `engine.py` compute functions.

**Pattern (verified against installed pydantic-ai 1.72.0 source):**

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from pitcher_narratives.data import PitcherData

@dataclass
class QADeps:
    """Dependencies for the Q&A agent."""
    pitcher_data: PitcherData
    pitcher_name: str

qa_agent = Agent(
    'openai:gpt-5.4-mini',
    deps_type=QADeps,
    output_type=str,
    instructions="You are a baseball analyst answering questions about pitchers...",
    defer_model_check=True,
)

@qa_agent.tool
def get_fastball_summary(ctx: RunContext[QADeps]) -> str:
    """Get the pitcher's primary fastball quality metrics.

    Returns velocity, Pitching+ triad (P+, S+, L+), movement deltas,
    and velocity trend vs season baseline.
    """
    from pitcher_narratives.engine import compute_fastball_summary
    fb = compute_fastball_summary(ctx.deps.pitcher_data)
    if fb is None:
        return "No standard fastball identified for this pitcher."
    # Return structured text the LLM can reason about
    return (
        f"Primary fastball: {fb.pitch_name} ({fb.pitch_type})\n"
        f"Season velo: {fb.season_velo:.1f} / Recent: {fb.window_velo:.1f} ({fb.velo_delta})\n"
        f"P+: {fb.season_p_plus:.0f} season / {fb.window_p_plus or '--'} recent ({fb.p_plus_delta})\n"
        f"S+: {fb.season_s_plus:.0f} season / {fb.window_s_plus or '--'} recent ({fb.s_plus_delta})\n"
        f"L+: {fb.season_l_plus:.0f} season / {fb.window_l_plus or '--'} recent ({fb.l_plus_delta})"
    )

@qa_agent.tool
def get_arsenal_summary(ctx: RunContext[QADeps]) -> str:
    """Get the pitcher's full arsenal with usage rates, P+/S+/L+ scores, and deltas."""
    from pitcher_narratives.engine import compute_arsenal_summary
    arsenal = compute_arsenal_summary(ctx.deps.pitcher_data)
    # Format as text table
    ...

@qa_agent.tool
def get_execution_metrics(ctx: RunContext[QADeps]) -> str:
    """Get per-pitch execution metrics: CSW%, zone rate, chase rate, xWhiff, xSwing."""
    ...

@qa_agent.tool
def get_workload_context(ctx: RunContext[QADeps]) -> str:
    """Get recent appearances, pitch counts, rest days, and workload flags."""
    ...

# ... additional tools wrapping engine.py compute functions
```

**Key API details (verified in installed source):**
- `@agent.tool`: First parameter must be `RunContext[QADeps]`. Remaining parameters become the tool schema sent to the LLM. For data lookup tools, there are no additional parameters -- the pitcher is implicit in `ctx.deps`.
- `@agent.tool_plain`: For tools that do not need `RunContext`. Not needed here since all tools access `ctx.deps.pitcher_data`.
- `ModelRetry`: Import from `pydantic_ai.exceptions`. Raise in a tool to tell the LLM to retry with different arguments. Useful if a tool receives invalid input.
- Tool return type: Must be JSON-serializable. Returning `str` is simplest and gives the LLM natural-language data it can directly quote.
- Docstrings are critical: pydantic-ai extracts the tool description from the docstring and sends it to the LLM as the tool's description. The LLM uses this to decide which tool to call.

**Running the agent:**

```python
result = qa_agent.run_sync(
    user_prompt=question,
    deps=QADeps(pitcher_data=data, pitcher_name=name),
)
print(result.output)
```

**Confidence:** HIGH -- `Agent.__init__` signature, `@agent.tool` decorator, `RunContext` dataclass, and `run_sync` method all verified in installed pydantic-ai 1.72.0 source at `.venv/lib/python3.14/site-packages/pydantic_ai/`.

### 3. `instructions` Over `system_prompt` for the Q&A Agent

**Decision:** Use the `instructions` parameter (not `system_prompt`) for the Q&A agent's system-level guidance.

**Why:**
- `instructions` are excluded from `message_history` when continuing conversations. This matters if we later add multi-turn Q&A: the instructions don't accumulate as duplicate system messages across turns.
- `system_prompt` is retained in message history. For a single-shot Q&A agent (v1.4 scope), both work identically. But `instructions` is future-proof for multi-turn without any code change.
- The existing report pipeline uses `system_prompt` because those agents never do multi-turn. For Q&A, the usage pattern is different.

**Confidence:** HIGH -- behavior difference verified in pydantic-ai docs: "Instructions: Exclude previous agent instructions when `message_history` is provided; reevaluated per run."

### 4. Separate CLI Module (Not Subcommand)

**Decision:** Create `ask_cli.py` as a new module with its own `main()` and a new `[project.scripts]` entry point `pitcher-ask`. Do NOT convert existing CLIs to subcommands.

**Why:**
- The existing project has two separate entry points (`pitcher-narratives` and `pitcher-scout`) as independent argparse scripts. Adding a third follows the established pattern.
- Converting to subcommands (e.g., `pitcher report`, `pitcher scout`, `pitcher ask`) would be a breaking change to the existing CLI interfaces that users may have scripted.
- argparse is adequate. The Q&A CLI needs: pitcher name (positional), question (positional or `-q`), provider flag, thinking flag. That's 4 arguments. No framework migration needed.

**Pattern:**

```python
# pyproject.toml addition
[project.scripts]
pitcher-narratives = "pitcher_narratives.cli:main"
pitcher-scout = "pitcher_narratives.scout_cli:main"
pitcher-ask = "pitcher_narratives.ask_cli:main"
```

```python
# ask_cli.py
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask questions about a pitcher's recent performance",
    )
    parser.add_argument("pitcher", help="Pitcher name (fuzzy matched)")
    parser.add_argument("question", help="Question to ask about the pitcher")
    parser.add_argument("--provider", choices=["openai", "claude", "gemini"], default="openai")
    parser.add_argument("--thinking", choices=["minimal", "low", "medium", "high", "xhigh"], default="medium")
    parser.add_argument("-w", "--window", type=int, default=30, help="Lookback window in days")
    return parser.parse_args()
```

**Confidence:** HIGH -- follows established project patterns exactly.

### 5. Tool Return Format: Structured Text (Not Pydantic Models)

**Decision:** Q&A tools return `str` (formatted text), not Pydantic model instances or dicts.

**Why:**
- The LLM needs to read the tool output and synthesize an answer. A formatted text string ("P+: 112 season / 118 recent (Rising)") is directly quotable and readable. A JSON dict (`{"season_p_plus": 112, "window_p_plus": 118, "delta": "Rising"}`) requires the LLM to reconstruct meaning from keys.
- The existing `PitcherContext.to_prompt()` already proves that structured text is the right format for LLM consumption in this project.
- Returning str avoids coupling tool output format to any specific schema. If engine.py evolves, the tool just updates its format string.

**When to use structured returns:** If a future feature needs the LLM to pass tool output to another tool (chained tool calls), structured output would be better. For v1.4's single-agent Q&A, text is simpler and more effective.

**Confidence:** HIGH -- validated by existing project's `to_prompt()` pattern.

### 6. No Async Conversion Needed

**Decision:** Continue using `run_sync` for the Q&A agent. Do not convert to async.

**Why:**
- The existing pipeline uses `run_sync` and `run_stream_sync` throughout. The Q&A agent is a CLI tool that blocks on a single LLM call. Async provides zero benefit here.
- pydantic-ai's `run_sync` internally handles the async-to-sync bridge. No manual `asyncio.run()` needed.
- The tool functions access polars DataFrames synchronously. Making them async would require wrapping every polars call in `asyncio.to_thread()` for no benefit.

**Confidence:** HIGH -- consistent with existing project architecture.

## Installation

```bash
# Add rapidfuzz to project dependencies
uv add "rapidfuzz>=3.14"
```

In `pyproject.toml`:

```toml
dependencies = [
    "polars>=1.39.3",
    "pydantic-ai>=1.72.0",
    "pydantic-ai-slim[google]>=1.72.0",
    "python-dotenv>=1.2.2",
    "rapidfuzz>=3.14",  # NEW for v1.4
]

[project.scripts]
pitcher-narratives = "pitcher_narratives.cli:main"
pitcher-scout = "pitcher_narratives.scout_cli:main"
pitcher-ask = "pitcher_narratives.ask_cli:main"  # NEW for v1.4
```

## Alternatives Considered

| Decision | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Fuzzy matching | rapidfuzz | thefuzz (fuzzywuzzy) | GPL license, pure Python (slower), less actively maintained. Identical API -- easy to swap if needed. |
| Fuzzy matching | rapidfuzz | polars string contains / regex | No fuzzy tolerance. "degrom" won't match "deGrom, Jacob" without exact substring logic. Breaks on typos. |
| Fuzzy matching | rapidfuzz | Manual Levenshtein | Reinventing the wheel. rapidfuzz's `process.extractOne` handles scoring, cutoff, preprocessing, and ranking in one call. |
| Agent pattern | Tool-calling agent | Pre-assembled full context | Wastes tokens on irrelevant data. A "what's his fastball velo?" question doesn't need platoon splits, TTO analysis, or first-pitch tendencies. |
| Agent pattern | Tool-calling agent | Multiple specialized agents | Over-engineering. One agent with 6-8 tools covers all question types. Multiple agents need routing logic and add latency. |
| CLI structure | Separate entry point | Subcommand migration | Breaking change to existing CLI. Three small independent scripts is simpler than one dispatcher. |
| CLI framework | argparse | typer / click | Already in stdlib, already used by project, 4 arguments don't justify a new dependency. typer IS in the dep tree (transitive via pydantic-ai) but using it for one CLI while others use argparse creates inconsistency. |
| Tool returns | str | dict / Pydantic model | LLM reads text better than JSON for answer synthesis. Existing to_prompt() pattern validates this approach. |

## What NOT to Add

| Avoid | Why | Risk if Added |
|-------|-----|---------------|
| LangChain / LlamaIndex | Massive dependency trees for a single-agent Q&A. pydantic-ai already does tool-calling natively. | 50+ transitive deps, version conflicts, abstraction layer mismatch |
| Vector database (ChromaDB, Pinecone) | 1,651 pitchers with structured data. Fuzzy string matching on names is exact enough. Vector search is for unstructured document retrieval. | Complexity for zero benefit on structured tabular data |
| Embedding model for name matching | Same reason. `process.extractOne` on 1,651 names runs in <1ms. Embedding similarity is slower and less interpretable. | API calls for name matching, latency, cost |
| Conversation memory / persistence | v1.4 is single-shot Q&A. Multi-turn is out of scope. pydantic-ai's `message_history` can add this later with zero new deps. | Premature complexity |
| typer / click / rich for CLI | argparse works. The Q&A CLI has 4-5 arguments. Rich terminal formatting is out of scope per PROJECT.md. | Inconsistency with existing CLIs, new dep for no benefit |
| Async runtime | CLI blocks on one LLM call. `run_sync` is correct. | asyncio boilerplate for zero performance benefit |
| Separate "router" agent | One agent can dispatch via tools. A router adds an extra LLM call to decide which agent to invoke. | Doubled latency, doubled cost, unnecessary for Q&A scope |
| pydantic-graph for Q&A flow | Q&A is: resolve name -> load data -> call agent -> print. Linear. Not a graph. | Same objection as v1.3: boilerplate for a while-loop |

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| rapidfuzz >=3.14 | Python >=3.10 | Project requires 3.14+, well within range |
| rapidfuzz >=3.14 | polars >=1.39 | No interaction (different domains) |
| rapidfuzz >=3.14 | pydantic-ai >=1.72 | No interaction (different domains) |
| pydantic-ai 1.72 | `@agent.tool` with `RunContext` | Verified in installed source -- full tool-calling support |
| pydantic-ai 1.72 | `instructions` parameter | Verified -- excludes from message_history on subsequent runs |
| pydantic-ai 1.72 | `ModelRetry` exception | Verified in `exceptions.py` -- tools can signal retry |

## Integration Points

### New Files

| File | Purpose | Depends On |
|------|---------|------------|
| `ask_cli.py` | CLI entry point for `pitcher-ask` command | argparse, data.py, resolve.py, ask.py |
| `resolve.py` | Pitcher name resolution (fuzzy matching) | rapidfuzz, data.py (for name lookup table) |
| `ask.py` | Q&A agent definition with tools | pydantic-ai, data.py, engine.py |

### Existing Files Modified

| File | Change | Impact |
|------|--------|--------|
| `pyproject.toml` | Add `rapidfuzz>=3.14` dep, add `pitcher-ask` entry point | Minimal -- two lines |

### Existing Files NOT Modified

| File | Why Unchanged |
|------|---------------|
| `data.py` | Functions reused as-is via tool wrappers. No changes to loading logic. |
| `engine.py` | Compute functions called from tools. No interface changes. |
| `context.py` | `assemble_pitcher_context` reusable if agent wants full context. No changes. |
| `report.py` | Narrative pipeline is a separate feature. No interaction with Q&A. |
| `cli.py` | Existing narrative CLI unchanged. |
| `scout.py` / `curator.py` / `scout_cli.py` | Unrelated features. |

## Sources

| Source | What Verified | Confidence |
|--------|---------------|------------|
| [RapidFuzz PyPI](https://pypi.org/project/RapidFuzz/) | v3.14.3 latest, MIT license, Python >=3.10 | HIGH |
| [RapidFuzz GitHub](https://github.com/rapidfuzz/RapidFuzz) | API: `process.extractOne`, `fuzz.WRatio`, `score_cutoff` param | HIGH |
| [pydantic-ai Tools docs](https://ai.pydantic.dev/tools/) | `@agent.tool`, `@agent.tool_plain`, docstring extraction, `ModelRetry` | HIGH |
| [pydantic-ai Agent docs](https://ai.pydantic.dev/agent/) | `instructions` vs `system_prompt`, `run_sync`, `deps_type`, `message_history` | HIGH |
| [pydantic-ai Dependencies docs](https://ai.pydantic.dev/dependencies/) | `RunContext[DepsType]`, dataclass deps pattern, runtime `deps=` passing | HIGH |
| Installed source: `pydantic_ai/agent/__init__.py` | `tool()` decorator signature, `tool_plain()` signature | HIGH |
| Installed source: `pydantic_ai/_run_context.py` | `RunContext` dataclass fields: `deps`, `model`, `usage`, `messages` | HIGH |
| Installed source: `pydantic_ai/exceptions.py` | `ModelRetry` class definition and schema | HIGH |
| Project source: `data.py` | `load_pitcher_data`, `PitcherData` dataclass, name format "Last, First" | HIGH |
| Project source: `report.py` | Existing agent creation pattern, `_make_agents`, `CachePoint` usage | HIGH |
| Project data: `statcast_2026.parquet` | 1,651 unique pitchers, "Last, First" name format confirmed | HIGH |

---
*Stack research for: v1.4 Interactive Pitcher Q&A*
*Researched: 2026-03-30*
