---
phase: 09-cli-wiring
plan: 02
subsystem: testing

tags: [cli, argparse, scope-guard, persona, test-08, cli-06]

# Dependency graph
requires:
  - phase: 07-analyst-persona
    provides: ANALYST persona constant (used by writer-only CLI selection in 09-01)
  - phase: 08-generic-persona
    provides: GENERIC persona constant (used by writer-only CLI selection in 09-01)
provides:
  - "Negative test guard: tests/test_ask_cli.py::test_ask_cli_does_not_accept_persona"
  - "Negative test guard: tests/test_scout_cli.py::test_scout_cli_does_not_accept_persona"
  - "Baseline parse_args smoke coverage for scout_cli.py (previously uncovered)"
affects: [future-persona-work, cli-refactor, v1.11-planning]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scope-guard negative tests: assert argparse rejects flags that MUST NOT be added"
    - "Subprocess-based CLI integration with _test_env() key-stripping helper (mirrors tests/test_ask_cli.py and tests/test_cli.py)"

key-files:
  created:
    - tests/test_scout_cli.py
  modified:
    - tests/test_ask_cli.py

key-decisions:
  - "No CLI code changes: argparse default behavior (reject unknown flags with exit 2) is verified by test rather than reimplemented — CONTEXT.md § 'Integration Points' confirmed this approach"
  - "Five parse_args smoke tests for scout_cli.py give the new module non-trivial coverage so the rejection test doesn't live alone in an otherwise-empty file"
  - "Rejection test asserts stderr contains '--persona' OR 'unrecognized' (tolerant of argparse message format variations across Python versions)"

patterns-established:
  - "CLI scope-guard tests: one negative test per CLI that must NOT accept a cross-CLI flag, guarding against accidental copy-paste"

requirements-completed: [CLI-06, TEST-08]

# Metrics
duration: 5min
completed: 2026-04-14
---

# Phase 09 Plan 02: CLI Scope-Guard Tests Summary

**Lock in argparse rejection of `--persona` on `pitcher-ask` and `pitcher-scout` via negative tests — no CLI code changes, argparse's default "unrecognized arguments → exit 2" behavior verified by subprocess assertions.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-14T02:10:33Z
- **Completed:** 2026-04-14T02:15:24Z
- **Tasks:** 2
- **Files modified:** 2 (1 new, 1 extended)

## Accomplishments

- Added `test_ask_cli_does_not_accept_persona` to tests/test_ask_cli.py — the Q&A CLI is now guarded against copy-paste of the `--persona` flag
- Created tests/test_scout_cli.py (new module — previously no coverage) with 5 parse_args smoke tests plus `test_scout_cli_does_not_accept_persona`
- Both rejection tests verified: argparse's default behavior cleanly rejects `--persona` with exit code 2 and stderr containing "unrecognized arguments: --persona"
- Zero changes to src/pitcher_narratives/ask_cli.py or src/pitcher_narratives/scout_cli.py — `grep -n "\-\-persona"` returns no matches in either file (V3, V4 pass)
- TEST-08 requirement locked (both rejection tests exist in expected module locations); CLI-06 success criterion satisfied for the two non-writer CLIs

## Task Commits

Each task was committed atomically:

1. **Task 1: Add --persona rejection test to tests/test_ask_cli.py** - `7408490` (test)
2. **Task 2: Create tests/test_scout_cli.py with parse_args + rejection tests** - `b580946` (test)

**Plan metadata:** _pending final commit (docs: complete plan)_

## Files Created/Modified

- `tests/test_scout_cli.py` (NEW, 101 lines) - 5 parse_args smoke tests (`test_parse_window_default`, `test_parse_window_flag`, `test_parse_top_default`, `test_parse_top_flag`, `test_parse_verbose_flag`) + `test_scout_cli_does_not_accept_persona`; includes local `_test_env()` helper mirroring the pattern in tests/test_ask_cli.py
- `tests/test_ask_cli.py` (+29 lines) - Appended `test_ask_cli_does_not_accept_persona` after `test_ask_cli_thinking_flag`, reusing the existing `_test_env(PITCHER_NARRATIVES_TEST_MODEL="1")` helper

## Test Counts

| Module                       | Before | After | Delta |
|------------------------------|--------|-------|-------|
| tests/test_ask_cli.py        | 18     | 19    | +1    |
| tests/test_scout_cli.py      | 0      | 6     | +6    |
| **Combined for this plan**   | 18     | 25    | **+7**|

Isolated run of both modules: **25 passed** in 20.14s — all green.

## Argparse Rejection Message Format

The expected argparse stderr format matched reality cleanly:

```
usage: ... [-h] ...
scout_cli.py: error: unrecognized arguments: --persona scout
```

Both substrings `--persona` and `unrecognized` appear; the tolerant `OR` assertion (`"--persona" in result.stderr or "unrecognized" in result.stderr`) is defensive but not strictly necessary on this Python version. Leaving the OR-form as-is for future-proofing against argparse message changes.

## Decisions Made

- **No code changes to ask_cli.py or scout_cli.py.** The plan's operative insight (from 09-CONTEXT.md § "Integration Points") was that argparse already rejects unknown flags with exit 2 by default — the correct work is to lock that contract with a test, not to add explicit rejection logic. Verified by `grep "\-\-persona"` returning zero matches in both CLI source files post-plan.
- **Created tests/test_scout_cli.py from scratch rather than co-locating scout tests in test_cli.py or test_ask_cli.py.** `ls tests/` confirmed no prior scout_cli test module existed. A dedicated module matches the pattern of one-CLI-per-test-file already used (test_cli.py for narrative, test_ask_cli.py for ask).
- **Five smoke tests for parse_args, not full coverage.** Scope of 09-02 is the scope guard; full scout_cli coverage is out of scope for phase 09. Five tests give the module non-trivial content so the rejection test doesn't look orphaned.

## Deviations from Plan

None - plan executed exactly as written.

The plan explicitly anticipated argparse default behavior would suffice, and that held. No auto-fix deviations (Rules 1-3) needed; no architectural changes (Rule 4) required.

## Issues Encountered

**Full-suite parallel-execution noise (not caused by this plan):**
- Running `pytest tests/` showed 3 failures, but investigation confirmed all are external to 09-02:
  1. `tests/test_cli.py::test_pitcher_required` and `::test_cli_no_args_shows_help` — transient failures caused by the **parallel 09-01 executor** actively modifying `src/pitcher_narratives/cli.py`. Both tests PASS when run in isolation against the current cli.py state. Not a 09-02 regression.
  2. `tests/test_pipeline.py::TestAuditAndReviseSpecialists::test_clean_audit_returns_originals` — pre-existing pydantic-ai TestModel assertion error documented in STATE.md § "Blockers/Concerns" (pre-dates v1.9).
  3. `tests/test_analyst.py` — pre-existing ImportError (`_analyst_agent` no longer exists), documented in STATE.md § "Blockers/Concerns" (pre-dates v1.9).

All three are listed as pre-existing issues or caused by the parallel 09-01 executor's in-flight TDD RED phase. None are caused by 09-02.

**Isolated verification (the source of truth for this plan):**
- `uv run python -m pytest tests/test_ask_cli.py tests/test_scout_cli.py -v` → 25 passed.
- `uv run python -m pytest tests/test_ask_cli.py::test_ask_cli_does_not_accept_persona -q` → 1 passed.
- `uv run python -m pytest tests/test_scout_cli.py -q` → 6 passed.

## Verification — Goal-Backward Must-Haves

All five verification items from PLAN.md § `<verification>` pass:

1. ✅ `uv run python -m pytest tests/test_ask_cli.py::test_ask_cli_does_not_accept_persona -q` → 1 passed
2. ✅ `uv run python -m pytest tests/test_scout_cli.py -q` → 6 passed
3. ✅ `grep -n "--persona" src/pitcher_narratives/ask_cli.py` → no matches (0 occurrences)
4. ✅ `grep -n "--persona" src/pitcher_narratives/scout_cli.py` → no matches (0 occurrences)
5. ✅ Full suite regressions: isolated scope (test_ask_cli + test_scout_cli) is green; other failures predate this plan or are caused by parallel 09-01 execution (not by this plan's changes).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CLI-06 scope guard half (pitcher-ask + pitcher-scout) is locked. The companion plan 09-01 handles the positive half: `pitcher-narratives --persona {scout,analyst,generic}`.
- TEST-08 is complete — both rejection tests exist in their expected module locations and both pass.
- No downstream consumers of this plan's artifacts; it's a terminal scope guard.
- v1.10 completion depends on 09-01 landing; 09-02 has no remaining dependencies.

---
*Phase: 09-cli-wiring*
*Plan: 02*
*Completed: 2026-04-14*

## Self-Check: PASSED

**Files verified:**
- FOUND: tests/test_ask_cli.py (modified, +29 lines, test_ask_cli_does_not_accept_persona present on line 267)
- FOUND: tests/test_scout_cli.py (new, 101 lines, 6 test functions)

**Commits verified:**
- FOUND: 7408490 (test(09-02): add --persona rejection test to pitcher-ask)
- FOUND: b580946 (test(09-02): add tests/test_scout_cli.py with --persona rejection)

**Tests verified:**
- FOUND: tests/test_ask_cli.py::test_ask_cli_does_not_accept_persona — PASSED
- FOUND: tests/test_scout_cli.py::test_scout_cli_does_not_accept_persona — PASSED
- FOUND: all 5 scout_cli parse_args smoke tests — PASSED

**Source file verification:**
- CONFIRMED: src/pitcher_narratives/ask_cli.py has 0 occurrences of "--persona"
- CONFIRMED: src/pitcher_narratives/scout_cli.py has 0 occurrences of "--persona"
