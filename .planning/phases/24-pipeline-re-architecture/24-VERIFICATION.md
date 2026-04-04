---
phase: 24-pipeline-re-architecture
verified: 2026-04-04T21:10:00Z
status: passed
score: 9/9 must-haves verified
gaps: []
human_verification: []
---

# Phase 24: Pipeline Re-Architecture Verification Report

**Phase Goal:** Pipeline architecture expands from 5 to 6 specialists with an Approach Specialist, adds RP conditional routing, adds raw data appendices, and wires all 6 agents through the writer and auditor.
**Verified:** 2026-04-04T21:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Approach Specialist agent receives platoon mix, count splits, and first-pitch data | VERIFIED | `_build_approach_input` calls `ctx._render_platoon_section()`, `ctx._render_count_splits_section()`, `ctx._render_first_pitch_section()` (pipeline.py:824-828) |
| 2 | Approach Specialist prompt prioritizes 10+ pp usage shifts as lead stories | VERIFIED | `_APPROACH_SPECIALIST_PROMPT` contains "10+" and "LEAD WITH THE BIGGEST SHIFTS" (pipeline.py:299-301) |
| 3 | Location Specialist input contains no platoon data | VERIFIED | `_build_location_input` has no platoon render calls; `test_location_input_no_platoon` passes |
| 4 | Game Shape specialist is skipped for relievers and replaced with a workload stub | VERIFIED | `if ctx.role == "RP": return _build_rp_workload_stub(ctx)` at top of `_build_game_shape_input` (pipeline.py:761-762) |
| 5 | Stuff and Trend specialist inputs include raw data appendices | VERIFIED | `_build_stuff_input` appends "## Raw Data (cite these exact numbers)" + "### Per-Pitch Delta Table" (pipeline.py:617-618); `_build_trend_input` appends "### Primary Pitch Deltas (≥10% usage)" (pipeline.py:727-728) |
| 6 | Writer receives all 6 specialist outputs including Approach Specialist analysis | VERIFIED | `build_writer_input` accepts `approach: str` param and renders "## Specialist Analysis 6: Approach\n{approach}" (pipeline.py:877); `_run_pipeline` passes `specialists.approach` (pipeline.py:1273) |
| 7 | Writer prompt says Six specialist analyses and includes approach description | VERIFIED | `_build_writer_prompt("SP")` returns "Six specialist analyses" and "6. Approach analysis — platoon, count-state, and first-pitch strategy patterns" (pipeline.py:431-437) |
| 8 | Writer prompt includes RP-conditional text when ctx.role is RP | VERIFIED | `_build_writer_prompt("RP")` includes "Do not fabricate TTO analysis" and "workload section replaces Game Shape" (pipeline.py:421-424); `_run_pipeline` passes `ctx.role` to `make_pipeline_agents` (pipeline.py:1247) |
| 9 | Auditor runs 6 audits total with 2 domain-specific categories for Approach | VERIFIED | `specialist_names = ["stuff", "location", "runvalue", "trends", "game_shape", "approach"]` (pipeline.py:938); `_DATA_AUDITOR_PROMPT` contains categories 8 (PLATOON_CLAIM_MISMATCH) and 9 (COUNT_STATE_CLAIM_MISMATCH) with "apply ONLY when" conditional framing (pipeline.py:361-375) |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/pipeline.py` | `_APPROACH_SPECIALIST_PROMPT` constant, `_build_approach_input`, `_build_rp_workload_stub`, RP guard in `_build_game_shape_input` | VERIFIED | All four present and substantive; RP guard at line 761; approach registered in `_get_specialist_input` dispatch (line 918) |
| `src/pitcher_narratives/pipeline.py` | `SpecialistOutputs.approach` field, `PipelineAgents.approach` field, updated `run_specialists`, `audit_and_revise_specialists`, `build_writer_input`, `_run_pipeline` with 6th agent | VERIFIED | All present: SpecialistOutputs (line 1116), PipelineAgents (line 1141), run_specialists (line 1197), audit list (line 938), build_writer_input (line 863), `_run_pipeline` (line 1247-1274) |
| `src/pitcher_narratives/pipeline.py` | Per-pitch delta table in `_build_stuff_input`, primary pitch appendix in `_build_trend_input` | VERIFIED | Stuff: lines 617-630; Trend: lines 727-740 |
| `src/pitcher_narratives/pipeline.py` | `_build_writer_prompt(role)` function (not constant), auditor categories 8-9 | VERIFIED | Function at line 409; no `_WRITER_PROMPT = """` constant; categories 8-9 at lines 361-375 |
| `tests/test_pipeline.py` | Test classes for approach input, approach prompt, RP game shape skip, location platoon absence, stuff/trend appendices, writer input, writer prompt, auditor prompt | VERIFIED | 12 new test classes: TestBuildApproachInput (6 tests), TestApproachPrompt (4), TestRPGameShapeSkip (5), TestStuffAppendix (6), TestTrendAppendix (3), TestSpecialistOutputsApproach (2), TestPipelineAgentsApproach (4), TestRunSpecialistsApproach (1), TestAuditSixSpecialists (1), TestAnchorSynthesisApproach (1), TestBuildWriterInput (3), TestWriterPrompt (6), TestAuditorPrompt (3) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pipeline.py::_build_approach_input` | `PitcherContext._render_platoon_section`, `_render_count_splits_section`, `_render_first_pitch_section` | method calls on ctx | WIRED | Lines 824-828 in pipeline.py |
| `pipeline.py::_build_game_shape_input` | `PitcherContext.role` | RP conditional guard | WIRED | `if ctx.role == "RP": return _build_rp_workload_stub(ctx)` at line 761 |
| `pipeline.py::run_specialists` | `approach_agent` in asyncio.gather | 6th task in parallel dispatch | WIRED | `tasks["approach"]` in gather (line 1223); result index 5 (line 1229) |
| `pipeline.py::build_writer_input` | `approach` parameter | 6th specialist section | WIRED | Param in signature (line 863); "Specialist Analysis 6: Approach" in output (line 877) |
| `pipeline.py::audit_and_revise_specialists` | `"approach"` in specialist_names | 6th audit in parallel | WIRED | `specialist_names = [..., "approach"]` at line 938 |
| `pipeline.py::_run_pipeline` | `agents.approach` in Phase 1 + 1.5 + 2 + 2.5 | full pipeline orchestration | WIRED | `agents.approach` in run_specialists call (line 1253), specialist_agents dict (line 1262), build_writer_input (line 1273), anchor synthesis (line 1313) |

---

### Data-Flow Trace (Level 4)

All phase-24 artifacts produce computed content from PitcherContext, not dynamic data from a DB. The data flow is: Parquet files → PitcherContext fields → input builder functions → LLM agent inputs. The `_build_approach_input` function assembles from `ctx.arsenal`, `ctx._render_platoon_section()`, `ctx._render_count_splits_section()`, and `ctx._render_first_pitch_section()` — all of which draw from live PitcherContext state. No static/hardcoded data detected in the data path.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `_build_approach_input` | `ctx.arsenal`, `ctx.platoon_mix`, `ctx.count_splits`, `ctx.first_pitch` | PitcherContext render methods | Yes | FLOWING |
| `_build_rp_workload_stub` | `ctx.workload.appearances` | PitcherContext workload field | Yes | FLOWING |
| `_build_stuff_input` delta table | `ctx.arsenal` PitchTypeSummary fields | PitcherContext arsenal list | Yes | FLOWING |
| `_build_trend_input` primary pitch appendix | `ctx.arsenal` filtered by `window_usage_pct >= 10.0` | PitcherContext arsenal list | Yes | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 97 pipeline tests pass | `uv run pytest tests/test_pipeline.py -x -q` | 97 passed, 1 warning | PASS |
| All 32 phase-24 specific tests pass | `uv run pytest tests/test_pipeline.py::TestBuildApproachInput ... -v` | 37 passed (includes TestLocationRvNoYoY class), 1 warning | PASS |
| Pre-existing test_context.py failure is not a regression | `uv run pytest tests/ -x` (non-pipeline) | 1 failure: `test_to_prompt_yoy_omits_all_steady_pitch` — confirmed pre-existing from phase 23 | PASS (not a phase-24 regression) |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PIPE-01 | 24-01-PLAN | Approach Specialist agent receives platoon mix, count splits, and first-pitch data | SATISFIED | `_build_approach_input` calls all three render methods; 6 tests in TestBuildApproachInput pass |
| PIPE-02 | 24-01-PLAN | Approach Specialist prompt prioritizes 10+ pp platoon/count-state shifts | SATISFIED | `_APPROACH_SPECIALIST_PROMPT` contains "10+" and "LEAD WITH THE BIGGEST SHIFTS"; TestApproachPrompt (4 tests) pass |
| PIPE-03 | 24-01-PLAN | Location Specialist no longer receives platoon data | SATISFIED | `_build_location_input` has no platoon render call; `test_location_input_no_platoon` passes |
| PIPE-04 | 24-01-PLAN | Game Shape specialist skipped for relievers (ctx.role == "RP") | SATISFIED | RP guard at line 761; TestRPGameShapeSkip (5 tests) pass |
| PIPE-05 | 24-02-PLAN | Stuff and Trend specialist inputs include raw data appendices | SATISFIED | Stuff: "## Raw Data (cite these exact numbers)" + "### Per-Pitch Delta Table" at lines 617-618; Trend: "### Primary Pitch Deltas (≥10% usage)" at line 728; TestStuffAppendix (6) and TestTrendAppendix (3) pass. **Note:** REQUIREMENTS.md still shows `[ ]` (unchecked) for PIPE-05 — bookkeeping artifact only, implementation is complete. |
| PIPE-06 | 24-03-PLAN | Writer input includes Approach Specialist output as 6th specialist | SATISFIED | `build_writer_input` has `approach: str` param; "Specialist Analysis 6: Approach" in output; writer prompt is a function returning "Six specialist analyses"; TestBuildWriterInput (3) and TestWriterPrompt (6) pass |
| PIPE-07 | 24-03-PLAN | Auditor runs against Approach Specialist output (6 audits), categories 8-9 added | SATISFIED | `specialist_names` has 6 entries including "approach"; `_DATA_AUDITOR_PROMPT` has categories 8 (PLATOON_CLAIM_MISMATCH) and 9 (COUNT_STATE_CLAIM_MISMATCH) with conditional framing; TestAuditorPrompt (3 tests) pass |

**Orphaned requirements check:** No additional PIPE-* requirements mapped to Phase 24 in REQUIREMENTS.md beyond PIPE-01 through PIPE-07.

**REQUIREMENTS.md bookkeeping note:** PIPE-05 shows `[ ]` (not checked) in REQUIREMENTS.md despite being fully implemented and test-covered. The status table on a later line also shows "Pending." This is a documentation-only discrepancy — it does not affect goal achievement.

---

### Anti-Patterns Found

Scan of modified files (`src/pitcher_narratives/pipeline.py`, `tests/test_pipeline.py`):

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TODO/FIXME/placeholder found | — | None |
| — | — | No empty `return null / [] / {}` in production path | — | None |
| — | — | No hardcoded empty data flowing to rendering | — | None |

No anti-patterns found. All new functions return fully computed content.

---

### Human Verification Required

None. All phase-24 goals are verifiable programmatically and all automated checks pass.

---

### Gaps Summary

No gaps. All 9 observable truths are verified, all artifacts exist and are substantive and wired, all key links confirmed present, all 97 pipeline tests pass.

The only item worth noting:
- **PIPE-05 in REQUIREMENTS.md is unchecked** (`[ ]`) despite the implementation being complete and all tests passing. This is a bookkeeping inconsistency in REQUIREMENTS.md, not a code gap. The requirement is fully satisfied.

---

_Verified: 2026-04-04T21:10:00Z_
_Verifier: Claude (gsd-verifier)_
