"""Manifest-row and deterministic context fact registration."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

import polars as pl

from pitcher_narratives.bundle_contract import (
    ArtifactSemantics,
    CalibrationArtifactSemantics,
    CalibrationMetricsRow,
    ModelEvaluationArtifact,
    ProducerIdentity,
)
from pitcher_narratives.facts import DERIVED_FACT_SOURCE, Fact, FactKind, FactRegistry
from pitcher_narratives.temporal import FrameSelection


def _json_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def manifest_source(grain: str) -> str:
    return f"pitchingplus:{grain}"


def manifest_row_id(artifact: ArtifactSemantics, row: Mapping[str, object]) -> str:
    """Return a stable row identity from manifest season and natural keys."""
    natural_key = {column: _json_value(row.get(column)) for column in artifact.natural_key}
    payload = {
        "season": artifact.season,
        "grain": artifact.grain,
        "natural_key": natural_key,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"row:{digest}"


def _fact_value(value: object) -> int | float | str | bool | None:
    value = _json_value(value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return None


def _variant(artifact: ArtifactSemantics, column: str) -> str | None:
    semantics = artifact.metrics.get(column)
    if semantics is not None:
        return semantics.variant
    if column in {"P+", "S+", "L+"}:
        return column[0]
    for suffix in ("_P", "_S", "_L"):
        if column.endswith(suffix):
            return suffix[-1]
    return None


def _entity(row: Mapping[str, object]) -> str:
    parts: list[str] = []
    for column in ("pitcher", "pitch_type", "game_pk", "stand", "platoon_matchup", "outcome"):
        value = row.get(column)
        if value is not None:
            parts.append(f"{column}:{_json_value(value)}")
    return "|".join(parts) or "pitchingplus-population"


_PRODUCER_IDENTITY_SOURCE = "pitchingplus:producer_identity"


def _producer_identity_row_id(identity: ProducerIdentity) -> str:
    return (
        f"producer_identity:{identity.schema_version}:"
        f"{identity.feature_schema_sha256}:{identity.model_bundle_sha256}"
    )


def _register_producer_identity_facts(
    registry: FactRegistry,
    *,
    identity: ProducerIdentity,
    frame: FrameSelection,
) -> None:
    row_id = _producer_identity_row_id(identity)
    for field in (
        "schema_version",
        "feature_schema_sha256",
        "model_bundle_sha256",
    ):
        registry.add(
            Fact.create(
                kind=FactKind.MODEL_SEMANTIC,
                metric=f"producer_identity.{field}",
                variant="identity",
                entity="PitchingPlus producer bundle",
                value=getattr(identity, field),
                unit=None,
                frame_id=frame.id,
                population=frame.source_population,
                sample_size=1,
                sufficiency="available",
                source=_PRODUCER_IDENTITY_SOURCE,
                semantic_key=f"producer_identity|{field}",
                manifest_version=frame.source_population,
                source_row_id=row_id,
            )
        )


_CALIBRATION_SOURCE = "pitchingplus:calibration"


def _register_calibration_facts(
    registry: FactRegistry,
    *,
    descriptor: CalibrationArtifactSemantics,
    report: ModelEvaluationArtifact,
    frame: FrameSelection,
) -> None:
    """Register held-out evaluation scalars against the exact JSON artifact."""
    row_id = f"calibration:{descriptor.sha256}"
    population = report.metadata.scoring_population

    def add(
        path: str,
        value: object,
        *,
        sample_size: int,
        variant: str | None = None,
        entity: str = "held-out model evaluation",
        unit: str | None = None,
    ) -> None:
        scalar = _fact_value(value)
        if scalar is None:
            return
        registry.add(
            Fact.create(
                kind=FactKind.MODEL_OUTPUT,
                metric=f"calibration.{path}",
                variant=variant,
                entity=entity,
                value=scalar,
                unit=unit,
                frame_id=frame.id,
                population=population,
                sample_size=sample_size,
                sufficiency="held_out",
                source=_CALIBRATION_SOURCE,
                semantic_key=(
                    f"artifact_sha256={descriptor.sha256}|identity_schema="
                    f"{descriptor.producer_identity.schema_version}|feature_schema="
                    f"{descriptor.producer_identity.feature_schema_sha256}|model_bundle="
                    f"{descriptor.producer_identity.model_bundle_sha256}|{path}"
                ),
                manifest_version=frame.source_population,
                source_row_id=row_id,
            )
        )

    metadata = report.metadata
    for name, value in (
        ("metadata.producer_identity.schema_version", metadata.producer_identity.schema_version),
        (
            "metadata.producer_identity.feature_schema_sha256",
            metadata.producer_identity.feature_schema_sha256,
        ),
        (
            "metadata.producer_identity.model_bundle_sha256",
            metadata.producer_identity.model_bundle_sha256,
        ),
        ("metadata.scoring_population", metadata.scoring_population),
        ("metadata.as_of", metadata.as_of),
        ("metadata.temporal_holdout_year", metadata.split_policy.temporal_holdout_year),
        ("metadata.prediction_rows", metadata.row_counts.prediction_rows),
    ):
        add(
            name,
            value,
            sample_size=metadata.row_counts.prediction_rows,
            entity="held-out evaluation artifact",
        )
    for family, pitch_set_sha256 in sorted(metadata.pitch_set_sha256_by_family.items()):
        add(
            f"metadata.pitch_set_sha256_by_family.{family}",
            pitch_set_sha256,
            sample_size=report.models[f"P.{family}"].overall.n_observations,
            entity=f"held-out {family} pitch set",
        )

    def add_metrics(
        prefix: str,
        metrics: CalibrationMetricsRow,
        *,
        variant: str,
        entity: str,
    ) -> None:
        units = {
            "log_loss": "nats",
            "brier_score": "probability_squared",
            "empirical_prior_log_loss": "nats",
            "log_loss_skill": "nats",
            "expected_calibration_error": "probability",
        }
        for name in (
            "n_observations",
            "n_classes",
            "log_loss",
            "brier_score",
            "empirical_prior_log_loss",
            "log_loss_skill",
            "expected_calibration_error",
        ):
            add(
                f"{prefix}.{name}",
                getattr(metrics, name),
                sample_size=metrics.n_observations,
                variant=variant,
                entity=entity,
                unit=units.get(name),
            )
        for index, bin_row in enumerate(metrics.reliability_bins):
            bin_entity = f"{entity}|probability_bin:{bin_row.lower:.12g}-{bin_row.upper:.12g}"
            for name in (
                "lower",
                "upper",
                "count",
                "mean_probability",
                "observed_frequency",
            ):
                add(
                    f"{prefix}.reliability_bins[{index}].{name}",
                    getattr(bin_row, name),
                    sample_size=bin_row.count,
                    variant=variant,
                    entity=bin_entity,
                    unit=("probability" if name != "count" else "observations"),
                )

    for model_key, model_report in sorted(report.models.items()):
        variant = model_key.split(".", maxsplit=1)[0]
        add_metrics(
            f"{model_key}.overall",
            model_report.overall,
            variant=variant,
            entity=model_key,
        )
        for dimension, strata in sorted(model_report.strata.items()):
            for stratum, metrics in sorted(strata.items()):
                add_metrics(
                    f"{model_key}.strata.{dimension}.{stratum}",
                    metrics,
                    variant=variant,
                    entity=f"{model_key}|{dimension}:{stratum}",
                )


def _artifact_statistical_population(
    artifact: ArtifactSemantics,
    frame: FrameSelection,
) -> str:
    """Describe sampled rows independently from bundle snapshot identity."""
    if artifact.grain == "all_pitches" or artifact.grain.endswith("_appearance"):
        return f"exact-frame:{frame.id}"
    if artifact.grain.endswith("_reference"):
        references = {
            metric.reference_population for metric in artifact.metrics.values() if metric.reference_population
        }
        if len(references) == 1:
            return next(iter(references))
    return f"scoring-season:{artifact.season}:{artifact.grain}"


def build_manifest_fact_registry(
    artifact_rows: Mapping[tuple[int, str], tuple[ArtifactSemantics, pl.DataFrame]],
    *,
    frame: FrameSelection,
    producer_identity: ProducerIdentity | None = None,
    calibration: tuple[CalibrationArtifactSemantics, ModelEvaluationArtifact] | None = None,
) -> tuple[FactRegistry, str]:
    """Register every scalar emitted value against its validated manifest row."""
    row_ids_by_source: dict[str, set[str]] = {}
    prepared: list[tuple[ArtifactSemantics, dict[str, Any], str]] = []
    for key in sorted(artifact_rows):
        artifact, rows = artifact_rows[key]
        source = manifest_source(artifact.grain)
        source_rows = row_ids_by_source.setdefault(source, set())
        for row in rows.iter_rows(named=True):
            row_id = manifest_row_id(artifact, row)
            source_rows.add(row_id)
            prepared.append((artifact, row, row_id))

    if producer_identity is not None:
        row_ids_by_source[_PRODUCER_IDENTITY_SOURCE] = {_producer_identity_row_id(producer_identity)}
    if calibration is not None:
        descriptor, _ = calibration
        row_ids_by_source[_CALIBRATION_SOURCE] = {f"calibration:{descriptor.sha256}"}
    registry = FactRegistry(
        manifest_version=frame.source_population,
        manifest_rows=row_ids_by_source,
    )
    base_ids: list[str] = []
    for artifact, row, row_id in prepared:
        source = manifest_source(artifact.grain)
        sample_size = int(row["n_pitches"]) if row.get("n_pitches") is not None else 1
        natural_key = "|".join(
            f"{column}={_json_value(row.get(column))!r}" for column in artifact.natural_key
        )
        for column in artifact.required_columns:
            value = _fact_value(row.get(column))
            if value is None:
                continue
            semantics = artifact.metrics.get(column)
            variant = _variant(artifact, column)
            fact = Fact.create(
                kind=(
                    FactKind.MODEL_OUTPUT
                    if semantics is not None or variant is not None
                    else FactKind.OBSERVED
                ),
                metric=f"{artifact.grain}.{column}",
                variant=variant,
                entity=_entity(row),
                value=value,
                unit=semantics.unit if semantics is not None else None,
                frame_id=frame.id,
                population=_artifact_statistical_population(artifact, frame),
                sample_size=sample_size,
                sufficiency="available",
                source=source,
                semantic_key=(
                    f"season={artifact.season}|grain={artifact.grain}|{natural_key}|metric={column}"
                ),
                manifest_version=frame.source_population,
                source_row_id=row_id,
            )
            registry.add(fact)
            base_ids.append(fact.id)

    if producer_identity is not None:
        _register_producer_identity_facts(
            registry,
            identity=producer_identity,
            frame=frame,
        )

    if calibration is not None:
        descriptor, report = calibration
        _register_calibration_facts(
            registry,
            descriptor=descriptor,
            report=report,
            frame=frame,
        )

    if not base_ids:
        raise ValueError("validated PitchingPlus bundle produced no manifest-bound facts")
    lineage = registry.add(
        Fact.create(
            kind=FactKind.COMPUTED,
            metric="context.manifest_row_lineage",
            variant="derived",
            entity="filtered PitchingPlus producer rows",
            value=len(prepared),
            unit="rows",
            frame_id=frame.id,
            population=frame.source_population,
            sample_size=len(prepared),
            sufficiency="available",
            source=DERIVED_FACT_SOURCE,
            semantic_key="all filtered producer scalar values used by deterministic context",
            source_fact_ids=base_ids,
            transform="manifest_scalars:identity(filtered_validated_bundle_values)",
            manifest_version=frame.source_population,
        )
    )
    registry.add(
        Fact.create(
            kind=FactKind.COMPUTED,
            metric="context.frame.as_of_input",
            variant="boundary",
            entity="canonical frame selection boundary",
            value=frame.as_of.isoformat(),
            unit="date",
            frame_id=frame.id,
            population=frame.source_population,
            sample_size=len(frame.games),
            sufficiency="available",
            source=DERIVED_FACT_SOURCE,
            semantic_key=(f"as_of={frame.as_of.isoformat()}|scoring_season={frame.scoring_season}"),
            source_fact_ids=(lineage.id,),
            transform="frame_selection:explicit_as_of_boundary",
            manifest_version=frame.source_population,
        )
    )
    return registry, lineage.id


def _scalar(value: object) -> int | float | str | bool | None:
    if isinstance(value, Enum):
        return str(value.value)
    return _fact_value(value)


def _children(value: object) -> Iterable[tuple[str, object]]:
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield field.name, getattr(value, field.name)
    elif isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield f"[{key}]", value[key]
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield f"[{index}]", item
    elif hasattr(value.__class__, "model_fields"):
        for name in value.__class__.model_fields:
            if name not in {"facts", "fact_ids"}:
                yield name, getattr(value, name)


def _path(parent: str, child: str) -> str:
    return f"{parent}{child}" if child.startswith("[") else f"{parent}.{child}" if parent else child


def _variant_for_path(path: str) -> str | None:
    lowered = path.lower()
    if "platoon" in lowered:
        return "P" if "p_plus" in lowered else "usage"
    if "s_plus" in lowered or lowered.endswith("_s"):
        return "S"
    if "l_plus" in lowered or lowered.endswith("_l"):
        return "L"
    if "p_plus" in lowered or lowered.endswith("_p"):
        return "P"
    return "derived"


def register_context_facts(
    context_values: Mapping[str, object],
    *,
    registry: FactRegistry,
    source_fact_ids_by_path: Mapping[str, tuple[str, ...]],
    frame: FrameSelection,
    pitcher_id: int,
    pitcher_throws: str,
) -> dict[str, str]:
    """Register deterministic scalar context values without re-registering sources."""
    fact_ids: dict[str, str] = {}

    def exact_sources(path: str, ancestors: tuple[object, ...]) -> tuple[str, ...]:
        mapped = source_fact_ids_by_path.get(path, ())
        if mapped:
            return tuple(sorted(set(mapped)))
        embedded: set[str] = set()
        for ancestor in reversed(ancestors):
            direct = getattr(ancestor, "fact_id", None)
            if isinstance(direct, str) and direct in registry:
                embedded.add(direct)
            fact_ids = getattr(ancestor, "fact_ids", ())
            values = fact_ids.values() if isinstance(fact_ids, Mapping) else fact_ids
            if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
                embedded.update(
                    fact_id for fact_id in values if isinstance(fact_id, str) and fact_id in registry
                )
            source_ids = getattr(ancestor, "source_fact_ids", ())
            if isinstance(source_ids, Iterable) and not isinstance(source_ids, (str, bytes)):
                embedded.update(
                    fact_id for fact_id in source_ids if isinstance(fact_id, str) and fact_id in registry
                )
            if embedded:
                break
        return tuple(sorted(embedded))

    def source_scope(fact: Fact) -> str:
        grain = fact.metric.split(".", 1)[0]
        if grain == "all_pitches" or grain.endswith("_appearance"):
            return "window"
        if grain in {"pitcher", "pitcher_type", "pitcher_type_platoon"}:
            return "season"
        return "reference"

    def summed_source_sample(source_facts: tuple[Fact, ...]) -> int | None:
        measured = tuple(
            fact
            for fact in source_facts
            if fact.sample_size is not None and fact.metric.endswith(".n_pitches")
        )
        if not measured:
            measured = tuple(fact for fact in source_facts if fact.sample_size is not None)
        grain_samples: dict[str, list[tuple[str | None, int]]] = {}
        for fact in measured:
            grain = fact.metric.split(".", 1)[0]
            grain_samples.setdefault(grain, []).append((fact.source_row_id, fact.sample_size or 0))
        effective: list[int] = []
        for grain, samples in grain_samples.items():
            if grain == "all_pitches" or grain.endswith("_appearance"):
                keyed = {row_id: sample for row_id, sample in samples if row_id is not None}
                effective.append(sum(keyed.values()) if keyed else sum(sample for _, sample in samples))
            else:
                effective.append(min(sample for _, sample in samples))
        return min(effective) if effective else None

    def statistical_population(
        source_facts: tuple[Fact, ...],
    ) -> tuple[str, bool]:
        season_populations = sorted(
            {fact.population for fact in source_facts if source_scope(fact) == "season"}
        )
        window_populations = sorted(
            {fact.population for fact in source_facts if source_scope(fact) == "window"}
        )
        if season_populations and window_populations:
            return (
                "comparison[season="
                + " + ".join(season_populations)
                + ";window="
                + " + ".join(window_populations)
                + "]",
                True,
            )
        populations = sorted({fact.population for fact in source_facts})
        if len(populations) == 1:
            return populations[0], False
        return "composed[" + " + ".join(populations) + "]", False

    def ancestor_sample(
        ancestors: tuple[object, ...],
        field_name: str,
    ) -> int | None:
        for ancestor in reversed(ancestors):
            value = getattr(ancestor, field_name, None)
            if value is not None:
                return int(value)
        return None

    def sample_evidence(
        path: str,
        ancestors: tuple[object, ...],
        source_facts: tuple[Fact, ...],
    ) -> tuple[int | None, str]:
        season_facts = tuple(fact for fact in source_facts if source_scope(fact) == "season")
        window_facts = tuple(fact for fact in source_facts if source_scope(fact) == "window")
        season_sample = summed_source_sample(season_facts) or ancestor_sample(ancestors, "n_pitches_season")
        window_sample = summed_source_sample(window_facts) or ancestor_sample(ancestors, "n_pitches_window")
        leaf = path.rsplit(".", 1)[-1].lower()
        if "delta" in leaf and season_sample is not None and window_sample is not None:
            return min(season_sample, window_sample), "comparison_min(season,window)"
        if "season" in leaf:
            return season_sample, "exact_season"
        if "window" in leaf:
            return window_sample, "exact_window"
        if path.startswith("hard_hit_rate."):
            batted_balls = ancestor_sample(ancestors, "n_batted_balls")
            if batted_balls is not None:
                return batted_balls, "ancestor:n_batted_balls"
        direct = summed_source_sample(source_facts)
        if direct is not None:
            return direct, "exact_source_rows"
        for field_name in ("n_pitches", "n_total", "n_batted_balls"):
            sample = ancestor_sample(ancestors, field_name)
            if sample is not None:
                return sample, f"ancestor:{field_name}"
        return None, "frame_games"

    def visit(path: str, value: object, ancestors: tuple[object, ...]) -> None:
        if path.endswith(("fact_id", "fact_ids", "source_fact_ids")):
            return
        scalar = _scalar(value)
        if scalar is not None:
            source_fact_ids = exact_sources(path, ancestors)
            if not source_fact_ids:
                return
            source_facts = tuple(registry.get(fact_id) for fact_id in source_fact_ids)
            population, comparison_population = statistical_population(source_facts)
            sample_size, sample_policy = sample_evidence(path, ancestors, source_facts)
            entity_parts = [f"pitcher:{pitcher_id}"]
            pitch_type: str | None = None
            platoon_side: str | None = None
            for ancestor in reversed(ancestors):
                pitch_type = pitch_type or getattr(ancestor, "pitch_type", None)
                platoon_side = platoon_side or getattr(ancestor, "platoon_side", None)
                if pitch_type:
                    break
            semantic_parts = [
                path,
                f"p_throws={pitcher_throws}",
                f"sample_policy={sample_policy}",
            ]
            if path.startswith("frame_games") and path.endswith((".game_pk", "[game_pk]")):
                entity_parts.append(f"game_pk:{scalar}")
                semantic_parts.append(f"game_pk={scalar}")
            if pitch_type:
                entity_parts.append(f"pitch_type:{pitch_type}")
                semantic_parts.append(f"pitch_type={pitch_type}")
            if platoon_side:
                batter_side = (
                    pitcher_throws if platoon_side == "same" else ("L" if pitcher_throws == "R" else "R")
                )
                entity_parts.append(f"batter_side:{batter_side}")
                semantic_parts.extend((f"platoon={platoon_side}", f"batter_side={batter_side}"))
                population = f"{population};platoon_matchup={platoon_side};batter_side={batter_side}"
            metric = (
                "context.frame.game_pk"
                if path.startswith("frame_games") and path.endswith((".game_pk", "[game_pk]"))
                else (
                    "context.platoon." + path.rsplit(".", 1)[-1]
                    if "platoon_mix.splits" in path
                    else "context." + path
                )
            )
            fact = registry.add(
                Fact.create(
                    kind=FactKind.COMPUTED,
                    metric=metric,
                    variant=_variant_for_path(path),
                    entity="|".join(entity_parts),
                    value=scalar,
                    unit=None,
                    frame_id=frame.id,
                    population=population,
                    sample_size=(sample_size if sample_size is not None else max(len(frame.games), 1)),
                    sufficiency="insufficient" if sample_size == 0 else "available",
                    source=DERIVED_FACT_SOURCE,
                    semantic_key="|".join(semantic_parts),
                    source_fact_ids=source_fact_ids,
                    transform=(
                        f"context_field:deterministic({path});"
                        f"sample_policy={sample_policy};"
                        f"comparison_population={comparison_population}"
                    ),
                    manifest_version=frame.source_population,
                )
            )
            fact_ids[path] = fact.id
            return
        for name, child in _children(value):
            visit(_path(path, name), child, (*ancestors, value))

    for name, value in context_values.items():
        visit(name, value, ())
    return fact_ids


def register_capability_fact(
    *,
    registry: FactRegistry,
    capability: str,
    available: bool,
    evidence_fact_ids: Iterable[str],
    frame: FrameSelection,
    producer_condition: str,
) -> Fact:
    """Register one producer-backed typed availability decision."""
    return registry.add(
        Fact.create(
            kind=FactKind.MODEL_SEMANTIC,
            metric=f"capability.{capability}",
            variant="availability",
            entity=f"pitcher-frame:{frame.id}",
            value=available,
            unit="boolean",
            frame_id=frame.id,
            population=frame.source_population,
            sample_size=max(len(frame.games), 1),
            sufficiency="available",
            source=DERIVED_FACT_SOURCE,
            semantic_key=f"capability={capability}|producer_condition={producer_condition}",
            source_fact_ids=tuple(sorted(set(evidence_fact_ids))),
            transform=f"capability:manifest_covered({producer_condition})",
            manifest_version=frame.source_population,
        )
    )
