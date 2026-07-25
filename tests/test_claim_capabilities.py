from __future__ import annotations

import pytest

from pitcher_narratives.claims import (
    AnalysisCapabilities,
    SpecialistAnalysis,
    enforce_analysis_capabilities,
)
from pitcher_narratives.facts import AnalysisClaim, ClaimType, Fact, FactKind, FactRegistry

_MANIFEST = "pitchingplus:2026:1.0.0"
_FRAME = "recent:2026:592155:2026-07-01:101"
_SOURCE = "pitchingplus:all_pitches"


def _fact(
    *,
    metric: str,
    value: int | float | str | bool,
    row_id: str,
    kind: FactKind = FactKind.OBSERVED,
) -> Fact:
    return Fact.create(
        kind=kind,
        metric=metric,
        variant=None,
        entity="pitcher:592155",
        value=value,
        unit=None,
        frame_id=_FRAME,
        population="2026 MLB regular season",
        sample_size=20,
        sufficiency="available",
        source=_SOURCE,
        semantic_key=f"pitcher:592155|{metric}",
        manifest_version=_MANIFEST,
        source_row_id=row_id,
    )


def _registry(*, capability: str, available: bool) -> tuple[FactRegistry, Fact, Fact]:
    observation = _fact(metric="release_speed", value=96.1, row_id="pitch:1")
    capability_fact = _fact(
        metric=f"capability.{capability}",
        value=available,
        row_id=f"semantic:{capability}",
        kind=FactKind.MODEL_SEMANTIC,
    )
    registry = FactRegistry(
        manifest_version=_MANIFEST,
        manifest_rows={
            _SOURCE: {"pitch:1", f"semantic:{capability}"},
        },
    )
    registry.add(observation)
    registry.add(capability_fact)
    return registry, observation, capability_fact


def _claim(
    registry: FactRegistry,
    *,
    text: str,
    claim_type: ClaimType,
    fact_ids: tuple[str, ...],
) -> AnalysisClaim:
    return AnalysisClaim.create(
        text=text,
        fact_ids=fact_ids,
        frame_id=_FRAME,
        manifest_version=_MANIFEST,
        fact_registry_version=registry.version,
        claim_type=claim_type,
        confidence="bounded",
    )


def test_stuff_analysis_rejects_driver_claim_without_attribution() -> None:
    registry, velocity, capability_fact = _registry(
        capability="feature_attribution",
        available=False,
    )
    observation = _claim(
        registry,
        text="The four-seam averaged 96.1 mph.",
        claim_type=ClaimType.OBSERVATION,
        fact_ids=(velocity.id,),
    )
    driver = _claim(
        registry,
        text="Elite velocity drives the S+.",
        claim_type=ClaimType.MODEL_DRIVER,
        fact_ids=(velocity.id,),
    )
    analysis = SpecialistAnalysis(
        observations=(observation,),
        supported_interpretations=(driver,),
        limitations=(),
    )

    bounded = enforce_analysis_capabilities(
        analysis,
        AnalysisCapabilities.from_registry(registry, frame_id=_FRAME),
        registry,
    )

    assert bounded.observations == (observation,)
    assert bounded.supported_interpretations == ()
    assert len(bounded.limitations) == 1
    assert bounded.limitations[0].text == (
        "The supplied aggregate profile does not identify the model driver."
    )
    assert bounded.limitations[0].fact_ids == (capability_fact.id,)


@pytest.mark.parametrize(
    ("capability", "claim_type"),
    [
        ("tunneling_measurement", ClaimType.TUNNELING),
        ("tunneling_measurement", ClaimType.DECEPTION),
        ("pitch_targets", ClaimType.INTENT),
        ("pitch_targets", ClaimType.COMMAND),
        ("biomechanical_causality", ClaimType.BIOMECHANICAL),
        ("platoon_splits", ClaimType.PLATOON),
    ],
)
def test_claim_requires_matching_available_capability_and_citation(
    capability: str,
    claim_type: ClaimType,
) -> None:
    registry, observation, capability_fact = _registry(
        capability=capability,
        available=True,
    )
    capabilities = AnalysisCapabilities.from_registry(registry, frame_id=_FRAME)
    uncited = _claim(
        registry,
        text=f"Bounded {claim_type.value} claim.",
        claim_type=claim_type,
        fact_ids=(observation.id,),
    )
    cited = _claim(
        registry,
        text=f"Bounded {claim_type.value} claim.",
        claim_type=claim_type,
        fact_ids=(observation.id, capability_fact.id),
    )

    rejected = enforce_analysis_capabilities(
        SpecialistAnalysis((), (uncited,), ()),
        capabilities,
        registry,
    )
    accepted = enforce_analysis_capabilities(
        SpecialistAnalysis((), (cited,), ()),
        capabilities,
        registry,
    )

    assert rejected.supported_interpretations == ()
    assert rejected.limitations
    assert accepted.supported_interpretations == (cited,)
    assert accepted.limitations == ()


def test_runvalue_component_cannot_supply_physical_mechanism() -> None:
    registry, component, _ = _registry(
        capability="biomechanical_causality",
        available=False,
    )
    mechanism = _claim(
        registry,
        text="Called-ball value proves that he pulled off the pitch.",
        claim_type=ClaimType.BIOMECHANICAL,
        fact_ids=(component.id,),
    )

    bounded = enforce_analysis_capabilities(
        SpecialistAnalysis((), (mechanism,), ()),
        AnalysisCapabilities.from_registry(registry, frame_id=_FRAME),
        registry,
    )

    assert bounded.supported_interpretations == ()
    assert "unavailable" in bounded.limitations[0].text.lower()


def test_capability_fact_must_be_model_semantic() -> None:
    observed_capability = _fact(
        metric="capability.feature_attribution",
        value=True,
        row_id="semantic:feature_attribution",
    )
    registry = FactRegistry(
        manifest_version=_MANIFEST,
        manifest_rows={_SOURCE: {"semantic:feature_attribution"}},
    )
    registry.add(observed_capability)

    with pytest.raises(ValueError, match="MODEL_SEMANTIC"):
        AnalysisCapabilities.from_registry(registry, frame_id=_FRAME)
