"""Tests for report generation module (pydantic-ai Agent + streaming)."""

from pydantic_ai.models.test import TestModel

from context import assemble_pitcher_context
from data import load_pitcher_data
from report import (
    agent,
    _SYSTEM_PROMPT,
    _SP_GUIDANCE,
    _RP_GUIDANCE,
    _build_user_message,
    generate_report_streaming,
    check_hallucinated_metrics,
)

TEST_PITCHER = 592155  # Booser, Cam

# Fixture-style: load data once (read-only test data)
_data = load_pitcher_data(TEST_PITCHER, window_days=30)
_ctx = assemble_pitcher_context(_data)


# -- Agent configuration tests ------------------------------------------------


def test_agent_model_is_claude_sonnet():
    """Agent is configured with anthropic:claude-sonnet-4-6 model string."""
    # model_name may be stored as the model attribute or a string repr
    model = agent.model
    # pydantic-ai stores the model as a string or Model instance
    assert "claude-sonnet-4-6" in str(model)


def test_agent_output_type_is_str():
    """Agent output_type is str."""
    assert agent.output_type is str


# -- System prompt tests -------------------------------------------------------


def test_system_prompt_has_scout_persona():
    """System prompt contains veteran MLB pitching analyst persona."""
    assert "veteran MLB pitching analyst" in _SYSTEM_PROMPT


def test_system_prompt_has_anti_recitation():
    """System prompt contains anti-recitation language."""
    assert "Write insight, not stat lines" in _SYSTEM_PROMPT


def test_system_prompt_references_numbers_as_support():
    """System prompt instructs referencing numbers to support observations."""
    # The anti-recitation guidance: "Reference numbers to support observations, don't list them"
    assert "Reference numbers" in _SYSTEM_PROMPT or "reference numbers" in _SYSTEM_PROMPT


# -- Role-conditional guidance tests -------------------------------------------


def test_sp_guidance_contains_stamina():
    """SP guidance mentions stamina indicators."""
    assert "stamina" in _SP_GUIDANCE.lower()


def test_sp_guidance_contains_pitch_mix():
    """SP guidance mentions pitch mix."""
    assert "pitch mix" in _SP_GUIDANCE.lower()


def test_rp_guidance_contains_workload():
    """RP guidance mentions workload."""
    assert "workload" in _RP_GUIDANCE.lower()


def test_rp_guidance_contains_leverage():
    """RP guidance mentions leverage."""
    assert "leverage" in _RP_GUIDANCE.lower()


# -- _build_user_message tests -------------------------------------------------


def test_build_user_message_includes_to_prompt():
    """_build_user_message includes the to_prompt() output."""
    msg = _build_user_message(_ctx)
    prompt_output = _ctx.to_prompt()
    assert prompt_output in msg


def test_build_user_message_sp_gets_sp_guidance():
    """_build_user_message for SP role includes SP-specific guidance."""
    # Create a modified context with SP role
    sp_ctx = _ctx.model_copy(update={"role": "SP"})
    msg = _build_user_message(sp_ctx)
    assert "stamina" in msg.lower()
    assert "pitch mix" in msg.lower()


def test_build_user_message_rp_gets_rp_guidance():
    """_build_user_message for RP role includes RP-specific guidance."""
    rp_ctx = _ctx.model_copy(update={"role": "RP"})
    msg = _build_user_message(rp_ctx)
    assert "workload" in msg.lower()
    assert "leverage" in msg.lower()


# -- generate_report_streaming tests -------------------------------------------


def test_generate_report_streaming_returns_string():
    """generate_report_streaming returns a non-empty string using TestModel."""
    result = generate_report_streaming(
        _ctx, _model_override=TestModel(custom_output_text="Test report output")
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_report_streaming_uses_test_model_output():
    """generate_report_streaming with TestModel produces the custom_output_text."""
    expected = "This is a custom scouting report for testing"
    result = generate_report_streaming(
        _ctx, _model_override=TestModel(custom_output_text=expected)
    )
    assert result == expected


# ── Hallucination guard ───────────────────────────────────────────────


def test_hallucination_guard_clean():
    """Known metrics in output produce no warnings."""
    text = "His P+ of 112 and xWhiff of 0.35 suggest elite stuff. CSW% at 32%."
    assert check_hallucinated_metrics(text) == []


def test_hallucination_guard_catches_unknown():
    """Fabricated metrics are flagged."""
    text = "His xDominance score of 95 suggests elite stuff."
    result = check_hallucinated_metrics(text)
    assert "xDominance" in result


def test_hallucination_guard_known_metrics():
    """All standard Pitching+ metrics pass without flags."""
    text = "S+ at 110, L+ at 105, xRV100 of -2.3, xGOr at 0.45."
    assert check_hallucinated_metrics(text) == []


def test_hallucination_guard_percentage_metrics():
    """CSW%, Zone%, Chase% are all known."""
    text = "CSW% of 32.1%, Zone% at 48%, Chase% near 30%."
    assert check_hallucinated_metrics(text) == []
