# Pitcher Narratives

Pitcher Narratives is a CLI that turns Statcast and Pitching+ data into
LLM-written scouting reports for MLB pitchers. The report is grounded in
pre-computed deltas and baselines so the model can focus on insight, not
arithmetic — every metric arrives at the LLM pre-tagged with window-vs-season
direction, z-score outlier flags, and small-sample caveats.

The narrative that comes out of the pipeline reads like a scout wrote it:
surfacing *changes, adaptations, and execution trends* for a single pitcher's
most recent appearance relative to their recent window and season baseline.

## Requirements

- Python 3.14+ (pinned in `.python-version` and enforced by
  `requires-python = ">=3.14"` in `pyproject.toml`)
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- An API key for at least one supported provider, exported or placed in
  a `.env` file at the project root (loaded automatically via
  `python-dotenv`):
  - `OPENAI_API_KEY` for `--provider openai`
  - `ANTHROPIC_API_KEY` for `--provider claude`
  - `GEMINI_API_KEY` for `--provider gemini`
- Static data files at the project root:
  - `statcast_2025.parquet`, `statcast_2026.parquet` — pitch-level
    Statcast data
  - `aggs/` — pre-computed Pitching+ CSVs for the 2025 and 2026 seasons
    (per pitcher, per pitch type, per appearance, platoon splits, etc.)
  - See `METHODOLOGY.md` for the full data-source breakdown.

No network calls to Baseball Savant happen at runtime. Everything is
served from these local files.

## Install / quick start

```bash
uv sync
uv run pitcher-narratives -p 657277 -w 5
```

Or use the Makefile shortcut, which wraps the same command:

```bash
make run   # runs: uv run pitcher-narratives -p 657277 -w 5
```

A successful run streams the scouting capsule to stdout and writes a
side-effect file `data-{pitcher}-{provider}.md` containing the rendered
pipeline prompts (useful for debugging or prompt inspection).

## The three CLIs

The package installs three entry points via `[project.scripts]` in
`pyproject.toml`:

| Script | Source | Purpose |
|---|---|---|
| `pitcher-narratives` | `pitcher_narratives.cli:main` | Full scouting report |
| `pitcher-scout` | `pitcher_narratives.scout_cli:main` | Appearance triage + scoring |
| `pitcher-ask` | `pitcher_narratives.ask_cli:main` | Natural-language Q&A |

### `pitcher-narratives`

Runs the multi-agent specialist pipeline end-to-end for a single pitcher
over a lookback window.

| Flag | Type | Default | Notes |
|---|---|---|---|
| `-p`, `--pitcher` | int | *required* | MLB pitcher ID |
| `-w`, `--window` | int | `30` | Lookback in days |
| `-v`, `--verbose` | flag | off | Prints pitcher name, game dates, pitch counts to stderr before running |
| `--print-prompts` | flag | off | Renders the pipeline prompts to stderr and exits without calling the LLM |
| `--provider` | enum | `openai` | `openai` \| `claude` \| `gemini` |
| `--thinking` | enum | `medium` | `minimal` \| `low` \| `medium` \| `high` \| `xhigh` |

Example:

```bash
uv run pitcher-narratives -p 657277 -w 30 --provider openai --thinking high
```

Stdout is printed in exactly this order:

1. `# Scouting Report` — the writer's capsule, streamed live.
2. `# Executive Summary` — bullets from the summary agent (falls back
   to `_Summary unavailable — no bullets produced._` if empty).
3. `# Stuff Analysis` — the stuff specialist's clean output.
4. `# Data Audit` — list of unresolved audit flags, or `Clean — no
   issues found.`
5. `# Anchor Check` — one of `Passed on first draft.`, `Revised N
   time(s) — passed.`, or `Revised N time(s) — remaining issues:`
   followed by the surviving warnings.
6. `# Hallucination Check` — emitted only when the post-pipeline guard
   finds unknown metrics or traditional outcome stats.

Every run also writes `data-{pitcher}-{provider}.md` to the working
directory with the rendered specialist and writer prompts.
`--print-prompts` dumps that same content to stderr and exits without
calling the model — useful when iterating on prompt wording.

### `pitcher-scout`

Cheap pre-filter that scans recent appearances, scores each one on a
ten-signal heuristic (no LLM), and prints a ranked table. Optionally
pipes the top results to a curator LLM.

| Flag | Default | Notes |
|---|---|---|
| `-w`, `--window` | `1` | Days to scan (`1` = most recent game date only) |
| `-n`, `--top` | `20` | Max results to display |
| `--min-pitches` | `20` | Minimum pitches for an appearance to be scored |
| `--min-score` | `0.0` | Minimum interest score to display |
| `-v`, `--verbose` | off | Show per-signal detail under each row |
| `--curate` | off | Send top results to an LLM for editorial selection |
| `--provider` | `openai` | `openai` \| `claude` \| `gemini` (used for `--curate`) |

Example:

```bash
uv run pitcher-scout -w 1 -n 25 --min-score 5.0 -v
```

The heuristic looks for velocity swings, P+/S+/L+ divergences, new or
dropped pitches, usage shifts, development candidates, and reliever
workload flags. See `METHODOLOGY.md` for the full signal table and
weights. `--curate` sends the top results through `curator.py`, which
asks the LLM to pick the 3–5 most compelling stories.

### `pitcher-ask`

Natural-language Q&A grounded in the same `PitcherContext` the narrative
pipeline builds, served by a tool-calling analyst agent. The agent
exposes exactly two tools — `get_pitcher_summary` (returns league
baselines plus the full context render) and `get_pitch_detail` (returns
focused per-pitch-type data).

| Flag | Default | Notes |
|---|---|---|
| positional `question` | — | Natural-language question (quoted) |
| `-w`, `--window` | `30` | Lookback in days |
| `--provider` | **`gemini`** | `openai` \| `claude` \| `gemini` — note: `pitcher-ask` defaults to **gemini**, not openai |
| `--thinking` | `medium` | `minimal` \| `low` \| `medium` \| `high` \| `xhigh` |

Example:

```bash
uv run pitcher-ask "How is Cease's slider playing this month?"
```

The pitcher name is fuzzy-matched out of the question text via
`resolver.py` (uses `rapidfuzz`). Output is just the streamed answer —
no Executive Summary, Data Audit, Stuff Analysis, or Anchor Check
sections. Those belong to the narrative CLI.

## Pipeline at a glance

`pitcher-narratives` runs the sole report-generation pipeline in
`pipeline.py`, organised into five phases:

- **Phase 1** — five specialist agents run in parallel: `stuff`,
  `location`, `runvalue`, `trends`, `game_shape`.
- **Phase 1.5** — per-specialist auditor runs in parallel, and any
  flagged specialists are re-run with the audit corrections. The
  writer never sees flawed prose.
- **Phase 1.75** — a non-critical signal extractor reads the clean
  specialist outputs and produces a `KeySignals` object (primary
  findings + optional secondary findings).
- **Phase 2** — the writer (streamed) and the executive summary agent
  run in parallel from the same clean synthesis.
- **Phase 2.5** — the anchor check validates the capsule against the
  synthesis; unclean drafts are revised up to `MAX_REVISIONS = 3`
  passes before any remaining warnings are reported.

`METHODOLOGY.md` has the deep version: agent tiers, model settings,
prompt structure, cache breakpoints, and the full anchor-check warning
taxonomy.

## Project layout

```
pitcher-narratives/
├── src/pitcher_narratives/
│   ├── __init__.py
│   ├── analyst.py        # Q&A tool-calling agent (pitcher-ask)
│   ├── anchor.py         # Anchor-check prompt + result models
│   ├── ask_cli.py        # pitcher-ask entry point
│   ├── cli.py            # pitcher-narratives entry point
│   ├── config.py         # providers, model settings, thinking caps
│   ├── context.py        # PitcherContext + to_prompt() renderer
│   ├── curator.py        # LLM-powered scout curation (--curate)
│   ├── data.py           # Statcast + Pitching+ loading pipeline
│   ├── engine.py         # Computation engine (metrics, deltas, flags)
│   ├── pipeline.py       # Multi-specialist pipeline (phases 1–2.5)
│   ├── resolver.py       # Fuzzy pitcher name resolution
│   ├── scout.py          # Appearance interest scoring (no LLM)
│   ├── scout_cli.py      # pitcher-scout entry point
│   └── signals.py        # KeySignals model + extractor prompt
├── aggs/                 # Pitching+ CSVs (2025 and 2026)
├── statcast_2025.parquet # Statcast pitch-level data, 2025
├── statcast_2026.parquet # Statcast pitch-level data, 2026
├── tests/                # pytest suite
├── Makefile              # run / scout / curate shortcuts
└── pyproject.toml
```

There is a single pipeline module. No legacy single-agent report path
exists in the current tree.

## Dev commands

```bash
uv sync                  # install / update deps
uv run pytest            # run the test suite
uv run ruff check        # lint
uv run ty check src      # type-check
```

Makefile shortcuts (all three actually exist in the `Makefile`):

```bash
make run      # uv run pitcher-narratives -p 657277 -w 5
make scout    # uv run pitcher-scout -n 25 --min-score 5.0 -v
make curate   # uv run pitcher-scout -n 25 --min-score 5.0 --curate
```

## See also

- [METHODOLOGY.md](./METHODOLOGY.md) — deep technical walkthrough of the
  data sources, the computation engine, the context renderer, the five
  pipeline phases, the anchor check, the hallucination guard, the model
  tier table, and the Q&A analyst.
