# Roadmap: Pitcher Narratives

## Milestones

- v1.0 MVP - Phases 1-4 (shipped 2026-03-26)
- v1.3 Editor-Anchor Reflection Loop - Phases 5-7 (shipped 2026-03-28)
- v1.4 Interactive Pitcher Q&A - Phases 8-10 (shipped 2026-03-30)
- v1.5 Model-Explainable Narratives - Phases 11-14 (shipped 2026-04-01)
- v1.6 Stuff Explainer - Phase 15 (shipped 2026-04-02)
- v1.7 Multi-Year Data & Game Type Filtering - Phases 16-18

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

<details>
<summary>v1.3 Editor-Anchor Reflection Loop (Phases 5-7) - SHIPPED 2026-03-28</summary>

- [x] **Phase 5: Reflection Data Models** - AnchorResult/AnchorWarning Pydantic models, ReportResult metadata fields, revision prompt builder
- [x] **Phase 6: Loop Mechanics** - While-loop wiring anchor feedback to editor revisions with streaming control and downstream capsule handoff
- [x] **Phase 7: Revision UX & Validation** - Surface surviving warnings and iteration status to stderr, end-to-end loop validation

</details>

<details>
<summary>v1.4 Interactive Pitcher Q&A (Phases 8-10) - SHIPPED 2026-03-30</summary>

- [x] **Phase 8: Name Resolution** - Fuzzy pitcher name matching with disambiguation for ambiguous queries
- [x] **Phase 9: Analyst Agent & Tools** - Tool-calling pydantic-ai agent that answers pitcher questions grounded in data
- [x] **Phase 10: Ask CLI** - CLI entry point composing name resolution and analyst agent into `pitcher-ask`

</details>

<details>
<summary>v1.5 Model-Explainable Narratives (Phases 11-14) - SHIPPED 2026-04-01</summary>

- [x] **Phase 11: Intermediate Probability Pipeline** - Load and surface existing intermediate probabilities (P and S variants) from pitchingplus aggregation CSVs
- [x] **Phase 12: Component Attribution** - Decompose xRV into 13 outcome-level contributions per pitch type
- [x] **Phase 13: Tool Interface Updates** - Update analyst tools to return intermediate probabilities, P/S comparisons, and component attribution
- [x] **Phase 14: Analyst Prompt Rewrite** - Rewrite system prompt to reason from model internals with P/S location diagnosis and outcome-dominant attribution

</details>

### v1.7 Multi-Year Data & Game Type Filtering

- [ ] **Phase 16: Data Foundation** - Filter spring training/exhibition data at load time, parameterize year-specific paths, add "season" to identity columns
- [ ] **Phase 17: Multi-Year Loading** - Concatenate parquet and CSV files across configured years with per-season baselines
- [ ] **Phase 18: Consumer Module Updates** - Eliminate all bypass CSV/parquet reads in engine.py, resolver.py, and scout.py by routing through data.py

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

<details>
<summary>v1.3 Editor-Anchor Reflection Loop (Phases 5-7) - SHIPPED 2026-03-28</summary>

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
- [x] 06-01-PLAN.md -- Wire for/else revision loop, MAX_REVISIONS constant, loop behavior tests

### Phase 7: Revision UX & Validation
**Goal**: Users can observe the reflection loop's behavior and trust that surviving warnings are transparently reported
**Depends on**: Phase 6
**Requirements**: LOOP-03, UX-03
**Success Criteria** (what must be TRUE):
  1. When the capsule passes anchor check on the first try, stderr shows "Passed anchor check" (or equivalent confirmation)
  2. When revisions occur and the capsule converges to CLEAN, stderr shows "Revised N time(s) -- anchor check passed"
  3. When the loop exhausts its revision cap with unresolved warnings, stderr shows the surviving warning descriptions so the user knows what the report could not self-correct
  4. Surviving warnings use the same stderr format as the existing anchor output (no new output channels or formats to learn)
**Plans**: 1 plan

Plans:
- [x] 07-01-PLAN.md -- Extract _print_revision_status helper, replace anchor block, unit + integration tests

</details>

<details>
<summary>v1.4 Interactive Pitcher Q&A (Phases 8-10) - SHIPPED 2026-03-30</summary>

### Phase 8: Name Resolution
**Goal**: Users can identify pitchers by name instead of numeric ID, with clear feedback when names are ambiguous or unrecognized
**Depends on**: Nothing (independent of other v1.4 phases; uses existing data files)
**Requirements**: RESOLVE-01, RESOLVE-02
**Success Criteria** (what must be TRUE):
  1. Given an exact full name (e.g., "Dylan Cease"), the resolver returns the correct pitcher ID without prompting for disambiguation
  2. Given a partial or last name that matches multiple pitchers (e.g., "Johnson"), the resolver returns a ranked list of candidates with names and IDs
  3. Given a name that matches no pitcher in the dataset, the resolver returns a clear "not found" result (not a crash or empty response)
**Plans**: 1 plan

Plans:
- [x] 08-01-PLAN.md -- Resolver module with fuzzy matching and comprehensive tests

### Phase 9: Analyst Agent & Tools
**Goal**: Users can ask natural-language questions about a pitcher and receive analytical answers grounded exclusively in the existing data pipeline
**Depends on**: Phase 4 (existing PitcherContext pipeline; independent of Phase 8)
**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06
**Success Criteria** (what must be TRUE):
  1. Given a broad question (e.g., "How did Cease pitch last week?"), the agent calls `get_pitcher_summary` and produces an answer citing data from the full PitcherContext
  2. Given a pitch-specific question (e.g., "Is his knuckle curve effective?"), the agent calls `get_pitch_detail` with the correct Statcast pitch code (KC) and produces an answer scoped to that pitch type
  3. Given a question the data cannot answer (e.g., "Will he get a win tomorrow?" or "How does he compare to Corbin Burnes?"), the agent declines with an explanation of what data is available rather than hallucinating
  4. The agent's answer streams token-by-token to stdout as it generates
**Plans**: 1 plan

Plans:
- [x] 09-01-PLAN.md -- Analyst module with QADeps, PITCH_TYPE_MAP, tools, agent factory, and streaming function (TDD)

### Phase 10: Ask CLI
**Goal**: Users have a complete command-line workflow for asking pitcher questions by name
**Depends on**: Phase 8, Phase 9
**Requirements**: CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. Running `pitcher-ask "Why is Cease's knuckle curve bad?"` resolves "Cease" to a pitcher ID, runs the analyst agent, and streams an answer to stdout
  2. Running `pitcher-ask --provider openai --thinking low "How is Yamamoto's fastball?"` uses the specified provider and thinking level
  3. When the name is ambiguous, the CLI presents a disambiguation list and exits with a helpful message (no crash, no silent failure)
  4. When no question is provided or the pitcher is not found, the CLI exits with a clear error message and nonzero exit code
**Plans**: 1 plan

Plans:
- [x] 10-01-PLAN.md -- CLI entry point composing resolver + analyst into pitcher-ask command (TDD)

</details>

<details>
<summary>v1.5 Model-Explainable Narratives (Phases 11-14) - SHIPPED 2026-04-01</summary>

### Phase 11: Intermediate Probability Pipeline
**Goal**: The data pipeline loads and surfaces per-pitch-type intermediate probabilities (both P and S variants) from pitchingplus aggregation CSVs so downstream tools can expose them
**Depends on**: Phase 9 (existing analyst agent and data pipeline)
**Requirements**: DATA-01, DATA-02
**Success Criteria** (what must be TRUE):
  1. Data loading reads xSwing_P, xSwing_S, xWhiff_P, xWhiff_S, xGOr_P, xGOr_S, xPUr_P, xPUr_S, xHR100_P, xHR100_S, BBE_prob_P, BBE_prob_S columns from pitchingplus aggregation CSVs
  2. Per-pitch-type aggregations include both P and S variants, enabling location impact calculation (P minus S)
  3. Intermediate probabilities are accessible at the same aggregation grains as existing plus scores (pitcher+type, pitcher+type+appearance)
  4. Missing columns (if a CSV lacks intermediates) are handled gracefully without crashing the pipeline
**Plans**: 1 plan

Plans:
- [x] 11-01-PLAN.md -- IntermediateProbabilities dataclass, compute function, PitcherContext wiring (TDD)

### Phase 12: Component Attribution
**Goal**: Each pitch type's xRV is decomposed into 13 additive outcome contributions, showing which outcomes (whiffs, HRs, ground outs, etc.) drive the overall score
**Depends on**: Phase 11 (intermediate probabilities loaded)
**Requirements**: DATA-03
**Success Criteria** (what must be TRUE):
  1. For each pitch type, 13 outcome-level contributions are computed as (outcome_probability x run_value_for_count)
  2. The 13 contributions sum to the total xRV (within floating-point tolerance)
  3. Each contribution is labeled with its outcome name (e.g., "whiff", "home_run", "called_strike")
  4. Attribution is available at pitcher+type and pitcher+type+appearance grain
**Plans**: 2 plans

Plans:
- [x] 12-01-PLAN.md -- Data prerequisite: regenerate all_pitches.csv with all 13 outcome columns, copy RV_df.csv
- [x] 12-02-PLAN.md -- ComponentAttribution dataclasses, compute function, PitcherContext wiring (TDD)

### Phase 13: Tool Interface Updates
**Goal**: The analyst agent's tools return intermediate probabilities, P/S comparisons, and component attribution alongside existing plus scores
**Depends on**: Phase 11, Phase 12
**Requirements**: TOOL-01, TOOL-02
**Success Criteria** (what must be TRUE):
  1. `get_pitcher_summary` tool output includes per-pitch-type intermediate probabilities with P and S variants
  2. `get_pitch_detail` tool output includes the 13-outcome component attribution breakdown for the requested pitch type
  3. P vs S delta is computed and presented (e.g., "xSwing_P: 42%, xSwing_S: 51%, location delta: -9%")
  4. Existing tool output (plus scores, arsenal, execution metrics) is preserved -- new data is additive
**Plans**: 1 plan

Plans:
- [x] 13-01-PLAN.md -- Intermediates rendering in to_prompt, attribution + intermediates in get_pitch_detail

### Phase 14: Analyst Prompt Rewrite
**Goal**: The analyst reasons from model internals -- diagnosing pitch quality through outcome probabilities and component attribution rather than citing opaque plus grades
**Depends on**: Phase 13 (tools returning new data)
**Requirements**: ANLST-01, ANLST-02, ANLST-03
**Success Criteria** (what must be TRUE):
  1. Analyst explains *why* a pitch scores well or poorly using intermediate probabilities (e.g., "38% whiff rate vs 25% league avg -- the movement fools hitters")
  2. Analyst diagnoses location impact by comparing P vs S variants (e.g., "swing rate drops 9% with location -- hitters lay off this pitch in the zones he's throwing it")
  3. Analyst identifies the dominant run-value driver from component attribution (e.g., "whiffs contribute 1.4 runs saved per 100, but home runs give back 0.6")
  4. Plus scores (P+/S+/L+) are still referenced as summary grades, but the explanation focuses on what drives them
**Plans**: 1 plan

Plans:
- [x] 14-01-PLAN.md -- Rewrite _ANALYST_INSTRUCTIONS with model-internals-first reasoning (TDD)

</details>

### Phase 16: Data Foundation
**Goal**: The data pipeline filters out spring training and exhibition games at load time and replaces all hardcoded year-specific paths with a parameterized `_YEARS` constant, so all downstream modules receive clean regular-season data without knowing about file naming or game type semantics
**Depends on**: Phase 15 (existing data pipeline)
**Requirements**: DFND-01, DFND-02, DFND-03, DFND-04
**Success Criteria** (what must be TRUE):
  1. Running any CLI command produces baselines computed exclusively from regular-season data -- spring training (game_type "S") and exhibition ("E") rows are excluded before any computation
  2. All year-specific file paths in data.py derive from a single `_YEARS` constant -- no hardcoded "2026-" prefixes or "statcast_2026.parquet" literals remain
  3. The `season` column is treated as an identity column (not weight-averaged as a metric) so multi-year data does not produce nonsense values like "2025.375"
  4. A public `filter_game_type()` function is exported from data.py for use by consumer modules that load data independently
  5. All existing tests pass after assertions are updated for filtered (regular-season-only) values
**Plans**: TBD

### Phase 17: Multi-Year Loading
**Goal**: The data pipeline loads and concatenates parquet and CSV files across all configured years, with per-season baselines that prevent cross-season averaging artifacts
**Depends on**: Phase 16
**Requirements**: MYLD-01, MYLD-02, MYLD-03, MYLD-04
**Success Criteria** (what must be TRUE):
  1. `load_statcast()` reads parquet files for all years in `_YEARS` and returns a single concatenated DataFrame spanning both 2025 and 2026
  2. `load_agg_csvs()` reads year-prefixed CSV files for all configured years and returns concatenated DataFrames per grain
  3. When a year's files are missing (e.g., 2025 parquet does not exist), the pipeline skips that year without crashing and loads available years
  4. Season baselines are computed per-season -- a pitcher who threw 95 mph in 2025 and 97 mph in 2026 has a 2026 baseline of 97, not 96
**Plans**: TBD

### Phase 18: Consumer Module Updates
**Goal**: All modules that bypass data.py to read CSV or parquet files directly are refactored to use data.py's loading functions, ensuring game type filtering and multi-year support are applied consistently everywhere
**Depends on**: Phase 16, Phase 17
**Requirements**: CSMR-01, CSMR-02, CSMR-03
**Success Criteria** (what must be TRUE):
  1. `engine.py` no longer contains any direct `read_csv` or `read_parquet` calls -- all data access routes through `data.py` functions
  2. `resolver.py` builds its pitcher name table from all available parquet files (not just 2026), so pitchers who appeared only in 2025 are discoverable
  3. `scout.py` no longer contains any direct CSV or parquet reads -- all data access routes through `data.py` functions including the velocity baseline computation
  4. Running `grep "read_csv\|read_parquet" src/pitcher_narratives/ | grep -v data.py` returns zero results (no bypass loads remain)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 16 -> 17 -> 18

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
| 15. Stuff Explainer | v1.6 | 1/1 | Complete | 2026-04-02 |
| 16. Data Foundation | v1.7 | 0/0 | Not started | -- |
| 17. Multi-Year Loading | v1.7 | 0/0 | Not started | -- |
| 18. Consumer Module Updates | v1.7 | 0/0 | Not started | -- |
