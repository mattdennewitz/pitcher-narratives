---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Model-Explainable Narratives
status: executing
stopped_at: Completed 11-01-PLAN.md
last_updated: "2026-03-31T20:47:54.714Z"
last_activity: 2026-03-31 -- Phase 12 execution started
progress:
  total_phases: 14
  completed_phases: 8
  total_plans: 15
  completed_plans: 13
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-31)

**Core value:** Reports must read like a scout wrote them -- surfacing changes, adaptations, and execution trends rather than reciting numbers.
**Current focus:** Phase 12 — Component Attribution

## Current Position

<<<<<<< Updated upstream
Phase: 12 (Component Attribution) — EXECUTING
Plan: 1 of 2
Status: Executing Phase 12
Last activity: 2026-03-31 -- Phase 12 execution started
=======
Phase: 11 (Intermediate Probability Pipeline) — EXECUTING
Plan: 1 of 1
Status: Executing Phase 11
Last activity: 2026-03-31 -- Phase 11 execution started
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

### Pending Todos

None yet.

### Blockers/Concerns

- pitchingplus model internals at ~/src/pitchingplus/packages/plus — external dependency, changes there affect this project's data pipeline

## Performance Metrics

| Phase-Plan | Duration | Tasks | Files |
|------------|----------|-------|-------|
| 11-01      | 5min     | 2     | 3     |

## Session Continuity

Last session: 2026-03-31T19:52:28Z
Stopped at: Completed 11-01-PLAN.md
Resume file: None
