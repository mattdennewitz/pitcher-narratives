# Phase 21: Arsenal Trend Engine - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Engine identifies pitches added, dropped, or significantly changed year-over-year and computes per-pitch-type YoY deltas. Produces an arsenal trend dataclass consumed by Phase 22 context assembly.

</domain>

<decisions>
## Implementation Decisions

### Arsenal Trend Detection
- Minimum-pitch threshold for added/dropped: reuse existing `_MIN_PITCHES = 10` constant (consistency with per-type analysis)
- A pitch type is "added" if present in current season with ≥ _MIN_PITCHES but absent or below threshold in prior season
- A pitch type is "dropped" if present in prior season with ≥ _MIN_PITCHES but absent or below threshold in current season
- "Changed" means present in both seasons with ≥ _MIN_PITCHES each

### Output Structure
- Dataclass with lists of added/dropped pitch type names, plus a list of per-pitch-type change records
- Each change record: pitch_type, usage_delta_str, pplus_delta_str, splus_delta_str, velo_delta_str
- Matches CrossSeasonSummary pattern from Phase 20

### Delta Language
- Reuse `_pplus_delta_string` for P+/S+ deltas (same thresholds as within-season)
- Reuse `_usage_delta_string` for usage rate deltas
- Reuse `_velo_delta_string` for velocity deltas
- Consistent with SDLT-02 language decision from Phase 20

### None Behavior
- Arsenal trend output is None when pitcher has only one season of data (ATRN-03)
- Returns None when `prior_pitch_type_baseline.is_empty()`

### Claude's Discretion
- Exact dataclass and field naming
- Helper function organization
- Whether to include raw numeric deltas alongside qualitative strings

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_MIN_PITCHES = 10` in engine.py — pitch count threshold for per-type analysis
- `_velo_delta_string`, `_pplus_delta_string`, `_usage_delta_string` — qualitative delta formatters
- `_safe_metric(df, col)` — safe column extraction from DataFrames
- `PitcherData.pitch_type_baseline` (current) and `PitcherData.prior_pitch_type_baseline` (prior) from Phase 19

### Established Patterns
- Frozen dataclasses for computed outputs
- Delta computation: current - prior, passed through qualitative string function
- Per-pitch-type analysis via pitch_type_baseline DataFrames grouped by pitch_type column

### Integration Points
- Input: `PitcherData` with current and prior pitch type baselines
- Output: consumed by Phase 22 (Context Assembly) as a field on PitcherContext
- Parallel to CrossSeasonSummary (Phase 20) — both fed into context layer

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond what's in the ROADMAP and REQUIREMENTS.md.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
