# Roadmap: Pitcher Narratives

## Milestones

- v1.0 MVP - Phases 1-4 (shipped 2026-03-26)
- v1.3 Editor-Anchor Reflection Loop - Phases 5-7 (in progress)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

<details>
<summary>v1.0 MVP (Phases 1-4) - SHIPPED 2026-03-26</summary>

- [x] **Phase 1: Data Pipeline & Classification** - Load Statcast/P+ data, classify starter vs. reliever, wire CLI skeleton
- [x] **Phase 2: Fastball & Arsenal Engine** - Compute baselines, deltas, and trend strings for fastball quality and arsenal analysis
- [x] **Phase 3: Execution & Context Engine** - Compute execution metrics, workload context, and complete the PitcherContext schema
- [x] **Phase 4: Report Generation** - Wire pydantic-ai agent with Claude, craft system prompt, produce scout-voice narrative output

</details>

### v1.3 Editor-Anchor Reflection Loop

- [ ] **Phase 5: Reflection Data Models** - AnchorResult/AnchorWarning Pydantic models, ReportResult metadata fields, revision prompt builder
- [ ] **Phase 6: Loop Mechanics** - While-loop wiring anchor feedback to editor revisions with streaming control and downstream capsule handoff
- [ ] **Phase 7: Revision UX & Validation** - Surface surviving warnings and iteration status to stderr, end-to-end loop validation

## Phase Details

<details>
<summary>v1.0 MVP (Phases 1-4) - SHIPPED 2026-03-26</summary>

### Phase 1: Data Pipeline & Classification
**Goal**: User can run the CLI with a pitcher ID and get validated, pitcher-scoped data with correct role classification
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, ROLE-01, ROLE-02, ROLE-03, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. Running `python main.py -p <pitcher_id>` loads Statcast parquet and Pitching+ CSVs filtered to that pitcher without error
  2. Running with `-w <days>` filters appearances to the specified lookback window; omitting `-w` uses a sensible default
  3. Each appearance is classified as start or relief, and a pitcher who has both start and relief outings gets correct per-appearance classification
  4. Season-level baselines (from pitcher.csv and pitcher_type.csv) are computed and accessible for the given pitcher
**Plans**: 2 plans

Plans:
- [x] 01-01: Data loading pipeline
- [x] 01-02: CLI wiring

### Phase 2: Fastball & Arsenal Engine
**Goal**: The system produces pre-computed fastball quality analysis and arsenal breakdown with deltas and qualitative trend strings ready for LLM consumption
**Depends on**: Phase 1
**Requirements**: FB-01, FB-02, FB-03, FB-04, ARSL-01, ARSL-02, ARSL-03, ARSL-04
**Success Criteria** (what must be TRUE):
  1. Fastball summary with season baseline velo, recent window velo, and qualitative delta string
  2. Fastball P+/S+/L+ scores show baseline vs. window with movement shape changes
  3. Within-game velocity arc analysis shows early vs. late velo drop-off
  4. Arsenal usage rate per pitch type with delta vs. baseline, including platoon mix shifts
  5. First-pitch strike weaponry analysis shows recent vs. season norm
**Plans**: 2 plans

Plans:
- [x] 02-01: Fastball quality engine
- [x] 02-02: Arsenal analysis engine

### Phase 3: Execution & Context Engine
**Goal**: Complete PitcherContext Pydantic model with execution metrics, workload context, and all engine outputs assembled into a prompt-ready document
**Depends on**: Phase 2
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, CTX-01, CTX-02, CTX-03
**Success Criteria** (what must be TRUE):
  1. Execution metrics include CSW%, xWhiff, xSwing per pitch type and zone rate vs. chase rate
  2. xRV100 ranking shows pitch grade relative to league
  3. Workload context shows rest days, IP, pitch counts, consecutive-days tracking
  4. PitcherContext renders via to_prompt() under 2,000 tokens
**Plans**: 2 plans

Plans:
- [x] 03-01: Execution metrics and workload context
- [x] 03-02: PitcherContext assembly

### Phase 4: Report Generation
**Goal**: User runs the CLI and receives a scout-voice narrative scouting report
**Depends on**: Phase 3
**Requirements**: RPT-01, RPT-02, RPT-03, RPT-04
**Success Criteria** (what must be TRUE):
  1. CLI produces a complete prose scouting report printed to the terminal
  2. Report contains narrative paragraphs with data tables where they aid comprehension
  3. Report references specific deltas and trends without fabricating claims
  4. Starter and reliever reports have visibly different structure
**Plans**: 2 plans

Plans:
- [x] 04-01: Report module with pydantic-ai Agent
- [x] 04-02: CLI wiring with error handling

</details>

### Phase 5: Reflection Data Models
**Goal**: The codebase has structured types for anchor check results, revision metadata, and a prompt builder that constructs targeted revision instructions from anchor warnings
**Depends on**: Phase 4 (existing pipeline)
**Requirements**: MODEL-01, MODEL-02, LOOP-02
**Success Criteria** (what must be TRUE):
  1. Anchor check agent returns an AnchorResult Pydantic model with is_clean boolean and a list of typed AnchorWarning objects (each with category and description) instead of a raw string
  2. ReportResult dataclass includes a revision_count field (0 = passed first try, 1-2 = revised N times) accessible after report generation completes
  3. A revision prompt builder function produces a fixed-size message containing the synthesis context, the current capsule, formatted warnings, and a targeted instruction to fix only the flagged issues while preserving voice and unflagged material
  4. All new types and the prompt builder are independently testable with no LLM calls (pure functions with deterministic outputs)
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md -- Anchor models, ReportResult update, agent + pipeline + CLI changes, test fixes
- [x] 05-02-PLAN.md -- Revision prompt builder function and tests

### Phase 6: Loop Mechanics
**Goal**: The editor-anchor cycle self-corrects the capsule before downstream phases receive it, with streaming only on the final version
**Depends on**: Phase 5
**Requirements**: LOOP-01, LOOP-04, UX-01, UX-02, UX-04
**Success Criteria** (what must be TRUE):
  1. Running a narrative generation automatically invokes the anchor check after the editor produces a capsule, and if warnings are found, the editor revises and the anchor re-checks (up to 2 revision passes)
  2. When the anchor returns CLEAN on any pass (including the first), the loop exits immediately with no additional LLM calls
  3. Only the final capsule (whether first draft or last revision) streams to stdout; revision passes run silently without visible output
  4. Hook writer and fantasy analyst phases receive the final revised capsule, not the original first draft
  5. The loop runs by default on every narrative generation without requiring a flag to enable it
**Plans**: 1 plan

Plans:
- [ ] 06-01-PLAN.md -- Wire for/else revision loop, MAX_REVISIONS constant, loop behavior tests

### Phase 7: Revision UX & Validation
**Goal**: Users can observe the reflection loop's behavior and trust that surviving warnings are transparently reported
**Depends on**: Phase 6
**Requirements**: LOOP-03, UX-03
**Success Criteria** (what must be TRUE):
  1. When the capsule passes anchor check on the first try, stderr shows "Passed anchor check" (or equivalent confirmation)
  2. When revisions occur and the capsule converges to CLEAN, stderr shows "Revised N time(s) -- anchor check passed"
  3. When the loop exhausts its revision cap with unresolved warnings, stderr shows the surviving warning descriptions so the user knows what the report could not self-correct
  4. Surviving warnings use the same stderr format as the existing anchor output (no new output channels or formats to learn)
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 5 -> 6 -> 7

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Data Pipeline & Classification | v1.0 | 2/2 | Complete | 2026-03-26 |
| 2. Fastball & Arsenal Engine | v1.0 | 2/2 | Complete | 2026-03-26 |
| 3. Execution & Context Engine | v1.0 | 2/2 | Complete | 2026-03-26 |
| 4. Report Generation | v1.0 | 2/2 | Complete | 2026-03-26 |
| 5. Reflection Data Models | v1.3 | 2/2 | Complete | 2026-03-28 |
| 6. Loop Mechanics | v1.3 | 0/1 | Not started | - |
| 7. Revision UX & Validation | v1.3 | 0/1 | Not started | - |
