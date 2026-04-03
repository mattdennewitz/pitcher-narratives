# Phase 13: Tool Interface Updates - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Update the analyst agent's tools (`get_pitcher_summary` and `get_pitch_detail`) to return intermediate probabilities with P/S comparisons and component attribution alongside existing plus scores. New data is additive — existing tool output must be preserved.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key context:
- Phase 11 added IntermediateProbabilities dataclass (P/S variants for all metrics)
- Phase 12 added ComponentAttribution dataclass (13-outcome xRV decomposition)
- Both are wired into PitcherContext.intermediates and PitcherContext.attributions
- analyst.py has get_pitcher_summary and get_pitch_detail tools that format PitcherContext data as markdown
- P vs S delta = P_value minus S_value (location impact)
- Existing tool output must not change — new sections are additive

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `analyst.py:_build_summary_context()` — builds markdown for get_pitcher_summary
- `analyst.py:_build_pitch_detail()` — builds markdown for get_pitch_detail
- `context.py:PitcherContext.intermediates` — list[IntermediateProbabilities]
- `context.py:PitcherContext.attributions` — list[ComponentAttribution]

### Established Patterns
- Tools return markdown strings formatted for LLM consumption
- Data grouped by pitch type with sections for Arsenal, Execution, Platoon

### Integration Points
- analyst.py tools consume PitcherContext via QADeps dependency injection
- Phase 14 will rewrite the system prompt to reason from this new data

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
