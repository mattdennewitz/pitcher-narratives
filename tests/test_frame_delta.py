import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pitcher_narratives.frame_delta import (
    build_trend_frame_comparison,
    render_trend_frame_comparison,
)
from pitcher_narratives.temporal import FrameSelection, GameKey, TemporalFrame


@dataclass
class _PT:
    pitch_name: str
    window_velo: float
    window_s_plus: float | None
    window_l_plus: float | None
    window_usage_pct: float
    n_pitches_window: int


@dataclass
class _ReleasePointPitchType:
    pitch_name: str
    window_release_x: float
    window_release_z: float
    window_extension: float


@dataclass
class _ReleasePoint:
    pitch_types: list


@dataclass
class _Ctx:
    arsenal: list
    release_point: _ReleasePoint = None
    frame_type: TemporalFrame = TemporalFrame.RECENT
    frame_id: str = "recent:test"
    source_population: str = "test:2026"
    as_of: date = date(2026, 7, 1)
    frame_row_count: int = 1

    def __post_init__(self):
        if self.release_point is None:
            self.release_point = _ReleasePoint(pitch_types=[])


def _ctx(*pts):
    return _Ctx(arsenal=list(pts))


def _prior(*pts):
    return _Ctx(
        arsenal=list(pts),
        frame_type=TemporalFrame.PRIOR,
        frame_id="prior:test",
    )


def _context_from_emitted_frame(fixture: dict, frame_type: TemporalFrame):
    frame_fixture = fixture["frames"][frame_type.value]
    pitcher = fixture["pitcher"]
    assert all(game["pitcher"] == pitcher for game in frame_fixture["games"])
    selection = FrameSelection.create(
        temporal_frame=frame_type,
        games=frozenset(
            GameKey(
                season=game["season"],
                game_date=date.fromisoformat(game["game_date"]),
                game_pk=game["game_pk"],
            )
            for game in frame_fixture["games"]
        ),
        as_of=date.fromisoformat(fixture["as_of"]),
        source_population=fixture["source_population"],
    )
    return _Ctx(
        arsenal=[_PT(**pitch) for pitch in frame_fixture["pitch_types"]],
        release_point=_ReleasePoint(
            pitch_types=[_ReleasePointPitchType(**release) for release in frame_fixture["release_points"]],
        ),
        frame_type=frame_type,
        frame_id=selection.id,
        source_population=selection.source_population,
        as_of=selection.as_of,
        frame_row_count=frame_fixture["frame_row_count"],
    )


def test_build_comparison_computes_recent_minus_prior():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _prior(_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40))
    cmp = build_trend_frame_comparison(recent, prior)
    d = cmp.deltas[0]
    assert d.pitch_name == "Four-Seam"
    assert d.velo_delta == 2.0
    assert d.s_plus_delta == 10.0
    assert d.usage_delta == 10.0
    assert d.sufficient is True
    assert cmp.prior_insufficient is False


def test_build_comparison_suppresses_below_sample_floor():
    recent = _ctx(_PT("Slider", 88.0, 100.0, 100.0, 30.0, 4))  # < 10 pitches
    prior = _prior(_PT("Slider", 87.0, 95.0, 95.0, 25.0, 40))
    cmp = build_trend_frame_comparison(recent, prior)
    d = cmp.deltas[0]
    assert d.sufficient is False
    assert d.velo_delta is None


def test_build_comparison_flags_prior_insufficient_when_empty():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    cmp = build_trend_frame_comparison(recent, _prior())
    assert cmp.prior_insufficient is True


def test_render_includes_signed_deltas_and_header():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _prior(_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40))
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, prior))
    assert "Recent vs Prior Window" in text
    assert "velo +2.0 mph" in text
    assert "S+ +10" in text


def test_release_language_requires_material_release_change() -> None:
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _prior(_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40))
    recent.release_point = _ReleasePoint([_ReleasePointPitchType("Four-Seam", -1.5, 5.9, 6.4)])
    prior.release_point = _ReleasePoint([_ReleasePointPitchType("Four-Seam", -1.5, 5.9, 6.4)])

    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, prior)).lower()

    assert "possible adjustment" not in text
    assert "shape changes moved together" not in text


def test_build_comparison_does_not_infer_dropped_pitch_from_truncated_arsenal():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _prior(
        _PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40),
        _PT("Curveball", 78.0, 90.0, 90.0, 15.0, 12),
    )
    cmp = build_trend_frame_comparison(recent, prior)
    names = [delta.pitch_name for delta in cmp.deltas]
    assert "Curveball" not in names
    assert "no longer thrown" not in render_trend_frame_comparison(cmp)


def test_build_comparison_ignores_thin_dropped_pitch():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    prior = _prior(
        _PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40),
        _PT("Curveball", 78.0, 90.0, 90.0, 15.0, 4),  # < 10 pitches, too thin
    )
    cmp = build_trend_frame_comparison(recent, prior)
    names = [d.pitch_name for d in cmp.deltas]
    assert "Curveball" not in names


def test_render_prior_insufficient_message():
    recent = _ctx(_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40))
    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, _prior()))
    assert "insufficient" in text.lower()


def test_changes_mode_hedges_release_shape_comovement():
    recent = _Ctx(
        arsenal=[_PT("Four-Seam", 95.0, 110.0, 105.0, 60.0, 40)],
        release_point=_ReleasePoint(pitch_types=[_ReleasePointPitchType("Four-Seam", -1.8, 5.9, 6.4)]),
    )
    prior = _Ctx(
        arsenal=[_PT("Four-Seam", 93.0, 100.0, 100.0, 50.0, 40)],
        release_point=_ReleasePoint(pitch_types=[_ReleasePointPitchType("Four-Seam", -1.6, 6.1, 6.1)]),
        frame_type=TemporalFrame.PRIOR,
        frame_id="prior:test",
    )

    text = render_trend_frame_comparison(build_trend_frame_comparison(recent, prior)).lower()

    assert "consistent with a possible adjustment" in text
    assert "do not identify a mechanism" in text
    assert "deliberate mechanical adjustment" not in text
    assert "drove" not in text


def test_changes_trend_comparison_golden():
    """Pins the full rendering from deterministic emitted RECENT/PRIOR frames."""
    fixture_dir = Path(__file__).parent / "fixtures"
    emitted_frames = json.loads(
        (fixture_dir / "changes_trend_frames.json").read_text(),
    )
    recent = _context_from_emitted_frame(emitted_frames, TemporalFrame.RECENT)
    prior = _context_from_emitted_frame(emitted_frames, TemporalFrame.PRIOR)

    assert recent.frame_id == "recent:3926cf5698ad0c8e"
    assert prior.frame_id == "prior:e39d967102076d45"

    comparison = build_trend_frame_comparison(recent, prior)
    assert comparison.recent_frame_id == recent.frame_id
    assert comparison.prior_frame_id == prior.frame_id

    text = render_trend_frame_comparison(comparison)
    golden = (fixture_dir / "changes_trend_comparison.txt").read_text()
    assert text == golden
