"""PitcherContext assembly for LLM prompt generation.

Assembles all engine outputs into a single Pydantic model with a
to_prompt() method that renders prompt-ready markdown under 2,000 tokens.
"""

from __future__ import annotations

import dataclasses

from pydantic import BaseModel, ConfigDict

from pitcher_narratives.data import PitcherData, filter_to_prior_appearances
from pitcher_narratives.engine import (
    ArsenalTrends,
    ComponentAttribution,
    CrossSeasonSummary,
    ExecutionMetrics,
    FastballSummary,
    FirstPitchWeaponry,
    HardHitRate,
    IntermediateProbabilities,
    _most_recent_row,
    PitchTypeSummary,
    PlatoonMix,
    ReleasePointMetrics,
    TemporalContext,
    VelocityArc,
    WorkloadContext,
    compute_arsenal_summary,
    compute_arsenal_trends,
    compute_component_attribution,
    compute_cross_season_summary,
    compute_execution_metrics,
    compute_fastball_summary,
    compute_first_pitch_weaponry,
    compute_hard_hit_rate,
    compute_intermediate_probabilities,
    compute_platoon_mix,
    compute_release_point_metrics,
    compute_temporal_context,
    compute_velocity_arc,
    compute_workload_context,
)
from pitcher_narratives.shape import (
    PitchShapeProfile,
    compute_pitch_shape,
)
from pitcher_narratives.temporal import TemporalFrame

__all__ = [
    "MultiFrameContext",
    "PitcherContext",
    "assemble_multi_frame_context",
    "assemble_pitcher_context",
    "assemble_prior_context",
]

_MAX_PITCH_TYPES = 4
"""Token budget: keep top 4 pitch types only in arsenal and execution tables."""


class PitcherContext(BaseModel):
    """Complete context document for LLM prompt generation.

    Assembles all engine outputs (fastball, arsenal, execution, workload)
    into one Pydantic model with a to_prompt() method.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pitcher_name: str
    pitcher_id: int
    throws: str
    role: str
    """Most recent appearance role: 'SP' or 'RP'."""

    fastball: FastballSummary | None
    velocity_arc: VelocityArc | None
    arsenal: list[PitchTypeSummary]
    platoon_mix: PlatoonMix
    first_pitch: FirstPitchWeaponry
    execution: list[ExecutionMetrics]
    intermediates: list[IntermediateProbabilities]
    """Per-pitch-type intermediate probabilities (P and S variants)."""
    attributions: list[ComponentAttribution]
    """Per-pitch-type xRV decomposition into 13 outcome contributions."""
    hard_hit_rate: HardHitRate
    release_point: ReleasePointMetrics
    workload: WorkloadContext
    temporal: TemporalContext

    cross_season_summary: CrossSeasonSummary | None = None
    """Year-over-year pitcher-level metric deltas (velocity, P+, S+, L+)."""

    arsenal_trend: ArsenalTrends | None = None
    """Year-over-year per-pitch-type arsenal changes (added/dropped/continued)."""

    pitch_shape: PitchShapeProfile | None = None
    """Movement vs arm-slot expectation (dead zone / deceptive shape traits)."""

    def to_prompt(self) -> str:
        """Render as prompt-ready markdown under 2,000 tokens.

        Delegates to prompt_builder; imported lazily to avoid a circular
        import (prompt_builder imports PitcherContext from this module).
        """
        from pitcher_narratives.prompt_builder import build_pitcher_prompt

        return build_pitcher_prompt(self)


def assemble_pitcher_context(data: PitcherData) -> PitcherContext:
    """Orchestrate all engine compute functions into a PitcherContext.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        PitcherContext with all sections populated, ready for to_prompt().
    """
    fastball = compute_fastball_summary(data)
    velocity_arc = compute_velocity_arc(data, fastball.pitch_type) if fastball else None
    arsenal = compute_arsenal_summary(data)[:_MAX_PITCH_TYPES]
    platoon_mix = compute_platoon_mix(data)
    first_pitch = compute_first_pitch_weaponry(data)
    execution = compute_execution_metrics(data)[:_MAX_PITCH_TYPES]
    intermediates = compute_intermediate_probabilities(data)[:_MAX_PITCH_TYPES]
    attributions = compute_component_attribution(data)[:_MAX_PITCH_TYPES]
    hard_hit_rate = compute_hard_hit_rate(data)
    release_point = compute_release_point_metrics(data)
    workload = compute_workload_context(data)
    temporal = compute_temporal_context(data, workload)
    cross_season_summary = compute_cross_season_summary(data)
    arsenal_trend = compute_arsenal_trends(data)
    pitch_shape = compute_pitch_shape(data)

    # Determine role from most recent appearance (deterministic tiebreak)
    most_recent = _most_recent_row(data.appearances)
    role = most_recent["role"]

    return PitcherContext(
        pitcher_name=data.pitcher_name,
        pitcher_id=data.pitcher_id,
        throws=data.throws,
        role=role,
        fastball=fastball,
        velocity_arc=velocity_arc,
        arsenal=arsenal,
        platoon_mix=platoon_mix,
        first_pitch=first_pitch,
        execution=execution,
        intermediates=intermediates,
        attributions=attributions,
        hard_hit_rate=hard_hit_rate,
        release_point=release_point,
        workload=workload,
        temporal=temporal,
        cross_season_summary=cross_season_summary,
        arsenal_trend=arsenal_trend,
        pitch_shape=pitch_shape,
    )


class MultiFrameContext(BaseModel):
    """One PitcherContext per temporal frame.

    Wrapper shape (not per-field) so every PitcherContext field keeps its
    type and all render_/_build_*_input helpers stay unchanged. Today only
    RECENT is populated; later phases add PRIOR / MOST_RECENT / SEASON
    frames (CHANGES/RECAP modes, see §5).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    frames: dict[TemporalFrame, PitcherContext]

    def for_frame(self, frame: TemporalFrame) -> PitcherContext:
        try:
            return self.frames[frame]
        except KeyError:
            available = ", ".join(sorted(f.value for f in self.frames))
            raise ValueError(
                f"frame {frame.value!r} not assembled; available: {available}"
            ) from None

    @property
    def primary(self) -> PitcherContext:
        """The default frame current call sites read (recent-appearance window)."""
        return self.for_frame(TemporalFrame.RECENT)


def assemble_multi_frame_context(data: PitcherData) -> MultiFrameContext:
    """Assemble the multi-frame context.

    Currently only the recent-appearance frame is built (it equals today's
    assemble_pitcher_context output). Other appearance-count frames
    (PRIOR / MOST_RECENT / SEASON) are added when CHANGES/RECAP modes land.
    """
    return MultiFrameContext(
        frames={TemporalFrame.RECENT: assemble_pitcher_context(data)},
    )


def assemble_prior_context(
    data: PitcherData, recent_n: int, prior_m: int
) -> PitcherContext:
    """Assemble a PitcherContext for the PRIOR appearance-count frame.

    Re-slices ``window_appearances`` to the ``prior_m`` appearances immediately
    older than the ``recent_n`` most-recent ones, leaving statcast and all
    baselines untouched. The engine derives window metrics by filtering
    ``data.statcast`` to the window's game dates, so replacing
    ``window_appearances`` is sufficient to retarget every ``window_*`` field.
    """
    prior_data = dataclasses.replace(
        data,
        window_appearances=filter_to_prior_appearances(
            data.appearances, recent_n, prior_m
        ),
    )
    return assemble_pitcher_context(prior_data)
