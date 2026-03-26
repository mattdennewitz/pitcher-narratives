---
phase: 4
slug: report-generation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already installed) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 8 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 04-01-01 | 01 | 1 | RPT-01 | unit | `uv run pytest tests/test_report.py::test_agent_configured -x` | pending |
| 04-01-01 | 01 | 1 | RPT-02 | unit | `uv run pytest tests/test_report.py::test_generate_report -x` | pending |
| 04-01-01 | 01 | 1 | RPT-03 | unit | `uv run pytest tests/test_report.py::test_system_prompt -x` | pending |
| 04-01-01 | 01 | 1 | RPT-04 | unit | `uv run pytest tests/test_report.py::test_sp_rp_guidance -x` | pending |
| 04-02-01 | 02 | 2 | RPT-02 | integration | `uv run pytest tests/test_cli.py -x` | pending |
| 04-02-01 | 02 | 2 | RPT-04 | integration | `uv run pytest tests/test_cli.py::test_report_output -x` | pending |

*Status: pending / green / red / flaky*
