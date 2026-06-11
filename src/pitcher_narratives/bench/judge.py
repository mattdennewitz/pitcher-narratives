"""LLM judge: scores one output against a rubric with structured output.

Panel logic lives here: by default every configured provider judges
every output EXCEPT its own author (cancels self-preference bias). With
two providers this degenerates to cross-judging; with one provider the
author judges itself (stated in the report).
"""

from __future__ import annotations

import logging

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from pitcher_narratives.bench.rubric import (
    JudgedOutput,
    RubricDimension,
    build_judge_prompt,
)
from pitcher_narratives.config import PROVIDERS

__all__ = ["judge_text", "judges_for", "make_judge_agent"]

log = logging.getLogger("pitcher_narratives.bench")

_JUDGE_MAX_TOKENS = 4096
_JUDGE_TEMPERATURE = 0.2
"""Low temperature, no extended thinking: judging should be near-deterministic."""


def judges_for(author: str, providers: list[str], judge_mode: str) -> list[str]:
    """Select which providers judge an output authored by `author`.

    judge_mode 'panel': every provider except the author; falls back to
    the author itself when it is the only provider. Any other value
    names a single fixed judge.
    """
    if judge_mode != "panel":
        return [judge_mode]
    panel = [p for p in providers if p != author]
    return panel if panel else [author]


def make_judge_agent(provider: str, rubric: list[RubricDimension]) -> Agent[None, JudgedOutput]:
    """Build a structured-output judge agent for the given provider."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown judge provider {provider!r}; expected one of {', '.join(PROVIDERS)}")
    settings = ModelSettings(temperature=_JUDGE_TEMPERATURE, max_tokens=_JUDGE_MAX_TOKENS)
    return Agent(
        PROVIDERS[provider],
        output_type=JudgedOutput,
        system_prompt=build_judge_prompt(rubric),
        model_settings=settings,
        retries=3,
        defer_model_check=True,
    )


def judge_text(
    *,
    ground_truth: str,
    output_text: str,
    tier_label: str,
    rubric: list[RubricDimension],
    judge_provider: str,
    _model_override: object = None,
) -> JudgedOutput:
    """Score one output against the rubric with one judge.

    Args:
        ground_truth: The pitcher context document the output was based on.
        output_text: The text under evaluation.
        tier_label: Human label for what is being judged (e.g. 'capsule').
        rubric: AGENT_RUBRIC or CAPSULE_RUBRIC.
        judge_provider: Provider key for the judge model.
        _model_override: Test-only model override.
    """
    agent = make_judge_agent(judge_provider, rubric)
    user_msg = (
        f"TIER: {tier_label}\n\n"
        f"=== GROUND TRUTH (the data the output was written from) ===\n"
        f"{ground_truth}\n\n"
        f"=== OUTPUT UNDER EVALUATION ===\n"
        f"{output_text}"
    )
    kwargs: dict = {"user_prompt": user_msg}
    if _model_override is not None:
        kwargs["model"] = _model_override
    return agent.run_sync(**kwargs).output
