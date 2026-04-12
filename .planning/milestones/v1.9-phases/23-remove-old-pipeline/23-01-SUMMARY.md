---
phase: 23-remove-old-pipeline
plan: 01
subsystem: infra
tags: [pipeline, cli, hallucination-guard, refactor]

# Dependency graph
requires:
  - phase: 15-specialist-writer-architecture
    provides: pipeline.py multi-agent specialist pipeline
provides:
  - HallucinationReport and check_hallucinated_metrics exported from pipeline.py
  - cli.py uses pipeline.py exclusively (no report.py dependency)
  - ask_cli.py uses pipeline path exclusively (no report.py dependency)
  - Standalone test_hallucination_guard.py with all 17 tests
affects: [23-remove-old-pipeline plan 02 — safe to delete report.py and test_report.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hallucination guard co-located with pipeline module for single import path"
    - "CLI modules import only from pipeline.py for report generation"

key-files:
  created:
    - tests/test_hallucination_guard.py
  modified:
    - src/pitcher_narratives/pipeline.py
    - src/pitcher_narratives/cli.py
    - src/pitcher_narratives/ask_cli.py

key-decisions:
  - "Hallucination guard appended to end of pipeline.py rather than a separate module — keeps the dependency graph simple"
  - "print_prompts replaced with reading pipeline data file to stderr — same spirit, no report.py dependency"

patterns-established:
  - "Pipeline-first CLI: all report generation routes through pipeline.py"

requirements-completed: [REM-03, CLI-01, CLI-02]

# Metrics
duration: 4min
completed: 2026-04-10
---

# Phase 23 Plan 01: Remove Old Pipeline Dependencies Summary

**Hallucination guard relocated to pipeline.py, both CLIs rewritten to use pipeline path exclusively with --pipeline flag removed**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-10T02:55:34Z
- **Completed:** 2026-04-10T02:59:45Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Relocated HallucinationReport, check_hallucinated_metrics, and all supporting constants/patterns from report.py to pipeline.py
- Rewrote cli.py to import exclusively from pipeline.py — removed --pipeline flag and old report.py branch
- Rewrote ask_cli.py to use pipeline path exclusively — removed --pipeline flag and old single-agent branch
- Created standalone test_hallucination_guard.py with all 17 hallucination guard tests passing from new import location

## Task Commits

Each task was committed atomically:

1. **Task 1: Relocate hallucination guard to pipeline.py and create standalone tests** - `3a785cf` (feat)
2. **Task 2: Rewrite cli.py and ask_cli.py to use pipeline path exclusively** - `3edd20e` (feat)

## Files Created/Modified
- `src/pitcher_narratives/pipeline.py` - Added hallucination guard section (HallucinationReport, check_hallucinated_metrics, _KNOWN_METRICS, _TRADITIONAL_STATS, regex patterns), updated __all__
- `src/pitcher_narratives/cli.py` - Removed --pipeline flag, replaced report.py imports with pipeline.py imports, removed if/else branching
- `src/pitcher_narratives/ask_cli.py` - Removed --pipeline flag, removed old single-agent branch, pipeline path is now the only path
- `tests/test_hallucination_guard.py` - New standalone test file with 17 hallucination guard tests importing from pipeline.py

## Decisions Made
- Hallucination guard appended to end of pipeline.py rather than a separate module — keeps the dependency graph simple and avoids creating a new module just for relocation
- print_prompts in cli.py replaced with reading the pipeline data file to stderr — same diagnostic spirit without depending on report.py internals

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functionality is fully wired.

## Next Phase Readiness
- report.py has zero imports from src/ modules (only tests/test_report.py remains)
- Plan 23-02 can safely delete report.py and test_report.py
- args.pipeline completely removed from both CLIs

---
*Phase: 23-remove-old-pipeline*
*Completed: 2026-04-10*
