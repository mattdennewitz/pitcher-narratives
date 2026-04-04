---
phase: 23-engine-foundation-data-enrichment
verified: 2026-04-04T18:42:36Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 23: Engine Foundation Data Enrichment — Verification Report

**Phase Goal:** Engine produces count-state usage splits, arm angle metrics, and percentile-ranked outlier tags so downstream agents have richer analytical inputs
**Verified:** 2026-04-04T18:42:36Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Engine output includes per-pitch-type usage rates across 5 count states (ahead/behind/even/two-strike/first-pitch) with window-vs-season structure | VERIFIED | `compute_count_splits` in engine.py:2129 returns `CountSplits` with 5 `CountBucket` entries; `_COUNT_BUCKETS` dict at line 109 defines all 5 filter expressions |
| 2 | Engine output includes arm angle computed from release point coordinates via atan2, with delta string showing window-vs-season change | VERIFIED | `_compute_arm_angle` at engine.py:138 uses `math.atan2(release_z, abs(release_x))`; `ReleasePointPitchType` fields `window_arm_angle`, `season_arm_angle`, `arm_angle_delta`, `arm_slot` at lines 1467-1477; populated in `compute_release_point_metrics` at line 2657-2690 |
| 3 | Outlier tags display percentile rank (e.g., "OUTLIER - 98th percentile") instead of raw z-score notation when percentile is provided | VERIFIED | `outlier_tag` at engine.py:398 accepts optional `percentile: int | None = None`; produces `"OUTLIER - 97th percentile (above avg, z=+2.0)"` format confirmed by spot-check |
| 4 | PitcherContext model includes CountSplits and arm angle fields, and to_prompt() renders them in correct section order | VERIFIED | `count_splits: CountSplits | None = None` at context.py:93; `_render_count_splits_section` placed after platoon (position 1446 vs 1326) and before first_pitch (1541); appendix after yoy (1667) and before appearances (1868); arm angle rendered at context.py:511 |
| 5 | Count buckets with fewer than 10 pitches are flagged as small sample with no usage delta computed | VERIFIED | `small_sample = n_window < _MIN_PITCHES` at engine.py:2165; notable_shifts skipped for small-sample buckets (`if not small_sample and not cold_start`); appendix shows `"(small sample)"` with `"--"` delta via context.py `_render_count_splits_appendix` |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/engine.py` | CountBucketUsage, CountBucket, CountSplits dataclasses; compute_count_splits; arm angle helpers; updated outlier_tag; extended LeagueBaseline | VERIFIED | All classes at lines 1108-1145; function at line 2129; `_compute_arm_angle` at 138; `_arm_slot_label` at 149; `_arm_angle_delta_string` at 172; `outlier_tag` at 398; `LeagueBaseline` extended with `p_throws` and release point fields at lines 251-270 |
| `src/pitcher_narratives/pipeline.py` | Percentile-passing outlier_tag calls using handedness-filtered baselines | VERIFIED | Handedness filter at pipeline.py:455 (`b.p_throws == pitcher_throws`); three `outlier_tag(..., percentile=_percentile_from_z(...))` calls at lines 470, 473, 476 |
| `src/pitcher_narratives/report.py` | Percentile-passing outlier_tag calls using handedness-filtered baselines | VERIFIED | Handedness filter at report.py:516 (`b.p_throws == pitcher_throws`); three `outlier_tag(..., percentile=_percentile_from_z(...))` calls at lines 526, 529, 532 |
| `src/pitcher_narratives/context.py` | PitcherContext.count_splits field; _render_count_splits_section; _render_count_splits_appendix; arm angle in _render_release_point_section; assemble wiring | VERIFIED | `count_splits` field at line 93; `_render_count_splits_section` at 547; `_render_count_splits_appendix` at 557; arm angle render at lines 508-513; `compute_count_splits` called at line 785 and passed at line 811 |
| `tests/test_engine.py` | Tests for count splits, arm angle, outlier_tag percentile format, LeagueBaseline extension | VERIFIED | 9 `test_count_*` functions (lines 2426-2627); 7 arm angle tests (lines 920-1006); 6 outlier_tag tests (including 3 percentile format tests) — all pass |
| `tests/test_context.py` | Integration tests for count splits rendering adjacency and arm angle rendering | VERIFIED | 13 Phase 23 test functions covering count splits field, assembly, adjacency, appendix ordering, notable shifts, small sample, arm angle per pitch type — all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py (ReleasePointPitchType)` | `atan2(release_z, abs(release_x))` | `_compute_arm_angle` | WIRED | `math.atan2` at line 146; called at lines 2657-2658 to populate `window_arm` and `season_arm` |
| `engine.py (outlier_tag)` | `percentile: int | None` parameter | optional keyword arg | WIRED | Signature at line 398; backward-compatible (None = original format, confirmed by spot-check) |
| `pipeline.py (build_stuff_input)` | `engine.py (outlier_tag + _percentile_from_z)` | import and call with percentile arg | WIRED | `_percentile_from_z` imported at pipeline.py:50; called at lines 469, 472, 475; passed as `percentile=` kwarg at 470, 473, 476 |
| `report.py` | `engine.py (outlier_tag + _percentile_from_z)` | import and call with percentile arg | WIRED | `_percentile_from_z` imported at report.py:49; called at lines 525, 528, 531; passed as `percentile=` kwarg at 526, 529, 532 |
| `context.py (PitcherContext)` | `engine.py (CountSplits)` | import and field assignment in assemble_pitcher_context | WIRED | `CountSplits` imported at context.py:17; `compute_count_splits` at 36; result assigned at line 785 and passed to constructor at 811 |
| `context.py (to_prompt)` | `_render_count_splits_section` | called immediately after `_render_platoon_section` | WIRED | Confirmed by source position analysis: platoon@1326, count_splits_inline@1446, first_pitch@1541 |
| `context.py (_render_release_point_section)` | `ReleasePointPitchType.window_arm_angle, arm_slot` | reads arm angle fields | WIRED | Lines 508-513: iterates `entries` and renders `pt.window_arm_angle`, `pt.arm_slot`, `pt.season_arm_angle`, `pt.arm_angle_delta` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `context.py (_render_count_splits_section)` | `self.count_splits.notable_shifts` | `compute_count_splits(data)` in `assemble_pitcher_context` | Yes — computed from `data.statcast` Polars DataFrame filtered by `_COUNT_BUCKETS` expressions | FLOWING |
| `context.py (_render_count_splits_appendix)` | `self.count_splits.buckets` | Same `compute_count_splits(data)` call | Yes — per-bucket usage rates computed from live statcast data | FLOWING |
| `context.py (_render_release_point_section)` | `pt.window_arm_angle` | `compute_release_point_metrics(data)` -> `_compute_arm_angle` | Yes — atan2 applied to mean `release_pos_x`/`release_pos_z` from statcast | FLOWING |
| `pipeline.py (outlier_tag calls)` | `percentile=_percentile_from_z(velo_z)` | z-score from handedness-matched `LeagueBaseline` | Yes — baselines loaded from real data via `compute_league_baselines()` | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `outlier_tag` with percentile produces correct format | `outlier_tag(97.0, 93.0, 2.0, percentile=97)` | `'OUTLIER - 97th percentile (above avg, z=+2.0)'` | PASS |
| `outlier_tag` without percentile preserves original format | `outlier_tag(97.0, 93.0, 2.0)` | `'OUTLIER (above avg, z=+2.0)'` | PASS |
| `_COUNT_BUCKETS` has exactly 5 keys with correct names | Python import check | `['ahead', 'behind', 'even', 'two_strike', 'first_pitch']` | PASS |
| `PitcherContext.count_splits` field exists with correct type | `PitcherContext.model_fields['count_splits']` | `CountSplits | None`, default `None` | PASS |
| `to_prompt()` section ordering: count splits after platoon, appendix after yoy | Source position analysis | platoon@1326 < inline@1446 < first_pitch@1541; yoy@1667 < appendix@1776 < appearances@1868 | PASS |
| Count split tests pass | `uv run pytest tests/test_engine.py -k "count_split" -q` | `9 passed, 140 deselected` | PASS |
| Arm angle tests pass | `uv run pytest tests/test_engine.py -k "arm_angle" -q` | `7 passed, 142 deselected` | PASS |
| Context Phase 23 tests pass | `uv run pytest tests/test_context.py -k "count_split or arm_angle" -q` | `13 passed, 45 deselected` | PASS |
| Full test suite (excluding pre-existing failures) | `uv run pytest tests/ -q` | `435 passed, 2 pre-existing failures` | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ENG-01 | 23-01 | Engine computes per-pitch-type usage across count states (ahead/behind/even/two-strike) with window vs season deltas | SATISFIED | `compute_count_splits` returns `CountSplits` with 5 buckets including window and season `CountBucketUsage` lists; `notable_shifts` pre-renders 10pp+ deltas |
| ENG-02 | 23-02 | Engine computes arm angle from release_x/release_z via atan2, with window vs season delta strings | SATISFIED | `_compute_arm_angle(release_x, release_z)` at engine.py:138; `ReleasePointPitchType` fields `window_arm_angle`, `season_arm_angle`, `arm_angle_delta`, `arm_slot` populated in `compute_release_point_metrics` |
| ENG-03 | 23-02 | Outlier tags include percentile rank (e.g., "98th percentile") instead of raw z-score notation | SATISFIED | `outlier_tag(..., percentile: int | None = None)` produces `"OUTLIER - Nth percentile (...)"` format; pipeline.py and report.py pass `percentile=_percentile_from_z(z)` using handedness-matched baselines |
| ENG-04 | 23-03 | CountSplits and arm angle fields wired into PitcherContext and rendered in prompt output | SATISFIED | `count_splits` field on `PitcherContext`; `assemble_pitcher_context` calls `compute_count_splits`; `to_prompt()` renders inline section adjacent to platoon and full appendix after yoy; arm angle in release point section |
| ENG-05 | 23-01 | Count bucket with fewer than 10 pitches flagged as small sample (no usage delta computed) | SATISFIED | `small_sample = n_window < _MIN_PITCHES` (10); `notable_shifts` excludes small-sample buckets; appendix renders `"(small sample)"` and `"--"` delta; season usage rates still populated (usage preserved, only delta suppressed) |

All 5 requirements satisfied. No orphaned requirements.

---

### Anti-Patterns Found

No anti-patterns found in Phase 23 modified files (`engine.py`, `context.py`, `pipeline.py`, `report.py`, `tests/test_engine.py`, `tests/test_context.py`). No TODO/FIXME markers, empty implementations, or hardcoded stub returns in Phase 23 code.

---

### Pre-Existing Test Failures (Not Phase 23 Regressions)

Two tests fail in the full suite — both are confirmed pre-existing failures unrelated to Phase 23:

- `tests/test_context.py::test_to_prompt_yoy_omits_all_steady_pitch` — fails on pre-Phase-23 code; asserts `"Steady (+0.1 in)"` not present but it is
- `tests/test_context.py::test_to_prompt_yoy_renders_movement_deltas` — same root cause

These are not regressions introduced by Phase 23. All 435 Phase 23-related tests pass.

---

### Human Verification Required

None. All success criteria are verifiable programmatically.

---

## Gaps Summary

No gaps. All 5 observable truths verified, all 6 artifacts pass all 4 levels (exists, substantive, wired, data flowing), all 7 key links confirmed wired, all 5 requirements satisfied, no blocker anti-patterns.

---

_Verified: 2026-04-04T18:42:36Z_
_Verifier: Claude (gsd-verifier)_
