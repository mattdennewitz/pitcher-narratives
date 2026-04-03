# Phase 19: Cross-Season Baseline Exposure - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Engine functions can access both current-season and prior-season baselines for any pitcher. PitcherData exposes prior-season baseline DataFrames so downstream phases (20-22) can compute cross-season deltas and trends.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from prior decisions:
- v1.7 established per-season baseline grouping (not cross-season averaged)
- v1.7 load_pitcher_data() currently filters baselines to max season — this phase removes that filter
- All data access must go through data.py (centralization decision from v1.7)

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria:
1. PitcherData contains both current-season and prior-season baseline DataFrames when multi-year data exists
2. When a pitcher has only one season of data, prior-season baselines are empty (not None, not crash)
3. Existing engine functions continue to work unchanged (no regression in single-season behavior)

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
