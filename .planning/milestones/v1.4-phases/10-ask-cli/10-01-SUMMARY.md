---
phase: 10-ask-cli
plan: 01
subsystem: cli
tags: [argparse, resolver, analyst, streaming, name-extraction]

# Dependency graph
requires:
  - phase: 08-resolver
    provides: resolve() function for fuzzy pitcher name resolution
  - phase: 09-analyst
    provides: ask_question_streaming() for tool-calling Q&A agent
provides:
  - pitcher-ask CLI entry point composing resolver + analyst into user-facing command
  - _extract_pitcher_name() for extracting pitcher names from natural-language questions
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capitalization heuristic for name extraction: only accept fuzzy/ambiguous results when candidate words are capitalized (proper noun detection)"
    - "Multi-word fuzzy guard: require ALL words capitalized for multi-word fuzzy matches, any word capitalized for single-word"

key-files:
  created:
    - src/pitcher_narratives/ask_cli.py
    - tests/test_ask_cli.py
  modified:
    - pyproject.toml

key-decisions:
  - "Default provider is claude (not openai) per CONTEXT.md locked decision"
  - "Capitalization heuristic for fuzzy matches prevents common English words from triggering false positives (e.g., 'about' -> 'Abbott')"
  - "Multi-word fuzzy requires ALL words capitalized to prevent 'Johnson pitching' from resolving as single pitcher instead of ambiguous"

patterns-established:
  - "Name extraction from natural language: tokenize, strip possessives, try 3/2/1-word windows against resolver with proper noun heuristic"

requirements-completed: [CLI-01, CLI-02]

# Metrics
duration: 7min
completed: 2026-03-30
---

# Phase 10 Plan 01: Ask CLI Summary

**pitcher-ask CLI entry point composing name resolver and analyst agent into a natural-language Q&A command with capitalization-aware name extraction**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-30T16:06:07Z
- **Completed:** 2026-03-30T16:13:14Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Built `pitcher-ask` CLI that resolves pitcher names from natural-language questions and streams analytical answers
- Name extraction with possessive stripping and capitalization-aware fuzzy matching prevents false positives on common English words
- 17 tests covering parse_args, _extract_pitcher_name, and full subprocess integration paths (valid, not-found, ambiguous, no-question, missing-key, flags)
- All error paths produce clean stderr messages with exit code 1

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ask_cli.py module and register entry point** - `3bde148` (test: RED), `8c69aac` (feat: GREEN)
2. **Task 2: Comprehensive test suite for ask CLI** - `16f0bdb` (test: comprehensive suite + name extraction fix)

## Files Created/Modified
- `src/pitcher_narratives/ask_cli.py` - CLI entry point with _extract_pitcher_name, parse_args, main
- `tests/test_ask_cli.py` - 17 tests (5 parse_args unit, 5 extraction unit, 7 integration)
- `pyproject.toml` - Added pitcher-ask entry point to [project.scripts]

## Decisions Made
- Default provider set to `claude` per CONTEXT.md locked decision (differs from cli.py's `openai` default)
- Capitalization heuristic for name extraction: fuzzy/ambiguous results only accepted when candidate words are Title Case (proper nouns), preventing "about" -> "Abbott" and "Tell me" -> ambiguous false positives
- Multi-word fuzzy matches require ALL words capitalized (e.g., "Dylan Cease" passes, "Johnson pitching" does not) to avoid resolving ambiguous names plus common verbs as single-pitcher matches

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] False positive fuzzy matches on common English words**
- **Found during:** Task 1 (name extraction implementation)
- **Issue:** The plan's extraction strategy of accepting any fuzzy match from 3/2/1-word candidates caused common English words and phrases to resolve to pitchers (e.g., "about" -> "Abbott", "Tell me about" -> "Abbott, Andrew", "Johnson pitching" -> "Johnson, Ty")
- **Fix:** Added capitalization-aware heuristic: exact/exact_last always accepted, fuzzy/ambiguous require proper noun capitalization. Single-word: word must be capitalized. Multi-word: ALL words must be capitalized.
- **Files modified:** src/pitcher_narratives/ask_cli.py
- **Verification:** test_extract_not_found passes (gibberish returns None), test_extract_ambiguous passes (Johnson returns ambiguous)
- **Committed in:** 16f0bdb (Task 2 commit, refined from Task 1)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for correctness -- without the capitalization heuristic, common English sentences would match random pitchers. No scope creep.

## Issues Encountered
- Resolver's fuzzy matching at score_cutoff=70 is aggressive enough to match short common words to pitcher last names. This is by design in the resolver (Pitfall 1 from RESEARCH.md), handled at the extraction layer rather than modifying the resolver.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functionality is fully wired.

## Next Phase Readiness
- Phase 10 is the final phase of v1.4 milestone
- All v1.4 features (resolver, analyst, ask CLI) are integrated and tested
- 239 tests passing across full test suite

## Self-Check: PASSED

- All 3 created files exist on disk
- All 3 task commits verified in git log (3bde148, 8c69aac, 16f0bdb)
- 239 tests passing in full suite

---
*Phase: 10-ask-cli*
*Completed: 2026-03-30*
