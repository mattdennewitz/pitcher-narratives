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

from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.personas import REPORT, NarrationMode
from pitcher_narratives.pipeline import (
    _build_game_shape_input,
    _build_location_input,
    _build_runvalue_input,
    _build_stuff_input,
    _build_trend_input,
    _flatten_prompt,
    build_writer_input,
    run_narration_modes,
)
from pitcher_narratives.temporal import (
    _DEFAULT_PRIOR_APPEARANCES,
    _DEFAULT_RECENT_APPEARANCES,
    TemporalFrame,
)

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
    """tier key ('specialist:stuff', ..., 'capsule:<mode>') -> text."""

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
    modes: list[NarrationMode] | None = None,
    prior: int = _DEFAULT_PRIOR_APPEARANCES,
    _model_override: object = None,
) -> CapturedRun:
    """Run the full pipeline for one provider and capture all outputs.

    Runs every requested narration mode via the production dispatcher
    ``run_narration_modes``. The five specialist tiers are mode-agnostic
    by construction (the spine re-runs per mode but its specialist inputs
    do not depend on the mode) and are captured once from the first
    mode's result; the capsule and executive summary are captured per
    mode under namespaced keys (``capsule:<mode.id>``, ``exec_summary:<mode.id>``).

    A failed run is returned as ok=False with the error message; the
    bench continues with other providers.
    """
    selected_modes = modes if modes is not None else [REPORT]
    data = load_pitcher_data(pitcher_id, recent_appearances=recent_appearances)
    ctx = assemble_pitcher_context(data)
    ground_truth = ctx.to_prompt()

    prior_ctx = None
    if any(TemporalFrame.PRIOR in m.temporal_frame for m in selected_modes):
        prior_ctx = assemble_prior_context(data, recent_appearances, prior)

    start = time.monotonic()
    try:
        results = run_narration_modes(
            ctx,
            modes=selected_modes,
            provider=provider,
            thinking=thinking,  # type: ignore[arg-type]
            persona=persona,
            _model_override=_model_override,
            prior_ctx=prior_ctx,
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

    # Specialist tiers are mode-agnostic; capture them once from the first
    # result. Their ground truths are deterministic functions of ctx.
    first = next(iter(results.values()))
    outputs = {
        "specialist:stuff": first.specialists.stuff,
        "specialist:location": first.specialists.location,
        "specialist:runvalue": first.specialists.runvalue,
        "specialist:trends": first.specialists.trends,
        "specialist:game_shape": first.specialists.game_shape,
    }
    ground_truths = {
        "specialist:stuff": _flatten_prompt(_build_stuff_input(ctx)),
        "specialist:location": _flatten_prompt(_build_location_input(ctx)),
        "specialist:runvalue": _flatten_prompt(_build_runvalue_input(ctx)),
        "specialist:trends": _flatten_prompt(_build_trend_input(ctx)),
        "specialist:game_shape": _flatten_prompt(_build_game_shape_input(ctx)),
    }

    # Per-mode capsule + exec summary. The writer-input ground truth is
    # rebuilt from THAT mode's specialists + key signals.
    for mode_id, result in results.items():
        writer_input = build_writer_input(
            ctx,
            result.specialists.stuff,
            result.specialists.location,
            result.specialists.runvalue,
            result.specialists.trends,
            result.specialists.game_shape,
            key_signals=result.key_signals,
        )
        outputs[f"capsule:{mode_id}"] = result.narrative
        ground_truths[f"capsule:{mode_id}"] = writer_input
        if result.executive_summary:
            outputs[f"exec_summary:{mode_id}"] = "\n".join(
                f"- {b}" for b in result.executive_summary
            )
            ground_truths[f"exec_summary:{mode_id}"] = writer_input

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
