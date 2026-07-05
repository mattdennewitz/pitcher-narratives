# Frame Sufficiency & Determinism Guards (Phase 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the analysis engine robust to empty, tiny, and doubleheader-ambiguous frames so it is safe for the appearance-count window model landing in phase 6.

**Architecture:** Five guards from design §15 (G2, G5, G6, G7, G8). G5 adds a `game_pk` secondary sort key to every "most-recent-appearance" pick (determinism). G2 stops `compute_fastball_summary` crashing on an empty window and marks the frame empty. G6 suppresses fastball delta strings below the pitch-count floor instead of only flagging them. G7 makes `outlier_tag` N-aware and suppresses the OUTLIER tag below the floor. G8 replaces the day-window-shaped `_is_cold_start` boolean with a three-state `frame_sufficiency` gate (`sufficient | thin | empty`) whose result is surfaced in the rendered output, never silent.

**Tech Stack:** Python 3.14, polars, pytest. No new dependencies.

## Global Constraints

- Python `>=3.14`; run everything through `uv run` (venv at `.venv/`).
- Tests read the real data tree. **Every pytest command in this plan must be prefixed** `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` (the data lives in the main checkout, not the worktree).
- Work **only** inside the worktree `/Users/matt/src/pitcher-narratives/.claude/worktrees/separate-narratives`. Never `cd` into `/Users/matt/src/pitcher-narratives` (the data dir); a prior phase-4 subagent committed to `main` by confusing the two. Set the data dir inline per command as above.
- Branch: `feat/mode-based-narration`. Do not push; the branch continues to phase 6.
- `snake_case` functions/vars, `UPPER_SNAKE_CASE` constants, `PascalCase` classes; module-private helpers prefixed `_`. Google-style docstrings, type hints on all signatures.
- The window model is still **day-windows** this phase (the appearance-count swap is phase 6). These guards are prerequisites for that swap.
- **This phase is NOT byte-for-byte behavior-preserving** (unlike phases 3–4). G6/G7/G8 intentionally change rendered output in small-sample situations. Golden/characterization fixtures that exercise a thin frame are expected to change; each task recalibrates the goldens it touches and records the diff.
- Test constant `TEST_PITCHER = 592155` (Cam Booser) is already defined per test file. Construct empty/thin frames with `dataclasses.replace(data, window_appearances=...)` — do not fabricate parquet.
- SDD ledger: append task progress to `.superpowers/sdd/progress.md` under a new `## Phase 5` heading.

---

## File Structure

| File | Responsibility in this phase |
|------|------------------------------|
| `src/pitcher_narratives/engine/_common.py` | Add `_most_recent_row` deterministic picker (G5), `frame_sufficiency` + `FrameSufficiency` + render-string constants (G8); update `_pplus_delta_strings` to take sufficiency; keep `_MIN_PITCHES`. |
| `src/pitcher_narratives/engine/baselines.py` | `outlier_tag` gains an `n` parameter; suppresses OUTLIER below `_MIN_PITCHES` (G7). |
| `src/pitcher_narratives/engine/arsenal.py` | Empty-frame guard + `window_empty` field on `FastballSummary` (G2); delta suppression below floor (G6); migrate `.row(0)` sorts and `_is_cold_start` calls to the new helpers (G5/G8). |
| `src/pitcher_narratives/engine/contact.py`, `execution.py`, `mechanics.py` | Migrate `_is_cold_start` call sites to `frame_sufficiency` (G8). |
| `src/pitcher_narratives/context.py` | Migrate the `.row(0)` role pick to `_most_recent_row` (G5). |
| `src/pitcher_narratives/pipeline.py` | Pass `n_pitches_window` into `outlier_tag` at the three call sites (G7). |
| `src/pitcher_narratives/prompt_builder.py` | Render "no data for this frame" when `window_empty` (G2); render a hedge line when the frame is `thin`/`empty` (G8). |
| `tests/test_engine.py`, `tests/test_context.py`, `tests/test_pipeline.py` | New unit tests per guard; recalibrate affected assertions. |

## Task ordering rationale

G5 first (pure determinism, smallest blast radius, unblocks nothing but is safest to land). Then G7 (pure function, directly unit-testable). Then G2 (localized to fastball summary). Then G6 (builds on G2's frame awareness). G8 last (largest: touches 6 files and the render layer).

---

## Task 1: G5 — deterministic most-recent-appearance picker

**Files:**
- Modify: `src/pitcher_narratives/engine/_common.py` (add `_most_recent_row`)
- Modify: `src/pitcher_narratives/engine/arsenal.py:436`
- Modify: `src/pitcher_narratives/context.py:139`
- Test: `tests/test_engine.py`

**Interfaces:**
- Produces: `_most_recent_row(appearances: pl.DataFrame) -> dict[str, Any]` — sorts by `game_date` then `game_pk` (both descending, `nulls_last=True`) and returns row 0 as a named dict. Raises `IndexError` on empty input (same as today's `.row(0)`).

Rationale: today two sites do `data.appearances.sort("game_date", descending=True).row(0, named=True)`. On a doubleheader (two `game_pk` on one `game_date`) "most recent" is non-deterministic. The `game_pk` tiebreak mirrors the established `sort_by(..., maintain_order=True, nulls_last=True)` pattern at `data.py:350`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine.py` (import `polars as pl` and `dataclasses` are already present; add `from pitcher_narratives.engine._common import _most_recent_row`):

```python
def test_most_recent_row_breaks_doubleheader_ties_by_game_pk():
    # Two appearances on the same date (a doubleheader): higher game_pk wins.
    appearances = pl.DataFrame(
        {
            "game_date": ["2024-05-01", "2024-05-01", "2024-04-15"],
            "game_pk": [745002, 745001, 744000],
            "role": ["RP", "RP", "RP"],
        }
    )
    row = _most_recent_row(appearances)
    assert row["game_pk"] == 745002


def test_most_recent_row_picks_latest_date():
    appearances = pl.DataFrame(
        {
            "game_date": ["2024-04-15", "2024-05-01"],
            "game_pk": [744000, 745001],
            "role": ["RP", "SP"],
        }
    )
    row = _most_recent_row(appearances)
    assert row["game_date"] == "2024-05-01"
    assert row["role"] == "SP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py::test_most_recent_row_breaks_doubleheader_ties_by_game_pk tests/test_engine.py::test_most_recent_row_picks_latest_date -v`
Expected: FAIL — `ImportError`/`cannot import name '_most_recent_row'`.

- [ ] **Step 3: Add the helper**

In `src/pitcher_narratives/engine/_common.py`, near `_get_window_game_dates` (it already imports `Any` and `pl`):

```python
def _most_recent_row(appearances: pl.DataFrame) -> dict[str, Any]:
    """Return the most-recent appearance as a named dict, deterministically.

    Sorts by ``game_date`` then ``game_pk`` (both descending) so doubleheaders
    (two ``game_pk`` on one date) resolve to a single stable "most recent" pick.

    Args:
        appearances: Per-appearance DataFrame with ``game_date`` and ``game_pk``.

    Returns:
        Row 0 after the deterministic sort, as a column->value dict.
    """
    return (
        appearances.sort(
            ["game_date", "game_pk"], descending=True, nulls_last=True
        ).row(0, named=True)
    )
```

- [ ] **Step 4: Migrate the two call sites**

`src/pitcher_narratives/engine/arsenal.py:435-436` — replace:
```python
    # Find most recent appearance
    recent = data.appearances.sort("game_date", descending=True).row(0, named=True)
```
with:
```python
    # Find most recent appearance (deterministic doubleheader tiebreak)
    recent = _most_recent_row(data.appearances)
```
Ensure `_most_recent_row` is added to the `from ._common import (...)` block at the top of `arsenal.py`.

`src/pitcher_narratives/context.py:138-139` — replace:
```python
    # Determine role from most recent appearance
    most_recent = data.appearances.sort("game_date", descending=True).row(0, named=True)
```
with:
```python
    # Determine role from most recent appearance (deterministic tiebreak)
    most_recent = _most_recent_row(data.appearances)
```
Add the import to `context.py` (check its existing engine imports; if it imports from `pitcher_narratives.engine._common`, extend that; otherwise add `from pitcher_narratives.engine._common import _most_recent_row`).

- [ ] **Step 5: Run the new tests + the affected suites**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py tests/test_context.py -q`
Expected: PASS (new tests pass; existing arsenal/context tests unchanged — real single-game dates have unique game_pk so output is identical).

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/engine/_common.py src/pitcher_narratives/engine/arsenal.py src/pitcher_narratives/context.py tests/test_engine.py
git commit -m "fix(engine): deterministic game_pk tiebreak on most-recent appearance (G5)"
```

---

## Task 2: G7 — N-aware outlier tags

**Files:**
- Modify: `src/pitcher_narratives/engine/baselines.py:157-165`
- Modify: `src/pitcher_narratives/pipeline.py:590,592,594`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `outlier_tag(value: float, avg: float, std: float, n: int, floor: int = _MIN_PITCHES) -> str`. Below the floor it returns `f"SMALL SAMPLE, N={n} -- untagged"` regardless of z-score. At/above the floor, behavior is unchanged from today.

Rationale: `outlier_tag` today tags off a single-outing mean with no shrinkage, and the stuff-specialist prompt orders the LLM to "RESPECT THE TAGS" (`pipeline.py:176`). A thin sample must not be amplified into a grade driver.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine.py` (add `from pitcher_narratives.engine.baselines import outlier_tag`; `_MIN_PITCHES` is 10):

```python
def test_outlier_tag_suppressed_below_sample_floor():
    # z-score would be a strong OUTLIER, but N is below the floor -> suppressed.
    tag = outlier_tag(value=100.0, avg=92.0, std=1.0, n=4)
    assert tag == "SMALL SAMPLE, N=4 -- untagged"


def test_outlier_tag_normal_string_unchanged_at_floor():
    tag = outlier_tag(value=92.5, avg=92.0, std=1.0, n=10)
    assert tag == "NORMAL (z=+0.5)"


def test_outlier_tag_outlier_string_unchanged_above_floor():
    tag = outlier_tag(value=95.0, avg=92.0, std=1.0, n=25)
    assert tag == "OUTLIER (above avg, z=+3.0)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py -k outlier_tag -v`
Expected: FAIL — `outlier_tag() missing 1 required positional argument: 'n'` (the suppression test) / `TypeError` on the others.

- [ ] **Step 3: Implement**

Replace `src/pitcher_narratives/engine/baselines.py:157-165`. `_MIN_PITCHES` must be importable here — add `from ._common import _MIN_PITCHES` if not already imported (check the existing imports at the top of `baselines.py`; if `_common` import would create a cycle, instead accept the floor only via the `floor` parameter and have callers pass `_MIN_PITCHES`). Prefer the import; the engine package already cross-imports `_common` freely.

```python
def outlier_tag(
    value: float, avg: float, std: float, n: int, floor: int = _MIN_PITCHES
) -> str:
    """Return OUTLIER/NORMAL tag based on z-score, suppressed below the sample floor.

    Below ``floor`` pitches the sample is too thin to trust, so no OUTLIER/NORMAL
    judgment is emitted — the tag explicitly says so instead (design §15 G7).
    """
    if n < floor:
        return f"SMALL SAMPLE, N={n} -- untagged"
    if std == 0:
        return "NORMAL"
    z = (value - avg) / std
    if abs(z) > 1.5:
        direction = "above" if z > 0 else "below"
        return f"OUTLIER ({direction} avg, z={z:+.1f})"
    return f"NORMAL (z={z:+.1f})"
```

- [ ] **Step 4: Update the pipeline call sites**

In `src/pitcher_narratives/pipeline.py` (inside the `for p in ctx.arsenal:` loop, lines 590/592/594) pass the window pitch count (`ArsenalPitch.n_pitches_window` exists):

```python
            velo_tag = outlier_tag(p.window_velo, b.avg_velo, b.velo_std, p.n_pitches_window)
            pfx_x_delta = p.window_pfx_x - b.avg_pfx_x
            pfx_x_tag = outlier_tag(p.window_pfx_x, b.avg_pfx_x, b.pfx_x_std, p.n_pitches_window)
            pfx_z_delta = p.window_pfx_z - b.avg_pfx_z
            pfx_z_tag = outlier_tag(p.window_pfx_z, b.avg_pfx_z, b.pfx_z_std, p.n_pitches_window)
```

- [ ] **Step 5: Run the new tests + affected suite; recalibrate goldens**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py tests/test_pipeline.py -q`
Expected: new tests PASS. Any `test_pipeline` assertion that pinned a `[NORMAL]`/`[OUTLIER]` tag for a pitch whose `n_pitches_window < 10` will now show `[SMALL SAMPLE, N=... -- untagged]`. That is the intended change: update the assertion to the new string and note it in the commit body. If no assertion pins such a tag, nothing else changes.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/engine/baselines.py src/pitcher_narratives/pipeline.py tests/test_engine.py tests/test_pipeline.py
git commit -m "fix(engine): N-aware outlier_tag suppresses tags below sample floor (G7)"
```

---

## Task 3: G2 — empty-frame guard on fastball summary

**Files:**
- Modify: `src/pitcher_narratives/engine/arsenal.py` (`FastballSummary` model + `compute_fastball_summary`)
- Modify: `src/pitcher_narratives/prompt_builder.py` (fastball render)
- Test: `tests/test_engine.py`

**Interfaces:**
- Produces: `FastballSummary` gains `window_empty: bool` (True when zero fastballs of the primary type fall in the window). When `window_empty`, velocity/movement window values fall back to season values (no `None` arithmetic / no `TypeError`), and the delta strings are the empty-frame string (see Task 5 for the shared constant; for this task hardcode `"No data for this frame"` and switch to the shared constant in Task 5).

Rationale: `compute_fastball_summary` does `window_velo = _float(window_fb["release_speed"].mean())` then `velo_delta = window_velo - season_velo`. An empty `window_fb` yields `None` → `TypeError` (`arsenal.py:334-335,373-374`). `compute_arsenal_summary` already guards each metric with `... if n_window > 0 else season_...` (`arsenal.py:565`); the fastball path never did.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine.py` (`import dataclasses`, `from pitcher_narratives.data import load_pitcher_data`, `from pitcher_narratives.engine.arsenal import compute_fastball_summary` — match existing import style in the file):

```python
def test_compute_fastball_summary_empty_window_does_not_crash():
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    # Force an empty frame: no appearances in the window.
    empty = dataclasses.replace(data, window_appearances=data.window_appearances.head(0))
    summary = compute_fastball_summary(empty)
    assert summary is not None
    assert summary.window_empty is True
    # Window values fall back to season values; no None arithmetic.
    assert summary.window_velo == summary.season_velo
    assert summary.velo_delta == "No data for this frame"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py::test_compute_fastball_summary_empty_window_does_not_crash -v`
Expected: FAIL — `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'`.

- [ ] **Step 3: Add the field to `FastballSummary`**

In the `FastballSummary` dataclass (`arsenal.py`, near line 155), add after `small_sample`:

```python
    window_empty: bool = False
    """True when zero fastballs of the primary type fell in the window."""
```
(Default `False` keeps every other construction site valid.)

- [ ] **Step 4: Guard `compute_fastball_summary`**

In `compute_fastball_summary` replace the velocity block (`arsenal.py:333-337`):
```python
    window_fb = fb_statcast.filter(pl.col("game_date").is_in(window_dates))
    window_velo = _float(window_fb["release_speed"].mean())
    velo_delta = window_velo - season_velo

    velo_delta_str = _COLD_START_STRING if cold_start else _velo_delta_string(velo_delta)
```
with:
```python
    window_fb = fb_statcast.filter(pl.col("game_date").is_in(window_dates))
    window_empty = len(window_fb) == 0
    window_velo = _float(window_fb["release_speed"].mean()) if not window_empty else season_velo
    velo_delta = window_velo - season_velo

    if window_empty:
        velo_delta_str = "No data for this frame"
    elif cold_start:
        velo_delta_str = _COLD_START_STRING
    else:
        velo_delta_str = _velo_delta_string(velo_delta)
```
Replace the movement block (`arsenal.py:373-378`) so window movement also falls back and its delta strings honor `window_empty`:
```python
    window_pfx_x = (_float(window_fb["pfx_x"].mean()) * _FEET_TO_INCHES) if not window_empty else season_pfx_x
    window_pfx_z = (_float(window_fb["pfx_z"].mean()) * _FEET_TO_INCHES) if not window_empty else season_pfx_z
```
and where `pfx_x_delta_str`/`pfx_z_delta_str` are assigned (the `if cold_start:` block at 376-378), add a leading `window_empty` branch that sets both to `"No data for this frame"`. Finally add `window_empty=window_empty,` to the `FastballSummary(...)` constructor (near line 416).

- [ ] **Step 5: Render the empty-frame contract**

In `src/pitcher_narratives/prompt_builder.py`, at the start of the fastball render (the function ending at line 210), after computing `fb`, add:
```python
    if fb.window_empty:
        lines.append(f"- {fb.pitch_name} ({fb.pitch_type}): No data for this frame")
        return "\n".join(lines)
```
Place this after the header line(s) that name the pitch but before the per-metric season/window/delta lines, so an empty frame renders one explicit "no data" line instead of season numbers dressed as window numbers. (Read lines 170-210 to slot it correctly relative to the existing header append.)

- [ ] **Step 6: Run the new test + affected suites**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py tests/test_context.py -q`
Expected: new test PASS; existing tests unchanged (real windows are never empty, so `window_empty` is `False` and every path is identical to today).

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/engine/arsenal.py src/pitcher_narratives/prompt_builder.py tests/test_engine.py
git commit -m "fix(engine): guard compute_fastball_summary against empty frame (G2)"
```

---

## Task 4: G6 — suppress fastball deltas below the pitch-count floor

**Files:**
- Modify: `src/pitcher_narratives/engine/arsenal.py` (`compute_fastball_summary`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `FastballSummary.small_sample` (already computed as `len(window_fb) < _MIN_PITCHES`) and `window_empty` from Task 3.
- Produces: when `small_sample` and not `window_empty`, the velocity / P+ / S+ / L+ / movement delta strings render the literal `"insufficient sample"` instead of a computed delta like `"Down sharply (-15)"`. The numeric window values are still populated (they feed nothing that claims confidence); only the qualitative delta strings are suppressed.

Rationale: `_MIN_PITCHES = 10`; today `small_sample` only appends a cosmetic `- *Small sample*` line (`prompt_builder.py:208`). Design §15 G6: below the floor, suppress the delta string, don't just mark it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine.py`:

```python
def test_compute_fastball_summary_suppresses_deltas_below_floor():
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    # A single game_date almost always yields fewer than _MIN_PITCHES fastballs.
    one_game = data.window_appearances.sort(
        ["game_date", "game_pk"], descending=True, nulls_last=True
    ).head(1)
    thin = dataclasses.replace(data, window_appearances=one_game)
    summary = compute_fastball_summary(thin)
    assert summary is not None
    assert summary.window_empty is False
    assert summary.small_sample is True
    assert summary.velo_delta == "insufficient sample"
    assert summary.p_plus_delta == "insufficient sample"
    assert summary.s_plus_delta == "insufficient sample"
    assert summary.l_plus_delta == "insufficient sample"
    assert summary.pfx_x_delta == "insufficient sample"
    assert summary.pfx_z_delta == "insufficient sample"
```

> If this test's `small_sample` assertion is `False` for the real pitcher (i.e. one game already has ≥10 fastballs), instead slice to the appearance with the fewest fastballs; but for Cam Booser (reliever) a single relief outing is well under 10 fastballs, so `head(1)` is expected to be thin.

- [ ] **Step 2: Run test to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py::test_compute_fastball_summary_suppresses_deltas_below_floor -v`
Expected: FAIL — `velo_delta` is a computed string (e.g. `"Down ..."`) not `"insufficient sample"`.

- [ ] **Step 3: Implement suppression**

Add a module constant near `_COLD_START_STRING` in `_common.py`:
```python
_INSUFFICIENT_SAMPLE_STRING = "insufficient sample"
```
Export it from `engine/__init__.py` alongside `_COLD_START_STRING` and import it in `arsenal.py`.

In `compute_fastball_summary`, after `small_sample` is computed and after all six delta strings (`velo_delta_str`, `p_plus_delta_str`, `s_plus_delta_str`, `l_plus_delta_str`, `pfx_x_delta_str`, `pfx_z_delta_str`) are assigned, insert a single suppression gate **before** the `FastballSummary(...)` construction:
```python
    # G6: below the pitch-count floor, a computed delta implies confidence the
    # sample cannot support. Suppress the qualitative delta strings (empty frame
    # already handled above via window_empty).
    if small_sample and not window_empty:
        velo_delta_str = _INSUFFICIENT_SAMPLE_STRING
        p_plus_delta_str = _INSUFFICIENT_SAMPLE_STRING
        s_plus_delta_str = _INSUFFICIENT_SAMPLE_STRING
        l_plus_delta_str = _INSUFFICIENT_SAMPLE_STRING
        pfx_x_delta_str = _INSUFFICIENT_SAMPLE_STRING
        pfx_z_delta_str = _INSUFFICIENT_SAMPLE_STRING
```
Ensure this runs after the cold-start/empty branches so it takes precedence for the thin-but-nonempty case.

- [ ] **Step 4: Run the new test + affected suites; recalibrate goldens**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py tests/test_context.py tests/test_pipeline.py -q`
Expected: new test PASS. Any existing test that pinned a fastball delta string for a window under 10 pitches now reads `"insufficient sample"`. Update those assertions and note the diff in the commit body. `test_arsenal_small_sample` (if it exists) likely needs updating from "flag only" to "suppressed delta".

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/engine/_common.py src/pitcher_narratives/engine/__init__.py src/pitcher_narratives/engine/arsenal.py tests/test_engine.py
git commit -m "fix(engine): suppress fastball deltas below pitch-count floor (G6)"
```

---

## Task 5: G8 — frame-aware sufficiency gate replacing `_is_cold_start`

**Files:**
- Modify: `src/pitcher_narratives/engine/_common.py` (add `FrameSufficiency`, `frame_sufficiency`, render-string constants; update `_pplus_delta_strings`; remove `_is_cold_start`)
- Modify: `src/pitcher_narratives/engine/arsenal.py`, `contact.py`, `execution.py`, `mechanics.py` (migrate call sites)
- Modify: `src/pitcher_narratives/prompt_builder.py` (surface `thin`/`empty` hedge)
- Modify: `src/pitcher_narratives/engine/__init__.py` (export changes)
- Test: `tests/test_engine.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces:
  ```python
  FrameSufficiency = Literal["sufficient", "thin", "empty"]

  def frame_sufficiency(data: PitcherData) -> FrameSufficiency: ...
  ```
  - `"empty"` — `len(data.window_appearances) == 0`.
  - `"thin"` — window is non-empty but underpowered: either it covers the whole season (`len(window_appearances) >= len(appearances)` — the old cold-start condition, no prior baseline to compare) OR fewer than `_THIN_APPEARANCES` appearances.
  - `"sufficient"` — otherwise.
  - `_THIN_APPEARANCES = 10` (ties to the existing `<10 appearances` relevance tier at `workload.py:338`).
- The old `cold_start: bool` fields on the summary dataclasses are **retained** (renaming them is out of scope), but are now populated as `frame_sufficiency(data) != "sufficient"`. The delta-string helpers select the render string by state.

Rationale: `_is_cold_start` compares window-appearance count vs total — a day-window notion that mis-fires under count frames. Replacing it with a three-state gate that is surfaced in the output satisfies "sufficiency is surfaced, never silent" (design §15).

> **Decision (user-confirmed):** full replacement now — `_is_cold_start` is removed and every call site migrates to `frame_sufficiency`. Under day-windows this newly classifies windows with 1–9 appearances as `thin` (previously they rendered normal deltas), which changes output for early-season/low-appearance pitchers. That is the intended §15 behavior; recalibrate goldens accordingly.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine.py` (`from pitcher_narratives.engine._common import frame_sufficiency`):

```python
def test_frame_sufficiency_empty_when_no_window_appearances():
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    empty = dataclasses.replace(data, window_appearances=data.window_appearances.head(0))
    assert frame_sufficiency(empty) == "empty"


def test_frame_sufficiency_thin_below_appearance_floor():
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    thin = dataclasses.replace(data, window_appearances=data.window_appearances.head(1))
    assert frame_sufficiency(thin) == "thin"


def test_frame_sufficiency_thin_when_window_covers_full_season():
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    # window == all appearances -> no prior baseline to compare
    full = dataclasses.replace(data, window_appearances=data.appearances)
    assert frame_sufficiency(full) == "thin"


def test_is_cold_start_removed():
    import pitcher_narratives.engine._common as common
    assert not hasattr(common, "_is_cold_start")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py -k "frame_sufficiency or cold_start_removed" -v`
Expected: FAIL — `cannot import name 'frame_sufficiency'`.

- [ ] **Step 3: Add the gate and render strings; retire `_is_cold_start`**

In `_common.py` add near the top constants (`Literal` from `typing` — add to imports):
```python
_THIN_APPEARANCES = 10
"""Below this many appearances a frame is too thin to power a comparison."""

_COLD_START_STRING = "Full season in window -- no trend comparison"  # existing; keep
_THIN_FRAME_STRING = "Underpowered comparison -- insufficient window sample"
_EMPTY_FRAME_STRING = "No data for this frame"

FrameSufficiency = Literal["sufficient", "thin", "empty"]
```
Add the gate and delete `_is_cold_start`:
```python
def frame_sufficiency(data: PitcherData) -> FrameSufficiency:
    """Classify the current frame's power to support a season-vs-window comparison.

    Returns ``"empty"`` (no appearances), ``"thin"`` (non-empty but underpowered:
    covers the whole season, or fewer than ``_THIN_APPEARANCES`` appearances), or
    ``"sufficient"``. Replaces the day-window-shaped ``_is_cold_start`` (design §15 G8).
    """
    n_window = len(data.window_appearances)
    n_total = len(data.appearances)
    if n_window == 0:
        return "empty"
    if n_window >= n_total or n_window < _THIN_APPEARANCES:
        return "thin"
    return "sufficient"
```

- [ ] **Step 4: Update `_pplus_delta_strings` to take sufficiency**

Replace the signature/body (`_common.py:219-237`):
```python
def _pplus_delta_strings(
    sufficiency: FrameSufficiency,
    season_p: float,
    season_s: float,
    season_l: float,
    window_p: float | None,
    window_s: float | None,
    window_l: float | None,
) -> tuple[str, str, str]:
    """Compute P+/S+/L+ delta strings with sufficiency and None handling."""
    if sufficiency == "empty":
        return _EMPTY_FRAME_STRING, _EMPTY_FRAME_STRING, _EMPTY_FRAME_STRING
    if sufficiency == "thin":
        return _THIN_FRAME_STRING, _THIN_FRAME_STRING, _THIN_FRAME_STRING
    if window_p is None:
        return "No window data", "No window data", "No window data"
    return (
        _pplus_delta_string(window_p - season_p),
        _pplus_delta_string(window_s - season_s) if window_s is not None else "No window data",
        _pplus_delta_string(window_l - season_l) if window_l is not None else "No window data",
    )
```

- [ ] **Step 5: Migrate every call site**

At each site currently doing `cold_start = _is_cold_start(data)` (arsenal.py:326,501; contact.py:59; execution.py:192,296; mechanics.py:131), replace with:
```python
    sufficiency = frame_sufficiency(data)
    cold_start = sufficiency != "sufficient"
```
Keep the existing `cold_start=cold_start` dataclass assignments (fields unchanged). Then update each place that branches on `cold_start` to render the state-specific string:
- Where code does `X = _COLD_START_STRING if cold_start else _something(...)`, change to select `_EMPTY_FRAME_STRING` / `_THIN_FRAME_STRING` by `sufficiency` (empty→empty string, thin→thin string, sufficient→computed). Sites: arsenal.py:337 (already replaced in Task 3 — extend its branch order: `window_empty` → `sufficiency` → computed), arsenal.py:376-378, arsenal.py:528-529 (`usage_delta`), arsenal.py:572-575, contact.py:79, mechanics.py:173-176.
- Where `_pplus_delta_strings(cold_start, ...)` is called (search all engine files), pass `sufficiency` instead of `cold_start`.
- Update imports in each engine file: drop `_is_cold_start`, add `frame_sufficiency`, `_THIN_FRAME_STRING`, `_EMPTY_FRAME_STRING`, `FrameSufficiency` as needed; update `engine/__init__.py` re-exports (drop `_is_cold_start`, add the new names).

Note: `_COLD_START_STRING` remains defined and exported (still the message for the whole-season sub-case if any site wants to distinguish it), but the primary thin message is `_THIN_FRAME_STRING`. If a site previously relied on the exact `_COLD_START_STRING` text and you want to preserve the "full season" wording for the `n_window >= n_total` case specifically, that is acceptable — but keep it consistent and update goldens either way.

- [ ] **Step 6: Surface the hedge in the rendered prompt**

In `prompt_builder.py`, the two consumers of `cold_start` are at line 141 (`not hhr.cold_start`) and line 402 (`all_cold = all(pt.cold_start for pt in entries)`). These already gate trend prose on cold-start. Extend line 402's block so that when `all_cold` (now = all non-sufficient), the rendered header explicitly states the comparison is underpowered — read lines 395-410 and append a line like:
```python
    if all_cold:
        lines.append("_Note: window is thin/empty — trend comparisons below are underpowered._")
```
(Match the surrounding append style and heading level.) This satisfies "the trends/CHANGES narration is told when a comparison is underpowered."

- [ ] **Step 7: Run the full engine + pipeline + context suites; recalibrate goldens**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_engine.py tests/test_context.py tests/test_pipeline.py -q`
Expected: new tests PASS. Existing assertions that pinned `_COLD_START_STRING` for the test pitcher's window (Cam Booser's 30-day window vs full season) will change to `_THIN_FRAME_STRING` if the window is <10 appearances or covers the season. Update each and record the before/after in the commit body. `test_cold_start_arsenal` will need updating to the new semantics/strings.

- [ ] **Step 8: Full-suite regression**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: PASS except the one known pre-existing failure `test_to_prompt_token_budget` (carried from phase 4). If any other test fails, it is a real regression from this task — fix or recalibrate it before committing.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(engine): frame_sufficiency gate replaces _is_cold_start (G8)"
```

---

## Task 6: Phase-5 wrap-up

- [ ] **Step 1: Confirm grep-clean**

Run: `grep -rn "_is_cold_start" src/ ; grep -rn "\.sort(\"game_date\", descending=True)\.row(0" src/`
Expected: no matches (all migrated).

- [ ] **Step 2: Full suite one more time**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: PASS except the known `test_to_prompt_token_budget` pre-existing failure. Record the pass/fail count.

- [ ] **Step 3: Update the SDD ledger**

Append a `## Phase 5: Frame Sufficiency & Determinism Guards` section to `.superpowers/sdd/progress.md` mirroring the phase-4 format: plan path, base commit, the 5 guard tasks with commit SHAs, and a note that G6/G7/G8 changed goldens (with the recalibrated test names). Commit:
```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(sdd): phase-5 frame-sufficiency ledger"
```

- [ ] **Step 4: Request whole-branch review** per the project's per-phase ritual (see phase-3/4 log entries) before considering phase 5 complete.

---

## Self-Review (spec coverage)

- **G2** empty-frame crash → Task 3 (guard + `window_empty` + render). ✓
- **G5** determinism / `game_pk` tiebreak → Task 1 (`_most_recent_row`, both `.row(0)` sites). ✓
- **G6** tiny-frame delta suppression → Task 4 (`_INSUFFICIENT_SAMPLE_STRING`). ✓
- **G7** N-aware outlier tags → Task 2 (`outlier_tag(..., n)` + pipeline call sites). ✓
- **G8** frame-aware sufficiency gate → Task 5 (`frame_sufficiency`, full `_is_cold_start` replacement, surfaced hedge). ✓
- "Surfaced, never silent" principle → Tasks 3/4/5 all render explicit strings, plus Task 5 Step 6 hedge line. ✓

Deferred to phase 6 (window swap), not this plan: making the appearance-count slicer primary, renaming `cold_start` fields, recalibrating morning-run/bench proxies.
