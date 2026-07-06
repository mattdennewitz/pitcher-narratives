# Pitcher Narratives

Pitcher Narratives turns Statcast and Pitching+ data into LLM-written scouting
reports for MLB pitchers. Every metric arrives at the model pre-computed and
pre-tagged — window-vs-season direction, z-score outlier flags, small-sample
caveats — so the model spends its effort on insight, not arithmetic.

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
- Local data files (no Baseball Savant calls happen at runtime — everything is
  served from disk):
  - `var/statcast/<year>.parquet` — pitch-level Statcast data (e.g.
    `var/statcast/2025.parquet`, `var/statcast/2026.parquet`)
  - `var/aggs/<year>-<grain>.csv` — pre-computed Pitching+ CSVs per pitcher, pitch
    type, appearance, and platoon split, plus `var/aggs/RV_df.csv` (the run-values
    lookup)
  - See [Syncing the data](#syncing-the-data) to pull these from R2, and
    `METHODOLOGY.md` for the full source breakdown.

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
| `pitcher-narratives` | `pitcher_narratives.cli:main` | `report` (one pitcher), `morning` (daily digest), and `scoreboard` (no-LLM triage) subcommands |

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
| `--no-explain-model` | flag | off | Skip S+/L+/P+ model explanations in the capsule (repeat readers) |
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
/ `Recap`), the final capsule (printed once — the pipeline buffers the writer
output rather than streaming it), a `**Verification:**` stamp (✅ verified / ⚠️
UNVERIFIED with counts), and — for `report`/`changes` only — a distilled
`## Executive Summary` (recap's capsule is already the short-form deliverable,
so it skips distillation).

The QA/diagnostics appendix (`### Stuff Analysis`, `### Data Audit`,
`### Capsule Fact-Check`, `### Value Parity`, `### Anchor Check`,
`### Hallucination Check`) is **off the reader stream**: pass `-v` to print it to
stderr, or `--diagnostics-file PATH` to write it as JSON (one object per mode).

If any mode ships an **unverified** capsule (residual anchor/fact warnings after
the revision budget is spent), an `UNVERIFIED` banner is printed to stderr for
that mode and the process exits non-zero — so CI catches a bad report instead of
treating it as clean. Each run also writes
`data-{pitcher}-{provider}-pipeline.md` with the rendered prompts;
`--print-prompts` dumps that content to stderr and exits without calling the
model — useful when iterating on prompt wording.

### Narration modes

A **narration mode** selects the output shape and temporal frame the single
writer voice (`WRITER_VOICE`) renders in. The voice — tone, scouting register,
how deep to explain the grading model — never changes; the mode picks
structure, length, and what temporal frame the writer sees.

| Mode | Temporal frame | Deliverable | Notes |
|---|---|---|---|
| `report` (default) | recent vs season | `## Executive Summary` bullets + 350–600 word flowing prose capsule (3–5 paragraphs) | Today's full report path; deepest validation budget |
| `changes` | recent vs **prior** window | `## Executive Summary` bullets + 250–450 word change-focused write-up | Two-frame engine: code-computes recent-`-n`-vs-prior-`--prior` deltas and hands the writer a "Recent vs Prior Window" comparison block |
| `recap` | recent vs season | 60–120 word (3–5 sentence) capsule only — no bullets | Shallower anchor loop (less prose to drift); the mode `pitcher-narratives morning` uses per pick |

Pass one mode, or several comma-separated (`--mode report,changes`); each mode
renders its own capsule and section block, and the run exits non-zero if *any*
of them is unverified. A duplicated mode id is de-duplicated, not double-run.

#### The three deliverables

Every deliverable is written in the same single voice — a field-facing
analyst voice that explains the model as it goes, never cheerleads, and
never admires the grading system for its own sake. Only the mode changes:

- **`report`** — the full scouting read: an `## Executive Summary` of bullets
  distilled from the capsule, followed by a 350–600 word, 3–5 paragraph prose
  narrative. Prose only (no headings, no bullet lists, no tables inside the
  capsule itself). Leads with the model's single most important read on the
  pitcher; explains S+/L+/P+ on first use (unless `--no-explain-model`).
- **`changes`** — the same executive-summary bullets, then a 250–450 word
  change log framed against the **prior** window: leads with the single
  biggest shift, reports only what moved, and omits stable traits unless they
  frame a change.
- **`recap`** — a short 60–120 word (3–5 sentence) capsule and nothing else.
  No executive summary, no bullets, no headings — the capsule *is* the whole
  deliverable, which is why distillation is skipped. This is the shape
  `pitcher-narratives morning` writes for every digest pick.

Every mode also produces the same QA/diagnostics appendix (`### Stuff
Analysis`, `### Data Audit`, `### Capsule Fact-Check`, `### Value Parity`,
`### Anchor Check`, and — when triggered — `### Hallucination Check`),
available off the reader stream via `-v` or `--diagnostics-file`.

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

The heuristic looks for velocity swings, P+/S+/L+ divergences, new or dropped
pitches, usage shifts, development candidates, and reliever workload flags.
Per-pitch-type grade signals (the S+/L+ divergence and "stuff without feel"
checks) require at least a handful of pitches of that type, so a one-off pitch
can't manufacture a phantom signal. See `METHODOLOGY.md` for the full signal
table and weights.

## The morning digest

`pitcher-narratives morning` runs the full editorial pipeline:

1. **Scout** — score every appearance in the window (`scout.py`).
2. **Select** — the curator LLM (`curator.py`) picks a slate, assigning each
   pick one of four editorial **categories** and capping it at **5 picks per
   category** (no minimum), with a prompt nudge toward variety so the slate
   isn't a block of look-alikes:

   | Category | Meaning |
   |---|---|
   | `clean_breakout` | Velocity gain + a real stuff jump, backed by data |
   | `lab_project` | Top-tier raw stuff, command not there yet |
   | `identity_crisis` | A radically altered pitch mix — plan or problem? |
   | `red_flag` | An anomaly that may be a tracking artifact or a warning sign |

3. **Write** — concurrent writer agents produce one capsule per pick
   (`digest.py`), each run through the `recap` narration mode so the digest
   shares the same validated capsule path as `report --mode recap`.
4. **Assemble** — a deterministic markdown digest, grouped by category.

Each run writes `<out>/<game-date>/`: `digest.md`, `slate.json`, `briefing.md`,
and `usage.json` (token + cost accounting). On a quiet day with no interesting
appearances, no digest is written.

## Syncing the data

The Statcast parquet and the aggregate CSVs live in Cloudflare R2 (bucket
`pitchingplus`). The Makefile pulls them via `wrangler` (requires
`wrangler login`):

```bash
make pull-data        # both of the below
make pull-statcast    # var/statcast/<year>.parquet
make pull-aggs        # latest dated aggregate snapshot -> var/aggs/
```

`pull-aggs` walks back from today to the most recent daily snapshot, downloads
its zip, and unzips the CSVs into `var/aggs/`. **Keep the two in sync** — run
`make pull-data` rather than one half. If the parquet lags the aggregates, the
role map can't classify recent starts and the scout will warn that appearances
are defaulting to RP (run `make pull-statcast`).

## Report pipeline at a glance

`pitcher-narratives report` runs the pipeline in `pipeline.py`, in five phases:

- **Phase 1** — five specialist agents run in parallel: `stuff`, `location`,
  `runvalue`, `trends`, `game_shape`.
- **Phase 1.5** — a per-specialist auditor runs in parallel; flagged
  specialists are re-run with corrections, so the writer never sees flawed
  prose.
- **Phase 1.75** — a signal extractor reads the clean specialist outputs into a
  `KeySignals` object.
- **Phase 2** — the writer (streamed) and the executive-summary agent run in
  parallel from the same synthesis.
- **Phase 2.5** — the anchor check and fact-check validate the capsule; unclean
  drafts are revised, fact revisions carrying ground truth back to the writer,
  up to a per-mode budget before any remaining warnings ship. Each mode sets its
  own `anchor_depth`/`fact_depth` (a `ValidationPolicy`): `report` and `changes`
  use the full budget, `recap` a shallower one. These caps are provisional and
  calibrated from the `--metrics-out` records — see
  [`docs/calibration.md`](./docs/calibration.md). When a fact revision rewrites
  the capsule, the pipeline re-anchors the new text and spends any remaining
  anchor budget on *reconciling* revisions that may not change numeric values
  (ground truth outranks the synthesis); a detection-only re-audit guards the
  result, reverting to the fact-revised capsule if reconciliation regressed a
  number.

For `changes` mode, a code-computed recent-vs-prior comparison (`frame_delta.py`)
is threaded into the trends specialist and the writer before Phase 2.

`METHODOLOGY.md` has the deep version: agent tiers, model settings, prompt
structure, cache breakpoints, and the anchor-check taxonomy.

## Project layout

```
pitcher-narratives/
├── src/pitcher_narratives/
│   ├── cli.py            # pitcher-narratives entry (report + morning + scoreboard)
│   ├── data.py           # Statcast + Pitching+ loading pipeline
│   ├── engine/           # computation subpackage (baselines, arsenal,
│   │                     #   execution, workload, mechanics, contact, tto,
│   │                     #   attribution) behind a re-export facade
│   ├── context.py        # PitcherContext data model + assembly
│   ├── prompt_builder.py # renders a PitcherContext into prompt markdown
│   ├── pipeline.py       # multi-specialist report pipeline (phases 1–2.5)
│   ├── anchor.py         # anchor-check prompt + result models
│   ├── signals.py        # KeySignals model + extractor prompt
│   ├── resolver.py       # fuzzy pitcher name resolution
│   ├── shape.py          # arm-slot / pitch-shape analysis
│   ├── scout.py          # appearance interest scoring (no LLM)
│   ├── curator.py        # LLM slate selection (category-bucketed)
│   ├── digest.py         # story cues + concurrent writers + assembly
│   ├── morning.py        # morning-run orchestration
│   ├── personas.py       # single writer voice + narration modes (report/changes/recap)
│   ├── costs.py          # token + dollar usage tracking
│   ├── config.py         # providers, model settings, thinking caps
│   ├── agent_skills.py   # pydantic-ai skills toolset wiring
│   ├── bench/            # LLM benchmark harness
│   └── skills/           # agent skill definitions
├── var/                  # gitignored local data
│   ├── aggs/             # Pitching+ CSVs + RV_df.csv
│   └── statcast/         # per-year Statcast parquet
├── morning-runs/         # digest artifacts (gitignored output)
├── tests/                # pytest suite
├── Makefile              # run / scout / curate / pull-* shortcuts
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
make pull-data      # refresh var/statcast/ and var/aggs/ from R2
```

## See also

- [METHODOLOGY.md](./METHODOLOGY.md) — deep technical walkthrough of the data
  sources, the computation engine, the context renderer, the report pipeline
  phases, the anchor check, the hallucination guard, the model tier table, and
  the Q&A analyst.
