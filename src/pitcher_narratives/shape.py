"""Arm-slot movement interaction analysis from emitted PitchingPlus facts.

Pitcher movement uses the producer's handedness-normalized
``arm_side_pfx_x`` value. Slot means and pitch-level spreads come from the
manifest-covered reference artifact; Narratives never scans a local population
or mirrors catcher-view values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import _get_season_rows

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


_DEAD_ZONE_Z = 0.5
"""Residual within this many pitch-level SDs on both axes = slot-typical."""

_FLAG_Z = 1.5
"""Residual beyond this many pitch-level SDs on an axis = a rare trait."""

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
    """Pitch-level SD of arm-side movement within this emitted slot."""

    std_ride_in: float
    """Pitch-level SD of ride within this emitted slot."""


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
    """Run residual in pitch-level SD units for the emitted slot."""

    ride_residual_z: float
    """Ride residual in pitch-level SD units for the emitted slot."""

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

    unavailable_reason: str | None = None
    reference_population: str | None = None


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
    """Classify movement residual rarity against the emitted slot reference.

    Decisions use z-scores (residual / emitted pitch-level SD for the slot) so
    the bands scale with pitch-level variation at that arm angle. A fastball
    within _DEAD_ZONE_Z SD on both axes is slot-typical; a residual beyond
    _FLAG_Z SD on an axis is rare. These labels do not establish importance,
    hitter behavior, deception, or a model mechanism.
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
        return "DEAD ZONE -- movement matches slot expectation on both axes"
    return "In line with slot expectation"


def _z(residual: float, sd: float) -> float:
    """Standardize a residual by emitted pitch-level SD; 0.0 when unusable."""
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
    edges. The pitch-level SDs are interpolated the same way. When one
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


def compute_slot_expectations(
    reference_rows: pl.DataFrame | None = None,
) -> dict[tuple[str, int], SlotExpectation]:
    """Parse a manifest-covered, pitch-weighted slot reference artifact."""
    if reference_rows is None or reference_rows.is_empty():
        return {}
    required = {
        "manifest_id",
        "seasons",
        "level",
        "game_types",
        "pitch_type",
        "arm_angle_bucket",
        "metric",
        "mean",
        "std",
        "n_pitches",
        "unit",
        "pitcher_handling",
        "statistical_unit",
        "weighting",
    }
    if missing := required - set(reference_rows.columns):
        raise ValueError(f"pitch_type_slot_reference is missing columns: {sorted(missing)}")
    rows = reference_rows.filter(
        (pl.col("level") == "MLB")
        & (pl.col("game_types") == "R")
        & (pl.col("unit") == "inches")
        & (pl.col("pitcher_handling") == "handedness_normalized")
        & (pl.col("statistical_unit") == "pitch")
        & (pl.col("weighting") == "pitch_weighted")
    )
    table: dict[tuple[str, int], SlotExpectation] = {}
    for key_rows in rows.partition_by(["pitch_type", "arm_angle_bucket"], maintain_order=True):
        metrics = {str(row["metric"]): row for row in key_rows.iter_rows(named=True)}
        run = metrics.get("arm_side_pfx_x")
        ride = metrics.get("pfx_z")
        if run is None or ride is None:
            continue
        if run["unit"] != "inches" or ride["unit"] != "inches":
            raise ValueError("pitch_type_slot_reference movement metrics must use inches")
        population_fields = (
            "manifest_id",
            "seasons",
            "level",
            "game_types",
            "pitcher_handling",
            "statistical_unit",
            "weighting",
        )
        if any(run[field] != ride[field] for field in population_fields):
            raise ValueError("pitch_type_slot_reference metrics disagree on reference population")
        n_pitches = min(int(run["n_pitches"]), int(ride["n_pitches"]))
        run_std = run["std"]
        ride_std = ride["std"]
        if (
            n_pitches < _MIN_BUCKET_PITCHES
            or run_std is None
            or ride_std is None
            or float(run_std) <= 0
            or float(ride_std) <= 0
        ):
            continue
        pitch_type = str(run["pitch_type"])
        bucket = int(run["arm_angle_bucket"])
        table[(pitch_type, bucket)] = SlotExpectation(
            pitch_type=pitch_type,
            bucket=bucket,
            n_pitches=n_pitches,
            exp_arm_side_run_in=float(run["mean"]),
            exp_ride_in=float(ride["mean"]),
            std_arm_side_run_in=float(run_std),
            std_ride_in=float(ride_std),
        )
    return table


def compute_pitch_shape(data: PitcherData) -> PitchShapeProfile | None:
    """Compare season shape with the emitted absolute slot reference."""
    df = _get_season_rows(data).filter(
        pl.col("arm_angle").is_not_null()
        & pl.col("arm_side_pfx_x").is_not_null()
        & pl.col("pfx_z").is_not_null()
    )
    if df.is_empty():
        return PitchShapeProfile(
            entries=[],
            unavailable_reason="no known-hand season pitches with movement and arm angle",
        )

    agg = (
        df.with_columns(
            (pl.col("arm_side_pfx_x") * _FEET_TO_INCHES).alias("arm_side_run_in"),
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

    reference_rows = data.aggregates.get("pitch_type_slot_reference")
    if (
        reference_rows is not None
        and data.frame is not None
        and data.frame.scoring_season is not None
        and "season" in reference_rows.columns
    ):
        reference_rows = reference_rows.filter(pl.col("season") == data.frame.scoring_season)
    expectations = compute_slot_expectations(reference_rows)
    if not expectations:
        return PitchShapeProfile(
            entries=[],
            unavailable_reason="compatible emitted slot reference unavailable",
        )
    assert reference_rows is not None
    compatible_reference = reference_rows.filter(
        (pl.col("level") == "MLB")
        & (pl.col("game_types") == "R")
        & (pl.col("unit") == "inches")
        & (pl.col("pitcher_handling") == "handedness_normalized")
        & (pl.col("statistical_unit") == "pitch")
        & (pl.col("weighting") == "pitch_weighted")
    )
    first_reference = compatible_reference.row(0, named=True)
    reference_population = (
        f"manifest `{first_reference['manifest_id']}`; seasons "
        f"{first_reference['seasons']}; {first_reference['level']} regular season; "
        f"{str(first_reference['weighting']).replace('_', '-')} pitches; "
        f"{str(first_reference['pitcher_handling']).replace('_', '-')}; "
        f"statistical unit `{first_reference['statistical_unit']}`"
    )

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
        return PitchShapeProfile(
            entries=[],
            unavailable_reason="pitch samples are thin or reference variance is unavailable",
            reference_population=reference_population,
        )
    return PitchShapeProfile(
        entries=entries,
        reference_population=reference_population,
    )


_MAX_RENDER_ENTRIES = 4
"""Token budget: render at most 4 pitch types, matching context tables."""


def render_pitch_shape(profile: PitchShapeProfile | None) -> str:
    """Render computed unavailability while preserving an intentionally omitted profile."""
    if profile is None:
        return ""
    if not profile.entries:
        return (
            f"## Pitch Shape vs Arm Slot\n\nUnavailable: {profile.unavailable_reason or 'insufficient data'}."
        )

    lines = ["## Pitch Shape vs Arm Slot"]
    lines.append(
        "Season movement vs the emitted reference for the same arm-angle slot. "
        "SD is the pitch-level spread and describes absolute physical rarity "
        "only; it is not recent-vs-season change significance, a role "
        "comparison, or model feature importance."
    )
    if profile.reference_population:
        lines.append(f"Population: {profile.reference_population}.")
    for e in profile.entries[:_MAX_RENDER_ENTRIES]:
        lines.append(
            f"- {e.pitch_name} ({e.pitch_type}): {e.arm_angle:.0f} deg slot; "
            f"ride {e.ride_in:.1f} in (slot exp {e.exp_ride_in:.1f}), "
            f"arm-side run {e.arm_side_run_in:.1f} in (slot exp {e.exp_arm_side_run_in:.1f}) "
            f"-- {e.shape_tag}"
        )
    return "\n".join(lines)
