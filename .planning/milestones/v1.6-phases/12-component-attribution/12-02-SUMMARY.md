---
phase: 12-component-attribution
plan: 02
subsystem: engine
tags: [polars, xRV, component-attribution, run-values, dataclass]

requires:
  - phase: 12-01
    provides: "load_run_values() and RV_DF_PATH for count-specific run value lookup"
provides:
  - "OutcomeContribution and ComponentAttribution dataclasses"
  - "compute_component_attribution() at pitcher+type and pitcher+type+appearance grains"
  - "PitcherContext.attributions field for downstream tools and prompt rendering"
affects: [13-attribution-tools, 14-narrative-prompt]

tech-stack:
  added: []
  patterns: [unpivot-join-aggregate for probability x run-value decomposition]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - src/pitcher_narratives/context.py
    - tests/test_engine.py

key-decisions:
  - "Raw xRV100 (pre-mean-subtraction) used for contributions -- differs from mean-subtracted xRV100_P by a constant league-average offset"
  - "Contributions sorted by |contribution| descending for easy top-driver identification"

patterns-established:
  - "unpivot + join pattern: unpivot 13 probability columns to long format, join with RV_df on [balls, strikes, model_classes], aggregate per outcome"

requirements-completed: [DATA-03]

duration: 4min
completed: 2026-03-31
---

# Phase 12 Plan 02: Component Attribution Summary

**13-outcome xRV decomposition engine with per-pitch-type attribution at season and appearance grains, wired into PitcherContext**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-31T21:26:49Z
- **Completed:** 2026-03-31T21:31:03Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Implemented 13-outcome component attribution decomposing xRV100 into additive outcome contributions (probability x count-specific run value)
- Attribution works at both pitcher+type grain (season) and pitcher+type+appearance grain (per-game)
- Wired into PitcherContext.attributions field, capped at 4 pitch types, ready for Phase 13 tools

## Task Commits

Each task was committed atomically:

1. **Task 1: ComponentAttribution dataclasses, compute function, and tests** - `16144dd` (test + feat, TDD)
2. **Task 2: Wire ComponentAttribution into PitcherContext** - `cb1e506` (feat)

_Note: TDD task 1 had RED phase commit followed by GREEN phase commit._

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added OutcomeContribution, ComponentAttribution dataclasses, _OUTCOME_COLS_P/_OUTCOME_NAMES constants, compute_component_attribution() function
- `src/pitcher_narratives/context.py` - Added attributions field to PitcherContext, wired compute_component_attribution call in assemble_pitcher_context
- `tests/test_engine.py` - Added 7 test functions covering 13-outcome count, sum validation, label canonicality, magnitude sorting, both grains, and pitch names

## Decisions Made
- Used raw xRV100 (pre-mean-subtraction) for contribution sums -- this is the correct decomposition because mean-subtraction is a league-average constant that doesn't change per-outcome attribution
- Sorted contributions by |contribution| descending so the highest-impact outcomes appear first for downstream tools and prompts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ComponentAttribution accessible via PitcherContext.attributions for Phase 13 tools
- 13 canonical outcome labels stable for Phase 13 formatting and Phase 14 prompt rendering
- All 252 tests pass, lint clean

## Self-Check: PASSED

- All 3 source files exist
- Both task commits verified (16144dd, cb1e506)
- SUMMARY.md created

---
*Phase: 12-component-attribution*
*Completed: 2026-03-31*
