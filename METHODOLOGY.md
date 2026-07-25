# Pitcher Narratives — Methodology

This document describes how `pitcher-narratives` turns a versioned
PitchingPlus output bundle into scouting reports. It covers deterministic
transformations, the multi-agent pipeline, and guardrails. For installation
and CLI usage, see `README.md`.

## Overview

Pitcher Narratives is built around one premise: arithmetic is a terrible
use of an LLM, but delta interpretation and cross-metric synthesis are
a great one. The system pre-computes every metric, delta, baseline, and
outlier tag the downstream stages need, so specialists receive inputs
that already say "FB velo is DOWN 1.8 mph (OUTLIER, z=-2.1)" rather
than two numbers that the model has to subtract and evaluate.

The sole runtime input is a static, versioned PitchingPlus bundle under
`var/aggs/`. The generated capsule is buffered, converted to a typed
provenance-bound artifact, and validated before it reaches stdout. Reports may
then append a separate deterministic model-and-data-boundary explanation.

## Producer and data boundary

Raw Statcast enters **PitchingPlus**. PitchingPlus performs feature processing,
prediction, run-value conversion, centering, aggregation, and artifact
publication. It emits a versioned bundle whose season manifests cover:

- `all_pitches` rows used for exact game/frame selection;
- pitcher, pitch-type, appearance, platoon, and team aggregates;
- league and pitch-class reference populations;
- formal Location+ and any emitted spatial evidence;
- any emitted 13-outcome component-attribution artifact;
- any registered model-evaluation/calibration artifact; and
- semantic manifests with checksums, grains, natural keys, frames, variants,
  populations, statistical units, weighting, and metric definitions.

`data.load_pitchingplus_bundle` validates the manifests and every required
artifact before returning rows. Pitcher Narratives never opens raw Statcast,
run-value tables, model files, count-weight artifacts, or unmanifested
auxiliary data. Deterministic Narrative code may select, aggregate, compare,
and label emitted facts. Agents may interpret only exact cited facts.

The canonical model contract is deterministic: PitchingPlus converts 13
predicted outcome probabilities to expected run value with count-specific run
values. P includes realized location. S omits realized `plate_x`/`plate_z` but
retains release position/extension, arm angle, derived acceleration/spin
coordinates, handedness/platoon, fastball-velocity context, coarse repertoire
shares, and count processing. Exported S uses training-sample
`P(count | broad pitch class, same_side)` outcome marginalization followed by
actual-count run-value scoring; formal L uses hidden same-count S. P, S, and L
have independent same-scoring-season MLB regular-season pitch-weighted 100
anchors. The current 20–80 display is uncapped `plus - 50`, not SD-scaled.
Conditional expected rates are means of per-pitch ratios, and group grades have
no model-level minimum or shrinkage. Location+ is associative realized-location
evidence, not command, intent, target execution, or causal attribution.

### Behavioral choices in `data.py`

- **Lookback window is relative to the dataset**, not wall clock. The
  `-w/--window` value is subtracted from the most recent `game_date`
  present in the loaded appearance data, not from "today." This keeps
  behavior stable against frozen bundle snapshots — rerunning later produces
  the same result while the bundle is unchanged.
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

`engine/` contains deterministic selection, aggregation, comparison, and
labeling over producer-emitted facts. Specialists and the writer never
recompute PitchingPlus predictions or reconstruct data from raw sources.

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

`PitcherContext` is a Pydantic model assembled from one canonical frame. It
carries pitcher identity and role, fastball and arsenal summaries, modeled
execution metrics, P/S intermediate probabilities, formal Location+, emitted
spatial distributions, 13-outcome attribution, release and arm-slot shape,
contact/platoon/first-pitch/workload summaries, cross-season comparisons,
calibration evidence, a closed capability block, and the manifest-backed fact
registry.

### `to_prompt()` — 16 ordered sections

`PitcherContext.to_prompt()` delegates to `prompt_builder.py`. Empty sections
are skipped. The order is:

1. title;
2. temporal context;
3. deterministic executive context summary;
4. role;
5. primary fastball;
6. arsenal;
7. modeled execution;
8. P/S intermediate probabilities;
9. model validation and uncertainty;
10. release point;
11. pitch shape versus arm-slot expectation;
12. contact quality;
13. platoon shifts;
14. first-pitch tendencies;
15. recent appearances; and
16. year-over-year comparison.

The prompt also carries typed fact-registry lineage. Unsupported classes remain
explicitly unavailable rather than being synthesized from nearby data.

### Specialist-only evidence

The 13-outcome attribution table is not rendered into the shared prompt.
`_build_runvalue_input` supplies it only to the run-value specialist. Formal
Location+ and spatial distributions likewise reach the location handoff under
their exact emitted semantics. Keeping evidence scoped prevents agents from
turning unrelated aggregates into model drivers.

## Scout (`scout.py`)

`scout.py` is the no-LLM triage layer. It scans recent appearances and
scores each one on a heuristic signal table, so the expensive narrative
pipeline only runs on appearances that look interesting.

### Scored signal registry

`_WEIGHTS` defines the following emitted and reserved signal weights:

| Signal | Weight | Threshold | Interpretation |
|---|---|---|---|
| `new_pitch` | 4.0 | Season usage `< 1%` and game usage `> 5%` | A new pitch type appeared at meaningful volume |
| `velo_decline` | 3.5 | Fastball velocity falls `>= 1.5 mph` from first to last outing third, with `>= 9` fastballs | Within-outing velocity decline |
| `splus_lplus_level_gap` | 3.5 | `S+ >= 110` and `L+ <= 80` on the same pitch | A sufficiently sampled S+/L+ grade gap |
| `location_grade_surge` | 3.5 | Season `L+ < 90`, appearance `L+ >= 110` | Location+ grade change versus season |
| `velo_delta` | 3.0 | `>= 1.5 mph` from season fastball average | Fastball velocity swing versus season |
| `splus_lplus_divergence` | 3.0 | `S+` and `L+` deltas each `>= 10 pts`, opposite signs | Opposing S+/L+ grade changes on one pitch |
| `dropped_pitch` | 3.0 | Season usage `>= 10%` and game usage `0%` | Established pitch was absent |
| `pplus_swing` | 2.5 | `>= 15 pts` from season P+ | Overall P+ spike or decline |
| `pplus_lplus_split` | 2.5 | `P+ >= 105` and `L+ < 85` at appearance level | Appearance-level P+/L+ grade split |
| `spin_drop` | 2.0 | Fastball spin is at least `1.5` robust standard deviations below the leave-one-game-out reference | Fastball spin decline |
| `usage_shift` | 2.0 | `>= 8 pp` pitch-type usage change from season | Mix shift on any pitch type |
| `hard_hit_spike` (reserved) | 1.5 | none | No current emitter |
| `workload_flag` | 1.0 | `>= 3` consecutive calendar days pitched | Reliever workload state |

**About `hard_hit_spike`.** The entry exists in the `_WEIGHTS` dict at
`scout.py:37`, but no code path in `scout.py` emits a `Signal` with
that name — it is a documented stub awaiting implementation. The other
scout signals each have a dedicated `_check_*` helper called from
`scout_appearances`; `hard_hit_spike` does not. Do not assume it fires.

Each fired `Signal` carries `name`, `weight`, and a human-readable
`detail` line. `ScoredAppearance.score` is the sum of fired weights.

## Curator (`curator.py`)

The `--curate` flag on `pitcher-narratives scoreboard` sends the scored appearances
to an LLM via `curate_appearances` in `curator.py`, using the provider
selected by `--provider`. The curator's job is editorial selection: it
picks the 3–5 most compelling stories from the top of the heuristic
ranking and writes short framing blurbs.

## Pipeline (`pipeline.py`)

`pipeline.py` contains the sole report generation path — there is no
single-agent or non-bundle fallback. The historically named
`generate_pipeline_streaming` entry point runs a buffered pipeline; only the
CLI prints the final result.

### Phases 1–1.5 — four typed specialists and audits

The four specialists are `stuff`, `location`, `runvalue`, and `trends`.
`run_spine_core` runs the first three concurrently and audits each against its
exact input. `run_spine_tail` runs trends for the selected temporal frame,
audits it, and joins it to the reusable core.

| Specialist | Tier | temp | max_tokens | Prompt |
|---|---|---|---|---|
| `stuff` | Pro | 0.3 | LARGE (4096) | `_STUFF_SPECIALIST_PROMPT` |
| `location` | Mini | 0.3 | LARGE (4096) | `_LOCATION_SPECIALIST_PROMPT` |
| `runvalue` | Mini | 0.3 | LARGE (4096) | `_RUNVALUE_SPECIALIST_PROMPT` |
| `trends` | Mini | 0.3 | MEDIUM (2048) | `_TREND_SPECIALIST_PROMPT` |

Specialist agents return `SpecialistAnalysisDraft`; deterministic code resolves
citations and validates the final `SpecialistAnalysis`. The auditor returns
typed `AuditResult` flags. Flagged specialists are revised and re-audited. A
provider failure, invalid draft, leaked internal tag, or residual flag marks
that specialist unavailable; raw or generated fallback prose is not handed to
downstream synthesis.

### Phase 1.75 — signal extractor

The signal extractor runs only when all four specialist analyses are verified.
It returns typed, evidence-bound `KeySignals`. Provider failure, schema failure,
or invalid provenance leaves signals explicitly unavailable; it never promotes
uncited prose into evidence.

### Phases 2–2.5 — buffered narrative validation

The Pro-tier writer receives the four verified analyses plus any verified key
signals and returns `NarrativeArtifactDraft`. No draft is streamed. The shared
renderer then:

1. resolves every claim and fact citation into a deterministic
   `NarrativeArtifact`;
2. runs the anchor revision loop against specialist synthesis;
3. runs the capsule audit against producer-backed ground truth;
4. re-anchors any fact-revised capsule;
5. performs a detection-only final audit to catch reconciliation regressions;
   and
6. fails closed to an unavailable narrative when no clean verdict exists.

Only after the final capsule is verified does `_run_summaries` create the
executive summary. The summary is itself a typed artifact whose claims must be
a subset of the final capsule's verified claims.

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

#### Artifact freshness and reconciliation

Anchor checks measure editorial coverage against the verified specialist
synthesis; capsule audits measure factual and semantic correctness against
producer-backed evidence. Anchor is never presented as factual verification.

Every writer or fact-revision mutation invalidates the prior anchor verdict.
After a fact revision, `_reconcile_anchor_warnings` anchors the rewritten text,
spends any remaining bounded revision budget, and performs a detection-only
fact re-audit. A re-anchor exception appends `AUDIT_FAILED` and withholds the
capsule; it cannot reuse the clean verdict for an older artifact. If a
reconciliation revision regresses facts, the pipeline reverts to the
fact-verified text and retains the anchor verdict for that exact text.

`is_unverified` gates empty output, residual fact flags, value-parity failures,
reader claim/metric failures, and correctness anchor categories
(`MISSED_SIGNAL`, `DIRECTION_ERROR`, `UNSUPPORTED`, `OVERSTATED`).
`UNDERWEIGHTED` remains editorial advice. Summary generation runs only from the
final materialized capsule artifact, and invalid or wrong-shape summaries are
unavailable rather than recovered from generated residue.

#### Temporal frames

In changes mode two baselines coexist: recent-vs-season deltas in the context
tables and the code-computed recent-vs-prior block. The capsule fact-check's
ground truth includes BOTH (the frame block is threaded in exactly as the
trends specialist saw it), and the auditor is instructed that a claim matching
either baseline is grounded — it must never "correct" a number from one frame
into the other. The anchor receives changes-mode guidance to the same effect,
and to reserve MISSED_SIGNAL/UNDERWEIGHTED for signals that describe a change.

## Reader claim guard

`check_hallucinated_metrics` deterministically checks the generated artifact
for unknown metrics, discouraged outcome-stat language, and claim classes
whose typed capabilities or citations are unavailable. These warnings gate the
verification stamp and exit status. CLI diagnostics run against the generated
artifact only — never against the separately validated deterministic model
explainer — and stay off the reader stream unless requested with `-v` or
`--diagnostics-file`.

## Release acceptance

`make release-acceptance` is the clean-checkout cross-repository integrity gate.
It runs the deterministic `FunctionModel` surface and manifest-loader contracts,
then runs PitchingPlus's canonical metric-semantics, evaluation, archive, schema,
and output-bundle contract tests in the sibling producer checkout.

The acceptance fixture covers report, changes, recap, morning, ask, and
diagnostics policy; manifest-only data ingress; structured audit output;
reader-claim rejection; and fail-closed verification banners. Diagnostics
inspect artifacts but never inject the deterministic model explainer into the
reader stream. Producer tests remain authoritative for P/S/L formulas and
manifest publication; consumer tests prove those versioned artifacts survive
selection, composition, and validation without a raw-data fallback.

## Caching and prompt cache breakpoints

`pydantic_ai.CachePoint` is used in two distinct layers. Each specialist
input and each anchor-flavoured message is a `list[str | CachePoint]`
rather than a plain string, which lets the pipeline declare cache
boundaries explicitly.

**Specialist inputs (4 places in `pipeline.py`).** `_build_stuff_input`,
`_build_location_input`, `_build_runvalue_input`, and `_build_trend_input`
return a stable manifest-backed prefix, `CachePoint()`, and variable
pitch/frame evidence. The producer-backed prefix can be reused while the
pitch-specific tail changes.

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
| `claude` | `anthropic:claude-sonnet-4-6` | `anthropic:claude-haiku-4-5` |
| `gemini` | `google-gla:gemini-3.5-flash` | `google-gla:gemini-flash-latest` |

### Token budgets

- `TOKEN_BUDGET_SMALL = 1024` — specialist auditor and anchor
- `TOKEN_BUDGET_MEDIUM = 2048` — trends specialist, capsule auditor, summary,
  signal extractor
- `TOKEN_BUDGET_LARGE = 4096` — writer, answerer, stuff/location/run-value
  specialists

### Role → tier / temp / max_tokens / thinking cap

`make_pipeline_agents` assigns each role via `cap_thinking`, which
clamps the user-supplied `--thinking` level to a per-role ceiling.

| Role | Tier | temp | max_tokens | Thinking cap |
|---|---|---|---|---|
| Stuff specialist | Pro | 0.3 | LARGE | `medium` |
| Location / RunValue | Mini | 0.3 | LARGE | `medium` |
| Trends | Mini | 0.3 | MEDIUM | `medium` |
| Writer | Pro | 0.7 | LARGE | *(user level, uncapped)* |
| Specialist Auditor | Mini | 0.1 | SMALL | `low` |
| Capsule Auditor | Mini | 0.1 | MEDIUM | `medium` |
| Anchor | Mini | 0.1 | SMALL | `low` |
| Executive Summary | Mini | 0.3 | MEDIUM | disabled |
| Signal Extractor | Mini | 0.3 | MEDIUM | `medium` |

The writer is intentionally uncapped — it's the one place where the
user's `--thinking high` or `--thinking xhigh` actually matters for
prose quality. Every other role is capped because extra thinking on
short structured outputs mostly just burns tokens.

### Provider quirks (`make_model_settings`)

- **Gemini** uses `GoogleModelSettings`; `high`/`xhigh` request high thinking,
  lower CLI levels request low thinking, and pure distillation can disable it.
- **Claude** disables thinking for mini models and small output budgets.
  Supported effort aliases are normalized before the request.

## Grade Q&A (`qa.py`)

`pitcher-narratives ask` is a first-class output surface for focused questions
of the form “why does [pitcher]'s [pitch] grade [value] [P+/S+/L+]?” The parser
resolves pitcher and pitch identity, then `build_grade_input` supplies only the
named grade family's typed same-frame facts, capability block, model
probabilities, emitted references, formal Location+ evidence, and bounded
calibration provenance.

The Pro-tier answer agent returns generated prose only. It may interpret cited
evidence, but cannot invent feature weights, decision traces, model drivers,
command, intent, target execution, tunneling, biomechanics, or observed hitter
behavior. The answer is audited against the exact grade input. Flagged answers
are revised and re-audited; a residual flag fails closed.

After a clean answer, `qa.answer_question` appends the same versioned
deterministic model-and-data-boundary explanation used by report and changes.
That section is composed outside the audited generated answer. Calibration
language reports only the manifest-covered evaluation artifact's schema/model/
feature versions, population, as-of date, holdout year, and row count; absent
evidence yields an explicit no-confidence statement.

## End-to-end diagram

```
PitchingPlus versioned bundle
        |
        v
load_pitchingplus_bundle -> canonical frame -> PitcherContext + FactRegistry
        |
        v
+---------------------------------------------------+
|  Four specialists + per-specialist audit         |
|    core: stuff | location | runvalue              |
|    tail: trends (mode-specific frame)             |
+---------------------------------------------------+
        |
        v
+---------------------------------------------------+
|  Verified signal extraction                      |
|    unavailable when specialist handoff is partial |
+---------------------------------------------------+
        |
        v
+---------------------------------------------------+
|  Buffered typed writer artifact                   |
|    anchor -> fact audit -> re-anchor -> guard     |
+---------------------------------------------------+
        |
        v
+---------------------------------------------------+
|  Final verified capsule -> typed summary          |
|  diagnostics inspect generated artifacts only     |
+---------------------------------------------------+
        |
        v
deterministic model explanation (report/changes; optional)
        |
        v
CLI reader output + separate diagnostics
```

Every generated factual statement traces to a manifest-covered row and exact
frame. Validation failure removes the narrative rather than relabeling
unverified generated prose as evidence.
