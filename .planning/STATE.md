---
gsd_state_version: 1.0
milestone: v1.8
milestone_name: Cross-Season Trend Analysis
status: ready_to_plan
stopped_at: Roadmap created for v1.8
last_updated: "2026-04-05T13:36:17Z"
last_activity: 2026-04-05
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** Reports must read like a scout wrote them -- surfacing changes, adaptations, and execution trends rather than reciting numbers.
**Current focus:** v1.8 Cross-Season Trend Analysis -- Phase 19 ready to plan

## Current Position

Phase: 19 (Cross-Season Baseline Exposure)
Plan: Not started
Status: Ready to plan
Last activity: 2026-04-02

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

- v1.7: Per-season baseline grouping (not cross-season averaged) -- foundation for v1.8
- v1.7: load_pitcher_data() filters baselines to max season -- v1.8 Phase 19 removes this filter

### Pending Todos

None.

### Blockers/Concerns

- pitchingplus model internals at ~/src/pitchingplus/packages/plus -- external dependency, changes there affect this project's data pipeline
- Only 2 years of data exist (2025 parquet may not exist on all machines) -- tests must use synthetic multi-year data

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260403-cr4 | Add per-pitch-type movement and velocity deltas to YoY arsenal trends | 2026-04-03 | 3d714bc | [260403-cr4-add-per-pitch-type-movement-and-velocity](./quick/260403-cr4-add-per-pitch-type-movement-and-velocity/) |
| 260403-f5t | Add per-appearance pitch trends (three-way comparison) | 2026-04-03 | 9292143 | [260403-f5t-add-per-appearance-pitch-trends-comparin](./quick/260403-f5t-add-per-appearance-pitch-trends-comparin/) |
| 260404-vya | Add CachePoint support to pipeline specialist builders | 2026-04-05 | e79d2c9 | [260404-vya-fully-examine-new-prompts-and-reset-cach](./quick/260404-vya-fully-examine-new-prompts-and-reset-cach/) |
| 260405-cmp | Optimize LLM spend: right-size max_tokens and thinking per agent role | 2026-04-05 | 3c7bf6b | [260405-cmp-optimize-llm-spend-right-size-max-tokens](./quick/260405-cmp-optimize-llm-spend-right-size-max-tokens/) |
| 260405-d6c | Add MINI_PROVIDERS model tier and route lightweight agents to mini models | 2026-04-05 | c43da35 | [260405-d6c-add-mini-providers-model-tier-and-route-](./quick/260405-d6c-add-mini-providers-model-tier-and-route-/) |

## Session Continuity

Last session: 2026-04-05
Last activity: 2026-04-05 - Completed quick task 260405-d6c: MINI_PROVIDERS model tier
Stopped at: Completed quick task 260405-d6c
Resume file: None
