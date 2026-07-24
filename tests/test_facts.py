from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pitcher_narratives.facts import (
    AnalysisClaim,
    ClaimType,
    Fact,
    FactKind,
    FactRegistry,
    NarrativeArtifact,
    NarrativeClaim,
)

MANIFEST_VERSION = "pitchingplus:semantic-manifest:2026:v1"
APPEARANCE_SOURCE = "pitchingplus:pitcher_type_appearance"
DERIVED_SOURCE = "pitcher_narratives:deterministic_transform"


def _registry(*row_ids: str, manifest_version: str = MANIFEST_VERSION) -> FactRegistry:
    return FactRegistry(
        manifest_version=manifest_version,
        manifest_rows={APPEARANCE_SOURCE: row_ids},
    )


def _base_fact(
    *,
    row_id: str = "appearance-1",
    frame_id: str = "frame:recent",
    manifest_version: str = MANIFEST_VERSION,
    metric: str = "xRV100_L",
    variant: str | None = "L",
    entity: str = "FF",
    value: float = -0.4,
    population: str = "season=2026;pitch_type=FF",
    sample_size: int = 20,
    sufficiency: str = "available",
    source: str = APPEARANCE_SOURCE,
) -> Fact:
    return Fact.create(
        kind=FactKind.MODEL_OUTPUT,
        metric=metric,
        variant=variant,
        entity=entity,
        value=value,
        unit="runs_per_100_pitches",
        frame_id=frame_id,
        population=population,
        sample_size=sample_size,
        sufficiency=sufficiency,
        source=source,
        source_row_id=row_id,
        semantic_key=f"{row_id}|metric={metric}",
        manifest_version=manifest_version,
    )


def _analysis_claim(
    registry: FactRegistry,
    fact: Fact,
    *,
    text: str = "The four-seamer prevented runs.",
) -> AnalysisClaim:
    return AnalysisClaim.create(
        text=text,
        fact_ids=(fact.id,),
        frame_id=fact.frame_id,
        manifest_version=fact.manifest_version,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
        confidence="high",
    )


def test_fact_identity_is_stable_and_roundtrips_without_losing_types() -> None:
    first = _base_fact()
    second = _base_fact()
    other_row = _base_fact(row_id="appearance-2", value=0.2, sample_size=10)

    derived_forward = Fact.create(
        kind=FactKind.COMPUTED,
        metric="xRV100_L",
        variant="L",
        entity="FF",
        value=-0.2,
        unit="runs_per_100_pitches",
        frame_id="frame:recent",
        population="season=2026;pitch_type=FF",
        sample_size=30,
        sufficiency="available",
        source=DERIVED_SOURCE,
        semantic_key="FF|weighted_xRV100_L",
        source_fact_ids=(first.id, other_row.id),
        transform="pitch_count_weighted_mean(xRV100_L)",
        manifest_version=MANIFEST_VERSION,
    )
    derived_reversed = Fact.create(
        kind=FactKind.COMPUTED,
        metric="xRV100_L",
        variant="L",
        entity="FF",
        value=-0.2,
        unit="runs_per_100_pitches",
        frame_id="frame:recent",
        population="season=2026;pitch_type=FF",
        sample_size=30,
        sufficiency="available",
        source=DERIVED_SOURCE,
        semantic_key="FF|weighted_xRV100_L",
        source_fact_ids=(other_row.id, first.id),
        transform="pitch_count_weighted_mean(xRV100_L)",
        manifest_version=MANIFEST_VERSION,
    )

    assert first.id == second.id
    assert derived_forward.id == derived_reversed.id
    assert Fact.from_dict(derived_forward.to_dict()) == derived_forward
    assert isinstance(Fact.from_dict(first.to_dict()).kind, FactKind)
    assert isinstance(Fact.from_dict(derived_forward.to_dict()).source_fact_ids, tuple)
    with pytest.raises(FrozenInstanceError):
        first.value = 2.0  # type: ignore[misc]

    for changed in (
        _base_fact(frame_id="frame:season"),
        _base_fact(metric="xRV100_P", variant="P"),
        _base_fact(entity="SL"),
        _base_fact(population="season=2026;pitch_type=SL"),
    ):
        assert changed.id != first.id


def test_registry_rejects_base_fact_outside_manifest_covered_pitchingplus_rows() -> None:
    registry = _registry("appearance-1")

    with pytest.raises(ValueError, match="manifest-covered PitchingPlus artifact row"):
        registry.add(_base_fact(source="statcast:raw_pitches"))
    with pytest.raises(ValueError, match="manifest-covered PitchingPlus artifact row"):
        registry.add(_base_fact(source="pitchingplus:unmanifested_table"))
    with pytest.raises(ValueError, match="manifest version"):
        _registry("appearance-1", manifest_version="").add(_base_fact(manifest_version=""))


def test_registry_rejects_source_less_derived_fact() -> None:
    registry = _registry("appearance-1")
    source_less = Fact.create(
        kind=FactKind.COMPUTED,
        metric="xRV100_L",
        variant="L",
        entity="FF",
        value=-0.4,
        unit="runs_per_100_pitches",
        frame_id="frame:recent",
        population="season=2026;pitch_type=FF",
        sample_size=20,
        sufficiency="available",
        source=DERIVED_SOURCE,
        semantic_key="FF|weighted_xRV100_L",
        transform="pitch_count_weighted_mean(xRV100_L)",
        manifest_version=MANIFEST_VERSION,
    )

    with pytest.raises(ValueError, match="upstream fact IDs"):
        registry.add(source_less)


def test_pitch_count_weighted_derivation_preserves_every_source_row_id() -> None:
    registry = _registry("appearance-1", "appearance-2")
    first = registry.add(_base_fact())
    second = registry.add(_base_fact(row_id="appearance-2", value=0.2, sample_size=10))
    derived = Fact.create(
        kind=FactKind.COMPUTED,
        metric="xRV100_L",
        variant="L",
        entity="FF",
        value=(-0.4 * 20 + 0.2 * 10) / 30,
        unit="runs_per_100_pitches",
        frame_id="frame:recent",
        population="season=2026;pitch_type=FF",
        sample_size=30,
        sufficiency="available",
        source=DERIVED_SOURCE,
        semantic_key="FF|weighted_xRV100_L",
        source_fact_ids=(second.id, first.id),
        transform="pitch_count_weighted_mean(xRV100_L)",
        manifest_version=MANIFEST_VERSION,
    )

    assert registry.add(derived) == derived
    assert derived.source_fact_ids == tuple(sorted((first.id, second.id)))
    assert {fact.source_row_id for fact in registry.base_lineage(derived.id)} == {
        "appearance-1",
        "appearance-2",
    }


def test_derived_fact_requires_registered_same_frame_and_manifest_lineage() -> None:
    registry = _registry("appearance-1")
    base = registry.add(_base_fact())

    for replacement, message in (
        ({"source_fact_ids": ("fact:missing",)}, "registered"),
        ({"frame_id": "frame:season"}, "same frame"),
        ({"manifest_version": "pitchingplus:semantic-manifest:2025:v1"}, "same manifest"),
        ({"transform": None}, "deterministic transform"),
    ):
        values = {
            "kind": FactKind.COMPUTED,
            "metric": "xRV100_L",
            "variant": "L",
            "entity": "FF",
            "value": -0.4,
            "unit": "runs_per_100_pitches",
            "frame_id": "frame:recent",
            "population": "season=2026;pitch_type=FF",
            "sample_size": 20,
            "sufficiency": "available",
            "source": DERIVED_SOURCE,
            "semantic_key": "FF|weighted_xRV100_L",
            "source_fact_ids": (base.id,),
            "transform": "pitch_count_weighted_mean(xRV100_L)",
            "manifest_version": MANIFEST_VERSION,
        }
        values.update(replacement)
        with pytest.raises(ValueError, match=message):
            registry.add(Fact.create(**values))


def test_registry_version_is_a_content_hash_independent_of_insertion_order() -> None:
    first = _base_fact()
    second = _base_fact(row_id="appearance-2", value=0.2, sample_size=10)
    forward = _registry("appearance-1", "appearance-2")
    reversed_registry = _registry("appearance-2", "appearance-1")
    for fact in (first, second):
        forward.add(fact)
    for fact in (second, first):
        reversed_registry.add(fact)

    assert forward.version == reversed_registry.version
    assert forward.version.startswith("facts:")
    changed = _registry("appearance-1", "appearance-2")
    changed.add(first)
    changed.add(_base_fact(row_id="appearance-2", value=0.3, sample_size=10))
    assert changed.version != forward.version


def test_analysis_claim_rejects_missing_unknown_and_insufficient_facts() -> None:
    registry = _registry("appearance-1", "appearance-2")
    supported = registry.add(_base_fact())
    insufficient = registry.add(
        _base_fact(
            row_id="appearance-2",
            sufficiency="insufficient",
            sample_size=2,
        )
    )

    valid = _analysis_claim(registry, supported)
    assert valid.validate(registry) == valid
    assert AnalysisClaim.from_dict(valid.to_dict()) == valid

    missing = AnalysisClaim.create(
        text="Unsupported direction.",
        fact_ids=(),
        frame_id=supported.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
        confidence="high",
    )
    unknown = AnalysisClaim.create(
        text="Unknown evidence.",
        fact_ids=("fact:unknown",),
        frame_id=supported.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
        confidence="high",
    )
    weak = _analysis_claim(registry, insufficient)

    with pytest.raises(ValueError, match="at least one fact"):
        missing.validate(registry)
    with pytest.raises(ValueError, match="unknown fact"):
        unknown.validate(registry)
    with pytest.raises(ValueError, match="insufficient"):
        weak.validate(registry)


def test_equal_value_from_wrong_frame_or_manifest_does_not_verify() -> None:
    registry = _registry("appearance-1", "appearance-season")
    correct = registry.add(_base_fact())
    wrong_frame = registry.add(_base_fact(row_id="appearance-season", frame_id="frame:season"))
    wrong_frame_claim = AnalysisClaim.create(
        text="The four-seamer prevented runs.",
        fact_ids=(wrong_frame.id,),
        frame_id=correct.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
        confidence="high",
    )
    with pytest.raises(ValueError, match="wrong frame"):
        wrong_frame_claim.validate(registry)

    other_manifest = "pitchingplus:semantic-manifest:2025:v1"
    stale_registry = _registry("appearance-1", manifest_version=other_manifest)
    equal_stale_fact = stale_registry.add(_base_fact(manifest_version=other_manifest))
    wrong_manifest_claim = AnalysisClaim.create(
        text="The four-seamer prevented runs.",
        fact_ids=(equal_stale_fact.id,),
        frame_id=equal_stale_fact.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=stale_registry.version,
        claim_type=ClaimType.DIRECTIONAL,
        confidence="high",
    )
    with pytest.raises(ValueError, match="wrong manifest"):
        wrong_manifest_claim.validate(stale_registry)


def test_writer_claims_require_same_frame_fact_citations() -> None:
    registry = _registry("recent-appearance", "prior-appearance")
    recent = registry.add(_base_fact(row_id="recent-appearance", frame_id="frame:recent"))
    prior = registry.add(
        _base_fact(
            row_id="prior-appearance",
            frame_id="frame:prior",
            value=0.2,
        )
    )
    source = _analysis_claim(registry, recent)
    writer_claim = NarrativeClaim.create(
        text="His prior-window four-seamer prevented runs.",
        fact_ids=(prior.id,),
        source_claim_ids=(source.id,),
        frame_id=recent.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
    )

    with pytest.raises(ValueError, match="wrong frame"):
        writer_claim.validate(registry, source_claims=(source,))


def test_claims_and_artifacts_have_deterministic_identity_and_content_hash() -> None:
    registry = _registry("appearance-1")
    fact = registry.add(_base_fact())
    analysis = _analysis_claim(registry, fact)
    writer_claim = NarrativeClaim.create(
        text="His four-seamer was a run-prevention strength.",
        fact_ids=(fact.id,),
        source_claim_ids=(analysis.id,),
        frame_id=fact.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
    )
    artifact = NarrativeArtifact.create(
        content="His four-seamer was a run-prevention strength.",
        claims=(writer_claim,),
        frame_id=fact.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
    )

    assert writer_claim == NarrativeClaim.from_dict(writer_claim.to_dict())
    assert writer_claim.validate(registry, source_claims=(analysis,)) == writer_claim
    assert artifact.validate(registry, source_claims=(analysis,)) == artifact
    assert artifact == NarrativeArtifact.from_dict(artifact.to_dict())
    assert (
        artifact.id
        == NarrativeArtifact.create(
            content=artifact.content,
            claims=artifact.claims,
            frame_id=artifact.frame_id,
            manifest_version=artifact.manifest_version,
            fact_registry_version=artifact.fact_registry_version,
        ).id
    )
    assert len(artifact.content_hash) == 64


def test_narrative_artifact_rejects_claim_text_absent_from_content() -> None:
    registry = _registry("appearance-1")
    fact = registry.add(_base_fact())
    analysis = _analysis_claim(registry, fact)
    omitted = NarrativeClaim.create(
        text="The four-seamer prevented runs.",
        fact_ids=(fact.id,),
        source_claim_ids=(analysis.id,),
        frame_id=fact.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
    )
    artifact = NarrativeArtifact.create(
        content="The slider led the outing.",
        claims=(omitted,),
        frame_id=fact.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
    )

    with pytest.raises(ValueError, match="claim text is absent"):
        artifact.validate(registry, source_claims=(analysis,))


def test_narrative_artifact_rejects_uncited_quantitative_statement() -> None:
    registry = _registry("appearance-1")
    fact = registry.add(_base_fact())
    analysis = _analysis_claim(registry, fact)
    cited = NarrativeClaim.create(
        text="The four-seamer prevented runs.",
        fact_ids=(fact.id,),
        source_claim_ids=(analysis.id,),
        frame_id=fact.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
    )
    artifact = NarrativeArtifact.create(
        content="The four-seamer prevented runs. Its velocity was 95 mph.",
        claims=(cited,),
        frame_id=fact.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
    )

    with pytest.raises(ValueError, match="reader statement lacks a claim"):
        artifact.validate(registry, source_claims=(analysis,))


def test_narrative_claim_rejects_evidence_not_present_in_its_source_claims() -> None:
    registry = _registry("appearance-1", "appearance-2")
    first = registry.add(_base_fact())
    second = registry.add(_base_fact(row_id="appearance-2", metric="L+", value=105.0))
    analysis = _analysis_claim(registry, first)
    unsupported = NarrativeClaim.create(
        text="The location grade was above average.",
        fact_ids=(second.id,),
        source_claim_ids=(analysis.id,),
        frame_id=first.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.COMPARATIVE,
    )

    with pytest.raises(ValueError, match="source claim evidence"):
        unsupported.validate(registry, source_claims=(analysis,))


def test_summary_can_only_cite_final_verified_capsule_claims() -> None:
    registry = _registry("appearance-1", "appearance-2")
    first = registry.add(_base_fact())
    second = registry.add(_base_fact(row_id="appearance-2", metric="L+", value=105.0))
    first_analysis = _analysis_claim(registry, first)
    second_analysis = _analysis_claim(
        registry,
        second,
        text="The four-seamer location grade was above average.",
    )
    capsule_claim = NarrativeClaim.create(
        text="The four-seamer prevented runs.",
        fact_ids=(first.id,),
        source_claim_ids=(first_analysis.id,),
        frame_id=first.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
    )
    capsule = NarrativeArtifact.create(
        content="The four-seamer prevented runs.",
        claims=(capsule_claim,),
        frame_id=first.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
    )
    capsule.validate(registry, source_claims=(first_analysis, second_analysis))

    summary_claim = NarrativeClaim.create(
        text="Four-seam run prevention led the outing.",
        fact_ids=(first.id,),
        source_claim_ids=(capsule_claim.id,),
        frame_id=first.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.DIRECTIONAL,
    )
    summary = NarrativeArtifact.create(
        content="- Four-seam run prevention led the outing.",
        claims=(summary_claim,),
        frame_id=first.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
    )
    assert summary.validate_summary(registry, capsule) == summary

    leaked_claim = NarrativeClaim.create(
        text="The location grade was above average.",
        fact_ids=(second.id,),
        source_claim_ids=(second_analysis.id,),
        frame_id=first.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
        claim_type=ClaimType.COMPARATIVE,
    )
    leaked_summary = NarrativeArtifact.create(
        content="- The location grade was above average.",
        claims=(leaked_claim,),
        frame_id=first.frame_id,
        manifest_version=MANIFEST_VERSION,
        fact_registry_version=registry.version,
    )
    with pytest.raises(ValueError, match="final verified capsule"):
        leaked_summary.validate_summary(registry, capsule)


@pytest.mark.parametrize(
    "claim_type",
    (
        "observation",
        "quantitative",
        "directional",
        "comparative",
        "spatial",
        "platoon",
        "value_component",
        "model_semantic",
        "model_driver",
        "tunneling",
        "deception",
        "intent",
        "command",
        "biomechanical",
    ),
)
def test_claim_types_are_a_closed_capability_set(claim_type: str) -> None:
    assert ClaimType(claim_type).value == claim_type

    with pytest.raises(ValueError):
        ClaimType(f"{claim_type}:unsupported")


def test_boolean_capability_fact_has_stable_identity_and_roundtrips_as_bool() -> None:
    capability = Fact.create(
        kind=FactKind.MODEL_SEMANTIC,
        metric="capability:model_driver",
        variant=None,
        entity="PitchingPlus",
        value=True,
        unit=None,
        frame_id="frame:recent",
        population="season=2026",
        sample_size=20,
        sufficiency="available",
        source=APPEARANCE_SOURCE,
        source_row_id="appearance-1",
        semantic_key="appearance-1|capability=model_driver",
        manifest_version=MANIFEST_VERSION,
    )

    restored = Fact.from_dict(capability.to_dict())
    assert restored == capability
    assert restored.value is True
    assert restored.id == capability.id


def test_explicit_comparison_accepts_mixed_frames_and_preserves_both_lineages() -> None:
    registry = _registry("recent-appearance", "prior-appearance")
    recent = registry.add(_base_fact(row_id="recent-appearance", frame_id="frame:recent"))
    prior = registry.add(
        _base_fact(
            row_id="prior-appearance",
            frame_id="frame:prior",
            value=0.2,
        )
    )
    comparison = Fact.create(
        kind=FactKind.COMPUTED,
        metric="xRV100_L_delta",
        variant="L",
        entity="FF",
        value=-0.6,
        unit="runs_per_100_pitches",
        frame_id="frame:recent-vs-prior",
        population="season=2026;pitch_type=FF",
        sample_size=40,
        sufficiency="available",
        source=DERIVED_SOURCE,
        semantic_key="FF|recent-vs-prior|xRV100_L_delta",
        source_fact_ids=(prior.id, recent.id),
        transform="comparison:delta",
        manifest_version=MANIFEST_VERSION,
    )

    assert registry.add(comparison) == comparison
    assert {fact.source_row_id for fact in registry.base_lineage(comparison.id)} == {
        "recent-appearance",
        "prior-appearance",
    }

    ordinary = Fact.create(
        kind=FactKind.COMPUTED,
        metric="xRV100_L",
        variant="L",
        entity="FF",
        value=-0.2,
        unit="runs_per_100_pitches",
        frame_id="frame:recent-vs-prior",
        population="season=2026;pitch_type=FF",
        sample_size=40,
        sufficiency="available",
        source=DERIVED_SOURCE,
        semantic_key="FF|invalid-mixed-frame-mean",
        source_fact_ids=(recent.id, prior.id),
        transform="pitch_count_weighted_mean(xRV100_L)",
        manifest_version=MANIFEST_VERSION,
    )
    with pytest.raises(ValueError, match="same frame"):
        registry.add(ordinary)


def test_model_semantic_capability_can_retain_producer_fact_lineage() -> None:
    registry = _registry("appearance-1")
    producer_fact = registry.add(_base_fact())
    capability = Fact.create(
        kind=FactKind.MODEL_SEMANTIC,
        metric="capability:model_driver",
        variant=None,
        entity="PitchingPlus",
        value=True,
        unit=None,
        frame_id=producer_fact.frame_id,
        population=producer_fact.population,
        sample_size=producer_fact.sample_size,
        sufficiency="available",
        source=DERIVED_SOURCE,
        semantic_key="capability=model_driver",
        source_fact_ids=(producer_fact.id,),
        transform="capability:model_driver_availability",
        manifest_version=MANIFEST_VERSION,
    )

    assert registry.add(capability) == capability
    assert registry.base_lineage(capability.id) == (producer_fact,)


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
def test_registry_rejects_non_finite_numeric_fact_values(value: float) -> None:
    registry = _registry("appearance-1")

    with pytest.raises(ValueError, match="finite"):
        registry.add(_base_fact(value=value))
