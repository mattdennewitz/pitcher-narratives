# External Integrations

**Analysis Date:** 2026-03-26

## APIs & External Services

**LLM Providers (available via pydantic-ai, none yet configured in application code):**

- OpenAI - GPT models
  - SDK/Client: `openai` 2.30.0
  - Auth: `OPENAI_API_KEY`
  - Used by: `pydantic_ai.models.openai`

- Anthropic - Claude models
  - SDK/Client: `anthropic` 0.86.0
  - Auth: `ANTHROPIC_API_KEY`
  - Used by: `pydantic_ai.models.anthropic`

- Google Gemini - Gemini models
  - SDK/Client: `google-genai` 1.68.0
  - Auth: `GOOGLE_API_KEY` or `GOOGLE_APPLICATION_CREDENTIALS`
  - Used by: `pydantic_ai.models.google`

- Groq - Fast inference
  - SDK/Client: `groq` 1.1.2
  - Auth: `GROQ_API_KEY`
  - Used by: `pydantic_ai.models.groq`

- Mistral AI - Mistral models
  - SDK/Client: `mistralai` 2.1.3
  - Auth: `MISTRAL_API_KEY`
  - Used by: `pydantic_ai.models.mistral`

- Cohere - Cohere models
  - SDK/Client: `cohere` 5.21.1
  - Auth: `CO_API_KEY`
  - Used by: `pydantic_ai.models.cohere`

- xAI - Grok models
  - SDK/Client: `xai-sdk` 1.10.0
  - Auth: `XAI_API_KEY`
  - Used by: `pydantic_ai.models.xai`

- AWS Bedrock - AWS-hosted models
  - SDK/Client: `boto3` 1.42.76
  - Auth: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`
  - Used by: `pydantic_ai.models.bedrock`

**Observability:**

- Pydantic Logfire - Tracing and monitoring
  - SDK/Client: `logfire` 4.30.0
  - Auth: `LOGFIRE_TOKEN`
  - Protocol: OpenTelemetry (OTLP over HTTP)
  - Used by: pydantic-ai automatic instrumentation

**MCP (Model Context Protocol):**

- FastMCP - MCP server/client for tool integration
  - SDK/Client: `fastmcp` 3.1.1
  - Auth: varies by MCP server configuration
  - Used by: `pydantic_ai` tool/resource integration

**Workflow Orchestration:**

- Temporal - Durable workflow execution
  - SDK/Client: `temporalio` 1.20.0
  - Auth: Temporal server connection config
  - Used by: `pydantic_ai` for durable agent workflows

## Data Storage

**Databases:**
- None configured. No database client or ORM in direct dependencies.
- polars can read from various sources (CSV, Parquet, JSON, databases via connectors) but none are configured yet.

**File Storage:**
- Local filesystem only (no cloud storage SDK in direct dependencies)
- `fsspec` 0.1+ available transitively (abstract filesystem interface)

**Caching:**
- None configured

## Authentication & Identity

**Auth Provider:**
- Not applicable yet. No auth system implemented.
- `authlib` is available transitively (via fastmcp) for OAuth flows if needed.

## Monitoring & Observability

**Error Tracking:**
- None explicitly configured
- Logfire (via pydantic-ai) provides error tracking when enabled

**Logs:**
- No logging framework configured in application code
- `logfire` available for structured logging with OpenTelemetry export
- Standard `logging` module available via Python stdlib

**Tracing:**
- OpenTelemetry stack fully available (transitive via pydantic-ai + logfire):
  - `opentelemetry-api` - Tracing API
  - `opentelemetry-sdk` - Tracing SDK
  - `opentelemetry-exporter-otlp-proto-http` - OTLP HTTP export
  - `opentelemetry-instrumentation-httpx` - Auto-instrument HTTP calls

## CI/CD & Deployment

**Hosting:**
- Not configured

**CI Pipeline:**
- Not configured (no CI config files present)

## Environment Configuration

**Required env vars (at minimum, one LLM provider key is needed):**
- `OPENAI_API_KEY` - If using OpenAI models
- `ANTHROPIC_API_KEY` - If using Anthropic/Claude models
- `GOOGLE_API_KEY` - If using Google Gemini models
- Other provider keys as needed (see LLM Providers section above)

**Optional env vars:**
- `LOGFIRE_TOKEN` - For Pydantic Logfire observability
- `PYDANTIC_AI_MODEL` - Default model selection for pydantic-ai

**Secrets location:**
- No `.env` file present yet
- `python-dotenv` available transitively (via pydantic-settings) for `.env` file loading
- Recommend creating `.env` (and adding to `.gitignore`) for local development

## Webhooks & Callbacks

**Incoming:**
- None configured
- `starlette` is available (transitive) for serving agent UI or webhook endpoints

**Outgoing:**
- None configured

## Current Integration Status

No integrations are active in application code. `main.py` contains only a hello-world stub. All integrations listed above are available through the dependency tree (primarily via pydantic-ai's comprehensive extras) and ready to be wired up.

**Immediate setup needed before building features:**
1. Create `.gitignore` (exclude `.env`, `.venv/`, `__pycache__/`, etc.)
2. Create `.env` with at least one LLM provider API key
3. Choose primary LLM provider and configure pydantic-ai agent

---

*Integration audit: 2026-03-26*
