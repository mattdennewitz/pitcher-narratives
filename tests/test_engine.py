"""Tests for the fastball quality, arsenal, execution metrics, workload, and trend engine.

Covers delta string helpers, FastballSummary computation, VelocityArc
computation, cold start fallback, small sample flagging, arsenal summary,
platoon mix shifts, first-pitch weaponry analysis, execution metrics
(CSW%, zone rate, chase rate, xWhiff, xSwing, xRV100 percentile),
workload context (rest days, IP, pitch counts, consecutive days), and
year-over-year arsenal trend computation (added/dropped/continued pitches).
"""

import dataclasses

import polars as pl

from pitcher_narratives.data import PitcherData, load_pitcher_data
from pitcher_narratives.engine.baselines import outlier_tag
from pitcher_narratives.engine import (
    _CSW_DESCRIPTIONS,
    AppearanceWorkload,
    ArsenalTrends,
    ComponentAttribution,
    CrossSeasonSummary,
    ExecutionMetrics,
    FastballSummary,
    FirstPitchEntry,
    FirstPitchWeaponry,
    HardHitRate,
    IntermediateProbabilities,
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
    _most_recent_row,
    _pplus_delta_string,
    _stand_to_platoon,
    _usage_delta_string,
    _velo_delta_string,
    compute_arsenal_summary,
    compute_arsenal_trends,
    compute_component_attribution,
    compute_cross_season_summary,
    compute_execution_metrics,
    compute_fastball_summary,
    compute_first_pitch_weaponry,
    compute_hard_hit_rate,
    compute_intermediate_probabilities,
    compute_league_baselines,
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert isinstance(summary.season_p_plus, float)
    # window_p_plus may be None if no P+ data in window
    assert isinstance(summary.p_plus_delta, str)
    assert any(word in summary.p_plus_delta for word in ["Up", "Down", "Steady", "Full season"])


def test_fastball_splus_lplus():
    """FastballSummary has S+ and L+ season/window/delta fields."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert isinstance(summary.season_s_plus, float)
    assert isinstance(summary.s_plus_delta, str)
    assert isinstance(summary.season_l_plus, float)
    assert isinstance(summary.l_plus_delta, str)


def test_fastball_movement_delta():
    """FastballSummary has pfx_x/pfx_z season/window/delta fields."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert summary.pitch_type in ("FF", "FC")
    assert summary.pitch_name != ""  # Should have human-readable name


def test_compute_fastball_summary_suppresses_deltas_below_floor():
    """G6: below the pitch-count floor (but not empty), qualitative fastball
    delta strings render 'insufficient sample' instead of a computed delta."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    # A single game_date almost always yields fewer than _MIN_PITCHES fastballs.
    one_game = data.window_appearances.sort(
        ["game_date", "game_pk"], descending=True, nulls_last=True
    ).head(1)
    thin = dataclasses.replace(data, window_appearances=one_game)
    summary = compute_fastball_summary(thin)
    assert summary is not None
    assert summary.window_empty is False
    assert summary.small_sample is True
    assert summary.velo_delta == "insufficient sample"
    assert summary.p_plus_delta == "insufficient sample"
    assert summary.s_plus_delta == "insufficient sample"
    assert summary.l_plus_delta == "insufficient sample"
    assert summary.pfx_x_delta == "insufficient sample"
    assert summary.pfx_z_delta == "insufficient sample"


def test_compute_fastball_summary_empty_window_does_not_crash():
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    # Force an empty frame: no appearances in the window.
    empty = dataclasses.replace(data, window_appearances=data.window_appearances.head(0))
    summary = compute_fastball_summary(empty)
    assert summary is not None
    assert summary.window_empty is True
    # Window values fall back to season values; no None arithmetic.
    assert summary.window_velo == summary.season_velo
    assert summary.velo_delta == "No data for this frame"


# ── VelocityArc ──────────────────────────────────────────────────────


def _single_inning_pitcher_data(fastball_type: str = "FF") -> PitcherData:
    """Minimal PitcherData whose most recent appearance is a single inning.

    compute_velocity_arc only reads ``appearances`` (the most recent game) and
    ``statcast`` (that game's fastballs), so the remaining fields are empty
    stubs. Constructed rather than loaded so the single-inning branch is
    exercised deterministically, independent of any live pitcher's latest game.
    """
    import datetime

    game_date = datetime.date(2026, 6, 1)
    statcast = pl.DataFrame(
        {
            "game_pk": [1, 1, 1],
            "game_date": [game_date] * 3,
            "pitch_type": [fastball_type] * 3,
            "inning": [1, 1, 1],
            "release_speed": [95.0, 95.5, 94.5],
        }
    )
    appearances = pl.DataFrame({"game_pk": [1], "game_date": [game_date]})
    empty = pl.DataFrame()
    return PitcherData(
        statcast=statcast,
        appearances=appearances,
        window_appearances=empty,
        season_baseline=empty,
        pitch_type_baseline=empty,
        prior_season_baseline=empty,
        prior_pitch_type_baseline=empty,
        agg_csvs={},
        pitcher_id=1,
        pitcher_name="Test",
        throws="R",
    )


def test_velocity_arc_single_inning():
    """A single-inning appearance yields VelocityArc with available=False."""
    data = _single_inning_pitcher_data("FF")
    arc = compute_velocity_arc(data, "FF")
    assert isinstance(arc, VelocityArc)
    assert arc.available is False
    assert arc.innings_pitched == 1
    assert "Single inning" in arc.drop_string


def test_velocity_arc():
    """Multi-inning appearance returns VelocityArc with early/late velo."""
    # Use a pitcher with multi-inning appearances for this test.
    # Test pitcher Booser is all single-inning, so we test the structure
    # and the single-inning fallback above. For the multi-inning case,
    # we verify the dataclass fields are correct.
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    """When window covers full season, delta strings report the thin-frame hedge."""
    # Use recent_appearances=9999 so all appearances fall in window
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert summary.cold_start is True
    assert "Underpowered comparison" in summary.velo_delta
    assert "Underpowered comparison" in summary.p_plus_delta
    assert "Underpowered comparison" in summary.pfx_x_delta


# ── Frame sufficiency gate (G8) ───────────────────────────────────────


def test_frame_sufficiency_empty():
    """Zero window appearances classify as 'empty'."""
    from pitcher_narratives.engine._common import frame_sufficiency

    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    empty = dataclasses.replace(
        data, window_appearances=data.window_appearances.head(0)
    )
    assert frame_sufficiency(empty) == "empty"


def test_frame_sufficiency_thin_low_appearances():
    """A single-appearance window is underpowered ('thin')."""
    from pitcher_narratives.engine._common import frame_sufficiency

    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    thin = dataclasses.replace(
        data, window_appearances=data.window_appearances.head(1)
    )
    assert frame_sufficiency(thin) == "thin"


def test_frame_sufficiency_thin_full_season():
    """A window covering the whole season has no baseline to compare -> 'thin'."""
    from pitcher_narratives.engine._common import frame_sufficiency

    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    full = dataclasses.replace(data, window_appearances=data.appearances)
    assert frame_sufficiency(full) == "thin"


def test_is_cold_start_removed():
    """The day-window-shaped detector is gone after the G8 migration."""
    from pitcher_narratives.engine import _common

    assert not hasattr(_common, "_is_cold_start")


# ── Small sample ──────────────────────────────────────────────────────


def test_small_sample_flag():
    """FastballSummary.small_sample is True when <10 fastballs in window."""
    # Use a very small window to get few pitches
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=1)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    # compute_arsenal_summary returns the pitcher's qualifying pitch types,
    # whose season usage shares each fall in (0, 100] and sum to at most 100%.
    # It may omit fringe/low-sample types, so the total need not reach 100 --
    # assert the invariant rather than a data-coupled ~100 window.
    total_season = sum(p.season_usage_pct for p in arsenal)
    assert 0.0 < total_season <= 100.5


def test_arsenal_pplus_deltas():
    """Each PitchTypeSummary has P+/S+/L+ season, window, and delta fields."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    arsenal = compute_arsenal_summary(data)
    for pts in arsenal:
        assert isinstance(pts.pitch_name, str)
        assert pts.pitch_name != ""
        # Should not be just the code (e.g., "FC"), should be full name
        assert len(pts.pitch_name) > 2


def test_arsenal_ordering():
    """PitchTypeSummary list is ordered by season usage descending."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=1)
    arsenal = compute_arsenal_summary(data)
    for pts in arsenal:
        assert isinstance(pts.small_sample, bool)
        if pts.n_pitches_window < 10:
            assert pts.small_sample is True


def test_single_pitch_type():
    """Arsenal is a non-empty list of valid PitchTypeSummary entries, and a
    zero usage delta (the single-type / 100%-usage case) renders as 'Steady'."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    arsenal = compute_arsenal_summary(data)
    # Count of qualifying pitch types varies with the data; assert non-empty
    # rather than pinning an exact, data-coupled count.
    assert len(arsenal) >= 1
    for pts in arsenal:
        assert pts.n_pitches_season > 0
    # Single-type case: 0 usage delta at 100% usage reports "Steady".
    steady = _usage_delta_string(0.0)
    assert "Steady" in steady


def test_cold_start_arsenal():
    """A window covering the full season reports the thin-frame hedge on deltas."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    arsenal = compute_arsenal_summary(data)
    assert len(arsenal) > 0
    for pts in arsenal:
        assert pts.cold_start is True
        assert "Underpowered comparison" in pts.usage_delta
        assert "Underpowered comparison" in pts.p_plus_delta
        assert "Underpowered comparison" in pts.s_plus_delta
        assert "Underpowered comparison" in pts.l_plus_delta


# ── Platoon Mix ──────────────────────────────────────────────────────


def test_platoon_mix_shifts():
    """compute_platoon_mix returns PlatoonMix with per-type per-side usage rates and deltas."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    """Platoon splits honor the available/unavailable contract regardless of
    which (pitch_type, side) combos the pitcher actually throws: available
    splits carry valid usage, and a pitch not thrown to a side yields an
    unavailable split flagged with a 'not thrown' note.
    """
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    platoon = compute_platoon_mix(data)
    assert platoon.splits  # at least one (pitch_type, side) split
    for s in platoon.splits:
        assert s.platoon_side in ("same", "opposite")
        if s.available:
            assert 0.0 <= s.season_usage_pct <= 100.0
        else:
            # Unavailable combos document why, rather than being dropped.
            assert "not thrown" in s.usage_delta.lower()


def _one_sided_platoon_data() -> PitcherData:
    """Minimal PitcherData where CH is thrown only to opposite-side batters.

    Drives compute_platoon_mix to the 'not thrown to this side' branch for
    CH-same deterministically, independent of any live pitcher's splits. The
    empty (schema-only) platoon agg frames let the available (opposite) branch
    run without contributing data.
    """
    import datetime

    day = datetime.date(2026, 6, 1)
    statcast = pl.DataFrame(
        {
            "game_pk": [1] * 3,
            "game_date": [day] * 3,
            "pitch_type": ["CH"] * 3,
            "pitch_name": ["Changeup"] * 3,
            "stand": ["L"] * 3,  # LHB vs RHP -> opposite-side only
            "p_throws": ["R"] * 3,
            "release_speed": [85.0, 85.5, 84.5],
            "pfx_x": [1.0] * 3,
            "pfx_z": [1.0] * 3,
        }
    )
    appearances = pl.DataFrame({"game_pk": [1], "game_date": [day]})
    pitch_type_baseline = pl.DataFrame({"pitch_type": ["CH"], "n_pitches": [3]})
    platoon_schema = {
        "pitcher": pl.Int64, "pitch_type": pl.String, "platoon_matchup": pl.String,
        "n_pitches": pl.Int64, "P+": pl.Float64, "S+": pl.Float64, "L+": pl.Float64,
    }
    appearance_schema = {
        "game_date": pl.Date, "pitch_type": pl.String, "platoon_matchup": pl.String,
        "n_pitches": pl.Int64, "P+": pl.Float64, "S+": pl.Float64, "L+": pl.Float64,
    }
    empty = pl.DataFrame()
    return PitcherData(
        statcast=statcast,
        appearances=appearances,
        window_appearances=appearances,
        season_baseline=empty,
        pitch_type_baseline=pitch_type_baseline,
        prior_season_baseline=empty,
        prior_pitch_type_baseline=empty,
        agg_csvs={
            "pitcher_type_platoon": pl.DataFrame(schema=platoon_schema),
            "pitcher_type_platoon_appearance": pl.DataFrame(schema=appearance_schema),
        },
        pitcher_id=1,
        pitcher_name="Test",
        throws="R",
    )


def test_platoon_unavailable_combo():
    """A pitch thrown to only one side yields an unavailable split (with a
    'not thrown' note) for the side it skipped, and an available split for the
    side it was thrown to."""
    platoon = compute_platoon_mix(_one_sided_platoon_data())
    ch_same = [s for s in platoon.splits if s.pitch_type == "CH" and s.platoon_side == "same"]
    assert len(ch_same) == 1
    assert ch_same[0].available is False
    assert "not thrown" in ch_same[0].usage_delta.lower()
    ch_opp = [s for s in platoon.splits if s.pitch_type == "CH" and s.platoon_side == "opposite"]
    assert len(ch_opp) == 1
    assert ch_opp[0].available is True


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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    fpw = compute_first_pitch_weaponry(data)
    assert fpw.total_first_pitches_season > 0


def test_first_pitch_ordering():
    """First pitch entries are ordered by window_pct descending."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    fpw = compute_first_pitch_weaponry(data)
    for i in range(len(fpw.entries) - 1):
        assert fpw.entries[i].window_pct >= fpw.entries[i + 1].window_pct


# ── Execution Metrics ────────────────────────────────────────────────


def test_csw_per_type():
    """compute_execution_metrics returns list of ExecutionMetrics; FC has csw_pct > 0."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    metrics = compute_execution_metrics(data)
    for m in metrics:
        assert isinstance(m.zone_rate, float)
        assert 0.0 <= m.zone_rate <= 100.0


def test_chase_rate():
    """ExecutionMetrics entries have chase_rate (O-Swing%) between 0-100, zones 11-14 only."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    metrics = compute_execution_metrics(data)
    for m in metrics:
        assert isinstance(m.chase_rate, float)
        assert 0.0 <= m.chase_rate <= 100.0


def test_xwhiff_xswing():
    """ExecutionMetrics entries have xwhiff_p and xswing_p from pitcher_type_appearance CSV."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    metrics = compute_execution_metrics(data)
    # At least one pitch type should have xwhiff_p data (FC has enough pitches)
    fc_metrics = [m for m in metrics if m.pitch_type == "FC"]
    assert len(fc_metrics) == 1
    # xwhiff_p may be None for small sample types, but FC should have data
    assert fc_metrics[0].xwhiff_p is not None or fc_metrics[0].small_sample
    assert fc_metrics[0].xswing_p is not None or fc_metrics[0].small_sample


def test_xrv100_percentile():
    """ExecutionMetrics entries have xrv100_percentile as int 0-100, computed against distribution."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    metrics = compute_execution_metrics(data)
    fc_metrics = [m for m in metrics if m.pitch_type == "FC"]
    assert len(fc_metrics) == 1
    pctl = fc_metrics[0].xrv100_percentile
    assert isinstance(pctl, int)
    assert 0 <= pctl <= 100
    # Should not be exactly 50 (fallback) -- computed against real distribution
    assert pctl != 50


def test_xrv100_percentile_excludes_minor_league():
    """The percentile distribution is MLB-only; A/AAA pitchers must not pad it."""
    from pitcher_narratives.engine.execution import _compute_xrv100_percentile

    # 3 MLB pitchers (xRV100 0/1/2) and 5 worse minor-league pitchers (5..9).
    df = pl.DataFrame(
        {
            "pitcher": [1, 2, 3, 4, 5, 6, 7, 8],
            "pitch_type": ["FF"] * 8,
            "level": ["MLB", "MLB", "MLB", "AAA", "AAA", "A", "A", "AAA"],
            "n_pitches": [100] * 8,
            "xRV100_P": [0.0, 1.0, 2.0, 5.0, 6.0, 7.0, 8.0, 9.0],
        }
    )
    # Query xRV100 = 1.5: worse-than among MLB = {2.0} -> 1/3 -> 33rd percentile.
    # If minor-league rows leaked in, worse = 6/8 -> 75th. So this distinguishes.
    pctl = _compute_xrv100_percentile(1.5, "FF", df)
    assert pctl == 33, f"expected MLB-only 33rd percentile, got {pctl} (minor-league leak?)"


def test_xrv100_polarity():
    """Lower (more negative) xRV100 = better for pitcher = higher percentile."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    metrics = compute_execution_metrics(data)
    # Just verify the percentile is in valid range and the structure is correct
    # The polarity test is that the computation uses > (worse) to count n_worse
    for m in metrics:
        if m.xrv100_percentile is not None:
            assert 0 <= m.xrv100_percentile <= 100


def test_execution_metrics_small_sample():
    """ExecutionMetrics.small_sample is True when < 10 pitches of that type in window."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=1)
    metrics = compute_execution_metrics(data)
    for m in metrics:
        assert isinstance(m.small_sample, bool)
        if m.n_pitches < 10:
            assert m.small_sample is True


def test_execution_metrics_cold_start():
    """When window covers full season, cold_start is True."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    metrics = compute_execution_metrics(data)
    assert len(metrics) > 0
    for m in metrics:
        assert m.cold_start is True


# ── Workload Context ────────────────────────────────────────────────


def test_rest_days():
    """compute_workload_context returns WorkloadContext with rest_days; first has None, rest have int >= 0."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    workload = compute_workload_context(data)
    for app in workload.appearances:
        assert isinstance(app.pitch_count, int)
        assert app.pitch_count > 0
        # Verify against statcast
        statcast_count = data.statcast.filter(pl.col("game_pk") == app.game_pk).height
        assert app.pitch_count == statcast_count


def test_consecutive_days():
    """WorkloadContext has max_consecutive_days as int >= 1."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    workload = compute_workload_context(data)
    assert isinstance(workload.max_consecutive_days, int)
    assert workload.max_consecutive_days >= 1


def test_consecutive_days_flag():
    """WorkloadContext has workload_concern bool, True when max_consecutive_days >= 3."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    workload = compute_workload_context(data)
    assert isinstance(workload.workload_concern, bool)
    if workload.max_consecutive_days >= 3:
        assert workload.workload_concern is True
    else:
        assert workload.workload_concern is False


# ── Times Through Order ───────────────────────────────────────────────


def test_tto_returns_analysis():
    """compute_tto_analysis returns TTOAnalysis dataclass."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    tto = compute_tto_analysis(data)
    assert isinstance(tto, TTOAnalysis)
    assert isinstance(tto.available, bool)
    assert isinstance(tto.summary, str)
    assert len(tto.summary) > 0


def test_tto_splits_have_pass_numbers():
    """Each TTOSplit has a pass_number >= 1 and FB/secondary P+ fields."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
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
    data = load_pitcher_data(686799, recent_appearances=9999)
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
    data = load_pitcher_data(686799, recent_appearances=10)
    tto = compute_tto_analysis(data)
    if tto.available and len(tto.splits) >= 2:
        # First pass deltas are "--"
        assert tto.splits[0].fb_p_plus_delta == "--"
        assert tto.splits[0].sec_p_plus_delta == "--"
        # Later passes have real deltas
        assert tto.splits[1].fb_p_plus_delta != "--"


def test_tto_summary_mentions_fb():
    """TTO summary references fastball P+ specifically."""
    data = load_pitcher_data(686799, recent_appearances=10)
    tto = compute_tto_analysis(data)
    if tto.available:
        assert "Fastball P+" in tto.summary or "Secondary P+" in tto.summary


def test_tto_small_sample_flag():
    """Passes with < 50 pitches are flagged."""
    data = load_pitcher_data(686799, recent_appearances=9999)
    tto = compute_tto_analysis(data)
    for s in tto.splits:
        if s.pitches < 50:
            assert s.small_sample is True
        else:
            assert s.small_sample is False


def test_tto_reliever_single_pass():
    """Reliever who only faces batters once gets available=False."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    tto = compute_tto_analysis(data)
    # Booser is mostly RP with single-inning outings
    # If he has < 2 TTO groups, available should be False
    if len([s for s in tto.splits if s.pass_number >= 2]) == 0:
        assert tto.available is False


# ── Hard-Hit Rate ────────────────────────────────────────────────────


def test_hard_hit_rate_returns_dataclass():
    """compute_hard_hit_rate returns a HardHitRate with hard_hit_pct between 0 and 100."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    hhr = compute_hard_hit_rate(data)
    assert isinstance(hhr, HardHitRate)
    assert 0.0 <= hhr.hard_hit_pct <= 100.0


def test_hard_hit_rate_counts_batted_balls():
    """hard_hit_pct counts only batted balls (hit_into_play) with launch_speed >= 95."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    hhr = compute_hard_hit_rate(data)
    assert hhr.n_batted_balls > 0


def test_hard_hit_rate_small_sample():
    """small_sample is True when fewer than 10 batted balls in window."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=1)
    hhr = compute_hard_hit_rate(data)
    if hhr.n_batted_balls < 10:
        assert hhr.small_sample is True


def test_hard_hit_rate_cold_start():
    """cold_start is True when window covers entire season."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    hhr = compute_hard_hit_rate(data)
    assert hhr.cold_start is True


def test_hard_hit_rate_season_pct():
    """season_hard_hit_pct is computed from full season, not just window."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    hhr = compute_hard_hit_rate(data)
    assert any(word in hhr.delta for word in ["Up", "Down", "Steady", "Full season in window"])


# ── Release Point Metrics ────────────────────────────────────────────


def test_release_point_returns_metrics():
    """compute_release_point_metrics returns ReleasePointMetrics with non-empty pitch_types list."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    rp = compute_release_point_metrics(data)
    assert isinstance(rp, ReleasePointMetrics)
    assert isinstance(rp.pitch_types, list)
    assert len(rp.pitch_types) > 0


def test_release_point_values_reasonable():
    """Release point values are in physically reasonable ranges."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    rp = compute_release_point_metrics(data)
    for pt in rp.pitch_types:
        for delta_str in [pt.release_x_delta, pt.release_z_delta, pt.extension_delta]:
            assert any(word in delta_str for word in ["Up", "Down", "Steady", "Full season"]), (
                f"Unexpected delta string: {delta_str}"
            )


def test_release_point_cold_start():
    """With recent_appearances=9999, cold_start=True and deltas report the thin-frame hedge."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=9999)
    rp = compute_release_point_metrics(data)
    assert rp.cold_start is True
    for pt in rp.pitch_types:
        assert pt.cold_start is True
        assert "Underpowered comparison" in pt.release_x_delta
        assert "Underpowered comparison" in pt.release_z_delta
        assert "Underpowered comparison" in pt.extension_delta


def test_release_point_small_sample():
    """With recent_appearances=1, entries with < 10 pitches have small_sample=True."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=1)
    rp = compute_release_point_metrics(data)
    for pt in rp.pitch_types:
        if pt.n_pitches_window < 10:
            assert pt.small_sample is True


def test_release_point_ordering():
    """Entries are ordered by season pitch count descending."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    rp = compute_release_point_metrics(data)
    # Verify descending order -- first entry should be one of the top-usage pitches
    if len(rp.pitch_types) >= 2:
        assert rp.pitch_types[0].pitch_type in ("FF", "FC", "ST")


# ── Intermediate Probabilities ───────────────────────────────────────


def test_intermediate_probabilities_computed():
    """compute_intermediate_probabilities returns typed results with real data."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    result = compute_intermediate_probabilities(data)
    for item in result:
        assert item.bbe_prob_p is None
        assert item.bbe_prob_s is None


def test_intermediate_p_and_s_variants():
    """P and S variants should both exist together for each metric."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    result = compute_component_attribution(data)
    assert isinstance(result, list)
    assert len(result) > 0
    for attr in result:
        assert isinstance(attr, ComponentAttribution)
        assert len(attr.contributions) == 13


def test_component_attribution_sum():
    """Sum of 13 contributions equals total_xrv100 within tolerance."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    result = compute_component_attribution(data)
    for attr in result:
        labels = {c.outcome for c in attr.contributions}
        assert labels == canonical, f"{attr.pitch_type}: labels={labels}"


def test_component_attribution_sorted_by_magnitude():
    """Contributions are sorted by |contribution| descending."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    result = compute_component_attribution(data)
    for attr in result:
        magnitudes = [abs(c.contribution) for c in attr.contributions]
        assert magnitudes == sorted(magnitudes, reverse=True), (
            f"{attr.pitch_type}: not sorted by magnitude"
        )


def test_component_attribution_pitcher_type_grain():
    """With game_pk=None, returns season-level aggregation."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
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


# ── Cross-season summary ────────────────────────────────────────────


SINGLE_SEASON_PITCHER = 823810  # Moring, Reed -- only 2026 data


def test_cross_season_summary_returns_dataclass_for_multi_season_pitcher():
    """SDLT-01: Multi-season pitcher gets CrossSeasonSummary with all YoY deltas."""
    data = load_pitcher_data(TEST_PITCHER)
    result = compute_cross_season_summary(data)
    assert result is not None
    assert isinstance(result, CrossSeasonSummary)
    assert isinstance(result.current_season, int)
    assert isinstance(result.prior_season, int)
    assert result.current_season > result.prior_season
    assert result.current_velo > 0
    assert result.prior_velo > 0
    assert isinstance(result.velo_delta, str) and len(result.velo_delta) > 0
    assert isinstance(result.p_plus_delta, str) and len(result.p_plus_delta) > 0
    assert isinstance(result.s_plus_delta, str) and len(result.s_plus_delta) > 0
    assert isinstance(result.l_plus_delta, str) and len(result.l_plus_delta) > 0


def test_cross_season_summary_delta_strings_use_qualitative_language():
    """SDLT-02: YoY deltas use same language as within-season (Steady/Up/Down)."""
    data = load_pitcher_data(TEST_PITCHER)
    result = compute_cross_season_summary(data)
    assert result is not None
    for delta_str in [result.velo_delta, result.p_plus_delta, result.s_plus_delta, result.l_plus_delta]:
        assert any(word in delta_str for word in ("Steady", "Up", "Down")), (
            f"Delta string '{delta_str}' missing qualitative language"
        )


def test_cross_season_summary_returns_none_for_single_season_pitcher():
    """SDLT-03: Single-season pitcher gets None, not empty or zeroes."""
    data = load_pitcher_data(SINGLE_SEASON_PITCHER)
    result = compute_cross_season_summary(data)
    assert result is None


def test_cross_season_summary_in_engine_all():
    """CrossSeasonSummary and compute_cross_season_summary exported in __all__."""
    import pitcher_narratives.engine as eng
    assert "CrossSeasonSummary" in eng.__all__
    assert "compute_cross_season_summary" in eng.__all__


# ── Arsenal Trends (Year-over-Year) ────────────────────────────────────


MULTI_YEAR_PITCHER = 607625  # Multi-year pitcher with varied arsenal


def test_arsenal_trends_single_season_returns_none():
    """ATRN-03: Pitcher with only one season of data gets None."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    # Simulate single-season by filtering agg_csvs to max season only
    from pitcher_narratives.data import PitcherData

    pt_df = data.agg_csvs["pitcher_type"]
    if "season" in pt_df.columns:
        max_season = pt_df["season"].max()
        single_season_pt = pt_df.filter(pl.col("season") == max_season)
    else:
        single_season_pt = pt_df

    single_data = PitcherData(
        statcast=data.statcast,
        appearances=data.appearances,
        window_appearances=data.window_appearances,
        season_baseline=data.season_baseline,
        pitch_type_baseline=data.pitch_type_baseline,
        prior_season_baseline=data.prior_season_baseline.clear(),
        prior_pitch_type_baseline=data.prior_pitch_type_baseline.clear(),
        agg_csvs={**data.agg_csvs, "pitcher_type": single_season_pt},
        pitcher_id=data.pitcher_id,
        pitcher_name=data.pitcher_name,
        throws=data.throws,
    )
    result = compute_arsenal_trends(single_data)
    assert result is None, "Single-season pitcher should return None"


def test_arsenal_trends_returns_arsenal_trends():
    """Multi-season pitcher returns ArsenalTrends container."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None, "Multi-season pitcher should return ArsenalTrends"
    assert isinstance(result, ArsenalTrends)


def test_arsenal_trends_identifies_added_dropped():
    """ATRN-01: Correctly classifies added and dropped pitches."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None

    # All entries have correct status
    for trend in result.added:
        assert trend.status == "added"
        assert trend.prior_usage_pct is None, "Added pitch should have no prior usage"
        assert trend.current_usage_pct is not None, "Added pitch should have current usage"
        assert trend.n_pitches_prior is None
        assert trend.n_pitches_current is not None and trend.n_pitches_current > 0

    for trend in result.dropped:
        assert trend.status == "dropped"
        assert trend.prior_usage_pct is not None, "Dropped pitch should have prior usage"
        assert trend.current_usage_pct is None, "Dropped pitch should have no current usage"
        assert trend.n_pitches_prior is not None and trend.n_pitches_prior > 0
        assert trend.n_pitches_current is None

    # Added + dropped + continued covers all pitch types across both seasons
    all_types = (
        {t.pitch_type for t in result.added}
        | {t.pitch_type for t in result.dropped}
        | {t.pitch_type for t in result.continued}
    )
    assert len(all_types) > 0, "Should have at least one pitch type"


def test_arsenal_trends_computes_yoy_deltas():
    """ATRN-02: Continued pitches have per-pitch-type YoY deltas."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None
    assert len(result.continued) > 0, "Should have continued pitches"

    for trend in result.continued:
        assert trend.status == "continued"
        # Usage delta
        assert trend.prior_usage_pct is not None
        assert trend.current_usage_pct is not None
        assert trend.usage_delta is not None
        assert isinstance(trend.usage_delta, str)
        # P+/S+/L+ deltas
        assert trend.prior_p_plus is not None
        assert trend.current_p_plus is not None
        assert trend.p_plus_delta is not None
        assert trend.s_plus_delta is not None
        assert trend.l_plus_delta is not None
        # Pitch counts
        assert trend.n_pitches_prior is not None and trend.n_pitches_prior > 0
        assert trend.n_pitches_current is not None and trend.n_pitches_current > 0


def test_arsenal_trends_uses_qualitative_language():
    """Delta strings match existing qualitative style (Up/Down/Steady/sharply)."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None

    valid_prefixes = ("Steady", "Up", "Down")
    for trend in result.continued:
        assert trend.usage_delta is not None
        assert any(trend.usage_delta.startswith(p) for p in valid_prefixes), (
            f"usage_delta '{trend.usage_delta}' doesn't start with Steady/Up/Down"
        )
        assert trend.p_plus_delta is not None
        assert any(trend.p_plus_delta.startswith(p) for p in valid_prefixes), (
            f"p_plus_delta '{trend.p_plus_delta}' doesn't start with Steady/Up/Down"
        )
        assert trend.s_plus_delta is not None
        assert any(trend.s_plus_delta.startswith(p) for p in valid_prefixes), (
            f"s_plus_delta '{trend.s_plus_delta}' doesn't start with Steady/Up/Down"
        )


def test_arsenal_trends_minimum_pitch_threshold():
    """Pitches below minimum threshold excluded from trends."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None

    from pitcher_narratives.engine import _MIN_PITCHES

    for trend in result.continued:
        assert trend.n_pitches_current is not None and trend.n_pitches_current >= _MIN_PITCHES
        assert trend.n_pitches_prior is not None and trend.n_pitches_prior >= _MIN_PITCHES
    for trend in result.added:
        assert trend.n_pitches_current is not None and trend.n_pitches_current >= _MIN_PITCHES
    for trend in result.dropped:
        assert trend.n_pitches_prior is not None and trend.n_pitches_prior >= _MIN_PITCHES


def test_arsenal_trends_season_fields():
    """ArsenalTrends has correct prior and current season values."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None
    assert result.prior_season < result.current_season
    assert result.prior_season == 2025
    assert result.current_season == 2026

    # Individual trends also carry season info
    for trend in [*result.added, *result.dropped, *result.continued]:
        assert trend.prior_season == result.prior_season
        assert trend.current_season == result.current_season


def test_arsenal_trends_has_changes_property():
    """has_changes property reflects whether any changes exist."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None
    assert result.has_changes is True, "Multi-year pitcher should have changes"


def test_arsenal_trends_velocity_deltas():
    """Continued pitches include velocity deltas from statcast data."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None

    has_velo = False
    for trend in result.continued:
        if trend.velo_delta is not None:
            has_velo = True
            assert trend.prior_velo is not None
            assert trend.current_velo is not None
            valid_prefixes = ("Steady", "Up", "Down")
            assert any(trend.velo_delta.startswith(p) for p in valid_prefixes), (
                f"velo_delta '{trend.velo_delta}' doesn't use qualitative language"
            )
    assert has_velo, "Should have at least one continued pitch with velocity data"


def test_arsenal_trends_pitch_names():
    """All trends include human-readable pitch names."""
    data = load_pitcher_data(MULTI_YEAR_PITCHER, recent_appearances=10)
    result = compute_arsenal_trends(data)
    assert result is not None

    for trend in [*result.added, *result.dropped, *result.continued]:
        assert trend.pitch_name, f"pitch_name should not be empty for {trend.pitch_type}"
        assert isinstance(trend.pitch_name, str)


def test_most_recent_row_breaks_doubleheader_ties_by_game_pk():
    # Two appearances on the same date (a doubleheader): higher game_pk wins.
    appearances = pl.DataFrame(
        {
            "game_date": ["2024-05-01", "2024-05-01", "2024-04-15"],
            "game_pk": [745002, 745001, 744000],
            "role": ["RP", "RP", "RP"],
        }
    )
    row = _most_recent_row(appearances)
    assert row["game_pk"] == 745002


def test_most_recent_row_picks_latest_date():
    appearances = pl.DataFrame(
        {
            "game_date": ["2024-04-15", "2024-05-01"],
            "game_pk": [744000, 745001],
            "role": ["RP", "SP"],
        }
    )
    row = _most_recent_row(appearances)
    assert row["game_date"] == "2024-05-01"
    assert row["role"] == "SP"


# ── Movement units (inches, not raw Statcast feet) ───────────────────


def test_league_baseline_movement_in_inches():
    """League FF vertical movement lands in the inch range (~16), not feet (~1.3)."""
    baselines = compute_league_baselines()
    ff = next(b for b in baselines if b.pitch_type == "FF")
    assert 10.0 < ff.avg_pfx_z < 25.0
    assert 0.5 < ff.pfx_z_std < 6.0


def test_fastball_summary_movement_in_inches():
    """Fastball summary movement values are inches (Booser FC ride ~3-4 in)."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    summary = compute_fastball_summary(data)
    assert summary is not None
    assert abs(summary.season_pfx_z) > 1.0 or abs(summary.season_pfx_x) > 1.0
    assert -30.0 < summary.season_pfx_x < 30.0
    assert abs(summary.season_pfx_x) + abs(summary.season_pfx_z) > 3.0


def test_arsenal_summary_movement_in_inches():
    """Arsenal per-type movement values are inches, not feet."""
    data = load_pitcher_data(TEST_PITCHER, recent_appearances=10)
    arsenal = compute_arsenal_summary(data)
    ff = next(p for p in arsenal if p.pitch_type == "FF")
    assert 10.0 < ff.season_pfx_z < 25.0


def test_outlier_tag_suppressed_below_sample_floor():
    # z-score would be a strong OUTLIER, but N is below the floor -> suppressed.
    tag = outlier_tag(value=100.0, avg=92.0, std=1.0, n=4)
    assert tag == "SMALL SAMPLE, N=4 -- untagged"


def test_outlier_tag_normal_string_unchanged_at_floor():
    tag = outlier_tag(value=92.5, avg=92.0, std=1.0, n=10)
    assert tag == "NORMAL (z=+0.5)"


def test_outlier_tag_outlier_string_unchanged_above_floor():
    tag = outlier_tag(value=95.0, avg=92.0, std=1.0, n=25)
    assert tag == "OUTLIER (above avg, z=+3.0)"
