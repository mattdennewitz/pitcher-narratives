# Phase 24: Pipeline Re-Architecture - Research

**Researched:** 2026-04-04
**Domain:** Multi-agent pipeline expansion (pydantic-ai specialist agents)
**Confidence:** HIGH

## Summary

Phase 24 expands the 5-specialist pipeline to 6 agents by adding an Approach Specialist, implementing dynamic RP routing that skips Game Shape for relievers, and attaching raw data appendices to Stuff and Trend specialist inputs. All changes are confined to `pipeline.py` (agent definitions, input builders, prompts, orchestration, auditor wiring) with no new engine computation required -- Phase 23 already provides all data fields (platoon_mix, count_splits, first_pitch on PitcherContext).

The codebase has a clean, consistent pattern: each specialist gets a system prompt constant, an `_build_*_input()` function, an `Agent[None, str]` definition in `PipelineAgents`, a slot in `SpecialistOutputs`, and wiring in `run_specialists()` / `audit_and_revise_specialists()` / `build_writer_input()`. Adding the 6th agent means replicating this pattern exactly. The RP Game Shape skip is a conditional guard in `_build_game_shape_input()` and `run_specialists()` that returns a static workload stub instead of making an LLM call.

**Primary recommendation:** Follow the established specialist pattern exactly. Add `_APPROACH_SPECIALIST_PROMPT`, `_build_approach_input()`, an `approach` field to `SpecialistOutputs` and `PipelineAgents`, and wire it through `run_specialists()`, `audit_and_revise_specialists()`, `build_writer_input()`, and the anchor check synthesis string.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Strategy-first framing. Prompt leads with the pitcher's approach pattern ("attacks righties with sinker, hides sweeper when ahead") then cites the data. Reads like a scout describing how the pitcher thinks, not a data dump.
- **D-02:** Cross-reference platoon and count-state data. Prompt explicitly instructs: "When a pitcher throws more X vs lefties AND more X when behind, connect these -- it reveals situational strategy." This is the analytical value-add over having separate data streams.
- **D-03:** Adaptive output length with anti-padding directive. Prompt: "Match your output length to the density of the data. If the pitcher shows complex, highly variable strategies, use up to 3 paragraphs. If the pitcher's approach is uniform and straightforward, summarize it in 1 paragraph. Under no circumstances should you pad the response with filler or repeat data points to increase length."
- **D-04:** Notable shifts only (10+ pp) as input, NOT full appendix tables. Must include baseline overall pitch mix alongside the shifts so the specialist can weight significance -- a 12pp shift on a 40% pitch is the headline; on a 5% pitch it's a footnote.
- **D-05:** Workload-only stub for relievers. A short pre-formatted block with appearance frequency, pitch count trends, and rest days -- deterministic data from PitcherContext, no LLM call. Writer gets real workload signal without TTO noise.
- **D-06:** Conditional writer prompt for RP context. Use conditional logic in prompt compilation: "You are synthesizing a scouting report for a {Role}. {If Role == Reliever: do not fabricate TTO analysis; the workload section replaces Game Shape.}" Single writer prompt with role-aware insertion, not two separate prompts.
- **D-07:** Stuff Specialist gets a per-pitch delta table: pitch type, window/season velo, velo delta, window/season pfx_x/pfx_z, movement deltas, S+/P+ window and season. All numbers the specialist references, in one grounding table.
- **D-08:** Stuff prompt includes anti-recalculation directive: "Refer specifically to the data in the Per-Pitch Delta Table when discussing movement or velocity changes. Do not attempt to recalculate these numbers."
- **D-09:** Raw data appendix labeled as ground truth with citation requirement: "Raw Data (cite these exact numbers)." Prompt directive: "When referencing metrics, use the exact values from the Raw Data section."
- **D-10:** Trend Specialist gets a timeline-oriented appendix -- per-appearance snapshots for the last 5-7 appearances, primary pitches only (>10% usage). This forces genuine temporal narratives ("ramping up", "fading", "plateauing") instead of restating static deltas. Differentiates Trend from Stuff output.
- **D-11:** Timeline data cap: 5-7 most recent appearances. Filter to primary pitches (>10% usage) to prevent token overload. The existing 30-day window parameter naturally handles IL stint returns -- post-return data only.
- **D-12:** Same 7 existing audit categories PLUS 2 domain-specific checks for Approach Specialist: (1) platoon claim matches actual vs-LHB/vs-RHB data, (2) count-state claim matches actual bucket data.
- **D-13:** Domain-specific audit checks use chain-of-thought "show your work" format: (1) state the claim from the text, (2) cite the exact numbers from the data table, (3) Boolean Pass/Fail.
- **D-14:** Auditor receives both input data and output for the Approach Specialist (same pattern as existing specialists). Enables cross-checking claims against source data.

### Claude's Discretion
- Exact Approach Specialist system prompt wording (beyond the framing and directives captured above)
- Per-appearance timeline table column selection for Trend Specialist
- Workload stub formatting details (column layout, which fields beyond appearance frequency, pitch count, rest days)
- How the conditional RP writer prompt is structured syntactically

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-01 | Approach Specialist agent receives platoon mix, count splits, and first-pitch data as input | New `_build_approach_input()` function calls `ctx._render_platoon_section()`, `ctx._render_count_splits_section()`, `ctx._render_first_pitch_section()`, and includes baseline overall pitch mix from `ctx.arsenal` |
| PIPE-02 | Approach Specialist prompt prioritizes 10+ pp platoon/count usage shifts as lead stories | System prompt includes D-01 strategy-first framing, D-02 cross-reference directive, D-03 adaptive length, D-04 notable-shifts-only instruction |
| PIPE-03 | Location Specialist no longer receives platoon data (moved to Approach Specialist) | **Already satisfied**: `_build_location_input()` at line 528 contains NO platoon data. Prompt at line 149 makes no platoon references. Verification-only task. |
| PIPE-04 | Game Shape specialist skipped for relievers (ctx.role == "RP"), replaced with static placeholder | Conditional guard in `run_specialists()` and/or `_build_game_shape_input()`; static workload stub built from `ctx.workload` per D-05 |
| PIPE-05 | Stuff and Trend specialist inputs include raw data appendix with PitchTypeSummary deltas | Stuff appendix: per-pitch delta table from `ctx.arsenal` (D-07). Trend appendix: per-appearance timeline from `ctx.appearance_pitch_trends` filtered to primary pitches (D-10/D-11) |
| PIPE-06 | Writer input includes Approach Specialist output as 6th specialist analysis | `build_writer_input()` gains `approach` parameter; writer prompt updated from "Five" to "Six" with role-conditional RP text (D-06) |
| PIPE-07 | Auditor runs against Approach Specialist output (6 audits total, up from 5) | `audit_and_revise_specialists()` wired with 6th name/agent; auditor prompt extended with 2 domain-specific categories (D-12/D-13) |
</phase_requirements>

## Architecture Patterns

### Existing Specialist Pattern (replicate for Approach)

Every specialist follows this exact structure. The Approach Specialist must replicate it:

```
1. Prompt constant:   _APPROACH_SPECIALIST_PROMPT (module-level string)
2. Input builder:     _build_approach_input(ctx: PitcherContext) -> str
3. SpecialistOutputs: add `approach: str` field
4. PipelineAgents:    add `approach: Agent[None, str]` field
5. make_pipeline_agents(): approach=_specialist(_APPROACH_SPECIALIST_PROMPT)
6. run_specialists(): add approach_agent param, include in asyncio.gather
7. _get_specialist_input(): add "approach" to builders dict
8. audit_and_revise_specialists(): add "approach" to specialist_names list
9. build_writer_input(): add approach param, include as section
10. _run_pipeline(): wire approach through Phase 1 -> 1.5 -> 2 -> 2.5
```

### Key Code Locations (line numbers from current codebase)

| Component | File | Lines | What to Change |
|-----------|------|-------|---------------|
| Specialist prompts | pipeline.py | 79-264 | Add `_APPROACH_SPECIALIST_PROMPT` after line 264 |
| Auditor prompt | pipeline.py | 271-312 | Add categories 8 and 9 for platoon/count-state claims |
| Writer prompt | pipeline.py | 339-396 | Change "Five" to "Six", add approach description, add RP conditional (D-06) |
| `_build_stuff_input()` | pipeline.py | 445-525 | Append per-pitch delta table (D-07), add anti-recalculation note (D-08/D-09) |
| `_build_location_input()` | pipeline.py | 528-562 | No changes needed (already clean of platoon data) |
| `_build_trend_input()` | pipeline.py | 583-601 | Append per-appearance timeline appendix (D-10/D-11) |
| `_build_game_shape_input()` | pipeline.py | 604-650 | Add RP guard: if `ctx.role == "RP"` return workload stub (D-05) |
| `build_writer_input()` | pipeline.py | 653-673 | Add 6th approach section + RP conditional placeholder |
| `_get_specialist_input()` | pipeline.py | 705-714 | Add "approach" to builders dict |
| `audit_and_revise_specialists()` | pipeline.py | 717-801 | Add "approach" to specialist_names list |
| `SpecialistOutputs` | pipeline.py | 902-908 | Add `approach: str` field |
| `PipelineAgents` | pipeline.py | 925-936 | Add `approach: Agent[None, str]` field |
| `make_pipeline_agents()` | pipeline.py | 939-973 | Add approach agent construction |
| `run_specialists()` | pipeline.py | 980-1017 | Add approach_agent param, include in gather |
| `_run_pipeline()` | pipeline.py | 1020-1128 | Wire approach through entire pipeline, update synthesis string |
| `generate_pipeline_streaming()` | pipeline.py | 1131-1157 | No changes (calls _run_pipeline) |

### Data Available for Approach Specialist Input

The following `PitcherContext` render methods are already implemented and ready to call:

| Method | Returns | Notes |
|--------|---------|-------|
| `ctx._render_platoon_section()` | Platoon shifts markdown | Per-pitch vs-same/vs-opposite usage with deltas |
| `ctx._render_count_splits_section()` | Notable shifts (10+ pp) inline | Pre-filtered by engine, only shows 10+ pp shifts |
| `ctx._render_first_pitch_section()` | First-pitch tendencies | Top 3 by window usage, with season comparison |
| `ctx._render_count_splits_appendix()` | Full count-state table | Full bucket data -- per D-04 do NOT use this, use notable shifts only |

### Data Available for Stuff Appendix (D-07)

`PitchTypeSummary` dataclass fields to include in per-pitch delta table:

| Field | Window | Season | Delta |
|-------|--------|--------|-------|
| `window_velo` / `season_velo` | yes | yes | `velo_delta` (qualitative string) |
| `window_pfx_x` / `season_pfx_x` | yes | yes | `pfx_x_delta` |
| `window_pfx_z` / `season_pfx_z` | yes | yes | `pfx_z_delta` |
| `window_s_plus` / `season_s_plus` | yes | yes | `s_plus_delta` |
| `window_p_plus` / `season_p_plus` | yes | yes | `p_plus_delta` |

### Data Available for Trend Timeline Appendix (D-10/D-11)

`AppearancePitchTrends` (on `ctx.appearance_pitch_trends`) already provides per-appearance records but is a three-way comparison (last start vs window vs prior season), not a per-appearance timeline. The requirement calls for 5-7 most recent appearance snapshots with per-pitch velo/movement data.

**Important**: The existing `ctx.appearance_pitch_trends` only captures the MOST RECENT appearance compared to window and season averages -- it is NOT a multi-appearance timeline. To satisfy D-10 (per-appearance snapshots for last 5-7 appearances), we need either:

1. A new engine function that computes per-appearance snapshots (out of scope per phase boundary -- no new engine computation)
2. Use what's available: the existing `_render_appearance_pitch_trends_section()` plus the workload appearances table as the best available temporal data

**Resolution**: The existing `appearance_pitch_trends` records already contain per-appearance pitch-level data (velocity, movement) grouped by pitch type. The `_render_appearance_pitch_trends_section()` renders a three-way comparison table. For the Trend timeline appendix, we build a markdown table from `ctx.arsenal` deltas (window vs season) as the core temporal signal, supplemented by the appearance pitch trends if available. The 30-day window parameter and >10% usage filter per D-11 can be applied at render time by filtering `ctx.arsenal` to pitches where `window_usage_pct >= 10.0`.

### RP Workload Stub Pattern (D-05)

When `ctx.role == "RP"`, instead of calling the Game Shape agent, return a deterministic string built from:

```python
# Available from ctx.workload:
ctx.workload.appearances  # list[AppearanceWorkload] with game_date, ip, pitch_count, rest_days
ctx.workload.max_consecutive_days
ctx.workload.workload_concern
```

Format as a markdown section like the other specialist outputs (plain text paragraph or compact summary), so the writer can consume it the same way.

### Writer Prompt RP Conditional (D-06)

The writer prompt currently says "INPUT: Five specialist analyses". For Phase 24:

```python
# Build writer prompt dynamically based on role:
role_label = "starter" if ctx.role == "SP" else "reliever"
game_shape_desc = (
    "6. Game shape -- how effectiveness changes within a game (TTO, velocity arc)"
    if ctx.role == "SP"
    else "6. Workload context -- appearance frequency, pitch count trends, rest patterns"
)
```

Single writer prompt with string interpolation, not two separate prompts (D-06).

### Auditor Domain-Specific Categories (D-12/D-13)

Add to `_DATA_AUDITOR_PROMPT` after category 7:

```
8. PLATOON_CLAIM_MISMATCH: The prose states a platoon-specific claim
(e.g., "throws more sliders to lefties") that contradicts the
vs-LHB/vs-RHB data in the input.
Show your work: (1) state the claim, (2) cite the exact platoon
numbers, (3) Pass/Fail.

9. COUNT_STATE_CLAIM_MISMATCH: The prose states a count-state claim
(e.g., "relies on the curveball when behind") that contradicts the
count bucket data in the input.
Show your work: (1) state the claim, (2) cite the exact bucket
numbers, (3) Pass/Fail.
```

These only apply to the Approach Specialist audit. The auditor already receives per-specialist input data (ground truth) alongside the specialist output, so it will naturally see platoon/count data only when auditing the Approach Specialist.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Platoon data rendering | Custom format | `ctx._render_platoon_section()` | Already renders platoon shifts with deltas, tested in Phase 23 |
| Count splits rendering | Custom format | `ctx._render_count_splits_section()` | Already filters to 10+ pp notable shifts, tested in Phase 23 |
| First pitch rendering | Custom format | `ctx._render_first_pitch_section()` | Already renders top 3, tested in Phase 23 |
| Specialist agent definition | Custom Agent setup | `_specialist()` factory in `make_pipeline_agents()` | Handles model, output_type, temperature, defer_model_check |
| Per-specialist audit | Custom audit logic | Existing `audit_and_revise_specialists()` pattern | Just add "approach" to the specialist_names list |

## Common Pitfalls

### Pitfall 1: SpecialistOutputs field ordering breaks asyncio.gather indexing
**What goes wrong:** `run_specialists()` unpacks `asyncio.gather()` results by positional index (results[0], results[1], etc.). If the new `approach` field is added to `SpecialistOutputs` at a different position than its task in the gather, outputs get swapped.
**Why it happens:** NamedTuple/BaseModel field order and gather task order must match.
**How to avoid:** Add `approach` as the LAST field in `SpecialistOutputs` and the LAST task in `asyncio.gather()`. This preserves existing index assignments.
**Warning signs:** Tests pass but the wrong text ends up in the wrong specialist slot.

### Pitfall 2: RP conditional breaks the anchor check synthesis
**What goes wrong:** The anchor check at lines 1092-1098 builds a synthesis string with hardcoded specialist labels. If Game Shape is replaced with a workload stub but the synthesis still says "GAME SHAPE:", the anchor check may flag non-issues.
**Why it happens:** The synthesis string is built after the writer, using specialist outputs from `SpecialistOutputs`.
**How to avoid:** When `ctx.role == "RP"`, the `game_shape` slot in `SpecialistOutputs` should contain the workload stub text (not empty), and the synthesis label should say "WORKLOAD:" or "GAME SHAPE (RP):" to match.
**Warning signs:** Anchor check generates spurious warnings about missing game shape content for RP reports.

### Pitfall 3: Auditor prompt categories 8-9 fire on non-Approach specialists
**What goes wrong:** Categories 8 (PLATOON_CLAIM_MISMATCH) and 9 (COUNT_STATE_CLAIM_MISMATCH) are domain-specific to the Approach Specialist, but the auditor prompt is shared across all 6 audits.
**Why it happens:** The same `_DATA_AUDITOR_PROMPT` is used for every specialist audit.
**How to avoid:** Frame categories 8-9 as conditional: "These categories apply ONLY when the specialist output contains platoon or count-state analysis." Since only the Approach Specialist's input data contains platoon/count data, the auditor will naturally ignore these for other specialists (no matching data to check against).
**Warning signs:** Stuff specialist gets flagged for PLATOON_CLAIM_MISMATCH even though it never references platoon data.

### Pitfall 4: PipelineAgents NamedTuple field addition breaks existing callers
**What goes wrong:** `PipelineAgents` is a NamedTuple. Adding a new field changes the tuple structure. Any code that unpacks it positionally breaks.
**Why it happens:** `_run_pipeline()` accesses agents by name (`agents.stuff`, `agents.approach`), not by position, so this is low risk. But verify no positional unpacking exists.
**How to avoid:** Add `approach` field between `game_shape` and `writer` in PipelineAgents (logical grouping with other specialists). Verify all access is by attribute name.
**Warning signs:** TypeError on tuple unpacking.

### Pitfall 5: build_writer_input signature change breaks callers
**What goes wrong:** `build_writer_input()` currently takes 5 specialist strings. Adding a 6th positional arg breaks existing callers.
**Why it happens:** The function is called in `_run_pipeline()` at line 1057 and imported in `__all__`.
**How to avoid:** Add `approach` as a keyword argument with a sensible position, or add it as the last positional arg and update the single call site in `_run_pipeline()`.
**Warning signs:** TypeError on missing positional argument.

### Pitfall 6: Stuff appendix duplicates data already in the input
**What goes wrong:** `_build_stuff_input()` already includes velo, pfx_x, pfx_z, S+ for each pitch. Adding a "Per-Pitch Delta Table" that repeats all the same numbers bloats the input.
**Why it happens:** D-07 asks for a consolidated table, but the existing Arsenal Physical Profile already has these fields.
**How to avoid:** The appendix table should be a CONSOLIDATED view (one row per pitch with all deltas in columns) rather than repeating the existing prose-style per-pitch blocks. Format as a markdown table at the end of the input with a clear "Raw Data (cite these exact numbers)" label per D-09.
**Warning signs:** Token count doubles for stuff specialist input without new information.

## Code Examples

### Pattern: New specialist agent definition (from existing codebase)

```python
# Source: pipeline.py:953-955 (existing _specialist factory)
def _specialist(prompt: str) -> Agent[None, str]:
    return Agent(model, output_type=str, system_prompt=prompt,
                 model_settings=specialist_settings, defer_model_check=True)
```

### Pattern: Input builder function (from existing codebase)

```python
# Source: pipeline.py:583-601 (existing _build_trend_input)
def _build_trend_input(ctx: PitcherContext) -> str:
    baselines = render_league_baselines(_pitch_types(ctx))
    sections = [
        f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
        baselines,
        "",
        ctx._render_fastball_section(),
        ctx._render_arsenal_section(),
        ctx._render_release_point_section(),
        ctx._render_hard_hit_section(),
    ]
    # ...
    return "\n\n".join(s for s in sections if s)
```

### Pattern: Approach Specialist input builder (new)

```python
def _build_approach_input(ctx: PitcherContext) -> str:
    """Build input for the approach specialist -- platoon, count splits, first pitch."""
    sections = [
        f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
    ]
    # Baseline overall pitch mix for weighting significance (D-04)
    arsenal_lines = ["## Overall Pitch Mix (baseline for weighting shifts)"]
    for p in ctx.arsenal:
        arsenal_lines.append(
            f"- {p.pitch_name} ({p.pitch_type}): "
            f"{p.season_usage_pct:.1f}% season / {p.window_usage_pct:.1f}% recent"
        )
    sections.append("\n".join(arsenal_lines))
    # Platoon, count splits (notable only), first pitch
    sections.append(ctx._render_platoon_section())
    sections.append(ctx._render_count_splits_section())
    sections.append(ctx._render_first_pitch_section())
    return "\n\n".join(s for s in sections if s)
```

### Pattern: RP Game Shape workload stub (new, D-05)

```python
def _build_rp_workload_stub(ctx: PitcherContext) -> str:
    """Build static workload summary for relievers (no LLM call)."""
    wl = ctx.workload
    sorted_apps = sorted(wl.appearances, key=lambda a: a.game_date, reverse=True)
    lines = [f"## Workload Context ({ctx.pitcher_name}, RP)"]
    lines.append(f"- Appearances: {len(wl.appearances)}")
    if wl.max_consecutive_days >= 2:
        lines.append(f"- Max consecutive days: {wl.max_consecutive_days}")
    if wl.workload_concern:
        lines.append("- **Workload concern: 3+ consecutive days pitched**")
    # Recent appearances table
    lines.append("\n| Date | IP | Pitches | Rest |")
    lines.append("|------|----|---------|------|")
    for a in sorted_apps[:7]:  # Cap at 7 most recent
        rest = f"{a.rest_days}d" if a.rest_days is not None else "--"
        lines.append(f"| {a.game_date} | {a.ip} | {a.pitch_count} | {rest} |")
    # Pitch count trend
    if len(sorted_apps) >= 3:
        recent_pcs = [a.pitch_count for a in sorted_apps[:3]]
        avg_pc = sum(recent_pcs) / len(recent_pcs)
        lines.append(f"\n- Avg pitch count (last 3): {avg_pc:.0f}")
    return "\n".join(lines)
```

### Pattern: Conditional writer prompt section (D-06)

```python
# In writer prompt construction, use string interpolation:
role_desc = "starter" if ctx.role == "SP" else "reliever"
section_6 = (
    "6. Game shape -- how effectiveness changes within a game (TTO, velocity arc)"
    if ctx.role == "SP"
    else "6. Workload context -- appearance frequency, pitch count trends, rest patterns (reliever)"
)
rp_directive = (
    ""
    if ctx.role == "SP"
    else "\nYou are synthesizing a scouting report for a reliever. "
    "Do not fabricate TTO analysis; the workload section replaces Game Shape."
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 5 parallel specialists | 6 parallel specialists (adding Approach) | Phase 24 | Richer platoon/count analysis |
| All pitchers get Game Shape | RP skips Game Shape, gets workload stub | Phase 24 | No TTO noise for relievers |
| Specialists get computed data only | Specialists get raw data appendices | Phase 24 | Better grounding, less hallucination |
| 5 audits | 6 audits with 2 new domain-specific categories | Phase 24 | Approach Specialist claims verified |

## Open Questions

1. **Per-appearance timeline for Trend Specialist (D-10)**
   - What we know: `ctx.appearance_pitch_trends` provides a three-way comparison (last start vs window vs prior), not a multi-appearance timeline. The existing `_render_appearance_pitch_trends_section()` is already included in `_build_trend_input()`.
   - What's unclear: D-10 specifies "per-appearance snapshots for the last 5-7 appearances" but the engine does not currently produce per-appearance historical data beyond the most recent appearance comparison.
   - Recommendation: The existing appearance pitch trends data IS the best available temporal signal. Enhance the Trend appendix by leveraging what exists (`_render_appearance_pitch_trends_section`) plus the workload appearances table (dates, pitch counts) as a timeline proxy. If the user wants richer per-appearance data, that's a new engine feature (out of scope per phase boundary: "No new engine computation").

2. **Writer prompt construction approach**
   - What we know: D-06 says "single writer prompt with role-aware insertion, not two separate prompts." The current `_WRITER_PROMPT` is a module-level constant string.
   - What's unclear: Whether to convert the constant to a function that takes ctx.role, or use a template with f-string substitution.
   - Recommendation: Convert `_WRITER_PROMPT` to a function `_build_writer_prompt(role: str) -> str` that returns the complete prompt with role-conditional sections interpolated. This keeps the pattern clean and testable. The writer agent would then be constructed per-run rather than at `make_pipeline_agents()` time, or the prompt could be passed as user message context.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_pipeline.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | Approach input contains platoon, count splits, first pitch data | unit | `uv run pytest tests/test_pipeline.py::TestBuildApproachInput -x` | Wave 0 |
| PIPE-02 | Approach prompt prioritizes 10+ pp shifts | unit (prompt content check) | `uv run pytest tests/test_pipeline.py::TestApproachPrompt -x` | Wave 0 |
| PIPE-03 | Location input has no platoon data | unit | `uv run pytest tests/test_pipeline.py::TestLocationRvNoYoY::test_location_input_no_platoon -x` | Wave 0 (extend existing class) |
| PIPE-04 | Game Shape skipped for RP, returns workload stub | unit | `uv run pytest tests/test_pipeline.py::TestRPGameShapeSkip -x` | Wave 0 |
| PIPE-05 | Stuff/Trend inputs include raw data appendix | unit | `uv run pytest tests/test_pipeline.py::TestStuffAppendix -x` | Wave 0 |
| PIPE-06 | Writer input includes 6th specialist, RP conditional | unit | `uv run pytest tests/test_pipeline.py::TestBuildWriterInput -x` | Wave 0 |
| PIPE-07 | Auditor runs 6 audits with domain-specific categories | smoke | `uv run pytest tests/test_pipeline.py::TestAuditAndReviseSpecialists -x` | Partial (extend existing) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_pipeline.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pipeline.py::TestBuildApproachInput` -- covers PIPE-01 (approach input builder outputs)
- [ ] `tests/test_pipeline.py::TestApproachPrompt` -- covers PIPE-02 (prompt content assertions)
- [ ] `tests/test_pipeline.py::TestRPGameShapeSkip` -- covers PIPE-04 (RP conditional + workload stub)
- [ ] `tests/test_pipeline.py::TestStuffAppendix` -- covers PIPE-05 (raw data appendix in stuff/trend inputs)
- [ ] `tests/test_pipeline.py::TestBuildWriterInput` -- covers PIPE-06 (6 sections, RP conditional)
- [ ] Extend `_make_pipeline_ctx()` helper with platoon_mix, count_splits, first_pitch populated for testing
- [ ] Extend `_make_pipeline_ctx()` helper to support `role="RP"` variant

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python 3.14+, polars, pydantic-ai, Claude -- all changes in existing files
- **Data format**: Static parquet + CSV, no live API calls
- **Entry point**: `uv run` for all commands
- **Code style**: ruff configured (pyproject.toml), snake_case for functions, PascalCase for classes
- **Naming**: Use existing naming patterns (e.g., `_build_*_input`, `_*_SPECIALIST_PROMPT`)
- **GSD Workflow**: All changes through GSD workflow
- **No new dependencies**: This phase adds no packages -- all changes are in pipeline.py and its tests

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `pipeline.py` (1157 lines), `context.py` (800+ lines), `engine.py` (3600+ lines)
- `tests/test_pipeline.py` (707 lines) -- existing test patterns
- `24-CONTEXT.md` -- user decisions D-01 through D-14
- `REQUIREMENTS.md` -- PIPE-01 through PIPE-07 definitions

### Secondary (MEDIUM confidence)
- pydantic-ai `Agent[None, str]` pattern -- verified from codebase usage (not external docs needed; pattern is fully established in existing code)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all changes in existing codebase
- Architecture: HIGH - exact pattern to follow established in existing 5 specialists
- Pitfalls: HIGH - identified from direct code analysis of integration points
- Data availability: HIGH - all PitcherContext fields verified present from Phase 23

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable -- internal codebase, no external dependency changes)
