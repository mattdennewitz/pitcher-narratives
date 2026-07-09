"""Tests for the TTO deviation evaluator (join + gate + P+ veto)."""

import polars as pl

from pitcher_narratives.engine.tto import TTOAnalysis, TTOSplit, evaluate_tto_deviations

_BASE = pl.DataFrame(
    {
        "cohort_key": ["LEAGUE_SP"] * 4,
        "pass_num": [2, 2, 3, 3],
        "metric": ["velo", "pplus", "velo", "pplus"],
        "median_exp_delta": [-0.4, -1.8, -1.1, -3.5],
        "mad": [1.0, 2.0, 1.0, 2.0],
        "n": [5000] * 4,
    }
)


def _split(p, velo, pplus, pitches=40):
    return TTOSplit(
        pass_number=p,
        pitches=pitches,
        avg_velo=velo,
        avg_p_plus=pplus,
        avg_s_plus=None,
        fb_p_plus=None,
        sec_p_plus=None,
        velo_delta="",
        p_plus_delta="",
        fb_p_plus_delta="",
        sec_p_plus_delta="",
        pitch_types=[],
        platoon=[],
        small_sample=False,
    )


def _tto(*splits):
    return TTOAnalysis(splits=list(splits), available=True, summary="", mix_shifts=[])


def test_typical_fade_yields_no_deviation():
    # pass3 velo -1.0 (vs median -1.1, z=+0.07): typical
    # pass3 pplus -3.0 (vs median -3.5, z=+0.17): typical
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 95.0, 102.0))
    assert evaluate_tto_deviations(tto, _BASE) == []


def test_corroborated_fatigue_is_surfaced():
    # Δvelo -4.5 (z=-2.29, material fatigue), Δpplus -10.0 (z=-2.19, material fatigue)
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 95.0))
    devs = evaluate_tto_deviations(tto, _BASE)
    metrics = {d.metric for d in devs}
    assert "velo" in metrics and "pplus" in metrics
    assert all(d.direction == "fatigue" for d in devs)


def test_velo_drop_with_holding_pplus_is_vetoed():
    # Δvelo -4.5 (z=-2.29, material fatigue), Δpplus -3.3 (z=+0.07, typical) → velo vetoed
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 101.7))
    devs = evaluate_tto_deviations(tto, _BASE)
    assert all(d.metric != "velo" for d in devs)  # velo vetoed
    assert devs == []  # pplus is typical, so nothing surfaces at all


def test_resilience_pplus_positive_is_surfaced_not_vetoed():
    # Δvelo -4.5 (z=-2.29, material fatigue), Δpplus +1.5 (z=+1.69, material stamina)
    # → velo vetoed (unsupported), pplus stamina surfaces independently
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 106.5))
    devs = evaluate_tto_deviations(tto, _BASE)
    assert all(d.metric != "velo" for d in devs)
    pplus = [d for d in devs if d.metric == "pplus"]
    assert pplus and pplus[0].direction == "stamina"


def test_missing_baseline_degrades_to_silence():
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 88.0, 90.0))
    assert evaluate_tto_deviations(tto, None) == []


def test_unavailable_tto_is_silent():
    assert evaluate_tto_deviations(TTOAnalysis([], available=False, summary="", mix_shifts=[]), _BASE) == []


def test_small_sample_pass_is_skipped():
    # pitches below min_pitches threshold should not produce a deviation
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 95.0, pitches=10))
    assert evaluate_tto_deviations(tto, _BASE) == []


def test_thin_baseline_cell_is_skipped_even_with_material_z():
    # Same corroborated-fatigue shape as test_corroborated_fatigue_is_surfaced
    # (material z on both metrics), but the pass-3 baseline cell's n is below
    # the floor -- the finding must be suppressed rather than manufactured
    # from a volatile MAD (design §3.3 sample-adequacy guard).
    thin_base = pl.DataFrame(
        {
            "cohort_key": ["LEAGUE_SP"] * 4,
            "pass_num": [2, 2, 3, 3],
            "metric": ["velo", "pplus", "velo", "pplus"],
            "median_exp_delta": [-0.4, -1.8, -1.1, -3.5],
            "mad": [1.0, 2.0, 1.0, 2.0],
            "n": [5000, 5000, 40, 40],
        }
    )
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 95.0))
    assert evaluate_tto_deviations(tto, thin_base) == []
