"""Times-through-order analysis: per-pass pitch mix, fastball/secondary
P+ degradation, velocity decay, and platoon splits across passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _FASTBALL_TYPES,
    _PPLUS_THRESHOLD,
    _pplus_delta_string,
    _velo_delta_string,
)
from pitcher_narratives.engine.deviation import evaluate_deviation

# ── Times Through Order ───────────────────────────────────────────────


_TTO_SMALL_SAMPLE = 50
"""Pitches below which a TTO pass gets a small-sample caveat."""


@dataclass
class TTOPitchType:
    """Per-pitch-type breakdown within a TTO pass."""

    pitch_type: str
    pitches: int
    usage_pct: float
    """Usage percentage within this pass."""
    usage_delta: str
    """Delta vs this type's pass-1 usage (e.g., '+12.0pp')."""
    avg_p_plus: float | None
    p_plus_delta: str
    """Delta vs this type's pass-1 P+ (e.g., 'Down 8 points')."""


@dataclass
class TTOPlatoonSplit:
    """Per-pitch-type breakdown within a TTO pass for one platoon side."""

    pitch_type: str
    stand: str
    """Batter handedness: 'L' or 'R'."""
    pitches: int
    usage_pct: float
    avg_p_plus: float | None


@dataclass
class TTOSplit:
    """Metrics for a single pass through the order."""

    pass_number: int
    """1 = first time through, 2 = second, 3 = third+."""
    pitches: int
    avg_velo: float | None
    avg_p_plus: float | None
    avg_s_plus: float | None
    fb_p_plus: float | None
    """Fastball-only P+ for this pass (FF/SI/FC)."""
    sec_p_plus: float | None
    """Secondary-only P+ for this pass (non-fastball)."""
    velo_delta: str
    """Delta vs first pass (e.g., 'Down 1.8 mph')."""
    p_plus_delta: str
    """Delta vs first pass."""
    fb_p_plus_delta: str
    """Fastball P+ delta vs first pass."""
    sec_p_plus_delta: str
    """Secondary P+ delta vs first pass."""
    pitch_types: list[TTOPitchType]
    """Per-pitch-type breakdown within this pass."""
    platoon: list[TTOPlatoonSplit]
    """Per-pitch-type per-platoon breakdown within this pass."""
    small_sample: bool
    """True if < _TTO_SMALL_SAMPLE pitches."""


@dataclass
class TTOAnalysis:
    """Times-through-order breakdown for starters."""

    splits: list[TTOSplit]
    available: bool
    """False if pitcher never faces TTO 2+."""
    summary: str
    """Qualitative summary (e.g., 'FB P+ drops 14 pts; CH abandoned vs RHB by pass 3')."""
    mix_shifts: list[str]
    """Notable pitch mix changes across passes (e.g., 'SI drops 35% → 9% by pass 3')."""


def compute_tto_analysis(data: PitcherData) -> TTOAnalysis:
    """Compute times-through-order P+ and velocity degradation.

    Joins Statcast (has n_thruorder_pitcher, pitch_type) with all_pitches
    CSV (has P+/S+) to compute per-pass metrics with fastball/secondary
    split and per-pitch-type breakdown. Only uses window appearances.

    Args:
        data: PitcherData bundle.

    Returns:
        TTOAnalysis with per-pass splits, pitch-type breakdowns, and summary.
    """
    statcast = data.statcast
    all_pitches = data.agg_csvs.get("all_pitches")

    if all_pitches is None or all_pitches.is_empty():
        return TTOAnalysis(splits=[], available=False, summary="No pitch-level data", mix_shifts=[])

    # Filter statcast to window games only
    window_game_pks = data.window_appearances["game_pk"].unique().to_list()
    sc_window = statcast.filter(pl.col("game_pk").is_in(window_game_pks))

    if sc_window.is_empty():
        return TTOAnalysis(splits=[], available=False, summary="No window appearances", mix_shifts=[])

    # Join statcast (n_thruorder_pitcher, pitch_type, stand) with all_pitches (P+, S+)
    sc_cols = sc_window.select(
        "pitcher",
        "game_pk",
        "pitch_number",
        "n_thruorder_pitcher",
        "release_speed",
        "pitch_type",
        "stand",
    )
    ap_cols = all_pitches.select("pitcher", "game_pk", "pitch_number", "P+", "S+")

    joined = sc_cols.join(ap_cols, on=["pitcher", "game_pk", "pitch_number"], how="inner")
    joined = joined.filter(pl.col("pitch_type") != "")

    if joined.is_empty():
        return TTOAnalysis(splits=[], available=False, summary="No matched pitch data", mix_shifts=[])

    # Tag fastball vs secondary
    joined = joined.with_columns(pl.col("pitch_type").is_in(list(_FASTBALL_TYPES)).alias("is_fastball"))

    # ── Overall aggregation by TTO pass ──
    tto_overall = (
        joined.group_by("n_thruorder_pitcher")
        .agg(
            pl.col("release_speed").mean().alias("avg_velo"),
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.col("S+").mean().alias("avg_s_plus"),
            pl.len().alias("pitches"),
        )
        .sort("n_thruorder_pitcher")
    )

    # ── Fastball / secondary split by TTO pass ──
    fb_sec = (
        joined.group_by(["n_thruorder_pitcher", "is_fastball"])
        .agg(
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.len().alias("pitches"),
        )
        .sort(["n_thruorder_pitcher", "is_fastball"])
    )

    # ── Per pitch-type breakdown by TTO pass (with counts for usage %) ──
    pitch_type_breakdown = (
        joined.group_by(["n_thruorder_pitcher", "pitch_type"])
        .agg(
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.len().alias("pitches"),
        )
        .sort(["n_thruorder_pitcher", "pitch_type"])
    )

    # ── Platoon breakdown by TTO pass ──
    platoon_breakdown = (
        joined.group_by(["n_thruorder_pitcher", "stand", "pitch_type"])
        .agg(
            pl.col("P+").mean().alias("avg_p_plus"),
            pl.len().alias("pitches"),
        )
        .sort(["n_thruorder_pitcher", "stand", "pitch_type"])
    )

    overall_rows = tto_overall.to_dicts()
    if len(overall_rows) < 2:
        return TTOAnalysis(
            splits=[],
            available=False,
            summary="Only faced batters once per game (no TTO comparison)",
            mix_shifts=[],
        )

    # Helper: extract fb/sec P+ for a pass
    def _get_fb_sec(pass_num: int) -> tuple[float | None, float | None]:
        fb_rows = fb_sec.filter((pl.col("n_thruorder_pitcher") == pass_num) & pl.col("is_fastball"))
        sec_rows = fb_sec.filter((pl.col("n_thruorder_pitcher") == pass_num) & ~pl.col("is_fastball"))
        fb_val = fb_rows["avg_p_plus"][0] if fb_rows.height > 0 else None
        sec_val = sec_rows["avg_p_plus"][0] if sec_rows.height > 0 else None
        return fb_val, sec_val

    # Helper: extract pitch-type breakdown for a pass
    def _get_pitch_types(pass_num: int, total_pitches: int) -> list[dict[str, Any]]:
        rows = pitch_type_breakdown.filter(pl.col("n_thruorder_pitcher") == pass_num).sort(
            "pitches", descending=True
        )
        result = rows.to_dicts()
        for r in result:
            r["usage_pct"] = (r["pitches"] / total_pitches * 100) if total_pitches > 0 else 0.0
        return result

    # Helper: extract platoon splits for a pass
    def _get_platoon(pass_num: int) -> list[TTOPlatoonSplit]:
        rows = platoon_breakdown.filter(pl.col("n_thruorder_pitcher") == pass_num)
        if rows.is_empty():
            return []
        # Compute per-stand totals for usage %
        stand_totals: dict[str, int] = {}
        for r in rows.to_dicts():
            stand_totals[r["stand"]] = stand_totals.get(r["stand"], 0) + r["pitches"]
        entries: list[TTOPlatoonSplit] = []
        for r in rows.sort("pitches", descending=True).to_dicts():
            total = stand_totals.get(r["stand"], 1)
            entries.append(
                TTOPlatoonSplit(
                    pitch_type=r["pitch_type"],
                    stand=r["stand"],
                    pitches=r["pitches"],
                    usage_pct=r["pitches"] / total * 100,
                    avg_p_plus=r["avg_p_plus"],
                )
            )
        return entries

    # Get pass-1 baselines for deltas
    first = overall_rows[0]
    first_fb, first_sec = _get_fb_sec(first["n_thruorder_pitcher"])

    # Get pass-1 per-type baselines (P+ and usage)
    first_by_type: dict[str, dict[str, Any]] = {}
    for pt in _get_pitch_types(first["n_thruorder_pitcher"], first["pitches"]):
        first_by_type[pt["pitch_type"]] = {
            "avg_p_plus": pt["avg_p_plus"],
            "usage_pct": pt["usage_pct"],
        }

    # Build splits
    splits: list[TTOSplit] = []
    for row in overall_rows:
        pass_num = row["n_thruorder_pitcher"]
        velo = row["avg_velo"]
        p_plus = row["avg_p_plus"]
        s_plus = row["avg_s_plus"]
        total_pitches = row["pitches"]
        fb_pp, sec_pp = _get_fb_sec(pass_num)

        if pass_num == first["n_thruorder_pitcher"]:
            vdelta = "--"
            pdelta = "--"
            fb_delta = "--"
            sec_delta = "--"
        else:
            vdelta = (
                _velo_delta_string(velo - first["avg_velo"])
                if velo is not None and first["avg_velo"] is not None
                else "--"
            )
            pdelta = (
                _pplus_delta_string(p_plus - first["avg_p_plus"])
                if p_plus is not None and first["avg_p_plus"] is not None
                else "--"
            )
            fb_delta = (
                _pplus_delta_string(fb_pp - first_fb) if fb_pp is not None and first_fb is not None else "--"
            )
            sec_delta = (
                _pplus_delta_string(sec_pp - first_sec)
                if sec_pp is not None and first_sec is not None
                else "--"
            )

        # Per-pitch-type breakdown with usage % and deltas
        pt_entries: list[TTOPitchType] = []
        for pt in _get_pitch_types(pass_num, total_pitches):
            pt_type = pt["pitch_type"]
            pt_pp = pt["avg_p_plus"]
            pt_usage = pt["usage_pct"]

            if pass_num == first["n_thruorder_pitcher"]:
                pt_p_delta = "--"
                pt_u_delta = "--"
            else:
                # P+ delta
                if pt_type in first_by_type and pt_pp is not None:
                    pt_p_delta = _pplus_delta_string(pt_pp - first_by_type[pt_type]["avg_p_plus"])
                else:
                    pt_p_delta = "New"
                # Usage delta
                if pt_type in first_by_type:
                    u_diff = pt_usage - first_by_type[pt_type]["usage_pct"]
                    pt_u_delta = f"{u_diff:+.1f}pp"
                else:
                    pt_u_delta = "New"

            pt_entries.append(
                TTOPitchType(
                    pitch_type=pt_type,
                    pitches=pt["pitches"],
                    usage_pct=pt_usage,
                    usage_delta=pt_u_delta,
                    avg_p_plus=pt_pp,
                    p_plus_delta=pt_p_delta,
                )
            )

        # Platoon splits for this pass
        platoon_entries = _get_platoon(pass_num)

        splits.append(
            TTOSplit(
                pass_number=pass_num,
                pitches=total_pitches,
                avg_velo=velo,
                avg_p_plus=p_plus,
                avg_s_plus=s_plus,
                fb_p_plus=fb_pp,
                sec_p_plus=sec_pp,
                velo_delta=vdelta,
                p_plus_delta=pdelta,
                fb_p_plus_delta=fb_delta,
                sec_p_plus_delta=sec_delta,
                pitch_types=pt_entries,
                platoon=platoon_entries,
                small_sample=total_pitches < _TTO_SMALL_SAMPLE,
            )
        )

    # ── Detect notable mix shifts ──
    mix_shifts: list[str] = []
    last = splits[-1]
    for entry in last.pitch_types:
        if entry.pitch_type in first_by_type:
            first_usage = first_by_type[entry.pitch_type]["usage_pct"]
            diff = entry.usage_pct - first_usage
            if abs(diff) >= 10.0:
                mix_shifts.append(
                    f"{entry.pitch_type} {first_usage:.0f}% → "
                    f"{entry.usage_pct:.0f}% by pass {last.pass_number}"
                )
        else:
            if entry.pitches >= 5:
                mix_shifts.append(
                    f"{entry.pitch_type} introduced in pass {last.pass_number} ({entry.usage_pct:.0f}%)"
                )
    # Detect pitches dropped in later passes
    for pt_type, baseline in first_by_type.items():
        if baseline["usage_pct"] >= 10.0:
            found = any(p.pitch_type == pt_type for p in last.pitch_types)
            if not found:
                mix_shifts.append(
                    f"{pt_type} abandoned by pass {last.pass_number} (was {baseline['usage_pct']:.0f}%)"
                )

    # Build summary — lead with fastball P+ degradation signal
    summary_parts: list[str] = []
    if first_fb and splits[-1].fb_p_plus:
        fb_drop = first_fb - splits[-1].fb_p_plus
        if abs(fb_drop) >= _PPLUS_THRESHOLD:
            summary_parts.append(f"Fastball P+ drops {fb_drop:.0f} points by pass {splits[-1].pass_number}")
        else:
            summary_parts.append(f"Fastball P+ holds through {len(splits)} passes ({fb_drop:+.0f})")

    if first_sec and splits[-1].sec_p_plus:
        sec_drop = first_sec - splits[-1].sec_p_plus
        if abs(sec_drop) >= _PPLUS_THRESHOLD:
            summary_parts.append(f"Secondary P+ drops {sec_drop:.0f} points")
        else:
            summary_parts.append(f"Secondary P+ holds ({sec_drop:+.0f})")

    if mix_shifts:
        summary_parts.append(f"{len(mix_shifts)} mix shift(s)")

    if splits[-1].small_sample:
        summary_parts.append(f"small sample in pass {splits[-1].pass_number} ({splits[-1].pitches} pitches)")

    summary = "; ".join(summary_parts) if summary_parts else f"{len(splits)} passes through the order"

    return TTOAnalysis(splits=splits, available=True, summary=summary, mix_shifts=mix_shifts)


# ── Deviation gate (design 2026-07-08-game-shape-deviation-gate) ──────


@dataclass(frozen=True)
class TTODeviation:
    """A material within-game deviation of one metric at one pass vs. the
    league-SP baseline."""

    pass_num: int
    metric: str  # "velo" | "pplus"
    actual_delta: float
    median_exp_delta: float
    robust_z: float
    direction: str  # "fatigue" | "stamina"


_MIN_BASELINE_N = 100
"""Floor on the baseline cell's per-appearance sample size (design §3.3
sample-adequacy guard). Pass-2/3 league cells run to the thousands; the real
pass-4 LEAGUE_SP cell has n=471, so 100 keeps pass 4 while dropping truly
thin pass-5+ cells that could manufacture a finding from a volatile MAD."""


def evaluate_tto_deviations(
    tto: "TTOAnalysis",
    baseline: "pl.DataFrame | None",
    *,
    min_pitches: int = 15,
    min_baseline_n: int = _MIN_BASELINE_N,
) -> list["TTODeviation"]:
    """Material within-game deviations vs. the LEAGUE_SP baseline (design §3-4).

    Silence (empty list) when TTO is unavailable, the baseline is absent, or no
    cell is material. Applies the P+-corroboration veto: a negative-material
    ``velo`` deviation is kept (fatigue) only if ``pplus`` is also
    negative-material; a positive-material ``pplus`` surfaces independently
    (resilience); an otherwise-unsupported velo drop is vetoed. Also enforces
    the sample-adequacy guard on both sides of the join (design §3.3): a
    pitcher-side pass with fewer than ``min_pitches`` window pitches, or a
    baseline cell with fewer than ``min_baseline_n`` per-appearance
    observations, is skipped rather than treated as material.
    """
    if not getattr(tto, "available", False) or baseline is None:
        return []
    by_pass = {s.pass_number: s for s in tto.splits}
    p1 = by_pass.get(1)
    if p1 is None or p1.avg_velo is None or p1.avg_p_plus is None:
        return []

    # baseline -> {(pass_num, metric): (median, mad, n)}
    b = {
        (r["pass_num"], r["metric"]): (r["median_exp_delta"], r["mad"], r["n"])
        for r in baseline.to_dicts()
        if r["cohort_key"] == "LEAGUE_SP"
    }

    # First pass: compute a Deviation per (pass>=2, metric) cell.
    raw: dict[tuple[int, str], "TTODeviation"] = {}
    for pass_num, split in sorted(by_pass.items()):
        if pass_num < 2 or split.pitches < min_pitches:
            continue
        for metric, actual, ref in (
            ("velo", split.avg_velo, p1.avg_velo),
            ("pplus", split.avg_p_plus, p1.avg_p_plus),
        ):
            if actual is None:
                continue
            cell = b.get((pass_num, metric))
            if cell is None:
                continue
            median_exp, mad, baseline_n = cell
            if baseline_n < min_baseline_n:
                continue
            d = evaluate_deviation(actual - ref, median_exp, mad)
            if d.material:
                raw[(pass_num, metric)] = TTODeviation(
                    pass_num, metric, actual - ref, median_exp, d.robust_z, d.direction
                )

    # P+ veto: drop a fatigue velo cell unless the same pass's pplus is also
    # negative-material (fatigue). Positive-material pplus stays (resilience).
    out: list["TTODeviation"] = []
    for (pass_num, metric), dev in raw.items():
        if metric == "velo" and dev.direction == "fatigue":
            pplus = raw.get((pass_num, "pplus"))
            if pplus is None or pplus.direction != "fatigue":
                continue  # vetoed
        out.append(dev)
    return sorted(out, key=lambda d: (d.pass_num, d.metric))


