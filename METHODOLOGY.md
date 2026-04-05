# Pitcher Narratives — Methodology

## Overview

Pitcher Narratives is an automated scouting report system that transforms raw pitch-tracking data into analytical capsules written in the voice of an elite sabermetric baseball analyst. The system offers two report generation architectures — a simple four-phase pipeline and a multi-specialist parallel pipeline — both sharing the same data pipeline, context assembly, and anchor check infrastructure. Three CLI tools: `pitcher-narratives` (reports), `pitcher-scout` (appearance scanning), `pitcher-ask` (Q&A).

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

### League Baselines

The engine computes league-wide mean and standard deviation for key metrics (velocity, pfx_x, pfx_z, S+, xWhiff_S, xRV100_S) per pitch type from all pitchers in the season data. Each pitcher's values are then pre-tagged as NORMAL (within 1.5 stddev) or OUTLIER. Both pipelines and the Q&A analyst use these annotations as an anti-hallucination guardrail — the LLM never needs to compute z-scores because every metric arrives pre-annotated.

### Intermediate Probabilities

Per-pitch-type S-variant (stuff-only) model predictions: xSwing_S, xWhiff_S, xSwSt_S, xRV100_S. These isolate what the pitch's physical characteristics (velocity + movement) produce independent of location. The P-vs-S delta for each metric quantifies location's contribution. Feeds the Model Internals context section and the location/stuff specialist agents.

### Component Attribution

Per-pitch-type xRV100 decomposition into 13 outcome contributions (called_strike, swinging_strike, ball, foul, single, double, triple, home_run, etc.). Each outcome's contribution is signed: negative = pitcher benefits, positive = costs runs. Feeds the run value specialist in the multi-specialist pipeline.

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

All engine outputs are assembled into a single `PitcherContext` Pydantic model. The model's `to_prompt()` method renders the data as a structured markdown document with twelve sections:

1. **Executive Summary** — Bullet-point overview of key changes from the most recent appearance (velo trend, full P+/S+/L+ triad, biggest usage shift, TTO summary, hard-hit rate shift, workload flags).
2. **Role** — Most recent role (SP/RP), appearance count, consecutive days pitched, workload concern flag.
3. **Primary Fastball** — Velocity, P+/S+/L+ triad with deltas vs. season, movement deltas, velocity arc from last outing.
4. **Times Through Order** — Fastball/secondary P+ split table, per-pitch-type mix and P+ evolution across passes, platoon-within-TTO breakdown.
5. **Arsenal** — Top 4 pitch types by usage with usage deltas and P+/S+/L+ columns with deltas vs. season.
6. **Execution** — CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 percentile per pitch type.
7. **Model Internals: Location Impact** — S-variant (stuff-only) probabilities and P-vs-S deltas per pitch type. Isolates what location contributes beyond the pitch's physical profile.
8. **Release Point Mechanics** — Per-pitch-type release x/z/extension with deltas vs. pitcher's own season baseline.
9. **Contact Quality** — Hard-hit rate (window vs. season) with delta string.
10. **Platoon Shifts** — Per-pitch-type usage and P+ by batter handedness with deltas.
11. **First-Pitch Tendencies** — Top 3 first-pitch types with recent vs. season usage.
12. **Recent Appearances** — Date, IP, pitch count, and rest days for each appearance in the window.

Component attribution data (13-outcome xRV100 decomposition per pitch type) is available on the `PitcherContext` model as `attributions` but is not rendered by `to_prompt()` — it is consumed directly by the multi-specialist pipeline's data builders.

The Pitching+ triad (P+, S+, L+) is surfaced throughout — in the executive summary, fastball section, and arsenal table — so the LLM can distinguish between stuff changes (S+) and command changes (L+).

This document typically renders at 900-1,200 tokens depending on the pitcher's arsenal complexity. It serves as the sole data input to the LLM — the model receives no raw DataFrames, no CSV files, and no Statcast rows.

---

## Appearance Scout

Before generating full reports, the scout identifies which appearances are worth writing about. It runs entirely in Python — no LLM calls — scoring each appearance against the pitcher's season baselines across 10 signal types.

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
| `hard_hit_spike` | 1.5 | (defined, not yet implemented) | Hard-hit rate anomaly |
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

## Report Pipelines

The system offers two report generation architectures selected via the `--pipeline` CLI flag. Both share the same data pipeline, context assembly, and anchor check infrastructure.

Three LLM providers are supported, each with a Pro and Mini model tier:

| Provider | Pro (Writer/Stuff) | Mini (Specialists/Checkers) |
|----------|--------------------|-----------------------------|
| OpenAI | gpt-5.4 | gpt-5.4-mini |
| Anthropic | claude-sonnet-4-6 | claude-haiku-4-5 |
| Google | gemini-3.1-pro-preview | gemini-flash-latest |

Pro-tier models handle roles where reasoning and prose quality matter (writer, editor, stuff specialist, stuff explainer, answerer). Mini-tier models handle high-volume structured tasks (location/runvalue/trends/game-shape specialists, auditor, anchor, synthesizer, executive summary). Provider-specific thinking configuration is handled automatically.

### Simple Pipeline (report.py)

The original architecture. Four LLM phases with a fact-checking reflection loop.

**Phase 1: The Synthesizer** (Mini tier, temp=0.3)

Objective data parser preparing a factual briefing for a senior writer. Receives the full `to_prompt()` markdown plus role-conditional analysis guidance (starter/reliever focus areas) and league baselines with S-variant comparisons.

Extracts signal from noise using three analytical lenses: breakout indicators, regression risks, and development opportunities. Audits the arsenal as a portfolio — cross-referencing stuff quality (S+) with command (L+) and platoon splits. Does not write prose or editorialize.

Key analytical instructions: intent-based reasoning (check lineup handedness before attributing usage shifts to fatigue), portfolio audit (high S+ / low L+ = development opportunity), plausibility filter (>3 mph velo outliers flagged as possible misclassification).

Output: 9 structured sections (Fastball Quality, Pitching+ Profile, Pitch Mix, Execution, Platoon Splits, Release Point, Workload & Stamina, Opponent Context, Key Signal with 3 bullets). Role-conditional appendix: starters get TTO/stamina focus, relievers get rest/workload focus.

**Phase 2: The Editor** (Pro tier, temp=0.7)

Elite sabermetric baseball writer. Finds the narrative thread and weaves the synthesis into a tight, 2-3 paragraph capsule. Reorganizes by narrative importance — leads with what's most interesting, not a category walk-through.

Editorial guidelines enforced by prompt: three-metric maximum, link mechanics to outcomes, diagnose root causes, consider intent lightly, scale confidence to sample, L+ is not command (pair with walk rate), conversational scouting voice, word bans (degradation, binary, elite, dominant, etc.), spot-check before finishing, no fluff, data fidelity.

**Phase 2.5: Anchor Check + Reflection Loop** (shared with multi-specialist pipeline — see below)

**Phase 3: Stuff Explainer** (Pro tier, temp=0.3)

Traces each pitch's S+ grade to its physical profile via stuff-only model predictions. Receives synthesis + league baselines + S-variant data. Output: one paragraph covering 2-3 most notable pitches.

**Executive Summary** (Mini tier, temp=0.3)

Concise metrics-focused bullets for front office readers. Exactly 3 bullet points, each citing a specific metric. Directional consistency enforced.

**Data Flow:**
```
Context → Synthesizer → Editor → Anchor Check ─┬─ Stuff Explainer
                                                └─ Executive Summary
```

### Multi-Specialist Pipeline (pipeline.py)

Parallel architecture selected via `--pipeline` flag. Decomposes the synthesizer's job into five specialist agents, each receiving tailored data inputs with pre-computed NORMAL/OUTLIER annotations.

**Phase 1: Five Specialist Agents (parallel)**

Each specialist receives a custom data build from the PitcherContext — not the raw `to_prompt()` output. Data builders (`_build_stuff_input`, `_build_location_input`, `_build_runvalue_input`, etc.) pre-annotate every metric with its delta from league average and an explicit NORMAL/OUTLIER z-score tag.

1. **Stuff Specialist** (Pro tier, temp=0.3) — Traces velocity and movement shape to S+ grades via S-variant predictions. Rules: respect NORMAL/OUTLIER tags, directional consistency, xWhiff reconciliation, citation required for all behavioral claims.

2. **Location Specialist** (Mini tier, temp=0.3) — Isolates location impact by comparing P-variant (stuff + location) vs S-variant (stuff only) predictions. Zone rate and chase rate against league baselines.

3. **Run Value Specialist** (Mini tier, temp=0.3) — Reads 13-outcome component attribution per pitch type. Identifies 2-3 dominant outcome contributors. Sign convention: negative = pitcher benefits.

4. **Trend Specialist** (Mini tier, temp=0.3) — Window-vs-season deltas in velocity, grades, usage, movement, release point, hard-hit rate. Does NOT analyze within-game patterns.

5. **Game Shape Specialist** (Mini tier, temp=0.3) — Within-game effectiveness: TTO splits, velocity arc, mix shifts by pass, platoon-specific TTO patterns, workload. Does NOT analyze window-vs-season trends.

**Phase 1.5: Per-Specialist Audit + Revision (parallel)**

Each specialist's output is audited independently against the raw data it received. Five audits run in parallel. The auditor (Mini tier, temp=0.1, retries=3) checks 7 categories:

| Category | What it catches |
|----------|-----------------|
| METRIC_CONTRADICTION | Calling a NORMAL-tagged metric unusual |
| DIRECTION_ERROR | Saying good when data says bad |
| SIGN_INCONSISTENCY | S+ vs xRV100_S narrative mismatch |
| UNRECONCILED_STRENGTH | Ignoring xWhiff >= 25% |
| HALLUCINATED_CAUSATION | Invented mechanism not in data |
| FABRICATED_DATA | Cited number not in input |
| UNCITED_BEHAVIORAL_CLAIM | Hitter behavior claim without metric citation |

Flagged specialists are re-run with their original input + audit corrections. The writer never sees flawed prose.

**Phase 2: Writer + Executive Summary (parallel)**

The writer (Pro tier, temp=0.7) receives all 5 clean specialist outputs and composes a unified 2-3 paragraph capsule. Same editorial voice and constraints as the simple pipeline's editor, but input is specialist analyses rather than a single synthesis. Key instruction: specialists are ingredients, not sections to preserve. Find one thread across all five.

Executive summary (Mini tier, temp=0.3) runs concurrently — same format as simple pipeline (3 bullets citing specific metrics), sourced from specialist outputs.

**Phase 2.5: Anchor Check + Reflection Loop** (shared infrastructure — see below)

**Data Flow:**
```
Context → Data Builders → 5 Specialists (parallel)
                              ↓
                        5 Audits (parallel)
                              ↓
                        Revisions (flagged only)
                              ↓
                    Writer + Exec Summary (parallel)
                              ↓
                        Anchor Check
```

### Shared Infrastructure

#### Anchor Check + Reflection Loop

Both pipelines use the same anchor check implementation (anchor.py). The anchor agent (Mini tier, temp=0.1) receives the synthesis/specialist outputs and the capsule, then flags specific problems:

| Check | What it catches |
|-------|-----------------|
| **`MISSED_SIGNAL`** | The synthesis flagged something in Key Signal but the capsule ignored it entirely |
| **`UNSUPPORTED`** | The capsule states a metric or trend not present in the synthesis |
| **`DIRECTION_ERROR`** | The synthesis says a metric went up but the capsule says it went down |
| **`OVERSTATED`** | The synthesis notes small sample but the capsule presents it as definitive |

**Output:** A structured `AnchorResult` Pydantic model containing a list of typed `AnchorWarning` objects (each with a `category` from the four types above and a `description`). The `is_clean` property returns `True` when no warnings exist.

**Reflection loop:** If the anchor returns warnings, the editor receives a targeted revision prompt and silently rewrites the capsule. The anchor then re-checks. This repeats up to `MAX_REVISIONS` (default: 3) times, for a maximum of 4 total passes (first draft + 3 revisions).

```
Editor (streamed) → Anchor Check
                     ├─ CLEAN → proceed to downstream phases
                     └─ warnings → Editor revises (silent)
                                   → Anchor re-checks
                                   ├─ CLEAN → proceed
                                   └─ warnings → Editor revises (silent)
                                                 → Anchor re-checks
                                                 ├─ CLEAN → proceed
                                                 └─ warnings → Editor revises (silent, final)
                                                               → Anchor re-checks (final)
                                                               → proceed with surviving warnings
```

**Revision prompt design:**
- **Fresh prompt per revision** — no message history; avoids anchoring bias where the editor fixates on its previous mistakes instead of the actual issues
- **Fixed-size context** — synthesis + current capsule + formatted warnings only; no growing conversation
- **Targeted instruction** — "Fix ONLY the warnings listed above. Preserve the voice, structure, and all unflagged material. Do not add new analysis."

**Streaming control:** Only the first draft is streamed to stdout. Revision passes use `run_sync` (silent). If a revision occurs, the user already saw the first draft stream by — the final capsule replaces it in the `ReportResult` and flows to downstream phases.

**Stderr output:** The CLI reports the reflection loop outcome:
- First-try clean: `Passed anchor check`
- Revised and converged: `Revised N time(s) -- anchor check passed`
- Exhausted with warnings: `Revised N time(s) -- anchor check found issues:` followed by each surviving warning in `[CATEGORY] description` format

**Why this phase exists:** The editor is already doing a lot of self-auditing (spot-check #10), but asking a writer to verify their own factual accuracy is like asking them to proofread their own work. A separate persona reading the synthesis and capsule together catches signal drift that the editor's self-check misses — for example, the synthesizer flagging the sinker as the development pitch while the editor builds the narrative around the changeup and barely mentions it. The reflection loop closes the feedback gap: instead of just reporting the drift, the system corrects it.

Downstream phases (Stuff Explainer, Executive Summary) receive the **final** capsule (post-revision if revisions occurred) — not the raw synthesis and not the first draft — so they inherit the editor's three-metric curation, plausibility filters, and confidence scaling.

### Model Configuration

Each agent role is assigned a model tier, thinking effort cap, and token budget tuned to its task:

| Role | Model Tier | Thinking Cap | max_tokens | Temp |
|------|-----------|-------------|------------|------|
| Synthesizer | Mini | medium | 2048 | 0.3 |
| Editor / Writer | Pro | uncapped | 4096 | 0.7 |
| Stuff Specialist / Explainer | Pro | medium | 2048 / 4096 | 0.3 |
| Location / RunValue / Trends / Game Shape Specialists | Mini | medium | 2048 | 0.3 |
| Auditor | Mini | low | 1024 | 0.1 |
| Anchor | Mini | low | 1024 | 0.1 |
| Executive Summary | Mini | medium | 1024 | 0.3 |
| Q&A Answerer | Pro | uncapped | 4096 | 0.3 |
| Curator | Pro | none | 4096 | default |

**Thinking effort** controls the model's reasoning budget. Levels are: minimal, low, medium, high, xhigh. The `cap_thinking()` utility clamps the user's CLI-selected level to a per-role ceiling — so `--thinking high` on the CLI still results in "low" for the anchor agent. Provider-specific behavior:

- **Claude:** Thinking disabled entirely for mini-tier models (Haiku) and when max_tokens <= 2048 (thinking budget would exceed output budget).
- **OpenAI:** Thinking disabled for gpt-5.4-mini (reasoning_effort not supported via chat completions API). Small token budgets omit max_tokens to avoid choking the model.
- **Gemini:** Thinking levels map to "high" (for high/xhigh) or "low" (all others). Flash supports thinking natively.

**Token budgets** prevent expensive thinking tangents on simple tasks. The budgets are role-appropriate: 1024 for short structured output (anchor warnings, audit flags, bullet summaries), 2048 for focused analytical paragraphs, 4096 for full narrative prose.

### Prompt Caching

CachePoint markers are inserted at strategic boundaries in the user messages to enable prompt caching across phases and across pitchers in batch runs:

- **Phase 1:** Cache breakpoint after role guidance (stable across all pitchers of the same role).
- **Phase 2:** Cache breakpoint after the synthesis output.
- **Phase 2.5:** Cache breakpoint after the synthesis (shared prefix with Phase 2).
- **Downstream phases:** Cache breakpoint after the capsule (shared across Stuff Explainer and Executive Summary for the same pitcher).

On Anthropic, these translate to explicit `cache_control` headers. On OpenAI, automatic prefix caching benefits from the same structure. On Gemini, CachePoints are silently ignored.

### Post-Generation Verification

After the reflection loop produces the final capsule and downstream phases complete, two verification steps run:

1. **Revision status** — the CLI reports the anchor check outcome: "Passed on first draft" / "Revised N time(s) — passed" / "Revised N time(s) — remaining issues:" with each surviving warning.
2. **Metric hallucination guard** — a regex scan of the narrative for metric-like patterns (xMetric, Acronym%, P+/S+/L+ family) flags any term not present in a known-safe set. It also detects traditional outcome stats (ERA, WHIP, W-L) that the editor prompt warns against citing. Flagged terms are reported as warnings on stderr.

---

## Q&A Analyst

The `pitcher-ask` CLI provides a natural-language Q&A interface grounded in the same data pipeline.

**Architecture:** A tool-calling pydantic-ai agent (Pro tier, temp=0.3) with `RunContext[QADeps]` dependency injection. The agent receives system instructions but no pre-loaded data — it calls tools to retrieve what it needs. The agent is constructed dynamically via `_make_qa_agent()`, respecting the user's `--provider` and `--thinking` flags.

**Two tools:**
1. `get_pitcher_summary()` — returns the full `to_prompt()` context plus league baselines with stddev and NORMAL/OUTLIER annotations
2. `get_pitch_detail(pitch_type)` — returns per-pitch-type detail including S-variant probabilities, P-vs-S deltas, and 13-outcome component attribution

**Reasoning chain:** Trace from physical pitch characteristics → model predictions → plus scores. Five-step chain: physical inputs, S+ via stuff profile, P-vs-S location isolation, component attribution, summary grades.

**Data grounding rules:** Answer only from tool output, never from training data. Compare metrics against league baselines (within 1.5 stddev = NORMAL). Enforce directional consistency. Reconcile strengths before labeling a pitch poor.

**Scope boundaries:** Declines predictions, fantasy advice, historical comparisons, cross-pitcher rankings, and game-by-game play-by-play.

---

## Pipeline Summary

```
                    ┌─────────────────────────────────────────────┐
                    │          SCOUT (pitcher-scout)              │
                    │                                             │
                    │  Appearance CSVs + Statcast                 │
                    │      │                                      │
                    │      ▼                                      │
                    │  10 signal checkers (pure Python)           │
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
                    │  Computation Engine (11 analysis modules)   │
                    │      │                                      │
                    │      ▼                                      │
                    │  Context Assembly (12-section markdown)     │
                    │      │                                      │
                    │      ├──▶ Simple Pipeline (report.py)       │
                    │      │     Synth → Editor → Anchor          │
                    │      │       ├──▶ Stuff Explainer           │
                    │      │       └──▶ Executive Summary         │
                    │      │                                      │
                    │      └──▶ Multi-Specialist (pipeline.py)    │
                    │            5 Specialists → 5 Audits         │
                    │              → Writer + Summary → Anchor    │
                    │      │                                      │
                    │      ▼                                      │
                    │  Hallucination Guard + Output               │
                    └─────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────┐
                    │          Q&A ANALYST (pitcher-ask)          │
                    │                                             │
                    │  Same data pipeline + league baselines      │
                    │      │                                      │
                    │      ▼                                      │
                    │  Tool-calling agent (2 tools)               │
                    │      │                                      │
                    │      ▼                                      │
                    │  Streamed prose answer                      │
                    └─────────────────────────────────────────────┘
```

Every number in the final report traces back through this pipeline to a specific Statcast column or Pitching+ aggregation. The LLM interprets and articulates — it does not compute.
