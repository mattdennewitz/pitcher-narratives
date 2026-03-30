---
phase: 10-ask-cli
verified: 2026-03-30T17:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 10: Ask CLI Verification Report

**Phase Goal:** Users have a complete command-line workflow for asking pitcher questions by name
**Verified:** 2026-03-30T17:00:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `pitcher-ask "How is Cease pitching?"` resolves Cease, loads data, streams an answer, exits 0 | VERIFIED | Subprocess smoke test: exit 0, non-empty JSON tool output |
| 2 | `pitcher-ask --provider openai --thinking low "..."` uses specified provider and thinking | VERIFIED | `test_ask_cli_provider_flag` and `test_ask_cli_thinking_flag` both pass; argparse choices enforce validity |
| 3 | `pitcher-ask "How is Johnson pitching?"` prints numbered disambiguation list to stderr, exits 1 | VERIFIED | Subprocess: "Multiple pitchers matched. Use a more specific name." + 5 numbered candidates, exit 1 |
| 4 | `pitcher-ask` with no question prints usage hint to stderr, exits 1 | VERIFIED | Subprocess: `Usage: pitcher-ask "How is Cease pitching?"` to stderr, exit 1 |
| 5 | `pitcher-ask "How is Xyzzy pitching?"` prints not-found error to stderr, exits 1 | VERIFIED | Subprocess: "No pitcher found matching 'How is Xyzzyplugh pitching?'", exit 1 |
| 6 | Missing API key without test model exits 1 with the relevant env var name | VERIFIED | Subprocess: "Error: ANTHROPIC_API_KEY not set.", exit 1 |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/ask_cli.py` | CLI entry point composing resolver + analyst | VERIFIED | 195 lines; exports `main`, `parse_args`, `_extract_pitcher_name`; fully substantive |
| `tests/test_ask_cli.py` | Unit + integration tests, min 80 lines | VERIFIED | 225 lines, 17 test functions (5 parse_args unit, 5 extraction unit, 7 integration) |
| `pyproject.toml` | pitcher-ask entry point registration | VERIFIED | Line 19: `pitcher-ask = "pitcher_narratives.ask_cli:main"` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `ask_cli.py` | `pitcher_narratives.resolver` | `resolve()` call in `_extract_pitcher_name` | WIRED | Line 43: lazy import inside function; line 71: `resolve(candidate)` called |
| `ask_cli.py` | `pitcher_narratives.analyst` | `ask_question_streaming()` call in `main` | WIRED | Line 171: import; line 183: called with all required args |
| `pyproject.toml` | `src/pitcher_narratives/ask_cli.py` | `[project.scripts]` entry point | WIRED | Line 19: `pitcher-ask = "pitcher_narratives.ask_cli:main"` |
| `ask_cli.py` | `pitcher_narratives.report.PROVIDERS` | Flag validation (PLAN specified import) | NOTE | Not imported; choices hard-coded as `["openai", "claude", "gemini"]` inline in `parse_args`. Functionally equivalent -- values are identical. Non-blocking. |

### Data-Flow Trace (Level 4)

This phase is a CLI entry point that coordinates existing data modules; it does not render independent dynamic data. Data flows through the wired call chain: `resolve()` -> `load_pitcher_data()` -> `assemble_pitcher_context()` -> `ask_question_streaming()`. The smoke test confirmed real pitcher data (Cease's arsenal, TTO tables, platoon data) flows from Statcast parquet files through to streamed output.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `ask_cli.py` | `pitcher_data` | `load_pitcher_data(pitcher_id, args.window)` | Yes -- Statcast parquet files | FLOWING |
| `ask_cli.py` | `ctx` | `assemble_pitcher_context(pitcher_data)` | Yes -- derived from real data | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Valid question exits 0 with output | `PITCHER_NARRATIVES_TEST_MODEL=1 python -m pitcher_narratives.ask_cli "How is Cease pitching?"` | Exit 0, JSON tool output with full pitcher context | PASS |
| Not-found exits 1 with message | Same + Xyzzyplugh | "No pitcher found matching ...", exit 1 | PASS |
| Ambiguous exits 1 with numbered list | Same + "Johnson pitching?" | "Multiple pitchers matched." + 5 candidates, exit 1 | PASS |
| No question exits 1 with usage | No args | `Usage: pitcher-ask "..."`, exit 1 | PASS |
| Missing API key exits 1 with env var | No test model, no keys | "Error: ANTHROPIC_API_KEY not set.", exit 1 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CLI-01 | 10-01-PLAN.md | User can ask a question via CLI entry point | SATISFIED | `pitcher-ask` registered in `pyproject.toml`; smoke test confirms exit 0 with real output |
| CLI-02 | 10-01-PLAN.md | CLI supports `--provider` and `--thinking` flags matching existing report CLI | SATISFIED | Both flags present in `parse_args` with matching choices (`openai/claude/gemini`, `minimal/low/medium/high/xhigh`) and default `claude`/`high`; integration tests pass |

No orphaned requirements: REQUIREMENTS.md traceability table maps only CLI-01 and CLI-02 to Phase 10, both satisfied.

### Anti-Patterns Found

No anti-patterns found. Scan of `src/pitcher_narratives/ask_cli.py` and `tests/test_ask_cli.py`:

- Zero TODO/FIXME/PLACEHOLDER comments
- No stub return patterns (`return null`, `return []`, `return {}`)
- No hardcoded empty data passed to rendering paths
- All handlers are fully implemented (not just `e.preventDefault()` or `console.log`)
- SUMMARY.md correctly reports "Known Stubs: None"

### Human Verification Required

One item is worth a manual smoke test with a real API key if desired, but is not blocking:

**Full-stack streaming with a real LLM provider**

- **Test:** Set `ANTHROPIC_API_KEY` and run `pitcher-ask "Why is Cease's knuckle curve underperforming?"` without the test model override.
- **Expected:** Streaming narrative answer printed to stdout, exit 0.
- **Why human:** Requires a real API key and live API call. The test model confirms the entire call chain is wired; this verifies the streaming output renders correctly to a terminal.

### Gaps Summary

No gaps. All six observable truths verified, all artifacts substantive and wired, all 17 tests pass, full suite green at 239 tests.

The sole noted deviation -- inlining `["openai", "claude", "gemini"]` in `parse_args` rather than importing `PROVIDERS` from `report.py` -- is a valid implementation choice. The values are identical and the integration tests confirm all three providers are accepted. If `PROVIDERS` gains new keys in a future release, `ask_cli.py` would need a manual update, but this is a maintenance concern, not a current defect.

---

_Verified: 2026-03-30T17:00:00Z_
_Verifier: Claude (gsd-verifier)_
