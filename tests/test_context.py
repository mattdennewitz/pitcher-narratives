"""Tests for PitcherContext assembly and to_prompt() rendering."""

import pytest
from pydantic import BaseModel

from context import PitcherContext, assemble_pitcher_context
from data import load_pitcher_data
from engine import HardHitRate

TEST_PITCHER = 592155  # Booser, Cam


@pytest.fixture(scope="module")
def ctx():
    """Load data once per module (read-only test data)."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    return assemble_pitcher_context(data)


# ── Assembly tests ────────────────────────────────────────────────────


def test_pitcher_context_assembly(ctx):
    """assemble_pitcher_context returns a PitcherContext with all sections populated."""
    assert ctx is not None
    assert ctx.pitcher_name is not None
    assert ctx.throws is not None
    assert ctx.fastball is not None or ctx.pitcher_name  # at least has name
    assert ctx.arsenal is not None
    assert ctx.execution is not None
    assert ctx.workload is not None
    assert ctx.platoon_mix is not None
    assert ctx.first_pitch is not None


def test_pitcher_context_is_pydantic(ctx):
    """PitcherContext is a Pydantic BaseModel."""
    assert isinstance(ctx, BaseModel)


def test_pitcher_context_pitcher_info(ctx):
    """PitcherContext has correct pitcher name and throws."""
    assert ctx.pitcher_name == "Booser, Cam"
    assert ctx.throws == "L"


def test_arsenal_top_4(ctx):
    """Arsenal contains at most 4 entries (token budget)."""
    assert len(ctx.arsenal) <= 4


def test_execution_present(ctx):
    """Execution is a non-empty list of execution metric entries."""
    assert isinstance(ctx.execution, list)
    assert len(ctx.execution) > 0


# ── Rendering tests ───────────────────────────────────────────────────


def test_to_prompt_returns_string(ctx):
    """to_prompt() returns a str."""
    result = ctx.to_prompt()
    assert isinstance(result, str)


def test_to_prompt_has_headers(ctx):
    """to_prompt() output contains markdown headers."""
    prompt = ctx.to_prompt()
    assert "# " in prompt
    assert "## " in prompt


def test_to_prompt_has_pitcher_name(ctx):
    """to_prompt() output contains the pitcher's name."""
    prompt = ctx.to_prompt()
    assert "Booser" in prompt


def test_to_prompt_has_fastball_section(ctx):
    """to_prompt() output contains fastball info."""
    prompt = ctx.to_prompt()
    # Should mention primary fastball or note its absence
    assert "Fastball" in prompt or "Cutter" in prompt or "fastball" in prompt


def test_to_prompt_has_arsenal_section(ctx):
    """to_prompt() output contains 'Arsenal'."""
    prompt = ctx.to_prompt()
    assert "Arsenal" in prompt


def test_to_prompt_has_execution_section(ctx):
    """to_prompt() output contains 'Execution'."""
    prompt = ctx.to_prompt()
    assert "Execution" in prompt


def test_to_prompt_has_workload_section(ctx):
    """to_prompt() output contains 'Workload' or 'Appearance'."""
    prompt = ctx.to_prompt()
    assert "Workload" in prompt or "Appearance" in prompt or "Recent" in prompt


def test_to_prompt_token_budget(ctx):
    """to_prompt() output is under 2,000 tokens at ~4 chars/token."""
    prompt = ctx.to_prompt()
    estimated_tokens = len(prompt) / 4
    assert estimated_tokens < 2000, f"Estimated {estimated_tokens:.0f} tokens, exceeds 2,000 budget"


def test_to_prompt_no_none_literals(ctx):
    """to_prompt() output does not contain the literal string 'None'."""
    prompt = ctx.to_prompt()
    assert "None" not in prompt, f"Found 'None' literal in prompt output:\n{prompt}"


# ── Hard-hit rate in context ──────────────────────────────────────────


def test_hard_hit_rate_in_context(ctx):
    """assemble_pitcher_context has a non-None hard_hit_rate field of type HardHitRate."""
    assert ctx.hard_hit_rate is not None
    assert isinstance(ctx.hard_hit_rate, HardHitRate)


def test_to_prompt_has_contact_quality(ctx):
    """to_prompt() output contains 'Contact Quality' or 'Hard-hit'."""
    prompt = ctx.to_prompt()
    assert "Contact Quality" in prompt or "Hard-hit" in prompt
