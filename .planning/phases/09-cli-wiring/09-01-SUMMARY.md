---
phase: 09-cli-wiring
plan: 01
subsystem: cli
tags: [argparse, persona, cli-entrypoint, print-prompts, verbose-logging]

requires:
  - phase: 06-scout-persona-refactor
    provides: Persona dataclass, PERSONAS registry, build_writer_system_prompt, generate_pipeline_streaming accepting persona kwarg
  - phase: 07-analyst-persona
    provides: ANALYST persona instance with newsletter overlay
  - phase: 08-generic-persona
    provides: GENERIC persona instance with structured sectioned overlay + summary table
provides:
  - "--persona {scout,analyst,generic} flag on pitcher-narratives (default scout, type=str.lower normalizes case)"
  - "--list-personas flag that short-circuits before data/LLM and prints the registry to stdout"
  - "persona threaded into write_pipeline_data_file and generate_pipeline_streaming so --print-prompts renders the selected persona's composed writer prompt"
  - "-v/--verbose now logs persona=<id> to stderr"
  - "_render_pipeline_data_sections and write_pipeline_data_file accept persona kwarg (default scout preserves ask-path byte-identity)"
affects: [09-02-ask-cli-wiring, future CLI work]

tech-stack:
  added: []
  patterns:
    - "CLI short-circuit flag pattern: argparse stays permissive (required=False on -p), main() re-asserts requirements after the short-circuit branch"
    - "type=str.lower for case-insensitive argparse choices without cluttering the choices list"
    - "Persona string at CLI boundary, Persona object at rendering boundary: string flows args.persona → write_pipeline_data_file(persona=...) → _render_pipeline_data_sections(persona=...) → get_persona(persona) → build_writer_system_prompt(persona_obj)"

key-files:
  created: []
  modified:
    - src/pitcher_narratives/cli.py
    - src/pitcher_narratives/pipeline.py
    - tests/test_cli.py

key-decisions:
  - "Inline early-exit in main() for --list-personas (vs argparse.Action subclass) — simpler, reads sequentially, matches 09-CONTEXT.md"
  - "required=False on -p with main()-level re-assertion — needed so --list-personas can run standalone without supplying a pitcher"
  - "Default persona='scout' on _render_pipeline_data_sections and write_pipeline_data_file — preserves v1.9 byte-identity for the ask-pipeline path (ask_cli.py does not pass persona; the ANSWERER phase is persona-agnostic anyway)"
  - "4-space indent + alphabetical sort + blank line between persona blocks in --list-personas output — picked the wider indent option per 09-CONTEXT.md for scannability"
  - "Updated two pre-existing tests (test_pitcher_required unit, test_cli_no_args_shows_help integration) to reflect the new main()-level enforcement — argparse no longer raises for missing -p, main() does"

patterns-established:
  - "--list-personas short-circuit: runs before setup_logging, load_pitcher_data, and API key check — no LLM, no data file, no network"
  - "verbose persona logging: log.info('persona=%s', args.persona) emitted on stderr alongside existing pitcher/dates summary"

requirements-completed: [CLI-01, CLI-02, CLI-03, CLI-04, CLI-05]

duration: 11 min
completed: 2026-04-14
---

# Phase 09 Plan 01: CLI Persona Wiring Summary

**Exposes v1.10 personas on `pitcher-narratives` via `--persona {scout,analyst,generic}` and `--list-personas`, threads `args.persona` through `write_pipeline_data_file` and `generate_pipeline_streaming`, and logs `persona=<id>` under `-v`. Fifteen new CLI tests (6 unit + 9 integration) mechanically lock CLI-01 through CLI-05.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-14T02:10:44Z
- **Completed:** 2026-04-14T02:21:52Z
- **Tasks:** 2 (both TDD: RED → GREEN, no REFACTOR needed)
- **Files modified:** 3 (cli.py, pipeline.py, tests/test_cli.py)

## Accomplishments

- `pitcher-narratives --persona {scout,analyst,generic}` with `type=str.lower`, `choices=sorted(PERSONAS.keys())`, `default="scout"` (CLI-01).
- `pitcher-narratives --list-personas` prints all three personas in alphabetical order to stdout with display_name + description, exits 0 without loading data or calling the LLM (CLI-02).
- `--print-prompts` now threads `args.persona` into `write_pipeline_data_file` → `_render_pipeline_data_sections` → `build_writer_system_prompt(persona_obj)` so the WRITER section dumps the composed prompt for the *selected* persona, not the hardcoded scout default (CLI-03).
- `-v/--verbose` logs `persona=<id>` to stderr alongside the existing pitcher summary (CLI-04).
- No-flag and `--persona scout` produce observationally identical runs; prompt-level equivalence is locked by unit + print-prompts tests (CLI-05).
- 34/34 tests pass in `tests/test_cli.py` (6 new unit + 9 new integration + 19 pre-existing + 2 updated pre-existing = 34 active, 0 regressions).

## Task Commits

1. **Task 1 RED: failing unit tests for --persona / --list-personas** — `98989b3` (test)
2. **Task 1 GREEN: wire --persona and --list-personas into pitcher-narratives CLI + pipeline** — `a189814` (feat)
3. **Task 2: integration tests locking CLI-01 through CLI-05** — `201a260` (test)

_No REFACTOR commit — the GREEN implementation was already minimal and clean; no duplication to extract._

## Files Created/Modified

- `src/pitcher_narratives/cli.py` — added `from pitcher_narratives.personas import PERSONAS`, added `--persona` and `--list-personas` argparse flags, dropped `required=True` on `-p`, added `_print_personas()` helper, added `--list-personas` short-circuit in `main()`, added main()-level `-p` re-assertion, added `log.info("persona=%s", args.persona)` in the verbose branch, threaded `persona=args.persona` into both `write_pipeline_data_file()` and `generate_pipeline_streaming()` calls.
- `src/pitcher_narratives/pipeline.py` — added `persona: str = "scout"` kwarg to `_render_pipeline_data_sections` and `write_pipeline_data_file`; resolved `persona_obj = get_persona(persona)` once inside the renderer; replaced the line-938 hardcoded `build_writer_system_prompt(DEFAULT_PERSONA)` with `build_writer_system_prompt(persona_obj)`.
- `tests/test_cli.py` — added 6 unit tests for parse_args (persona defaults / normalization / invalid / list-personas boolean) and 9 integration subprocess tests (list-personas bypass, analyst/scout/uppercase/bogus runs, persona-identity equivalence, verbose log on/off, print-prompts per persona). Updated `test_pitcher_required` and `test_cli_no_args_shows_help` to reflect the new main()-level enforcement path (argparse no longer raises — main() exits 2 with `"-p/--pitcher is required"`).

## Decisions Made

- **Inline early-exit in `main()` for `--list-personas`** — chose over an `argparse.Action` subclass per 09-CONTEXT.md § "Claude's Discretion". Reads sequentially alongside the -p re-assertion, no side-effect action hidden inside argparse.
- **`required=False` on `-p` with manual re-assertion in `main()`** — the only way `--list-personas` can run standalone. Trade-off: two pre-existing tests (`test_pitcher_required` unit, `test_cli_no_args_shows_help` integration) needed updating. Both now pass and assert the correct new behavior.
- **Default `persona="scout"` on `_render_pipeline_data_sections` and `write_pipeline_data_file`** — the ask-pipeline path (`ask_cli.py → write_pipeline_data_file(..., question=...)`) does not pass persona. The scout default preserves v1.9 byte-identity for that path; the ANSWERER phase is persona-agnostic anyway (the `question is not None` branch renders ANSWERER, not WRITER), so the default is only defensive.
- **4-space indent + alphabetical sort + blank-line separator in --list-personas output** — picked the wider indent per 09-CONTEXT.md for readability.
- **No REFACTOR commit for Task 1** — the TDD RED produced minimal additions; the GREEN implementation was already clean. Skipping REFACTOR is allowed per the plan's TDD reference (`refactor if needed`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pre-existing tests updated to match new main()-level `-p` enforcement**

- **Found during:** Task 1 GREEN (full test_cli.py regression run after implementing `required=False`).
- **Issue:** `test_pitcher_required` (unit) and `test_cli_no_args_shows_help` (integration) asserted the *old* argparse-level behavior (`SystemExit(code=2)` from `parser.parse_args()` and `"usage:"` in stderr). The plan mandates option (i) — `required=False` with `main()` re-asserting and exiting 2 — which by design moves that check out of argparse. Without the update, the new behavior would look like a regression.
- **Fix:** Updated `test_pitcher_required` to assert `args.pitcher is None` when `-p` is omitted (since argparse no longer rejects it). Updated `test_cli_no_args_shows_help` to assert the new error string `"-p/--pitcher is required"` on stderr with exit 2. Both tests still validate the spirit of the original requirement (omitting -p is rejected) — just at the correct layer now.
- **Files modified:** `tests/test_cli.py`
- **Verification:** Both updated tests pass; integration test's custom message match confirms main()-level rejection path.
- **Committed in:** `a189814` (Task 1 GREEN)

---

**Total deviations:** 1 auto-fixed (1 blocking test update)
**Impact on plan:** Necessary for the plan-mandated `required=False` decision to land without a spurious regression. No scope creep — tests now assert the correct new behavior at the correct layer.

## Issues Encountered

- **Pre-existing test failure in `tests/test_pipeline.py::TestAuditAndReviseSpecialists::test_clean_audit_returns_originals`** — pydantic-ai TestModel assertion error (`"Plain response not allowed, but custom_output_text is set"`). STATE.md already lists this as a known blocker that predates Phase 09. Not caused by 09-01; full `tests/` run: 400 passed + 1 xfailed + 1 pre-existing failure, all 09-01 assertions green.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Ready for 09-02** (ask-cli wiring or next plan in the phase). `pitcher-ask` is explicitly untouched by this plan per the milestone constraint "narrative-only"; if 09-02 touches ask_cli.py, the `write_pipeline_data_file(..., persona=...)` default-scout behavior is already in place to preserve the ask path's current output.
- All five CLI requirements (CLI-01 through CLI-05) mechanically locked by tests. Any future regression will surface immediately.
- No blockers. Parallel-executor mode used `--no-verify` on all commits to avoid pre-commit hook contention with 09-02 — the orchestrator should run the full hook suite once both parallel agents complete.

---
*Phase: 09-cli-wiring*
*Completed: 2026-04-14*

## Self-Check: PASSED

- All 3 modified files exist on disk.
- All 3 task commits present in git log (`98989b3` RED, `a189814` GREEN, `201a260` integration tests).
- All 34 tests in `tests/test_cli.py` pass.
- Acceptance_criteria greps for Task 1 (9 cli.py checks, 4 pipeline.py checks) and Task 2 (16 test function greps, 3 content greps) all return expected counts.
