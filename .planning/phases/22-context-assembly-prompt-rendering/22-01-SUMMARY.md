---
phase: 22-context-assembly-prompt-rendering
plan: "01"
subsystem: context
tags: [pydantic, polars, cross-season, yoy, pipeline, specialist-agents]

# Dependency graph
requires:
  - phase: 20-season-delta-engine
    provides: CrossSeasonSummary dataclass and compute_cross_season_summary()
  - phase: 21-arsenal-trend-engine
    provides: ArsenalTrend/AddedDroppedPitch/PitchTrend dataclasses and compute_arsenal_trends()
provides:
  - PitcherContext with cross_season_summary and arsenal_trend optional fields
  - _render_yoy_section() for prompt rendering with top-level deltas and arsenal changes
  - assemble_pitcher_context() wired to call compute_cross_season_summary() and compute_arsenal_trends()
  - Stuff/Trend/Game Shape specialist inputs include cross-season context when available
affects: [report, pipeline, analyst]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional cross-season fields with None default for backward compatibility"
    - "Section omission pattern: return empty string when data absent, join filters it out"
    - "Specialist-specific YoY slicing: stuff gets grades, trend gets full, game_shape gets workload"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/context.py
    - src/pitcher_narratives/pipeline.py
    - tests/test_context.py
    - tests/test_pipeline.py

key-decisions:
  - "YoY section placed between First-Pitch and Recent Appearances in prompt ordering"
  - "Section heading is 'Year-over-Year Changes' in prompt, 'Year-over-Year Context' in specialist inputs"
  - "Location and Run Value specialists excluded from YoY data per CONTEXT.md decision"
  - "All-Steady pitch trends omitted from YoY section to reduce noise"
  - "Trend specialist reuses ctx._render_yoy_section() for full YoY rendering"

patterns-established:
  - "Synthetic PitcherContext fixture pattern for tests that don't need real data files"
  - "monkeypatch league baselines pattern for pipeline builder tests"

requirements-completed: [CPMT-01, CPMT-02, CPMT-03]

# Metrics
duration: 8min
completed: 2026-04-03
---

# Phase 22 Plan 01: Context Assembly & Prompt Rendering Summary

**PitcherContext wired with CrossSeasonSummary and ArsenalTrend fields, YoY section renders in prompt and 3 specialist inputs (stuff/trend/game_shape)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-03T12:31:24Z
- **Completed:** 2026-04-03T12:39:24Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- PitcherContext accepts optional cross_season_summary (CrossSeasonSummary) and arsenal_trend (ArsenalTrend) fields with None defaults for backward compatibility (CPMT-01)
- to_prompt() renders "## Year-over-Year Changes" section with velocity/P+/S+/L+ deltas, workload comparison, added/dropped pitches, and non-Steady pitch trend deltas when multi-season data exists; omits entirely for single-season pitchers (CPMT-02)
- Three specialist pipeline inputs extended: stuff gets velocity/grade deltas + adds/drops, trend gets full YoY render, game shape gets workload comparison + usage shifts; location and run value are unchanged (CPMT-03)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add cross-season fields to PitcherContext, render YoY section, wire assembly** - `4f68cbe` (feat)
   - RED: `test(22-01): add failing tests for YoY context assembly and rendering`
   - GREEN: `feat(22-01): add cross-season fields to PitcherContext and render YoY section`
2. **Task 2: Extend specialist pipeline inputs with cross-season context** - `2327432` (feat)
   - RED: `test(22-01): add failing tests for specialist pipeline YoY inputs`
   - GREEN: `feat(22-01): extend specialist pipeline inputs with cross-season context`

## Files Created/Modified
- `src/pitcher_narratives/context.py` - Added CrossSeasonSummary/ArsenalTrend imports, optional fields, _render_yoy_section(), assembly wiring
- `src/pitcher_narratives/pipeline.py` - Extended _build_stuff_input, _build_trend_input, _build_game_shape_input with YoY context blocks
- `tests/test_context.py` - 15 new tests for YoY context assembly and rendering using synthetic fixtures
- `tests/test_pipeline.py` - 14 new tests for specialist input YoY inclusion/exclusion using synthetic fixtures

## Decisions Made
- YoY section positioned between First-Pitch Tendencies and Recent Appearances in prompt ordering -- follows the pattern of "analysis sections first, recency context last"
- Location and Run Value specialists excluded from YoY data -- these analyze within-season mechanics, not year-over-year changes
- All-Steady pitch trends filtered from YoY section -- reduces noise when a pitch hasn't meaningfully changed
- Trend specialist reuses ctx._render_yoy_section() for full rendering -- avoids duplicating the render logic

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Cherry-picked prerequisite phases into worktree**
- **Found during:** Pre-task setup
- **Issue:** Phase 22 depends on Phases 19 (PitcherData prior-season baselines), 20 (CrossSeasonSummary), and 21 (ArsenalTrend), which existed on separate worktree branches
- **Fix:** Cherry-picked commits from worktree-agent-aa8b2afa (Phase 19), worktree-agent-a265bdb9 (Phase 20), and worktree-agent-afd23100 (Phase 21) into this worktree, resolving merge conflicts in test_engine.py
- **Files modified:** src/pitcher_narratives/data.py, src/pitcher_narratives/engine.py, tests/test_data.py, tests/test_engine.py
- **Verification:** All 20 cross-season engine tests pass

**2. [Rule 1 - Bug] Fixed missing prior_season_baseline fields in arsenal trend test helper**
- **Found during:** Pre-task setup (merge conflict resolution)
- **Issue:** The Phase 21 fix commit (69568a3) had a merge conflict that left _make_pitcher_data_for_trends() missing prior_season_baseline and prior_pitch_type_baseline fields
- **Fix:** Added prior_season_baseline=pl.DataFrame() and prior_pitch_type_baseline=pl.DataFrame() to the test helper
- **Files modified:** tests/test_engine.py
- **Verification:** All 13 arsenal trend tests pass

---

**Total deviations:** 2 auto-fixed (1 blocking dependency, 1 bug in test helper)
**Impact on plan:** Both fixes necessary for prerequisite code to function. No scope creep.

## Issues Encountered
- Worktree isolation: This agent's worktree only had v1.7 code; Phases 19-21 were on separate agent worktrees. Required cherry-picking 3 phases worth of changes before starting Phase 22 work.
- Existing test suite failures: Many tests require real data files (statcast parquet, Pitching+ CSVs) not present in the worktree. All new tests use synthetic fixtures to avoid this dependency.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all fields are wired to real compute functions (compute_cross_season_summary, compute_arsenal_trends) and rendering produces actual data when multi-season data exists.

## Next Phase Readiness
- Phase 22 is the final phase of v1.8 milestone
- All CPMT requirements complete: context assembly and prompt rendering for cross-season data
- When merged with Phases 19-21, the full v1.8 pipeline will surface year-over-year changes in narratives

## Self-Check: PASSED

- FOUND: src/pitcher_narratives/context.py
- FOUND: src/pitcher_narratives/pipeline.py
- FOUND: tests/test_context.py
- FOUND: tests/test_pipeline.py
- FOUND commit: 4f68cbe
- FOUND commit: 2327432

---
*Phase: 22-context-assembly-prompt-rendering*
*Completed: 2026-04-03*
