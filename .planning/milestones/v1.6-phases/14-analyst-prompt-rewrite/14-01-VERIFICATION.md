---
phase: 14-analyst-prompt-rewrite
verified: 2026-03-31T22:30:00Z
status: human_needed
score: 4/4 must-haves verified
human_verification:
  - test: "Run `pitcher-ask 'How is [pitcher]s slider?' --provider openai` against a real pitcher (e.g., pitcher ID 592155)"
    expected: "Response should open with an intermediate probability signal (xWhiff, xSwing, xSwSt, or xRV100), not a plus grade. Should include a P-vs-S delta in the body. Should reference the dominant attribution outcome class. Should close with P+/S+/L+ as summary grades."
    why_human: "LLM output quality is non-deterministic. String-content tests verify the prompt teaches the right reasoning, but only live inference can confirm the agent actually uses those instructions to produce model-internals-first prose rather than reverting to plus-score-centric answers."
  - test: "Ask a follow-up: 'What does location add to his slider?'"
    expected: "Response should cite a P-variant vs S-variant delta numerically (e.g., 'location adds N pp of whiff rate') and characterize whether command is a net positive or negative for the pitch."
    why_human: "P-vs-S diagnostic behavior requires live tool call with real data; the TestModel in automated tests returns a stub string that does not exercise the reasoning chain."
  - test: "Ask: 'What is the dominant run-value driver for his fastball?'"
    expected: "Response should identify 2-3 specific outcome contributions from the attribution table (e.g., whiffs, ground outs, home runs) rather than listing all 13. Should frame them in terms of runs saved or cost per 100 pitches."
    why_human: "Attribution filtering behavior ('find 2-3 outcomes') is a qualitative reasoning instruction; automated tests verify the instruction exists in the prompt but cannot verify the LLM follows it correctly."
---

# Phase 14: Analyst Prompt Rewrite Verification Report

**Phase Goal:** The analyst reasons from model internals -- diagnosing pitch quality through outcome probabilities and component attribution rather than citing opaque plus grades
**Verified:** 2026-03-31T22:30:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Analyst explains WHY a pitch scores well or poorly using intermediate probabilities (xWhiff, xSwing, xSwSt, xRV100) | VERIFIED | All 4 metric names appear in _ANALYST_INSTRUCTIONS (lines 100-101, 120-123, 131-133); test_prompt_references_intermediates passes |
| 2 | Analyst diagnoses location impact by comparing P-variant vs S-variant probabilities | VERIFIED | "P-variant" and "S-variant" appear at lines 104-105; "location" appears throughout; test_prompt_references_p_vs_s passes |
| 3 | Analyst identifies the dominant run-value driver from component attribution | VERIFIED | "attribution" at lines 98, 109; "dominant" at line 109; "2-3" at line 111; test_prompt_references_attribution passes |
| 4 | Plus scores (P+/S+/L+) still appear as summary grades, not removed | VERIFIED | "Summarize with plus scores" section at line 115; "summary grades" at lines 116, 147; "Pitching+ triad" NOT present; test_prompt_internals_before_plus passes |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pitcher_narratives/analyst.py` | Rewritten _ANALYST_INSTRUCTIONS with model-internals-first reasoning | VERIFIED | Contains "ANALYTICAL FRAMEWORK (Model Internals)" (line 96), all 4 metric names, P-variant/S-variant, attribution, sign conventions, 3-step diagnostic approach; prompt is ~86 lines including surrounding scaffolding, 46-line prompt body |
| `tests/test_analyst.py` | String-content tests verifying prompt contains correct concepts | VERIFIED | All 4 test functions present (lines 273-325): test_prompt_references_intermediates, test_prompt_internals_before_plus, test_prompt_references_p_vs_s, test_prompt_references_attribution |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/pitcher_narratives/analyst.py` | `_analyst_agent` | `instructions=_ANALYST_INSTRUCTIONS` | VERIFIED | Line 187 confirms `instructions=_ANALYST_INSTRUCTIONS` in Agent() constructor; `_analyst_agent._instructions[0]` is a non-empty string confirmed by test_agent_uses_instructions_not_system_prompt |

### Data-Flow Trace (Level 4)

Not applicable. This phase changes a string constant (`_ANALYST_INSTRUCTIONS`) that is an LLM system prompt. There is no runtime data flow to trace -- the "data" is the prompt text itself, verified by string-content tests.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 19 analyst tests pass (new + existing) | `uv run pytest tests/test_analyst.py -x` | 19 passed, 1 warning | PASS |
| Full suite passes (265 tests) | `uv run pytest tests/ -x` | 265 passed, 1 warning in 19.88s | PASS |
| 4 new ANLST tests pass individually | `uv run pytest tests/test_analyst.py -v -k "test_prompt"` | 4/4 passed | PASS |
| "Pitching+ triad" removed | `grep "Pitching+ triad" src/pitcher_narratives/analyst.py` | 0 matches | PASS |
| "summary" in plus-score context | `grep "summary" src/pitcher_narratives/analyst.py` | 4 matches (lines 116, 147, 193, 303) | PASS |
| intermediate metrics present | `grep -c "xWhiff|xSwing|xSwSt|xRV100" src/pitcher_narratives/analyst.py` | 21 matches | PASS |
| Both commit hashes exist | `git log --oneline 7be525e 3ecf57a` | Both present and correctly described | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ANLST-01 | 14-01-PLAN.md | Analyst system prompt frames reasoning around model internals (outcome probabilities, component attribution) rather than opaque plus grades | SATISFIED | _ANALYST_INSTRUCTIONS leads with 4-step framework starting from intermediate probabilities; "Pitching+ triad" removed; test_prompt_references_intermediates + test_prompt_internals_before_plus both pass |
| ANLST-02 | 14-01-PLAN.md | Analyst diagnoses location impact by comparing P-variant vs S-variant probabilities | SATISFIED | "P-variant (stuff + location) vs S-variant (stuff only)" at lines 104-105; concrete example at line 106-107; test_prompt_references_p_vs_s passes |
| ANLST-03 | 14-01-PLAN.md | Analyst identifies which outcome class is the dominant run-value driver for a given pitch type | SATISFIED | "dominant run-value driver from the component attribution table" at line 109; "2-3 outcomes contributing the most" at line 111; test_prompt_references_attribution passes |

**Orphaned requirements check:** REQUIREMENTS.md traceability table lists only ANLST-01, ANLST-02, ANLST-03 for Phase 14. All three are claimed in the PLAN frontmatter. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | -- | -- | -- | -- |

No TODOs, FIXMEs, placeholder returns, or hardcoded empty values found in the modified files. The prompt constant is fully written and wired; the test functions are substantive string assertions, not stubs.

### Human Verification Required

#### 1. Live inference: model-internals-first response style

**Test:** Run `pitcher-ask "How is [pitcher]'s slider?" --provider openai` for a pitcher with slider data (e.g., Cam Booser, ID 592155).
**Expected:** Response opens with an intermediate probability signal (xWhiff, xSwing, xSwSt, or xRV100 value), not a plus grade. Body includes a P-vs-S delta framed as a location contribution. Identifies the dominant attribution outcome class. Closes with P+/S+/L+ as summary grades.
**Why human:** LLM output is non-deterministic. String-content tests verify the prompt teaches the right reasoning but cannot confirm the model applies it in practice.

#### 2. P-vs-S location diagnosis in prose

**Test:** Ask `pitcher-ask "What does location add to his slider?" --provider openai`.
**Expected:** Response cites a P-variant vs S-variant delta numerically (e.g., "location adds 13 percentage points of whiff rate") and characterizes whether command is a net positive or negative for the pitch.
**Why human:** P-vs-S diagnostic behavior requires live tool call with real data. TestModel in automated tests returns a stub string that does not exercise the 3-step reasoning chain.

#### 3. Attribution dominant-driver filtering

**Test:** Ask `pitcher-ask "What is the dominant run-value driver for his fastball?" --provider openai`.
**Expected:** Response identifies 2-3 specific outcome contributions from the attribution table rather than listing all 13. Frames them as runs saved or cost per 100 pitches.
**Why human:** Filtering behavior ("find 2-3 outcomes, not all 13") is a qualitative reasoning instruction. Automated tests verify the instruction is present in the prompt but cannot verify the LLM follows it correctly under live inference.

### Gaps Summary

No automated gaps. All 4 must-have truths are verified, both artifacts are substantive and wired, the key link is confirmed, all 265 tests pass, and all 3 requirements (ANLST-01, ANLST-02, ANLST-03) are satisfied by code evidence.

The `human_needed` status reflects the nature of the final deliverable: a system prompt that teaches LLM reasoning. Automated tests can only verify that the instructions contain the required concepts -- they cannot verify that a live LLM model actually reasons the way the prompt intends. Human validation requires running `pitcher-ask` against a real pitcher with a live LLM provider.

---

_Verified: 2026-03-31T22:30:00Z_
_Verifier: Claude (gsd-verifier)_
