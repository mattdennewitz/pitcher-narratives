# Mode CHANGES two-frame engine (Phase 9B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Mode CHANGES a genuine recent-X-vs-prior-Y two-frame engine: assemble a PRIOR appearance-count frame, compute RECENT-vs-PRIOR deltas **in code**, feed them to the trends specialist, and expose `--prior` — so CHANGES narrates measured change across two windows instead of riding the single RECENT-vs-SEASON spine (9A).

**Architecture:** Additive and mode-gated. A new offset appearance slicer builds a PRIOR-frame `PitcherContext` via `dataclasses.replace(data, window_appearances=<prior slice>)`. A pure `frame_delta` module computes/renders the RECENT-vs-PRIOR delta block. `_build_trend_input` gains an optional `frame_comparison` block; `prior_ctx` threads down `run_narration_modes → generate_pipeline_streaming → _run_pipeline → run_analysis_spine → run_spine_tail → run_specialists`, applied **only** to the trends specialist and **only** for modes whose new `NarrationMode.temporal_frame` contains `PRIOR`. REPORT/RECAP pass `prior_ctx=None` and stay byte-identical. Per user decisions (2026-07-03): **trends-only** frame scope (game-shape stays in the run-once frame-agnostic core); **enrich-trends-input, ride `_run_pipeline`** (no `render_changes`/overlay).

**Tech Stack:** Python 3.14+, polars, pydantic / pydantic-ai, pytest.

## Global Constraints

- Python 3.14+ (`requires-python = ">=3.14"`); `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` module constants.
- Work ONLY in the worktree `/Users/matt/src/pitcher-narratives/.claude/worktrees/separate-narratives`. NEVER `cd` into the main checkout `/Users/matt/src/pitcher-narratives`.
- Data-dependent tests need the env prefix `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` (worktree lacks gitignored `var/` data). Without it ~25 `test_data.py`/context tests fail "Pitcher not found" (environmental, not real).
- Pre-existing known failure unrelated to this work: `test_to_prompt_token_budget` (Phase-4 vintage, 2063>2000). One failing test in a full-suite run is expected; all others pass.
- `report` (mode REPORT) and `recap` output stay **byte-identical** — this phase is purely additive and mode-gated on `PRIOR`. `run_narration_modes` dedupes by `mode.id`; do not change that.
- Appearance-count carry-forward invariant (Phase 6): a window below `_THIN_APPEARANCES` (10) renders every delta as the "Underpowered comparison" hedge. `TEST_PITCHER` (Cam Booser, id 592155) makes ≥10 appearances, so `--recent 10 --prior 10` yields a populated PRIOR frame in tests.
- Mode ids and contract ids are collision-free and unchanged. `temporal_frame` is a **new frozen-dataclass field with a default** (`frozenset({RECENT})`), appended per the `NarrationMode` docstring's reserved-field note — existing construction is unaffected.

---

## File Structure

- `src/pitcher_narratives/temporal.py` — MODIFY. Add `_DEFAULT_PRIOR_APPEARANCES = 10` next to `_DEFAULT_RECENT_APPEARANCES`; extend `__all__`. Leaf module, no cycles.
- `src/pitcher_narratives/data.py` — MODIFY. Add `filter_to_prior_appearances(df, recent_n, prior_m)` (offset slicer, sibling of `filter_to_recent_appearances`).
- `src/pitcher_narratives/context.py` — MODIFY. Add `assemble_prior_context(data, recent_n, prior_m) -> PitcherContext` (re-slices `window_appearances`, reuses `assemble_pitcher_context`).
- `src/pitcher_narratives/frame_delta.py` — CREATE. Pure `PitchFrameDelta` / `TrendFrameComparison` dataclasses + `build_trend_frame_comparison(recent, prior)` + `render_trend_frame_comparison(cmp)`. Imports `from .context import PitcherContext` (context does NOT import frame_delta → no cycle).
- `src/pitcher_narratives/personas.py` — MODIFY. Add `NarrationMode.temporal_frame: frozenset[TemporalFrame]` field (default `{RECENT}`); set `CHANGES` to `{RECENT, PRIOR}`; import `TemporalFrame`; extend `__all__` only if a new symbol is exported (it is not — `temporal_frame` is a field).
- `src/pitcher_narratives/pipeline.py` — MODIFY. `_build_trend_input(ctx, *, frame_comparison=None)`; thread `prior_ctx` through `run_specialists`, `run_spine_tail`, `run_analysis_spine`, `_run_pipeline`, `generate_pipeline_streaming`, `run_narration_modes` (gate on `PRIOR in mode.temporal_frame`).
- `src/pitcher_narratives/cli.py` — MODIFY. Add `--prior` to the `report` subcommand; when any selected mode needs `PRIOR`, build `prior_ctx = assemble_prior_context(...)` and pass to `run_narration_modes`.
- Tests: `tests/test_data.py`, `tests/test_context.py`, `tests/test_frame_delta.py` (new), `tests/test_pipeline.py`, `tests/test_personas.py`, `tests/test_cli.py`.

---

## Task 1: Offset appearance slicer (PRIOR window)

**Files:**
- Modify: `src/pitcher_narratives/data.py` (add after `filter_to_recent_appearances`, ~data.py:459)
- Test: `tests/test_data.py`

**Interfaces:**
- Produces: `filter_to_prior_appearances(df: pl.DataFrame, recent_n: int, prior_m: int) -> pl.DataFrame` — returns the rows of the `prior_m` distinct appearances immediately older than the `recent_n` most-recent ones (rank `[recent_n : recent_n + prior_m]` by `game_date` desc, `game_pk` desc). Empty when fewer than `recent_n` appearances exist.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_data.py` (uses `import polars as pl`; mirror the existing `filter_to_recent_appearances` tests):

```python
def _appearances(dates_pks):
    return pl.DataFrame(
        {"game_date": [d for d, _ in dates_pks], "game_pk": [p for _, p in dates_pks]}
    )


def test_filter_to_prior_appearances_selects_offset_window():
    df = _appearances([("2024-04-01", 1), ("2024-04-05", 2), ("2024-04-10", 3),
                       ("2024-04-15", 4), ("2024-04-20", 5)])
    out = filter_to_prior_appearances(df, recent_n=2, prior_m=2)
    # recent 2 = pks 5,4; prior 2 = pks 3,2
    assert sorted(out["game_pk"].to_list()) == [2, 3]


def test_filter_to_prior_appearances_empty_when_fewer_than_recent():
    df = _appearances([("2024-04-01", 1), ("2024-04-05", 2)])
    assert filter_to_prior_appearances(df, recent_n=5, prior_m=3).is_empty()


def test_filter_to_prior_appearances_partial_when_prior_runs_out():
    df = _appearances([("2024-04-01", 1), ("2024-04-05", 2), ("2024-04-10", 3)])
    out = filter_to_prior_appearances(df, recent_n=2, prior_m=5)
    assert out["game_pk"].to_list() == [1]  # only pk1 remains after recent 3,2


def test_filter_to_prior_appearances_empty_input():
    assert filter_to_prior_appearances(pl.DataFrame(), recent_n=1, prior_m=1).is_empty()
```

Ensure `filter_to_prior_appearances` is in the `from pitcher_narratives.data import (...)` block at the top of `tests/test_data.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py -k filter_to_prior -v`
Expected: FAIL / ImportError — `filter_to_prior_appearances` not defined.

- [ ] **Step 3: Implement the slicer**

Add to `src/pitcher_narratives/data.py` immediately after `filter_to_recent_appearances`:

```python
def filter_to_prior_appearances(
    df: pl.DataFrame, recent_n: int, prior_m: int
) -> pl.DataFrame:
    """Filter rows to the ``prior_m`` appearances immediately older than the
    ``recent_n`` most-recent ones.

    An appearance = unique ``(game_date, game_pk)`` pair. Keys are ranked
    most-recent ``game_date`` first, ``game_pk`` descending as tiebreak;
    this returns the rows of the keys ranked ``[recent_n, recent_n + prior_m)``.
    Returns an empty frame when fewer than ``recent_n`` appearances exist, and
    fewer than ``prior_m`` rows when the prior window runs past the season's
    oldest appearance. Works at any row granularity (appearance- or pitch-level).
    """
    if df.is_empty():
        return df
    prior_keys = (
        df.select("game_date", "game_pk")
        .unique()
        .sort(["game_date", "game_pk"], descending=True, nulls_last=True)
        .slice(recent_n, prior_m)
    )
    return df.join(prior_keys, on=["game_date", "game_pk"], how="inner")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py -k filter_to_prior -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/data.py tests/test_data.py
git commit -m "feat(data): offset appearance slicer for PRIOR frame (P9B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: PRIOR-frame context builder

**Files:**
- Modify: `src/pitcher_narratives/temporal.py` (add `_DEFAULT_PRIOR_APPEARANCES`)
- Modify: `src/pitcher_narratives/context.py` (add `assemble_prior_context`)
- Test: `tests/test_context.py`

**Interfaces:**
- Consumes: `filter_to_prior_appearances` (Task 1); `assemble_pitcher_context(data: PitcherData) -> PitcherContext` (existing, context.py:113); `PitcherData` dataclass (data.py:87).
- Produces: `_DEFAULT_PRIOR_APPEARANCES = 10` (temporal.py); `assemble_prior_context(data: PitcherData, recent_n: int, prior_m: int) -> PitcherContext` — a PitcherContext whose `window_*` metrics reflect the prior slice (engine derives window pitches from `data.statcast.filter(game_date.is_in(window_dates))`, so re-slicing `window_appearances` is sufficient and correct).

- [ ] **Step 1: Add the prior-window default constant**

In `src/pitcher_narratives/temporal.py`, after `_DEFAULT_RECENT_APPEARANCES = 10` add:

```python
_DEFAULT_PRIOR_APPEARANCES = 10
```

and extend `__all__` to `["TemporalFrame", "_DEFAULT_RECENT_APPEARANCES", "_DEFAULT_PRIOR_APPEARANCES"]`.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_context.py` (data-dependent; `TEST_PITCHER = 592155`, load via `load_pitcher_data`):

```python
def test_assemble_prior_context_differs_from_recent():
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context

    data = load_pitcher_data(592155, recent_appearances=5)
    recent = assemble_pitcher_context(data)
    prior = assemble_prior_context(data, recent_n=5, prior_m=5)
    # Both are fully-shaped PitcherContexts; the prior frame draws different
    # appearances, so at least the window pitch counts differ.
    assert isinstance(prior.arsenal, list)
    recent_counts = {p.pitch_name: p.n_pitches_window for p in recent.arsenal}
    prior_counts = {p.pitch_name: p.n_pitches_window for p in prior.arsenal}
    assert recent_counts != prior_counts


def test_assemble_prior_context_empty_prior_is_shaped():
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.context import assemble_prior_context

    data = load_pitcher_data(592155, recent_appearances=5)
    # recent_n far beyond available -> prior slice empty -> still a valid ctx
    prior = assemble_prior_context(data, recent_n=9999, prior_m=5)
    assert prior.pitcher_name  # shaped, no crash (empty-frame guards from Phase 5)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_context.py -k assemble_prior -v`
Expected: FAIL — `assemble_prior_context` not defined.

- [ ] **Step 4: Implement the builder**

In `src/pitcher_narratives/context.py`, add near `assemble_multi_frame_context`. Ensure imports at top: `import dataclasses` and `from .data import filter_to_prior_appearances` (context.py already imports `PitcherData` from `.data`).

```python
def assemble_prior_context(
    data: PitcherData, recent_n: int, prior_m: int
) -> PitcherContext:
    """Assemble a PitcherContext for the PRIOR appearance-count frame.

    Re-slices ``window_appearances`` to the ``prior_m`` appearances immediately
    older than the ``recent_n`` most-recent ones, leaving statcast and all
    baselines untouched. The engine derives window metrics by filtering
    ``data.statcast`` to the window's game dates, so replacing
    ``window_appearances`` is sufficient to retarget every ``window_*`` field.
    """
    prior_data = dataclasses.replace(
        data,
        window_appearances=filter_to_prior_appearances(
            data.appearances, recent_n, prior_m
        ),
    )
    return assemble_pitcher_context(prior_data)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_context.py -k assemble_prior -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/temporal.py src/pitcher_narratives/context.py tests/test_context.py
git commit -m "feat(context): assemble_prior_context for PRIOR appearance frame (P9B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Code-computed RECENT-vs-PRIOR trend comparison

**Files:**
- Create: `src/pitcher_narratives/frame_delta.py`
- Test: `tests/test_frame_delta.py`

**Interfaces:**
- Consumes: `PitcherContext.arsenal: list[PitchTypeSummary]` (context.py:79); `PitchTypeSummary` fields (arsenal.py:110-160): `pitch_name: str`, `window_velo: float`, `window_s_plus/l_plus/p_plus: float | None`, `window_usage_pct: float`, `n_pitches_window: int`; `_MIN_PITCHES` (engine/_common.py, =10).
- Produces: `PitchFrameDelta`, `TrendFrameComparison` (frozen dataclasses); `build_trend_frame_comparison(recent: PitcherContext, prior: PitcherContext) -> TrendFrameComparison`; `render_trend_frame_comparison(cmp: TrendFrameComparison) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_frame_delta.py`:

```python
from dataclasses import dataclass

from pitcher_narratives.frame_delta import (
    build_trend_frame_comparison,
    render_trend_frame_comparison,
)


@dataclass
class _PT:
    pitch_name: str
    window_velo: float
    window_s_plus: float | None
    window_l_plus: float | None
    window_usage_pct: float
    n_pitches_window: int


@dataclass
class _Ctx:
    arsenal: list


def _ctx(*pts):
    return _Ctx(arsenal=list(pts))


def test_build_comparison_computes_recent_minus_prior():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _ctx(_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40))
    cmp = build_trend_frame_comparison(recent, prior)
    d = cmp.deltas[0]
    assert d.pitch_name == "Four-Seam"
    assert d.velo_delta == 2.0
    assert d.s_plus_delta == 10.0
    assert d.usage_delta == 10.0
    assert d.sufficient is True
    assert cmp.prior_insufficient is False


def test_build_comparison_suppresses_below_sample_floor():
    recent = _ctx(_PT("Slider", 88.0, 100.0, 100.0, 30.0, 4))   # < 10 pitches
    prior = _ctx(_PT("Slider", 87.0, 95.0, 95.0, 25.0, 40))
    cmp = build_trend_frame_comparison(recent, prior)
    d = cmp.deltas[0]
    assert d.sufficient is False
    assert d.velo_delta is None


def test_build_comparison_flags_prior_insufficient_when_empty():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    cmp = build_trend_frame_comparison(recent, _ctx())
    assert cmp.prior_insufficient is True


def test_render_includes_signed_deltas_and_header():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _ctx(_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40))
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, prior))
    assert "Recent vs Prior Window" in text
    assert "velo +2.0 mph" in text
    assert "S+ +10" in text


def test_render_prior_insufficient_message():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, _ctx()))
    assert "insufficient" in text.lower()
```

(The test's `_PT`/`_Ctx` duck-type the real models — `build_trend_frame_comparison` only reads the listed attributes, keeping the unit test data-free.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_frame_delta.py -v`
Expected: FAIL — module `pitcher_narratives.frame_delta` not found.

- [ ] **Step 3: Implement the module**

Create `src/pitcher_narratives/frame_delta.py`:

```python
"""Code-computed RECENT-vs-PRIOR window deltas for the trends specialist.

Deltas are computed here (never by the LLM), consistent with the project's
"give the model deltas, not arithmetic" value. Consumed by CHANGES mode's
two-frame engine; imported by pipeline._build_trend_input.
"""

from __future__ import annotations

from dataclasses import dataclass

from .context import PitcherContext
from .engine._common import _MIN_PITCHES

__all__ = [
    "PitchFrameDelta",
    "TrendFrameComparison",
    "build_trend_frame_comparison",
    "render_trend_frame_comparison",
]

_HEADER = "## Recent vs Prior Window (code-computed deltas)"


@dataclass(frozen=True)
class PitchFrameDelta:
    pitch_name: str
    velo_delta: float | None
    s_plus_delta: float | None
    l_plus_delta: float | None
    usage_delta: float | None
    sufficient: bool


@dataclass(frozen=True)
class TrendFrameComparison:
    deltas: list[PitchFrameDelta]
    prior_insufficient: bool


def _opt_delta(a: float | None, b: float | None) -> float | None:
    return (a - b) if (a is not None and b is not None) else None


def build_trend_frame_comparison(
    recent: PitcherContext, prior: PitcherContext
) -> TrendFrameComparison:
    """Compute per-pitch recent-minus-prior deltas, matched by pitch name.

    A delta is suppressed (``sufficient=False``, fields ``None``) when either
    frame has fewer than ``_MIN_PITCHES`` window pitches for that pitch type,
    or the pitch is absent from the prior frame. The prior frame is flagged
    insufficient when it has no arsenal or no pitch clears the sample floor.
    """
    prior_by_name = {p.pitch_name: p for p in prior.arsenal}
    deltas: list[PitchFrameDelta] = []
    for r in recent.arsenal:
        p = prior_by_name.get(r.pitch_name)
        suff = (
            p is not None
            and r.n_pitches_window >= _MIN_PITCHES
            and p.n_pitches_window >= _MIN_PITCHES
        )
        deltas.append(
            PitchFrameDelta(
                pitch_name=r.pitch_name,
                velo_delta=(r.window_velo - p.window_velo) if suff else None,
                s_plus_delta=_opt_delta(r.window_s_plus, p.window_s_plus) if suff else None,
                l_plus_delta=_opt_delta(r.window_l_plus, p.window_l_plus) if suff else None,
                usage_delta=(r.window_usage_pct - p.window_usage_pct) if suff else None,
                sufficient=suff,
            )
        )
    prior_insufficient = not prior.arsenal or all(not d.sufficient for d in deltas)
    return TrendFrameComparison(deltas=deltas, prior_insufficient=prior_insufficient)


def render_trend_frame_comparison(cmp: TrendFrameComparison) -> str:
    """Render the comparison as a markdown block for the trends specialist."""
    if cmp.prior_insufficient:
        return (
            f"{_HEADER}\n\n"
            "Prior window insufficient for comparison (too few prior "
            "appearances). Report recent-window findings without a prior "
            "contrast; do not invent a change."
        )
    lines = [
        _HEADER,
        "",
        "Deltas are recent minus prior; positive = higher in the recent window.",
        "",
    ]
    for d in cmp.deltas:
        if not d.sufficient:
            lines.append(f"- {d.pitch_name}: insufficient sample for a recent-vs-prior delta")
            continue
        parts: list[str] = []
        if d.velo_delta is not None:
            parts.append(f"velo {d.velo_delta:+.1f} mph")
        if d.s_plus_delta is not None:
            parts.append(f"S+ {d.s_plus_delta:+.0f}")
        if d.l_plus_delta is not None:
            parts.append(f"L+ {d.l_plus_delta:+.0f}")
        if d.usage_delta is not None:
            parts.append(f"usage {d.usage_delta:+.1f} pts")
        lines.append(f"- {d.pitch_name}: {', '.join(parts) if parts else 'no meaningful change'}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_frame_delta.py -v`
Expected: 5 passed.

- [ ] **Step 5: Verify no import cycle**

Run: `uv run python -c "import pitcher_narratives.frame_delta; import pitcher_narratives.pipeline; print('ok')"`
Expected: `ok` (context does not import frame_delta).

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/frame_delta.py tests/test_frame_delta.py
git commit -m "feat(frame-delta): code-computed RECENT-vs-PRIOR trend comparison (P9B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `_build_trend_input` accepts a frame-comparison block

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:727-751` (`_build_trend_input`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `_build_trend_input(ctx: PitcherContext, *, frame_comparison: str | None = None) -> UserPrompt` — appends `frame_comparison` to the data sections when non-None; identical output to today when `None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py` (import `_build_trend_input` from `pitcher_narratives.pipeline`; reuse the existing PitcherContext fixture — find how sibling `_build_*_input` tests obtain a `ctx`, e.g. a `sample_context`/loaded fixture):

```python
def test_build_trend_input_default_omits_comparison(sample_context):
    prompt = _build_trend_input(sample_context)
    joined = "".join(s for s in prompt if isinstance(s, str))
    assert "Recent vs Prior Window" not in joined


def test_build_trend_input_appends_frame_comparison(sample_context):
    block = "## Recent vs Prior Window (code-computed deltas)\n\n- Four-Seam: velo +2.0 mph"
    prompt = _build_trend_input(sample_context, frame_comparison=block)
    joined = "".join(s for s in prompt if isinstance(s, str))
    assert "Recent vs Prior Window" in joined
    assert "velo +2.0 mph" in joined
```

(If no `sample_context` fixture exists, use the data-dependent pattern the neighboring trend-input test uses — `load_pitcher_data(592155, recent_appearances=10)` → `assemble_pitcher_context`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_pipeline.py -k build_trend_input -v`
Expected: FAIL — unexpected keyword `frame_comparison`.

- [ ] **Step 3: Modify `_build_trend_input`**

In `src/pitcher_narratives/pipeline.py`, change the signature and append the block. The current body (727-751) builds `data_sections`; add the comparison to it:

```python
def _build_trend_input(
    ctx: PitcherContext, *, frame_comparison: str | None = None
) -> UserPrompt:
    baselines = render_league_baselines(_pitch_types(ctx))
    prefix_sections = [
        f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
        baselines,
    ]
    data_sections = [
        render_fastball_section(ctx),
        render_arsenal_section(ctx),
        render_release_point_section(ctx),
        render_hard_hit_section(ctx),
    ]
    if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
        data_sections.append(render_yoy_section(ctx))
    if frame_comparison is not None:
        data_sections.append(frame_comparison)
    return [
        "\n\n".join(s for s in prefix_sections if s),
        CachePoint(),
        "\n\n".join(s for s in data_sections if s),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_pipeline.py -k build_trend_input -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): _build_trend_input accepts optional frame_comparison (P9B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `NarrationMode.temporal_frame` field + CHANGES wiring

**Files:**
- Modify: `src/pitcher_narratives/personas.py` (NarrationMode dataclass ~461-482; CHANGES ~515-525; imports)
- Test: `tests/test_personas.py`

**Interfaces:**
- Produces: `NarrationMode.temporal_frame: frozenset[TemporalFrame]` (default `frozenset({TemporalFrame.RECENT})`); `CHANGES.temporal_frame == frozenset({TemporalFrame.RECENT, TemporalFrame.PRIOR})`; `REPORT`/`RECAP` retain the default.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_personas.py` (import `TemporalFrame` from `pitcher_narratives.temporal`, and `REPORT, RECAP, CHANGES` already imported):

```python
def test_report_and_recap_are_single_frame():
    from pitcher_narratives.temporal import TemporalFrame
    assert REPORT.temporal_frame == frozenset({TemporalFrame.RECENT})
    assert RECAP.temporal_frame == frozenset({TemporalFrame.RECENT})


def test_changes_declares_recent_and_prior_frames():
    from pitcher_narratives.temporal import TemporalFrame
    assert CHANGES.temporal_frame == frozenset(
        {TemporalFrame.RECENT, TemporalFrame.PRIOR}
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_personas.py -k temporal_frame -v`
Expected: FAIL — `NarrationMode` has no attribute `temporal_frame`.

- [ ] **Step 3: Add the field and wire CHANGES**

In `src/pitcher_narratives/personas.py`:
1. Add import near the other imports: `from .temporal import TemporalFrame`.
2. Extend the `NarrationMode` dataclass (append after `validation`, preserving the `__post_init__`):

```python
@dataclass(frozen=True)
class NarrationMode:
    id: str
    contracts: Mapping[str, OutputContract]
    validation: ValidationPolicy = ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    )
    temporal_frame: frozenset[TemporalFrame] = frozenset({TemporalFrame.RECENT})

    def __post_init__(self) -> None:
        object.__setattr__(self, "contracts", MappingProxyType(dict(self.contracts)))
```

3. In the `CHANGES = NarrationMode(...)` definition (~515-525), add the field:

```python
CHANGES = NarrationMode(
    id="changes",
    contracts={
        "scout": CHANGES_SCOUT,
        "analyst": CHANGES_ANALYST,
        "generic": CHANGES_GENERIC,
    },
    validation=ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    ),
    temporal_frame=frozenset({TemporalFrame.RECENT, TemporalFrame.PRIOR}),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_personas.py -k "temporal_frame or changes" -v`
Expected: new tests pass; existing CHANGES/writer-prompt goldens still pass (the writer system prompt is unchanged — `temporal_frame` never enters `build_writer_system_prompt`).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/personas.py tests/test_personas.py
git commit -m "feat(personas): NarrationMode.temporal_frame; CHANGES = RECENT+PRIOR (P9B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Thread `prior_ctx` through the spine to the trends specialist

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — `run_specialists` (1371-1414), `run_spine_tail` (1470-1524), `run_analysis_spine` (1527-1560), `_run_pipeline` (1987-2068), `generate_pipeline_streaming` (2071-2102), `run_narration_modes` (2105-2144)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `build_trend_frame_comparison`, `render_trend_frame_comparison` (Task 3); `_build_trend_input(..., frame_comparison=)` (Task 4); `NarrationMode.temporal_frame` (Task 5); `TemporalFrame.PRIOR`.
- Produces: an optional `prior_ctx: PitcherContext | None = None` kwarg on each of the six functions above. When `prior_ctx` is not None, the trends specialist input carries the rendered RECENT-vs-PRIOR block; otherwise behavior is byte-identical to today. `run_narration_modes` supplies `prior_ctx` to a mode **only** when `TemporalFrame.PRIOR in mode.temporal_frame`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`. This asserts the wiring: with a `prior_ctx`, the trends specialist receives the comparison block. Use a spy that captures the trends prompt (mirror how existing spine tests stub agents / capture inputs). Sketch:

```python
@pytest.mark.asyncio
async def test_run_spine_tail_injects_frame_comparison(sample_context, prior_context, spine_agents):
    captured = {}

    class _CaptureTrends:
        async def run(self, *a, **k):
            captured["prompt"] = k.get("user_prompt") or (a[0] if a else None)
            return _FakeResult(output="trends text")

    agents = spine_agents(trends=_CaptureTrends())
    core = CoreContext(stuff="s", location="l", runvalue="r", game_shape="g")
    await run_spine_tail(core, sample_context, agents=agents, prior_ctx=prior_context)
    joined = "".join(x for x in captured["prompt"] if isinstance(x, str))
    assert "Recent vs Prior Window" in joined
```

Match the actual agent-stub + fixture patterns already in `tests/test_pipeline.py` (there are existing tail/spine tests with fake agents — reuse their `_FakeResult`/`agent_kwargs` conventions; `prior_context` = `assemble_prior_context(load_pitcher_data(592155, 10), 10, 10)`). Also add a negative test: `run_spine_tail(..., prior_ctx=None)` produces a trends prompt WITHOUT the header (byte-identical path).

- [ ] **Step 2: Run test to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_pipeline.py -k frame_comparison -v`
Expected: FAIL — `run_spine_tail` has no `prior_ctx` kwarg.

- [ ] **Step 3: Wire `run_specialists`**

Add a keyword-only param and use it for the trends builder only:

```python
async def run_specialists(
    stuff_agent, location_agent, runvalue_agent, trends_agent, game_shape_agent,
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    names: list[str] | None = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
    trend_frame_comparison: str | None = None,
) -> SpecialistOutputs:
    ...
    all_inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (trends_agent, _build_trend_input(ctx, frame_comparison=trend_frame_comparison)),
        "game_shape": (game_shape_agent, _build_game_shape_input(ctx)),
    }
    ...  # unchanged
```

- [ ] **Step 4: Wire `run_spine_tail`**

Add `prior_ctx: PitcherContext | None = None` (keyword-only). Compute the comparison and pass it to `run_specialists`. Add imports at top of pipeline.py: `from .frame_delta import build_trend_frame_comparison, render_trend_frame_comparison`.

```python
async def run_spine_tail(
    core: CoreContext,
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    prior_ctx: PitcherContext | None = None,
) -> AnalyzedContext:
    ...
    trend_frame_comparison = (
        render_trend_frame_comparison(build_trend_frame_comparison(ctx, prior_ctx))
        if prior_ctx is not None
        else None
    )
    # in the existing run_specialists(...) call for _TAIL_SPECIALISTS, pass:
    #   trend_frame_comparison=trend_frame_comparison
```

Locate the `run_specialists(...)` call inside `run_spine_tail` (it runs `names=_TAIL_SPECIALISTS`) and add the `trend_frame_comparison=trend_frame_comparison` kwarg. Leave everything else (merge into SpecialistOutputs, audit/revise, signal extraction) unchanged.

- [ ] **Step 5: Wire `run_analysis_spine`, `_run_pipeline`, `generate_pipeline_streaming`**

Add `prior_ctx: PitcherContext | None = None` (keyword-only) to each and forward:
- `run_analysis_spine(...)` → pass `prior_ctx=prior_ctx` to its `run_spine_tail(...)` call (leave `run_spine_core` untouched — core is frame-agnostic).
- `_run_pipeline(...)` → pass `prior_ctx=prior_ctx` to its `run_analysis_spine(...)` call.
- `generate_pipeline_streaming(...)` → pass `prior_ctx=prior_ctx` into the `asyncio.run(_run_pipeline(...))` call.

- [ ] **Step 6: Wire `run_narration_modes` (mode-gated)**

Add `prior_ctx: PitcherContext | None = None` (keyword-only). In the per-mode loop, gate it. Import `TemporalFrame` at top of pipeline.py (`from .temporal import TemporalFrame`).

```python
def run_narration_modes(
    ctx: PitcherContext,
    *,
    modes: list[NarrationMode] | None = None,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    _model_override: Any = None,
    prior_ctx: PitcherContext | None = None,
) -> dict[str, PipelineResult]:
    ...
    # inside the deduped per-mode loop, when calling generate_pipeline_streaming:
    mode_prior = prior_ctx if TemporalFrame.PRIOR in mode.temporal_frame else None
    result = generate_pipeline_streaming(
        ctx, provider=provider, thinking=thinking, persona=persona,
        mode=mode, _model_override=_model_override, prior_ctx=mode_prior,
    )
```

- [ ] **Step 7: Run the wiring tests + the byte-identity guard**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest \
  tests/test_pipeline.py -k "frame_comparison or spine or narration_modes" -v
```
Expected: new tests pass; existing single-frame spine tests (REPORT path, `prior_ctx=None`) unchanged.

- [ ] **Step 8: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): thread prior_ctx to trends specialist, PRIOR-gated per mode (P9B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: `--prior` CLI flag + build `prior_ctx` end-to-end

**Files:**
- Modify: `src/pitcher_narratives/cli.py` — `report` subcommand args (~35-88); the report command body (~389-421)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `assemble_prior_context` (Task 2); `_DEFAULT_PRIOR_APPEARANCES` (Task 2); `run_narration_modes(..., prior_ctx=)` (Task 6); `NarrationMode.temporal_frame` / `TemporalFrame.PRIOR`.
- Produces: `report --prior N` flag; `prior_ctx` built and passed to `run_narration_modes` **only** when a selected mode needs PRIOR.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (uses `PITCHER_NARRATIVES_TEST_MODEL`; mirror `test_cli_changes_mode_runs_and_produces_output`):

```python
def test_report_subcommand_accepts_prior_flag():
    args = parse_args(["report", "-p", "592155", "--mode", "changes", "--prior", "8"])
    assert args.prior == 8


def test_report_prior_defaults():
    args = parse_args(["report", "-p", "592155", "--mode", "changes"])
    assert args.prior == 10  # _DEFAULT_PRIOR_APPEARANCES


@pytest.mark.usefixtures("test_model_env")  # or the existing TestModel fixture
def test_cli_changes_two_frame_runs(capsys):
    # runs CHANGES with --prior; asserts it completes and emits a CHANGES section
    exit_code = main(["report", "-p", "592155", "--mode", "changes",
                      "--recent", "10", "--prior", "10"])
    out = capsys.readouterr().out
    assert exit_code in (0, 1)  # 1 only if TestModel triggers residual banner
    assert "Scouting Report" in out
```

Match the exact `parse_args`/`main` entry names and TestModel fixture already used by neighboring CLI tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py -k "prior or two_frame" -v`
Expected: FAIL — unrecognized argument `--prior`.

- [ ] **Step 3: Add the `--prior` argument**

In `cli.py`, in the `report` subcommand setup (next to `-n/--recent`, ~39-45). Import `_DEFAULT_PRIOR_APPEARANCES` from `.temporal`:

```python
report.add_argument(
    "--prior",
    type=int,
    default=_DEFAULT_PRIOR_APPEARANCES,
    help=(
        "Prior-window size in appearances for CHANGES mode's recent-vs-prior "
        f"comparison (default: {_DEFAULT_PRIOR_APPEARANCES}). Ignored by "
        "report/recap modes."
    ),
)
```

Also update the `--mode` help string (~81-88) is already accurate (lists `changes`); no change needed there.

- [ ] **Step 4: Build and pass `prior_ctx`**

In the report command body (~389-421), after `selected_modes = _resolve_modes(...)`, build the prior context only when needed. Import `assemble_prior_context` from `.context` and `TemporalFrame` from `.temporal`:

```python
ctx = assemble_pitcher_context(pitcher_data)
selected_modes = _resolve_modes(getattr(args, "mode", None))

needs_prior = any(
    TemporalFrame.PRIOR in m.temporal_frame for m in selected_modes
)
prior_ctx = (
    assemble_prior_context(pitcher_data, args.recent, args.prior)
    if needs_prior
    else None
)
...
results = run_narration_modes(
    ctx,
    modes=selected_modes,
    provider=args.provider,
    thinking=args.thinking,
    persona=args.persona,
    _model_override=model_override,
    prior_ctx=prior_ctx,
)
```

(`--print-prompts` path: since it renders through the same `run_narration_modes`/pipeline input assembly, the CHANGES trends prompt will now include the comparison block for free when `--mode changes --prior N` is given. No extra change required unless `--print-prompts` short-circuits before `run_narration_modes` — if so, thread `prior_ctx` into that print path the same way.)

- [ ] **Step 5: Run the CLI tests**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py -k "prior or two_frame or changes or report or recap" -v`
Expected: new tests pass; REPORT/RECAP CLI tests unchanged (they never build `prior_ctx`).

- [ ] **Step 6: Byte-identity sanity check (REPORT unchanged)**

Run the existing REPORT byte-identity / section tests:
`PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py tests/test_pipeline.py -k "report" -v`
Expected: all pass — no REPORT output drift.

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat(cli): --prior flag; build prior_ctx for CHANGES two-frame engine (P9B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Golden for the trend comparison block + full-suite wrap-up

**Files:**
- Create: `tests/fixtures/changes_trend_comparison.txt` (golden of the rendered block for the canonical pitcher/window)
- Test: `tests/test_frame_delta.py` (or `tests/test_pipeline.py`) — golden assertion
- Modify: `.superpowers/sdd/progress.md` (append Phase 9B section)

**Interfaces:** none new — this task locks output and verifies the whole increment.

- [ ] **Step 1: Write a golden test for the rendered block**

Add a data-dependent golden test that pins the exact rendered comparison for `592155`, `--recent 10 --prior 10`:

```python
def test_changes_trend_comparison_golden():
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context
    from pitcher_narratives.frame_delta import (
        build_trend_frame_comparison, render_trend_frame_comparison,
    )

    data = load_pitcher_data(592155, recent_appearances=10)
    recent = assemble_pitcher_context(data)
    prior = assemble_prior_context(data, recent_n=10, prior_m=10)
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, prior))
    golden = (Path(__file__).parent / "fixtures" / "changes_trend_comparison.txt").read_text()
    assert text == golden
```

- [ ] **Step 2: Generate the golden**

Run a one-off to produce the file (generate-and-verify, not hand-authored):

```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -c "
from pathlib import Path
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context
from pitcher_narratives.frame_delta import build_trend_frame_comparison, render_trend_frame_comparison
d = load_pitcher_data(592155, recent_appearances=10)
t = render_trend_frame_comparison(build_trend_frame_comparison(
    assemble_pitcher_context(d), assemble_prior_context(d, 10, 10)))
Path('tests/fixtures/changes_trend_comparison.txt').write_text(t)
print(t)
"
```

Read the printed block; confirm it is a sane recent-vs-prior delta list (or the "insufficient" message if 592155's prior-10 window is thin — either is a valid pinned golden, but note which in the commit).

- [ ] **Step 3: Run the golden test**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_frame_delta.py -k golden -v`
Expected: PASS.

- [ ] **Step 4: Full suite + grep-clean**

```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q
```
Expected: all pass except the single pre-existing `test_to_prompt_token_budget`.

Grep-clean checks:
```bash
grep -rn "prior_ctx\|temporal_frame\|filter_to_prior\|frame_comparison\|assemble_prior_context" src/pitcher_narratives | wc -l   # non-zero, wired
grep -rn "render_changes\|two_frame_overlay" src/pitcher_narratives   # expect ZERO (no non-standard render, per decision)
```

- [ ] **Step 5: Append the progress ledger**

Add a `## Phase 9B: Mode CHANGES two-frame engine` section to `.superpowers/sdd/progress.md`: base commit, the 7 impl commits, the two user decisions (trends-only scope; enrich-trends-input/no render_changes), the byte-identity guarantee for REPORT/RECAP, the PRIOR-frame = `dataclasses.replace(window_appearances)` mechanism, and note that Phase 10 (bench + per-mode goldens) and Phase 11 (depth/span calibration) remain.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/changes_trend_comparison.txt tests/test_frame_delta.py .superpowers/sdd/progress.md
git commit -m "test(frame-delta): golden trend-comparison block; P9B wrap-up

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (design §5/§6 CHANGES row, split-scope 9B — the slice deferred by 9A):**
- "recent-X-vs-prior-Y two-frame engine" → Tasks 1–2 (offset slicer + PRIOR-frame `PitcherContext`).
- "appearance-count slicer selecting last N appearances… PRIOR-frame assembly" → Task 1 (`filter_to_prior_appearances`) + Task 2 (`assemble_prior_context`).
- "Deltas between frames computed in code (engine), never by LLM" → Task 3 (`build_trend_frame_comparison`, pure).
- "trends receive multi-frame block; keeps specialist input from ballooning" → Tasks 3–4, **trends only** (user decision; game-shape stays frame-agnostic in the run-once core, consistent with §3's within-game clarification).
- "`--recent`/`--prior`" → `--recent` exists (Phase 6); Task 7 adds `--prior`.
- "`NarrationMode` frame selector (design §4, deferred by Phase 4 docstring)" → Task 5 (`temporal_frame`).
- Frame sufficiency surfaced never silent (§15): empty/thin PRIOR → `prior_insufficient` message; per-pitch sub-floor → "insufficient sample" (Task 3), reusing `_MIN_PITCHES`.
- REPORT/RECAP byte-identical (§ Global Constraints): `prior_ctx=None` default everywhere; `run_narration_modes` gates on `PRIOR in mode.temporal_frame`; `_build_trend_input` default omits the block.
- **Explicitly out of scope (later phases, per design §13):** `render_changes`/overlay (user decision: not needed — enrich-trends path); game-shape multi-frame (trends-only decision); per-mode bench + golden combinatorics (Phase 10); RECAP/CHANGES depth + span calibration (Phase 11); populating PRIOR inside `MultiFrameContext` / an `input_assembler` member (not required by the enrich-trends path — `prior_ctx` threads directly).

**Placeholder scan:** No TBD/"handle edge cases"/"similar to Task N". Every code step shows real bodies. The golden (Task 8) is generated by a concrete command, not hand-authored. Two spots say "match the existing fixture/stub pattern in the neighboring test" (Task 4 `sample_context`, Task 6 agent spy, Task 7 `parse_args`/`main`/TestModel names) — these reference concrete existing tests the implementer must read, not invent; the assertions themselves are fully specified.

**Type consistency:** `filter_to_prior_appearances(df, recent_n, prior_m)`, `assemble_prior_context(data, recent_n, prior_m)`, `build_trend_frame_comparison(recent, prior)` → `TrendFrameComparison`, `render_trend_frame_comparison(cmp)` → `str`, `_build_trend_input(ctx, *, frame_comparison)`, `run_specialists(..., trend_frame_comparison=)`, and `prior_ctx` (all spine fns) are used identically across tasks. `temporal_frame` is `frozenset[TemporalFrame]` everywhere. Delta field names (`velo_delta`, `s_plus_delta`, `l_plus_delta`, `usage_delta`, `sufficient`, `prior_insufficient`) match between Task 3's dataclass, its tests, and the renderer.

**Doubleheader note (pre-existing, not fixed here):** the engine derives window pitches via `game_date.is_in(window_dates)`, so two `game_pk` on one date both fall in a frame even if the slicer (which ranks by `(game_date, game_pk)`) split them. This imprecision predates 9B and affects RECENT identically; out of scope.
