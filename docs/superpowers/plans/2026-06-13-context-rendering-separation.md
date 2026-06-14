# Context Rendering Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the ~540 lines of markdown-rendering logic out of the `PitcherContext` Pydantic model into a dedicated `prompt_builder.py`, leaving `context.py` as a focused data model + assembly module, and remove `pipeline.py`'s reach into private `_render_*` methods.

**Architecture:** `PitcherContext` becomes a near-pure data container: it keeps its fields, `assemble_pitcher_context()`, and a single public `to_prompt()` method that delegates one line into `prompt_builder.build_pitcher_prompt(self)`. All 15 `_render_*` section methods move to `prompt_builder.py` as public free functions `render_<section>(ctx)`. The eight private render calls in `pipeline.py` are repointed at those free functions.

**Tech Stack:** Python 3.14, pydantic, polars, pytest, uv, ruff.

**Prerequisite:** This plan is independent of the engine split but reads cleanest after it. It can run before or after `2026-06-13-engine-subpackage-split.md`.

---

## Critical Context for the Implementer

### Why `to_prompt()` stays on the model

`to_prompt()` is real public API. It is called by:
- `tests/test_context.py` — 15+ assertions (`ctx.to_prompt()`).
- `src/pitcher_narratives/analyst.py:267` — `ctx.deps.context.to_prompt()`.
- `src/pitcher_narratives/bench/runner.py:71` — `ground_truth = ctx.to_prompt()`.

Deleting it would churn 17+ call sites for zero architectural gain. Instead, `to_prompt()` survives as a **one-line delegator**. The bulk (the 15 `_render_*` methods) moves out. That is the actual size win: `context.py` drops from 698 to ~160 lines.

### The real smell being fixed

`pipeline.py` reaches into eight **private** methods of the model to build specialist inputs (lines 643–646, 650, 694–697):
```python
ctx._render_fastball_section()
ctx._render_arsenal_section()
ctx._render_release_point_section()
ctx._render_hard_hit_section()
ctx._render_yoy_section()
ctx._render_tto_section()
ctx._render_appearances_section()
ctx._render_role_section()
```
After this refactor these become public free-function calls: `render_fastball_section(ctx)`, etc. No more cross-module private access.

### The 15 render methods (current `context.py`)

`_render_temporal_section`, `_render_executive_summary`, `_render_role_section`, `_render_fastball_section`, `_render_tto_section`, `_render_arsenal_section`, `_render_execution_section`, `_render_intermediates_section`, `_render_release_point_section`, `_render_pitch_shape_section`, `_render_hard_hit_section`, `_render_platoon_section`, `_render_first_pitch_section`, `_render_appearances_section`, `_render_yoy_section`.

Each becomes a free function with the same suffix but `render_` prefix and a `ctx: PitcherContext` first parameter. Inside each body, every `self.` becomes `ctx.`.

Special case: `_render_pitch_shape_section` is already a thin delegator — its body is `return render_pitch_shape(self.pitch_shape)` (calling `shape.render_pitch_shape`). It becomes `def render_pitch_shape_section(ctx): return render_pitch_shape(ctx.pitch_shape)`. Watch the name collision: `prompt_builder.py` imports `render_pitch_shape` from `shape.py`, and defines `render_pitch_shape_section` — distinct names, no clash.

### The `_MAX_PITCH_TYPES` constant

`context.py` defines `_MAX_PITCH_TYPES = 4` (used by both the render methods AND `assemble_pitcher_context`). After the split, **both** modules need it. Keep the canonical definition in `context.py` (assembly uses it), and import it into `prompt_builder.py`: `from pitcher_narratives.context import PitcherContext, _MAX_PITCH_TYPES`. This creates a one-way dependency `prompt_builder → context`, which is correct (the renderer depends on the model, never the reverse).

### Avoiding a circular import

`context.py` must NOT import `prompt_builder` at module top level, or you get a cycle (`prompt_builder` imports `context`). The `to_prompt()` delegator imports lazily inside the method body:
```python
def to_prompt(self) -> str:
    """Render as prompt-ready markdown under 2,000 tokens."""
    from pitcher_narratives.prompt_builder import build_pitcher_prompt
    return build_pitcher_prompt(self)
```

### Baseline test command

```bash
uv run pytest -q tests/test_context.py tests/test_pipeline.py
```
Record the pass/fail count at Task 0. As with the engine plan, the branch is not fully green — preserve the exact count, do not chase green. `test_pipeline.py` is included because Task 3 edits `pipeline.py`.

---

## Task 0: Capture the baseline

**Files:**
- None (verification only)

- [ ] **Step 1: Record the current pass/fail for the affected test files**

Run:
```bash
uv run pytest -q tests/test_context.py tests/test_pipeline.py 2>&1 | tail -3
```
Record the exact `N passed, M failed` line. This is the contract for the rest of the plan.

- [ ] **Step 2: Snapshot the rendered prompt for a known pitcher (golden output)**

Run:
```bash
uv run python -c "
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.context import assemble_pitcher_context
ctx = assemble_pitcher_context(load_pitcher_data(657277, 30))
open('/tmp/prompt_before.md','w').write(ctx.to_prompt())
print('bytes:', len(ctx.to_prompt()))
"
```
Expected: prints a byte count and writes `/tmp/prompt_before.md`. This golden file is your behavior oracle — the rendered output must be byte-identical after the refactor.

---

## Task 1: Create prompt_builder.py with all section renderers

**Files:**
- Create: `src/pitcher_narratives/prompt_builder.py`
- Test: reuse `tests/test_context.py` (no new test file; `to_prompt()` delegation keeps it valid)

- [ ] **Step 1: Create the module with header and the orchestrator**

Create `src/pitcher_narratives/prompt_builder.py`:

```python
"""Prompt rendering for PitcherContext.

Renders an assembled PitcherContext into prompt-ready markdown (under
~2,000 tokens). Split out of context.py so the PitcherContext model stays
a focused data container. Each `render_*_section` is a pure function of
the context; `build_pitcher_prompt` orchestrates them in display order.
"""

from __future__ import annotations

from pitcher_narratives.context import PitcherContext, _MAX_PITCH_TYPES
from pitcher_narratives.engine import TTOPitchType, TTOPlatoonSplit
from pitcher_narratives.shape import render_pitch_shape


def build_pitcher_prompt(ctx: PitcherContext) -> str:
    """Render the context as prompt-ready markdown under 2,000 tokens."""
    sections: list[str] = []
    sections.append(f"# {ctx.pitcher_name} ({ctx.throws}HP) -- Scouting Context")
    sections.append(render_temporal_section(ctx))
    sections.append(render_executive_summary(ctx))
    sections.append(render_role_section(ctx))
    sections.append(render_fastball_section(ctx))
    sections.append(render_tto_section(ctx))
    sections.append(render_arsenal_section(ctx))
    sections.append(render_execution_section(ctx))
    sections.append(render_intermediates_section(ctx))
    sections.append(render_release_point_section(ctx))
    sections.append(render_pitch_shape_section(ctx))
    sections.append(render_hard_hit_section(ctx))
    sections.append(render_platoon_section(ctx))
    sections.append(render_first_pitch_section(ctx))
    sections.append(render_appearances_section(ctx))
    sections.append(render_yoy_section(ctx))
    return "\n\n".join(s for s in sections if s)
```

> The title line (`# {name} ...`) was the first append inside the old `to_prompt()` — it stays here in `build_pitcher_prompt`, not in a `render_*` function. `TTOPitchType`/`TTOPlatoonSplit` are imported because `render_tto_section` declares them in local type hints (`dict[str, dict[int, TTOPitchType]]`); keep the import only if the moved body references them, else drop it (ruff will tell you).

- [ ] **Step 2: Move each render method body as a free function**

For each of the 15 methods, copy the body from `context.py` into `prompt_builder.py`, converting the signature and `self` references. Pattern (shown for one; repeat for all 15):

From `context.py`:
```python
    def _render_role_section(self) -> str:
        lines = ["## Role"]
        lines.append(f"- Most recent: {self.role}")
        wl = self.workload
        lines.append(f"- Appearances: {len(wl.appearances)}")
        if wl.max_consecutive_days >= 2:
            lines.append(f"- Max consecutive days: {wl.max_consecutive_days}")
        if wl.workload_concern:
            lines.append("- **Workload concern: 3+ consecutive days**")
        return "\n".join(lines)
```
To `prompt_builder.py`:
```python
def render_role_section(ctx: PitcherContext) -> str:
    lines = ["## Role"]
    lines.append(f"- Most recent: {ctx.role}")
    wl = ctx.workload
    lines.append(f"- Appearances: {len(wl.appearances)}")
    if wl.max_consecutive_days >= 2:
        lines.append(f"- Max consecutive days: {wl.max_consecutive_days}")
    if wl.workload_concern:
        lines.append("- **Workload concern: 3+ consecutive days**")
    return "\n".join(lines)
```

Do this for all 15: `render_temporal_section`, `render_executive_summary`, `render_role_section`, `render_fastball_section`, `render_tto_section`, `render_arsenal_section`, `render_execution_section`, `render_intermediates_section`, `render_release_point_section`, `render_pitch_shape_section`, `render_hard_hit_section`, `render_platoon_section`, `render_first_pitch_section`, `render_appearances_section`, `render_yoy_section`.

Notes per tricky body:
- `render_pitch_shape_section`: body is `return render_pitch_shape(ctx.pitch_shape)`.
- `render_intermediates_section`, `render_tto_section`: these define inner helper closures (`_pct`, `_rv`, `_delta_pct`, `_delta_rv` in intermediates) and local dict-building. Move them verbatim, only swapping `self.` → `ctx.`.
- Anything referencing `_MAX_PITCH_TYPES` (e.g. `ctx.arsenal[:_MAX_PITCH_TYPES]`) now resolves via the module-level import added in Step 1.

- [ ] **Step 3: Lint the new module (it will fail to import until Task 2 — that is expected here)**

Run:
```bash
uv run ruff check src/pitcher_narratives/prompt_builder.py
```
Expected: ruff reports style only (no syntax errors). Import-time correctness is verified in Task 2 after `context.py` is trimmed. Fix any unused-import or undefined-name findings now.

- [ ] **Step 4: Commit**

```bash
git add src/pitcher_narratives/prompt_builder.py
git commit -m "refactor(context): add prompt_builder with section render functions"
```

---

## Task 2: Trim context.py to model + assembly + delegating to_prompt

**Files:**
- Modify: `src/pitcher_narratives/context.py`

- [ ] **Step 1: Replace the 15 render methods and the old to_prompt body with a single delegator**

In `context.py`, delete all 15 `_render_*` methods and the old multi-line `to_prompt` body. Replace the `to_prompt` method with:

```python
    def to_prompt(self) -> str:
        """Render as prompt-ready markdown under 2,000 tokens.

        Delegates to prompt_builder; imported lazily to avoid a circular
        import (prompt_builder imports PitcherContext from this module).
        """
        from pitcher_narratives.prompt_builder import build_pitcher_prompt

        return build_pitcher_prompt(self)
```

Keep: the module docstring, the `_MAX_PITCH_TYPES` constant, the `PitcherContext` class fields, `to_prompt` (now the delegator), and `assemble_pitcher_context()`.

- [ ] **Step 2: Prune now-unused imports in context.py**

`context.py` imported many engine dataclasses purely for the field type annotations and the render bodies. The field annotations still need their types, but any import used ONLY by the deleted render methods is now dead. Run ruff to find them:

```bash
uv run ruff check src/pitcher_narratives/context.py
```
Remove every import ruff flags as unused (F401). Do NOT remove imports still referenced by the `PitcherContext` field annotations or by `assemble_pitcher_context()` — ruff distinguishes these correctly.

- [ ] **Step 3: Verify no render methods remain on the model**

Run:
```bash
grep -n "_render_" src/pitcher_narratives/context.py
```
Expected: no output.

- [ ] **Step 4: Run the context tests**

Run:
```bash
uv run pytest -q tests/test_context.py 2>&1 | tail -3
```
Expected: same pass/fail as Task 0 for this file. `to_prompt()` still works (now via delegation), so every `ctx.to_prompt()` assertion holds.

- [ ] **Step 5: Verify byte-identical rendered output against the golden file**

Run:
```bash
uv run python -c "
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.context import assemble_pitcher_context
ctx = assemble_pitcher_context(load_pitcher_data(657277, 30))
open('/tmp/prompt_after.md','w').write(ctx.to_prompt())
" && diff /tmp/prompt_before.md /tmp/prompt_after.md && echo "IDENTICAL"
```
Expected: `IDENTICAL` (diff prints nothing). If diff shows changes, a `self.`→`ctx.` substitution or an ordering change is wrong — fix before committing.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/context.py
git commit -m "refactor(context): reduce PitcherContext to data model with delegating to_prompt"
```

---

## Task 3: Repoint pipeline.py at the public render functions

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py`

- [ ] **Step 1: Add the prompt_builder import**

In `pipeline.py`, near the existing `from pitcher_narratives.context import PitcherContext` (line 68), add:
```python
from pitcher_narratives.prompt_builder import (
    render_appearances_section,
    render_arsenal_section,
    render_fastball_section,
    render_hard_hit_section,
    render_release_point_section,
    render_role_section,
    render_tto_section,
    render_yoy_section,
)
```

- [ ] **Step 2: Replace the eight private method calls**

In `_build_trend_input` (around lines 643–650) and `_build_game_shape_input` (around lines 694–697), replace each `ctx._render_X_section()` with the free-function form `render_X_section(ctx)`:

| Old | New |
|-----|-----|
| `ctx._render_fastball_section()` | `render_fastball_section(ctx)` |
| `ctx._render_arsenal_section()` | `render_arsenal_section(ctx)` |
| `ctx._render_release_point_section()` | `render_release_point_section(ctx)` |
| `ctx._render_hard_hit_section()` | `render_hard_hit_section(ctx)` |
| `ctx._render_yoy_section()` | `render_yoy_section(ctx)` |
| `ctx._render_tto_section()` | `render_tto_section(ctx)` |
| `ctx._render_appearances_section()` | `render_appearances_section(ctx)` |
| `ctx._render_role_section()` | `render_role_section(ctx)` |

- [ ] **Step 3: Confirm no private render access remains anywhere**

Run:
```bash
grep -rn "\._render_" src/pitcher_narratives/ | grep -v __pycache__
```
Expected: no output (all references now go through `prompt_builder` free functions).

- [ ] **Step 4: Lint and run the pipeline + context tests**

Run:
```bash
uv run ruff check src/pitcher_narratives/pipeline.py && \
uv run pytest -q tests/test_context.py tests/test_pipeline.py 2>&1 | tail -3
```
Expected: ruff clean; same pass/fail count as Task 0.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py
git commit -m "refactor(pipeline): use public prompt_builder renderers instead of private context methods"
```

---

## Task 4: Whole-package verification

**Files:**
- None (verification only)

- [ ] **Step 1: Import every consumer**

Run:
```bash
uv run python -c "import pitcher_narratives.context, pitcher_narratives.prompt_builder, pitcher_narratives.pipeline, pitcher_narratives.analyst, pitcher_narratives.bench.runner; print('OK')"
```
Expected: `OK` (proves no circular import).

- [ ] **Step 2: Confirm the dependency direction is one-way**

Run:
```bash
grep -n "import prompt_builder\|from pitcher_narratives.prompt_builder" src/pitcher_narratives/context.py
```
Expected: the ONLY match is the lazy import inside `to_prompt()` (indented, inside the method). No module-level import of `prompt_builder` in `context.py`.

- [ ] **Step 3: Confirm context.py shrank**

Run:
```bash
wc -l src/pitcher_narratives/context.py src/pitcher_narratives/prompt_builder.py
```
Expected: `context.py` ~150–170 lines; `prompt_builder.py` ~520–560 lines.

- [ ] **Step 4: Final byte-identical re-check and commit any cleanup**

Run:
```bash
uv run python -c "
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.context import assemble_pitcher_context
ctx = assemble_pitcher_context(load_pitcher_data(657277, 30))
open('/tmp/prompt_final.md','w').write(ctx.to_prompt())
" && diff /tmp/prompt_before.md /tmp/prompt_final.md && echo "IDENTICAL"
```
Expected: `IDENTICAL`.

---

## Self-Review Checklist

- [ ] `ctx.to_prompt()` returns byte-identical output to the Task 0 golden file.
- [ ] No `_render_` references remain in `src/` outside `prompt_builder.py`'s own function names.
- [ ] `context.py` has no module-level import of `prompt_builder` (lazy import inside `to_prompt` only).
- [ ] All 15 render methods exist as `render_*_section(ctx)` free functions in `prompt_builder.py`.
- [ ] `tests/test_context.py` and `tests/test_pipeline.py` match the Task 0 pass/fail count.
- [ ] `uv run ruff check src/pitcher_narratives/context.py src/pitcher_narratives/prompt_builder.py src/pitcher_narratives/pipeline.py` is clean.

## Out of scope

- Changing `to_prompt()`'s signature or removing it.
- Touching the engine modules (separate plan).
- Altering rendered markdown content (this is a pure move — output must not change).
