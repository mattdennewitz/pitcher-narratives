# Stack Research: v1.6 Multi-Year Data & Game Type Filtering

**Project:** Pitcher Narratives
**Milestone:** v1.6 -- Multi-Year Data & Game Type Filtering
**Researched:** 2026-04-02
**Confidence:** HIGH
**Scope:** Stack additions/changes ONLY for multi-year parquet/CSV loading and game type filtering. Existing validated stack (Python 3.14, polars 1.39.3, pydantic-ai 1.72, rapidfuzz, multi-provider LLM) is unchanged.

## Executive Summary

No new dependencies. Polars 1.39.3 already supports every pattern needed: `read_parquet` accepts `list[Path]` for multi-file loading, `pl.concat(how="vertical")` handles multi-year CSV concatenation, and `is_in` filtering handles game type exclusion. This milestone is a refactor of `data.py` internals -- not a stack change.

## Stack Changes for v1.6

### New Dependencies

None.

### What Changes

| Component | Current (v1.5) | Change for v1.6 | Why |
|-----------|----------------|------------------|-----|
| `PARQUET_PATH` constant | Single `Path` to `statcast_2026.parquet` | List of paths or glob-based discovery | Support 2025 + 2026 parquet files |
| `_SEASON_CSVS` / `_APPEARANCE_CSVS` dicts | Hardcoded `"2026-pitcher.csv"` etc. | Year-parameterized templates with multi-year iteration | Support year-prefixed CSV files for both years |
| `load_statcast()` | `pl.read_parquet(PARQUET_PATH)` | `pl.read_parquet(list_of_paths)` + game type filter | Multi-file load with immediate filtering |
| `_load_csv_with_dates()` | Loads single CSV | Loads per-year CSVs and `pl.concat`s | Multi-year aggregation data |
| `compute_season_baseline()` | Weights across game_type rows (S/C/R) | Weights across game_type rows after filtering to R only | Correct baselines exclude spring training |

### What Does NOT Change

- **engine.py**: All compute functions receive DataFrames from `data.py`. No interface changes.
- **context.py**: Receives `PitcherData` bundle. No changes.
- **report.py**: 5-phase pipeline receives assembled context. No changes.
- **analyst.py / ask_cli.py**: Tool-calling agent receives `PitcherData`. No changes.
- **resolver.py**: Needs minor update (reads from multi-year parquet), but the fuzzy matching logic is unchanged.
- **scout.py**: Needs minor update (reads `PARQUET_PATH` for velo data), but scoring logic is unchanged.

## Polars Patterns for Multi-Year Loading

### Pattern 1: Parquet -- `pl.read_parquet` with `list[Path]`

**Verified:** polars 1.39.3 `FileSource` type resolves to `str | Path | IO[bytes] | bytes | list[str] | list[Path] | list[IO[bytes]] | list[bytes]`. Passing a list of `Path` objects works natively -- polars reads each file in parallel and auto-concatenates.

```python
YEARS: list[int] = [2025, 2026]

def _discover_parquet_paths() -> list[Path]:
    """Build ordered list of statcast parquet paths for all configured years."""
    paths = [DATA_DIR / f"statcast_{year}.parquet" for year in YEARS]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing parquet files: {missing}")
    return paths

def load_statcast(pitcher_id: int) -> pl.DataFrame:
    paths = _discover_parquet_paths()
    df = pl.read_parquet(paths)
    df = df.filter(pl.col("game_type").is_in(REGULAR_SEASON_GAME_TYPES))
    result = df.filter(pl.col("pitcher") == pitcher_id)
    if result.is_empty():
        raise ValueError(f"Pitcher {pitcher_id} not found")
    return result
```

**Why `list[Path]` over glob string:** Explicit path construction from `YEARS` constant fails fast on missing files. A glob like `statcast_*.parquet` would silently succeed with fewer files than expected (e.g., if `statcast_2025.parquet` is missing, glob returns only 2026 and continues with incomplete data).

**Why `read_parquet` (eager) over `scan_parquet` (lazy):** Total dataset is ~50MB across both years. Eager read takes <1s. The code immediately filters to one pitcher (~200 rows). LazyFrame adds `.collect()` calls everywhere for zero measurable benefit. The existing codebase is entirely eager -- no reason to introduce lazy evaluation for a small dataset.

**Key parameter notes:**
- `include_file_paths="source_file"` could tag rows with origin, useful for debugging. Not needed in production.
- `missing_columns="raise"` (the default) is correct. Statcast schema is stable across 2025-2026. If schemas diverge, we want a loud error, not silent nulls.

### Pattern 2: CSV -- `pl.concat` with per-year `pl.read_csv`

**Verified:** polars 1.39.3 `read_csv` source type is `str | Path | IO[str] | IO[bytes] | bytes` -- does NOT accept a list of paths (unlike `read_parquet`). Glob patterns via `read_csv("aggs/*-pitcher.csv")` fail when multiple grains match ("schema lengths differ").

```python
_SEASON_CSV_GRAINS = {
    "pitcher": "pitcher.csv",
    "pitcher_type": "pitcher_type.csv",
    "pitcher_type_platoon": "pitcher_type_platoon.csv",
    "team": "team.csv",
}

def _load_csv_multi_year(grain: str, pitcher_id: int | None) -> pl.DataFrame:
    """Load a CSV agg file across all available years and concatenate."""
    template = {**_SEASON_CSV_GRAINS, **_APPEARANCE_CSV_GRAINS}[grain]
    frames = []
    for year in YEARS:
        path = AGGS_DIR / f"{year}-{template}"
        if path.exists():
            df = pl.read_csv(path)
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No CSV files found for grain '{grain}'")
    combined = pl.concat(frames, how="vertical")
    # Apply game_type filter and pitcher filter
    if "game_type" in combined.columns:
        combined = combined.filter(pl.col("game_type").is_in(REGULAR_SEASON_GAME_TYPES))
    if "game_date" in combined.columns:
        combined = combined.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))
    if pitcher_id is not None and "pitcher" in combined.columns:
        combined = combined.filter(pl.col("pitcher") == pitcher_id)
    return combined
```

**Why `pl.concat` over glob:** The 8 grain files have different schemas (pitcher.csv: 30 columns, pitcher_type.csv: 32+, etc.), so glob patterns match wrong files. Explicit per-year loading with `pl.concat(how="vertical")` is predictable.

**Why `how="vertical"`:** All year-files for the same grain share identical schemas. Vertical concat stacks rows. This is the default but explicit is clearer.

**Why `path.exists()` check instead of raising:** CSVs might lag -- 2025 data could exist before 2026, or vice versa. Graceful fallback to available years is safer than requiring all years to be present. The parquet files should all be present (they're the primary data), but agg CSVs are derived and may be generated incrementally.

### Pattern 3: Game Type Filtering

**Verified from actual data:**

| Source | game_type values | Row counts (2026) |
|--------|-----------------|-------------------|
| `statcast_2026.parquet` | S, R, C | S=133,887; R=31,331; C=11,162 |
| `aggs/2026-pitcher.csv` | R only | All rows are game_type=R |

- **S** = Spring Training (75.9% of 2026 statcast rows -- early-season data dominated by ST)
- **R** = Regular Season (17.8%)
- **C** = Championship Series / All-Star / Exhibition (6.3%)
- Agg CSVs only contain R rows because the upstream Pitching+ aggregation pipeline already filters

**Filtering constant:**

```python
REGULAR_SEASON_GAME_TYPES = frozenset({"R"})
```

**Where to filter:**

1. **Statcast parquet** -- filter in `load_statcast()` immediately after `read_parquet`, before any downstream processing. This is the critical filter: 82% of statcast rows are non-regular-season.

2. **Agg CSVs** -- filter in `_load_csv_multi_year()` as defense-in-depth. The upstream pipeline already filters to R, but if that changes or if 2025 data has different behavior, we're protected.

3. **NOT in downstream consumers.** `engine.py`, `context.py`, `report.py`, `analyst.py` should all receive already-filtered data. Single filtering point in `data.py` prevents leakage.

**Why `frozenset` + `is_in`:** Extensible to include postseason game types (D=Division Series, L=League Championship, W=World Series) later without code changes. Constant makes allowed types explicit and grep-able.

**Impact on baselines:** `compute_season_baseline()` currently uses n_pitches-weighted averaging across game_type rows. After filtering CSVs to R only, this averaging becomes a passthrough (single game_type). The function still works correctly -- it just collapses fewer rows. No code change needed in the function itself.

## Integration Points

### Files that import from `data.py` and need attention:

| Module | Import | Impact |
|--------|--------|--------|
| `resolver.py` | `PARQUET_PATH` (singular `Path`) | Must change to use multi-file loading. Options: (a) import a new function that returns concatenated name table, or (b) import a `PARQUET_PATHS` list. Recommend (a) -- expose a `load_pitcher_names() -> pl.DataFrame` function from `data.py`. |
| `scout.py` | `PARQUET_PATH` (singular `Path`) | Line 283: `pl.read_parquet(PARQUET_PATH, columns=[...])` for velo data. Must change to multi-file read. Same pattern: `pl.read_parquet(paths, columns=[...])`. |
| `engine.py` | `AGGS_DIR`, `PitcherData` | Uses `AGGS_DIR` for `RV_df.csv` (not year-prefixed, no change needed). `PitcherData` interface unchanged. |
| `cli.py` | `load_pitcher_data` | No change -- calls orchestrator function. |
| `ask_cli.py` | `load_pitcher_data` | No change -- calls orchestrator function. |
| `context.py` | `PitcherData` | No change -- receives already-loaded data. |
| `analyst.py` | `PitcherData` | No change -- receives already-loaded data. |

### Key design decision: Year-awareness scope

**Recommendation:** Year-awareness lives entirely in `data.py`. Replace `PARQUET_PATH` (singular constant) with either:
- A `YEARS` constant + discovery functions, or
- A `PARQUET_PATHS` list constant

The CSV filename dicts (`_SEASON_CSVS`, `_APPEARANCE_CSVS`) become grain-only templates (strip the `2026-` prefix), with the year applied at load time.

No other module should know about year prefixes or file naming conventions.

### The `PitcherData` dataclass

**No interface change.** Downstream consumers receive the same `PitcherData` bundle. The data inside it now spans multiple years, but the fields (statcast, appearances, agg_csvs, etc.) are the same type and shape. This is the key benefit of centralizing loading in `data.py`.

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `scan_parquet` / LazyFrames | ~50MB total across 2 years. Eager read <1s. Lazy adds `.collect()` everywhere for zero benefit. | `pl.read_parquet(list[Path])` |
| `pyarrow.dataset` | Polars handles multi-file parquet natively. PyArrow adds API surface for no gain. | `pl.read_parquet(list[Path])` |
| `duckdb` | Sometimes suggested for multi-file queries. Massive dependency, overkill for 2 files. | `pl.read_parquet` + `pl.concat` |
| Hive partitioning | Requires reorganizing files into `year=2025/` directories. Unnecessary for 2 flat files. | Year-prefixed filenames |
| `glob` stdlib module | `pathlib.Path.glob()` or explicit path construction is sufficient. | `DATA_DIR / f"statcast_{year}.parquet"` |
| New config system for years | Two years don't justify YAML/TOML config. A module-level `YEARS = [2025, 2026]` constant is sufficient. Add config later if year count grows. | `YEARS` constant |
| `missing_columns="insert"` | Only needed if schemas differ across years. Statcast schema is stable 2025-2026. Silent null columns mask real problems. | Default `missing_columns="raise"` |
| `include_file_paths` parameter | Adds a source column to every DataFrame. Useful for debugging but unnecessary overhead in production. The `season` column already identifies year. | The existing `season` column in the data |
| Environment variable for game type filter | The filter is a safety/correctness concern, not a user preference. Allowing `GAME_TYPES=S,R` via env var invites broken baselines. | Hardcoded `REGULAR_SEASON_GAME_TYPES` constant |

## Version Compatibility

| Package | Version | Status | Notes |
|---------|---------|--------|-------|
| polars | 1.39.3 | Already installed | `read_parquet(list[Path])` verified. `pl.concat(how="vertical")` verified. `is_in` filtering verified. No upgrade needed. |
| Python | 3.14 | Already pinned | `pathlib.Path` works as expected. `frozenset` for game type constant works. |

No new packages. No version upgrades. The existing polars 1.39.3 handles this milestone completely.

## Sources

| Source | What Verified | Confidence |
|--------|---------------|------------|
| polars 1.39.3 venv (`inspect.signature`) | `read_parquet` accepts `list[Path]` via `FileSource` type alias | HIGH |
| polars 1.39.3 venv (`inspect.signature`) | `read_csv` does NOT accept `list[Path]` -- source is `str \| Path \| IO` only | HIGH |
| polars 1.39.3 venv (`inspect.signature`) | `pl.concat` signature: `how: ConcatMethod = 'vertical'` | HIGH |
| polars 1.39.3 venv (`FileSource` type) | Resolves to `str \| Path \| IO[bytes] \| bytes \| list[str] \| list[Path] \| list[IO[bytes]] \| list[bytes]` | HIGH |
| Actual data: `statcast_2026.parquet` | game_type distribution: S=133,887, R=31,331, C=11,162 | HIGH |
| Actual data: `aggs/2026-pitcher.csv` | Contains only `game_type="R"` rows | HIGH |
| Project source: `data.py` | Current loading patterns, constant structure, baseline computation | HIGH |
| [Polars multiple files guide](https://docs.pola.rs/user-guide/io/multiple/) | Glob and concat patterns for multi-file loading | MEDIUM |
| [polars.read_parquet API](https://docs.pola.rs/api/python/stable/reference/api/polars.read_parquet.html) | Parameter reference | MEDIUM |

---
*Stack research for: v1.6 Multi-Year Data & Game Type Filtering*
*Researched: 2026-04-02*
