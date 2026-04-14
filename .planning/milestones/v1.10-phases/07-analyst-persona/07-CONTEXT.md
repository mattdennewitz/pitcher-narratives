# Phase 07: Analyst Persona - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

An ANALYST persona exists with a newsletter voice targeting analytically-inclined fans, inheriting factual discipline from scout, with teaching vocabulary permissions and a per-persona hallucination-guard allowlist.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — voice characteristics fully specified in REQUIREMENTS.md (VOICE-02, PERSONA-10 analyst portion). Use ROADMAP success criteria and existing personas.py patterns to guide decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `personas.py` — Persona frozen dataclass with `parent` field for overlay inheritance, `SCOUT` constant, `build_writer_system_prompt()` composer
- `pipeline.py` — persona-aware pipeline (Phase 06), `check_hallucinated_metrics()` function for per-persona allowlist
- `tests/test_personas.py` — 18 existing tests, pattern for adding persona smoke tests

### Established Patterns
- Persona overlay is a string constant concatenated with SHARED_WRITER_BASE via `build_writer_system_prompt()`
- `parent` field enables overlay inheritance (scout factual-discipline rules inherited by analyst)
- `PERSONAS` dict registry with `get_persona()` lookup
- TestModel-based pipeline smoke tests for end-to-end persona verification

### Integration Points
- `personas.py` — add ANALYST constant, update PERSONAS registry
- `pipeline.py:check_hallucinated_metrics()` — add per-persona allowlist for analyst vocabulary
- `tests/test_personas.py` — add analyst smoke test, shape assertion

</code_context>

<specifics>
## Specific Ideas

No specific requirements — voice fully specified in REQUIREMENTS.md VOICE-02.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
