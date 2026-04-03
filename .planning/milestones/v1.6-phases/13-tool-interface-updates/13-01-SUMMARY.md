---
phase: 13-tool-interface-updates
plan: 01
subsystem: api
tags: [analyst-tools, intermediates, attribution, markdown-rendering, pydantic-ai]

# Dependency graph
requires:
  - phase: 11-intermediate-probability-pipeline
    provides: IntermediateProbabilities dataclass and compute function wired into PitcherContext.intermediates
  - phase: 12-component-attribution
    provides: ComponentAttribution dataclass and compute function wired into PitcherContext.attributions
provides:
  - "get_pitcher_summary tool output includes Model Internals section with S-variant probabilities and P-vs-S location impact deltas"
  - "get_pitch_detail tool output includes per-pitch intermediates with P/S comparison and 13-outcome component attribution table"
affects: [14-system-prompt-rewrite]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_render_intermediates_section pattern on PitcherContext for to_prompt() rendering"
    - "_ps_line/_ps_line_rv helpers for P-vs-S probability/run-value formatting"
    - "attribution_rows/intermediates_rows keyword parameters on _render_pitch_detail"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/context.py
    - src/pitcher_narratives/analyst.py
    - tests/test_context.py
    - tests/test_analyst.py

key-decisions:
  - "4 diagnostic metrics (xSwing, xWhiff, xSwSt, xRV100) in summary view -- balances comprehensiveness vs token budget"
  - "S-variants and deltas only in intermediates section -- P-variants already in Execution section, avoids duplication"
  - "Probabilities as percentages, xRV100 as raw value -- respects scale differences per research guidance"

patterns-established:
  - "P-vs-S delta presentation: format as '+X.Xpp' for probabilities, '+X.XX' for run values"
  - "Attribution share computation: contribution/total * 100 with zero-division guard"

requirements-completed: [TOOL-01, TOOL-02]

# Metrics
duration: 4min
completed: 2026-03-31
---

# Phase 13 Plan 01: Tool Interface Updates Summary

**Extended analyst tools with S-variant intermediates and 13-outcome attribution rendering alongside existing plus scores**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-31T21:49:50Z
- **Completed:** 2026-03-31T21:54:18Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added "Model Internals: Location Impact" section to to_prompt() with S-variant values and P-vs-S deltas for xSwing, xWhiff, xSwSt, xRV100 per pitch type
- Extended get_pitch_detail with intermediates P/S comparison and 13-outcome component attribution (xRV100 decomposition) table
- get_pitcher_summary now includes intermediates via to_prompt() delegation
- 9 new tests (4 context + 5 analyst), all 261 tests passing with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add intermediates rendering to PitcherContext.to_prompt()** - `27b2450` (feat+test, TDD)
2. **Task 2: Extend get_pitch_detail with attribution and intermediates** - `54690ac` (feat+test, TDD)

## Files Created/Modified
- `src/pitcher_narratives/context.py` - Added _render_intermediates_section() method, called from to_prompt() after Execution section
- `src/pitcher_narratives/analyst.py` - Extended _render_pitch_detail() with attribution_rows and intermediates_rows; added _ps_line/_ps_line_rv helpers; updated get_pitch_detail to filter and pass new data
- `tests/test_context.py` - 4 new tests for intermediates in to_prompt output
- `tests/test_analyst.py` - 5 new tests for attribution and intermediates in tool output

## Decisions Made
- Selected 4 key diagnostic metrics (xSwing, xWhiff, xSwSt, xRV100) for the summary intermediates table to stay within token budget -- aligned with research recommendation
- Show only S-variants and P-minus-S deltas in the new section since P-variants are already in the existing Execution section, avoiding data duplication (Pitfall 2)
- Format probabilities as percentages (42.1% not 0.421) and xRV100 as raw values per scale guidance (Pitfall 5)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Data files (parquet + CSVs) not present in worktree -- resolved by symlinking from main repo directory

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data paths fully wired from existing PitcherContext fields through to rendered markdown output.

## Next Phase Readiness
- Tool output now includes model internals and attribution data
- Phase 14 (system prompt rewrite) can reference "Model Internals: Location Impact" and "Component Attribution" sections in its instructions for the analyst agent to reason from

---
*Phase: 13-tool-interface-updates*
*Completed: 2026-03-31*
