---
phase: 17
slug: multi-year-loading
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py -x` |
| **Full suite command** | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py -x`
- **After every plan wave:** Run `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | MYLD-01 | unit | `pytest tests/test_data.py::test_load_statcast_multi_year -x` | ❌ W0 | ⬜ pending |
| 17-01-02 | 01 | 1 | MYLD-02 | unit | `pytest tests/test_data.py::test_load_agg_csvs_multi_year -x` | ❌ W0 | ⬜ pending |
| 17-01-03 | 01 | 1 | MYLD-03 | unit | `pytest tests/test_data.py::test_load_statcast_missing_year_skipped -x` | ❌ W0 | ⬜ pending |
| 17-01-04 | 01 | 1 | MYLD-03 | unit | `pytest tests/test_data.py::test_load_agg_csvs_missing_year_skipped -x` | ❌ W0 | ⬜ pending |
| 17-01-05 | 01 | 1 | MYLD-04 | unit | `pytest tests/test_data.py::test_season_baseline_per_season -x` | ❌ W0 | ⬜ pending |
| 17-01-06 | 01 | 1 | MYLD-04 | unit | `pytest tests/test_data.py::test_pitch_type_baseline_per_season -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_data.py::test_load_statcast_multi_year` — MYLD-01 synthetic multi-year parquet
- [ ] `tests/test_data.py::test_load_agg_csvs_multi_year` — MYLD-02 synthetic multi-year CSV
- [ ] `tests/test_data.py::test_load_statcast_missing_year_skipped` — MYLD-03 parquet missing year
- [ ] `tests/test_data.py::test_load_agg_csvs_missing_year_skipped` — MYLD-03 CSV missing year
- [ ] `tests/test_data.py::test_season_baseline_per_season` — MYLD-04 per-season grouping
- [ ] `tests/test_data.py::test_pitch_type_baseline_per_season` — MYLD-04 pitch type per-season
- [ ] Update `test_season_baseline_weighted` — account for per-season grouping
- [ ] Update `test_years_constant_drives_paths` — verify `_YEARS` = `[2025, 2026]`

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
