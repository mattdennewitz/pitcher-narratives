"""Grade-explanation Q&A: parse a natural-language question, then narrate a
grounded answer over the analysis spine's reused specialist input.

Public: parse_grade_question, answer_question, QuestionError, GradeQuestion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pitcher_narratives.resolver import extract_pitcher_from_question

__all__ = ["GradeQuestion", "QuestionError", "answer_question", "parse_grade_question"]


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
