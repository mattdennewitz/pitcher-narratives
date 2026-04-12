# Phase 2: Fastball & Arsenal Engine - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the computation engine that transforms loaded pitcher data into pre-computed fastball quality analysis and arsenal breakdowns with deltas and qualitative trend strings. Produces structured dicts/dataclasses ready for LLM consumption — not DataFrames, not raw numbers. Everything the LLM needs to write about fastball quality and arsenal usage.

</domain>

<decisions>
## Implementation Decisions

### Module Structure & Fastball Identification
- New `engine.py` module — separates computation from data loading; imports PitcherData from data.py
- Primary fastball identified as highest-usage fastball type (FF, SI, FC) from pitcher_type season baseline
- Fastball pitch types: FF (Four-Seam), SI (Sinker), FC (Cutter) — standard Statcast classification
- Engine functions return plain dicts/dataclasses with string fields — qualitative trend strings ready for LLM, not DataFrames

### Delta Computation & Trend Strings
- Notable velocity change threshold: 0.5 mph (below is noise in Statcast data)
- Notable usage rate change threshold: 5 percentage points
- Qualitative delta vocabulary: directional + magnitude — "Up 1.2 mph", "Down sharply (-3.1)", "Steady (+0.2)"
- Within-game velocity arc: compare avg velo in first 2 innings vs last 2 innings of the appearance

### Platoon & First-Pitch Analysis
- Platoon mix shifts: compare pitch type usage % vs RHB and vs LHB from platoon appearance data, delta vs season platoon baseline
- First pitch: pitch_number == 1 in Statcast data (first pitch of each at-bat)
- First-pitch weaponry changes: compare % of first pitches that are each pitch type in recent window vs season
- Minimum pitch count for per-pitch-type analysis: 10 pitches of that type in window; below this flag "small sample" but still include

### Claude's Discretion
- Internal function signatures and helper naming
- Exact dataclass field names for engine output
- How to handle pitchers with only 1 pitch type (no arsenal analysis needed)
- Ordering of pitch types in output (by usage? alphabetical?)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py` — PitcherData dataclass with: statcast (pitch-level), appearances (game-level with role), window_appearances, season_baseline, pitch_type_baseline, agg_csvs (all 8 grains), pitcher_id, pitcher_name, throws
- `PitcherData.agg_csvs` keys: "pitcher", "pitcher_type", "pitcher_type_platoon", "team", "pitcher_appearance", "pitcher_type_appearance", "pitcher_type_platoon_appearance", "all_pitches"
- Season baselines use n_pitches-weighted averaging across game_type rows
- Window filtering uses max date in dataset, not date.today()

### Established Patterns
- polars DataFrames throughout data layer
- Google-style docstrings, type hints, __all__ for public APIs
- Tests in tests/ directory using pytest with real data files

### Integration Points
- `data.load_pitcher_data(pitcher_id, window_days)` returns PitcherData — engine.py consumes this
- Statcast columns needed: release_speed, pfx_x, pfx_z, pitch_type, inning, pitch_number, stand, game_pk, game_date
- P+ CSV columns: P+, S+, L+, xRV100_P/S, xWhiff_P/S, xSwing_P/S, pitch_type, n_pitches, platoon_matchup

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
