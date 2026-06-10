"""Tests for runtime agent skill loading via pydantic-ai-skills.

The package's bundled SKILL.md files (src/pitcher_narratives/skills/)
are exposed to runtime pydantic-ai agents through a shared
SkillsToolset (progressive disclosure: names+descriptions in
instructions, bodies on demand).
"""

from pydantic_ai_skills import SkillsToolset, discover_skills

from pitcher_narratives.agent_skills import SKILLS_DIR, skill_toolset
from pitcher_narratives.analyst import _make_qa_agent
from pitcher_narratives.pipeline import make_pipeline_agents


def _toolsets(agent) -> list:
    """All toolsets attached to an agent (pydantic-ai private accessor)."""
    return list(getattr(agent, "_user_toolsets", []))


# ── Discovery ─────────────────────────────────────────────────────────


def test_repo_skills_are_discovered():
    """The project's two committed skills are found under the package skills dir."""
    names = {s.name for s in discover_skills(str(SKILLS_DIR))}
    assert "statcast-data-conventions" in names
    assert "derived-signal-feature" in names


def test_skill_toolset_is_skillstoolset():
    """The shared toolset is the library's SkillsToolset."""
    assert isinstance(skill_toolset(), SkillsToolset)


def test_skill_toolset_is_shared_singleton():
    """One registry instance is reused across all agents."""
    assert skill_toolset() is skill_toolset()


def test_skill_toolset_exposes_load_skill():
    """The library's load_skill tool is present on the toolset."""
    tool_names = set(skill_toolset().tools.keys())
    assert "load_skill" in tool_names
    assert "list_skills" in tool_names


# ── QA agent wiring ───────────────────────────────────────────────────


def test_qa_agent_has_skill_toolset():
    """The Q&A agent carries the shared skills toolset."""
    agent = _make_qa_agent()
    assert skill_toolset() in _toolsets(agent)


# ── Narrative engine wiring ───────────────────────────────────────────


def test_pipeline_prose_agents_have_skill_toolset():
    """Every prose specialist and the writer carry the skills toolset."""
    agents = make_pipeline_agents()
    for name in ("stuff", "location", "runvalue", "trends", "game_shape", "writer"):
        agent = getattr(agents, name)
        assert skill_toolset() in _toolsets(agent), f"{name} missing skills toolset"


def test_pipeline_structured_agents_have_no_skill_toolset():
    """Structured-output agents stay tool-free (skills are prose-only)."""
    agents = make_pipeline_agents()
    for name in ("auditor", "anchor", "signal_extractor"):
        agent = getattr(agents, name)
        assert skill_toolset() not in _toolsets(agent), f"{name} should not carry skills"
