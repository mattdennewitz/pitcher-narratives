# Phase 11: Intermediate Probability Pipeline - Research

**Researched:** 2026-03-31
**Domain:** Polars data pipeline extension -- surfacing existing CSV columns as structured data
**Confidence:** HIGH

## Summary

This phase is a pure data pipeline extension. The intermediate probability columns (P and S variants) **already exist** in all 8 pitchingplus aggregation CSVs and are **already loaded** into memory by `data.py:load_agg_csvs()` via `pl.read_csv()` (no column filtering). The work is to (1) create structured dataclass types that expose these columns, (2) add engine functions that extract them using the established `_weighted_window_metrics` pattern, and (3) ensure graceful handling when columns are missing (as is the case for `BBE_prob_P/S`, which exist only in per-pitch `all_pitches.csv`, not in the aggregation CSVs).

The existing codebase already uses `xWhiff_P`, `xSwing_P`, and `xRV100_P` via the `_XMETRICS` tuple and `_weighted_window_metrics()` function in `engine.py`. This phase widens that pattern to cover all intermediate probability columns and adds the S-variants so location impact (P minus S) can be computed downstream.

**Primary recommendation:** Extend the existing `_XMETRICS`-style tuple pattern and `_weighted_window_metrics` helper to cover all intermediate probability columns. Create a new `IntermediateProbabilities` dataclass (or similar) holding P and S variants per metric. No new dependencies needed. No changes to `data.py` required since all columns are already loaded.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key codebase observations informing implementation:
- Columns already present in CSVs: xSwing_P/S, xWhiff_P/S, xGOr_P/S, xPUr_P/S, xHR100_P/S, xSwSt_P/S, xRV100_P/S
- BBE_prob_P/S columns do NOT exist in current data files -- handle as "missing column" case
- engine.py already uses xWhiff_P, xSwing_P, xRV100_P via _XMETRICS tuple
- data.py loads all CSV columns implicitly via pl.read_csv (no column filtering)
- Weighted baseline computation in data.py already averages all non-ID columns

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Analyst context includes per-pitch-type intermediate probabilities (xSwing, xWhiff, xGOr, xPUr, xHR100, BBE_prob) from pitchingplus aggregations | Columns verified present in all 8 CSVs (except BBE_prob -- missing column case). `_weighted_window_metrics` already handles missing columns gracefully (returns None). |
| DATA-02 | Analyst context includes P vs S variants of intermediates so location impact is quantifiable | All CSVs have both `_P` and `_S` suffix variants. Location impact = P minus S, computed downstream. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude (already in pyproject.toml)
- **Data format**: Static parquet + CSV files, no live API calls
- **Python version**: 3.14+
- **Naming**: `snake_case.py` modules, `PascalCase` classes/dataclasses, `UPPER_SNAKE_CASE` constants
- **Docstrings**: Google-style
- **Imports**: Absolute, grouped with blank lines, sorted alphabetically
- **Module design**: `__all__` for public APIs, `_` prefix for internal helpers
- **Error handling**: Specific exception types, handle `pl.exceptions.ComputeError`
- **GSD workflow enforcement**: All file changes through GSD commands
- **Line length**: 110 (ruff config)
- **Linting**: ruff with select `["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]`

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame operations, CSV loading, weighted averaging | Already in use throughout data.py and engine.py |
| dataclasses | stdlib | Structured engine output types | Established pattern in engine.py (FastballSummary, ExecutionMetrics, etc.) |

### Supporting
No additional libraries needed. This phase uses only existing dependencies.

## Architecture Patterns

### Existing Project Structure (Relevant Files)
```
src/pitcher_narratives/
    data.py          # CSV loading, baseline computation -- NO CHANGES NEEDED
    engine.py        # Computation engine with dataclasses + compute functions -- EXTEND HERE
    context.py       # PitcherContext assembly + to_prompt() -- MINOR EXTENSION
    analyst.py       # Tool-calling agent -- Phase 13 scope (NOT this phase)
```

### Pattern 1: _XMETRICS Tuple + _weighted_window_metrics
**What:** Group related column names in a tuple constant, pass to `_weighted_window_metrics()` to compute n_pitches-weighted averages across a filtered window.
**When to use:** Any time you need to extract metric values from CSV data at a specific grain.
**Example (existing code in engine.py):**
```python
_XMETRICS = ("xWhiff_P", "xSwing_P", "xRV100_P")

xmetrics = _weighted_window_metrics(
    data.agg_csvs["pitcher_type_appearance"],
    _XMETRICS,
    _window_date_type_filter(window_dates, pt),
)
xwhiff_p = xmetrics["xWhiff_P"]  # float | None
```
**Key behavior:** `_weighted_window_metrics` returns `None` for columns not present in the DataFrame. This is the built-in graceful handling for missing columns.

### Pattern 2: Dataclass for Structured Engine Output
**What:** Define a frozen-ish `@dataclass` with typed fields, `float | None` for optional metrics.
**When to use:** Every engine output type follows this pattern.
**Example (existing):**
```python
@dataclass
class ExecutionMetrics:
    pitch_type: str
    pitch_name: str
    xwhiff_p: float | None
    xswing_p: float | None
    # ... etc
```

### Pattern 3: Season Baseline via Weighted Averaging
**What:** `compute_pitch_type_baseline()` in data.py already computes weighted averages for ALL non-ID columns. Since intermediate probability columns are already in the CSVs, they are already included in `pitch_type_baseline`.
**Key insight:** The baseline computation does NOT need modification -- it already averages intermediate columns because it dynamically discovers metric columns via `[c for c in df.columns if c not in id_cols]`.

### Recommended Implementation Approach

**New constant** -- define the full set of intermediate probability columns:
```python
_INTERMEDIATE_P_COLS = (
    "xSwing_P", "xWhiff_P", "xGOr_P", "xPUr_P", "xHR100_P", "BBE_prob_P",
)
_INTERMEDIATE_S_COLS = (
    "xSwing_S", "xWhiff_S", "xGOr_S", "xPUr_S", "xHR100_S", "BBE_prob_S",
)
_INTERMEDIATE_COLS = _INTERMEDIATE_P_COLS + _INTERMEDIATE_S_COLS
```

**New dataclass** -- per-pitch-type intermediate probabilities:
```python
@dataclass
class IntermediateProbabilities:
    pitch_type: str
    pitch_name: str
    # P-variants (model output including location)
    xswing_p: float | None
    xwhiff_p: float | None
    xgor_p: float | None
    xpur_p: float | None
    xhr100_p: float | None
    bbe_prob_p: float | None
    # S-variants (stuff-only, no location)
    xswing_s: float | None
    xwhiff_s: float | None
    xgor_s: float | None
    xpur_s: float | None
    xhr100_s: float | None
    bbe_prob_s: float | None
    # Grain metadata
    n_pitches: int
    small_sample: bool
    cold_start: bool
```

**New compute function** -- follows the established pattern:
```python
def compute_intermediate_probabilities(data: PitcherData) -> list[IntermediateProbabilities]:
    """Compute per-pitch-type intermediate probabilities for window and season."""
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)
    name_map = _build_name_map(data.statcast)

    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    results = []
    for pt in pitch_types:
        metrics = _weighted_window_metrics(
            data.agg_csvs["pitcher_type_appearance"],
            _INTERMEDIATE_COLS,
            _window_date_type_filter(window_dates, pt),
        )
        # Extract P and S variants -- None if column missing
        results.append(IntermediateProbabilities(
            pitch_type=pt,
            pitch_name=name_map.get(pt, pt),
            xswing_p=metrics.get("xSwing_P"),
            xwhiff_p=metrics.get("xWhiff_P"),
            # ... etc for all fields
            n_pitches=int(metrics.get("n_pitches", 0)),
            small_sample=int(metrics.get("n_pitches", 0)) < _MIN_PITCHES,
            cold_start=cold_start,
        ))
    return results
```

**Season baseline access** -- already available via `data.pitch_type_baseline` which already has all intermediate columns.

### Anti-Patterns to Avoid
- **Adding column selection to data.py:** `pl.read_csv()` loads all columns already. Adding explicit column lists creates a maintenance burden and risks breaking when CSVs gain new columns.
- **Duplicating weighted averaging logic:** Use `_weighted_window_metrics` -- do not re-implement the weighted average.
- **Modifying existing `_XMETRICS` tuple:** The existing tuple is used by `compute_execution_metrics`. Create a separate, wider tuple for the new function rather than widening the existing one, which would change `compute_execution_metrics` behavior.
- **Trying to aggregate BBE_prob from all_pitches.csv:** The success criteria ask for graceful handling of missing columns, not computing aggregates from pitch-level data. BBE_prob_P/S will simply be `None` when read from the aggregation CSVs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Weighted averaging | Custom weighted-avg loop | `_weighted_window_metrics()` | Already handles missing columns, empty windows, and n_pitches weighting correctly |
| Column presence checking | Manual `if col in df.columns` loops | `_weighted_window_metrics()` built-in None handling | The function already returns None for missing columns (line 332 of engine.py) |
| Pitch type name mapping | Hardcoded name dict | `_build_name_map(statcast)` | Existing helper derives names from Statcast data |
| Window date filtering | Custom date filter | `_window_date_type_filter()` + `_get_window_game_dates()` | Established pattern used by all engine functions |

**Key insight:** The existing `_weighted_window_metrics` function was designed to handle exactly this case. It iterates over a tuple of column names, checks `if metric in window.columns`, and returns `None` for missing columns. This is precisely the graceful missing-column handling required by success criterion 4.

## Common Pitfalls

### Pitfall 1: BBE_prob Columns Are Not in Aggregation CSVs
**What goes wrong:** Success criteria mention BBE_prob_P and BBE_prob_S, but these columns do NOT exist in any of the 8 aggregation CSVs. They exist only in the per-pitch `all_pitches.csv`.
**Why it happens:** The pitchingplus pipeline computes per-pitch BBE probabilities but does not aggregate them to the pitcher_type level.
**How to avoid:** Include BBE_prob_P/S in the column tuple -- `_weighted_window_metrics` will return `None` gracefully. The dataclass fields should be `float | None`. Do NOT attempt to compute BBE_prob aggregates from `all_pitches.csv` -- that is out of scope.
**Warning signs:** Tests that assert BBE_prob values are not None will fail.

### Pitfall 2: Column Name Case Sensitivity
**What goes wrong:** Polars column names are case-sensitive. Using `xswing_p` instead of `xSwing_P` will silently return None.
**Why it happens:** The CSV column names use mixed case (e.g., `xSwing_P`, `xWhiff_S`, `xGOr_P`).
**How to avoid:** Use exact column names from the CSV headers. Verified column names: `xSwing_P`, `xSwing_S`, `xWhiff_P`, `xWhiff_S`, `xGOr_P`, `xGOr_S`, `xPUr_P`, `xPUr_S`, `xHR100_P`, `xHR100_S`, `xSwSt_P`, `xSwSt_S`.
**Warning signs:** All intermediate values coming back as None despite columns existing.

### Pitfall 3: Confusing Dataclass Field Names with CSV Column Names
**What goes wrong:** The dataclass uses `snake_case` field names (e.g., `xswing_p`) but the CSV columns use mixed case (e.g., `xSwing_P`). The dict keys from `_weighted_window_metrics` use the CSV column names.
**Why it happens:** Python naming conventions vs. domain-specific CSV naming.
**How to avoid:** The extraction pattern is: `xswing_p=metrics["xSwing_P"]` (or `metrics.get("xSwing_P")`) -- mapping CSV-cased dict key to snake_cased dataclass field.

### Pitfall 4: Scope Creep Into Phase 13 Territory
**What goes wrong:** This phase surfaces intermediate probabilities. Computing P-minus-S deltas, formatting them for the analyst agent, or modifying tool output is Phase 13 work.
**Why it happens:** Natural desire to complete the feature end-to-end.
**How to avoid:** Phase 11 = data structures + compute functions. Phase 13 = tool integration + rendering. The boundary is: Phase 11 makes data *accessible*; Phase 13 makes it *visible to the LLM*.

### Pitfall 5: Forgetting xSwSt and xRV100 Columns
**What goes wrong:** The success criteria list 6 metrics (xSwing, xWhiff, xGOr, xPUr, xHR100, BBE_prob) but the CSVs also contain xSwSt_P/S and xRV100_P/S which are already partially used.
**Why it happens:** The success criteria are the minimum set; the CSVs have more.
**How to avoid:** Include ALL intermediate probability columns from the CSVs in the new dataclass. xRV100_P is already used by `_XMETRICS` but its S-variant is not surfaced. xSwSt (expected swing-and-strike) is a useful intermediate. The CONTEXT.md explicitly lists xSwSt_P/S and xRV100_P/S as present.

## Code Examples

### Verified CSV Column Headers (from actual data files)

**All 8 CSVs share this intermediate column set:**
```
xRV100_P, xRV100_S, xHR100_P, xHR100_S,
xSwing_P, xSwing_S, xSwSt_P, xSwSt_S,
xWhiff_P, xWhiff_S, xGOr_P, xGOr_S,
xPUr_P, xPUr_S
```

**NOT present in aggregation CSVs:**
```
BBE_prob_P, BBE_prob_S  (only in 2026-all_pitches.csv which is per-pitch)
```

### Existing _weighted_window_metrics Missing Column Handling (engine.py:294-334)
```python
def _weighted_window_metrics(
    df: pl.DataFrame,
    metrics: tuple[str, ...],
    filters: pl.Expr,
) -> dict[str, float | int | None]:
    window = df.filter(filters)
    empty: dict[str, float | int | None] = {m: None for m in metrics}
    empty["n_pitches"] = 0
    if window.is_empty():
        return empty
    total_pitches = window["n_pitches"].sum()
    if total_pitches == 0:
        return empty
    result: dict[str, float | int | None] = {"n_pitches": int(total_pitches)}
    for metric in metrics:
        if metric in window.columns:          # <-- graceful missing column handling
            weighted = (window[metric] * window["n_pitches"]).sum()
            result[metric] = _float(weighted) / _float(total_pitches)
        else:
            result[metric] = None             # <-- returns None, no crash
    return result
```

### Grains Available (from data.py)
```python
# Season grains (no game_date)
data.agg_csvs["pitcher"]           # pitcher-level season
data.agg_csvs["pitcher_type"]      # pitcher+pitch_type season  <-- KEY
data.agg_csvs["pitcher_type_platoon"]  # pitcher+type+platoon season

# Appearance grains (have game_date)
data.agg_csvs["pitcher_appearance"]          # pitcher per game
data.agg_csvs["pitcher_type_appearance"]     # pitcher+type per game  <-- KEY
data.agg_csvs["pitcher_type_platoon_appearance"]  # pitcher+type+platoon per game

# Pre-computed baselines (already include intermediates)
data.pitch_type_baseline  # weighted avg across game_types per pitch_type  <-- KEY
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Only `xWhiff_P`, `xSwing_P`, `xRV100_P` (3 metrics) | All 12+ intermediate P/S columns | This phase | Enables location impact (P-S) and full model transparency |
| P-variant only in `ExecutionMetrics` | Both P and S variants in new `IntermediateProbabilities` | This phase | S-variant gives stuff-only baseline for comparison |

## Open Questions

1. **Should xSwSt_P/S and xRV100_P/S be included in the new IntermediateProbabilities dataclass?**
   - What we know: They exist in all CSVs. xRV100_P is already used by `_XMETRICS`. xSwSt is expected swing-strike rate.
   - What's unclear: Whether Phase 13/14 will need them.
   - Recommendation: Include them. It costs nothing (same `_weighted_window_metrics` call) and avoids a future revisit. The CONTEXT.md explicitly lists them as present.

2. **Should season-level intermediates be exposed alongside window-level?**
   - What we know: `pitch_type_baseline` already contains all intermediates (weighted average). Engine currently provides season values alongside window values for P+/S+/L+ (in PitchTypeSummary).
   - What's unclear: Whether the IntermediateProbabilities dataclass should have both `season_xswing_p` and `window_xswing_p` (following the pattern of PitchTypeSummary's `season_p_plus`/`window_p_plus`).
   - Recommendation: Include both season and window values. This follows the established pattern and enables delta computation downstream (Phase 13).

3. **Should the `_render_execution_section` be updated to include new metrics?**
   - What we know: Phase 13 handles tool interface updates. Phase 11 is data pipeline only.
   - Recommendation: No. Keep context.py changes minimal (just wire the new compute function into `assemble_pitcher_context`). Rendering updates are Phase 13.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_engine.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Intermediate probabilities loaded for each pitch type | unit | `uv run pytest tests/test_engine.py::test_intermediate_probabilities_computed -x` | Wave 0 |
| DATA-01 | BBE_prob fields are None (missing from agg CSVs) | unit | `uv run pytest tests/test_engine.py::test_intermediate_bbe_prob_none -x` | Wave 0 |
| DATA-02 | Both P and S variants present per pitch type | unit | `uv run pytest tests/test_engine.py::test_intermediate_p_and_s_variants -x` | Wave 0 |
| DATA-02 | Location impact computable (P minus S yields numeric) | unit | `uv run pytest tests/test_engine.py::test_intermediate_location_impact -x` | Wave 0 |
| SC-3 | Accessible at pitcher+type and pitcher+type+appearance grains | unit | `uv run pytest tests/test_engine.py::test_intermediate_both_grains -x` | Wave 0 |
| SC-4 | Missing columns return None without crash | unit | `uv run pytest tests/test_engine.py::test_intermediate_missing_columns_graceful -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_engine.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- add new test functions for IntermediateProbabilities (file exists, new tests needed)
- [ ] No new test files or fixtures needed -- existing `load_pitcher_data(TEST_PITCHER)` fixture pattern is sufficient

## Sources

### Primary (HIGH confidence)
- Actual CSV column headers from `/Users/matt/src/pitcher-narratives/aggs/2026-pitcher_type.csv` and `2026-pitcher_type_appearance.csv` -- verified all intermediate columns present
- Source code: `engine.py` `_weighted_window_metrics` function (lines 294-334) -- verified missing column handling
- Source code: `data.py` `load_agg_csvs` and `compute_pitch_type_baseline` -- verified implicit column loading
- Source code: `engine.py` `_XMETRICS` tuple and `compute_execution_metrics` -- verified existing pattern

### Secondary (MEDIUM confidence)
- CONTEXT.md phase boundary document -- auto-generated from codebase analysis, cross-verified against actual code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, using existing polars + dataclasses
- Architecture: HIGH -- extending well-established patterns with verified existing helpers
- Pitfalls: HIGH -- verified BBE_prob absence in CSVs, verified column case sensitivity from actual headers

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- no external dependencies, static data files)
