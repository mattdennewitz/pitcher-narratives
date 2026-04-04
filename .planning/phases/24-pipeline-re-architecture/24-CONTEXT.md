# Phase 24: Pipeline Re-Architecture - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

The 5-specialist pipeline expands to 6 agents with an Approach Specialist handling platoon/count analysis, dynamic RP routing that skips Game Shape for relievers, and raw data appendices for grounding. No prompt heuristic changes (that's Phase 25). No new engine computation (Phase 23 complete).

</domain>

<decisions>
## Implementation Decisions

### Approach Specialist Design
- **D-01:** Strategy-first framing. Prompt leads with the pitcher's approach pattern ("attacks righties with sinker, hides sweeper when ahead") then cites the data. Reads like a scout describing how the pitcher thinks, not a data dump.
- **D-02:** Cross-reference platoon and count-state data. Prompt explicitly instructs: "When a pitcher throws more X vs lefties AND more X when behind, connect these — it reveals situational strategy." This is the analytical value-add over having separate data streams.
- **D-03:** Adaptive output length with anti-padding directive. Prompt: "Match your output length to the density of the data. If the pitcher shows complex, highly variable strategies, use up to 3 paragraphs. If the pitcher's approach is uniform and straightforward, summarize it in 1 paragraph. Under no circumstances should you pad the response with filler or repeat data points to increase length."
- **D-04:** Notable shifts only (10+ pp) as input, NOT full appendix tables. Must include baseline overall pitch mix alongside the shifts so the specialist can weight significance — a 12pp shift on a 40% pitch is the headline; on a 5% pitch it's a footnote.

### RP Game Shape Replacement
- **D-05:** Workload-only stub for relievers. A short pre-formatted block with appearance frequency, pitch count trends, and rest days — deterministic data from PitcherContext, no LLM call. Writer gets real workload signal without TTO noise.
- **D-06:** Conditional writer prompt for RP context. Use conditional logic in prompt compilation: "You are synthesizing a scouting report for a {Role}. {If Role == Reliever: do not fabricate TTO analysis; the workload section replaces Game Shape.}" Single writer prompt with role-aware insertion, not two separate prompts.

### Raw Data Appendix
- **D-07:** Stuff Specialist gets a per-pitch delta table: pitch type, window/season velo, velo delta, window/season pfx_x/pfx_z, movement deltas, S+/P+ window and season. All numbers the specialist references, in one grounding table.
- **D-08:** Stuff prompt includes anti-recalculation directive: "Refer specifically to the data in the Per-Pitch Delta Table when discussing movement or velocity changes. Do not attempt to recalculate these numbers."
- **D-09:** Raw data appendix labeled as ground truth with citation requirement: "Raw Data (cite these exact numbers)." Prompt directive: "When referencing metrics, use the exact values from the Raw Data section."
- **D-10:** Trend Specialist gets a timeline-oriented appendix — per-appearance snapshots for the last 5-7 appearances, primary pitches only (>10% usage). This forces genuine temporal narratives ("ramping up", "fading", "plateauing") instead of restating static deltas. Differentiates Trend from Stuff output.
- **D-11:** Timeline data cap: 5-7 most recent appearances. Filter to primary pitches (>10% usage) to prevent token overload. The existing 30-day window parameter naturally handles IL stint returns — post-return data only.

### Auditor Expansion
- **D-12:** Same 7 existing audit categories PLUS 2 domain-specific checks for Approach Specialist: (1) platoon claim matches actual vs-LHB/vs-RHB data, (2) count-state claim matches actual bucket data.
- **D-13:** Domain-specific audit checks use chain-of-thought "show your work" format: (1) state the claim from the text, (2) cite the exact numbers from the data table, (3) Boolean Pass/Fail. This step-by-step extraction improves auditor accuracy.
- **D-14:** Auditor receives both input data and output for the Approach Specialist (same pattern as existing specialists). Enables cross-checking claims against source data.

### Claude's Discretion
- Exact Approach Specialist system prompt wording (beyond the framing and directives captured above)
- Per-appearance timeline table column selection for Trend Specialist
- Workload stub formatting details (column layout, which fields beyond appearance frequency, pitch count, rest days)
- How the conditional RP writer prompt is structured syntactically

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — PIPE-01 through PIPE-07 define the seven deliverables for this phase

### Pipeline Architecture
- `src/pitcher_narratives/pipeline.py` §80-147 — `_STUFF_SPECIALIST_PROMPT` (existing specialist prompt pattern)
- `src/pitcher_narratives/pipeline.py` §271-312 — `_DATA_AUDITOR_PROMPT` (7 audit categories to extend)
- `src/pitcher_narratives/pipeline.py` §339-396 — `_WRITER_PROMPT` (needs RP conditional insertion)
- `src/pitcher_narratives/pipeline.py` §445-525 — `_build_stuff_input()` (raw data appendix attaches here)
- `src/pitcher_narratives/pipeline.py` §528-562 — `_build_location_input()` (platoon data removal target)
- `src/pitcher_narratives/pipeline.py` §583-601 — `_build_trend_input()` (timeline appendix attaches here)
- `src/pitcher_narratives/pipeline.py` §604-650 — `_build_game_shape_input()` (RP skip + stub target)
- `src/pitcher_narratives/pipeline.py` §653-673 — `build_writer_input()` (6th specialist output wiring)
- `src/pitcher_narratives/pipeline.py` §717-801 — Auditor validation (6th audit wiring)
- `src/pitcher_narratives/pipeline.py` §980-1017 — `run_specialists()` (parallel dispatch, add 6th agent)

### Context Data (Phase 23 outputs)
- `src/pitcher_narratives/context.py` §72-73 — `platoon_mix`, `first_pitch` fields on PitcherContext
- `src/pitcher_narratives/context.py` §93 — `count_splits` field on PitcherContext
- `src/pitcher_narratives/context.py` §532 — `_render_platoon_section()` (platoon data rendering)
- `src/pitcher_narratives/context.py` §547 — `_render_count_splits_section()` (notable shifts rendering)
- `src/pitcher_narratives/context.py` §598 — `_render_first_pitch_section()` (first pitch data rendering)

### Engine Data Models
- `src/pitcher_narratives/engine.py` — `CountSplits`, `CountBucket`, `PlatoonMix`, `FirstPitchWeaponry` dataclasses
- `src/pitcher_narratives/engine.py` — `PitchTypeSummary` (source for per-pitch delta table fields)

### Prior Phase Context
- `.planning/phases/23-engine-foundation-data-enrichment/23-CONTEXT.md` — D-11 (10pp threshold), D-13 (count splits adjacent to platoon)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_specialists()` at pipeline.py:980 — parallel `asyncio.gather()` dispatch pattern. Add 6th agent here.
- `_build_*_input()` functions — consistent pattern for each specialist. New `_build_approach_input()` follows same structure.
- `_DATA_AUDITOR_PROMPT` — 7-category audit template. Extend with 2 domain-specific categories.
- `_render_*_section()` methods on PitcherContext — can be called directly to build specialist inputs (Trend already does this).

### Established Patterns
- **Agent definition**: `Agent[None, str]` with system prompt, model name, temperature
- **Input builders**: Functions that take `PitcherContext` and return formatted markdown string
- **Auditor**: Per-specialist parallel audits via `asyncio.gather()`, with revision loop on failure
- **Writer**: Concatenates all specialist outputs as markdown sections
- **Temperature convention**: Specialists=0.3, Writer=0.7, Auditor=0.1

### Integration Points
- `run_specialists()` — add 6th agent and its input builder
- `build_writer_input()` — include 6th specialist output section
- Auditor dispatch — add 6th audit with domain-specific categories
- `_build_location_input()` — verify no platoon data leaks (may already be clean)
- `_build_game_shape_input()` — add `ctx.role == "RP"` guard

</code_context>

<specifics>
## Specific Ideas

- Anti-padding directive for Approach Specialist: "Under no circumstances should you pad the response with filler or repeat data points to increase length."
- Anti-recalculation directive for Stuff appendix: "Do not attempt to recalculate these numbers."
- Chain-of-thought auditor format: claim → data citation → Pass/Fail
- Conditional writer prompt uses string interpolation, not separate prompts: `{If Role == Reliever: ...}`
- Trend timeline capped at 5-7 appearances, primary pitches only (>10% usage)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 24-pipeline-re-architecture*
*Context gathered: 2026-04-04*
