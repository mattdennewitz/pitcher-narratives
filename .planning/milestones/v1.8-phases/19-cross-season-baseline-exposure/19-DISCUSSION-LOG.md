# Phase 19: Cross-Season Baseline Exposure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-08
**Phase:** 19-cross-season-baseline-exposure
**Areas discussed:** Prior season scope, Dead scaffolding cleanup, Pitch-type baseline handling

---

## Prior Season Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate prior only | prior_season_baseline contains only the single preceding season (e.g., 2025 when current is 2026). Matches existing scaffolding. | ✓ |
| All non-current seasons | prior_season_baseline contains all seasons except current max. Future-proofs for 3+ years. | |
| You decide | Claude picks based on scaffolding and requirements. | |

**User's choice:** Immediate prior only (Recommended)
**Notes:** Aligns with compute_cross_season_summary() which does exactly a 2-season comparison.

---

## Dead Scaffolding Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Leave for Phase 20 | Phase 19 exposes baselines. Scaffolding (compute_cross_season_summary, _per_season_velo, __all__) belongs to Phase 20. Clean separation of concerns. | ✓ |
| Clean up in Phase 19 | Fix broken code now to avoid crash risk. Adds scope. | |
| Delete the scaffolding | Remove broken code. Phase 20 rewrites fresh. | |

**User's choice:** Leave for Phase 20 (Recommended)
**Notes:** Clean boundary — Phase 19 exposes data, Phase 20 owns computation.

---

## Pitch-type Baseline Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Both now | Expose both prior_season_baseline AND prior_pitch_type_baseline. Same pattern, keeps data.py changes in one phase. | ✓ |
| Season-level only | Only prior_season_baseline in Phase 19. Phase 21 adds pitch-type when needed. | |
| You decide | Claude picks based on cross-phase coupling. | |

**User's choice:** Both now (Recommended)
**Notes:** Both use the same split pattern. Keeps all baseline exposure in one phase.

---

## Claude's Discretion

- Exact implementation of season splitting logic in load_pitcher_data()
- Whether to use a helper function or inline the split
- Empty DataFrame construction approach

## Deferred Ideas

None — discussion stayed within phase scope
