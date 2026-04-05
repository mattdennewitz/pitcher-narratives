---
phase: quick
plan: 260404-vya
subsystem: pipeline
tags: [cachepoint, pydantic-ai, llm-caching, prompt-optimization]

# Dependency graph
requires: []
provides:
  - CachePoint-aware specialist builders in pipeline.py
  - UserPrompt type alias for consistent prompt typing
  - _flatten_prompt and _render_user_prompt utilities
affects: [pipeline, report, anchor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CachePoint placement after header+baselines prefix in specialist builders"
    - "UserPrompt type alias (list[str | CachePoint]) for structured prompts"
    - "_flatten_prompt for audit/revision plain text, _render_user_prompt for tracing"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/pipeline.py

key-decisions:
  - "Split each builder at header+baselines boundary -- this is the natural cache prefix that stays constant across same-pitcher reruns"
  - "Used _flatten_prompt for audit ground truths to keep f-string concatenation working"
  - "Matched report.py pattern for _render_user_prompt but with simpler breakpoint marker text"

patterns-established:
  - "CachePoint insertion pattern: header_lines + CachePoint() + data_lines for newline-joined builders"
  - "CachePoint insertion pattern: prefix_sections + CachePoint() + data_sections for double-newline-joined builders"

requirements-completed: []

# Metrics
duration: 5min
completed: 2026-04-04
---

# Quick Task 260404-vya: CachePoint Support for Pipeline Specialist Builders

**Added CachePoint cache breakpoints to all 5 specialist data builders in pipeline.py, enabling Anthropic prompt caching of header+baselines prefix across same-pitcher reruns**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-05T03:21:19Z
- **Completed:** 2026-04-05T03:26:06Z
- **Tasks:** 2 (1 implementation + 1 validation)
- **Files modified:** 1

## Accomplishments
- All 5 specialist builders (_build_stuff_input, _build_location_input, _build_runvalue_input, _build_trend_input, _build_game_shape_input) return UserPrompt with CachePoint after header+baselines
- Added UserPrompt type alias, _flatten_prompt utility (strips CachePoints for audit), and _render_user_prompt utility (renders breakpoint markers for tracing)
- Added _get_specialist_input_text helper so audit_and_revise_specialists continues to receive plain text ground truths
- Updated write_pipeline_data_file to render cache breakpoint markers in data files
- Updated run_specialists type annotation for UserPrompt passthrough to pydantic-ai
- Validated with live data: all 5 builders return 3-part UserPrompt lists, data file contains exactly 5 breakpoint markers

## Task Commits

Each task was committed atomically:

1. **Task 1: Add CachePoint support to all 5 specialist builders and update call sites** - `e79d2c9` (feat)
2. **Task 2: Validate CachePoint placement with a live data smoke test** - no code changes, validation-only task

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Added CachePoint import, UserPrompt type alias, _flatten_prompt, _render_user_prompt, _get_specialist_input_text; refactored all 5 builders to return UserPrompt; updated _get_specialist_input, audit_and_revise_specialists, run_specialists, and write_pipeline_data_file

## Decisions Made
- Split at the header+baselines boundary in each builder (natural cache prefix that stays constant across same-pitcher reruns while data sections vary per specialist)
- Used _flatten_prompt for audit ground truths rather than passing UserPrompt, since _build_specialist_audit_input and _build_specialist_revision_input do string concatenation via f-strings
- Matched the pattern from report.py for _render_user_prompt but used simpler `-- [cache breakpoint] --` marker text vs report.py's unicode dashes

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is fully wired.

## Issues Encountered

- Data files (parquet) are not present in the worktree; resolved by pointing PITCHER_NARRATIVES_DATA_DIR to the main repo for the live validation test

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Pipeline specialist builders are now CachePoint-aware
- Anthropic prompt caching will automatically activate when the same pitcher's header+baselines prefix is reused across runs
- No further changes needed; pydantic-ai handles CachePoint in UserPrompt lists natively

## Self-Check: PASSED

- FOUND: src/pitcher_narratives/pipeline.py
- FOUND: 260404-vya-SUMMARY.md
- FOUND: commit e79d2c9

---
*Plan: quick/260404-vya*
*Completed: 2026-04-04*
