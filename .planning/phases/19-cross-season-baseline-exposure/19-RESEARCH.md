# Phase 19: Cross-Season Baseline Exposure - Research

**Researched:** 2026-04-03
**Domain:** Polars DataFrame manipulation, Pydantic dataclass evolution, Python data pipeline refactoring
**Confidence:** HIGH

## Summary

Phase 19 is a focused infrastructure change to the data layer. The current `load_pitcher_data()` in `data.py` computes per-season baselines via `compute_season_baseline()` and `compute_pitch_type_baseline()` but then filters both down to the max (most recent) season before storing them in `PitcherData`. This phase removes that filter and adds new fields to `PitcherData` so that downstream phases (20-22) can access prior-season baselines for year-over-year comparison.

The key challenge is **backwards compatibility**: all existing engine functions in `engine.py` reference `data.pitch_type_baseline` and expect it to contain only current-season rows (no `season` filtering is done in engine code). The design must either (a) add new prior-season fields while keeping existing fields unchanged, or (b) change existing fields to contain all seasons and update every engine consumer. Option (a) is strongly preferred because it satisfies success criterion #3 (no regression) with zero engine changes.

**Primary recommendation:** Add `prior_season_baseline` and `prior_pitch_type_baseline` fields to the `PitcherData` dataclass, populated by filtering the already-computed all-season baselines to `max_season - 1`. Keep existing `season_baseline` and `pitch_type_baseline` fields unchanged (filtered to max season). Single-season pitchers get empty DataFrames for the prior-season fields.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure phase).

Key constraints from prior decisions:
- v1.7 established per-season baseline grouping (not cross-season averaged)
- v1.7 load_pitcher_data() currently filters baselines to max season -- this phase removes that filter
- All data access must go through data.py (centralization decision from v1.7)

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| XSBL-01 | PitcherData exposes prior-season baselines alongside current-season baselines (both season-level and pitch-type-level) | Add `prior_season_baseline` and `prior_pitch_type_baseline` fields to PitcherData dataclass; populate in load_pitcher_data() |
| XSBL-02 | load_pitcher_data() retains all per-season baseline rows instead of filtering to max season only | Remove max-season filter in load_pitcher_data(); use all-season baselines to populate both current and prior fields |
| XSBL-03 | Prior-season baselines are empty DataFrames (not crashes) when pitcher has only one season of data | When only one season exists, set prior fields to `pl.DataFrame()` (empty); downstream code must handle empty gracefully |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python 3.14+, polars, pydantic-ai, Claude
- **Data format**: Static parquet + CSV files, no live API calls
- **Package manager**: uv
- **Naming**: snake_case for modules/functions/variables, PascalCase for classes/models
- **Error handling**: Specific exceptions, no bare `except:`
- **Testing**: pytest (dev dependency), tests in `tests/` directory
- **Linting**: ruff configured in pyproject.toml
- **Imports**: Absolute imports, alphabetically sorted within groups

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | >=1.39.3 | DataFrame operations for baseline filtering and splitting | Already used throughout data.py and engine.py |
| dataclasses | stdlib | PitcherData dataclass definition | Already used for PitcherData |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=9.0.2 | Test framework | All new test cases for prior-season baseline behavior |

No new dependencies needed. This phase modifies existing code only.

## Architecture Patterns

### Current Data Flow (to be modified)
```
load_pitcher_data(pitcher_id)
  -> load_agg_csvs(pitcher_id)        # loads all years' CSVs
  -> compute_season_baseline(...)      # groups by (pitcher, season) -> all seasons
  -> compute_pitch_type_baseline(...)  # groups by (pitcher, season, pitch_type) -> all seasons
  -> FILTER to max season only         # <-- THIS IS WHAT CHANGES
  -> PitcherData(season_baseline=..., pitch_type_baseline=...)
```

### Proposed Data Flow (after phase 19)
```
load_pitcher_data(pitcher_id)
  -> load_agg_csvs(pitcher_id)
  -> compute_season_baseline(...)      # all seasons
  -> compute_pitch_type_baseline(...)  # all seasons
  -> SPLIT into current + prior        # <-- NEW LOGIC
  -> PitcherData(
       season_baseline=current,            # max season (unchanged behavior)
       pitch_type_baseline=current_pt,     # max season (unchanged behavior)
       prior_season_baseline=prior,        # max_season - 1 (NEW)
       prior_pitch_type_baseline=prior_pt, # max_season - 1 (NEW)
     )
```

### Pattern 1: Additive Dataclass Extension
**What:** Add new optional fields to PitcherData without changing existing ones
**When to use:** When downstream consumers must not break
**Example:**
```python
@dataclass
class PitcherData:
    """Bundle of all loaded and processed data for a pitcher."""

    statcast: pl.DataFrame
    appearances: pl.DataFrame
    window_appearances: pl.DataFrame
    season_baseline: pl.DataFrame          # current season only (unchanged)
    pitch_type_baseline: pl.DataFrame      # current season only (unchanged)
    prior_season_baseline: pl.DataFrame    # NEW: prior season (empty if single-season)
    prior_pitch_type_baseline: pl.DataFrame  # NEW: prior season (empty if single-season)
    agg_csvs: dict[str, pl.DataFrame]
    pitcher_id: int
    pitcher_name: str
    throws: str
```

### Pattern 2: Season Splitting Logic
**What:** Split all-season baselines into current and prior using max_season
**When to use:** In load_pitcher_data() after computing baselines
**Example:**
```python
# After computing season_baseline_all and pitch_type_baseline_all...
if "season" in season_baseline_all.columns and not season_baseline_all.is_empty():
    max_season = season_baseline_all["season"].max()
    season_baseline = season_baseline_all.filter(pl.col("season") == max_season)
    prior_season_baseline = season_baseline_all.filter(pl.col("season") < max_season)
else:
    season_baseline = season_baseline_all
    prior_season_baseline = pl.DataFrame()

# Same pattern for pitch_type_baseline_all
if "season" in pitch_type_baseline_all.columns and not pitch_type_baseline_all.is_empty():
    max_season = pitch_type_baseline_all["season"].max()
    pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") == max_season)
    prior_pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") < max_season)
else:
    pitch_type_baseline = pitch_type_baseline_all
    prior_pitch_type_baseline = pl.DataFrame()
```

### Anti-Patterns to Avoid
- **Changing existing field semantics:** Do NOT change `season_baseline` to contain all seasons. That would break every engine function that reads `data.pitch_type_baseline` without season-filtering.
- **Using None for empty prior-season:** Use `pl.DataFrame()` (empty DataFrame), not `None`. This avoids `AttributeError` in downstream code and matches success criterion #2.
- **Filtering to exactly max_season - 1:** Use `< max_season` rather than `== max_season - 1`. While only 2 years exist today, this future-proofs for 3+ seasons (deferred but good to not paint into a corner). However, note that phases 20-21 specifically compare current vs prior (2-season comparison), so the prior fields should contain only the single prior season. Given the out-of-scope note about "three-or-more season trend lines", filtering to `== max_season - 1` is actually correct for the current requirement. Use `< max_season` if there's exactly one prior season, but be aware phases 20-21 expect a single prior season row.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Empty DataFrame creation | `pl.DataFrame({"col": []})` with explicit schema | `pl.DataFrame()` | polars handles empty DataFrames gracefully; no need to pre-define schema for empties |
| Season detection | Custom logic to figure out years | `df["season"].max()` / `df["season"].unique()` | polars column operations are the idiomatic way |
| DataFrame filtering | Python loops over rows | `df.filter(pl.col("season") == val)` | polars vectorized filter is correct pattern |

## Common Pitfalls

### Pitfall 1: Empty DataFrame Column Mismatch
**What goes wrong:** `pl.DataFrame()` has no columns, so downstream code that accesses `.columns` or filters on specific column names gets unexpected behavior.
**Why it happens:** When prior-season baseline is empty (single-season pitcher), downstream phases (20-21) will try to read columns like "P+", "season", etc.
**How to avoid:** Document that downstream consumers must check `df.is_empty()` before accessing columns. Phase 20-21 will need to handle empty prior baselines by returning `None` for cross-season summaries (per SDLT-03 and ATRN-03). The empty-check pattern already exists in the codebase (load_pitcher_data already checks `not season_baseline_all.is_empty()`).
**Warning signs:** `ColumnNotFoundError` or `SchemaError` in tests with single-season test data.

### Pitfall 2: Dataclass Field Ordering
**What goes wrong:** Adding fields to the middle of a `@dataclass` breaks positional construction.
**Why it happens:** Python dataclasses are order-sensitive for positional args. Any existing code constructing PitcherData positionally would break.
**How to avoid:** Check all PitcherData construction sites. Currently there is exactly ONE: `load_pitcher_data()` in data.py (line 434) using keyword arguments. Tests may also construct PitcherData. Add new fields after existing fields to maintain keyword-arg compatibility.
**Warning signs:** `TypeError: __init__() got an unexpected keyword argument` in tests.

### Pitfall 3: Test Data Must Be Multi-Year
**What goes wrong:** Tests pass trivially because test data only has one season, never exercising the prior-season path.
**Why it happens:** Existing test fixtures are single-season.
**How to avoid:** Create test fixtures with both 2025 and 2026 season data. Use `monkeypatch` + `tmp_path` pattern already established in test_data.py (see `test_load_statcast_multi_year`, `test_load_agg_csvs_multi_year`).
**Warning signs:** All tests pass but prior-season fields are always empty DataFrames.

### Pitfall 4: Regression in Engine Functions
**What goes wrong:** Changing `season_baseline` or `pitch_type_baseline` semantics causes engine functions to produce different output.
**Why it happens:** Engine functions access `data.pitch_type_baseline` at 6 distinct locations (lines 1145, 1168, 1320, 1468, 1788, 1885) and assume it contains only current-season data.
**How to avoid:** Keep `season_baseline` and `pitch_type_baseline` filtered to max season (current behavior). Only add NEW fields for prior season. Run full test suite after changes.
**Warning signs:** test_engine.py failures on any compute function.

### Pitfall 5: Season Column Missing in Empty Baselines
**What goes wrong:** `compute_season_baseline()` and `compute_pitch_type_baseline()` can return DataFrames without a "season" column if the input has no season column.
**Why it happens:** The `group_by(["pitcher", "season"])` will produce a DataFrame with season in columns, but an empty input might not.
**How to avoid:** Guard the max_season extraction with `if "season" in df.columns and not df.is_empty()` -- this pattern is already used in the current code.
**Warning signs:** `ColumnNotFoundError` on "season" during baseline splitting.

## Code Examples

### Current load_pitcher_data() Baseline Logic (lines 416-430)
```python
# Current code -- filters to max season
season_baseline_all = compute_season_baseline(agg_csvs["pitcher"])
pitch_type_baseline_all = compute_pitch_type_baseline(agg_csvs["pitcher_type"])

if "season" in season_baseline_all.columns and not season_baseline_all.is_empty():
    max_season = season_baseline_all["season"].max()
    season_baseline = season_baseline_all.filter(pl.col("season") == max_season)
else:
    season_baseline = season_baseline_all

if "season" in pitch_type_baseline_all.columns and not pitch_type_baseline_all.is_empty():
    max_season = pitch_type_baseline_all["season"].max()
    pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") == max_season)
else:
    pitch_type_baseline = pitch_type_baseline_all
```

### Proposed Replacement
```python
# New code -- splits into current + prior
season_baseline_all = compute_season_baseline(agg_csvs["pitcher"])
pitch_type_baseline_all = compute_pitch_type_baseline(agg_csvs["pitcher_type"])

if "season" in season_baseline_all.columns and not season_baseline_all.is_empty():
    max_season = season_baseline_all["season"].max()
    season_baseline = season_baseline_all.filter(pl.col("season") == max_season)
    prior_season_baseline = season_baseline_all.filter(pl.col("season") < max_season)
else:
    season_baseline = season_baseline_all
    prior_season_baseline = pl.DataFrame()

if "season" in pitch_type_baseline_all.columns and not pitch_type_baseline_all.is_empty():
    max_season = pitch_type_baseline_all["season"].max()
    pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") == max_season)
    prior_pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") < max_season)
else:
    pitch_type_baseline = pitch_type_baseline_all
    prior_pitch_type_baseline = pl.DataFrame()
```

### Engine Consumer Locations (unchanged)
These 6 locations in engine.py reference `data.pitch_type_baseline` and must NOT change:
- Line 1145: `_identify_primary_fastball(data.pitch_type_baseline)` in `compute_fastball_summary`
- Line 1168: `data.pitch_type_baseline.filter(...)` in `compute_fastball_summary`
- Line 1320: `data.pitch_type_baseline.sort(...)` in `compute_arsenal_summary`
- Line 1468: `data.pitch_type_baseline.sort(...)` in `compute_platoon_mix`
- Line 1788: `data.pitch_type_baseline.sort(...)` in `compute_execution_metrics`
- Line 1885: `data.pitch_type_baseline.sort(...)` in `compute_intermediate_probabilities`

No engine function references `data.season_baseline` directly (confirmed by grep).

### Test Pattern: Multi-Year PitcherData
```python
def test_prior_season_baseline_multi_year(tmp_path, monkeypatch):
    """XSBL-01: PitcherData has prior-season baselines when multi-year data exists."""
    # ... setup tmp_path with 2025 + 2026 CSVs and parquets ...
    data = load_pitcher_data(12345, window_days=30)
    
    assert not data.season_baseline.is_empty()
    assert data.season_baseline["season"].unique().to_list() == [2026]
    
    assert not data.prior_season_baseline.is_empty()
    assert data.prior_season_baseline["season"].unique().to_list() == [2025]

def test_prior_season_baseline_single_year(tmp_path, monkeypatch):
    """XSBL-03: Prior baselines are empty when only one season exists."""
    # ... setup tmp_path with only 2026 data ...
    data = load_pitcher_data(12345, window_days=30)
    
    assert not data.season_baseline.is_empty()
    assert data.prior_season_baseline.is_empty()
    assert data.prior_pitch_type_baseline.is_empty()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-year CSV loading | Multi-year CSV loading via _YEARS loop | v1.7 (Phase 16-17) | load_agg_csvs now loads 2025+2026 CSVs |
| Cross-season averaged baselines | Per-season baseline grouping | v1.7 (Phase 16) | compute_season_baseline groups by (pitcher, season) |
| All seasons in PitcherData | Max-season filter in load_pitcher_data | v1.7 (Phase 17) | Engine gets single-season baseline only |

**Key insight:** v1.7 laid the groundwork by making baselines per-season. This phase simply exposes what was previously computed but filtered away.

## Open Questions

1. **Prior-season field naming convention**
   - What we know: The fields need "prior" semantics to distinguish from current
   - What's unclear: `prior_season_baseline` vs `prev_season_baseline` vs `season_baseline_prior`
   - Recommendation: Use `prior_season_baseline` and `prior_pitch_type_baseline` -- "prior" is conventional in baseball analytics and consistent with the ROADMAP language ("prior-season baselines")

2. **Should `__all__` in data.py be updated?**
   - What we know: PitcherData is already exported
   - What's unclear: Whether the new fields need separate documentation
   - Recommendation: No `__all__` change needed since PitcherData is the exported symbol and its fields are just attributes. Add the new fields to the PitcherData docstring.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_data.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| XSBL-01 | PitcherData exposes prior-season baselines when multi-year data exists | unit | `uv run pytest tests/test_data.py::test_prior_season_baseline_multi_year -x` | Wave 0 |
| XSBL-01 | PitcherData exposes prior pitch-type baselines when multi-year data exists | unit | `uv run pytest tests/test_data.py::test_prior_pitch_type_baseline_multi_year -x` | Wave 0 |
| XSBL-02 | load_pitcher_data retains all seasons internally (current + prior split) | unit | `uv run pytest tests/test_data.py::test_load_pitcher_data_retains_all_seasons -x` | Wave 0 |
| XSBL-03 | Prior baselines are empty DataFrames when single season | unit | `uv run pytest tests/test_data.py::test_prior_baseline_empty_single_season -x` | Wave 0 |
| XSBL-03 | Prior baselines do not cause crash for single-season pitcher | unit | `uv run pytest tests/test_data.py::test_single_season_no_crash -x` | Wave 0 |
| Regression | Existing engine functions produce identical output | integration | `uv run pytest tests/test_engine.py -x -q` | Existing |
| Regression | Existing data tests still pass | unit | `uv run pytest tests/test_data.py -x -q` | Existing |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_data.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_data.py::test_prior_season_baseline_multi_year` -- covers XSBL-01
- [ ] `tests/test_data.py::test_prior_pitch_type_baseline_multi_year` -- covers XSBL-01
- [ ] `tests/test_data.py::test_load_pitcher_data_retains_all_seasons` -- covers XSBL-02
- [ ] `tests/test_data.py::test_prior_baseline_empty_single_season` -- covers XSBL-03
- [ ] `tests/test_data.py::test_single_season_no_crash` -- covers XSBL-03

Note: Wave 0 tests should use the established `tmp_path` + `monkeypatch` pattern from existing multi-year tests in test_data.py.

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/data.py` - Direct source code inspection of PitcherData, load_pitcher_data(), compute_season_baseline(), compute_pitch_type_baseline()
- `src/pitcher_narratives/engine.py` - Grep audit of all 6 locations accessing data.pitch_type_baseline; confirmed zero references to data.season_baseline
- `tests/test_data.py` - 39 existing tests all passing; multi-year test patterns established
- `src/pitcher_narratives/context.py` - Verified PitcherContext assembly does not access baselines directly (goes through engine functions)

### Secondary (MEDIUM confidence)
- `.planning/ROADMAP.md` - Phase 19-22 dependency chain and success criteria
- `.planning/REQUIREMENTS.md` - XSBL-01/02/03 requirement definitions
- `.planning/STATE.md` - v1.7 decisions about per-season grouping

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies; pure modification of existing polars/dataclass code
- Architecture: HIGH - Additive field pattern is well-established; current code structure fully understood from source inspection
- Pitfalls: HIGH - All consumer sites identified by grep; test patterns proven in existing test_data.py

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable codebase, no external dependencies changing)
