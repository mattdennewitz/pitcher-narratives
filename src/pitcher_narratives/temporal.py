"""Temporal frame identifiers for multi-frame pitcher context assembly.

Leaf module: no imports from other project modules. Importable by both
context.py and pipeline.py without creating cycles.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["TemporalFrame"]


class TemporalFrame(StrEnum):
    MOST_RECENT = "most_recent"   # the single latest appearance (RECAP)
    RECENT = "recent"             # recent N appearances (REPORT span / CHANGES recent-X)
    PRIOR = "prior"               # prior M appearances (CHANGES)
    SEASON = "season"             # full season baseline
    WINDOW_DAYS = "window_days"   # TRANSITIONAL day-based lookback; removed at the slicer swap
