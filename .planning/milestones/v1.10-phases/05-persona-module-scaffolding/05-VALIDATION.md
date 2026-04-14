---
phase: 05
slug: persona-module-scaffolding
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.2 |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_personas.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_personas.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | PERSONA-01 | unit | `uv run pytest tests/test_personas.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | PERSONA-04 | unit | `uv run pytest tests/test_personas.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | PERSONA-02 | unit | `uv run pytest tests/test_personas.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | PERSONA-03 | unit | `uv run pytest tests/test_personas.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | PERSONA-05 | unit | `uv run pytest tests/test_personas.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | PERSONA-06 | unit | `uv run pytest tests/test_personas.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-07 | 01 | 1 | VOICE-01 | unit | `uv run pytest tests/test_personas.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | TEST-01 | fixture | `test -f tests/fixtures/writer_prompt_scout.txt` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | TEST-02 | unit | `uv run pytest tests/test_personas.py::test_scout_composed_prompt_is_byte_identical_to_v19 -x -q` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 1 | TEST-03 | unit | `uv run pytest tests/test_personas.py::test_base_prompt_has_no_voice_words -x -q` | ❌ W0 | ⬜ pending |
| 05-02-04 | 02 | 1 | TEST-04 | unit | `uv run pytest tests/test_personas.py::test_base_prompt_has_explainer_section -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_personas.py` — stubs for all persona unit tests
- [ ] `tests/fixtures/writer_prompt_scout.txt` — frozen v1.9 writer prompt fixture

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
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
