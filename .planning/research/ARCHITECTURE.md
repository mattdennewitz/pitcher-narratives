# Architecture: Interactive Pitcher Q&A Integration

**Domain:** Conversational Q&A agent layered onto existing data pipeline
**Researched:** 2026-03-30
**Confidence:** HIGH

## Problem Statement

The existing system generates one-shot scouting reports: user provides a pitcher ID, the pipeline computes everything, a 5-phase LLM pipeline produces a narrative. v1.4 adds a second consumer of that same data pipeline -- a Q&A agent that answers natural-language questions about pitchers. This requires solving four integration questions:

1. Where does pitcher name resolution live?
2. Should the analyst agent use tools (multi-turn) or pre-assembled context (single call)?
3. How do report and Q&A consumers share the data pipeline?
4. What does the CLI entry point look like?

## Current Architecture (What Exists)

```
CLI (cli.py)                 Scout CLI (scout_cli.py)
    |                              |
    v                              v
load_pitcher_data(id, window)  scout_appearances(window, top_n)
    |                              |
    v                              |
PitcherData                        |
    |                              |
    v                              |
assemble_pitcher_context()         |
    |                              |
    v                              v
PitcherContext            ScoredAppearance[]
    |                              |
    v                              v
generate_report_streaming()   curate_appearances()
    |
    v
ReportResult (narrative + hook + fantasy + warnings)
```

Key module responsibilities:
- **data.py**: `load_pitcher_data(pitcher_id, window_days)` -> `PitcherData` (parquet + 8 CSVs, classification, baselines)
- **engine.py**: 10 compute functions (fastball, velocity arc, arsenal, execution, platoon, first pitch, workload, hard hit, release point, TTO) -> dataclass outputs
- **context.py**: `assemble_pitcher_context(PitcherData)` -> `PitcherContext` Pydantic model with `to_prompt()` -> ~544 token markdown
- **report.py**: 5-phase LLM pipeline + reflection loop, `generate_report_streaming(PitcherContext)` -> `ReportResult`
- **scout.py**: Scores appearances for interestingness without LLM calls
- **curator.py**: LLM-powered curation of scored appearances
- **cli.py**: argparse entry point for narrative generation (`pitcher-narratives` script)
- **scout_cli.py**: argparse entry point for scouting (`pitcher-scout` script)

Data sources:
- `statcast_2026.parquet`: 145K pitch-level rows, has `pitcher` (int ID) and `player_name` (str, format "Last, First")
- `aggs/2026-pitcher.csv`: ~1,651 unique pitchers with `pitcher` and `player_name` columns

## Integration Decision: Name Resolution

### Decision: Standalone `resolver.py` module (not an LLM tool)

Name resolution is a deterministic string-matching problem. It does not benefit from LLM reasoning and should not consume LLM tokens. The LLM does not need to "decide" to look up a name -- the CLI layer resolves the name before any LLM call happens.

**Implementation:**

```python
# resolver.py
@dataclass
class ResolvedPitcher:
    pitcher_id: int
    pitcher_name: str    # canonical "Last, First" format
    confidence: float    # match score 0-100
    alternatives: list[tuple[int, str, float]]  # other close matches

def resolve_pitcher(query: str) -> ResolvedPitcher: ...
```

**Why not a tool?** Three reasons:
1. Name resolution must succeed before we load any data. If the LLM calls a tool and gets back "Ohtani could be 660271 or did you mean..." -- that adds a round trip and the LLM still cannot proceed without a definitive ID.
2. The existing data pipeline (`load_pitcher_data`) takes `pitcher_id: int`. Changing this to accept names would couple two concerns.
3. Fuzzy matching is fast (~ms on 1,651 names) and deterministic. No reason to involve the LLM.

**Data source for name lookup:** `aggs/2026-pitcher.csv` is the smallest file containing the full pitcher-to-name mapping (375 KB, ~1,651 unique pitchers). Load it once, build an in-memory index.

**Matching strategy:**
- Exact match first (case-insensitive, both "Ohtani" and "Ohtani, Shohei")
- Token-based matching for partial names ("Shohei" matches "Ohtani, Shohei")
- Fuzzy matching via `rapidfuzz` for typos ("Ohtanni" -> "Ohtani, Shohei")
- Threshold: score >= 85 for auto-resolve, 70-85 presents alternatives, <70 fails

**Dependency:** `rapidfuzz` (MIT license, C++ backend, ~100x faster than `thefuzz`, API-compatible). Small pure dependency, no transitive weight. If adding a dependency is undesirable, Python's `difflib.SequenceMatcher` handles 1,651 names fine (just slower on repeated calls).

**Recommendation:** Use `rapidfuzz` -- it is the standard library for this task, MIT licensed, and the performance headroom means name resolution stays under 5ms even with repeated calls.

## Integration Decision: Tool-Based vs. Pre-Assembled Context

### Decision: Pre-assembled context with a single LLM call (no tools)

This is the most consequential architectural choice and the one where this research diverges from the STACK.md recommendation. STACK.md recommends a tool-calling agent with `@agent.tool` decorators wrapping engine compute functions. This ARCHITECTURE.md recommends pre-assembled context instead. Here is the full analysis.

**Option A: Tools (multi-turn)** -- Agent has tools like `get_fastball_summary()`, `get_arsenal()`, `get_platoon_splits()`. The LLM decides which data to fetch based on the question.

**Option B: Pre-assembled context (single call)** -- Assemble the full `PitcherContext.to_prompt()` markdown (~544 tokens) and send it with the question in one call. The LLM answers from the pre-assembled data.

**Option B wins.** The reasoning:

1. **Context is small -- the core argument.** The entire `PitcherContext.to_prompt()` is ~544 tokens. STACK.md's argument for tools is "A 'what's his fastball velo?' question doesn't need platoon splits" -- true, but the overhead of sending unused context is ~400 tokens, which costs <$0.001 and adds zero perceptible latency. The overhead of a tool-calling round trip is 500ms-2s of wall-clock time per tool call, plus the LLM must decide which tool to call (sometimes incorrectly).

2. **Tools add latency, not intelligence.** Each tool call requires: (a) the LLM to decide to call a tool, (b) sending the tool call back to the application, (c) executing the tool, (d) returning the result, (e) the LLM to process the result. For a Q&A interaction where the user wants sub-second responsiveness, a single call with 544 tokens of context is always faster than tool-calling loops. Even a single tool call adds 1-2 seconds of latency.

3. **The existing context is already optimized.** The `to_prompt()` method was specifically designed for LLM consumption. The engine already pre-computes deltas, trend strings, and qualitative labels. The tools in STACK.md would just be wrappers that call the same compute functions and format the output -- duplicating what `to_prompt()` already does.

4. **Tool-based agents are harder to test.** With pre-assembled context, testing is: build context, call agent, assert on output. With tools, you need to verify the LLM calls the right tools for each question type, handle cases where it calls the wrong tool or no tool, mock tool execution, etc. The test matrix is combinatorial.

5. **Tool selection can be wrong.** If a user asks "what's different about his stuff recently?" the LLM must decide: call `get_fastball_summary()`? `get_arsenal_summary()`? Both? All of them? Pre-assembled context sidesteps this entirely -- the LLM has everything and picks what is relevant. The LLM is better at extracting relevant information from a document than at deciding which API to call.

6. **Question-aware filtering is better done in Python.** If context filtering is needed (it likely is not at 544 tokens), detecting "slider" in a question and promoting SL data in the context is a simple regex. It is cheaper, faster, and more reliable than hoping the LLM calls `get_pitch_type_data("SL")`.

**When tools would be the right choice:**
- If context exceeded ~2,000 tokens (selective retrieval saves real cost)
- If the agent needs data not in PitcherContext (league averages, other pitchers)
- If multi-turn conversation is supported (tools enable dynamic data fetching per turn)

None of these apply to v1.4. If any become true in v1.5+, migrating from pre-assembled context to tools is straightforward -- the `ask_question()` function signature does not change, only its internals.

### Reconciliation with STACK.md

STACK.md recommends tools because it views the problem as "the LLM should only see relevant data." This is sound engineering intuition for large contexts. But it does not account for the actual context size (544 tokens) or the latency cost of tool calls in a CLI Q&A interaction. The architectural evidence (measuring `to_prompt()` output) overrides the general principle.

STACK.md's `instructions` vs `system_prompt` recommendation is correct and adopted here. STACK.md's `rapidfuzz` recommendation is correct and adopted here. The tool-calling pattern is the only point of disagreement, and this document explains why.

### Question-Aware Context Filtering

Not a complex feature -- a lightweight enhancement:

```python
# In context.py or a new qa_context.py
def to_qa_prompt(self, question: str) -> str:
    """Render context with question-relevant sections promoted."""
```

The idea: detect keywords in the question (pitch type names, "velocity", "platoon", "workload", etc.) and reorder or annotate the context sections to emphasize relevant data. The full context still ships (it is only 544 tokens), but the question-relevant section gets a "** Relevant to your question **" annotation or moves to the top.

**Recommendation:** Start without question-aware filtering. The context is small enough that the LLM handles it fine. Add filtering only if testing reveals the agent missing relevant data in answers.

## Integration Decision: Sharing the Data Pipeline

### Decision: Reuse `load_pitcher_data()` and `assemble_pitcher_context()` as-is

The existing pipeline already does exactly what the Q&A agent needs:

```
resolve_pitcher("Ohtani")      # NEW: resolver.py
    |
    v
pitcher_id = 660271
    |
    v
load_pitcher_data(660271, 30)  # EXISTING: data.py (unchanged)
    |
    v
PitcherData
    |
    v
assemble_pitcher_context(data) # EXISTING: context.py (unchanged)
    |
    v
PitcherContext
    |
    v
analyst_agent.run_sync(        # NEW: analyst.py
    question + context.to_prompt()
)
    |
    v
Answer (str)
```

**No modifications needed to data.py, engine.py, or context.py.** The Q&A agent is a new consumer of the same data pipeline, not a modification of it.

The `window_days` parameter maps naturally to Q&A: default to 30 for general questions, allow the user to specify a different window if they want ("how has he looked in the last week?").

## Integration Decision: CLI Entry Point

### Decision: New `ask_cli.py` module with new `pitcher-ask` script entry point

The project already has two separate CLI scripts:
- `pitcher-narratives` -> `cli.py:main`
- `pitcher-scout` -> `scout_cli.py:main`

Follow the same pattern: a new `pitcher-ask` script entry point.

```toml
# pyproject.toml
[project.scripts]
pitcher-narratives = "pitcher_narratives.cli:main"
pitcher-scout = "pitcher_narratives.scout_cli:main"
pitcher-ask = "pitcher_narratives.ask_cli:main"       # NEW
```

**Why not a subcommand of `pitcher-narratives`?** Three reasons:
1. The existing CLIs use `argparse` with no subcommand structure. Adding subcommands to `pitcher-narratives` would break the existing `pitcher-narratives -p 660271` interface.
2. The project already set the precedent of separate scripts per concern (`pitcher-scout` is separate from `pitcher-narratives`).
3. The Q&A usage pattern is fundamentally different: it takes a name (not an ID) and a question (not a window).

**CLI interface:**

```bash
# Basic usage
pitcher-ask "Ohtani" "How's his slider looking?"

# With options
pitcher-ask "Gerrit Cole" "Is his fastball velocity trending down?" -w 14
pitcher-ask "Cole, Gerrit" "What's changed recently?" --provider claude
```

Arguments:
- `pitcher` (positional): Pitcher name (fuzzy matched)
- `question` (positional): Natural language question
- `-w` / `--window`: Lookback window in days (default 30, reuses existing convention)
- `--provider`: LLM provider (default openai, same options as existing CLIs)
- `--thinking`: Thinking effort level (default medium, same as existing)

## Recommended Architecture (v1.4)

### New Component Map

```
CLI Layer
  ask_cli.py [NEW]          -- argparse, orchestrates name resolution + Q&A
  cli.py     [UNCHANGED]    -- existing narrative CLI
  scout_cli.py [UNCHANGED]  -- existing scout CLI

Resolution Layer
  resolver.py [NEW]         -- fuzzy name-to-ID matching

Data Layer
  data.py    [UNCHANGED]    -- load_pitcher_data()
  engine.py  [UNCHANGED]    -- 10 compute functions
  context.py [UNCHANGED]    -- PitcherContext assembly + to_prompt()

LLM Layer
  analyst.py [NEW]          -- Q&A agent with analyst system prompt
  report.py  [UNCHANGED]    -- 5-phase narrative pipeline
  curator.py [UNCHANGED]    -- curation agent
```

### New Modules Detail

#### `resolver.py` -- Pitcher Name Resolution

```python
"""Fuzzy pitcher name resolution from local data.

Maps natural-language pitcher names to MLB pitcher IDs using the
pitcher aggregation CSV as the name registry.
"""

@dataclass
class ResolvedPitcher:
    pitcher_id: int
    pitcher_name: str
    confidence: float
    alternatives: list[tuple[int, str, float]]

class AmbiguousMatchError(Exception):
    """Multiple pitchers matched with similar confidence."""
    candidates: list[tuple[int, str, float]]

class NoMatchError(Exception):
    """No pitcher matched the query."""
    query: str

def build_pitcher_index() -> dict[int, str]:
    """Load unique pitcher ID -> name mapping from 2026-pitcher.csv."""

def resolve_pitcher(query: str) -> ResolvedPitcher:
    """Resolve a natural-language name to a pitcher ID.

    Strategy: exact match -> token match -> fuzzy match.
    Raises AmbiguousMatchError or NoMatchError on failure.
    """
```

Responsibilities:
- Load pitcher name registry from `aggs/2026-pitcher.csv` (once, cached)
- Support multiple input formats: "Ohtani", "Shohei Ohtani", "Ohtani, Shohei"
- Fuzzy match via `rapidfuzz.fuzz.token_sort_ratio` for typo tolerance
- Return structured result with confidence score and alternatives
- Raise specific errors for ambiguous or no-match cases

#### `analyst.py` -- Q&A Analyst Agent

```python
"""Single-phase Q&A analyst agent.

Takes a question and PitcherContext, returns a grounded analytical
response. No multi-phase pipeline, no reflection loop -- single call
optimized for interactive responsiveness.
"""

def ask_question(
    question: str,
    ctx: PitcherContext,
    *,
    provider: str = "openai",
    thinking: ThinkingEffort = "medium",
    _model_override: Any = None,
) -> str:
    """Answer a question about a pitcher using pre-assembled context."""
```

System prompt characteristics:
- Grounded analyst voice (reuse the pragmatic tone from the editor prompt)
- Explicit instruction: answer ONLY from the provided data, say "the data doesn't cover that" when asked about something not in the context
- No hallucination -- cite specific numbers from the context
- Concise answers (2-4 sentences for most questions, longer for "tell me everything about his slider")
- No bullet points, no headers -- conversational prose

Key differences from the report pipeline:
- Single agent, single call (no multi-phase, no reflection loop)
- Optimized for speed (interactive feel, not report quality)
- Lower thinking effort by default (medium vs high)
- Output is direct answer text, not a structured ReportResult
- Uses `instructions` parameter (not `system_prompt`) per STACK.md recommendation, for future multi-turn compatibility

#### `ask_cli.py` -- Q&A CLI Entry Point

```python
"""CLI entry point for interactive pitcher Q&A.

Resolves pitcher names to IDs, loads data, and answers questions
using the analyst agent.
"""

def main() -> None:
    """Entry point: resolve name, load data, ask question, print answer."""
```

Flow:
1. Parse args (pitcher name, question, options)
2. Resolve name via `resolver.resolve_pitcher()`
3. Print resolution result to stderr ("Resolved: Ohtani, Shohei (660271)")
4. Load data via `data.load_pitcher_data()`
5. Assemble context via `context.assemble_pitcher_context()`
6. Call `analyst.ask_question()` with streaming output
7. Print answer to stdout

Error handling:
- `NoMatchError`: print "No pitcher found matching 'X'" to stderr, exit 1
- `AmbiguousMatchError`: print candidates to stderr ("Did you mean: ..."), exit 1
- `ValueError` from `load_pitcher_data`: print error, exit 1
- Missing API key: same pre-flight check pattern as existing CLIs

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `ask_cli.py` | Arg parsing, orchestration, error handling, streaming output | resolver, data, context, analyst |
| `resolver.py` | Name -> ID mapping, fuzzy matching, ambiguity handling | data (reads CSV directly) |
| `analyst.py` | LLM Q&A agent definition, system prompt, single-call answering | context (reads PitcherContext) |
| `data.py` | Data loading (unchanged) | parquet + CSV files |
| `engine.py` | Computation (unchanged) | data.py outputs |
| `context.py` | Context assembly (unchanged) | engine.py outputs |

### Data Flow

```
User: pitcher-ask "Ohtani" "How's his slider looking?" -w 14

ask_cli.py:
  1. Parse: pitcher="Ohtani", question="How's his slider looking?", window=14
  2. resolver.resolve_pitcher("Ohtani")
     -> ResolvedPitcher(id=660271, name="Ohtani, Shohei", confidence=95)
  3. stderr: "Resolved: Ohtani, Shohei (660271)"
  4. data.load_pitcher_data(660271, window_days=14) -> PitcherData
  5. context.assemble_pitcher_context(data) -> PitcherContext
  6. analyst.ask_question(
       question="How's his slider looking?",
       ctx=pitcher_context,
       provider="openai",
     )
  7. Stream answer to stdout
```

## Patterns to Follow

### Pattern 1: Separate CLI per Concern (established)
**What:** Each major feature gets its own CLI entry point script and pyproject.toml entry.
**When:** Adding a new user-facing capability with a different interaction pattern.
**Evidence:** `cli.py` / `pitcher-narratives` and `scout_cli.py` / `pitcher-scout` already demonstrate this.

### Pattern 2: Agent Factory with Caching (established)
**What:** `_make_agents()` in report.py creates and caches agents keyed by (provider, thinking).
**When:** Creating LLM agents that may be reused across calls.
**Apply to:** The analyst agent in `analyst.py` should follow the same pattern -- a module-level `_make_analyst()` that caches by (provider, thinking).

### Pattern 3: Pre-flight API Key Check (established)
**What:** Check for the required API key env var before making any LLM call.
**When:** Any CLI that calls an LLM.
**Evidence:** Both `cli.py` and `scout_cli.py` do this.

### Pattern 4: Lazy Imports for Speed (established)
**What:** Import heavy modules (`pydantic_ai`, `polars`) inside functions, not at module top.
**When:** CLI modules where import time affects perceived startup latency.
**Evidence:** `cli.py` uses `from pitcher_narratives.data import load_pitcher_data` inside `main()`.

### Pattern 5: stderr for Status, stdout for Output (established)
**What:** All status messages, progress indicators, and error messages go to stderr. Only the final output (report, table, answer) goes to stdout.
**When:** Always.
**Evidence:** All existing CLIs follow this strictly.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Making the LLM Do Name Resolution
**What:** Giving the analyst agent a `resolve_name` tool so it can look up pitcher IDs.
**Why bad:** Wastes LLM tokens on a deterministic string-matching task. Adds latency (tool call round trip). Creates error paths where the LLM misinterprets ambiguous matches.
**Instead:** Resolve the name in Python before any LLM call. The LLM receives a fully-resolved PitcherContext.

### Anti-Pattern 2: Modifying PitcherContext for Q&A
**What:** Adding Q&A-specific fields or methods to the shared `PitcherContext` model.
**Why bad:** Couples two consumers. The report pipeline and Q&A agent have different context needs. PitcherContext is already well-scoped for its purpose.
**Instead:** If Q&A needs different context formatting, create a thin wrapper or a separate `to_qa_prompt()` method. But start by reusing `to_prompt()` as-is -- it is only 544 tokens and likely sufficient.

### Anti-Pattern 3: Multi-Phase Pipeline for Q&A
**What:** Replicating the synthesizer -> editor -> anchor check flow for Q&A.
**Why bad:** Massive overkill. The report pipeline exists because generating a polished narrative requires multiple refinement passes. Q&A is a direct question-answer interaction. One LLM call is correct.
**Instead:** Single agent, single call. If answer quality becomes a problem, add a lightweight fact-check step later (but do not start with it).

### Anti-Pattern 4: Subcommands on Existing CLI
**What:** Changing `pitcher-narratives -p 660271` to `pitcher-narratives report -p 660271` and adding `pitcher-narratives ask "Ohtani" "question"`.
**Why bad:** Breaking change to the existing interface. The existing CLI has no subcommand structure. Users and scripts depending on `pitcher-narratives -p 660271` would break.
**Instead:** New `pitcher-ask` script. Clean separation, zero breaking changes.

### Anti-Pattern 5: Tool-Based Agent for 544-Token Context
**What:** Wrapping each engine compute function as an `@agent.tool` so the LLM fetches data selectively.
**Why bad:** At 544 tokens total context, the overhead of tool-calling (latency, LLM decision-making about which tool to call, error handling for wrong tool selection) exceeds the cost of sending the full context. Tools are correct when context is large and selective retrieval saves meaningful tokens/cost. That threshold is not met here.
**Instead:** Send full `PitcherContext.to_prompt()` as user message context. Reassess if context grows past ~2,000 tokens.

## Suggested Build Order

The build order follows dependency chains and enables incremental testing.

### Phase 1: Pitcher Name Resolution (`resolver.py`)
**Rationale:** Foundation for the new CLI. Has zero LLM dependencies, pure Python + `rapidfuzz`. Can be built and thoroughly tested independently.

Build:
1. `resolver.py` with `build_pitcher_index()`, `resolve_pitcher()`, error types
2. Unit tests: exact match, partial name, fuzzy match, ambiguous, no match, "Last, First" format, "First Last" format
3. Add `rapidfuzz` to `pyproject.toml` dependencies

Dependencies: Only `data.py` (for CSV path constants). No other modules touched.

### Phase 2: Q&A Analyst Agent (`analyst.py`)
**Rationale:** The core LLM integration. Depends on `PitcherContext` (which already exists and is unchanged). Can be tested with `TestModel` from pydantic-ai.

Build:
1. `analyst.py` with system prompt, agent factory, `ask_question()` function
2. System prompt: grounded analyst voice, data-only answers, cite specific numbers
3. Unit tests with `TestModel` (no real LLM calls): verify prompt assembly, verify context is included, verify streaming works

Dependencies: `context.py` (unchanged), `report.py` (imports `PROVIDERS`, `THINKING_LEVELS` constants).

### Phase 3: Q&A CLI Entry Point (`ask_cli.py`)
**Rationale:** Wires the previous two components together. Follows established CLI patterns.

Build:
1. `ask_cli.py` with `parse_args()` and `main()`
2. Positional args for pitcher name and question
3. Standard options: `-w`, `--provider`, `--thinking`
4. Error handling for resolution failures and missing API keys
5. `pyproject.toml` entry: `pitcher-ask = "pitcher_narratives.ask_cli:main"`
6. Integration tests: end-to-end with `TestModel`

Dependencies: `resolver.py` (Phase 1), `analyst.py` (Phase 2), `data.py` + `context.py` (unchanged).

### Phase 4 (optional): Question-Aware Context Filtering
**Rationale:** Only build if testing reveals the agent struggling with questions about specific pitch types or metrics. The 544-token context is likely small enough that the LLM handles it without filtering.

Build:
1. Keyword detection in questions (pitch type names, metric categories)
2. Context section reordering or annotation
3. Tests verifying filtering behavior

Dependencies: `context.py` (would add a new method, not modify existing ones).

## What Stays Unchanged

| Module | Reason |
|--------|--------|
| `data.py` | Q&A uses `load_pitcher_data()` as-is. No API changes needed. |
| `engine.py` | All 10 compute functions used indirectly through `assemble_pitcher_context()`. No changes. |
| `context.py` | `PitcherContext` and `assemble_pitcher_context()` reused as-is. `to_prompt()` provides the Q&A context. |
| `report.py` | Narrative pipeline is a separate consumer. Q&A does not touch it. Constants (`PROVIDERS`, `THINKING_LEVELS`) may be imported. |
| `scout.py` | Appearance scoring is unrelated to Q&A. |
| `curator.py` | Curation is unrelated to Q&A. |
| `cli.py` | Existing narrative CLI unchanged. |
| `scout_cli.py` | Existing scout CLI unchanged. |

## What Gets Created

| Module | Purpose | Size Estimate |
|--------|---------|---------------|
| `resolver.py` | Name-to-ID resolution | ~100-150 lines |
| `analyst.py` | Q&A analyst agent | ~80-120 lines |
| `ask_cli.py` | Q&A CLI entry point | ~80-100 lines |
| `tests/test_resolver.py` | Resolver unit tests | ~150-200 lines |
| `tests/test_analyst.py` | Agent unit tests | ~80-120 lines |
| `tests/test_ask_cli.py` | CLI integration tests | ~80-120 lines |

**Total new code:** ~570-810 lines across 6 files. No modifications to existing files except `pyproject.toml` (adding `pitcher-ask` entry point and `rapidfuzz` dependency).

## Scalability Considerations

| Concern | v1.4 (current) | Future |
|---------|-----------------|--------|
| Name resolution speed | <5ms for 1,651 pitchers with rapidfuzz | Scales linearly, still fast at 10K+ |
| Context size | 544 tokens (well within limits) | If context grows past 2K tokens, question-aware filtering or tools become worthwhile |
| LLM latency | Single call, ~1-3 seconds | If multi-turn needed, consider tool-based approach |
| Data loading | Full parquet scan per query (~1-2s) | Could cache PitcherData for repeated questions about same pitcher |
| Pitcher index | Loaded from CSV per invocation | Could persist as a pickle/sqlite for <1ms startup |

## Confidence Assessment

| Decision | Confidence | Rationale |
|----------|------------|-----------|
| Standalone resolver (not LLM tool) | HIGH | Deterministic task, established pattern, tested in production systems |
| Pre-assembled context (not tools) | HIGH | Context is 544 tokens, tools add latency for no benefit at this scale. Measured via `to_prompt()` output. |
| Separate CLI script | HIGH | Established project pattern, zero breaking changes |
| rapidfuzz for fuzzy matching | HIGH | Industry standard, MIT license, well-documented |
| Single-call agent (no pipeline) | HIGH | Q&A is fundamentally different from narrative generation |
| Skip question-aware filtering initially | MEDIUM | Likely unnecessary at 544 tokens, but may help with specific pitch-type questions |
| `instructions` over `system_prompt` | HIGH | Future-proofs for multi-turn per STACK.md recommendation |

## Sources

- [Pydantic AI - Function Tools documentation](https://ai.pydantic.dev/tools/)
- [Pydantic AI - Dependencies and RunContext](https://ai.pydantic.dev/dependencies/)
- [Pydantic AI - Agents](https://ai.pydantic.dev/agent/)
- [RapidFuzz documentation](https://rapidfuzz.github.io/RapidFuzz/)
- [RapidFuzz GitHub](https://github.com/rapidfuzz/RapidFuzz)
- Existing codebase: `data.py`, `context.py`, `report.py`, `cli.py`, `scout_cli.py` (primary evidence for architecture decisions)
- `.planning/research/STACK.md` (v1.4 stack research, reconciled in this document)
