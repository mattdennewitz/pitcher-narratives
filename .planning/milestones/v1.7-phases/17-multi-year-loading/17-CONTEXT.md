# Phase 17: Multi-Year Loading - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase -- discuss skipped)

<domain>
## Phase Boundary

The data pipeline loads and concatenates parquet and CSV files across all configured years, with per-season baselines that prevent cross-season averaging artifacts.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key decisions already locked in STATE.md:
- Explicit `_YEARS` constant (already `[2026]` from Phase 16) expanded to `[2025, 2026]`
- Per-season baselines (not cross-season averaged) to prevent double-counting artifacts -- `compute_season_baseline()` must group by `["pitcher", "season"]`
- When a year's files are missing, skip that year gracefully without crashing
- `PARQUET_PATH` stays singular for backward compatibility; `load_statcast()` internally iterates `_YEARS`

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py` already has `_YEARS: list[int] = [2026]`, `_SEASON_GRAINS`, `_APPEARANCE_GRAINS` from Phase 16
- `filter_game_type()` is already applied at load time in `load_statcast()` and `load_csv()`
- `_ID_COLS` already includes `"season"` as an identity column

### Established Patterns
- Parquet path derived from `_YEARS[-1]`: `DATA_DIR / f"statcast_{_YEARS[-1]}.parquet"`
- CSV filenames derived from grain and year: `f"{_YEARS[-1]}-{grain}.csv"`
- `compute_season_baseline()` currently groups by `"pitcher"` only -- needs `["pitcher", "season"]`

### Integration Points
- `PARQUET_PATH` is imported by `resolver.py` and `engine.py` (Phase 18 scope to update)
- `load_statcast()` currently reads single parquet; needs to iterate years and concatenate
- `load_agg_csvs()` currently reads single year's CSVs; needs to iterate years and concatenate

</code_context>

<specifics>
## Specific Ideas

No specific requirements -- infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None -- infrastructure phase.

</deferred>
