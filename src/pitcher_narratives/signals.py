"""Key signal extraction model and rendering.

The signal extractor identifies cross-specialist patterns that no single
specialist can see: tensions between analysts, arsenal dependencies,
connected changes, and sample size caveats. These signals guide the
writer's narrative priorities and give the anchor checker concrete
validation targets.
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = [
    "KeySignals",
    "SIGNAL_EXTRACTOR_PROMPT",
    "render_key_signals",
]


class KeySignals(BaseModel):
    """Cross-specialist narrative signals extracted from clean specialist outputs.

    Primary signals (required) are anchor-enforced via MISSED_SIGNAL.
    Secondary signals (optional) are advisory via UNDERWEIGHTED.
    """

    # Primary signals (required)
    top_improvement: str
    top_concern: str

    # Secondary signals (optional)
    development_pitch: str | None = None
    specialist_tension: str | None = None
    arsenal_dependency: str | None = None
    connected_changes: str | None = None
    platoon_vulnerability: str | None = None
    sample_size_caution: str | None = None


_FIELD_LABELS: dict[str, str] = {
    "top_improvement": "Top Improvement",
    "top_concern": "Top Concern",
    "development_pitch": "Development Pitch",
    "specialist_tension": "Specialist Tension",
    "arsenal_dependency": "Arsenal Dependency",
    "connected_changes": "Connected Changes",
    "platoon_vulnerability": "Platoon Vulnerability",
    "sample_size_caution": "Sample Size Caution",
}


def render_key_signals(signals: KeySignals) -> str:
    """Render populated key signals as a labeled bullet list.

    Omits None fields entirely so the writer and anchor checker
    only see signals that are present.
    """
    lines = ["## Key Signals"]
    for field_name, label in _FIELD_LABELS.items():
        value = getattr(signals, field_name)
        if value is not None:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)


SIGNAL_EXTRACTOR_PROMPT = ""
