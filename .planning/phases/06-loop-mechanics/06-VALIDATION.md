---
phase: 6
slug: loop-mechanics
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest tests/test_report.py -x -q` |
| **Full suite command** | `uv run python -m pytest tests/ -q` |
| **Estimated runtime** | ~14 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest tests/test_report.py -x -q`
- **After every plan wave:** Run `uv run python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | LOOP-01, LOOP-04 | unit | `uv run python -m pytest tests/test_report.py -k "reflection_loop" -q` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | UX-01, UX-02, UX-04 | unit | `uv run python -m pytest tests/test_report.py -k "revision_count or downstream" -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_report.py` — add stubs for LOOP-01, LOOP-04, UX-01, UX-02, UX-04

*Existing test infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Only final capsule visible in stdout | UX-02 | Requires visual inspection with real LLM | Run `python -m pitcher_narratives.cli -p 592155` and verify no duplicate output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
