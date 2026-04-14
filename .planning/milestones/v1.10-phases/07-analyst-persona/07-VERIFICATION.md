---
phase: 07-analyst-persona
verified: 2026-04-13T00:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 07: Analyst Persona Verification Report

**Phase Goal:** Add the ANALYST persona — a newsletter-style teaching voice (450-800 words) targeting analytically-inclined fans. Inherits scout's factual discipline. Second persona in v1.10 persona system. Includes per-persona hallucination guard allowlist and analyst-specific tests.
**Verified:** 2026-04-13
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `get_persona('analyst')` returns ANALYST with parent='scout' and length_target=(450, 800) | VERIFIED | personas.py lines 195-205; runtime check passed |
| 2 | `build_writer_system_prompt(ANALYST)` starts with SHARED_WRITER_BASE, includes _SCOUT_OVERLAY, then _ANALYST_OVERLAY | VERIFIED | personas.py lines 229-240; `build_writer_system_prompt` composes parts=[SHARED_WRITER_BASE, parent.overlay, persona.overlay]; runtime check confirmed 6548 chars |
| 3 | `check_hallucinated_metrics(text, persona='analyst')` does not false-positive on analyst vocabulary (playability, tunneling gap, pitch tree, arsenal depth) | VERIFIED | pipeline.py lines 1466-1473 (_PERSONA_KNOWN_METRICS), 1553-1554; test_analyst_vocab_not_flagged_with_persona passes |
| 4 | `check_hallucinated_metrics(text)` with no persona argument behaves identically to v1.9 | VERIFIED | persona defaults to None; persona_known = frozenset() when persona is falsy; test_no_persona_backward_compat passes |
| 5 | A TestModel-based analyst smoke test runs the pipeline end-to-end without errors | VERIFIED | test_analyst_pipeline_smoke defined at test_personas.py lines 300-323; PASSED in test run |
| 6 | `assert_analyst_shape` validates structural constraints (no tables, no bullets, no h1) | VERIFIED | assert_analyst_shape defined at test_personas.py lines 236-272; three shape tests all pass |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/personas.py` | ANALYST persona with newsletter overlay, parent=scout | VERIFIED | Lines 195-210: ANALYST defined, registered, exported in __all__ |
| `src/pitcher_narratives/pipeline.py` | _PERSONA_KNOWN_METRICS dict, persona param on check_hallucinated_metrics | VERIFIED | Lines 1466-1473, 1514-1516, 1553-1554 |
| `tests/test_personas.py` | test_analyst_pipeline_smoke, assert_analyst_shape | VERIFIED | Lines 236-323; both present and substantive |
| `tests/test_hallucination_guard.py` | test_analyst_vocab_not_flagged_with_persona and 3 companion tests | VERIFIED | Lines 173-219; 4 analyst regression vector tests added |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `personas.py` | PERSONAS registry | `"analyst": ANALYST` at line 209 | VERIFIED | `PERSONAS` dict contains both "scout" and "analyst" keys |
| `pipeline.py` | `personas.py` | `persona: str \| None = None` on `check_hallucinated_metrics` | VERIFIED | Signature at line 1514-1516; persona param wired to _PERSONA_KNOWN_METRICS lookup |
| `tests/test_personas.py` | `personas.py` + `pipeline.py` | imports ANALYST, calls `generate_pipeline_streaming` with `persona="analyst"` | VERIFIED | Line 9 imports ANALYST; line 311 calls with `persona="analyst"` |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces persona constants, a guard allowlist, and test helpers. No dynamic data rendering components.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ANALYST persona importable with correct fields | `uv run python -c "from pitcher_narratives.personas import ANALYST, get_persona, ..."` | All assertions pass, "ALL CHECKS PASSED" | PASS |
| 49 persona + guard tests pass | `uv run python -m pytest tests/test_personas.py tests/test_hallucination_guard.py` | 49 passed, 0 failed, 1 warning | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| VOICE-02 | 07-01-PLAN.md | ANALYST persona constant, newsletter voice, 450-800 words, parent=scout, teaching vocabulary | SATISFIED | personas.py lines 130-210; test_analyst_has_expected_fields, test_analyst_composed_prompt_includes_base_and_scout, test_analyst_overlay_has_teaching_vocabulary all pass |
| PERSONA-10 | 07-01-PLAN.md | check_hallucinated_metrics gains optional persona param; per-persona _PERSONA_KNOWN_METRICS allowlist | SATISFIED | pipeline.py lines 1466-1473, 1514-1516, 1553-1554; test_analyst_vocab_not_flagged_with_persona and test_no_persona_backward_compat pass |
| TEST-05 (analyst portion) | 07-01-PLAN.md | TestModel-based analyst smoke test in test_personas.py | SATISFIED | test_analyst_pipeline_smoke at test_personas.py:300; passes |
| TEST-06 (analyst portion) | 07-01-PLAN.md | assert_analyst_shape structural validator (no tables, no bullets, no h1) | SATISFIED | assert_analyst_shape at test_personas.py:236; three shape helper tests pass |
| TEST-07 (analyst portion) | 07-01-PLAN.md | Per-persona regression vectors for analyst vocabulary in test_hallucination_guard.py | SATISFIED | 4 tests added at lines 173-219; all pass |

**Orphaned requirements check:** REQUIREMENTS.md traceability table maps VOICE-02, PERSONA-10, TEST-05 (partial), TEST-06 (partial), TEST-07 (partial) to Phase 07. All accounted for. No orphans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No anti-patterns found |

Scan performed on all four modified files. No TODO/FIXME/placeholder comments, no empty handlers, no hardcoded-empty returns in functional code paths, no stub implementations.

### Human Verification Required

None — all must-haves are fully verifiable programmatically. The analyst voice quality (does it actually read like a newsletter?) is deferred to real LLM output in Phase D per REQUIREMENTS.md scope decision.

### Gaps Summary

No gaps. All 6 must-have truths verified. All 4 artifacts present, substantive, and wired. All 5 requirement IDs satisfied. 49 tests pass.

---

_Verified: 2026-04-13_
_Verifier: Claude (gsd-verifier)_
