# Pitcher Narratives — Methodology

## Overview

Pitcher Narratives is an automated scouting report system that transforms raw pitch-tracking data into analytical capsules written in the voice of an elite sabermetric baseball analyst. The system uses a deterministic Python pipeline for all data computation and a two-phase LLM architecture that separates objective data extraction from editorial prose.

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

All engine outputs are assembled into a single `PitcherContext` Pydantic model. The model's `to_prompt()` method renders the data as a structured markdown document with nine sections:

1. **Executive Summary** — Bullet-point overview of key changes from the most recent appearance (velo trend, P+ trend, biggest usage shift, TTO summary, workload flags).
2. **Role** — Most recent role (SP/RP), appearance count, consecutive days pitched, workload concern flag.
3. **Primary Fastball** — Velocity, P+/S+/L+, movement deltas vs. season, velocity arc from last outing.
4. **Times Through Order** — Fastball/secondary P+ split table, per-pitch-type mix and P+ evolution across passes, platoon-within-TTO breakdown.
5. **Arsenal** — Top 4 pitch types by usage with usage deltas and P+ deltas vs. season.
6. **Execution** — CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 percentile per pitch type.
7. **Platoon Shifts** — Per-pitch-type usage and P+ by batter handedness with deltas.
8. **First-Pitch Tendencies** — Top 3 first-pitch types with recent vs. season usage.
9. **Recent Appearances** — Date, IP, pitch count, and rest days for each appearance in the window.

This document typically renders at 800-1,100 tokens depending on the pitcher's arsenal complexity. It serves as the sole data input to the LLM — the model receives no raw DataFrames, no CSV files, and no Statcast rows.

---

## Two-Phase LLM Architecture

The report generation pipeline uses two sequential LLM calls with distinct roles. This separation ensures the editorial phase never performs arithmetic — it receives pre-extracted findings and focuses entirely on interpretation and voice.

### Phase 1: The Data Synthesizer

**Role:** Objective data parser preparing a factual briefing for a senior writer.

**Input:** The full `to_prompt()` markdown document plus role-conditional analysis guidance (starter-specific or reliever-specific focus areas).

**Task:** Extract the signal from the noise. Identify the most significant changes — both improvements and declines — and organize them into a rigid structure. The synthesizer does not write prose, does not editorialize, and does not project future performance.

**Output format (enforced by prompt):**

```
## Fastball Quality & Velocity Trends
[Bulleted facts with baselines and deltas]

## Pitch Mix & Usage Shifts
[Largest positive and negative usage deltas, new/abandoned pitches]

## Execution & Outcomes
[CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 by pitch type]

## Platoon Splits
[Pitch mix and P+ disaggregated by batter handedness]

## Workload & Stamina
[Pitch counts, rest days, TTO degradation/improvement, IP trends]

## Key Signal
[The single most important improvement AND the single most important concern]
```

The rigid output format guarantees Phase 2 receives the same shape of input for every pitcher. The **Key Signal** section forces the synthesizer to commit to the two facts that should anchor the editorial.

**Role-conditional guidance:**
- **Starters** receive additional focus on TTO breakdown, pitch mix evolution across passes, platoon-specific TTO patterns, stamina trajectory, and new weapons.
- **Relievers** receive additional focus on rest day impact, put-away pitch identification, pitch count efficiency, platoon vulnerabilities, and workload trajectory.

**Why this phase exists:** LLMs produce higher-quality prose when freed from mathematical reasoning. By extracting all analytical building blocks in Phase 1, Phase 2 never needs to compute a delta, rank a percentile, or compare two numbers. This is the primary defense against hallucinated metrics.

### Phase 2: The Editor

**Role:** Elite, sabermetrically inclined baseball writer. Writes for front offices, advanced fantasy players, and data-driven fans. Tone is objective, mildly skeptical, and highly analytical.

**Input:** The structured briefing from Phase 1 (the synthesizer's bulleted output) plus the pitcher's name, handedness, and role.

**Task:** Weave the extracted facts into a tight, 2-3 paragraph scouting capsule following strict editorial guidelines.

**Structure — The Capsule:**

- **Paragraph 1 (The Setup):** Identifies the core change or current state of the stuff. New pitch? Velocity gain or drop? How are the raw shapes grading out? Grounds the reader in what is physically different about this pitcher right now.

- **Paragraph 2+ (The Verdict):** Explains how that stuff is playing in the zone. Addresses platoon splits directly. Highlights the glaring weakness or the path to sustained success. Delivers a definitive projection.

A third paragraph is permitted when the Setup needs separation (e.g., fastball changes and arsenal evolution each warrant their own paragraph before the Verdict).

**Editorial guidelines enforced by prompt:**

| Guideline | Description |
|-----------|-------------|
| **Anchor every metric** | Never state a velocity, P+ score, or usage rate without contextualizing it against the MLB average (100 for P+/S+/L+) or the pitcher's own baseline. |
| **Diagnose, don't just describe** | Connect outcomes to physical inputs. If strikeouts are up, explain it's tied to added break or a velocity gain. Link the "what" to the "why." |
| **Be skeptical** | Do not trust small samples blindly. Flag regression risks when results outpace underlying stuff metrics. Use language like "small-sample issues," "I'm not convinced," "prone to blow-ups." |
| **Platoon everything** | Treat the arsenal as two separate entities — how it works against lefties and how it works against righties. |
| **Take a stance** | End with a decisive, unsentimental projection. Assign a concrete tier: "a low 4s ERA arm," "a #5 starter," "profiles as a leverage reliever." No hedging. |
| **Voice constraints** | No clichés ("bulldog mentality," "pitches to contact," "electric stuff"). No negative comparison constructions ("not just X, it's Y"). State what something is — don't define it by what it isn't. Rely on K-BB%, SwStr%, CSW%, P+/S+/L+, xRV100. |
| **No fluff** | No introductory throat-clearing. Start immediately with the analysis. No bullet points, no headers, no tables in the output. |
| **Data fidelity** | Rely entirely on the briefing provided. Do not hallucinate metrics or trends. Ignore traditional outcome stats (ERA, W/L) in the body — base all analysis on underlying metrics. |

### Post-Generation Verification

After the editor produces the final capsule, a **metric hallucination guard** scans the output for metric-like patterns (xMetric, Acronym%, P+/S+/L+ family) and flags any term not present in a known-safe set. This catches cases where the LLM invents plausible-sounding metrics (e.g., "xDominance") to make a sentence flow better. Flagged terms are reported as warnings on stderr.

---

## Pipeline Summary

```
CLI Input (pitcher ID, window days)
    │
    ▼
Data Loading (Statcast parquet + 8 Pitching+ CSVs)
    │
    ▼
Filtering & Classification (window, SP/RP per appearance)
    │
    ▼
Computation Engine (7 analysis modules, all in Python)
    ├── Fastball Quality (velo, P+, movement, velocity arc)
    ├── Arsenal Analysis (usage rates, P+ per type)
    ├── Platoon Mix (per-type per-handedness)
    ├── First-Pitch Weaponry (count approach changes)
    ├── Execution Metrics (CSW%, zone/chase, xWhiff, xRV100)
    ├── Workload Context (rest days, IP, consecutive days)
    └── TTO Analysis (FB/sec split, pitch-type breakdown, platoon within TTO)
    │
    ▼
Context Assembly (PitcherContext Pydantic model → to_prompt() markdown)
    │
    ▼
Phase 1: Data Synthesizer (LLM extracts structured bullet findings)
    │
    ▼
Phase 2: Editor (LLM writes 2-3 paragraph analytical capsule)
    │
    ▼
Hallucination Guard (regex scan for unknown metrics)
    │
    ▼
Terminal Output (streamed capsule + stderr warnings if flagged)
```

Every number in the final report traces back through this pipeline to a specific Statcast column or Pitching+ aggregation. The LLM interprets and articulates — it does not compute.
