# Pitch Shape vs Arm Slot

This document explains the arm-slot movement interaction feature
(`shape.py`): what it computes, why the math is shaped the way it is,
and how its output is threaded through the multi-agent pipeline so the
final capsule can say things like *"given his arm angle, the fastball's
movement profile is dead zone."* For the system-wide picture, see
`METHODOLOGY.md`.

## The insight being automated

A pitch's movement numbers mean nothing in isolation — they mean
something *relative to what the hitter's eye predicts from the release
point*. A four-seamer with 16 inches of ride is elite from a sidearm
slot and unremarkable from straight over the top, because hitters
calibrate their swing to the trajectory the arm angle implies.

Two well-known consequences:

- **Dead zone**: a fastball whose ride and run match the league-average
  shape for its arm slot. Nothing about the pitch surprises the
  hitter's eye, so it tends to underperform its raw velocity and
  movement. This is the classic explanation for a fastball with NORMAL
  physical metrics and a poor whiff rate.
- **Deception**: movement well above or below slot expectation — a low
  slot with big ride ("invisiball"), or a high slot with unexpected
  sink/run — outperforms its raw numbers because the shape contradicts
  the visual cue.

An LLM can recite these concepts, but asking it to *derive* them from
raw `arm_angle`/`pfx_x`/`pfx_z` columns invites inconsistency and
hallucination. Following the project's core premise — arithmetic is the
engine's job, interpretation is the model's — `shape.py` pre-computes
the interaction deterministically and hands the pipeline a labeled
fact.

## What the engine computes

### 1. League expectation table (`compute_slot_expectations`)

A table of expected movement conditional on arm angle, built once per
process from the full Statcast parquet set (all pitchers, all loaded
seasons) and cached:

- **Filter**: rows with non-null `arm_angle`, `pfx_x`, `pfx_z`.
  Statcast populates `arm_angle` on roughly 40% of pitches; with two
  seasons pooled there is ample sample for every common cell.
- **Unit conversion**: raw Statcast `pfx_*` values are in **feet**;
  everything in this module is converted to inches (×12) at ingestion.
- **Handedness mirroring**: horizontal movement is converted to
  *arm-side run* — `pfx_x` for LHP, `-pfx_x` for RHP — so left- and
  right-handed samples pool into one table. (Verified empirically:
  league sinker means mirror at ±1.24 ft by handedness.)
- **Bucketing**: arm angle is floored into 10° buckets per pitch type.
  Cells with fewer than 200 league pitches are dropped.

The table captures the physical gradient cleanly: four-seam ride rises
from ~12 in at a 10° (sidearm) slot to ~20 in at 70° (over the top),
while arm-side run falls from ~12 in to ~2 in over the same range.

**Why 10° buckets?** The FF gradient is roughly 1–2 in of ride per 10°
of arm angle. A 10° bucket therefore bounds the worst-case
discretization bias at ~1 in — half the 2 in classification threshold —
while keeping nearly every pitch type's slot range above the 200-pitch
floor. Narrower buckets halve the bias but push rare pitch types below
the sample floor; wider buckets let bucket-edge bias approach the
decision threshold.

### 2. Interpolation (`_interpolate_expectation`)

Bucket means are anchored at bucket centers (the 30–40° bucket's mean
represents 35°). A pitcher's expectation is linearly interpolated
between the two buckets whose centers straddle his exact mean arm
angle, so expectations vary continuously instead of stepping at bucket
edges — a pitcher at 39.9° and one at 40.1° get nearly identical
baselines rather than baselines an inch apart. At the edge of the
table (one neighbor missing), the nearest bucket's means are used
unchanged.

### 3. Per-pitcher profile (`compute_pitch_shape`)

For each pitch type the pitcher throws:

- Uses **full-season** rows with arm-angle data, not the recent window
  — shape relative to slot is a physical trait, not a trend. Types with
  fewer than 10 arm-angle pitches are skipped.
- Computes mean arm angle, observed ride, and observed arm-side run
  (inches, mirrored).
- Looks up the interpolated league expectation at that exact arm angle
  and takes residuals: `observed − expected` on each axis.

### 4. Classification (`_classify_shape`)

Deterministic tags from the residuals, with a 2 in threshold per axis:

| Condition | Tag |
|-----------|-----|
| Fastball (FF/SI/FC), both residuals < 2 in | `DEAD ZONE -- movement matches slot expectation; hitters see what the arm angle predicts` |
| Ride residual ≥ +2 in | `Ride above slot expectation (+X.X in)` |
| Ride residual ≤ −2 in | `Sinks below slot expectation (−X.X in)` |
| Run residual ≥ +2 in | `More arm-side run than slot suggests (+X.X in)` |
| Run residual ≤ −2 in | `More cut/glove-side than slot suggests (−X.X in)` |
| Non-fastball, both residuals < 2 in | `In line with slot expectation` |

Both-axis flags combine ("Sinks below slot expectation (−4.8 in); more
cut/glove-side than slot suggests (−2.3 in)"). The dead-zone concept is
reserved for fastballs — a slider matching its slot expectation is
merely unremarkable, not a liability.

## How it reaches the narrative

The hybrid design surfaces both the raw numbers *and* the derived
label, so the model's claim is grounded in arithmetic the engine
controls:

1. **Context document** (`context.py`): `render_pitch_shape` emits a
   "Pitch Shape vs Arm Slot" section — one line per pitch type with
   slot, observed vs expected movement, and tag — prefixed by a
   self-documenting explanation of what DEAD ZONE means, so consumers
   need no outside knowledge. Example output:

   > - 4-Seam Fastball (FF): 40 deg slot; ride 15.8 in (slot exp 15.8),
   >   arm-side run 7.3 in (slot exp 7.6) -- DEAD ZONE -- movement
   >   matches slot expectation; hitters see what the arm angle predicts

2. **Stuff specialist** (`pipeline.py`): the same section is appended
   to the stuff specialist's input, and an `ARM SLOT CONTEXT`
   interpretation rule in its system prompt requires every fastball
   paragraph to reference the slot context when the section is present.
   The rule explicitly directs the specialist to use the dead-zone tag
   to explain mediocre S+ or weak xWhiff despite NORMAL raw metrics —
   the exact case where the old prompt could only say "the model sees
   something in the movement interaction."

3. **Writer** (`personas.py`): `SHARED_WRITER_BASE` instructs the
   writer (all personas) to treat arm-slot shape findings from
   specialists as high-value mechanism evidence and work them into the
   capsule rather than dropping them during synthesis.

The data flows engine → context → specialist → writer with the tag
intact at every hop, and the specialist-audit loop can verify any
shape claim against the same rendered section.

## Failure modes and guardrails

- **Sparse arm-angle data**: pitch types under 10 arm-angle pitches are
  omitted; a pitcher with no usable types gets no section, and the
  specialist prompt rule only activates "when the section is present."
- **Unusual slots**: a slot outside the league table's populated range
  falls back to the nearest bucket rather than extrapolating.
- **Units**: the module converts feet→inches internally and labels
  everything explicitly, with a test asserting expectations land in a
  plausible inch range to catch regressions.

## Tests

`tests/test_shape.py` covers bucketing, every classification branch,
the league table's physics (ride increases and run decreases with slot
height, all in inches), interpolation (exact-center identity, midpoint
blending, boundary continuity, edge fallback), and a real-data profile.
`tests/test_context.py` and `tests/test_pipeline.py` pin the section's
presence in the context document and the stuff specialist input, and
literal-string tests pin the prompt rules in `pipeline.py` and
`personas.py`.
