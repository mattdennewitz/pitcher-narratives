"""Tests for four-phase report generation pipeline."""

import pytest
from pydantic_ai import CachePoint
from pydantic_ai.models.test import TestModel

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.report import (
    _EDITOR_PROMPT,
    _FANTASY_PROMPT,
    _RP_SYNTH_GUIDANCE,
    _SP_SYNTH_GUIDANCE,
    _SYNTHESIZER_PROMPT,
    HallucinationReport,
    ReportResult,
    _build_editor_message,
    _build_fantasy_message,
    _build_hook_message,
    _build_synthesizer_message,
    _make_agents,
    check_hallucinated_metrics,
    generate_report_streaming,
)


def _prompt_text(parts: list[str | CachePoint]) -> str:
    """Join the text parts of a user prompt, skipping CachePoints."""
    return "\n".join(p for p in parts if isinstance(p, str))


TEST_PITCHER = 592155  # Booser, Cam


@pytest.fixture(scope="module")
def ctx():
    """Load data once per module (read-only test data)."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    return assemble_pitcher_context(data)


# -- Phase 1: Synthesizer agent tests -----------------------------------------


def test_synthesizer_model_matches_provider():
    """Synthesizer agent uses the correct model for each provider."""
    synth, _, _, _ = _make_agents(provider="claude")
    assert "claude-sonnet-4-6" in str(synth.model)
    synth_oai, _, _, _ = _make_agents(provider="openai")
    assert "gpt-5.4-mini" in str(synth_oai.model)


def test_synthesizer_output_type_is_str():
    """Synthesizer output_type is str."""
    synth, _, _, _ = _make_agents()
    assert synth.output_type is str


def test_synthesizer_prompt_is_objective():
    """Synthesizer prompt emphasizes objectivity, not a story."""
    assert "not writing a story" in _SYNTHESIZER_PROMPT
    assert "Absolute Objectivity" in _SYNTHESIZER_PROMPT


def test_synthesizer_prompt_has_rigid_output_format():
    """Synthesizer prompt prescribes exact output categories."""
    assert "## Fastball Quality & Velocity Trends" in _SYNTHESIZER_PROMPT
    assert "## Pitch Mix & Usage Shifts" in _SYNTHESIZER_PROMPT
    assert "## Execution & Outcomes" in _SYNTHESIZER_PROMPT
    assert "## Platoon Splits" in _SYNTHESIZER_PROMPT
    assert "## Workload & Stamina" in _SYNTHESIZER_PROMPT
    assert "## Key Signal" in _SYNTHESIZER_PROMPT


def test_synthesizer_prompt_requires_baselines():
    """Synthesizer prompt requires stating baselines and deltas."""
    assert "baseline" in _SYNTHESIZER_PROMPT.lower()
    assert "delta" in _SYNTHESIZER_PROMPT.lower()


def test_synthesizer_prompt_balanced_gains_and_drops():
    """Synthesizer prompt weights gains equally with drops."""
    assert "gains AND drops" in _SYNTHESIZER_PROMPT or "Breakout Indicators" in _SYNTHESIZER_PROMPT
    assert "Regression Risks" in _SYNTHESIZER_PROMPT


# -- Phase 2: Editor agent tests ----------------------------------------------


def test_editor_model_matches_provider():
    """Editor agent uses the correct model for the provider."""
    _, ed, _, _ = _make_agents(provider="claude")
    assert "claude-sonnet-4-6" in str(ed.model)


def test_editor_prompt_has_skeptical_tone():
    """Editor prompt instructs skeptical evaluation."""
    assert "skeptical" in _EDITOR_PROMPT.lower()
    assert "not a cheerleader" in _EDITOR_PROMPT.lower()


def test_editor_prompt_requires_decisive_projection():
    """Editor prompt requires a decisive tier projection."""
    assert "Take a Stance" in _EDITOR_PROMPT


def test_editor_prompt_requires_capsule_structure():
    """Editor prompt enforces 2-3 paragraph capsule structure."""
    assert "2-3 Paragraph" in _EDITOR_PROMPT or "The Setup" in _EDITOR_PROMPT
    assert "The Verdict" in _EDITOR_PROMPT


def test_editor_prompt_requires_platoon():
    """Editor prompt requires platoon analysis."""
    assert "Platoon Everything" in _EDITOR_PROMPT


def test_editor_prompt_strict_constraints():
    """Editor prompt has strict data-only constraints."""
    assert "Rely entirely on the data provided" in _EDITOR_PROMPT
    assert "Do not hallucinate" in _EDITOR_PROMPT


def test_editor_prompt_no_fluff():
    """Editor prompt bans introductory fluff and headers."""
    assert "No introductory fluff" in _EDITOR_PROMPT
    assert "Start immediately with the analysis" in _EDITOR_PROMPT


def test_editor_prompt_no_cliches():
    """Editor prompt bans cliches with examples."""
    assert "bulldog mentality" in _EDITOR_PROMPT
    assert "pitches to contact" in _EDITOR_PROMPT


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


def test_synthesizer_message_includes_to_prompt(ctx):
    """Synthesizer message includes the to_prompt() output."""
    msg = _prompt_text(_build_synthesizer_message(ctx))
    assert ctx.to_prompt() in msg


def test_synthesizer_message_sp_gets_sp_guidance(ctx):
    """SP context gets SP-specific synthesis focus."""
    sp_ctx = ctx.model_copy(update={"role": "SP"})
    msg = _prompt_text(_build_synthesizer_message(sp_ctx))
    assert "starter" in msg.lower()


def test_synthesizer_message_rp_gets_rp_guidance(ctx):
    """RP context gets RP-specific synthesis focus."""
    rp_ctx = ctx.model_copy(update={"role": "RP"})
    msg = _prompt_text(_build_synthesizer_message(rp_ctx))
    assert "reliever" in msg.lower()


def test_editor_message_includes_synthesis(ctx):
    """Editor message includes the synthesis output."""
    synthesis = "- Fastball velo down 1.2 mph\n- Slider usage up 12pp"
    msg = _prompt_text(_build_editor_message(ctx, synthesis))
    assert synthesis in msg
    assert ctx.pitcher_name in msg


# -- Two-phase pipeline tests -------------------------------------------------


def test_generate_report_returns_report_result(ctx):
    """Full pipeline returns a ReportResult using TestModel."""
    result = generate_report_streaming(
        ctx, _model_override=TestModel(custom_output_text="Test report output")
    )
    assert isinstance(result, ReportResult)
    assert len(result.narrative) > 0
    assert len(result.social_hook) > 0


def test_generate_report_uses_test_model(ctx):
    """Pipeline with TestModel produces the custom_output_text from Phase 2."""
    expected = "This is the final editor capsule"
    result = generate_report_streaming(ctx, _model_override=TestModel(custom_output_text=expected))
    # TestModel returns same text for both phases; Phase 2 narrative is what we get
    assert result.narrative == expected


# -- Hallucination guard tests ------------------------------------------------


def test_hallucination_guard_clean():
    """Known metrics in output produce no warnings."""
    text = "His P+ of 112 and xWhiff of 0.35 suggest elite stuff. CSW% at 32%."
    result = check_hallucinated_metrics(text)
    assert isinstance(result, HallucinationReport)
    assert result.unknown_metrics == []
    assert result.outcome_stat_warnings == []
    assert result.is_clean


def test_hallucination_guard_catches_unknown():
    """Fabricated metrics are flagged."""
    text = "His xDominance score of 95 suggests elite stuff."
    result = check_hallucinated_metrics(text)
    assert isinstance(result, HallucinationReport)
    assert "xDominance" in result.unknown_metrics


def test_hallucination_guard_known_metrics():
    """All standard Pitching+ metrics pass without flags."""
    text = "S+ at 110, L+ at 105, xRV100 of -2.3, xGOr at 0.45."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_percentage_metrics():
    """CSW%, Zone%, Chase% are all known."""
    text = "CSW% of 32.1%, Zone% at 48%, Chase% near 30%."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_editorial_metrics():
    """Metrics used in editorial voice (K-BB%, SwStr%, xFIP) are known."""
    text = "K-BB% at 15%, SwStr% of 12%, xFIP near 3.50."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_plus_metrics_in_sentence():
    """P+ detected in natural sentence context (space after +)."""
    text = "His P+ of 112 was solid"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_plus_after_comma():
    """S+, L+ detected when followed by comma or space."""
    text = "S+, L+ both above 100"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_plus_at_end_of_string():
    """L+ detected at end of string."""
    text = "great L+"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_xwoba_matched():
    """xwOBA (lowercase w after x) is matched and recognized as known."""
    text = "xwOBA of .320"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_xera_known():
    """xERA recognized as known metric."""
    text = "xERA near 3.50"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_barrel_pct_known():
    """Barrel% recognized as known metric."""
    text = "Barrel% at 12%"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_traditional_stats_warned():
    """Traditional outcome stats flagged as outcome_stat_warnings, not unknown."""
    text = "ERA of 3.50 and WHIP of 1.20"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert "ERA" in result.outcome_stat_warnings
    assert "WHIP" in result.outcome_stat_warnings
    assert not result.is_clean


def test_hallucination_guard_mixed_issues():
    """Text with fabricated metric AND traditional stat populates both lists."""
    text = "His xDominance of 95 and ERA of 3.50 are both notable."
    result = check_hallucinated_metrics(text)
    assert "xDominance" in result.unknown_metrics
    assert "ERA" in result.outcome_stat_warnings
    assert not result.is_clean


def test_hallucination_guard_is_clean_property():
    """is_clean True for clean text, False for dirty text."""
    clean = check_hallucinated_metrics("Nothing metric-like here.")
    assert clean.is_clean

    dirty = check_hallucinated_metrics("His xFakeMetric is off the charts.")
    assert not dirty.is_clean


def test_hallucination_guard_all_traditional_stats():
    """FIP, WAR, K%, BB%, HR/9 all flagged as outcome stat warnings."""
    text = "FIP at 3.20, WAR of 2.5, K% at 28%, BB% at 7%, HR/9 at 1.1."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    for stat in ["FIP", "WAR", "K%", "BB%", "HR/9"]:
        assert stat in result.outcome_stat_warnings, f"{stat} not in outcome_stat_warnings"


def test_hallucination_guard_xdominance_still_unknown():
    """xDominance still caught as unknown metric (regression check)."""
    text = "xDominance score was 95."
    result = check_hallucinated_metrics(text)
    assert "xDominance" in result.unknown_metrics


def test_hallucination_guard_hardhit_pct_still_known():
    """HardHit% still passes as known (regression check)."""
    text = "HardHit% at 42%."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


# -- Phase 3: Hook writer agent tests -----------------------------------------


def test_hook_writer_model_matches_provider():
    """Hook writer agent uses the correct model for the provider."""
    _, _, hook, _ = _make_agents(provider="claude")
    assert "claude-sonnet-4-6" in str(hook.model)


def test_hook_writer_output_type_is_str():
    """Hook writer output_type is str."""
    _, _, hook, _ = _make_agents()
    assert hook.output_type is str


def test_hook_message_includes_pitcher_name(ctx):
    """Hook message includes pitcher name."""
    msg = _prompt_text(_build_hook_message(ctx, "test synthesis"))
    assert ctx.pitcher_name in msg


def test_hook_message_includes_synthesis(ctx):
    """Hook message includes synthesis text."""
    msg = _prompt_text(_build_hook_message(ctx, "Fastball velo down 1.5"))
    assert "Fastball velo down 1.5" in msg


def test_report_result_has_social_hook(ctx):
    """ReportResult has non-empty narrative and social_hook fields."""
    result = generate_report_streaming(ctx, _model_override=TestModel(custom_output_text="hook text"))
    assert isinstance(result, ReportResult)
    assert result.social_hook
    assert result.narrative


def test_report_result_narrative_matches_editor_output(ctx):
    """ReportResult narrative matches editor TestModel output."""
    result = generate_report_streaming(ctx, _model_override=TestModel(custom_output_text="editor output"))
    assert result.narrative == "editor output"


# -- Phase 4: Fantasy analyst agent tests ----------------------------------------


def test_fantasy_analyst_model_matches_provider():
    """Fantasy analyst agent uses the correct model for the provider."""
    _, _, _, fantasy = _make_agents(provider="claude")
    assert "claude-sonnet-4-6" in str(fantasy.model)


def test_fantasy_analyst_output_type_is_str():
    """Fantasy analyst output_type is str."""
    _, _, _, fantasy = _make_agents()
    assert fantasy.output_type is str


def test_fantasy_prompt_requires_three_bullets():
    """Fantasy prompt requires exactly 3 bullet points."""
    prompt_lower = _FANTASY_PROMPT.lower()
    assert "3" in _FANTASY_PROMPT or "three" in prompt_lower
    assert "bullet" in prompt_lower


def test_fantasy_prompt_news_first_style():
    """Fantasy prompt uses news-wire voice, not command-style verdicts."""
    assert "axios" in _FANTASY_PROMPT.lower()
    assert "news" in _FANTASY_PROMPT.lower()


def test_fantasy_message_includes_pitcher_name(ctx):
    """Fantasy message includes pitcher name."""
    msg = _prompt_text(_build_fantasy_message(ctx, "test synthesis"))
    assert ctx.pitcher_name in msg


def test_fantasy_message_includes_synthesis(ctx):
    """Fantasy message includes synthesis text."""
    msg = _prompt_text(_build_fantasy_message(ctx, "Fastball velo down 1.5"))
    assert "Fastball velo down 1.5" in msg


def test_report_result_has_fantasy_insights(ctx):
    """ReportResult has non-empty fantasy_insights field."""
    result = generate_report_streaming(ctx, _model_override=TestModel(custom_output_text="fantasy text"))
    assert isinstance(result, ReportResult)
    assert result.fantasy_insights


def test_report_result_all_fields_populated(ctx):
    """ReportResult has all three fields populated."""
    result = generate_report_streaming(ctx, _model_override=TestModel(custom_output_text="test output"))
    assert result.narrative
    assert result.social_hook
    assert result.fantasy_insights
