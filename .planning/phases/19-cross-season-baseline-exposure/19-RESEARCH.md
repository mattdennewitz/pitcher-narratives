# Phase 19: Cross-Season Baseline Exposure - Research

**Researched:** 2026-04-08
**Domain:** Polars DataFrame splitting, Python dataclass extension, data pipeline modification
**Confidence:** HIGH

## Summary

Phase 19 is a focused data-layer change: split the already-computed multi-season baseline DataFrames into current-season and prior-season (N-1) slices, and expose the prior-season slices as new fields on the `PitcherData` dataclass. The critical insight from code inspection is that `load_pitcher_data()` already computes all-season baselines via `compute_season_baseline()` and `compute_pitch_type_baseline()`, then discards non-current seasons in a filter step. The work is literally retaining what's currently thrown away.

Engine.py already contains scaffolding (`compute_cross_season_summary`, `CrossSeasonSummary`) that expects `data.prior_season_baseline` -- this phase delivers what that scaffolding needs. The scaffolding itself is broken (references undefined `_per_season_velo`) but per D-07 we do NOT fix it; Phase 20 owns that.

**Primary recommendation:** Add `prior_season_baseline` and `prior_pitch_type_baseline` fields to `PitcherData`, populate them in `load_pitcher_data()` by filtering `season_baseline_all` / `pitch_type_baseline_all` to `max_season - 1`, and use schema-preserving empty DataFrames (via `.clear()`) when no prior season exists.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** "Prior season" means the immediate preceding season only (e.g., 2025 when current is 2026)
- **D-02:** Do not aggregate or include all non-current seasons -- strictly N-1
- **D-03:** Add both `prior_season_baseline` and `prior_pitch_type_baseline` fields to PitcherData in this phase
- **D-04:** Both use the same pattern as current baselines -- split the existing `season_baseline_all` / `pitch_type_baseline_all` into current (max season) + prior (max season - 1)
- **D-05:** When a pitcher has only one season of data, prior baselines are empty DataFrames (not None, not crash) -- per XSBL-03
- **D-06:** Existing engine functions that consume `season_baseline` and `pitch_type_baseline` must continue working unchanged -- no regression
- **D-07:** Do NOT clean up the broken `compute_cross_season_summary()` / `CrossSeasonSummary` / `_per_season_velo()` scaffolding in engine.py -- that belongs to Phase 20 (Season-Delta Engine)
- **D-08:** Phase 19 only exposes data; Phase 20 owns the computation that consumes it

### Claude's Discretion
- Exact implementation of the season splitting logic in `load_pitcher_data()`
- Whether to use a helper function or inline the split
- Empty DataFrame construction approach (schema-preserving vs plain empty)

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| XSBL-01 | PitcherData exposes prior-season baselines alongside current-season baselines (both season-level and pitch-type-level) | Add `prior_season_baseline` and `prior_pitch_type_baseline` fields to PitcherData dataclass; populate in `load_pitcher_data()` |
| XSBL-02 | load_pitcher_data() retains all per-season baseline rows instead of filtering to max season only | The all-season baselines (`season_baseline_all`, `pitch_type_baseline_all`) are already computed at lines 416-417; currently only max-season is kept (lines 419-430). Split into current + prior instead of discarding |
| XSBL-03 | Prior-season baselines are empty DataFrames (not crashes) when pitcher has only one season of data | Use schema-preserving `.clear()` on the all-season DataFrame to produce typed empty DataFrames; verified that `_safe_metric()` and `is_empty()` both handle this correctly |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python, polars, pydantic-ai, Claude -- no new dependencies needed for this phase
- **Python version:** 3.14+
- **Data format:** Static parquet + CSV files, no live API calls
- **Naming:** snake_case for fields, PascalCase for classes
- **Error handling:** Specific exception types, not bare except
- **GSD workflow:** All changes through GSD commands

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame operations for baseline splitting | Already in use for all data operations |
| dataclasses | stdlib | PitcherData definition | Already used for PitcherData |

No new dependencies required. This phase modifies existing code only.

## Architecture Patterns

### Recommended Change Structure
```
src/pitcher_narratives/data.py    # PitcherData + load_pitcher_data() changes
tests/test_data.py                # New tests for prior-season baselines
```

### Pattern 1: Season Splitting via Filter
**What:** Filter the all-season baseline DataFrame by `max_season - 1` to get prior-season data
**When to use:** This is the only pattern needed -- directly mirrors the existing current-season filter
**Example:**
```python
# Current code (lines 419-424):
if "season" in season_baseline_all.columns and not season_baseline_all.is_empty():
    max_season = season_baseline_all["season"].max()
    season_baseline = season_baseline_all.filter(pl.col("season") == max_season)
else:
    season_baseline = season_baseline_all

# New prior-season extraction (same block):
    prior_season_val = max_season - 1
    prior_rows = season_baseline_all.filter(pl.col("season") == prior_season_val)
    prior_season_baseline = prior_rows if not prior_rows.is_empty() else season_baseline_all.clear()
```

### Pattern 2: Schema-Preserving Empty DataFrames
**What:** Use `df.clear()` to create an empty DataFrame that retains column names and types
**When to use:** When a pitcher has only one season of data (XSBL-03)
**Why:** Downstream code like `compute_cross_season_summary()` checks `data.prior_season_baseline.is_empty()` (line 2213) and also accesses `data.prior_season_baseline["season"]` (line 2218). Schema-preserving empties ensure column-access on non-empty frames works, while `is_empty()` short-circuits on empty ones. Verified: `_safe_metric()` handles both plain-empty and schema-empty identically, but schema-preserving is strictly safer.
**Example:**
```python
# Schema-preserving empty:
empty = season_baseline_all.clear()
# Result: 0 rows, same columns and dtypes as source
# empty.is_empty() -> True
# "P+" in empty.columns -> True
```

### Pattern 3: Dataclass Field Extension
**What:** Add new fields to `PitcherData` with explicit type annotations
**When to use:** Always for this pattern -- `PitcherData` is a `@dataclass`, not a Pydantic model
**Example:**
```python
@dataclass
class PitcherData:
    # ... existing fields ...
    season_baseline: pl.DataFrame
    pitch_type_baseline: pl.DataFrame
    prior_season_baseline: pl.DataFrame      # NEW
    prior_pitch_type_baseline: pl.DataFrame   # NEW
    agg_csvs: dict[str, pl.DataFrame]
    # ...
```
**Note:** Field ordering matters in dataclasses -- new fields must go after existing baselines and before subsequent fields to maintain readable ordering. Since PitcherData uses positional construction (line 434), the constructor call must also be updated.

### Anti-Patterns to Avoid
- **Optional[pl.DataFrame] with None:** Decision D-05 explicitly says "not None" -- always use empty DataFrames
- **Modifying engine.py:** Decision D-07/D-08 explicitly bars touching the broken cross-season scaffolding
- **Aggregating all non-current seasons:** Decision D-02 says strictly N-1, not "all prior"
- **Changing `compute_season_baseline()` or `compute_pitch_type_baseline()`:** These functions already produce correct multi-season output; the splitting belongs in `load_pitcher_data()`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Empty DataFrames with matching schema | Manual Schema() construction | `df.clear()` | Polars `.clear()` handles all column types automatically and tracks schema changes |
| Season identification | Parsing date strings for year | `season` column already exists | Both baseline DataFrames have an integer `season` column |

## Common Pitfalls

### Pitfall 1: Dataclass Constructor Ordering
**What goes wrong:** Adding new fields to `PitcherData` in the wrong position breaks the existing positional `PitcherData(...)` call in `load_pitcher_data()`
**Why it happens:** Python dataclasses use positional arguments by default. The constructor at line 434 passes all fields positionally.
**How to avoid:** Update both the field declarations AND the constructor call in lockstep. Place new fields logically after the existing baseline fields.
**Warning signs:** `TypeError: PitcherData.__init__() got multiple values for argument`

### Pitfall 2: Prior Season Might Not Be max_season - 1
**What goes wrong:** If a pitcher played in 2024 and 2026 but not 2025, filtering for `max_season - 1` (2025) yields empty -- which is correct per D-01 but might surprise.
**Why it happens:** The data only covers `_YEARS = [2025, 2026]`, so this is actually impossible with current data. But the logic should be correct regardless.
**How to avoid:** Filter for `max_season - 1` as required by D-01. If no rows match, return schema-preserving empty. This is the correct behavior -- "prior season" means exactly N-1, not "most recent other season."
**Warning signs:** None -- this is working as designed.

### Pitfall 3: Test Regression from PitcherData Field Addition
**What goes wrong:** Existing tests that construct `PitcherData` manually or assert on its fields break.
**Why it happens:** Adding required fields to a dataclass without defaults breaks any manual construction.
**How to avoid:** Verified: no tests manually construct `PitcherData` -- test_engine.py uses `load_pitcher_data()` directly (via `TEST_PITCHER`). But `test_data.py::test_load_pitcher_data_returns_complete_bundle` uses `hasattr` checks and will need new assertions.
**Warning signs:** Run existing tests before AND after the change.

### Pitfall 4: Schema Mismatch Between Current and Prior Baselines
**What goes wrong:** If the 2025 CSV and 2026 CSV have different columns, the prior-season baseline schema won't match the current-season schema.
**Why it happens:** `pl.concat(frames, how="diagonal_relaxed")` handles this during loading, filling missing columns with null. After `compute_season_baseline()` groups by `[pitcher, season]`, both seasons have the same schema.
**How to avoid:** This is already handled by the existing data pipeline. Verified: `compute_season_baseline()` output has a single consistent schema across all seasons.
**Warning signs:** None -- already handled.

## Code Examples

### Current load_pitcher_data() Baseline Logic (lines 416-430)
```python
# Source: src/pitcher_narratives/data.py lines 416-430
season_baseline_all = compute_season_baseline(agg_csvs["pitcher"])
pitch_type_baseline_all = compute_pitch_type_baseline(agg_csvs["pitcher_type"])

# Filter baselines to most recent season for engine consumption
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

### Engine.py Consumer (lines 2213-2228) -- DO NOT MODIFY
```python
# Source: src/pitcher_narratives/engine.py lines 2213-2228
# This is the downstream consumer we're enabling -- Phase 20 will fix/own it
if data.prior_season_baseline.is_empty():
    return None
prior_seasons = data.prior_season_baseline["season"].unique().to_list()
prior_season = int(max(prior_seasons))
prior_p_plus = _safe_metric(data.prior_season_baseline, "P+")
prior_s_plus = _safe_metric(data.prior_season_baseline, "S+")
prior_l_plus = _safe_metric(data.prior_season_baseline, "L+")
```

### Verified Baseline DataFrame Schemas
```python
# season_baseline schema (from compute_season_baseline):
# Schema({'pitcher': Int64, 'season': Int64, 'n_pitches': Int64,
#         'player_name': String, 'p_throws': String, 'team_code': String,
#         'xRV100_P': Float64, 'P+': Float64, 'P+2080': Float64,
#         'xRV100_S': Float64, 'S+': Float64, 'S+2080': Float64,
#         'xRV100_L': Float64, 'L+': Float64, 'L+2080': Float64,
#         'xHR100_pctl': Float64, 'xHR100_P': Float64, 'xHR100_S': Float64,
#         'xSwing_P': Float64, 'xSwing_S': Float64, 'xSwSt_P': Float64,
#         'xSwSt_S': Float64, 'xWhiff_P': Float64, 'xWhiff_S': Float64,
#         'xGOr_P': Float64, 'xGOr_S': Float64, 'xPUr_P': Float64,
#         'xPUr_S': Float64})
# 28 columns total

# pitch_type_baseline schema (from compute_pitch_type_baseline):
# Same as above PLUS 'pitch_type': String and 'usage_pct': Float64
# 30 columns total
```

### Test Data Availability
```python
# Multi-season pitcher (for happy path):
TEST_PITCHER = 592155  # Booser, Cam -- has data in both 2025 AND 2026

# Single-season pitcher (for XSBL-03 edge case):
# 823810 (Moring, Reed) -- only in 2026
# 669699 (Shewmake, Braden) -- only in 2026  
# 664074 (Ponce, Cody) -- only in 2026
# 141 pitchers exist in 2026 only
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_data.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| XSBL-01 | PitcherData has prior_season_baseline and prior_pitch_type_baseline fields populated for multi-season pitcher | unit | `uv run pytest tests/test_data.py::test_prior_season_baseline_populated -x` | Wave 0 |
| XSBL-01 | prior_season_baseline contains N-1 season data only | unit | `uv run pytest tests/test_data.py::test_prior_season_baseline_is_n_minus_1 -x` | Wave 0 |
| XSBL-02 | load_pitcher_data retains prior-season rows in new fields | unit | `uv run pytest tests/test_data.py::test_load_pitcher_data_retains_prior_season -x` | Wave 0 |
| XSBL-02 | Current season baseline unchanged (regression) | unit | `uv run pytest tests/test_data.py::test_current_season_baseline_unchanged -x` | Wave 0 |
| XSBL-03 | Prior baselines are empty DataFrames for single-season pitcher | unit | `uv run pytest tests/test_data.py::test_prior_baseline_empty_single_season -x` | Wave 0 |
| XSBL-03 | Empty prior baselines don't crash, are not None | unit | `uv run pytest tests/test_data.py::test_prior_baseline_not_none -x` | Wave 0 |
| D-06 | Existing engine functions work unchanged | integration | `uv run pytest tests/test_engine.py -x` | Existing (39+ tests) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_data.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_data.py` -- add XSBL-01, XSBL-02, XSBL-03 test cases (file exists, needs new test functions)
- No new test files or fixtures needed -- existing `TEST_PITCHER = 592155` has multi-season data

## Open Questions

1. **Field ordering in PitcherData dataclass**
   - What we know: Current fields are positional. Adding fields mid-dataclass changes constructor order.
   - What's unclear: Whether to place new fields immediately after their current-season counterparts or at the end of the dataclass.
   - Recommendation: Place after `pitch_type_baseline` (before `agg_csvs`) for logical grouping. Update the constructor call accordingly. This is within Claude's discretion per CONTEXT.md.

2. **Helper function vs inline splitting**
   - What we know: The split logic is ~8 lines for each baseline type. The current code already has inline filter logic.
   - What's unclear: Whether a helper function improves readability.
   - Recommendation: Inline is fine -- the logic is simple and co-located with the existing current-season filter. A helper adds indirection for minimal benefit. This is within Claude's discretion per CONTEXT.md.

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/data.py` -- full source read, PitcherData dataclass (line 71), load_pitcher_data() (line 395), baseline computation and filtering (lines 416-430)
- `src/pitcher_narratives/engine.py` -- CrossSeasonSummary (line 1031), compute_cross_season_summary() (line 2196), all `data.season_baseline` / `data.pitch_type_baseline` consumers
- `tests/test_data.py` -- 39 passing tests verified, test patterns confirmed
- `tests/test_engine.py` -- confirmed no manual PitcherData construction, uses load_pitcher_data()
- Live data verification via `uv run python3` -- confirmed schemas, multi-season availability, empty DataFrame behavior

### Secondary (MEDIUM confidence)
- Polars `.clear()` method -- verified via live interpreter, produces schema-preserving empty DataFrames

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, existing polars patterns only
- Architecture: HIGH -- change is surgically scoped to 2 locations (PitcherData fields + load_pitcher_data body)
- Pitfalls: HIGH -- verified all consumers, tested edge cases, confirmed test infrastructure

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable -- no external dependencies or API changes)
