# Phase 22: Context Assembly & Prompt Rendering - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Infrastructure phase (autonomous smart discuss)

<domain>
## Phase Boundary

Integrate cross-season insights into PitcherContext and the LLM prompt. Wire CrossSeasonSummary (Phase 20) and ArsenalTrends (Phase 21) through context assembly into rendered prompt sections and specialist pipeline agents. Single-season pitchers get no cross-season section.

</domain>

<decisions>
## Implementation Decisions

### Context assembly wiring
- `assemble_pitcher_context()` in context.py must call `compute_cross_season_summary()` and `compute_arsenal_trends()` and populate the existing stub fields on PitcherContext
- Replace `cross_season_summary: Any | None = None` with typed `CrossSeasonSummary | None` (same for `arsenal_trend` → `ArsenalTrends | None`)

### Prompt rendering
- `to_prompt()` renders a "Year-over-Year" section with top-level deltas (velocity, P+, S+, L+) and arsenal changes (added/dropped/continued)
- Section is omitted entirely for single-season pitchers — no empty headers, no "N/A" placeholders (per CPMT-02)

### Pipeline integration
- Specialist pipeline agents (stuff, trends, game shape) receive cross-season data in their context blocks (per CPMT-03)
- pipeline.py already has conditional guards checking `ctx.cross_season_summary is not None` and `ctx.arsenal_trend is not None` — these will fire once the stubs are populated
- **CRITICAL:** pipeline.py uses `at.added_pitches`, `at.dropped_pitches`, `at.pitch_trends` but ArsenalTrends has `added`, `dropped`, `continued`. These references must be updated to match the actual dataclass attributes.

### Dead code cleanup
- `_render_yoy_section()` is referenced in pipeline.py but never defined — Phase 22 must either implement it on PitcherContext or replace the reference
- `_render_appearance_pitch_trends_section()` is also referenced but undefined — implement or remove
- `appearance_pitch_trends: Any | None = None` stub on PitcherContext — this is out of v1.8 scope (no appearance-level trends computed); remove or leave as None

### Claude's Discretion
- Exact format/layout of the YoY prompt section
- How to render added/dropped/continued pitch details (table vs prose vs structured list)
- Whether to keep `appearance_pitch_trends` stub or remove it

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Context layer (to modify)
- `src/pitcher_narratives/context.py` — PitcherContext stubs (lines ~82-85), assemble_pitcher_context() (~line 580), _render_temporal_section() as pattern reference

### Pipeline layer (to modify)
- `src/pitcher_narratives/pipeline.py` — Conditional guards at ~lines 551-725 that inject YoY data into specialist prompts; references to `at.added_pitches` etc. that need updating

### Engine outputs (inputs to this phase)
- `src/pitcher_narratives/engine.py` — CrossSeasonSummary, compute_cross_season_summary, ArsenalTrends, ArsenalPitchTrend, compute_arsenal_trends

### Requirements
- `.planning/REQUIREMENTS.md` — CPMT-01, CPMT-02, CPMT-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_render_temporal_section()` in context.py — pattern for rendering optional sections that omit when data is None
- Pipeline guard pattern: `if ctx.cross_season_summary is not None:` — already in place, just needs stubs populated

### Established Patterns
- PitcherContext fields typed with `| None` and populated conditionally in `assemble_pitcher_context()`
- `to_prompt()` builds sections as strings, skips None fields
- Specialist pipeline builds data_sections list, appends only when data exists

### Integration Points
- `assemble_pitcher_context()` is the single assembly point — all new calls go here
- `to_prompt()` renders all sections — new YoY section goes here
- Pipeline specialist prompts in pipeline.py — inject cross-season data blocks

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- `appearance_pitch_trends` (micro-trends across recent outings) — not computed in v1.8, defer to future milestone

</deferred>

---

*Phase: 22-context-assembly-prompt-rendering*
*Context gathered: 2026-04-08 via autonomous smart discuss*
