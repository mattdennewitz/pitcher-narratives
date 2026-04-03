---
status: passed
phase: 19
phase_name: Cross-Season Baseline Exposure
score: 3/3
verified: 2026-04-03
---

# Phase 19: Cross-Season Baseline Exposure — Verification

## Goal
Engine functions can access both current-season and prior-season baselines for any pitcher.

## Must-Haves Verification

### XSBL-01: PitcherData exposes prior-season baselines
**Status:** PASSED

Evidence:
- `data.py:88` — `prior_season_baseline: pl.DataFrame` field on PitcherData dataclass
- `data.py:89` — `prior_pitch_type_baseline: pl.DataFrame` field on PitcherData dataclass
- `data.py:440` — `prior_season_baseline = season_baseline_all.filter(pl.col("season") < max_season)` populates prior-season data
- `data.py:448-449` — `prior_pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") < max_season)` populates prior pitch-type data
- `data.py:464-465` — Both fields passed to PitcherData constructor

### XSBL-02: load_pitcher_data() retains all per-season baseline rows
**Status:** PASSED

Evidence:
- `data.py:416-417` — `season_baseline_all` and `pitch_type_baseline_all` computed from full multi-year data before any filtering
- `data.py:435` — max season filter applied only to `season_baseline` (current), not to the `_all` variants
- `data.py:440` — Prior seasons extracted via `< max_season` filter on the `_all` data
- Tests: `test_prior_season_baseline_multi_year`, `test_prior_pitch_type_baseline_multi_year` verify both seasons accessible

### XSBL-03: Prior-season baselines are empty DataFrames for single-season pitchers
**Status:** PASSED

Evidence:
- `data.py:443` — `prior_season_baseline = season_baseline_all.clear()` when only one season exists
- `data.py:453` — `prior_pitch_type_baseline = pitch_type_baseline_all.clear()` when only one season exists
- `.clear()` returns an empty DataFrame with identical schema (not None, not crash)
- Tests: `test_prior_baseline_empty_single_season`, `test_single_season_no_crash` verify empty DataFrame behavior

## Regression Check

- 318 tests passing (full suite)
- 47 data tests passing (module-level)
- 8 new XSBL tests all green
- No existing tests modified

## Automated Checks

```
uv run pytest tests/ -x -q
# 318 passed in 67.17s
```

## Summary

All 3 must-haves verified against the actual codebase. Phase goal achieved: engine functions can access both current-season and prior-season baselines for any pitcher.
