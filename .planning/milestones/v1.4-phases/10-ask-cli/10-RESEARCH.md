# Phase 10: Ask CLI - Research

**Researched:** 2026-03-30
**Domain:** Python CLI integration (argparse + existing modules)
**Confidence:** HIGH

## Summary

Phase 10 is a thin integration layer -- a new `ask_cli.py` module that composes the resolver (Phase 8) and analyst agent (Phase 9) into a user-facing `pitcher-ask` CLI command. All the hard work (fuzzy name resolution, agent tool-calling, streaming output) is already implemented. This phase wires them together with argument parsing, error handling, and a pyproject.toml entry point.

The codebase has two prior CLI modules (`cli.py` and `scout_cli.py`) that establish clear patterns for argparse setup, error handling, test model support, and subprocess-based integration testing. The new module follows these patterns exactly -- no new libraries, no architectural decisions, no new dependencies.

**Primary recommendation:** Mirror `cli.py` structure exactly: `parse_args()` + `main()` with lazy imports, `_API_KEYS` dict for pre-flight key check, `PITCHER_NARRATIVES_TEST_MODEL` env var for testability, and `if __name__ == "__main__": main()` guard for `-m` module invocation in tests.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Positional question string: `pitcher-ask "Why is Cease's knuckle curve bad?"`
- Extract pitcher name from question text by passing words/phrases to the resolver until a match is found
- Entry point in pyproject.toml: `pitcher-ask = "pitcher_narratives.ask_cli:main"` -- matches existing patterns
- Default provider: Claude (`anthropic:claude-sonnet-4-6`) -- same as report pipeline
- `--provider` flag: openai | claude | gemini (reuse PROVIDERS dict from report.py)
- `--thinking` flag: minimal | low | medium | high | xhigh (reuse THINKING_LEVELS from report.py)
- `--window` / `-w` flag: lookback window in days, default 30 (matches existing CLI)
- Disambiguation: print numbered list to stderr, exit code 1 with message "Multiple pitchers matched. Use a more specific name."
- Missing API key: same `UserError` pattern as existing cli.py (note: cli.py uses inline print+exit, not a UserError class -- follow the actual pattern)
- No question provided: exit code 1 with usage hint
- Pitcher not found: exit code 1 with "No pitcher found matching [query]"

### Claude's Discretion
- argparse argument definitions (names, help text, metavar)
- Internal name extraction strategy from question text
- Verbose/quiet output flags

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLI-01 | User can ask a question via CLI entry point (e.g., `pitcher-ask "Why is Cease's knuckle curve bad?"`) | Positional argument in argparse, resolver extracts name, analyst streams answer. All building blocks exist. |
| CLI-02 | CLI supports `--provider` and `--thinking` flags matching existing report CLI | Reuse `PROVIDERS` dict and `THINKING_LEVELS` list from `report.py`. Same argparse patterns as `cli.py`. |

</phase_requirements>

## Standard Stack

### Core

No new libraries. Everything is already in the project.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| argparse | stdlib | CLI argument parsing | Used by cli.py and scout_cli.py already |
| python-dotenv | >=1.2.2 | Load .env for API keys | Already in pyproject.toml dependencies |

### Reusable Imports from Existing Modules

| Module | Import | Purpose |
|--------|--------|---------|
| `resolver` | `resolve`, `ResolveResult` | Fuzzy name resolution from question text |
| `analyst` | `ask_question_streaming` | Tool-calling agent with streaming output |
| `data` | `load_pitcher_data` | Load Statcast + aggregation data for pitcher |
| `context` | `assemble_pitcher_context` | Build PitcherContext from PitcherData |
| `report` | `PROVIDERS`, `THINKING_LEVELS` | Provider/thinking config dicts |

### Alternatives Considered

None -- this is pure integration of existing modules. No library choices to make.

## Architecture Patterns

### Module Structure

```
src/pitcher_narratives/
    ask_cli.py          # NEW -- the only new file
    cli.py              # Existing pattern to mirror
    scout_cli.py        # Second existing pattern reference
    resolver.py         # Phase 8 -- called by ask_cli
    analyst.py          # Phase 9 -- called by ask_cli
    data.py             # Data loading
    context.py          # Context assembly
    report.py           # PROVIDERS + THINKING_LEVELS constants
```

### Pattern 1: CLI Module Structure (from cli.py)

**What:** Every CLI module follows: `parse_args()` function + `main()` entry point + `__name__` guard
**When to use:** Always -- this is the established codebase pattern

```python
# Source: src/pitcher_narratives/cli.py (lines 21-53, 102-184)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument(...)
    return parser.parse_args()

def main() -> None:
    load_dotenv()
    args = parse_args()
    # Lazy imports for speed
    from pitcher_narratives.data import load_pitcher_data
    # ... orchestration ...

if __name__ == "__main__":
    main()
```

### Pattern 2: Error Handling (from cli.py)

**What:** Print error to stderr, exit with code 1. No custom exception class needed -- cli.py does it inline.
**When to use:** All error paths (missing pitcher, ambiguous, missing API key, no question)

```python
# Source: src/pitcher_narratives/cli.py (lines 109-113, 143-146)
try:
    pitcher_data = load_pitcher_data(args.pitcher, args.window)
except ValueError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)

# API key check
if model_override is None and not os.environ.get(_API_KEYS[args.provider]):
    env_var = _API_KEYS[args.provider]
    print(f"Error: {env_var} not set.", file=sys.stderr)
    sys.exit(1)
```

### Pattern 3: Test Model Override (from cli.py)

**What:** Check `PITCHER_NARRATIVES_TEST_MODEL` env var to inject `TestModel()` instead of hitting a real LLM API.
**When to use:** Must be in ask_cli.py for integration tests to work without API keys.

```python
# Source: src/pitcher_narratives/cli.py (lines 136-140)
model_override = None
if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
    from pydantic_ai.models.test import TestModel
    model_override = TestModel()
```

### Pattern 4: Name Extraction from Question Text

**What:** Extract a pitcher name from a natural-language question by trying progressively shorter phrases against the resolver.
**When to use:** Core logic unique to ask_cli.py.

Strategy (from CONTEXT.md: "try longest phrases first"):
1. Tokenize the question into words
2. Generate candidate phrases: all contiguous 3-word, then 2-word, then 1-word subsequences
3. For each candidate, call `resolve(candidate)`
4. First result with `match_type` in `("exact", "exact_last", "fuzzy")` wins
5. If all candidates return `ambiguous` or `not_found`, use the best ambiguous result (or report not found)

This is a simple extraction heuristic -- no NLP, no LLM. The resolver does all the fuzzy matching work.

### Pattern 5: Default Provider Difference

**What:** The ask CLI defaults to `claude` provider while the report CLI defaults to `openai`.
**When to use:** In the `--provider` argument definition.

```python
# ask_cli.py uses claude as default (per CONTEXT.md decision)
parser.add_argument("--provider", choices=["openai", "claude", "gemini"], default="claude")
# cli.py uses openai as default
```

### Anti-Patterns to Avoid

- **Do NOT use `UserError` class:** Despite CONTEXT.md mentioning it, cli.py does NOT define a `UserError` class. It uses inline `print(msg, file=sys.stderr); sys.exit(1)`. Follow the actual codebase pattern.
- **Do NOT use `typer` or `click`:** The project uses argparse. Stay consistent.
- **Do NOT import at module level if it causes slow startup:** Follow cli.py's pattern of lazy imports inside `main()`.
- **Do NOT call the LLM for name extraction:** This was explicitly ruled out of scope in REQUIREMENTS.md ("LLM-powered name resolution" is out of scope).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Name resolution | Custom string matching | `resolver.resolve()` | Already handles fuzzy, exact, disambiguation |
| LLM orchestration | Custom API calls | `analyst.ask_question_streaming()` | Already handles streaming, tool-calling, provider switching |
| Provider/thinking config | New config dicts | `report.PROVIDERS`, `report.THINKING_LEVELS` | Single source of truth, already tested |
| Data loading + context | Custom data pipeline | `data.load_pitcher_data()` + `context.assemble_pitcher_context()` | Full pipeline already exists |

**Key insight:** ask_cli.py should contain approximately zero business logic. It is pure glue code: parse args, extract name, resolve, load data, assemble context, call agent, handle errors.

## Common Pitfalls

### Pitfall 1: Name Extraction Greediness

**What goes wrong:** A naive "try every word" approach matches common words (e.g., "Why" could fuzzy-match a pitcher name at a low score).
**Why it happens:** The resolver uses a score cutoff of 70, but short common English words can still match short last names.
**How to avoid:** Try longest phrases (3-word, 2-word) before single words. Accept the first `exact` or `exact_last` match immediately. For `fuzzy` matches on single words, only accept if no better result was found from longer phrases.
**Warning signs:** Common English words resolving to pitcher names in tests.

### Pitfall 2: Forgetting to Skip API Key Check in Test Mode

**What goes wrong:** Integration tests fail because API key is not set, even though `PITCHER_NARRATIVES_TEST_MODEL` is set.
**Why it happens:** The pre-flight API key check runs before the test model override is evaluated.
**How to avoid:** Check for test model override BEFORE the API key check, exactly as cli.py does (lines 136-146).
**Warning signs:** Tests failing with "API_KEY not set" despite `PITCHER_NARRATIVES_TEST_MODEL=1`.

### Pitfall 3: Positional Argument with Dashes

**What goes wrong:** `pitcher-ask "Why is Cease's bad?"` -- the shell passes the quoted string correctly, but argparse may misinterpret arguments starting with `-` as flags.
**Why it happens:** argparse treats strings starting with `-` as option flags by default.
**How to avoid:** Use `nargs='?'` or handle via argparse's `REMAINDER` mode -- or more simply, since the question is a single positional string in quotes, standard argparse handles this fine. Test with questions containing hyphens.
**Warning signs:** `error: unrecognized arguments` for questions containing dashes.

### Pitfall 4: Disambiguation Exit Code

**What goes wrong:** The CLI prints the disambiguation list but continues to try loading data with `pitcher_id=None`.
**Why it happens:** Not checking `ResolveResult.match_type` before proceeding.
**How to avoid:** Check `result.match_type` immediately after resolve. If `ambiguous`, print candidates to stderr and `sys.exit(1)`. If `not_found`, print error and `sys.exit(1)`.
**Warning signs:** TypeError when passing `None` as pitcher_id to `load_pitcher_data()`.

### Pitfall 5: Default Provider Inconsistency

**What goes wrong:** Default provider is `openai` (copied from cli.py) but CONTEXT.md says default should be `claude`.
**Why it happens:** Copy-paste from cli.py without updating the default.
**How to avoid:** Set `default="claude"` in the `--provider` argument, per the locked decision.
**Warning signs:** Users getting OpenAI errors when they expected Claude to be the default.

## Code Examples

### ask_cli.py Skeleton

```python
# Source: Derived from cli.py pattern + CONTEXT.md decisions
"""CLI entry point for pitcher Q&A.

Parses a natural-language question, resolves the pitcher name,
loads data, and streams an answer from the analyst agent.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv


def _extract_pitcher_name(question: str) -> str | None:
    """Extract a pitcher name from a question by trying phrases against the resolver.

    Tries 3-word, 2-word, then 1-word contiguous subsequences.
    Returns the query string that matched, or None.
    """
    from pitcher_narratives.resolver import resolve

    words = question.split()
    # Try progressively shorter phrases
    for width in (3, 2, 1):
        for i in range(len(words) - width + 1):
            candidate = " ".join(words[i : i + width])
            result = resolve(candidate)
            if result.match_type in ("exact", "exact_last", "fuzzy"):
                return candidate
            # Track ambiguous for fallback
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask a question about a pitcher's recent performance"
    )
    parser.add_argument("question", nargs="?", help="Question about a pitcher")
    parser.add_argument("-w", "--window", type=int, default=30, ...)
    parser.add_argument("--provider", choices=["openai", "claude", "gemini"], default="claude", ...)
    parser.add_argument("--thinking", choices=["minimal", "low", "medium", "high", "xhigh"], default="high", ...)
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if not args.question:
        print("Usage: pitcher-ask \"Why is Cease's knuckle curve bad?\"", file=sys.stderr)
        sys.exit(1)

    # Resolve pitcher name from question
    from pitcher_narratives.resolver import resolve
    # ... name extraction + resolve logic ...
    # ... handle ambiguous, not_found ...

    # Test model support
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        from pydantic_ai.models.test import TestModel
        model_override = TestModel()

    # API key pre-flight
    _API_KEYS = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
    if model_override is None and not os.environ.get(_API_KEYS[args.provider]):
        print(f"Error: {_API_KEYS[args.provider]} not set.", file=sys.stderr)
        sys.exit(1)

    # Load data + assemble context
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.analyst import ask_question_streaming

    data = load_pitcher_data(pitcher_id, args.window)
    ctx = assemble_pitcher_context(data)
    ask_question_streaming(args.question, ctx, data,
                           provider=args.provider, thinking=args.thinking,
                           _model_override=model_override)


if __name__ == "__main__":
    main()
```

### Integration Test Pattern (from test_cli.py)

```python
# Source: tests/test_cli.py (lines 81-92)
def test_ask_cli_valid_question_exit_0():
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.ask_cli",
         "How is Cease pitching?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert result.stdout.strip()
```

### Disambiguation Output Pattern

```python
# Print numbered list to stderr, then exit 1
if result.match_type == "ambiguous":
    print("Multiple pitchers matched. Use a more specific name.", file=sys.stderr)
    for i, (pid, name) in enumerate(result.candidates, 1):
        print(f"  {i}. {name} (ID: {pid})", file=sys.stderr)
    sys.exit(1)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| N/A | N/A | N/A | N/A -- this is a new CLI wiring existing modules |

No relevant changes to track. All dependencies are stable and already in use.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_ask_cli.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLI-01a | Positional question argument parsed correctly | unit | `uv run pytest tests/test_ask_cli.py::test_parse_question_positional -x` | No -- Wave 0 |
| CLI-01b | Name extracted from question text | unit | `uv run pytest tests/test_ask_cli.py::test_extract_pitcher_name -x` | No -- Wave 0 |
| CLI-01c | Valid question exits 0 with output | integration | `uv run pytest tests/test_ask_cli.py::test_ask_cli_valid_question_exit_0 -x` | No -- Wave 0 |
| CLI-01d | Pitcher not found exits 1 with error | integration | `uv run pytest tests/test_ask_cli.py::test_ask_cli_not_found_exit_1 -x` | No -- Wave 0 |
| CLI-01e | Ambiguous name exits 1 with numbered list | integration | `uv run pytest tests/test_ask_cli.py::test_ask_cli_ambiguous_exit_1 -x` | No -- Wave 0 |
| CLI-01f | No question exits 1 with usage hint | integration | `uv run pytest tests/test_ask_cli.py::test_ask_cli_no_question_exit_1 -x` | No -- Wave 0 |
| CLI-02a | --provider flag accepted | unit | `uv run pytest tests/test_ask_cli.py::test_parse_provider_flag -x` | No -- Wave 0 |
| CLI-02b | --thinking flag accepted | unit | `uv run pytest tests/test_ask_cli.py::test_parse_thinking_flag -x` | No -- Wave 0 |
| CLI-02c | Missing API key exits 1 | integration | `uv run pytest tests/test_ask_cli.py::test_ask_cli_missing_api_key_exit_1 -x` | No -- Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_ask_cli.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_ask_cli.py` -- covers CLI-01 and CLI-02 (all test cases above)
- No new fixtures needed -- reuse `_test_env()` helper pattern from test_cli.py

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python, polars, pydantic-ai, Claude -- no new dependencies
- **Data format:** Static parquet + CSV files, no live API calls
- **Python version:** 3.14+
- **Naming:** snake_case.py for modules, snake_case for functions, PascalCase for classes
- **Imports:** Absolute imports, grouped with blank lines, sorted alphabetically
- **Docstrings:** Google-style, type hints on all function signatures
- **Module design:** `__all__` for public APIs, `_` prefix for internal helpers
- **Error handling:** Specific exception types, not bare `except:`
- **Entry point:** `def main(): ...` called by `[project.scripts]`
- **GSD workflow:** Changes go through GSD commands

## Open Questions

1. **Name extraction edge cases with possessives**
   - What we know: Questions like "Cease's knuckle curve" contain `'s` after the name
   - What's unclear: Whether `resolve("Cease's")` matches or whether the possessive needs stripping
   - Recommendation: Strip trailing `'s` and `'` from candidate phrases before passing to resolver. Test explicitly with possessive forms.

2. **Multiple pitcher names in one question**
   - What we know: Cross-pitcher comparison is out of scope for v1.4
   - What's unclear: What happens if a question mentions two pitchers ("How does Cease compare to Yamamoto?")
   - Recommendation: The name extraction takes the first match. Since cross-pitcher comparison is declined by the agent's system prompt anyway, this is acceptable behavior. Document in help text that questions should be about a single pitcher.

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/cli.py` -- existing CLI pattern (argparse, error handling, test model)
- `src/pitcher_narratives/scout_cli.py` -- second CLI pattern reference
- `src/pitcher_narratives/resolver.py` -- `resolve()` API: `ResolveResult` with `pitcher_id`, `pitcher_name`, `candidates`, `match_type`
- `src/pitcher_narratives/analyst.py` -- `ask_question_streaming()` API: `(question, context, data, *, provider, thinking, _model_override)`
- `src/pitcher_narratives/report.py` -- `PROVIDERS` dict and `THINKING_LEVELS` list
- `tests/test_cli.py` -- integration test patterns (subprocess, `_test_env`, `PITCHER_NARRATIVES_TEST_MODEL`)
- `pyproject.toml` -- existing `[project.scripts]` entries

### Secondary (MEDIUM confidence)
- None -- all findings are from direct codebase inspection

### Tertiary (LOW confidence)
- None -- no external research needed for this phase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, everything already exists in the codebase
- Architecture: HIGH -- direct mirror of cli.py pattern with well-defined integration points
- Pitfalls: HIGH -- identified from actual code inspection (test model pattern, resolver API, argparse behavior)

**Research date:** 2026-03-30
**Valid until:** Indefinite -- this is codebase-internal research, not dependent on external library versions
