"""Tests for persona definitions, registry, and prompt composition."""

import dataclasses
from pathlib import Path

import pytest

from pitcher_narratives.personas import (
    Persona,
    PERSONAS,
    DEFAULT_PERSONA,
    SHARED_WRITER_BASE,
    build_writer_system_prompt,
    get_persona,
)

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
