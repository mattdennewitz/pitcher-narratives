# Technology Stack — v1.10 Output Personas

**Project:** Pitcher Narratives
**Researched:** 2026-04-11
**Mode:** Scoped ecosystem research (subsequent milestone, not greenfield)
**Overall confidence:** HIGH

## TL;DR

**Recommendation:** No new libraries. Use plain Python string composition at module import time (`BASE + "\n\n" + OVERLAY`), store persona configs as frozen dataclasses in a new `src/pitcher_narratives/personas.py` module, and construct **one writer `Agent` per persona** inside `make_pipeline_agents()`. Pass the selected writer agent through the pipeline; leave the revision loop's call site unchanged.

Do **not** use:
- jinja2 / chevron / handlebars — no runtime variable substitution is needed; overlays are static text with zero placeholders.
- TOML config files — three personas, all developer-authored, ship as code; TOML adds a file + loader for no win.
- `Agent.override(instructions=...)` context manager — it's a replacement, not a layering primitive, and it discards capability-contributed instructions.
- Per-run `agent.run(instructions=...)` layering on a shared agent — technically works, but forces switching the base from `system_prompt=` to `instructions=`, and the resolved text is still concatenated into one system string before it hits any provider, so it buys nothing over three pre-built agents.
- A single shared writer `Agent` called with persona chosen at runtime — no caching benefit, extra branching in the hot path.

## Recommended Stack (deltas from v1.9)

### New Files (no new dependencies)

| File | Purpose | Content |
|------|---------|---------|
| `src/pitcher_narratives/personas.py` | Persona registry + prompt composition | `PersonaKey` Literal, `PersonaConfig` frozen dataclass, three module-level constants (`SCOUT`, `ANALYST`, `GENERIC`), `PERSONAS` dict, `build_writer_prompt(key) -> str` helper |

### Modified Files

| File | Change |
|------|--------|
| `pipeline.py` | Move `_WRITER_PROMPT` → `personas.BASE_WRITER_PROMPT`; `make_pipeline_agents` gains a `persona: PersonaKey = "scout"` kwarg and builds one writer agent with `system_prompt=build_writer_prompt(persona)`; `PipelineAgents.writer` stays singular |
| `cli.py` | Add `--persona {scout,analyst,generic}` argparse flag, default `"scout"`, pass through to `generate_report()` |
| `anchor.py` | No change for the persona mechanism itself. A tolerance pass for the `generic` persona's summary-table format is a separate problem (see PITFALLS.md) and belongs to `ANCHOR_PROMPT` text, not to the stack |

### Unchanged

- `pydantic-ai 1.72.0` — supports everything we need with the API we already use
- `pydantic 2.12.5` — frozen dataclass is fine; no need to promote to BaseModel
- `polars`, `rapidfuzz`, `logfire`, `python-dotenv` — irrelevant to this milestone
- `pyproject.toml` dependencies — **no additions, no removals**

## Direct Answers to the Five Questions

### 1. Does pydantic-ai 1.72 have built-in prompt composition / layering / overrides?

**Yes, three mechanisms exist. None of them are better than plain string concatenation for our case.**

Direct evidence from the installed source:

**a) Per-run `instructions=` on `run()` / `run_sync()` / `run_stream()`**
`pydantic_ai/agent/abstract.py:178` (and again at 200, 221) — every `run*` overload accepts:
```python
instructions: _instructions.AgentInstructions[AgentDepsT] = None
```
These are **additive**, not replacement. From `pydantic_ai/agent/__init__.py:2280-2293` (`_get_instructions`):
```python
instructions = self._instructions.copy()
instructions.extend(cap_instructions if ... else self._cap_instructions)
if additional_instructions is not None:
    instructions.extend(_instructions.normalize_instructions(additional_instructions))
```
So per-run instructions append to the agent's init-time instructions, then get joined with `\n`.

**b) `Agent.override(instructions=...)` context manager**
`pydantic_ai/agent/__init__.py:1614-1732`. This **replaces** the agent's instructions entirely for the duration of the `with` block, including capability-contributed instructions (the docstring explicitly calls this out at line 1638-1640). It's designed for testing, not production layering.

**c) `@agent.instructions` decorator for dynamic instruction functions**
`pydantic_ai/agent/__init__.py:1735-1793`. Lets you register a `Callable[[RunContext], str]` that runs on each request. Useful when overlays depend on `deps`, but our personas are pure static text — this is overkill.

**d) `TemplateStr` (Handlebars)**
`pydantic_ai/_template.py:16-89`. Backed by `pydantic-handlebars` 0.1.0, already installed transitively. Allows `{{deps.name}}` interpolation inside instructions. **Not relevant** — our overlays have zero placeholders.

**Why none of these beat plain strings for v1.10:**

The current code uses `system_prompt=_WRITER_PROMPT` on the writer Agent. Whether we switch to `instructions=` or stick with `system_prompt=`, the eventual bytes sent to the provider are the same: one combined system string. From `pydantic_ai/models/anthropic.py:775-1002`:
```python
system_prompt_parts: list[str] = []
for m in messages:
    ... system_prompt_parts.append(request_part.content)   # from system_prompt=
if instructions := self._get_instructions(messages, ...):  # from instructions=
    system_prompt_parts.append(instructions)
system_prompt = '\n\n'.join(system_prompt_parts)
```
Per-run `instructions=` layering would give us one writer Agent instead of three, but it would require changing the base from `system_prompt=` to `instructions=` (no structural benefit), and complicates the anchor revision loop which currently just hands `writer_agent` around as an opaque callable.

**Confidence:** HIGH. Direct source read of pydantic-ai 1.72.0.

### 2. Is there a lightweight templating library worth pulling in?

**No.** Our overlays are fixed literal strings with zero variable substitution. Evaluated options:

| Library | Version | What it buys | Needed? | Integration cost |
|---------|---------|--------------|---------|------------------|
| jinja2 | 3.1.x | Full templating, conditionals, loops | **No** — zero placeholders in the overlays | 1 dep, 1 loader module, runtime compile cost |
| `string.Template` (stdlib) | n/a | `$name` substitution | **No** — nothing to substitute | Zero |
| f-strings / plain concat | n/a | String concatenation | **Yes, this** | Zero |
| chevron / mustache | n/a | Logic-less templates | **No** | 1 dep |
| pydantic-ai `TemplateStr` | 0.1.0 | Handlebars over `RunContext.deps` | **No** — already in the tree but no deps model to template over | Zero new deps, but adds a TemplateStr instantiation per agent and an opaque compile step |

The overlay text for each persona is fully known at import time. `BASE_WRITER_PROMPT + "\n\n" + overlay_text` is the entire mechanism. If a future persona needs variable text (e.g., `{pitcher_name}` injected into the system prompt), revisit — `str.format` or `TemplateStr` would both work, and `TemplateStr` is already in the tree via `pydantic-handlebars 0.1.0` at `.venv/lib/python3.14/site-packages/pydantic_handlebars/`.

**Confidence:** HIGH.

### 3. Where should persona definitions live — Python constants, TOML, dataclass, pydantic model?

**Frozen `@dataclass` module-level constants in `src/pitcher_narratives/personas.py`.** Not TOML, not pydantic BaseModel.

Reasoning:

- **Not TOML.** `tomllib` is stdlib in 3.14, so loading is free, but three developer-authored personas shipped as code do not benefit from file-based config. It would add: a `personas.toml` file, a `_load_personas()` function with error handling, test fixtures for malformed TOML, an import-time vs runtime question, and a new surface area for "why doesn't my persona work." User-configurable personas are explicitly out of scope for v1.10.
- **Not pydantic BaseModel.** Overkill for a record with two string fields (`key`, `overlay`) plus maybe a length hint or voice tag. Validation is a no-op because these values are authored in-repo. BaseModel also makes it unnecessarily easy for a future contributor to load personas from JSON/YAML/etc. when we've deliberately decided not to.
- **Frozen dataclass is the sweet spot.** Gives us typed fields, immutability (matches the "data is static, keys are closed Literal" model), and zero runtime cost. The `Literal["scout", "analyst", "generic"]` persona key plays nicely with ty/pyright exhaustiveness checks in argparse dispatch.

Reference shape:
```python
# src/pitcher_narratives/personas.py
from dataclasses import dataclass
from typing import Literal

PersonaKey = Literal["scout", "analyst", "generic"]

BASE_WRITER_PROMPT = """..."""  # the shared base (current _WRITER_PROMPT, minus scout-specific voice)

@dataclass(frozen=True, slots=True)
class PersonaConfig:
    key: PersonaKey
    overlay: str

SCOUT = PersonaConfig(key="scout", overlay="""...""")
ANALYST = PersonaConfig(key="analyst", overlay="""...""")
GENERIC = PersonaConfig(key="generic", overlay="""...""")

PERSONAS: dict[PersonaKey, PersonaConfig] = {
    "scout": SCOUT, "analyst": ANALYST, "generic": GENERIC,
}

def build_writer_prompt(key: PersonaKey) -> str:
    return f"{BASE_WRITER_PROMPT}\n\n{PERSONAS[key].overlay}"
```

What the pydantic-ai community typically does: its own examples in `examples/` and the docs consistently use Python constants / literal strings for system prompts (see the `Agent(..., system_prompt="...")` shape repeated across `_WRITER_PROMPT`, `_EXECUTIVE_SUMMARY_PROMPT`, `_STUFF_SPECIALIST_PROMPT` in our own `pipeline.py`, which mirrors the framework's own patterns). Dynamic personas via `@agent.instructions` are shown in the API reference but not used in any of the framework's own examples for the static case.

**Confidence:** HIGH.

### 4. Should `make_pipeline_agents()` build one writer agent per persona, or one agent that takes persona at call time?

**One writer Agent per persona, selected at construction time, not runtime.**

The cleanest change: `make_pipeline_agents()` takes a new `persona: PersonaKey = "scout"` kwarg. It builds a single writer Agent with `system_prompt=build_writer_prompt(persona)`. `PipelineAgents.writer` remains a single `Agent[None, str]` field. The anchor revision loop in `_run_anchor_revision_loop` (pipeline.py:1209-1276) receives `writer_agent` as before — it never has to know which persona was selected.

Why this over a shared agent + per-run `instructions=`:

1. **Revision loop is already a closure over `writer_agent`.** The loop calls `writer_agent.run(...)` twice (initial capsule + per-revision). If the agent holds the composed persona prompt, the loop does not change at all. If we used per-run `instructions=`, every one of those call sites would need to thread the overlay text through — three new parameters for zero behavioral gain.
2. **`system_prompt` vs `instructions` byte-equality.** As noted in #1, the eventual system string sent to the provider is identical either way. There is no caching, token, or latency difference.
3. **Model-level debugging.** Logfire spans (we already `logfire.instrument_pydantic_ai()` in `config.py:122-123`) surface the system prompt on the first request. Having three distinct agents means spans are cleanly labeled per persona and per-persona evals are trivial to add later.
4. **Constructor cost is negligible.** `Agent(..., defer_model_check=True)` is a dict assignment — three of them at pipeline start is free. We already construct ~10 agents per pipeline invocation (see `make_pipeline_agents` at pipeline.py:1112-1162).
5. **Matches existing code shape.** Every agent in `make_pipeline_agents` is built with a fixed system prompt. The persona selection fits the existing pattern exactly: pass a different prompt literal to `_writer()`. No new pattern to learn, no new mental model.

Why not `Agent.override(instructions=...)`:

- `override` is a context manager intended for testing. Its docstring (pydantic_ai/agent/__init__.py:1627-1632) literally says so.
- It **replaces** all agent-level instructions, including any capability-contributed ones, rather than appending.
- Wrapping every `writer_agent.run()` call inside `with writer_agent.override(...)` is strictly worse than holding a preconfigured agent.

**Confidence:** HIGH. The pipeline architecture already treats agents as immutable per-pipeline configurations.

### 5. Prompt-cache interactions with persona overlays on each provider

The persona overlay goes into the **system prompt**. The specialists' user-message `CachePoint`s (which are the milestone's main caching investment) are untouched. Provider-by-provider:

#### Anthropic (Claude)

**Risk level:** MEDIUM — real, but the current code already has this problem in a latent form.

How pydantic-ai sends the system string (verified directly in `pydantic_ai/models/anthropic.py:775-1036`):
1. It collects every `SystemPromptPart` from messages and every `instructions` string resolved via `_get_instructions`, concatenates them with `\n\n`, and sends them as Anthropic's `system` field.
2. A `cache_control` breakpoint is added to the last system block **only if** `anthropic_cache_instructions=True` is set on `AnthropicModelSettings`.
3. CachePoint markers in user messages add breakpoints via `_add_cache_control_to_last_param` (anthropic.py:785, 1121-1149).
4. Anthropic allows at most 4 cache points per request; pydantic-ai enforces this in `_limit_cache_points` (anthropic.py:1039-1105).

**Current state (v1.9):** Our code does NOT set `anthropic_cache_instructions` anywhere (grep confirms: zero hits in `src/pitcher_narratives/`). The writer's `_WRITER_PROMPT` is therefore NOT cached at the system level today. All caching is on specialist *user* messages via `CachePoint`. The revision loop also sends a brand-new user message on each pass, so the writer system prompt is re-read every time.

**v1.10 impact:** Swapping persona changes the system text, so if we were to turn on `anthropic_cache_instructions`, each persona would have its own cache lineage. With three personas and a 5-minute TTL, that would still amortize nicely across a batch of reports with the same persona. Cross-persona invalidation is a non-issue because the three caches are simply independent — Anthropic matches on an exact prefix of the combined system string (base+overlay), so `scout` hits a different entry than `analyst` but each is internally stable.

**Anchor revision loop caveat:** Anchor + writer revisions already pay a full re-encode cost of the writer's system prompt on every pass (because `anthropic_cache_instructions` is off). Adding a persona overlay does not make that worse. If we ever turn caching on for instructions, we'd want to make sure the overlay sits inside the cached block (not after it), which it does by construction — `f"{BASE}\n\n{OVERLAY}"` is a fixed string per agent.

**Recommendation for v1.10:** Leave `anthropic_cache_instructions` unset (match current behavior; do not conflate persona work with a caching optimization). File a follow-up if we want to measure the cost.

**Confidence:** HIGH for the pydantic-ai wiring; MEDIUM for Anthropic's prefix-matching semantics (training-data, not re-verified this session because WebFetch/WebSearch are denied in this environment).

#### OpenAI (gpt-5.4 / gpt-5.4-mini)

**Risk level:** LOW.

Direct evidence: `pydantic_ai/models/openai.py:1322-1324`:
```python
elif isinstance(item, CachePoint):
    # OpenAI doesn't support prompt caching via CachePoint, so we filter it out
    return None
```

OpenAI does implicit prompt caching on Chat Completions / Responses based on stable prompt prefixes — no explicit markers, no settings, no cache_control field. The persona overlay extends the system prompt suffix, so different personas are three distinct caching lineages, each amortizing across its own reruns.

Because OpenAI caching is implicit, there is nothing to configure or break in pydantic-ai. Each persona will cache independently once a baseline threshold of reruns is hit.

**Confidence:** HIGH for the pydantic-ai behavior (it filters `CachePoint` as a no-op). MEDIUM for OpenAI's internal cache mechanics (training-data knowledge; not re-verified this session).

#### Google (Gemini 3.1 Pro)

**Risk level:** LOW.

Direct evidence: `pydantic_ai/models/google.py:917-921`:
```python
elif isinstance(item, CachePoint):
    # Google doesn't support inline CachePoint markers. Google's caching requires
    # pre-creating cache objects via the API, then referencing them by name using
    # `GoogleModelSettings.google_cached_content`. See https://ai.google.dev/gemini-api/docs/caching
    pass
```

The pipeline does not use `google_cached_content` anywhere. Gemini prompt caching is effectively off for this application and has been throughout v1.6–v1.9. Persona swaps therefore change nothing about caching on the Gemini path.

**Confidence:** HIGH. Direct source read.

### Summary: caching interaction

| Provider | Cache mechanism in use | Impact of persona overlay |
|----------|------------------------|---------------------------|
| Anthropic | User-message `CachePoint` only; system prompt not cached | **None** — system string differs per persona but isn't cached anyway |
| OpenAI | Implicit prefix caching (provider-side) | Each persona caches as an independent prefix; no overlap, but no regression either |
| Google | No caching in use (`google_cached_content` unset) | None |

The headline worry — "Claude cache_control on a stable base plus per-persona suffix invalidates the base" — **does not apply** because we don't currently cache the writer's system prompt on Claude. And even if we turn that on later, `cache_control` is exact-prefix anyway: each persona gets its own cached base+overlay block, which is exactly what we want.

## Library Checklist (for planner)

| Library | Version | Buys us | Need? | Integration cost |
|---------|---------|---------|-------|------------------|
| jinja2 | 3.1.x | Template engine with loops/conditionals | No | — |
| chevron | 0.14.x | Mustache templates | No | — |
| pydantic-handlebars | 0.1.0 (already installed) | Handlebars via `TemplateStr` | No | — |
| `string.Template` (stdlib) | n/a | `$var` substitution | No | — |
| tomllib (stdlib) | n/a | Parse TOML configs | No | — |
| **none** | — | Plain f-string concat + frozen dataclass | **Yes** | Zero |

## Concrete Recommendation for Phase 1 + Phase 2

**Phase 1 (new `personas.py` module):**
- Zero new dependencies
- ~80 lines total: `PersonaKey` Literal, `PersonaConfig` frozen dataclass, `BASE_WRITER_PROMPT` constant (derived from current `_WRITER_PROMPT` with scout-specific voice extracted), three persona constants, a `PERSONAS` dict, one helper function `build_writer_prompt(key: PersonaKey) -> str`
- Unit tests: persona key exhaustiveness (Literal), scout overlay produces byte-identical output to current `_WRITER_PROMPT` (regression safety net for the no-regression constraint), base prompt contains no voice-specific language

**Phase 2 (pipeline.py integration):**
- Delete `_WRITER_PROMPT` from pipeline.py
- Import `PersonaKey, build_writer_prompt` from `.personas`
- `make_pipeline_agents` signature gains `persona: PersonaKey = "scout"` (default preserves behavior)
- `_writer(build_writer_prompt(persona))` replaces `_writer(_WRITER_PROMPT)` at pipeline.py:1153
- `_run_pipeline` and its CLI entry point gain a `persona` kwarg threaded through to `make_pipeline_agents`
- Anchor revision loop: **no changes** — `writer_agent` is already whatever it is
- `cli.py` gains `--persona` argparse flag

Byte-equality regression check: a snapshot test that asserts `build_writer_prompt("scout") == <the old _WRITER_PROMPT text>` enforces the constraint that scout callers see zero regression.

## Sources

- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/agent/__init__.py` — Agent class `__init__`, `override`, `instructions`, `_get_instructions` (HIGH)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/agent/abstract.py` — `run()` / `run_sync()` / `run_stream()` signatures with per-call `instructions` parameter (HIGH)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/_instructions.py` — `normalize_instructions` (HIGH)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/_template.py` — `TemplateStr` and pydantic-handlebars backing (HIGH)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/models/anthropic.py` — system prompt assembly, `anthropic_cache_instructions`, `CachePoint` handling, `_limit_cache_points` (HIGH)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/models/openai.py:1322-1324` — `CachePoint` is a no-op on OpenAI (HIGH)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/models/google.py:917-921` — `CachePoint` is a no-op on Google; caching requires `google_cached_content` (HIGH)
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai_slim-1.72.0.dist-info/METADATA` — version pin confirmation (HIGH)
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/pipeline.py` — current `_WRITER_PROMPT`, `make_pipeline_agents`, `_run_anchor_revision_loop`, `build_writer_input` (HIGH)
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/config.py` — current agent settings and provider map (HIGH)
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/anchor.py` — `build_revision_message` showing user-message CachePoint pattern (HIGH)
- Anthropic / OpenAI provider cache semantics — training-data only this session (WebFetch/WebSearch denied); MEDIUM confidence. Flagged where used.
