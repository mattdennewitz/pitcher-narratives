# Architecture: Editor-Anchor Reflection Loop

**Domain:** LLM self-refinement / actor-critic loop integration
**Researched:** 2026-03-27
**Confidence:** HIGH

## Problem Statement

The current pipeline runs Phase 2 (Editor) then Phase 2.5 (Anchor Check) once. The anchor check produces warnings -- missed signals, unsupported claims, directional errors, overstated confidence -- but those warnings are printed to stderr and never acted upon. The capsule goes to downstream phases (hook writer, fantasy analyst) unchanged, even when the anchor identifies problems.

The v1.3 milestone closes this loop: anchor warnings feed back to the editor, the editor revises, and the cycle repeats until the capsule is CLEAN or a max iteration cap is hit.

## Current Architecture (What Exists)

```
generate_report_streaming()
    |
    Phase 1: synthesizer.run_sync(ctx)  --> synthesis (str)
    |
    Phase 2: editor.run_stream_sync(synthesis)  --> capsule (str, streamed)
    |
    Phase 2.5: anchor_checker.run_sync(synthesis, capsule)  --> "CLEAN" | warnings[]
    |
    Phase 3: hook_writer.run_sync(capsule)  --> social_hook (str)
    |
    Phase 4: fantasy_analyst.run_sync(capsule)  --> fantasy_insights (str)
    |
    return ReportResult(narrative, social_hook, fantasy_insights, anchor_warnings)
```

Key facts about the current code:
- All 5 agents are created by `_make_agents()` which returns a tuple of `Agent[None, str]`
- The editor uses `run_stream_sync()` for Phase 2 (streaming to stdout)
- The anchor checker uses `run_sync()` and returns str
- Anchor output is parsed: "CLEAN" means no issues, otherwise each line is a warning
- `ReportResult` has `anchor_warnings: list[str]` field
- `_build_editor_message()` takes `(ctx, synthesis)` and returns a prompt list
- `_build_anchor_message()` takes `(synthesis, capsule)` and returns a prompt list
- The editor and anchor checker are separate Agent instances with different system prompts
- The pipeline is synchronous throughout (`run_sync` / `run_stream_sync`)

## Architectural Options Evaluated

### Option A: Simple While Loop (RECOMMENDED)

Replace the single editor-then-anchor block with a `while` loop inside `generate_report_streaming()`.

```python
# Phase 2 + 2.5: Editor-Anchor reflection loop
MAX_REVISIONS = 2
capsule = _run_editor(editor, ctx, synthesis, _model_override)  # first pass (streamed)

for revision in range(MAX_REVISIONS):
    warnings = _run_anchor_check(anchor_checker, synthesis, capsule, _model_override)
    if not warnings:
        break  # CLEAN -- capsule is faithful
    # Feed warnings back to editor for revision
    capsule = _run_editor_revision(editor, ctx, synthesis, capsule, warnings, _model_override)

# Warnings that survive the loop
surviving_warnings = _run_anchor_check(anchor_checker, synthesis, capsule, _model_override)
```

**Pros:**
- Zero new dependencies or abstractions
- Fits naturally into the existing synchronous flow
- Easy to understand: it is a loop
- Testing is straightforward: mock TestModel with different outputs per call
- The iteration cap, warning tracking, and convergence check are all plain Python
- Streaming only happens on the first pass (subsequent revisions are silent, which is correct UX)

**Cons:**
- No formal state machine -- the "state" is local variables (`capsule`, `warnings`, `revision`)
- If the loop logic grows (e.g., different strategies per warning type), the function body gets long

**Verdict:** This is the right choice. The loop has exactly two participants (editor, anchor), one piece of state (the capsule), and a simple termination condition (CLEAN or max iterations). A state machine framework adds abstraction tax with no payoff at this scale.

### Option B: pydantic-graph State Machine

Model the reflection loop as a graph with nodes for EditorRevise and AnchorCheck that can cycle.

```python
@dataclass
class LoopState:
    synthesis: str
    capsule: str
    iteration: int = 0
    warnings: list[str] = field(default_factory=list)

@dataclass
class EditorRevise(BaseNode[LoopState]):
    async def run(self, ctx: GraphRunContext[LoopState]) -> AnchorCheck:
        ctx.state.capsule = await editor.run(...)
        ctx.state.iteration += 1
        return AnchorCheck()

@dataclass
class AnchorCheck(BaseNode[LoopState]):
    async def run(self, ctx: GraphRunContext[LoopState]) -> EditorRevise | End[str]:
        result = await anchor.run(...)
        if result == "CLEAN" or ctx.state.iteration >= MAX:
            return End(ctx.state.capsule)
        ctx.state.warnings = parse_warnings(result)
        return EditorRevise()
```

**Pros:**
- Formal state machine with typed transitions
- Graph visualization (mermaid) for documentation
- Persistence support if you need to resume a loop mid-run

**Cons:**
- pydantic-graph is async-only (`BaseNode.run()` is `async def`). The current pipeline is synchronous. Converting to async requires changing `generate_report_streaming()` signature and all callers, plus handling the async streaming differently.
- Adds a dependency on `pydantic-graph` (currently unused in the project despite being installed transitively)
- The graph has exactly 2 nodes and 1 cycle. The framework overhead (State class, BaseNode subclasses, Graph constructor, async runner) dwarfs the actual logic.
- Testing requires async test fixtures
- Breaks the clean sequential flow of `generate_report_streaming()` -- the loop becomes an async subgraph embedded in a sync function

**Verdict:** Overengineered. pydantic-graph is designed for multi-step agent workflows with branching, persistence, and complex state. A 2-node cycle is not that. Revisit if the pipeline grows to 10+ nodes with branching logic.

### Option C: Custom Orchestrator Class

Extract the loop into a `ReflectionLoop` class that encapsulates the editor-anchor cycle.

```python
class ReflectionLoop:
    def __init__(self, editor, anchor, max_revisions=2):
        self.editor = editor
        self.anchor = anchor
        self.max_revisions = max_revisions

    def run(self, ctx, synthesis, model_override=None) -> ReflectionResult:
        capsule = self._first_pass(ctx, synthesis, model_override)
        for i in range(self.max_revisions):
            warnings = self._anchor_check(synthesis, capsule, model_override)
            if not warnings:
                return ReflectionResult(capsule=capsule, iterations=i+1, warnings=[])
            capsule = self._revise(ctx, synthesis, capsule, warnings, model_override)
        final_warnings = self._anchor_check(synthesis, capsule, model_override)
        return ReflectionResult(capsule=capsule, iterations=self.max_revisions+1, warnings=final_warnings)
```

**Pros:**
- Clean separation of loop logic from pipeline orchestration
- Testable in isolation
- Encapsulates iteration tracking, convergence detection

**Cons:**
- Adds a class where a function suffices
- The "orchestrator" has one method (`run`) and holds two agents -- it is a function wearing a class costume
- Adds indirection: reader must find the class to understand what happens between Phase 2 and Phase 3

**Verdict:** Premature abstraction. If the loop gains complexity (warning-type-specific strategies, rollback logic, multi-capsule comparison), extract then. For v1.3 the function-level while loop is clearer.

## Recommended Architecture

### The While Loop with Helper Functions

The reflection loop lives inside `generate_report_streaming()` as a bounded while loop, with the messy parts extracted into helper functions. No new files, no new classes, no new abstractions.

```
generate_report_streaming()
    |
    Phase 1: synthesizer.run_sync(ctx)  --> synthesis
    |
    Phase 2 + 2.5: REFLECTION LOOP
    |   |
    |   |-- _run_editor_first_pass(editor, ctx, synthesis)  --> capsule (STREAMED)
    |   |
    |   |-- for revision in range(MAX_REVISIONS):
    |   |     |-- warnings = _parse_anchor_output(anchor_checker.run_sync(...))
    |   |     |-- if not warnings: break
    |   |     |-- capsule = _run_editor_revision(editor, ctx, synthesis, capsule, warnings)
    |   |
    |   |-- final_warnings = _parse_anchor_output(anchor_checker.run_sync(...))
    |   |
    |   return (capsule, final_warnings, iteration_count)
    |
    Phase 3: hook_writer.run_sync(capsule)
    |
    Phase 4: fantasy_analyst.run_sync(capsule)
    |
    return ReportResult(...)
```

### Component Boundaries

| Component | Responsibility | New/Modified | Communicates With |
|-----------|---------------|--------------|-------------------|
| `generate_report_streaming()` | Top-level pipeline orchestration | MODIFIED -- loop replaces single editor+anchor block | All agents |
| `_run_editor_first_pass()` | First editor call with streaming output | NEW helper function | editor agent, stdout |
| `_run_editor_revision()` | Subsequent editor calls (silent, non-streaming) | NEW helper function | editor agent |
| `_build_revision_message()` | Build editor prompt with anchor feedback appended | NEW message builder | None (pure function) |
| `_parse_anchor_output()` | Parse anchor output into warnings list (extracted from inline code) | NEW helper (extracted) | None (pure function) |
| `ReportResult` | Pipeline output model | MODIFIED -- add `revision_count: int` field | CLI consumer |
| `_make_agents()` | Agent factory | UNCHANGED | N/A |

### Data Flow

```
                    synthesis (str, from Phase 1)
                         |
                         v
            +------------------------+
            | Editor (first pass)    |
            | Streamed to stdout     |
            +------------------------+
                         |
                    capsule_v1 (str)
                         |
          +--------------+--------------+
          |                             |
          v                             |
    +-------------+                     |
    | Anchor      |                     |
    | Check       |                     |
    +-------------+                     |
          |                             |
    warnings or CLEAN                   |
          |                             |
    [if CLEAN] -----> capsule_v1 used --+----> Phase 3, Phase 4
          |
    [if warnings]
          |
          v
    +------------------------+
    | Editor (revision)      |
    | Receives: synthesis    |
    |   + capsule_v1         |
    |   + anchor warnings    |
    | Silent (no streaming)  |
    +------------------------+
          |
    capsule_v2 (str)
          |
          v
    +-------------+
    | Anchor      |  (loop back if still dirty, up to MAX_REVISIONS)
    | Check       |
    +-------------+
          |
    CLEAN or surviving warnings
          |
          v
    Final capsule ---> Phase 3, Phase 4
```

## Critical Design Decisions

### 1. How the Editor Receives Anchor Feedback

**Decision:** New user message with synthesis + previous capsule + anchor warnings, NOT via message_history.

**Rationale:** The editor agent has a system prompt optimized for writing from a synthesis briefing. Using `message_history` would carry forward the full conversation context (system prompt + original user message + first response + anchor feedback), which:
- Doubles the token cost (the full synthesis appears twice)
- Includes the first capsule as a model response, which the LLM may anchor to instead of revising
- Makes the revision prompt harder to control

Instead, build a new `_build_revision_message()` that gives the editor:
1. The original synthesis (source of truth)
2. The previous capsule (what to revise)
3. The specific anchor warnings (what to fix)
4. A revision instruction ("Revise the capsule to address these issues")

This is a fresh editor call with a targeted prompt, not a conversation continuation. The editor should not "remember" its first attempt through message history -- it should receive explicit instructions about what to change.

```python
def _build_revision_message(
    ctx: PitcherContext,
    synthesis: str,
    capsule: str,
    warnings: list[str],
) -> _UserPrompt:
    """Build editor prompt for a revision pass with anchor feedback."""
    warning_block = "\n".join(f"- {w}" for w in warnings)
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Key Findings From Data Analysis\n{synthesis}",
        CachePoint(),
        f"## Your Previous Capsule\n{capsule}\n\n"
        f"## Anchor Check Findings\n{warning_block}\n\n"
        "Revise the capsule to address each finding above. Maintain the same "
        "voice and structure. Do not add information beyond the synthesis. "
        "If a finding asks you to include a missed signal, weave it in naturally. "
        "If a finding flags an unsupported claim, remove or correct it.",
    ]
```

**Why CachePoint after synthesis:** The synthesis is identical across all revision passes for the same pitcher. Caching it avoids re-processing those tokens on each revision.

### 2. Streaming Only on First Pass

**Decision:** Stream Phase 2 first pass to stdout. Revision passes run silently via `run_sync()`.

**Rationale:** The user sees the initial capsule stream in real-time. If revisions happen, they occur silently -- the user does not need to watch the capsule being rewritten. The final capsule (post-revision) replaces what was streamed. The CLI can print a note like "Revised (2 passes)" to stderr.

This avoids the UX problem of streaming a capsule, then streaming a different capsule, confusing the reader. The first stream is the draft; the final output is what gets used downstream.

**Implementation note:** This means `_run_editor_first_pass()` uses `editor.run_stream_sync()` and prints to stdout, while `_run_editor_revision()` uses `editor.run_sync()` silently.

### 3. Max Revisions = 2

**Decision:** Cap at 2 revision passes (so the editor gets at most 3 total attempts: 1 initial + 2 revisions).

**Rationale:**
- Each revision is a full LLM call (~5-10s, ~2K-4K tokens). Three total attempts means 3 editor calls + 3 anchor checks = 6 LLM calls for the edit-check loop alone (on top of synthesizer, hook, fantasy = 9 total, up from current 5).
- In practice, most anchor issues are first-pass problems: the editor missed a key signal or overstated something. One revision pass typically resolves these. Two revisions handle edge cases where the first revision introduced a new issue.
- If the capsule is not clean after 3 attempts, it has a systematic problem (the synthesis is ambiguous, or the editor and anchor disagree on interpretation). Looping further will not help. Surface the surviving warnings and let the user decide.
- The cap is a constant (`MAX_REVISIONS = 2`) that can be tuned without code changes.

### 4. ReportResult Changes

**Decision:** Add `revision_count: int` to `ReportResult`. Keep `anchor_warnings: list[str]` for surviving warnings only.

```python
class ReportResult(BaseModel):
    narrative: str
    social_hook: str
    fantasy_insights: str
    anchor_warnings: list[str]   # surviving warnings after loop (was: all warnings)
    revision_count: int           # NEW: 0 = clean first pass, 1-2 = revised
```

**Rationale:** Downstream consumers (CLI output, potential future logging) need to know:
- Whether any revisions occurred (for cost/latency tracking)
- What warnings survived (for quality monitoring)

The semantics of `anchor_warnings` change slightly: currently it is "all warnings from the single anchor pass." After v1.3, it means "warnings that survived the full reflection loop." This is a breaking change but the only consumer is `cli.py`, which we control.

### 5. Parse Anchor Output as a Separate Function

**Decision:** Extract `_parse_anchor_output(raw: str) -> list[str]` from the inline code.

Currently the anchor parsing is inline:
```python
anchor_output = anchor_result.output.strip()
anchor_warnings: list[str] = []
if anchor_output != "CLEAN":
    anchor_warnings = [line.strip() for line in anchor_output.splitlines() if line.strip()]
```

Extract to:
```python
def _parse_anchor_output(raw: str) -> list[str]:
    """Parse anchor check output into a list of warnings. Empty list = CLEAN."""
    stripped = raw.strip()
    if stripped == "CLEAN":
        return []
    return [line.strip() for line in stripped.splitlines() if line.strip()]
```

**Rationale:** The loop calls the anchor check multiple times. Without extraction, the parsing logic is duplicated. The function is also independently testable.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Using message_history for the Revision Loop

**What:** Pass `message_history=first_pass.all_messages()` to the editor's revision call, appending the anchor warnings as a new user message in the ongoing conversation.

**Why it is wrong:** The editor's system prompt says "Write the two-paragraph scouting capsule now." In a conversation continuation, the model sees its own first capsule as an assistant response, then gets told "fix these things." This creates anchoring bias -- the model tries to minimally edit rather than cleanly rewrite. It also doubles the prompt tokens (full synthesis appears in the history plus the new prompt). And it carries over any reasoning/thinking tokens from the first pass, further inflating cost.

**Do this instead:** Fresh editor call with `_build_revision_message()` that explicitly provides the capsule as user-message context, not as the model's own prior output. The editor rewrites from scratch with the anchor findings in view.

### Anti-Pattern 2: Streaming Revision Passes

**What:** Stream every editor pass to stdout, showing the user each draft in real-time.

**Why it is wrong:** Confusing UX. The user sees a complete capsule, then sees it being overwritten by a different capsule. This is visually jarring and makes the output unreadable in a pipe or redirect.

**Do this instead:** Stream only the first pass. Run revisions silently. If a revision occurred, print a status note to stderr ("Capsule revised, 2 passes") and output the final capsule as the definitive version.

### Anti-Pattern 3: Per-Warning-Type Revision Strategy

**What:** Parse the anchor warning type brackets (`[MISSED SIGNAL]`, `[UNSUPPORTED]`, `[DIRECTION ERROR]`, `[OVERSTATED]`) and route each to a different revision strategy or agent.

**Why it is wrong for v1.3:** The editor is a capable LLM. It can read "you missed X, you made up Y, you got Z backwards" and fix all three in a single revision pass. Routing warnings to different strategies adds complexity with no quality gain. The anchor warning format is already clear and actionable.

**Do this instead:** Pass all warnings to the editor in a single revision prompt. Let the LLM handle the multi-issue revision holistically. If a specific warning type proves systematically resistant to revision (discovered through v1.3 usage), add targeted handling then.

### Anti-Pattern 4: Infinite Loop Without Hard Cap

**What:** Loop until CLEAN with no iteration limit.

**Why it is wrong:** The editor and anchor are both LLMs. They can disagree indefinitely. The anchor might flag something the editor considers acceptable editorial judgment. Or the editor's revision might introduce a new issue the anchor catches, creating an oscillation. Without a hard cap, this burns unbounded API calls.

**Do this instead:** `MAX_REVISIONS = 2` as a constant. Log surviving warnings. Let the user see what the anchor was unhappy about.

## Integration Points

### Modified Components

| File | What Changes | Why |
|------|-------------|-----|
| `report.py` | `generate_report_streaming()` gains reflection loop; new helper functions added; `ReportResult` gets `revision_count` | Core integration point |
| `cli.py` | Print revision count to stderr; adjust anchor warning display | Consumer of new `revision_count` field |
| `tests/test_report.py` | New tests for loop behavior, revision message builder, anchor parsing | Test coverage |

### Unchanged Components

| File | Why Unchanged |
|------|--------------|
| `data.py`, `engine.py`, `context.py` | Data pipeline is upstream of the loop; no changes needed |
| `scout.py`, `curator.py`, `scout_cli.py` | Independent CLI; no connection to report pipeline loop |
| Agent system prompts (synthesizer, hook, fantasy) | Unaffected by editor-anchor loop |
| `_ANCHOR_PROMPT` | Anchor prompt is already designed for this -- it checks capsule against synthesis and returns typed warnings. No changes needed. |
| `_EDITOR_PROMPT` | The editor's system prompt defines how to write from a synthesis. The revision instruction comes in the user message, not the system prompt. |

### New Components (All in report.py)

| Component | Type | Purpose |
|-----------|------|---------|
| `_build_revision_message()` | Function | Build editor prompt with anchor feedback |
| `_parse_anchor_output()` | Function | Extract warnings from anchor output string |
| `_run_editor_first_pass()` | Function | First editor call with streaming |
| `_run_editor_revision()` | Function | Subsequent editor calls, silent |
| `MAX_REVISIONS` | Constant | Iteration cap (default: 2) |
| `ReportResult.revision_count` | Field | Track iteration count in output |

## Build Order

The reflection loop is a localized change to `report.py` with no upstream dependencies. Build order follows the dependency chain within the loop:

### Phase 1: Foundation (no dependencies)

1. **`_parse_anchor_output()`** -- Extract from inline code. Pure function, trivially testable.
2. **`_build_revision_message()`** -- New message builder. Depends only on `PitcherContext` and `CachePoint` (both exist).
3. **`ReportResult` update** -- Add `revision_count: int` field.

### Phase 2: Loop Mechanics (depends on Phase 1)

4. **`_run_editor_first_pass()`** -- Extract current streaming editor block into helper.
5. **`_run_editor_revision()`** -- New function using `_build_revision_message()` + `editor.run_sync()`.
6. **Reflection loop in `generate_report_streaming()`** -- Replace single editor+anchor block with while loop using the helpers.

### Phase 3: Consumer Updates (depends on Phase 2)

7. **`cli.py` updates** -- Display `revision_count`, adjust anchor warning display.
8. **Test updates** -- Tests for `_parse_anchor_output`, `_build_revision_message`, loop convergence, max iteration cap, ReportResult changes.

### Rationale

- Phase 1 components are independently testable with no side effects
- Phase 2 depends on Phase 1 helpers existing
- Phase 3 is purely cosmetic/testing -- the loop works without CLI changes or tests
- Each phase can be committed and verified independently

## Testing Strategy

### Unit Tests (new)

| Test | What It Verifies |
|------|-----------------|
| `test_parse_anchor_output_clean` | "CLEAN" returns empty list |
| `test_parse_anchor_output_warnings` | Multi-line warnings parsed correctly |
| `test_parse_anchor_output_whitespace` | Handles blank lines, trailing whitespace |
| `test_build_revision_message_includes_warnings` | All warnings appear in prompt |
| `test_build_revision_message_includes_synthesis` | Synthesis present for editor context |
| `test_build_revision_message_includes_capsule` | Previous capsule present for reference |
| `test_build_revision_message_has_cache_point` | CachePoint after synthesis for token savings |

### Integration Tests (modified)

| Test | What It Verifies |
|------|-----------------|
| `test_generate_report_clean_first_pass` | TestModel returns "CLEAN" anchor -> revision_count=0 |
| `test_generate_report_revision_then_clean` | TestModel returns warnings then CLEAN -> revision_count=1 |
| `test_generate_report_max_revisions` | TestModel always returns warnings -> revision_count=MAX_REVISIONS, surviving warnings populated |
| `test_report_result_has_revision_count` | ReportResult includes revision_count field |

**Testing the loop with TestModel:** pydantic-ai's `TestModel` returns the same `custom_output_text` for every call. To test the loop properly, use `TestModel` with a call counter or mock that returns different outputs on successive calls. Alternatively, use `FunctionModel` which accepts a callable that can vary its response.

## Cost/Latency Impact

| Scenario | LLM Calls (current) | LLM Calls (v1.3) | Delta |
|----------|---------------------|-------------------|-------|
| Clean first pass | 5 | 5 | +0 (no change) |
| One revision needed | 5 | 7 (+1 editor, +1 anchor) | +2 |
| Two revisions needed | 5 | 9 (+2 editor, +2 anchor) | +4 |
| Max cap hit | 5 | 9 | +4 |

At ~$0.003/call (Sonnet 4.6 at ~2K tokens), worst case adds ~$0.012 per report. At ~8s/call, worst case adds ~32s latency. The clean-first-pass case (expected to be most common) adds zero overhead.

## Sources

- [pydantic-ai Agent documentation](https://ai.pydantic.dev/agents/) -- Agent.run_sync, run_stream_sync, message_history API
- [pydantic-ai Message History](https://ai.pydantic.dev/message-history/) -- message_history vs instructions vs system_prompt behavior
- [pydantic-graph documentation](https://ai.pydantic.dev/graph/) -- BaseNode, Graph, cycle support, async-only constraint
- Existing `report.py` (v1.2) -- current pipeline structure, agent factory, message builders
- Existing `cli.py` (v1.2) -- ReportResult consumption pattern
- Existing `tests/test_report.py` -- current test patterns, TestModel usage

---
*Architecture research for: pitcher-narratives v1.3 Editor-Anchor Reflection Loop*
*Researched: 2026-03-27*
