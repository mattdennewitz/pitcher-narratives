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


def test_write_pick_summaries_records_usage():
    """Each successful writer call records usage tagged writer:<name>."""
    from pitcher_narratives.costs import UsageTracker

    apps = {1: _app(1)}
    cues = {1: "cue"}
    tracker = UsageTracker()
    asyncio.run(write_pick_summaries(
        [_pick(1)], cues, apps, provider="gemini", persona=DEFAULT_PERSONA,
        tracker=tracker,
        _model_override=TestModel(custom_output_text="Summary."),
    ))
    [rec] = tracker.records
    assert rec.stage == "writer:Pitcher 1"
    assert rec.input_tokens > 0


def test_write_pick_summaries_mixed_outcomes():
    """One failing pick falls back; the other still gets written text."""

    class _FailsForCueTwo(TestModel):
        async def request(self, messages, model_settings, model_request_parameters):
            # Inspect rendered message content for the cue text.
            text = " ".join(
                part.content
                for m in messages
                for part in (m.parts if hasattr(m, "parts") else [])
                if hasattr(part, "content") and isinstance(part.content, str)
            )
            if "cue two" in text:
                raise RuntimeError("provider error")
            return await super().request(messages, model_settings, model_request_parameters)

    apps = {1: _app(1), 2: _app(2, role="RP")}
    cues = {1: "cue one", 2: "cue two"}
    summaries = asyncio.run(write_pick_summaries(
        [_pick(1), _pick(2)], cues, apps, provider="gemini",
        persona=DEFAULT_PERSONA, _model_override=_FailsForCueTwo(),
    ))
    assert "[summary unavailable" not in summaries[1]
    assert "[summary unavailable" in summaries[2]


def test_writer_settings_are_provider_aware():
    """Gemini writers get explicit thinking config so reasoning tokens
    cannot silently consume the output budget (observed live: summaries
    truncated mid-sentence at the cap)."""
    from pitcher_narratives.digest import _make_writer_agent

    agent = _make_writer_agent("gemini", DEFAULT_PERSONA)
    assert "google_thinking_config" in agent.model_settings


def test_writer_prompt_composes_persona_chain():
    """Child personas include their parent overlay, and the precedence
    rule appears after the voice section."""
    from pitcher_narratives.digest import _build_writer_prompt
    from pitcher_narratives.personas import PERSONAS

    analyst = PERSONAS["analyst"]
    prompt = _build_writer_prompt(analyst)
    scout_overlay_marker = PERSONAS["scout"].overlay[:40]
    assert scout_overlay_marker in prompt          # parent chain included
    assert analyst.overlay[:40] in prompt          # own overlay included
    assert prompt.index(scout_overlay_marker) < prompt.index(analyst.overlay[:40])
    assert "PRECEDENCE:" in prompt
    assert prompt.index("PRECEDENCE:") > prompt.index("VOICE:")


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
    slate = CurationSlate(picks=[_pick(1), _pick(2)])
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
    i_cat = digest.index("## Clean Breakouts")
    i_board = digest.index("## The Full Board")
    assert i_cat < i_board
    assert i_cat < digest.index("SP summary text.") < i_board
    assert i_cat < digest.index("RP summary text.") < i_board
    assert "clean_breakout" in digest
    assert "Pitcher 1" in digest
    assert digest.rstrip().endswith("(5s)")


def _pick2(pid: int, category: str, conviction: str = "medium") -> CurationPick:
    return CurationPick(
        pitcher_id=pid, category=category, angle="a", conviction=conviction,
        conviction_reason="r",
    )


def _appearance(pid: int, score: float):
    from datetime import date as _date

    from pitcher_narratives.scout import ScoredAppearance
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"P{pid}", throws="R",
        game_date=_date(2026, 6, 13), game_pk=1, n_pitches=80, score=score, role="RP",
    )


def test_digest_groups_by_category_and_omits_empty():
    slate = CurationSlate(picks=[
        _pick2(1, "red_flag"),
        _pick2(2, "lab_project"),
        _pick2(3, "lab_project"),
    ])
    appearances = {1: _appearance(1, 9.0), 2: _appearance(2, 5.0), 3: _appearance(3, 8.0)}
    summaries = {1: "s1", 2: "s2", 3: "s3"}
    out = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=list(appearances.values()), game_date="2026-06-13", cost_block="cost",
    )
    assert "## Lab Projects" in out
    assert "## Red Flags" in out
    assert "## Clean Breakouts" not in out
    assert "## Identity Crises" not in out
    assert out.index("## Lab Projects") < out.index("## Red Flags")


def test_digest_orders_within_category_by_conviction_then_score():
    slate = CurationSlate(picks=[
        _pick2(1, "lab_project", "low"),
        _pick2(2, "lab_project", "high"),
        _pick2(3, "lab_project", "high"),
    ])
    appearances = {1: _appearance(1, 9.0), 2: _appearance(2, 5.0), 3: _appearance(3, 8.0)}
    summaries = {1: "s1", 2: "s2", 3: "s3"}
    out = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=list(appearances.values()), game_date="2026-06-13", cost_block="cost",
    )
    assert out.index("### P3") < out.index("### P2") < out.index("### P1")
