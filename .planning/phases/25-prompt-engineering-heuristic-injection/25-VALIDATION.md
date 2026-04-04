---
phase: 25
slug: prompt-engineering-heuristic-injection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (uv-managed) |
| **Config file** | pyproject.toml (no [tool.pytest] section) |
| **Quick run command** | `uv run python -m pytest tests/test_pipeline.py -x -q` |
| **Full suite command** | `uv run python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest tests/test_pipeline.py -x -q`
- **After every plan wave:** Run `uv run python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 25-01-01 | 01 | 1 | PROMPT-01 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_stuff_prompt_tradeoff"` | Wave 0 | ⬜ pending |
| 25-01-02 | 01 | 1 | PROMPT-02 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_location_prompt_contradiction"` | Wave 0 | ⬜ pending |
| 25-01-03 | 01 | 1 | PROMPT-06 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_location_input_adjacent"` | Wave 0 | ⬜ pending |
| 25-02-01 | 02 | 1 | PROMPT-03 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_trend_prompt"` | Wave 0 | ⬜ pending |
| 25-02-02 | 02 | 1 | PROMPT-03 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_trend_prompt_no_arm"` | Wave 0 | ⬜ pending |
| 25-03-01 | 03 | 1 | PROMPT-04 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_writer_prompt_causal"` | Wave 0 | ⬜ pending |
| 25-03-02 | 03 | 1 | PROMPT-05 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_auditor_whitelist"` | Wave 0 | ⬜ pending |
| 25-03-03 | 03 | 1 | PROMPT-05 | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_auditor_whitelist_placement"` | Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline.py::TestStuffPromptHeuristics` — stubs for PROMPT-01 trade-off detection substring checks
- [ ] `tests/test_pipeline.py::TestLocationPromptHeuristics` — stubs for PROMPT-02 contradiction detection
- [ ] `tests/test_pipeline.py::TestTrendPromptFunction` — stubs for PROMPT-03 conditional vocabulary (with and without arm angle)
- [ ] `tests/test_pipeline.py::TestWriterPromptCausalHook` — stubs for PROMPT-04 causal hook section presence
- [ ] `tests/test_pipeline.py::TestAuditorWhitelist` — stubs for PROMPT-05 whitelist content and placement
- [ ] `tests/test_pipeline.py::TestLocationInputAdjacency` — stubs for PROMPT-06 metric adjacency in output

*Existing infrastructure covers test framework. Wave 0 adds test classes only.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLM output quality | All PROMPT-* | LLM output is non-deterministic | Run full pipeline on sample pitcher, review narrative for trade-offs/contradictions/causal hooks |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
