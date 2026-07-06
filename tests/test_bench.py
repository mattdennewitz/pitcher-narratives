"""Tests for the LLM benchmarking harness (bench package).

Covers rubric models and prompt construction, panel judge selection,
scorecard aggregation math, report rendering, the pipeline runner with
a deterministic test model, and CLI argument parsing.
"""

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from pitcher_narratives.bench.__main__ import parse_args
from pitcher_narratives.bench.judge import JUDGE_MODELS, judges_for, make_judge_agent
from pitcher_narratives.bench.rubric import (
    AGENT_RUBRIC,
    CAPSULE_RUBRIC,
    DimensionScore,
    JudgedOutput,
    build_judge_prompt,
    weighted_overall,
)
from pitcher_narratives.bench.runner import run_provider
from pitcher_narratives.bench.scorecard import JudgedRecord, _rubric_for, aggregate, render_report

TEST_PITCHER = 592155


# ── Rubric models ─────────────────────────────────────────────────────


def test_dimension_score_bounds():
    """Scores outside 1-5 are rejected."""
    with pytest.raises(ValidationError):
        DimensionScore(dimension="grounding", score=6, justification="x", evidence="y")
    with pytest.raises(ValidationError):
        DimensionScore(dimension="grounding", score=0, justification="x", evidence="y")


def test_rubrics_have_weighted_dimensions():
    """Both rubrics exist, share the grounding core, and weight grounding highest."""
    for rubric in (AGENT_RUBRIC, CAPSULE_RUBRIC):
        keys = [d.key for d in rubric]
        assert "grounding" in keys
        assert "directional_consistency" in keys
        assert "sample_size_calibration" in keys
        top = max(rubric, key=lambda d: d.weight)
        assert top.key == "grounding"
    assert any(d.key == "analytical_mechanism" for d in AGENT_RUBRIC)
    assert any(d.key == "thread_coherence" for d in CAPSULE_RUBRIC)


def test_judge_prompt_contains_anchors_and_evidence_rule():
    """Judge prompt carries every dimension, the 1/3/5 anchors, and the
    evidence-quote requirement."""
    prompt = build_judge_prompt(AGENT_RUBRIC)
    for d in AGENT_RUBRIC:
        assert d.key in prompt
    assert "1 =" in prompt and "3 =" in prompt and "5 =" in prompt
    assert "verbatim" in prompt.lower()
    assert "ground truth" in prompt.lower()


def test_weighted_overall_math():
    """Weighted overall = sum(score*weight)/sum(weight) over the rubric."""
    scores = [
        DimensionScore(dimension=d.key, score=5 if d.key == "grounding" else 3,
                       justification="j", evidence="e")
        for d in AGENT_RUBRIC
    ]
    overall = weighted_overall(scores, AGENT_RUBRIC)
    w_total = sum(d.weight for d in AGENT_RUBRIC)
    w_ground = next(d.weight for d in AGENT_RUBRIC if d.key == "grounding")
    expected = (5 * w_ground + 3 * (w_total - w_ground)) / w_total
    assert overall == pytest.approx(expected)


def test_weighted_overall_ignores_unknown_dimensions():
    """Scores for dimensions not in the rubric are skipped, not crashed on."""
    scores = [
        DimensionScore(dimension="grounding", score=4, justification="j", evidence="e"),
        DimensionScore(dimension="made_up", score=1, justification="j", evidence="e"),
    ]
    overall = weighted_overall(scores, AGENT_RUBRIC)
    assert overall == pytest.approx(4.0)


# ── Panel judge selection ─────────────────────────────────────────────


def test_panel_excludes_author():
    """Panel mode: every provider except the output's author judges it."""
    assert judges_for("gemini", ["gemini", "claude"], "panel") == ["claude"]
    assert judges_for("claude", ["gemini", "claude"], "panel") == ["gemini"]


def test_single_judge_mode():
    """Naming a provider forces that single judge even for its own output."""
    assert judges_for("gemini", ["gemini", "claude"], "gemini") == ["gemini"]


def test_panel_with_one_provider_falls_back_to_self():
    """A single-provider bench cannot exclude the author; judge = author."""
    assert judges_for("gemini", ["gemini"], "panel") == ["gemini"]


def test_deepseek_judge_is_registered():
    """The default judge is DeepSeek v4 Pro via OpenRouter — a
    non-contestant, so self-preference bias cannot arise."""
    assert "deepseek" in JUDGE_MODELS
    assert JUDGE_MODELS["deepseek"] == "openrouter:deepseek/deepseek-v4-pro"


def test_make_judge_agent_resolves_deepseek():
    """make_judge_agent accepts the non-contestant judge key."""
    agent = make_judge_agent("deepseek", AGENT_RUBRIC)
    assert "deepseek-v4-pro" in str(agent.model)


def test_make_judge_agent_deepseek_high_effort():
    """The DeepSeek judge requests high reasoning effort."""
    agent = make_judge_agent("deepseek", AGENT_RUBRIC)
    settings = agent.model_settings or {}
    assert settings.get("openrouter_reasoning", {}).get("effort") == "high"


def test_deepseek_judge_uses_prompted_output():
    """OpenRouter judges use PromptedOutput: reasoning models emit the
    output as JSON text rather than reliably calling an output tool."""
    agent = make_judge_agent("deepseek", AGENT_RUBRIC)
    assert "Prompted" in type(agent._output_schema).__name__


def test_judge_retry_backs_off_on_api_errors():
    """Transient API errors (rate limits) retry with backoff before dropping."""
    from pitcher_narratives.bench.judge import with_retry

    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 too many requests")
        return "ok"

    assert with_retry(flaky, attempts=3, backoffs=(1, 2), _sleep=sleeps.append) == "ok"
    assert calls["n"] == 3
    assert sleeps == [1, 2]


def test_judge_retry_raises_after_exhaustion():
    """After all attempts fail, the last error propagates (caller drops the judge)."""
    from pitcher_narratives.bench.judge import with_retry

    def always_fails():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        with_retry(always_fails, attempts=2, backoffs=(0,), _sleep=lambda s: None)


# ── Scorecard aggregation ─────────────────────────────────────────────


def _judged(score: int, rubric) -> JudgedOutput:
    return JudgedOutput(
        scores=[DimensionScore(dimension=d.key, score=score, justification="j",
                               evidence="e") for d in rubric],
        overall_comment="c",
    )


def test_rubric_for_namespaced_capsule_tiers():
    """Namespaced capsule tiers resolve to CAPSULE_RUBRIC; specialists to AGENT."""
    assert _rubric_for("capsule") is CAPSULE_RUBRIC
    assert _rubric_for("capsule:report") is CAPSULE_RUBRIC
    assert _rubric_for("capsule:recap") is CAPSULE_RUBRIC
    assert _rubric_for("capsule:changes") is CAPSULE_RUBRIC
    assert _rubric_for("specialist:stuff") is AGENT_RUBRIC
    assert _rubric_for("specialist:trends") is AGENT_RUBRIC


def test_aggregate_means_across_judges():
    """Two judges' scores for one output average per dimension."""
    records = [
        JudgedRecord(provider="gemini", tier="capsule", judge="claude",
                     judged=_judged(4, CAPSULE_RUBRIC)),
        JudgedRecord(provider="gemini", tier="capsule", judge="gemini",
                     judged=_judged(2, CAPSULE_RUBRIC)),
    ]
    agg = aggregate(records)
    assert agg["gemini"]["capsule"]["dimensions"]["grounding"] == pytest.approx(3.0)
    assert agg["gemini"]["capsule"]["overall"] == pytest.approx(3.0)


def test_render_report_contains_providers_and_dimensions():
    """Markdown report names providers, tiers, and dimension scores."""
    records = [
        JudgedRecord(provider="gemini", tier="specialist:stuff", judge="claude",
                     judged=_judged(4, AGENT_RUBRIC)),
        JudgedRecord(provider="claude", tier="specialist:stuff", judge="gemini",
                     judged=_judged(3, AGENT_RUBRIC)),
    ]
    report = render_report(aggregate(records), meta={"pitcher": "Test, Guy"})
    assert "gemini" in report and "claude" in report
    assert "specialist:stuff" in report
    assert "grounding" in report


# ── Runner ────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not __import__("pitcher_narratives.data", fromlist=["statcast_parquet_path"]).statcast_parquet_path(2026).exists(),
    reason="statcast parquet files not present (set STATCAST_PATH)",
)
def test_run_provider_captures_all_tiers():
    """A provider run captures 5 specialists + exec summary + capsule and
    the ground-truth context document."""
    captured = run_provider(
        TEST_PITCHER, provider="gemini", thinking="low",
        _model_override=TestModel(call_tools=[]),
    )
    assert captured.ok
    assert captured.error is None
    assert captured.wall_s >= 0
    for key in ("specialist:stuff", "specialist:location", "specialist:runvalue",
                "specialist:trends:report", "specialist:game_shape", "capsule:report"):
        assert key in captured.outputs, f"missing {key}"
        assert captured.outputs[key]
        assert captured.ground_truths.get(key), f"missing ground truth for {key}"
    # Each tier is judged against ITS author's actual input, not the
    # generic context doc -- otherwise the judge calls provided data
    # 'invented' and grounding scores are artifacts.
    assert "Arsenal Physical Profile" in captured.ground_truths["specialist:stuff"]
    assert "Specialist Analysis" in captured.ground_truths["capsule:report"]


@pytest.mark.skipif(
    not __import__("pitcher_narratives.data", fromlist=["statcast_parquet_path"]).statcast_parquet_path(2026).exists(),
    reason="statcast parquet files not present (set STATCAST_PATH)",
)
def test_run_provider_captures_per_mode_capsules():
    """A multi-mode run captures a namespaced capsule + exec summary per mode,
    the four mode-agnostic specialists once, and a per-mode TRENDS specialist
    whose ground truth carries the CHANGES frame comparison."""
    from pitcher_narratives.personas import get_narration_mode

    modes = [get_narration_mode("report"), get_narration_mode("changes")]
    captured = run_provider(
        TEST_PITCHER, provider="gemini", thinking="low",
        modes=modes, _model_override=TestModel(call_tools=[]),
    )
    assert captured.ok
    # Four specialists captured once, mode-agnostic.
    for spec in ("specialist:stuff", "specialist:location", "specialist:runvalue",
                 "specialist:game_shape"):
        assert captured.outputs[spec]
        assert captured.ground_truths.get(spec), f"missing ground truth for {spec}"
    # No bare, un-namespaced trends tier survives.
    assert "specialist:trends" not in captured.outputs
    # TRENDS is captured per mode, each with its own ground truth.
    for mode_id in ("report", "changes"):
        trends = f"specialist:trends:{mode_id}"
        assert captured.outputs[trends]
        assert captured.ground_truths.get(trends), f"missing ground truth for {trends}"
    # The fix: the CHANGES trends ground truth carries the prior-vs-recent
    # frame comparison the specialist actually saw; REPORT's does not.
    changes_gt = captured.ground_truths["specialist:trends:changes"].lower()
    report_gt = captured.ground_truths["specialist:trends:report"].lower()
    assert "prior window" in changes_gt
    assert "prior window" not in report_gt
    assert changes_gt != report_gt
    for mode_id in ("report", "changes"):
        cap = f"capsule:{mode_id}"
        assert captured.outputs.get(cap), f"missing {cap}"
        assert "Specialist Analysis" in captured.ground_truths[cap]
    # No bare "capsule" key survives the namespacing.
    assert "capsule" not in captured.outputs


# ── CLI ───────────────────────────────────────────────────────────────


def test_parse_args_defaults(monkeypatch):
    import sys

    from pitcher_narratives.config import PROVIDERS

    monkeypatch.setattr(sys, "argv", ["bench", "-p", "693433"])
    args = parse_args()
    assert args.pitcher == 693433
    assert set(args.providers.split(",")) == set(PROVIDERS)
    assert args.judges == "deepseek"


def test_contestant_judge_uses_tool_output():
    """Contestant-provider judges (e.g. claude) keep tool-mode structured
    output; PromptedOutput is only for OpenRouter reasoning models that
    emit JSON as text."""
    agent = make_judge_agent("claude", AGENT_RUBRIC)
    assert "claude" in str(agent.model)
    assert "Prompted" not in type(agent._output_schema).__name__
    settings = agent.model_settings or {}
    assert "openrouter_reasoning" not in settings


def test_parse_args_mode_and_prior_defaults(monkeypatch):
    import sys as _sys

    from pitcher_narratives.temporal import _DEFAULT_PRIOR_APPEARANCES

    monkeypatch.setattr(_sys, "argv", ["bench", "-p", "693433"])
    args = parse_args()
    assert args.mode == "report"
    assert args.prior == _DEFAULT_PRIOR_APPEARANCES


def test_parse_args_accepts_comma_mode(monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys, "argv", ["bench", "-p", "693433", "--mode", "report,recap"])
    args = parse_args()
    assert args.mode == "report,recap"


def test_resolve_bench_modes_valid_and_invalid():
    from pitcher_narratives.bench.__main__ import _resolve_bench_modes

    modes = _resolve_bench_modes("report,changes")
    assert [m.id for m in modes] == ["report", "changes"]
    with pytest.raises(SystemExit) as exc:
        _resolve_bench_modes("bogus")
    assert exc.value.code == 2
    with pytest.raises(SystemExit):
        _resolve_bench_modes(" , ")
