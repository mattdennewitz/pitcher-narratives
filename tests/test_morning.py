"""Tests for morning-run orchestration: artifacts, quiet days."""

import json
from datetime import date

import polars as pl
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


def _patch_data(monkeypatch):
    """Stub all data-loading seams in morning.py."""
    monkeypatch.setattr(
        morning, "scout_appearances",
        lambda **kw: [_app(1, "SP"), _app(2, "RP")],
    )
    season = pl.DataFrame({
        "pitcher": [1, 2], "season": [2026, 2026], "n_pitches": [900, 400],
        "P+": [104.0, 99.0], "S+": [112.0, 105.0], "L+": [96.0, 101.0],
    })
    types = pl.DataFrame({
        "pitcher": [1], "season": [2026], "pitch_type": ["FF"],
        "n_pitches": [500], "S+": [115.0], "L+": [98.0], "usage_pct": [55.6],
    })
    monkeypatch.setattr(morning, "_load_baselines", lambda: (season, types, {}))


def _selector_model():
    return TestModel(custom_output_args={
        "starters": [{
            "pitcher_id": 1, "category": "clean_breakout",
            "angle": "Velo spike", "conviction": "medium",
            "conviction_reason": "Shape agrees.",
        }],
        "relievers": [{
            "pitcher_id": 2, "category": "red_flag",
            "angle": "Suspicious spike", "conviction": "low",
            "conviction_reason": "Single game.",
        }],
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
    assert slate["picks"]["starters"][0]["pitcher_id"] == 1
    assert slate["names"]["1"] == "Pitcher 1"

    assert "STARTERS" in (run_dir / "briefing.md").read_text()
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
        "starters": [{
            "pitcher_id": 1, "category": "clean_breakout",
            "angle": "Velo spike", "conviction": "medium",
            "conviction_reason": "Shape agrees.",
        }],
        "relievers": [],
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
    season = pl.DataFrame({
        "pitcher": [1, 2], "season": [2026, 2026], "n_pitches": [900, 400],
        "P+": [104.0, 99.0], "S+": [112.0, 105.0], "L+": [96.0, 101.0],
    })
    types = pl.DataFrame({
        "pitcher": [1], "season": [2026], "pitch_type": ["FF"],
        "n_pitches": [500], "S+": [115.0], "L+": [98.0], "usage_pct": [55.6],
    })
    monkeypatch.setattr(morning, "_load_baselines", lambda: (season, types, {}))
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
