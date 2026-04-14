"""Tests for persona definitions, registry, and prompt composition."""

import dataclasses
from pathlib import Path

import pytest

from pitcher_narratives.personas import (
    ANALYST,  # NEW
    Persona,
    PERSONAS,
    SCOUT,
    DEFAULT_PERSONA,
    SHARED_WRITER_BASE,
    build_writer_system_prompt,
    get_persona,
)
from pitcher_narratives.pipeline import make_pipeline_agents, generate_pipeline_streaming, PipelineResult
from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pydantic_ai.models.test import TestModel

_FIXTURE = Path(__file__).parent / "fixtures" / "writer_prompt_scout.txt"

# Scout-specific voice words that must NOT appear in SHARED_WRITER_BASE.
# These words belong in the scout overlay only.
_SCOUT_VOICE_WORDS = ("stuff", "feel", "groove", "tagged", "elite", "massive")


def test_persona_is_frozen_dataclass():
    """Persona instances are frozen dataclasses — attribute assignment raises."""
    persona = Persona(
        id="test",
        display_name="Test",
        description="A test persona",
        overlay="test overlay",
        length_target=(100, 200),
    )
    assert dataclasses.is_dataclass(persona)
    with pytest.raises(dataclasses.FrozenInstanceError):
        persona.id = "changed"


def test_scout_has_expected_fields():
    """SCOUT persona has the correct id, display_name, parent, and length_target."""
    scout = PERSONAS["scout"]
    assert scout.id == "scout"
    assert scout.display_name == "Scout"
    assert scout.parent is None
    assert isinstance(scout.length_target, tuple)
    assert len(scout.length_target) == 2
    assert all(isinstance(v, int) for v in scout.length_target)


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


def test_base_prompt_has_no_voice_words():
    """SHARED_WRITER_BASE contains none of the scout-specific voice words."""
    base_lower = SHARED_WRITER_BASE.lower()
    for word in _SCOUT_VOICE_WORDS:
        assert word not in base_lower, (
            f"Voice word {word!r} found in SHARED_WRITER_BASE — "
            f"should be in scout overlay only"
        )


def test_base_prompt_has_explainer_section():
    """SHARED_WRITER_BASE contains the EXPLAIN THE MODEL instruction."""
    assert "EXPLAIN THE MODEL" in SHARED_WRITER_BASE


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


def test_registry_contains_scout_and_analyst():
    """After Phase 07 the registry contains scout and analyst personas."""
    assert len(PERSONAS) == 2
    assert "scout" in PERSONAS
    assert "analyst" in PERSONAS


def test_composed_prompt_starts_with_base():
    """The composed scout prompt begins with SHARED_WRITER_BASE."""
    composed = build_writer_system_prompt(PERSONAS["scout"])
    assert composed.startswith(SHARED_WRITER_BASE)


# ── Pipeline integration tests (Phase 06: PERSONA-07, PERSONA-08, TEST-05) ──


@pytest.fixture(scope="module")
def ctx():
    """Load pitcher data once per module for pipeline smoke tests."""
    data = load_pitcher_data(592155, window_days=30)
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
    test_model = TestModel()
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
    """VOICE-02: ANALYST persona has correct id, parent, length_target, and display_name."""
    analyst = PERSONAS["analyst"]
    assert analyst.id == "analyst"
    assert analyst.display_name == "Analyst"
    assert analyst.parent == "scout"
    assert analyst.length_target == (450, 800)
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


def test_analyst_overlay_has_hard_word_limit():
    """VOICE-02: Analyst overlay enforces hard 800-word ceiling."""
    overlay = ANALYST.overlay
    assert "800 words" in overlay
    assert "HARD LIMIT" in overlay


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

    # Verify the composed prompt includes base and scout overlay
    expected = build_writer_system_prompt(ANALYST)
    assert expected.startswith(SHARED_WRITER_BASE)
    assert "Write like an analyst talking to another analyst" in expected
