---
phase: 11-intermediate-probability-pipeline
verified: 2026-03-31T20:10:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 11: Intermediate Probability Pipeline Verification Report

**Phase Goal:** The data pipeline loads and surfaces per-pitch-type intermediate probabilities (both P and S variants) from pitchingplus aggregation CSVs so downstream tools can expose them.
**Verified:** 2026-03-31T20:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each pitch type has xSwing, xWhiff, xGOr, xPUr, xHR100, xSwSt, xRV100 intermediate probabilities with both P and S variants | VERIFIED | `IntermediateProbabilities` dataclass has all 7 metrics x 2 variants x 2 grains = 28 metric fields. `_INTERMEDIATE_P_COLS` and `_INTERMEDIATE_S_COLS` each have exactly 8 entries (including BBE_prob). `test_intermediate_p_and_s_variants` passes. |
| 2 | BBE_prob_P and BBE_prob_S are None (not present in aggregation CSVs) without crashing | VERIFIED | `bbe_prob_p: float | None` and `bbe_prob_s: float | None` defined in dataclass. `_bl` closure and `_weighted_window_metrics` both handle missing columns by returning None. `test_intermediate_bbe_prob_none` passes. |
| 3 | Location impact is computable as P minus S for any intermediate metric | VERIFIED | All P and S fields are `float | None`. `test_intermediate_location_impact` computes `xswing_p - xswing_s` and asserts `math.isfinite(delta)`. Passes. |
| 4 | Intermediate probabilities are available at both window and season grains | VERIFIED | Window values from `pitcher_type_appearance` grain via `_weighted_window_metrics`. Season values from `pitch_type_baseline` via `_bl` closure. Both sets of 16 fields present in dataclass. `test_intermediate_both_grains` passes. |
| 5 | Missing columns in CSVs produce None values, not exceptions | VERIFIED | `_weighted_window_metrics` returns None for missing columns. `_bl` closure guards with `col not in _row.columns`. `test_intermediate_missing_columns_graceful` passes. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/engine.py` | `IntermediateProbabilities` dataclass and `compute_intermediate_probabilities` function | VERIFIED | Dataclass at line 615 with 35 fields (pitch_type, pitch_name, 16 window, 16 season, n_pitches, small_sample, cold_start). Function at line 1541. Both in `__all__` at lines 31 and 48. `_INTERMEDIATE_P_COLS`, `_INTERMEDIATE_S_COLS`, `_INTERMEDIATE_COLS` constants at lines 398-410. |
| `src/pitcher_narratives/context.py` | `PitcherContext` with `intermediates` field wired from compute function | VERIFIED | `intermediates: list[IntermediateProbabilities]` field at line 66. `compute_intermediate_probabilities(data)[:_MAX_PITCH_TYPES]` call at line 494. `intermediates=intermediates` in constructor at line 515. |
| `tests/test_engine.py` | 6 test functions covering DATA-01, DATA-02, both grains, missing columns | VERIFIED | All 6 tests present at lines 893, 907, 916, 937, 954, 969. All 6 pass in 0.69s. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/pitcher_narratives/engine.py` | `_weighted_window_metrics` | `compute_intermediate_probabilities` calls `_weighted_window_metrics` with `_INTERMEDIATE_COLS` | WIRED | Line 1566-1570: `_weighted_window_metrics(data.agg_csvs["pitcher_type_appearance"], _INTERMEDIATE_COLS, ...)` |
| `src/pitcher_narratives/context.py` | `compute_intermediate_probabilities` | `assemble_pitcher_context` calls `compute_intermediate_probabilities(data)` | WIRED | Line 494: `intermediates = compute_intermediate_probabilities(data)[:_MAX_PITCH_TYPES]` |
| `src/pitcher_narratives/context.py` | `IntermediateProbabilities` | `PitcherContext.intermediates` field typed as `list[IntermediateProbabilities]` | WIRED | Line 66: `intermediates: list[IntermediateProbabilities]` with import confirmed at line 17 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `engine.py:compute_intermediate_probabilities` | `metrics` (window values) | `data.agg_csvs["pitcher_type_appearance"]` — polars DataFrame loaded from real CSV via `load_agg_csvs()` | Yes — `test_intermediate_probabilities_computed` asserts `any(item.xswing_p is not None ...)` | FLOWING |
| `engine.py:compute_intermediate_probabilities` | `_bl(col)` (season values) | `data.pitch_type_baseline` — weighted average computed from CSV by `compute_pitch_type_baseline()` in data.py | Yes — `test_intermediate_both_grains` asserts at least one item has both `season_xswing_p` and `xswing_p` not None | FLOWING |
| `context.py:PitcherContext.intermediates` | `intermediates` | `compute_intermediate_probabilities(data)` — real computation from CSV data | Yes — 245 tests pass including 6 new intermediate tests | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `IntermediateProbabilities` and `compute_intermediate_probabilities` importable from `pitcher_narratives.engine` | `uv run python -c "from pitcher_narratives.engine import IntermediateProbabilities, compute_intermediate_probabilities; print('OK')"` | `OK` | PASS |
| `PitcherContext` has `intermediates` field | `uv run python -c "from pitcher_narratives.context import PitcherContext; print([f for f in PitcherContext.model_fields if 'intermediate' in f])"` | `['intermediates']` | PASS |
| All 6 intermediate probability tests pass | `uv run pytest tests/test_engine.py::test_intermediate_* -x -q` | `6 passed in 0.69s` | PASS |
| Full test suite passes without regression | `uv run pytest tests/ -x -q` | `245 passed, 1 warning in 21.36s` | PASS |
| Lint clean on modified files | `uv run ruff check src/pitcher_narratives/engine.py src/pitcher_narratives/context.py` | `All checks passed!` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 11-01-PLAN.md | Analyst context includes per-pitch-type intermediate probabilities (xSwing, xWhiff, xGOr, xPUr, xHR100, BBE_prob) from pitchingplus aggregations | SATISFIED | `IntermediateProbabilities` includes all listed metrics (xswing, xwhiff, xgor, xpur, xhr100, bbe_prob) plus xswst and xrv100. Wired into `PitcherContext.intermediates` via `assemble_pitcher_context`. |
| DATA-02 | 11-01-PLAN.md | Analyst context includes P vs S variants of intermediates so location impact is quantifiable | SATISFIED | Every metric has `*_p` and `*_s` variants. `test_intermediate_location_impact` computes `xswing_p - xswing_s` and verifies it is a finite float. |

No orphaned requirements: REQUIREMENTS.md lines 70-71 confirm DATA-01 and DATA-02 map to Phase 11 and are marked Complete. No other Phase 11 requirements listed.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No TODO/FIXME/placeholder comments found in phase-modified files. No empty implementations. No hardcoded empty data flows to user-visible output. The `bbe_prob_p`/`bbe_prob_s` fields intentionally return None but this is documented behavior tested by `test_intermediate_bbe_prob_none`, not a stub.

### Human Verification Required

None. All goal criteria are verifiable programmatically and confirmed passing.

### Gaps Summary

No gaps. All 5 observable truths verified, all 3 artifacts fully substantive and wired, all 3 key links confirmed connected, real data flows through to PitcherContext, 245 tests pass, lint clean, both requirements satisfied.

The one notable design decision (BBE_prob_P/S columns included in the constant tuples even though they return None from current CSVs) is intentional and future-proofed: if pitchingplus agg CSVs are regenerated with these columns, they will be picked up automatically without code changes.

---

_Verified: 2026-03-31T20:10:00Z_
_Verifier: Claude (gsd-verifier)_
