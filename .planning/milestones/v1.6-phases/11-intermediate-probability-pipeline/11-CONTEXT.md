# Phase 11: Intermediate Probability Pipeline - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Load and surface per-pitch-type intermediate probabilities (both P and S variants) from pitchingplus aggregation CSVs so downstream tools can expose them. The columns already exist in the CSVs — this phase makes them accessible as structured data at both season and appearance grains.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key codebase observations informing implementation:
- Columns already present in CSVs: xSwing_P/S, xWhiff_P/S, xGOr_P/S, xPUr_P/S, xHR100_P/S, xSwSt_P/S, xRV100_P/S
- BBE_prob_P/S columns do NOT exist in current data files — handle as "missing column" case
- engine.py already uses xWhiff_P, xSwing_P, xRV100_P via _XMETRICS tuple
- data.py loads all CSV columns implicitly via pl.read_csv (no column filtering)
- Weighted baseline computation in data.py already averages all non-ID columns

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py:load_agg_csvs()` — loads all 8 CSVs filtered to pitcher; already includes all columns
- `data.py:compute_pitch_type_baseline()` — weighted average per pitch type across game_types
- `engine.py:_XMETRICS` tuple — existing pattern for grouping related columns
- `engine.py:_compute_xmetrics_for_type()` — extracts xWhiff_P, xSwing_P, xRV100_P from window rows

### Established Patterns
- Dataclasses for structured engine output (FastballSummary, PitchTypeSummary, ExecutionMetrics)
- Weighted n_pitches averaging for baseline computation
- `_ID_COLS` frozenset to separate identifiers from metrics
- Window vs season baseline pattern throughout engine

### Integration Points
- `PitcherData.agg_csvs["pitcher_type"]` — season grain
- `PitcherData.agg_csvs["pitcher_type_appearance"]` — appearance grain
- `PitcherData.pitch_type_baseline` — already has weighted intermediate columns
- Phase 13 will consume whatever structured types this phase creates

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
