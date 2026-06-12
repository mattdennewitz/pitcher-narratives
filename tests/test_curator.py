"""Tests for the structured morning-run selector."""

from datetime import date

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from pitcher_narratives.curator import (
    CurationPick,
    CurationSlate,
    build_selector_briefing,
    select_slate,
)
from pitcher_narratives.scout import ScoredAppearance, Signal


def _app(pid: int, role: str, name: str | None = None) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=name or f"Pitcher {pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=80, score=5.0,
        role=role,
        signals=[Signal("velo_delta", 3.0, "+2.1 mph vs season")],
    )


def _pick(pid: int) -> dict:
    return {
        "pitcher_id": pid,
        "category": "clean_breakout",
        "angle": "Velocity spike with stuff gain",
        "conviction": "medium",
        "conviction_reason": "One game, but the shape data agrees.",
    }


# ── Model validation ────────────────────────────────────────────────


def test_slate_caps_each_role_at_ten():
    with pytest.raises(ValidationError):
        CurationSlate(
            starters=[CurationPick(**_pick(i)) for i in range(11)],
            relievers=[],
        )


def test_slate_must_not_be_empty():
    with pytest.raises(ValidationError):
        CurationSlate(starters=[], relievers=[])


def test_slate_accepts_thin_day():
    slate = CurationSlate(
        starters=[CurationPick(**_pick(1))],
        relievers=[],
    )
    assert len(slate.starters) == 1


# ── Briefing ────────────────────────────────────────────────────────


def test_briefing_buckets_by_role():
    """SP and RP candidates appear under separate labeled sections."""
    briefing = build_selector_briefing([_app(1, "SP"), _app(2, "RP")])
    sp_idx = briefing.index("STARTERS")
    rp_idx = briefing.index("RELIEVERS")
    assert sp_idx < briefing.index("Pitcher 1") < rp_idx
    assert rp_idx < briefing.index("Pitcher 2")
    assert "velo_delta" in briefing
    assert "+2.1 mph vs season" in briefing
    assert "id=1" in briefing  # pitcher_id is in the briefing for the LLM to echo


# ── Selector agent ──────────────────────────────────────────────────


def test_select_slate_returns_validated_slate():
    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={
        "starters": [_pick(1)],
        "relievers": [_pick(2)],
    })
    slate = select_slate(candidates, provider="gemini", _model_override=model)
    assert [p.pitcher_id for p in slate.starters] == [1]
    assert [p.pitcher_id for p in slate.relievers] == [2]


def test_select_slate_rejects_unknown_pitcher_id():
    """A pick whose id is not among the role's candidates is retried and,
    with a model that never corrects, ultimately fails."""
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={
        "starters": [_pick(999)],  # not a candidate
        "relievers": [],
    })
    with pytest.raises(UnexpectedModelBehavior):
        select_slate(candidates, provider="gemini", _model_override=model)


def test_select_slate_rejects_role_swap():
    """An RP candidate picked as a starter bounces."""
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={
        "starters": [_pick(2)],  # RP picked as SP
        "relievers": [],
    })
    with pytest.raises(UnexpectedModelBehavior):
        select_slate(candidates, provider="gemini", _model_override=model)
