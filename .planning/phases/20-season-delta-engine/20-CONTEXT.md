# Phase 20: Season-Delta Engine - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Infrastructure phase (autonomous smart discuss)

<domain>
## Phase Boundary

Compute year-over-year deltas for pitcher-level metrics (velocity, P+, S+, L+) comparing current season baseline to prior season baseline. Produces a CrossSeasonSummary dataclass consumed by Phase 22 (Context Assembly).

</domain>

<decisions>
## Implementation Decisions

### Scaffolding ownership (from Phase 19 D-07/D-08)
- Phase 20 owns the broken `compute_cross_season_summary()` scaffolding in engine.py — fix it, wire it, export it
- Fix the undefined `_per_season_velo()` helper referenced at engine.py:2231
- Add `CrossSeasonSummary` and `compute_cross_season_summary` to engine.py `__all__`
- The existing `CrossSeasonSummary` dataclass (engine.py:1032) and `compute_cross_season_summary()` (engine.py:2196) are the starting point — fix and complete, don't rewrite from scratch

### Delta string consistency (SDLT-02)
- YoY delta strings must use the same qualitative thresholds and language as within-season deltas (Steady / Up modestly / Down sharply / etc.)
- Reuse existing delta-string functions where they exist

### None behavior (SDLT-03)
- Cross-season summary is None when prior-season data is missing — no fabricated comparisons
- The existing guard at engine.py:2213 (`if data.prior_season_baseline.is_empty(): return None`) is the correct pattern

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Data layer (Phase 19 output)
- `src/pitcher_narratives/data.py` — PitcherData with `prior_season_baseline` and `prior_pitch_type_baseline` fields (Phase 19 delivered)

### Engine scaffolding (to fix)
- `src/pitcher_narratives/engine.py` — CrossSeasonSummary (line ~1032), compute_cross_season_summary() (line ~2196), _per_season_velo() (undefined, needs creation)

### Context stubs (Phase 22 will consume)
- `src/pitcher_narratives/context.py` — PitcherContext.cross_season_summary stub (line ~82)

### Requirements
- `.planning/REQUIREMENTS.md` — SDLT-01, SDLT-02, SDLT-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CrossSeasonSummary` dataclass already defined with correct fields
- `compute_cross_season_summary()` already implemented with correct structure — just needs `_per_season_velo()` and export
- Existing delta-string functions (`_velo_delta_string`, `_pplus_delta_string`) for reuse
- `_safe_metric()` helper handles None/missing values in baselines

### Established Patterns
- Engine functions follow `compute_X(data: PitcherData) -> X | None` pattern
- Delta strings use qualitative language thresholds
- All public engine functions listed in `__all__`

### Integration Points
- `PitcherData.prior_season_baseline` and `PitcherData.season_baseline` are the inputs (Phase 19 delivered)
- `PitcherContext.cross_season_summary` is the downstream consumer (Phase 22 will wire)
- `assemble_pitcher_context()` in context.py will need to call this (Phase 22 scope)

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

*Phase: 20-season-delta-engine*
*Context gathered: 2026-04-08 via autonomous smart discuss*
