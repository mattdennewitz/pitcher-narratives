"""Per-provider pipeline runs with full output capture.

Runs every requested narration mode for one provider via the production
dispatcher ``run_narration_modes`` and captures every judgeable text:
the specialist outputs, and per mode the executive summary and final
capsule under namespaced keys -- plus the pitcher context document (the
judge's generic ground truth) and wall-clock time. Each tier carries
the exact author input as its per-tier ground truth.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.frame_delta import (
    build_trend_frame_comparison,
    render_trend_frame_comparison,
)
from pitcher_narratives.personas import REPORT, NarrationMode
from pitcher_narratives.pipeline import (
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
    """tier key ('specialist:stuff', 'specialist:trends:<mode>', ...,
    'capsule:<mode>') -> text."""

    ground_truths: dict[str, str] = field(default_factory=dict)
    """tier key -> the exact input that tier's author received. Judging
    grounding against anything else marks provided data as 'invented'."""

    pitcher_name: str = ""


def run_provider(
    pitcher_id: int,
    *,
    provider: str,
    thinking: str = "medium",
    recent_appearances: int = _DEFAULT_RECENT_APPEARANCES,
    modes: list[NarrationMode] | None = None,
    prior: int = _DEFAULT_PRIOR_APPEARANCES,
    _model_override: object = None,
) -> CapturedRun:
    """Run the full pipeline for one provider and capture all outputs.

    Runs every requested narration mode via the production dispatcher
    ``run_narration_modes``. Three specialist tiers (stuff, location,
    runvalue) are mode-agnostic by construction — their
    inputs do not depend on the mode — and are captured once from the
    first mode's result. The TRENDS specialist is captured per mode
    (``specialist:trends:<mode.id>``) because CHANGES feeds it a prior-vs-
    recent frame comparison the other modes do not, so its ground truth
    differs by mode. The capsule and executive summary are captured per
    mode (``capsule:<mode.id>``, ``exec_summary:<mode.id>``).

    A failed run is returned as ok=False with the error message; the
    bench continues with other providers.
    """
    selected_modes = modes if modes is not None else [REPORT]
    data = load_pitcher_data(pitcher_id, recent_appearances=recent_appearances)
    ctx = assemble_pitcher_context(data)
    ground_truth = ctx.to_prompt()
    mode_by_id = {m.id: m for m in selected_modes}

    start = time.monotonic()
    try:
        # Prior-window assembly can raise on pitchers with too few
        # appearances to form a prior frame; keep it inside the try so a
        # failure is captured as ok=False rather than aborting the bench.
        prior_ctx = None
        if any(TemporalFrame.PRIOR in m.temporal_frame for m in selected_modes):
            prior_ctx = assemble_prior_context(data, recent_appearances, prior)

        results = run_narration_modes(
            ctx,
            modes=selected_modes,
            provider=provider,
            thinking=thinking,  # type: ignore[arg-type]
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

    # Three specialist tiers are mode-agnostic (their inputs don't depend
    # on the mode); capture them once from the first result. Their ground
    # truths are deterministic functions of ctx.
    first = next(iter(results.values()))
    outputs = {
        "specialist:stuff": first.specialists.stuff,
        "specialist:location": first.specialists.location,
        "specialist:runvalue": first.specialists.runvalue,
    }
    ground_truths = {
        "specialist:stuff": _flatten_prompt(_build_stuff_input(ctx)),
        "specialist:location": _flatten_prompt(_build_location_input(ctx)),
        "specialist:runvalue": _flatten_prompt(_build_runvalue_input(ctx)),
    }

    # The TRENDS specialist differs by mode: CHANGES feeds it a prior-vs-
    # recent frame comparison. Capture it per mode with the matching
    # ground truth (mirroring run_narration_modes' PRIOR gating and the
    # spine's frame-comparison derivation).
    for mode_id, result in results.items():
        mode_prior = (
            prior_ctx
            if TemporalFrame.PRIOR in mode_by_id[mode_id].temporal_frame
            else None
        )
        frame_comparison = (
            render_trend_frame_comparison(build_trend_frame_comparison(ctx, mode_prior))
            if mode_prior is not None
            else None
        )
        outputs[f"specialist:trends:{mode_id}"] = result.specialists.trends
        ground_truths[f"specialist:trends:{mode_id}"] = _flatten_prompt(
            _build_trend_input(ctx, frame_comparison=frame_comparison)
        )

    # Per-mode capsule + exec summary. The writer-input ground truth is
    # rebuilt from THAT mode's specialists + key signals.
    for mode_id, result in results.items():
        writer_input = build_writer_input(
            ctx,
            result.specialists.stuff,
            result.specialists.location,
            result.specialists.runvalue,
            result.specialists.trends,
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
