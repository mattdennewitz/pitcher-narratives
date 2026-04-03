# Phase 16: Data Foundation - Research

**Researched:** 2026-04-02
**Domain:** Polars DataFrame filtering, path parameterization, Python module-level constants
**Confidence:** HIGH

## Summary

Phase 16 modifies `data.py` to (1) filter parquet data to allowed game types at load time, (2) replace all hardcoded year-prefixed paths with a `_YEARS` constant, (3) ensure `season` is treated as an identity column, and (4) export `filter_game_type` as a public function. The scope is entirely within `data.py` and `tests/test_data.py` -- consumer modules (engine.py, scout.py, resolver.py) are Phase 18 scope.

The primary correctness concern is that `statcast_2026.parquet` contains 176,380 rows of which 75.9% are spring training (game_type "S") and 6.3% are exhibition (game_type "C"). Only 17.8% are regular season (game_type "R"). Without filtering, every baseline in the system is contaminated by spring training data where pitchers face weaker lineups and experiment with pitch development. The CSVs in `aggs/` already contain only game_type "R" rows, so CSV filtering is a defensive measure; the parquet filter is the critical path.

The test fixture pitcher (592155, Booser) drops from 13 appearances to 1 after filtering. The `test_swingman_classification` test (which asserts both SP and RP roles) will need a different test pitcher. All other data tests will continue passing because they either test CSV-backed data (already R-only) or make assertions that hold with fewer rows.

**Primary recommendation:** Use an allowlist approach (`_ALLOWED_GAME_TYPES = frozenset({"R", "F", "D", "L", "W"})`) matching DFND-01, apply in `load_statcast()` immediately after read, and export as `filter_game_type()`. Replace hardcoded paths with `_YEARS`-derived generation. Update test fixture to pitcher 676571 (Poulin, PJ) who has 4 regular-season appearances with both SP and RP roles.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key decisions already locked in STATE.md:
- Filter once in data.py at load time, all downstream consumers receive clean data
- Explicit _YEARS constant over filesystem auto-discovery (sufficient for 2 years)
- Per-season baselines (not cross-season averaged) to prevent double-counting artifacts
- Export filter_game_type as public API for consumer modules

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase.

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DFND-01 | Data pipeline filters to allowed game types (R, F, D, L, W) at load time, excluding spring training and exhibition data | Parquet has S (75.9%), C (6.3%), R (17.8%). Use `_ALLOWED_GAME_TYPES` frozenset with `is_in()` filter in `load_statcast()`. CSVs already R-only but apply filter defensively. |
| DFND-02 | Year-specific hardcoded paths replaced with parameterized loading from a `_YEARS` constant | 9 hardcoded `"2026-"` references in `data.py` (1 parquet path + 8 CSV filenames). Replace with `_YEARS = [2026]` and derive paths via f-string. |
| DFND-03 | "season" added to `_ID_COLS` so year values are not weight-averaged as metrics | `season` is ALREADY in `_ID_COLS` (verified). However, `compute_season_baseline()` groups by `pitcher` only -- it should group by `["pitcher", "season"]` for per-season baselines when multi-year data arrives (Phase 17). Phase 16 can add this grouping now as a forward-compatible no-op (single year = same result). |
| DFND-04 | `filter_game_type` helper exported as public API for use by consumer modules | Add to `__all__`, implement as `filter_game_type(df: pl.DataFrame) -> pl.DataFrame`. Use internally in `load_statcast()` and `load_csv()`. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Data format**: Static parquet + CSV files, no live API calls
- **Python version**: 3.14+
- **Conventions**: snake_case functions, UPPER_SNAKE_CASE constants, Google-style docstrings, type hints on all signatures
- **Module design**: `__all__` exports define public API, internal helpers prefixed with `_`
- **Testing**: pytest (configured in pyproject.toml)
- **Linting**: ruff configured in pyproject.toml

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame filtering, file I/O, column operations | Already installed, all data operations use it |
| pathlib | stdlib | Path construction from `_YEARS` constant | Already used throughout data.py |
| pytest | 9.0.2 | Test framework | Already configured in pyproject.toml |

### Supporting
No new libraries needed. This phase uses only existing dependencies.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Allowlist (`is_in`) | Exclusion list (`~is_in({"S","E"})`) | Allowlist is safer: unknown game types default to excluded. DFND-01 specifies allowed types explicitly. |
| `_YEARS = [2026]` (list) | `_YEARS = (2026,)` (tuple) | List is conventional for ordered sequences; tuple works but reads as immutable config. List matches the prior research. |

## Architecture Patterns

### Current data.py Structure
```
data.py (301 lines)
  Constants: DATA_DIR, PARQUET_PATH, AGGS_DIR, RV_DF_PATH
  Dicts: _SEASON_CSVS (4 entries), _APPEARANCE_CSVS (4 entries)
  Identity: _ID_COLS frozenset
  Dataclass: PitcherData
  Functions: load_csv, load_statcast, load_run_values, load_agg_csvs,
             classify_appearances, compute_season_baseline,
             compute_pitch_type_baseline, filter_to_window, load_pitcher_data
  Exports: __all__ (12 items)
```

### Target data.py Structure (after Phase 16)
```
data.py
  Constants: DATA_DIR, AGGS_DIR, RV_DF_PATH, _YEARS, _ALLOWED_GAME_TYPES
  Derived: PARQUET_PATH (from _YEARS[0] -- singular, single year still)
  Grains: _SEASON_GRAINS (list of grain names), _APPEARANCE_GRAINS (list)
  Identity: _ID_COLS frozenset (unchanged -- season already present)
  Dataclass: PitcherData (unchanged)
  Functions: filter_game_type (NEW, public), load_csv (updated),
             load_statcast (updated with filter), load_run_values (unchanged),
             load_agg_csvs (updated to derive filenames from _YEARS),
             classify_appearances (unchanged), compute_season_baseline (unchanged),
             compute_pitch_type_baseline (unchanged), filter_to_window (unchanged),
             load_pitcher_data (unchanged)
  Exports: __all__ (13 items -- adds filter_game_type)
```

### Pattern 1: Allowlist Game Type Filter
**What:** Filter DataFrame rows to allowed game types using `is_in()`.
**When to use:** Every function that reads from parquet or CSV.
**Example:**
```python
# Verified against polars 1.39.3 API
_ALLOWED_GAME_TYPES = frozenset({"R", "F", "D", "L", "W"})

def filter_game_type(df: pl.DataFrame) -> pl.DataFrame:
    """Filter DataFrame to regular-season and postseason game types.

    Retains rows where game_type is one of: R (Regular Season),
    F (Wild Card), D (Division Series), L (League Championship),
    W (World Series). Excludes spring training (S), exhibition (E/C),
    and any other non-regular-season game types.

    If the DataFrame has no game_type column, returns it unchanged.

    Args:
        df: Input DataFrame, possibly containing a game_type column.

    Returns:
        Filtered DataFrame with only allowed game type rows.
    """
    if "game_type" not in df.columns:
        return df
    return df.filter(pl.col("game_type").is_in(list(_ALLOWED_GAME_TYPES)))
```

### Pattern 2: Year-Parameterized Path Generation
**What:** Derive file paths from a `_YEARS` constant instead of hardcoding.
**When to use:** All parquet and CSV path construction.
**Example:**
```python
_YEARS: list[int] = [2026]

# Parquet path (single year for now, Phase 17 will iterate)
PARQUET_PATH = DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"

# CSV filename generation (replaces _SEASON_CSVS and _APPEARANCE_CSVS dicts)
_SEASON_GRAINS = ("pitcher", "pitcher_type", "pitcher_type_platoon", "team")
_APPEARANCE_GRAINS = (
    "pitcher_appearance",
    "pitcher_type_appearance",
    "pitcher_type_platoon_appearance",
    "all_pitches",
)

def _csv_filename(grain: str, year: int | None = None) -> str:
    """Generate CSV filename for a grain and year."""
    y = year if year is not None else _YEARS[-1]
    return f"{y}-{grain}.csv"
```

### Pattern 3: Backward-Compatible PARQUET_PATH
**What:** Keep `PARQUET_PATH` as a module-level constant pointing to the latest year's parquet, since consumer modules (resolver.py, engine.py) import it directly.
**When to use:** Phase 16 only -- Phase 17 will introduce `PARQUET_PATHS` (list).
**Why:** Changing `PARQUET_PATH` to a list would break engine.py and resolver.py imports (Phase 18 scope). Phase 16 changes data.py internals only.

### Anti-Patterns to Avoid
- **Filtering after construction:** Do NOT filter game_type in `load_pitcher_data()` or downstream -- filter inside `load_statcast()` and `load_csv()` so no unfiltered data escapes.
- **Hardcoding "2026" anywhere new:** Every year reference must derive from `_YEARS`.
- **Changing PitcherData interface:** The dataclass fields and `load_pitcher_data()` signature must remain unchanged -- consumers depend on them.
- **Modifying engine.py/scout.py/resolver.py:** These are Phase 18 scope. Phase 16 touches only data.py and tests.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Game type filtering | Custom string matching | `pl.col("game_type").is_in(list(_ALLOWED_GAME_TYPES))` | Polars native, vectorized, handles nulls correctly |
| Path construction | String concatenation | `f"statcast_{year}.parquet"` with `Path /` operator | Type-safe, cross-platform |
| DataFrame column check | Try/except on column access | `"game_type" in df.columns` | Explicit, no exception overhead |

## Common Pitfalls

### Pitfall 1: Test Fixture Becomes Degenerate After Filtering
**What goes wrong:** Test pitcher 592155 (Booser) drops from 13 appearances (1 SP + 12 RP) to 1 appearance (RP only) after game_type filtering. The `test_swingman_classification` test asserts both SP and RP roles exist.
**Why it happens:** 92% of Booser's pitches are spring training/exhibition. His only regular-season appearance is a single relief outing.
**How to avoid:** Change test fixture to pitcher 676571 (Poulin, PJ) who has 4 regular-season appearances with both SP (1) and RP (3) roles. Alternatively, keep 592155 for most tests (1 RP appearance is sufficient for basic assertions) and use 676571 specifically for the swingman test.
**Warning signs:** Tests that assert `len(appearances) > N` or `roles == ["RP", "SP"]` on the filtered data.

### Pitfall 2: Filter Applied in Wrong Scope
**What goes wrong:** Adding filter_game_type inside `compute_season_baseline()` or `classify_appearances()` instead of in the loaders.
**Why it happens:** Tempting to filter at the computation layer since that's where correctness matters.
**How to avoid:** Filter in `load_statcast()` and `load_csv()` -- the gate functions. Computation functions receive already-clean data.
**Warning signs:** `filter_game_type` called in multiple places instead of once at load time.

### Pitfall 3: Breaking PARQUET_PATH Import in Consumer Modules
**What goes wrong:** Renaming `PARQUET_PATH` to something else or making it a list breaks `resolver.py` (line 19) and `engine.py` (line 201) which import it.
**Why it happens:** Natural instinct to rename to `PARQUET_PATHS` when parameterizing.
**How to avoid:** Keep `PARQUET_PATH` as-is in Phase 16. It still points to a single file. Phase 17/18 will handle the multi-path transition.
**Warning signs:** Import errors in resolver.py or engine.py tests.

### Pitfall 4: CSV Filenames Diverge from Grain Names
**What goes wrong:** The mapping from grain name to CSV filename breaks if grain names don't match the file naming convention exactly.
**Why it happens:** Current `_SEASON_CSVS` dict maps e.g. `"pitcher"` to `"2026-pitcher.csv"`. Switching to `f"{year}-{grain}.csv"` only works if grain names match file names.
**How to avoid:** Verify: `pitcher` -> `2026-pitcher.csv`, `pitcher_type` -> `2026-pitcher_type.csv`, etc. All 8 grains match exactly. Use the grain name directly in the f-string.
**Warning signs:** `FileNotFoundError` when loading CSVs with the new generation logic.

### Pitfall 5: compute_season_baseline Groups By Pitcher Only
**What goes wrong:** When Phase 17 adds 2025 data, `compute_season_baseline()` will weight-average across seasons (2025 + 2026) into a single row per pitcher.
**Why it happens:** Current `group_by("pitcher")` collapses all seasons. With single-year data this is a non-issue.
**How to avoid:** This is Phase 17's concern, not Phase 16. However, Phase 16 could optionally add `"season"` to the group_by as a forward-compatible change (no-op with single year). Decision: leave as-is for Phase 16 -- the DFND-03 requirement is only that `season` be in `_ID_COLS` (already true), not that baselines be per-season (that's MYLD-04).
**Warning signs:** Nonsense baseline values like season=2025.375 when multi-year data is added.

## Code Examples

### Example 1: Adding filter_game_type to data.py
```python
# At module level, after _ID_COLS
_ALLOWED_GAME_TYPES = frozenset({"R", "F", "D", "L", "W"})


def filter_game_type(df: pl.DataFrame) -> pl.DataFrame:
    """Filter DataFrame to regular-season and postseason game types.

    Retains rows where game_type is one of: R (Regular Season),
    F (Wild Card), D (Division Series), L (League Championship),
    W (World Series). Removes spring training, exhibition, and
    other non-competitive game types.

    If the DataFrame has no game_type column, returns it unchanged.

    Args:
        df: Input DataFrame, possibly containing a game_type column.

    Returns:
        Filtered DataFrame with only allowed game type rows.
    """
    if "game_type" not in df.columns:
        return df
    return df.filter(pl.col("game_type").is_in(list(_ALLOWED_GAME_TYPES)))
```

### Example 2: Updated load_statcast with filtering
```python
def load_statcast(pitcher_id: int) -> pl.DataFrame:
    """Load Statcast pitch-level data filtered to a single pitcher.

    Reads the parquet file, filters to allowed game types (excluding
    spring training and exhibition), then filters to the given pitcher.

    Args:
        pitcher_id: MLB pitcher ID to filter on.

    Returns:
        Polars DataFrame containing only regular-season rows for the given pitcher.

    Raises:
        ValueError: If no rows found for the given pitcher ID after filtering.
    """
    df = pl.read_parquet(PARQUET_PATH)
    df = filter_game_type(df)
    result = df.filter(pl.col("pitcher") == pitcher_id)
    if result.is_empty():
        raise ValueError(f"Pitcher {pitcher_id} not found")
    return result
```

### Example 3: Year-parameterized CSV filename generation
```python
_YEARS: list[int] = [2026]

_SEASON_GRAINS = ("pitcher", "pitcher_type", "pitcher_type_platoon", "team")
_APPEARANCE_GRAINS = (
    "pitcher_appearance",
    "pitcher_type_appearance",
    "pitcher_type_platoon_appearance",
    "all_pitches",
)


def load_agg_csvs(pitcher_id: int) -> dict[str, pl.DataFrame]:
    """Load all Pitching+ CSV aggregation files filtered to a pitcher."""
    all_grains = [*_SEASON_GRAINS, *_APPEARANCE_GRAINS]
    result: dict[str, pl.DataFrame] = {}
    for grain in all_grains:
        filename = f"{_YEARS[-1]}-{grain}.csv"
        pid = None if grain == "team" else pitcher_id
        result[grain] = load_csv(filename, pid)
    return result
```

### Example 4: Updated load_csv with filtering
```python
def load_csv(filename: str, pitcher_id: int | None) -> pl.DataFrame:
    """Load a CSV agg file, filter game types, parse dates, and optionally filter to pitcher."""
    path = AGGS_DIR / filename
    df = pl.read_csv(path)
    df = filter_game_type(df)
    if "game_date" in df.columns:
        df = df.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))
    if pitcher_id is not None and "pitcher" in df.columns:
        df = df.filter(pl.col("pitcher") == pitcher_id)
    return df
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| All game types included | Filter to allowed types at load time | Phase 16 | Baselines computed from regular season only |
| Hardcoded `"2026-"` in 9 places | `_YEARS` constant + f-string generation | Phase 16 | Single constant controls all year references |
| `_filter_game_type` private helper | `filter_game_type` public export | Phase 16 | Consumer modules can use it independently |

## Open Questions

1. **Should `_YEARS` be `[2026]` or `[2025, 2026]`?**
   - What we know: Only 2026 data files exist currently. Phase 17 will add 2025 support.
   - What's unclear: Whether to set `_YEARS = [2026]` now and expand in Phase 17, or set `_YEARS = [2025, 2026]` now with graceful skip for missing files.
   - Recommendation: `_YEARS = [2026]` in Phase 16. This keeps Phase 16 as a pure refactor with no behavior change. Phase 17 expands to `[2025, 2026]` and adds graceful-skip logic.

2. **Should `PARQUET_PATH` stay singular or become `PARQUET_PATHS`?**
   - What we know: `resolver.py` imports `PARQUET_PATH` directly. `engine.py` also imports it.
   - What's unclear: Whether changing to a derived path `DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"` could cause import-time issues.
   - Recommendation: Keep `PARQUET_PATH` as singular, derive from `_YEARS[-1]`. This is backward-compatible and resolves to the same path. Phase 17 introduces `PARQUET_PATHS` list.

3. **Which test pitcher for swingman test?**
   - What we know: 676571 (Poulin, PJ) has 4 R-game appearances with both SP and RP. 670990 (Ramirez, Yohan) has 3. 656641 (Latz, Jacob) has 2.
   - Recommendation: 676571 (Poulin) -- most appearances, most robust test fixture.

## Data Analysis Results

### Parquet Game Type Distribution
| Game Type | Description | Rows | Percentage |
|-----------|-------------|------|------------|
| S | Spring Training | 133,887 | 75.9% |
| C | Exhibition/College | 11,162 | 6.3% |
| R | Regular Season | 31,331 | 17.8% |

### CSV Game Type Distribution
All 8 CSVs in `aggs/` contain only `game_type = "R"` rows.

### Test Pitcher Impact (592155, Booser)
| Metric | Before Filter | After Filter |
|--------|--------------|--------------|
| Pitch rows | 189 | 16 |
| Appearances | 13 | 1 |
| Roles | SP + RP | RP only |
| Tests affected | `test_swingman_classification` | Fixture must change |

### Replacement Pitcher Candidates (both SP+RP in R games)
| Pitcher ID | Name | R-Game Appearances | Roles |
|------------|------|--------------------|-------|
| 676571 | Poulin, PJ | 4 | SP + RP |
| 670990 | Ramirez, Yohan | 3 | SP + RP |
| 656641 | Latz, Jacob | 2 | SP + RP |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_data.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DFND-01 | load_statcast excludes S/C/E game types | unit | `uv run pytest tests/test_data.py::test_load_statcast_filters_game_type -x` | Wave 0 |
| DFND-01 | load_csv applies game_type filter | unit | `uv run pytest tests/test_data.py::test_load_csv_filters_game_type -x` | Wave 0 |
| DFND-01 | filter_game_type passes through non-game-type DataFrames | unit | `uv run pytest tests/test_data.py::test_filter_game_type_no_column -x` | Wave 0 |
| DFND-02 | No hardcoded "2026-" in _SEASON_CSVS/_APPEARANCE_CSVS | unit | `uv run pytest tests/test_data.py::test_no_hardcoded_year_in_csv_dicts -x` | Wave 0 |
| DFND-02 | _YEARS constant exists and drives path generation | unit | `uv run pytest tests/test_data.py::test_years_constant_drives_paths -x` | Wave 0 |
| DFND-03 | season in _ID_COLS | unit | `uv run pytest tests/test_data.py::test_season_in_id_cols -x` | Wave 0 |
| DFND-04 | filter_game_type in __all__ | unit | `uv run pytest tests/test_data.py::test_filter_game_type_exported -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_data.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_data.py::test_load_statcast_filters_game_type` -- covers DFND-01 for parquet
- [ ] `tests/test_data.py::test_load_csv_filters_game_type` -- covers DFND-01 for CSV
- [ ] `tests/test_data.py::test_filter_game_type_no_column` -- covers DFND-01 edge case
- [ ] `tests/test_data.py::test_filter_game_type_exported` -- covers DFND-04
- [ ] `tests/test_data.py::test_no_hardcoded_year_in_csv_dicts` -- covers DFND-02
- [ ] `tests/test_data.py::test_swingman_classification` -- update fixture to 676571

## Pre-Existing Issues (Out of Phase 16 Scope)

1. **scout.py calls `load_csv()` with 1 argument** (lines 114-117) but `load_csv` requires 2. These calls are broken and are Phase 18 scope.
2. **engine.py has 3 direct data reads** (lines 200, 232, 1791) that bypass data.py. Phase 18 scope.
3. **resolver.py imports `PARQUET_PATH`** for name table building. Phase 18 scope.

## Sources

### Primary (HIGH confidence)
- Direct code analysis: `src/pitcher_narratives/data.py` (301 lines) -- full read
- Direct code analysis: `tests/test_data.py` (160 lines) -- full read
- Direct data analysis: `statcast_2026.parquet` via polars -- game_type distribution verified
- Direct data analysis: all 8 `aggs/2026-*.csv` files -- game_type values verified
- Prior milestone research: `.planning/research/SUMMARY.md` and `.planning/research/ARCHITECTURE.md`
- polars 1.39.3 installed -- `is_in()`, `filter()`, `read_parquet()` verified via actual usage

### Secondary (MEDIUM confidence)
- Test pitcher analysis: 592155 and 676571 impact verified by running actual queries against data
- Full test suite run: 15/15 data tests passing, 211/286 overall tests passing (remaining failures are data-file-missing in worktree)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all polars patterns verified against installed 1.39.3
- Architecture: HIGH - single-module change (data.py), all integration points inventoried at line level
- Pitfalls: HIGH - test fixture impact verified by running actual data queries; all 5 pitfalls derived from code/data analysis

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable -- no external dependencies or fast-moving libraries)
