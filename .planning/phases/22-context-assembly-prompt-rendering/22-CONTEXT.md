# Phase 22: Context Assembly & Prompt Rendering - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire cross-season outputs from Phases 20-21 into PitcherContext and to_prompt() so the LLM receives year-over-year changes in its prompt. Also route cross-season data to the 3 relevant specialist pipeline agents.

</domain>

<decisions>
## Implementation Decisions

### PitcherContext Model
- Add optional `cross_season_summary: CrossSeasonSummary | None` field (from Phase 20)
- Add optional `arsenal_trend: ArsenalTrend | None` field (from Phase 21)
- Both are None for single-season pitchers

### to_prompt() Rendering
- Section heading: "## Year-over-Year Changes"
- Position: after existing sections (fastball, arsenal, execution), before workload context
- Renders top-level deltas (velocity, P+, S+, L+, workload) from cross_season_summary
- Renders arsenal changes (added, dropped, changed pitches) from arsenal_trend
- Omit the section entirely for single-season pitchers (no empty headers, no "N/A" placeholders)

### Specialist Pipeline Context
- 3 specialists receive cross-season data per CPMT-03: stuff, trends, game_shape
- Stuff specialist: gets cross-season velocity/P+/S+ deltas + arsenal changes (pitch adds/drops)
- Trends specialist: gets full cross-season summary + arsenal trends (everything)
- Game Shape specialist: gets workload comparison + arsenal usage shifts
- Location and Run Value specialists: no cross-season data (not relevant to their lens)

### Claude's Discretion
- Exact markdown formatting within the YoY section
- How to abbreviate arsenal changes to stay within token budget
- Whether to include raw numbers or only qualitative strings in prompt

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PitcherContext` in context.py — Pydantic BaseModel with `to_prompt()` method
- `CrossSeasonSummary` from Phase 20 — pitcher-level YoY deltas
- `ArsenalTrend` from Phase 21 — added/dropped/changed pitch types
- `compute_cross_season_summary()` and `compute_arsenal_trends()` from engine.py

### Established Patterns
- PitcherContext fields use `| None = None` for optional data
- to_prompt() builds sections list, skips sections when data is None
- Pipeline context blocks built in pipeline.py per-specialist

### Integration Points
- context.py: PitcherContext model + to_prompt()
- pipeline.py: specialist context block assembly
- Engine functions called from context assembly code

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond what's in the ROADMAP and REQUIREMENTS.md.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
