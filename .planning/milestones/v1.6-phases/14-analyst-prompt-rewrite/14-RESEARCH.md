# Phase 14: Analyst Prompt Rewrite - Research

**Researched:** 2026-03-31
**Domain:** LLM system prompt engineering for baseball analytics agent
**Confidence:** HIGH

## Summary

Phase 14 is a pure prompt rewrite with no structural code changes. The `_ANALYST_INSTRUCTIONS` string constant in `analyst.py` (lines 91-150) must be replaced with new instructions that shift the analytical framework from opaque plus grades to model-internal reasoning. The data infrastructure is already complete: Phase 11 added intermediate probabilities (P/S variants), Phase 12 added component attribution (13-outcome xRV decomposition), and Phase 13 wired both into the tools' output. The LLM already receives this data -- it just lacks instructions on how to use it.

The rewrite is surgical: one string constant (`_ANALYST_INSTRUCTIONS`) changes, everything else stays. The current prompt's "ANALYTICAL FRAMEWORK" and "DIAGNOSTIC APPROACH" sections (lines 98-123) are the primary targets. The new prompt must teach the agent three new reasoning patterns: (1) explain pitch quality through intermediate probabilities like xWhiff and xSwing rather than just citing P+, (2) diagnose location impact by comparing P-variant vs S-variant numbers, and (3) identify the dominant run-value driver from the attribution table. Plus scores remain as summary anchors, but the explanation layer shifts to model internals.

**Primary recommendation:** Replace `_ANALYST_INSTRUCTIONS` with a prompt that defines three explicit reasoning patterns (intermediates-first, P-vs-S delta diagnosis, attribution decomposition) while keeping the existing data grounding rules, response format, and out-of-scope guardrails intact.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ANLST-01 | Analyst system prompt frames reasoning around model internals (outcome probabilities, component attribution) rather than opaque plus grades | New "ANALYTICAL FRAMEWORK" section replacing plus-grade-centric framing with intermediates-first reasoning. Plus scores become summary anchors, not the primary lens. |
| ANLST-02 | Analyst diagnoses location impact by comparing P-variant vs S-variant probabilities | New "LOCATION DIAGNOSIS" section teaching the agent the P-vs-S comparison pattern with concrete examples. Data already in tools from Phase 13. |
| ANLST-03 | Analyst identifies which outcome class is the dominant run-value driver for a given pitch type | New "ATTRIBUTION ANALYSIS" section teaching the agent to read the 13-outcome contribution table and identify dominant drivers. Data already in tools from Phase 13. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Python version**: 3.14+
- **Code style**: snake_case modules, PascalCase classes, Google-style docstrings, absolute imports
- **No `.env` in git**, API keys via environment variables
- **GSD workflow**: Changes go through GSD commands

## Standard Stack

No new dependencies. This phase modifies one string constant in an existing module.

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-ai | 1.72.0 | Agent framework | Already powers the analyst agent |

No `npm install` or `pip install` needed.

## Architecture Patterns

### Prompt Structure Pattern (from existing codebase)

The project uses a consistent prompt structure across all agents:

1. **Role definition** -- one opening sentence establishing voice/persona
2. **Analytical framework** -- the primary lens the agent uses to interpret data
3. **Diagnostic approach** -- how to decompose and explain observations
4. **Data grounding rules** -- absolute constraints on data usage
5. **Response format** -- output structure expectations
6. **Out of scope** -- what to decline

The current `_ANALYST_INSTRUCTIONS` follows this exact structure. The rewrite MUST preserve sections 1, 4, 5, and 6 unchanged (or with minimal edits) and rewrite sections 2 and 3.

### Current Prompt Sections to KEEP (verbatim or near-verbatim)
- **Lines 92-97**: Voice definition ("analytical baseball scout... pragmatic, specific, grounded")
- **Lines 125-134**: DATA GROUNDING RULES (absolute -- never cite training data)
- **Lines 136-149**: RESPONSE FORMAT (paragraph structure, cite numbers in prose)
- **Lines 144-150**: OUT OF SCOPE (decline gracefully)

### Current Prompt Sections to REWRITE
- **Lines 98-108**: ANALYTICAL FRAMEWORK -- currently "Pitching+ triad" (S+/L+/P+). Replace with model-internals-first reasoning where intermediates (xSwing, xWhiff, xSwSt, xRV100) and attribution (13-outcome decomposition) are the primary analytical tools. Plus scores become summary grades.
- **Lines 109-123**: DIAGNOSTIC APPROACH -- currently "bad stuff + good command" pattern using S+/L+. Replace with three specific diagnostic patterns:
  1. **Intermediates diagnosis**: Explain why a pitch works using probability metrics
  2. **P-vs-S location impact**: Compare P-variant and S-variant to isolate what location does
  3. **Attribution decomposition**: Identify which outcomes drive the overall run value

### Data Available to the Agent

The agent receives data through two tools. The prompt must teach interpretation of all data sections.

**From `get_pitcher_summary` (via `to_prompt()`):**
- Arsenal table: pitch types with P+/S+/L+ scores and deltas
- Execution table: CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 percentile
- Model Internals table: xSwing S, xWhiff S, xSwSt S, xRV100 S values + P-minus-S deltas (in percentage points or run value units)
- Plus: fastball, TTO, platoon, release point, hard-hit, workload sections

**From `get_pitch_detail` (per pitch type):**
- Arsenal: P+/S+/L+ with deltas
- Execution: CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 percentile
- Model Internals: Location Impact -- P vs S for xSwing, xWhiff, xSwSt, xRV100 with deltas
- Component Attribution: 13-row table with outcome name, contribution value, and share percentage

### Metric Semantics (CRITICAL for prompt accuracy)

The prompt must teach these concepts correctly:

| Metric | What it measures | Scale | Direction |
|--------|-----------------|-------|-----------|
| xSwing | Expected swing rate | 0-1 (displayed as %) | Higher = more swings induced |
| xWhiff | Expected whiff rate (given swing) | 0-1 (displayed as %) | Higher = more misses |
| xSwSt | Expected swinging strike rate | 0-1 (displayed as %) | Higher = more K potential |
| xRV100 | Expected run value per 100 pitches | runs (negative = pitcher-favorable) | Lower/more negative = better for pitcher |
| P-variant | Full model prediction (stuff + location) | Same as base metric | Combined effect |
| S-variant | Stuff-only prediction (no location) | Same as base metric | Isolated physical quality |
| P minus S | Location impact | Same units | Positive delta = location helps (for whiff/swing metrics); sign interpretation varies by metric |
| Attribution contribution | Outcome's share of total xRV100 | runs per 100 pitches | Negative = pitcher benefits from this outcome |

**Sign convention for P-vs-S deltas:**
- xSwing: P > S means location induces MORE swings (can be good or bad depending on context)
- xWhiff: P > S means location increases whiff rate (good for pitcher)
- xSwSt: P > S means location increases swinging strike rate (good for pitcher)
- xRV100: P < S means location makes xRV more negative/pitcher-favorable (good for pitcher)

The prompt must encode these sign interpretations so the LLM doesn't misread deltas.

### Anti-Patterns to Avoid

- **Don't remove plus scores entirely.** Requirements explicitly state P+/S+/L+ remain as summary grades. The shift is from "lead with plus, explain later" to "lead with internals, summarize with plus."
- **Don't over-specify examples.** The prompt should teach the reasoning pattern, not give so many examples that the agent parrots them. 1-2 examples per pattern is sufficient.
- **Don't introduce new data expectations.** The prompt must only reference data the tools actually return. No referencing league averages, percentiles not in the data, or fields that don't exist.
- **Don't make the prompt token-heavy.** The current prompt is ~60 lines. The new one should be similar length. Longer prompts waste tokens on every API call.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Metric sign interpretation | Hardcoded explanations in tool output | Teach in prompt | The LLM needs to reason about direction, not just read pre-computed labels |
| Example responses | Pre-built few-shot examples | Pattern description with 1-2 inline examples | Few-shot eats tokens on every call; pattern description is more flexible |

## Common Pitfalls

### Pitfall 1: Sign Confusion in P-vs-S Deltas
**What goes wrong:** The LLM misinterprets whether a positive delta is good or bad because different metrics have different favorable directions.
**Why it happens:** xRV100 is pitcher-favorable when negative, but xWhiff is pitcher-favorable when positive. A naive "bigger is better" instruction leads to wrong analysis.
**How to avoid:** The prompt must explicitly state the favorable direction for each metric class, or teach a general rule: "For probability metrics (xSwing, xWhiff, xSwSt), higher P than S means location helps the effect. For run value (xRV100), location helps when P is more negative than S."
**Warning signs:** Agent says "location hurts his slider's run value" when the delta actually shows location improving it.

### Pitfall 2: Forgetting the Summary Anchor
**What goes wrong:** The agent dives into intermediates and attribution but never connects back to the plus grades the user is familiar with.
**Why it happens:** The prompt emphasizes internals so strongly that plus scores get dropped entirely.
**How to avoid:** The response format section should explicitly state: "Reference plus scores (P+/S+/L+) as summary grades after explaining the model internals that drive them."
**Warning signs:** Agent response has no P+/S+/L+ numbers despite them being available in the data.

### Pitfall 3: Attribution Table Overload
**What goes wrong:** The agent lists all 13 outcome contributions instead of identifying the 2-3 dominant ones.
**Why it happens:** The prompt doesn't teach filtering/prioritization of the attribution data.
**How to avoid:** Instruct: "Identify the 2-3 outcome classes that contribute the most run value (positive or negative). Don't list all 13."
**Warning signs:** Agent response reads like a data table rather than analytical insight.

### Pitfall 4: Intermediate Probabilities Without Context
**What goes wrong:** The agent cites raw probabilities (e.g., "38% xWhiff") without comparing to anything, making the numbers meaningless to the reader.
**Why it happens:** The prompt doesn't teach comparison anchors.
**How to avoid:** Instruct the agent to compare intermediates against the S-variant (to show location impact) or against the pitch's own season baseline. The data includes both window and season values.
**Warning signs:** "His slider has a 42% xWhiff" with no comparison or interpretation.

### Pitfall 5: Prompt Regression on Existing Behaviors
**What goes wrong:** The rewrite inadvertently removes or weakens existing good behaviors (data grounding, graceful out-of-scope handling, scout voice).
**Why it happens:** Rewriting the whole prompt instead of surgically replacing only the framework/diagnostic sections.
**How to avoid:** Keep DATA GROUNDING RULES, RESPONSE FORMAT, and OUT OF SCOPE sections verbatim. Only rewrite ANALYTICAL FRAMEWORK and DIAGNOSTIC APPROACH.
**Warning signs:** Agent starts hallucinating data or responding in a non-scouting voice.

## Code Examples

### Current Prompt Structure (what to preserve vs replace)
```python
# Source: analyst.py lines 91-150
_ANALYST_INSTRUCTIONS = """\
# KEEP: Voice definition (lines 92-97)
You are an analytical baseball scout...

# REWRITE: Analytical framework (lines 98-108)
ANALYTICAL FRAMEWORK (Pitching+ triad):
...

# REWRITE: Diagnostic approach (lines 109-123)
DIAGNOSTIC APPROACH:
...

# KEEP: Data grounding rules (lines 125-134)
DATA GROUNDING RULES (absolute):
...

# KEEP: Response format (lines 136-149)
RESPONSE FORMAT:
...

# KEEP: Out of scope (lines 144-150)
OUT OF SCOPE (decline gracefully):
...
"""
```

### New Analytical Framework Pattern (recommended structure)
```python
# Recommended new ANALYTICAL FRAMEWORK section
"""
ANALYTICAL FRAMEWORK (Model Internals):
Your primary analytical lens is the Pitching+ model's intermediate \
probabilities and outcome attribution. For every pitch assessment:

1. Start with the model internals — xSwing (swing rate), xWhiff \
(whiff rate given swing), xSwSt (swinging strike rate), xRV100 \
(expected run value per 100 pitches). These tell you WHAT the pitch \
does to hitters.

2. Diagnose location impact by comparing P-variant (stuff + location) \
vs S-variant (stuff only). The delta tells you what command adds or \
subtracts. Example: "xWhiff drops from 38% (P) to 25% (S) — his \
location adds 13 percentage points of whiff rate."

3. Identify the dominant run-value driver from the component \
attribution table. Each pitch's xRV100 is decomposed into 13 outcome \
contributions. Find the 2-3 outcomes that contribute the most (positive \
or negative). Example: "Whiffs contribute -1.4 runs per 100 (saving \
runs), but home runs give back +0.6 (costing runs)."

4. Summarize with plus scores. After explaining the internals, \
reference P+ (combined), S+ (stuff), and L+ (location) as summary \
grades. P+ > 100 helps the pitcher; below 100 hurts.

SIGN CONVENTIONS:
- Probability metrics (xSwing, xWhiff, xSwSt): P > S means location \
increases the rate. Whether that helps depends on the metric — higher \
xWhiff is good for the pitcher, higher xSwing means more balls in play.
- Run value (xRV100): More negative = better for pitcher. P < S means \
location improves run value (good).
- Attribution contributions: Negative = pitcher benefits from that \
outcome. Positive = outcome costs runs.
"""
```

### New Diagnostic Approach Pattern (recommended structure)
```python
# Recommended new DIAGNOSTIC APPROACH section
"""
DIAGNOSTIC APPROACH:
When analyzing a pitch, follow this reasoning chain:

1. What does the pitch do? Read the intermediate probabilities. High \
xWhiff means it generates misses. High xSwing means hitters can't lay \
off. Low xRV100 means it saves runs overall.

2. How much does location help? Compare P vs S variants. A large \
positive xWhiff delta means his command is putting this pitch where \
hitters swing and miss. A small or negative delta means the whiffs \
come from stuff alone — command isn't adding much.

3. Where do the runs come from? Read the attribution table. If whiffs \
dominate the negative (pitcher-favorable) side, this is a swing-and-miss \
pitch. If ground outs dominate, it's a weak-contact pitch. If home runs \
dominate the positive (pitcher-costly) side, the pitch has a gopher \
ball problem even if the overall grade looks decent.

Use execution metrics (CSW%, Zone%, Chase%) as supporting evidence, not \
the primary frame. Reference plus scores (P+/S+/L+) as summary grades \
after explaining the underlying model signals.
"""
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (configured in pyproject.toml) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_analyst.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ANLST-01 | Prompt frames reasoning around model internals | unit (string inspection) | `uv run pytest tests/test_analyst.py::test_prompt_references_intermediates -x` | Wave 0 |
| ANLST-01 | Prompt de-emphasizes plus-grade-first framing | unit (string inspection) | `uv run pytest tests/test_analyst.py::test_prompt_internals_before_plus -x` | Wave 0 |
| ANLST-02 | Prompt includes P-vs-S location diagnosis instructions | unit (string inspection) | `uv run pytest tests/test_analyst.py::test_prompt_references_p_vs_s -x` | Wave 0 |
| ANLST-03 | Prompt includes attribution/dominant-driver instructions | unit (string inspection) | `uv run pytest tests/test_analyst.py::test_prompt_references_attribution -x` | Wave 0 |
| ALL | Existing agent integration test still passes | integration | `uv run pytest tests/test_analyst.py::test_ask_question_streaming -x` | Exists |
| ALL | Existing tool tests still pass (no structural changes) | integration | `uv run pytest tests/test_analyst.py -x` | Exists |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_analyst.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_analyst.py::test_prompt_references_intermediates` -- verifies ANLST-01 (prompt mentions xWhiff, xSwing, xSwSt, xRV100 as primary analytical tools)
- [ ] `tests/test_analyst.py::test_prompt_internals_before_plus` -- verifies ANLST-01 (analytical framework leads with internals, plus scores are "summary")
- [ ] `tests/test_analyst.py::test_prompt_references_p_vs_s` -- verifies ANLST-02 (prompt teaches P-variant vs S-variant comparison)
- [ ] `tests/test_analyst.py::test_prompt_references_attribution` -- verifies ANLST-03 (prompt teaches attribution decomposition and dominant-driver identification)

Note: These are string-content tests against `_ANALYST_INSTRUCTIONS`. They verify the prompt contains the right conceptual elements. They do NOT test LLM output quality (that requires manual validation with a real model).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Plus-grade-centric (P+/S+/L+ as primary lens) | Model-internals-first (intermediates + attribution as primary lens) | Phase 14 (this phase) | Agent explains *why* instead of just *what* |
| S+/L+ binary diagnosis ("bad stuff, good command") | P-vs-S delta diagnosis with probability metrics | Phase 14 (this phase) | Quantitative location impact instead of qualitative grade labels |
| No outcome-level decomposition | 13-outcome attribution table | Phase 12 data, Phase 13 tools, Phase 14 prompt | Agent identifies which outcomes drive overall run value |

## Open Questions

1. **How will manual validation work?**
   - What we know: String-content tests verify the prompt references the right concepts. The full suite passes if the prompt doesn't break the agent structure.
   - What's unclear: Validating that the LLM actually produces better analytical output requires running the agent against real data with a real model and reading the response.
   - Recommendation: After the prompt is rewritten and tests pass, run `pitcher-ask "How is [pitcher]'s slider?" --provider openai` manually and verify the output references intermediates, P-vs-S deltas, and attribution. This is a post-phase manual validation step, not an automated test.

2. **Should the response format change to accommodate new analytical depth?**
   - What we know: Current format says "Lead with the P+ grade, then decompose into S+ and L+." This must change since the new flow leads with internals.
   - What's unclear: Whether the "2-4 paragraphs for broad, 1-2 for specific" sizing still works with the additional analytical dimensions.
   - Recommendation: Keep the paragraph count guidance but update the leading pattern: "Lead with the most important model signal, then explain using intermediates and attribution, then summarize with plus grades."

## Sources

### Primary (HIGH confidence)
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/analyst.py` -- current prompt, agent structure, tool implementations
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/context.py` -- `to_prompt()` and `_render_intermediates_section()` showing exact data format the LLM receives
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/engine.py` -- `IntermediateProbabilities`, `ComponentAttribution`, `OutcomeContribution` dataclasses (lines 632-725)
- `/Users/matt/src/pitcher-narratives/tests/test_analyst.py` -- existing test patterns for the analyst module

### Secondary (MEDIUM confidence)
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/report.py` -- synthesizer/editor prompts as reference for scout-voice prompting patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, purely a string constant change
- Architecture: HIGH -- complete codebase read, all data structures and tool outputs understood
- Pitfalls: HIGH -- derived from direct analysis of metric semantics and sign conventions in the actual code

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- prompt engineering on fixed data structures)
