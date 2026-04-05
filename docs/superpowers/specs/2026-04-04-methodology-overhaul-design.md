# Methodology Doc Overhaul + Linear Update

**Date:** 2026-04-04
**Scope:** Rewrite METHODOLOGY.md from scratch; update Linear "Narration Agent Pipeline" doc

---

## Problem

METHODOLOGY.md has drifted significantly from the codebase. It describes a five-phase LLM architecture (Synthesizer, Editor, Anchor, Hook Writer, Fantasy Analyst) that no longer exists — the Hook Writer and Fantasy Analyst were removed. The v1.6 multi-specialist pipeline (pipeline.py) isn't documented at all. Context assembly undercounts sections (11 vs 12). The scout signals table lists 9 when the code has 10. The Q&A analyst pipeline isn't mentioned. Several computation engine features (intermediates, component attribution, league baselines) are missing.

The Linear doc ("Narration Agent Pipeline — End-to-End Diagram") accurately covers the v1.6 pipeline internals but doesn't acknowledge the simple pipeline, scout, or Q&A system. Minor accuracy fixes needed.

## Audience

- **METHODOLOGY.md**: Public-facing technical reference for blog readers, collaborators, and anyone evaluating the system
- **Linear doc**: Internal engineering reference with architecture diagrams, temperature strategy, LLM call budgets

## Approach

Rewrite METHODOLOGY.md from scratch. Update Linear doc with targeted fixes.

---

## METHODOLOGY.md — New Structure

### Section 1: Overview

Single paragraph establishing the system's purpose and core design principle: Python does all computation, LLM does interpretation only. Mention that two report pipelines exist (simple and multi-specialist). Three CLI tools: `pitcher-narratives`, `pitcher-scout`, `pitcher-ask`.

### Section 2: Data Sources

Two subsections, largely carried over from current doc:

**Statcast Pitch-Level Data**
- Source, grain, volume
- Key columns table (current version is accurate)
- Add `level` column (used for MLB filtering in the code)

**Pitching+ Aggregations**
- 8-grain CSV table (current version is accurate)
- Additional metrics (xRV100, xWhiff, xSwing, xGOr, xPUr, 20-80 scale variants)
- Note S-variant intermediate data: stuff-only model predictions (xSwing_S, xWhiff_S, xSwSt_S, xRV100_S) and 13-outcome component attribution per pitch type
- Join key

### Section 3: Data Pipeline

Carried over with additions:

**Loading and Filtering** — as-is, add MLB level filter

**Lookback Window** — as-is

**Starter/Reliever Classification** — as-is (per-appearance, inning-1 heuristic)

**Season Baselines** — as-is (n_pitches-weighted averages)

**League Baselines** (new) — describes how the engine computes league-wide mean + stddev for key metrics per pitch type, then pre-tags each pitcher's values as NORMAL (within 1.5 stddev) or OUTLIER. Used by both pipelines and the Q&A analyst as an anti-hallucination guardrail. The LLM never needs to compute z-scores — every metric arrives pre-annotated.

### Section 4: Computation Engine

Intro paragraph about polars DataFrames, structured dataclass outputs, pre-computed qualitative trend strings.

**Delta String Vocabulary** — as-is (threshold table for velocity, P+/S+/L+, usage, movement)

**Minimum Sample Size** — as-is (10 pitches per type, `small_sample` flag)

**Fastball Quality Analysis** — as-is (primary identification, velo/P+/S+/L+/movement trends, within-game velocity arc)

**Arsenal Analysis** — as-is (top 4 by usage, usage rate + P+/S+/L+ deltas)

**Execution Metrics** — as-is (CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 percentile per pitch type)

**Intermediate Probabilities** (new) — Per-pitch-type S-variant (stuff-only) model predictions: xSwing_S, xWhiff_S, xSwSt_S, xRV100_S. These isolate what the pitch's physical characteristics (velocity + movement) produce independent of location. The P-vs-S delta for each metric quantifies location's contribution. Feeds the Model Internals context section and the location/stuff specialist agents.

**Component Attribution** (new) — Per-pitch-type xRV100 decomposition into 13 outcome contributions (called_strike, swinging_strike, ball, foul, single, double, triple, home_run, etc.). Each outcome's contribution is signed: negative = pitcher benefits, positive = costs runs. Feeds the run value specialist in the multi-specialist pipeline.

**Platoon Mix Analysis** — as-is

**First-Pitch Weaponry** — as-is

**Hard-Hit Rate** — as-is

**Release Point Mechanics** — as-is (pitcher-specific baselines, not league)

**Times Through Order (TTO)** — as-is (3 levels: FB/secondary split, per-pitch-type breakdown, platoon within TTO, mix shift detection, small sample caveat)

**Workload Context** — as-is

### Section 5: Context Assembly

Update section list to match the 12 actual `to_prompt()` render methods:

1. Executive Summary
2. Role
3. Primary Fastball
4. Times Through Order
5. Arsenal
6. Execution
7. **Model Internals: Location Impact** (new — S-variant probabilities and P-vs-S deltas)
8. Release Point
9. Contact Quality
10. Platoon Shifts
11. First-Pitch Tendencies
12. Recent Appearances

Note: Component attribution data is available on the PitcherContext model (as `attributions`) but is not rendered by `to_prompt()` — it's consumed directly by the multi-specialist pipeline's data builders.

Token estimate: verify actual range from recent runs. The current claim of "900-1,200 tokens" may have grown with the intermediates section.

### Section 6: Appearance Scout

**Signal Detection** — update table to 10 signals:

| Signal | Weight | Threshold | Description |
|--------|--------|-----------|-------------|
| `new_pitch` | 4.0 | >5% game usage, <1% season usage | Pitch type newly appearing |
| `development_opportunity` | 3.5 | S+ >110, L+ <80 | High stuff, poor command |
| `velo_delta` | 3.0 | >= 1.5 mph from season | Fastball velocity gain or loss |
| `splus_lplus_divergence` | 3.0 | >= 10 pts each, opposite directions | Stuff/command split |
| `dropped_pitch` | 3.0 | >= 10% season usage, 0% game usage | Established pitch shelved |
| `pplus_swing` | 2.5 | >= 15 pts from season | Overall P+ spike or collapse |
| `walk_rate_pplus_contradiction` | 2.5 | P+ >= 105 with L+ < 85 | Good stuff without command |
| `usage_shift` | 2.0 | >= 8pp from season | Pitch type usage change |
| `hard_hit_spike` | 1.5 | (defined, not yet implemented) | Hard-hit rate anomaly |
| `workload_flag` | 1.0 | 3+ consecutive days | Reliever workload concern |

**LLM Curator** — as-is (four-tier signal hierarchy, 3-5 selections, conviction scoring, exclusion explanations)

### Section 7: Report Pipelines

Brief intro: the system offers two report generation architectures selected via the `--pipeline` CLI flag. Both share the same data pipeline, context assembly, and anchor check infrastructure. Three LLM providers supported: OpenAI (gpt-5.4-mini), Anthropic (claude-sonnet-4-6), Google (gemini-3.1-pro-preview).

#### 7a: Simple Pipeline (report.py)

The original architecture. Four LLM agents with a fact-checking reflection loop.

**Phase 1: The Synthesizer**
- Role: Objective data parser preparing a factual briefing
- Input: `to_prompt()` markdown + role-conditional guidance (starter/reliever) + league baselines + S-variant comparisons
- 10 analytical instructions (fastball baseline, intra-game stamina, usage shifts, execution, platoon specifics, portfolio audit, release point, intent, plausibility filter, objectivity)
- Structured output: 9 sections (Fastball Quality, Pitching+ Profile, Pitch Mix, Execution, Platoon Splits, Release Point, Workload & Stamina, Opponent Context, Key Signal with 3 bullets)
- Role-conditional appendix: starters get TTO/stamina focus, relievers get rest/workload focus
- Temperature: 0.3

**Phase 2: The Editor**
- Role: Elite sabermetric baseball writer
- Input: Phase 1 structured briefing + pitcher metadata
- Task: Find the narrative thread, write 2-3 paragraph capsule
- 10-point editorial guidelines (three metrics max, link mechanics to outcomes, diagnose root causes, consider intent lightly, scale confidence to sample, L+ is not command, voice rules, word bans, spot-check, data fidelity)
- Capsule structure: Setup paragraph (what changed) + Verdict paragraph(s) (how it plays in practice)
- Temperature: 0.7

**Phase 2.5: Anchor Check + Reflection Loop**
- Shared with multi-specialist pipeline (see Section 7c)

**Phase 3: Stuff Explainer**
- Role: Traces each pitch's S+ grade to its physical profile via stuff-only model predictions
- Input: Synthesis + league baselines + S-variant data
- Output: One paragraph covering 2-3 most notable pitches
- Temperature: 0.3

**Executive Summary**
- Role: Concise metrics-focused bullets for front office readers
- Input: Phase 1 synthesis
- Output: Exactly 3 bullet points, each citing a specific metric
- Directional consistency enforced
- Temperature: 0.3

**Data Flow:**
```
Context → Synthesizer → Editor → Anchor Check ─┬─ Stuff Explainer
                                                └─ Executive Summary
```

#### 7b: Multi-Specialist Pipeline (pipeline.py, v1.6)

Parallel architecture that decomposes the synthesizer's job into five specialist agents, each receiving tailored data inputs with pre-computed NORMAL/OUTLIER annotations.

**Phase 1: Five Specialist Agents (parallel, temp=0.3)**

Each specialist receives a custom data build from the PitcherContext — not the raw `to_prompt()` output. Data builders (`_build_stuff_input`, `_build_location_input`, `_build_runvalue_input`, etc.) pre-annotate every metric with its delta from league average and an explicit NORMAL/OUTLIER z-score tag.

1. **Stuff Specialist** — Traces velocity and movement shape to S+ grades via S-variant predictions. Rules: respect NORMAL/OUTLIER tags, secondary pitches derive value from movement not velocity, directional consistency (S+ < 100 = xRV100_S positive), xWhiff reconciliation (>= 25% = meaningful), citation requirement for all behavioral claims, no hallucinated causation.

2. **Location Specialist** — Isolates location impact by comparing P-variant (stuff + location) vs S-variant (stuff only) predictions. Explains mechanism: where is the pitcher putting the pitch, and how does that change hitter behavior? Zone rate and chase rate compared against league baselines.

3. **Run Value Specialist** — Reads the 13-outcome component attribution per pitch type. Identifies 2-3 dominant outcome contributors (largest positive and negative values). Connects outcomes to physical characteristics. Sign convention: negative = pitcher benefits.

4. **Trend Specialist** — Identifies window-vs-season deltas in velocity, grades, usage, movement, release point, hard-hit rate. Separates real trends from noise. Does NOT analyze within-game patterns.

5. **Game Shape Specialist** — Describes within-game effectiveness changes: TTO splits, velocity arc, mix shifts by pass, platoon-specific TTO patterns, workload context. Does NOT analyze window-vs-season trends.

**Phase 1.5: Per-Specialist Audit + Revision (parallel, temp=0.1)**

Each specialist's output is audited independently against the raw data it received. Five audits run in parallel. The auditor checks 7 categories:

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

The writer (temp=0.7) receives all 5 clean specialist outputs and composes a unified 2-3 paragraph capsule. Same editorial voice and constraints as the simple pipeline's editor, but input is specialist analyses rather than a single synthesis. Key instruction: specialists are ingredients, not sections to preserve. Find one thread across all five. Drop redundancy. Prioritize the surprising.

Executive summary (temp=0.3) runs concurrently with the writer — same format as simple pipeline (3 bullets citing specific metrics), but sourced from specialist outputs and aware of audit flags.

**Phase 2.5: Anchor Check + Reflection Loop**
- Shared infrastructure (see Section 7c)

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

#### 7c: Shared Infrastructure

**Anchor Check + Reflection Loop**

Both pipelines use the same anchor check implementation (anchor.py). After the editor/writer produces a capsule:

1. The anchor agent (temp=0.1) receives the synthesis/specialist outputs and the capsule
2. It checks for 4 warning categories: MISSED_SIGNAL, UNSUPPORTED, DIRECTION_ERROR, OVERSTATED
3. If clean: proceed to downstream phases
4. If warnings: editor receives a targeted revision prompt (fresh prompt, no message history, fixed-size context: synthesis + current capsule + formatted warnings)
5. Anchor re-checks. Up to MAX_REVISIONS (default: 2) passes, for a maximum of 3 total (first draft + 2 revisions)

Streaming: only the first draft streams to stdout. Revisions are silent. The final capsule flows to downstream phases.

Stderr reports: "Passed anchor check" / "Revised N time(s) -- anchor check passed" / "Revised N time(s) -- anchor check found issues: [surviving warnings]"

**Prompt Caching**

CachePoint markers at strategic boundaries:
- Phase 1: after role guidance (stable across pitchers of same role)
- Phase 2: after synthesis output
- Phase 2.5: after synthesis (shared prefix with Phase 2)
- Downstream phases: after capsule (shared across stuff explainer + exec summary)

On Anthropic: explicit `cache_control` headers. On OpenAI: automatic prefix caching. On Gemini: CachePoints silently ignored.

**Metric Hallucination Guard**

Post-generation regex scan of the narrative for metric-like patterns. Flags terms not in a known-safe set. Detects traditional outcome stats (ERA, WHIP, W-L) that the editor is warned against citing. Flagged terms reported as warnings on stderr.

**Temperature Strategy**

| Role | Temp | Rationale |
|------|------|-----------|
| Synthesizer / Specialists | 0.3 | Data precision |
| Editor / Writer | 0.7 | Prose quality |
| Exec Summary / Stuff Explainer | 0.3 | Metrics focus |
| Auditor / Anchor | 0.1 | Maximum determinism |

### Section 8: Q&A Analyst

The `pitcher-ask` CLI provides a natural-language Q&A interface grounded in the same data pipeline.

**Architecture:** A tool-calling pydantic-ai agent with RunContext[QADeps] dependency injection. The agent receives system instructions but no pre-loaded data — it calls tools to retrieve what it needs.

**Two tools:**
1. `get_pitcher_summary()` — returns the full `to_prompt()` context plus league baselines with stddev and NORMAL/OUTLIER annotations
2. `get_pitch_detail(pitch_type)` — returns per-pitch-type detail including S-variant probabilities, P-vs-S deltas, and 13-outcome component attribution

**Reasoning chain:** The agent is instructed to trace from physical pitch characteristics → model predictions → plus scores. Five-step chain: physical inputs, S+ via stuff profile, P-vs-S location isolation, component attribution, summary grades.

**Data grounding rules:** Answer only from tool output, never from training data. Compare metrics against league baselines (within 1.5 stddev = NORMAL). Enforce directional consistency. Reconcile strengths before labeling a pitch poor.

**Scope boundaries:** Declines predictions, fantasy advice, historical comparisons, cross-pitcher rankings, and game-by-game play-by-play.

**Voice:** Same analyst-to-analyst style as the report pipelines.

### Section 9: Pipeline Summary

Updated ASCII diagram showing the full system:

```
                    ┌─────────────────────────────────────────────┐
                    │          SCOUT (pitcher-scout)              │
                    │                                             │
                    │  Appearance CSVs + Statcast                 │
                    │      │                                      │
                    │      v                                      │
                    │  10 signal checkers (pure Python)           │
                    │      │                                      │
                    │      v                                      │
                    │  Scored + ranked appearances                │
                    │      │                                      │
                    │      v (--curate)                           │
                    │  LLM Curator (select 3-5 stories)          │
                    └─────────────────────────────────────────────┘
                                       │
                          pitcher IDs worth writing about
                                       │
                                       v
                    ┌─────────────────────────────────────────────┐
                    │     NARRATIVE BUILDER (pitcher-narratives)  │
                    │                                             │
                    │  Statcast parquet + 8 Pitching+ CSVs        │
                    │      │                                      │
                    │      v                                      │
                    │  Computation Engine (11 analysis modules)   │
                    │      │                                      │
                    │      v                                      │
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
                    │      v                                      │
                    │  Hallucination Guard + Output               │
                    └─────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────┐
                    │          Q&A ANALYST (pitcher-ask)          │
                    │                                             │
                    │  Same data pipeline + league baselines      │
                    │      │                                      │
                    │      v                                      │
                    │  Tool-calling agent (2 tools)               │
                    │      │                                      │
                    │      v                                      │
                    │  Streamed prose answer                      │
                    └─────────────────────────────────────────────┘
```

Closing line: Every number in the final report traces back through this pipeline to a specific Statcast column or Pitching+ aggregation. The LLM interprets and articulates — it does not compute.

---

## Linear Doc Updates

Update the existing "Narration Agent Pipeline — End-to-End Diagram" document:

1. **Add scope note** at the top: "This document covers the v1.6 multi-specialist pipeline (pipeline.py). For the simple pipeline (report.py), scout system, and Q&A analyst, see METHODOLOGY.md."

2. **Verify LLM call budget table** against current code — the "best case 13 / typical 15 / worst case 22" counts should still be accurate but verify.

3. **Keep everything else** — the mermaid diagrams, temperature strategy quadrant, audit categories, data flow, file map, and specialist guardrails are accurate and serve the internal engineering audience well.

---

## Out of Scope

- Changing any code behavior
- Restructuring the codebase
- Adding new features
- Updating README.md or blog-post.md (separate tasks if desired)
