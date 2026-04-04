---
phase: 25-prompt-engineering-heuristic-injection
verified: 2026-04-04T22:19:06Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 25: Prompt Engineering Heuristic Injection Verification Report

**Phase Goal:** Specialist and writer prompts encode sabermetric heuristics so narratives surface trade-offs, contradictions, and causal chains instead of just restating metric directions
**Verified:** 2026-04-04T22:19:06Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Stuff Specialist prompt narrates trade-off patterns when velo and S+ move inversely | VERIFIED | `_STUFF_SPECIALIST_PROMPT` contains TRADE-OFF DETECTION + COMMON PATTERNS + INVERSE + pfx deltas at lines 155-167 |
| 2 | Location Specialist prompt narrates contradiction patterns when zone% and xWhiff diverge | VERIFIED | `_LOCATION_SPECIALIST_PROMPT` contains CONTRADICTION DETECTION + COMMON PATTERNS + expanding the zone + chase% at lines 204-212 |
| 3 | Trend Specialist prompt includes release-point vocabulary when arm angle data is present | VERIFIED | `_build_trend_prompt(ctx_with_arm_angle)` injects RELEASE POINT FRAMING section (lines 277-287) when `ctx.release_point.pitch_types` is non-empty |
| 4 | Trend Specialist prompt omits release-point vocabulary when no arm angle data exists | VERIFIED | `_build_trend_prompt(None)` returns base prompt only; confirmed programmatically: `RELEASE POINT FRAMING in None case: False` |
| 5 | Writer narrative cites physical driver for S+ changes >= 10 points | VERIFIED | `_build_writer_prompt("SP")` and `_build_writer_prompt("RP")` both contain CAUSAL HOOK REQUIREMENT with "10 or more points" and "Stuff Specialist" citation at lines 549-558 |
| 6 | Writer narrative admits uncertainty honestly when Stuff Specialist cannot explain S+ change | VERIFIED | "without an obvious physical explanation" present in writer prompt; "NEVER invent a physical cause" anti-fabrication directive present |
| 7 | Data Auditor does not flag cited inverse/zone-expansion claims as hallucination | VERIFIED | `_DATA_AUDITOR_PROMPT` contains ALLOWED HEURISTIC PATTERNS with INVERSE CORRELATION, ZONE EXPANSION, APPROACH ANGLE whitelisted (lines 420-435) |
| 8 | Data Auditor still flags uncited heuristic claims as HALLUCINATED_CAUSATION | VERIFIED | Whitelist is evidence-gated: "ONLY when evidence is cited. Pattern recognition alone...is still a category 5 violation" |
| 9 | Location Specialist input shows zone_rate, xWhiff_P, and chase_rate on the same line per pitch type | VERIFIED | `_build_location_input` restructured to per-pitch-type unified view with Zone%, xWhiff_P, Chase% adjacent (line 757-761); old section headers (P vs S Location Impact, Execution Metrics) removed |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/pipeline.py` | TRADE-OFF DETECTION in `_STUFF_SPECIALIST_PROMPT` | VERIFIED | Line 155: `TRADE-OFF DETECTION:` |
| `src/pitcher_narratives/pipeline.py` | CONTRADICTION DETECTION in `_LOCATION_SPECIALIST_PROMPT` | VERIFIED | Line 204: `CONTRADICTION DETECTION:` |
| `src/pitcher_narratives/pipeline.py` | `_build_trend_prompt` function (not constant) | VERIFIED | Line 247: `def _build_trend_prompt(ctx: PitcherContext | None = None) -> str:` |
| `src/pitcher_narratives/pipeline.py` | No `_TREND_SPECIALIST_PROMPT =` constant | VERIFIED | grep returns 0 matches — constant fully removed |
| `src/pitcher_narratives/pipeline.py` | CAUSAL HOOK REQUIREMENT in `_build_writer_prompt()` | VERIFIED | Line 549: inside `_build_writer_prompt` function (defined at 469) |
| `src/pitcher_narratives/pipeline.py` | ALLOWED HEURISTIC PATTERNS in `_DATA_AUDITOR_PROMPT` | VERIFIED | Line 420; whitelist index 2346 < output format index 3144 (placement correct) |
| `src/pitcher_narratives/pipeline.py` | Restructured `_build_location_input` with unified view | VERIFIED | Line 746: `"## Location Analysis by Pitch Type"`; exec_lookup at line 733 |
| `tests/test_pipeline.py` | `TestStuffPromptHeuristics` class | VERIFIED | Line 1303 |
| `tests/test_pipeline.py` | `TestLocationPromptHeuristics` class | VERIFIED | Line 1323 |
| `tests/test_pipeline.py` | `TestTrendPromptFunction` class | VERIFIED | Line 1339 |
| `tests/test_pipeline.py` | `TestMakePipelineAgentsCtx` class | VERIFIED | Line 1372 |
| `tests/test_pipeline.py` | `TestWriterPromptCausalHook` class | VERIFIED | Line 1388 |
| `tests/test_pipeline.py` | `TestAuditorWhitelist` class | VERIFIED | Line 1422 |
| `tests/test_pipeline.py` | `TestLocationInputAdjacency` class | VERIFIED | Line 1595 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_build_trend_prompt` | `make_pipeline_agents` | `trends=_specialist(_build_trend_prompt(ctx))` | WIRED | Line 1278: function called with ctx |
| `_build_trend_prompt` | `write_pipeline_data_file` | tuple in specialist_phases list | WIRED | Line 1148: `_build_trend_prompt(ctx)` in data file |
| `_run_pipeline` | `make_pipeline_agents` | `ctx=ctx` kwarg | WIRED | Line 1350: `make_pipeline_agents(provider, thinking, role=ctx.role, ctx=ctx)` |
| `_DATA_AUDITOR_PROMPT` | ALLOWED HEURISTIC PATTERNS placement | before "For each problem found" | WIRED | Index 2346 < 3144 confirmed programmatically |
| `_build_location_input` | Location Specialist agent | passed via `run_specialists` | WIRED | Referenced in specialist_phases list at line 1146 |

### Data-Flow Trace (Level 4)

Not applicable — all phase 25 artifacts are prompt strings and input builder functions, not components rendering dynamic state from a data store. The data flows through LLM calls at runtime, not through a data pipeline that can be statically traced.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `_build_trend_prompt(None)` excludes release-point vocabulary | Python inline | RELEASE POINT FRAMING: False, trend analyst: True | PASS |
| `_build_writer_prompt` includes all 6 causal hook markers for SP and RP | Python inline | All 6 checks PASS | PASS |
| Auditor whitelist appears before output format | Python inline | index 2346 < 3144 | PASS |
| Full test suite (132 tests) | `uv run python -m pytest tests/test_pipeline.py` | 132 passed, 1 warning | PASS |
| Phase-25 test classes (35 tests) | `uv run python -m pytest -k "TestStuffPrompt...TestLocationInputAdjacency"` | 35 passed, 97 deselected | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PROMPT-01 | 25-01-PLAN | Stuff Specialist prompt includes trade-off detection directive | SATISFIED | TRADE-OFF DETECTION + INVERSE + pfx deltas at lines 155-167 |
| PROMPT-02 | 25-01-PLAN | Location Specialist prompt includes contradiction detection directive | SATISFIED | CONTRADICTION DETECTION + expanding the zone + chase% at lines 204-212 |
| PROMPT-03 | 25-01-PLAN | Trend Specialist prompt includes conditional release-point framing | SATISFIED | `_build_trend_prompt` function with arm-slot/tunneling vocabulary gated on pitch_types presence |
| PROMPT-04 | 25-02-PLAN | Writer prompt includes causal hook requirement (S+ change >= 10 pts) | SATISFIED | CAUSAL HOOK REQUIREMENT with 10-point threshold, Stuff Specialist citation, honest fallback |
| PROMPT-05 | 25-02-PLAN | Data Auditor prompt whitelists sabermetric heuristics | SATISFIED | ALLOWED HEURISTIC PATTERNS with INVERSE CORRELATION, ZONE EXPANSION, APPROACH ANGLE; evidence-gated |
| PROMPT-06 | 25-03-PLAN | Location Specialist input places xWhiff and zone_rate adjacent | SATISFIED | `_build_location_input` unified view with Zone%, xWhiff_P, Chase% on same line per pitch type |

No orphaned requirements — all 6 PROMPT-* requirements declared in REQUIREMENTS.md are mapped to plans in this phase and verified as implemented.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pipeline.py` | 1157 | Comment: "placeholder since specialist output isn't known yet" | Info | Design comment, not a stub — refers to the data file audit section which correctly uses `[specialist output goes here]` as a visual template marker |
| `tests/test_pipeline.py` | 1651 | Comment: "# Missing data should show placeholder" | Info | Test comment explaining test intent, not a code stub |

No blockers or warnings found.

### Human Verification Required

The following items cannot be verified programmatically:

#### 1. Narrative Quality of Heuristic Application

**Test:** Run the full pipeline on a pitcher with a known velo-down/S+-up profile (e.g., a knuckle-curve specialist). Read the Stuff Specialist output.
**Expected:** The narrative identifies the inverse relationship and cites specific pfx deltas as the compensating factor, not just restating the metric directions.
**Why human:** LLM output quality cannot be asserted in tests; tests only verify the directive text exists in the prompt, not that the LLM follows it correctly.

#### 2. Auditor Whitelist Effectiveness

**Test:** Generate a narrative where the Stuff Specialist correctly analyzes velo-down/S+-up with pfx delta citation. Confirm the Auditor does not flag it as HALLUCINATED_CAUSATION.
**Expected:** Auditor returns clean (no flags) for cited inverse correlation claims.
**Why human:** Requires live LLM call with actual specialist output to observe auditor behavior.

#### 3. Location Input Contradiction Detection in Practice

**Test:** Run pipeline on a pitcher with low zone% + high xWhiff. Verify the Location Specialist output references "zone expansion" or "expanding the zone" and cites chase%.
**Expected:** Location Specialist narrates the contradiction pattern using the adjacent metrics in the restructured input.
**Why human:** Requires live data and LLM run to verify the adjacency restructuring actually improves contradiction detection in output.

### Gaps Summary

No gaps. All 9 truths verified, all 14 artifacts confirmed (exists + substantive + wired), all 5 key links confirmed. 132 tests pass with no regressions. All 6 PROMPT-* requirements satisfied with implementation evidence.

---

_Verified: 2026-04-04T22:19:06Z_
_Verifier: Claude (gsd-verifier)_
