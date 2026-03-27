# Pitcher Narratives

LLM-powered scouting reports for MLB pitchers. Given a pitcher ID, assembles pitch-level Statcast data and pre-computed Pitching+ aggregations into a structured context document, then sends it through a four-phase LLM pipeline to produce an analytical narrative, a social media hook, and fantasy baseball insights.

Reports read like a scout wrote them — surfacing changes, adaptations, and execution trends rather than reciting numbers.

## Quick Start

```bash
# Install
uv sync

# Set your API key
export OPENAI_API_KEY=sk-...      # for OpenAI (default)
export ANTHROPIC_API_KEY=sk-...   # for Claude
export GEMINI_API_KEY=...         # for Gemini

# Generate a report
pitcher-narratives -p 592155

# With options
pitcher-narratives -p 592155 -w 14 --provider claude --thinking high -v
```

## CLI Reference

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

## Output

Each run produces:

1. **Narrative** (streamed to stdout) — 2-3 paragraph scouting capsule in an elite sabermetric analyst voice
2. **Social hook** — one headline-length sentence for X/Bluesky, under 280 characters
3. **Fantasy insights** — 3 Axios-style bullet points with fantasy-relevant analysis
4. **Data file** — `data-{pitcherid}-{provider}.md` with all prompts sent to the LLM

A post-generation hallucination guard scans the narrative for unknown or traditional metrics and warns on stderr.

## Architecture

```
CLI Input (pitcher ID, window days, provider)
    |
    v
Data Loading (Statcast parquet + 8 Pitching+ CSVs)
    |
    v
Computation Engine (all arithmetic in Python, never LLM)
    |  Fastball quality, arsenal, platoon mix, first-pitch weaponry,
    |  execution metrics, workload context, TTO analysis,
    |  release point mechanics, hard-hit rate, contact quality
    |
    v
Context Assembly (PitcherContext -> to_prompt() markdown, ~1000 tokens)
    |
    v
Four-Phase LLM Pipeline (with CachePoint markers for prompt caching)
    |  Phase 1: Synthesizer — extracts structured bullet findings
    |  Phase 2: Editor — writes the scouting capsule (streamed)
    |  Phase 3: Hook Writer — one social media headline
    |  Phase 4: Fantasy Analyst — 3 Axios-style bullets
    |
    v
Output (narrative + hook + fantasy bullets + hallucination guard)
```

Every number in the final report traces back through the Python pipeline to a specific Statcast column or Pitching+ aggregation. The LLM interprets — it does not compute.

## Providers

| Provider | Model | Thinking | Notes |
|----------|-------|----------|-------|
| `openai` | gpt-5.4-mini | Standard `ThinkingEffort` levels | Default provider |
| `claude` | claude-sonnet-4-6 | Standard `ThinkingEffort` levels | 16384 max_tokens for thinking budget |
| `gemini` | gemini-3.1-pro-preview | `low`/`high` (mapped from CLI levels) | `GoogleModelSettings`, temperature=1.0 |

Prompt caching is supported across all providers. CachePoint markers are placed after role guidance (Phase 1) and after synthesis output (Phases 2-4) to avoid re-processing shared content across phases and across pitchers in batch runs.

## Project Structure

```
src/pitcher_narratives/
    __init__.py
    cli.py          # CLI entry point
    data.py         # Statcast + Pitching+ loading pipeline
    engine.py       # Computation engine (all metrics, deltas, flags)
    context.py      # PitcherContext assembly and to_prompt() rendering
    report.py       # Four-phase LLM pipeline + hallucination guard
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
uv run pytest                    # Run tests (174 tests)
uv run ruff check src/ tests/    # Lint
uv run ty check                  # Type check
uv run pre-commit run --all-files  # All hooks
```

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for detailed documentation of data sources, computation pipeline, delta vocabulary, and the LLM prompt architecture.
