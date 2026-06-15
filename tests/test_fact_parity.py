"""Skeleton: fact-layer parity assertions between scout and engine (Phase 0).

A later refactor phase will fill this file with old-vs-new delta parity
assertions that prove the consolidated fact engine produces identical
outputs to the original per-path scout functions.  Planned assertions
include:

- Velocity-delta parity: scout._check_velocity_drop vs engine function
- Pitching+-delta parity: scout._check_pp_decline vs engine function
- Usage-shift parity: scout._check_usage_shift vs engine function
- S+/L+ divergence parity: scout._check_stuff_location_divergence vs engine function

These will be populated once the new engine functions are written in a
later phase.  The placeholder test below keeps this file collected and
green so CI catches import regressions early.
"""

from __future__ import annotations

import importlib

# ── Placeholder import-smoke test ─────────────────────────────────────


def test_scout_and_engine_import_successfully() -> None:
    """Verify that pitcher_narratives.scout and pitcher_narratives.engine import without error.

    This is the Phase 0 placeholder.  A later phase will add delta-parity
    assertions here once the consolidated engine functions exist.
    """
    assert importlib.import_module("pitcher_narratives.engine") is not None
    assert importlib.import_module("pitcher_narratives.scout") is not None
