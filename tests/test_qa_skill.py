"""The grade-explanation skill loads into runtime agents."""

from pitcher_narratives.agent_skills import SKILLS_DIR, runtime_skill_names


def test_explaining_pitch_grades_is_runtime_skill():
    assert "explaining-pitch-grades" in runtime_skill_names()


def test_grade_skills_preserve_evidence_capability_boundaries():
    content = " ".join(
        "\n".join(
            (SKILLS_DIR / name / "SKILL.md").read_text()
            for name in ("explaining-pitch-grades", "pitching-plus-conventions")
        ).split()
    )

    assert "The supplied aggregate profile does not identify the model driver." in content
    assert "feature attribution" in content
    assert "cited fact" in content
    assert "release traits" in content
    assert "count processing" in content
    assert "raw stuff only" not in content
    assert "tunneling story" not in content
    assert "xWhiff_S ≥ 25%" not in content
    assert "movement and deception" not in content
