# Phase 12: Component Attribution - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Decompose each pitch type's xRV into 13 additive outcome-level contributions, showing which outcomes (whiffs, HRs, ground outs, etc.) drive the overall score. Each contribution is computed as (outcome_probability x run_value_for_count). The 13 contributions must sum to xRV within floating-point tolerance. Available at both pitcher+type (season) and pitcher+type+appearance grains.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key codebase observations:
- Phase 11 just added IntermediateProbabilities dataclass with P/S variants for xSwing, xWhiff, xGOr, xPUr, xHR100, xSwSt, xRV100
- The 13 outcomes and their run values come from the pitchingplus model — need to identify what columns represent which outcomes
- engine.py pattern: dataclass + compute function using _weighted_window_metrics
- xRV100 is the total run value score — components should sum to this
- The pitchingplus model computes xRV from intermediate probabilities multiplied by count-specific run values

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `engine.py:IntermediateProbabilities` — Phase 11 output with P/S variants per pitch type
- `engine.py:_weighted_window_metrics()` — extracts weighted metrics from CSV windows
- `engine.py:compute_intermediate_probabilities()` — per-pitch-type intermediate extraction
- `data.py:PitcherData.agg_csvs` — all 8 CSVs already loaded with all columns

### Established Patterns
- Dataclasses for structured engine output
- _XMETRICS tuple pattern for column grouping
- Window vs season baseline computation
- _build_name_map for pitch type naming

### Integration Points
- Phase 11's IntermediateProbabilities — contains the probability values needed
- data.agg_csvs["pitcher_type"] and ["pitcher_type_appearance"] — source grains
- Phase 13 will consume attribution data through analyst tools

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. The 13 outcomes and their run values need to be identified from the pitchingplus model internals at ~/src/pitchingplus/packages/plus.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
