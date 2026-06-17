# Pitcher Narratives

Pitcher Narratives turns Statcast and Pitching+ data into LLM-written scouting
reports for MLB pitchers. Every metric arrives at the model pre-computed and
pre-tagged — window-vs-season direction, z-score outlier flags, small-sample
caveats — so the model spends its effort on insight, not arithmetic.

It works at two scales:

- **One pitcher** — a full scouting capsule for a single arm's recent
  appearances (`pitcher-narratives report`), plus a triage scanner
  (`pitcher-scout`).
- **The whole league, every morning** — an editorial digest that scouts the
  day's appearances, selects the most compelling stories by category, and
  writes a capsule for each (`pitcher-narratives morning`).

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
uv run pitcher-narratives report -p 657277 -w 5
```

Or the Makefile shortcut, which wraps the same command:

```bash
make run   # uv run pitcher-narratives report -p 657277 -w 5
```

## The CLIs

The package installs two entry points via `[project.scripts]`:

| Script | Source | Purpose |
|---|---|---|
| `pitcher-narratives` | `pitcher_narratives.cli:main` | `report` (one pitcher) and `morning` (daily digest) subcommands |
| `pitcher-scout` | `pitcher_narratives.scout_cli:main` | Appearance triage + scoring |

### `pitcher-narratives report`

Runs the multi-agent specialist pipeline end-to-end for a single pitcher over a
lookback window.

| Flag | Type | Default | Notes |
|---|---|---|---|
| `-p`, `--pitcher` | int | *required* | MLB pitcher ID |
| `-w`, `--window` | int | `30` | Lookback in days |
| `-v`, `--verbose` | flag | off | Prints pitcher name, game dates, pitch counts to stderr before running |
| `--print-prompts` | flag | off | Renders the pipeline prompts to stderr and exits without calling the LLM |
| `--provider` | enum | `gemini` | `gemini` \| `claude` |
| `--thinking` | enum | `medium` | `minimal` \| `low` \| `medium` \| `high` \| `xhigh` |
| `--persona` | enum | `scout` | Writer voice: `scout` \| `analyst` \| `generic` |
| `--list-personas` | flag | off | Print available personas and exit |

```bash
uv run pitcher-narratives report -p 657277 -w 30 --provider claude --thinking high
```

Stdout is printed in this order: `# Scouting Report` (the writer's capsule,
streamed live) → `# Executive Summary` → `# Brief` (a 2-3 sentence
recent-appearance-vs-window summary, in the selected persona's voice) →
`# Stuff Analysis` → `# Data Audit` →
`# Anchor Check` → `# Hallucination Check` (emitted only when the post-pipeline
guard finds unknown metrics or traditional outcome stats). Each run also writes
`data-{pitcher}-{provider}-pipeline.md` with the rendered prompts;
`--print-prompts` dumps that content to stderr and exits without calling the
model — useful when iterating on prompt wording.

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
| `--persona` | enum | `scout` | Writer voice |
| `--out` | path | `morning-runs` | Output directory root |

```bash
uv run pitcher-narratives morning
```

### `pitcher-scout`

Cheap pre-filter that scans recent appearances, scores each on a heuristic (no
LLM), and prints a ranked table. Optionally pipes the top results to a curator
LLM.

| Flag | Default | Notes |
|---|---|---|
| `-w`, `--window` | `1` | Days to scan (`1` = most recent game date only) |
| `-n`, `--top` | `20` | Max results per role to display |
| `--min-pitches` | `20` | Minimum pitches for an appearance to be scored |
| `--min-score` | `0.0` | Minimum interest score to display |
| `-v`, `--verbose` | off | Show per-signal detail under each row |
| `--curate` | off | Send top results to the curator LLM and print the slate |
| `--provider` | `gemini` | `gemini` \| `claude` (used for `--curate`) |

```bash
uv run pitcher-scout -w 1 -n 25 --min-score 5.0 -v
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
   (`digest.py`).
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
- **Phase 2.5** — the anchor check validates the capsule; unclean drafts are
  revised up to `MAX_REVISIONS = 3` passes before any remaining warnings ship.

`METHODOLOGY.md` has the deep version: agent tiers, model settings, prompt
structure, cache breakpoints, and the anchor-check taxonomy.

## Project layout

```
pitcher-narratives/
├── src/pitcher_narratives/
│   ├── cli.py            # pitcher-narratives entry (report + morning)
│   ├── scout_cli.py      # pitcher-scout entry
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
│   ├── personas.py       # writer personas (scout / analyst / generic)
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
make run            # uv run pitcher-narratives report -p 657277 -w 5
make scout          # uv run pitcher-scout -n 25 --min-score 5.0 -v
make curate         # uv run pitcher-scout -n 25 --min-score 5.0 --curate
make pull-data      # refresh var/statcast/ and var/aggs/ from R2
```

## See also

- [METHODOLOGY.md](./METHODOLOGY.md) — deep technical walkthrough of the data
  sources, the computation engine, the context renderer, the report pipeline
  phases, the anchor check, the hallucination guard, the model tier table, and
  the Q&A analyst.
