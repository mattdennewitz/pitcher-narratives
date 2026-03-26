"""Tests for two-phase report generation (Synthesizer → Editor)."""

from pydantic_ai.models.test import TestModel

from context import assemble_pitcher_context
from data import load_pitcher_data
from report import (
    synthesizer,
    editor,
    _SYNTHESIZER_PROMPT,
    _EDITOR_PROMPT,
    _SP_SYNTH_GUIDANCE,
    _RP_SYNTH_GUIDANCE,
    _build_synthesizer_message,
    _build_editor_message,
    generate_report_streaming,
    check_hallucinated_metrics,
)

TEST_PITCHER = 592155  # Booser, Cam

# Fixture-style: load data once (read-only test data)
_data = load_pitcher_data(TEST_PITCHER, window_days=30)
_ctx = assemble_pitcher_context(_data)


# -- Phase 1: Synthesizer agent tests -----------------------------------------


def test_synthesizer_model_is_claude_sonnet():
    """Synthesizer agent uses claude-sonnet-4-6."""
    assert "claude-sonnet-4-6" in str(synthesizer.model)


def test_synthesizer_output_type_is_str():
    """Synthesizer output_type is str."""
    assert synthesizer.output_type is str


def test_synthesizer_prompt_is_objective():
    """Synthesizer prompt emphasizes objectivity, no editorial opinion."""
    assert "purely objective" in _SYNTHESIZER_PROMPT
    assert "Do NOT write narrative prose" in _SYNTHESIZER_PROMPT


def test_synthesizer_prompt_requires_baselines():
    """Synthesizer prompt requires stating baselines and deltas."""
    assert "baseline" in _SYNTHESIZER_PROMPT.lower()
    assert "delta" in _SYNTHESIZER_PROMPT.lower()


# -- Phase 2: Editor agent tests ----------------------------------------------


def test_editor_model_is_claude_sonnet():
    """Editor agent uses claude-sonnet-4-6."""
    assert "claude-sonnet-4-6" in str(editor.model)


def test_editor_prompt_has_skeptical_tone():
    """Editor prompt instructs skeptical evaluation."""
    assert "Skeptical" in _EDITOR_PROMPT or "skeptical" in _EDITOR_PROMPT


def test_editor_prompt_requires_decisive_projection():
    """Editor prompt requires a decisive tier projection."""
    assert "Take a Stance" in _EDITOR_PROMPT


def test_editor_prompt_requires_two_paragraphs():
    """Editor prompt enforces two-paragraph structure."""
    assert "Two-Paragraph" in _EDITOR_PROMPT or "two paragraphs" in _EDITOR_PROMPT.lower()


def test_editor_prompt_requires_platoon():
    """Editor prompt requires platoon analysis."""
    assert "Platoon Everything" in _EDITOR_PROMPT or "platoon" in _EDITOR_PROMPT.lower()


def test_editor_prompt_deemphasizes_traditional_stats():
    """Editor prompt de-emphasizes ERA/W-L in favor of underlying metrics."""
    assert "De-emphasize traditional" in _EDITOR_PROMPT or "traditional box score" in _EDITOR_PROMPT


def test_editor_prompt_no_cliches():
    """Editor prompt bans cliches."""
    assert "cliché" in _EDITOR_PROMPT or "bulldog mentality" in _EDITOR_PROMPT


# -- Role-conditional guidance tests -------------------------------------------


def test_sp_synth_guidance_contains_tto():
    """SP synthesis guidance mentions TTO."""
    assert "tto" in _SP_SYNTH_GUIDANCE.lower() or "time" in _SP_SYNTH_GUIDANCE.lower()


def test_sp_synth_guidance_contains_platoon():
    """SP synthesis guidance mentions platoon."""
    assert "platoon" in _SP_SYNTH_GUIDANCE.lower()


def test_rp_synth_guidance_contains_rest():
    """RP synthesis guidance mentions rest days."""
    assert "rest" in _RP_SYNTH_GUIDANCE.lower()


def test_rp_synth_guidance_contains_put_away():
    """RP synthesis guidance mentions put-away pitch."""
    assert "put-away" in _RP_SYNTH_GUIDANCE.lower()


# -- Message builder tests ----------------------------------------------------


def test_synthesizer_message_includes_to_prompt():
    """Synthesizer message includes the to_prompt() output."""
    msg = _build_synthesizer_message(_ctx)
    assert _ctx.to_prompt() in msg


def test_synthesizer_message_sp_gets_sp_guidance():
    """SP context gets SP-specific synthesis focus."""
    sp_ctx = _ctx.model_copy(update={"role": "SP"})
    msg = _build_synthesizer_message(sp_ctx)
    assert "starter" in msg.lower()


def test_synthesizer_message_rp_gets_rp_guidance():
    """RP context gets RP-specific synthesis focus."""
    rp_ctx = _ctx.model_copy(update={"role": "RP"})
    msg = _build_synthesizer_message(rp_ctx)
    assert "reliever" in msg.lower()


def test_editor_message_includes_synthesis():
    """Editor message includes the synthesis output."""
    synthesis = "- Fastball velo down 1.2 mph\n- Slider usage up 12pp"
    msg = _build_editor_message(_ctx, synthesis)
    assert synthesis in msg
    assert _ctx.pitcher_name in msg


# -- Two-phase pipeline tests -------------------------------------------------


def test_generate_report_returns_string():
    """Full pipeline returns a non-empty string using TestModel."""
    result = generate_report_streaming(
        _ctx, _model_override=TestModel(custom_output_text="Test report output")
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_report_uses_test_model():
    """Pipeline with TestModel produces the custom_output_text from Phase 2."""
    expected = "This is the final editor capsule"
    result = generate_report_streaming(
        _ctx, _model_override=TestModel(custom_output_text=expected)
    )
    # TestModel returns same text for both phases; Phase 2 output is what we get
    assert result == expected


# -- Hallucination guard tests ------------------------------------------------


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


def test_hallucination_guard_editorial_metrics():
    """Metrics used in editorial voice (K-BB%, SwStr%, xFIP) are known."""
    text = "K-BB% at 15%, SwStr% of 12%, xFIP near 3.50."
    assert check_hallucinated_metrics(text) == []
