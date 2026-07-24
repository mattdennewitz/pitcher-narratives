"""Deterministic parsing of grade-explanation questions (no LLM, real resolver)."""

import pytest

from pitcher_narratives.qa import QuestionError, parse_grade_question


def test_parses_jones_fastball_stuff():
    q = parse_grade_question("why does Jared Jones's fastball grade 92 stuff+")
    assert q.pitcher_id == 683003
    assert q.grade_family == "S"
    assert q.pitch_candidates == ["FF", "SI"]  # "fastball" is ambiguous; reconciled later
    assert q.cited_value == 92.0


def test_grade_family_location_and_pitching():
    assert parse_grade_question("Jared Jones slider location+").grade_family == "L"
    assert parse_grade_question("Jared Jones curveball pitching+").grade_family == "P"


def test_command_is_not_a_location_grade_alias():
    with pytest.raises(QuestionError, match="target"):
        parse_grade_question("why is Jared Jones slider command poor")


def test_grade_family_defaults_to_stuff():
    assert parse_grade_question("Jared Jones changeup").grade_family == "S"


def test_specific_pitch_beats_generic():
    # "four-seam" must win over the substring "fastball" logic and map to FF only.
    assert parse_grade_question("Jared Jones four-seam stuff+").pitch_candidates == ["FF"]


def test_unknown_pitcher_raises():
    with pytest.raises(QuestionError, match="pitcher"):
        parse_grade_question("why does the fastball grade 92 stuff+")


def test_no_pitch_raises():
    with pytest.raises(QuestionError, match="pitch"):
        parse_grade_question("how good is Jared Jones")
