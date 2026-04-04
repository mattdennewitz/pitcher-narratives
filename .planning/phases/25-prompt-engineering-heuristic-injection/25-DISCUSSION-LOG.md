# Phase 25: Prompt Engineering & Heuristic Injection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 25-prompt-engineering-heuristic-injection
**Areas discussed:** Trade-off & contradiction heuristics, Release-point vocabulary, Writer causal hook, Auditor whitelist scope

---

## Trade-off & Contradiction Heuristics

### Q1: How explicit should the trade-off/contradiction pattern directives be?

| Option | Description | Selected |
|--------|-------------|----------|
| Enumerated patterns | List specific metric pairs in the prompt (velo down + S+ up, etc.) | |
| Principle-based | Describe the heuristic principle, let LLM find instances | |
| Hybrid | State principle first, then 1-2 concrete examples as illustration | ✓ |

**User's choice:** Hybrid — with a specific structure: PRINCIPLE block stating the sabermetric reality, followed by COMMON PATTERNS with enumerated examples. User provided exact prompt structure to follow.
**Notes:** User emphasized this locks the agent into sabermetric reality while giving flexibility to read actual data. Asked about edge cases (dropped pitches) — already handled by Trend Specialist via Phase 21 arsenal trend engine.

### Q2: Location contradiction — layout change, prompt directive, or both?

| Option | Description | Selected |
|--------|-------------|----------|
| Layout change + prompt directive | Move xWhiff/zone_rate adjacent AND add contradiction directive | ✓ |
| Prompt directive only | Keep current layout, add directive | |
| Layout change only | Move data adjacent, no directive | |

**User's choice:** Layout change + prompt directive (both angles)
**Notes:** User explained the physics: LLM self-attention mechanisms attend more strongly to adjacent tokens. Spatial locality of data + behavioral directive = "virtually eliminate the chance the Location Specialist misses the command strategy." Asked about Writer synthesis — confirmed existing _build_writer_prompt() handles this; Phase 25 only adds the causal hook.

---

## Release-Point Vocabulary

### Q3: How should the Trend Specialist use release-point framing vocabulary?

| Option | Description | Selected |
|--------|-------------|----------|
| Vocabulary glossary in prompt | Add RELEASE POINT FRAMING section mapping arm angle data to scouting vocabulary | ✓ |
| Conditional prompt block | Only include vocabulary when arm angle data present | |
| Embedded in existing rules | Weave into existing Trend prompt rules | |

**User's choice:** Vocabulary glossary — but with conditional injection at the Python level (borrowing from Option 2)
**Notes:** User recommended handling the conditional logic in Python (like _build_writer_prompt) rather than the LLM prompt. "Saves tokens and removes an unnecessary conditional branch for the LLM to evaluate." Result: new _build_trend_prompt(ctx) function that includes glossary only when arm angle data exists.

---

## Writer Causal Hook

### Q4: How strict should the S+ causal hook requirement be?

| Option | Description | Selected |
|--------|-------------|----------|
| Must-cite with fallback | Writer MUST cite physical driver; if Stuff Specialist didn't explain, say so honestly | ✓ |
| Soft nudge | Writer SHOULD cite when available, can omit for flow | |
| Threshold-gated injection | Python pre-scans for S+ deltas, injects directive conditionally | |

**User's choice:** Must-cite with fallback
**Notes:** Honest fallback ("S+ moved N points without an obvious physical explanation") preserves intellectual honesty.

### Q5: Should the 10-point threshold be hardcoded or dynamically injected?

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded in prompt | Static "≥10 points" rule, writer identifies pitches itself | ✓ |
| Python pre-scan + injection | Code scans ctx.arsenal, injects specific pitch names crossing threshold | |

**User's choice:** Hardcoded in prompt — simpler, writer already has all S+ data.

---

## Auditor Whitelist Scope

### Q6: How should the auditor whitelist sabermetric heuristics?

| Option | Description | Selected |
|--------|-------------|----------|
| Enumerated exception list | ALLOWED HEURISTIC PATTERNS section listing specific whitelisted patterns | ✓ |
| Category modification | Modify HALLUCINATED_CAUSATION category to carve out exceptions | |
| Separate audit pass | Post-process flags in Python to remove false positives | |

**User's choice:** Enumerated exception list with 3 patterns (inverse correlation, zone expansion, approach angle)
**Notes:** User recommended placing the whitelist block immediately before output format instructions (recency effect — LLM weighs end-of-prompt tokens heavily). Key rule: heuristic valid ONLY when specialist cites supporting metrics. Asked about fallback mechanism — existing Phase 16 audit revision loop handles flagged output (specialist gets revision pass).

---

## Claude's Discretion

- Exact wording of heuristic principle statements
- Location input restructuring column order and formatting
- Whether _build_trend_prompt() is new function or refactors existing constant

## Deferred Ideas

- Height-normalized arm angle (carried from Phase 23 D-07a) — requires pitcher height data not in Statcast
