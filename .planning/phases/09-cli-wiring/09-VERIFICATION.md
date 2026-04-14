---
phase: 09-cli-wiring
verified: 2026-04-13T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 09: CLI Wiring Verification Report

**Phase Goal:** Users can select a persona via `--persona {scout,analyst,generic}` on `pitcher-narratives`, list available personas via `--list-personas`, and the other two CLIs explicitly reject the flag.
**Verified:** 2026-04-13
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                      | Status     | Evidence                                                                                                                                                             |
|-----|------------------------------------------------------------------------------------------------------------|------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1   | `pitcher-narratives --persona analyst -p 656302 -w 10` runs with analyst persona; scout/no-flag identical | ✓ VERIFIED | `--persona` argparse flag present in `cli.py:62-68` with `type=str.lower`, `choices=sorted(PERSONAS.keys())`, `default="scout"`; threaded into `generate_pipeline_streaming` and `write_pipeline_data_file` calls; tests `test_cli_persona_analyst_exits_0`, `test_cli_persona_uppercase_normalizes`, `test_cli_persona_scout_and_no_flag_are_identical` all PASS |
| 2   | `pitcher-narratives --list-personas` prints all three personas and exits 0 without LLM                    | ✓ VERIFIED | `_print_personas()` at `cli.py:77-92` iterates `sorted(PERSONAS.items())`, prints id + display_name + description; `main()` short-circuits before API key check and data loading; tests `test_cli_list_personas_exits_0_without_data`, `test_cli_list_personas_contains_display_names_and_descriptions` PASS |
| 3   | `--persona bogus` exits 2; `--persona SCOUT` normalizes to `scout`                                        | ✓ VERIFIED | `type=str.lower` on the argparse argument normalizes case before choices validation; invalid values cause argparse exit 2; tests `test_persona_invalid_exits_2` and `test_cli_invalid_persona_exits_2` assert exit 2 with valid choices in stderr; `test_persona_case_normalization` and `test_cli_persona_uppercase_normalizes` PASS |
| 4   | `pitcher-ask --persona scout` and `pitcher-scout --persona scout` both exit 2                             | ✓ VERIFIED | Neither `ask_cli.py` nor `scout_cli.py` contain `--persona` (grep returns 0 matches); argparse default rejects unknown flags with exit 2; `test_ask_cli_does_not_accept_persona` and `test_scout_cli_does_not_accept_persona` PASS |
| 5   | `pitcher-narratives -v --persona analyst` logs `persona=analyst` to stderr                                | ✓ VERIFIED | `cli.py:152-153`: `if args.verbose: log.info("persona=%s", args.persona)` runs before `_print_verbose_summary`; tests `test_cli_verbose_logs_persona` asserts `"persona=analyst" in result.stderr` and `test_cli_no_verbose_no_persona_log` asserts it absent without `-v` — both PASS |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact                             | Expected                                         | Status     | Details                                                                                              |
|--------------------------------------|--------------------------------------------------|------------|------------------------------------------------------------------------------------------------------|
| `src/pitcher_narratives/cli.py`      | `--persona` and `--list-personas` flags          | ✓ VERIFIED | Lines 62-73: both flags defined; `_print_personas()` helper at line 77; verbose persona log at 153; `args.persona` threaded into `write_pipeline_data_file` (line 186) and `generate_pipeline_streaming` (line 210)  |
| `src/pitcher_narratives/pipeline.py` | `persona` kwarg on rendering + execution paths  | ✓ VERIFIED | `_render_pipeline_data_sections(persona: str = "scout")` at line 883; `write_pipeline_data_file(persona: str = "scout")` at line 973; `_run_pipeline(persona: str = "scout")` at line 1228; `generate_pipeline_streaming(persona: str = "scout")` at line 1362 |
| `tests/test_cli.py`                  | CLI-01 through CLI-05 test coverage              | ✓ VERIFIED | 27 tests covering persona defaults, case normalization, invalid rejection, list-personas bypass, verbose logging, print-prompts per-persona — all PASS |
| `tests/test_ask_cli.py`              | `test_ask_cli_does_not_accept_persona`           | ✓ VERIFIED | Line 267: test present, subprocess asserts exit 2 with `--persona` or `unrecognized` in stderr — PASS |
| `tests/test_scout_cli.py`            | New file with `test_scout_cli_does_not_accept_persona` | ✓ VERIFIED | 101-line new file; 5 parse_args smoke tests + rejection test at line 80 — all 6 PASS |

---

### Key Link Verification

| From                     | To                                    | Via                                    | Status     | Details                                                                                                  |
|--------------------------|---------------------------------------|----------------------------------------|------------|----------------------------------------------------------------------------------------------------------|
| `cli.py: args.persona`   | `write_pipeline_data_file`            | `persona=args.persona` kwarg           | ✓ WIRED    | `cli.py:186`: `write_pipeline_data_file(ctx, args.pitcher, args.provider, persona=args.persona)`        |
| `cli.py: args.persona`   | `generate_pipeline_streaming`         | `persona=args.persona` kwarg           | ✓ WIRED    | `cli.py:210`: `generate_pipeline_streaming(ctx, ..., persona=args.persona, ...)`                        |
| `pipeline.py: persona str` | `get_persona()` → `Persona` object  | `persona_obj = get_persona(persona)` inside `_run_pipeline` | ✓ WIRED | `pipeline.py:1239`: `persona_obj = get_persona(persona)` before `make_pipeline_agents` |
| `pipeline.py: persona_obj` | `build_writer_system_prompt`        | `_render_pipeline_data_sections:944`   | ✓ WIRED    | `pipeline.py:944`: `build_writer_system_prompt(persona_obj)` used for WRITER section in print-prompts path |
| `make_pipeline_agents`   | writer agent system prompt            | `build_writer_system_prompt(persona)`  | ✓ WIRED    | `pipeline.py:1097`: `writer=_writer(build_writer_system_prompt(persona))`                               |
| `ask_cli.py` / `scout_cli.py` | no `--persona` flag             | argparse default rejection             | ✓ WIRED    | Zero occurrences of `--persona` in both source files; argparse exits 2 on unknown args by default       |

---

### Data-Flow Trace (Level 4)

Not applicable. This phase wires a CLI flag through string-to-string plumbing into an existing pipeline. There is no new dynamic data rendering — the persona string is passed to `get_persona()` which returns an existing `Persona` object from `PERSONAS`, then to `build_writer_system_prompt()` which returns a composed string. All data sources are static code constants, not DB queries or external fetches. The output shape (narrative report) is tested via TestModel end-to-end tests in `test_cli.py`.

---

### Behavioral Spot-Checks

| Behavior                                         | Command                                                       | Result                        | Status  |
|--------------------------------------------------|---------------------------------------------------------------|-------------------------------|---------|
| `--list-personas` exits 0 with all 3 personas   | `test_cli_list_personas_exits_0_without_data` (pytest)        | PASS (alphabetical ordering asserted) | ✓ PASS |
| `--persona analyst` completes with TestModel     | `test_cli_persona_analyst_exits_0` (pytest)                   | PASS (exit 0, non-empty stdout) | ✓ PASS |
| `--persona SCOUT` normalizes and runs            | `test_cli_persona_uppercase_normalizes` (pytest)              | PASS                          | ✓ PASS |
| `--persona bogus` exits 2                        | `test_cli_invalid_persona_exits_2` (pytest)                   | PASS (exit 2, choices in stderr) | ✓ PASS |
| `-v --persona analyst` logs `persona=analyst`    | `test_cli_verbose_logs_persona` (pytest)                      | PASS                          | ✓ PASS |
| `pitcher-ask --persona scout` exits 2            | `test_ask_cli_does_not_accept_persona` (pytest)               | PASS                          | ✓ PASS |
| `pitcher-scout --persona scout` exits 2          | `test_scout_cli_does_not_accept_persona` (pytest)             | PASS                          | ✓ PASS |

Full test run: **59 passed** in tests/test_cli.py + tests/test_ask_cli.py + tests/test_scout_cli.py.

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                               | Status       | Evidence                                                                                                  |
|-------------|-------------|---------------------------------------------------------------------------|--------------|-----------------------------------------------------------------------------------------------------------|
| CLI-01      | 09-01-PLAN  | `--persona {scout,analyst,generic}` with `type=str.lower`, choices, default="scout" | ✓ SATISFIED | `cli.py:62-68` exactly matches spec; `test_persona_default`, `test_persona_case_normalization`, `test_persona_invalid_exits_2` PASS |
| CLI-02      | 09-01-PLAN  | `--list-personas` prints registry and exits 0 without LLM                | ✓ SATISFIED | `cli.py:69-73` + `_print_personas()` + short-circuit in `main()` at line 115; integration tests PASS     |
| CLI-03      | 09-01-PLAN  | `--print-prompts` renders composed writer prompt for selected persona     | ✓ SATISFIED  | `_render_pipeline_data_sections` accepts `persona` kwarg; `write_pipeline_data_file` returns rendered text used directly for `--print-prompts`; `test_cli_print_prompts_uses_selected_persona` and `test_cli_print_prompts_uses_generic_persona` PASS |
| CLI-04      | 09-01-PLAN  | `-v/--verbose` logs `persona=<id>` to stderr                             | ✓ SATISFIED  | `cli.py:152-153`; `test_cli_verbose_logs_persona` PASS                                                    |
| CLI-05      | 09-01-PLAN  | No-flag and `--persona scout` produce identical runs                      | ✓ SATISFIED  | `default="scout"` on argparse; `test_cli_persona_scout_and_no_flag_are_identical` PASS; prompt-level equivalence via unit test + print-prompts test |
| CLI-06      | 09-02-PLAN  | `pitcher-ask` and `pitcher-scout` reject `--persona` with exit 2         | ✓ SATISFIED  | Zero `--persona` occurrences in `ask_cli.py` and `scout_cli.py`; both rejection tests PASS               |
| TEST-08     | 09-02-PLAN  | `test_ask_cli_does_not_accept_persona` and `test_scout_cli_does_not_accept_persona` exist and pass | ✓ SATISFIED | Both tests present in expected module locations; both PASS in the 59-test run                           |

**No orphaned requirements.** REQUIREMENTS.md maps CLI-01 through CLI-06 and TEST-08 to Phase 09; all seven are claimed by plans 09-01 and 09-02 and all are satisfied.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | — |

No stubs, placeholders, empty handlers, or TODO/FIXME items found in the phase-modified files (`cli.py`, `pipeline.py`, `tests/test_cli.py`, `tests/test_ask_cli.py`, `tests/test_scout_cli.py`).

---

### Human Verification Required

None. All five observable truths are mechanically locked by subprocess-level integration tests that exercise the full CLI surface. Visual appearance is not relevant (CLI output format is asserted in tests).

---

### Gaps Summary

No gaps. All five must-haves are verified at all applicable levels (exists, substantive, wired). The complete chain from `args.persona` string at the CLI boundary through `get_persona()` resolution to `build_writer_system_prompt()` at the writer-agent construction boundary is present and tested. The scope-guard tests on `pitcher-ask` and `pitcher-scout` confirm CLI-06 and TEST-08 are satisfied. The 59-test run covering all three test modules passes clean.

---

_Verified: 2026-04-13_
_Verifier: Claude (gsd-verifier)_
