---
phase: 1
slug: data-pipeline-classification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (needs installation via `uv add --dev pytest`) |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | DATA-01 | unit | `uv run pytest tests/test_data.py::test_load_statcast_filters_by_pitcher -x` | Wave 0 | pending |
| 01-01-01 | 01 | 1 | DATA-01 | unit | `uv run pytest tests/test_data.py::test_load_statcast_invalid_pitcher -x` | Wave 0 | pending |
| 01-01-01 | 01 | 1 | DATA-02 | unit | `uv run pytest tests/test_data.py::test_load_csvs_all_grains -x` | Wave 0 | pending |
| 01-01-01 | 01 | 1 | DATA-02 | unit | `uv run pytest tests/test_data.py::test_csv_date_parsing -x` | Wave 0 | pending |
| 01-01-02 | 01 | 1 | DATA-03 | unit | `uv run pytest tests/test_data.py::test_season_baseline_weighted -x` | Wave 0 | pending |
| 01-01-02 | 01 | 1 | DATA-03 | unit | `uv run pytest tests/test_data.py::test_season_baseline_single_game_type -x` | Wave 0 | pending |
| 01-01-02 | 01 | 1 | DATA-04 | unit | `uv run pytest tests/test_data.py::test_window_filter -x` | Wave 0 | pending |
| 01-01-02 | 01 | 1 | ROLE-01 | unit | `uv run pytest tests/test_data.py::test_classify_starter -x` | Wave 0 | pending |
| 01-01-02 | 01 | 1 | ROLE-01 | unit | `uv run pytest tests/test_data.py::test_classify_reliever -x` | Wave 0 | pending |
| 01-01-02 | 01 | 1 | ROLE-03 | unit | `uv run pytest tests/test_data.py::test_swingman_classification -x` | Wave 0 | pending |
| 01-02-01 | 02 | 2 | CLI-01 | unit | `uv run pytest tests/test_cli.py::test_parse_pitcher_flag -x` | Wave 0 | pending |
| 01-02-01 | 02 | 2 | CLI-02 | unit | `uv run pytest tests/test_cli.py::test_window_default -x` | Wave 0 | pending |
| 01-02-01 | 02 | 2 | ROLE-02 | unit | `uv run pytest tests/test_data.py::test_role_column_exists -x` | Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `uv add --dev pytest` — install test framework
- [ ] `tests/__init__.py` — empty init for test package
- [ ] `tests/test_data.py` — stubs for DATA-01..04, ROLE-01, ROLE-02, ROLE-03
- [ ] `tests/test_cli.py` — stubs for CLI-01, CLI-02
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` section
