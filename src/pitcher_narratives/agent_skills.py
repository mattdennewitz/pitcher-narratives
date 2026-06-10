"""Runtime skill loading for pydantic-ai agents via pydantic-ai-skills.

Exposes the repo's .claude/skills/ SKILL.md files to runtime agents as
a single shared SkillsToolset. The library handles progressive
disclosure: skill names and descriptions are injected into the agent's
instructions, and full bodies load on demand through its load_skill
tool. These are the same SKILL.md files Claude Code reads during
development -- authored once, consumed by both.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai_skills import SkillsToolset

__all__ = ["SKILLS_DIR", "skill_toolset"]

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "skills"
"""Repo-root .claude/skills/ -- the same files Claude Code discovers."""

_skill_toolset: SkillsToolset | None = None


def skill_toolset() -> SkillsToolset:
    """Return the shared SkillsToolset over the repo's .claude/skills/.

    Cached so every agent shares one discovery/registry instance. When
    the directory is absent (e.g. installed without the repo tree), an
    empty toolset is returned so agent construction never fails.
    """
    global _skill_toolset
    if _skill_toolset is None:
        directories = [str(SKILLS_DIR)] if SKILLS_DIR.is_dir() else []
        _skill_toolset = SkillsToolset(directories=directories)
    return _skill_toolset
