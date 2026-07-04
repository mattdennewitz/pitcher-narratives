# Pitcher Narratives — Methodology

This document describes how `pitcher-narratives` turns static Statcast
and Pitching+ data into a scout-voice scouting capsule. It is intended
for people who want to understand the data transformations, the
multi-agent pipeline, and the guardrails — not just how to run the CLI.
For installation and CLI usage, see `README.md`.

## Overview

Pitcher Narratives is built around one premise: arithmetic is a terrible
use of an LLM, but delta interpretation and cross-metric synthesis are
a great one. The system pre-computes every metric, delta, baseline, and
outlier tag the downstream stages need, so specialists receive inputs
that already say "FB velo is DOWN 1.8 mph (OUTLIER, z=-2.1)" rather
than two numbers that the model has to subtract and evaluate.

The inputs are entirely static: a pair of Statcast parquet files in
`var/statcast/` and a folder of pre-computed Pitching+ CSVs in `var/aggs/`.
The output is a streamed scouting capsule plus a set of structured
side artifacts — executive summary bullets, stuff analysis, data-audit
flags, anchor-check results, and an optional hallucination-guard
report. Everything is grounded against the same pitcher context built
once per run.

## Data sources

### Statcast parquet (`var/statcast/`)

- `var/statcast/2025.parquet`, `var/statcast/2026.parquet` — pitch-level
  Statcast data for the 2025 and 2026 seasons. Loaded by `data.py` via
  `load_all_statcast` / `load_pitcher_data`.

### Pitching+ CSVs (`var/aggs/`)

Eight CSVs per season. The 2026 set is the current season; the 2025
set provides cross-season baselines for year-over-year deltas.

- `2026-pitcher.csv` — one row per pitcher per season.
- `2026-pitcher_type.csv` — per pitcher per pitch type (P+/S+/L+,
  usage, movement).
- `2026-pitcher_appearance.csv` — one row per game per pitcher.
- `2026-pitcher_type_appearance.csv` — per game per pitcher per pitch
  type.
- `2026-pitcher_type_platoon.csv` — season splits per pitcher per pitch
  type against L and R hitters.
- `2026-pitcher_type_platoon_appearance.csv` — per-game platoon splits.
- `2026-all_pitches.csv` — individual pitches with P+/S+/L+.
- `2026-team.csv` — team-level season rows.

The 2025 analogues live alongside. `data.py` joins the year-aware files
into year-over-year cross-season views.

### Behavioral choices in `data.py`

- **Lookback window is relative to the dataset**, not wall clock. The
  `-w/--window` value is subtracted from the most recent `game_date`
  present in the loaded appearance data, not from "today." This keeps
  behaviour stable against frozen parquet/CSV snapshots — running the
  CLI a month later still produces the same result as long as the
  files on disk are the same.
- **Starter vs reliever is classified per appearance** from the first
  inning pitched. First inning of the outing == 1 → `SP`, otherwise
  `RP`. Openers (who throw the first inning before handing off) end up
  labeled `SP` under this rule. The classification is per-appearance,
  not per-season, so two-way arms shift role naturally.
- **Season baselines across game types are `n_pitches`-weighted**, not
  simple arithmetic means. This prevents a five-pitch regular-season
  row from outweighing a 200-pitch spring-training row when the same
  pitcher's record shows up across multiple game types.

## Engine (`engine.py`)

`engine.py` is the large computation module. It owns every metric,
delta, baseline, and outlier flag that the downstream stages consume.
Specialists and the writer never recompute anything from raw data —
they just read pre-annotated inputs from the engine.

### Delta vocabulary

| Metric family | "Steady" cutoff | "Up/Down" band | "Sharply" |
|---|---|---|---|
| Velocity (mph) | `< 0.5` | `0.5 – 2.0` | `> 2.0` |
| P+ / S+ / L+ (points) | `< 5` | `5 – 10` | `> 10` |
| Usage rate (pp) | `< 5` | `5 – 10` | `> 10` |
| Movement (inches) | `< 0.5` | `>= 0.5` | — |

Each delta rendered into the specialist inputs also gets an explicit
NORMAL/OUTLIER tag from `engine.outlier_tag` (a z-score thresholded
against the same-role league distribution). This is how specialists
know whether "FB velo down 0.8 mph" is noise or a real shift.

### Fallbacks and small-sample handling

- **Full-window-no-baseline fallback.** If the lookback window covers
  the entire season the pitcher has available, there is no prior
  baseline to compare against. The delta string is replaced with
  `"Full season in window — no trend comparison."`
- **Small-sample flag.** Per-pitch-type analyses below 10 pitches in
  the window set `small_sample: true`. Specialists are instructed to
  either caveat or drop findings that rest on small samples, and the
  anchor check is primed to flag small-sample findings presented as
  definitive (see the `OVERSTATED` category below).

## Context assembly (`context.py`)

`PitcherContext` is a Pydantic model that bundles everything the
pipeline needs for a single pitcher: role info, fastball detail, TTO
splits, arsenal table, execution metrics, location-impact model
internals, release-point drift, contact quality, platoon splits,
first-pitch tendencies, recent appearances, year-over-year snapshot,
and a detached `attributions` field.

### `to_prompt()` — up to 15 rendered sections

`PitcherContext.to_prompt()` renders up to **15 sections** in the order
below. Empty sections are skipped (for example, single-season pitchers
get no `Year-over-Year` block). The fifteen sections are:

1. **Title** — `# {pitcher_name} ({L/R}HP) -- Scouting Context`
2. **`## Temporal Context`** — analysis date, season phase
   (early / mid / full), prior-year workload relevance line.
3. **`## Executive Summary`** — last outing; fastball velo delta;
   fastball P+/S+/L+ triad deltas; biggest arsenal usage shift; TTO
   summary; hard-hit delta; workload flag.
4. **`## Role`** — most recent role (SP/RP), appearance count,
   consecutive days pitched, workload concern flag.
5. **`## Primary Fastball: {pitch_name} ({type})`** — velocity,
   P+/S+/L+ triad + deltas, movement deltas, within-game velocity arc
   from the last outing. Falls back to
   `## Primary Fastball\n- No standard fastball identified` when no
   standard fastball is found.
6. **`## Times Through Order`** — fastball vs secondary P+ split per
   pass; per-pitch-type usage + P+ across passes with mix-shift flags;
   platoon-within-TTO breakdowns. Skipped when there is no TTO data
   (e.g. pure relievers with one-inning outings).
7. **`## Arsenal`** — top pitch types by usage with usage delta and
   P+/S+/L+ columns vs season baseline.
8. **`## Execution`** — CSW%, Zone%, Chase%, xWhiff, xSwing, and xRV100
   percentile per pitch type.
9. **`## Model Internals: Location Impact`** — S-variant (stuff-only)
   probabilities and P-vs-S deltas per pitch type. This is the
   location-impact decomposition: how much of each pitch's P+ comes
   from raw stuff vs location vs command.
10. **`## Release Point`** — per-pitch-type release x/z/extension vs
    the pitcher's own season baseline.
11. **`## Contact Quality`** — hard-hit rate, window vs season, with
    delta.
12. **`## Platoon Shifts`** — per-pitch-type usage and P+ by batter
    handedness.
13. **`## First-Pitch Tendencies`** — top first-pitch types, recent vs
    season share.
14. **`## Recent Appearances`** — date, IP, pitch count, rest days.
15. **`## Year-over-Year`** — cross-season pitcher-level deltas plus
    added and dropped pitches. Skipped for single-season pitchers.

### What `to_prompt()` does NOT render

`PitcherContext.attributions` — the 13-outcome xRV100 decomposition per
pitch type — is **not** rendered by `to_prompt()`. It is consumed
directly by `_build_runvalue_input` in `pipeline.py`, which formats it
into the run-value specialist's bespoke input. Keeping it out of the
shared context render prevents all specialists from seeing the full
attribution table when only one of them needs it.

## Scout (`scout.py`)

`scout.py` is the no-LLM triage layer. It scans recent appearances and
scores each one on a heuristic signal table, so the expensive narrative
pipeline only runs on appearances that look interesting.

### Ten scored signals

`_WEIGHTS` defines ten signals, listed here highest weight first:

| Signal | Weight | Threshold | Intent |
|---|---|---|---|
| `new_pitch` | 4.0 | Season usage `< 1%` and game usage `> 5%` | A new pitch type appeared at meaningful volume |
| `development_opportunity` | 3.5 | `S+ >= 110` and `L+ <= 80` on the same pitch | High stuff without feel — a pitch worth developing |
| `velo_delta` | 3.0 | `>= 1.5 mph` from season fastball average | Fastball velocity swing vs season |
| `splus_lplus_divergence` | 3.0 | `S+` and `L+` deltas each `>= 10 pts`, opposite signs | Stuff/command split on a single pitch |
| `dropped_pitch` | 3.0 | Season usage `>= 10%` and game usage `0%` | Established pitch was shelved |
| `pplus_swing` | 2.5 | `>= 15 pts` from season P+ | Overall P+ spike or collapse |
| `walk_rate_pplus_contradiction` | 2.5 | `P+ >= 105` and `L+ < 85` at appearance level | Good overall stuff without command |
| `usage_shift` | 2.0 | `>= 8 pp` pitch-type usage change from season | Mix shift on any pitch type |
| `hard_hit_spike` (stub) | 1.5 | (none) | Listed in the weights table but not yet wired into the scanner |
| `workload_flag` | 1.0 | `>= 3` consecutive calendar days pitched | Reliever workload concern |

**About `hard_hit_spike`.** The entry exists in the `_WEIGHTS` dict at
`scout.py:37`, but no code path in `scout.py` emits a `Signal` with
that name — it is a documented stub awaiting implementation. The other
scout signals each have a dedicated `_check_*` helper called from
`scout_appearances`; `hard_hit_spike` does not. Do not assume it fires.

Each fired `Signal` carries `name`, `weight`, and a human-readable
`detail` line. `ScoredAppearance.score` is the sum of fired weights.

## Curator (`curator.py`)

The `--curate` flag on `pitcher-scout` sends the top scored appearances
to an LLM via `curate_appearances` in `curator.py`, using the provider
selected by `--provider`. The curator's job is editorial selection: it
picks the 3–5 most compelling stories from the top of the heuristic
ranking and writes short framing blurbs.

## Pipeline (`pipeline.py`)

`pipeline.py` contains the sole report generation path — there is no
single-agent fallback. The streaming entry point `generate_pipeline_streaming`
assembles the agents via `make_pipeline_agents(provider, thinking)` and
then drives the five phases below in order.

### Phase 1 — specialists in parallel

Five specialist agents run concurrently via `run_specialists`. Each
receives a bespoke input built by its `_build_*_input` helper, with
every metric pre-annotated with a delta from league average and an
explicit `NORMAL`/`OUTLIER` z-score tag from `engine.outlier_tag`.

| Specialist | Tier | temp | max_tokens | Prompt |
|---|---|---|---|---|
| `stuff` | Pro | 0.3 | LARGE (4096) | `_STUFF_SPECIALIST_PROMPT` |
| `location` | Mini | 0.3 | LARGE (4096) | `_LOCATION_SPECIALIST_PROMPT` |
| `runvalue` | Mini | 0.3 | LARGE (4096) | `_RUNVALUE_SPECIALIST_PROMPT` |
| `trends` | Mini | 0.3 | MEDIUM (2048) | `_TREND_SPECIALIST_PROMPT` |
| `game_shape` | Mini | 0.3 | MEDIUM (2048) | `_GAME_SHAPE_SPECIALIST_PROMPT` |

Only the stuff specialist runs on the Pro-tier model — it is the one
output that surfaces in the final narrative as `# Stuff Analysis` so
it gets the highest-quality model. The other four specialists produce
inputs that only the writer ever sees, so Mini-tier is sufficient.

### Phase 1.5 — audit + revise

`audit_and_revise_specialists` runs the auditor (Mini tier, `temp=0.1`,
`retries=5`, SMALL token budget) on each of the five specialist outputs
in parallel. The auditor's job is to verify every quantitative claim
against the ground-truth input that was passed to that specialist.

- **Phase 1.5a** — all five audits run concurrently.
- **Phase 1.5b** — any specialist whose audit fires flags is re-run
  with its original input plus the audit corrections. Clean
  specialists pass through untouched.

`AuditFlag` and `AuditResult` are defined in `pipeline.py`. The writer
never sees flawed specialist prose — if an audit flag survives, the
specialist is re-run before the writer ever starts composing.

### Phase 1.75 — signal extractor

A dedicated `signal_extractor` agent (Mini tier, SMALL budget,
`retries=3`) reads the clean specialist outputs and returns a
`KeySignals` object from `signals.py`.

**Primary fields (required, non-empty):**

- `top_improvement` — the single most important positive finding
  across all specialists, with pitch type and metric cited.
- `top_concern` — the single most important negative finding across
  all specialists, with pitch type and metric cited.

**Secondary fields (optional, may be `null`):**

- `development_pitch` — a pitch with high `S+` and low `L+` that would
  solve a documented platoon gap.
- `specialist_tension` — where two specialists disagree about the same
  pitch.
- `arsenal_dependency` — one pitch carrying the profile while the rest
  is replacement-level.
- `connected_changes` — multiple specialists reporting facets of the
  same underlying shift.
- `platoon_vulnerability` — a clear weakness against one handedness
  that the data suggests is not being addressed.
- `sample_size_caution` — when the strongest finding rests on thin
  data.

**Phase 1.75 is non-critical.** If the signal extractor raises, the
pipeline continues with `key_signals=None` and the downstream anchor
check degrades gracefully (primary-signal enforcement just can't fire).
Failing the signal extractor never fails the whole run.

### Phase 2 — writer + executive summary in parallel

The writer (Pro tier, `temp=0.7`, LARGE budget) runs from
`build_writer_input(ctx, specialists, key_signals)` and streams to
stdout — this is what the user sees scrolling past under
`# Scouting Report`.

Concurrently, the executive summary agent (Mini tier, `temp=0.3`,
SMALL budget) runs from the same input. Summary failures are
non-fatal: an empty bullet list renders as
`_Summary unavailable — no bullets produced._` and the rest of the
run continues.

### Phase 2.5 — anchor check + revision loop

`_run_anchor_revision_loop` drives the anchor agent (Mini tier,
`temp=0.1`, SMALL budget) via `anchor.ANCHOR_PROMPT`. The synthesis
passed to the anchor is `render_key_signals(key_signals)` concatenated
with the specialist outputs. The anchor's job is to verify that the
capsule is faithful to that synthesis — not to evaluate stuff quality
or narrative style, only whether the prose matches the data it was
built from.

When the anchor is not clean, the writer is asked to revise via
`anchor.build_revision_message` — a fresh prompt with no message
history, a `CachePoint` breakpoint after the synthesis, and a targeted
instruction that says "fix only the listed warnings." Up to
`MAX_REVISIONS` (3) revision passes run, and then one final anchor
check captures any surviving warnings.

#### Anchor warning categories

The five categories are defined as `anchor.WarningCategory` and are
emitted literally by the anchor prompt:

| Category | Meaning |
|---|---|
| `MISSED_SIGNAL` | The capsule ignores a required primary `KeySignals` field (`top_improvement` or `top_concern`) |
| `UNDERWEIGHTED` | The capsule ignores a populated secondary `KeySignals` field (e.g. `development_pitch`, `specialist_tension`, `arsenal_dependency`, `connected_changes`, `platoon_vulnerability`, `sample_size_caution`) |
| `UNSUPPORTED` | The capsule states a metric, trend, or fact that does not appear anywhere in the synthesis |
| `DIRECTION_ERROR` | The synthesis says a metric moved up and the capsule says it moved down (or vice versa) |
| `OVERSTATED` | The synthesis flagged something as small sample or uncertain, but the capsule presents it as definitive |

`AnchorResult.is_clean` is `True` when `warnings` is empty.

#### Reconciling the anchor check with fact-revised capsules

The anchor check and the fact-check (`run_capsule_audit`, part of the
capsule audit) validate the capsule against two different references:
the anchor's reference is the synthesis (does the prose match the
specialist findings?), while the fact-check's reference is the
ground-truth data (does the prose match reality?). **When they
disagree, the data wins** — a fact revision is allowed to invalidate
an anchor result that was captured before the ground truth was
applied.

Concretely: if a fact revision rewrites the capsule (`capsule_revised`
is `True`), the anchor check computed earlier in the pipeline no
longer describes the final text, so `_reconcile_anchor_warnings`
re-anchors it. If the re-anchor comes back clean, nothing further
happens. Otherwise, as long as budget remains
(`anchor_depth - revision_count`), the pipeline runs reconciling
revision passes: the writer is asked to fix the listed warnings under
a prompt that forbids changing any numeric value, since the fact-check
already verified those numbers and the anchor may simply be looking at
stale synthesis. Each pass re-anchors and stops early either on a
clean result or when the warning set stalls (identical warnings two
passes in a row).

Once the loop ends, a detection-only capsule re-audit
(`max_fact_revisions=0`) guards the outcome: if the reconciled prose
regressed a verified fact, the pipeline reverts to the fact-revised
capsule and ships the earlier recheck warnings as advisory rather than
keeping the regression. A crash anywhere in this reconcile step is
advisory-plus — it's logged and the pipeline keeps the prior
`anchor_check` rather than failing the run. Reconcile passes count
toward `revision_count`, so the CLI's "Revised N time(s)" reflects
them the same as ordinary anchor revisions.

## Hallucination guard

After Phase 2.5 completes, `check_hallucinated_metrics` in `pipeline.py`
regex-scans the final narrative text and returns a `HallucinationReport`
with two fields:

- `unknown_metrics` — metric-like patterns (xMetric names like xWhiff,
  acronyms-plus-percent like `CSW%`, and the `P+`/`S+`/`L+` family)
  that do not appear in a known-safe allowlist. This catches cases
  where the writer invents a plausible-sounding metric.
- `outcome_stat_warnings` — traditional outcome stats the writer prompt
  explicitly warns against (ERA, WHIP, W-L, etc.). These are
  discouraged because scouting capsules are about process, not
  outcomes.

The CLI (`cli.py`) emits the `# Hallucination Check` section **only
when the report is not clean**. A clean narrative never prints a
hallucination section.

## Caching and prompt cache breakpoints

`pydantic_ai.CachePoint` is used in two distinct layers. Each specialist
input and each anchor-flavoured message is a `list[str | CachePoint]`
rather than a plain string, which lets the pipeline declare cache
boundaries explicitly.

**Specialist inputs (5 places in `pipeline.py`).** Each of the five
`_build_*_input` helpers — `_build_stuff_input`, `_build_location_input`,
`_build_runvalue_input`, `_build_trend_input`, `_build_game_shape_input`
— emits a list shaped like
`[header + league baselines, CachePoint(), per-pitch data]`. The
header prefix (role guidance, league baselines, S-variant tables,
`NORMAL`/`OUTLIER` legend) is stable across reruns for the same
pitcher, so the cache-friendly prefix is hoisted in front of the
breakpoint while the variable pitch-level data trails behind it.

**Anchor messages (2 places in `anchor.py`).**
`build_anchor_message(synthesis, capsule)` and
`build_revision_message(synthesis, capsule, warnings)` both put a
`CachePoint` between the synthesis (key signals + concatenated
specialist outputs) and the capsule-plus-instructions tail. The effect
is that the synthesis half is cacheable across the initial anchor
check and every subsequent revision pass within a single run — only
the capsule and the formatted warning list change each pass.

`build_writer_input` is plain `str`, not a `UserPrompt` list, so the
writer does not add a cache breakpoint of its own; its caching benefit
comes from whatever automatic prefix caching the underlying provider
offers. On providers that honour explicit `CachePoint` breakpoints,
the specialist-prefix and anchor-synthesis hoists still cut latency
and cost meaningfully on retries and same-pitcher reruns.

## Model table (from `config.py`)

### Provider model strings

| Provider key | Pro tier (`PROVIDERS`) | Mini tier (`MINI_PROVIDERS`) |
|---|---|---|
| `openai` | `openai:gpt-5.4` | `openai:gpt-5.4-mini` |
| `claude` | `anthropic:claude-sonnet-4-6` | `anthropic:claude-haiku-4-5` |
| `gemini` | `google-gla:gemini-3.1-pro-preview` | `google-gla:gemini-flash-latest` |

### Token budgets

- `TOKEN_BUDGET_SMALL = 1024` — anchor, auditor, executive summary,
  signal extractor (short structured output)
- `TOKEN_BUDGET_MEDIUM = 2048` — compact specialists (`trends`,
  `game_shape`)
- `TOKEN_BUDGET_LARGE = 4096` — writer plus the `stuff`, `location`,
  and `runvalue` specialists (long-form prose)

### Role → tier / temp / max_tokens / thinking cap

`make_pipeline_agents` assigns each role via `cap_thinking`, which
clamps the user-supplied `--thinking` level to a per-role ceiling.

| Role | Tier | temp | max_tokens | Thinking cap |
|---|---|---|---|---|
| Stuff specialist | Pro | 0.3 | LARGE | `medium` |
| Location / RunValue | Mini | 0.3 | LARGE | `medium` |
| Trends / Game Shape | Mini | 0.3 | MEDIUM | `medium` |
| Writer | Pro | 0.7 | LARGE | *(user level, uncapped)* |
| Auditor | Mini | 0.1 | SMALL | `low` |
| Anchor | Mini | 0.1 | SMALL | `low` |
| Executive Summary | Mini | 0.3 | SMALL | `medium` |
| Signal Extractor | Mini | 0.3 | SMALL | `medium` |

The writer is intentionally uncapped — it's the one place where the
user's `--thinking high` or `--thinking xhigh` actually matters for
prose quality. Every other role is capped because extra thinking on
short structured outputs mostly just burns tokens.

### Provider quirks (`make_model_settings`)

- **Gemini** always uses `GoogleModelSettings` with
  `google_thinking_config={"thinking_level": "high" | "low"}`. CLI
  levels `high` and `xhigh` map to `"high"`; everything else maps to
  `"low"`. `temperature` and `max_tokens` pass through unchanged.
- **Claude** disables thinking entirely when `mini=True` or when
  `max_tokens <= TOKEN_BUDGET_MEDIUM` — otherwise Claude's thinking
  budget would exceed the output budget and the request would fail.
  When thinking is on, temperature is forced to `1` (Claude refuses
  non-1 temperature with thinking enabled).
- **OpenAI** disables `reasoning_effort` for mini-tier models —
  `gpt-5.4-mini` doesn't support it via chat completions — and omits
  `max_tokens` entirely when the budget is `<= TOKEN_BUDGET_MEDIUM`.
  Reasoning tokens count against `max_tokens`, so small caps choke
  the model before it produces visible output.

## Q&A analyst (`analyst.py`)

`pitcher-ask` is a separate entry point that answers natural-language
questions about a pitcher. It is **not** a wrapper around the narrative
pipeline — it is a single tool-calling agent that owns its own context.

- **Tier / temp:** Pro tier, `temp=0.3`, LARGE token budget.
- **Default provider:** `pitcher-ask` defaults to `gemini` (not openai — this is intentional and different from `pitcher-narratives`, which defaults to openai).
- **System prompt:** `ANALYST_INSTRUCTIONS`.
- **Entry point:** `ask_question_streaming(question, context, data,
  provider, thinking, ...)`.

### Tools (exactly two)

The agent is constructed at `analyst.py:464` with exactly two tools:

- **`get_pitcher_summary(ctx)`** — returns league baselines (per pitch
  type, including stddev) plus the full `PitcherContext.to_prompt()`
  output. This is the broad-view tool: whenever the agent needs the
  whole picture, it calls this.
- **`get_pitch_detail(ctx, pitch_type)`** — returns focused arsenal,
  execution, platoon, model-internals, and 13-outcome attribution data
  for one specific pitch type. Accepts human pitch type names
  ("slider", "four-seam") or Statcast codes ("SL", "FF") via the
  `PITCH_TYPE_MAP` synonym table.

These two tools are the entire tool set — there are no others.
Everything the agent needs is covered by summary-plus-detail, and the
agent is free to call `get_pitch_detail` multiple times to assemble a
multi-pitch answer.

### Resolver and input plumbing

`resolver.py` uses `rapidfuzz` to fuzzy-match the pitcher name out of
the question text (`extract_pitcher_from_question`). If no pitcher is
found, or if multiple pitchers match ambiguously, the CLI exits with
an error listing the candidates. Once the pitcher is resolved,
`data.load_pitcher_data` and `context.assemble_pitcher_context` build
the same `PitcherContext` the narrative pipeline uses, and it is
injected into the agent as part of `QADeps`.

### `ask_question_pipeline` / `PipelineAnswer`

`analyst.py` also defines `ask_question_pipeline` and `PipelineAnswer`
— a multi-agent Q&A path that reuses the specialist → audit → signal
extractor flow from `pipeline.py` before calling a final answerer
agent. The `pitcher-ask` CLI currently uses the simpler single-agent
tool-calling path (`ask_question_streaming`); the pipeline path exists
as an alternate implementation for future use.

## End-to-end diagram

```
load_pitcher_data (data.py)
        |
        v
assemble_pitcher_context (context.py)
        |
        v
+---------------------------------------------------+
|  Phase 1 — five specialists in parallel           |
|    stuff | location | runvalue | trends | game_shape
+---------------------------------------------------+
        |
        v
+---------------------------------------------------+
|  Phase 1.5 — per-specialist audit + re-run        |
|    (auditor x 5 in parallel, then revise flagged) |
+---------------------------------------------------+
        |
        v
+---------------------------------------------------+
|  Phase 1.75 — signal extractor (non-critical)     |
|    -> KeySignals(top_improvement, top_concern,    |
|       + 6 optional secondary fields) or None      |
+---------------------------------------------------+
        |
        v
+---------------------------------------------------+
|  Phase 2 — writer (streamed) + exec summary       |
|    (parallel, same input)                         |
+---------------------------------------------------+
        |
        v
+---------------------------------------------------+
|  Phase 2.5 — anchor check + revision loop         |
|    (up to MAX_REVISIONS = 3 passes)               |
|    warnings: MISSED_SIGNAL / UNDERWEIGHTED /      |
|              UNSUPPORTED / DIRECTION_ERROR /      |
|              OVERSTATED                           |
+---------------------------------------------------+
        |
        v
check_hallucinated_metrics (pipeline.py)
        |
        v
stdout:
  # Scouting Report
  # Executive Summary
  # Stuff Analysis
  # Data Audit
  # Anchor Check
  # Hallucination Check   (only when not clean)
```

All five phases share the same `PitcherContext`, and every specialist
input is built from that single source. The anchor check and the
hallucination guard are the two structural guardrails that keep the
LLM honest against the data it was given.
