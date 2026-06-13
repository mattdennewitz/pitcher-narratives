"""Component attribution: decomposes xRV100 into 13 outcome-level
contributions per pitch type using the run-values lookup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData, load_run_values
from pitcher_narratives.engine._common import _OUTCOME_COLS_P, _build_name_map

_log = logging.getLogger(__name__)


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
