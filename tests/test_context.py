"""Tests for PitcherContext assembly and to_prompt() rendering."""

import pytest
from pydantic import BaseModel

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.engine import HardHitRate, ReleasePointMetrics
from pitcher_narratives.shape import PitchShapeProfile

TEST_PITCHER = 592155  # Booser, Cam


@pytest.fixture(scope="module")
def ctx():
    """Load data once per module (read-only test data)."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    return assemble_pitcher_context(data)


def test_assemble_prior_context_differs_from_recent():
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context

    data = load_pitcher_data(592155, recent_appearances=5)
    recent = assemble_pitcher_context(data)
    prior = assemble_prior_context(data, recent_n=5, prior_m=5)
    # Both are fully-shaped PitcherContexts; the prior frame draws different
    # appearances, so at least the window pitch counts differ.
    assert isinstance(prior.arsenal, list)
    recent_counts = {p.pitch_name: p.n_pitches_window for p in recent.arsenal}
    prior_counts = {p.pitch_name: p.n_pitches_window for p in prior.arsenal}
    assert recent_counts != prior_counts


def test_assemble_prior_context_empty_prior_is_shaped():
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.context import assemble_prior_context

    data = load_pitcher_data(592155, recent_appearances=5)
    # recent_n far beyond available -> prior slice empty -> still a valid ctx
    prior = assemble_prior_context(data, recent_n=9999, prior_m=5)
    assert prior.pitcher_name  # shaped, no crash (empty-frame guards from Phase 5)


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


# ── Year-over-Year rendering tests ───────────────────────────────────


def test_yoy_section_present_for_multi_season(ctx):
    """to_prompt() includes Year-over-Year section when cross-season data exists."""
    prompt = ctx.to_prompt()
    if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
        assert "## Year-over-Year" in prompt
    else:
        assert "## Year-over-Year" not in prompt


def test_yoy_section_omitted_for_single_season():
    """_render_yoy_section returns empty string when both fields are None."""
    from datetime import date

    from pitcher_narratives.context import PitcherContext
    from pitcher_narratives.engine import (
        FirstPitchWeaponry,
        HardHitRate,
        PlatoonMix,
        ReleasePointMetrics,
        TemporalContext,
        WorkloadContext,
    )

    # Minimal PitcherContext with no cross-season data
    ctx = PitcherContext(
        pitcher_name="Test Pitcher",
        pitcher_id=0,
        throws="R",
        role="SP",
        fastball=None,
        velocity_arc=None,
        arsenal=[],
        platoon_mix=PlatoonMix(splits=[], cold_start=True),
        first_pitch=FirstPitchWeaponry(
            entries=[], total_first_pitches_season=0,
            total_first_pitches_window=0, cold_start=True,
        ),
        execution=[],
        intermediates=[],
        attributions=[],
        hard_hit_rate=HardHitRate(
            hard_hit_pct=0, season_hard_hit_pct=0, delta="Steady",
            n_batted_balls=0, n_hard_hit=0, small_sample=True, cold_start=True,
        ),
        release_point=ReleasePointMetrics(pitch_types=[], cold_start=True),
        workload=WorkloadContext(
            appearances=[], max_consecutive_days=0, workload_concern=False,
        ),
        temporal=TemporalContext(
            analysis_date=date(2026, 4, 8),
            current_season=2026,
            current_season_appearances=10,
            current_season_ip="20.0",
            current_season_first_date="2026-03-28",
            prior_season=2025,
            prior_season_appearances=0,
            prior_season_ip="0.0",
            prior_year_relevance="LOW",
            prior_year_relevance_reason="No prior season data",
        ),
        cross_season_summary=None,
        arsenal_trend=None,
    )
    from pitcher_narratives.prompt_builder import render_yoy_section

    result = render_yoy_section(ctx)
    assert result == ""
    prompt = ctx.to_prompt()
    assert "Year-over-Year" not in prompt


def test_yoy_section_renders_cross_season_summary():
    """_render_yoy_section renders top-level deltas from CrossSeasonSummary."""
    from datetime import date

    from pitcher_narratives.context import PitcherContext
    from pitcher_narratives.engine import (
        CrossSeasonSummary,
        FirstPitchWeaponry,
        HardHitRate,
        PlatoonMix,
        ReleasePointMetrics,
        TemporalContext,
        WorkloadContext,
    )

    css = CrossSeasonSummary(
        current_season=2026, prior_season=2025,
        current_velo=93.5, prior_velo=92.0, velo_delta="Up 1.5 mph",
        current_p_plus=110, prior_p_plus=100, p_plus_delta="Up 10 pts",
        current_s_plus=115, prior_s_plus=105, s_plus_delta="Up 10 pts",
        current_l_plus=95, prior_l_plus=100, l_plus_delta="Down 5 pts",
    )
    ctx = PitcherContext(
        pitcher_name="Test Pitcher",
        pitcher_id=0,
        throws="R",
        role="SP",
        fastball=None,
        velocity_arc=None,
        arsenal=[],
        platoon_mix=PlatoonMix(splits=[], cold_start=True),
        first_pitch=FirstPitchWeaponry(
            entries=[], total_first_pitches_season=0,
            total_first_pitches_window=0, cold_start=True,
        ),
        execution=[],
        intermediates=[],
        attributions=[],
        hard_hit_rate=HardHitRate(
            hard_hit_pct=0, season_hard_hit_pct=0, delta="Steady",
            n_batted_balls=0, n_hard_hit=0, small_sample=True, cold_start=True,
        ),
        release_point=ReleasePointMetrics(pitch_types=[], cold_start=True),
        workload=WorkloadContext(
            appearances=[], max_consecutive_days=0, workload_concern=False,
        ),
        temporal=TemporalContext(
            analysis_date=date(2026, 4, 8),
            current_season=2026,
            current_season_appearances=10,
            current_season_ip="20.0",
            current_season_first_date="2026-03-28",
            prior_season=2025,
            prior_season_appearances=30,
            prior_season_ip="180.0",
            prior_year_relevance="HIGH",
            prior_year_relevance_reason="Full prior season",
        ),
        cross_season_summary=css,
        arsenal_trend=None,
    )
    from pitcher_narratives.prompt_builder import render_yoy_section

    section = render_yoy_section(ctx)
    assert "## Year-over-Year" in section
    assert "2026 vs 2025" in section
    assert "Up 1.5 mph" in section
    assert "P+" in section
    assert "S+" in section
    assert "L+" in section


# ── Pitch shape vs arm slot in context ───────────────────────────────


def test_pitch_shape_in_context(ctx):
    """assemble_pitcher_context has a non-None pitch_shape field of type PitchShapeProfile."""
    assert ctx.pitch_shape is not None
    assert isinstance(ctx.pitch_shape, PitchShapeProfile)


def test_to_prompt_has_pitch_shape_section(ctx):
    """to_prompt() output contains the 'Pitch Shape vs Arm Slot' section header."""
    prompt = ctx.to_prompt()
    assert "Pitch Shape vs Arm Slot" in prompt


def test_to_prompt_pitch_shape_explains_dead_zone(ctx):
    """Pitch shape section self-documents what DEAD ZONE means for the LLM."""
    prompt = ctx.to_prompt()
    assert "DEAD ZONE" in prompt


def test_to_prompt_pitch_shape_has_arm_angle(ctx):
    """Pitch shape section reports the arm angle in degrees."""
    prompt = ctx.to_prompt()
    start = prompt.index("Pitch Shape vs Arm Slot")
    section = prompt[start : prompt.index("\n## ", start)]
    assert "deg" in section


# ── MultiFrameContext (Phase 2) ──────────────────────────────────────


def test_multi_frame_context_primary_and_for_frame(ctx):
    from pitcher_narratives.context import MultiFrameContext
    from pitcher_narratives.temporal import TemporalFrame

    mfc = MultiFrameContext(frames={TemporalFrame.RECENT: ctx})
    assert mfc.primary is ctx
    assert mfc.for_frame(TemporalFrame.RECENT) is ctx

    import pytest
    with pytest.raises(ValueError, match="season"):
        mfc.for_frame(TemporalFrame.SEASON)


def test_assemble_multi_frame_primary_matches_single(ctx):
    from pitcher_narratives.context import assemble_multi_frame_context
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.temporal import TemporalFrame

    data = load_pitcher_data(592155, recent_appearances=10)
    mfc = assemble_multi_frame_context(data)

    assert set(mfc.frames) == {TemporalFrame.RECENT}
    # Behavior-preserving: the wrapped frame matches the existing assembly.
    assert mfc.primary.pitcher_id == ctx.pitcher_id
    assert mfc.primary.to_prompt() == ctx.to_prompt()


def test_primary_frame_is_recent():
    from pitcher_narratives.context import assemble_multi_frame_context
    from pitcher_narratives.temporal import TemporalFrame

    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    mfc = assemble_multi_frame_context(data)
    assert TemporalFrame.RECENT in mfc.frames
    assert mfc.primary is mfc.for_frame(TemporalFrame.RECENT)
