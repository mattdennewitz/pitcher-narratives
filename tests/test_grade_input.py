"""build_grade_input reuses the spine's specialist inputs and surfaces the
grade + S+ class baseline the ask agent anchors to."""

import pytest

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.pipeline import build_grade_input


@pytest.fixture(scope="module")
def jones_ctx():
    return assemble_pitcher_context(load_pitcher_data(683003))  # Jones, Jared


def _text(parts):
    return "\n".join(p for p in parts if isinstance(p, str))


def test_stuff_input_contains_ff_grade_and_class_baseline(jones_ctx):
    text = _text(build_grade_input(jones_ctx, "S"))
    assert "FF" in text
    assert "S+" in text                 # per-pitch grade present
    assert "S-variant league avg" in text  # class baseline (avg_s_plus) present


def test_pitching_input_includes_both_stuff_and_location(jones_ctx):
    text = _text(build_grade_input(jones_ctx, "P"))
    assert "Arsenal Physical Profile" in text          # from stuff input
    assert "Location" in text or "location" in text     # from location input


def test_unknown_family_raises(jones_ctx):
    with pytest.raises(ValueError, match="family"):
        build_grade_input(jones_ctx, "X")
