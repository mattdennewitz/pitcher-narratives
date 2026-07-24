"""Tests for runtime agent skill loading via pydantic-ai-skills.

The package's bundled SKILL.md files (src/pitcher_narratives/skills/)
are exposed to runtime pydantic-ai agents through a shared
SkillsToolset (progressive disclosure: names+descriptions in
instructions, bodies on demand).
"""

from pydantic_ai_skills import SkillsToolset, discover_skills

from pitcher_narratives.agent_skills import SKILLS_DIR, runtime_skill_names, skill_toolset
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


def test_skill_toolset_excludes_script_and_resource_tools():
    """No skill ships scripts or resources, and a model hallucinating
    run_skill_script('...') raises through the toolset and kills the
    whole pipeline run (observed with DeepSeek). Don't offer the tools."""
    tool_names = set(skill_toolset().tools.keys())
    assert "run_skill_script" not in tool_names
    assert "read_skill_resource" not in tool_names


# ── Audience filtering (runtime vs builder) ───────────────────────────


def test_runtime_skills_include_only_runtime_audience():
    """Runtime-tagged skills load into agents; builder-tagged ones do not."""
    names = set(runtime_skill_names())
    assert "statcast-data-conventions" not in names
    assert "pitching-plus-conventions" in names
    # builder-facing skills must NOT reach runtime narrative agents
    assert "derived-signal-feature" not in names
    assert "pipeline-agent-testing" not in names


def test_runtime_toolset_excludes_builder_skill_body():
    """load_skill on the runtime toolset cannot return a builder skill."""
    from pydantic_ai_skills import discover_skills as _discover

    loaded = {s.name for s in _discover(SKILLS_DIR) if s.name in runtime_skill_names()}
    assert "derived-signal-feature" not in loaded


def test_pitching_plus_skill_exposes_complete_model_boundary_contract():
    skill = next(
        skill for skill in discover_skills(str(SKILLS_DIR)) if skill.name == "pitching-plus-conventions"
    )
    content = " ".join(skill.content.split())
    for required in (
        "13 outcome probabilities",
        "P includes realized plate location",
        "derived acceleration/spin coordinates",
        "P(count | broad pitch class, same_side)",
        "actual count",
        "hidden same-count S",
        "independently centered",
        "pitch-weighted mean",
        "uncapped plus grade minus 50",
        "means of per-pitch ratios",
        "no model-level minimum sample or shrinkage",
        "explicit pitch or player identity",
        "Raw Statcast enters PitchingPlus",
        "Pitcher Narratives reads only that bundle",
        "Agents may interpret only cited facts",
    ):
        assert required in content


def test_grade_explanation_skill_defers_model_definitions_to_ask_surface():
    skill = next(
        skill for skill in discover_skills(str(SKILLS_DIR)) if skill.name == "explaining-pitch-grades"
    )
    content = " ".join(skill.content.split())
    assert "Do not generate model definitions" in content
    assert "ask surface appends the validated, versioned deterministic" in content


# ── Narrative engine wiring ───────────────────────────────────────────


def test_pipeline_prose_agents_have_skill_toolset():
    """Every prose specialist and the writer carry the skills toolset."""
    agents = make_pipeline_agents()
    for name in ("stuff", "location", "runvalue", "trends", "writer"):
        agent = getattr(agents, name)
        assert skill_toolset() in _toolsets(agent), f"{name} missing skills toolset"


def test_pipeline_structured_agents_have_no_skill_toolset():
    """Structured-output agents stay tool-free (skills are prose-only)."""
    agents = make_pipeline_agents()
    for name in ("auditor", "anchor", "signal_extractor"):
        agent = getattr(agents, name)
        assert skill_toolset() not in _toolsets(agent), f"{name} should not carry skills"
