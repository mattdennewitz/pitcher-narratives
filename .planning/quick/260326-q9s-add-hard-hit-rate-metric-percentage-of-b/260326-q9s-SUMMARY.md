---
phase: quick
plan: 260326-q9s
subsystem: engine
tags: [polars, statcast, batted-ball, hard-hit-rate]

requires:
  - phase: 02-computation-engine
    provides: engine.py compute functions, delta string helpers, PitcherData
  - phase: 03-context-assembly
    provides: PitcherContext model, to_prompt() rendering, assemble_pitcher_context
provides:
  - HardHitRate dataclass and compute_hard_hit_rate function in engine.py
  - Contact Quality section in prompt rendering
  - HardHit% in hallucination guard known metrics
affects: [report-generation, prompt-rendering]

tech-stack:
  added: []
  patterns:
    - "Batted ball filtering: description == 'hit_into_play' AND launch_speed.is_not_null()"

key-files:
  created: []
  modified:
    - engine.py
    - context.py
    - report.py
    - tests/test_engine.py
    - tests/test_context.py
    - .gitignore

key-decisions:
  - "Used _usage_delta_string for hard-hit rate delta (percentage-point thresholds match semantics)"
  - "Placed Contact Quality section after Execution table in prompt rendering order"
  - "Executive summary includes hard-hit rate only when shift >= 5pp and not cold start"

patterns-established:
  - "Batted ball quality metrics follow same window/season/delta/flags pattern as execution metrics"

requirements-completed: []

duration: 7min
completed: 2026-03-26
---

# Quick Task 260326-q9s: Add Hard-Hit Rate Metric Summary

**Hard-hit rate metric (% BIP with launch_speed >= 95 mph) computed in engine.py, rendered as Contact Quality section in prompt, with 9 new tests**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-26T22:58:43Z
- **Completed:** 2026-03-26T23:05:15Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- HardHitRate dataclass with window/season rates, delta string, counts, and small_sample/cold_start flags
- compute_hard_hit_rate function filters batted balls from Statcast, computes exit velo >= 95 mph threshold
- Contact Quality section rendered in to_prompt() with BIP counts and season comparison
- Executive summary includes hard-hit rate when notable shift (>= 5pp) detected
- HardHit% added to hallucination guard in report.py
- All 135 tests pass (7 new engine tests + 2 new context tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add HardHitRate dataclass and compute_hard_hit_rate to engine.py** - `c431f92` (feat)
2. **Task 2: Wire hard-hit rate into PitcherContext and prompt rendering** - `3a46078` (feat)

## Files Created/Modified
- `engine.py` - Added HardHitRate dataclass and compute_hard_hit_rate function
- `context.py` - Added hard_hit_rate field, _render_hard_hit_section(), executive summary bullet, compute call in assembler
- `report.py` - Added HardHit% to _KNOWN_METRICS hallucination guard
- `tests/test_engine.py` - 7 new tests for hard-hit rate computation
- `tests/test_context.py` - 2 new tests for context integration and prompt rendering
- `.gitignore` - Added aggs/ for worktree data symlinks

## Decisions Made
- Used `_usage_delta_string` for hard-hit rate delta since it handles percentage-point deltas with appropriate thresholds (5pp steady, 10pp sharp)
- Placed Contact Quality as its own `## Contact Quality` section after Execution rather than embedding within Execution, for clarity
- Executive summary hard-hit rate bullet uses >= 5.0pp threshold and excludes cold start and "Steady" deltas
- Set small_sample threshold at `_MIN_PITCHES` (10) reusing existing constant

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Data files (parquet + aggs/) are gitignored and not present in worktrees -- created symlinks to main repo data files and added `aggs` to .gitignore

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data is wired end-to-end from Statcast through engine to prompt rendering.

## Self-Check: PASSED

All files exist. All commits found. All key artifacts verified in source files.

---
*Plan: quick-260326-q9s*
*Completed: 2026-03-26*
