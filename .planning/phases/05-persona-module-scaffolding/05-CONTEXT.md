# Phase 05: Persona Module Scaffolding - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

A new `personas.py` module exists with the Persona dataclass, SHARED_WRITER_BASE, SCOUT overlay, registry, and composer -- and the composed scout prompt is byte-identical to the v1.9 writer prompt.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_WRITER_PROMPT` constant at `pipeline.py:408` — the v1.9 writer prompt to be decomposed into SHARED_WRITER_BASE + SCOUT overlay
- `pipeline.py:1153` — `make_pipeline_agents()` currently hardcodes `_writer(_WRITER_PROMPT)` as the writer agent constructor

### Established Patterns
- Frozen dataclasses used for immutable config (per REQUIREMENTS: `Persona` is a frozen dataclass)
- Module-level constants (e.g., `_WRITER_PROMPT`, `MAX_REVISIONS`) for configuration
- `src/pitcher_narratives/` package layout with per-concern modules (config.py, anchor.py, data.py, etc.)

### Integration Points
- `pipeline.py` — sole consumer of the writer prompt; Phase 06 will wire `build_writer_system_prompt(persona)` here
- `tests/test_signals.py` — references `_WRITER_PROMPT` import; Phase 06 will need to update these references
- `tests/fixtures/writer_prompt_scout.txt` — frozen fixture to be created for byte-identity gate

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
