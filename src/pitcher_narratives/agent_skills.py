"""Runtime skill loading for pydantic-ai agents.

Discovers SKILL.md files under the repo's .claude/skills/ directory and
exposes them to runtime agents the same way Claude Code exposes them to
development sessions: a lightweight catalog (name + description) goes
into agent instructions, and the full body loads on demand via the
read_skill tool. Skills are authored once and consumed by both.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "AgentSkill",
    "SKILLS_DIR",
    "list_skills",
    "read_skill",
    "render_skill_catalog",
]

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "skills"
"""Repo-root .claude/skills/ — same files Claude Code discovers."""


@dataclass
class AgentSkill:
    """One loadable skill: catalog metadata plus full markdown body."""

    name: str
    description: str
    body: str


def _parse_skill_md(text: str, fallback_name: str) -> AgentSkill:
    """Split YAML frontmatter from body and extract name/description.

    Parses the two known frontmatter keys with plain string handling --
    skills are first-party files, so a YAML dependency is unwarranted.
    """
    name = fallback_name
    description = ""
    body = text

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            frontmatter, body = parts[1], parts[2]
            for line in frontmatter.splitlines():
                key, _, value = line.partition(":")
                if key.strip() == "name":
                    name = value.strip()
                elif key.strip() == "description":
                    description = value.strip()

    return AgentSkill(name=name, description=description, body=body.strip())


_skills_cache: dict[str, AgentSkill] | None = None


def list_skills() -> dict[str, AgentSkill]:
    """Discover and parse all skills under SKILLS_DIR. Cached after first call.

    Returns:
        Dict keyed by skill name. Empty when the directory is missing.
    """
    global _skills_cache
    if _skills_cache is not None:
        return _skills_cache

    skills: dict[str, AgentSkill] = {}
    if SKILLS_DIR.is_dir():
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            skill = _parse_skill_md(skill_file.read_text(), skill_file.parent.name)
            skills[skill.name] = skill

    _skills_cache = skills
    return skills


def render_skill_catalog() -> str:
    """Render the catalog block appended to agent instructions.

    Empty string when no skills exist so callers can skip the section.
    """
    skills = list_skills()
    if not skills:
        return ""

    lines = ["AVAILABLE SKILLS (load with the read_skill tool):"]
    for skill in skills.values():
        lines.append(f"- {skill.name}: {skill.description}")
    lines.append(
        "Before answering questions that depend on data conventions "
        "(movement units, sign conventions, arm angle coverage), read "
        "the relevant skill first and apply it."
    )
    return "\n".join(lines)


def read_skill(skill_name: str) -> str:
    """Return the full body of a skill by name.

    Registered as a pydantic-ai tool on runtime agents. Unknown names
    return a corrective message listing valid skills (LLM-friendly --
    no exception, the model should retry with a valid name).

    Args:
        skill_name: Skill name as shown in the instructions catalog.
    """
    skills = list_skills()
    skill = skills.get(skill_name)
    if skill is None:
        available = ", ".join(skills.keys()) or "(none)"
        return f"Unknown skill {skill_name!r}. Available skills: {available}"
    return skill.body
