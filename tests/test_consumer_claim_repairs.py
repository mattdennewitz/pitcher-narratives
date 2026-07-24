from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

import pitcher_narratives.model_explainer as model_explainer
import pitcher_narratives.pipeline as pipeline_module
from pitcher_narratives.claim_guard import find_unsupported_claims
from pitcher_narratives.claims import (
    AnalysisCapabilities,
    SpecialistAnalysis,
    enforce_analysis_capabilities,
)
from pitcher_narratives.facts import (
    DERIVED_FACT_SOURCE,
    AnalysisClaim,
    ClaimType,
    Fact,
    FactKind,
    FactRegistry,
    NarrativeArtifact,
    NarrativeClaim,
)
from pitcher_narratives.frame_delta import build_trend_frame_comparison, render_trend_frame_comparison
from pitcher_narratives.models import ClaimDraft, SpecialistAnalysisDraft, SpecialistOutputs
from pitcher_narratives.personas import CHANGES, REPORT
from pitcher_narratives.pipeline import (
    PipelineResult,
    _materialize_specialist_draft,
    _publication_reader_guard_warnings,
    _render_fact_catalog,
    _render_specialist_evidence,
    _validate_key_signals,
    is_unverified,
    residual_banner,
)
from pitcher_narratives.signals import KeySignals, Signal, SignalState
from pitcher_narratives.temporal import TemporalFrame

MANIFEST = "pitchingplus:test:2026:v1"
SOURCE = "pitchingplus:all_pitches"
RECENT = "recent:test"
PRIOR = "prior:test"


def _registry(*row_ids: str) -> FactRegistry:
    return FactRegistry(manifest_version=MANIFEST, manifest_rows={SOURCE: row_ids})


def _fact(
    registry: FactRegistry,
    *,
    row_id: str,
    frame_id: str = RECENT,
    metric: str = "release_speed",
    value: bool | float | int | str = 95.0,
    kind: FactKind = FactKind.OBSERVED,
    entity: str = "FF",
) -> Fact:
    return registry.add(
        Fact.create(
            kind=kind,
            metric=metric,
            variant=None,
            entity=entity,
            value=value,
            unit=None,
            frame_id=frame_id,
            population=MANIFEST,
            sample_size=20,
            sufficiency="available",
            source=SOURCE,
            source_row_id=row_id,
            semantic_key=f"{row_id}|{metric}",
            manifest_version=MANIFEST,
        )
    )


def _analysis_claim(
    registry: FactRegistry,
    *,
    text: str,
    fact_ids: tuple[str, ...],
    claim_type: ClaimType = ClaimType.OBSERVATION,
    frame_id: str = RECENT,
) -> AnalysisClaim:
    return AnalysisClaim.create(
        text=text,
        fact_ids=fact_ids,
        frame_id=frame_id,
        manifest_version=MANIFEST,
        fact_registry_version=registry.version,
        claim_type=claim_type,
        confidence="bounded",
    )


def _narrative_claim(
    registry: FactRegistry,
    source: AnalysisClaim,
    *,
    text: str,
    fact_ids: tuple[str, ...],
    claim_type: ClaimType = ClaimType.OBSERVATION,
) -> NarrativeClaim:
    return NarrativeClaim.create(
        text=text,
        fact_ids=fact_ids,
        source_claim_ids=(source.id,),
        frame_id=RECENT,
        manifest_version=MANIFEST,
        fact_registry_version=registry.version,
        claim_type=claim_type,
    )


def _capability_fact(
    registry: FactRegistry,
    capability: str,
    *,
    available: bool,
    row_id: str,
) -> Fact:
    return _fact(
        registry,
        row_id=row_id,
        metric=f"capability.{capability}",
        value=available,
        kind=FactKind.MODEL_SEMANTIC,
        entity="PitchingPlus",
    )


def test_artifact_requires_full_statement_claim_not_substring() -> None:
    registry = _registry("metric")
    evidence = _fact(registry, row_id="metric")
    source = _analysis_claim(
        registry,
        text="The fastball is above average.",
        fact_ids=(evidence.id,),
        claim_type=ClaimType.COMPARATIVE,
    )
    partial = _narrative_claim(
        registry,
        source,
        text="The fastball is above average",
        fact_ids=(evidence.id,),
        claim_type=ClaimType.COMPARATIVE,
    )
    artifact = NarrativeArtifact.create(
        content="The fastball is above average and the slider is elite.",
        claims=(partial,),
        frame_id=RECENT,
        manifest_version=MANIFEST,
        fact_registry_version=registry.version,
    )

    with pytest.raises(ValueError, match="claim text is absent"):
        artifact.validate(registry, source_claims=(source,))


def test_artifact_requires_claim_for_assertion_without_selected_vocabulary() -> None:
    registry = _registry("metric")
    evidence = _fact(registry, row_id="metric")
    source = _analysis_claim(registry, text="Opening thought.", fact_ids=(evidence.id,))
    opening = _narrative_claim(
        registry,
        source,
        text="Opening thought.",
        fact_ids=(evidence.id,),
    )
    artifact = NarrativeArtifact.create(
        content="Opening thought. The slider is elite.",
        claims=(opening,),
        frame_id=RECENT,
        manifest_version=MANIFEST,
        fact_registry_version=registry.version,
    )

    with pytest.raises(ValueError, match="reader statement lacks a claim"):
        artifact.validate(registry, source_claims=(source,))


def test_narrative_claim_cannot_escalate_observation_to_command() -> None:
    registry = _registry("metric", "cap")
    evidence = _fact(registry, row_id="metric")
    capability = _capability_fact(
        registry,
        "pitch_targets",
        available=True,
        row_id="cap",
    )
    source = _analysis_claim(
        registry,
        text="The fastball averaged 95 mph.",
        fact_ids=(evidence.id, capability.id),
    )
    escalated = _narrative_claim(
        registry,
        source,
        text="He commanded the fastball.",
        fact_ids=(evidence.id, capability.id),
        claim_type=ClaimType.COMMAND,
    )

    with pytest.raises(ValueError, match="escalates source claim type"):
        escalated.validate(registry, source_claims=(source,))


def test_gated_narrative_claim_must_cite_available_capability_itself() -> None:
    registry = _registry("metric", "cap")
    evidence = _fact(registry, row_id="metric")
    capability = _capability_fact(
        registry,
        "pitch_targets",
        available=True,
        row_id="cap",
    )
    source = _analysis_claim(
        registry,
        text="He commanded the fastball.",
        fact_ids=(evidence.id, capability.id),
        claim_type=ClaimType.COMMAND,
    )
    uncited = _narrative_claim(
        registry,
        source,
        text="Fastball command held.",
        fact_ids=(evidence.id,),
        claim_type=ClaimType.COMMAND,
    )

    with pytest.raises(ValueError, match="exact available capability fact"):
        uncited.validate(registry, source_claims=(source,))


def test_guard_rejects_capability_language_masquerading_as_model_semantic() -> None:
    registry = _registry("metric", "cap")
    evidence = _fact(registry, row_id="metric")
    capability = _capability_fact(
        registry,
        "pitch_targets",
        available=True,
        row_id="cap",
    )
    source = _analysis_claim(
        registry,
        text="Pitch-target evidence is available.",
        fact_ids=(evidence.id, capability.id),
        claim_type=ClaimType.MODEL_SEMANTIC,
    )
    masquerading = _narrative_claim(
        registry,
        source,
        text="He commanded the fastball.",
        fact_ids=(evidence.id, capability.id),
        claim_type=ClaimType.MODEL_SEMANTIC,
    )
    masquerading.validate(registry, source_claims=(source,))

    warnings = find_unsupported_claims(
        (masquerading,),
        capabilities=AnalysisCapabilities.from_registry(registry, frame_id=RECENT),
    )

    assert len(warnings) == 1
    assert "misclassified command" in warnings[0]


def test_guard_rejects_elite_clause_masquerading_as_observation() -> None:
    registry = _registry("metric")
    evidence = _fact(registry, row_id="metric")
    source = _analysis_claim(
        registry,
        text="The fastball averaged 95 mph.",
        fact_ids=(evidence.id,),
    )
    masquerading = _narrative_claim(
        registry,
        source,
        text="The fastball averaged 95 mph, and the slider was elite.",
        fact_ids=(evidence.id,),
    )
    masquerading.validate(registry, source_claims=(source,))

    warnings = find_unsupported_claims((masquerading,))

    assert len(warnings) == 1
    assert "misclassified qualitative comparison" in warnings[0]


def test_guard_allows_elite_label_on_grounded_comparative_claim() -> None:
    registry = _registry("metric")
    evidence = _fact(registry, row_id="metric")
    source = _analysis_claim(
        registry,
        text="The pitch's grade was elite.",
        fact_ids=(evidence.id,),
        claim_type=ClaimType.COMPARATIVE,
    )
    grounded = _narrative_claim(
        registry,
        source,
        text="The fastball grade was elite.",
        fact_ids=(evidence.id,),
        claim_type=ClaimType.COMPARATIVE,
    )
    grounded.validate(registry, source_claims=(source,))

    assert find_unsupported_claims((grounded,)) == []


def test_capability_policy_replaces_affirmative_limitation_claim() -> None:
    registry = _registry("metric", "cap")
    evidence = _fact(registry, row_id="metric")
    capability = _capability_fact(
        registry,
        "pitch_targets",
        available=False,
        row_id="cap",
    )
    affirmative = _analysis_claim(
        registry,
        text="His command remained elite despite the limitation.",
        fact_ids=(evidence.id,),
        claim_type=ClaimType.COMMAND,
    )
    bounded = enforce_analysis_capabilities(
        SpecialistAnalysis((), (), (affirmative,)),
        AnalysisCapabilities.from_registry(registry, frame_id=RECENT),
        registry,
    )

    assert affirmative not in bounded.limitations
    assert len(bounded.limitations) == 1
    assert bounded.limitations[0].claim_type is ClaimType.MODEL_SEMANTIC
    assert bounded.limitations[0].fact_ids == (capability.id,)
    assert "unavailable" in bounded.limitations[0].text.lower()


def test_guard_checks_capability_citation_per_reader_claim() -> None:
    registry = _registry("metric", "cap")
    evidence = _fact(registry, row_id="metric")
    capability = _capability_fact(
        registry,
        "pitch_targets",
        available=True,
        row_id="cap",
    )
    source = _analysis_claim(
        registry,
        text="Command evidence.",
        fact_ids=(evidence.id, capability.id),
        claim_type=ClaimType.COMMAND,
    )
    cited = _narrative_claim(
        registry,
        source,
        text="Fastball command improved.",
        fact_ids=(evidence.id, capability.id),
        claim_type=ClaimType.COMMAND,
    )
    uncited = _narrative_claim(
        registry,
        source,
        text="Slider command improved.",
        fact_ids=(evidence.id,),
        claim_type=ClaimType.COMMAND,
    )
    capabilities = AnalysisCapabilities.from_registry(registry, frame_id=RECENT)

    warnings = find_unsupported_claims((cited, uncited), capabilities=capabilities)

    assert len(warnings) == 1
    assert "Slider command improved" in warnings[0]


def test_guard_does_not_apply_negation_from_an_unrelated_clause() -> None:
    registry = _registry("metric", "cap")
    evidence = _fact(registry, row_id="metric")
    _capability_fact(registry, "pitch_targets", available=False, row_id="cap")
    source = _analysis_claim(registry, text="Observed pitch shape.", fact_ids=(evidence.id,))
    claim = _narrative_claim(
        registry,
        source,
        text="The slider was not elite, while fastball command improved.",
        fact_ids=(evidence.id,),
    )

    warnings = find_unsupported_claims(
        (claim,),
        capabilities=AnalysisCapabilities.from_registry(registry, frame_id=RECENT),
    )

    assert warnings
    assert "command" in warnings[0]


def test_guard_does_not_apply_negation_across_coordinated_clause() -> None:
    registry = _registry("metric", "cap")
    evidence = _fact(registry, row_id="metric")
    _capability_fact(registry, "pitch_targets", available=False, row_id="cap")
    source = _analysis_claim(registry, text="Observed velocity.", fact_ids=(evidence.id,))
    claim = _narrative_claim(
        registry,
        source,
        text="He did not lose velocity and he commanded the zone.",
        fact_ids=(evidence.id,),
    )

    warnings = find_unsupported_claims(
        (claim,),
        capabilities=AnalysisCapabilities.from_registry(registry, frame_id=RECENT),
    )

    assert warnings
    assert "command" in warnings[0]


@dataclass
class _Pitch:
    pitch_name: str
    window_velo: float
    window_s_plus: float
    window_l_plus: float
    window_usage_pct: float
    n_pitches_window: int


@dataclass
class _Release:
    pitch_types: list[object]


@dataclass
class _DeltaContext:
    arsenal: list[_Pitch]
    frame_type: TemporalFrame
    frame_id: str
    facts: FactRegistry
    fact_ids: dict[str, str]
    release_point: _Release
    source_population: str = MANIFEST
    as_of: date = date(2026, 7, 1)
    frame_row_count: int = 40


def _delta_context(frame_id: str, frame_type: TemporalFrame, *, velocity: float) -> _DeltaContext:
    row_ids = tuple(f"{frame_id}:{name}" for name in ("velo", "s", "l", "usage", "count"))
    registry = _registry(*row_ids)
    values = {
        "window_velo": velocity,
        "window_s_plus": 105.0,
        "window_l_plus": 101.0,
        "window_usage_pct": 55.0,
        "n_pitches_window": 40,
    }
    fact_ids = {
        f"arsenal[0].{name}": _fact(
            registry,
            row_id=row_id,
            frame_id=frame_id,
            metric=name,
            value=value,
        ).id
        for (name, value), row_id in zip(values.items(), row_ids, strict=True)
    }
    return _DeltaContext(
        arsenal=[_Pitch("Four-Seam", velocity, 105.0, 101.0, 55.0, 40)],
        frame_type=frame_type,
        frame_id=frame_id,
        facts=registry,
        fact_ids=fact_ids,
        release_point=_Release([]),
    )


def test_two_mode_run_keeps_earlier_artifact_registry_binding(monkeypatch) -> None:
    recent = _delta_context(RECENT, TemporalFrame.RECENT, velocity=95.0)
    prior = _delta_context(PRIOR, TemporalFrame.PRIOR, velocity=93.0)
    source_claims: dict[str, tuple[AnalysisClaim, ...]] = {}

    def _generate(ctx, *, mode, **_kwargs):
        fact_id = ctx.fact_ids["arsenal[0].window_velo"]
        text = f"{mode.id} velocity evidence."
        source = AnalysisClaim.create(
            text=text,
            fact_ids=(fact_id,),
            frame_id=ctx.frame_id,
            manifest_version=ctx.source_population,
            fact_registry_version=ctx.facts.version,
            claim_type=ClaimType.OBSERVATION,
            confidence="observed",
        )
        claim = NarrativeClaim.create(
            text=text,
            fact_ids=(fact_id,),
            source_claim_ids=(source.id,),
            frame_id=ctx.frame_id,
            manifest_version=ctx.source_population,
            fact_registry_version=ctx.facts.version,
            claim_type=ClaimType.OBSERVATION,
        )
        artifact = NarrativeArtifact.create(
            content=text,
            claims=(claim,),
            frame_id=ctx.frame_id,
            manifest_version=ctx.source_population,
            fact_registry_version=ctx.facts.version,
        )
        source_claims[mode.id] = (source,)
        return PipelineResult(
            narrative=text,
            specialists=SpecialistOutputs(),
            narrative_artifact=artifact,
        )

    monkeypatch.setattr(pipeline_module, "generate_pipeline_streaming", _generate)

    results = pipeline_module.run_narration_modes(
        recent,
        modes=[REPORT, CHANGES],
        prior_ctx=prior,
        explain_model=False,
    )

    for mode_id, result in results.items():
        assert result.narrative_artifact is not None
        result.narrative_artifact.validate(
            recent.facts,
            source_claims=source_claims[mode_id],
        )


def test_trend_delta_registers_exact_cross_frame_facts_and_renders_ids() -> None:
    recent = _delta_context(RECENT, TemporalFrame.RECENT, velocity=95.0)
    prior = _delta_context(PRIOR, TemporalFrame.PRIOR, velocity=93.0)

    comparison = build_trend_frame_comparison(recent, prior)
    delta = comparison.deltas[0]

    assert delta.fact_ids
    velocity_fact = next(
        recent.facts.get(fact_id)
        for fact_id in delta.fact_ids
        if recent.facts.get(fact_id).metric == "trend.velocity_delta"
    )
    assert velocity_fact.value == 2.0
    assert velocity_fact.frame_id == RECENT
    assert velocity_fact.transform == "comparison:delta"
    assert set(velocity_fact.source_fact_ids) == {
        recent.fact_ids["arsenal[0].window_velo"],
        prior.fact_ids["arsenal[0].window_velo"],
    }
    assert {fact.frame_id for fact in recent.facts.base_lineage(velocity_fact.id)} == {
        RECENT,
        PRIOR,
    }
    rendered = render_trend_frame_comparison(comparison)
    assert f"[{velocity_fact.id}]" in rendered


def test_trends_reject_comparative_claim_without_comparison_fact() -> None:
    capabilities = (
        "feature_attribution",
        "location_regions",
        "pitch_targets",
        "biomechanical_causality",
        "tunneling_measurement",
        "platoon_splits",
    )
    row_ids = ("metric", *(f"cap:{name}" for name in capabilities))
    registry = _registry(*row_ids)
    evidence = _fact(registry, row_id="metric")
    for capability in capabilities:
        _capability_fact(
            registry,
            capability,
            available=False,
            row_id=f"cap:{capability}",
        )
    draft = SpecialistAnalysisDraft(
        observations=(
            ClaimDraft(
                text="Velocity improved from the prior window.",
                fact_ids=(evidence.id,),
                claim_type=ClaimType.COMPARATIVE,
                confidence="bounded",
            ),
        )
    )

    with pytest.raises(ValueError, match="recent-vs-prior comparison fact"):
        _materialize_specialist_draft(
            draft,
            specialist="trends",
            registry=registry,
            frame_id=RECENT,
        )


def test_trends_accept_comparative_claim_with_exact_comparison_fact() -> None:
    recent = _delta_context(RECENT, TemporalFrame.RECENT, velocity=95.0)
    prior = _delta_context(PRIOR, TemporalFrame.PRIOR, velocity=93.0)
    comparison = build_trend_frame_comparison(recent, prior)
    velocity_fact = next(
        recent.facts.get(fact_id)
        for fact_id in comparison.deltas[0].fact_ids
        if recent.facts.get(fact_id).metric == "trend.velocity_delta"
    )
    capabilities = (
        "feature_attribution",
        "location_regions",
        "pitch_targets",
        "biomechanical_causality",
        "tunneling_measurement",
        "platoon_splits",
    )
    capability_registry = _registry(*(f"cap:{name}" for name in capabilities))
    for capability in capabilities:
        _capability_fact(
            capability_registry,
            capability,
            available=False,
            row_id=f"cap:{capability}",
        )
    recent.facts.merge(capability_registry)
    draft = SpecialistAnalysisDraft(
        observations=(
            ClaimDraft(
                text="Velocity improved by 2 mph from the prior window.",
                fact_ids=(velocity_fact.id,),
                claim_type=ClaimType.COMPARATIVE,
                confidence="bounded",
            ),
        )
    )

    analysis = _materialize_specialist_draft(
        draft,
        specialist="trends",
        registry=recent.facts,
        frame_id=RECENT,
    )

    assert analysis.observations[0].fact_ids == (velocity_fact.id,)


def test_fact_catalog_serializes_only_exposed_roots_not_base_lineage() -> None:
    registry = _registry("base", "unrelated")
    base = _fact(registry, row_id="base", metric="release_speed")
    unrelated = _fact(registry, row_id="unrelated", metric="all_pitches.spin_rate")
    root = registry.add(
        Fact.create(
            kind=FactKind.COMPUTED,
            metric="context.window_velo",
            variant=None,
            entity="FF",
            value=95.0,
            unit="mph",
            frame_id=RECENT,
            population=MANIFEST,
            sample_size=20,
            sufficiency="available",
            source=DERIVED_FACT_SOURCE,
            source_fact_ids=(base.id,),
            transform="mean(release_speed)",
            semantic_key="arsenal[0].window_velo",
            manifest_version=MANIFEST,
        )
    )

    rendered = _render_fact_catalog(registry, fact_ids=(root.id,))

    assert root.id in rendered
    assert base.id not in rendered
    assert unrelated.id not in rendered


def test_specialist_catalog_excludes_unsurfaced_all_pitches_lineage() -> None:
    capabilities = (
        "feature_attribution",
        "location_regions",
        "pitch_targets",
        "biomechanical_causality",
        "tunneling_measurement",
        "platoon_splits",
    )
    registry = _registry(
        "base",
        "unrelated",
        "calibration-s",
        "calibration-p",
        "calibration-metadata",
        *(f"cap:{name}" for name in capabilities),
    )
    base = _fact(registry, row_id="base", metric="release_speed")
    unrelated = _fact(
        registry,
        row_id="unrelated",
        metric="all_pitches.spin_rate",
    )
    calibration_s = _fact(
        registry,
        row_id="calibration-s",
        metric="calibration.S.swing.overall.log_loss",
        value=0.42,
    )
    calibration_p = _fact(
        registry,
        row_id="calibration-p",
        metric="calibration.P.swing.overall.log_loss",
        value=0.39,
    )
    calibration_metadata = _fact(
        registry,
        row_id="calibration-metadata",
        metric="calibration.metadata.prediction_rows",
        value=10_000,
    )
    root = registry.add(
        Fact.create(
            kind=FactKind.COMPUTED,
            metric="context.window_velo",
            variant=None,
            entity="FF",
            value=95.0,
            unit="mph",
            frame_id=RECENT,
            population=MANIFEST,
            sample_size=20,
            sufficiency="available",
            source=DERIVED_FACT_SOURCE,
            source_fact_ids=(base.id,),
            transform="mean(release_speed)",
            semantic_key="arsenal[0].window_velo",
            manifest_version=MANIFEST,
        )
    )
    for capability in capabilities:
        _capability_fact(
            registry,
            capability,
            available=False,
            row_id=f"cap:{capability}",
        )
    ctx = SimpleNamespace(
        facts=registry,
        frame_id=RECENT,
        fact_ids={
            "arsenal[0].window_velo": root.id,
            calibration_s.metric: calibration_s.id,
            calibration_p.metric: calibration_p.id,
            calibration_metadata.metric: calibration_metadata.id,
        },
    )

    rendered = _render_specialist_evidence(
        ctx,
        specialist="stuff",
        surfaced_text="",
    )

    assert root.id in rendered
    assert base.id not in rendered
    assert unrelated.id not in rendered
    assert calibration_s.id in rendered
    assert calibration_metadata.id in rendered
    assert calibration_p.id not in rendered


def test_key_signal_rejects_invented_comparison_population() -> None:
    registry = _registry("metric")
    fact = _fact(registry, row_id="metric")
    source = _analysis_claim(
        registry,
        text="Velocity changed.",
        fact_ids=(fact.id,),
    )
    specialists = SpecialistOutputs(
        stuff=SpecialistAnalysis(
            observations=(source,),
            supported_interpretations=(),
            limitations=(),
        ),
    )
    signals = KeySignals(
        state=SignalState.MATERIAL,
        top_improvement=Signal(
            text="Velocity improved.",
            fact_ids=(fact.id,),
            source_claim_ids=(source.id,),
            sample_size=fact.sample_size or 0,
            comparison_population="league average",
        ),
    )

    with pytest.raises(ValueError, match="exact comparison population"):
        _validate_key_signals(
            signals,
            specialists=specialists,
            registry=registry,
            frame_id=RECENT,
        )


def test_key_signal_rejects_mixed_cited_fact_populations() -> None:
    registry = _registry("metric", "other")
    first = _fact(registry, row_id="metric")
    second = registry.add(
        Fact.create(
            kind=FactKind.OBSERVED,
            metric="release_extension",
            variant=None,
            entity="FF",
            value=6.5,
            unit="ft",
            frame_id=RECENT,
            population="different held-out population",
            sample_size=20,
            sufficiency="available",
            source=SOURCE,
            source_row_id="other",
            semantic_key="other|release_extension",
            manifest_version=MANIFEST,
        )
    )
    source = _analysis_claim(
        registry,
        text="Velocity and extension changed.",
        fact_ids=(first.id, second.id),
    )
    specialists = SpecialistOutputs(
        stuff=SpecialistAnalysis(
            observations=(source,),
            supported_interpretations=(),
            limitations=(),
        ),
    )
    signals = KeySignals(
        state=SignalState.MATERIAL,
        top_improvement=Signal(
            text="The delivery changed.",
            fact_ids=(first.id, second.id),
            source_claim_ids=(source.id,),
            sample_size=20,
            comparison_population=MANIFEST,
        ),
    )

    with pytest.raises(ValueError, match="share its exact comparison population"):
        _validate_key_signals(
            signals,
            specialists=specialists,
            registry=registry,
            frame_id=RECENT,
        )


def test_generated_summary_claim_guard_gates_unknown_metric_and_causal_driver() -> None:
    registry = _registry("metric")
    fact = _fact(registry, row_id="metric")
    source = _analysis_claim(
        registry,
        text="Velocity held.",
        fact_ids=(fact.id,),
    )
    capsule_claim = _narrative_claim(
        registry,
        source,
        text="Velocity held.",
        fact_ids=(fact.id,),
    )
    capsule = NarrativeArtifact.create(
        content=capsule_claim.text,
        claims=(capsule_claim,),
        frame_id=RECENT,
        manifest_version=MANIFEST,
        fact_registry_version=registry.version,
    )
    summary_claim = _narrative_claim(
        registry,
        source,
        text="xMagic rose because velocity drove success.",
        fact_ids=(fact.id,),
    )
    summary = NarrativeArtifact.create(
        content=summary_claim.text,
        claims=(summary_claim,),
        frame_id=RECENT,
        manifest_version=MANIFEST,
        fact_registry_version=registry.version,
    )

    warnings = _publication_reader_guard_warnings(
        capsule=capsule.content,
        capsule_artifact=capsule,
        summary_artifact=summary,
        capabilities=AnalysisCapabilities(),
    )
    result = PipelineResult(
        narrative=capsule.content,
        specialists=SpecialistOutputs(),
        reader_claim_warnings=warnings,
        narrative_artifact=capsule,
        summary_artifact=summary,
    )

    assert any(warning == "[summary] Unknown metric: xMagic" for warning in warnings)
    assert any(warning.startswith("[summary] misclassified model-driver") for warning in warnings)
    assert is_unverified(result)


def _supported_semantics(*artifacts: str):
    return model_explainer.ProducerModelSemantics(
        schema_version="1.0.0",
        feature_schema_sha256="a" * 64,
        model_bundle_sha256="b" * 64,
        artifact_grains=frozenset(artifacts),
    )


def test_model_explanation_omits_without_supported_semantic_descriptor() -> None:
    assert model_explainer.render_model_explanation("report") is None
    unsupported = model_explainer.ProducerModelSemantics(
        schema_version="1.0.0",
        feature_schema_sha256="a" * 64,
        model_bundle_sha256="not-a-sha256",
    )
    assert model_explainer.render_model_explanation("report", producer_semantics=unsupported) is None


def test_model_explanation_is_bound_and_inventory_is_conditional() -> None:
    explanation = model_explainer.render_model_explanation(
        "report",
        producer_semantics=_supported_semantics("all_pitches", "pitcher_type_appearance"),
    )

    assert explanation is not None
    assert explanation.producer_semantics == _supported_semantics("all_pitches", "pitcher_type_appearance")
    assert "all_pitches" in explanation.content
    assert "spatial" not in explanation.content
    assert "component-attribution" not in explanation.content
    assert "calibration artifacts" not in explanation.content
    assert model_explainer.validate_model_explanation(explanation) is explanation


def test_unresolved_specialist_state_gates_publication() -> None:
    result = PipelineResult(
        narrative="Grounded narrative.",
        specialists=SpecialistOutputs(),
        residual_specialists=["stuff"],
    )

    assert is_unverified(result) is True
    assert "unresolved specialist" in (residual_banner(result) or "").lower()
