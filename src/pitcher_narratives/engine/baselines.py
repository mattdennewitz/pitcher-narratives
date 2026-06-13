"""League baseline computation and rendering.

Computes league-average physical/quality profiles and S-variant benchmarks
from the season aggregates, plus outlier tagging and the markdown rendering
used to ground specialist prompts.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import load_all_statcast, load_full_agg
from pitcher_narratives.engine._common import _FEET_TO_INCHES, _SWING_DESCRIPTIONS

# ── League baselines ─────────────────────────────────────────────────

@dataclass
class LeagueBaseline:
    """League-average physical profile and S-variant benchmarks for a pitch type.

    Physical metrics (velo, movement, zone/chase) come from the Statcast parquet.
    S-variant benchmarks (S+, xSwing_S, xWhiff_S, xRV100_S) come from the
    pitcher_type CSV aggregated across all pitchers, weighted by n_pitches.
    """

    pitch_type: str
    pitch_name: str
    n_pitches: int
    # Physical averages
    avg_velo: float
    avg_pfx_x: float
    avg_pfx_z: float
    zone_pct: float
    chase_pct: float
    # Physical standard deviations (for outlier detection)
    velo_std: float
    pfx_x_std: float
    pfx_z_std: float
    # S-variant benchmarks (league averages weighted by n_pitches)
    avg_s_plus: float | None = None
    avg_xswing_s: float | None = None
    avg_xwhiff_s: float | None = None
    avg_xrv100_s: float | None = None


_league_baselines_cache: list[LeagueBaseline] | None = None


def compute_league_baselines() -> list[LeagueBaseline]:
    """Compute league-average velocity, movement, zone/chase, and S-variant benchmarks.

    Physical metrics and standard deviations come from the Statcast parquet.
    S-variant benchmarks (S+, xSwing_S, xWhiff_S, xRV100_S) are weighted
    averages from the pitcher_type CSV across all pitchers.

    Results are cached after first call. Only includes pitch types with
    at least 100 pitches in the dataset.

    Returns:
        List of LeagueBaseline sorted by pitch count descending.
    """
    global _league_baselines_cache
    if _league_baselines_cache is not None:
        return _league_baselines_cache

    df = load_all_statcast(
        columns=[
            "pitch_type", "pitch_name", "release_speed",
            "pfx_x", "pfx_z", "zone", "description", "level",
        ],
    )
    # MLB-only norm: exclude minor-league (A/AAA) and WBC pitches.
    df = df.filter(pl.col("level") == "MLB")
    df = df.filter(pl.col("release_speed").is_not_null())

    is_in_zone = pl.col("zone").is_between(1, 9)
    is_swing = pl.col("description").is_in(list(_SWING_DESCRIPTIONS))

    agg = (
        df.group_by("pitch_type", "pitch_name")
        .agg(
            pl.len().alias("n"),
            pl.col("release_speed").mean().alias("avg_velo"),
            pl.col("release_speed").std().alias("velo_std"),
            pl.col("pfx_x").mean().alias("avg_pfx_x"),
            pl.col("pfx_x").std().alias("pfx_x_std"),
            pl.col("pfx_z").mean().alias("avg_pfx_z"),
            pl.col("pfx_z").std().alias("pfx_z_std"),
            (is_in_zone.mean() * 100).alias("zone_pct"),
            # Chase: swings on pitches outside zones 1-9
            ((is_in_zone.not_() & is_swing).sum()
             / (is_in_zone.not_()).sum() * 100).alias("chase_pct"),
        )
        .filter(pl.col("n") >= 100)
        .sort("n", descending=True)
    )

    # --- S-variant benchmarks from pitcher_type CSV ---
    s_variant_lookup: dict[str, dict[str, float]] = {}
    pt_df = load_full_agg("pitcher_type")
    if "level" in pt_df.columns:
        pt_df = pt_df.filter(pl.col("level") == "MLB")
    if not pt_df.is_empty():
        # Weighted average across all pitchers per pitch type
        s_agg = (
            pt_df.filter(pl.col("n_pitches") >= 10)
            .group_by("pitch_type")
            .agg(
                (pl.col("S+") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
                (pl.col("xSwing_S") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
                (pl.col("xWhiff_S") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
                (pl.col("xRV100_S") * pl.col("n_pitches")).sum()
                / pl.col("n_pitches").sum(),
            )
        )
        for row in s_agg.iter_rows(named=True):
            s_variant_lookup[row["pitch_type"]] = {
                "avg_s_plus": float(row["S+"]),
                "avg_xswing_s": float(row["xSwing_S"]),
                "avg_xwhiff_s": float(row["xWhiff_S"]),
                "avg_xrv100_s": float(row["xRV100_S"]),
            }

    results = []
    for row in agg.iter_rows(named=True):
        pt = row["pitch_type"]
        s_data = s_variant_lookup.get(pt, {})
        results.append(
            LeagueBaseline(
                pitch_type=pt,
                pitch_name=row["pitch_name"],
                n_pitches=row["n"],
                avg_velo=float(row["avg_velo"]),
                avg_pfx_x=float(row["avg_pfx_x"]) * _FEET_TO_INCHES,
                avg_pfx_z=float(row["avg_pfx_z"]) * _FEET_TO_INCHES,
                zone_pct=float(row["zone_pct"]),
                chase_pct=float(row["chase_pct"]),
                velo_std=float(row["velo_std"]) if row["velo_std"] is not None else 0.0,
                pfx_x_std=float(row["pfx_x_std"]) * _FEET_TO_INCHES if row["pfx_x_std"] is not None else 0.0,
                pfx_z_std=float(row["pfx_z_std"]) * _FEET_TO_INCHES if row["pfx_z_std"] is not None else 0.0,
                avg_s_plus=s_data.get("avg_s_plus"),
                avg_xswing_s=s_data.get("avg_xswing_s"),
                avg_xwhiff_s=s_data.get("avg_xwhiff_s"),
                avg_xrv100_s=s_data.get("avg_xrv100_s"),
            )
        )

    _league_baselines_cache = results
    return results


def outlier_tag(value: float, avg: float, std: float) -> str:
    """Return OUTLIER or NORMAL tag based on z-score from league average."""
    if std == 0:
        return "NORMAL"
    z = (value - avg) / std
    if abs(z) > 1.5:
        direction = "above" if z > 0 else "below"
        return f"OUTLIER ({direction} avg, z={z:+.1f})"
    return f"NORMAL (z={z:+.1f})"


def render_league_baselines(pitch_types: list[str]) -> str:
    """Render league-average baselines with normal ranges and S-variant benchmarks.

    Includes standard deviations so agents can determine whether a pitcher's
    metrics are outliers or within the normal range for that pitch type.
    """
    baselines = compute_league_baselines()
    lookup = {b.pitch_type: b for b in baselines}

    lines = [
        "## League Baselines (2026, all pitchers)",
        "Use these baselines to determine whether a metric is an outlier or normal.",
        "A metric within ±1.5 stddev of the league average is NORMAL for that pitch type.",
        "",
    ]
    for pt in pitch_types:
        b = lookup.get(pt)
        if b is None:
            continue
        lines.append(f"### {b.pitch_name} ({b.pitch_type})")
        lines.append(
            f"- Velocity: {b.avg_velo:.1f} mph (stddev {b.velo_std:.1f}, "
            f"normal range {b.avg_velo - 1.5 * b.velo_std:.1f}–{b.avg_velo + 1.5 * b.velo_std:.1f})"  # noqa: RUF001
        )
        lines.append(f"- Horizontal movement (pfx_x): {b.avg_pfx_x:.1f} in (stddev {b.pfx_x_std:.1f})")
        lines.append(f"- Vertical movement (pfx_z): {b.avg_pfx_z:.1f} in (stddev {b.pfx_z_std:.1f})")
        lines.append(f"- Zone%: {b.zone_pct:.1f}, Chase%: {b.chase_pct:.1f}")
        if b.avg_s_plus is not None:
            xswing = f"{b.avg_xswing_s * 100:.1f}%" if b.avg_xswing_s is not None else "--"
            xwhiff = f"{b.avg_xwhiff_s * 100:.1f}%" if b.avg_xwhiff_s is not None else "--"
            xrv = f"{b.avg_xrv100_s:.2f}" if b.avg_xrv100_s is not None else "--"
            lines.append(
                f"- S-variant league avg: S+ {b.avg_s_plus:.0f}, "
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


