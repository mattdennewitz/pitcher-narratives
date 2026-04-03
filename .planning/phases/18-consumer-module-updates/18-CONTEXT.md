# Phase 18: Consumer Module Updates - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase -- discuss skipped)

<domain>
## Phase Boundary

All modules that bypass data.py to read CSV or parquet files directly are refactored to use data.py's loading functions, ensuring game type filtering and multi-year support are applied consistently everywhere.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure refactoring phase. Key constraints:
- `engine.py` must not contain any direct `read_csv` or `read_parquet` calls after this phase
- `resolver.py` must build its pitcher name table from all available parquet files (all years in `_YEARS`)
- `scout.py` must not contain any direct CSV or parquet reads
- All data access must route through `data.py` functions
- `grep "read_csv\|read_parquet" src/pitcher_narratives/ | grep -v data.py` must return zero results

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py` now has multi-year `load_statcast()`, `load_agg_csvs()`, `load_csv()`, `filter_game_type()`
- `_YEARS = [2025, 2026]` drives all path generation
- Per-season baselines via `compute_season_baseline()` and `compute_pitch_type_baseline()`
- `PARQUET_PATH` still exported as singular path (backward-compatible)

### Known Bypass Points (from Phase 16 research)
- `engine.py:230` reads `2026-pitcher_type.csv` directly
- `engine.py:1791` reads `2026-pitcher_type.csv` directly
- `scout.py:114-117` reads four `2026-` CSVs directly via `load_csv()` with wrong arity
- `resolver.py` imports `PARQUET_PATH` and reads parquet directly for name resolution

### Integration Points
- All consumer modules must use `data.py` functions
- May need new data.py helper functions for specific consumer needs (e.g., name table building)

</code_context>

<specifics>
## Specific Ideas

No specific requirements -- refactoring phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None -- refactoring phase.

</deferred>
