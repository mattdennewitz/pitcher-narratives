"""LLM judge: scores one output against a rubric with structured output.

The default judge is a NON-CONTESTANT model (DeepSeek v4 Pro via
OpenRouter, high reasoning effort), which eliminates self-preference
bias entirely. 'panel' mode remains available: every contestant judges
every output except its own author.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModelSettings
from pydantic_ai.output import PromptedOutput
from pydantic_ai.settings import ModelSettings

from pitcher_narratives.bench.rubric import (
    JudgedOutput,
    RubricDimension,
    build_judge_prompt,
)
from pitcher_narratives.config import PROVIDERS

__all__ = ["JUDGE_MODELS", "judge_text", "judges_for", "make_judge_agent", "with_retry"]

log = logging.getLogger("pitcher_narratives.bench")

JUDGE_MODELS = {
    "deepseek": "openrouter:deepseek/deepseek-v4-pro",
}
"""Judge-only model keys usable with --judges (requires
OPENROUTER_API_KEY). Contestant providers (PROVIDERS keys) are also
valid judges -- prefer one that is not in the run's contestant list."""

_JUDGE_MAX_TOKENS = 16384
_JUDGE_TEMPERATURE = 0.2
"""Low temperature: judging should be near-deterministic."""

_T = TypeVar("_T")

_JUDGE_BACKOFFS = (10.0, 30.0, 60.0)
"""Seconds between judge retry attempts -- sequential high-effort calls
trip provider rate limits, which clear on their own."""


def with_retry(
    fn: Callable[[], _T],
    *,
    attempts: int = 4,
    backoffs: tuple[float, ...] = _JUDGE_BACKOFFS,
    _sleep: Callable[[float], None] = time.sleep,
) -> _T:
    """Call fn, retrying with backoff on any exception; re-raise the last."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                delay = backoffs[min(i, len(backoffs) - 1)]
                log.warning("judge attempt %d failed (%s); retrying in %.0fs", i + 1, type(exc).__name__, delay)
                _sleep(delay)
    assert last is not None
    raise last


def judges_for(author: str, providers: list[str], judge_mode: str) -> list[str]:
    """Select which judges score an output authored by `author`.

    judge_mode 'panel': every provider except the author; falls back to
    the author itself when it is the only provider. Any other value
    names a single fixed judge (a contestant or a JUDGE_MODELS key).
    """
    if judge_mode != "panel":
        return [judge_mode]
    panel = [p for p in providers if p != author]
    return panel if panel else [author]


def make_judge_agent(judge: str, rubric: list[RubricDimension]) -> Agent[None, JudgedOutput]:
    """Build a structured-output judge agent.

    `judge` is either a JUDGE_MODELS key (non-contestant, preferred) or
    a contestant provider key from PROVIDERS.
    """
    output_type: object = JudgedOutput
    if judge in JUDGE_MODELS:
        model = JUDGE_MODELS[judge]
        if model.startswith("openrouter:"):
            settings: ModelSettings = OpenRouterModelSettings(
                temperature=_JUDGE_TEMPERATURE,
                max_tokens=_JUDGE_MAX_TOKENS,
                openrouter_reasoning={"effort": "high"},
            )
            # Reasoning models on OpenRouter emit the result as JSON text
            # rather than reliably calling an output tool; PromptedOutput
            # puts the schema in the prompt and parses the JSON response.
            output_type = PromptedOutput(JudgedOutput)
        else:
            settings = ModelSettings(temperature=_JUDGE_TEMPERATURE, max_tokens=_JUDGE_MAX_TOKENS)
    elif judge in PROVIDERS:
        model = PROVIDERS[judge]
        settings = ModelSettings(temperature=_JUDGE_TEMPERATURE, max_tokens=_JUDGE_MAX_TOKENS)
    else:
        valid = ", ".join([*JUDGE_MODELS, *PROVIDERS])
        raise ValueError(f"Unknown judge {judge!r}; expected one of {valid}")
    return Agent(
        model,
        output_type=output_type,
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
