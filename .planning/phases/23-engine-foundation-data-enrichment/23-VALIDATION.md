---
phase: 23
slug: engine-foundation-data-enrichment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_engine.py tests/test_context.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_engine.py tests/test_context.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | ENG-01 | unit | `uv run pytest tests/test_engine.py -x -k "count_split" -q` | ❌ W0 | ⬜ pending |
| 23-02-01 | 02 | 1 | ENG-02 | unit | `uv run pytest tests/test_engine.py -x -k "arm_angle" -q` | ❌ W0 | ⬜ pending |
| 23-03-01 | 03 | 1 | ENG-03 | unit | `uv run pytest tests/test_engine.py -x -k "outlier_tag or percentile" -q` | ❌ W0 (outlier_tag tests exist; percentile format tests new) | ⬜ pending |
| 23-04-01 | 04 | 2 | ENG-04 | integration | `uv run pytest tests/test_context.py -x -k "count_split or arm_angle" -q` | ❌ W0 | ⬜ pending |
| 23-05-01 | 05 | 1 | ENG-05 | unit | `uv run pytest tests/test_engine.py -x -k "small_sample and count" -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_engine.py` — new test functions for count splits computation (5 buckets, usage rates, deltas, notable shifts)
- [ ] `tests/test_engine.py` — new test functions for arm angle (atan2 math, slot labels, delta strings, per-pitch-type)
- [ ] `tests/test_engine.py` — update existing outlier_tag tests for new percentile format + backward compat
- [ ] `tests/test_engine.py` — test handedness-split percentile computation
- [ ] `tests/test_engine.py` — test small sample behavior (delta suppressed, usage still shown)
- [ ] `tests/test_engine.py` — test LeagueBaseline extension with release point fields
- [ ] `tests/test_context.py` — test PitcherContext includes count_splits and arm angle fields
- [ ] `tests/test_context.py` — test to_prompt() renders count splits adjacent to platoon section

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
