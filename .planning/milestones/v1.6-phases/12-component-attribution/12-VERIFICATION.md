---
phase: 12-component-attribution
verified: 2026-03-31T22:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 12: Component Attribution Verification Report

**Phase Goal:** Each pitch type's xRV is decomposed into 13 additive outcome contributions, showing which outcomes (whiffs, HRs, ground outs, etc.) drive the overall score
**Verified:** 2026-03-31T22:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Combined must-haves from Plan 01 and Plan 02.

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | RV_df.csv is present in aggs/ with 156 rows (12 counts x 13 outcomes) | VERIFIED | `aggs/RV_df.csv` confirmed 156 rows, columns: balls, strikes, model_classes, delta_run_exp, n_observations |
| 2  | all_pitches.csv contains all 13 P-variant and 13 S-variant outcome probability columns | VERIFIED | 13/13 P-variant present, 13/13 S-variant present (95,107 rows) |
| 3  | The 13 per-pitch probabilities sum to approximately 1.0 for each row | VERIFIED | Confirmed by test_component_attribution_sum: sum of 13 contributions == total_xrv100 within 0.01 abs tolerance |
| 4  | Each pitch type has 13 outcome-level xRV contributions computed as mean(probability x run_value) x 100 | VERIFIED | compute_component_attribution produces 13 OutcomeContribution per pitch type; FC (Cutter): 13 outcomes, total=-0.90 |
| 5  | The 13 contributions sum to the raw xRV100 total within floating-point tolerance | VERIFIED | Behavioral spot-check: diff=0.000000 for FC; test_component_attribution_sum passes |
| 6  | Each contribution is labeled with its outcome name (HBP, called_ball, called_strike, whiff, foul, double, ground_out, home_run, line_out, low_line_out, pop_out, single, triple) | VERIFIED | test_component_attribution_labels passes; 13 canonical labels match exactly |
| 7  | Attribution is available at pitcher+type grain (season aggregate) | VERIFIED | test_component_attribution_pitcher_type_grain passes; n_pitches matches full season count per type |
| 8  | Attribution is available at pitcher+type+appearance grain (per-game) | VERIFIED | test_component_attribution_appearance_grain passes; n_pitches matches filtered game_pk count |
| 9  | ComponentAttribution is accessible via PitcherContext for downstream tools | VERIFIED | PitcherContext.attributions field wired in context.py; assemble_pitcher_context returns populated list capped at 4 pitch types |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `aggs/RV_df.csv` | Run values lookup table (156 rows) | VERIFIED | 156 rows, columns: balls, strikes, model_classes, delta_run_exp, n_observations |
| `aggs/2026-all_pitches.csv` | Per-pitch data with all 13 P/S outcome probability columns | VERIFIED | 95,107 rows, 81 columns; HBP_P and all 12 others present |
| `src/pitcher_narratives/data.py` | load_run_values() and RV_DF_PATH in public API | VERIFIED | RV_DF_PATH and load_run_values in __all__; function returns pl.DataFrame with 156 rows |
| `src/pitcher_narratives/engine.py` | OutcomeContribution, ComponentAttribution dataclasses, compute_component_attribution function | VERIFIED | All three in __all__; full implementation at lines 692-2357 |
| `src/pitcher_narratives/context.py` | PitcherContext.attributions field wired to compute_component_attribution | VERIFIED | attributions: list[ComponentAttribution] field present; assemble_pitcher_context calls compute_component_attribution(data)[:_MAX_PITCH_TYPES] |
| `tests/test_engine.py` | 7 test functions covering component attribution | VERIFIED | test_component_attribution_{13_outcomes,sum,labels,sorted_by_magnitude,pitcher_type_grain,appearance_grain,pitch_names} — all 7 pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `aggs/RV_df.csv` | `engine.py compute_component_attribution` | polars join on [balls, strikes, model_classes] | WIRED | Line 2313: `joined = long.join(rv_df.select([...]), on=["balls", "strikes", "model_classes"], how="inner")` |
| `aggs/2026-all_pitches.csv` | `engine.py compute_component_attribution` | unpivot 13 probability columns, compute p_i * delta_run_exp | WIRED | Lines 2303-2310: unpivot on _OUTCOME_COLS_P, variable_name="outcome_col"; pattern _OUTCOME_COLS_P defined at line 416 |
| `src/pitcher_narratives/context.py` | `src/pitcher_narratives/engine.py` | import and call compute_component_attribution | WIRED | Lines 28, 499: ComponentAttribution and compute_component_attribution imported; `attributions = compute_component_attribution(data)[:_MAX_PITCH_TYPES]` called |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `context.py PitcherContext.attributions` | attributions list | compute_component_attribution(data) | Yes — reads agg_csvs["all_pitches"] joined with RV_df.csv DB rows; behavioral spot-check confirmed non-empty list with real contribution values | FLOWING |
| `engine.py compute_component_attribution` | all_pitches DataFrame | data.agg_csvs["all_pitches"] (95,107 rows, loaded from CSV) | Yes — live CSV data, not static; game_pk filter works for appearance grain | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| PitcherContext.attributions returns 13 outcomes with real values | assemble_pitcher_context(load_pitcher_data(592155)).attributions[0] | FC (Cutter): 13 outcomes, total=-0.90, n=44 | PASS |
| Contributions sum to total_xrv100 | sum(contributions) vs total_xrv100 | diff=0.000000 | PASS |
| Top contributors have expected outcome names | a.contributions[:3] | called_ball: 1.757, single: 1.408, home_run: 1.323 | PASS |
| Full test suite passes | uv run pytest tests/ -x -q | 252 passed, 1 warning in 19.82s | PASS |
| Attribution-specific tests | uv run pytest tests/test_engine.py -k component_attribution | 7 passed, 77 deselected in 0.71s | PASS |
| Lint clean | uv run ruff check engine.py context.py data.py | All checks passed! | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DATA-03 | 12-01-PLAN.md, 12-02-PLAN.md | xRV is decomposed into 13 outcome-level contributions (probability x run_value per outcome) per pitch type | SATISFIED | compute_component_attribution implements the exact decomposition; PitcherContext.attributions exposes it for downstream tools (Phase 13 TOOL-02) |

**Orphaned requirements check:** REQUIREMENTS.md maps DATA-03 to Phase 12. No other requirements are mapped to Phase 12. No orphaned requirements.

### Anti-Patterns Found

No anti-patterns detected.

Scanned files: engine.py (compute_component_attribution), context.py (assemble_pitcher_context), data.py (load_run_values), tests/test_engine.py.

- No TODO/FIXME/placeholder comments in modified code
- No empty return values (compute_component_attribution returns [] only when outcome columns are missing — this is correct guarded behavior, not a stub)
- No hardcoded data props; all data flows through live CSV loading
- No orphaned functions; all three new symbols are imported by context.py and/or tests

### Human Verification Required

None. All acceptance criteria are programmatically verifiable and passed.

### Gaps Summary

No gaps. All must-haves from both plans are satisfied:

- Plan 01 data prerequisites: RV_df.csv (156 rows), all_pitches.csv (13 P + 13 S columns), load_run_values() wired into data.py public API.
- Plan 02 implementation: OutcomeContribution and ComponentAttribution dataclasses substantively implemented; compute_component_attribution handles both season and appearance grains via game_pk parameter; PitcherContext.attributions wired and capped at 4 pitch types; 7 TDD tests all pass; 252 total tests pass; lint clean.

The phase goal is fully achieved. Each pitch type's xRV is decomposed into exactly 13 additive outcome contributions (probability x count-specific run value x 100), labeled with canonical outcome names, sortable by magnitude, and accessible via PitcherContext.attributions for Phase 13 tool implementations.

---

_Verified: 2026-03-31T22:00:00Z_
_Verifier: Claude (gsd-verifier)_
