# Phase 06: Pipeline Integration & Scout Parity Gate - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The pipeline is persona-aware -- `make_pipeline_agents` accepts a persona argument, the old `_WRITER_PROMPT` constant is deleted from pipeline.py, and scout behavior is byte-identical to v1.9 through the full pipeline path.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `personas.py` module (Phase 05) — provides `build_writer_system_prompt()`, `get_persona()`, `DEFAULT_PERSONA`, `SCOUT`
- `_WRITER_PROMPT` constant at `pipeline.py:408` — to be deleted and replaced with persona-based construction
- `_writer()` helper in pipeline.py — constructs the writer agent, currently takes prompt string
- `make_pipeline_agents()` at pipeline.py — factory function that builds all pipeline agents

### Established Patterns
- `make_pipeline_agents(provider, thinking)` is the current signature — persona param added as optional with DEFAULT_PERSONA default
- `generate_pipeline_streaming()` and `_run_pipeline()` are the entry points that need persona string parameter
- `analyst.py:618` has a positional call to `make_pipeline_agents` that must not break

### Integration Points
- `pipeline.py` — sole module being modified (delete `_WRITER_PROMPT`, wire `build_writer_system_prompt(persona)`)
- `tests/test_signals.py` — imports `_WRITER_PROMPT` from pipeline; needs update to import from personas
- `tests/fixtures/writer_prompt_scout.txt` — the byte-identity fixture from Phase 05
- `analyst.py:618` — positional call that must continue working with new default arg

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
