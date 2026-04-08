---
phase: 22-context-assembly-prompt-rendering
plan: 02
subsystem: pipeline
tags: [pipeline, arsenal-trends, cross-season, specialist-agents]

requires:
  - phase: 22-01
    provides: "Typed cross-season fields on PitcherContext, _render_yoy_section method, ArsenalTrends/ArsenalPitchTrend dataclasses"
  - phase: 21-01
    provides: "ArsenalTrends engine (compute_arsenal_trends) with added/dropped/continued attributes"
provides:
  - "Pipeline specialist prompt builders use correct ArsenalTrends attributes (added, dropped, continued)"
  - "Dead code removed (pfx_x_delta/pfx_z_delta on ArsenalPitchTrend, _render_appearance_pitch_trends_section)"
  - "14 unit tests verifying cross-season data flows into specialist prompts"
affects: [pipeline, report-generation]

tech-stack:
  added: []
  patterns:
    - "MagicMock PitcherContext with monkeypatched baselines for data-isolated pipeline tests"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/pipeline.py
    - tests/test_pipeline.py

key-decisions:
  - "Replaced pfx_x_delta/pfx_z_delta movement rendering with usage/velo/S+ delta rendering for continued pitches"
  - "Used MagicMock for PitcherContext in tests to avoid dependency on real statcast data files"

patterns-established:
  - "Monkeypatch compute_league_baselines and render_league_baselines for pipeline builder unit tests"

requirements-completed: [CPMT-03]

duration: 7min
completed: 2026-04-08
---

# Phase 22 Plan 02: Pipeline ArsenalTrends Fix Summary

**Fixed specialist prompt builders to use correct ArsenalTrends attribute names (added, dropped, continued) and removed dead pfx_x_delta/pfx_z_delta code**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-08T22:32:48Z
- **Completed:** 2026-04-08T22:40:38Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- All three specialist prompt builders (stuff, trends, game shape) now use correct ArsenalTrends attributes
- Removed dead code referencing nonexistent ArsenalPitchTrend.pfx_x_delta/pfx_z_delta and _render_appearance_pitch_trends_section
- Added 14 isolated unit tests verifying cross-season data flows correctly into specialist prompts

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix ArsenalTrends attribute names and remove dead code** - `8c7f87a` (fix)
2. **Task 2: Add integration tests for cross-season data in specialist prompts** - `6359283` (test)

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Fixed 3 functions: _build_stuff_input, _build_trend_input, _build_game_shape_input
- `tests/test_pipeline.py` - Added 14 tests across 3 test classes for cross-season data flow verification

## Decisions Made
- Replaced movement delta rendering (pfx_x_delta/pfx_z_delta) with usage/velocity/S+ delta rendering for continued pitches, since ArsenalPitchTrend has usage_delta, velo_delta, and s_plus_delta but not movement deltas
- Used MagicMock for PitcherContext with monkeypatched baselines to create data-isolated tests that don't require real statcast parquet files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rebased worktree onto main to pick up plan 22-01 changes**
- **Found during:** Pre-task investigation
- **Issue:** Worktree was behind main and missing plan 22-01 commits (typed cross-season fields, _render_yoy_section, ArsenalTrends dataclass)
- **Fix:** Ran `git rebase main` to incorporate plan 22-01 changes
- **Verification:** ArsenalTrends/ArsenalPitchTrend/CrossSeasonSummary classes confirmed present in engine.py

**2. [Rule 2 - Missing Critical] Added null guards for optional delta fields on ArsenalPitchTrend**
- **Found during:** Task 1 (replacing pfx deltas with usage/velo/S+ deltas)
- **Issue:** ArsenalPitchTrend.usage_delta, velo_delta, and s_plus_delta are `str | None`, but the plan's replacement code didn't guard against None
- **Fix:** Added `pt.usage_delta and` / `pt.velo_delta and` / `pt.s_plus_delta and` None guards before "Steady" checks in both _build_stuff_input and _build_game_shape_input
- **Files modified:** src/pitcher_narratives/pipeline.py
- **Committed in:** 8c7f87a (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
- Existing pipeline tests (TestBuildStuffInput, TestGeneratePipelineStreaming, etc.) require real statcast data files and cannot run in a worktree without data. New tests use MagicMock to avoid this dependency.

## Known Stubs
None - all code paths wire to real ArsenalTrends/CrossSeasonSummary data.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Specialist prompt builders now correctly access cross-season data
- Pipeline is ready for runtime testing with real pitcher data
- All existing unit tests continue to pass

---
*Phase: 22-context-assembly-prompt-rendering*
*Completed: 2026-04-08*
