---
phase: 23-remove-old-pipeline
verified: 2026-04-09T22:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 23: Remove Old Pipeline Verification Report

**Phase Goal:** The old single-agent reporting path is completely removed and the CLI routes all report generation through pipeline.py
**Verified:** 2026-04-09
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | report.py does not exist in the repository | VERIFIED | `test ! -f src/pitcher_narratives/report.py` succeeds |
| 2 | test_report.py does not exist in the repository | VERIFIED | `test ! -f tests/test_report.py` succeeds |
| 3 | No module in the codebase imports from report.py | VERIFIED | `grep -r "from pitcher_narratives.report import" src/ tests/` returns zero matches |
| 4 | Running the CLI without --pipeline generates a report via pipeline.py (flag is gone, pipeline is the default) | VERIFIED | --pipeline flag absent from both cli.py and ask_cli.py help output; cli.py imports generate_pipeline_streaming and write_pipeline_data_file directly from pipeline.py with no branching; ask_cli.py imports ask_question_pipeline and write_pipeline_data_file directly |
| 5 | anchor.py is unchanged and still importable by pipeline.py | VERIFIED | anchor.py has no commits during phase 23; `from pitcher_narratives.anchor import AnchorResult, AnchorWarning` succeeds; pipeline.py contains `from pitcher_narratives.anchor import` |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/report.py` | MUST NOT EXIST | VERIFIED (deleted) | File does not exist |
| `tests/test_report.py` | MUST NOT EXIST | VERIFIED (deleted) | File does not exist |
| `src/pitcher_narratives/pipeline.py` | Exports HallucinationReport, check_hallucinated_metrics | VERIFIED | class HallucinationReport at L1306, def check_hallucinated_metrics at L1433, both in __all__ |
| `src/pitcher_narratives/cli.py` | Imports from pipeline.py exclusively | VERIFIED | L91: `from pitcher_narratives.pipeline import`, zero references to report.py |
| `src/pitcher_narratives/ask_cli.py` | Uses pipeline path exclusively | VERIFIED | L117-118: imports from analyst and pipeline, zero references to report.py or ask_question_streaming |
| `tests/test_hallucination_guard.py` | Standalone hallucination guard tests from pipeline | VERIFIED | L7: imports from pitcher_narratives.pipeline, 17 tests passing |
| `src/pitcher_narratives/anchor.py` | Unchanged, still importable | VERIFIED | No phase-23 commits, import succeeds |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| cli.py | pipeline.py | `from pitcher_narratives.pipeline import check_hallucinated_metrics, generate_pipeline_streaming, write_pipeline_data_file` | WIRED | L91-95, all three functions called in main() |
| ask_cli.py | pipeline.py | `from pitcher_narratives.pipeline import write_pipeline_data_file` | WIRED | L118, called at L120 |
| ask_cli.py | analyst.py | `from pitcher_narratives.analyst import ask_question_pipeline` | WIRED | L117, called at L127 |
| pipeline.py | anchor.py | `from pitcher_narratives.anchor import AnchorResult, AnchorWarning` | WIRED | L69, used in anchor check logic |
| test_hallucination_guard.py | pipeline.py | `from pitcher_narratives.pipeline import HallucinationReport, check_hallucinated_metrics` | WIRED | L7, 17 tests exercise both exports |
| cli.py | report.py | Any import | NOT WIRED (correct) | Zero references to report.py |
| ask_cli.py | report.py | Any import | NOT WIRED (correct) | Zero references to report.py |

### Data-Flow Trace (Level 4)

Not applicable -- this phase deletes code and rewires imports. No new data-rendering artifacts introduced.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| pipeline.py exports hallucination guard | `python -c "from pitcher_narratives.pipeline import check_hallucinated_metrics, HallucinationReport"` | "pipeline import OK" | PASS |
| anchor.py still importable | `python -c "from pitcher_narratives.anchor import AnchorResult, AnchorWarning"` | "anchor import OK" | PASS |
| cli.py imports cleanly | `python -c "from pitcher_narratives.cli import main"` | "cli import OK" | PASS |
| ask_cli.py imports cleanly | `python -c "from pitcher_narratives.ask_cli import main"` | "ask_cli import OK" | PASS |
| Hallucination guard tests pass | `pytest tests/test_hallucination_guard.py -x -q` | 17 passed | PASS |
| Full test suite (excl. pre-existing failures) | `pytest -x -q --ignore=tests/test_analyst.py --ignore=tests/test_pipeline.py` | 249 passed | PASS |
| --pipeline flag absent from CLI | CLI help output grepped for "pipeline" | No matches | PASS |
| --pipeline flag absent from ask CLI | ask CLI help output grepped for "pipeline" | No matches | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REM-01 | 23-02 | report.py is deleted | SATISFIED | File does not exist |
| REM-02 | 23-02 | test_report.py is deleted | SATISFIED | File does not exist |
| REM-03 | 23-01 | All imports of report.py removed from cli.py and any other consumers | SATISFIED | grep returns zero matches across src/ and tests/ |
| CLI-01 | 23-01 | --pipeline flag removed from CLI | SATISFIED | Flag absent from both cli.py and ask_cli.py arg parsers and help output |
| CLI-02 | 23-01 | CLI generates reports via pipeline.py by default with no flag required | SATISFIED | cli.py unconditionally calls generate_pipeline_streaming; ask_cli.py unconditionally calls ask_question_pipeline |

No orphaned requirements -- all 5 phase-23 requirement IDs mapped to plans and satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/pitcher_narratives/config.py` | 4 | Docstring references "report.py" as historical context | Info | Stale comment; report.py no longer exists. Not a blocker. |
| `src/pitcher_narratives/anchor.py` | 3 | Docstring references "single-agent report pipeline (report.py)" | Info | Stale comment; report.py no longer exists. Not a blocker. |

No blocker or warning-level anti-patterns found. The two informational items are stale docstring references that mention report.py in a historical context but have no functional impact.

### Pre-existing Test Failures (Not Caused by Phase 23)

- `tests/test_analyst.py` -- imports `_analyst_agent` which no longer exists (pre-existing, out of scope per plan)
- `tests/test_pipeline.py::TestAuditAndReviseSpecialists::test_clean_audit_returns_originals` -- pydantic-ai TestModel assertion error (pre-existing, last modified in commit 05495cf before phase 23)

### Human Verification Required

None -- all success criteria are programmatically verifiable and have been verified.

### Gaps Summary

No gaps found. All 5 success criteria verified. The old single-agent reporting path (report.py) is completely removed, no module imports from it, the --pipeline flag is gone from both CLIs, and pipeline.py is the sole report generation path. anchor.py is unchanged and still wired into pipeline.py.

---

_Verified: 2026-04-09_
_Verifier: Claude (gsd-verifier)_
