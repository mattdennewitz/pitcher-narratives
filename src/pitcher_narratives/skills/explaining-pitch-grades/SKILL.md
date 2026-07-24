---
name: explaining-pitch-grades
description: Use when explaining, justifying, or reconciling why a specific pitch earns its Pitching+ grade (P+, S+/Stuff+, or L+/Location+) from the provided arsenal data — grade explanations, class-baseline comparisons, grade-vs-xRV100 discrepancies, NORMAL/OUTLIER shape questions.
audience: runtime
---

# Explaining a pitch's P+ / S+ / L+ grade

A grade is a model output, not a decision trace. Explain only from the typed
facts and capability states supplied in the current handoff. Every quantitative,
directional, comparative, spatial, behavioral, and model-semantic statement must
cite the exact same-frame fact IDs that support it.

The answer explains only supported pitcher evidence. Do not generate model
definitions: the ask surface appends the validated, versioned deterministic
model-and-data-boundary explanation after the audited answer.

## Method

1. **Anchor to the pitch-type class baseline.** Compare a pitch with its
   emitted, cited pitch-class reference rather than assuming 100 is the
   class-specific average. Preserve the population, sample, and frame.
2. **Separate observation from interpretation.** Report a cited aggregate or
   grade as an observation. Add an interpretation only when its required
   capability is AVAILABLE and the interpretation cites that capability fact.
3. **Treat rarity as rarity.** NORMAL and OUTLIER describe distance from an
   emitted physical reference. Neither label establishes model importance,
   causation, hitter behavior, or narrative priority.
4. **Respect the S boundary.** S omits realized plate x/z, but it includes
   release traits, arm angle, handedness/platoon context, fastball velocity
   context, coarse repertoire shares, and count processing. It is not a pure
   velocity-and-movement model, a tunneling model, or count-neutral.
   Exported S uses training-sample
   `P(count | broad pitch class, same_side)` outcome marginalization followed
   by actual-count run-value scoring. Formal L uses hidden same-count S.
5. **Reconcile signs without inventing a cause.** Preserve the emitted S+/L+/P+
   and xRV100 directions. If supplied values disagree, report the discrepancy.
   Without feature attribution, use this limitation exactly: "The supplied
   aggregate profile does not identify the model driver."
6. **Keep unavailable claim classes unavailable.** Tunneling, deception, intent,
   command, target execution, biomechanics, platoon vulnerability, and model
   drivers require their matching AVAILABLE capability and cited facts.
   Physical aggregates, outcome contributions, and realized-location evidence
   cannot substitute for those capabilities.
7. **Do not turn model probabilities into observed behavior.** Describe xSwing
   or xWhiff as modeled estimates unless a separate observed, cited fact is
   supplied. Use the emitted pitch-class comparison; there is no universal
   whiff threshold.
8. **Preserve the model and scale contract.** PitchingPlus converts 13 predicted
   outcomes to expected run value with count-specific run values. P includes
   realized location. P, S, and L each use their own same-scoring-season MLB
   regular-season pitch-weighted 100 anchor. The current 20–80 display is
   uncapped `plus - 50`, not SD-scaled. Conditional rates are means of
   per-pitch ratios; group grades have no model-level minimum or shrinkage.
9. **Respect direct-input and producer boundaries.** The predictor does not
   directly use pitch/player identity, sequence/tunnel geometry, target,
   park/weather, game state, observed BBE result, raw spin rate, or raw pfx.
   Raw Statcast enters PitchingPlus; Pitcher Narratives consumes only the
   producer's versioned manifest-covered bundle, and agents interpret cited
   emitted facts.

## Output

Write 1-3 concise paragraphs about the requested pitch. Preserve inline fact
citations and explicit limitations. Omit any claim whose facts are unknown,
stale, wrong-frame, insufficient, or unavailable.
