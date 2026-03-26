---
phase: 01-data-pipeline-classification
verified: 2026-03-26T19:15:00Z
status: passed
score: 15/15 must-haves verified
gaps: []
human_verification:
  - test: "Confirm ROLE-02 scoping intent in REQUIREMENTS.md"
    expected: "ROLE-02 'Report structure adapts based on detected role' is partially satisfied — role detection and data availability is complete, but the actual report structure adaptation is Phase 4 work. REQUIREMENTS.md marking it complete in Phase 1 may be intentional (partial/foundational credit) or a tracking error."
    why_human: "Requirements traceability call — only the product owner can confirm whether 'complete' in REQUIREMENTS.md means 'foundation laid' or 'fully delivered'."
---

# Phase 1: Data Pipeline & Classification Verification Report

**Phase Goal:** User can run the CLI with a pitcher ID and get validated, pitcher-scoped data with correct role classification
**Verified:** 2026-03-26T19:15:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria + PLAN must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `python main.py -p <pitcher_id>` loads Statcast parquet and Pitching+ CSVs without error | VERIFIED | CLI exits 0, output: "Booser, Cam (LHP) \| 12 appearances (11 in 30d window) \| Roles: RP, SP" |
| 2 | `-w <days>` filters to specified lookback window; omitting uses 30-day default | VERIFIED | `-w 7` produces "3 in 7d window"; no -w gives "11 in 30d window" |
| 3 | Each appearance classified SP/RP; pitcher with both roles gets correct per-appearance classification | VERIFIED | 1 SP (first_inning=1) + 11 RP (all first_inning > 1); roles=['RP', 'SP'] confirmed |
| 4 | Season-level baselines computed and accessible | VERIFIED | season_baseline=1 row (n_pitches=172), pitch_type_baseline=4 rows |
| 5 | load_statcast returns polars DataFrame filtered to single pitcher ID | VERIFIED | `df["pitcher"].unique().to_list() == [592155]` — test passes |
| 6 | Invalid pitcher ID raises ValueError with "Pitcher {id} not found" | VERIFIED | `uv run python main.py -p 9999999` → stderr "Pitcher 9999999 not found", exit 1 |
| 7 | All 8 CSV aggregation files load and filter to pitcher without error | VERIFIED | agg_csvs keys: pitcher, pitcher_type, pitcher_type_platoon, team, pitcher_appearance, pitcher_type_appearance, pitcher_type_platoon_appearance, all_pitches |
| 8 | CSV game_date columns parsed to polars Date type, not String | VERIFIED | `appearances["game_date"].dtype = Date`, `agg_csvs["pitcher_appearance"]["game_date"].dtype = Date` |
| 9 | Season baselines use n_pitches-weighted averaging | VERIFIED | compute_season_baseline uses `(col * n_pitches).sum() / n_pitches.sum()` — single row with n_pitches=172 |
| 10 | Each appearance classified SP (first_inning==1) or RP (first_inning>1) | VERIFIED | test_classify_starter and test_classify_reliever both pass; verified programmatically |
| 11 | Swingman with both start and relief gets correct per-appearance classification | VERIFIED | Booser: 1 SP + 11 RP; `roles == ["RP", "SP"]` — test_swingman_classification passes |
| 12 | Window filtering uses max date in dataset, not date.today() | VERIFIED | `max_date=2026-03-24`, `date.today()=2026-03-26` — confirmed not equal; `df["game_date"].max()` used in filter_to_window |
| 13 | CLI accepts -p (required int) and -w (optional int, default 30) | VERIFIED | parse_args unit tests pass; argparse.ArgumentParser with -p required=True, -w default=30 |
| 14 | Missing -p shows usage help and exits 2 | VERIFIED | `uv run python main.py` → exit 2, "usage: main.py [-h] -p PITCHER [-w WINDOW]" on stderr |
| 15 | Role column accessible for downstream use | VERIFIED | `pitcher_data.appearances["role"]` accessible; CLI output shows "Roles: RP, SP" |

**Score:** 15/15 truths verified

---

### Required Artifacts

| Artifact | Expected | Min Lines | Actual Lines | Status | Details |
|----------|----------|-----------|--------------|--------|---------|
| `data.py` | All data loading, classification, baseline, filtering functions | — | 273 | VERIFIED | Exports load_statcast, load_agg_csvs, classify_appearances, compute_season_baseline, compute_pitch_type_baseline, filter_to_window, load_pitcher_data, PitcherData |
| `tests/test_data.py` | Unit tests for all data module functions | 100 | 150 | VERIFIED | 15 test functions, all passing |
| `pyproject.toml` | pytest dev dependency and config | — | — | VERIFIED | Contains `[tool.pytest.ini_options]`, `pytest>=9.0.2` in dev group |
| `.gitignore` | Ignore patterns for Python project | — | — | VERIFIED | Contains `__pycache__/` and standard Python patterns |
| `main.py` | CLI entry point with argparse and data pipeline | 30 | 53 | VERIFIED | parse_args, main, argparse, from data import load_pitcher_data, clean exit codes |
| `tests/test_cli.py` | Unit tests for CLI argument parsing and integration | 40 | 100 | VERIFIED | 10 test functions (5 unit, 5 integration), all passing |
| `tests/__init__.py` | Empty test package init | — | 0 | VERIFIED | Exists |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `data.py` | `statcast_2026.parquet` | `pl.read_parquet()` in load_statcast | WIRED | Line 101: `df = pl.read_parquet(PARQUET_PATH)` |
| `data.py` | `aggs/*.csv` | `pl.read_csv()` in _load_csv_with_dates | WIRED | Line 79: `df = pl.read_csv(path)` |
| `data.py` | `data.py` (internal) | `load_pitcher_data` orchestrates all loaders | WIRED | Lines 254-273: calls load_statcast, load_agg_csvs, classify_appearances, filter_to_window, compute_season_baseline, compute_pitch_type_baseline |
| `tests/test_data.py` | `data.py` | import and call all public functions | WIRED | Line 4: `from data import load_statcast, load_agg_csvs, classify_appearances, ...` |
| `main.py` | `data.py` | `from data import load_pitcher_data` | WIRED | Line 33 (inside main()): `from data import load_pitcher_data` |
| `main.py` | `argparse` | parse_args function | WIRED | Line 9: `import argparse`; parse_args builds ArgumentParser |
| `tests/test_cli.py` | `main.py` | import parse_args and subprocess calls | WIRED | Line 10: `from main import parse_args`; subprocess calls to `main.py` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `main.py` (output line) | `pitcher_data` | `load_pitcher_data(args.pitcher, args.window)` | Yes — reads parquet + 8 CSVs from disk | FLOWING |
| `data.py` load_statcast | `result` | `pl.read_parquet(PARQUET_PATH).filter(...)` | Yes — 145K row parquet, filtered to pitcher; 592155 returns non-empty | FLOWING |
| `data.py` load_agg_csvs | dict values | `pl.read_csv(AGGS_DIR / filename)` for each of 8 files | Yes — all 8 CSVs present and non-empty for test pitcher | FLOWING |
| `data.py` classify_appearances | appearances DataFrame | group_by(game_pk, game_date).agg(...) on statcast | Yes — 12 appearances for 592155 | FLOWING |
| `data.py` compute_season_baseline | single-row baseline | n_pitches-weighted agg on pitcher.csv | Yes — 1 row, n_pitches=172 | FLOWING |
| `data.py` filter_to_window | window_appearances | `df["game_date"].max()` reference, not date.today() | Yes — 11/12 appearances in 30d window | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Valid pitcher loads and exits 0 | `uv run python main.py -p 592155` | "Booser, Cam (LHP) \| 12 appearances (11 in 30d window) \| Roles: RP, SP" exit 0 | PASS |
| Custom window flag respected | `uv run python main.py -p 592155 -w 7` | "Booser, Cam (LHP) \| 12 appearances (3 in 7d window) \| Roles: RP, SP" exit 0 | PASS |
| Invalid pitcher exits 1 with stderr | `uv run python main.py -p 9999999` | stderr: "Pitcher 9999999 not found" exit 1 | PASS |
| No args exits 2 with usage | `uv run python main.py` | stderr: "usage: main.py [-h] -p PITCHER [-w WINDOW]" exit 2 | PASS |
| All 25 tests pass | `uv run pytest tests/ -v` | 25 passed in 2.22s | PASS |

---

### Requirements Coverage

All 9 requirement IDs declared across both plans are accounted for.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 01-01 | Load Statcast parquet and filter by pitcher ID | SATISFIED | load_statcast reads parquet, filters by pitcher, raises ValueError if not found; test_load_statcast_* passes |
| DATA-02 | 01-01 | Load and join Pitching+ CSVs at all grains | SATISFIED | load_agg_csvs returns all 8 grains; game_date parsed to Date; pitcher filtered; test_csv_* passes |
| DATA-03 | 01-01 | Compute season-level baselines | SATISFIED | compute_season_baseline + compute_pitch_type_baseline use n_pitches-weighted averaging; test_season_baseline_* passes |
| DATA-04 | 01-01 | Filter appearances to configurable lookback window | SATISFIED | filter_to_window uses max date in data; test_window_filter passes |
| ROLE-01 | 01-01 | Auto-detect start vs. relief per appearance | SATISFIED | classify_appearances: first_inning==1 → SP, else RP; test_classify_starter + test_classify_reliever pass |
| ROLE-02 | 01-02 | Report structure adapts based on detected role | PARTIAL — see note | Role column exists and is accessible (test_role_column_exists, test_cli_output_has_role pass); full report structure adaptation is Phase 4 work. REQUIREMENTS.md marks complete; ROADMAP Phase 4 success criterion #4 explicitly requires it. Foundation is delivered. |
| ROLE-03 | 01-01 | Correctly handles swingmen/openers | SATISFIED | test_swingman_classification passes; Booser: 1 SP + 11 RP with correct per-appearance roles |
| CLI-01 | 01-02 | Accept -p argument for pitcher ID | SATISFIED | parse_args: -p/--pitcher required=True, type=int; test_parse_pitcher_flag + test_pitcher_required pass |
| CLI-02 | 01-02 | Accept -w argument for lookback window with default | SATISFIED | parse_args: -w/--window type=int, default=30; test_window_default + test_window_custom pass |

**Note on ROLE-02:** The REQUIREMENTS.md marks ROLE-02 complete in Phase 1, but the full requirement text is "Report structure adapts based on detected role (starter report vs. reliever report)." Phase 1 delivers the role classification data that enables this adaptation. The actual role-differentiated report output is explicitly Phase 4 work (Phase 4 success criterion #4: "Starter reports and reliever reports have visibly different structure"). This is flagged for human review under Human Verification.

**Orphaned requirements check:** No additional requirement IDs from REQUIREMENTS.md are mapped to Phase 1 in the traceability table beyond the 9 listed above.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `main.py` | 41 | "Temporary verification output (replaced by report in Phase 4)" comment | Info | Intentional stub — clearly documented, Phase 4 replaces this with LLM report. Not a blocker. |

No TODO/FIXME/HACK comments, no empty return values in production paths, no hardcoded empty data structures, no unimplemented handlers found across data.py, main.py, or test files.

The `main.py` temporary output line is not a code-quality stub — it is the correct Phase 1 output per the PLAN specification ("Working CLI that loads pitcher data silently and prints a brief verification summary (temporary — replaced by report in Phase 4)"). The role, pitcher name, window count, and appearances are all derived from real data.

---

### Human Verification Required

#### 1. ROLE-02 Requirements Traceability Scoping

**Test:** Review REQUIREMENTS.md traceability table entry `ROLE-02 | Phase 1 | Complete`.

**Expected:** Confirm whether "Complete" means (a) foundational detection work is done and Phase 4 will finish the full adaptation, or (b) this was erroneously marked complete and ROLE-02 should remain open until Phase 4 delivers role-differentiated report structure.

**Why human:** Requirements traceability decisions are product-owner judgment calls. The code is unambiguously correct — role detection works. The question is whether the requirements tracker accurately reflects the Phase 1 / Phase 4 split of ROLE-02's two sub-concerns (detection vs. adaptation).

---

### Gaps Summary

No gaps found. All 15 must-have truths are verified. All 7 artifacts exist, are substantive, and are wired. All 7 key links are confirmed wired. All 9 requirement IDs from plan frontmatter are satisfied (with a documentation note on ROLE-02 scoping). Data flows through every layer from disk to CLI output with real data. All 25 tests pass.

The one human verification item (ROLE-02 scoping in REQUIREMENTS.md) does not block phase goal achievement — the goal is fully met.

---

## Commit History

| Commit | Type | Description |
|--------|------|-------------|
| `0a702e2` | test | Project setup: pytest, .gitignore, test scaffolds |
| `428475b` | feat | Implement data loading pipeline with classification and baselines |
| `9c1e676` | feat | Wire CLI entry point with argparse and data pipeline |
| `b3a3808` | docs | Complete Plan 01-01 SUMMARY and state updates |
| `3a09cbe` | docs | Complete Plan 01-02 SUMMARY and state updates |

---

_Verified: 2026-03-26T19:15:00Z_
_Verifier: Claude (gsd-verifier)_
