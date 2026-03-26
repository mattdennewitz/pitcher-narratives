# Architecture Research

**Domain:** LLM-powered data analysis report (CLI pipeline)
**Researched:** 2026-03-26
**Confidence:** HIGH

## System Overview

```
                        pitcher-narratives pipeline
 -----------------------------------------------------------------------
|                                                                       |
|  CLI Entry Point                                                      |
|  (argparse: -p pitcher_id -w lookback_days)                           |
|       |                                                               |
|       v                                                               |
|  +-----------+     +----------------+     +-------------------+       |
|  | Data      |---->| Delta          |---->| Schema            |       |
|  | Loader    |     | Engine         |     | Assembler         |       |
|  +-----------+     +----------------+     +-------------------+       |
|       |                   |                        |                  |
|       | reads             | computes               | produces        |
|       v                   v                        v                  |
|  +-----------+     +----------------+     +-------------------+       |
|  | statcast  |     | baselines vs   |     | Pydantic models   |       |
|  | .parquet  |     | recent deltas  |     | (LLM input schema)|       |
|  | aggs/*.csv|     | qualitative    |     +--------+----------+       |
|  +-----------+     | trend strings  |              |                  |
|                    +----------------+              | deps injection   |
|                                                    v                  |
|                                            +-------------------+      |
|                                            | Report            |      |
|                                            | Generator         |      |
|                                            | (pydantic-ai      |      |
|                                            |  Agent + Claude)  |      |
|                                            +--------+----------+      |
|                                                     |                 |
|                                                     v                 |
|                                            +-------------------+      |
|                                            | Output Formatter  |      |
|                                            | (stdout / file)   |      |
|                                            +-------------------+      |
 -----------------------------------------------------------------------
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| **CLI** | Parse args, validate pitcher ID exists in data, orchestrate pipeline | `argparse` or `click`, top-level `main()` |
| **Data Loader** | Read parquet + CSVs, filter to target pitcher, return typed DataFrames | `polars` read/scan, returns pitcher-scoped data |
| **Delta Engine** | Compute baselines, recent windows, deltas, qualitative trend strings | Pure polars transforms, no LLM involvement |
| **Schema Assembler** | Map computed data into Pydantic models that form the LLM's input context | Pydantic `BaseModel` construction from DataFrames |
| **Report Generator** | Send structured context to Claude, get narrative back | `pydantic-ai` Agent with `deps_type` and `output_type` |
| **Output Formatter** | Render final report to terminal or file | Print/write, minimal logic |

## Recommended Project Structure

```
pitcher_narratives/
├── __init__.py
├── cli.py                  # Entry point, arg parsing, pipeline orchestration
├── loader.py               # Data loading and pitcher-scoping
├── models/
│   ├── __init__.py
│   ├── context.py          # Pydantic models for LLM input (the "schema")
│   └── report.py           # Pydantic models for LLM output (optional structured output)
├── engine/
│   ├── __init__.py
│   ├── classify.py         # Starter vs reliever detection
│   ├── fastball.py         # Fastball quality deltas (velo, shape, IVB trends)
│   ├── arsenal.py          # Usage rates, platoon shifts, first-pitch mix
│   ├── execution.py        # CSW%, zone rate, chase rate, P+/S+/L+ trends
│   └── context.py          # Rest days, innings depth, workload
├── agent.py                # pydantic-ai Agent definition, prompts, report generation
└── formatting.py           # Output rendering (terminal, file)
```

### Structure Rationale

- **`models/`**: Separates the data contracts (what the LLM sees and produces) from the computation logic. These Pydantic models are the most important design artifact in the project -- they define the interface between Python computation and LLM reasoning.
- **`engine/`**: Each file computes one section of the scouting report. Files are split by report section, not by data source. This means `fastball.py` reads from both Statcast (velo, movement) and P+ aggregations (S+ trends) as needed. The boundary is "what story does this section tell" not "which table does this query."
- **`agent.py`**: Single file for the pydantic-ai Agent. Keeps all LLM interaction (system prompt, dependency wiring, output handling) in one place.
- **`cli.py`**: Thin orchestrator. Calls loader, engine, assembler, agent, formatter in sequence. No business logic here.

## Architectural Patterns

### Pattern 1: Deps-as-Context (pydantic-ai dependency injection)

**What:** Package all computed pitcher data into a single dataclass, inject it as `deps_type` into the pydantic-ai Agent. Dynamic system prompt functions read from `ctx.deps` to build the full context string the LLM sees.

**When to use:** Always -- this is how pydantic-ai is designed to work for data-driven prompts.

**Trade-offs:** The LLM never sees raw DataFrames; it sees pre-formatted text/tables assembled from Pydantic models. This is correct because the LLM should receive pre-digested insight material, not raw data.

**Example:**

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from pitcher_narratives.models.context import PitcherContext

@dataclass
class ReportDeps:
    context: PitcherContext  # all computed data for this pitcher

agent = Agent(
    "anthropic:claude-sonnet-4-20250514",
    deps_type=ReportDeps,
    output_type=str,  # narrative prose output
    instructions="You are a major league scout writing pitcher reports...",
)

@agent.instructions
def inject_pitcher_context(ctx: RunContext[ReportDeps]) -> str:
    """Build the full data context from computed pitcher analysis."""
    return ctx.deps.context.to_prompt()  # renders structured data as text
```

### Pattern 2: Pre-Compute Everything, LLM Writes Insight

**What:** All arithmetic (deltas, trends, baselines, qualitative flags) happens in Python/polars before the LLM sees anything. The LLM receives statements like "Slider usage: 32% (season baseline: 20%, trend: SIGNIFICANT INCREASE)" -- never raw numbers to do math with.

**When to use:** Always for this type of data analysis pipeline. LLMs are unreliable at arithmetic but excellent at synthesizing pre-computed findings into narrative.

**Trade-offs:** More Python code to write, but dramatically better report quality. The LLM can focus on "what does this mean" instead of "what is 32 minus 20."

**Example:**

```python
# In engine/arsenal.py
def compute_usage_deltas(
    baseline_usage: dict[str, float],
    recent_usage: dict[str, float],
) -> list[UsageDelta]:
    deltas = []
    for pitch_type, recent_pct in recent_usage.items():
        baseline_pct = baseline_usage.get(pitch_type, 0.0)
        delta = recent_pct - baseline_pct
        trend = classify_trend(delta)  # "Significant Increase", "Slight Decrease", etc.
        deltas.append(UsageDelta(
            pitch_type=pitch_type,
            recent_pct=recent_pct,
            baseline_pct=baseline_pct,
            delta=delta,
            trend=trend,
        ))
    return deltas
```

### Pattern 3: Layered Pydantic Models for LLM Context

**What:** The Pydantic models form a hierarchy: leaf models hold individual computed facts (e.g., `VeloTrend`), section models aggregate them (e.g., `FastballQuality`), and a top-level `PitcherContext` holds all sections. Each model has a `to_prompt()` method that renders itself as formatted text suitable for the LLM.

**When to use:** When the LLM input is complex and multi-section. The hierarchy makes it easy to test each section independently and to control exactly what text the LLM sees.

**Trade-offs:** More models to define upfront, but they serve as living documentation of "what does the LLM know about this pitcher" and are trivially unit-testable.

**Example:**

```python
class VeloTrend(BaseModel):
    pitch_type: str
    season_avg: float
    recent_avg: float
    last_game_avg: float
    delta_season_to_recent: float
    trend: str  # "Stable", "Ticking Up", "Declining", etc.

    def to_prompt(self) -> str:
        return (
            f"{self.pitch_type}: {self.recent_avg:.1f} mph "
            f"(season: {self.season_avg:.1f}, {self.trend})"
        )

class FastballQuality(BaseModel):
    velo_trends: list[VeloTrend]
    ivb_delta: float | None
    hb_delta: float | None
    arm_angle_note: str | None

    def to_prompt(self) -> str:
        lines = ["## Fastball Quality"]
        for vt in self.velo_trends:
            lines.append(f"- {vt.to_prompt()}")
        if self.ivb_delta is not None:
            lines.append(f"- IVB change: {self.ivb_delta:+.1f} in")
        return "\n".join(lines)

class PitcherContext(BaseModel):
    pitcher_name: str
    pitcher_id: int
    role: str  # "starter" | "reliever"
    fastball: FastballQuality
    arsenal: ArsenalAnalysis
    execution: ExecutionMetrics
    context: GameContext

    def to_prompt(self) -> str:
        sections = [
            f"# Scouting Report Data: {self.pitcher_name} ({self.role.title()})",
            self.fastball.to_prompt(),
            self.arsenal.to_prompt(),
            self.execution.to_prompt(),
            self.context.to_prompt(),
        ]
        return "\n\n".join(sections)
```

## Data Flow

### Pipeline Flow (single invocation)

```
CLI: parse(-p 608331 -w 10)
    |
    v
Loader: read parquet + CSVs, filter pitcher=608331
    |
    +---> statcast_df: DataFrame (365 rows, pitcher's pitches)
    +---> season_aggs: DataFrame (1 row, season P+/S+/L+)
    +---> pitch_type_aggs: DataFrame (~5 rows, per-pitch-type season)
    +---> appearance_aggs: DataFrame (~8 rows, per-game P+)
    +---> pitch_type_appearance_aggs: DataFrame (~30 rows, per-pitch per-game)
    +---> platoon_aggs: DataFrame (~10 rows, per-pitch per-platoon)
    +---> platoon_appearance_aggs: DataFrame (~50 rows, per-pitch per-platoon per-game)
    +---> team_aggs: DataFrame (1 row, team context)
    |
    v
Classify: starter or reliever? (from appearance frequency + pitch count patterns)
    |
    v
Engine: compute deltas for each report section
    |
    +---> fastball.compute(statcast_df, pitch_type_aggs, appearance_aggs, lookback=10)
    |       -> VeloTrend[], IVB delta, HB delta, arm angle note
    |
    +---> arsenal.compute(statcast_df, pitch_type_aggs, platoon_aggs, lookback=10)
    |       -> UsageDelta[], platoon shifts, first-pitch mix
    |
    +---> execution.compute(statcast_df, season_aggs, appearance_aggs, pitch_type_appearance_aggs)
    |       -> CSW%, zone rate, chase rate, P+/S+/L+ trends
    |
    +---> context.compute(appearance_aggs, role, lookback=10)
    |       -> rest days, innings depth, pitch count trend
    |
    v
Schema Assembler: instantiate PitcherContext from engine outputs
    |
    v
Agent: agent.run_sync(user_prompt, deps=ReportDeps(context=pitcher_context))
    |
    +---> @agent.instructions renders pitcher_context.to_prompt()
    +---> Claude generates narrative prose
    |
    v
Output Formatter: print report to stdout
```

### Key Data Flows

1. **Parquet -> Filtered DataFrame -> Engine computations:** The loader reads the full parquet once (20MB, fast in polars), filters to the target pitcher. Each engine module receives the same filtered DataFrame plus relevant aggregation DataFrames. Engine modules are pure functions: DataFrames in, Pydantic models out.

2. **Engine outputs -> PitcherContext -> LLM prompt:** The schema assembler is trivial -- it just constructs the top-level `PitcherContext` from engine outputs. The `to_prompt()` method chain converts structured data into the text the LLM actually sees. This is the critical formatting boundary.

3. **LLM response -> stdout:** The agent returns `str` (narrative prose). The output formatter adds any terminal formatting (headers, dividers) and prints. No structured output parsing needed on the way out -- the value is in the prose, not in structured data extraction.

## Build Order (dependency chain)

The components have a strict dependency chain that dictates build order:

```
Phase 1: models/context.py    (Pydantic schemas -- the contract everything depends on)
         loader.py             (data loading -- independent, needed by everything)

Phase 2: engine/classify.py   (starter vs reliever -- gates report structure)
         engine/fastball.py    (first report section)
         engine/arsenal.py     (second report section)
         engine/execution.py   (third report section)
         engine/context.py     (fourth report section)

Phase 3: agent.py             (LLM wiring -- needs models + engine to exist)
         models/report.py      (output model, if using structured output)

Phase 4: cli.py               (orchestration -- needs everything above)
         formatting.py         (presentation -- needs agent output)
```

**Why this order:**

1. **Models first** because every other component depends on the data contract. If you change what the LLM sees, you change what the engine must produce. Design the Pydantic schema to match the report philosophy (deltas, trends, qualitative strings), then build the engine to produce exactly that.

2. **Loader early** because you cannot develop or test engine code without real data flowing through.

3. **Engine modules are parallelizable** -- they have no dependencies on each other. Each takes DataFrames and produces its own section model. Build them in report-section order (fastball first because it's the foundation of scouting).

4. **Agent after engine** because the system prompt and dependency injection pattern depend on the finalized PitcherContext shape.

5. **CLI last** because it's pure orchestration glue.

## Anti-Patterns

### Anti-Pattern 1: Sending Raw DataFrames to the LLM

**What people do:** Serialize a DataFrame to CSV/JSON and paste it into the prompt, expecting the LLM to compute deltas and find patterns.

**Why it's wrong:** LLMs miscalculate. With 30+ rows of numeric data, the LLM will make arithmetic errors, miss important deltas, and waste context window on raw numbers instead of insight. Token cost explodes.

**Do this instead:** Pre-compute every delta, trend, and qualitative flag in Python. The LLM receives "Slider usage increased from 20% to 32% (Significant Increase)" not 30 rows of pitch-by-pitch data.

### Anti-Pattern 2: One Giant System Prompt String

**What people do:** Build the entire LLM prompt as a single f-string or template with all data inlined.

**Why it's wrong:** Untestable, unmaintainable, impossible to iterate on individual sections. Prompt changes require editing a wall of text.

**Do this instead:** Use the layered Pydantic model pattern with `to_prompt()` methods. Each section is independently testable. The system prompt is composed from typed, validated data structures. Use pydantic-ai's `@agent.instructions` decorator to inject the data context dynamically from deps.

### Anti-Pattern 3: Lazy Loading Every File on Every Run

**What people do:** Scan all 8 CSV files lazily and filter each independently, resulting in 8+ file reads.

**Why it's wrong:** At this data scale (20MB parquet, ~100MB total CSVs), the overhead of "smart" lazy loading exceeds the cost of just reading the files. Premature optimization that adds complexity.

**Do this instead:** Read the parquet eagerly with `pl.read_parquet()` once. For CSVs, read them eagerly and filter. The entire dataset fits comfortably in memory. Use `pl.scan_parquet` only if the dataset grows past ~1GB.

### Anti-Pattern 4: Structured Output for Narrative Reports

**What people do:** Define a complex Pydantic `output_type` with fields for each paragraph, forcing the LLM to fill structured JSON for prose content.

**Why it's wrong:** Narrative prose is inherently unstructured. Forcing it into JSON fields constrains the LLM's writing quality and creates awkward paragraph boundaries. The value of this tool is scout-quality prose, not structured data extraction.

**Do this instead:** Use `output_type=str` for the narrative report. All structure lives in the INPUT (the Pydantic context models). The output is free-form prose that reads like a human wrote it.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Claude (Anthropic API) | Via pydantic-ai Agent, `anthropic:claude-sonnet-4-20250514` or similar model string | Requires `ANTHROPIC_API_KEY` env var. pydantic-ai handles retries and validation. Single API call per report. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Loader -> Engine | Polars DataFrames passed as function args | Loader returns a typed dataclass or NamedTuple of filtered DataFrames |
| Engine -> Schema Assembler | Pydantic models (section-level) | Each engine module returns its section model |
| Schema Assembler -> Agent | `PitcherContext` as `deps.context` | The `to_prompt()` chain renders the full context string |
| Agent -> Formatter | `str` (narrative prose) | Plain text, possibly with markdown formatting |

## Scaling Considerations

| Concern | Current (1 pitcher/run) | Batch mode (100 pitchers) | Notes |
|---------|------------------------|--------------------------|-------|
| Data loading | ~0.5s, read all + filter | Read once, filter 100x | Parquet scan is fast; CSV reads are the bottleneck at batch scale |
| Computation | ~0.1s per pitcher | ~10s for 100 | Engine functions are pure polars, very fast |
| LLM calls | ~5-15s (single API call) | 100 serial calls = 8-25 min | Batch would need async `agent.run()` with concurrency limit |
| Memory | ~200MB (all data in memory) | Same ~200MB (data shared) | Data does not scale with pitcher count |

### Scaling Priorities

1. **First bottleneck: LLM latency.** At ~10s per report, batch mode is I/O bound on the API. If batch mode is ever needed, use `asyncio.gather` with a concurrency semaphore (3-5 concurrent calls). This is not needed for MVP.
2. **Second bottleneck: CSV read time.** The `2026-all_pitches.csv` is 83MB. If batch mode is needed, read it once and pass the full DataFrame to each pitcher's engine. Alternatively, convert it to parquet for faster reads.

## Sources

- [Pydantic AI Agent documentation](https://ai.pydantic.dev/agent/)
- [Pydantic AI Dependencies documentation](https://ai.pydantic.dev/dependencies/)
- [Pydantic AI Output documentation](https://ai.pydantic.dev/output/)
- [Polars Parquet I/O guide](https://docs.pola.rs/user-guide/io/parquet/)
- [Polars scan_parquet API](https://docs.pola.rs/api/python/dev/reference/api/polars.scan_parquet.html)
- Actual data inspection of `statcast_2026.parquet` and `aggs/*.csv` in this repository

---
*Architecture research for: pitcher-narratives (LLM-powered scouting report CLI)*
*Researched: 2026-03-26*
