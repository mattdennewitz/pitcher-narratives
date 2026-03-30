# Feature Landscape: Interactive Pitcher Q&A

**Domain:** Natural language question-answering over structured baseball analytics data
**Researched:** 2026-03-30
**Confidence:** MEDIUM (research grounded in existing codebase inspection, domain knowledge of baseball analytics tooling, and web research on sports Q&A systems; no direct competitor with identical scope found)

## Context

The existing v1.3 system generates full scouting reports through a five-phase LLM pipeline. Users provide a pitcher ID and get a multi-section narrative. The v1.4 milestone adds a complementary capability: users ask a natural language question about a pitcher and get a focused analytical answer grounded in the same data pipeline.

This is NOT a chatbot. This is a single-shot Q&A tool: one question in, one answer out. The user identifies a pitcher by name (not numeric ID), asks a specific question, and gets a data-grounded response. The existing `data.py -> engine.py -> context.py` pipeline provides the analytical backbone -- the new work is question parsing, name resolution, context filtering, and a Q&A-focused analyst agent.

## Question Taxonomy

Before mapping features, it is essential to define what kinds of questions the system should handle. Based on research into sports analytics Q&A systems (SPORTSQL's primitive-based classification, the LangGraph baseball analysis agent pattern, and the existing data model's capabilities), questions about pitchers fall into six categories:

### Category 1: Pitch-Specific Inquiry
"Why is Cease's knuckle curve bad?" / "How is his slider performing?" / "What's happening with the changeup?"

These ask about a specific pitch type. The system must identify the pitch type from the question, then surface the relevant P+/S+/L+, usage, execution metrics, and movement data for that pitch. This is the most common question type for this tool.

**Data dependency:** Arsenal summary, execution metrics, platoon splits filtered to one pitch type.

### Category 2: Trend / Delta Query
"Is his fastball velocity trending up or down?" / "Has his command improved recently?"

These ask about change over time. The system already computes deltas (window vs. season) -- these questions map directly to existing engine outputs. The challenge is identifying which metric(s) the user is asking about.

**Data dependency:** Fastball summary (velo deltas), arsenal P+/S+/L+ deltas, execution metric deltas.

### Category 3: Comparative / Platoon Query
"How does he pitch differently to lefties?" / "What changes against right-handed batters?"

These ask about platoon splits. The existing platoon_mix and TTO platoon data cover this well.

**Data dependency:** Platoon mix splits, TTO platoon breakdown.

### Category 4: Role / Workload Query
"How does he hold up deep in games?" / "Is he better rested or on short rest?" / "What happens third time through?"

These ask about stamina, workload, and TTO patterns. The existing TTO analysis and workload context cover this.

**Data dependency:** TTO analysis, workload context, velocity arc.

### Category 5: Overall Assessment
"What's the scouting report on Yamamoto?" / "How is he pitching right now?"

These are broad questions that essentially request a mini-report. For these, the full context document is appropriate -- similar to the existing report pipeline but with a single-phase answer rather than five phases.

**Data dependency:** Full PitcherContext (same as report pipeline).

### Category 6: Unsupported / Out-of-Scope
"Will he get the win tonight?" / "Should I start him in fantasy?" / "How many strikeouts did he have last game?" / "Compare him to Ohtani."

These ask for predictions, fantasy advice, traditional box-score stats not in the data, or multi-pitcher comparisons. The system should recognize these gracefully and decline or redirect.

**Data dependency:** None (out of scope of the data model).

## Table Stakes

Features users expect from a Q&A interface layered on top of the existing tool. Missing any of these makes the feature feel broken or useless.

| Feature | Why Expected | Complexity | Depends On |
|---------|--------------|------------|------------|
| **Pitcher name resolution (fuzzy)** | Users will type "Cease", "cease", "Dylan Cease", "cease, dylan" -- never a numeric pitcher ID. The entire point of Q&A is removing the ID lookup friction. Must handle last-name-only (unambiguous cases), full name, and common variations. | MEDIUM | Pitcher name lookup table extracted from Statcast parquet `player_name` column; fuzzy matching logic |
| **Disambiguation prompt for ambiguous names** | "Johnson" matches multiple pitchers. The system must list matches and ask the user to clarify, not guess. Silent wrong-pitcher resolution is worse than no resolution. | LOW | Name resolution returning multiple candidates |
| **Single-phase analyst agent** | A Q&A answer does not need five pipeline phases. One agent with a Q&A-focused system prompt that receives the question + relevant context and produces a focused analytical answer. Simpler, faster, cheaper than the report pipeline. | MEDIUM | pydantic-ai Agent definition, new system prompt, PitcherContext data |
| **Data-grounded answers only** | The agent must answer from the data in the context document, not from training knowledge. If the data does not contain the answer, it must say so. This is the same principle as the existing report pipeline -- "pre-computed deltas, not LLM arithmetic." | LOW | System prompt engineering (already proven in v1.0-v1.3) |
| **CLI entry point for questions** | `pitcher-narratives ask "Why is Cease's knuckle curve bad?"` or similar. Must accept pitcher name and question in a natural way. Single-shot, not conversational. | LOW | argparse or new subcommand in cli.py |
| **Graceful handling of unanswerable questions** | If the question asks about data the system does not have (e.g., "How many strikeouts last game?"), the agent must say so rather than hallucinate. The system prompt must define what data is available. | LOW | System prompt that describes available data scope |
| **Full reuse of existing data pipeline** | The Q&A feature must load data through `data.py -> engine.py -> context.py` -- no parallel data path. This ensures consistency between reports and Q&A answers and avoids duplicate maintenance. | LOW | Existing `load_pitcher_data()` and `assemble_pitcher_context()` |

## Differentiators

Features that make the Q&A tool genuinely useful rather than just a wrapper around "dump context + question into an LLM." Not required for launch but significantly improve answer quality and user experience.

| Feature | Value Proposition | Complexity | Depends On |
|---------|-------------------|------------|------------|
| **Question-aware context filtering** | For "Why is his knuckle curve bad?", the full 2000-token context doc includes fastball data, workload data, and first-pitch tendencies that are irrelevant. Filtering the context to promote the relevant pitch type's data (arsenal row, execution row, platoon splits for that pitch, P+/S+/L+ breakdown) produces a more focused prompt and better answers. Reduces token waste and focuses the LLM. | MEDIUM | Question parsing to identify pitch type or metric focus; selective rendering of PitcherContext sections |
| **Question-type classification** | Classify the question into one of the six categories above before building the context. This enables: (1) selecting which context sections to include, (2) tailoring the system prompt for the question type, (3) gracefully declining out-of-scope questions. Can be done with simple keyword/regex heuristics -- does not need an LLM classifier. | MEDIUM | Keyword/regex patterns for pitch names, trend words, platoon indicators, broad-assessment signals |
| **Pitch type extraction from natural language** | Map "knuckle curve" to pitch_type "KC", "slider" to "SL", "four-seam" / "fastball" to "FF", "sinker" to "SI", "changeup" / "change" to "CH", "cutter" to "FC", "curveball" / "curve" to "CU", "sweeper" to "ST". This enables pitch-specific context filtering. Must handle common synonyms and informal names. | LOW | Static mapping dictionary of natural language names to Statcast pitch_type codes |
| **Answer with data citations** | The answer should reference specific numbers from the context (e.g., "His knuckle curve carries a 78 S+ this window vs. 95 on the season -- the stuff has degraded"). This grounds the answer and lets the user verify. The existing report pipeline does this via the editor prompt; the Q&A agent prompt needs the same instruction. | LOW | System prompt instruction (pattern already proven in editor prompt) |
| **Streaming output** | Stream the answer to stdout as it generates, matching the existing report UX. Users expect immediate feedback for a CLI LLM tool. | LOW | Existing streaming infrastructure in report.py, reusable for Q&A agent |
| **Multi-provider support** | Support the same `--provider openai|claude|gemini` flag as the report CLI. Already implemented in report.py -- just wire the same provider resolution. | LOW | Existing PROVIDERS dict and model resolution in report.py |

## Anti-Features

Features that seem obviously good but would harm the Q&A tool's quality, scope, or maintainability. Each is drawn from observed failure modes in sports analytics Q&A systems or LLM-powered tools.

| Anti-Feature | Why Tempting | Why Problematic | What to Do Instead |
|--------------|--------------|-----------------|-------------------|
| **Conversational / multi-turn mode** | "Users will want to ask follow-up questions." | Multi-turn conversation requires session state, message history management, context window budgeting, and a fundamentally different UX model. The existing tool is a CLI pipeline -- adding conversation turns it into a different product. Multi-turn also invites context drift where later answers reference earlier (potentially wrong) answers rather than the data. The project scope explicitly says "CLI script, not a chatbot." | Single-shot Q&A. One question, one answer. Users can run the command again with a different question. Keep it simple. |
| **SQL generation from natural language** | "Let users write arbitrary queries against the data." SPORTSQL does this well for EPL data. | The Statcast parquet has 114 columns with cryptic names (`pfx_x`, `release_speed`, `delta_run_exp`). Generating correct SQL requires the LLM to know the schema intimately. Incorrect SQL produces wrong answers silently. The existing engine.py already computes the meaningful derived metrics -- bypassing it to query raw data loses the pre-computed deltas, trend strings, and weighted baselines that make answers accurate. | Route all data access through the existing engine, which produces human-readable metrics. The LLM interprets computed results, not raw data. |
| **Fantasy advice in Q&A answers** | "Users asking about pitchers probably play fantasy baseball." | Fantasy advice is speculative and ungrounded. The existing pipeline has a dedicated fantasy analyst phase with its own prompt guardrails. Mixing fantasy speculation into Q&A answers dilutes the data-grounded analytical voice. If users want fantasy insights, they should run the full report. | Q&A answers are analytical only. No "start/sit" advice, no roster recommendations. Reference the full report pipeline for fantasy analysis. |
| **LLM-powered name resolution** | "Use the LLM to figure out which pitcher the user means." | Sending a name resolution query to the LLM is slow (~2-5s), expensive, and unreliable. The LLM might hallucinate a pitcher ID or confidently resolve an ambiguous name incorrectly. Name resolution is a lookup problem, not a reasoning problem. | Build a local name lookup table from the parquet data. Use string matching (case-insensitive substring, then Levenshtein distance for typos). Fast, deterministic, zero API cost. |
| **Comparative cross-pitcher analysis** | "Compare Cease to Yamamoto" | The existing data pipeline loads one pitcher at a time. Cross-pitcher comparison requires loading two PitcherData bundles, aligning their metrics, and giving the LLM a much larger context. This doubles the data loading time and context size, and introduces a new category of prompting challenges (fair comparison framing). Out of scope for v1.4. | Decline comparative questions gracefully: "This tool analyzes one pitcher at a time. Run separate queries for each pitcher." |
| **Historical season-over-season trends** | "How has he changed since last year?" | The data is single-season (2026 Statcast parquet + 2026 Pitching+ CSVs). There is no 2025 data to compare against. Out of scope per PROJECT.md. | Decline with explanation: "This tool covers the current 2026 season only." |
| **Question rewriting or rephrasing** | "Rephrase the user's question for better LLM understanding before answering." | An extra LLM call that adds latency and cost. The analyst agent is already capable of interpreting natural language questions directly. Question rewriting is useful when routing to SQL or a retrieval system, but here the LLM receives the raw question plus structured context -- it does not need a rewritten query. | Pass the raw question directly to the analyst agent. The system prompt provides enough framing. |

## Feature Dependencies

```
[Pitcher name resolution] ── Required: Cannot answer without knowing which pitcher
        |
        v
[Data pipeline reuse] ── load_pitcher_data(resolved_id) -> assemble_pitcher_context()
        |
        v
[Single-phase analyst agent] ── Core: question + context -> answer
        |
        ├──> [Question-type classification] ── Enhancement: informs context filtering
        |         |
        |         v
        ├──> [Question-aware context filtering] ── Enhancement: promotes relevant data
        |         |
        |         v
        |    [Pitch type extraction] ── Enables pitch-specific filtering
        |
        ├──> [Streaming output] ── UX parity with report pipeline
        |
        ├──> [Multi-provider support] ── Reuses existing PROVIDERS dict
        |
        └──> [Data citations in answers] ── Prompt engineering (no code dependency)

[CLI entry point] ── Independent: argparse subcommand or new script
        |
        └──> [Disambiguation prompt] ── Triggered by name resolution returning >1 match

[Graceful out-of-scope handling] ── Independent: system prompt defines data scope
```

### Dependency Notes

- **Name resolution is the gateway:** Nothing works without resolving a pitcher name to an ID. This must be built first and must be robust. It is the only new infrastructure the Q&A feature requires -- everything else either reuses existing code or is prompt engineering.
- **The analyst agent is the core deliverable:** A pydantic-ai Agent with a Q&A system prompt, receiving the question + PitcherContext.to_prompt() output, returning a string answer. This is structurally identical to the existing report agents but with a different prompt.
- **Context filtering is the quality lever:** Without it, the agent gets the full ~2000-token context for every question. With it, a pitch-specific question gets a ~500-token focused context. This is the difference between a good answer and a great answer, but the feature works without it.
- **Question classification enables context filtering:** You need to know "this is a pitch-specific question about the knuckle curve" before you can filter the context to knuckle curve data. But classification also has standalone value for declining out-of-scope questions.
- **The existing pipeline is not modified:** Q&A is an additive feature. `data.py`, `engine.py`, `context.py`, and `report.py` are unchanged. The new code lives in new modules (e.g., `ask.py`, `resolve.py`) plus a CLI entry point.

## MVP Recommendation

### v1.4 Launch (Interactive Q&A MVP)

The minimum feature set that makes the Q&A tool functional and useful.

1. **Pitcher name resolution** -- Build name lookup table from parquet player_name column. Case-insensitive matching on last name, full name, and "Last, First" format. Levenshtein fallback for typos. Disambiguation list when multiple pitchers match.
2. **CLI entry point** -- `pitcher-narratives ask "pitcher name" "question"` or `pitcher-narratives ask -p "Cease" -q "Why is his knuckle curve bad?"`. Support `--window`, `--provider`, `--thinking` flags from existing CLI.
3. **Single-phase analyst agent** -- pydantic-ai Agent with Q&A system prompt. Receives question + full PitcherContext.to_prompt(). Returns streaming string answer.
4. **Data-grounded system prompt** -- Instruct the agent: "Answer only from the data provided. If the data does not address the question, say so. Cite specific numbers. Do not speculate beyond what the data supports."
5. **Graceful out-of-scope handling** -- System prompt defines what data is available. Agent declines questions about predictions, fantasy, historical seasons, or data not in the context.
6. **Streaming output** -- Reuse existing streaming pattern from report.py.

### v1.4 Fast-Follow (Quality Improvements)

Add after basic Q&A is validated with real questions.

7. **Pitch type extraction** -- Map natural language pitch names to Statcast codes (static dictionary).
8. **Question-type classification** -- Regex/keyword classifier into the six categories. Use for context filtering and out-of-scope detection.
9. **Question-aware context filtering** -- For pitch-specific questions, render only the relevant arsenal/execution/platoon rows. For TTO questions, promote the TTO section. For broad questions, send full context.
10. **Multi-provider support** -- Wire existing PROVIDERS dict into Q&A CLI.

### Defer (v1.5+)

11. **Conversational mode** -- Only if strong user demand. Would require session state, message history, and a different UX paradigm.
12. **Cross-pitcher comparison** -- Requires loading multiple pitcher data bundles and new prompting strategies.
13. **Custom lookback window per question** -- "How was his slider last week?" implies a different window than the default 30 days.

## Complexity Assessment

| Feature | Est. Lines of Code | LLM Calls | Risk |
|---------|-------------------|-----------|------|
| Name resolution (table + matching) | ~80-120 (new module) | 0 | LOW -- deterministic string matching |
| CLI entry point | ~40-60 (new subcommand) | 0 | LOW -- mirrors existing CLI pattern |
| Analyst agent + system prompt | ~60-80 (new module) | 1 per question | MEDIUM -- prompt quality is testable only by running real questions |
| Streaming output | ~10 (reuse existing) | 0 | LOW -- proven pattern |
| Pitch type extraction | ~30 (static dict + lookup) | 0 | LOW -- fixed mapping |
| Question classification | ~50-70 (regex patterns) | 0 | LOW -- heuristic, not ML |
| Context filtering | ~60-100 (selective to_prompt) | 0 | MEDIUM -- need to expose per-section rendering from PitcherContext |
| **Total MVP (items 1-6)** | **~200-280 new lines** | **1 LLM call per question** | **LOW-MEDIUM overall** |

**Cost impact:** One LLM call per question (~$0.005-0.02 depending on provider and context size). Compare to the report pipeline's 5-9 LLM calls. Q&A is 5-9x cheaper per interaction.

**Latency:** Name resolution is instant (local lookup). Data loading is ~1-2s (parquet read + engine compute). LLM response is ~3-8s (streaming). Total: ~5-10s from question to first token.

## Sources

- [SPORTSQL: An Interactive System for Real-Time Sports Reasoning and Visualization](https://arxiv.org/html/2508.17157v1) -- Question primitive classification (Calculate, Compare, Filter, Order, Manipulate, Retrieve), entity resolution via SQL lookups against reference tables, multi-stage pipeline architecture. MEDIUM confidence.
- [LangGraph Baseball Data Analysis Agent](https://cognitiveclass.ai/courses/build-a-baseball-data-analysis-agent-w-langgraph) -- Pattern of routing queries to correct dataset, interpreting structured data, generating real-time insights. LOW confidence (course description only).
- [MLB AI at Bat (Google Cloud)](https://cloud.google.com/transform/mlb-statcast-ai-fan-experience-team-analytics) -- MLB's own AI assistant for Statcast data, surfacing stats through natural language. LOW confidence (marketing page, architecture not detailed).
- [Statcast MCP Server](https://glama.ai/mcp/servers/alex-rimerman/statcast-mcp) -- MCP server translating natural language to Statcast queries, demonstrating the demand for conversational access to baseball data. LOW confidence (third-party tool).
- [UX Patterns for CLI Tools](https://lucasfcosta.com/2022/06/01/ux-patterns-cli-tools.html) -- Interactive vs. non-interactive CLI patterns; guided setup with defaults. MEDIUM confidence.
- [Fuzzy Name Matching Best Practices](https://dataladder.com/fuzzy-matching-101/) -- Jaro-Winkler for names, layered matching approach, contextual filtering. MEDIUM confidence.
- Direct inspection of existing codebase: `data.py`, `engine.py`, `context.py`, `report.py`, `cli.py` -- HIGH confidence on data model, available metrics, and pipeline reusability.

---
*Feature research for: Interactive Pitcher Q&A (v1.4 milestone)*
*Researched: 2026-03-30*
