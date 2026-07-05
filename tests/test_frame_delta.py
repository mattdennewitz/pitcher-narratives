from dataclasses import dataclass
from pathlib import Path

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
class _ReleasePoint:
    pitch_types: list


@dataclass
class _Ctx:
    arsenal: list
    release_point: _ReleasePoint = None

    def __post_init__(self):
        if self.release_point is None:
            self.release_point = _ReleasePoint(pitch_types=[])


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


def test_build_comparison_surfaces_dropped_pitch():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _ctx(
        _PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40),
        _PT("Curveball", 78.0, 90.0, 90.0, 15.0, 12),
    )
    cmp = build_trend_frame_comparison(recent, prior)
    dropped = [d for d in cmp.deltas if d.pitch_name == "Curveball"]
    assert len(dropped) == 1
    d = dropped[0]
    assert d.dropped is True
    assert d.sufficient is False
    assert d.velo_delta is None
    assert cmp.prior_insufficient is False
    text = render_trend_frame_comparison(cmp)
    assert "Curveball: no longer thrown" in text


def test_build_comparison_ignores_thin_dropped_pitch():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _ctx(
        _PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40),
        _PT("Curveball", 78.0, 90.0, 90.0, 15.0, 4),  # < 10 pitches, too thin
    )
    cmp = build_trend_frame_comparison(recent, prior)
    names = [d.pitch_name for d in cmp.deltas]
    assert "Curveball" not in names


def test_render_prior_insufficient_message():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, _ctx()))
    assert "insufficient" in text.lower()


def test_changes_trend_comparison_golden():
    """Pins the rendered RECENT-vs-PRIOR comparison block for pitcher 592155
    at --recent 10 --prior 10, generated via the one-off script in
    task-8-brief.md Step 2 (generate-and-verify, not hand-authored)."""
    from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context
    from pitcher_narratives.data import load_pitcher_data

    data = load_pitcher_data(592155, recent_appearances=10)
    recent = assemble_pitcher_context(data)
    prior = assemble_prior_context(data, recent_n=10, prior_m=10)
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, prior))
    golden = (Path(__file__).parent / "fixtures" / "changes_trend_comparison.txt").read_text()
    assert text == golden
