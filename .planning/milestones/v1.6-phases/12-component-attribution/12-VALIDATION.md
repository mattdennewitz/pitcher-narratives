---
phase: 12
slug: component-attribution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_engine.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~7 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_engine.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | DATA-03 | unit | `uv run pytest tests/test_engine.py::test_attribution_13_outcomes -x` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | DATA-03 | unit | `uv run pytest tests/test_engine.py::test_attribution_sum_to_xrv -x` | ❌ W0 | ⬜ pending |
| 12-01-03 | 01 | 1 | DATA-03 | unit | `uv run pytest tests/test_engine.py::test_attribution_labeled -x` | ❌ W0 | ⬜ pending |
| 12-01-04 | 01 | 1 | DATA-03 | unit | `uv run pytest tests/test_engine.py::test_attribution_both_grains -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_engine.py` — add new test functions for ComponentAttribution (file exists, new tests needed)
- [ ] RV_df.csv must be accessible in aggs/ or data directory

*Existing infrastructure covers most phase requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
