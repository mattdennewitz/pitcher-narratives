# Phase 20: Season-Delta Engine - Research

**Researched:** 2026-04-03
**Domain:** Cross-season delta computation for pitcher-level metrics
**Confidence:** HIGH

## Summary

Phase 20 adds a cross-season summary engine that computes year-over-year deltas for pitcher-level metrics: velocity, P+, S+, and L+, plus basic workload comparison (innings pitched, pitch count averages, appearances). The implementation adds to `engine.py` alongside existing within-season delta logic, reusing the same qualitative string functions (`_velo_delta_string`, `_pplus_delta_string`) and threshold constants.

The core data sources are already available from Phase 19: `PitcherData.season_baseline` (current season) and `PitcherData.prior_season_baseline` (previous season). P+/S+/L+ come directly from the season_baseline DataFrame columns. Velocity requires computing season-level averages from statcast `release_speed` grouped by `game_year`. When `prior_season_baseline` is empty (single-season pitcher), the cross-season summary must be `None`.

The implementation is straightforward because (a) all input data is already loaded and split by Phase 19, (b) the delta string functions already exist, and (c) the frozen-dataclass-as-output pattern is well-established in the codebase. The main design decisions are around the exact dataclass shape and whether workload numbers come from statcast aggregation or from the season_baseline.

**Primary recommendation:** Add a `CrossSeasonSummary` dataclass and a `compute_cross_season_summary(data: PitcherData) -> CrossSeasonSummary | None` function to `engine.py`, returning `None` when `data.prior_season_baseline.is_empty()`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Output type is a frozen dataclass (matches PitcherData, WorkloadContext patterns in engine.py)
- Computation lives in engine.py alongside existing delta logic -- reuses existing threshold constants and delta string functions
- Per-pitch-type YoY deltas deferred to Phase 21 (Arsenal Trend Engine) -- this phase covers pitcher-level only
- Workload profile included at basic level: YoY deltas for innings pitched, pitch count averages, and appearance count
- YoY delta strings MUST reuse the same qualitative functions already in engine.py: `_velo_delta_string`, `_pplus_delta_string` (SDLT-02)
- Same thresholds: _VELO_THRESHOLD=0.5, _PPLUS_THRESHOLD=5, _SHARP_VELO_THRESHOLD=2.0, _SHARP_PPLUS_THRESHOLD=10
- Format stays consistent: "Up sharply", "Down modestly", "Steady" with numeric values in parentheses
- Cross-season summary is None (not empty dataclass, not zeroes) when prior-season data is missing (SDLT-03)
- Caller checks `if summary is not None` before rendering

### Claude's Discretion
- Exact dataclass field naming
- Whether to compute workload deltas from season_baseline or from raw statcast aggregations
- Helper function organization within engine.py

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SDLT-01 | Engine computes year-over-year deltas for pitcher-level metrics (velocity, P+, S+, L+) comparing current season baseline to prior season baseline | P+/S+/L+ available as columns in `season_baseline` and `prior_season_baseline` DataFrames. Velocity requires statcast `release_speed` grouped by `game_year`. Delta computation uses `_velo_delta_string` and `_pplus_delta_string`. |
| SDLT-02 | YoY delta strings use the same qualitative thresholds and language as within-season deltas (Steady / Up modestly / Down sharply / etc.) | Functions `_velo_delta_string(delta)` and `_pplus_delta_string(delta)` already exist at engine.py:376 and engine.py:395. Same constants: `_VELO_THRESHOLD=0.5`, `_PPLUS_THRESHOLD=5`, `_SHARP_VELO_THRESHOLD=2.0`, `_SHARP_PPLUS_THRESHOLD=10`. |
| SDLT-03 | Cross-season summary is None when prior-season data is missing (no fabricated comparisons) | `PitcherData.prior_season_baseline` is an empty DataFrame (zero rows, same schema) for single-season pitchers -- verified in Phase 19 tests (test_data.py:691-716). Guard: `if data.prior_season_baseline.is_empty(): return None`. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame operations for baseline comparison | Already used throughout engine.py and data.py |
| dataclasses (stdlib) | 3.14 | Frozen output types | Matches all existing engine output types |
| pytest | 9.0.2+ | Test framework | Already configured in pyproject.toml |

No new dependencies needed. This phase uses only existing libraries.

## Architecture Patterns

### Recommended Project Structure
```
src/pitcher_narratives/
├── engine.py          # ADD: CrossSeasonSummary + compute_cross_season_summary()
├── data.py            # NO CHANGES (Phase 19 already provides prior_season_baseline)
└── context.py         # NO CHANGES THIS PHASE (Phase 22 will consume the output)

tests/
└── test_engine.py     # ADD: cross-season summary tests
```

### Pattern 1: Dataclass Output from Engine Compute Function
**What:** Every engine analysis facet follows the same pattern: a `@dataclass` for the output shape and a `compute_*()` function that takes `PitcherData` and returns the dataclass (or `None`).
**When to use:** Always -- this is the established pattern in engine.py.
**Example (from existing code):**
```python
@dataclass
class FastballSummary:
    """Pre-computed fastball quality analysis ready for LLM."""
    pitch_type: str
    season_velo: float
    window_velo: float
    velo_delta: str
    # ... more fields ...

def compute_fastball_summary(data: PitcherData) -> FastballSummary | None:
    """Compute fastball quality analysis."""
    primary = _identify_primary_fastball(data.pitch_type_baseline)
    if primary is None:
        return None
    # ... compute fields ...
    return FastballSummary(...)
```

### Pattern 2: Delta String Reuse
**What:** Numeric deltas are passed through `_velo_delta_string()` or `_pplus_delta_string()` to produce qualitative strings like "Up sharply (+2.5 mph)" or "Steady (+3)".
**When to use:** For all YoY deltas on velocity and P+/S+/L+. The function signature is `_velo_delta_string(delta: float, threshold: float = _VELO_THRESHOLD) -> str`.
**Computation pattern:** `delta = current_season_value - prior_season_value` (positive = improvement/increase).

### Pattern 3: None-for-Missing-Data Guard
**What:** When input data is missing or insufficient, the compute function returns `None` rather than a zero-filled or empty-string output.
**When to use:** When `prior_season_baseline.is_empty()` is True.
**Example (from existing code):**
```python
def compute_fastball_summary(data: PitcherData) -> FastballSummary | None:
    primary = _identify_primary_fastball(data.pitch_type_baseline)
    if primary is None:
        return None
    # ...
```

### Pattern 4: Metric Extraction via _safe_metric
**What:** `_safe_metric(df, col, default)` safely extracts the first value of a column from a DataFrame, returning the default if the column is missing or the DataFrame is empty.
**When to use:** For extracting P+, S+, L+ from season baselines.

### Important: Dataclass is NOT Frozen
**What:** Despite the CONTEXT.md saying "frozen dataclass," the actual codebase uses plain `@dataclass` (no `frozen=True`) for all output types (FastballSummary, WorkloadContext, PitchTypeSummary, etc.).
**Recommendation:** Use plain `@dataclass` to match the existing codebase pattern. The CONTEXT.md likely meant "immutable-intent dataclass" rather than Python's `frozen=True` parameter.

### Anti-Patterns to Avoid
- **Computing velocity from CSV aggregations:** The pitcher.csv does NOT contain velocity -- velocity must be computed from statcast `release_speed`. P+/S+/L+ come from the CSV-derived season_baseline.
- **Returning an empty/zeroed CrossSeasonSummary for single-season pitchers:** Must return `None` per SDLT-03.
- **Creating new delta string functions for YoY:** SDLT-02 requires reusing `_velo_delta_string` and `_pplus_delta_string` verbatim.
- **Modifying data.py:** Data layer changes were completed in Phase 19. This phase only touches engine.py.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Qualitative delta formatting | Custom YoY string templates | `_velo_delta_string()` and `_pplus_delta_string()` | Consistency with within-season deltas (SDLT-02); thresholds already calibrated |
| Safe metric extraction | Manual `.is_empty()` + index checks | `_safe_metric(df, col, default)` | Handles missing columns and empty DataFrames gracefully |
| Season splitting | Manual season filtering | `PitcherData.season_baseline` / `prior_season_baseline` | Already split by Phase 19's `load_pitcher_data()` |

## Common Pitfalls

### Pitfall 1: Velocity Source Confusion
**What goes wrong:** Attempting to read velocity from `season_baseline` DataFrame (pitcher.csv), which does not contain a velocity column.
**Why it happens:** P+/S+/L+ are in the CSV baselines, so it's natural to assume velocity is too.
**How to avoid:** Velocity must be computed from statcast `release_speed` grouped by `game_year`. The season_baseline (from pitcher.csv) contains P+, S+, L+, xRV100_P, and other model metrics, but NOT raw physical measurements.
**Warning signs:** `KeyError: 'release_speed'` or `KeyError: 'avg_velo'` when accessing season_baseline.

### Pitfall 2: REQUIREMENTS.md vs CONTEXT.md Conflict on Workload
**What goes wrong:** Skipping workload deltas because REQUIREMENTS.md lists "Cross-season workload comparison" as Out of Scope.
**Why it happens:** The Out of Scope table was written before the discussion phase.
**How to avoid:** The CONTEXT.md explicitly overrides this: "Workload profile included at basic level: YoY deltas for innings pitched, pitch count averages, and appearance count." Follow CONTEXT.md.
**Warning signs:** Missing workload fields in the dataclass.

### Pitfall 3: Empty DataFrame vs None Semantics
**What goes wrong:** Checking `prior_season_baseline is None` instead of `prior_season_baseline.is_empty()`.
**Why it happens:** Phase 19 returns an empty DataFrame (not None) for single-season pitchers.
**How to avoid:** Guard with `if data.prior_season_baseline.is_empty(): return None`. The prior_season_baseline is ALWAYS a DataFrame (empty or populated), never None.
**Warning signs:** AttributeError when calling `.is_empty()` on None, or the function never returning None.

### Pitfall 4: Workload Metrics Need Cross-Season Statcast Aggregation
**What goes wrong:** Trying to get innings pitched or appearance count from the season_baseline DataFrame.
**Why it happens:** season_baseline only has pitch-count weighted metric averages, not aggregate workload stats.
**How to avoid:** Workload stats (total innings, appearance count, mean pitch count) must be derived from statcast data grouped by `game_year`, or from the `appearances` DataFrame which already has per-appearance IP and pitch counts. The appearances DataFrame is derived from statcast in `classify_appearances()`.
**Warning signs:** Missing columns or incorrect totals.

### Pitfall 5: Statcast game_year Column for Season Grouping
**What goes wrong:** Using `game_date.year` extraction instead of the explicit `game_year` column.
**Why it happens:** The `game_year` column exists in statcast parquet but isn't commonly used in the current codebase.
**How to avoid:** Either approach works, but `game_year` is the canonical season indicator. Alternatively, since `appearances` has `game_date`, extract year from that.

## Code Examples

### CrossSeasonSummary Dataclass (recommended shape)
```python
@dataclass
class CrossSeasonSummary:
    """Year-over-year pitcher-level metric deltas.

    Produced by compute_cross_season_summary(). None when the pitcher
    has only one season of data.
    """

    current_season: int
    prior_season: int

    # Velocity
    current_velo: float
    prior_velo: float
    velo_delta: str
    """Qualitative YoY velocity delta, e.g., 'Up 1.2 mph'."""

    # P+ / S+ / L+
    current_p_plus: float
    prior_p_plus: float
    p_plus_delta: str

    current_s_plus: float
    prior_s_plus: float
    s_plus_delta: str

    current_l_plus: float
    prior_l_plus: float
    l_plus_delta: str

    # Workload
    current_appearances: int
    prior_appearances: int
    current_ip: float
    """Total innings pitched (decimal, not baseball notation)."""
    prior_ip: float
    current_avg_pitches: float
    """Mean pitches per appearance."""
    prior_avg_pitches: float
```

### Computing Per-Season Velocity from Statcast
```python
# Source: Existing codebase pattern from engine.py:1156
# Velocity from statcast release_speed, grouped by game_year
def _per_season_velo(statcast: pl.DataFrame) -> dict[int, float]:
    """Compute mean fastball velocity per season from statcast."""
    fb = statcast.filter(pl.col("pitch_type").is_in(list(_FASTBALL_TYPES)))
    result = (
        fb.group_by("game_year")
        .agg(pl.col("release_speed").mean().alias("avg_velo"))
    )
    return {int(row["game_year"]): float(row["avg_velo"])
            for row in result.iter_rows(named=True)}
```

### Extracting P+/S+/L+ from Season Baselines
```python
# Source: Existing pattern from engine.py:1169-1171
current_p_plus = _safe_metric(data.season_baseline, "P+")
current_s_plus = _safe_metric(data.season_baseline, "S+")
current_l_plus = _safe_metric(data.season_baseline, "L+")

prior_p_plus = _safe_metric(data.prior_season_baseline, "P+")
prior_s_plus = _safe_metric(data.prior_season_baseline, "S+")
prior_l_plus = _safe_metric(data.prior_season_baseline, "L+")
```

### Computing YoY Delta Strings (reuse existing functions)
```python
# Source: engine.py:376, engine.py:395
velo_delta_str = _velo_delta_string(current_velo - prior_velo)
p_plus_delta_str = _pplus_delta_string(current_p_plus - prior_p_plus)
s_plus_delta_str = _pplus_delta_string(current_s_plus - prior_s_plus)
l_plus_delta_str = _pplus_delta_string(current_l_plus - prior_l_plus)
```

### Workload Metrics from Appearances
```python
# Source: Existing pattern from compute_workload_context (engine.py:1958)
# appearances DataFrame has: game_pk, game_date, first_inning, last_inning, n_pitches, role
def _season_workload(statcast: pl.DataFrame, appearances: pl.DataFrame) -> dict:
    """Compute workload stats for each season."""
    # Add game_year from statcast to appearances via game_pk join
    # Or extract year from game_date
    apps_with_year = appearances.with_columns(
        pl.col("game_date").dt.year().alias("season")
    )
    by_season = apps_with_year.group_by("season").agg(
        pl.len().alias("appearance_count"),
        pl.col("n_pitches").mean().alias("avg_pitches"),
    )
    return {row["season"]: row for row in by_season.iter_rows(named=True)}
```

### None Guard Pattern
```python
# Source: Established pattern in engine.py
def compute_cross_season_summary(data: PitcherData) -> CrossSeasonSummary | None:
    """Compute cross-season YoY deltas for pitcher-level metrics.

    Returns None when prior-season data is missing.
    """
    if data.prior_season_baseline.is_empty():
        return None
    # ... compute deltas ...
```

### Computing IP from Appearances
```python
# Total innings pitched per season needs _compute_ip per appearance,
# which is already done in compute_workload_context().
# For cross-season, we need to sum IP across all appearances per season.
# Note: IP is stored as baseball notation string ("5.2") in AppearanceWorkload,
# so either:
# (a) compute decimal IP directly from statcast per season, or
# (b) parse AppearanceWorkload.ip strings (fragile).
# Recommend (a): compute from statcast by counting outs per season.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-season baselines only | Multi-season baselines via Phase 19 | Phase 19 (v1.8) | Enables cross-season comparison |
| season_baseline filtered to max season | All seasons retained, split into current/prior | Phase 19 (v1.8) | prior_season_baseline available as input |

## Open Questions

1. **Innings Pitched Computation Method**
   - What we know: `_compute_ip()` in engine.py produces baseball notation strings ("5.2") per appearance. The `appearances` DataFrame has `n_pitches` but not IP as a numeric. Statcast has raw pitch-level data with inning information.
   - What's unclear: The cleanest way to get total decimal IP per season without re-parsing baseball notation strings.
   - Recommendation: Compute decimal IP from statcast by counting outs per season (each out = 1/3 of an inning). This avoids parsing "5.2" -> 5.667 conversion and is more reliable.

2. **Workload Delta Formatting**
   - What we know: CONTEXT.md suggests "X more innings", "Y fewer appearances" format (simple numeric differences, not qualitative functions).
   - What's unclear: Whether workload deltas should use the Steady/Up/Down qualitative pattern or just raw numbers.
   - Recommendation: Use raw numeric differences for workload (e.g., "+15 IP", "-3 appearances", "+8.2 avg pitches") since the existing qualitative functions are tuned for velocity and P+ scales, not workload scales.

## Project Constraints (from CLAUDE.md)

- Tech stack: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- Data format: Static parquet + CSV files, no live API calls
- Python version: 3.14+
- Use `snake_case` for functions/variables, `PascalCase` for classes
- Use Google-style docstrings with type hints on all function signatures
- Use absolute imports
- Use specific exception types, not bare `except:`
- No new dependencies needed for this phase

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_engine.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SDLT-01 | Engine computes YoY deltas for velocity, P+, S+, L+ | unit | `uv run pytest tests/test_engine.py::test_cross_season_summary_metrics -x` | Wave 0 |
| SDLT-01 | Velocity delta computed from statcast release_speed per season | unit | `uv run pytest tests/test_engine.py::test_cross_season_velo_from_statcast -x` | Wave 0 |
| SDLT-02 | Delta strings use same qualitative language as within-season | unit | `uv run pytest tests/test_engine.py::test_cross_season_delta_strings_match -x` | Wave 0 |
| SDLT-03 | Cross-season summary is None when prior-season data is missing | unit | `uv run pytest tests/test_engine.py::test_cross_season_none_single_season -x` | Wave 0 |
| SDLT-01 | Workload deltas included (appearances, IP, avg pitches) | unit | `uv run pytest tests/test_engine.py::test_cross_season_workload -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_engine.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- add cross-season summary tests (5+ test functions covering SDLT-01, SDLT-02, SDLT-03)
- [ ] Reuse `_create_synthetic_multi_year_data` helper from `tests/test_data.py` or create a similar fixture for engine tests that need multi-year statcast + baseline data

### Test Pattern from Phase 19

Phase 19 tests (in `test_data.py`) established the synthetic multi-year data pattern:
- `_create_synthetic_multi_year_data(tmp_path, years=(2025, 2026))` creates minimal parquet + CSV fixtures
- Uses `monkeypatch` to override `DATA_DIR`, `AGGS_DIR`, and `_YEARS` module-level variables
- Tests call `load_pitcher_data()` with the synthetic data and verify baseline separation

Phase 20 tests should follow the same pattern but also need:
- Statcast data with `release_speed` column (for velocity) and `game_year` column
- CSV data with `P+`, `S+`, `L+` columns (already in the synthetic data pattern)
- Both multi-year (2025+2026) and single-year (2026-only) test cases
- Appearances data sufficient to compute workload metrics

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/engine.py` -- delta string functions at lines 376-446, all dataclass definitions, compute_* patterns
- `src/pitcher_narratives/data.py` -- PitcherData dataclass (line 71), season_baseline/prior_season_baseline split (lines 437-453)
- `src/pitcher_narratives/context.py` -- integration point showing how engine outputs are consumed
- `tests/test_data.py` -- Phase 19 test patterns for multi-year synthetic data (lines 564-766)
- `tests/test_engine.py` -- existing test patterns for delta string helpers and compute functions
- `aggs/2026-pitcher.csv` -- column schema: season, level, game_type, pitcher, player_name, p_throws, team_code, n_pitches, xRV100_P, P+, S+, L+, ...
- `pyproject.toml` -- pytest configuration and dependency declarations

### Secondary (MEDIUM confidence)
- Statcast parquet schema verified: `game_date`, `game_year`, `release_speed`, `pitcher`, `pitch_type`, `inning` columns confirmed present

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all libraries verified in existing codebase
- Architecture: HIGH -- follows exact patterns already in engine.py with 20+ existing dataclass/compute pairs
- Pitfalls: HIGH -- identified from direct code inspection, not assumptions
- Delta strings: HIGH -- functions verified at specific line numbers with exact signatures
- Workload metrics: MEDIUM -- source data confirmed available, but optimal IP computation approach has a minor open question

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable domain -- existing codebase patterns unlikely to change)
