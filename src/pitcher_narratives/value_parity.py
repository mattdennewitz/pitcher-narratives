"""Deterministic value-parity check (advisory): flags capsule numbers that do
not trace to anything the writer saw. See the 2026-06-28 capsule-fact-checking
design. Advisory only — never blocks or triggers a revision."""

from __future__ import annotations

import re

from pydantic import BaseModel

__all__ = ["MetricValue", "ValueParityReport", "extract_metric_values", "check_value_parity"]

MetricValue = tuple[str, float]
"""(metric_class, value). Cross-class values never match; within-class match by tolerance."""

# "28% above average" -> ("grade", 128); "13%below average" -> ("grade", 87).
# \s* (not \s+) before above/below so a missing space ("13%below") still parses.
_PCT_VS_AVG = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%?\s*(above|below)\s+(?:league\s+)?average", re.I)
# grade: "S+ 130", "S+ of 130", "Stuff+ 130", "130 Stuff+", "130 S+".
# The number must immediately follow the label (optionally "of "); a wider gap
# would capture an unrelated nearby number ("S+ sits 95" — 95 is a velocity).
_GRADE_AFTER = re.compile(r"(?:S\+|P\+|L\+|Stuff\+|Location\+|Pitching\+)\s*(?:of\s+)?(\d{2,3})\b")
_GRADE_BEFORE = re.compile(r"\b(\d{2,3})\s+(?:S\+|P\+|L\+|Stuff\+|Location\+|Pitching\+)")
_VELO = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*mph")
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)")
# Fix: use [^\d+\-] so the quantifier doesn't consume the leading sign of the value.
_XRV = re.compile(
    r"xRV100[^\d+\-]{0,14}([+\-]?\d+\.\d{1,2})"
    r"|"
    r"([+\-]?\d+\.\d{1,2})[^\d+\-]{0,14}xRV100",
    re.I,
)
_PFX = re.compile(r"(-?\d+\.\d)\s*(?:in\b|inches)")


def extract_metric_values(text: str) -> set[MetricValue]:
    """Extract (metric_class, value) tuples from prose or rendered tables."""
    out: set[MetricValue] = set()
    # Track spans consumed by _PCT_VS_AVG so we don't double-count them as
    # bare percentages (e.g. "28% above average" → grade 128, NOT also pct 28).
    pct_vs_avg_spans: list[tuple[int, int]] = []
    for m in _PCT_VS_AVG.finditer(text):
        x = float(m.group(1))
        out.add(("grade", 100.0 + x if m.group(2).lower() == "above" else 100.0 - x))
        pct_vs_avg_spans.append(m.span())
    for rx in (_GRADE_AFTER, _GRADE_BEFORE):
        out.update(("grade", float(g)) for g in rx.findall(text))
    out.update(("velo", float(g)) for g in _VELO.findall(text))
    for m in _PCT.finditer(text):
        if not any(s <= m.start() < e for s, e in pct_vs_avg_spans):
            out.add(("pct", float(m.group(1))))
    for a, b in _XRV.findall(text):
        out.add(("xrv100", float(a or b)))
    out.update(("pfx", float(g)) for g in _PFX.findall(text))
    return out


class ValueParityReport(BaseModel):
    """Advisory result: capsule values not traceable to the union."""

    unmatched: list[str]

    @property
    def is_clean(self) -> bool:
        return not self.unmatched


# Per-class match tolerance. Grades are whole-number (+/-1); others +/-0.5.
_TOLERANCE: dict[str, float] = {
    "grade": 1.0,
    "velo": 0.5,
    "pct": 0.5,
    "xrv100": 0.05,
    "pfx": 0.5,
    "delta": 1.0,
}

# Hedge markers: a number right after one is the writer signaling uncertainty
# and is not flagged regardless of union support.
_HEDGE = re.compile(r"\b(roughly|about|around|approximately)\b\s*~?\s*-?\d", re.I)
# Characters past the hedge to scan for the hedged number + its unit/metric
# token (xRV100 trails its value by a few chars). Kept short so a hedge doesn't
# suppress an unrelated metric further along the sentence.
_HEDGE_WINDOW = 16


def _hedged_metric_values(text: str) -> set[MetricValue]:
    """Return the (class, value) tuples the writer hedged ("around 95 mph").

    Each hedged value is extracted from a window starting at the hedge word, so
    it carries the correct metric class (no cross-class suppression leak) and
    the correct sign (the full number, including a leading '-', sits inside the
    window). Re-using ``extract_metric_values`` keeps hedge classification
    identical to capsule classification, so exact (class, value) membership works.
    """
    out: set[MetricValue] = set()
    for m in _HEDGE.finditer(text):
        out |= extract_metric_values(text[m.start() : m.end() + _HEDGE_WINDOW])
    return out


def check_value_parity(capsule: str, union: str) -> ValueParityReport:
    """Flag capsule metric-values with no same-class match (within tolerance)
    anywhere in the union. Advisory; cross-class values never satisfy each
    other; hedged and indeterminate-class numbers are not flagged."""
    union_values = extract_metric_values(union)
    hedged = _hedged_metric_values(capsule)
    unmatched: list[str] = []
    for cls, val in sorted(extract_metric_values(capsule)):
        if (cls, val) in hedged:  # class-aware: a hedged velo can't suppress a grade
            continue
        tol = _TOLERANCE.get(cls, 0.5)  # default keeps a new class advisory, not a crash
        if any(u_cls == cls and abs(u_val - val) <= tol for u_cls, u_val in union_values):
            continue
        unmatched.append(f"{cls}={val:g} (no match in source data)")
    return ValueParityReport(unmatched=unmatched)
