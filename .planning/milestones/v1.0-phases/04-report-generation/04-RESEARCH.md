# Phase 4: Report Generation - Research

**Researched:** 2026-03-26
**Domain:** LLM agent integration (pydantic-ai + Claude) for narrative generation
**Confidence:** HIGH

## Summary

Phase 4 wires the final link in the pipeline: sending the assembled PitcherContext prompt to Claude via pydantic-ai and printing the resulting scout-voice narrative report. The existing codebase already has a complete data-to-prompt pipeline (`data.load_pitcher_data() -> context.assemble_pitcher_context() -> PitcherContext.to_prompt()`), and `main.py` has a temporary verification print that Phase 4 replaces with the actual report.

The pydantic-ai Agent API (v1.72.0, verified installed) provides `run_sync` for simple request/response and `run_stream_sync` for streaming text output. The Agent accepts `output_type=str` for free-form prose (no structured output schema), and `system_prompt` for role instructions. `ModelSettings(max_tokens=4096)` controls response length. The `TestModel` from `pydantic_ai.models.test` enables unit testing without API calls by providing `custom_output_text`.

**Primary recommendation:** Create a `report.py` module with a pydantic-ai Agent configured for `anthropic:claude-sonnet-4-6`, using `run_stream_sync` for streaming output to terminal. Wire into `main.py` replacing the temporary verification print. Use `TestModel` for automated tests.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Claude model: claude-sonnet-4-6 (good quality/cost ratio for narrative generation)
- Context passing: system prompt with role instructions + user message with to_prompt() output
- Output type: str (free-form prose) -- structured output constrains narrative quality
- Max tokens: 4096 (enough for comprehensive report)
- Persona: "You are a veteran MLB pitching analyst writing a scouting report"
- Anti-recitation: explicit instructions -- "Write insight, not stat lines. Reference numbers to support observations, don't list them. If a delta is small, say so and move on."
- SP vs RP differentiation: include role in system prompt + conditional section guidance (starters get stamina/pitch mix depth, relievers get workload/leverage/short-window focus)
- Agent code lives in new `report.py` module -- separates LLM interaction from data/compute layers

### Claude's Discretion
- Exact system prompt wording beyond the persona and anti-recitation core
- How to handle API errors (retry? fallback message?)
- Whether to stream output or wait for complete response
- Report length guidance in the prompt

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RPT-01 | Pydantic models define structured context schema for LLM input with pre-computed deltas and qualitative trend strings | Already complete -- PitcherContext exists with `to_prompt()` producing ~544 tokens of structured markdown. This requirement is satisfied by Phase 3 output. Phase 4 validates it works end-to-end. |
| RPT-02 | Claude generates report via pydantic-ai agent with str output type | pydantic-ai Agent with `output_type=str` (default) + model `anthropic:claude-sonnet-4-6`. Use `run_sync()` or `run_stream_sync()`. Verified both work. |
| RPT-03 | System prompt uses anti-recitation prompt engineering for scout-voice narrative | System prompt set via `system_prompt=` parameter on Agent constructor. Role-conditional guidance (SP vs RP) passed as part of user message or appended to system prompt dynamically. |
| RPT-04 | Report output contains prose paragraphs with data tables where sensible -- exemplary quality | Prompt engineering task. System prompt instructs interleaving tables with narrative. Streaming output with `stream_text(delta=True)` for good UX. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-ai | 1.72.0 (verified installed) | Agent framework wrapping Claude API | Already in pyproject.toml; provides Agent, TestModel, streaming, model settings |
| anthropic | 0.86.0 (transitive, verified installed) | Claude API client | Pulled in by pydantic-ai; provides the actual API transport |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic_ai.models.test.TestModel | (bundled) | Deterministic test model | Unit tests that verify agent wiring without API calls |
| pydantic_ai.settings.ModelSettings | (bundled) | max_tokens, temperature | Configure Claude response parameters |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pydantic-ai Agent | Raw anthropic client | Lose structured output, retries, TestModel -- pydantic-ai is already a dependency |
| run_stream_sync | run_sync | Lose streaming UX -- user sees nothing until full response completes |

**Installation:** No new packages needed -- everything is already in pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
pitcher-narratives/
  main.py          # CLI entry point -- add report generation call
  report.py        # NEW: pydantic-ai Agent, system prompt, generate_report()
  context.py       # PitcherContext + to_prompt() (unchanged)
  engine.py        # All compute functions (unchanged)
  data.py          # Data loading pipeline (unchanged)
  tests/
    test_report.py # NEW: report module tests with TestModel
```

### Pattern 1: Agent-per-Module with Function Wrapper
**What:** Define the Agent at module level, wrap it in a function that accepts PitcherContext and returns the report string.
**When to use:** Always for this project -- keeps the agent configuration declarative and the call interface clean.
**Example:**
```python
# report.py
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from context import PitcherContext

_SYSTEM_PROMPT = """You are a veteran MLB pitching analyst..."""

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=str,
    system_prompt=_SYSTEM_PROMPT,
    model_settings=ModelSettings(max_tokens=4096),
)

def generate_report(ctx: PitcherContext) -> str:
    """Generate a scouting report from assembled pitcher context."""
    result = agent.run_sync(ctx.to_prompt())
    return result.output
```

### Pattern 2: Streaming Output to Terminal
**What:** Use `run_stream_sync` + `stream_text(delta=True)` to print tokens as they arrive.
**When to use:** For the CLI -- gives immediate feedback instead of a multi-second wait.
**Example:**
```python
import sys

def generate_report_streaming(ctx: PitcherContext) -> str:
    """Generate and stream a scouting report to stdout."""
    stream = agent.run_stream_sync(ctx.to_prompt())
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end='', flush=True)
        chunks.append(delta)
    print()  # Final newline
    return ''.join(chunks)
```

**Important:** `run_stream_sync` returns the `StreamedRunResultSync` directly -- it is NOT a context manager. Do not use `with`.

### Pattern 3: Role-Conditional System Prompt
**What:** Build the system prompt dynamically based on PitcherContext.role (SP vs RP).
**When to use:** Required by locked decisions -- starters and relievers get different section guidance.
**Example:**
```python
_BASE_PROMPT = """You are a veteran MLB pitching analyst..."""

_SP_GUIDANCE = """For this starter, emphasize:
- Pitch mix depth and evolution across recent starts
- Stamina indicators (velocity arc, late-inning command)
- Times-through-order preparation"""

_RP_GUIDANCE = """For this reliever, emphasize:
- Workload patterns (consecutive days, rest impact)
- Short-window weapon deployment (what's the put-away pitch?)
- Leverage readiness and reliability signals"""

def _build_prompt(role: str) -> str:
    guidance = _SP_GUIDANCE if role == "SP" else _RP_GUIDANCE
    return f"{_BASE_PROMPT}\n\n{guidance}"
```

Since pydantic-ai's `system_prompt` is set at Agent construction time, use `instructions` parameter (accepts a callable) OR pass role guidance as part of the user message alongside `to_prompt()` output. The simpler approach: include role guidance in the user message.

### Pattern 4: TestModel for Deterministic Tests
**What:** Use pydantic-ai's built-in TestModel to test agent wiring without API calls.
**When to use:** All automated tests.
**Example:**
```python
from pydantic_ai.models.test import TestModel

def test_generate_report():
    """Agent produces string output from pitcher context."""
    from report import agent
    result = agent.run_sync(
        "test prompt",
        model=TestModel(custom_output_text="Test scouting report content"),
    )
    assert isinstance(result.output, str)
    assert "Test scouting report" in result.output
```

The `model=` parameter on `run_sync` overrides the agent's default model, enabling tests without ANTHROPIC_API_KEY.

### Anti-Patterns to Avoid
- **Using `with` on `run_stream_sync`:** The sync streaming result is NOT a context manager. Call it directly and iterate.
- **Hardcoding system prompt in Agent for role-conditional logic:** Either use `instructions` parameter (callable) or pass role guidance in user message. Do not create two separate Agent instances for SP/RP.
- **Catching bare `Exception` for API errors:** Catch `ModelHTTPError` (4xx/5xx), `UsageLimitExceeded`, `UnexpectedModelBehavior` specifically from `pydantic_ai.exceptions`.
- **Printing raw output without newline handling:** LLM responses may or may not end with newline -- ensure consistent terminal formatting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM API calls | HTTP client + message formatting | `pydantic_ai.Agent` | Handles retries, streaming, provider abstraction |
| Response streaming | Manual chunk assembly | `stream_text(delta=True)` | Built-in debouncing and iterator protocol |
| Test mocking | Mock/patch of anthropic client | `TestModel(custom_output_text=...)` | Purpose-built for pydantic-ai agent testing; override via `model=` param |
| Token limit enforcement | Count tokens manually | `ModelSettings(max_tokens=4096)` | Passed through to Claude API natively |
| API error retries | Custom retry loop | Agent `retries=` parameter | Built-in retry with configurable count |

**Key insight:** pydantic-ai already solves every LLM interaction problem this phase needs. The work is prompt engineering and wiring, not infrastructure.

## Common Pitfalls

### Pitfall 1: Missing ANTHROPIC_API_KEY
**What goes wrong:** Agent creation succeeds but `run_sync` raises `UserError` at call time.
**Why it happens:** pydantic-ai defers provider initialization until the first run call.
**How to avoid:** Check for the environment variable early in `main.py` and give a clear error message before entering the pipeline. Or catch `UserError` from pydantic_ai.exceptions.
**Warning signs:** "Set the ANTHROPIC_API_KEY environment variable" error on first run.

### Pitfall 2: run_stream_sync Used as Context Manager
**What goes wrong:** `TypeError: 'StreamedRunResultSync' object does not support the context manager protocol`
**Why it happens:** The async `run_stream` IS a context manager, but the sync `run_stream_sync` is NOT (verified by testing).
**How to avoid:** Call `run_stream_sync()` directly and assign to a variable -- do not use `with`.
**Warning signs:** TypeError on the `with` statement.

### Pitfall 3: Prompt Too Long or Too Short
**What goes wrong:** Report either recites stats (prompt didn't guide enough) or hallucinates trends not in data.
**Why it happens:** System prompt lacks specific anti-recitation guidance or doesn't anchor the model to only reference provided data.
**How to avoid:** Explicit instructions: "Only reference data provided in the context below. If a delta is small, say so briefly and move on. Never fabricate trends."
**Warning signs:** Report contains specific claims not traceable to to_prompt() output.

### Pitfall 4: Blocking the CLI on Long Generation
**What goes wrong:** User runs command and sees nothing for 5-10 seconds.
**Why it happens:** Using `run_sync` instead of `run_stream_sync` -- waits for full response.
**How to avoid:** Use streaming. First tokens appear in ~1 second.
**Warning signs:** Long pause before any output.

### Pitfall 5: Agent Module-Level Initialization Failure
**What goes wrong:** Importing `report.py` fails if the agent tries to validate the model at import time.
**Why it happens:** Agent with `defer_model_check=False` (default) validates the model string on construction.
**How to avoid:** Either use `defer_model_check=True` or accept that the `anthropic` package must be importable (it is -- already installed). The actual API key is only needed at run time, not import time.
**Warning signs:** ImportError on `import report`.

## Code Examples

Verified patterns from live inspection of pydantic-ai 1.72.0:

### Creating an Agent with String Output
```python
# Source: Verified via `Agent.__init__` inspection, pydantic-ai 1.72.0
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=str,  # This is actually the default
    system_prompt='You are a veteran MLB pitching analyst.',
    model_settings=ModelSettings(max_tokens=4096),
)
```

### Running Synchronously
```python
# Source: Verified via Agent.run_sync inspection
result = agent.run_sync('Generate report for this pitcher context...')
report_text: str = result.output  # .output contains the str
```

### Streaming to Terminal
```python
# Source: Verified via StreamedRunResultSync.stream_text inspection
# IMPORTANT: run_stream_sync is NOT a context manager
stream = agent.run_stream_sync('Generate report...')
for delta in stream.stream_text(delta=True):
    print(delta, end='', flush=True)
print()
```

### Overriding Model for Tests
```python
# Source: Verified via TestModel inspection
from pydantic_ai.models.test import TestModel

result = agent.run_sync(
    'test prompt',
    model=TestModel(custom_output_text='Mocked report output'),
)
assert result.output == 'Mocked report output'
```

### Error Handling
```python
# Source: Verified via pydantic_ai.exceptions inspection
from pydantic_ai.exceptions import ModelHTTPError, UserError, UnexpectedModelBehavior

try:
    result = agent.run_sync(prompt)
except UserError as e:
    # Missing API key or invalid configuration
    print(f"Configuration error: {e}", file=sys.stderr)
    sys.exit(1)
except ModelHTTPError as e:
    # 4xx/5xx from Claude API
    print(f"API error: {e}", file=sys.stderr)
    sys.exit(1)
except UnexpectedModelBehavior as e:
    # Malformed response
    print(f"Unexpected model response: {e}", file=sys.stderr)
    sys.exit(1)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `result.data` | `result.output` | pydantic-ai ~0.50+ | Access the agent output via `.output` not `.data` |
| `Agent(model, result_type=str)` | `Agent(model, output_type=str)` | pydantic-ai ~0.50+ | Parameter renamed from `result_type` to `output_type` |
| `with agent.run_stream_sync() as stream:` | `stream = agent.run_stream_sync()` | pydantic-ai 1.x | Sync streaming is NOT a context manager (async IS) |
| `system_prompt` only | `instructions` parameter (dynamic) | pydantic-ai 1.x | `instructions` can be a callable for dynamic prompts |

**Deprecated/outdated:**
- `result.data`: Renamed to `result.output` in newer pydantic-ai versions
- `result_type=`: Renamed to `output_type=` in newer pydantic-ai versions

## Open Questions

1. **Streaming vs. non-streaming default**
   - What we know: Both `run_sync` and `run_stream_sync` work. Streaming gives better UX.
   - What's unclear: Whether streaming adds complexity that outweighs the UX benefit for a CLI tool.
   - Recommendation: Use streaming -- it is straightforward (3 lines of code) and dramatically improves perceived responsiveness. The delta iterator is clean.

2. **Role-conditional prompt delivery mechanism**
   - What we know: System prompt is fixed at Agent construction. `instructions` parameter can be a callable. Alternatively, role guidance can go in the user message.
   - What's unclear: Whether `instructions` callable receives enough context to determine SP/RP, or if embedding in user message is cleaner.
   - Recommendation: Include role-specific guidance in the user message alongside `to_prompt()` output. This is the simplest approach -- the system prompt stays fixed with persona/anti-recitation, and the user message carries both the data and the role-specific analysis guidance.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_report.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RPT-01 | PitcherContext.to_prompt() produces structured LLM input | unit | `uv run pytest tests/test_context.py -x` | Yes (existing) |
| RPT-02 | Agent produces str output from pitcher context | unit | `uv run pytest tests/test_report.py::test_generate_report -x` | No -- Wave 0 |
| RPT-03 | System prompt contains anti-recitation and scout persona | unit | `uv run pytest tests/test_report.py::test_system_prompt_content -x` | No -- Wave 0 |
| RPT-04 | End-to-end CLI produces report output | integration | `uv run pytest tests/test_report.py::test_cli_integration -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_report.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_report.py` -- covers RPT-02, RPT-03, RPT-04 (uses TestModel, no API key needed)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pydantic-ai | Agent framework | Yes | 1.72.0 | -- |
| anthropic | Claude API client | Yes | 0.86.0 (transitive) | -- |
| ANTHROPIC_API_KEY | Runtime API access | Unknown (env var) | -- | Clear error message; TestModel for tests |
| pytest | Test execution | Yes | 9.0.2 (dev dep) | -- |

**Missing dependencies with no fallback:**
- ANTHROPIC_API_KEY at runtime -- needed for actual report generation. Tests use TestModel so they do NOT need it.

**Missing dependencies with fallback:**
- None.

## Sources

### Primary (HIGH confidence)
- pydantic-ai 1.72.0 installed package -- inspected `Agent.__init__`, `Agent.run_sync`, `Agent.run_stream_sync`, `StreamedRunResultSync.stream_text`, `AgentRunResult.output`, `TestModel.__init__`, `ModelSettings` TypedDict, and `pydantic_ai.exceptions` via live Python introspection
- Existing codebase: `context.py`, `engine.py`, `data.py`, `main.py`, `tests/test_context.py` -- read in full
- `pyproject.toml` -- verified dependencies and test configuration

### Secondary (MEDIUM confidence)
- None needed -- all findings verified via live introspection

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified installed, APIs inspected live
- Architecture: HIGH -- patterns verified via actual execution against TestModel
- Pitfalls: HIGH -- each pitfall was discovered/verified via live testing (e.g., context manager TypeError)

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (stable -- pydantic-ai API is mature at 1.72.0)
