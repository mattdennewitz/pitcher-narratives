"""Validated PitchingPlus bundle loading and canonical frame selection."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

import polars as pl
from pydantic import ValidationError

from pitcher_narratives.bundle_contract import (
    ArtifactSemantics,
    CalibrationArtifactSemantics,
    MetricSemanticsManifest,
    ModelEvaluationArtifact,
    ProducerIdentity,
)
from pitcher_narratives.fact_provenance import (
    build_manifest_fact_registry,
    manifest_row_id,
    manifest_source,
)
from pitcher_narratives.facts import FactRegistry
from pitcher_narratives.temporal import (
    _DEFAULT_RECENT_APPEARANCES,
    FrameSelection,
    GameKey,
    TemporalFrame,
)

log = logging.getLogger("pitcher_narratives.data")
_CALIBRATION_NOT_REGISTERED = "Calibration artifact is not registered in the PitchingPlus manifest"
_CALIBRATION_MANIFEST_INCOMPATIBLE = "Calibration manifest descriptor is incompatible"
_CALIBRATION_ARTIFACT_UNAVAILABLE = "Registered calibration artifact is unavailable"
_CALIBRATION_CHECKSUM_FAILED = "Calibration artifact failed checksum validation"
_CALIBRATION_ARTIFACT_INCOMPATIBLE = "Calibration artifact is incompatible with its PitchingPlus manifest"
_ATTRIBUTION_GRAIN = "pitcher_type_outcome_appearance"
_ATTRIBUTION_NATURAL_KEY = (
    "season",
    "pitcher",
    "pitch_type",
    "game_date",
    "game_pk",
    "outcome",
)
_ATTRIBUTION_COLUMNS = (
    "season",
    "manifest_id",
    "pitcher",
    "pitch_type",
    "game_date",
    "game_pk",
    "outcome",
    "n_pitches",
    "raw_component_xrv100",
    "raw_total_xrv100",
    "league_centering_offset_xrv100",
    "centered_xrv100_p",
    "run_value_table_version",
)
_ATTRIBUTION_OUTCOMES = frozenset(
    {
        "HBP",
        "called_ball",
        "called_strike",
        "whiff",
        "foul",
        "double",
        "ground_out",
        "home_run",
        "line_out",
        "low_line_out",
        "pop_out",
        "single",
        "triple",
    }
)

__all__ = [
    "AGGS_DIR",
    "PITCH_NAMES",
    "FrameIntegrityError",
    "IncompatiblePitchingPlusExport",
    "PitcherData",
    "PitchingPlusBundle",
    "classify_appearances",
    "classify_game_roles",
    "compute_pitch_type_baseline",
    "compute_season_baseline",
    "filter_to_frame",
    "filter_to_recent_appearances",
    "load_emitted_grain",
    "load_pitcher_data",
    "load_pitchingplus_bundle",
    "make_frame_selection",
    "validated_join",
]

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent
_data_dir_override = os.environ.get("PITCHER_NARRATIVES_DATA_DIR")
DATA_DIR = Path(_data_dir_override) if _data_dir_override else _DEFAULT_DATA_DIR
_YEARS: list[int] = [2025, 2026]
AGGS_DIR = DATA_DIR / "var" / "aggs"

PITCH_NAMES = {
    "CH": "Changeup",
    "CS": "Slow Curve",
    "CU": "Curveball",
    "EP": "Eephus",
    "FA": "Fastball",
    "FC": "Cutter",
    "FF": "4-Seam Fastball",
    "FO": "Forkball",
    "FS": "Split-Finger",
    "KC": "Knuckle Curve",
    "KN": "Knuckleball",
    "SC": "Screwball",
    "SI": "Sinker",
    "SL": "Slider",
    "ST": "Sweeper",
    "SV": "Slurve",
}


class IncompatiblePitchingPlusExport(ValueError):
    """The producer bundle is missing, stale, or semantically incompatible."""


class FrameIntegrityError(ValueError):
    """Emitted rows disagree with an explicit frame or join contract."""


def filter_to_frame(df: pl.DataFrame, frame: FrameSelection) -> pl.DataFrame:
    """Select exact emitted rows by season, date, and game identity."""
    required = {"game_date", "game_pk"}
    missing = required - set(df.columns)
    if missing:
        raise FrameIntegrityError(f"frame filtering requires columns: {sorted(missing)}")
    season_column = "season" if "season" in df.columns else "game_year"
    if season_column not in df.columns:
        raise FrameIntegrityError("frame filtering requires season or game_year")
    if "season" in df.columns and "game_year" in df.columns:
        disagreement = df.filter(pl.col("season") != pl.col("game_year"))
        if not disagreement.is_empty():
            keys = disagreement.select("season", "game_year", "game_date", "game_pk").to_dicts()
            raise FrameIntegrityError(f"emitted season and game_year disagree for rows: {keys}")
    if not frame.games:
        return df.clear()

    keys = pl.DataFrame(
        {
            "_frame_season": [game.season for game in sorted(frame.games)],
            "game_date": [game.game_date for game in sorted(frame.games)],
            "game_pk": [game.game_pk for game in sorted(frame.games)],
        }
    )
    working = df.with_columns(pl.col(season_column).alias("_row_season"))
    candidates = working.join(
        keys,
        on=["game_date", "game_pk"],
        how="inner",
        validate="m:1",
    )
    mismatched = candidates.filter(pl.col("_row_season") != pl.col("_frame_season"))
    if not mismatched.is_empty():
        mismatch_keys = (
            mismatched.select("_row_season", "_frame_season", "game_date", "game_pk").unique().to_dicts()
        )
        raise FrameIntegrityError(f"emitted rows disagree with requested frame season: {mismatch_keys}")
    return candidates.filter(pl.col("game_date") <= frame.as_of).drop("_row_season", "_frame_season")


def _normalize_platoon_analysis_rows(rows: pl.DataFrame) -> pl.DataFrame:
    """Translate producer hand-pair codes for consumer side calculations.

    Manifest rows and their fact lineage retain the raw LL/LR/RL/RR code.
    Only the analysis copy consumed by legacy same/opposite computations is
    normalized.
    """
    if "platoon_matchup" not in rows.columns or rows.is_empty():
        return rows
    codes = set(rows["platoon_matchup"].drop_nulls().cast(pl.String).to_list())
    allowed = {"LL", "LR", "RL", "RR"}
    if invalid := codes - allowed:
        raise IncompatiblePitchingPlusExport(
            f"producer platoon_matchup codes are incompatible: {sorted(invalid)}"
        )
    return rows.with_columns(
        pl.col("platoon_matchup")
        .replace_strict(
            {
                "LL": "same",
                "RR": "same",
                "LR": "opposite",
                "RL": "opposite",
            }
        )
        .alias("platoon_matchup")
    )


def make_frame_selection(
    rows: pl.DataFrame,
    *,
    temporal_frame: TemporalFrame,
    as_of: date,
    source_population: str,
    scoring_season: int | None = None,
    allow_calendar_year_fallback: bool = False,
) -> FrameSelection:
    """Build an exact frame from emitted game identities at an as-of boundary."""
    required = {"game_date", "game_pk"}
    missing = required - set(rows.columns)
    if missing:
        raise FrameIntegrityError(f"frame selection requires columns: {sorted(missing)}")
    season_column = "season" if "season" in rows.columns else "game_year"
    if season_column not in rows.columns and not allow_calendar_year_fallback:
        raise FrameIntegrityError("frame selection requires season or game_year")

    games: set[GameKey] = set()
    for row in (
        rows.select("game_date", "game_pk", *([season_column] if season_column in rows.columns else []))
        .unique()
        .iter_rows(named=True)
    ):
        game_date = row["game_date"]
        if isinstance(game_date, datetime):
            game_date = game_date.date()
        if not isinstance(game_date, date):
            game_date = date.fromisoformat(str(game_date))
        if game_date > as_of:
            continue
        season = int(row[season_column]) if season_column in row else game_date.year
        games.add(
            GameKey(
                season=season,
                game_date=game_date,
                game_pk=int(row["game_pk"]),
            )
        )
    return FrameSelection.create(
        temporal_frame=temporal_frame,
        games=frozenset(games),
        as_of=as_of,
        source_population=source_population,
        scoring_season=scoring_season,
    )


def _scope_producer_artifact_rows(
    artifact_rows: Mapping[
        tuple[int, str],
        tuple[ArtifactSemantics, pl.DataFrame],
    ],
    *,
    frame: FrameSelection,
) -> dict[tuple[int, str], tuple[ArtifactSemantics, pl.DataFrame]]:
    """Bind game grains to exact frame keys and aggregate grains to its season."""
    if frame.scoring_season is None:
        raise FrameIntegrityError("producer rows require a frame scoring season")
    scoped: dict[tuple[int, str], tuple[ArtifactSemantics, pl.DataFrame]] = {}
    for key, (artifact, rows) in artifact_rows.items():
        game_columns = {"game_date", "game_pk"}.intersection(rows.columns)
        if game_columns:
            if game_columns != {"game_date", "game_pk"}:
                raise FrameIntegrityError(f"{artifact.grain} game-keyed rows require game_date and game_pk")
            selected = filter_to_frame(rows, frame)
        elif artifact.season != frame.scoring_season:
            continue
        else:
            selected = rows
            season_column = "season" if "season" in rows.columns else "game_year"
            if season_column in rows.columns:
                selected = rows.filter(pl.col(season_column) == frame.scoring_season)
        scoped[key] = (artifact, selected)
    return scoped


def validated_join(
    left: pl.DataFrame,
    right: pl.DataFrame,
    *,
    on: list[str],
    cardinality: str,
    required: bool,
    left_name: str,
    right_name: str,
    how: str = "inner",
) -> pl.DataFrame:
    """Join emitted grains only after enforcing cardinality and row coverage."""
    valid_cardinalities = {"1:1", "1:m", "m:1", "m:m"}
    if cardinality not in valid_cardinalities:
        raise ValueError(f"unknown join cardinality: {cardinality}")
    missing_left = set(on) - set(left.columns)
    missing_right = set(on) - set(right.columns)
    if missing_left or missing_right:
        raise IncompatiblePitchingPlusExport(
            f"join keys missing; {left_name}={sorted(missing_left)}, {right_name}={sorted(missing_right)}"
        )
    if cardinality in {"1:1", "1:m"} and left.unique(subset=on).height != left.height:
        duplicates = left.group_by(on).len().filter(pl.col("len") > 1).select(on).to_dicts()
        raise IncompatiblePitchingPlusExport(
            f"{left_name} has duplicate natural keys for {cardinality} join: {duplicates}"
        )
    if cardinality in {"1:1", "m:1"} and right.unique(subset=on).height != right.height:
        duplicates = right.group_by(on).len().filter(pl.col("len") > 1).select(on).to_dicts()
        raise IncompatiblePitchingPlusExport(
            f"{right_name} has duplicate natural keys for {cardinality} join: {duplicates}"
        )

    joined = left.join(right, on=on, how=how, validate=cardinality)
    if required and how == "inner":
        matched_keys = joined.select(on).unique()
        dropped = left.select(on).unique().join(matched_keys, on=on, how="anti")
        if not dropped.is_empty():
            raise IncompatiblePitchingPlusExport(
                f"required {left_name}->{right_name} join dropped keys: {dropped.to_dicts()}"
            )
    return joined


@dataclass(frozen=True)
class PitchingPlusBundle:
    """Validated PitchingPlus manifests and manifest-covered artifact rows."""

    root: Path
    manifests: Mapping[int, MetricSemanticsManifest]
    producer_identity: ProducerIdentity
    frames: Mapping[tuple[int, str], pl.DataFrame]
    calibration_reports: Mapping[int, ModelEvaluationArtifact]
    calibration_descriptors: Mapping[int, CalibrationArtifactSemantics]
    calibration_unavailable: Mapping[int, str]

    def frame(self, grain: str, seasons: Iterable[int] | None = None) -> pl.DataFrame:
        selected = sorted(self.manifests if seasons is None else set(seasons))
        frames = [self.frames[(season, grain)] for season in selected if (season, grain) in self.frames]
        if not frames:
            return pl.DataFrame()
        if len(frames) == 1:
            return frames[0]
        return pl.concat(frames, how="diagonal_relaxed")


def _bundle_snapshot_version(
    bundle: PitchingPlusBundle,
    requested_seasons: tuple[int, ...],
) -> str:
    """Hash the complete validated semantic/checksum identity of one load."""
    payload = [
        {
            "manifest": bundle.manifests[season].model_dump(mode="json"),
            "calibration": (
                descriptor.model_dump(mode="json")
                if (descriptor := bundle.calibration_descriptors.get(season)) is not None
                else None
            ),
        }
        for season in sorted(requested_seasons)
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_CONSUMED_NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "all_pitches": ("game_pk", "at_bat_number", "pitch_number"),
    "pitcher": ("season", "level", "game_type", "pitcher"),
    "pitcher_type": ("season", "level", "game_type", "pitcher", "pitch_type"),
    "pitcher_type_appearance": ("season", "pitcher", "game_pk", "pitch_type"),
    "pitcher_type_platoon": (
        "season",
        "level",
        "game_type",
        "pitcher",
        "pitch_type",
        "platoon_matchup",
    ),
    "pitcher_type_platoon_appearance": (
        "season",
        "pitcher",
        "game_pk",
        "pitch_type",
        "platoon_matchup",
    ),
    "pitch_type_reference": ("season", "pitch_type", "metric"),
    "pitch_type_slot_reference": (
        "season",
        "pitch_type",
        "arm_angle_bucket",
        "metric",
    ),
}
_PSL_GRAINS = frozenset(
    {
        "all_pitches",
        "pitcher",
        "pitcher_type",
        "pitcher_type_appearance",
        "pitcher_type_platoon",
        "pitcher_type_platoon_appearance",
    }
)
_CONSUMED_IDENTITY_COLUMNS: dict[str, frozenset[str]] = {
    "all_pitches": frozenset(
        {
            "season",
            "level",
            "game_type",
            "game_date",
            "pitcher",
            "player_name",
            "p_throws",
            "inning",
            "pitch_type",
            "release_spin_rate",
            "release_speed",
            "pfx_x",
            "pfx_z",
            "release_pos_x",
            "release_pos_z",
            "release_extension",
            "description",
            "events",
            "zone",
            "stand",
            "launch_speed",
            "arm_angle",
            "arm_side_pfx_x",
        }
    ),
    "pitcher": frozenset({"player_name", "p_throws", "n_pitches"}),
    "pitcher_type": frozenset({"player_name", "p_throws", "n_pitches"}),
    "pitcher_type_appearance": frozenset({"game_date", "player_name", "p_throws", "n_pitches"}),
    "pitcher_type_platoon": frozenset({"player_name", "p_throws", "n_pitches"}),
    "pitcher_type_platoon_appearance": frozenset({"game_date", "player_name", "p_throws", "n_pitches"}),
    "pitch_type_reference": frozenset(
        {
            "manifest_id",
            "seasons",
            "level",
            "game_types",
            "pitcher_handling",
            "statistical_unit",
            "weighting",
            "unit",
            "n_pitches",
            "mean",
            "std",
        }
    ),
    "pitch_type_slot_reference": frozenset(
        {
            "manifest_id",
            "seasons",
            "level",
            "game_types",
            "pitcher_handling",
            "statistical_unit",
            "weighting",
            "unit",
            "n_pitches",
            "mean",
            "std",
        }
    ),
}


def _validate_consumed_artifact_contract(artifact: ArtifactSemantics) -> None:
    """Require exact natural keys and every column used by the consumer."""
    expected_key = _CONSUMED_NATURAL_KEYS.get(artifact.grain)
    if expected_key is None:
        return
    if artifact.natural_key != expected_key:
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} natural key is incompatible: "
            f"{artifact.natural_key!r} (expected {expected_key!r})"
        )
    required = set(expected_key) | set(_CONSUMED_IDENTITY_COLUMNS.get(artifact.grain, ()))
    if artifact.grain in _PSL_GRAINS:
        xrv_names = (
            {"xRV_P", "xRV_S", "xRV_L"}
            if artifact.grain == "all_pitches"
            else {"xRV100_P", "xRV100_S", "xRV100_L"}
        )
        required.update(xrv_names | {"P+", "S+", "L+"})
    missing = required - set(artifact.required_columns)
    if missing:
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} is missing required consumed columns: {sorted(missing)}"
        )


def _validate_consumed_metric_semantics(artifact: ArtifactSemantics) -> None:
    """Require one complete canonical P/S/L contract for consumed grains."""
    if artifact.grain not in _PSL_GRAINS:
        return
    pitch_grain = artifact.grain == "all_pitches"
    xrv_names = ("xRV_P", "xRV_S", "xRV_L") if pitch_grain else ("xRV100_P", "xRV100_S", "xRV100_L")
    grade_names = ("P+", "S+", "L+")
    consumed_columns = set(xrv_names) | set(grade_names)
    missing_columns = consumed_columns - set(artifact.required_columns)
    if missing_columns:
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} is missing required P/S/L columns: {sorted(missing_columns)}"
        )
    missing = consumed_columns - set(artifact.metrics)
    if missing:
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} P/S/L metric semantics are incomplete: {sorted(missing)}"
        )

    expected_population = f"{artifact.season} MLB regular season pitches"
    expected_by_variant = {
        "P": (None, "actual_count_conditioned_prediction"),
        "S": ("count_matched", "count_matched_prediction"),
        "L": (None, "P_minus_count_matched_S"),
    }
    for index, variant in enumerate(("P", "S", "L")):
        for name, is_grade in ((xrv_names[index], False), (grade_names[index], True)):
            metric = artifact.metrics[name]
            expected_s_product, expected_count_treatment = expected_by_variant[variant]
            expected = {
                "variant": variant,
                "s_product": expected_s_product,
                "domain": "normalized_run_value" if is_grade else "centered_run_value",
                "unit": (
                    "plus_grade"
                    if is_grade
                    else ("runs_per_pitch" if pitch_grain else "runs_per_100_pitches")
                ),
                "precision": "full" if pitch_grain and not is_grade else 3,
                "benchmark": 100.0 if is_grade else 0.0,
                "higher_is_better": is_grade,
                "aggregation": (
                    "per_pitch_transform"
                    if is_grade and pitch_grain
                    else (
                        "transform_of_pitch_weighted_mean"
                        if is_grade
                        else ("emitted_value" if pitch_grain else "pitch_weighted_mean")
                    )
                ),
                "statistical_unit": "pitch",
                "weighting": "unweighted" if pitch_grain else "pitch_weighted",
                "count_treatment": expected_count_treatment,
                "reference_population": expected_population,
            }
            actual = {field: getattr(metric, field) for field in expected}
            if actual != expected:
                mismatched = ", ".join(
                    f"{field}={actual[field]!r} (expected {expected[field]!r})"
                    for field in sorted(expected)
                    if actual[field] != expected[field]
                )
                raise IncompatiblePitchingPlusExport(
                    f"{artifact.filename} {name} semantics are incompatible: {mismatched}"
                )
    core_names = set(xrv_names) | set(grade_names)
    for name, metric in artifact.metrics.items():
        if name in core_names or not name.endswith(("_P", "_S")):
            continue
        variant = name[-1]
        home_run_rate = name.startswith("xHR100_")
        expected = {
            "variant": variant,
            "s_product": "count_matched" if variant == "S" else None,
            "domain": "home_run_rate" if home_run_rate else "event_probability",
            "unit": "events_per_100_pitches" if home_run_rate else "probability",
            "benchmark": None,
            "higher_is_better": False if home_run_rate else None,
            "aggregation": (
                "pitch_weighted_mean"
                if home_run_rate
                else ("emitted_value" if pitch_grain else "pitch_weighted_mean")
            ),
            "statistical_unit": "pitch",
            "weighting": (
                "pitch_weighted" if home_run_rate else ("unweighted" if pitch_grain else "pitch_weighted")
            ),
            "count_treatment": (
                "count_matched_prediction" if variant == "S" else "actual_count_conditioned_prediction"
            ),
            "reference_population": expected_population,
        }
        actual = {field: getattr(metric, field) for field in expected}
        if actual != expected:
            mismatched = ", ".join(
                f"{field}={actual[field]!r} (expected {expected[field]!r})"
                for field in sorted(expected)
                if actual[field] != expected[field]
            )
            raise IncompatiblePitchingPlusExport(
                f"{artifact.filename} {name} semantics are incompatible: {mismatched}"
            )


def _validate_psl_values(
    artifact: ArtifactSemantics,
    frame: pl.DataFrame,
) -> None:
    """Verify formal L within the precision declared for P, S, and L."""
    names = (
        ("xRV_P", "xRV_S", "xRV_L")
        if artifact.grain == "all_pitches"
        else ("xRV100_P", "xRV100_S", "xRV100_L")
    )
    if not set(names) <= set(frame.columns):
        return
    p_name, s_name, l_name = names
    rounding_tolerance = math.fsum(
        0.5 * (10.0**-precision)
        for name in names
        if isinstance((precision := artifact.metrics[name].precision), int)
    )
    tolerance = max(rounding_tolerance, 1e-9) + 1e-12
    invalid = frame.filter(
        pl.any_horizontal(pl.col(name).is_null() | ~pl.col(name).is_finite() for name in names)
        | ((pl.col(p_name) - pl.col(s_name) - pl.col(l_name)).abs() > tolerance)
    )
    if not invalid.is_empty():
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} formal L values do not equal P minus count-matched S"
        )
    grade_names = ("P+", "S+", "L+")
    invalid_grades = frame.filter(
        pl.any_horizontal(pl.col(name).is_null() | ~pl.col(name).is_finite() for name in grade_names)
    )
    if not invalid_grades.is_empty():
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} P/S/L grades contain null or non-finite values"
        )


def _validate_attribution_artifact(
    artifact: ArtifactSemantics,
    frame: pl.DataFrame,
) -> None:
    """Reject ambiguous or non-reconciling producer attribution."""
    if artifact.natural_key != _ATTRIBUTION_NATURAL_KEY:
        raise IncompatiblePitchingPlusExport(f"{artifact.filename} attribution natural key is incompatible")
    if artifact.required_columns != _ATTRIBUTION_COLUMNS:
        raise IncompatiblePitchingPlusExport(f"{artifact.filename} attribution columns are incompatible")
    expected_metrics = {
        "raw_component_xrv100": (
            "P",
            "raw_outcome_run_value_contribution",
            "pitch_weighted_mean_by_outcome",
            "actual_count_conditioned_prediction",
        ),
        "raw_total_xrv100": (
            "P",
            "raw_expected_run_value",
            "sum_of_outcome_components",
            "actual_count_conditioned_prediction",
        ),
        "league_centering_offset_xrv100": (
            "derived",
            "league_centering_offset",
            "centered_minus_raw",
            "league_reference_centering_adjustment",
        ),
        "centered_xrv100_p": (
            "P",
            "centered_run_value",
            "pitch_weighted_mean",
            "actual_count_conditioned_prediction_league_centered",
        ),
    }
    if set(artifact.metrics) != set(expected_metrics):
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} attribution metric semantics are incomplete"
        )
    for name, expected in expected_metrics.items():
        metric = artifact.metrics[name]
        actual = (
            metric.variant,
            metric.domain,
            metric.aggregation,
            metric.count_treatment,
        )
        expected_benchmark = 0.0 if name == "centered_xrv100_p" else None
        expected_higher_is_better = False if metric.variant == "P" else None
        if (
            actual != expected
            or metric.unit != "runs_per_100_pitches"
            or metric.precision != "full"
            or metric.statistical_unit != "appearance"
            or metric.weighting != "pitch_weighted"
            or metric.benchmark != expected_benchmark
            or metric.higher_is_better != expected_higher_is_better
            or metric.reference_population != f"{artifact.season} MLB regular season pitches"
        ):
            raise IncompatiblePitchingPlusExport(f"{artifact.filename} {name} semantics are incompatible")
    if frame.is_empty():
        return

    if frame.filter(
        (pl.col("n_pitches") <= 0)
        | pl.col("manifest_id").is_null()
        | (pl.col("manifest_id").str.len_chars() == 0)
        | pl.col("run_value_table_version").is_null()
        | (pl.col("run_value_table_version").str.len_chars() == 0)
    ).height:
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} attribution provenance or sample size is invalid"
        )
    expected_manifest_id = f"pitchingplus:outcome-attribution:v1:{artifact.season}"
    if frame["manifest_id"].unique().to_list() != [expected_manifest_id]:
        raise IncompatiblePitchingPlusExport(
            f"{artifact.filename} attribution manifest identity is incompatible"
        )
    if frame["run_value_table_version"].n_unique() != 1:
        raise IncompatiblePitchingPlusExport(f"{artifact.filename} attribution mixes run-value tables")
    numeric_columns = (
        "raw_component_xrv100",
        "raw_total_xrv100",
        "league_centering_offset_xrv100",
        "centered_xrv100_p",
    )
    if frame.select(
        pl.any_horizontal(
            pl.col(column).is_null() | ~pl.col(column).is_finite() for column in numeric_columns
        ).any()
    ).item():
        raise IncompatiblePitchingPlusExport(f"{artifact.filename} attribution contains non-finite values")

    group_columns = [
        "season",
        "pitcher",
        "pitch_type",
        "game_date",
        "game_pk",
    ]
    repeated_columns = (
        "manifest_id",
        "n_pitches",
        "raw_total_xrv100",
        "league_centering_offset_xrv100",
        "centered_xrv100_p",
        "run_value_table_version",
    )
    for group in frame.partition_by(group_columns, maintain_order=True):
        if set(group["outcome"].to_list()) != _ATTRIBUTION_OUTCOMES:
            raise IncompatiblePitchingPlusExport(
                f"{artifact.filename} attribution must contain exactly 13 canonical outcomes"
            )
        if any(group[column].n_unique() != 1 for column in repeated_columns):
            raise IncompatiblePitchingPlusExport(
                f"{artifact.filename} attribution group metadata is inconsistent"
            )
        raw_total = float(group["raw_total_xrv100"][0])
        component_sum = float(group["raw_component_xrv100"].sum())
        offset = float(group["league_centering_offset_xrv100"][0])
        centered = float(group["centered_xrv100_p"][0])
        if not math.isclose(
            component_sum,
            raw_total,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise IncompatiblePitchingPlusExport(
                f"{artifact.filename} raw components do not sum to raw total"
            )
        if not math.isclose(
            raw_total + offset,
            centered,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise IncompatiblePitchingPlusExport(
                f"{artifact.filename} raw total and centering offset do not reconcile"
            )


_CORE_AGGREGATE_GROUPS: dict[str, tuple[str, ...]] = {
    "pitcher": ("season", "level", "game_type", "pitcher"),
    "pitcher_type": ("season", "level", "game_type", "pitcher", "pitch_type"),
    "pitcher_type_appearance": (
        "season",
        "pitcher",
        "game_pk",
        "game_date",
        "pitch_type",
    ),
    "pitcher_type_platoon": (
        "season",
        "level",
        "game_type",
        "pitcher",
        "pitch_type",
        "platoon_matchup",
    ),
    "pitcher_type_platoon_appearance": (
        "season",
        "pitcher",
        "game_pk",
        "game_date",
        "pitch_type",
        "platoon_matchup",
    ),
}


def _validate_core_aggregate_reconciliation(
    frames: Mapping[tuple[int, str], pl.DataFrame],
) -> None:
    """Require every emitted core aggregate row to match all-pitches counts."""
    seasons = sorted(season for season, grain in frames if grain == "all_pitches")
    for season in seasons:
        all_pitches = frames[(season, "all_pitches")]
        with_platoon = all_pitches.with_columns(pl.concat_str("p_throws", "stand").alias("platoon_matchup"))
        for grain, group_columns in _CORE_AGGREGATE_GROUPS.items():
            aggregate = frames.get((season, grain))
            if aggregate is None:
                continue
            source = with_platoon if "platoon_matchup" in group_columns else all_pitches
            required = set(group_columns) | {"n_pitches"}
            missing_source = set(group_columns) - set(source.columns)
            missing_aggregate = required - set(aggregate.columns)
            if missing_source or missing_aggregate:
                raise IncompatiblePitchingPlusExport(
                    f"{season}-{grain} reconciliation columns are missing; "
                    f"all_pitches={sorted(missing_source)}, "
                    f"aggregate={sorted(missing_aggregate)}"
                )
            numeric_counts = aggregate.select(
                pl.col("n_pitches").cast(pl.Float64, strict=False).alias("_validated_n_pitches")
            )
            invalid_counts = numeric_counts.filter(
                pl.col("_validated_n_pitches").is_null()
                | ~pl.col("_validated_n_pitches").is_finite()
                | (pl.col("_validated_n_pitches") <= 0)
                | (pl.col("_validated_n_pitches") != pl.col("_validated_n_pitches").floor())
            )
            if not invalid_counts.is_empty():
                raise IncompatiblePitchingPlusExport(
                    f"{season}-{grain} n_pitches must contain finite positive integers"
                )
            expected = source.group_by(group_columns).len(name="_expected_n_pitches")
            actual = aggregate.select(
                *group_columns,
                pl.col("n_pitches").cast(pl.Int64).alias("_actual_n_pitches"),
            )
            mismatches = expected.join(
                actual,
                on=group_columns,
                how="full",
                coalesce=True,
            ).filter(
                pl.col("_expected_n_pitches").is_null()
                | pl.col("_actual_n_pitches").is_null()
                | (pl.col("_expected_n_pitches") != pl.col("_actual_n_pitches"))
            )
            if not mismatches.is_empty():
                raise IncompatiblePitchingPlusExport(
                    f"{season}-{grain} does not reconcile to all_pitches: {mismatches.to_dicts()}"
                )


def load_pitchingplus_bundle(
    root: str | Path | None = None, *, seasons: Iterable[int] = _YEARS
) -> PitchingPlusBundle:
    """Validate every manifest before loading any producer artifact."""
    bundle_root = (Path(root) if root is not None else AGGS_DIR).resolve()
    requested_seasons = tuple(sorted(set(seasons)))
    manifests: dict[int, MetricSemanticsManifest] = {}
    calibration_descriptors: dict[int, CalibrationArtifactSemantics] = {}
    calibration_unavailable: dict[int, str] = {}

    for season in requested_seasons:
        manifest_path = bundle_root / f"{season}-metric-semantics.json"
        if not manifest_path.is_file():
            raise IncompatiblePitchingPlusExport(
                f"PitchingPlus semantic manifest is missing for season {season}"
            )
        manifest_path = manifest_path.resolve()
        if manifest_path.parent != bundle_root:
            raise IncompatiblePitchingPlusExport(
                f"PitchingPlus semantic manifest escapes its bundle for season {season}"
            )
        try:
            manifest_payload = json.loads(manifest_path.read_text())
            calibration_payload = manifest_payload.pop("calibration", None)
            manifest = MetricSemanticsManifest.model_validate(manifest_payload)
        except (OSError, ValidationError, ValueError) as exc:
            raise IncompatiblePitchingPlusExport(
                f"Incompatible PitchingPlus manifest for season {season}: {exc}"
            ) from exc
        if calibration_payload is None:
            calibration_unavailable[season] = _CALIBRATION_NOT_REGISTERED
        else:
            try:
                calibration_descriptor = CalibrationArtifactSemantics.model_validate(calibration_payload)
            except (ValidationError, ValueError) as exc:
                log.warning(
                    "Ignoring incompatible calibration descriptor for %s: %r",
                    season,
                    exc,
                )
                calibration_unavailable[season] = _CALIBRATION_MANIFEST_INCOMPATIBLE
            else:
                if calibration_descriptor.producer_identity != manifest.producer_identity:
                    calibration_unavailable[season] = _CALIBRATION_MANIFEST_INCOMPATIBLE
                else:
                    calibration_descriptors[season] = calibration_descriptor
                    manifest = manifest.model_copy(update={"calibration": calibration_descriptor})
        if manifest.season != season:
            raise IncompatiblePitchingPlusExport(
                f"Manifest season {manifest.season} does not match requested season {season}"
            )
        for artifact in manifest.artifacts:
            _validate_consumed_artifact_contract(artifact)
            _validate_consumed_metric_semantics(artifact)
        manifests[season] = manifest

    identities = {manifest.producer_identity for manifest in manifests.values()}
    if len(identities) != 1:
        raise IncompatiblePitchingPlusExport("requested manifests disagree on producer identity")
    producer_identity = next(iter(identities))

    # Validate the complete bundle before parsing any CSV. A substituted file
    # cannot influence schemas, context, or agent input.
    artifact_paths: dict[tuple[int, str], tuple[Path, ArtifactSemantics]] = {}
    for season, manifest in manifests.items():
        for artifact in manifest.artifacts:
            key = (season, artifact.grain)
            if key in artifact_paths:
                raise IncompatiblePitchingPlusExport(
                    f"Duplicate artifact grain {artifact.grain!r} for season {season}"
                )
            try:
                path = (bundle_root / artifact.filename).resolve(strict=True)
            except OSError as exc:
                raise IncompatiblePitchingPlusExport(
                    f"Manifest-covered artifact is missing: {artifact.filename}"
                ) from exc
            if path.parent != bundle_root or not path.is_file():
                raise IncompatiblePitchingPlusExport(
                    f"Manifest-covered artifact escapes its bundle: {artifact.filename}"
                )
            digest = hashlib.sha256()
            with path.open("rb") as artifact_file:
                for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                    digest.update(chunk)
            checksum = digest.hexdigest()
            if checksum != artifact.sha256:
                raise IncompatiblePitchingPlusExport(f"Artifact checksum mismatch: {artifact.filename}")
            artifact_paths[key] = (path, artifact)

    frames: dict[tuple[int, str], pl.DataFrame] = {}
    for key, (path, artifact) in artifact_paths.items():
        frame = pl.read_csv(path)
        actual_columns = set(frame.columns)
        required_columns = set(artifact.required_columns)
        if actual_columns != required_columns:
            raise IncompatiblePitchingPlusExport(
                f"{artifact.filename} columns differ from its semantic manifest"
            )
        for season_column in ("season", "game_year"):
            if season_column not in frame.columns:
                continue
            invalid_seasons = frame.filter(
                pl.col(season_column).is_null() | (pl.col(season_column) != artifact.season)
            )
            if not invalid_seasons.is_empty():
                values = invalid_seasons[season_column].unique().to_list()
                raise IncompatiblePitchingPlusExport(
                    f"{artifact.filename} row season values {values} do not "
                    f"match manifest season {artifact.season}"
                )
        if "game_date" in frame.columns and frame.schema["game_date"] == pl.String:
            frame = frame.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))
        natural_key = list(artifact.natural_key)
        if frame.select(pl.any_horizontal(pl.col(natural_key).is_null()).any()).item():
            raise IncompatiblePitchingPlusExport(f"{artifact.filename} contains null natural-key values")
        if frame.unique(subset=natural_key).height != frame.height:
            raise IncompatiblePitchingPlusExport(f"{artifact.filename} contains duplicate natural-key rows")
        _validate_psl_values(artifact, frame)
        if artifact.grain == _ATTRIBUTION_GRAIN:
            _validate_attribution_artifact(artifact, frame)
        frames[key] = frame
    _validate_core_aggregate_reconciliation(frames)

    calibration_reports: dict[int, ModelEvaluationArtifact] = {}
    resolved_bundle_root = bundle_root
    for season, descriptor in calibration_descriptors.items():
        unavailable_reason = _CALIBRATION_ARTIFACT_UNAVAILABLE
        try:
            path = (resolved_bundle_root / descriptor.filename).resolve(strict=True)
            if path.parent != resolved_bundle_root or not path.is_file():
                unavailable_reason = _CALIBRATION_ARTIFACT_INCOMPATIBLE
                raise ValueError("registered calibration path escapes its bundle")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != descriptor.sha256:
                unavailable_reason = _CALIBRATION_CHECKSUM_FAILED
                raise ValueError("calibration checksum mismatch")
            unavailable_reason = _CALIBRATION_ARTIFACT_INCOMPATIBLE
            report = ModelEvaluationArtifact.model_validate_json(path.read_text())
            metadata = report.metadata
            compatibility = {
                "artifact_schema_version": (
                    descriptor.artifact_schema_version,
                    report.schema_version,
                ),
                "scoring_population": (
                    descriptor.scoring_population,
                    metadata.scoring_population,
                ),
                "dataset_years": (
                    descriptor.dataset_years,
                    metadata.dataset_years,
                ),
                "row_counts": (
                    descriptor.row_counts,
                    metadata.row_counts.model_dump(),
                ),
                "producer_identity": (
                    descriptor.producer_identity,
                    metadata.producer_identity,
                ),
                "pitch_set_sha256_by_family": (
                    descriptor.pitch_set_sha256_by_family,
                    metadata.pitch_set_sha256_by_family,
                ),
                "split_seed": (
                    descriptor.split_seed,
                    metadata.split_seed,
                ),
                "temporal_holdout_year": (
                    descriptor.temporal_holdout_year,
                    metadata.split_policy.temporal_holdout_year,
                ),
                "arm_angle_policy": (
                    descriptor.arm_angle_policy,
                    metadata.split_policy.arm_angle_policy,
                ),
                "validation_policy": (
                    descriptor.validation_policy,
                    metadata.split_policy.validation,
                ),
                "learned_artifacts_policy": (
                    descriptor.learned_artifacts_policy,
                    metadata.split_policy.learned_artifacts_fit_on,
                ),
                "as_of": (descriptor.as_of, metadata.as_of),
            }
            mismatched = [name for name, (declared, actual) in compatibility.items() if declared != actual]
            if mismatched:
                raise ValueError(f"calibration artifact differs from manifest fields: {mismatched}")
        except (OSError, ValidationError, ValueError) as exc:
            log.warning(
                "Ignoring calibration artifact for %s: %r",
                season,
                exc,
            )
            calibration_unavailable[season] = unavailable_reason
        else:
            calibration_reports[season] = report
            calibration_unavailable.pop(season, None)

    return PitchingPlusBundle(
        root=bundle_root,
        manifests=manifests,
        producer_identity=producer_identity,
        frames=frames,
        calibration_reports=calibration_reports,
        calibration_descriptors=calibration_descriptors,
        calibration_unavailable=calibration_unavailable,
    )


def load_emitted_grain(
    grain: str,
    *,
    root: str | Path | None = None,
    seasons: Iterable[int] = _YEARS,
) -> pl.DataFrame:
    """Load one manifest-covered grain across requested scoring seasons."""
    bundle = load_pitchingplus_bundle(root, seasons=seasons)
    frames = [
        bundle.frames[(season, grain)]
        for season in sorted(bundle.manifests)
        if (season, grain) in bundle.frames
    ]
    if not frames:
        raise IncompatiblePitchingPlusExport(f"PitchingPlus bundle is missing emitted grain {grain!r}")
    return pl.concat(frames, how="diagonal_relaxed")


# Columns that are identifiers, not metrics (used in baseline computation)
_ID_COLS = frozenset(
    {
        "season",
        "level",
        "game_type",
        "pitcher",
        "player_name",
        "p_throws",
        "team_code",
        "n_pitches",
    }
)


@dataclass
class PitcherData:
    """Bundle of emitted PitchingPlus data scoped by one immutable frame."""

    pitches: pl.DataFrame
    appearances: pl.DataFrame
    window_appearances: pl.DataFrame
    season_baseline: pl.DataFrame
    pitch_type_baseline: pl.DataFrame
    prior_season_baseline: pl.DataFrame
    prior_pitch_type_baseline: pl.DataFrame
    aggregates: dict[str, pl.DataFrame]
    pitcher_id: int
    pitcher_name: str
    throws: str
    frame: FrameSelection | None = None
    producer_identity: ProducerIdentity | None = None
    producer_artifact_grains: frozenset[str] = field(default_factory=frozenset)
    artifact_semantics: dict[str, ArtifactSemantics] = field(default_factory=dict)
    artifact_semantics_by_season: dict[tuple[int, str], ArtifactSemantics] = field(default_factory=dict)
    producer_artifact_rows: dict[tuple[int, str], tuple[ArtifactSemantics, pl.DataFrame]] = field(
        default_factory=dict, repr=False
    )
    fact_registry: FactRegistry | None = field(default=None, repr=False)
    lineage_fact_id: str | None = field(default=None, repr=False)
    calibration: ModelEvaluationArtifact | None = None
    calibration_descriptor: CalibrationArtifactSemantics | None = None
    calibration_unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.frame is not None:
            return
        boundary_rows = self.appearances if self.window_appearances.is_empty() else self.window_appearances
        if boundary_rows.is_empty():
            raise FrameIntegrityError("PitcherData requires an explicit empty frame")
        latest = boundary_rows["game_date"].max()
        if isinstance(latest, datetime):
            latest = latest.date()
        if not isinstance(latest, date):
            latest = date.fromisoformat(str(latest))
        if self.window_appearances.is_empty():
            self.frame = FrameSelection.create(
                temporal_frame=TemporalFrame.RECENT,
                games=frozenset(),
                as_of=latest,
                source_population="legacy-test-fixture",
                scoring_season=latest.year,
            )
        else:
            self.frame = make_frame_selection(
                self.window_appearances,
                temporal_frame=TemporalFrame.RECENT,
                as_of=latest,
                source_population="legacy-test-fixture",
                allow_calendar_year_fallback=True,
            )

    def with_frame(
        self,
        appearances: pl.DataFrame,
        *,
        temporal_frame: TemporalFrame | None = None,
    ) -> PitcherData:
        """Return a copy whose appearance rows and frame identity cannot diverge."""
        if self.frame is None:
            raise FrameIntegrityError("PitcherData has no canonical frame")
        selection = make_frame_selection(
            appearances,
            temporal_frame=temporal_frame or self.frame.temporal_frame,
            as_of=self.frame.as_of,
            source_population=self.frame.source_population,
            scoring_season=self.frame.scoring_season,
            allow_calendar_year_fallback=(self.frame.source_population == "legacy-test-fixture"),
        )
        seasons = {game.season for game in selection.games}
        baseline_changes: dict[str, pl.DataFrame] = {}
        if len(seasons) == 1 and {"pitcher", "pitcher_type"} <= self.aggregates.keys():
            season = next(iter(seasons))
            season_all = compute_season_baseline(self.aggregates["pitcher"])
            pitch_type_all = compute_pitch_type_baseline(self.aggregates["pitcher_type"])
            baseline_changes = {
                "season_baseline": season_all.filter(pl.col("season") == season),
                "prior_season_baseline": season_all.filter(pl.col("season") == season - 1),
                "pitch_type_baseline": pitch_type_all.filter(pl.col("season") == season),
                "prior_pitch_type_baseline": pitch_type_all.filter(pl.col("season") == season - 1),
            }
        result = replace(
            self,
            window_appearances=appearances,
            frame=selection,
            fact_registry=None,
            lineage_fact_id=None,
            **baseline_changes,
        )
        if not self.producer_artifact_rows:
            return result
        scoped_rows = _scope_producer_artifact_rows(
            self.producer_artifact_rows,
            frame=selection,
        )
        calibration = (
            (self.calibration_descriptor, self.calibration)
            if self.calibration_descriptor is not None and self.calibration is not None
            else None
        )
        registry, lineage_fact_id = build_manifest_fact_registry(
            scoped_rows,
            frame=selection,
            producer_identity=self.producer_identity,
            calibration=calibration,
        )
        producer_artifact_grains = frozenset(
            artifact.grain for artifact, rows in scoped_rows.values() if not rows.is_empty()
        )
        if calibration is not None:
            producer_artifact_grains |= {"calibration"}
        return replace(
            result,
            fact_registry=registry,
            lineage_fact_id=lineage_fact_id,
            producer_artifact_grains=producer_artifact_grains,
        )

    def base_fact_ids(
        self,
        grain: str,
        rows: pl.DataFrame,
        columns: Iterable[str],
    ) -> tuple[str, ...]:
        """Resolve already-registered base facts for exact manifest rows."""
        if self.fact_registry is None:
            raise ValueError("PitcherData has no manifest-bound fact registry")
        requested = set(columns)
        index = {
            (fact.source, fact.source_row_id, fact.metric): fact.id
            for fact in self.fact_registry.facts()
            if not fact.source_fact_ids
            and fact.source_row_id is not None
            and fact.metric in {f"{grain}.{column}" for column in requested}
        }
        resolved: set[str] = set()
        for row in rows.iter_rows(named=True):
            season_value = row.get("season", row.get("game_year"))
            if season_value is None:
                raise ValueError(f"{grain} row has no manifest season")
            artifact = self.artifact_semantics_by_season.get((int(season_value), grain))
            if artifact is None:
                raise ValueError(f"{grain} row is not covered by a loaded season manifest")
            row_id = manifest_row_id(artifact, row)
            for column in requested:
                if row.get(column) is None:
                    continue
                key = (manifest_source(grain), row_id, f"{grain}.{column}")
                fact_id = index.get(key)
                if fact_id is None:
                    raise ValueError(f"{grain}.{column} has no registered fact for manifest row {row_id}")
                resolved.add(fact_id)
        return tuple(sorted(resolved))


def classify_appearances(pitches: pl.DataFrame) -> pl.DataFrame:
    """Classify one pitcher's emitted appearances as SP or RP."""
    season_columns = [column for column in ("season", "game_year") if column in pitches.columns]
    return (
        pitches.group_by([*season_columns, "game_pk", "game_date"])
        .agg(
            pl.col("inning").min().alias("first_inning"),
            pl.col("inning").max().alias("last_inning"),
            pl.len().alias("n_pitches"),
            pl.col("player_name").first(),
        )
        .with_columns(
            pl.when(pl.col("first_inning") == 1).then(pl.lit("SP")).otherwise(pl.lit("RP")).alias("role")
        )
        .sort(["game_date", "game_pk"])
    )


def classify_game_roles(pitches: pl.DataFrame) -> pl.DataFrame:
    """Classify every emitted appearance in a league-wide frame as SP or RP."""
    if pitches.is_empty():
        return pl.DataFrame(schema={"game_pk": pl.Int64, "pitcher": pl.Int64, "role": pl.String})
    starters = (
        pitches.group_by(["game_pk", "inning_topbot"])
        .agg(pl.col("pitcher").sort_by("at_bat_number", maintain_order=True, nulls_last=True).first())
        .select("game_pk", "pitcher")
        .unique(subset=["game_pk", "pitcher"])
        .with_columns(pl.lit("SP").alias("role"))
    )
    appearances = pitches.select("game_pk", "pitcher").unique()
    return appearances.join(starters, on=["game_pk", "pitcher"], how="left").with_columns(
        pl.col("role").fill_null("RP")
    )


def compute_season_baseline(pitcher_df: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted per-season MLB baseline for a pitcher.

    Producer manifests define the scoring population before rows reach this
    helper. This additionally restricts the baseline to MLB rows so a mixed
    emitted level cannot leak into the season norm.

    Args:
        pitcher_df: Manifest-covered pitcher aggregate rows.

    Returns:
        DataFrame with one row per pitcher per season with weighted average
        metric values, restricted to MLB level.
    """
    if "level" in pitcher_df.columns:
        pitcher_df = pitcher_df.filter(pl.col("level") == "MLB")
    metric_cols = [c for c in pitcher_df.columns if c not in _ID_COLS]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return pitcher_df.group_by(["pitcher", "season"]).agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted_exprs,
    )


def compute_pitch_type_baseline(pitcher_type_df: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted MLB baseline per pitch type per season.

    Filters out empty pitch_type strings, restricts to MLB rows so
    minor-league (A/AAA) data does not leak into the per-pitch-type norm,
    and combines rows using pitch-count weighting. Includes ``usage_pct``
    -- the percentage of total pitches thrown with each pitch type within
    a season.

    Args:
        pitcher_type_df: Manifest-covered pitch-type aggregate rows.

    Returns:
        DataFrame with one row per pitcher/season/pitch_type and weighted
        average metrics, restricted to MLB level.
    """
    df = pitcher_type_df.filter(pl.col("pitch_type") != "")
    if "level" in df.columns:
        df = df.filter(pl.col("level") == "MLB")
    id_cols = _ID_COLS | {"pitch_type"}
    metric_cols = [c for c in df.columns if c not in id_cols]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    result = df.group_by(["pitcher", "season", "pitch_type"]).agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted_exprs,
    )
    pitcher_totals = df.group_by(["pitcher", "season"]).agg(
        pl.col("n_pitches").sum().alias("total_pitches"),
    )
    return (
        result.join(pitcher_totals, on=["pitcher", "season"])
        .with_columns(
            (pl.col("n_pitches") / pl.col("total_pitches") * 100).alias("usage_pct"),
        )
        .drop("total_pitches")
    )


def filter_to_recent_appearances(df: pl.DataFrame, n: int) -> pl.DataFrame:
    """Filter rows to the ``n`` most-recent distinct appearances.

    An appearance is a unique ``(game_date, game_pk)`` pair, so doubleheaders
    on the same calendar date count as two appearances. Ordering is
    deterministic: most-recent ``game_date`` first, ``game_pk`` descending as
    the tiebreak (matches the Phase-5 G5 most-recent picker). When the frame
    holds fewer than ``n`` distinct appearances, all rows are returned. Works
    at any row granularity (appearance-level or pitch-level) — it dedups on
    the two keys and joins the originals back.

    Args:
        df: DataFrame with ``game_date`` and ``game_pk`` columns.
        n: Number of most-recent appearances to retain.

    Returns:
        The rows belonging to the ``n`` most-recent appearances.
    """
    if df.is_empty():
        return df
    season_column = "season" if "season" in df.columns else "game_year"
    key_columns = [
        *([season_column] if season_column in df.columns else []),
        "game_date",
        "game_pk",
    ]
    recent_keys = (
        df.select(key_columns)
        .unique()
        .sort(["game_date", "game_pk"], descending=True, nulls_last=True)
        .head(n)
    )
    return df.join(recent_keys, on=key_columns, how="inner")


def filter_to_prior_appearances(df: pl.DataFrame, recent_n: int, prior_m: int) -> pl.DataFrame:
    """Filter rows to the ``prior_m`` appearances immediately older than the
    ``recent_n`` most-recent ones.

    An appearance = unique ``(game_date, game_pk)`` pair. Keys are ranked
    most-recent ``game_date`` first, ``game_pk`` descending as tiebreak;
    this returns the rows of the keys ranked ``[recent_n, recent_n + prior_m)``.
    Returns an empty frame when fewer than ``recent_n`` appearances exist, and
    fewer than ``prior_m`` rows when the prior window runs past the season's
    oldest appearance. Works at any row granularity (appearance- or pitch-level).
    """
    if df.is_empty():
        return df
    season_column = "season" if "season" in df.columns else "game_year"
    key_columns = [
        *([season_column] if season_column in df.columns else []),
        "game_date",
        "game_pk",
    ]
    prior_keys = (
        df.select(key_columns)
        .unique()
        .sort(["game_date", "game_pk"], descending=True, nulls_last=True)
        .slice(recent_n, prior_m)
    )
    return df.join(prior_keys, on=key_columns, how="inner")


def load_pitcher_data(
    pitcher_id: int,
    recent_appearances: int = _DEFAULT_RECENT_APPEARANCES,
    *,
    root: str | Path | None = None,
    seasons: Iterable[int] = tuple(_YEARS),
    as_of: date | None = None,
) -> PitcherData:
    """Build pitcher analysis exclusively from a validated PitchingPlus bundle."""
    requested_seasons = tuple(sorted(set(seasons)))
    bundle = load_pitchingplus_bundle(root, seasons=requested_seasons)
    available_grains = {grain for _, grain in bundle.frames}
    required_grains = {
        "all_pitches",
        "pitcher",
        "pitcher_type",
        "pitcher_type_appearance",
        "pitcher_type_platoon",
        "pitcher_type_platoon_appearance",
        "pitch_type_reference",
        "pitch_type_slot_reference",
    }
    for season in requested_seasons:
        season_grains = {grain for artifact_season, grain in bundle.frames if artifact_season == season}
        missing_grains = required_grains - season_grains
        if missing_grains:
            raise IncompatiblePitchingPlusExport(
                f"PitchingPlus {season} bundle is missing required grains: {sorted(missing_grains)}"
            )

    aggregate_rows: dict[str, pl.DataFrame] = {}
    population_grains = {
        "pitch_type_reference",
        "pitch_type_slot_reference",
        "reference_population",
        "run_values",
    }
    for grain in sorted(available_grains):
        rows = bundle.frame(grain, requested_seasons)
        if "pitcher" in rows.columns and grain not in population_grains:
            rows = rows.filter(pl.col("pitcher") == pitcher_id)
        aggregate_rows[grain] = rows

    all_pitches = aggregate_rows["all_pitches"]
    if all_pitches.is_empty():
        raise ValueError(f"Pitcher {pitcher_id} not found")
    required_pitch_fields = {
        "game_date",
        "game_pk",
        "inning",
        "pitch_type",
        "player_name",
        "p_throws",
    }
    missing_pitch_fields = required_pitch_fields - set(all_pitches.columns)
    if missing_pitch_fields:
        raise IncompatiblePitchingPlusExport(
            f"all_pitches is missing emitted fields: {sorted(missing_pitch_fields)}"
        )
    if "pitch_name" not in all_pitches.columns:
        all_pitches = all_pitches.with_columns(
            pl.col("pitch_type").replace_strict(PITCH_NAMES, default=pl.col("pitch_type")).alias("pitch_name")
        )
        aggregate_rows["all_pitches"] = all_pitches
    season_column = "season" if "season" in all_pitches.columns else "game_year"
    if season_column not in all_pitches.columns:
        raise IncompatiblePitchingPlusExport("all_pitches requires an authoritative season or game_year")
    if as_of is None:
        pitcher_seasons = all_pitches[season_column].drop_nulls().unique().to_list()
        default_season = int(max(pitcher_seasons)) if pitcher_seasons else max(requested_seasons)
        boundary = bundle.frames[(default_season, "all_pitches")]["game_date"].max()
    else:
        boundary = as_of
    if isinstance(boundary, datetime):
        boundary = boundary.date()
    if not isinstance(boundary, date):
        boundary = date.fromisoformat(str(boundary))

    for grain, rows in aggregate_rows.items():
        if "game_date" in rows.columns:
            rows = rows.filter(pl.col("game_date") <= boundary)
        if grain in {
            "pitcher_type_platoon",
            "pitcher_type_platoon_appearance",
        }:
            rows = _normalize_platoon_analysis_rows(rows)
        aggregate_rows[grain] = rows
    all_pitches = aggregate_rows["all_pitches"]
    if all_pitches.is_empty():
        raise ValueError(f"Pitcher {pitcher_id} has no pitches on or before {boundary}")

    eligible_seasons = all_pitches[season_column].drop_nulls().unique().to_list()
    current_season = int(max(eligible_seasons)) if eligible_seasons else max(requested_seasons)
    artifact_cutoff = bundle.frames[(current_season, "all_pitches")]["game_date"].max()
    if isinstance(artifact_cutoff, datetime):
        artifact_cutoff = artifact_cutoff.date()
    if artifact_cutoff is not None and not isinstance(artifact_cutoff, date):
        artifact_cutoff = date.fromisoformat(str(artifact_cutoff))
    has_unscoped_aggregate = any(
        season == current_season and "game_date" not in rows.columns and not rows.is_empty()
        for (season, _), rows in bundle.frames.items()
    )
    if artifact_cutoff is not None and boundary < artifact_cutoff and has_unscoped_aggregate:
        raise IncompatiblePitchingPlusExport(
            "historical as_of cannot use season/reference aggregates whose "
            f"artifact cutoff is {artifact_cutoff}"
        )

    appearances = classify_appearances(all_pitches)
    season_appearances = appearances.filter(pl.col(season_column) == current_season)
    window_appearances = filter_to_recent_appearances(season_appearances, recent_appearances)
    source_population = f"pitchingplus:bundle-snapshot:{_bundle_snapshot_version(bundle, requested_seasons)}"
    frame = make_frame_selection(
        window_appearances,
        temporal_frame=TemporalFrame.RECENT,
        as_of=boundary,
        source_population=source_population,
        scoring_season=current_season,
    )

    artifact_semantics_by_season = {
        (season, artifact.grain): artifact
        for season, manifest in bundle.manifests.items()
        for artifact in manifest.artifacts
        if season in requested_seasons
    }
    producer_artifact_rows: dict[tuple[int, str], tuple[ArtifactSemantics, pl.DataFrame]] = {}
    for key, artifact in artifact_semantics_by_season.items():
        rows = bundle.frames[key]
        if "pitcher" in rows.columns and artifact.grain not in population_grains:
            rows = rows.filter(pl.col("pitcher") == pitcher_id)
        if "game_date" in rows.columns:
            rows = rows.filter(pl.col("game_date") <= boundary)
        producer_artifact_rows[key] = (artifact, rows)
    scoped_producer_rows = _scope_producer_artifact_rows(
        producer_artifact_rows,
        frame=frame,
    )
    calibration_descriptor = bundle.calibration_descriptors.get(current_season)
    calibration_report = bundle.calibration_reports.get(current_season)
    calibration = (
        (calibration_descriptor, calibration_report)
        if calibration_descriptor is not None and calibration_report is not None
        else None
    )
    producer_artifact_grains = frozenset(
        artifact.grain for artifact, rows in scoped_producer_rows.values() if not rows.is_empty()
    )
    if calibration is not None:
        producer_artifact_grains |= {"calibration"}
    fact_registry, lineage_fact_id = build_manifest_fact_registry(
        scoped_producer_rows,
        frame=frame,
        producer_identity=bundle.producer_identity,
        calibration=calibration,
    )
    season_baseline_all = compute_season_baseline(aggregate_rows["pitcher"])
    pitch_type_baseline_all = compute_pitch_type_baseline(aggregate_rows["pitcher_type"])
    season_baseline = season_baseline_all.filter(pl.col("season") == current_season)
    prior_season_baseline = season_baseline_all.filter(pl.col("season") == current_season - 1)
    pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") == current_season)
    prior_pitch_type_baseline = pitch_type_baseline_all.filter(pl.col("season") == current_season - 1)

    identity_rows = all_pitches.sort(["game_date", "game_pk"], descending=True)
    return PitcherData(
        pitches=all_pitches,
        appearances=appearances,
        window_appearances=window_appearances,
        season_baseline=season_baseline,
        pitch_type_baseline=pitch_type_baseline,
        prior_season_baseline=prior_season_baseline,
        prior_pitch_type_baseline=prior_pitch_type_baseline,
        aggregates=aggregate_rows,
        pitcher_id=pitcher_id,
        pitcher_name=str(identity_rows["player_name"][0]),
        throws=str(identity_rows["p_throws"][0]),
        producer_identity=bundle.producer_identity,
        producer_artifact_grains=producer_artifact_grains,
        frame=frame,
        artifact_semantics={
            artifact.grain: artifact for artifact in bundle.manifests[current_season].artifacts
        },
        artifact_semantics_by_season=artifact_semantics_by_season,
        producer_artifact_rows=producer_artifact_rows,
        fact_registry=fact_registry,
        lineage_fact_id=lineage_fact_id,
        calibration=bundle.calibration_reports.get(current_season),
        calibration_descriptor=calibration_descriptor,
        calibration_unavailable_reason=bundle.calibration_unavailable.get(current_season),
    )
