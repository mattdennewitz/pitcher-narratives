"""Arm-slot movement interaction (pitch shape) analysis.

Computes a league expectation table of pitch movement conditional on
arm angle, then classifies each pitcher's pitch shapes against that
expectation. A four-seamer whose movement matches what hitters expect
from the release slot is a "dead zone" pitch; movement well above or
below slot expectation is a distinctive trait worth narrating.

All movement values are converted from Statcast feet to inches, and
horizontal movement is mirrored to arm-side-positive so left- and
right-handed samples pool into one expectation table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData, load_all_statcast

__all__ = [
    "PitchShapeEntry",
    "PitchShapeProfile",
    "SlotExpectation",
    "compute_pitch_shape",
    "compute_slot_expectations",
    "render_pitch_shape",
]

_BUCKET_DEGREES = 10
"""Arm angle bucket width in degrees."""

_MIN_BUCKET_PITCHES = 200
"""Minimum league pitches per (pitch_type, bucket) for a usable expectation."""

_MIN_PITCHER_PITCHES = 10
"""Minimum pitcher pitches with arm-angle data per pitch type."""

_MIN_PITCHER_PITCHES_FOR_SD = 5
"""Minimum pitches for a pitcher's mean to count toward between-pitcher SD."""

_DEAD_ZONE_Z = 0.5
"""Residual within this many between-pitcher SDs on both axes = slot-typical."""

_FLAG_Z = 1.5
"""Residual beyond this many between-pitcher SDs on an axis = a deceptive trait."""

_FASTBALL_TYPES = frozenset({"FF", "SI", "FC"})
"""Standard Statcast fastball classification codes."""

_FEET_TO_INCHES = 12.0


@dataclass
class SlotExpectation:
    """League-average movement for one pitch type from one arm angle bucket."""

    pitch_type: str
    bucket: int
    """Lower bound of the arm angle bucket in degrees, e.g. 30 = [30, 40)."""

    n_pitches: int
    exp_arm_side_run_in: float
    """League mean arm-side horizontal movement (inches, arm-side positive)."""

    exp_ride_in: float
    """League mean induced vertical movement (inches)."""

    std_arm_side_run_in: float
    """Between-pitcher SD of mean arm-side run in this slot (z-score denominator)."""

    std_ride_in: float
    """Between-pitcher SD of mean ride in this slot (z-score denominator)."""


@dataclass
class PitchShapeEntry:
    """One pitch type's movement profile relative to slot expectation."""

    pitch_type: str
    pitch_name: str
    is_fastball: bool

    n_pitches: int
    """Pitches with arm-angle data used for this entry."""

    arm_angle: float
    """Mean arm angle in degrees."""

    arm_side_run_in: float
    """Observed arm-side horizontal movement (inches)."""

    ride_in: float
    """Observed induced vertical movement (inches)."""

    exp_arm_side_run_in: float
    exp_ride_in: float
    run_residual_in: float
    """Observed minus expected arm-side run (inches)."""

    ride_residual_in: float
    """Observed minus expected ride (inches)."""

    run_residual_z: float
    """Run residual in between-pitcher SD units for the slot."""

    ride_residual_z: float
    """Ride residual in between-pitcher SD units for the slot."""

    shape_tag: str
    """Deterministic classification, e.g. 'DEAD ZONE ...' or ride/run flags."""

    @property
    def run_z(self) -> float:
        return self.run_residual_z

    @property
    def ride_z(self) -> float:
        return self.ride_residual_z


@dataclass
class PitchShapeProfile:
    """Arm-slot shape analysis across the pitcher's arsenal."""

    entries: list[PitchShapeEntry]
    """Ordered by arm-angle pitch count descending."""


def _arm_angle_bucket(arm_angle: float) -> int:
    """Floor an arm angle to its bucket lower bound in degrees."""
    return int(math.floor(arm_angle / _BUCKET_DEGREES) * _BUCKET_DEGREES)


def _classify_shape(
    run_residual_in: float,
    ride_residual_in: float,
    run_z: float,
    ride_z: float,
    is_fastball: bool,
) -> str:
    """Classify a pitch's movement residuals vs slot expectation.

    Decisions use z-scores (residual / between-pitcher SD for the slot) so
    the bands scale with how much pitchers actually vary at that arm angle:
    a fastball within _DEAD_ZONE_Z SD on BOTH axes is slot-typical (DEAD
    ZONE); a residual beyond _FLAG_Z SD on an axis is a notable deceptive
    trait. The displayed magnitudes stay in inches (scout-readable) with the
    SD appended so the reader can weight it.
    """
    flags: list[str] = []
    if ride_z >= _FLAG_Z:
        flags.append(f"ride above slot expectation ({ride_residual_in:+.1f} in, {ride_z:+.1f} SD)")
    elif ride_z <= -_FLAG_Z:
        flags.append(f"sinks below slot expectation ({ride_residual_in:+.1f} in, {ride_z:+.1f} SD)")
    if run_z >= _FLAG_Z:
        flags.append(f"more arm-side run than slot suggests ({run_residual_in:+.1f} in, {run_z:+.1f} SD)")
    elif run_z <= -_FLAG_Z:
        flags.append(f"more cut/glove-side than slot suggests ({run_residual_in:+.1f} in, {run_z:+.1f} SD)")

    if flags:
        joined = "; ".join(flags)
        return joined[:1].upper() + joined[1:]
    if is_fastball and abs(run_z) < _DEAD_ZONE_Z and abs(ride_z) < _DEAD_ZONE_Z:
        return "DEAD ZONE -- movement matches slot expectation; hitters see what the arm angle predicts"
    return "In line with slot expectation"


def _z(residual: float, sd: float) -> float:
    """Standardize a residual by a between-pitcher SD; 0.0 when SD is unusable."""
    return residual / sd if sd > 0 else 0.0


def _interpolate_expectation(
    expectations: dict[tuple[str, int], SlotExpectation],
    pitch_type: str,
    arm_angle: float,
) -> tuple[float, float, float, float] | None:
    """Linearly interpolate (run, ride, sd_run, sd_ride) at an exact arm angle.

    Bucket values are anchored at bucket centers (bucket + 5 deg) and the
    expectation blends the two buckets whose centers straddle the angle,
    so expectations vary continuously instead of stepping at bucket
    edges. The between-pitcher SDs are interpolated the same way. When one
    neighbor is missing (edge of the league table) the nearest available
    bucket's values are used unchanged.

    Returns:
        (exp_arm_side_run_in, exp_ride_in, std_arm_side_run_in, std_ride_in)
        or None when no bucket near the angle exists for this pitch type.
    """
    half = _BUCKET_DEGREES / 2.0
    lower_bucket = _arm_angle_bucket(arm_angle - half)
    upper_bucket = lower_bucket + _BUCKET_DEGREES
    lower = expectations.get((pitch_type, lower_bucket))
    upper = expectations.get((pitch_type, upper_bucket))

    if lower is not None and upper is not None:
        t = (arm_angle - (lower_bucket + half)) / _BUCKET_DEGREES
        blend = lambda lo, hi: lo + t * (hi - lo)  # noqa: E731
        return (
            blend(lower.exp_arm_side_run_in, upper.exp_arm_side_run_in),
            blend(lower.exp_ride_in, upper.exp_ride_in),
            blend(lower.std_arm_side_run_in, upper.std_arm_side_run_in),
            blend(lower.std_ride_in, upper.std_ride_in),
        )

    nearest = lower if lower is not None else upper
    if nearest is None:
        return None
    return (
        nearest.exp_arm_side_run_in,
        nearest.exp_ride_in,
        nearest.std_arm_side_run_in,
        nearest.std_ride_in,
    )


_slot_expectations_cache: dict[tuple[str, int], SlotExpectation] | None = None


def compute_slot_expectations() -> dict[tuple[str, int], SlotExpectation]:
    """Compute the league movement expectation table conditional on arm angle.

    Pools both handedness samples by mirroring horizontal movement to
    arm-side positive (pfx_x for LHP, -pfx_x for RHP), buckets arm angle
    into 10-degree bins, and keeps (pitch_type, bucket) cells with at
    least _MIN_BUCKET_PITCHES league pitches. Cached after first call.

    Returns:
        Dict keyed by (pitch_type, bucket lower bound in degrees).
    """
    global _slot_expectations_cache
    if _slot_expectations_cache is not None:
        return _slot_expectations_cache

    df = load_all_statcast(columns=["pitcher", "pitch_type", "p_throws", "arm_angle", "pfx_x", "pfx_z"])
    df = df.filter(
        pl.col("arm_angle").is_not_null()
        & pl.col("pfx_x").is_not_null()
        & pl.col("pfx_z").is_not_null()
        & pl.col("pitch_type").is_not_null()
    )

    arm_side_sign = pl.when(pl.col("p_throws") == "L").then(1.0).otherwise(-1.0)
    df = df.with_columns(
        ((pl.col("arm_angle") / _BUCKET_DEGREES).floor() * _BUCKET_DEGREES)
        .cast(pl.Int32)
        .alias("bucket"),
        (pl.col("pfx_x") * arm_side_sign * _FEET_TO_INCHES).alias("arm_side_run_in"),
        (pl.col("pfx_z") * _FEET_TO_INCHES).alias("ride_in"),
    )

    # Expectation = pitch-weighted league mean shape from this slot.
    agg = (
        df.group_by("pitch_type", "bucket")
        .agg(
            pl.len().alias("n"),
            pl.col("arm_side_run_in").mean().alias("exp_run"),
            pl.col("ride_in").mean().alias("exp_ride"),
        )
        .filter(pl.col("n") >= _MIN_BUCKET_PITCHES)
    )

    # Dispersion = SD of per-pitcher mean shapes within the slot. This is the
    # right z-score denominator for a per-pitcher residual: "how unusual is
    # this pitcher's shape among pitchers from the same slot?" Pitch-level SD
    # would conflate within-pitcher noise and overstate the spread.
    pitcher_means = df.group_by("pitcher", "pitch_type", "bucket").agg(
        pl.len().alias("n_p"),
        pl.col("arm_side_run_in").mean().alias("p_run"),
        pl.col("ride_in").mean().alias("p_ride"),
    ).filter(pl.col("n_p") >= _MIN_PITCHER_PITCHES_FOR_SD)
    bp_std = pitcher_means.group_by("pitch_type", "bucket").agg(
        pl.col("p_run").std().alias("std_run"),
        pl.col("p_ride").std().alias("std_ride"),
    )
    std_lookup = {
        (str(r["pitch_type"]), int(r["bucket"])): r
        for r in bp_std.iter_rows(named=True)
    }

    table: dict[tuple[str, int], SlotExpectation] = {}
    for row in agg.iter_rows(named=True):
        key = (str(row["pitch_type"]), int(row["bucket"]))
        std = std_lookup.get(key, {})
        std_run = std.get("std_run")
        std_ride = std.get("std_ride")
        table[key] = SlotExpectation(
            pitch_type=key[0],
            bucket=key[1],
            n_pitches=int(row["n"]),
            exp_arm_side_run_in=float(row["exp_run"]),
            exp_ride_in=float(row["exp_ride"]),
            std_arm_side_run_in=float(std_run) if std_run is not None else 0.0,
            std_ride_in=float(std_ride) if std_ride is not None else 0.0,
        )

    _slot_expectations_cache = table
    return table


def compute_pitch_shape(data: PitcherData) -> PitchShapeProfile | None:
    """Compute the pitcher's movement-vs-arm-slot profile.

    Uses full-season Statcast rows with arm-angle data (shape is a
    physical trait, not a window trend). Expectations are interpolated
    between league bucket centers at the pitcher's exact mean arm angle.
    Pitch types below _MIN_PITCHER_PITCHES arm-angle pitches are
    skipped, as are types with no league bucket near the slot.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        PitchShapeProfile or None when no pitch type has enough data.
    """
    df = data.statcast.filter(
        pl.col("arm_angle").is_not_null()
        & pl.col("pfx_x").is_not_null()
        & pl.col("pfx_z").is_not_null()
    )
    if df.is_empty():
        return None

    arm_side_sign = pl.when(pl.col("p_throws") == "L").then(1.0).otherwise(-1.0)
    agg = (
        df.with_columns(
            (pl.col("pfx_x") * arm_side_sign * _FEET_TO_INCHES).alias("arm_side_run_in"),
            (pl.col("pfx_z") * _FEET_TO_INCHES).alias("ride_in"),
        )
        .group_by("pitch_type", "pitch_name")
        .agg(
            pl.len().alias("n"),
            pl.col("arm_angle").mean().alias("arm_angle"),
            pl.col("arm_side_run_in").mean().alias("run"),
            pl.col("ride_in").mean().alias("ride"),
        )
        .filter(pl.col("n") >= _MIN_PITCHER_PITCHES)
        .sort("n", descending=True)
    )

    expectations = compute_slot_expectations()

    entries: list[PitchShapeEntry] = []
    for row in agg.iter_rows(named=True):
        pitch_type = str(row["pitch_type"])
        arm_angle = float(row["arm_angle"])
        expected = _interpolate_expectation(expectations, pitch_type, arm_angle)
        if expected is None:
            continue
        exp_run, exp_ride, sd_run, sd_ride = expected

        is_fastball = pitch_type in _FASTBALL_TYPES
        run_residual = float(row["run"]) - exp_run
        ride_residual = float(row["ride"]) - exp_ride
        run_z = _z(run_residual, sd_run)
        ride_z = _z(ride_residual, sd_ride)
        entries.append(
            PitchShapeEntry(
                pitch_type=pitch_type,
                pitch_name=str(row["pitch_name"]),
                is_fastball=is_fastball,
                n_pitches=int(row["n"]),
                arm_angle=arm_angle,
                arm_side_run_in=float(row["run"]),
                ride_in=float(row["ride"]),
                exp_arm_side_run_in=exp_run,
                exp_ride_in=exp_ride,
                run_residual_in=run_residual,
                ride_residual_in=ride_residual,
                run_residual_z=run_z,
                ride_residual_z=ride_z,
                shape_tag=_classify_shape(run_residual, ride_residual, run_z, ride_z, is_fastball),
            )
        )

    if not entries:
        return None
    return PitchShapeProfile(entries=entries)


_MAX_RENDER_ENTRIES = 4
"""Token budget: render at most 4 pitch types, matching context tables."""


def render_pitch_shape(profile: PitchShapeProfile | None) -> str:
    """Render the shape profile as a self-documenting markdown section.

    Explains the DEAD ZONE concept inline so LLM consumers can interpret
    the tags without outside knowledge. Returns an empty string when no
    profile is available so callers can skip the section.
    """
    if profile is None or not profile.entries:
        return ""

    lines = ["## Pitch Shape vs Arm Slot"]
    lines.append(
        "Season movement vs league expectation for the same arm angle, "
        "standardized against how much pitchers actually vary at that slot "
        "(SD = between-pitcher spread). A fastball whose ride and run both "
        "sit within 0.5 SD of slot expectation is a DEAD ZONE pitch -- "
        "statistically the shape hitters' eyes predict from the release "
        "slot. Residuals past 1.5 SD (shown in the tag) are deceptive "
        "traits that play up or down relative to the slot."
    )
    for e in profile.entries[:_MAX_RENDER_ENTRIES]:
        lines.append(
            f"- {e.pitch_name} ({e.pitch_type}): {e.arm_angle:.0f} deg slot; "
            f"ride {e.ride_in:.1f} in (slot exp {e.exp_ride_in:.1f}), "
            f"arm-side run {e.arm_side_run_in:.1f} in (slot exp {e.exp_arm_side_run_in:.1f}) "
            f"-- {e.shape_tag}"
        )
    return "\n".join(lines)
