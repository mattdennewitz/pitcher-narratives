---
name: explaining-pitch-grades
description: Use when explaining, justifying, or reconciling why a specific pitch earns its Pitching+ grade (P+, S+/Stuff+, or L+/Location+) from the provided arsenal data — grade explanations, class-baseline comparisons, grade-vs-xRV100 discrepancies, NORMAL/OUTLIER shape questions.
audience: runtime
---

# Explaining a pitch's P+ / S+ / L+ grade

A grade is the end of a chain: physical pitch -> the model's outcome
predictions -> grade. Explain it by walking that chain over the data you were
given. Do not compute anything — every number is already in the input.

## Method

1. **Anchor to the pitch-type class baseline, not 100.** The input's
   "S-variant league avg: S+ ..." line is the average grade *for that pitch
   type*. Four-seam fastballs sit below the all-pitch 100; breaking balls sit
   above. Read the pitch's grade against its own class line, then explain the
   gap from there — "92 vs the ~97 fastball average" beats "92 vs 100".
2. **A NORMAL trait is not a driver.** Each physical trait is tagged NORMAL or
   OUTLIER. If velocity/spin is an OUTLIER but the grade is unremarkable, the
   story is that the *shape* (movement, ride, arm-slot fit) doesn't separate
   from expectation — the model prices the shape, not the radar reading. Never
   invent a velocity-causation story.
3. **Reconcile the sign.** Sub-100 S+ should pair with a positive (costly)
   xRV100_S; above-100 with negative (run-saving). If they disagree, report the
   discrepancy honestly rather than forcing a story.
4. **Cite the metric behind each claim.** "misses bats" -> xWhiff_S; "hitters
   attack it" -> xSwing_S; "hittable" -> xRV100_S.
5. **Contrast with the arsenal.** A grade reads differently next to the
   pitcher's other pitches — a plus breaker beside an average fastball tells a
   tunneling story.

See the `pitching-plus-conventions` skill for the authoritative sign
conventions and the NORMAL/OUTLIER rule.

## Output

1-3 tight paragraphs of scout prose about the ONE pitch named in the leading
instruction. No preamble, no restating the question.
