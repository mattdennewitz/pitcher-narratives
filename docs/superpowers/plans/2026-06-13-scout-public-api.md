# Promote Cross-Module Private Functions to Public API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three private (`_`-prefixed) functions are imported across module boundaries, which signals a missing public API. Promote each to a public name, add it to its module's `__all__`, and update every importer and call site atomically.

**Architecture:** Pure renames. No logic changes, no signature changes (keyword parameters, including the `_sleep` test-injection seam, are preserved). Each function is renamed at its definition, exported via `__all__`, and repointed at every call site in the same commit so nothing is ever broken mid-task.

**Tech Stack:** Python 3.14, polars, pytest, uv, ruff.

**Prerequisite:** Independent of the engine and context plans. Can run in any order relative to them.

---

## Critical Context for the Implementer

### The three offenders (verified call sites)

1. **`scout._top_per_role`** → **`scout.top_per_role`**
   - Def: `src/pitcher_narratives/scout.py:90` — `def _top_per_role(results: list[ScoredAppearance], top_n: int) -> list[ScoredAppearance]`
   - Cross-module importers: `scout_cli.py:14,99`; `morning.py:36–37,90`; `tests/test_scout.py:5,22,30`
   - Genuinely a scout-domain operation consumed by the scout CLI and the morning workflow → promote to public.

2. **`scout._compute_velo_baselines`** → **`scout.compute_velo_baselines`**
   - Def: `src/pitcher_narratives/scout.py:244` — `def _compute_velo_baselines() -> pl.DataFrame`
   - Internal use: `scout.py:146`. Cross-module importer: `morning.py:36,53`
   - Promote to public.

3. **`bench/judge._with_retry`** → **`bench/judge.with_retry`**
   - Def: `src/pitcher_narratives/bench/judge.py:50`
   - Cross-module importer: `bench/__main__.py:21,126`; `tests/test_bench.py:135,146,153,159`
   - A generic retry helper used by the bench entrypoint → promote within the bench package.

### Why rename rather than leave private

A `_`-prefixed name is a contract: "internal, may change without notice." When another module imports it, that contract is already broken — the name is de-facto public but advertised as private, so refactors inside the owning module can silently break consumers. Promoting + adding to `__all__` makes the real API honest.

### Do NOT rename the `_sleep` parameter

`with_retry` has a `_sleep` keyword parameter used by tests for injection (`_with_retry(flaky, ..., _sleep=sleeps.append)`). That underscore is a conventional "internal seam" marker on a parameter and is fine to keep. Only the **function** name changes. After the rename the tests call `with_retry(flaky, ..., _sleep=sleeps.append)`.

### Atomicity rule

Each task renames the definition AND every call site AND the `__all__` entry in a single commit. Never commit a half-rename — imports would break. Run the per-task test command before committing.

### Per-task test commands (run specific files to dodge the pre-existing `test_analyst.py` collection error)

- Task 1 & 2: `uv run pytest -q tests/test_scout.py tests/test_morning.py`
- Task 3: `uv run pytest -q tests/test_bench.py`

Record each file's baseline pass/fail in Task 0; preserve it.

---

## Task 0: Capture the baseline

**Files:**
- None (verification only)

- [ ] **Step 1: Record baselines for the affected test files**

Run:
```bash
uv run pytest -q tests/test_scout.py tests/test_morning.py tests/test_bench.py 2>&1 | tail -4
```
Record the `N passed, M failed` line. This is the contract for the plan.

- [ ] **Step 2: Confirm the exact current call-site set**

Run:
```bash
grep -rn "_top_per_role\|_compute_velo_baselines\|_with_retry" src/ tests/ | grep -v __pycache__
```
Expected: the call sites listed in Critical Context above. If any additional site appears, add it to the relevant task's edit list.

---

## Task 1: Promote `_top_per_role` → `top_per_role`

**Files:**
- Modify: `src/pitcher_narratives/scout.py` (def L90, `__all__` L27)
- Modify: `src/pitcher_narratives/scout_cli.py` (L14, L99)
- Modify: `src/pitcher_narratives/morning.py` (L34–39 import block, L90)
- Modify: `tests/test_scout.py` (L5, L22, L30)

- [ ] **Step 1: Rename the definition**

In `src/pitcher_narratives/scout.py:90`, change:
```python
def _top_per_role(results: list[ScoredAppearance], top_n: int) -> list[ScoredAppearance]:
```
to:
```python
def top_per_role(results: list[ScoredAppearance], top_n: int) -> list[ScoredAppearance]:
```

- [ ] **Step 2: Add it to `__all__`**

In `src/pitcher_narratives/scout.py:27`, change:
```python
__all__ = ["ScoredAppearance", "scout_appearances"]
```
to:
```python
__all__ = ["ScoredAppearance", "scout_appearances", "top_per_role"]
```

- [ ] **Step 3: Update scout_cli.py**

Line 14, change `from pitcher_narratives.scout import _top_per_role, scout_appearances` to `from pitcher_narratives.scout import scout_appearances, top_per_role`.
Line 99, change `results = _top_per_role(results, args.top)` to `results = top_per_role(results, args.top)`.

- [ ] **Step 4: Update morning.py**

In the `from pitcher_narratives.scout import (...)` block (lines 34–39), change `_top_per_role,` to `top_per_role,`.
Line 90, change `candidates = _top_per_role(all_scored, top_n)` to `candidates = top_per_role(all_scored, top_n)`.

- [ ] **Step 5: Update tests/test_scout.py**

Line 5, change `from pitcher_narratives.scout import ScoredAppearance, _top_per_role` to `from pitcher_narratives.scout import ScoredAppearance, top_per_role`.
Lines 22 and 30, change `_top_per_role(apps, ...)` to `top_per_role(apps, ...)`.

- [ ] **Step 6: Confirm no stragglers**

Run:
```bash
grep -rn "_top_per_role" src/ tests/ | grep -v __pycache__
```
Expected: no output.

- [ ] **Step 7: Lint and test**

Run:
```bash
uv run ruff check src/pitcher_narratives/scout.py src/pitcher_narratives/scout_cli.py src/pitcher_narratives/morning.py && \
uv run pytest -q tests/test_scout.py tests/test_morning.py 2>&1 | tail -3
```
Expected: ruff clean; same pass/fail as Task 0 for those files.

- [ ] **Step 8: Commit**

```bash
git add -A src/pitcher_narratives/scout.py src/pitcher_narratives/scout_cli.py src/pitcher_narratives/morning.py tests/test_scout.py
git commit -m "refactor(scout): promote top_per_role to public API"
```

---

## Task 2: Promote `_compute_velo_baselines` → `compute_velo_baselines`

**Files:**
- Modify: `src/pitcher_narratives/scout.py` (def L244, internal call L146, `__all__` L27)
- Modify: `src/pitcher_narratives/morning.py` (import block L34–39, L53)

- [ ] **Step 1: Rename the definition**

In `src/pitcher_narratives/scout.py:244`, change:
```python
def _compute_velo_baselines() -> pl.DataFrame:
```
to:
```python
def compute_velo_baselines() -> pl.DataFrame:
```

- [ ] **Step 2: Update the internal call site**

In `src/pitcher_narratives/scout.py:146`, change `velo_baselines = _compute_velo_baselines()` to `velo_baselines = compute_velo_baselines()`.

- [ ] **Step 3: Add it to `__all__`**

In `src/pitcher_narratives/scout.py:27`, extend the list (it already gained `top_per_role` in Task 1):
```python
__all__ = ["ScoredAppearance", "compute_velo_baselines", "scout_appearances", "top_per_role"]
```

- [ ] **Step 4: Update morning.py**

In the `from pitcher_narratives.scout import (...)` block, change `_compute_velo_baselines,` to `compute_velo_baselines,`.
Line 53, change `velo = _compute_velo_baselines()` to `velo = compute_velo_baselines()`.

- [ ] **Step 5: Confirm no stragglers**

Run:
```bash
grep -rn "_compute_velo_baselines" src/ tests/ | grep -v __pycache__
```
Expected: no output.

- [ ] **Step 6: Lint and test**

Run:
```bash
uv run ruff check src/pitcher_narratives/scout.py src/pitcher_narratives/morning.py && \
uv run pytest -q tests/test_scout.py tests/test_morning.py 2>&1 | tail -3
```
Expected: ruff clean; same pass/fail as Task 0.

- [ ] **Step 7: Commit**

```bash
git add -A src/pitcher_narratives/scout.py src/pitcher_narratives/morning.py
git commit -m "refactor(scout): promote compute_velo_baselines to public API"
```

---

## Task 3: Promote `_with_retry` → `with_retry`

**Files:**
- Modify: `src/pitcher_narratives/bench/judge.py` (def L50, `__all__` L28)
- Modify: `src/pitcher_narratives/bench/__main__.py` (L21, L126)
- Modify: `tests/test_bench.py` (L135, L146, L153, L159)

- [ ] **Step 1: Rename the definition**

In `src/pitcher_narratives/bench/judge.py:50`, change `def _with_retry(` to `def with_retry(`. Leave the `_sleep` parameter name unchanged.

- [ ] **Step 2: Add it to `__all__`**

In `src/pitcher_narratives/bench/judge.py:28`, change:
```python
__all__ = ["JUDGE_MODELS", "judge_text", "judges_for", "make_judge_agent"]
```
to:
```python
__all__ = ["JUDGE_MODELS", "judge_text", "judges_for", "make_judge_agent", "with_retry"]
```

- [ ] **Step 3: Update bench/__main__.py**

Line 21, change `from pitcher_narratives.bench.judge import JUDGE_MODELS, _with_retry, judge_text, judges_for` to `from pitcher_narratives.bench.judge import JUDGE_MODELS, judge_text, judges_for, with_retry`.
Line 126, change `judged = _with_retry(lambda: judge_text(` to `judged = with_retry(lambda: judge_text(`.

- [ ] **Step 4: Update tests/test_bench.py**

Line 135, change `from pitcher_narratives.bench.judge import _with_retry` to `from pitcher_narratives.bench.judge import with_retry`.
Line 153, same change (second local import).
Lines 146 and 159, change `_with_retry(` to `with_retry(` (keep the `_sleep=` kwarg as-is).

- [ ] **Step 5: Confirm no stragglers**

Run:
```bash
grep -rn "_with_retry" src/ tests/ | grep -v __pycache__
```
Expected: no output.

- [ ] **Step 6: Lint and test**

Run:
```bash
uv run ruff check src/pitcher_narratives/bench/judge.py src/pitcher_narratives/bench/__main__.py && \
uv run pytest -q tests/test_bench.py 2>&1 | tail -3
```
Expected: ruff clean; same pass/fail as Task 0 for `test_bench.py`.

- [ ] **Step 7: Commit**

```bash
git add -A src/pitcher_narratives/bench/judge.py src/pitcher_narratives/bench/__main__.py tests/test_bench.py
git commit -m "refactor(bench): promote with_retry to public API"
```

---

## Task 4: Final verification

**Files:**
- None (verification only)

- [ ] **Step 1: Confirm zero cross-module private imports remain for these three**

Run:
```bash
grep -rn "import.*_top_per_role\|import.*_compute_velo_baselines\|import.*_with_retry" src/ tests/ | grep -v __pycache__
```
Expected: no output.

- [ ] **Step 2: Import the consumers**

Run:
```bash
uv run python -c "import pitcher_narratives.scout_cli, pitcher_narratives.morning, pitcher_narratives.bench.__main__; print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Re-run all affected test files together**

Run:
```bash
uv run pytest -q tests/test_scout.py tests/test_morning.py tests/test_bench.py 2>&1 | tail -4
```
Expected: same aggregate pass/fail as Task 0.

---

## Self-Review Checklist

- [ ] `grep -rn "_top_per_role\|_compute_velo_baselines\|_with_retry" src/ tests/` returns nothing (all renamed).
- [ ] `scout.__all__` contains `top_per_role` and `compute_velo_baselines`.
- [ ] `bench.judge.__all__` contains `with_retry`.
- [ ] The `_sleep` parameter of `with_retry` is unchanged.
- [ ] All three affected test files match the Task 0 pass/fail counts.
- [ ] ruff is clean on every edited file.

## Out of scope

- Moving `with_retry` out of `bench/judge.py` into a separate util module (it stays in place; only the name is promoted).
- Any logic, signature, or parameter-name change.
- The broader `data.py` concern-mixing noted in the architecture review (low priority; not addressed here).
