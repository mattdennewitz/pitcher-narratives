"""Pure population-deviation primitive.

The reusable core of the "compare-to-population, report-the-residual"
mechanism (design 2026-07-08-game-shape-deviation-gate). A specialist supplies
an observed delta and a population (median_exp_delta, mad) cell; this returns a
robust, directional, gated Deviation. No I/O, no domain knowledge — the TTO
evaluator (and future specialists) own the join and the framing.
"""

from __future__ import annotations

from dataclasses import dataclass

# Empirically calibrated (design §3.3). Asymmetric: a fatigue (harmful) claim
# must be undeniable; a stamina (beneficial) claim surfaces more readily.
Z_GATE_FATIGUE: float = -2.0
Z_GATE_STAMINA: float = 1.5

_MAD_TO_SIGMA: float = 1.4826


@dataclass(frozen=True)
class Deviation:
    """A robust, directional, gated deviation of one observed delta from a
    population cell."""

    residual: float
    robust_z: float
    direction: str  # "fatigue" (harmful side) | "stamina" (beneficial side)
    material: bool


def evaluate_deviation(
    actual_delta: float,
    median_exp_delta: float,
    mad: float,
    *,
    z_gate_fatigue: float = Z_GATE_FATIGUE,
    z_gate_stamina: float = Z_GATE_STAMINA,
) -> Deviation:
    """Compare an observed delta against a population (median, MAD) cell.

    ``direction`` is "fatigue" when the residual is on the harmful side (the
    metric dropped MORE than the population expected, i.e. residual < 0) and
    "stamina" when it held/improved beyond expectation (residual > 0). The gate
    is asymmetric: a fatigue Deviation is material at ``z <= z_gate_fatigue``; a
    stamina Deviation at ``z >= z_gate_stamina``. A non-positive ``mad`` (a
    degenerate/zero-dispersion cell) yields z=0 and non-material — defensive;
    callers exclude the pass-1 Δ≡0 reference upstream.
    """
    residual = actual_delta - median_exp_delta
    if mad <= 0.0:
        return Deviation(residual=residual, robust_z=0.0, direction="stamina" if residual >= 0 else "fatigue", material=False)
    robust_z = residual / (_MAD_TO_SIGMA * mad)
    if robust_z < 0:
        return Deviation(residual, robust_z, "fatigue", robust_z <= z_gate_fatigue)
    return Deviation(residual, robust_z, "stamina", robust_z >= z_gate_stamina)
