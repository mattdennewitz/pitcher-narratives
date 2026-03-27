# Technology Stack: v1.3 Editor-Anchor Reflection Loop

**Project:** Pitcher Narratives
**Milestone:** v1.3 -- Editor-Anchor Reflection Loop
**Researched:** 2026-03-27
**Scope:** Stack additions/changes ONLY for the reflection loop. Existing stack (Python 3.14, polars, pydantic-ai 1.72, multi-provider) is validated and unchanged.

## Executive Summary

No new dependencies are needed. The reflection loop is implementable entirely with existing pydantic-ai 1.72 primitives: `Agent.run_sync()` with `output_type` for structured anchor results, a plain Python `for` loop for iteration control, and Pydantic `BaseModel` for the anchor check's structured output. The critical decision is to use a **plain while-loop orchestrator** instead of `pydantic-graph` -- the loop topology is too simple to justify graph infrastructure, and keeping it in plain Python makes convergence logic, token tracking, and max-iteration caps trivially debuggable.

**Confidence:** HIGH -- all patterns verified against installed pydantic-ai 1.72.0 source code.

## Stack Changes for v1.3

### New Dependencies

**None.** Zero new packages required.

### What Changes

| Component | Current (v1.2) | Change for v1.3 | Why |
|-----------|----------------|------------------|-----|
| Anchor check agent | `output_type=str`, text-parsed | `output_type=AnchorResult` (Pydantic model) | Structured output enables the loop to programmatically inspect warnings without text parsing |
| Editor agent call | Single `run_sync` | Called in a loop with `user_prompt` carrying feedback | Enables revision based on anchor feedback |
| Orchestration | Linear 5-phase | Phases 2+2.5 become a while-loop, phases 1/3/4 unchanged | Only the editor-anchor pair iterates |
| `ReportResult` model | `anchor_warnings: list[str]` | Add `anchor_iterations: int`, `anchor_history: list[AnchorResult]` | Track convergence for diagnostics |

### What Does NOT Change

- Phase 1 (Synthesizer): Unchanged. Runs once, produces synthesis.
- Phase 3 (Hook Writer): Unchanged. Receives final capsule after loop converges.
- Phase 4 (Fantasy Analyst): Unchanged. Receives final capsule after loop converges.
- Agent creation (`_make_agents`): The anchor agent switches `output_type` but keeps the same model/settings.
- Streaming of Phase 2: First iteration streams as before. Revision iterations are silent (no streaming).
- All existing CLI flags and arguments.

## Key Technical Decisions

### 1. Plain While-Loop, Not pydantic-graph

**Decision:** Use a plain Python `while` loop for the editor-anchor iteration. Do NOT use `pydantic-graph`.

**Why:**

The installed `pydantic-graph` (via pydantic-ai 1.72) provides a directed graph framework (`BaseNode`, `End`, `Graph`) where nodes define edges via return type annotations and the framework manages traversal. It is designed for complex multi-step workflows with branching, parallel execution (beta `Fork`/`Join` nodes), and state persistence.

The editor-anchor loop has exactly one topology: `editor -> anchor -> (editor or done)`. This is a while-loop. Using pydantic-graph for this would require:
- Defining 3+ dataclass nodes (`EditorNode`, `AnchorNode`, `DoneNode`)
- An async `run` method on each (pydantic-graph nodes are async-only)
- A `GraphRunContext` with custom state dataclass
- Graph instantiation and `.run()` call

All of this to express `while not clean and iterations < max: revise()`. The graph infrastructure adds ~80 lines of boilerplate with zero functional benefit for a linear loop.

**When pydantic-graph WOULD make sense:** If the pipeline later needs branching (e.g., "if anchor finds directional errors, go back to synthesizer; if it finds missed signals, go back to editor"), the graph topology becomes non-trivial and pydantic-graph earns its keep. That is not v1.3's scope.

**Confidence:** HIGH -- verified by reading `pydantic_graph.nodes.BaseNode`, `pydantic_graph.graph.Graph`, and the beta graph builder source. The API is well-designed but targets a different complexity tier.

### 2. Structured Output for Anchor Check (AnchorResult Model)

**Decision:** Change the anchor check agent from `output_type=str` to `output_type=AnchorResult` where `AnchorResult` is a Pydantic model.

**Why:** The current anchor check returns free text that gets split on newlines and checked for "CLEAN". This works for one-shot checking but breaks down for a feedback loop because:
1. The editor needs to know WHICH warnings to address, with typed categories
2. The loop needs a boolean `is_clean` to decide whether to continue
3. Convergence tracking needs structured warning counts per iteration

**Pattern (verified against pydantic-ai 1.72.0 source):**

```python
from pydantic import BaseModel, Field
from typing import Literal

class AnchorWarning(BaseModel):
    """A single warning from the anchor check."""
    category: Literal[
        "MISSED_SIGNAL",
        "UNSUPPORTED",
        "DIRECTION_ERROR",
        "OVERSTATED",
    ]
    detail: str = Field(description="One-line description of the issue")

class AnchorResult(BaseModel):
    """Structured output from the anchor check agent."""
    is_clean: bool = Field(
        description="True if the capsule is faithful to the synthesis with no issues"
    )
    warnings: list[AnchorWarning] = Field(
        default_factory=list,
        description="List of specific issues found. Empty if is_clean is True."
    )
```

The anchor check agent then uses `output_type=AnchorResult`:

```python
anchor_checker = Agent(
    model,
    output_type=AnchorResult,
    system_prompt=_ANCHOR_PROMPT,
    model_settings=settings,
    defer_model_check=True,
)
```

pydantic-ai 1.72 handles this via tool-based structured output: it presents the Pydantic schema as a tool the LLM must call, validates the response, and retries on validation failure (up to `retries` count, default 1). This is the standard pydantic-ai pattern -- the same mechanism used for any `BaseModel` output type.

**Anchor prompt adjustment:** The `_ANCHOR_PROMPT` must be updated to instruct the LLM to respond using the structured format. The current prompt already defines the categories (`[MISSED SIGNAL]`, `[UNSUPPORTED]`, etc.) which map directly to the `AnchorWarning.category` enum.

**Confidence:** HIGH -- verified `Agent.__init__` accepts `output_type: OutputSpec[OutputDataT]`, and `run_sync` returns `AgentRunResult[OutputDataT]` where `.output` is the validated Pydantic model instance.

### 3. Editor Revision via Fresh Prompt (Not message_history)

**Decision:** Each editor revision is a fresh `run_sync` call with the anchor feedback injected into the user prompt. Do NOT use `message_history` for multi-turn conversation.

**Why:**

pydantic-ai 1.72's `run_sync` accepts `message_history: Sequence[ModelMessage]` which enables multi-turn conversations by passing `result.all_messages()` from a previous run. This seems like a natural fit for "revise your previous output." However, for this use case, a fresh prompt is better:

1. **Token efficiency:** The editor's system prompt is ~3000 tokens. The synthesis is ~2000 tokens. A conversation history approach accumulates ALL previous editor outputs and anchor feedback as message history, meaning iteration 3 sends iteration 1's full output + anchor feedback + iteration 2's full output + anchor feedback + new prompt. With a fresh prompt, each iteration sends only: system prompt + synthesis + previous capsule + anchor warnings. The delta is significant: ~5K constant per iteration (fresh) vs ~5K + 3K per previous iteration (history).

2. **Prompt clarity:** A fresh prompt with explicit instructions ("Here is your previous capsule. Here are the anchor check's findings. Revise the capsule to address these specific issues.") is clearer to the LLM than a multi-turn conversation where the model must infer what changed between turns.

3. **Streaming control:** The first editor pass streams to stdout. Revision passes are silent. With `message_history`, the agent treats it as one continuous conversation and streaming behavior becomes harder to control per-iteration.

**Pattern:**

```python
def _build_editor_revision_message(
    ctx: PitcherContext,
    synthesis: str,
    previous_capsule: str,
    anchor_result: AnchorResult,
) -> _UserPrompt:
    """Build editor prompt for a revision pass."""
    warnings_text = "\n".join(
        f"- [{w.category}] {w.detail}" for w in anchor_result.warnings
    )
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Key Findings From Data Analysis\n{synthesis}",
        CachePoint(),
        f"## Your Previous Capsule\n{previous_capsule}\n\n"
        f"## Anchor Check Findings\n{warnings_text}\n\n"
        "Revise the capsule to address these specific issues. "
        "Preserve the parts that were not flagged. "
        "Do not over-correct -- fix only what the anchor check identified.",
    ]
```

The `CachePoint()` after the synthesis is key: the synthesis and pitcher context are identical across all iterations, so pydantic-ai's prompt caching (via Anthropic's cache control) avoids re-processing those tokens. Only the revision-specific content after the cache point changes per iteration.

**Confidence:** HIGH -- verified `CachePoint` import in existing codebase, and `message_history` parameter signature in `run_sync`.

### 4. Convergence Tracking with Dataclasses

**Decision:** Track iteration state with a simple dataclass, not a separate tracking library.

```python
from dataclasses import dataclass, field
from pydantic_ai.usage import RunUsage

@dataclass
class ReflectionTrace:
    """Tracks the editor-anchor reflection loop state."""
    iterations: int = 0
    max_iterations: int = 3
    history: list[AnchorResult] = field(default_factory=list)
    usage_per_iteration: list[RunUsage] = field(default_factory=list)

    @property
    def converged(self) -> bool:
        """True if the last anchor check was clean."""
        return bool(self.history) and self.history[-1].is_clean

    @property
    def exhausted(self) -> bool:
        """True if max iterations reached without convergence."""
        return self.iterations >= self.max_iterations and not self.converged

    @property
    def surviving_warnings(self) -> list[AnchorWarning]:
        """Warnings from the final iteration (if not converged)."""
        if self.converged or not self.history:
            return []
        return self.history[-1].warnings

    @property
    def total_usage(self) -> RunUsage:
        """Aggregate token usage across all iterations."""
        total = RunUsage()
        for u in self.usage_per_iteration:
            total.incr(u)
        return total
```

pydantic-ai's `RunUsage` class (verified in installed source) has an `incr()` method that accumulates token counts, making it trivial to sum usage across iterations. Each `AgentRunResult` exposes `.usage()` returning a `RunUsage` with `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, and `requests` fields.

**Confidence:** HIGH -- `RunUsage.incr()` verified in installed pydantic_ai/usage.py.

### 5. Max Iteration Cap: Default 3

**Decision:** Default `max_iterations=3` for the reflection loop.

**Why:**
- Iteration 1: Initial anchor check. Most capsules pass or have 1-2 issues.
- Iteration 2: Editor revises. Fixes most issues.
- Iteration 3: Safety net for stubborn issues or regressions from revision.
- Beyond 3: Diminishing returns. If the editor cannot fix an issue in 3 passes, it likely cannot fix it at all -- the issue may be a genuine tension between synthesis data and narrative framing.

At ~5K input tokens + ~2K output tokens per editor+anchor iteration pair, 3 iterations adds at most ~21K tokens (~$0.06 at Sonnet 4.6 pricing) on top of the base pipeline cost. This is well within acceptable bounds.

**Configurable:** Expose as a CLI flag (`--max-revisions N`) for power users. Default to 3.

**Confidence:** MEDIUM -- the cap of 3 is a design judgment, not empirically validated. May need tuning after observing real loop behavior. Start at 3, instrument to measure.

## Orchestration Pattern (Complete)

The full reflection loop in the context of the existing pipeline:

```python
def generate_report_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
    max_revisions: int = 3,
    _model_override: Any = None,
) -> ReportResult:
    """Generate report with editor-anchor reflection loop."""
    synthesizer, editor, hook_writer, fantasy_analyst, anchor_checker = _make_agents(provider, thinking)

    # Phase 1: Synthesis (unchanged)
    synthesis = synthesizer.run_sync(
        user_prompt=_build_synthesizer_message(ctx),
        model=_model_override,
    ).output

    # Phase 2: Initial editor pass (streamed)
    stream = editor.run_stream_sync(
        user_prompt=_build_editor_message(ctx, synthesis),
        model=_model_override,
    )
    capsule = _collect_streamed_output(stream)  # prints to stdout

    # Phase 2.5: Reflection loop
    trace = ReflectionTrace(max_iterations=max_revisions)
    for _ in range(max_revisions):
        # Anchor check
        anchor_result = anchor_checker.run_sync(
            user_prompt=_build_anchor_message(synthesis, capsule),
            model=_model_override,
        )
        trace.iterations += 1
        trace.history.append(anchor_result.output)
        trace.usage_per_iteration.append(anchor_result.usage())

        if anchor_result.output.is_clean:
            break

        # Editor revision (silent -- no streaming)
        revision_result = editor.run_sync(
            user_prompt=_build_editor_revision_message(
                ctx, synthesis, capsule, anchor_result.output,
            ),
            model=_model_override,
        )
        capsule = revision_result.output
        trace.usage_per_iteration.append(revision_result.usage())

    # Phases 3 + 4: Downstream (unchanged, use final capsule)
    hook = hook_writer.run_sync(...).output
    fantasy = fantasy_analyst.run_sync(...).output

    return ReportResult(
        narrative=capsule,
        social_hook=hook,
        fantasy_insights=fantasy,
        anchor_warnings=[
            f"[{w.category}] {w.detail}"
            for w in trace.surviving_warnings
        ],
        anchor_iterations=trace.iterations,
    )
```

## Alternatives Considered

| Decision | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Loop orchestration | Plain while-loop | pydantic-graph `Graph` | Graph adds ~80 lines of async boilerplate for a topology that is literally `while not done`. Overkill. Consider if branching is added later. |
| Loop orchestration | Plain while-loop | pydantic-graph beta `GraphBuilder` | Same problem. Beta API adds step/decision/fork/join abstractions designed for parallel execution and complex branching. Not this use case. |
| Editor feedback | Fresh prompt per iteration | `message_history` conversation | Token accumulation across turns is wasteful. Fresh prompt with explicit revision instructions is clearer and cheaper. CachePoint reuse makes the constant part free. |
| Anchor output | `output_type=AnchorResult` (Pydantic) | `output_type=str` with text parsing | Text parsing is fragile. Structured output enables programmatic loop control and typed warning categories. |
| Anchor output | `output_type=AnchorResult` (Pydantic) | `output_type=str` with a second LLM call to parse | Two LLM calls for one check is wasteful. Structured output via pydantic-ai does it in one call with validation. |
| Iteration tracking | Dataclass with RunUsage | Logfire/OpenTelemetry spans | Logfire is available transitively but adds observability complexity for a CLI tool. A dataclass is sufficient for v1.3. Instrument with OTel later if needed. |

## What NOT to Add

| Avoid | Why | Risk if Added |
|-------|-----|---------------|
| New dependencies | Everything needed is already in pydantic-ai 1.72 | Dependency bloat, version conflicts, maintenance burden |
| pydantic-graph for the loop | Over-engineering a while-loop. Async boilerplate for a sync CLI. | 80+ lines of boilerplate, harder to debug, async/sync bridge complexity |
| LangGraph / CrewAI / AutoGen | External multi-agent frameworks | Massive dependency trees, incompatible abstractions with existing pydantic-ai pipeline, learning curve for marginal benefit |
| Custom retry/backoff library | pydantic-ai already handles LLM retries internally | Conflicting retry layers, doubled wait times |
| Database/persistence for loop state | The loop runs in-memory in a single CLI invocation | Storage overhead for ephemeral state that lives <30 seconds |
| Async conversion | The CLI is synchronous. `run_sync` is the correct API. | Would require async runtime setup (asyncio.run) throughout, for zero benefit in a CLI that blocks on LLM calls anyway |
| Separate "revision" agent | Editor revises itself with feedback. No need for a third agent. | Extra model/prompt configuration, unclear responsibility boundary, more LLM calls |

## Integration with Existing Code

### Files Modified

| File | Change | Impact |
|------|--------|--------|
| `report.py` | Add `AnchorResult`/`AnchorWarning` models, `ReflectionTrace`, revision prompt builder, loop logic in `generate_report_streaming` | Primary change. ~100 lines added, ~20 lines modified. |
| `report.py` | Anchor agent `output_type` changes from `str` to `AnchorResult` | Breaking change to `_make_agents` return types. Update type alias. |
| `report.py` | `ReportResult` gets `anchor_iterations: int` field | Additive. Downstream consumers (cli.py) can optionally display it. |
| `cli.py` | Add `--max-revisions` flag, display iteration count in output | ~10 lines. |
| `tests/test_report.py` | Update tests for new anchor output type, add loop convergence tests | ~60 lines of new tests. |

### Files NOT Modified

| File | Why Unchanged |
|------|---------------|
| `data.py` | Data loading is unrelated to the reflection loop |
| `engine.py` | Computation engine is unrelated |
| `context.py` | Context assembly is unrelated |
| `scout.py` | Scout scoring is unrelated |
| `curator.py` | LLM curation is unrelated |
| `pyproject.toml` | No new dependencies |

### Testing Pattern

The existing test suite uses `pydantic_ai.models.test.TestModel` for deterministic LLM testing. The reflection loop tests should follow the same pattern:

```python
from pydantic_ai.models.test import TestModel

def test_reflection_loop_converges_on_clean():
    """Loop exits after one iteration when anchor returns clean."""
    # TestModel returns whatever output_type expects with default values
    # For AnchorResult, that means is_clean=False, warnings=[]
    # Override with custom_output_text or similar
    ...

def test_reflection_loop_caps_at_max_iterations():
    """Loop stops after max_iterations even if not clean."""
    ...

def test_reflection_loop_passes_warnings_to_editor():
    """Editor revision prompt contains anchor warnings."""
    ...
```

**Confidence:** HIGH -- `TestModel` usage pattern verified in existing `tests/test_report.py`.

## Sources

All findings verified against installed source code at:
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/` (v1.72.0)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_graph/` (v1.72.0)
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/report.py` (current pipeline)
- `/Users/matt/src/pitcher-narratives/tests/test_report.py` (test patterns)

| Source | What Verified | Confidence |
|--------|---------------|------------|
| `pydantic_ai/agent/abstract.py` | `run_sync` signature: `output_type`, `message_history`, `usage` parameters | HIGH |
| `pydantic_ai/run.py` | `AgentRunResult.output`, `.usage()`, `.all_messages()` API | HIGH |
| `pydantic_ai/usage.py` | `RunUsage.incr()` for accumulating token usage across iterations | HIGH |
| `pydantic_ai/result.py` | `StreamedRunResultSync.all_messages()` for conversation history | HIGH |
| `pydantic_graph/nodes.py` | `BaseNode`, `End`, `GraphRunContext` -- async-only, typed edges | HIGH |
| `pydantic_graph/graph.py` | `Graph` class -- async `.run()`, state management | HIGH |
| `pydantic_graph/beta/` | Fork/Join/Decision nodes -- parallel execution framework | HIGH |
| `report.py` (current) | Existing 5-phase pipeline structure, `CachePoint` usage, `_make_agents` pattern | HIGH |

---
*Stack research for: v1.3 Editor-Anchor Reflection Loop*
*Researched: 2026-03-27*
