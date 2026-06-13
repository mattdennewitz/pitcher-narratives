"""Computation engine for pitcher narratives.

Transforms PitcherData into pre-computed analysis with qualitative trend
strings ready for LLM consumption. Computes fastball quality deltas
(velocity, P+/S+/L+, movement), within-game velocity arcs, and shared
delta helpers used across all analysis facets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData, load_run_values

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

_log = logging.getLogger(__name__)

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





# ── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class OutcomeContribution:
    """A single outcome's contribution to xRV100."""

    outcome: str
    """Outcome name, e.g., 'whiff', 'home_run', 'called_strike'."""

    contribution: float
    """mean(p_i * rv_i) * 100, same scale as xRV100."""


@dataclass
class ComponentAttribution:
    """Per-pitch-type decomposition of xRV into 13 outcome contributions.

    Each pitch type's xRV100 is broken into 13 additive outcome-level
    contributions: contribution_i = mean(probability_i * delta_run_exp_i) * 100.
    The 13 contributions sum to the raw xRV100 total (pre-mean-subtraction).
    """

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    contributions: list[OutcomeContribution]
    """13 items, sorted by |contribution| descending."""

    total_xrv100: float
    """Sum of all 13 contribution values."""

    n_pitches: int
    """Number of pitches used in the computation."""


# ── Public API ────────────────────────────────────────────────────────


# ── Execution metrics helpers ────────────────────────────────────────


# ── Component attribution ────────────────────────────────────────────


def compute_component_attribution(
    data: PitcherData,
    game_pk: int | None = None,
) -> list[ComponentAttribution]:
    """Decompose xRV into 13 outcome-level contributions per pitch type.

    For each pitch: contribution_i = p_i * delta_run_exp(outcome_i, balls, strikes).
    Per pitch type: mean(contribution_i) * 100 for each of 13 outcomes.

    The contributions sum to the RAW xRV100 (pre-mean-subtraction). This will
    differ from the mean-subtracted xRV100_P in the CSVs by a constant
    league-average offset.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.
        game_pk: If provided, compute for a single appearance only.
            If None, compute season-level (all pitches for this pitcher).

    Returns:
        List of ComponentAttribution, one per pitch type, sorted by
        n_pitches descending. Empty list if all_pitches CSV lacks
        required outcome columns.
    """
    all_pitches = data.agg_csvs["all_pitches"]

    # Check that all 13 outcome columns exist
    if not all(col in all_pitches.columns for col in _OUTCOME_COLS_P):
        return []

    # Load run values lookup table
    try:
        rv_df = load_run_values()
    except FileNotFoundError as exc:
        _log.warning("Skipping component attribution: %s", exc)
        return []

    # Filter to specific appearance if requested
    if game_pk is not None:
        all_pitches = all_pitches.filter(pl.col("game_pk") == game_pk)
        if all_pitches.is_empty():
            return []

    name_map = _build_name_map(data.statcast)

    # Get pitch types sorted by count descending
    type_counts = (
        all_pitches.group_by("pitch_type")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
    )
    pitch_types = type_counts["pitch_type"].to_list()

    results: list[ComponentAttribution] = []

    for pt in pitch_types:
        pitches = all_pitches.filter(pl.col("pitch_type") == pt)
        n_pitches = pitches.height
        if n_pitches == 0:
            continue

        # Unpivot the 13 probability columns to long format
        long = pitches.unpivot(
            on=list(_OUTCOME_COLS_P),
            index=["game_pk", "at_bat_number", "pitch_number", "balls", "strikes"],
            variable_name="outcome_col",
            value_name="probability",
        ).with_columns(
            pl.col("outcome_col").str.replace("_P$", "").alias("model_classes"),
        )

        # Join with run values on [balls, strikes, model_classes]
        joined = long.join(
            rv_df.select(["balls", "strikes", "model_classes", "delta_run_exp"]),
            on=["balls", "strikes", "model_classes"],
            how="inner",
        )

        # Compute per-pitch contribution = probability * delta_run_exp
        joined = joined.with_columns(
            (pl.col("probability") * pl.col("delta_run_exp")).alias("contribution"),
        )

        # Group by outcome and compute mean(contribution) * 100
        outcome_means = (
            joined.group_by("model_classes")
            .agg(pl.col("contribution").mean().alias("mean_contribution"))
            .with_columns(
                (pl.col("mean_contribution") * 100).alias("contribution_xrv100"),
            )
        )

        # Build list of OutcomeContribution, sorted by |contribution| descending
        contributions: list[OutcomeContribution] = []
        for row in outcome_means.iter_rows(named=True):
            contributions.append(
                OutcomeContribution(
                    outcome=row["model_classes"],
                    contribution=row["contribution_xrv100"],
                )
            )
        contributions.sort(key=lambda c: abs(c.contribution), reverse=True)

        total_xrv100 = sum(c.contribution for c in contributions)

        results.append(
            ComponentAttribution(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                contributions=contributions,
                total_xrv100=total_xrv100,
                n_pitches=n_pitches,
            )
        )

    results.sort(key=lambda x: x.n_pitches, reverse=True)
    return results
