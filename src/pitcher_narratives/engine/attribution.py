"""Frame-scoped consumer of producer-emitted outcome attribution."""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import (
    IncompatiblePitchingPlusExport,
    PitcherData,
    filter_to_frame,
    validated_join,
)
from pitcher_narratives.engine._common import _OUTCOME_COLS_P, _build_name_map
from pitcher_narratives.facts import DERIVED_FACT_SOURCE, Fact, FactKind

_THREE_DECIMAL_RECONCILIATION_TOLERANCE = 0.000500000001


@dataclass(frozen=True)
class OutcomeContribution:
    """One producer-emitted raw outcome contribution."""

    outcome: str
    contribution: float
    fact_id: str


@dataclass(frozen=True)
class ComponentAttribution:
    """Frame-scoped P-model decomposition with explicit centering semantics."""

    pitch_type: str
    pitch_name: str
    contributions: tuple[OutcomeContribution, ...]
    raw_total_xrv100: float
    league_centering_offset_xrv100: float
    centered_xrv100_p: float
    n_pitches: int
    frame_id: str
    manifest_id: str
    run_value_table_version: str
    reference_population: str
    raw_total_fact_id: str
    league_centering_offset_fact_id: str
    centered_xrv100_p_fact_id: str


# ── Component attribution ────────────────────────────────────────────


def compute_component_attribution(
    data: PitcherData,
) -> list[ComponentAttribution]:
    """Pitch-count-combine producer-emitted appearance attribution rows.

    This consumer never rebuilds outcome contributions from pitch probabilities
    or a run-value lookup. Missing producer rows therefore remain unavailable.
    """
    if data.frame is None:
        raise ValueError("PitcherData has no canonical frame")
    artifact = data.artifact_semantics.get("pitcher_type_outcome_appearance")
    if data.artifact_semantics and artifact is None:
        return []
    emitted = data.aggregates.get("pitcher_type_outcome_appearance")
    if emitted is None:
        if artifact is not None:
            raise IncompatiblePitchingPlusExport("registered attribution artifact was not loaded")
        return []
    if emitted.is_empty() and not data.artifact_semantics:
        return []
    selected = filter_to_frame(emitted, data.frame)
    appearance_keys = [
        "season",
        "pitcher",
        "pitch_type",
        "game_date",
        "game_pk",
    ]
    missing_pitch_columns = set(appearance_keys) - set(data.pitches.columns)
    if missing_pitch_columns:
        raise IncompatiblePitchingPlusExport(
            f"all_pitches cannot validate attribution coverage; missing {sorted(missing_pitch_columns)}"
        )
    expected_appearances = (
        filter_to_frame(data.pitches, data.frame)
        .filter(pl.col("pitcher") == data.pitcher_id)
        .group_by(appearance_keys)
        .len(name="_expected_n_pitches")
    )
    emitted_appearances = selected.select(
        *appearance_keys,
        "n_pitches",
    ).unique()
    coverage = validated_join(
        expected_appearances,
        emitted_appearances,
        on=appearance_keys,
        cardinality="1:1",
        required=True,
        left_name="frame all_pitches appearances",
        right_name="outcome attribution appearances",
    )
    if coverage.height != emitted_appearances.height:
        extras = emitted_appearances.join(
            expected_appearances,
            on=appearance_keys,
            how="anti",
        ).select(appearance_keys)
        raise IncompatiblePitchingPlusExport(
            f"outcome attribution has appearances outside the frame: {extras.to_dicts()}"
        )
    if coverage.filter(pl.col("_expected_n_pitches") != pl.col("n_pitches")).height:
        raise IncompatiblePitchingPlusExport("outcome attribution pitch counts do not match all_pitches")
    canonical_frame = data.aggregates.get("pitcher_type_appearance")
    required_canonical_columns = {*appearance_keys, "n_pitches", "xRV100_P"}
    if canonical_frame is None:
        raise IncompatiblePitchingPlusExport(
            "canonical pitcher_type_appearance was not loaded for attribution reconciliation"
        )
    missing_canonical_columns = required_canonical_columns - set(canonical_frame.columns)
    if missing_canonical_columns:
        raise IncompatiblePitchingPlusExport(
            "canonical pitcher_type_appearance cannot validate attribution; "
            f"missing {sorted(missing_canonical_columns)}"
        )
    canonical_appearances = (
        filter_to_frame(canonical_frame, data.frame)
        .filter(pl.col("pitcher") == data.pitcher_id)
        .select(
            *appearance_keys,
            pl.col("n_pitches").alias("_canonical_n_pitches"),
            pl.col("xRV100_P").alias("_canonical_xrv100_p"),
        )
    )
    attribution_appearances = selected.select(
        *appearance_keys,
        pl.col("n_pitches").alias("_attribution_n_pitches"),
        pl.col("centered_xrv100_p").alias("_attribution_centered_xrv100_p"),
    ).unique()
    canonical_reconciliation = validated_join(
        canonical_appearances,
        attribution_appearances,
        on=appearance_keys,
        cardinality="1:1",
        required=True,
        left_name="canonical pitcher_type_appearance",
        right_name="outcome attribution appearances",
    )
    if canonical_reconciliation.height != attribution_appearances.height:
        extras = attribution_appearances.join(
            canonical_appearances,
            on=appearance_keys,
            how="anti",
        ).select(appearance_keys)
        raise IncompatiblePitchingPlusExport(
            "outcome attribution has appearances outside canonical pitcher_type_appearance: "
            f"{extras.to_dicts()}"
        )
    aggregate_reconciliation = canonical_reconciliation.group_by("pitch_type").agg(
        pl.col("_canonical_n_pitches").sum().alias("_canonical_total_n_pitches"),
        pl.col("_attribution_n_pitches").sum().alias("_attribution_total_n_pitches"),
        (
            (pl.col("_canonical_xrv100_p") * pl.col("_canonical_n_pitches")).sum()
            / pl.col("_canonical_n_pitches").sum()
        ).alias("_canonical_centered_xrv100_p"),
        (
            (pl.col("_attribution_centered_xrv100_p") * pl.col("_attribution_n_pitches")).sum()
            / pl.col("_attribution_n_pitches").sum()
        ).alias("_attribution_centered_xrv100_p"),
    )
    if aggregate_reconciliation.filter(
        pl.col("_canonical_total_n_pitches") != pl.col("_attribution_total_n_pitches")
    ).height:
        raise IncompatiblePitchingPlusExport(
            "outcome attribution pitch counts do not match canonical pitcher_type_appearance"
        )
    for row in aggregate_reconciliation.iter_rows(named=True):
        if not math.isclose(
            row["_canonical_centered_xrv100_p"],
            row["_attribution_centered_xrv100_p"],
            rel_tol=0.0,
            abs_tol=_THREE_DECIMAL_RECONCILIATION_TOLERANCE,
        ):
            raise IncompatiblePitchingPlusExport(
                "outcome attribution centered xRV100_P does not match canonical "
                f"pitcher_type_appearance for {row['pitch_type']}"
            )
    if selected.is_empty():
        return []

    fact_registry = data.fact_registry
    if fact_registry is None:
        raise ValueError("attribution requires PitcherData's manifest-bound fact registry")
    name_map = _build_name_map(data.pitches)
    expected_outcomes = frozenset(column.removesuffix("_P") for column in _OUTCOME_COLS_P)
    results: list[ComponentAttribution] = []
    reference_population = data.frame.source_population
    if artifact is not None:
        centered_semantics = artifact.metrics.get("centered_xrv100_p")
        if centered_semantics is not None:
            reference_population = centered_semantics.reference_population

    for pitch_type in selected["pitch_type"].unique(maintain_order=True):
        pitch_rows = selected.filter(pl.col("pitch_type") == pitch_type)
        manifest_ids = pitch_rows["manifest_id"].unique().to_list()
        run_value_versions = pitch_rows["run_value_table_version"].unique().to_list()
        if len(manifest_ids) != 1 or len(run_value_versions) != 1:
            raise ValueError(f"{pitch_type} attribution spans multiple producer contracts")
        manifest_id = str(manifest_ids[0])
        run_value_version = str(run_value_versions[0])

        pitch_appearance_keys = appearance_keys
        appearances = pitch_rows.unique(subset=pitch_appearance_keys)
        n_pitches = int(appearances["n_pitches"].sum())
        if n_pitches <= 0:
            raise ValueError(f"{pitch_type} attribution has no pitches")

        contributions: list[OutcomeContribution] = []
        for outcome in sorted(expected_outcomes):
            outcome_rows = pitch_rows.filter(pl.col("outcome") == outcome)
            if outcome_rows.height != appearances.height:
                raise ValueError(
                    f"{pitch_type} attribution does not cover outcome {outcome!r} once per appearance"
                )
            contribution = float(
                (outcome_rows["raw_component_xrv100"] * outcome_rows["n_pitches"]).sum() / n_pitches
            )
            fact = _attribution_fact(
                data,
                pitch_type=str(pitch_type),
                metric="raw_component_xrv100",
                entity=(f"pitcher:{data.pitcher_id}|pitch_type:{pitch_type}|outcome:{outcome}"),
                value=contribution,
                n_pitches=n_pitches,
                manifest_id=manifest_id,
                run_value_version=run_value_version,
                reference_population=reference_population,
                source_fact_ids=data.base_fact_ids(
                    "pitcher_type_outcome_appearance",
                    outcome_rows,
                    ("raw_component_xrv100", "n_pitches"),
                ),
            )
            fact_registry.add(fact)
            contributions.append(
                OutcomeContribution(
                    outcome=outcome,
                    contribution=contribution,
                    fact_id=fact.id,
                )
            )

        weighted_values: dict[str, float] = {}
        for column in (
            "raw_total_xrv100",
            "league_centering_offset_xrv100",
            "centered_xrv100_p",
        ):
            weighted_values[column] = float(
                (appearances[column] * appearances["n_pitches"]).sum() / n_pitches
            )

        raw_total = weighted_values["raw_total_xrv100"]
        offset = weighted_values["league_centering_offset_xrv100"]
        centered = weighted_values["centered_xrv100_p"]
        component_sum = sum(row.contribution for row in contributions)
        if not math.isclose(
            component_sum,
            raw_total,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ValueError(f"{pitch_type} raw attribution components do not sum to raw total")
        if not math.isclose(
            raw_total + offset,
            centered,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ValueError(f"{pitch_type} raw attribution does not reconcile to centered P")

        scalar_facts = {
            metric: _attribution_fact(
                data,
                pitch_type=str(pitch_type),
                metric=metric,
                entity=f"pitcher:{data.pitcher_id}|pitch_type:{pitch_type}",
                value=value,
                n_pitches=n_pitches,
                manifest_id=manifest_id,
                run_value_version=run_value_version,
                reference_population=reference_population,
                source_fact_ids=data.base_fact_ids(
                    "pitcher_type_outcome_appearance",
                    pitch_rows,
                    (metric, "n_pitches"),
                ),
            )
            for metric, value in weighted_values.items()
        }
        for fact in scalar_facts.values():
            fact_registry.add(fact)

        contributions.sort(key=lambda row: abs(row.contribution), reverse=True)
        results.append(
            ComponentAttribution(
                pitch_type=str(pitch_type),
                pitch_name=name_map.get(str(pitch_type), str(pitch_type)),
                contributions=tuple(contributions),
                raw_total_xrv100=raw_total,
                league_centering_offset_xrv100=offset,
                centered_xrv100_p=centered,
                n_pitches=n_pitches,
                frame_id=data.frame.id,
                manifest_id=manifest_id,
                run_value_table_version=run_value_version,
                reference_population=reference_population,
                raw_total_fact_id=scalar_facts["raw_total_xrv100"].id,
                league_centering_offset_fact_id=scalar_facts["league_centering_offset_xrv100"].id,
                centered_xrv100_p_fact_id=scalar_facts["centered_xrv100_p"].id,
            )
        )

    results.sort(key=lambda row: row.n_pitches, reverse=True)
    return results


def _attribution_fact(
    data: PitcherData,
    *,
    pitch_type: str,
    metric: str,
    entity: str,
    value: float,
    n_pitches: int,
    manifest_id: str,
    run_value_version: str,
    reference_population: str,
    source_fact_ids: tuple[str, ...],
) -> Fact:
    if data.frame is None:
        raise ValueError("PitcherData has no canonical frame")
    return Fact.create(
        kind=FactKind.COMPUTED,
        metric=metric,
        variant=("derived" if metric == "league_centering_offset_xrv100" else "P"),
        entity=entity,
        value=value,
        unit="runs_per_100_pitches",
        frame_id=data.frame.id,
        population=reference_population,
        sample_size=n_pitches,
        sufficiency="available",
        source=DERIVED_FACT_SOURCE,
        semantic_key=(
            f"pitcher:{data.pitcher_id}|{pitch_type}|{entity}|{metric}|"
            f"producer_manifest={manifest_id}|run_values={run_value_version}"
        ),
        source_fact_ids=source_fact_ids,
        transform="pitch_count_weighted_mean(emitted_appearance_rows)",
        manifest_version=data.frame.source_population,
    )
