from dataclasses import dataclass

from pitcher_narratives.frame_delta import (
    build_trend_frame_comparison,
    render_trend_frame_comparison,
)


@dataclass
class _PT:
    pitch_name: str
    window_velo: float
    window_s_plus: float | None
    window_l_plus: float | None
    window_usage_pct: float
    n_pitches_window: int


@dataclass
class _Ctx:
    arsenal: list


def _ctx(*pts):
    return _Ctx(arsenal=list(pts))


def test_build_comparison_computes_recent_minus_prior():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _ctx(_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40))
    cmp = build_trend_frame_comparison(recent, prior)
    d = cmp.deltas[0]
    assert d.pitch_name == "Four-Seam"
    assert d.velo_delta == 2.0
    assert d.s_plus_delta == 10.0
    assert d.usage_delta == 10.0
    assert d.sufficient is True
    assert cmp.prior_insufficient is False


def test_build_comparison_suppresses_below_sample_floor():
    recent = _ctx(_PT("Slider", 88.0, 100.0, 100.0, 30.0, 4))   # < 10 pitches
    prior = _ctx(_PT("Slider", 87.0, 95.0, 95.0, 25.0, 40))
    cmp = build_trend_frame_comparison(recent, prior)
    d = cmp.deltas[0]
    assert d.sufficient is False
    assert d.velo_delta is None


def test_build_comparison_flags_prior_insufficient_when_empty():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    cmp = build_trend_frame_comparison(recent, _ctx())
    assert cmp.prior_insufficient is True


def test_render_includes_signed_deltas_and_header():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _ctx(_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40))
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, prior))
    assert "Recent vs Prior Window" in text
    assert "velo +2.0 mph" in text
    assert "S+ +10" in text


def test_render_prior_insufficient_message():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, _ctx()))
    assert "insufficient" in text.lower()
