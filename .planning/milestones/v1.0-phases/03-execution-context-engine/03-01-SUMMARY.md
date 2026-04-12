---
phase: 03-execution-context-engine
plan: 01
subsystem: engine
tags: [polars, dataclass, csw, zone-rate, chase-rate, xrv100, xwhiff, xswing, workload, rest-days, innings-pitched]

# Dependency graph
requires:
  - phase: 01-data-loading
    provides: PitcherData bundle with statcast, appearances, agg_csvs
  - phase: 02-fastball-arsenal-engine
    provides: engine.py patterns (_weighted_window_pplus, _get_window_game_dates, _is_cold_start, _MIN_PITCHES)
provides:
  - ExecutionMetrics dataclass with CSW%, zone rate, chase rate, xWhiff, xSwing, xRV100 percentile per pitch type
  - WorkloadContext dataclass with rest days, IP, pitch counts, consecutive-days tracking
  - AppearanceWorkload dataclass for per-appearance workload data
  - compute_execution_metrics() function
  - compute_workload_context() function
  - Helper functions: _compute_ip, _compute_rest_days, _max_consecutive_days, _weighted_window_xmetrics, _compute_xrv100_percentile
  - Constants: _CSW_DESCRIPTIONS, _SWING_DESCRIPTIONS, _ZONE_IN, _ZONE_OUT, _OUT_EVENTS, _DOUBLE_OUT_EVENTS
affects: [03-02-context-assembly, 04-llm-generation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Event-based IP computation using _OUT_EVENTS and _DOUBLE_OUT_EVENTS for baseball notation"
    - "League percentile ranking via full CSV reload (AGGS_DIR) with n_pitches weighting"
    - "Per-pitch-type execution metrics following existing dataclass + compute function pattern"

key-files:
  created: []
  modified:
    - engine.py
    - tests/test_engine.py

key-decisions:
  - "xRV100 percentile loads full unfiltered pitcher_type.csv for league distribution (not pre-filtered to this pitcher)"
  - "IP computed from event-based out counting (not outs_when_up) for accuracy with mid-inning entries"
  - "Reused _MIN_PITCHES=10 threshold for both small_sample flag and xRV100 percentile minimum"

patterns-established:
  - "Execution metrics: per-pitch-type CSW%, zone rate, chase rate from Statcast description/zone columns"
  - "Workload context: appearance-level rest days, IP, pitch counts from date arithmetic and event counting"
  - "xRV100 percentile: negative-is-better polarity (count pitchers with worse/higher xRV100)"

requirements-completed: [EXEC-01, EXEC-02, EXEC-03, EXEC-04, CTX-01, CTX-02, CTX-03]

# Metrics
duration: 4min
completed: 2026-03-26
---

# Phase 03 Plan 01: Execution Metrics & Workload Context Summary

**Per-pitch-type CSW%, zone/chase rates, xWhiff/xSwing, xRV100 league percentile, plus rest-day/IP/consecutive-day workload tracking via Statcast event counting**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T20:03:05Z
- **Completed:** 2026-03-26T20:07:11Z
- **Tasks:** 1 (TDD: RED-GREEN)
- **Files modified:** 2

## Accomplishments
- ExecutionMetrics with CSW% (3-description frozenset), zone rate (zones 1-9, null-safe), chase rate (O-Swing% on zones 11-14), xWhiff/xSwing from P+ CSVs, and xRV100 percentile ranking against all pitchers
- WorkloadContext with per-appearance IP in baseball notation (event-based out counting), pitch counts from Statcast, rest days from date arithmetic, and consecutive-days workload concern flag
- 15 new tests (50 total engine tests, 75 full suite) all passing against real data (pitcher 592155)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `e66c0d6` (test)
2. **Task 1 (GREEN): Implementation** - `9431572` (feat)

**Plan metadata:** pending (docs: complete plan)

_TDD task with RED and GREEN commits._

## Files Created/Modified
- `engine.py` - Extended with ExecutionMetrics, AppearanceWorkload, WorkloadContext dataclasses; compute_execution_metrics, compute_workload_context functions; _compute_ip, _compute_rest_days, _max_consecutive_days, _weighted_window_xmetrics, _compute_xrv100_percentile helpers; _CSW_DESCRIPTIONS, _SWING_DESCRIPTIONS, _ZONE_IN, _ZONE_OUT, _OUT_EVENTS, _DOUBLE_OUT_EVENTS constants
- `tests/test_engine.py` - Extended with 15 new tests: test_csw_per_type, test_csw_descriptions_exact, test_zone_rate, test_chase_rate, test_xwhiff_xswing, test_xrv100_percentile, test_xrv100_polarity, test_execution_metrics_small_sample, test_execution_metrics_cold_start, test_rest_days, test_rest_days_consecutive, test_ip_per_appearance, test_pitch_count_per_appearance, test_consecutive_days, test_consecutive_days_flag

## Decisions Made
- xRV100 percentile loads full unfiltered 2026-pitcher_type.csv from AGGS_DIR for the league distribution, since data.agg_csvs["pitcher_type"] is pre-filtered to this pitcher
- IP computed from event-based out counting (_OUT_EVENTS / _DOUBLE_OUT_EVENTS) rather than outs_when_up for accuracy with mid-inning reliever entries
- Reused existing _MIN_PITCHES=10 threshold consistently for small_sample flag and xRV100 percentile minimum pitch filter

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All engine computations complete (fastball, arsenal, execution, workload)
- Ready for Plan 02: PitcherContext Pydantic model assembly and to_prompt() rendering
- compute_execution_metrics and compute_workload_context exported and tested

## Self-Check: PASSED

- All files exist (engine.py, tests/test_engine.py, 03-01-SUMMARY.md)
- All commits found (e66c0d6, 9431572)
- All required classes and functions present in engine.py
- 75/75 tests passing

---
*Phase: 03-execution-context-engine*
*Completed: 2026-03-26*
