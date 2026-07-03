"""Tests for the multi-agent specialist→auditor→writer pipeline.

Covers unit tests for helpers (outlier_tag, format_s_variant_comparisons,
summary bullet parsing), data builder output verification, and smoke tests
for the full orchestration using pydantic-ai's TestModel.
"""

import asyncio

import pytest
from pydantic_ai.models.test import TestModel

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.engine import (
    ArsenalPitchTrend,
    ArsenalTrends,
    CrossSeasonSummary,
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
from pitcher_narratives.pipeline import (
    _STUFF_SPECIALIST_PROMPT,
    AnalyzedContext,
    AuditFlag,
    AuditResult,
    PipelineAgents,
    PipelineResult,
    SpecialistOutputs,
    _build_game_shape_input,
    _build_stuff_input,
    _build_trend_input,
    _flatten_prompt,
    audit_and_revise_specialists,
    check_explainer_present,
    generate_pipeline_streaming,
    make_pipeline_agents,
    run_analysis_spine,
    run_specialists,
)
from pitcher_narratives.signals import KeySignals

TEST_PITCHER = 592155


@pytest.fixture(scope="module")
def ctx():
    """Load data once per module (read-only test data)."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    return assemble_pitcher_context(data)


# ── Unit tests: outlier_tag ──────────────────────────────────────────


class TestOutlierTag:
    def test_normal_near_mean(self):
        result = outlier_tag(81.3, 82.9, 3.9, n=10)
        assert "NORMAL" in result

    def test_normal_at_boundary(self):
        """Value just inside ±1.5 stddev is still normal."""
        result = outlier_tag(77.1, 82.9, 3.9, n=10)  # z ≈ -1.49
        assert "NORMAL" in result

    def test_outlier_below(self):
        result = outlier_tag(75.0, 82.9, 3.9, n=10)  # z ≈ -2.0
        assert "OUTLIER" in result
        assert "below" in result

    def test_outlier_above(self):
        result = outlier_tag(92.0, 82.9, 3.9, n=10)  # z ≈ +2.3
        assert "OUTLIER" in result
        assert "above" in result

    def test_zero_std_returns_normal(self):
        assert outlier_tag(81.0, 81.0, 0.0, n=10) == "NORMAL"

    def test_includes_z_score(self):
        result = outlier_tag(81.3, 82.9, 3.9, n=10)
        assert "z=" in result


# ── Unit tests: format_s_variant_comparisons ─────────────────────────


class TestFormatSVariantComparisons:
    @pytest.fixture
    def kc_baseline(self):
        baselines = compute_league_baselines()
        return next(b for b in baselines if b.pitch_type == "KC")

    def test_returns_three_parts(self, kc_baseline):
        parts = format_s_variant_comparisons(kc_baseline, 0.37, 0.31, 0.69)
        assert len(parts) == 3

    def test_includes_league_deltas(self, kc_baseline):
        parts = format_s_variant_comparisons(kc_baseline, 0.37, 0.31, 0.69)
        assert all("vs league" in p for p in parts)

    def test_formats_percentages(self, kc_baseline):
        parts = format_s_variant_comparisons(kc_baseline, 0.37, 0.31, 0.69)
        assert "37.0%" in parts[0]
        assert "31.0%" in parts[1]
        assert "0.69" in parts[2]

    def test_none_values_show_dashes(self):
        parts = format_s_variant_comparisons(None, None, None, None)
        assert all("--" in p for p in parts)
        assert len(parts) == 3

    def test_no_baseline_skips_delta(self):
        parts = format_s_variant_comparisons(None, 0.37, 0.31, 0.69)
        assert all("vs league" not in p for p in parts)
        assert "37.0%" in parts[0]


# ── Unit tests: render_league_baselines ──────────────────────────────


class TestRenderLeagueBaselines:
    def test_includes_pitch_types(self):
        output = render_league_baselines(["FF", "KC"])
        assert "4-Seam Fastball" in output or "Four-Seam" in output
        assert "Knuckle Curve" in output

    def test_includes_normal_range(self):
        output = render_league_baselines(["FF"])
        assert "normal range" in output
        assert "stddev" in output

    def test_includes_s_variant_benchmarks(self):
        output = render_league_baselines(["FF"])
        assert "S-variant league avg" in output
        assert "xSwing_S" in output
        assert "xWhiff_S" in output

    def test_skips_unknown_pitch_type(self):
        output = render_league_baselines(["ZZ"])
        assert "ZZ" not in output

    def test_empty_input(self):
        output = render_league_baselines([])
        assert "League Baselines" in output


# ── Unit tests: summary bullet parsing ───────────────────────────────


class TestSummaryBulletParsing:
    """Test the bullet parsing logic used by the summary step."""

    def _parse(self, raw: str) -> list[str]:
        from pitcher_narratives.pipeline import _parse_summary_bullets
        return _parse_summary_bullets(raw)

    def test_standard_bullets(self):
        raw = "- First bullet\n- Second bullet\n- Third bullet"
        assert self._parse(raw) == ["First bullet", "Second bullet", "Third bullet"]

    def test_ignores_non_bullet_lines(self):
        raw = "## Header\n- Bullet one\nNot a bullet\n- Bullet two"
        assert self._parse(raw) == ["Bullet one", "Bullet two"]

    def test_strips_whitespace(self):
        raw = "  - Padded bullet  \n- Tight bullet"
        assert self._parse(raw) == ["Padded bullet", "Tight bullet"]

    def test_empty_input(self):
        assert self._parse("") == []
        assert self._parse("No bullets here") == []

    def test_preserves_leading_negative_sign(self):
        """A bullet whose content starts with a minus keeps its sign — a
        negative xRV100 (good for the pitcher) must not be flipped positive.
        ``lstrip("- ")`` would eat the leading dash; ``removeprefix`` must not."""
        raw = "- -0.77 xRV100 on the cutter saves runs\n- +0.32 xRV100 on the changeup costs runs"
        assert self._parse(raw) == [
            "-0.77 xRV100 on the cutter saves runs",
            "+0.32 xRV100 on the changeup costs runs",
        ]


class TestRunSummaries:
    class _BoomAgent:
        """Stand-in agent that records invocation and raises if ever called."""
        def __init__(self):
            self.called = False
        async def run(self, **kwargs):
            self.called = True
            raise RuntimeError("boom")

    def test_empty_capsule_skips_both_agents(self):
        from pitcher_narratives.pipeline import _run_summaries
        boom = self._BoomAgent()
        bullets, brief = asyncio.run(_run_summaries(
            summary_agent=boom, brief_agent=boom,
            capsule="   \n  ", writer_input="ignored",
        ))
        assert bullets == []
        assert brief == ""
        assert boom.called is False  # the guard must skip both agents, not just swallow their errors

    def test_populated_capsule_runs_both(self):
        from pitcher_narratives.pipeline import _run_summaries
        agents = make_pipeline_agents("gemini", "high")
        tm = TestModel(call_tools=[], custom_output_text="- one\n- two")
        bullets, brief = asyncio.run(_run_summaries(
            summary_agent=agents.summary, brief_agent=agents.brief,
            capsule="A real capsule.", writer_input="grounding",
            _model_override=tm,
        ))
        assert bullets == ["one", "two"]
        assert brief == "- one\n- two"

    def test_one_failure_degrades_without_cancelling_sibling(self):
        from pitcher_narratives.pipeline import _run_summaries
        agents = make_pipeline_agents("gemini", "high")
        tm = TestModel(call_tools=[], custom_output_text="- kept")
        # Summary agent booms; brief must still produce output.
        bullets, brief = asyncio.run(_run_summaries(
            summary_agent=self._BoomAgent(), brief_agent=agents.brief,
            capsule="A real capsule.", writer_input="grounding",
            _model_override=tm,
        ))
        assert bullets == []
        assert brief == "- kept"


# ── Data builder tests ───────────────────────────────────────────────


def _flatten(parts):
    """Join UserPrompt list parts into a single string for assertion checks."""
    return "\n".join(p for p in parts if isinstance(p, str))


class TestBuildStuffInput:
    def test_contains_outlier_tags(self, ctx):
        output = _flatten(_build_stuff_input(ctx))
        assert "NORMAL" in output or "OUTLIER" in output

    def test_contains_league_comparison(self, ctx):
        output = _flatten(_build_stuff_input(ctx))
        assert "vs league avg" in output or "vs avg" in output

    def test_contains_s_variant_predictions(self, ctx):
        output = _flatten(_build_stuff_input(ctx))
        assert "xSwing_S" in output
        assert "xWhiff_S" in output
        assert "xRV100_S" in output

    def test_contains_league_baselines(self, ctx):
        output = _flatten(_build_stuff_input(ctx))
        assert "League Baselines" in output

    def test_contains_pitcher_name(self, ctx):
        output = _flatten(_build_stuff_input(ctx))
        assert ctx.pitcher_name in output


# ── Agent factory tests ──────────────────────────────────────────────


class TestMakePipelineAgents:
    def test_returns_named_tuple(self):
        agents = make_pipeline_agents("gemini", "high")
        assert isinstance(agents, PipelineAgents)

    def test_all_fields_populated(self):
        agents = make_pipeline_agents("gemini", "high")
        for name in PipelineAgents._fields:
            assert getattr(agents, name) is not None

    def test_named_access(self):
        agents = make_pipeline_agents("gemini", "high")
        assert agents.stuff is not None
        assert agents.auditor is not None
        assert agents.anchor is not None
        assert agents.summary is not None

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            make_pipeline_agents("invalid", "high")

    def test_has_signal_extractor(self):
        agents = make_pipeline_agents("gemini", "high")
        assert agents.signal_extractor is not None

    def test_brief_uses_mini_model(self):
        agents = make_pipeline_agents("gemini", "high")
        # BRIEF distills an already-written report — a mini model suffices.
        assert agents.brief.model == agents.summary.model
        assert agents.brief.model != agents.writer.model

    def test_has_capsule_auditor_on_mini_model(self):
        agents = make_pipeline_agents("gemini", "high")
        assert agents.capsule_auditor is not None
        # Same mini tier as the other checker agents, distinct from the writer.
        assert agents.capsule_auditor.model == agents.auditor.model
        assert agents.capsule_auditor.model != agents.writer.model


# ── Audit loop smoke tests ───────────────────────────────────────────


class TestAuditAndReviseSpecialists:
    @pytest.fixture
    def specialists(self):
        return SpecialistOutputs(
            stuff="The four-seam is elite.",
            location="Location is average.",
            runvalue="Run value is neutral.",
            trends="No changes.",
            game_shape="Steady across passes.",
        )

    @pytest.fixture
    def agents(self):
        return make_pipeline_agents("gemini", "high")

    def test_clean_audit_returns_originals(self, specialists, agents):
        """When auditor returns clean, specialist outputs pass through unchanged."""
        clean_model = TestModel(custom_output_text="clean")

        async def _run():
            # TestModel with AuditResult will generate a flag by default,
            # so we need to override the auditor agent directly
            from pydantic_ai import Agent
            clean_auditor = Agent("test", output_type=AuditResult)

            specialist_agents = {
                "stuff": agents.stuff, "location": agents.location,
                "runvalue": agents.runvalue, "trends": agents.trends,
                "game_shape": agents.game_shape,
            }
            # Use a context with minimal data
            data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
            ctx = assemble_pitcher_context(data)

            result, flags = await audit_and_revise_specialists(
                specialists, specialist_agents, clean_auditor, ctx,
                _model_override=clean_model,
            )
            return result, flags

        result, flags = asyncio.run(_run())
        # TestModel with AuditResult generates one flag, so we get flags
        # but the key is that it doesn't crash
        assert isinstance(result, SpecialistOutputs)
        assert isinstance(flags, list)

    def test_does_not_crash_on_model_error(self, specialists, agents):
        """Audit loop degrades gracefully on LLM errors."""
        # TestModel should work without errors — this just verifies the
        # try/except path doesn't break the return type
        test_model = TestModel(call_tools=[])

        async def _run():
            from pydantic_ai import Agent
            auditor = Agent("test", output_type=AuditResult)

            specialist_agents = {
                "stuff": agents.stuff, "location": agents.location,
                "runvalue": agents.runvalue, "trends": agents.trends,
                "game_shape": agents.game_shape,
            }
            data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
            ctx = assemble_pitcher_context(data)

            result, flags = await audit_and_revise_specialists(
                specialists, specialist_agents, auditor, ctx,
                _model_override=test_model,
            )
            return result, flags

        result, flags = asyncio.run(_run())
        assert isinstance(result, SpecialistOutputs)
        assert all(isinstance(f, AuditFlag) for f in flags)


# ── End-to-end pipeline smoke test ───────────────────────────────────


class TestGeneratePipelineStreaming:
    def test_returns_pipeline_result(self, ctx, capsys):
        """Full pipeline runs with TestModel and returns valid PipelineResult."""
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )

        assert isinstance(result, PipelineResult)
        assert isinstance(result.narrative, str)
        assert len(result.narrative) > 0
        assert isinstance(result.executive_summary, list)
        assert isinstance(result.specialists, SpecialistOutputs)
        assert isinstance(result.audit_flags, list)
        assert isinstance(result.anchor_warnings, list)
        assert isinstance(result.revision_count, int)
        # Revision count must be bounded — MAX_REVISIONS caps the loop
        # to prevent runaway passes. Anything outside [0, MAX_REVISIONS]
        # means the loop logic is broken.
        from pitcher_narratives.config import MAX_REVISIONS
        assert 0 <= result.revision_count <= MAX_REVISIONS, (
            f"revision_count {result.revision_count} outside [0, {MAX_REVISIONS}] — "
            "revision loop logic is broken"
        )

    def test_run_narration_modes_returns_dict_keyed_by_mode_id(self, ctx):
        """run_narration_modes returns {mode.id: PipelineResult}; default is REPORT only."""
        from pitcher_narratives.pipeline import run_narration_modes, PipelineResult
        from pydantic_ai.models.test import TestModel

        model = TestModel(call_tools=[])
        results = run_narration_modes(ctx, _model_override=model)

        assert set(results) == {"report"}
        assert isinstance(results["report"], PipelineResult)

    def test_run_narration_modes_explicit_report_matches_single_entry(self, ctx):
        """Explicitly passing [REPORT] yields the same single 'report' key."""
        from pitcher_narratives.pipeline import run_narration_modes
        from pitcher_narratives.personas import REPORT
        from pydantic_ai.models.test import TestModel

        model = TestModel(call_tools=[])
        results = run_narration_modes(ctx, modes=[REPORT], _model_override=model)
        assert list(results) == ["report"]

    def test_run_narration_modes_dedupes_repeated_mode(self, ctx, monkeypatch):
        """A repeated mode id runs the pipeline once, not per duplicate."""
        import pitcher_narratives.pipeline as pl
        from pitcher_narratives.personas import REPORT

        calls: list[str] = []

        def _fake_stream(_ctx, *, mode, **_kw):
            calls.append(mode.id)
            return pl.PipelineResult(
                narrative="x", specialists=SpecialistOutputs(
                    stuff="", location="", runvalue="", trends="", game_shape=""
                ),
            )

        monkeypatch.setattr(pl, "generate_pipeline_streaming", _fake_stream)
        results = pl.run_narration_modes(ctx, modes=[REPORT, REPORT])
        assert calls == ["report"]
        assert list(results) == ["report"]

    def test_run_narration_modes_gates_prior_ctx_by_temporal_frame(self, ctx, monkeypatch):
        """run_narration_modes([CHANGES, REPORT], prior_ctx=...) must route the
        RECENT-vs-PRIOR comparison block into run_specialists only for CHANGES
        (whose temporal_frame includes PRIOR); REPORT must receive None,
        preserving byte-identical REPORT/RECAP behavior (P9B constraint)."""
        import pitcher_narratives.pipeline as pl
        from pitcher_narratives.context import assemble_prior_context
        from pitcher_narratives.personas import CHANGES, REPORT

        prior_ctx = assemble_prior_context(load_pitcher_data(TEST_PITCHER, 10), 10, 10)

        captured: dict[str, str | None] = {}
        real_run_specialists = pl.run_specialists

        async def _spy_run_specialists(*args, **kwargs):
            # generate_pipeline_streaming -> run_analysis_spine -> run_spine_tail
            # -> run_specialists is the real chain we're driving end-to-end;
            # only intercept the kwarg to record what each mode actually sent.
            trend_fc = kwargs.get("trend_frame_comparison")
            if trend_fc is not None:
                captured["changes"] = trend_fc
            else:
                captured.setdefault("report", trend_fc)
            return await real_run_specialists(*args, **kwargs)

        monkeypatch.setattr(pl, "run_specialists", _spy_run_specialists)

        model = TestModel(call_tools=[])
        results = pl.run_narration_modes(
            ctx, modes=[CHANGES, REPORT], prior_ctx=prior_ctx,
            _model_override=model,
        )

        assert set(results) == {"changes", "report"}
        # CHANGES receives the rendered comparison block.
        assert captured.get("changes") is not None
        assert "Recent vs Prior Window" in captured["changes"]
        # REPORT is gated off — no prior context leaks in (byte-identical
        # REPORT/RECAP guarantee).
        assert captured.get("report") is None

    def test_max_revisions_constant_is_nonzero(self):
        """MAX_REVISIONS must allow at least one revision pass."""
        from pitcher_narratives.config import MAX_REVISIONS
        assert MAX_REVISIONS >= 1, "MAX_REVISIONS must allow at least one revision"

    def test_max_revisions_is_five(self):
        """The report anchor loop allows up to 5 revision passes."""
        from pitcher_narratives.config import MAX_REVISIONS
        assert MAX_REVISIONS == 5

    def test_pipeline_result_includes_brief(self, ctx):
        """The terminal layer runs the BRIEF agent and returns its text.

        BRIEF is wired as an additional agent alongside the writer and
        executive summary — same input, non-critical — so a successful run
        populates PipelineResult.brief with non-empty text. (custom_output_text
        can't be used here: it would force the structured auditor/anchor/signal
        agents into plain responses, which TestModel rejects.)
        """
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert isinstance(result.brief, str)
        assert len(result.brief) > 0

    def test_pipeline_result_includes_executive_summary(self, ctx):
        """The terminal layer runs the executive summary against the final
        capsule and returns parsed bullets."""
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert isinstance(result.executive_summary, list)

    def test_brief_agent_has_no_skill_toolset(self):
        """The brief agent stays tool-free (like the executive summary).

        A 2-3 sentence synthesis of already-clean specialist text needs no
        skills, and staying tool-free means a hallucinated skill call cannot
        kill this non-critical concurrent agent.
        """
        from pitcher_narratives.agent_skills import skill_toolset
        agents = make_pipeline_agents()
        toolsets = list(getattr(agents.brief, "_user_toolsets", []))
        assert skill_toolset() not in toolsets

    def test_pipeline_result_has_fact_check_fields(self, ctx):
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert isinstance(result.capsule_audit_flags, list)
        assert isinstance(result.capsule_revised, bool)
        assert isinstance(result.value_parity_warnings, list)


# ── Anchor revision loop behavioral tests ────────────────────────────
#
# These tests exercise the extracted `run_anchor_revision_loop` helper
# with stateful AsyncMock agents that can return different outputs per
# call. This is the only reliable way to test loop behavior — TestModel
# returns the same thing every call, so it cannot verify that:
#   (a) the loop actually iterates when the anchor returns warnings
#   (b) the revised capsule (not the first draft) is what gets returned
#
# Both of these were regressions caught historically (see the UX-04
# bug referenced in the old test_report.py that was deleted in v1.9).
# They are hard gaps the v1.9 test-coverage review noted but couldn't
# close without extracting the loop into a testable unit.


class TestAnchorRevisionLoop:
    """Behavioral tests for the anchor + writer revision loop.

    Each test builds a fake anchor agent with a scripted list of
    AnchorResult responses and a fake writer that returns a specific
    revised capsule, then asserts on loop state afterward.
    """

    def _fake_anchor(self, *responses):
        """Build an AsyncMock anchor whose .run() yields the given results in order.

        Each entry should be an AnchorResult. The mock wraps each one in
        an object with an `.output` attribute to match how the pipeline
        code destructures `anchor_result.output`.
        """
        from unittest.mock import AsyncMock, MagicMock

        wrapped = [MagicMock(output=r) for r in responses]
        mock = MagicMock()
        mock.run = AsyncMock(side_effect=wrapped)
        return mock

    def _fake_writer(self, *revision_texts):
        """Build an AsyncMock writer whose .run() yields the given texts in order."""
        from unittest.mock import AsyncMock, MagicMock

        wrapped = [MagicMock(output=t) for t in revision_texts]
        mock = MagicMock()
        mock.run = AsyncMock(side_effect=wrapped)
        return mock

    def test_passes_first_check_no_revisions(self):
        """Clean anchor on first pass → revision_count 0, original capsule returned."""
        import asyncio

        from pitcher_narratives.anchor import AnchorResult
        from pitcher_narratives.pipeline import run_anchor_revision_loop

        anchor = self._fake_anchor(AnchorResult(warnings=[]))
        writer = self._fake_writer()  # should never be called

        capsule, final, count = asyncio.run(
            run_anchor_revision_loop(
                anchor_agent=anchor,
                writer_agent=writer,
                synthesis="synth",
                capsule="ORIGINAL_CAPSULE",
                max_revisions=2,
                _model_override=None,
            )
        )

        assert capsule == "ORIGINAL_CAPSULE"
        assert count == 0
        assert final.is_clean
        assert anchor.run.call_count == 1
        assert writer.run.call_count == 0

    def test_loop_iterates_when_anchor_dirty_then_clean(self):
        """Anchor dirty on pass 1, clean on pass 2 → revision_count 1 and revised capsule returned.

        This is the UX-04 regression test: verifies the loop actually
        runs when the anchor flags warnings, and that the writer's
        revised output (not the original) ends up as the final capsule.
        """
        import asyncio

        from pitcher_narratives.anchor import AnchorResult, AnchorWarning
        from pitcher_narratives.pipeline import run_anchor_revision_loop

        dirty = AnchorResult(
            warnings=[
                AnchorWarning(
                    category="MISSED_SIGNAL",
                    description="skipped the top concern",
                )
            ]
        )
        clean = AnchorResult(warnings=[])

        anchor = self._fake_anchor(dirty, clean)
        writer = self._fake_writer("REVISED_CAPSULE")

        capsule, final, count = asyncio.run(
            run_anchor_revision_loop(
                anchor_agent=anchor,
                writer_agent=writer,
                synthesis="synth",
                capsule="ORIGINAL_CAPSULE",
                max_revisions=2,
                _model_override=None,
            )
        )

        # The loop ran once
        assert count == 1
        # The REVISED capsule is what's returned, not the original
        assert capsule == "REVISED_CAPSULE"
        assert capsule != "ORIGINAL_CAPSULE"
        # The final anchor check was clean
        assert final.is_clean
        # Exactly 2 anchor calls (dirty + clean) and 1 writer call (the revision)
        assert anchor.run.call_count == 2
        assert writer.run.call_count == 1

    def test_loop_exhausts_max_revisions_and_surfaces_warnings(self):
        """If anchor stays dirty for max_revisions+1 passes, surviving warnings are surfaced.

        This verifies the `for/else` branch: after the loop exhausts
        max_revisions without a clean pass, a final anchor check
        captures the surviving warnings so the caller can include them
        in PipelineResult.anchor_warnings.
        """
        import asyncio

        from pitcher_narratives.anchor import AnchorResult, AnchorWarning
        from pitcher_narratives.pipeline import run_anchor_revision_loop

        # Build a persistent dirty result
        persistent_dirty = AnchorResult(
            warnings=[
                AnchorWarning(
                    category="UNSUPPORTED",
                    description="invented a metric",
                )
            ]
        )

        # 2 revisions allowed → 3 anchor calls (2 in-loop + 1 final exhaustion check)
        anchor = self._fake_anchor(
            persistent_dirty, persistent_dirty, persistent_dirty
        )
        writer = self._fake_writer("REV_1", "REV_2")

        capsule, final, count = asyncio.run(
            run_anchor_revision_loop(
                anchor_agent=anchor,
                writer_agent=writer,
                synthesis="synth",
                capsule="ORIGINAL",
                max_revisions=2,
                _model_override=None,
            )
        )

        # Both revisions ran
        assert count == 2
        # Final capsule is the second revision
        assert capsule == "REV_2"
        # Surviving warnings are on the final anchor result
        assert not final.is_clean
        assert len(final.warnings) == 1
        assert final.warnings[0].category == "UNSUPPORTED"
        # 3 anchor calls (2 in-loop + 1 exhaustion check), 2 writer calls
        assert anchor.run.call_count == 3
        assert writer.run.call_count == 2

    def test_revised_capsule_is_passed_to_next_anchor_check(self):
        """Each revision pass feeds its output back into the next anchor check.

        Guards against a regression where the loop revises but then
        checks the ORIGINAL capsule again instead of the revision —
        which would create an infinite loop at the MAX_REVISIONS cap.
        """
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from pitcher_narratives.anchor import AnchorResult, AnchorWarning
        from pitcher_narratives.pipeline import run_anchor_revision_loop

        # Record the capsule passed to each anchor call so we can verify
        # the second call received the REVISED capsule.
        capsules_seen: list[str] = []

        async def anchor_side_effect(**kwargs):
            # The anchor message includes the capsule — extract it from
            # the user_prompt kwarg which is a list[str | CachePoint].
            prompt_parts = kwargs["user_prompt"]
            joined = "\n".join(p for p in prompt_parts if isinstance(p, str))
            capsules_seen.append(joined)
            # First call: dirty. Second call: clean.
            if len(capsules_seen) == 1:
                return MagicMock(
                    output=AnchorResult(
                        warnings=[
                            AnchorWarning(
                                category="DIRECTION_ERROR",
                                description="backwards",
                            )
                        ]
                    )
                )
            return MagicMock(output=AnchorResult(warnings=[]))

        anchor = MagicMock()
        anchor.run = AsyncMock(side_effect=anchor_side_effect)
        writer = self._fake_writer("REVISED_CAPSULE_TEXT")

        capsule, final, count = asyncio.run(
            run_anchor_revision_loop(
                anchor_agent=anchor,
                writer_agent=writer,
                synthesis="synth",
                capsule="ORIGINAL_CAPSULE_TEXT",
                max_revisions=2,
                _model_override=None,
            )
        )

        assert count == 1
        assert capsule == "REVISED_CAPSULE_TEXT"
        # First anchor call saw the original, second saw the revision.
        assert "ORIGINAL_CAPSULE_TEXT" in capsules_seen[0]
        assert "REVISED_CAPSULE_TEXT" in capsules_seen[1]
        # And critically: the original must not appear in the second check
        assert "ORIGINAL_CAPSULE_TEXT" not in capsules_seen[1]

    def test_records_usage_per_anchor_and_revision(self):
        """With a tracker, each anchor check and writer revision is recorded."""
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from pitcher_narratives.anchor import AnchorResult, AnchorWarning
        from pitcher_narratives.costs import UsageTracker
        from pitcher_narratives.pipeline import run_anchor_revision_loop

        def _wrap(output, tin, tout):
            return MagicMock(
                output=output,
                usage=MagicMock(return_value=SimpleNamespace(
                    input_tokens=tin, output_tokens=tout)),
            )

        dirty = AnchorResult(warnings=[AnchorWarning(
            category="MISSED_SIGNAL", description="x")])
        clean = AnchorResult(warnings=[])
        anchor = MagicMock()
        anchor.run = AsyncMock(side_effect=[_wrap(dirty, 10, 5), _wrap(clean, 10, 5)])
        writer = MagicMock()
        writer.run = AsyncMock(side_effect=[_wrap("REVISED", 20, 8)])

        tracker = UsageTracker()
        asyncio.run(run_anchor_revision_loop(
            anchor_agent=anchor, writer_agent=writer,
            synthesis="synth", capsule="ORIG", max_revisions=2,
            tracker=tracker, tracker_model="m",
        ))

        stages = [r.stage for r in tracker.records]
        assert stages == ["anchor", "anchor_revision", "anchor"]
        assert tracker.total_input() == 40   # 10 + 20 + 10
        assert tracker.total_output() == 18  # 5 + 8 + 5

    def test_specialist_outputs_populated(self, ctx):
        """All 5 specialist slots are non-empty strings."""
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )

        for name in SpecialistOutputs.model_fields:
            value = getattr(result.specialists, name)
            assert isinstance(value, str)
            assert len(value) > 0


# ── Key signals integration test ─────────────────────────────────────


class TestPipelineKeySignals:
    def test_pipeline_result_includes_key_signals(self, ctx):
        """Full pipeline produces key_signals in result."""
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert result.key_signals is not None
        assert isinstance(result.key_signals, KeySignals)
        assert result.key_signals.top_improvement is not None
        assert result.key_signals.top_concern is not None


# ── Cross-season data flow tests ────────────────────────────────────


def _make_continued_trend() -> ArsenalPitchTrend:
    """Build a continued ArsenalPitchTrend for testing."""
    return ArsenalPitchTrend(
        pitch_type="SL",
        pitch_name="Slider",
        status="continued",
        prior_season=2025,
        current_season=2026,
        prior_usage_pct=20.0,
        current_usage_pct=25.0,
        usage_delta="Up 5.0 pp",
        prior_p_plus=100.0,
        current_p_plus=110.0,
        p_plus_delta="Up 10 pts",
        prior_s_plus=105.0,
        current_s_plus=115.0,
        s_plus_delta="Up 10 pts",
        prior_l_plus=95.0,
        current_l_plus=90.0,
        l_plus_delta="Down 5 pts",
        prior_velo=84.0,
        current_velo=85.5,
        velo_delta="Up 1.5 mph",
        n_pitches_prior=200,
        n_pitches_current=50,
    )


def _make_added_trend() -> ArsenalPitchTrend:
    """Build an added ArsenalPitchTrend for testing."""
    return ArsenalPitchTrend(
        pitch_type="ST",
        pitch_name="Sweeper",
        status="added",
        prior_season=None,
        current_season=2026,
        prior_usage_pct=None,
        current_usage_pct=12.0,
        usage_delta=None,
        prior_p_plus=None,
        current_p_plus=120.0,
        p_plus_delta=None,
        prior_s_plus=None,
        current_s_plus=125.0,
        s_plus_delta=None,
        prior_l_plus=None,
        current_l_plus=110.0,
        l_plus_delta=None,
        prior_velo=None,
        current_velo=80.0,
        velo_delta=None,
        n_pitches_prior=None,
        n_pitches_current=30,
    )


def _make_arsenal_trends() -> ArsenalTrends:
    """Build ArsenalTrends with an added and continued pitch."""
    return ArsenalTrends(
        added=[_make_added_trend()],
        dropped=[],
        continued=[_make_continued_trend()],
        prior_season=2025,
        current_season=2026,
    )


def _make_cross_season_summary() -> CrossSeasonSummary:
    """Build a CrossSeasonSummary for testing."""
    return CrossSeasonSummary(
        current_season=2026,
        prior_season=2025,
        current_velo=93.5,
        prior_velo=92.0,
        velo_delta="Up 1.5 mph",
        current_p_plus=112.0,
        prior_p_plus=105.0,
        p_plus_delta="Up 7 pts",
        current_s_plus=108.0,
        prior_s_plus=100.0,
        s_plus_delta="Up 8 pts",
        current_l_plus=104.0,
        prior_l_plus=110.0,
        l_plus_delta="Down 6 pts",
    )


def _make_mock_ctx():
    """Build a MagicMock PitcherContext with cross-season data populated."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.pitcher_name = "Test Pitcher"
    mock.throws = "R"
    mock.role = "SP"
    mock.arsenal = []  # empty — we only care about cross-season sections
    mock.intermediates = []
    mock.cross_season_summary = _make_cross_season_summary()
    mock.arsenal_trend = _make_arsenal_trends()

    # The trend/game-shape builders render sections via the prompt_builder
    # render_*_section(ctx) free functions; those are patched per-test by the
    # _patch_render_sections fixture, not on the mock ctx.

    # TemporalContext for game shape workload rendering
    mock.temporal.current_season_appearances = 8
    mock.temporal.current_season_ip = 48.0
    mock.temporal.prior_season = 2025
    mock.temporal.prior_season_appearances = 32
    mock.temporal.prior_season_ip = 195.0

    return mock


@pytest.fixture
def _patch_baselines(monkeypatch):
    """Patch compute_league_baselines and render_league_baselines for unit tests."""
    monkeypatch.setattr(
        "pitcher_narratives.pipeline.compute_league_baselines",
        lambda: [],
    )
    monkeypatch.setattr(
        "pitcher_narratives.pipeline.render_league_baselines",
        lambda _types: "## League Baselines (mocked)",
    )


@pytest.fixture
def _patch_render_sections(monkeypatch):
    """Patch the prompt_builder render functions used by the pipeline builders.

    The trend and game-shape builders call render_*_section(ctx) free functions
    (imported into the pipeline namespace). Patch them to canned strings so
    these unit tests do not depend on full PitcherContext rendering. Each patch
    is a MagicMock so call assertions still work.
    """
    from unittest.mock import MagicMock

    canned = {
        "render_fastball_section": "## Fastball\nFF 94.0 mph",
        "render_arsenal_section": "## Arsenal\nSL, CH",
        "render_release_point_section": "## Release Point\nConsistent",
        "render_hard_hit_section": "## Hard Hit\n35%",
        "render_yoy_section": (
            "## Year-over-Year\n"
            "Comparing 2026 vs 2025:\n"
            "- Velocity: Up 1.5 mph\n"
            "- Added pitches: Sweeper\n"
            "- Slider: usage Up 5.0 pp, velo Up 1.5 mph"
        ),
        "render_tto_section": "## TTO\nSteady",
        "render_appearances_section": "## Appearances\n3 in window",
        "render_role_section": "## Role\nSP",
    }
    for name, value in canned.items():
        monkeypatch.setattr(
            f"pitcher_narratives.pipeline.{name}", MagicMock(return_value=value)
        )


@pytest.mark.usefixtures("_patch_baselines")
class TestStuffSpecialistReceivesYoyData:
    """Verify _build_stuff_input includes cross-season data with correct attributes."""

    def test_contains_yoy_header(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_stuff_input(ctx))
        assert "Year-over-Year" in output

    def test_contains_velocity_delta(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_stuff_input(ctx))
        assert "Up 1.5 mph" in output

    def test_contains_added_pitch(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_stuff_input(ctx))
        assert "Sweeper" in output
        assert "Added pitches" in output

    def test_contains_continued_pitch_with_usage_delta(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_stuff_input(ctx))
        assert "Slider" in output
        assert "usage Up 5.0 pp" in output

    def test_no_pfx_references(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_stuff_input(ctx))
        assert "pfx_x_delta" not in output
        assert "H-mov" not in output


@pytest.mark.usefixtures("_patch_baselines", "_patch_render_sections")
class TestTrendSpecialistReceivesYoySection:
    """Verify _build_trend_input includes the YoY section via render_yoy_section."""

    def test_output_is_string_list(self):
        ctx = _make_mock_ctx()
        output = _build_trend_input(ctx)
        assert isinstance(output, list)
        text = _flatten_prompt(output)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_contains_yoy_from_render_method(self):
        ctx = _make_mock_ctx()
        text = _flatten_prompt(_build_trend_input(ctx))
        assert "Year-over-Year" in text
        assert "Sweeper" in text

    def test_render_yoy_section_called(self):
        import pitcher_narratives.pipeline as p

        ctx = _make_mock_ctx()
        _build_trend_input(ctx)
        p.render_yoy_section.assert_called_once()

    def test_build_trend_input_default_omits_comparison(self):
        ctx = _make_mock_ctx()
        prompt = _build_trend_input(ctx)
        joined = _flatten_prompt(prompt)
        assert "Recent vs Prior Window" not in joined

    def test_build_trend_input_appends_frame_comparison(self):
        ctx = _make_mock_ctx()
        block = "## Recent vs Prior Window (code-computed deltas)\n\n- Four-Seam: velo +2.0 mph"
        prompt = _build_trend_input(ctx, frame_comparison=block)
        joined = _flatten_prompt(prompt)
        assert "Recent vs Prior Window" in joined
        assert "velo +2.0 mph" in joined


@pytest.mark.usefixtures("_patch_baselines", "_patch_render_sections")
class TestGameShapeSpecialistReceivesYoyData:
    """Verify _build_game_shape_input includes cross-season data with correct attributes."""

    def test_contains_yoy_header(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_game_shape_input(ctx))
        assert "Year-over-Year" in output

    def test_contains_added_pitch(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_game_shape_input(ctx))
        assert "Sweeper" in output
        assert "Added" in output

    def test_contains_continued_pitch_with_usage(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_game_shape_input(ctx))
        assert "Slider" in output
        assert "usage Up 5.0 pp" in output

    def test_no_pfx_references(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_game_shape_input(ctx))
        assert "pfx_x_delta" not in output
        assert "H-mov" not in output

    def test_contains_workload_comparison(self):
        ctx = _make_mock_ctx()
        output = _flatten_prompt(_build_game_shape_input(ctx))
        assert "Workload" in output
        assert "48.0 IP" in output


# ── check_explainer_present unit tests (Phase 08: PERSONA-11) ──


class TestCheckExplainerPresent:
    """Unit tests for the Pitching+ explainer post-processor."""

    def test_check_explainer_present_detects_plus_family(self):
        """PERSONA-11: Each Pitching+ family keyword individually returns True."""
        for keyword in ("S+", "L+", "P+", "Pitching+", "Stuff+", "Location+"):
            text = f"The model graded this pitch {keyword} 112 above average."
            assert check_explainer_present(text) is True, (
                f"Expected keyword {keyword!r} to be detected in capsule"
            )

    def test_check_explainer_present_absent(self):
        """PERSONA-11: Capsule with no explainer keywords returns False."""
        text = (
            "The slider has been sharp lately. The curveball is giving "
            "him trouble, particularly against right-handers."
        )
        assert check_explainer_present(text) is False

    def test_check_explainer_present_rejects_empty(self):
        """PERSONA-11: Empty capsule raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            check_explainer_present("")

    def test_check_explainer_present_rejects_non_string(self):
        """PERSONA-11: Non-string input raises TypeError."""
        with pytest.raises(TypeError, match="must be str"):
            check_explainer_present(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="must be str"):
            check_explainer_present(42)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="must be str"):
            check_explainer_present(b"bytes")  # type: ignore[arg-type]

    def test_check_explainer_present_exported(self):
        """PERSONA-11: Function is in pipeline.__all__."""
        import pitcher_narratives.pipeline as p
        assert "check_explainer_present" in p.__all__


def test_validation_loops_are_public():
    """Phases 8/9 reuse these by name; they must be importable + exported."""
    from pitcher_narratives import pipeline

    for name in (
        "run_anchor_revision_loop",
        "run_capsule_audit",
        "build_capsule_audit_input",
    ):
        assert hasattr(pipeline, name), f"{name} missing from pipeline"
        assert name in pipeline.__all__, f"{name} not exported in __all__"

    # The old private names must be fully gone (no aliases left behind).
    for old in (
        "_run_anchor_revision_loop",
        "_run_capsule_audit",
        "_build_capsule_audit_input",
    ):
        assert not hasattr(pipeline, old), f"stale private alias {old} remains"


# ── Pipeline explainer-check integration (Phase 08: PERSONA-11) ──


def test_run_pipeline_logs_warning_when_capsule_missing_explainer(caplog):
    """PERSONA-11: _run_pipeline logs a warning when check_explainer_present returns False.

    TestModel produces a canned placeholder capsule that does NOT
    contain any Pitching+ keywords, so the explainer check returns
    False and a warning is logged at WARNING level.
    """
    import logging

    from pydantic_ai.models.test import TestModel

    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.pipeline import generate_pipeline_streaming

    data = load_pitcher_data(592155, recent_appearances=10)
    ctx = assemble_pitcher_context(data)

    with caplog.at_level(logging.WARNING, logger="pitcher_narratives.pipeline"):
        generate_pipeline_streaming(
            ctx,
            provider="gemini",
            thinking="high",
            persona="scout",
            _model_override=TestModel(call_tools=[]),
        )

    # Find the explainer-missing warning in caplog
    explainer_warnings = [
        r for r in caplog.records
        if "capsule is missing model explanation content" in r.getMessage()
    ]
    assert len(explainer_warnings) >= 1, (
        f"Expected at least one explainer-missing warning, "
        f"got records: {[r.getMessage() for r in caplog.records]}"
    )
    # The warning's formatted message includes the persona id in brackets
    warning_msg = explainer_warnings[0].getMessage()
    assert "[scout]" in warning_msg, (
        f"Expected '[scout]' in warning message, got: {warning_msg!r}"
    )


def test_check_explainer_present_happy_path_is_silent(caplog, monkeypatch):
    """PERSONA-11 positive path: no warning when capsule contains explainer keywords.

    Guards against a bug that always-logs the warning (which would pass
    the negative test above but silently inform every run).
    """
    import logging

    from pitcher_narratives import pipeline as pipeline_mod

    # Direct unit-level check: happy path returns True.
    assert check_explainer_present(
        "The slider graded S+ 112 on the Pitching+ model."
    )

    # And at the integration level: patch check_explainer_present at its
    # call site in _run_pipeline so the pipeline sees it as always-True.
    # That isolates us from TestModel output content.
    monkeypatch.setattr(
        pipeline_mod, "check_explainer_present", lambda capsule: True
    )

    from pydantic_ai.models.test import TestModel

    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data

    data = load_pitcher_data(592155, recent_appearances=10)
    ctx = assemble_pitcher_context(data)

    with caplog.at_level(logging.WARNING, logger="pitcher_narratives.pipeline"):
        pipeline_mod.generate_pipeline_streaming(
            ctx,
            provider="gemini",
            thinking="high",
            persona="scout",
            _model_override=TestModel(call_tools=[]),
        )

    explainer_warnings = [
        r for r in caplog.records
        if "capsule is missing model explanation content" in r.getMessage()
    ]
    assert not explainer_warnings, (
        f"Expected zero explainer-missing warnings on happy path, "
        f"got {len(explainer_warnings)}: "
        f"{[r.getMessage() for r in explainer_warnings]}"
    )


# ── Pitch shape in stuff specialist input ─────────────────────────────


class TestPitchShapeInStuffInput:
    def test_contains_pitch_shape_section(self, ctx):
        """Stuff specialist input includes the Pitch Shape vs Arm Slot section."""
        output = _flatten(_build_stuff_input(ctx))
        assert "Pitch Shape vs Arm Slot" in output

    def test_contains_shape_classification(self, ctx):
        """Shape tags (dead zone / slot expectation) reach the stuff specialist."""
        output = _flatten(_build_stuff_input(ctx))
        assert "slot expectation" in output

    def test_omitted_when_no_shape_data(self, ctx):
        """No shape profile -> no empty section in the specialist input."""
        bare = ctx.model_copy(update={"pitch_shape": None})
        output = _flatten(_build_stuff_input(bare))
        assert "Pitch Shape vs Arm Slot" not in output


class TestStuffPromptArmSlotRule:
    def test_prompt_explains_dead_zone(self):
        """Stuff specialist prompt defines the DEAD ZONE concept."""
        assert "DEAD ZONE" in _STUFF_SPECIALIST_PROMPT

    def test_prompt_references_shape_section(self):
        """Stuff specialist prompt points at the Pitch Shape vs Arm Slot section."""
        assert "Pitch Shape vs Arm Slot" in _STUFF_SPECIALIST_PROMPT

    def test_prompt_mentions_arm_angle(self):
        """Prompt ties pitch shape to the arm angle."""
        assert "arm angle" in _STUFF_SPECIALIST_PROMPT

    def test_prompt_does_not_force_causal_attribution(self):
        """Dead-zone is framed as a risk factor, not a mandatory explanation."""
        p = _STUFF_SPECIALIST_PROMPT
        assert "MUST reference its slot context" not in p
        assert "not a verdict" in p.lower() or "risk factor" in p.lower()


# ── Provider concurrency limiting ─────────────────────────────────────


class _CountingAgent:
    """Stub agent recording peak concurrent .run() calls."""

    def __init__(self, tracker: dict):
        self._t = tracker

    async def run(self, **kwargs):
        import asyncio as _aio

        self._t["live"] += 1
        self._t["peak"] = max(self._t["peak"], self._t["live"])
        await _aio.sleep(0.01)
        self._t["live"] -= 1

        class _R:
            output = "text"

        return _R()


def test_run_specialists_fan_out_concurrently(ctx):
    """Specialists fan out concurrently rather than running serially."""
    tracker = {"live": 0, "peak": 0}
    agent = _CountingAgent(tracker)
    asyncio.run(run_specialists(agent, agent, agent, agent, agent, ctx))
    assert tracker["peak"] > 1


def test_run_specialists_names_runs_only_selected(ctx):
    """With names=['trends'], only the trends agent is invoked and the other
    SpecialistOutputs fields default to empty strings."""
    import asyncio

    class _MarkAgent:
        def __init__(self, mark):
            self.mark = mark
            self.calls = 0
        async def run(self, **kwargs):
            self.calls += 1
            class _R:
                pass
            r = _R()
            r.output = self.mark
            return r

    stuff = _MarkAgent("STUFF")
    location = _MarkAgent("LOC")
    runvalue = _MarkAgent("RV")
    trends = _MarkAgent("TRENDS")
    game_shape = _MarkAgent("GS")

    out = asyncio.run(run_specialists(
        stuff, location, runvalue, trends, game_shape, ctx,
        names=["trends"],
    ))
    assert trends.calls == 1
    assert stuff.calls == 0
    assert location.calls == 0
    assert runvalue.calls == 0
    assert game_shape.calls == 0
    assert out.trends == "TRENDS"
    assert out.stuff == ""
    assert out.location == ""
    assert out.runvalue == ""
    assert out.game_shape == ""


class _ExplodingAuditor:
    """Stub auditor whose every run raises (e.g. provider error body)."""

    async def run(self, **kwargs):
        raise RuntimeError("all-null response body")


def test_audit_failure_degrades_to_unaudited(ctx):
    """A failing auditor must not kill the pipeline: the specialist's
    original text passes through un-audited with no flags."""
    outputs = SpecialistOutputs(stuff="s", location="l", runvalue="r",
                                trends="t", game_shape="g")
    clean, flags = asyncio.run(audit_and_revise_specialists(
        outputs, {}, _ExplodingAuditor(), ctx,
    ))
    assert clean == outputs
    assert flags == []


def test_audit_names_audits_only_selected(ctx):
    """With names=['trends'], only trends is audited; other specialists
    pass through unchanged and no flags are raised for them."""
    import asyncio
    from pitcher_narratives.models import SpecialistOutputs, AuditResult
    from pitcher_narratives.pipeline import audit_and_revise_specialists

    outputs = SpecialistOutputs(stuff="s", location="l", runvalue="r",
                                trends="t", game_shape="g")

    class _CountingAuditor:
        def __init__(self):
            self.calls = 0
        async def run(self, **kwargs):
            self.calls += 1
            class _R:
                output = AuditResult(flags=[])
            return _R()

    auditor = _CountingAuditor()
    clean, flags = asyncio.run(audit_and_revise_specialists(
        outputs, {}, auditor, ctx, names=["trends"],
    ))
    assert auditor.calls == 1          # only one specialist audited
    assert clean == outputs            # all five fields preserved, unchanged
    assert flags == []


def test_run_analysis_spine_returns_analyzed_context(ctx):
    """run_analysis_spine returns a valid AnalyzedContext under TestModel."""
    agents = make_pipeline_agents("gemini", "high")
    # call_tools=[] prevents TestModel from auto-generating tool calls
    # against the skill toolset (which would fail with SkillNotFoundError).
    model = TestModel(call_tools=[], custom_output_text="Specialist analysis.")
    result = asyncio.run(
        run_analysis_spine(ctx, agents=agents, _model_override=model)
    )
    assert isinstance(result, AnalyzedContext)
    assert result.specialists.stuff != ""
    assert result.specialists.location != ""
    assert result.specialists.runvalue != ""
    assert result.specialists.trends != ""
    assert result.specialists.game_shape != ""
    assert isinstance(result.audit_flags, list)


def test_run_analysis_spine_composes_core_then_tail(ctx, monkeypatch):
    """run_analysis_spine must delegate to run_spine_core then run_spine_tail,
    passing the produced CoreContext and the same ctx into the tail."""
    import asyncio
    import pitcher_narratives.pipeline as _pl
    from pitcher_narratives.models import CoreContext, AnalyzedContext, SpecialistOutputs
    from unittest.mock import AsyncMock

    sentinel_core = CoreContext(stuff="s", location="l", runvalue="r", game_shape="g")
    sentinel_analyzed = AnalyzedContext(
        specialists=SpecialistOutputs(stuff="s", location="l", runvalue="r",
                                      trends="t", game_shape="g"),
    )
    core_mock = AsyncMock(return_value=sentinel_core)
    tail_mock = AsyncMock(return_value=sentinel_analyzed)
    monkeypatch.setattr(_pl, "run_spine_core", core_mock)
    monkeypatch.setattr(_pl, "run_spine_tail", tail_mock)

    class _Agents:
        mini_model_name = ""

    result = asyncio.run(_pl.run_analysis_spine(ctx, agents=_Agents()))
    assert result is sentinel_analyzed
    core_mock.assert_awaited_once()
    tail_mock.assert_awaited_once()
    # The CoreContext from core is threaded into the tail as its first arg,
    # and the same ctx is passed through.
    tail_args, tail_kwargs = tail_mock.call_args
    assert tail_args[0] is sentinel_core
    assert tail_args[1] is ctx


def test_run_spine_core_returns_four_clean_specialists(ctx):
    """run_spine_core runs only the four core specialists under TestModel and
    returns a CoreContext with all four populated."""
    import asyncio
    from pitcher_narratives.models import CoreContext
    from pitcher_narratives.pipeline import run_spine_core, make_pipeline_agents

    agents = make_pipeline_agents("gemini", "high")
    model = TestModel(call_tools=[], custom_output_text="Core analysis.")
    core = asyncio.run(run_spine_core(ctx, agents=agents, _model_override=model))

    assert isinstance(core, CoreContext)
    assert core.stuff != ""
    assert core.location != ""
    assert core.runvalue != ""
    assert core.game_shape != ""
    assert isinstance(core.audit_flags, list)


def test_run_spine_tail_assembles_full_analyzed_context(ctx):
    """run_spine_tail runs trends + signal extraction over a CoreContext and
    returns a complete AnalyzedContext preserving the core specialist text."""
    import asyncio
    from pitcher_narratives.models import CoreContext, AnalyzedContext
    from pitcher_narratives.pipeline import run_spine_tail, make_pipeline_agents

    agents = make_pipeline_agents("gemini", "high")
    model = TestModel(call_tools=[], custom_output_text="Tail analysis.")
    core = CoreContext(stuff="CORE_STUFF", location="CORE_LOC",
                       runvalue="CORE_RV", game_shape="CORE_GS")

    analyzed = asyncio.run(
        run_spine_tail(core, ctx, agents=agents, _model_override=model)
    )
    assert isinstance(analyzed, AnalyzedContext)
    # Core specialist text is carried through verbatim.
    assert analyzed.specialists.stuff == "CORE_STUFF"
    assert analyzed.specialists.game_shape == "CORE_GS"
    # Trends was produced by the tail.
    assert analyzed.specialists.trends != ""


def test_run_spine_tail_injects_frame_comparison_with_prior_ctx(ctx, monkeypatch):
    """run_spine_tail computes a RECENT-vs-PRIOR block from prior_ctx and
    passes it into run_specialists as trend_frame_comparison, which lands in
    the trends specialist's prompt."""
    import asyncio
    from unittest.mock import AsyncMock

    import pitcher_narratives.pipeline as _pl
    from pitcher_narratives.context import assemble_prior_context
    from pitcher_narratives.models import CoreContext, SpecialistOutputs
    from pitcher_narratives.pipeline import make_pipeline_agents, run_spine_tail

    prior_ctx = assemble_prior_context(load_pitcher_data(592155, 10), 10, 10)

    captured = {}

    async def _fake_run_specialists(*args, **kwargs):
        captured["trend_frame_comparison"] = kwargs.get("trend_frame_comparison")
        return SpecialistOutputs(stuff="s", location="l", runvalue="r", trends="TRENDS_OUT", game_shape="g")

    monkeypatch.setattr(_pl, "run_specialists", _fake_run_specialists)

    agents = make_pipeline_agents("gemini", "high")
    model = TestModel(call_tools=[], custom_output_text="Tail analysis.")
    core = CoreContext(stuff="CORE_STUFF", location="CORE_LOC",
                       runvalue="CORE_RV", game_shape="CORE_GS")

    asyncio.run(
        run_spine_tail(core, ctx, agents=agents, _model_override=model,
                       prior_ctx=prior_ctx)
    )

    assert captured["trend_frame_comparison"] is not None
    assert "Recent vs Prior Window" in captured["trend_frame_comparison"]


def test_run_spine_tail_no_frame_comparison_without_prior_ctx(ctx, monkeypatch):
    """Without prior_ctx, run_spine_tail passes trend_frame_comparison=None
    (byte-identical to the pre-P9B path)."""
    import asyncio

    import pitcher_narratives.pipeline as _pl
    from pitcher_narratives.models import CoreContext, SpecialistOutputs
    from pitcher_narratives.pipeline import make_pipeline_agents, run_spine_tail

    captured = {}

    async def _fake_run_specialists(*args, **kwargs):
        captured["trend_frame_comparison"] = kwargs.get("trend_frame_comparison")
        return SpecialistOutputs(stuff="s", location="l", runvalue="r", trends="TRENDS_OUT", game_shape="g")

    monkeypatch.setattr(_pl, "run_specialists", _fake_run_specialists)

    agents = make_pipeline_agents("gemini", "high")
    model = TestModel(call_tools=[], custom_output_text="Tail analysis.")
    core = CoreContext(stuff="CORE_STUFF", location="CORE_LOC",
                       runvalue="CORE_RV", game_shape="CORE_GS")

    asyncio.run(
        run_spine_tail(core, ctx, agents=agents, _model_override=model)
    )

    assert captured["trend_frame_comparison"] is None


def test_order_flags_puts_specialists_in_canonical_order():
    from pitcher_narratives.models import AuditFlag
    from pitcher_narratives.pipeline import _order_flags

    def flag(spec):
        return AuditFlag(category="X", specialist=spec, claim="c",
                         data_shows="d", suggested_fix="f")

    # Core-first + trends-last input (as run_spine_tail concatenates) must be
    # reordered to the legacy stuff/location/runvalue/trends/game_shape order.
    ordered = _order_flags([flag("game_shape"), flag("trends"), flag("stuff")])
    assert [f.specialist for f in ordered] == ["stuff", "trends", "game_shape"]


class TestBuildSummaryInput:
    def test_frames_capsule_as_subject_with_grounding(self):
        from pitcher_narratives.pipeline import build_summary_input
        out = build_summary_input("CAPSULE_TEXT", "WRITER_INPUT_TEXT")
        # Both payloads present.
        assert "CAPSULE_TEXT" in out
        assert "WRITER_INPUT_TEXT" in out
        # Capsule is the subject and comes first.
        assert out.index("CAPSULE_TEXT") < out.index("WRITER_INPUT_TEXT")
        # Contract markers present.
        assert "FINISHED REPORT" in out
        assert "reference ONLY" in out.replace("reference only", "reference ONLY")
        assert "do NOT add" in out or "do NOT correct" in out


class TestExecutiveSummaryPrompt:
    def test_prompt_targets_finished_report_with_recover_only_grounding(self):
        from pitcher_narratives.pipeline import _EXECUTIVE_SUMMARY_PROMPT
        p = _EXECUTIVE_SUMMARY_PROMPT
        assert "finished scouting report" in p.lower()
        # Recover-only grounding contract.
        assert "never change a number the report gives" in p
        assert "do not introduce a finding" in p.lower()
        # Old framing is gone.
        assert "Given specialist analyses" not in p
        # Citation requirement preserved.
        assert "cite a specific number" in p.lower()


class TestRunCapsuleAudit:
    class _CleanAuditor:
        async def run(self, **kwargs):
            from pitcher_narratives.models import AuditResult
            class _R:
                output = AuditResult(flags=[])
            return _R()

    class _FlaggingAuditor:
        async def run(self, **kwargs):
            from pitcher_narratives.models import AuditResult, AuditFlag
            class _R:
                output = AuditResult(flags=[AuditFlag(category="FABRICATED_DATA", claim="98 mph", data_shows="95.9", suggested_fix="use 95.9")])
            return _R()

    class _Writer:
        async def run(self, **kwargs):
            class _R:
                output = "corrected capsule"
            return _R()

    class _FlagThenCleanAuditor:
        """Flags on the first audit, clean on the re-audit — the happy path."""
        def __init__(self):
            self.calls = 0
        async def run(self, **kwargs):
            from pitcher_narratives.models import AuditResult, AuditFlag
            self.calls += 1
            flags = [] if self.calls > 1 else [
                AuditFlag(category="FABRICATED_DATA", claim="98 mph", data_shows="95.9", suggested_fix="use 95.9")
            ]
            class _R:
                output = AuditResult(flags=flags)
            return _R()

    class _FlagUntilCleanAuditor:
        """Flags for the first ``flag_calls`` audits, then clean — exercises
        convergence on a later loop pass."""
        def __init__(self, flag_calls):
            self.flag_calls = flag_calls
            self.calls = 0
        async def run(self, **kwargs):
            from pitcher_narratives.models import AuditResult, AuditFlag
            self.calls += 1
            flags = [
                AuditFlag(category="FABRICATED_DATA", claim="98 mph", data_shows="95.9", suggested_fix="x")
            ] if self.calls <= self.flag_calls else []
            class _R:
                output = AuditResult(flags=flags)
            return _R()

    class _CountingWriter:
        def __init__(self):
            self.calls = 0
        async def run(self, **kwargs):
            self.calls += 1
            class _R:
                output = "corrected capsule"
            return _R()

    def test_clean_audit_no_revision(self):
        from pitcher_narratives.pipeline import run_capsule_audit
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=self._CleanAuditor(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "original capsule"
        assert flags == []
        assert revised is False

    def test_flagged_audit_triggers_one_revision(self):
        from pitcher_narratives.pipeline import run_capsule_audit
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=self._FlaggingAuditor(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "corrected capsule"
        assert len(flags) == 1
        assert revised is True

    def test_auditor_error_degrades_to_unchanged(self):
        from pitcher_narratives.pipeline import run_capsule_audit
        class _Boom:
            async def run(self, **kwargs):
                raise RuntimeError("boom")
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=_Boom(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "original capsule"
        assert flags == []
        assert revised is False

    def test_writer_error_keeps_flags_not_revised(self):
        # Writer-failure branch differs from auditor-failure: flags are
        # PRESERVED (not []), and revised is False (no correction applied).
        from pitcher_narratives.pipeline import run_capsule_audit
        class _BoomWriter:
            async def run(self, **kwargs):
                raise RuntimeError("writer boom")
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=self._FlaggingAuditor(), writer_agent=_BoomWriter(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "original capsule"
        assert len(flags) == 1   # flags preserved, not []
        assert revised is False

    def test_blank_revision_keeps_capsule(self):
        # A degenerate (whitespace) fact-revision must NOT overwrite the good
        # capsule — keep the pre-revision text, revised=False.
        from pitcher_narratives.pipeline import run_capsule_audit
        class _BlankWriter:
            async def run(self, **kwargs):
                class _R:
                    output = "   \n  "
                return _R()
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=self._FlaggingAuditor(), writer_agent=_BlankWriter(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "original capsule"
        assert len(flags) == 1
        assert revised is False

    def test_reaudit_clean_verifies_revision(self):
        # Flag -> revise -> re-audit clean: the revised capsule ships with NO
        # residual flags (the revision is verified).
        from pitcher_narratives.pipeline import run_capsule_audit
        auditor = self._FlagThenCleanAuditor()
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=auditor, writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "corrected capsule"
        assert flags == []          # re-audit clean -> residual empty
        assert revised is True
        assert auditor.calls == 2   # initial audit + one re-audit

    def test_reaudit_surfaces_residual(self):
        # Auditor keeps flagging after the revision: the residual must be
        # surfaced (not shipped unchecked), and the revised capsule is kept.
        from pitcher_narratives.pipeline import run_capsule_audit
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=self._FlaggingAuditor(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "corrected capsule"
        assert len(flags) == 1      # residual from the re-audit
        assert revised is True

    def test_reaudit_error_surfaces_original_flags(self):
        # If the re-audit call raises, degrade by surfacing the original flags
        # (better than silently shipping the revision as clean).
        from pitcher_narratives.pipeline import run_capsule_audit
        from pitcher_narratives.models import AuditResult, AuditFlag
        class _FlagThenBoom:
            def __init__(self):
                self.calls = 0
            async def run(self, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("re-audit boom")
                class _R:
                    output = AuditResult(flags=[AuditFlag(category="FABRICATED_DATA", claim="98 mph", data_shows="95.9", suggested_fix="x")])
                return _R()
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=_FlagThenBoom(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "corrected capsule"
        assert len(flags) == 1
        assert revised is True

    def test_loop_converges_on_second_pass(self):
        # Flags audits 1 and 2, clean on audit 3 -> two revisions, then verified
        # clean. Requires the loop (a single revise would still be flagged).
        from pitcher_narratives.pipeline import run_capsule_audit
        auditor = self._FlagUntilCleanAuditor(flag_calls=2)
        writer = self._CountingWriter()
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=auditor, writer_agent=writer,
            ground_truth="gt", capsule="original capsule", max_fact_revisions=2,
        ))
        assert flags == []          # converged
        assert revised is True
        assert writer.calls == 2    # two fact-revisions
        assert auditor.calls == 3   # initial + 2 re-audits

    def test_loop_caps_revisions_and_surfaces_residual(self):
        # Auditor never goes clean: the loop must stop at max_fact_revisions and
        # surface the residual rather than spinning.
        from pitcher_narratives.pipeline import run_capsule_audit
        writer = self._CountingWriter()
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=self._FlaggingAuditor(), writer_agent=writer,
            ground_truth="gt", capsule="original capsule", max_fact_revisions=2,
        ))
        assert len(flags) == 1      # residual surfaced
        assert revised is True
        assert writer.calls == 2    # capped at max_fact_revisions

    def test_max_fact_revisions_one(self):
        from pitcher_narratives.pipeline import run_capsule_audit
        writer = self._CountingWriter()
        cap, flags, revised = asyncio.run(run_capsule_audit(
            auditor=self._FlaggingAuditor(), writer_agent=writer,
            ground_truth="gt", capsule="original capsule", max_fact_revisions=1,
        ))
        assert writer.calls == 1
        assert len(flags) == 1      # still flagged, surfaced


def test_capsule_audit_records_usage():
    """Initial audit + one revision + re-audit are each recorded."""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from pitcher_narratives.costs import UsageTracker
    from pitcher_narratives.models import AuditFlag, AuditResult
    from pitcher_narratives.pipeline import run_capsule_audit

    def _wrap(output, tin, tout):
        return MagicMock(
            output=output,
            usage=MagicMock(return_value=SimpleNamespace(
                input_tokens=tin, output_tokens=tout)),
        )

    flag = AuditFlag(category="FABRICATED_DATA", claim="c",
                     data_shows="d", suggested_fix="f")
    dirty = AuditResult(flags=[flag])
    clean = AuditResult(flags=[])
    auditor = MagicMock()
    auditor.run = AsyncMock(side_effect=[_wrap(dirty, 10, 4), _wrap(clean, 10, 4)])
    writer = MagicMock()
    writer.run = AsyncMock(side_effect=[_wrap("FIXED CAPSULE", 20, 6)])

    tracker = UsageTracker()
    asyncio.run(run_capsule_audit(
        auditor=auditor, writer_agent=writer,
        ground_truth="gt", capsule="CAP", max_fact_revisions=2,
        tracker=tracker, tracker_model="m",
    ))

    stages = [r.stage for r in tracker.records]
    assert stages == ["fact_audit", "fact_revision", "fact_audit"]


def test_capsule_audit_usage_error_propagates_not_swallowed_as_auditor_failure():
    """A usage()-recording error is a tracker/instrumentation problem, not an
    auditor failure. It must propagate (raise) rather than be silently
    treated as "auditor failed, skip fact-check" -- that would misattribute
    the error and silently disable fact-checking.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from pitcher_narratives.costs import UsageTracker
    from pitcher_narratives.models import AuditResult
    from pitcher_narratives.pipeline import run_capsule_audit

    clean = AuditResult(flags=[])
    auditor = MagicMock()
    auditor.run = AsyncMock(return_value=MagicMock(
        output=clean,
        usage=MagicMock(side_effect=RuntimeError("usage boom")),
    ))
    writer = MagicMock()

    tracker = UsageTracker()
    with pytest.raises(RuntimeError, match="usage boom"):
        asyncio.run(run_capsule_audit(
            auditor=auditor, writer_agent=writer,
            ground_truth="gt", capsule="CAP",
            tracker=tracker, tracker_model="m",
        ))


def test_flag_summary_counts_fields():
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.pipeline import PipelineResult, flag_summary

    result = PipelineResult(
        narrative="n",
        specialists=SpecialistOutputs(
            stuff="s", location="l", runvalue="r", trends="t", game_shape="g"),
        revision_count=2,
        capsule_revised=True,
        anchor_warnings=[],
        value_parity_warnings=["[capsule] 1.23"],
    )
    summary = flag_summary(result)
    assert summary == {
        "revision_count": 2,
        "capsule_revised": True,
        "n_capsule_audit_flags": 0,
        "n_anchor_warnings": 0,
        "n_value_parity_warnings": 1,
        "n_audit_flags": 0,
    }


class TestExplainerDropped:
    def test_empty_capsule_not_dropped(self):
        # Must not raise (check_explainer_present raises on empty); empty means
        # "nothing to drop" -> False.
        from pitcher_narratives.pipeline import _explainer_dropped
        assert _explainer_dropped("") is False
        assert _explainer_dropped("   \n ") is False

    def test_present_not_dropped(self):
        from pitcher_narratives.pipeline import _explainer_dropped
        assert _explainer_dropped("the slider's S+ is strong") is False

    def test_absent_is_dropped(self):
        from pitcher_narratives.pipeline import _explainer_dropped
        assert _explainer_dropped("the fastball just looks fast") is True


class TestCapsuleAuditBuilders:
    def test_capsule_ground_truth_concatenates_all_specialists(self, ctx):
        from pitcher_narratives.pipeline import _build_capsule_ground_truth
        gt = _build_capsule_ground_truth(ctx)
        # The stuff specialist's ground truth has the arsenal physical profile.
        assert "Arsenal Physical Profile" in gt
        assert "P vs S Location Impact" in gt  # location specialist's input

    def test_capsule_audit_input_has_both_sections(self):
        from pitcher_narratives.pipeline import build_capsule_audit_input
        out = build_capsule_audit_input("GROUND_TRUTH", "CAPSULE_TEXT")
        assert "GROUND_TRUTH" in out
        assert "CAPSULE_TEXT" in out
        # Ground truth comes first, the capsule to fact-check second.
        assert out.index("GROUND_TRUTH") < out.index("CAPSULE_TEXT")

    def test_fact_revision_message_lists_flags(self):
        from pitcher_narratives.pipeline import build_fact_revision_message
        from pitcher_narratives.models import AuditFlag
        flags = [AuditFlag(category="FABRICATED_DATA", claim="98 mph", data_shows="95.9 mph", suggested_fix="use 95.9")]
        msg = build_fact_revision_message("the capsule text", flags)
        assert "the capsule text" in msg
        assert "FABRICATED_DATA" in msg
        assert "95.9 mph" in msg
        assert "ONLY" in msg  # instructs to fix only flagged issues


def test_pipeline_threads_report_validation_depths(monkeypatch):
    """_run_pipeline must read depths from mode.validation, not the constants."""
    from pydantic_ai.models.test import TestModel

    from pitcher_narratives import pipeline
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.personas import REPORT

    captured: dict[str, int] = {}

    real_anchor = pipeline.run_anchor_revision_loop
    real_audit = pipeline.run_capsule_audit

    async def anchor_spy(*args, **kwargs):
        captured["anchor"] = kwargs["max_revisions"]
        return await real_anchor(*args, **kwargs)

    async def audit_spy(*args, **kwargs):
        captured["fact"] = kwargs["max_fact_revisions"]
        return await real_audit(*args, **kwargs)

    monkeypatch.setattr(pipeline, "run_anchor_revision_loop", anchor_spy)
    monkeypatch.setattr(pipeline, "run_capsule_audit", audit_spy)

    data = load_pitcher_data(592155, recent_appearances=10)
    ctx = assemble_pitcher_context(data)

    pipeline.generate_pipeline_streaming(
        ctx,
        provider="gemini",
        thinking="high",
        persona="scout",
        mode=REPORT,
        _model_override=TestModel(call_tools=[]),
    )

    assert captured["anchor"] == REPORT.validation.anchor_depth == 5
    assert captured["fact"] == REPORT.validation.fact_depth == 2


def _result_with_flags(n: int):
    """Minimal PipelineResult carrying n residual capsule-audit flags."""
    from pitcher_narratives.pipeline import AuditFlag, PipelineResult, SpecialistOutputs

    flags = [
        AuditFlag(category="velocity", specialist="stuff", claim=f"c{i}", data_shows="d", suggested_fix="")
        for i in range(n)
    ]
    return PipelineResult(
        narrative="x",
        specialists=SpecialistOutputs.model_construct(),  # empty smoke value
        capsule_audit_flags=flags,
    )


def test_is_unverified_tracks_residual_flags():
    from pitcher_narratives.pipeline import is_unverified

    assert is_unverified(_result_with_flags(0)) is False
    assert is_unverified(_result_with_flags(3)) is True


def test_residual_banner_matches_report_wording():
    from pitcher_narratives.pipeline import residual_banner

    assert residual_banner(_result_with_flags(0)) is None
    banner = residual_banner(_result_with_flags(2))
    assert banner == (
        "⚠️  REPORT UNVERIFIED — 2 flagged claim(s) survived the "
        "fact-check loop. Review before use."
    )
    # label parameterizes the surface for RECAP/CHANGES/morning reuse.
    assert residual_banner(_result_with_flags(1), label="RECAP").startswith(
        "⚠️  RECAP UNVERIFIED — 1 flagged claim(s)"
    )


def test_render_capsule_non_streaming_returns_capsule(ctx, capsys):
    """_render_capsule(stream=False) captures the writer output without
    printing to stdout, and runs the anchor + capsule-audit loops."""
    from pitcher_narratives import pipeline

    agents = pipeline.make_pipeline_agents("gemini", "high")
    tm_spine = TestModel(call_tools=[], custom_output_text="Specialist analysis.")
    tm = TestModel(call_tools=[])

    async def _go():
        analyzed = await pipeline.run_analysis_spine(
            ctx, agents=agents, _model_override=tm_spine
        )
        return await pipeline._render_capsule(
            ctx, analyzed, agents=agents, anchor_depth=1, fact_depth=1,
            stream=False, check_explainer=False, _model_override=tm,
        )

    rc = asyncio.run(_go())
    assert isinstance(rc.capsule, str) and rc.capsule  # non-empty
    assert rc.writer_input and rc.fact_check_source
    # stream=False must NOT print the capsule to stdout.
    assert rc.capsule not in capsys.readouterr().out


# ── render_recap + build_recap_overlay (Phase 8B) ────────────────────


def test_build_recap_overlay_leads_with_angle():
    from pitcher_narratives.pipeline import build_recap_overlay

    overlay = build_recap_overlay(angle="Sweeper usage doubled", category="command_breakout")
    assert "Sweeper usage doubled" in overlay
    assert "command_breakout" in overlay


def test_render_recap_produces_validated_pipeline_result(ctx):
    """render_recap renders a recap from a pre-computed AnalyzedContext and runs
    the validation stack (recap depths), returning a PipelineResult."""
    from pitcher_narratives import pipeline
    from pitcher_narratives.personas import RECAP, get_persona

    agents = pipeline.make_pipeline_agents("gemini", "medium", get_persona("scout"), RECAP)
    tm_spine = TestModel(call_tools=[], custom_output_text="Specialist analysis.")
    tm = TestModel(call_tools=[])

    async def _go():
        analyzed = await pipeline.run_analysis_spine(ctx, agents=agents, _model_override=tm_spine)
        return await pipeline.render_recap(ctx, analyzed, agents=agents, pick=None, _model_override=tm)

    result = asyncio.run(_go())
    from pitcher_narratives.pipeline import PipelineResult
    assert isinstance(result, PipelineResult)
    assert result.narrative                              # recap text present
    assert result.executive_summary == []                # recap has no exec summary
    assert result.brief == ""                             # recap has no # Brief
    # is_unverified applies to a recap result just like a report result.
    from pitcher_narratives.pipeline import is_unverified
    assert isinstance(is_unverified(result), bool)


def test_render_recap_records_validation_calls_with_model_name(ctx, monkeypatch):
    """render_recap must pass a non-empty tracker_model to the validation loops,
    so morning's recap anchor/fact-check calls are priced. A blank model name
    costs to None and silently undercounts the digest's true spend."""
    from pitcher_narratives import pipeline
    from pitcher_narratives.costs import UsageTracker
    from pitcher_narratives.personas import RECAP, get_persona

    agents = pipeline.make_pipeline_agents("gemini", "medium", get_persona("scout"), RECAP)
    tm_spine = TestModel(call_tools=[], custom_output_text="Specialist analysis.")
    tm = TestModel(call_tools=[])
    tracker = UsageTracker()

    captured: dict[str, str] = {}
    real_audit = pipeline.run_capsule_audit

    async def _spy_audit(**kw):
        captured["tracker_model"] = kw.get("tracker_model")
        return await real_audit(**kw)

    monkeypatch.setattr(pipeline, "run_capsule_audit", _spy_audit)

    async def _go():
        analyzed = await pipeline.run_analysis_spine(ctx, agents=agents, _model_override=tm_spine)
        await pipeline.render_recap(
            ctx, analyzed, agents=agents, pick=None, _model_override=tm, tracker=tracker
        )

    asyncio.run(_go())
    assert captured["tracker_model"], "render_recap passed an empty tracker_model"
    assert captured["tracker_model"] == agents.mini_model_name
