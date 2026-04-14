# Phase 09: CLI Wiring - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can select a persona via `--persona {scout,analyst,generic}` on `pitcher-narratives`, list available personas via `--list-personas`, and the other two CLIs (`pitcher-ask`, `pitcher-scout`) explicitly reject the flag. No pipeline, persona, or analyst-layer changes — this is the user-facing surface only.

</domain>

<decisions>
## Implementation Decisions

### --list-personas Output Format
- Plain text, one persona per block:
  - Line 1: `id` (lowercase, sorted alphabetically)
  - Line 2: indented `display_name`
  - Line 3: indented `description`
- Blank line between personas
- Sorted alphabetically by id
- No LLM/data calls — returns immediately with exit 0
- No color codes (pipe-friendly)

### Test Structure
- Extend `tests/test_cli.py` for pitcher-narratives persona tests (CLI-01 through CLI-05)
- Extend `tests/test_ask_cli.py` for `pitcher-ask --persona` rejection (CLI-06 ask portion / TEST-08)
- Create new `tests/test_scout_cli.py` for `pitcher-scout --persona` rejection (CLI-06 scout portion / TEST-08) — currently no coverage exists
- Argparse `SystemExit` assertions for reject cases
- Stub LLM calls via existing `PITCHER_NARRATIVES_TEST_MODEL` env var or TestModel pattern where end-to-end behavior needed

### Flag Interactions
- `--print-prompts` renders the composed writer prompt for the SELECTED persona (reads from `build_writer_system_prompt(get_persona(args.persona))`, not a hardcoded scout prompt)
- `--verbose` / `-v` logs `persona=<id>` to stderr alongside existing verbose output (pitcher name, game dates, pitch counts)
- `--list-personas` takes precedence: if both `--list-personas` and `-p` are provided, print personas and exit 0 (do NOT load pitcher data or call LLM)

### Claude's Discretion
- Exact argparse error message wording (argparse default is acceptable — naming valid choices is automatic)
- Whether to use `argparse.Action` subclass for `--list-personas` early-exit or handle inline in main()
- Indentation for list-personas block (2 or 4 spaces — pick whichever reads better in terminal)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `personas.py` — `PERSONAS` registry, `get_persona()`, `DEFAULT_PERSONA`, `build_writer_system_prompt()`
- `cli.py` (pitcher-narratives) — existing argparse setup with `-p`, `-w`, `-v`, `--print-prompts`
- `ask_cli.py` (pitcher-ask) — argparse setup, no --persona today
- `scout_cli.py` (pitcher-scout) — argparse setup, no --persona today
- `pipeline.py:generate_pipeline_streaming(..., persona="scout")` — already accepts persona kwarg from Phase 06

### Established Patterns
- argparse-based CLI parsing in all three CLI modules
- `PITCHER_NARRATIVES_TEST_MODEL=1` env var for stubbing LLM calls in tests
- Existing test pattern: invoke CLI main() with patched `sys.argv`, assert on stdout/stderr/exit code

### Integration Points
- `cli.py` — add `--persona` (argparse with `type=str.lower`, `choices=sorted(PERSONAS.keys())`, `default="scout"`), add `--list-personas` (action="store_true"), thread `args.persona` into `generate_pipeline_streaming()` and `--print-prompts` branch
- `ask_cli.py` — no action needed IF argparse already rejects unknown flags (default behavior). Verify via test.
- `scout_cli.py` — same as ask_cli.py. Verify via test.
- `tests/test_cli.py` — add tests for persona selection, case normalization, --list-personas, invalid persona, --verbose logging
- `tests/test_ask_cli.py` — add test for `--persona` rejection
- `tests/test_scout_cli.py` (NEW) — add test for `--persona` rejection

</code_context>

<specifics>
## Specific Ideas

- argparse signature for --persona on pitcher-narratives:
  ```python
  parser.add_argument(
      "--persona",
      type=str.lower,
      choices=sorted(PERSONAS.keys()),
      default="scout",
      help="Writer persona to use (default: scout)",
  )
  ```
- --list-personas sample output:
  ```
  analyst
      Analyst
      Newsletter-style analysis -- 450-800 words, teaching voice for analytically-inclined fans

  generic
      Generic
      Sectioned report with summary table -- 300-500 words

  scout
      Scout
      Front-office scouting capsule -- 2-3 paragraphs, conversational, sabermetric voice
  ```

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
