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


SIGNAL_EXTRACTOR_PROMPT = """\
You are a cross-specialist pattern detector for a baseball analytics \
pipeline. You receive five specialist analyses of a pitcher's recent \
window (stuff, location, run value, trends, game shape). Your job is \
to identify patterns that span multiple specialists.

Extract these signals:

PRIMARY (always provide — there is always a best and worst signal):
- top_improvement: The single most important positive finding across \
all specialists. Cite the pitch type and metric.
- top_concern: The single most important negative finding across \
all specialists. Cite the pitch type and metric.

SECONDARY (provide ONLY when the pattern is genuinely present, \
otherwise leave as null):
- development_pitch: A pitch with high S+ (>110) but low L+ (<90) \
that would solve a documented platoon weakness. Name the pitch, \
cite S+ and L+, and identify which platoon gap it addresses. \
If nothing fits, null.
- specialist_tension: Where two specialists disagree about the same \
pitch. Example: stuff says the curveball is elite (S+ 128) but run \
value shows it bleeding runs (+1.2 xRV100). Name both specialists \
and their conflicting assessments. If all specialists agree, null.
- arsenal_dependency: If one pitch is carrying the entire profile \
while the rest is replacement-level. Cite the pitch and the evidence \
(e.g., whiff share, xRV100 gap). If the arsenal is balanced, null.
- connected_changes: When multiple specialists are reporting different \
facets of the same underlying shift. Example: trend sees velo drop, \
stuff sees S+ drop, run value sees more hard contact — all one \
pattern. Name the thread. If changes are independent, null.
- platoon_vulnerability: A clear weakness against one handedness \
that the data suggests is not being addressed. Cite P+ or pitch mix \
splits. If platoon splits are balanced, null.
- sample_size_caution: When the single strongest finding (whether \
improvement or concern) rests on thin data. Cite the sample size. \
If the key findings have adequate samples, null.

RULES:
- Cite specific pitch types and metrics in every field.
- Do not invent patterns — only surface what the specialists \
explicitly reported.
- Each field is ONE sentence. Be specific, not vague.
- Do not duplicate the same finding across multiple fields."""
