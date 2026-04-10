---
phase: 20-season-delta-engine
plan: 01
subsystem: engine
tags: [polars, dataclass, deltas, cross-season, TDD]

# Dependency graph
requires:
  - phase: 19-cross-season-baseline-exposure
    provides: "PitcherData.prior_season_baseline field (N-1 season baseline DataFrame)"
provides:
  - "Working compute_cross_season_summary() returning CrossSeasonSummary with YoY deltas"
  - "_per_season_velo() helper for mean velocity per season from statcast data"
  - "CrossSeasonSummary and compute_cross_season_summary exported in engine.__all__"
affects: [22-context-assembly-prompt-rendering]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Per-season velocity from statcast via game_date.dt.year() groupby", "Reuse existing delta-string functions for YoY consistency"]

key-files:
  created: []
  modified:
    - "src/pitcher_narratives/engine.py"
    - "tests/test_engine.py"

key-decisions:
  - "Reuse _velo_delta_string and _pplus_delta_string for YoY deltas -- ensures qualitative language consistency with within-season deltas"
  - "_per_season_velo derives season from game_date year, not from a separate column -- consistent with temporal context pattern"

patterns-established:
  - "Cross-season delta computation: extract metrics from season_baseline and prior_season_baseline, compute diff, pass through existing delta-string functions"

requirements-completed: [SDLT-01, SDLT-02, SDLT-03]

# Metrics
duration: 5min
completed: 2026-04-08
---

# Phase 20 Plan 01: Season-Delta Engine Summary

**Working compute_cross_season_summary() with _per_season_velo helper producing YoY deltas for velocity, P+, S+, L+ using existing qualitative delta-string functions**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-08T21:35:23Z
- **Completed:** 2026-04-08T21:40:54Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Fixed broken compute_cross_season_summary() scaffolding by implementing the missing _per_season_velo() helper
- Added CrossSeasonSummary and compute_cross_season_summary to engine.__all__ for public export
- All 88 engine tests pass (4 new cross-season + 84 existing, zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for CrossSeasonSummary (RED)** - `9a49637` (test)
2. **Task 2: Implement _per_season_velo and add __all__ exports (GREEN)** - `fdb8968` (feat)

_TDD: Task 1 wrote failing tests (RED), Task 2 made them pass (GREEN)._

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added _per_season_velo() helper, added CrossSeasonSummary and compute_cross_season_summary to __all__
- `tests/test_engine.py` - Added 4 new tests covering SDLT-01 (multi-season returns populated CrossSeasonSummary), SDLT-02 (delta strings use Steady/Up/Down language), SDLT-03 (single-season returns None), and __all__ exports

## Decisions Made
- Reused existing _velo_delta_string and _pplus_delta_string functions for YoY deltas -- ensures same qualitative language (Steady/Up/Down/sharply) as within-season deltas
- _per_season_velo derives season from game_date.dt.year() -- consistent with the pattern used in compute_temporal_context

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Worktree needed Phase 19 code changes cherry-picked before Phase 20 tests could run (prior_season_baseline field on PitcherData)
- Data files not present in worktree; tests run with PITCHER_NARRATIVES_DATA_DIR pointing to main repo

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- compute_cross_season_summary() is fully functional and exported, ready for Phase 22 (Context Assembly) to wire into PitcherContext
- CrossSeasonSummary dataclass provides velocity, P+, S+, L+ deltas with qualitative strings
- No blockers for downstream phases

## Self-Check: PASSED

- FOUND: src/pitcher_narratives/engine.py
- FOUND: tests/test_engine.py
- FOUND: .planning/phases/20-season-delta-engine/20-01-SUMMARY.md
- FOUND: 9a49637 (Task 1 commit)
- FOUND: fdb8968 (Task 2 commit)

---
*Phase: 20-season-delta-engine*
*Completed: 2026-04-08*
