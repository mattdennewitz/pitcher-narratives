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


def _pick_cat(pid: int, category: str) -> dict:
    return {**_pick(pid), "category": category}


# ── Model validation ────────────────────────────────────────────────


def test_slate_caps_each_category_at_five():
    """At most 5 picks per category; a 6th in one category is rejected."""
    with pytest.raises(ValidationError):
        CurationSlate(
            picks=[CurationPick(**_pick_cat(i, "lab_project")) for i in range(6)]
        )


def test_slate_allows_five_per_category_across_categories():
    """5 in each of the four categories (20 total, distinct ids) is valid."""
    cats = ["clean_breakout", "lab_project", "identity_crisis", "red_flag"]
    picks = [CurationPick(**_pick_cat(i, cats[i // 5])) for i in range(20)]
    slate = CurationSlate(picks=picks)
    assert len(slate.picks) == 20


def test_slate_must_not_be_empty():
    with pytest.raises(ValidationError):
        CurationSlate(picks=[])


def test_slate_accepts_thin_day():
    slate = CurationSlate(picks=[CurationPick(**_pick(1))])
    assert len(slate.picks) == 1


# ── Briefing ────────────────────────────────────────────────────────


def test_briefing_is_flat_not_role_bucketed():
    briefing = build_selector_briefing([_app(1, "SP"), _app(2, "RP")])
    assert "STARTERS" not in briefing
    assert "RELIEVERS" not in briefing
    # both candidates still appear, with role shown inline
    assert "id=1" in briefing and "id=2" in briefing


# ── Selector agent ──────────────────────────────────────────────────


def test_selector_settings_are_provider_aware():
    """Gemini selector gets explicit thinking config via the shared factory."""
    from pitcher_narratives.curator import make_selector_agent

    agent = make_selector_agent("gemini", [_app(1, "SP")])
    assert "google_thinking_config" in agent.model_settings


def test_selector_claude_disables_thinking_for_determinism():
    """The selector documents temperature=0.0 determinism; on Claude, thinking
    must be explicitly disabled or Anthropic silently forces temperature=1."""
    from pitcher_narratives.curator import make_selector_agent

    agent = make_selector_agent("claude", [_app(1, "SP")])
    assert agent.model_settings["temperature"] == 0.0
    assert "thinking" not in agent.model_settings


def test_select_slate_returns_validated_slate():
    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={"picks": [_pick(1), _pick(2)]})
    slate = select_slate(candidates, provider="gemini", _model_override=model)
    assert sorted(p.pitcher_id for p in slate.picks) == [1, 2]


def test_select_slate_rejects_unknown_pitcher_id():
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    candidates = [_app(1, "SP")]
    model = TestModel(custom_output_args={"picks": [_pick(999)]})  # not a candidate
    with pytest.raises(UnexpectedModelBehavior):
        select_slate(candidates, provider="gemini", _model_override=model)


def test_select_slate_empty_candidates_raises_without_llm():
    """No candidates -> immediate ValueError, no model calls."""
    with pytest.raises(ValueError):
        select_slate([], provider="gemini")


def test_select_slate_rejects_duplicate_picks():
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    candidates = [_app(1, "SP"), _app(2, "RP")]
    model = TestModel(custom_output_args={"picks": [_pick(1), _pick(1)]})
    with pytest.raises(UnexpectedModelBehavior):
        select_slate(candidates, provider="gemini", _model_override=model)


def test_slate_accepts_command_breakout_and_velo_drop():
    """The two new categories validate as picks."""
    slate = CurationSlate(picks=[
        CurationPick(**_pick_cat(1, "command_breakout")),
        CurationPick(**_pick_cat(2, "velo_drop")),
    ])
    assert {p.category for p in slate.picks} == {"command_breakout", "velo_drop"}


def test_pick_rejects_unknown_category():
    """A category outside the six-item enum is rejected."""
    with pytest.raises(ValidationError):
        CurationPick(**_pick_cat(1, "not_a_category"))


# ── Category registry ───────────────────────────────────────────────


def test_category_registry_matches_literal():
    """The Category registry must exactly cover CurationPick.category's Literal."""
    from typing import get_args

    from pitcher_narratives.curator import CATEGORY_BY_ID, CurationPick

    declared = set(get_args(CurationPick.model_fields["category"].annotation))
    assert set(CATEGORY_BY_ID) == declared


def test_category_registry_order_and_labels():
    from pitcher_narratives.curator import CATEGORIES

    assert [c.id for c in CATEGORIES] == [
        "clean_breakout", "command_breakout", "lab_project",
        "identity_crisis", "velo_drop", "red_flag",
    ]
    assert [c.order for c in CATEGORIES] == [0, 1, 2, 3, 4, 5]
    labels = {c.id: (c.section_title, c.badge) for c in CATEGORIES}
    assert labels["clean_breakout"] == ("Clean Breakouts", "CLEAN BREAKOUT")
    assert labels["velo_drop"] == ("Velocity Drops", "VELO DROP")
    assert all(c.section_title and c.badge for c in CATEGORIES)



# ── Category registry ───────────────────────────────────────────────


def test_category_registry_matches_literal():
    """The Category registry must exactly cover CurationPick.category's Literal."""
    from typing import get_args

    from pitcher_narratives.curator import CATEGORY_BY_ID, CurationPick

    declared = set(get_args(CurationPick.model_fields["category"].annotation))
    assert set(CATEGORY_BY_ID) == declared


def test_category_registry_order_and_labels():
    from pitcher_narratives.curator import CATEGORIES

    assert [c.id for c in CATEGORIES] == [
        "clean_breakout", "command_breakout", "lab_project",
        "identity_crisis", "velo_drop", "red_flag",
    ]
    assert [c.order for c in CATEGORIES] == [0, 1, 2, 3, 4, 5]
    labels = {c.id: (c.section_title, c.badge) for c in CATEGORIES}
    assert labels["clean_breakout"] == ("Clean Breakouts", "CLEAN BREAKOUT")
    assert labels["velo_drop"] == ("Velocity Drops", "VELO DROP")
    assert all(c.section_title and c.badge for c in CATEGORIES)
