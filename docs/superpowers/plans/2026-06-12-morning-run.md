# Morning Editorial Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `pitcher-narratives morning` subcommand that scouts the most recent games, has an LLM editor select up to 10 SP + 10 RP stories with angles, writes a tailored summary per pick concurrently, and assembles a digest with a full scored board and cost footer into `morning-runs/<game-date>/`.

**Architecture:** Two-stage editorial workflow. Stage 1 (selector) is one structured-output LLM call choosing the slate from scout-scored candidates. Stage 2 (writers) is one LLM call per pick, fed a deterministic cue package (scout signals + selector angle + season baselines). Everything between and after the LLM calls is deterministic, testable code. Spec: `docs/superpowers/specs/2026-06-12-morning-run-design.md`.

**Tech Stack:** Python 3.14, polars, pydantic, pydantic-ai (`Agent`, `ModelRetry`, `TestModel` for tests), pytest. Run commands with `uv run`.

**Conventions:** Conventional commits (`feat(scope): Subject`), each ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. All tests live in `tests/`, run via `uv run pytest`.

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `src/pitcher_narratives/costs.py` | create | `PRICING`, `UsageTracker` (per-call stage records + per-model totals), cost block + table rendering |
| `compare.py` | modify | Delete local `PRICING`/`UsageTracker`, import from `costs.py` |
| `src/pitcher_narratives/data.py` | modify | Add league-wide `classify_game_roles()` |
| `src/pitcher_narratives/scout.py` | modify | `ScoredAppearance.role`, role attachment, per-role top-N |
| `src/pitcher_narratives/scout_cli.py` | modify | Role column in table, `--curate` prints structured slate |
| `src/pitcher_narratives/curator.py` | rewrite | `CurationPick`/`CurationSlate` models, role-bucketed briefing, structured selector with `ModelRetry` validation. Streaming prose path deleted. |
| `src/pitcher_narratives/digest.py` | create | Story cue builder, per-pick writer (with fallback), digest assembler incl. Full Board |
| `src/pitcher_narratives/morning.py` | create | `run_morning()` orchestration: scout → select → cues → writers → assemble → write artifacts |
| `src/pitcher_narratives/cli.py` | modify | argparse subcommands: `report` (existing flags) + `morning` |
| `tests/test_costs.py` | create | Tracker arithmetic, unknown-model `n/a`, rendering |
| `tests/test_data.py` | modify | `classify_game_roles` cases incl. opener edge |
| `tests/test_scout.py` | create | `_top_per_role` helper |
| `tests/test_curator.py` | create | Slate validation, briefing format, selector via `TestModel` |
| `tests/test_digest.py` | create | Cue rendering, writer fallback, assembler golden checks |
| `tests/test_morning.py` | create | End-to-end orchestration with `TestModel` + tmp dirs |
| `tests/test_cli.py` | modify | Subcommand routing; bare `-p` now errors |
| `tests/test_scout_cli.py` | modify | Existing parse tests still pass; `--curate` help text |
| `README.md` | modify | New CLI invocations |
| `pyproject.toml` | unchanged | `pitcher-narratives` entry point already exists; no new script |

---

### Task 1: Cost tracking module (`costs.py`)

**Files:**
- Create: `src/pitcher_narratives/costs.py`
- Test: `tests/test_costs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_costs.py`:

```python
"""Tests for the shared cost-tracking module."""

from pitcher_narratives.costs import PRICING, UsageTracker, model_label


def test_model_label_strips_provider_prefix():
    """Provider-qualified model ids reduce to bare model names."""
    assert model_label("anthropic:claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert model_label("google-gla:gemini-3.1-pro-preview") == "gemini-3.1-pro-preview"
    assert model_label("claude-haiku-4-5") == "claude-haiku-4-5"


def test_pricing_covers_the_four_run_models():
    """Both providers' full and mini tiers are priced."""
    for model in (
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "gemini-3.1-pro-preview",
        "gemini-flash-latest",
    ):
        assert "input" in PRICING[model] and "output" in PRICING[model]


def test_tracker_records_and_totals():
    """Records accumulate per model and stage; totals are exact."""
    t = UsageTracker()
    t.record("anthropic:claude-sonnet-4-6", 1_000_000, 500_000, stage="selector")
    t.record("anthropic:claude-sonnet-4-6", 1_000_000, 500_000, stage="writer:Smith")
    # sonnet: $3/M in, $15/M out -> 2M in = $6, 1M out = $15
    assert t.total_cost() == 21.0
    assert t.total_input() == 2_000_000
    assert t.total_output() == 1_000_000
    assert [r.stage for r in t.records] == ["selector", "writer:Smith"]


def test_tracker_unknown_model_costs_none():
    """Unknown models keep token counts but report no dollar cost."""
    t = UsageTracker()
    t.record("openrouter:deepseek/deepseek-v4-pro", 1000, 1000, stage="selector")
    assert t.total_input() == 1000
    assert t.total_cost() is None or t.total_cost() == 0.0
    block = t.render_cost_block(wall_s=10.0)
    assert "n/a" in block


def test_render_cost_block_contents():
    """The digest footer block names stages, models, and the total."""
    t = UsageTracker()
    t.record("google-gla:gemini-3.1-pro-preview", 12_400, 1_100, stage="selector")
    t.record("google-gla:gemini-3.1-pro-preview", 3_000, 500, stage="writer:Smith")
    t.record("google-gla:gemini-3.1-pro-preview", 3_000, 500, stage="writer:Jones")
    block = t.render_cost_block(wall_s=94.0)
    assert "selector" in block
    assert "writers" in block          # writer:* stages are grouped
    assert "gemini-3.1-pro-preview" in block
    assert "94s" in block
    assert "$" in block


def test_to_json_records():
    """Raw per-call records serialize for usage.json."""
    t = UsageTracker()
    t.record("anthropic:claude-sonnet-4-6", 100, 50, stage="selector")
    [rec] = t.to_json()
    assert rec == {
        "stage": "selector",
        "model": "claude-sonnet-4-6",
        "input_tokens": 100,
        "output_tokens": 50,
    }


def test_format_table_still_renders_markdown():
    """compare.py's markdown table survives the move."""
    t = UsageTracker()
    t.record("anthropic:claude-haiku-4-5", 1_000_000, 0, stage="x")
    table = t.format_table()
    assert table.startswith("| Model |")
    assert "claude-haiku-4-5" in table
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_costs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pitcher_narratives.costs'`

- [ ] **Step 3: Implement `costs.py`**

Create `src/pitcher_narratives/costs.py`:

```python
"""Shared LLM cost tracking: pricing table, usage tracker, renderers.

Used by the morning run (digest footer, usage.json) and by compare.py
(markdown table). Token extraction from pydantic-ai usage objects is the
caller's job; this module only does arithmetic and rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["PRICING", "UsageTracker", "model_label"]

PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.00},
    "gemini-flash-latest": {"input": 0.15, "output": 0.60},
}
"""USD per 1M tokens. Keys are bare model names (no provider prefix)."""


def model_label(model: str) -> str:
    """Strip the pydantic-ai provider prefix: 'anthropic:x' -> 'x'."""
    return model.split(":", 1)[-1]


@dataclass
class CallRecord:
    """Token usage for one LLM call."""

    stage: str
    model: str  # bare model name
    input_tokens: int
    output_tokens: int

    def cost(self) -> float | None:
        """Dollar cost, or None when the model is not in PRICING."""
        p = PRICING.get(self.model)
        if p is None:
            return None
        return (
            self.input_tokens / 1_000_000 * p["input"]
            + self.output_tokens / 1_000_000 * p["output"]
        )


@dataclass
class UsageTracker:
    """Accumulates per-call token usage for cost reporting."""

    records: list[CallRecord] = field(default_factory=list)

    def record(self, model: str, input_tokens: int, output_tokens: int,
               *, stage: str = "") -> None:
        """Add one call's usage. `model` may carry a provider prefix."""
        self.records.append(CallRecord(
            stage=stage, model=model_label(model),
            input_tokens=input_tokens, output_tokens=output_tokens,
        ))

    def total_input(self) -> int:
        return sum(r.input_tokens for r in self.records)

    def total_output(self) -> int:
        return sum(r.output_tokens for r in self.records)

    def total_cost(self) -> float | None:
        """Sum of known-model costs; None if NO record has a priced model."""
        costs = [c for r in self.records if (c := r.cost()) is not None]
        if not costs:
            return None
        return sum(costs)

    def to_json(self) -> list[dict]:
        """Raw per-call records for usage.json."""
        return [
            {
                "stage": r.stage,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
            }
            for r in self.records
        ]

    def _grouped(self) -> dict[tuple[str, str], list[CallRecord]]:
        """Group records by (stage group, model). writer:* collapses to 'writers'."""
        groups: dict[tuple[str, str], list[CallRecord]] = {}
        for r in self.records:
            stage = "writers" if r.stage.startswith("writer:") else (r.stage or "other")
            groups.setdefault((stage, r.model), []).append(r)
        return groups

    def render_cost_block(self, *, wall_s: float) -> str:
        """Compact run-cost block for the digest footer and stdout."""

        def _fmt_tokens(n: int) -> str:
            return f"{n / 1000:.1f}k" if n >= 1000 else str(n)

        def _fmt_cost(c: float | None) -> str:
            return f"${c:.3f}" if c is not None else "n/a"

        lines = ["── Run cost ─────────────────────────────"]
        for (stage, model), recs in self._grouped().items():
            tin = sum(r.input_tokens for r in recs)
            tout = sum(r.output_tokens for r in recs)
            costs = [c for r in recs if (c := r.cost()) is not None]
            cost = sum(costs) if costs else None
            count = f" ×{len(recs)}" if len(recs) > 1 else ""
            lines.append(
                f"{stage:<10} {model}{count}  "
                f"{_fmt_tokens(tin)} in / {_fmt_tokens(tout)} out  {_fmt_cost(cost)}"
            )
        lines.append(
            f"{'total':<10} {_fmt_cost(self.total_cost()):>40}   ({wall_s:.0f}s)"
        )
        return "\n".join(lines)

    def format_table(self) -> str:
        """Markdown per-model cost table (compare.py's format)."""
        by_model: dict[str, dict[str, int]] = {}
        for r in self.records:
            t = by_model.setdefault(r.model, {"input": 0, "output": 0})
            t["input"] += r.input_tokens
            t["output"] += r.output_tokens

        rows = [
            "| Model | Input | Output | Input Cost | Output Cost | Total |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        grand_in = grand_out = 0
        grand_cost = 0.0
        for model in sorted(by_model):
            t = by_model[model]
            p = PRICING.get(model, {"input": 0, "output": 0})
            ic = t["input"] / 1_000_000 * p["input"]
            oc = t["output"] / 1_000_000 * p["output"]
            rows.append(
                f"| {model} | {t['input']:,} | {t['output']:,} "
                f"| ${ic:.4f} | ${oc:.4f} | ${ic + oc:.4f} |"
            )
            grand_in += t["input"]
            grand_out += t["output"]
            grand_cost += ic + oc
        rows.append(
            f"| **Total** | **{grand_in:,}** | **{grand_out:,}** "
            f"| | | **${grand_cost:.4f}** |"
        )
        return "\n".join(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_costs.py -q`
Expected: all PASS. If `test_tracker_unknown_model_costs_none` fails on the `total_cost()` assertion, the implementation returns `None` correctly — check the test logic, not the code.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/costs.py tests/test_costs.py
git commit -m "feat(costs): Add shared LLM cost tracking module" \
  -m "Pricing table, per-call usage records tagged by stage, and renderers
for the digest cost footer, usage.json, and compare.py's markdown table.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Refactor compare.py to import from costs.py**

In `compare.py`:
1. Delete the local `PRICING` dict and the entire local `UsageTracker` class.
2. Add `from pitcher_narratives.costs import UsageTracker` near the other imports.
3. Update every `_tracker.record(model_name, usage)` call site to extract tokens explicitly:

```python
_tracker.record(
    model_name,
    usage.request_tokens or 0,
    usage.response_tokens or 0,
)
```

(There are two call sites: `tracked_run` and `tracked_run_stream`. The new tracker has no `reset()`; if `reset()` is called anywhere in compare.py, replace with `_tracker.records.clear()`.)

Note: the old tracker recorded bare model names; the new `record()` runs `model_label()` which is a no-op on bare names — behavior unchanged.

- [ ] **Step 7: Smoke-check compare.py imports**

Run: `uv run python -c "import ast; ast.parse(open('compare.py').read())" && uv run python -c "import compare" 2>&1 | head -3`
Expected: no `NameError`/`ImportError` mentioning `PRICING` or `UsageTracker`. (`import compare` may fail on missing env/dotenv side effects — only import-time name errors matter here.)

- [ ] **Step 8: Commit**

```bash
git add compare.py
git commit -m "ref(compare): Use the shared cost tracker from costs.py" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: League-wide role classification (`data.py`)

**Files:**
- Modify: `src/pitcher_narratives/data.py` (add function after `classify_appearances`, ~line 326)
- Test: `tests/test_data.py` (append)

Context: `classify_appearances()` already exists but is single-pitcher and uses `first_inning == 1`, which would misclassify a reliever who enters mid-first after an opener. The new league-wide function uses the exact rule: per `(game_pk, inning_topbot)`, the pitcher of the minimum `at_bat_number` started for that side.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_data.py`:

```python
# ── classify_game_roles ──────────────────────────────────────────────

import polars as pl

from pitcher_narratives.data import classify_game_roles


def _statcast_rows(rows: list[tuple[int, int, str, int]]) -> pl.DataFrame:
    """Build a minimal statcast frame: (game_pk, pitcher, inning_topbot, at_bat_number)."""
    return pl.DataFrame(
        {
            "game_pk": [r[0] for r in rows],
            "pitcher": [r[1] for r in rows],
            "inning_topbot": [r[2] for r in rows],
            "at_bat_number": [r[3] for r in rows],
        }
    )


def test_classify_game_roles_starter_and_reliever():
    """First pitcher per side is SP; later pitchers are RP."""
    df = _statcast_rows([
        (1, 100, "Top", 1),   # home starter (pitches in Top)
        (1, 100, "Top", 2),
        (1, 101, "Top", 30),  # home reliever
        (1, 200, "Bot", 4),   # away starter
        (1, 201, "Bot", 35),  # away reliever
    ])
    roles = classify_game_roles(df)
    lookup = {
        (r["game_pk"], r["pitcher"]): r["role"]
        for r in roles.iter_rows(named=True)
    }
    assert lookup[(1, 100)] == "SP"
    assert lookup[(1, 101)] == "RP"
    assert lookup[(1, 200)] == "SP"
    assert lookup[(1, 201)] == "RP"


def test_classify_game_roles_opener_edge():
    """A reliever entering mid-first inning is RP (min at_bat_number rule),
    even though their first_inning is 1."""
    df = _statcast_rows([
        (2, 300, "Top", 1),  # opener: faces 2 batters in the 1st
        (2, 300, "Top", 2),
        (2, 301, "Top", 3),  # bulk guy, also enters in the 1st inning
    ])
    roles = classify_game_roles(df)
    lookup = {
        (r["game_pk"], r["pitcher"]): r["role"]
        for r in roles.iter_rows(named=True)
    }
    assert lookup[(2, 300)] == "SP"  # opener started the game: SP
    assert lookup[(2, 301)] == "RP"  # mid-inning entrant: RP


def test_classify_game_roles_multiple_games():
    """Roles are computed per game: the same pitcher can be SP in one
    game and RP in another."""
    df = _statcast_rows([
        (3, 400, "Top", 1),
        (4, 400, "Top", 20),
        (4, 401, "Top", 1),
    ])
    roles = classify_game_roles(df)
    lookup = {
        (r["game_pk"], r["pitcher"]): r["role"]
        for r in roles.iter_rows(named=True)
    }
    assert lookup[(3, 400)] == "SP"
    assert lookup[(4, 400)] == "RP"
    assert lookup[(4, 401)] == "SP"


def test_classify_game_roles_empty_frame():
    """An empty frame yields an empty result, not an error."""
    df = _statcast_rows([])
    roles = classify_game_roles(df)
    assert roles.is_empty()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data.py -q -k classify_game_roles`
Expected: FAIL — `ImportError: cannot import name 'classify_game_roles'`

- [ ] **Step 3: Implement `classify_game_roles`**

Add to `src/pitcher_narratives/data.py` immediately after `classify_appearances` (and add `"classify_game_roles"` to `__all__`):

```python
def classify_game_roles(statcast: pl.DataFrame) -> pl.DataFrame:
    """Classify every appearance in a league-wide statcast frame as SP or RP.

    The starter for each side of each game is the pitcher with the
    minimum at_bat_number in that (game_pk, inning_topbot) group. This
    handles the opener edge that first_inning == 1 misses: a reliever
    entering mid-first is RP.

    Args:
        statcast: Pitch-level frame with at least game_pk, pitcher,
            inning_topbot, at_bat_number (any number of pitchers/games).

    Returns:
        One row per (game_pk, pitcher) with a 'role' column ('SP'/'RP').
    """
    if statcast.is_empty():
        return pl.DataFrame(
            schema={"game_pk": pl.Int64, "pitcher": pl.Int64, "role": pl.String}
        )
    starters = (
        statcast.group_by(["game_pk", "inning_topbot"])
        .agg(pl.col("pitcher").sort_by("at_bat_number").first())
        .select("game_pk", "pitcher")
        .with_columns(pl.lit("SP").alias("role"))
    )
    appearances = statcast.select("game_pk", "pitcher").unique()
    return appearances.join(starters, on=["game_pk", "pitcher"], how="left").with_columns(
        pl.col("role").fill_null("RP")
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data.py -q -k classify_game_roles`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/data.py tests/test_data.py
git commit -m "feat(data): Add league-wide SP/RP game-role classification" \
  -m "Starter per side = pitcher of the minimum at_bat_number in each
(game_pk, inning_topbot) group, so mid-first relief entrants behind an
opener classify as RP.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Scout role field and per-role top-N (`scout.py`)

**Files:**
- Modify: `src/pitcher_narratives/scout.py`
- Modify: `src/pitcher_narratives/scout_cli.py` (table role column)
- Test: `tests/test_scout.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scout.py`:

```python
"""Tests for scout pure helpers: role-aware ranking."""

from datetime import date

from pitcher_narratives.scout import ScoredAppearance, _top_per_role


def _app(pid: int, score: float, role: str) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"P{pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=50,
        score=score, role=role,
    )


def test_top_per_role_caps_each_bucket():
    """Each role keeps its own top N; result is merged, score-desc."""
    apps = [
        _app(1, 9.0, "SP"), _app(2, 8.0, "SP"), _app(3, 7.0, "SP"),
        _app(4, 6.5, "RP"), _app(5, 5.0, "RP"), _app(6, 4.0, "RP"),
    ]
    out = _top_per_role(apps, top_n=2)
    assert [a.pitcher_id for a in out] == [1, 2, 4, 5]
    assert [a.score for a in out] == sorted([a.score for a in out], reverse=True)


def test_top_per_role_thin_bucket():
    """A bucket with fewer than N keeps everything it has."""
    apps = [_app(1, 9.0, "SP"), _app(4, 6.5, "RP")]
    out = _top_per_role(apps, top_n=10)
    assert len(out) == 2


def test_scored_appearance_has_role_default():
    """role is part of the dataclass (default RP so old call sites work)."""
    a = _app(1, 1.0, "SP")
    assert a.role == "SP"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scout.py -q`
Expected: FAIL — `TypeError: ScoredAppearance.__init__() got an unexpected keyword argument 'role'` (and ImportError for `_top_per_role`)

- [ ] **Step 3: Implement scout changes**

In `src/pitcher_narratives/scout.py`:

1. Add `role` to the dataclass (after `score`, before `signals`):

```python
@dataclass
class ScoredAppearance:
    """A scored pitcher appearance with interest signals."""

    pitcher_id: int
    pitcher_name: str
    throws: str
    game_date: date
    game_pk: int
    n_pitches: int
    score: float
    role: str = "RP"
    signals: list[Signal] = field(default_factory=list)
```

2. Add the pure ranking helper (module level, near `scout_appearances`):

```python
def _top_per_role(results: list[ScoredAppearance], top_n: int) -> list[ScoredAppearance]:
    """Keep the top N per role, merged and sorted by score descending."""
    ranked = sorted(results, key=lambda x: x.score, reverse=True)
    sp = [r for r in ranked if r.role == "SP"][:top_n]
    rp = [r for r in ranked if r.role == "RP"][:top_n]
    merged = sp + rp
    merged.sort(key=lambda x: x.score, reverse=True)
    return merged
```

3. Add a role-map loader (near `_compute_velo_baselines`):

```python
def _compute_role_map() -> dict[tuple[int, int], str]:
    """Map (pitcher_id, game_pk) -> 'SP'/'RP' from league-wide statcast."""
    df = load_all_statcast(
        columns=["pitcher", "game_pk", "inning_topbot", "at_bat_number"],
    )
    if df.is_empty():
        return {}
    roles = classify_game_roles(df)
    return {
        (row["pitcher"], row["game_pk"]): row["role"]
        for row in roles.iter_rows(named=True)
    }
```

Add `classify_game_roles` to the existing `from pitcher_narratives.data import (...)` block.

4. Wire into `scout_appearances`:
   - Update the docstring `top_n` line to: `top_n: Return the top N most interesting appearances PER ROLE (SP and RP ranked separately).`
   - Before the `for row in app_window.iter_rows(named=True):` loop, add `role_map = _compute_role_map()`.
   - In the `ScoredAppearance(...)` construction, add `role=role_map.get((pitcher_id, game_pk), "RP"),`.
   - Replace the final two lines (`results.sort(...)` / `return results[:top_n]`) with `return _top_per_role(results, top_n)`.

5. In `src/pitcher_narratives/scout_cli.py`, update `_print_table` to include the role:

```python
def _print_table(results: list, *, verbose: bool) -> None:
    """Print the scored appearances table."""
    print(f"{'Score':>5}  {'Pitcher':<25} {'T':>1} {'Role':<4}  {'Date':<10}  {'#P':>3}  {'Signals'}")
    print(f"{'─' * 5}  {'─' * 25} {'─':>1} {'─' * 4}  {'─' * 10}  {'─' * 3}  {'─' * 40}")

    for r in results:
        signal_names = ", ".join(s.name for s in r.signals)
        print(
            f"{r.score:5.1f}  {r.pitcher_name:<25} {r.throws:>1} {r.role:<4}  "
            f"{r.game_date!s:<10}  {r.n_pitches:>3}  {signal_names}"
        )

        if verbose:
            for s in r.signals:
                print(f"       └─ {s.name} ({s.weight:.1f}): {s.detail}")
            print()
```

Also update the `-n/--top` help string in `scout_cli.parse_args` to `"Number of results per role to show (default: 20)"`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_scout.py tests/test_scout_cli.py -q`
Expected: all PASS (existing scout_cli parse tests are unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/scout.py src/pitcher_narratives/scout_cli.py tests/test_scout.py
git commit -m "feat(scout): Rank appearances per role with SP/RP classification" \
  -m "ScoredAppearance carries role derived from league-wide statcast;
top_n becomes per-role so the morning selector gets real competition
in both buckets.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Structured selector (`curator.py` rewrite)

**Files:**
- Rewrite: `src/pitcher_narratives/curator.py`
- Modify: `src/pitcher_narratives/scout_cli.py` (`--curate` path)
- Test: `tests/test_curator.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_curator.py`:

```python
"""Tests for the structured morning-run selector."""

from datetime import date

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from pitcher_narratives.curator import (
    CurationPick,
    CurationSlate,
    build_selector_briefing,
    select_slate,
)
from pitcher_narratives.scout import ScoredAppearance, Signal


def _app(pid: int, role: str, name: str | None = None) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=name or f"Pitcher {pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=80, score=5.0,
        role=role,
        signals=[Signal("velo_delta", 3.0, "+2.1 mph vs season")],
    )


def _pick(pid: int) -> dict:
    return {
        "pitcher_id": pid,
        "category": "clean_breakout",
        "angle": "Velocity spike with stuff gain",
        "conviction": "medium",
        "conviction_reason": "One game, but the shape data agrees.",
    }


# ── Model validation ────────────────────────────────────────────────


def test_slate_caps_each_role_at_ten():
    with pytest.raises(ValidationError):
        CurationSlate(
            starters=[CurationPick(**_pick(i)) for i in range(11)],
            relievers=[],
        )


def test_slate_must_not_be_empty():
    with pytest.raises(ValidationError):
        CurationSlate(starters=[], relievers=[])


def test_slate_accepts_thin_day():
    slate = CurationSlate(
        starters=[CurationPick(**_pick(1))],
        relievers=[],
    )
    assert len(slate.starters) == 1


# ── Briefing ────────────────────────────────────────────────────────


def test_briefing_buckets_by_role():
    """SP and RP candidates appear under separate labeled sections."""
    briefing = build_selector_briefing([_app(1, "SP"), _app(2, "RP")])
    sp_idx = briefing.index("STARTERS")
    rp_idx = briefing.index("RELIEVERS")
    assert sp_idx < briefing.index("Pitcher 1") < rp_idx
    assert rp_idx < briefing.index("Pitcher 2")
    assert "velo_delta" in briefing
    assert "+2.1 mph vs season" in briefing
    assert "id=1" in briefing  # pitcher_id is in the briefing for the LLM to echo


# ── Selector agent ──────────────────────────────────────────────────


def test_select_slate_returns_validated_slate():
    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={
        "starters": [_pick(1)],
        "relievers": [_pick(2)],
    })
    slate = select_slate(candidates, provider="gemini", _model_override=model)
    assert [p.pitcher_id for p in slate.starters] == [1]
    assert [p.pitcher_id for p in slate.relievers] == [2]


def test_select_slate_rejects_unknown_pitcher_id():
    """A pick whose id is not among the role's candidates is retried and,
    with a model that never corrects, ultimately fails."""
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={
        "starters": [_pick(999)],  # not a candidate
        "relievers": [],
    })
    with pytest.raises(UnexpectedModelBehavior):
        select_slate(candidates, provider="gemini", _model_override=model)


def test_select_slate_rejects_role_swap():
    """An RP candidate picked as a starter bounces."""
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={
        "starters": [_pick(2)],  # RP picked as SP
        "relievers": [],
    })
    with pytest.raises(UnexpectedModelBehavior):
        select_slate(candidates, provider="gemini", _model_override=model)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_curator.py -q`
Expected: FAIL — `ImportError: cannot import name 'CurationPick'`

- [ ] **Step 3: Rewrite `curator.py`**

Replace the entire contents of `src/pitcher_narratives/curator.py`:

```python
"""Structured editorial selection of scouted appearances.

Stage 1 of the morning run: one LLM call ("the editor") reads the
role-bucketed candidate briefing and returns a CurationSlate — up to
10 starters and up to 10 relievers, each with a story category, a
one-sentence angle, and a conviction level. The angle is the cue the
Stage 2 writers build from.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.settings import ModelSettings

from pitcher_narratives.config import PROVIDERS
from pitcher_narratives.scout import ScoredAppearance

__all__ = [
    "CurationPick",
    "CurationSlate",
    "build_selector_briefing",
    "select_slate",
]

_MAX_PICKS_PER_ROLE = 10
_SELECTOR_TEMPERATURE = 0.2
"""Low temperature: selection should be near-deterministic."""
_SELECTOR_MAX_TOKENS = 8192


class CurationPick(BaseModel):
    """One selected story: the pitcher and the editorial framing."""

    pitcher_id: int
    category: Literal[
        "clean_breakout", "lab_project", "identity_crisis", "red_flag"
    ]
    angle: str = Field(min_length=1)
    conviction: Literal["low", "medium", "high"]
    conviction_reason: str = Field(min_length=1)


class CurationSlate(BaseModel):
    """The morning slate: up to 10 picks per role, at least one overall."""

    starters: list[CurationPick] = Field(max_length=_MAX_PICKS_PER_ROLE)
    relievers: list[CurationPick] = Field(max_length=_MAX_PICKS_PER_ROLE)

    @model_validator(mode="after")
    def _non_empty(self) -> "CurationSlate":
        if not self.starters and not self.relievers:
            raise ValueError("slate must contain at least one pick")
        return self


_SELECTOR_PROMPT = """\
You are the editor of a data-driven baseball morning report. From the
scored candidate appearances below, select up to 10 STARTERS and up to
10 RELIEVERS whose outings are the most compelling stories, focusing on
process over results.

Use this hierarchy of signal when choosing:

1. clean_breakout: A significant velocity gain (1.5+ mph) coupled with
a jump in overall stuff (P+ or S+). A physical change backed by data.

2. lab_project: Top-tier raw stuff (S+ 130+) with poor command
(L+ < 80). High-upside development stories — the pitch has the shape,
the feel hasn't arrived.

3. identity_crisis: A radically altered pitch mix — shelving a primary,
doubling a secondary, or introducing something new. Plan or problem?

4. red_flag: Statistical anomalies that look like gains but might be
tracking errors. A single-game velocity spike of 3+ mph, or a P+ jump
the underlying stuff metrics don't support. Flag honestly.

RULES:
- Pick ONLY from the listed candidates, using their exact pitcher_id.
- Starters come ONLY from the STARTERS section, relievers ONLY from
  the RELIEVERS section.
- If a bucket is thin, pick fewer. Never pad with ordinary outings.
- Ignore "good" outings where the data matches the season average.
- For each pick: category from the hierarchy above; angle is ONE
  sentence stating the story; conviction scaled to the sample with a
  one-sentence reason. Be pragmatic, not breathless.
"""


def build_selector_briefing(candidates: list[ScoredAppearance]) -> str:
    """Render role-bucketed candidates as the selector's briefing."""

    def _bucket(label: str, apps: list[ScoredAppearance]) -> list[str]:
        lines = [f"=== {label} ({len(apps)} candidates) ==="]
        if not apps:
            lines.append("(none)")
        for r in apps:
            lines.append(
                f"## {r.pitcher_name} (id={r.pitcher_id}, {r.throws}HP) — "
                f"{r.game_date}, {r.n_pitches} pitches, score {r.score:.1f}"
            )
            for s in r.signals:
                lines.append(f"- [{s.name}] {s.detail}")
            lines.append("")
        return lines

    sp = [r for r in candidates if r.role == "SP"]
    rp = [r for r in candidates if r.role == "RP"]
    return "\n".join(_bucket("STARTERS", sp) + _bucket("RELIEVERS", rp))


def make_selector_agent(
    provider: str, candidates: list[ScoredAppearance]
) -> Agent[None, CurationSlate]:
    """Build the selector agent with candidate-membership validation."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}, expected: {', '.join(PROVIDERS)}")

    sp_ids = {r.pitcher_id for r in candidates if r.role == "SP"}
    rp_ids = {r.pitcher_id for r in candidates if r.role == "RP"}

    agent: Agent[None, CurationSlate] = Agent(
        PROVIDERS[provider],
        output_type=CurationSlate,
        system_prompt=_SELECTOR_PROMPT,
        model_settings=ModelSettings(
            temperature=_SELECTOR_TEMPERATURE, max_tokens=_SELECTOR_MAX_TOKENS,
        ),
        retries=3,
        defer_model_check=True,
    )

    @agent.output_validator
    def _picks_are_candidates(output: CurationSlate) -> CurationSlate:
        bad_sp = [p.pitcher_id for p in output.starters if p.pitcher_id not in sp_ids]
        bad_rp = [p.pitcher_id for p in output.relievers if p.pitcher_id not in rp_ids]
        if bad_sp or bad_rp:
            raise ModelRetry(
                f"Invalid picks — not candidates in that role bucket: "
                f"starters {bad_sp}, relievers {bad_rp}. "
                f"Use only the listed pitcher_id values."
            )
        return output

    return agent


def select_slate(
    candidates: list[ScoredAppearance],
    *,
    provider: str = "gemini",
    tracker: object | None = None,
    _model_override: object = None,
) -> CurationSlate:
    """Run the selector over the candidates and return the validated slate.

    Args:
        candidates: Role-tagged ranked output of scout_appearances.
        provider: Contestant provider key.
        tracker: Optional costs.UsageTracker; records the call as 'selector'.
        _model_override: Test-only model override.
    """
    agent = make_selector_agent(provider, candidates)
    briefing = build_selector_briefing(candidates)
    user_msg = (
        "Select the slate from these scored candidates.\n\n" + briefing
    )
    kwargs: dict = {"user_prompt": user_msg}
    if _model_override is not None:
        kwargs["model"] = _model_override
    result = agent.run_sync(**kwargs)
    if tracker is not None:
        usage = result.usage()
        tracker.record(  # type: ignore[attr-defined]
            PROVIDERS[provider],
            usage.request_tokens or 0,
            usage.response_tokens or 0,
            stage="selector",
        )
    return result.output
```

Implementation note: pydantic-ai output validators may be declared with or without `RunContext` as the first parameter; the single-argument form above is supported. If the installed version requires the context form, use:

```python
    @agent.output_validator
    def _picks_are_candidates(ctx, output: CurationSlate) -> CurationSlate:
        ...same body...
```

- [ ] **Step 4: Run tests, adjust for pydantic-ai specifics**

Run: `uv run pytest tests/test_curator.py -q`
Expected: all PASS. Two known wobbles:
- If the `UnexpectedModelBehavior` tests fail because `TestModel` *does* satisfy retries differently, check what exception surfaces after retries exhaust (`uv run python -c "import pydantic_ai.exceptions as e; print(dir(e))"`) and assert that one.
- If `TestModel(custom_output_args=...)` nesting fails validation, pass the dict under the output tool's schema as shown (it maps to `CurationSlate(**custom_output_args)`).

- [ ] **Step 5: Repoint `scout_cli --curate`**

In `src/pitcher_narratives/scout_cli.py`, replace the `--curate` help string with `"Run the LLM selector on the scored candidates and print the slate"`, and replace the curate block at the bottom of `main()` with:

```python
    if args.curate:
        # Check API key
        env_var = API_KEYS[args.provider]
        if not os.environ.get(env_var):
            print(f"\nError: {env_var} not set.", file=sys.stderr)
            sys.exit(1)

        from pitcher_narratives.curator import select_slate

        print(f"\n{'═' * 72}", file=sys.stderr)
        print("SELECTOR — choosing the slate...", file=sys.stderr)
        print(f"{'═' * 72}\n", file=sys.stderr)

        slate = select_slate(results, provider=args.provider)
        names = {r.pitcher_id: r.pitcher_name for r in results}
        for label, picks in (("STARTERS", slate.starters), ("RELIEVERS", slate.relievers)):
            print(f"\n{label}")
            for p in picks:
                print(f"  [{p.category}] {names.get(p.pitcher_id, p.pitcher_id)} "
                      f"({p.conviction}): {p.angle}")
```

- [ ] **Step 6: Run the full curator + scout_cli tests**

Run: `uv run pytest tests/test_curator.py tests/test_scout_cli.py -q`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/curator.py src/pitcher_narratives/scout_cli.py tests/test_curator.py
git commit -m "feat(curator): Replace prose curation with a structured selector" \
  -m "One editor call returns a validated CurationSlate (up to 10 SP +
10 RP picks with category, angle, conviction). Picks are checked
against the role-bucketed candidate list via ModelRetry. The streaming
prose path is deleted; scout --curate prints the slate.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Cue builder, per-pick writer, assembler (`digest.py`)

**Files:**
- Create: `src/pitcher_narratives/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_digest.py`:

```python
"""Tests for the morning digest: cues, writers, assembly."""

import asyncio
from datetime import date

import polars as pl
from pydantic_ai.models.test import TestModel

from pitcher_narratives.curator import CurationPick, CurationSlate
from pitcher_narratives.digest import (
    assemble_digest,
    build_story_cue,
    render_full_board,
    write_pick_summaries,
)
from pitcher_narratives.personas import DEFAULT_PERSONA
from pitcher_narratives.scout import ScoredAppearance, Signal


def _app(pid: int, role: str = "SP", score: float = 5.0) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"Pitcher {pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=80, score=score,
        role=role,
        signals=[Signal("velo_delta", 3.0, "+2.1 mph vs season")],
    )


def _pick(pid: int) -> CurationPick:
    return CurationPick(
        pitcher_id=pid, category="clean_breakout",
        angle="Velocity spike with stuff gain", conviction="medium",
        conviction_reason="One game, but shape agrees.",
    )


def _season_baseline() -> pl.DataFrame:
    return pl.DataFrame({
        "pitcher": [1], "season": [2026], "n_pitches": [900],
        "P+": [104.0], "S+": [112.0], "L+": [96.0],
    })


def _type_baseline() -> pl.DataFrame:
    return pl.DataFrame({
        "pitcher": [1, 1], "season": [2026, 2026],
        "pitch_type": ["FF", "SL"], "n_pitches": [500, 400],
        "S+": [115.0, 108.0], "L+": [98.0, 93.0],
        "usage_pct": [55.6, 44.4],
    })


# ── Cue builder ─────────────────────────────────────────────────────


def test_story_cue_contains_all_layers():
    cue = build_story_cue(
        _app(1), _pick(1),
        season_baseline=_season_baseline(),
        type_baseline=_type_baseline(),
        season_velo=94.8,
    )
    assert "Pitcher 1" in cue
    assert "2026-06-10" in cue and "80 pitches" in cue and "SP" in cue
    assert "velo_delta" in cue and "+2.1 mph vs season" in cue
    assert "clean_breakout" in cue
    assert "Velocity spike with stuff gain" in cue
    assert "medium" in cue
    # season context slice
    assert "104" in cue and "112" in cue and "96" in cue
    assert "FF" in cue and "55.6" in cue
    assert "94.8" in cue


def test_story_cue_handles_missing_baselines():
    """A pick with no baseline rows still renders (signals + angle only)."""
    empty = pl.DataFrame(schema={"pitcher": pl.Int64, "season": pl.Int64})
    cue = build_story_cue(
        _app(1), _pick(1),
        season_baseline=empty, type_baseline=empty, season_velo=None,
    )
    assert "Velocity spike with stuff gain" in cue
    assert "no season baseline available" in cue


# ── Writers ─────────────────────────────────────────────────────────


def test_write_pick_summaries_returns_text_per_pick():
    apps = {1: _app(1), 2: _app(2, role="RP")}
    cues = {1: "cue one", 2: "cue two"}
    picks = [_pick(1), _pick(2)]
    summaries = asyncio.run(write_pick_summaries(
        picks, cues, apps, provider="gemini", persona=DEFAULT_PERSONA,
        _model_override=TestModel(custom_output_text="A tailored summary."),
    ))
    assert summaries[1] == "A tailored summary."
    assert summaries[2] == "A tailored summary."


def test_write_pick_summaries_falls_back_on_failure():
    """A writer that raises degrades to a deterministic cue rendering."""

    class _ExplodingModel(TestModel):
        async def request(self, *args, **kwargs):
            raise RuntimeError("provider error")

    apps = {1: _app(1)}
    cues = {1: "the cue text"}
    summaries = asyncio.run(write_pick_summaries(
        [_pick(1)], cues, apps, provider="gemini", persona=DEFAULT_PERSONA,
        _model_override=_ExplodingModel(),
    ))
    assert "[summary unavailable" in summaries[1]
    assert "Velocity spike with stuff gain" in summaries[1]


# ── Full Board + assembly ───────────────────────────────────────────


def test_render_full_board_groups_and_sorts():
    board = render_full_board([
        _app(1, "SP", 9.0), _app(2, "RP", 7.0), _app(3, "SP", 3.0),
    ])
    assert board.index("Starters") < board.index("Pitcher 1") < board.index("Pitcher 3")
    assert board.index("Relievers") < board.index("Pitcher 2")
    assert "velo_delta" in board and "+2.1 mph vs season" in board
    assert "9.0" in board


def test_assemble_digest_layout():
    slate = CurationSlate(starters=[_pick(1)], relievers=[_pick(2)])
    apps = {1: _app(1), 2: _app(2, role="RP")}
    digest = assemble_digest(
        slate=slate,
        summaries={1: "SP summary text.", 2: "RP summary text."},
        appearances=apps,
        board=[_app(1), _app(2, role="RP")],
        game_date=date(2026, 6, 10),
        cost_block="── Run cost ── total $0.10 (5s)",
    )
    assert digest.startswith("# Morning Digest — 2026-06-10")
    i_sp = digest.index("## Starters")
    i_rp = digest.index("## Relievers")
    i_board = digest.index("## The Full Board")
    assert i_sp < i_rp < i_board
    assert i_sp < digest.index("SP summary text.") < i_rp
    assert i_rp < digest.index("RP summary text.") < i_board
    assert "clean_breakout" in digest          # category badge
    assert "Pitcher 1" in digest               # name resolved from scout data
    assert digest.rstrip().endswith("(5s)")    # cost footer last
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_digest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pitcher_narratives.digest'`

- [ ] **Step 3: Implement `digest.py`**

Create `src/pitcher_narratives/digest.py`:

```python
"""Morning digest: story cues, per-pick writers, and assembly.

Stage 2 of the morning run. Each selected pick gets a deterministic
cue package (scout signals + the selector's angle + a season context
slice); a writer call turns each cue into a short tailored summary;
deterministic code assembles the digest document.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import polars as pl

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from pitcher_narratives.config import PROVIDERS
from pitcher_narratives.curator import CurationPick, CurationSlate
from pitcher_narratives.personas import Persona
from pitcher_narratives.scout import ScoredAppearance

__all__ = [
    "assemble_digest",
    "build_story_cue",
    "render_full_board",
    "write_pick_summaries",
]

log = logging.getLogger("pitcher_narratives.digest")

_WRITER_TEMPERATURE = 0.7
"""Match the pipeline writer's voice settings."""
_WRITER_MAX_TOKENS = 2048


# ── Cue builder ─────────────────────────────────────────────────────


def build_story_cue(
    app: ScoredAppearance,
    pick: CurationPick,
    *,
    season_baseline: pl.DataFrame,
    type_baseline: pl.DataFrame,
    season_velo: float | None,
) -> str:
    """Render the writer's briefing for one pick.

    Layers: appearance line, fired scout signals, the selector's
    editorial framing, and a compact season context slice.
    """
    lines = [
        f"PITCHER: {app.pitcher_name} ({app.throws}HP, {app.role})",
        f"APPEARANCE: {app.game_date}, {app.n_pitches} pitches",
        "",
        "FIRED SIGNALS (from deterministic scouting):",
    ]
    for s in app.signals:
        lines.append(f"- [{s.name}] {s.detail}")
    lines += [
        "",
        "EDITORIAL FRAMING (from the selector):",
        f"- Category: {pick.category}",
        f"- Angle: {pick.angle}",
        f"- Conviction: {pick.conviction} — {pick.conviction_reason}",
        "",
        "SEASON CONTEXT:",
    ]

    season_row = season_baseline.filter(pl.col("pitcher") == app.pitcher_id)
    if season_row.is_empty():
        lines.append("- no season baseline available")
    else:
        row = season_row.sort("season", descending=True).head(1).row(0, named=True)
        lines.append(
            f"- Season ({row['n_pitches']} pitches): "
            f"P+ {row['P+']:.0f}, S+ {row['S+']:.0f}, L+ {row['L+']:.0f}"
        )
        if season_velo is not None:
            lines.append(f"- Season avg fastball velocity: {season_velo:.1f} mph")
        types = type_baseline.filter(pl.col("pitcher") == app.pitcher_id)
        if not types.is_empty():
            max_season = types["season"].max()
            types = types.filter(pl.col("season") == max_season)
            for trow in types.sort("usage_pct", descending=True).iter_rows(named=True):
                lines.append(
                    f"- {trow['pitch_type']}: {trow['usage_pct']:.1f}% usage, "
                    f"S+ {trow['S+']:.0f}, L+ {trow['L+']:.0f}"
                )
    return "\n".join(lines)


# ── Per-pick writers ────────────────────────────────────────────────


_DIGEST_WRITER_BASE = """\
You write one short item for a data-driven baseball morning digest.

INPUT: a cue package for one pitcher's recent appearance — fired
scouting signals, the editor's framing (category, angle, conviction),
and season context.

CONTRACT:
- Lead with the editor's angle. It is the story; do not bury it.
- Ground every claim in the cue's numbers. Do not invent statistics.
- Scale your tone to the stated conviction: a 'low' conviction story
  is framed as something to monitor, not a breakout.
- Close with one sentence on what to watch in the next outing.
- 150-250 words. No headline; prose only — the document supplies
  headings.
"""


def _build_writer_prompt(persona: Persona) -> str:
    """Digest writer system prompt with the persona voice overlay."""
    return _DIGEST_WRITER_BASE + "\nVOICE:\n" + persona.overlay


def _fallback_summary(pick: CurationPick, cue: str) -> str:
    """Deterministic stand-in when a writer call fails."""
    return (
        f"*[summary unavailable — writer call failed; cue data follows]*\n\n"
        f"**Angle:** {pick.angle}\n"
        f"**Conviction:** {pick.conviction} — {pick.conviction_reason}\n\n"
        f"```\n{cue}\n```"
    )


async def write_pick_summaries(
    picks: list[CurationPick],
    cues: dict[int, str],
    appearances: dict[int, ScoredAppearance],
    *,
    provider: str,
    persona: Persona,
    tracker: object | None = None,
    _model_override: object = None,
) -> dict[int, str]:
    """Write all pick summaries concurrently. Failures degrade to fallback.

    Returns:
        Mapping of pitcher_id to summary text (written or fallback).
    """
    agent: Agent[None, str] = Agent(
        PROVIDERS[provider],
        output_type=str,
        system_prompt=_build_writer_prompt(persona),
        model_settings=ModelSettings(
            temperature=_WRITER_TEMPERATURE, max_tokens=_WRITER_MAX_TOKENS,
        ),
        retries=3,
        defer_model_check=True,
    )

    async def _write_one(pick: CurationPick) -> tuple[int, str]:
        name = appearances[pick.pitcher_id].pitcher_name
        kwargs: dict = {"user_prompt": cues[pick.pitcher_id]}
        if _model_override is not None:
            kwargs["model"] = _model_override
        try:
            result = await agent.run(**kwargs)
        except Exception:
            log.error("Writer failed for %s; using fallback.", name, exc_info=True)
            return pick.pitcher_id, _fallback_summary(pick, cues[pick.pitcher_id])
        if tracker is not None:
            usage = result.usage()
            tracker.record(  # type: ignore[attr-defined]
                PROVIDERS[provider],
                usage.request_tokens or 0,
                usage.response_tokens or 0,
                stage=f"writer:{name}",
            )
        return pick.pitcher_id, result.output

    results = await asyncio.gather(*(_write_one(p) for p in picks))
    return dict(results)


# ── Assembly ────────────────────────────────────────────────────────


_CATEGORY_BADGES = {
    "clean_breakout": "CLEAN BREAKOUT",
    "lab_project": "LAB PROJECT",
    "identity_crisis": "IDENTITY CRISIS",
    "red_flag": "RED FLAG",
}


def render_full_board(board: list[ScoredAppearance]) -> str:
    """Deterministic listing of every scored appearance, grouped by role."""
    lines = ["## The Full Board", ""]
    for label, role in (("### Starters", "SP"), ("### Relievers", "RP")):
        group = sorted(
            (a for a in board if a.role == role),
            key=lambda a: a.score, reverse=True,
        )
        lines.append(label)
        if not group:
            lines.append("*(none scored)*")
        for a in group:
            lines.append(
                f"- **{a.pitcher_name}** ({a.score:.1f}) — "
                f"{a.game_date}, {a.n_pitches} pitches"
            )
            for s in a.signals:
                lines.append(f"  - `{s.name}`: {s.detail}")
        lines.append("")
    return "\n".join(lines)


def assemble_digest(
    *,
    slate: CurationSlate,
    summaries: dict[int, str],
    appearances: dict[int, ScoredAppearance],
    board: list[ScoredAppearance],
    game_date: date,
    cost_block: str,
) -> str:
    """Render the final digest document."""

    def _section(title: str, picks: list[CurationPick]) -> list[str]:
        lines = [f"## {title}", ""]
        if not picks:
            lines += ["*(no picks today)*", ""]
        for pick in picks:
            name = appearances[pick.pitcher_id].pitcher_name
            badge = _CATEGORY_BADGES[pick.category]
            lines += [
                f"### {name} — `{pick.category}` [{badge}]",
                "",
                summaries[pick.pitcher_id],
                "",
            ]
        return lines

    parts = [f"# Morning Digest — {game_date}", ""]
    parts += _section("Starters", slate.starters)
    parts += _section("Relievers", slate.relievers)
    parts.append(render_full_board(board))
    parts += ["", cost_block]
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_digest.py -q`
Expected: all PASS. Known wobble: if `TestModel(custom_output_text=...)` is not the right kwarg name in the installed pydantic-ai, check with `uv run python -c "from pydantic_ai.models.test import TestModel; help(TestModel)" | head -30` — the parameter that fixes plain-text output is what you want.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/digest.py tests/test_digest.py
git commit -m "feat(digest): Add story cues, per-pick writers, and assembly" \
  -m "Deterministic cue packages (signals + editorial angle + season
context) feed concurrent persona-voiced writer calls; failures degrade
to a marked cue rendering. The assembler renders Starters/Relievers
sections, the deterministic Full Board, and the cost footer.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Orchestration (`morning.py`)

**Files:**
- Create: `src/pitcher_narratives/morning.py`
- Test: `tests/test_morning.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_morning.py`:

```python
"""Tests for morning-run orchestration: artifacts, quiet days."""

import json
from datetime import date

import polars as pl
from pydantic_ai.models.test import TestModel

from pitcher_narratives import morning
from pitcher_narratives.scout import ScoredAppearance, Signal


def _app(pid: int, role: str) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"Pitcher {pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=80, score=5.0,
        role=role,
        signals=[Signal("velo_delta", 3.0, "+2.1 mph vs season")],
    )


def _patch_data(monkeypatch):
    """Stub all data-loading seams in morning.py."""
    monkeypatch.setattr(
        morning, "scout_appearances",
        lambda **kw: [_app(1, "SP"), _app(2, "RP")],
    )
    season = pl.DataFrame({
        "pitcher": [1, 2], "season": [2026, 2026], "n_pitches": [900, 400],
        "P+": [104.0, 99.0], "S+": [112.0, 105.0], "L+": [96.0, 101.0],
    })
    types = pl.DataFrame({
        "pitcher": [1], "season": [2026], "pitch_type": ["FF"],
        "n_pitches": [500], "S+": [115.0], "L+": [98.0], "usage_pct": [55.6],
    })
    monkeypatch.setattr(morning, "_load_baselines", lambda: (season, types, {}))


def _selector_model():
    return TestModel(custom_output_args={
        "starters": [{
            "pitcher_id": 1, "category": "clean_breakout",
            "angle": "Velo spike", "conviction": "medium",
            "conviction_reason": "Shape agrees.",
        }],
        "relievers": [{
            "pitcher_id": 2, "category": "red_flag",
            "angle": "Suspicious spike", "conviction": "low",
            "conviction_reason": "Single game.",
        }],
    })


def test_run_morning_writes_all_artifacts(tmp_path, monkeypatch):
    _patch_data(monkeypatch)
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(custom_output_text="A summary."),
    )
    assert run_dir == tmp_path / "2026-06-10"
    digest = (run_dir / "digest.md").read_text()
    assert digest.startswith("# Morning Digest — 2026-06-10")
    assert "A summary." in digest
    assert "## The Full Board" in digest
    assert "Run cost" in digest

    slate = json.loads((run_dir / "slate.json").read_text())
    assert slate["game_date"] == "2026-06-10"
    assert slate["picks"]["starters"][0]["pitcher_id"] == 1
    assert slate["names"]["1"] == "Pitcher 1"

    assert "STARTERS" in (run_dir / "briefing.md").read_text()
    usage = json.loads((run_dir / "usage.json").read_text())
    assert any(rec["stage"] == "selector" for rec in usage)


def test_run_morning_quiet_day_returns_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(morning, "scout_appearances", lambda **kw: [])
    result = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
    )
    assert result is None
    assert not list(tmp_path.iterdir())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_morning.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pitcher_narratives.morning'`

- [ ] **Step 3: Implement `morning.py`**

Create `src/pitcher_narratives/morning.py`:

```python
"""Morning editorial run orchestration.

scout -> selector -> cue builder -> concurrent writers -> assembler,
with artifacts written to <out_root>/<game-date>/: digest.md,
slate.json, briefing.md, usage.json. See
docs/superpowers/specs/2026-06-12-morning-run-design.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import polars as pl

from pitcher_narratives.costs import UsageTracker
from pitcher_narratives.curator import build_selector_briefing, select_slate
from pitcher_narratives.data import (
    compute_pitch_type_baseline,
    compute_season_baseline,
    load_full_agg,
)
from pitcher_narratives.digest import (
    assemble_digest,
    build_story_cue,
    write_pick_summaries,
)
from pitcher_narratives.personas import PERSONAS
from pitcher_narratives.scout import scout_appearances, _compute_velo_baselines

__all__ = ["run_morning"]

log = logging.getLogger("pitcher_narratives.morning")


def _load_baselines() -> tuple[pl.DataFrame, pl.DataFrame, dict[int, float]]:
    """Season + pitch-type baselines and per-pitcher season fastball velo."""
    season_df = load_full_agg("pitcher").filter(pl.col("level") == "MLB")
    type_df = load_full_agg("pitcher_type").filter(pl.col("level") == "MLB")
    season_baseline = compute_season_baseline(season_df)
    type_baseline = compute_pitch_type_baseline(type_df)

    velo = _compute_velo_baselines()
    season_velo: dict[int, float] = {}
    if not velo.is_empty():
        per_pitcher = velo.group_by("pitcher").agg(
            pl.col("season_velo").last(),
        )
        season_velo = {
            row["pitcher"]: row["season_velo"]
            for row in per_pitcher.iter_rows(named=True)
        }
    return season_baseline, type_baseline, season_velo


def run_morning(
    *,
    window_days: int,
    top_n: int,
    min_pitches: int,
    provider: str,
    persona_id: str,
    out_root: Path,
    _selector_override: object = None,
    _writer_override: object = None,
) -> Path | None:
    """Run the full morning workflow. Returns the run dir, or None on a quiet day."""
    started = time.monotonic()
    tracker = UsageTracker()
    persona = PERSONAS[persona_id]

    # ── Scout ─────────────────────────────────────────────────────
    log.info("Scouting appearances...")
    candidates = scout_appearances(
        window_days=window_days, top_n=top_n, min_pitches=min_pitches,
    )
    if not candidates:
        print("No interesting appearances found — quiet day, no digest.")
        return None
    game_date = max(c.game_date for c in candidates)
    appearances = {c.pitcher_id: c for c in candidates}

    # ── Select ────────────────────────────────────────────────────
    log.info("Selecting the slate from %d candidates...", len(candidates))
    briefing = build_selector_briefing(candidates)
    slate = select_slate(
        candidates, provider=provider, tracker=tracker,
        _model_override=_selector_override,
    )
    picks = [*slate.starters, *slate.relievers]
    log.info("Slate: %d starters, %d relievers.",
             len(slate.starters), len(slate.relievers))

    # ── Cues ──────────────────────────────────────────────────────
    season_baseline, type_baseline, season_velo = _load_baselines()
    cues = {
        p.pitcher_id: build_story_cue(
            appearances[p.pitcher_id], p,
            season_baseline=season_baseline,
            type_baseline=type_baseline,
            season_velo=season_velo.get(p.pitcher_id),
        )
        for p in picks
    }

    # ── Write ─────────────────────────────────────────────────────
    log.info("Writing %d summaries...", len(picks))
    summaries = asyncio.run(write_pick_summaries(
        picks, cues, appearances, provider=provider, persona=persona,
        tracker=tracker, _model_override=_writer_override,
    ))

    # ── Assemble + persist ────────────────────────────────────────
    wall_s = time.monotonic() - started
    cost_block = tracker.render_cost_block(wall_s=wall_s)
    digest = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=candidates, game_date=game_date, cost_block=cost_block,
    )

    run_dir = out_root / str(game_date)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "digest.md").write_text(digest)
    (run_dir / "briefing.md").write_text(briefing)
    (run_dir / "slate.json").write_text(json.dumps(
        {
            "game_date": str(game_date),
            "picks": slate.model_dump(),
            "names": {
                str(p.pitcher_id): appearances[p.pitcher_id].pitcher_name
                for p in picks
            },
        },
        indent=2,
    ))
    (run_dir / "usage.json").write_text(json.dumps(tracker.to_json(), indent=2))

    print(digest)
    return run_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_morning.py -q`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/morning.py tests/test_morning.py
git commit -m "feat(morning): Add morning-run orchestration and artifacts" \
  -m "scout -> selector -> cues -> concurrent writers -> digest, with
digest.md, slate.json, briefing.md, and usage.json written to a
game-date run directory. Quiet days exit cleanly with no artifacts.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: CLI subcommands (`cli.py`)

**Files:**
- Modify: `src/pitcher_narratives/cli.py`
- Test: `tests/test_cli.py` (modify existing parse tests; add subcommand tests)

**Breaking change (approved in spec):** bare `pitcher-narratives -p ...` stops working; the report flags move under `pitcher-narratives report`.

- [ ] **Step 1: Read `tests/test_cli.py` and list every test that calls `parse_args`**

Run: `grep -n "parse_args\|sys, .argv" tests/test_cli.py | head -40`

Every `monkeypatch.setattr(sys, "argv", ["cli", ...])` list gains `"report"` as the second element (e.g. `["cli", "report", "-p", "123"]`). Do this mechanically across the file. Subprocess-based tests that invoke the console script get the same treatment.

- [ ] **Step 2: Add failing subcommand tests**

Append to `tests/test_cli.py`:

```python
# ── Subcommand routing ──────────────────────────────────────────────


def test_bare_invocation_errors(monkeypatch, capsys):
    """Without a subcommand, argparse exits with a usage error."""
    import pytest

    monkeypatch.setattr(sys, "argv", ["cli"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_report_subcommand_parses(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "report", "-p", "123"])
    args = parse_args()
    assert args.command == "report"
    assert args.pitcher == 123
    assert args.window == 30


def test_morning_subcommand_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "morning"])
    args = parse_args()
    assert args.command == "morning"
    assert args.window == 1
    assert args.candidates == 25
    assert args.min_pitches == 20
    assert args.provider == "gemini"
    assert args.persona == "scout"
    assert args.out == "morning-runs"
```

- [ ] **Step 3: Run to verify the new tests fail**

Run: `uv run pytest tests/test_cli.py -q`
Expected: new tests FAIL (`AttributeError: ... no attribute 'command'` or SystemExit mismatch); pre-edit tests updated in Step 1 also FAIL until the implementation lands. That's expected — proceed.

- [ ] **Step 4: Restructure `cli.py` with subparsers**

In `src/pitcher_narratives/cli.py`, replace `parse_args()` with a subparser version. All existing `parser.add_argument(...)` calls for the report flags move verbatim onto the `report` subparser:

```python
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments (subcommands: report, morning)."""
    parser = argparse.ArgumentParser(
        description="Pitcher scouting reports and morning digests from Statcast data",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Generate one pitcher's scouting report")
    # Note: required=False so `--list-personas` works standalone.
    # main() re-asserts that -p is present when --list-personas is not used.
    report.add_argument("-p", "--pitcher", type=int, required=False, help="MLB pitcher ID (e.g., 592155)")
    # ... move EVERY existing report argument here verbatim:
    # -w/--window (default 30), -v/--verbose, --print-prompts,
    # --provider, --thinking, --persona, --list-personas

    morning = sub.add_parser("morning", help="Scout, select, and write the morning digest")
    morning.add_argument("-w", "--window", type=int, default=1,
                         help="Days to scan back from the most recent game date (default: 1)")
    morning.add_argument("--candidates", type=int, default=25,
                         help="Scout candidates per role fed to the selector (default: 25)")
    morning.add_argument("--min-pitches", type=int, default=20,
                         help="Minimum pitches for an appearance to be scored (default: 20)")
    morning.add_argument("--provider", choices=["gemini", "claude"], default="gemini",
                         help="LLM provider (default: gemini)")
    morning.add_argument("--persona", type=str.lower, choices=sorted(PERSONAS.keys()),
                         default="scout", help="Writer persona (default: scout)")
    morning.add_argument("--out", default="morning-runs",
                         help="Output directory root (default: morning-runs)")

    return parser.parse_args()
```

Then split `main()`:

```python
def main() -> None:
    """Entry point: dispatch to the report or morning subcommand."""
    load_dotenv()
    args = parse_args()
    if args.command == "morning":
        _run_morning_command(args)
    else:
        _run_report_command(args)


def _run_report_command(args: argparse.Namespace) -> None:
    """Generate one pitcher's report (the pre-subcommand behavior)."""
    # ... the ENTIRE existing body of main() after parse_args(),
    # moved verbatim (the --list-personas short-circuit, the -p
    # required check, setup_logging, data load, pipeline call).


def _run_morning_command(args: argparse.Namespace) -> None:
    """Run the morning editorial workflow."""
    env_var = API_KEYS[args.provider]
    if not os.environ.get(env_var):
        print(f"Error: {env_var} not set.", file=sys.stderr)
        sys.exit(1)
    setup_logging()

    from pathlib import Path

    from pitcher_narratives.morning import run_morning

    run_dir = run_morning(
        window_days=args.window,
        top_n=args.candidates,
        min_pitches=args.min_pitches,
        provider=args.provider,
        persona_id=args.persona,
        out_root=Path(args.out),
    )
    if run_dir is not None:
        print(f"\nRun artifacts: {run_dir}", file=sys.stderr)
```

(`os` and `API_KEYS` are already imported at module level in cli.py.)

- [ ] **Step 5: Run the full CLI test files**

Run: `uv run pytest tests/test_cli.py -q`
Expected: all PASS (including the updated pre-existing tests).

- [ ] **Step 6: Manual smoke test of help output**

Run: `uv run pitcher-narratives --help && uv run pitcher-narratives morning --help`
Expected: top-level help lists `report` and `morning`; morning help shows the six flags with defaults.

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat(cli)!: Restructure into report and morning subcommands" \
  -m "pitcher-narratives gains subcommands: 'report' (the existing
single-pitcher flags, moved verbatim) and 'morning' (the editorial
digest run).

BREAKING CHANGE: bare 'pitcher-narratives -p ...' no longer works;
use 'pitcher-narratives report -p ...'.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Docs + full verification

**Files:**
- Modify: `README.md` (usage section)

- [ ] **Step 1: Update README usage**

Find the usage/CLI section (`grep -n "pitcher-narratives\|Usage" README.md | head`) and:
1. Update every `pitcher-narratives -p ...` example to `pitcher-narratives report -p ...`.
2. Add a morning-run subsection after the report examples:

```markdown
### Morning digest

Scout the most recent games, have an LLM editor select up to 10
starters and 10 relievers, and write a tailored summary per pick:

​```bash
uv run pitcher-narratives morning                 # most recent game date
uv run pitcher-narratives morning -w 3 --provider claude --persona scout
​```

Artifacts land in `morning-runs/<game-date>/`: `digest.md` (also printed
to stdout, with a run-cost footer), `slate.json` (the structured picks),
`briefing.md` (what the selector saw), and `usage.json` (per-call token
records). Quiet days (no scored appearances) exit cleanly without
writing anything.
```

(Remove the zero-width characters around the inner code fence when pasting.)

- [ ] **Step 2: Full suite**

Run: `uv run pytest -q --ignore=tests/test_analyst.py --ignore=tests/test_engine.py`
Expected: all PASS. (`test_analyst.py` has a pre-existing collection error and `test_engine.py` has 6 pre-existing data-dependent failures — both broken on main before this work; do not fix them here.)

- [ ] **Step 3: Live smoke test (requires GEMINI_API_KEY in .env)**

Run: `uv run pitcher-narratives morning --candidates 5`
Expected: scout table activity in stderr, then a digest on stdout ending with the `── Run cost ──` block, and a `morning-runs/<date>/` directory containing the four artifacts. If no API key is configured, skip this step and note it in the final report.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): Document the morning subcommand and report rename" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review Notes (already applied)

- **Spec coverage:** costs (Task 1), role classification incl. opener edge (Task 2), per-role scouting (Task 3), structured selector with ModelRetry + thin-day acceptance + `--curate` repoint + prose-path deletion (Task 4), cues/writers/fallback/Full Board/assembly (Task 5), orchestration + 4 artifacts + game-date dir + quiet day (Task 6), subcommands + breaking change (Task 7), README (Task 8). Out-of-scope items from the spec have no tasks, as intended.
- **Type consistency:** `ScoredAppearance.role` (Task 3) is used by Tasks 4-6; `UsageTracker.record(model, in, out, *, stage)` (Task 1) matches call sites in Tasks 4-6; `CurationPick`/`CurationSlate` field names match between Tasks 4, 5, 6.
- **Known API wobbles called out inline:** pydantic-ai output-validator signature (Task 4), `TestModel` kwargs (Tasks 4-6), retry-exhaustion exception type (Task 4). These are verify-and-adjust steps, not placeholders.
