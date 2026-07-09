"""Operating-envelope harness for the game-shape deviation gate (diagnostic).

Characterizes where the TTO deviation gate succeeds vs. falls apart across the
league SP population, against `var/tto_baseline.parquet`. Tier-1 probes (no
ground truth required) from the game-shape v2-scoping analysis:

  Probe 1 (coverage): per-pitcher bucket -> not-evaluated / evaluated-silent /
      material, plus the max evaluable pass reached.
  Probe 2 (z-distribution): robust-z percentiles per (pass, metric) and the
      fatigue / stamina / typical split at the default gates.
  Probe 3 (threshold sweep): fired-pitcher count over a grid of
      (Z_GATE_FATIGUE, Z_GATE_STAMINA), with the P+ veto applied -- looking for
      a stable, selective plateau vs. a flood/zero regime.

One expensive pass (per-pitcher compute_tto_analysis) collects every evaluable
cell's z; all three probes derive from that collection.

Run (needs the built artifact -- `python -m pitcher_narratives.tto_baseline` first):
  PITCHER_NARRATIVES_DATA_DIR=/path uv run python scripts/tto_operating_envelope.py [--limit N] [--window W]
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
_MIN_PITCHES = 15
_MIN_BASELINE_N = 100


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
    """Every evaluable (pass>=2, metric) cell for one pitcher.

    Returns (pass_num, metric, actual_delta, median, mad, z). Empty when the
    pitcher is not evaluable at all (TTO unavailable / no pass 1 / all cells
    below the pitcher or baseline sample floors).
    """
    if not tto.available:
        return []
    by_pass = {s.pass_number: s for s in tto.splits}
    p1 = by_pass.get(1)
    if p1 is None or p1.avg_velo is None or p1.avg_p_plus is None:
        return []
    out: list[tuple] = []
    for pnum, s in sorted(by_pass.items()):
        if pnum < 2 or s.pitches < _MIN_PITCHES:
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
            out.append((pnum, metric, actual - ref, median, mad, d.robust_z))
    return out


def _fire(cells: list[tuple], zf: float, zs: float) -> list[tuple]:
    """Gate + P+ veto at thresholds (zf, zs). Returns fired (pass, metric, direction)."""
    material: dict[tuple, str] = {}
    for pnum, metric, delta, median, mad, _z in cells:
        d = evaluate_deviation(delta, median, mad, z_gate_fatigue=zf, z_gate_stamina=zs)
        if d.material:
            material[(pnum, metric)] = d.direction
    fired: list[tuple] = []
    for (pnum, metric), direction in material.items():
        if metric == "velo" and direction == "fatigue":
            if material.get((pnum, "pplus")) != "fatigue":
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
    args = ap.parse_args()

    baseline = load_tto_baseline()
    if baseline is None:
        sys.exit("No tto_baseline.parquet. Run `python -m pitcher_narratives.tto_baseline` first.")
    baseline_map = {
        (r["pass_num"], r["metric"]): (r["median_exp_delta"], r["mad"], r["n"])
        for r in baseline.to_dicts()
        if r["cohort_key"] == "LEAGUE_SP"
    }

    ids = _sp_ids(args.limit)
    print(f"Sampling {len(ids)} SP pitchers (window={args.window})...", file=sys.stderr)

    per_pitcher_cells: dict[int, list[tuple]] = {}
    z_by_cell: dict[tuple, list[float]] = defaultdict(list)
    coverage = Counter()
    reached = Counter()  # max evaluable pass -> count
    n_err = 0

    for k, pid in enumerate(ids):
        try:
            data = load_pitcher_data(pid, recent_appearances=args.window)
            cells = _cells(compute_tto_analysis(data), baseline_map)
        except Exception:
            n_err += 1
            continue
        per_pitcher_cells[pid] = cells
        if not cells:
            coverage["not_evaluated"] += 1
            reached[0] += 1
            continue
        reached[max(c[0] for c in cells)] += 1
        for pnum, metric, _d, _m, _mad, z in cells:
            z_by_cell[(pnum, metric)].append(z)
        coverage["material" if _fire(cells, Z_GATE_FATIGUE, Z_GATE_STAMINA) else "evaluated_silent"] += 1
        if (k + 1) % 25 == 0:
            print(f"  ...{k + 1}/{len(ids)}", file=sys.stderr)

    n = sum(coverage.values())
    print("\n" + "=" * 70)
    print(f"TTO DEVIATION GATE — OPERATING ENVELOPE  (n={n} evaluated, {n_err} load errors)")
    print("=" * 70)

    # ── Probe 1: coverage ────────────────────────────────────────────
    print("\n[1] COVERAGE")
    for bucket in ("not_evaluated", "evaluated_silent", "material"):
        c = coverage[bucket]
        print(f"    {bucket:18s} {c:4d}  ({100 * c / n:5.1f}%)")
    print("    max evaluable pass reached:")
    for p in sorted(reached):
        label = "none (silent by construction)" if p == 0 else f"pass {p}"
        print(f"        {label:32s} {reached[p]:4d}  ({100 * reached[p] / n:5.1f}%)")

    # ── Probe 2: z-distribution + default-gate split ─────────────────
    print("\n[2] Z-DISTRIBUTION per (pass, metric)   [gates: fatigue<=-2.0, stamina>=1.5]")
    print(f"    {'cell':12s} {'count':>6s} {'p10':>7s} {'p50':>7s} {'p90':>7s} {'fatig':>6s} {'stam':>6s} {'typ':>6s}")
    for cell in sorted(z_by_cell):
        zs = z_by_cell[cell]
        fat = sum(1 for z in zs if z <= Z_GATE_FATIGUE)
        stam = sum(1 for z in zs if z >= Z_GATE_STAMINA)
        typ = len(zs) - fat - stam
        name = f"p{cell[0]}/{cell[1]}"
        print(f"    {name:12s} {len(zs):6d} {_pct(zs,10):7.2f} {_pct(zs,50):7.2f} {_pct(zs,90):7.2f} {fat:6d} {stam:6d} {typ:6d}")

    # ── Probe 3: threshold sweep (fired pitchers, veto applied) ──────
    print("\n[3] THRESHOLD SWEEP — pitchers with >=1 fired finding (P+ veto applied)")
    fatigue_grid = [-1.5, -2.0, -2.5, -3.0]
    stamina_grid = [1.0, 1.5, 2.0, 2.5]
    header = "    zf\\zs " + "".join(f"{zs:>8.1f}" for zs in stamina_grid)
    print(header)
    for zf in fatigue_grid:
        row = f"    {zf:6.1f} "
        for zs in stamina_grid:
            fired = sum(1 for cells in per_pitcher_cells.values() if cells and _fire(cells, zf, zs))
            row += f"{fired:8d}"
        print(row)
    print(f"\n    (default gates {Z_GATE_FATIGUE}/{Z_GATE_STAMINA} -> "
          f"{coverage['material']} material of {n}. Look for a stable plateau vs. a flood/zero regime.)")


if __name__ == "__main__":
    main()
