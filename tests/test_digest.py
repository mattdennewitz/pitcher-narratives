"""Tests for the morning digest: full-board rendering and assembly."""

from datetime import date

from pitcher_narratives.curator import CurationPick, CurationSlate
from pitcher_narratives.digest import assemble_digest, render_full_board
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
        board=list(appearances.values()), game_date=date(2026, 6, 13), cost_block="cost",
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
        board=list(appearances.values()), game_date=date(2026, 6, 13), cost_block="cost",
    )
    assert out.index("### P3") < out.index("### P2") < out.index("### P1")


def test_digest_renders_new_category_sections_in_order():
    """command_breakout and velo_drop render as sections, in hierarchy order."""
    slate = CurationSlate(picks=[
        _pick2(1, "command_breakout"),
        _pick2(2, "velo_drop"),
        _pick2(3, "red_flag"),
    ])
    appearances = {
        1: _appearance(1, 9.0), 2: _appearance(2, 7.0), 3: _appearance(3, 8.0),
    }
    summaries = {1: "s1", 2: "s2", 3: "s3"}
    out = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=list(appearances.values()), game_date=date(2026, 6, 13), cost_block="cost",
    )
    assert "## Command Breakouts" in out
    assert "## Velocity Drops" in out
    # hierarchy order: command_breakout before velo_drop before red_flag
    assert (
        out.index("## Command Breakouts")
        < out.index("## Velocity Drops")
        < out.index("## Red Flags")
    )
    assert "[COMMAND BREAKOUT]" in out
    assert "[VELO DROP]" in out
