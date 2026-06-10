---
name: pitching-plus-conventions
description: Use when interpreting or narrating Pitching+ model metrics for a pitcher — S+/P+/L+ grades, xRV100, xSwing/xWhiff/xSwSt, P-vs-S location impact, NORMAL/OUTLIER tags, or reconciling a grade with its physical inputs.
audience: runtime
---

# Pitching+ Metric Conventions

The model grades each pitch by predicting 13 outcome probabilities from its physical characteristics, then pricing each outcome in runs. Read every grade as the end of a chain: physical pitch -> model prediction -> grade. These conventions are absolute; they override intuition.

## The grade family (100 = league average)

- **S+ (Stuff+)** — raw stuff only: velocity + movement, location ignored.
- **L+ (Location+)** — what command adds or subtracts.
- **P+ (Pitching+)** — the combined grade (stuff + location).
- Above 100 helps the pitcher; below 100 hurts. A pitch can have strong S+ and weak P+ (good stuff, bad location) or the reverse.

## Sign conventions (the rules that trip people up)

- **xRV100** (expected run value / 100 pitches): **more negative = better** for the pitcher. Positive = costing runs.
- **Probabilities** (xSwing, xWhiff, xSwSt): higher = more of that event.
- **P vs S** isolates location: `P − S` is the location impact. For probabilities, `P > S` means location *increases* the rate. For xRV100, `P < S` (more negative) means location is *helping*.
- **Component attribution** (per-outcome xRV breakdown): negative = pitcher benefits; positive = costs runs.

## Directional consistency (flag, don't force)

- S+ below 100 should pair with positive xRV100_S (costly); S+ above 100 with negative xRV100_S (saves runs). If the signs disagree, **report the discrepancy honestly** rather than inventing a story to reconcile them.
- L+ above 0 should make P-variant xRV100 more negative than S-variant. If not, note it.

## NORMAL vs OUTLIER

- A metric within ±1.5 SD of the league average for that pitch type is **NORMAL** — do not cite it as a driver of a good or bad grade. When velocity is NORMAL, look to movement shape, movement interaction (horizontal × vertical), spin, tunneling, or arm-slot fit instead.
- xWhiff_S ≥ 25% is a meaningful whiff rate; reconcile that strength before calling a pitch "poor."

## Mandatory reconciliations

- Every behavioral claim cites the metric behind it: "hitters take it" -> xSwing_S; "misses bats" -> xWhiff_S; "hittable" -> xRV100_S or batted-ball data.
- Secondary pitches (breaking/offspeed) derive value from movement and deception, not velocity — don't default to a velocity explanation for them.
- No hallucinated causation: if the physical profile looks average but the grade is extreme, say the model sees something the raw averages don't capture rather than inventing a velocity story.
