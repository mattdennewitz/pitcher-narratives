# Phase 6: Loop Mechanics - Research

**Researched:** 2026-03-28
**Domain:** Reflection loop wiring, streaming control, pydantic-ai agent orchestration
**Confidence:** HIGH

## Summary

Phase 6 wires the editor-anchor reflection loop into the existing `generate_report_streaming()` function. All building blocks are in place from Phase 5: `AnchorResult` with `is_clean` property, `AnchorWarning` typed warnings, `_build_revision_message()` prompt builder, and `ReportResult.revision_count`. The implementation is a plain while-loop inserted between the existing Phase 2 (editor) and Phase 3 (hook writer) stages.

The core change is approximately 25-35 lines of new code inside `generate_report_streaming()`, replacing the current single-pass anchor check with an iterative check-revise cycle. The key technical consideration is streaming control: the first draft streams via `run_stream_sync`, but revision passes must use `run_sync` (silent). Since the first draft has already been streamed to stdout before the anchor check runs, there is no way to "un-stream" it -- but the final capsule (whether first draft or revision) is what gets stored in `ReportResult.narrative` and passed to downstream phases.

The primary testing challenge is that pydantic-ai's `TestModel` cannot simultaneously return different outputs for str agents and AnchorResult agents (it raises AssertionError if both `custom_output_text` and `custom_output_args` are set). The default `TestModel()` returns dirty anchor results (one default warning), which naturally exercises the revision path. Clean-exit testing requires the `TestModel(custom_output_args={'warnings': []})` approach, but this only works for AnchorResult agents -- str agents need the default TestModel. The solution is that the existing pipeline tests already use `TestModel()` which returns `'success (no tool calls)'` for str agents and a dirty AnchorResult for the anchor agent, meaning the loop will naturally run MAX_REVISIONS iterations.

**Primary recommendation:** Add a `MAX_REVISIONS = 2` constant and a while-loop after the Phase 2 editor stream block. The loop calls `anchor_checker.run_sync()` on the current capsule, checks `anchor_check.is_clean`, and if dirty, calls `editor.run_sync()` (not `run_stream_sync`) with `_build_revision_message()`. After the loop, the existing hook/fantasy phases use the final `capsule` variable unchanged.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Loop Structure (from v1.3 research)
- Plain while-loop inside generate_report_streaming() (not pydantic-graph -- async-only, overkill for 2-node cycle)
- MAX_REVISIONS = 2 constant (3 total passes including first draft); configurable via constant
- Loop exits immediately when anchor returns is_clean == True
- Fresh prompt per revision (no message history -- avoids anchoring bias and token bloat)
- Fixed-size revision context: synthesis + current capsule + current warnings only (via _build_revision_message)

#### Streaming Control (from v1.3 research)
- First draft: editor runs via run_stream_sync (streams to stdout as currently implemented)
- Revision passes: editor runs via run_sync (silent -- no output to stdout)
- Only the final capsule (first draft or last revision) is the one that was streamed/returned
- If revision occurs, the first draft was already streamed -- but the final capsule replaces it in ReportResult

#### Pipeline Integration
- Hook writer and fantasy analyst receive the final capsule (post-revision), not the original first draft
- ReportResult.revision_count tracks how many revision passes occurred (0 = passed first try)
- Loop runs by default on every call to generate_report_streaming() -- no flag needed

### Claude's Discretion
- Exact placement of the while-loop within generate_report_streaming()
- Whether MAX_REVISIONS is a module constant or a parameter
- How to handle anchor agent errors during the loop (retry? break? propagate?)
- Whether to update the _make_agents cache or agent factory for the revision editor calls

### Deferred Ideas (OUT OF SCOPE)
- --no-refine flag to skip the loop (QUAL-05 -- future requirement)
- Oscillation detection (QUAL-01 -- terminate early when warnings cycle)
- Revision diff tracking (QUAL-02 -- record what changed per pass)
- ReflectionTrace with per-iteration token usage (QUAL-03)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOOP-01 | Editor-anchor loop iterates until anchor returns CLEAN or max revision cap (2) is reached | While-loop with MAX_REVISIONS=2 constant, AnchorResult.is_clean check, _build_revision_message for revision prompts -- all building blocks exist from Phase 5 |
| LOOP-04 | Loop terminates immediately when anchor returns CLEAN (no unnecessary iterations) | `if anchor_check.is_clean: break` at top of while-loop body immediately after anchor check |
| UX-01 | Loop runs by default on all narrative generations | Loop is unconditional inside generate_report_streaming() -- no flag, no conditional, always runs |
| UX-02 | Only the final capsule streams to stdout (revision passes run silently) | First draft: run_stream_sync (already implemented). Revisions: run_sync (silent). capsule variable is overwritten with each revision |
| UX-04 | Downstream phases (hook, fantasy) receive the final revised capsule | Hook and fantasy already use the `capsule` variable -- loop updates it in place before they execute |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Python version**: 3.14+
- **Naming**: snake_case for modules/functions, PascalCase for classes and Pydantic models, UPPER_SNAKE_CASE for constants
- **Code style**: ruff configured (line-length 110, target py313)
- **Module design**: Use `__all__` for public APIs, prefix internal helpers with `_`
- **Error handling**: Use specific exception types, not bare `except:`
- **Docstrings**: Google-style, type hints on all function signatures
- **GSD workflow**: All changes through GSD commands

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-ai | 1.72.0 | Agent.run_sync() and Agent.run_stream_sync() for LLM calls | Already used for all pipeline phases |
| pydantic | 2.12.5 | AnchorResult, AnchorWarning, ReportResult models | Already in use for all structured types |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=9.0.2 | Test framework | Already configured with testpaths=["tests"] |
| pydantic_ai.models.test.TestModel | 1.72.0 | Deterministic LLM testing | For loop behavior tests without real API calls |

**No new dependencies needed.** Everything is already installed.

## Architecture Patterns

### Recommended Project Structure

No new files needed. All changes go in existing modules:

```
src/pitcher_narratives/
    report.py           # MAX_REVISIONS constant, while-loop in generate_report_streaming()
tests/
    test_report.py      # New tests for loop behavior
```

### Pattern 1: While-Loop Reflection Cycle

**What:** Plain while-loop that alternates between anchor check and editor revision, bounded by MAX_REVISIONS.
**When to use:** Exactly this phase -- wiring the editor-anchor cycle.
**Example:**

```python
# Placement: after Phase 2 (editor stream) block, before Phase 3 (hook writer)

MAX_REVISIONS = 2
"""Maximum number of revision passes before accepting the capsule."""

# ... inside generate_report_streaming() ...

# Phase 2.5: Anchor check + revision loop
revision_count = 0
for _ in range(MAX_REVISIONS):
    anchor_kwargs: dict[str, Any] = {
        "user_prompt": _build_anchor_message(synthesis, capsule),
    }
    if _model_override is not None:
        anchor_kwargs["model"] = _model_override

    anchor_result = anchor_checker.run_sync(**anchor_kwargs)
    anchor_check = anchor_result.output

    if anchor_check.is_clean:
        break

    # Revise silently (no streaming)
    revision_kwargs: dict[str, Any] = {
        "user_prompt": _build_revision_message(synthesis, capsule, anchor_check.warnings),
    }
    if _model_override is not None:
        revision_kwargs["model"] = _model_override

    revision_result = editor.run_sync(**revision_kwargs)
    capsule = revision_result.output
    revision_count += 1
else:
    # Exhausted revisions -- do one final anchor check to capture surviving warnings
    anchor_kwargs = {
        "user_prompt": _build_anchor_message(synthesis, capsule),
    }
    if _model_override is not None:
        anchor_kwargs["model"] = _model_override
    anchor_result = anchor_checker.run_sync(**anchor_kwargs)
    anchor_check = anchor_result.output
```

### Pattern 2: Streaming vs Silent Agent Calls

**What:** Use `run_stream_sync` for user-visible output (first draft) and `run_sync` for silent background work (revisions).
**When to use:** Any pipeline phase that should not produce visible output.
**Key insight:** The editor agent is the same object for both first draft (streamed) and revisions (silent). The difference is purely which method is called.

```python
# First draft: streamed to stdout
stream = editor.run_stream_sync(**editor_kwargs)
chunks: list[str] = []
for delta in stream.stream_text(delta=True):
    print(delta, end="", flush=True)
    chunks.append(delta)
print()
capsule = "".join(chunks)

# Revision: silent (same agent, different method)
revision_result = editor.run_sync(**revision_kwargs)
capsule = revision_result.output  # Overwrites the streamed capsule
```

### Pattern 3: for/else for Bounded Loop with Final Check

**What:** Python's for/else construct where the else clause runs only when the loop completes without a break. This naturally handles the "exhausted MAX_REVISIONS" case.
**When to use:** When you need different behavior for "exited early" vs "exhausted iterations".

```python
for _ in range(MAX_REVISIONS):
    anchor_check = ...
    if anchor_check.is_clean:
        break  # Early exit -- else clause skipped
    capsule = revise(...)
else:
    # Only runs if loop exhausted without break
    # Do one final anchor check to capture surviving warnings
    anchor_check = final_check(...)
```

### Anti-Patterns to Avoid

- **Passing message_history between revision calls:** Locked decision -- fresh prompt per revision. Each revision gets the synthesis + current capsule + current warnings. No conversation threading.
- **Using run_stream_sync for revisions:** Revision passes must be silent. Streaming mid-revision would produce confusing double output.
- **Checking is_clean after the loop exits:** The loop structure must ensure `anchor_check` always holds the result of the most recent anchor check, regardless of whether the loop broke early or exhausted iterations.
- **Creating new agent instances for revisions:** Reuse the same `editor` agent from `_make_agents()`. The cached agent already has the correct model, settings, and system prompt.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Revision prompt assembly | Custom string concatenation | `_build_revision_message()` (Phase 5) | Already built, tested, follows project pattern |
| Clean/dirty check | String comparison or regex | `AnchorResult.is_clean` property (Phase 5) | Already built, typed, tested |
| Agent caching for revisions | New agent factory | Existing `_make_agents()` cache | Editor agent is already cached and reusable |
| Streaming control | Custom output buffer | `run_sync` vs `run_stream_sync` method choice | pydantic-ai provides both methods on every Agent |

**Key insight:** Phase 5 built every building block. Phase 6 is pure orchestration -- wiring existing pieces together inside a while-loop.

## Common Pitfalls

### Pitfall 1: anchor_check Not Updated After Final Revision

**What goes wrong:** If the loop does MAX_REVISIONS iterations and breaks, `anchor_check` holds the result from the check BEFORE the last revision -- not after. The surviving warnings in `ReportResult.anchor_warnings` would be stale.
**Why it happens:** The loop structure checks anchor, then revises. After the last revision, there is no subsequent anchor check.
**How to avoid:** Use a for/else pattern where the else clause does one final anchor check after exhausting iterations. Or restructure so the anchor check always happens at the top of the next iteration (and the else clause captures the final state).
**Warning signs:** `ReportResult.anchor_warnings` contains warnings that were actually fixed in the last revision.

### Pitfall 2: TestModel Cannot Test Clean-Exit Path Through Full Pipeline

**What goes wrong:** `TestModel()` always returns dirty anchor results (one default `AnchorWarning`). You cannot set `custom_output_args={'warnings': []}` because the str agents (synthesizer, editor, hook, fantasy) would fail with `AssertionError: Cannot set both custom_output_text and custom_output_args`.
**Why it happens:** TestModel does not support different output behaviors per agent type within a single model instance.
**How to avoid:** For the full-pipeline test, accept that default TestModel always exercises the revision path (revision_count == MAX_REVISIONS). For clean-exit testing, test the loop logic in isolation by calling anchor_checker.run_sync directly with a clean TestModel override, separate from the full pipeline. Alternatively, test clean-exit behavior at the unit level by verifying the anchor check + break logic.
**Warning signs:** Tests trying to verify `revision_count == 0` through `generate_report_streaming` with TestModel will fail.

### Pitfall 3: First Draft Already Streamed Before Revision

**What goes wrong:** The user sees the first draft streamed to stdout. If revisions occur, the final capsule is different from what was displayed. The user's terminal shows the original draft, not the revised version.
**Why it happens:** Streaming is real-time -- you cannot recall characters already printed.
**How to avoid:** This is a known, accepted behavior from the locked decisions. The `ReportResult.narrative` field holds the final (revised) capsule. Phase 7 will add stderr messages indicating revision occurred. For now, the first draft streams and the final capsule is what downstream phases use.
**Warning signs:** User confusion when the streamed output differs from what hook/fantasy reference. Phase 7 addresses this with stderr status messages.

### Pitfall 4: _model_override Not Passed to Revision Calls

**What goes wrong:** The anchor check and revision editor calls inside the loop forget to pass `_model_override`, causing them to use the real LLM provider in tests.
**Why it happens:** The _model_override kwarg pattern must be replicated for every new agent call.
**How to avoid:** Follow the exact same `if _model_override is not None: kwargs["model"] = _model_override` pattern used by all existing phase calls. Build kwargs dict then conditionally add model.
**Warning signs:** Tests hanging waiting for real API calls, or failing with missing API key errors.

### Pitfall 5: Capsule Variable Not Updated After Revision

**What goes wrong:** The `capsule` variable holds the first draft after streaming, but revision output is not assigned back to it. Downstream phases receive the original draft.
**Why it happens:** Forgetting to assign `capsule = revision_result.output` after the revision call.
**How to avoid:** After `editor.run_sync()` for revision, immediately assign `capsule = revision_result.output`. This is what makes downstream phases (hook, fantasy) automatically receive the revised version.
**Warning signs:** UX-04 test fails -- hook/fantasy content matches first draft instead of revision.

## Code Examples

Verified patterns from the existing codebase:

### Current Pipeline Flow (to be modified)

```python
# report.py generate_report_streaming() -- CURRENT (Phase 5 state):

# Phase 2: Streamed editorial
stream = editor.run_stream_sync(**editor_kwargs)
chunks: list[str] = []
for delta in stream.stream_text(delta=True):
    print(delta, end="", flush=True)
    chunks.append(delta)
print()
capsule = "".join(chunks)

# Phase 2.5: Single anchor check (no loop)
anchor_result = anchor_checker.run_sync(**anchor_kwargs)
anchor_check: AnchorResult = anchor_result.output

# Phase 3: Hook (uses capsule)
hook_result = hook_writer.run_sync(**hook_kwargs)

# Phase 4: Fantasy (uses capsule)
fantasy_result = fantasy_analyst.run_sync(**fantasy_kwargs)

return ReportResult(
    narrative=capsule,
    social_hook=hook_result.output,
    fantasy_insights=fantasy_result.output,
    anchor_warnings=anchor_check.warnings,
)
```

### Target Pipeline Flow (Phase 6 implementation)

```python
# report.py generate_report_streaming() -- TARGET (after Phase 6):

MAX_REVISIONS = 2

# Phase 2: Streamed editorial (unchanged)
stream = editor.run_stream_sync(**editor_kwargs)
chunks: list[str] = []
for delta in stream.stream_text(delta=True):
    print(delta, end="", flush=True)
    chunks.append(delta)
print()
capsule = "".join(chunks)

# Phase 2.5: Anchor check + revision loop
revision_count = 0
for _ in range(MAX_REVISIONS):
    anchor_kwargs: dict[str, Any] = {
        "user_prompt": _build_anchor_message(synthesis, capsule),
    }
    if _model_override is not None:
        anchor_kwargs["model"] = _model_override

    anchor_result = anchor_checker.run_sync(**anchor_kwargs)
    anchor_check = anchor_result.output

    if anchor_check.is_clean:
        break

    # Revise silently
    revision_kwargs: dict[str, Any] = {
        "user_prompt": _build_revision_message(synthesis, capsule, anchor_check.warnings),
    }
    if _model_override is not None:
        revision_kwargs["model"] = _model_override

    revision_result = editor.run_sync(**revision_kwargs)
    capsule = revision_result.output
    revision_count += 1
else:
    # Exhausted MAX_REVISIONS -- final anchor check for surviving warnings
    anchor_kwargs = {
        "user_prompt": _build_anchor_message(synthesis, capsule),
    }
    if _model_override is not None:
        anchor_kwargs["model"] = _model_override
    anchor_result = anchor_checker.run_sync(**anchor_kwargs)
    anchor_check = anchor_result.output

# Phase 3: Hook (uses final capsule -- post-revision if revised)
hook_kwargs: dict[str, Any] = {
    "user_prompt": _build_hook_message(ctx, capsule),
}
if _model_override is not None:
    hook_kwargs["model"] = _model_override
hook_result = hook_writer.run_sync(**hook_kwargs)

# Phase 4: Fantasy (uses final capsule)
fantasy_kwargs: dict[str, Any] = {
    "user_prompt": _build_fantasy_message(ctx, capsule),
}
if _model_override is not None:
    fantasy_kwargs["model"] = _model_override
fantasy_result = fantasy_analyst.run_sync(**fantasy_kwargs)

return ReportResult(
    narrative=capsule,
    social_hook=hook_result.output,
    fantasy_insights=fantasy_result.output,
    anchor_warnings=anchor_check.warnings,
    revision_count=revision_count,
)
```

### Testing the Loop with Default TestModel

```python
# Default TestModel() returns:
#   str agents: 'success (no tool calls)'
#   AnchorResult agent: AnchorResult(warnings=[AnchorWarning(category='MISSED_SIGNAL', description='a')])
#
# This means the loop ALWAYS revises with default TestModel.
# revision_count will be MAX_REVISIONS (2).

def test_generate_report_revision_count_with_dirty_anchor(ctx):
    """Pipeline with default TestModel exercises full revision loop."""
    result = generate_report_streaming(ctx, _model_override=TestModel())
    assert result.revision_count == 2  # MAX_REVISIONS
    assert isinstance(result.anchor_warnings, list)
```

### Testing the _model_override Pattern

```python
# The kwargs pattern for passing _model_override to each agent call:
kwargs: dict[str, Any] = {"user_prompt": some_prompt}
if _model_override is not None:
    kwargs["model"] = _model_override
result = agent.run_sync(**kwargs)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-pass anchor check | Iterative anchor-revision loop | Phase 6 (this phase) | Capsule self-corrects before downstream consumption |
| Anchor warnings as informational only | Anchor warnings drive revision | Phase 6 (this phase) | Warnings become actionable feedback, not just diagnostics |

**Deprecated/outdated:**
- The single-pass anchor check (current Phase 2.5) becomes the first iteration of the loop. No code is deprecated -- it is extended.

## Design Decisions (Claude's Discretion)

### MAX_REVISIONS: Module Constant vs Parameter

**Recommendation: Module-level constant.** `MAX_REVISIONS = 2` as a module constant at the top of report.py (near `PROVIDERS` and `THINKING_LEVELS`). Reasons: (1) success criteria says "up to 2 revision passes" as a fixed behavior, not a user choice; (2) the deferred `--no-refine` flag (QUAL-05) will eventually need to bypass the loop entirely, not adjust the count; (3) a constant is simpler and follows the existing PROVIDERS/THINKING_LEVELS pattern.

### Error Handling During Loop

**Recommendation: Propagate exceptions.** If `anchor_checker.run_sync()` or `editor.run_sync()` raises an exception during the loop (e.g., `UnexpectedModelBehavior`, `ModelHTTPError`), let it propagate to the caller. Reasons: (1) the caller (`cli.py`) already has no exception handling for these -- it crashes with a traceback; (2) partial results from a failed revision are worse than no results; (3) retry logic is a future concern (QUAL-03 territory). The simple approach: no try/except in the loop.

### Agent Reuse for Revisions

**Recommendation: Reuse the cached editor agent.** The same `editor` agent instance from `_make_agents()` is used for both the first draft (via `run_stream_sync`) and revisions (via `run_sync`). The agent's system prompt (`_EDITOR_PROMPT`) provides voice consistency. The revision prompt from `_build_revision_message()` provides the specific instructions. No new agent creation needed.

### Loop Structure: for/else vs while

**Recommendation: for/else.** `for _ in range(MAX_REVISIONS)` with an else clause for the final anchor check. This is cleaner than a while-loop with a manual counter because: (1) the iteration count is bounded and known; (2) the else clause naturally handles the "exhausted iterations" case; (3) no need for `revision_count < MAX_REVISIONS` guard.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_report.py -x -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOOP-01 | Loop revises capsule when anchor returns dirty, up to MAX_REVISIONS times | unit | `uv run pytest tests/test_report.py -x -q -k "revision_count"` | Needs new tests |
| LOOP-04 | Loop exits immediately when anchor returns CLEAN on first check | unit | `uv run pytest tests/test_report.py -x -q -k "clean_anchor"` | Existing test (test_generate_report_clean_anchor) needs update |
| UX-01 | Loop runs by default without flags | integration | `uv run pytest tests/test_report.py -x -q -k "generate_report"` | Covered by existing + new tests |
| UX-02 | Revision passes do not stream to stdout | unit | `uv run pytest tests/test_report.py -x -q -k "revision_silent"` | Needs new test (capsys or mock) |
| UX-04 | Downstream phases receive revised capsule | unit | `uv run pytest tests/test_report.py -x -q -k "downstream_capsule"` | Needs new test |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_report.py -x -q`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Test that default TestModel produces revision_count == MAX_REVISIONS (loop exercises full path)
- [ ] Test that revision passes update capsule (ReportResult.narrative differs from first draft when revisions occur)
- [ ] Test that ReportResult.revision_count is set correctly
- [ ] Test that anchor_warnings in ReportResult reflect the final anchor check (after last revision)
- [ ] Test that existing pipeline tests still pass (no regressions)

## Open Questions

1. **Stdout Artifact from First Draft When Revisions Occur**
   - What we know: The first draft is streamed to stdout before the anchor check. If revisions occur, the terminal shows the original (possibly flawed) draft, but ReportResult.narrative holds the corrected version.
   - What's unclear: Whether this is confusing to users in practice.
   - Recommendation: Accept this behavior per locked decisions. Phase 7 will add stderr messages ("Revised N times") to signal that revision occurred. The streamed output is a progress indicator, not the definitive result.

2. **TestModel Limitation for Clean-Exit Full Pipeline Test**
   - What we know: Default TestModel always produces dirty anchor results. Cannot use custom_output_args with str agents.
   - What's unclear: Whether we need a full-pipeline clean-exit test or if unit-level verification is sufficient.
   - Recommendation: Accept that the full-pipeline test with TestModel exercises the revision path. Verify clean-exit logic at the unit level by testing that `AnchorResult.is_clean` correctly triggers loop break. The existing `test_generate_report_clean_anchor` test already verifies the clean anchor path at the pipeline level (it just runs MAX_REVISIONS since TestModel is dirty).

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/pitcher_narratives/report.py` -- full current implementation of generate_report_streaming(), all agent call patterns, _make_agents() cache, _build_*_message() functions
- Codebase inspection: `tests/test_report.py` -- all existing test patterns, TestModel usage, _prompt_text helper
- Local verification: `Agent.run_sync()` can be called multiple times on the same agent instance with different prompts
- Local verification: `Agent.run_sync(model=override)` works for per-call model override
- Local verification: Default `TestModel()` returns `AnchorResult(warnings=[AnchorWarning(category='MISSED_SIGNAL', description='a')])` for AnchorResult agents (always dirty)
- Local verification: Default `TestModel()` returns `'success (no tool calls)'` for str agents
- Local verification: `TestModel(custom_output_text=..., custom_output_args=...)` raises AssertionError -- mutually exclusive
- Local verification: `TestModel(custom_output_args={'warnings': []})` produces clean `AnchorResult`
- Codebase inspection: `pydantic_ai/exceptions.py` -- all exception types (UnexpectedModelBehavior, ModelHTTPError, AgentRunError, etc.)

### Secondary (MEDIUM confidence)
- Phase 5 research and plans: Verified building blocks (AnchorResult, _build_revision_message, ReportResult.revision_count)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all APIs verified against installed pydantic-ai 1.72.0
- Architecture: HIGH -- building blocks confirmed in codebase; loop pattern verified with TestModel
- Pitfalls: HIGH -- TestModel limitation verified empirically; all edge cases tested locally

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable domain; all dependencies pinned)
