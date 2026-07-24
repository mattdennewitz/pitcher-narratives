"""Shared Pydantic models used across pipeline, digest, and morning layers.

Extracting these here breaks the formatting/orchestration → engine downward
import that would otherwise force digest.py to depend on pipeline.py.

Import graph:
    models.py → signals.py (for KeySignals)
    pipeline.py → models.py
    digest.py → models.py
    morning.py → models.py
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pitcher_narratives.claims import SpecialistAnalysis
from pitcher_narratives.facts import ClaimType
from pitcher_narratives.signals import KeySignals

__all__ = [
    "AnalyzedContext",
    "AuditFlag",
    "AuditResult",
    "ClaimDraft",
    "CoreContext",
    "NarrativeArtifactDraft",
    "NarrativeClaimDraft",
    "SpecialistAnalysisDraft",
    "SpecialistOutputs",
    "VerificationState",
    "empty_narrative_draft",
    "empty_specialist_analysis",
    "render_specialist_analysis",
]


class VerificationState(StrEnum):
    """Closed verification outcomes for generated evidence."""

    VERIFIED = "verified"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    PROVIDER_FAILED = "provider_failed"


class AuditFlag(BaseModel):
    """A rejected or unavailable claim with exact evidence references."""

    category: str
    specialist: str = ""
    claim: str
    data_shows: str
    suggested_fix: str
    claim_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()
    state: VerificationState = VerificationState.REJECTED


class AuditResult(BaseModel):
    """Structured output from the data auditor agent."""

    flags: list[AuditFlag]

    @property
    def state(self) -> VerificationState:
        return VerificationState.VERIFIED if not self.flags else VerificationState.REJECTED

    @property
    def is_clean(self) -> bool:
        return self.state is VerificationState.VERIFIED


class ClaimDraft(BaseModel):
    """Untrusted specialist claim before evidence binding and validation."""

    text: str
    claim_type: ClaimType
    confidence: str
    fact_ids: tuple[str, ...]


class SpecialistAnalysisDraft(BaseModel):
    """Untrusted structured output returned by a specialist agent."""

    observations: tuple[ClaimDraft, ...] = ()
    supported_interpretations: tuple[ClaimDraft, ...] = ()
    limitations: tuple[ClaimDraft, ...] = ()


class NarrativeClaimDraft(BaseModel):
    """Untrusted writer or summary claim before provenance validation."""

    text: str
    fact_ids: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    claim_type: ClaimType


class NarrativeArtifactDraft(BaseModel):
    """Untrusted reader-facing artifact returned by a prose agent."""

    content: str
    claims: tuple[NarrativeClaimDraft, ...]


def empty_narrative_draft() -> NarrativeArtifactDraft:
    """Return the explicit unavailable reader artifact draft."""
    return NarrativeArtifactDraft(content="", claims=())


def empty_specialist_analysis() -> SpecialistAnalysis:
    """Return a typed empty placeholder for an unselected specialist."""
    return SpecialistAnalysis(
        observations=(),
        supported_interpretations=(),
        limitations=(),
    )


def render_specialist_analysis(analysis: SpecialistAnalysis) -> str:
    """Render validated claims deterministically with inline fact citations."""
    sections = (
        ("Observations", analysis.observations),
        ("Supported Interpretations", analysis.supported_interpretations),
        ("Limitations", analysis.limitations),
    )
    lines: list[str] = []
    for heading, claims in sections:
        lines.append(f"### {heading}")
        if not claims:
            lines.append("- None.")
            continue
        for claim in claims:
            citations = " ".join(f"[{fact_id}]" for fact_id in claim.fact_ids)
            lines.append(f"- [claim:{claim.id}] {claim.text} {citations}")
    return "\n".join(lines)


class SpecialistOutputs(BaseModel):
    """Validated immutable analyses from each specialist agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    stuff: SpecialistAnalysis = Field(default_factory=empty_specialist_analysis)
    location: SpecialistAnalysis = Field(default_factory=empty_specialist_analysis)
    runvalue: SpecialistAnalysis = Field(default_factory=empty_specialist_analysis)
    trends: SpecialistAnalysis = Field(default_factory=empty_specialist_analysis)


class AnalyzedContext(BaseModel):
    """Grounded specialist analysis produced by run_analysis_spine.

    Carries the clean specialist outputs, cross-specialist key signals, and
    any audit flags from the specialist revision loop. Does not include
    terminal-layer artifacts (writer capsule, anchor result, hallucination
    report) — those depend on a specific output target and are produced by
    the calling terminal.

    ``trend_frame_comparison`` carries the rendered CHANGES-mode
    recent-vs-prior frame comparison block when ``run_spine_tail`` was given
    a ``prior_ctx``; it is ``None`` otherwise.
    """

    specialists: SpecialistOutputs
    key_signals: KeySignals | None = None
    audit_flags: list[AuditFlag] = []
    signals_failed: bool = False
    signals_state: VerificationState = VerificationState.VERIFIED
    residual_specialists: list[str] = []
    trend_frame_comparison: str | None = None


class CoreContext(BaseModel):
    """Frame-agnostic core of the analysis spine.

    Holds the clean stuff/location/run-value specialist outputs and
    their audit flags. Trends analysis, key-signal extraction, and the anchor
    check are frame-sensitive and produced by the tail (see run_spine_tail);
    they are deliberately absent here so the core can be computed once and
    shared across narration modes that differ only in temporal frame.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    stuff: SpecialistAnalysis
    location: SpecialistAnalysis
    runvalue: SpecialistAnalysis
    audit_flags: list[AuditFlag] = []
    residual_specialists: list[str] = []
