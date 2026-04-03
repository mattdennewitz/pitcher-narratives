---
phase: 14
slug: analyst-prompt-rewrite
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_analyst.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~7 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_analyst.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | ANLST-01 | unit | `uv run pytest tests/test_analyst.py -x -q -k "prompt"` | ✅ | ⬜ pending |
| 14-01-02 | 01 | 1 | ANLST-02 | unit | `uv run pytest tests/test_analyst.py -x -q -k "prompt"` | ✅ | ⬜ pending |
| 14-01-03 | 01 | 1 | ANLST-03 | unit | `uv run pytest tests/test_analyst.py -x -q -k "prompt"` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing test infrastructure covers phase requirements. New tests for prompt content verification may be added.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLM output uses intermediates reasoning | ANLST-01 | LLM response quality not automatable | Run `pitcher-ask "How is Cease's cutter?" --provider claude` and verify response cites intermediate probabilities |
| LLM diagnoses location impact | ANLST-02 | LLM response quality not automatable | Check response mentions P vs S comparison |
| LLM identifies dominant attribution driver | ANLST-03 | LLM response quality not automatable | Check response mentions specific outcome contributions |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
