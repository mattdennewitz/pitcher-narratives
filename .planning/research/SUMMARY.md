# Research Summary: v1.4 Interactive Pitcher Q&A

**Domain:** Conversational Q&A agent integration into existing MLB scouting CLI
**Researched:** 2026-03-30
**Overall confidence:** HIGH

## Executive Summary

The v1.4 milestone adds an interactive Q&A capability to the existing pitcher narratives tool. Users ask natural-language questions about pitchers by name (not by ID) and receive grounded analytical responses. The core architectural insight: the existing data pipeline (`data.py` -> `engine.py` -> `context.py`) already produces exactly the right context for Q&A consumption. The full `PitcherContext.to_prompt()` output is only ~544 tokens -- small enough to send in its entirety with every question. This means no tools, no multi-turn agent loops, and no modifications to the existing pipeline.

Three new modules are needed, cleanly separated by concern: `resolver.py` handles fuzzy name-to-ID resolution using `rapidfuzz` against the existing pitcher CSV registry (~1,651 pitchers), `analyst.py` defines a single-call Q&A agent with a grounded analyst system prompt, and `ask_cli.py` provides the CLI entry point following the project's established pattern of one script per concern (`pitcher-ask` alongside `pitcher-narratives` and `pitcher-scout`). Zero existing modules are modified.

**Research disagreement resolved:** The STACK.md research recommends a tool-calling agent with `@agent.tool` decorators. The ARCHITECTURE.md research recommends pre-assembled context (single LLM call) instead. The architecture recommendation wins because the context is only 544 tokens -- tools add latency and complexity for no benefit at this scale. STACK.md's other recommendations (rapidfuzz, separate CLI, `instructions` over `system_prompt`) are adopted.

The build order follows dependency chains: name resolution first (zero LLM dependencies, pure Python), then the analyst agent (depends on existing PitcherContext), then the CLI wiring. An optional fourth phase for question-aware context filtering is deferred -- the context is small enough that the LLM handles it without section reordering.

## Key Findings

**Stack:** Add `rapidfuzz` for name resolution. No other new dependencies. Existing pydantic-ai agent patterns cover the Q&A agent. Single LLM call with pre-assembled context, not tool-calling.
**Architecture:** Three new modules (`resolver.py`, `analyst.py`, `ask_cli.py`), zero modifications to existing code. Pre-assembled context (544 tokens) over tools.
**Critical pitfall:** The LLM must be explicitly constrained to answer only from provided data. Without strong grounding instructions, the model will hallucinate pitcher stats from training data instead of citing the context.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Phase: Name Resolution** - Build `resolver.py` with fuzzy matching
   - Addresses: Pitcher name input, fuzzy matching, error handling for ambiguous/missing names
   - Avoids: Coupling name resolution to LLM (keeps it deterministic and fast)
   - Pure Python, no LLM -- lowest risk, highest testability

2. **Phase: Q&A Analyst Agent** - Build `analyst.py` with grounded system prompt
   - Addresses: Single-call Q&A, grounded-in-data answers, analyst voice
   - Avoids: Over-engineering with multi-phase pipeline or tool-based approach
   - Depends on: existing PitcherContext (not on Phase 1 of this milestone)

3. **Phase: CLI Wiring** - Build `ask_cli.py`, update pyproject.toml
   - Addresses: User-facing entry point, error handling, streaming output
   - Avoids: Breaking existing CLI interfaces by adding subcommands
   - Depends on: Phases 1 and 2

4. **(Optional) Phase: Context Filtering** - Question-aware context promotion
   - Addresses: Edge cases where agent misses relevant pitch-type data
   - Build only if testing reveals quality gaps

**Phase ordering rationale:**
- Name resolution is a prerequisite for the CLI (user provides names, not IDs)
- The analyst agent can be developed in parallel with name resolution since it only depends on PitcherContext
- CLI wiring is last because it composes both previous components
- Context filtering is deferred pending evidence of need

**Research flags for phases:**
- Phase 1 (Name Resolution): Standard patterns, unlikely to need further research
- Phase 2 (Analyst Agent): System prompt design is the main risk -- may need iteration during testing to tune grounding strength, answer length, and voice
- Phase 3 (CLI Wiring): Standard patterns, follows existing precedent exactly
- Phase 4 (Context Filtering): Needs phase-specific research only if triggered

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | rapidfuzz is the standard tool, pydantic-ai patterns are well-established in the codebase, only disagreement (tools vs context) resolved with measured evidence |
| Features | HIGH | Feature set is well-defined in PROJECT.md, clear scope boundaries, question taxonomy mapped in FEATURES.md |
| Architecture | HIGH | Decisions driven by concrete evidence (544-token context size, existing CLI patterns, 1,651 pitcher index). Disagreement with STACK.md documented and resolved. |
| Pitfalls | MEDIUM | Grounding/hallucination risk is real but mitigatable via prompt engineering. System prompt quality is the main empirical unknown. |

## Gaps to Address

- System prompt content for the analyst agent needs iteration during implementation (grounding strength, answer length guidance, voice calibration)
- Whether `rapidfuzz` should be a hard dependency or optional with `difflib` fallback -- recommendation is hard dependency (MIT license, no concerns)
- Caching strategy for repeated questions about the same pitcher (load data once, ask multiple questions) is out of scope for v1.4 but a natural v1.5 improvement
- The tools vs pre-assembled context decision should be revisited if PitcherContext grows significantly in future milestones

## Sources

- [Pydantic AI - Function Tools](https://ai.pydantic.dev/tools/)
- [Pydantic AI - Agents](https://ai.pydantic.dev/agent/)
- [Pydantic AI - Dependencies](https://ai.pydantic.dev/dependencies/)
- [RapidFuzz documentation](https://rapidfuzz.github.io/RapidFuzz/)
- [RapidFuzz GitHub](https://github.com/rapidfuzz/RapidFuzz)
- Existing codebase: all modules in `src/pitcher_narratives/` (HIGH confidence)
- `.planning/research/STACK.md`, `FEATURES.md` (v1.4 research, reconciled in this document)

---
*Research completed: 2026-03-30*
*Ready for roadmap: yes*
