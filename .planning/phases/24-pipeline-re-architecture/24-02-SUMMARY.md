---
phase: 24-pipeline-re-architecture
plan: 02
subsystem: pipeline
tags: [specialist-agents, raw-data-grounding, anti-hallucination, pipeline]

# Dependency graph
requires:
  - phase: 22-context-assembly-prompt-rendering
    provides: PitcherContext with arsenal (PitchTypeSummary) and appearance_pitch_trends
provides:
  - Per-pitch delta table in Stuff specialist input (velo, movement, S+, P+ columns)
  - Primary pitch delta appendix in Trend specialist input (>=10% usage filter)
  - Anti-recalculation directive in Stuff prompt
  - Citation requirement for Raw Data ground truth
affects: [24-pipeline-re-architecture, 25-prompt-engineering]

# Tech tracking
tech-stack:
  added: []
  patterns: [raw-data-appendix-pattern, anti-recalculation-directive]

key-files:
  created: []
  modified:
    - src/pitcher_narratives/pipeline.py
    - tests/test_pipeline.py

key-decisions:
  - "Stuff appendix uses full arsenal (all pitches) while Trend appendix filters to primary pitches (>=10% usage) per PIPE-05/D-11"
  - "Anti-recalculation directive added to OUTPUT FORMAT section of Stuff prompt to prevent LLM from recomputing provided deltas"

patterns-established:
  - "Raw data appendix pattern: consolidated markdown table appended to specialist input, labeled 'Raw Data (cite these exact numbers)' for grounding"

requirements-completed: [PIPE-05]

# Metrics
duration: 3min
completed: 2026-04-04
---

# Phase 24 Plan 02: Raw Data Appendices Summary

**Per-pitch delta table and primary pitch appendix added to Stuff and Trend specialist inputs for anti-hallucination grounding**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-04T20:22:07Z
- **Completed:** 2026-04-04T20:25:38Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Stuff specialist input now includes a consolidated Per-Pitch Delta Table with all velo, movement, and plus score fields from PitchTypeSummary
- Trend specialist input now includes a primary-pitch-only (>=10% usage) raw data appendix with usage, velo, movement, and grade deltas
- Both appendices labeled "Raw Data (cite these exact numbers)" for LLM grounding
- Anti-recalculation directive added to Stuff specialist prompt: "Do not attempt to recalculate these numbers"
- Citation requirement added: "use the exact values from the Raw Data section"

## Task Commits

Each task was committed atomically:

1. **Task 1: Stuff per-pitch delta table and Trend timeline appendix with tests**
   - `3ab4fb7` (test) - RED: failing tests for delta table and raw data appendix
   - `8639fa0` (feat) - GREEN: implement raw data appendices and prompt directives

_Note: TDD task with RED + GREEN commits_

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Added per-pitch delta table to `_build_stuff_input()`, primary pitch appendix to `_build_trend_input()`, anti-recalculation and citation directives to `_STUFF_SPECIALIST_PROMPT`
- `tests/test_pipeline.py` - Added TestStuffAppendix (6 tests) and TestTrendAppendix (3 tests)

## Decisions Made
- Stuff appendix includes all arsenal pitches (no usage filter) since physical profile analysis covers every pitch type. Trend appendix filters to primary pitches (>=10% usage) to focus temporal analysis on meaningful data.
- Anti-recalculation directive placed in OUTPUT FORMAT section of the Stuff prompt, co-located with other output instructions.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all data flows are fully wired.

## Self-Check: PASSED

- FOUND: 24-02-SUMMARY.md
- FOUND: 3ab4fb7 (RED commit)
- FOUND: 8639fa0 (GREEN commit)
- FOUND: src/pitcher_narratives/pipeline.py
- FOUND: tests/test_pipeline.py

## Next Phase Readiness
- Raw data appendices are in place for PIPE-05 grounding
- Ready for 24-03 (full pipeline wiring: 6-agent orchestration, writer prompt, auditor categories)

---
*Phase: 24-pipeline-re-architecture*
*Completed: 2026-04-04*
