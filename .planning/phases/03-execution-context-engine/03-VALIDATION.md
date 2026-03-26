---
phase: 3
slug: execution-context-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already installed) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
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

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 03-01-01 | 01 | 1 | EXEC-01 | unit | `uv run pytest tests/test_engine.py::test_csw_pct -x` | pending |
| 03-01-01 | 01 | 1 | EXEC-02 | unit | `uv run pytest tests/test_engine.py::test_xwhiff_xswing -x` | pending |
| 03-01-01 | 01 | 1 | EXEC-03 | unit | `uv run pytest tests/test_engine.py::test_zone_chase_rate -x` | pending |
| 03-01-01 | 01 | 1 | EXEC-04 | unit | `uv run pytest tests/test_engine.py::test_xrv100_percentile -x` | pending |
| 03-01-01 | 01 | 1 | CTX-01 | unit | `uv run pytest tests/test_engine.py::test_rest_days -x` | pending |
| 03-01-01 | 01 | 1 | CTX-02 | unit | `uv run pytest tests/test_engine.py::test_innings_pitched -x` | pending |
| 03-01-01 | 01 | 1 | CTX-03 | unit | `uv run pytest tests/test_engine.py::test_consecutive_days -x` | pending |
| 03-02-01 | 02 | 2 | ALL | integration | `uv run pytest tests/test_context.py -x` | pending |
| 03-02-01 | 02 | 2 | ALL | integration | `uv run pytest tests/test_context.py::test_to_prompt_token_budget -x` | pending |

*Status: pending / green / red / flaky*
