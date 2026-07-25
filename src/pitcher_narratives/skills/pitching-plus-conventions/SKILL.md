---
name: pitching-plus-conventions
description: Use when interpreting or narrating Pitching+ model metrics for a pitcher — formal S+/P+/L+ grades, xRV100, xSwing/xWhiff/xSwSt, diagnostic P/S contrasts, NORMAL/OUTLIER tags, or reconciling a grade with supported evidence.
audience: runtime
---

# Pitching+ Metric Conventions

Pitching+ grades are predictive model outputs, not causal explanations or
observed hitter behavior. Use only the typed facts and capability block in the
current handoff. Every factual claim cites exact same-frame fact IDs.

Do not improvise a model explainer inside agent prose. Report, changes, and
ask surfaces append the versioned deterministic explanation after the
provenance-bound generated artifact; recap intentionally omits it.

## Grade family

- **S+ (Stuff+)** uses the producer's S variant. It omits realized plate x/z,
  but includes release traits, arm angle, handedness/platoon context, fastball
  velocity context, coarse repertoire shares, and count processing. It is not
  pure velocity and movement, a tunneling model, or count-neutral.
- **L+ (Location+)** is the independently centered formal L variant emitted by
  the producer from P minus count-matched S. It is realized-location evidence,
  not target, intent, command, feel, or execution.
- **P+ (Pitching+)** is the producer's combined P-model grade.
- A plus grade is centered so higher is better. A grade alone does not identify
  feature importance, a model driver, or a physical cause.

## Canonical model and scale contract

- PitchingPlus predicts 13 outcome probabilities and converts them to expected
  run value with count-specific run values.
- P includes realized plate location. S removes realized `plate_x`/`plate_z`
  but retains release position/extension, arm angle, derived acceleration/spin
  coordinates, handedness/platoon, fastball-velocity context, coarse repertoire
  shares, and count processing.
- Exported S marginalizes standard outcome probabilities with the
  training-sample `P(count | broad pitch class, same_side)` distribution, then
  scores run value with the actual count. Formal L uses hidden same-count S.
- P, S, and L are independently centered on each variant's same-scoring-season
  MLB regular-season pitch-weighted mean. A plus grade of 100 is average and
  higher is better.
- The displayed 20–80 value is the uncapped plus grade minus 50, not an
  SD-scaled score. Conditional expected rates are means of per-pitch ratios.
  Group grades have no model-level minimum sample or shrinkage.
- Direct predictor inputs exclude explicit pitch or player identity, sequence
  or tunnel geometry, target, park/weather, game state, observed batted-ball
  result, raw spin rate, and raw pfx fields.
- Raw Statcast enters PitchingPlus. PitchingPlus emits the versioned
  manifest-covered bundle; Pitcher Narratives reads only that bundle.
  Deterministic Narrative code may select, aggregate, compare, and label
  emitted facts. Agents may interpret only cited facts.

## Sign and semantic conventions

- **xRV100**: more negative is better for the pitcher; positive costs runs.
- **Modeled probabilities** such as xSwing and xWhiff estimate event
  probabilities. Do not present them as observed hitter behavior.
- **P minus count-marginalized S** is a diagnostic contrast, not formal L+.
- **Outcome attribution** is an additive value component. It does not establish
  the physical, location, intent, or hitter-behavior mechanism for an outcome.
- Preserve supplied signs. If a grade and displayed aggregate do not reconcile,
  report the discrepancy. Without feature attribution, say: "The supplied
  aggregate profile does not identify the model driver."

## Rarity, capability, and citation

- NORMAL and OUTLIER describe physical rarity against the emitted pitch-class
  reference only. Neither label means irrelevant, important, good, or bad.
- Compare rates only with the emitted pitch-class baseline and cite both facts.
  There is no universal xWhiff cutoff.
- Model-driver claims require AVAILABLE feature attribution plus its cited fact.
- Spatial regions require AVAILABLE location regions plus same-frame cited
  facts.
- Platoon claims require AVAILABLE split evidence with exact sides, variant,
  frame, population, and adequate samples.
- Tunneling, deception, intent, command, target execution, and biomechanics
  remain unavailable unless their matching capability and cited facts are
  supplied. Do not substitute raw-equivalent data, prose, or intuition.
