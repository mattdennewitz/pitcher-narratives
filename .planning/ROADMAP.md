# Roadmap: Pitcher Narratives

## Milestones

- ✅ **v1.0 MVP** — Phases 1-4 (shipped 2026-03-26)
- ✅ **v1.3 Editor-Anchor Reflection Loop** — Phases 5-7 (shipped 2026-03-28)
- ✅ **v1.4 Interactive Pitcher Q&A** — Phases 8-10 (shipped 2026-03-30)
- ✅ **v1.5 Model-Explainable Narratives** — Phases 11-14 (shipped 2026-04-01)
- ✅ **v1.6 Multi-Agent Pipeline** — Phase 15 (shipped 2026-04-03)
- ✅ **v1.7 Multi-Year Data & Game Type Filtering** — Phases 16-18 (shipped 2026-04-03)
- 🚧 **v1.8 Cross-Season Trend Analysis** — Phases 19-22 (in progress)

### v1.8 Cross-Season Trend Analysis

**Milestone Goal:** Reports surface year-over-year changes -- a pitcher who added a sweeper, gained 2 mph, or saw Stuff+ collapse gets that story told automatically.

- [ ] **Phase 19: Cross-Season Baseline Exposure** - Make prior-season baselines available to engine computations
- [ ] **Phase 20: Season-Delta Engine** - Compute year-over-year deltas for top-level pitcher metrics
- [x] **Phase 21: Arsenal Trend Engine** - Compute year-over-year deltas per pitch type (added/dropped pitches, usage shifts, grade changes) (completed 2026-04-03)
- [ ] **Phase 22: Context Assembly & Prompt Rendering** - Integrate cross-season insights into PitcherContext and LLM prompt

## Phase Details

### Phase 19: Cross-Season Baseline Exposure
**Goal**: Engine functions can access both current-season and prior-season baselines for any pitcher
**Depends on**: Phase 18 (all data access centralized through data.py)
**Requirements**: XSBL-01, XSBL-02, XSBL-03
**Success Criteria** (what must be TRUE):
  1. PitcherData contains both current-season and prior-season baseline DataFrames when multi-year data exists
  2. When a pitcher has only one season of data, prior-season baselines are empty (not None, not crash)
  3. Existing engine functions continue to work unchanged (no regression in single-season behavior)
**Plans**: TBD

### Phase 20: Season-Delta Engine
**Goal**: Users see year-over-year changes in top-level pitcher metrics (velocity, P+/S+/L+, workload profile)
**Depends on**: Phase 19
**Requirements**: SDLT-01, SDLT-02, SDLT-03
**Success Criteria** (what must be TRUE):
  1. Engine produces a cross-season summary dataclass with YoY deltas for velocity, P+, S+, L+ at the pitcher level
  2. Delta strings use the same qualitative language as within-season deltas ("Up sharply", "Down modestly", "Steady") so the LLM prompt stays consistent
  3. When prior-season data is missing, the cross-season summary is None (not empty strings or zeroes)
**Plans**: TBD

### Phase 21: Arsenal Trend Engine
**Goal**: Users see which pitches a pitcher added, dropped, or significantly changed year-over-year
**Depends on**: Phase 19
**Requirements**: ATRN-01, ATRN-02, ATRN-03
**Success Criteria** (what must be TRUE):
  1. Engine identifies pitches present in prior season but absent in current season (dropped) and vice versa (added)
  2. Engine computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity
  3. When a pitcher has only one season of data, arsenal trend output is None (no fabricated trends)
**Plans**: TBD

### Phase 22: Context Assembly & Prompt Rendering
**Goal**: Cross-season insights appear in the LLM prompt so narratives can reference year-over-year changes
**Depends on**: Phase 20, Phase 21
**Requirements**: CPMT-01, CPMT-02, CPMT-03
**Success Criteria** (what must be TRUE):
  1. PitcherContext includes cross-season summary and arsenal trend fields
  2. to_prompt() renders a "Year-over-Year" section with top-level deltas and arsenal changes when multi-season data exists
  3. to_prompt() omits the cross-season section entirely for single-season pitchers (no empty headers, no "N/A" placeholders)
  4. Specialist pipeline agents receive cross-season data in their context blocks
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Data Pipeline & Classification | v1.0 | 2/2 | Complete | 2026-03-26 |
| 2. Fastball & Arsenal Engine | v1.0 | 2/2 | Complete | 2026-03-26 |
| 3. Execution & Context Engine | v1.0 | 2/2 | Complete | 2026-03-26 |
| 4. Report Generation | v1.0 | 2/2 | Complete | 2026-03-26 |
| 5. Reflection Data Models | v1.3 | 2/2 | Complete | 2026-03-28 |
| 6. Loop Mechanics | v1.3 | 1/1 | Complete | 2026-03-28 |
| 7. Revision UX & Validation | v1.3 | 1/1 | Complete | 2026-03-28 |
| 8. Name Resolution | v1.4 | 1/1 | Complete | 2026-03-30 |
| 9. Analyst Agent & Tools | v1.4 | 1/1 | Complete | 2026-03-30 |
| 10. Ask CLI | v1.4 | 1/1 | Complete | 2026-03-30 |
| 11. Intermediate Probability Pipeline | v1.5 | 1/1 | Complete | 2026-03-31 |
| 12. Component Attribution | v1.5 | 2/2 | Complete | 2026-03-31 |
| 13. Tool Interface Updates | v1.5 | 1/1 | Complete | 2026-03-31 |
| 14. Analyst Prompt Rewrite | v1.5 | 1/1 | Complete | 2026-03-31 |
| 15. Specialist-Writer Architecture | v1.6 | prototyped | Complete | 2026-04-03 |
| 16. Data Foundation | v1.7 | 1/1 | Complete | 2026-04-03 |
| 17. Multi-Year Loading | v1.7 | 1/1 | Complete | 2026-04-03 |
| 18. Consumer Module Updates | v1.7 | 2/2 | Complete | 2026-04-03 |
| 19. Cross-Season Baseline Exposure | v1.8 | 0/0 | Not started | - |
| 20. Season-Delta Engine | v1.8 | 0/0 | Not started | - |
| 21. Arsenal Trend Engine | v1.8 | 1/1 | Complete    | 2026-04-03 |
| 22. Context Assembly & Prompt Rendering | v1.8 | 0/0 | Not started | - |

---
*Full phase details archived in `.planning/milestones/`*
