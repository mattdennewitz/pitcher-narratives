---
gsd_state_version: 1.0
milestone: v1.7
milestone_name: Multi-Year Data & Game Type Filtering
status: planning
stopped_at: null
last_updated: "2026-04-02T00:00:00.000Z"
last_activity: 2026-04-02
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-02)

**Core value:** Reports must read like a scout wrote them -- surfacing changes, adaptations, and execution trends rather than reciting numbers.
**Current focus:** Defining requirements for v1.7

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-04-02 — Milestone v1.7 started

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.4]: Tool-calling agent pattern (AGENT-02/03 require tools, not pre-assembled context)
- [v1.4]: rapidfuzz for name resolution (deterministic, fast, no LLM)
- [v1.4]: Three new modules (resolver.py, analyst.py, ask_cli.py), zero modifications to existing code
- [v1.5]: Component attribution (medium effort) over SHAP (high effort) — answers "why" using already-computed data without new ML infrastructure
- [v1.5]: P vs S variant comparison to isolate location impact — scout-readable diagnostic

### Pending Todos

None yet.

### Blockers/Concerns

- pitchingplus model internals at ~/src/pitchingplus/packages/plus — external dependency, changes there affect this project's data pipeline
- data.py has hardcoded 2026-prefixed filenames and single parquet path — restructuring is the core of v1.6

## Performance Metrics

(Reset for new milestone)

## Session Continuity

Last session: 2026-04-02
Stopped at: Milestone v1.7 initialization
Resume file: None
