# Phase 07: Analyst Persona - Research

**Researched:** 2026-04-12
**Domain:** Persona overlay definition, hallucination guard extension, test scaffolding
**Confidence:** HIGH

## Summary

Phase 07 adds the ANALYST persona constant to `personas.py`, extends `check_hallucinated_metrics` with a per-persona allowlist parameter, and creates both shape-assertion helpers and smoke tests for the analyst voice. The work is entirely additive -- no existing code changes behavior, only new constants, a new function parameter with backward-compatible default, and new tests.

The core implementation pattern is fully established by Phases 05-06: frozen `Persona` dataclass with `parent` field for overlay inheritance, `build_writer_system_prompt()` compositor that chains `SHARED_WRITER_BASE + parent overlay + child overlay`, and the `PERSONAS` registry with `get_persona()` lookup. Phase 07 follows the same pattern for a second persona entry.

**Primary recommendation:** Define the ANALYST constant with `parent="scout"` so it inherits the scout overlay's factual-discipline rules (banned words, three-metric cap, plausibility filters), then layer the analyst-specific newsletter voice on top. Add the `persona` parameter to `check_hallucinated_metrics` with a `_PERSONA_KNOWN_METRICS` dict for per-persona vocabulary allowlisting.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices are at Claude's discretion per CONTEXT.md.

### Claude's Discretion
All implementation choices are at Claude's discretion -- voice characteristics fully specified in REQUIREMENTS.md (VOICE-02, PERSONA-10 analyst portion). Use ROADMAP success criteria and existing personas.py patterns to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VOICE-02 | ANALYST persona constant with newsletter voice targeting 450-800 words, inherits from SCOUT via parent field, teaching vocabulary permissions, full-sentence "explain the model" depth, hard word-count ceiling | Analyst voice spec in FEATURES.md section 3b; overlay composition pattern in personas.py; parent inheritance already implemented in `build_writer_system_prompt()` |
| PERSONA-10 (analyst portion) | `check_hallucinated_metrics(narrative, persona=None)` gains optional persona parameter; `_PERSONA_KNOWN_METRICS` dict adds per-persona safe phrases for analyst vocabulary | Current function signature takes `report_text` only; regex does not currently catch plain English terms but mechanism must exist for forward compatibility and to satisfy test vectors |
| TEST-05 (analyst portion) | TestModel-based analyst smoke test runs pipeline end-to-end, asserts composed prompt starts with SHARED_WRITER_BASE, narrative is non-empty, anchor check runs, hallucination guard does not fire | Existing scout smoke test pattern in `test_personas.py::test_scout_pipeline_smoke` provides exact template |
| TEST-06 (analyst portion) | `assert_analyst_shape(text)` validates word-count bounds and allowed structural elements | No shape helpers exist yet; analyst shape spec: 450-800 words (length_target on Persona), prose only, no tables, no bullet lists, optional bolded leading phrases, no `##` headings |
| TEST-07 (analyst portion) | Per-persona regression vectors in `test_hallucination_guard.py` -- analyst vocabulary does not false-positive when `persona="analyst"` | Current test file has 19 tests; new tests add analyst-specific vectors |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Python version**: 3.14+
- **Naming**: snake_case.py modules, UPPER_SNAKE_CASE constants, PascalCase classes
- **Imports**: Absolute imports, grouped with blank line between sections
- **Docstrings**: Google-style, type hints on all function signatures
- **Module design**: `__all__` for public APIs, `_` prefix for internals
- **GSD Workflow**: All edits through GSD workflow

## Standard Stack

No new dependencies required. Phase 07 is purely additive Python code using existing project infrastructure.

### Core (already installed)
| Library | Version | Purpose | Role in Phase 07 |
|---------|---------|---------|-------------------|
| pydantic-ai | 1.72.0 | Agent framework | TestModel for smoke tests |
| pydantic | 2.12.5 | BaseModel for HallucinationReport | check_hallucinated_metrics return type |
| pytest | 9.0.2 | Test framework | All test execution |

## Architecture Patterns

### Files Modified in Phase 07

```
src/pitcher_narratives/
  personas.py          # ADD: ANALYST constant, update PERSONAS registry, update __all__
  pipeline.py          # MODIFY: check_hallucinated_metrics signature, add _PERSONA_KNOWN_METRICS

tests/
  test_personas.py     # ADD: analyst smoke test, assert_analyst_shape helper
  test_hallucination_guard.py  # ADD: per-persona regression vectors for analyst
```

### Pattern 1: Persona Constant Definition (from Phase 05)

The ANALYST persona follows the exact same pattern as SCOUT. Key fields:

```python
# In personas.py
_ANALYST_OVERLAY = """\
[newsletter voice overlay text]
"""

ANALYST = Persona(
    id="analyst",
    display_name="Analyst",
    description=(
        "Newsletter-style analysis -- 450-800 words, "
        "teaching voice for analytically-inclined fans"
    ),
    overlay=_ANALYST_OVERLAY,
    length_target=(450, 800),
    parent="scout",  # inherits scout overlay's factual-discipline rules
)
```

Source: Existing `SCOUT` definition in `personas.py:133-142`

**Critical: `parent="scout"` enables overlay inheritance.** When `build_writer_system_prompt(ANALYST)` is called, the compositor already handles this:
1. Start with `SHARED_WRITER_BASE`
2. Append parent (SCOUT) overlay
3. Append ANALYST overlay

This is already implemented in `build_writer_system_prompt()` at `personas.py:165-176`.

### Pattern 2: Registry Update

```python
PERSONAS: dict[str, Persona] = {
    "scout": SCOUT,
    "analyst": ANALYST,  # NEW
}
```

This is the only registry change. `get_persona("analyst")` will work automatically.

### Pattern 3: Per-Persona Hallucination Guard Allowlist (PERSONA-10)

```python
# In pipeline.py, near _KNOWN_METRICS
_PERSONA_KNOWN_METRICS: dict[str, frozenset[str]] = {
    "analyst": frozenset({
        "playability",
        "tunneling gap",
        "pitch tree",
        "arsenal depth",
    }),
}

def check_hallucinated_metrics(
    report_text: str,
    persona: str | None = None,
) -> HallucinationReport:
    """..."""
    # ... existing validation ...
    
    found = set(_METRIC_PATTERN.findall(report_text))
    
    # Persona-specific allowlist
    persona_known = _PERSONA_KNOWN_METRICS.get(persona, frozenset()) if persona else frozenset()
    unknown = sorted(found - _KNOWN_METRICS - _TRADITIONAL_STATS - persona_known)
    
    # ... rest unchanged ...
```

**Important finding:** The analyst vocabulary terms (`playability`, `tunneling gap`, `pitch tree`, `arsenal depth`) are plain English and do NOT currently match the `_METRIC_PATTERN` regex (verified by running the regex against each term). The per-persona allowlist mechanism still must be implemented because:
1. The requirement (PERSONA-10) explicitly specifies it
2. TEST-07 requires regression vectors that verify the mechanism works
3. The architecture is forward-looking -- future regex changes or term additions might catch new patterns
4. Phase 08 (generic) will add its own per-persona entries

The `persona` parameter defaults to `None`, so all existing callers (in `cli.py`) continue to work identically -- backward compatibility is preserved.

### Pattern 4: TestModel-Based Pipeline Smoke Test

```python
def test_analyst_pipeline_smoke(ctx):
    """TEST-05 (analyst): Full pipeline with TestModel produces non-empty narrative."""
    test_model = TestModel()
    result = generate_pipeline_streaming(
        ctx,
        provider="gemini",
        thinking="high",
        persona="analyst",
        _model_override=test_model,
    )
    assert isinstance(result, PipelineResult)
    assert len(result.narrative) > 0
    
    expected = build_writer_system_prompt(ANALYST)
    assert expected.startswith(SHARED_WRITER_BASE)
```

Source: Existing `test_scout_pipeline_smoke` in `test_personas.py:168-190`

### Pattern 5: Shape Assertion Helper

```python
def assert_analyst_shape(text: str) -> None:
    """Validate analyst persona output shape: word count, structural elements."""
    words = text.split()
    word_count = len(words)
    
    # Word count bounds from ANALYST.length_target = (450, 800)
    # TestModel produces synthetic text, so bounds must be relaxed for test context
    # Real validation uses the Persona's length_target
    
    # No tables (no pipe-delimited rows)
    assert "|" not in text or text.count("|") < 3, "Analyst output should not contain tables"
    
    # No bullet lists
    for line in text.strip().splitlines():
        stripped = line.strip()
        assert not stripped.startswith("- "), "Analyst output should not contain bullet lists"
    
    # No h1 headings
    assert not any(
        line.strip().startswith("# ") and not line.strip().startswith("## ")
        for line in text.splitlines()
    ), "Analyst output should not contain h1 headings"
```

Note: TestModel produces synthetic placeholder text (not real narrative), so word-count validation against the 450-800 target only applies to real LLM output. The shape helper should validate structural constraints (no tables, no bullets, no h1) which are enforceable even on synthetic text.

### Anti-Patterns to Avoid

- **Do NOT touch `anchor.py`.** Explicitly prohibited for Phases 05-07 per ROADMAP note: "Phase 08 is the only phase that may touch anchor.py."
- **Do NOT modify the existing scout smoke test or scout-related test assertions.** Phase 07 is additive only.
- **Do NOT add `assert_scout_shape` in Phase 07.** TEST-06 says Phase 06 owns the scout shape helper. However, since Phase 06 did not create it, and Phase 07 needs `assert_analyst_shape`, the planner may choose to add `assert_scout_shape` as well for consistency -- but it is not a Phase 07 requirement.
- **Do NOT change `_run_pipeline` or `generate_pipeline_streaming` signatures.** They already accept `persona: str = "scout"` from Phase 06.
- **Do NOT change `cli.py`.** CLI wiring is Phase 09.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Overlay composition | Custom string templating | `build_writer_system_prompt(persona)` | Already handles parent inheritance via `\n\n`.join pattern |
| Persona lookup | Manual dict access | `get_persona(persona_id)` | Raises ValueError with helpful message for unknown ids |
| Pipeline testing | Real LLM calls | `pydantic_ai.models.test.TestModel` | Deterministic, free, fast |
| Test data loading | Custom fixtures | `load_pitcher_data(592155, window_days=30)` | Same fixture pitcher used in existing smoke tests |

## Common Pitfalls

### Pitfall 1: Overlay Ordering Matters for LLM Salience
**What goes wrong:** Placing the analyst's voice instructions before the inherited scout factual-discipline rules causes the LLM to weight voice over accuracy.
**Why it happens:** LLMs give highest salience to the last block in a system prompt.
**How to avoid:** The compositor already places overlays in correct order: base -> parent overlay -> child overlay. The analyst overlay (voice, length, vocabulary) comes LAST, which is correct because voice should be most salient. The scout overlay's factual rules come in the middle, sandwiched between base correctness rules and analyst voice rules.
**Warning signs:** Analyst output violates directional consistency or invents metrics.

### Pitfall 2: Analyst Vocabulary Terms Are Not Currently Regex-Matched
**What goes wrong:** Developer assumes the per-persona allowlist is immediately load-bearing and skips implementation because "the terms don't match anyway."
**Why it happens:** Plain English terms like `playability` don't match `_METRIC_PATTERN` today.
**How to avoid:** Implement the mechanism anyway. It is required by PERSONA-10, tested by TEST-07, and needed for Phase 08's generic persona vocabulary.
**Warning signs:** Missing `persona` parameter on `check_hallucinated_metrics`.

### Pitfall 3: Analyst Overlay Too Long Causes Token Budget Blowout
**What goes wrong:** The composed prompt (base + scout overlay + analyst overlay) exceeds a reasonable system prompt length, consuming tokens that should go to the narrative.
**Why it happens:** Analyst overlay includes teaching instructions, vocabulary permissions, AND the inherited scout overlay (~30 lines).
**How to avoid:** Keep the analyst overlay concise. The scout overlay is ~35 lines; the analyst overlay should be comparable. Research recommends a hard length cap instruction in the overlay ("if you approach 800 words, wrap up").
**Warning signs:** Composed prompt exceeds ~4000 characters.

### Pitfall 4: TestModel Output Does Not Resemble Real Analyst Output
**What goes wrong:** Shape assertion passes on TestModel but fails on real output (or vice versa).
**Why it happens:** TestModel returns generic placeholder text, not newsletter-voice prose.
**How to avoid:** Shape assertions on TestModel output should check structural constraints only (no tables, no bullets, no h1). Word-count validation against 450-800 is only meaningful for real LLM output. The smoke test's job is to verify the pipeline runs without errors and the prompt is correctly composed -- not to validate LLM behavior.
**Warning signs:** Shape assertion that checks for specific vocabulary in TestModel output.

### Pitfall 5: Forgetting to Export ANALYST from __all__
**What goes wrong:** `from pitcher_narratives.personas import ANALYST` fails in tests.
**Why it happens:** New constant added but `__all__` not updated.
**How to avoid:** Add `"ANALYST"` to `__all__` in `personas.py`.
**Warning signs:** ImportError in tests.

### Pitfall 6: Registry Test Assumes Only Scout
**What goes wrong:** Existing test `test_registry_contains_only_scout` fails when ANALYST is added.
**Why it happens:** Phase 05 wrote a test asserting `len(PERSONAS) == 1`.
**How to avoid:** This test MUST be updated when ANALYST is added to the registry. Change assertion to `len(PERSONAS) == 2` and verify both "scout" and "analyst" are present.
**Warning signs:** Test failure on `test_registry_contains_only_scout`.

## Code Examples

### Analyst Overlay Voice Specification

Based on FEATURES.md section 3b and VOICE-02 requirements:

```python
_ANALYST_OVERLAY = """\
You are writing a newsletter-style analysis for analytically-inclined \
baseball fans. Your reader has strong baseball literacy but is not a \
working analyst.

TARGET: 450-800 words, 4-6 paragraphs. Long enough to teach, short \
enough to read over coffee.

VOICE:
- Newsletter tone. First-person plural is optional ("what we're seeing \
here is..."). Teach as you analyze.
- When you name S+, L+, or P+, take a sentence to explain what the \
metric measures and why the pipeline reached its grade. "S+ of 128 on \
the slider means the stuff-only model scored it 28 percent above \
league average on physical characteristics alone; the vertical break \
is the driver."
- Longer sentences and subordinate clauses are fine, but stay \
conversational. Similes and analogies are welcome ("think of L+ as \
the grade the command gets after the stuff is already priced in").
- You may digress briefly to contextualize a finding ("for reference, \
league-average S+ on a sweeper is close to 100").
- Still avoids cheerleading. Still enforces directional consistency.

VOCABULARY:
- Keep the scout banned-word list: never use "degradation," "binary," \
"profiles as," "dominant," "elite," "massive spike."
- Teaching vocabulary is permitted: "playability," "tunneling gap," \
"pitch tree," "arsenal depth," "model," "credit," "grade," \
"below-average," "holds up," "pencils out."
- Three-metric maximum per paragraph, but you may cite the same metric \
twice if the second citation explains the first.

STRUCTURE:
- Prose only. No tables, no bullet lists.
- Bolded leading phrases at the start of paragraphs are allowed.
- No Markdown ## headings (headings invite "meanwhile" energy).
- Lead with the narrative hook — a question or setup anchored to the \
top_improvement or top_concern signal.

For the EXPLAIN THE MODEL section: full-sentence depth. Each plus-metric's \
first appearance gets a sentence explaining what the metric measures and \
why the grade is what it is. This is the teaching persona.

HARD LIMIT: Do not exceed 800 words. If you approach 700 words, wrap up."""
```

Source: FEATURES.md section 3b, VOICE-02, PITFALLS.md section 7

### Per-Persona Allowlist Implementation

```python
# In pipeline.py, after _KNOWN_METRICS definition
_PERSONA_KNOWN_METRICS: dict[str, frozenset[str]] = {
    "analyst": frozenset({
        "playability",
        "tunneling gap",
        "pitch tree",
        "arsenal depth",
    }),
}
```

### Hallucination Guard Signature Change

```python
def check_hallucinated_metrics(
    report_text: str,
    persona: str | None = None,
) -> HallucinationReport:
```

The `persona` parameter is keyword-only by convention (second parameter), with `None` default preserving backward compatibility. All existing callers pass only `report_text`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml (no [tool.pytest] section yet) |
| Quick run command | `uv run python -m pytest tests/test_personas.py tests/test_hallucination_guard.py -x -q` |
| Full suite command | `uv run python -m pytest tests/test_personas.py tests/test_hallucination_guard.py tests/test_pipeline_persona_wiring.py -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VOICE-02 | ANALYST persona exists with correct fields, parent=scout, length_target=(450,800) | unit | `uv run python -m pytest tests/test_personas.py::test_analyst_has_expected_fields -x` | Wave 0 |
| VOICE-02 | Composed analyst prompt starts with SHARED_WRITER_BASE and includes scout overlay | unit | `uv run python -m pytest tests/test_personas.py::test_analyst_composed_prompt_includes_base_and_scout -x` | Wave 0 |
| PERSONA-10 | check_hallucinated_metrics accepts persona parameter | unit | `uv run python -m pytest tests/test_hallucination_guard.py::test_analyst_vocab_not_flagged_with_persona -x` | Wave 0 |
| PERSONA-10 | Calls without persona arg behave identically to v1.9 | unit | `uv run python -m pytest tests/test_hallucination_guard.py -x` (existing tests still pass) | Existing |
| TEST-05 | Analyst pipeline smoke test via TestModel | integration | `uv run python -m pytest tests/test_personas.py::test_analyst_pipeline_smoke -x` | Wave 0 |
| TEST-06 | assert_analyst_shape validates structural elements | unit | `uv run python -m pytest tests/test_personas.py::test_assert_analyst_shape -x` | Wave 0 |
| TEST-07 | Analyst vocab regression vectors | unit | `uv run python -m pytest tests/test_hallucination_guard.py::test_analyst_vocab_not_flagged_with_persona -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/test_personas.py tests/test_hallucination_guard.py tests/test_pipeline_persona_wiring.py -x -q`
- **Per wave merge:** `uv run python -m pytest tests/ --ignore=tests/test_analyst.py -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_personas.py::test_analyst_has_expected_fields` -- covers VOICE-02 field validation
- [ ] `tests/test_personas.py::test_analyst_composed_prompt_includes_base_and_scout` -- covers VOICE-02 composition
- [ ] `tests/test_personas.py::test_analyst_pipeline_smoke` -- covers TEST-05
- [ ] `tests/test_personas.py::assert_analyst_shape` -- covers TEST-06 (helper function, not standalone test)
- [ ] `tests/test_hallucination_guard.py::test_analyst_vocab_not_flagged_with_persona` -- covers TEST-07
- [ ] `tests/test_hallucination_guard.py::test_no_persona_backward_compat` -- covers PERSONA-10 backward compat
- No new framework install needed -- pytest is already available

## Key Implementation Details

### Overlay Inheritance Chain for Analyst

When `build_writer_system_prompt(ANALYST)` is called, the result is:
```
SHARED_WRITER_BASE          (analytical contract, EXPLAIN THE MODEL)
\n\n
_SCOUT_OVERLAY              (banned words, three-metric cap, scouting voice, terse explainer)
\n\n
_ANALYST_OVERLAY             (newsletter voice, teaching depth, 450-800 words, vocabulary permissions)
```

The scout overlay's voice instructions (scouting language, short sentences, 2-3 paragraphs) will be present but superseded by the analyst overlay's voice instructions (newsletter tone, longer sentences, 4-6 paragraphs). This is by design -- the scout overlay's factual-discipline rules (banned words, metric cap, plausibility filters) carry through, while the voice and structural rules are overridden by the analyst overlay that comes last.

### Existing Test That Must Be Updated

`test_personas.py::test_registry_contains_only_scout` (line 119-122) asserts `len(PERSONAS) == 1` and `"scout" in PERSONAS`. This test must be updated to reflect the addition of ANALYST:
```python
def test_registry_contains_scout_and_analyst():
    """After Phase 07 the registry contains scout and analyst personas."""
    assert len(PERSONAS) == 2
    assert "scout" in PERSONAS
    assert "analyst" in PERSONAS
```

### Call Site in cli.py (Phase 09, NOT Phase 07)

The `cli.py` call to `check_hallucinated_metrics(pipe_result.narrative)` at line 205 does NOT pass a persona argument today. Phase 09 (CLI wiring) will update this call to pass `persona=args.persona`. Phase 07 only adds the parameter and the allowlist mechanism -- it does not change any call sites.

## Open Questions

1. **Should `assert_scout_shape` also be created in Phase 07?**
   - What we know: TEST-06 says Phase 06 owns scout shape, but Phase 06 did not create it. Phase 07 needs `assert_analyst_shape`. Phase 08 needs `assert_generic_shape`.
   - What's unclear: Whether creating all three in their respective phases or creating the pattern (scout + analyst) together in Phase 07 is cleaner.
   - Recommendation: Create `assert_analyst_shape` only. Scout shape can be added when needed. Keep scope tight.

2. **How strict should word-count bounds be in `assert_analyst_shape` for TestModel output?**
   - What we know: TestModel returns synthetic text that won't match real word counts. The Persona `length_target=(450, 800)` is the authoritative bound for real output.
   - What's unclear: Whether to validate word count at all in the shape helper when it is only called with TestModel output.
   - Recommendation: The shape helper should accept a `strict_word_count: bool = False` parameter or simply skip word-count validation. Structural checks (no tables, no bullets, no h1) are enforceable on any text.

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/personas.py` -- direct read of Persona dataclass, SCOUT constant, build_writer_system_prompt, registry pattern
- `src/pitcher_narratives/pipeline.py` -- direct read of check_hallucinated_metrics function, _KNOWN_METRICS, _METRIC_PATTERN, HallucinationReport
- `tests/test_personas.py` -- direct read of existing test patterns (18 tests + pipeline integration)
- `tests/test_hallucination_guard.py` -- direct read of existing guard tests (19 tests)
- `.planning/REQUIREMENTS.md` -- VOICE-02, PERSONA-10, TEST-05/06/07 specifications
- `.planning/ROADMAP.md` -- Phase 07 success criteria and dependency chain
- `.planning/research/FEATURES.md` section 3b -- analyst voice specification
- `.planning/research/SUMMARY.md` -- Phase C requirements, risk register items 5 and 11

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` sections 5, 7, 10 -- length cap, per-persona allowlist, shape assertion design
- Runtime verification: regex pattern tested against analyst vocabulary terms (all return empty matches)
- Runtime verification: `check_hallucinated_metrics` current signature confirmed as `(report_text: str)`
- Runtime verification: 42 existing tests pass across test_personas.py, test_hallucination_guard.py, test_pipeline_persona_wiring.py

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, purely additive Python
- Architecture: HIGH -- all patterns established by Phase 05-06, direct code reads
- Pitfalls: HIGH -- verified via runtime testing of regex patterns and function signatures
- Voice specification: MEDIUM -- analyst overlay text is based on research FEATURES.md, not battle-tested against real LLM output

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable -- no external dependencies to drift)
