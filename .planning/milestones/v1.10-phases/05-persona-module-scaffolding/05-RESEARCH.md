# Phase 05: Persona Module Scaffolding - Research

**Researched:** 2026-04-12
**Domain:** Python module design, prompt engineering decomposition, frozen dataclass patterns, test fixture strategy
**Confidence:** HIGH

## Summary

Phase 05 creates a new `src/pitcher_narratives/personas.py` module that extracts the v1.9 `_WRITER_PROMPT` from `pipeline.py` into a shared analytical base (`SHARED_WRITER_BASE`) plus a scout-specific voice overlay, composed via `build_writer_system_prompt(persona)`. The module introduces a `Persona` frozen dataclass, a `PERSONAS` registry, `get_persona()` lookup, and `DEFAULT_PERSONA = PERSONAS["scout"]`. Four tests enforce the decomposition: byte-identity of the composed scout prompt against a frozen fixture, no-voice-words in the base, and the presence of an "EXPLAIN THE MODEL" section in the base.

The core technical challenge is the prompt decomposition: the v1.9 `_WRITER_PROMPT` (3,607 bytes, 7 logical sections) mixes analytical contract, voice instructions, and structural constraints. Splitting it requires careful attention to byte boundaries so that `SHARED_WRITER_BASE + "\n\n" + scout_overlay` reconstructs the target exactly. A critical requirement tension exists between VOICE-01 (composed scout = v1.9 verbatim) and PERSONA-06 (base contains a NEW "EXPLAIN THE MODEL" instruction) -- see Open Questions below.

**Primary recommendation:** Start with the decomposition of `_WRITER_PROMPT` into base + scout overlay, write the byte-identity test first (TEST-02), then iterate the split until the test passes. The "EXPLAIN THE MODEL" section goes into `SHARED_WRITER_BASE` and the scout overlay gets a terse-depth modulation line. The fixture captures the composed result (base + overlay), which will differ from the raw v1.9 `_WRITER_PROMPT` by the addition of the new EXPLAIN THE MODEL section.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- CONTEXT.md notes this is an infrastructure phase with all implementation choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PERSONA-01 | `Persona` frozen dataclass with id, display_name, description, overlay, length_target, parent | Codebase uses `@dataclass` from stdlib extensively (data.py, scout.py, resolver.py, engine.py); frozen=True pattern matches immutable config convention |
| PERSONA-02 | `PERSONAS: dict[str, Persona]` registry + `get_persona()` raising ValueError | Module-level dict + lookup function pattern consistent with existing `PROVIDERS`/`MINI_PROVIDERS` dicts in config.py |
| PERSONA-03 | `DEFAULT_PERSONA = PERSONAS["scout"]` module-level constant | Mirrors existing `DEFAULT_*` constant patterns in config.py |
| PERSONA-04 | `SHARED_WRITER_BASE` extracted from v1.9 `_WRITER_PROMPT` with voice words lifted out | Decomposition analysis of `_WRITER_PROMPT` (7 sections) identifies analytical contract (INPUT, CRITICAL, CONSTRAINTS partial) vs. voice (opening line, VOICE section, STRUCTURE) |
| PERSONA-05 | `build_writer_system_prompt(persona)` composer with `\n\n` separator and parent overlay support | Research confirms plain string concatenation is the unanimous recommendation; parent overlay composed first, child appended |
| PERSONA-06 | `SHARED_WRITER_BASE` contains "EXPLAIN THE MODEL" instruction about Pitching+ grades | New content added to base; research FEATURES.md Cat 6 defines exact wording and purpose |
| VOICE-01 | SCOUT persona whose composed prompt is byte-identical to v1.9 `_WRITER_PROMPT` | See Open Questions -- tension with PERSONA-06. Scout overlay captures voice, structure, banned-word list |
| TEST-01 | Frozen fixture at `tests/fixtures/writer_prompt_scout.txt` | No fixtures directory exists yet; must be created |
| TEST-02 | `test_scout_composed_prompt_is_byte_identical_to_v19` byte-identity test | pytest infrastructure exists, configured in pyproject.toml |
| TEST-03 | `test_base_prompt_has_no_voice_words` assertion | Research PITFALLS.md defines exact word list: "stuff", "feel", "groove", "tagged", "elite", "massive" |
| TEST-04 | `test_base_prompt_has_explainer_section` assertion | Checks for "EXPLAIN THE MODEL" substring in SHARED_WRITER_BASE |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python dataclasses | stdlib | Frozen `Persona` dataclass | Project convention -- all data containers use `@dataclass` from stdlib, not Pydantic BaseModel (locked decision in research SUMMARY.md) |
| pytest | >=9.0.2 | Test framework for persona contract tests | Already in dev dependencies, configured in pyproject.toml |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | -- | -- | Phase 05 requires zero new dependencies |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@dataclass(frozen=True)` | Pydantic BaseModel | Explicitly rejected by research -- no validation needed, no serialization, personas are hand-authored constants |
| String concatenation | Jinja2/Mustache templating | Explicitly rejected by research -- "overlays are data, not code"; plain concatenation is predictable and testable |
| `Agent.override()` / per-run `instructions=` | Static `system_prompt=` | Research confirms one Agent per persona, built at construction time; override APIs add complexity for zero benefit |

**Installation:**
```bash
# No new packages needed -- all dependencies already installed
```

## Architecture Patterns

### Recommended Project Structure
```
src/pitcher_narratives/
    personas.py          # NEW -- Persona dataclass, registry, composer, base+overlay constants
    pipeline.py          # UNTOUCHED in Phase 05 (Phase 06 removes _WRITER_PROMPT)
    ...

tests/
    test_personas.py     # NEW -- byte-identity, no-voice-words, explainer-section tests
    fixtures/
        writer_prompt_scout.txt  # NEW -- frozen fixture for byte-identity gate
```

### Pattern 1: Frozen Dataclass for Persona
**What:** A `@dataclass(frozen=True)` with typed fields for persona configuration
**When to use:** Immutable configuration constants that are hand-authored in code
**Example:**
```python
# Source: Codebase convention (data.py, scout.py, resolver.py all use @dataclass)
from dataclasses import dataclass

@dataclass(frozen=True)
class Persona:
    """Immutable persona configuration for the writer agent."""
    id: str
    display_name: str
    description: str
    overlay: str
    length_target: tuple[int, int]  # (min_words, max_words)
    parent: str | None = None  # persona id for overlay inheritance
```

### Pattern 2: Module-Level Registry + Lookup
**What:** A `dict[str, Persona]` populated at module scope with a typed accessor function
**When to use:** Small, fixed set of named constants that need lookup-by-id with error handling
**Example:**
```python
# Source: Mirrors PROVIDERS/MINI_PROVIDERS pattern in config.py
PERSONAS: dict[str, Persona] = {
    "scout": SCOUT,
    # analyst and generic added in Phases 07/08
}

DEFAULT_PERSONA: Persona = PERSONAS["scout"]

def get_persona(persona_id: str) -> Persona:
    """Look up a persona by id. Raises ValueError for unknown ids."""
    try:
        return PERSONAS[persona_id]
    except KeyError:
        valid = ", ".join(sorted(PERSONAS.keys()))
        raise ValueError(f"Unknown persona {persona_id!r}; valid: {valid}") from None
```

### Pattern 3: String Concatenation Composer
**What:** Base prompt + `\n\n` + overlay(s), with parent-chaining
**When to use:** Composing the full writer system prompt from shared base + persona overlay
**Example:**
```python
# Source: Research SUMMARY.md locked decision -- plain concatenation, overlay last
def build_writer_system_prompt(persona: Persona) -> str:
    """Compose the full writer system prompt from base + persona overlay(s)."""
    parts = [SHARED_WRITER_BASE]
    if persona.parent is not None:
        parent = PERSONAS[persona.parent]
        parts.append(parent.overlay)
    parts.append(persona.overlay)
    return "\n\n".join(parts)
```

### Pattern 4: `__all__` Export List
**What:** Explicit public API declaration
**When to use:** All modules that serve as public APIs (per CLAUDE.md conventions)
**Example:**
```python
__all__ = [
    "Persona",
    "PERSONAS",
    "DEFAULT_PERSONA",
    "SHARED_WRITER_BASE",
    "build_writer_system_prompt",
    "get_persona",
]
```

### Anti-Patterns to Avoid
- **Putting persona logic in pipeline.py:** pipeline.py is 66KB already; personas.py is a separate concern module (mirrors anchor.py, signals.py pattern)
- **Using Pydantic BaseModel for Persona:** Research explicitly rejects this -- no validation needed, frozen dataclass is lighter
- **Template engines for prompt composition:** "Overlays are data, not code" -- Jinja/Mustache rejected
- **Importing `_WRITER_PROMPT` in personas.py:** The base and overlay are NEW constants defined in personas.py; `_WRITER_PROMPT` stays in pipeline.py untouched until Phase 06 deletes it
- **Touching pipeline.py in Phase 05:** This phase creates personas.py and tests; pipeline.py changes happen in Phase 06

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Frozen dataclass | Custom `__setattr__` override | `@dataclass(frozen=True)` | stdlib, hashable, battle-tested |
| Registry lookup | Custom registry class | Plain `dict[str, Persona]` + function | Three personas, no need for metaclass magic |
| Prompt composition | Template engine, regex substitution | String concatenation with `"\n\n".join()` | Predictable, testable, zero dependencies |
| Test fixture loading | Custom fixture loader | `pathlib.Path.read_text()` in test | Standard pattern, no framework needed |

**Key insight:** This phase is pure Python stdlib work -- a frozen dataclass, a dict, a function, and string concatenation. The complexity is in getting the prompt decomposition right, not in the machinery.

## Common Pitfalls

### Pitfall 1: Voice Bleed Between Base and Overlay
**What goes wrong:** Scout-flavored phrasing ("finding a groove", "getting tagged", "elite") leaks into `SHARED_WRITER_BASE`, causing all future personas (analyst, generic) to sound scout-flavored.
**Why it happens:** The v1.9 `_WRITER_PROMPT` mixes analytical contract with voice in the same sections. The CRITICAL section uses "elite" in an example ("If stuff and run value both say the slider is elite, say it once"), and the CONSTRAINTS section mixes analytical rules (directional consistency) with structural rules (no bullet points, prose only).
**How to avoid:** The banned voice word list from research PITFALLS.md is: "stuff", "feel", "groove", "tagged", "elite", "massive". Test TEST-03 asserts none of these appear in `SHARED_WRITER_BASE.lower()`. During decomposition, any sentence containing these words goes into the scout overlay.
**Warning signs:** TEST-03 failing; the word "stuff" appearing in the base (it's in the VOICE section and also in the INPUT section as "Stuff analysis" -- the INPUT section reference to "Stuff analysis" is a proper noun describing the specialist, not a voice word; the test should check `.lower()` on the base but the base should use the specialist name without the scout-voice word).

### Pitfall 2: Whitespace Drift Breaking Byte-Identity
**What goes wrong:** The composed prompt `SHARED_WRITER_BASE + "\n\n" + scout_overlay` has different whitespace than the target, breaking TEST-02.
**Why it happens:** The split point between base and overlay is a `\n\n` boundary in the original prompt. If the split doesn't align exactly with an existing paragraph break, extra or missing newlines appear.
**How to avoid:** Identify the exact byte offset where the split occurs. The `_WRITER_PROMPT` uses `\n\n` between its 7 sections. The split boundary should be at one of these existing `\n\n` boundaries. Write the byte-identity test FIRST, then iterate the split.
**Warning signs:** TEST-02 failing with diff showing only whitespace differences.

### Pitfall 3: "EXPLAIN THE MODEL" Conflicting with Byte-Identity
**What goes wrong:** PERSONA-06 requires new "EXPLAIN THE MODEL" content in `SHARED_WRITER_BASE`, but VOICE-01 requires the composed scout prompt to be byte-identical to the v1.9 `_WRITER_PROMPT` which does NOT contain this content.
**Why it happens:** Genuine tension between two requirements. See Open Questions section.
**How to avoid:** Choose one of the resolutions documented in Open Questions and make the choice explicit in the frozen fixture.
**Warning signs:** TEST-02 and TEST-04 cannot both pass simultaneously under the naive interpretation.

### Pitfall 4: Forgetting `__all__` or Missing Exports
**What goes wrong:** Phase 06 tries `from pitcher_narratives.personas import Persona, PERSONAS, ...` and fails because names aren't exported.
**Why it happens:** Success Criterion 1 lists exact imports that must work.
**How to avoid:** Define `__all__` listing all 6 public names. Verify with an import test.
**Warning signs:** ImportError in Phase 06.

### Pitfall 5: Scout Overlay Containing Analytical Contract Rules
**What goes wrong:** Rules like "directional consistency" or "temporal grounding" end up in the scout overlay instead of the base, meaning future personas (analyst, generic) lose these critical guardrails.
**Why it happens:** The v1.9 CONSTRAINTS section mixes analytical contract ("DIRECTIONAL CONSISTENCY", "TEMPORAL GROUNDING") with scout-specific structure ("No bullet points, no headers, no tables. Prose only.").
**How to avoid:** The CONSTRAINTS section must be split line-by-line: directional consistency, "use ONLY data", acknowledge tensions, scale confidence to sample size, and temporal grounding go to base. "No bullet points, no headers, no tables. Prose only." goes to scout overlay.
**Warning signs:** Future persona tests in Phases 07/08 discover missing guardrails in their composed prompts.

### Pitfall 6: `get_persona` Not Raising ValueError on Unknown IDs
**What goes wrong:** Success Criterion 4 explicitly requires `get_persona("bogus")` to raise `ValueError`.
**Why it happens:** Using `dict.get()` with a default instead of catching `KeyError`.
**How to avoid:** Use `try/except KeyError` and raise `ValueError` with a message naming valid choices.
**Warning signs:** SC4 test failing.

## Code Examples

### Prompt Decomposition Map

The v1.9 `_WRITER_PROMPT` (3,607 bytes) has 7 logical sections separated by blank lines. Here is the decomposition assignment:

```
Section 1: Opening identity ("You are an elite, sabermetrically inclined baseball writer...")
  -> SCOUT OVERLAY (voice-specific identity statement)

Section 2: INPUT list ("INPUT: Five specialist analyses...")
  -> SHARED_WRITER_BASE (analytical contract -- what the writer receives)

Section 3: Job description ("Your job is to compose a single, unified 2-3 paragraph scouting capsule...")
  -> SCOUT OVERLAY ("2-3 paragraph scouting capsule" is scout-specific format)

Section 4: CRITICAL ingredients rules ("Find the thread", "Write as one voice", "Drop redundant", "Prioritize surprising", "Use Key Signals")
  -> SHARED_WRITER_BASE (analytical contract -- how to synthesize)
  NOTE: Contains "elite" in example text ("If stuff and run value both say the slider is elite").
        This line needs careful handling -- the example may need rewording in base, or the
        test word list needs to account for it. Research PITFALLS says "elite" is a banned voice word.

Section 5: STRUCTURE ("Paragraph 1: The Setup...", "Paragraph 2+: The Verdict...")
  -> SCOUT OVERLAY (scout-specific paragraph structure)

Section 6: VOICE (entire section -- scouting language, banned words, three-metric rule)
  -> SCOUT OVERLAY (entirely voice-specific)

Section 7: CONSTRAINTS
  -> SPLIT:
     Base: "Use ONLY data...", "DIRECTIONAL CONSISTENCY...", "If specialists contradict...",
           "Scale confidence to sample size...", "TEMPORAL GROUNDING..."
     Scout overlay: "No bullet points, no headers, no tables. Prose only."
```

### Frozen Fixture Creation
```python
# In test setup or fixture creation script:
from pitcher_narratives.pipeline import _WRITER_PROMPT

fixture_path = Path("tests/fixtures/writer_prompt_scout.txt")
fixture_path.parent.mkdir(parents=True, exist_ok=True)
fixture_path.write_text(_WRITER_PROMPT)
```

### Byte-Identity Test Pattern
```python
# tests/test_personas.py
from pathlib import Path
from pitcher_narratives.personas import (
    PERSONAS, SHARED_WRITER_BASE, build_writer_system_prompt
)

_FIXTURE = Path(__file__).parent / "fixtures" / "writer_prompt_scout.txt"

def test_scout_composed_prompt_is_byte_identical_to_v19():
    expected = _FIXTURE.read_text()
    actual = build_writer_system_prompt(PERSONAS["scout"])
    assert actual == expected, (
        f"Scout composed prompt differs from fixture. "
        f"Lengths: {len(actual)} vs {len(expected)}"
    )
```

### No-Voice-Words Test Pattern
```python
# Source: Research PITFALLS.md Pitfall 1 verification
_SCOUT_VOICE_WORDS = ("stuff", "feel", "groove", "tagged", "elite", "massive")

def test_base_prompt_has_no_voice_words():
    base_lower = SHARED_WRITER_BASE.lower()
    for word in _SCOUT_VOICE_WORDS:
        assert word not in base_lower, (
            f"Voice word {word!r} found in SHARED_WRITER_BASE -- "
            f"should be in scout overlay only"
        )
```

### Explainer Section Test Pattern
```python
def test_base_prompt_has_explainer_section():
    assert "EXPLAIN THE MODEL" in SHARED_WRITER_BASE
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `_WRITER_PROMPT` in pipeline.py | Split into `SHARED_WRITER_BASE` + persona overlays in personas.py | Phase 05 (this phase) | Enables multi-persona writer without duplicating prompt content |
| Hardcoded writer agent in `make_pipeline_agents` | Persona-parameterized writer (Phase 06) | Phase 06 | Writer agent construction becomes persona-aware |

**Deprecated/outdated:**
- `_WRITER_PROMPT` in pipeline.py: Phase 06 will delete it; until then it remains as the source of truth for the v1.9 prompt text

## Open Questions

### 1. CRITICAL: PERSONA-06 vs VOICE-01 Byte-Identity Tension

**What we know:**
- VOICE-01 requires: `build_writer_system_prompt(SCOUT)` produces a string byte-identical to the v1.9 `_WRITER_PROMPT`
- PERSONA-06 requires: `SHARED_WRITER_BASE` contains a named "EXPLAIN THE MODEL" instruction that requires contextualizing Pitching+ grades (S+ = stuff, L+ = location, P+ = combined)
- The v1.9 `_WRITER_PROMPT` does NOT contain an "EXPLAIN THE MODEL" section or any text about "S+ = stuff, L+ = location, P+ = combined"
- TEST-01 says the fixture contains "the v1.9 `_WRITER_PROMPT` verbatim"
- TEST-02 asserts byte-identity between composed scout prompt and the fixture

**What's unclear:** These requirements cannot all be satisfied simultaneously under a strict reading. If the base contains NEW "EXPLAIN THE MODEL" content, the composed scout prompt will differ from the v1.9 `_WRITER_PROMPT`.

**Three possible resolutions:**
1. **Fixture = composed scout (including EXPLAIN THE MODEL).** TEST-01's "v1.9 verbatim" is imprecise; the fixture captures the new composed scout prompt (v1.9 content + EXPLAIN THE MODEL section). The scout overlay includes a depth modulation line ("Explain the model tersely..."). Byte-identity is against the fixture, not against the raw v1.9 text. This means scout output will change slightly from v1.9 (the writer now sees the EXPLAIN THE MODEL instruction it didn't have before).
2. **EXPLAIN THE MODEL goes in scout overlay, not base.** This satisfies VOICE-01 (composed = v1.9 verbatim) but violates PERSONA-06 (base must contain it). The base would not contain the section, only the overlays would.
3. **Split EXPLAIN THE MODEL into base (presence) + scout overlay (terse depth + reframe of existing text).** The base gets a minimal "EXPLAIN THE MODEL" reference to content already implicitly present in the v1.9 prompt (the specialist analyses describe S+/L+/P+ grades), and the scout overlay adds the depth modulation. The composed result matches a fixture that includes this new framing.

**Recommendation:** Resolution 1 is the most consistent with the research documents (FEATURES.md Cat 6, SUMMARY.md). The fixture should capture the ACTUAL composed scout prompt (base + scout overlay), which includes the new "EXPLAIN THE MODEL" section. TEST-01's description should be interpreted as "the fixture is the canonical scout prompt for this milestone" rather than "byte-for-byte identical to the old `_WRITER_PROMPT`." The research SUMMARY.md already says "byte-identical-ish" and defines the hard test as prompt-level identity with the fixture. The planner should make this resolution explicit and update the fixture description if needed.

### 2. Exact Voice Word List for TEST-03

**What we know:** Research PITFALLS.md lists: "stuff", "feel", "groove", "tagged", "elite", "massive". But the CRITICAL section (Section 4 of `_WRITER_PROMPT`) uses "elite" in an example: "If stuff and run value both say the slider is elite, say it once."

**What's unclear:** Does "elite" in the analytical contract (the CRITICAL synthesis rules) count as a voice word? The word "stuff" also appears in the INPUT section ("Stuff analysis") and the CRITICAL section ("If stuff and run value...").

**Recommendation:** The INPUT section references "Stuff analysis" as a proper noun (the specialist name). The CRITICAL section uses "stuff" and "elite" in analytical examples about synthesis rules. These are part of the analytical contract, not voice. The base should rephrase these examples to avoid the banned words (e.g., "If two specialists agree the slider is strong, say it once"). The test should use whole-word or contextual matching, but given the research says `word not in base.lower()`, the base must genuinely not contain these words in any form. This means Section 4's example text needs minor rewording in the base, with the original wording preserved in the scout overlay. This is another source of byte-identity tension.

### 3. Registry Completeness at Phase 05

**What we know:** At Phase 05, only `SCOUT` is populated. Analyst and generic are added in Phases 07/08.

**What's unclear:** Should `PERSONAS` contain only `{"scout": SCOUT}` at Phase 05, or should it contain placeholder entries for analyst/generic?

**Recommendation:** Only `{"scout": SCOUT}` at Phase 05. Research SUMMARY.md phase A says "Registry completeness test (at this stage, only SCOUT is populated)." Phases 07/08 will add entries.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_personas.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERSONA-01 | Persona frozen dataclass importable with correct fields | unit | `uv run pytest tests/test_personas.py::test_persona_is_frozen_dataclass -x` | Wave 0 |
| PERSONA-02 | PERSONAS registry + get_persona raises ValueError | unit | `uv run pytest tests/test_personas.py::test_get_persona_unknown_raises_valueerror -x` | Wave 0 |
| PERSONA-03 | DEFAULT_PERSONA equals PERSONAS["scout"] | unit | `uv run pytest tests/test_personas.py::test_default_persona_is_scout -x` | Wave 0 |
| PERSONA-04 | SHARED_WRITER_BASE has analytical contract, no voice words | unit | `uv run pytest tests/test_personas.py::test_base_prompt_has_no_voice_words -x` | Wave 0 |
| PERSONA-05 | build_writer_system_prompt composes correctly | unit | `uv run pytest tests/test_personas.py::test_scout_composed_prompt_is_byte_identical_to_v19 -x` | Wave 0 |
| PERSONA-06 | SHARED_WRITER_BASE contains EXPLAIN THE MODEL | unit | `uv run pytest tests/test_personas.py::test_base_prompt_has_explainer_section -x` | Wave 0 |
| VOICE-01 | Composed scout = fixture | unit | `uv run pytest tests/test_personas.py::test_scout_composed_prompt_is_byte_identical_to_v19 -x` | Wave 0 |
| TEST-01 | Fixture file exists and is readable | unit | `uv run pytest tests/test_personas.py::test_fixture_exists -x` | Wave 0 |
| TEST-02 | Byte-identity test | unit | `uv run pytest tests/test_personas.py::test_scout_composed_prompt_is_byte_identical_to_v19 -x` | Wave 0 |
| TEST-03 | No voice words in base | unit | `uv run pytest tests/test_personas.py::test_base_prompt_has_no_voice_words -x` | Wave 0 |
| TEST-04 | Explainer section in base | unit | `uv run pytest tests/test_personas.py::test_base_prompt_has_explainer_section -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_personas.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_personas.py` -- all persona contract tests (covers TEST-01 through TEST-04, PERSONA-01 through PERSONA-06, VOICE-01)
- [ ] `tests/fixtures/writer_prompt_scout.txt` -- frozen fixture file
- [ ] `tests/fixtures/` directory -- does not exist yet, must be created

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Python version:** 3.14+ (verified: system is 3.14.2)
- **Package layout:** `src/pitcher_narratives/` with per-concern modules
- **Naming:** snake_case for modules and functions, PascalCase for classes, UPPER_SNAKE_CASE for constants
- **Imports:** Absolute imports, grouped with blank lines between sections
- **Module design:** `__all__` in public API modules, `_` prefix for internal helpers
- **Docstrings:** Google-style, type hints on all function signatures
- **Error handling:** Specific exception types, not bare `except:`
- **No GSD bypass:** Must work through GSD workflow for edits
- **Dataclass, not Pydantic BaseModel:** Research locked decision -- frozen dataclass for Persona
- **String concatenation, not templates:** Research locked decision -- `\n\n`.join for prompt composition
- **Pipeline.py untouched in Phase 05:** Phase 06 handles the integration

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/pipeline.py:408-477` -- v1.9 `_WRITER_PROMPT` (3,607 bytes, 7 sections)
- `src/pitcher_narratives/pipeline.py:1112-1162` -- `make_pipeline_agents` current signature
- `src/pitcher_narratives/data.py`, `scout.py`, `resolver.py`, `engine.py` -- existing `@dataclass` patterns
- `.planning/REQUIREMENTS.md` -- PERSONA-01 through PERSONA-06, VOICE-01, TEST-01 through TEST-04
- `.planning/ROADMAP.md` -- Phase 05 goal and success criteria
- `.planning/research/SUMMARY.md` -- locked decisions, byte-parity strategy, phase ordering
- `.planning/research/FEATURES.md` -- Cat 3a (scout voice), Cat 5 (testing), Cat 6 (EXPLAIN THE MODEL)
- `.planning/research/PITFALLS.md` -- Pitfall 1 (voice bleed), Pitfall 9 (scout regression)

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` -- module layout, `make_pipeline_agents` signature evolution
- `.planning/research/STACK.md` -- library landscape confirming no new dependencies needed

### Tertiary (LOW confidence)
- None -- all findings are codebase-grounded

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, pure stdlib Python
- Architecture: HIGH -- patterns are well-established in the codebase, research provides unanimous guidance
- Pitfalls: HIGH -- research documents provide detailed, codebase-grounded pitfall analysis
- Open Questions: MEDIUM -- the PERSONA-06 vs VOICE-01 tension is real and needs explicit resolution by the planner

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable -- no external dependencies that could change)
