<!-- GSD:project-start source:PROJECT.md -->
## Project

**Pitcher Narratives**

A CLI tool that generates LLM-written scouting reports for MLB pitchers. Given a pitcher ID, it assembles pitch-level Statcast data and pre-computed Pitching+ aggregations into a structured context document, then sends it to Claude to produce an insightful narrative assessment of the pitcher's most recent appearance relative to recent trends.

**Core Value:** The report must read like a scout wrote it — surfacing *changes, adaptations, and execution trends* rather than reciting numbers. The LLM gets pre-computed deltas and baselines so it can focus on insight, not arithmetic.

### Constraints

- **Tech stack**: Python, polars, pydantic-ai, Claude — already in pyproject.toml
- **Data format**: Static parquet + CSV files, no live API calls to Baseball Savant
- **Python version**: 3.14+
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.14 - All application code (pinned in `.python-version` and `pyproject.toml` via `requires-python = ">=3.14"`)
## Runtime
- CPython 3.14
- Virtual environment managed via `uv` at `.venv/`
- uv (inferred from `uv.lock` format and `.venv` structure)
- Lockfile: present (`uv.lock`, 148 locked packages)
## Frameworks
- pydantic-ai 1.72.0 - AI agent framework for building LLM-powered applications
- polars 1.39.3 - High-performance DataFrame library (Rust-backed via `polars-runtime-32`)
- pydantic 2.12.5 - Data validation and settings (transitive via pydantic-ai)
- pydantic-settings 2.13.1 - Configuration management with env var support (transitive)
- openai 2.30.0 - OpenAI API client
- anthropic 0.86.0 - Anthropic (Claude) API client
- google-genai 1.68.0 - Google Gemini API client
- groq 1.1.2 - Groq API client
- mistralai 2.1.3 - Mistral AI client
- cohere 5.21.1 - Cohere API client
- xai-sdk 1.10.0 - xAI (Grok) API client
- boto3 1.42.76 - AWS Bedrock support
- pydantic-graph 1.72.0 - Graph-based agent workflows
- pydantic-evals 1.72.0 - LLM evaluation framework
- fastmcp 3.1.1 - Model Context Protocol server/client
- mcp 1.26.0 - MCP protocol base
- temporalio 1.20.0 - Temporal workflow orchestration
- ag-ui-protocol 0.1.14 - Agent UI protocol
- logfire 4.30.0 - Pydantic Logfire observability platform
- opentelemetry-api - OpenTelemetry tracing
- opentelemetry-sdk - OpenTelemetry SDK
- opentelemetry-exporter-otlp-proto-http - OTLP exporter
- httpx - Async HTTP client (used by all LLM provider SDKs)
- aiohttp 3.13.3 - Async HTTP (used by xai-sdk)
- starlette - ASGI framework (for agent UI serving)
- rich - Terminal formatting
- prompt-toolkit - Interactive CLI
- argcomplete - Shell completion
- typer - CLI framework
- No explicit dev dependencies declared
- No test framework declared
- No linting/formatting tools declared
## Key Dependencies
- polars >=1.39.3 - DataFrame operations for data analysis/transformation
- pydantic-ai >=1.72.0 - AI agent framework (brings in all LLM provider SDKs)
- pydantic 2.12.5 - Core data modeling throughout the stack
- httpx - HTTP transport for all API calls
- opentelemetry-api - Tracing/observability backbone
## Configuration
- No `.env` file present
- No `.gitignore` in project root (only in `.venv/`)
- `pydantic-settings` is available (transitive) for env var configuration via `python-dotenv`
- LLM API keys will be needed at runtime (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
- `pyproject.toml` - Project metadata and dependencies
- `uv.lock` - Deterministic dependency resolution
- `.python-version` - Python version pin (3.14)
## Platform Requirements
- Python 3.14+
- uv package manager
- macOS / Linux (primary targets based on lock file wheels)
- Python 3.14 runtime
- Network access to chosen LLM provider APIs
- Environment variables for API keys and configuration
## Project Maturity
- Single `main.py` with a hello-world function
- No application logic implemented yet
- No tests, no linting config, no CI/CD
- Dependencies suggest intended use: AI-powered data analysis/narrative generation using polars for data processing and pydantic-ai for LLM orchestration
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Project Status
## Naming Patterns
- Use `snake_case.py` for all Python modules
- Current example: `main.py`
- Use `snake_case` for all functions and methods
- Current example: `def main():` in `main.py`
- Use `snake_case` for local variables and module-level variables
- Use `UPPER_SNAKE_CASE` for constants
- Use `PascalCase` for classes, Pydantic models, and type aliases
- Use Pydantic models (from `pydantic` or `pydantic-ai`) for structured data rather than plain dicts
- Use `snake_case` for module and package directory names
## Code Style
- Not yet configured. **Recommendation:** Add `ruff` as a dev dependency and configure in `pyproject.toml`:
- Not yet configured. **Recommendation:** Use `ruff` for linting as well:
- Not yet configured. **Recommendation:** Add `mypy` or `pyright` as a dev dependency. Given the use of Pydantic AI, `pyright` pairs well:
## Import Organization
- Use absolute imports for project modules
- Group imports with a blank line between each section
- Sort alphabetically within each group
- None configured. The project does not yet use a `src/` layout or path aliasing.
## Error Handling
- Use specific exception types, not bare `except:`
- For Pydantic AI agent errors, catch `pydantic_ai` exception types specifically
- For Polars operations, handle `pl.exceptions.ComputeError` and similar
- Use structured logging (not print statements) for error reporting in production code
## Logging
- Use Python's built-in `logging` module or `loguru` for structured logging
- The `pydantic-ai` dependency pulls in `logfire` as a transitive dependency, which could be used for observability
- Replace `print()` calls (currently in `main.py`) with proper logging as the project grows
## Comments
- Add docstrings to all public functions, classes, and modules
- Use inline comments sparingly, only to explain "why" not "what"
- Use type hints on all function signatures instead of documenting parameter types in docstrings
- Use Google-style docstrings:
## Function Design
## Module Design
- Use `__all__` in modules that serve as public APIs
- Keep internal helpers prefixed with `_`
- Use `__init__.py` files for package-level re-exports when creating packages
## Configuration
- No `.env` file exists yet
- No environment configuration pattern established
- **Recommendation:** Use `pydantic-settings` (compatible with the existing Pydantic dependency) for typed environment configuration
- All project metadata is in `pyproject.toml`
- No `[tool.*]` sections configured yet -- all tooling configuration should go here (not in separate config files)
## Entry Point
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Single-file Python project with no package structure
- No src layout, no modules, no internal packages
- Dependencies locked via `uv.lock` but not yet imported anywhere
- pydantic-ai v1.72.0 pulls in a large transitive dependency tree including support for Anthropic, OpenAI, Google, Groq, Mistral, Cohere, Bedrock, xAI, Hugging Face, and Vertex AI model providers
- Polars v1.39.3 available for high-performance DataFrame operations
## Intended Architecture (Inferred from Dependencies)
- Define `Agent` instances with structured output types (Pydantic models)
- Use tools (decorated functions) to give agents capabilities
- Use `result_type` to enforce structured LLM responses
- pydantic-ai supports dependency injection via `RunContext` for passing runtime state to tools
- pydantic-graph (included transitively) supports multi-step agent workflows as directed graphs
- Use Polars DataFrames/LazyFrames for data ingestion, transformation, and analysis
- Polars excels at columnar operations on structured/tabular data
- Likely used for processing baseball/pitcher statistics or similar structured datasets
## Layers
- Purpose: Placeholder main function
- Location: `main.py`
- Contains: A single `main()` function that prints a greeting
- Depends on: Nothing (no imports)
- Used by: Direct script execution (`python main.py`)
## Data Flow
## Key Abstractions
- Purpose: Define structured data schemas for both input data and LLM outputs
- Pattern: Pydantic BaseModel subclasses with typed fields
- Purpose: Wrap LLM calls with structured inputs/outputs and tool access
- Pattern: `Agent(model, result_type=MyModel, system_prompt="...")` instances
- Each agent gets a model provider, optional tools, and a result type
- Purpose: Efficient tabular data processing
- Pattern: Load data into `pl.DataFrame` or `pl.LazyFrame`, transform with expressions
## Entry Points
- Location: `/Users/matt/src/pitcher-narratives/main.py`
- Triggers: `python main.py` or `uv run main.py`
- Responsibilities: Currently just prints a greeting. Will become the primary entry point.
## Error Handling
- pydantic-ai raises `UnexpectedModelBehavior` for malformed LLM responses
- Use `ModelRetry` exception inside tools to signal the agent to retry
- Polars raises `polars.exceptions.PolarsError` subtypes for data issues
- Pydantic raises `ValidationError` for schema violations
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
