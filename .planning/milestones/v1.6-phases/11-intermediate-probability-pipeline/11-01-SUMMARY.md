---
phase: 11-intermediate-probability-pipeline
plan: 01
subsystem: engine
tags: [polars, dataclass, intermediate-probabilities, pitchingplus, P-variant, S-variant]

# Dependency graph
requires:
  - phase: 04-report-generation
    provides: PitcherContext model and assemble_pitcher_context pattern
  - phase: 03-execution-context-engine
    provides: ExecutionMetrics dataclass and _weighted_window_metrics helper
provides:
  - IntermediateProbabilities dataclass with P/S variants for 8 metrics at window and season grains
  - compute_intermediate_probabilities() function extracting from pitchingplus agg CSVs
  - PitcherContext.intermediates field wired into assembly pipeline
affects: [13-tool-interface-updates, 14-analyst-prompt-rewrite]

# Tech tracking
tech-stack:
  added: []
  patterns: [_INTERMEDIATE_P_COLS/_INTERMEDIATE_S_COLS constant tuples, closure-with-default-arg for baseline lookup]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - src/pitcher_narratives/context.py
    - tests/test_engine.py

key-decisions:
  - "BBE_prob_P/S included in column constants despite missing from CSVs -- future-proofs against agg regeneration"
  - "Default parameter pattern (_row=bl_row) for inner closure to satisfy ruff B023 loop variable binding"

patterns-established:
  - "_INTERMEDIATE_P_COLS/_INTERMEDIATE_S_COLS tuple pattern mirrors existing _PPLUS_METRICS/_XMETRICS convention"
  - "Season baseline lookup via inner closure with default parameter binding"

requirements-completed: [DATA-01, DATA-02]

# Metrics
duration: 5min
completed: 2026-03-31
---

# Phase 11 Plan 01: Intermediate Probability Pipeline Summary

**IntermediateProbabilities dataclass with P/S variants for xSwing, xWhiff, xGOr, xPUr, xHR100, xSwSt, xRV100 at window and season grains, wired into PitcherContext**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T19:46:59Z
- **Completed:** 2026-03-31T19:52:28Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- IntermediateProbabilities dataclass with 35 fields: 16 window metrics (8 P + 8 S), 16 season metrics (8 P + 8 S), plus pitch_type, pitch_name, n_pitches, small_sample, cold_start
- compute_intermediate_probabilities() function reusing _weighted_window_metrics and pitch_type_baseline patterns from existing engine code
- PitcherContext.intermediates field wired via assemble_pitcher_context, capped at 4 pitch types
- BBE_prob_P/S columns gracefully return None (absent from current agg CSVs) without exception
- 6 new tests covering structure, both grains, P/S pairing, location impact computation, missing column handling

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for IntermediateProbabilities** - `5da364b` (test)
2. **Task 1 (GREEN): IntermediateProbabilities dataclass and compute function** - `28a570b` (feat)
3. **Task 2: Wire intermediate probabilities into PitcherContext** - `9457c88` (feat)

_Note: TDD task had RED and GREEN commits._

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added _INTERMEDIATE_P_COLS, _INTERMEDIATE_S_COLS, _INTERMEDIATE_COLS constants, IntermediateProbabilities dataclass, compute_intermediate_probabilities function, updated __all__
- `src/pitcher_narratives/context.py` - Added intermediates field to PitcherContext, wired compute call in assemble_pitcher_context
- `tests/test_engine.py` - 6 new test functions for intermediate probabilities

## Decisions Made
- BBE_prob_P/S included in column constant tuples despite missing from current CSVs -- future-proofs against pitchingplus agg regeneration without code changes
- Used default parameter binding (`_row=bl_row`) for inner closure to satisfy ruff B023 loop variable capture lint rule

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff B023 closure variable binding**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** `_bl` inner closure captured loop variable `bl_row` by reference, triggering ruff B023
- **Fix:** Changed to default parameter pattern `def _bl(col: str, _row: pl.DataFrame = bl_row)`
- **Files modified:** src/pitcher_narratives/engine.py
- **Verification:** `uv run ruff check src/pitcher_narratives/engine.py` exits 0
- **Committed in:** 28a570b (part of GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor lint fix, no scope creep.

## Issues Encountered
- Worktree missing data files (statcast_2026.parquet, aggs/) -- resolved by symlinking from main repo. Pre-existing infrastructure issue, not a code problem.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data flows are wired to real computation. Intermediate probabilities are populated from actual CSV data.

## Next Phase Readiness
- IntermediateProbabilities is accessible via PitcherContext.intermediates for Phase 13 tool interface updates
- Location impact (P minus S) is computable from any pair of P/S fields
- No rendering/prompt changes were made (Phase 13 scope)
- Phase 12 (Component Attribution) can proceed independently

## Self-Check: PASSED

- All 3 files verified present
- All 3 commit hashes verified in git log
- 245 tests passing (full suite)
- Lint clean on modified files

---
*Phase: 11-intermediate-probability-pipeline*
*Completed: 2026-03-31*
