"""Operating-envelope harness for the game-shape deviation gate (diagnostic).

Characterizes where the TTO deviation gate succeeds vs. falls apart across the
league SP population, against `var/tto_baseline.parquet`. Ground-truth-free
Tier-1 probes:

  Probe 1 (coverage): per-pitcher bucket -> not-evaluated / evaluated-silent /
      material, plus the max evaluable pass reached.
  Probe 2 (z-distribution): robust-z percentiles per (pass, metric) and the
      fatigue / stamina / typical split at the default gates.
  Probe 3 (threshold sweep): fired-pitcher count over a grid of
      (Z_GATE_FATIGUE, Z_GATE_STAMINA), P+ veto applied.
  Probe 4 (min_pitches sweep): as the per-pass sample floor rises, does the
      material rate collapse toward the stable-starter rate (i.e. the excess was
      small-sample noise), and is DEEP (pass-4) signal retained while SHALLOW
      (pass-2/3-only) firing dies? Also the pitch-count distribution of fired
      cells, to locate the noise.

One expensive pass (per-pitcher compute_tto_analysis) collects EVERY evaluable
cell (no min_pitches filter; baseline-n floor only) with its pitch count; all
probes derive from that collection.

Run (needs the built artifact -- `python -m pitcher_narratives.tto_baseline` first):
  PITCHER_NARRATIVES_DATA_DIR=/path uv run python scripts/tto_operating_envelope.py [--limit N] [--window W] [--min-pitches M]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict

import polars as pl

from pitcher_narratives.data import (
    classify_game_roles,
    load_all_statcast,
    load_pitcher_data,
    load_tto_baseline,
)
from pitcher_narratives.engine.deviation import (
    Z_GATE_FATIGUE,
    Z_GATE_STAMINA,
    evaluate_deviation,
)
from pitcher_narratives.engine.tto import compute_tto_analysis

_METRICS = (("velo", "avg_velo"), ("pplus", "avg_p_plus"))
_MIN_BASELINE_N = 100
# cell tuple indices: (pass_num, metric, actual_delta, median, mad, z, pitches)
_PASS, _METRIC, _DELTA, _MED, _MAD, _Z, _PITCHES = range(7)


def _sp_ids(limit: int) -> list[int]:
    """League SP pitcher ids, most SP appearances first (workhorses lead)."""
    roles = classify_game_roles(load_all_statcast())
    counts = (
        roles.filter(pl.col("role") == "SP")
        .group_by("pitcher")
        .len()
        .sort("len", descending=True)
    )
    ids = [int(x) for x in counts["pitcher"].to_list()]
    return ids[:limit] if limit else ids


def _cells(tto, baseline_map: dict) -> list[tuple]:
    """EVERY pass>=2 cell for one pitcher whose baseline cell clears the sample
    floor (no per-pitcher min_pitches filter -- that is applied downstream so it
    can be swept). Empty when the pitcher is not evaluable at all."""
    if not tto.available:
        return []
    by_pass = {s.pass_number: s for s in tto.splits}
    p1 = by_pass.get(1)
    if p1 is None or p1.avg_velo is None or p1.avg_p_plus is None:
        return []
    out: list[tuple] = []
    for pnum, s in sorted(by_pass.items()):
        if pnum < 2:
            continue
        for metric, attr in _METRICS:
            actual = getattr(s, attr)
            ref = getattr(p1, attr)
            if actual is None or ref is None:
                continue
            cell = baseline_map.get((pnum, metric))
            if cell is None:
                continue
            median, mad, n = cell
            if n < _MIN_BASELINE_N:
                continue
            d = evaluate_deviation(actual - ref, median, mad)
            out.append((pnum, metric, actual - ref, median, mad, d.robust_z, s.pitches))
    return out


def _floor(cells: list[tuple], min_pitches: int) -> list[tuple]:
    return [c for c in cells if c[_PITCHES] >= min_pitches]


def _fire(cells: list[tuple], zf: float, zs: float) -> list[tuple]:
    """Gate + P+ veto at thresholds (zf, zs). Returns fired (pass, metric, direction)."""
    material: dict[tuple, str] = {}
    for c in cells:
        d = evaluate_deviation(c[_DELTA], c[_MED], c[_MAD], z_gate_fatigue=zf, z_gate_stamina=zs)
        if d.material:
            material[(c[_PASS], c[_METRIC])] = d.direction
    fired: list[tuple] = []
    for (pnum, metric), direction in material.items():
        if metric == "velo" and direction == "fatigue" and material.get((pnum, "pplus")) != "fatigue":
            continue  # P+ veto
        fired.append((pnum, metric, direction))
    return fired


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[i]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=150, help="max SP pitchers to sample (0 = all)")
    ap.add_argument("--window", type=int, default=10, help="recent-appearance window per pitcher")
    ap.add_argument("--min-pitches", type=int, default=15, help="base per-pass pitch floor for probes 1-3")
    args = ap.parse_args()
    base_mp = args.min_pitches

    baseline = load_tto_baseline()
    if baseline is None:
        sys.exit("No tto_baseline.parquet. Run `python -m pitcher_narratives.tto_baseline` first.")
    baseline_map = {
        (r["pass_num"], r["metric"]): (r["median_exp_delta"], r["mad"], r["n"])
        for r in baseline.to_dicts()
        if r["cohort_key"] == "LEAGUE_SP"
    }

    ids = _sp_ids(args.limit)
    print(f"Sampling {len(ids)} SP pitchers (window={args.window}, base min_pitches={base_mp})...", file=sys.stderr)

    all_cells: dict[int, list[tuple]] = {}  # ALL evaluable cells (unfloored)
    n_err = 0
    for k, pid in enumerate(ids):
        try:
            data = load_pitcher_data(pid, recent_appearances=args.window)
            all_cells[pid] = _cells(compute_tto_analysis(data), baseline_map)
        except Exception:
            n_err += 1
            continue
        if (k + 1) % 50 == 0:
            print(f"  ...{k + 1}/{len(ids)}", file=sys.stderr)

    # base-floor view for probes 1-3
    based: dict[int, list[tuple]] = {pid: _floor(c, base_mp) for pid, c in all_cells.items()}
    n = len(based)

    coverage = Counter()
    reached = Counter()
    z_by_cell: dict[tuple, list[float]] = defaultdict(list)
    for cells in based.values():
        if not cells:
            coverage["not_evaluated"] += 1
            reached[0] += 1
            continue
        reached[max(c[_PASS] for c in cells)] += 1
        for c in cells:
            z_by_cell[(c[_PASS], c[_METRIC])].append(c[_Z])
        coverage["material" if _fire(cells, Z_GATE_FATIGUE, Z_GATE_STAMINA) else "evaluated_silent"] += 1

    print("\n" + "=" * 72)
    print(f"TTO DEVIATION GATE — OPERATING ENVELOPE  (n={n}, {n_err} errors, base min_pitches={base_mp})")
    print("=" * 72)

    print("\n[1] COVERAGE")
    for b in ("not_evaluated", "evaluated_silent", "material"):
        print(f"    {b:18s} {coverage[b]:4d}  ({100 * coverage[b] / n:5.1f}%)")
    print("    max evaluable pass reached:")
    for p in sorted(reached):
        label = "none (silent by construction)" if p == 0 else f"pass {p}"
        print(f"        {label:32s} {reached[p]:4d}  ({100 * reached[p] / n:5.1f}%)")

    print(f"\n[2] Z-DISTRIBUTION per (pass, metric)   [gates {Z_GATE_FATIGUE}/{Z_GATE_STAMINA}, min_pitches={base_mp}]")
    print(f"    {'cell':12s} {'count':>6s} {'p10':>7s} {'p50':>7s} {'p90':>7s} {'fatig':>6s} {'stam':>6s} {'typ':>6s}")
    for cell in sorted(z_by_cell):
        zs = z_by_cell[cell]
        fat = sum(1 for z in zs if z <= Z_GATE_FATIGUE)
        stam = sum(1 for z in zs if z >= Z_GATE_STAMINA)
        print(f"    p{cell[0]}/{cell[1]:8s} {len(zs):6d} {_pct(zs,10):7.2f} {_pct(zs,50):7.2f} {_pct(zs,90):7.2f} {fat:6d} {stam:6d} {len(zs)-fat-stam:6d}")

    print("\n[3] THRESHOLD SWEEP — pitchers with >=1 fired finding (P+ veto)")
    stamina_grid = [1.0, 1.5, 2.0, 2.5]
    print("    zf\\zs " + "".join(f"{zs:>8.1f}" for zs in stamina_grid))
    for zf in [-1.5, -2.0, -2.5, -3.0]:
        row = f"    {zf:6.1f} "
        for zs in stamina_grid:
            row += f"{sum(1 for c in based.values() if c and _fire(c, zf, zs)):8d}"
        print(row)

    # ── Probe 4: min_pitches sweep (deep vs shallow retention) ────────
    print("\n[4] MIN_PITCHES SWEEP — at default gates, over ALL evaluable pitchers")
    print(f"    {'min_pitches':>11s} {'evaluable':>9s} {'material':>8s} {'rate':>6s} {'deep(p4)':>8s} {'shallow':>8s}")
    for mp in [15, 25, 40, 60, 80]:
        floored = {pid: _floor(c, mp) for pid, c in all_cells.items()}
        evaluable = sum(1 for c in floored.values() if c)
        mat = deep = shallow = 0
        for cells in floored.values():
            if not cells:
                continue
            fired = _fire(cells, Z_GATE_FATIGUE, Z_GATE_STAMINA)
            if not fired:
                continue
            mat += 1
            if any(f[0] >= 4 for f in fired):
                deep += 1
            else:
                shallow += 1
        rate = f"{100 * mat / evaluable:4.1f}%" if evaluable else "  n/a"
        print(f"    {mp:11d} {evaluable:9d} {mat:8d} {rate:>6s} {deep:8d} {shallow:8d}")

    # pitch-count distribution of FIRED cells at the base floor (locate the noise)
    print(f"\n    fired-cell pitch-count distribution (base min_pitches={base_mp}, default gates):")
    buckets = Counter()
    for cells in based.values():
        fired = {(f[0], f[1]) for f in _fire(cells, Z_GATE_FATIGUE, Z_GATE_STAMINA)}
        for c in cells:
            if (c[_PASS], c[_METRIC]) in fired:
                pk = c[_PITCHES]
                b = "15-24" if pk < 25 else "25-39" if pk < 40 else "40-59" if pk < 60 else "60+"
                buckets[b] += 1
    total = sum(buckets.values()) or 1
    for b in ("15-24", "25-39", "40-59", "60+"):
        print(f"        {b:8s} {buckets[b]:5d}  ({100 * buckets[b] / total:5.1f}% of fired cells)")


if __name__ == "__main__":
    main()
