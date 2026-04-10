# Phase 21: Arsenal Trend Engine - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Infrastructure phase (autonomous smart discuss)

<domain>
## Phase Boundary

Compute year-over-year deltas per pitch type: identify pitches added (present in current season, absent in prior) and dropped (present in prior, absent in current), plus per-pitch-type YoY deltas for usage rate, P+, S+, and velocity. Produces an ArsenalTrend type consumed by Phase 22 (Context Assembly).

</domain>

<decisions>
## Implementation Decisions

### ArsenalTrend type design
- Create an ArsenalTrend dataclass (or similar) to hold: added pitches, dropped pitches, and per-pitch-type YoY deltas
- Use a minimum-pitch threshold to distinguish "dropped" from "barely thrown" (per ATRN-01)
- Follow the same pattern as CrossSeasonSummary: function returns ArsenalTrend | None

### Data source
- Use `PitcherData.pitch_type_baseline` (current season) and `PitcherData.prior_pitch_type_baseline` (prior season) from Phase 19
- These contain per-pitcher, per-season, per-pitch-type rows with P+, S+, L+, n_pitches, and velocity metrics

### None behavior (ATRN-03)
- Arsenal trend output is None when pitcher has only one season of data — same pattern as CrossSeasonSummary

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Data layer (Phase 19 output)
- `src/pitcher_narratives/data.py` — PitcherData with `prior_pitch_type_baseline` field

### Engine layer (Phase 20 pattern)
- `src/pitcher_narratives/engine.py` — CrossSeasonSummary and compute_cross_season_summary() as the reference pattern for ArsenalTrend

### Context stubs (Phase 22 will consume)
- `src/pitcher_narratives/context.py` — PitcherContext.arsenal_trend stub (line ~83)

### Pipeline guards (Phase 22 will activate)
- `src/pitcher_narratives/pipeline.py` — Conditional blocks checking ctx.arsenal_trend (lines ~552, ~668)

### Requirements
- `.planning/REQUIREMENTS.md` — ATRN-01, ATRN-02, ATRN-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compute_pitch_type_baseline()` groups by [pitcher, season, pitch_type] — produces the per-pitch-type rows
- `_safe_metric()` extracts metrics safely from baseline DataFrames
- `_pplus_delta_string()` for qualitative delta language
- `_velo_delta_string()` for velocity delta language

### Established Patterns
- Engine functions: `compute_X(data: PitcherData) -> X | None`
- Public exports in `__all__`
- TDD approach from Phases 19-20

### Integration Points
- `PitcherData.pitch_type_baseline` and `PitcherData.prior_pitch_type_baseline` are inputs
- `PitcherContext.arsenal_trend` is the downstream consumer (Phase 22)
- Pipeline guards in pipeline.py already check for `ctx.arsenal_trend` — Phase 22 just needs to populate it

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-arsenal-trend-engine*
*Context gathered: 2026-04-08 via autonomous smart discuss*
