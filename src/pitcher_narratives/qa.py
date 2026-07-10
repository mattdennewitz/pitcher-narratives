"""Grade-explanation Q&A: parse a natural-language question, then narrate a
grounded answer over the analysis spine's reused specialist input.

Public: parse_grade_question, answer_question, QuestionError, GradeQuestion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic_ai import Agent

from pitcher_narratives.agent_skills import skill_toolset
from pitcher_narratives.config import (
    PROVIDERS,
    TOKEN_BUDGET_LARGE,
    agent_kwargs,
    make_model_settings,
)
from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.pipeline import (
    build_fact_revision_message,
    build_grade_input,
    run_data_audit,
)
from pitcher_narratives.resolver import extract_pitcher_from_question

__all__ = [
    "GradeQuestion",
    "QuestionError",
    "answer_question",
    "build_qa_agent",
    "parse_grade_question",
    "resolve_pitch_against_arsenal",
]


class QuestionError(Exception):
    """A user-facing problem with the question (bad pitcher, missing pitch, out of scope)."""


# Pitch nouns -> Statcast pitch-type codes. "fastball"/"heater" are ambiguous
# (FF or SI) and get reconciled against the pitcher's actual arsenal later.
PITCH_SYNONYMS: dict[str, list[str]] = {
    "four-seam": ["FF"], "four seam": ["FF"], "4-seam": ["FF"], "4 seam": ["FF"],
    "fastball": ["FF", "SI"], "heater": ["FF", "SI"], "fourseam": ["FF"],
    "sinker": ["SI"], "two-seam": ["SI"], "two seam": ["SI"], "twoseam": ["SI"],
    "cutter": ["FC"], "cut fastball": ["FC"],
    "sweeper": ["ST"], "slider": ["SL"],
    "knuckle curve": ["KC"], "knuckle-curve": ["KC"],
    "curveball": ["CU"], "curve": ["CU"],
    "changeup": ["CH"], "change-up": ["CH"], "change up": ["CH"], "change": ["CH"],
    "splitter": ["FS"], "split-finger": ["FS"], "split": ["FS"],
}

# Grade family detection. Order within each family is longest-first so
# "stuff+" is preferred over a bare "stuff".
GRADE_SYNONYMS: list[tuple[str, str]] = [
    ("location+", "L"), ("location plus", "L"), ("command", "L"), ("location", "L"), ("l+", "L"),
    ("pitching+", "P"), ("pitching plus", "P"), ("pitching", "P"), ("p+", "P"),
    ("stuff+", "S"), ("stuff plus", "S"), ("stuff", "S"), ("s+", "S"),
]

GRADE_LABELS: dict[str, str] = {
    "S": "Stuff+ (S+)", "L": "Location+ (L+)", "P": "Pitching+ (P+)",
}


@dataclass
class GradeQuestion:
    """A parsed grade-explanation question, before arsenal reconciliation."""

    pitcher_id: int
    pitcher_name: str
    grade_family: str
    pitch_noun: str
    pitch_candidates: list[str] = field(default_factory=list)
    cited_value: float | None = None


def _detect_grade(q: str) -> str:
    for phrase, family in GRADE_SYNONYMS:
        if phrase in q:
            return family
    return "S"  # default: Stuff+


def _detect_pitch(q: str) -> tuple[str, list[str]]:
    # Longest key first so "four-seam" wins over "fastball", "curveball" over "curve".
    for noun in sorted(PITCH_SYNONYMS, key=len, reverse=True):
        if noun in q:
            return noun, PITCH_SYNONYMS[noun]
    return "", []


def _detect_value(q: str) -> float | None:
    m = re.search(r"\b(\d{2,3})\b", q)
    return float(m.group(1)) if m else None


def parse_grade_question(question: str) -> GradeQuestion:
    """Parse a 'why does X's <pitch> grade <value> <grade>' question.

    Deterministic: pitcher via the resolver, pitch + grade via keyword maps.
    Raises QuestionError for an unresolvable pitcher or a missing pitch noun.
    """
    _matched, res = extract_pitcher_from_question(question)
    if res is None or res.pitcher_id is None:
        if res is not None and res.match_type == "ambiguous":
            names = ", ".join(name for _pid, name in res.candidates)
            raise QuestionError(f"Ambiguous pitcher — did you mean: {names}?")
        raise QuestionError("Couldn't find a pitcher in that question.")

    lowered = question.lower()
    pitch_noun, candidates = _detect_pitch(lowered)
    if not candidates:
        raise QuestionError(
            "Couldn't tell which pitch — name one, e.g. 'fastball' or 'slider'."
        )
    return GradeQuestion(
        pitcher_id=res.pitcher_id,
        pitcher_name=res.pitcher_name or "",
        grade_family=_detect_grade(lowered),
        pitch_noun=pitch_noun,
        pitch_candidates=candidates,
        cited_value=_detect_value(question),
    )


QA_SYSTEM_PROMPT = """\
You explain why a single pitch earns its Pitching+ grade (P+/S+/L+), for a \
front-office reader.

You are given pre-computed data for the pitcher's full arsenal: per-pitch \
grades, each physical trait tagged NORMAL or OUTLIER versus league, the \
S-variant league average for each pitch type, stuff-model predictions \
(xWhiff/xSwing/xRV100), and arm-slot shape. A leading instruction names the \
ONE pitch and grade to explain.

Consult the `explaining-pitch-grades` skill for the method before answering.

Rules:
- Explain ONLY the named pitch and grade; use the rest of the arsenal as contrast.
- Every number comes from the provided data — never compute or invent a statistic.
- If the data needed is missing, say so plainly.
- Answer in 1-3 tight paragraphs of scout prose. No preamble."""


def build_qa_agent(provider: str = "gemini") -> Agent[None, str]:
    """The focused grade-explanation agent: capable model + the skill library."""
    return Agent(
        PROVIDERS[provider],
        output_type=str,
        system_prompt=QA_SYSTEM_PROMPT,
        model_settings=make_model_settings(provider, "medium", 0.3, max_tokens=TOKEN_BUDGET_LARGE),
        toolsets=[skill_toolset()],
        retries=3,
        defer_model_check=True,
    )


def resolve_pitch_against_arsenal(candidates: list[str], arsenal: list) -> tuple[str, str]:
    """Pick the arsenal pitch matching the parsed candidates (most-thrown wins).

    Raises QuestionError listing the real arsenal if none of the candidates
    are thrown (e.g. asking about a splitter he doesn't have).
    """
    present = [p for p in arsenal if p.pitch_type in candidates]
    if not present:
        thrown = ", ".join(f"{p.pitch_name} ({p.pitch_type})" for p in arsenal)
        raise QuestionError(f"He doesn't throw that. Pitches: {thrown}.")
    best = max(present, key=lambda p: p.n_pitches_window)
    return best.pitch_type, best.pitch_name


async def answer_question(
    question: str,
    *,
    provider: str = "gemini",
    model_override=None,
) -> str:
    """Answer 'why does <pitcher>'s <pitch> grade <value> <grade>' in prose."""
    q = parse_grade_question(question)
    data = load_pitcher_data(q.pitcher_id)
    ctx = assemble_pitcher_context(data)
    pitch_type, pitch_name = resolve_pitch_against_arsenal(q.pitch_candidates, ctx.arsenal)

    grade_input = build_grade_input(ctx, q.grade_family)
    ground_truth = "\n".join(p for p in grade_input if isinstance(p, str))
    scoping = (
        f"Explain ONLY the {pitch_name} ({pitch_type}) and its "
        f"{GRADE_LABELS[q.grade_family]}. Use the rest of the arsenal as contrast."
    )

    agent = build_qa_agent(provider)
    result = await agent.run(**agent_kwargs([scoping, *grade_input], model_override))
    answer = result.output

    audit = await run_data_audit(ground_truth, answer, provider=provider, model_override=model_override)
    if not audit.is_clean:
        revision = build_fact_revision_message(ground_truth, answer, audit.flags)
        result = await agent.run(**agent_kwargs(revision, model_override))
        answer = result.output
    return answer
