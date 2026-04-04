# Roadmap: Pitcher Narratives

## Milestones

- ✅ **v1.0 MVP** — Phases 1-4 (shipped 2026-03-26)
- ✅ **v1.3 Editor-Anchor Reflection Loop** — Phases 5-7 (shipped 2026-03-28)
- ✅ **v1.4 Interactive Pitcher Q&A** — Phases 8-10 (shipped 2026-03-30)
- ✅ **v1.5 Model-Explainable Narratives** — Phases 11-14 (shipped 2026-04-01)
- ✅ **v1.6 Multi-Agent Pipeline** — Phase 15 (shipped 2026-04-03)
- ✅ **v1.7 Multi-Year Data & Game Type Filtering** — Phases 16-18 (shipped 2026-04-03)
- ✅ **v1.8 Cross-Season Trend Analysis** — Phases 19-22 (shipped 2026-04-03)
- 🚧 **v1.9 Multi-Agent Narrative Upgrade** — Phases 23-25 (in progress)

## Phases

### v1.9 Multi-Agent Narrative Upgrade

**Milestone Goal:** Deepen the 6-agent specialist pipeline with count-state awareness, arm angle context, approach analysis, and prompt heuristics that push narratives toward causal reasoning and trade-off detection.

- [x] **Phase 23: Engine Foundation & Data Enrichment** - CountSplits engine, arm angle calculation, percentile outlier tags, context wiring (completed 2026-04-04)
- [x] **Phase 24: Pipeline Re-Architecture** - Approach Specialist agent, RP dynamic routing, raw data appendix, Location Specialist platoon removal (completed 2026-04-04)
- [ ] **Phase 25: Prompt Engineering & Heuristic Injection** - Trade-off, contradiction, release-point, causal-hook directives, auditor whitelist

## Phase Details

### Phase 23: Engine Foundation & Data Enrichment
**Goal**: Engine produces count-state usage splits, arm angle metrics, and percentile-ranked outlier tags so downstream agents have richer analytical inputs
**Depends on**: Phase 22 (context assembly and prompt rendering complete)
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05
**Success Criteria** (what must be TRUE):
  1. Engine output includes per-pitch-type usage rates across four count states (ahead/behind/even/two-strike) with window-vs-season deltas
  2. Engine output includes arm angle computed from release point coordinates, with a delta string showing window-vs-season change
  3. Outlier tags display percentile rank (e.g., "OUTLIER - 98th percentile") instead of raw z-score notation
  4. PitcherContext model includes CountSplits and arm angle fields, and to_prompt() renders them into the context document
  5. Count buckets with fewer than 10 pitches are flagged as small sample with no usage delta computed
**Plans**: 3 plans
Plans:
- [x] 23-01-PLAN.md -- CountSplits dataclasses and compute_count_splits engine function
- [x] 23-02-PLAN.md -- Arm angle fields on ReleasePointPitchType + LeagueBaseline extension + outlier_tag percentile upgrade
- [x] 23-03-PLAN.md -- PitcherContext wiring + to_prompt rendering (count splits adjacent to platoon, arm angle in release point)

### Phase 24: Pipeline Re-Architecture
**Goal**: The specialist pipeline expands to 6 agents with an Approach Specialist handling platoon/count analysis, dynamic RP routing that skips Game Shape, and raw data appendices for grounding
**Depends on**: Phase 23 (CountSplits and arm angle data available for Approach Specialist input)
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06, PIPE-07
**Success Criteria** (what must be TRUE):
  1. Approach Specialist agent runs as 6th specialist, receiving platoon mix, count splits, and first-pitch data, with its prompt prioritizing 10+ pp usage shifts
  2. Location Specialist no longer receives platoon data in its input (platoon analysis moved entirely to Approach Specialist)
  3. Game Shape specialist is skipped for relievers (ctx.role == "RP") and replaced with a static placeholder in the writer input
  4. Stuff and Trend specialist inputs include a raw data appendix with PitchTypeSummary deltas for grounding
  5. Writer receives all 6 specialist outputs and auditor validates all 6 (up from 5)
**Plans**: 3 plans
Plans:
- [x] 24-01-PLAN.md -- Approach Specialist prompt + input builder, RP workload stub, game shape conditional
- [x] 24-02-PLAN.md -- Stuff per-pitch delta table and Trend timeline appendix (raw data grounding)
- [x] 24-03-PLAN.md -- Full pipeline wiring: 6-agent orchestration, writer prompt, auditor categories

### Phase 25: Prompt Engineering & Heuristic Injection
**Goal**: Specialist and writer prompts encode sabermetric heuristics so narratives surface trade-offs, contradictions, and causal chains instead of just restating metric directions
**Depends on**: Phase 24 (6-agent architecture wired and validated before updating prompts)
**Requirements**: PROMPT-01, PROMPT-02, PROMPT-03, PROMPT-04, PROMPT-05, PROMPT-06
**Success Criteria** (what must be TRUE):
  1. Stuff Specialist prompt detects and narrates trade-off patterns (e.g., velo down + movement up = S+ improvement)
  2. Location Specialist prompt detects and narrates contradiction patterns (e.g., low zone rate + high whiff = expanding zone), with xWhiff and zone_rate placed adjacent in input
  3. Trend Specialist prompt uses release-point framing vocabulary (arm angle, deception, approach angle) when arm angle data is present
  4. Writer prompt requires a physical-driver citation whenever S+ changes by 10+ points (causal hook)
  5. Data Auditor prompt whitelists sabermetric heuristics (inverse correlations, zone expansion) so valid analysis is not flagged as hallucination
**Plans**: 3 plans
Plans:
- [x] 25-01-PLAN.md -- Specialist prompt heuristics: Stuff trade-off detection, Location contradiction detection, Trend release-point vocabulary function
- [x] 25-02-PLAN.md -- Writer causal hook requirement + auditor sabermetric whitelist
- [ ] 25-03-PLAN.md -- Location input restructuring: per-pitch-type unified view with adjacent contradiction metrics

## Progress

**Execution Order:**
Phases execute in numeric order: 23 -> 24 -> 25

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
| 19. Cross-Season Baseline Exposure | v1.8 | 1/1 | Complete | 2026-04-03 |
| 20. Season-Delta Engine | v1.8 | 1/1 | Complete | 2026-04-03 |
| 21. Arsenal Trend Engine | v1.8 | 1/1 | Complete | 2026-04-03 |
| 22. Context Assembly & Prompt Rendering | v1.8 | 1/1 | Complete | 2026-04-03 |
| 23. Engine Foundation & Data Enrichment | v1.9 | 3/3 | Complete    | 2026-04-04 |
| 24. Pipeline Re-Architecture | v1.9 | 3/3 | Complete    | 2026-04-04 |
| 25. Prompt Engineering & Heuristic Injection | v1.9 | 1/3 | In Progress|  |

---
*Full phase details archived in `.planning/milestones/`*
