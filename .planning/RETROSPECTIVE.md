# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.9 — Pipeline Consolidation

**Shipped:** 2026-04-10
**Phases:** 2 | **Plans:** 3

### What Was Built
- Deleted the old single-agent report.py (~850 lines) and its tests test_report.py (~635 lines)
- Relocated hallucination guard (HallucinationReport, check_hallucinated_metrics, regex patterns) from report.py to pipeline.py
- Rewrote cli.py and ask_cli.py to use pipeline.py exclusively — removed `--pipeline` flag and old-path branches from both CLIs
- Created standalone tests/test_hallucination_guard.py with 17 passing tests
- Cleaned stale report.py docstring references from anchor.py and config.py

### What Worked
- Clear separation of concerns across 3 plans: Wave 1 relocated shared code + rewired CLIs, Wave 2 deleted the orphaned files, Phase 24 verified + cleaned up stragglers
- Autonomous mode's "infrastructure phase detection" correctly skipped discuss-phase for both Phase 23 and Phase 24 — straight to planning saved significant time
- Phase 23 verification flagged stale docstrings as informational, Phase 24 cleaned them up — tight feedback loop between adjacent phases
- Worktree-based parallel execution kept merges clean (two STATE.md conflicts resolved trivially)

### What Was Inefficient
- ROADMAP.md success criteria mentioned non-existent flags (`--hallucination-check`, `--info` mode) — planner had to interpret intent rather than verify literal criteria. Future: verify success criteria match actual codebase before locking the roadmap.
- Merge conflicts in STATE.md required manual resolution because the worktree executor and main branch both wrote to it concurrently. Future: have worktree executors skip STATE.md writes, or update STATE.md only from the orchestrator.

### Patterns Established
- For pure removal/refactor phases, skip research and discuss — the roadmap description IS the spec
- Relocate shared utilities to their sole consumer rather than extracting to a new module when the caller count is 1
- Pre-existing test failures should be documented in VERIFICATION.md and carried forward as known debt rather than treated as phase regressions

### Key Lessons
1. When an entire module is scheduled for deletion, identify its shared dependencies FIRST (not LAST) — the hallucination guard move had to happen before the CLI rewrite, which had to happen before the file delete. Correct ordering in Wave 1 → Wave 2 kept the plan coherent.
2. "Auto-generated minimal context" for infrastructure phases works — the executor doesn't need grey-area answers for file deletion tasks.
3. Roadmap success criteria should reference actual CLI flags/features, not hypothetical ones. Verify against the current codebase at roadmap-creation time.

### Cost Observations
- Model mix: opus for planning/execution, sonnet for verification
- Sessions: 1 autonomous run
- Notable: Wave 1 (23-01) took 4 min, Wave 2 (23-02) took 3 min, Wave 3 (24-01) took 3 min — short-cycle infrastructure work is the sweet spot for worktree-parallel execution

---

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
| v1.9 | 2 | 3 | Pipeline consolidation (removal only) |

### Top Lessons (Verified Across Milestones)

1. Pre-computing derived metrics in Python (not LLM) consistently produces better narrative quality — validated across v1.0, v1.5, v1.8
2. Centralizing data access through a single module prevents filtering bugs — validated in v1.7 (game type) and v1.8 (cross-season)
3. Layered milestones compound: v1.7's multi-year data made v1.8's cross-season features straightforward
