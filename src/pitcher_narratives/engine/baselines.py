"""Parse and render manifest-covered physical reference artifacts."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PITCH_NAMES
from pitcher_narratives.engine._common import _MIN_PITCHES

# ── League baselines ─────────────────────────────────────────────────


@dataclass(frozen=True)
class BaselinePopulation:
    """Exact producer-declared population behind one physical reference."""

    manifest_id: str
    seasons: tuple[int, ...]
    level: str
    game_types: tuple[str, ...]
    pitch_type: str
    pitcher_handling: str
    statistical_unit: str
    weighting: str
    unit: str
    n_pitches: int


@dataclass
class LeagueBaseline:
    """Emitted pitch-type reference; Narratives performs no population scan."""

    pitch_type: str
    pitch_name: str
    n_pitches: int
    avg_velo: float
    avg_arm_side_pfx_x: float
    avg_pfx_z: float
    zone_pct: float
    chase_pct: float
    velo_std: float | None
    arm_side_pfx_x_std: float | None
    pfx_z_std: float | None
    population: BaselinePopulation
    metric_sample_sizes: dict[str, int]
    avg_s_plus: float | None = None
    avg_xswing_s: float | None = None
    avg_xwhiff_s: float | None = None
    avg_xrv100_s: float | None = None


def _optional_float(row: dict[str, object] | None, column: str) -> float | None:
    if row is None or row.get(column) is None:
        return None
    return float(row[column])  # type: ignore[arg-type]


def compute_league_baselines(
    reference_rows: pl.DataFrame | None = None,
) -> list[LeagueBaseline]:
    """Parse the manifest-covered, long-form pitch-type reference table."""
    if reference_rows is None or reference_rows.is_empty():
        return []
    required = {
        "manifest_id",
        "seasons",
        "level",
        "game_types",
        "pitch_type",
        "pitcher_handling",
        "statistical_unit",
        "weighting",
        "unit",
        "metric",
        "n_pitches",
        "mean",
        "std",
    }
    if missing := required - set(reference_rows.columns):
        raise ValueError(f"pitch_type_reference is missing columns: {sorted(missing)}")
    compatible = reference_rows.filter(
        (pl.col("level") == "MLB")
        & (pl.col("game_types") == "R")
        & (pl.col("pitcher_handling") == "handedness_normalized")
        & (pl.col("statistical_unit") == "pitch")
        & (pl.col("weighting") == "pitch_weighted")
    )
    results: list[LeagueBaseline] = []
    required_metrics = {
        "release_speed",
        "arm_side_pfx_x",
        "pfx_z",
        "zone_pct",
        "chase_pct",
    }
    expected_units = {
        "release_speed": "mph",
        "arm_side_pfx_x": "inches",
        "pfx_z": "inches",
        "zone_pct": "percent",
        "chase_pct": "percent",
        "S+": "plus_grade",
        "xSwing_S": "probability",
        "xWhiff_S": "probability",
        "xRV100_S": "runs_per_100_pitches",
    }
    for pitch_rows in compatible.partition_by("pitch_type", maintain_order=True):
        metrics = {str(row["metric"]): row for row in pitch_rows.iter_rows(named=True)}
        if not required_metrics.issubset(metrics):
            continue
        for metric, row in metrics.items():
            expected_unit = expected_units.get(metric)
            if expected_unit is not None and row["unit"] != expected_unit:
                raise ValueError(
                    f"pitch_type_reference metric {metric!r} has unit "
                    f"{row['unit']!r}; expected {expected_unit!r}"
                )
        population_signatures = {
            (
                row["manifest_id"],
                row["seasons"],
                row["level"],
                row["game_types"],
                row["pitch_type"],
                row["pitcher_handling"],
                row["statistical_unit"],
                row["weighting"],
            )
            for row in metrics.values()
        }
        if len(population_signatures) != 1:
            raise ValueError("pitch_type_reference metrics disagree on reference population")
        arm_side = metrics["arm_side_pfx_x"]
        seasons = tuple(int(value) for value in str(arm_side["seasons"]).split(",") if value)
        population = BaselinePopulation(
            manifest_id=str(arm_side["manifest_id"]),
            seasons=seasons,
            level=str(arm_side["level"]),
            game_types=tuple(value for value in str(arm_side["game_types"]).split(",") if value),
            pitch_type=str(arm_side["pitch_type"]),
            pitcher_handling=str(arm_side["pitcher_handling"]),
            statistical_unit=str(arm_side["statistical_unit"]),
            weighting=str(arm_side["weighting"]),
            unit=str(arm_side["unit"]),
            n_pitches=int(arm_side["n_pitches"]),
        )
        results.append(
            LeagueBaseline(
                pitch_type=population.pitch_type,
                pitch_name=PITCH_NAMES.get(population.pitch_type, population.pitch_type),
                n_pitches=population.n_pitches,
                avg_velo=float(metrics["release_speed"]["mean"]),
                avg_arm_side_pfx_x=float(arm_side["mean"]),
                avg_pfx_z=float(metrics["pfx_z"]["mean"]),
                zone_pct=float(metrics["zone_pct"]["mean"]),
                chase_pct=float(metrics["chase_pct"]["mean"]),
                velo_std=_optional_float(metrics["release_speed"], "std"),
                arm_side_pfx_x_std=_optional_float(arm_side, "std"),
                pfx_z_std=_optional_float(metrics["pfx_z"], "std"),
                metric_sample_sizes={metric: int(row["n_pitches"]) for metric, row in metrics.items()},
                population=population,
                avg_s_plus=_optional_float(metrics.get("S+"), "mean"),
                avg_xswing_s=_optional_float(metrics.get("xSwing_S"), "mean"),
                avg_xwhiff_s=_optional_float(metrics.get("xWhiff_S"), "mean"),
                avg_xrv100_s=_optional_float(metrics.get("xRV100_S"), "mean"),
            )
        )
    return sorted(results, key=lambda baseline: baseline.n_pitches, reverse=True)


def outlier_tag(
    value: float,
    avg: float,
    std: float | None,
    n: int,
    floor: int = _MIN_PITCHES,
) -> str:
    """Classify absolute rarity only when sample and reference permit it."""
    if n < floor:
        return f"SMALL SAMPLE, N={n} -- untagged"
    if std is None:
        return "UNAVAILABLE -- reference spread not emitted"
    if std <= 0:
        return "UNAVAILABLE -- zero-variance reference"
    z = (value - avg) / std
    if abs(z) > 1.5:
        direction = "above" if z > 0 else "below"
        return f"OUTLIER ({direction} avg, z={z:+.1f})"
    return f"NORMAL (z={z:+.1f})"


def render_league_baselines(pitch_types: list[str], baselines: list[LeagueBaseline] | None = None) -> str:
    """Render the exact emitted population and absolute-rarity comparison."""
    lookup = {baseline.pitch_type: baseline for baseline in (baselines or [])}
    selected = [lookup[pt] for pt in pitch_types if pt in lookup]
    if not selected:
        return (
            "## Physical Reference Baselines\n\n"
            "Unavailable: compatible emitted pitch-type reference not found."
        )

    population = selected[0].population
    seasons = ", ".join(str(season) for season in population.seasons)
    lines = [
        "## Physical Reference Baselines",
        (
            f"Population: manifest `{population.manifest_id}`; seasons {seasons}; "
            f"{population.level} regular season; "
            f"{population.weighting.replace('_', '-')} pitches; "
            f"{population.pitcher_handling.replace('_', '-')}; "
            f"statistical unit `{population.statistical_unit}`."
        ),
        (
            "These z-scores describe absolute physical rarity within that population. "
            "They are not recent-vs-season change significance, role comparisons, "
            "or model feature importance. Official 100-centered Pitching+ grades "
            "retain their producer-defined model benchmark."
        ),
        "",
    ]
    for baseline in selected:
        velo_spread = f"{baseline.velo_std:.1f}" if baseline.velo_std is not None else "unavailable"
        arm_side_spread = (
            f"{baseline.arm_side_pfx_x_std:.1f}" if baseline.arm_side_pfx_x_std is not None else "unavailable"
        )
        vertical_spread = f"{baseline.pfx_z_std:.1f}" if baseline.pfx_z_std is not None else "unavailable"
        lines.append(f"### {baseline.pitch_name} ({baseline.pitch_type})")
        lines.append(
            f"- Velocity: {baseline.avg_velo:.1f} mph "
            f"(pitch-level SD {velo_spread}, "
            f"N={baseline.metric_sample_sizes['release_speed']:,})"
        )
        lines.append(
            "- Arm-side horizontal movement "
            f"(arm_side_pfx_x): {baseline.avg_arm_side_pfx_x:.1f} in "
            f"(pitch-level SD {arm_side_spread}, "
            f"N={baseline.metric_sample_sizes['arm_side_pfx_x']:,})"
        )
        lines.append(
            f"- Vertical movement (pfx_z): {baseline.avg_pfx_z:.1f} in "
            f"(pitch-level SD {vertical_spread}, "
            f"N={baseline.metric_sample_sizes['pfx_z']:,})"
        )
        lines.append(
            f"- Zone%: {baseline.zone_pct:.1f} "
            f"(N={baseline.metric_sample_sizes['zone_pct']:,}), "
            f"Chase%: {baseline.chase_pct:.1f} "
            f"(N={baseline.metric_sample_sizes['chase_pct']:,})"
        )
        if baseline.avg_s_plus is not None:
            xswing = f"{baseline.avg_xswing_s * 100:.1f}%" if baseline.avg_xswing_s is not None else "--"
            xwhiff = f"{baseline.avg_xwhiff_s * 100:.1f}%" if baseline.avg_xwhiff_s is not None else "--"
            xrv = f"{baseline.avg_xrv100_s:.2f}" if baseline.avg_xrv100_s is not None else "--"
            lines.append(
                f"- S-variant league avg: S+ {baseline.avg_s_plus:.0f}, "
                f"xSwing_S {xswing}, xWhiff_S {xwhiff}, xRV100_S {xrv}"
            )
        lines.append("")
    return "\n".join(lines)


def format_s_variant_comparisons(
    baseline: LeagueBaseline | None,
    xswing_s: float | None,
    xwhiff_s: float | None,
    xrv100_s: float | None,
) -> list[str]:
    """Format S-variant predictions with league comparison deltas.

    Returns a list of formatted strings like:
        ["xSwing_S 37.0% (-7.5pp vs league)", "xWhiff_S 31.2% (-7.6pp vs league)", ...]
    """
    parts: list[str] = []
    b = baseline

    xswing_str = f"{xswing_s * 100:.1f}%" if xswing_s is not None else "--"
    if b and xswing_s is not None and b.avg_xswing_s is not None:
        d = (xswing_s - b.avg_xswing_s) * 100
        parts.append(f"xSwing_S {xswing_str} ({d:+.1f}pp vs league)")
    else:
        parts.append(f"xSwing_S {xswing_str}")

    xwhiff_str = f"{xwhiff_s * 100:.1f}%" if xwhiff_s is not None else "--"
    if b and xwhiff_s is not None and b.avg_xwhiff_s is not None:
        d = (xwhiff_s - b.avg_xwhiff_s) * 100
        parts.append(f"xWhiff_S {xwhiff_str} ({d:+.1f}pp vs league)")
    else:
        parts.append(f"xWhiff_S {xwhiff_str}")

    xrv_str = f"{xrv100_s:.2f}" if xrv100_s is not None else "--"
    if b and xrv100_s is not None and b.avg_xrv100_s is not None:
        d = xrv100_s - b.avg_xrv100_s
        parts.append(f"xRV100_S {xrv_str} ({d:+.2f} vs league)")
    else:
        parts.append(f"xRV100_S {xrv_str}")

    return parts
