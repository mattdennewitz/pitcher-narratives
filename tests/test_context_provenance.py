from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date

import polars as pl
import pytest

from pitcher_narratives.bundle_contract import ArtifactSemantics
from pitcher_narratives.claims import AnalysisCapabilities
from pitcher_narratives.context import (
    PitcherContext,
    _has_entity_components,
    assemble_pitcher_context,
)
from pitcher_narratives.data import PitcherData, load_pitcher_data
from pitcher_narratives.engine import compute_league_baselines
from pitcher_narratives.fact_provenance import build_manifest_fact_registry
from pitcher_narratives.facts import Fact, FactKind
from pitcher_narratives.temporal import FrameSelection, GameKey, TemporalFrame


@pytest.fixture(scope="module")
def loaded_data() -> PitcherData:
    return load_pitcher_data(592155, recent_appearances=5)


@pytest.fixture(scope="module")
def context(loaded_data: PitcherData) -> PitcherContext:
    return assemble_pitcher_context(loaded_data)


def test_loaded_data_owns_manifest_bound_base_fact_registry(loaded_data: PitcherData) -> None:
    registry = loaded_data.fact_registry

    assert registry.manifest_version == loaded_data.frame.source_population
    assert registry.facts()
    assert loaded_data.artifact_semantics_by_season
    assert all(fact.frame_id == loaded_data.frame.id for fact in registry.facts())

    base = next(fact for fact in registry.facts() if not fact.source_fact_ids)
    unmanifested = Fact.create(
        kind=base.kind,
        metric=base.metric,
        variant=base.variant,
        entity=base.entity,
        value=base.value,
        unit=base.unit,
        frame_id=base.frame_id,
        population=base.population,
        sample_size=base.sample_size,
        sufficiency=base.sufficiency,
        source=base.source,
        semantic_key=base.semantic_key + "|unmanifested",
        manifest_version=base.manifest_version,
        source_row_id="unmanifested-row-with-the-same-value",
    )
    with pytest.raises(ValueError, match="manifest-covered"):
        registry.add(unmanifested)


def test_context_exposes_validated_producer_identity_and_inventory(
    context: PitcherContext,
) -> None:
    assert context.producer_identity is not None
    assert context.producer_artifact_grains
    for field in (
        "schema_version",
        "feature_schema_sha256",
        "model_bundle_sha256",
    ):
        path = f"producer_identity.{field}"
        fact = context.facts.get(context.fact_ids[path])
        assert fact.value == getattr(context.producer_identity, field)
        assert fact.source == "pitchingplus:producer_identity"
        assert fact.source_row_id


def test_current_frame_identity_facts_name_pitcher_and_games(context: PitcherContext) -> None:
    identity = {
        fact.metric: fact
        for fact in context.facts.facts()
        if fact.metric in {"context.pitcher_id", "context.pitcher_name", "context.frame.game_pk"}
    }

    assert identity["context.pitcher_id"].value == context.pitcher_id
    assert identity["context.pitcher_name"].value == context.pitcher_name
    game_fact = identity["context.frame.game_pk"]
    assert game_fact.frame_id == context.frame_id
    assert f"pitcher:{context.pitcher_id}" in game_fact.entity
    assert str(game_fact.value) in game_fact.semantic_key


def test_platoon_facts_carry_typed_same_frame_semantics(context: PitcherContext) -> None:
    facts = [fact for fact in context.facts.facts() if fact.metric.startswith("context.platoon.")]

    assert facts
    assert {fact.variant for fact in facts} >= {"P", "usage"}
    for fact in facts:
        assert fact.frame_id == context.frame_id
        assert fact.population.startswith(f"{context.source_population};platoon_matchup=")
        assert ";batter_side=" in fact.population
        assert fact.sample_size is not None
        assert "p_throws=" in fact.semantic_key
        assert "batter_side=" in fact.semantic_key
        assert "pitch_type=" in fact.semantic_key
    for index, split in enumerate(context.platoon_mix.splits):
        assert split.frame_id == context.frame_id
        assert split.population == context.source_population
        assert split.pitcher_side == context.throws
        assert split.batter_side in {"L", "R"}
        if split.window_usage_pct is not None:
            split_fact = context.facts.get(context.fact_ids[f"platoon_mix.splits[{index}].window_usage_pct"])
            assert split_fact.sample_size == split.n_pitches_window


def test_every_specialist_context_scalar_has_one_resolvable_fact_id(context: PitcherContext) -> None:
    assert context.fact_ids
    assert all(context.facts.get(fact_id).id == fact_id for fact_id in context.fact_ids.values())
    assert all(not path.endswith("source_fact_ids") for path in context.fact_ids)

    prompt = context.to_prompt()
    rendered_ids = set(re.findall(r"fact:[0-9a-f]{24}", prompt))
    assert rendered_ids
    assert rendered_ids <= set(context.fact_ids.values())
    assert all(fact_id in context.facts for fact_id in rendered_ids)


def test_computed_context_lineage_terminates_in_manifest_rows(context: PitcherContext) -> None:
    computed = [
        context.facts.get(fact_id)
        for fact_id in set(context.fact_ids.values())
        if context.facts.get(fact_id).kind is FactKind.COMPUTED
    ]

    assert computed
    for fact in computed:
        lineage = context.facts.base_lineage(fact.id)
        assert lineage
        assert all(base.source.startswith("pitchingplus:") for base in lineage)
        assert all(base.source_row_id for base in lineage)
        assert all(base.manifest_version == context.source_population for base in lineage)


def test_key_context_values_retain_exact_metric_and_sample_lineage(
    context: PitcherContext,
) -> None:
    def metrics(path: str) -> set[str]:
        fact = context.facts.get(context.fact_ids[path])
        return {base.metric for base in context.facts.base_lineage(fact.id)}

    assert "all_pitches.release_speed" in metrics("fastball.window_velo")
    assert {
        "pitcher_type_appearance.P+",
        "pitcher_type_appearance.n_pitches",
    } <= metrics("arsenal[0].window_p_plus")
    assert "all_pitches.pitch_type" in metrics("arsenal[0].window_usage_pct")

    probability_path = next(
        path for path in context.fact_ids if path.startswith("intermediates[") and path.endswith(".xwhiff_p")
    )
    assert {
        "pitcher_type_appearance.xWhiff_P",
        "pitcher_type_appearance.n_pitches",
    } <= metrics(probability_path)


def test_calibration_is_not_registered_by_generic_context_walking(
    context: PitcherContext,
) -> None:
    assert not any(
        fact.kind is FactKind.COMPUTED and fact.metric.startswith("context.calibration")
        for fact in context.facts.facts()
    )


def test_location_regions_depends_on_sufficient_distribution_not_formal_location(
    loaded_data: PitcherData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pitcher_narratives.context.compute_formal_location_values",
        lambda *args, **kwargs: [],
    )

    context = assemble_pitcher_context(loaded_data)
    capability = context.facts.get(context.fact_ids["capability.location_regions"])

    assert any(distribution.sufficient for distribution in context.location_distributions)
    assert capability.value is True
    assert all(
        base.source == "pitchingplus:all_pitches" for base in context.facts.base_lineage(capability.id)
    )


def test_capabilities_are_boolean_model_semantics_from_producer_facts(
    context: PitcherContext,
) -> None:
    capability_facts = {
        fact.metric.removeprefix("capability."): fact
        for fact in context.facts.facts()
        if fact.metric.startswith("capability.")
    }

    assert set(capability_facts) == {
        "feature_attribution",
        "location_regions",
        "pitch_targets",
        "biomechanical_causality",
        "tunneling_measurement",
        "platoon_splits",
    }
    for fact in capability_facts.values():
        assert fact.kind is FactKind.MODEL_SEMANTIC
        assert type(fact.value) is bool
        assert fact.frame_id == context.frame_id
        assert fact.source_fact_ids
        assert context.facts.base_lineage(fact.id)

    assert capability_facts["feature_attribution"].value is False
    assert capability_facts["pitch_targets"].value is False
    assert capability_facts["biomechanical_causality"].value is False
    assert capability_facts["tunneling_measurement"].value is False

    capabilities = AnalysisCapabilities.from_registry(context.facts, frame_id=context.frame_id)
    assert capabilities.has_location_regions is capability_facts["location_regions"].value
    assert capabilities.has_platoon_splits is capability_facts["platoon_splits"].value


def _platoon_context(
    monkeypatch: pytest.MonkeyPatch,
    recent_only: bool = False,
    frame_as_of: date | None = None,
    batted_ball_velocity: float = 96.0,
) -> PitcherContext:
    game_dates = {10: date(2026, 7, 1), 11: date(2026, 7, 2)}
    raw_rows = []
    for index in range(40):
        raw_rows.append(
            {
                "season": 2026,
                "game_pk": 10 if index < 20 else 11,
                "game_date": game_dates[10 if index < 20 else 11],
                "pitcher": 1,
                "at_bat_number": index + 1,
                "pitch_number": 1,
                "inning": 1,
                "events": "strikeout",
                "description": ("hit_into_play" if index % 2 or index == 2 else "called_strike"),
                "launch_speed": (
                    None if index == 2 else (batted_ball_velocity if index % 2 or index == 0 else None)
                ),
                "zone": 1 if index % 2 else 11,
                "stand": "R" if index < 20 else "L",
                "p_throws": "R",
                "pitch_type": "FF",
                "pitch_name": "4-Seam Fastball",
                "player_name": "Test, Pitcher",
                "release_speed": 95.0 + index / 100,
                "pfx_x": -0.5,
                "arm_angle": 45.0,
                "arm_side_pfx_x": 0.5,
                "pfx_z": 1.2,
                "release_pos_x": -2.0,
                "release_pos_z": 5.8,
                "release_extension": 6.4,
            }
        )
    pitches = pl.DataFrame(raw_rows)
    appearances = pl.DataFrame(
        {
            "season": [2026, 2026],
            "game_pk": [10, 11],
            "game_date": [game_dates[10], game_dates[11]],
            "pitcher": [1, 1],
            "role": ["SP", "SP"],
        }
    )
    probabilities = {
        column: 0.1
        for column in (
            "xSwing_P",
            "xSwing_S",
            "xWhiff_P",
            "xWhiff_S",
            "xGOr_P",
            "xGOr_S",
            "xPUr_P",
            "xPUr_S",
            "xHR100_P",
            "xHR100_S",
            "BBE_prob_P",
            "BBE_prob_S",
            "xSwSt_P",
            "xSwSt_S",
            "xRV100_P",
            "xRV100_S",
        )
    }
    pitcher_type = pl.DataFrame(
        [
            {
                "season": 2026,
                "pitcher": 1,
                "pitch_type": "FF",
                "n_pitches": 40,
                "P+": 101.0,
                "S+": 102.0,
                "L+": 99.0,
                **probabilities,
            }
        ]
    )
    appearance_rows = pl.DataFrame(
        [
            {
                "season": 2026,
                "game_pk": game_pk,
                "game_date": game_dates[game_pk],
                "pitcher": 1,
                "pitch_type": "FF",
                "n_pitches": 20,
                "P+": 101.0,
                "S+": 102.0,
                "L+": 99.0,
                **probabilities,
            }
            for game_pk in (10, 11)
        ]
    )
    platoon_season = pl.DataFrame(
        [
            {
                "season": 2026,
                "pitcher": 1,
                "pitch_type": "FF",
                "platoon_matchup": side,
                "n_pitches": 20,
                "P+": 101.0,
                "S+": 102.0,
                "L+": 99.0,
            }
            for side in ("RR", "RL")
        ]
    )
    platoon_appearance = pl.DataFrame(
        [
            {
                "season": 2026,
                "game_pk": game_pk,
                "game_date": game_dates[game_pk],
                "pitcher": 1,
                "pitch_type": "FF",
                "platoon_matchup": side,
                "n_pitches": 20,
                "P+": 101.0,
                "S+": 102.0,
                "L+": 99.0,
            }
            for side, game_pk in (("RR", 10), ("RL", 11))
        ]
    )
    pitcher = pl.DataFrame(
        [
            {
                "season": 2026,
                "pitcher": 1,
                "n_pitches": 40,
                "P+": 101.0,
                "S+": 102.0,
                "L+": 99.0,
            }
        ]
    )
    reference = pl.DataFrame(
        [
            {
                "season": 2026,
                "manifest_id": "reference:v1",
                "seasons": "2026",
                "level": "MLB",
                "game_types": "R",
                "pitch_type": "FF",
                "pitcher_handling": "handedness_normalized",
                "statistical_unit": "pitch",
                "weighting": "pitch_weighted",
                "unit": unit,
                "metric": metric,
                "n_pitches": 1000,
                "mean": mean,
                "std": std,
            }
            for metric, unit, mean, std in (
                ("release_speed", "mph", 94.0, 1.0),
                ("arm_side_pfx_x", "inches", 6.0, 1.0),
                ("pfx_z", "inches", 14.0, 1.0),
                ("zone_pct", "percent", 50.0, None),
                ("chase_pct", "percent", 30.0, None),
            )
        ]
    )
    slot_reference = pl.DataFrame(
        [
            {
                "season": 2026,
                "manifest_id": "slot-reference:v1",
                "seasons": "2024-2026",
                "level": "MLB",
                "game_types": "R",
                "pitch_type": "FF",
                "arm_angle_bucket": 40,
                "metric": metric,
                "mean": mean,
                "std": 2.0,
                "n_pitches": 200,
                "unit": "inches",
                "pitcher_handling": "handedness_normalized",
                "statistical_unit": "pitch",
                "weighting": "pitch_weighted",
            }
            for metric, mean in (("arm_side_pfx_x", 6.0), ("pfx_z", 14.4))
        ]
    )
    frames = {
        "all_pitches": pitches,
        "pitcher": pitcher,
        "pitcher_type": pitcher_type,
        "pitcher_type_appearance": appearance_rows,
        "pitcher_type_platoon": platoon_season,
        "pitcher_type_platoon_appearance": platoon_appearance,
        "pitch_type_slot_reference": slot_reference,
        **{
            grain: pl.DataFrame([{"season": 2026, "pitcher": 1, "arbitrary_value": 1.0}])
            for grain in (
                "pitch_targets",
                "biomechanical_causality",
                "tunneling_measurement",
            )
        },
    }
    artifacts = {
        grain: ArtifactSemantics(
            filename=f"2026-{grain}.csv",
            sha256="a" * 64,
            season=2026,
            grain=grain,
            natural_key=(
                ("season", "game_pk", "at_bat_number", "pitch_number")
                if grain == "all_pitches"
                else (
                    ("season", "pitch_type", "arm_angle_bucket", "metric")
                    if grain == "pitch_type_slot_reference"
                    else tuple(
                        column
                        for column in (
                            "season",
                            "pitcher",
                            "pitch_type",
                            "platoon_matchup",
                            "game_date",
                            "game_pk",
                        )
                        if column in frames[grain].columns
                    )
                )
            ),
            required_columns=tuple(frames[grain].columns),
            metrics={},
        )
        for grain in frames
    }
    selected_game_pks = {11} if recent_only else {10, 11}
    frame = FrameSelection.create(
        temporal_frame=TemporalFrame.RECENT,
        games=frozenset(GameKey(2026, game_dates[game_pk], game_pk) for game_pk in selected_game_pks),
        as_of=frame_as_of or game_dates[11],
        source_population="test:canonical",
        scoring_season=2026,
    )
    reference_artifact = ArtifactSemantics(
        filename="2026-pitch_type_reference.csv",
        sha256="b" * 64,
        season=2026,
        grain="pitch_type_reference",
        natural_key=("season", "pitch_type", "metric"),
        required_columns=tuple(reference.columns),
        metrics={},
    )
    artifacts["pitch_type_reference"] = reference_artifact
    producer_rows = {(2026, grain): (artifacts[grain], rows) for grain, rows in frames.items()}
    producer_rows = {
        key: (
            artifact,
            (rows.filter(pl.col("game_pk").is_in(selected_game_pks)) if "game_pk" in rows.columns else rows),
        )
        for key, (artifact, rows) in producer_rows.items()
    }
    producer_rows[(2026, "pitch_type_reference")] = (
        reference_artifact,
        reference,
    )
    registry, lineage_id = build_manifest_fact_registry(producer_rows, frame=frame)
    data = PitcherData(
        pitches=pitches,
        appearances=appearances,
        window_appearances=appearances.filter(pl.col("game_pk").is_in(selected_game_pks)),
        season_baseline=pitcher,
        pitch_type_baseline=pitcher_type,
        prior_season_baseline=pl.DataFrame(),
        prior_pitch_type_baseline=pl.DataFrame(),
        aggregates={
            grain: (
                rows.with_columns(
                    pl.col("platoon_matchup")
                    .replace_strict({"LL": "same", "RR": "same", "LR": "opposite", "RL": "opposite"})
                    .alias("platoon_matchup")
                )
                if grain in {"pitcher_type_platoon", "pitcher_type_platoon_appearance"}
                else rows
            )
            for grain, rows in frames.items()
        },
        pitcher_id=1,
        pitcher_name="Test, Pitcher",
        throws="R",
        frame=frame,
        producer_artifact_grains=frozenset(frames),
        artifact_semantics=artifacts,
        artifact_semantics_by_season={(2026, grain): artifact for grain, artifact in artifacts.items()},
        producer_artifact_rows=producer_rows,
        fact_registry=registry,
        lineage_fact_id=lineage_id,
    )
    monkeypatch.setattr("pitcher_narratives.context.compute_formal_location_values", lambda *a, **k: [])
    monkeypatch.setattr("pitcher_narratives.context.compute_location_distributions", lambda *a, **k: [])
    monkeypatch.setattr("pitcher_narratives.context.compute_component_attribution", lambda *a, **k: [])
    league_baselines = compute_league_baselines(reference)
    monkeypatch.setattr(
        "pitcher_narratives.context.compute_league_baselines",
        lambda _rows: league_baselines,
    )
    return assemble_pitcher_context(data)


def test_one_recent_appearance_does_not_cite_frame_rows_as_season_physical_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(monkeypatch, recent_only=True)

    for path in (
        "fastball.season_velo",
        "fastball.season_pfx_x",
        "arsenal[0].season_velo",
        "arsenal[0].season_pfx_z",
        "first_pitch.entries[0].season_pct",
        "hard_hit_rate.season_hard_hit_pct",
        "release_point.pitch_types[0].season_release_x",
        "fastball.velo_delta",
        "fastball.pfx_x_delta",
        "arsenal[0].velo_delta",
        "arsenal[0].pfx_z_delta",
        "first_pitch.entries[0].delta",
        "hard_hit_rate.delta",
        "release_point.pitch_types[0].release_x_delta",
    ):
        assert path not in context.fact_ids
    assert "arsenal[0].season_usage_pct" in context.fact_ids
    assert "platoon_mix.splits[0].season_usage_pct" in context.fact_ids
    assert context.temporal.recent_frame_appearances == 1
    assert "temporal.recent_frame_appearances" in context.fact_ids
    prompt = context.to_prompt()
    assert "Recent canonical frame" in prompt
    assert "Prior-year workload relevance" not in prompt
    assert "early season" not in prompt


def test_inactive_pitcher_as_of_cites_explicit_boundary_not_last_pitch_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary = date(2026, 7, 10)
    context = _platoon_context(monkeypatch, frame_as_of=boundary)

    as_of = context.facts.get(context.fact_ids["as_of"])
    as_of_sources = {context.facts.get(fact_id).metric for fact_id in as_of.source_fact_ids}
    assert "context.frame.as_of_input" in as_of_sources
    assert "all_pitches.game_date" not in as_of_sources
    assert as_of.value == boundary.isoformat()

    source_population = context.facts.get(context.fact_ids["source_population"])
    assert {context.facts.get(fact_id).metric for fact_id in source_population.source_fact_ids} == {
        "context.manifest_row_lineage"
    }

    frame_id = context.facts.get(context.fact_ids["frame_id"])
    frame_metrics = {context.facts.get(fact_id).metric for fact_id in frame_id.source_fact_ids}
    assert {
        "context.manifest_row_lineage",
        "context.frame.as_of_input",
        "all_pitches.season",
        "all_pitches.game_date",
        "all_pitches.game_pk",
    } <= frame_metrics


def test_hard_hit_sources_intersect_bip_and_nonnull_exit_velocity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(monkeypatch)
    fact = context.facts.get(context.fact_ids["hard_hit_rate.hard_hit_pct"])
    sources = tuple(context.facts.get(fact_id) for fact_id in fact.source_fact_ids)
    description_rows = {
        source.source_row_id for source in sources if source.metric == "all_pitches.description"
    }
    velocity_rows = {
        source.source_row_id for source in sources if source.metric == "all_pitches.launch_speed"
    }
    assert description_rows == velocity_rows
    assert len(description_rows) == 20
    assert all(
        source.value == "hit_into_play" for source in sources if source.metric.endswith(".description")
    )
    assert all(source.value is not None for source in sources if source.metric.endswith(".launch_speed"))

    excluded = {
        source.source_row_id
        for source in context.facts.facts()
        if source.metric in {"all_pitches.description", "all_pitches.launch_speed"}
        and (
            "at_bat_number=1" in source.semantic_key.split("|")
            or "at_bat_number=3" in source.semantic_key.split("|")
        )
    }
    assert excluded.isdisjoint(description_rows)


def test_zero_hard_hits_remains_citable_from_full_valid_denominator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(
        monkeypatch,
        recent_only=True,
        batted_ball_velocity=90.0,
    )
    assert context.hard_hit_rate.n_hard_hit == 0
    fact = context.facts.get(context.fact_ids["hard_hit_rate.n_hard_hit"])
    assert fact.sample_size == context.hard_hit_rate.n_batted_balls == 10
    assert len({context.facts.get(fact_id).source_row_id for fact_id in fact.source_fact_ids}) == 10


def test_context_fact_samples_and_populations_preserve_temporal_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(monkeypatch, recent_only=True)

    season = context.facts.get(context.fact_ids["arsenal[0].season_p_plus"])
    window = context.facts.get(context.fact_ids["arsenal[0].window_p_plus"])
    delta = context.facts.get(context.fact_ids["arsenal[0].p_plus_delta"])
    assert season.sample_size == 40
    assert window.sample_size == 20
    assert context.facts.get(context.fact_ids["fastball.window_velo"]).sample_size == 20
    assert context.facts.get(context.fact_ids["arsenal[0].window_pfx_z"]).sample_size == 20
    assert context.facts.get(context.fact_ids["arsenal[0].window_usage_pct"]).sample_size == 20
    assert context.facts.get(context.fact_ids["hard_hit_rate.hard_hit_pct"]).sample_size == 10
    assert delta.sample_size == 20
    assert season.population == "scoring-season:2026:pitcher_type"
    assert window.population == f"exact-frame:{context.frame_id}"
    assert delta.population == (
        f"comparison[season=scoring-season:2026:pitcher_type;window=exact-frame:{context.frame_id}]"
    )

    league = context.facts.get(context.fact_ids["league_baselines[0].avg_velo"])
    source_populations = {context.facts.get(fact_id).population for fact_id in league.source_fact_ids}
    assert source_populations == {league.population}
    assert league.sample_size == 1000
    assert league.population == "scoring-season:2026:pitch_type_reference"


def test_adequate_platoon_rows_register_exact_fact_ids_and_unlock_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(monkeypatch)
    expected_codes = {"same": "RR", "opposite": "RL"}
    for index, split in enumerate(context.platoon_mix.splits):
        fact = context.facts.get(context.fact_ids[f"platoon_mix.splits[{index}].window_p_plus"])
        producer_rows = [
            base
            for base in context.facts.base_lineage(fact.id)
            if base.source == "pitchingplus:pitcher_type_platoon_appearance"
        ]
        assert producer_rows
        assert all(
            f"platoon_matchup={expected_codes[split.platoon_side]!r}" in row.semantic_key
            for row in producer_rows
        )
    split_paths = {path for path in context.fact_ids if path.startswith("platoon_mix.splits[")}

    assert split_paths
    capability = context.facts.get(context.fact_ids["capability.platoon_splits"])
    assert capability.value is True
    assert context.facts.base_lineage(capability.id)
    for path in split_paths:
        fact = context.facts.get(context.fact_ids[path])
        assert fact.source_fact_ids
        assert all(base.source_row_id for base in context.facts.base_lineage(fact.id))


def test_entity_component_matching_does_not_confuse_game_12_with_123() -> None:
    assert _has_entity_components("pitcher:1|game_pk:12", ("game_pk:12",))
    assert not _has_entity_components("pitcher:1|game_pk:123", ("game_pk:12",))


def test_same_named_untyped_optional_grain_does_not_unlock_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(monkeypatch)

    for capability in (
        "pitch_targets",
        "biomechanical_causality",
        "tunneling_measurement",
    ):
        assert capability in context.producer_artifact_grains
        assert context.facts.get(context.fact_ids[f"capability.{capability}"]).value is False


def test_specialist_context_sections_use_corresponding_producer_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(monkeypatch)

    def lineage_metrics(path: str) -> set[str]:
        fact = context.facts.get(context.fact_ids[path])
        return {base.metric for base in context.facts.base_lineage(fact.id)}

    expectations = {
        "fastball.window_pfx_x": {"all_pitches.pfx_x"},
        "velocity_arc.innings_pitched": {"all_pitches.inning"},
        "arsenal[0].window_pfx_z": {"all_pitches.pfx_z"},
        "first_pitch.entries[0].window_pct": {
            "all_pitches.pitch_number",
            "all_pitches.pitch_type",
        },
        "execution[0].csw_pct": {"all_pitches.description"},
        "hard_hit_rate.hard_hit_pct": {
            "all_pitches.description",
            "all_pitches.launch_speed",
        },
        "release_point.pitch_types[0].window_release_x": {
            "all_pitches.release_pos_x",
        },
        "workload.appearances[0].pitch_count": {"all_pitches.game_pk"},
        "temporal.recent_frame_appearances": {"all_pitches.season"},
        "platoon_mix.splits[0].window_p_plus": {
            "pitcher_type_platoon_appearance.P+",
            "pitcher_type_platoon_appearance.n_pitches",
        },
        "league_baselines[0].avg_velo": {
            "pitch_type_reference.mean",
            "pitch_type_reference.n_pitches",
        },
        "pitch_shape.entries[0].arm_angle": {"all_pitches.arm_angle"},
        "pitch_shape.entries[0].arm_side_run_in": {
            "all_pitches.arm_side_pfx_x",
        },
        "pitch_shape.entries[0].exp_arm_side_run_in": {
            "all_pitches.arm_angle",
            "pitch_type_slot_reference.mean",
            "pitch_type_slot_reference.n_pitches",
        },
        "pitch_shape.entries[0].run_residual_z": {
            "all_pitches.arm_angle",
            "all_pitches.arm_side_pfx_x",
            "pitch_type_slot_reference.mean",
            "pitch_type_slot_reference.std",
        },
    }
    for path, required in expectations.items():
        assert required <= lineage_metrics(path)


def test_every_reader_visible_specialist_scalar_has_exact_source_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _platoon_context(monkeypatch)
    sections = {
        "fastball": context.fastball,
        "velocity_arc": context.velocity_arc,
        "arsenal": context.arsenal,
        "platoon_mix": context.platoon_mix,
        "first_pitch": context.first_pitch,
        "execution": context.execution,
        "intermediates": context.intermediates,
        "hard_hit_rate": context.hard_hit_rate,
        "release_point": context.release_point,
        "workload": context.workload,
        "temporal": context.temporal,
        "league_baselines": context.league_baselines,
        "pitch_shape": context.pitch_shape,
    }
    scalar_paths: set[str] = set()

    def walk(path: str, value: object) -> None:
        if value is None:
            return
        if isinstance(value, (str, int, float, bool, date)):
            scalar_paths.add(path)
            return
        if is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                walk(f"{path}.{field.name}", getattr(value, field.name))
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                walk(f"{path}[{key}]", item)
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(f"{path}[{index}]", item)

    for section, value in sections.items():
        walk(section, value)

    assert scalar_paths <= set(context.fact_ids)
    assert context.cross_season_summary is None
    assert context.arsenal_trend is None
