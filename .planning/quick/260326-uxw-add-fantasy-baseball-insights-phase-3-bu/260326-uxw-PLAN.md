---
phase: quick-260326-uxw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - report.py
  - main.py
  - tests/test_report.py
autonomous: true
requirements: [QUICK-UXW]
must_haves:
  truths:
    - "ReportResult contains a fantasy_insights field with 3 bullet points"
    - "Fantasy insights print after the social hook in CLI output"
    - "Fantasy analyst agent runs silently (no streaming) using the synthesizer output"
    - "All existing tests still pass after changes"
  artifacts:
    - path: "report.py"
      provides: "fantasy_analyst agent, _FANTASY_PROMPT, _build_fantasy_message, updated ReportResult"
      contains: "fantasy_analyst"
    - path: "main.py"
      provides: "CLI output of fantasy_insights after social_hook"
      contains: "fantasy_insights"
    - path: "tests/test_report.py"
      provides: "Tests for fantasy analyst agent, message builder, ReportResult field"
      contains: "fantasy_analyst"
  key_links:
    - from: "report.py"
      to: "report.py::generate_report_streaming"
      via: "Phase 4 call to fantasy_analyst.run_sync"
      pattern: "fantasy_analyst\\.run_sync"
    - from: "main.py"
      to: "report.py::ReportResult"
      via: "result.fantasy_insights"
      pattern: "result\\.fantasy_insights"
---

<objective>
Add a fantasy baseball insights phase to the report pipeline.

Purpose: Provide 3 bullet points of actionable fantasy baseball insights derived from the synthesizer output, following the exact same pattern as the hook_writer agent (Phase 3: social media hook).
Output: New `fantasy_analyst` agent, `fantasy_insights` field on ReportResult, CLI output section, tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@report.py
@main.py
@tests/test_report.py
@context.py

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from codebase. -->

From report.py — the hook_writer pattern to replicate exactly:
```python
# Agent definition (line 214-220)
_HOOK_PROMPT = """..."""
hook_writer = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=str,
    system_prompt=_HOOK_PROMPT,
    model_settings=ModelSettings(max_tokens=150),
    defer_model_check=True,
)

# ReportResult model (line 223-228)
class ReportResult(BaseModel):
    """Structured output from the two-phase report pipeline."""
    narrative: str
    social_hook: str

# Message builder (line 256-264)
def _build_hook_message(ctx: PitcherContext, synthesis: str) -> str:
    """Build the Phase 3 user message for the social media hook."""
    return (
        f"## Pitcher\n"
        f"{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Key Findings\n{synthesis}\n\n"
        f"Write one social media hook (1-2 sentences). "
        f"Focus on the single most notable change."
    )

# Phase 3 in generate_report_streaming (line 309-316)
hook_kwargs: dict = {
    "user_prompt": _build_hook_message(ctx, synthesis),
}
if _model_override is not None:
    hook_kwargs["model"] = _model_override
hook_result = hook_writer.run_sync(**hook_kwargs)

# Return (line 318-321)
return ReportResult(
    narrative=''.join(chunks),
    social_hook=hook_result.output,
)

# __all__ (line 20-27) includes hook_writer and _build_hook_message
```

From main.py — how social_hook is printed (line 99-100):
```python
# Print social hook
print(f"\n---\n{result.social_hook}")
```

From tests/test_report.py — hook_writer test pattern (line 346-386):
```python
# Agent config tests
def test_hook_writer_model_is_claude_sonnet():
    assert "claude-sonnet-4-6" in str(hook_writer.model)

def test_hook_writer_output_type_is_str():
    assert hook_writer.output_type is str

# Message builder tests
def test_hook_message_includes_pitcher_name(ctx):
    msg = _build_hook_message(ctx, "test synthesis")
    assert ctx.pitcher_name in msg

def test_hook_message_includes_synthesis(ctx):
    msg = _build_hook_message(ctx, "Fastball velo down 1.5")
    assert "Fastball velo down 1.5" in msg

# ReportResult field tests
def test_report_result_has_social_hook(ctx):
    result = generate_report_streaming(
        ctx, _model_override=TestModel(custom_output_text="hook text")
    )
    assert isinstance(result, ReportResult)
    assert result.social_hook
    assert result.narrative
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add fantasy_analyst agent and wire into report pipeline</name>
  <files>report.py</files>
  <action>
Follow the hook_writer pattern exactly to add a Phase 4: Fantasy Analyst.

1. **Add agent section** after the hook_writer block (after line 220), with a clear section header matching the existing style:

```
# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: THE FANTASY ANALYST
# ═══════════════════════════════════════════════════════════════════════
```

2. **Create `_FANTASY_PROMPT`** system prompt. The agent is a sharp fantasy baseball analyst who writes exactly 3 bullet points. Each bullet should be actionable (roster add/drop/hold, start/sit, buy-low/sell-high). The tone is direct, analytical, and specific — cite the metric or trend backing each bullet. No hedging. No generic advice. Fantasy-relevant means: does this affect his value in standard 5x5 or points leagues? Think ownership changes, streaming value, matchup dependency, injury/workload red flags.

3. **Create `fantasy_analyst` agent** — identical pattern to hook_writer:
   - Model: `'anthropic:claude-sonnet-4-6'`
   - `output_type=str`
   - `system_prompt=_FANTASY_PROMPT`
   - `model_settings=ModelSettings(max_tokens=300)` (3 bullets need more room than a 1-2 sentence hook)
   - `defer_model_check=True`

4. **Create `_build_fantasy_message(ctx: PitcherContext, synthesis: str) -> str`** — same pattern as `_build_hook_message`:
   - Include pitcher name, handedness, role
   - Include synthesis key findings
   - Instruction: "Write exactly 3 bullet points of fantasy baseball insights. Each bullet must be actionable and cite a specific metric or trend."

5. **Update `ReportResult`** — add `fantasy_insights: str` field after `social_hook`.

6. **Update `generate_report_streaming`**:
   - Add Phase 4 block after Phase 3 (same pattern: build kwargs, conditionally add model_override, call `fantasy_analyst.run_sync`)
   - Update the return statement to include `fantasy_insights=fantasy_result.output`
   - Update the docstring to mention Phase 4

7. **Update `__all__`** — add `fantasy_analyst` and `_build_fantasy_message`.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "from report import fantasy_analyst, _build_fantasy_message, ReportResult; r = ReportResult(narrative='a', social_hook='b', fantasy_insights='c'); print('OK:', r.fantasy_insights)"</automated>
  </verify>
  <done>fantasy_analyst agent defined, _build_fantasy_message builder exists, ReportResult has fantasy_insights field, generate_report_streaming calls Phase 4</done>
</task>

<task type="auto">
  <name>Task 2: Add CLI output and tests</name>
  <files>main.py, tests/test_report.py</files>
  <action>
**main.py changes:**

After the social hook print (line 100: `print(f"\n---\n{result.social_hook}")`), add a fantasy insights section:

```python
# Print fantasy insights
print(f"\n---\n{result.fantasy_insights}")
```

**tests/test_report.py changes:**

1. Update imports to include `fantasy_analyst`, `_build_fantasy_message`, `_FANTASY_PROMPT`.

2. Add a new test section after the hook writer tests (line 386), with the same section comment style:

```python
# -- Phase 4: Fantasy analyst agent tests ----------------------------------------
```

3. Add these tests mirroring the hook_writer test pattern:

- `test_fantasy_analyst_model_is_claude_sonnet` — assert `"claude-sonnet-4-6"` in str(fantasy_analyst.model)
- `test_fantasy_analyst_output_type_is_str` — assert fantasy_analyst.output_type is str
- `test_fantasy_prompt_requires_three_bullets` — assert "3" or "three" (case-insensitive) in _FANTASY_PROMPT and "bullet" in _FANTASY_PROMPT.lower()
- `test_fantasy_prompt_requires_actionable` — assert "actionable" in _FANTASY_PROMPT.lower()
- `test_fantasy_message_includes_pitcher_name(ctx)` — same pattern as test_hook_message_includes_pitcher_name
- `test_fantasy_message_includes_synthesis(ctx)` — same pattern as test_hook_message_includes_synthesis
- `test_report_result_has_fantasy_insights(ctx)` — generate with TestModel, assert result.fantasy_insights is truthy
- `test_report_result_all_fields_populated(ctx)` — generate with TestModel, assert all three fields (narrative, social_hook, fantasy_insights) are non-empty
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run pytest tests/test_report.py -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>Fantasy insights print after social hook in CLI. All new tests pass. All existing tests still pass.</done>
</task>

</tasks>

<verification>
1. `uv run python -c "from report import fantasy_analyst, ReportResult"` — imports succeed
2. `uv run pytest tests/test_report.py -x -q` — all tests pass (existing + new)
3. `uv run pytest tests/ -x -q` — full test suite still passes
</verification>

<success_criteria>
- ReportResult has three fields: narrative, social_hook, fantasy_insights
- fantasy_analyst agent mirrors hook_writer pattern exactly (model, output_type, defer_model_check)
- _build_fantasy_message follows _build_hook_message pattern
- generate_report_streaming runs 4 phases (synth, editor, hook, fantasy)
- CLI prints fantasy insights after social hook, separated by ---
- All existing tests pass unchanged
- New tests cover agent config, prompt content, message builder, and pipeline output
</success_criteria>

<output>
After completion, create `.planning/quick/260326-uxw-add-fantasy-baseball-insights-phase-3-bu/260326-uxw-SUMMARY.md`
</output>
