# Pitcher Narratives — Methodology

## Overview

Pitcher Narratives is an automated scouting report system that transforms raw pitch-tracking data into analytical capsules written in the voice of an elite sabermetric baseball analyst. The system uses a deterministic Python pipeline for all data computation and a four-phase LLM architecture that separates objective data extraction from editorial prose, social media distillation, and fantasy analysis.

No LLM performs arithmetic, computes deltas, or derives metrics. Every number in the final report originates from a pre-computed Python pipeline. The LLM's role is strictly interpretive: identify which findings are significant, then articulate why they matter.

---

## Data Sources

### Statcast Pitch-Level Data

**Source:** Baseball Savant (via `statcast_2026.parquet`)
**Grain:** One row per pitch thrown in MLB games
**Volume:** ~145,000 pitches across ~1,650 unique pitchers

Key columns used:

| Column | Purpose |
|--------|---------|
| `release_speed` | Pitch velocity |
| `pfx_x`, `pfx_z` | Horizontal and vertical movement (inches) |
| `pitch_type` | Pitch classification (FF, SI, SL, CH, etc.) |
| `zone` | Location zone (1-9 = strike zone, 11-14 = chase zones) |
| `description` | Pitch outcome (called_strike, swinging_strike, ball, etc.) |
| `stand` | Batter handedness (L/R) |
| `inning` | Inning of appearance |
| `n_thruorder_pitcher` | Times through the order (1st, 2nd, 3rd pass) |
| `pitch_number` | Sequential pitch number within at-bat |
| `game_pk`, `game_date` | Game identifier and date |
| `pitcher`, `player_name` | Pitcher identifier and name |

### Pitching+ Aggregations

**Source:** Pre-computed model outputs (via `aggs/*.csv`)
**Metric family:** P+ (Pitching+), S+ (Stuff+), L+ (Location+) — scaled to 100 = MLB average

Available at eight grains:

| File | Grain | Use |
|------|-------|-----|
| `2026-pitcher.csv` | Season per pitcher | Season baselines |
| `2026-pitcher_type.csv` | Season per pitcher per pitch type | Per-pitch baselines |
| `2026-pitcher_appearance.csv` | Per game per pitcher | Game-level trends |
| `2026-pitcher_type_appearance.csv` | Per game per pitcher per pitch type | Per-pitch game trends |
| `2026-pitcher_type_platoon.csv` | Season per pitcher per pitch type per platoon | Platoon baselines |
| `2026-pitcher_type_platoon_appearance.csv` | Per game per pitcher per pitch type per platoon | Platoon game trends |
| `2026-all_pitches.csv` | Individual pitch | Pitch-level P+/S+/L+ scores |
| `2026-team.csv` | Team season | League-level context |

Additional metrics in each file: xRV100 (expected run value per 100 pitches), xWhiff (expected whiff probability), xSwing (expected swing probability), xGOr (expected ground out rate), xPUr (expected pop up rate), and 20-80 scouting scale variants (P+2080, S+2080, L+2080).

**Join key:** `pitcher` (integer MLB player ID) is shared across all files.

---

## Data Pipeline

### Loading and Filtering

1. **Statcast parquet** is loaded and filtered to the target pitcher by ID.
2. **All eight CSV aggregation files** are loaded, dates are parsed from string to Date type, and each is filtered to the target pitcher (where applicable — `team.csv` is loaded unfiltered for league context).
3. **Appearances** are identified from the per-game aggregation file, providing the list of games the pitcher appeared in.

### Lookback Window

The system accepts a configurable lookback window in days (default: 30). The window is computed relative to the **most recent date in the dataset** (not the current calendar date), ensuring consistent behavior against static data files. Appearances within the window form the "recent" sample; the full season forms the baseline.

### Starter/Reliever Classification

Each appearance is classified independently — not the pitcher as a whole. A pitcher who starts one game and relieves in the next gets correct per-appearance labels.

**Heuristic:** If the pitcher's first inning in a game is inning 1, the appearance is classified as a Start (SP). Otherwise, it is classified as Relief (RP). This correctly handles openers (classified as SP regardless of innings pitched) and swingmen who move between roles.

### Season Baselines

Season baselines are computed from the season-level aggregation files (`pitcher.csv`, `pitcher_type.csv`). When a pitcher has rows across multiple game types (e.g., spring training and regular season), baselines are computed as **n_pitches-weighted averages** across game types — not simple means. This prevents a 5-pitch regular season row from equally weighting against a 200-pitch spring training row.

---

## Computation Engine

All computation is performed in Python using polars DataFrames. The engine produces structured dataclass outputs with pre-computed qualitative trend strings. The LLM never receives raw numbers without context — every metric is accompanied by its baseline and a human-readable delta description.

### Delta String Vocabulary

Deltas are classified by magnitude:

| Type | Threshold | "Steady" | "Up/Down" | "Sharply" |
|------|-----------|----------|-----------|-----------|
| Velocity | 0.5 mph | Below threshold | 0.5-2.0 mph | Above 2.0 mph |
| P+/S+/L+ | 5 points | Below threshold | 5-10 points | Above 10 points |
| Usage rate | 5 percentage points | Below threshold | 5-10pp | Above 10pp |
| Movement | 0.5 inches | Below threshold | 0.5+ inches | — |

Example outputs: "Down 1.2 mph", "Up sharply (+15 points)", "Steady (+0.3)".

When the lookback window covers the entire season (no baseline comparison possible), the string reads: "Full season in window — no trend comparison."

### Minimum Sample Size

Per-pitch-type analyses require a minimum of 10 pitches of that type within the window. Below this threshold, the analysis is still included but flagged with `small_sample: true`. The LLM receives this flag so it can appropriately caveat its conclusions.

### Fastball Quality Analysis

1. **Primary fastball identification:** The highest-usage pitch among fastball types (FF four-seam, SI sinker, FC cutter) from the season baseline.
2. **Velocity trend:** Season average velocity vs. window average velocity, with delta string.
3. **P+/S+/L+ trend:** Season baseline vs. window average for each metric, with delta strings.
4. **Movement trend:** Season pfx_x (horizontal) and pfx_z (vertical) vs. window averages, with delta strings.
5. **Within-game velocity arc:** For the most recent appearance, compares average velocity in the first two innings vs. the last two innings. Single-inning appearances report "Held steady" or are marked unavailable.

### Arsenal Analysis

For each pitch type (top 4 by season usage):

1. **Usage rate:** Window usage percentage and delta vs. season baseline.
2. **P+/S+/L+:** Window average and delta vs. season baseline.
3. **Cold start detection:** When the window covers the full season, delta strings are replaced with "Full season in window."

### Platoon Mix Analysis

For each pitch type and platoon matchup (same-hand vs. opposite-hand):

1. **Usage percentage** against each batter handedness.
2. **P+ score** against each batter handedness.
3. Missing combinations (e.g., a changeup never thrown to same-side batters) are flagged with `available: false`.

Platoon matchup is derived from the pitcher's throwing hand (`p_throws`) and the batter's stance (`stand`): same hand = "same", different hand = "opposite".

### First-Pitch Weaponry

Identifies which pitch types are used on the first pitch of each at-bat (`pitch_number == 1` in Statcast data). Compares recent window distribution to season distribution, surfacing changes in approach (e.g., a pitcher shifting from fastball-first to slider-first in early counts).

### Execution Metrics

For each pitch type in the recent window:

1. **CSW% (Called + Swinging Strike Rate):** Counts of `called_strike`, `swinging_strike`, and `swinging_strike_blocked` descriptions divided by total pitches.
2. **Zone Rate:** Percentage of pitches landing in zones 1-9 (strike zone).
3. **Chase Rate (O-Swing%):** Percentage of pitches outside the zone (zones 11-14) that generated a swing.
4. **xWhiff and xSwing:** Expected whiff and swing probabilities from the Pitching+ model.
5. **xRV100 Percentile:** The pitcher's expected run value per 100 pitches for each pitch type, ranked as a percentile against all MLB pitchers with at least 10 pitches of that type in the season.

### Workload Context

1. **Rest days:** Calendar days between consecutive appearances (date arithmetic on sorted game dates).
2. **Innings pitched:** Counted from unique (game_pk, inning) pairs in Statcast data, with partial innings derived from recorded outs.
3. **Pitch count:** Total pitches per appearance (row count in Statcast per game).
4. **Consecutive days pitched:** Maximum streak of consecutive calendar days with appearances. A streak of 3+ triggers a workload concern flag for relievers.

### Hard-Hit Rate

Computes the percentage of batted balls with exit velocity >= 95 mph from Statcast data. Compares the window hard-hit rate against the season baseline with standard delta strings. Batted balls are identified by the presence of a non-null `launch_speed` column. Small samples (fewer than 10 batted balls in the window) are flagged.

### Release Point Mechanics

For each pitch type, computes the mean release position (horizontal `release_pos_x`, vertical `release_pos_z`) and extension (`release_extension`) within the window vs. the pitcher's own season baseline. All baselines are pitcher-specific, pitch-type-by-pitch-type — never league averages.

Delta strings use the same vocabulary as other metrics. Uniform shifts across all pitch types suggest a delivery change, fatigue, or potential injury. A shift in one pitch type suggests tinkering with that offering. The LLM receives explicit guidance to interpret release point data in this mechanical context.

### Times Through Order (TTO)

Joins Statcast (which carries `n_thruorder_pitcher`) with the `all_pitches.csv` (which carries per-pitch P+/S+) on `(pitcher, game_pk, pitch_number)`. Computes three levels of analysis:

**Level 1 — Fastball vs. Secondary P+ Split:**
For each TTO pass, computes separate P+ averages for fastball types (FF/SI/FC) and secondary types (all others). This isolates whether stuff degradation is driven by fastball decline or secondary pitch decline.

**Level 2 — Per-Pitch-Type Breakdown:**
For each TTO pass, computes usage percentage and P+ for every pitch type thrown. Includes usage deltas vs. pass 1 (e.g., "CH usage +21pp by pass 3") and P+ deltas vs. pass 1 (e.g., "FF P+ down 24 points").

**Level 3 — Platoon Within TTO:**
For each TTO pass, breaks out pitch mix and P+ by batter handedness. Identifies platoon-specific TTO patterns (e.g., a pitcher who drops his sinker entirely against LHB by the third pass).

**Mix Shift Detection:**
Automatically flags pitch types whose usage changed by 10+ percentage points between pass 1 and the final pass, and pitches that were abandoned entirely (present in pass 1, absent in later passes with >= 10% original usage).

**Small Sample Caveat:**
TTO passes with fewer than 50 total pitches are flagged in the output so the LLM can appropriately weight its conclusions.

---

## Context Assembly

All engine outputs are assembled into a single `PitcherContext` Pydantic model. The model's `to_prompt()` method renders the data as a structured markdown document with eleven sections:

1. **Executive Summary** — Bullet-point overview of key changes from the most recent appearance (velo trend, full P+/S+/L+ triad, biggest usage shift, TTO summary, hard-hit rate shift, workload flags).
2. **Role** — Most recent role (SP/RP), appearance count, consecutive days pitched, workload concern flag.
3. **Primary Fastball** — Velocity, P+/S+/L+ triad with deltas vs. season, movement deltas, velocity arc from last outing.
4. **Times Through Order** — Fastball/secondary P+ split table, per-pitch-type mix and P+ evolution across passes, platoon-within-TTO breakdown.
5. **Arsenal** — Top 4 pitch types by usage with usage deltas and P+/S+/L+ columns with deltas vs. season.
6. **Execution** — CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 percentile per pitch type.
7. **Release Point Mechanics** — Per-pitch-type release x/z/extension with deltas vs. pitcher's own season baseline.
8. **Contact Quality** — Hard-hit rate (window vs. season) with delta string.
9. **Platoon Shifts** — Per-pitch-type usage and P+ by batter handedness with deltas.
10. **First-Pitch Tendencies** — Top 3 first-pitch types with recent vs. season usage.
11. **Recent Appearances** — Date, IP, pitch count, and rest days for each appearance in the window.

The Pitching+ triad (P+, S+, L+) is surfaced throughout — in the executive summary, fastball section, and arsenal table — so the LLM can distinguish between stuff changes (S+) and command changes (L+).

This document typically renders at 900-1,200 tokens depending on the pitcher's arsenal complexity. It serves as the sole data input to the LLM — the model receives no raw DataFrames, no CSV files, and no Statcast rows.

---

## Appearance Scout

Before generating full reports, the scout identifies which appearances are worth writing about. It runs entirely in Python — no LLM calls — scoring each appearance against the pitcher's season baselines across 9 signal types.

### Signal Detection

| Signal | Weight | Threshold | Description |
|--------|--------|-----------|-------------|
| `new_pitch` | 4.0 | >5% game usage, <1% season usage | Pitch type newly appearing in the repertoire |
| `development_opportunity` | 3.5 | S+ >110, L+ <80 | High stuff with poor command — the "missing piece" pattern |
| `velo_delta` | 3.0 | >= 1.5 mph from season | Fastball velocity gain or loss |
| `splus_lplus_divergence` | 3.0 | >= 10 pts each, opposite directions | Stuff improving while command slips, or vice versa |
| `dropped_pitch` | 3.0 | >= 10% season usage, 0% game usage | Established pitch completely shelved |
| `pplus_swing` | 2.5 | >= 15 pts from season | Overall P+ spike or collapse |
| `walk_rate_pplus_contradiction` | 2.5 | P+ >= 105 with L+ < 85 | Good stuff without command (the Cavalli pattern) |
| `usage_shift` | 2.0 | >= 8pp from season | Pitch type usage change |
| `workload_flag` | 1.0 | 3+ consecutive days | Reliever workload concern |

The scout loads appearance-level and season-level aggregation CSVs, computes velocity baselines from the Statcast parquet, and scores each appearance by summing the weights of all signals that fire. A typical game day produces 15-30 appearances above a score of 5.0.

### LLM Curator

With `--curate`, the scored list is sent to an LLM for editorial selection. The curator uses a four-tier signal hierarchy:

1. **Clean Breakout** — velocity gain coupled with stuff improvement (strongest signal)
2. **Lab Project** — top-tier raw stuff (S+ 130+) with poor command (L+ < 80)
3. **Identity Crisis** — radical pitch mix changes (shelving primaries, doubling secondaries)
4. **Red Flag** — statistical anomalies that may be tracking errors (3+ mph velo spikes)

The curator selects 3-5 pitchers, writes a brief for each (signal, narrative, conviction score), names 2-3 worth tracking, and explains why every other pitcher was excluded.

---

## Four-Phase LLM Architecture

The report generation pipeline uses four sequential LLM calls with distinct roles. Phase 1 extracts facts; Phase 2 writes the capsule; Phases 3 and 4 derive from the capsule (not the raw synthesis), inheriting the editor's plausibility filters and metric curation.

Three LLM providers are supported: OpenAI (gpt-5.4-mini), Anthropic (claude-sonnet-4-6), and Google (gemini-3.1-pro-preview). Provider-specific thinking configuration is handled automatically.

### Phase 1: The Data Synthesizer

**Role:** Objective data parser preparing a factual briefing for a senior writer.

**Input:** The full `to_prompt()` markdown document plus role-conditional analysis guidance (starter-specific or reliever-specific focus areas).

**Task:** Extract the signal from the noise using three analytical lenses: breakout indicators, regression risks, and development opportunities. The synthesizer audits the arsenal as a portfolio — cross-referencing stuff quality (S+) with command (L+) and platoon splits. It does not write prose, does not editorialize, and does not project future performance.

**Key analytical instructions:**

- **Intent-based reasoning:** Before attributing usage shifts to fatigue or mechanical causes, check whether the opposing lineup's handedness mix explains the pattern. Frame opponent-driven patterns as game plans, not mechanical byproducts.
- **Portfolio audit:** High S+ / low L+ pitches are flagged as development opportunities and cross-referenced with platoon data to identify which pitch would most change the pitcher's projection.
- **Plausibility filter:** Velocity outliers (>3 mph) are flagged as possible misclassification. Command contradictions (high L+ with high walk rate) are reframed as pitch-level targeting, not overall command.

**Output format (enforced by prompt):**

```
## Fastball Quality & Velocity Trends
## Pitching+ Profile
## Pitch Mix & Usage Shifts
## Execution & Outcomes
## Platoon Splits
## Release Point Mechanics
## Workload & Stamina
## Opponent Context & Intent
## Key Signal
    - Most important improvement
    - Most important concern
    - Development pitch (high-S+/low-L+ that would solve a platoon weakness)
```

**Role-conditional guidance:**
- **Starters** receive additional focus on TTO breakdown, pitch mix evolution across passes, platoon-specific TTO patterns, stamina trajectory, and new weapons.
- **Relievers** receive additional focus on rest day impact, put-away pitch identification, pitch count efficiency, platoon vulnerabilities, and workload trajectory.

**Why this phase exists:** LLMs produce higher-quality prose when freed from mathematical reasoning. By extracting all analytical building blocks in Phase 1, Phase 2 never needs to compute a delta, rank a percentile, or compare two numbers. This is the primary defense against hallucinated metrics.

### Phase 2: The Editor

**Role:** Elite, sabermetrically inclined baseball writer. Writes for front offices, advanced fantasy players, and data-driven fans. Tone is pragmatic, cautious, and highly analytical.

**Input:** The structured briefing from Phase 1 (the synthesizer's bulleted output) plus the pitcher's name, handedness, and role.

**Task:** Find the narrative thread, then weave the extracted facts into a tight, 2-3 paragraph scouting capsule. The editor reorganizes the synthesizer's category-based structure by narrative importance — leading with whatever is most interesting, not walking through fastball→secondary→platoon→conclusion.

**Structure — The Capsule:**

- **Paragraph 1 (The Setup):** Tells the reader what is different about this pitcher right now. Leads with what happened — the concrete change — not with a theory about why it happened or what didn't change. The "why" comes after the "what" is established.

- **Paragraph 2+ (The Verdict):** Explains how the stuff is playing in practice. Weaves in platoon splits where they matter to the story. Delivers a clear-eyed conclusion on the pitcher's current trajectory.

**Editorial guidelines enforced by prompt:**

| Guideline | Description |
|-----------|-------------|
| **Three primary metrics** | Choose at most three metrics to carry the narrative. Everything else stays in the briefing. |
| **Link mechanics to outcomes** | Every mechanical observation (extension, release point) must immediately connect to a tactical result. No orphaned mechanical details. |
| **Diagnose, don't just describe** | Connect outcomes to physical inputs. Link the "what" to the "why." |
| **Consider intent — lightly** | When data shows usage shifts, consider whether the opposing lineup explains the pattern before defaulting to fatigue. But don't build a theory around every mix change — sometimes a pitcher just threw more changeups. Mention intent as a possibility, never as a confident conclusion from one game. |
| **Scale confidence to sample** | Three starts get "trending toward." A full season supports firmer assessments. No declaring what a pitcher "profiles as" from a handful of appearances. |
| **L+ is not command** | L+ measures pitch-level placement, not overall command. High L+ with high walks = precise targeting on one pitch, not a guy in command of the zone. Always pair L+ with walk rate. |
| **Voice** | Write like an analyst talking to another analyst. Conversational scouting language (stuff, feel, finding a groove, getting tagged). No clinical jargon (degradation, binary, mathematical liability). No formulaic transitions (Meanwhile, However). Vary sentence length. |
| **Word bans** | Never use: degradation, binary, physical characteristics, extreme variance, profiles as, metrics are grim, navigating a lineup, elite, dominant, massive spike. |
| **Spot-check** | Before finishing, verify: metric count <= 3, all mechanics link to outcomes, confidence matches sample size, any "command" claim is backed by walk rate. Then read the capsule as a reader: does it lead with what happened or with a theory about why? If more words explain the mechanism than describe the change, rebalance. Never open with what is NOT happening. |
| **No fluff** | No introductory throat-clearing. Start immediately with the analysis. No bullet points, no headers, no tables in the output. |
| **Data fidelity** | Rely entirely on the briefing provided. Do not hallucinate metrics or trends. Be direct without being dismissive or alarmist. |

### Phase 3: The Hook Writer

**Role:** Wire-service headline writer crafting a single social media post.

**Input:** The pitcher's name, handedness, role, and the editor's capsule (Phase 2 output).

**Task:** Write one sentence — headline-length, under 280 characters — that captures the single most important change, trend, or signal. Name the pitcher, name the pitch or metric, state the direction.

**Constraints:** One sentence only. No run-on sentences joined by dashes or semicolons. No hashtags, emojis, or hype. Must stand alone without context.

### Phase 4: The Fantasy Analyst

**Role:** Fantasy baseball analyst writing in news-wire voice for competitive league managers.

**Input:** The pitcher's name, handedness, role, and the editor's capsule (Phase 2 output).

**Task:** Write exactly 3 bullet points — Axios-style: short, declarative, news-first. Lead with the fact or trend, then explain why it matters for fantasy. Each bullet cites one specific metric.

**Voice:** Analyst reporting news, not manager issuing roster moves. Frame implications as things to monitor ("keep an eye on," "worth watching") rather than directives ("pick him up," "move him to the bench"). No bold labels, no verdict prefixes. Plain text bullets.

### Phase 2.5: The Anchor Check

**Role:** Fact-checker verifying the capsule is faithful to the synthesis.

**Input:** The synthesis (Phase 1 output) and the capsule (Phase 2 output).

**Task:** Compare the two documents and flag specific problems:

| Check | What it catches |
|-------|-----------------|
| **Missed key signal** | The synthesis flagged something in Key Signal but the capsule ignored it entirely |
| **Unsupported claim** | The capsule states a metric or trend not present in the synthesis |
| **Directional error** | The synthesis says a metric went up but the capsule says it went down |
| **Overstated confidence** | The synthesis notes small sample but the capsule presents it as definitive |

**Output:** Either `CLEAN` (no issues) or one line per issue with a bracketed type prefix. Warnings are printed to stderr in the CLI alongside the hallucination guard.

**Why this phase exists:** The editor is already doing a lot of self-auditing (spot-check #10), but asking a writer to verify their own factual accuracy is like asking them to proofread their own work. A separate persona reading the synthesis and capsule together catches signal drift that the editor's self-check misses — for example, the synthesizer flagging the sinker as the development pitch while the editor builds the narrative around the changeup and barely mentions it.

### Data Flow

The anchor check runs after the editor and before Phases 3/4. Phases 3 and 4 receive the editor's capsule — not the raw synthesis — so they inherit the editor's three-metric curation, plausibility filters, L+/walk-rate reframing, and confidence scaling.

```
Phase 1 (Synthesis) ──→ Phase 2 (Editor/Capsule) ──→ Phase 2.5 (Anchor Check)
                                                  ──→ Phase 3 (Hook)
                                                  ──→ Phase 4 (Fantasy)
```

### Prompt Caching

CachePoint markers are inserted at strategic boundaries in the user messages to enable prompt caching across phases and across pitchers in batch runs:

- **Phase 1:** Cache breakpoint after role guidance (stable across all pitchers of the same role).
- **Phase 2:** Cache breakpoint after the synthesis output.
- **Phase 2.5:** Cache breakpoint after the synthesis (shared prefix with Phase 2).
- **Phases 3, 4:** Cache breakpoint after the capsule (shared across both downstream phases for the same pitcher).

On Anthropic, these translate to explicit `cache_control` headers. On OpenAI, automatic prefix caching benefits from the same structure. On Gemini, CachePoints are silently ignored.

### Post-Generation Verification

After the editor produces the final capsule, a **metric hallucination guard** scans the narrative for metric-like patterns (xMetric, Acronym%, P+/S+/L+ family) and flags any term not present in a known-safe set. It also detects traditional outcome stats (ERA, WHIP, W-L) that the editor prompt warns against citing. Flagged terms are reported as warnings on stderr.

---

## Pipeline Summary

```
                    ┌─────────────────────────────────────────────┐
                    │          SCOUT (pitcher-scout)              │
                    │                                             │
                    │  Appearance CSVs + Statcast                 │
                    │      │                                      │
                    │      ▼                                      │
                    │  9 signal checkers (pure Python)            │
                    │      │                                      │
                    │      ▼                                      │
                    │  Scored + ranked appearances                │
                    │      │                                      │
                    │      ▼ (--curate)                           │
                    │  LLM Curator (select 3-5 stories)          │
                    └─────────────────────────────────────────────┘
                                       │
                          pitcher IDs worth writing about
                                       │
                                       ▼
                    ┌─────────────────────────────────────────────┐
                    │     NARRATIVE BUILDER (pitcher-narratives)  │
                    │                                             │
                    │  Statcast parquet + 8 Pitching+ CSVs        │
                    │      │                                      │
                    │      ▼                                      │
                    │  Computation Engine (9 analysis modules)    │
                    │      │                                      │
                    │      ▼                                      │
                    │  Context Assembly (~1000 tokens markdown)   │
                    │      │                                      │
                    │      ▼                                      │
                    │  Phase 1: Synthesizer                       │
                    │      │                                      │
                    │      ▼                                      │
                    │  Phase 2: Editor (capsule, streamed)        │
                    │      │                                      │
                    │      ▼                                      │
                    │  Phase 2.5: Anchor Check (verify fidelity)  │
                    │      │                                      │
                    │      ├──▶ Phase 3: Hook Writer              │
                    │      └──▶ Phase 4: Fantasy Analyst          │
                    │      │                                      │
                    │      ▼                                      │
                    │  Hallucination Guard + Output               │
                    └─────────────────────────────────────────────┘
```

Every number in the final report traces back through this pipeline to a specific Statcast column or Pitching+ aggregation. The LLM interprets and articulates — it does not compute.
