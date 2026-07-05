# Board & Category Unification (WS1) — Design

**Date:** 2026-07-05
**Status:** Approved design, pending implementation plan
**Topic:** Collapse the duplicated board renderers and category metadata into one source of truth; remove the redundant `pitcher-scout` binary.

---

## 1. Problem

The six curation categories and the scored board are each expressed multiple
times with divergent conventions:

- **Category strings** are canonically a `Literal` on `CurationPick.category`
  (`curator.py:48-53`), and the selector prompt enumerates them a second time
  (`curator.py:82-106`).
- **Order + display labels** are re-declared in `digest.py:38-49`
  (`_CATEGORY_ORDER`, `_CATEGORY_BADGES`, `_CATEGORY_SECTION_TITLES`) and *again*
  in `scout_cli.py:134-145` with an ad-hoc `cat.upper().replace('_', ' ')`
  instead of the shared labels.
- **The board renders three ways:** `render_full_board` (markdown,
  `digest.py:53`), `render_full_board_json` (`digest.py:75`), and
  `scout_cli._print_table` (fixed-width, `scout_cli.py:68`).
- **Two binaries expose the same board.** `pitcher-scout`
  (`pyproject.toml:20` → `scout_cli:main`) and `pitcher-narratives scoreboard`
  (`cli.py:622`, `cli.py:654`) are ~90% the same command; the only real
  difference is table-vs-markdown formatting and the `--curate` path.

Adding a category or renaming a label today means editing 3+ sites, and the two
CLIs can drift.

## 2. Key facts established (with evidence)

- `curator.py` is the natural owner of the category vocabulary — the `Literal`
  lives there (`curator.py:48`) and `_MAX_PICKS_PER_CATEGORY = 5` +
  `CurationSlate` validation already treat categories as a first-class set
  (`curator.py:31`, `curator.py:58-74`).
- `render_full_board` is already **shared** — `scoreboard` calls it
  (`cli.py:655`) and the digest appends it (`digest.py:151`). Only
  `scout_cli._print_table` is a genuinely separate renderer.
- `scout_cli.py`'s scan + `top_per_role` + `--min-score` filtering
  (`scout_cli.py:98-105`) duplicates logic already reachable from `cli.py`'s
  scoreboard path (`cli.py:622-655`), which also has `--starters-only` and
  `--json`. The scoreboard path is the superset.
- `--curate` in `scout_cli.py:119-148` re-implements slate grouping that
  `assemble_digest` already owns via `_CATEGORY_ORDER` (`digest.py:148`).

## 3. Target design

### 3.1 One category registry (in `curator.py`)

Introduce a frozen registry keyed by the existing category ids:

```python
@dataclass(frozen=True)
class Category:
    id: str            # matches the Literal member
    order: int
    section_title: str # "Clean Breakouts"
    badge: str         # "CLEAN BREAKOUT"
    short_label: str   # "Clean breakout" (terminal/table use)

CATEGORIES: tuple[Category, ...]   # ordered; single source of truth
CATEGORY_BY_ID: Mapping[str, Category]
```

- The `CurationPick.category` `Literal` stays (it is the type-level guard); an
  import-time invariant asserts the `Literal` members and `CATEGORIES` ids match,
  mirroring the persona/mode registry checks (`personas.py:747-756`).
- `digest.py` imports `CATEGORIES`/`CATEGORY_BY_ID`; delete `_CATEGORY_ORDER`,
  `_CATEGORY_BADGES`, `_CATEGORY_SECTION_TITLES`.

### 3.2 Remove `pitcher-scout`; fold into `scoreboard`

> **Supersedes a prior decision.** `2026-06-15-narrative-consolidation.md:193`
> weighed and *deferred* this fold, concluding "keeping `pitcher-scout`
> standalone for triage is legitimate." The 2026-07-05 decision reverses that:
> the ~90% overlap with `scoreboard` (which is a strict superset — it has
> `--starters-only` and `--json`) outweighs the standalone-triage convenience.
> Dependency-clean: no `src/` module imports `scout_cli`; only
> `tests/test_scout_cli.py:14` does.

Per the 2026-07-05 decision (**remove outright, no alias**):

- Delete `pyproject.toml:20` (`pitcher-scout` entry) and `scout_cli.py`'s CLI
  (`parse_args`, `_print_table`, `main`). The reusable scan functions it calls
  (`scout_appearances`, `top_per_role`) live in `scout.py` and are unaffected.
- Add `scoreboard --format {table,md,json}` (default `md`):
  - `md` → existing `render_full_board`.
  - `json` → existing `render_full_board_json` (replaces today's `--json`; keep
    `--json` as a hidden shim → `--format json` for one release *only if* trivial,
    else drop).
  - `table` → a `render_full_board_table` renderer moved from
    `scout_cli._print_table` into `digest.py`, using `short_label` from the
    registry for any category column.
- The `--curate` capability moves to `scoreboard --curate`, grouping via the
  shared registry (reuse the `assemble_digest` grouping helper rather than the
  old ad-hoc block).

### 3.3 Result

- One category truth (`curator.CATEGORIES`).
- One board data path; format is a flag.
- One binary (`pitcher-narratives`).

## 4. Migration / plan sketch

1. Add `Category` registry + invariant in `curator.py` (+ `test_curator`).
2. Repoint `digest.py` at the registry; delete local dicts (+ `test_digest`).
3. Move `_print_table` → `render_full_board_table` in `digest.py`.
4. Add `--format` (and `--curate`) to the `scoreboard` subcommand in `cli.py`.
5. Delete `scout_cli.py` + its `pyproject.toml` script entry + `test_scout_cli.py`
   (port any still-relevant assertions onto `test_cli` scoreboard cases).

## 5. Testing

- `test_curator`: registry ↔ `Literal` invariant; ordering.
- `test_digest`: unchanged markdown/JSON output; new table renderer golden.
- `test_cli`: `scoreboard --format table|md|json`, `--curate`, `--starters-only`.
- Remove `test_scout_cli.py`.

## 6. Open questions

- Keep `scoreboard --json` as a back-compat shim, or hard-cut to
  `--format json`? (Leaning hard-cut, consistent with the "remove outright"
  posture — confirm at plan time.)
- Does anyone script `pitcher-scout` in a cron/CI job (`docs/daily-runs.md`)?
  Grep before deleting; update docs in the same PR.
