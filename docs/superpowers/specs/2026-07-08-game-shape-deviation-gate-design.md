# Population-Baseline Deviation Gate — Game-Shape v1 — Design

**Date:** 2026-07-08
**Status:** Approved design, pending implementation plan
**Topic:** Stop the analysis from surfacing league-universal patterns (the
third-time-through fade, late-game velocity decline) as if they were
pitcher-specific insights. Compare each pitcher's within-game shape against a
precomputed population baseline and surface only the *residual* — the deviation
from what a typical starter does — gated so a typical fade produces silence.

---

## 1. Problem

Every starter gets tagged with a "stark contrast between early-game power and
late-game pivots." This is a **base-rate insight**: the times-through-the-order
(TTO) penalty and late-game velocity decline are league-*universal*, so "this
starter fades late" is about as informative as "this hitter sometimes strikes
out." The game-shape specialist (`_GAME_SHAPE_SPECIALIST_PROMPT`,
`pipeline.py:400`) is told to "flag stamina signals: velo cliff, S+ drop,
command loss in later passes" and "lead with the most notable within-game
pattern" — but it has **no population baseline** to compare against. Every
baseline in the system is *self*-relative (this window vs. this pitcher's own
season) or absolute. So the specialist cannot tell that fading late *is* the
norm, and surfaces it as the headline for every starter. The signal extractor
then promotes it, and it reaches the reader as a finding.

The insight worth reporting is not *that* a starter fades — it is whether he
fades **more or less than expected, or in an unusual way** (loses the fastball
but the effectiveness holds; craters at pass 2 instead of pass 3; the slider
actually improves late).

## 2. Scope & success criteria

- **Scope (C):** game-shape / TTO is the **proving ground** for a reusable
  "compare-to-population, report-the-residual" mechanism. Build it for
  within-game shape first, designed so the same primitive extends to other
  specialists (pitch mix, velo trend) later.
- **Success (A):** when a starter's within-game shape is *typical* (a
  bog-standard fade, no material deviation from peers), the report says
  **nothing** about game shape — the words go to what is distinctive. Silence =
  "we checked; nothing here." Game shape enters the narrative only when a
  deviation crosses a materiality threshold.
- **Non-goal:** changing the anchor/validation stack, the writer voice, or the
  other specialists' logic in v1.

## 3. Mechanism: baseline → residual → gate

Matches the project's core value — the LLM receives pre-computed deltas and
baselines and focuses on insight, not arithmetic. Three parts:

### 3.1 The baseline artifact (offline build, static)

An offline build step aggregates the **league-wide** statcast parquet into a
per-pass expected-decay table and writes it as a **static parquet artifact**
(shipped alongside the other data inputs, rebuilt only when the underlying data
changes). It is **never** computed at report time — league aggregation is too
heavy for the hot path.

**Delta definition:** for each league SP appearance, compute the per-pass metric
(velocity, P+) and its delta vs. **that appearance's pass 1** (the reference,
Δ≡0). The baseline is the distribution of those per-appearance deltas across all
league SP appearances, per pass.

**Robust statistics (not mean/SD).** TTO decay distributions have a heavy left
tail (early hooks, injury blowups, mechanical collapses) that would inflate SD
and make the runtime gate too permissive for genuine slow-burn fatigue. Store
the **median** expected delta and the **MAD** (median absolute deviation) per
cell.

**Schema (long form, keyed for extensibility and the Join Key Pattern):**

| column | meaning |
|---|---|
| `cohort_key` | v1: always `LEAGUE_SP`. The upgrade seam (see §6). |
| `pass_num` | 2, 3, … (pass 1 is the Δ≡0 reference; not stored). |
| `metric` | `velo` \| `pplus`. Long form so new metrics are new rows, not new columns — the shared contract for scope-C generalization. |
| `median_exp_delta` | median per-appearance (passN − pass1) delta across league SP. |
| `mad` | median absolute deviation of that delta. |
| `n` | appearances in the cell (for a sample-adequacy guard). |

### 3.2 The residual evaluator (runtime, cheap)

`engine/tto.py::compute_tto_analysis` already yields this pitcher's per-pass
ΔVelo/ΔP+ over the window. A new `engine/deviation.py` primitive computes, per
(pass, metric):

- `residual = actual_delta − median_exp_delta`
- robust z: `z = residual / (1.4826 · mad)` → and an approximate percentile.
- `direction`: `fatigue` if the residual is on the harmful side (velo/P+ drops
  more than expected), `stamina` if on the beneficial side (holds/improves vs.
  the norm).

**Pass-1 identity handling:** pass 1 is the Δ≡0 reference with zero dispersion;
the evaluator **excludes `pass_num == 1`** from the join so it never evaluates
`residual / 0`.

`engine/deviation.py` is the reusable primitive: a pure function
`evaluate_deviation(actual_delta, median_exp_delta, mad) -> Deviation` with
`{residual, robust_z, percentile, direction, material}`. Other specialists plug
their own baseline tables into the *same* function — nothing else changes.

Output: a `list[TTODeviation]`, one per material (pass, metric) cell, each with
`pass_num, metric, actual_delta, median_exp_delta, robust_z, percentile,
direction`.

### 3.3 The directional, asymmetric gate + P+ veto

**Per-cell + directional.** The gate runs per (pass, metric) with the sign
carried, because a pitcher can be material-negative on ΔVelo yet
material-positive on ΔP+ — "loses the fastball late but stays effective," a
genuinely non-obvious story we *want*.

**Asymmetric thresholds** (both empirically calibrated constants, not guessed):
- `Z_GATE_FATIGUE = -2.0` — a harmful deviation must be undeniable to be
  narrated. Deliberately conservative: fatigue false-positives are the failure
  mode we are fixing, and the flat baseline systematically over-punishes the
  finesse negative tail (§6).
- `Z_GATE_STAMINA = +1.5` — a beneficial deviation (elite stamina / mechanical
  hold) is easier to surface; it is a high-value, low-risk story.

**P+-corroboration veto on fatigue findings.** P+ is the reality check on
velocity. A negative ΔVelo finding is only narrated as *fatigue* when ΔP+
corroborates it:
- ΔVelo neg-material **and** ΔP+ neg-material → **fatigue finding** (real).
- ΔVelo neg-material **and** ΔP+ *positive*-material → **not vetoed**; surfaced
  via the P+ positive cell as "velo erodes but effectiveness holds/climbs."
- ΔVelo neg-material **and** ΔP+ typical → **veto** the velo fatigue finding →
  silence.

A 1.5-mph drop for an 89-mph starter whose P+ has not moved is not fatigue — it
is just pitching; the veto suppresses that false narrative without swallowing
the genuinely interesting velo-down-but-effective case (handled by the positive
gate independently).

**Sample-adequacy guard:** if a cell's `n` (baseline) or the pitcher's per-pass
pitch count is below a minimum, treat as non-material (do not manufacture a
finding from noise).

## 4. Integration flow

1. `compute_tto_analysis(data)` → per-pass ΔVelo/ΔP+ (existing).
2. New evaluator joins the baseline (`cohort_key='LEAGUE_SP'`, `pass_num≥2`),
   runs `engine/deviation.py`, applies the asymmetric gate + P+ veto → a
   (possibly empty) `list[TTODeviation]` of material cells.
3. `_build_game_shape_input` (`pipeline.py:883`) renders from the deviations,
   **not** the raw fade:
   - **No material cells** → the input states: "within-game shape is typical for
     a starter — no material deviation from the league fade curve; do not report
     it," and the specialist stays **silent** on game shape (success A).
   - **Material cells** → render the residual and direction, e.g.
     *"ΔVelo pass 3: −3.6 vs. typical −1.1 (robust z −3.2, ~1st pctile) — severe
     late fade"* / *"ΔP+ pass 3: +0.2 vs. typical −3.5 (z +2.1) — holds, unlike
     the norm."*
4. `_GAME_SHAPE_SPECIALIST_PROMPT` is rewritten to speak in **residuals** (not
   raw within-game values), to frame by direction (fatigue vs. earned stamina),
   and to omit game shape entirely when the input says it is typical.

Because typical fades never enter the specialist input, they never reach the
signal extractor or the writer — **the obviousness is killed at the source, not
filtered downstream.**

## 5. Error / degradation handling

- **TTO unavailable** (`TTOAnalysis.available == False`, existing) → no
  deviations → specialist silent on game shape (unchanged from the typical
  branch).
- **Baseline artifact missing / cohort or pass absent** → the evaluator cannot
  judge, so it emits **no** deviation (→ silence), and logs a warning. It must
  never fall back to surfacing the raw fade (that reintroduces the bug) and must
  never crash the pipeline.
- Below sample-adequacy minimums → non-material (§3.3).

## 6. Known v1 limitations → the v2 upgrade (Join Key Pattern)

The flat `LEAGUE_SP` baseline was chosen deliberately (isolate the
baseline→residual→gate plumbing from cohort-boundary and sample-size noise while
proving the mechanism). Two documented blind spots motivate the eventual
cohort upgrade; the P+ veto + asymmetric gate mitigate but do not eliminate
them:

1. **Stuff+ non-linearity at velocity cliffs.** A flat ΔVelo baseline treats
   −1.5 mph identically at 96→95 (which can shove a four-seamer off a Stuff+
   cliff, −12 to −15) and at 90→89 (−4 to −6). v1 systematically underrates velo
   loss for power arms and over-punishes finesse. Robust MAD helps the tail
   inflation, not this cohort-blend bias.
2. **Pass-3 survivor bias.** Finesse pitchers who reach pass 3 are self-selected
   cruisers (little physical decay); power arms there ride max effort (steeper
   fatigue). A blended `LEAGUE_SP` pass-3 curve is too forgiving for high-velo,
   too punitive for soft-tossers.

**v2 upgrade (data-engineering only, zero change to residual/gate math):** the
baseline build emits stratified `cohort_key`s and the evaluator derives the key
from the pitcher's profile. The recommended **first** v2 step is the binary
split **`SP_POWER` (pass-1 avg velo ≥ 93.5) / `SP_FINESSE` (< 93.5)** — the
smallest cohorting that removes the blended-curve bias, and a direct proof that
the `cohort_key` architecture pays off. Everything downstream of the join is
untouched.

## 7. Components (isolation)

| Unit | Responsibility | Depends on |
|---|---|---|
| Baseline build (script/module) | Aggregate league SP parquet → `LEAGUE_SP` per-pass median/MAD table; write static parquet. | league-wide data loader (`data.py`). |
| Baseline loader | Load the static table at runtime. | the artifact. |
| `engine/deviation.py` | Pure `evaluate_deviation(actual, median_exp, mad)` → `Deviation`; the reusable primitive. | nothing (pure). |
| TTO deviation evaluator | Join pitcher TTO × baseline, apply gate + P+ veto → `list[TTODeviation]`. | `compute_tto_analysis`, baseline loader, `deviation.py`. |
| `_build_game_shape_input` / specialist prompt | Render residuals or the typical-→-silent instruction. | the evaluator. |

## 8. Testing

- **`engine/deviation.py`:** residual + robust-z math; MAD ×1.4826 scaling; both
  gate directions; asymmetric thresholds; pass-1 exclusion / no div-by-zero;
  sample-adequacy guard.
- **Evaluator:** join a fixture baseline; material-negative, material-positive,
  and typical inputs → correct `TTODeviation` shape; the **P+ veto** cases
  (velo-neg + P+-typical → suppressed; velo-neg + P+-neg → fatigue; velo-neg +
  P+-pos → resilience surfaced).
- **Golden pair:** a known power-fader (material fatigue) vs. a league-median
  starter (silent game shape) — proves the gate suppresses the obvious case.
- **Baseline build:** reproducible output; schema conformance (`cohort_key`
  present and `== 'LEAGUE_SP'` in v1).
- **Degradation:** missing artifact → silence + warning, no crash; TTO
  unavailable → silence.
- **`Z_GATE_*` calibration check:** the thresholds separate a known fader from a
  median starter on real distributions (documented calibration, not a guessed
  constant).

## 9. Open questions (resolved)

- Reference class → flat `LEAGUE_SP` for v1; binary `SP_POWER/SP_FINESSE` is the
  first v2 step (§6).
- Dispersion → median + MAD (robust), not mean + SD (§3.1).
- Skip vs. hedge on the typical case → **silence** (success A).
- Gate → per-cell, directional, **asymmetric** (`−2.0` fatigue / `+1.5`
  stamina), with the **P+ veto** on fatigue (§3.3).
- Baseline unit caveat: dispersion is over *per-appearance* deltas while the
  runtime residual uses the pitcher's *window-aggregated* delta (lower
  variance), making the gate slightly conservative — acceptable for v1;
  revisit during `Z_GATE` calibration if it makes the gate too quiet.
