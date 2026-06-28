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
    for m in _PCT_VS_AVG.finditer(text):
        x = float(m.group(1))
        out.add(("grade", 100.0 + x if m.group(2).lower() == "above" else 100.0 - x))
    for rx in (_GRADE_AFTER, _GRADE_BEFORE):
        out.update(("grade", float(g)) for g in rx.findall(text))
    out.update(("velo", float(g)) for g in _VELO.findall(text))
    out.update(("pct", float(g)) for g in _PCT.findall(text))
    for a, b in _XRV.findall(text):
        out.add(("xrv100", float(a or b)))
    out.update(("pfx", float(g)) for g in _PFX.findall(text))
    return out
