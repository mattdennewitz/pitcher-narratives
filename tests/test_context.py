"""Tests for PitcherContext assembly and to_prompt() rendering."""

from datetime import date

import polars as pl
import pytest
from pydantic import BaseModel

from pitcher_narratives.context import PitcherContext, assemble_pitcher_context
from pitcher_narratives.data import PitcherData, load_pitcher_data
from pitcher_narratives.engine import (
    AddedDroppedPitch,
    AppearancePitchTrendRecord,
    AppearancePitchTrends,
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
    PitchTrend,
    PitchTypeSummary,
    PlatoonMix,
    PlatoonSplit,
    ReleasePointMetrics,
    ReleasePointPitchType,
    VelocityArc,
    WorkloadContext,
)

TEST_PITCHER = 592155  # Booser, Cam


@pytest.fixture(scope="module")
def ctx():
    """Load data once per module (read-only test data)."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    return assemble_pitcher_context(data)


def _make_synthetic_ctx(
    *,
    cross_season_summary: CrossSeasonSummary | None = None,
    arsenal_trend: ArsenalTrend | None = None,
    appearance_pitch_trends: AppearancePitchTrends | None = None,
) -> PitcherContext:
    """Build a minimal synthetic PitcherContext for YoY tests.

    Avoids needing real data files -- constructs all required fields
    with synthetic but structurally valid data.
    """
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
        first_pitch=FirstPitchWeaponry(entries=[], total_first_pitches_season=100, total_first_pitches_window=10, cold_start=False),
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
        appearance_pitch_trends=appearance_pitch_trends,
    )


def _make_cross_season_summary() -> CrossSeasonSummary:
    """Create a synthetic CrossSeasonSummary for tests."""
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


def _make_arsenal_trend() -> ArsenalTrend:
    """Create a synthetic ArsenalTrend for tests."""
    return ArsenalTrend(
        prior_season=2025,
        current_season=2026,
        added_pitches=[
            AddedDroppedPitch(
                pitch_type="SV",
                pitch_name="Sweeper",
                usage_pct=12.0,
                n_pitches=50,
                season=2026,
            ),
        ],
        dropped_pitches=[
            AddedDroppedPitch(
                pitch_type="KC",
                pitch_name="Knuckle Curve",
                usage_pct=8.0,
                n_pitches=40,
                season=2025,
            ),
        ],
        pitch_trends=[
            PitchTrend(
                pitch_type="FF",
                pitch_name="4-Seam Fastball",
                prior_usage_pct=55.0,
                current_usage_pct=48.0,
                usage_delta="Down 7.0 pp",
                prior_p_plus=105.0,
                current_p_plus=112.0,
                p_plus_delta="Up 7 points",
                prior_s_plus=101.0,
                current_s_plus=108.0,
                s_plus_delta="Up 7 points",
                prior_velo=92.1,
                current_velo=93.5,
                velo_delta="Up 1.4 mph",
                prior_pfx_x=-6.0,
                current_pfx_x=-8.0,
                pfx_x_delta="Down 2.0 in",
                prior_pfx_z=14.0,
                current_pfx_z=13.0,
                pfx_z_delta="Down 1.0 in",
            ),
            PitchTrend(
                pitch_type="SL",
                pitch_name="Slider",
                prior_usage_pct=20.0,
                current_usage_pct=22.0,
                usage_delta="Steady (+2.0 pp)",
                prior_p_plus=100.0,
                current_p_plus=101.0,
                p_plus_delta="Steady (+1 points)",
                prior_s_plus=100.0,
                current_s_plus=100.0,
                s_plus_delta="Steady (0 points)",
                prior_velo=85.0,
                current_velo=85.2,
                velo_delta="Steady (+0.2 mph)",
                prior_pfx_x=2.0,
                current_pfx_x=2.1,
                pfx_x_delta="Steady (+0.1 in)",
                prior_pfx_z=3.0,
                current_pfx_z=3.1,
                pfx_z_delta="Steady (+0.1 in)",
            ),
        ],
    )


# ── Assembly tests ────────────────────────────────────────────────────


def test_pitcher_context_assembly(ctx):
    """assemble_pitcher_context returns a PitcherContext with all sections populated."""
    assert ctx is not None
    assert ctx.pitcher_name is not None
    assert ctx.throws is not None
    assert ctx.fastball is not None or ctx.pitcher_name  # at least has name
    assert ctx.arsenal is not None
    assert ctx.execution is not None
    assert ctx.workload is not None
    assert ctx.platoon_mix is not None
    assert ctx.first_pitch is not None


def test_pitcher_context_is_pydantic(ctx):
    """PitcherContext is a Pydantic BaseModel."""
    assert isinstance(ctx, BaseModel)


def test_pitcher_context_pitcher_info(ctx):
    """PitcherContext has correct pitcher name and throws."""
    assert ctx.pitcher_name == "Booser, Cam"
    assert ctx.throws == "L"


def test_arsenal_top_4(ctx):
    """Arsenal contains at most 4 entries (token budget)."""
    assert len(ctx.arsenal) <= 4


def test_execution_present(ctx):
    """Execution is a non-empty list of execution metric entries."""
    assert isinstance(ctx.execution, list)
    assert len(ctx.execution) > 0


# ── Rendering tests ───────────────────────────────────────────────────


def test_to_prompt_returns_string(ctx):
    """to_prompt() returns a str."""
    result = ctx.to_prompt()
    assert isinstance(result, str)


def test_to_prompt_has_headers(ctx):
    """to_prompt() output contains markdown headers."""
    prompt = ctx.to_prompt()
    assert "# " in prompt
    assert "## " in prompt


def test_to_prompt_has_pitcher_name(ctx):
    """to_prompt() output contains the pitcher's name."""
    prompt = ctx.to_prompt()
    assert "Booser" in prompt


def test_to_prompt_has_fastball_section(ctx):
    """to_prompt() output contains fastball info."""
    prompt = ctx.to_prompt()
    # Should mention primary fastball or note its absence
    assert "Fastball" in prompt or "Cutter" in prompt or "fastball" in prompt


def test_to_prompt_has_arsenal_section(ctx):
    """to_prompt() output contains 'Arsenal'."""
    prompt = ctx.to_prompt()
    assert "Arsenal" in prompt


def test_to_prompt_has_execution_section(ctx):
    """to_prompt() output contains 'Execution'."""
    prompt = ctx.to_prompt()
    assert "Execution" in prompt


def test_to_prompt_has_workload_section(ctx):
    """to_prompt() output contains 'Workload' or 'Appearance'."""
    prompt = ctx.to_prompt()
    assert "Workload" in prompt or "Appearance" in prompt or "Recent" in prompt


def test_to_prompt_token_budget(ctx):
    """to_prompt() output is under 2,000 tokens at ~4 chars/token."""
    prompt = ctx.to_prompt()
    estimated_tokens = len(prompt) / 4
    assert estimated_tokens < 2000, f"Estimated {estimated_tokens:.0f} tokens, exceeds 2,000 budget"


def test_to_prompt_no_none_literals(ctx):
    """to_prompt() output does not contain the literal string 'None'."""
    prompt = ctx.to_prompt()
    assert "None" not in prompt, f"Found 'None' literal in prompt output:\n{prompt}"


# ── Hard-hit rate in context ──────────────────────────────────────────


def test_hard_hit_rate_in_context(ctx):
    """assemble_pitcher_context has a non-None hard_hit_rate field of type HardHitRate."""
    assert ctx.hard_hit_rate is not None
    assert isinstance(ctx.hard_hit_rate, HardHitRate)


def test_to_prompt_has_contact_quality(ctx):
    """to_prompt() output contains 'Contact Quality' or 'Hard-hit'."""
    prompt = ctx.to_prompt()
    assert "Contact Quality" in prompt or "Hard-hit" in prompt


# ── Release Point in context ─────────────────────────────────────────


def test_release_point_in_context(ctx):
    """assemble_pitcher_context has a non-None release_point field of type ReleasePointMetrics."""
    assert ctx.release_point is not None
    assert isinstance(ctx.release_point, ReleasePointMetrics)


def test_to_prompt_has_release_point(ctx):
    """to_prompt() output contains 'Release Point' section header."""
    prompt = ctx.to_prompt()
    assert "Release Point" in prompt


# ── Intermediates in context ────────────────────────────────────────


def test_to_prompt_includes_intermediates(ctx):
    """to_prompt() output contains 'Model Internals' section header."""
    prompt = ctx.to_prompt()
    assert "Model Internals" in prompt


def test_to_prompt_intermediates_has_ps_delta(ctx):
    """to_prompt() intermediates section contains P-vs-S delta information."""
    prompt = ctx.to_prompt()
    assert "delta" in prompt.lower()


def test_to_prompt_intermediates_respects_max_types(ctx):
    """Intermediates section has at most 4 pitch type rows (token budget)."""
    prompt = ctx.to_prompt()
    # Find the intermediates table section and count data rows
    in_section = False
    row_count = 0
    for line in prompt.split("\n"):
        if "Model Internals" in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break  # next section
        if in_section and line.startswith("|") and "Pitch" not in line and "---" not in line:
            row_count += 1
    assert row_count <= 4, f"Found {row_count} intermediates rows, expected <= 4"


def test_to_prompt_no_intermediates_when_empty(ctx):
    """to_prompt() with empty intermediates list omits section entirely."""
    # Create a copy with empty intermediates
    empty_ctx = ctx.model_copy(update={"intermediates": []})
    prompt = empty_ctx.to_prompt()
    assert "Model Internals" not in prompt


# ── Year-over-Year context tests ─────────────────────────────────────


def test_pitcher_context_accepts_cross_season_fields():
    """CPMT-01: PitcherContext accepts cross_season_summary and arsenal_trend fields."""
    css = _make_cross_season_summary()
    at = _make_arsenal_trend()
    ctx = _make_synthetic_ctx(cross_season_summary=css, arsenal_trend=at)
    assert ctx.cross_season_summary is css
    assert ctx.arsenal_trend is at


def test_pitcher_context_yoy_fields_default_none():
    """CPMT-01: cross_season_summary and arsenal_trend default to None."""
    ctx = _make_synthetic_ctx()
    assert ctx.cross_season_summary is None
    assert ctx.arsenal_trend is None


def test_to_prompt_yoy_section_present():
    """CPMT-02: to_prompt() renders 'Year-over-Year Changes' header when cross-season data exists."""
    ctx = _make_synthetic_ctx(
        cross_season_summary=_make_cross_season_summary(),
        arsenal_trend=_make_arsenal_trend(),
    )
    prompt = ctx.to_prompt()
    assert "## Year-over-Year Changes" in prompt


def test_to_prompt_yoy_section_absent():
    """CPMT-02: to_prompt() omits YoY section entirely when both fields are None."""
    ctx = _make_synthetic_ctx(cross_season_summary=None, arsenal_trend=None)
    prompt = ctx.to_prompt()
    assert "Year-over-Year" not in prompt


def test_to_prompt_yoy_renders_velocity_delta():
    """CPMT-02: YoY section contains velocity delta string."""
    css = _make_cross_season_summary()
    ctx = _make_synthetic_ctx(cross_season_summary=css)
    prompt = ctx.to_prompt()
    assert css.velo_delta in prompt


def test_to_prompt_yoy_renders_plus_deltas():
    """CPMT-02: YoY section contains P+/S+/L+ delta strings."""
    css = _make_cross_season_summary()
    ctx = _make_synthetic_ctx(cross_season_summary=css)
    prompt = ctx.to_prompt()
    assert css.p_plus_delta in prompt
    assert css.s_plus_delta in prompt
    assert css.l_plus_delta in prompt


def test_to_prompt_yoy_renders_added_pitches():
    """CPMT-02: YoY section contains added pitch names from arsenal_trend."""
    at = _make_arsenal_trend()
    ctx = _make_synthetic_ctx(arsenal_trend=at)
    prompt = ctx.to_prompt()
    assert "Added" in prompt
    assert "Sweeper" in prompt


def test_to_prompt_yoy_renders_dropped_pitches():
    """CPMT-02: YoY section contains dropped pitch names from arsenal_trend."""
    at = _make_arsenal_trend()
    ctx = _make_synthetic_ctx(arsenal_trend=at)
    prompt = ctx.to_prompt()
    assert "Dropped" in prompt
    assert "Knuckle Curve" in prompt


def test_to_prompt_yoy_renders_nonsteady_pitch_trends():
    """CPMT-02: YoY section shows non-Steady pitch trend deltas."""
    at = _make_arsenal_trend()
    ctx = _make_synthetic_ctx(arsenal_trend=at)
    prompt = ctx.to_prompt()
    # FF has non-Steady deltas: "Down 7.0 pp", "Up 7 points", "Up 1.4 mph"
    assert "4-Seam Fastball" in prompt
    assert "Down 7.0 pp" in prompt or "Up 7 points" in prompt


def test_to_prompt_yoy_omits_all_steady_pitch():
    """CPMT-02: YoY section omits pitches where ALL deltas are Steady."""
    at = _make_arsenal_trend()
    ctx = _make_synthetic_ctx(arsenal_trend=at)
    prompt = ctx.to_prompt()
    # The "Slider" trend has all Steady deltas in our fixture
    # It should NOT appear as a pitch trend line in the YoY section
    yoy_start = prompt.find("Year-over-Year")
    if yoy_start >= 0:
        yoy_section = prompt[yoy_start:]
        # "Slider" could appear in other sections (arsenal, etc.)
        # but should not appear in a pitch trend line within YoY
        yoy_end = yoy_section.find("\n## ", 1)
        if yoy_end > 0:
            yoy_text = yoy_section[:yoy_end]
        else:
            yoy_text = yoy_section
        assert "Slider" not in yoy_text


def test_to_prompt_yoy_section_ordering():
    """CPMT-02: YoY section appears after First-Pitch and before Recent Appearances."""
    ctx = _make_synthetic_ctx(
        cross_season_summary=_make_cross_season_summary(),
        arsenal_trend=_make_arsenal_trend(),
    )
    prompt = ctx.to_prompt()
    yoy_pos = prompt.find("Year-over-Year Changes")
    appearances_pos = prompt.find("Recent Appearances")
    assert yoy_pos > 0, "Year-over-Year section not found"
    assert appearances_pos > 0, "Recent Appearances section not found"
    assert yoy_pos < appearances_pos, "YoY should come before Recent Appearances"


def test_to_prompt_yoy_token_budget():
    """CPMT-02: to_prompt() stays under 2,000 token budget even with YoY section."""
    ctx = _make_synthetic_ctx(
        cross_season_summary=_make_cross_season_summary(),
        arsenal_trend=_make_arsenal_trend(),
    )
    prompt = ctx.to_prompt()
    estimated_tokens = len(prompt) / 4
    assert estimated_tokens < 2000, f"Estimated {estimated_tokens:.0f} tokens exceeds 2,000 budget"


def test_to_prompt_yoy_with_only_cross_season_summary():
    """CPMT-02: YoY section renders when only cross_season_summary is present (no arsenal_trend)."""
    ctx = _make_synthetic_ctx(cross_season_summary=_make_cross_season_summary())
    prompt = ctx.to_prompt()
    assert "Year-over-Year Changes" in prompt
    assert "Up 1.4 mph" in prompt


def test_to_prompt_yoy_with_only_arsenal_trend():
    """CPMT-02: YoY section renders when only arsenal_trend is present (no cross_season_summary)."""
    ctx = _make_synthetic_ctx(arsenal_trend=_make_arsenal_trend())
    prompt = ctx.to_prompt()
    assert "Year-over-Year Changes" in prompt
    assert "Sweeper" in prompt


def test_to_prompt_yoy_workload_comparison():
    """CPMT-02: YoY section includes workload comparison when cross_season_summary present."""
    css = _make_cross_season_summary()
    ctx = _make_synthetic_ctx(cross_season_summary=css)
    prompt = ctx.to_prompt()
    # Should mention appearances and IP
    assert "10 app" in prompt or "10 appearances" in prompt
    assert "45" in prompt  # current IP


def test_to_prompt_yoy_renders_movement_deltas():
    """YoY section includes H-mov/V-mov for non-Steady movement changes."""
    at = _make_arsenal_trend()
    ctx = _make_synthetic_ctx(arsenal_trend=at)
    prompt = ctx.to_prompt()
    # FF has non-Steady movement: pfx_x_delta="Down 2.0 in", pfx_z_delta="Down 1.0 in"
    assert "H-mov" in prompt
    assert "V-mov" in prompt
    assert "Down 2.0 in" in prompt
    assert "Down 1.0 in" in prompt
    # Slider has all Steady movement -- "Steady (+0.1 in)" should NOT produce H-mov/V-mov lines
    yoy_start = prompt.find("Year-over-Year")
    assert yoy_start >= 0
    yoy_section = prompt[yoy_start:]
    yoy_end = yoy_section.find("\n## ", 1)
    if yoy_end > 0:
        yoy_text = yoy_section[:yoy_end]
    else:
        yoy_text = yoy_section
    # Slider's Steady movement should not appear
    assert "Steady (+0.1 in)" not in yoy_text


# ── Appearance Pitch Trends context tests ────────────────────────────


def _make_appearance_pitch_trends() -> AppearancePitchTrends:
    """Create a synthetic AppearancePitchTrends for tests."""
    return AppearancePitchTrends(
        last_game_date="2026-04-15",
        records=[
            AppearancePitchTrendRecord(
                pitch_type="FF",
                pitch_name="4-Seam Fastball",
                n_pitches_last=20,
                last_start_velo=96.0,
                window_avg_velo=94.3,
                prior_season_velo=94.0,
                last_vs_window_velo="Up 1.7 mph",
                last_vs_prior_velo="Up 2.0 mph",
                last_start_pfx_x=0.96,
                window_avg_pfx_x=0.76,
                prior_season_pfx_x=0.66,
                last_vs_window_pfx_x="Steady (+0.2 in)",
                last_vs_prior_pfx_x="Steady (+0.3 in)",
                last_start_pfx_z=1.56,
                window_avg_pfx_z=1.44,
                prior_season_pfx_z=1.38,
                last_vs_window_pfx_z="Steady (+0.1 in)",
                last_vs_prior_pfx_z="Steady (+0.2 in)",
                pattern_label="something new",
            ),
        ],
    )


def test_appearance_pitch_trends_field_default_none():
    """appearance_pitch_trends defaults to None."""
    ctx = _make_synthetic_ctx()
    assert ctx.appearance_pitch_trends is None


def test_appearance_pitch_trends_field_accepts_value():
    """PitcherContext accepts appearance_pitch_trends field."""
    apt = _make_appearance_pitch_trends()
    ctx = _make_synthetic_ctx(appearance_pitch_trends=apt)
    assert ctx.appearance_pitch_trends is apt
    assert len(ctx.appearance_pitch_trends.records) == 1


def test_to_prompt_includes_appearance_pitch_trends():
    """to_prompt() renders 'Appearance Pitch Trends' header when data exists."""
    apt = _make_appearance_pitch_trends()
    ctx = _make_synthetic_ctx(appearance_pitch_trends=apt)
    prompt = ctx.to_prompt()
    assert "Appearance Pitch Trends" in prompt


def test_to_prompt_omits_appearance_pitch_trends_when_none():
    """to_prompt() omits appearance pitch trends when field is None."""
    ctx = _make_synthetic_ctx(appearance_pitch_trends=None)
    prompt = ctx.to_prompt()
    assert "Appearance Pitch Trends" not in prompt


def test_to_prompt_appearance_pitch_trends_contains_velo_table():
    """Rendered section has velocity comparison table with pattern label."""
    apt = _make_appearance_pitch_trends()
    ctx = _make_synthetic_ctx(appearance_pitch_trends=apt)
    prompt = ctx.to_prompt()
    assert "Last Velo" in prompt
    assert "Win Avg" in prompt
    assert "Pattern" in prompt
    assert "something new" in prompt
    assert "96.0" in prompt  # last_start_velo
    assert "94.3" in prompt  # window_avg_velo


def test_to_prompt_appearance_pitch_trends_contains_movement_detail():
    """Rendered section has horizontal and vertical movement detail tables."""
    apt = _make_appearance_pitch_trends()
    ctx = _make_synthetic_ctx(appearance_pitch_trends=apt)
    prompt = ctx.to_prompt()
    assert "Movement detail" in prompt
    assert "H-mov" in prompt
    assert "V-mov" in prompt


def test_to_prompt_appearance_pitch_trends_ordering():
    """Appearance Pitch Trends appears after Arsenal and before Execution."""
    apt = _make_appearance_pitch_trends()
    ctx = _make_synthetic_ctx(appearance_pitch_trends=apt)
    prompt = ctx.to_prompt()
    arsenal_pos = prompt.find("## Arsenal")
    apt_pos = prompt.find("## Appearance Pitch Trends")
    exec_pos = prompt.find("## Execution")
    assert arsenal_pos > 0, "Arsenal section not found"
    assert apt_pos > 0, "Appearance Pitch Trends section not found"
    assert exec_pos > 0, "Execution section not found"
    assert arsenal_pos < apt_pos < exec_pos, (
        f"Ordering wrong: Arsenal@{arsenal_pos}, APT@{apt_pos}, Exec@{exec_pos}"
    )


# ── Count Splits context tests ─────────────────────────────────────


def _make_count_splits(*, notable_shifts: list[str] | None = None) -> CountSplits:
    """Create a synthetic CountSplits for tests."""
    return CountSplits(
        buckets=[
            CountBucket(
                bucket="ahead",
                n_pitches_window=25,
                n_pitches_season=200,
                small_sample=False,
                pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=60.0),
                    CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=40.0),
                ],
                season_pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=55.0),
                    CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=45.0),
                ],
            ),
            CountBucket(
                bucket="behind",
                n_pitches_window=15,
                n_pitches_season=180,
                small_sample=False,
                pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=70.0),
                    CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=30.0),
                ],
                season_pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=65.0),
                    CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=35.0),
                ],
            ),
            CountBucket(
                bucket="even",
                n_pitches_window=20,
                n_pitches_season=150,
                small_sample=False,
                pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=50.0),
                ],
                season_pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=52.0),
                ],
            ),
            CountBucket(
                bucket="two_strike",
                n_pitches_window=10,
                n_pitches_season=120,
                small_sample=False,
                pitch_types=[
                    CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=65.0),
                ],
                season_pitch_types=[
                    CountBucketUsage(pitch_type="SL", pitch_name="Slider", usage_pct=60.0),
                ],
            ),
            CountBucket(
                bucket="first_pitch",
                n_pitches_window=5,
                n_pitches_season=50,
                small_sample=True,
                pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=80.0),
                ],
                season_pitch_types=[
                    CountBucketUsage(pitch_type="FF", pitch_name="4-Seam Fastball", usage_pct=70.0),
                ],
            ),
        ],
        notable_shifts=notable_shifts if notable_shifts is not None else [
            "4-Seam Fastball: +15pp in Ahead in count (60% vs 45% season)"
        ],
    )


def _make_synthetic_ctx_with_count_splits(
    *,
    count_splits: CountSplits | None = None,
    release_point: ReleasePointMetrics | None = None,
    platoon_mix: PlatoonMix | None = None,
) -> PitcherContext:
    """Build a minimal synthetic PitcherContext with count splits and optional release point."""
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

    if platoon_mix is None:
        platoon_mix = PlatoonMix(
            splits=[
                PlatoonSplit(
                    pitch_type="FF",
                    pitch_name="4-Seam Fastball",
                    platoon_side="same",
                    season_usage_pct=55.0,
                    window_usage_pct=50.0,
                    usage_delta="Down modestly",
                    season_p_plus=105.0,
                    window_p_plus=108.0,
                    p_plus_delta="Up modestly",
                    available=True,
                ),
            ],
            cold_start=False,
        )

    if release_point is None:
        release_point = ReleasePointMetrics(pitch_types=[], cold_start=False)

    return PitcherContext(
        pitcher_name="Test Pitcher",
        pitcher_id=99999,
        throws="R",
        role="SP",
        fastball=fastball,
        velocity_arc=None,
        arsenal=arsenal,
        platoon_mix=platoon_mix,
        first_pitch=FirstPitchWeaponry(entries=[], total_first_pitches_season=100, total_first_pitches_window=10, cold_start=False),
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
        release_point=release_point,
        workload=workload,
        tto=None,
        count_splits=count_splits,
    )


def test_pitcher_context_accepts_count_splits_field():
    """PitcherContext accepts count_splits field of type CountSplits."""
    cs = _make_count_splits()
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    assert ctx.count_splits is cs


def test_pitcher_context_count_splits_defaults_none():
    """PitcherContext count_splits defaults to None."""
    ctx = _make_synthetic_ctx_with_count_splits()
    assert ctx.count_splits is None


def test_assemble_pitcher_context_has_count_splits(ctx):
    """assemble_pitcher_context result has count_splits populated (not None)."""
    assert ctx.count_splits is not None
    assert isinstance(ctx.count_splits, CountSplits)


def test_to_prompt_count_splits_section_header():
    """to_prompt() output contains 'Count-State Usage Shifts' section header when notable shifts exist."""
    cs = _make_count_splits()
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    prompt = ctx.to_prompt()
    assert "## Count-State Usage Shifts" in prompt


def test_to_prompt_count_splits_adjacent_to_platoon():
    """D-13: Count-State section appears AFTER Platoon and BEFORE First-Pitch."""
    cs = _make_count_splits()
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    prompt = ctx.to_prompt()
    platoon_pos = prompt.find("## Platoon Shifts")
    count_state_pos = prompt.find("## Count-State Usage Shifts")
    first_pitch_pos = prompt.find("## First-Pitch Tendencies")
    assert platoon_pos > 0, "Platoon section not found"
    assert count_state_pos > 0, "Count-State section not found"
    assert first_pitch_pos > 0, "First-Pitch section not found"
    assert platoon_pos < count_state_pos < first_pitch_pos, (
        f"Ordering wrong: Platoon@{platoon_pos}, CountState@{count_state_pos}, FirstPitch@{first_pitch_pos}"
    )


def test_to_prompt_count_splits_appendix_header():
    """to_prompt() output contains 'Count-State Usage Appendix' section."""
    cs = _make_count_splits()
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    prompt = ctx.to_prompt()
    assert "## Count-State Usage Appendix" in prompt


def test_to_prompt_count_splits_appendix_ordering():
    """Appendix appears AFTER YoY section and BEFORE Recent Appearances."""
    cs = _make_count_splits()
    ctx = _make_synthetic_ctx_with_count_splits(
        count_splits=cs,
    )
    prompt = ctx.to_prompt()
    appendix_pos = prompt.find("## Count-State Usage Appendix")
    appearances_pos = prompt.find("## Recent Appearances")
    assert appendix_pos > 0, "Count-State Usage Appendix not found"
    assert appearances_pos > 0, "Recent Appearances not found"
    assert appendix_pos < appearances_pos, (
        f"Appendix@{appendix_pos} should be before Appearances@{appearances_pos}"
    )


def test_to_prompt_count_splits_notable_shifts_rendered():
    """When count_splits has notable_shifts, they appear in the inline section."""
    cs = _make_count_splits(notable_shifts=["4-Seam Fastball: +15pp in Ahead in count (60% vs 45% season)"])
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    prompt = ctx.to_prompt()
    assert "+15pp" in prompt
    assert "Ahead in count" in prompt


def test_to_prompt_count_splits_small_sample_tag():
    """When a bucket has small_sample=True, the appendix shows '(small sample)'."""
    cs = _make_count_splits()
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    prompt = ctx.to_prompt()
    assert "(small sample)" in prompt


def test_to_prompt_count_splits_appendix_has_table():
    """Appendix contains markdown table with Window %, Season %, Delta columns."""
    cs = _make_count_splits()
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    prompt = ctx.to_prompt()
    assert "Window %" in prompt
    assert "Season %" in prompt
    assert "Delta" in prompt


def test_to_prompt_count_splits_no_notable_shifts_omits_inline():
    """When count_splits has no notable_shifts, inline section is omitted."""
    cs = _make_count_splits(notable_shifts=[])
    ctx = _make_synthetic_ctx_with_count_splits(count_splits=cs)
    prompt = ctx.to_prompt()
    assert "## Count-State Usage Shifts" not in prompt
    # But appendix should still render
    assert "## Count-State Usage Appendix" in prompt


# ── Arm Angle in Release Point tests ───────────────────────────────


def _make_release_point_with_arm_angle() -> ReleasePointMetrics:
    """Create a ReleasePointMetrics with arm angle data."""
    return ReleasePointMetrics(
        pitch_types=[
            ReleasePointPitchType(
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
                n_pitches_window=25,
                small_sample=False,
                cold_start=False,
                window_arm_angle=71.5,
                season_arm_angle=71.0,
                arm_angle_delta="Steady (+0.5 deg)",
                arm_slot="High 3/4",
            ),
            ReleasePointPitchType(
                pitch_type="SL",
                pitch_name="Slider",
                window_release_x=-1.8,
                season_release_x=-1.9,
                release_x_delta="Steady",
                window_release_z=5.8,
                season_release_z=5.7,
                release_z_delta="Steady",
                window_extension=6.3,
                season_extension=6.2,
                extension_delta="Steady",
                n_pitches_window=15,
                small_sample=False,
                cold_start=False,
                window_arm_angle=70.2,
                season_arm_angle=70.0,
                arm_angle_delta="Steady (+0.2 deg)",
                arm_slot="High 3/4",
            ),
        ],
        cold_start=False,
    )


def test_to_prompt_release_point_includes_arm_angle():
    """Release point section includes arm angle degrees for each pitch type."""
    rp = _make_release_point_with_arm_angle()
    ctx = _make_synthetic_ctx_with_count_splits(release_point=rp)
    prompt = ctx.to_prompt()
    assert "71.5 deg" in prompt  # window_arm_angle for FF
    assert "High 3/4" in prompt  # arm_slot


def test_to_prompt_release_point_arm_angle_per_pitch():
    """Each pitch type in release point section has arm angle and slot label."""
    rp = _make_release_point_with_arm_angle()
    ctx = _make_synthetic_ctx_with_count_splits(release_point=rp)
    prompt = ctx.to_prompt()
    # Both pitch types should have arm angle rendered
    assert "71.5" in prompt  # FF arm angle
    assert "70.2" in prompt  # SL arm angle
    assert "deg" in prompt  # units
