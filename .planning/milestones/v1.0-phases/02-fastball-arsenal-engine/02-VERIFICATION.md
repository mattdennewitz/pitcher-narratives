---
phase: 02-fastball-arsenal-engine
verified: 2026-03-26T00:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification: null
gaps: []
human_verification: []
---

# Phase 2: Fastball Arsenal Engine Verification Report

**Phase Goal:** The system produces pre-computed fastball quality analysis and arsenal breakdown with deltas and qualitative trend strings ready for LLM consumption
**Verified:** 2026-03-26
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | `compute_fastball_summary` returns a `FastballSummary` dataclass with season vs window velocity and a qualitative delta string | VERIFIED | `FastballSummary` dataclass at engine.py:318; `compute_fastball_summary` at engine.py:476; spot-check: FC @ 86.8 mph, delta "Steady (-0.0)" |
| 2  | `FastballSummary` includes P+/S+/L+ season vs window with delta strings | VERIFIED | `season_p_plus`, `window_p_plus`, `p_plus_delta`, `season_s_plus`, `window_s_plus`, `s_plus_delta`, `season_l_plus`, `window_l_plus`, `l_plus_delta` fields present; `test_fastball_pplus_delta` and `test_fastball_splus_lplus` pass |
| 3  | `FastballSummary` includes pfx_x/pfx_z movement deltas with qualitative strings | VERIFIED | `season_pfx_x`, `window_pfx_x`, `pfx_x_delta`, `season_pfx_z`, `window_pfx_z`, `pfx_z_delta` present; `test_fastball_movement_delta` passes |
| 4  | `compute_velocity_arc` returns early vs late inning velo comparison or single-inning fallback | VERIFIED | engine.py:590; test pitcher returns `available=False`, `drop_string='Single inning -- no velocity arc available'`; spot-check confirmed |
| 5  | Primary fastball identified as highest-usage FF/SI/FC from `pitch_type_baseline` | VERIFIED | `_identify_primary_fastball` at engine.py:141; `_FASTBALL_TYPES = frozenset({"FF", "SI", "FC"})` at engine.py:34; returns "FC" for test pitcher (77 pitches); `test_identify_primary_fastball` passes |
| 6  | Cold start pitchers get "Full season in window" trend strings instead of zero deltas | VERIFIED | `_COLD_START_STRING = "Full season in window -- no trend comparison"` at engine.py:58; applied across velo, P+/S+/L+, and movement when `_is_cold_start` is True; `test_cold_start_fallback` and `test_cold_start_arsenal` pass |
| 7  | Small sample (<10 pitches) is flagged but results are still included | VERIFIED | `_MIN_PITCHES = 10` at engine.py:55; `small_sample` bool on both `FastballSummary` and `PitchTypeSummary`; `test_small_sample_flag` and `test_arsenal_small_sample` pass |
| 8  | `compute_arsenal_summary` returns a list of `PitchTypeSummary` ordered by season usage descending | VERIFIED | engine.py:661; results.sort at engine.py:771; arsenal[0].pitch_type == "FC" confirmed in spot-check; `test_arsenal_ordering` passes |
| 9  | Each `PitchTypeSummary` has usage rate season vs window with qualitative delta string | VERIFIED | `season_usage_pct`, `window_usage_pct`, `usage_delta` fields; `_usage_delta_string` helper; `test_usage_rate_deltas` passes; total usage sums to 100.0% |
| 10 | Each `PitchTypeSummary` has P+/S+/L+ season vs window with delta strings | VERIFIED | Full P+/S+/L+ fields with window values from `_weighted_window_pplus`; `test_arsenal_pplus_deltas` passes |
| 11 | `compute_platoon_mix` returns platoon-split usage rates with deltas for same vs opposite hand | VERIFIED | engine.py:775; `PlatoonMix` with `PlatoonSplit` list; `_stand_to_platoon` helper; `test_platoon_mix_shifts` passes |
| 12 | Platoon mix handles missing combinations (e.g., CH only thrown to opposite side) | VERIFIED | CH same-side returns `available=False`, `usage_delta="Not thrown to same-side batters"`; confirmed by spot-check and `test_platoon_missing_combo` |
| 13 | Small sample (<10 pitches) is flagged per pitch type but still included | VERIFIED | `small_sample` bool on `PitchTypeSummary`; `n_pitches_window < _MIN_PITCHES`; `test_arsenal_small_sample` passes |
| 14 | `compute_first_pitch_weaponry` returns first-pitch type distribution with window vs season delta | VERIFIED | engine.py:904; `pitch_number == 1` filter; `FirstPitchWeaponry` with `FirstPitchEntry` list; 42 total first pitches validated; `test_first_pitch_weaponry`, `test_first_pitch_count`, `test_first_pitch_ordering` all pass |

**Score:** 14/14 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `engine.py` | Fastball quality engine with delta helpers and dataclasses | VERIFIED | 977 lines; substantive implementation with 7 dataclasses, 5 public functions, 8 private helpers |
| `engine.py` — `class FastballSummary` | FastballSummary dataclass | VERIFIED | Exists at line 318; 20 fields including all required velocity/P+/movement fields |
| `engine.py` — `def compute_velocity_arc` | VelocityArc computation | VERIFIED | Exists at line 590; handles both multi-inning and single-inning paths |
| `engine.py` — `class PitchTypeSummary` | Arsenal dataclass | VERIFIED | Exists at line 379; 16 fields including usage, P+/S+/L+, small_sample, cold_start |
| `engine.py` — `def compute_platoon_mix` | Platoon mix analysis | VERIFIED | Exists at line 775; handles missing combos with `available=False` |
| `engine.py` — `def compute_first_pitch_weaponry` | First-pitch weaponry analysis | VERIFIED | Exists at line 904; filters on `pitch_number == 1` |
| `tests/test_engine.py` | Tests for all requirements and edge cases | VERIFIED | 443 lines; 35 tests; all pass in 2.33s |

---

### Key Link Verification

**Plan 01 key links:**

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py` | `data.py` | `from data import PitcherData` | WIRED | Line 15 of engine.py |
| `engine.py` | `data.py` | uses `pitch_type_baseline` for primary fastball ID | WIRED | `_identify_primary_fastball(data.pitch_type_baseline)` at line 490 |
| `tests/test_engine.py` | `engine.py` | imports engine functions | WIRED | Lines 11-30: all public and private helpers imported |

**Plan 02 key links:**

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py` (arsenal) | `engine.py` (delta helpers) | reuses `_usage_delta_string` | WIRED | `_usage_delta_string` called at lines 713, 858, 956 |
| `engine.py` (platoon) | `data.py PitcherData.agg_csvs` | reads `pitcher_type_platoon` CSV | WIRED | `data.agg_csvs["pitcher_type_platoon"]` at line 807 |
| `engine.py` (first_pitch) | `data.py PitcherData.statcast` | filters `pitch_number == 1` | WIRED | Line 928: `data.statcast.filter(pl.col("pitch_number") == 1)` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `compute_fastball_summary` | `season_velo`, `window_velo` | `data.statcast.filter(pitch_type == primary)["release_speed"].mean()` | Yes — Polars mean over real pitch rows | FLOWING |
| `compute_fastball_summary` | `season_p_plus` | `data.pitch_type_baseline` (n_pitches-weighted CSV aggregation) | Yes — from `pitcher_type.csv` grain | FLOWING |
| `compute_fastball_summary` | `window_p_plus` | `_weighted_window_pplus(data.agg_csvs["pitcher_type_appearance"], ...)` | Yes — filters to window dates, weighted average | FLOWING |
| `compute_arsenal_summary` | usage rates | `len(data.statcast.filter(pitch_type == pt)) / total * 100.0` | Yes — pitch count from real Statcast rows | FLOWING |
| `compute_platoon_mix` | platoon splits | `_compute_platoon_baseline(data.agg_csvs["pitcher_type_platoon"])` + statcast with `platoon_matchup` column | Yes — real CSV data + statcast batter-hand column | FLOWING |
| `compute_first_pitch_weaponry` | first-pitch counts | `data.statcast.filter(pitch_number == 1)` | Yes — 42 first pitches confirmed against known at-bat count | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Primary fastball is FC for test pitcher (592155) | `compute_fastball_summary(data).pitch_type` | "FC" | PASS |
| Velocity is in MLB range | `fb.season_velo` | 86.8 mph | PASS |
| velo_delta contains qualitative vocabulary | `'Steady' in fb.velo_delta` | "Steady (-0.0)" | PASS |
| Arsenal ordered FC first by season usage | `arsenal[0].pitch_type` | "FC" | PASS |
| Usage rates sum to 100% | `sum(p.season_usage_pct for p in arsenal)` | 100.0% | PASS |
| CH same-side returns available=False | `ch_same[0].available` | False | PASS |
| CH same-side delta string | `ch_same[0].usage_delta` | "Not thrown to same-side batters" | PASS |
| Total first pitches matches at-bat count | `fpw.total_first_pitches_season` | 42 | PASS |
| Velocity arc single-inning fallback | `arc.available, arc.drop_string` | False, "Single inning -- no velocity arc available" | PASS |
| Cold start string propagates to all delta fields | `'Full season in window' in fb.velo_delta` | True | PASS |
| Import contract — all public API | `from engine import ...` all 12 public names | "All public imports OK" | PASS |

All behavioral spot-checks: 11/11 PASS

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FB-01 | 02-01 | Season vs window average fastball velocity | SATISFIED | `season_velo`, `window_velo`, `velo_delta` on `FastballSummary`; spot-check: 86.8 mph |
| FB-02 | 02-01 | P+/S+/L+ for primary fastball: season vs window with delta | SATISFIED | All six P+/S+/L+ fields on `FastballSummary` with delta strings; `test_fastball_pplus_delta` passes |
| FB-03 | 02-01 | Movement deltas (pfx_x/pfx_z) for fastball | SATISFIED | `season_pfx_x/z`, `window_pfx_x/z`, `pfx_x_delta/z_delta` on `FastballSummary`; `test_fastball_movement_delta` passes |
| FB-04 | 02-01 | Within-game velocity arc analysis (early vs late innings) | SATISFIED | `compute_velocity_arc` returns `VelocityArc` with `early_velo`, `late_velo`, `drop`, `drop_string`; single-inning fallback confirmed |
| ARSL-01 | 02-02 | Usage rate per pitch type with delta vs season baseline | SATISFIED | `season_usage_pct`, `window_usage_pct`, `usage_delta` on every `PitchTypeSummary`; total = 100.0% |
| ARSL-02 | 02-02 | P+/S+/L+ per pitch type: season vs window with delta | SATISFIED | Full P+/S+/L+ fields on `PitchTypeSummary`; `test_arsenal_pplus_deltas` passes |
| ARSL-03 | 02-02 | Platoon mix shifts (usage changes by batter handedness) | SATISFIED | `compute_platoon_mix` returns `PlatoonMix` with per-(pitch_type, side) `PlatoonSplit` entries; missing combo handled |
| ARSL-04 | 02-02 | First-pitch strike weaponry analysis | SATISFIED | `compute_first_pitch_weaponry` with `pitch_number == 1` filter; 42 at-bat first pitches confirmed; ordered by `window_pct` desc |

All 8 requirements: SATISFIED. No orphaned requirements.

---

### Anti-Patterns Found

None detected. Scan results:
- No TODO/FIXME/HACK/placeholder comments in `engine.py`
- No empty `return null / return {} / return []` stubs
- No print statements
- No hardcoded empty data arrays passed to rendering paths
- No disconnected props

---

### Human Verification Required

None. All aspects of this phase are programmatically verifiable:
- All computations are pure mathematical transformations of static Parquet/CSV data
- Qualitative strings are generated deterministically from thresholds
- No UI, no real-time behavior, no external service integration

---

### Gaps Summary

No gaps. The phase goal is fully achieved.

The system now produces pre-computed fastball quality analysis (`FastballSummary`) and complete arsenal breakdown (`PitchTypeSummary`, `PlatoonMix`, `FirstPitchWeaponry`) with season-vs-window deltas and qualitative trend strings across all dimensions: velocity, movement, P+/S+/L+, usage rates, platoon splits, and first-pitch distribution. All data flows from real Statcast parquet and Pitching+ CSV sources through Polars computation. Cold start detection and small sample flagging prevent the LLM from receiving misleading zero-delta signals. All 60 tests pass including 35 engine-specific tests against real pitcher data.

---

_Verified: 2026-03-26_
_Verifier: Claude (gsd-verifier)_
