"""Tests for morning-run orchestration: artifacts, quiet days."""

import json
from datetime import date

from pydantic_ai.models.test import TestModel

from pitcher_narratives import morning
from pitcher_narratives.scout import ScoredAppearance, Signal


def _app(pid: int, role: str) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"Pitcher {pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=80, score=5.0,
        role=role,
        signals=[Signal("velo_delta", 3.0, "+2.1 mph vs season")],
    )


def _make_minimal_context():
    """Build a minimal PitcherContext suitable for morning-run unit tests."""
    from pitcher_narratives.context import PitcherContext
    from pitcher_narratives.engine import (
        FirstPitchWeaponry,
        HardHitRate,
        PlatoonMix,
        ReleasePointMetrics,
        TemporalContext,
        WorkloadContext,
    )

    return PitcherContext(
        pitcher_name="Pitcher", pitcher_id=0, throws="R", role="SP",
        fastball=None, velocity_arc=None, arsenal=[],
        platoon_mix=PlatoonMix(splits=[], cold_start=True),
        first_pitch=FirstPitchWeaponry(
            entries=[], total_first_pitches_season=0,
            total_first_pitches_window=0, cold_start=True,
        ),
        execution=[], intermediates=[], attributions=[],
        hard_hit_rate=HardHitRate(
            hard_hit_pct=0, season_hard_hit_pct=0, delta="Steady",
            n_batted_balls=0, n_hard_hit=0, small_sample=True, cold_start=True,
        ),
        release_point=ReleasePointMetrics(pitch_types=[], cold_start=True),
        workload=WorkloadContext(appearances=[], max_consecutive_days=0, workload_concern=False),
        temporal=TemporalContext(
            analysis_date=date(2026, 6, 10), current_season=2026,
            current_season_appearances=10, current_season_ip="20.0",
            current_season_first_date="2026-03-28",
            prior_season=2025, prior_season_appearances=0, prior_season_ip="0.0",
            prior_year_relevance="LOW", prior_year_relevance_reason="No data",
        ),
        tto=None, cross_season_summary=None, arsenal_trend=None,
    )


def _patch_data(monkeypatch):
    """Stub all data-loading seams in morning.py."""
    monkeypatch.setattr(
        morning, "scout_appearances",
        lambda **kw: [_app(1, "SP"), _app(2, "RP")],
    )
    monkeypatch.setattr(morning, "_load_pitcher_context", lambda pid: _make_minimal_context())


def _selector_model():
    return TestModel(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
            {
                "pitcher_id": 2, "category": "red_flag",
                "angle": "Suspicious spike", "conviction": "low",
                "conviction_reason": "Single game.",
            },
        ],
    })


def test_run_morning_writes_all_artifacts(tmp_path, monkeypatch):
    _patch_data(monkeypatch)
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(custom_output_text="A summary."),
    )
    assert run_dir == tmp_path / "2026-06-10"
    digest = (run_dir / "digest.md").read_text()
    assert digest.startswith("# Morning Digest — 2026-06-10")
    assert "A summary." in digest
    assert "## The Full Board" in digest
    assert "Run cost" in digest

    slate = json.loads((run_dir / "slate.json").read_text())
    assert slate["game_date"] == "2026-06-10"
    assert slate["picks"][0]["pitcher_id"] == 1
    assert slate["names"]["1"] == "Pitcher 1"

    assert "CANDIDATES" in (run_dir / "briefing.md").read_text()
    usage = json.loads((run_dir / "usage.json").read_text())
    assert any(rec["stage"] == "selector" for rec in usage)


def test_run_morning_single_event_loop(tmp_path, monkeypatch):
    """Selector and writers share one event loop: provider-client state
    created during selection must not leak into a second loop (observed
    live: the first writer call failed with 'Event bound to a different
    event loop' and the top pick always fell back)."""
    import asyncio

    loops: list = []

    class _LoopRecorder(TestModel):
        async def request(self, messages, model_settings, model_request_parameters):
            loops.append(asyncio.get_running_loop())
            return await super().request(
                messages, model_settings, model_request_parameters
            )

    selector = _LoopRecorder(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
        ],
    })
    writer = _LoopRecorder(custom_output_text="A summary.")

    _patch_data(monkeypatch)
    morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
        _selector_override=selector, _writer_override=writer,
    )
    assert len(loops) >= 2
    assert all(lp is loops[0] for lp in loops)


def test_run_morning_notes_failed_writers_in_cost_block(tmp_path, monkeypatch):
    """A fallen-back writer is disclosed in the cost footer."""

    class _ExplodingWriter(TestModel):
        async def request(self, messages, model_settings, model_request_parameters):
            raise RuntimeError("provider error")

    _patch_data(monkeypatch)
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=_ExplodingWriter(),
    )
    digest = (run_dir / "digest.md").read_text()
    assert "2 writer call(s) failed" in digest


def test_run_morning_quiet_day_returns_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(morning, "scout_appearances", lambda **kw: [])
    result = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
    )
    assert result is None
    assert not list(tmp_path.iterdir())


def test_full_board_lists_beyond_candidate_cap(tmp_path, monkeypatch):
    """The Full Board shows every scored appearance even when the
    selector only sees the top N per role."""
    apps = [_app(1, "SP")] + [
        ScoredAppearance(
            pitcher_id=pid, pitcher_name=f"Pitcher {pid}", throws="R",
            game_date=date(2026, 6, 10), game_pk=pid, n_pitches=40,
            score=float(5 - pid), role="SP",
            signals=[Signal("velo_delta", 3.0, "+1.6 mph vs season")],
        )
        for pid in range(2, 5)
    ]
    monkeypatch.setattr(morning, "scout_appearances", lambda **kw: apps)
    monkeypatch.setattr(morning, "_load_pitcher_context", lambda pid: _make_minimal_context())
    selector = TestModel(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
        ],
    })
    run_dir = morning.run_morning(
        window_days=1, top_n=1, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
        _selector_override=selector,
        _writer_override=TestModel(custom_output_text="A summary."),
    )
    digest = (run_dir / "digest.md").read_text()
    board = digest[digest.index("## The Full Board"):]
    for pid in range(1, 5):
        assert f"Pitcher {pid}" in board       # all scored, not just top_n=1
    briefing = (run_dir / "briefing.md").read_text()
    assert "Pitcher 4" not in briefing          # selector saw only the cap


def test_run_morning_duplicate_pitcher_keeps_highest_scored(tmp_path, monkeypatch):
    """A pitcher with two scored appearances keys to the higher-scored one."""
    high = _app(1, "SP")
    low = ScoredAppearance(
        pitcher_id=1, pitcher_name="Pitcher 1", throws="R",
        game_date=date(2026, 6, 9), game_pk=2, n_pitches=30, score=2.0,
        role="SP",
        signals=[Signal("workload_flag", 1.0, "2 consecutive days")],
    )
    monkeypatch.setattr(
        morning, "scout_appearances",
        lambda **kw: [high, low, _app(2, "RP")],
    )
    monkeypatch.setattr(morning, "_load_pitcher_context", lambda pid: _make_minimal_context())
    run_dir = morning.run_morning(
        window_days=2, top_n=25, min_pitches=20,
        provider="gemini", persona_id="scout", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(custom_output_text="A summary."),
    )
    briefing = (run_dir / "briefing.md").read_text()
    assert "80 pitches" in briefing            # high-scored appearance present
    digest = (run_dir / "digest.md").read_text()
    assert run_dir == tmp_path / "2026-06-10"  # game date = max date
