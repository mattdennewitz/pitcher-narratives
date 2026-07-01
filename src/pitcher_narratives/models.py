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

from pydantic import BaseModel

from pitcher_narratives.signals import KeySignals

__all__ = [
    "AnalyzedContext",
    "AuditFlag",
    "AuditResult",
    "SpecialistOutputs",
]


class AuditFlag(BaseModel):
    """A single data audit flag."""

    category: str
    specialist: str = ""
    claim: str
    data_shows: str
    suggested_fix: str


class AuditResult(BaseModel):
    """Structured output from the data auditor agent."""

    flags: list[AuditFlag]

    @property
    def is_clean(self) -> bool:
        return len(self.flags) == 0


class SpecialistOutputs(BaseModel):
    """Raw outputs from each specialist agent."""

    stuff: str
    location: str
    runvalue: str
    trends: str
    game_shape: str


class AnalyzedContext(BaseModel):
    """Grounded specialist analysis produced by run_analysis_spine.

    Carries the clean specialist outputs, cross-specialist key signals, and
    any audit flags from the specialist revision loop. Does not include
    terminal-layer artifacts (writer capsule, anchor result, hallucination
    report) — those depend on a specific output target and are produced by
    the calling terminal.
    """

    specialists: SpecialistOutputs
    key_signals: KeySignals | None = None
    audit_flags: list[AuditFlag] = []
    signals_failed: bool = False


class CoreContext(BaseModel):
    """Frame-agnostic core of the analysis spine.

    Holds the clean stuff/location/run-value/game-shape specialist outputs and
    their audit flags. Trends analysis, key-signal extraction, and the anchor
    check are frame-sensitive and produced by the tail (see run_spine_tail);
    they are deliberately absent here so the core can be computed once and
    shared across narration modes that differ only in temporal frame.
    """

    stuff: str
    location: str
    runvalue: str
    game_shape: str
    audit_flags: list[AuditFlag] = []
