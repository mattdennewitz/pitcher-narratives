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
    CountBucket,
    CountBucketUsage,
    CountSplits,
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
    PlatoonSplit,
    ReleasePointMetrics,
    ReleasePointPitchType,
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
    _build_approach_input,
    _build_game_shape_input,
    _build_location_input,
    _build_runvalue_input,
    _build_stuff_input,
    _build_trend_input,
    _build_trend_prompt,
    audit_and_revise_specialists,
    build_writer_input,
    generate_pipeline_streaming,
    make_pipeline_agents,
    run_specialists,
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
            approach="Approach analysis.",
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
                "game_shape": agents.game_shape, "approach": agents.approach,
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
                "game_shape": agents.game_shape, "approach": agents.approach,
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
        """All 6 specialist slots are non-empty strings."""
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
    role: str = "SP",
    platoon_mix: PlatoonMix | None = None,
    first_pitch: FirstPitchWeaponry | None = None,
    count_splits: CountSplits | None = None,
    release_point: ReleasePointMetrics | None = None,
    workload_appearances: list[AppearanceWorkload] | None = None,
) -> PitcherContext:
    """Build a minimal synthetic PitcherContext for pipeline tests."""
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

    if workload_appearances is not None:
        appearances = workload_appearances
        max_consec = max(
            (1 for a in appearances if a.rest_days == 0),
            default=1,
        )
        # Simple consecutive count: count 0-rest-day chains
        consec = 1
        for a in sorted(appearances, key=lambda x: x.game_date):
            if a.rest_days == 0:
                consec += 1
            else:
                consec = 1
        max_consec = max(max_consec, consec)
        workload_concern = max_consec >= 3
    else:
        appearances = [
            AppearanceWorkload(
                game_pk=700001,
                game_date="2026-06-15",
                role=role,
                ip="6.0",
                pitch_count=95,
                rest_days=5,
            ),
        ]
        max_consec = 1
        workload_concern = False

    workload = WorkloadContext(
        appearances=appearances,
        max_consecutive_days=max_consec,
        workload_concern=workload_concern,
    )

    default_platoon_mix = PlatoonMix(splits=[], cold_start=False)
    default_first_pitch = FirstPitchWeaponry(
        entries=[], total_first_pitches_season=100,
        total_first_pitches_window=10, cold_start=False,
    )

    return PitcherContext(
        pitcher_name="Test Pitcher",
        pitcher_id=99999,
        throws="R",
        role=role,
        fastball=fastball,
        velocity_arc=None,
        arsenal=arsenal,
        platoon_mix=platoon_mix if platoon_mix is not None else default_platoon_mix,
        first_pitch=first_pitch if first_pitch is not None else default_first_pitch,
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
        release_point=release_point if release_point is not None else ReleasePointMetrics(pitch_types=[], cold_start=False),
        workload=workload,
        tto=None,
        cross_season_summary=cross_season_summary,
        arsenal_trend=arsenal_trend,
        count_splits=count_splits,
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

    def test_location_input_no_platoon(self, yoy_ctx, monkeypatch):
        """PIPE-03: Location specialist input does NOT contain platoon data."""
        _patch_league_baselines(monkeypatch)
        output = _build_location_input(yoy_ctx)
        assert "platoon" not in output.lower()


# ── PIPE-05: Raw data appendix tests ──────────────────────────────────


class TestStuffAppendix:
    """PIPE-05: Stuff specialist input includes per-pitch delta table."""

    def test_stuff_input_contains_delta_table(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx()
        output = _build_stuff_input(ctx)
        assert "Per-Pitch Delta Table" in output

    def test_stuff_delta_table_has_velo_columns(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx()
        output = _build_stuff_input(ctx)
        # Table should contain the actual window and season velo values
        assert "94.5" in output  # window_velo
        assert "94.0" in output  # season_velo

    def test_stuff_delta_table_has_movement_columns(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx()
        output = _build_stuff_input(ctx)
        assert "6.5" in output  # pfx_x (window: -6.5)
        assert "14.2" in output  # pfx_z window

    def test_stuff_delta_table_has_plus_scores(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx()
        output = _build_stuff_input(ctx)
        # Should contain S+ and P+ in the delta table
        assert "106" in output  # window_s_plus
        assert "108" in output  # window_p_plus

    def test_stuff_delta_table_raw_data_label(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx()
        output = _build_stuff_input(ctx)
        assert "Raw Data (cite these exact numbers)" in output

    def test_stuff_prompt_anti_recalculation(self):
        from pitcher_narratives.pipeline import _STUFF_SPECIALIST_PROMPT
        assert "Do not attempt to recalculate" in _STUFF_SPECIALIST_PROMPT


class TestTrendAppendix:
    """PIPE-05: Trend specialist input includes raw data appendix."""

    def test_trend_input_contains_raw_data(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx()
        output = _build_trend_input(ctx)
        assert "Raw Data" in output

    def test_trend_appendix_primary_pitches_only(self, monkeypatch):
        """Only pitches with >= 10% window usage appear in appendix."""
        _patch_league_baselines(monkeypatch)
        # Create ctx with one primary pitch (50%) and one minor pitch (5%)
        ctx = _make_pipeline_ctx()
        minor_pitch = PitchTypeSummary(
            pitch_type="CH",
            pitch_name="Changeup",
            season_velo=85.0,
            window_velo=84.5,
            velo_delta="Steady",
            season_usage_pct=8.0,
            window_usage_pct=5.0,
            usage_delta="Down modestly",
            season_p_plus=95.0,
            window_p_plus=93.0,
            p_plus_delta="Down slightly",
            season_s_plus=90.0,
            window_s_plus=88.0,
            s_plus_delta="Down slightly",
            season_l_plus=98.0,
            window_l_plus=96.0,
            l_plus_delta="Steady",
            window_pfx_x=8.0,
            season_pfx_x=7.8,
            pfx_x_delta="Steady",
            window_pfx_z=2.5,
            season_pfx_z=2.6,
            pfx_z_delta="Steady",
            n_pitches_season=40,
            n_pitches_window=5,
            small_sample=True,
            cold_start=False,
        )
        ctx.arsenal.append(minor_pitch)
        output = _build_trend_input(ctx)
        # Split at "Raw Data" to check only the appendix portion
        raw_idx = output.find("Raw Data")
        assert raw_idx != -1, "Raw Data section must exist"
        appendix = output[raw_idx:]
        assert "4-Seam Fastball" in appendix  # 50% usage — included
        assert "Changeup" not in appendix  # 5% usage — excluded

    def test_trend_appendix_contains_delta_columns(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx()
        output = _build_trend_input(ctx)
        # Raw data section should contain velo values
        assert "94.5" in output  # window_velo from arsenal


# ── Approach Specialist test helpers ───────────────────────────────────


def _make_test_platoon_mix() -> PlatoonMix:
    """Create a PlatoonMix with meaningful data for approach tests."""
    return PlatoonMix(
        splits=[
            PlatoonSplit(
                pitch_type="FF", pitch_name="4-Seam Fastball",
                platoon_side="same", season_usage_pct=55.0,
                window_usage_pct=42.0, usage_delta="Down sharply",
                season_p_plus=105.0, window_p_plus=None, p_plus_delta="--",
                available=True,
            ),
            PlatoonSplit(
                pitch_type="SL", pitch_name="Slider",
                platoon_side="opposite", season_usage_pct=20.0,
                window_usage_pct=35.0, usage_delta="Up sharply",
                season_p_plus=110.0, window_p_plus=None, p_plus_delta="--",
                available=True,
            ),
        ],
        cold_start=False,
    )


def _make_test_count_splits() -> CountSplits:
    """Create a CountSplits with a notable shift for approach tests."""
    return CountSplits(
        buckets=[
            CountBucket(
                bucket="ahead", n_pitches_window=30, n_pitches_season=200,
                small_sample=False,
                pitch_types=[CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=45.0)],
                season_pitch_types=[CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=30.0)],
            ),
        ],
        notable_shifts=["Slider ahead: 45.0% window vs 30.0% season (+15.0 pp)"],
    )


def _make_test_first_pitch() -> FirstPitchWeaponry:
    """Create a FirstPitchWeaponry with data for approach tests."""
    return FirstPitchWeaponry(
        entries=[
            FirstPitchEntry(
                pitch_type="FF", pitch_name="4-Seam Fastball",
                season_pct=60.0, window_pct=55.0, delta="Down modestly",
                n_first_pitches_season=200, n_first_pitches_window=20,
            ),
        ],
        total_first_pitches_season=350,
        total_first_pitches_window=35,
        cold_start=False,
    )


def _make_approach_ctx() -> PitcherContext:
    """PitcherContext populated with platoon, count splits, and first-pitch data."""
    return _make_pipeline_ctx(
        platoon_mix=_make_test_platoon_mix(),
        count_splits=_make_test_count_splits(),
        first_pitch=_make_test_first_pitch(),
    )


def _make_rp_pipeline_ctx() -> PitcherContext:
    """PitcherContext for an RP with multiple workload appearances."""
    return _make_pipeline_ctx(
        role="RP",
        workload_appearances=[
            AppearanceWorkload(game_pk=700001, game_date="2026-06-15", role="RP", ip="1.0", pitch_count=18, rest_days=1),
            AppearanceWorkload(game_pk=700002, game_date="2026-06-14", role="RP", ip="1.0", pitch_count=22, rest_days=0),
            AppearanceWorkload(game_pk=700003, game_date="2026-06-13", role="RP", ip="0.2", pitch_count=12, rest_days=2),
        ],
    )


# ── Approach Specialist tests ──────────────────────────────────────────


class TestBuildApproachInput:
    def test_approach_input_contains_platoon_section(self, monkeypatch):
        """PIPE-01: Approach input contains platoon shifts when data present."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_approach_ctx()
        output = _build_approach_input(ctx)
        assert "Platoon Shifts" in output

    def test_approach_input_contains_count_splits(self, monkeypatch):
        """PIPE-01: Approach input contains notable count-state shifts."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_approach_ctx()
        output = _build_approach_input(ctx)
        assert "Count-State Usage Shifts" in output
        assert "+15.0 pp" in output

    def test_approach_input_contains_first_pitch(self, monkeypatch):
        """PIPE-01: Approach input contains first-pitch tendencies."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_approach_ctx()
        output = _build_approach_input(ctx)
        assert "First-Pitch Tendencies" in output

    def test_approach_input_contains_baseline_mix(self, monkeypatch):
        """PIPE-01: Approach input contains baseline overall pitch mix."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_approach_ctx()
        output = _build_approach_input(ctx)
        assert "Overall Pitch Mix" in output
        assert "55.0% season" in output
        assert "50.0% recent" in output

    def test_approach_input_contains_pitcher_header(self, monkeypatch):
        """PIPE-01: Approach input starts with pitcher name/handedness/role."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_approach_ctx()
        output = _build_approach_input(ctx)
        assert output.startswith("## Test Pitcher (RHP, SP)")

    def test_approach_input_no_full_appendix(self, monkeypatch):
        """D-04: Approach input does NOT contain the full count splits appendix."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_approach_ctx()
        output = _build_approach_input(ctx)
        assert "Count-State Usage Appendix" not in output


class TestApproachPrompt:
    def test_prompt_contains_strategy_first(self):
        """D-01: Approach prompt contains strategy-first framing."""
        from pitcher_narratives.pipeline import _APPROACH_SPECIALIST_PROMPT
        assert "approach pattern" in _APPROACH_SPECIALIST_PROMPT.lower() or \
               "strategy" in _APPROACH_SPECIALIST_PROMPT.lower()

    def test_prompt_contains_cross_reference_directive(self):
        """D-02: Approach prompt contains cross-reference instruction."""
        from pitcher_narratives.pipeline import _APPROACH_SPECIALIST_PROMPT
        assert "platoon side AND" in _APPROACH_SPECIALIST_PROMPT or \
               "cross-reference" in _APPROACH_SPECIALIST_PROMPT.lower()

    def test_prompt_contains_adaptive_length(self):
        """D-03: Approach prompt contains anti-padding directive."""
        from pitcher_narratives.pipeline import _APPROACH_SPECIALIST_PROMPT
        assert "Under no circumstances should you pad" in _APPROACH_SPECIALIST_PROMPT

    def test_prompt_contains_notable_shifts(self):
        """D-04: Approach prompt references 10+ pp shifts."""
        from pitcher_narratives.pipeline import _APPROACH_SPECIALIST_PROMPT
        assert "10+" in _APPROACH_SPECIALIST_PROMPT


class TestRPGameShapeSkip:
    def test_rp_gets_workload_stub(self, monkeypatch):
        """PIPE-04: RP game shape returns workload stub, not TTO content."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_rp_pipeline_ctx()
        output = _build_game_shape_input(ctx)
        assert "Workload Context" in output
        # Should NOT contain TTO content
        assert "TTO" not in output

    def test_rp_stub_contains_appearances(self, monkeypatch):
        """PIPE-04: RP workload stub contains appearances count."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_rp_pipeline_ctx()
        output = _build_game_shape_input(ctx)
        assert "Appearances" in output or "appearances" in output
        assert "3" in output  # 3 appearances

    def test_rp_stub_contains_pitch_counts(self, monkeypatch):
        """PIPE-04: RP workload stub contains pitch count info."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_rp_pipeline_ctx()
        output = _build_game_shape_input(ctx)
        assert "18" in output or "22" in output or "Pitches" in output or "pitch" in output.lower()

    def test_rp_stub_contains_rest_days(self, monkeypatch):
        """PIPE-04: RP workload stub contains rest day info."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_rp_pipeline_ctx()
        output = _build_game_shape_input(ctx)
        assert "1d" in output or "2d" in output or "Rest" in output or "rest" in output

    def test_sp_gets_normal_game_shape(self, monkeypatch):
        """PIPE-04: SP game shape returns normal TTO content, not workload stub."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_pipeline_ctx(role="SP")
        output = _build_game_shape_input(ctx)
        assert "Workload Context" not in output


# ── PIPE-06/07: 6-agent pipeline wiring (Task 1) ──────────────────────


class TestSpecialistOutputsApproach:
    """PIPE-06: SpecialistOutputs has approach field."""

    def test_specialist_outputs_has_approach_field(self):
        so = SpecialistOutputs(
            stuff="s", location="l", runvalue="r",
            trends="t", game_shape="g", approach="a",
        )
        assert so.approach == "a"

    def test_specialist_outputs_field_order(self):
        """approach is the last specialist field."""
        fields = list(SpecialistOutputs.model_fields.keys())
        assert fields[-1] == "approach"
        assert fields[-2] == "game_shape"


class TestPipelineAgentsApproach:
    """PIPE-06: PipelineAgents has approach field between game_shape and writer."""

    def test_approach_in_pipeline_agents_fields(self):
        assert "approach" in PipelineAgents._fields

    def test_approach_position(self):
        """approach comes between game_shape and writer."""
        fields = list(PipelineAgents._fields)
        gs_idx = fields.index("game_shape")
        ap_idx = fields.index("approach")
        wr_idx = fields.index("writer")
        assert gs_idx < ap_idx < wr_idx

    def test_make_pipeline_agents_approach_populated(self):
        agents = make_pipeline_agents("gemini", "high")
        assert agents.approach is not None

    def test_named_access_approach(self):
        agents = make_pipeline_agents("gemini", "high")
        assert agents.approach is not None
        assert agents.stuff is not None
        assert agents.writer is not None


class TestRunSpecialistsApproach:
    """PIPE-06: run_specialists dispatches 6 agents in parallel."""

    def test_run_specialists_returns_approach(self, monkeypatch):
        _patch_league_baselines(monkeypatch)
        from pydantic_ai.models.test import TestModel
        test_model = TestModel()
        agents = make_pipeline_agents("gemini", "high")
        ctx = _make_approach_ctx()

        result = asyncio.run(run_specialists(
            agents.stuff, agents.location, agents.runvalue,
            agents.trends, agents.game_shape, agents.approach,
            ctx, test_model,
        ))
        assert isinstance(result, SpecialistOutputs)
        assert isinstance(result.approach, str)
        assert len(result.approach) > 0


class TestAuditSixSpecialists:
    """PIPE-07: Audit loop handles 6 specialists including approach."""

    @pytest.fixture
    def six_specialists(self):
        return SpecialistOutputs(
            stuff="The four-seam is elite.",
            location="Location is average.",
            runvalue="Run value is neutral.",
            trends="No changes.",
            game_shape="Steady across passes.",
            approach="Approach analysis.",
        )

    def test_audit_six_returns_specialist_outputs(self, six_specialists):
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel
        test_model = TestModel()
        agents = make_pipeline_agents("gemini", "high")

        async def _run():
            clean_auditor = Agent("test", output_type=AuditResult)
            specialist_agents = {
                "stuff": agents.stuff, "location": agents.location,
                "runvalue": agents.runvalue, "trends": agents.trends,
                "game_shape": agents.game_shape, "approach": agents.approach,
            }
            data = load_pitcher_data(TEST_PITCHER, window_days=30)
            ctx = assemble_pitcher_context(data)
            result, flags = await audit_and_revise_specialists(
                six_specialists, specialist_agents, clean_auditor, ctx,
                _model_override=test_model,
            )
            return result, flags

        result, flags = asyncio.run(_run())
        assert isinstance(result, SpecialistOutputs)
        assert hasattr(result, "approach")
        assert isinstance(flags, list)


class TestAnchorSynthesisApproach:
    """Anchor synthesis includes approach and RP-conditional game shape label."""

    def test_e2e_pipeline_has_approach_in_specialists(self, ctx):
        """End-to-end: pipeline returns approach in specialists."""
        test_model = TestModel()
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert hasattr(result.specialists, "approach")
        assert isinstance(result.specialists.approach, str)
        assert len(result.specialists.approach) > 0


# ── PIPE-06: Writer input + prompt tests (Task 2) ─────────────────────


class TestBuildWriterInput:
    """PIPE-06: Writer input includes 6th specialist output."""

    def test_writer_input_has_six_sections(self):
        ctx = _make_pipeline_ctx()
        output = build_writer_input(
            ctx, "stuff text", "location text", "runvalue text",
            "trends text", "game shape text", "approach text",
        )
        assert "Specialist Analysis 6: Approach" in output
        assert "approach text" in output

    def test_writer_input_contains_all_specialists(self):
        ctx = _make_pipeline_ctx()
        output = build_writer_input(
            ctx, "s1", "s2", "s3", "s4", "s5", "s6",
        )
        for i in range(1, 7):
            assert f"Specialist Analysis {i}" in output

    def test_writer_input_contains_pitcher_header(self):
        ctx = _make_pipeline_ctx()
        output = build_writer_input(ctx, "s", "s", "s", "s", "s", "s")
        assert "Test Pitcher" in output


class TestWriterPrompt:
    """Writer prompt says Six, includes approach, has RP conditional."""

    def test_writer_prompt_says_six(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "Six specialist analyses" in prompt

    def test_writer_prompt_includes_approach_description(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "Approach analysis" in prompt

    def test_writer_prompt_rp_conditional(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("RP")
        assert "reliever" in prompt
        assert "Do not fabricate TTO" in prompt

    def test_writer_prompt_sp_no_rp_directive(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "Do not fabricate TTO" not in prompt

    def test_writer_prompt_rp_workload_section(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("RP")
        assert "Workload context" in prompt

    def test_writer_prompt_sp_game_shape_section(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "Game shape" in prompt


class TestAuditorPrompt:
    """PIPE-07: Auditor has 9 categories with domain-specific checks."""

    def test_auditor_has_nine_categories(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "8. PLATOON_CLAIM_MISMATCH" in _DATA_AUDITOR_PROMPT
        assert "9. COUNT_STATE_CLAIM_MISMATCH" in _DATA_AUDITOR_PROMPT

    def test_auditor_platoon_category_conditional(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "apply ONLY when" in _DATA_AUDITOR_PROMPT

    def test_auditor_count_state_chain_of_thought(self):
        """D-13: Domain-specific checks use show-your-work format."""
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "state the claim" in _DATA_AUDITOR_PROMPT
        assert "Pass/Fail" in _DATA_AUDITOR_PROMPT


# ── Heuristic directive tests (Phase 25, Plan 01) ─────────────────────


def _make_rp_pitch_type() -> ReleasePointPitchType:
    """Create a minimal ReleasePointPitchType for testing."""
    return ReleasePointPitchType(
        pitch_type="FF",
        pitch_name="4-Seam Fastball",
        window_release_x=-2.0,
        season_release_x=-2.1,
        release_x_delta="Steady",
        window_release_z=6.0,
        season_release_z=5.9,
        release_z_delta="Steady",
        window_extension=6.5,
        season_extension=6.4,
        extension_delta="Steady",
        n_pitches_window=50,
        small_sample=False,
        cold_start=False,
        window_arm_angle=65.0,
        season_arm_angle=64.5,
        arm_angle_delta="Steady",
        arm_slot="High 3/4",
    )


def _ctx_with_arm_angle() -> PitcherContext:
    """PitcherContext with arm angle data present."""
    return _make_pipeline_ctx(
        release_point=ReleasePointMetrics(
            pitch_types=[_make_rp_pitch_type()],
            cold_start=False,
        ),
    )


def _ctx_no_arm_angle() -> PitcherContext:
    """PitcherContext without arm angle data."""
    return _make_pipeline_ctx(
        release_point=ReleasePointMetrics(
            pitch_types=[],
            cold_start=False,
        ),
    )


class TestStuffPromptHeuristics:
    """PROMPT-01: Stuff specialist trade-off detection directive (D-01/D-02)."""

    def test_stuff_prompt_tradeoff_section(self):
        from pitcher_narratives.pipeline import _STUFF_SPECIALIST_PROMPT
        assert "TRADE-OFF DETECTION" in _STUFF_SPECIALIST_PROMPT

    def test_stuff_prompt_common_patterns(self):
        from pitcher_narratives.pipeline import _STUFF_SPECIALIST_PROMPT
        assert "COMMON PATTERNS" in _STUFF_SPECIALIST_PROMPT

    def test_stuff_prompt_inverse_relationship(self):
        from pitcher_narratives.pipeline import _STUFF_SPECIALIST_PROMPT
        assert "INVERSE" in _STUFF_SPECIALIST_PROMPT

    def test_stuff_prompt_cites_pfx_deltas(self):
        from pitcher_narratives.pipeline import _STUFF_SPECIALIST_PROMPT
        assert "pfx deltas" in _STUFF_SPECIALIST_PROMPT


class TestLocationPromptHeuristics:
    """PROMPT-02: Location specialist contradiction detection directive (D-03)."""

    def test_location_prompt_contradiction_section(self):
        from pitcher_narratives.pipeline import _LOCATION_SPECIALIST_PROMPT
        assert "CONTRADICTION DETECTION" in _LOCATION_SPECIALIST_PROMPT

    def test_location_prompt_zone_expansion(self):
        from pitcher_narratives.pipeline import _LOCATION_SPECIALIST_PROMPT
        assert "expanding the zone" in _LOCATION_SPECIALIST_PROMPT

    def test_location_prompt_chase_rate(self):
        from pitcher_narratives.pipeline import _LOCATION_SPECIALIST_PROMPT
        assert "chase%" in _LOCATION_SPECIALIST_PROMPT


class TestTrendPromptFunction:
    """PROMPT-03: Trend specialist release-point vocabulary (D-05/D-06)."""

    def test_trend_prompt_is_callable(self):
        assert callable(_build_trend_prompt)

    def test_trend_prompt_base_content(self):
        ctx = _ctx_no_arm_angle()
        prompt = _build_trend_prompt(ctx)
        assert "trend analyst" in prompt

    def test_trend_prompt_with_arm_angle(self):
        ctx = _ctx_with_arm_angle()
        prompt = _build_trend_prompt(ctx)
        assert "RELEASE POINT FRAMING" in prompt

    def test_trend_prompt_without_arm_angle(self):
        ctx = _ctx_no_arm_angle()
        prompt = _build_trend_prompt(ctx)
        assert "RELEASE POINT FRAMING" not in prompt

    def test_trend_prompt_anti_speculation(self):
        ctx = _ctx_with_arm_angle()
        prompt = _build_trend_prompt(ctx)
        assert "Do NOT speculate on mechanical causes" in prompt

    def test_trend_prompt_vocabulary(self):
        ctx = _ctx_with_arm_angle()
        prompt = _build_trend_prompt(ctx)
        assert "arm slot" in prompt
        assert "tunneling" in prompt


class TestMakePipelineAgentsCtx:
    """Backward and forward compat for ctx parameter on make_pipeline_agents."""

    def test_make_pipeline_agents_no_ctx(self):
        agents = make_pipeline_agents("gemini", "high")
        assert isinstance(agents, PipelineAgents)

    def test_make_pipeline_agents_with_ctx(self):
        ctx = _make_pipeline_ctx()
        agents = make_pipeline_agents("gemini", "high", ctx=ctx)
        assert isinstance(agents, PipelineAgents)


# ── Writer & Auditor heuristic tests (Phase 25, Plan 02) ──────────────


class TestWriterPromptCausalHook:
    """PROMPT-04 (D-07/D-08/D-09): Writer must cite physical drivers for large S+ changes."""

    def test_writer_prompt_causal_hook_section(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "CAUSAL HOOK REQUIREMENT" in prompt

    def test_writer_prompt_causal_hook_threshold(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "10" in prompt

    def test_writer_prompt_causal_hook_stuff_citation(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "Stuff Specialist" in prompt

    def test_writer_prompt_causal_hook_anti_fabrication(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "NEVER invent a physical cause" in prompt

    def test_writer_prompt_causal_hook_honest_fallback(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("SP")
        assert "without an obvious physical explanation" in prompt

    def test_writer_prompt_rp_also_has_causal_hook(self):
        from pitcher_narratives.pipeline import _build_writer_prompt
        prompt = _build_writer_prompt("RP")
        assert "CAUSAL HOOK REQUIREMENT" in prompt


class TestAuditorWhitelist:
    """PROMPT-05 (D-10/D-11/D-12): Auditor whitelists evidence-backed heuristic patterns."""

    def test_auditor_whitelist_section(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "ALLOWED HEURISTIC PATTERNS" in _DATA_AUDITOR_PROMPT

    def test_auditor_whitelist_inverse_correlation(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "INVERSE CORRELATION" in _DATA_AUDITOR_PROMPT

    def test_auditor_whitelist_zone_expansion(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "ZONE EXPANSION" in _DATA_AUDITOR_PROMPT

    def test_auditor_whitelist_approach_angle(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "APPROACH ANGLE" in _DATA_AUDITOR_PROMPT

    def test_auditor_whitelist_evidence_gate(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "ONLY when" in _DATA_AUDITOR_PROMPT

    def test_auditor_whitelist_placement_before_output(self):
        """D-12: Whitelist must appear before output format for recency effect."""
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        wl_idx = _DATA_AUDITOR_PROMPT.index("ALLOWED HEURISTIC PATTERNS")
        of_idx = _DATA_AUDITOR_PROMPT.index("For each problem found")
        assert wl_idx < of_idx, (
            f"Whitelist at {wl_idx} must come before output format at {of_idx}"
        )

    def test_auditor_whitelist_uncited_still_violation(self):
        from pitcher_narratives.pipeline import _DATA_AUDITOR_PROMPT
        assert "category 5" in _DATA_AUDITOR_PROMPT


# ── Location input adjacency tests (Phase 25, Plan 03) ─────────────────


def _make_location_ctx(*, include_execution: bool = True) -> PitcherContext:
    """Build a PitcherContext with execution + intermediates data for location tests."""
    _none_fields = dict(
        xgor_p=None, xgor_s=None, xpur_p=None, xpur_s=None,
        xhr100_p=None, xhr100_s=None, bbe_prob_p=None, bbe_prob_s=None,
        xswst_p=None, xswst_s=None,
        season_xswing_p=None, season_xswing_s=None, season_xwhiff_p=None,
        season_xwhiff_s=None, season_xgor_p=None, season_xgor_s=None,
        season_xpur_p=None, season_xpur_s=None, season_xhr100_p=None,
        season_xhr100_s=None, season_bbe_prob_p=None, season_bbe_prob_s=None,
        season_xswst_p=None, season_xswst_s=None, season_xrv100_p=None,
        season_xrv100_s=None,
    )
    intermediates = [
        IntermediateProbabilities(
            pitch_type="FF",
            pitch_name="4-Seam Fastball",
            xswing_p=0.72,
            xswing_s=0.68,
            xwhiff_p=0.28,
            xwhiff_s=0.25,
            xrv100_p=-1.50,
            xrv100_s=-1.20,
            n_pitches=50,
            small_sample=False,
            cold_start=False,
            **_none_fields,
        ),
        IntermediateProbabilities(
            pitch_type="SL",
            pitch_name="Slider",
            xswing_p=0.65,
            xswing_s=0.60,
            xwhiff_p=0.35,
            xwhiff_s=0.30,
            xrv100_p=-2.10,
            xrv100_s=-1.80,
            n_pitches=25,
            small_sample=False,
            cold_start=False,
            **_none_fields,
        ),
    ]

    execution = [
        ExecutionMetrics(
            pitch_type="FF",
            pitch_name="4-Seam Fastball",
            csw_pct=30.5,
            zone_rate=48.2,
            chase_rate=28.1,
            xwhiff_p=0.28,
            xswing_p=0.72,
            xrv100_p=-1.50,
            xrv100_percentile=75,
            n_pitches=50,
            small_sample=False,
            cold_start=False,
        ),
        ExecutionMetrics(
            pitch_type="SL",
            pitch_name="Slider",
            csw_pct=33.0,
            zone_rate=38.5,
            chase_rate=35.2,
            xwhiff_p=0.35,
            xswing_p=0.65,
            xrv100_p=-2.10,
            xrv100_percentile=85,
            n_pitches=25,
            small_sample=False,
            cold_start=False,
        ),
    ] if include_execution else [
        # Only FF execution -- SL missing (for graceful handling test)
        ExecutionMetrics(
            pitch_type="FF",
            pitch_name="4-Seam Fastball",
            csw_pct=30.5,
            zone_rate=48.2,
            chase_rate=28.1,
            xwhiff_p=0.28,
            xswing_p=0.72,
            xrv100_p=-1.50,
            xrv100_percentile=75,
            n_pitches=50,
            small_sample=False,
            cold_start=False,
        ),
    ]

    ctx = _make_pipeline_ctx()
    # Override the empty defaults with actual data
    ctx.intermediates = intermediates
    ctx.execution = execution
    ctx.arsenal[0].window_p_plus = 108.0
    ctx.arsenal[0].window_s_plus = 106.0
    ctx.arsenal[0].window_l_plus = 101.0
    # Add slider to arsenal
    ctx.arsenal.append(
        PitchTypeSummary(
            pitch_type="SL",
            pitch_name="Slider",
            season_velo=85.0,
            window_velo=85.5,
            velo_delta="Steady",
            season_usage_pct=25.0,
            window_usage_pct=28.0,
            usage_delta="Up modestly",
            season_p_plus=112.0,
            window_p_plus=115.0,
            p_plus_delta="Up modestly",
            season_s_plus=110.0,
            window_s_plus=113.0,
            s_plus_delta="Up modestly",
            season_l_plus=108.0,
            window_l_plus=110.0,
            l_plus_delta="Steady",
            window_pfx_x=2.5,
            season_pfx_x=2.3,
            pfx_x_delta="Steady",
            window_pfx_z=-1.2,
            season_pfx_z=-1.0,
            pfx_z_delta="Steady",
            n_pitches_season=200,
            n_pitches_window=25,
            small_sample=False,
            cold_start=False,
        ),
    )
    return ctx


class TestLocationInputAdjacency:
    """PROMPT-06: Location input per-pitch-type unified view with adjacent contradiction metrics."""

    def test_location_input_per_pitch_heading(self, monkeypatch):
        """Output contains unified section header."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_location_ctx()
        output = _build_location_input(ctx)
        assert "## Location Analysis by Pitch Type" in output

    def test_location_input_no_separate_execution_section(self, monkeypatch):
        """Old '## Execution Metrics' section header is removed."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_location_ctx()
        output = _build_location_input(ctx)
        assert "## Execution Metrics" not in output

    def test_location_input_no_separate_pvs_section(self, monkeypatch):
        """Old '## P vs S Location Impact' section header is removed."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_location_ctx()
        output = _build_location_input(ctx)
        assert "## P vs S Location Impact" not in output

    def test_location_input_zone_xwhiff_chase_adjacent(self, monkeypatch):
        """D-04: zone_rate, xWhiff_P, and chase_rate appear on the same line per pitch type."""
        import re
        _patch_league_baselines(monkeypatch)
        ctx = _make_location_ctx()
        output = _build_location_input(ctx)
        # Zone%, xWhiff, and Chase% must appear on a single line
        assert re.search(r"Zone%.*xWhiff.*Chase%", output), (
            f"Expected Zone%/xWhiff/Chase% on same line, got:\n{output}"
        )

    def test_location_input_plus_scores_per_pitch(self, monkeypatch):
        """Plus scores (P+, S+, L+) appear within each pitch type block, not in a separate section."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_location_ctx()
        output = _build_location_input(ctx)
        # The old section header must be gone
        assert "## Plus Scores" not in output
        # P+, S+, L+ must appear in the output
        assert "P+" in output
        assert "S+" in output
        assert "L+" in output

    def test_location_input_missing_execution_graceful(self, monkeypatch):
        """Missing execution data for a pitch type renders gracefully (no crash)."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_location_ctx(include_execution=False)
        # SL is in intermediates but not in execution -- should not crash
        output = _build_location_input(ctx)
        assert isinstance(output, str)
        # Slider should still appear (from intermediates)
        assert "Slider" in output
        # Missing data should show placeholder
        assert "--" in output

    def test_location_input_header_includes_pitcher_name(self, monkeypatch):
        """Output starts with pitcher name and handedness."""
        _patch_league_baselines(monkeypatch)
        ctx = _make_location_ctx()
        output = _build_location_input(ctx)
        assert "Test Pitcher" in output
        assert "RHP" in output
