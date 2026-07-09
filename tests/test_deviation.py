from pitcher_narratives.engine.deviation import (
    Deviation, evaluate_deviation, Z_GATE_FATIGUE, Z_GATE_STAMINA,
)


def test_robust_z_uses_mad_scaling():
    # actual −4.0 vs expected −1.0, mad 1.0 → z = (−3.0)/(1.4826*1.0) ≈ −2.02
    d = evaluate_deviation(-4.0, -1.0, 1.0)
    assert round(d.robust_z, 2) == -2.02
    assert d.direction == "fatigue"
    assert d.material is True  # −2.02 <= −2.0


def test_fatigue_gate_is_conservative():
    # z ≈ −1.9 does NOT trip the −2.0 fatigue gate
    d = evaluate_deviation(-3.8, -1.0, 1.0)  # (−2.8)/1.4826 ≈ −1.89
    assert d.material is False


def test_stamina_gate_is_easier():
    # holds better than expected: actual +0.2 vs expected −3.5, mad 1.5 → z ≈ +1.66
    d = evaluate_deviation(0.2, -3.5, 1.5)
    assert d.direction == "stamina"
    assert d.robust_z > Z_GATE_STAMINA
    assert d.material is True


def test_typical_is_not_material():
    d = evaluate_deviation(-1.2, -1.0, 1.0)  # z ≈ −0.13
    assert d.material is False


def test_zero_mad_is_guarded_not_divide_by_zero():
    # defensive: pass-1 exclusion is upstream, but a degenerate cell must not crash
    d = evaluate_deviation(-2.0, -1.0, 0.0)
    assert d.material is False
    assert d.robust_z == 0.0
