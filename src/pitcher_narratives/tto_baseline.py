"""Offline league-SP within-game (TTO) baseline artifact.

Aggregates the league-wide statcast x all_pitches join into a long-form table
of expected per-pass decay (median + MAD of the per-appearance passN-pass1
delta) for velo and P+. Written once to var/tto_baseline.parquet and loaded at
report time by the deviation evaluator. Never computed on the hot path.

Pass bucketing matches ``engine.tto.compute_tto_analysis`` exactly: the raw
``n_thruorder_pitcher`` value is used as-is with no clamp. That field is NOT
capped at 3 in the underlying Statcast data (observed values run up to 5), so
this baseline can emit rows for pass_num > 3 too.

Run: `python -m pitcher_narratives.tto_baseline`
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from pitcher_narratives.data import (
    classify_game_roles,
    load_all_statcast,
    load_full_agg,
    tto_baseline_path,
)

__all__ = ["build_tto_baseline", "write_tto_baseline", "main"]


def build_tto_baseline(statcast: pl.DataFrame, all_pitches: pl.DataFrame) -> pl.DataFrame:
    """Long-form LEAGUE_SP baseline: median + MAD of per-appearance passN-pass1
    delta, per (pass_num, metric).

    Args:
        statcast: League-wide pitch-level Statcast frame (any number of
            pitchers/games), with at least pitcher, game_pk, pitch_number,
            n_thruorder_pitcher, release_speed, pitch_type, inning_topbot,
            at_bat_number.
        all_pitches: League-wide Pitching+ pitch-level frame with pitcher,
            game_pk, pitch_number, and P+.

    Returns:
        Long-form DataFrame: cohort_key, pass_num, metric, median_exp_delta,
        mad, n. Pass 1 (the Delta=0 reference pass) is not stored.
    """
    roles = classify_game_roles(statcast)  # (game_pk, pitcher, role)
    sp = roles.filter(pl.col("role") == "SP").select("game_pk", "pitcher")

    joined = (
        statcast.select(
            "pitcher", "game_pk", "pitch_number", "n_thruorder_pitcher", "release_speed", "pitch_type"
        )
        .filter(pl.col("pitch_type") != "")
        .join(
            all_pitches.select("pitcher", "game_pk", "pitch_number", "P+"),
            on=["pitcher", "game_pk", "pitch_number"],
            how="inner",
        )
        .join(sp, on=["game_pk", "pitcher"], how="inner")
        # Pass bucketing matches compute_tto_analysis verbatim: raw
        # n_thruorder_pitcher, no clamp (see module docstring).
        .with_columns(pl.col("n_thruorder_pitcher").alias("pass_num"))
    )

    # Per (appearance, pass) mean metric, then delta vs that appearance's pass 1.
    per_pass = joined.group_by("pitcher", "game_pk", "pass_num").agg(
        pl.col("release_speed").mean().alias("velo"),
        pl.col("P+").mean().alias("pplus"),
    )
    pass1 = per_pass.filter(pl.col("pass_num") == 1).select(
        "pitcher", "game_pk", pl.col("velo").alias("velo_p1"), pl.col("pplus").alias("pplus_p1")
    )
    deltas = (
        per_pass.filter(pl.col("pass_num") >= 2)
        .join(pass1, on=["pitcher", "game_pk"], how="inner")
        .with_columns(
            (pl.col("velo") - pl.col("velo_p1")).alias("d_velo"),
            (pl.col("pplus") - pl.col("pplus_p1")).alias("d_pplus"),
        )
    )

    out = []
    for metric, dcol in (("velo", "d_velo"), ("pplus", "d_pplus")):
        agg = deltas.group_by("pass_num").agg(
            pl.col(dcol).median().alias("median_exp_delta"),
            (pl.col(dcol) - pl.col(dcol).median()).abs().median().alias("mad"),
            pl.len().alias("n"),
        )
        out.append(
            agg.with_columns(
                pl.lit("LEAGUE_SP").alias("cohort_key"),
                pl.lit(metric).alias("metric"),
            ).select("cohort_key", "pass_num", "metric", "median_exp_delta", "mad", "n")
        )
    return pl.concat(out).sort("pass_num", "metric")


def write_tto_baseline(df: pl.DataFrame, path: Path | None = None) -> Path:
    """Write the baseline DataFrame to a parquet artifact.

    Args:
        df: Long-form baseline DataFrame from ``build_tto_baseline``.
        path: Destination path. Defaults to ``data.tto_baseline_path()``.

    Returns:
        The path written to.
    """
    path = path or tto_baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def main() -> None:
    """Build and write the league-SP TTO baseline artifact from live data."""
    statcast = load_all_statcast()
    all_pitches = load_full_agg("all_pitches")
    df = build_tto_baseline(statcast, all_pitches)
    out = write_tto_baseline(df)
    print(f"wrote {out} ({df.height} rows)")


if __name__ == "__main__":
    main()
