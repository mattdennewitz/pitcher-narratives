"""Tests for the within-game deviation block rendered into the game-shape
specialist input (design 2026-07-08-game-shape-deviation-gate, Task 4).

`_render_deviation_block` is a pure function: empty deviations -> an
explicit "typical, stay silent" instruction; material deviations -> one
residual line per cell (the residual + robust z + direction), never the
raw within-game value.
"""

from __future__ import annotations

from pitcher_narratives.engine.tto import TTODeviation
from pitcher_narratives.pipeline import _render_deviation_block


def test_typical_input_instructs_silence():
    text = _render_deviation_block([])  # no material deviations
    assert "typical" in text.lower()
    assert "do not report" in text.lower()


def test_material_input_speaks_residual_not_raw_fade():
    devs = [TTODeviation(3, "velo", -4.5, -1.1, -3.2, "fatigue")]
    text = _render_deviation_block(devs)
    assert "vs" in text and "-1.1" in text  # the expected value is shown
    assert "z" in text.lower() and "-3.2" in text  # the residual/z, not the raw fade
    assert "fatigue" in text.lower()


def test_material_input_shows_actual_delta():
    """The actual observed delta is shown alongside the expected median."""
    devs = [TTODeviation(3, "velo", -4.5, -1.1, -3.2, "fatigue")]
    text = _render_deviation_block(devs)
    assert "-4.5" in text


def test_stamina_direction_is_labeled_distinctly_from_fatigue():
    fatigue_text = _render_deviation_block(
        [TTODeviation(3, "velo", -4.5, -1.1, -3.2, "fatigue")]
    )
    stamina_text = _render_deviation_block(
        [TTODeviation(3, "pplus", 6.0, -3.5, 2.1, "stamina")]
    )
    assert "fatigue" in fatigue_text.lower()
    assert "stamina" in stamina_text.lower()
    assert fatigue_text != stamina_text


def test_multiple_deviations_each_get_a_line():
    devs = [
        TTODeviation(2, "velo", -3.0, -0.4, -2.5, "fatigue"),
        TTODeviation(3, "pplus", -8.0, -3.5, -2.4, "fatigue"),
    ]
    text = _render_deviation_block(devs)
    assert text.count("Pass 2") == 1
    assert text.count("Pass 3") == 1


def test_typical_block_does_not_leak_material_language():
    """Sanity: the silence instruction should not accidentally use words
    that would read as material findings (e.g. no residual/z jargon)."""
    text = _render_deviation_block([])
    assert "robust z" not in text.lower()
