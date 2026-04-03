# Phase 20: Season-Delta Engine - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Engine produces a cross-season summary with year-over-year deltas for pitcher-level metrics so downstream context assembly (Phase 22) can render them in the LLM prompt. Covers velocity, P+, S+, L+, and basic workload comparison (innings pitched, pitch count averages, appearances).

</domain>

<decisions>
## Implementation Decisions

### Cross-Season Summary Design
- Output type is a frozen dataclass (matches PitcherData, WorkloadContext patterns in engine.py)
- Computation lives in engine.py alongside existing delta logic — reuses existing threshold constants and delta string functions
- Per-pitch-type YoY deltas deferred to Phase 21 (Arsenal Trend Engine) — this phase covers pitcher-level only
- Workload profile included at basic level: YoY deltas for innings pitched, pitch count averages, and appearance count

### Delta Language
- YoY delta strings MUST reuse the same qualitative functions already in engine.py: `_velo_delta_string`, `_pplus_delta_string` (SDLT-02)
- Same thresholds: _VELO_THRESHOLD=0.5, _PPLUS_THRESHOLD=5, _SHARP_VELO_THRESHOLD=2.0, _SHARP_PPLUS_THRESHOLD=10
- Format stays consistent: "Up sharply", "Down modestly", "Steady" with numeric values in parentheses

### None Behavior
- Cross-season summary is None (not empty dataclass, not zeroes) when prior-season data is missing (SDLT-03)
- Caller checks `if summary is not None` before rendering

### Claude's Discretion
- Exact dataclass field naming
- Whether to compute workload deltas from season_baseline or from raw statcast aggregations
- Helper function organization within engine.py

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_velo_delta_string(delta, threshold)` in engine.py — qualitative velocity delta formatting
- `_pplus_delta_string(delta, threshold)` in engine.py — qualitative P+/S+/L+ delta formatting
- Threshold constants: `_VELO_THRESHOLD`, `_PPLUS_THRESHOLD`, `_SHARP_VELO_THRESHOLD`, `_SHARP_PPLUS_THRESHOLD`
- `PitcherData.prior_season_baseline` and `PitcherData.prior_pitch_type_baseline` (from Phase 19) — source of prior-season data

### Established Patterns
- Frozen dataclasses for computed outputs (WorkloadContext, PitcherData)
- Delta computation: window_value - baseline_value, passed through qualitative string function
- n_pitches-weighted averaging for baselines

### Integration Points
- Input: `PitcherData` with `season_baseline` (current) and `prior_season_baseline` (prior) fields
- Output: consumed by Phase 22 (Context Assembly) as a field on PitcherContext
- Engine functions called from context.py during context assembly

</code_context>

<specifics>
## Specific Ideas

- Workload comparison metrics: innings_pitched, pitch_count (mean per appearance), appearance_count
- These can be derived from season_baseline which already contains per-season aggregations
- For workload deltas, use simple numeric differences (no existing qualitative function needed — "X more innings", "Y fewer appearances")

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
