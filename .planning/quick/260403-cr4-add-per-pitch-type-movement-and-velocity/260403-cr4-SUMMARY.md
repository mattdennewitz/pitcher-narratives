---
phase: quick
plan: 260403-cr4
subsystem: engine, context, pipeline
tags: [movement, pfx_x, pfx_z, yoy, pitch-trend, arsenal-trend]
dependency_graph:
  requires: [PitchTrend, compute_arsenal_trends, _movement_delta_string, _render_yoy_section, _build_stuff_input, _build_game_shape_input]
  provides: [per-pitch-movement-yoy-deltas]
  affects: [context-yoy-section, stuff-specialist-input, game-shape-specialist-input]
tech_stack:
  added: []
  patterns: [tdd-red-green, statcast-pfx-movement-columns]
key_files:
  created: []
  modified:
    - src/pitcher_narratives/engine.py
    - src/pitcher_narratives/context.py
    - src/pitcher_narratives/pipeline.py
    - tests/test_engine.py
    - tests/test_context.py
    - tests/test_pipeline.py
decisions:
  - Movement falls back to 0.0 when pfx_x/pfx_z columns missing from statcast (no agg CSV fallback like velocity)
  - Game shape pipeline loop replaced single-field usage check with multi-field (usage + H-mov + V-mov) check
metrics:
  duration: 5m 55s
  completed: 2026-04-03
  tasks_completed: 2
  tasks_total: 2
  tests_added: 4
  tests_total_passing: 45
---

# Quick Task 260403-cr4: Per-Pitch-Type Movement and Velocity YoY Deltas Summary

PitchTrend extended with pfx_x/pfx_z horizontal and vertical movement deltas computed from statcast data, rendered as H-mov/V-mov in YoY context and specialist pipelines.

## What Changed

### Task 1: Add movement fields to PitchTrend and compute them

**Commits:** ccd8451 (RED), 95e6271 (GREEN)

- Added 6 fields to PitchTrend dataclass: `prior_pfx_x`, `current_pfx_x`, `pfx_x_delta`, `prior_pfx_z`, `current_pfx_z`, `pfx_z_delta`
- `compute_arsenal_trends` computes movement from statcast `pfx_x`/`pfx_z` columns per pitch_type per season, reusing the already-filtered prior/current statcast DataFrames
- Uses existing `_movement_delta_string()` for qualitative strings (e.g., "Down 2.0 in", "Steady (+0.2 in)")
- Falls back to 0.0 when statcast is empty or missing pfx columns
- Updated `_make_statcast` test helper to include pfx_x/pfx_z columns with 0.0 defaults
- New test `test_arsenal_trends_movement_deltas` verifies per-pitch-type movement computation

### Task 2: Wire movement deltas into context rendering and specialist pipelines

**Commits:** 1fb1074 (RED), 7ef0963 (GREEN)

- `_render_yoy_section` in context.py appends "H-mov" and "V-mov" entries for non-Steady pitch trends
- `_build_stuff_input` in pipeline.py renders per-pitch movement lines below added/dropped section
- `_build_game_shape_input` in pipeline.py replaced the usage-only loop with a combined loop that shows usage, H-mov, and V-mov per pitch
- Updated PitchTrend fixtures in test_context.py and test_pipeline.py with realistic movement values
- New tests: `test_to_prompt_yoy_renders_movement_deltas`, `test_stuff_input_yoy_movement_deltas`, `test_game_shape_input_movement_shifts`

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all fields are fully wired from statcast data through rendering.

## Verification

```
45 passed, 147 deselected, 1 warning in 0.59s
```

All arsenal_trends and yoy tests pass. Pre-existing failures in test_analyst.py and other modules are data-dependency issues (missing local parquet files) unrelated to this change.

## Self-Check: PASSED

All 7 modified/created files verified present. All 4 task commits verified in git log.
