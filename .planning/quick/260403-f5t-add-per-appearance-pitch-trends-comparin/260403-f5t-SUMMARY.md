---
phase: quick
plan: 260403-f5t
subsystem: engine, context, pipeline
tags: [pitch-trends, three-way-comparison, appearance-analysis]
dependency_graph:
  requires: [engine.py helpers, PitcherData, PitcherContext]
  provides: [AppearancePitchTrendRecord, AppearancePitchTrends, compute_appearance_pitch_trends]
  affects: [context.py to_prompt(), pipeline.py _build_trend_input()]
tech_stack:
  added: []
  patterns: [three-way comparison pattern classification, per-appearance aggregation]
key_files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - src/pitcher_narratives/context.py
    - src/pitcher_narratives/pipeline.py
    - tests/test_engine.py
    - tests/test_context.py
decisions:
  - Pattern classification uses _VELO_THRESHOLD (0.5 mph) for consistency with existing delta helpers
  - Movement stored in inches (pfx * 12) matching existing convention
  - Prior season computed from statcast year < max_game_date.year, not from prior_pitch_type_baseline
metrics:
  duration_seconds: 407
  completed: "2026-04-03T15:07:22Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 15
  files_modified: 5
---

# Quick Plan 260403-f5t: Per-Appearance Pitch Trends Summary

**One-liner:** Three-way pitch trend comparison (last start vs window avg vs prior season) with pattern classification for the trends specialist.

## What Was Built

### Task 1: Dataclasses + compute_appearance_pitch_trends (TDD)

Added to `src/pitcher_narratives/engine.py`:

- **AppearancePitchTrendRecord** dataclass: Per-pitch-type record with velocity, horizontal movement (inches), vertical movement (inches) at three levels (last start, window average, prior season), qualitative delta strings, and pattern_label.
- **AppearancePitchTrends** dataclass: Container with last_game_date and list of records sorted by pitch count descending.
- **compute_appearance_pitch_trends()**: Computes the three-way comparison from PitcherData. Groups statcast by pitch_type for each level, computes means, converts movement to inches, applies delta string helpers, and classifies patterns.
- **_classify_pattern()**: Uses _VELO_THRESHOLD to classify: steady (both deltas below threshold), one-off (last != window but last ~ prior), sustained change (last ~ window but both != prior), something new (last != both). Single-season pitchers can only be steady or one-off.

8 tests added to `tests/test_engine.py` covering:
- Three-way comparison correctness (values and delta strings)
- _MIN_PITCHES filter (excludes pitch types with < 10 pitches in last start)
- Single-season pitcher handling (None prior values, "--" delta strings)
- Empty statcast and no window appearances returning None
- Multiple pitch types sorted by count descending
- All four pattern labels with specific numeric scenarios

### Task 2: Wire into PitcherContext and pipeline

- **context.py**: Added `appearance_pitch_trends: AppearancePitchTrends | None = None` field to PitcherContext. Added `_render_appearance_pitch_trends_section()` rendering velocity table with pattern labels and movement detail tables (horizontal and vertical). Wired into `to_prompt()` between Arsenal and Execution sections. Called from `assemble_pitcher_context()`.
- **pipeline.py**: Added appearance pitch trends section to `_build_trend_input()` so the trends specialist receives the three-way comparison data.

7 tests added to `tests/test_context.py` covering:
- Field default None, accepts value
- Rendered output contains correct headers and data
- Section omitted when None
- Ordering: after Arsenal, before Execution

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | `655ee18` | test: add failing tests for appearance pitch trends |
| 1 (GREEN) | `efc995c` | feat: add AppearancePitchTrends dataclasses and compute function |
| 2 | `9292143` | feat: wire appearance pitch trends into context and pipeline |

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all data is wired end-to-end from compute function through context assembly to prompt rendering and trends specialist input.

## Verification

All 15 new tests pass. Pre-existing tests that use real data files (not available in this worktree) show expected errors but are unrelated to this change. All synthetic/unit tests pass without regression.

## Self-Check: PASSED

All 6 files verified present. All 3 commits verified in git history.
