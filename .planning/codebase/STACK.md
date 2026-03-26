# Technology Stack

**Analysis Date:** 2026-03-26

## Languages

**Primary:**
- Python 3.14 - All application code (pinned in `.python-version` and `pyproject.toml` via `requires-python = ">=3.14"`)

## Runtime

**Environment:**
- CPython 3.14
- Virtual environment managed via `uv` at `.venv/`

**Package Manager:**
- uv (inferred from `uv.lock` format and `.venv` structure)
- Lockfile: present (`uv.lock`, 148 locked packages)

## Frameworks

**Core:**
- pydantic-ai 1.72.0 - AI agent framework for building LLM-powered applications
- polars 1.39.3 - High-performance DataFrame library (Rust-backed via `polars-runtime-32`)

**Data Validation:**
- pydantic 2.12.5 - Data validation and settings (transitive via pydantic-ai)
- pydantic-settings 2.13.1 - Configuration management with env var support (transitive)

**AI/LLM Providers (all bundled as pydantic-ai extras):**
- openai 2.30.0 - OpenAI API client
- anthropic 0.86.0 - Anthropic (Claude) API client
- google-genai 1.68.0 - Google Gemini API client
- groq 1.1.2 - Groq API client
- mistralai 2.1.3 - Mistral AI client
- cohere 5.21.1 - Cohere API client
- xai-sdk 1.10.0 - xAI (Grok) API client
- boto3 1.42.76 - AWS Bedrock support

**Agent Infrastructure (transitive via pydantic-ai):**
- pydantic-graph 1.72.0 - Graph-based agent workflows
- pydantic-evals 1.72.0 - LLM evaluation framework
- fastmcp 3.1.1 - Model Context Protocol server/client
- mcp 1.26.0 - MCP protocol base
- temporalio 1.20.0 - Temporal workflow orchestration
- ag-ui-protocol 0.1.14 - Agent UI protocol

**Observability (transitive via pydantic-ai):**
- logfire 4.30.0 - Pydantic Logfire observability platform
- opentelemetry-api - OpenTelemetry tracing
- opentelemetry-sdk - OpenTelemetry SDK
- opentelemetry-exporter-otlp-proto-http - OTLP exporter

**HTTP/Networking:**
- httpx - Async HTTP client (used by all LLM provider SDKs)
- aiohttp 3.13.3 - Async HTTP (used by xai-sdk)
- starlette - ASGI framework (for agent UI serving)

**CLI (transitive via pydantic-ai[cli]):**
- rich - Terminal formatting
- prompt-toolkit - Interactive CLI
- argcomplete - Shell completion
- typer - CLI framework

**Build/Dev:**
- No explicit dev dependencies declared
- No test framework declared
- No linting/formatting tools declared

## Key Dependencies

**Critical (direct):**
- polars >=1.39.3 - DataFrame operations for data analysis/transformation
- pydantic-ai >=1.72.0 - AI agent framework (brings in all LLM provider SDKs)

**Infrastructure (transitive, high-impact):**
- pydantic 2.12.5 - Core data modeling throughout the stack
- httpx - HTTP transport for all API calls
- opentelemetry-api - Tracing/observability backbone

## Configuration

**Environment:**
- No `.env` file present
- No `.gitignore` in project root (only in `.venv/`)
- `pydantic-settings` is available (transitive) for env var configuration via `python-dotenv`
- LLM API keys will be needed at runtime (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)

**Build:**
- `pyproject.toml` - Project metadata and dependencies
- `uv.lock` - Deterministic dependency resolution
- `.python-version` - Python version pin (3.14)

## Platform Requirements

**Development:**
- Python 3.14+
- uv package manager
- macOS / Linux (primary targets based on lock file wheels)

**Production:**
- Python 3.14 runtime
- Network access to chosen LLM provider APIs
- Environment variables for API keys and configuration

## Project Maturity

This is a scaffold/greenfield project:
- Single `main.py` with a hello-world function
- No application logic implemented yet
- No tests, no linting config, no CI/CD
- Dependencies suggest intended use: AI-powered data analysis/narrative generation using polars for data processing and pydantic-ai for LLM orchestration

---

*Stack analysis: 2026-03-26*
