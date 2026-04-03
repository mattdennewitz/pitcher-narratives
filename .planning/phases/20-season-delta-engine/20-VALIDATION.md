---
phase: 20
slug: season-delta-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via uv run pytest) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_engine.py -x -q -k cross_season` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds (quick), ~67 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_engine.py -x -q -k cross_season`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | SDLT-01 | unit | `uv run pytest tests/test_engine.py -x -q -k cross_season_summary` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | SDLT-02 | unit | `uv run pytest tests/test_engine.py -x -q -k cross_season_delta_strings` | ❌ W0 | ⬜ pending |
| 20-01-03 | 01 | 1 | SDLT-03 | unit | `uv run pytest tests/test_engine.py -x -q -k cross_season_none` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_engine.py` — add cross-season delta tests (multi-year, single-year, delta string format)

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
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
