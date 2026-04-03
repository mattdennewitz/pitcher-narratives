# Project Research Summary

**Project:** Pitcher Narratives
**Milestone:** v1.6 — Multi-Year Data & Game Type Filtering
**Domain:** Refactoring a single-year pitcher analytics data pipeline to support multi-year (2025 + 2026) loading with regular-season-only filtering
**Researched:** 2026-04-02
**Confidence:** HIGH

## Executive Summary

v1.6 is a focused internal refactor — no new user-facing features, no new dependencies. The entire change surface is `data.py` and its consumers. Polars 1.39.3 (already installed) handles multi-year parquet loading natively via `read_parquet(list[Path])` and multi-year CSV loading via `pl.concat`. The primary concern is correctness: spring training data (game_type "S") currently contaminates every baseline in the system because `compute_season_baseline()` weight-averages across all game types. Adding a full 2025 dataset amplifies this contamination significantly. The filter must land before any other v1.6 work.

The architectural principle is clean: filter once in `data.py` at load time, let all downstream consumers receive already-clean data. Year-awareness lives entirely in `data.py` behind a `_YEARS = [2025, 2026]` constant. No other module should know about year prefixes, file counts, or game type semantics. The `PitcherData` dataclass interface does not change — adding a year means changing one constant. All 17 integration points across 4 files (data.py, engine.py, resolver.py, scout.py) are fully inventoried.

The main implementation risk is double-counting pitchers across seasons. Season baselines must be computed per-season and the correct season selected, not naively weight-averaged across all years. The execution order is critical: game_type filtering first (correctness), then year parameterization (refactor), then multi-year loading (behavior change). Each step should be verified with the existing test suite before proceeding to the next.

## Key Findings

### Recommended Stack

No new dependencies. Polars 1.39.3 covers every pattern needed: `read_parquet(list[Path])` for parallel multi-file parquet loading, `pl.concat(how="vertical")` for CSV concatenation, and `~is_in(...)` for game type exclusion. Eager loading (not LazyFrames) is correct for the dataset size (~50MB total across both years), consistent with the existing codebase, and avoids introducing `.collect()` calls everywhere for zero measurable benefit.

**Core technologies:**
- `polars 1.39.3` — multi-file parquet loading via `read_parquet(list[Path])`, verified against actual `FileSource` type alias
- `polars 1.39.3` — CSV concatenation via `pl.concat(how="vertical")`, needed because `read_csv` does NOT accept a list of paths
- `polars 1.39.3` — game type filtering via `df.filter(~pl.col("game_type").is_in(...))` with `frozenset({"S", "E"})` as exclusion set
- `pathlib.Path` — explicit path construction from `YEARS` constant, preferred over glob to fail fast on missing files

### Expected Features

This milestone has no user-facing features. It is pure infrastructure work whose output is correct, regular-season-only baselines and a data loading layer that supports two years of Statcast data.

**Must have (correctness requirements):**
- Game type filter applied in `data.py` load functions before any downstream consumption
- Multi-year parquet files concatenated transparently in `load_statcast()`
- Multi-year CSV files concatenated transparently in `_load_csv_with_dates()`
- `resolver.py` name table built from all available parquets (not just 2026)
- `engine.py` hardcoded direct CSV read on line 1563 eliminated and routed through `data.py`
- `scout.py` hardcoded CSV loads eliminated and routed through new `load_full_agg()` export

**Should have (robustness):**
- Graceful degradation when one year's files are missing (skip silently, not crash)
- "season" added to `_ID_COLS` to prevent year values being weight-averaged as metrics
- Game type filter applied in `scout.py`'s velocity baseline computation (parquet load path)

**Defer (not this milestone):**
- User-visible data freshness indicator when most recent data is from a prior season
- Auto-discovery of years from filesystem (explicit `_YEARS` constant is sufficient for now)
- Converting agg CSVs to parquet format (valid consideration at 5+ years, not needed at 2)

### Architecture Approach

Year-awareness lives entirely in `data.py`. A single `_YEARS = [2025, 2026]` constant drives all file discovery. `PARQUET_PATH` (singular) becomes `PARQUET_PATHS` (list). The CSV filename dicts drop the `"2026-"` prefix and a new multi-year loader generates per-year filenames at runtime. A shared `_filter_game_type(df)` helper applies the exclusion consistently across all load paths. A new `load_full_agg(grain)` export serves engine.py and scout.py for league-wide data access. The `PitcherData` dataclass and `load_pitcher_data()` signature are unchanged — callers get the same bundle, now backed by cleaner, broader data.

**Major components and their changes:**
1. `data.py` (primary target) — add `_YEARS`, `PARQUET_PATHS`, `_EXCLUDED_GAME_TYPES`, `_filter_game_type`, year-parameterized CSV loading, `load_full_agg()` export
2. `engine.py` (one-line fix) — replace line 1563 direct CSV read with `load_full_agg("pitcher_type")`
3. `resolver.py` (minimal) — import `PARQUET_PATHS`, concat across years for name table
4. `scout.py` (secondary) — replace 4 hardcoded CSV loads and `PARQUET_PATH` velocity load with `load_full_agg()` and `PARQUET_PATHS`
5. `context.py`, `analyst.py`, `report.py`, `cli.py`, `ask_cli.py`, `curator.py`, `scout_cli.py` — zero changes

### Critical Pitfalls

1. **Baseline contamination from spring training** — Filter to `game_type != "S"` (and `!= "E"`) in `data.py` loaders BEFORE baseline computation. `compute_season_baseline()` currently weight-averages across all game_type rows; spring training is a distinct data population (weaker hitters, experimental approaches) and must be excluded from regular-season baselines. Adding 2025 data amplifies the contamination because 2025 includes a full spring training sample. The statcast parquet has 75.9% spring training rows in 2026 alone.

2. **Double-counting across seasons in baseline computation** — Do not naive-concat two years and let `compute_season_baseline()` produce a cross-season average. Season baselines must be per-season (use the `season` column to identify target year). A pitcher who threw 95 mph in 2025 and 97 mph in 2026 should have a 2026 baseline of 97, not 96. The agg CSVs have a `season` column — use it for baseline selection.

3. **Game type filtering at the wrong layer** — `data.py` has at least 3 load paths. `engine.py` has a direct CSV read that bypasses `data.py` entirely (line 1563). `scout.py` has 4 independent CSV loads and a direct parquet read. Filter once in `data.py` via a `_filter_game_type` helper and eliminate all bypass loads. A `grep "read_csv\|read_parquet" src/ | grep -v data.py` returning zero results is the correctness gate.

4. **Resolver missing 2025-only pitchers** — `resolver.py` currently builds its name table from a single parquet. Pitchers who appeared in 2025 but not 2026 are invisible. Build the name table from all `PARQUET_PATHS` with `.unique(subset=["pitcher"])` keeping the most recent `player_name`.

5. **`_ID_COLS` missing "season"** — If `season` is not in `_ID_COLS`, the year value (2025 or 2026) gets weight-averaged as if it were a metric, producing nonsense like `2025.375`. Add "season" to the `_ID_COLS` frozenset in `data.py` and the equivalent id_col sets in `engine.py` and `scout.py`.

## Implications for Roadmap

The dependency graph is clear: `data.py` is the foundation everything imports from. All correctness concerns must be resolved there before consumer modules are updated.

### Phase 1: Data Foundation — Game Type Filtering and Year Parameterization

**Rationale:** Filtering is the correctness-critical change. It must come first because baselines produced without filtering are wrong, and every downstream computation (engine, scout, context, report) depends on correct baselines. Year parameterization in the same phase eliminates the 16 hardcoded "2026-" references and establishes the `_YEARS` constant before any multi-year loading is added. This phase produces clean single-year data as a baseline to verify against before widening to two years.
**Delivers:** `data.py` with `_YEARS`, `_EXCLUDED_GAME_TYPES`, `_filter_game_type`, `PARQUET_PATHS`, year-derived CSV filenames, `load_full_agg()` export. All existing tests pass after assertions are updated for filtered values.
**Addresses:** All table-stakes correctness requirements (filtering, year parameterization)
**Avoids:** Pitfalls 1 (baseline contamination), 3 (filtering at wrong layer), 5 (hardcoded year references), 10 (_ID_COLS missing "season")

### Phase 2: Multi-Year Loading

**Rationale:** Multi-year loading is a behavior change — it changes baseline values and widens the data window. It must land on top of the clean filtering foundation from Phase 1. With game_type filtering already in place, adding 2025 data will not introduce spring training contamination. The season boundary handling (selecting the correct season for baselines vs. concatenating for appearance history) must be resolved in this phase.
**Delivers:** `load_statcast()` and `load_agg_csvs()` reading from both 2025 and 2026 files. `load_pitcher_data()` returning data spanning both seasons with correct per-season baselines. Test suite updated for multi-year assertions.
**Avoids:** Pitfalls 2 (double-counting across seasons), 4 (missing 2025-only pitchers in resolver)

### Phase 3: Consumer Module Updates

**Rationale:** engine.py, resolver.py, and scout.py are leaf consumers that can be updated independently once the `data.py` foundation and `load_full_agg()` export are in place. These are mechanical substitutions: replace hardcoded paths with `data.py` function calls. All three are independent of each other and can be done in any order or in parallel.
**Delivers:** All bypass CSV/parquet loads eliminated. Resolver scans all parquets. Scout uses shared loading. `grep "read_csv\|read_parquet" src/ | grep -v data.py` returns zero results.
**Avoids:** Pitfalls 3 (filtering bypass in engine.py), 4 (resolver missing 2025 pitchers), 6 (scout module divergence), 8 (xRV100 percentile on wrong distribution)

### Phase Ordering Rationale

- Game type filtering before multi-year loading: if filtering and multi-year land together, it is impossible to distinguish filtering bugs from multi-year loading bugs. Staged rollout keeps debugging tractable.
- Year parameterization in Phase 1 (not Phase 2): when only 2026 files exist, it is a pure refactor with no behavior change. Moving it to Phase 2 would bundle a structural change with a behavioral change, complicating root-cause analysis.
- Consumer updates last: engine.py, resolver.py, and scout.py all import from `data.py`. Updating them before `data.py`'s new exports exist would break the build.

### Research Flags

Phases with standard patterns (no additional research needed):
- **Phase 1:** Polars filtering and file path construction are well-documented core APIs. All patterns verified against the installed library source.
- **Phase 2:** Multi-file parquet concatenation is a standard Polars pattern. The cross-season baseline selection logic is the only open design decision — use the `season` column to filter before grouping.
- **Phase 3:** Mechanical substitution of hardcoded paths with `data.py` function calls. No novel patterns.

No phase requires `/gsd:research-phase` during planning. All patterns are verified against polars 1.39.3 and the actual data files.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All patterns verified against polars 1.39.3 source via `inspect.signature`. `FileSource` type alias inspected directly. No documentation inference required. |
| Features | HIGH | This milestone has no user-facing features; all requirements are internal correctness demands derived from direct code analysis. Scope is fully bounded by PROJECT.md. |
| Architecture | HIGH | Integration points inventoried at line-level across all 4 affected files. 17 specific change sites identified. Build order is dependency-driven with no ambiguity. |
| Pitfalls | HIGH | All 11 pitfalls derived from direct line-by-line analysis of production code and all 8 test files. The bugs are demonstrably present in the current codebase, not inferred from external sources. |

**Overall confidence:** HIGH

### Gaps to Address

- **Cross-season baseline selection:** The research recommends selecting the most recent season's baseline for the analysis target, but the exact implementation (filter `season == max_season` before grouping vs. add a `target_season` parameter to `load_pitcher_data()`) was not fully specified. Resolve during Phase 2 implementation. The `season` column is present in all agg CSVs and is the correct discriminator.

- **Test fixture updates:** Five specific test assertions will break when filtering lands (test_season_baseline_weighted, test_identify_primary_fastball, test_load_agg_csvs_all_grains, and resolver tests). The correct new expected values must be computed against filtered data before updating assertions. Treat this as a Phase 1 implementation task, not a separate phase.

- **scout.py velocity baseline filter export:** `_compute_velo_baselines()` in scout.py needs game_type filtering on its statcast parquet load. Whether to export `_filter_game_type` as a public function from `data.py` or have scout.py apply the filter inline should be decided during Phase 3. Recommendation: export as `filter_game_type` (public) to prevent the pattern from diverging.

## Sources

### Primary (HIGH confidence)
- Direct code analysis: `data.py`, `engine.py`, `scout.py`, `resolver.py`, `context.py`, `analyst.py`, `cli.py`, `scout_cli.py`
- Direct analysis: all 8 test files in `tests/`
- `polars 1.39.3` installed library: `inspect.signature(pl.read_parquet)`, `FileSource` type alias, `pl.concat` signature
- Actual data: `statcast_2026.parquet` game_type distribution (S=133,887; R=31,331; C=11,162)
- Actual data: `aggs/2026-pitcher.csv` confirmed game_type="R" rows only

### Secondary (MEDIUM confidence)
- [Polars multiple files guide](https://docs.pola.rs/user-guide/io/multiple/) — glob and concat patterns for multi-file loading
- [polars.read_parquet API](https://docs.pola.rs/api/python/stable/reference/api/polars.read_parquet.html) — parameter reference

### Tertiary (LOW confidence — external research for v1.4 context, not load-bearing for v1.6)
- [SPORTSQL](https://arxiv.org/html/2508.17157v1) — Q&A primitive classification (referenced in FEATURES.md, which covers the v1.4 milestone)
- MLB AI at Bat (Google Cloud) — natural language Statcast access patterns (v1.4 context only)

---
*Research completed: 2026-04-02*
*Ready for roadmap: yes*
