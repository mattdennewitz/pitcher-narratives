---
phase: 21-arsenal-trend-engine
verified: 2026-04-08T23:00:00Z
status: passed
score: 3/3 must-haves verified
re_verification: false
---

# Phase 21: Arsenal Trend Engine Verification Report

**Phase Goal:** Users see which pitches a pitcher added, dropped, or significantly changed year-over-year
**Verified:** 2026-04-08
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Engine identifies pitches added (in current season, absent in prior) and dropped (in prior, absent in current) using a minimum-pitch threshold | VERIFIED | `compute_arsenal_trends()` uses set difference on `current_types - prior_types` and `prior_types - current_types`, both filtered by `_MIN_PITCHES`. Test `test_arsenal_trends_identifies_added_dropped` passes against live multi-year data. |
| 2 | Engine computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity for pitches present in both seasons | VERIFIED | Continued pitches receive `usage_delta`, `p_plus_delta`, `s_plus_delta`, `l_plus_delta`, and `velo_delta` strings via existing qualitative helpers. Test `test_arsenal_trends_computes_yoy_deltas` passes. Velocity sourced from statcast parquet. |
| 3 | Arsenal trend output is None when pitcher has only one season of data | VERIFIED | Function checks `len(seasons) < 2` and returns `None`. Test `test_arsenal_trends_single_season_returns_none` constructs a single-season `PitcherData` and asserts `None`. Passes. |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/engine.py` | `ArsenalPitchTrend` dataclass | VERIFIED | Lines 815–866. Full field set: pitch_type, pitch_name, status, prior/current season, usage, P+/S+/L+, velocity, pitch counts. |
| `src/pitcher_narratives/engine.py` | `ArsenalTrends` dataclass | VERIFIED | Lines 868–890. Fields: `added`, `dropped`, `continued` lists, `prior_season`, `current_season`, `has_changes` property. |
| `src/pitcher_narratives/engine.py` | `compute_arsenal_trends()` function | VERIFIED | Lines 1598–1794. Substantive: handles None/empty data, computes per-season baselines, applies `_MIN_PITCHES` threshold, builds all three lists, returns `ArsenalTrends`. |
| `src/pitcher_narratives/engine.py` | All symbols in `__all__` | VERIFIED | Lines 29–30 and 54: `ArsenalPitchTrend`, `ArsenalTrends`, `compute_arsenal_trends` all present in `__all__`. |
| `tests/test_engine.py` | 10 tests for arsenal trend engine | VERIFIED | Functions at lines 1144–1327. All 10 pass. Coverage: ATRN-01, ATRN-02, ATRN-03, qualitative language, minimum threshold, season fields, `has_changes`, velocity deltas, pitch names. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `compute_arsenal_trends` | `data.agg_csvs["pitcher_type"]` | `compute_pitch_type_baseline()` | WIRED | Function imports and calls `compute_pitch_type_baseline(pt_df)` from `pitcher_narratives.data`. |
| `compute_arsenal_trends` | `data.statcast` | polars filter on `game_date.dt.year()` | WIRED | Velocity for continued pitches is pulled directly from `data.statcast` per-season filter. |
| `ArsenalPitchTrend` delta strings | `_pplus_delta_string`, `_velo_delta_string`, `_usage_delta_string` | direct call | WIRED | All three qualitative helpers called for continued pitches. Test `test_arsenal_trends_uses_qualitative_language` confirms Steady/Up/Down prefix output. |
| `engine.py` symbols | downstream (Phase 22) | `__all__` export | WIRED (export ready) | Phase 22 wiring of `arsenal_trend` into `PitcherContext` and rendering is explicitly out-of-scope for Phase 21. |

### Data-Flow Trace (Level 4)

This phase produces a computation engine, not a rendering component. Data flows from parquet/CSV through `compute_arsenal_trends()` to a dataclass. No rendering artifact to trace.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `compute_arsenal_trends()` | `pt_baseline` | `data.agg_csvs["pitcher_type"]` via `compute_pitch_type_baseline()` | Yes — live CSV data filtered per-season | FLOWING |
| `compute_arsenal_trends()` | velocity (continued pitches) | `data.statcast` filtered by `pitch_type` and `game_date.dt.year()` | Yes — real statcast rows | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ATRN-03: Single-season returns None | `uv run python -m pytest tests/test_engine.py::test_arsenal_trends_single_season_returns_none -v` | PASSED | PASS |
| ATRN-01: Add/drop classification | `uv run python -m pytest tests/test_engine.py::test_arsenal_trends_identifies_added_dropped -v` | PASSED | PASS |
| ATRN-02: YoY deltas computed | `uv run python -m pytest tests/test_engine.py::test_arsenal_trends_computes_yoy_deltas -v` | PASSED | PASS |
| Full test suite (no regressions) | `uv run python -m pytest tests/test_engine.py -v` | 98 passed in 62.74s | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ATRN-01 | 21-01-PLAN.md | Engine identifies pitches added (present in current season, absent in prior) and dropped (present in prior, absent in current) using a minimum-pitch threshold | SATISFIED | Set-difference logic at lines 1654–1656. `_MIN_PITCHES` applied to both seasons at lines 1641–1650. `test_arsenal_trends_identifies_added_dropped` passes. |
| ATRN-02 | 21-01-PLAN.md | Engine computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity for pitches present in both seasons | SATISFIED | Continued-pitch loop at lines 1718–1783 computes all four delta dimensions. `test_arsenal_trends_computes_yoy_deltas` and `test_arsenal_trends_velocity_deltas` pass. |
| ATRN-03 | 21-01-PLAN.md | Arsenal trend output is None when pitcher has only one season of data | SATISFIED | `len(seasons) < 2` guard at line 1628. `test_arsenal_trends_single_season_returns_none` passes. |

No orphaned requirements: all three ATRN IDs are accounted for by 21-01-PLAN.md and verified in the codebase.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/pitcher_narratives/pipeline.py` | 562–575, 707–724 | References `at.added_pitches`, `at.dropped_pitches`, `at.pitch_trends`, `pt.pfx_x_delta`, `pt.pfx_z_delta` — field names that do not exist on the new `ArsenalTrends`/`ArsenalPitchTrend` dataclasses | INFO | Pre-existing placeholder guards written before Phase 21. They are dead code until Phase 22 populates `ctx.arsenal_trend` (currently `Any | None = None` in context.py). Phase 21 did not touch pipeline.py. Phase 22 must reconcile these attribute names with the actual `ArsenalTrends` shape when wiring. |

No stubs or placeholder patterns found in Phase 21 code (lines 815–1794 of engine.py).

### Human Verification Required

None. All behaviors are programmatically verifiable via the test suite.

### Gaps Summary

No gaps. All three ATRN requirements are implemented, substantive, and tested with passing tests. The pre-existing pipeline attribute mismatch (`added_pitches` vs `added`, etc.) is a Phase 22 responsibility explicitly called out in the Phase 21 CONTEXT and PLAN.

---

_Verified: 2026-04-08_
_Verifier: Claude (gsd-verifier)_
