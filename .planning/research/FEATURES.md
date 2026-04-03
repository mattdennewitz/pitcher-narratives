# Feature Research: Multi-Year Data Loading & Game Type Filtering

**Domain:** MLB pitcher scouting narrative generation (CLI tool)
**Researched:** 2026-04-02
**Confidence:** HIGH

## Context

The project currently loads a single `statcast_2026.parquet` and 8 CSV files prefixed `2026-`. The statcast parquet contains game_type values S (Spring Training: 133,887 rows), C (Cactus League: 11,162 rows), and R (Regular Season: 31,331 rows), but the Pitching+ CSV aggregations only contain R rows. The `compute_season_baseline` function weight-averages across all game_type rows (S/C/R) when multiple exist. Since spring training data represents 76% of current pitch-level data and has fundamentally different competitive context, any downstream computation that touches the raw parquet is contaminated by non-competitive pitches.

The milestone adds two capabilities: (1) filtering by game type so narratives reflect regular-season performance, and (2) loading data from multiple seasons (2025 + 2026) so year-over-year trends become visible.

## Feature Landscape

### Table Stakes (Users Expect These)

Features that must ship for multi-year + game-type filtering to be useful. Without these, the feature is broken or misleading.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Filter statcast parquet by game_type before all downstream computation | Spring training pitches (76% of current rows) have different competitive context: pitchers experiment with new grips, face minor leaguers, limit effort to 85%, cap pitch counts. Including ST data in baselines corrupts every metric. This is the highest-priority fix. | LOW | Add `game_type` filter param to `load_statcast()`, default to `"R"`. The parquet already has the column. Single `pl.filter()` call. |
| Filter appearance-level CSV aggs by game_type | `compute_season_baseline` weight-averages across game_type rows. Currently the CSVs only contain R, so this is a no-op today -- but it must be defensive for when CSVs gain S/C/R rows. | LOW | CSVs already have `game_type` column. Filter before baseline computation. Protect against future data shape changes. |
| Multi-year parquet discovery and loading | Users expect `pitcher-narratives -p 592155` to use all available season data. A pitcher's 2025 regular season is the baseline their 2026 performance should be compared against. | MEDIUM | Glob `statcast_*.parquet` in DATA_DIR, concatenate with `pl.concat(how="diagonal")`. Must handle schema differences across years (new columns, removed columns). |
| Multi-year CSV agg discovery and loading | Pitching+ CSVs are year-prefixed (`2026-pitcher.csv`). Loading 2025 data means discovering `2025-pitcher.csv` etc. and concatenating. | MEDIUM | Glob `*-{grain}.csv` pattern per grain. CSVs have a `season` column for disambiguation after concat. Must handle missing grains (e.g., 2025 may lack some appearance-level files). |
| CLI flag to select game types | Users need to opt into spring training data when desired (e.g., early-March scouting of a prospect). Default must be regular season only. | LOW | `--game-type R` (default). Accept comma-separated codes for multi-select (e.g., `R,S`). Treat C and S equivalently as "spring training" for user convenience. |
| Name resolver works across all loaded seasons | `resolve()` builds a name table from the parquet. Multi-year means scanning all parquets so a pitcher who only appears in 2025 data is still findable. | MEDIUM | `_build_name_table()` currently reads one `PARQUET_PATH`. Must read all discovered parquets and deduplicate by pitcher ID, preferring the most recent season's name. |
| Season-aware baseline computation | Season baselines must reflect only the relevant season, not blend 2025 and 2026 metrics. A pitcher's "season baseline" for a 2026 appearance should use 2026 data only. | MEDIUM | Group by `season` column before weight-averaging in `compute_season_baseline` and `compute_pitch_type_baseline`. The `season` column exists in all CSVs. |
| Hardcoded file references eliminated | `_SEASON_CSVS` and `_APPEARANCE_CSVS` hardcode `"2026-"` prefixes. `compute_execution_metrics` hardcodes `"2026-pitcher_type.csv"`. `PARQUET_PATH` points to a single file. | MEDIUM | Replace all hardcoded year-prefixed references with discovery-based loading. This touches data.py, engine.py (line 1791), and resolver.py. |
| Graceful single-year fallback | When only one year of data exists, all features must work identically to today. Early-career pitchers and new additions have no prior data. | LOW | Every multi-year feature must handle missing prior year as `None`, not error. Pattern: check availability, skip cross-year output if missing. |

### Differentiators (Competitive Advantage)

Features that make multi-year data genuinely insightful rather than just "more rows."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Year-over-year velocity trend | "Velo down 1.2 mph from 2025 full season" is higher-signal than "velo down 0.3 from this month." Season-scale velocity trends reveal physical changes (arm fatigue, mechanical adjustment, aging). | LOW | Subtract prior-season fastball velo baseline from current-season baseline. Small addition to `compute_fastball_summary`. Depends on season-aware baselines. |
| Cross-year pitch repertoire evolution | Detecting that a pitcher added a sweeper in 2026 that didn't exist in 2025, or dropped a curveball. Arsenal changes are the single highest-signal finding for scouts. | MEDIUM | Compare pitch_type sets between season baselines. Flag new/dropped types in context assembly. Depends on season-aware baselines. |
| Year-over-year physical observable deltas | Cross-year deltas for velocity, movement (pfx_x, pfx_z), and usage rates. These are directly comparable across years (unlike plus metrics). | MEDIUM | New engine function comparing prior-season and current-season baselines on physical columns only. |
| Postseason game_type support | Playoff data (F/D/L/W) is higher-leverage than regular season. Users analyzing October pitchers want to isolate postseason performance. | LOW | Already handled by game_type filter infrastructure -- just document the valid codes. No extra logic needed beyond what table-stakes game_type filtering provides. |
| Level filtering (MLB vs AAA) | The data includes minor league rows (`level = "AAA"` in both parquet and CSVs). For MLB pitcher reports, AAA appearances should be excluded by default. | LOW | Add `level` filter alongside `game_type` filter. Default to `"MLB"`. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem useful but create problems in this specific domain.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Blending spring training into regular-season baselines | "More data = better baselines" | Spring training is fundamentally non-competitive. Pitchers work on new pitches, face minor leaguers, sit at 85% effort, pitch 2-3 innings max. Including ST data actively degrades baseline quality. The current parquet has 134K ST pitches vs 31K regular season -- ST would overwhelm the signal by 4:1. | Filter to R by default. Let users opt in via `--game-type S` for explicit ST analysis. |
| Automatic cross-year P+/S+/L+ comparison | "Compare his 2025 P+ to his 2026 P+" | Pitching+ models are recalibrated annually. P+ 110 in 2025 does not equal P+ 110 in 2026 -- the league baseline shifts, the model is retrained with new data, and standard deviations change. FanGraphs has documented that "the probability that excellent stuff actually turns into excellent results is significantly lower" in recent years despite identical grades. Cross-year plus-metric deltas would be actively misleading. | Compare physical observables cross-year (velocity, movement, usage rates). Keep plus metrics within-season only. Flag this limitation in narrative prompts so the LLM does not fabricate cross-year P+ comparisons. |
| Loading unlimited historical years | "Load 2020-2026 for full career view" | Each parquet is ~24MB with 145K+ rows. Loading 7 years means ~1M rows in memory. More importantly, Statcast schema has evolved (new columns, spin axis methodology changes, Hawk-Eye transition in 2020). The value drops sharply past 2 years -- a pitcher's 2021 slider has little relevance to their 2026 slider. | Support current + prior year only (hardcap at 2). This covers the useful case (year-over-year trends) without the complexity. Make the cap a constant for future expansion if needed. |
| Mid-season team filtering | "Only show his stats with the Yankees, not the Mets" | Statcast pitch-level data has `home_team`/`away_team` but no clean `pitcher_team` field. You must infer pitcher team from game context. The Pitching+ CSVs have `team_code` but a traded pitcher has rows for both teams. The narrative pipeline does not surface team-specific context. | If team filtering matters later, add it at the Pitching+ CSV level where `team_code` is explicit. Not needed for this milestone. |
| Spring training scouting report mode | "Generate a full scouting report from spring training data" | ST data violates nearly every assumption in the pipeline: baselines are unreliable, opponent quality unknown, pitch counts non-representative, workload context meaningless. The narrative prompts assume competitive regular-season context. A "spring training scouting report" is a different product. | Allow `--game-type S` for data exploration via the Q&A analyst. Warn or refuse full narrative reports from ST-only data since the pipeline's assumptions break. |
| Automatic year detection based on current date | "Just load the right year based on today's date" | The data files are static parquets, not live feeds. The "current" year depends on when the data was downloaded, not today's date. A user in January 2027 analyzing 2026 data should not have the tool guess wrong. | Discover available years from the files on disk. Use the most recent year as "current." Simple and correct. |

## Feature Dependencies

```
[Game type filtering (statcast)]
    +--must-precede--> [ALL downstream computation]
    +--enables--------> [CLI --game-type flag]

[Game type filtering (CSVs)]
    +--must-precede--> [compute_season_baseline]
    +--must-precede--> [compute_pitch_type_baseline]
    +--must-precede--> [_compute_platoon_baseline]

[Multi-year parquet discovery]
    +--requires--> [Schema alignment via pl.concat(how="diagonal")]
    +--requires--> [Name resolver reads all parquets]
    +--enables---> [Year-over-year delta computation]

[Multi-year CSV agg discovery]
    +--requires--> [Hardcoded file references eliminated]
    +--requires--> [Season-aware baseline computation]
    +--enables---> [Year-over-year delta computation]
    +--enables---> [Cross-year repertoire evolution]

[Season-aware baselines]
    +--requires--> [Multi-year CSV discovery]
    +--enables---> [YoY velocity trend]
    +--enables---> [YoY physical deltas]
    +--enables---> [Cross-year repertoire evolution]

[Graceful single-year fallback]
    +--required-by--> [ALL cross-year features]
```

### Dependency Notes

- **Game type filtering must come first:** Every downstream computation (baselines, engine metrics, context assembly) depends on the data being correctly scoped. Filtering is the foundation -- it fixes a latent correctness bug and must precede any multi-year work.
- **Hardcoded references block multi-year:** The `_SEASON_CSVS`/`_APPEARANCE_CSVS` dicts and `PARQUET_PATH` constant must be replaced with discovery logic before multi-year CSVs or parquets can be loaded.
- **Season-aware baselines before cross-year deltas:** Cross-year comparisons require separate per-season baselines to diff. Without per-season separation, you get a blended baseline that helps nobody.
- **Single-year fallback is a pattern, not a feature:** Enforce it through the data model (Optional fields on cross-year types) rather than per-callsite None checks. This keeps the code clean as more cross-year features are added.
- **Game type filtering and multi-year discovery are independent.** They can be built in parallel or either order, though filtering is simpler and higher-impact, so it should ship first even if multi-year takes longer.

## MVP Definition

### Launch With (P1)

Minimum set to make game-type filtering and multi-year loading functional and correct.

- [ ] Game type filter on statcast parquet (default `R`, configurable) -- fixes the latent data contamination bug
- [ ] Game type filter on CSV aggs (defensive filtering before baselines)
- [ ] CLI `--game-type` flag with `R` default
- [ ] Multi-year parquet discovery via glob (`statcast_*.parquet`)
- [ ] Multi-year CSV discovery via glob pattern per grain
- [ ] Schema alignment for concatenated parquets (`pl.concat(how="diagonal")`)
- [ ] Eliminate all hardcoded `"2026-"` references and `PARQUET_PATH` singleton
- [ ] Season-aware baseline computation (group by season before averaging)
- [ ] Name resolver reads all discovered parquets
- [ ] Graceful single-year fallback (no errors when only one year exists)
- [ ] Propagate game_type and multi-year awareness through `load_pitcher_data`, CLI, and ask CLI

### Add After Validation (P2)

Features that need the P1 foundation but follow shortly after.

- [ ] Year-over-year velocity trend in `FastballSummary` -- simple delta, high narrative value
- [ ] Cross-year pitch repertoire evolution detection (added/dropped pitches)
- [ ] Year-over-year delta for physical observables (velo, movement, usage rates) in `PitcherContext`
- [ ] Narrative prompt updates to leverage cross-year context when available
- [ ] Level filtering (MLB vs AAA, default MLB) as additional data quality control

### Future Consideration (P3)

Defer until multi-year is proven useful and 2-year data is validated.

- [ ] Postseason-specific analysis mode (`--game-type F,D,L,W`)
- [ ] Qualitative trend strings for cross-year deltas ("velo trending down from 2025")
- [ ] Historical career arc support (3+ years) -- only if 2-year proves insufficient
- [ ] Spring training scouting report mode with appropriately modified assumptions

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Game type filter (statcast) | HIGH | LOW | P1 |
| Game type filter (CSVs) | HIGH | LOW | P1 |
| CLI --game-type flag | HIGH | LOW | P1 |
| Eliminate hardcoded year refs | HIGH | MEDIUM | P1 |
| Multi-year parquet discovery | HIGH | MEDIUM | P1 |
| Multi-year CSV discovery | HIGH | MEDIUM | P1 |
| Schema alignment (concat) | MEDIUM | LOW | P1 |
| Season-aware baselines | HIGH | MEDIUM | P1 |
| Name resolver multi-year | HIGH | LOW | P1 |
| Single-year fallback | HIGH | LOW | P1 |
| YoY velocity trend | HIGH | LOW | P2 |
| YoY repertoire evolution | HIGH | MEDIUM | P2 |
| YoY physical deltas | MEDIUM | MEDIUM | P2 |
| Narrative prompt updates | MEDIUM | LOW | P2 |
| Level filtering (MLB/AAA) | MEDIUM | LOW | P2 |
| Postseason mode | LOW | LOW | P3 |

## Edge Cases and Domain-Specific Concerns

### Cross-Year Data Combination Pitfalls

1. **Pitcher transfers between teams:** A pitcher traded mid-season has rows with different `team_code` values. The `pitcher` ID (MLB player ID) is stable across teams and years. No action needed for data loading -- the pitcher ID is the join key everywhere. Baseline `team_code` will reflect whichever team had more pitches (correct for weighted average) or last appearance (for display).

2. **Pitching+ model recalibration:** Plus metrics are recalibrated annually. FanGraphs documents that "the probability that excellent stuff actually turns into excellent results is significantly lower" in recent years despite identical P+ grades. Cross-year plus-metric deltas would be actively misleading. The system must only compare physical observables (velocity, movement, usage) across years and must explicitly instruct the narrative LLM not to compare P+/S+/L+ between seasons.

3. **Statcast schema evolution:** New columns may be added between years (e.g., new tracking metrics). `pl.concat(how="diagonal")` handles this by filling missing columns with null. Removed columns are rare but possible. Test with actual 2025 + 2026 files once 2025 data is acquired.

4. **Player name changes:** A pitcher's `player_name` could change between years (marriage, legal name change, diacritics normalization). The `pitcher` (numeric ID) is the stable key. Name resolution should prefer the most recent season's name for display but match against all name variants.

5. **Rule changes between 2025 and 2026:** The 2026 season introduced the Automated Ball-Strike Challenge System (ABS), allowing players to challenge ball-strike calls. This could subtly affect pitch location strategies (pitchers may target edges more aggressively knowing bad calls can be challenged). Not something the code needs to handle, but narrative prompts should note rule context when cross-year location metrics diverge.

6. **Spring training vs regular season date ranges:** In 2026, S/C games: Feb 20 - Mar 24; R games: Mar 25 onwards. No date overlap. Filtering on `game_type` column (not date ranges) is the correct, future-proof approach since overlap patterns may vary by year.

7. **Empty prior year:** Many pitchers will have no 2025 data (rookies, international signings, pitchers returning from multi-year injury). Every cross-year feature must handle this gracefully. Design pattern: `prior_season_baseline: SeasonBaseline | None` where `None` means "no prior data available," and all delta computations return `None` when either side is missing.

8. **Level column (MLB vs AAA):** Both parquet and CSVs contain AAA rows. A pitcher called up mid-season has mixed-level data. The default filter should be `level = "MLB"` alongside `game_type = "R"`. Consider making level a second filter parameter, defaulting to MLB.

9. **game_type "C" vs "S":** Both are spring training. C = Cactus League (Arizona), S = Spring Training (Grapefruit League, Florida). They should be treated identically. When user specifies `--game-type S`, include both S and C. The Statcast documentation lists the full set: E (Exhibition), S (Spring Training), R (Regular Season), F (Wild Card), D (Division Series), L (League Championship Series), W (World Series).

10. **Appearance CSVs vs season CSVs, different game_type coverage:** Season-grain CSVs (pitcher.csv, pitcher_type.csv, etc.) may have different game_type rows than appearance-grain CSVs. Currently all CSVs only have R, but this may not hold for 2025 data or future refreshes. Filter consistently everywhere.

## Existing Code Touchpoints

Specific locations in the codebase that need modification, mapped by module.

| File | Location | Change Needed |
|------|----------|---------------|
| `data.py` | `PARQUET_PATH` (line 36) | Replace single path with discovery function returning list of paths |
| `data.py` | `_SEASON_CSVS` dict (lines 41-46) | Replace hardcoded `"2026-"` filenames with glob-based discovery per grain |
| `data.py` | `_APPEARANCE_CSVS` dict (lines 47-52) | Same: replace hardcoded prefixes with discovery |
| `data.py` | `load_statcast()` (line 104) | Add `game_type` and `seasons` parameters; load from multiple parquets; filter |
| `data.py` | `load_csv()` (line 84) | Add optional `game_type` filter parameter |
| `data.py` | `load_agg_csvs()` (line 133) | Discover and load multi-year CSVs per grain, concat by season |
| `data.py` | `compute_season_baseline()` (line 181) | Group by season column before weight-averaging |
| `data.py` | `compute_pitch_type_baseline()` (line 207) | Group by season column before weight-averaging |
| `data.py` | `PitcherData` dataclass (line 69) | Add `seasons` field tracking which seasons are loaded |
| `data.py` | `load_pitcher_data()` (line 263) | Accept `game_type` param, propagate to all loaders |
| `engine.py` | Line 1791 | Remove hardcoded `"2026-pitcher_type.csv"`, use discovered CSVs from PitcherData |
| `engine.py` | `compute_league_baselines()` (line 200) | Read from discovered parquets via helper, not `PARQUET_PATH` |
| `engine.py` | `_compute_platoon_baseline()` (line 583) | Ensure game_type filtering is applied before weight-averaging |
| `resolver.py` | `_build_name_table()` (line 96) | Read all discovered parquets; deduplicate by pitcher ID, prefer most recent name |
| `resolver.py` | `PARQUET_PATH` import (line 19) | Replace with multi-parquet discovery |
| `cli.py` | `parse_args()` (line 25) | Add `--game-type` argument |
| `cli.py` | `main()` (line 78) | Pass game_type to `load_pitcher_data` |
| `ask_cli.py` | Entry point | Propagate game_type to data loading |
| `scout.py` | `score_appearances()` | Ensure game_type-filtered data flows through |

## Sources

- [Statcast Search CSV Documentation](https://baseballsavant.mlb.com/csv-docs) -- game_type field values: E (Exhibition), S (Spring Training), R (Regular Season), F (Wild Card), D (Division Series), L (League Championship Series), W (World Series). HIGH confidence.
- [FanGraphs: They Don't Make Pitch Models Like They Used To](https://blogs.fangraphs.com/they-dont-make-pitch-models-like-they-used-to/) -- Documents Pitching+ annual recalibration and why cross-year plus-metric comparisons are unreliable. HIGH confidence.
- [MLB Rule Changes for 2026](https://bleacherreport.com/articles/25409037-explaining-mlb-pace-play-and-more-rule-changes-2026-season) -- ABS challenge system introduced in 2026. MEDIUM confidence (details from article summary).
- Direct inspection of `statcast_2026.parquet` -- Confirmed game_type distribution: S=133,887, C=11,162, R=31,331. Date ranges: S/C Feb 20 - Mar 24, R Mar 25 - Apr 1. HIGH confidence.
- Direct inspection of `aggs/2026-pitcher.csv` -- Confirmed game_type column only contains `R` values. Confirmed `season`, `level`, `game_type` columns present in all CSVs. HIGH confidence.
- Codebase analysis of data.py, engine.py, resolver.py, context.py, cli.py, scout.py -- All hardcoded references and game_type handling verified by code inspection. HIGH confidence.

---
*Feature research for: Multi-Year Data Loading & Game Type Filtering*
*Researched: 2026-04-02*
