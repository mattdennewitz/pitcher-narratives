"""Tests for the arm-slot movement interaction (pitch shape) module.

Covers arm angle bucketing, shape classification (dead zone, ride above
slot, sink below slot, extra arm-side run), the league slot-expectation
table (handedness-mirrored, inch units, slot-vs-ride physics), and the
per-pitcher shape profile computed from real Statcast data.
"""

import pytest

from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.shape import (
    PitchShapeEntry,
    PitchShapeProfile,
    SlotExpectation,
    _arm_angle_bucket,
    _classify_shape,
    _interpolate_expectation,
    compute_pitch_shape,
    compute_slot_expectations,
)

TEST_PITCHER = 592155  # Booser, Cam -- LHP, FF/FC/ST/CH arsenal


# ── Arm angle bucketing ───────────────────────────────────────────────


def test_arm_angle_bucket_floors_to_ten_degrees():
    """35.9 degrees falls in the [30, 40) bucket."""
    assert _arm_angle_bucket(35.9) == 30


def test_arm_angle_bucket_exact_boundary():
    """40.0 degrees starts the [40, 50) bucket."""
    assert _arm_angle_bucket(40.0) == 40


def test_arm_angle_bucket_negative():
    """Submarine slots floor toward negative buckets: -5 -> [-10, 0)."""
    assert _arm_angle_bucket(-5.0) == -10


# ── Shape classification ──────────────────────────────────────────────


def test_classify_dead_zone_fastball():
    """Fastball within 0.5 SD on both axes is DEAD ZONE."""
    tag = _classify_shape(0.5, -0.8, run_z=0.2, ride_z=-0.3, is_fastball=True)
    assert tag.startswith("DEAD ZONE")


def test_classify_ride_above_slot():
    """Fastball with ride 1.8 SD above expectation flags ride, showing in + SD."""
    tag = _classify_shape(0.0, 3.2, run_z=0.0, ride_z=1.8, is_fastball=True)
    assert "ride" in tag.lower()
    assert "+3.2" in tag
    assert "1.8 SD" in tag


def test_classify_sink_below_slot():
    """Fastball with ride 1.7 SD below expectation flags sink."""
    tag = _classify_shape(0.0, -2.5, run_z=0.0, ride_z=-1.7, is_fastball=True)
    assert "sink" in tag.lower()


def test_classify_extra_run():
    """Run 1.8 SD above expectation flags more arm-side run than slot suggests."""
    tag = _classify_shape(3.0, 0.0, run_z=1.8, ride_z=0.0, is_fastball=True)
    assert "run" in tag.lower()


def test_classify_both_axes():
    """Residuals notable (>=1.5 SD) on both axes are both mentioned."""
    tag = _classify_shape(3.0, 3.0, run_z=1.8, ride_z=1.8, is_fastball=True)
    assert "run" in tag.lower()
    assert "ride" in tag.lower()


def test_classify_non_fastball_neutral():
    """Non-fastball matching slot expectation is in line, never DEAD ZONE."""
    tag = _classify_shape(0.5, 0.5, run_z=0.2, ride_z=0.2, is_fastball=False)
    assert "DEAD ZONE" not in tag
    assert "in line" in tag.lower()


def test_classify_gray_zone_not_dead_zone():
    """A fastball 0.9 SD off slot is neither DEAD ZONE nor flagged."""
    tag = _classify_shape(0.0, 1.8, run_z=0.0, ride_z=0.9, is_fastball=True)
    assert "DEAD ZONE" not in tag
    assert "in line" in tag.lower()


def test_classify_dead_zone_requires_both_axes_within_half_sd():
    """A fastball within 0.5 SD on ride but 0.6 SD on run is not DEAD ZONE."""
    tag = _classify_shape(1.7, 0.5, run_z=0.6, ride_z=0.2, is_fastball=True)
    assert "DEAD ZONE" not in tag


# ── League slot expectations ──────────────────────────────────────────


@pytest.fixture(scope="module")
def expectations() -> dict[tuple[str, int], SlotExpectation]:
    return compute_slot_expectations()


def test_slot_expectations_has_ff_buckets(expectations):
    """Common four-seam arm angle buckets (30, 40) exist in the table."""
    assert ("FF", 30) in expectations
    assert ("FF", 40) in expectations


def test_slot_expectations_values_in_inches(expectations):
    """FF ride expectation is in plausible inch range (catches feet bug)."""
    exp = expectations[("FF", 40)]
    assert 10.0 < exp.exp_ride_in < 25.0


def test_slot_expectations_ride_increases_with_slot(expectations):
    """Higher arm slots produce more ride on four-seamers."""
    assert expectations[("FF", 50)].exp_ride_in > expectations[("FF", 10)].exp_ride_in


def test_slot_expectations_run_decreases_with_slot(expectations):
    """Higher arm slots produce less arm-side run on four-seamers."""
    assert expectations[("FF", 50)].exp_arm_side_run_in < expectations[("FF", 10)].exp_arm_side_run_in


def test_slot_expectations_min_sample(expectations):
    """Every bucket in the table meets the league minimum pitch count."""
    assert all(e.n_pitches >= 200 for e in expectations.values())


# ── Pitcher shape profile (real data) ─────────────────────────────────


@pytest.fixture(scope="module")
def profile() -> PitchShapeProfile | None:
    data = load_pitcher_data(TEST_PITCHER)
    return compute_pitch_shape(data)


def test_profile_present(profile):
    """Test pitcher has enough arm-angle data for a shape profile."""
    assert isinstance(profile, PitchShapeProfile)
    assert len(profile.entries) > 0


def test_profile_ff_entry(profile):
    """FF entry carries slot, observed movement, expectation, residuals, tag."""
    ff = next(e for e in profile.entries if e.pitch_type == "FF")
    assert isinstance(ff, PitchShapeEntry)
    assert 30.0 < ff.arm_angle < 45.0
    assert 14.0 < ff.ride_in < 18.0
    assert 10.0 < ff.exp_ride_in < 25.0
    assert ff.ride_residual_in == pytest.approx(ff.ride_in - ff.exp_ride_in)
    assert ff.run_residual_in == pytest.approx(ff.arm_side_run_in - ff.exp_arm_side_run_in)
    assert ff.shape_tag


def test_profile_skips_thin_samples(profile):
    """Every entry meets the 10-pitch arm-angle minimum."""
    assert all(e.n_pitches >= 10 for e in profile.entries)


def test_profile_ordered_by_sample_descending(profile):
    """Entries are ordered by pitch count descending (FF first for Booser)."""
    counts = [e.n_pitches for e in profile.entries]
    assert counts == sorted(counts, reverse=True)


def test_profile_fastball_flag(profile):
    """FF/FC are flagged as fastballs; ST is not."""
    flags = {e.pitch_type: e.is_fastball for e in profile.entries}
    assert flags.get("FF") is True
    assert flags.get("FC") is True
    assert flags.get("ST") is False


# ── Interpolated expectations ─────────────────────────────────────────


def _synthetic_table() -> dict[tuple[str, int], SlotExpectation]:
    """Two adjacent FF buckets with a known linear gradient in mean and SD."""
    return {
        ("FF", 30): SlotExpectation(
            pitch_type="FF", bucket=30, n_pitches=1000,
            exp_arm_side_run_in=8.0, exp_ride_in=15.0,
            std_arm_side_run_in=3.0, std_ride_in=2.0,
        ),
        ("FF", 40): SlotExpectation(
            pitch_type="FF", bucket=40, n_pitches=1000,
            exp_arm_side_run_in=6.0, exp_ride_in=17.0,
            std_arm_side_run_in=3.0, std_ride_in=4.0,
        ),
    }


def test_interpolate_midpoint_between_centers():
    """Angle midway between bucket centers (40.0) blends mean and SD equally."""
    run, ride, sd_run, sd_ride = _interpolate_expectation(_synthetic_table(), "FF", 40.0)
    assert run == pytest.approx(7.0)
    assert ride == pytest.approx(16.0)
    assert sd_ride == pytest.approx(3.0)  # between 2.0 and 4.0


def test_interpolate_at_center_returns_bucket_mean():
    """Angle at a bucket center (35.0) returns that bucket's means and SD."""
    run, ride, sd_run, sd_ride = _interpolate_expectation(_synthetic_table(), "FF", 35.0)
    assert run == pytest.approx(8.0)
    assert ride == pytest.approx(15.0)
    assert sd_ride == pytest.approx(2.0)


def test_interpolate_continuous_across_bucket_boundary():
    """Expectations barely move across the 40-degree bucket edge (no step)."""
    table = _synthetic_table()
    _, ride_below, _, _ = _interpolate_expectation(table, "FF", 39.9)
    _, ride_above, _, _ = _interpolate_expectation(table, "FF", 40.1)
    assert abs(ride_above - ride_below) < 0.1


def test_interpolate_missing_neighbor_falls_back_to_nearest():
    """With only one bucket in the table, its means and SD are used as-is."""
    table = _synthetic_table()
    del table[("FF", 40)]
    run, ride, sd_run, sd_ride = _interpolate_expectation(table, "FF", 39.9)
    assert run == pytest.approx(8.0)
    assert ride == pytest.approx(15.0)
    assert sd_ride == pytest.approx(2.0)


def test_interpolate_no_data_returns_none():
    """Pitch type absent from the table yields None."""
    assert _interpolate_expectation({}, "FF", 35.0) is None


# ── Between-pitcher SD and z-scores ───────────────────────────────────


def test_slot_expectations_std_is_between_pitcher(expectations):
    """FF SD is the between-pitcher spread (~2 in ride), not pitch-level (~2.6)."""
    e = expectations[("FF", 40)]
    assert 1.0 < e.std_ride_in < 3.0
    assert 2.0 < e.std_arm_side_run_in < 4.0


def test_profile_entries_carry_z_scores(profile):
    """Each entry exposes residual z-scores consistent with residual / slot SD."""
    ff = next(e for e in profile.entries if e.pitch_type == "FF")
    assert isinstance(ff.ride_z, float)
    assert isinstance(ff.run_z, float)
    # z has the same sign as the residual and a sane magnitude
    assert (ff.ride_z >= 0) == (ff.ride_residual_in >= 0)
    assert abs(ff.ride_z) < 6.0
