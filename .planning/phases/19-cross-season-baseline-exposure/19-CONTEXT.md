# Phase 19: Cross-Season Baseline Exposure - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Make prior-season baselines available to engine computations. PitcherData gets new fields for prior-season data (both season-level and pitch-type-level) so downstream phases (20-22) can compute YoY deltas and arsenal trends without touching data.py.

</domain>

<decisions>
## Implementation Decisions

### Prior season scope
- **D-01:** "Prior season" means the immediate preceding season only (e.g., 2025 when current is 2026)
- **D-02:** Do not aggregate or include all non-current seasons — strictly N-1

### Baseline field structure
- **D-03:** Add both `prior_season_baseline` and `prior_pitch_type_baseline` fields to PitcherData in this phase
- **D-04:** Both use the same pattern as current baselines — split the existing `season_baseline_all` / `pitch_type_baseline_all` into current (max season) + prior (max season - 1)

### Single-season behavior
- **D-05:** When a pitcher has only one season of data, prior baselines are empty DataFrames (not None, not crash) — per XSBL-03
- **D-06:** Existing engine functions that consume `season_baseline` and `pitch_type_baseline` must continue working unchanged — no regression

### Dead scaffolding
- **D-07:** Do NOT clean up the broken `compute_cross_season_summary()` / `CrossSeasonSummary` / `_per_season_velo()` scaffolding in engine.py — that belongs to Phase 20 (Season-Delta Engine)
- **D-08:** Phase 19 only exposes data; Phase 20 owns the computation that consumes it

### Claude's Discretion
- Exact implementation of the season splitting logic in `load_pitcher_data()`
- Whether to use a helper function or inline the split
- Empty DataFrame construction approach (schema-preserving vs plain empty)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Data layer
- `src/pitcher_narratives/data.py` — PitcherData dataclass (line ~70), load_pitcher_data() (line ~395), baseline filtering (lines ~419-430), compute_season_baseline() (line ~310), compute_pitch_type_baseline() (line ~345)

### Engine scaffolding (read-only context, do not modify)
- `src/pitcher_narratives/engine.py` — CrossSeasonSummary (line ~1032), compute_cross_season_summary() (line ~2196) — shows the interface Phase 20 expects from `data.prior_season_baseline`

### Requirements
- `.planning/REQUIREMENTS.md` — XSBL-01, XSBL-02, XSBL-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compute_season_baseline()` and `compute_pitch_type_baseline()` already group by `[pitcher, season]` — they produce multi-season output naturally
- `load_pitcher_data()` already computes `season_baseline_all` and `pitch_type_baseline_all` with all years, then filters to max season — the all-years data is computed but discarded
- `_YEARS = [2025, 2026]` centralizes year configuration

### Established Patterns
- Baselines are Polars DataFrames with a `season` column for year identification
- `filter_game_type()` applied at load time excludes spring training / exhibition data
- Multi-year loading uses `pl.concat(frames, how="diagonal_relaxed")` for schema tolerance

### Integration Points
- `load_pitcher_data()` is the single function that constructs PitcherData — all baseline changes go here
- `PitcherData` dataclass is consumed by every engine function — new fields must not break existing consumers
- `compute_cross_season_summary()` in engine.py already expects `data.prior_season_baseline` — this is the target interface

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 19-cross-season-baseline-exposure*
*Context gathered: 2026-04-08*
