"""Tests for role-adaptive prompting in the Game Shape specialist.

Ensures SP and RP pitchers get different guidance blocks injected into
the Game Shape specialist's user message, restoring a capability that
the old single-agent synthesizer had before v1.9 consolidation.
"""

from __future__ import annotations

from pitcher_narratives.pipeline import (
    _RP_GAME_SHAPE_GUIDANCE,
    _SP_GAME_SHAPE_GUIDANCE,
    _build_game_shape_input,
    _role_game_shape_guidance,
)


# ── Role guidance lookup ──────────────────────────────────────────────────


def test_sp_guidance_returned_for_starter():
    """Role 'SP' gets the starter guidance block."""
    assert _role_game_shape_guidance("SP") is _SP_GAME_SHAPE_GUIDANCE


def test_rp_guidance_returned_for_reliever():
    """Role 'RP' gets the reliever guidance block."""
    assert _role_game_shape_guidance("RP") is _RP_GAME_SHAPE_GUIDANCE


def test_unknown_role_returns_none():
    """Unknown roles don't get a guidance block."""
    assert _role_game_shape_guidance("UNKNOWN") is None
    assert _role_game_shape_guidance("") is None


def test_case_insensitive_role_match():
    """Lowercase 'sp'/'rp' still resolve — defends against data-layer changes."""
    assert _role_game_shape_guidance("sp") is _SP_GAME_SHAPE_GUIDANCE
    assert _role_game_shape_guidance("rp") is _RP_GAME_SHAPE_GUIDANCE


def test_long_form_role_names_match():
    """'STARTER' / 'RELIEVER' long forms also resolve."""
    assert _role_game_shape_guidance("STARTER") is _SP_GAME_SHAPE_GUIDANCE
    assert _role_game_shape_guidance("reliever") is _RP_GAME_SHAPE_GUIDANCE


# ── Guidance content ──────────────────────────────────────────────────────


def test_sp_guidance_mentions_tto_and_stamina():
    """SP guidance calls out TTO and stamina — the key starter concerns."""
    assert "TTO" in _SP_GAME_SHAPE_GUIDANCE
    assert "Stamina" in _SP_GAME_SHAPE_GUIDANCE or "stamina" in _SP_GAME_SHAPE_GUIDANCE
    assert "STARTER" in _SP_GAME_SHAPE_GUIDANCE


def test_rp_guidance_mentions_rest_and_put_away():
    """RP guidance calls out rest days and put-away pitch — the key reliever concerns."""
    assert "Rest day" in _RP_GAME_SHAPE_GUIDANCE or "rest day" in _RP_GAME_SHAPE_GUIDANCE
    assert "put-away" in _RP_GAME_SHAPE_GUIDANCE or "Primary weapon" in _RP_GAME_SHAPE_GUIDANCE
    assert "RELIEVER" in _RP_GAME_SHAPE_GUIDANCE


def test_sp_and_rp_guidance_are_distinct():
    """The two guidance blocks should not be identical."""
    assert _SP_GAME_SHAPE_GUIDANCE != _RP_GAME_SHAPE_GUIDANCE


# ── Integration with _build_game_shape_input ──────────────────────────────


def test_game_shape_input_injects_sp_guidance_for_starter():
    """A starter's game shape input includes the SP guidance block before the cache point."""
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data

    # 592155 is Cam Booser in the test fixtures — check the most recent
    # appearance role and pick a test strategy accordingly. We just need
    # SOME pitcher to exercise the injection branch; the guidance content
    # assertions above already validate the string, so here we verify
    # the injection actually happens in the UserPrompt parts.
    data = load_pitcher_data(592155, recent_appearances=10)
    ctx = assemble_pitcher_context(data)

    parts = _build_game_shape_input(ctx)
    # Join the string parts (skip CachePoint objects)
    joined = "\n".join(p for p in parts if isinstance(p, str))

    # Exactly one of the guidance blocks must appear, matching ctx.role.
    if ctx.role == "SP":
        assert "## Role Focus: STARTER" in joined
        assert "## Role Focus: RELIEVER" not in joined
    elif ctx.role == "RP":
        assert "## Role Focus: RELIEVER" in joined
        assert "## Role Focus: STARTER" not in joined
    else:
        # Defensive: if the fixture pitcher has an unexpected role,
        # neither block should appear.
        assert "## Role Focus" not in joined
