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


def test_deepseek_provider_registered():
    """DeepSeek is a full pipeline contestant via OpenRouter."""
    from pitcher_narratives.config import API_KEYS, MINI_PROVIDERS, PROVIDERS

    assert PROVIDERS["deepseek"] == "openrouter:deepseek/deepseek-v4-pro"
    assert MINI_PROVIDERS["deepseek"] == "openrouter:deepseek/deepseek-v4-flash"
    assert API_KEYS["deepseek"] == "OPENROUTER_API_KEY"


def test_deepseek_settings_map_thinking_to_reasoning_effort():
    """Non-mini DeepSeek gets OpenRouter reasoning effort from thinking level."""
    settings = make_model_settings("deepseek", "high", 0.3, max_tokens=TOKEN_BUDGET_LARGE)
    assert settings.get("openrouter_reasoning", {}).get("effort") == "high"
    assert settings["max_tokens"] > TOKEN_BUDGET_LARGE  # reasoning headroom
    assert settings["temperature"] == 0.3


def test_deepseek_mini_plain_settings():
    """Mini DeepSeek (v4-flash) runs without reasoning config."""
    settings = make_model_settings("deepseek", "high", 0.3, max_tokens=TOKEN_BUDGET_SMALL, mini=True)
    assert "openrouter_reasoning" not in settings
    assert settings["max_tokens"] == TOKEN_BUDGET_SMALL
