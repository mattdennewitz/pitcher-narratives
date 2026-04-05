---
phase: quick-260405-gtv
plan: 01
subsystem: context-assembly
tags: [temporal-context, hallucination-guard, prompt-engineering, polars]

# Dependency graph
requires:
  - phase: quick-260403-f5t
    provides: "appearance pitch trends and cross-season context assembly"
provides:
  - "TemporalContext dataclass with per-season appearance counts, IP, and prior-year relevance tier"
  - "compute_temporal_context() function splitting appearances by season year"
  - "_sum_baseball_ip() helper for summing baseball-notation IP strings"
  - "Temporal grounding rules in all 7 narrative-generating prompts"
affects: [report, pipeline, analyst, context-assembly, prompt-rendering]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Prior-year relevance tier (HIGH/MODERATE/LOW) gating LLM workload narrative weight"
    - "Temporal Context section rendered as first section after title in LLM prompts"

key-files:
  created: []
  modified:
    - "src/pitcher_narratives/engine.py"
    - "src/pitcher_narratives/context.py"
    - "src/pitcher_narratives/report.py"
    - "src/pitcher_narratives/pipeline.py"
    - "src/pitcher_narratives/analyst.py"

key-decisions:
  - "Prior-year relevance tiers: HIGH (<10 apps), MODERATE (10-30), LOW (>30) -- gates LLM narrative weight"
  - "Season phase labels: early (<10 apps), mid (10-60), full (>60) -- for human-readable context"
  - "Temporal Context rendered before Executive Summary so LLM reads it first"

patterns-established:
  - "Temporal grounding pattern: dataclass + compute function + rendered section + per-prompt rules"

requirements-completed: [GTV-01]

# Metrics
duration: 5min
completed: 2026-04-05
---

# Quick Task 260405-gtv: TemporalContext with Sliding Prior-Year Relevance

**TemporalContext dataclass with per-season appearance/IP counts and HIGH/MODERATE/LOW prior-year relevance tier, wired into all 7 narrative-generating prompts to prevent cross-season fatigue hallucination**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-05T16:12:13Z
- **Completed:** 2026-04-05T16:17:40Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Added TemporalContext dataclass to engine.py with analysis_date, per-season appearance counts, IP totals, and prior-year relevance tier (HIGH/MODERATE/LOW)
- Added compute_temporal_context() that derives season from game_date, sums baseball-notation IP per season, and assigns relevance tier based on current-season appearance count
- Wired temporal field into PitcherContext model with _render_temporal_section() rendering before Executive Summary
- Added temporal grounding instructions to all 7 narrative-generating prompts (synthesizer, editor, trend specialist, game shape specialist, writer, analyst, answerer)
- End-to-end verified with real pitcher data: correct per-season stats, proper relevance tier, section ordering

## Task Commits

Each task was committed atomically:

1. **Task 1: Add TemporalContext dataclass, compute function, and wire into PitcherContext** - `ce286a6` (feat)
2. **Task 2: Add temporal grounding rules to all narrative-generating prompts** - `e68c7bd` (feat)
3. **Task 3: End-to-end smoke test** - verification only, no commit

## Files Created/Modified
- `src/pitcher_narratives/engine.py` - Added TemporalContext dataclass, _sum_baseball_ip() helper, compute_temporal_context() function
- `src/pitcher_narratives/context.py` - Added temporal field to PitcherContext, _render_temporal_section() method, wired into to_prompt() and assemble_pitcher_context()
- `src/pitcher_narratives/report.py` - Added temporal grounding rules to _SYNTHESIZER_PROMPT (rule 0) and _EDITOR_PROMPT (rule 1.5)
- `src/pitcher_narratives/pipeline.py` - Added TEMPORAL GROUNDING rules to _TREND_SPECIALIST_PROMPT, _GAME_SHAPE_SPECIALIST_PROMPT, and _WRITER_PROMPT
- `src/pitcher_narratives/analyst.py` - Added TEMPORAL GROUNDING sections to ANALYST_INSTRUCTIONS and ANSWERER_INSTRUCTIONS

## Decisions Made
- Prior-year relevance tiers based on current-season appearance count: <10 = HIGH (sample too small), 10-30 = MODERATE (growing), >30 = LOW (self-sufficient) -- simple thresholds that match baseball season pacing
- When no prior season data exists, relevance is HIGH with a reason noting absence -- prevents the LLM from inventing prior-season context
- Temporal Context section placed first after title so the LLM reads temporal grounding before any analysis data
- Used date.today() for analysis_date to ground the report against real calendar time

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used environment variable to point to main repo data for E2E test**
- **Found during:** Task 3 (End-to-end smoke test)
- **Issue:** Worktree does not contain parquet data files; pitcher 660882 not found in local data
- **Fix:** Set PITCHER_NARRATIVES_DATA_DIR to main repo path and used an available pitcher ID (434378) instead of 660882
- **Files modified:** None (runtime-only adjustment)
- **Verification:** E2E test passed with pitcher 434378 showing correct temporal context

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Test adapted to available data. No code changes needed.

## Issues Encountered
None beyond the data path deviation noted above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Temporal grounding is fully wired into the context assembly and all narrative prompts
- Ready for Phase 22 context-assembly-prompt-rendering work
- Future consideration: temporal thresholds could be tuned based on observed LLM behavior

## Self-Check: PASSED

- All 5 modified files exist on disk
- Commit ce286a6 (Task 1) verified in git log
- Commit e68c7bd (Task 2) verified in git log
- SUMMARY.md created at expected path

---
*Quick Task: 260405-gtv*
*Completed: 2026-04-05*
