# Phase 22: Context Assembly & Prompt Rendering - Research

**Researched:** 2026-04-03
**Domain:** Pydantic model extension, markdown prompt rendering, multi-agent pipeline context routing
**Confidence:** HIGH

## Summary

Phase 22 wires the cross-season outputs from Phases 20 and 21 into the LLM prompt pipeline. There are three distinct integration points: (1) adding two optional fields to the `PitcherContext` Pydantic model, (2) rendering a new "Year-over-Year Changes" section in `to_prompt()`, and (3) injecting cross-season data into three specialist pipeline agents' context blocks.

The codebase already has all the upstream dependencies implemented. `CrossSeasonSummary` and `ArsenalTrend` dataclasses exist in `engine.py` with working `compute_cross_season_summary()` and `compute_arsenal_trends()` functions. The `PitcherContext` model in `context.py` follows a consistent pattern: optional fields typed as `X | None`, `assemble_pitcher_context()` calling engine compute functions, and `to_prompt()` building a sections list where each section is rendered by a private `_render_*` method that returns an empty string when data is absent. The pipeline specialist input builders in `pipeline.py` follow a similar pattern: each `_build_*_input()` function composes markdown from `PitcherContext` fields.

**Primary recommendation:** Follow the existing codebase patterns exactly -- add two optional fields to PitcherContext, one new `_render_yoy_section()` method in `to_prompt()`, wire engine calls in `assemble_pitcher_context()`, and extend three `_build_*_input()` functions in pipeline.py.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- PitcherContext gets `cross_season_summary: CrossSeasonSummary | None` and `arsenal_trend: ArsenalTrend | None` fields, both None for single-season pitchers
- Section heading: "## Year-over-Year Changes", positioned after existing sections (fastball, arsenal, execution), before workload context
- Renders top-level deltas (velocity, P+, S+, L+, workload) from cross_season_summary
- Renders arsenal changes (added, dropped, changed pitches) from arsenal_trend
- Omit the section entirely for single-season pitchers (no empty headers, no "N/A" placeholders)
- 3 specialists receive cross-season data: stuff, trends, game_shape
- Stuff specialist: gets cross-season velocity/P+/S+ deltas + arsenal changes (pitch adds/drops)
- Trends specialist: gets full cross-season summary + arsenal trends (everything)
- Game Shape specialist: gets workload comparison + arsenal usage shifts
- Location and Run Value specialists: no cross-season data (not relevant to their lens)

### Claude's Discretion
- Exact markdown formatting within the YoY section
- How to abbreviate arsenal changes to stay within token budget
- Whether to include raw numbers or only qualitative strings in prompt

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CPMT-01 | PitcherContext model includes optional cross-season summary and arsenal trend fields | PitcherContext uses `X \| None = None` pattern; `CrossSeasonSummary` and `ArsenalTrend` dataclasses exist in engine.py; `assemble_pitcher_context()` already calls all engine compute functions |
| CPMT-02 | to_prompt() renders a Year-over-Year section with top-level deltas and arsenal changes when multi-season data exists, omits it entirely for single-season pitchers | `to_prompt()` uses sections list with `_render_*` methods returning empty string for absent data; same pattern applies here |
| CPMT-03 | Specialist pipeline agents (stuff, trends, game shape) receive cross-season data in their context blocks | `_build_stuff_input()`, `_build_trend_input()`, `_build_game_shape_input()` in pipeline.py each compose markdown from ctx fields; extend these three functions only |
</phase_requirements>

## Standard Stack

No new dependencies. Phase 22 uses only existing project libraries.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | PitcherContext model definition | Already used; PitcherContext is a BaseModel |
| polars | 1.39.3 | Not directly used in this phase | Upstream data; context assembly receives computed dataclasses |

### Supporting
No new libraries needed. All work is in existing modules.

## Architecture Patterns

### Recommended Project Structure (files modified)
```
src/pitcher_narratives/
    context.py      # PitcherContext model + to_prompt() + assemble_pitcher_context()
    pipeline.py     # _build_stuff_input(), _build_trend_input(), _build_game_shape_input()
tests/
    test_context.py # New tests for YoY rendering
    test_pipeline.py # New tests for specialist context blocks
```

### Pattern 1: Optional Field with None Default (PitcherContext)
**What:** Add optional cross-season fields that are None when data is absent
**When to use:** When data availability depends on pitcher history
**Example (from existing code):**
```python
# context.py, line 63 -- existing pattern
fastball: FastballSummary | None
velocity_arc: VelocityArc | None

# New fields follow same pattern:
cross_season_summary: CrossSeasonSummary | None
arsenal_trend: ArsenalTrend | None
```

### Pattern 2: Sections List with Conditional Rendering (to_prompt)
**What:** `to_prompt()` appends section strings to a list, then joins non-empty ones
**When to use:** Every section in the prompt output
**Example (from existing code):**
```python
# context.py, line 77-120
def to_prompt(self) -> str:
    sections: list[str] = []
    sections.append(self._render_executive_summary())
    # ...each section appended...
    return "\n\n".join(s for s in sections if s)
```
The join filter `if s` means a `_render_*` method returning `""` is silently omitted. The new `_render_yoy_section()` returns `""` when both `cross_season_summary` and `arsenal_trend` are None.

### Pattern 3: Engine Call in assemble_pitcher_context
**What:** Each engine compute function is called in `assemble_pitcher_context()` and its result stored on PitcherContext
**When to use:** Every new data section
**Example (from existing code):**
```python
# context.py, lines 548-560
fastball = compute_fastball_summary(data)
velocity_arc = compute_velocity_arc(data, fastball.pitch_type) if fastball else None
# ...
return PitcherContext(
    fastball=fastball,
    velocity_arc=velocity_arc,
    # ...
)
```
New calls: `compute_cross_season_summary(data)` and `compute_arsenal_trends(data)`.

### Pattern 4: Specialist Input Builder (pipeline.py)
**What:** Each specialist has a `_build_*_input(ctx: PitcherContext) -> str` function that composes markdown
**When to use:** Every specialist that needs data injected
**Example (from existing code):**
```python
# pipeline.py, lines 550-562
def _build_trend_input(ctx: PitcherContext) -> str:
    baselines = render_league_baselines(_pitch_types(ctx))
    sections = [
        f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
        baselines, "",
        ctx._render_fastball_section(),
        ctx._render_arsenal_section(),
        ctx._render_release_point_section(),
        ctx._render_hard_hit_section(),
    ]
    return "\n\n".join(s for s in sections if s)
```
Cross-season data is appended to the relevant sections list in each builder.

### Pattern 5: Section Placement in to_prompt()
**What:** The YoY section goes after execution sections, before workload/appearances
**When to use:** Specific to this phase
**Current section order in to_prompt():**
1. Title
2. Executive Summary
3. Role & Workload summary
4. Primary Fastball
5. Times Through Order
6. Arsenal table
7. Execution table
8. Model Internals
9. Release Point
10. Contact Quality
11. Platoon Shifts
12. First-Pitch Tendencies
13. Recent Appearances

**New insertion point:** After First-Pitch Tendencies (#12), before Recent Appearances (#13). This matches the CONTEXT.md decision "after existing sections (fastball, arsenal, execution), before workload context" -- the recent appearances section serves as the workload/recency context.

### Anti-Patterns to Avoid
- **Rendering None as "N/A" or empty headers:** The CONTEXT.md explicitly forbids this. Return `""` from the render method when data is None.
- **Modifying Location or Run Value specialist inputs:** CONTEXT.md locks these two specialists out of cross-season data.
- **Using dataclass fields directly in prompt text:** Convert to readable strings. CrossSeasonSummary already has `velo_delta`, `p_plus_delta` etc. as pre-computed qualitative strings.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YoY delta strings | Custom string formatting | Use `CrossSeasonSummary.velo_delta`, `.p_plus_delta`, etc. | Engine already computes qualitative strings using same thresholds as within-season |
| Pitch name mapping | Manual dict lookup | Use `ArsenalTrend.added_pitches[].pitch_name`, `.dropped_pitches[].pitch_name` | Engine already resolves pitch type codes to human names |
| Arsenal trend None check | Checking individual fields | Check `self.arsenal_trend is None` | ArsenalTrend is None for single-season; when present, all lists are populated |

## Common Pitfalls

### Pitfall 1: Token Budget Violation
**What goes wrong:** Adding a full YoY section with per-pitch-type deltas blows past the 2,000 token budget.
**Why it happens:** ArsenalTrend.pitch_trends can have up to 6+ entries with 4 metrics each.
**How to avoid:** Limit pitch_trends display to top 3-4 by usage. Only show non-Steady deltas. Use compact formatting (one line per pitch, not bullet lists).
**Warning signs:** The existing `test_to_prompt_token_budget` test fails (estimated 2,000 tokens at ~4 chars/token).

### Pitfall 2: Section Appears for Single-Season Pitchers
**What goes wrong:** The YoY section renders with empty content or "no data" message.
**Why it happens:** Guard clause checks only one of the two fields, or renders a header before checking both.
**How to avoid:** Return `""` immediately when BOTH `self.cross_season_summary is None` AND `self.arsenal_trend is None`. Check at the top of `_render_yoy_section()`.
**Warning signs:** Prompt output contains "Year-over-Year" for a pitcher with only one season of data.

### Pitfall 3: Import Cycle Between context.py and engine.py
**What goes wrong:** Adding imports of `CrossSeasonSummary` and `ArsenalTrend` to context.py could create issues.
**Why it happens:** context.py already imports many engine types (line 12-39). No cycle exists today.
**How to avoid:** Add the new imports to the existing engine import block. No new modules needed.
**Warning signs:** ImportError at module load time.

### Pitfall 4: CrossSeasonSummary is a Dataclass, Not a BaseModel
**What goes wrong:** PitcherContext (BaseModel) holds CrossSeasonSummary (dataclass). Pydantic may not serialize it by default.
**Why it happens:** PitcherContext already has `model_config = ConfigDict(arbitrary_types_allowed=True)` (line 54), so dataclasses are handled. But `model_copy()` in tests needs to work.
**How to avoid:** The existing `arbitrary_types_allowed=True` config already handles this. Verify with a `model_copy(update={...})` test.
**Warning signs:** Pydantic ValidationError when constructing PitcherContext with a CrossSeasonSummary.

### Pitfall 5: Specialist Prompt Not Updated to Explain YoY Data
**What goes wrong:** The LLM receives cross-season data but the system prompt doesn't tell it what the data means or how to use it.
**Why it happens:** Only the user message (context block) is updated, not the system prompt.
**How to avoid:** Add a brief instruction to each relevant specialist's system prompt explaining what the YoY section contains. This is optional but recommended -- the data is self-describing markdown, and the existing prompts already say "use the data provided."
**Warning signs:** Specialist outputs ignore the YoY data entirely.

## Code Examples

### Adding Fields to PitcherContext
```python
# In context.py, add to imports:
from pitcher_narratives.engine import (
    # ... existing imports ...
    ArsenalTrend,
    CrossSeasonSummary,
    compute_arsenal_trends,
    compute_cross_season_summary,
)

# In PitcherContext class, add after existing fields:
cross_season_summary: CrossSeasonSummary | None = None
"""Year-over-year pitcher-level metric deltas. None for single-season pitchers."""

arsenal_trend: ArsenalTrend | None = None
"""Year-over-year arsenal evolution (added/dropped/changed pitches). None for single-season pitchers."""
```

### Rendering the YoY Section (recommended format)
```python
def _render_yoy_section(self) -> str:
    """Render Year-over-Year Changes section.

    Returns empty string when both cross-season fields are None,
    ensuring single-season pitchers get no YoY section.
    """
    css = self.cross_season_summary
    at = self.arsenal_trend

    if css is None and at is None:
        return ""

    lines = ["## Year-over-Year Changes"]

    if css is not None:
        lines.append(f"Comparing {css.current_season} vs {css.prior_season}:")
        lines.append(f"- Velocity: {css.velo_delta}")
        lines.append(f"- P+: {css.p_plus_delta}")
        lines.append(f"- S+: {css.s_plus_delta}")
        lines.append(f"- L+: {css.l_plus_delta}")
        # Workload comparison
        lines.append(
            f"- Workload: {css.current_appearances} app / {css.current_ip:.0f} IP "
            f"(prior: {css.prior_appearances} app / {css.prior_ip:.0f} IP)"
        )

    if at is not None:
        if at.added_pitches:
            added = ", ".join(
                f"{p.pitch_name} ({p.usage_pct:.0f}%)" for p in at.added_pitches
            )
            lines.append(f"- Added: {added}")
        if at.dropped_pitches:
            dropped = ", ".join(
                f"{p.pitch_name} ({p.usage_pct:.0f}%)" for p in at.dropped_pitches
            )
            lines.append(f"- Dropped: {dropped}")
        # Top changed pitches (non-Steady only, limit to 4)
        for pt in at.pitch_trends[:_MAX_PITCH_TYPES]:
            deltas = []
            if "Steady" not in pt.usage_delta:
                deltas.append(f"usage {pt.usage_delta}")
            if "Steady" not in pt.p_plus_delta:
                deltas.append(f"P+ {pt.p_plus_delta}")
            if "Steady" not in pt.s_plus_delta:
                deltas.append(f"S+ {pt.s_plus_delta}")
            if "Steady" not in pt.velo_delta:
                deltas.append(f"velo {pt.velo_delta}")
            if deltas:
                lines.append(f"- {pt.pitch_name}: {', '.join(deltas)}")

    return "\n".join(lines)
```

### Wiring in assemble_pitcher_context
```python
# In assemble_pitcher_context(), add before the return:
cross_season_summary = compute_cross_season_summary(data)
arsenal_trend = compute_arsenal_trends(data)

# In the PitcherContext() constructor call, add:
cross_season_summary=cross_season_summary,
arsenal_trend=arsenal_trend,
```

### Extending Specialist Inputs (stuff example)
```python
# In _build_stuff_input(), after existing content, before return:
if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
    lines.append("\n## Year-over-Year Context")
    css = ctx.cross_season_summary
    if css is not None:
        lines.append(f"- Velocity YoY: {css.velo_delta}")
        lines.append(f"- P+ YoY: {css.p_plus_delta}")
        lines.append(f"- S+ YoY: {css.s_plus_delta}")
    at = ctx.arsenal_trend
    if at is not None:
        if at.added_pitches:
            lines.append(f"- Added pitches: {', '.join(p.pitch_name for p in at.added_pitches)}")
        if at.dropped_pitches:
            lines.append(f"- Dropped pitches: {', '.join(p.pitch_name for p in at.dropped_pitches)}")
```

### Insertion Point in to_prompt()
```python
# In to_prompt(), add after _render_first_pitch_section() and before _render_appearances_section():
sections.append(self._render_yoy_section())
sections.append(self._render_appearances_section())
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-season data only | Multi-season baselines in PitcherData | Phase 19 (v1.8) | Engine can compute cross-season deltas |
| No YoY metrics | CrossSeasonSummary + ArsenalTrend engine functions | Phases 20-21 (v1.8) | Data exists but is not yet surfaced to LLM |
| Specialists see only current-season data | Phase 22 adds YoY context to 3 of 5 specialists | This phase | LLM can reference year-over-year changes in narratives |

## Open Questions

1. **Token budget headroom**
   - What we know: Current `to_prompt()` output passes the 2,000 token budget test (~800 chars/token estimate). The new section adds variable-length content depending on arsenal size.
   - What's unclear: Exact token cost of the YoY section for a pitcher with 5+ pitch types and significant changes across all metrics.
   - Recommendation: Cap pitch_trends display at `_MAX_PITCH_TYPES` (4) and only show non-Steady deltas. Run the token budget test against a multi-season pitcher after implementation.

2. **Whether specialist system prompts need YoY instructions**
   - What we know: The existing prompts tell specialists to "use the data provided" and explain the data format. The YoY section is self-describing markdown.
   - What's unclear: Whether specialists will actually reference the YoY data without explicit instructions.
   - Recommendation: Add a single sentence to each relevant specialist's HOW TO READ THE DATA section: "The Year-over-Year Context section shows changes from the previous season." This is low-cost and prevents silent data ignorance. Marked as Claude's discretion per CONTEXT.md.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_context.py tests/test_pipeline.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CPMT-01 | PitcherContext includes cross_season_summary and arsenal_trend fields | unit | `uv run pytest tests/test_context.py::test_cross_season_fields_present -x` | Wave 0 |
| CPMT-01 | Fields are None for single-season pitcher | unit | `uv run pytest tests/test_context.py::test_cross_season_fields_none_single_season -x` | Wave 0 |
| CPMT-02 | to_prompt() renders YoY section for multi-season | unit | `uv run pytest tests/test_context.py::test_to_prompt_yoy_section_present -x` | Wave 0 |
| CPMT-02 | to_prompt() omits YoY section for single-season | unit | `uv run pytest tests/test_context.py::test_to_prompt_yoy_section_absent_single_season -x` | Wave 0 |
| CPMT-02 | to_prompt() stays within token budget with YoY | unit | `uv run pytest tests/test_context.py::test_to_prompt_token_budget -x` | Existing (must still pass) |
| CPMT-03 | Stuff specialist input includes YoY when available | unit | `uv run pytest tests/test_pipeline.py::test_stuff_input_includes_yoy -x` | Wave 0 |
| CPMT-03 | Trends specialist input includes full YoY | unit | `uv run pytest tests/test_pipeline.py::test_trend_input_includes_yoy -x` | Wave 0 |
| CPMT-03 | Game shape specialist input includes workload YoY | unit | `uv run pytest tests/test_pipeline.py::test_game_shape_input_includes_yoy -x` | Wave 0 |
| CPMT-03 | Location/RV specialist inputs do NOT include YoY | unit | `uv run pytest tests/test_pipeline.py::test_location_rv_no_yoy -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_context.py tests/test_pipeline.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- Tests for CPMT-01: PitcherContext field presence and None-for-single-season
- Tests for CPMT-02: YoY section present/absent in to_prompt() output; token budget still passes
- Tests for CPMT-03: Three specialist inputs include YoY; two specialist inputs exclude YoY
- Test helper: synthetic multi-season PitcherContext with populated CrossSeasonSummary and ArsenalTrend (can use `model_copy(update={...})` on the existing real-data fixture for rendering tests, or build synthetic dataclasses directly for unit tests)

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python, polars, pydantic-ai, Claude -- no new dependencies
- **Naming:** snake_case for modules/functions, PascalCase for Pydantic models and dataclasses
- **Code style:** ruff for formatting/linting (line-length 110, target py313)
- **Imports:** Absolute imports, grouped/sorted
- **Error handling:** Specific exceptions, no bare `except:`
- **Docstrings:** Google-style, type hints on all function signatures
- **GSD workflow:** All edits through GSD workflow
- **Python version:** 3.14+

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/context.py` -- PitcherContext model, to_prompt() rendering, assemble_pitcher_context() orchestration (read in full)
- `src/pitcher_narratives/engine.py` -- CrossSeasonSummary (lines 1110-1148), ArsenalTrend (lines 2924-2941), compute_cross_season_summary() (lines 2153-2222), compute_arsenal_trends() (lines 2943+)
- `src/pitcher_narratives/pipeline.py` -- _build_stuff_input() (lines 444-492), _build_trend_input() (lines 550-562), _build_game_shape_input() (lines 565-577), run_specialists() (lines 907-944)
- `tests/test_context.py` -- 22 existing tests, all passing (verified via `uv run pytest`)
- `tests/test_engine.py` -- Arsenal trend tests (lines 1197-1530), synthetic data fixture pattern

### Secondary (MEDIUM confidence)
- `src/pitcher_narratives/data.py` -- PitcherData dataclass with prior_season_baseline field (lines 70-93)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies; all code uses existing modules
- Architecture: HIGH - Every pattern directly observed in current codebase; all four integration points verified
- Pitfalls: HIGH - Token budget test exists and will catch regressions; None handling pattern is well-established

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable internal codebase patterns, no external dependencies)
