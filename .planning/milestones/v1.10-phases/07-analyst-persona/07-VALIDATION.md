---
phase: 07
slug: analyst-persona
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.2 |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_personas.py tests/test_hallucination_guard.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q --ignore=tests/test_analyst.py` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_personas.py tests/test_hallucination_guard.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q --ignore=tests/test_analyst.py`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | VOICE-02 | unit | `uv run pytest tests/test_personas.py -x -q` | ✅ | ⬜ pending |
| 07-01-02 | 01 | 1 | PERSONA-10 | unit | `uv run pytest tests/test_hallucination_guard.py -x -q` | ✅ | ⬜ pending |
| 07-01-03 | 01 | 1 | TEST-05/06/07 | integration | `uv run pytest tests/test_personas.py tests/test_hallucination_guard.py -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing pytest infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
