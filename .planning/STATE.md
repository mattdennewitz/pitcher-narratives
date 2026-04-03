---
gsd_state_version: 1.0
milestone: v1.7
milestone_name: Multi-Year Data & Game Type Filtering
status: in_progress
stopped_at: Completed 17-01-PLAN.md
last_updated: "2026-04-03T02:57:04Z"
last_activity: 2026-04-03
progress:
  total_phases: 8
  completed_phases: 8
  total_plans: 14
  completed_plans: 14
  percent: 89
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** Reports must read like a scout wrote them -- surfacing changes, adaptations, and execution trends rather than reciting numbers.
**Current focus:** Phase 18 -- Consumer Updates (next phase)

## Current Position

Phase: 17 of 18 (Multi-Year Loading) -- COMPLETE
Plan: 1/1 complete
Status: Phase 17 complete, ready for Phase 18
Last activity: 2026-04-03 -- Phase 17 plan 01 complete

Progress: [=================░] 94% (17/18 phases)

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

- Allowlist (is_in) over exclusion list for game type filtering -- unknown game types default to excluded
- Grain tuples + f-string generation over hardcoded CSV filename dicts -- _YEARS drives all paths
- Pitcher 676571 (Poulin, PJ) as swingman test fixture -- 4 R-game appearances with SP+RP roles
- Explicit _YEARS=[2025,2026] over glob auto-discovery -- predictable, no surprises from unexpected files
- Filter per-year-file before concat to minimize memory usage
- Per-season baselines via group_by([pitcher, season]) -- prevents cross-season averaging artifacts

### Pending Todos

None.

### Blockers/Concerns

- pitchingplus model internals at ~/src/pitchingplus/packages/plus -- external dependency, changes there affect this project's data pipeline
- test_engine.py::test_fastball_velocity_delta needs fixture update for filtered data (Phase 18 scope)
- RV_df.csv missing from aggs/ directory -- pre-existing, affects test_analyst.py and test_ask_cli.py
- PitcherData.season_baseline now returns multiple rows per season -- Phase 18 consumers that assume single-row need updating

## Performance Metrics

| Phase-Plan | Duration | Tasks | Files |
|-----------|----------|-------|-------|
| 16-01 | 5min | 2 | 2 |
| 17-01 | 7min | 2 | 2 |

## Session Continuity

Last session: 2026-04-03
Stopped at: Completed 17-01-PLAN.md
Resume file: None
