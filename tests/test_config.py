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


def test_gemini_disable_thinking_sets_zero_budget():
    """disable_thinking turns Gemini thinking off via thinking_budget=0 so
    thinking tokens cannot consume the output budget (which truncated the
    second-step summarizers)."""
    settings = make_model_settings(
        "gemini", "high", 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, disable_thinking=True
    )
    assert settings["google_thinking_config"] == {"thinking_budget": 0}
    assert settings["max_tokens"] == TOKEN_BUDGET_MEDIUM


def test_gemini_thinking_enabled_uses_level_not_budget():
    """Without disable_thinking, Gemini uses thinking_level (the default path)."""
    settings = make_model_settings(
        "gemini", "high", 0.3, max_tokens=TOKEN_BUDGET_MEDIUM
    )
    assert "thinking_level" in settings["google_thinking_config"]
    assert "thinking_budget" not in settings["google_thinking_config"]


def test_claude_disable_thinking_no_thinking_key():
    """disable_thinking forces Claude to omit the thinking setting even at a
    large budget that would otherwise enable it."""
    settings = make_model_settings(
        "claude", "high", 0.3, max_tokens=TOKEN_BUDGET_LARGE, disable_thinking=True
    )
    assert "thinking" not in settings
    assert settings["max_tokens"] == TOKEN_BUDGET_LARGE
    # Thinking is off, so the caller's temperature is honored (not forced to 1).
    assert settings["temperature"] == 0.3


def test_unknown_provider_raises():
    """Unknown providers raise instead of silently falling through."""
    with pytest.raises(ValueError):
        make_model_settings("openai", "high", 0.3)
