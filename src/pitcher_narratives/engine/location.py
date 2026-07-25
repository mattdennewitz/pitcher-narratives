"""Formal Location+ values and pitcher-relative spatial distributions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import polars as pl

from pitcher_narratives.data import PITCH_NAMES
from pitcher_narratives.facts import Fact, FactKind, FactRegistry

_LOCATION_COVERAGE_FLOOR = 80.0
_FORMAL_COLUMNS = {
    "pitch_type",
    "n_pitches",
    "xRV100_L",
    "L+",
}
_SPATIAL_COLUMNS = {
    "pitch_type",
    "stand",
    "pitcher_relative_location_region",
    "location_region_valid",
}
_PITCH_ID_COLUMNS = ("game_pk", "at_bat_number", "pitch_number")
_APPEARANCE_ID_COLUMNS = ("game_pk", "pitcher", "pitch_type")


@dataclass(frozen=True)
class FormalLocationValue:
    xrv100_l: float
    l_plus: float
    n_pitches: int
    frame_id: str
    source_fact_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    pitch_type: str
    pitch_name: str
    population: str


@dataclass(frozen=True)
class LocationDistribution:
    region_shares: Mapping[str, float]
    n_with_coordinates: int
    coverage_pct: float
    frame_id: str
    source_fact_ids: tuple[str, ...]
    region_fact_ids: Mapping[str, str]
    coverage_fact_id: str
    pitch_type: str
    pitch_name: str
    batter_side: str
    region_counts: Mapping[str, int]
    n_total: int
    sufficient: bool
    population: str


def _row_key(row: dict[str, Any], columns: tuple[str, ...]) -> str:
    return "|".join(f"{column}={row.get(column)!r}" for column in columns)


def _pitch_name(row: dict[str, Any]) -> str:
    value = row.get("pitch_name")
    return str(value) if value else PITCH_NAMES.get(str(row["pitch_type"]), str(row["pitch_type"]))


def _base_fact(
    *,
    row: dict[str, Any],
    metric: str,
    value: int | float | str | None,
    unit: str | None,
    variant: str | None,
    frame_id: str,
    population: str,
    source: str,
    semantic_key: str,
    sample_size: int | None,
    registry: FactRegistry,
    manifest_version: str | None,
) -> Fact:
    return registry.add(
        Fact.create(
            kind=FactKind.MODEL_OUTPUT if variant is not None else FactKind.OBSERVED,
            metric=metric,
            variant=variant,
            entity=_pitch_name(row),
            value=value,
            unit=unit,
            frame_id=frame_id,
            population=population,
            sample_size=sample_size,
            sufficiency="available" if value is not None else "unavailable",
            source=source,
            semantic_key=semantic_key,
            manifest_version=manifest_version,
        )
    )


def _derived_fact(
    *,
    metric: str,
    variant: str | None,
    entity: str,
    value: int | float | str | None,
    unit: str,
    frame_id: str,
    population: str,
    sample_size: int,
    semantic_key: str,
    source_fact_ids: tuple[str, ...],
    transform: str,
    registry: FactRegistry,
    manifest_version: str | None,
) -> Fact:
    return registry.add(
        Fact.create(
            kind=FactKind.COMPUTED,
            metric=metric,
            variant=variant,
            entity=entity,
            value=value,
            unit=unit,
            frame_id=frame_id,
            population=population,
            sample_size=sample_size,
            sufficiency="available",
            source="pitcher_narratives:deterministic_transform",
            semantic_key=semantic_key,
            source_fact_ids=source_fact_ids,
            transform=transform,
            manifest_version=manifest_version,
        )
    )


def compute_formal_location_values(
    appearance_rows: pl.DataFrame | None,
    *,
    frame_id: str,
    registry: FactRegistry | None = None,
    manifest_version: str | None = None,
    base_fact_resolver: Callable[[pl.DataFrame, tuple[str, ...]], tuple[str, ...]] | None = None,
) -> list[FormalLocationValue]:
    """Aggregate producer-emitted L-variant values over selected appearances."""
    if appearance_rows is None or appearance_rows.is_empty():
        return []
    if not _FORMAL_COLUMNS.issubset(appearance_rows.columns):
        return []

    facts = registry if registry is not None else FactRegistry()
    values: list[FormalLocationValue] = []
    for pitch_rows in appearance_rows.sort(
        [column for column in _APPEARANCE_ID_COLUMNS if column in appearance_rows.columns]
    ).partition_by("pitch_type", maintain_order=True):
        source_ids: list[str] = []
        source_rows: list[dict[str, Any]] = []
        weighted_xrv = 0.0
        weighted_l_plus = 0.0
        n_pitches = 0
        first = pitch_rows.row(0, named=True)
        population = f"{frame_id}; pitch_type={first['pitch_type']}"
        for row in pitch_rows.iter_rows(named=True):
            n = int(row["n_pitches"] or 0)
            xrv = row["xRV100_L"]
            l_plus = row["L+"]
            if n <= 0 or xrv is None or l_plus is None:
                continue
            source_rows.append(row)
            if base_fact_resolver is None:
                row_key = _row_key(row, _APPEARANCE_ID_COLUMNS)
                xrv_fact = _base_fact(
                    row=row,
                    metric="xRV100_L",
                    value=float(xrv),
                    unit="runs_per_100_pitches",
                    variant="L",
                    frame_id=frame_id,
                    population=population,
                    source="pitchingplus:pitcher_type_appearance",
                    semantic_key=f"{row_key}|metric=xRV100_L",
                    sample_size=n,
                    registry=facts,
                    manifest_version=manifest_version,
                )
                grade_fact = _base_fact(
                    row=row,
                    metric="L+",
                    value=float(l_plus),
                    unit="plus_grade",
                    variant="L",
                    frame_id=frame_id,
                    population=population,
                    source="pitchingplus:pitcher_type_appearance",
                    semantic_key=f"{row_key}|metric=L+",
                    sample_size=n,
                    registry=facts,
                    manifest_version=manifest_version,
                )
                source_ids.extend((xrv_fact.id, grade_fact.id))
            weighted_xrv += float(xrv) * n
            weighted_l_plus += float(l_plus) * n
            n_pitches += n
        if base_fact_resolver is not None and source_rows:
            source_ids.extend(
                base_fact_resolver(
                    pl.DataFrame(source_rows),
                    ("xRV100_L", "L+"),
                )
            )
        if n_pitches == 0:
            continue
        upstream_ids = tuple(sorted(source_ids))
        xrv_value = weighted_xrv / n_pitches
        l_plus_value = weighted_l_plus / n_pitches
        xrv_fact = _derived_fact(
            metric="xRV100_L",
            variant="L",
            entity=_pitch_name(first),
            value=xrv_value,
            unit="runs_per_100_pitches",
            frame_id=frame_id,
            population=population,
            sample_size=n_pitches,
            semantic_key=f"{first['pitch_type']}|weighted_xRV100_L",
            source_fact_ids=upstream_ids,
            transform="pitch_count_weighted_mean(xRV100_L)",
            registry=facts,
            manifest_version=manifest_version,
        )
        l_plus_fact = _derived_fact(
            metric="L+",
            variant="L",
            entity=_pitch_name(first),
            value=l_plus_value,
            unit="plus_grade",
            frame_id=frame_id,
            population=population,
            sample_size=n_pitches,
            semantic_key=f"{first['pitch_type']}|weighted_L+",
            source_fact_ids=upstream_ids,
            transform="pitch_count_weighted_mean(L+)",
            registry=facts,
            manifest_version=manifest_version,
        )
        values.append(
            FormalLocationValue(
                xrv100_l=xrv_value,
                l_plus=l_plus_value,
                n_pitches=n_pitches,
                frame_id=frame_id,
                source_fact_ids=upstream_ids,
                fact_ids=(xrv_fact.id, l_plus_fact.id),
                pitch_type=str(first["pitch_type"]),
                pitch_name=_pitch_name(first),
                population=population,
            )
        )
    return values


def _spatial_base_facts(
    rows: list[dict[str, Any]],
    *,
    frame_id: str,
    registry: FactRegistry,
    manifest_version: str | None,
) -> tuple[str, ...]:
    fact_ids = []
    for row in rows:
        region = row.get("pitcher_relative_location_region")
        fact = _base_fact(
            row=row,
            metric="pitcher_relative_location_region",
            value=str(region) if region is not None else None,
            unit="region",
            variant=None,
            frame_id=frame_id,
            population=(f"{frame_id}; pitch_type={row['pitch_type']}; batter_side={row.get('stand')}"),
            source="pitchingplus:all_pitches",
            semantic_key=_row_key(row, _PITCH_ID_COLUMNS),
            sample_size=1,
            registry=registry,
            manifest_version=manifest_version,
        )
        fact_ids.append(fact.id)
    return tuple(sorted(fact_ids))


def compute_location_distributions(
    all_pitch_rows: pl.DataFrame | None,
    *,
    frame_id: str,
    registry: FactRegistry | None = None,
    manifest_version: str | None = None,
    base_fact_resolver: Callable[[pl.DataFrame, tuple[str, ...]], tuple[str, ...]] | None = None,
) -> list[LocationDistribution]:
    """Compute exact region shares overall and by batter side from emitted labels."""
    if all_pitch_rows is None or all_pitch_rows.is_empty():
        return []
    if not _SPATIAL_COLUMNS.issubset(all_pitch_rows.columns):
        return []

    facts = registry if registry is not None else FactRegistry()
    distributions: list[LocationDistribution] = []
    for pitch_rows in all_pitch_rows.partition_by("pitch_type", maintain_order=True):
        first = pitch_rows.row(0, named=True)
        for batter_side in ("all", "L", "R"):
            scoped = pitch_rows if batter_side == "all" else pitch_rows.filter(pl.col("stand") == batter_side)
            if scoped.is_empty():
                continue
            rows = list(scoped.iter_rows(named=True))
            valid_rows = [
                row
                for row in rows
                if row.get("location_region_valid") is True
                and row.get("pitcher_relative_location_region") is not None
            ]
            counts = Counter(str(row["pitcher_relative_location_region"]) for row in valid_rows)
            n_total = len(rows)
            n_valid = len(valid_rows)
            coverage = n_valid / n_total * 100.0
            population = f"{frame_id}; pitch_type={first['pitch_type']}; batter_side={batter_side}"
            source_ids = (
                base_fact_resolver(
                    scoped,
                    (
                        "pitcher_relative_location_region",
                        "location_region_valid",
                    ),
                )
                if base_fact_resolver is not None
                else _spatial_base_facts(
                    rows,
                    frame_id=frame_id,
                    registry=facts,
                    manifest_version=manifest_version,
                )
            )
            ordered_counts = dict(sorted(counts.items()))
            shares = (
                {region: count / n_valid * 100.0 for region, count in ordered_counts.items()}
                if n_valid
                else {}
            )
            coverage_fact = _derived_fact(
                metric="location_region_coverage_pct",
                variant=None,
                entity=_pitch_name(first),
                value=coverage,
                unit="percent",
                frame_id=frame_id,
                population=population,
                sample_size=n_total,
                semantic_key=f"{first['pitch_type']}|{batter_side}|coverage",
                source_fact_ids=source_ids,
                transform="count(valid_region)/count(all_pitches)*100",
                registry=facts,
                manifest_version=manifest_version,
            )
            region_fact_ids = {
                region: _derived_fact(
                    metric=f"location_region_share:{region}",
                    variant=None,
                    entity=_pitch_name(first),
                    value=share,
                    unit="percent",
                    frame_id=frame_id,
                    population=population,
                    sample_size=n_valid,
                    semantic_key=(f"{first['pitch_type']}|{batter_side}|region={region}"),
                    source_fact_ids=source_ids,
                    transform=(f"count(region={region})/count(valid_region)*100"),
                    registry=facts,
                    manifest_version=manifest_version,
                ).id
                for region, share in shares.items()
            }
            distributions.append(
                LocationDistribution(
                    region_shares=MappingProxyType(shares),
                    n_with_coordinates=n_valid,
                    coverage_pct=coverage,
                    frame_id=frame_id,
                    source_fact_ids=source_ids,
                    region_fact_ids=MappingProxyType(region_fact_ids),
                    coverage_fact_id=coverage_fact.id,
                    pitch_type=str(first["pitch_type"]),
                    pitch_name=_pitch_name(first),
                    batter_side=batter_side,
                    region_counts=MappingProxyType(ordered_counts),
                    n_total=n_total,
                    sufficient=coverage >= _LOCATION_COVERAGE_FLOOR,
                    population=population,
                )
            )
    return distributions


def render_location_evidence(
    formal_values: list[FormalLocationValue],
    distributions: list[LocationDistribution],
) -> str:
    """Render only evidence carried by the typed Location contracts."""
    lines = ["## Formal Location+ Values"]
    if not formal_values:
        lines.append("- Unavailable: no selected L-variant appearance aggregates.")
    for value in formal_values:
        citations = ", ".join(value.fact_ids)
        lines.append(
            f"- {value.pitch_name} ({value.pitch_type}): "
            f"xRV100_L {value.xrv100_l:+.3f} runs/100 pitches; "
            f"L+ {value.l_plus:.1f}; N={value.n_pitches}; "
            f"frame {value.frame_id}; facts [{citations}]"
        )

    lines.append("\n## Pitcher-Relative Location Distribution")
    if not distributions:
        lines.append("- Unavailable: producer-emitted region labels are absent.")
    for distribution in distributions:
        coverage = (
            f"coverage {distribution.n_with_coordinates}/{distribution.n_total} "
            f"({distribution.coverage_pct:.1f}%)"
        )
        heading = (
            f"- {distribution.pitch_name} ({distribution.pitch_type}); "
            f"Batter side: {distribution.batter_side}; {coverage}; "
            f"coverage fact [{distribution.coverage_fact_id}]"
        )
        if not distribution.sufficient:
            lines.append(f"{heading}; unavailable for pattern claims.")
            continue
        lines.append(f"{heading}:")
        for region, count in distribution.region_counts.items():
            label = region.replace("_", " ")
            share = distribution.region_shares[region]
            lines.append(
                f"  - {label}: {count}/{distribution.n_with_coordinates} "
                f"valid-location pitches ({share:.1f}%); {coverage}; "
                f"fact [{distribution.region_fact_ids[region]}]"
            )
    return "\n".join(lines)
