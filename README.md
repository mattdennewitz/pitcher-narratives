# Pitcher Narratives

Pitcher Narratives turns versioned PitchingPlus output bundles into
LLM-written scouting reports for MLB pitchers. Raw Statcast enters
PitchingPlus, not this application. Every metric reaches an agent as a typed,
manifest-covered fact with pre-computed frames, baselines, and sample context,
so models interpret evidence rather than reconstructing arithmetic.

It works at two scales:

- **One pitcher** — a full scouting capsule for a single arm's recent
  appearances (`pitcher-narratives report`).
- **The whole league, every morning** — an editorial digest that scouts the
  day's appearances, selects the most compelling stories by category, and
  writes a capsule for each (`pitcher-narratives morning`).

Every single-pitcher run is driven by a **narration mode** — the same data spine,
one writer voice, rendered as a full `report`, a change-focused `changes`
write-up, or a short `recap` capsule. Pick one (or several at once) with
`--mode`. See [Narration modes](#narration-modes).

## Requirements

- Python 3.14+ (pinned in `.python-version`, enforced by
  `requires-python = ">=3.14"` in `pyproject.toml`)
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- An API key for at least one supported provider, exported or placed in a
  `.env` file at the project root (loaded automatically via `python-dotenv`):
  - `GEMINI_API_KEY` for `--provider gemini` (the default)
  - `ANTHROPIC_API_KEY` for `--provider claude`
- A local, versioned PitchingPlus output bundle under `var/aggs/`. Its manifests
  cover `all_pitches`, aggregate tables, reference populations, and any emitted
  spatial, component-attribution, or registered model-evaluation artifacts.
  Pitcher Narratives does not read raw Statcast, run-value lookup files, model
  files, or unmanifested auxiliary data. See
  [Syncing the data](#syncing-the-data) and `METHODOLOGY.md`.

Baselines and league norms are restricted to **MLB regular-season + postseason**
data; minor-league and WBC rows are filtered out so they never skew the norms.

## Install / quick start

```bash
uv sync
uv run pitcher-narratives report -p 657277 -n 10
```

`-n/--recent` is the analysis window measured in **most-recent appearances**
(default `10`), not calendar days. Add `--mode changes` for a
what-moved write-up, or `--mode recap` for a short capsule — details in
[Narration modes](#narration-modes).

## The CLIs

The package installs one entry point via `[project.scripts]`:

| Script | Source | Purpose |
|---|---|---|
| `pitcher-narratives` | `pitcher_narratives.cli:main` | `report`, `ask`, `morning`, and `scoreboard` subcommands |

### `pitcher-narratives report`

Runs the multi-agent specialist pipeline end-to-end for a single pitcher over a
window of recent appearances, in one or more [narration modes](#narration-modes).

| Flag | Type | Default | Notes |
|---|---|---|---|
| `-p`, `--pitcher` | int | *required* | MLB pitcher ID |
| `-n`, `--recent` | int | `10` | Analysis window in **most-recent appearances** (not days) |
| `--mode` | str | `report` | Comma-separated modes: `report` \| `changes` \| `recap` |
| `--prior` | int | `10` | Size of the prior window (appearances) for `changes` mode's recent-vs-prior comparison; ignored by `report`/`recap` |
| `--metrics-out` | path | *none* | Append per-mode calibration records as JSONL (see [`docs/calibration.md`](./docs/calibration.md)) |
| `-v`, `--verbose` | flag | off | Print pitcher summary **and** the QA/diagnostics appendix to stderr (default stdout is the reader report only) |
| `--print-prompts` | flag | off | Renders the pipeline prompts to stderr and exits without calling the LLM |
| `--provider` | enum | `gemini` | `gemini` \| `claude` |
| `--thinking` | enum | `medium` | `minimal` \| `low` \| `medium` \| `high` \| `xhigh` |
| `--no-explain-model` | flag | off | Omit the deterministic model-and-data-boundary section for repeat readers |
| `--diagnostics-file` | path | *none* | Write the QA/diagnostics appendix as JSON (one object per mode); stdout stays the reader report |

```bash
# Default full report over the last 10 appearances
uv run pitcher-narratives report -p 657277 -n 10 --provider claude --thinking high

# What changed in the last 5 starts vs the 10 before them
uv run pitcher-narratives report -p 657277 -n 5 --prior 10 --mode changes

# All three modes in one run, with calibration records captured
uv run pitcher-narratives report -p 657277 --mode report,changes,recap --metrics-out run.jsonl
```

Stdout emits one labeled block per requested mode, in `--mode` order — the
**reader document only**: `# <Mode Title>` (`Scouting Report` / `Change Report`
/ `Recap`), the final provenance-bound capsule, the separate deterministic
model-and-data-boundary section for `report`/`changes` unless disabled, a
`**Verification:**` stamp, and — for `report`/`changes` only — a distilled
`## Executive Summary`. The writer is buffered; generated prose is printed
once only after validation. Recap is already the short-form deliverable.

The QA/diagnostics appendix (`### Stuff Analysis`, `### Data Audit`,
`### Capsule Fact-Check`, `### Value Parity`, `### Anchor Check`,
`### Hallucination Check`) is **off the reader stream**: pass `-v` to print it to
stderr, or `--diagnostics-file PATH` to write it as JSON (one object per mode).

If a mode has no validated capsule, or any fact, value-parity, reader-claim,
or gating anchor check remains unresolved, the mode is stamped `UNVERIFIED`,
the process exits non-zero outside explicit test mode, and stderr names the
failure. Provider/audit failure never upgrades missing generated prose to a
verified report.
Every run also writes `data-{pitcher}-{provider}-pipeline.md` with the rendered prompts;
`--print-prompts` dumps that content to stderr and exits without calling the
model — useful when iterating on prompt wording.

### Narration modes

A **narration mode** selects the output shape and temporal frame the single
writer voice (`WRITER_VOICE`) renders in. The voice and evidence rules never
change; the mode picks structure, length, temporal frame, validation depth, and
whether the validated deterministic model explanation is appended.

| Mode | Temporal frame | Deliverable | Notes |
|---|---|---|---|
| `report` (default) | recent vs season | 350–600 word flowing prose capsule (3–5 paragraphs) + verification stamp + `## Executive Summary` bullets | Today's full report path; deepest validation budget |
| `changes` | recent vs **prior** window | 250–450 word change-focused write-up + verification stamp + `## Executive Summary` bullets | Code computes recent-`-n`-vs-prior-`--prior` deltas and hands the writer a "Recent vs Prior Window" comparison block |
| `recap` | recent vs season | 60–120 word (3–5 sentence) capsule + verification stamp; no summary bullets | Shallower anchor loop; the morning digest uses this mode per pick |

Pass one mode, or several comma-separated (`--mode report,changes`); each mode
renders its own capsule and section block, and the run exits non-zero if *any*
of them is unverified. A duplicated mode id is de-duplicated, not double-run.

#### The three deliverables

Every deliverable uses the same field-facing analyst voice. Agents synthesize
only cited pitcher evidence; they do not improvise model definitions, feature
weights, decision traces, or causal explanations. Only the mode changes:

- **`report`** — the full scouting read: a 350–600 word, 3–5 paragraph
  provenance-bound narrative, the verification stamp, then an
  `## Executive Summary` distilled only from the final validated capsule.
  The deterministic model explanation is appended outside the generated
  artifact unless `--no-explain-model` is set.
- **`changes`** — a 250–450 word change log framed against the **prior**
  window, followed by its verification stamp and summary bullets. It leads
  with the single biggest shift, reports only what moved, and omits stable
  traits unless they frame a change.
- **`recap`** — a short 60–120 word (3–5 sentence) capsule plus verification
  stamp. No executive summary or generated headings; the capsule is already
  the brief. This is the shape `pitcher-narratives morning` writes for each
  digest pick.

Every mode also produces the same QA/diagnostics appendix (`### Stuff
Analysis`, `### Data Audit`, `### Capsule Fact-Check`, `### Value Parity`,
`### Anchor Check`, and — when triggered — `### Hallucination Check`),
available off the reader stream via `-v` or `--diagnostics-file`.

### Deterministic Pitching+ explanation

`report`, `changes`, and `ask` append a versioned deterministic explanation
outside generated prose. `recap` and `morning` intentionally omit it. The
canonical contract is:

- PitchingPlus converts probabilities for 13 pitch outcomes to expected run
  value using count-specific run values.
- P includes realized plate location. S omits realized `plate_x`/`plate_z` but
  retains release position/extension, arm angle, derived acceleration/spin
  coordinates, handedness/platoon, fastball-velocity context, coarse repertoire
  shares, and count processing. Exported S marginalizes outcomes with
  training-sample `P(count | broad pitch class, same_side)`, then applies
  actual-count run-value scoring. Formal L uses hidden same-count S.
- Location+ is the P expected-run-value contrast with count-matched S:
  associative realized-location evidence, not command, control, intent, target
  execution, or causal intervention.
- P, S, and L each center on their own same-scoring-season MLB regular-season
  pitch-weighted mean. 100 is average and higher is better. The displayed
  20–80 value is uncapped `plus - 50`, not SD-scaled.
- Conditional expected rates are means of per-pitch ratios. Group grades have
  no model-level minimum sample or shrinkage.
- Direct predictor inputs exclude explicit pitch/player identity,
  sequence/tunnel geometry, target, park/weather, game state, observed
  batted-ball result, raw spin rate, and raw pfx fields. These grades are
  predictive outputs, not causal feature attributions.
- Raw Statcast enters PitchingPlus. PitchingPlus emits a manifest-covered
  bundle; deterministic Narrative code may select, aggregate, compare, and
  label emitted facts, and agents may interpret only cited facts.

### `pitcher-narratives morning`

The editorial workflow: scout the day's appearances → select a slate by
category → write a capsule for each → assemble a digest. See
[The morning digest](#the-morning-digest) below.

| Flag | Type | Default | Notes |
|---|---|---|---|
| `-w`, `--window` | int | `1` | Days to scan back from the most recent game date |
| `--candidates` | int | `25` | Scout candidates per role fed to the selector |
| `--min-pitches` | int | `20` | Minimum pitches for an appearance to be scored |
| `--provider` | enum | `gemini` | `gemini` \| `claude` |
| `--starters-only` | flag | off | Restrict the board to starting pitchers (role SP) before selection |
| `--out` | path | `morning-runs` | Output directory root |

```bash
uv run pitcher-narratives morning
```

### `pitcher-narratives scoreboard`

Cheap pre-filter that scans recent appearances, scores each on a heuristic (no
LLM), and prints the board. Optionally pipes the board to a curator LLM.

| Flag | Default | Notes |
|---|---|---|
| `-w`, `--window` | `1` | Days to scan (`1` = most recent game date only) |
| `--min-pitches` | `20` | Minimum pitches for an appearance to be scored |
| `--starters-only` | off | Restrict the board to starting pitchers (role SP) |
| `--format` | `md` | `table` (fixed-width) \| `md` (markdown board) \| `json` |
| `-n`, `--top` | `0` | Keep only the top N per role by score (`0` = no limit) |
| `--min-score` | `0.0` | Drop appearances below this interest score |
| `-v`, `--verbose` | off | In `table` format, show per-signal detail under each row |
| `--curate` | off | Send the board to the curator LLM and print the slate |
| `--provider` | `gemini` | `gemini` \| `claude` (used for `--curate`) |

```bash
uv run pitcher-narratives scoreboard -w 1 --format table -n 25 --min-score 5.0 -v
```

The heuristic looks for velocity and grade changes, new or absent pitches,
usage shifts, grade gaps, and reliever workload states. Per-pitch-type grade
signals require at least a handful of pitches of that type, so a one-off pitch
cannot manufacture an editorial signal. See `METHODOLOGY.md` for the full
signal registry and weights.

### `pitcher-narratives ask`

Answers a focused grade question for one named pitch, then appends the same
versioned deterministic explanation used by full reports:

```bash
uv run pitcher-narratives ask "why does Jared Jones's fastball grade 92 Stuff+?"
```

The agent answer is built from typed same-frame facts, capability states, and
PitchingPlus bundle evidence, then fact-checked before composition. It cannot
infer model drivers, command, intent, tunneling, target execution, or causal
mechanisms from aggregates.

## The morning digest

`pitcher-narratives morning` runs the full editorial pipeline:

1. **Scout** — score every appearance in the window (`scout.py`).
2. **Select** — the curator LLM (`curator.py`) picks a slate, assigning each
   pick one of six editorial **categories** and capping it at **5 picks per
   category** (no minimum):

   | Category | Meaning |
   |---|---|
   | `clean_breakout` | Velocity gain co-moving with higher P+ or S+ |
   | `location_breakout` | Location+ rose versus the supplied season norm |
   | `lab_project` | Well-sampled S+ above 130 with L+ below 80 |
   | `identity_crisis` | A materially altered pitch mix |
   | `velo_drop` | Fastball velocity loss co-moving with lower P+ or S+ |
   | `red_flag` | A supplied measurement conflict or explicit anomaly-policy hit |

3. **Write** — concurrent writer agents produce one capsule per pick
   (`digest.py`), each run through the `recap` narration mode so the digest
   shares the same validated capsule path as `report --mode recap`.
4. **Assemble** — a deterministic markdown digest, grouped by category.

Each run writes `<out>/<game-date>/`: `digest.md`, `slate.json`, `briefing.md`,
and `usage.json` (token + cost accounting). On a quiet day with no interesting
appearances, no digest is written.

## Syncing the data

Pitcher Narratives downloads PitchingPlus-produced bundles from Cloudflare R2.
`make pull-data` validates the latest dated snapshot, replaces only the seasons
included in that snapshot, preserves other installed seasons, validates the
complete supported-season set, and then atomically installs it under `var/aggs/`:

```bash
make pull-data
```

The loader validates manifest versions, checksums, declared seasons, artifact
schemas, calibration provenance, and frame compatibility before exposing any
rows. There is no consumer-side raw-Statcast sync path.

## Report pipeline at a glance

`pitcher-narratives report` runs the buffered pipeline in `pipeline.py`:

- **Phase 1 / 1.5** — four specialists (`stuff`, `location`, `runvalue`,
  `trends`) produce typed cited analyses. The frame-agnostic first three form a
  reusable core; trends is the frame-sensitive tail. Each output is audited
  against its exact producer-backed input, revised when flagged, and rejected
  when no clean verdict is available.
- **Phase 1.75** — the signal extractor runs only over the complete verified
  specialist handoff and returns typed, provenance-checked `KeySignals`.
- **Phase 2 / 2.5** — the writer returns a typed narrative artifact. The
  buffered draft passes anchor revision, ground-truth capsule audit, post-fact
  re-anchoring, and a detection-only regression audit. Failures close to an
  unavailable narrative rather than publishing generated prose as verified.
- **Final assembly** — only the final validated capsule is summarized. Value
  parity and hallucination diagnostics inspect generated artifacts. The
  versioned deterministic model explanation is composed afterward, outside the
  generated artifact and its claim bindings.

`report` and `changes` use the full validation budget; `recap` uses its shorter
mode-specific budget. Revision caps are measured by `--metrics-out`; they are
not claims of statistical confidence. For `changes`, a code-computed
recent-vs-prior comparison (`frame_delta.py`) is supplied to trends and the
writer.


`METHODOLOGY.md` has the deep version: agent tiers, model settings, prompt
structure, cache breakpoints, and the anchor-check taxonomy.

## Project layout

```
pitcher-narratives/
├── src/pitcher_narratives/
│   ├── cli.py            # report + ask + morning + scoreboard entry point
│   ├── data.py           # validated PitchingPlus bundle loader
│   ├── bundle_contract.py# producer manifest and artifact validation
│   ├── model_explainer.py# deterministic model/data-boundary templates
│   ├── engine/           # deterministic selection, aggregation, comparison
│   │                     #   and labeling over emitted facts
│   ├── context.py        # PitcherContext data model + assembly
│   ├── prompt_builder.py # renders typed context into prompt markdown
│   ├── pipeline.py       # four-specialist buffered validation pipeline
│   ├── qa.py             # focused, audited grade-question path
│   ├── anchor.py         # anchor-check prompt + result models
│   ├── signals.py        # KeySignals model + extractor prompt
│   ├── resolver.py       # fuzzy pitcher name resolution
│   ├── shape.py          # arm-slot / pitch-shape analysis
│   ├── scout.py          # appearance interest scoring (no LLM)
│   ├── curator.py        # LLM slate selection
│   ├── digest.py         # story cues + concurrent writers + assembly
│   ├── morning.py        # morning-run orchestration
│   ├── personas.py       # one writer voice + report/changes/recap modes
│   ├── costs.py          # token + dollar usage tracking
│   ├── config.py         # providers, model settings, thinking caps
│   ├── agent_skills.py   # runtime skills toolset wiring
│   ├── bench/            # LLM benchmark harness
│   └── skills/           # agent skill definitions
├── var/aggs/             # validated PitchingPlus output bundle
├── morning-runs/         # digest artifacts (gitignored output)
├── tests/                # pytest suite
├── Makefile              # run / scout / curate / pull-data shortcuts
└── pyproject.toml
```

## Dev commands

```bash
uv sync                  # install / update deps
uv run pytest            # run the test suite
uv run ruff check        # lint
uv run ty check src      # type-check
```

Makefile shortcuts:

```bash
make run            # uv run pitcher-narratives report -p 657277 -n 10
make scout          # uv run pitcher-narratives scoreboard -n 25 --min-score 5.0 --format table -v
make curate         # uv run pitcher-narratives scoreboard -n 25 --min-score 5.0 --curate
make pull-data      # validate and merge the latest PitchingPlus bundle from R2
make release-acceptance  # run deterministic consumer/producer boundary contracts
```

## See also

- [METHODOLOGY.md](./METHODOLOGY.md) — data boundary, deterministic
  transformations, prompt grounding, report validation, model contract,
  provider settings, and audited grade Q&A.
