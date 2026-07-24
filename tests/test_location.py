"""Formal Location+ and spatial-distribution evidence contracts."""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

from pitcher_narratives.engine.location import (
    compute_formal_location_values,
    compute_location_distributions,
    render_location_evidence,
)
from pitcher_narratives.facts import Fact, FactKind, FactRegistry
from pitcher_narratives.pipeline import _build_location_input

_FRAME = "recent:test"
_MANIFEST = "pitchingplus:test:1.0.0"


def _manifest_registry(
    rows: pl.DataFrame,
    *,
    grain: str,
    columns: tuple[str, ...],
    key_columns: tuple[str, ...],
) -> tuple[FactRegistry, object]:
    source = f"pitchingplus:{grain}"

    def row_id(row):
        return "row:" + "|".join(f"{column}={row.get(column)!r}" for column in key_columns)

    manifest_rows = {source: {row_id(row) for row in rows.iter_rows(named=True)}}
    registry = FactRegistry(
        manifest_version=_MANIFEST,
        manifest_rows=manifest_rows,
    )
    fact_ids = {}
    for row in rows.iter_rows(named=True):
        for column in columns:
            value = row.get(column)
            if value is None:
                continue
            fact = registry.add(
                Fact.create(
                    kind=(FactKind.MODEL_OUTPUT if column in {"xRV100_L", "L+"} else FactKind.OBSERVED),
                    metric=f"{grain}.{column}",
                    variant="L" if column in {"xRV100_L", "L+"} else None,
                    entity=f"pitcher:{row.get('pitcher')}|pitch_type:{row.get('pitch_type')}",
                    value=value,
                    unit=None,
                    frame_id=_FRAME,
                    population=_MANIFEST,
                    sample_size=int(row.get("n_pitches", 1)),
                    sufficiency="available",
                    source=source,
                    semantic_key=f"{row_id(row)}|metric={column}",
                    manifest_version=_MANIFEST,
                    source_row_id=row_id(row),
                )
            )
            fact_ids[(row_id(row), column)] = fact.id

    def resolve(selected: pl.DataFrame, selected_columns: tuple[str, ...]):
        return tuple(
            sorted(
                fact_ids[(row_id(row), column)]
                for row in selected.iter_rows(named=True)
                for column in selected_columns
                if row.get(column) is not None
            )
        )

    return registry, resolve


def _formal_rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "manifest_id": ["manifest:v1"] * 3,
            "season": [2026] * 3,
            "level": ["MLB"] * 3,
            "game_type": ["R"] * 3,
            "game_pk": [1, 2, 3],
            "pitcher": [10] * 3,
            "pitch_type": ["FF"] * 3,
            "pitch_name": ["Four-Seam Fastball"] * 3,
            "n_pitches": [10, 30, 50],
            "xRV100_L": [-0.5, -1.5, 99.0],
            "L+": [101.0, 111.0, -999.0],
            "xRV100_P": [10.0, 20.0, -50.0],
            "xRV100_S": [9.0, 19.0, 50.0],
        }
    )


def _formal_values(rows: pl.DataFrame):
    registry, resolve = _manifest_registry(
        rows,
        grain="pitcher_type_appearance",
        columns=("xRV100_L", "L+"),
        key_columns=("game_pk", "pitcher", "pitch_type"),
    )
    return compute_formal_location_values(
        rows,
        frame_id=_FRAME,
        registry=registry,
        manifest_version=_MANIFEST,
        base_fact_resolver=resolve,
    )


def test_formal_location_reads_l_variant_without_reconstructing_p_minus_s():
    selected = _formal_rows().filter(pl.col("game_pk").is_in([1, 2]))

    values = _formal_values(selected)

    assert len(values) == 1
    value = values[0]
    assert value.pitch_type == "FF"
    assert value.xrv100_l == pytest.approx(-1.25)
    assert value.l_plus == pytest.approx(108.5)
    assert value.n_pitches == 40
    assert value.frame_id == "recent:test"
    assert len(value.source_fact_ids) == 4


def _spatial_rows(valid_count: int = 8, invalid_count: int = 2) -> pl.DataFrame:
    regions = ["high_arm_side"] * 3 + ["heart"] * 5
    stands = ["L", "L", "R", "R", "R", "R", "R", "R"]
    rows = [
        {
            "manifest_id": "manifest:v1",
            "game_pk": index + 1,
            "at_bat_number": 1,
            "pitch_number": 1,
            "pitcher": 10,
            "pitch_type": "FF",
            "pitch_name": "Four-Seam Fastball",
            "stand": stands[index],
            "pitcher_relative_location_region": regions[index],
            "location_region_valid": True,
        }
        for index in range(valid_count)
    ]
    rows.extend(
        {
            "manifest_id": "manifest:v1",
            "game_pk": 100 + index,
            "at_bat_number": 1,
            "pitch_number": 1,
            "pitcher": 10,
            "pitch_type": "FF",
            "pitch_name": "Four-Seam Fastball",
            "stand": "R",
            "pitcher_relative_location_region": None,
            "location_region_valid": False,
        }
        for index in range(invalid_count)
    )
    return pl.DataFrame(rows)


def _spatial_distributions(rows: pl.DataFrame):
    registry, resolve = _manifest_registry(
        rows,
        grain="all_pitches",
        columns=(
            "pitcher_relative_location_region",
            "location_region_valid",
        ),
        key_columns=("game_pk", "at_bat_number", "pitch_number"),
    )
    return compute_location_distributions(
        rows,
        frame_id=_FRAME,
        registry=registry,
        manifest_version=_MANIFEST,
        base_fact_resolver=resolve,
    )


def test_distribution_reports_exact_denominators_coverage_and_batter_splits():
    distributions = _spatial_distributions(_spatial_rows())

    all_batters = next(item for item in distributions if item.batter_side == "all")
    left = next(item for item in distributions if item.batter_side == "L")
    right = next(item for item in distributions if item.batter_side == "R")
    assert all_batters.region_counts == {"heart": 5, "high_arm_side": 3}
    assert all_batters.region_shares == {
        "heart": pytest.approx(62.5),
        "high_arm_side": pytest.approx(37.5),
    }
    assert all_batters.n_with_coordinates == 8
    assert all_batters.n_total == 10
    assert all_batters.coverage_pct == pytest.approx(80.0)
    assert all_batters.sufficient is True
    assert left.n_with_coordinates == 2
    assert left.n_total == 2
    assert right.n_with_coordinates == 6
    assert right.n_total == 8
    assert set(left.source_fact_ids) < set(all_batters.source_fact_ids)
    assert set(right.source_fact_ids) < set(all_batters.source_fact_ids)


def test_distribution_below_coverage_floor_is_explicitly_unavailable():
    rows = _spatial_rows(valid_count=8, invalid_count=2).with_columns(
        pl.when(pl.col("game_pk") == 1)
        .then(False)
        .otherwise(pl.col("location_region_valid"))
        .alias("location_region_valid")
    )

    distribution = next(item for item in _spatial_distributions(rows) if item.batter_side == "all")

    assert distribution.coverage_pct == pytest.approx(70.0)
    assert distribution.sufficient is False
    rendered = render_location_evidence([], [distribution])
    assert "unavailable for pattern claims" in rendered
    assert "high" not in rendered.lower()


def test_rendered_spatial_claims_carry_numerator_denominator_and_coverage():
    distributions = _spatial_distributions(_spatial_rows())

    rendered = render_location_evidence([], distributions)

    assert "5/8 valid-location pitches (62.5%)" in rendered
    assert "coverage 8/10 (80.0%)" in rendered
    assert "Batter side: L" in rendered
    assert "Batter side: R" in rendered


def test_location_specialist_handoff_excludes_reconstructed_and_proxy_evidence():
    formal = _formal_values(_formal_rows().filter(pl.col("game_pk").is_in([1, 2])))
    distributions = _spatial_distributions(_spatial_rows())
    context = SimpleNamespace(
        pitcher_name="Test Pitcher",
        throws="R",
        role="RP",
        formal_location=formal,
        location_distributions=distributions,
        intermediates=[],
        execution=[],
        arsenal=[],
        league_baselines=[],
    )

    handoff = str(_build_location_input(context, include_evidence=False)[2])
    assert "Calibration unavailable: no manifest-covered calibration artifact." in handoff
    assert "predictive reliability as unknown" in handoff

    assert "Formal Location+ Values" in handoff
    assert "Pitcher-Relative Location Distribution" in handoff
    assert "xRV100_L -1.250" in handoff
    assert "P vs S" not in handoff
    assert "xSwing" not in handoff
    assert "Zone%" not in handoff
    assert "CSW%" not in handoff
