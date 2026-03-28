# Pitcher Narratives

LLM-powered scouting reports for MLB pitchers. Given a pitcher ID, assembles pitch-level Statcast data and pre-computed Pitching+ aggregations into a structured context document, then sends it through a five-phase LLM pipeline with a self-correcting reflection loop to produce an analytical narrative, a social media hook, and fantasy baseball insights.

Reports read like a scout wrote them — surfacing changes, adaptations, and execution trends rather than reciting numbers.

## Quick Start

```bash
# Install
uv sync

# Set your API key
export OPENAI_API_KEY=sk-...      # for OpenAI (default)
export ANTHROPIC_API_KEY=sk-...   # for Claude
export GEMINI_API_KEY=...         # for Gemini

# Scout: find interesting appearances from today's games
pitcher-scout -v

# Curate: let the LLM pick the top stories
pitcher-scout --curate

# Generate a full report for a specific pitcher
pitcher-narratives -p 669432 -w 5 -v
```

## Scout: Finding Interesting Appearances

The scout scans all pitcher appearances in a date window and scores each one for "interestingness" — no LLM calls, just heuristic signal detection against season baselines.

```
pitcher-scout [-w DAYS] [-n TOP] [-v] [--min-score N]
              [--curate] [--provider {openai,claude,gemini}]
```

| Flag | Description |
|------|-------------|
| `-w, --window` | Days to scan (default: 1 = most recent game date) |
| `-n, --top` | Number of results (default: 20) |
| `-v, --verbose` | Show signal details for each appearance |
| `--min-score` | Minimum interest score to display |
| `--curate` | Send results to an LLM to select the 3-5 best stories |
| `--provider` | LLM provider for curation (default: `openai`) |

### Signals Scored

| Signal | Weight | What it catches |
|--------|--------|-----------------|
| `new_pitch` | 4.0 | Pitch type appearing that wasn't in the season repertoire |
| `development_opportunity` | 3.5 | High S+ (>110) with low L+ (<80) — stuff without feel |
| `velo_delta` | 3.0 | Fastball velo >= 1.5 mph from season average |
| `splus_lplus_divergence` | 3.0 | S+ and L+ moving opposite directions (>= 10 pts each) |
| `dropped_pitch` | 3.0 | Season pitch (>= 10% usage) not thrown at all |
| `pplus_swing` | 2.5 | Overall P+ >= 15 pts from season average |
| `walk_rate_pplus_contradiction` | 2.5 | Good P+ (>= 105) with poor L+ (< 85) |
| `usage_shift` | 2.0 | Any pitch >= 8pp usage change from season |
| `workload_flag` | 1.0 | 3+ consecutive days pitched |

### Example: Scout Output

```
$ pitcher-scout -n 5 -v

Score  Pitcher                   T  Date         #P  Signals
─────  ───────────────────────── ─  ──────────  ───  ────────────────────────────────────────
 18.0  Rogers, Trevor            L  2026-03-26   88  splus_lplus_divergence, usage_shift, ...
       └─ splus_lplus_divergence (3.0): SI: S+ +25, L+ -93 (stuff/command split)
       └─ usage_shift (2.0): CH usage up 14.4pp (29.5% vs 15.2% season)
       └─ dropped_pitch (3.0): ST dropped (was 14.8% of season mix)
       └─ dropped_pitch (3.0): SL dropped (was 10.4% of season mix)
       └─ development_opportunity (3.5): CU: S+ 128 / L+ 70 (stuff without feel)
       └─ development_opportunity (3.5): SI: S+ 128 / L+ 12 (stuff without feel)
 16.5  Legumina, Casey           R  2026-03-26   29  pplus_swing, splus_lplus_divergence, ...
 16.5  Gómez, Yoendrys           R  2026-03-26   28  pplus_swing, splus_lplus_divergence, ...
 16.0  Seymour, Ian              L  2026-03-26   21  splus_lplus_divergence, usage_shift, ...
 16.0  Backhus, Kyle             L  2026-03-26   20  pplus_swing, splus_lplus_divergence, ...
```

### Example: LLM Curation

With `--curate`, the LLM selects the most compelling stories from the scored list using a signal hierarchy (Clean Breakout > Lab Project > Identity Crisis > Red Flag), explains each pick, and accounts for every pitcher it didn't select.

## Narrative Builder: Full Scouting Reports

Once you've identified an interesting appearance, generate a full report:

```
pitcher-narratives -p PITCHER [-w WINDOW] [-v] [--print-prompts]
                   [--provider {openai,claude,gemini}]
                   [--thinking {minimal,low,medium,high,xhigh}]
```

| Flag | Description |
|------|-------------|
| `-p, --pitcher` | MLB pitcher ID (required) |
| `-w, --window` | Lookback window in days (default: 30) |
| `-v, --verbose` | Show pitcher name, game dates, and pitch counts on stderr |
| `--print-prompts` | Print all system/user prompts to stderr and exit |
| `--provider` | LLM provider: `openai` (default), `claude`, `gemini` |
| `--thinking` | Reasoning effort level (default: `medium`) |

### Example: Narrative Output

```
$ pitcher-narratives -p 808967 --provider claude

Yamamoto's cutter is the most interesting pitch in this arsenal right now,
and it's functioning almost entirely on placement. The pitch posts P+ 144
with an xRV100 at the 94th percentile — by some distance the highest marks
in this four-start dataset — while carrying S+ 98, which is below the MLB
average of 100. L+ 139 is what's generating the results: a 41-point gap
between pitch-level location quality and shape quality...

The broader context matters here. No pitch in this arsenal exceeds S+ 106.
This is a system-wide characteristic, not a quirk of one pitch, which means
precision delivery is the load-bearing structure of the entire profile...

---
Yamamoto's cutter is carrying his entire arsenal on placement alone,
posting a 41-point gap between location quality and shape quality that
explains every elite result from a pitch without elite movement.

---
- Yamamoto's cutter is carrying his fantasy value through four starts,
  posting P+ 144 with a 40.0% CSW%...
- A cutter P+ drop from 108 in pass 1 to 93 in pass 3 flags a potential
  late-outing location issue...
- No pitch in this arsenal exceeds S+ 106, meaning the entire profile runs
  on precision delivery rather than elite shape...
```

The reflection loop runs automatically. When the anchor check finds issues, the editor silently revises and the anchor re-checks (up to 2 passes). Stderr reports the outcome:

```
Passed anchor check                              # clean on first try
Revised 1 time(s) -- anchor check passed         # revised and converged
Revised 2 time(s) -- anchor check found issues:  # exhausted with warnings
  [MISSED_SIGNAL] Key velocity drop not addressed
```

## Output

Each report produces:

1. **Narrative** (streamed to stdout) — 2-3 paragraph scouting capsule
2. **Social hook** — one headline-length sentence, under 280 characters
3. **Fantasy insights** — 3 Axios-style bullet points
4. **Revision status** — stderr reports anchor check outcome and any surviving warnings
5. **Data file** — `data-{pitcherid}-{provider}.md` with all prompts sent to the LLM

Post-generation guards run automatically: the **editor-anchor reflection loop** verifies the narrative is faithful to the synthesis — flagging missed key signals, unsupported claims, directional errors, and overstated confidence. If issues are found, the editor silently revises and the anchor re-checks, up to 2 passes. A **metric hallucination guard** then scans for unknown or traditional metrics.

## Architecture

```
pitcher-scout (triage)                   pitcher-narratives (full report)
─────────────────────                    ────────────────────────────────
Appearance-level CSVs + Statcast         Statcast parquet + 8 Pitching+ CSVs
    │                                        │
    ▼                                        ▼
9 signal checkers (pure Python)          Computation Engine (9 analysis modules)
    │                                        │
    ▼                                        ▼
Scored + ranked appearances              Context Assembly (~1000 tokens markdown)
    │                                        │
    ▼ (--curate only)                        ▼
LLM Curator (select 3-5 stories)        Five-Phase LLM Pipeline
                                             Phase 1: Synthesizer → structured findings
                                             Phase 2: Editor → scouting capsule (streamed)
                                             Phase 2.5: Anchor Check + Reflection Loop
                                               ┌─ anchor returns CLEAN → proceed
                                               └─ warnings found → editor revises silently
                                                  → anchor re-checks (up to 2 passes)
                                             Phase 3: Hook Writer → social headline
                                             Phase 4: Fantasy Analyst → 3 bullet points
                                             │
                                             ▼
                                         Hallucination Guard + Output
```

The pipeline is split by design: the scout runs without LLM calls (cheap, fast, scannable), and the narrative builder runs the full five-phase pipeline for the pitchers worth writing about. The anchor check (Phase 2.5) verifies the editor's capsule is faithful to the synthesis. If warnings are found, the editor revises using a fresh targeted prompt and the anchor re-checks — up to 2 revision passes. Only the final capsule flows to Phases 3 and 4, which derive from it and inherit the editor's plausibility filters and metric curation.

## Providers

| Provider | Model | Thinking | Notes |
|----------|-------|----------|-------|
| `openai` | gpt-5.4-mini | Standard `ThinkingEffort` levels | Default provider |
| `claude` | claude-sonnet-4-6 | Standard `ThinkingEffort` levels | 16384 max_tokens for thinking budget |
| `gemini` | gemini-3.1-pro-preview | `low`/`high` (mapped from CLI levels) | `GoogleModelSettings`, temperature=1.0 |

## Project Structure

```
src/pitcher_narratives/
    __init__.py
    cli.py          # Narrative builder CLI entry point
    scout_cli.py    # Scout CLI entry point
    data.py         # Statcast + Pitching+ loading pipeline
    engine.py       # Computation engine (all metrics, deltas, flags)
    context.py      # PitcherContext assembly and to_prompt() rendering
    report.py       # Five-phase LLM pipeline + reflection loop + hallucination guard
    scout.py        # Appearance interest scoring (no LLM)
    curator.py      # LLM-powered curation of scouted appearances
tests/
    test_data.py
    test_engine.py
    test_context.py
    test_report.py
    test_cli.py
```

## Development

```bash
uv sync                          # Install deps
uv run pytest                    # Run tests
uv run ruff check src/ tests/    # Lint
uv run ty check                  # Type check
make scout                       # Scout: top 25, score >= 5.0, verbose
make curate                      # Scout + LLM curation
```

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for detailed documentation of data sources, computation pipeline, delta vocabulary, and the LLM prompt architecture.
