---
phase: 5
slug: reflection-data-models
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already in use — tests/ directory exists) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest tests/test_report.py -x -q` |
| **Full suite command** | `uv run python -m pytest tests/ -q` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest tests/test_report.py -x -q`
- **After every plan wave:** Run `uv run python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | MODEL-01 | unit | `uv run python -m pytest tests/test_report.py -k "anchor_result" -q` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | MODEL-02 | unit | `uv run python -m pytest tests/test_report.py -k "revision_count" -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | LOOP-02 | unit | `uv run python -m pytest tests/test_report.py -k "revision_prompt" -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_report.py` — fix existing 10 test failures (5-agent unpack), add stubs for MODEL-01, MODEL-02, LOOP-02
- [ ] No new framework install needed — pytest already available

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Revision prompt reads naturally | LOOP-02 | Subjective quality | Read prompt output, verify it reads as targeted revision instruction |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
