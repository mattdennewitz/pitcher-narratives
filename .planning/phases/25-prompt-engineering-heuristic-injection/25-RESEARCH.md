# Phase 25: Prompt Engineering & Heuristic Injection - Research

**Researched:** 2026-04-04
**Domain:** LLM prompt engineering for sabermetric narrative generation
**Confidence:** HIGH

## Summary

Phase 25 modifies prompt text in 5 agents and restructures one input builder. All changes target a single file: `src/pitcher_narratives/pipeline.py`. The work involves (1) appending heuristic directive sections to three specialist prompt constants, (2) converting the Trend Specialist prompt from a constant to a function with conditional vocabulary injection, (3) adding a causal hook requirement section to the writer prompt function, (4) inserting a whitelist section into the auditor prompt, and (5) restructuring the location input builder to place contradiction-relevant metrics adjacent per pitch type.

No new dependencies, no new agents, no architectural changes. Every modification has a precise insertion point documented in CONTEXT.md and verified against the current codebase. The existing test infrastructure covers prompt content assertions (substring checks on prompt constants and function outputs) and input builder output verification, establishing the exact test pattern for this phase.

**Primary recommendation:** Implement as three plans: (1) specialist prompt heuristics (Stuff + Location + Trend), (2) writer causal hook + auditor whitelist, (3) location input restructuring. This grouping separates "append text to prompts" work from "restructure data layout" work and keeps the auditor whitelist paired with the writer causal hook since they reference the same sabermetric patterns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Hybrid structure for Stuff trade-off detection -- state governing sabermetric principle first, then enumerate common patterns as grounding examples
- **D-02:** Hybrid pattern (principle + enumerated examples) is the standard template for ALL heuristic directives (PROMPT-01, PROMPT-02, PROMPT-03)
- **D-03:** Same hybrid structure for Location contradiction detection -- principle about zone expansion, then enumerated patterns
- **D-04:** PROMPT-06 implemented as BOTH data layout change AND prompt directive. `_build_location_input()` restructured so zone_rate, xWhiff_P, and chase_rate appear adjacent per pitch type
- **D-05:** Vocabulary glossary injected conditionally at Python level via `_build_trend_prompt(ctx)` -- NOT static prompt text. Includes block only when ctx has arm angle data
- **D-06:** Vocabulary content: arm slot -> "delivery angle" or "arm slot"; slot shift -> mechanical adjustment; tunneling advantage from different arm angles; anti-speculation directive
- **D-07:** Must-cite with honest fallback for S+ >= 10 point change. Writer MUST cite physical driver from Stuff Specialist. If unexplained, say so honestly
- **D-08:** 10-point S+ threshold hardcoded in writer prompt text. No Python pre-scanning
- **D-09:** Causal hook added to `_build_writer_prompt()` as CAUSAL HOOK REQUIREMENT section after existing sections
- **D-10:** Enumerated exception list as ALLOWED HEURISTIC PATTERNS section in auditor prompt. Three whitelisted patterns: inverse correlation, zone expansion, approach angle
- **D-11:** Heuristic valid ONLY when specialist cites specific supporting metrics. Uncited heuristic = HALLUCINATED_CAUSATION (category 5)
- **D-12:** Whitelist block placed immediately before output format instructions in auditor prompt (recency effect)

### Claude's Discretion
- Exact wording of each heuristic principle statement (beyond structure/content above)
- How Location Specialist input restructuring groups zone_rate/xWhiff/chase_rate (column order, formatting)
- Whether `_build_trend_prompt()` is a new function or refactors the existing constant (function preferred per D-05)

### Deferred Ideas (OUT OF SCOPE)
- Height-normalized arm angle (requires pitcher height data not in Statcast parquet)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROMPT-01 | Stuff Specialist prompt includes trade-off detection directive (inverse velo/movement -> S+ improvement) | D-01/D-02: Hybrid principle+examples template. Append to `_STUFF_SPECIALIST_PROMPT` after line 153. Existing anti-recalculation directive pattern at lines 149-153 establishes precedent for UPPERCASE section headers |
| PROMPT-02 | Location Specialist prompt includes contradiction detection directive (low zone + high whiff = expanding zone) | D-03: Same hybrid template. Append to `_LOCATION_SPECIALIST_PROMPT` after line 188. Pair with D-04 layout change in `_build_location_input()` |
| PROMPT-03 | Trend Specialist prompt includes release point framing vocabulary (arm angle, deception, approach angle) | D-05/D-06: Convert `_TREND_SPECIALIST_PROMPT` constant to `_build_trend_prompt(ctx)` function. Conditionally include vocabulary when `ctx.release_point.pitch_types` is non-empty. Update `make_pipeline_agents`, `run_specialists`, and `write_pipeline_data_file` |
| PROMPT-04 | Writer prompt includes causal hook requirement (S+ change >= 10 pts must cite physical driver) | D-07/D-08/D-09: Add CAUSAL HOOK REQUIREMENT section to `_build_writer_prompt()` after CONSTRAINTS section (line 487). Threshold hardcoded in prompt text |
| PROMPT-05 | Data Auditor prompt whitelists sabermetric heuristics as valid analysis | D-10/D-11/D-12: Insert ALLOWED HEURISTIC PATTERNS section in `_DATA_AUDITOR_PROMPT` immediately before "For each problem found" (line 377). Evidence-gated whitelist |
| PROMPT-06 | Location Specialist input places xWhiff and zone_rate adjacent for contradiction visibility | D-04: Restructure `_build_location_input()` to merge intermediates and execution data per pitch type. Currently zone_rate is in Execution section (line 672) while xWhiff_P is in P vs S section (line 668) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- no new dependencies
- **Data format**: Static parquet + CSV files, no live API calls
- **Python version**: 3.14+
- **Code style**: snake_case modules/functions, PascalCase classes, Google-style docstrings
- **Testing**: pytest (existing tests in `tests/test_pipeline.py`)
- **GSD workflow enforcement**: All edits through GSD commands

## Architecture Patterns

### Modification Targets in pipeline.py

```
src/pitcher_narratives/pipeline.py
  Lines 81-153   _STUFF_SPECIALIST_PROMPT      (PROMPT-01: append section)
  Lines 155-188  _LOCATION_SPECIALIST_PROMPT   (PROMPT-02: append section)
  Lines 223-246  _TREND_SPECIALIST_PROMPT      (PROMPT-03: convert to function)
  Lines 325-382  _DATA_AUDITOR_PROMPT          (PROMPT-05: insert section)
  Lines 409-487  _build_writer_prompt()        (PROMPT-04: add section)
  Lines 650-684  _build_location_input()       (PROMPT-06: restructure layout)
  Lines 1043-48  write_pipeline_data_file()    (PROMPT-03: update trend reference)
  Lines 1148-84  make_pipeline_agents()        (PROMPT-03: pass ctx for trend prompt)
  Lines 1191-229 run_specialists()             (PROMPT-03: no change needed if agent created with ctx)
```

### Pattern 1: Prompt Section Append (PROMPT-01, PROMPT-02)
**What:** Add a new UPPERCASE-HEADER section to the end of an existing prompt constant string.
**When to use:** Adding heuristic directives to Stuff and Location specialist prompts.
**Example:**
```python
# Existing pattern from lines 149-153:
_STUFF_SPECIALIST_PROMPT = """\
...existing content...
- When referencing metrics, use the exact values from the Raw Data \
section. These are ground truth.

TRADE-OFF DETECTION:
Stuff+ evaluates the holistic pitch. Whenever you see an INVERSE \
relationship between raw physical metrics (velocity/movement) and \
the S+ grade, your primary goal is to narrate the contradiction by \
finding the compensating factor in the data.

COMMON PATTERNS:
- Velo down + S+ up: movement or spin compensation. Cite the pfx \
deltas that explain the improvement.
- Velo up + S+ down: lost movement or dead zone shape. Cite \
movement deltas that explain the decline.
- Movement change + stable S+: shape adaptation maintaining \
effectiveness."""
```

### Pattern 2: Constant-to-Function Conversion (PROMPT-03)
**What:** Convert `_TREND_SPECIALIST_PROMPT` string constant to `_build_trend_prompt(ctx)` function with conditional sections.
**When to use:** When prompt content depends on runtime data availability.
**Precedent:** `_build_writer_prompt(role)` at line 409 -- same pattern, builds prompt string with conditional sections based on `role` parameter.
**Critical detail:** This requires changes to `make_pipeline_agents()` which currently passes the constant directly. Two options:
1. **Option A (recommended):** Pass `ctx` to `make_pipeline_agents()` so it can call `_build_trend_prompt(ctx)` when creating the trend agent. This is the simplest change -- add `ctx` parameter, call function instead of using constant.
2. **Option B:** Build the trend agent separately in `_run_pipeline()` after ctx is available. More disruptive to the agent factory pattern.

**Arm angle data detection:** `ctx.release_point.pitch_types` is non-empty when arm angle data exists. Since arm angle is computed from release_x/release_z via atan2 (always present in Statcast), this will be true for all real pitchers. The conditional still matters for test scenarios with empty release point data.

### Pattern 3: Section Insertion (PROMPT-05)
**What:** Insert a new section at a specific position within an existing prompt, not at the end.
**When to use:** When placement matters (D-12: recency effect -- whitelist before output format).
**Insertion point:** In `_DATA_AUDITOR_PROMPT`, immediately before "For each problem found, report:" (line 377). The whitelist must be the last substantive section before output instructions so the LLM weighs it heavily when generating pass/fail decisions.

### Pattern 4: Input Builder Restructuring (PROMPT-06)
**What:** Merge data from separate sections (intermediates + execution) into a per-pitch-type unified view.
**When to use:** When the LLM needs to cross-reference metrics that are currently separated by many tokens.
**Current structure (3 sections):**
```
## P vs S Location Impact
- Fastball: xSwing P/S, xWhiff P/S, xRV100 P/S
- Slider: xSwing P/S, xWhiff P/S, xRV100 P/S

## Execution Metrics
- Fastball: Zone%, Chase%, CSW%
- Slider: Zone%, Chase%, CSW%

## Plus Scores
- Fastball: P+, S+, L+
- Slider: P+, S+, L+
```
**Target structure (per-pitch unified):**
```
## Location Analysis by Pitch Type
### Fastball (FF)
- Zone: zone_rate, xWhiff_P, chase_rate (adjacent -- D-04)
- P vs S: xSwing P/S delta, xWhiff P/S delta, xRV100 P/S delta
- Grades: P+, S+, L+

### Slider (SL)
- Zone: zone_rate, xWhiff_P, chase_rate
...
```

### Anti-Patterns to Avoid
- **LLM-side conditionals:** Do NOT put "if arm angle data is present, use this vocabulary" in the prompt text. D-05 explicitly requires Python-level conditional injection.
- **Prompt bloat:** Do NOT add heuristic directives that duplicate existing interpretation rules. The trade-off detection directive supplements the existing RESPECT THE TAGS and MOVEMENT CONTEXT rules, not replaces them.
- **Static threshold injection:** Do NOT add Python code to scan ctx for pitches crossing the 10-point S+ threshold. D-08 explicitly says the writer identifies these from specialist inputs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prompt conditional injection | String concatenation with f-strings everywhere | Follow `_build_writer_prompt()` pattern: function with conditional blocks | Established pattern, clean separation |
| Metric adjacency | Custom data structure or new Pydantic model | Restructure `_build_location_input()` text output | The LLM consumes text, not data structures -- restructuring the text is sufficient |
| Arm angle detection | New boolean field on PitcherContext | `bool(ctx.release_point.pitch_types)` | Data already exists, no new field needed |

## Common Pitfalls

### Pitfall 1: Breaking make_pipeline_agents Signature
**What goes wrong:** Adding `ctx` parameter to `make_pipeline_agents()` breaks callers that don't pass it.
**Why it happens:** The function is called from `_run_pipeline()` (line 1247) and from tests.
**How to avoid:** Check all callers of `make_pipeline_agents` before changing its signature. The tests at `test_pipeline.py` call it directly (TestMakePipelineAgents class). Update test calls to pass a ctx or make ctx optional with a fallback to the static prompt.
**Warning signs:** Test failures in TestMakePipelineAgents.

### Pitfall 2: Whitelist Placement Off-by-One
**What goes wrong:** Inserting the whitelist section after the output format instructions instead of before them.
**Why it happens:** D-12 specifically says "immediately before the output format instructions" for recency effect. The output format starts at line 377: "For each problem found, report:".
**How to avoid:** The insertion point is between the last numbered category (9. COUNT_STATE_CLAIM_MISMATCH at line 375) and "For each problem found" (line 377). Place ALLOWED HEURISTIC PATTERNS in this gap.
**Warning signs:** The whitelist text appears after "For each problem found" in the final prompt string.

### Pitfall 3: Location Input Data Mismatch
**What goes wrong:** After restructuring `_build_location_input()`, a pitch type in `ctx.intermediates` has no corresponding entry in `ctx.execution` (or vice versa), causing data alignment errors.
**Why it happens:** Intermediates come from PitchingPlus model predictions; execution comes from Statcast observed data. Pitch types might not perfectly align.
**How to avoid:** Use a pitch-type-keyed merge strategy. Build a dict of execution metrics by pitch_type, then iterate intermediates and pull execution data when available. Handle missing execution data gracefully (show "--" or skip the execution line).
**Warning signs:** KeyError on pitch_type lookup, or pitches showing in intermediates but not execution.

### Pitfall 4: Trend Prompt Reference Stale in Data File
**What goes wrong:** `write_pipeline_data_file()` at line 1046 still references `_TREND_SPECIALIST_PROMPT` (the deleted constant) instead of calling `_build_trend_prompt(ctx)`.
**Why it happens:** Three call sites reference the trend prompt: `make_pipeline_agents`, `run_specialists` (via agent), and `write_pipeline_data_file`. Easy to miss the data file.
**How to avoid:** After converting the constant to a function, grep for `_TREND_SPECIALIST_PROMPT` to find all references. There are exactly three: line 1046 (data file), line 1175 (agent factory), and the import (if any).
**Warning signs:** NameError at runtime when generating data files.

### Pitfall 5: Test Assertions on Deleted Constant
**What goes wrong:** Existing tests import `_TREND_SPECIALIST_PROMPT` directly, which no longer exists after conversion to function.
**Why it happens:** Test files may reference the constant for assertion checks.
**How to avoid:** Search test files for `_TREND_SPECIALIST_PROMPT`. Current test_pipeline.py does NOT appear to import or assert on this constant directly (the prompt tests focus on Stuff, Writer, and Auditor), but verify before implementation.
**Warning signs:** ImportError in test collection.

### Pitfall 6: Causal Hook Wording Conflicts with Existing Writer Constraints
**What goes wrong:** The causal hook section says "MUST cite physical driver" but the existing CONSTRAINTS section says "Use ONLY data from the specialist analyses." These are compatible, but the LLM might interpret "cite physical driver" as needing to invent one when the Stuff Specialist didn't provide one.
**Why it happens:** D-07 specifically addresses this with the honest fallback: "NEVER invent a physical cause that the Stuff Specialist did not identify."
**How to avoid:** Include the anti-fabrication directive explicitly in the CAUSAL HOOK REQUIREMENT section. The fallback language ("S+ moved N points without an obvious physical explanation") must be part of the directive.
**Warning signs:** Writer narratives inventing physical causes for S+ changes.

## Code Examples

### Example 1: Stuff Specialist Trade-off Detection (PROMPT-01)
```python
# Source: CONTEXT.md D-01, D-02
# Append to _STUFF_SPECIALIST_PROMPT after line 153

"""
TRADE-OFF DETECTION:
Stuff+ evaluates the holistic pitch. Whenever you see an INVERSE \
relationship between raw physical metrics (velocity/movement) and \
the S+ grade, your primary goal is to narrate the contradiction by \
finding the compensating factor in the data.

COMMON PATTERNS:
- Velo down + S+ up: movement or spin compensation is driving the \
improvement. Cite the pfx deltas that explain it.
- Velo up + S+ down: lost movement or dead zone shape is undermining \
the velocity gain. Cite movement deltas.
- Movement change + stable S+: shape adaptation maintaining \
effectiveness through a different movement profile."""
```

### Example 2: Trend Prompt Function Conversion (PROMPT-03)
```python
# Source: CONTEXT.md D-05, D-06
# Pattern follows _build_writer_prompt() at line 409

def _build_trend_prompt(ctx: PitcherContext) -> str:
    """Build trend specialist system prompt with conditional release-point vocabulary."""
    base = """\
You are a trend analyst. Your job is to identify what has changed in \
the pitcher's recent window compared to season baseline and flag the \
direction and magnitude of those changes.
...existing content unchanged...
- Plain prose, no bullet lists."""

    # Conditional release-point framing vocabulary (D-05)
    if ctx.release_point.pitch_types:
        base += """

RELEASE POINT FRAMING:
When arm angle data is present, use this vocabulary to describe \
release point changes:
- Arm slot: "delivery angle" or "arm slot" (not "release point angle")
- Slot shift: describe as mechanical adjustment ("dropped down," \
"came over the top")
- Different arm angles across pitch types: tunneling advantage \
(pitches look similar out of the hand despite different trajectories)
- Overhand: steeper approach angle. Sidearm: more horizontal plane.
- Do NOT speculate on mechanical causes (injury, fatigue) -- only \
describe what the data shows."""

    return base
```

### Example 3: Location Input Restructuring (PROMPT-06)
```python
# Source: CONTEXT.md D-04
# Restructure _build_location_input() to group metrics per pitch type

def _build_location_input(ctx: PitcherContext) -> str:
    """Build input for the location specialist with adjacent contradiction metrics."""
    lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    lines.append(render_league_baselines(_pitch_types(ctx)))
    lines.append("")

    # Build execution lookup by pitch_type for merging
    exec_lookup = {e.pitch_type: e for e in ctx.execution}
    plus_lookup = {p.pitch_type: p for p in ctx.arsenal}

    lines.append("## Location Analysis by Pitch Type")
    for im in ctx.intermediates:
        if im.xswing_p is None:
            lines.append(f"\n### {im.pitch_name} ({im.pitch_type}): no data")
            continue

        lines.append(f"\n### {im.pitch_name} ({im.pitch_type})")

        # Contradiction metrics adjacent (D-04: zone_rate, xWhiff_P, chase_rate)
        e = exec_lookup.get(im.pitch_type)
        if e:
            lines.append(
                f"- Zone% {e.zone_rate:.1f}, xWhiff_P {im.xwhiff_p * 100:.1f}%, "
                f"Chase% {e.chase_rate:.1f}"
            )
            lines.append(f"- CSW% {e.csw_pct:.1f}")

        # P vs S location impact
        def _d(p, s):
            if p is not None and s is not None:
                return f"{(p - s) * 100:+.1f}pp"
            return "--"
        def _drv(p, s):
            if p is not None and s is not None:
                return f"{(p - s):+.2f}"
            return "--"

        lines.append(
            f"- P vs S: xSwing {_d(im.xswing_p, im.xswing_s)}, "
            f"xWhiff {_d(im.xwhiff_p, im.xwhiff_s)}, "
            f"xRV100 {_drv(im.xrv100_p, im.xrv100_s)}"
        )

        # Plus scores
        p = plus_lookup.get(im.pitch_type)
        if p:
            wp = f"{p.window_p_plus:.0f}" if p.window_p_plus is not None else "--"
            ws = f"{p.window_s_plus:.0f}" if p.window_s_plus is not None else "--"
            wl = f"{p.window_l_plus:.0f}" if p.window_l_plus is not None else "--"
            lines.append(f"- P+ {wp}, S+ {ws}, L+ {wl}")

    return "\n".join(lines)
```

### Example 4: Auditor Whitelist Insertion (PROMPT-05)
```python
# Source: CONTEXT.md D-10, D-11, D-12
# Insert BEFORE "For each problem found" (line 377)

"""
ALLOWED HEURISTIC PATTERNS:
The following analytical patterns are VALID when the specialist cites \
the specific metrics that support them. An uncited heuristic claim is \
still HALLUCINATED_CAUSATION (category 5).

1. INVERSE CORRELATION: Velocity down + S+ up (or vice versa) is \
valid IF the specialist cites pfx deltas (movement changes) as the \
compensating factor.
2. ZONE EXPANSION: Low zone% + high xWhiff is valid IF the specialist \
cites chase% as confirming evidence of zone expansion strategy.
3. APPROACH ANGLE: Arm angle -> deception/tunneling claims are valid \
IF arm angle data is present in the input and the specialist cites it.

Key rule: the pattern is valid ONLY when evidence is cited. Pattern \
recognition alone, without citing the specific metrics, is still a \
category 5 violation.

For each problem found, report:
..."""
```

### Example 5: Writer Causal Hook (PROMPT-04)
```python
# Source: CONTEXT.md D-07, D-08, D-09
# Append to _build_writer_prompt() return string after CONSTRAINTS section

"""
CAUSAL HOOK REQUIREMENT:
When ANY pitch shows a Stuff+ change of 10 or more points (window vs \
season S+ delta), you MUST cite the physical driver from the Stuff \
Specialist's analysis. Connect the S+ change to the velocity, \
movement, or spin change that explains it.

If the Stuff Specialist could not explain the S+ change, say so \
honestly: "S+ moved [N] points without an obvious physical \
explanation in the movement data." NEVER invent a physical cause \
that the Stuff Specialist did not identify."""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Static specialist prompts | Dynamic prompt functions (writer already converted) | Phase 24 | Trend prompt conversion follows established pattern |
| Flat data sections in inputs | Per-pitch-type unified views (approach input does this) | Phase 24 | Location input restructuring follows approach input pattern |
| 7 auditor categories | 9 categories with conditional framing | Phase 24 | Whitelist addition extends existing category structure |

## Open Questions

1. **make_pipeline_agents signature change for ctx**
   - What we know: `make_pipeline_agents(provider, thinking, role)` needs to call `_build_trend_prompt(ctx)` but doesn't receive ctx.
   - What's unclear: Whether to add ctx as required param (breaking test calls) or optional with fallback to static prompt.
   - Recommendation: Add `ctx: PitcherContext | None = None` as optional param. When None, use static base prompt without release-point vocabulary. Tests that don't care about arm angle pass no ctx. `_run_pipeline` passes ctx. This is the least disruptive change.

2. **Execution metrics missing for some pitch types**
   - What we know: `ctx.intermediates` and `ctx.execution` may not have the same pitch types (intermediates from model predictions, execution from observed data).
   - What's unclear: Whether this actually occurs in practice with real data.
   - Recommendation: Use dict-based lookup with graceful fallback. Show "--" for missing execution metrics rather than crashing.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (no version pinned, using uv-managed) |
| Config file | pyproject.toml (no [tool.pytest] section -- see existing tests) |
| Quick run command | `uv run python -m pytest tests/test_pipeline.py -x -q` |
| Full suite command | `uv run python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROMPT-01 | Stuff prompt contains trade-off detection section | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_stuff_prompt_tradeoff"` | Wave 0 |
| PROMPT-02 | Location prompt contains contradiction detection section | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_location_prompt_contradiction"` | Wave 0 |
| PROMPT-03 | Trend prompt function returns release-point vocabulary when arm angle present | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_trend_prompt"` | Wave 0 |
| PROMPT-03 | Trend prompt function omits vocabulary when no arm angle data | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_trend_prompt_no_arm"` | Wave 0 |
| PROMPT-04 | Writer prompt contains causal hook section | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_writer_prompt_causal"` | Wave 0 |
| PROMPT-05 | Auditor prompt contains allowed heuristic patterns section | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_auditor_whitelist"` | Wave 0 |
| PROMPT-05 | Auditor whitelist appears before output format | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_auditor_whitelist_placement"` | Wave 0 |
| PROMPT-06 | Location input has zone_rate, xWhiff, chase_rate adjacent per pitch type | unit | `uv run python -m pytest tests/test_pipeline.py -x -q -k "test_location_input_adjacent"` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/test_pipeline.py -x -q`
- **Per wave merge:** `uv run python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pipeline.py::TestStuffPromptHeuristics` -- test class for PROMPT-01 trade-off detection substring checks
- [ ] `tests/test_pipeline.py::TestLocationPromptHeuristics` -- test class for PROMPT-02 contradiction detection
- [ ] `tests/test_pipeline.py::TestTrendPromptFunction` -- test class for PROMPT-03 conditional vocabulary (with and without arm angle data)
- [ ] `tests/test_pipeline.py::TestWriterPromptCausalHook` -- test class for PROMPT-04 causal hook section presence
- [ ] `tests/test_pipeline.py::TestAuditorWhitelist` -- test class for PROMPT-05 whitelist content and placement
- [ ] `tests/test_pipeline.py::TestLocationInputAdjacency` -- test class for PROMPT-06 metric adjacency in output

All test classes follow the established pattern in test_pipeline.py: import the prompt constant or builder function, call it, assert substring presence. No mocking of external services needed.

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/pipeline.py` -- direct code inspection of all modification targets
- `src/pitcher_narratives/engine.py` -- ReleasePointMetrics, arm angle computation, ExecutionMetrics structure
- `src/pitcher_narratives/context.py` -- PitcherContext model, release_point rendering
- `tests/test_pipeline.py` -- existing test patterns for prompt content assertions
- `.planning/phases/25-prompt-engineering-heuristic-injection/25-CONTEXT.md` -- all implementation decisions (D-01 through D-12)

### Secondary (MEDIUM confidence)
- `.planning/phases/23-engine-foundation-data-enrichment/23-CONTEXT.md` -- arm angle computation details (D-05 through D-07a)
- `.planning/phases/24-pipeline-re-architecture/24-CONTEXT.md` -- anti-recalculation directive pattern (D-08), auditor categories (D-12/D-13)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all changes in existing Python code
- Architecture: HIGH -- all insertion points verified against current source, established patterns for every modification type
- Pitfalls: HIGH -- identified from direct code inspection of data flow and call sites

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable -- prompt text changes, no external dependency drift)
