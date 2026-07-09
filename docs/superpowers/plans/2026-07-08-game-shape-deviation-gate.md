# Game-Shape Deviation Gate (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface within-game (TTO) shape only when a pitcher deviates materially from a precomputed league-SP baseline — a typical fade produces silence — via a pure deviation primitive, an offline baseline artifact, a runtime evaluator with an asymmetric directional gate + P+ veto, and a residual-speaking game-shape prompt.

**Architecture:** Heavy league aggregation happens **offline** (a build script writes `var/tto_baseline.parquet`, long-form `cohort_key/pass_num/metric/median_exp_delta/mad/n`). At report time a cheap evaluator joins this pitcher's per-pass ΔVelo/ΔP+ (already computed by `compute_tto_analysis`) against the baseline, runs the pure `engine/deviation.py` primitive, applies the gate + P+ veto, and feeds the *residual* (or a "typical → stay silent" instruction) into the game-shape specialist input. The `cohort_key` join is hardcoded `LEAGUE_SP` in v1 (the v2 cohort seam).

**Tech Stack:** Python 3.14, polars, pytest, `uv`.

## Global Constraints

- Python 3.14+; run everything via `uv run`. Tests/build needing data set `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives`.
- Data dir layout (from `data.py`): `DATA_DIR = $PITCHER_NARRATIVES_DATA_DIR or repo root`; `AGGS_DIR = DATA_DIR/var/aggs`; statcast at `DATA_DIR/var/statcast/<year>.parquet`. The new baseline artifact lives at **`DATA_DIR/var/tto_baseline.parquet`** — it is *generated data*, NOT committed to git (like statcast/aggs).
- Metric enum strings are exactly `"velo"` and `"pplus"` (the ΔVelo/ΔP+ concepts). Long-form baseline schema: `cohort_key, pass_num, metric, median_exp_delta, mad, n`. `cohort_key == "LEAGUE_SP"` in v1.
- Robust stats only: **median** expected delta + **MAD** (×1.4826); never mean/SD. Robust z `= (actual_delta − median_exp_delta) / (1.4826 · mad)`.
- Gate is per-cell, directional, **asymmetric**: `Z_GATE_FATIGUE = -2.0`, `Z_GATE_STAMINA = +1.5` (empirically calibrated; these are the starting values). Pass 1 (Δ≡0, dispersion 0) is **excluded** from evaluation — never evaluate `residual/0`.
- **P+ veto (truth table, spec §3.3):** negative-material `velo` is narrated as *fatigue* only if `pplus` is also negative-material; if `pplus` is positive-material → surface the resilience story via the `pplus` cell (not vetoed); if `pplus` is typical → veto the velo fatigue finding (silence).
- Success behavior: **typical → the specialist says nothing about game shape.** Degradation (TTO unavailable, baseline missing/absent cell, sub-sample) → no deviation → silence, never a crash, never fall back to the raw fade.
- Spec: `docs/superpowers/specs/2026-07-08-game-shape-deviation-gate-design.md`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/pitcher_narratives/engine/deviation.py` (new) | Pure `evaluate_deviation(...)` primitive + `Deviation` + `Z_GATE_*` constants. The reusable scope-C core. |
| `src/pitcher_narratives/tto_baseline.py` (new) | Offline `build_tto_baseline()` (league aggregation → long-form frame) + `write_tto_baseline()`; runnable as `python -m pitcher_narratives.tto_baseline`. |
| `src/pitcher_narratives/data.py` (modify) | `tto_baseline_path()` + cached `load_tto_baseline()`. |
| `src/pitcher_narratives/engine/tto.py` (modify) | `TTODeviation` + `evaluate_tto_deviations(tto, baseline)` (numeric per-pass deltas, join, primitive, gate + P+ veto). |
| `src/pitcher_narratives/pipeline.py` (modify) | `_build_game_shape_input` renders residuals / typical-silence; `_GAME_SHAPE_SPECIALIST_PROMPT` rewritten to speak residuals. |
| `tests/test_deviation.py`, `tests/test_tto_baseline.py`, `tests/test_tto_deviation.py`, `tests/test_game_shape_input.py` (new) | Per-unit tests. |

---

## Task 1: The pure deviation primitive (`engine/deviation.py`)

**Files:**
- Create: `src/pitcher_narratives/engine/deviation.py`
- Test: `tests/test_deviation.py`

**Interfaces:**
- Produces: `Z_GATE_FATIGUE: float = -2.0`, `Z_GATE_STAMINA: float = 1.5`; `Deviation` dataclass; `evaluate_deviation(actual_delta: float, median_exp_delta: float, mad: float, *, z_gate_fatigue: float = Z_GATE_FATIGUE, z_gate_stamina: float = Z_GATE_STAMINA) -> Deviation`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deviation.py`:

```python
from pitcher_narratives.engine.deviation import (
    Deviation, evaluate_deviation, Z_GATE_FATIGUE, Z_GATE_STAMINA,
)


def test_robust_z_uses_mad_scaling():
    # actual −4.0 vs expected −1.0, mad 1.0 → z = (−3.0)/(1.4826*1.0) ≈ −2.02
    d = evaluate_deviation(-4.0, -1.0, 1.0)
    assert round(d.robust_z, 2) == -2.02
    assert d.direction == "fatigue"
    assert d.material is True  # −2.02 <= −2.0


def test_fatigue_gate_is_conservative():
    # z ≈ −1.9 does NOT trip the −2.0 fatigue gate
    d = evaluate_deviation(-3.8, -1.0, 1.0)  # (−2.8)/1.4826 ≈ −1.89
    assert d.material is False


def test_stamina_gate_is_easier():
    # holds better than expected: actual +0.2 vs expected −3.5, mad 1.5 → z ≈ +1.66
    d = evaluate_deviation(0.2, -3.5, 1.5)
    assert d.direction == "stamina"
    assert d.robust_z > Z_GATE_STAMINA
    assert d.material is True


def test_typical_is_not_material():
    d = evaluate_deviation(-1.2, -1.0, 1.0)  # z ≈ −0.13
    assert d.material is False


def test_zero_mad_is_guarded_not_divide_by_zero():
    # defensive: pass-1 exclusion is upstream, but a degenerate cell must not crash
    d = evaluate_deviation(-2.0, -1.0, 0.0)
    assert d.material is False
    assert d.robust_z == 0.0
```

- [ ] **Step 2: Run — fails (module missing)**

Run: `uv run pytest tests/test_deviation.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `engine/deviation.py`**

```python
"""Pure population-deviation primitive.

The reusable core of the "compare-to-population, report-the-residual"
mechanism (design 2026-07-08-game-shape-deviation-gate). A specialist supplies
an observed delta and a population (median_exp_delta, mad) cell; this returns a
robust, directional, gated Deviation. No I/O, no domain knowledge — the TTO
evaluator (and future specialists) own the join and the framing.
"""

from __future__ import annotations

from dataclasses import dataclass

# Empirically calibrated (design §3.3). Asymmetric: a fatigue (harmful) claim
# must be undeniable; a stamina (beneficial) claim surfaces more readily.
Z_GATE_FATIGUE: float = -2.0
Z_GATE_STAMINA: float = 1.5

_MAD_TO_SIGMA: float = 1.4826


@dataclass(frozen=True)
class Deviation:
    """A robust, directional, gated deviation of one observed delta from a
    population cell."""

    residual: float
    robust_z: float
    direction: str  # "fatigue" (harmful side) | "stamina" (beneficial side)
    material: bool


def evaluate_deviation(
    actual_delta: float,
    median_exp_delta: float,
    mad: float,
    *,
    z_gate_fatigue: float = Z_GATE_FATIGUE,
    z_gate_stamina: float = Z_GATE_STAMINA,
) -> Deviation:
    """Compare an observed delta against a population (median, MAD) cell.

    ``direction`` is "fatigue" when the residual is on the harmful side (the
    metric dropped MORE than the population expected, i.e. residual < 0) and
    "stamina" when it held/improved beyond expectation (residual > 0). The gate
    is asymmetric: a fatigue Deviation is material at ``z <= z_gate_fatigue``; a
    stamina Deviation at ``z >= z_gate_stamina``. A non-positive ``mad`` (a
    degenerate/zero-dispersion cell) yields z=0 and non-material — defensive;
    callers exclude the pass-1 Δ≡0 reference upstream.
    """
    residual = actual_delta - median_exp_delta
    if mad <= 0.0:
        return Deviation(residual=residual, robust_z=0.0, direction="stamina" if residual >= 0 else "fatigue", material=False)
    robust_z = residual / (_MAD_TO_SIGMA * mad)
    if robust_z < 0:
        return Deviation(residual, robust_z, "fatigue", robust_z <= z_gate_fatigue)
    return Deviation(residual, robust_z, "stamina", robust_z >= z_gate_stamina)
```

- [ ] **Step 4: Run — passes**

Run: `uv run pytest tests/test_deviation.py -v`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/engine/deviation.py tests/test_deviation.py
git commit -m "feat(engine): pure population-deviation primitive (robust z + directional gate)"
```

---

## Task 2: Offline league baseline build + artifact + loader

**Files:**
- Create: `src/pitcher_narratives/tto_baseline.py`
- Modify: `src/pitcher_narratives/data.py` (add `tto_baseline_path()` + cached `load_tto_baseline()`)
- Test: `tests/test_tto_baseline.py`

**Interfaces:**
- Consumes: `load_all_statcast()`, `load_csv("all_pitches", None)`, `classify_game_roles(statcast)` (all in `data.py`); the `pass_number` bucketing used by `compute_tto_analysis` (1 / 2 / 3+).
- Produces: `build_tto_baseline(statcast, all_pitches) -> pl.DataFrame` (long-form: `cohort_key, pass_num, metric, median_exp_delta, mad, n`); `write_tto_baseline(df, path)`; `data.tto_baseline_path() -> Path`; `data.load_tto_baseline() -> pl.DataFrame | None` (cached; None if the artifact is absent).

- [ ] **Step 1: Confirm the runtime pass bucketing to match**

Run: `grep -n "pass_number\|n_thruorder\|min(\|clip\|when(pl.col(\"n_thruorder" src/pitcher_narratives/engine/tto.py`
Read how `compute_tto_analysis` maps `n_thruorder_pitcher` → `TTOSplit.pass_number` (1 = first, 2 = second, **3 = third+**). The baseline MUST bucket identically: `pass_num = min(n_thruorder_pitcher, 3)`. Note the exact rule you find; use it verbatim in Step 4.

- [ ] **Step 2: Write the failing build test (synthetic league frame)**

Create `tests/test_tto_baseline.py`. Build a tiny synthetic statcast + all_pitches pair for two SP appearances so the median/MAD are hand-checkable:

```python
import polars as pl
from pitcher_narratives.tto_baseline import build_tto_baseline


def _synthetic():
    # 2 SP appearances (game 1,2), pitcher 100, first inning == 1 (SP).
    # pass1 velo 96, pass2 velo 95 (Δ−1) in game1; pass2 velo 93 (Δ−3) in game2.
    rows = []
    def add(game, pitch_no, tto, velo, pplus, inning):
        rows.append(dict(pitcher=100, game_pk=game, pitch_number=pitch_no,
                         n_thruorder_pitcher=tto, release_speed=velo,
                         pitch_type="FF", stand="R", inning=inning,
                         inning_topbot="Top", at_bat_number=pitch_no, P_plus=pplus))
    # game 1
    add(1, 1, 1, 96.0, 105.0, 1); add(1, 2, 2, 95.0, 101.0, 5)
    # game 2
    add(2, 1, 1, 96.0, 105.0, 1); add(2, 2, 2, 93.0, 97.0, 5)
    sc = pl.DataFrame(rows).select(
        "pitcher","game_pk","pitch_number","n_thruorder_pitcher",
        "release_speed","pitch_type","stand","inning","inning_topbot","at_bat_number")
    ap = pl.DataFrame(rows).select("pitcher","game_pk","pitch_number").with_columns(
        pl.Series("P+", [r["P_plus"] for r in rows]))
    return sc, ap


def test_build_emits_long_form_league_sp_rows():
    sc, ap = _synthetic()
    base = build_tto_baseline(sc, ap)
    assert set(base.columns) == {"cohort_key","pass_num","metric","median_exp_delta","mad","n"}
    assert base["cohort_key"].unique().to_list() == ["LEAGUE_SP"]
    # pass 1 is the Δ≡0 reference and is NOT stored
    assert 1 not in base["pass_num"].to_list()
    velo2 = base.filter((pl.col("pass_num")==2) & (pl.col("metric")=="velo"))
    # per-appearance velo deltas at pass2: −1.0 and −3.0 → median −2.0
    assert round(velo2["median_exp_delta"][0], 3) == -2.0
    assert velo2["n"][0] == 2
    pplus2 = base.filter((pl.col("pass_num")==2) & (pl.col("metric")=="pplus"))
    # pplus deltas: (101−105)=−4, (97−105)=−8 → median −6.0
    assert round(pplus2["median_exp_delta"][0], 3) == -6.0
```

- [ ] **Step 3: Run — fails (module missing)**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_tto_baseline.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 4: Implement `tto_baseline.py`**

```python
"""Offline league-SP within-game (TTO) baseline artifact.

Aggregates the league-wide statcast × all_pitches join into a long-form table
of expected per-pass decay (median + MAD of the per-appearance passN−pass1
delta) for velo and P+. Written once to var/tto_baseline.parquet and loaded at
report time by the deviation evaluator. Never computed on the hot path.

Run: `python -m pitcher_narratives.tto_baseline`
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from pitcher_narratives.data import (
    classify_game_roles, load_all_statcast, load_csv, tto_baseline_path,
)

_METRICS = {"velo": "release_speed", "pplus": "P+"}


def build_tto_baseline(statcast: pl.DataFrame, all_pitches: pl.DataFrame) -> pl.DataFrame:
    """Long-form LEAGUE_SP baseline: median + MAD of per-appearance passN−pass1
    delta, per (pass_num, metric)."""
    roles = classify_game_roles(statcast)  # (game_pk, pitcher, role)
    sp = roles.filter(pl.col("role") == "SP").select("game_pk", "pitcher")

    joined = (
        statcast.select("pitcher", "game_pk", "pitch_number", "n_thruorder_pitcher", "release_speed", "pitch_type")
        .filter(pl.col("pitch_type") != "")
        .join(all_pitches.select("pitcher", "game_pk", "pitch_number", "P+"),
              on=["pitcher", "game_pk", "pitch_number"], how="inner")
        .join(sp, on=["game_pk", "pitcher"], how="inner")
        # Bucket to match TTOSplit.pass_number semantics (1 / 2 / 3+). Use the
        # exact rule confirmed in Step 1:
        .with_columns(pl.min_horizontal(pl.col("n_thruorder_pitcher"), pl.lit(3)).alias("pass_num"))
    )

    # Per (appearance, pass) mean metric, then delta vs that appearance's pass 1.
    per_pass = joined.group_by("pitcher", "game_pk", "pass_num").agg(
        pl.col("release_speed").mean().alias("velo"),
        pl.col("P+").mean().alias("pplus"),
    )
    pass1 = per_pass.filter(pl.col("pass_num") == 1).select(
        "pitcher", "game_pk", pl.col("velo").alias("velo_p1"), pl.col("pplus").alias("pplus_p1"))
    deltas = (
        per_pass.filter(pl.col("pass_num") >= 2)
        .join(pass1, on=["pitcher", "game_pk"], how="inner")
        .with_columns((pl.col("velo") - pl.col("velo_p1")).alias("d_velo"),
                      (pl.col("pplus") - pl.col("pplus_p1")).alias("d_pplus"))
    )

    out = []
    for metric, dcol in (("velo", "d_velo"), ("pplus", "d_pplus")):
        agg = (
            deltas.group_by("pass_num")
            .agg(pl.col(dcol).median().alias("median_exp_delta"),
                 (pl.col(dcol) - pl.col(dcol).median()).abs().median().alias("mad"),
                 pl.len().alias("n"))
        )
        out.append(agg.with_columns(pl.lit("LEAGUE_SP").alias("cohort_key"),
                                    pl.lit(metric).alias("metric"))
                   .select("cohort_key", "pass_num", "metric", "median_exp_delta", "mad", "n"))
    return pl.concat(out).sort("pass_num", "metric")


def write_tto_baseline(df: pl.DataFrame, path: Path | None = None) -> Path:
    path = path or tto_baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def main() -> None:
    statcast = load_all_statcast()
    all_pitches = load_csv("all_pitches", None)
    df = build_tto_baseline(statcast, all_pitches)
    out = write_tto_baseline(df)
    print(f"wrote {out} ({df.height} rows)")


if __name__ == "__main__":
    main()
```

> Note: the MAD here is `median(|x − median(x)|)`. If polars lacks a one-call MAD, the two-step expression above is correct. Verify `load_all_statcast` and `classify_game_roles` column names against `data.py` before running (Step 1 confirmed `classify_game_roles` returns `game_pk, pitcher, role`).

- [ ] **Step 5: Add the path + cached loader to `data.py`**

```python
def tto_baseline_path() -> Path:
    """Path to the offline league-SP TTO baseline artifact (generated data)."""
    override = os.environ.get("PITCHER_NARRATIVES_TTO_BASELINE")
    return Path(override) if override else DATA_DIR / "var" / "tto_baseline.parquet"


@functools.cache
def load_tto_baseline() -> "pl.DataFrame | None":
    """Load the TTO baseline artifact, or None if it has not been built.

    None (not an exception) so the deviation evaluator degrades to silence
    rather than crashing a report when the artifact is absent.
    """
    path = tto_baseline_path()
    if not path.exists():
        return None
    return pl.read_parquet(path)
```

(Add `import functools` if absent; confirm `pl` is imported in `data.py`.)

- [ ] **Step 6: Run the build test + a loader test**

Add to `tests/test_tto_baseline.py`:

```python
def test_load_tto_baseline_missing_returns_none(tmp_path, monkeypatch):
    import pitcher_narratives.data as d
    d.load_tto_baseline.cache_clear()
    monkeypatch.setenv("PITCHER_NARRATIVES_TTO_BASELINE", str(tmp_path / "nope.parquet"))
    assert d.load_tto_baseline() is None
    d.load_tto_baseline.cache_clear()
```

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_tto_baseline.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/tto_baseline.py src/pitcher_narratives/data.py tests/test_tto_baseline.py
git commit -m "feat(tto): offline league-SP TTO baseline build + artifact loader"
```

---

## Task 3: The TTO deviation evaluator (join + gate + P+ veto)

**Files:**
- Modify: `src/pitcher_narratives/engine/tto.py` (add `TTODeviation` + `evaluate_tto_deviations`)
- Test: `tests/test_tto_deviation.py`

**Interfaces:**
- Consumes: `TTOAnalysis` (`.splits: list[TTOSplit]` with `.pass_number, .avg_velo, .avg_p_plus, .pitches`), the baseline frame (Task 2 schema), `engine.deviation.evaluate_deviation`.
- Produces: `TTODeviation` dataclass (`pass_num: int, metric: str, actual_delta: float, median_exp_delta: float, robust_z: float, direction: str`); `evaluate_tto_deviations(tto: TTOAnalysis, baseline: "pl.DataFrame | None", *, min_pitches: int = 15) -> list[TTODeviation]`.

- [ ] **Step 1: Write the failing evaluator tests (the P+ veto truth table)**

Create `tests/test_tto_deviation.py`. Use a fixture baseline (pass 2: velo median −0.4/mad 1.0, pplus median −1.8/mad 2.0; pass 3: velo −1.1/mad 1.0, pplus −3.5/mad 2.0) and hand-built `TTOAnalysis` objects:

```python
import polars as pl
from pitcher_narratives.engine.tto import TTOAnalysis, TTOSplit, evaluate_tto_deviations

_BASE = pl.DataFrame({
    "cohort_key": ["LEAGUE_SP"]*4,
    "pass_num":   [2, 2, 3, 3],
    "metric":     ["velo","pplus","velo","pplus"],
    "median_exp_delta": [-0.4, -1.8, -1.1, -3.5],
    "mad":        [1.0, 2.0, 1.0, 2.0],
    "n":          [5000]*4,
})

def _split(p, velo, pplus, pitches=40):
    return TTOSplit(pass_number=p, pitches=pitches, avg_velo=velo, avg_p_plus=pplus,
                    avg_s_plus=None, fb_p_plus=None, sec_p_plus=None,
                    velo_delta="", p_plus_delta="", fb_p_plus_delta="", sec_p_plus_delta="",
                    pitch_types=[], platoon=[], small_sample=False)

def _tto(*splits):
    return TTOAnalysis(splits=list(splits), available=True, summary="", mix_shifts=[])

def test_typical_fade_yields_no_deviation():
    # pass3 velo −1.0 (vs −1.1), pplus −3.0 (vs −3.5): both typical
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 95.0, 102.0))
    assert evaluate_tto_deviations(tto, _BASE) == []

def test_corroborated_fatigue_is_surfaced():
    # pass3 velo 92.0 (Δ−4.0, z≈−1.95? tune) AND pplus 98 (Δ−7 vs −3.5): both neg-material
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 97.0))  # Δvelo −4.5, Δpplus −8.0
    devs = evaluate_tto_deviations(tto, _BASE)
    metrics = {d.metric for d in devs}
    assert "velo" in metrics and "pplus" in metrics
    assert all(d.direction == "fatigue" for d in devs)

def test_velo_drop_with_holding_pplus_is_vetoed():
    # Δvelo material-negative, Δpplus typical → velo fatigue vetoed → NO velo deviation
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 101.7))  # Δvelo −4.5, Δpplus −3.3 (~typical)
    devs = evaluate_tto_deviations(tto, _BASE)
    assert all(d.metric != "velo" for d in devs)  # velo vetoed

def test_resilience_pplus_positive_is_surfaced_not_vetoed():
    # Δvelo material-negative, Δpplus positive-material (holds) → pplus stamina surfaces
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 91.5, 105.2))  # Δvelo −4.5, Δpplus +0.2 vs −3.5
    devs = evaluate_tto_deviations(tto, _BASE)
    pplus = [d for d in devs if d.metric == "pplus"]
    assert pplus and pplus[0].direction == "stamina"

def test_missing_baseline_degrades_to_silence():
    tto = _tto(_split(1, 96.0, 105.0), _split(3, 88.0, 90.0))
    assert evaluate_tto_deviations(tto, None) == []

def test_unavailable_tto_is_silent():
    assert evaluate_tto_deviations(TTOAnalysis([], available=False, summary="", mix_shifts=[]), _BASE) == []
```

(Adjust the exact velo/pplus values so the z-scores land clearly inside/outside the gates — compute `z = (Δ − median)/(1.4826·mad)` when picking numbers; the comments show intent.)

- [ ] **Step 2: Run — fails**

Run: `uv run pytest tests/test_tto_deviation.py -v`
Expected: FAIL (`TTODeviation`/`evaluate_tto_deviations` undefined).

- [ ] **Step 3: Implement the evaluator in `engine/tto.py`**

Add near the top (imports) `from pitcher_narratives.engine.deviation import evaluate_deviation`, then:

```python
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


def evaluate_tto_deviations(
    tto: "TTOAnalysis",
    baseline: "pl.DataFrame | None",
    *,
    min_pitches: int = 15,
) -> list["TTODeviation"]:
    """Material within-game deviations vs. the LEAGUE_SP baseline (design §3-4).

    Silence (empty list) when TTO is unavailable, the baseline is absent, or no
    cell is material. Applies the P+-corroboration veto: a negative-material
    ``velo`` deviation is kept (fatigue) only if ``pplus`` is also
    negative-material; a positive-material ``pplus`` surfaces independently
    (resilience); an otherwise-unsupported velo drop is vetoed.
    """
    if not getattr(tto, "available", False) or baseline is None:
        return []
    by_pass = {s.pass_number: s for s in tto.splits}
    p1 = by_pass.get(1)
    if p1 is None or p1.avg_velo is None or p1.avg_p_plus is None:
        return []

    # baseline → {(pass_num, metric): (median, mad)}
    b = {(r["pass_num"], r["metric"]): (r["median_exp_delta"], r["mad"])
         for r in baseline.to_dicts() if r["cohort_key"] == "LEAGUE_SP"}

    # First pass: compute a Deviation per (pass>=2, metric) cell.
    raw: dict[tuple[int, str], "TTODeviation"] = {}
    for pass_num, split in sorted(by_pass.items()):
        if pass_num < 2 or split.pitches < min_pitches:
            continue
        for metric, actual, ref in (("velo", split.avg_velo, p1.avg_velo),
                                    ("pplus", split.avg_p_plus, p1.avg_p_plus)):
            if actual is None:
                continue
            cell = b.get((pass_num, metric))
            if cell is None:
                continue
            median_exp, mad = cell
            d = evaluate_deviation(actual - ref, median_exp, mad)
            if d.material:
                raw[(pass_num, metric)] = TTODeviation(
                    pass_num, metric, actual - ref, median_exp, d.robust_z, d.direction)

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
```

- [ ] **Step 4: Run — passes**

Run: `uv run pytest tests/test_tto_deviation.py -v`
Expected: PASS. (Tune the fixture velo/pplus values in Step 1 if a z lands on the wrong side of a gate.)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/engine/tto.py tests/test_tto_deviation.py
git commit -m "feat(tto): deviation evaluator with asymmetric gate + P+ veto"
```

---

## Task 4: Render residuals in the game-shape input + rewrite the specialist prompt

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`_build_game_shape_input` ~883; `_GAME_SHAPE_SPECIALIST_PROMPT` ~400)
- Test: `tests/test_game_shape_input.py`

**Interfaces:**
- Consumes: `evaluate_tto_deviations`, `load_tto_baseline`, `ctx.tto`.
- Produces: game-shape user input that carries a `## Within-Game Deviation` block (residual lines when material; an explicit typical-→-silent instruction when not).

- [ ] **Step 1: Write the failing render tests**

Create `tests/test_game_shape_input.py`. Use the Task-3 fixtures to drive `_build_game_shape_input` (or a small extracted renderer — see Step 3), asserting the rendered text:

```python
def test_typical_input_instructs_silence():
    text = _render_deviation_block([])  # no material deviations
    assert "typical" in text.lower()
    assert "do not report" in text.lower()

def test_material_input_speaks_residual_not_raw_fade():
    from pitcher_narratives.engine.tto import TTODeviation
    devs = [TTODeviation(3, "velo", -4.5, -1.1, -3.2, "fatigue")]
    text = _render_deviation_block(devs)
    assert "vs" in text and "-1.1" in text            # the expected value is shown
    assert "z" in text.lower() and "-3.2" in text     # the residual/z, not the raw fade
    assert "fatigue" in text.lower()
```

- [ ] **Step 2: Run — fails**

Run: `uv run pytest tests/test_game_shape_input.py -v`
Expected: FAIL (`_render_deviation_block` undefined).

- [ ] **Step 3: Add a pure renderer + wire it into `_build_game_shape_input`**

Add a pure helper to `pipeline.py` (kept pure so it's unit-testable without data):

```python
def _render_deviation_block(deviations: "list[TTODeviation]") -> str:
    """Render the within-game deviation section for the game-shape input.

    Empty -> an explicit 'typical, stay silent' instruction (success A). Non-empty
    -> one residual line per material cell (the residual + z + direction, NOT the
    raw within-game value)."""
    if not deviations:
        return (
            "## Within-Game Shape\n"
            "This pitcher's within-game shape is TYPICAL for a starter — no material "
            "deviation from the league fade curve. Do not report game shape as a "
            "finding; say nothing about TTO/velocity-arc unless another section "
            "makes it relevant."
        )
    lines = ["## Within-Game Deviation (vs. league starters)"]
    for d in deviations:
        label = "VELOCITY" if d.metric == "velo" else "PITCHING+ (P+)"
        lines.append(
            f"- Pass {d.pass_num} {label}: Δ{d.actual_delta:+.1f} vs. typical "
            f"{d.median_exp_delta:+.1f} (robust z {d.robust_z:+.1f}) — "
            f"{'excess fade / ' + d.direction if d.direction == 'fatigue' else 'holds better than expected / ' + d.direction}"
        )
    lines.append(
        "Report ONLY these residuals as the within-game story — frame fatigue vs. "
        "earned stamina by direction. Do not restate the raw pass-by-pass values as "
        "if the fade itself were the finding."
    )
    return "\n".join(lines)
```

In `_build_game_shape_input`, compute deviations and inject the block:

```python
from pitcher_narratives.data import load_tto_baseline
from pitcher_narratives.engine.tto import evaluate_tto_deviations
# ...
deviations = evaluate_tto_deviations(ctx.tto, load_tto_baseline()) if ctx.tto else []
# ... append _render_deviation_block(deviations) into the assembled sections,
# and STOP emitting the raw TTO summary as a lead when deviations is empty.
```

(Read `_build_game_shape_input` first; splice the block where the TTO data section currently goes, and gate the raw TTO dump so a typical pitcher no longer ships a raw fade table that re-invites the obvious narrative.)

- [ ] **Step 4: Rewrite `_GAME_SHAPE_SPECIALIST_PROMPT` to speak residuals**

Replace the "Flag stamina signals: velo cliff, S+ drop, command loss" / "Lead with the most notable within-game pattern" framing with residual-first, silence-when-typical instruction. New prompt body (keep the TEMPORAL GROUNDING rule and role focus):

```python
_GAME_SHAPE_SPECIALIST_PROMPT = """\
You are a game shape analyst. You describe how the pitcher's effectiveness \
changes WITHIN a game — but ONLY where it deviates from what a typical starter \
does.

CRITICAL — the fade is the baseline, not the story. Every starter loses \
velocity and effectiveness late; that is league-universal and is NOT a finding. \
The input's "Within-Game" section has already compared this pitcher to the \
league fade curve:
- If it says the shape is TYPICAL, write NOTHING about game shape. Do not \
narrate a fade, a TTO penalty, or a velocity arc. Silence is correct.
- If it lists residual deviations, those are the only within-game story. Report \
them as residuals (how far off the typical curve), and frame by direction: a \
FATIGUE residual (drops more than peers) vs. earned STAMINA (holds/improves \
where peers fade). "Loses the fastball late but P+ holds" is a real, valuable \
story — say it.

Rules:
- TEMPORAL GROUNDING: respect the prior-year relevance level; do not attribute \
within-game patterns to cumulative seasonal fatigue in a young season.
- Never restate the raw pass-by-pass numbers as if the fade itself were the \
finding. Speak in deviations from the norm.
- One focused paragraph, or nothing at all. Plain prose, no bullet lists.
- Do NOT analyze window-vs-season trends — a separate specialist handles that."""
```

- [ ] **Step 5: Run the render tests + affected suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_game_shape_input.py tests/test_tto_deviation.py -q`
Expected: PASS.
Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: PASS aside from the documented baseline failures. **If any game-shape prompt/input golden or `test_signals`/pipeline fixture asserts the old wording, re-baseline it deliberately** (the prompt change is intentional) — review each diff.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_game_shape_input.py
git commit -m "feat(game-shape): speak within-game residuals; stay silent on a typical fade"
```

---

## Task 5: Generate the real artifact, calibrate the gates, golden-pair proof

**Files:**
- Modify: `docs/superpowers/specs/2026-07-08-game-shape-deviation-gate-design.md` (record calibrated `Z_GATE_*` if changed) and/or `engine/deviation.py` (adjust constants)
- Add: `tests/test_tto_deviation_golden.py`

- [ ] **Step 1: Build the real baseline artifact**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -m pitcher_narratives.tto_baseline`
Expected: writes `.../var/tto_baseline.parquet` and prints the row count (should be ~4 rows: passes 2 & 3 × {velo, pplus}). Inspect it: `uv run python -c "import polars as pl; print(pl.read_parquet('/Users/matt/src/pitcher-narratives/var/tto_baseline.parquet'))"`. Sanity: `velo`/`pplus` `median_exp_delta` are negative and grow (more negative) from pass 2 → 3; `mad` > 0; `n` is large.

- [ ] **Step 2: Calibrate `Z_GATE_*` against the real window-aggregated z distribution**

Per the spec §3.3 Calibration note, the runtime residual uses window-aggregated deltas (lower variance → z shrinks). Sample a set of real starters, compute their `robust_z` per cell against the real baseline, and confirm the defaults (`-2.0` / `+1.5`) actually separate a known heavy fader (materially negative) from a league-median starter (silent). If the window-aggregation shrinkage makes the defaults too quiet/loud, adjust `Z_GATE_FATIGUE`/`Z_GATE_STAMINA` in `engine/deviation.py` and record the chosen values + the calibration reasoning in the spec. Script this as a throwaway `uv run python -c "..."` over a handful of `load_pitcher_data(...)` → `compute_tto_analysis` → `evaluate_tto_deviations`; capture the z values in the commit message.

- [ ] **Step 3: Golden-pair regression test**

Pick two real pitcher ids from Step 2: `POWER_FADER` (trips a material fatigue finding) and `TYPICAL_SP` (silent). Add:

```python
import os, pytest
pytestmark = pytest.mark.skipif(
    not os.environ.get("PITCHER_NARRATIVES_DATA_DIR"), reason="needs data dir")

def test_known_fader_is_material_and_typical_is_silent():
    from pitcher_narratives.data import load_pitcher_data, load_tto_baseline
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.engine.tto import compute_tto_analysis, evaluate_tto_deviations
    base = load_tto_baseline()
    assert base is not None, "run `python -m pitcher_narratives.tto_baseline` first"
    def devs(pid):
        data = load_pitcher_data(pid, recent_appearances=10)
        return evaluate_tto_deviations(compute_tto_analysis(data), base)
    assert devs(POWER_FADER_ID), "known fader should trip a material deviation"
    assert devs(TYPICAL_SP_ID) == [], "league-median starter should be silent"
```

Fill `POWER_FADER_ID`/`TYPICAL_SP_ID` from Step 2's findings; the test is `skipif` without a data dir so CI without data stays green.

- [ ] **Step 4: Run + commit**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_tto_deviation_golden.py -q` (PASS) and the full suite (PASS aside from baseline).

```bash
git add tests/test_tto_deviation_golden.py src/pitcher_narratives/engine/deviation.py docs/superpowers/specs/2026-07-08-game-shape-deviation-gate-design.md
git commit -m "test(tto): golden fader-vs-typical proof; calibrate Z_GATE_* on real distributions"
```

> The `var/tto_baseline.parquet` artifact itself is generated data (not committed). Document regeneration in the spec/README: run `python -m pitcher_narratives.tto_baseline` after the underlying statcast/aggs change.

---

## Self-Review

**Spec coverage:**
- §3.1 offline baseline artifact (median/MAD, long-form `cohort_key/pass_num/metric`, `var/` static) → Task 2. ✓
- §3.2 pure residual primitive + pass-1 exclusion → Task 1 (primitive), Task 3 (pass≥2 filter). ✓
- §3.3 asymmetric directional gate + P+ veto (truth table) → Task 1 (gate), Task 3 (veto). ✓
- §4 integration: residual rendering + silence-when-typical + prompt rewrite → Task 4. ✓
- §5 degradation (unavailable/missing → silence, no crash) → Task 2 (loader None), Task 3 (guards), tested. ✓
- §6 `cohort_key='LEAGUE_SP'` hardcoded, v2 seam → Task 2/3 (literal), documented. ✓
- §8 testing (primitive math, veto cases, golden pair, degradation, calibration) → Tasks 1/3/5. ✓
- §3.3 calibration note (window-vs-appearance shrinkage) → Task 5 Step 2. ✓

**Placeholder scan:** Task 5 leaves `POWER_FADER_ID`/`TYPICAL_SP_ID` to be filled from Step 2's real-data calibration — inherent to an empirical calibration step, flagged explicitly with how to obtain them, not a silent TODO. All source/code steps carry complete code.

**Type consistency:** `evaluate_deviation(actual_delta, median_exp_delta, mad) -> Deviation` (Task 1) is consumed with that exact signature in Task 3. `TTODeviation(pass_num, metric, actual_delta, median_exp_delta, robust_z, direction)` is produced in Task 3 and consumed identically in Task 4's renderer. Metric strings `"velo"/"pplus"` are consistent across the baseline schema (Task 2), evaluator (Task 3), and renderer (Task 4). `load_tto_baseline()` (Task 2) is called in Task 4/5.
