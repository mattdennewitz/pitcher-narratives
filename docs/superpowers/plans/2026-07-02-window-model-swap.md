# Window-Model Swap (Phase 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap the sole analysis slicer from a day-based lookback to an appearance-count window, make it the primary frame, re-express cold-start in appearance terms, retire the `WINDOW_DAYS` transitional frame, and recalibrate the goldens the swap moves.

**Architecture:** `PitcherData.window_appearances` and every downstream `window_*` consumer stay exactly as they are — only *how* that slice is populated changes. A new `filter_to_recent_appearances(df, n)` replaces `filter_to_window(df, window_days)` inside `load_pitcher_data`. The report/bench CLI surface swaps `--window <days>` for `--recent <appearances>`; the scout/morning *discovery scan* (`scout_appearances(window_days=…)`) is a separate calendar concept and is **left untouched**. `TemporalFrame.WINDOW_DAYS` is deleted; `MultiFrameContext.primary` re-points to `TemporalFrame.RECENT`. Because the swap changes which pitches land in the window, it is **not output-neutral** — affected goldens are regenerated and diff-reviewed.

**Tech Stack:** Python 3.14, polars, pytest. No new dependencies.

## Global Constraints

- Python 3.14+; run everything via `uv run` against the project `.venv`.
- `snake_case` functions/modules, `PascalCase` types, `UPPER_SNAKE_CASE` constants; Google-style docstrings; type hints on every signature.
- Pydantic models for structured data, not dicts.
- Absolute imports for project modules; keep `data.py` module-level imports minimal (CLI `--help` latency budget).
- SDD ledger: append task progress to `.superpowers/sdd/progress.md` under a new `## Phase 6` heading.
- Base commit: `5bb3b1d` (Phase 5 complete). `main` (`f9ea1ce`) stays untouched; do **not** push.
- **Carry-forward invariant (from Phase 5):** the appearance-count window MUST be ≥ `_THIN_APPEARANCES` (10). A default below 10 makes *every* frame permanently `"thin"` and collapses all trend deltas to the "Underpowered comparison" hedge (`engine/_common.py:328`).
- Source of truth: `docs/superpowers/specs/2026-06-29-mode-based-narration-design.md` §5 (window model), §13 item 6 (this phase), §14 (swap is not output-neutral).

## Locked design decisions (from brainstorming)

1. **Default RECENT span:** empirically derived from real Statcast data, floored at 10. Measured once at execution time (Task 2) and hard-coded as a documented constant.
2. **API surface:** swap to `--recent N` (appearance count) end-to-end for the report + bench paths; remove the `window_days` analysis parameter and `WINDOW_DAYS` frame. The scout discovery-scan `window_days` stays calendar-based.
3. **Goldens:** regenerate affected fixtures from the new slicer, then diff-review each change in its commit.

---

## File Structure

- `src/pitcher_narratives/data.py` — replace `filter_to_window` with `filter_to_recent_appearances`; rewire `load_pitcher_data` signature. **Primary change site.**
- `src/pitcher_narratives/temporal.py` — delete `TemporalFrame.WINDOW_DAYS`.
- `src/pitcher_narratives/context.py` — `MultiFrameContext.primary` → `RECENT`; `assemble_multi_frame_context` builds the `RECENT` frame; doc wording.
- `src/pitcher_narratives/cli.py` — `report` subparser `--window/-w <days>` → `--recent/-n <appearances>`; call site at `cli.py:221`.
- `src/pitcher_narratives/bench/runner.py`, `src/pitcher_narratives/bench/__main__.py` — bench `-w/--window` → `-n/--recent`; `load_pitcher_data` call.
- `src/pitcher_narratives/engine/_common.py` — `frame_sufficiency` docstring/comment wording (appearance terms). Logic already appearance-count-correct.
- `tests/` — `test_data.py`, `test_context.py`, `test_temporal.py`, `test_cli.py`, `test_bench.py`, plus any golden/`test_fact_parity.py`/`test_engine.py`/`test_pipeline.py` fixtures the slice moves.

**Explicitly NOT touched (separate calendar concept):** `scout.py`, `morning.py` `window_days`, `scout_cli.py`, `bench` scout-discovery flags. `run_morning(window_days=…)` and `scout_appearances(window_days=…)` scan calendar days for candidate appearances — orthogonal to the analysis window.

## Task ordering rationale

Task 1 lands the new slicer as a pure, independently-tested function with `filter_to_window` still in place (no behavior change yet). Task 2 flips `load_pitcher_data` onto it and derives the default — this is the one behavior-moving commit; goldens recalibrate here. Task 3 (CLI/bench surface) and Task 4 (frame retirement) are mechanical follow-ons that depend on Task 2's new signature. Task 5 is wording-only. Task 6 is the full-suite green gate + ledger.

---

## Task 1: Appearance-count slicer

**Files:**
- Modify: `src/pitcher_narratives/data.py` (add function near `filter_to_window:433`; add to `__all__:27`)
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: a `pl.DataFrame` of classified appearances with a `game_date` column and one row per pitch (same shape `filter_to_window` receives).
- Produces: `filter_to_recent_appearances(df: pl.DataFrame, n: int) -> pl.DataFrame` — returns all pitch rows belonging to the `n` most-recent **distinct appearances** (by `game_date`, with `game_pk` as the deterministic doubleheader tiebreak per Phase-5 G5). Fewer than `n` distinct appearances → returns all rows. Empty input → empty frame.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_data.py` (near the existing `filter_to_window` tests):

```python
def test_filter_to_recent_appearances_keeps_n_latest_games():
    df = pl.DataFrame(
        {
            "game_date": [date(2024, 4, 1), date(2024, 4, 1), date(2024, 4, 5), date(2024, 4, 10)],
            "game_pk": [1, 1, 2, 3],
            "pitch_type": ["FF", "SL", "FF", "FF"],
        }
    )
    out = filter_to_recent_appearances(df, 2)
    # The 2 most-recent appearances are 4/10 (pk 3) and 4/5 (pk 2).
    assert sorted(out["game_pk"].unique().to_list()) == [2, 3]
    assert len(out) == 2


def test_filter_to_recent_appearances_distinguishes_doubleheader_by_game_pk():
    # Same calendar date, two game_pks -> two distinct appearances.
    df = pl.DataFrame(
        {
            "game_date": [date(2024, 4, 1), date(2024, 4, 1), date(2024, 3, 20)],
            "game_pk": [10, 11, 5],
            "pitch_type": ["FF", "FF", "FF"],
        }
    )
    out = filter_to_recent_appearances(df, 2)
    assert sorted(out["game_pk"].unique().to_list()) == [10, 11]


def test_filter_to_recent_appearances_returns_all_when_fewer_than_n():
    df = pl.DataFrame(
        {"game_date": [date(2024, 4, 1)], "game_pk": [1], "pitch_type": ["FF"]}
    )
    assert len(filter_to_recent_appearances(df, 10)) == 1


def test_filter_to_recent_appearances_empty_input_returns_empty():
    df = pl.DataFrame(
        schema={"game_date": pl.Date, "game_pk": pl.Int64, "pitch_type": pl.Utf8}
    )
    assert filter_to_recent_appearances(df, 5).is_empty()
```

Ensure `filter_to_recent_appearances` is imported in the test's import block (it will be exported from `data.py`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data.py -k filter_to_recent_appearances -v`
Expected: FAIL — `ImportError` / `cannot import name 'filter_to_recent_appearances'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/pitcher_narratives/data.py` (immediately after `filter_to_window`):

```python
def filter_to_recent_appearances(df: pl.DataFrame, n: int) -> pl.DataFrame:
    """Filter pitch rows to the ``n`` most-recent distinct appearances.

    An appearance is a unique ``(game_date, game_pk)`` pair, so doubleheaders
    on the same calendar date count as two appearances. Ordering is
    deterministic: most-recent ``game_date`` first, ``game_pk`` descending as
    the tiebreak (matches the Phase-5 G5 most-recent picker). When the frame
    holds fewer than ``n`` distinct appearances, all rows are returned.

    Args:
        df: DataFrame of pitch rows with ``game_date`` and ``game_pk`` columns.
        n: Number of most-recent appearances to retain.

    Returns:
        Pitch rows belonging to the ``n`` most-recent appearances.
    """
    if df.is_empty():
        return df
    recent_keys = (
        df.select("game_date", "game_pk")
        .unique()
        .sort(["game_date", "game_pk"], descending=True, nulls_last=True)
        .head(n)
    )
    return df.join(recent_keys, on=["game_date", "game_pk"], how="inner")
```

Add `"filter_to_recent_appearances"` to `__all__` in `data.py:27`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data.py -k filter_to_recent_appearances -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/data.py tests/test_data.py
git commit -m "feat(data): appearance-count slicer filter_to_recent_appearances (P6)"
```

---

## Task 2: Flip `load_pitcher_data` onto the appearance-count window

**Files:**
- Modify: `src/pitcher_narratives/data.py:454-474` (`load_pitcher_data` signature + slicer call; add default constant)
- Modify: `tests/test_data.py`, and any `load_pitcher_data(...)`-dependent goldens the slice moves.

**Interfaces:**
- Consumes: `filter_to_recent_appearances` (Task 1).
- Produces: `load_pitcher_data(pitcher_id: int, recent_appearances: int = _DEFAULT_RECENT_APPEARANCES) -> PitcherData`. `window_appearances` is now the `recent_appearances`-most-recent-appearance slice. The `window_days` parameter is removed.

- [ ] **Step 1: Empirically derive the default span**

Measure how many distinct appearances the current 30-day window yields for a real multi-appearance pitcher, then floor at 10. Run:

```bash
uv run python -c "
from datetime import date, timedelta
from pitcher_narratives.data import load_statcast, classify_appearances
import polars as pl
for pid in (592155, 676571):
    df = classify_appearances(load_statcast(pid))
    mx = df['game_date'].max()
    win = df.filter(pl.col('game_date') >= mx - timedelta(days=30))
    n = win.select('game_date','game_pk').unique().height
    print(pid, 'appearances in last 30d:', n)
"
```

Record the counts. Set `_DEFAULT_RECENT_APPEARANCES = max(<measured typical count>, 10)`. Document the derivation in a code comment and in the Task-2 commit body. **If the measured count is below 10, the floor of 10 wins** (carry-forward invariant). Note in the ledger which pitcher/count drove the choice, and reconcile against `tests/test_data.py:25`'s "1 regular-season RP appearance" comment — if the fixture pitcher truly has <10 real appearances, the default is 10 and the Phase-5 fact-parity fixtures (expanded to 10) remain the mechanism keeping the suite green.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_data.py`:

```python
def test_load_pitcher_data_slices_by_appearance_count(monkeypatch):
    from pitcher_narratives import data as data_mod

    captured = {}

    real = data_mod.filter_to_recent_appearances

    def spy(df, n):
        captured["n"] = n
        return real(df, n)

    monkeypatch.setattr(data_mod, "filter_to_recent_appearances", spy)
    result = data_mod.load_pitcher_data(TEST_PITCHER, recent_appearances=3)
    assert captured["n"] == 3
    # window_appearances holds at most 3 distinct appearances.
    n_appts = result.window_appearances.select("game_date", "game_pk").unique().height
    assert n_appts <= 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_data.py -k slices_by_appearance_count -v`
Expected: FAIL — `TypeError: load_pitcher_data() got an unexpected keyword argument 'recent_appearances'`.

- [ ] **Step 4: Rewire `load_pitcher_data`**

In `src/pitcher_narratives/data.py`:

Add near the top-of-module constants:

```python
# Default analysis window, in most-recent appearances. Derived empirically
# (~30d of a reliever's usage) and floored at the thin-frame threshold
# (_THIN_APPEARANCES = 10); a smaller default would make every frame "thin".
_DEFAULT_RECENT_APPEARANCES = <value from Step 1>
```

Change the signature and slicer call (`data.py:454`, `474`):

```python
def load_pitcher_data(
    pitcher_id: int, recent_appearances: int = _DEFAULT_RECENT_APPEARANCES
) -> PitcherData:
```

Update the docstring `Args:` to describe `recent_appearances` (drop `window_days`). Replace:

```python
    window_appearances = filter_to_window(appearances, window_days)
```
with:
```python
    window_appearances = filter_to_recent_appearances(appearances, recent_appearances)
```

Delete `filter_to_window` and remove `"filter_to_window"` from `__all__` (grep-confirm no remaining src references first: `rg 'filter_to_window' src`). Remove the now-unused `timedelta` import from `data.py` **only if** no other function uses it (grep first).

- [ ] **Step 5: Run the new test + full data suite**

Run: `uv run pytest tests/test_data.py -v`
Expected: the new test PASSES. Other `test_data.py` tests that asserted day-window slice contents will need regeneration — proceed to Step 6.

- [ ] **Step 6: Regenerate + diff-review affected goldens**

Run the broader suites the slice feeds:

```bash
uv run pytest tests/test_data.py tests/test_engine.py tests/test_fact_parity.py tests/test_pipeline.py tests/test_context.py -q
```

For each failure caused by the slice moving (different pitches in `window_appearances`): confirm the new expected value is arithmetically correct against the new slice (do **not** weaken assertions — recompute, don't loosen), update the fixture/expected literal, and note the change. Keep genuinely-broken tests broken. Re-run until these suites are green.

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/data.py tests/
git commit -m "feat(data): load_pitcher_data slices by appearance count; retire filter_to_window (P6)

Default _DEFAULT_RECENT_APPEARANCES=<value>, derived from ~30d reliever
usage, floored at _THIN_APPEARANCES=10. Goldens recalibrated for the
appearance-count slice (not output-neutral, design §14)."
```

---

## Task 3: Swap the CLI + bench surface to `--recent`

**Files:**
- Modify: `src/pitcher_narratives/cli.py:38-45` (report subparser), `cli.py:221` (call site)
- Modify: `src/pitcher_narratives/bench/runner.py:61,69`, `src/pitcher_narratives/bench/__main__.py:48,82,93`
- Test: `tests/test_cli.py`, `tests/test_bench.py`

**Interfaces:**
- Consumes: `load_pitcher_data(pitcher_id, recent_appearances=…)` (Task 2).
- Produces: report CLI flag `-n/--recent <int>` (appearances); bench `-n/--recent <int>`.

**Do NOT touch** the morning path: `cli.py:447 run_morning(window_days=args.window, …)` belongs to the **morning** subparser's own `--window` (calendar discovery scan), not the report window. Verify the report and morning subparsers have independent `--window` args before editing; only the *report* one changes.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py` (follow the existing arg-parsing test style):

```python
def test_report_accepts_recent_appearance_count():
    parser = build_parser()  # or the project's parser factory used elsewhere in this file
    args = parser.parse_args(["report", "-p", "592155", "--recent", "5"])
    assert args.recent == 5


def test_report_recent_defaults_to_appearance_span():
    parser = build_parser()
    args = parser.parse_args(["report", "-p", "592155"])
    # default is the empirically-derived appearance count, not 30
    assert args.recent >= 10
```

Match the parser-construction helper already used by neighbouring tests in `test_cli.py` (grep for how existing tests build the parser).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k recent -v`
Expected: FAIL — unrecognized arguments / `Namespace` has no attribute `recent`.

- [ ] **Step 3: Update the report subparser + call site**

In `cli.py` (report subparser, lines ~38-45), replace the `-w/--window` block with:

```python
    report.add_argument(
        "-n",
        "--recent",
        type=int,
        default=_DEFAULT_RECENT_APPEARANCES,
        help="Analysis window in most-recent appearances (default: %(default)s)",
    )
```

Import the default: `from pitcher_narratives.data import _DEFAULT_RECENT_APPEARANCES` (keep lazy if it pulls polars — check existing import placement; if importing it eagerly regresses `--help` latency, define the default in `temporal.py` or a lightweight constants module instead and import from there in both `data.py` and `cli.py`).

At `cli.py:221` change:
```python
        pitcher_data = load_pitcher_data(args.pitcher, args.window)
```
to:
```python
        pitcher_data = load_pitcher_data(args.pitcher, args.recent)
```

- [ ] **Step 4: Update bench**

`bench/runner.py:61` — rename param `window_days: int = 30` → `recent_appearances: int = _DEFAULT_RECENT_APPEARANCES`; line 69 → `load_pitcher_data(pitcher_id, recent_appearances=recent_appearances)`.
`bench/__main__.py:48` — `-w/--window … default=30 help="Lookback window days"` → `-n/--recent … default=_DEFAULT_RECENT_APPEARANCES help="Analysis window in appearances"`; lines 82/93 → `recent_appearances=args.recent`.

- [ ] **Step 5: Run CLI + bench tests**

Run: `uv run pytest tests/test_cli.py tests/test_bench.py -v`
Expected: PASS. Update any test that referenced `--window`/`args.window` on the **report/bench** path (not morning).

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/cli.py src/pitcher_narratives/bench/ tests/test_cli.py tests/test_bench.py
git commit -m "feat(cli): report/bench take --recent N appearances, not --window days (P6)"
```

---

## Task 4: Retire `TemporalFrame.WINDOW_DAYS`; primary → RECENT

**Files:**
- Modify: `src/pitcher_narratives/temporal.py:19`
- Modify: `src/pitcher_narratives/context.py:190-204`
- Test: `tests/test_temporal.py`, `tests/test_context.py`

**Interfaces:**
- Consumes: `TemporalFrame.RECENT`, `assemble_pitcher_context(data)`.
- Produces: `MultiFrameContext.frames` keyed by `TemporalFrame.RECENT`; `MultiFrameContext.primary` returns the `RECENT` frame.

- [ ] **Step 1: Write the failing tests**

In `tests/test_temporal.py`:
```python
def test_window_days_frame_removed():
    from pitcher_narratives.temporal import TemporalFrame
    assert not hasattr(TemporalFrame, "WINDOW_DAYS")
    assert "window_days" not in [f.value for f in TemporalFrame]
```

In `tests/test_context.py` (adapt to the existing multi-frame test that references `WINDOW_DAYS`):
```python
def test_primary_frame_is_recent(sample_pitcher_data):
    ctx = assemble_multi_frame_context(sample_pitcher_data)
    assert TemporalFrame.RECENT in ctx.frames
    assert ctx.primary is ctx.for_frame(TemporalFrame.RECENT)
```
Use whatever `sample_pitcher_data` fixture `test_context.py` already provides.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_temporal.py tests/test_context.py -k "window_days or primary_frame or recent" -v`
Expected: FAIL — `WINDOW_DAYS` still present; `primary` still reads `WINDOW_DAYS`.

- [ ] **Step 3: Delete the frame + re-point primary**

`temporal.py:19` — delete the `WINDOW_DAYS = "window_days"` line.

`context.py` — update `primary` and the assembler:
```python
    @property
    def primary(self) -> PitcherContext:
        """The default frame current call sites read (the recent-appearance window)."""
        return self.for_frame(TemporalFrame.RECENT)
```
```python
def assemble_multi_frame_context(data: PitcherData) -> MultiFrameContext:
    """Assemble the multi-frame context.

    The recent-appearance window is the primary frame. PRIOR / MOST_RECENT /
    SEASON frames are added when CHANGES/RECAP land (design §5).
    """
    return MultiFrameContext(
        frames={TemporalFrame.RECENT: assemble_pitcher_context(data)},
    )
```
Update the `MultiFrameContext` class docstring (`context.py:172`) to drop the "Today only WINDOW_DAYS" wording.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_temporal.py tests/test_context.py -v`
Expected: PASS. Grep-confirm no remaining `WINDOW_DAYS` references anywhere: `rg 'WINDOW_DAYS|window_days' src tests` — remaining hits must only be the scout/morning **discovery** `window_days` (calendar), never the frame.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/temporal.py src/pitcher_narratives/context.py tests/test_temporal.py tests/test_context.py
git commit -m "feat(context): retire WINDOW_DAYS frame; primary frame is RECENT (P6)"
```

---

## Task 5: Re-express cold-start / window wording in appearance terms

**Files:**
- Modify: `src/pitcher_narratives/engine/_common.py:314-316` (`frame_sufficiency` docstring)
- Test: existing sufficiency tests in `tests/test_engine.py` (assert wording only if a user-facing string changes)

**Interfaces:** none new. `frame_sufficiency` logic is already appearance-count-correct (counts `len(window_appearances)`); only the day-window-shaped *wording* is stale.

- [ ] **Step 1: Audit user-facing strings**

Run: `rg -n 'day-window|30-day|days back|in window|Full season in window|cold[- ]start' src/pitcher_narratives`
For each hit, decide: user-facing narration string (must re-express in appearance terms) vs. internal comment/docstring (update for accuracy). The Phase-5 recalibration already moved narration strings to "Underpowered comparison"; confirm none still say "day"/"30".

- [ ] **Step 2: Update wording**

`_common.py:316` docstring — change "day-window-shaped cold-start detector" to "appearance-count frame sufficiency gate". Update any comment referencing days to reference appearances. Do **not** change logic or thresholds.

- [ ] **Step 3: Run the engine suite**

Run: `uv run pytest tests/test_engine.py -q`
Expected: PASS (wording-only change; assertions unchanged unless a narration string moved, in which case update the golden and confirm arithmetic).

- [ ] **Step 4: Commit**

```bash
git add src/pitcher_narratives/engine/_common.py tests/
git commit -m "docs(engine): re-express window sufficiency wording in appearance terms (P6)"
```

---

## Task 6: Phase-6 wrap-up — full-suite green gate + ledger

**Files:**
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass except the one documented pre-existing failure `test_to_prompt_token_budget` (present since Phase 4). Any *other* failure must be resolved or explicitly justified as a recalibrated golden before wrap-up.

- [ ] **Step 2: Grep-clean verification**

Run: `rg -n 'filter_to_window|WINDOW_DAYS' src` — expect **zero** hits. `rg -n 'window_days' src` — expect only scout/morning discovery-scan hits (`scout.py`, `morning.py`, `scout_cli.py`, bench scout flags), never the analysis window.

- [ ] **Step 3: Append the Phase-6 ledger section**

Append a `## Phase 6: Window-Model Swap` section to `.superpowers/sdd/progress.md` mirroring the Phase-5 format: plan path (`docs/superpowers/plans/2026-07-02-window-model-swap.md`), base commit `5bb3b1d`, the derived `_DEFAULT_RECENT_APPEARANCES` value and how it was measured, the 5 impl tasks with commit SHAs, the list of recalibrated goldens, and confirmation that `main` (`f9ea1ce`) is untouched and the branch is not pushed.

- [ ] **Step 4: Commit**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(sdd): Phase 6 window-model swap wrap-up"
```

---

## Self-Review (spec coverage)

- **§5 appearance-count slicer** → Task 1 (`filter_to_recent_appearances`) + Task 2 (wired into `load_pitcher_data`). ✓
- **§5 REPORT RECENT span becomes appearance count, default mapped from 30d** → Task 2 Step 1 (empirical derivation, floored at 10). ✓
- **§5/§Frames: remove `WINDOW_DAYS` transitional scaffolding** → Task 4. ✓
- **§5 cold-start re-expressed in appearance terms** → Task 5 (logic already migrated in Phase 5 G8; wording here). ✓
- **§10 CLI surface (`--recent`)** → Task 3. ✓
- **§14 swap not output-neutral, isolated phase, explicit recalibration** → Task 2 Step 6 + Task 6 (regenerate + diff-review, full-suite gate). ✓
- **Carry-forward invariant (window ≥ 10)** → Task 2 Step 1 floor. ✓
- **Scout/morning `window_days` untouched** → called out in File Structure, Task 3 guard, Task 6 Step 2 grep. ✓
- **Out of scope (correctly deferred to later phases):** multi-frame RECENT/PRIOR/SEASON assembly and `--prior` (Phase 9 CHANGES); MOST_RECENT/RECAP (Phase 8); per-mode focus. This phase populates only the RECENT primary frame.
