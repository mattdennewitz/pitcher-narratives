# Phase 10: Ask CLI - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `ask_cli.py` — the CLI entry point that composes Phase 8 (resolver) and Phase 9 (analyst agent) into a user-facing `pitcher-ask` command. Register as a `[project.scripts]` entry point in pyproject.toml. This is a thin integration layer following the established pattern of cli.py and scout_cli.py.

</domain>

<decisions>
## Implementation Decisions

### CLI Design
- Positional question string: `pitcher-ask "Why is Cease's knuckle curve bad?"`
- Extract pitcher name from question text by passing words/phrases to the resolver until a match is found
- Entry point in pyproject.toml: `pitcher-ask = "pitcher_narratives.ask_cli:main"` — matches existing patterns
- Default provider: Claude (`anthropic:claude-sonnet-4-6`) — same as report pipeline

### Flags
- `--provider` flag: openai | claude | gemini (reuse PROVIDERS dict from report.py)
- `--thinking` flag: minimal | low | medium | high | xhigh (reuse THINKING_LEVELS from report.py)
- `--window` / `-w` flag: lookback window in days, default 30 (matches existing CLI)

### Error Handling & UX
- Disambiguation: print numbered list to stderr, exit code 1 with message "Multiple pitchers matched. Use a more specific name."
- Missing API key: same `UserError` pattern as existing cli.py
- No question provided: exit code 1 with usage hint
- Pitcher not found: exit code 1 with "No pitcher found matching [query]"

### Claude's Discretion
- argparse argument definitions (names, help text, metavar)
- Internal name extraction strategy from question text
- Verbose/quiet output flags

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cli.py` has argparse setup with `-p`, `-w`, `--provider`, `--thinking` flags — mirror the pattern
- `cli.py` has `UserError` exception class for clean error messages
- `report.py` has `PROVIDERS` dict and `THINKING_LEVELS` list
- `resolver.py` (Phase 8) has `resolve(query)` returning `ResolveResult`
- `analyst.py` (Phase 9) has `ask_question_streaming(pitcher_id, question, provider, thinking)` — the main public function
- `data.py` has `load_pitcher_data(pitcher_id, lookback_window)`
- `context.py` has `assemble_pitcher_context(pitcher_data)`

### Established Patterns
- `cli.py` uses `argparse.ArgumentParser` with `description=` and `add_argument` calls
- Error handling: try/except `UserError` → print to stderr, exit 1
- Missing API key: `UserError("Set ANTHROPIC_API_KEY")`
- Entry point: `def main(): ...` called by `[project.scripts]`

### Integration Points
- New file: `src/pitcher_narratives/ask_cli.py`
- Imports from: `resolver.py` (resolve, ResolveResult), `analyst.py` (ask_question_streaming), `data.py` (load_pitcher_data), `context.py` (assemble_pitcher_context), `report.py` (PROVIDERS, THINKING_LEVELS)
- pyproject.toml: add `pitcher-ask` to `[project.scripts]`
- Does NOT modify any existing module

</code_context>

<specifics>
## Specific Ideas

- The name extraction from question text should try longest phrases first (e.g., "Dylan Cease" before "Dylan" or "Cease")
- The CLI should stream output to stdout with no buffering (matching existing pattern)
- Consider a `--verbose` / `-v` flag for showing pitcher metadata (name, ID, handedness, role) before the answer

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
