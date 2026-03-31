---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Model-Explainable Narratives
status: completed
stopped_at: Completed 13-01-PLAN.md
last_updated: "2026-03-31T21:59:37.011Z"
last_activity: 2026-03-31
progress:
  total_phases: 14
  completed_phases: 10
  total_plans: 16
  completed_plans: 16
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-31)

**Core value:** Reports must read like a scout wrote them -- surfacing changes, adaptations, and execution trends rather than reciting numbers.
**Current focus:** Phase 13 — Tool Interface Updates

## Current Position

<<<<<<< Updated upstream
Phase: 14
Plan: Not started
Status: Phase 13 plan 01 complete
Last activity: 2026-03-31
=======
Phase: 13 (Tool Interface Updates) — EXECUTING
Plan: 1 of 1
Status: Executing Phase 13
Last activity: 2026-03-31 -- Phase 13 execution started
>>>>>>> Stashed changes

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.4]: Tool-calling agent pattern (AGENT-02/03 require tools, not pre-assembled context)
- [v1.4]: rapidfuzz for name resolution (deterministic, fast, no LLM)
- [v1.4]: Three new modules (resolver.py, analyst.py, ask_cli.py), zero modifications to existing code
- [v1.5]: Component attribution (medium effort) over SHAP (high effort) — answers "why" using already-computed data without new ML infrastructure
- [v1.5]: P vs S variant comparison to isolate location impact — scout-readable diagnostic

- [Phase 11]: BBE_prob_P/S included in constants despite missing from CSVs -- future-proofs against agg regeneration
- [Phase 11]: Default parameter binding for inner closure to satisfy ruff B023
- [Phase 12]: Raw xRV100 (pre-mean-subtraction) for component attribution -- correct decomposition since league-average offset is constant
- [Phase 13]: 4 diagnostic metrics (xSwing, xWhiff, xSwSt, xRV100) in summary intermediates; S-variants and deltas only to avoid Execution section duplication

### Pending Todos

None yet.

### Blockers/Concerns

- pitchingplus model internals at ~/src/pitchingplus/packages/plus — external dependency, changes there affect this project's data pipeline

## Performance Metrics

| Phase-Plan | Duration | Tasks | Files |
|------------|----------|-------|-------|
| 11-01      | 5min     | 2     | 3     |
| 12-01      | 2min     | 1     | 1     |
| Phase 12 P02 | 4min | 2 tasks | 3 files |
| 13-01      | 4min     | 2     | 4     |

## Session Continuity

Last session: 2026-03-31T21:54:18Z
Stopped at: Completed 13-01-PLAN.md
Resume file: None
