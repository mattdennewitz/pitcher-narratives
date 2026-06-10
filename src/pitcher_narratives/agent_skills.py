"""Runtime skill loading for pydantic-ai agents via pydantic-ai-skills.

Exposes the package's bundled SKILL.md files to runtime agents as a
single shared SkillsToolset. The library handles progressive
disclosure: skill names and descriptions are injected into the agent's
instructions, and full bodies load on demand through its load_skill
tool. Skills are application code -- they ship inside the package next
to this module.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai_skills import SkillsToolset

__all__ = ["SKILLS_DIR", "runtime_skill_names", "skill_toolset"]

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
"""Bundled skills directory inside the package (application code)."""

_RUNTIME_AUDIENCE = "runtime"
"""Only skills whose frontmatter declares this audience load into agents."""


def _audience(skill_md: Path) -> str:
    """Read the `audience` frontmatter field; default 'builder' (not runtime).

    Defaulting to builder means a skill must explicitly opt in to being
    loaded into runtime agents, so a new builder/dev skill never leaks
    into the narrative agents by accident.
    """
    text = skill_md.read_text()
    if not text.startswith("---"):
        return "builder"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "builder"
    for line in parts[1].splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "audience":
            return value.strip().lower()
    return "builder"


def _runtime_skill_dirs() -> list[str]:
    """Directories of skills tagged `audience: runtime`."""
    if not SKILLS_DIR.is_dir():
        return []
    return [
        str(skill_md.parent)
        for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md"))
        if _audience(skill_md) == _RUNTIME_AUDIENCE
    ]


def runtime_skill_names() -> list[str]:
    """Names of the skills that load into runtime agents."""
    return [Path(d).name for d in _runtime_skill_dirs()]


_skill_toolset: SkillsToolset | None = None


def skill_toolset() -> SkillsToolset:
    """Return the shared SkillsToolset over the runtime-audience skills.

    Cached so every agent shares one discovery/registry instance.
    Builder-facing skills (e.g. dev recipes) are excluded so narrative
    agents only see runtime-relevant reference material. An empty
    toolset is returned when no runtime skills exist, so agent
    construction never fails.
    """
    global _skill_toolset
    if _skill_toolset is None:
        _skill_toolset = SkillsToolset(directories=_runtime_skill_dirs())
    return _skill_toolset
