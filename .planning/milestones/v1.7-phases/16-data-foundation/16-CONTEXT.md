# Phase 16: Data Foundation - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase -- discuss skipped)

<domain>
## Phase Boundary

The data pipeline filters out spring training and exhibition games at load time and replaces all hardcoded year-specific paths with a parameterized `_YEARS` constant, so all downstream modules receive clean regular-season data without knowing about file naming or game type semantics.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key decisions already locked in STATE.md:
- Filter once in data.py at load time, all downstream consumers receive clean data
- Explicit `_YEARS` constant over filesystem auto-discovery (sufficient for 2 years)
- Per-season baselines (not cross-season averaged) to prevent double-counting artifacts
- Export `filter_game_type` as public API for consumer modules

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py` is the central data loading module with `load_statcast()`, `load_agg_csvs()`, `load_csv()`, `compute_season_baseline()`, `compute_pitch_type_baseline()`
- `_ID_COLS` frozenset already includes `"game_type"` and `"season"` as identity columns
- `_SEASON_CSVS` and `_APPEARANCE_CSVS` dicts map grain names to hardcoded `2026-` prefixed filenames

### Established Patterns
- Parquet path: `DATA_DIR / "statcast_2026.parquet"` (single hardcoded path)
- CSV loading via `load_csv(filename)` helper
- Baseline computation combines `game_type` rows using pitch-count weighting
- `__all__` exports define the public API

### Integration Points
- `engine.py:230` reads `2026-pitcher_type.csv` directly (bypass)
- `engine.py:1791` reads `2026-pitcher_type.csv` directly (bypass)
- `scout.py:114-117` reads four `2026-` CSVs directly (bypass)
- `resolver.py` likely reads parquet directly for name resolution
- All bypasses are Phase 18 scope -- Phase 16 focuses on data.py internals

</code_context>

<specifics>
## Specific Ideas

No specific requirements -- infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None -- infrastructure phase.

</deferred>
