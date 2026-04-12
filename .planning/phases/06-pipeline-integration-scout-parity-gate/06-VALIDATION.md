---
phase: 06
slug: pipeline-integration-scout-parity-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.2 |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_personas.py tests/test_signals.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q --ignore=tests/test_analyst.py` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_personas.py tests/test_signals.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q --ignore=tests/test_analyst.py`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 8 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | PERSONA-07 | unit | `uv run pytest tests/test_personas.py tests/test_signals.py -x -q` | ✅ | ⬜ pending |
| 06-01-02 | 01 | 1 | PERSONA-08 | unit | `uv run pytest tests/test_personas.py -x -q` | ✅ | ⬜ pending |
| 06-01-03 | 01 | 1 | PERSONA-09 | unit | `uv run pytest tests/test_personas.py -x -q` | ✅ | ⬜ pending |
| 06-01-04 | 01 | 1 | TEST-05 | integration | `uv run pytest tests/test_personas.py -x -q -k scout_smoke` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Pipeline smoke test added to `tests/test_personas.py` for scout persona

*Existing pytest infrastructure covers framework requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 8s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
