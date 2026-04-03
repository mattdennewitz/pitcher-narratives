---
phase: 20-season-delta-engine
plan: "01"
subsystem: engine
tags: [polars, dataclass, cross-season, yoy-delta, velocity, pitching-plus]

# Dependency graph
requires:
  - phase: 19-cross-season-baseline-exposure
    provides: "PitcherData with prior_season_baseline and prior_pitch_type_baseline fields"
provides:
  - "CrossSeasonSummary dataclass with YoY deltas for velocity, P+, S+, L+, and workload"
  - "compute_cross_season_summary(data) function returning CrossSeasonSummary or None"
  - "_per_season_velo helper for mean fastball velocity per season"
  - "_per_season_workload helper for appearances, IP, avg pitches per season"
affects: [21-arsenal-trend-engine, 22-context-assembly]

# Tech tracking
tech-stack:
  added: []
  patterns: [cross-season-delta-computation, per-season-aggregation]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - tests/test_engine.py

key-decisions:
  - "P+/S+/L+ columns accessed as 'P+', 'S+', 'L+' matching real pitchingplus CSV output"
  - "Velocity computed from statcast release_speed (not from CSV baselines which lack velocity)"
  - "IP computed as decimal from out-event counting in statcast per season"
  - "Plain @dataclass (not frozen) matching existing codebase convention"

patterns-established:
  - "Cross-season delta: compute_X(data) returns dataclass|None; None when prior_season_baseline is empty"
  - "_per_season_velo: group statcast by game_year for season-level fastball velocity"
  - "_per_season_workload: appearances + statcast outs for per-season workload stats"

requirements-completed: [SDLT-01, SDLT-02, SDLT-03]

# Metrics
duration: 5min
completed: 2026-04-03
---

# Phase 20 Plan 01: Season-Delta Engine Summary

**CrossSeasonSummary dataclass with YoY deltas for velocity, P+/S+/L+, and workload using existing qualitative delta string functions**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-03T11:14:19Z
- **Completed:** 2026-04-03T11:19:10Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- CrossSeasonSummary dataclass with 20 fields covering seasons, velocity, P+/S+/L+, and workload
- compute_cross_season_summary reuses _velo_delta_string and _pplus_delta_string for consistent qualitative language (SDLT-02)
- Returns None when prior-season data missing (SDLT-03) -- callers check `if summary is not None`
- 7 new tests covering all requirements, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Write cross-season summary tests** - `86e3398` (test) -- TDD RED: 7 failing tests
2. **Task 2: Implement CrossSeasonSummary and compute function** - `3484ce3` (feat) -- TDD GREEN: all 7 pass

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added CrossSeasonSummary dataclass, compute_cross_season_summary function, _per_season_velo and _per_season_workload helpers
- `tests/test_engine.py` - Added 7 cross-season tests with synthetic multi-year PitcherData helper

## Decisions Made
- Used `P+`, `S+`, `L+` column names in test synthetic data to match real pitchingplus CSV output (not `stuff_plus` etc. used by Phase 19 data tests)
- Computed IP as decimal from out-event counting rather than parsing baseball notation strings
- Used `_OUT_EVENTS` and `_DOUBLE_OUT_EVENTS` constants already in engine.py for IP computation
- Used `game_date.dt.year()` from appearances for season grouping in workload (canonical approach)

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None -- no external service configuration required.

## Known Stubs
None -- all fields in CrossSeasonSummary are fully computed from data, no placeholders or TODOs.

## Next Phase Readiness
- CrossSeasonSummary is ready for Phase 22 (Context Assembly) to consume via `compute_cross_season_summary(data)`
- Phase 21 (Arsenal Trend Engine) can proceed independently -- it covers per-pitch-type YoY deltas
- Both phases depend on Phase 19 (already complete), not on each other

---
*Phase: 20-season-delta-engine*
*Completed: 2026-04-03*
