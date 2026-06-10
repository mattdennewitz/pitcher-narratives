"""Tests for runtime agent skill loading.

Covers SKILL.md discovery and frontmatter parsing from .claude/skills/,
the skill catalog rendered into agent instructions, the read_skill tool
contract, and QA agent wiring.
"""

from pitcher_narratives.agent_skills import (
    AgentSkill,
    list_skills,
    read_skill,
    render_skill_catalog,
)
from pitcher_narratives.analyst import _make_qa_agent


# ── Discovery and parsing ─────────────────────────────────────────────


def test_list_skills_finds_project_skills():
    """Skills in .claude/skills/ are discovered by directory name."""
    skills = list_skills()
    assert "statcast-data-conventions" in skills
    assert isinstance(skills["statcast-data-conventions"], AgentSkill)


def test_skill_has_description_from_frontmatter():
    """The description field is parsed out of the YAML frontmatter."""
    skill = list_skills()["statcast-data-conventions"]
    assert skill.description.startswith("Use when")


def test_skill_body_excludes_frontmatter():
    """The body starts at the markdown content, not the YAML block."""
    skill = list_skills()["statcast-data-conventions"]
    assert not skill.body.startswith("---")
    assert "description:" not in skill.body
    assert "# Statcast Data Conventions" in skill.body


# ── Catalog rendering ─────────────────────────────────────────────────


def test_catalog_lists_all_skills():
    """Catalog contains each skill name and its description."""
    catalog = render_skill_catalog()
    assert "statcast-data-conventions" in catalog
    assert "Use when" in catalog


def test_catalog_empty_when_no_skills(tmp_path, monkeypatch):
    """Missing skills directory yields an empty catalog, not an error."""
    import pitcher_narratives.agent_skills as mod

    monkeypatch.setattr(mod, "SKILLS_DIR", tmp_path / "nope")
    mod._skills_cache = None
    try:
        assert render_skill_catalog() == ""
    finally:
        mod._skills_cache = None


# ── read_skill tool contract ──────────────────────────────────────────


def test_read_skill_returns_body():
    """Known skill name returns the skill body."""
    result = read_skill("statcast-data-conventions")
    assert "# Statcast Data Conventions" in result


def test_read_skill_unknown_name_lists_available():
    """Unknown skill returns a helpful message naming valid skills."""
    result = read_skill("not-a-skill")
    assert "statcast-data-conventions" in result
    assert "# " not in result


# ── QA agent wiring ───────────────────────────────────────────────────


def test_qa_agent_has_read_skill_tool():
    """The QA agent registers read_skill alongside its data tools."""
    agent = _make_qa_agent()
    tool_names = set(agent._function_toolset.tools.keys())
    assert "read_skill" in tool_names


def test_qa_agent_instructions_include_catalog():
    """QA agent instructions carry the skill catalog."""
    agent = _make_qa_agent()
    instructions = agent._instructions
    assert "statcast-data-conventions" in str(instructions)
