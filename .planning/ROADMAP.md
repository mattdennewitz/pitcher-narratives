# Roadmap: Pitcher Narratives

## Overview

This roadmap delivers a CLI tool that transforms Statcast pitch data and Pitching+ aggregations into scout-voice narrative reports via Claude. The build follows the data pipeline's natural dependency chain: load and classify data first, then compute the deltas and trend strings that make reports insightful, then wire the LLM agent that turns computed context into prose. Each phase delivers a testable capability -- data flows before computation, computation before generation.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Data Pipeline & Classification** - Load Statcast/P+ data, classify starter vs. reliever, wire CLI skeleton
- [ ] **Phase 2: Fastball & Arsenal Engine** - Compute baselines, deltas, and trend strings for fastball quality and arsenal analysis
- [ ] **Phase 3: Execution & Context Engine** - Compute execution metrics, workload context, and complete the PitcherContext schema
- [ ] **Phase 4: Report Generation** - Wire pydantic-ai agent with Claude, craft system prompt, produce scout-voice narrative output

## Phase Details

### Phase 1: Data Pipeline & Classification
**Goal**: User can run the CLI with a pitcher ID and get validated, pitcher-scoped data with correct role classification
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, ROLE-01, ROLE-02, ROLE-03, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. Running `python main.py -p <pitcher_id>` loads Statcast parquet and Pitching+ CSVs filtered to that pitcher without error
  2. Running with `-w <days>` filters appearances to the specified lookback window; omitting `-w` uses a sensible default
  3. Each appearance is classified as start or relief, and a pitcher who has both start and relief outings gets correct per-appearance classification
  4. Season-level baselines (from pitcher.csv and pitcher_type.csv) are computed and accessible for the given pitcher
**Plans:** 2 plans

Plans:
- [x] 01-01-PLAN.md -- Data loading pipeline: project setup, data.py with all loader/classification/baseline functions, tests
- [x] 01-02-PLAN.md -- CLI wiring: argparse entry point, data pipeline integration, end-to-end tests

### Phase 2: Fastball & Arsenal Engine
**Goal**: The system produces pre-computed fastball quality analysis and arsenal breakdown with deltas and qualitative trend strings ready for LLM consumption
**Depends on**: Phase 1
**Requirements**: FB-01, FB-02, FB-03, FB-04, ARSL-01, ARSL-02, ARSL-03, ARSL-04
**Success Criteria** (what must be TRUE):
  1. For a given pitcher, the system outputs a fastball summary containing season baseline velo, recent window velo, and a qualitative delta string (e.g., "Down 1.2 mph from baseline")
  2. Fastball P+/S+/L+ scores show season baseline vs. recent window with computed deltas and movement shape changes (pfx_x/pfx_z)
  3. Within-game velocity arc analysis shows early-inning vs. late-inning velo drop-off for the most recent appearance
  4. Arsenal analysis shows usage rate per pitch type with delta vs. season baseline, including platoon mix shifts by batter handedness
  5. First-pitch strike weaponry analysis shows which pitch is being used to get ahead recently vs. season norm
**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md -- Fastball quality engine: delta helpers, FastballSummary/VelocityArc dataclasses, primary fastball identification, tests
- [x] 02-02-PLAN.md -- Arsenal analysis engine: per-type usage/P+ deltas, platoon mix shifts, first-pitch weaponry, tests

### Phase 3: Execution & Context Engine
**Goal**: The system produces a complete PitcherContext Pydantic model with execution metrics, workload context, and all engine outputs assembled into a prompt-ready document under 2,000 tokens
**Depends on**: Phase 2
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, CTX-01, CTX-02, CTX-03
**Success Criteria** (what must be TRUE):
  1. Execution metrics section includes CSW%, xWhiff, xSwing per pitch type and zone rate vs. chase rate analysis for the recent window
  2. xRV100 ranking shows how each pitch grades relative to the league
  3. Workload context shows rest days between appearances, innings pitched, pitch counts, and consecutive-days-pitched tracking for relievers
  4. The assembled PitcherContext model renders via `to_prompt()` to a complete markdown document under 2,000 tokens containing all computed sections
**Plans**: TBD

### Phase 4: Report Generation
**Goal**: User runs the CLI and receives a scout-voice narrative scouting report that reads like a human analyst wrote it
**Depends on**: Phase 3
**Requirements**: RPT-01, RPT-02, RPT-03, RPT-04
**Success Criteria** (what must be TRUE):
  1. Running `python main.py -p <pitcher_id>` produces a complete prose scouting report printed to the terminal
  2. The report contains narrative paragraphs interspersed with data tables where they aid comprehension -- not a wall of stats
  3. The report references specific deltas and trends from the computed context (e.g., "His slider usage jumped 12 percentage points") without fabricating claims not present in the input data
  4. Starter reports and reliever reports have visibly different structure (starters get pitch mix depth and stamina; relievers get workload patterns and short-window focus)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Pipeline & Classification | 0/2 | Planning complete | - |
| 2. Fastball & Arsenal Engine | 0/2 | Planning complete | - |
| 3. Execution & Context Engine | 0/0 | Not started | - |
| 4. Report Generation | 0/0 | Not started | - |
