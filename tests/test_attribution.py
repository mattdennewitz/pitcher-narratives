from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from pitcher_narratives.bundle_contract import ArtifactSemantics
from pitcher_narratives.data import (
    IncompatiblePitchingPlusExport,
    PitcherData,
)
from pitcher_narratives.engine.attribution import compute_component_attribution
from pitcher_narratives.fact_provenance import (
    build_manifest_fact_registry,
    register_capability_fact,
)
from pitcher_narratives.pipeline import _build_runvalue_input
from pitcher_narratives.temporal import FrameSelection, GameKey, TemporalFrame

_OUTCOMES = (
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
)


def _appearance_rows(*, pitcher_id: int = 10) -> pl.DataFrame:
    rows = []
    for game_date, game_pk, n_pitches, raw_total, offset in (
        (date(2026, 7, 1), 100, 2, -0.4, 0.1),
        (date(2026, 7, 1), 101, 6, 0.4, 0.1),
    ):
        for index, outcome in enumerate(_OUTCOMES):
            rows.append(
                {
                    "season": 2026,
                    "manifest_id": "pitchingplus:outcome-attribution:v1:2026",
                    "pitcher": pitcher_id,
                    "pitch_type": "FF",
                    "game_date": game_date,
                    "game_pk": game_pk,
                    "outcome": outcome,
                    "n_pitches": n_pitches,
                    "raw_component_xrv100": raw_total if index == 0 else 0.0,
                    "raw_total_xrv100": raw_total,
                    "league_centering_offset_xrv100": offset,
                    "centered_xrv100_p": raw_total + offset,
                    "run_value_table_version": "sha256:run-values-v1",
                }
            )
    return pl.DataFrame(rows)


def _canonical_appearance_rows(*, pitcher_id: int = 10) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2026, 2026],
            "pitcher": [pitcher_id, pitcher_id],
            "pitch_type": ["FF", "FF"],
            "game_date": [date(2026, 7, 1), date(2026, 7, 1)],
            "game_pk": [100, 101],
            "n_pitches": [2, 6],
            "xRV100_P": [-0.3, 0.5],
        }
    )


def _pitcher_data(
    *,
    games: frozenset[GameKey],
    pitcher_id: int = 10,
) -> PitcherData:
    pitch_rows = []
    for game in sorted(games):
        n_pitches = 2 if game.game_pk == 100 else 6
        pitch_rows.extend(
            {
                "season": game.season,
                "game_date": game.game_date,
                "game_pk": game.game_pk,
                "pitcher": pitcher_id,
                "pitch_type": "FF",
                "pitch_name": "4-Seam Fastball",
            }
            for _ in range(n_pitches)
        )
    pitches = pl.DataFrame(pitch_rows)
    frame = FrameSelection.create(
        temporal_frame=TemporalFrame.RECENT,
        games=games,
        as_of=max(game.game_date for game in games),
        source_population="pitchingplus:2026:1.0.0",
        scoring_season=2026,
    )
    empty = pl.DataFrame()
    attribution_rows = _appearance_rows(pitcher_id=pitcher_id)
    attribution_artifact = ArtifactSemantics(
        filename="2026-pitcher_type_outcome_appearance.csv",
        sha256="0" * 64,
        season=2026,
        grain="pitcher_type_outcome_appearance",
        natural_key=(
            "season",
            "pitcher",
            "pitch_type",
            "game_date",
            "game_pk",
            "outcome",
        ),
        required_columns=tuple(attribution_rows.columns),
        metrics={},
    )
    producer_rows = {
        (2026, attribution_artifact.grain): (
            attribution_artifact,
            attribution_rows,
        )
    }
    registry, lineage_fact_id = build_manifest_fact_registry(
        producer_rows,
        frame=frame,
    )
    for capability in (
        "feature_attribution",
        "location_regions",
        "pitch_targets",
        "biomechanical_causality",
        "tunneling_measurement",
        "platoon_splits",
    ):
        register_capability_fact(
            registry=registry,
            capability=capability,
            available=False,
            evidence_fact_ids=(lineage_fact_id,),
            frame=frame,
            producer_condition="synthetic attribution fixture",
        )
    return PitcherData(
        pitches=pitches,
        appearances=pitches,
        window_appearances=pitches,
        season_baseline=empty,
        pitch_type_baseline=empty,
        prior_season_baseline=empty,
        prior_pitch_type_baseline=empty,
        aggregates={
            "all_pitches": pitches,
            "pitcher_type_outcome_appearance": attribution_rows,
            "pitcher_type_appearance": _canonical_appearance_rows(pitcher_id=pitcher_id),
        },
        pitcher_id=pitcher_id,
        pitcher_name=f"Pitcher {pitcher_id}",
        throws="R",
        frame=frame,
        artifact_semantics={attribution_artifact.grain: attribution_artifact},
        artifact_semantics_by_season={(2026, attribution_artifact.grain): attribution_artifact},
        producer_artifact_rows=producer_rows,
        fact_registry=registry,
        lineage_fact_id=lineage_fact_id,
    )


def test_attribution_selects_exact_frame_and_preserves_centering_semantics():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    registry = data.fact_registry
    assert registry is not None

    result = compute_component_attribution(data)

    assert len(result) == 1
    attribution = result[0]
    assert attribution.n_pitches == 6
    assert attribution.raw_total_xrv100 == pytest.approx(0.4)
    assert attribution.league_centering_offset_xrv100 == pytest.approx(0.1)
    assert attribution.centered_xrv100_p == pytest.approx(0.5)
    assert sum(row.contribution for row in attribution.contributions) == pytest.approx(0.4)
    assert attribution.manifest_id == "pitchingplus:outcome-attribution:v1:2026"
    assert attribution.run_value_table_version == "sha256:run-values-v1"
    assert attribution.frame_id == data.frame.id
    assert attribution.raw_total_fact_id in registry
    assert attribution.centered_xrv100_p_fact_id in registry
    assert registry.get(attribution.league_centering_offset_fact_id).variant == "derived"
    assert all(row.fact_id in registry for row in attribution.contributions)


def test_attribution_pitch_count_combines_emitted_appearance_rows():
    games = frozenset(
        {
            GameKey(2026, date(2026, 7, 1), 100),
            GameKey(2026, date(2026, 7, 1), 101),
        }
    )
    result = compute_component_attribution(_pitcher_data(games=games))

    attribution = result[0]
    assert attribution.n_pitches == 8
    assert attribution.raw_total_xrv100 == pytest.approx(0.2)
    assert attribution.league_centering_offset_xrv100 == pytest.approx(0.1)
    assert attribution.centered_xrv100_p == pytest.approx(0.3)
    assert sum(row.contribution for row in attribution.contributions) == pytest.approx(0.2)


def test_attribution_rejects_missing_appearance_coverage():
    games = frozenset(
        {
            GameKey(2026, date(2026, 7, 1), 100),
            GameKey(2026, date(2026, 7, 1), 101),
        }
    )
    data = _pitcher_data(games=games)
    data.aggregates["pitcher_type_outcome_appearance"] = data.aggregates[
        "pitcher_type_outcome_appearance"
    ].filter(pl.col("game_pk") == 101)

    with pytest.raises(
        IncompatiblePitchingPlusExport,
        match="dropped keys",
    ):
        compute_component_attribution(data)


def test_attribution_rejects_mismatched_pitch_counts():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    data.aggregates["pitcher_type_outcome_appearance"] = data.aggregates[
        "pitcher_type_outcome_appearance"
    ].with_columns(pl.lit(5).alias("n_pitches"))

    with pytest.raises(
        IncompatiblePitchingPlusExport,
        match="pitch counts",
    ):
        compute_component_attribution(data)


def test_attribution_accepts_independent_three_decimal_rounding():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    data.aggregates["pitcher_type_appearance"] = data.aggregates["pitcher_type_appearance"].with_columns(
        pl.when(pl.col("game_pk") == 101).then(0.5005).otherwise(pl.col("xRV100_P")).alias("xRV100_P")
    )

    result = compute_component_attribution(data)

    assert result[0].centered_xrv100_p == pytest.approx(0.5)


def test_attribution_rejects_centered_mismatch_beyond_three_decimal_rounding():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    data.aggregates["pitcher_type_appearance"] = data.aggregates["pitcher_type_appearance"].with_columns(
        pl.when(pl.col("game_pk") == 101).then(0.501).otherwise(pl.col("xRV100_P")).alias("xRV100_P")
    )

    with pytest.raises(
        IncompatiblePitchingPlusExport,
        match="centered xRV100_P does not match canonical pitcher_type_appearance",
    ):
        compute_component_attribution(data)


def test_attribution_rejects_centered_value_that_disagrees_with_canonical_appearance():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    data.aggregates["pitcher_type_outcome_appearance"] = data.aggregates[
        "pitcher_type_outcome_appearance"
    ].with_columns(
        pl.when(pl.col("game_pk") == 101)
        .then(pl.when(pl.col("outcome") == "HBP").then(0.9).otherwise(0.0))
        .otherwise(pl.col("raw_component_xrv100"))
        .alias("raw_component_xrv100"),
        pl.when(pl.col("game_pk") == 101)
        .then(0.9)
        .otherwise(pl.col("raw_total_xrv100"))
        .alias("raw_total_xrv100"),
        pl.when(pl.col("game_pk") == 101)
        .then(1.0)
        .otherwise(pl.col("centered_xrv100_p"))
        .alias("centered_xrv100_p"),
    )
    data.aggregates["pitcher_type_appearance"] = data.aggregates["pitcher_type_appearance"].with_columns(
        pl.when(pl.col("game_pk") == 101).then(2.0).otherwise(pl.col("xRV100_P")).alias("xRV100_P")
    )

    with pytest.raises(
        IncompatiblePitchingPlusExport,
        match="centered xRV100_P does not match canonical pitcher_type_appearance",
    ):
        compute_component_attribution(data)


def test_attribution_rejects_canonical_pitch_count_mismatch():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    data.aggregates["pitcher_type_appearance"] = data.aggregates["pitcher_type_appearance"].with_columns(
        pl.when(pl.col("game_pk") == 101).then(5).otherwise(pl.col("n_pitches")).alias("n_pitches")
    )

    with pytest.raises(
        IncompatiblePitchingPlusExport,
        match="pitch counts do not match canonical pitcher_type_appearance",
    ):
        compute_component_attribution(data)


def test_attribution_fact_ids_include_pitcher_identity():
    game = frozenset({GameKey(2026, date(2026, 7, 1), 101)})
    first_data = _pitcher_data(games=game, pitcher_id=10)
    second_data = _pitcher_data(games=game, pitcher_id=20)
    first = compute_component_attribution(first_data)[0]
    second = compute_component_attribution(second_data)[0]

    assert first.frame_id == second.frame_id
    assert first.raw_total_fact_id != second.raw_total_fact_id
    assert first.centered_xrv100_p_fact_id != (second.centered_xrv100_p_fact_id)
    assert first.raw_total_fact_id in first_data.fact_registry
    assert second.raw_total_fact_id in second_data.fact_registry


def test_registered_attribution_cannot_fall_back_to_pitch_rows():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    data.aggregates.pop("pitcher_type_outcome_appearance")

    with pytest.raises(IncompatiblePitchingPlusExport, match="was not loaded"):
        compute_component_attribution(data)


def test_attribution_ignores_auxiliary_run_value_data():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    expected = compute_component_attribution(data)
    data.aggregates["run_values"] = pl.DataFrame(
        {
            "balls": [0],
            "strikes": [0],
            "model_classes": ["HBP"],
            "delta_run_exp": [999.0],
        }
    )

    assert compute_component_attribution(data) == expected


def test_runvalue_prompt_labels_raw_and_centered_values_with_fact_ids():
    data = _pitcher_data(games=frozenset({GameKey(2026, date(2026, 7, 1), 101)}))
    attribution = compute_component_attribution(data)[0]
    ctx = type(
        "Context",
        (),
        {
            "pitcher_name": "Test Pitcher",
            "throws": "R",
            "role": "SP",
            "facts": data.fact_registry,
            "frame_id": data.frame.id,
            "fact_ids": {},
            "attributions": [attribution],
            "arsenal": [type("Pitch", (), {"pitch_type": "FF"})()],
            "league_baselines": [],
            "calibration": None,
            "calibration_unavailable_reason": "not registered",
        },
    )()

    output = "\n".join(part for part in _build_runvalue_input(ctx) if isinstance(part, str))

    assert "raw pre-centering xRV100: +0.400" in output
    assert "league-centering offset: +0.100" in output
    assert "centered P xRV100: +0.500" in output
    assert attribution.raw_total_fact_id in output
    assert attribution.centered_xrv100_p_fact_id in output
    assert "total xRV100:" not in output
