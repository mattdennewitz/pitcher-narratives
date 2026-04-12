# Phase 18: Consumer Module Updates - Research

**Researched:** 2026-04-02
**Domain:** Refactoring data access patterns -- routing all CSV/parquet reads through data.py
**Confidence:** HIGH

## Summary

Phase 18 is a pure refactoring phase. Three modules -- engine.py, scout.py, and resolver.py -- bypass data.py by calling `pl.read_csv()` or `pl.read_parquet()` directly with hardcoded `2026-` filenames. These bypasses miss game-type filtering and multi-year data concatenation that data.py now provides (Phase 16 + Phase 17).

The key insight is that the bypasses fall into two categories: (1) **league-wide reads** (engine.py league baselines, engine.py percentile computation, scout.py scanning, scout.py velocity baselines) and (2) **name-table reads** (resolver.py). data.py currently only has pitcher-filtered loaders (`load_statcast(pitcher_id)` and `load_agg_csvs(pitcher_id)`), so it needs **two new functions** for league-wide access: `load_all_statcast()` and `load_full_agg()`.

Additionally, scout.py calls `load_csv()` with wrong arity (1 arg instead of 2), which would crash at runtime. Seven engine.py tests fail because Phase 16's game-type filtering changed data for the test pitcher (Booser #592155) -- his primary fastball shifted from FC to FF. These test assertions need updating to match filtered data.

**Primary recommendation:** Add `load_all_statcast(columns)` and `load_full_agg(grain)` to data.py, then mechanically replace each bypass point to use these functions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked. This is an infrastructure phase with discuss skipped.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure refactoring phase. Key constraints:
- `engine.py` must not contain any direct `read_csv` or `read_parquet` calls after this phase
- `resolver.py` must build its pitcher name table from all available parquet files (all years in `_YEARS`)
- `scout.py` must not contain any direct CSV or parquet reads
- All data access must route through `data.py` functions
- `grep "read_csv\|read_parquet" src/pitcher_narratives/ | grep -v data.py` must return zero results

### Deferred Ideas (OUT OF SCOPE)
None -- refactoring phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CSMR-01 | engine.py direct CSV read eliminated and routed through data.py load_full_agg() | New `load_full_agg(grain)` function in data.py replaces lines 230-232 and 1791; new `load_all_statcast(columns)` replaces lines 200-203 |
| CSMR-02 | resolver.py builds name table from all available parquet files (not just 2026) | New `load_all_statcast(columns)` loads all years; resolver passes `columns=["pitcher","player_name"]` |
| CSMR-03 | scout.py hardcoded CSV loads and parquet reads replaced with data.py functions | `load_full_agg(grain)` replaces 4 hardcoded `load_csv("2026-...")` calls; `load_all_statcast(columns)` replaces direct parquet read in `_compute_velo_baselines()` |
</phase_requirements>

## Architecture Patterns

### New data.py API Functions

Two new public functions are needed because data.py currently only has pitcher-filtered loaders:

#### `load_all_statcast(columns: list[str] | None = None) -> pl.DataFrame`
- Reads parquet files for all years in `_YEARS`
- Applies `filter_game_type()` to each
- Concatenates across years
- Optional `columns` parameter for memory efficiency (engine.py only needs 7 columns, resolver.py only needs 2)
- Skips missing year files gracefully (same pattern as `load_statcast()`)
- Does NOT filter by pitcher

#### `load_full_agg(grain: str) -> pl.DataFrame`
- Reads CSV files for a single grain across all years in `_YEARS`
- Applies `filter_game_type()` and date parsing (same as `load_csv()`)
- Concatenates across years
- Does NOT filter by pitcher
- Follows existing `load_csv()` pattern but iterates `_YEARS`

### Bypass Point Inventory

There are exactly **5 bypass points** across 3 files:

| # | File | Line | Current Code | Replacement |
|---|------|------|-------------|-------------|
| 1 | engine.py | 200-203 | `pl.read_parquet(PARQUET_PATH, columns=[...])` | `load_all_statcast(columns=[...])` |
| 2 | engine.py | 230-232 | `pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")` | `load_full_agg("pitcher_type")` |
| 3 | engine.py | 1791 | `pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")` | `load_full_agg("pitcher_type")` |
| 4 | scout.py | 114-117 | `load_csv("2026-*.csv")` (wrong arity -- 1 arg, needs 2) | `load_full_agg("pitcher_appearance")`, etc. |
| 5 | scout.py | 238-239 | `pl.read_parquet(PARQUET_PATH, columns=[...])` | `load_all_statcast(columns=[...])` |

Plus 1 indirect bypass:

| # | File | Line | Current Code | Replacement |
|---|------|------|-------------|-------------|
| 6 | resolver.py | 111 | `pl.read_parquet(PARQUET_PATH, columns=[...])` | `load_all_statcast(columns=["pitcher","player_name"])` |

### Import Cleanup After Refactoring

| File | Remove from imports | Add to imports |
|------|-------------------|----------------|
| engine.py | `AGGS_DIR`, `PARQUET_PATH` | `load_all_statcast`, `load_full_agg` |
| scout.py | `AGGS_DIR`, `PARQUET_PATH`, `load_csv` | `load_all_statcast`, `load_full_agg` |
| resolver.py | `PARQUET_PATH` | `load_all_statcast` |

### Resolver Cache Invalidation

resolver.py caches its name table in a module-level `_name_table` variable. After switching to multi-year loading, the cache must be cleared between test runs or the resolver will not pick up pitchers from additional years. The existing `_name_table = None` reset pattern is sufficient -- no changes needed to caching logic, just to `_build_name_table()` to call `load_all_statcast(columns=["pitcher","player_name"])` instead of `pl.read_parquet(PARQUET_PATH, ...)`.

### Scout.py `load_csv()` Arity Fix

scout.py line 114-117 calls `load_csv("2026-pitcher_appearance.csv")` with 1 argument, but `load_csv(filename, pitcher_id)` requires 2. This would crash at runtime. The fix is to replace these with `load_full_agg(grain)` calls (which return all-pitcher data across all years), or call `load_csv(filename, None)`. The `load_full_agg()` approach is better because it also handles multi-year concatenation.

### Scout.py `_compute_velo_baselines()` Multi-Year

This function reads a single parquet file. After refactoring, it will get data from all years. The function computes per-pitcher season velocity averages and per-game velocities, then joins them. With multi-year data, the season average will span all years -- this is acceptable for the velocity delta signal because:
- Most pitchers will only appear in one year's recent window anyway
- The `group_by("pitcher")` for `season_velo` will produce a single cross-year average
- If per-season granularity is needed later, it can be added (deferred)

### Engine.py `compute_league_baselines()` Multi-Year

This function is cached and computes league-wide pitch type averages. With multi-year data, the averages will include 2025 and 2026 data. This is correct behavior -- league baselines should reflect all available data. The S-variant benchmarks from `pitcher_type.csv` will also span both years, which is appropriate for league-level percentile computation.

### Engine.py `_compute_xrv100_percentile()` Multi-Year

Line 1791 loads full pitcher_type CSV for percentile computation. The function computes league distribution of xRV100 values. With multi-year data, the distribution will be larger and more representative. The `group_by("pitcher")` already aggregates across game_types, so adding cross-year data is seamless.

### Season Baseline Multi-Row Impact

STATE.md notes: "PitcherData.season_baseline now returns multiple rows per season -- Phase 18 consumers that assume single-row need updating."

After investigation, the scout.py code at line 156 does:
```python
pitcher_baseline = season_baseline.filter(pl.col("pitcher") == pitcher_id)
if pitcher_baseline.is_empty():
    continue
```
And later at line 175: `pitcher_baseline.row(0, named=True)`.

Since `compute_season_baseline()` now produces one row per pitcher per **season**, `pitcher_baseline` could have 2 rows (2025 and 2026). `row(0, named=True)` picks the first arbitrarily. The fix is to either:
- Filter to the most recent season, or
- Use the matching season for the appearance being scored

For scout.py, the appearances being scored are in a recent date window. The correct approach is to filter `season_baseline` to the season matching the appearance's game_date year. However, this adds complexity. The simpler approach -- filter to the latest season -- is acceptable because scout.py scores recent appearances which are always in the current season.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-year file iteration | Manual year loops in each consumer | `load_all_statcast()`, `load_full_agg()` in data.py | Centralizes year-aware path generation, game_type filtering, and graceful skip logic |
| Game type filtering | Per-module filter calls | `filter_game_type()` applied inside data.py loaders | Prevents filtering being accidentally omitted |
| CSV date parsing | Per-call `.str.to_date()` | Handled inside `load_csv()` / `load_full_agg()` | Consistent date parsing everywhere |

## Common Pitfalls

### Pitfall 1: Scout.py Season Baseline Multi-Row
**What goes wrong:** `pitcher_baseline.row(0, named=True)` silently picks wrong season when multi-year data produces 2 rows per pitcher.
**Why it happens:** `compute_season_baseline()` now groups by `[pitcher, season]` instead of just `[pitcher]`.
**How to avoid:** Filter season_baseline to the relevant season before taking `.row(0)`. For scout.py, filter to max season (current season).
**Warning signs:** P+ delta signals would fire incorrectly if comparing 2026 appearance against 2025 baseline.

### Pitfall 2: Scout.py Pitch Type Baseline Multi-Row
**What goes wrong:** `compute_pitch_type_baseline()` also produces per-season rows. `pitcher_type_bl.filter(pl.col("pitch_type") == pt)` could return 2 rows.
**Why it happens:** Same season grouping change.
**How to avoid:** Filter pitch_type_baseline to the relevant season as well.
**Warning signs:** Usage shift signals fire on stale baselines.

### Pitfall 3: Engine.py League Baselines Cache Stale Across Tests
**What goes wrong:** `_league_baselines_cache` is module-level. If tests monkeypatch DATA_DIR, the cache may hold stale data.
**Why it happens:** Cache is populated on first call, never invalidated.
**How to avoid:** This is pre-existing. No changes needed for this phase, but be aware during testing.
**Warning signs:** Test failures that disappear when running tests in isolation.

### Pitfall 4: Forgetting to Update __all__ in data.py
**What goes wrong:** New functions not exported, IDE autocompletion and `from data import *` miss them.
**Why it happens:** data.py uses explicit `__all__`.
**How to avoid:** Add `load_all_statcast` and `load_full_agg` to `__all__`.
**Warning signs:** Import errors in consumer modules.

### Pitfall 5: Test Fixture Values Changed by Game-Type Filtering
**What goes wrong:** 7 test_engine.py tests fail because Booser #592155's data changed after Phase 16 filtered out non-regular-season games.
**Why it happens:** Test assertions were written against pre-filtering data. The primary fastball shifted from FC to FF when spring training data was excluded.
**How to avoid:** Update test assertions to match the filtered data. Run tests against real data to discover actual values.
**Warning signs:** `assert result == "FC"` fails with actual `"FF"`.

### Pitfall 6: resolver.py Module-Level Cache with Multi-Year Data
**What goes wrong:** Resolver's `_name_table` is built once and cached at module level. If the cache was populated before the refactoring (from a prior import in the same process), it holds single-year data.
**Why it happens:** Module-level `_name_table = None` pattern.
**How to avoid:** This is only a concern during development/testing. In production, the module is imported fresh. For tests, the cache should be fine since it builds on first call within the test session.
**Warning signs:** Pitchers from 2025-only not found in resolver.

## Code Examples

### New data.py Functions

```python
# Source: Follows existing load_statcast() pattern in data.py

def load_all_statcast(columns: list[str] | None = None) -> pl.DataFrame:
    """Load Statcast pitch-level data for all pitchers across all years.

    Reads parquet files for all configured years in ``_YEARS``, filters
    each to allowed game types, and concatenates results. Missing year
    files are skipped gracefully.

    Args:
        columns: If provided, only load these columns from parquet files.
            Reduces memory usage for targeted queries.

    Returns:
        Polars DataFrame with all pitchers' regular-season data across
        all available years.
    """
    frames: list[pl.DataFrame] = []
    for year in _YEARS:
        path = DATA_DIR / f"statcast_{year}.parquet"
        if not path.exists():
            continue
        df = pl.read_parquet(path, columns=columns)
        df = filter_game_type(df)
        if not df.is_empty():
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames)


def load_full_agg(grain: str) -> pl.DataFrame:
    """Load a Pitching+ CSV aggregation across all years without pitcher filtering.

    Reads year-prefixed CSV files for a single grain and concatenates.
    Applies game_type filtering and date parsing. Missing year files are
    skipped gracefully.

    Args:
        grain: Grain name (e.g., 'pitcher_type', 'pitcher_appearance').

    Returns:
        Polars DataFrame with all pitchers' data for this grain across
        all available years.
    """
    frames: list[pl.DataFrame] = []
    for year in _YEARS:
        filename = f"{year}-{grain}.csv"
        path = AGGS_DIR / filename
        if not path.exists():
            continue
        frames.append(load_csv(filename, None))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames)
```

### Engine.py Refactoring -- compute_league_baselines()

```python
# Before (bypass):
df = pl.read_parquet(
    PARQUET_PATH,
    columns=["pitch_type", "pitch_name", "release_speed", "pfx_x", "pfx_z", "zone", "description"],
)

# After:
df = load_all_statcast(
    columns=["pitch_type", "pitch_name", "release_speed", "pfx_x", "pfx_z", "zone", "description"],
)
```

```python
# Before (bypass):
pitcher_type_path = AGGS_DIR / "2026-pitcher_type.csv"
if pitcher_type_path.exists():
    pt_df = pl.read_csv(pitcher_type_path)

# After:
pt_df = load_full_agg("pitcher_type")
if not pt_df.is_empty():
```

### Engine.py Refactoring -- compute_execution_metrics()

```python
# Before (bypass):
full_pitcher_type_df = pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")
if "game_date" in full_pitcher_type_df.columns:
    full_pitcher_type_df = full_pitcher_type_df.with_columns(
        pl.col("game_date").str.to_date("%Y-%m-%d")
    )

# After (date parsing handled by load_csv inside load_full_agg):
full_pitcher_type_df = load_full_agg("pitcher_type")
```

### Scout.py Refactoring -- scout_appearances()

```python
# Before (wrong arity, hardcoded year):
app_df = load_csv("2026-pitcher_appearance.csv")
app_type_df = load_csv("2026-pitcher_type_appearance.csv")
season_type_df = load_csv("2026-pitcher_type.csv")
season_df = load_csv("2026-pitcher.csv")

# After:
app_df = load_full_agg("pitcher_appearance")
app_type_df = load_full_agg("pitcher_type_appearance")
season_type_df = load_full_agg("pitcher_type")
season_df = load_full_agg("pitcher")
```

### Scout.py Refactoring -- _compute_velo_baselines()

```python
# Before (bypass):
if not PARQUET_PATH.exists():
    return pl.DataFrame(schema={"pitcher": pl.Int64, "season_velo": pl.Float64})
df = pl.read_parquet(
    PARQUET_PATH,
    columns=["pitcher", "game_pk", "game_date", "pitch_type", "release_speed"],
)

# After:
df = load_all_statcast(
    columns=["pitcher", "game_pk", "game_date", "pitch_type", "release_speed"],
)
if df.is_empty():
    return pl.DataFrame(schema={"pitcher": pl.Int64, "season_velo": pl.Float64})
```

### Resolver.py Refactoring -- _build_name_table()

```python
# Before (bypass, single-year):
df = pl.read_parquet(PARQUET_PATH, columns=["pitcher", "player_name"])

# After (multi-year):
df = load_all_statcast(columns=["pitcher", "player_name"])
```

### Scout.py Season Baseline Fix

```python
# Before (assumes single row):
pitcher_baseline = season_baseline.filter(pl.col("pitcher") == pitcher_id)
if pitcher_baseline.is_empty():
    continue

# After (filter to most recent season):
pitcher_baseline = season_baseline.filter(pl.col("pitcher") == pitcher_id)
if pitcher_baseline.is_empty():
    continue
pitcher_baseline = pitcher_baseline.sort("season", descending=True).head(1)
```

Same pattern for `pitcher_type_bl`:
```python
# Before:
pitcher_type_bl = season_type_baseline.filter(pl.col("pitcher") == pitcher_id)

# After (filter to most recent season):
pitcher_type_bl = season_type_baseline.filter(pl.col("pitcher") == pitcher_id)
max_season = pitcher_type_bl["season"].max()
if max_season is not None:
    pitcher_type_bl = pitcher_type_bl.filter(pl.col("season") == max_season)
```

## Test Fixture Updates Required

7 test_engine.py tests fail due to Phase 16 game-type filtering changing the test pitcher's data:

| Test | Assertion | Current | Expected After Fix |
|------|-----------|---------|-------------------|
| `test_identify_primary_fastball` | `assert result == "FC"` | `"FF"` | Update to `"FF"` |
| `test_fastball_velocity_delta` | velocity range check | Different values | Re-verify with filtered data |
| `test_fastball_pitch_type` | `primary_type == "FC"` | `"FF"` | Update to `"FF"` |
| `test_arsenal_ordering` | First pitch type check | Different ordering | Re-verify ordering |
| `test_first_pitch_count` | `== 42` | `3` | Update to `3` (fewer non-spring appearances) |
| `test_hard_hit_rate_delta_string` | Delta string check | Different value | Re-verify |
| `test_release_point_ordering` | First pitch type | `"FC"` | Update to `"FF"` |

**Strategy:** Run each failing test, observe actual values, update assertions to match. The values changed because spring training data was correctly excluded in Phase 16.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py tests/test_engine.py tests/test_resolver.py -x --tb=short -q` |
| Full suite command | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py tests/test_engine.py tests/test_resolver.py --tb=short -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CSMR-01 | engine.py has no direct read_csv/read_parquet | smoke | `grep "read_csv\|read_parquet" src/pitcher_narratives/engine.py` returns empty | N/A (grep check) |
| CSMR-01 | engine.py league baselines still computed correctly | integration | `uv run pytest tests/test_engine.py -x --tb=short -q` | Yes |
| CSMR-02 | resolver.py builds name table from all years | unit | `uv run pytest tests/test_resolver.py -x --tb=short -q` | Yes |
| CSMR-03 | scout.py has no direct CSV/parquet reads | smoke | `grep "read_csv\|read_parquet" src/pitcher_narratives/scout.py` returns empty | N/A (grep check) |
| CSMR-03 | scout.py still functions correctly | manual | `uv run python -c "from pitcher_narratives.scout import scout_appearances; r = scout_appearances(); print(len(r))"` | No test file |
| ALL | No bypass reads in src/pitcher_narratives/ | smoke | `grep "read_csv\|read_parquet" src/pitcher_narratives/ -r \| grep -v data.py` returns empty | N/A (grep check) |
| ALL | New data.py functions work correctly | unit | `uv run pytest tests/test_data.py -x --tb=short -q` | Needs new tests |

### Sampling Rate
- **Per task commit:** `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py tests/test_engine.py tests/test_resolver.py -x --tb=short -q`
- **Per wave merge:** Full suite
- **Phase gate:** All tests green, grep verification zero results

### Wave 0 Gaps
- [ ] `tests/test_data.py` -- add tests for new `load_all_statcast()` and `load_full_agg()` functions
- [ ] `tests/test_engine.py` -- update 7 broken test assertions for post-filtering data values
- [ ] No test_scout.py exists -- a basic smoke test would be valuable but is not strictly required (manual verification suffices)

## Sources

### Primary (HIGH confidence)
- Direct source code inspection of data.py, engine.py, scout.py, resolver.py in the working tree
- grep verification of all bypass points across `src/pitcher_narratives/`
- Existing test suite execution (110 passed, 14 failed -- 7 RV_df.csv pre-existing, 7 game-type fixture drift)

### Secondary (MEDIUM confidence)
- STATE.md notes about `PitcherData.season_baseline` multi-row impact on Phase 18 consumers
- CONTEXT.md known bypass points from Phase 16 research

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries, pure refactoring of existing codebase
- Architecture: HIGH - New functions follow exact pattern of existing data.py functions
- Pitfalls: HIGH - All bypass points verified by grep, all failures reproduced by test execution

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable internal refactoring, no external dependency drift)
