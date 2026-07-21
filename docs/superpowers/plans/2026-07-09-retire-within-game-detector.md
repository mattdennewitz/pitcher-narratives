# Retire the Within-Game (Game-Shape) Detector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the per-pitcher within-game (times-through-order) analysis entirely — the v1 deviation gate, the game-shape specialist, and the underlying TTO engine — dropping the analysis spine from 5 specialists to 4.

**Architecture:** This is a purely *subtractive* refactor across a tightly-coupled module (`pipeline.py`) and its consumers. Because the game-shape specialist, the TTO engine, and the deviation gate are interdependent, the removal is ordered top-down: **Task 1** cuts the specialist out of the runtime spine (5 → 4) while leaving the now-unused engine modules importable, so the suite stays green; **Task 2** deletes the orphaned engine/context/prompt wiring and the standalone TTO files; **Task 3** is the grep-gate + full-suite + end-to-end verification. There are no new abstractions and no new behavior — the "tests" are the existing suite with specialist-count assertions flipped to 4, plus a `grep` gate proving no residual references remain.

**Tech Stack:** Python 3.14, polars, pydantic-ai, pytest, `uv`.

## Global Constraints

- Python 3.14+; run everything via `uv run` (`.venv/` managed by `uv`).
- **Test data dir:** this branch is checked out in a git worktree. Tests need `PITCHER_NARRATIVES_DATA_DIR` pointed at the original repo's data. Prefix every test command with `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives`.
- **Known pre-existing baseline failures** (NOT caused by this work; permitted to remain): `test_to_prompt_token_budget`, `test_changes_trend_comparison_golden`, and the order-dependent `test_assemble_multi_frame_primary_matches_single` flake. No *new* failures are permitted.
- The spine goes 5 → 4 specialists: **stuff, location, run value, trends**. Game shape is removed, not reworded.
- Numbering after removal: writer-input sections and diagnostic listings run 1–4 (stuff=1, location=2, run value=3, trends=4). Trends keeps its slot; only the game-shape "5" entry is deleted.
- Subtractive only — do NOT refactor the four remaining specialists or introduce new types.
- Frequent, atomic commits (one per task minimum).

---

## File Structure

Files touched, and why:

**Task 1 (cut the specialist, spine 5 → 4):**
- Modify `src/pitcher_narratives/models.py` — drop `game_shape` from `SpecialistOutputs` and `CoreContext`.
- Modify `src/pitcher_narratives/pipeline.py` — delete the game-shape prompts, input builder, deviation block, agent field, and every orchestration reference; renumber writer-input/diagnostic sections 1–4.
- Modify `src/pitcher_narratives/personas.py` — `_SYNTHESIS_FRAMING`: "Five" → "Four", drop the "5. Game shape" line and other five-counts.
- Modify `src/pitcher_narratives/prompt_builder.py` — stop calling `render_tto_section` in the shared prompt and drop the TTO bullet (definition itself deleted in Task 2).
- Modify `src/pitcher_narratives/bench/runner.py` — drop the `game_shape` bench entries and the `_build_game_shape_input` import.
- Modify tests: `test_models.py`, `test_morning.py`, `test_signals.py`, `test_bench.py`, `test_agent_skills.py`, `test_pipeline.py`; **delete** `test_role_guidance.py` and `test_game_shape_input.py`.
- Regenerate `tests/fixtures/writer_prompt_{report,changes,recap}.txt`.

**Task 2 (delete the engine + wiring):**
- Delete `src/pitcher_narratives/engine/tto.py`, `src/pitcher_narratives/engine/deviation.py`, `src/pitcher_narratives/tto_baseline.py`.
- Modify `src/pitcher_narratives/engine/__init__.py` — drop TTO imports + `__all__` entries.
- Modify `src/pitcher_narratives/context.py` — drop the `tto` field, the `compute_tto_analysis` call, and the imports.
- Modify `src/pitcher_narratives/prompt_builder.py` — delete `render_tto_section`, its `__all__` entry, and the `TTOPitchType`/`TTOPlatoonSplit` imports.
- Modify `src/pitcher_narratives/data.py` — delete `tto_baseline_path` / `load_tto_baseline`.
- Delete artifact `var/tto_baseline.parquet` (if present).
- **Delete** `tests/test_tto_baseline.py`, `tests/test_tto_deviation.py`, `tests/test_tto_deviation_golden.py`, `tests/test_deviation.py`; strip the TTO block from `tests/test_engine.py`.

**Task 3:** verification only (grep gate + suite + smoke). No production edits except any stray reference the gate surfaces.

---

## Task 1: Cut the game-shape specialist (spine 5 → 4)

**Files:**
- Modify: `src/pitcher_narratives/models.py:47-55`, `:79-95`
- Modify: `src/pitcher_narratives/pipeline.py` (many regions — enumerated below)
- Modify: `src/pitcher_narratives/personas.py:71-96`, `:130`
- Modify: `src/pitcher_narratives/prompt_builder.py:43`, `:126-131`
- Modify: `src/pitcher_narratives/bench/runner.py:25`, `:136`, `:142`, `:168-176`
- Modify: `tests/test_models.py`, `tests/test_morning.py`, `tests/test_signals.py`, `tests/test_bench.py`, `tests/test_agent_skills.py`, `tests/test_pipeline.py`
- Delete: `tests/test_role_guidance.py`, `tests/test_game_shape_input.py`
- Regenerate: `tests/fixtures/writer_prompt_report.txt`, `writer_prompt_changes.txt`, `writer_prompt_recap.txt`

**Interfaces:**
- Consumes: existing `PitcherContext` (its `.tto` field still exists after Task 1 — untouched here; removed in Task 2).
- Produces (post-task signatures other code relies on):
  - `SpecialistOutputs(stuff: str, location: str, runvalue: str, trends: str)` — no `game_shape`.
  - `CoreContext(stuff, location, runvalue, *, audit_flags=[], residual_specialists=[])` — no `game_shape`.
  - `build_writer_input(ctx, stuff, location, runvalue, trends, *, key_signals=None) -> str` — no `game_shape` positional.
  - `run_specialists(stuff_agent, location_agent, runvalue_agent, trends_agent, ctx, _model_override=None, *, names=None, ...)` — no `game_shape_agent`.
  - `PipelineAgents` — no `game_shape` field; `specialist_dict()` returns four.
  - `_CORE_SPECIALISTS = ["stuff", "location", "runvalue"]`; `_SPECIALIST_ORDER` has no `game_shape`.

### Test-first: flip the count assertions to 4

- [ ] **Step 1: Update `test_models.py` to the 4-field models**

In `tests/test_models.py`, remove every `game_shape=...` kwarg and the `core.game_shape` assertion. The two constructions become:

```python
    core = CoreContext(
        stuff="s", location="l", runvalue="r",
    )
    assert core.stuff == "s"
    # (delete: assert core.game_shape == "g")
```
```python
    assert CoreContext(stuff="s", location="l", runvalue="r").audit_flags == []
```

- [ ] **Step 2: Update `test_morning.py` SpecialistOutputs constructions**

In `tests/test_morning.py`, drop the `game_shape=...` kwarg at lines ~21, ~430, ~617 and drop `game_shape` from the `stuff = location = runvalue = trends = game_shape = auditor = _noop` tuple at line ~446 (remove the `game_shape =` link so it reads `stuff = location = runvalue = trends = auditor = _noop`).

```python
    # e.g. line ~430
    SpecialistOutputs(stuff="S", location="L", runvalue="R", trends="T")
```

- [ ] **Step 3: Update `test_signals.py` build_writer_input calls**

In `tests/test_signals.py` (4 call sites ~133, 151, 166, 193), delete the `"game_shape output"` positional argument so each call passes `ctx, stuff, location, runvalue, trends` then keyword args. Example:

```python
        result = build_writer_input(
            ctx, "stuff output", "location output", "runvalue output",
            "trends output", key_signals=ks,
        )
```

- [ ] **Step 4: Update `test_agent_skills.py` specialist tuple**

In `tests/test_agent_skills.py:82`, drop `game_shape` from the iteration tuple:

```python
    for name in ("stuff", "location", "runvalue", "trends", "writer"):
```

- [ ] **Step 5: Update `test_bench.py` expected labels**

In `tests/test_bench.py`, update the docstring "5 specialists" → "4 specialists" (line ~218) and remove `"specialist:game_shape"` from the expected-key tuples at lines ~228 and ~257.

- [ ] **Step 6: Update `test_pipeline.py` orchestration calls**

In `tests/test_pipeline.py`, fix the two direct `run_specialists` calls to pass four agents instead of five:

```python
    # line ~1886
    asyncio.run(run_specialists(agent, agent, agent, agent, ctx))
```

For line ~1913's `run_specialists(...)` call, likewise drop the fifth `agent` positional. Search the file for any other `game_shape` reference (e.g. assertions on `_SPECIALIST_ORDER`, `specialist_dict`, or SpecialistOutputs field counts) and update the expected value to four. Do NOT change behavior — only the specialist count.

- [ ] **Step 7: Delete the two game-shape-only test files**

```bash
git rm tests/test_role_guidance.py tests/test_game_shape_input.py
```

- [ ] **Step 8: Run the updated tests to confirm they now FAIL (red)**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_models.py tests/test_signals.py tests/test_agent_skills.py -x -q
```
Expected: FAIL — `SpecialistOutputs`/`CoreContext` still *require* `game_shape`, and `build_writer_input` still *expects* the positional. This proves the tests now describe the 4-specialist target.

### Make it pass: remove game_shape from the models

- [ ] **Step 9: Drop `game_shape` from the two models**

In `src/pitcher_narratives/models.py`, `SpecialistOutputs` (line ~47) loses its last field:

```python
class SpecialistOutputs(BaseModel):
    """Raw outputs from each specialist agent."""

    stuff: str
    location: str
    runvalue: str
    trends: str
```

`CoreContext` (line ~79) loses its `game_shape` field and the docstring drops "game-shape":

```python
    stuff: str
    location: str
    runvalue: str
    audit_flags: list[AuditFlag] = []
    residual_specialists: list[str] = []
```

Update the `CoreContext` docstring line "the clean stuff/location/run-value/game-shape specialist outputs" → "the clean stuff/location/run-value specialist outputs".

### Remove game_shape from pipeline.py

- [ ] **Step 10: Delete the game-shape prompt constants**

In `src/pitcher_narratives/pipeline.py`, delete these definitions in full: `_GAME_SHAPE_SPECIALIST_PROMPT` (line ~401-427), `_SP_GAME_SHAPE_GUIDANCE` (~437-444), `_RP_GAME_SHAPE_GUIDANCE` (~446-452), and the role-guidance comment block above them (~430-435). Also in the trends specialist prompt, delete the now-false line (~397-398):

```
- Do NOT analyze TTO patterns, velocity arcs, or within-game \
progression — a separate specialist handles that.
```

- [ ] **Step 11: Delete the deviation block and game-shape input builder**

Delete `_role_game_shape_guidance` (line ~865-880), `_render_deviation_block` (~883-916), and `_build_game_shape_input` (~918 to the end of that function). Also delete the module-top import it used: `from pitcher_narratives.engine.tto import TTODeviation` (line ~95).

- [ ] **Step 12: Renumber `build_writer_input` and drop its `game_shape` param**

`build_writer_input` (line ~995) loses the `game_shape: str` parameter and the "Specialist Analysis 5" line:

```python
def build_writer_input(
    ctx: PitcherContext,
    stuff: str,
    location: str,
    runvalue: str,
    trends: str,
    *,
    key_signals: KeySignals | None = None,
) -> str:
```
```python
    parts.extend([
        f"## Specialist Analysis 1: Stuff\n{stuff}\n",
        f"## Specialist Analysis 2: Location\n{location}\n",
        f"## Specialist Analysis 3: Run Value\n{runvalue}\n",
        f"## Specialist Analysis 4: Trends\n{trends}",
    ])
```
(Note the trailing `\n` moves off `trends` since it is now the last section.)

- [ ] **Step 13: Drop game_shape from the ground-truth and parity builders**

`_build_capsule_ground_truth` (line ~551) `names` list and its "all five" docstring:

```python
    names = ["stuff", "location", "runvalue", "trends"]
```
Change the docstring "all five specialists' input tables" → "all four specialists' input tables".

`_build_parity_union` (line ~586) `specialist_prose` dict drops the game_shape entry:

```python
    specialist_prose = {
        "stuff": specialists.stuff,
        "location": specialists.location,
        "runvalue": specialists.runvalue,
        "trends": specialists.trends,
    }
```

`_get_specialist_input` (line ~1090) builders dict drops game_shape:

```python
    builders = {
        "stuff": _build_stuff_input,
        "location": _build_location_input,
        "runvalue": _build_runvalue_input,
    }
```

- [ ] **Step 14: Renumber the diagnostic listing (full-pipeline prompts)**

At line ~1361, delete the `("SPECIALIST 5: GAME SHAPE", ...)` tuple entry from `specialist_phases`. In the same function, change the three "all 5 specialist outputs" strings (lines ~1374, ~1382, ~1390) to "all 4 specialist outputs".

- [ ] **Step 15: Drop game_shape from `PipelineAgents` and `make_pipeline_agents`**

`PipelineAgents` (line ~1560) loses the `game_shape: Agent[None, str]` field; `specialist_dict` (line ~1576) loses the `"game_shape": self.game_shape` entry and its docstring says "four" not "five". `make_pipeline_agents` (line ~1666) drops the `game_shape=_mini_specialist_compact(_GAME_SHAPE_SPECIALIST_PROMPT),` construction line.

- [ ] **Step 16: Drop `game_shape_agent` from `run_specialists`**

`run_specialists` (line ~1695) loses the `game_shape_agent` parameter, the `"game_shape": (...)` entry in `all_inputs` (line ~1720), and the docstring "all five run" → "all four run":

```python
async def run_specialists(
    stuff_agent: Agent[None, str],
    location_agent: Agent[None, str],
    runvalue_agent: Agent[None, str],
    trends_agent: Agent[None, str],
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    names: list[str] | None = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
    trend_frame_comparison: str | None = None,
) -> SpecialistOutputs:
```
```python
    all_inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (trends_agent, _build_trend_input(ctx, frame_comparison=trend_frame_comparison)),
    }
```

- [ ] **Step 17: Fix the two `run_specialists` call sites in the spine**

`_CORE_SPECIALISTS` (line ~1745) drops game_shape:

```python
_CORE_SPECIALISTS = ["stuff", "location", "runvalue"]
```

`_SPECIALIST_ORDER` (line ~1782) drops game_shape and its `_order_flags` docstring stops mentioning game-shape ordering:

```python
_SPECIALIST_ORDER = {
    "stuff": 0, "location": 1, "runvalue": 2, "trends": 3,
}
```

`run_spine_core` (line ~1765) call passes four agents; `CoreContext(...)` drops `game_shape=clean.game_shape`:

```python
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, ctx, _model_override,
        names=_CORE_SPECIALISTS, tracker=tracker, tracker_model=mini,
    )
```
```python
    return CoreContext(
        stuff=clean.stuff, location=clean.location,
        runvalue=clean.runvalue,
        audit_flags=flags,
        residual_specialists=sorted(residual),
    )
```

`run_spine_tail` (line ~1822) call passes four agents; the `merged = SpecialistOutputs(...)` drops game_shape; the `build_writer_input(...)` at line ~1838 drops `specialists.game_shape`:

```python
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, ctx, _model_override,
        names=_TAIL_SPECIALISTS, tracker=tracker, tracker_model=mini,
        trend_frame_comparison=trend_frame_comparison,
    )
    merged = SpecialistOutputs(
        stuff=core.stuff, location=core.location, runvalue=core.runvalue,
        trends=raw.trends,
    )
```
```python
    signal_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends,
    )
```

- [ ] **Step 18: Fix the writer-input and synthesis render in the terminal**

At line ~2287, the `build_writer_input(...)` call drops `specialists.game_shape`:

```python
    writer_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends,
        key_signals=key_signals,
    )
```

At line ~2315, `specialist_synthesis` drops the `GAME SHAPE:` block (trends becomes the last block — drop its trailing blank-line separator):

```python
    specialist_synthesis = (
        f"STUFF:\n{specialists.stuff}\n\n"
        f"LOCATION:\n{specialists.location}\n\n"
        f"RUN VALUE:\n{specialists.runvalue}\n\n"
        f"TRENDS:\n{specialists.trends}"
    )
```

- [ ] **Step 19: Update the module docstring and stale "five" comments**

In `pipeline.py`, change the module docstring (lines ~4, ~11) "Phase 1: 5 specialist agents" → "Phase 1: 4 specialist agents" and delete the "Game Shape Analyst: TTO degradation..." bullet. Update comment ~179 ("across all five specialists" → "four"), the `run_analysis_spine` docstring ~1886-1887 ("all five specialists"/"all five audits" → "four"), and the streaming docstrings ~2492 / ~2580 ("5 specialists run concurrently" → "4 specialists run concurrently").

### Remove game_shape from personas, prompt_builder, bench

- [ ] **Step 20: Re-frame the synthesis prompt to four analyses**

In `src/pitcher_narratives/personas.py`, `_SYNTHESIS_FRAMING` (line ~75) changes "Five specialist analyses" → "Four specialist analyses", deletes the "5. Game shape — ..." list line (~80), and everywhere it says "all five analyses" / "five specialists" / "the five analyses" (lines ~85, ~88, ~130) → "four". Verify the numbered list now runs 1–4 with no gaps.

- [ ] **Step 21: Stop rendering the TTO section into the shared prompt**

In `src/pitcher_narratives/prompt_builder.py`, delete the `sections.append(render_tto_section(ctx))` call (line ~43) and the TTO bullet block (lines ~126-131):

```python
    # (delete)
    # tto = ctx.tto
    # if tto and tto.available and tto.summary:
    #     bullets.append(f"TTO: {tto.summary}")
```
(The `render_tto_section` *definition* and its imports are deleted in Task 2 — leaving them briefly unused here keeps Task 1's suite green.)

- [ ] **Step 22: Drop the game-shape bench entries**

In `src/pitcher_narratives/bench/runner.py`: remove the `_build_game_shape_input` import (line ~25), the two `"specialist:game_shape"` dict entries (lines ~136, ~142), the `result.specialists.game_shape` positional in the `build_writer_input(...)` call (lines ~168-176), and drop `game_shape` from the specialist-list comment (~81).

- [ ] **Step 23: Run the full suite (expect fixture failures only)**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest -q
```
Expected: the only new failures are `test_single_voice.py::test_matches_frozen_fixture[report|changes|recap]` (the writer system prompt now says "Four", so it no longer matches the frozen fixtures), plus the 3 documented pre-existing failures. Any *other* failure is a missed call site — fix it before continuing.

- [ ] **Step 24: Regenerate the three writer-prompt fixtures and review the diff**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -c "
from pathlib import Path
from pitcher_narratives.personas import build_writer_system_prompt
from tests.test_single_voice import _MODES
fix = Path('tests/fixtures')
for mode_id, mode in _MODES.items():
    (fix / f'writer_prompt_{mode_id}.txt').write_text(build_writer_system_prompt(mode))
"
git diff tests/fixtures/
```
Confirm the diff shows ONLY: "Five" → "Four", the dropped "5. Game shape" line, and renumbered counts — nothing else. If any unexpected content changed, stop and investigate.

- [ ] **Step 25: Run the full suite green**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest -q
```
Expected: PASS except the 3 documented pre-existing failures. No game-shape-related failures.

- [ ] **Step 26: Commit**

```bash
git add -A
git commit -m "refactor: cut game-shape specialist — analysis spine 5 → 4

Removes the within-game (TTO) specialist, its prompts, deviation block,
and every orchestration reference; re-frames synthesis to four analyses
and regenerates the writer-prompt fixtures. Engine modules remain
importable (deleted in the follow-up)."
```

---

## Task 2: Delete the TTO engine, deviation gate, and context/prompt wiring

**Files:**
- Delete: `src/pitcher_narratives/engine/tto.py`, `src/pitcher_narratives/engine/deviation.py`, `src/pitcher_narratives/tto_baseline.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`, `src/pitcher_narratives/context.py`, `src/pitcher_narratives/prompt_builder.py`, `src/pitcher_narratives/data.py`
- Delete: `tests/test_tto_baseline.py`, `tests/test_tto_deviation.py`, `tests/test_tto_deviation_golden.py`, `tests/test_deviation.py`
- Modify: `tests/test_engine.py` (strip the TTO block, ~lines 34/58/860-945)
- Delete artifact: `var/tto_baseline.parquet` (if present)

**Interfaces:**
- Consumes: the Task 1 result (no runtime consumer of `ctx.tto` remains except the prompt render removed here).
- Produces: `PitcherContext` with no `tto` field; `engine` package with no TTO exports; `prompt_builder` with no `render_tto_section`; `data` with no TTO-baseline helpers.

### Test-first: delete the tests that exercise the removed engine

- [ ] **Step 1: Remove the standalone TTO/deviation test files**

```bash
git rm tests/test_tto_baseline.py tests/test_tto_deviation.py \
       tests/test_tto_deviation_golden.py tests/test_deviation.py
```

- [ ] **Step 2: Strip the TTO block from `test_engine.py`**

In `tests/test_engine.py`, remove `TTOAnalysis` (line ~34) and `compute_tto_analysis` (line ~58) from the imports, and delete every `compute_tto_analysis`-based test in the ~860-945 range (the `TTOAnalysis`/`tto = compute_tto_analysis(data)` block). Leave the rest of the file intact.

- [ ] **Step 3: Run test_engine.py to confirm it FAILS on the import (red)**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_engine.py -q
```
Expected: it still imports `TTOAnalysis`/`compute_tto_analysis` from `engine` (facade unchanged yet) — if you removed all references it collects clean; if a stray reference remains it errors. Either way this pins the target before deleting the engine.

### Delete the engine + wiring

- [ ] **Step 4: Remove TTO from the engine facade**

In `src/pitcher_narratives/engine/__init__.py`, delete the entire `from pitcher_narratives.engine.tto import (...)` block (lines ~79-85) and remove `"TTOAnalysis"`, `"TTOPitchType"`, `"TTOPlatoonSplit"`, `"TTOSplit"`, and `"compute_tto_analysis"` from `__all__` (lines ~115-118, ~135).

- [ ] **Step 5: Remove `tto` from `PitcherContext`**

In `src/pitcher_narratives/context.py`: delete `TTOAnalysis` (line ~28) and `compute_tto_analysis` (line ~43) from the `engine` import block; delete the `tto: TTOAnalysis | None` field (line ~94); delete `tto = compute_tto_analysis(data)` (line ~137); and delete `tto=tto,` from the `PitcherContext(...)` construction (line ~163).

- [ ] **Step 6: Delete `render_tto_section` and its imports from prompt_builder**

In `src/pitcher_narratives/prompt_builder.py`: delete the `from pitcher_narratives.engine import TTOPitchType, TTOPlatoonSplit` import (line ~12), remove `"render_tto_section"` from `__all__` (line ~30), and delete the `render_tto_section` function definition (lines ~215 to the end of that function). (Its two call sites were already removed in Task 1 Step 21.)

- [ ] **Step 7: Delete the TTO-baseline data helpers and module**

In `src/pitcher_narratives/data.py`, delete `tto_baseline_path` and `load_tto_baseline` (and any `TTO`-related import at the top). Then:

```bash
git rm src/pitcher_narratives/engine/tto.py \
       src/pitcher_narratives/engine/deviation.py \
       src/pitcher_narratives/tto_baseline.py
rm -f var/tto_baseline.parquet
```

- [ ] **Step 8: Run the full suite green**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest -q
```
Expected: PASS except the 3 documented pre-existing failures. (`test_to_prompt_token_budget` may now behave differently since the TTO section left the prompt — if it flips to PASS, that is acceptable and welcome; note it in the commit. If any import error surfaces, a reference to a deleted symbol remains — fix it.)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: delete TTO engine, deviation gate, and context/prompt wiring

Removes engine/tto.py, engine/deviation.py, tto_baseline.py, the
ctx.tto field, render_tto_section, and the TTO-baseline data helpers.
The within-game signal is no longer computed or rendered anywhere."
```

---

## Task 3: Grep gate + full-suite + end-to-end verification

**Files:** none (verification only; fix any stray reference the gate surfaces in its owning file).

- [ ] **Step 1: Residual-reference grep gate**

Run (must return NOTHING under `src/`, `tests/`, `bench/`; docs/comments elsewhere are exempt):

```bash
grep -rnE "game_shape|TTOAnalysis|compute_tto_analysis|evaluate_tto_deviations|TTODeviation|load_tto_baseline|tto_baseline_path|render_tto_section|_build_game_shape_input|_render_deviation_block|_role_game_shape_guidance" \
  src/ tests/ --include='*.py'
```
Expected: no output. Also confirm no engine-level `deviation` symbol survives:
```bash
grep -rnE "engine\.deviation|from pitcher_narratives\.engine\.tto|import deviation" src/ tests/ --include='*.py'
```
Expected: no output. If anything prints, remove it in its file and re-run.

- [ ] **Step 2: Full suite**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest -q
```
Expected: PASS with only the documented pre-existing failures (`test_to_prompt_token_budget` — unless it now passes —, `test_changes_trend_comparison_golden`, and the `test_assemble_multi_frame_primary_matches_single` order flake). Record the pass/fail count.

- [ ] **Step 3: End-to-end smoke — a report still generates from four specialists**

Drive the real report path for one pitcher and confirm a non-empty capsule is produced with no game-shape/TTO reference. Use the project's report entry point (check `cli.py` for the exact command); e.g.:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run python -m pitcher_narratives.cli report <PITCHER_ID> 2>&1 | tee /tmp/retire-smoke.txt
```
Expected: a complete narrative prints; `grep -i "tto\|times through\|game shape" /tmp/retire-smoke.txt` returns nothing (the report no longer narrates within-game shape). If the CLI needs a live model key and none is available, substitute the pipeline's offline/mock smoke test used elsewhere in `tests/test_pipeline.py` and confirm it exercises the four-specialist path.

- [ ] **Step 4: Final commit (only if Step 1/3 required a fix)**

```bash
git add -A
git commit -m "chore: scrub residual within-game references (grep gate)"
```

---

## Self-Review

**Spec coverage** (against `2026-07-09-retire-within-game-detector-design.md`):
- §3 Deviation-gate machinery (deviation.py, tto_baseline.py, evaluate_tto_deviations/TTODeviation, _render_deviation_block, deviation wiring, load_tto_baseline) → Task 1 Steps 10-11 + Task 2 Steps 4-7. ✔
- §3 Game-shape specialist + TTO engine (engine/tto.py, context tto field/call, pipeline prompts/builders/agent/orchestration, models.py fields, personas five→four, bench entries) → Task 1 Steps 9-22 + Task 2 Steps 4-6. ✔
- §4 What is kept: the 3 diagnostic harnesses (`scripts/tto_*.py`) and the design docs are NOT touched by any task. ✔ The retired banner on `2026-07-08-game-shape-deviation-gate-design.md` was already added in commit `0740cfc` — no task needed. ✔
- §5 Spine 5 → 4 across run_specialists/make_pipeline_agents/PipelineAgents/names/models → Task 1 Steps 9, 15-18. ✔
- §5 Synthesis framing four analyses + writer fixtures re-baselined → Task 1 Steps 20, 24. ✔
- §6 Testing: suite green (Task 3 Step 2), count tests updated (Task 1 Steps 1-6), fixtures re-baselined (Step 24), grep gate (Task 3 Step 1), pipeline smoke (Task 3 Step 3). ✔
- §7 Non-goals: no change to the four remaining specialists, no replacement feature, harnesses kept — plan is subtractive only. ✔

**Additions beyond the spec's file list** (discovered by reading the code, not in the spec's enumeration): `render_tto_section` lives in `prompt_builder.py` (not pipeline) and is *called in the shared context prompt* at line 43 plus a TTO bullet at 126-131 → handled Task 1 Step 21 / Task 2 Step 6. `CoreContext.game_shape` (models.py:92) and `_SPECIALIST_ORDER`/`_CORE_SPECIALISTS` → handled. `data.py::tto_baseline_path`/`load_tto_baseline` live in `data.py` (spec said `data.tto_baseline_path`) → handled Task 2 Step 7.

**Placeholder scan:** every code step shows the exact replacement text; no "TBD"/"add error handling"/"similar to". ✔

**Type consistency:** `SpecialistOutputs`/`CoreContext`/`build_writer_input`/`run_specialists`/`PipelineAgents` signatures in the Interfaces blocks match the edits in Steps 9, 12, 15-18. Trends keeps index 3; game_shape (index 4) is the only removal. ✔
