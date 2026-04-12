---
phase: 2
slug: fastball-arsenal-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already installed) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_engine.py -x -q` |
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

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 02-01-01 | 01 | 1 | FB-01 | unit | `uv run pytest tests/test_engine.py::test_fastball_velo_baseline_vs_window -x` | pending |
| 02-01-01 | 01 | 1 | FB-02 | unit | `uv run pytest tests/test_engine.py::test_fastball_pplus_delta -x` | pending |
| 02-01-01 | 01 | 1 | FB-03 | unit | `uv run pytest tests/test_engine.py::test_fastball_movement_delta -x` | pending |
| 02-01-01 | 01 | 1 | FB-04 | unit | `uv run pytest tests/test_engine.py::test_velocity_arc -x` | pending |
| 02-02-01 | 02 | 2 | ARSL-01 | unit | `uv run pytest tests/test_engine.py::test_arsenal_usage_rates -x` | pending |
| 02-02-01 | 02 | 2 | ARSL-02 | unit | `uv run pytest tests/test_engine.py::test_arsenal_pplus_per_type -x` | pending |
| 02-02-01 | 02 | 2 | ARSL-03 | unit | `uv run pytest tests/test_engine.py::test_platoon_mix -x` | pending |
| 02-02-01 | 02 | 2 | ARSL-04 | unit | `uv run pytest tests/test_engine.py::test_first_pitch_weaponry -x` | pending |

*Status: pending / green / red / flaky*
