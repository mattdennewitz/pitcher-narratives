---
phase: quick
plan: 260326-vj7
subsystem: engine
tags: [release-point, statcast, polars, dataclass, context-assembly]

requires:
  - phase: 03-context-assembly
    provides: PitcherContext model with to_prompt() rendering
provides:
  - Per-pitch-type release point metrics (x, z, extension) with window vs season deltas
  - Release Point section in LLM context document
affects: [report-generation, prompt-tuning]

tech-stack:
  added: []
  patterns:
    - "Release point delta helpers (_release_delta_string, _extension_delta_string) with ft units"
    - "Per-pitch-type grouping pattern for statcast release columns"

key-files:
  created: []
  modified:
    - engine.py
    - context.py
    - tests/test_engine.py
    - tests/test_context.py

key-decisions:
  - "0.1 ft threshold for release_x/z deltas (sensitive to ~1.2 inch changes), 0.2 ft for extension"
  - "Cold start renders without delta columns plus explanatory note"
  - "Release Point section placed between Execution and Contact Quality in prompt"

patterns-established:
  - "Release point analysis follows same per-pitch-type aggregation pattern as arsenal and execution"

requirements-completed: [release-point-analysis]

duration: 4min
completed: 2026-03-27
---

# Quick 260326-vj7: Add Release Point Analysis Summary

**Per-pitch-type release point metrics (horiz/vert/extension) with window vs season deltas and ft-based threshold strings, rendered as markdown table in LLM context document**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T02:46:39Z
- **Completed:** 2026-03-27T02:51:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- ReleasePointPitchType and ReleasePointMetrics dataclasses with window/season means and qualitative delta strings for all three release dimensions
- Release Point markdown table in to_prompt() between Execution and Contact Quality, capped at 4 pitch types
- Cold start (no baseline), small sample (<10 pitches), and null release data handled gracefully
- Token budget remains at ~770 tokens (well under 2,000 limit)
- 9 new tests (7 engine + 2 context), all 160 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ReleasePointMetrics engine and tests** - `316eff6` (test: RED), `dc51b0f` (feat: GREEN)
2. **Task 2: Wire release point into context document** - `8106e24` (feat)

## Files Created/Modified
- `engine.py` - ReleasePointPitchType, ReleasePointMetrics dataclasses, compute_release_point_metrics function, _release_delta_string and _extension_delta_string helpers
- `context.py` - release_point field on PitcherContext, _render_release_point_section method, wired in assemble_pitcher_context
- `tests/test_engine.py` - 7 tests: returns metrics, reasonable values, per-pitch-type, delta strings, cold start, small sample, ordering
- `tests/test_context.py` - 2 tests: release_point_in_context, to_prompt_has_release_point

## Decisions Made
- Used 0.1 ft threshold for horizontal/vertical release deltas (~1.2 inches, meaningful for release point consistency) and 0.2 ft for extension (slightly less sensitive)
- Separate _release_delta_string and _extension_delta_string helpers (ft units, 2 decimal places) rather than reusing _movement_delta_string (inches)
- Cold start mode renders table without Delta columns plus "(season = window -- no baseline)" note
- Small sample pitch types marked with asterisk in table

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Data files (parquet + aggs) not present in worktree; resolved by symlinking from main repo

## Known Stubs

None - all data is wired through from statcast release columns.

## Self-Check: PASSED
