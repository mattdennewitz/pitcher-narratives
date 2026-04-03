---
phase: 11
slug: intermediate-probability-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_engine.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

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
| 11-01-01 | 01 | 1 | DATA-01 | unit | `uv run pytest tests/test_engine.py::test_intermediate_probabilities_computed -x` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | DATA-01 | unit | `uv run pytest tests/test_engine.py::test_intermediate_bbe_prob_none -x` | ❌ W0 | ⬜ pending |
| 11-01-03 | 01 | 1 | DATA-02 | unit | `uv run pytest tests/test_engine.py::test_intermediate_p_and_s_variants -x` | ❌ W0 | ⬜ pending |
| 11-01-04 | 01 | 1 | DATA-02 | unit | `uv run pytest tests/test_engine.py::test_intermediate_location_impact -x` | ❌ W0 | ⬜ pending |
| 11-01-05 | 01 | 1 | SC-3 | unit | `uv run pytest tests/test_engine.py::test_intermediate_both_grains -x` | ❌ W0 | ⬜ pending |
| 11-01-06 | 01 | 1 | SC-4 | unit | `uv run pytest tests/test_engine.py::test_intermediate_missing_columns_graceful -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_engine.py` — add new test functions for IntermediateProbabilities (file exists, new tests needed)
- [ ] No new test files or fixtures needed — existing `load_pitcher_data(TEST_PITCHER)` fixture pattern is sufficient

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
