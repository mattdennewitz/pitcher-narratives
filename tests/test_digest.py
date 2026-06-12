"""Tests for the morning digest: cues, writers, assembly."""

import asyncio
from datetime import date

import polars as pl
from pydantic_ai.models.test import TestModel

from pitcher_narratives.curator import CurationPick, CurationSlate
from pitcher_narratives.digest import (
    assemble_digest,
    build_story_cue,
    render_full_board,
    write_pick_summaries,
)
from pitcher_narratives.personas import DEFAULT_PERSONA
from pitcher_narratives.scout import ScoredAppearance, Signal


def _app(pid: int, role: str = "SP", score: float = 5.0) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"Pitcher {pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=80, score=score,
        role=role,
        signals=[Signal("velo_delta", 3.0, "+2.1 mph vs season")],
    )


def _pick(pid: int) -> CurationPick:
    return CurationPick(
        pitcher_id=pid, category="clean_breakout",
        angle="Velocity spike with stuff gain", conviction="medium",
        conviction_reason="One game, but shape agrees.",
    )


def _season_baseline() -> pl.DataFrame:
    return pl.DataFrame({
        "pitcher": [1], "season": [2026], "n_pitches": [900],
        "P+": [104.0], "S+": [112.0], "L+": [96.0],
    })


def _type_baseline() -> pl.DataFrame:
    return pl.DataFrame({
        "pitcher": [1, 1], "season": [2026, 2026],
        "pitch_type": ["FF", "SL"], "n_pitches": [500, 400],
        "S+": [115.0, 108.0], "L+": [98.0, 93.0],
        "usage_pct": [55.6, 44.4],
    })


# ── Cue builder ─────────────────────────────────────────────────────


def test_story_cue_contains_all_layers():
    cue = build_story_cue(
        _app(1), _pick(1),
        season_baseline=_season_baseline(),
        type_baseline=_type_baseline(),
        season_velo=94.8,
    )
    assert "Pitcher 1" in cue
    assert "2026-06-10" in cue and "80 pitches" in cue and "SP" in cue
    assert "velo_delta" in cue and "+2.1 mph vs season" in cue
    assert "clean_breakout" in cue
    assert "Velocity spike with stuff gain" in cue
    assert "medium" in cue
    # season context slice
    assert "104" in cue and "112" in cue and "96" in cue
    assert "FF" in cue and "55.6" in cue
    assert "94.8" in cue


def test_story_cue_handles_missing_baselines():
    """A pick with no baseline rows still renders (signals + angle only)."""
    empty = pl.DataFrame(schema={"pitcher": pl.Int64, "season": pl.Int64})
    cue = build_story_cue(
        _app(1), _pick(1),
        season_baseline=empty, type_baseline=empty, season_velo=None,
    )
    assert "Velocity spike with stuff gain" in cue
    assert "no season baseline available" in cue


# ── Writers ─────────────────────────────────────────────────────────


def test_write_pick_summaries_returns_text_per_pick():
    apps = {1: _app(1), 2: _app(2, role="RP")}
    cues = {1: "cue one", 2: "cue two"}
    picks = [_pick(1), _pick(2)]
    summaries = asyncio.run(write_pick_summaries(
        picks, cues, apps, provider="gemini", persona=DEFAULT_PERSONA,
        _model_override=TestModel(custom_output_text="A tailored summary."),
    ))
    assert summaries[1] == "A tailored summary."
    assert summaries[2] == "A tailored summary."


def test_write_pick_summaries_falls_back_on_failure():
    """A writer that raises degrades to a deterministic cue rendering."""

    class _ExplodingModel(TestModel):
        async def request(self, messages, model_settings, model_request_parameters):
            raise RuntimeError("provider error")

    apps = {1: _app(1)}
    cues = {1: "the cue text"}
    summaries = asyncio.run(write_pick_summaries(
        [_pick(1)], cues, apps, provider="gemini", persona=DEFAULT_PERSONA,
        _model_override=_ExplodingModel(),
    ))
    assert "[summary unavailable" in summaries[1]
    assert "Velocity spike with stuff gain" in summaries[1]


# ── Full Board + assembly ───────────────────────────────────────────


def test_render_full_board_groups_and_sorts():
    board = render_full_board([
        _app(1, "SP", 9.0), _app(2, "RP", 7.0), _app(3, "SP", 3.0),
    ])
    assert board.index("Starters") < board.index("Pitcher 1") < board.index("Pitcher 3")
    assert board.index("Relievers") < board.index("Pitcher 2")
    assert "velo_delta" in board and "+2.1 mph vs season" in board
    assert "9.0" in board


def test_assemble_digest_layout():
    slate = CurationSlate(starters=[_pick(1)], relievers=[_pick(2)])
    apps = {1: _app(1), 2: _app(2, role="RP")}
    digest = assemble_digest(
        slate=slate,
        summaries={1: "SP summary text.", 2: "RP summary text."},
        appearances=apps,
        board=[_app(1), _app(2, role="RP")],
        game_date=date(2026, 6, 10),
        cost_block="── Run cost ── total $0.10 (5s)",
    )
    assert digest.startswith("# Morning Digest — 2026-06-10")
    i_sp = digest.index("## Starters")
    i_rp = digest.index("## Relievers")
    i_board = digest.index("## The Full Board")
    assert i_sp < i_rp < i_board
    assert i_sp < digest.index("SP summary text.") < i_rp
    assert i_rp < digest.index("RP summary text.") < i_board
    assert "clean_breakout" in digest          # category badge
    assert "Pitcher 1" in digest               # name resolved from scout data
    assert digest.rstrip().endswith("(5s)")    # cost footer last
