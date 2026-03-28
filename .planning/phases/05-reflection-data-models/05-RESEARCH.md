# Phase 5: Reflection Data Models - Research

**Researched:** 2026-03-28
**Domain:** Pydantic models, prompt engineering, pydantic-ai structured output
**Confidence:** HIGH

## Summary

Phase 5 is a pure infrastructure phase: define structured types for anchor check results, add revision metadata to ReportResult, and build a revision prompt builder function. All deliverables are deterministic, LLM-free, and independently testable. The codebase already has strong Pydantic model patterns to follow (ReportResult, HallucinationReport with `is_clean` property, PitcherContext).

The main technical risk is the anchor agent's `output_type` change from `str` to `AnchorResult`. Verification confirms that pydantic-ai `Agent(output_type=AnchorResult)` works correctly with TestModel via `custom_output_args`, enabling tests without LLM calls. The revision prompt builder is a pure string-assembly function following the existing `_build_*_message()` pattern.

**Primary recommendation:** Define AnchorWarning and AnchorResult as Pydantic BaseModel classes in report.py following the HallucinationReport pattern. Change the anchor agent's output_type to AnchorResult. Add `revision_count: int = 0` to ReportResult. Build `_build_revision_message()` following the existing `_build_*_message()` pattern, returning `_UserPrompt` (list of str|CachePoint).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODEL-01 | Anchor check returns structured AnchorResult (Pydantic model with is_clean + typed warnings) instead of raw string | AnchorResult/AnchorWarning models verified working with pydantic-ai output_type; TestModel supports custom_output_args for structured testing |
| MODEL-02 | ReportResult includes revision_count (0 = passed first try, 1-2 = revised N times) | Simple field addition with default=0; follows existing BaseModel pattern |
| LOOP-02 | Revision prompt tells editor to fix specific flagged issues while preserving the rest of the capsule | _build_revision_message() function following existing _build_*_message() pattern; pure function returning _UserPrompt |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Python version**: 3.14+
- **Naming**: snake_case for modules/functions, PascalCase for classes and Pydantic models
- **Code style**: ruff configured (line-length 110, target py313)
- **Module design**: Use `__all__` for public APIs, prefix internal helpers with `_`
- **Error handling**: Use specific exception types, not bare `except:`
- **Docstrings**: Google-style, type hints on all function signatures
- **GSD workflow**: All changes through GSD commands

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | Data validation, BaseModel definitions | Already used for all structured types in project |
| pydantic-ai | 1.72.0 | Agent framework with output_type for structured LLM output | Already used for all agents; supports Pydantic model as output_type |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=9.0.2 | Test framework | Already configured in pyproject.toml; tests/ directory exists |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pydantic BaseModel for AnchorResult | Plain dataclass | BaseModel is the project standard for all structured types; dataclass is used only in engine.py for computation intermediates |
| Literal type for categories | str Enum | Literal is simpler, no class needed, Pydantic generates identical JSON schema enum constraint |
| Changing anchor agent output_type | Parse str output post-hoc | Structured output_type gives model-enforced schema; less fragile than regex parsing. Success criteria explicitly says "agent returns AnchorResult" |

**No new dependencies needed.** Everything is already installed.

## Architecture Patterns

### Recommended Project Structure

No new files needed. All changes go in existing modules:

```
src/pitcher_narratives/
    report.py           # AnchorWarning, AnchorResult, ReportResult changes, _build_revision_message()
tests/
    test_report.py      # New tests for AnchorResult, revision prompt builder
```

### Pattern 1: Pydantic Model with `is_clean` Property

**What:** The project already uses this pattern in HallucinationReport. AnchorResult should follow it exactly.
**When to use:** Any model that represents a pass/fail check result.
**Example:**

```python
# Existing pattern in report.py (HallucinationReport)
class HallucinationReport(BaseModel):
    unknown_metrics: list[str]
    outcome_stat_warnings: list[str]

    @property
    def is_clean(self) -> bool:
        return not self.unknown_metrics and not self.outcome_stat_warnings


# New pattern for AnchorResult (same structure)
class AnchorWarning(BaseModel):
    category: Literal["MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED"]
    description: str

class AnchorResult(BaseModel):
    warnings: list[AnchorWarning]

    @property
    def is_clean(self) -> bool:
        return len(self.warnings) == 0
```

### Pattern 2: Message Builder Functions

**What:** Pure functions that assemble prompt content from typed inputs, returning `_UserPrompt` (list of str|CachePoint).
**When to use:** Every prompt construction in the pipeline.
**Example:**

```python
# Existing pattern
def _build_anchor_message(synthesis: str, capsule: str) -> _UserPrompt:
    return [
        f"## Synthesis (Data Analyst's Briefing)\n{synthesis}",
        CachePoint(),
        f"## Capsule (Editor's Narrative)\n{capsule}\n\n"
        "Check the capsule against the synthesis. Report any issues or respond CLEAN.",
    ]

# New revision builder follows identical pattern
def _build_revision_message(
    synthesis: str,
    capsule: str,
    warnings: list[AnchorWarning],
) -> _UserPrompt:
    # Fixed-size context: synthesis + capsule + warnings + instruction
    ...
```

### Pattern 3: Agent with Structured output_type

**What:** pydantic-ai Agent configured with a Pydantic model as output_type instead of str.
**When to use:** When the LLM must return structured, typed data.
**Verified:** Agent(output_type=AnchorResult) works. TestModel(custom_output_args={...}) produces typed test fixtures.

```python
# Current: all agents use output_type=str
Agent(model, output_type=str, system_prompt=p, ...)

# Phase 5: anchor agent uses output_type=AnchorResult
anchor_agent = Agent(model, output_type=AnchorResult, system_prompt=_ANCHOR_PROMPT, ...)
```

### Anti-Patterns to Avoid

- **Regex parsing of LLM output into structured types:** The current anchor check parses raw strings with `splitlines()`. The structured output_type eliminates this fragility entirely.
- **Mixing agent creation approaches:** Keep the anchor agent creation close to the other agents in _make_agents. Do not create a separate factory function -- just handle the different output_type within the existing pattern.
- **Adding fields without defaults to existing models:** ReportResult is already in use. Adding `revision_count` MUST use a default value (0) to avoid breaking existing call sites.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON schema generation for anchor categories | Manual schema dict | `Literal["MISSED_SIGNAL", ...]` in Pydantic field | Pydantic generates the JSON schema enum automatically |
| String-to-structured parsing of anchor output | Regex/split parser | pydantic-ai `output_type=AnchorResult` | Framework handles structured extraction via tool calling |
| Prompt template engine | Jinja2 or custom template system | f-strings in `_build_revision_message()` | Project convention; all existing builders use f-strings |

**Key insight:** The whole point of this phase is to replace hand-rolled string parsing (the current `splitlines()` approach) with framework-supported structured output.

## Common Pitfalls

### Pitfall 1: Breaking Existing Tests with _make_agents Change

**What goes wrong:** The test suite currently unpacks `_make_agents()` into 4 values (`synth, _, _, _`) but the function returns a 5-tuple. 10 tests already fail because of this mismatch.
**Why it happens:** Tests were written before the anchor checker agent was added.
**How to avoid:** Fix the unpacking in tests as part of this phase. Change 4-tuple unpacking to 5-tuple. This is a pre-existing bug that will get worse when the anchor agent's output_type changes.
**Warning signs:** `ValueError: too many values to unpack (expected 4, got 5)`

### Pitfall 2: Changing Agent Signature Without Updating Callers

**What goes wrong:** If the anchor agent's output_type changes from str to AnchorResult, the code in `generate_report_streaming()` that does `anchor_result.output.strip()` and string splitting will break.
**Why it happens:** The caller expects a string but now gets an AnchorResult object.
**How to avoid:** Phase 5 defines the types and prompt builder but the actual agent creation change and caller update happen together. Either update both in Phase 5 (preferred -- since success criteria says "agent returns AnchorResult") or defer the agent wiring to Phase 6.
**Warning signs:** `AttributeError: 'AnchorResult' object has no attribute 'strip'`

### Pitfall 3: Revision Prompt Losing Voice Consistency

**What goes wrong:** The revision prompt tells the editor to fix issues but doesn't carry the editor's system prompt context, leading to voice drift.
**Why it happens:** The revision prompt builder only assembles user content. The editor agent's system prompt is separate.
**How to avoid:** The revision prompt is a USER message sent to the same editor agent (which already has the editor system prompt). The builder only needs to assemble the user-facing content: synthesis context, current capsule, warnings, and targeted instruction. The agent handles voice consistency via its system prompt.
**Warning signs:** Revised capsule sounds different from original (different tone, style, structure).

### Pitfall 4: TestModel Default Output for Structured Types

**What goes wrong:** TestModel() without custom_output_args produces a default AnchorResult with a non-empty warning (it fills minimal valid data). Tests expecting "clean" results get "dirty" results.
**Why it happens:** TestModel generates minimal valid instances of structured types, and `list[AnchorWarning]` gets one default entry.
**How to avoid:** Always use `TestModel(custom_output_args={"warnings": []})` for clean test cases and `TestModel(custom_output_args={"warnings": [...]})` for dirty cases.
**Warning signs:** Test assertions on `is_clean` fail unexpectedly.

### Pitfall 5: _make_agents Type Signature Mismatch

**What goes wrong:** `_make_agents` currently returns `_AgentTuple = tuple[Agent[None, str], ...]` (all str output). Changing the anchor agent to `Agent[None, AnchorResult]` breaks the type alias.
**Why it happens:** The type alias assumes homogeneous agent output types.
**How to avoid:** Either update the type alias to accommodate the mixed return type, or return the anchor agent separately. The cleanest approach: keep `_AgentTuple` for the 4 str-agents and return the anchor agent as a separate value, or define a new broader type alias.
**Warning signs:** Type checker (ty/pyright) errors on the return type.

## Code Examples

Verified patterns from the existing codebase and pydantic-ai documentation:

### AnchorWarning and AnchorResult Models

```python
# Follows HallucinationReport pattern in report.py
from typing import Literal
from pydantic import BaseModel

WarningCategory = Literal["MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED"]
"""Anchor check warning categories matching _ANCHOR_PROMPT output format."""

class AnchorWarning(BaseModel):
    """A single anchor check warning with typed category."""
    category: WarningCategory
    description: str

class AnchorResult(BaseModel):
    """Structured output from the anchor check agent."""
    warnings: list[AnchorWarning]

    @property
    def is_clean(self) -> bool:
        """True when the capsule is faithfully anchored to the synthesis."""
        return len(self.warnings) == 0
```

### ReportResult with revision_count

```python
class ReportResult(BaseModel):
    """Structured output from the multi-phase report pipeline."""
    narrative: str
    social_hook: str
    fantasy_insights: str
    anchor_warnings: list[AnchorWarning]  # Changed from list[str]
    revision_count: int = 0
    """Number of revision passes (0 = passed first try, 1-2 = revised N times)."""
```

### Revision Prompt Builder

```python
def _build_revision_message(
    synthesis: str,
    capsule: str,
    warnings: list[AnchorWarning],
) -> _UserPrompt:
    """Build a revision prompt for the editor to fix anchor-flagged issues.

    Fixed-size context: synthesis + current capsule + formatted warnings +
    targeted instruction. No message history (fresh prompt per revision).
    """
    formatted_warnings = "\n".join(
        f"- [{w.category}] {w.description}" for w in warnings
    )
    return [
        f"## Data Analyst's Briefing\n{synthesis}",
        CachePoint(),
        f"## Current Capsule\n{capsule}\n\n"
        f"## Anchor Check Warnings\n{formatted_warnings}\n\n"
        "Revise the capsule to address ONLY the warnings listed above. "
        "Preserve the voice, structure, and all unflagged material. "
        "Do not add new analysis or metrics not in the briefing.",
    ]
```

### Testing Structured Agent Output with TestModel

```python
# Verified working: TestModel with custom_output_args for structured types
from pydantic_ai.models.test import TestModel

# Clean anchor result (no warnings)
clean_model = TestModel(custom_output_args={"warnings": []})

# Dirty anchor result (specific warnings)
dirty_model = TestModel(custom_output_args={
    "warnings": [
        {"category": "MISSED_SIGNAL", "description": "Key velocity drop not mentioned"},
        {"category": "UNSUPPORTED", "description": "Capsule claims improvement not in synthesis"},
    ]
})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Parsing raw LLM text into structured data | pydantic-ai output_type with Pydantic models | pydantic-ai v0.x -> v1.x (2025) | Model enforces schema via tool calling; no regex needed |
| `result_type` parameter name | `output_type` parameter name | pydantic-ai v1.x (2025) | Renamed; this project already uses `output_type` |

**Deprecated/outdated:**
- `result_type` parameter: Renamed to `output_type` in pydantic-ai v1.x. This project already uses the current name.

## Key Design Decisions

### Should the anchor agent use output_type=AnchorResult directly?

**Decision: Yes.** The success criteria explicitly states "Anchor check agent returns an AnchorResult Pydantic model." pydantic-ai's structured output via tool calling is more reliable than regex parsing. Verified working with TestModel.

### Should _make_agents return type change?

**Recommendation:** The cleanest approach is to split the anchor agent creation out of the shared loop since it has a different output_type. Two options:

1. **Keep _make_agents for the 4 str-agents, create anchor separately.** Breaks existing 5-tuple unpacking in `generate_report_streaming()` but is type-safe.
2. **Return a broader tuple type.** Keep all 5 together but the type alias becomes more complex.

Option 1 is recommended because it makes the type difference explicit and is easier to test.

### Where should AnchorResult live?

**In report.py**, alongside HallucinationReport and ReportResult. All check-result models live in report.py. No new module needed.

### Should anchor_warnings in ReportResult change type?

**Yes: `list[str]` -> `list[AnchorWarning]`.** This is a breaking change to the ReportResult model. The CLI code that prints warnings (`for warning in result.anchor_warnings: print(f"  {warning}")`) will need to format AnchorWarning objects instead of raw strings. This change should be included in Phase 5 since it flows directly from MODEL-01.

### Should the anchor prompt (_ANCHOR_PROMPT) change?

**Possibly minimal changes.** The current anchor prompt tells the LLM to output "CLEAN" or bracket-prefixed lines. With `output_type=AnchorResult`, the LLM returns structured JSON via tool calling. The system prompt should still describe the checking criteria but no longer needs to prescribe the text output format. The LLM will be guided by the JSON schema instead.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_report.py -x -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODEL-01 | AnchorResult model with is_clean and typed warnings | unit | `uv run pytest tests/test_report.py -x -q -k anchor_result` | Needs new tests |
| MODEL-01 | AnchorWarning with Literal category validation | unit | `uv run pytest tests/test_report.py -x -q -k anchor_warning` | Needs new tests |
| MODEL-02 | ReportResult.revision_count field, default 0 | unit | `uv run pytest tests/test_report.py -x -q -k revision_count` | Needs new tests |
| LOOP-02 | _build_revision_message returns correct prompt structure | unit | `uv run pytest tests/test_report.py -x -q -k revision_message` | Needs new tests |
| LOOP-02 | Revision message contains synthesis, capsule, warnings, instruction | unit | `uv run pytest tests/test_report.py -x -q -k revision_message` | Needs new tests |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_report.py -x -q`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Tests for AnchorWarning model (category validation, construction)
- [ ] Tests for AnchorResult model (is_clean property, empty vs non-empty warnings)
- [ ] Tests for ReportResult.revision_count field (default value, explicit value)
- [ ] Tests for _build_revision_message() (output structure, content inclusion)
- [ ] Fix existing test unpacking bug (4-tuple -> 5-tuple in _make_agents calls)
- [ ] Tests for anchor agent with output_type=AnchorResult using TestModel

## Open Questions

1. **Anchor prompt format change for structured output**
   - What we know: The current _ANCHOR_PROMPT tells the LLM to output "CLEAN" or bracket-prefixed lines. With output_type=AnchorResult, the model fills a JSON schema instead.
   - What's unclear: Whether the existing prompt text should be simplified (remove OUTPUT FORMAT section) or kept as-is for reasoning guidance.
   - Recommendation: Keep the checking criteria. Remove or simplify the OUTPUT FORMAT section since the JSON schema replaces it. Test both approaches empirically in Phase 6.

2. **anchor_warnings type change in ReportResult**
   - What we know: Changing `list[str]` to `list[AnchorWarning]` is cleaner and flows from MODEL-01.
   - What's unclear: Whether cli.py's warning printer should be updated in Phase 5 or deferred to Phase 7.
   - Recommendation: Update in Phase 5 -- it's a direct consequence of the type change and prevents runtime errors. Format as `f"[{w.category}] {w.description}"` for backwards-compatible stderr output.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: report.py (lines 448-660, 668-681) -- existing ReportResult, HallucinationReport, _build_*_message() patterns
- Codebase inspection: report.py (lines 414-445) -- _ANCHOR_PROMPT with 4 warning categories
- Codebase inspection: test_report.py -- existing test patterns, TestModel usage
- pydantic-ai docs (https://ai.pydantic.dev/output/) -- output_type with Pydantic models
- Local verification: AnchorResult model with Literal categories validated in Python 3.14 + Pydantic 2.12.5
- Local verification: `Agent(output_type=AnchorResult)` works with `TestModel(custom_output_args=...)` for both clean and dirty test cases

### Secondary (MEDIUM confidence)
- pydantic-ai API docs (https://ai.pydantic.dev/api/agent/) -- Agent class generics and type safety

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all patterns verified against installed versions
- Architecture: HIGH -- follows existing codebase patterns exactly; all proposed code verified locally
- Pitfalls: HIGH -- test failures confirmed by running test suite; TestModel behavior verified empirically

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable domain; Pydantic/pydantic-ai versions pinned)
