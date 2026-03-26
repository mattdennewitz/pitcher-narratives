---
phase: 01-data-pipeline-classification
plan: 01
subsystem: data
tags: [polars, parquet, csv, dataframe, classification, baseline, pipeline]

# Dependency graph
requires: []
provides:
  - "data.py module with load_statcast, load_agg_csvs, classify_appearances, compute_season_baseline, compute_pitch_type_baseline, filter_to_window, load_pitcher_data"
  - "PitcherData dataclass bundling all loaded data for a pitcher"
  - "pytest infrastructure with 15 passing tests"
affects: [01-02, 02-delta-computation, 03-context-assembly, 04-report-generation]

# Tech tracking
tech-stack:
  added: [pytest]
  patterns: [eager-parquet-loading, csv-date-parsing, n_pitches-weighted-averaging, first-inning-role-classification, max-date-window-filtering]

key-files:
  created: [data.py, tests/test_data.py, tests/__init__.py, .gitignore]
  modified: [pyproject.toml, uv.lock]

key-decisions:
  - "Used dataclass (not NamedTuple) for PitcherData bundle -- mutable, cleaner attribute access"
  - "frozenset for _ID_COLS to share between season and pitch_type baseline functions"
  - "Window filtering uses max date in dataset, not date.today() -- data is static"

patterns-established:
  - "Eager parquet load with immediate filter: pl.read_parquet() then .filter()"
  - "CSV date parsing at load time: pl.col('game_date').str.to_date('%Y-%m-%d')"
  - "Weighted averaging via (col * weight).sum() / weight.sum() in group_by().agg()"
  - "Role classification: first_inning == 1 -> SP, otherwise RP"
  - "Private helper prefix with underscore: _load_csv_with_dates"
  - "Google-style docstrings with Args/Returns/Raises sections"

requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04, ROLE-01, ROLE-03]

# Metrics
duration: 3min
completed: 2026-03-26
---

# Phase 01 Plan 01: Data Pipeline & Classification Summary

**Polars data pipeline loading Statcast parquet + 8 Pitching+ CSVs with SP/RP classification, n_pitches-weighted baselines, and configurable lookback window filtering**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-26T18:46:50Z
- **Completed:** 2026-03-26T18:50:09Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Built complete data.py module with 7 public functions and PitcherData dataclass
- All 15 unit tests passing against real data (pitcher 592155: 12 appearances, 1 SP + 11 RP)
- Season baselines correctly use n_pitches-weighted averaging across game_type rows
- CSV game_date columns parsed to polars Date type at load time
- Window filtering uses max date in dataset (not date.today()) for static data correctness

## Task Commits

Each task was committed atomically:

1. **Task 1: Project setup -- pytest, .gitignore, test scaffolds** - `0a702e2` (test)
2. **Task 2: Build data.py -- all data loading, classification, baselines, and filtering** - `428475b` (feat)

## Files Created/Modified
- `data.py` - All data loading, classification, baseline, and filtering functions (273 lines)
- `tests/test_data.py` - 15 unit tests covering DATA-01 through DATA-04, ROLE-01, ROLE-03
- `tests/__init__.py` - Empty init for test package
- `pyproject.toml` - Added pytest dev dependency and [tool.pytest.ini_options] config
- `uv.lock` - Updated lockfile with pytest + deps
- `.gitignore` - Standard Python ignore patterns

## Decisions Made
- Used `@dataclass` for PitcherData bundle instead of NamedTuple -- mutable, cleaner attribute access, better IDE support
- Shared `_ID_COLS` frozenset between `compute_season_baseline` and `compute_pitch_type_baseline` to avoid duplication
- Window filtering uses `df["game_date"].max()` as reference date, not `date.today()`, because the dataset is static (ends 2026-03-25)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- data.py provides the complete foundation for Phase 01 Plan 02 (CLI entry point)
- All loader functions are tested and verified with real data
- PitcherData dataclass is ready for downstream consumption in Phase 02 (delta computation)
- Polars 1.39.3 confirmed working with Python 3.14.3 (resolves STATE.md blocker concern)

## Self-Check: PASSED

- All 4 created files exist on disk
- Both task commits (0a702e2, 428475b) found in git log
- SUMMARY.md created at correct path

---
*Phase: 01-data-pipeline-classification*
*Completed: 2026-03-26*
