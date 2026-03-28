---
phase: 6
slug: loop-mechanics
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-28
---

# Phase 6 -- Validation Strategy

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
| 06-01-01 | 01 | 1 | LOOP-01, LOOP-04 | unit | `uv run python -m pytest tests/test_report.py -k "reflection_loop" -q` | Yes (W0) | ⬜ pending |
| 06-01-02 | 01 | 1 | UX-01, UX-02, UX-04 | unit | `uv run python -m pytest tests/test_report.py -k "revision_count or downstream" -q` | Yes (W0) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_report.py` -- tests written by 06-01 Task 2 (loop behavior tests including UX-04 capsule handoff verification via Agent.run_sync patching)

*Wave 0 is handled inline by 06-01 Task 2, which creates all loop behavior tests as part of its action. No separate Wave 0 plan is needed. Existing test infrastructure (pytest, fixtures, TestModel imports) is already in place from prior phases.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Only final capsule visible in stdout | UX-02 | Requires visual inspection with real LLM | Run `python -m pitcher_narratives.cli -p 592155` and verify no duplicate output |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (Wave 0 handled inline by 06-01 Task 2)
