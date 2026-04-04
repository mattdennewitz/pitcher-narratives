---
phase: 24
slug: pipeline-re-architecture
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_pipeline.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_pipeline.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 24-01-01 | 01 | 0 | PIPE-01 | unit | `uv run pytest tests/test_pipeline.py::TestBuildApproachInput -x` | ❌ W0 | ⬜ pending |
| 24-01-02 | 01 | 0 | PIPE-02 | unit | `uv run pytest tests/test_pipeline.py::TestApproachPrompt -x` | ❌ W0 | ⬜ pending |
| 24-01-03 | 01 | 0 | PIPE-03 | unit | `uv run pytest tests/test_pipeline.py::TestLocationRvNoYoY::test_location_input_no_platoon -x` | ❌ W0 | ⬜ pending |
| 24-01-04 | 01 | 0 | PIPE-04 | unit | `uv run pytest tests/test_pipeline.py::TestRPGameShapeSkip -x` | ❌ W0 | ⬜ pending |
| 24-01-05 | 01 | 0 | PIPE-05 | unit | `uv run pytest tests/test_pipeline.py::TestStuffAppendix -x` | ❌ W0 | ⬜ pending |
| 24-01-06 | 01 | 0 | PIPE-06 | unit | `uv run pytest tests/test_pipeline.py::TestBuildWriterInput -x` | ❌ W0 | ⬜ pending |
| 24-01-07 | 01 | 0 | PIPE-07 | smoke | `uv run pytest tests/test_pipeline.py::TestAuditAndReviseSpecialists -x` | Partial | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline.py::TestBuildApproachInput` — covers PIPE-01 (approach input builder outputs)
- [ ] `tests/test_pipeline.py::TestApproachPrompt` — covers PIPE-02 (prompt content assertions)
- [ ] `tests/test_pipeline.py::TestRPGameShapeSkip` — covers PIPE-04 (RP conditional + workload stub)
- [ ] `tests/test_pipeline.py::TestStuffAppendix` — covers PIPE-05 (raw data appendix in stuff/trend inputs)
- [ ] `tests/test_pipeline.py::TestBuildWriterInput` — covers PIPE-06 (6 sections, RP conditional)
- [ ] Extend `_make_pipeline_ctx()` helper with platoon_mix, count_splits, first_pitch populated for testing
- [ ] Extend `_make_pipeline_ctx()` helper to support `role="RP"` variant

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Approach Specialist narrative quality | PIPE-02 | LLM output quality is subjective | Run full pipeline, review approach section reads like a scout |
| Writer RP conditional phrasing | PIPE-04 | Prompt interpolation quality | Run pipeline with RP pitcher, verify no TTO references |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending