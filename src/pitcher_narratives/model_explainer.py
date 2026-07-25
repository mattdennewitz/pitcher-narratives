"""Versioned deterministic Pitching+ model and producer-boundary explanation."""

from __future__ import annotations

from dataclasses import dataclass, field

from pitcher_narratives.bundle_contract import ModelEvaluationArtifact, ProducerIdentity

MODEL_EXPLANATION_TEMPLATE_ID = "pitchingplus-model-and-boundary"
MODEL_EXPLANATION_TEMPLATE_VERSION = "2.0.0"
MODEL_SEMANTIC_SCHEMA_VERSION = "1.0.0"

_EXPLAINED_MODES = frozenset({"report", "changes", "ask"})
_OMITTED_MODES = frozenset({"recap"})
_ARTIFACT_LABELS = {
    "all_pitches": "all_pitches",
    "pitcher": "pitcher aggregate",
    "pitcher_type": "pitch-type aggregate",
    "pitcher_appearance": "appearance aggregate",
    "pitcher_type_appearance": "pitch-type appearance aggregate",
    "pitch_type_reference": "pitch-type reference",
    "pitch_type_slot_reference": "pitch-type slot reference",
    "pitcher_relative_location": "spatial",
    "pitcher_type_outcome_appearance": "component-attribution",
    "calibration": "calibration artifacts",
}


@dataclass(frozen=True)
class ProducerModelSemantics:
    """Producer identity for which the canonical explanation is valid."""

    schema_version: str
    feature_schema_sha256: str
    model_bundle_sha256: str
    artifact_grains: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_identity(
        cls,
        identity: ProducerIdentity,
        *,
        artifact_grains: frozenset[str],
    ) -> ProducerModelSemantics:
        return cls(
            schema_version=identity.schema_version,
            feature_schema_sha256=identity.feature_schema_sha256,
            model_bundle_sha256=identity.model_bundle_sha256,
            artifact_grains=artifact_grains,
        )

    @property
    def identity(self) -> tuple[str, str, str]:
        return (
            self.schema_version,
            self.feature_schema_sha256,
            self.model_bundle_sha256,
        )

    @property
    def is_supported(self) -> bool:
        hashes = (self.feature_schema_sha256, self.model_bundle_sha256)
        return self.schema_version == "1.0.0" and all(
            len(value) == 64 and all(character in "0123456789abcdef" for character in value)
            for value in hashes
        )


@dataclass(frozen=True)
class CalibrationExplanationEvidence:
    """Bounded provenance copied from a validated producer evaluation artifact."""

    evaluation_schema_version: str
    producer_schema_version: str
    feature_schema_sha256: str
    model_bundle_sha256: str
    pitch_set_sha256_by_family: tuple[tuple[str, str], ...]
    scoring_population: str
    as_of: str
    temporal_holdout_year: int
    prediction_rows: int

    @classmethod
    def from_artifact(cls, artifact: ModelEvaluationArtifact) -> CalibrationExplanationEvidence:
        metadata = artifact.metadata
        return cls(
            evaluation_schema_version=artifact.schema_version,
            producer_schema_version=metadata.producer_identity.schema_version,
            feature_schema_sha256=metadata.producer_identity.feature_schema_sha256,
            model_bundle_sha256=metadata.producer_identity.model_bundle_sha256,
            pitch_set_sha256_by_family=tuple(sorted(metadata.pitch_set_sha256_by_family.items())),
            scoring_population=metadata.scoring_population,
            as_of=metadata.as_of.isoformat(),
            temporal_holdout_year=metadata.split_policy.temporal_holdout_year,
            prediction_rows=metadata.row_counts.prediction_rows,
        )


@dataclass(frozen=True)
class ModelExplanation:
    """Reader-facing template plus the identities required to validate it."""

    mode_id: str
    template_id: str
    template_version: str
    semantic_schema_version: str
    producer_semantics: ProducerModelSemantics
    content: str
    calibration: CalibrationExplanationEvidence | None = None


def _calibration_paragraph(
    evidence: CalibrationExplanationEvidence | None,
) -> str:
    if evidence is None:
        return (
            "**Evaluation evidence.** No matching versioned model-evaluation artifact "
            "is available, so this explanation makes no confidence claim."
        )
    pitch_sets = ", ".join(f"{family}={sha256}" for family, sha256 in evidence.pitch_set_sha256_by_family)
    return (
        "**Evaluation evidence.** The producer evaluation artifact "
        f"(evaluation schema {evidence.evaluation_schema_version}, producer schema "
        f"{evidence.producer_schema_version}, model bundle "
        f"{evidence.model_bundle_sha256}, feature schema "
        f"{evidence.feature_schema_sha256}, as of {evidence.as_of}) covers "
        f"{evidence.prediction_rows:,} predictions from "
        f"{evidence.scoring_population}, with {evidence.temporal_holdout_year} "
        f"as the temporal holdout. Held-out pitch sets are bound by {pitch_sets}. "
        "This identifies evaluation provenance and population only; it does not "
        "support a causal explanation."
    )


def _inventory_paragraph(
    semantics: ProducerModelSemantics,
    calibration: CalibrationExplanationEvidence | None,
) -> str:
    grains = set(semantics.artifact_grains)
    if calibration is None:
        grains.discard("calibration")
    labels = [_ARTIFACT_LABELS.get(grain, grain) for grain in sorted(grains)]
    if not labels:
        return (
            "**Data boundary.** Raw Statcast enters PitchingPlus. Pitcher "
            "Narratives reads only that bundle. No optional artifact inventory "
            "was supplied for this explanation."
        )
    return (
        "**Data boundary.** Raw Statcast enters PitchingPlus. Pitcher Narratives "
        "reads only that bundle. The supplied artifact inventory "
        f"contains {', '.join(labels)}. Deterministic Narrative code may select, "
        "aggregate, compare, and label emitted facts; agents may interpret only "
        "cited facts."
    )


def _canonical_content(
    semantics: ProducerModelSemantics,
    calibration: CalibrationExplanationEvidence | None,
) -> str:
    return "\n\n".join(
        (
            "## How Pitching+ Works",
            (
                "**Supported producer semantics.** This explanation is bound to "
                f"producer schema {semantics.schema_version}, feature schema "
                f"{semantics.feature_schema_sha256}, and model bundle "
                f"{semantics.model_bundle_sha256}."
            ),
            (
                "Pitching+ converts predicted probabilities for 13 pitch outcomes "
                "into expected run value using count-specific run values. P models "
                "include realized plate location. Count-matched S models omit realized "
                "plate_x and plate_z while retaining the same count state as P. "
                "Location+ uses P expected run value minus count-matched S "
                "expected run value. P, S, and L are independently centered to that "
                "season's MLB regular-season pitch-weighted mean and mapped so 100 is "
                "average and higher is better. These are predictive grades, not "
                "causal feature attributions."
            ),
            (
                "**S and Location boundaries.** S is not pure velocity and movement "
                "or fully count-neutral: it includes release position and extension, "
                "arm angle, derived acceleration and spin coordinates, handedness and "
                "platoon context, fastball-velocity context, coarse repertoire shares, "
                "and count processing. Exported S evaluates its outcome probabilities "
                "and run values at the same actual count as P. Formal L uses that "
                "same-count S estimate. Location+ is an associative "
                "realized-location contrast, not command, control, target execution, "
                "intent, or a causal intervention."
            ),
            (
                "**Scale and aggregation.** Each variant's 100 anchor is its own "
                "same-scoring-season MLB regular-season pitch-weighted mean. The "
                "current 20-80 display is the uncapped plus grade minus 50; it is not "
                "standard-deviation scaled. Conditional expected rates are means of "
                "per-pitch ratios. Group grades have no model-level minimum sample or "
                "shrinkage, so sample size and supplied sufficiency remain part of any "
                "interpretation."
            ),
            (
                "**Direct-input limits.** The predictor does not directly use explicit "
                "pitch identity, player identity, sequence or tunnel geometry, target, "
                "park or weather, game state, observed batted-ball result, raw spin "
                "rate, or raw pfx movement fields. An aggregate that moves with a grade "
                "does not identify a model driver."
            ),
            _inventory_paragraph(semantics, calibration),
            _calibration_paragraph(calibration),
        )
    )


def _validate_calibration_binding(
    evidence: CalibrationExplanationEvidence | None,
    semantics: ProducerModelSemantics,
) -> None:
    if evidence is None:
        return
    pitch_sets = dict(evidence.pitch_set_sha256_by_family)
    expected_families = {
        "swing",
        "umpire",
        "contact",
        "bbe_specification",
        "final_outcome",
    }
    if (
        evidence.feature_schema_sha256 != semantics.feature_schema_sha256
        or evidence.model_bundle_sha256 != semantics.model_bundle_sha256
        or evidence.producer_schema_version != semantics.schema_version
        or "calibration" not in semantics.artifact_grains
        or set(pitch_sets) != expected_families
        or len(pitch_sets) != len(evidence.pitch_set_sha256_by_family)
        or any(
            len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256)
            for sha256 in pitch_sets.values()
        )
    ):
        raise ValueError("model-evaluation artifact does not match the producer semantic descriptor")


def render_model_explanation(
    mode_id: str,
    *,
    producer_semantics: ProducerModelSemantics | None = None,
    calibration: ModelEvaluationArtifact | None = None,
) -> ModelExplanation | None:
    """Render only when an explicitly supported producer descriptor is supplied."""
    if mode_id in _OMITTED_MODES:
        return None
    if mode_id not in _EXPLAINED_MODES:
        valid = ", ".join(sorted(_EXPLAINED_MODES | _OMITTED_MODES))
        raise ValueError(f"unknown narration mode {mode_id!r}; valid: {valid}")
    if producer_semantics is None or not producer_semantics.is_supported:
        return None
    evidence = CalibrationExplanationEvidence.from_artifact(calibration) if calibration is not None else None
    _validate_calibration_binding(evidence, producer_semantics)
    explanation = ModelExplanation(
        mode_id=mode_id,
        template_id=MODEL_EXPLANATION_TEMPLATE_ID,
        template_version=MODEL_EXPLANATION_TEMPLATE_VERSION,
        semantic_schema_version=MODEL_SEMANTIC_SCHEMA_VERSION,
        producer_semantics=producer_semantics,
        content=_canonical_content(producer_semantics, evidence),
        calibration=evidence,
    )
    return validate_model_explanation(explanation)


def validate_model_explanation(explanation: ModelExplanation) -> ModelExplanation:
    """Reject explanations not bound to the exact supported producer semantics."""
    if not isinstance(explanation, ModelExplanation):
        raise TypeError(f"model explanation must be ModelExplanation, got {type(explanation).__name__}")
    if explanation.semantic_schema_version != MODEL_SEMANTIC_SCHEMA_VERSION:
        raise ValueError(
            f"model explanation semantic schema is incompatible: {explanation.semantic_schema_version!r}"
        )
    if not explanation.producer_semantics.is_supported:
        raise ValueError("model explanation producer semantics are unsupported")
    _validate_calibration_binding(
        explanation.calibration,
        explanation.producer_semantics,
    )
    if (
        explanation.mode_id not in _EXPLAINED_MODES
        or explanation.template_id != MODEL_EXPLANATION_TEMPLATE_ID
        or explanation.template_version != MODEL_EXPLANATION_TEMPLATE_VERSION
        or explanation.content != _canonical_content(explanation.producer_semantics, explanation.calibration)
    ):
        raise ValueError("canonical model explanation identity or content is invalid")
    return explanation


def compose_model_explanation(
    narrative: str,
    explanation: ModelExplanation | None,
) -> str:
    """Attach a validated deterministic section outside the agent artifact."""
    if not isinstance(narrative, str):
        raise TypeError(f"narrative must be str, got {type(narrative).__name__}")
    if explanation is None:
        return narrative
    validated = validate_model_explanation(explanation)
    if not narrative.strip():
        return narrative
    return f"{narrative.rstrip()}\n\n{validated.content}"
