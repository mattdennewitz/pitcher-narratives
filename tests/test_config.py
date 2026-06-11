"""Tests for provider-aware model settings construction."""

import pytest

from pitcher_narratives.config import (
    TOKEN_BUDGET_LARGE,
    TOKEN_BUDGET_MEDIUM,
    TOKEN_BUDGET_SMALL,
    make_model_settings,
)


def test_claude_thinking_gets_max_tokens_headroom():
    """Claude with extended thinking needs headroom: Anthropic's thinking
    budget counts against max_tokens, so a 4096 cap can be exhausted
    before any response text is generated."""
    settings = make_model_settings("claude", "high", 0.3, max_tokens=TOKEN_BUDGET_LARGE)
    assert settings.get("thinking")
    assert settings["max_tokens"] > TOKEN_BUDGET_LARGE


def test_claude_small_budget_disables_thinking_no_headroom():
    """Small budgets disable thinking and keep the requested cap."""
    settings = make_model_settings("claude", "high", 0.3, max_tokens=TOKEN_BUDGET_SMALL)
    assert "thinking" not in settings
    assert settings["max_tokens"] == TOKEN_BUDGET_SMALL


def test_claude_mini_disables_thinking_no_headroom():
    """Mini-tier Claude (Haiku) keeps the requested cap, no thinking."""
    settings = make_model_settings("claude", "high", 0.3, max_tokens=TOKEN_BUDGET_LARGE, mini=True)
    assert "thinking" not in settings
    assert settings["max_tokens"] == TOKEN_BUDGET_LARGE


def test_gemini_max_tokens_unchanged():
    """Gemini thinking is separate from max_tokens; no headroom applied."""
    settings = make_model_settings("gemini", "high", 0.3, max_tokens=TOKEN_BUDGET_MEDIUM)
    assert settings["max_tokens"] == TOKEN_BUDGET_MEDIUM


def test_unknown_provider_raises():
    """Unknown providers raise instead of silently falling through."""
    with pytest.raises(ValueError):
        make_model_settings("openai", "high", 0.3)
