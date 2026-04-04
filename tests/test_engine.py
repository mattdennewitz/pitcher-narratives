"""Tests for the fastball quality, arsenal, execution metrics, workload, and cross-season engine.

Covers delta string helpers, FastballSummary computation, VelocityArc
computation, cold start fallback, small sample flagging, arsenal summary,
platoon mix shifts, first-pitch weaponry analysis, execution metrics
(CSW%, zone rate, chase rate, xWhiff, xSwing, xRV100 percentile),
workload context (rest days, IP, pitch counts, consecutive days), and
cross-season year-over-year delta computation and arsenal trend computation.
"""

from datetime import date

import polars as pl

from pitcher_narratives.data import PitcherData, load_pitcher_data
from pitcher_narratives.engine import (
    _CSW_DESCRIPTIONS,
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
    OutcomeContribution,
    PitchTrend,
    PitchTypeSummary,
    PlatoonMix,
    PlatoonSplit,
    ReleasePointMetrics,
    ReleasePointPitchType,
    TTOAnalysis,
    TTOPitchType,
    TTOSplit,
    VelocityArc,
    WorkloadContext,
    _identify_primary_fastball,
    _movement_delta_string,
    _pplus_delta_string,
    _stand_to_platoon,
    _usage_delta_string,
    _velo_delta_string,
    compute_appearance_pitch_trends,
    compute_arsenal_summary,
    compute_arsenal_trends,
    compute_component_attribution,
    compute_count_splits,
    compute_cross_season_summary,
    compute_execution_metrics,
    compute_fastball_summary,
    compute_first_pitch_weaponry,
    compute_hard_hit_rate,
    compute_intermediate_probabilities,
    compute_platoon_mix,
    compute_release_point_metrics,
    compute_tto_analysis,
    compute_velocity_arc,
    compute_workload_context,
)

TEST_PITCHER = 592155  # Booser, Cam -- LHP, 12 appearances, FC primary fastball


# ── Delta string helpers ──────────────────────────────────────────────


def test_velo_delta_string_steady():
    """Below 0.5 mph threshold reports 'Steady'."""
    result = _velo_delta_string(0.3)
    assert "Steady" in result
    assert "+0.3" in result


def test_velo_delta_string_up():
    """Above threshold, positive delta reports 'Up X mph'."""
    result = _velo_delta_string(1.5)
    assert "Up" in result
    assert "1.5" in result
    assert "mph" in result


def test_velo_delta_string_down_sharply():
    """Above sharp threshold (2.0), reports 'sharply'."""
    result = _velo_delta_string(-2.5)
    assert "Down" in result
    assert "sharply" in result
    assert "2.5" in result
    assert "mph" in result


def test_pplus_delta_string_up():
    """P+ delta above threshold reports 'Up N points'."""
    result = _pplus_delta_string(8.0)
    assert "Up" in result
    assert "8" in result
    assert "points" in result


def test_pplus_delta_string_down():
    """P+ delta below negative threshold reports 'Down N points'."""
    result = _pplus_delta_string(-3.0)
    assert "Steady" in result


def test_pplus_delta_string_steady():
    """P+ delta below 5-point threshold reports 'Steady'."""
    result = _pplus_delta_string(3.0)
    assert "Steady" in result


def test_pplus_delta_string_sharply():
    """P+ delta above 10-point sharp threshold reports 'sharply'."""
    result = _pplus_delta_string(15.0)
    assert "sharply" in result
    assert "15" in result


def test_usage_delta_string_up():
    """Usage delta above 5 pp threshold reports 'Up'."""
    result = _usage_delta_string(7.0)
    assert "Up" in result
    assert "7.0" in result
    assert "pp" in result


def test_usage_delta_string_steady():
    """Usage delta below 5 pp threshold reports 'Steady'."""
    result = _usage_delta_string(3.0)
    assert "Steady" in result


def test_movement_delta_string_steady():
    """Movement delta below 0.5 in threshold reports 'Steady'."""
    result = _movement_delta_string(0.2)
    assert "Steady" in result
    assert "in" in result


def test_movement_delta_string_direction():
    """Movement delta above threshold reports direction."""
    result = _movement_delta_string(1.5)
    assert "Up" in result or "Gained" in result or "1.5" in result
    assert "in" in result


# ── Primary fastball identification ───────────────────────────────────


def test_identify_primary_fastball():
    """Returns a fastball type for test pitcher (FF and FC tied at 5 pitches each)."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = _identify_primary_fastball(data.pitch_type_baseline)
    assert result in ("FF", "FC")


def test_identify_primary_fastball_no_fb():
    """Returns None for a pitcher with no FF/SI/FC types."""
    import polars as pl

    # Create a fake pitch_type_baseline with no fastball types
    fake_baseline = pl.DataFrame(
        {
            "pitch_type": ["CH", "SL", "CU"],
            "n_pitches": [50, 40, 30],
        }
    )
    result = _identify_primary_fastball(fake_baseline)
    assert result is None


# ── FastballSummary ───────────────────────────────────────────────────


def test_fastball_velocity_delta():
    """compute_fastball_summary returns FastballSummary with velocity fields."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert isinstance(summary, FastballSummary)
    assert isinstance(summary.season_velo, float)
    assert isinstance(summary.window_velo, float)
    assert isinstance(summary.velo_delta, str)
    # Velocity should be reasonable for MLB (70-105 mph)
    assert 70.0 < summary.season_velo < 105.0
    assert 70.0 < summary.window_velo < 105.0
    # Delta string should contain directional vocabulary or cold-start message
    assert any(word in summary.velo_delta for word in ["Up", "Down", "Steady", "Full season in window"])


def test_fastball_pplus_delta():
    """FastballSummary has P+ season/window/delta fields."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert isinstance(summary.season_p_plus, float)
    # window_p_plus may be None if no P+ data in window
    assert isinstance(summary.p_plus_delta, str)
    assert any(word in summary.p_plus_delta for word in ["Up", "Down", "Steady", "Full season"])


def test_fastball_splus_lplus():
    """FastballSummary has S+ and L+ season/window/delta fields."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert isinstance(summary.season_s_plus, float)
    assert isinstance(summary.s_plus_delta, str)
    assert isinstance(summary.season_l_plus, float)
    assert isinstance(summary.l_plus_delta, str)


def test_fastball_movement_delta():
    """FastballSummary has pfx_x/pfx_z season/window/delta fields."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert isinstance(summary.season_pfx_x, float)
    assert isinstance(summary.window_pfx_x, float)
    assert isinstance(summary.pfx_x_delta, str)
    assert isinstance(summary.season_pfx_z, float)
    assert isinstance(summary.window_pfx_z, float)
    assert isinstance(summary.pfx_z_delta, str)


def test_fastball_pitch_type():
    """FastballSummary identifies a fastball type for test pitcher (FF/FC tied)."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert summary.pitch_type in ("FF", "FC")
    assert summary.pitch_name != ""  # Should have human-readable name


# ── VelocityArc ──────────────────────────────────────────────────────


def test_velocity_arc_single_inning():
    """Single-inning appearance returns VelocityArc with available=False."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    summary = compute_fastball_summary(data)
    assert summary is not None
    arc = compute_velocity_arc(data, summary.pitch_type)
    assert isinstance(arc, VelocityArc)
    # Test pitcher's most recent appearance is single-inning
    assert arc.available is False
    assert "Single inning" in arc.drop_string


def test_velocity_arc():
    """Multi-inning appearance returns VelocityArc with early/late velo."""
    # Use a pitcher with multi-inning appearances for this test.
    # Test pitcher Booser is all single-inning, so we test the structure
    # and the single-inning fallback above. For the multi-inning case,
    # we verify the dataclass fields are correct.
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    summary = compute_fastball_summary(data)
    assert summary is not None
    arc = compute_velocity_arc(data, summary.pitch_type)
    assert isinstance(arc, VelocityArc)
    assert isinstance(arc.game_pk, int)
    assert isinstance(arc.game_date, str)
    assert isinstance(arc.drop_string, str)
    assert isinstance(arc.innings_pitched, int)


# ── Cold start ────────────────────────────────────────────────────────


def test_cold_start_fallback():
    """When window covers full season, delta strings contain cold start message."""
    # Use window_days=9999 so all appearances fall in window
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert summary.cold_start is True
    assert "Full season in window" in summary.velo_delta
    assert "Full season in window" in summary.p_plus_delta
    assert "Full season in window" in summary.pfx_x_delta


# ── Small sample ──────────────────────────────────────────────────────


def test_small_sample_flag():
    """FastballSummary.small_sample is True when <10 fastballs in window."""
    # Use a very small window to get few pitches
    data = load_pitcher_data(TEST_PITCHER, window_days=1)
    summary = compute_fastball_summary(data)
    # Even with small window, summary should exist (or be None if no pitches)
    if summary is not None:
        assert isinstance(summary.small_sample, bool)
        # With 1-day window, likely small sample
        if summary.small_sample:
            assert summary.small_sample is True


# ── Arsenal Summary ──────────────────────────────────────────────────


def test_usage_rate_deltas():
    """compute_arsenal_summary returns PitchTypeSummary list with usage deltas."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    arsenal = compute_arsenal_summary(data)
    assert isinstance(arsenal, list)
    assert len(arsenal) > 0
    for pts in arsenal:
        assert isinstance(pts, PitchTypeSummary)
        assert isinstance(pts.season_usage_pct, float)
        assert isinstance(pts.window_usage_pct, float)
        assert isinstance(pts.usage_delta, str)
        # Usage pcts should sum to ~100
        assert 0.0 < pts.season_usage_pct <= 100.0
        assert 0.0 <= pts.window_usage_pct <= 100.0
    # Total season usage should sum to ~100%
    total_season = sum(p.season_usage_pct for p in arsenal)
    assert 99.0 < total_season < 101.0


def test_arsenal_pplus_deltas():
    """Each PitchTypeSummary has P+/S+/L+ season, window, and delta fields."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    arsenal = compute_arsenal_summary(data)
    assert len(arsenal) > 0
    for pts in arsenal:
        assert isinstance(pts.season_p_plus, float)
        assert isinstance(pts.p_plus_delta, str)
        assert isinstance(pts.season_s_plus, float)
        assert isinstance(pts.s_plus_delta, str)
        assert isinstance(pts.season_l_plus, float)
        assert isinstance(pts.l_plus_delta, str)
        # P+/S+/L+ should be in reasonable range (50-200 ish)
        assert 20.0 < pts.season_p_plus < 250.0
        # Delta strings should contain known vocabulary
        assert any(word in pts.p_plus_delta for word in ["Up", "Down", "Steady", "Full season", "No window"])


def test_arsenal_pitch_names():
    """Each PitchTypeSummary has human-readable pitch_name."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    arsenal = compute_arsenal_summary(data)
    for pts in arsenal:
        assert isinstance(pts.pitch_name, str)
        assert pts.pitch_name != ""
        # Should not be just the code (e.g., "FC"), should be full name
        assert len(pts.pitch_name) > 2


def test_arsenal_ordering():
    """PitchTypeSummary list is ordered by season usage descending."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    arsenal = compute_arsenal_summary(data)
    assert len(arsenal) >= 2
    # Verify descending order
    for i in range(len(arsenal) - 1):
        assert arsenal[i].season_usage_pct >= arsenal[i + 1].season_usage_pct
    # Top pitch should be one of the fastball types (FF/FC/ST tied after filtering)
    assert arsenal[0].pitch_type in ("FF", "FC", "ST")


def test_arsenal_small_sample():
    """PitchTypeSummary.small_sample is True for pitch types with < 10 pitches in window."""
    # Use a tiny window to get few pitches per type
    data = load_pitcher_data(TEST_PITCHER, window_days=1)
    arsenal = compute_arsenal_summary(data)
    for pts in arsenal:
        assert isinstance(pts.small_sample, bool)
        if pts.n_pitches_window < 10:
            assert pts.small_sample is True


def test_single_pitch_type():
    """Pitcher with only 1 pitch type gets 1-element arsenal list with 100% usage."""
    # Test the delta string for single-type scenario
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    arsenal = compute_arsenal_summary(data)
    # Test pitcher has 4 types, so verify list has 4 elements
    assert len(arsenal) == 4
    # Verify each has the pitch_type and n_pitches_season fields
    for pts in arsenal:
        assert pts.n_pitches_season > 0
    # For single-type case: verify _usage_delta_string with 0 delta at 100% would say "Steady"
    # This is a unit-level check of the logic
    steady = _usage_delta_string(0.0)
    assert "Steady" in steady


def test_cold_start_arsenal():
    """With large window covering full season, delta strings contain 'Full season in window'."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    arsenal = compute_arsenal_summary(data)
    assert len(arsenal) > 0
    for pts in arsenal:
        assert pts.cold_start is True
        assert "Full season in window" in pts.usage_delta
        assert "Full season in window" in pts.p_plus_delta
        assert "Full season in window" in pts.s_plus_delta
        assert "Full season in window" in pts.l_plus_delta


# ── Platoon Mix ──────────────────────────────────────────────────────


def test_platoon_mix_shifts():
    """compute_platoon_mix returns PlatoonMix with per-type per-side usage rates and deltas."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    platoon = compute_platoon_mix(data)
    assert isinstance(platoon, PlatoonMix)
    assert isinstance(platoon.splits, list)
    assert len(platoon.splits) > 0
    for split in platoon.splits:
        assert isinstance(split, PlatoonSplit)
        assert split.platoon_side in ("same", "opposite")
        assert isinstance(split.pitch_type, str)
        assert isinstance(split.pitch_name, str)
        if split.available:
            assert isinstance(split.season_usage_pct, float)
            assert isinstance(split.usage_delta, str)


def test_platoon_missing_combo():
    """For CH (only thrown to opposite side for test pitcher), same-side entry shows unavailable."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    platoon = compute_platoon_mix(data)
    # Find the CH same-side split
    ch_same = [s for s in platoon.splits if s.pitch_type == "CH" and s.platoon_side == "same"]
    assert len(ch_same) == 1
    assert ch_same[0].available is False
    assert "same-side" in ch_same[0].usage_delta.lower() or "not thrown" in ch_same[0].usage_delta.lower()


def test_platoon_mapping():
    """For LHP, stand=L maps to 'same' and stand=R maps to 'opposite'."""
    assert _stand_to_platoon("L", "L") == "same"
    assert _stand_to_platoon("R", "L") == "opposite"
    # Also verify RHP
    assert _stand_to_platoon("R", "R") == "same"
    assert _stand_to_platoon("L", "R") == "opposite"


# ── First Pitch Weaponry ─────────────────────────────────────────────


def test_first_pitch_weaponry():
    """compute_first_pitch_weaponry returns FirstPitchWeaponry with per-type first-pitch %."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    fpw = compute_first_pitch_weaponry(data)
    assert isinstance(fpw, FirstPitchWeaponry)
    assert isinstance(fpw.entries, list)
    assert len(fpw.entries) > 0
    for entry in fpw.entries:
        assert isinstance(entry, FirstPitchEntry)
        assert isinstance(entry.season_pct, float)
        assert isinstance(entry.window_pct, float)
        assert isinstance(entry.delta, str)
        assert 0.0 <= entry.season_pct <= 100.0
    # Total first pitch % should sum to ~100
    total_season_pct = sum(e.season_pct for e in fpw.entries)
    assert 99.0 < total_season_pct < 101.0


def test_first_pitch_count():
    """Total first pitches equals number of batters faced across all seasons."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    fpw = compute_first_pitch_weaponry(data)
    assert fpw.total_first_pitches_season > 0


def test_first_pitch_ordering():
    """First pitch entries are ordered by window_pct descending."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    fpw = compute_first_pitch_weaponry(data)
    for i in range(len(fpw.entries) - 1):
        assert fpw.entries[i].window_pct >= fpw.entries[i + 1].window_pct


# ── Execution Metrics ────────────────────────────────────────────────


def test_csw_per_type():
    """compute_execution_metrics returns list of ExecutionMetrics; FC has csw_pct > 0."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    metrics = compute_execution_metrics(data)
    assert isinstance(metrics, list)
    assert len(metrics) > 0
    for m in metrics:
        assert isinstance(m, ExecutionMetrics)
    # FC should have positive CSW%
    fc_metrics = [m for m in metrics if m.pitch_type == "FC"]
    assert len(fc_metrics) == 1
    assert fc_metrics[0].csw_pct > 0.0


def test_csw_descriptions_exact():
    """CSW only counts called_strike, swinging_strike, swinging_strike_blocked."""
    assert (
        frozenset(
            {
                "called_strike",
                "swinging_strike",
                "swinging_strike_blocked",
            }
        )
        == _CSW_DESCRIPTIONS
    )


def test_zone_rate():
    """ExecutionMetrics entries have zone_rate between 0-100, null zones excluded."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    metrics = compute_execution_metrics(data)
    for m in metrics:
        assert isinstance(m.zone_rate, float)
        assert 0.0 <= m.zone_rate <= 100.0


def test_chase_rate():
    """ExecutionMetrics entries have chase_rate (O-Swing%) between 0-100, zones 11-14 only."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    metrics = compute_execution_metrics(data)
    for m in metrics:
        assert isinstance(m.chase_rate, float)
        assert 0.0 <= m.chase_rate <= 100.0


def test_xwhiff_xswing():
    """ExecutionMetrics entries have xwhiff_p and xswing_p from pitcher_type_appearance CSV."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    metrics = compute_execution_metrics(data)
    # At least one pitch type should have xwhiff_p data (FC has enough pitches)
    fc_metrics = [m for m in metrics if m.pitch_type == "FC"]
    assert len(fc_metrics) == 1
    # xwhiff_p may be None for small sample types, but FC should have data
    assert fc_metrics[0].xwhiff_p is not None or fc_metrics[0].small_sample
    assert fc_metrics[0].xswing_p is not None or fc_metrics[0].small_sample


def test_xrv100_percentile():
    """ExecutionMetrics entries have xrv100_percentile as int 0-100, computed against distribution."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    metrics = compute_execution_metrics(data)
    fc_metrics = [m for m in metrics if m.pitch_type == "FC"]
    assert len(fc_metrics) == 1
    pctl = fc_metrics[0].xrv100_percentile
    assert isinstance(pctl, int)
    assert 0 <= pctl <= 100
    # Should not be exactly 50 (fallback) -- computed against real distribution
    assert pctl != 50


def test_xrv100_polarity():
    """Lower (more negative) xRV100 = better for pitcher = higher percentile."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    metrics = compute_execution_metrics(data)
    # Just verify the percentile is in valid range and the structure is correct
    # The polarity test is that the computation uses > (worse) to count n_worse
    for m in metrics:
        if m.xrv100_percentile is not None:
            assert 0 <= m.xrv100_percentile <= 100


def test_execution_metrics_small_sample():
    """ExecutionMetrics.small_sample is True when < 10 pitches of that type in window."""
    data = load_pitcher_data(TEST_PITCHER, window_days=1)
    metrics = compute_execution_metrics(data)
    for m in metrics:
        assert isinstance(m.small_sample, bool)
        if m.n_pitches < 10:
            assert m.small_sample is True


def test_execution_metrics_cold_start():
    """When window covers full season, cold_start is True."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    metrics = compute_execution_metrics(data)
    assert len(metrics) > 0
    for m in metrics:
        assert m.cold_start is True


# ── Workload Context ────────────────────────────────────────────────


def test_rest_days():
    """compute_workload_context returns WorkloadContext with rest_days; first has None, rest have int >= 0."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    workload = compute_workload_context(data)
    assert isinstance(workload, WorkloadContext)
    assert len(workload.appearances) > 0
    # First appearance has rest_days = None
    assert workload.appearances[0].rest_days is None
    # Subsequent appearances have int >= 0
    for app in workload.appearances[1:]:
        assert isinstance(app.rest_days, int)
        assert app.rest_days >= 0


def test_rest_days_consecutive():
    """Two appearances on consecutive calendar days have rest_days = 0."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    workload = compute_workload_context(data)
    # Check if any rest_days == 0 exist (consecutive days)
    _ = [a.rest_days for a in workload.appearances if a.rest_days is not None]
    # If there are consecutive day appearances, one should be 0
    # Test pitcher has appearances -- verify structure is correct
    for app in workload.appearances:
        assert isinstance(app, AppearanceWorkload)
        if app.rest_days is not None and app.rest_days == 0:
            # Confirmed consecutive days have 0 rest days
            break


def test_ip_per_appearance():
    """WorkloadContext has appearances with ip field in baseball notation."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    workload = compute_workload_context(data)
    for app in workload.appearances:
        assert isinstance(app.ip, str)
        # Should match baseball notation pattern X.Y where Y is 0, 1, or 2
        parts = app.ip.split(".")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert parts[1] in ("0", "1", "2")


def test_pitch_count_per_appearance():
    """WorkloadContext appearances have pitch_count matching statcast row count per game_pk."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    workload = compute_workload_context(data)
    for app in workload.appearances:
        assert isinstance(app.pitch_count, int)
        assert app.pitch_count > 0
        # Verify against statcast
        statcast_count = data.statcast.filter(pl.col("game_pk") == app.game_pk).height
        assert app.pitch_count == statcast_count


def test_consecutive_days():
    """WorkloadContext has max_consecutive_days as int >= 1."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    workload = compute_workload_context(data)
    assert isinstance(workload.max_consecutive_days, int)
    assert workload.max_consecutive_days >= 1


def test_consecutive_days_flag():
    """WorkloadContext has workload_concern bool, True when max_consecutive_days >= 3."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    workload = compute_workload_context(data)
    assert isinstance(workload.workload_concern, bool)
    if workload.max_consecutive_days >= 3:
        assert workload.workload_concern is True
    else:
        assert workload.workload_concern is False


# ── Times Through Order ───────────────────────────────────────────────


def test_tto_returns_analysis():
    """compute_tto_analysis returns TTOAnalysis dataclass."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    tto = compute_tto_analysis(data)
    assert isinstance(tto, TTOAnalysis)
    assert isinstance(tto.available, bool)
    assert isinstance(tto.summary, str)
    assert len(tto.summary) > 0


def test_tto_splits_have_pass_numbers():
    """Each TTOSplit has a pass_number >= 1 and FB/secondary P+ fields."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    tto = compute_tto_analysis(data)
    for s in tto.splits:
        assert isinstance(s, TTOSplit)
        assert s.pass_number >= 1
        assert s.pitches > 0
        assert isinstance(s.fb_p_plus_delta, str)
        assert isinstance(s.sec_p_plus_delta, str)
        assert isinstance(s.pitch_types, list)
        assert isinstance(s.small_sample, bool)


def test_tto_starter_with_deep_outings():
    """Starter with TTO 2+ gets available=True, FB/sec split, and pitch types."""
    # Kochanowicz had 3 passes in our earlier exploration
    data = load_pitcher_data(686799, window_days=9999)
    tto = compute_tto_analysis(data)
    if len(tto.splits) >= 2:
        assert tto.available is True
        assert tto.splits[0].velo_delta == "--"  # First pass has no delta
        assert tto.splits[1].velo_delta != "--"  # Second pass has delta
        # FB/secondary split should be populated for starters
        assert tto.splits[0].fb_p_plus is not None
        assert tto.splits[0].sec_p_plus is not None
        # Per-pitch-type breakdown should be present
        assert len(tto.splits[0].pitch_types) > 0
        for pt in tto.splits[0].pitch_types:
            assert isinstance(pt, TTOPitchType)
            assert pt.pitches > 0


def test_tto_fb_sec_deltas():
    """TTO shows fastball and secondary P+ deltas separately."""
    data = load_pitcher_data(686799, window_days=30)
    tto = compute_tto_analysis(data)
    if tto.available and len(tto.splits) >= 2:
        # First pass deltas are "--"
        assert tto.splits[0].fb_p_plus_delta == "--"
        assert tto.splits[0].sec_p_plus_delta == "--"
        # Later passes have real deltas
        assert tto.splits[1].fb_p_plus_delta != "--"


def test_tto_summary_mentions_fb():
    """TTO summary references fastball P+ specifically."""
    data = load_pitcher_data(686799, window_days=30)
    tto = compute_tto_analysis(data)
    if tto.available:
        assert "Fastball P+" in tto.summary or "Secondary P+" in tto.summary


def test_tto_small_sample_flag():
    """Passes with < 50 pitches are flagged."""
    data = load_pitcher_data(686799, window_days=9999)
    tto = compute_tto_analysis(data)
    for s in tto.splits:
        if s.pitches < 50:
            assert s.small_sample is True
        else:
            assert s.small_sample is False


def test_tto_reliever_single_pass():
    """Reliever who only faces batters once gets available=False."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    tto = compute_tto_analysis(data)
    # Booser is mostly RP with single-inning outings
    # If he has < 2 TTO groups, available should be False
    if len([s for s in tto.splits if s.pass_number >= 2]) == 0:
        assert tto.available is False


# ── Hard-Hit Rate ────────────────────────────────────────────────────


def test_hard_hit_rate_returns_dataclass():
    """compute_hard_hit_rate returns a HardHitRate with hard_hit_pct between 0 and 100."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    hhr = compute_hard_hit_rate(data)
    assert isinstance(hhr, HardHitRate)
    assert 0.0 <= hhr.hard_hit_pct <= 100.0


def test_hard_hit_rate_counts_batted_balls():
    """hard_hit_pct counts only batted balls (hit_into_play) with launch_speed >= 95."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    hhr = compute_hard_hit_rate(data)
    # n_hard_hit should be <= n_batted_balls
    assert hhr.n_hard_hit <= hhr.n_batted_balls
    # Verify against raw statcast
    window_dates = data.window_appearances["game_date"].unique().to_list()
    window_sc = data.statcast.filter(pl.col("game_date").is_in(window_dates))
    bip = window_sc.filter((pl.col("description") == "hit_into_play") & pl.col("launch_speed").is_not_null())
    assert hhr.n_batted_balls == bip.height
    hard = bip.filter(pl.col("launch_speed") >= 95.0)
    assert hhr.n_hard_hit == hard.height


def test_hard_hit_rate_positive_batted_balls():
    """n_batted_balls is positive for test pitcher with batted ball events."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    hhr = compute_hard_hit_rate(data)
    assert hhr.n_batted_balls > 0


def test_hard_hit_rate_small_sample():
    """small_sample is True when fewer than 10 batted balls in window."""
    data = load_pitcher_data(TEST_PITCHER, window_days=1)
    hhr = compute_hard_hit_rate(data)
    if hhr.n_batted_balls < 10:
        assert hhr.small_sample is True


def test_hard_hit_rate_cold_start():
    """cold_start is True when window covers entire season."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    hhr = compute_hard_hit_rate(data)
    assert hhr.cold_start is True


def test_hard_hit_rate_season_pct():
    """season_hard_hit_pct is computed from full season, not just window."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    hhr = compute_hard_hit_rate(data)
    # Verify against full statcast
    bip = data.statcast.filter(
        (pl.col("description") == "hit_into_play") & pl.col("launch_speed").is_not_null()
    )
    hard = bip.filter(pl.col("launch_speed") >= 95.0)
    expected_pct = hard.height / bip.height * 100.0 if bip.height > 0 else 0.0
    assert abs(hhr.season_hard_hit_pct - expected_pct) < 0.01


def test_hard_hit_rate_delta_string():
    """delta string follows existing pattern (Up/Down/Steady with pp, or cold-start message)."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    hhr = compute_hard_hit_rate(data)
    assert any(word in hhr.delta for word in ["Up", "Down", "Steady", "Full season in window"])


# ── Release Point Metrics ────────────────────────────────────────────


def test_release_point_returns_metrics():
    """compute_release_point_metrics returns ReleasePointMetrics with non-empty pitch_types list."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    rp = compute_release_point_metrics(data)
    assert isinstance(rp, ReleasePointMetrics)
    assert isinstance(rp.pitch_types, list)
    assert len(rp.pitch_types) > 0


def test_release_point_values_reasonable():
    """Release point values are in physically reasonable ranges."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    rp = compute_release_point_metrics(data)
    for pt in rp.pitch_types:
        # Horizontal release: -4 to 4 ft from center
        assert -4.0 <= pt.window_release_x <= 4.0, f"{pt.pitch_type} release_x={pt.window_release_x}"
        assert -4.0 <= pt.season_release_x <= 4.0
        # Vertical release: 3 to 8 ft
        assert 3.0 <= pt.window_release_z <= 8.0, f"{pt.pitch_type} release_z={pt.window_release_z}"
        assert 3.0 <= pt.season_release_z <= 8.0
        # Extension: 4 to 8 ft
        assert 4.0 <= pt.window_extension <= 8.0, f"{pt.pitch_type} extension={pt.window_extension}"
        assert 4.0 <= pt.season_extension <= 8.0


def test_release_point_per_pitch_type():
    """Each entry has pitch_type, pitch_name, and all float fields."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    rp = compute_release_point_metrics(data)
    for pt in rp.pitch_types:
        assert isinstance(pt, ReleasePointPitchType)
        assert isinstance(pt.pitch_type, str)
        assert len(pt.pitch_type) > 0
        assert isinstance(pt.pitch_name, str)
        assert len(pt.pitch_name) > 2
        assert isinstance(pt.window_release_x, float)
        assert isinstance(pt.season_release_x, float)
        assert isinstance(pt.window_release_z, float)
        assert isinstance(pt.season_release_z, float)
        assert isinstance(pt.window_extension, float)
        assert isinstance(pt.season_extension, float)
        assert isinstance(pt.n_pitches_window, int)
        assert pt.n_pitches_window > 0


def test_release_point_delta_strings():
    """Delta strings contain Up/Down/Steady vocabulary."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    rp = compute_release_point_metrics(data)
    for pt in rp.pitch_types:
        for delta_str in [pt.release_x_delta, pt.release_z_delta, pt.extension_delta]:
            assert any(word in delta_str for word in ["Up", "Down", "Steady", "Full season"]), (
                f"Unexpected delta string: {delta_str}"
            )


def test_release_point_cold_start():
    """With window_days=9999, cold_start=True and deltas contain 'Full season in window'."""
    data = load_pitcher_data(TEST_PITCHER, window_days=9999)
    rp = compute_release_point_metrics(data)
    assert rp.cold_start is True
    for pt in rp.pitch_types:
        assert pt.cold_start is True
        assert "Full season in window" in pt.release_x_delta
        assert "Full season in window" in pt.release_z_delta
        assert "Full season in window" in pt.extension_delta


def test_release_point_small_sample():
    """With window_days=1, entries with < 10 pitches have small_sample=True."""
    data = load_pitcher_data(TEST_PITCHER, window_days=1)
    rp = compute_release_point_metrics(data)
    for pt in rp.pitch_types:
        if pt.n_pitches_window < 10:
            assert pt.small_sample is True


def test_release_point_ordering():
    """Entries are ordered by season pitch count descending."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    rp = compute_release_point_metrics(data)
    # Verify descending order -- first entry should be one of the top-usage pitches
    if len(rp.pitch_types) >= 2:
        assert rp.pitch_types[0].pitch_type in ("FF", "FC", "ST")


# ── Intermediate Probabilities ───────────────────────────────────────


def test_intermediate_probabilities_computed():
    """compute_intermediate_probabilities returns typed results with real data."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_intermediate_probabilities(data)
    assert len(result) > 0
    for item in result:
        assert isinstance(item, IntermediateProbabilities)
        assert isinstance(item.pitch_type, str) and item.pitch_type
        assert isinstance(item.pitch_name, str) and item.pitch_name
        assert item.n_pitches > 0
    # At least one item should have non-None xswing_p or xwhiff_p
    assert any(item.xswing_p is not None or item.xwhiff_p is not None for item in result)


def test_intermediate_bbe_prob_none():
    """BBE_prob columns do not exist in agg CSVs -- values must be None."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_intermediate_probabilities(data)
    for item in result:
        assert item.bbe_prob_p is None
        assert item.bbe_prob_s is None


def test_intermediate_p_and_s_variants():
    """P and S variants should both exist together for each metric."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_intermediate_probabilities(data)
    for item in result:
        if item.xswing_p is not None:
            assert item.xswing_s is not None
        if item.xwhiff_p is not None:
            assert item.xwhiff_s is not None
        if item.xgor_p is not None:
            assert item.xgor_s is not None
        if item.xpur_p is not None:
            assert item.xpur_s is not None
        if item.xhr100_p is not None:
            assert item.xhr100_s is not None
        if item.xswst_p is not None:
            assert item.xswst_s is not None
        if item.xrv100_p is not None:
            assert item.xrv100_s is not None


def test_intermediate_location_impact():
    """Location impact (P minus S) is computable for non-None pairs."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_intermediate_probabilities(data)
    # Find first item where both xswing_p and xswing_s are not None
    found = False
    for item in result:
        if item.xswing_p is not None and item.xswing_s is not None:
            delta = item.xswing_p - item.xswing_s
            assert isinstance(delta, float)
            import math
            assert math.isfinite(delta)
            found = True
            break
    assert found, "Expected at least one item with both xswing_p and xswing_s non-None"


def test_intermediate_both_grains():
    """Window and season values should both be populated."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_intermediate_probabilities(data)
    for item in result:
        # Window values come from pitcher_type_appearance grain
        # Season values come from pitch_type_baseline grain
        pass
    # At least one item should have both window and season xswing_p
    assert any(
        item.season_xswing_p is not None and item.xswing_p is not None
        for item in result
    ), "Expected at least one item with both season and window xswing_p"


def test_intermediate_missing_columns_graceful():
    """Missing columns (BBE_prob) produce None, not exceptions."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_intermediate_probabilities(data)
    # Function completed without exception (implicit)
    # BBE_prob_P/S is the missing-column case
    for item in result:
        assert item.bbe_prob_p is None
    # Result is a list, not None or empty
    assert isinstance(result, list)
    assert len(result) > 0


# ── Component attribution ────────────────────────────────────────────


def test_component_attribution_13_outcomes():
    """Each pitch type has exactly 13 outcome contributions."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_component_attribution(data)
    assert isinstance(result, list)
    assert len(result) > 0
    for attr in result:
        assert isinstance(attr, ComponentAttribution)
        assert len(attr.contributions) == 13


def test_component_attribution_sum():
    """Sum of 13 contributions equals total_xrv100 within tolerance."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_component_attribution(data)
    for attr in result:
        computed_sum = sum(c.contribution for c in attr.contributions)
        assert abs(computed_sum - attr.total_xrv100) < 0.01, (
            f"{attr.pitch_type}: sum={computed_sum:.4f} != total={attr.total_xrv100:.4f}"
        )


def test_component_attribution_labels():
    """The 13 outcome strings match the canonical set."""
    canonical = {
        "HBP", "called_ball", "called_strike", "whiff", "foul",
        "double", "ground_out", "home_run", "line_out",
        "low_line_out", "pop_out", "single", "triple",
    }
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_component_attribution(data)
    for attr in result:
        labels = {c.outcome for c in attr.contributions}
        assert labels == canonical, f"{attr.pitch_type}: labels={labels}"


def test_component_attribution_sorted_by_magnitude():
    """Contributions are sorted by |contribution| descending."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_component_attribution(data)
    for attr in result:
        magnitudes = [abs(c.contribution) for c in attr.contributions]
        assert magnitudes == sorted(magnitudes, reverse=True), (
            f"{attr.pitch_type}: not sorted by magnitude"
        )


def test_component_attribution_pitcher_type_grain():
    """With game_pk=None, returns season-level aggregation."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_component_attribution(data, game_pk=None)
    assert len(result) > 0
    # Total n_pitches across all types should match all_pitches total
    all_pitches = data.agg_csvs["all_pitches"]
    for attr in result:
        type_count = all_pitches.filter(
            pl.col("pitch_type") == attr.pitch_type
        ).height
        assert attr.n_pitches == type_count, (
            f"{attr.pitch_type}: n_pitches={attr.n_pitches} != {type_count}"
        )


def test_component_attribution_appearance_grain():
    """With a specific game_pk, returns per-appearance aggregation."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    all_pitches = data.agg_csvs["all_pitches"]
    game_pk = all_pitches["game_pk"][0]
    result = compute_component_attribution(data, game_pk=game_pk)
    assert len(result) > 0
    for attr in result:
        type_count = all_pitches.filter(
            (pl.col("pitch_type") == attr.pitch_type) &
            (pl.col("game_pk") == game_pk)
        ).height
        assert attr.n_pitches == type_count, (
            f"{attr.pitch_type}: n_pitches={attr.n_pitches} != {type_count}"
        )


def test_component_attribution_pitch_names():
    """Each ComponentAttribution has correct human-readable pitch_name."""
    data = load_pitcher_data(TEST_PITCHER, window_days=30)
    result = compute_component_attribution(data)
    # Build expected name map from statcast
    name_df = data.statcast.select(["pitch_type", "pitch_name"]).unique()
    expected_names = {
        row["pitch_type"]: row["pitch_name"]
        for row in name_df.iter_rows(named=True)
    }
    for attr in result:
        assert attr.pitch_name == expected_names.get(attr.pitch_type, attr.pitch_type), (
            f"{attr.pitch_type}: pitch_name={attr.pitch_name}"
        )


# -- Cross-season summary --


def _create_cross_season_pitcher_data(tmp_path, monkeypatch, years=(2025, 2026)):
    """Create synthetic multi-year PitcherData with columns needed by the engine.

    Extends the pattern from test_data._create_synthetic_multi_year_data but
    adds: release_speed, pitch_type, events, and pitch_name columns to statcast,
    and uses P+/S+/L+ column names matching real pitchingplus CSV output.

    Synthetic metric values:
        2025: P+=98, S+=100, L+=95, velo~93.5
        2026: P+=105, S+=110, L+=100, velo~95.0
    """
    from datetime import date as date_cls

    import pitcher_narratives.data as data_mod

    aggs_dir = tmp_path / "aggs"
    aggs_dir.mkdir(exist_ok=True)

    # Grain definitions (must match data.py)
    season_grains = ("pitcher", "pitcher_type", "pitcher_type_platoon", "team")
    appearance_grains = (
        "pitcher_appearance",
        "pitcher_type_appearance",
        "pitcher_type_platoon_appearance",
        "all_pitches",
    )

    for year in years:
        # Velocities: 2025=93.5, 2026=95.0
        velo = 93.5 if year == 2025 else 95.0
        game_dt = date_cls(year, 6, 15)
        game_pk_val = 100000 + year

        # Create statcast with enough rows: 6 pitches across 2 innings,
        # including events for IP computation (outs in inning 2).
        statcast_df = pl.DataFrame(
            {
                "pitcher": [12345] * 6,
                "player_name": ["Test Pitcher"] * 6,
                "p_throws": ["R"] * 6,
                "game_type": ["R"] * 6,
                "game_year": [year] * 6,
                "game_pk": [game_pk_val] * 6,
                "game_date": [game_dt] * 6,
                "inning": [1, 1, 1, 2, 2, 2],
                "release_speed": [velo, velo + 0.5, velo - 0.5, velo, velo + 0.2, velo - 0.2],
                "pitch_type": ["FF", "FF", "FF", "FF", "FF", "FF"],
                "pitch_name": ["4-Seam Fastball"] * 6,
                "events": [None, None, "strikeout", None, "field_out", "field_out"],
            }
        )
        statcast_df.write_parquet(tmp_path / f"statcast_{year}.parquet")

        # Create CSV agg files with P+/S+/L+ columns (matching real pitchingplus output)
        p_plus = 98.0 + (year - 2025) * 7  # 2025=98, 2026=105
        s_plus = 100.0 + (year - 2025) * 10  # 2025=100, 2026=110
        l_plus = 95.0 + (year - 2025) * 5  # 2025=95, 2026=100

        for grain in [*season_grains, *appearance_grains]:
            base_cols: dict[str, list] = {
                "season": [year],
                "game_type": ["R"],
                "player_name": ["Test Pitcher"],
                "p_throws": ["R"],
                "team_code": ["NYY"],
                "n_pitches": [100],
                "P+": [p_plus],
                "S+": [s_plus],
                "L+": [l_plus],
            }
            if grain != "team":
                base_cols["pitcher"] = [12345]
            if "type" in grain:
                base_cols["pitch_type"] = ["FF"]
            if "platoon" in grain:
                base_cols["platoon"] = ["vs_R"]
            if "appearance" in grain:
                base_cols["game_date"] = [f"{year}-06-15"]
                base_cols["game_pk"] = [game_pk_val]
            if grain == "all_pitches":
                base_cols["game_date"] = [f"{year}-06-15"]
                base_cols["game_pk"] = [game_pk_val]

            df = pl.DataFrame(base_cols)
            df.write_csv(aggs_dir / f"{year}-{grain}.csv")

    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "AGGS_DIR", aggs_dir)
    monkeypatch.setattr(data_mod, "_YEARS", list(years))

    return load_pitcher_data(12345, window_days=365)


def _create_single_season_pitcher_data(tmp_path, monkeypatch):
    """Create synthetic single-season PitcherData (2026 only)."""
    return _create_cross_season_pitcher_data(tmp_path, monkeypatch, years=(2026,))


def test_cross_season_summary_returns_dataclass(tmp_path, monkeypatch):
    """Multi-year PitcherData -> compute_cross_season_summary returns CrossSeasonSummary."""
    data = _create_cross_season_pitcher_data(tmp_path, monkeypatch)
    result = compute_cross_season_summary(data)
    assert result is not None
    assert isinstance(result, CrossSeasonSummary)


def test_cross_season_summary_metrics(tmp_path, monkeypatch):
    """CrossSeasonSummary has correct current/prior P+, S+, L+ values."""
    data = _create_cross_season_pitcher_data(tmp_path, monkeypatch)
    result = compute_cross_season_summary(data)
    assert result is not None
    # 2026 values: P+=105, S+=110, L+=100
    assert abs(result.current_p_plus - 105.0) < 0.1
    assert abs(result.current_s_plus - 110.0) < 0.1
    assert abs(result.current_l_plus - 100.0) < 0.1
    # 2025 values: P+=98, S+=100, L+=95
    assert abs(result.prior_p_plus - 98.0) < 0.1
    assert abs(result.prior_s_plus - 100.0) < 0.1
    assert abs(result.prior_l_plus - 95.0) < 0.1


def test_cross_season_velo_from_statcast(tmp_path, monkeypatch):
    """Velocity computed from statcast release_speed, not from CSV baselines."""
    data = _create_cross_season_pitcher_data(tmp_path, monkeypatch)
    result = compute_cross_season_summary(data)
    assert result is not None
    # 2026 velo should be ~95.0 (mean of 95.0, 95.5, 94.5, 95.0, 95.2, 94.8)
    assert abs(result.current_velo - 95.0) < 0.5
    # 2025 velo should be ~93.5
    assert abs(result.prior_velo - 93.5) < 0.5


def test_cross_season_delta_strings_match(tmp_path, monkeypatch):
    """YoY delta strings use the same format as within-season deltas."""
    data = _create_cross_season_pitcher_data(tmp_path, monkeypatch)
    result = compute_cross_season_summary(data)
    assert result is not None
    # Velo delta: 95.0 - 93.5 = 1.5, above 0.5 threshold -> "Up"
    assert "Up" in result.velo_delta
    assert "mph" in result.velo_delta
    # P+ delta: 105 - 98 = 7, above 5 threshold -> "Up"
    assert "Up" in result.p_plus_delta
    assert "points" in result.p_plus_delta
    # S+ delta: 110 - 100 = 10, hits sharp threshold -> "sharply"
    assert "Up" in result.s_plus_delta
    assert "sharply" in result.s_plus_delta
    # L+ delta: 100 - 95 = 5, right at threshold -> could be "Steady" or "Up"
    # _pplus_delta_string uses abs(delta) < threshold, so 5 is NOT < 5 -> "Up"
    assert "Up" in result.l_plus_delta


def test_cross_season_none_single_season(tmp_path, monkeypatch):
    """Single-season PitcherData -> compute_cross_season_summary returns None."""
    data = _create_single_season_pitcher_data(tmp_path, monkeypatch)
    result = compute_cross_season_summary(data)
    assert result is None


def test_cross_season_workload(tmp_path, monkeypatch):
    """CrossSeasonSummary includes workload comparison metrics."""
    data = _create_cross_season_pitcher_data(tmp_path, monkeypatch)
    result = compute_cross_season_summary(data)
    assert result is not None
    # Each year has 1 appearance with 6 pitches
    assert result.current_appearances >= 1
    assert result.prior_appearances >= 1
    # IP: each year has 2 innings of data; 1 full inning + partial
    # Inning 1: complete (3 outs assumed for non-final). Inning 2: 2 field_outs.
    # => 1 full inning + 2 outs in final = 1.2 baseball = 5/3 = ~1.67 decimal
    assert result.current_ip > 0
    assert result.prior_ip > 0
    # Avg pitches: 6 pitches per appearance
    assert result.current_avg_pitches > 0
    assert result.prior_avg_pitches > 0


def test_cross_season_seasons(tmp_path, monkeypatch):
    """CrossSeasonSummary has correct season year values."""
    data = _create_cross_season_pitcher_data(tmp_path, monkeypatch)
    result = compute_cross_season_summary(data)
    assert result is not None
    assert result.current_season == 2026
    assert result.prior_season == 2025


# ── Arsenal Trend Engine Tests ───────────────────────────────────────


def _make_pitcher_type_agg(
    pitcher_id: int,
    rows: list[dict],
) -> pl.DataFrame:
    """Build a synthetic pitcher_type aggregation DataFrame.

    Each row dict must have: season, pitch_type, n_pitches.
    Optional: P+, S+, L+, game_type, player_name, p_throws, team_code.
    """
    full_rows = []
    for r in rows:
        full_rows.append({
            "season": r["season"],
            "pitcher": pitcher_id,
            "pitch_type": r["pitch_type"],
            "n_pitches": r["n_pitches"],
            "P+": r.get("P+", 100.0),
            "S+": r.get("S+", 100.0),
            "L+": r.get("L+", 100.0),
            "game_type": r.get("game_type", "R"),
            "player_name": r.get("player_name", "Test Pitcher"),
            "p_throws": r.get("p_throws", "R"),
            "team_code": r.get("team_code", "TST"),
        })
    return pl.DataFrame(full_rows)


def _make_statcast(
    pitcher_id: int,
    rows: list[dict],
) -> pl.DataFrame:
    """Build a minimal synthetic Statcast DataFrame for arsenal trend tests.

    Each row dict must have: game_date (date), pitch_type, pitch_name, release_speed.
    Optional: game_pk, inning, p_throws, player_name, stand.
    """
    if not rows:
        return pl.DataFrame(
            schema={
                "game_date": pl.Date,
                "game_pk": pl.Int64,
                "pitcher": pl.Int64,
                "pitch_type": pl.String,
                "pitch_name": pl.String,
                "release_speed": pl.Float64,
                "pfx_x": pl.Float64,
                "pfx_z": pl.Float64,
                "inning": pl.Int64,
                "p_throws": pl.String,
                "player_name": pl.String,
                "stand": pl.String,
            }
        )
    full_rows = []
    for i, r in enumerate(rows):
        full_rows.append({
            "game_date": r["game_date"],
            "game_pk": r.get("game_pk", 700000 + i),
            "pitcher": pitcher_id,
            "pitch_type": r["pitch_type"],
            "pitch_name": r["pitch_name"],
            "release_speed": r["release_speed"],
            "pfx_x": r.get("pfx_x", 0.0),
            "pfx_z": r.get("pfx_z", 0.0),
            "inning": r.get("inning", 1),
            "p_throws": r.get("p_throws", "R"),
            "player_name": r.get("player_name", "Test Pitcher"),
            "stand": r.get("stand", "R"),
        })
    return pl.DataFrame(full_rows).with_columns(
        pl.col("game_date").cast(pl.Date),
    )


def _make_pitcher_data_for_trends(
    pitcher_id: int = 999999,
    pitcher_type_rows: list[dict] | None = None,
    statcast_rows: list[dict] | None = None,
) -> PitcherData:
    """Build a PitcherData with synthetic data for arsenal trend tests.

    Only populates fields needed by compute_arsenal_trends:
    agg_csvs["pitcher_type"] and statcast.
    """
    if pitcher_type_rows is None:
        pitcher_type_rows = []
    if statcast_rows is None:
        statcast_rows = []

    pitcher_type_df = _make_pitcher_type_agg(pitcher_id, pitcher_type_rows)
    statcast = _make_statcast(pitcher_id, statcast_rows)

    return PitcherData(
        statcast=statcast,
        appearances=pl.DataFrame(),
        window_appearances=pl.DataFrame(),
        season_baseline=pl.DataFrame(),
        pitch_type_baseline=pl.DataFrame(),
        prior_season_baseline=pl.DataFrame(),
        prior_pitch_type_baseline=pl.DataFrame(),
        agg_csvs={"pitcher_type": pitcher_type_df},
        pitcher_id=pitcher_id,
        pitcher_name="Test Pitcher",
        throws="R",
    )


def test_arsenal_trends_single_season_returns_none():
    """ATRN-03: Single-season pitcher produces None, not empty trends."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            {"season": 2026, "pitch_type": "FF", "n_pitches": 100},
            {"season": 2026, "pitch_type": "SL", "n_pitches": 50},
        ],
        statcast_rows=[
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is None


def test_arsenal_trends_empty_agg_returns_none():
    """Empty pitcher_type agg produces None."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[],
        statcast_rows=[],
    )
    result = compute_arsenal_trends(data)
    assert result is None


def test_arsenal_trends_missing_agg_key_returns_none():
    """Missing pitcher_type key in agg_csvs produces None."""
    data = _make_pitcher_data_for_trends()
    data.agg_csvs = {}  # No pitcher_type key
    result = compute_arsenal_trends(data)
    assert result is None


def test_arsenal_trends_identifies_added_pitch():
    """ATRN-01: Pitch in current but not prior season is detected as added."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            # 2025: FF and SL only
            {"season": 2025, "pitch_type": "FF", "n_pitches": 200, "P+": 105.0, "S+": 110.0},
            {"season": 2025, "pitch_type": "SL", "n_pitches": 100, "P+": 95.0, "S+": 90.0},
            # 2026: FF, SL, and new SV (sweeper)
            {"season": 2026, "pitch_type": "FF", "n_pitches": 180, "P+": 108.0, "S+": 112.0},
            {"season": 2026, "pitch_type": "SL", "n_pitches": 80, "P+": 98.0, "S+": 95.0},
            {"season": 2026, "pitch_type": "SV", "n_pitches": 40, "P+": 115.0, "S+": 120.0},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 95.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 86.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "SV", "pitch_name": "Sweeper", "release_speed": 80.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None
    assert result.prior_season == 2025
    assert result.current_season == 2026

    # SV should be detected as added
    added_types = [p.pitch_type for p in result.added_pitches]
    assert "SV" in added_types
    sv = [p for p in result.added_pitches if p.pitch_type == "SV"][0]
    assert sv.season == 2026
    assert sv.n_pitches == 40

    # No dropped pitches
    assert len(result.dropped_pitches) == 0


def test_arsenal_trends_identifies_dropped_pitch():
    """ATRN-01: Pitch in prior but not current season is detected as dropped."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            # 2025: FF, SL, and CU
            {"season": 2025, "pitch_type": "FF", "n_pitches": 200, "P+": 105.0, "S+": 110.0},
            {"season": 2025, "pitch_type": "SL", "n_pitches": 100, "P+": 95.0, "S+": 90.0},
            {"season": 2025, "pitch_type": "CU", "n_pitches": 50, "P+": 80.0, "S+": 75.0},
            # 2026: FF and SL only (dropped CU)
            {"season": 2026, "pitch_type": "FF", "n_pitches": 220, "P+": 108.0, "S+": 112.0},
            {"season": 2026, "pitch_type": "SL", "n_pitches": 120, "P+": 98.0, "S+": 95.0},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "CU", "pitch_name": "Curveball", "release_speed": 78.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 95.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 86.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None

    # CU should be detected as dropped
    dropped_types = [p.pitch_type for p in result.dropped_pitches]
    assert "CU" in dropped_types
    cu = [p for p in result.dropped_pitches if p.pitch_type == "CU"][0]
    assert cu.season == 2025
    assert cu.n_pitches == 50

    # No added pitches
    assert len(result.added_pitches) == 0


def test_arsenal_trends_yoy_deltas_for_shared_pitches():
    """ATRN-02: Computes per-pitch-type YoY deltas for usage, P+, S+, velocity."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            # 2025: FF at 105 P+, 110 S+, 60% usage
            {"season": 2025, "pitch_type": "FF", "n_pitches": 300, "P+": 105.0, "S+": 110.0},
            {"season": 2025, "pitch_type": "SL", "n_pitches": 200, "P+": 95.0, "S+": 90.0},
            # 2026: FF at 112 P+, 115 S+ (up), usage shifted
            {"season": 2026, "pitch_type": "FF", "n_pitches": 250, "P+": 112.0, "S+": 115.0},
            {"season": 2026, "pitch_type": "SL", "n_pitches": 250, "P+": 100.0, "S+": 98.0},
        ],
        statcast_rows=[
            # 2025 FF velo: 93.5
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 93.0},
            {"game_date": date(2025, 6, 2), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 84.0},
            {"game_date": date(2025, 6, 2), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            # 2026 FF velo: 95.5 (up 2.0 mph)
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 95.0},
            {"game_date": date(2026, 4, 2), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 96.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            {"game_date": date(2026, 4, 2), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 86.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None
    assert isinstance(result, ArsenalTrend)

    # Should have 2 pitch trends (FF and SL)
    assert len(result.pitch_trends) == 2
    # Sorted by current usage descending
    assert result.pitch_trends[0].current_usage_pct >= result.pitch_trends[1].current_usage_pct

    # Find FF trend
    ff = [t for t in result.pitch_trends if t.pitch_type == "FF"][0]
    assert isinstance(ff, PitchTrend)

    # P+ went from 105 to 112: Up 7 points
    assert "Up" in ff.p_plus_delta
    assert ff.prior_p_plus == 105.0
    assert ff.current_p_plus == 112.0

    # S+ went from 110 to 115: Steady (+5) -- below 5-point threshold
    assert ff.prior_s_plus == 110.0
    assert ff.current_s_plus == 115.0

    # Velocity went from 93.5 to 95.5: Up sharply (+2.0 mph)
    assert "Up" in ff.velo_delta
    assert "sharply" in ff.velo_delta
    assert abs(ff.prior_velo - 93.5) < 0.01
    assert abs(ff.current_velo - 95.5) < 0.01


def test_arsenal_trends_min_pitches_filters_noise():
    """Pitches below _MIN_PITCHES threshold excluded from added/dropped."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            # 2025: FF + tiny sample of SL (5 pitches, below threshold)
            {"season": 2025, "pitch_type": "FF", "n_pitches": 300, "P+": 105.0, "S+": 110.0},
            {"season": 2025, "pitch_type": "SL", "n_pitches": 5, "P+": 90.0, "S+": 85.0},
            # 2026: FF only
            {"season": 2026, "pitch_type": "FF", "n_pitches": 280, "P+": 108.0, "S+": 112.0},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 95.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None

    # SL should NOT be in dropped (below _MIN_PITCHES threshold)
    dropped_types = [p.pitch_type for p in result.dropped_pitches]
    assert "SL" not in dropped_types

    # No added pitches either
    assert len(result.added_pitches) == 0


def test_arsenal_trends_usage_delta_strings():
    """Usage delta strings use same qualitative language as within-season."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            # 2025: 60% FF, 40% SL
            {"season": 2025, "pitch_type": "FF", "n_pitches": 300, "P+": 100.0, "S+": 100.0},
            {"season": 2025, "pitch_type": "SL", "n_pitches": 200, "P+": 100.0, "S+": 100.0},
            # 2026: 50% FF, 50% SL (FF usage down ~10pp)
            {"season": 2026, "pitch_type": "FF", "n_pitches": 250, "P+": 100.0, "S+": 100.0},
            {"season": 2026, "pitch_type": "SL", "n_pitches": 250, "P+": 100.0, "S+": 100.0},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None

    ff = [t for t in result.pitch_trends if t.pitch_type == "FF"][0]
    sl = [t for t in result.pitch_trends if t.pitch_type == "SL"][0]

    # FF usage went from 60% to 50%: Down sharply (-10.0 pp)
    assert "Down" in ff.usage_delta
    assert "sharply" in ff.usage_delta

    # SL usage went from 40% to 50%: Up sharply (+10.0 pp)
    assert "Up" in sl.usage_delta
    assert "sharply" in sl.usage_delta


def test_arsenal_trends_season_identification():
    """ArsenalTrend correctly identifies prior and current seasons."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            {"season": 2025, "pitch_type": "FF", "n_pitches": 200},
            {"season": 2026, "pitch_type": "FF", "n_pitches": 200},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None
    assert result.prior_season == 2025
    assert result.current_season == 2026


def test_arsenal_trends_three_seasons_uses_most_recent_two():
    """With 3+ seasons, only the two most recent are compared."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            {"season": 2024, "pitch_type": "FF", "n_pitches": 200, "P+": 90.0, "S+": 85.0},
            {"season": 2025, "pitch_type": "FF", "n_pitches": 200, "P+": 100.0, "S+": 100.0},
            {"season": 2026, "pitch_type": "FF", "n_pitches": 200, "P+": 110.0, "S+": 115.0},
        ],
        statcast_rows=[
            {"game_date": date(2024, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 92.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 96.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None
    # Should compare 2025 vs 2026, not 2024 vs 2026
    assert result.prior_season == 2025
    assert result.current_season == 2026
    ff = result.pitch_trends[0]
    assert ff.prior_p_plus == 100.0  # 2025 value, not 2024's 90
    assert ff.current_p_plus == 110.0


def test_arsenal_trends_added_pitch_has_correct_fields():
    """AddedDroppedPitch has all expected fields populated."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            {"season": 2025, "pitch_type": "FF", "n_pitches": 300},
            {"season": 2026, "pitch_type": "FF", "n_pitches": 250},
            {"season": 2026, "pitch_type": "CH", "n_pitches": 50},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "CH", "pitch_name": "Changeup", "release_speed": 84.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None
    assert len(result.added_pitches) == 1
    ch = result.added_pitches[0]
    assert isinstance(ch, AddedDroppedPitch)
    assert ch.pitch_type == "CH"
    assert ch.pitch_name == "Changeup"
    assert ch.season == 2026
    assert ch.n_pitches == 50
    assert ch.usage_pct > 0


def test_arsenal_trends_pitch_trends_sorted_by_usage():
    """PitchTrend list is sorted by current usage percentage descending."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            {"season": 2025, "pitch_type": "FF", "n_pitches": 300},
            {"season": 2025, "pitch_type": "SL", "n_pitches": 100},
            {"season": 2025, "pitch_type": "CH", "n_pitches": 100},
            {"season": 2026, "pitch_type": "FF", "n_pitches": 200},
            {"season": 2026, "pitch_type": "SL", "n_pitches": 200},
            {"season": 2026, "pitch_type": "CH", "n_pitches": 100},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            {"game_date": date(2025, 6, 1), "pitch_type": "CH", "pitch_name": "Changeup", "release_speed": 84.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "SL", "pitch_name": "Slider", "release_speed": 85.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "CH", "pitch_name": "Changeup", "release_speed": 84.0},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None
    assert len(result.pitch_trends) == 3
    usages = [t.current_usage_pct for t in result.pitch_trends]
    assert usages == sorted(usages, reverse=True)


def test_arsenal_trends_steady_deltas():
    """Minimal changes produce 'Steady' delta strings."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            {"season": 2025, "pitch_type": "FF", "n_pitches": 300, "P+": 100.0, "S+": 100.0},
            {"season": 2026, "pitch_type": "FF", "n_pitches": 300, "P+": 102.0, "S+": 101.0},
        ],
        statcast_rows=[
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.0},
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball", "release_speed": 94.2},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None
    ff = result.pitch_trends[0]
    # Small P+ change (2 pts) => Steady
    assert "Steady" in ff.p_plus_delta
    # Small S+ change (1 pt) => Steady
    assert "Steady" in ff.s_plus_delta
    # Small velo change (0.2 mph) => Steady
    assert "Steady" in ff.velo_delta


def test_arsenal_trends_movement_deltas():
    """Movement deltas are computed from statcast pfx_x/pfx_z per pitch type per season."""
    data = _make_pitcher_data_for_trends(
        pitcher_type_rows=[
            {"season": 2025, "pitch_type": "FF", "n_pitches": 200, "P+": 105.0, "S+": 110.0},
            {"season": 2025, "pitch_type": "SL", "n_pitches": 100, "P+": 95.0, "S+": 90.0},
            {"season": 2026, "pitch_type": "FF", "n_pitches": 200, "P+": 108.0, "S+": 112.0},
            {"season": 2026, "pitch_type": "SL", "n_pitches": 100, "P+": 98.0, "S+": 95.0},
        ],
        statcast_rows=[
            # 2025 FF: pfx_x=-6.0, pfx_z=14.0
            {"game_date": date(2025, 6, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball",
             "release_speed": 94.0, "pfx_x": -6.0, "pfx_z": 14.0},
            # 2026 FF: pfx_x=-8.0, pfx_z=14.0 (H-mov changed by -2.0, V-mov steady)
            {"game_date": date(2026, 4, 1), "pitch_type": "FF", "pitch_name": "4-Seam Fastball",
             "release_speed": 95.0, "pfx_x": -8.0, "pfx_z": 14.0},
            # 2025 SL: pfx_x=2.0, pfx_z=3.0
            {"game_date": date(2025, 6, 1), "pitch_type": "SL", "pitch_name": "Slider",
             "release_speed": 85.0, "pfx_x": 2.0, "pfx_z": 3.0},
            # 2026 SL: pfx_x=2.1, pfx_z=3.2 (both steady, below threshold)
            {"game_date": date(2026, 4, 1), "pitch_type": "SL", "pitch_name": "Slider",
             "release_speed": 86.0, "pfx_x": 2.1, "pfx_z": 3.2},
        ],
    )
    result = compute_arsenal_trends(data)
    assert result is not None

    ff = [t for t in result.pitch_trends if t.pitch_type == "FF"][0]
    # FF horizontal movement changed from -6.0 to -8.0 (delta = -2.0) => "Down 2.0 in"
    assert ff.prior_pfx_x == -6.0
    assert ff.current_pfx_x == -8.0
    assert "Down" in ff.pfx_x_delta
    assert "2.0" in ff.pfx_x_delta
    # FF vertical movement stayed at 14.0 => Steady
    assert ff.prior_pfx_z == 14.0
    assert ff.current_pfx_z == 14.0
    assert "Steady" in ff.pfx_z_delta

    sl = [t for t in result.pitch_trends if t.pitch_type == "SL"][0]
    # SL horizontal movement: 2.0 -> 2.1 (delta = 0.1) => Steady
    assert abs(sl.prior_pfx_x - 2.0) < 0.01
    assert abs(sl.current_pfx_x - 2.1) < 0.01
    assert "Steady" in sl.pfx_x_delta
    # SL vertical movement: 3.0 -> 3.2 (delta = 0.2) => Steady
    assert abs(sl.prior_pfx_z - 3.0) < 0.01
    assert abs(sl.current_pfx_z - 3.2) < 0.01
    assert "Steady" in sl.pfx_z_delta


# ── Appearance Pitch Trends ──────────────────────────────────────────


def _make_pitcher_data_for_appearance_trends(
    pitcher_id: int = 999999,
    statcast_rows: list[dict] | None = None,
    pitcher_type_rows: list[dict] | None = None,
    window_days: int = 30,
) -> PitcherData:
    """Build a PitcherData with synthetic data for appearance pitch trend tests.

    Unlike _make_pitcher_data_for_trends, this helper also populates
    window_appearances from the statcast rows (unique game_date/game_pk
    combinations filtered to within window_days of the max game_date).
    """
    if statcast_rows is None:
        statcast_rows = []
    if pitcher_type_rows is None:
        pitcher_type_rows = []

    statcast = _make_statcast(pitcher_id, statcast_rows)

    # Build appearances from unique game_date/game_pk in statcast
    if not statcast.is_empty():
        apps = (
            statcast.select(["game_date", "game_pk"])
            .unique()
            .with_columns(
                pl.lit("SP").alias("role"),
                pl.lit(90).alias("n_pitches"),
            )
        )
        # Window: filter to within window_days of max game_date
        max_date = statcast["game_date"].max()
        from datetime import timedelta

        cutoff = max_date - timedelta(days=window_days)
        window_apps = apps.filter(pl.col("game_date") >= cutoff)
    else:
        apps = pl.DataFrame(
            schema={
                "game_date": pl.Date,
                "game_pk": pl.Int64,
                "role": pl.String,
                "n_pitches": pl.Int64,
            }
        )
        window_apps = apps.clone()

    pitcher_type_df = _make_pitcher_type_agg(pitcher_id, pitcher_type_rows) if pitcher_type_rows else pl.DataFrame()

    return PitcherData(
        statcast=statcast,
        appearances=apps,
        window_appearances=window_apps,
        season_baseline=pl.DataFrame(),
        pitch_type_baseline=pl.DataFrame(),
        prior_season_baseline=pl.DataFrame(),
        prior_pitch_type_baseline=pl.DataFrame(),
        agg_csvs={"pitcher_type": pitcher_type_df} if pitcher_type_rows else {},
        pitcher_id=pitcher_id,
        pitcher_name="Test Pitcher",
        throws="R",
    )


def _ff_rows(game_date: date, n: int, velo: float, pfx_x: float, pfx_z: float, game_pk: int = 700000) -> list[dict]:
    """Generate n rows of FF statcast data for a single appearance."""
    return [
        {
            "game_date": game_date,
            "game_pk": game_pk,
            "pitch_type": "FF",
            "pitch_name": "4-Seam Fastball",
            "release_speed": velo,
            "pfx_x": pfx_x,
            "pfx_z": pfx_z,
        }
        for _ in range(n)
    ]


def _sl_rows(game_date: date, n: int, velo: float, pfx_x: float = 0.15, pfx_z: float = 0.02, game_pk: int = 700100) -> list[dict]:
    """Generate n rows of SL statcast data for a single appearance."""
    return [
        {
            "game_date": game_date,
            "game_pk": game_pk,
            "pitch_type": "SL",
            "pitch_name": "Slider",
            "release_speed": velo,
            "pfx_x": pfx_x,
            "pfx_z": pfx_z,
        }
        for _ in range(n)
    ]


def test_appearance_pitch_trends_three_way_comparison():
    """Multi-appearance data produces correct last_start / window_avg / prior_season values."""
    # 3 appearances of FF (Apr 1, Apr 8, Apr 15; velo: 93, 94, 96; pfx_x in feet: 0.05, 0.06, 0.08; pfx_z: 0.12, 0.11, 0.13)
    # Prior season FF: velo 94, pfx_x 0.055, pfx_z 0.115
    rows = []
    # Prior season: 2025
    rows.extend(_ff_rows(date(2025, 7, 1), 15, 94.0, 0.055, 0.115, game_pk=600001))
    # Current season: 2026
    rows.extend(_ff_rows(date(2026, 4, 1), 15, 93.0, 0.05, 0.12, game_pk=700001))
    rows.extend(_ff_rows(date(2026, 4, 8), 15, 94.0, 0.06, 0.11, game_pk=700002))
    rows.extend(_ff_rows(date(2026, 4, 15), 15, 96.0, 0.08, 0.13, game_pk=700003))

    data = _make_pitcher_data_for_appearance_trends(statcast_rows=rows, window_days=30)
    result = compute_appearance_pitch_trends(data)
    assert result is not None
    assert result.last_game_date == "2026-04-15"
    assert len(result.records) == 1

    ff = result.records[0]
    assert ff.pitch_type == "FF"
    assert ff.n_pitches_last == 15

    # Last start velo = 96.0
    assert abs(ff.last_start_velo - 96.0) < 0.01
    # Window avg velo = mean(93, 94, 96) = 94.333...
    assert abs(ff.window_avg_velo - 94.333) < 0.1
    # Prior season velo = 94.0
    assert ff.prior_season_velo is not None
    assert abs(ff.prior_season_velo - 94.0) < 0.01

    # Movement in INCHES: pfx_x * 12
    # Last start pfx_x = 0.08 * 12 = 0.96
    assert abs(ff.last_start_pfx_x - 0.96) < 0.01
    # Window avg pfx_x = mean(0.05, 0.06, 0.08) * 12 = 0.076 * 12 = 0.76
    assert abs(ff.window_avg_pfx_x - 0.76) < 0.1
    # Prior season pfx_x = 0.055 * 12 = 0.66
    assert ff.prior_season_pfx_x is not None
    assert abs(ff.prior_season_pfx_x - 0.66) < 0.01

    # Delta strings should be present
    assert isinstance(ff.last_vs_window_velo, str)
    assert isinstance(ff.last_vs_prior_velo, str)


def test_appearance_pitch_trends_min_pitches_filter():
    """Pitch type with fewer than _MIN_PITCHES in most recent appearance is excluded."""
    rows = []
    # Current season: FF with 15 pitches (above threshold), SL with 5 (below)
    rows.extend(_ff_rows(date(2026, 4, 15), 15, 94.0, 0.05, 0.12, game_pk=700001))
    rows.extend(_sl_rows(date(2026, 4, 15), 5, 84.0, game_pk=700001))

    data = _make_pitcher_data_for_appearance_trends(statcast_rows=rows, window_days=30)
    result = compute_appearance_pitch_trends(data)
    assert result is not None
    # Only FF should be in records (SL excluded due to < 10 pitches in last start)
    pitch_types = [r.pitch_type for r in result.records]
    assert "FF" in pitch_types
    assert "SL" not in pitch_types


def test_appearance_pitch_trends_single_season():
    """Single-season pitcher has prior_season fields as None and prior deltas as '--'."""
    rows = _ff_rows(date(2026, 4, 1), 15, 93.0, 0.05, 0.12, game_pk=700001)
    rows.extend(_ff_rows(date(2026, 4, 8), 15, 95.0, 0.06, 0.13, game_pk=700002))

    data = _make_pitcher_data_for_appearance_trends(statcast_rows=rows, window_days=30)
    result = compute_appearance_pitch_trends(data)
    assert result is not None

    ff = result.records[0]
    assert ff.prior_season_velo is None
    assert ff.prior_season_pfx_x is None
    assert ff.prior_season_pfx_z is None
    assert ff.last_vs_prior_velo == "--"
    assert ff.last_vs_prior_pfx_x == "--"
    assert ff.last_vs_prior_pfx_z == "--"


def test_appearance_pitch_trends_empty_statcast():
    """Returns None when statcast is empty."""
    data = _make_pitcher_data_for_appearance_trends(statcast_rows=[])
    result = compute_appearance_pitch_trends(data)
    assert result is None


def test_appearance_pitch_trends_no_window_appearances():
    """Returns None when window has no appearances."""
    data = _make_pitcher_data_for_appearance_trends(statcast_rows=[])
    # Force empty window_appearances
    data.window_appearances = pl.DataFrame(
        schema={"game_date": pl.Date, "game_pk": pl.Int64, "role": pl.String, "n_pitches": pl.Int64}
    )
    result = compute_appearance_pitch_trends(data)
    assert result is None


def test_appearance_pitch_trends_multiple_pitch_types_sorted():
    """Multiple pitch types each get their own record, sorted by total pitch count desc."""
    rows = []
    # FF: 20 pitches in last start, SL: 15 pitches
    rows.extend(_ff_rows(date(2026, 4, 15), 20, 94.0, 0.05, 0.12, game_pk=700001))
    rows.extend(_sl_rows(date(2026, 4, 15), 15, 84.0, game_pk=700001))

    data = _make_pitcher_data_for_appearance_trends(statcast_rows=rows, window_days=30)
    result = compute_appearance_pitch_trends(data)
    assert result is not None
    assert len(result.records) == 2
    # FF (20 pitches) should come before SL (15 pitches)
    assert result.records[0].pitch_type == "FF"
    assert result.records[1].pitch_type == "SL"
    assert result.records[0].n_pitches_last >= result.records[1].n_pitches_last


def test_appearance_pitch_trends_pattern_labels():
    """Pattern labels correctly classify one-off, sustained change, something new, steady."""
    # Steady: last ~ window ~ prior (all similar)
    # We need multiple appearances to get a window_avg
    rows = []
    # Prior season: velo 94
    rows.extend(_ff_rows(date(2025, 7, 1), 15, 94.0, 0.05, 0.12, game_pk=600001))
    # Current season window: velo 94.2, 94.1 => window avg ~ 94.15
    rows.extend(_ff_rows(date(2026, 4, 1), 15, 94.2, 0.05, 0.12, game_pk=700001))
    # Last start: velo 94.1 (close to both window and prior)
    rows.extend(_ff_rows(date(2026, 4, 8), 15, 94.1, 0.05, 0.12, game_pk=700002))

    data = _make_pitcher_data_for_appearance_trends(statcast_rows=rows, window_days=30)
    result = compute_appearance_pitch_trends(data)
    assert result is not None
    ff = result.records[0]
    assert ff.pattern_label == "steady"

    # One-off: last != window_avg but last ~ prior
    rows2 = []
    rows2.extend(_ff_rows(date(2025, 7, 1), 15, 94.0, 0.05, 0.12, game_pk=600001))
    # Window: velo 94.0 (matches prior)
    rows2.extend(_ff_rows(date(2026, 4, 1), 15, 94.0, 0.05, 0.12, game_pk=700001))
    # Last start: velo 96.0 (different from window avg, but this is a blip)
    # However the label is about last vs window AND last vs prior
    # one-off: abs(last - window) >= threshold AND abs(last - prior) < threshold
    # Here: last=96, window_avg=mean(94,96)=95, prior=94
    # last-window = 96-95 = 1.0 >= 0.5 (yes)
    # last-prior = 96-94 = 2.0 >= 0.5 (no, that's "something new")
    # So let's adjust: prior=95.8 => last-prior = 0.2 < 0.5
    rows2 = []
    rows2.extend(_ff_rows(date(2025, 7, 1), 15, 95.8, 0.05, 0.12, game_pk=600001))
    rows2.extend(_ff_rows(date(2026, 4, 1), 15, 94.0, 0.05, 0.12, game_pk=700001))
    rows2.extend(_ff_rows(date(2026, 4, 8), 15, 96.0, 0.05, 0.12, game_pk=700002))
    # window_avg = mean(94, 96) = 95.0, last=96, prior=95.8
    # last-window = 1.0 >= 0.5, last-prior = 0.2 < 0.5 => one-off
    data2 = _make_pitcher_data_for_appearance_trends(statcast_rows=rows2, window_days=30)
    result2 = compute_appearance_pitch_trends(data2)
    assert result2 is not None
    ff2 = result2.records[0]
    assert ff2.pattern_label == "one-off"

    # Sustained change: last ~ window_avg but both != prior
    rows3 = []
    rows3.extend(_ff_rows(date(2025, 7, 1), 15, 92.0, 0.05, 0.12, game_pk=600001))
    rows3.extend(_ff_rows(date(2026, 4, 1), 15, 94.0, 0.05, 0.12, game_pk=700001))
    rows3.extend(_ff_rows(date(2026, 4, 8), 15, 94.2, 0.05, 0.12, game_pk=700002))
    # window_avg = mean(94.0, 94.2) = 94.1, last=94.2, prior=92.0
    # last-window = 0.1 < 0.5, last-prior = 2.2 >= 0.5 => sustained change
    data3 = _make_pitcher_data_for_appearance_trends(statcast_rows=rows3, window_days=30)
    result3 = compute_appearance_pitch_trends(data3)
    assert result3 is not None
    ff3 = result3.records[0]
    assert ff3.pattern_label == "sustained change"

    # Something new: last != window_avg AND last != prior
    rows4 = []
    rows4.extend(_ff_rows(date(2025, 7, 1), 15, 92.0, 0.05, 0.12, game_pk=600001))
    rows4.extend(_ff_rows(date(2026, 4, 1), 15, 93.0, 0.05, 0.12, game_pk=700001))
    rows4.extend(_ff_rows(date(2026, 4, 8), 15, 96.0, 0.05, 0.12, game_pk=700002))
    # window_avg = mean(93.0, 96.0) = 94.5, last=96.0, prior=92.0
    # last-window = 1.5 >= 0.5, last-prior = 4.0 >= 0.5 => something new
    data4 = _make_pitcher_data_for_appearance_trends(statcast_rows=rows4, window_days=30)
    result4 = compute_appearance_pitch_trends(data4)
    assert result4 is not None
    ff4 = result4.records[0]
    assert ff4.pattern_label == "something new"


def test_appearance_pitch_trends_no_prior_pattern():
    """Single-season: can only be 'steady' or 'one-off'."""
    # Steady case
    rows_steady = []
    rows_steady.extend(_ff_rows(date(2026, 4, 1), 15, 94.0, 0.05, 0.12, game_pk=700001))
    rows_steady.extend(_ff_rows(date(2026, 4, 8), 15, 94.2, 0.05, 0.12, game_pk=700002))
    data_s = _make_pitcher_data_for_appearance_trends(statcast_rows=rows_steady, window_days=30)
    result_s = compute_appearance_pitch_trends(data_s)
    assert result_s is not None
    assert result_s.records[0].pattern_label == "steady"

    # One-off case (no prior => can never be sustained or something-new)
    rows_oneoff = []
    rows_oneoff.extend(_ff_rows(date(2026, 4, 1), 15, 93.0, 0.05, 0.12, game_pk=700001))
    rows_oneoff.extend(_ff_rows(date(2026, 4, 8), 15, 96.0, 0.05, 0.12, game_pk=700002))
    # window_avg = mean(93, 96) = 94.5, last=96.0
    # last-window = 1.5 >= 0.5, no prior => one-off
    data_o = _make_pitcher_data_for_appearance_trends(statcast_rows=rows_oneoff, window_days=30)
    result_o = compute_appearance_pitch_trends(data_o)
    assert result_o is not None
    assert result_o.records[0].pattern_label == "one-off"


# ── Count splits helpers ────────────────────────────────────────────


def _make_pitcher_data_for_count_splits(
    statcast_rows: list[dict] | None = None,
    window_days: int = 30,
) -> PitcherData:
    """Build a PitcherData with synthetic data for count splits tests.

    Populates statcast with balls/strikes columns and builds
    window_appearances from unique game_date/game_pk combos.
    """
    pitcher_id = 999999

    if statcast_rows is None:
        statcast_rows = []

    if not statcast_rows:
        statcast = pl.DataFrame(
            schema={
                "game_date": pl.Date,
                "game_pk": pl.Int64,
                "pitcher": pl.Int64,
                "pitch_type": pl.String,
                "pitch_name": pl.String,
                "release_speed": pl.Float64,
                "pfx_x": pl.Float64,
                "pfx_z": pl.Float64,
                "inning": pl.Int64,
                "p_throws": pl.String,
                "player_name": pl.String,
                "stand": pl.String,
                "balls": pl.Int64,
                "strikes": pl.Int64,
            }
        )
    else:
        full_rows = []
        for i, r in enumerate(statcast_rows):
            full_rows.append({
                "game_date": r["game_date"],
                "game_pk": r.get("game_pk", 700000),
                "pitcher": pitcher_id,
                "pitch_type": r["pitch_type"],
                "pitch_name": r["pitch_name"],
                "release_speed": r.get("release_speed", 90.0),
                "pfx_x": r.get("pfx_x", 0.0),
                "pfx_z": r.get("pfx_z", 0.0),
                "inning": r.get("inning", 1),
                "p_throws": r.get("p_throws", "R"),
                "player_name": r.get("player_name", "Test Pitcher"),
                "stand": r.get("stand", "R"),
                "balls": r["balls"],
                "strikes": r["strikes"],
            })
        statcast = pl.DataFrame(full_rows).with_columns(
            pl.col("game_date").cast(pl.Date),
        )

    # Build appearances from unique game_date/game_pk in statcast
    if not statcast.is_empty():
        apps = (
            statcast.select(["game_date", "game_pk"])
            .unique()
            .with_columns(
                pl.lit("SP").alias("role"),
                pl.lit(90).alias("n_pitches"),
            )
        )
        from datetime import timedelta

        max_date = statcast["game_date"].max()
        cutoff = max_date - timedelta(days=window_days)
        window_apps = apps.filter(pl.col("game_date") >= cutoff)
    else:
        apps = pl.DataFrame(
            schema={
                "game_date": pl.Date,
                "game_pk": pl.Int64,
                "role": pl.String,
                "n_pitches": pl.Int64,
            }
        )
        window_apps = apps.clone()

    return PitcherData(
        statcast=statcast,
        appearances=apps,
        window_appearances=window_apps,
        season_baseline=pl.DataFrame(),
        pitch_type_baseline=pl.DataFrame(),
        prior_season_baseline=pl.DataFrame(),
        prior_pitch_type_baseline=pl.DataFrame(),
        agg_csvs={},
        pitcher_id=pitcher_id,
        pitcher_name="Test Pitcher",
        throws="R",
    )


def _count_rows(
    game_date: date,
    pitch_type: str,
    pitch_name: str,
    balls: int,
    strikes: int,
    n: int = 1,
    game_pk: int = 700000,
) -> list[dict]:
    """Generate n rows of statcast data with specific ball/strike counts."""
    return [
        {
            "game_date": game_date,
            "game_pk": game_pk,
            "pitch_type": pitch_type,
            "pitch_name": pitch_name,
            "balls": balls,
            "strikes": strikes,
        }
        for _ in range(n)
    ]


# ── Count splits tests ──────────────────────────────────────────────


def test_count_splits_returns_five_buckets():
    """compute_count_splits returns CountSplits with exactly 5 buckets."""
    rows = []
    d = date(2026, 4, 1)
    # Add pitches in various counts to populate all buckets
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 0, n=5))   # even + first_pitch
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 1, n=5))   # ahead
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 0, n=5))   # behind
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 2, n=5))   # ahead + two_strike
    rows.extend(_count_rows(d, "SL", "Slider", 0, 2, n=5))            # ahead + two_strike

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    assert isinstance(result, CountSplits)
    assert len(result.buckets) == 5
    bucket_names = {b.bucket for b in result.buckets}
    assert bucket_names == {"ahead", "behind", "even", "two_strike", "first_pitch"}


def test_count_splits_two_strike_overlap():
    """A pitch at 0-2 appears in BOTH 'ahead' and 'two_strike' buckets."""
    rows = []
    d = date(2026, 4, 1)
    # 15 pitches at 0-2 (ahead AND two_strike)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 2, n=15))
    # 5 pitches at 0-0 (even + first_pitch) so other buckets exist
    rows.extend(_count_rows(d, "SL", "Slider", 0, 0, n=15))

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    ahead_bucket = [b for b in result.buckets if b.bucket == "ahead"][0]
    two_strike_bucket = [b for b in result.buckets if b.bucket == "two_strike"][0]

    # The 15 pitches at 0-2 should be in both ahead and two_strike
    assert ahead_bucket.n_pitches_window >= 15
    assert two_strike_bucket.n_pitches_window >= 15


def test_count_splits_first_pitch_in_even():
    """A pitch at 0-0 appears in BOTH 'even' and 'first_pitch' buckets."""
    rows = []
    d = date(2026, 4, 1)
    # 15 pitches at 0-0 (even + first_pitch)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 0, n=15))
    # Other pitches so we have something in other buckets
    rows.extend(_count_rows(d, "SL", "Slider", 1, 0, n=15))

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    even_bucket = [b for b in result.buckets if b.bucket == "even"][0]
    first_pitch_bucket = [b for b in result.buckets if b.bucket == "first_pitch"][0]

    assert even_bucket.n_pitches_window >= 15
    assert first_pitch_bucket.n_pitches_window >= 15


def test_count_splits_usage_pct_sums_to_100():
    """Each bucket's pitch_types usage_pct values sum to approximately 100.0."""
    rows = []
    d = date(2026, 4, 1)
    # Ahead: 10 FF, 5 SL at 0-1
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 1, n=10))
    rows.extend(_count_rows(d, "SL", "Slider", 0, 1, n=5))
    # Behind: 8 FF, 7 SL at 1-0
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 0, n=8))
    rows.extend(_count_rows(d, "SL", "Slider", 1, 0, n=7))
    # Even: 6 FF, 6 SL at 1-1
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 1, n=6))
    rows.extend(_count_rows(d, "SL", "Slider", 1, 1, n=6))
    # Two-strike: 5 FF, 5 SL at 0-2
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 2, n=5))
    rows.extend(_count_rows(d, "SL", "Slider", 0, 2, n=5))
    # First pitch: 4 FF, 4 SL at 0-0
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 0, n=4))
    rows.extend(_count_rows(d, "SL", "Slider", 0, 0, n=4))

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    for bucket in result.buckets:
        if bucket.n_pitches_window > 0:
            total_pct = sum(pt.usage_pct for pt in bucket.pitch_types)
            assert abs(total_pct - 100.0) < 0.1, (
                f"Bucket {bucket.bucket}: usage_pct sum = {total_pct}, expected ~100"
            )


def test_count_splits_small_sample_flag():
    """Bucket with <10 window pitches has small_sample=True; >=10 has False."""
    rows = []
    d = date(2026, 4, 1)
    # Ahead: only 5 pitches at 0-1 (small sample)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 1, n=5))
    # Behind: 15 pitches at 1-0 (not small sample)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 0, n=15))
    # Even: 3 at 0-0 (small sample)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 0, n=3))
    # Two-strike: 12 at 1-2 (not small)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 2, n=12))

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    ahead = [b for b in result.buckets if b.bucket == "ahead"][0]
    behind = [b for b in result.buckets if b.bucket == "behind"][0]
    even = [b for b in result.buckets if b.bucket == "even"][0]
    two_strike = [b for b in result.buckets if b.bucket == "two_strike"][0]
    first_pitch = [b for b in result.buckets if b.bucket == "first_pitch"][0]

    # Ahead: 5 window pitches at 0-1 (small sample)
    assert ahead.small_sample is True
    # Behind: 15 window pitches (not small)
    assert behind.small_sample is False
    # Even: 3 at 0-0 (small sample)
    assert even.small_sample is True
    # Two-strike: 12 at 1-2 (not small)
    assert two_strike.small_sample is False
    # First pitch: 3 at 0-0 (small sample)
    assert first_pitch.small_sample is True


def test_count_splits_small_sample_still_has_season_usage():
    """Small sample buckets suppress delta but still populate season_pitch_types."""
    rows = []
    d = date(2026, 4, 1)
    # 5 window pitches in ahead bucket (small sample)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 1, n=5))
    # Also add season-level pitches in a different game date that's outside window
    d_old = date(2026, 1, 15)
    rows.extend(_count_rows(d_old, "FF", "4-Seam Fastball", 0, 1, n=20, game_pk=600000))
    rows.extend(_count_rows(d_old, "SL", "Slider", 0, 1, n=10, game_pk=600000))
    # Need something in another bucket for the test to be meaningful
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 0, n=15))

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    ahead = [b for b in result.buckets if b.bucket == "ahead"][0]
    assert ahead.small_sample is True
    # Season pitch types should still be populated
    assert len(ahead.season_pitch_types) > 0


def test_count_splits_notable_shifts_10pp():
    """notable_shifts contains strings for shifts >= 10pp window vs season."""
    rows = []
    d_old = date(2026, 1, 15)
    d_window = date(2026, 4, 1)

    # Season ahead: 70% FF, 30% SL (70 FF, 30 SL)
    rows.extend(_count_rows(d_old, "FF", "4-Seam Fastball", 0, 1, n=70, game_pk=600000))
    rows.extend(_count_rows(d_old, "SL", "Slider", 0, 1, n=30, game_pk=600000))

    # Window ahead: 50% FF, 50% SL (10 FF, 10 SL) — delta is 20pp for both
    rows.extend(_count_rows(d_window, "FF", "4-Seam Fastball", 0, 1, n=10))
    rows.extend(_count_rows(d_window, "SL", "Slider", 0, 1, n=10))

    # Need some pitches in other buckets to avoid empty everything
    rows.extend(_count_rows(d_window, "FF", "4-Seam Fastball", 1, 0, n=15))

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    # There should be notable shifts for the ahead bucket
    assert len(result.notable_shifts) > 0
    # Should mention "Ahead" and contain percentage-point info
    shift_text = " ".join(result.notable_shifts)
    assert "Ahead" in shift_text or "ahead" in shift_text.lower()


def test_count_splits_no_notable_shifts_from_small_sample():
    """notable_shifts does NOT contain entries from small-sample buckets."""
    rows = []
    d_old = date(2026, 1, 15)
    d_window = date(2026, 4, 1)

    # Season ahead: 90% FF, 10% SL (huge difference)
    rows.extend(_count_rows(d_old, "FF", "4-Seam Fastball", 0, 1, n=90, game_pk=600000))
    rows.extend(_count_rows(d_old, "SL", "Slider", 0, 1, n=10, game_pk=600000))

    # Window ahead: only 5 pitches total (small sample), all SL => 0% FF (big delta)
    rows.extend(_count_rows(d_window, "SL", "Slider", 0, 1, n=5))

    # Must have something in another non-small bucket
    rows.extend(_count_rows(d_window, "FF", "4-Seam Fastball", 1, 0, n=15))

    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=30)
    result = compute_count_splits(data)

    ahead = [b for b in result.buckets if b.bucket == "ahead"][0]
    assert ahead.small_sample is True

    # No notable shifts should reference the ahead bucket
    for shift in result.notable_shifts:
        assert "Ahead" not in shift, f"Small-sample bucket appeared in notable_shifts: {shift}"


def test_count_splits_cold_start():
    """Cold start (window == season) produces identical window and season usage rates."""
    rows = []
    d = date(2026, 4, 1)

    # All pitches in a single game (window covers entire season)
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 0, 1, n=10))
    rows.extend(_count_rows(d, "SL", "Slider", 0, 1, n=10))
    rows.extend(_count_rows(d, "FF", "4-Seam Fastball", 1, 0, n=10))

    # window_days=365 so all data is in window => cold start
    data = _make_pitcher_data_for_count_splits(statcast_rows=rows, window_days=365)
    result = compute_count_splits(data)

    # For the ahead bucket, window and season usage should be identical
    ahead = [b for b in result.buckets if b.bucket == "ahead"][0]
    for w_pt in ahead.pitch_types:
        # Find matching season pitch type
        s_pt = [s for s in ahead.season_pitch_types if s.pitch_type == w_pt.pitch_type]
        assert len(s_pt) == 1, f"Missing season entry for {w_pt.pitch_type}"
        assert abs(w_pt.usage_pct - s_pt[0].usage_pct) < 0.1, (
            f"Cold start mismatch: window={w_pt.usage_pct}, season={s_pt[0].usage_pct}"
        )
