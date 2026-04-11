# 260411-hxm — Reference: current codebase facts (pre-verified)

This file holds facts about the current codebase that I (the user-facing
orchestrator) have already confirmed by reading the source. The rewrite
must not contradict any of these. The rewrite must not copy content
forward from the existing README.md or METHODOLOGY.md — both are stale
and contain claims that no longer match the code.

## Stale claims in the existing docs (do NOT carry forward)

- "Simple pipeline" / `report.py` — file no longer exists.
- `--pipeline` CLI flag — does not exist; there is only one pipeline.
- "Four-phase pipeline" — there is one multi-specialist pipeline with
  phases 1 / 1.5 / 1.75 / 2 / 2.5.
- "Social hook" output / "Fantasy insights" output /
  "3 Axios-style bullets" — none of these exist in the current CLI.
- "12-section context" — `to_prompt()` now renders up to 15 sections.
- "4 anchor warning categories" — there are 5 (UNDERWEIGHTED is new).
- "9 scout signals" — there are 10.
- "pitcher-ask defaults to openai" — it defaults to **gemini**.

## Entry points (pyproject.toml `[project.scripts]`)

- `pitcher-narratives` → `src/pitcher_narratives/cli.py:main`
- `pitcher-scout` → `src/pitcher_narratives/scout_cli.py:main`
- `pitcher-ask` → `src/pitcher_narratives/ask_cli.py:main`

## Package layout (`src/pitcher_narratives/`)

| File | Lines | Role |
|------|-------|------|
| `__init__.py` | 1 | Package marker |
| `analyst.py` | 723 | Q&A tool-calling agent (pitcher-ask) |
| `anchor.py` | 117 | Anchor check prompt + AnchorResult/AnchorWarning models |
| `ask_cli.py` | 181 | pitcher-ask entry point |
| `cli.py` | 222 | pitcher-narratives entry point |
| `config.py` | 129 | PROVIDERS, model settings factory, thinking caps |
| `context.py` | 681 | PitcherContext model + `to_prompt()` renderer |
| `curator.py` | 115 | LLM-powered scout curation (`--curate`) |
| `data.py` | 456 | Statcast + Pitching+ CSV loading pipeline |
| `engine.py` | 3184 | Computation engine (all metrics, deltas, flags) |
| `pipeline.py` | 1607 | Multi-specialist pipeline (the only pipeline) |
| `resolver.py` | 385 | Fuzzy pitcher name resolution for pitcher-ask |
| `scout_cli.py` | 136 | pitcher-scout entry point |
| `scout.py` | 496 | Appearance interest scoring (no LLM) |
| `signals.py` | 110 | KeySignals model + signal extractor prompt |

There is **no `report.py`** — do not reference it.

## `pitcher-narratives` CLI (`cli.py`)

Args:

| Flag | Type | Default | Notes |
|------|------|---------|-------|
| `-p`, `--pitcher` | int | required | MLB pitcher ID |
| `-w`, `--window` | int | 30 | Lookback in days |
| `-v`, `--verbose` | flag | off | Logs name, game dates, counts on stderr |
| `--print-prompts` | flag | off | Prints the rendered pipeline prompts and exits (no LLM call) |
| `--provider` | enum | `openai` | `openai` \| `claude` \| `gemini` |
| `--thinking` | enum | `medium` | `minimal` \| `low` \| `medium` \| `high` \| `xhigh` |

Stdout output, printed in this exact order:

1. `# Scouting Report` — the writer's capsule streams live from
   `generate_pipeline_streaming`.
2. `# Executive Summary` — bullets from the summary agent, or
   `_Summary unavailable — no bullets produced._` if empty.
3. `# Stuff Analysis` — `pipe_result.specialists.stuff`.
4. `# Data Audit` — list of `audit_flags` (category, specialist, claim,
   data_shows), or `Clean — no issues found.`
5. `# Anchor Check` — one of:
   - `Passed on first draft.`
   - `Revised N time(s) — passed.`
   - `Revised N time(s) — remaining issues:` followed by
     `**[CATEGORY]** description` for each surviving warning.
6. `# Hallucination Check` — emitted only when the guard finds unknown
   metrics or traditional outcome stats.

Also writes `data-{pitcher}-{provider}.md` via
`write_pipeline_data_file` with the rendered specialist and writer
prompts. `--print-prompts` prints that file to stderr and exits.

No "Social Hook" section. No "Fantasy Insights" section.

## `pitcher-scout` CLI (`scout_cli.py`)

Args:

| Flag | Default | Notes |
|------|---------|-------|
| `-w`, `--window` | 1 | Days to scan (1 = most recent game date) |
| `-n`, `--top` | 20 | Number of results to display |
| `--min-pitches` | 20 | Minimum pitches for an appearance to be scored |
| `--min-score` | 0.0 | Minimum interest score to display |
| `-v`, `--verbose` | off | Show per-signal detail under each row |
| `--curate` | off | Send top results to an LLM for editorial selection |
| `--provider` | `openai` | `openai` \| `claude` \| `gemini` |

`--curate` checks for the provider's API key before calling
`curate_appearances` from `curator.py`.

## `pitcher-ask` CLI (`ask_cli.py`)

Args:

| Flag | Default | Notes |
|------|---------|-------|
| positional `question` | — | Natural-language question |
| `-w`, `--window` | 30 | Lookback days |
| `--provider` | **`gemini`** | `openai` \| `claude` \| `gemini` |
| `--thinking` | `medium` | Same five levels |

Flow:
1. Parse question → `resolver.extract_pitcher_from_question` for fuzzy
   name resolution (exits with error if no match / ambiguous).
2. `data.load_pitcher_data` → `context.assemble_pitcher_context`.
3. Write `data-{pitcher}-{provider}-ask.md` (ANALYST_INSTRUCTIONS +
   question + tool descriptions).
4. `analyst.ask_question_streaming` streams the answer.

Output is just the streamed answer — no Executive Summary / Data Audit /
Stuff Analysis / Anchor Check sections. The narrative CLI owns those.

## Pipeline (`pipeline.py`)

**Phase 1 — specialists (parallel).** `run_specialists` gathers five
agents concurrently. Each specialist receives a bespoke input built by
its `_build_*_input` helper, with every metric pre-annotated with a
delta from league average and an explicit `NORMAL`/`OUTLIER` z-score
tag (`engine.outlier_tag`).

| Specialist | Tier | temp | `max_tokens` | Prompt constant |
|------------|------|------|--------------|-----------------|
| `stuff` | Pro | 0.3 | LARGE (4096) | `_STUFF_SPECIALIST_PROMPT` |
| `location` | Mini | 0.3 | LARGE (4096) | `_LOCATION_SPECIALIST_PROMPT` |
| `runvalue` | Mini | 0.3 | LARGE (4096) | `_RUNVALUE_SPECIALIST_PROMPT` |
| `trends` | Mini | 0.3 | MEDIUM (2048) | `_TREND_SPECIALIST_PROMPT` |
| `game_shape` | Mini | 0.3 | MEDIUM (2048) | `_GAME_SHAPE_SPECIALIST_PROMPT` |

**Phase 1.5 — audit + revise.** `audit_and_revise_specialists` runs
the auditor (Mini tier, temp 0.1, `retries=5`, SMALL token budget)
against each specialist's output in parallel. Flagged specialists are
re-run with their original input plus the audit corrections. The
writer never sees flawed prose. `AuditFlag` / `AuditResult` live in
`pipeline.py`.

**Phase 1.75 — signal extractor.** The `signal_extractor` agent (Mini
tier, SMALL budget, `retries=3`) reads the clean specialist outputs and
returns a `KeySignals` object from `signals.py`:

- Primary (required, non-empty): `top_improvement`, `top_concern`
- Secondary (optional, may be null): `development_pitch`,
  `specialist_tension`, `arsenal_dependency`, `connected_changes`,
  `platoon_vulnerability`, `sample_size_caution`

This phase is non-critical: on any exception the pipeline continues
with `key_signals=None` and the anchor check degrades gracefully.

**Phase 2 — writer + summary (parallel).** The writer (Pro tier, temp
0.7, LARGE budget) runs with `build_writer_input(ctx, specialists,
key_signals)` and streams to stdout. The executive summary agent (Mini
tier, temp 0.3, SMALL budget) runs concurrently from the same input.
Summary failures are non-fatal (empty list).

**Phase 2.5 — anchor check + revision loop.**
`_run_anchor_revision_loop` drives the anchor agent (Mini tier, temp
0.1, SMALL budget) via `anchor.ANCHOR_PROMPT`. The synthesis passed in
is `render_key_signals(key_signals) + specialist outputs`. When the
anchor is not clean, the writer is asked to revise via
`anchor.build_revision_message` — a fresh prompt with no history, a
cache breakpoint after the synthesis, and a targeted instruction that
says "fix only the listed warnings." Up to `MAX_REVISIONS` (3) passes,
then one final anchor check captures surviving warnings.

**Anchor warning categories** (`anchor.WarningCategory`, five total):

| Category | Meaning |
|----------|---------|
| `MISSED_SIGNAL` | Capsule ignores a required primary key signal |
| `UNDERWEIGHTED` | Capsule ignores a populated secondary key signal |
| `UNSUPPORTED` | Capsule states a metric/trend absent from the synthesis |
| `DIRECTION_ERROR` | Capsule flips a direction (up vs down) from the synthesis |
| `OVERSTATED` | Capsule presents a small-sample finding as definitive |

**Post-pipeline hallucination guard.** `check_hallucinated_metrics`
regex-scans the final narrative and returns `HallucinationReport` with:

- `unknown_metrics` — metric-like patterns (xMetric, Acronym%, P+/S+/L+
  family) that are not in a known-safe set.
- `outcome_stat_warnings` — traditional stats the prompt warns against
  (ERA, WHIP, W-L, etc.).

## Config (`config.py`)

```python
PROVIDERS = {
    "openai": "openai:gpt-5.4",
    "claude": "anthropic:claude-sonnet-4-6",
    "gemini": "google-gla:gemini-3.1-pro-preview",
}

MINI_PROVIDERS = {
    "openai": "openai:gpt-5.4-mini",
    "claude": "anthropic:claude-haiku-4-5",
    "gemini": "google-gla:gemini-flash-latest",
}

TOKEN_BUDGET_SMALL = 1024   # anchor / auditor / summary
TOKEN_BUDGET_MEDIUM = 2048  # compact specialists (trends, game_shape)
TOKEN_BUDGET_LARGE = 4096   # writer + stuff/location/runvalue specialists
MAX_REVISIONS = 3

API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
```

Provider-specific quirks in `make_model_settings`:

- **Gemini** always uses `GoogleModelSettings` with
  `google_thinking_config={"thinking_level": "high" | "low"}`. CLI
  levels `high`/`xhigh` map to `"high"`, everything else maps to
  `"low"`. Temperature and `max_tokens` pass through.
- **Claude** disables thinking entirely when `mini=True` or when
  `max_tokens <= TOKEN_BUDGET_MEDIUM` (otherwise the thinking budget
  would exceed the output budget). Temperature is forced to `1` when
  thinking is on.
- **OpenAI** disables `reasoning_effort` for mini-tier models
  (`gpt-5.4-mini` doesn't support it via chat completions) and omits
  `max_tokens` when the budget is `<= TOKEN_BUDGET_MEDIUM` (reasoning
  tokens count against the cap and small budgets choke the model).

`cap_thinking(user_level, ceiling)` clamps the user's CLI selection to
a per-role ceiling. Role ceilings used by `make_pipeline_agents`:

| Role | Thinking cap | Tier | temp | max_tokens |
|------|--------------|------|------|------------|
| Stuff specialist | `medium` | Pro | 0.3 | LARGE |
| Location / RunValue | `medium` | Mini | 0.3 | LARGE |
| Trends / Game Shape | `medium` | Mini | 0.3 | MEDIUM |
| Writer | (user level, uncapped) | Pro | 0.7 | LARGE |
| Auditor | `low` | Mini | 0.1 | SMALL |
| Anchor | `low` | Mini | 0.1 | SMALL |
| Executive Summary | `medium` | Mini | 0.3 | SMALL |
| Signal Extractor | `medium` | Mini | 0.3 | SMALL |

## Context assembly (`context.py`)

`PitcherContext` is a Pydantic model. `to_prompt()` appends sections in
this order, skipping any that render empty:

1. Title: `# {pitcher_name} ({L/R}HP) -- Scouting Context`
2. `## Temporal Context` — analysis date, season phase (early / mid /
   full), prior-year workload relevance line.
3. `## Executive Summary` — last outing; fastball velo delta; fastball
   P+/S+/L+ triad deltas; biggest arsenal usage shift; TTO summary;
   hard-hit delta; workload flag.
4. `## Role` — most recent role (SP/RP), appearance count,
   consecutive days pitched, workload concern flag.
5. `## Primary Fastball: {pitch_name} ({type})` — velocity, P+/S+/L+
   triad + deltas, movement deltas, within-game velocity arc from the
   last outing. Falls back to `## Primary Fastball\n- No standard
   fastball identified` when none is found.
6. `## Times Through Order` — fastball vs secondary P+ split per pass;
   per-pitch-type usage + P+ across passes with mix-shift flags;
   platoon-within-TTO breakdowns. Skipped when no TTO data.
7. `## Arsenal` — top pitch types by usage with usage delta and
   P+/S+/L+ columns vs season baseline.
8. `## Execution` — CSW%, Zone%, Chase%, xWhiff, xSwing, and xRV100
   percentile per pitch type.
9. `## Model Internals: Location Impact` — S-variant (stuff-only)
   probabilities and P-vs-S deltas per pitch type.
10. `## Release Point` — per-pitch-type release x/z/extension vs the
    pitcher's own season baseline.
11. `## Contact Quality` — hard-hit rate, window vs season, with delta.
12. `## Platoon Shifts` — per-pitch-type usage and P+ by batter hand.
13. `## First-Pitch Tendencies` — top first-pitch types, recent vs
    season share.
14. `## Recent Appearances` — date, IP, pitch count, rest days.
15. `## Year-over-Year` — cross-season pitcher-level deltas +
    added/dropped pitches. Skipped for single-season pitchers.

`PitcherContext.attributions` (13-outcome xRV100 decomposition per
pitch type) is **not** rendered by `to_prompt()`. It is consumed
directly by `_build_runvalue_input` for the run-value specialist.

## Scout signals (`scout.py`, `_WEIGHTS`)

Ten signals. Each `Signal` carries `name`, `weight`, `detail`.

| Signal | Weight | Threshold | Intent |
|--------|--------|-----------|--------|
| `new_pitch` | 4.0 | `< 1%` season usage, `> 5%` in game | New pitch type |
| `development_opportunity` | 3.5 | `S+ > 110` and `L+ < 80` | Stuff without feel |
| `velo_delta` | 3.0 | `>= 1.5 mph` from season fastball avg | Velocity swing |
| `splus_lplus_divergence` | 3.0 | Each `>= 10 pts`, opposite directions | Stuff vs command split |
| `dropped_pitch` | 3.0 | `>= 10%` season usage, `0%` in game | Established pitch shelved |
| `pplus_swing` | 2.5 | `>= 15 pts` from season P+ | Overall P+ spike/collapse |
| `walk_rate_pplus_contradiction` | 2.5 | `P+ >= 105` and `L+ < 85` | Good stuff without command |
| `usage_shift` | 2.0 | `>= 8pp` usage change from season | Mix shift |
| `hard_hit_spike` | 1.5 | — | **Verify status in scout.py when rewriting** |
| `workload_flag` | 1.0 | `3+` consecutive calendar days | Reliever workload concern |

NOTE for rewriter: `hard_hit_spike` may still be a no-op stub. Read
`scout.py` before documenting it — if no code path creates a signal
with that name, say so plainly (e.g. "defined in the weights table but
not yet wired into the scanner").

## Q&A analyst (`analyst.py`)

Tool-calling pydantic-ai agent, Pro tier, temp 0.3. System prompt is
`ANALYST_INSTRUCTIONS`. Entry point is `ask_question_streaming`.
Resolver (`resolver.py`) handles fuzzy pitcher name lookup via
`extract_pitcher_from_question` (uses rapidfuzz).

**Rewriter must read `analyst.py` to enumerate the actual tools.** I
confirmed the shape (tool-calling with `RunContext[QADeps]`) and that
`get_pitcher_summary` + `get_pitch_detail` are at least two of the
tools, but the current full tool list must be taken from the source,
not from this reference.

## Data pipeline (`data.py`)

- Loads the Statcast parquet at the project root (filename inferred
  from the loader — read `data.py` to confirm the current path).
- Loads eight Pitching+ CSVs from `aggs/`:
  - `2026-pitcher.csv` — season per pitcher
  - `2026-pitcher_type.csv` — season per pitcher per pitch type
  - `2026-pitcher_appearance.csv` — per game per pitcher
  - `2026-pitcher_type_appearance.csv` — per game per pitcher per type
  - `2026-pitcher_type_platoon.csv` — season per pitcher per type per platoon
  - `2026-pitcher_type_platoon_appearance.csv` — per game platoon
  - `2026-all_pitches.csv` — individual pitches with P+/S+/L+
  - `2026-team.csv` — team season
- 2025 analogues live alongside for year-over-year comparisons.
- Window is computed relative to the **most recent date in the
  dataset**, not the wall clock — this keeps behavior stable against
  static files.
- Starter vs reliever is classified **per appearance** (first inning =
  1 → SP, otherwise RP). Openers end up labeled SP.
- Season baselines across game types are computed as `n_pitches`-weighted
  averages, not simple means — this prevents a five-pitch regular-season
  row from outweighing a 200-pitch spring training row.

## Delta vocabulary (from `engine.py`)

| Metric family | "Steady" cutoff | "Up/Down" band | "Sharply" |
|---------------|-----------------|----------------|-----------|
| Velocity (mph) | < 0.5 | 0.5 – 2.0 | > 2.0 |
| P+ / S+ / L+ (points) | < 5 | 5 – 10 | > 10 |
| Usage rate (pp) | < 5 | 5 – 10 | > 10 |
| Movement (inches) | < 0.5 | >= 0.5 | — |

When the lookback window covers the full season there is no baseline
to compare against, and the delta string is replaced with
`"Full season in window — no trend comparison."`

Per-pitch-type analyses flag `small_sample: true` below 10 pitches in
the window.

## `pyproject.toml`

- `requires-python = ">=3.14"`
- Runtime deps: `logfire`, `nameparser`, `polars>=1.39.3`,
  `pydantic-ai>=1.72.0`, `pydantic-ai-slim[google]`, `python-dotenv`,
  `rapidfuzz`.
- Dev deps: `pre-commit`, `pytest`, `ruff`, `ty`.
- Ruff: `line-length = 110`, `target-version = "py313"`,
  `select = ["E","F","W","I","UP","B","SIM","RUF"]`.
- `pytest.ini_options.testpaths = ["tests"]`.

## Tests (`tests/`)

`test_analyst.py`, `test_anchor.py`, `test_ask_cli.py`, `test_cli.py`,
`test_context.py`, `test_data.py`, `test_engine.py`,
`test_hallucination_guard.py`, `test_pipeline.py`, `test_resolver.py`,
`test_role_guidance.py`, `test_signals.py`.

## Makefile targets (verify)

The old README referenced `make scout` and `make curate`. Check the
Makefile during the rewrite — keep any target that still exists, drop
any that don't.
