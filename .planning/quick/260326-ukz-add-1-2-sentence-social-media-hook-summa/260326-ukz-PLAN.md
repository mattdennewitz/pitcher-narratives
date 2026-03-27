---
phase: quick-260326-ukz
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - report.py
  - main.py
  - tests/test_report.py
autonomous: true
requirements: [QUICK-UKZ]

must_haves:
  truths:
    - "Running the CLI produces the scouting capsule followed by a social media hook on a separate line"
    - "The social media hook is 1-2 sentences distilling the most important difference from the latest appearance"
    - "The hook is stored as a separate field, not embedded in the narrative text"
    - "Test suite passes including new hook tests"
  artifacts:
    - path: "report.py"
      provides: "ReportResult dataclass, hook agent, updated generate_report_streaming returning ReportResult"
      contains: "social_hook"
    - path: "main.py"
      provides: "Updated CLI to print the hook after the narrative"
      contains: "social_hook"
    - path: "tests/test_report.py"
      provides: "Tests for hook agent and ReportResult"
      contains: "test_report_result_has_social_hook"
  key_links:
    - from: "report.py"
      to: "report.py"
      via: "hook_writer agent uses synthesis output from Phase 1"
      pattern: "hook_writer.*run_sync"
    - from: "main.py"
      to: "report.py"
      via: "main unpacks ReportResult.narrative and ReportResult.social_hook"
      pattern: "result\\.social_hook"
---

<objective>
Add a social media hook field to the scouting report pipeline.

Purpose: Give the user a 1-2 sentence, insight-driven summary of the most important changes from the pitcher's latest appearance -- designed for immediate use as a social media post. This is a separate output field, not part of the narrative capsule.

Output: Updated report.py with a ReportResult dataclass, a hook_writer agent, and updated main.py CLI output.
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
<!-- Key types and contracts the executor needs. -->

From report.py:
```python
def generate_report_streaming(
    ctx: PitcherContext,
    *,
    _model_override=None,
) -> str:
    """Returns the complete report text (Phase 2 output) as a string."""

# Existing agents:
synthesizer = Agent('anthropic:claude-sonnet-4-6', output_type=str, ...)
editor = Agent('anthropic:claude-sonnet-4-6', output_type=str, ...)
```

From context.py:
```python
class PitcherContext(BaseModel):
    pitcher_name: str
    pitcher_id: int
    throws: str
    role: str
    # ... all engine outputs
    def to_prompt(self) -> str: ...
```

From main.py:
```python
report_text = generate_report_streaming(ctx, _model_override=model_override)
# Then hallucination check runs on report_text
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add ReportResult dataclass and hook_writer agent to report.py</name>
  <files>report.py</files>
  <action>
1. Add a `ReportResult` dataclass (or simple class with two str fields) near the top of the orchestration section:

```python
class ReportResult(BaseModel):
    """Structured output from the two-phase report pipeline."""
    narrative: str
    social_hook: str
```

Add `ReportResult` to `__all__`.

2. Add a `hook_writer` agent after the editor agent definition. This is a lightweight Phase 3 that distills the synthesis into a social hook. System prompt:

```
You are a sharp, analytically-minded baseball writer crafting a single social media hook. Given key findings from a pitcher's latest appearance, write 1-2 sentences that capture the single most important change, trend, or signal. Be specific — name the pitch, cite the metric, state the direction. No hashtags, no emojis, no hype. Write with authority, as if tweeting to a front-office audience. The hook must stand alone without context.
```

Use `ModelSettings(max_tokens=150)` to keep it tight. `output_type=str`. Use `defer_model_check=True` consistent with the other agents.

3. Add a `_build_hook_message` function that takes `ctx: PitcherContext` and `synthesis: str` and returns:
```
## Pitcher
{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})

## Key Findings
{synthesis}

Write one social media hook (1-2 sentences). Focus on the single most notable change.
```

4. Update `generate_report_streaming` to:
   - After Phase 2 (editor) completes and report text is collected, run Phase 3: call `hook_writer.run_sync()` with `_build_hook_message(ctx, synthesis)`. Pass `_model_override` if provided.
   - Return `ReportResult(narrative=''.join(chunks), social_hook=hook_result.output)` instead of the raw string.
   - Update the return type annotation from `-> str` to `-> ReportResult`.
   - Update the docstring to reflect the new return type.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "from report import ReportResult, hook_writer, _build_hook_message; print('imports OK')"</automated>
  </verify>
  <done>report.py exports ReportResult with narrative + social_hook fields, hook_writer agent exists, generate_report_streaming returns ReportResult</done>
</task>

<task type="auto">
  <name>Task 2: Update main.py to unpack ReportResult and print hook</name>
  <files>main.py</files>
  <action>
1. Update the `generate_report_streaming` call site in `main()`. Currently:
```python
report_text = generate_report_streaming(ctx, _model_override=model_override)
```
Change to:
```python
result = generate_report_streaming(ctx, _model_override=model_override)
```

2. After the streaming completes (which already prints the narrative to stdout via the streaming loop inside generate_report_streaming), print the social hook on a new line, visually separated:

```python
# Print social hook
print(f"\n---\n{result.social_hook}")
```

3. Update the hallucination check to use `result.narrative` instead of `report_text`:
```python
hallucination_report = check_hallucinated_metrics(result.narrative)
```

The hook is intentionally NOT checked by the hallucination guard -- it is a distillation of the synthesis, not a separate analytical output. It should reference the same metrics the synthesis already surfaced.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && PITCHER_NARRATIVES_TEST_MODEL=1 uv run python main.py -p 592155 2>/dev/null | tail -5</automated>
  </verify>
  <done>CLI prints narrative followed by separator and social hook. Hallucination check runs on narrative only. Exit code 0 in test mode.</done>
</task>

<task type="auto">
  <name>Task 3: Add tests for hook agent and ReportResult</name>
  <files>tests/test_report.py</files>
  <action>
Add the following tests to tests/test_report.py:

1. Import additions: add `ReportResult`, `hook_writer`, `_build_hook_message` to the import block from `report`.

2. `test_hook_writer_model_is_claude_sonnet` -- assert "claude-sonnet-4-6" in str(hook_writer.model).

3. `test_hook_writer_output_type_is_str` -- assert hook_writer.output_type is str.

4. `test_hook_message_includes_pitcher_name(ctx)` -- call `_build_hook_message(ctx, "test synthesis")` and assert ctx.pitcher_name is in the result.

5. `test_hook_message_includes_synthesis(ctx)` -- call `_build_hook_message(ctx, "Fastball velo down 1.5")` and assert "Fastball velo down 1.5" is in the result.

6. `test_report_result_has_social_hook(ctx)` -- call `generate_report_streaming(ctx, _model_override=TestModel(custom_output_text="hook text"))` and assert `isinstance(result, ReportResult)`, assert `result.social_hook` is a non-empty string, assert `result.narrative` is a non-empty string.

7. `test_report_result_narrative_matches_editor_output(ctx)` -- call with TestModel(custom_output_text="editor output"), assert `result.narrative == "editor output"`.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -m pytest tests/test_report.py -x -q</automated>
  </verify>
  <done>All existing tests pass plus 5+ new tests covering hook_writer agent, _build_hook_message, and ReportResult fields</done>
</task>

</tasks>

<verification>
```bash
# Full test suite passes
cd /Users/matt/src/pitcher-narratives && uv run python -m pytest tests/ -x -q

# Test mode CLI produces output with hook section
cd /Users/matt/src/pitcher-narratives && PITCHER_NARRATIVES_TEST_MODEL=1 uv run python main.py -p 592155
```
</verification>

<success_criteria>
- generate_report_streaming returns ReportResult with .narrative and .social_hook fields
- CLI prints the narrative (streamed) followed by a "---" separator and the social hook
- hook_writer agent uses a tight system prompt focused on 1-2 sentence insight hooks
- Hallucination guard runs on narrative only
- All tests pass (existing + new)
</success_criteria>

<output>
After completion, create `.planning/quick/260326-ukz-add-1-2-sentence-social-media-hook-summa/260326-ukz-SUMMARY.md`
</output>
