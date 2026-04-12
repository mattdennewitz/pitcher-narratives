# Phase 06: Pipeline Integration & Scout Parity Gate - Research

**Researched:** 2026-04-12
**Domain:** Python module integration, pydantic-ai Agent construction, backward-compatible signature evolution
**Confidence:** HIGH

## Summary

Phase 06 is a focused wiring phase: delete `_WRITER_PROMPT` from `pipeline.py`, import the persona machinery from `personas.py` (built in Phase 05), and thread a `persona` parameter through `make_pipeline_agents`, `_run_pipeline`, and `generate_pipeline_streaming`. The critical constraint is backward compatibility: `analyst.py:618` calls `make_pipeline_agents(provider, thinking)` positionally and must not break.

The codebase is well-positioned for this change. Phase 05 delivered `personas.py` with `build_writer_system_prompt()`, `DEFAULT_PERSONA`, `SCOUT`, and `get_persona()` -- all 13 contract tests pass. The frozen fixture at `tests/fixtures/writer_prompt_scout.txt` (4,507 bytes) matches `build_writer_system_prompt(SCOUT)` byte-for-byte. The integration work is mechanical: three functions gain a parameter, one constant is deleted, two reference sites are updated, and one downstream test (`test_signals.py`) needs its import redirected.

**Primary recommendation:** Add `persona: Persona = DEFAULT_PERSONA` as the third keyword argument to `make_pipeline_agents`, replace `_writer(_WRITER_PROMPT)` with `_writer(build_writer_system_prompt(persona))`, delete the `_WRITER_PROMPT` constant, and add `persona: str = "scout"` to `_run_pipeline` and `generate_pipeline_streaming` with resolution via `get_persona()` at the `_run_pipeline` boundary.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PERSONA-07 | `_WRITER_PROMPT` removed from `pipeline.py`; writer agent built from `build_writer_system_prompt(persona)` | Delete constant at line 408-477, replace reference at line 1153 with `build_writer_system_prompt(persona)`, replace reference at line 1007 in `_render_pipeline_data_sections` |
| PERSONA-08 | `make_pipeline_agents(provider, thinking, persona: Persona = DEFAULT_PERSONA)` preserves positional call at `analyst.py:618` | DEFAULT_PERSONA import from personas.py; keyword-only after two positional args; analyst.py confirmed calling with exactly two positional args |
| PERSONA-09 | `generate_pipeline_streaming` and `_run_pipeline` accept `persona: str = "scout"` and resolve via `get_persona()` | String-at-boundaries pattern; resolve once at `_run_pipeline` entry, pass `Persona` object to `make_pipeline_agents` |
| TEST-05 (scout) | TestModel-based scout smoke test runs pipeline end-to-end, composed writer prompt equals frozen fixture | Use `_system_prompts` tuple on Agent to verify prompt content; leverage existing `generate_pipeline_streaming` + TestModel pattern from `test_pipeline.py` |
</phase_requirements>

## Standard Stack

### Core

No new libraries. This phase uses only existing project dependencies.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-ai | 1.72.0 | Agent construction with `system_prompt` kwarg | Already in use; `Agent._system_prompts` tuple provides verification access |
| pytest | 9.0.2 | Test runner | Already configured in `pyproject.toml` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-ai TestModel | (bundled) | `from pydantic_ai.models.test import TestModel` | Smoke tests that run the full pipeline without LLM calls |

## Architecture Patterns

### Modification Map

```
src/pitcher_narratives/
  pipeline.py         # DELETE _WRITER_PROMPT, ADD persona param to 3 functions,
                      # UPDATE _render_pipeline_data_sections writer prompt ref
  personas.py         # UNCHANGED (Phase 05 deliverable, consumed as-is)

tests/
  test_personas.py    # ADD scout pipeline smoke test (TEST-05 scout portion)
  test_signals.py     # UPDATE import: _WRITER_PROMPT -> build_writer_system_prompt(SCOUT)
  test_pipeline.py    # UNCHANGED (all 53 passing tests must remain green)
```

### Pattern 1: Default-Argument Backward Compatibility

**What:** Adding `persona` as a keyword argument with a module-level default to `make_pipeline_agents` so existing callers are unchanged.

**When to use:** When extending a function signature without breaking existing call sites.

**Exact change to `make_pipeline_agents`:**
```python
from pitcher_narratives.personas import (
    Persona,
    DEFAULT_PERSONA,
    build_writer_system_prompt,
)

def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona = DEFAULT_PERSONA,  # NEW -- keyword-with-default
) -> PipelineAgents:
    # ... existing code ...
    # Line 1153 changes from:
    #   writer=_writer(_WRITER_PROMPT),
    # to:
    #   writer=_writer(build_writer_system_prompt(persona)),
```

**Why this works:** `analyst.py:618` calls `make_pipeline_agents(provider, thinking)` with exactly two positional args. The new `persona` parameter has a default value (`DEFAULT_PERSONA` = SCOUT singleton), so the existing call resolves identically. Python allows positional-or-keyword arguments after existing positional-or-keyword arguments when they have defaults.

### Pattern 2: String-at-Boundaries, Object-Inside

**What:** Public-facing functions (`generate_pipeline_streaming`, `_run_pipeline`) accept `persona: str = "scout"` and resolve to a `Persona` object via `get_persona()` before passing to `make_pipeline_agents`.

**Why:** CLI code and callers should not need to import `Persona` or `SCOUT`. The string is the boundary contract; the object is the internal contract.

**Resolution point:** `_run_pipeline` resolves the string once:
```python
async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",          # NEW
    _model_override: Any = None,
) -> PipelineResult:
    from pitcher_narratives.personas import get_persona
    persona_obj = get_persona(persona)
    agents = make_pipeline_agents(provider, thinking, persona_obj)
    # ... rest unchanged ...
```

`generate_pipeline_streaming` threads the string through to `_run_pipeline`:
```python
def generate_pipeline_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",          # NEW
    _model_override: Any = None,
) -> PipelineResult:
    return asyncio.run(
        _run_pipeline(ctx, provider=provider, thinking=thinking,
                      persona=persona, _model_override=_model_override)
    )
```

### Pattern 3: `_render_pipeline_data_sections` Update

**What:** The `_WRITER_PROMPT` reference at pipeline.py line 1007 (used by `write_pipeline_data_file` and `--print-prompts`) must switch to `build_writer_system_prompt()`.

**Approach:** Since `_render_pipeline_data_sections` does not currently receive a persona parameter, it must either (a) accept a new optional `persona` kwarg, or (b) use the default `DEFAULT_PERSONA` for now. Option (b) is simpler and correct for Phase 06 -- the CLI does not yet have `--persona` (that is Phase 09). Use `build_writer_system_prompt(DEFAULT_PERSONA)` directly. Phase 09 will thread the persona through when adding CLI support.

```python
# Line 1007 changes from:
#   sections.append(f"## System Prompt\n\n{_WRITER_PROMPT}\n")
# to:
from pitcher_narratives.personas import DEFAULT_PERSONA, build_writer_system_prompt
sections.append(f"## System Prompt\n\n{build_writer_system_prompt(DEFAULT_PERSONA)}\n")
```

Note: The import should be at module level, not inline. But since this function is already heavy with constants, a top-of-file import is cleaner.

### Pattern 4: Verifying Agent System Prompt Content

**What:** pydantic-ai `Agent` stores system prompts in `agent._system_prompts` as a tuple of strings. This is how tests can verify the writer agent received the correct composed prompt.

**Test strategy for success criterion 2 (identical system prompts):**
```python
def test_default_and_explicit_scout_produce_identical_writer_prompts():
    from pitcher_narratives.personas import SCOUT
    agents_default = make_pipeline_agents("gemini", "high")
    agents_explicit = make_pipeline_agents("gemini", "high", SCOUT)
    assert agents_default.writer._system_prompts == agents_explicit.writer._system_prompts
```

**Test strategy for success criterion 4 (scout smoke test with prompt verification):**
```python
def test_scout_pipeline_smoke_test(ctx):
    from pitcher_narratives.personas import SCOUT, build_writer_system_prompt
    test_model = TestModel()
    result = generate_pipeline_streaming(
        ctx, provider="gemini", thinking="high", _model_override=test_model,
    )
    assert isinstance(result, PipelineResult)
    assert len(result.narrative) > 0

    # Verify writer agent received correct prompt
    agents = make_pipeline_agents("gemini", "high")
    expected = build_writer_system_prompt(SCOUT)
    assert agents.writer._system_prompts == (expected,)

    # Verify against frozen fixture
    fixture = Path("tests/fixtures/writer_prompt_scout.txt").read_text()
    assert expected == fixture
```

### Anti-Patterns to Avoid

- **Do not make `persona` positional-only or keyword-only via `/` or `*`:** The existing `provider` and `thinking` args are positional-or-keyword. Adding `persona` with the same convention keeps the signature uniform.
- **Do not resolve persona string inside `make_pipeline_agents`:** The architecture decision is that `make_pipeline_agents` takes a `Persona` object, not a string. String resolution happens at the `_run_pipeline` boundary. This keeps `make_pipeline_agents` type-safe and avoids an import cycle.
- **Do not delete `_WRITER_PROMPT` without updating all three reference sites:** There are exactly three: the constant definition (line 408), the `make_pipeline_agents` call (line 1153), and the `_render_pipeline_data_sections` reference (line 1007).
- **Do not add persona parameter to `write_pipeline_data_file` in this phase:** That function is used by `cli.py` which does not yet have `--persona` (Phase 09). Pass-through would be dead code. Use `DEFAULT_PERSONA` in the renderer for now.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Writer prompt composition | String concatenation in pipeline.py | `build_writer_system_prompt(persona)` from personas.py | Single source of truth; byte-parity already tested |
| Persona lookup | Dict access with manual error handling | `get_persona(persona_id)` from personas.py | Already built with proper ValueError messaging |
| Agent system prompt verification | Intercepting LLM calls or parsing output | `agent._system_prompts` tuple | Direct access to the stored prompt; no runtime cost |

## Common Pitfalls

### Pitfall 1: Import Cycle Between pipeline.py and personas.py

**What goes wrong:** Adding `from pitcher_narratives.personas import ...` at the top of `pipeline.py` while `personas.py` imports from `pipeline.py`.
**Why it happens:** Circular imports cause `ImportError`.
**How to avoid:** `personas.py` has ZERO imports from `pipeline.py` (verified by reading the file). The dependency is one-way: `pipeline.py -> personas.py`. Safe to add a top-level import.
**Warning signs:** `ImportError: cannot import name 'X' from partially initialized module`.

### Pitfall 2: Breaking `analyst.py:618` Positional Call

**What goes wrong:** The new `persona` parameter is inserted before `thinking` or made required, breaking `make_pipeline_agents(provider, thinking)`.
**Why it happens:** Careless parameter ordering.
**How to avoid:** `persona` MUST be the THIRD parameter with a default value. The existing two parameters (`provider`, `thinking`) keep their positions.
**Warning signs:** `TypeError: make_pipeline_agents() got multiple values for argument...` or `missing required argument`.

### Pitfall 3: test_signals.py Import Breakage

**What goes wrong:** `tests/test_signals.py` lines 136-141 import `_WRITER_PROMPT` from `pipeline`. After deletion, these tests fail with `ImportError`.
**Why it happens:** Downstream test file has a direct import of the deleted constant.
**How to avoid:** Update `test_signals.py` to import `build_writer_system_prompt` and `SCOUT` from `personas.py`, then call `build_writer_system_prompt(SCOUT)` to get the prompt text. The assertions (`"Key Signals" in prompt`, `"Primary" in prompt`, etc.) will still pass because the composed prompt contains all the same content.
**Warning signs:** `ImportError: cannot import name '_WRITER_PROMPT' from 'pitcher_narratives.pipeline'`.

### Pitfall 4: `_render_pipeline_data_sections` Still Referencing Deleted Constant

**What goes wrong:** `_render_pipeline_data_sections` at line 1007 uses `_WRITER_PROMPT` for the `--print-prompts` data file. If not updated, `NameError` at runtime.
**Why it happens:** This reference is easy to miss because it is in a rendering helper, not the agent factory.
**How to avoid:** Grep for all three occurrences of `_WRITER_PROMPT` in `pipeline.py` before declaring the deletion complete (lines 408, 1007, 1153).
**Warning signs:** `NameError: name '_WRITER_PROMPT' is not defined` when running `pitcher-narratives --print-prompts`.

### Pitfall 5: `__all__` Export List

**What goes wrong:** If `_WRITER_PROMPT` were in `__all__`, removing it would be a public API break. 
**How to avoid:** Verified: `_WRITER_PROMPT` is NOT in `pipeline.py`'s `__all__` (lines 82-89). It is a private constant (leading underscore). No `__all__` update needed in pipeline.py.
**Warning signs:** N/A -- already verified safe.

### Pitfall 6: Prompt Content Drift in _render_pipeline_data_sections

**What goes wrong:** After switching from `_WRITER_PROMPT` to `build_writer_system_prompt(DEFAULT_PERSONA)`, the `--print-prompts` output changes content (because the composed v1.10 prompt is 4,507 bytes vs the old 3,607 bytes).
**Why it happens:** The composed prompt includes `SHARED_WRITER_BASE` + scout overlay, which is intentionally different from the old `_WRITER_PROMPT`.
**How to avoid:** This is expected and correct. The `_render_pipeline_data_sections` function should render the same prompt the agent actually receives. After Phase 06, the agent receives the composed prompt, so `--print-prompts` should show the composed prompt. No separate handling needed.
**Warning signs:** Only a concern if someone expects `--print-prompts` output to be identical to v1.9 -- it won't be, and that is by design.

## Code Examples

### Complete `make_pipeline_agents` Signature Change

```python
# At top of pipeline.py, add to existing imports:
from pitcher_narratives.personas import (
    Persona,
    DEFAULT_PERSONA,
    build_writer_system_prompt,
)

# Updated function signature:
def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona = DEFAULT_PERSONA,
) -> PipelineAgents:
    # ... existing model/settings setup unchanged ...

    def _writer(prompt: str) -> Agent[None, str]:
        return Agent(model, output_type=str, system_prompt=prompt,
                     model_settings=writer_settings, defer_model_check=True)

    return PipelineAgents(
        # ... all other agents unchanged ...
        writer=_writer(build_writer_system_prompt(persona)),
        # ... rest unchanged ...
    )
```

### Complete `_run_pipeline` Signature Change

```python
async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    _model_override: Any = None,
) -> PipelineResult:
    persona_obj = get_persona(persona)
    agents = make_pipeline_agents(provider, thinking, persona_obj)
    # ... rest of function unchanged ...
```

### test_signals.py Update

```python
# Change lines 136-141 from:
class TestWriterPromptKeySignals:
    def test_references_key_signals(self):
        from pitcher_narratives.pipeline import _WRITER_PROMPT
        assert "Key Signals" in _WRITER_PROMPT

    def test_distinguishes_primary_secondary(self):
        from pitcher_narratives.pipeline import _WRITER_PROMPT
        assert "Primary" in _WRITER_PROMPT or "primary" in _WRITER_PROMPT
        assert "Secondary" in _WRITER_PROMPT or "secondary" in _WRITER_PROMPT

# To:
class TestWriterPromptKeySignals:
    def test_references_key_signals(self):
        from pitcher_narratives.personas import SCOUT, build_writer_system_prompt
        prompt = build_writer_system_prompt(SCOUT)
        assert "Key Signals" in prompt

    def test_distinguishes_primary_secondary(self):
        from pitcher_narratives.personas import SCOUT, build_writer_system_prompt
        prompt = build_writer_system_prompt(SCOUT)
        assert "Primary" in prompt or "primary" in prompt
        assert "Secondary" in prompt or "secondary" in prompt
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `_WRITER_PROMPT` hardcoded constant in pipeline.py | `build_writer_system_prompt(persona)` from personas.py | Phase 06 (this phase) | Writer prompt is now composable and persona-aware |
| `make_pipeline_agents(provider, thinking)` | `make_pipeline_agents(provider, thinking, persona=DEFAULT_PERSONA)` | Phase 06 (this phase) | Pipeline factory is persona-aware while preserving backward compat |

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run python -m pytest tests/test_personas.py tests/test_signals.py -x -v` |
| Full suite command | `uv run python -m pytest tests/ -x -v --ignore=tests/test_analyst.py` |

Note: `tests/test_analyst.py` has a pre-existing broken import (`_analyst_agent`) unrelated to this phase. The `--ignore` prevents it from blocking.

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERSONA-07 | `_WRITER_PROMPT` deleted; writer built from `build_writer_system_prompt(persona)` | unit | `uv run python -m pytest tests/test_personas.py -x -k "byte_identical"` | Exists (test_personas.py:72) -- but pipeline-path test needed (Wave 0) |
| PERSONA-08 | `make_pipeline_agents(provider, thinking)` and `make_pipeline_agents(provider, thinking, SCOUT)` produce identical writer prompts | unit | `uv run python -m pytest tests/test_pipeline.py -x -k "default_and_explicit"` | Wave 0 |
| PERSONA-09 | `generate_pipeline_streaming(..., persona="scout")` resolves correctly | smoke | `uv run python -m pytest tests/test_pipeline.py -x -k "scout_smoke"` | Wave 0 |
| TEST-05 (scout) | TestModel-based scout smoke test runs pipeline end-to-end, composed writer prompt equals frozen fixture | smoke | `uv run python -m pytest tests/test_personas.py -x -k "pipeline_smoke"` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run python -m pytest tests/test_personas.py tests/test_signals.py tests/test_pipeline.py -x -v`
- **Per wave merge:** `uv run python -m pytest tests/ -x -v --ignore=tests/test_analyst.py`
- **Phase gate:** Full suite green + `test_scout_composed_prompt_is_byte_identical_to_v19` passes (already exists) + new pipeline integration tests pass

### Wave 0 Gaps

- [ ] `tests/test_pipeline.py::test_default_and_explicit_scout_produce_identical_writer_prompts` -- covers PERSONA-08 (success criterion 2)
- [ ] `tests/test_personas.py::test_scout_pipeline_smoke` or equivalent in `test_pipeline.py` -- covers TEST-05 scout portion (success criterion 4); runs full pipeline with TestModel, verifies writer prompt matches fixture
- [ ] `tests/test_signals.py::TestWriterPromptKeySignals` -- import update needed (currently imports deleted `_WRITER_PROMPT`)

## Open Questions

1. **Where should the new pipeline integration test live?**
   - What we know: `test_personas.py` has the persona-level contract tests. `test_pipeline.py` has the pipeline smoke tests. TEST-05 says "tests/test_personas.py contains one TestModel-based smoke test per persona."
   - What's unclear: The requirement says `test_personas.py` but the test needs pipeline imports (`make_pipeline_agents`, `generate_pipeline_streaming`, `PipelineResult`).
   - Recommendation: Follow the requirement -- put it in `test_personas.py` since that is where TEST-05 specifies it. The test can import from both `personas` and `pipeline` modules. This keeps all persona-related tests in one file for the full milestone (Phase 07 and 08 will add analyst and generic smoke tests to the same file).

2. **Should `_render_pipeline_data_sections` gain a persona parameter now or in Phase 09?**
   - What we know: The function currently uses `_WRITER_PROMPT` directly. Phase 09 adds `--persona` to the CLI, which is when `write_pipeline_data_file` would need to render the selected persona's prompt.
   - Recommendation: Use `build_writer_system_prompt(DEFAULT_PERSONA)` inline for now. Add the parameter threading in Phase 09 when the CLI provides the persona. This avoids dead code.

## Sources

### Primary (HIGH confidence)

- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/pipeline.py` -- current `_WRITER_PROMPT` at line 408, `make_pipeline_agents` at line 1112, `_run_pipeline` at line 1279, `generate_pipeline_streaming` at line 1402, `_render_pipeline_data_sections` at line 948
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/personas.py` -- Phase 05 deliverable, 177 lines, all 13 contract tests pass
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/analyst.py` line 618 -- confirmed `make_pipeline_agents(provider, thinking)` positional call
- `/Users/matt/src/pitcher-narratives/tests/test_signals.py` lines 136-141 -- `_WRITER_PROMPT` import that needs update
- `/Users/matt/src/pitcher-narratives/tests/test_pipeline.py` -- 53 passing tests (1 pre-existing failure unrelated to this phase)
- `/Users/matt/src/pitcher-narratives/tests/test_personas.py` -- 13 passing tests from Phase 05
- `/Users/matt/src/pitcher-narratives/tests/fixtures/writer_prompt_scout.txt` -- frozen fixture, 4507 bytes
- pydantic-ai Agent internals verified: `Agent._system_prompts` is a tuple of strings

### Secondary (MEDIUM confidence)

- `.planning/research/ARCHITECTURE.md` -- design decisions for make_pipeline_agents signature and CLI threading path
- `.planning/research/SUMMARY.md` -- confirmed string-at-boundaries pattern and agent-level verification strategy

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, using only existing project code
- Architecture: HIGH -- all touch points identified by reading actual source code, all three _WRITER_PROMPT references mapped, analyst.py call site confirmed
- Pitfalls: HIGH -- every pitfall is verified against the actual codebase (import cycles checked, __all__ verified, test file imports mapped)

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable -- no external dependency changes expected)
