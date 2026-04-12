---
phase: 04-report-generation
plan: 02
subsystem: cli-integration
tags: [pydantic-ai, cli, streaming, error-handling, test-model]

# Dependency graph
requires:
  - phase: 04-report-generation-01
    provides: report.py with generate_report_streaming function and TestModel override support
  - phase: 03-context-assembly
    provides: PitcherContext model with to_prompt() and assemble_pitcher_context function
provides:
  - Complete end-to-end CLI pipeline: data -> context -> report generation with streaming
  - PITCHER_NARRATIVES_TEST_MODEL env var for API-free integration testing
  - ANTHROPIC_API_KEY error handling with clear user-facing message
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [PITCHER_NARRATIVES_TEST_MODEL env var for subprocess integration tests without API keys, UserError catch for missing API key with friendly stderr message]

key-files:
  created: []
  modified: [main.py, tests/test_cli.py]

key-decisions:
  - "Catch pydantic_ai.exceptions.UserError specifically (not bare Exception) for missing ANTHROPIC_API_KEY -- type-safe and follows research recommendations"
  - "PITCHER_NARRATIVES_TEST_MODEL env var triggers TestModel in main.py -- enables subprocess-based integration tests without API keys"
  - "Removed test_cli_output_has_role (tested temp verification output) and test_cli_custom_window 7d assertion (temp output format gone)"

patterns-established:
  - "Env-var-gated TestModel for subprocess integration tests: set PITCHER_NARRATIVES_TEST_MODEL=1 to run full pipeline without API key"

requirements-completed: [RPT-02, RPT-04]

# Metrics
duration: 2min
completed: 2026-03-26
---

# Phase 04 Plan 02: CLI Wiring Summary

**Full CLI pipeline wired: data -> context -> streaming report via Claude, with UserError catch for missing API key and PITCHER_NARRATIVES_TEST_MODEL env var for API-free integration testing**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-26T20:40:01Z
- **Completed:** 2026-03-26T20:42:16Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Replaced temporary verification output in main.py with full pipeline: load data, assemble context, generate streaming report
- Added ANTHROPIC_API_KEY error handling: catches UserError, prints clear message to stderr with link to console, exits 1
- Added PITCHER_NARRATIVES_TEST_MODEL env var support for API-free integration testing via TestModel
- Updated CLI tests: 11 tests passing (5 unit + 6 integration) including missing API key and report output verification
- Full test suite 104/104 green

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire main.py to generate report and update CLI tests** - `cdf2738` (feat)

## Files Created/Modified
- `main.py` - Full pipeline: data -> context -> report with UserError handling and test model support
- `tests/test_cli.py` - 11 tests: arg parsing, valid/invalid pitcher, report output, missing API key, no-args help

## Decisions Made
- Caught `UserError` from `pydantic_ai.exceptions` specifically rather than generic `Exception` with string matching -- type-safe and follows the research recommendations for error handling
- Used `PITCHER_NARRATIVES_TEST_MODEL` env var to gate `TestModel` injection in `main.py` -- this enables subprocess-based integration tests to run the full pipeline without requiring an API key
- Removed `test_cli_output_has_role` test (was testing temporary verification output format) and updated `test_cli_custom_window` assertion (no longer checks "7d window" string since temp output is gone)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
**ANTHROPIC_API_KEY required for real report generation.** To run the CLI with actual Claude-powered reports:
1. Get an API key from https://console.anthropic.com/
2. Export it: `export ANTHROPIC_API_KEY=your-key-here`
3. Run: `python main.py -p 592155`

For testing without an API key: `PITCHER_NARRATIVES_TEST_MODEL=1 python main.py -p 592155`

## Next Phase Readiness
- The v1.0 milestone pipeline is complete: data loading -> engine computation -> context assembly -> report generation
- All 104 tests pass without requiring ANTHROPIC_API_KEY
- Running with a real ANTHROPIC_API_KEY streams a scout-voice narrative report to the terminal

## Self-Check: PASSED

- FOUND: main.py
- FOUND: tests/test_cli.py
- FOUND: .planning/phases/04-report-generation/04-02-SUMMARY.md
- FOUND: commit cdf2738

---
*Phase: 04-report-generation*
*Completed: 2026-03-26*
