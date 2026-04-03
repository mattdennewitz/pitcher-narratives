---
phase: 20-season-delta-engine
verified: 2026-04-03T00:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 20: Season-Delta Engine Verification Report

**Phase Goal:** Users see year-over-year changes in top-level pitcher metrics (velocity, P+/S+/L+, workload profile)
**Verified:** 2026-04-03
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `compute_cross_season_summary` returns a `CrossSeasonSummary` with YoY deltas for velocity, P+, S+, L+ when multi-season data exists | VERIFIED | `engine.py:2149` fully populates all 20 fields including `current_velo`, `prior_velo`, `velo_delta`, `current_p_plus`, `prior_p_plus`, `p_plus_delta`, and S+/L+ equivalents; `test_cross_season_summary_returns_dataclass` and `test_cross_season_summary_metrics` confirm values |
| 2 | YoY delta strings use the same qualitative language as within-season deltas (Steady/Up/Down with same thresholds) | VERIFIED | `compute_cross_season_summary` calls `_velo_delta_string(current_velo - prior_velo)` at line 2187 and `_pplus_delta_string(...)` at lines 2188-2190, reusing the existing threshold constants `_VELO_THRESHOLD=0.5` and `_PPLUS_THRESHOLD=5`; `test_cross_season_delta_strings_match` asserts "Up"/"mph"/"points"/"sharply" string patterns |
| 3 | `compute_cross_season_summary` returns `None` when `prior_season_baseline` is empty (single-season pitcher) | VERIFIED | `engine.py:2164-2165`: `if data.prior_season_baseline.is_empty(): return None`; `test_cross_season_none_single_season` confirms this path returns `None` |
| 4 | `CrossSeasonSummary` includes basic workload comparison (appearances, IP, avg pitches per appearance) | VERIFIED | Dataclass at `engine.py:1106` has `current_appearances`, `prior_appearances`, `current_ip`, `prior_ip`, `current_avg_pitches`, `prior_avg_pitches`; `_per_season_workload` at line 486 computes these from appearances and statcast; `test_cross_season_workload` asserts all are > 0 |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/engine.py` | `CrossSeasonSummary` dataclass and `compute_cross_season_summary` function | VERIFIED | `class CrossSeasonSummary` at line 1106 (20 fields, fully populated); `def compute_cross_season_summary` at line 2149; both exported in `__all__` at lines 30 and 51 |
| `tests/test_engine.py` | Cross-season summary unit tests | VERIFIED | 7 test functions matching `test_cross_season_*` at lines 1188-1272; `CrossSeasonSummary` and `compute_cross_season_summary` imported at lines 18 and 44 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py:compute_cross_season_summary` | `engine.py:_velo_delta_string` | direct call for velocity YoY delta | WIRED | `_velo_delta_string(current_velo - prior_velo)` at line 2187 |
| `engine.py:compute_cross_season_summary` | `engine.py:_pplus_delta_string` | direct calls for P+/S+/L+ YoY deltas | WIRED | Three calls at lines 2188-2190 |
| `engine.py:compute_cross_season_summary` | `engine.py:_safe_metric` | baseline metric extraction | WIRED | Six calls at lines 2173-2179 for P+, S+, L+ from both baselines |
| `engine.py:compute_cross_season_summary` | `data.py:PitcherData` | function parameter type | WIRED | `def compute_cross_season_summary(data: PitcherData) -> CrossSeasonSummary | None:` at line 2149 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `CrossSeasonSummary` (velocity) | `velo_by_season` | `_per_season_velo(data.statcast)` groups statcast by `game_year`, filters to `_FASTBALL_TYPES`, computes `release_speed.mean()` | Yes — real Polars group_by aggregation | FLOWING |
| `CrossSeasonSummary` (P+/S+/L+) | `_safe_metric(data.season_baseline, "P+")` etc. | `data.season_baseline` DataFrame populated by `compute_season_baseline` in `data.py` from real CSV files | Yes — reads actual pitchingplus CSV output | FLOWING |
| `CrossSeasonSummary` (workload) | `workload` | `_per_season_workload(data.statcast, data.appearances)` counts outs via `_OUT_EVENTS`/`_DOUBLE_OUT_EVENTS` constants | Yes — real Polars aggregations over statcast events | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 7 cross-season tests pass | `uv run pytest tests/test_engine.py -x -q -k cross_season` | 7 passed, 84 deselected in 0.15s | PASS |
| Full test suite: no regressions | `uv run pytest tests/ -x -q` | 325 passed, 1 warning in 65.87s | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SDLT-01 | 20-01-PLAN.md | Engine computes YoY deltas for velocity, P+, S+, L+ | SATISFIED | `compute_cross_season_summary` extracts these from `season_baseline`, `prior_season_baseline`, and `statcast`; all values verified by `test_cross_season_summary_metrics` and `test_cross_season_velo_from_statcast` |
| SDLT-02 | 20-01-PLAN.md | YoY delta strings use same qualitative thresholds as within-season deltas | SATISFIED | Calls `_velo_delta_string` and `_pplus_delta_string` directly — no new delta functions added; `test_cross_season_delta_strings_match` verifies "Up"/"Down"/"Steady"/"mph"/"points"/"sharply" patterns |
| SDLT-03 | 20-01-PLAN.md | Cross-season summary is `None` when prior-season data is missing | SATISFIED | Guard at `engine.py:2164-2165`; `test_cross_season_none_single_season` confirms single-season path returns `None` |

No orphaned requirements: REQUIREMENTS.md maps exactly SDLT-01, SDLT-02, SDLT-03 to Phase 20, all claimed in the plan.

### Anti-Patterns Found

No anti-patterns detected in the phase-modified files. The `return None` at line 2165 is an intentional, guarded early exit (SDLT-03), not a stub. The `return {}` at line 476 in `_per_season_velo` is a correct empty-fastball guard. No TODO/FIXME/PLACEHOLDER comments found near new code.

### Human Verification Required

None. All goal-relevant behaviors are verifiable programmatically via the test suite and static analysis.

### Gaps Summary

No gaps. All four must-have truths verified, all artifacts exist and are substantive, all key links wired, all requirements satisfied. Test suite is green at 325/325 with no regressions.

---

_Verified: 2026-04-03_
_Verifier: Claude (gsd-verifier)_
