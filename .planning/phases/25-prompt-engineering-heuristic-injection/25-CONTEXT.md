# Phase 25: Prompt Engineering & Heuristic Injection - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Specialist and writer prompts encode sabermetric heuristics so narratives surface trade-offs, contradictions, and causal chains instead of just restating metric directions. This phase modifies prompt text and one input builder layout — no new engine computation, no new agents, no pipeline re-architecture.

</domain>

<decisions>
## Implementation Decisions

### Stuff Specialist Trade-off Detection (PROMPT-01)
- **D-01:** Hybrid structure — state the governing sabermetric principle first, then enumerate common patterns as grounding examples. Format:
  - TRADE-OFF DETECTION (PRINCIPLE): "Stuff+ evaluates the holistic pitch. Whenever you see an INVERSE relationship between raw physical metrics (velocity/movement) and the S+ grade, your primary goal is to narrate the contradiction by finding the compensating factor in the data."
  - COMMON PATTERNS: velo down + S+ up → movement/spin compensation (cite pfx deltas); velo up + S+ down → lost movement/dead zone shape (cite movement deltas); movement change + stable S+ → shape adaptation maintaining effectiveness.
- **D-02:** This hybrid pattern (principle + enumerated examples) is the standard template for ALL heuristic directives in this phase. Apply consistently to PROMPT-01, PROMPT-02, and PROMPT-03.

### Location Specialist Contradiction Detection (PROMPT-02)
- **D-03:** Same hybrid structure as D-01. CONTRADICTION DETECTION (PRINCIPLE): "Location metrics can appear contradictory when a pitcher is expanding the zone. Narrate these — they reveal command strategy." COMMON PATTERNS: low zone% + high xWhiff → expanding zone, getting chases (cite chase% to confirm); high zone% + low xWhiff → in the zone but predictable (cite xSwing to check).
- **D-04:** PROMPT-06 implemented as BOTH a data layout change and a prompt directive. `_build_location_input()` restructured so zone_rate, xWhiff_P, and chase_rate appear adjacent per pitch type (not separated across sections). Rationale: token adjacency improves LLM attention across related metrics; the directive injects the scouting intelligence to interpret the pattern.

### Trend Specialist Release-Point Vocabulary (PROMPT-03)
- **D-05:** Vocabulary glossary injected conditionally at the Python level — NOT a static part of the prompt. `_build_trend_prompt()` function (new, similar to `_build_writer_prompt()`) includes the RELEASE POINT FRAMING block only when ctx has arm angle data. If no arm angle data exists, the Trend Specialist prompt stays as-is with no mention of release-point vocabulary. Saves tokens and removes an unnecessary conditional branch for the LLM.
- **D-06:** Vocabulary glossary content: arm slot → "delivery angle" or "arm slot"; slot shift → mechanical adjustment ("dropped down", "came over the top"); different arm angles across pitch types = tunneling advantage; overhand = steeper approach, sidearm = more horizontal plane. Explicit anti-speculation directive: "Do NOT speculate on mechanical causes (injury, fatigue) — only describe what the data shows."

### Writer Causal Hook (PROMPT-04)
- **D-07:** Must-cite with honest fallback. When ANY pitch shows S+ change ≥10 points (window vs season), the writer MUST cite the physical driver from the Stuff Specialist's analysis. If the Stuff Specialist could not explain the change, the writer says so honestly rather than inventing a cause. "NEVER invent a physical cause that the Stuff Specialist did not identify."
- **D-08:** 10-point S+ threshold hardcoded as a static rule in the writer prompt text. The writer identifies which pitches cross the threshold from the specialist inputs it already receives. No Python pre-scanning or dynamic injection needed.
- **D-09:** Causal hook directive added to `_build_writer_prompt()` as a new section (CAUSAL HOOK REQUIREMENT), following the existing CRITICAL/STRUCTURE/VOICE/CONSTRAINTS sections.

### Data Auditor Whitelist (PROMPT-05)
- **D-10:** Enumerated exception list as an ALLOWED HEURISTIC PATTERNS section in the auditor prompt. Three whitelisted patterns:
  1. INVERSE CORRELATION: velo/movement vs S+ — valid if pfx deltas cited
  2. ZONE EXPANSION: low zone% + high xWhiff — valid if chase% cited as confirming evidence
  3. APPROACH ANGLE: arm angle → deception/tunneling — valid if arm angle data present in input
- **D-11:** Key rule: a heuristic is valid ONLY when the specialist cites the specific metrics that support it. An uncited heuristic claim is still HALLUCINATED_CAUSATION (category 5). The whitelist gates on evidence, not on pattern recognition alone.
- **D-12:** Whitelist block placed immediately before the output format instructions in the auditor prompt (recency effect — LLM weighs end-of-prompt tokens heavily, ensuring the exceptions are checked before generating pass/fail output).

### Claude's Discretion
- Exact wording of each heuristic principle statement (beyond the structure and content captured above)
- How the Location Specialist input restructuring groups zone_rate/xWhiff/chase_rate (column order, formatting)
- Whether `_build_trend_prompt()` is a new function or refactors the existing constant (function preferred per D-05 pattern)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — PROMPT-01 through PROMPT-06 define the six deliverables for this phase

### Specialist Prompts (modification targets)
- `src/pitcher_narratives/pipeline.py` §81-153 — `_STUFF_SPECIALIST_PROMPT` (add trade-off detection directive)
- `src/pitcher_narratives/pipeline.py` §155-188 — `_LOCATION_SPECIALIST_PROMPT` (add contradiction detection directive)
- `src/pitcher_narratives/pipeline.py` §223-246 — `_TREND_SPECIALIST_PROMPT` (convert to function with conditional release-point vocabulary)
- `src/pitcher_narratives/pipeline.py` §325-382 — `_DATA_AUDITOR_PROMPT` (add allowed heuristic patterns section before output format)
- `src/pitcher_narratives/pipeline.py` §409-487 — `_build_writer_prompt()` (add causal hook requirement section)

### Input Builder (layout change target)
- `src/pitcher_narratives/pipeline.py` §650-684 — `_build_location_input()` (restructure to place zone_rate, xWhiff_P, chase_rate adjacent)

### Prior Phase Context
- `.planning/phases/23-engine-foundation-data-enrichment/23-CONTEXT.md` — D-05 through D-07a (arm angle computation details, conditional availability)
- `.planning/phases/24-pipeline-re-architecture/24-CONTEXT.md` — D-08 (anti-recalculation directive pattern), D-12/D-13 (auditor category structure)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_build_writer_prompt(role)` at pipeline.py:409 — pattern for dynamic prompt construction with conditional sections. Reuse for `_build_trend_prompt(ctx)`.
- Anti-recalculation directive already in Stuff prompt (lines 149-153) — established pattern for "do not recompute" instructions.
- Auditor categories 8-9 already use conditional framing ("apply ONLY when") — pattern for the whitelist section.
- `_build_location_input()` at pipeline.py:650 — current structure has P vs S section and Execution Metrics section separated. Both sections iterate over `ctx.intermediates` and `ctx.execution` respectively.

### Established Patterns
- Specialist prompts are module-level string constants (except writer which is a function)
- All prompt directives use UPPERCASE SECTION HEADERS with explanation below
- Interpretation rules use enumerated patterns with specific metric names
- Conditional prompt content uses Python string building, not LLM-side conditionals

### Integration Points
- `_STUFF_SPECIALIST_PROMPT` — append trade-off detection section
- `_LOCATION_SPECIALIST_PROMPT` — append contradiction detection section
- `_TREND_SPECIALIST_PROMPT` → `_build_trend_prompt(ctx)` — convert constant to function
- `_DATA_AUDITOR_PROMPT` — insert whitelist before output format
- `_build_writer_prompt()` — append causal hook section
- `_build_location_input()` — restructure data layout
- `run_specialists()` at pipeline.py:1172 — update trend specialist to use function instead of constant

</code_context>

<specifics>
## Specific Ideas

- Hybrid structure (principle + enumerated examples) is the standard template for all heuristic directives — establishes a design pattern: governing sabermetric principle handles edge cases, enumerated examples ground the logic
- Python-level conditional injection for release-point vocabulary mirrors the `_build_writer_prompt()` pattern — the LLM never processes conditional branches about data it doesn't have
- Whitelist placement before output format instructions exploits LLM recency effect — tokens at prompt boundaries receive higher attention weight
- Location input restructuring exploits LLM token adjacency — metrics that need cross-referencing are grouped spatially, not just mentioned in a directive
- The fallback "S+ moved N points without an obvious physical explanation" preserves intellectual honesty — the system admits uncertainty rather than fabricating causation

</specifics>

<deferred>
## Deferred Ideas

- **Height-normalized arm angle** — Carried forward from Phase 23 D-07a. Normalize release_z against pitcher height to isolate arm slot from stature. Requires pitcher height data not currently in Statcast parquet. Raw atan2 sufficient for now.

</deferred>

---

*Phase: 25-prompt-engineering-heuristic-injection*
*Context gathered: 2026-04-04*
