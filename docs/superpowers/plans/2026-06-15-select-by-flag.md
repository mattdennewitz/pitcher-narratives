# Select-by-Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the morning slate's role-based structure (≤10 starters + ≤10 relievers) with a category-based one — up to 5 picks per editorial category (`clean_breakout`, `lab_project`, `identity_crisis`, `red_flag`), no minimum — plus an anti-clustering nudge in the selector prompt.

**Architecture:** `CurationSlate` becomes a flat `picks: list[CurationPick]` with a validator capping any category at 5 (approach A — `category` stays the single source of truth). The selector briefing flattens (no role buckets), the prompt switches to per-category caps + a variety rule, the digest groups capsules by category, and `morning.py`/`scout_cli.py` iterate the flat list.

**Tech Stack:** Python 3.14, pydantic + pydantic-ai (selector agent with output validators), polars, pytest, uv, ruff.

**Spec:** `docs/superpowers/specs/2026-06-14-select-by-flag-design.md`

---

## Critical Context for the Implementer

### This is a contained behavior change across 4 source files + their tests

Files modified: `curator.py` (schema, prompt, briefing, validator), `morning.py` (iteration + `slate.json`), `digest.py` (category-grouped sections), `scout_cli.py` (`--curate` output). Tests: `test_curator.py`, `test_digest.py`, `test_morning.py`.

### Baseline (capture before starting)

The suite is currently green. The selector/digest/morning tests are the net:

```bash
uv run pytest -q tests/test_curator.py tests/test_digest.py tests/test_morning.py
```

Record the pass count. Every task ends with this (or a subset) passing. Data is fresh (statcast + aggs both through 2026-06-13), so no data-staleness failures.

### The four categories (fixed) and their display

`category ∈ {clean_breakout, lab_project, identity_crisis, red_flag}`. `digest.py` already has `_CATEGORY_BADGES` mapping each to an uppercase badge (`"CLEAN BREAKOUT"`, etc.). Section display order is the editorial hierarchy: **clean_breakout → lab_project → identity_crisis → red_flag**.

### What "no minimum" means

A category with no compelling candidates contributes zero picks and is **omitted** from the digest entirely (no "*(no picks today)*" placeholder). The slate as a whole must still contain at least one pick.

---

## Task 0: Capture the baseline

**Files:** none (verification only)

- [ ] **Step 1: Run the net and record the count**

Run:
```bash
uv run pytest -q tests/test_curator.py tests/test_digest.py tests/test_morning.py 2>&1 | tail -1
```
Expected: a clean `N passed` line. Record N. This is the contract for the rest of the plan.

---

## Task 1: Reshape `CurationSlate` to a flat, category-capped list

**Files:**
- Modify: `src/pitcher_narratives/curator.py`
- Test: `tests/test_curator.py`

- [ ] **Step 1: Write the failing tests**

Replace the three role-shaped slate tests (`test_slate_caps_each_role_at_ten`, `test_slate_must_not_be_empty`, `test_slate_accepts_thin_day`) in `tests/test_curator.py` with these. The `_pick(pid)` helper (returns a dict with `category="clean_breakout"`) is unchanged; add a `_pick_cat` helper that lets a test set the category.

```python
def _pick_cat(pid: int, category: str) -> dict:
    return {**_pick(pid), "category": category}


def test_slate_caps_each_category_at_five():
    """At most 5 picks per category; a 6th in one category is rejected."""
    with pytest.raises(ValidationError):
        CurationSlate(
            picks=[CurationPick(**_pick_cat(i, "lab_project")) for i in range(6)]
        )


def test_slate_allows_five_per_category_across_categories():
    """5 in each of the four categories (20 total, distinct ids) is valid."""
    cats = ["clean_breakout", "lab_project", "identity_crisis", "red_flag"]
    picks = [CurationPick(**_pick_cat(i, cats[i // 5])) for i in range(20)]
    slate = CurationSlate(picks=picks)
    assert len(slate.picks) == 20


def test_slate_must_not_be_empty():
    with pytest.raises(ValidationError):
        CurationSlate(picks=[])


def test_slate_accepts_thin_day():
    slate = CurationSlate(picks=[CurationPick(**_pick(1))])
    assert len(slate.picks) == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_curator.py::test_slate_caps_each_category_at_five -v`
Expected: FAIL — `CurationSlate` has no `picks` field yet (`starters`/`relievers` required).

- [ ] **Step 3: Reshape the schema**

In `src/pitcher_narratives/curator.py`, add `from collections import Counter` to the imports. Replace the `_MAX_PICKS_PER_ROLE = 10` constant and the `CurationSlate` class:

```python
_MAX_PICKS_PER_CATEGORY = 5
```

```python
class CurationSlate(BaseModel):
    """The morning slate: up to 5 picks per category, at least one overall."""

    picks: list[CurationPick] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "CurationSlate":
        if not self.picks:
            raise ValueError("slate must contain at least one pick")
        over = {
            cat: n
            for cat, n in Counter(p.category for p in self.picks).items()
            if n > _MAX_PICKS_PER_CATEGORY
        }
        if over:
            raise ValueError(
                f"Too many picks in categories {over}; "
                f"cap is {_MAX_PICKS_PER_CATEGORY} per category."
            )
        return self
```

`CurationPick` is unchanged. `_MAX_PICKS_PER_ROLE` is deleted.

- [ ] **Step 4: Run to verify the new tests pass**

Run: `uv run pytest -q tests/test_curator.py::test_slate_caps_each_category_at_five tests/test_curator.py::test_slate_allows_five_per_category_across_categories tests/test_curator.py::test_slate_must_not_be_empty tests/test_curator.py::test_slate_accepts_thin_day -v`
Expected: 4 PASS. (Other `test_curator.py` tests still fail — fixed in Task 2.)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/curator.py tests/test_curator.py
git commit -m "feat(curator): cap slate picks per category (flat picks list)"
```

---

## Task 2: Flatten the briefing, update the selector prompt + validator

**Files:**
- Modify: `src/pitcher_narratives/curator.py`
- Test: `tests/test_curator.py`

- [ ] **Step 1: Write/replace the failing tests**

In `tests/test_curator.py`: (a) replace `test_briefing_buckets_by_role` with a flat-briefing test, (b) update `test_select_slate_returns_validated_slate` to the flat output shape, (c) **delete** `test_select_slate_rejects_role_swap` (no role buckets anymore), (d) update the membership + duplicate tests to the flat shape.

```python
def test_briefing_is_flat_not_role_bucketed():
    briefing = build_selector_briefing([_app(1, "SP"), _app(2, "RP")])
    assert "STARTERS" not in briefing
    assert "RELIEVERS" not in briefing
    # both candidates still appear, with role shown inline
    assert "id=1" in briefing and "id=2" in briefing


def test_select_slate_returns_validated_slate():
    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={"picks": [_pick(1), _pick(2)]})
    slate = select_slate(candidates, provider="gemini", _model_override=model)
    assert sorted(p.pitcher_id for p in slate.picks) == [1, 2]


def test_select_slate_rejects_unknown_pitcher_id():
    candidates = [_app(1, "SP")]
    model = TestModel(custom_output_args={"picks": [_pick(999)]})  # not a candidate
    with pytest.raises(Exception):
        select_slate(candidates, provider="gemini", _model_override=model)


def test_select_slate_rejects_duplicate_picks():
    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={"picks": [_pick(1), _pick(1)]})
    with pytest.raises(Exception):
        select_slate(candidates, provider="gemini", _model_override=model)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_curator.py::test_briefing_is_flat_not_role_bucketed -v`
Expected: FAIL — the briefing still emits `STARTERS`/`RELIEVERS` sections.

- [ ] **Step 3: Flatten `build_selector_briefing`**

Replace `build_selector_briefing` in `curator.py`:

```python
def build_selector_briefing(candidates: list[ScoredAppearance]) -> str:
    """Render scored candidates as a single flat, score-ranked briefing."""
    ranked = sorted(candidates, key=lambda r: r.score, reverse=True)
    lines = [f"=== CANDIDATES ({len(ranked)}) ==="]
    if not ranked:
        lines.append("(none)")
    for r in ranked:
        lines.append(
            f"## {r.pitcher_name} (id={r.pitcher_id}, {r.throws}HP, {r.role}) — "
            f"{r.game_date}, {r.n_pitches} pitches, score {r.score:.1f}"
        )
        for s in r.signals:
            lines.append(f"- [{s.name}] {s.detail}")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Update the selector prompt**

Replace `_SELECTOR_PROMPT` in `curator.py` (keep the four category definitions verbatim from the existing prompt; only the framing and RULES change):

```python
_SELECTOR_PROMPT = """\
You are the editor of a data-driven baseball morning report. From the
scored candidate appearances below, select the most compelling stories,
focusing on process over results. Assign each pick exactly one category
and select up to 5 picks PER CATEGORY across the four categories below.

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
- At most 5 picks per category. A category with few compelling
  candidates gets fewer, or none. Never pad with ordinary outings.
- Ignore "good" outings where the data matches the season average.
- Favor variety. Prefer a spread across categories and distinct stories
  over many look-alikes. When several candidates tell the same story
  (e.g. multiple "elite breaking ball, no command" lab projects), keep
  only the most distinctive or highest-conviction few rather than
  filling the cap with duplicates. A shorter, varied slate beats a
  long, repetitive one.
- For each pick: category from the hierarchy above; angle is ONE
  sentence stating the story; conviction scaled to the sample with a
  one-sentence reason. Be pragmatic, not breathless.
- Frame each angle for front offices and data-driven fans — what to
  watch, not what to do.
"""
```

- [ ] **Step 5: Simplify the membership validator**

Replace the `_picks_are_candidates` validator and the `sp_ids`/`rp_ids` setup in `make_selector_agent` (the per-category cap now lives on the schema; the agent validator only checks membership + duplicates against the full candidate set):

```python
    candidate_ids = {r.pitcher_id for r in candidates}

    agent: Agent[None, CurationSlate] = Agent(
        PROVIDERS[provider],
        output_type=CurationSlate,
        system_prompt=_SELECTOR_PROMPT,
        model_settings=make_model_settings(
            provider, "medium", _SELECTOR_TEMPERATURE, max_tokens=_SELECTOR_MAX_TOKENS,
        ),
        retries=3,
        defer_model_check=True,
    )

    @agent.output_validator
    def _picks_are_candidates(output: CurationSlate) -> CurationSlate:
        bad = [p.pitcher_id for p in output.picks if p.pitcher_id not in candidate_ids]
        if bad:
            raise ModelRetry(
                f"Invalid picks — not listed candidates: {bad}. "
                f"Use only the listed pitcher_id values."
            )
        ids = [p.pitcher_id for p in output.picks]
        if len(ids) != len(set(ids)):
            raise ModelRetry(
                "Duplicate pitcher_id picks; select each pitcher at most once."
            )
        return output

    return agent
```

- [ ] **Step 6: Run the full curator suite**

Run: `uv run ruff check src/pitcher_narratives/curator.py && uv run pytest -q tests/test_curator.py -v`
Expected: ruff clean; all `test_curator.py` tests PASS (the deleted role-swap test is gone).

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/curator.py tests/test_curator.py
git commit -m "feat(curator): flat briefing, per-category prompt + anti-clustering nudge"
```

---

## Task 3: Iterate the flat slate in `morning.py` + flat `slate.json`

**Files:**
- Modify: `src/pitcher_narratives/morning.py`
- Test: `tests/test_morning.py`

- [ ] **Step 1: Update the test fixtures + assertions**

In `tests/test_morning.py`: change `_selector_model()` and the two inline selector fixtures (around the `test_run_morning_single_event_loop` and `test_full_board_lists_beyond_candidate_cap` tests) from `{"starters": [...], "relievers": [...]}` to a flat `{"picks": [...]}`. Update the `slate.json` assertion and the `briefing.md` assertion.

`_selector_model()` becomes:
```python
def _selector_model():
    return TestModel(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
            {
                "pitcher_id": 2, "category": "red_flag",
                "angle": "Suspicious spike", "conviction": "low",
                "conviction_reason": "Single game.",
            },
        ],
    })
```

In `test_run_morning_writes_all_artifacts`, change:
```python
    assert slate["picks"]["starters"][0]["pitcher_id"] == 1
```
to:
```python
    assert slate["picks"][0]["pitcher_id"] == 1
```
and change the briefing assertion:
```python
    assert "STARTERS" in (run_dir / "briefing.md").read_text()
```
to:
```python
    assert "CANDIDATES" in (run_dir / "briefing.md").read_text()
```

For the other inline selector fixtures in this file that use `"starters"`/`"relievers"`, convert each to a single `"picks": [ ... ]` list containing the same pick dicts (drop the role keys; keep each pick's existing `category`). Their candidate ids must remain valid candidates in those tests.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_morning.py::test_run_morning_writes_all_artifacts -v`
Expected: FAIL — `morning.py` still references `slate.starters`/`slate.relievers`.

- [ ] **Step 3: Update `morning.py`**

In `src/pitcher_narratives/morning.py`, in `_llm_stages`, replace:
```python
        picks = [*slate.starters, *slate.relievers]
        log.info("Slate: %d starters, %d relievers.",
                 len(slate.starters), len(slate.relievers))
```
with:
```python
        picks = slate.picks
        from collections import Counter
        by_cat = Counter(p.category for p in picks)
        log.info("Slate: %d picks across categories %s.", len(picks), dict(by_cat))
```

And in the `slate.json` block, replace `"picks": slate.model_dump(),` with:
```python
            "picks": slate.model_dump()["picks"],
```
(Serializes the flat list directly so `slate.json["picks"]` is the list of pick dicts, not `{"picks": [...]}`.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run ruff check src/pitcher_narratives/morning.py && uv run pytest -q tests/test_morning.py -v`
Expected: ruff clean; all `test_morning.py` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/morning.py tests/test_morning.py
git commit -m "feat(morning): iterate flat slate.picks; flatten slate.json"
```

---

## Task 4: Group the digest by category in `digest.py`

**Files:**
- Modify: `src/pitcher_narratives/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_digest.py` (it already imports `assemble_digest`, `CurationPick`, `CurationSlate`, and has a `_pick(pid)` CurationPick helper). Add a small builder for picks with a chosen category/conviction and an appearance/summary fixture, then assert category grouping + ordering + omission.

```python
def _pick2(pid: int, category: str, conviction: str = "medium") -> CurationPick:
    return CurationPick(
        pitcher_id=pid, category=category, angle="a", conviction=conviction,
        conviction_reason="r",
    )


def _appearance(pid: int, score: float):
    from datetime import date as _date

    from pitcher_narratives.scout import ScoredAppearance
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"P{pid}", throws="R",
        game_date=_date(2026, 6, 13), game_pk=1, n_pitches=80, score=score, role="RP",
    )


def test_digest_groups_by_category_and_omits_empty():
    slate = CurationSlate(picks=[
        _pick2(1, "red_flag"),
        _pick2(2, "lab_project"),
        _pick2(3, "lab_project"),
    ])
    appearances = {1: _appearance(1, 9.0), 2: _appearance(2, 5.0), 3: _appearance(3, 8.0)}
    summaries = {1: "s1", 2: "s2", 3: "s3"}
    out = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=list(appearances.values()), game_date="2026-06-13", cost_block="cost",
    )
    # category sections present in hierarchy order; clean_breakout / identity_crisis omitted
    assert "## Lab Projects" in out
    assert "## Red Flags" in out
    assert "## Clean Breakouts" not in out
    assert "## Identity Crises" not in out
    assert out.index("## Lab Projects") < out.index("## Red Flags")


def test_digest_orders_within_category_by_conviction_then_score():
    slate = CurationSlate(picks=[
        _pick2(1, "lab_project", "low"),
        _pick2(2, "lab_project", "high"),
        _pick2(3, "lab_project", "high"),
    ])
    # within high-conviction, higher score first => P3 (8.0) before P2 (5.0); P1 (low) last
    appearances = {1: _appearance(1, 9.0), 2: _appearance(2, 5.0), 3: _appearance(3, 8.0)}
    summaries = {1: "s1", 2: "s2", 3: "s3"}
    out = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=list(appearances.values()), game_date="2026-06-13", cost_block="cost",
    )
    assert out.index("### P3") < out.index("### P2") < out.index("### P1")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_digest.py::test_digest_groups_by_category_and_omits_empty -v`
Expected: FAIL — `assemble_digest` still renders `## Starters` / `## Relievers` from `slate.starters`.

- [ ] **Step 3: Rewrite `assemble_digest`**

In `src/pitcher_narratives/digest.py`, add module constants near `_CATEGORY_BADGES`:

```python
_CATEGORY_ORDER = ["clean_breakout", "lab_project", "identity_crisis", "red_flag"]
_CATEGORY_SECTION_TITLES = {
    "clean_breakout": "Clean Breakouts",
    "lab_project": "Lab Projects",
    "identity_crisis": "Identity Crises",
    "red_flag": "Red Flags",
}
_CONVICTION_RANK = {"high": 0, "medium": 1, "low": 2}
```

Replace `assemble_digest`:

```python
def assemble_digest(
    *,
    slate: CurationSlate,
    summaries: dict[int, str],
    appearances: dict[int, ScoredAppearance],
    board: list[ScoredAppearance],
    game_date: date,
    cost_block: str,
) -> str:
    """Render the final digest document, grouped by category."""

    def _ordered(picks: list[CurationPick]) -> list[CurationPick]:
        return sorted(
            picks,
            key=lambda p: (
                _CONVICTION_RANK[p.conviction],
                -appearances[p.pitcher_id].score,
            ),
        )

    def _section(title: str, picks: list[CurationPick]) -> list[str]:
        lines = [f"## {title}", ""]
        for pick in _ordered(picks):
            name = appearances[pick.pitcher_id].pitcher_name
            badge = _CATEGORY_BADGES[pick.category]
            lines += [
                f"### {name} — `{pick.category}` [{badge}]",
                "",
                summaries[pick.pitcher_id],
                "",
            ]
        return lines

    by_cat: dict[str, list[CurationPick]] = {c: [] for c in _CATEGORY_ORDER}
    for pick in slate.picks:
        by_cat[pick.category].append(pick)

    parts = [f"# Morning Digest — {game_date}", ""]
    for cat in _CATEGORY_ORDER:
        if by_cat[cat]:
            parts += _section(_CATEGORY_SECTION_TITLES[cat], by_cat[cat])
    parts.append(render_full_board(board))
    parts += ["", cost_block]
    return "\n".join(parts)
```

`render_full_board` is unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `uv run ruff check src/pitcher_narratives/digest.py && uv run pytest -q tests/test_digest.py -v`
Expected: ruff clean; all `test_digest.py` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/digest.py tests/test_digest.py
git commit -m "feat(digest): group capsules by category, ordered by conviction then score"
```

---

## Task 5: Group the `scout-scout --curate` output by category

**Files:**
- Modify: `src/pitcher_narratives/scout_cli.py`

- [ ] **Step 1: Update the `--curate` print loop**

In `src/pitcher_narratives/scout_cli.py`, replace the slate-printing loop:
```python
        slate = select_slate(results, provider=args.provider)
        names = {r.pitcher_id: r.pitcher_name for r in results}
        for label, picks in (("STARTERS", slate.starters), ("RELIEVERS", slate.relievers)):
            print(f"\n{label}")
            for p in picks:
                print(f"  [{p.category}] {names.get(p.pitcher_id, p.pitcher_id)} "
                      f"({p.conviction}): {p.angle}")
```
with (group by the same hierarchy order; omit empty categories):
```python
        slate = select_slate(results, provider=args.provider)
        names = {r.pitcher_id: r.pitcher_name for r in results}
        order = ["clean_breakout", "lab_project", "identity_crisis", "red_flag"]
        by_cat: dict[str, list] = {c: [] for c in order}
        for p in slate.picks:
            by_cat[p.category].append(p)
        for cat in order:
            picks = by_cat[cat]
            if not picks:
                continue
            print(f"\n{cat.upper().replace('_', ' ')}")
            for p in picks:
                print(f"  {names.get(p.pitcher_id, p.pitcher_id)} "
                      f"({p.conviction}): {p.angle}")
```

- [ ] **Step 2: Verify it imports and the package is clean**

Run:
```bash
uv run ruff check src/pitcher_narratives/scout_cli.py && \
uv run python -c "import pitcher_narratives.scout_cli; print('scout_cli imports OK')"
```
Expected: ruff clean; `scout_cli imports OK`.

- [ ] **Step 3: Commit**

```bash
git add src/pitcher_narratives/scout_cli.py
git commit -m "feat(scout-cli): group --curate output by category"
```

---

## Task 6: Full integration verification

**Files:** none (verification only)

- [ ] **Step 1: No stray references to the old slate shape**

Run:
```bash
grep -rn "slate.starters\|slate.relievers\|_MAX_PICKS_PER_ROLE\|\.starters\b\|\.relievers\b" src/pitcher_narratives/ | grep -v __pycache__
```
Expected: no output (all role-shaped slate access is gone). If anything prints, fix it.

- [ ] **Step 2: Run the full suite**

Run:
```bash
uv run pytest -q 2>&1 | tail -2
```
Expected: same pass count as the pre-change baseline (575 passed), adjusted by the tests added/removed in this plan (net: `test_select_slate_rejects_role_swap` removed; `test_slate_allows_five_per_category_across_categories`, two digest tests added → roughly +2). No failures.

- [ ] **Step 3: Live run — confirm category-grouped digest with the cap respected**

Run:
```bash
uv run pitcher-narratives morning > /tmp/sbf.txt 2>/tmp/sbf_err.txt; echo "exit=$?"
grep -E "^## " /tmp/sbf.txt | grep -v "Full Board"
uv run python -c "
import json
d=json.load(open('morning-runs/2026-06-13/slate.json'))
from collections import Counter
c=Counter(p['category'] for p in d['picks'])
print('category mix:', dict(c))
assert all(n <= 5 for n in c.values()), f'cap violated: {c}'
print('cap respected (<=5 per category)')
"
```
Expected: digest section headers are category names (e.g. `## Lab Projects`, `## Red Flags`), not `## Starters`/`## Relievers`; the category mix shows ≤5 per category. (Costs a real LLM call ~$0.18; requires `GEMINI_API_KEY`.)

- [ ] **Step 4: Final commit (if Step 1–3 produced cleanup edits)**

```bash
git add -A
git commit -m "chore(select-by-flag): integration verification cleanup"
```

---

## Self-Review Checklist

- [ ] `CurationSlate` is a flat `picks` list; the validator rejects >5 per category and an empty slate.
- [ ] The briefing has no `STARTERS`/`RELIEVERS` sections; the selector prompt says "up to 5 per category" and contains the anti-clustering "Favor variety" rule.
- [ ] `make_selector_agent`'s validator checks membership + duplicates against the full candidate set (no role-section check).
- [ ] `morning.py` iterates `slate.picks`; `slate.json["picks"]` is a flat list of pick dicts.
- [ ] `assemble_digest` renders one section per non-empty category in hierarchy order, ordered within by conviction then score; `render_full_board` unchanged.
- [ ] `scout_cli --curate` groups by category.
- [ ] `grep` finds no `slate.starters`/`slate.relievers`/`_MAX_PICKS_PER_ROLE` anywhere in `src/`.
- [ ] Full suite green.

## Out of Scope (do not implement here)

- The per-capsule writer template (the prose-repetition fix) — the only lever in this plan is the selector nudge.
- A configurable cap (`--flag-cap`) — the cap is the constant `5`.
- The raw Full Board (stays role-grouped).
- Scout signal scoring (`scout.py`) — unchanged.
