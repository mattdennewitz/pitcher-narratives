"""Temporal frame identifiers for multi-frame pitcher context assembly.

Leaf module: no imports from other project modules. Importable by both
context.py and pipeline.py without creating cycles.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["TemporalFrame", "_DEFAULT_RECENT_APPEARANCES"]


class TemporalFrame(StrEnum):
    MOST_RECENT = "most_recent"   # the single latest appearance (RECAP)
    RECENT = "recent"             # recent N appearances (REPORT span / CHANGES recent-X)
    PRIOR = "prior"               # prior M appearances (CHANGES)
    SEASON = "season"             # full season baseline


# Default analysis window, in most-recent appearances. Derived empirically
# (~30d of a reliever's usage) and floored at the thin-frame threshold
# (_THIN_APPEARANCES = 10); a smaller default would make every frame "thin".
# Measured 2026-07-01: pitcher 592155 (Cam Booser, RP) = 10 appearances in
# the last 30d; pitcher 676571 (PJ Poulin) = 13. Both clear the floor;
# 592155's count sets the default since it is the fixture pitcher and the
# lower of the two measured counts.
_DEFAULT_RECENT_APPEARANCES = 10
