---
phase: 22
slug: context-assembly-prompt-rendering
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via uv run pytest) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_context.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~2 seconds (quick), ~72 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_context.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | CPMT-01 | unit | `uv run pytest tests/test_context.py -x -q -k cross_season` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | CPMT-02 | unit | `uv run pytest tests/test_context.py -x -q -k yoy_section` | ❌ W0 | ⬜ pending |
| 22-01-03 | 01 | 1 | CPMT-03 | unit | `uv run pytest tests/test_pipeline.py -x -q -k cross_season` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_context.py` — add cross-season field and YoY rendering tests
- [ ] `tests/test_pipeline.py` — add specialist cross-season context tests

*Existing infrastructure covers framework requirements. Only new test cases needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
