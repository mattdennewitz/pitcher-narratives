"""Deterministic capability gates for evidence-backed analysis claims."""

from __future__ import annotations

from dataclasses import dataclass, field

from pitcher_narratives.facts import (
    CLAIM_CAPABILITY_REQUIREMENTS,
    AnalysisClaim,
    ClaimType,
    FactKind,
    FactRegistry,
)

_CAPABILITY_FIELDS = (
    "feature_attribution",
    "location_regions",
    "pitch_targets",
    "biomechanical_causality",
    "tunneling_measurement",
    "platoon_splits",
)
_MODEL_DRIVER_LIMITATION = "The supplied aggregate profile does not identify the model driver."


@dataclass(frozen=True)
class AnalysisCapabilities:
    """Producer-backed evidence capabilities available to one handoff frame."""

    has_feature_attribution: bool = False
    has_location_regions: bool = False
    has_pitch_targets: bool = False
    has_biomechanical_causality: bool = False
    has_tunneling_measurement: bool = False
    has_platoon_splits: bool = False
    evidence_fact_ids: tuple[tuple[str, str], ...] = field(default=(), repr=False)

    @classmethod
    def from_registry(
        cls,
        registry: FactRegistry,
        *,
        frame_id: str,
    ) -> AnalysisCapabilities:
        values: dict[str, bool] = {}
        evidence: dict[str, str] = {}
        for capability in _CAPABILITY_FIELDS:
            candidates = tuple(
                fact
                for fact in registry.facts()
                if fact.frame_id == frame_id and fact.metric == f"capability.{capability}"
            )
            if len(candidates) > 1:
                raise ValueError(f"multiple capability facts registered for {capability}")
            if candidates:
                fact = candidates[0]
                if fact.kind is not FactKind.MODEL_SEMANTIC:
                    raise ValueError(f"capability fact {fact.id} must use MODEL_SEMANTIC kind")
                if type(fact.value) is not bool:
                    raise ValueError(f"capability fact {fact.id} must contain a boolean value")
                values[capability] = fact.value
                evidence[capability] = fact.id
            else:
                values[capability] = False
        return cls(
            has_feature_attribution=values["feature_attribution"],
            has_location_regions=values["location_regions"],
            has_pitch_targets=values["pitch_targets"],
            has_biomechanical_causality=values["biomechanical_causality"],
            has_tunneling_measurement=values["tunneling_measurement"],
            has_platoon_splits=values["platoon_splits"],
            evidence_fact_ids=tuple(sorted(evidence.items())),
        )

    def is_available(self, capability: str) -> bool:
        if capability not in _CAPABILITY_FIELDS:
            raise ValueError(f"unknown analysis capability {capability!r}")
        return bool(getattr(self, f"has_{capability}"))

    def evidence_fact_id(self, capability: str) -> str | None:
        return dict(self.evidence_fact_ids).get(capability)

    def render(self) -> str:
        """Render the machine-derived capability block included in every handoff."""
        lines = ["## Analysis Capabilities"]
        for capability in _CAPABILITY_FIELDS:
            state = "AVAILABLE" if self.is_available(capability) else "UNAVAILABLE"
            fact_id = self.evidence_fact_id(capability)
            citation = f" [{fact_id}]" if fact_id is not None else ""
            lines.append(f"- {capability}: {state}{citation}")
        return "\n".join(lines)


@dataclass(frozen=True)
class SpecialistAnalysis:
    """Structured specialist output separating evidence from interpretation."""

    observations: tuple[AnalysisClaim, ...]
    supported_interpretations: tuple[AnalysisClaim, ...]
    limitations: tuple[AnalysisClaim, ...]

    @property
    def claims(self) -> tuple[AnalysisClaim, ...]:
        return self.observations + self.supported_interpretations + self.limitations

    def validate(self, registry: FactRegistry) -> SpecialistAnalysis:
        for claim in self.claims:
            claim.validate(registry)
        return self


def _limitation_text(
    claim_type: ClaimType,
    capability: str,
    *,
    capability_available: bool,
) -> str:
    label = capability.replace("_", " ")
    if capability_available:
        return f"The required {label} capability fact was not cited; this claim was excluded."
    if claim_type is ClaimType.MODEL_DRIVER:
        return _MODEL_DRIVER_LIMITATION
    return f"The required {label} evidence is unavailable; this claim was excluded."


def _limitation_claim(
    rejected: AnalysisClaim,
    *,
    capability: str,
    evidence_fact_id: str,
    capability_available: bool,
    registry: FactRegistry,
) -> AnalysisClaim:
    return AnalysisClaim.create(
        text=_limitation_text(
            rejected.claim_type,
            capability,
            capability_available=capability_available,
        ),
        fact_ids=(evidence_fact_id,),
        frame_id=rejected.frame_id,
        manifest_version=rejected.manifest_version,
        fact_registry_version=registry.version,
        claim_type=ClaimType.MODEL_SEMANTIC,
        confidence="deterministic_policy",
    )


def enforce_analysis_capabilities(
    analysis: SpecialistAnalysis,
    capabilities: AnalysisCapabilities,
    registry: FactRegistry,
) -> SpecialistAnalysis:
    """Apply capability policy to interpretations and limitation claims alike."""
    analysis.validate(registry)
    accepted: list[AnalysisClaim] = []
    limitations: list[AnalysisClaim] = []

    def _append_limitation(rejected: AnalysisClaim, capability: str) -> None:
        evidence_fact_id = capabilities.evidence_fact_id(capability)
        if evidence_fact_id is None:
            raise ValueError(f"missing typed availability fact for required capability {capability}")
        limitation = _limitation_claim(
            rejected,
            capability=capability,
            capability_available=capabilities.is_available(capability),
            evidence_fact_id=evidence_fact_id,
            registry=registry,
        )
        if limitation.id not in {existing.id for existing in limitations}:
            limitations.append(limitation)

    for claim in analysis.supported_interpretations:
        capability = CLAIM_CAPABILITY_REQUIREMENTS.get(claim.claim_type)
        if capability is None:
            accepted.append(claim)
            continue
        evidence_fact_id = capabilities.evidence_fact_id(capability)
        if (
            capabilities.is_available(capability)
            and evidence_fact_id is not None
            and evidence_fact_id in claim.fact_ids
        ):
            accepted.append(claim)
        else:
            _append_limitation(claim, capability)

    for claim in analysis.limitations:
        capability = CLAIM_CAPABILITY_REQUIREMENTS.get(claim.claim_type)
        if capability is None:
            limitations.append(claim)
            continue
        evidence_fact_id = capabilities.evidence_fact_id(capability)
        if (
            capabilities.is_available(capability)
            and evidence_fact_id is not None
            and evidence_fact_id in claim.fact_ids
        ):
            limitations.append(claim)
        else:
            _append_limitation(claim, capability)

    bounded = SpecialistAnalysis(
        observations=analysis.observations,
        supported_interpretations=tuple(accepted),
        limitations=tuple(limitations),
    )
    return bounded.validate(registry)
