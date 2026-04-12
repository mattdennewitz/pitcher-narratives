---
phase: 18
slug: consumer-module-updates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py tests/test_engine.py tests/test_resolver.py -x --tb=short -q` |
| **Full suite command** | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_data.py tests/test_engine.py tests/test_resolver.py --tb=short -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | CSMR-01 | smoke+integration | `grep + pytest tests/test_engine.py` | Yes (needs updates) | ⬜ pending |
| 18-01-02 | 01 | 1 | CSMR-02 | unit | `pytest tests/test_resolver.py` | Yes | ⬜ pending |
| 18-01-03 | 01 | 1 | CSMR-03 | smoke | `grep + functional check` | No test file | ⬜ pending |
| 18-01-04 | 01 | 1 | ALL | smoke | `grep "read_csv\|read_parquet" src/pitcher_narratives/ -r \| grep -v data.py` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_data.py` — add tests for `load_all_statcast()` and `load_full_agg()` new functions
- [ ] `tests/test_engine.py` — update 7 broken test assertions for post-filtering data

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| scout.py scout_appearances works end-to-end | CSMR-03 | No test_scout.py exists | `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -c "from pitcher_narratives.scout import scout_appearances; r = scout_appearances(); print(len(r))"` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
