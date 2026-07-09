"""Validity + censoring harness for the game-shape deviation gate (diagnostic).

Tier-2 probes that bring in independent OUTCOME data (Statcast run value +
xwOBA) rather than pitcher reputations, over the league SP population:

  Probe A (face validity): is a within-game P+ move a real performance signal?
      Per pitcher (pooled over all SP appearances), compute per-pass ΔP+ and the
      matching Δ(outcome): Δ mean pitcher run value (delta_pitcher_run_exp, +=
      worse for the pitcher) and Δ mean xwOBA (+= worse). Correlate ΔP+ vs Δrv
      across pitchers per pass (expect NEGATIVE: P+ down <-> outcome worse), and
      report concordance of P+-material cells with outcome-degraded cells.

  Probe B (survivor/censoring): classify each appearance deep (max pass >= 4) vs
      pulled-early (<= 3). Compare pass-2/3 outcomes for deep vs pulled
      appearances (are pulled guys getting hit harder in those passes?), and
      quantify how outcome-selected the deep-pass sample the detector relies on
      actually is.

Run (needs statcast + aggs):
  PITCHER_NARRATIVES_DATA_DIR=/path uv run python scripts/tto_validity.py [--min-per-pass N]
"""

from __future__ import annotations

import argparse
import sys

import polars as pl

from pitcher_narratives.data import classify_game_roles, load_all_statcast, load_full_agg

_RV = "delta_pitcher_run_exp"   # per-pitch, pitcher perspective: + = worse for pitcher
_XW = "estimated_woba_using_speedangle"  # xwOBA on contact: + = worse for pitcher


def _corr(a: list[float], b: list[float]) -> float:
    df = pl.DataFrame({"a": a, "b": b}).drop_nulls()
    if df.height < 3:
        return float("nan")
    return df.select(pl.corr("a", "b")).item()


def _spearman(a: list[float], b: list[float]) -> float:
    df = pl.DataFrame({"a": a, "b": b}).drop_nulls()
    if df.height < 3:
        return float("nan")
    df = df.with_columns(pl.col("a").rank().alias("ra"), pl.col("b").rank().alias("rb"))
    return df.select(pl.corr("ra", "rb")).item()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-per-pass", type=int, default=50,
                    help="min pooled pitches a pitcher needs at a pass to be included (Probe A)")
    args = ap.parse_args()

    print("Loading league statcast + P+ ...", file=sys.stderr)
    sc = load_all_statcast(columns=[
        "pitcher", "game_pk", "pitch_number", "n_thruorder_pitcher",
        "inning", "inning_topbot", "at_bat_number", _RV, _XW,
    ])
    roles = classify_game_roles(sc)
    sp = roles.filter(pl.col("role") == "SP").select("game_pk", "pitcher")
    ap_pp = load_full_agg("all_pitches").select("pitcher", "game_pk", "pitch_number", "P+")

    j = (
        sc.join(ap_pp, on=["pitcher", "game_pk", "pitch_number"], how="left")
        .join(sp, on=["game_pk", "pitcher"], how="inner")
        .rename({"n_thruorder_pitcher": "pass"})
    )
    n_slices = j.select(["game_pk", "pitcher"]).unique().height
    print(f"  {j.height:,} SP pitches across {n_slices:,} appearances", file=sys.stderr)

    # ── Per (pitcher, game_pk, pass) appearance-pass means + max pass per appearance ──
    per = (
        j.group_by("pitcher", "game_pk", "pass")
        .agg(pl.col("P+").mean().alias("pplus"), pl.col(_RV).mean().alias("rv"),
             pl.col(_XW).mean().alias("xw"), pl.len().alias("pitches"))
    )
    appmax = per.group_by("pitcher", "game_pk").agg(pl.col("pass").max().alias("max_pass"))

    # ══ PROBE A ══ per-pitcher pooled-per-pass deltas vs pass 1, then correlate.
    pool = (
        j.group_by("pitcher", "pass")
        .agg(pl.col("P+").mean().alias("pplus"), pl.col(_RV).mean().alias("rv"),
             pl.col(_XW).mean().alias("xw"), pl.len().alias("pitches"))
        .filter(pl.col("pitches") >= args.min_per_pass)
    )
    p1 = pool.filter(pl.col("pass") == 1).select(
        "pitcher", pl.col("pplus").alias("p1_pplus"), pl.col("rv").alias("p1_rv"), pl.col("xw").alias("p1_xw"))
    deltas = (
        pool.filter(pl.col("pass") >= 2)
        .join(p1, on="pitcher", how="inner")
        .with_columns((pl.col("pplus") - pl.col("p1_pplus")).alias("d_pplus"),
                      (pl.col("rv") - pl.col("p1_rv")).alias("d_rv"),
                      (pl.col("xw") - pl.col("p1_xw")).alias("d_xw"))
    )

    print("\n" + "=" * 74)
    print("PROBE A — FACE VALIDITY: does within-game ΔP+ track actual Δ(outcome)?")
    print("=" * 74)
    print("  (ΔP+ < 0 = P+ fell; Δrv > 0 = pitcher run value worse; Δxw > 0 = xwOBA worse)")
    print("  Expect NEGATIVE corr: P+ down <-> outcome worse.\n")
    print(f"  {'pass':>4s} {'n':>5s} {'corr(ΔP+,Δrv)':>15s} {'spear':>7s} {'corr(ΔP+,Δxw)':>15s} {'spear':>7s}")
    for pnum in sorted(deltas["pass"].unique().to_list()):
        d = deltas.filter(pl.col("pass") == pnum)
        dp, drv, dxw = d["d_pplus"].to_list(), d["d_rv"].to_list(), d["d_xw"].to_list()
        print(f"  {pnum:4d} {len(dp):5d} {_corr(dp, drv):15.3f} {_spearman(dp, drv):7.3f} {_corr(dp, dxw):15.3f} {_spearman(dp, dxw):7.3f}")

    # concordance: among the biggest P+ drops (bottom decile ΔP+), how many are in the
    # worse-outcome half (top-half Δrv)? vs a random 50% baseline.
    print("\n  concordance — of the worst-decile ΔP+ cells, share also in the worse-outcome half of Δrv:")
    for pnum in sorted(deltas["pass"].unique().to_list()):
        d = deltas.filter(pl.col("pass") == pnum)
        if d.height < 20:
            continue
        thr_p = d["d_pplus"].quantile(0.10)
        thr_rv = d["d_rv"].median()
        worst = d.filter(pl.col("d_pplus") <= thr_p)
        share = worst.filter(pl.col("d_rv") > thr_rv).height / max(worst.height, 1)
        print(f"    pass {pnum}: {share:5.1%}  (n={worst.height};  50% = no signal, >50% = ΔP+ predicts worse outcomes)")

    # ══ PROBE B ══ censoring / survivor bias
    print("\n" + "=" * 74)
    print("PROBE B — CENSORING: is the deep-pass sample outcome-selected?")
    print("=" * 74)
    per_b = per.join(appmax, on=["pitcher", "game_pk"], how="inner")
    n_app = appmax.height
    reach = appmax.group_by("max_pass").len().sort("max_pass")
    print(f"\n  {n_app:,} SP appearances. Max pass reached:")
    for row in reach.iter_rows(named=True):
        print(f"    pass {row['max_pass']}: {row['len']:6d}  ({100*row['len']/n_app:5.1f}%)")

    print("\n  pass-2/3 outcomes: appearances PULLED at that pass vs. those that CONTINUED deeper")
    print(f"  {'pass':>4s} {'group':>10s} {'appics':>7s} {'mean rv':>9s} {'mean xw':>9s}")
    for pnum in (2, 3):
        at = per_b.filter(pl.col("pass") == pnum)
        pulled = at.filter(pl.col("max_pass") == pnum)      # this pass was their last
        cont = at.filter(pl.col("max_pass") > pnum)          # went deeper
        for name, grp in (("pulled", pulled), ("continued", cont)):
            if grp.height:
                print(f"  {pnum:4d} {name:>10s} {grp.height:7d} {grp['rv'].mean():9.4f} {grp['xw'].mean():9.4f}")

    # fraction of the worst pass-2/3 damage that lives in appearances that never reach pass 4
    p23 = per_b.filter(pl.col("pass").is_in([2, 3]))
    thr = p23["rv"].quantile(0.90)  # worst-decile pass-2/3 damage
    worst = p23.filter(pl.col("rv") >= thr)
    never_deep = worst.filter(pl.col("max_pass") < 4).height / max(worst.height, 1)
    print(f"\n  worst-decile pass-2/3 run-value damage: {never_deep:.1%} occurs in appearances pulled before pass 4")
    print("  (high = the deep-pass detector never sees the worst late damage -> survivor bias on pass-4 findings)")


if __name__ == "__main__":
    main()
