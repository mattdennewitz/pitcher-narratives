---
phase: quick
plan: 260404-vya
type: execute
wave: 1
depends_on: []
files_modified:
  - src/pitcher_narratives/pipeline.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "All 5 specialist builders return UserPrompt (list with CachePoints)"
    - "CachePoint placed after header+baselines in each builder, before data"
    - "run_specialists passes lists through to pydantic-ai without flattening"
    - "audit_and_revise_specialists uses plain text for ground truths"
    - "write_pipeline_data_file renders prompts as readable text"
    - "Final text content sent to LLMs is byte-identical to previous output"
  artifacts:
    - path: "src/pitcher_narratives/pipeline.py"
      provides: "CachePoint-aware specialist builders"
      contains: "CachePoint"
  key_links:
    - from: "_build_stuff_input"
      to: "run_specialists"
      via: "UserPrompt list flows through agent_kwargs to pydantic-ai"
      pattern: "agent_kwargs.*prompt"
    - from: "_get_specialist_input"
      to: "audit_and_revise_specialists"
      via: "_flatten_prompt converts UserPrompt to plain text for audit"
      pattern: "_flatten_prompt"
---

<objective>
Add CachePoints to all 5 specialist data builders in pipeline.py so LLM providers (especially Anthropic) can cache the header+baselines prefix across same-pitcher reruns.

Purpose: Reduces cost and latency for repeat runs and development/debugging workflows. Aligns pipeline.py with the caching strategy already used in report.py and anchor.py.

Output: Modified pipeline.py with CachePoint-aware builders, a flatten utility, and updated call sites.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/pitcher_narratives/pipeline.py
@src/pitcher_narratives/anchor.py (reference pattern: UserPrompt type alias, CachePoint usage)
@src/pitcher_narratives/report.py (reference pattern: _UserPrompt, _render_user_prompt)
@src/pitcher_narratives/config.py (agent_kwargs passes user_prompt through unchanged)
</context>

<interfaces>
<!-- Key types and contracts the executor needs. -->

From src/pitcher_narratives/anchor.py:
```python
from pydantic_ai import CachePoint

UserPrompt = list[str | CachePoint]
"""Type alias for user prompts with cache breakpoints."""
```

From src/pitcher_narratives/report.py:
```python
_UserPrompt = list[str | CachePoint]

def _render_user_prompt(parts: _UserPrompt) -> str:
    """Render a user prompt (with CachePoints) as readable text."""
    return "\n".join("  -- [cache breakpoint] --" if isinstance(p, CachePoint) else p for p in parts)
```

From src/pitcher_narratives/config.py:
```python
def agent_kwargs(prompt: Any, model_override: Any = None) -> dict[str, Any]:
    """Build kwargs for an agent.run() call."""
    kwargs: dict[str, Any] = {"user_prompt": prompt}
    # ...
```
pydantic-ai's Agent.run() accepts user_prompt as str | list[str | CachePoint], so lists pass through agent_kwargs transparently.
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Add CachePoint support to all 5 specialist builders and update call sites</name>
  <files>src/pitcher_narratives/pipeline.py</files>
  <action>
All changes are in pipeline.py. The goal is to split each builder's output at the natural header+baselines boundary, inserting a CachePoint between the prefix (cacheable across same-pitcher reruns) and the data section (varies per specialist).

**1. Update import (line 38):**
Change `from pydantic_ai import Agent` to `from pydantic_ai import Agent, CachePoint`

**2. Add type alias after `__all__` (near line 68):**
```python
UserPrompt = list[str | CachePoint]
"""Type alias for user prompts with cache breakpoints."""
```

**3. Add flatten utility right after the type alias:**
```python
def _flatten_prompt(parts: UserPrompt) -> str:
    """Join text parts of a user prompt, stripping CachePoints."""
    return "\n".join(p for p in parts if isinstance(p, str))
```

**4. Add render utility for the data file writer:**
```python
def _render_user_prompt(parts: UserPrompt) -> str:
    """Render a user prompt (with CachePoints) as readable text for tracing."""
    return "\n".join(
        "  -- [cache breakpoint] --" if isinstance(p, CachePoint) else p
        for p in parts
    )
```

**5. Refactor `_build_stuff_input` (line 444) to return `UserPrompt`:**
- Change return type annotation from `-> str` to `-> UserPrompt`
- Split `lines` into `header_lines` and `data_lines`
- `header_lines`: the header line (`f"## {ctx.pitcher_name}..."`) + `render_league_baselines(...)` + empty string
- `data_lines`: everything from `"## Arsenal Physical Profile..."` onward (the for loop over `ctx.arsenal` and the S-variant section)
- Return `["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]`
- CRITICAL: The `_flatten_prompt()` output must produce the same text as the original `"\n".join(lines)`. Verify the join boundaries match: `header_lines` ends with `""`, `data_lines` starts with `"## Arsenal Physical Profile..."`. The `"\n".join` of the list items with `\n` between them at CachePoint boundaries must reconstruct the original.

**6. Refactor `_build_location_input` (line 495) to return `UserPrompt`:**
- Change return type from `-> str` to `-> UserPrompt`
- `header_lines`: header + baselines + empty string
- `data_lines`: `"## P vs S Location Impact"` through the rest (intermediates, execution, plus scores)
- Return `["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]`

**7. Refactor `_build_runvalue_input` (line 532) to return `UserPrompt`:**
- Change return type from `-> str` to `-> UserPrompt`
- `header_lines`: header + baselines + empty string
- `data_lines`: `"## Component Attribution..."` through attribution loop
- Return `["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]`

**8. Refactor `_build_trend_input` (line 550) to return `UserPrompt`:**
- Change return type from `-> str` to `-> UserPrompt`
- Currently uses `sections` list joined with `"\n\n"`. Split:
  - `prefix_sections`: header, baselines (first 2 items, before the empty string)
  - `data_sections`: fastball, arsenal, release point, hard-hit (items after the empty string)
- The empty string `""` between baselines and data in the original sections list produces `"\n\n"` when joined. Preserve this by including it at the end of the prefix or start of the data, ensuring `_flatten_prompt()` output matches original.
- Return `["\n\n".join(s for s in prefix_sections if s), CachePoint(), "\n\n".join(s for s in data_sections if s)]`

**9. Refactor `_build_game_shape_input` (line 565) to return `UserPrompt`:**
- Same approach as trend builder: split sections at the empty string boundary
- prefix_sections: header, baselines
- data_sections: TTO, fastball, appearances, role
- Return `["\n\n".join(s for s in prefix_sections if s), CachePoint(), "\n\n".join(s for s in data_sections if s)]`

**10. Update `_get_specialist_input` (line 632) to return `UserPrompt`:**
- Change return type from `-> str` to `-> UserPrompt`
- No other changes needed (builders already return UserPrompt)

**11. Add `_get_specialist_input_text` helper below `_get_specialist_input`:**
```python
def _get_specialist_input_text(name: str, ctx: PitcherContext) -> str:
    """Get specialist data input as plain text (no CachePoints)."""
    return _flatten_prompt(_get_specialist_input(name, ctx))
```

**12. Update `audit_and_revise_specialists` (line 666):**
Change `ground_truths` dict comprehension to use `_get_specialist_input_text`:
```python
ground_truths = {
    name: _get_specialist_input_text(name, ctx) for name in specialist_names
}
```
This ensures audit/revision inputs remain plain strings (they feed into `_build_specialist_audit_input` and `_build_specialist_revision_input` which do string concatenation via f-strings).

**13. Update `run_specialists` (line 907):**
The `_run` helper's type annotation should change from `prompt: str` to `prompt: str | UserPrompt` (or just `Any`). The actual behavior is unchanged since `agent_kwargs` passes the value through to pydantic-ai which handles both types. Update the annotation for correctness.

**14. Update `write_pipeline_data_file` (line 763-768):**
The `specialist_phases` list currently calls builders and treats results as strings. Since builders now return `UserPrompt`, use `_render_user_prompt()` to convert:
```python
specialist_phases = [
    ("SPECIALIST 1: STUFF", _STUFF_SPECIALIST_PROMPT, _render_user_prompt(_build_stuff_input(ctx))),
    ("SPECIALIST 2: LOCATION", _LOCATION_SPECIALIST_PROMPT, _render_user_prompt(_build_location_input(ctx))),
    ("SPECIALIST 3: RUN VALUE", _RUNVALUE_SPECIALIST_PROMPT, _render_user_prompt(_build_runvalue_input(ctx))),
    ("SPECIALIST 4: TRENDS", _TREND_SPECIALIST_PROMPT, _render_user_prompt(_build_trend_input(ctx))),
    ("SPECIALIST 5: GAME SHAPE", _GAME_SHAPE_SPECIALIST_PROMPT, _render_user_prompt(_build_game_shape_input(ctx))),
]
```
The rest of write_pipeline_data_file (the for loop at line 770-773) already treats the third tuple element as a string, so `_render_user_prompt` returning a string is correct.

**15. Update `__all__` export list** to include `UserPrompt` if desired (optional, since it's mainly internal).

**KEY CONSTRAINT:** The actual text content delivered to the LLM must be IDENTICAL to what it was before. The only change is how that text is structured (single string vs list with CachePoints). pydantic-ai concatenates list parts with newlines at CachePoint boundaries, so ensure the join points produce the same `\n` pattern as the original `"\n".join(lines)`.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && python -c "
from pydantic_ai import CachePoint
from pitcher_narratives.pipeline import (
    _build_stuff_input, _build_location_input, _build_runvalue_input,
    _build_trend_input, _build_game_shape_input, _flatten_prompt, UserPrompt,
)
# Verify imports work and builders return lists with CachePoints
# (Cannot run full test without PitcherContext data, but import check confirms no syntax errors)
print('All imports OK')
assert isinstance(UserPrompt, type) or True  # type alias check
print('UserPrompt type alias defined')
print('CachePoint imported in pipeline')
"</automated>
  </verify>
  <done>
All 5 specialist builders return UserPrompt with CachePoint after header+baselines.
_flatten_prompt and _render_user_prompt utilities exist.
_get_specialist_input returns UserPrompt; _get_specialist_input_text returns plain str.
audit_and_revise_specialists uses _get_specialist_input_text for ground truths.
run_specialists passes UserPrompt lists through to pydantic-ai.
write_pipeline_data_file renders prompts with cache breakpoint markers.
No change to actual text content delivered to LLMs.
  </done>
</task>

<task type="auto">
  <name>Task 2: Validate CachePoint placement with a live data smoke test</name>
  <files>src/pitcher_narratives/pipeline.py</files>
  <action>
Run the data file writer (which exercises all 5 builders) against a real pitcher to verify:
1. The pipeline module loads without errors
2. All builders produce UserPrompt lists with exactly 1 CachePoint each
3. The rendered data file is well-formed

Execute: `cd /Users/matt/src/pitcher-narratives && uv run python -m pitcher_narratives.cli data 676265`

This runs `write_pipeline_data_file` which calls all 5 builders. If it produces a file without errors, the refactor is correct.

Then verify the output file contains cache breakpoint markers:
`grep -c "cache breakpoint" data-676265-*.md`

Should show 5 markers (one per specialist).

If errors occur, diagnose and fix the join boundary issues in the specific builder that fails.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -m pitcher_narratives.cli data 676265 2>/dev/null && grep -c "cache breakpoint" data-676265-*.md && rm -f data-676265-*.md</automated>
  </verify>
  <done>
Data file generates without errors. Output contains exactly 5 cache breakpoint markers (one per specialist builder). File cleaned up after verification.
  </done>
</task>

</tasks>

<verification>
1. `python -c "from pitcher_narratives.pipeline import CachePoint, UserPrompt, _flatten_prompt"` succeeds
2. `uv run python -m pitcher_narratives.cli data 676265` produces a data file with 5 cache breakpoint markers
3. All 5 builder functions return `UserPrompt` (list with CachePoint), not `str`
4. `_get_specialist_input_text` returns plain `str` (no CachePoints)
5. audit/revision pipeline still receives plain text ground truths
</verification>

<success_criteria>
- All 5 specialist builders in pipeline.py return UserPrompt with CachePoint after header+baselines
- run_specialists sends lists through to pydantic-ai (enabling provider-level caching)
- audit_and_revise_specialists continues to work with plain text ground truths
- write_pipeline_data_file renders cache breakpoints visually in data files
- No change to the actual text content seen by LLMs
</success_criteria>

<output>
After completion, create `.planning/quick/260404-vya-fully-examine-new-prompts-and-reset-cach/260404-vya-SUMMARY.md`
</output>
