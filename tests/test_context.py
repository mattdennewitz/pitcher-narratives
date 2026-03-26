"""Tests for PitcherContext assembly and to_prompt() rendering."""

from pydantic import BaseModel

from context import PitcherContext, assemble_pitcher_context
from data import load_pitcher_data
from engine import HardHitRate

TEST_PITCHER = 592155  # Booser, Cam

# Fixture-style: load data once (read-only test data)
_data = load_pitcher_data(TEST_PITCHER, window_days=30)
_ctx = assemble_pitcher_context(_data)


# ── Assembly tests ────────────────────────────────────────────────────


def test_pitcher_context_assembly():
    """assemble_pitcher_context returns a PitcherContext with all sections populated."""
    assert _ctx is not None
    assert _ctx.pitcher_name is not None
    assert _ctx.throws is not None
    assert _ctx.fastball is not None or _ctx.pitcher_name  # at least has name
    assert _ctx.arsenal is not None
    assert _ctx.execution is not None
    assert _ctx.workload is not None
    assert _ctx.platoon_mix is not None
    assert _ctx.first_pitch is not None


def test_pitcher_context_is_pydantic():
    """PitcherContext is a Pydantic BaseModel."""
    assert isinstance(_ctx, BaseModel)


def test_pitcher_context_pitcher_info():
    """PitcherContext has correct pitcher name and throws."""
    assert _ctx.pitcher_name == "Booser, Cam"
    assert _ctx.throws == "L"


def test_arsenal_top_4():
    """Arsenal contains at most 4 entries (token budget)."""
    assert len(_ctx.arsenal) <= 4


def test_execution_present():
    """Execution is a non-empty list of execution metric entries."""
    assert isinstance(_ctx.execution, list)
    assert len(_ctx.execution) > 0


# ── Rendering tests ───────────────────────────────────────────────────


def test_to_prompt_returns_string():
    """to_prompt() returns a str."""
    result = _ctx.to_prompt()
    assert isinstance(result, str)


def test_to_prompt_has_headers():
    """to_prompt() output contains markdown headers."""
    prompt = _ctx.to_prompt()
    assert "# " in prompt
    assert "## " in prompt


def test_to_prompt_has_pitcher_name():
    """to_prompt() output contains the pitcher's name."""
    prompt = _ctx.to_prompt()
    assert "Booser" in prompt


def test_to_prompt_has_fastball_section():
    """to_prompt() output contains fastball info."""
    prompt = _ctx.to_prompt()
    # Should mention primary fastball or note its absence
    assert "Fastball" in prompt or "Cutter" in prompt or "fastball" in prompt


def test_to_prompt_has_arsenal_section():
    """to_prompt() output contains 'Arsenal'."""
    prompt = _ctx.to_prompt()
    assert "Arsenal" in prompt


def test_to_prompt_has_execution_section():
    """to_prompt() output contains 'Execution'."""
    prompt = _ctx.to_prompt()
    assert "Execution" in prompt


def test_to_prompt_has_workload_section():
    """to_prompt() output contains 'Workload' or 'Appearance'."""
    prompt = _ctx.to_prompt()
    assert "Workload" in prompt or "Appearance" in prompt or "Recent" in prompt


def test_to_prompt_token_budget():
    """to_prompt() output is under 2,000 tokens at ~4 chars/token."""
    prompt = _ctx.to_prompt()
    estimated_tokens = len(prompt) / 4
    assert estimated_tokens < 2000, f"Estimated {estimated_tokens:.0f} tokens, exceeds 2,000 budget"


def test_to_prompt_no_none_literals():
    """to_prompt() output does not contain the literal string 'None'."""
    prompt = _ctx.to_prompt()
    assert "None" not in prompt, f"Found 'None' literal in prompt output:\n{prompt}"


# ── Hard-hit rate in context ──────────────────────────────────────────


def test_hard_hit_rate_in_context():
    """assemble_pitcher_context has a non-None hard_hit_rate field of type HardHitRate."""
    assert _ctx.hard_hit_rate is not None
    assert isinstance(_ctx.hard_hit_rate, HardHitRate)


def test_to_prompt_has_contact_quality():
    """to_prompt() output contains 'Contact Quality' or 'Hard-hit'."""
    prompt = _ctx.to_prompt()
    assert "Contact Quality" in prompt or "Hard-hit" in prompt
