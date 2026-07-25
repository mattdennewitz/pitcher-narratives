"""Typed, deterministic evidence facts used by narrative analysis."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from pitcher_narratives.bundle_contract import ModelEvaluationArtifact

DERIVED_FACT_SOURCE = "pitcher_narratives:deterministic_transform"
_PITCHINGPLUS_SOURCE = re.compile(r"pitchingplus:[a-z0-9][a-z0-9_]*\Z")
_COMPARISON_TRANSFORM = re.compile(r"comparison:(?:delta|difference|ratio|percent_change)\Z")
_SUPPORTED_SUFFICIENCY = frozenset({"available", "sufficient", "held_out"})
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _reader_statements(content: str) -> tuple[str, ...]:
    """Return every non-presentation reader assertion in normalized form."""
    statements: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith("#")
            or re.fullmatch(r"(?:[-*_]\s*){3,}", line)
            or re.fullmatch(r"\|?(?:\s*:?-+:?\s*\|)+", line)
        ):
            continue
        line = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", line)
        statements.extend(
            normalized
            for sentence in _SENTENCE_BOUNDARY.split(line)
            if (normalized := _normalize_statement(sentence))
        )
    return tuple(statements)


def _normalize_statement(text: str) -> str:
    """Normalize presentation markup without weakening statement boundaries."""
    normalized = re.sub(r"[*_`]+", "", text)
    return " ".join(normalized.split()).strip()


def _digest(prefix: str, value: object, *, length: int | None = None) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{prefix}:{digest[:length] if length is not None else digest}"


class FactKind(StrEnum):
    OBSERVED = "observed"
    COMPUTED = "computed"
    MODEL_OUTPUT = "model_output"
    MODEL_SEMANTIC = "model_semantic"


class ClaimType(StrEnum):
    OBSERVATION = "observation"
    QUANTITATIVE = "quantitative"
    DIRECTIONAL = "directional"
    COMPARATIVE = "comparative"
    SPATIAL = "spatial"
    PLATOON = "platoon"
    VALUE_COMPONENT = "value_component"
    MODEL_SEMANTIC = "model_semantic"
    MODEL_DRIVER = "model_driver"
    TUNNELING = "tunneling"
    DECEPTION = "deception"
    INTENT = "intent"
    COMMAND = "command"
    BIOMECHANICAL = "biomechanical"
    CAUSAL = "causal"


CLAIM_CAPABILITY_REQUIREMENTS = MappingProxyType(
    {
        ClaimType.MODEL_DRIVER: "feature_attribution",
        ClaimType.SPATIAL: "location_regions",
        ClaimType.PLATOON: "platoon_splits",
        ClaimType.TUNNELING: "tunneling_measurement",
        ClaimType.DECEPTION: "tunneling_measurement",
        ClaimType.INTENT: "pitch_targets",
        ClaimType.COMMAND: "pitch_targets",
        ClaimType.BIOMECHANICAL: "biomechanical_causality",
        ClaimType.CAUSAL: "biomechanical_causality",
    }
)

NARRATIVE_CLAIM_TRANSITIONS = MappingProxyType(
    {
        ClaimType.OBSERVATION: frozenset({ClaimType.OBSERVATION}),
        ClaimType.QUANTITATIVE: frozenset({ClaimType.OBSERVATION, ClaimType.QUANTITATIVE}),
        ClaimType.DIRECTIONAL: frozenset({ClaimType.OBSERVATION, ClaimType.DIRECTIONAL}),
        ClaimType.COMPARATIVE: frozenset(
            {
                ClaimType.OBSERVATION,
                ClaimType.DIRECTIONAL,
                ClaimType.COMPARATIVE,
            }
        ),
        ClaimType.SPATIAL: frozenset({ClaimType.OBSERVATION, ClaimType.SPATIAL}),
        ClaimType.PLATOON: frozenset({ClaimType.OBSERVATION, ClaimType.PLATOON}),
        ClaimType.VALUE_COMPONENT: frozenset({ClaimType.OBSERVATION, ClaimType.VALUE_COMPONENT}),
        ClaimType.MODEL_SEMANTIC: frozenset({ClaimType.OBSERVATION, ClaimType.MODEL_SEMANTIC}),
        ClaimType.MODEL_DRIVER: frozenset(
            {
                ClaimType.OBSERVATION,
                ClaimType.MODEL_SEMANTIC,
                ClaimType.MODEL_DRIVER,
            }
        ),
        ClaimType.TUNNELING: frozenset({ClaimType.OBSERVATION, ClaimType.TUNNELING}),
        ClaimType.DECEPTION: frozenset({ClaimType.OBSERVATION, ClaimType.DECEPTION}),
        ClaimType.INTENT: frozenset({ClaimType.OBSERVATION, ClaimType.INTENT}),
        ClaimType.COMMAND: frozenset({ClaimType.OBSERVATION, ClaimType.COMMAND}),
        ClaimType.BIOMECHANICAL: frozenset({ClaimType.OBSERVATION, ClaimType.BIOMECHANICAL}),
        ClaimType.CAUSAL: frozenset({ClaimType.OBSERVATION, ClaimType.DIRECTIONAL, ClaimType.CAUSAL}),
    }
)


@dataclass(frozen=True)
class Fact:
    id: str
    kind: FactKind
    metric: str
    variant: str | None
    entity: str
    value: bool | int | float | str | None
    unit: str | None
    frame_id: str
    population: str
    sample_size: int | None
    sufficiency: str
    source: str
    source_fact_ids: tuple[str, ...] = ()
    transform: str | None = None
    manifest_version: str | None = None
    source_row_id: str | None = None
    semantic_key: str = ""

    @classmethod
    def create(
        cls,
        *,
        kind: FactKind,
        metric: str,
        variant: str | None,
        entity: str,
        value: bool | int | float | str | None,
        unit: str | None,
        frame_id: str,
        population: str,
        sample_size: int | None,
        sufficiency: str,
        source: str,
        semantic_key: str,
        source_fact_ids: Iterable[str] = (),
        transform: str | None = None,
        manifest_version: str | None = None,
        source_row_id: str | None = None,
    ) -> Fact:
        upstream = tuple(sorted(source_fact_ids))
        identity = cls._identity(
            kind=kind,
            metric=metric,
            variant=variant,
            entity=entity,
            frame_id=frame_id,
            population=population,
            source=source,
            source_row_id=source_row_id,
            semantic_key=semantic_key,
            source_fact_ids=upstream,
            transform=transform,
            manifest_version=manifest_version,
        )
        return cls(
            id=_digest("fact", identity, length=24),
            kind=kind,
            metric=metric,
            variant=variant,
            entity=entity,
            value=value,
            unit=unit,
            frame_id=frame_id,
            population=population,
            sample_size=sample_size,
            sufficiency=sufficiency,
            source=source,
            source_fact_ids=upstream,
            transform=transform,
            manifest_version=manifest_version,
            source_row_id=source_row_id,
            semantic_key=semantic_key,
        )

    @staticmethod
    def _identity(
        *,
        kind: FactKind,
        metric: str,
        variant: str | None,
        entity: str,
        frame_id: str,
        population: str,
        source: str,
        source_row_id: str | None,
        semantic_key: str,
        source_fact_ids: tuple[str, ...],
        transform: str | None,
        manifest_version: str | None,
    ) -> dict[str, object]:
        return {
            "entity": entity,
            "frame_id": frame_id,
            "kind": kind.value,
            "manifest_version": manifest_version,
            "metric": metric,
            "population": population,
            "semantic_key": semantic_key,
            "source": source,
            "source_fact_ids": source_fact_ids,
            "source_row_id": source_row_id,
            "transform": transform,
            "variant": variant,
        }

    @property
    def expected_id(self) -> str:
        return _digest(
            "fact",
            self._identity(
                kind=self.kind,
                metric=self.metric,
                variant=self.variant,
                entity=self.entity,
                frame_id=self.frame_id,
                population=self.population,
                source=self.source,
                source_row_id=self.source_row_id,
                semantic_key=self.semantic_key,
                source_fact_ids=self.source_fact_ids,
                transform=self.transform,
                manifest_version=self.manifest_version,
            ),
            length=24,
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Fact:
        return cls(
            **{
                **value,
                "kind": FactKind(value["kind"]),
                "source_fact_ids": tuple(value.get("source_fact_ids", ())),
            }
        )


class FactRegistry:
    """Manifest-bound registry of immutable evidence facts."""

    def __init__(
        self,
        facts: Iterable[Fact] = (),
        *,
        manifest_version: str | None = None,
        manifest_rows: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self._facts: dict[str, Fact] = {}
        self._manifest_version = manifest_version
        self._version: str | None = None
        self._manifest_rows = {
            source: frozenset(row_ids) for source, row_ids in (manifest_rows or {}).items()
        }
        for fact in facts:
            self.add(fact)

    @property
    def manifest_version(self) -> str | None:
        return self._manifest_version

    @property
    def version(self) -> str:
        if self._version is None:
            content = [fact.to_dict() for fact in self.facts()]
            self._version = _digest("facts", content)
        return self._version

    def add(self, fact: Fact) -> Fact:
        self._validate_identity(fact)
        self._validate_manifest_binding(fact)
        if fact.source_fact_ids:
            self._validate_derived(fact)
        else:
            self._validate_base(fact)
        existing = self._facts.get(fact.id)
        if existing is not None and existing != fact:
            raise ValueError(f"conflicting fact identity {fact.id}")
        if existing is None:
            self._facts[fact.id] = fact
            self._version = None
        return fact

    def _validate_identity(self, fact: Fact) -> None:
        if not fact.semantic_key.strip():
            raise ValueError("fact semantic key must be nonempty")
        if type(fact.value) is float and not math.isfinite(fact.value):
            raise ValueError("numeric fact value must be finite")
        if fact.id != fact.expected_id:
            raise ValueError(f"fact ID does not match semantic identity: {fact.id}")

    def _validate_manifest_binding(self, fact: Fact) -> None:
        if self._manifest_version is None or not self._manifest_version.strip():
            raise ValueError("registry requires a nonempty manifest version")
        if fact.manifest_version != self._manifest_version:
            raise ValueError("fact must use the same manifest version as the registry and upstream facts")

    def _validate_base(self, fact: Fact) -> None:
        if fact.kind is FactKind.COMPUTED or fact.source == DERIVED_FACT_SOURCE:
            raise ValueError("derived fact requires nonempty upstream fact IDs")
        if fact.transform is not None:
            raise ValueError("base fact cannot declare a transform")
        if (
            not _PITCHINGPLUS_SOURCE.fullmatch(fact.source)
            or fact.source not in self._manifest_rows
            or fact.source_row_id is None
            or not fact.source_row_id.strip()
            or fact.source_row_id not in self._manifest_rows[fact.source]
        ):
            raise ValueError("base fact must identify a manifest-covered PitchingPlus artifact row")

    def _validate_derived(self, fact: Fact) -> None:
        if fact.kind not in {FactKind.COMPUTED, FactKind.MODEL_SEMANTIC}:
            raise ValueError("derived fact must use computed or model_semantic fact kind")
        if fact.source != DERIVED_FACT_SOURCE:
            raise ValueError("derived fact source must be pitcher_narratives:deterministic_transform")
        if fact.source_row_id is not None:
            raise ValueError("derived fact cannot identify a base source row")
        if fact.transform is None or not fact.transform.strip():
            raise ValueError("derived fact requires a deterministic transform")
        if any(not fact_id.strip() for fact_id in fact.source_fact_ids) or len(
            set(fact.source_fact_ids)
        ) != len(fact.source_fact_ids):
            raise ValueError("derived fact upstream fact IDs must be nonempty and unique")
        missing = [fact_id for fact_id in fact.source_fact_ids if fact_id not in self._facts]
        if missing:
            raise ValueError(
                "derived fact requires every upstream fact ID to be already registered: " + ", ".join(missing)
            )
        upstream = [self._facts[fact_id] for fact_id in fact.source_fact_ids]
        is_comparison = _COMPARISON_TRANSFORM.fullmatch(fact.transform) is not None
        if fact.transform.startswith("comparison:") and not is_comparison:
            raise ValueError("derived fact uses an unsupported comparison transform")
        upstream_frames = {source.frame_id for source in upstream}
        if is_comparison:
            if len(upstream) < 2 or len(upstream_frames) < 2:
                raise ValueError("comparison transform requires facts from at least two frames")
        elif any(source.frame_id != fact.frame_id for source in upstream):
            raise ValueError("derived fact and every upstream fact must use the same frame")
        if any(source.manifest_version != fact.manifest_version for source in upstream):
            raise ValueError("derived fact and every upstream fact must use the same manifest")

    def __contains__(self, fact_id: str) -> bool:
        return fact_id in self._facts

    def get(self, fact_id: str) -> Fact:
        return self._facts[fact_id]

    def facts(self) -> tuple[Fact, ...]:
        return tuple(self._facts[fact_id] for fact_id in sorted(self._facts))

    def merge(self, other: FactRegistry) -> FactRegistry:
        """Merge another registry with the same manifest, preserving full lineage."""
        if other is self:
            return self
        if self.manifest_version != other.manifest_version:
            raise ValueError("fact registries must use the same manifest version")
        for source, row_ids in other._manifest_rows.items():
            self._manifest_rows[source] = frozenset(set(self._manifest_rows.get(source, ())) | set(row_ids))
        pending = {fact.id: fact for fact in other.facts() if fact.id not in self._facts}
        while pending:
            ready = tuple(
                fact
                for fact in pending.values()
                if all(source_id in self._facts for source_id in fact.source_fact_ids)
            )
            if not ready:
                raise ValueError("cannot merge registry with unresolved fact lineage")
            for fact in ready:
                self.add(fact)
                pending.pop(fact.id)
        return self

    def base_lineage(self, fact_id: str) -> tuple[Fact, ...]:
        if fact_id not in self._facts:
            raise KeyError(fact_id)
        base_ids: set[str] = set()
        pending = [fact_id]
        while pending:
            current_id = pending.pop()
            current = self._facts[current_id]
            if current.source_fact_ids:
                pending.extend(current.source_fact_ids)
            else:
                base_ids.add(current_id)
        return tuple(self._facts[source_id] for source_id in sorted(base_ids))

    def validate_fact_ids(
        self,
        fact_ids: Sequence[str],
        *,
        frame_id: str,
        manifest_version: str,
        claim_type: ClaimType,
    ) -> tuple[Fact, ...]:
        if not fact_ids:
            raise ValueError("claim requires at least one fact citation")
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("claim fact citations must be unique")
        unknown = [fact_id for fact_id in fact_ids if fact_id not in self._facts]
        if unknown:
            raise ValueError("claim cites unknown fact IDs: " + ", ".join(unknown))
        facts = tuple(self._facts[fact_id] for fact_id in fact_ids)
        if any(fact.frame_id != frame_id for fact in facts):
            raise ValueError("claim cites a fact from the wrong frame")
        if any(fact.manifest_version != manifest_version for fact in facts):
            raise ValueError("claim cites a fact from the wrong manifest")
        for fact in facts:
            if (
                fact.sufficiency not in _SUPPORTED_SUFFICIENCY
                or fact.value is None
                or (fact.sample_size is not None and fact.sample_size <= 0)
            ):
                raise ValueError(f"insufficient fact {fact.id} for {claim_type.value} claim")
            self.base_lineage(fact.id)
        return facts

    def _validate_claim_binding(
        self,
        *,
        frame_id: str,
        manifest_version: str,
        fact_registry_version: str,
    ) -> None:
        if manifest_version != self._manifest_version:
            raise ValueError("claim is bound to the wrong manifest")
        if fact_registry_version != self.version:
            raise ValueError("claim is bound to a stale or wrong fact registry")
        if not frame_id.strip():
            raise ValueError("claim frame must be nonempty")


@dataclass(frozen=True)
class AnalysisClaim:
    id: str
    text: str
    fact_ids: tuple[str, ...]
    frame_id: str
    manifest_version: str
    fact_registry_version: str
    claim_type: ClaimType
    confidence: str

    @classmethod
    def create(
        cls,
        *,
        text: str,
        fact_ids: Iterable[str],
        frame_id: str,
        manifest_version: str,
        fact_registry_version: str,
        claim_type: ClaimType | str,
        confidence: str,
    ) -> AnalysisClaim:
        citations = tuple(sorted(fact_ids))
        typed_claim = ClaimType(claim_type)
        identity = {
            "claim_type": typed_claim.value,
            "confidence": confidence,
            "fact_ids": citations,
            "fact_registry_version": fact_registry_version,
            "frame_id": frame_id,
            "manifest_version": manifest_version,
            "text": text,
        }
        return cls(
            id=_digest("analysis-claim", identity),
            text=text,
            fact_ids=citations,
            frame_id=frame_id,
            manifest_version=manifest_version,
            fact_registry_version=fact_registry_version,
            claim_type=typed_claim,
            confidence=confidence,
        )

    @property
    def expected_id(self) -> str:
        return self.create(
            text=self.text,
            fact_ids=self.fact_ids,
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            fact_registry_version=self.fact_registry_version,
            claim_type=self.claim_type,
            confidence=self.confidence,
        ).id

    def validate(self, registry: FactRegistry) -> AnalysisClaim:
        if self.id != self.expected_id:
            raise ValueError("analysis claim ID does not match claim content")
        if not self.text.strip():
            raise ValueError("analysis claim text must be nonempty")
        if not self.confidence.strip():
            raise ValueError("analysis claim confidence must be nonempty")
        registry._validate_claim_binding(
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            fact_registry_version=self.fact_registry_version,
        )
        registry.validate_fact_ids(
            self.fact_ids,
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            claim_type=self.claim_type,
        )
        return self

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["claim_type"] = self.claim_type.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AnalysisClaim:
        return cls(
            **{
                **value,
                "fact_ids": tuple(value["fact_ids"]),
                "claim_type": ClaimType(value["claim_type"]),
            }
        )


@dataclass(frozen=True)
class NarrativeClaim:
    id: str
    text: str
    fact_ids: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    frame_id: str
    manifest_version: str
    fact_registry_version: str
    claim_type: ClaimType

    @classmethod
    def create(
        cls,
        *,
        text: str,
        fact_ids: Iterable[str],
        source_claim_ids: Iterable[str],
        frame_id: str,
        manifest_version: str,
        fact_registry_version: str,
        claim_type: ClaimType | str,
    ) -> NarrativeClaim:
        citations = tuple(sorted(fact_ids))
        upstream = tuple(sorted(source_claim_ids))
        typed_claim = ClaimType(claim_type)
        identity = {
            "claim_type": typed_claim.value,
            "fact_ids": citations,
            "fact_registry_version": fact_registry_version,
            "frame_id": frame_id,
            "manifest_version": manifest_version,
            "source_claim_ids": upstream,
            "text": text,
        }
        return cls(
            id=_digest("narrative-claim", identity),
            text=text,
            fact_ids=citations,
            source_claim_ids=upstream,
            frame_id=frame_id,
            manifest_version=manifest_version,
            fact_registry_version=fact_registry_version,
            claim_type=typed_claim,
        )

    @property
    def expected_id(self) -> str:
        return self.create(
            text=self.text,
            fact_ids=self.fact_ids,
            source_claim_ids=self.source_claim_ids,
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            fact_registry_version=self.fact_registry_version,
            claim_type=self.claim_type,
        ).id

    def validate(
        self,
        registry: FactRegistry,
        *,
        source_claims: Iterable[AnalysisClaim | NarrativeClaim],
    ) -> NarrativeClaim:
        if self.id != self.expected_id:
            raise ValueError("narrative claim ID does not match claim content")
        if not self.text.strip():
            raise ValueError("narrative claim text must be nonempty")
        registry._validate_claim_binding(
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            fact_registry_version=self.fact_registry_version,
        )
        registry.validate_fact_ids(
            self.fact_ids,
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            claim_type=self.claim_type,
        )
        available: dict[str, AnalysisClaim | NarrativeClaim] = {}
        for claim in source_claims:
            if claim.id in available:
                raise ValueError(f"duplicate source claim ID {claim.id}")
            available[claim.id] = claim
        if not self.source_claim_ids:
            raise ValueError("narrative claim requires source claim IDs")
        unknown = [claim_id for claim_id in self.source_claim_ids if claim_id not in available]
        if unknown:
            raise ValueError("narrative claim cites unknown source claim IDs: " + ", ".join(unknown))
        cited_sources = [available[claim_id] for claim_id in self.source_claim_ids]
        allowed_fact_ids: set[str] = set()
        for source in cited_sources:
            if source.id != source.expected_id:
                raise ValueError("source claim ID does not match claim content")
            if (
                source.frame_id != self.frame_id
                or source.manifest_version != self.manifest_version
                or source.fact_registry_version != self.fact_registry_version
            ):
                raise ValueError("narrative claim source has incompatible provenance")
            registry.validate_fact_ids(
                source.fact_ids,
                frame_id=source.frame_id,
                manifest_version=source.manifest_version,
                claim_type=source.claim_type,
            )
            allowed_fact_ids.update(source.fact_ids)
        if not set(self.fact_ids).issubset(allowed_fact_ids):
            raise ValueError("narrative claim facts are not a subset of source claim evidence")
        if not any(
            self.claim_type in NARRATIVE_CLAIM_TRANSITIONS[source.claim_type] for source in cited_sources
        ):
            source_types = ", ".join(sorted({source.claim_type.value for source in cited_sources}))
            raise ValueError(
                f"narrative claim escalates source claim type(s) {source_types} to {self.claim_type.value}"
            )
        capability = CLAIM_CAPABILITY_REQUIREMENTS.get(self.claim_type)
        if capability is not None:
            capability_facts = tuple(
                fact
                for fact in registry.facts()
                if fact.frame_id == self.frame_id and fact.metric == f"capability.{capability}"
            )
            if (
                len(capability_facts) != 1
                or capability_facts[0].kind is not FactKind.MODEL_SEMANTIC
                or capability_facts[0].value is not True
                or capability_facts[0].id not in self.fact_ids
            ):
                raise ValueError(
                    f"{self.claim_type.value} narrative claim requires its exact "
                    f"available capability fact for {capability}"
                )
        return self

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["claim_type"] = self.claim_type.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> NarrativeClaim:
        return cls(
            **{
                **value,
                "fact_ids": tuple(value["fact_ids"]),
                "source_claim_ids": tuple(value["source_claim_ids"]),
                "claim_type": ClaimType(value["claim_type"]),
            }
        )


@dataclass(frozen=True)
class NarrativeArtifact:
    id: str
    content: str
    claims: tuple[NarrativeClaim, ...]
    content_hash: str
    frame_id: str
    manifest_version: str
    fact_registry_version: str

    @classmethod
    def create(
        cls,
        *,
        content: str,
        claims: Iterable[NarrativeClaim],
        frame_id: str,
        manifest_version: str,
        fact_registry_version: str,
    ) -> NarrativeArtifact:
        typed_claims = tuple(claims)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        identity = {
            "claim_ids": tuple(claim.id for claim in typed_claims),
            "content_hash": content_hash,
            "fact_registry_version": fact_registry_version,
            "frame_id": frame_id,
            "manifest_version": manifest_version,
        }
        return cls(
            id=_digest("narrative-artifact", identity),
            content=content,
            claims=typed_claims,
            content_hash=content_hash,
            frame_id=frame_id,
            manifest_version=manifest_version,
            fact_registry_version=fact_registry_version,
        )

    @property
    def expected_id(self) -> str:
        return self.create(
            content=self.content,
            claims=self.claims,
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            fact_registry_version=self.fact_registry_version,
        ).id

    def _validate_integrity(self, registry: FactRegistry) -> None:
        if not self.content.strip():
            raise ValueError("narrative artifact content must be nonempty")
        expected_hash = hashlib.sha256(self.content.encode()).hexdigest()
        if self.content_hash != expected_hash:
            raise ValueError("narrative artifact content hash is invalid")
        if self.id != self.expected_id:
            raise ValueError("narrative artifact ID does not match artifact content")
        if not self.claims:
            raise ValueError("narrative artifact requires at least one claim")
        if len({claim.id for claim in self.claims}) != len(self.claims):
            raise ValueError("narrative artifact claim IDs must be unique")
        reader_statements = _reader_statements(self.content)
        statement_set = set(reader_statements)
        for claim in self.claims:
            if _normalize_statement(claim.text) not in statement_set:
                raise ValueError(f"narrative claim text is absent from artifact content: {claim.id}")
        claim_statements = {_normalize_statement(claim.text) for claim in self.claims}
        for statement in reader_statements:
            if statement not in claim_statements:
                raise ValueError(f"reader statement lacks a claim: {statement!r}")
        registry._validate_claim_binding(
            frame_id=self.frame_id,
            manifest_version=self.manifest_version,
            fact_registry_version=self.fact_registry_version,
        )
        for claim in self.claims:
            if (
                claim.frame_id != self.frame_id
                or claim.manifest_version != self.manifest_version
                or claim.fact_registry_version != self.fact_registry_version
            ):
                raise ValueError("artifact claim has incompatible provenance")

    def validate(
        self,
        registry: FactRegistry,
        *,
        source_claims: Iterable[AnalysisClaim | NarrativeClaim],
    ) -> NarrativeArtifact:
        self._validate_integrity(registry)
        upstream = tuple(source_claims)
        for claim in self.claims:
            claim.validate(registry, source_claims=upstream)
        return self

    def validate_summary(
        self,
        registry: FactRegistry,
        final_verified_capsule: NarrativeArtifact,
    ) -> NarrativeArtifact:
        self._validate_integrity(registry)
        final_verified_capsule._validate_integrity(registry)
        capsule_claim_ids = {claim.id for claim in final_verified_capsule.claims}
        capsule_fact_ids = {fact_id for claim in final_verified_capsule.claims for fact_id in claim.fact_ids}
        for claim in self.claims:
            if not set(claim.source_claim_ids).issubset(capsule_claim_ids) or not set(
                claim.fact_ids
            ).issubset(capsule_fact_ids):
                raise ValueError("summary evidence is not a subset of the final verified capsule")
            try:
                claim.validate(
                    registry,
                    source_claims=final_verified_capsule.claims,
                )
            except ValueError as exc:
                raise ValueError("summary evidence is not a subset of the final verified capsule") from exc
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "claims": [claim.to_dict() for claim in self.claims],
            "content_hash": self.content_hash,
            "frame_id": self.frame_id,
            "manifest_version": self.manifest_version,
            "fact_registry_version": self.fact_registry_version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> NarrativeArtifact:
        return cls(
            id=value["id"],
            content=value["content"],
            claims=tuple(NarrativeClaim.from_dict(claim) for claim in value["claims"]),
            content_hash=value["content_hash"],
            frame_id=value["frame_id"],
            manifest_version=value["manifest_version"],
            fact_registry_version=value["fact_registry_version"],
        )


def calibration_facts(
    report: ModelEvaluationArtifact,
    *,
    frame_id: str,
    manifest_version: str | None,
) -> tuple[Fact, ...]:
    """Expose held-out calibration metrics without prose inference."""
    facts: list[Fact] = []
    metadata = report.metadata
    source = (
        "PitchingPlus calibration "
        f"model_bundle={metadata.producer_identity.model_bundle_sha256}; "
        f"feature_schema={metadata.producer_identity.feature_schema_sha256}; "
        f"as_of={metadata.as_of}"
    )
    scalar_metrics = (
        ("log_loss", "log_loss", "nats"),
        ("brier_score", "brier_score", "probability_squared"),
        (
            "empirical_prior_log_loss",
            "empirical_prior_log_loss",
            "nats",
        ),
        ("log_loss_skill", "log_loss_skill", "nats"),
        (
            "expected_calibration_error",
            "expected_calibration_error",
            "probability",
        ),
    )
    for model_key, model_report in sorted(report.models.items()):
        overall = model_report.overall
        variant = model_key.split(".", maxsplit=1)[0]
        for metric, attribute, unit in scalar_metrics:
            facts.append(
                Fact.create(
                    kind=FactKind.MODEL_OUTPUT,
                    metric=metric,
                    variant=variant,
                    entity=model_key,
                    value=getattr(overall, attribute),
                    unit=unit,
                    frame_id=frame_id,
                    population=metadata.scoring_population,
                    sample_size=overall.n_observations,
                    sufficiency="held_out",
                    source=source,
                    semantic_key=f"{model_key}|overall|{metric}",
                    manifest_version=manifest_version,
                )
            )
        for index, row in enumerate(overall.reliability_bins):
            entity = f"{model_key}|probability_bin:{row.lower:.12g}-{row.upper:.12g}"
            for metric, value in (
                ("reliability_mean_probability", row.mean_probability),
                ("reliability_observed_frequency", row.observed_frequency),
            ):
                facts.append(
                    Fact.create(
                        kind=FactKind.MODEL_OUTPUT,
                        metric=metric,
                        variant=variant,
                        entity=entity,
                        value=value,
                        unit="probability",
                        frame_id=frame_id,
                        population=metadata.scoring_population,
                        sample_size=row.count,
                        sufficiency=("held_out" if row.count > 0 else "unavailable"),
                        source=source,
                        semantic_key=(f"{model_key}|reliability|{index}|{metric}"),
                        manifest_version=manifest_version,
                    )
                )
    return tuple(sorted(facts, key=lambda fact: fact.id))


def calibration_unavailable_fact(
    reason: str,
    *,
    frame_id: str,
    population: str,
    manifest_version: str | None,
) -> Fact:
    """Represent unavailable confidence evidence as typed null data."""
    return Fact.create(
        kind=FactKind.MODEL_SEMANTIC,
        metric="calibration_availability",
        variant=None,
        entity="PitchingPlus model calibration",
        value=None,
        unit=None,
        frame_id=frame_id,
        population=population,
        sample_size=None,
        sufficiency="unavailable",
        source=reason,
        semantic_key="calibration|availability",
        manifest_version=manifest_version,
    )
