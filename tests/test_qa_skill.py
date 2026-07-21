"""The grade-explanation skill loads into runtime agents."""

from pitcher_narratives.agent_skills import runtime_skill_names


def test_explaining_pitch_grades_is_runtime_skill():
    assert "explaining-pitch-grades" in runtime_skill_names()
