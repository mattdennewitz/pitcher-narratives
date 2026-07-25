# Daily Runs — Triage, Curation, and Why It Works

This document describes the daily process: how `pitcher-narratives` turns
*yesterday's slate of games* into a short, trustworthy watchlist of
pitchers worth a closer look, and — for the few that earn it — a full
scouting capsule. It explains the architecture, assesses how effective
the current implementation is (with empirical evidence), and documents
the failure modes that specifically bite a daily cadence. For the
narrative pipeline itself, see `METHODOLOGY.md`; for one worked signal,
see `pitch-shape-arm-slot.md`.

## The daily problem

Every day the league throws ~15–30 pitcher appearances worth examining.
Generating a full multi-agent capsule (`METHODOLOGY.md`) for each is
expensive — 15–25 LLM calls per pitcher — and most outings are
unremarkable: the pitcher did roughly what his season says he does. The
daily job is therefore a **triage** problem before it is a writing
problem. You want to spend LLM budget only on the appearances where
*something changed*.

That yields a three-stage funnel, widest first:

1. **Scout** (`scout.py`) — a cheap, deterministic pre-filter. Scores
   *every* appearance in the window for "interestingness" and returns a
   ranked shortlist. No LLM.
2. **Curate** (`curator.py`) — one LLM pass over the shortlist that
   picks the 3–5 most compelling stories, assigns a conviction level,
   and explains what it rejected.
3. **Narrate** (the pipeline) — optionally run the full capsule on the
   handful of pitchers the curator flagged High conviction.

The guiding split is **recall then precision**: the deterministic score
is tuned to get every genuinely interesting appearance *into* the
shortlist (recall); the LLM curator supplies judgment to pick the few
that matter (precision). This is the same "engine does arithmetic, LLM
does insight" division the rest of the system uses — applied to *which
pitcher to look at* instead of *what to say about him*.

## Stage 1 — Scout scoring

`scout_appearances(window_days=1, top_n=20, min_pitches=20)` loads the
Pitching+ appearance aggregates, filters to MLB regular season, takes
the most recent date(s), and scores each appearance as a weighted sum of
*change* signals versus that pitcher's season baseline:

| Signal | Weight | Fires when |
|--------|-------:|-----------|
| `new_pitch` | 4.0 | a pitch is ≥5% of the game and <1% of the season |
| `velo_decline` | 3.5 | fastball velocity falls ≥1.5 mph from first to last outing third, with ≥9 fastballs |
| `splus_lplus_level_gap` | 3.5 | a sufficiently sampled pitch has S+ ≥110 and L+ ≤80 |
| `location_grade_surge` | 3.5 | season L+ is <90 and appearance L+ is ≥110 |
| `velo_delta` | 3.0 | fastball velocity is ≥1.5 mph off season |
| `splus_lplus_divergence` | 3.0 | S+ and L+ change in opposite directions, each ≥10 |
| `dropped_pitch` | 3.0 | an established pitch (≥10% of season) is absent |
| `pplus_swing` | 2.5 | overall P+ is ≥15 points off season |
| `pplus_lplus_split` | 2.5 | appearance P+ is ≥105 while L+ is <85 |
| `spin_drop` | 2.0 | fastball spin is at least 1.5 robust standard deviations below its leave-one-game-out reference |
| `usage_shift` | 2.0 | a pitch's usage is ≥8 percentage points off season |
| `hard_hit_spike` | 1.5 | reserved; no current emitter |
| `workload_flag` | 1.0 | the pitcher has worked 3+ consecutive days |

The crucial design choice is correct: it scores **changes, not
results**. ERA, strikeouts, and win/loss never enter. A pitcher who got
shelled but threw exactly his season profile scores ~0; a pitcher who
quietly added 2 mph and a new slider scores high even in a loss. That is
the right lens for a scout, and it is why the daily output reads like
"what's different" rather than a box score.

## Stage 2 — Curator

The curator (`_CURATOR_PROMPT`) receives the shortlist as signal bullets
and selects 3–5 pitchers against an explicit hierarchy — Clean Breakout
(velo + stuff), Lab Project (elite S+, poor L+), Identity Crisis (mix
overhaul), Red Flag (likely tracking/sample noise) — each with a
**conviction** level scaled to sample size, plus a "Why not the others"
section that forces the model to articulate its filter. The hierarchy
and the explicit-rejection step are genuinely good: they make the watch
list legible, not a black box.

## Is it effective? Evidence, and where it breaks

The **architecture** is effective and right for a daily run. The
**current scoring**, evaluated against a real slate (2026-04-13), has
specific, fixable weaknesses that degrade it from "ranked watchlist" to
"unranked candidate pool that the curator must clean up."

### What works

- Cheap, deterministic, runs over the whole slate — the funnel shape is
  correct, and recall (interesting outings reaching the shortlist) is
  generally good.
- Change-based scoring surfaces process stories the box score hides.
- The curator's conviction + explicit-rejection design is trustworthy
  when it runs to completion.

### Where it breaks (empirical)

1. **The score ranks by signal *volume*, not intensity.** It is an
   unweighted sum of fired weights, so a pitcher who trips many weak
   signals outranks one with a single strong one. On the test slate the
   top appearance (score 23.5) fired nine signals; the magnitude of each
   is in the detail string but **not in the score** — a +1.5 mph blip
   and a +4 mph jump both contribute exactly 3.0, and an absurd
   `L+ −173` divergence scores the same as a modest `L+ −40`.

2. **Correlated signals are multi-counted.** Usage percentages must sum
   to 100%, so one mix change manufactures several `usage_shift` signals
   (one pitcher: SI −17 pp necessarily coincides with FF +19, CH +9,
   and SL −12). `pplus_swing`, `splus_lplus_divergence`, and
   `splus_lplus_level_gap` can also describe the same grade pattern.
   The sum can therefore count one appearance-level pattern several
   times and inflate that pitcher's rank.

3. **Small samples dominate the ranking.** `min_pitches=20` admits
   20–29-pitch relief outings whose single-game P+/S+/L+ are wildly
   noisy (observed `L+` of −110 and −173). With no sample-size
   down-weighting, the noisiest appearances rank *highest*: on the test
   slate the 20–29-pitch outings occupied ranks 1–10 while the
   76–99-pitch *starts* fell to 11–20. The score actively prefers noise.

4. **Early-season baseline degeneracy.** "This game vs season" is only
   meaningful once the season baseline has accumulated. In April the
   baseline is 1–2 prior starts, so the comparison is noise-vs-noise —
   and velocity signals went silent entirely (season velo ≈ game velo
   when the season is two outings old).

5. **Dead and silent signals.** `hard_hit_spike` (weight 1.5) is
   declared but never computed — there is no checker for it. `new_pitch`
   (weight 4.0, the *highest*) fired zero times in the test top-20. The
   two signals meant to carry the most weight contribute nothing.

6. **The curator inherits the noise and has no grounding guard.** In a
   live run the curator selected a 48-pitch reliever's `S+ 174 / L+ −110`
   sweeper and narrated it as a genuine "wipeout weapon" — taking the
   extreme `L+` at face value rather than flagging it as the small-sample
   artifact it almost certainly is, even though the prompt has an
   explicit Red Flag tier. Unlike the narrative pipeline, the curator has
   **no auditor, anchor, or hallucination check**, so noise that survives
   Stage 1 can be over-interpreted in Stage 2.

### Verdict

The daily funnel is the right design and is *partially* effective today:
the genuinely interesting pitchers do tend to reach the shortlist, so a
diligent reader of the full list is well served. But the **ranking** is
not trustworthy — it is dominated by signal volume and small-sample
noise — and the curator can launder that noise into confident prose. The
system is closer to "good candidate generation, unreliable
prioritization" than to "ranked watchlist."

## Why this matters more for a *daily* run

The failure modes above are amplified by the daily cadence:

- **Single games are the unit.** A daily run inherently looks at one
  outing, where P+/S+/L+ are least stable. A weekly or rolling-window
  scout would average out much of the small-sample noise that currently
  tops the board.
- **Relievers re-appear constantly.** A 20-pitch reliever can surface
  most days; without sample weighting, the same noisy arms churn through
  the top of the list.
- **The early season is structurally degenerate.** For the first few
  weeks the "season baseline" barely exists, so the whole vs-season
  premise is weak exactly when interest is highest.

## Recommended calibration (not yet implemented)

These mirror the fix already applied to the dead-zone signal
(`pitch-shape-arm-slot.md`), where a flat threshold that ignored
dispersion was replaced with a z-score against the real spread:

1. **Weight by effect size, not occurrence.** Scale each signal's
   contribution by how many SDs the change is, not a flat weight — a
   +4 mph jump should outscore a +1.5 mph blip.
2. **Down-weight thin samples.** Multiply the score by a sample-size
   factor (e.g. shrink toward zero below ~50 pitches) so a 22-pitch
   reliever's loud-but-noisy line cannot outrank a 95-pitch start.
3. **Collapse correlated signals.** Count "mix change" once, not once
   per pitch; treat correlated S+/L+ grade signals as one event.
4. **Gate on baseline maturity.** Suppress or discount vs-season signals
   until the baseline has enough prior outings; lean on prior-year or
   league baselines early in the season.
5. **Fix the dead signals.** Implement `hard_hit_spike` or remove its
   weight; diagnose why `new_pitch` never fires.
6. **Give the curator a grounding pass.** A lightweight check that
   flags physically implausible single-game values (an `L+` of −110) as
   likely artifacts before they become "wipeout weapon" prose.

None of these change the funnel — they make Stage 1's ranking honest and
keep Stage 2 from over-reading noise, which is what turns the daily run
from a candidate dump into a watchlist you can trust top-down.
