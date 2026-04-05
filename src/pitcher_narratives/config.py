"""Shared configuration: provider map, model settings factory, and CLI helpers.

Centralises constants and utilities that were previously scattered across
report.py, pipeline.py, analyst.py, and the CLI modules.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.settings import ModelSettings, ThinkingEffort

__all__ = [
    "API_KEYS",
    "MAX_REVISIONS",
    "MINI_PROVIDERS",
    "PROVIDERS",
    "THINKING_LEVELS",
    "agent_kwargs",
    "make_model_settings",
    "setup_logging",
]

PROVIDERS = {
    "openai": "openai:gpt-5.4-mini",
    "claude": "anthropic:claude-sonnet-4-6",
    "gemini": "google-gla:gemini-3.1-pro-preview",
}

MINI_PROVIDERS = {
    "openai": "openai:gpt-5.4-mini",
    "claude": "anthropic:claude-haiku-4-5",
    "gemini": "google-gla:gemini-3.1-flash",
}

THINKING_LEVELS: list[ThinkingEffort] = ["minimal", "low", "medium", "high", "xhigh"]

MAX_REVISIONS = 2
"""Maximum number of editor revision passes before accepting the capsule."""

API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def make_model_settings(
    provider: str,
    thinking: ThinkingEffort,
    temperature: float,
    *,
    max_tokens: int = 16384,
) -> ModelSettings:
    """Build provider-aware ModelSettings with thinking-effort translation.

    Gemini uses a discrete ``thinking_level`` instead of the continuous
    ``ThinkingEffort`` enum, so we map high/xhigh → ``"high"`` and
    everything else → ``"low"``.
    """
    if provider == "gemini":
        gemini_level = "high" if thinking in ("high", "xhigh") else "low"
        return GoogleModelSettings(
            google_thinking_config={"thinking_level": gemini_level},
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "claude":
        return ModelSettings(thinking=thinking, temperature=temperature, max_tokens=max_tokens)
    else:
        return ModelSettings(thinking=thinking, temperature=temperature)


def agent_kwargs(prompt: Any, model_override: Any = None) -> dict[str, Any]:
    """Build kwargs for an ``agent.run()`` call, optionally injecting a model override."""
    kwargs: dict[str, Any] = {"user_prompt": prompt}
    if model_override is not None:
        kwargs["model"] = model_override
    return kwargs


def setup_logging() -> None:
    """Configure logging for pitcher_narratives to stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root = logging.getLogger("pitcher_narratives")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
