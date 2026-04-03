# Architecture Patterns

**Domain:** Multi-year data loading and game type filtering for pitcher narratives CLI
**Researched:** 2026-04-02

## Recommended Architecture

### Design Principle: Filter Early, Concatenate at the Loader

Game type filtering and multi-year concatenation belong in `data.py` at load time -- before `PitcherData` is constructed. Every downstream consumer (`engine.py`, `context.py`, `scout.py`, `resolver.py`) already operates on `PitcherData` fields or raw DataFrames from `data.py` exports. If filtered data enters `PitcherData`, nothing downstream needs to change.

This is the single most important architectural decision: **filtering happens inside the loaders, not after construction.**

### Data Flow (Current vs Proposed)

```
CURRENT:
  statcast_2026.parquet ──> load_statcast() ──> PitcherData.statcast
  2026-pitcher.csv ────────> load_agg_csvs() ─> PitcherData.agg_csvs
  (single year, all game types including S/E)

PROPOSED:
  statcast_2025.parquet ─┐
  statcast_2026.parquet ─┴─> load_statcast() ──> filter game_type ──> PitcherData.statcast
  2025-pitcher.csv ──────┐
  2026-pitcher.csv ──────┴─> load_agg_csvs() ──> filter game_type ──> PitcherData.agg_csvs
  (multi-year, regular season only)
```

## Component Boundaries

### What Changes

| Component | Change Type | Scope |
|-----------|-------------|-------|
| `data.py` | **Modified (primary)** | Multi-year paths, concat, game_type filter |
| `scout.py` | **Modified (secondary)** | Has its own hardcoded CSV filenames + PARQUET_PATH import |
| `engine.py` | **Modified (one line)** | Line 1563: hardcoded `2026-pitcher_type.csv` |
| `resolver.py` | **Modified (minimal)** | Uses `PARQUET_PATH` for name table; needs multi-parquet |
| `context.py` | **No change** | Consumes `PitcherData`, agnostic to data source |
| `analyst.py` | **No change** | Consumes `PitcherContext`, no direct data loading |
| `report.py` | **No change** | Consumes context/capsules, no data loading |
| `cli.py` | **No change** | Calls `load_pitcher_data()`, interface unchanged |
| `curator.py` | **No change** | Consumes `ScoredAppearance` list |
| `ask_cli.py` | **No change** | Calls `load_pitcher_data()` via analyst |
| `scout_cli.py` | **No change** | Calls `scout_appearances()`, interface unchanged |

### Component Detail

#### data.py (Primary Target)

**Current hardcoded state:**
- `PARQUET_PATH = DATA_DIR / "statcast_2026.parquet"` -- single file
- `_SEASON_CSVS` -- 4 entries, all `"2026-"` prefixed
- `_APPEARANCE_CSVS` -- 4 entries, all `"2026-"` prefixed
- `_ID_COLS` includes `"game_type"` already (used to exclude from metric averaging)

**Changes needed:**

1. **Add centralized constants** for years and excluded game types:
   ```python
   _YEARS = [2025, 2026]
   _EXCLUDED_GAME_TYPES = frozenset({"S", "E"})
   ```

2. **Replace `PARQUET_PATH` with `PARQUET_PATHS`** -- a list of paths:
   ```python
   PARQUET_PATHS: list[Path] = [DATA_DIR / f"statcast_{y}.parquet" for y in _YEARS]
   ```

3. **Replace `_SEASON_CSVS` / `_APPEARANCE_CSVS` with year-aware generation**:
   ```python
   _SEASON_GRAINS = ["pitcher", "pitcher_type", "pitcher_type_platoon", "team"]
   _APPEARANCE_GRAINS = ["pitcher_appearance", "pitcher_type_appearance",
                          "pitcher_type_platoon_appearance", "all_pitches"]
   ```

4. **Add a shared game_type filter helper**:
   ```python
   def _filter_game_type(df: pl.DataFrame) -> pl.DataFrame:
       if "game_type" in df.columns:
           return df.filter(~pl.col("game_type").is_in(list(_EXCLUDED_GAME_TYPES)))
       return df
   ```

5. **Update `load_statcast()`** to concat multiple parquets and filter:
   ```python
   def load_statcast(pitcher_id: int) -> pl.DataFrame:
       frames = [pl.read_parquet(p) for p in PARQUET_PATHS if p.exists()]
       if not frames:
           raise FileNotFoundError("No statcast parquet files found")
       df = pl.concat(frames)
       df = _filter_game_type(df)
       result = df.filter(pl.col("pitcher") == pitcher_id)
       if result.is_empty():
           raise ValueError(f"Pitcher {pitcher_id} not found")
       return result
   ```

6. **Update `_load_csv_with_dates()`** to accept a list of filenames:
   ```python
   def _load_csv_with_dates(filenames: list[str], pitcher_id: int | None) -> pl.DataFrame:
       frames = [pl.read_csv(AGGS_DIR / f) for f in filenames if (AGGS_DIR / f).exists()]
       if not frames:
           raise FileNotFoundError(f"No CSV files found for {filenames}")
       df = pl.concat(frames)
       df = _filter_game_type(df)
       if "game_date" in df.columns:
           df = df.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))
       if pitcher_id is not None and "pitcher" in df.columns:
           df = df.filter(pl.col("pitcher") == pitcher_id)
       return df
   ```

7. **Update `load_agg_csvs()`** to generate multi-year filename lists:
   ```python
   def load_agg_csvs(pitcher_id: int) -> dict[str, pl.DataFrame]:
       result: dict[str, pl.DataFrame] = {}
       for grain in _SEASON_GRAINS + _APPEARANCE_GRAINS:
           filenames = [f"{y}-{grain}.csv" for y in _YEARS]
           pid = None if grain == "team" else pitcher_id
           result[grain] = _load_csv_with_dates(filenames, pid)
       return result
   ```

8. **Add `load_full_agg()` export** for engine.py and scout.py:
   ```python
   def load_full_agg(grain: str) -> pl.DataFrame:
       """Load full (unfiltered-by-pitcher) multi-year agg CSV, game_type filtered."""
       filenames = [f"{y}-{grain}.csv" for y in _YEARS]
       return _load_csv_with_dates(filenames, pitcher_id=None)
   ```

9. **`compute_season_baseline()` and `compute_pitch_type_baseline()` need no structural changes.** These already group by `pitcher` (not by season or game_type) and weight by `n_pitches`. After game_type filtering removes S/E rows upstream, the weighted averaging math remains correct. The `_ID_COLS` frozenset already includes `"game_type"` and `"season"`, so multi-year data with `season` column values [2025, 2026] will have metric columns correctly identified and averaged.

10. **`load_pitcher_data()` signature stays the same:** `load_pitcher_data(pitcher_id: int, window_days: int = 30) -> PitcherData`. No new parameters. Multi-year and game_type filtering are internal to the loaders.

#### resolver.py (Minimal Change)

**Current:** Imports `PARQUET_PATH` from `data.py`, reads single parquet for name table.

**Change:** Import `PARQUET_PATHS`, concat:
```python
from pitcher_narratives.data import PARQUET_PATHS

def _build_name_table() -> _NameTable:
    ...
    frames = [pl.read_parquet(p, columns=["pitcher", "player_name"])
              for p in PARQUET_PATHS if p.exists()]
    df = pl.concat(frames)
    unique = df.unique(subset=["pitcher"])
    ...
```

No game_type filter needed here -- name resolution should work for all pitchers regardless of game type. A pitcher who only appeared in spring training should still be resolvable (the downstream data just will not have regular-season rows for them, and `load_statcast` will raise `ValueError`).

#### scout.py (Secondary Target)

**Current state:** Has its own `_load_csv()` helper with 4 hardcoded `"2026-"` filenames (lines 115-118), and imports `PARQUET_PATH` (line 277). Also filters on `level == "MLB"` (lines 121-124) but does not filter game_type.

**Changes needed:**

1. **Replace 4 hardcoded CSV loads** with the new `load_full_agg()` from data.py:
   ```python
   from pitcher_narratives.data import PARQUET_PATHS, load_full_agg
   
   def scout_appearances(...) -> list[ScoredAppearance]:
       app_df = load_full_agg("pitcher_appearance")
       app_type_df = load_full_agg("pitcher_type_appearance")
       season_type_df = load_full_agg("pitcher_type")
       season_df = load_full_agg("pitcher")
   ```
   This eliminates scout.py's `_load_csv()` helper entirely. Game_type filtering comes from `load_full_agg` for free.

2. **Add game_type filter alongside existing `level == "MLB"` filter** (lines 121-124). After switching to `load_full_agg()`, game_type is already filtered, so these lines only need the `level` filter. But verify -- if `load_full_agg` handles game_type, scout only needs `level`.

3. **Replace `PARQUET_PATH` import** with `PARQUET_PATHS` in `_compute_velo_baselines()` (line 277-284):
   ```python
   frames = [pl.read_parquet(p, columns=[...]) for p in PARQUET_PATHS if p.exists()]
   df = pl.concat(frames)
   # game_type filter for statcast too
   df = df.filter(~pl.col("game_type").is_in(["S", "E"]))
   ```
   Note: `_compute_velo_baselines` loads specific columns from parquet and does not go through `load_statcast()`, so it needs its own game_type filter or should use the shared `_filter_game_type` helper. Since scout.py already imports from `data.py`, importing `_EXCLUDED_GAME_TYPES` or using `load_full_agg` patterns works. But the parquet load here is not a CSV -- it is the raw statcast parquet for velocity computation. Best approach: import `_filter_game_type` (or make it public as `filter_game_type`) from data.py and apply it after concat.

#### engine.py (One-Line Fix)

**Line 1563:** `full_pitcher_type_df = pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")`

This loads the full (unfiltered-by-pitcher) pitcher_type CSV for league-wide xRV100 percentile computation in `_compute_xrv100_percentile`.

**Fix:** Import and use `load_full_agg`:
```python
from pitcher_narratives.data import load_full_agg

# In compute_execution_metrics():
full_pitcher_type_df = load_full_agg("pitcher_type")
```

This single change gets multi-year concat + game_type filtering for free.

## Patterns to Follow

### Pattern 1: Filter at the Gate

**What:** Apply game_type exclusion (`~game_type.is_in(["S", "E"])`) inside every load function, not in consumer code.

**When:** Always. Every function that reads from parquet or CSV should strip spring training and exhibition data before returning.

**Why:** Downstream code (engine, context, scout, report) never sees non-regular-season data. No risk of a forgotten filter in one code path producing tainted baselines. The `compute_season_baseline` docstring currently says "Combines game_type rows (S/C/R)" -- after filtering, it only sees R and C (championship/postseason), which is correct.

**Implementation:**
```python
_EXCLUDED_GAME_TYPES = frozenset({"S", "E"})

def _filter_game_type(df: pl.DataFrame) -> pl.DataFrame:
    """Remove spring training and exhibition rows if game_type column exists."""
    if "game_type" in df.columns:
        return df.filter(~pl.col("game_type").is_in(list(_EXCLUDED_GAME_TYPES)))
    return df
```

### Pattern 2: Year-Agnostic Consumers

**What:** No code outside `data.py` should know about year prefixes or file counts.

**When:** Always. If a new year (2027) is added, only `data.py`'s `_YEARS` list should change.

**Why:** Single point of configuration. The rest of the codebase operates on concatenated DataFrames and does not care how many years contributed to them.

### Pattern 3: Graceful Degradation on Missing Files

**What:** If a parquet or CSV file for a given year does not exist, skip it silently and load available years.

**When:** During development and data ingestion when years arrive incrementally.

**Example:**
```python
frames = [pl.read_parquet(p) for p in PARQUET_PATHS if p.exists()]
if not frames:
    raise FileNotFoundError("No statcast parquet files found")
df = pl.concat(frames)
```

**Why:** Fail loud when no data exists (zero frames = error). Degrade gracefully when partial data exists (one year missing = proceed with available data).

### Pattern 4: Centralized Year Configuration

**What:** A single `_YEARS` constant in `data.py` drives all file discovery.

**When:** Always. No magic year detection from filesystem -- explicit is better.

**Why:** Predictable behavior. An accidental `statcast_2024.parquet` in the data dir will not silently load stale data. Adding a new year is a one-line change with clear intent.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Filtering in PitcherData Consumers

**What:** Letting engine.py or context.py filter game_type from DataFrames they receive.

**Why bad:** Duplicated filter logic across 5+ modules. One missed filter means spring training data contaminates baselines or scout scores. The current `compute_season_baseline` averages across game_type rows by design -- if S/E rows are present, they get averaged in, silently biasing metrics toward spring training performance.

**Instead:** Filter once in `data.py` loaders. Consumers get clean data.

### Anti-Pattern 2: Changing PitcherData's Interface

**What:** Adding `game_types: list[str]` or `years: list[int]` fields to `PitcherData`.

**Why bad:** `PitcherData` is a value object -- a bundle of processed data for a single pitcher. It should not carry metadata about how it was filtered. Every consumer would need to check these fields or ignore them. The dataclass has 9 fields today and is passed through engine, context, report, analyst. Adding filter metadata is noise.

**Instead:** `load_pitcher_data()` applies filtering during construction. Downstream code receives clean data and does not second-guess it.

### Anti-Pattern 3: Dynamic Year Discovery from Filesystem

**What:** Scanning `DATA_DIR` for `statcast_*.parquet` and auto-loading all matches.

**Why bad:** Unpredictable. A leftover test file or backup would silently contaminate data. Makes debugging harder when you cannot tell which years loaded.

**Instead:** Explicit `_YEARS = [2025, 2026]`. Add new years consciously.

### Anti-Pattern 4: Separate Code Paths for Each Year

**What:** `if year == 2025: load_2025_data()` style branching.

**Why bad:** O(n) code for O(1) logic. Concat handles multi-year data in a single code path.

**Instead:** List of paths, concat, filter, done.

### Anti-Pattern 5: Making game_type Filtering Configurable

**What:** Adding a `game_types: list[str] = ["R"]` parameter to `load_pitcher_data()`.

**Why bad:** For this project, the policy is clear and permanent: exclude spring training and exhibition. Making it configurable adds API surface with no current use case. If a future feature needs spring training data, it can call `pl.read_parquet()` directly.

**Instead:** Hardcode the exclusion in `_EXCLUDED_GAME_TYPES`. Simple, clear, not configurable.

## Integration Points (Exhaustive Inventory)

Every location in the codebase that references year-specific files or would be affected by multi-year / game_type changes:

| File | Line(s) | Current Code | Change Required |
|------|---------|--------------|-----------------|
| `data.py` | 34 | `PARQUET_PATH = DATA_DIR / "statcast_2026.parquet"` | Replace with `PARQUET_PATHS` list |
| `data.py` | 39-44 | `_SEASON_CSVS` dict, `"2026-"` prefixed | Generate from `_YEARS` x `_SEASON_GRAINS` |
| `data.py` | 45-50 | `_APPEARANCE_CSVS` dict, `"2026-"` prefixed | Generate from `_YEARS` x `_APPEARANCE_GRAINS` |
| `data.py` | 82-99 | `_load_csv_with_dates(filename: str, ...)` | Accept `filenames: list[str]`, concat, filter |
| `data.py` | 102-118 | `load_statcast()` reads single parquet | Read `PARQUET_PATHS`, concat, filter game_type |
| `data.py` | 131-147 | `load_agg_csvs()` iterates single-file dicts | Iterate multi-file grain lists |
| `data.py` | 179-202 | `compute_season_baseline()` | No structural change needed |
| `data.py` | 205-230 | `compute_pitch_type_baseline()` | No structural change needed |
| `engine.py` | 1563 | `pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")` | Use `load_full_agg("pitcher_type")` |
| `scout.py` | 115 | `_load_csv("2026-pitcher_appearance.csv")` | Use `load_full_agg("pitcher_appearance")` |
| `scout.py` | 116 | `_load_csv("2026-pitcher_type_appearance.csv")` | Use `load_full_agg("pitcher_type_appearance")` |
| `scout.py` | 117 | `_load_csv("2026-pitcher_type.csv")` | Use `load_full_agg("pitcher_type")` |
| `scout.py` | 118 | `_load_csv("2026-pitcher.csv")` | Use `load_full_agg("pitcher")` |
| `scout.py` | 121-124 | `level == "MLB"` filter only | Game_type handled by `load_full_agg`; keep `level` filter |
| `scout.py` | 277-284 | `PARQUET_PATH` import + single read | Use `PARQUET_PATHS`, concat, filter game_type |
| `resolver.py` | 18 | `from pitcher_narratives.data import PARQUET_PATH` | Import `PARQUET_PATHS` |
| `resolver.py` | 110 | `pl.read_parquet(PARQUET_PATH, ...)` | Concat from `PARQUET_PATHS` (no game_type filter) |

**Total: 17 locations across 4 files.** context.py, analyst.py, report.py, cli.py, ask_cli.py, curator.py, scout_cli.py need zero changes.

## New Exports from data.py

After changes, `data.py` should export these new items:

| Export | Type | Purpose | Consumers |
|--------|------|---------|-----------|
| `PARQUET_PATHS` | `list[Path]` | Multi-year parquet paths | resolver.py, scout.py |
| `load_full_agg(grain)` | `function` | Load unfiltered multi-year agg CSV with game_type filter | engine.py, scout.py |

Existing exports (`PitcherData`, `load_statcast`, `load_agg_csvs`, `load_pitcher_data`, `load_run_values`, `RV_DF_PATH`, etc.) keep their signatures unchanged. `load_pitcher_data(pitcher_id, window_days)` does not gain new parameters.

Internal additions (not exported):
- `_YEARS: list[int]` -- year list
- `_EXCLUDED_GAME_TYPES: frozenset[str]` -- game types to exclude
- `_SEASON_GRAINS: list[str]` -- season-level CSV grain names
- `_APPEARANCE_GRAINS: list[str]` -- appearance-level CSV grain names  
- `_filter_game_type(df)` -- shared filter helper

## Suggested Build Order

Build order respects dependency flow: `data.py` is the foundation everything imports from.

| Step | What | Why This Order | Risk |
|------|------|----------------|------|
| 1 | `data.py`: Add `_YEARS`, `_EXCLUDED_GAME_TYPES`, `_filter_game_type`, `PARQUET_PATHS`, grain lists | Foundation constants everything else needs | Low -- additive, no existing behavior changes yet |
| 2 | `data.py`: Update `_load_csv_with_dates()` to accept/concat multiple filenames | Internal helper used by `load_agg_csvs` and new `load_full_agg` | Medium -- changes internal API; `load_agg_csvs` must be updated in same step |
| 3 | `data.py`: Update `load_statcast()` for multi-parquet + game_type filter | Feeds `PitcherData.statcast` and `classify_appearances` | Medium -- behavioral change; existing tests should verify |
| 4 | `data.py`: Update `load_agg_csvs()` to use grain-based filename generation | Feeds baselines and all downstream agg data | Medium -- must match step 2's new `_load_csv_with_dates` signature |
| 5 | `data.py`: Add `load_full_agg()` export | Needed by engine.py and scout.py before they can be updated | Low -- new function, no existing code changes |
| 6 | `engine.py`: Replace line 1563 with `load_full_agg("pitcher_type")` | Single line change, depends on step 5 | Low |
| 7 | `resolver.py`: Update to use `PARQUET_PATHS` | Depends on step 1; straightforward concat | Low |
| 8 | `scout.py`: Replace hardcoded CSVs with `load_full_agg` calls + multi-parquet | Depends on step 5; most lines changed of any non-data.py file | Medium -- scout has its own baseline computation that must still work |

Steps 6, 7, 8 are independent of each other and can be done in parallel after step 5.

**Recommended phasing for the GSD roadmap:**
- **Phase 1**: Steps 1-5 (all data.py changes). This is the foundation. Ship it and verify `load_pitcher_data` still works end-to-end.
- **Phase 2**: Steps 6-8 (engine.py, resolver.py, scout.py updates). These are leaf consumers that can be done independently.

## Verification Strategy

After each phase, these checks confirm correctness:

| Check | What It Validates |
|-------|-------------------|
| `load_pitcher_data(pitcher_id, 30)` returns data | Multi-year concat works, game_type filter did not strip all rows |
| `PitcherData.statcast` has no `game_type == "S"` or `"E"` rows | Filter applied correctly |
| `PitcherData.agg_csvs["pitcher"]` has rows from both 2025 and 2026 seasons | Multi-year CSV concat works |
| `compute_season_baseline` returns one row per pitcher (not per season) | Grouping still correct across years |
| `scout_appearances()` returns results | Scout's multi-year + game_type filter works |
| `resolver.resolve("Cole")` still resolves | Multi-parquet name table works |
| `compute_execution_metrics` includes xRV100 percentile | engine.py's `load_full_agg` call works |

## Scalability Considerations

| Concern | 2 years (now) | 5 years | 10 years |
|---------|---------------|---------|----------|
| Parquet read time | Negligible (2 files, ~300K rows total) | Add column selection at read time | Partitioned parquet or LazyFrame |
| CSV concat | Fine (16 CSVs, small files) | Still fine | Consider converting aggs to parquet |
| Memory (statcast) | ~300K rows, well within Polars comfort | ~750K rows, still fine | Filter columns at read time |
| Name table size | ~2K unique pitchers | ~4K pitchers | Still fine, dict lookup is O(1) |

For the 2-year scope of v1.6, plain eager concat of 2 parquet files and 16 CSVs is well within Polars' comfort zone. No lazy frames or column projection needed.

## Sources

- Direct code analysis of `data.py`, `engine.py`, `context.py`, `resolver.py`, `scout.py`, `analyst.py`, `cli.py`, `scout_cli.py` in the current repository (HIGH confidence -- primary source)
- `PROJECT.md` for data schema documentation: game_type column values "R" (regular), "S" (spring training), "E" (exhibition) (HIGH confidence)
- Polars `pl.concat()` for vertical DataFrame concatenation (HIGH confidence -- well-documented core API)
- Polars `DataFrame.filter()` with `is_in()` for set-based filtering (HIGH confidence)
