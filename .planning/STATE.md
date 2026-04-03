---
gsd_state_version: 1.0
milestone: v1.7
milestone_name: Multi-Year Data & Game Type Filtering
status: roadmap_complete
stopped_at: Roadmap created with 3 phases (16-18)
last_updated: "2026-04-03T00:00:00.000Z"
last_activity: 2026-04-03
progress:
  total_phases: 18
  completed_phases: 15
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** Reports must read like a scout wrote them -- surfacing changes, adaptations, and execution trends rather than reciting numbers.
**Current focus:** Phase 16 -- Data Foundation (ready to plan)

## Current Position

Phase: 16 of 18 (Data Foundation)
Plan: Not started
Status: Ready to plan
Last activity: 2026-04-03 -- Roadmap created for v1.7

Progress: [===============░░░] 83% (15/18 phases)

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.7]: Filter once in data.py at load time, all downstream consumers receive clean data
- [v1.7]: Explicit _YEARS constant over filesystem auto-discovery (sufficient for 2 years)
- [v1.7]: Per-season baselines (not cross-season averaged) to prevent double-counting artifacts
- [v1.7]: Export filter_game_type as public API for consumer modules

### Pending Todos

None.

### Blockers/Concerns

- pitchingplus model internals at ~/src/pitchingplus/packages/plus -- external dependency, changes there affect this project's data pipeline
- 75.9% of 2026 statcast rows are spring training -- filtering is correctness-critical, not optional
- Test assertions will break when filtering lands; new expected values must be computed against filtered data

## Session Continuity

Last session: 2026-04-03
Stopped at: Roadmap created for v1.7 (3 phases 16-18, 11 requirements)
Resume file: None
