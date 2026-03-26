# Stack Research

**Domain:** LLM-powered data analysis and report generation CLI (Python)
**Researched:** 2026-03-26
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.14+ | Runtime | Already constrained by pyproject.toml. Free-threading available but do NOT enable it (see Pitfalls). |
| pydantic-ai | >=1.72.0 | LLM agent framework | Already in deps. Type-safe agent framework with structured output validation, dependency injection, and native Anthropic support. Production-stable. |
| pydantic | >=2.12.5 | Schema definition | Transitive dep via pydantic-ai. Define LLM input/output schemas, data models for pitch context documents, and report structure. v2 required. |
| polars | >=1.39.3 | Data processing | Already in deps. Rust-backed columnar engine handles 145K-row Statcast parquet and multi-grain CSV aggregations with lazy evaluation and predicate pushdown. 5-30x faster than pandas for this workload shape. |
| anthropic | (transitive) | Claude API client | Installed automatically by pydantic-ai[anthropic]. Provides the underlying HTTP client for Claude API calls. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich | >=14.3.3 | Terminal formatting | Render the final scouting report with styled markdown, colored tables, and section headers in the terminal. Also provides Console.export_text() for plain-text file output. |
| python-dotenv | >=1.1.0 | Environment config | Load ANTHROPIC_API_KEY from .env file. Lightweight, no-config. Pydantic-ai's AnthropicModel reads from env automatically, but dotenv ensures .env files work without manual export. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package management | Already managing the project (uv.lock present). Fast resolver, lockfile support, Python version management. |
| ruff | Linting + formatting | Standard Python linter/formatter for 2025-2026. Replaces black + isort + flake8. Add to dev deps. |
| pytest | Testing | Standard test runner. Use with inline fixtures for testing data assembly logic. |

## Key Architecture Decisions

### pydantic-ai: Agent Configuration for Report Generation

Use `anthropic:claude-sonnet-4-6` as the model string. Sonnet 4.6 is the current default-tier model (released Feb 2026) -- it provides near-Opus quality for analytical writing at 5x lower cost than Opus 4.6. Reserve Opus for tasks requiring deeper multi-step reasoning.

**Confidence:** HIGH -- verified via pydantic-ai docs and Anthropic model page.

```python
from pydantic_ai import Agent
from pydantic import BaseModel, Field

class ScoutingReport(BaseModel):
    """Structured output with narrative free-text fields."""
    pitcher_name: str
    role: str = Field(description="'SP' or 'RP'")
    executive_summary: str = Field(description="2-3 sentence scout-style overview")
    fastball_assessment: str = Field(description="Prose paragraph on fastball quality and trends")
    arsenal_analysis: str = Field(description="Prose paragraph on pitch mix and usage shifts")
    execution_metrics: str = Field(description="Prose paragraph on command and results metrics")
    contextual_factors: str = Field(description="Rest, workload, game situation context")
    # Structured data tables embedded alongside prose
    pitch_usage_table: list[dict[str, str]] = Field(description="Pitch type usage with deltas")
    key_metrics_table: list[dict[str, str]] = Field(description="Key performance metrics with trends")

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=ScoutingReport,
    instructions="You are an MLB scouting analyst...",
)
```

**Pattern: Structured output with narrative fields.** Use `output_type` set to a Pydantic model where prose fields are `str` with descriptive `Field(description=...)`. The LLM writes free-form narrative into each field while pydantic-ai validates the structure. This is better than plain `str` output because:
1. Each section is independently addressable for rendering
2. Structured data tables coexist with prose
3. Validation catches malformed responses automatically (pydantic-ai retries on failure)

**Alternative pattern considered:** Plain `output_type=str` with markdown. Rejected because it provides no validation, no retry on malformed output, and makes rendering inflexible.

### pydantic-ai: Instructions and Dependency Injection

Use **static instructions** for the scouting persona and report style guidelines. Use **dynamic instructions via `@agent.instructions`** to inject the pitcher context document at runtime through dependency injection.

```python
from dataclasses import dataclass
from pydantic_ai import RunContext

@dataclass
class PitcherContext:
    """Dependencies injected at runtime."""
    pitcher_name: str
    role: str  # "SP" or "RP"
    context_document: str  # Pre-assembled structured text

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    deps_type=PitcherContext,
    output_type=ScoutingReport,
    instructions=(
        "You are an MLB pitching analyst writing scouting reports. "
        "Emphasize changes and adaptations over raw numbers. "
        "Frame analysis around fastball quality as the foundation."
    ),
)

@agent.instructions
def inject_pitcher_data(ctx: RunContext[PitcherContext]) -> str:
    return ctx.deps.context_document
```

**Confidence:** HIGH -- verified via pydantic-ai agent docs.

### pydantic-ai: Run Pattern for CLI

Use `agent.run_sync()` for simple blocking execution. Use `agent.run_stream_sync()` if streaming output to terminal during generation is desired (better UX for long reports).

```python
# Simple blocking (good for file output)
result = agent.run_sync(
    "Generate a scouting report for this pitcher's most recent appearance.",
    deps=pitcher_context,
)
report: ScoutingReport = result.output

# Streaming (good for terminal display)
with agent.run_stream_sync(
    "Generate a scouting report...",
    deps=pitcher_context,
) as stream:
    for chunk in stream.stream_text():
        console.print(chunk, end="")
```

Note: `run_stream_sync` returns `StreamedRunResultSync` with synchronous iterators -- no async/await needed in CLI context. However, streaming with structured `output_type` is limited (you get partial text, not partial structured objects). For structured output, prefer `run_sync()` and render the complete result.

**Confidence:** HIGH -- verified via pydantic-ai agent and streaming docs.

### pydantic-ai: Model Settings

Configure temperature low for analytical writing. Increase max_tokens for long reports.

```python
from pydantic_ai.settings import ModelSettings

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=ScoutingReport,
    model_settings=ModelSettings(
        temperature=0.3,      # Low for consistent analytical tone
        max_tokens=4096,      # Sufficient for full scouting report
    ),
)
```

**Confidence:** HIGH -- verified via pydantic-ai settings API docs.

### polars: Data Assembly Patterns

Use **lazy evaluation** (`scan_parquet`, `scan_csv`) for all data loading. The Statcast parquet is 145K rows -- lazy mode enables predicate pushdown (filter to single pitcher before loading full dataset) and projection pushdown (only read needed columns).

```python
import polars as pl

# Lazy scan with predicate pushdown -- only reads matching rows from parquet
pitches = (
    pl.scan_parquet("statcast_2026.parquet")
    .filter(pl.col("pitcher") == pitcher_id)
    .select(["pitcher", "game_date", "pitch_type", "release_speed",
             "pfx_x", "pfx_z", "plate_x", "plate_z", "description"])
    .collect()
)

# CSV aggregations -- eager is fine for small filtered datasets
season_agg = pl.read_csv("aggs/2026-pitcher.csv").filter(pl.col("pitcher") == pitcher_id)
```

**Multi-grain assembly pattern:** Load each aggregation grain independently, filter to target pitcher, then join or pass as separate DataFrames to the context builder. Do NOT try to create one giant joined table -- the grains have different cardinalities (season=1 row, appearance=N rows, pitch-type-appearance=NxM rows).

```python
# Each grain is its own DataFrame, filtered to pitcher
season = pl.read_csv("aggs/2026-pitcher.csv").filter(pl.col("pitcher") == pid)
season_by_type = pl.read_csv("aggs/2026-pitcher_type.csv").filter(pl.col("pitcher") == pid)
appearances = pl.read_csv("aggs/2026-pitcher_appearance.csv").filter(pl.col("pitcher") == pid)
app_by_type = pl.read_csv("aggs/2026-pitcher_type_appearance.csv").filter(pl.col("pitcher") == pid)

# Compute deltas in polars, not in the LLM
recent = app_by_type.sort("game_date").tail(lookback_window)
baseline = season_by_type
deltas = compute_usage_deltas(recent, baseline)  # Custom function
```

**Confidence:** HIGH -- standard polars patterns verified via official docs.

### CLI: Use argparse (stdlib)

For a CLI with exactly two arguments (`-p pitcher_id` and `-w lookback_window`), argparse is the right choice. Zero external dependencies. The CLI surface is too small to justify pulling in typer/click.

```python
import argparse

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate LLM scouting reports for MLB pitchers"
    )
    parser.add_argument("-p", "--pitcher", type=int, required=True,
                        help="Statcast pitcher ID")
    parser.add_argument("-w", "--window", type=int, default=10,
                        help="Lookback window in days (default: 10)")
    parser.add_argument("-o", "--output", choices=["terminal", "markdown", "file"],
                        default="terminal", help="Output format")
    return parser.parse_args()
```

**Confidence:** HIGH -- argparse is stdlib, stable, well-documented. No version concerns.

### Report Rendering: rich

Use rich's `Console` for terminal output and `Markdown` rendering. The scouting report contains both prose paragraphs and data tables -- rich handles both natively.

```python
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

console = Console()

# Render prose sections as markdown
console.print(Markdown(f"## Fastball Assessment\n\n{report.fastball_assessment}"))

# Render data tables with rich.table
table = Table(title="Pitch Usage")
table.add_column("Pitch", style="cyan")
table.add_column("Usage%", justify="right")
table.add_column("Delta", justify="right")
for row in report.pitch_usage_table:
    table.add_row(row["pitch"], row["usage"], row["delta"])
console.print(table)
```

For file output, use `Console(file=..., force_terminal=False)` to write plain text, or generate raw markdown strings directly from the Pydantic model fields.

**Confidence:** HIGH -- rich 14.x is production-stable, supports Python 3.14, widely used.

## Installation

```bash
# Core dependencies (add to pyproject.toml)
uv add "polars>=1.39.3" "pydantic-ai>=1.72.0" "rich>=14.3.3" "python-dotenv>=1.1.0"

# Dev dependencies
uv add --dev ruff pytest
```

Updated `pyproject.toml` dependencies section:
```toml
dependencies = [
    "polars>=1.39.3",
    "pydantic-ai>=1.72.0",
    "rich>=14.3.3",
    "python-dotenv>=1.1.0",
]
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| argparse (stdlib) | typer 0.24.x | If CLI grows beyond 3-4 commands with subcommands. Typer adds rich error display and auto-completion, but pulls in click+rich+shellingham as deps. Overkill for `-p` and `-w`. |
| pydantic-ai | instructor | If you need structured output without the agent abstraction. Instructor is lighter but lacks dependency injection, dynamic instructions, and retry-on-validation-failure. pydantic-ai is strictly better for this use case. |
| pydantic-ai | langchain | Never for this project. LangChain's abstractions add complexity without value for a single-agent, single-model CLI tool. |
| polars | pandas | If you need compatibility with a library that only accepts pandas DataFrames. Polars is faster, more memory-efficient, and has cleaner syntax for the group_by/agg patterns this project needs. |
| rich | plain print | If you want zero dependencies for output. But scouting reports with tables look dramatically better with rich formatting. Worth the dep. |
| python-dotenv | pydantic-settings | If config grows beyond a single API key (e.g., multiple env vars, nested settings, validation). For one env var, python-dotenv is simpler. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| pandas | Slower, higher memory, worse API for lazy eval and aggregations. No predicate pushdown on parquet. | polars |
| langchain | Massive dependency tree, unnecessary abstraction layers for a single-agent tool. Adds complexity without value. | pydantic-ai directly |
| openai SDK | Wrong provider. Project uses Claude. | pydantic-ai with anthropic provider |
| jinja2 templates | Over-engineering for report formatting. The LLM generates prose; rich renders it. No template engine needed. | rich + direct string formatting |
| click | Intermediate abstraction that typer supersedes. If you want more than argparse, skip to typer. | argparse (simple) or typer (complex) |
| f-strings for tables | Fragile alignment, no color, no wrapping. | rich.table.Table |
| PYTHON_GIL=0 / free-threading | Polars' Rust bindings are NOT audited for GIL-free operation. Will cause silent data corruption or crashes. | Default GIL-enabled Python 3.14 |

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| pydantic-ai >=1.72.0 | Python 3.10-3.14 | Requires pydantic v2. Installs anthropic SDK transitively when using `pydantic-ai[anthropic]` or full `pydantic-ai`. |
| polars >=1.39.3 | Python 3.10-3.13 (3.14 in progress) | PyPI classifiers list through 3.13. Works on 3.14 in practice (polars-bio confirmed 3.14 support Feb 2026), but not officially classified yet. **LOW confidence on 3.14 -- verify with `uv run python -c "import polars"` before committing to 3.14.** |
| pydantic >=2.12.5 | Python 3.9-3.14 | Explicitly classifies 3.14 support. |
| rich >=14.3.3 | Python 3.8-3.14 | Explicitly classifies 3.14 support. No compatibility concerns. |
| python-dotenv >=1.1.0 | Python 3.9+ | Lightweight, no native extensions. Works everywhere. |

### Python 3.14 Compatibility Risk

Polars 1.39.3 does not officially list Python 3.14 in its PyPI classifiers (stops at 3.13). The project already has `requires-python = ">=3.14"` in pyproject.toml and `polars>=1.39.3` in dependencies. This likely works (Rust extensions compile against the stable ABI) but should be verified early in development. If polars fails to import on 3.14, the fallback is to pin to Python 3.13 or wait for the next polars release.

**Mitigation:** Run `uv run python -c "import polars; print(polars.__version__)"` as the first task in Phase 1 to confirm compatibility.

## Stack Patterns

**For structured report output (recommended):**
- Use `output_type=ScoutingReport` (Pydantic model with str narrative fields)
- Each section is a field with `Field(description=...)` to guide the LLM
- pydantic-ai validates structure, retries on failure
- rich renders each field independently with appropriate formatting

**For streaming terminal output (optional enhancement):**
- Use `output_type=str` with `run_stream_sync()` for real-time terminal display
- Sacrifice structured validation for streaming UX
- Better for interactive use, worse for file output
- Consider as a Phase 2 enhancement after core report works

**For delta computation (critical pattern):**
- Compute ALL deltas, trends, and qualitative labels in Python/polars BEFORE sending to LLM
- LLM receives pre-digested context like "Slider Usage: 32% (Baseline: 20%, +12pp, HIGH INCREASE)"
- LLM writes insight ("leaned heavily on his slider, nearly doubling usage..."), not arithmetic
- This is the single most important architectural decision for report quality

## Sources

- [pydantic-ai official docs](https://ai.pydantic.dev/) -- Agent API, output types, Anthropic configuration (HIGH confidence)
- [pydantic-ai Anthropic provider](https://ai.pydantic.dev/models/anthropic/) -- Model strings, settings, caching (HIGH confidence)
- [pydantic-ai output docs](https://ai.pydantic.dev/output/) -- TextOutput, structured output, union types (HIGH confidence)
- [Polars user guide](https://docs.pola.rs/user-guide/) -- Lazy API, aggregation, scan_parquet (HIGH confidence)
- [Polars PyPI](https://pypi.org/project/polars/) -- Version 1.39.3, Python classifiers (HIGH confidence)
- [rich PyPI](https://pypi.org/project/rich/) -- Version 14.3.3, Python 3.14 support (HIGH confidence)
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview) -- Claude Sonnet 4.6 as current default model (HIGH confidence)
- [pydantic-ai streaming docs](https://deepwiki.com/pydantic/pydantic-ai/4.1-streaming-and-real-time-processing) -- run_stream_sync pattern (MEDIUM confidence -- DeepWiki, not official)
- [Polars + Python 3.14](https://biodatageeks.org/polars-bio/blog/2026/02/14/polars-bio-0230-faster-parsing-and-python-314-support/) -- polars-bio 3.14 support confirmation (MEDIUM confidence -- adjacent project, not polars core)

---
*Stack research for: LLM-powered pitching scouting report CLI*
*Researched: 2026-03-26*
