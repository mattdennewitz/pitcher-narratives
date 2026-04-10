---
phase: 19
slug: cross-season-baseline-exposure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-08
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (not yet installed — Wave 0 installs) |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `uv run pytest tests/test_data.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_data.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | XSBL-01 | unit | `uv run pytest tests/test_data.py::test_pitcher_data_has_prior_baselines -x` | ❌ W0 | ⬜ pending |
| 19-01-02 | 01 | 1 | XSBL-02 | unit | `uv run pytest tests/test_data.py::test_load_retains_all_seasons -x` | ❌ W0 | ⬜ pending |
| 19-01-03 | 01 | 1 | XSBL-03 | unit | `uv run pytest tests/test_data.py::test_single_season_empty_prior -x` | ❌ W0 | ⬜ pending |
| 19-01-04 | 01 | 1 | XSBL-03 | regression | `uv run pytest tests/test_data.py::test_existing_engine_no_regression -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_data.py` — stubs for XSBL-01, XSBL-02, XSBL-03
- [ ] `tests/conftest.py` — shared fixtures (mock PitcherData factory)
- [ ] `uv add --dev pytest` — install test framework

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Report output unchanged for single-season pitcher | XSBL-03 | End-to-end report requires LLM call | Run `uv run pitcher-report -p 808967` and verify output matches pre-change baseline |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
