"""Single-voice composition invariants (design §4-5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pitcher_narratives.personas import (
    CHANGES,
    RECAP,
    REPORT,
    SHARED_WRITER_BASE,
    WRITER_VOICE,
    NarrationMode,
    build_writer_system_prompt,
)

_FIX = Path(__file__).parent / "fixtures"
_MODES = {"report": REPORT, "changes": CHANGES, "recap": RECAP}


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_prompt_starts_with_base_then_contains_voice(mode_id):
    p = build_writer_system_prompt(_MODES[mode_id])
    assert p.startswith(SHARED_WRITER_BASE)
    assert WRITER_VOICE in p


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_writer_never_generates_model_explanation(mode_id):
    prompt = build_writer_system_prompt(_MODES[mode_id])
    assert "EXPLAIN THE MODEL" not in prompt
    assert "what the model decided" not in prompt.lower()
    assert "feature importance" not in prompt.lower()


def test_changes_framing_carries_the_change_mandate():
    p = build_writer_system_prompt(CHANGES)
    # Matches the existing _CHANGES_MANDATE text verbatim (case-sensitive).
    assert "Report what has CHANGED" in p


@pytest.mark.parametrize(
    "mode_id,phrase",
    [
        ("report", "350-600 words"),
        ("changes", "250-450 words"),
        ("recap", "60-120 words"),
    ],
)
def test_structure_length_phrase_present(mode_id, phrase):
    assert phrase in build_writer_system_prompt(_MODES[mode_id])


def test_three_modes_produce_distinct_prompts():
    prompts = {m: build_writer_system_prompt(mode) for m, mode in _MODES.items()}
    assert len(set(prompts.values())) == 3


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_matches_frozen_fixture(mode_id):
    expected = (_FIX / f"writer_prompt_{mode_id}.txt").read_text()
    assert build_writer_system_prompt(_MODES[mode_id]) == expected


# ── Universal directive manifest (folded from the retired test_voice_golden) ──
# Every canonical writer directive must survive in the composed report prompt.
# Markers are stable substrings that prove the concern they guard was not
# dropped from SHARED_WRITER_BASE or the synthesis framing.
_UNIVERSAL_MANIFEST = [
    "degradation",  # banned-word list
    "DIRECTIONAL CONSISTENCY",
    "TEMPORAL GROUNDING",
    "Scale language",  # sample/sufficiency calibration
    "Arm-slot",  # rarity is not causality
    "Find the strongest supported thread",
]


@pytest.mark.parametrize("marker", _UNIVERSAL_MANIFEST)
def test_report_prompt_carries_universal_directive(marker):
    """Every universal directive marker survives in the composed report prompt."""
    assert marker in build_writer_system_prompt(REPORT), (
        f"report prompt is missing directive marker {marker!r}"
    )


# ── NarrationMode length-target validation (ported from the old contract) ──


def test_narration_mode_rejects_inverted_length_target():
    """length_target min > max raises at construction."""
    with pytest.raises(ValueError, match="min<=max"):
        NarrationMode(id="bad", length_target=(500, 100))


def test_narration_mode_rejects_non_positive_length_target():
    """length_target with a zero/negative bound raises at construction."""
    with pytest.raises(ValueError, match="positive"):
        NarrationMode(id="bad", length_target=(0, 100))


def test_narration_mode_requires_length_target():
    """length_target has no default — omitting it is a construction-time error."""
    with pytest.raises(TypeError, match="length_target"):
        NarrationMode(id="x")
