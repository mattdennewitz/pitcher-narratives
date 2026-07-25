"""PitcherContext assembly for LLM prompt generation.

Assembles all engine outputs into a single Pydantic model with a
to_prompt() method that renders prompt-ready markdown under 2,000 tokens.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from pitcher_narratives.bundle_contract import ModelEvaluationArtifact, ProducerIdentity
from pitcher_narratives.data import (
    PitcherData,
    filter_to_frame,
    filter_to_prior_appearances,
)
from pitcher_narratives.engine import (
    ArsenalTrends,
    ComponentAttribution,
    CrossSeasonSummary,
    ExecutionMetrics,
    FastballSummary,
    FirstPitchWeaponry,
    FormalLocationValue,
    HardHitRate,
    IntermediateProbabilities,
    LeagueBaseline,
    LocationDistribution,
    PitchTypeSummary,
    PlatoonMix,
    ReleasePointMetrics,
    TemporalContext,
    VelocityArc,
    WorkloadContext,
    _most_recent_row,
    compute_arsenal_summary,
    compute_component_attribution,
    compute_execution_metrics,
    compute_fastball_summary,
    compute_first_pitch_weaponry,
    compute_formal_location_values,
    compute_hard_hit_rate,
    compute_intermediate_probabilities,
    compute_league_baselines,
    compute_location_distributions,
    compute_platoon_mix,
    compute_release_point_metrics,
    compute_temporal_context,
    compute_velocity_arc,
    compute_workload_context,
)
from pitcher_narratives.fact_provenance import (
    manifest_source,
    register_capability_fact,
    register_context_facts,
)
from pitcher_narratives.facts import FactRegistry
from pitcher_narratives.shape import (
    _BUCKET_DEGREES,
    PitchShapeProfile,
    _arm_angle_bucket,
    compute_pitch_shape,
)
from pitcher_narratives.temporal import TemporalFrame

__all__ = [
    "MultiFrameContext",
    "PitcherContext",
    "assemble_multi_frame_context",
    "assemble_pitcher_context",
    "assemble_prior_context",
]

_MAX_PITCH_TYPES = 4
"""Token budget: keep top 4 pitch types only in arsenal and execution tables."""

_MIN_CAPABILITY_PITCHES = 20


class PitcherContext(BaseModel):
    """Complete context document for LLM prompt generation.

    Assembles all engine outputs (fastball, arsenal, execution, workload)
    into one Pydantic model with a to_prompt() method.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pitcher_name: str
    pitcher_id: int
    throws: str
    role: str
    """Most recent appearance role: 'SP' or 'RP'."""

    frame_id: str
    frame_type: TemporalFrame
    as_of: str
    source_population: str
    frame_row_count: int
    scoring_season: int | None
    producer_identity: ProducerIdentity | None = None
    producer_artifact_grains: frozenset[str] = Field(default_factory=frozenset)

    fastball: FastballSummary | None
    velocity_arc: VelocityArc | None
    arsenal: list[PitchTypeSummary]
    platoon_mix: PlatoonMix
    first_pitch: FirstPitchWeaponry
    execution: list[ExecutionMetrics]
    intermediates: list[IntermediateProbabilities]
    """Per-pitch-type intermediate probabilities (P and S variants)."""
    attributions: list[ComponentAttribution]
    """Per-pitch-type xRV decomposition into 13 outcome contributions."""
    hard_hit_rate: HardHitRate
    release_point: ReleasePointMetrics
    workload: WorkloadContext
    temporal: TemporalContext

    cross_season_summary: CrossSeasonSummary | None = None
    """Year-over-year pitcher-level metric deltas (velocity, P+, S+, L+)."""

    arsenal_trend: ArsenalTrends | None = None
    """Year-over-year per-pitch-type arsenal changes (added/dropped/continued)."""

    pitch_shape: PitchShapeProfile | None = None

    league_baselines: list[LeagueBaseline]
    """Manifest-covered reference population used for comparisons."""
    formal_location: list[FormalLocationValue] = Field(default_factory=list)
    location_distributions: list[LocationDistribution] = Field(default_factory=list)
    calibration: ModelEvaluationArtifact | None = None
    calibration_unavailable_reason: str | None = None
    facts: FactRegistry | None = Field(default=None, exclude=True)
    fact_ids: dict[str, str] = Field(default_factory=dict)
    """Movement vs arm-slot expectation (dead zone / deceptive shape traits)."""

    def to_prompt(self) -> str:
        """Render as prompt-ready markdown under 2,000 tokens.

        Delegates to prompt_builder; imported lazily to avoid a circular
        import (prompt_builder imports PitcherContext from this module).
        """
        from pitcher_narratives.prompt_builder import build_pitcher_prompt

        prompt = build_pitcher_prompt(self)
        lineage_id = self.fact_ids.get("manifest_lineage")
        if lineage_id is None:
            return prompt
        return f"{prompt}\n\n## Typed Fact Registry\n- Manifest-bound context lineage [{lineage_id}]"


def _has_entity_components(entity: str, components: tuple[str, ...]) -> bool:
    """Match producer entity components exactly, never by substring."""
    return set(components) <= set(entity.split("|"))


def _context_source_fact_ids(
    data: PitcherData,
    context_values: dict[str, object],
) -> dict[str, tuple[str, ...]]:
    """Resolve deterministic context fields to the exact producer scalars used."""
    if data.fact_registry is None:
        return {}
    base_facts = tuple(fact for fact in data.fact_registry.facts() if not fact.source_fact_ids)

    unset = object()

    def select(
        grain: str,
        column: str,
        *,
        pitch_type: str | None = None,
        game_pk: int | None = None,
        platoon_matchup: str | None = None,
        stand: str | None = None,
        season: int | None = None,
        natural_keys: dict[str, object] | None = None,
        fact_value: object = unset,
        source_row_ids: frozenset[str] | None = None,
    ) -> tuple[str, ...]:
        source = manifest_source(grain)
        entity_tokens = tuple(
            token
            for token in (
                f"pitch_type:{pitch_type}" if pitch_type is not None else None,
                f"game_pk:{game_pk}" if game_pk is not None else None,
                (f"platoon_matchup:{platoon_matchup}" if platoon_matchup is not None else None),
                f"stand:{stand}" if stand is not None else None,
            )
            if token is not None
        )
        semantic_tokens = {
            **(natural_keys or {}),
            **({"season": season} if season is not None else {}),
        }
        return tuple(
            sorted(
                fact.id
                for fact in base_facts
                if fact.source == source
                and fact.metric == f"{grain}.{column}"
                and _has_entity_components(fact.entity, entity_tokens)
                and (fact_value is unset or fact.value == fact_value)
                and (source_row_ids is None or fact.source_row_id in source_row_ids)
                and all(
                    f"|{key}={value!r}|" in f"|{fact.semantic_key}|" for key, value in semantic_tokens.items()
                )
            )
        )

    def aggregate(
        grain: str,
        column: str,
        *,
        pitch_type: str,
        platoon_matchup: str | None = None,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                set(
                    select(
                        grain,
                        column,
                        pitch_type=pitch_type,
                        platoon_matchup=platoon_matchup,
                    )
                )
                | set(
                    select(
                        grain,
                        "n_pitches",
                        pitch_type=pitch_type,
                        platoon_matchup=platoon_matchup,
                    )
                )
            )
        )

    sources: dict[str, tuple[str, ...]] = {}
    season_game_keys = frozenset(
        (
            int(row["season"]),
            str(row["game_date"]),
            int(row["game_pk"]),
        )
        for row in (
            data.appearances.filter(pl.col("season") == data.frame.scoring_season).iter_rows(named=True)
            if data.frame is not None
            and data.frame.scoring_season is not None
            and {"season", "game_date", "game_pk"} <= set(data.appearances.columns)
            else ()
        )
    )
    frame_game_keys = frozenset(
        (game.season, game.game_date.isoformat(), game.game_pk)
        for game in (data.frame.games if data.frame is not None else ())
    )
    season_is_frame = bool(season_game_keys) and frame_game_keys == season_game_keys
    lineage_ids = (
        (data.lineage_fact_id,)
        if data.lineage_fact_id is not None and data.lineage_fact_id in data.fact_registry
        else ()
    )
    boundary_ids = tuple(
        fact.id
        for fact in data.fact_registry.facts()
        if fact.metric == "context.frame.as_of_input" and fact.frame_id == data.frame.id
    )
    frame_evidence = set(lineage_ids) | set(boundary_ids)
    for game in sorted(data.frame.games if data.frame is not None else ()):
        for column in ("season", "game_date", "game_pk"):
            frame_evidence.update(select("all_pitches", column, game_pk=game.game_pk))
    frame_evidence_ids = tuple(sorted(frame_evidence))

    identity_sources = {
        "pitcher_name": select("all_pitches", "player_name"),
        "pitcher_id": select("all_pitches", "pitcher"),
        "throws": select("all_pitches", "p_throws"),
        "role": select("all_pitches", "inning"),
        "frame_id": frame_evidence_ids,
        "frame_type": frame_evidence_ids,
        "as_of": tuple(sorted(set(lineage_ids) | set(boundary_ids))),
        "source_population": lineage_ids,
        "frame_row_count": select("all_pitches", "game_pk"),
        "scoring_season": select("all_pitches", "season"),
    }
    sources.update({path: ids for path, ids in identity_sources.items() if ids})
    for index, game in enumerate(sorted(data.frame.games if data.frame is not None else ())):
        for field, column in (
            ("season", "season"),
            ("game_date", "game_date"),
            ("game_pk", "game_pk"),
        ):
            ids = select("all_pitches", column, game_pk=game.game_pk)
            if ids:
                sources[f"frame_games[{index}].{field}"] = ids

    def combined(*groups: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({fact_id for group in groups for fact_id in group}))

    def assign(path: str, *groups: tuple[str, ...]) -> None:
        fact_ids = combined(*groups)
        if fact_ids:
            sources[path] = fact_ids

    fastball = context_values.get("fastball")
    arsenal = context_values.get("arsenal")

    # Physical fastball values are raw-pitch reductions. A season value is
    # citable from the frame grain only when the frame itself covers the season.
    if isinstance(fastball, FastballSummary):
        pitch_type = fastball.pitch_type
        pitch_identity = select("all_pitches", "pitch_type", pitch_type=pitch_type)
        pitch_name = select("all_pitches", "pitch_name", pitch_type=pitch_type)
        window_count = pitch_identity
        # Raw season physicals are only exact when the canonical frame is the
        # complete scoring-season appearance game-key set.
        for field, column in (
            ("window_velo", "release_speed"),
            ("window_pfx_x", "pfx_x"),
            ("window_pfx_z", "pfx_z"),
        ):
            assign(f"fastball.{field}", select("all_pitches", column, pitch_type=pitch_type))
        assign("fastball.pitch_type", pitch_identity)
        assign("fastball.pitch_name", pitch_name)
        for field in ("small_sample", "window_empty"):
            assign(f"fastball.{field}", window_count)
        assign("fastball.cold_start", select("all_pitches", "game_pk"))
        if season_is_frame:
            for field, column in (
                ("season_velo", "release_speed"),
                ("season_pfx_x", "pfx_x"),
                ("season_pfx_z", "pfx_z"),
            ):
                assign(f"fastball.{field}", select("all_pitches", column, pitch_type=pitch_type))
            for field, column in (
                ("velo_delta", "release_speed"),
                ("velo_delta_mph", "release_speed"),
                ("pfx_x_delta", "pfx_x"),
                ("pfx_z_delta", "pfx_z"),
            ):
                assign(f"fastball.{field}", select("all_pitches", column, pitch_type=pitch_type))
        for variant, column in (("p", "P+"), ("s", "S+"), ("l", "L+")):
            season_ids = aggregate("pitcher_type", column, pitch_type=pitch_type)
            window_ids = aggregate(
                "pitcher_type_appearance",
                column,
                pitch_type=pitch_type,
            )
            assign(f"fastball.season_{variant}_plus", season_ids)
            assign(f"fastball.window_{variant}_plus", window_ids)
            assign(
                f"fastball.{variant}_plus_delta",
                season_ids,
                window_ids,
            )
            assign(
                f"fastball.{variant}_plus_delta_pts",
                season_ids,
                window_ids,
            )

    velocity_arc = context_values.get("velocity_arc")
    if isinstance(velocity_arc, VelocityArc):
        game_pk = velocity_arc.game_pk
        pitch_type = fastball.pitch_type if isinstance(fastball, FastballSummary) else None
        game_ids = select("all_pitches", "game_pk", game_pk=game_pk)
        game_dates = select("all_pitches", "game_date", game_pk=game_pk)
        innings = select("all_pitches", "inning", pitch_type=pitch_type, game_pk=game_pk)
        speeds = select("all_pitches", "release_speed", pitch_type=pitch_type, game_pk=game_pk)
        assign("velocity_arc.game_pk", game_ids)
        assign("velocity_arc.game_date", game_dates)
        for field in ("available", "innings_pitched"):
            assign(f"velocity_arc.{field}", innings)
        for field in ("early_velo", "late_velo", "drop", "drop_string"):
            assign(f"velocity_arc.{field}", innings, speeds)

    if isinstance(arsenal, list):
        all_window_types = select("all_pitches", "pitch_type")
        pitcher_total = select("pitcher", "n_pitches")
        for index, summary in enumerate(arsenal):
            if not isinstance(summary, PitchTypeSummary):
                continue
            prefix = f"arsenal[{index}]"
            pitch_type = summary.pitch_type
            pitch_rows = select("all_pitches", "pitch_type", pitch_type=pitch_type)
            season_count = select("pitcher_type", "n_pitches", pitch_type=pitch_type)
            assign(f"{prefix}.pitch_type", pitch_rows)
            assign(
                f"{prefix}.pitch_name",
                select("all_pitches", "pitch_name", pitch_type=pitch_type),
            )
            assign(f"{prefix}.n_pitches_window", pitch_rows)
            assign(f"{prefix}.small_sample", pitch_rows)
            assign(f"{prefix}.window_usage_pct", pitch_rows, all_window_types)
            assign(f"{prefix}.season_usage_pct", season_count, pitcher_total)
            assign(f"{prefix}.n_pitches_season", season_count)
            assign(
                f"{prefix}.usage_delta",
                pitch_rows,
                all_window_types,
                season_count,
                pitcher_total,
            )
            for field, column in (
                ("window_velo", "release_speed"),
                ("window_pfx_x", "pfx_x"),
                ("window_pfx_z", "pfx_z"),
            ):
                assign(
                    f"{prefix}.{field}",
                    select("all_pitches", column, pitch_type=pitch_type),
                )
            assign(f"{prefix}.cold_start", select("all_pitches", "game_pk"))
            if season_is_frame:
                for field, column in (
                    ("season_velo", "release_speed"),
                    ("season_pfx_x", "pfx_x"),
                    ("season_pfx_z", "pfx_z"),
                    ("velo_delta", "release_speed"),
                    ("pfx_x_delta", "pfx_x"),
                    ("pfx_z_delta", "pfx_z"),
                ):
                    assign(
                        f"{prefix}.{field}",
                        select("all_pitches", column, pitch_type=pitch_type),
                    )
            for variant, column in (("p", "P+"), ("s", "S+"), ("l", "L+")):
                season_ids = aggregate(
                    "pitcher_type",
                    column,
                    pitch_type=pitch_type,
                )
                window_ids = aggregate(
                    "pitcher_type_appearance",
                    column,
                    pitch_type=pitch_type,
                )
                assign(f"{prefix}.season_{variant}_plus", season_ids)
                assign(f"{prefix}.window_{variant}_plus", window_ids)
                assign(
                    f"{prefix}.{variant}_plus_delta",
                    season_ids,
                    window_ids,
                )
                assign(
                    f"{prefix}.{variant}_plus_delta_pts",
                    season_ids,
                    window_ids,
                )

    probability_columns = {
        "xswing_p": "xSwing_P",
        "xswing_s": "xSwing_S",
        "xwhiff_p": "xWhiff_P",
        "xwhiff_s": "xWhiff_S",
        "xgor_p": "xGOr_P",
        "xgor_s": "xGOr_S",
        "xpur_p": "xPUr_P",
        "xpur_s": "xPUr_S",
        "xhr100_p": "xHR100_P",
        "xhr100_s": "xHR100_S",
        "bbe_prob_p": "BBE_prob_P",
        "bbe_prob_s": "BBE_prob_S",
        "xswst_p": "xSwSt_P",
        "xswst_s": "xSwSt_S",
        "xrv100_p": "xRV100_P",
        "xrv100_s": "xRV100_S",
    }
    intermediates = context_values.get("intermediates")
    if isinstance(intermediates, list):
        for index, probabilities in enumerate(intermediates):
            if not isinstance(probabilities, IntermediateProbabilities):
                continue
            prefix = f"intermediates[{index}]"
            pitch_type = probabilities.pitch_type
            assign(
                f"{prefix}.pitch_type",
                select("all_pitches", "pitch_type", pitch_type=pitch_type),
            )
            assign(
                f"{prefix}.pitch_name",
                select("all_pitches", "pitch_name", pitch_type=pitch_type),
            )
            sample_ids = select(
                "pitcher_type_appearance",
                "n_pitches",
                pitch_type=pitch_type,
            )
            assign(f"{prefix}.n_pitches", sample_ids)
            assign(f"{prefix}.small_sample", sample_ids)
            assign(f"{prefix}.cold_start", select("all_pitches", "game_pk"))
            for field, column in probability_columns.items():
                assign(
                    f"{prefix}.{field}",
                    aggregate(
                        "pitcher_type_appearance",
                        column,
                        pitch_type=pitch_type,
                    ),
                )
                assign(
                    f"{prefix}.season_{field}",
                    aggregate("pitcher_type", column, pitch_type=pitch_type),
                )

    platoon_mix = context_values.get("platoon_mix")
    if isinstance(platoon_mix, PlatoonMix):
        assign("platoon_mix.cold_start", select("all_pitches", "game_pk"))
        for index, split in enumerate(platoon_mix.splits):
            prefix = f"platoon_mix.splits[{index}]"
            pitch_type = split.pitch_type
            side = split.platoon_side
            stand = data.throws if side == "same" else ("L" if data.throws == "R" else "R")
            producer_matchup = f"{data.throws}{stand}"
            side_rows = select("all_pitches", "stand", stand=stand)
            type_rows = select("all_pitches", "pitch_type", pitch_type=pitch_type, stand=stand)
            window_p = aggregate(
                "pitcher_type_platoon_appearance",
                "P+",
                pitch_type=pitch_type,
                platoon_matchup=producer_matchup,
            )
            season_p = aggregate(
                "pitcher_type_platoon",
                "P+",
                pitch_type=pitch_type,
                platoon_matchup=producer_matchup,
            )
            season_type_count = select(
                "pitcher_type_platoon",
                "n_pitches",
                pitch_type=pitch_type,
                platoon_matchup=producer_matchup,
            )
            season_side_counts = select(
                "pitcher_type_platoon",
                "n_pitches",
                platoon_matchup=producer_matchup,
            )
            assign(f"{prefix}.pitch_type", type_rows)
            assign(
                f"{prefix}.pitch_name",
                select("all_pitches", "pitch_name", pitch_type=pitch_type, stand=stand),
            )
            assign(f"{prefix}.platoon_side", side_rows)
            assign(f"{prefix}.pitcher_side", select("all_pitches", "p_throws", stand=stand))
            assign(f"{prefix}.batter_side", side_rows)
            assign(f"{prefix}.population", select("all_pitches", "season", stand=stand))
            assign(f"{prefix}.frame_id", select("all_pitches", "game_pk", stand=stand))
            assign(f"{prefix}.n_pitches_window", type_rows)
            assign(f"{prefix}.window_usage_pct", type_rows, side_rows)
            assign(f"{prefix}.window_p_plus", window_p)
            assign(f"{prefix}.available", season_p)
            assign(f"{prefix}.n_pitches_season", season_type_count)
            assign(
                f"{prefix}.season_usage_pct",
                season_type_count,
                season_side_counts,
            )
            assign(
                f"{prefix}.usage_delta",
                type_rows,
                side_rows,
                season_type_count,
                season_side_counts,
            )
            assign(f"{prefix}.season_p_plus", season_p)
            assign(f"{prefix}.p_plus_delta", season_p, window_p)

    first_pitch = context_values.get("first_pitch")
    if isinstance(first_pitch, FirstPitchWeaponry):
        first_pitch_types = select(
            "all_pitches",
            "pitch_type",
            natural_keys={"pitch_number": 1},
        )
        assign("first_pitch.total_first_pitches_window", first_pitch_types)
        assign("first_pitch.cold_start", select("all_pitches", "game_pk"))
        if season_is_frame:
            assign("first_pitch.total_first_pitches_season", first_pitch_types)
        for index, entry in enumerate(first_pitch.entries):
            prefix = f"first_pitch.entries[{index}]"
            type_rows = select(
                "all_pitches",
                "pitch_type",
                pitch_type=entry.pitch_type,
                natural_keys={"pitch_number": 1},
            )
            pitch_numbers = select(
                "all_pitches",
                "pitch_number",
                pitch_type=entry.pitch_type,
                natural_keys={"pitch_number": 1},
            )
            assign(f"{prefix}.pitch_type", type_rows)
            assign(f"{prefix}.pitch_name", select("all_pitches", "pitch_name", pitch_type=entry.pitch_type))
            assign(f"{prefix}.window_pct", type_rows, pitch_numbers, first_pitch_types)
            assign(f"{prefix}.n_first_pitches_window", type_rows, pitch_numbers)
            if season_is_frame:
                assign(f"{prefix}.season_pct", type_rows, pitch_numbers, first_pitch_types)
                assign(f"{prefix}.n_first_pitches_season", type_rows, pitch_numbers)
                assign(f"{prefix}.delta", type_rows, pitch_numbers, first_pitch_types)

    execution = context_values.get("execution")
    if isinstance(execution, list):
        for index, metrics in enumerate(execution):
            if not isinstance(metrics, ExecutionMetrics):
                continue
            prefix = f"execution[{index}]"
            pitch_type = metrics.pitch_type
            type_rows = select("all_pitches", "pitch_type", pitch_type=pitch_type)
            descriptions = select("all_pitches", "description", pitch_type=pitch_type)
            zones = select("all_pitches", "zone", pitch_type=pitch_type)
            assign(f"{prefix}.pitch_type", type_rows)
            assign(f"{prefix}.pitch_name", select("all_pitches", "pitch_name", pitch_type=pitch_type))
            assign(f"{prefix}.csw_pct", descriptions, type_rows)
            assign(f"{prefix}.zone_rate", zones)
            assign(f"{prefix}.chase_rate", zones, descriptions)
            assign(f"{prefix}.n_pitches", type_rows)
            assign(f"{prefix}.small_sample", type_rows)
            assign(f"{prefix}.cold_start", select("all_pitches", "game_pk"))
            for field, column in (
                ("xwhiff_p", "xWhiff_P"),
                ("xswing_p", "xSwing_P"),
                ("xrv100_p", "xRV100_P"),
            ):
                assign(
                    f"{prefix}.{field}",
                    aggregate("pitcher_type_appearance", column, pitch_type=pitch_type),
                )
            assign(
                f"{prefix}.xrv100_percentile",
                aggregate("pitcher_type_appearance", "xRV100_P", pitch_type=pitch_type),
                aggregate("pitcher_type", "xRV100_P", pitch_type=pitch_type),
            )

    hard_hit = context_values.get("hard_hit_rate")
    if isinstance(hard_hit, HardHitRate):
        batted_descriptions = select(
            "all_pitches",
            "description",
            fact_value="hit_into_play",
        )
        nonnull_launch_speeds = select("all_pitches", "launch_speed")
        description_rows = {data.fact_registry.get(fact_id).source_row_id for fact_id in batted_descriptions}
        launch_rows = {data.fact_registry.get(fact_id).source_row_id for fact_id in nonnull_launch_speeds}
        batted_row_ids = frozenset(row_id for row_id in description_rows & launch_rows if row_id is not None)
        valid_descriptions = select(
            "all_pitches",
            "description",
            fact_value="hit_into_play",
            source_row_ids=batted_row_ids,
        )
        valid_launch_speeds = select(
            "all_pitches",
            "launch_speed",
            source_row_ids=batted_row_ids,
        )
        hard_launch_speeds = tuple(
            fact_id for fact_id in valid_launch_speeds if float(data.fact_registry.get(fact_id).value) >= 95.0
        )
        hard_row_ids = frozenset(
            data.fact_registry.get(fact_id).source_row_id
            for fact_id in hard_launch_speeds
            if data.fact_registry.get(fact_id).source_row_id is not None
        )
        hard_descriptions = select(
            "all_pitches",
            "description",
            fact_value="hit_into_play",
            source_row_ids=hard_row_ids,
        )
        for field in ("hard_hit_pct", "n_batted_balls", "small_sample"):
            assign(
                f"hard_hit_rate.{field}",
                valid_descriptions,
                valid_launch_speeds,
            )
        assign(
            "hard_hit_rate.n_hard_hit",
            valid_descriptions,
            valid_launch_speeds,
            hard_descriptions,
            hard_launch_speeds,
        )
        assign("hard_hit_rate.cold_start", select("all_pitches", "game_pk"))
        if season_is_frame:
            assign(
                "hard_hit_rate.season_hard_hit_pct",
                valid_descriptions,
                valid_launch_speeds,
            )
            assign(
                "hard_hit_rate.delta",
                valid_descriptions,
                valid_launch_speeds,
            )

    release_point = context_values.get("release_point")
    if isinstance(release_point, ReleasePointMetrics):
        assign("release_point.cold_start", select("all_pitches", "game_pk"))
        for index, pitch in enumerate(release_point.pitch_types):
            prefix = f"release_point.pitch_types[{index}]"
            pitch_type = pitch.pitch_type
            type_rows = select("all_pitches", "pitch_type", pitch_type=pitch_type)
            assign(f"{prefix}.pitch_type", type_rows)
            assign(f"{prefix}.pitch_name", select("all_pitches", "pitch_name", pitch_type=pitch_type))
            for field, column in (
                ("window_release_x", "release_pos_x"),
                ("window_release_z", "release_pos_z"),
                ("window_extension", "release_extension"),
            ):
                assign(f"{prefix}.{field}", select("all_pitches", column, pitch_type=pitch_type))
            assign(f"{prefix}.n_pitches_window", type_rows)
            assign(f"{prefix}.small_sample", type_rows)
            assign(f"{prefix}.cold_start", select("all_pitches", "game_pk"))
            if season_is_frame:
                for field, column in (
                    ("season_release_x", "release_pos_x"),
                    ("release_x_delta", "release_pos_x"),
                    ("season_release_z", "release_pos_z"),
                    ("release_z_delta", "release_pos_z"),
                    ("season_extension", "release_extension"),
                    ("extension_delta", "release_extension"),
                ):
                    assign(f"{prefix}.{field}", select("all_pitches", column, pitch_type=pitch_type))

    pitch_shape = context_values.get("pitch_shape")
    if isinstance(pitch_shape, PitchShapeProfile) and season_is_frame:
        reference_population_ids: set[str] = set()
        for index, entry in enumerate(pitch_shape.entries):
            prefix = f"pitch_shape.entries[{index}]"
            pitch_type = entry.pitch_type
            observed_pitch_type = select("all_pitches", "pitch_type", pitch_type=pitch_type)
            observed_name = select("all_pitches", "pitch_name", pitch_type=pitch_type)
            observed_angle = select("all_pitches", "arm_angle", pitch_type=pitch_type)
            observed_run = select("all_pitches", "arm_side_pfx_x", pitch_type=pitch_type)
            observed_ride = select("all_pitches", "pfx_z", pitch_type=pitch_type)
            lower_bucket = _arm_angle_bucket(entry.arm_angle - (_BUCKET_DEGREES / 2.0))
            buckets = (lower_bucket, lower_bucket + _BUCKET_DEGREES)

            def slot_ids(
                metric: str,
                *columns: str,
                pitch_type: str = pitch_type,
                buckets: tuple[int, int] = buckets,
            ) -> tuple[str, ...]:
                return combined(
                    *(
                        select(
                            "pitch_type_slot_reference",
                            column,
                            pitch_type=pitch_type,
                            natural_keys={
                                "arm_angle_bucket": bucket,
                                "metric": metric,
                            },
                        )
                        for bucket in buckets
                        for column in columns
                    )
                )

            run_mean = slot_ids("arm_side_pfx_x", "mean", "n_pitches")
            run_std = slot_ids("arm_side_pfx_x", "std", "n_pitches")
            ride_mean = slot_ids("pfx_z", "mean", "n_pitches")
            ride_std = slot_ids("pfx_z", "std", "n_pitches")
            reference_metadata = combined(
                slot_ids(
                    "arm_side_pfx_x",
                    "manifest_id",
                    "seasons",
                    "level",
                    "game_types",
                    "pitcher_handling",
                    "statistical_unit",
                    "weighting",
                    "unit",
                    "n_pitches",
                ),
                slot_ids(
                    "pfx_z",
                    "manifest_id",
                    "seasons",
                    "level",
                    "game_types",
                    "pitcher_handling",
                    "statistical_unit",
                    "weighting",
                    "unit",
                    "n_pitches",
                ),
            )
            reference_population_ids.update(reference_metadata)
            assign(f"{prefix}.pitch_type", observed_pitch_type)
            assign(f"{prefix}.pitch_name", observed_name)
            assign(f"{prefix}.is_fastball", observed_pitch_type)
            assign(f"{prefix}.n_pitches", observed_pitch_type)
            assign(f"{prefix}.arm_angle", observed_angle)
            assign(f"{prefix}.arm_side_run_in", observed_run)
            assign(f"{prefix}.ride_in", observed_ride)
            assign(
                f"{prefix}.exp_arm_side_run_in",
                observed_angle,
                run_mean,
            )
            assign(f"{prefix}.exp_ride_in", observed_angle, ride_mean)
            assign(
                f"{prefix}.run_residual_in",
                observed_run,
                observed_angle,
                run_mean,
            )
            assign(
                f"{prefix}.ride_residual_in",
                observed_ride,
                observed_angle,
                ride_mean,
            )
            assign(
                f"{prefix}.run_residual_z",
                observed_run,
                observed_angle,
                run_mean,
                run_std,
            )
            assign(
                f"{prefix}.ride_residual_z",
                observed_ride,
                observed_angle,
                ride_mean,
                ride_std,
            )
            assign(
                f"{prefix}.shape_tag",
                observed_pitch_type,
                observed_run,
                observed_ride,
                observed_angle,
                run_mean,
                run_std,
                ride_mean,
                ride_std,
            )
        assign(
            "pitch_shape.reference_population",
            tuple(sorted(reference_population_ids)),
        )

    workload = context_values.get("workload")
    if isinstance(workload, WorkloadContext):
        all_dates = select("all_pitches", "game_date")
        assign("workload.max_consecutive_days", all_dates)
        assign("workload.workload_concern", all_dates)
        assign("workload.frame_id", select("all_pitches", "game_pk"))
        for index, appearance in enumerate(workload.appearances):
            prefix = f"workload.appearances[{index}]"
            game_pk = appearance.game_pk
            game_ids = select("all_pitches", "game_pk", game_pk=game_pk)
            game_dates = select("all_pitches", "game_date", game_pk=game_pk)
            innings = select("all_pitches", "inning", game_pk=game_pk)
            events = select("all_pitches", "events", game_pk=game_pk)
            assign(f"{prefix}.game_pk", game_ids)
            assign(f"{prefix}.game_date", game_dates)
            assign(f"{prefix}.role", innings)
            assign(f"{prefix}.ip", innings, events)
            assign(f"{prefix}.pitch_count", game_ids)
            assign(f"{prefix}.rest_days", all_dates)

    temporal = context_values.get("temporal")
    if isinstance(temporal, TemporalContext):
        season_ids = select("all_pitches", "season")
        game_ids = select("all_pitches", "game_pk")
        game_dates = select("all_pitches", "game_date")
        innings = select("all_pitches", "inning")
        events = select("all_pitches", "events")
        assign(
            "temporal.analysis_date",
            tuple(sorted(set(lineage_ids) | set(boundary_ids))),
        )
        assign("temporal.scoring_season", season_ids)
        assign(
            "temporal.recent_frame_appearances",
            game_ids,
            season_ids,
        )
        assign(
            "temporal.recent_frame_first_date",
            game_dates,
            season_ids,
        )
        assign(
            "temporal.recent_frame_ip",
            game_ids,
            innings,
            events,
        )
        assign("temporal.frame_id", frame_evidence_ids)

    league_baselines = context_values.get("league_baselines")
    if isinstance(league_baselines, list):
        for index, baseline in enumerate(league_baselines):
            if not isinstance(baseline, LeagueBaseline):
                continue
            prefix = f"league_baselines[{index}]"
            pitch_type = baseline.pitch_type

            def reference(
                metric: str,
                *columns: str,
                pitch_type: str = pitch_type,
            ) -> tuple[str, ...]:
                return combined(
                    *(
                        select(
                            "pitch_type_reference",
                            column,
                            pitch_type=pitch_type,
                            natural_keys={"metric": metric},
                        )
                        for column in columns
                    )
                )

            assign(f"{prefix}.pitch_type", reference("arm_side_pfx_x", "pitch_type"))
            assign(f"{prefix}.pitch_name", reference("arm_side_pfx_x", "pitch_type"))
            metric_fields = {
                "avg_velo": "release_speed",
                "avg_arm_side_pfx_x": "arm_side_pfx_x",
                "avg_pfx_z": "pfx_z",
                "zone_pct": "zone_pct",
                "chase_pct": "chase_pct",
                "velo_std": "release_speed",
                "arm_side_pfx_x_std": "arm_side_pfx_x",
                "pfx_z_std": "pfx_z",
                "avg_s_plus": "S+",
                "avg_xswing_s": "xSwing_S",
                "avg_xwhiff_s": "xWhiff_S",
                "avg_xrv100_s": "xRV100_S",
            }
            for field, metric in metric_fields.items():
                column = "std" if field.endswith("_std") else "mean"
                assign(f"{prefix}.{field}", reference(metric, column, "n_pitches"))
            population_ids = reference(
                "arm_side_pfx_x",
                "manifest_id",
                "seasons",
                "level",
                "game_types",
                "pitch_type",
                "pitcher_handling",
                "statistical_unit",
                "weighting",
                "unit",
                "n_pitches",
            )
            assign(f"{prefix}.n_pitches", population_ids)
            for field in (
                "manifest_id",
                "seasons",
                "level",
                "game_types",
                "pitch_type",
                "pitcher_handling",
                "statistical_unit",
                "weighting",
                "unit",
                "n_pitches",
            ):
                assign(f"{prefix}.population.{field}", population_ids)
            for metric in baseline.metric_sample_sizes:
                assign(
                    f"{prefix}.metric_sample_sizes[{metric}]",
                    reference(metric, "n_pitches"),
                )

            for field, values in (
                ("seasons", baseline.population.seasons),
                ("game_types", baseline.population.game_types),
            ):
                for value_index, _ in enumerate(values):
                    assign(
                        f"{prefix}.population.{field}[{value_index}]",
                        population_ids,
                    )
    return sources


def assemble_pitcher_context(data: PitcherData) -> PitcherContext:
    """Orchestrate all engine compute functions into a PitcherContext.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        PitcherContext with all sections populated, ready for to_prompt().
    """
    if data.frame is None:
        raise ValueError("PitcherData has no canonical frame")
    frame_rows = filter_to_frame(data.pitches, data.frame)
    scoring_season = data.frame.scoring_season
    reference_rows = data.aggregates.get("pitch_type_reference")
    if (
        reference_rows is not None
        and data.frame.scoring_season is not None
        and "season" in reference_rows.columns
    ):
        reference_rows = reference_rows.filter(pl.col("season") == data.frame.scoring_season)
    league_baselines = compute_league_baselines(reference_rows)
    fact_registry = data.fact_registry
    location_appearance_rows = data.aggregates.get("pitcher_type_appearance")
    if location_appearance_rows is not None:
        location_appearance_rows = filter_to_frame(location_appearance_rows, data.frame)
    if fact_registry is None:
        formal_location = []
        location_distributions = []
    else:
        formal_location = compute_formal_location_values(
            location_appearance_rows,
            frame_id=data.frame.id,
            registry=fact_registry,
            manifest_version=data.frame.source_population,
            base_fact_resolver=lambda rows, columns: data.base_fact_ids(
                "pitcher_type_appearance",
                rows,
                columns,
            ),
        )
        location_distributions = compute_location_distributions(
            frame_rows,
            frame_id=data.frame.id,
            registry=fact_registry,
            manifest_version=data.frame.source_population,
            base_fact_resolver=lambda rows, columns: data.base_fact_ids(
                "all_pitches",
                rows,
                columns,
            ),
        )
    fastball = compute_fastball_summary(data)
    velocity_arc = compute_velocity_arc(data, fastball.pitch_type) if fastball else None
    arsenal = compute_arsenal_summary(data)[:_MAX_PITCH_TYPES]
    platoon_mix = compute_platoon_mix(data)
    first_pitch = compute_first_pitch_weaponry(data)
    execution = compute_execution_metrics(data)[:_MAX_PITCH_TYPES]
    intermediates = compute_intermediate_probabilities(data)[:_MAX_PITCH_TYPES]
    attributions = compute_component_attribution(data)[:_MAX_PITCH_TYPES] if fact_registry is not None else []
    hard_hit_rate = compute_hard_hit_rate(data)
    release_point = compute_release_point_metrics(data)
    workload = compute_workload_context(data)
    temporal = compute_temporal_context(data, workload)
    # Cross-season claims require a registry containing both immutable frames.
    # This registry deliberately contains only scoring-season population rows.
    cross_season_summary = None
    arsenal_trend = None
    pitch_shape = compute_pitch_shape(data)

    # Determine role from most recent appearance (deterministic tiebreak)
    most_recent = _most_recent_row(data.appearances)
    role = most_recent["role"]

    context_values = {
        "pitcher_name": data.pitcher_name,
        "pitcher_id": data.pitcher_id,
        "throws": data.throws,
        "role": role,
        "frame_id": data.frame.id,
        "frame_type": data.frame.temporal_frame,
        "as_of": data.frame.as_of.isoformat(),
        "source_population": data.frame.source_population,
        "frame_row_count": frame_rows.height,
        "scoring_season": scoring_season,
        "producer_identity": data.producer_identity,
        "producer_artifact_grains": data.producer_artifact_grains,
        "fastball": fastball,
        "velocity_arc": velocity_arc,
        "arsenal": arsenal,
        "platoon_mix": platoon_mix,
        "first_pitch": first_pitch,
        "execution": execution,
        "intermediates": intermediates,
        "attributions": attributions,
        "hard_hit_rate": hard_hit_rate,
        "release_point": release_point,
        "workload": workload,
        "temporal": temporal,
        "cross_season_summary": cross_season_summary,
        "arsenal_trend": arsenal_trend,
        "pitch_shape": pitch_shape,
        "league_baselines": league_baselines,
        "formal_location": formal_location,
        "location_distributions": location_distributions,
        "calibration": data.calibration,
        "calibration_unavailable_reason": data.calibration_unavailable_reason,
    }
    fact_ids: dict[str, str] = {}
    if fact_registry is not None and data.lineage_fact_id is not None:
        walked_context_values = {
            name: value for name, value in context_values.items() if name != "calibration"
        }
        source_fact_ids_by_path = _context_source_fact_ids(data, context_values)
        fact_ids = register_context_facts(
            {
                **walked_context_values,
                "frame_games": [
                    {
                        "season": game.season,
                        "game_date": game.game_date,
                        "game_pk": game.game_pk,
                    }
                    for game in sorted(data.frame.games)
                ],
            },
            registry=fact_registry,
            source_fact_ids_by_path=source_fact_ids_by_path,
            frame=data.frame,
            pitcher_id=data.pitcher_id,
            pitcher_throws=data.throws,
        )
        fact_ids["manifest_lineage"] = data.lineage_fact_id
        fact_ids.update(
            {
                fact.metric: fact.id
                for fact in fact_registry.facts()
                if fact.source == "pitchingplus:calibration"
            }
        )
        fact_ids.update(
            {
                fact.metric: fact.id
                for fact in fact_registry.facts()
                if fact.source == "pitchingplus:producer_identity"
            }
        )

        feature_attribution_evidence = tuple(
            fact.id
            for fact in fact_registry.facts()
            if fact.source == manifest_source("feature_attribution") and fact.frame_id == data.frame.id
        )
        location_evidence = tuple(
            fact_id
            for distribution in location_distributions
            if distribution.frame_id == data.frame.id and distribution.sufficient
            for fact_id in (
                distribution.coverage_fact_id,
                *distribution.region_fact_ids.values(),
            )
        )
        platoon_rows = data.aggregates.get("pitcher_type_platoon_appearance")
        if platoon_rows is not None:
            platoon_rows = filter_to_frame(platoon_rows, data.frame)
        adequate_platoon = False
        if (
            platoon_rows is not None
            and not platoon_rows.is_empty()
            and {"platoon_matchup", "n_pitches"} <= set(platoon_rows.columns)
        ):
            side_samples = {
                str(row["platoon_matchup"]): int(row["n_pitches"])
                for row in platoon_rows.group_by("platoon_matchup")
                .agg(pl.col("n_pitches").sum())
                .iter_rows(named=True)
            }
            adequate_platoon = all(
                side_samples.get(side, 0) >= _MIN_CAPABILITY_PITCHES for side in ("same", "opposite")
            )
        platoon_evidence = tuple(
            fact_id for path, fact_id in fact_ids.items() if path.startswith("platoon_mix.splits[")
        )
        capability_values = {
            "feature_attribution": bool(feature_attribution_evidence),
            "location_regions": bool(location_evidence),
            "pitch_targets": False,
            "biomechanical_causality": False,
            "tunneling_measurement": False,
            "platoon_splits": adequate_platoon and bool(platoon_evidence),
        }
        capability_evidence = {
            "feature_attribution": feature_attribution_evidence,
            "location_regions": location_evidence,
            "platoon_splits": platoon_evidence,
        }
        for capability, available in capability_values.items():
            evidence = capability_evidence.get(capability, ())
            capability_fact = register_capability_fact(
                registry=fact_registry,
                capability=capability,
                available=available,
                evidence_fact_ids=evidence or (data.lineage_fact_id,),
                frame=data.frame,
                producer_condition=(
                    "matching same-frame registered rows"
                    if available
                    else (
                        "typed artifact validator and natural-key evidence unavailable"
                        if capability
                        in {
                            "pitch_targets",
                            "biomechanical_causality",
                            "tunneling_measurement",
                        }
                        else "no matching manifest-covered producer artifact"
                    )
                ),
            )
            fact_ids[f"capability.{capability}"] = capability_fact.id

    return PitcherContext(
        **context_values,
        facts=fact_registry,
        fact_ids=fact_ids,
    )


class MultiFrameContext(BaseModel):
    """One PitcherContext per temporal frame.

    Wrapper shape (not per-field) so every PitcherContext field keeps its
    type and all render_/_build_*_input helpers stay unchanged. Today only
    RECENT is populated; later phases add PRIOR / MOST_RECENT / SEASON
    frames (CHANGES/RECAP modes, see §5).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    frames: dict[TemporalFrame, PitcherContext]

    def for_frame(self, frame: TemporalFrame) -> PitcherContext:
        try:
            return self.frames[frame]
        except KeyError:
            available = ", ".join(sorted(f.value for f in self.frames))
            raise ValueError(f"frame {frame.value!r} not assembled; available: {available}") from None

    @property
    def primary(self) -> PitcherContext:
        """The default frame current call sites read (recent-appearance window)."""
        return self.for_frame(TemporalFrame.RECENT)


def assemble_multi_frame_context(data: PitcherData) -> MultiFrameContext:
    """Assemble the multi-frame context.

    Currently only the recent-appearance frame is built (it equals today's
    assemble_pitcher_context output). Other appearance-count frames
    (PRIOR / MOST_RECENT / SEASON) are added when CHANGES/RECAP modes land.
    """
    return MultiFrameContext(
        frames={TemporalFrame.RECENT: assemble_pitcher_context(data)},
    )


def assemble_prior_context(data: PitcherData, recent_n: int, prior_m: int) -> PitcherContext:
    """Assemble a PitcherContext for the PRIOR appearance-count frame.

    Selects prior appearances from the authoritative scoring season, then
    replaces the canonical frame so every engine receives the same exact game
    identities. Season baselines remain unchanged for explicit year-over-year
    comparisons.
    """
    appearances = data.appearances
    season_column = "season" if "season" in appearances.columns else "game_year"
    if (
        data.frame is not None
        and data.frame.scoring_season is not None
        and season_column in appearances.columns
    ):
        appearances = appearances.filter(pl.col(season_column) == data.frame.scoring_season)
    prior_appearances = filter_to_prior_appearances(appearances, recent_n, prior_m)
    prior_data = data.with_frame(
        prior_appearances,
        temporal_frame=TemporalFrame.PRIOR,
    )
    return assemble_pitcher_context(prior_data)
