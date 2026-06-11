"""Benchmarking rubrics and judge output models.

Two absolute 1-5 rubrics with anchored descriptors and weights: one for
individual specialist outputs, one for the final scouting capsule. Both
share a grounding-weighted core. The judge scores every dimension with
a written justification and a verbatim evidence quote.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

__all__ = [
    "AGENT_RUBRIC",
    "CAPSULE_RUBRIC",
    "DimensionScore",
    "JudgedOutput",
    "RubricDimension",
    "build_judge_prompt",
    "weighted_overall",
]


@dataclass(frozen=True)
class RubricDimension:
    """One scored dimension: key, weight, and 1/3/5 anchor descriptors."""

    key: str
    label: str
    weight: float
    anchor_1: str
    anchor_3: str
    anchor_5: str


class DimensionScore(BaseModel):
    """The judge's score for a single rubric dimension."""

    dimension: str
    score: int = Field(ge=1, le=5)
    justification: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    """Verbatim quote from the judged text (or ground truth for grounding
    violations) supporting the score."""


class JudgedOutput(BaseModel):
    """Structured output from one judge over one text."""

    scores: list[DimensionScore]
    overall_comment: str


# ── Shared core dimensions ────────────────────────────────────────────

_CORE = [
    RubricDimension(
        key="grounding",
        label="Grounding / faithfulness",
        weight=3.0,
        anchor_1="Invents metrics or values absent from the ground truth, or misquotes provided numbers.",
        anchor_3="All numbers check out, but some claims stretch beyond what the data supports.",
        anchor_5="Every claim traceable to the ground truth; numbers exact; no embellishment.",
    ),
    RubricDimension(
        key="directional_consistency",
        label="Directional consistency",
        weight=2.0,
        anchor_1="Sign errors: treats positive xRV100 as good, flips P-vs-S location logic, or contradicts a grade's direction.",
        anchor_3="Directions correct but hedged or muddled in places.",
        anchor_5="All metric directions handled correctly and confidently (xRV100 negative = good; P>S meaning; S+ vs xRV100_S alignment).",
    ),
    RubricDimension(
        key="sample_size_calibration",
        label="Sample-size calibration",
        weight=1.5,
        anchor_1="States single-game or thin-sample artifacts as established traits.",
        anchor_3="Mostly calibrated; occasional overconfidence on small samples.",
        anchor_5="Conviction scales with sample size; thin data gets tentative language.",
    ),
]

# ── Specialist (individual agent) rubric ──────────────────────────────

AGENT_RUBRIC: list[RubricDimension] = _CORE + [
    RubricDimension(
        key="analytical_mechanism",
        label="Analytical mechanism",
        weight=2.0,
        anchor_1="Recites numbers without connecting physical inputs to model predictions to grades.",
        anchor_3="Some mechanism, but key links asserted rather than traced.",
        anchor_5="Traces the chain physical pitch -> model prediction -> grade for the pitches that matter.",
    ),
    RubricDimension(
        key="citation_discipline",
        label="Citation discipline",
        weight=1.5,
        anchor_1="Behavioral claims (whiffs, takes, chases) made with no supporting metric.",
        anchor_3="Most claims cite a metric; a few float free.",
        anchor_5="Every behavioral claim names the specific metric that supports it.",
    ),
    RubricDimension(
        key="no_hallucinated_causation",
        label="No hallucinated causation",
        weight=2.0,
        anchor_1="Invents causes from data not provided (release height, grip, mechanics).",
        anchor_3="Causes stay within the data but are occasionally overstated.",
        anchor_5="Causal claims strictly within the provided data; honest when the model sees something the averages don't show.",
    ),
    RubricDimension(
        key="focus",
        label="Focus",
        weight=1.0,
        anchor_1="Walks through every metric indiscriminately or misses the interesting pitches.",
        anchor_3="Covers the right pitches but buries the lead.",
        anchor_5="Prioritizes the extreme/surprising; routine facts get one line or none.",
    ),
]

# ── Final capsule rubric ──────────────────────────────────────────────

CAPSULE_RUBRIC: list[RubricDimension] = _CORE + [
    RubricDimension(
        key="thread_coherence",
        label="Thread coherence",
        weight=2.0,
        anchor_1="Reads as five stitched-together analyses with section seams and repeated facts.",
        anchor_3="One narrative but the thread wanders or restates.",
        anchor_5="One story in one voice; every paragraph serves the same thread.",
    ),
    RubricDimension(
        key="insight_synthesis",
        label="Insight / synthesis",
        weight=2.0,
        anchor_1="Recites specialist findings without connecting them.",
        anchor_3="Some cross-signal connection, mostly summary.",
        anchor_5="Surfaces the cross-specialist pattern as the lead; the reader learns something no single section said.",
    ),
    RubricDimension(
        key="scout_voice",
        label="Scout voice",
        weight=1.5,
        anchor_1="Clinical jargon, cliches, formulaic transitions, or breathless hype.",
        anchor_3="Readable but generic; cadence flat.",
        anchor_5="Conversational scouting register; varied cadence; numbers woven into prose naturally.",
    ),
    RubricDimension(
        key="model_explanation",
        label="Model explanation",
        weight=1.0,
        anchor_1="Uses S+/P+/L+ with no explanation of what they measure.",
        anchor_3="Defines the grades but mechanically.",
        anchor_5="Contextualizes the grading system on first use so an unfamiliar reader can follow.",
    ),
    RubricDimension(
        key="readability",
        label="Readability / structure",
        weight=1.0,
        anchor_1="Dense, repetitive, or disorganized; hard to follow.",
        anchor_3="Clear but workmanlike.",
        anchor_5="Effortless to read top to bottom; structure serves the story.",
    ),
]


def weighted_overall(scores: list[DimensionScore], rubric: list[RubricDimension]) -> float:
    """Weighted mean of scores over the rubric's dimensions.

    Scores whose dimension is not in the rubric are ignored (judges
    occasionally emit extras; they must not crash aggregation).
    """
    weights = {d.key: d.weight for d in rubric}
    num = 0.0
    den = 0.0
    for s in scores:
        w = weights.get(s.dimension)
        if w is None:
            continue
        num += s.score * w
        den += w
    return num / den if den else 0.0


def build_judge_prompt(rubric: list[RubricDimension]) -> str:
    """Build the judge's system prompt from a rubric.

    The judge receives the ground-truth context document and the text
    under evaluation in the user message; this prompt fixes the role,
    the anchors, and the evidence rules.
    """
    lines = [
        "You are a strict evaluation judge for LLM-written baseball scouting "
        "analysis. You receive a GROUND TRUTH data document and one OUTPUT "
        "to evaluate. Score the OUTPUT on every dimension below, 1-5, using "
        "the anchors. Be harsh and calibrated: 3 is competent, 5 is rare.",
        "",
        "RULES:",
        "- Score every dimension exactly once, using the dimension key verbatim.",
        "- justification: one or two sentences explaining the score.",
        "- evidence: a verbatim quote from the OUTPUT supporting your score. "
        "For grounding violations, also quote the ground truth that "
        "contradicts the output.",
        "- Verify every number in the OUTPUT against the GROUND TRUTH before "
        "scoring grounding. A single invented metric caps grounding at 1.",
        "- Do not reward length. Reward correctness, calibration, and insight.",
        "",
        "DIMENSIONS:",
    ]
    for d in rubric:
        lines.append(f"### {d.key} (weight {d.weight}) -- {d.label}")
        lines.append(f"- 1 = {d.anchor_1}")
        lines.append(f"- 3 = {d.anchor_3}")
        lines.append(f"- 5 = {d.anchor_5}")
        lines.append("")
    return "\n".join(lines)
