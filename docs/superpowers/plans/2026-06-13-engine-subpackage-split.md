# Engine Subpackage Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 3,187-line `engine.py` god module into a focused `engine/` subpackage, one module per analytical concern, without changing any behavior or any consumer's import statements.

**Architecture:** Convert `engine.py` into a package. A shared internal `_common.py` holds the private helpers and constants that every compute group depends on. Each analytical concern (baselines, arsenal, execution, workload, mechanics, tto, attribution, contact) becomes its own module importing from `_common`. The package `__init__.py` re-exports every public **and** test-referenced private symbol, so `from pitcher_narratives.engine import X` keeps working untouched everywhere.

**Tech Stack:** Python 3.14, polars, pydantic, pytest, uv, ruff, ty.

---

## Critical Context for the Implementer

### This is a pure mechanical refactor — behavior must not change

You are **moving code, not editing logic**. Copy function/class bodies verbatim. The only new code you write is import wiring in `__init__.py` and the per-module import headers.

### The baseline is NOT green — preserve the exact pass/fail set

On this branch (`mattdennewitz/feat/pitch-shape-arm-slot`), before you touch anything, the suite has **pre-existing failures unrelated to this refactor**. Your job is to keep that set identical, not to fix it.

Known pre-existing state (captured 2026-06-13):
- `tests/test_engine.py`: **124 passed, 6 failed**. The 6 failures are:
  - `test_fastball_pplus_delta`
  - `test_xwhiff_xswing`
  - `test_xrv100_percentile`
  - `test_intermediate_probabilities_computed`
  - `test_intermediate_location_impact`
  - `test_intermediate_both_grains`
- `tests/test_analyst.py`: **collection ImportError** (`cannot import name '_analyst_agent'`). This blocks a full-suite run, so this plan runs the engine/context test files directly.

**Success = same 124 pass / same 6 fail, before and after every task.** If a previously-passing test starts failing, you broke the move — revert and retry.

### Tests import PRIVATE engine symbols — the re-export must include them

`tests/test_engine.py` imports these underscore-prefixed names directly from `pitcher_narratives.engine`:
- `_CSW_DESCRIPTIONS` (constant)
- `_MIN_PITCHES` (constant)
- `_identify_primary_fastball`
- `_movement_delta_string`
- `_pplus_delta_string`
- `_usage_delta_string`
- `_velo_delta_string`
- `_stand_to_platoon`

A bare `from .module import *` will NOT pull underscore names. The `__init__.py` must import these **explicitly**. This is verified in Task 2.

### The baseline test command

```bash
uv run pytest -q tests/test_engine.py tests/test_context.py
```

This is the safety net you run after every task. It takes ~75 seconds (it loads real data from `aggs/` and `statcast/`). Do not use `-x`; you want the full count each time so you can compare against 124 passed / 6 failed.

### Source map of engine.py (current line numbers)

Constants & shared helpers (→ `_common.py`):
- L23 `_float`
- L77–161 module constants: `_FASTBALL_TYPES`, `_VELO_THRESHOLD`, `_PPLUS_THRESHOLD`, `_SHARP_VELO_THRESHOLD`, `_SHARP_PPLUS_THRESHOLD`, `_USAGE_THRESHOLD`, `_MOVEMENT_THRESHOLD`, `_FEET_TO_INCHES`, `_MIN_PITCHES`, `_COLD_START_STRING`, `_CSW_DESCRIPTIONS`, `_SWING_DESCRIPTIONS`, `_ZONE_IN`, `_ZONE_OUT`, `_OUT_EVENTS`, `_DOUBLE_OUT_EVENTS`
- L387 `_velo_delta_string`, L406 `_pplus_delta_string`, L425 `_usage_delta_string`, L444 `_movement_delta_string`
- L463 `_safe_metric`, L470 `_per_season_velo`, L492 `_pplus_delta_strings`, L513 `_build_name_map`, L519 `_identify_primary_fastball`, L537 `_get_window_game_dates`, L549 `_is_cold_start`, L561 `_weighted_window_metrics`, L604 `_stand_to_platoon`, L617 `_compute_platoon_baseline`
- L657–695 shared column tuples: `_PPLUS_METRICS`, `_XMETRICS`, `_INTERMEDIATE_P_COLS`, `_INTERMEDIATE_S_COLS`, `_INTERMEDIATE_COLS`, `_OUTCOME_COLS_P`, `_OUTCOME_NAMES`
- L2079 `_window_date_type_filter`

Baselines (→ `baselines.py`):
- L165 `LeagueBaseline`, L197 `compute_league_baselines`, L296 `outlier_tag`, L307 `render_league_baselines`, L346 `format_s_variant_comparisons`

Arsenal (→ `arsenal.py`):
- Dataclasses: L696 `FastballSummary`, L738 `VelocityArc`, L758 `PitchTypeSummary`, L817 `ArsenalPitchTrend`, L871 `ArsenalTrends`, L896 `PlatoonSplit`, L917 `PlatoonMix`, L925 `FirstPitchEntry`, L938 `FirstPitchWeaponry`
- Functions: L1295 `compute_fastball_summary`, L1401 `compute_velocity_arc`, L1465 `compute_arsenal_summary`, L1601 `compute_arsenal_trends`, L1791 `compute_platoon_mix`, L1916 `compute_first_pitch_weaponry`

Execution (→ `execution.py`):
- Dataclasses: L950 `ExecutionMetrics`, L991 `IntermediateProbabilities`
- Functions: L2084 `_compute_xrv100_percentile` (private, only used here), L2130 `compute_execution_metrics`, L2231 `compute_intermediate_probabilities`

Workload/temporal (→ `workload.py`):
- Dataclasses: L1087 `AppearanceWorkload`, L1106 `WorkloadContext`, L1118 `TemporalContext`, L1139 `CrossSeasonSummary`
- Functions: L1989 `_compute_ip_all_games`, L2024 `_compute_ip`, L2035 `_compute_rest_days`, L2056 `_max_consecutive_days` (all private, only used here), L2322 `compute_workload_context`, L2375 `_sum_baseball_ip` (private, only here), L2397 `compute_temporal_context`, L2495 `compute_cross_season_summary`

Mechanics (→ `mechanics.py`):
- Constants: L1198 `_RELEASE_POS_THRESHOLD`, L1201 `_EXTENSION_THRESHOLD`
- Functions: L1205 `_release_delta_string`, L1221 `_extension_delta_string` (private, only used here)
- Dataclasses: L1237 `ReleasePointPitchType`, L1281 `ReleasePointMetrics`
- Function: L2607 `compute_release_point_metrics`

Contact (→ `contact.py`):
- Dataclass: L1170 `HardHitRate`
- Function: L2562 `compute_hard_hit_rate`

TTO (→ `tto.py`):
- Constant: L2700 `_TTO_SMALL_SAMPLE`
- Dataclasses: L2704 `TTOPitchType`, L2719 `TTOPlatoonSplit`, L2731 `TTOSplit`, L2761 `TTOAnalysis`
- Function: L2774 `compute_tto_analysis`

Attribution (→ `attribution.py`):
- Dataclasses: L1051 `OutcomeContribution`, L1062 `ComponentAttribution`
- Function: L3072 `compute_component_attribution`

### Dependency rule

Every concern module imports the helpers/constants it needs **from `pitcher_narratives.engine._common`**. `_common.py` imports only from `pitcher_narratives.data` (for `PitcherData`, `load_full_agg`, etc.) and stdlib/polars. No concern module imports another concern module. `baselines.py` is independent (reads via `load_full_agg`). This keeps the graph a clean star: `_common` ← each concern, and `__init__` ← everything.

### How to verify each move (the discipline for every extraction task)

1. `git mv` is not used (we extract subsets, not whole files). Instead: create the new module, **cut** the relevant defs out of the old `engine.py` body, paste into the new module with an import header.
2. In `__init__.py`, add `from pitcher_narratives.engine.<module> import <symbols>`.
3. Run the baseline command. Confirm **124 passed, 6 failed** (the same 6 names).
4. Run `uv run ruff check src/pitcher_narratives/engine/` — expect clean (no unused imports, no F401 except the intentional re-exports in `__init__.py`, see Task 2).
5. Commit.

---

## Task 0: Capture the baseline as a recorded fact

**Files:**
- None (verification only)

- [ ] **Step 1: Run the engine/context tests and record the exact result**

Run:
```bash
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected (record the actual numbers you see — they are the contract for the rest of this plan):
```
6 failed, 124 passed in ~75s
```
The 6 failures must be exactly: `test_fastball_pplus_delta`, `test_xwhiff_xswing`, `test_xrv100_percentile`, `test_intermediate_probabilities_computed`, `test_intermediate_location_impact`, `test_intermediate_both_grains`.

If your numbers differ from this, STOP and reconcile before proceeding — the plan's safety net assumes this baseline.

- [ ] **Step 2: Confirm the full set of consumer imports that must keep working**

Run:
```bash
grep -rn "from pitcher_narratives.engine import\|from pitcher_narratives import engine\|pitcher_narratives\.engine\." src/ tests/ | grep -v __pycache__
```
Expected: imports in `context.py`, `pipeline.py`, `analyst.py`, `tests/test_engine.py`, `tests/test_context.py`, `tests/test_pipeline.py`. Every symbol they pull must be re-exported by the final `__init__.py`. Keep this output handy as your re-export checklist.

---

## Task 1: Create the package skeleton (engine.py → engine/__init__.py)

This task changes the file layout but moves zero code logically — `engine/__init__.py` temporarily contains the entire old file. `pitcher_narratives.engine` resolves to the package; all imports keep working.

**Files:**
- Create: `src/pitcher_narratives/engine/__init__.py` (from existing `engine.py`)
- Delete: `src/pitcher_narratives/engine.py`

- [ ] **Step 1: Move the module into a package directory**

Run:
```bash
mkdir -p src/pitcher_narratives/engine
git mv src/pitcher_narratives/engine.py src/pitcher_narratives/engine/__init__.py
```

- [ ] **Step 2: Run the baseline to prove the package resolves identically**

Run:
```bash
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: `6 failed, 124 passed` — identical to Task 0.

- [ ] **Step 3: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): convert engine module to package (no logic change)"
```

---

## Task 2: Extract _common.py (shared helpers + constants)

This is the foundation every other module depends on, so it goes first. After this task, `__init__.py` keeps the public symbols but pulls the shared internals from `_common`.

**Files:**
- Create: `src/pitcher_narratives/engine/_common.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create _common.py with the shared header and cut-in helpers**

Create `src/pitcher_narratives/engine/_common.py`. Start with this header, then **cut** (move, do not copy-leaving-duplicate) the following from `__init__.py` into it, preserving each body verbatim:

```python
"""Shared internal helpers and constants for the engine subpackage.

Private to the engine package. Concern modules (arsenal, execution,
workload, mechanics, tto, attribution, contact) import the delta-string
formatters, weighted-window helpers, name maps, and threshold constants
from here. Not part of the public engine API except where __init__.py
re-exports specific names for tests.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import polars as pl

from pitcher_narratives.data import PitcherData

_log = logging.getLogger(__name__)
```

Move these definitions out of `__init__.py` into `_common.py` (current locations in the source map above):
- `_float` (L23)
- All constants L77–161: `_FASTBALL_TYPES`, `_VELO_THRESHOLD`, `_PPLUS_THRESHOLD`, `_SHARP_VELO_THRESHOLD`, `_SHARP_PPLUS_THRESHOLD`, `_USAGE_THRESHOLD`, `_MOVEMENT_THRESHOLD`, `_FEET_TO_INCHES`, `_MIN_PITCHES`, `_COLD_START_STRING`, `_CSW_DESCRIPTIONS`, `_SWING_DESCRIPTIONS`, `_ZONE_IN`, `_ZONE_OUT`, `_OUT_EVENTS`, `_DOUBLE_OUT_EVENTS`
- `_velo_delta_string`, `_pplus_delta_string`, `_usage_delta_string`, `_movement_delta_string`
- `_safe_metric`, `_per_season_velo`, `_pplus_delta_strings`, `_build_name_map`, `_identify_primary_fastball`, `_get_window_game_dates`, `_is_cold_start`, `_weighted_window_metrics`, `_stand_to_platoon`, `_compute_platoon_baseline`
- Column tuples L657–695: `_PPLUS_METRICS`, `_XMETRICS`, `_INTERMEDIATE_P_COLS`, `_INTERMEDIATE_S_COLS`, `_INTERMEDIATE_COLS`, `_OUTCOME_COLS_P`, `_OUTCOME_NAMES`
- `_window_date_type_filter` (L2079)

> Note: `__init__.py` already has `import logging` / `import polars as pl` / `from typing import Any, cast` / the `data` import at its top. Leave those in `__init__.py` for now (the remaining code there still uses them); you will prune `__init__.py` imports in Task 10.

- [ ] **Step 2: Wire __init__.py to pull shared internals from _common**

At the top of `src/pitcher_narratives/engine/__init__.py`, immediately after its existing imports, add:

```python
# Shared internal helpers — re-exported because tests and sibling modules
# reference them by name from `pitcher_narratives.engine`.
from pitcher_narratives.engine._common import (  # noqa: F401
    _CSW_DESCRIPTIONS,
    _MIN_PITCHES,
    _build_name_map,
    _compute_platoon_baseline,
    _float,
    _get_window_game_dates,
    _identify_primary_fastball,
    _is_cold_start,
    _movement_delta_string,
    _per_season_velo,
    _pplus_delta_string,
    _pplus_delta_strings,
    _safe_metric,
    _stand_to_platoon,
    _usage_delta_string,
    _velo_delta_string,
    _weighted_window_metrics,
    _window_date_type_filter,
)
from pitcher_narratives.engine._common import (  # noqa: F401
    _COLD_START_STRING,
    _DOUBLE_OUT_EVENTS,
    _FASTBALL_TYPES,
    _FEET_TO_INCHES,
    _INTERMEDIATE_COLS,
    _INTERMEDIATE_P_COLS,
    _INTERMEDIATE_S_COLS,
    _MOVEMENT_THRESHOLD,
    _OUT_EVENTS,
    _OUTCOME_COLS_P,
    _OUTCOME_NAMES,
    _PPLUS_METRICS,
    _PPLUS_THRESHOLD,
    _SHARP_PPLUS_THRESHOLD,
    _SHARP_VELO_THRESHOLD,
    _SWING_DESCRIPTIONS,
    _USAGE_THRESHOLD,
    _VELO_THRESHOLD,
    _XMETRICS,
    _ZONE_IN,
    _ZONE_OUT,
    _SWING_DESCRIPTIONS as _SWING_DESCRIPTIONS_alias,  # placeholder if duplicate; remove if ruff flags
)
```

> The `# noqa: F401` is intentional: these are re-exports, not unused imports. If ruff still complains, the canonical fix is to add the names to `__all__` (done in Task 10) rather than removing the noqa. Remove the `_SWING_DESCRIPTIONS_alias` placeholder line — it is only shown to flag that you must not double-import a name; import each name exactly once.

The remaining code still in `__init__.py` (the compute functions not yet moved) references these helpers by bare name (e.g. `_velo_delta_string(...)`). The import above rebinds those names in the `__init__` namespace, so the still-present functions resolve them correctly.

- [ ] **Step 3: Run the baseline**

Run:
```bash
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: `6 failed, 124 passed`. In particular, `test_engine.py`'s imports of `_velo_delta_string`, `_pplus_delta_string`, `_usage_delta_string`, `_movement_delta_string`, `_identify_primary_fastball`, `_stand_to_platoon`, `_CSW_DESCRIPTIONS`, `_MIN_PITCHES` must still resolve (collection succeeds).

- [ ] **Step 4: Lint the new module**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/_common.py
```
Expected: clean. Fix any unused-import findings by deleting genuinely-unused imports from `_common.py` (e.g. if a moved helper did not need `cast`, drop it — but `_float` uses `cast`, so keep it).

- [ ] **Step 5: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract shared helpers and constants to _common"
```

---

## Task 3: Extract baselines.py

**Files:**
- Create: `src/pitcher_narratives/engine/baselines.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create baselines.py and move the league-baseline code**

Create `src/pitcher_narratives/engine/baselines.py` with this header, then cut `LeagueBaseline` (L165), `compute_league_baselines` (L197), `outlier_tag` (L296), `render_league_baselines` (L307), `format_s_variant_comparisons` (L346) out of `__init__.py` into it:

```python
"""League baseline computation and rendering.

Computes league-average physical/quality profiles and S-variant
benchmarks from the season aggregates, plus the outlier tagging and
markdown rendering used to ground specialist prompts.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import load_full_agg
```

> Check the moved bodies for any helper they call. `compute_league_baselines` uses `load_full_agg`; `render_league_baselines` / `format_s_variant_comparisons` are self-contained string builders. If any references a `_common` symbol (e.g. a threshold), add `from pitcher_narratives.engine._common import <name>`. Verify with the grep in Step 3.

- [ ] **Step 2: Re-export from __init__.py**

In `src/pitcher_narratives/engine/__init__.py`, add:
```python
from pitcher_narratives.engine.baselines import (  # noqa: F401
    LeagueBaseline,
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
```

- [ ] **Step 3: Verify no dangling references and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/baselines.py && \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `6 failed, 124 passed`.

- [ ] **Step 4: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract league baselines to baselines module"
```

---

## Task 4: Extract arsenal.py

**Files:**
- Create: `src/pitcher_narratives/engine/arsenal.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create arsenal.py and move arsenal dataclasses + compute functions**

Create `src/pitcher_narratives/engine/arsenal.py` with this header, then cut these from `__init__.py`: dataclasses `FastballSummary` (L696), `VelocityArc` (L738), `PitchTypeSummary` (L758), `ArsenalPitchTrend` (L817), `ArsenalTrends` (L871), `PlatoonSplit` (L896), `PlatoonMix` (L917), `FirstPitchEntry` (L925), `FirstPitchWeaponry` (L938); and functions `compute_fastball_summary` (L1295), `compute_velocity_arc` (L1401), `compute_arsenal_summary` (L1465), `compute_arsenal_trends` (L1601), `compute_platoon_mix` (L1791), `compute_first_pitch_weaponry` (L1916).

```python
"""Arsenal analysis: fastball summary, velocity arc, per-pitch-type
breakdowns, year-over-year arsenal trends, platoon mix, and first-pitch
weaponry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _COLD_START_STRING,
    _FASTBALL_TYPES,
    _FEET_TO_INCHES,
    _build_name_map,
    _compute_platoon_baseline,
    _float,
    _get_window_game_dates,
    _identify_primary_fastball,
    _is_cold_start,
    _movement_delta_string,
    _per_season_velo,
    _pplus_delta_string,
    _pplus_delta_strings,
    _safe_metric,
    _usage_delta_string,
    _velo_delta_string,
    _weighted_window_metrics,
    _window_date_type_filter,
)
```

> The import list above is the **expected** set based on the call-site analysis. After pasting, remove any name ruff flags as unused, and add any name the moved code references that is missing (ruff/`ty` will report `undefined name`). The `field` import is only needed if a moved dataclass uses `field(default_factory=...)`; drop it if not.

- [ ] **Step 2: Re-export from __init__.py**

Add to `__init__.py`:
```python
from pitcher_narratives.engine.arsenal import (  # noqa: F401
    ArsenalPitchTrend,
    ArsenalTrends,
    FastballSummary,
    FirstPitchEntry,
    FirstPitchWeaponry,
    PitchTypeSummary,
    PlatoonMix,
    PlatoonSplit,
    VelocityArc,
    compute_arsenal_summary,
    compute_arsenal_trends,
    compute_fastball_summary,
    compute_first_pitch_weaponry,
    compute_platoon_mix,
    compute_velocity_arc,
)
```

- [ ] **Step 3: Lint, type-check, and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/arsenal.py && \
uv run ty check src/pitcher_narratives/engine/arsenal.py ; \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `ty` reports no new errors; `6 failed, 124 passed`. (`ty` is pre-1.0 — if it emits noise unrelated to undefined names, focus only on `undefined-name`/`unresolved-import` findings.)

- [ ] **Step 4: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract arsenal analysis to arsenal module"
```

---

## Task 5: Extract execution.py

**Files:**
- Create: `src/pitcher_narratives/engine/execution.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create execution.py and move execution code**

Create `src/pitcher_narratives/engine/execution.py` with this header, then cut from `__init__.py`: dataclasses `ExecutionMetrics` (L950), `IntermediateProbabilities` (L991); functions `_compute_xrv100_percentile` (L2084, private — moves here, only used here), `compute_execution_metrics` (L2130), `compute_intermediate_probabilities` (L2231).

```python
"""Execution metrics: CSW%, zone rate, chase rate, expected whiff/swing,
xRV100 percentile, and intermediate P/S-variant probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _CSW_DESCRIPTIONS,
    _INTERMEDIATE_P_COLS,
    _INTERMEDIATE_S_COLS,
    _SWING_DESCRIPTIONS,
    _XMETRICS,
    _ZONE_IN,
    _ZONE_OUT,
    _build_name_map,
    _float,
    _get_window_game_dates,
    _is_cold_start,
    _weighted_window_metrics,
    _window_date_type_filter,
)
```

> Adjust the import set to exactly what the moved bodies use (ruff will flag extras; `ty` will flag missing). `_compute_xrv100_percentile` is only called inside `compute_execution_metrics`, so it belongs here, not in `_common`.

- [ ] **Step 2: Re-export from __init__.py**

Add to `__init__.py`:
```python
from pitcher_narratives.engine.execution import (  # noqa: F401
    ExecutionMetrics,
    IntermediateProbabilities,
    compute_execution_metrics,
    compute_intermediate_probabilities,
)
```

- [ ] **Step 3: Lint and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/execution.py && \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `6 failed, 124 passed`. The 6 known failures live in this concern (intermediate/xrv tests) — confirm they are the **same 6**, not 7+. If a previously-passing execution test now fails, you dropped a reference; reconcile.

- [ ] **Step 4: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract execution metrics to execution module"
```

---

## Task 6: Extract workload.py

**Files:**
- Create: `src/pitcher_narratives/engine/workload.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create workload.py and move workload/temporal code**

Create `src/pitcher_narratives/engine/workload.py` with this header, then cut from `__init__.py`: dataclasses `AppearanceWorkload` (L1087), `WorkloadContext` (L1106), `TemporalContext` (L1118), `CrossSeasonSummary` (L1139); functions `_compute_ip_all_games` (L1989), `_compute_ip` (L2024), `_compute_rest_days` (L2035), `_max_consecutive_days` (L2056), `compute_workload_context` (L2322), `_sum_baseball_ip` (L2375), `compute_temporal_context` (L2397), `compute_cross_season_summary` (L2495). The four `_compute_ip*`/`_max_consecutive_days`/`_sum_baseball_ip` privates are used only by this concern, so they move here.

```python
"""Workload and temporal context: rest days, innings pitched, consecutive
appearances, season grounding, and cross-season metric deltas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _build_name_map,
    _float,
    _get_window_game_dates,
    _is_cold_start,
    _per_season_velo,
    _pplus_delta_string,
    _usage_delta_string,
    _velo_delta_string,
)
```

> `compute_temporal_context` takes a `WorkloadContext` argument (it is called as `compute_temporal_context(data, workload)` in `context.py`). Keep its signature byte-for-byte. Trim/extend the `_common` import set to actual usage.

- [ ] **Step 2: Re-export from __init__.py**

Add to `__init__.py`:
```python
from pitcher_narratives.engine.workload import (  # noqa: F401
    AppearanceWorkload,
    CrossSeasonSummary,
    TemporalContext,
    WorkloadContext,
    compute_cross_season_summary,
    compute_temporal_context,
    compute_workload_context,
)
```

- [ ] **Step 3: Lint and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/workload.py && \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `6 failed, 124 passed`.

- [ ] **Step 4: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract workload and temporal context to workload module"
```

---

## Task 7: Extract mechanics.py

**Files:**
- Create: `src/pitcher_narratives/engine/mechanics.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create mechanics.py and move release-point code**

Create `src/pitcher_narratives/engine/mechanics.py` with this header, then cut from `__init__.py`: constants `_RELEASE_POS_THRESHOLD` (L1198), `_EXTENSION_THRESHOLD` (L1201); functions `_release_delta_string` (L1205), `_extension_delta_string` (L1221) (both private, used only here); dataclasses `ReleasePointPitchType` (L1237), `ReleasePointMetrics` (L1281); function `compute_release_point_metrics` (L2607).

```python
"""Release-point mechanics: per-pitch-type horizontal/vertical release
position and extension, with window-vs-season deltas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _build_name_map,
    _float,
    _get_window_game_dates,
    _is_cold_start,
)
```

> The two release threshold constants and their delta-string helpers are mechanics-local; keep them in this module (not `_common`). Adjust `_common` imports to actual usage.

- [ ] **Step 2: Re-export from __init__.py**

Add to `__init__.py`:
```python
from pitcher_narratives.engine.mechanics import (  # noqa: F401
    ReleasePointMetrics,
    ReleasePointPitchType,
    compute_release_point_metrics,
)
```

- [ ] **Step 3: Lint and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/mechanics.py && \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `6 failed, 124 passed`.

- [ ] **Step 4: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract release-point mechanics to mechanics module"
```

---

## Task 8: Extract contact.py and tto.py

These two are independent of each other; doing them in one task keeps commits proportionate.

**Files:**
- Create: `src/pitcher_narratives/engine/contact.py`
- Create: `src/pitcher_narratives/engine/tto.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create contact.py and move hard-hit code**

Create `src/pitcher_narratives/engine/contact.py` with this header, then cut from `__init__.py`: dataclass `HardHitRate` (L1170); function `compute_hard_hit_rate` (L2562).

```python
"""Contact quality: hard-hit rate over batted balls in the window vs
season.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _COLD_START_STRING,
    _build_name_map,
    _get_window_game_dates,
    _is_cold_start,
    _usage_delta_string,
)
```

- [ ] **Step 2: Create tto.py and move times-through-order code**

Create `src/pitcher_narratives/engine/tto.py` with this header, then cut from `__init__.py`: constant `_TTO_SMALL_SAMPLE` (L2700); dataclasses `TTOPitchType` (L2704), `TTOPlatoonSplit` (L2719), `TTOSplit` (L2731), `TTOAnalysis` (L2761); function `compute_tto_analysis` (L2774).

```python
"""Times-through-order analysis: per-pass pitch mix, fastball/secondary
P+ degradation, velocity decay, and platoon splits across passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _build_name_map,
    _float,
    _get_window_game_dates,
    _pplus_delta_string,
    _usage_delta_string,
    _velo_delta_string,
    _weighted_window_metrics,
)
```

> `compute_tto_analysis` is the largest single function (~300 lines, L2774–3067). Move the whole body verbatim. Adjust `_common` imports to actual usage.

- [ ] **Step 3: Re-export both from __init__.py**

Add to `__init__.py`:
```python
from pitcher_narratives.engine.contact import (  # noqa: F401
    HardHitRate,
    compute_hard_hit_rate,
)
from pitcher_narratives.engine.tto import (  # noqa: F401
    TTOAnalysis,
    TTOPitchType,
    TTOPlatoonSplit,
    TTOSplit,
    compute_tto_analysis,
)
```

- [ ] **Step 4: Lint and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/contact.py src/pitcher_narratives/engine/tto.py && \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `6 failed, 124 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract contact quality and TTO to dedicated modules"
```

---

## Task 9: Extract attribution.py

After this, `__init__.py` should contain no compute functions or dataclasses of its own — only the re-export block.

**Files:**
- Create: `src/pitcher_narratives/engine/attribution.py`
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Create attribution.py and move component-attribution code**

Create `src/pitcher_narratives/engine/attribution.py` with this header, then cut from `__init__.py`: dataclasses `OutcomeContribution` (L1051), `ComponentAttribution` (L1062); function `compute_component_attribution` (L3072).

```python
"""Component attribution: decomposes xRV100 into 13 outcome-level
contributions per pitch type using the run-values lookup.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData, load_run_values
from pitcher_narratives.engine._common import (
    _OUTCOME_COLS_P,
    _OUTCOME_NAMES,
    _build_name_map,
    _get_window_game_dates,
    _window_date_type_filter,
)
```

> `compute_component_attribution` uses the run-values table; confirm whether it calls `load_run_values` directly or receives it via `data`. Keep imports matching actual usage (drop `load_run_values` if unused).

- [ ] **Step 2: Re-export from __init__.py**

Add to `__init__.py`:
```python
from pitcher_narratives.engine.attribution import (  # noqa: F401
    ComponentAttribution,
    OutcomeContribution,
    compute_component_attribution,
)
```

- [ ] **Step 3: Lint and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/attribution.py && \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `6 failed, 124 passed`.

- [ ] **Step 4: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): extract component attribution to attribution module"
```

---

## Task 10: Finalize __init__.py as a pure re-export surface

At this point `__init__.py` holds only the re-export imports plus whatever leftover top-level imports (logging/polars/typing/data) are now unused. Clean it into a deliberate public API.

**Files:**
- Modify: `src/pitcher_narratives/engine/__init__.py`

- [ ] **Step 1: Rewrite __init__.py header and __all__**

Replace the top-of-file module imports (the original `import logging`, `import polars as pl`, `from typing import Any, cast`, `from pitcher_narratives.data import ...`, and the `_float`/`_log` leftovers if any remain) with this docstring, keeping ONLY the `from pitcher_narratives.engine.<module> import (...)` re-export blocks added in Tasks 2–9:

```python
"""Computation engine for pitcher narratives (subpackage facade).

Transforms PitcherData into pre-computed analysis ready for LLM
consumption. This module is a thin facade: every public symbol is
implemented in a focused concern module (baselines, arsenal, execution,
workload, mechanics, contact, tto, attribution) and re-exported here so
existing `from pitcher_narratives.engine import X` imports keep working.

Shared private helpers live in `_common`; a handful are re-exported here
because the test suite references them directly.
"""

from __future__ import annotations
```

- [ ] **Step 2: Define __all__ from the original export list**

Append the original public `__all__` (the 34-symbol list that was at the top of the pre-split `engine.py`) verbatim so the public surface is explicit and ruff's F401 on the re-exports is satisfied by membership in `__all__`:

```python
__all__ = [
    "ArsenalPitchTrend",
    "ArsenalTrends",
    "AppearanceWorkload",
    "ComponentAttribution",
    "CrossSeasonSummary",
    "ExecutionMetrics",
    "FastballSummary",
    "FirstPitchEntry",
    "FirstPitchWeaponry",
    "HardHitRate",
    "IntermediateProbabilities",
    "OutcomeContribution",
    "PitchTypeSummary",
    "PlatoonMix",
    "PlatoonSplit",
    "ReleasePointMetrics",
    "ReleasePointPitchType",
    "TTOAnalysis",
    "TTOPitchType",
    "TTOPlatoonSplit",
    "TTOSplit",
    "TemporalContext",
    "VelocityArc",
    "WorkloadContext",
    "compute_arsenal_summary",
    "compute_arsenal_trends",
    "compute_component_attribution",
    "compute_cross_season_summary",
    "compute_execution_metrics",
    "compute_fastball_summary",
    "compute_first_pitch_weaponry",
    "compute_hard_hit_rate",
    "compute_intermediate_probabilities",
    "compute_platoon_mix",
    "compute_release_point_metrics",
    "compute_temporal_context",
    "compute_tto_analysis",
    "compute_velocity_arc",
    "compute_workload_context",
    "LeagueBaseline",
    "compute_league_baselines",
    "format_s_variant_comparisons",
    "outlier_tag",
    "render_league_baselines",
]
```

> The private re-exports (`_velo_delta_string`, `_MIN_PITCHES`, etc.) stay as `# noqa: F401` imports and are deliberately NOT in `__all__` — they remain importable by name for the tests but are not part of the advertised API.

- [ ] **Step 3: Confirm __init__.py contains no logic**

Run:
```bash
grep -nE "^def |^class |^@dataclass" src/pitcher_narratives/engine/__init__.py
```
Expected: no output. If anything prints, a definition was left behind — move it to its concern module.

- [ ] **Step 4: Lint the whole package and run the baseline**

Run:
```bash
uv run ruff check src/pitcher_narratives/engine/ && \
uv run pytest -q tests/test_engine.py tests/test_context.py 2>&1 | tail -3
```
Expected: ruff clean; `6 failed, 124 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): reduce __init__ to a pure re-export facade"
```

---

## Task 11: Full-package verification and import-graph sanity

**Files:**
- None (verification only)

- [ ] **Step 1: Verify every consumer module still imports cleanly**

Run:
```bash
uv run python -c "import pitcher_narratives.context, pitcher_narratives.pipeline, pitcher_narratives.analyst, pitcher_narratives.morning, pitcher_narratives.scout; print('all consumers import OK')"
```
Expected: `all consumers import OK`.

- [ ] **Step 2: Run the pipeline test file (heaviest consumer of engine)**

Run:
```bash
uv run pytest -q tests/test_pipeline.py 2>&1 | tail -3
```
Expected: same pass/fail count as before the refactor. (Capture this number at Task 0 if you want a strict comparison: run `uv run pytest -q tests/test_pipeline.py 2>&1 | tail -3` during Task 0 and record it.)

- [ ] **Step 3: Confirm no sibling-to-sibling concern imports leaked in**

Run:
```bash
grep -rn "from pitcher_narratives.engine.\(arsenal\|execution\|workload\|mechanics\|contact\|tto\|attribution\|baselines\) import" src/pitcher_narratives/engine/ | grep -v __init__.py
```
Expected: no output. Concern modules may import only from `_common` (and `data`), never from each other. If a line prints, refactor the shared dependency down into `_common`.

- [ ] **Step 4: Confirm file sizes are now tractable**

Run:
```bash
wc -l src/pitcher_narratives/engine/*.py | sort -n
```
Expected: no module over ~700 lines; `__init__.py` well under 120 lines. `tto.py` will be the largest concern module (~350 lines) and that is acceptable.

- [ ] **Step 5: Final commit (if Step 1–4 produced any cleanup edits)**

```bash
git add -A src/pitcher_narratives/engine
git commit -m "refactor(engine): verify subpackage import graph and module sizes"
```

---

## Self-Review Checklist (run before declaring done)

- [ ] Every symbol in the original `engine.py.__all__` is re-exported by `__init__.py` and listed in `__all__`.
- [ ] The 8 test-referenced private names (`_CSW_DESCRIPTIONS`, `_MIN_PITCHES`, `_identify_primary_fastball`, `_movement_delta_string`, `_pplus_delta_string`, `_usage_delta_string`, `_velo_delta_string`, `_stand_to_platoon`) are importable from `pitcher_narratives.engine`.
- [ ] `uv run pytest -q tests/test_engine.py tests/test_context.py` ends in `6 failed, 124 passed` — the same 6 names as Task 0.
- [ ] No concern module imports another concern module.
- [ ] `__init__.py` contains zero `def`/`class`/`@dataclass`.
- [ ] `uv run ruff check src/pitcher_narratives/engine/` is clean.

## Out of scope (do NOT attempt in this plan)

- Fixing the 6 pre-existing `test_engine.py` failures.
- Fixing the `test_analyst.py` collection error (`_analyst_agent`).
- Splitting `context.py` (separate plan: `2026-06-13-context-rendering-separation.md`).
- Promoting scout private functions (separate plan: `2026-06-13-scout-public-api.md`).
- Renaming any public symbol or changing any function signature.
