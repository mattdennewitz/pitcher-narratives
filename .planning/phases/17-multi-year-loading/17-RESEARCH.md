# Phase 17: Multi-Year Loading - Research

**Researched:** 2026-04-02
**Domain:** Polars multi-file loading, DataFrame concatenation, per-season grouping
**Confidence:** HIGH

## Summary

Phase 17 modifies `data.py` to load and concatenate parquet and CSV files across all years in `_YEARS`, with graceful handling of missing files and per-season baseline computation. The changes are contained entirely within `data.py` -- consumer modules (`engine.py`, `resolver.py`, `scout.py`) are Phase 18 scope (CSMR-01 through CSMR-03).

The existing code is well-structured for this change. `_YEARS: list[int] = [2026]` already exists, `_SEASON_GRAINS` and `_APPEARANCE_GRAINS` already drive CSV filename generation via f-strings, and `_ID_COLS` already includes `"season"`. The primary work is: (1) looping `load_statcast()` over `_YEARS` and concatenating parquet DataFrames, (2) looping `load_agg_csvs()` over `_YEARS` and concatenating CSV DataFrames per grain, (3) adding file-existence checks that skip missing years, and (4) changing `compute_season_baseline()` and `compute_pitch_type_baseline()` to group by `["pitcher", "season"]` instead of just `"pitcher"`.

**Primary recommendation:** Use `Path.exists()` guards in both loaders, `pl.concat()` for vertical concatenation, and add `"season"` to the `group_by` keys in both baseline functions.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices are at Claude's discretion per CONTEXT.md.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key decisions already locked in STATE.md:
- Explicit `_YEARS` constant (already `[2026]` from Phase 16) expanded to `[2025, 2026]`
- Per-season baselines (not cross-season averaged) to prevent double-counting artifacts -- `compute_season_baseline()` must group by `["pitcher", "season"]`
- When a year's files are missing, skip that year gracefully without crashing
- `PARQUET_PATH` stays singular for backward compatibility; `load_statcast()` internally iterates `_YEARS`

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MYLD-01 | load_statcast() reads and concatenates parquet files for all configured years | Polars `read_parquet` accepts list of paths natively; alternatively iterate `_YEARS`, check `Path.exists()`, read each, `pl.concat()`. Parquet has `game_year` column for season identification. |
| MYLD-02 | load_agg_csvs() reads and concatenates CSV files for all configured years per grain | CSVs already have `season` column. Loop `_YEARS` x grains, derive filename as `f"{year}-{grain}.csv"`, skip missing, concat per grain. |
| MYLD-03 | Pipeline gracefully handles missing year files (skips without crashing) | `Path.exists()` before read. `pl.concat([])` raises `ValueError` -- must guard against empty list (return empty DataFrame with matching schema). |
| MYLD-04 | Season baselines computed per-season using the season column | Change `group_by("pitcher")` to `group_by(["pitcher", "season"])` in both `compute_season_baseline()` and `compute_pitch_type_baseline()`. CSVs already have `season` column; parquet has `game_year`. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame operations, parquet/CSV reading, concat | Already in use; `read_parquet` accepts list of paths, `pl.concat` for vertical concatenation |
| pathlib | stdlib | File existence checks | `Path.exists()` for graceful missing-file handling |

No new dependencies required. Everything needed is already available.

## Architecture Patterns

### Current Module Structure (unchanged)
```
src/pitcher_narratives/
    data.py          # <-- ALL Phase 17 changes here
    engine.py        # Consumer -- Phase 18 scope (CSMR-01)
    resolver.py      # Consumer -- Phase 18 scope (CSMR-02)
    scout.py         # Consumer -- Phase 18 scope (CSMR-03)
tests/
    test_data.py     # <-- Phase 17 test additions here
```

### Pattern 1: Multi-Year Parquet Loading
**What:** `load_statcast()` iterates `_YEARS`, constructs path per year, checks existence, reads each, concatenates.
**When to use:** Whenever loading statcast data.
**Current code (line 141):**
```python
df = pl.read_parquet(PARQUET_PATH)
```
**Target pattern:**
```python
def load_statcast(pitcher_id: int) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for year in _YEARS:
        path = DATA_DIR / f"statcast_{year}.parquet"
        if not path.exists():
            continue
        df = pl.read_parquet(path)
        df = filter_game_type(df)
        frames.append(df.filter(pl.col("pitcher") == pitcher_id))
    if not frames:
        raise ValueError(f"Pitcher {pitcher_id} not found")
    result = pl.concat(frames)
    if result.is_empty():
        raise ValueError(f"Pitcher {pitcher_id} not found")
    return result
```

**Key detail:** Filter per-year BEFORE concat to minimize memory. Apply `filter_game_type` per-year too, consistent with current behavior.

**PARQUET_PATH backward compatibility:** The module-level `PARQUET_PATH` constant stays as `DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"` because `engine.py`, `resolver.py`, and `scout.py` import it directly. Those imports are Phase 18 scope.

### Pattern 2: Multi-Year CSV Loading
**What:** `load_agg_csvs()` iterates `_YEARS` x grains, constructs filenames, skips missing, concatenates per grain.
**Current code (line 173):**
```python
filename = f"{_YEARS[-1]}-{grain}.csv"
```
**Target pattern:**
```python
def load_agg_csvs(pitcher_id: int) -> dict[str, pl.DataFrame]:
    all_grains = [*_SEASON_GRAINS, *_APPEARANCE_GRAINS]
    result: dict[str, pl.DataFrame] = {}
    for grain in all_grains:
        frames: list[pl.DataFrame] = []
        for year in _YEARS:
            filename = f"{year}-{grain}.csv"
            path = AGGS_DIR / filename
            if not path.exists():
                continue
            pid = None if grain == "team" else pitcher_id
            frames.append(load_csv(filename, pid))
        if frames:
            result[grain] = pl.concat(frames)
        else:
            result[grain] = pl.DataFrame()  # empty -- needs schema handling
    return result
```

**Schema concern:** If all years are missing for a grain, `pl.DataFrame()` has no columns. This is acceptable because downstream code (e.g., `compute_season_baseline`) will get an empty DF and the pipeline will fail gracefully on the pitcher-not-found path. However, tests should verify this path.

### Pattern 3: Per-Season Baseline Grouping
**What:** Change `group_by("pitcher")` to `group_by(["pitcher", "season"])` so a pitcher with data in multiple seasons gets separate baseline rows.
**Current code (line 226):**
```python
return pitcher_df.group_by("pitcher").agg(...)
```
**Target pattern:**
```python
return pitcher_df.group_by(["pitcher", "season"]).agg(...)
```

**Same change needed in `compute_pitch_type_baseline` (line 255):**
```python
# Current:
result = df.group_by(["pitcher", "pitch_type"]).agg(...)
pitcher_totals = df.group_by("pitcher").agg(...)
# Target:
result = df.group_by(["pitcher", "season", "pitch_type"]).agg(...)
pitcher_totals = df.group_by(["pitcher", "season"]).agg(...)
```

**Impact on `load_pitcher_data`:** Currently `compute_season_baseline` returns 1 row per pitcher. After this change, it returns 1 row per pitcher per season. `load_pitcher_data` calls `compute_season_baseline(agg_csvs["pitcher"])` and stores the result in `PitcherData.season_baseline`. The return type stays `pl.DataFrame` -- callers just get more rows. Phase 18 consumers that assume a single-row baseline will need updating (that's Phase 18 scope).

### Anti-Patterns to Avoid
- **Glob-based auto-discovery:** Requirement explicitly out of scope. Do NOT use `DATA_DIR.glob("statcast_*.parquet")` -- iterate `_YEARS` explicitly.
- **Reading all data then filtering:** Filter to pitcher and game type per-year-file before concatenating to keep memory bounded.
- **Using `pl.concat([])` without guard:** Raises `ValueError`. Always check `if frames:` before concat.
- **Breaking PARQUET_PATH backward compatibility:** Keep module-level `PARQUET_PATH` pointing to `_YEARS[-1]` -- consumer modules import it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-parquet reading | Custom file scanner / glob | `Path.exists()` per year from `_YEARS` list + `pl.concat()` | Explicit `_YEARS` is a design decision; auto-discovery is out of scope |
| Schema alignment on concat | Manual column matching | `pl.concat(how="vertical_relaxed")` if schemas differ between years | Polars handles column alignment; `vertical_relaxed` fills missing cols with null |
| Weighted averages | Manual numpy/math | Polars expressions: `(pl.col(c) * pl.col("n_pitches")).sum() / pl.col("n_pitches").sum()` | Already established pattern in codebase |

## Common Pitfalls

### Pitfall 1: `pl.concat([])` Crashes
**What goes wrong:** If all years are missing for a grain or no parquet files exist, `pl.concat([])` raises `ValueError: cannot concat empty list`.
**Why it happens:** Graceful skip logic collects zero frames.
**How to avoid:** Always guard: `pl.concat(frames) if frames else pl.DataFrame()`. For `load_statcast`, raise `ValueError("Pitcher ... not found")` instead.
**Warning signs:** Tests with mocked missing files pass but real empty-concat path untested.

### Pitfall 2: Cross-Season Averaging in Baselines
**What goes wrong:** A pitcher who threw 95 mph in 2025 and 97 mph in 2026 gets a baseline of 96 mph instead of separate 95 and 97 baselines per season.
**Why it happens:** `group_by("pitcher")` combines all seasons.
**How to avoid:** `group_by(["pitcher", "season"])` in both baseline functions.
**Warning signs:** Test with synthetic multi-season data that asserts separate rows per season.

### Pitfall 3: Parquet Has `game_year` Not `season`
**What goes wrong:** Parquet files use `game_year` column while CSVs use `season` column. Code that assumes uniform column names across data sources will fail.
**Why it happens:** Statcast data uses `game_year`; Pitching+ aggs use `season`.
**How to avoid:** This is not an issue for Phase 17 because `load_statcast()` does not compute baselines -- it returns raw pitch data. Baselines are computed from CSV data which has `season`. However, if anyone adds season-based grouping to statcast queries, they must use `game_year`.
**Warning signs:** Column not found errors when using `"season"` on statcast DataFrames.

### Pitfall 4: `load_pitcher_data` Return Shape Change
**What goes wrong:** `season_baseline` changes from 1 row (per pitcher) to N rows (per pitcher-season). Code downstream that does `baseline[0]` or assumes `.height == 1` breaks.
**Why it happens:** `group_by(["pitcher", "season"])` produces more rows.
**How to avoid:** Phase 17 changes the function; Phase 18 updates consumers. Within Phase 17, update `load_pitcher_data` to be aware of multi-row baselines but don't change its return type.
**Warning signs:** Existing tests that assert `len(baseline) == 1` will need updating.

### Pitfall 5: Empty DataFrame Schema Mismatch
**What goes wrong:** When all years are missing, returning `pl.DataFrame()` creates a zero-column DataFrame. Downstream code that accesses specific columns gets `ColumnNotFoundError`.
**Why it happens:** `pl.DataFrame()` has no schema by default.
**How to avoid:** For the graceful-skip case in `load_agg_csvs`, an empty grain means the pitcher has no data at all -- the pipeline will fail elsewhere (pitcher not found). This is acceptable. Alternatively, read one file to get schema then filter to empty.
**Warning signs:** Tests that mock all-missing-years and then access columns.

## Code Examples

### Verified: Current `_YEARS` and Path Derivation
```python
# Source: data.py lines 38-41
_YEARS: list[int] = [2026]
PARQUET_PATH = DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"
AGGS_DIR = DATA_DIR / "aggs"
```

### Verified: Current Grain Iteration
```python
# Source: data.py lines 170-176
all_grains = [*_SEASON_GRAINS, *_APPEARANCE_GRAINS]
result: dict[str, pl.DataFrame] = {}
for grain in all_grains:
    filename = f"{_YEARS[-1]}-{grain}.csv"
    pid = None if grain == "team" else pitcher_id
    result[grain] = load_csv(filename, pid)
```

### Verified: CSV Schema Includes Season
```python
# Confirmed via inspection: aggs/2026-pitcher.csv
# First columns: season, level, game_type, pitcher, player_name, p_throws, team_code, n_pitches, ...
# season values: [2026] (single year currently)
```

### Verified: Parquet Schema Has `game_year` (Not `season`)
```python
# Confirmed via inspection: statcast_2026.parquet
# Has game_year column with values [2026]
# Does NOT have season column
# Has 114 columns, 176380 rows
```

### Verified: Polars Concat and Read Patterns
```python
# polars 1.39.3 confirmed:
# pl.read_parquet accepts list of paths: pl.read_parquet([path1, path2])
# pl.concat([df1, df2]) for vertical concatenation
# pl.concat([]) raises ValueError -- must guard
```

### Verified: Data File Inventory
```
# Existing files (original repo):
statcast_2026.parquet  (23.5M, 176380 rows, 114 cols)
aggs/2026-all_pitches.csv          (28.2M)
aggs/2026-pitcher_appearance.csv   (183.7K)
aggs/2026-pitcher_type_appearance.csv  (718.2K)
aggs/2026-pitcher_type_platoon_appearance.csv  (1.2M)
aggs/2026-pitcher_type_platoon.csv (740.5K)
aggs/2026-pitcher_type.csv         (415.5K)
aggs/2026-pitcher.csv              (94.5K)
aggs/2026-team.csv                 (9.2K)

# Missing (expected for MYLD-03 graceful skip):
statcast_2025.parquet  -- DOES NOT EXIST
aggs/2025-*.csv        -- DO NOT EXIST
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded `statcast_2026.parquet` | `_YEARS[-1]`-derived path | Phase 16 | Already parameterized |
| Hardcoded CSV filename dicts | `_SEASON_GRAINS` + `_APPEARANCE_GRAINS` tuples | Phase 16 | f-string generation ready |
| `season` not in `_ID_COLS` | `season` in `_ID_COLS` | Phase 16 | Won't be weighted-averaged |

## Open Questions

1. **Multi-row baseline impact on `load_pitcher_data` callers**
   - What we know: `season_baseline` will have 1 row per season instead of 1 row total. `PitcherData.season_baseline` return type is `pl.DataFrame` (unchanged).
   - What's unclear: Whether `context.py`, `engine.py`, or other Phase 18 consumers index into `season_baseline` assuming single row.
   - Recommendation: Phase 17 makes the change; Phase 18 fixes consumers. Within Phase 17, verify the existing `test_season_baseline_weighted` test is updated to handle multi-row output.

2. **Empty DataFrame when all years missing**
   - What we know: `pl.DataFrame()` has no schema. Downstream column access would fail.
   - What's unclear: Whether this edge case matters in practice (if no data exists for any year, the pipeline has bigger problems).
   - Recommendation: Accept empty DataFrame for missing years; document that this is a "no data available" state, not a bug. The `load_statcast` path already raises `ValueError` for missing pitchers.

3. **`usage_pct` computation in `compute_pitch_type_baseline` with multi-season**
   - What we know: Currently `pitcher_totals` groups by `"pitcher"` to get total pitches for usage_pct. With multi-season, it should group by `["pitcher", "season"]` so usage_pct is per-season.
   - What's unclear: Nothing -- this is clearly correct.
   - Recommendation: Update both the main groupby and the `pitcher_totals` groupby to include `"season"`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -m pytest tests/test_data.py -x` |
| Full suite command | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -m pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MYLD-01 | load_statcast reads/concatenates all years | unit (synthetic) | `pytest tests/test_data.py::test_load_statcast_multi_year -x` | Wave 0 |
| MYLD-01 | load_statcast with real 2026 data (regression) | integration | `pytest tests/test_data.py::test_load_statcast_filters_by_pitcher -x` | Exists (passes) |
| MYLD-02 | load_agg_csvs reads/concatenates all years | unit (synthetic) | `pytest tests/test_data.py::test_load_agg_csvs_multi_year -x` | Wave 0 |
| MYLD-02 | load_agg_csvs with real 2026 data (regression) | integration | `pytest tests/test_data.py::test_load_agg_csvs_all_grains -x` | Exists (passes) |
| MYLD-03 | Missing year files skipped without crash | unit (monkeypatch) | `pytest tests/test_data.py::test_load_statcast_missing_year_skipped -x` | Wave 0 |
| MYLD-03 | Missing year CSV files skipped | unit (monkeypatch) | `pytest tests/test_data.py::test_load_agg_csvs_missing_year_skipped -x` | Wave 0 |
| MYLD-04 | Season baseline per-season grouping | unit (synthetic) | `pytest tests/test_data.py::test_season_baseline_per_season -x` | Wave 0 |
| MYLD-04 | Pitch type baseline per-season grouping | unit (synthetic) | `pytest tests/test_data.py::test_pitch_type_baseline_per_season -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -m pytest tests/test_data.py -x`
- **Per wave merge:** `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_data.py::test_load_statcast_multi_year` -- covers MYLD-01 with synthetic multi-year parquet data via tmp_path
- [ ] `tests/test_data.py::test_load_agg_csvs_multi_year` -- covers MYLD-02 with synthetic multi-year CSV data via tmp_path
- [ ] `tests/test_data.py::test_load_statcast_missing_year_skipped` -- covers MYLD-03 for parquet
- [ ] `tests/test_data.py::test_load_agg_csvs_missing_year_skipped` -- covers MYLD-03 for CSV
- [ ] `tests/test_data.py::test_season_baseline_per_season` -- covers MYLD-04 (synthetic 2-season data, asserts separate rows)
- [ ] `tests/test_data.py::test_pitch_type_baseline_per_season` -- covers MYLD-04 for pitch type baselines
- [ ] Update `test_season_baseline_weighted` -- currently asserts `len(baseline) == 1`, needs to account for per-season grouping
- [ ] Update `test_years_constant_drives_paths` -- verify `_YEARS` now contains `[2025, 2026]`

### Test Strategy Notes
- **Synthetic data preferred for multi-year tests** because 2025 data files do not exist on disk. Use `tmp_path` + `monkeypatch` to override `DATA_DIR` and create minimal test parquet/CSV files.
- **Existing tests must not break** -- they use real 2026 data via `PITCHER_NARRATIVES_DATA_DIR`. The `_YEARS` expansion to `[2025, 2026]` with missing 2025 files exercises MYLD-03 naturally.
- **Important env var:** All tests require `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` because data files live in the original repo, not the worktree.

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/data.py` -- current implementation (Phase 16 state), all functions examined
- `tests/test_data.py` -- 22 passing tests, current coverage
- `aggs/2026-pitcher.csv` -- schema verified: `season` column present, values `[2026]`
- `statcast_2026.parquet` -- schema verified: `game_year` column present (not `season`), 114 columns, 176380 rows
- polars 1.39.3 -- `read_parquet(list_of_paths)` confirmed working, `pl.concat([])` raises ValueError confirmed

### Secondary (MEDIUM confidence)
- `src/pitcher_narratives/scout.py` lines 114-117 -- hardcoded `"2026-..."` filenames (Phase 18 scope)
- `src/pitcher_narratives/engine.py` line 200-201, 1791 -- direct `PARQUET_PATH` and CSV reads (Phase 18 scope)
- `src/pitcher_narratives/resolver.py` line 111 -- `PARQUET_PATH` import (Phase 18 scope)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- polars already in use, no new dependencies
- Architecture: HIGH -- patterns derived from reading actual code, verified with Python REPL
- Pitfalls: HIGH -- concat edge cases and schema differences verified empirically

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable domain -- no external API changes expected)
