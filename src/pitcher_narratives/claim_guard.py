"""Deterministic reader-boundary checks for unsupported narrative claims."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from pitcher_narratives.claims import AnalysisCapabilities
from pitcher_narratives.facts import ClaimType, NarrativeClaim

__all__ = ["find_unsupported_claims"]


@dataclass(frozen=True)
class _ClaimRule:
    name: str
    pattern: re.Pattern[str]
    capability: str | None
    claim_types: frozenset[ClaimType] | None = None


_RULES = (
    _ClaimRule(
        "model-driver attribution",
        re.compile(
            r"\b(?:model\s+(?:credited|weighted|relied\s+on)|"
            r"(?:velocity|velo(?:city)?|spin|movement|break|shape|release|extension|"
            r"location|grade|metric|trait)\b[^.!?]{0,80}\b(?:drove|drives|caused|"
            r"explains?|responsible\s+for|model\s+driver|feature\s+importance))\b",
            re.IGNORECASE,
        ),
        "feature_attribution",
        frozenset({ClaimType.MODEL_DRIVER}),
    ),
    _ClaimRule(
        "tunneling",
        re.compile(r"\b(?:tunnel(?:ing|ed)?|tunneling\s+gap)\b", re.IGNORECASE),
        "tunneling_measurement",
        frozenset({ClaimType.TUNNELING}),
    ),
    _ClaimRule(
        "deception",
        re.compile(r"\b(?:decept(?:ion|ive)|deceiv(?:e|ed|es|ing))\b", re.IGNORECASE),
        "tunneling_measurement",
        frozenset({ClaimType.DECEPTION}),
    ),
    _ClaimRule(
        "command",
        re.compile(r"\bcommand(?:ed|ing)?\b", re.IGNORECASE),
        "pitch_targets",
        frozenset({ClaimType.COMMAND, ClaimType.INTENT}),
    ),
    _ClaimRule(
        "intent or target execution",
        re.compile(
            r"\b(?:intent(?:ion|ional|ionally)?|target(?:ed|ing)?|"
            r"execut(?:e|ed|es|ing|ion)|aim(?:ed|ing)?)\b",
            re.IGNORECASE,
        ),
        "pitch_targets",
        frozenset({ClaimType.COMMAND, ClaimType.INTENT}),
    ),
    _ClaimRule(
        "biomechanical cause",
        re.compile(
            r"\b(?:biomechan(?:ic|ical|ics)|mechanical\s+(?:cause|driver|adjustment)|"
            r"mechanism\s+(?:caused|drove|explains?))\b",
            re.IGNORECASE,
        ),
        "biomechanical_causality",
        frozenset({ClaimType.BIOMECHANICAL, ClaimType.CAUSAL}),
    ),
    _ClaimRule(
        "observed hitter behavior",
        re.compile(
            r"\bhitters?\s+(?:chase[ds]?|miss(?:ed|es|ing)?|swing|swung|"
            r"attack(?:ed|s|ing)?|offer(?:ed|s|ing)?|take|takes|took|see|sees|saw|"
            r"couldn['\N{RIGHT SINGLE QUOTATION MARK}]t\s+square)\b",
            re.IGNORECASE,
        ),
        None,
    ),
)

_NEGATION = re.compile(
    r"\b(?:does\s+not|do\s+not|did\s+not|cannot|can't|not|never|without|"
    r"doesn['\N{RIGHT SINGLE QUOTATION MARK}]t|is\s+not|"
    r"isn['\N{RIGHT SINGLE QUOTATION MARK}]t|no\s+evidence\s+of|"
    r"unavailable|insufficient|cannot\s+assess|lacks?\s+(?:the\s+)?evidence)\b",
    re.IGNORECASE,
)
_RARITY_IMPORTANCE = re.compile(
    r"\b(?:NORMAL|OUTLIER)\b[^.!?]{0,100}\b(?:important|importance|irrelevant|driver|"
    r"caused?|because|therefore|so\s+it)\b",
    re.IGNORECASE,
)
_QUALITATIVE_COMPARISON = re.compile(
    r"\b(?:elite|premium|dominant|poor|below[-\s]+average|above[-\s]+average|"
    r"fringe[-\s]+average)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"[^.!?]+[.!?]?", re.MULTILINE)
_CLAUSE_BOUNDARY = re.compile(
    r"[,;:]|\N{EM DASH}|\b(?:but|however|while|whereas)\b|"
    r"\b(?:and|or)\s+(?:he|she|they|it|the\s+pitcher|his|her|their)\b",
    re.IGNORECASE,
)


def _is_negated(sentence: str, match_start: int, match_end: int) -> bool:
    """Return whether negation occurs in the guarded concept's own clause."""
    clause_start = 0
    clause_end = len(sentence)
    for boundary in _CLAUSE_BOUNDARY.finditer(sentence):
        if boundary.end() <= match_start:
            clause_start = boundary.end()
        elif boundary.start() >= match_end:
            clause_end = boundary.start()
            break
    return bool(_NEGATION.search(sentence[clause_start:clause_end]))


def find_unsupported_claims(
    claims: Iterable[NarrativeClaim],
    *,
    capabilities: AnalysisCapabilities | None = None,
) -> list[str]:
    """Return capability warnings scoped to each materialized reader claim."""
    active = capabilities or AnalysisCapabilities()
    warnings: set[str] = set()

    for claim in claims:
        citations = frozenset(claim.fact_ids)
        for sentence_match in _SENTENCE.finditer(claim.text):
            sentence = sentence_match.group(0).strip()
            if not sentence:
                continue

            rarity = _RARITY_IMPORTANCE.search(sentence)
            if rarity and not _is_negated(sentence, rarity.start(), rarity.end()):
                warnings.add(f"rarity label used as model importance or causal evidence: {claim.id}")

            qualitative = _QUALITATIVE_COMPARISON.search(sentence)
            claim_type = getattr(claim, "claim_type", None)
            if (
                qualitative
                and not _is_negated(
                    sentence,
                    qualitative.start(),
                    qualitative.end(),
                )
                and claim_type is not None
                and claim_type is not ClaimType.COMPARATIVE
            ):
                warnings.add(f"misclassified qualitative comparison in {claim.id}: {sentence}")

            for rule in _RULES:
                match = rule.pattern.search(sentence)
                if match is None or _is_negated(sentence, match.start(), match.end()):
                    continue
                claim_type = getattr(claim, "claim_type", None)
                if (
                    claim_type is not None
                    and rule.claim_types is not None
                    and claim_type not in rule.claim_types
                ):
                    warnings.add(f"misclassified {rule.name} in {claim.id}: {sentence}")
                    continue
                if rule.capability is None:
                    warnings.add(f"unsupported {rule.name} in {claim.id}: {sentence}")
                    continue
                evidence_fact_id = active.evidence_fact_id(rule.capability)
                if not active.is_available(rule.capability) or evidence_fact_id not in citations:
                    warnings.add(f"unsupported {rule.name} in {claim.id}: {sentence}")

    return sorted(warnings)
