# Domain Pitfalls: Multi-Year Data & Game Type Filtering

**Domain:** Adding multi-year (2025 + 2026) parquet/CSV loading and game_type filtering to an existing single-year pitcher analytics pipeline
**Researched:** 2026-04-02
**Confidence:** HIGH -- grounded in direct line-by-line analysis of data.py, engine.py, resolver.py, scout.py, context.py, analyst.py, and all 8 test files in the codebase

---

## Critical Pitfalls

Mistakes that cause data corruption, silent wrong answers, or require significant rework.

### Pitfall 1: Baseline Computation Poisoned by Spring Training Data

**What goes wrong:** `compute_season_baseline()` (data.py:179) currently does a weighted average across ALL `game_type` rows per pitcher. The docstring explicitly says "Combines game_type rows (S/C/R) into a single row." This means spring training (S) and exhibition (E) pitch data is weighted into the season baseline that feeds every downstream computation: fastball deltas, arsenal usage shifts, P+/S+/L+ comparisons, execution metrics, and platoon splits. A pitcher who experimented with a new slider grip in spring training drags down his season S+ baseline, making his regular-season performance look better by comparison. Conversely, a pitcher who was dominant in spring training (small sample, weaker competition) inflates his baseline, making regular-season numbers look worse.

The same pattern repeats in three other places:
- `compute_pitch_type_baseline()` (data.py:205) -- same game_type-agnostic weighted average
- `_compute_platoon_baseline()` (engine.py:355) -- duplicates the pattern for platoon splits
- `_build_season_baseline()` and `_build_season_type_baseline()` (scout.py:231, 248) -- the scout module has its OWN baseline computation that independently repeats the same bug

**Why it happens:** The original design correctly identified that game_type rows need combining (the weighted average is the right math), but the intent was to collapse game_type as a dimension, not to include all game types indiscriminately. When there was only 2026 data with mostly regular season games, the spring training contamination was small enough to not notice. Adding 2025 data (which has a FULL spring training) significantly amplifies the problem because 2025 spring training represents a much larger fraction of the combined dataset.

**Consequences:**
- Every delta string in the context document (velo trends, P+ trends, usage shifts) is computed against a poisoned baseline
- The LLM generates insights like "fastball velocity down 1.2 mph from season" when it's actually down 0.3 mph from regular season -- the gap is spring training inflation
- Scout scoring (scout.py) flags false positives and misses true signals because its baselines are independently contaminated
- The xRV100 percentile computation (engine.py:1491) uses the full league pitcher_type CSV without filtering, meaning percentile ranks include spring training noise for ALL pitchers in the league distribution

**Prevention:**
- Filter to `game_type == "R"` BEFORE baseline computation, not after
- The filter belongs in the data loading layer (data.py), not scattered across consumers
- Specifically: `load_agg_csvs()` should filter each DataFrame to `game_type == "R"` when the column exists, OR a new function should handle this
- The statcast parquet also has a `game_type` column -- `load_statcast()` must filter it too
- The hardcoded `full_pitcher_type_df = pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")` in engine.py:1563 bypasses all data.py abstractions and must also be filtered
- scout.py:115-118 loads CSVs independently via `_load_csv()` -- these four loads must also filter

**Detection:**
- A pitcher with 100 spring training pitches and 500 regular season pitches will have a baseline shifted by ~17% toward spring training values
- Compare `compute_season_baseline()` output with and without game_type="R" filter -- if they differ for any pitcher who played spring training, the bug is present
- Check if the `_ID_COLS` frozenset (data.py:53) still contains "game_type" after filtering -- if game_type is being used as a group-by key somewhere downstream, it will silently produce multiple rows

**Phase to address:** Phase 1 (Data Loading Restructure) -- this must be the FIRST change because every downstream computation depends on clean baselines.

---

### Pitfall 2: Double-Counting Pitchers Who Appear in Both 2025 and 2026

**What goes wrong:** When loading multi-year parquet files and concatenating them, a pitcher who pitched in both 2025 and 2026 appears in BOTH DataFrames. If the code simply concatenates without deduplication awareness, several things break:

1. **Season baselines span two seasons.** `compute_season_baseline()` groups by `pitcher` and weight-averages. If the concatenated data has 2025 rows AND 2026 rows for the same pitcher, the "season" baseline becomes a career-fragment average. A pitcher who threw 95 mph in 2025 and 97 mph in 2026 gets a baseline of ~96 mph, which makes his current 97 mph look like only +1 mph gain instead of being right at his 2026 level.

2. **Pitch type baselines lose seasonal context.** If a pitcher added a sweeper in 2026 that he didn't throw in 2025, the sweeper's baseline gets diluted by zero 2025 usage, distorting usage-rate deltas.

3. **Appearance classification spans seasons.** `classify_appearances()` groups by game_pk/game_date but doesn't account for the semantic boundary between seasons. A pitcher who was a reliever all of 2025 but converted to starting in 2026 would have his 2025 RP appearances counted alongside 2026 SP appearances, making `_is_cold_start()` and lookback window logic behave incorrectly.

4. **Lookback window math crosses the offseason.** `filter_to_window()` uses `max_date - timedelta(days=window_days)`. With a 30-day window in early April 2026, this catches late March 2026 data, which is fine. But if the statcast data starts from Opening Day 2025, a pitcher who hasn't pitched in early 2026 would have `max_date` in October 2025, and the window would look back into September 2025. This is correct behavior for 2025-only analysis but confusing if the user expects 2026 data.

**Why it happens:** The current code assumes "season" = "all data in the file." With one parquet file per year, this is true. The moment you `pl.concat()` two years, "all data in the file" becomes "two seasons" and every function that computes baselines, windows, or trends silently changes meaning.

**Prevention:**
- Do NOT concatenate years into a single DataFrame for baseline purposes. Load each year's agg CSVs separately and compute baselines per season, then select the appropriate season's baseline for the analysis being performed.
- For the statcast parquet, concatenation is fine for the pitch-level data (appearances span only one game), but the window/baseline logic must know which season's data to use.
- Add a `season` column filter wherever baselines are computed. The agg CSVs already have a `season` column -- use it.
- When computing "season baseline," define which season you mean: the most recent one where the pitcher has data, not "everything we loaded."
- PitcherData should carry a `season: int` field indicating the target analysis season.

**Detection:**
- Run `load_pitcher_data()` for a pitcher who pitched in both years and check if `season_baseline` has one row or multiple
- Check if `appearances` DataFrame contains games from both seasons
- Look for unreasonable delta values (e.g., velocity deltas > 3 mph for an established pitcher) which indicate cross-season averaging

**Phase to address:** Phase 1 (Data Loading Restructure) -- the multi-year loading architecture must define season boundaries upfront.

---

### Pitfall 3: Game Type Filtering at the Wrong Layer

**What goes wrong:** Instead of filtering in the data loading layer (data.py), each consumer (engine.py, scout.py, analyst.py, context.py) independently adds `game_type == "R"` filters. This produces three failure modes:

1. **Inconsistent filtering.** engine.py filters but scout.py doesn't (or vice versa), producing different baselines for the same pitcher. The narrative report says "P+ up 8 points" but the scout scorer doesn't flag it because it's using a different baseline.

2. **Missed filter sites.** engine.py:1563 loads the full pitcher_type CSV directly (`pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")`) for league-wide percentile computation, bypassing data.py entirely. Any filtering in data.py doesn't touch this path. There are at least 5 independent CSV-loading code paths across the codebase (data.py:94, data.py:114, engine.py:1563, scout.py:81, scout.py:115-118).

3. **Filter after aggregation.** If the agg CSVs already have per-game_type rows pre-aggregated by the upstream Pitching+ pipeline, filtering `game_type == "R"` on the agg CSVs correctly selects regular-season rows. But if someone tries to filter game_type on the statcast parquet and THEN re-aggregate, they'll get different numbers than the agg CSVs because the Pitching+ model was trained on all game types. The filter must happen at the right grain.

**Why it happens:** The path of least resistance is "add a filter where I need it." When you're modifying `compute_fastball_summary()`, it's tempting to add `.filter(pl.col("game_type") == "R")` right there. But engine.py has 12+ compute functions, scout.py has 4 baseline builders, and there's a direct CSV read in the percentile function. Remembering to filter in all of them is error-prone.

**Prevention:**
- Filter ONCE in data.py, at load time, for both parquet and CSV paths
- `load_statcast()` filters to `game_type == "R"` before returning
- `_load_csv_with_dates()` filters to `game_type == "R"` when the column exists
- Eliminate the direct `pl.read_csv()` call in engine.py:1563 -- make it go through data.py so it gets the filter automatically
- scout.py's `_load_csv()` should be eliminated; scout.py should use data.py's loading functions
- Write a test that asserts no code outside data.py calls `pl.read_csv()` or `pl.read_parquet()` on data files
- Consider making the filter configurable (defaulting to "R") rather than hardcoded, in case exhibition/spring data is needed for future features

**Detection:**
- `grep -r "read_csv\|read_parquet" src/pitcher_narratives/ | grep -v data.py` reveals bypass loading
- Differing baselines between report pipeline and scout pipeline for the same pitcher indicates inconsistent filtering
- Tests that compare `compute_season_baseline()` output vs manual calculation on filtered data

**Phase to address:** Phase 1 (Data Loading Restructure) -- centralize before anything else builds on top.

---

### Pitfall 4: Resolver Name Table Built from Single Parquet, Missing 2025-Only Pitchers

**What goes wrong:** `resolver.py:110` builds the name lookup table from `PARQUET_PATH`, which is currently `statcast_2026.parquet`. A pitcher who appeared in 2025 but not yet in 2026 (injury, retirement, minors assignment, not yet called up) will not be in the name table. The user types "Tyler Glasnow" (hypothetically only in the 2025 file), the resolver returns `not_found`, and the system reports "Pitcher not found" even though there's a full season of data available.

This is also a deduplication issue: if the name table is built from concatenated 2025+2026 parquets using `.unique(subset=["pitcher"])`, a pitcher whose `player_name` changed between years (name change, suffix addition, diacritics inconsistency) could appear as two different entries, one per year.

**Why it happens:** The resolver was built for a single-year system. `PARQUET_PATH` is a module-level constant pointing to one file. The name table is cached at module level (`_name_table`), so it builds once and never updates.

**Prevention:**
- The resolver must build its name table from ALL available parquet files, not just one
- Use `.unique(subset=["pitcher"])` on the concatenated result, keeping the MOST RECENT `player_name` per pitcher_id (in case of name changes)
- Alternatively, build the name table from the agg CSVs (which are smaller) rather than the parquet files -- the pitcher-level CSVs already have pitcher/player_name pairs
- Store both year-variants of a name in the index if they differ, both pointing to the same pitcher_id
- Test with a pitcher ID that exists only in 2025 data

**Detection:**
- Count unique pitcher IDs in combined parquets vs name table entries -- if they differ, pitchers are being dropped
- Test resolver with a known 2025-only pitcher name

**Phase to address:** Phase 1 (Data Loading Restructure) -- the resolver's data source must be updated alongside the parquet path changes.

---

## Moderate Pitfalls

Issues that cause incorrect analytics or degraded user experience but don't corrupt core data flow.

### Pitfall 5: Hardcoded "2026-" Prefixes Create a Maintenance Trap

**What goes wrong:** The codebase has 16 hardcoded references to "2026-" prefixed filenames:
- data.py lines 40-49: 8 CSV filename strings in `_SEASON_CSVS` and `_APPEARANCE_CSVS`
- scout.py lines 115-118: 4 independent `_load_csv("2026-...")` calls
- engine.py line 1563: 1 direct `pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")`
- data.py line 34: 1 `PARQUET_PATH` pointing to `statcast_2026.parquet`
- test_resolver.py line 4: docstring referencing `statcast_2026.parquet`

Adding 2025 support by duplicating these references (adding 16 more "2025-" versions) creates 32 hardcoded paths. When 2027 data arrives, it's 48. Every year adds another copy-paste round.

**Why it happens:** The original single-year design didn't need parameterization. Constants were the simplest correct solution at the time.

**Prevention:**
- Define a `YEARS = [2025, 2026]` constant and derive filenames programmatically: `f"{year}-pitcher.csv"`
- For parquets: `[DATA_DIR / f"statcast_{year}.parquet" for year in YEARS]`
- Auto-discover available years from the filesystem: `sorted(path.stem.split("_")[1] for path in DATA_DIR.glob("statcast_*.parquet"))`
- The CSV filename pattern is consistent (`{year}-{grain}.csv`), so derive all 8 grains x N years from the pattern
- Make `load_agg_csvs()` accept a `years` parameter or discover years automatically

**Detection:**
- `grep -r "2026" src/` should eventually return zero hits outside of test fixtures and documentation
- A new data year should require changing at most 1 constant or 0 lines of code

**Phase to address:** Phase 1 (Data Loading Restructure) -- this is the structural change that enables everything else.

---

### Pitfall 6: Scout Module Has Independent Data Loading, Will Diverge

**What goes wrong:** `scout.py` has its own `_load_csv()` function (line 81) and its own baseline builders (`_build_season_baseline` at line 231, `_build_season_type_baseline` at line 248). These duplicate the logic in data.py but are completely independent code paths. When data.py is updated for multi-year loading and game_type filtering, scout.py must be updated separately -- and there's nothing forcing synchronization.

The scout module also hard-filters to `level == "MLB"` (lines 121-124) but does NOT filter by game_type. After adding game_type filtering to data.py, the scout module would still include spring training data unless separately updated.

**Why it happens:** The scout module was designed as a standalone scoring tool ("Cheap triage before expensive narrative generation"). It loads data independently because it doesn't need the full PitcherData bundle -- it scans ALL pitchers, not one at a time. This is a valid architectural choice for performance, but it creates a parallel loading path that must be kept in sync.

**Prevention:**
- Extract shared loading logic from data.py into functions that both data.py and scout.py use
- At minimum, the game_type filter must be applied in scout.py's `_load_csv()`, not just data.py
- Consider making scout.py use data.py's `_load_csv_with_dates()` (currently a module-private function) -- either promote it to public API or create a shared internal module
- Write a cross-module test: for a given pitcher, assert that scout.py's baseline equals data.py's baseline

**Detection:**
- Differing results between `pitcher-scout` and `pitcher-narratives` for the same appearance
- scout.py's `_build_season_baseline()` and data.py's `compute_season_baseline()` producing different numbers for the same pitcher

**Phase to address:** Phase 1 or 2 -- depends on whether scout.py is being updated in this milestone or deferred.

---

### Pitfall 7: Test Fixtures Assume Single-Year, Single-Game-Type Data

**What goes wrong:** All tests use `TEST_PITCHER = 592155` (Booser, Cam) and call live data loading functions (`load_statcast`, `load_pitcher_data`, `load_agg_csvs`) against real data files. The tests make implicit assumptions:

1. **test_data.py:82** (`test_season_baseline_weighted`): Asserts `len(baseline) == 1`. After multi-year loading, a pitcher could have rows for both seasons, producing `len(baseline) == 2` if grouping by season.

2. **test_data.py:36** (`test_load_agg_csvs_all_grains`): Asserts exactly 8 keys. If multi-year loading changes the dict structure (e.g., keyed by `(year, grain)`), this breaks.

3. **test_engine.py:142** (`test_identify_primary_fastball`): Asserts `result == "FC"`. If 2025 data is included and Booser threw a different primary fastball in 2025, the result changes.

4. **test_resolver.py**: All name resolution tests assume `statcast_2026.parquet` as the data source. Multi-year resolution changes the name table contents, potentially changing disambiguation results (e.g., a "Johnson" test expects N candidates but 2025 data adds more Johnsons).

5. **test_engine.py:54** (`TEST_PITCHER = 592155`): This pitcher may or may not exist in 2025 data. Tests that call `load_pitcher_data()` will get different results with different data files present.

**Why it happens:** Integration tests against real data are fragile by nature. The existing tests verify behavior against a specific dataset snapshot. Changing the dataset (adding a year) changes the behavior.

**Prevention:**
- **Do not break existing tests first.** The multi-year loading should be backward-compatible: if only 2026 files exist, behavior is identical to today.
- **Add game_type filtering first** (before multi-year). This changes baselines but in a smaller, predictable way. Update test assertions after confirming the filtered values are correct.
- **For tests that assert specific numeric values** (e.g., primary fastball type, baseline row count), recalculate expected values against filtered data and update assertions.
- **Consider adding a `PITCHER_NARRATIVES_YEARS` env var** that tests can set to `[2026]` to isolate from 2025 data during initial development.
- **Tests for resolver should pin to a known-good state**: if adding 2025 data changes the name table, the "Johnson" disambiguation test needs updated expected counts.
- **Add new tests for multi-year specific behavior**: pitcher exists in 2025 only, pitcher exists in both years, pitcher changed teams between years.

**Detection:**
- Run the existing test suite after each incremental change. If more than 2-3 tests fail simultaneously, you've likely broken a shared assumption rather than individual test logic.
- Any test failure in `test_season_baseline_weighted` or `test_identify_primary_fastball` is a data shape change, not a logic bug.

**Phase to address:** Every phase should run the full test suite before and after changes. Phase 1 will cause the most breakage; plan for test updates as part of that phase.

---

### Pitfall 8: xRV100 Percentile Computation Uses Hardcoded Direct CSV Load

**What goes wrong:** engine.py line 1563 does:
```python
full_pitcher_type_df = pl.read_csv(AGGS_DIR / "2026-pitcher_type.csv")
```

This bypasses all data.py abstractions. It will not get multi-year data, will not get game_type filtering, and will not benefit from any centralized changes. The percentile rank for a pitcher's xRV100 will be computed against an unfiltered, single-year league distribution while the pitcher's own xRV100 comes from filtered, potentially multi-year data.

This creates a subtle correctness issue: the pitcher's value is "regular season only" but the league distribution includes spring training. Since spring training P+ metrics are noisier (weaker hitters, experimental approaches), the league distribution is wider, pushing percentiles toward the middle. A pitcher who is 90th percentile in regular season might show as 80th when measured against a spring-training-diluted distribution.

**Why it happens:** The percentile function needs the FULL league data for all pitchers (not filtered to one pitcher), which is a different access pattern than `load_agg_csvs()`. The expedient solution was to load the CSV directly.

**Prevention:**
- Add a `load_league_pitcher_type()` function to data.py that loads the full pitcher_type CSV with game_type filtering applied
- The function should handle multi-year data: load all years, filter to `game_type == "R"`, return the combined result
- Replace the direct read in engine.py with a call to this new function
- The function should be called once per `compute_execution_metrics()` invocation, not once per pitch type (it's already structured this way)

**Detection:**
- `grep "read_csv\|read_parquet" src/pitcher_narratives/engine.py` should return zero results after the fix
- Compare percentile values before and after filtering -- they should shift slightly for most pitchers

**Phase to address:** Phase 1 (Data Loading Restructure) -- this is part of centralizing all data loading.

---

## Minor Pitfalls

Issues that cause confusion, minor bugs, or technical debt but don't affect data correctness.

### Pitfall 9: Module-Level PARQUET_PATH Evaluated at Import Time

**What goes wrong:** `PARQUET_PATH = DATA_DIR / "statcast_2026.parquet"` (data.py:34) is evaluated when the module is first imported. If the plan is to make this dynamic (multiple parquets, year discovery), any code that imports `PARQUET_PATH` at module level will cache the old value. The resolver does this: `from pitcher_narratives.data import PARQUET_PATH` (resolver.py:18), then uses it in `_build_name_table()`.

**Prevention:**
- Replace module-level path constants with functions: `def get_parquet_paths() -> list[Path]`
- Or use a lazy-loading pattern where the paths are computed on first access
- The resolver's `_name_table` cache must be invalidated if the data source changes (e.g., new year added)

**Phase to address:** Phase 1 (Data Loading Restructure).

---

### Pitfall 10: The _ID_COLS Frozenset Determines Baseline Metric Selection

**What goes wrong:** `_ID_COLS` (data.py:53) is a frozenset that defines which columns are NOT metrics. Every column NOT in this set gets weight-averaged in the baseline computation. If new columns are added to the agg CSVs (e.g., a `season` column that varies between years), they'll be treated as metrics and weight-averaged, producing nonsense values.

The current _ID_COLS includes "game_type" -- which means game_type is excluded from metrics (correct) but also excluded from the group_by in the weighted average (also correct for collapsing across game types). However, if you add "season" to _ID_COLS, it will be excluded from metrics (correct) but also from the group_by. If you DON'T add "season" to _ID_COLS, it'll be treated as a metric and weight-averaged (e.g., `(2025 * 500 + 2026 * 300) / 800 = 2025.375`).

**Prevention:**
- Add "season" to `_ID_COLS` immediately when multi-year CSVs are loaded
- Also add it to the equivalent `id_cols` sets in engine.py:370 and scout.py:233, 251
- Consider flipping the pattern: define `_METRIC_COLS` explicitly rather than computing them by exclusion. This is more verbose but safer against new columns.

**Detection:**
- If any baseline column has a value like 2025.6 that looks like a year, _ID_COLS is missing "season"
- Print the metric columns being averaged and visually inspect for non-metric columns

**Phase to address:** Phase 1 -- trivial fix but must happen before multi-year data is loaded.

---

### Pitfall 11: filter_to_window Uses Max Date from Potentially Multi-Year Data

**What goes wrong:** `filter_to_window()` (data.py:233) computes `max_date = df["game_date"].max()` and subtracts the window. With multi-year data, this correctly finds the most recent date across all years. But there's a subtle issue: if 2026 data starts in late March but the user runs the tool in early April, the max date is in late March 2026, and a 30-day window captures late February/March 2026. This is fine.

However, if only 2025 data exists for a pitcher (they didn't pitch in 2026), `max_date` is in October 2025, and the 30-day window captures September-October 2025. The user might not realize they're looking at 6-month-old data. There's no indication in the output that this is 2025 data, not current.

**Prevention:**
- When the window is drawn from a prior season's data, surface this to the user (e.g., in PitcherData or the context prompt: "Most recent data: 2025-10-01")
- Consider adding a staleness check: if max_date is more than 90 days ago, warn the user
- The `WorkloadContext` already surfaces appearance dates, but a top-level "data freshness" indicator would be clearer

**Phase to address:** Phase 2 or 3 -- a UX concern, not a data correctness issue.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|---|---|---|
| Multi-year parquet loading | Double-counting across seasons (Pitfall 2) | Group baselines by season, select target season explicitly |
| Multi-year CSV loading | 16 hardcoded "2026-" references (Pitfall 5) | Derive filenames from year list, auto-discover |
| Game type filtering | Filter at wrong layer (Pitfall 3) | Filter ONCE in data.py at load time |
| Game type filtering | Baseline contamination (Pitfall 1) | Filter BEFORE baseline computation |
| Game type filtering | Scout module divergence (Pitfall 6) | Centralize loading or sync scout's filters |
| Resolver update | Missing 2025-only pitchers (Pitfall 4) | Build name table from ALL parquets |
| Engine percentile | Hardcoded CSV bypass (Pitfall 8) | New data.py function for league data |
| Test suite update | Single-year assumptions (Pitfall 7) | Run tests incrementally, update assertions per phase |
| Baseline computation | _ID_COLS missing "season" (Pitfall 10) | Add "season" to all id_col sets |
| Window filtering | Stale data from prior season (Pitfall 11) | Surface data freshness to user |

## Execution Order Recommendation

Based on dependency analysis of these pitfalls:

1. **First: Add game_type filtering in data.py** (addresses Pitfalls 1, 3, 8). This is the smallest change with the largest correctness impact. Filter to `game_type == "R"` in `_load_csv_with_dates()` and `load_statcast()`. Update the direct CSV read in engine.py:1563. Run tests -- some baseline values will shift.

2. **Second: Parameterize year references** (addresses Pitfall 5). Replace hardcoded "2026-" with derived paths. This is a refactor, not a behavior change (if only 2026 files exist). Tests should pass unchanged.

3. **Third: Add multi-year loading** (addresses Pitfalls 2, 4, 10). Load 2025 + 2026, add "season" to _ID_COLS, update resolver to scan all parquets. This is where most test breakage occurs.

4. **Fourth: Sync scout.py** (addresses Pitfall 6). Either refactor to use shared loading or independently apply the same filters.

5. **Fifth: Update tests** (addresses Pitfall 7). Should happen incrementally with each step above, not as a big-bang at the end.

## Sources

- Direct analysis of `data.py`, `engine.py`, `scout.py`, `resolver.py`, `context.py`, `analyst.py` in the codebase
- Direct analysis of all 8 test files in `tests/`
- PROJECT.md v1.6 milestone definition confirming game_type values "R", "S", "E" in agg CSVs
- The agg CSV schema (game_type column present in season-grain files) confirmed from _ID_COLS frozenset in data.py
