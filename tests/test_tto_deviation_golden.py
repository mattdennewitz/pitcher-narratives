"""Golden fader-vs-typical proof for the game-shape deviation gate.

Real-data regression: with the offline LEAGUE_SP baseline artifact built
(``python -m pitcher_narratives.tto_baseline``), a known deep-outing fader must
trip a material within-game deviation and a league-median starter must stay
silent. Skips cleanly on a checkout without ``PITCHER_NARRATIVES_DATA_DIR`` or
without the built ``var/tto_baseline.parquet`` so CI-without-data stays green.

Ids + z-evidence discovered empirically against the real baseline (design
2026-07-08-game-shape-deviation-gate §3.3 calibration), gates -2.0 / +1.5:

  592332 Kevin Gausman (fader):  pass-4 pplus z=-5.71 fatigue (P+ -19.1),
                                 pass-4 velo  z=+2.00 stamina -> NON-EMPTY.
  624133 Ranger Suárez (typical): every cell within [-0.10, -0.05] -> [].

Across 45 sampled starters the pass-2/3 cells (huge league n) were uniformly
within the gates (window-aggregation shrinkage, §3.3); materiality only emerged
at pass 4 (deep outings). 8/45 flagged, 37/45 silent — a clean separation, so
the -2.0 / +1.5 defaults were kept unchanged.
"""

from __future__ import annotations

import os

import pytest

from pitcher_narratives.data import load_tto_baseline

pytestmark = pytest.mark.skipif(
    not os.environ.get("PITCHER_NARRATIVES_DATA_DIR") or load_tto_baseline() is None,
    reason="needs PITCHER_NARRATIVES_DATA_DIR and a built var/tto_baseline.parquet",
)

POWER_FADER_ID = 592332  # Kevin Gausman — pplus collapses deep in games
TYPICAL_SP_ID = 624133  # Ranger Suárez — textbook league-median fade


def test_known_fader_is_material_and_typical_is_silent():
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.engine.tto import compute_tto_analysis, evaluate_tto_deviations

    base = load_tto_baseline()
    assert base is not None, "run `python -m pitcher_narratives.tto_baseline` first"

    def devs(pid):
        data = load_pitcher_data(pid, recent_appearances=10)
        return evaluate_tto_deviations(compute_tto_analysis(data), base)

    assert devs(POWER_FADER_ID), "known fader (Gausman) should trip a material deviation"
    assert devs(TYPICAL_SP_ID) == [], "league-median starter (Suárez) should be silent"
