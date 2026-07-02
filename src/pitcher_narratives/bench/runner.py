"""Per-provider pipeline runs with full output capture.

Runs the existing multi-agent pipeline once per provider and captures
every judgeable text: the five specialist outputs, the executive
summary, and the final capsule -- plus the pitcher context document
(the judge's ground truth) and wall-clock time. PipelineResult already
exposes all per-agent text, so no pipeline changes are needed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.pipeline import (
    _build_game_shape_input,
    _build_location_input,
    _build_runvalue_input,
    _build_stuff_input,
    _build_trend_input,
    _flatten_prompt,
    build_writer_input,
    generate_pipeline_streaming,
)
from pitcher_narratives.temporal import _DEFAULT_RECENT_APPEARANCES

__all__ = ["CapturedRun", "run_provider"]

log = logging.getLogger("pitcher_narratives.bench")


@dataclass
class CapturedRun:
    """Everything captured from one provider's pipeline run."""

    provider: str
    ok: bool
    error: str | None
    wall_s: float
    ground_truth: str
    """The pitcher context document (generic reference)."""

    outputs: dict[str, str] = field(default_factory=dict)
    """tier key ('specialist:stuff', ..., 'capsule') -> text."""

    ground_truths: dict[str, str] = field(default_factory=dict)
    """tier key -> the exact input that tier's author received. Judging
    grounding against anything else marks provided data as 'invented'."""

    pitcher_name: str = ""


def run_provider(
    pitcher_id: int,
    *,
    provider: str,
    thinking: str = "medium",
    persona: str = "scout",
    recent_appearances: int = _DEFAULT_RECENT_APPEARANCES,
    _model_override: object = None,
) -> CapturedRun:
    """Run the full pipeline for one provider and capture all outputs.

    A failed run is returned as ok=False with the error message; the
    bench continues with other providers.
    """
    data = load_pitcher_data(pitcher_id, recent_appearances=recent_appearances)
    ctx = assemble_pitcher_context(data)
    ground_truth = ctx.to_prompt()

    start = time.monotonic()
    try:
        result = generate_pipeline_streaming(
            ctx,
            provider=provider,
            thinking=thinking,  # type: ignore[arg-type]
            persona=persona,
            _model_override=_model_override,
        )
    except Exception as exc:  # noqa: BLE001 -- a provider failure must not kill the bench
        log.error("bench: %s run failed: %s", provider, exc)
        return CapturedRun(
            provider=provider,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            wall_s=time.monotonic() - start,
            ground_truth=ground_truth,
            pitcher_name=data.pitcher_name,
        )

    wall_s = time.monotonic() - start
    outputs = {
        "specialist:stuff": result.specialists.stuff,
        "specialist:location": result.specialists.location,
        "specialist:runvalue": result.specialists.runvalue,
        "specialist:trends": result.specialists.trends,
        "specialist:game_shape": result.specialists.game_shape,
        "capsule": result.narrative,
    }
    if result.executive_summary:
        outputs["exec_summary"] = "\n".join(f"- {b}" for b in result.executive_summary)

    # Per-tier ground truth = the exact input that tier's author saw.
    # Specialist inputs are deterministic functions of ctx; the writer's
    # input is composed from THIS run's specialist outputs + key signals.
    writer_input = build_writer_input(
        ctx,
        result.specialists.stuff,
        result.specialists.location,
        result.specialists.runvalue,
        result.specialists.trends,
        result.specialists.game_shape,
        key_signals=result.key_signals,
    )
    ground_truths = {
        "specialist:stuff": _flatten_prompt(_build_stuff_input(ctx)),
        "specialist:location": _flatten_prompt(_build_location_input(ctx)),
        "specialist:runvalue": _flatten_prompt(_build_runvalue_input(ctx)),
        "specialist:trends": _flatten_prompt(_build_trend_input(ctx)),
        "specialist:game_shape": _flatten_prompt(_build_game_shape_input(ctx)),
        "capsule": writer_input,
        "exec_summary": writer_input,
    }

    return CapturedRun(
        provider=provider,
        ok=True,
        error=None,
        wall_s=wall_s,
        ground_truth=ground_truth,
        outputs=outputs,
        ground_truths=ground_truths,
        pitcher_name=data.pitcher_name,
    )
