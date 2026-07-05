"""Anchor check quality gate: verifies capsules are faithful to the synthesis.

Used by the multi-agent specialist pipeline (pipeline.py) to verify
capsule faithfulness to the synthesis.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic_ai import CachePoint

__all__ = [
    "ANCHOR_PROMPT",
    "AnchorResult",
    "AnchorWarning",
    "WarningCategory",
    "build_anchor_message",
    "build_reconcile_message",
    "build_revision_message",
]

UserPrompt = list[str | CachePoint]
"""Type alias for user prompts with cache breakpoints."""

ANCHOR_PROMPT = """\
You are a fact-checker for a baseball analytics newsletter. You receive \
two documents: the data analyst's structured briefing (the synthesis) \
and the editor's finished narrative (the capsule). Your job is to verify \
that the capsule is faithfully anchored to the synthesis.

Check for these specific problems:

1. Missed Key Signals: The synthesis includes a Key Signals section with \
primary and secondary findings. Primary signals (Top Improvement, Top \
Concern) are mandatory — if the capsule ignores either entirely, flag it \
as MISSED_SIGNAL. Secondary signals (Development Pitch, Specialist \
Tension, Arsenal Dependency, Connected Changes, Platoon Vulnerability, \
Sample Size Caution) are advisory — if the capsule ignores a populated \
secondary signal, flag it as UNDERWEIGHTED.

2. Unsupported Claims: If the capsule states a metric, trend, or fact \
that does not appear anywhere in the synthesis, flag it. The capsule \
should not invent data.

3. Directional Errors: If the synthesis says a metric went up and the \
capsule says it went down (or vice versa), flag it.

4. Overstated Confidence: If the synthesis flags something as small \
sample or uncertain, but the capsule presents it as definitive, flag it.

For each problem found, report it with its category and a concise description.
If everything checks out, return an empty list of warnings.

Summary tables in a fixed section format are intentional structure, \
not narrative violations."""


WarningCategory = Literal["MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED", "UNDERWEIGHTED"]
"""Anchor check warning categories matching ANCHOR_PROMPT output format."""


class AnchorWarning(BaseModel):
    """A single anchor check warning with typed category."""

    category: WarningCategory
    description: str


class AnchorResult(BaseModel):
    """Structured output from the anchor check agent."""

    warnings: list[AnchorWarning]

    @property
    def is_clean(self) -> bool:
        """True when the capsule is faithfully anchored to the synthesis."""
        return len(self.warnings) == 0


def _render_warnings(warnings: list[AnchorWarning]) -> str:
    """Render anchor warnings as a bracketed-category bullet list."""
    return "\n".join(f"- [{w.category}] {w.description}" for w in warnings)


def build_anchor_message(synthesis: str, capsule: str) -> UserPrompt:
    """Build the anchor check user message."""
    return [
        f"## Synthesis (Data Analyst's Briefing)\n{synthesis}",
        CachePoint(),
        f"## Capsule (Editor's Narrative)\n{capsule}\n\n"
        "Check the capsule against the synthesis. Report any issues, or return an empty warnings list if everything checks out.",
    ]


def build_revision_message(
    synthesis: str,
    capsule: str,
    warnings: list[AnchorWarning],
) -> UserPrompt:
    """Build a revision prompt for the editor to fix anchor-flagged issues.

    Fixed-size context: synthesis + current capsule + formatted warnings +
    targeted instruction. No message history (fresh prompt per revision).

    Args:
        synthesis: The data analyst's structured briefing.
        capsule: The editor's current narrative capsule.
        warnings: Anchor check warnings to address.

    Returns:
        User prompt parts with cache breakpoint after synthesis.
    """
    formatted_warnings = _render_warnings(warnings)
    return [
        f"## Data Analyst's Briefing\n{synthesis}",
        CachePoint(),
        f"## Current Capsule\n{capsule}\n\n"
        f"## Anchor Check Warnings\n{formatted_warnings}\n\n"
        "Revise the capsule to address ONLY the warnings listed above. "
        "Preserve the voice, structure, and all unflagged material. "
        "Do not add new analysis or metrics not in the briefing.",
    ]


def build_reconcile_message(
    synthesis: str, capsule: str, warnings: list[AnchorWarning]
) -> str:
    """Revision message for anchor warnings raised AFTER a data fact-revision.

    The capsule's numbers were just corrected against source data, so this
    variant of the revision message forbids touching them: when the anchor
    says the synthesis disagrees with a number, the synthesis is the side
    that may be wrong. The writer fixes the warnings through prose —
    attribution, hedging, dropping unsupported causal claims — never by
    editing figures back toward the synthesis.

    Args:
        synthesis: The data analyst's structured briefing.
        capsule: The fact-checked, numerically authoritative capsule.
        warnings: Anchor check warnings raised against the revised capsule.

    Returns:
        A single revision prompt string (no cache breakpoints — this is a
        one-off reconcile pass, not part of the cached revision loop).
    """
    rendered = _render_warnings(warnings)
    return (
        "Your capsule was revised by a data fact-check: its numeric values are "
        "now verified against source data and are authoritative. A subsequent "
        "anchor check against the specialist synthesis raised the warnings "
        "below. Revise the capsule to address them, under one hard rule:\n"
        "DO NOT CHANGE ANY NUMERIC VALUE in the capsule. Where a warning says "
        "the synthesis shows different numbers, keep the capsule's numbers "
        "(the fact-check verified them; the synthesis may overstate) and fix "
        "the prose instead — soften or attribute the claim, hedge the "
        "mechanism, or drop an unsupported causal link.\n\n"
        f"WARNINGS:\n{rendered}\n\n"
        f"SPECIALIST SYNTHESIS:\n{synthesis}\n\n"
        f"CURRENT CAPSULE:\n{capsule}\n\n"
        "Return only the revised capsule text."
    )
