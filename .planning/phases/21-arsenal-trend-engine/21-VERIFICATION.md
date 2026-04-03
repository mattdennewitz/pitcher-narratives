---
phase: 21-arsenal-trend-engine
verified: 2026-04-03T12:30:00Z
status: passed
score: 3/3 must-haves verified
re_verification: false
---

# Phase 21: Arsenal Trend Engine Verification Report

**Phase Goal:** Users see which pitches a pitcher added, dropped, or significantly changed year-over-year
**Verified:** 2026-04-03T12:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Engine identifies pitches present in prior season but absent in current (dropped) and vice versa (added) | VERIFIED | `compute_arsenal_trends()` at engine.py:2943 computes `prior_types - current_types` (dropped) and `current_types - prior_types` (added) using `_MIN_PITCHES=10` threshold; tests `test_arsenal_trends_identifies_added_pitch` and `test_arsenal_trends_identifies_dropped_pitch` both pass |
| 2 | Engine computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity | VERIFIED | `PitchTrend` dataclass at engine.py:2877 carries `usage_delta`, `p_plus_delta`, `s_plus_delta`, `velo_delta` qualitative strings plus raw `prior_*`/`current_*` numeric fields; `test_arsenal_trends_yoy_deltas_for_shared_pitches` passes |
| 3 | When a pitcher has only one season of data, arsenal trend output is None | VERIFIED | `compute_arsenal_trends()` returns `None` when `len(seasons) < 2` (engine.py:2976-2977); `test_arsenal_trends_single_season_returns_none` passes |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/engine.py` | `AddedDroppedPitch`, `PitchTrend`, `ArsenalTrend` dataclasses and `compute_arsenal_trends()` function | VERIFIED | All four symbols defined at lines 2857, 2877, 2924, 2943; exported in `__all__` at lines 28, 30, 40, 53; file is 3092 lines (substantive) |
| `tests/test_engine.py` | 13 comprehensive tests for all three requirements | VERIFIED | 13 arsenal-trend tests at lines 1197-1529 using synthetic `_make_pitcher_data_for_trends` factory; all 13 pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `compute_arsenal_trends` | `compute_pitch_type_baseline` | `from pitcher_narratives.data import compute_pitch_type_baseline` (engine.py:2963) | WIRED | Import is deferred inside function body; `compute_pitch_type_baseline` confirmed at data.py:349 |
| `compute_arsenal_trends` | `_usage_delta_string`, `_pplus_delta_string`, `_velo_delta_string` | Direct calls at engine.py:3070-3079 | WIRED | All three helpers defined at engine.py:382, 401, 420 |
| `compute_arsenal_trends` | `_MIN_PITCHES` threshold | `pl.col("n_pitches") >= _MIN_PITCHES` at engine.py:2991, 2994 | WIRED | Constant defined at engine.py:96 |
| `compute_arsenal_trends` | `_build_name_map` | Called at engine.py:2987 | WIRED | Helper defined at engine.py:583 |
| `tests/test_engine.py` | `compute_arsenal_trends`, `ArsenalTrend`, `PitchTrend`, `AddedDroppedPitch` | Imports at test_engine.py:47 | WIRED | All symbols imported and exercised in 13 tests |

### Data-Flow Trace (Level 4)

Not applicable. This phase produces a computation engine (pure function returning dataclasses), not a rendering component. Data flows into `compute_arsenal_trends(data: PitcherData)` and out as an `ArsenalTrend` dataclass. The function reads from `data.agg_csvs["pitcher_type"]` (real DataFrame) and `data.statcast` (real DataFrame); no static returns or hardcoded empty fallbacks for the success path. Downstream rendering is Phase 22's responsibility.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 13 arsenal-trend unit tests pass | `uv run python -m pytest tests/test_engine.py -v -k "arsenal_trend"` | `13 passed, 84 deselected in 0.08s` | PASS |
| Full test suite has no regressions | `uv run python -m pytest tests/test_engine.py` | `97 passed in 38.74s` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ATRN-01 | 21-01-PLAN.md | Engine identifies pitches added (in current, absent prior) and dropped (in prior, absent current) using minimum-pitch threshold | SATISFIED | `compute_arsenal_trends()` builds `added_pitches` and `dropped_pitches` lists with `_MIN_PITCHES=10` guard; tests `test_arsenal_trends_identifies_added_pitch`, `test_arsenal_trends_identifies_dropped_pitch`, `test_arsenal_trends_min_pitches_filters_noise` all pass |
| ATRN-02 | 21-01-PLAN.md | Engine computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity for pitches present in both seasons | SATISFIED | `PitchTrend` dataclass contains all four delta fields; `compute_arsenal_trends()` populates them using existing qualitative helpers; `test_arsenal_trends_yoy_deltas_for_shared_pitches` and `test_arsenal_trends_usage_delta_strings` pass |
| ATRN-03 | 21-01-PLAN.md | Arsenal trend output is None when pitcher has only one season of data | SATISFIED | Early return `if len(seasons) < 2: return None` at engine.py:2976; `test_arsenal_trends_single_season_returns_none` and `test_arsenal_trends_empty_agg_returns_none` pass |

No orphaned requirements. REQUIREMENTS.md marks all three ATRN IDs as Complete under Phase 21.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No TODOs, FIXMEs, placeholder returns, or hardcoded empty collections found in the new arsenal trend code (engine.py lines 2853-3092).

### Human Verification Required

None. All goal behaviors are verifiable programmatically via unit tests. Phase 22 (Context Assembly) is where the `ArsenalTrend` output is rendered into the LLM prompt — human review of narrative quality belongs there.

### Gaps Summary

No gaps. All three success criteria from the roadmap are satisfied by substantive, wired, tested implementation:

- Added/dropped pitch detection (ATRN-01): implemented with `_MIN_PITCHES=10` noise filter, tested with 3 cases
- Per-pitch-type YoY deltas for usage/P+/S+/velocity (ATRN-02): implemented using existing qualitative delta helpers for LLM consistency, tested with delta-string validation
- Single-season None return (ATRN-03): implemented with early return, tested with 2 edge cases (empty agg, missing key)

The engine is a pure computation layer producing `ArsenalTrend` dataclass output. Phase 22 consumes it; downstream rendering is not in scope for this phase.

---

_Verified: 2026-04-03T12:30:00Z_
_Verifier: Claude (gsd-verifier)_
