"""Tests for persona definitions, registry, and prompt composition."""

import dataclasses
from pathlib import Path

import pytest

from pitcher_narratives.personas import (
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


def test_registry_contains_only_scout():
    """At Phase 05 the registry contains only the scout persona."""
    assert len(PERSONAS) == 1
    assert "scout" in PERSONAS


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
