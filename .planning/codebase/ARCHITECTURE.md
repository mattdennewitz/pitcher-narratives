# Architecture

**Analysis Date:** 2026-03-26

## Pattern Overview

**Overall:** Minimal scaffold -- single-file script with no architecture yet established

This project is in its earliest stage: a `uv`-managed Python project with two declared dependencies (Polars and pydantic-ai) and a hello-world entry point. No application architecture, layers, or abstractions exist yet. The dependency choices signal the intended direction: data processing with Polars and LLM-powered AI agent workflows with pydantic-ai.

**Key Characteristics:**
- Single-file Python project with no package structure
- No src layout, no modules, no internal packages
- Dependencies locked via `uv.lock` but not yet imported anywhere
- pydantic-ai v1.72.0 pulls in a large transitive dependency tree including support for Anthropic, OpenAI, Google, Groq, Mistral, Cohere, Bedrock, xAI, Hugging Face, and Vertex AI model providers
- Polars v1.39.3 available for high-performance DataFrame operations

## Intended Architecture (Inferred from Dependencies)

Based on the declared dependencies, the project will likely adopt:

**pydantic-ai Agent Pattern:**
- Define `Agent` instances with structured output types (Pydantic models)
- Use tools (decorated functions) to give agents capabilities
- Use `result_type` to enforce structured LLM responses
- pydantic-ai supports dependency injection via `RunContext` for passing runtime state to tools
- pydantic-graph (included transitively) supports multi-step agent workflows as directed graphs

**Polars Data Processing:**
- Use Polars DataFrames/LazyFrames for data ingestion, transformation, and analysis
- Polars excels at columnar operations on structured/tabular data
- Likely used for processing baseball/pitcher statistics or similar structured datasets

**Suggested Layering (for when architecture is established):**
1. **Data Layer** -- Polars-based data loading and transformation
2. **Agent Layer** -- pydantic-ai Agent definitions with tools and structured outputs
3. **Orchestration Layer** -- Coordination of data retrieval and narrative generation
4. **Entry Point** -- CLI or script that ties it all together

## Layers

**Currently: Single Entry Point**
- Purpose: Placeholder main function
- Location: `main.py`
- Contains: A single `main()` function that prints a greeting
- Depends on: Nothing (no imports)
- Used by: Direct script execution (`python main.py`)

## Data Flow

**Current:** None. The only execution path is:

1. `main.py` is invoked
2. `main()` prints "Hello from pitcher-narratives!"
3. Process exits

**Anticipated Data Flow (based on project name and dependencies):**

1. Load/fetch pitcher performance data (source TBD)
2. Process data into structured form using Polars
3. Pass structured data to pydantic-ai Agent as context
4. Agent generates narrative text based on the data
5. Return structured output (narrative + metadata)

## Key Abstractions

**None yet.** When built, expect:

**Pydantic Models:**
- Purpose: Define structured data schemas for both input data and LLM outputs
- Pattern: Pydantic BaseModel subclasses with typed fields

**pydantic-ai Agents:**
- Purpose: Wrap LLM calls with structured inputs/outputs and tool access
- Pattern: `Agent(model, result_type=MyModel, system_prompt="...")` instances
- Each agent gets a model provider, optional tools, and a result type

**Polars DataFrames:**
- Purpose: Efficient tabular data processing
- Pattern: Load data into `pl.DataFrame` or `pl.LazyFrame`, transform with expressions

## Entry Points

**`main.py`:**
- Location: `/Users/matt/src/pitcher-narratives/main.py`
- Triggers: `python main.py` or `uv run main.py`
- Responsibilities: Currently just prints a greeting. Will become the primary entry point.

## Error Handling

**Strategy:** Not yet established.

**Recommendations based on pydantic-ai patterns:**
- pydantic-ai raises `UnexpectedModelBehavior` for malformed LLM responses
- Use `ModelRetry` exception inside tools to signal the agent to retry
- Polars raises `polars.exceptions.PolarsError` subtypes for data issues
- Pydantic raises `ValidationError` for schema violations

## Cross-Cutting Concerns

**Logging:** Not configured. pydantic-ai integrates with Logfire (included as a transitive dependency via the `logfire` extra) and OpenTelemetry for observability.

**Validation:** Pydantic is the validation layer. All structured data should flow through Pydantic models.

**Authentication:** Not applicable yet. LLM API keys will be needed at runtime (typically via environment variables like `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).

**Configuration:** No configuration system yet. pydantic-settings is available as a transitive dependency and is the natural choice for environment-based configuration.

---

*Architecture analysis: 2026-03-26*
