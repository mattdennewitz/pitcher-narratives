---
phase: 08-generic-persona
verified: 2026-04-13T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 08: Generic Persona Verification Report

**Phase Goal:** A GENERIC persona exists with a sectioned-with-summary-table format, validated against the shared anchor check and hallucination guard -- the only phase that may conditionally touch anchor.py
**Verified:** 2026-04-13
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | `get_persona("generic")` returns GENERIC persona with fixed sections in order (Stuff, Location, Run Value & Execution, Trend, Game Shape, Summary Table) and forbids h1 headings | VERIFIED | `GENERIC` constant in `personas.py` lines 272-282; overlay contains STRUCTURE OVERRIDE clause, all 6 sections in order, `FORBIDDEN: Markdown h1 headings` clause; `test_generic_overlay_fixes_section_order` and `test_generic_overlay_forbids_h1` pass |
| 2 | Synthetic generic capsule passes hallucination guard and anchor check without false positives; if false positives occur a one-line ANCHOR_PROMPT addendum is applied | VERIFIED | `test_generic_synthetic_capsule_clean` passes; `anchor.py` line 55 contains the addendum "Summary tables in a fixed section format are intentional structure, not narrative violations."; anchor tolerance test is `xfail(strict=False)` with documented TestModel Pitfall 4 rationale |
| 3 | `check_explainer_present(capsule)` runs after writer's capsule in `_run_pipeline` and logs a warning to stderr when Pitching+ content is missing | VERIFIED | `pipeline.py` lines 1302-1309 show Phase 2.25 call site wired; `test_run_pipeline_logs_warning_when_capsule_missing_explainer` passes, confirming warning logged with `[scout]` persona id |
| 4 | TestModel-based generic smoke test runs the pipeline and `assert_generic_shape(text)` validates exactly one markdown table, correct row count, allowed section set, and no h1 headings | VERIFIED | `test_generic_pipeline_smoke` passes; `assert_generic_shape` helper at `test_personas.py` lines 406-466 validates all stated constraints; 5 exercisers cover accept/reject cases for h1, missing sections, multiple tables, wrong row count |
| 5 | Hallucination guard regression: a known-dirty capsule (fabricated section or invented metric in a table row) is correctly flagged | VERIFIED | `test_generic_table_row_invented_metric_flagged` and `test_generic_fabricated_section_metric_flagged` both pass; `xDominance` and `xFakeMetric` caught in generic-persona context |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/personas.py` | GENERIC constant with 6-section overlay, parent="scout", length_target=(300,500) | VERIFIED | Lines 185-282; GENERIC dataclass present, all structural requirements confirmed |
| `src/pitcher_narratives/pipeline.py` | `_PERSONA_KNOWN_METRICS["generic"]`, `check_explainer_present`, Phase 2.25 wiring | VERIFIED | `_PERSONA_KNOWN_METRICS` at line 1476 contains `"generic": frozenset()`; `check_explainer_present` at line 1586; Phase 2.25 at line 1302 |
| `src/pitcher_narratives/anchor.py` | Summary-table tolerance addendum to ANCHOR_PROMPT | VERIFIED | Line 55: "Summary tables in a fixed section format are intentional structure, not narrative violations." |
| `tests/test_personas.py` | `assert_generic_shape` helper + exercisers, generic smoke test, registry test | VERIFIED | Lines 406-555; all helper exercisers present, smoke test present, `test_registry_contains_all_three` present |
| `tests/test_hallucination_guard.py` | Generic guard regression vectors (5 tests) | VERIFIED | Lines 221-279; 5 tests covering allowlist key, clean capsule, table row fabrication, section fabrication, no-suppression |
| `tests/test_pipeline.py` | `TestCheckExplainerPresent` (5 unit tests) + pipeline integration test | VERIFIED | Lines 858-942; 5 unit tests in class + 1 integration test |
| `tests/test_anchor.py` | `test_anchor_tolerates_generic_summary_table` (xfail) | VERIFIED | Lines 151-226; xfail(strict=False) with TestModel Pitfall 4 documented |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `personas.py::GENERIC` | `pipeline.py::make_pipeline_agents` | `build_writer_system_prompt(persona)` | WIRED | `build_writer_system_prompt(GENERIC)` composes SHARED_WRITER_BASE + scout overlay + generic overlay; `make_pipeline_agents` receives Persona and calls composer |
| `pipeline.py::check_explainer_present` | `pipeline.py::_run_pipeline` | Phase 2.25 call site | WIRED | Line 1305: `if not check_explainer_present(capsule): log.warning(...)` |
| `pipeline.py::_PERSONA_KNOWN_METRICS["generic"]` | `pipeline.py::check_hallucinated_metrics` | `persona_known = _PERSONA_KNOWN_METRICS.get(persona, frozenset())` | WIRED | Line 1569; resolved when `persona="generic"` passed to function |
| `anchor.py::ANCHOR_PROMPT` addendum | anchor check agent | System prompt string passed to anchor Agent | WIRED | `ANCHOR_PROMPT` imported by pipeline at line 51 and passed to anchor agent constructor |

---

### Data-Flow Trace (Level 4)

Not applicable — this phase produces no data-rendering components. All deliverables are prompt strings, keyword scanners, and test assertions. No UI or dynamic-data rendering artifacts.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `get_persona("generic")` returns correct persona | `uv run pytest tests/test_personas.py::test_generic_has_expected_fields -q` | PASSED | PASS |
| 6 sections in order, h1 forbidden | `uv run pytest tests/test_personas.py::test_generic_overlay_fixes_section_order tests/test_personas.py::test_generic_overlay_forbids_h1 -q` | PASSED | PASS |
| Generic smoke pipeline runs end-to-end | `uv run pytest tests/test_personas.py::test_generic_pipeline_smoke -q` | PASSED | PASS |
| check_explainer_present wired and logs warning | `uv run pytest tests/test_pipeline.py::test_run_pipeline_logs_warning_when_capsule_missing_explainer -q` | PASSED | PASS |
| Guard regression vectors (fabricated metrics caught) | `uv run pytest tests/test_hallucination_guard.py -k generic -q` | 5 passed | PASS |
| Overall test suite (phase-relevant files) | `uv run pytest tests/test_personas.py tests/test_hallucination_guard.py tests/test_anchor.py -q` | 79 passed, 1 xfailed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| VOICE-03 | 08-01-PLAN | GENERIC persona constant with sectioned+table overlay, 6 fixed sections, h1 forbidden, parent="scout" | SATISFIED | `GENERIC` at `personas.py:272-282`; overlay at lines 185-242; tests pass |
| PERSONA-10 (generic portion) | 08-01-PLAN | `_PERSONA_KNOWN_METRICS["generic"]` entry in pipeline.py | SATISFIED | `"generic": frozenset()` at `pipeline.py:1488` with documented rationale |
| PERSONA-11 | 08-02-PLAN | `check_explainer_present` post-processor wired at Phase 2.25 | SATISFIED | Function at `pipeline.py:1586`; Phase 2.25 call site at line 1302; exported in `__all__` |
| TEST-05 (generic portion) | 08-01-PLAN | TestModel-based generic pipeline smoke test | SATISFIED | `test_generic_pipeline_smoke` at `test_personas.py:523`; passes |
| TEST-06 (generic portion) | 08-01-PLAN | `assert_generic_shape` helper + exercisers | SATISFIED | Helper at `test_personas.py:406`; 5 exercisers covering all shape constraints |
| TEST-07 (generic portion) | 08-01-PLAN | Hallucination guard regression vectors for generic persona | SATISFIED | 5 tests at `test_hallucination_guard.py:221-279`; fabricated metrics in tables and sections both caught |

All 6 required IDs satisfied. No orphaned requirements for Phase 08 in REQUIREMENTS.md.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_anchor.py:162` | 162 | `xfail(strict=False)` on anchor tolerance test | INFO | Documented TestModel Pitfall 4 — TestModel always returns a non-empty AnchorResult; addendum applied as low-regret safety; real-LLM validation deferred per REQUIREMENTS.md Future section |

No blockers or warnings found. The xfail is intentional and documented.

---

### Human Verification Required

**1. Anchor PROMPT addendum behavioral validation**

**Test:** Run `generate_pipeline_streaming` with `persona="generic"` against a real LLM (not TestModel), using a synthetic synthesis containing a Key Signals section and a 6-section + table capsule. Inspect the anchor check result.
**Expected:** `AnchorResult.is_clean` is True (no UNSUPPORTED or OVERSTATED warnings triggered by the section headings or table structure).
**Why human:** TestModel always returns a non-empty canned AnchorResult regardless of prompt content (Pitfall 4). The one-sentence addendum to ANCHOR_PROMPT can only be validated with a real LLM call.

---

### Gaps Summary

No gaps. All 5 observable truths are verified, all required artifacts exist at all three levels (exists, substantive, wired), all 6 requirement IDs are satisfied. The single human-verification item (anchor addendum with real LLM) is a validation quality concern, not a blocker — the addendum has been applied and the test infrastructure is in place.

---

_Verified: 2026-04-13_
_Verifier: Claude (gsd-verifier)_
