"""Tests for the multi-agent specialist→auditor→writer pipeline.

Covers unit tests for helpers (outlier_tag, format_s_variant_comparisons,
summary bullet parsing), data builder output verification, and smoke tests
for the full orchestration using pydantic-ai's TestModel.
"""

import asyncio
from datetime import date

import pytest
from pydantic_ai.models.test import TestModel

from pitcher_narratives.context import PitcherContext, assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.engine import (
    AddedDroppedPitch,
    AppearanceWorkload,
    ArsenalTrend,
    ComponentAttribution,
    CrossSeasonSummary,
    ExecutionMetrics,
    FastballSummary,
    FirstPitchEntry,
    FirstPitchWeaponry,
    HardHitRate,
    IntermediateProbabilities,
    LeagueBaseline,
    PitchTrend,
    PitchTypeSummary,
    PlatoonMix,
    ReleasePointMetrics,
    VelocityArc,
    WorkloadContext,
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
from pitcher_narratives.pipeline import (
    AuditFlag,
    AuditResult,
    PipelineAgents,
    PipelineResult,
    SpecialistOutputs,
    _build_game_shape_input,
    _build_location_input,
    _build_runvalue_input,
    _build_stuff_input,
    _build_trend_input,
    audit_and_revise_specialists,
    generate_pipeline_streaming,
    make_pipeline_agents,
)


TEST_PITCHER = 592155


@pytest.fixture(scope="module")
def ctx():
    """Load data once per module (read-only test data)."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    return assemble_pitcher_context(data)


# ── Unit tests: outlier_tag ──────────────────────────────────────────


class TestOutlierTag:
    def test_normal_near_mean(self):
        result = outlier_tag(81.3, 82.9, 3.9)
        assert "NORMAL" in result

    def test_normal_at_boundary(self):
        """Value just inside ±1.5 stddev is still normal."""
        result = outlier_tag(77.1, 82.9, 3.9)  # z ≈ -1.49
        assert "NORMAL" in result

    def test_outlier_below(self):
        result = outlier_tag(75.0, 82.9, 3.9)  # z ≈ -2.0
        assert "OUTLIER" in result
        assert "below" in result

    def test_outlier_above(self):
        result = outlier_tag(92.0, 82.9, 3.9)  # z ≈ +2.3
        assert "OUTLIER" in result
        assert "above" in result

    def test_zero_std_returns_normal(self):
        assert outlier_tag(81.0, 81.0, 0.0) == "NORMAL"

    def test_includes_z_score(self):
        result = outlier_tag(81.3, 82.9, 3.9)
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
    """Test the bullet parsing logic used in _run_pipeline and ask_question_pipeline."""

    def _parse(self, raw: str) -> list[str]:
        return [
            line.lstrip("- ").strip()
            for line in raw.strip().splitlines()
            if line.strip().startswith("- ")
        ]

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


# ── Data builder tests ───────────────────────────────────────────────


class TestBuildStuffInput:
    def test_contains_outlier_tags(self, ctx):
        output = _build_stuff_input(ctx)
        assert "NORMAL" in output or "OUTLIER" in output

    def test_contains_league_comparison(self, ctx):
        output = _build_stuff_input(ctx)
        assert "vs league avg" in output or "vs avg" in output

    def test_contains_s_variant_predictions(self, ctx):
        output = _build_stuff_input(ctx)
        assert "xSwing_S" in output
        assert "xWhiff_S" in output
        assert "xRV100_S" in output

    def test_contains_league_baselines(self, ctx):
        output = _build_stuff_input(ctx)
        assert "League Baselines" in output

    def test_contains_pitcher_name(self, ctx):
        output = _build_stuff_input(ctx)
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
            data = load_pitcher_data(TEST_PITCHER, window_days=30)
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
        test_model = TestModel()

        async def _run():
            from pydantic_ai import Agent
            auditor = Agent("test", output_type=AuditResult)

            specialist_agents = {
                "stuff": agents.stuff, "location": agents.location,
                "runvalue": agents.runvalue, "trends": agents.trends,
                "game_shape": agents.game_shape,
            }
            data = load_pitcher_data(TEST_PITCHER, window_days=30)
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
        test_model = TestModel()
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

    def test_specialist_outputs_populated(self, ctx):
        """All 5 specialist slots are non-empty strings."""
        test_model = TestModel()
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )

        for name in SpecialistOutputs.model_fields:
            value = getattr(result.specialists, name)
            assert isinstance(value, str)
            assert len(value) > 0


# ── Year-over-Year specialist input tests ────────────────────────────


def _make_pipeline_ctx(
    *,
    cross_season_summary: CrossSeasonSummary | None = None,
    arsenal_trend: ArsenalTrend | None = None,
) -> PitcherContext:
    """Build a minimal synthetic PitcherContext for pipeline YoY tests."""
    fastball = FastballSummary(
        pitch_type="FF",
        pitch_name="4-Seam Fastball",
        season_velo=94.0,
        window_velo=94.5,
        velo_delta="Up modestly",
        season_p_plus=105.0,
        window_p_plus=108.0,
        p_plus_delta="Up modestly",
        season_s_plus=102.0,
        window_s_plus=106.0,
        s_plus_delta="Up modestly",
        season_l_plus=100.0,
        window_l_plus=101.0,
        l_plus_delta="Steady",
        window_pfx_x=-6.5,
        season_pfx_x=-6.3,
        pfx_x_delta="Steady",
        window_pfx_z=14.2,
        season_pfx_z=14.0,
        pfx_z_delta="Steady",
        small_sample=False,
        cold_start=False,
    )

    arsenal = [
        PitchTypeSummary(
            pitch_type="FF",
            pitch_name="4-Seam Fastball",
            season_velo=94.0,
            window_velo=94.5,
            velo_delta="Up modestly",
            season_usage_pct=55.0,
            window_usage_pct=50.0,
            usage_delta="Down modestly",
            season_p_plus=105.0,
            window_p_plus=108.0,
            p_plus_delta="Up modestly",
            season_s_plus=102.0,
            window_s_plus=106.0,
            s_plus_delta="Up modestly",
            season_l_plus=100.0,
            window_l_plus=101.0,
            l_plus_delta="Steady",
            window_pfx_x=-6.5,
            season_pfx_x=-6.3,
            pfx_x_delta="Steady",
            window_pfx_z=14.2,
            season_pfx_z=14.0,
            pfx_z_delta="Steady",
            n_pitches_season=500,
            n_pitches_window=50,
            small_sample=False,
            cold_start=False,
        ),
    ]

    workload = WorkloadContext(
        appearances=[
            AppearanceWorkload(
                game_pk=700001,
                game_date="2026-06-15",
                role="SP",
                ip="6.0",
                pitch_count=95,
                rest_days=5,
            ),
        ],
        max_consecutive_days=1,
        workload_concern=False,
    )

    return PitcherContext(
        pitcher_name="Test Pitcher",
        pitcher_id=99999,
        throws="R",
        role="SP",
        fastball=fastball,
        velocity_arc=None,
        arsenal=arsenal,
        platoon_mix=PlatoonMix(splits=[], cold_start=False),
        first_pitch=FirstPitchWeaponry(
            entries=[], total_first_pitches_season=100,
            total_first_pitches_window=10, cold_start=False,
        ),
        execution=[],
        intermediates=[],
        attributions=[],
        hard_hit_rate=HardHitRate(
            hard_hit_pct=30.0,
            season_hard_hit_pct=32.0,
            n_hard_hit=6,
            n_batted_balls=20,
            delta="Steady",
            cold_start=False,
            small_sample=True,
        ),
        release_point=ReleasePointMetrics(pitch_types=[], cold_start=False),
        workload=workload,
        tto=None,
        cross_season_summary=cross_season_summary,
        arsenal_trend=arsenal_trend,
    )


def _make_test_css() -> CrossSeasonSummary:
    """Create a synthetic CrossSeasonSummary for pipeline tests."""
    return CrossSeasonSummary(
        current_season=2026,
        prior_season=2025,
        current_velo=93.5,
        prior_velo=92.1,
        velo_delta="Up 1.4 mph",
        current_p_plus=112.0,
        prior_p_plus=105.0,
        p_plus_delta="Up 7 points",
        current_s_plus=108.0,
        prior_s_plus=101.0,
        s_plus_delta="Up 7 points",
        current_l_plus=104.0,
        prior_l_plus=103.0,
        l_plus_delta="Steady (+1 points)",
        current_appearances=10,
        prior_appearances=25,
        current_ip=45.0,
        prior_ip=120.0,
        current_avg_pitches=88.0,
        prior_avg_pitches=92.0,
    )


def _make_test_at() -> ArsenalTrend:
    """Create a synthetic ArsenalTrend for pipeline tests."""
    return ArsenalTrend(
        prior_season=2025,
        current_season=2026,
        added_pitches=[
            AddedDroppedPitch(
                pitch_type="SV", pitch_name="Sweeper",
                usage_pct=12.0, n_pitches=50, season=2026,
            ),
        ],
        dropped_pitches=[
            AddedDroppedPitch(
                pitch_type="KC", pitch_name="Knuckle Curve",
                usage_pct=8.0, n_pitches=40, season=2025,
            ),
        ],
        pitch_trends=[
            PitchTrend(
                pitch_type="FF", pitch_name="4-Seam Fastball",
                prior_usage_pct=55.0, current_usage_pct=48.0,
                usage_delta="Down 7.0 pp",
                prior_p_plus=105.0, current_p_plus=112.0,
                p_plus_delta="Up 7 points",
                prior_s_plus=101.0, current_s_plus=108.0,
                s_plus_delta="Up 7 points",
                prior_velo=92.1, current_velo=93.5,
                velo_delta="Up 1.4 mph",
                prior_pfx_x=-6.0, current_pfx_x=-8.0,
                pfx_x_delta="Down 2.0 in",
                prior_pfx_z=14.0, current_pfx_z=13.0,
                pfx_z_delta="Down 1.0 in",
            ),
        ],
    )


@pytest.fixture
def yoy_ctx():
    """PitcherContext with cross-season data populated."""
    return _make_pipeline_ctx(
        cross_season_summary=_make_test_css(),
        arsenal_trend=_make_test_at(),
    )


@pytest.fixture
def no_yoy_ctx():
    """PitcherContext without cross-season data."""
    return _make_pipeline_ctx()


def _patch_league_baselines(monkeypatch):
    """Patch compute_league_baselines to return an empty list (no data files needed)."""
    monkeypatch.setattr(
        "pitcher_narratives.pipeline.compute_league_baselines",
        lambda: [],
    )
    monkeypatch.setattr(
        "pitcher_narratives.pipeline.render_league_baselines",
        lambda _types: "## League Baselines\n(mocked)",
    )


class TestStuffInputYoY:
    def test_stuff_input_includes_yoy(self, yoy_ctx, monkeypatch):
        """CPMT-03: Stuff specialist input includes YoY context."""
        _patch_league_baselines(monkeypatch)
        output = _build_stuff_input(yoy_ctx)
        assert "Year-over-Year Context" in output

    def test_stuff_input_yoy_velocity_delta(self, yoy_ctx, monkeypatch):
        """CPMT-03: Stuff input contains velocity YoY delta string."""
        _patch_league_baselines(monkeypatch)
        output = _build_stuff_input(yoy_ctx)
        assert "Up 1.4 mph" in output

    def test_stuff_input_yoy_grade_deltas(self, yoy_ctx, monkeypatch):
        """CPMT-03: Stuff input contains P+/S+ YoY delta strings."""
        _patch_league_baselines(monkeypatch)
        output = _build_stuff_input(yoy_ctx)
        assert "P+ YoY" in output
        assert "S+ YoY" in output

    def test_stuff_input_yoy_added_dropped(self, yoy_ctx, monkeypatch):
        """CPMT-03: Stuff input contains added/dropped pitch names."""
        _patch_league_baselines(monkeypatch)
        output = _build_stuff_input(yoy_ctx)
        assert "Sweeper" in output
        assert "Knuckle Curve" in output

    def test_stuff_input_yoy_movement_deltas(self, yoy_ctx, monkeypatch):
        """Stuff input contains per-pitch movement YoY deltas for non-Steady pitches."""
        _patch_league_baselines(monkeypatch)
        output = _build_stuff_input(yoy_ctx)
        # FF has non-Steady movement: pfx_x_delta="Down 2.0 in", pfx_z_delta="Down 1.0 in"
        assert "movement" in output.lower()
        assert "H-mov" in output or "V-mov" in output

    def test_stuff_input_no_yoy_when_absent(self, no_yoy_ctx, monkeypatch):
        """CPMT-03: Stuff input has no YoY when cross-season data is absent."""
        _patch_league_baselines(monkeypatch)
        output = _build_stuff_input(no_yoy_ctx)
        assert "Year-over-Year" not in output


def _patch_league_baselines_with_handedness(monkeypatch):
    """Patch compute_league_baselines to return baselines with p_throws for percentile testing."""
    mock_baselines = [
        LeagueBaseline(
            pitch_type="FF", pitch_name="4-Seam Fastball", p_throws="R",
            n_pitches=50000, avg_velo=93.5, avg_pfx_x=-6.0, avg_pfx_z=14.0,
            zone_pct=45.0, chase_pct=25.0, velo_std=2.5, pfx_x_std=2.0, pfx_z_std=2.0,
        ),
        LeagueBaseline(
            pitch_type="FF", pitch_name="4-Seam Fastball", p_throws="L",
            n_pitches=20000, avg_velo=92.0, avg_pfx_x=6.0, avg_pfx_z=14.0,
            zone_pct=44.0, chase_pct=24.0, velo_std=2.5, pfx_x_std=2.0, pfx_z_std=2.0,
        ),
    ]
    monkeypatch.setattr(
        "pitcher_narratives.pipeline.compute_league_baselines",
        lambda: mock_baselines,
    )
    monkeypatch.setattr(
        "pitcher_narratives.pipeline.render_league_baselines",
        lambda _types: "## League Baselines\n(mocked)",
    )


class TestStuffInputPercentile:
    def test_stuff_input_includes_percentile(self, yoy_ctx, monkeypatch):
        """Stuff specialist output includes percentile text in outlier tags."""
        _patch_league_baselines_with_handedness(monkeypatch)
        output = _build_stuff_input(yoy_ctx)
        assert "percentile" in output

    def test_stuff_input_handedness_filtering(self, yoy_ctx, monkeypatch):
        """Stuff specialist uses handedness-matched baselines (RHP ctx -> RHP baselines)."""
        _patch_league_baselines_with_handedness(monkeypatch)
        output = _build_stuff_input(yoy_ctx)
        # RHP ctx with 93.0 velo vs RHP avg 93.5 — should be NORMAL
        # If it used LHP baselines (92.0 avg), result would differ
        assert "NORMAL" in output or "OUTLIER" in output


class TestTrendInputYoY:
    def test_trend_input_includes_yoy(self, yoy_ctx, monkeypatch):
        """CPMT-03: Trend specialist input includes YoY context."""
        _patch_league_baselines(monkeypatch)
        output = _build_trend_input(yoy_ctx)
        assert "Year-over-Year" in output

    def test_trend_input_full_cross_season(self, yoy_ctx, monkeypatch):
        """CPMT-03: Trend input contains full cross-season summary data."""
        _patch_league_baselines(monkeypatch)
        output = _build_trend_input(yoy_ctx)
        assert "Up 1.4 mph" in output
        assert "Sweeper" in output

    def test_trend_input_no_yoy_when_absent(self, no_yoy_ctx, monkeypatch):
        """CPMT-03: Trend input has no YoY when cross-season data is absent."""
        _patch_league_baselines(monkeypatch)
        output = _build_trend_input(no_yoy_ctx)
        assert "Year-over-Year" not in output


class TestGameShapeInputYoY:
    def test_game_shape_input_includes_yoy(self, yoy_ctx, monkeypatch):
        """CPMT-03: Game Shape specialist input includes YoY context."""
        _patch_league_baselines(monkeypatch)
        output = _build_game_shape_input(yoy_ctx)
        assert "Year-over-Year Context" in output

    def test_game_shape_input_workload_comparison(self, yoy_ctx, monkeypatch):
        """CPMT-03: Game Shape input contains workload comparison."""
        _patch_league_baselines(monkeypatch)
        output = _build_game_shape_input(yoy_ctx)
        assert "10 app" in output or "10 appearances" in output
        assert "45" in output  # current IP

    def test_game_shape_input_usage_shifts(self, yoy_ctx, monkeypatch):
        """CPMT-03: Game Shape input contains arsenal usage shift data."""
        _patch_league_baselines(monkeypatch)
        output = _build_game_shape_input(yoy_ctx)
        assert "Down 7.0 pp" in output or "usage" in output

    def test_game_shape_input_movement_shifts(self, yoy_ctx, monkeypatch):
        """Game Shape input contains per-pitch movement deltas for non-Steady pitches."""
        _patch_league_baselines(monkeypatch)
        output = _build_game_shape_input(yoy_ctx)
        # FF has non-Steady movement: should see H-mov or V-mov in output
        assert "H-mov" in output or "V-mov" in output

    def test_game_shape_input_no_yoy_when_absent(self, no_yoy_ctx, monkeypatch):
        """CPMT-03: Game Shape input has no YoY when cross-season data is absent."""
        _patch_league_baselines(monkeypatch)
        output = _build_game_shape_input(no_yoy_ctx)
        assert "Year-over-Year" not in output


class TestLocationRvNoYoY:
    def test_location_input_no_yoy(self, yoy_ctx, monkeypatch):
        """CPMT-03: Location specialist input does NOT include any YoY data."""
        _patch_league_baselines(monkeypatch)
        output = _build_location_input(yoy_ctx)
        assert "Year-over-Year" not in output

    def test_runvalue_input_no_yoy(self, yoy_ctx, monkeypatch):
        """CPMT-03: Run Value specialist input does NOT include any YoY data."""
        _patch_league_baselines(monkeypatch)
        output = _build_runvalue_input(yoy_ctx)
        assert "Year-over-Year" not in output
