# Board & Category Unification (WS1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the curation categories a single source of truth, fold the redundant `pitcher-scout` binary into `pitcher-narratives scoreboard` (preserving all its documented flags), so category metadata and board rendering live in one place.

**Architecture:** Introduce a `Category` registry in `curator.py` (the owner of the category `Literal`). `digest.py` renders from that registry instead of three private dicts, and grows a fixed-width table renderer + a slate renderer. The `scoreboard` subcommand absorbs `pitcher-scout`'s capabilities via a `--format {table,md,json}` flag plus `--top`/`--min-score`/`-v`/`--curate`/`--provider`; then `scout_cli.py`, its `pyproject.toml` script entry, and its test file are deleted.

**Tech Stack:** Python 3.14, pydantic v2, argparse, pytest, `uv`.

## Global Constraints

- Python **3.14+**; run everything via `uv run` (e.g. `uv run pytest`).
- Tests in a worktree may need `PITCHER_NARRATIVES_DATA_DIR` pointed at the original repo for data-backed tests; **all tests in this plan are pure or monkeypatched and need no data files.**
- `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Use Pydantic/`@dataclass(frozen=True)` models for structured data, not dicts.
- No bare `except:` — catch specific exception types.
- Category ids are fixed: `clean_breakout, command_breakout, lab_project, identity_crisis, velo_drop, red_flag` (in that display order).
- Branch: `worktree-report-cleanup` (already checked out — safe to commit).

---

### Task 1: Category registry in `curator.py`

**Files:**
- Modify: `src/pitcher_narratives/curator.py` (add after `CurationSlate`, ~line 76; extend `__all__` ~line 23)
- Test: `tests/test_curator.py`

**Interfaces:**
- Produces:
  - `class Category` — `@dataclass(frozen=True)` with fields `id: str`, `order: int`, `section_title: str`, `badge: str`.
  - `CATEGORIES: tuple[Category, ...]` — ordered, one per category id.
  - `CATEGORY_BY_ID: dict[str, Category]` — lookup by id.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_curator.py`:

```python
def test_category_registry_matches_literal():
    """The Category registry must exactly cover CurationPick.category's Literal."""
    from typing import get_args

    from pitcher_narratives.curator import CATEGORY_BY_ID, CurationPick

    declared = set(get_args(CurationPick.model_fields["category"].annotation))
    assert set(CATEGORY_BY_ID) == declared


def test_category_registry_order_and_labels():
    from pitcher_narratives.curator import CATEGORIES

    assert [c.id for c in CATEGORIES] == [
        "clean_breakout", "command_breakout", "lab_project",
        "identity_crisis", "velo_drop", "red_flag",
    ]
    assert [c.order for c in CATEGORIES] == [0, 1, 2, 3, 4, 5]
    labels = {c.id: (c.section_title, c.badge) for c in CATEGORIES}
    assert labels["clean_breakout"] == ("Clean Breakouts", "CLEAN BREAKOUT")
    assert labels["velo_drop"] == ("Velocity Drops", "VELO DROP")
    assert all(c.section_title and c.badge for c in CATEGORIES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_curator.py::test_category_registry_matches_literal tests/test_curator.py::test_category_registry_order_and_labels -q`
Expected: FAIL with `ImportError: cannot import name 'CATEGORY_BY_ID'`.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/curator.py`, change the import line (currently `from typing import Literal`) to:

```python
from dataclasses import dataclass
from typing import Literal, get_args
```

Add these entries to `__all__` (keep alphabetical grouping loose — match the file):

```python
__all__ = [
    "CATEGORIES",
    "CATEGORY_BY_ID",
    "Category",
    "CurationPick",
    "CurationSlate",
    "build_selector_briefing",
    "select_slate",
    "select_slate_async",
]
```

Immediately after the `CurationSlate` class (after its `_validate` method, ~line 76), insert:

```python
@dataclass(frozen=True)
class Category:
    """Display metadata for one curation category — the single source of truth
    for ordering and labels across the digest and scoreboard renderers."""

    id: str
    order: int
    section_title: str
    badge: str


CATEGORIES: tuple[Category, ...] = (
    Category("clean_breakout", 0, "Clean Breakouts", "CLEAN BREAKOUT"),
    Category("command_breakout", 1, "Command Breakouts", "COMMAND BREAKOUT"),
    Category("lab_project", 2, "Lab Projects", "LAB PROJECT"),
    Category("identity_crisis", 3, "Identity Crises", "IDENTITY CRISIS"),
    Category("velo_drop", 4, "Velocity Drops", "VELO DROP"),
    Category("red_flag", 5, "Red Flags", "RED FLAG"),
)

CATEGORY_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}

# Import-time invariant: the registry must exactly cover the CurationPick
# category Literal (mirrors the persona/mode registry checks in personas.py).
_declared_category_ids = set(get_args(CurationPick.model_fields["category"].annotation))
if set(CATEGORY_BY_ID) != _declared_category_ids:
    raise ValueError(
        f"Category registry {set(CATEGORY_BY_ID)} out of sync with "
        f"CurationPick.category Literal {_declared_category_ids}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_curator.py -q`
Expected: PASS (all curator tests, including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/curator.py tests/test_curator.py
git commit -m "feat(curator): add Category registry as single source of truth"
```

---

### Task 2: `digest.py` renders from the registry

**Files:**
- Modify: `src/pitcher_narratives/digest.py` (imports ~line 14; delete `_CATEGORY_BADGES`/`_CATEGORY_ORDER`/`_CATEGORY_SECTION_TITLES` lines 29-49; rewrite `_section` + grouping in `assemble_digest` lines 127-150)
- Test: `tests/test_digest.py`

**Interfaces:**
- Consumes: `CATEGORIES` from Task 1.
- Produces: unchanged `assemble_digest(...)` output; `digest` module no longer defines `_CATEGORY_*` dicts.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_digest.py`:

```python
def test_digest_has_no_local_category_dicts():
    """Category metadata lives only in curator; digest must not redefine it."""
    import pitcher_narratives.digest as d

    assert not hasattr(d, "_CATEGORY_BADGES")
    assert not hasattr(d, "_CATEGORY_ORDER")
    assert not hasattr(d, "_CATEGORY_SECTION_TITLES")


def test_digest_badge_comes_from_registry():
    from pitcher_narratives.curator import CATEGORY_BY_ID

    slate = CurationSlate(picks=[_pick(1)])
    out = assemble_digest(
        slate=slate, summaries={1: "s."}, appearances={1: _app(1)},
        board=[_app(1)], game_date=date(2026, 6, 10), cost_block="c",
    )
    cat = CATEGORY_BY_ID["clean_breakout"]
    assert f"## {cat.section_title}" in out
    assert f"[{cat.badge}]" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_digest.py::test_digest_has_no_local_category_dicts -q`
Expected: FAIL — `_CATEGORY_BADGES` still exists as a module attribute.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/digest.py`, change the curator import (line 14) to:

```python
from pitcher_narratives.curator import CATEGORIES, CurationPick, CurationSlate
```

Delete `_CATEGORY_BADGES` (29-36), `_CATEGORY_ORDER` (38-41), and `_CATEGORY_SECTION_TITLES` (42-49). Keep `_CONVICTION_RANK` (line 50).

Replace the `_section` helper and the grouping/emit block inside `assemble_digest` (current lines 127-150) with:

```python
    def _section(cat, picks: list[CurationPick]) -> list[str]:
        lines = [f"## {cat.section_title}", ""]
        for pick in _ordered(picks):
            name = appearances[pick.pitcher_id].pitcher_name
            lines += [
                f"### {name} — `{pick.category}` [{cat.badge}]",
                "",
                summaries[pick.pitcher_id],
                "",
            ]
        return lines

    by_cat: dict[str, list[CurationPick]] = {c.id: [] for c in CATEGORIES}
    for pick in slate.picks:
        if pick.pitcher_id in summaries:
            by_cat[pick.category].append(pick)

    parts = [f"# Morning Digest — {game_date}", ""]
    for cat in CATEGORIES:
        if by_cat[cat.id]:
            parts += _section(cat, by_cat[cat.id])
```

(The old code's "unknown category" `log.warning` branch is removed — `pick.category` is a validated `Literal` and the registry is invariant-checked, so it is unreachable.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_digest.py -q`
Expected: PASS (new tests plus all pre-existing digest tests — behavior unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/digest.py tests/test_digest.py
git commit -m "refactor(digest): render categories from curator registry"
```

---

### Task 3: `render_full_board_table` in `digest.py`

**Files:**
- Modify: `src/pitcher_narratives/digest.py` (add function; extend `__all__` line 17-21)
- Test: `tests/test_digest.py`

**Interfaces:**
- Produces: `render_full_board_table(board: list[ScoredAppearance], *, verbose: bool = False) -> str` — fixed-width table string, flat-sorted by score descending. `verbose` adds per-signal detail rows.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_digest.py`:

```python
def test_render_full_board_table_content_and_order():
    from pitcher_narratives.digest import render_full_board_table

    table = render_full_board_table([
        _app(1, "SP", 3.0), _app(2, "RP", 9.0),
    ])
    assert "Score" in table and "Pitcher" in table and "Signals" in table
    # Flat sort by score desc: Pitcher 2 (9.0) before Pitcher 1 (3.0).
    assert table.index("Pitcher 2") < table.index("Pitcher 1")
    assert "velo_delta" in table  # signal name column


def test_render_full_board_table_verbose_adds_detail_rows():
    from pitcher_narratives.digest import render_full_board_table

    plain = render_full_board_table([_app(1, "SP", 5.0)])
    verbose = render_full_board_table([_app(1, "SP", 5.0)], verbose=True)
    assert "+2.1 mph vs season" not in plain
    assert "+2.1 mph vs season" in verbose
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_digest.py::test_render_full_board_table_content_and_order -q`
Expected: FAIL — `cannot import name 'render_full_board_table'`.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/digest.py`, add `"render_full_board_table"` to `__all__`. Add this function after `render_full_board_json` (~line 103):

```python
def render_full_board_table(
    board: list[ScoredAppearance], *, verbose: bool = False
) -> str:
    """Fixed-width table of scored appearances, flat-sorted by score descending.

    ``verbose`` appends an indented detail row per signal (name, weight, detail).
    """
    ranked = sorted(board, key=lambda a: a.score, reverse=True)
    lines = [
        f"{'Score':>5}  {'Pitcher':<25} {'T':>1} {'Role':<4}  "
        f"{'Date':<10}  {'#P':>3}  Signals",
        f"{'─' * 5}  {'─' * 25} {'─':>1} {'─' * 4}  "
        f"{'─' * 10}  {'─' * 3}  {'─' * 40}",
    ]
    for a in ranked:
        signal_names = ", ".join(s.name for s in a.signals)
        lines.append(
            f"{a.score:5.1f}  {a.pitcher_name:<25} {a.throws:>1} {a.role:<4}  "
            f"{a.game_date!s:<10}  {a.n_pitches:>3}  {signal_names}"
        )
        if verbose:
            for s in a.signals:
                lines.append(f"       └─ {s.name} ({s.weight:.1f}): {s.detail}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_digest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/digest.py tests/test_digest.py
git commit -m "feat(digest): add render_full_board_table"
```

---

### Task 4: `render_curation_slate` in `digest.py`

**Files:**
- Modify: `src/pitcher_narratives/digest.py` (add function; extend `__all__`)
- Test: `tests/test_digest.py`

**Interfaces:**
- Consumes: `CATEGORIES` (Task 1), `CurationSlate`/`CurationPick`.
- Produces: `render_curation_slate(slate: CurationSlate, names: dict[int, str]) -> str` — categories in registry order, each under its `badge`, one line per pick (`name (conviction): angle`). Empty categories are skipped.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_digest.py`:

```python
def test_render_curation_slate_groups_in_registry_order():
    from pitcher_narratives.digest import render_curation_slate

    slate = CurationSlate(picks=[
        _pick2(2, "red_flag"),
        _pick2(1, "clean_breakout"),
    ])
    out = render_curation_slate(slate, {1: "Ace", 2: "Setup"})
    # clean_breakout (order 0) badge appears before red_flag (order 5) badge.
    assert out.index("CLEAN BREAKOUT") < out.index("RED FLAG")
    assert "Ace (medium): a" in out
    assert "Setup (medium): a" in out
```

(`_pick2` already exists in `tests/test_digest.py` and builds a `CurationPick` with `angle="a"`, `conviction="medium"`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_digest.py::test_render_curation_slate_groups_in_registry_order -q`
Expected: FAIL — `cannot import name 'render_curation_slate'`.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/digest.py`, add `"render_curation_slate"` to `__all__`. Add after `render_full_board_table`:

```python
def render_curation_slate(slate: CurationSlate, names: dict[int, str]) -> str:
    """Render a selected slate as category-grouped lines for terminal display.

    Categories appear in registry order under their badge; each pick is one
    line: ``<name> (<conviction>): <angle>``. Empty categories are skipped.
    """
    by_cat: dict[str, list[CurationPick]] = {c.id: [] for c in CATEGORIES}
    for pick in slate.picks:
        by_cat[pick.category].append(pick)
    blocks: list[str] = []
    for cat in CATEGORIES:
        picks = by_cat[cat.id]
        if not picks:
            continue
        lines = [cat.badge]
        for pick in picks:
            who = names.get(pick.pitcher_id, pick.pitcher_id)
            lines.append(f"  {who} ({pick.conviction}): {pick.angle}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_digest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/digest.py tests/test_digest.py
git commit -m "feat(digest): add render_curation_slate"
```

---

### Task 5: `scoreboard` absorbs `pitcher-scout`'s capabilities

**Files:**
- Modify: `src/pitcher_narratives/cli.py` (scoreboard `add_argument` block lines 165-191; `_run_scoreboard_command` lines 622-655)
- Test: `tests/test_cli.py` (scoreboard section lines 1070-1172)

**Interfaces:**
- Consumes: `render_full_board_table` (Task 3), `render_curation_slate` (Task 4), `render_full_board`, `render_full_board_json`, `scout_appearances`, `top_per_role`, `select_slate`.
- Produces: `scoreboard` accepts `--format {table,md,json}` (default `md`, replaces `--json`), `-n/--top` (default `0` = no limit), `--min-score` (default `0.0`), `-v/--verbose`, `--curate`, `--provider`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py`, add a Namespace helper just above the scoreboard section (after line 1070's `# ── scoreboard subcommand ──` comment):

```python
def _scoreboard_args(**over):
    import argparse

    base = dict(
        window=1, min_pitches=20, starters_only=False, format="md",
        top=0, min_score=0.0, verbose=False, curate=False, provider="gemini",
    )
    base.update(over)
    return argparse.Namespace(**base)
```

Update the existing scoreboard tests to use it and the new flags. Replace the bodies of the five `_run_scoreboard_command` call sites (lines 1100, 1117, 1132, 1150, 1167) so each uses `_scoreboard_args(...)`:

```python
    # test_scoreboard_prints_full_board
    _run_scoreboard_command(_scoreboard_args())
    # test_scoreboard_starters_only_drops_relievers
    _run_scoreboard_command(_scoreboard_args(starters_only=True))
    # test_scoreboard_quiet_day
    _run_scoreboard_command(_scoreboard_args())
    # test_scoreboard_json_output
    _run_scoreboard_command(_scoreboard_args(format="json"))
    # test_scoreboard_json_empty_is_valid
    _run_scoreboard_command(_scoreboard_args(format="json"))
```

Update `test_scoreboard_parse_defaults` (line 1073) to also assert the new defaults:

```python
def test_scoreboard_parse_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "scoreboard"])
    args = parse_args()
    assert args.command == "scoreboard"
    assert args.window == 1
    assert args.min_pitches == 20
    assert args.starters_only is False
    assert args.format == "md"
    assert args.top == 0
    assert args.min_score == 0.0
    assert args.verbose is False
    assert args.curate is False
    assert args.provider == "gemini"
```

Add these new tests at the end of the scoreboard section:

```python
def test_scoreboard_parse_format_and_curate_flags(monkeypatch):
    monkeypatch.setattr(
        sys, "argv",
        ["main.py", "scoreboard", "--format", "table", "-n", "5",
         "--min-score", "4.0", "-v", "--curate", "--provider", "claude"],
    )
    args = parse_args()
    assert args.format == "table"
    assert args.top == 5
    assert args.min_score == 4.0
    assert args.verbose is True
    assert args.curate is True
    assert args.provider == "claude"


def test_scoreboard_table_format(monkeypatch, capsys):
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0), _scored(2, "Setup RP", "RP", 6.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    _run_scoreboard_command(_scoreboard_args(format="table"))
    out = capsys.readouterr().out
    assert "Score" in out and "Signals" in out
    assert "Ace SP" in out and "Setup RP" in out


def test_scoreboard_min_score_filter(monkeypatch, capsys):
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0), _scored(2, "Weak RP", "RP", 2.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    _run_scoreboard_command(_scoreboard_args(min_score=5.0))
    out = capsys.readouterr().out
    assert "Ace SP" in out
    assert "Weak RP" not in out


def test_scoreboard_curate_prints_slate(monkeypatch, capsys):
    from pitcher_narratives import curator as curator_mod
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command
    from pitcher_narratives.curator import CurationPick, CurationSlate

    board = [_scored(1, "Ace SP", "SP", 12.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    slate = CurationSlate(picks=[CurationPick(
        pitcher_id=1, category="clean_breakout", angle="velo up",
        conviction="high", conviction_reason="shape agrees",
    )])
    monkeypatch.setattr(curator_mod, "select_slate", lambda *a, **k: slate)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    _run_scoreboard_command(_scoreboard_args(curate=True))
    out = capsys.readouterr().out
    assert "CLEAN BREAKOUT" in out
    assert "Ace SP (high): velo up" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k scoreboard -q`
Expected: FAIL — new flags not parsed (`AttributeError: 'Namespace' object has no attribute 'format'` / argparse errors).

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/cli.py`, replace the scoreboard `--json` argument (lines 187-191) with the new flag block:

```python
    scoreboard.add_argument(
        "--format",
        choices=["table", "md", "json"],
        default="md",
        help="Output format: fixed-width table, markdown board, or JSON (default: md)",
    )
    scoreboard.add_argument(
        "-n",
        "--top",
        type=int,
        default=0,
        help="Keep only the top N appearances per role by score (default: 0 = no limit)",
    )
    scoreboard.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Drop appearances below this interest score (default: 0.0 = keep all)",
    )
    scoreboard.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="In table format, show a per-signal detail row under each appearance",
    )
    scoreboard.add_argument(
        "--curate",
        action="store_true",
        help="Run the LLM selector on the board and print the selected slate",
    )
    scoreboard.add_argument(
        "--provider",
        choices=["gemini", "claude"],
        default="gemini",
        help="LLM provider for --curate (default: gemini)",
    )
```

Replace `_run_scoreboard_command` (lines 622-655) with:

```python
def _run_scoreboard_command(args: argparse.Namespace) -> None:
    """Print the scouted full board to stdout — no LLM unless --curate is set."""
    setup_logging()

    # Lazy imports: polars (~90ms) and the scout/digest modules are heavy;
    # importing at call time keeps `pitcher-narratives --help` fast.
    import polars as pl

    from pitcher_narratives.digest import (
        render_curation_slate,
        render_full_board,
        render_full_board_json,
        render_full_board_table,
    )
    from pitcher_narratives.scout import scout_appearances, top_per_role

    try:
        board = scout_appearances(window_days=args.window, min_pitches=args.min_pitches)
    except (ValueError, FileNotFoundError, pl.exceptions.PolarsError, OSError) as exc:
        print(f"Scoreboard failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.starters_only:
        board = [a for a in board if a.role == "SP"]
    if args.top > 0:
        board = top_per_role(board, args.top)
    if args.min_score > 0:
        board = [a for a in board if a.score >= args.min_score]

    # JSON always emits valid output (empty board -> empty appearances list) so
    # downstream consumers can parse stdout unconditionally.
    if args.format == "json":
        print(render_full_board_json(board))
        return

    if not board:
        noun = "starter appearances" if args.starters_only else "appearances"
        print(f"No interesting {noun} found — quiet day.", file=sys.stderr)
        return

    game_date = max(a.game_date for a in board)
    print(f"# Scoreboard — {game_date}\n")
    if args.format == "table":
        print(render_full_board_table(board, verbose=args.verbose))
    else:
        print(render_full_board(board))

    if args.curate:
        env_var = API_KEYS[args.provider]
        if not os.environ.get(env_var):
            print(f"\nError: {env_var} not set.", file=sys.stderr)
            sys.exit(1)
        from pitcher_narratives.curator import select_slate

        print(f"\n{'═' * 72}", file=sys.stderr)
        print("SELECTOR — choosing the slate...", file=sys.stderr)
        print(f"{'═' * 72}\n", file=sys.stderr)
        slate = select_slate(board, provider=args.provider)
        names = {a.pitcher_id: a.pitcher_name for a in board}
        print(render_curation_slate(slate, names))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k scoreboard -q`
Expected: PASS (updated + new scoreboard tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat(scoreboard): absorb pitcher-scout flags (--format/--top/--min-score/-v/--curate)"
```

---

### Task 6: Delete `pitcher-scout` and update docs

**Files:**
- Delete: `src/pitcher_narratives/scout_cli.py`
- Delete: `tests/test_scout_cli.py`
- Modify: `pyproject.toml` (remove `pitcher-scout` script line 20)
- Modify: `README.md` (lines 10-12, 58-63, 183-208)

**Interfaces:**
- Consumes: everything from Tasks 1-5 (scoreboard now covers the deleted binary's use cases).
- Produces: a single console script (`pitcher-narratives`).

- [ ] **Step 1: Confirm nothing in `src/` imports `scout_cli`**

Run: `grep -rn "scout_cli" src/`
Expected: no output (only `tests/test_scout_cli.py` referenced it, and that is being deleted).

- [ ] **Step 2: Delete the files and script entry**

```bash
git rm src/pitcher_narratives/scout_cli.py tests/test_scout_cli.py
```

In `pyproject.toml`, delete the line:

```toml
pitcher-scout = "pitcher_narratives.scout_cli:main"
```

- [ ] **Step 3: Update `README.md`**

Edit line 10-12 — remove the triage-scanner parenthetical:

```markdown
- **One pitcher** — a full scouting capsule for a single arm's recent
  appearances (`pitcher-narratives report`).
```

Edit the CLIs table (lines 58-63) — one entry point, and mention `scoreboard`:

```markdown
The package installs one entry point via `[project.scripts]`:

| Script | Source | Purpose |
|---|---|---|
| `pitcher-narratives` | `pitcher_narratives.cli:main` | `report` (one pitcher), `morning` (daily digest), and `scoreboard` (no-LLM triage) subcommands |
```

Replace the entire `### pitcher-scout` section (lines 183-208) with:

```markdown
### `pitcher-narratives scoreboard`

Cheap pre-filter that scans recent appearances, scores each on a heuristic (no
LLM), and prints the board. Optionally pipes the board to a curator LLM.

| Flag | Default | Notes |
|---|---|---|
| `-w`, `--window` | `1` | Days to scan (`1` = most recent game date only) |
| `--min-pitches` | `20` | Minimum pitches for an appearance to be scored |
| `--starters-only` | off | Restrict the board to starting pitchers (role SP) |
| `--format` | `md` | `table` (fixed-width) \| `md` (markdown board) \| `json` |
| `-n`, `--top` | `0` | Keep only the top N per role by score (`0` = no limit) |
| `--min-score` | `0.0` | Drop appearances below this interest score |
| `-v`, `--verbose` | off | In `table` format, show per-signal detail under each row |
| `--curate` | off | Send the board to the curator LLM and print the slate |
| `--provider` | `gemini` | `gemini` \| `claude` (used for `--curate`) |

```bash
uv run pitcher-narratives scoreboard -w 1 --format table -n 25 --min-score 5.0 -v
```

The heuristic looks for velocity swings, P+/S+/L+ divergences, new or dropped
pitches, usage shifts, development candidates, and reliever workload flags.
Per-pitch-type grade signals (the S+/L+ divergence and "stuff without feel"
checks) require at least a handful of pitches of that type, so a one-off pitch
can't manufacture a phantom signal. See `METHODOLOGY.md` for the full signal
table and weights.
```

- [ ] **Step 4: Verify the full suite is green and the CLI still works**

Run: `uv run pytest -q`
Expected: PASS, with no `test_scout_cli.py` collected.

Run: `uv run pitcher-narratives --help`
Expected: help text listing `report`, `morning`, `scoreboard` subcommands; exit 0.

Run: `grep -rn "pitcher-scout\|scout_cli" src/ tests/ README.md pyproject.toml`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove pitcher-scout, fold triage into scoreboard"
```

---

## Self-Review

**Spec coverage** (`2026-07-05-board-category-unification-design.md`):
- §3.1 one category registry → Task 1; `digest.py` repointed → Task 2. ✅
- §3.2 remove `pitcher-scout`, fold into `scoreboard`, `--format table|md|json` → Tasks 3, 5, 6. ✅
- §3.2 move `_print_table` → `render_full_board_table` → Task 3. ✅
- §3.2 `--curate` via shared registry → Tasks 4, 5. ✅
- §4 migration order → Tasks ordered registry → digest → renderers → CLI → delete. ✅
- §5 testing (`test_curator`, `test_digest`, `test_cli`, remove `test_scout_cli`) → covered. ✅
- §6 open question "keep `--json` shim vs hard-cut" → **hard-cut** to `--format json` (Task 5), consistent with the "remove outright" posture.
- §6 open question "does anyone script `pitcher-scout`" → README documented it (not cron); README updated in Task 6, `docs/daily-runs.md` has no reference (verified).

**Capability preservation note:** README documented `pitcher-scout`'s `-n/--top`, `--min-score`, `-v`, `--curate`, `--provider`. To avoid silently dropping documented features when the binary is removed, Task 5 has `scoreboard` absorb all of them (making it a true superset), rather than only `--format` + `--curate`. This widens WS1 slightly beyond the design spec's literal wording but honors its intent ("`scoreboard` is a strict superset").

**Placeholder scan:** none — every step has concrete code and exact commands.

**Type consistency:** `Category(id, order, section_title, badge)` used identically in Tasks 1-4. `render_full_board_table(board, *, verbose)` and `render_curation_slate(slate, names)` signatures match between definition (Tasks 3-4) and call site (Task 5). Namespace fields in `_scoreboard_args` match the `add_argument` dests in Task 5.
