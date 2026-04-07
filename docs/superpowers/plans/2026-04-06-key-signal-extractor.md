# Key Signal Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a signal extractor agent that bridges the gap between specialist outputs and the writer/anchor checker, restoring the Key Signal validation loop lost when the old synthesizer was replaced.

**Architecture:** A new `KeySignals` Pydantic model captures 2 primary (required) and 6 secondary (optional) cross-specialist patterns. A mini-model agent extracts these from clean specialist outputs. The signals feed both the writer (as narrative priorities) and the anchor checker (as validation targets with primary/secondary enforcement tiers).

**Tech Stack:** Python, pydantic, pydantic-ai, pytest

---

### Task 1: KeySignals Model + render helper

**Files:**
- Create: `src/pitcher_narratives/signals.py`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test for KeySignals model**

```python
# tests/test_signals.py
"""Tests for key signal extraction model and rendering."""

from pitcher_narratives.signals import KeySignals, render_key_signals


class TestKeySignals:
    def test_required_fields_only(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135 with new gyro shape",
            top_concern="Fastball velo down 2.1 mph from season baseline",
        )
        assert ks.top_improvement is not None
        assert ks.top_concern is not None
        assert ks.development_pitch is None
        assert ks.specialist_tension is None
        assert ks.arsenal_dependency is None
        assert ks.connected_changes is None
        assert ks.platoon_vulnerability is None
        assert ks.sample_size_caution is None

    def test_all_fields_populated(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
            development_pitch="Changeup has S+ 118 but L+ 72, would solve RHB platoon gap",
            specialist_tension="Stuff says curveball is elite (S+ 128) but run value shows +1.2 xRV100",
            arsenal_dependency="Slider accounts for 68% of whiffs, rest of arsenal is replacement-level",
            connected_changes="Velo drop, S+ drop, and increased hard contact all point to fatigue pattern",
            platoon_vulnerability="P+ vs LHB is 82 with no secondary weapon to that side",
            sample_size_caution="Slider S+ spike based on 34 pitches over 2 appearances",
        )
        assert ks.development_pitch is not None
        assert ks.specialist_tension is not None


class TestRenderKeySignals:
    def test_required_only(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
        )
        rendered = render_key_signals(ks)
        assert "## Key Signals" in rendered
        assert "- Top Improvement:" in rendered
        assert "- Top Concern:" in rendered
        assert "Development Pitch" not in rendered
        assert "Specialist Tension" not in rendered

    def test_includes_populated_optional(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
            specialist_tension="Stuff says curveball elite but run value disagrees",
        )
        rendered = render_key_signals(ks)
        assert "- Specialist Tension:" in rendered

    def test_omits_none_fields(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
            development_pitch=None,
        )
        rendered = render_key_signals(ks)
        assert "Development Pitch" not in rendered
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pitcher_narratives.signals'`

- [ ] **Step 3: Implement KeySignals model and render_key_signals**

```python
# src/pitcher_narratives/signals.py
"""Key signal extraction model and rendering.

The signal extractor identifies cross-specialist patterns that no single
specialist can see: tensions between analysts, arsenal dependencies,
connected changes, and sample size caveats. These signals guide the
writer's narrative priorities and give the anchor checker concrete
validation targets.
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = [
    "KeySignals",
    "SIGNAL_EXTRACTOR_PROMPT",
    "render_key_signals",
]


class KeySignals(BaseModel):
    """Cross-specialist narrative signals extracted from clean specialist outputs.

    Primary signals (required) are anchor-enforced via MISSED_SIGNAL.
    Secondary signals (optional) are advisory via UNDERWEIGHTED.
    """

    # Primary signals (required)
    top_improvement: str
    top_concern: str

    # Secondary signals (optional)
    development_pitch: str | None = None
    specialist_tension: str | None = None
    arsenal_dependency: str | None = None
    connected_changes: str | None = None
    platoon_vulnerability: str | None = None
    sample_size_caution: str | None = None


_FIELD_LABELS: dict[str, str] = {
    "top_improvement": "Top Improvement",
    "top_concern": "Top Concern",
    "development_pitch": "Development Pitch",
    "specialist_tension": "Specialist Tension",
    "arsenal_dependency": "Arsenal Dependency",
    "connected_changes": "Connected Changes",
    "platoon_vulnerability": "Platoon Vulnerability",
    "sample_size_caution": "Sample Size Caution",
}


def render_key_signals(signals: KeySignals) -> str:
    """Render populated key signals as a labeled bullet list.

    Omits None fields entirely so the writer and anchor checker
    only see signals that are present.
    """
    lines = ["## Key Signals"]
    for field_name, label in _FIELD_LABELS.items():
        value = getattr(signals, field_name)
        if value is not None:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signals.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/signals.py tests/test_signals.py
git commit -m "feat: add KeySignals model and render helper"
```

---

### Task 2: Signal Extractor Prompt

**Files:**
- Modify: `src/pitcher_narratives/signals.py`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test for prompt content**

Add to `tests/test_signals.py`:

```python
from pitcher_narratives.signals import SIGNAL_EXTRACTOR_PROMPT


class TestSignalExtractorPrompt:
    def test_mentions_all_signal_types(self):
        for keyword in [
            "top_improvement", "top_concern", "development_pitch",
            "specialist_tension", "arsenal_dependency", "connected_changes",
            "platoon_vulnerability", "sample_size_caution",
        ]:
            assert keyword in SIGNAL_EXTRACTOR_PROMPT

    def test_instructs_null_for_absent(self):
        assert "null" in SIGNAL_EXTRACTOR_PROMPT

    def test_instructs_no_invention(self):
        assert "invent" in SIGNAL_EXTRACTOR_PROMPT.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signals.py::TestSignalExtractorPrompt -v`
Expected: FAIL (SIGNAL_EXTRACTOR_PROMPT is exported but not yet defined with content)

- [ ] **Step 3: Implement the prompt**

Add to `src/pitcher_narratives/signals.py`, after the `render_key_signals` function:

```python
SIGNAL_EXTRACTOR_PROMPT = """\
You are a cross-specialist pattern detector for a baseball analytics \
pipeline. You receive five specialist analyses of a pitcher's recent \
window (stuff, location, run value, trends, game shape). Your job is \
to identify patterns that span multiple specialists.

Extract these signals:

PRIMARY (always provide — there is always a best and worst signal):
- top_improvement: The single most important positive finding across \
all specialists. Cite the pitch type and metric.
- top_concern: The single most important negative finding across \
all specialists. Cite the pitch type and metric.

SECONDARY (provide ONLY when the pattern is genuinely present, \
otherwise leave as null):
- development_pitch: A pitch with high S+ (>110) but low L+ (<90) \
that would solve a documented platoon weakness. Name the pitch, \
cite S+ and L+, and identify which platoon gap it addresses. \
If nothing fits, null.
- specialist_tension: Where two specialists disagree about the same \
pitch. Example: stuff says the curveball is elite (S+ 128) but run \
value shows it bleeding runs (+1.2 xRV100). Name both specialists \
and their conflicting assessments. If all specialists agree, null.
- arsenal_dependency: If one pitch is carrying the entire profile \
while the rest is replacement-level. Cite the pitch and the evidence \
(e.g., whiff share, xRV100 gap). If the arsenal is balanced, null.
- connected_changes: When multiple specialists are reporting different \
facets of the same underlying shift. Example: trend sees velo drop, \
stuff sees S+ drop, run value sees more hard contact — all one \
pattern. Name the thread. If changes are independent, null.
- platoon_vulnerability: A clear weakness against one handedness \
that the data suggests is not being addressed. Cite P+ or pitch mix \
splits. If platoon splits are balanced, null.
- sample_size_caution: When the single strongest finding (whether \
improvement or concern) rests on thin data. Cite the sample size. \
If the key findings have adequate samples, null.

RULES:
- Cite specific pitch types and metrics in every field.
- Do not invent patterns — only surface what the specialists \
explicitly reported.
- Each field is ONE sentence. Be specific, not vague.
- Do not duplicate the same finding across multiple fields."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signals.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/signals.py tests/test_signals.py
git commit -m "feat: add signal extractor prompt"
```

---

### Task 3: Update anchor.py — UNDERWEIGHTED category + revised check #1

**Files:**
- Modify: `src/pitcher_narratives/anchor.py:26-53`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test for UNDERWEIGHTED category**

Add to `tests/test_signals.py`:

```python
from pitcher_narratives.anchor import AnchorWarning, WarningCategory


class TestAnchorWarningCategory:
    def test_underweighted_is_valid(self):
        w = AnchorWarning(category="UNDERWEIGHTED", description="test")
        assert w.category == "UNDERWEIGHTED"

    def test_missed_signal_still_valid(self):
        w = AnchorWarning(category="MISSED_SIGNAL", description="test")
        assert w.category == "MISSED_SIGNAL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signals.py::TestAnchorWarningCategory -v`
Expected: FAIL with `ValidationError` — `"UNDERWEIGHTED"` is not in the current `WarningCategory` Literal

- [ ] **Step 3: Update WarningCategory and ANCHOR_PROMPT**

In `src/pitcher_narratives/anchor.py`, replace:

```python
WarningCategory = Literal["MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED"]
"""Anchor check warning categories matching ANCHOR_PROMPT output format."""
```

with:

```python
WarningCategory = Literal["MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED", "UNDERWEIGHTED"]
"""Anchor check warning categories matching ANCHOR_PROMPT output format."""
```

In the same file, replace the ANCHOR_PROMPT check #1 block (lines 34-36):

```python
1. Missed Key Signals: The synthesis has a "Key Signal" section with the \
most important improvement, concern, and development pitch. If the capsule \
ignores any of these entirely, flag it.
```

with:

```python
1. Missed Key Signals: The synthesis includes a Key Signals section with \
primary and secondary findings. Primary signals (Top Improvement, Top \
Concern) are mandatory — if the capsule ignores either entirely, flag it \
as MISSED_SIGNAL. Secondary signals (Development Pitch, Specialist \
Tension, Arsenal Dependency, Connected Changes, Platoon Vulnerability, \
Sample Size Caution) are advisory — if the capsule ignores a populated \
secondary signal, flag it as UNDERWEIGHTED.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signals.py::TestAnchorWarningCategory -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Run existing anchor-related tests to check for regressions**

Run: `uv run pytest tests/ -v -k "anchor or pipeline"`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/anchor.py tests/test_signals.py
git commit -m "feat: add UNDERWEIGHTED warning category and update anchor check #1"
```

---

### Task 4: Wire signal extractor into PipelineAgents + PipelineResult

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:68-73` (`__all__`)
- Modify: `src/pitcher_narratives/pipeline.py:975-982` (`PipelineResult`)
- Modify: `src/pitcher_narratives/pipeline.py:989-1046` (`PipelineAgents`, `make_pipeline_agents`)
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test for signal_extractor in PipelineAgents**

Add to `tests/test_pipeline.py`, in the existing `TestMakePipelineAgents` class:

```python
    def test_has_signal_extractor(self):
        agents = make_pipeline_agents("gemini", "high")
        assert agents.signal_extractor is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::TestMakePipelineAgents::test_has_signal_extractor -v`
Expected: FAIL with `AttributeError: 'PipelineAgents' object has no attribute 'signal_extractor'`

- [ ] **Step 3: Add signal_extractor to PipelineAgents and make_pipeline_agents**

In `src/pitcher_narratives/pipeline.py`, add the import at the top with the other anchor imports:

```python
from pitcher_narratives.signals import (
    KeySignals,
    SIGNAL_EXTRACTOR_PROMPT,
    render_key_signals,
)
```

Update `__all__` (line 68-73) to include `"KeySignals"`:

```python
__all__ = [
    "AuditFlag", "AuditResult", "ExecutiveSummary", "KeySignals",
    "PipelineAgents", "PipelineResult",
    "UserPrompt", "audit_and_revise_specialists", "build_writer_input",
    "generate_pipeline_streaming", "make_pipeline_agents", "run_specialists",
    "write_pipeline_data_file",
]
```

Add `signal_extractor` field to `PipelineAgents` (after `summary`):

```python
class PipelineAgents(NamedTuple):
    """All agents used by the multi-agent pipeline."""

    stuff: Agent[None, str]
    location: Agent[None, str]
    runvalue: Agent[None, str]
    trends: Agent[None, str]
    game_shape: Agent[None, str]
    writer: Agent[None, str]
    auditor: Agent[None, AuditResult]
    anchor: Agent[None, AnchorResult]
    summary: Agent[None, str]
    signal_extractor: Agent[None, KeySignals]
```

Add the agent creation in `make_pipeline_agents()`, in the return statement:

```python
    return PipelineAgents(
        stuff=_specialist(_STUFF_SPECIALIST_PROMPT),
        location=_mini_specialist(_LOCATION_SPECIALIST_PROMPT),
        runvalue=_mini_specialist(_RUNVALUE_SPECIALIST_PROMPT),
        trends=_mini_specialist(_TREND_SPECIALIST_PROMPT),
        game_shape=_mini_specialist(_GAME_SHAPE_SPECIALIST_PROMPT),
        writer=_writer(_WRITER_PROMPT),
        auditor=Agent(mini_model, output_type=AuditResult, system_prompt=_DATA_AUDITOR_PROMPT,
                      model_settings=checker_settings, retries=5, defer_model_check=True),
        anchor=Agent(mini_model, output_type=AnchorResult, system_prompt=ANCHOR_PROMPT,
                     model_settings=checker_settings, defer_model_check=True),
        summary=Agent(mini_model, output_type=str, system_prompt=_EXECUTIVE_SUMMARY_PROMPT,
                      model_settings=summary_settings, defer_model_check=True),
        signal_extractor=Agent(mini_model, output_type=KeySignals, system_prompt=SIGNAL_EXTRACTOR_PROMPT,
                               model_settings=checker_settings, defer_model_check=True),
    )
```

Add `key_signals` to `PipelineResult`:

```python
class PipelineResult(BaseModel):
    """Result from the multi-agent pipeline."""
    narrative: str
    executive_summary: list[str] = []
    specialists: SpecialistOutputs
    key_signals: KeySignals | None = None
    audit_flags: list[AuditFlag] = []
    anchor_warnings: list[AnchorWarning] = []
    revision_count: int = 0
```

- [ ] **Step 4: Run tests to verify the new test passes**

Run: `uv run pytest tests/test_pipeline.py::TestMakePipelineAgents -v`
Expected: All 4 tests PASS (including new `test_has_signal_extractor`)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: add signal_extractor to PipelineAgents and key_signals to PipelineResult"
```

---

### Task 5: Wire signal extractor into build_writer_input

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:712-732` (`build_writer_input`)
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signals.py`:

```python
from pitcher_narratives.pipeline import build_writer_input
from pitcher_narratives.signals import KeySignals


class TestBuildWriterInputWithSignals:
    def test_includes_key_signals_section(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
        )

        # Minimal PitcherContext mock — build_writer_input only reads
        # ctx.pitcher_name, ctx.throws, ctx.role from the context.
        from unittest.mock import SimpleNamespace
        ctx = SimpleNamespace(pitcher_name="Test Pitcher", throws="R", role="SP")

        result = build_writer_input(
            ctx, "stuff output", "location output", "runvalue output",
            "trends output", "game_shape output", key_signals=ks,
        )
        assert "## Key Signals" in result
        assert "- Top Improvement: Slider S+ jumped to 135" in result
        assert "- Top Concern: Fastball velo down 2.1 mph" in result
        # Key Signals should appear before specialist analyses
        signals_pos = result.index("## Key Signals")
        stuff_pos = result.index("## Specialist Analysis 1")
        assert signals_pos < stuff_pos

    def test_no_signals_omits_section(self):
        from unittest.mock import SimpleNamespace
        ctx = SimpleNamespace(pitcher_name="Test Pitcher", throws="R", role="SP")

        result = build_writer_input(
            ctx, "stuff output", "location output", "runvalue output",
            "trends output", "game_shape output",
        )
        assert "## Key Signals" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signals.py::TestBuildWriterInputWithSignals -v`
Expected: FAIL with `TypeError: build_writer_input() got an unexpected keyword argument 'key_signals'`

- [ ] **Step 3: Update build_writer_input to accept key_signals**

In `src/pitcher_narratives/pipeline.py`, replace `build_writer_input`:

```python
def build_writer_input(
    ctx: PitcherContext,
    stuff: str,
    location: str,
    runvalue: str,
    trends: str,
    game_shape: str,
    *,
    key_signals: KeySignals | None = None,
) -> str:
    """Compose all specialist outputs into writer input.

    Specialist outputs should already be clean (post-audit revision),
    so no audit flags are needed here. If key_signals is provided,
    a Key Signals section is prepended before the specialist analyses.
    """
    parts = [f"## Pitcher: {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    if key_signals is not None:
        parts.append(render_key_signals(key_signals) + "\n")
    parts.extend([
        f"## Specialist Analysis 1: Stuff\n{stuff}\n",
        f"## Specialist Analysis 2: Location\n{location}\n",
        f"## Specialist Analysis 3: Run Value\n{runvalue}\n",
        f"## Specialist Analysis 4: Trends\n{trends}\n",
        f"## Specialist Analysis 5: Game Shape\n{game_shape}",
    ])
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signals.py::TestBuildWriterInputWithSignals -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS (existing callers of `build_writer_input` pass no `key_signals`, which defaults to `None`)

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_signals.py
git commit -m "feat: wire key_signals into build_writer_input"
```

---

### Task 6: Wire signal extractor into _run_pipeline orchestration

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:1093-1201` (`_run_pipeline`)
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`:

```python
from pitcher_narratives.signals import KeySignals


class TestPipelineKeySignals:
    def test_pipeline_result_includes_key_signals(self, ctx):
        """Full pipeline produces key_signals in result."""
        test_model = TestModel()
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert result.key_signals is not None
        assert isinstance(result.key_signals, KeySignals)
        assert result.key_signals.top_improvement is not None
        assert result.key_signals.top_concern is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::TestPipelineKeySignals -v`
Expected: FAIL — `result.key_signals is None` (signal extractor not yet wired in)

- [ ] **Step 3: Wire signal extractor into _run_pipeline**

In `src/pitcher_narratives/pipeline.py`, update `_run_pipeline`. After the audit/revision block (line ~1126) and before the writer block (line ~1128), add the signal extraction step:

Replace:

```python
    # Phase 2: Writer + Executive Summary run concurrently
    # Writer gets clean specialist outputs (flagged claims already revised).
    writer_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
    )
```

with:

```python
    # Phase 1.75: Extract key signals from clean specialist outputs
    log.info("Extracting key signals...")
    signal_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
    )
    signal_result = await agents.signal_extractor.run(
        **agent_kwargs(signal_input, _model_override)
    )
    key_signals = signal_result.output
    log.info("Key signals extracted.")

    # Phase 2: Writer + Executive Summary run concurrently
    # Writer gets clean specialist outputs + key signals.
    writer_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
        key_signals=key_signals,
    )
```

Update the synthesis string for the anchor checker (line ~1165) to include key signals:

Replace:

```python
    synthesis = (
        f"STUFF:\n{specialists.stuff}\n\n"
        f"LOCATION:\n{specialists.location}\n\n"
        f"RUN VALUE:\n{specialists.runvalue}\n\n"
        f"TRENDS:\n{specialists.trends}\n\n"
        f"GAME SHAPE:\n{specialists.game_shape}"
    )
```

with:

```python
    synthesis = (
        f"{render_key_signals(key_signals)}\n\n"
        f"STUFF:\n{specialists.stuff}\n\n"
        f"LOCATION:\n{specialists.location}\n\n"
        f"RUN VALUE:\n{specialists.runvalue}\n\n"
        f"TRENDS:\n{specialists.trends}\n\n"
        f"GAME SHAPE:\n{specialists.game_shape}"
    )
```

Update the `PipelineResult` construction at the end of `_run_pipeline`:

Replace:

```python
    return PipelineResult(
        narrative=capsule,
        executive_summary=summary_bullets,
        specialists=specialists,
        audit_flags=audit_flags,
        anchor_warnings=anchor_check.warnings,
        revision_count=revision_count,
    )
```

with:

```python
    return PipelineResult(
        narrative=capsule,
        executive_summary=summary_bullets,
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=audit_flags,
        anchor_warnings=anchor_check.warnings,
        revision_count=revision_count,
    )
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py::TestPipelineKeySignals -v`
Expected: PASS

- [ ] **Step 5: Run the full pipeline test suite**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire signal extractor into pipeline orchestration"
```

---

### Task 7: Update writer prompt with Key Signals guidance

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:381-393` (`_WRITER_PROMPT`)
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signals.py`:

```python
from pitcher_narratives.pipeline import _WRITER_PROMPT


class TestWriterPromptKeySignals:
    def test_references_key_signals(self):
        assert "Key Signals" in _WRITER_PROMPT

    def test_distinguishes_primary_secondary(self):
        assert "Primary" in _WRITER_PROMPT or "primary" in _WRITER_PROMPT
        assert "Secondary" in _WRITER_PROMPT or "secondary" in _WRITER_PROMPT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signals.py::TestWriterPromptKeySignals -v`
Expected: FAIL — `"Key Signals" not in _WRITER_PROMPT`

- [ ] **Step 3: Update the writer prompt**

In `src/pitcher_narratives/pipeline.py`, in `_WRITER_PROMPT`, after the line:

```
- Prioritize the surprising. If three specialists agree on something \
obvious, give it one sentence. If one specialist found something \
the others didn't highlight, that's probably the lead.
```

add:

```
- Use the Key Signals. The Key Signals section contains cross-specialist \
patterns identified by a signal extractor. Primary signals (Top \
Improvement, Top Concern) are your narrative priorities — your lead \
must address one. Secondary signals (Specialist Tension, Connected \
Changes, etc.) are high-value if they serve the thread — use your \
judgment on weight. You are not required to mention every secondary \
signal.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signals.py::TestWriterPromptKeySignals -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_signals.py
git commit -m "feat: add key signals guidance to writer prompt"
```

---

### Task 8: Update write_pipeline_data_file for traceability

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:872-959` (`write_pipeline_data_file`)
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signals.py`:

```python
from pitcher_narratives.pipeline import write_pipeline_data_file
from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data


class TestDataFileSignalExtractor:
    def test_includes_signal_extractor_section(self, tmp_path):
        import os
        os.chdir(tmp_path)
        data = load_pitcher_data(592155, window_days=30)
        ctx = assemble_pitcher_context(data)
        path = write_pipeline_data_file(ctx, 592155, "gemini")
        content = open(path).read()
        assert "SIGNAL EXTRACTOR" in content
        assert "SIGNAL_EXTRACTOR_PROMPT" in content or "cross-specialist" in content.lower()

    def test_signal_extractor_appears_before_writer(self, tmp_path):
        import os
        os.chdir(tmp_path)
        data = load_pitcher_data(592155, window_days=30)
        ctx = assemble_pitcher_context(data)
        path = write_pipeline_data_file(ctx, 592155, "gemini")
        content = open(path).read()
        signal_pos = content.index("SIGNAL EXTRACTOR")
        writer_pos = content.index("WRITER")
        assert signal_pos < writer_pos
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signals.py::TestDataFileSignalExtractor -v`
Expected: FAIL — `"SIGNAL EXTRACTOR" not in content`

- [ ] **Step 3: Add signal extractor section to write_pipeline_data_file**

In `src/pitcher_narratives/pipeline.py`, in `write_pipeline_data_file`, after the data auditor section (line ~919) and before the `if question is not None:` branch (line ~921), add:

```python
    # Signal extractor
    sections.append(f"\n{sep}\nSIGNAL EXTRACTOR\n{sep}\n")
    sections.append(f"## System Prompt\n\n{SIGNAL_EXTRACTOR_PROMPT}\n")
    sections.append(
        "## User Message\n\n"
        "[Receives: all 5 specialist outputs (same as writer input)]\n"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signals.py::TestDataFileSignalExtractor -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_signals.py
git commit -m "feat: add signal extractor section to pipeline data file"
```

---

### Task 9: Update _run_pipeline docstring + module docstring

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:1-29` (module docstring)
- Modify: `src/pitcher_narratives/pipeline.py:1100-1105` (`_run_pipeline` docstring)

- [ ] **Step 1: Update module docstring**

In `src/pitcher_narratives/pipeline.py`, replace the architecture section in the module docstring (lines 3-22):

```python
"""Multi-agent specialist→auditor→writer report pipeline (v1.7 prototype).

Architecture:
  Phase 1: 5 specialist agents run in parallel, each producing a focused
  micro-analysis with league baselines (including stddev and S-variant
  benchmarks) injected for grounding:
    - Stuff Explainer: velocity/movement → S+ grades via S-variant predictions
    - Location Analyst: P vs S divergence, zone/chase rates, location impact
    - Run Value Decomposer: 13-outcome attribution, dominant value drivers
    - Trend Spotter: window vs season deltas in velocity, movement, usage, grades
    - Game Shape Analyst: TTO degradation, velocity arc, within-game mix shifts

  Phase 1.5: Per-specialist audit + revision loop. Each specialist's output
  is audited independently (5 audits run in parallel) against the raw data
  and league baselines. Flagged specialists are re-run with their original
  input + audit corrections to produce clean output. The writer never sees
  flawed prose — only corrected versions.

  Phase 1.75: Signal extractor reads clean specialist outputs and identifies
  cross-specialist patterns (top improvement, top concern, development pitch,
  specialist tensions, arsenal dependency, connected changes, platoon
  vulnerability, sample size caveats). These key signals feed both the
  writer (as narrative priorities) and the anchor checker (as validation
  targets).

  Phase 2: Writer composes a unified capsule from clean specialist outputs
  + key signals. Executive summary agent runs concurrently with writer.

  Phase 2.5: Anchor check + revision loop. Primary signals are enforced
  (MISSED_SIGNAL), secondary signals are advisory (UNDERWEIGHTED).
```

- [ ] **Step 2: Update _run_pipeline docstring**

Replace:

```python
    """Async core of the multi-agent pipeline.

    Phase 1: 5 specialists run concurrently.
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 2: Writer composes capsule (with audit flags if any).
    Phase 2.5: Anchor check + revision loop.
    """
```

with:

```python
    """Async core of the multi-agent pipeline.

    Phase 1: 5 specialists run concurrently.
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 1.75: Signal extractor identifies cross-specialist patterns.
    Phase 2: Writer composes capsule from specialist outputs + key signals.
    Phase 2.5: Anchor check + revision loop.
    """
```

- [ ] **Step 3: Run full test suite to verify nothing broke**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/pitcher_narratives/pipeline.py
git commit -m "docs: update pipeline docstrings for signal extractor phase"
```
