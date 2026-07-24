"""Consumer-owned validation contract for PitchingPlus output bundles."""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
DecimalPrecision = Literal["full"] | Annotated[StrictInt, Field(ge=0)]
_CALIBRATION_MODEL_FAMILIES = frozenset({"swing", "umpire", "contact", "bbe_specification", "final_outcome"})


class ProducerIdentity(BaseModel):
    """Exact feature-schema and model-bundle identities used for inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    feature_schema_sha256: Sha256
    model_bundle_sha256: Sha256


class MetricSemantics(BaseModel):
    """Meaning and aggregation contract for one emitted metric."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant: Literal["P", "S", "L", "observed", "derived"]
    s_product: Literal["count_marginalized", "count_matched"] | None = None
    domain: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    precision: DecimalPrecision
    benchmark: float | None = None
    higher_is_better: bool | None = None
    aggregation: str = Field(min_length=1)
    statistical_unit: str = Field(min_length=1)
    weighting: str = Field(min_length=1)
    count_treatment: str = Field(min_length=1)
    scoring_season: int = Field(ge=1900)
    reference_population: str = Field(min_length=1)


class ArtifactSemantics(BaseModel):
    """Natural key, columns, checksum, and metrics for one emitted file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    season: int = Field(ge=1900)
    grain: str = Field(min_length=1)
    natural_key: tuple[str, ...] = Field(min_length=1)
    required_columns: tuple[str, ...] = Field(min_length=1)
    metrics: dict[str, MetricSemantics]

    @field_validator("filename")
    @classmethod
    def validate_plain_filename(cls, value: str) -> str:
        if (
            value in {".", ".."}
            or "/" in value
            or "\\" in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("artifact filename must be a plain bundle-local filename")
        return value


class CalibrationArtifactSemantics(BaseModel):
    """Checksum and evaluation-population contract for calibration JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1)
    sha256: Sha256
    artifact_schema_version: Literal["1.0.0"]
    scoring_population: str = Field(min_length=1)
    dataset_years: tuple[int, ...] = Field(min_length=1)
    row_counts: dict[str, int]
    producer_identity: ProducerIdentity
    pitch_set_sha256_by_family: dict[str, Sha256]
    split_seed: int
    temporal_holdout_year: int = Field(ge=1900)
    validation_policy: str = Field(min_length=1)
    learned_artifacts_policy: str = Field(min_length=1)
    arm_angle_policy: Literal["observed_finite_only"]
    as_of: date

    @field_validator("filename")
    @classmethod
    def validate_plain_filename(cls, value: str) -> str:
        if (
            value in {".", ".."}
            or "/" in value
            or "\\" in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("calibration filename must be a plain bundle-local filename")
        return value

    @field_validator(
        "scoring_population",
        "validation_policy",
        "learned_artifacts_policy",
    )
    @classmethod
    def validate_single_line_provenance(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("calibration provenance must not contain control characters")
        return value

    @field_validator("pitch_set_sha256_by_family")
    @classmethod
    def validate_pitch_set_families(
        cls,
        value: dict[str, str],
    ) -> dict[str, str]:
        if set(value) != _CALIBRATION_MODEL_FAMILIES:
            raise ValueError("pitch-set identities must cover every model family")
        return value


class MetricSemanticsManifest(BaseModel):
    """Versioned semantic and integrity manifest accepted by Narratives."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"]
    producer: Literal["pitchingplus"]
    season: int = Field(ge=1900)
    producer_identity: ProducerIdentity
    artifacts: tuple[ArtifactSemantics, ...] = Field(min_length=1)
    calibration: CalibrationArtifactSemantics | None = None

    @model_validator(mode="after")
    def validate_seasons(self) -> MetricSemanticsManifest:
        for artifact in self.artifacts:
            if artifact.season != self.season:
                raise ValueError(
                    f"artifact season {artifact.season} does not match manifest season {self.season}"
                )
            for name, metric in artifact.metrics.items():
                if metric.scoring_season != self.season:
                    raise ValueError(
                        f"metric scoring season for {name} does not match manifest season {self.season}"
                    )
        return self


class ReliabilityBinRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    count: int = Field(ge=0)
    mean_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_frequency: float | None = Field(default=None, ge=0.0, le=1.0)


class CalibrationMetricsRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    n_observations: int = Field(gt=0)
    n_classes: int = Field(ge=2)
    log_loss: float = Field(ge=0.0)
    brier_score: float = Field(ge=0.0)
    empirical_prior_log_loss: float = Field(ge=0.0)
    log_loss_skill: float
    expected_calibration_error: float = Field(ge=0.0, le=1.0)
    reliability_bins: tuple[ReliabilityBinRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_metrics(self) -> CalibrationMetricsRow:
        previous_upper = 0.0
        for row in self.reliability_bins:
            if row.lower >= row.upper or not math.isclose(
                row.lower,
                previous_upper,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("reliability-bin bounds must be contiguous and ordered")
            if row.count == 0 and (row.mean_probability is not None or row.observed_frequency is not None):
                raise ValueError("empty reliability bins must have null frequencies")
            if row.count > 0 and (row.mean_probability is None or row.observed_frequency is None):
                raise ValueError("populated reliability bins require frequencies")
            if (
                row.count > 0
                and row.mean_probability is not None
                and not row.lower <= row.mean_probability <= row.upper
            ):
                raise ValueError("reliability-bin mean probability must lie within its bounds")
            previous_upper = row.upper
        if not math.isclose(
            previous_upper,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("reliability bins must cover zero through one")
        if sum(row.count for row in self.reliability_bins) != self.n_observations:
            raise ValueError("reliability-bin counts must sum to n_observations")
        expected_skill = self.empirical_prior_log_loss - self.log_loss
        if not math.isclose(
            self.log_loss_skill,
            expected_skill,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ValueError("log_loss_skill is inconsistent with its losses")
        expected_ece = (
            sum(
                row.count * abs(row.mean_probability - row.observed_frequency)
                for row in self.reliability_bins
                if row.count > 0 and row.mean_probability is not None and row.observed_frequency is not None
            )
            / self.n_observations
        )
        if not math.isclose(
            self.expected_calibration_error,
            expected_ece,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ValueError("expected_calibration_error is inconsistent with reliability bins")
        return self


class OmittedCalibrationStratum(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: Literal["pitch_type", "handedness"]
    value: str = Field(min_length=1)
    count: int = Field(ge=0, lt=1000)
    minimum: Literal[1000]
    reason: Literal["below_minimum_observations"]


class ModelCalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    overall: CalibrationMetricsRow
    strata: dict[str, dict[str, CalibrationMetricsRow]]
    omitted_strata: tuple[OmittedCalibrationStratum, ...]

    @model_validator(mode="after")
    def validate_strata(self) -> ModelCalibrationReport:
        if set(self.strata) != {"pitch_type", "handedness"}:
            raise ValueError("calibration strata must contain pitch_type and handedness")
        omitted_keys: set[tuple[str, str]] = set()
        omitted_counts: dict[str, int] = {}
        for omitted in self.omitted_strata:
            key = (omitted.dimension, omitted.value)
            if key in omitted_keys:
                raise ValueError("omitted calibration strata must be unique")
            if omitted.value in self.strata[omitted.dimension]:
                raise ValueError("a calibration stratum cannot be both scored and omitted")
            omitted_keys.add(key)
            omitted_counts[omitted.dimension] = omitted_counts.get(omitted.dimension, 0) + omitted.count
        for dimension, rows in self.strata.items():
            if any(row.n_classes != self.overall.n_classes for row in rows.values()):
                raise ValueError("stratum class counts must match overall model class count")
            if any(row.n_observations < 1000 for row in rows.values()):
                raise ValueError("scored calibration strata require 1,000 observations")
            represented = sum(row.n_observations for row in rows.values())
            represented += omitted_counts.get(dimension, 0)
            if represented != self.overall.n_observations:
                raise ValueError("scored and omitted strata must cover overall observations")
        return self


class EvaluationRowCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    training: int = Field(gt=0)
    pitcher_group_validation: int = Field(gt=0)
    temporal_holdout: int = Field(gt=0)
    prediction_rows: int = Field(gt=0)


class EvaluationSplitPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temporal_holdout_year: int = Field(ge=1900)
    validation: str = Field(min_length=1)
    learned_artifacts_fit_on: str = Field(min_length=1)
    arm_angle_policy: Literal["observed_finite_only"]

    @field_validator("validation", "learned_artifacts_fit_on")
    @classmethod
    def validate_single_line_policy(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("split-policy provenance must not contain control characters")
        return value


class EvaluationArtifactMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_years: tuple[int, ...] = Field(min_length=2)
    row_counts: EvaluationRowCounts
    producer_identity: ProducerIdentity
    pitch_set_sha256_by_family: dict[str, Sha256]
    split_seed: int
    split_policy: EvaluationSplitPolicy
    as_of: date
    scoring_population: str = Field(min_length=1)

    @field_validator("scoring_population")
    @classmethod
    def validate_single_line_provenance(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("calibration provenance must not contain control characters")
        return value

    @field_validator("pitch_set_sha256_by_family")
    @classmethod
    def validate_pitch_set_families(
        cls,
        value: dict[str, str],
    ) -> dict[str, str]:
        if set(value) != _CALIBRATION_MODEL_FAMILIES:
            raise ValueError("pitch-set identities must cover every model family")
        return value

    @model_validator(mode="after")
    def validate_latest_holdout(self) -> EvaluationArtifactMetadata:
        if tuple(sorted(set(self.dataset_years))) != self.dataset_years or any(
            year < 1900 for year in self.dataset_years
        ):
            raise ValueError("dataset years must be unique, sorted, and valid")
        if max(self.dataset_years) != self.split_policy.temporal_holdout_year:
            raise ValueError("temporal holdout must be the latest dataset year")
        return self


class ModelEvaluationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"]
    metadata: EvaluationArtifactMetadata
    models: dict[str, ModelCalibrationReport]

    @model_validator(mode="after")
    def validate_model_matrix(self) -> ModelEvaluationArtifact:
        expected = {
            f"{variant}.{family}"
            for variant in ("P", "S")
            for family in (
                "swing",
                "umpire",
                "contact",
                "bbe_specification",
                "final_outcome",
            )
        }
        if set(self.models) != expected:
            raise ValueError("calibration artifact must cover every P/S model family")
        expected_classes = {
            "swing": 2,
            "umpire": 3,
            "contact": 3,
            "final_outcome": 13,
        }
        for key, report in self.models.items():
            family = key.split(".", maxsplit=1)[1]
            required = expected_classes.get(family)
            if required is not None and report.overall.n_classes != required:
                raise ValueError(f"{key} requires exactly {required} outcome classes")
            overall = report.overall
            if overall.log_loss >= overall.empirical_prior_log_loss:
                raise ValueError(f"{key} does not beat its empirical-prior log-loss baseline")
        for family in (
            "swing",
            "umpire",
            "contact",
            "bbe_specification",
            "final_outcome",
        ):
            family_classes = {self.models[f"{variant}.{family}"].overall.n_classes for variant in ("P", "S")}
            if len(family_classes) != 1:
                raise ValueError(f"P/S {family} reports must use the same outcome classes")
            family_observations = {
                self.models[f"{variant}.{family}"].overall.n_observations for variant in ("P", "S")
            }
            if len(family_observations) != 1:
                raise ValueError(f"P/S {family} reports must cover the same observations")
        if (
            sum(report.overall.n_observations for report in self.models.values())
            != self.metadata.row_counts.prediction_rows
        ):
            raise ValueError("overall model observations must sum to prediction_rows")
        return self
