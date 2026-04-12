# Phase 3: Execution & Context Engine - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Build execution metrics computation, workload context tracking, and the PitcherContext Pydantic model that assembles ALL engine outputs into a single prompt-ready markdown document under 2,000 tokens. This is the complete schema the LLM receives in Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Execution Metrics
- Add execution metrics to engine.py — keeps all computation in one module
- CSW%: count called_strike + swinging_strike descriptions in Statcast, divide by total pitches per type in window
- Zone rate: pitches in zone 1-9 / total; Chase rate (O-Swing%): swings on pitches outside zone / pitches outside zone — uses Statcast `zone` and `description` columns
- xRV100 ranking: percentile rank against all pitchers in 2026-pitcher_type.csv (per pitch type, min 10 pitches) for league distribution; team.csv provides league-average reference

### Workload & Context
- Rest days: days between consecutive game_dates in appearance data
- Innings pitched: count unique (game_pk, inning) pairs + partial innings from outs recorded in Statcast
- Consecutive days pitched flag: 3+ consecutive days triggers reliever workload concern
- Pitch count per appearance: count rows in Statcast per (pitcher, game_pk)

### PitcherContext Assembly
- New `context.py` module — Pydantic model separate from polars computation in engine.py
- `to_prompt()` renders as markdown with headers, bullet points, and small tables
- Token budget: truncate lower-usage pitch types (keep top 4), abbreviate where possible, test with ~4 chars/token heuristic
- PitcherContext assembles ALL engine outputs (fastball, arsenal, execution, workload) into one prompt-ready document

### Claude's Discretion
- Exact Pydantic field names and nesting structure
- Markdown formatting details in to_prompt()
- How to handle missing data gracefully in the prompt (e.g., no platoon data available)
- Ordering of sections in the rendered prompt

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py` — PitcherData with statcast, appearances, window_appearances, season_baseline, pitch_type_baseline, agg_csvs
- `engine.py` — FastballSummary, VelocityArc, PitchTypeSummary, PlatoonMix, FirstPitchWeaponry dataclasses + compute functions
- Delta string helpers in engine.py: _velo_delta_string, _pplus_delta_string, _movement_delta_string, _usage_delta_string
- 60 tests passing across test_data.py and test_engine.py

### Established Patterns
- Dataclass-based return types from engine functions
- TDD with real data (pitcher 592155 / Booser)
- Delta strings as pre-computed qualitative text
- Small sample flags (< 10 pitches)

### Integration Points
- engine.py functions consume PitcherData fields directly
- Statcast columns for execution: description (pitch result), zone (1-9 = in zone), type (S/B/X)
- CSV columns for xRV100: xRV100_P in pitcher_type_appearance and team CSVs
- context.py will import from both data.py and engine.py

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
