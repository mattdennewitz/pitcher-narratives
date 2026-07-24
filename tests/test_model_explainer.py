"""Deterministic reader-facing Pitching+ model explanation contract."""

from dataclasses import replace

import pytest

from pitcher_narratives.bundle_contract import ProducerIdentity
from pitcher_narratives.model_explainer import (
    MODEL_EXPLANATION_TEMPLATE_ID,
    MODEL_EXPLANATION_TEMPLATE_VERSION,
    CalibrationExplanationEvidence,
    ModelExplanation,
    ProducerModelSemantics,
    compose_model_explanation,
    render_model_explanation,
    validate_model_explanation,
)

_SUPPORTED = ProducerModelSemantics(
    schema_version="1.0.0",
    feature_schema_sha256="a" * 64,
    model_bundle_sha256="b" * 64,
    artifact_grains=frozenset({"all_pitches"}),
)


def _explanation(mode_id: str):
    return render_model_explanation(mode_id, producer_semantics=_SUPPORTED)


@pytest.mark.parametrize("mode_id", ["report", "changes", "ask"])
def test_model_explanation_retains_complete_semantics(mode_id: str) -> None:
    explanation = _explanation(mode_id)

    assert isinstance(explanation, ModelExplanation)
    assert explanation.template_id == MODEL_EXPLANATION_TEMPLATE_ID
    assert explanation.template_version == MODEL_EXPLANATION_TEMPLATE_VERSION
    assert explanation.semantic_schema_version == "1.0.0"
    for required in (
        "13 pitch outcomes",
        "count-specific run values",
        "P models include realized plate location",
        "Count-matched S models omit realized plate_x and plate_z",
        "retaining the same count state as P",
        "count-matched S expected run value",
        "independently centered",
        "100 is average and higher is better",
        "predictive grades, not causal feature attributions",
        "uncapped plus grade minus 50",
        "no model-level minimum sample or shrinkage",
        "Raw Statcast enters PitchingPlus",
        "Pitcher Narratives reads only that bundle",
    ):
        assert required in explanation.content
    assert validate_model_explanation(explanation) is explanation


def test_explanation_identity_is_copied_from_validated_producer_descriptor() -> None:
    identity = ProducerIdentity(
        feature_schema_sha256="c" * 64,
        model_bundle_sha256="d" * 64,
    )
    semantics = ProducerModelSemantics.from_identity(
        identity,
        artifact_grains=frozenset({"all_pitches"}),
    )

    explanation = render_model_explanation("report", producer_semantics=semantics)

    assert explanation is not None
    assert semantics.identity == ("1.0.0", "c" * 64, "d" * 64)
    assert "c" * 64 in explanation.content
    assert "d" * 64 in explanation.content


def test_optional_inventory_is_rendered_only_for_present_artifacts() -> None:
    semantics = replace(
        _SUPPORTED,
        artifact_grains=frozenset(
            {
                "all_pitches",
                "pitcher_relative_location",
                "pitcher_type_outcome_appearance",
                "calibration",
            }
        ),
    )

    explanation = render_model_explanation("report", producer_semantics=semantics)

    assert explanation is not None
    assert "spatial" in explanation.content
    assert "component-attribution" in explanation.content
    assert "calibration artifacts" not in explanation.content


def test_validation_rejects_forged_calibration_model_identity() -> None:
    explanation = _explanation("report")
    assert explanation is not None
    forged = CalibrationExplanationEvidence(
        evaluation_schema_version="1.0.0",
        producer_schema_version="1.0.0",
        feature_schema_sha256="a" * 64,
        model_bundle_sha256="c" * 64,
        pitch_set_sha256_by_family=tuple(
            (family, "d" * 64)
            for family in (
                "swing",
                "umpire",
                "contact",
                "bbe_specification",
                "final_outcome",
            )
        ),
        scoring_population="held-out pitches",
        as_of="2026-07-01",
        temporal_holdout_year=2025,
        prediction_rows=10_000,
    )

    with pytest.raises(ValueError, match="does not match"):
        validate_model_explanation(replace(explanation, calibration=forged))


def test_recap_intentionally_omits_model_explanation() -> None:
    assert render_model_explanation("recap") is None


def test_bare_grade_token_is_not_model_explanation() -> None:
    with pytest.raises(TypeError, match="ModelExplanation"):
        validate_model_explanation("His S+ is 92.")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "contradiction",
    [
        "S is count-neutral.",
        "Location+ is ordinary P minus S.",
        "All variants share one centering baseline.",
        "The grades identify causal model drivers.",
        "50 is the average grade.",
    ],
)
def test_modified_or_contradictory_template_is_rejected(contradiction: str) -> None:
    explanation = _explanation("report")
    assert explanation is not None
    corrupted = replace(explanation, content=contradiction)

    with pytest.raises(ValueError, match="canonical model explanation"):
        validate_model_explanation(corrupted)


def test_incompatible_template_identity_or_semantic_schema_is_rejected() -> None:
    explanation = _explanation("report")
    assert explanation is not None

    with pytest.raises(ValueError, match="canonical model explanation"):
        validate_model_explanation(replace(explanation, template_version="stale"))
    with pytest.raises(ValueError, match="semantic schema"):
        validate_model_explanation(replace(explanation, semantic_schema_version="2.0.0"))


def test_composition_keeps_deterministic_section_outside_generated_artifact() -> None:
    explanation = _explanation("report")
    assert explanation is not None

    rendered = compose_model_explanation("Grounded generated narrative.", explanation)

    assert rendered.startswith("Grounded generated narrative.\n\n## How Pitching+ Works")
    assert rendered.endswith(explanation.content.splitlines()[-1])


def test_composition_is_unchanged_when_explanation_is_disabled() -> None:
    assert compose_model_explanation("Grounded generated narrative.", None) == (
        "Grounded generated narrative."
    )


def test_composition_does_not_mask_an_unavailable_narrative() -> None:
    explanation = _explanation("report")
    assert explanation is not None

    assert compose_model_explanation("", explanation) == ""
