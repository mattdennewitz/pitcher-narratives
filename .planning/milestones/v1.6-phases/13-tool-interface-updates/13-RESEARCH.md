# Phase 13: Tool Interface Updates - Research

**Researched:** 2026-03-31
**Domain:** Analyst tool markdown rendering (analyst.py tool output formatting)
**Confidence:** HIGH

## Summary

Phase 13 is a pure code modification phase within `analyst.py`. The two tools (`get_pitcher_summary` and `get_pitch_detail`) must be extended to include intermediate probabilities with P/S comparisons and component attribution data alongside their existing output. All the data is already computed and available on `PitcherContext.intermediates` (list of `IntermediateProbabilities`) and `PitcherContext.attributions` (list of `ComponentAttribution`) -- this phase is strictly about formatting that data into the markdown strings the tools return.

The key design constraint is **additive-only**: existing tool output (plus scores, arsenal, execution, platoon) must not change. New sections are appended. The `get_pitcher_summary` tool currently delegates to `PitcherContext.to_prompt()` -- the intermediates section must be added either there or as a separate append in the tool. The `get_pitch_detail` tool uses `_render_pitch_detail()` -- component attribution must be added there.

**Primary recommendation:** Add new `_render_intermediates_section()` and `_render_attribution_section()` helper methods on `PitcherContext` (for summary) and extend `_render_pitch_detail()` (for detail), following the existing markdown rendering patterns exactly.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices at Claude's discretion (infrastructure phase).

### Claude's Discretion
All implementation choices. Key context provided:
- Phase 11 added IntermediateProbabilities dataclass (P/S variants for all metrics)
- Phase 12 added ComponentAttribution dataclass (13-outcome xRV decomposition)
- Both are wired into PitcherContext.intermediates and PitcherContext.attributions
- analyst.py has get_pitcher_summary and get_pitch_detail tools that format PitcherContext data as markdown
- P vs S delta = P_value minus S_value (location impact)
- Existing tool output must not change -- new sections are additive

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-01 | get_pitcher_summary tool returns intermediate probabilities and P/S comparisons alongside existing plus scores | PitcherContext.intermediates has all data; add new markdown section after Execution in to_prompt() or append in tool |
| TOOL-02 | get_pitch_detail tool returns component attribution breakdown (13 outcome contributions to xRV) for a specific pitch type | PitcherContext.attributions has all data; extend _render_pitch_detail() with attribution section |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Python version**: 3.14+
- **Code style**: snake_case modules, PascalCase classes, Google-style docstrings, type hints on all signatures
- **Naming**: Use `__all__` in modules serving as public APIs, prefix internal helpers with `_`
- **Entry point**: `uv run` for all Python execution
- **Config**: All tooling config in `pyproject.toml`, not separate files
- **GSD workflow enforcement**: Active -- work through GSD commands

## Architecture Patterns

### Current Tool Architecture

Both tools follow the same pattern:

1. Tool is decorated with `@_analyst_agent.tool` on the module-level `_analyst_agent` Agent instance
2. Tool receives `RunContext[QADeps]` where `QADeps.context` is a `PitcherContext`
3. Tool returns a markdown string formatted for LLM consumption
4. `get_pitcher_summary` delegates entirely to `ctx.deps.context.to_prompt()`
5. `get_pitch_detail` filters context lists by pitch_type code, then calls `_render_pitch_detail()`

### Rendering Pattern

All markdown rendering follows this convention:
- Build a `lines: list[str]` accumulator
- Use `## Section` headers for major sections
- Use `### Subsection` headers within
- Use `- key: value` bullet format for metrics
- Use markdown tables for tabular data
- Use `f"{value:.1f}"` for percentages, `f"{value:.3f}"` for small probabilities
- Handle None with ternary: `f"{val:.3f}" if val is not None else "--"`
- Token budget: `_MAX_PITCH_TYPES = 4` limits all per-pitch-type lists to top 4

### Data Flow

```
PitcherData
  -> compute_intermediate_probabilities() -> list[IntermediateProbabilities]  (Phase 11)
  -> compute_component_attribution()      -> list[ComponentAttribution]       (Phase 12)
  -> assemble_pitcher_context()           -> PitcherContext                   (already wired)
     .intermediates: list[IntermediateProbabilities]  (sliced to [:4])
     .attributions: list[ComponentAttribution]        (sliced to [:4])

Analyst tools:
  get_pitcher_summary -> ctx.deps.context.to_prompt()       -> markdown string
  get_pitch_detail    -> _render_pitch_detail(code, ...)    -> markdown string
```

### Recommended Modification Points

**For TOOL-01 (get_pitcher_summary -- intermediates):**

Two viable approaches:

**Option A (recommended):** Add `_render_intermediates_section()` method to `PitcherContext` and call it from `to_prompt()`. This keeps all rendering in `context.py` where it belongs, consistent with how arsenal, execution, etc. are rendered. The new section goes after `_render_execution_section()`.

**Option B:** Append intermediates markdown after `to_prompt()` inside the `get_pitcher_summary` tool function. This avoids modifying `context.py` but breaks the single-responsibility pattern where `to_prompt()` renders the full context.

Option A is better because `to_prompt()` is already the canonical rendering location and Phase 14 (system prompt rewrite) will expect the full context to include intermediates.

**For TOOL-02 (get_pitch_detail -- component attribution):**

Extend `_render_pitch_detail()` in `analyst.py` to accept an optional `attribution_rows` parameter (list of `ComponentAttribution`). Add a new `### Component Attribution` subsection. The tool function filters `pc.attributions` by pitch_type and passes matches.

### Recommended Project Structure Changes

```
src/pitcher_narratives/
  context.py    # ADD: _render_intermediates_section() method on PitcherContext
                # MODIFY: to_prompt() to call new method
  analyst.py    # MODIFY: get_pitch_detail to filter and pass attributions
                # MODIFY: _render_pitch_detail() signature + body to render attributions
```

### Anti-Patterns to Avoid

- **Duplicating data rendering logic**: Do not re-compute P vs S deltas in the rendering layer. The delta is simply `P_value - S_value` -- compute it inline during rendering.
- **Breaking existing output format**: Do not reorder existing sections. New sections go at the end of their respective renders.
- **Overly dense tables**: The 8 intermediate metrics x 2 variants = 16 numbers per pitch type. A single table with all metrics would be unreadable. Group into conceptual clusters (swing/whiff behavior, batted ball outcomes, composite) or use a compact table with P, S, and delta columns.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| P vs S delta computation | Custom delta logic with edge-case handling | Simple `P - S` inline with None guard | Delta is definitionally P minus S; no scaling, no normalization needed |
| Metric formatting | Custom formatting utilities | Existing inline `f"{val:.Nf}" if val is not None else "--"` pattern | Established pattern throughout context.py and analyst.py |
| Pitch type filtering | New filtering function | Existing list comprehension pattern: `[x for x in pc.intermediates if x.pitch_type == code]` | Same pattern used for arsenal, execution, platoon in get_pitch_detail |

## Common Pitfalls

### Pitfall 1: Token Budget Explosion
**What goes wrong:** Adding all 8 intermediate metrics x 2 variants x 4 pitch types in a verbose format exceeds the ~2,000 token budget for `to_prompt()`.
**Why it happens:** IntermediateProbabilities has 16 window fields + 16 season fields = 32 numbers per pitch type.
**How to avoid:** Use a compact table format. Focus on the most diagnostic metrics (xSwing, xWhiff, xRV100, xSwSt) rather than listing all 8. Or present a selective subset with P, S, and delta in a single row. The existing Execution section already shows xWhiff_P and xSwing_P -- the intermediates section should show the S variants and deltas to complement, not duplicate.
**Warning signs:** Generated markdown exceeds 500 tokens for the intermediates section alone.

### Pitfall 2: Duplicating ExecutionMetrics Data
**What goes wrong:** The Execution section already renders `xWhiff_P`, `xSwing_P`, and `xRV100_P`. If the Intermediates section also renders these P-variants, the LLM gets duplicate data.
**Why it happens:** IntermediateProbabilities contains the same P-variant values as ExecutionMetrics (both sourced from the same CSV).
**How to avoid:** The intermediates section should focus on what is NEW: the S-variants and the P-vs-S deltas. The P-variants for xWhiff/xSwing/xRV100 are already in Execution. Frame the intermediates section as "Model Internals: Location Impact" or similar, showing S values and the delta, referencing that P values are in the Execution section above.
**Warning signs:** Same number appearing twice in the tool output with different labels.

### Pitfall 3: None Propagation in Delta Computation
**What goes wrong:** Computing `P - S` when either is None produces a TypeError.
**Why it happens:** Both P and S variants can be None when the underlying CSV column is missing (BBE_prob_P/S are future-proofed but may not exist in current data).
**How to avoid:** Guard with: `delta = f"{(p - s) * 100:+.1f}pp" if p is not None and s is not None else "--"` (or similar). Test with the actual test pitcher data to verify which fields are populated.
**Warning signs:** TypeError in rendering, or `--` for every delta.

### Pitfall 4: Forgetting to Pass Attributions to _render_pitch_detail
**What goes wrong:** `_render_pitch_detail()` is called from `get_pitch_detail` but the caller doesn't filter and pass `pc.attributions`.
**Why it happens:** The current signature takes only `(code, arsenal_rows, execution_rows, platoon_rows)`. Easy to extend the signature but forget to update the call site.
**How to avoid:** Update both the function signature and the call site in `get_pitch_detail` in the same task.
**Warning signs:** Attribution section never appears in get_pitch_detail output.

### Pitfall 5: Ignoring Scale Differences Between Metrics
**What goes wrong:** Presenting all intermediates with the same format when they have different scales.
**Why it happens:** xSwing/xWhiff/xGOr/xPUr/BBE_prob are 0-1 probabilities. xHR100 is per-100-pitches. xSwSt is 0-1. xRV100 is runs-per-100-pitches.
**How to avoid:** Format probability metrics as percentages (multiply by 100, show as `42.1%`). Format xHR100 and xRV100 as-is (they are already per-100 scale). Document the format choice.
**Warning signs:** Values displayed as `0.421` when `42.1%` would be more readable.

## Code Examples

### Pattern: Rendering Intermediates Section (for to_prompt)

```python
# Source: Follows existing pattern from _render_execution_section in context.py
def _render_intermediates_section(self) -> str:
    """Render intermediate probabilities with P vs S location impact."""
    if not self.intermediates:
        return ""

    lines = ["## Model Internals: Location Impact"]
    lines.append("| Pitch | xSwing S | delta | xWhiff S | delta | xRV100 S | delta |")
    lines.append("|-------|----------|-------|----------|-------|----------|-------|")

    for im in self.intermediates[:_MAX_PITCH_TYPES]:
        def _delta(p: float | None, s: float | None) -> str:
            if p is not None and s is not None:
                return f"{(p - s) * 100:+.1f}pp"
            return "--"

        def _pct(v: float | None) -> str:
            return f"{v * 100:.1f}%" if v is not None else "--"

        lines.append(
            f"| {im.pitch_name} ({im.pitch_type}) "
            f"| {_pct(im.xswing_s)} "
            f"| {_delta(im.xswing_p, im.xswing_s)} "
            f"| {_pct(im.xwhiff_s)} "
            f"| {_delta(im.xwhiff_p, im.xwhiff_s)} "
            f"| {_pct(im.xrv100_s) if im.xrv100_s is not None else '--'} "
            f"| {_delta(im.xrv100_p, im.xrv100_s)} |"
        )

    return "\n".join(lines)
```

**Note:** This is illustrative. The actual metric selection and table layout should balance comprehensiveness vs. token budget. The key metrics for scout-readable diagnostics are xSwing (swing rate), xWhiff (whiff rate), and xRV100 (overall value). xSwSt (swing+strike) and xGOr/xPUr (ground/popup ratios) are secondary.

### Pattern: Rendering Component Attribution (for get_pitch_detail)

```python
# Source: Follows existing pattern from _render_pitch_detail in analyst.py
# Added as new section within the function

# Attribution section
if attribution_rows:
    lines.append("")
    lines.append("### Component Attribution (xRV100 Decomposition)")
    for attr in attribution_rows:
        lines.append(f"Total raw xRV100: {attr.total_xrv100:.2f}")
        lines.append("")
        lines.append("| Outcome | Contribution | Share |")
        lines.append("|---------|-------------|-------|")
        for oc in attr.contributions:
            share = (oc.contribution / attr.total_xrv100 * 100) if attr.total_xrv100 != 0 else 0
            lines.append(
                f"| {oc.outcome} | {oc.contribution:+.3f} | {share:+.1f}% |"
            )
```

### Pattern: Filtering Attributions in get_pitch_detail Tool

```python
# Source: Follows existing filtering pattern in get_pitch_detail
attribution_match = [a for a in pc.attributions if a.pitch_type == code]
# Pass to _render_pitch_detail alongside existing parameters
```

### Pattern: P vs S Delta Presentation (success criterion 3)

```python
# Success criterion: "xSwing_P: 42%, xSwing_S: 51%, location delta: -9%"
# This format shows both values + the delta for diagnostic clarity
def _ps_line(label: str, p: float | None, s: float | None) -> str:
    """Format a P vs S comparison line."""
    p_str = f"{p * 100:.1f}%" if p is not None else "--"
    s_str = f"{s * 100:.1f}%" if s is not None else "--"
    if p is not None and s is not None:
        delta = (p - s) * 100
        return f"- {label}: P {p_str}, S {s_str}, location delta {delta:+.1f}pp"
    return f"- {label}: P {p_str}, S {s_str}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Opaque plus scores only | Plus scores + intermediate probabilities | Phase 11 (v1.5) | Agent can see WHY a pitch grades as it does |
| Single xRV100 number | 13-outcome xRV decomposition | Phase 12 (v1.5) | Agent can identify which outcome class drives value |
| No location isolation | P vs S variant comparison | Phase 11 (v1.5) | Agent can diagnose command vs stuff impact |

**Note:** Phase 14 will rewrite the system prompt to actively reason from these new data sections. Phase 13 just makes the data visible in tool output.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_analyst.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-01 | get_pitcher_summary includes intermediates with P/S comparisons | unit | `uv run pytest tests/test_analyst.py::test_get_pitcher_summary_includes_intermediates -x` | No -- Wave 0 |
| TOOL-01 | to_prompt() output includes intermediates section header | unit | `uv run pytest tests/test_context.py::test_to_prompt_includes_intermediates -x` | No -- Wave 0 |
| TOOL-02 | get_pitch_detail includes component attribution breakdown | unit | `uv run pytest tests/test_analyst.py::test_get_pitch_detail_includes_attribution -x` | No -- Wave 0 |
| TOOL-02 | Attribution shows 13 outcome contributions | unit | `uv run pytest tests/test_analyst.py::test_get_pitch_detail_attribution_has_outcomes -x` | No -- Wave 0 |
| TOOL-01/02 | Existing tool output preserved (no regression) | unit | `uv run pytest tests/test_analyst.py -x` | Yes -- existing tests |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_analyst.py tests/test_context.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_analyst.py::test_get_pitcher_summary_includes_intermediates` -- covers TOOL-01
- [ ] `tests/test_analyst.py::test_get_pitch_detail_includes_attribution` -- covers TOOL-02
- [ ] `tests/test_analyst.py::test_get_pitch_detail_attribution_has_outcomes` -- covers TOOL-02 (13 outcomes)
- [ ] `tests/test_context.py::test_to_prompt_includes_intermediates` -- covers TOOL-01 (rendering in context.py)

## Open Questions

1. **Token budget for intermediates in to_prompt()**
   - What we know: to_prompt() targets ~2,000 tokens. Adding all 8 metrics x 4 pitch types with P, S, and delta = 96 cells.
   - What's unclear: How many intermediate metrics to include in the summary view vs. saving detail for get_pitch_detail.
   - Recommendation: Include 3-4 key metrics (xSwing, xWhiff, xSwSt, xRV100) in summary. Include all 8 in get_pitch_detail's intermediates expansion. This keeps summary compact while giving the agent the option to drill deeper.

2. **Intermediates in get_pitch_detail too?**
   - What we know: TOOL-01 says "get_pitcher_summary returns intermediates." TOOL-02 says "get_pitch_detail returns attribution." Neither requirement explicitly says get_pitch_detail should also show intermediates.
   - What's unclear: Whether the agent should see P/S intermediates when drilling into a single pitch type.
   - Recommendation: Include intermediates in get_pitch_detail as well -- it is the natural drill-down point. Success criterion 3 mentions "P vs S delta is computed and presented" which implies it should be visible wherever the agent looks at pitch data. Phase 14's system prompt will likely direct the agent to call get_pitch_detail for diagnostic reasoning.

3. **xRV100 scale in intermediates vs. attribution**
   - What we know: IntermediateProbabilities.xrv100_p/s are from the CSVs (mean-subtracted, league-average-centered). ComponentAttribution.total_xrv100 is raw (pre-mean-subtraction).
   - What's unclear: Whether the narrative should reconcile these scales.
   - Recommendation: Do not reconcile in the tool output. Just label them clearly. Phase 14's system prompt can explain the scale difference.

## Sources

### Primary (HIGH confidence)
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/analyst.py` -- current tool implementations, rendering patterns, QADeps dependency injection
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/context.py` -- PitcherContext model, to_prompt() rendering, intermediates/attributions fields
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/engine.py` -- IntermediateProbabilities (line 632), ComponentAttribution (line 703), OutcomeContribution (line 692) dataclass definitions
- `/Users/matt/src/pitcher-narratives/tests/test_analyst.py` -- existing test patterns for tool testing with mock RunContext

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` -- TOOL-01, TOOL-02 requirement definitions
- `.planning/phases/13-tool-interface-updates/13-CONTEXT.md` -- phase boundary and implementation context

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, pure Python code modification
- Architecture: HIGH -- all patterns visible in existing codebase, well-established rendering conventions
- Pitfalls: HIGH -- identified from direct code analysis (None handling, token budget, data duplication)

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- internal codebase, no external dependency changes)
