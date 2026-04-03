# Phase 14: Analyst Prompt Rewrite - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Rewrite the analyst agent's system prompt so it reasons from model internals — diagnosing pitch quality through outcome probabilities and component attribution rather than citing opaque plus grades. Plus scores (P+/S+/L+) are still referenced as summary grades, but the explanation focuses on what drives them.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key context:
- Phase 13 added intermediates and attribution data to both tools' output
- The system prompt in analyst.py currently instructs the analyst to use plus scores
- The rewrite should instruct the analyst to:
  1. Explain *why* using intermediate probabilities (e.g., "38% whiff rate vs 25% league avg")
  2. Diagnose location impact via P vs S comparison
  3. Identify dominant run-value drivers from component attribution
  4. Still reference plus scores as summary grades

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `analyst.py` system prompt — currently references P+/S+/L+ scores
- `_build_summary_context()` now includes intermediates section
- `_build_pitch_detail()` now includes attribution table and intermediates

### Established Patterns
- System prompt is a string constant or defined inline in agent factory
- Instructions guide the LLM on how to interpret and present data

### Integration Points
- This is the final phase — no downstream consumers
- The prompt changes affect how the analyst agent responds to user questions

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
