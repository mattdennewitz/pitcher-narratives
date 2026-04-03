---
phase: 16
slug: data-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_data.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_data.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | DFND-01 | unit | `uv run pytest tests/test_data.py::test_load_statcast_filters_game_type -x` | ❌ W0 | ⬜ pending |
| 16-01-02 | 01 | 1 | DFND-01 | unit | `uv run pytest tests/test_data.py::test_load_csv_filters_game_type -x` | ❌ W0 | ⬜ pending |
| 16-01-03 | 01 | 1 | DFND-01 | unit | `uv run pytest tests/test_data.py::test_filter_game_type_no_column -x` | ❌ W0 | ⬜ pending |
| 16-01-04 | 01 | 1 | DFND-04 | unit | `uv run pytest tests/test_data.py::test_filter_game_type_exported -x` | ❌ W0 | ⬜ pending |
| 16-01-05 | 01 | 1 | DFND-02 | unit | `uv run pytest tests/test_data.py::test_no_hardcoded_year_in_csv_dicts -x` | ❌ W0 | ⬜ pending |
| 16-01-06 | 01 | 1 | DFND-03 | unit | `uv run pytest tests/test_data.py::test_season_in_id_cols -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_data.py::test_load_statcast_filters_game_type` — stubs for DFND-01 parquet filter
- [ ] `tests/test_data.py::test_load_csv_filters_game_type` — stubs for DFND-01 CSV filter
- [ ] `tests/test_data.py::test_filter_game_type_no_column` — stubs for DFND-01 edge case
- [ ] `tests/test_data.py::test_filter_game_type_exported` — stubs for DFND-04
- [ ] `tests/test_data.py::test_no_hardcoded_year_in_csv_dicts` — stubs for DFND-02
- [ ] `tests/test_data.py::test_season_in_id_cols` — stubs for DFND-03
- [ ] `tests/test_data.py::test_swingman_classification` — update fixture to 676571

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CLI output shows only regular-season baselines | DFND-01 | Integration requires running full CLI | Run `uv run python -m pitcher_narratives.cli scout 592155` and verify no spring training contamination |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
