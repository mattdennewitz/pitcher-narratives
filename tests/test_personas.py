"""Tests for persona definitions, registry, and prompt composition."""

import dataclasses
from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.personas import (
    ANALYST,
    BRIEF,
    DEFAULT_PERSONA,
    GENERIC,
    NEWSLETTER,
    PERSONAS,
    REPORT,
    SCOUT,
    SCOUT_REPORT,
    SECTIONED,
    SHARED_WRITER_BASE,
    OutputContract,
    Persona,
    build_system_prompt,
    build_writer_system_prompt,
    get_narration_mode,
    get_persona,
)
from pitcher_narratives.pipeline import PipelineResult, generate_pipeline_streaming, make_pipeline_agents

_FIXTURE = Path(__file__).parent / "fixtures" / "writer_prompt_scout.txt"
_FIXTURE_ANALYST = Path(__file__).parent / "fixtures" / "writer_prompt_analyst.txt"
_FIXTURE_GENERIC = Path(__file__).parent / "fixtures" / "writer_prompt_generic.txt"

# Scout-specific voice words that must NOT appear in SHARED_WRITER_BASE.
# These words belong in the scout overlay only. ("elite"/"massive" are NOT
# listed here: they now legitimately appear in the universal banned-word
# directive that lives in SHARED_WRITER_BASE.)
_SCOUT_VOICE_WORDS = ("stuff", "feel", "groove", "tagged")


def test_persona_is_frozen_dataclass():
    """Persona instances are frozen dataclasses — attribute assignment raises."""
    persona = Persona(
        id="test",
        display_name="Test",
        description="A test persona",
        overlay="test overlay",
    )
    assert dataclasses.is_dataclass(persona)
    with pytest.raises(dataclasses.FrozenInstanceError):
        persona.id = "changed"


def test_persona_rejects_empty_overlay():
    """Construction fails fast when overlay is empty."""
    with pytest.raises(ValueError, match="overlay must be non-empty"):
        Persona(
            id="bad",
            display_name="Bad",
            description="bad",
            overlay="",
        )


def test_output_contract_rejects_inverted_length_target():
    """OutputContract construction fails when length_target min > max."""
    with pytest.raises(ValueError, match="min must be <= max"):
        OutputContract(
            id="bad",
            length_target=(500, 100),
            structure="s",
            input_framing="f",
        )


def test_output_contract_rejects_non_positive_length_target():
    """OutputContract construction fails when length_target has zero/negative values."""
    with pytest.raises(ValueError, match="must be positive"):
        OutputContract(
            id="bad",
            length_target=(0, 100),
            structure="s",
            input_framing="f",
        )


def test_personas_registry_is_read_only():
    """PERSONAS is exposed as a MappingProxyType — external mutation fails."""
    with pytest.raises(TypeError):
        PERSONAS["bogus"] = PERSONAS["scout"]  # type: ignore[index]


def test_all_registered_personas_satisfy_invariants():
    """Every persona in PERSONAS has id matching its key and valid parent ref."""
    for pid, persona in PERSONAS.items():
        assert persona.id == pid, (
            f"Registry key {pid!r} does not match persona.id {persona.id!r}"
        )
        if persona.parent is not None:
            assert persona.parent in PERSONAS, (
                f"Persona {pid!r} references unknown parent {persona.parent!r}"
            )


def test_scout_has_expected_fields():
    """SCOUT persona has the correct id, display_name, and parent (voice-only)."""
    scout = PERSONAS["scout"]
    assert scout.id == "scout"
    assert scout.display_name == "Scout"
    assert scout.parent is None


def test_scout_report_contract_is_scout_report():
    """The scout report contract is SCOUT_REPORT with length_target (150, 350)."""
    contract = REPORT.contracts["scout"]
    assert contract is SCOUT_REPORT
    assert contract.length_target == (150, 350)
    assert all(isinstance(v, int) for v in contract.length_target)


def test_default_persona_is_scout():
    """DEFAULT_PERSONA is the same object as PERSONAS['scout']."""
    assert DEFAULT_PERSONA is PERSONAS["scout"]


def test_get_persona_returns_scout():
    """get_persona('scout') returns the SCOUT persona from the registry."""
    assert get_persona("scout") is PERSONAS["scout"]


def test_get_persona_unknown_raises_valueerror():
    """get_persona raises ValueError with the unknown id in the message."""
    with pytest.raises(ValueError, match="bogus"):
        get_persona("bogus")


def test_report_mode_maps_personas_to_report_contracts():
    """REPORT.contracts reproduces the legacy report-contracts mapping."""
    assert REPORT.id == "report"
    assert REPORT.contracts["scout"] is SCOUT_REPORT
    assert REPORT.contracts["analyst"] is NEWSLETTER
    assert REPORT.contracts["generic"] is SECTIONED


def test_narration_mode_is_frozen():
    """NarrationMode is immutable so registry identity is stable."""
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        REPORT.id = "changed"  # type: ignore[misc]


def test_get_narration_mode_returns_report():
    """get_narration_mode('report') resolves to the REPORT instance."""
    assert get_narration_mode("report") is REPORT


def test_get_narration_mode_unknown_raises_valueerror():
    """Unknown mode ids raise ValueError listing valid ids (not KeyError)."""
    with pytest.raises(ValueError, match="bogus"):
        get_narration_mode("bogus")


def test_build_writer_system_prompt_mode_arg_is_byte_identical_to_default():
    """Passing mode=REPORT explicitly equals the default single-arg call."""
    for pid in ("scout", "analyst", "generic"):
        p = get_persona(pid)
        assert build_writer_system_prompt(p, REPORT) == build_writer_system_prompt(p)


def test_fixture_exists():
    """Frozen fixture file exists and is non-empty."""
    assert _FIXTURE.exists(), f"Fixture not found at {_FIXTURE}"
    content = _FIXTURE.read_text()
    assert len(content) > 0, "Fixture file is empty"


def test_scout_composed_prompt_is_byte_identical_to_v19():
    """Composed scout prompt matches the frozen fixture byte-for-byte."""
    expected = _FIXTURE.read_text()
    actual = build_writer_system_prompt(PERSONAS["scout"])
    assert actual == expected, (
        f"Scout composed prompt differs from fixture. "
        f"Lengths: {len(actual)} vs {len(expected)}"
    )


def test_analyst_composed_prompt_is_byte_identical_to_fixture():
    """Composed analyst prompt matches the frozen fixture byte-for-byte.

    Guards against accidental whitespace drift, overlay reordering, or
    parent-chain regressions in the analyst persona.
    """
    assert _FIXTURE_ANALYST.exists(), f"Fixture not found at {_FIXTURE_ANALYST}"
    expected = _FIXTURE_ANALYST.read_text()
    actual = build_writer_system_prompt(PERSONAS["analyst"])
    assert actual == expected, (
        f"Analyst composed prompt differs from fixture. "
        f"Lengths: {len(actual)} vs {len(expected)}"
    )


def test_generic_composed_prompt_is_byte_identical_to_fixture():
    """Composed generic prompt matches the frozen fixture byte-for-byte.

    Guards against accidental whitespace drift, overlay reordering, or
    parent-chain regressions in the generic persona.
    """
    assert _FIXTURE_GENERIC.exists(), f"Fixture not found at {_FIXTURE_GENERIC}"
    expected = _FIXTURE_GENERIC.read_text()
    actual = build_writer_system_prompt(PERSONAS["generic"])
    assert actual == expected, (
        f"Generic composed prompt differs from fixture. "
        f"Lengths: {len(actual)} vs {len(expected)}"
    )


def test_all_three_personas_produce_distinct_composed_prompts():
    """The three personas must not accidentally produce identical prompts.

    Catches overlay-collision bugs where a refactor leaves two personas
    pointing at the same overlay string (or an inheritance chain that
    short-circuits a child overlay).
    """
    composed = {
        pid: build_writer_system_prompt(p) for pid, p in PERSONAS.items()
    }
    assert len(set(composed.values())) == len(composed), (
        f"Personas produced non-distinct composed prompts: "
        f"{[pid for pid in composed]}"
    )


def test_base_prompt_has_no_voice_words():
    """SHARED_WRITER_BASE contains none of the scout-specific voice words."""
    base_lower = SHARED_WRITER_BASE.lower()
    for word in _SCOUT_VOICE_WORDS:
        assert word not in base_lower, (
            f"Voice word {word!r} found in SHARED_WRITER_BASE — "
            f"should be in scout overlay only"
        )


def test_base_prompt_has_universal_analytical_rules():
    """SHARED_WRITER_BASE carries the universal analytical directives.

    EXPLAIN THE MODEL now lives in the synthesis-input framing (not the
    universal base); the universal base holds the directives that apply to
    every composed prompt, including the digest path.
    """
    assert "DIRECTIONAL CONSISTENCY" in SHARED_WRITER_BASE
    assert "TEMPORAL GROUNDING" in SHARED_WRITER_BASE
    assert "degradation" in SHARED_WRITER_BASE  # banned-word list, single-sourced


def test_report_prompt_has_explainer_section():
    """EXPLAIN THE MODEL survives in the composed report prompt (synthesis framing)."""
    assert "EXPLAIN THE MODEL" in build_writer_system_prompt(PERSONAS["scout"])


def test_scout_overlay_contains_voice_section():
    """Scout overlay includes the VOICE instruction block."""
    overlay = PERSONAS["scout"].overlay
    assert "VOICE:" in overlay
    assert "Write like an analyst talking to another analyst" in overlay


def test_all_exports_importable():
    """All 6 public names from __all__ are accessible and non-None."""
    assert Persona is not None
    assert PERSONAS is not None
    assert DEFAULT_PERSONA is not None
    assert SHARED_WRITER_BASE is not None
    assert build_writer_system_prompt is not None
    assert get_persona is not None


def test_registry_contains_all_three():
    """After Phase 08 the registry contains scout, analyst, and generic personas."""
    assert len(PERSONAS) == 3
    assert "scout" in PERSONAS
    assert "analyst" in PERSONAS
    assert "generic" in PERSONAS


def test_composed_prompt_starts_with_base():
    """The composed scout prompt begins with SHARED_WRITER_BASE."""
    composed = build_writer_system_prompt(PERSONAS["scout"])
    assert composed.startswith(SHARED_WRITER_BASE)


# ── Pipeline integration tests (Phase 06: PERSONA-07, PERSONA-08, TEST-05) ──


@pytest.fixture(scope="module")
def ctx():
    """Load pitcher data once per module for pipeline smoke tests."""
    data = load_pitcher_data(592155, recent_appearances=10)
    return assemble_pitcher_context(data)


class TestPipelinePersonaIntegration:
    """Tests that the pipeline correctly wires persona through to the writer agent."""

    def test_writer_prompt_deleted_from_pipeline(self):
        """PERSONA-07: _WRITER_PROMPT no longer importable from pipeline."""
        with pytest.raises(ImportError):
            from pitcher_narratives.pipeline import _WRITER_PROMPT  # noqa: F401

    def test_default_and_explicit_scout_produce_identical_writer_prompts(self):
        """PERSONA-08: No-arg and explicit-SCOUT produce the same writer prompt."""
        agents_default = make_pipeline_agents("gemini", "high")
        agents_explicit = make_pipeline_agents("gemini", "high", SCOUT)
        assert agents_default.writer._system_prompts == agents_explicit.writer._system_prompts

    def test_writer_receives_composed_persona_prompt(self):
        """PERSONA-07: Writer agent's system prompt is the full composed persona prompt."""
        agents = make_pipeline_agents("gemini", "high")
        expected = build_writer_system_prompt(SCOUT)
        assert agents.writer._system_prompts == (expected,)

    def test_writer_prompt_matches_frozen_fixture(self):
        """PERSONA-07 + TEST-05: Writer prompt equals the frozen fixture byte-for-byte."""
        agents = make_pipeline_agents("gemini", "high")
        fixture = _FIXTURE.read_text()
        assert agents.writer._system_prompts[0] == fixture


def test_scout_pipeline_smoke(ctx):
    """TEST-05 (scout): Full pipeline with TestModel produces non-empty narrative.

    Verifies:
    - Pipeline runs end-to-end without errors using TestModel
    - Result is a PipelineResult with a non-empty narrative
    - Writer agent received the correct composed scout prompt (matches fixture)
    """
    test_model = TestModel(call_tools=[])
    result = generate_pipeline_streaming(
        ctx,
        provider="gemini",
        thinking="high",
        persona="scout",
        _model_override=test_model,
    )
    assert isinstance(result, PipelineResult)
    assert len(result.narrative) > 0

    # Verify the writer prompt matches the frozen fixture
    fixture = _FIXTURE.read_text()
    expected = build_writer_system_prompt(SCOUT)
    assert expected == fixture


# -- Analyst persona unit tests (Phase 07: VOICE-02) --


def test_analyst_has_expected_fields():
    """VOICE-02: ANALYST persona has correct id, parent, contract, and display_name."""
    analyst = PERSONAS["analyst"]
    assert analyst.id == "analyst"
    assert analyst.display_name == "Analyst"
    assert analyst.parent == "scout"
    assert REPORT.contracts["analyst"] is NEWSLETTER
    assert NEWSLETTER.length_target == (450, 800)
    assert "newsletter" in analyst.description.lower() or "teaching" in analyst.description.lower()


def test_analyst_composed_prompt_includes_base_and_scout():
    """VOICE-02: Composed analyst prompt contains SHARED_WRITER_BASE and scout overlay."""
    composed = build_writer_system_prompt(ANALYST)
    assert composed.startswith(SHARED_WRITER_BASE)
    # Scout overlay content inherited via parent="scout"
    assert "Write like an analyst talking to another analyst" in composed
    # Analyst overlay content
    assert "newsletter" in composed.lower()
    assert "450-800 words" in composed


def test_analyst_overlay_has_teaching_vocabulary():
    """VOICE-02: Analyst overlay permits teaching vocabulary."""
    overlay = ANALYST.overlay
    for term in ("playability", "tunneling gap", "pitch tree", "arsenal depth"):
        assert term in overlay, f"Teaching vocabulary term {term!r} missing from analyst overlay"


def test_newsletter_contract_has_hard_word_limit():
    """VOICE-02: The NEWSLETTER contract enforces the hard 800-word ceiling.

    The hard limit is a structure/length concern, so it now lives on the
    output contract rather than the (voice-only) analyst overlay.
    """
    structure = NEWSLETTER.structure
    assert "800 words" in structure
    assert "HARD LIMIT" in structure


# -- Analyst shape assertion helper (Phase 07: TEST-06) --


def assert_analyst_shape(text: str) -> None:
    """TEST-06: Validate analyst persona output shape.

    Checks structural constraints enforceable on any text (including
    TestModel synthetic output). Word-count validation against the
    450-800 target only applies to real LLM output, not TestModel.

    Args:
        text: The narrative text to validate.

    Raises:
        AssertionError: If structural constraints are violated.
    """
    # No tables (pipe-delimited rows)
    lines = text.strip().splitlines()
    table_lines = [l for l in lines if l.strip().count("|") >= 2]
    assert len(table_lines) == 0, (
        f"Analyst output should not contain tables, found {len(table_lines)} table-like lines"
    )

    # No bullet lists
    for line in lines:
        stripped = line.strip()
        assert not stripped.startswith("- "), (
            f"Analyst output should not contain bullet lists: {stripped[:60]}"
        )
        assert not stripped.startswith("* "), (
            f"Analyst output should not contain bullet lists: {stripped[:60]}"
        )

    # No h1 headings (## is also banned for analyst per overlay, but h1 is the hard constraint)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            assert not stripped.startswith("# ") or stripped.startswith("## "), (
                f"Analyst output should not contain h1 headings: {stripped[:60]}"
            )


def test_assert_analyst_shape_rejects_table():
    """TEST-06: Shape helper catches tables."""
    with pytest.raises(AssertionError, match="table"):
        assert_analyst_shape("| Pitch | S+ | L+ |\n| Slider | 110 | 95 |")


def test_assert_analyst_shape_rejects_bullets():
    """TEST-06: Shape helper catches bullet lists."""
    with pytest.raises(AssertionError, match="bullet"):
        assert_analyst_shape("Key findings:\n- The slider improved\n- The curve declined")


def test_assert_analyst_shape_accepts_clean_prose():
    """TEST-06: Shape helper accepts clean narrative prose."""
    prose = (
        "The slider has been the story of this window. S+ jumped to 128, "
        "driven almost entirely by vertical break gains. That is a significant "
        "move for a pitch that was already above average."
    )
    assert_analyst_shape(prose)  # Should not raise


# -- Analyst pipeline smoke test (Phase 07: TEST-05) --


def test_analyst_pipeline_smoke(ctx):
    """TEST-05 (analyst): Full pipeline with TestModel produces non-empty narrative.

    Verifies:
    - Pipeline runs end-to-end with persona='analyst' using TestModel
    - Result is a PipelineResult with a non-empty narrative
    - Composed analyst prompt starts with SHARED_WRITER_BASE
    - Composed analyst prompt includes scout overlay (via parent inheritance)
    """
    test_model = TestModel(call_tools=[])
    result = generate_pipeline_streaming(
        ctx,
        provider="gemini",
        thinking="high",
        persona="analyst",
        _model_override=test_model,
    )
    assert isinstance(result, PipelineResult)
    assert len(result.narrative) > 0

    # Verify the composed prompt includes base and scout overlay
    expected = build_writer_system_prompt(ANALYST)
    assert expected.startswith(SHARED_WRITER_BASE)
    assert "Write like an analyst talking to another analyst" in expected


# ── Generic persona unit tests (Phase 08: VOICE-03) ──


def test_generic_has_expected_fields():
    """VOICE-03: GENERIC persona has correct id, parent, contract, and display_name."""
    generic = PERSONAS["generic"]
    assert generic.id == "generic"
    assert generic.display_name == "Generic"
    assert generic.parent == "scout"
    assert REPORT.contracts["generic"] is SECTIONED
    assert SECTIONED.length_target == (300, 500)
    assert "structured" in generic.description.lower() or "section" in generic.description.lower()


def test_generic_composed_prompt_includes_base_and_scout():
    """VOICE-03: Composed generic prompt contains SHARED_WRITER_BASE and scout overlay."""
    composed = build_writer_system_prompt(GENERIC)
    assert composed.startswith(SHARED_WRITER_BASE)
    # Scout overlay content inherited via parent="scout"
    assert "Write like an analyst talking to another analyst" in composed
    # Generic overlay content
    assert "## Stuff" in composed
    assert "## Summary Table" in composed
    assert "Signal | Key Finding | Grade" in composed


def test_sectioned_contract_fixes_section_order():
    """VOICE-03: The SECTIONED contract lists the six sections in fixed order.

    Section layout is structure, so it lives on the output contract now, not
    the (voice-only) generic overlay.
    """
    structure = SECTIONED.structure
    expected_order = (
        "## Stuff",
        "## Location",
        "## Run Value & Execution",
        "## Trend",
        "## Game Shape",
        "## Summary Table",
    )
    positions = [structure.find(section) for section in expected_order]
    assert all(p >= 0 for p in positions), f"Missing section(s): {[s for s, p in zip(expected_order, positions) if p < 0]}"
    assert positions == sorted(positions), f"Sections out of order: {list(zip(expected_order, positions))}"


def test_sectioned_contract_forbids_h1():
    """VOICE-03: The SECTIONED contract explicitly forbids h1 (single #) headings."""
    assert "FORBIDDEN: Markdown h1 headings" in SECTIONED.structure


def test_sectioned_contract_has_override_language():
    """VOICE-03: The SECTIONED contract overrides the no-headers/no-tables rule."""
    structure = SECTIONED.structure
    assert "STRUCTURE OVERRIDE" in structure or "override" in structure.lower()


def test_sectioned_contract_has_hard_word_limit():
    """VOICE-03: The SECTIONED contract enforces the hard 500-word ceiling."""
    structure = SECTIONED.structure
    assert "500 words" in structure
    assert "HARD LIMIT" in structure


# ── BRIEF contract: 2-3 sentence recent-vs-window summary ──


def test_brief_contract_fields():
    """BRIEF is a valid short-form contract with a sentence-scale word target."""
    assert isinstance(BRIEF, OutputContract)
    assert BRIEF.id == "brief"
    assert BRIEF.length_target == (40, 90)
    assert all(isinstance(v, int) for v in BRIEF.length_target)


def test_brief_structure_targets_recent_vs_window_with_sentence_cap():
    """The BRIEF structure leads on recent-vs-window and caps at 3 sentences."""
    structure = BRIEF.structure
    assert "2-3 sentence" in structure
    assert "most recent appearance" in structure
    # The window contrast is the defining frame, not an afterthought.
    assert "window" in structure
    assert "HARD LIMIT" in structure
    assert "3 sentences" in structure
    # Short form: no tables/headers/bullets.
    assert "prose only" in structure


def test_brief_framing_contrasts_recent_against_window():
    """The BRIEF input framing names the recent-vs-window contrast explicitly."""
    framing = BRIEF.input_framing
    assert "MOST RECENT appearance" in framing
    assert "trending" in framing or "window" in framing


def test_brief_framing_suppresses_model_teaching():
    """BRIEF must NOT carry the heavy EXPLAIN-THE-MODEL directive.

    The full synthesis capsule requires contextualizing the grading model on
    first reference; that is incompatible with a 2-3 sentence brief, so BRIEF
    uses a dedicated framing that explicitly suppresses it.
    """
    assert "EXPLAIN THE MODEL" not in BRIEF.input_framing
    assert "do NOT pause to explain the grading model" in BRIEF.input_framing


def test_brief_framing_leads_with_the_reports_thread():
    """BRIEF distills an already-anchored report, so it inherits the report's
    thread instead of re-deriving one from raw signals."""
    framing = BRIEF.input_framing
    assert "central thread" in framing
    assert "Do not re-derive a thread of your own" in framing


def test_brief_framing_preserves_report_hedging():
    """A finding the report stated tentatively must stay tentative."""
    framing = BRIEF.input_framing
    assert "tentative" in framing
    assert "never harden" in framing


def test_brief_framing_forbids_new_findings():
    """Grounding is recover-only: no finding the report did not make."""
    framing = BRIEF.input_framing
    assert "did not make" in framing
    # The raw-signal selection machinery is gone.
    assert "Do not pick by your own judgment" not in framing
    assert "fall back" not in framing


@pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
def test_brief_composes_with_every_persona(persona_id: str) -> None:
    """BRIEF composes through the voice system, honoring each persona's voice.

    The composed prompt layers the universal base, BRIEF's framing, the
    persona voice chain, and BRIEF's structure — and does not leak the heavy
    synthesis-capsule model-teaching directive.
    """
    persona = get_persona(persona_id)
    prompt = build_system_prompt(persona, BRIEF)
    # Universal base leads; brief framing + structure are present.
    assert prompt.startswith(SHARED_WRITER_BASE)
    assert "MOST RECENT appearance" in prompt
    assert "2-3 sentence" in prompt
    # Thread-inheritance directive survives composition (recover-only framing).
    assert "central thread" in prompt
    assert "Do not re-derive a thread of your own" in prompt
    # Persona voice is layered in (scout voice flows to all three via the chain).
    assert "Write like an analyst talking to another analyst" in prompt
    # Brief stays terse — the synthesis capsule's model-teaching mandate is absent.
    assert "Every capsule must contextualize the grading system" not in prompt


def test_brief_is_not_a_persona_report_contract():
    """BRIEF is an alternate output target, not any persona's canonical report."""
    assert BRIEF not in REPORT.contracts.values()


# ── Generic shape assertion helper (Phase 08: TEST-06) ──


import re as _re

_GENERIC_SECTIONS = (
    "## Stuff",
    "## Location",
    "## Run Value & Execution",
    "## Trend",
    "## Game Shape",
    "## Summary Table",
)

_TABLE_SEPARATOR_RE = _re.compile(r"^\s*\|[\s\-|:]+\|\s*$")


def assert_generic_shape(text: str, *, populated_signal_count: int | None = None) -> None:
    """TEST-06: Validate generic persona output shape.

    Checks structural constraints:
    - No h1 headings (single `#` lines, excluding `##`).
    - All six allowed sections present in overlay-fixed order.
    - Exactly one markdown table (detected by separator line).
    - Table data row count equals populated_signal_count when provided.

    Args:
        text: Narrative text to validate.
        populated_signal_count: If given, asserts the table's data-row
            count equals this number. Omit on TestModel output.

    Raises:
        AssertionError: If structural constraints are violated.
    """
    lines = text.strip().splitlines()

    # No h1 headings (line starting with "# " but not "## ")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("##"):
            raise AssertionError(
                f"Generic output must not contain h1 headings: {stripped[:60]!r}"
            )

    # Allowed section set present, in order
    section_positions = [(s, text.find(s)) for s in _GENERIC_SECTIONS]
    missing = [s for s, pos in section_positions if pos == -1]
    if missing:
        raise AssertionError(f"Generic output missing sections: {missing}")
    positions = [pos for _, pos in section_positions]
    if positions != sorted(positions):
        raise AssertionError(
            "Generic output sections are out of order. "
            f"Expected order: {list(_GENERIC_SECTIONS)}"
        )

    # Exactly one markdown table (separator line is the fingerprint)
    separator_lines = [l for l in lines if _TABLE_SEPARATOR_RE.match(l)]
    if len(separator_lines) != 1:
        raise AssertionError(
            f"Generic output must contain exactly one summary table, "
            f"found {len(separator_lines)} table separator lines"
        )

    # Row count check (only when caller provides the expected count)
    if populated_signal_count is not None:
        sep_idx = lines.index(separator_lines[0])
        data_rows = 0
        for line in lines[sep_idx + 1:]:
            stripped = line.strip()
            if not stripped or not stripped.startswith("|"):
                break
            data_rows += 1
        if data_rows != populated_signal_count:
            raise AssertionError(
                f"Generic summary table has {data_rows} data rows, "
                f"expected {populated_signal_count} (one per populated KeySignals entry)"
            )


def _valid_generic_capsule(num_rows: int = 2) -> str:
    """Build a synthetic well-formed generic capsule for shape-helper tests."""
    rows = "\n".join(
        f"| Top Improvement | Row {i} finding | S+ 11{i} |" for i in range(num_rows)
    )
    return (
        "## Stuff\nThe slider graded S+ 112 above league average.\n\n"
        "## Location\nFastball L+ 94 below league average.\n\n"
        "## Run Value & Execution\nThe arsenal produces -0.5 xRV100.\n\n"
        "## Trend\nVelocity stable vs season baseline.\n\n"
        "## Game Shape\nThird-time-through gap manageable.\n\n"
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        f"{rows}\n"
    )


def test_assert_generic_shape_accepts_valid_capsule():
    """TEST-06: Shape helper accepts a well-formed synthetic generic capsule."""
    assert_generic_shape(_valid_generic_capsule(num_rows=2))  # Should not raise


def test_assert_generic_shape_rejects_h1():
    """TEST-06: Shape helper catches h1 headings."""
    bad = "# Scouting Report\n" + _valid_generic_capsule(num_rows=2)
    with pytest.raises(AssertionError, match="h1"):
        assert_generic_shape(bad)


def test_assert_generic_shape_rejects_missing_section():
    """TEST-06: Shape helper catches missing sections."""
    bad = _valid_generic_capsule(num_rows=2).replace("## Trend\nVelocity stable vs season baseline.\n\n", "")
    with pytest.raises(AssertionError, match="missing sections"):
        assert_generic_shape(bad)


def test_assert_generic_shape_rejects_multiple_tables():
    """TEST-06: Shape helper catches multiple markdown tables."""
    bad = _valid_generic_capsule(num_rows=2) + "\n| A | B |\n|---|---|\n| x | y |\n"
    with pytest.raises(AssertionError, match="exactly one summary table"):
        assert_generic_shape(bad)


def test_assert_generic_shape_rejects_wrong_row_count():
    """TEST-06: Shape helper catches row-count mismatch when count provided."""
    capsule_with_2_rows = _valid_generic_capsule(num_rows=2)
    with pytest.raises(AssertionError, match="data rows"):
        assert_generic_shape(capsule_with_2_rows, populated_signal_count=5)


# ── Generic pipeline smoke test (Phase 08: TEST-05) ──


def test_generic_pipeline_smoke(ctx):
    """TEST-05 (generic): Full pipeline with TestModel produces non-empty narrative.

    Verifies:
    - Pipeline runs end-to-end with persona='generic' using TestModel
    - Result is a PipelineResult with a non-empty narrative
    - Composed generic prompt starts with SHARED_WRITER_BASE
    - Composed generic prompt includes scout overlay (via parent inheritance)
    - Composed generic prompt includes generic overlay section markers

    Note: This test does NOT call assert_generic_shape on the TestModel
    output. TestModel returns a canned placeholder, not sectioned output.
    The shape helper is validated against handcrafted synthetic capsules
    in the test_assert_generic_shape_* tests above.
    """
    test_model = TestModel(call_tools=[])
    result = generate_pipeline_streaming(
        ctx,
        provider="gemini",
        thinking="high",
        persona="generic",
        _model_override=test_model,
    )
    assert isinstance(result, PipelineResult)
    assert len(result.narrative) > 0

    # Verify the composed prompt includes base + scout + generic content
    expected = build_writer_system_prompt(GENERIC)
    assert expected.startswith(SHARED_WRITER_BASE)
    assert "Write like an analyst talking to another analyst" in expected
    assert "## Stuff" in expected
    assert "## Summary Table" in expected


# ── Arm-slot insight in writer base ──────────────────────────────────


def test_shared_base_surfaces_arm_slot_insight():
    """SHARED_WRITER_BASE instructs the writer to keep arm-slot shape insight."""
    assert "arm slot" in SHARED_WRITER_BASE.lower()
    assert "DEAD ZONE" in SHARED_WRITER_BASE


# ── RT-4: fallback contract for unmapped personas ─────────────────────


def test_build_writer_system_prompt_falls_back_to_scout_report_for_unknown_persona():
    """RT-4: build_writer_system_prompt uses SCOUT_REPORT for personas not in the mode's contracts.

    A newly added voice persona whose id is not yet in the mode's contracts must
    not raise a KeyError.  It should produce a SCOUT_REPORT-shaped prompt (i.e.
    contain the structure fingerprint phrase) rather than crashing.
    """
    unknown = Persona(
        id="future_voice",
        display_name="Future Voice",
        description="A persona not yet mapped to a report contract",
        overlay="Write in a future style.",
    )
    # Must not raise KeyError
    prompt = build_writer_system_prompt(unknown)
    # SCOUT_REPORT structure is "2-3 paragraph" — the fallback contract's fingerprint
    assert "2-3 paragraph" in prompt, (
        "build_writer_system_prompt should fall back to SCOUT_REPORT for unmapped "
        "personas; expected structure phrase '2-3 paragraph' in composed prompt"
    )


def test_report_validation_policy_matches_config_depths():
    """REPORT keeps today's depths; config is the single source of truth."""
    from pitcher_narratives.config import MAX_FACT_REVISIONS, MAX_REVISIONS
    from pitcher_narratives.personas import REPORT, ValidationPolicy

    assert REPORT.validation == ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    )
    assert (REPORT.validation.anchor_depth, REPORT.validation.fact_depth) == (5, 2)


def test_validation_policy_is_frozen():
    from dataclasses import FrozenInstanceError

    import pytest

    from pitcher_narratives.personas import ValidationPolicy

    policy = ValidationPolicy(anchor_depth=1, fact_depth=2)
    with pytest.raises(FrozenInstanceError):
        policy.anchor_depth = 3  # type: ignore[misc]


def test_recap_mode_registered_and_resolvable():
    from pitcher_narratives.personas import (
        NARRATION_MODES,
        RECAP,
        get_narration_mode,
    )

    assert set(NARRATION_MODES) == {"report", "recap"}
    assert get_narration_mode("recap") is RECAP
    assert RECAP.id == "recap"


def test_recap_validation_depths():
    """RECAP caps anchor at 1, keeps fact at 2 (design §7)."""
    from pitcher_narratives.personas import RECAP

    assert (RECAP.validation.anchor_depth, RECAP.validation.fact_depth) == (1, 2)


def test_recap_contract_shape_and_all_personas_mapped():
    from pitcher_narratives.personas import RECAP, RECAP_BRIEF
    from pitcher_narratives.personas import _SYNTHESIS_FRAMING

    assert RECAP_BRIEF.id == "recap"
    assert RECAP_BRIEF.length_target == (40, 90)
    # RECAP writes FROM the analyses (synthesis framing), not by distilling a
    # finished report — that is what lets it render off the shared spine.
    assert RECAP_BRIEF.input_framing is _SYNTHESIS_FRAMING
    # Every persona is mapped, so build_writer_system_prompt never falls back.
    assert set(RECAP.contracts) == {"scout", "analyst", "generic"}
    assert all(c is RECAP_BRIEF for c in RECAP.contracts.values())


def test_recap_writer_prompt_uses_brief_structure_not_report_structure():
    """The composed RECAP writer prompt must carry the brief structure and the
    synthesis framing — proving the mode selects the recap contract, not the
    report capsule structure."""
    from pitcher_narratives.personas import (
        PERSONAS,
        RECAP,
        REPORT,
        build_writer_system_prompt,
    )

    recap_prompt = build_writer_system_prompt(PERSONAS["scout"], RECAP)
    report_prompt = build_writer_system_prompt(PERSONAS["scout"], REPORT)
    # A distinctive phrase from _RECAP_STRUCTURE appears only in recap.
    assert "executive brief" in recap_prompt.lower()
    assert recap_prompt != report_prompt
