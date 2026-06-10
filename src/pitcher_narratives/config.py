"""Shared configuration: provider map, model settings factory, and CLI helpers.

Centralises constants and utilities shared by pipeline.py, analyst.py,
and the CLI modules.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import logfire

from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.settings import ModelSettings, ThinkingEffort

__all__ = [
    "API_KEYS",
    "MAX_REVISIONS",
    "MINI_PROVIDERS",
    "PROVIDERS",
    "THINKING_LEVELS",
    "TOKEN_BUDGET_LARGE",
    "TOKEN_BUDGET_MEDIUM",
    "TOKEN_BUDGET_SMALL",
    "agent_kwargs",
    "cap_thinking",
    "make_model_settings",
    "setup_logging",
]

PROVIDERS = {
    "claude": "anthropic:claude-sonnet-4-6",
    "gemini": "google-gla:gemini-3.1-pro-preview",
}

MINI_PROVIDERS = {
    "claude": "anthropic:claude-haiku-4-5",
    "gemini": "google-gla:gemini-flash-latest",
}

THINKING_LEVELS: list[ThinkingEffort] = ["minimal", "low", "medium", "high", "xhigh"]

TOKEN_BUDGET_SMALL = 1024
"""Anchor, auditor, executive summary -- short structured output."""

TOKEN_BUDGET_MEDIUM = 2048
"""Specialist builders -- moderate analytical output."""

TOKEN_BUDGET_LARGE = 4096
"""Writer, editor, answerer, stuff explainer -- long-form prose."""

MAX_REVISIONS = 3
"""Maximum number of editor revision passes before accepting the capsule."""

API_KEYS = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def make_model_settings(
    provider: str,
    thinking: ThinkingEffort,
    temperature: float,
    *,
    max_tokens: int = 16384,
    mini: bool = False,
) -> ModelSettings:
    """Build provider-aware ModelSettings with thinking-effort translation.

    Args:
        mini: True when targeting a mini-tier model. Disables thinking for
              providers where mini models don't support it (Claude).
    """
    if provider == "gemini":
        gemini_level = "high" if thinking in ("high", "xhigh") else "low"
        return GoogleModelSettings(
            google_thinking_config={"thinking_level": gemini_level},
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "claude":
        # Claude: disable thinking for small budgets (thinking.budget_tokens
        # would exceed max_tokens) and for mini models (Haiku).
        if mini or max_tokens <= TOKEN_BUDGET_MEDIUM:
            return ModelSettings(temperature=1, max_tokens=max_tokens)
        return ModelSettings(thinking=thinking, temperature=1, max_tokens=max_tokens)
    raise ValueError(f"Unknown provider {provider!r}; expected 'gemini' or 'claude'")


def cap_thinking(thinking: ThinkingEffort, ceiling: ThinkingEffort) -> ThinkingEffort:
    """Clamp thinking effort to the lower of the given level and the ceiling.

    Uses THINKING_LEVELS index ordering: minimal < low < medium < high < xhigh.
    """
    return thinking if THINKING_LEVELS.index(thinking) <= THINKING_LEVELS.index(ceiling) else ceiling


def agent_kwargs(prompt: Any, model_override: Any = None) -> dict[str, Any]:
    """Build kwargs for an ``agent.run()`` call, optionally injecting a model override."""
    kwargs: dict[str, Any] = {"user_prompt": prompt}
    if model_override is not None:
        kwargs["model"] = model_override
    return kwargs


def setup_logging() -> None:
    """Configure logging and Logfire instrumentation for pitcher_narratives."""
    logfire.configure()
    logfire.instrument_pydantic_ai()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root = logging.getLogger("pitcher_narratives")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
