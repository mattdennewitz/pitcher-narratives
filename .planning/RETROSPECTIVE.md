# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.8 — Cross-Season Trend Analysis

**Shipped:** 2026-04-08
**Phases:** 4 | **Plans:** 5

### What Was Built
- Prior-season baseline exposure on PitcherData via N-1 filtering
- CrossSeasonSummary engine producing YoY velocity/P+/S+/L+ deltas with qualitative language
- ArsenalTrends engine detecting added/dropped/continued pitches with per-pitch-type YoY deltas
- PitcherContext YoY rendering with single-season omission
- Specialist pipeline cross-season data injection and prompt builder fixes

### What Worked
- Leveraged existing qualitative delta-string functions (from v1.0 engine) for YoY deltas — zero duplication
- Per-season baseline grouping from v1.7 made N-1 filtering straightforward
- 4 phases kept scope tight: data exposure → summary engine → arsenal engine → assembly
- Code review catch on ArsenalTrends attribute names (added/dropped/continued vs old pfx_x_delta/pfx_z_delta) prevented runtime breakage

### What Was Inefficient
- Phase 22 needed a second plan (22-02) to fix specialist prompt builders — could have been caught during 22-01 if specialist integration was tested alongside context assembly
- Minor: _render_yoy_section produces empty YoY header when all deltas are "Steady" and no pitches added/dropped — deferred rather than fixed

### Patterns Established
- Cross-season features build on multi-year data layer (v1.7) — the layered milestone approach pays off
- Specialist prompt builders need integration testing when upstream data models change

### Key Lessons
1. When adding new data model fields, trace all consumers immediately — specialist prompt builders were missed in initial context assembly plan
2. Qualitative delta-string reuse across single-game and cross-season contexts validates the decision to centralize computation language in engine.py

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 4 | 8 | Foundation: data pipeline, engines, context, report |
| v1.3 | 3 | 4 | Reflection loop with typed anchor models |
| v1.4 | 3 | 3 | Q&A agent with fuzzy name resolution |
| v1.5 | 4 | 5 | Model-explainable narratives with component attribution |
| v1.6 | 1 | 1 | Multi-agent specialist pipeline (prototype) |
| v1.7 | 3 | 4 | Multi-year data centralization |
| v1.8 | 4 | 5 | Cross-season trend analysis |

### Top Lessons (Verified Across Milestones)

1. Pre-computing derived metrics in Python (not LLM) consistently produces better narrative quality — validated across v1.0, v1.5, v1.8
2. Centralizing data access through a single module prevents filtering bugs — validated in v1.7 (game type) and v1.8 (cross-season)
3. Layered milestones compound: v1.7's multi-year data made v1.8's cross-season features straightforward
