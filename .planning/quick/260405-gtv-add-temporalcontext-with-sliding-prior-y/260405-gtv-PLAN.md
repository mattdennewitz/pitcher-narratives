---
phase: quick-260405-gtv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/pitcher_narratives/engine.py
  - src/pitcher_narratives/context.py
  - src/pitcher_narratives/report.py
  - src/pitcher_narratives/pipeline.py
  - src/pitcher_narratives/analyst.py
autonomous: true
requirements: [GTV-01]
must_haves:
  truths:
    - "LLM receives a Temporal Context section in every prompt that identifies analysis date, per-season appearance counts and IP, and a prior-year relevance tier"
    - "Prior-year relevance tier gates how much weight the LLM gives to last season's workload in its narrative"
    - "All narrative-generating prompts (synthesizer, editor, pipeline specialists, analyst, answerer) include temporal grounding instructions"
  artifacts:
    - path: "src/pitcher_narratives/engine.py"
      provides: "TemporalContext dataclass and compute_temporal_context() function"
      contains: "class TemporalContext"
    - path: "src/pitcher_narratives/context.py"
      provides: "temporal field on PitcherContext, _render_temporal_section(), wired into to_prompt() and assemble_pitcher_context()"
      contains: "temporal: TemporalContext"
    - path: "src/pitcher_narratives/report.py"
      provides: "Temporal grounding rule in _SYNTHESIZER_PROMPT and _EDITOR_PROMPT"
      contains: "Temporal Grounding"
    - path: "src/pitcher_narratives/pipeline.py"
      provides: "Temporal grounding in _TREND_SPECIALIST_PROMPT, _GAME_SHAPE_SPECIALIST_PROMPT, and _WRITER_PROMPT"
      contains: "Temporal Grounding"
    - path: "src/pitcher_narratives/analyst.py"
      provides: "Temporal grounding in ANALYST_INSTRUCTIONS and ANSWERER_INSTRUCTIONS"
      contains: "Temporal Grounding"
  key_links:
    - from: "src/pitcher_narratives/context.py"
      to: "src/pitcher_narratives/engine.py"
      via: "import compute_temporal_context, TemporalContext"
      pattern: "from pitcher_narratives.engine import.*TemporalContext"
    - from: "src/pitcher_narratives/context.py"
      to: "PitcherContext.to_prompt()"
      via: "_render_temporal_section() called after title, before executive summary"
      pattern: "_render_temporal_section"
---

<objective>
Add TemporalContext with sliding prior-year relevance to ground LLM narratives against the seasonal timeline, preventing hallucinated fatigue/workload arcs.

Purpose: The LLM sees two years of data but has no sense of where in the season it is. It stitches prior-year workload into a fake fatigue narrative (e.g., "cumulative late-season fatigue" in April with 5 appearances). TemporalContext tells the LLM the analysis date, per-season appearance counts and IP totals, and a relevance tier that gates how much weight to give last season's workload.

Output: TemporalContext dataclass, compute function, rendered prompt section, and temporal grounding rules in all 7 narrative-generating prompts.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/pitcher_narratives/engine.py (dataclasses near line 975-1005, compute_workload_context near line 1958, __all__ near line 27)
@src/pitcher_narratives/context.py (full file — PitcherContext model, assemble_pitcher_context, to_prompt, imports)
@src/pitcher_narratives/report.py (lines 75-134 for _SYNTHESIZER_PROMPT, lines 226-305 for _EDITOR_PROMPT)
@src/pitcher_narratives/pipeline.py (lines 235-282 for _TREND_SPECIALIST_PROMPT and _GAME_SHAPE_SPECIALIST_PROMPT, lines 357-414 for _WRITER_PROMPT)
@src/pitcher_narratives/analyst.py (lines 98-218 for ANALYST_INSTRUCTIONS, lines 516-560 for ANSWERER_INSTRUCTIONS)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add TemporalContext dataclass, compute function, and wire into PitcherContext</name>
  <files>src/pitcher_narratives/engine.py, src/pitcher_narratives/context.py</files>
  <action>
**In engine.py:**

1. Add `TemporalContext` dataclass right after `WorkloadContext` (after line ~1003). Fields:
```python
@dataclass
class TemporalContext:
    """Temporal grounding for LLM narratives — prevents cross-season hallucination."""

    analysis_date: date
    current_season: int
    current_season_appearances: int
    current_season_first_date: str
    """ISO date of first appearance this season."""
    current_season_ip: str
    """Baseball-notation IP total for current season."""
    prior_season: int
    prior_season_appearances: int
    prior_season_ip: str
    """Baseball-notation IP total for prior season."""
    prior_year_relevance: str
    """'HIGH', 'MODERATE', or 'LOW'."""
    prior_year_relevance_reason: str
    """Human-readable explanation for the LLM."""
```

Import `date` from `datetime` at the top of engine.py (add to existing imports).

2. Add `compute_temporal_context(data: PitcherData) -> TemporalContext` function after `compute_workload_context`. Implementation:
   - Use `data.appearances` DataFrame which has `game_date` (date type) and `game_pk` columns.
   - Derive season year from `game_date.dt.year()` (polars expression).
   - Find the max year as `current_season`, `current_season - 1` as `prior_season`.
   - Filter appearances by season year, count rows for appearances per season.
   - Sum IP per season using a helper `_sum_baseball_ip(ip_strings: list[str]) -> str` that:
     - Converts each baseball-notation IP string to thirds (split on ".", whole*3 + remainder).
     - Sums all thirds.
     - Converts back: `f"{total // 3}.{total % 3}"`.
   - To get IP strings per appearance, call `_compute_ip(data.statcast, game_pk)` for each game_pk in the season's appearances. (This function already exists in engine.py at line 1635.)
   - Get `current_season_first_date` from the min game_date of current season appearances (format as ISO string).
   - Compute prior-year relevance tier:
     - `current_season_appearances < 10` -> relevance="HIGH", reason=f"Current season sample is too small to establish its own workload narrative. {prior_season} workload ({prior_apps} G / {prior_ip} IP) is plausible residual context, but do not treat the two seasons as a continuous timeline."
     - `10 <= current_season_appearances <= 30` -> relevance="MODERATE", reason="Patterns are emerging but sample is still growing. Prior year adds context for year-over-year comparison."
     - `current_season_appearances > 30` -> relevance="LOW", reason="Current season has enough volume to carry its own workload narrative. Use prior year for trend comparison only, not workload narrative."
   - Handle edge case: if no prior season data exists, set `prior_season_appearances=0`, `prior_season_ip="0.0"`, and adjust the reason to note no prior season data is available.
   - Use `date.today()` for `analysis_date` (the actual date the report is generated).

3. Add `"TemporalContext"` and `"compute_temporal_context"` to `__all__` list in engine.py (alphabetical order within existing entries).

**In context.py:**

4. Add `TemporalContext` and `compute_temporal_context` to the import block from `pitcher_narratives.engine`.

5. Add `temporal: TemporalContext` field to `PitcherContext` model (after the `workload` field, before `tto`).

6. Add `_render_temporal_section(self) -> str` method to PitcherContext. Render format:
```
## Temporal Context
- Analysis date: {self.temporal.analysis_date}
- {current_season} season: {current_season_appearances} appearances, {current_season_ip} IP since {current_season_first_date} (early season)
- {prior_season} season: {prior_season_appearances} appearances, {prior_season_ip} IP (completed)
- Prior-year workload relevance: {prior_year_relevance} -- {prior_year_relevance_reason}
```
The "(early season)" annotation: use "early season" if appearances < 10, "mid season" if 10-60, "full season" if > 60. If prior_season_appearances == 0, omit the prior season line.

7. In `to_prompt()`, insert `sections.append(self._render_temporal_section())` right after the title line (line ~89) and BEFORE the executive summary call (line ~92). This makes it the first real section the LLM reads.

8. In `assemble_pitcher_context()`, call `compute_temporal_context(data)` and pass the result as the `temporal=` kwarg to the PitcherContext constructor.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "from pitcher_narratives.engine import TemporalContext, compute_temporal_context; print('engine OK')" && uv run python -c "from pitcher_narratives.context import PitcherContext; print('context OK')"</automated>
  </verify>
  <done>TemporalContext dataclass exists in engine.py with all fields. compute_temporal_context() splits appearances by season, sums IP correctly using baseball notation, and returns appropriate relevance tier. PitcherContext has temporal field, _render_temporal_section() renders the section, to_prompt() includes it before Executive Summary, and assemble_pitcher_context() wires it in. Both modules import cleanly.</done>
</task>

<task type="auto">
  <name>Task 2: Add temporal grounding rules to all narrative-generating prompts</name>
  <files>src/pitcher_narratives/report.py, src/pitcher_narratives/pipeline.py, src/pitcher_narratives/analyst.py</files>
  <action>
**In report.py:**

1. In `_SYNTHESIZER_PROMPT` (starts at line 75), insert a new rule 0 before the existing rule 1 ("Identify the Fastball Baseline"). Add right after the "INSTRUCTIONS:" line:

```
0. Temporal Grounding: Read the "Temporal Context" section in the data \
first. The "prior-year workload relevance" level tells you how much \
weight to give last season's workload in your analysis. When it says \
LOW, do not build workload narratives from prior-season data. When it \
says HIGH, prior-year workload is plausible residual context but the \
two seasons are NOT a continuous timeline -- an offseason separates \
them. A pitcher with a handful of early-April appearances is not \
fatigued from this season's workload.

```

2. In `_EDITOR_PROMPT` (starts at line 226), insert a new rule 1.5 after rule 1 ("Find the Thread", ends around line 248) and before rule 2 ("Structure"):

```
1.5. Temporal Grounding: The data includes a "Temporal Context" section \
with a prior-year relevance level. Follow it. Do not infer cumulative \
fatigue, late-season workload, or mechanical drift across season \
boundaries unless the relevance level supports it. Scale seasonal \
narrative to the actual sample: a handful of early-season appearances \
does not support a workload story.

```

**In pipeline.py:**

3. In `_TREND_SPECIALIST_PROMPT` (starts at line 235), add to the "Rules:" section (before "Lead with the single most important change"):

```
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section. \
Respect the prior-year relevance level. Do not frame window-vs-season \
deltas as long-term trends when the current season has few appearances. \
Do not connect prior-season workload to current-season patterns as \
cause-and-effect.
```

4. In `_GAME_SHAPE_SPECIALIST_PROMPT` (starts at line 260), add to the "Rules:" section (before "Lead with the most notable within-game pattern"):

```
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section. \
Respect the prior-year relevance level. Do not attribute within-game \
patterns to cumulative seasonal fatigue if the current season is young. \
A pitcher with 5 early-April appearances is not showing late-season wear.
```

5. In `_WRITER_PROMPT` (starts at line 357), add to the "CONSTRAINTS:" section (after "Scale confidence to sample size"):

```
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section \
with a prior-year relevance level. Follow it. When relevance is LOW, \
prior-season workload does not drive narrative. When relevance is HIGH, \
prior year is residual context but two seasons are NOT a continuous \
timeline. Do not hallucinate cumulative fatigue across an offseason.
```

**In analyst.py:**

6. In `ANALYST_INSTRUCTIONS` (starts at line 98), add after the "FIND THE THREAD:" paragraph (before "HOW THE MODEL THINKS"):

```
TEMPORAL GROUNDING:
The scouting context includes a "Temporal Context" section with a \
prior-year workload relevance level (HIGH, MODERATE, or LOW). This \
tells you how much weight to give last season's workload when answering \
questions. When it says LOW, do not build workload narratives from \
prior-season data. When it says HIGH, prior-year workload is plausible \
residual context but two seasons are NOT a continuous timeline -- an \
offseason separates them. A pitcher with a handful of early-season \
appearances is not fatigued from this season's workload. Scale your \
seasonal narrative to the actual sample size.

```

7. In `ANSWERER_INSTRUCTIONS` (starts at line 516), add after the "APPROACH:" section (before "INTERPRETATION RULES:"):

```
TEMPORAL GROUNDING:
The specialist analyses are grounded against a "Temporal Context" that \
includes a prior-year relevance level. Follow it. Do not infer \
cumulative fatigue, late-season workload, or mechanical drift across \
season boundaries unless the relevance level supports it. Scale \
seasonal narrative to the actual sample.

```
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "
from pitcher_narratives.report import _SYNTHESIZER_PROMPT, _EDITOR_PROMPT
from pitcher_narratives.pipeline import _TREND_SPECIALIST_PROMPT, _GAME_SHAPE_SPECIALIST_PROMPT, _WRITER_PROMPT
from pitcher_narratives.analyst import ANALYST_INSTRUCTIONS, ANSWERER_INSTRUCTIONS
assert 'Temporal Grounding' in _SYNTHESIZER_PROMPT, 'synthesizer missing'
assert 'Temporal Grounding' in _EDITOR_PROMPT, 'editor missing'
assert 'TEMPORAL GROUNDING' in _TREND_SPECIALIST_PROMPT, 'trends missing'
assert 'TEMPORAL GROUNDING' in _GAME_SHAPE_SPECIALIST_PROMPT, 'game shape missing'
assert 'TEMPORAL GROUNDING' in _WRITER_PROMPT, 'writer missing'
assert 'TEMPORAL GROUNDING' in ANALYST_INSTRUCTIONS, 'analyst missing'
assert 'TEMPORAL GROUNDING' in ANSWERER_INSTRUCTIONS, 'answerer missing'
print('All 7 prompts have temporal grounding')
"</automated>
  </verify>
  <done>All 7 narrative-generating prompts (synthesizer, editor, trend specialist, game shape specialist, writer, analyst, answerer) contain temporal grounding instructions that reference the "Temporal Context" section and instruct the LLM to follow the prior-year relevance tier. No prompt invents fatigue narratives from early-season data.</done>
</task>

<task type="auto">
  <name>Task 3: End-to-end smoke test with a real pitcher</name>
  <files>none (verification only)</files>
  <action>
Run the full context assembly pipeline for a known pitcher (use Andres Munoz, pitcher_id=660882, or another available pitcher in the data) and verify:

1. `load_pitcher_data()` succeeds.
2. `assemble_pitcher_context()` succeeds and produces a PitcherContext with a populated `temporal` field.
3. `to_prompt()` renders a "## Temporal Context" section with correct analysis date, per-season appearance/IP counts, and a relevance tier.
4. The temporal section appears before "## Executive Summary" in the rendered prompt.

Run this as a Python script:
```python
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.context import assemble_pitcher_context

data = load_pitcher_data(660882)
ctx = assemble_pitcher_context(data)
prompt = ctx.to_prompt()

# Verify temporal field
assert ctx.temporal is not None
assert ctx.temporal.prior_year_relevance in ("HIGH", "MODERATE", "LOW")
assert ctx.temporal.current_season_appearances > 0

# Verify rendered section
assert "## Temporal Context" in prompt
temporal_pos = prompt.index("## Temporal Context")
exec_pos = prompt.index("## Executive Summary")
assert temporal_pos < exec_pos, "Temporal Context must precede Executive Summary"
print("Temporal section rendered:")
start = temporal_pos
end = prompt.index("\n\n", temporal_pos)
print(prompt[start:end])
print("\nAll checks passed.")
```

If pitcher 660882 is not available in the local data, find an available pitcher ID from the parquet files and use that instead.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.context import assemble_pitcher_context
data = load_pitcher_data(660882)
ctx = assemble_pitcher_context(data)
prompt = ctx.to_prompt()
assert ctx.temporal is not None
assert ctx.temporal.prior_year_relevance in ('HIGH', 'MODERATE', 'LOW')
assert '## Temporal Context' in prompt
t = prompt.index('## Temporal Context')
e = prompt.index('## Executive Summary')
assert t < e
print('E2E OK: temporal=' + ctx.temporal.prior_year_relevance + ', apps=' + str(ctx.temporal.current_season_appearances))
"</automated>
  </verify>
  <done>End-to-end pipeline produces a PitcherContext with a correct TemporalContext, renders the Temporal Context section before Executive Summary, and the relevance tier matches the appearance count.</done>
</task>

</tasks>

<verification>
1. All modules import cleanly: `uv run python -c "from pitcher_narratives.context import assemble_pitcher_context; from pitcher_narratives.engine import compute_temporal_context, TemporalContext"`
2. All 7 prompts contain temporal grounding: verified in Task 2 automated check.
3. End-to-end smoke test passes with real data: verified in Task 3.
4. Temporal Context section appears before Executive Summary in rendered prompt.
</verification>

<success_criteria>
- TemporalContext dataclass in engine.py with all specified fields
- compute_temporal_context() correctly splits by season, sums baseball-notation IP, and assigns relevance tier
- PitcherContext.to_prompt() renders "## Temporal Context" as the first section after the title
- All 7 narrative-generating prompts include temporal grounding instructions
- End-to-end pipeline works with real pitcher data
</success_criteria>

<output>
After completion, create `.planning/quick/260405-gtv-add-temporalcontext-with-sliding-prior-y/260405-gtv-SUMMARY.md`
</output>
