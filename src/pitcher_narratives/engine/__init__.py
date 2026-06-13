"""Computation engine for pitcher narratives (subpackage facade).

Transforms PitcherData into pre-computed analysis ready for LLM
consumption. This module is a thin facade: every public symbol is
implemented in a focused concern module (baselines, arsenal, execution,
workload, mechanics, contact, tto, attribution) and re-exported here so
existing ``from pitcher_narratives.engine import X`` imports keep working.

Shared private helpers live in ``_common``; a handful are re-exported here
because the test suite references them directly.
"""

from __future__ import annotations

# Shared internals — re-exported so the remaining compute code in this
# module, sibling concern modules, and the test suite resolve them by name.
from pitcher_narratives.engine._common import (  # noqa: F401
    _COLD_START_STRING,
    _CSW_DESCRIPTIONS,
    _DOUBLE_OUT_EVENTS,
    _FASTBALL_TYPES,
    _FEET_TO_INCHES,
    _INTERMEDIATE_COLS,
    _INTERMEDIATE_P_COLS,
    _INTERMEDIATE_S_COLS,
    _MIN_PITCHES,
    _MOVEMENT_THRESHOLD,
    _OUT_EVENTS,
    _OUTCOME_COLS_P,
    _OUTCOME_NAMES,
    _PPLUS_METRICS,
    _PPLUS_THRESHOLD,
    _SHARP_PPLUS_THRESHOLD,
    _SHARP_VELO_THRESHOLD,
    _SWING_DESCRIPTIONS,
    _USAGE_THRESHOLD,
    _VELO_THRESHOLD,
    _XMETRICS,
    _ZONE_IN,
    _ZONE_OUT,
    _build_name_map,
    _compute_platoon_baseline,
    _float,
    _get_window_game_dates,
    _identify_primary_fastball,
    _is_cold_start,
    _movement_delta_string,
    _per_season_velo,
    _pplus_delta_string,
    _pplus_delta_strings,
    _safe_metric,
    _stand_to_platoon,
    _usage_delta_string,
    _velo_delta_string,
    _weighted_window_metrics,
    _window_date_type_filter,
)
from pitcher_narratives.engine.arsenal import (
    ArsenalPitchTrend,
    ArsenalTrends,
    FastballSummary,
    FirstPitchEntry,
    FirstPitchWeaponry,
    PitchTypeSummary,
    PlatoonMix,
    PlatoonSplit,
    VelocityArc,
    compute_arsenal_summary,
    compute_arsenal_trends,
    compute_fastball_summary,
    compute_first_pitch_weaponry,
    compute_platoon_mix,
    compute_velocity_arc,
)
from pitcher_narratives.engine.attribution import (
    ComponentAttribution,
    OutcomeContribution,
    compute_component_attribution,
)
from pitcher_narratives.engine.baselines import (
    LeagueBaseline,
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
from pitcher_narratives.engine.contact import (
    HardHitRate,
    compute_hard_hit_rate,
)
from pitcher_narratives.engine.execution import (
    ExecutionMetrics,
    IntermediateProbabilities,
    compute_execution_metrics,
    compute_intermediate_probabilities,
)
from pitcher_narratives.engine.mechanics import (
    ReleasePointMetrics,
    ReleasePointPitchType,
    compute_release_point_metrics,
)
from pitcher_narratives.engine.tto import (
    TTOAnalysis,
    TTOPitchType,
    TTOPlatoonSplit,
    TTOSplit,
    compute_tto_analysis,
)
from pitcher_narratives.engine.workload import (
    AppearanceWorkload,
    CrossSeasonSummary,
    TemporalContext,
    WorkloadContext,
    compute_cross_season_summary,
    compute_temporal_context,
    compute_workload_context,
)

__all__ = [
    "AppearanceWorkload",
    "ArsenalPitchTrend",
    "ArsenalTrends",
    "ComponentAttribution",
    "CrossSeasonSummary",
    "ExecutionMetrics",
    "FastballSummary",
    "FirstPitchEntry",
    "FirstPitchWeaponry",
    "HardHitRate",
    "IntermediateProbabilities",
    "LeagueBaseline",
    "OutcomeContribution",
    "PitchTypeSummary",
    "PlatoonMix",
    "PlatoonSplit",
    "ReleasePointMetrics",
    "ReleasePointPitchType",
    "TTOAnalysis",
    "TTOPitchType",
    "TTOPlatoonSplit",
    "TTOSplit",
    "TemporalContext",
    "VelocityArc",
    "WorkloadContext",
    "compute_arsenal_summary",
    "compute_arsenal_trends",
    "compute_component_attribution",
    "compute_cross_season_summary",
    "compute_execution_metrics",
    "compute_fastball_summary",
    "compute_first_pitch_weaponry",
    "compute_hard_hit_rate",
    "compute_intermediate_probabilities",
    "compute_league_baselines",
    "compute_platoon_mix",
    "compute_release_point_metrics",
    "compute_temporal_context",
    "compute_tto_analysis",
    "compute_velocity_arc",
    "compute_workload_context",
    "format_s_variant_comparisons",
    "outlier_tag",
    "render_league_baselines",
]

