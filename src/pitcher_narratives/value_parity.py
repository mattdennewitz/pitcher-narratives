"""Deterministic value-parity check (advisory): flags capsule numbers that do
not trace to anything the writer saw. See the 2026-06-28 capsule-fact-checking
design. Advisory only — never blocks or triggers a revision."""

from __future__ import annotations

import re

from pydantic import BaseModel

__all__ = ["MetricValue", "ValueParityReport", "extract_metric_values", "check_value_parity"]

MetricValue = tuple[str, float]
"""(metric_class, value). Cross-class values never match; within-class match by tolerance."""

# "28% above average" -> ("grade", 128); "13% below average" -> ("grade", 87).
_PCT_VS_AVG = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%?\s+(above|below)\s+(?:league\s+)?average", re.I)
# grade: "S+ 130", "Stuff+ 130", "130 Stuff+", "130 S+"
_GRADE_AFTER = re.compile(r"(?:S\+|P\+|L\+|Stuff\+|Location\+|Pitching\+)\D{0,8}(\d{2,3})\b")
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

# Hedge markers: a number within ~20 chars after is the writer signaling
# uncertainty; not flagged regardless of union support.
_HEDGE = re.compile(r"\b(roughly|about|around|approximately)\b\s*~?\s*-?\d", re.I)


def _hedged_values(text: str) -> set[float]:
    """Return numeric values that appear immediately after a hedge word.

    The regex consumes the first digit of the number; we step back one
    character (``m.end() - 1``) so that ``re.search`` can find the full
    multi-digit value.
    """
    out: set[float] = set()
    for m in _HEDGE.finditer(text):
        num = re.search(r"-?\d+(?:\.\d+)?", text[m.end() - 1 :])
        if num:
            out.add(float(num.group(0)))
    return out


def check_value_parity(capsule: str, union: str) -> ValueParityReport:
    """Flag capsule metric-values with no same-class match (within tolerance)
    anywhere in the union. Advisory; cross-class values never satisfy each
    other; hedged and indeterminate-class numbers are not flagged."""
    union_values = extract_metric_values(union)
    hedged = _hedged_values(capsule)
    unmatched: list[str] = []
    for cls, val in sorted(extract_metric_values(capsule)):
        if val in hedged:
            continue
        tol = _TOLERANCE.get(cls, 0.5)  # default keeps a new class advisory, not a crash
        if any(u_cls == cls and abs(u_val - val) <= tol for u_cls, u_val in union_values):
            continue
        unmatched.append(f"{cls}={val:g} (no match in source data)")
    return ValueParityReport(unmatched=unmatched)
