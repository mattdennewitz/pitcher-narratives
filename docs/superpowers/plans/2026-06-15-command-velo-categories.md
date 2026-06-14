# command_breakout + velo_drop Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two morning-slate editorial categories — `command_breakout` (driven by a new `command_surge` scout signal) and `velo_drop` (curator-inferred, no new signal).

**Architecture:** `command_surge` is a new per-pitch-type scout signal (Location+ surge vs season, mirror of `development_opportunity`) that scores its appearances so they reach the curator. `velo_drop` adds no scout signal — it is the structural mirror of `clean_breakout`, inferred by the curator from existing `velo_delta`(down) + `pplus_swing`(down) signals. Both become curator categories with digest sections.

**Tech Stack:** Python 3.14, polars, pydantic / pydantic-ai, pytest. Run everything with `uv run`.

**Spec:** `docs/superpowers/specs/2026-06-15-command-velo-categories-design.md`

**Branch:** `feat/command-velo-categories` (already created off `main`).

---

### Task 1: `command_surge` scout signal

A new per-pitch-type signal: a pitch whose Location+ jumped `>= _COMMAND_SURGE_DELTA (15)` versus its season baseline AND whose game L+ is now `>= _COMMAND_GOOD_LPLUS (110)`, gated by `n_pitches >= _MIN_TYPE_PITCHES (3)`. This makes command surges visible to the scorer so they reach the curator (today nothing measures an L+ jump).

**Files:**
- Modify: `src/pitcher_narratives/scout.py` (weights ~34-45, thresholds ~60-63, new check fn after `_check_development_opportunity` which ends at line 556, wiring at line 237)
- Test: `tests/test_scout.py` (append after line 99)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scout.py`:

```python
def test_command_surge_fires_on_location_jump():
    """A pitch whose L+ surged vs season and now locates well fires command_surge."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SL"],
        "n_pitches": [12],
        "S+": [105.0],
        "L+": [118.0],          # game L+ well above the 110 floor
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SL"],
        "S+": [104.0],
        "L+": [98.0],           # +20 vs season, >= 15 delta
    })
    fired = {s.detail.split(":")[0] for s in _check_command_surge(game_types, baseline)}
    assert "SL" in fired


def test_command_surge_ignores_small_jump():
    """An L+ gain below the surge delta does not fire."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SL"],
        "n_pitches": [12],
        "S+": [105.0],
        "L+": [112.0],          # above floor, but only +5 vs season
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SL"],
        "S+": [104.0],
        "L+": [107.0],
    })
    assert _check_command_surge(game_types, baseline) == []


def test_command_surge_ignores_sub_floor_command():
    """A big L+ jump that still lands below the 'good command' floor does not fire."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SL"],
        "n_pitches": [12],
        "S+": [105.0],
        "L+": [100.0],          # +20 vs season but below the 110 floor
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SL"],
        "S+": [104.0],
        "L+": [80.0],
    })
    assert _check_command_surge(game_types, baseline) == []


def test_command_surge_ignores_tiny_samples():
    """A one-pitch L+ can't establish a command jump (small-sample gate)."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SI", "SL"],
        "n_pitches": [1, 12],
        "S+": [105.0, 105.0],
        "L+": [125.0, 118.0],
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SI", "SL"],
        "S+": [104.0, 104.0],
        "L+": [98.0, 98.0],
    })
    fired = {s.detail.split(":")[0] for s in _check_command_surge(game_types, baseline)}
    assert "SI" not in fired
    assert "SL" in fired
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_scout.py -k command_surge -v`
Expected: FAIL — `ImportError: cannot import name '_check_command_surge'`.

- [ ] **Step 3: Add the weight and thresholds**

In `src/pitcher_narratives/scout.py`, add to the `_WEIGHTS` dict (after the `development_opportunity` entry, line 43):

```python
    "development_opportunity": 3.5,
    "command_surge": 3.5,
    "workload_flag": 1.0,
```

And add two threshold constants after `_DEV_LPLUS_MAX = 80` (line 62):

```python
_DEV_SPLUS_MIN = 110  # high stuff threshold
_DEV_LPLUS_MAX = 80  # low command threshold
_COMMAND_SURGE_DELTA = 15  # L+ points gained vs season for a command surge
_COMMAND_GOOD_LPLUS = 110  # game L+ floor — command is now a genuine strength
_CONSECUTIVE_DAYS_FLAG = 3
```

- [ ] **Step 4: Add the check function**

In `src/pitcher_narratives/scout.py`, add immediately after `_check_development_opportunity` (which ends at line 556):

```python
def _check_command_surge(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
) -> list[Signal]:
    """Check for pitches whose Location+ surged vs season — command arrived.

    The inverse of development_opportunity: delta-based (a breakout is a change),
    firing when a pitch's L+ jumped meaningfully and now locates well.
    """
    signals: list[Signal] = []
    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        if row.get("n_pitches", 0) < _MIN_TYPE_PITCHES:
            continue  # too few pitches for a reliable L+ grade
        bl_row = pitcher_type_bl.filter(pl.col("pitch_type") == pt)
        if bl_row.is_empty():
            continue

        bl = bl_row.row(0, named=True)
        game_l = row.get("L+")
        season_l = bl.get("L+")
        if game_l is None or season_l is None:
            continue

        l_delta = float(game_l) - float(season_l)
        if l_delta >= _COMMAND_SURGE_DELTA and float(game_l) >= _COMMAND_GOOD_LPLUS:
            signals.append(Signal(
                "command_surge",
                _WEIGHTS["command_surge"],
                f"{pt}: L+ {l_delta:+.0f} (now {float(game_l):.0f}) — found the zone",
            ))
    return signals
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_scout.py -k command_surge -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Wire the signal into per-appearance assembly**

In `src/pitcher_narratives/scout.py`, after the development-opportunity block (line 236-237):

```python
        # --- Signal: Development opportunity (high S+, low L+) ---
        dev_signals = _check_development_opportunity(game_types, pitcher_type_bl)
        signals.extend(dev_signals)

        # --- Signal: Command surge (Location+ jump) ---
        command_signals = _check_command_surge(game_types, pitcher_type_bl)
        signals.extend(command_signals)
```

- [ ] **Step 7: Run the full scout test module to confirm no regressions**

Run: `uv run pytest tests/test_scout.py -q`
Expected: PASS (all scout tests, including the 4 new ones).

- [ ] **Step 8: Commit**

```bash
git add src/pitcher_narratives/scout.py tests/test_scout.py
git commit -m "feat(scout): add command_surge signal for Location+ jumps

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Curator categories + selector prompt

Add `command_breakout` and `velo_drop` to the pick category type, and rewrite the selector prompt's category hierarchy to six items so the LLM knows when to assign them. `velo_drop` is defined here only (no scout signal) — the curator infers it from existing `velo_delta`(down) + `pplus_swing`(down) lines in the briefing.

**Files:**
- Modify: `src/pitcher_narratives/curator.py` (`CurationPick.category` Literal at lines 41-43; `_SELECTOR_PROMPT` at lines 71-91)
- Test: `tests/test_curator.py` (append after line 121)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curator.py`:

```python
def test_slate_accepts_command_breakout_and_velo_drop():
    """The two new categories validate as picks."""
    slate = CurationSlate(picks=[
        CurationPick(**_pick_cat(1, "command_breakout")),
        CurationPick(**_pick_cat(2, "velo_drop")),
    ])
    assert {p.category for p in slate.picks} == {"command_breakout", "velo_drop"}


def test_pick_rejects_unknown_category():
    """A category outside the six-item enum is rejected."""
    with pytest.raises(ValidationError):
        CurationPick(**_pick_cat(1, "not_a_category"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_curator.py -k "command_breakout or unknown_category" -v`
Expected: `test_slate_accepts_command_breakout_and_velo_drop` FAILS (ValidationError — `command_breakout` not a valid Literal); `test_pick_rejects_unknown_category` PASSES already (any unknown string is rejected by the current Literal).

- [ ] **Step 3: Extend the category Literal**

In `src/pitcher_narratives/curator.py`, replace lines 41-43:

```python
    category: Literal[
        "clean_breakout", "command_breakout", "lab_project",
        "identity_crisis", "velo_drop", "red_flag",
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_curator.py -k "command_breakout or unknown_category" -v`
Expected: PASS (both).

- [ ] **Step 5: Rewrite the selector prompt hierarchy**

In `src/pitcher_narratives/curator.py`, replace the hierarchy block (lines 75-91 — from `and select up to 5 picks PER CATEGORY across the four categories below.` through the `4. red_flag:` definition ending `Flag honestly.`) with:

```python
and select up to 5 picks PER CATEGORY across the six categories below.

Use this hierarchy of signal when choosing:

1. clean_breakout: A significant velocity gain (1.5+ mph) coupled with
a jump in overall stuff (P+ or S+). A physical change backed by data.

2. command_breakout: A jump in command — a pitch's Location+ surged
versus its season norm and now locates well. The inverse of a lab
project: the feel has arrived, even if the stuff was already there.

3. lab_project: Top-tier raw stuff (S+ 130+) with poor command
(L+ < 80). High-upside development stories — the pitch has the shape,
the feel hasn't arrived.

4. identity_crisis: A radically altered pitch mix — shelving a primary,
doubling a secondary, or introducing something new. Plan or problem?

5. velo_drop: A fastball velocity loss (1.5+ mph) where the stuff
eroded with it (P+ or S+ down) — a durability concern, distinct from a
tracking artifact. If the velo dipped but the stuff held, it is NOT a
velo_drop.

6. red_flag: Statistical anomalies that look like gains but might be
tracking errors. A single-game velocity spike of 3+ mph, or a P+ jump
the underlying stuff metrics don't support. Flag honestly.
```

(Leave the `RULES:` block below it unchanged.)

- [ ] **Step 6: Run the curator test module**

Run: `uv run pytest tests/test_curator.py -q`
Expected: PASS (all, including the 2 new ones).

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/curator.py tests/test_curator.py
git commit -m "feat(curator): add command_breakout + velo_drop categories

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Digest + CLI category presentation

Register the two new categories in the digest's three category maps (badges, order, section titles) and in the `pitcher-scout --curate` print order. The assembly logic needs no change — it iterates `_CATEGORY_ORDER` and keys into the maps.

**Files:**
- Modify: `src/pitcher_narratives/digest.py` (`_CATEGORY_BADGES` 231-236; `_CATEGORY_ORDER` 238; `_CATEGORY_SECTION_TITLES` 239-244)
- Modify: `src/pitcher_narratives/scout_cli.py` (hardcoded `order` list at line 134)
- Test: `tests/test_digest.py` (append after line 271)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_digest.py`:

```python
def test_digest_renders_new_category_sections_in_order():
    """command_breakout and velo_drop render as sections, in hierarchy order."""
    slate = CurationSlate(picks=[
        _pick2(1, "command_breakout"),
        _pick2(2, "velo_drop"),
        _pick2(3, "red_flag"),
    ])
    appearances = {
        1: _appearance(1, 9.0), 2: _appearance(2, 7.0), 3: _appearance(3, 8.0),
    }
    summaries = {1: "s1", 2: "s2", 3: "s3"}
    out = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=list(appearances.values()), game_date=date(2026, 6, 13), cost_block="cost",
    )
    assert "## Command Breakouts" in out
    assert "## Velocity Drops" in out
    # hierarchy order: command_breakout before velo_drop before red_flag
    assert (
        out.index("## Command Breakouts")
        < out.index("## Velocity Drops")
        < out.index("## Red Flags")
    )
    assert "[COMMAND BREAKOUT]" in out
    assert "[VELO DROP]" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_digest.py -k new_category_sections -v`
Expected: FAIL — `KeyError: 'command_breakout'` (picks land in a category absent from `_CATEGORY_ORDER`/maps; `by_cat` has no such key).

- [ ] **Step 3: Extend the digest category maps**

In `src/pitcher_narratives/digest.py`, replace lines 231-244:

```python
_CATEGORY_BADGES = {
    "clean_breakout": "CLEAN BREAKOUT",
    "command_breakout": "COMMAND BREAKOUT",
    "lab_project": "LAB PROJECT",
    "identity_crisis": "IDENTITY CRISIS",
    "velo_drop": "VELO DROP",
    "red_flag": "RED FLAG",
}

_CATEGORY_ORDER = [
    "clean_breakout", "command_breakout", "lab_project",
    "identity_crisis", "velo_drop", "red_flag",
]
_CATEGORY_SECTION_TITLES = {
    "clean_breakout": "Clean Breakouts",
    "command_breakout": "Command Breakouts",
    "lab_project": "Lab Projects",
    "identity_crisis": "Identity Crises",
    "velo_drop": "Velocity Drops",
    "red_flag": "Red Flags",
}
```

- [ ] **Step 4: Run the digest test to verify it passes**

Run: `uv run pytest tests/test_digest.py -k new_category_sections -v`
Expected: PASS.

- [ ] **Step 5: Update the `--curate` CLI order list**

In `src/pitcher_narratives/scout_cli.py`, replace the hardcoded `order` list at line 134:

```python
        order = [
            "clean_breakout", "command_breakout", "lab_project",
            "identity_crisis", "velo_drop", "red_flag",
        ]
```

- [ ] **Step 6: Run the digest + scout_cli test modules**

Run: `uv run pytest tests/test_digest.py tests/test_scout_cli.py -q`
Expected: PASS (all, including the new digest test).

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/digest.py src/pitcher_narratives/scout_cli.py tests/test_digest.py
git commit -m "feat(digest): render command_breakout + velo_drop sections

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Full-suite verification + lint

Confirm the whole system is green and clean after the three changes.

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS — the prior baseline (580) plus the 7 new tests (4 scout + 2 curator + 1 digest) = 587 passed.

- [ ] **Step 2: Lint and type-check the changed files**

Run: `uv run ruff check src/pitcher_narratives/scout.py src/pitcher_narratives/curator.py src/pitcher_narratives/digest.py src/pitcher_narratives/scout_cli.py`
Expected: no new findings.

Run: `uv run ty check src`
Expected: no new errors.

- [ ] **Step 3: Smoke-test the live scout (optional, no LLM)**

Run: `uv run python -c "from pitcher_narratives.scout import scout_appearances; r = scout_appearances(window_days=14, min_pitches=20); n = sum(1 for a in r for s in a.signals if s.name == 'command_surge'); print(f'command_surge fires in 14d: {n}')"`
Expected: prints a non-negative count (confirms the new signal runs end-to-end against real data without error).

---

## Notes for the implementer

- **`velo_drop` has no scout code by design.** Do not add a `_check_velo_drop`. It is inferred by the curator (Task 2) from the existing `velo_delta` and `pplus_swing` signals, exactly as `clean_breakout` is inferred from their up-direction. The only `velo_drop` change is the category Literal + the prompt definition.
- **Category order is identical in three places** — keep `_CATEGORY_ORDER` (digest), the selector prompt hierarchy (curator), and the `--curate` `order` list (scout_cli) in the same sequence: `clean_breakout, command_breakout, lab_project, identity_crisis, velo_drop, red_flag`.
- **Out of scope:** `quiet_riser`; the dead `walk_rate_pplus_contradiction` / `hard_hit_spike` / `workload_flag` weights; any threshold/cap retuning.
