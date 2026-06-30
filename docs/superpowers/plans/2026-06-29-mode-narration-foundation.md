# Mode-Narration Foundation (Phases 1–2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the two lowest-risk, behavior-preserving foundations of the mode-based narration refactor — validation observability and the multi-frame context wrapper — so later phases (spine split, modes) have instrumentation and a context shape to build on.

**Architecture:** Phase 1 instruments the two terminal validation loops (`_run_anchor_revision_loop`, `_run_capsule_audit`) to record token usage on the shared `UsageTracker`, and adds a pure `flag_summary` that morning persists — closing the observability gap that left the capsule flag/revision rate unmeasured. Phase 2 introduces a `TemporalFrame` enum and a `MultiFrameContext` wrapper holding one `PitcherContext` per frame; for now only the existing day-window frame is populated, so output is unchanged. Neither phase alters any narration.

**Tech Stack:** Python 3.14, polars, pydantic / pydantic-ai (`TestModel`, agent injection), pytest, `uv` for env + test running.

## Global Constraints

- Python `>=3.14`; run everything via `uv run`.
- `snake_case` modules/functions, `PascalCase` for Pydantic models / type aliases, `UPPER_SNAKE_CASE` constants.
- Structured data is Pydantic models / dataclasses, not dicts.
- Both phases are **behavior-preserving**: no change to any generated narrative, prompt bytes, or existing test's expected output. New behavior is reachable only through new parameters/functions.
- Token-usage recording is **opt-in**: every new `tracker` parameter defaults to `None`, and recording is guarded by `if tracker is not None` so existing call sites and their mock agents (which lack a real `.usage()`) stay green.
- Test pitcher id for real-data fixtures: `592155` (used by `tests/test_pipeline.py`, `tests/test_context.py`).
- `UsageTracker.record` signature is fixed: `record(model: str, input_tokens: int, output_tokens: int, *, stage: str = "")` (`costs.py:55`).

---

## Phase 1 — Validation observability

### Task 1.1: Instrument the anchor-revision loop with usage tracking

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`_run_anchor_revision_loop`, ~1399–1466)
- Test: `tests/test_pipeline.py` (add to `class TestAnchorRevisionLoop`, ~484)

**Interfaces:**
- Consumes: `UsageTracker.record(model, input_tokens, output_tokens, *, stage)` from `costs.py`.
- Produces: `_run_anchor_revision_loop(*, anchor_agent, writer_agent, synthesis, capsule, max_revisions, _model_override=None, tracker: UsageTracker | None = None, tracker_model: str = "") -> tuple[str, AnchorResult, int]`. When `tracker` is set, records `stage="anchor"` per anchor check and `stage="anchor_revision"` per writer revision.

- [ ] **Step 1: Write the failing test**

```python
def test_records_usage_per_anchor_and_revision(self):
    """With a tracker, each anchor check and writer revision is recorded."""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from pitcher_narratives.anchor import AnchorResult, AnchorWarning
    from pitcher_narratives.costs import UsageTracker
    from pitcher_narratives.pipeline import _run_anchor_revision_loop

    def _wrap(output, tin, tout):
        return MagicMock(
            output=output,
            usage=MagicMock(return_value=SimpleNamespace(
                input_tokens=tin, output_tokens=tout)),
        )

    dirty = AnchorResult(warnings=[AnchorWarning(
        category="MISSED_SIGNAL", description="x")])
    clean = AnchorResult(warnings=[])
    anchor = MagicMock()
    anchor.run = AsyncMock(side_effect=[_wrap(dirty, 10, 5), _wrap(clean, 10, 5)])
    writer = MagicMock()
    writer.run = AsyncMock(side_effect=[_wrap("REVISED", 20, 8)])

    tracker = UsageTracker()
    asyncio.run(_run_anchor_revision_loop(
        anchor_agent=anchor, writer_agent=writer,
        synthesis="synth", capsule="ORIG", max_revisions=2,
        tracker=tracker, tracker_model="m",
    ))

    stages = [r.stage for r in tracker.records]
    assert stages == ["anchor", "anchor_revision", "anchor"]
    assert tracker.total_input() == 40   # 10 + 20 + 10
    assert tracker.total_output() == 18  # 5 + 8 + 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::TestAnchorRevisionLoop::test_records_usage_per_anchor_and_revision -v`
Expected: FAIL — `TypeError: _run_anchor_revision_loop() got an unexpected keyword argument 'tracker'`.

- [ ] **Step 3: Add the tracker params and recording**

In `_run_anchor_revision_loop`, add the two parameters to the signature:

```python
async def _run_anchor_revision_loop(
    *,
    anchor_agent: Agent[None, AnchorResult],
    writer_agent: Agent[None, str],
    synthesis: str,
    capsule: str,
    max_revisions: int,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> tuple[str, AnchorResult, int]:
```

Add a local helper at the top of the function body and call it after each agent run:

```python
    def _rec(result: Any, stage: str) -> None:
        if tracker is None:
            return
        u = result.usage()
        tracker.record(tracker_model, u.input_tokens or 0,
                       u.output_tokens or 0, stage=stage)
```

Then record at each call site inside the function:
- after `anchor_result = await anchor_agent.run(...)` → `_rec(anchor_result, "anchor")`
- after `revision_result = await writer_agent.run(...)` → `_rec(revision_result, "anchor_revision")`
- after `final_result = await anchor_agent.run(...)` (post-loop) → `_rec(final_result, "anchor")`

`UsageTracker` is already imported in `pipeline.py` (via `from pitcher_narratives.costs import UsageTracker, model_label`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py::TestAnchorRevisionLoop -v`
Expected: PASS (the new test plus all existing loop tests — the existing ones pass no `tracker`, so `_rec` is a no-op for them).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(observability): record anchor-loop token usage"
```

### Task 1.2: Instrument the capsule fact-check loop with usage tracking

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`_run_capsule_audit`, ~1526–1597)
- Test: `tests/test_pipeline.py` (near the existing `_run_capsule_audit` tests, ~1320)

**Interfaces:**
- Produces: `_run_capsule_audit(*, auditor, writer_agent, ground_truth, capsule, max_fact_revisions=MAX_FACT_REVISIONS, _model_override=None, tracker: UsageTracker | None = None, tracker_model: str = "") -> tuple[str, list[AuditFlag], bool]`. Records `stage="fact_audit"` per auditor run and `stage="fact_revision"` per writer revision.

- [ ] **Step 1: Write the failing test**

```python
def test_capsule_audit_records_usage():
    """Initial audit + one revision + re-audit are each recorded."""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from pitcher_narratives.costs import UsageTracker
    from pitcher_narratives.models import AuditFlag, AuditResult
    from pitcher_narratives.pipeline import _run_capsule_audit

    def _wrap(output, tin, tout):
        return MagicMock(
            output=output,
            usage=MagicMock(return_value=SimpleNamespace(
                input_tokens=tin, output_tokens=tout)),
        )

    flag = AuditFlag(category="FABRICATED_DATA", claim="c",
                     data_shows="d", suggested_fix="f")
    dirty = AuditResult(is_clean=False, flags=[flag])
    clean = AuditResult(is_clean=True, flags=[])
    auditor = MagicMock()
    auditor.run = AsyncMock(side_effect=[_wrap(dirty, 10, 4), _wrap(clean, 10, 4)])
    writer = MagicMock()
    writer.run = AsyncMock(side_effect=[_wrap("FIXED CAPSULE", 20, 6)])

    tracker = UsageTracker()
    asyncio.run(_run_capsule_audit(
        auditor=auditor, writer_agent=writer,
        ground_truth="gt", capsule="CAP", max_fact_revisions=2,
        tracker=tracker, tracker_model="m",
    ))

    stages = [r.stage for r in tracker.records]
    assert stages == ["fact_audit", "fact_revision", "fact_audit"]
```

(Confirm the `AuditFlag` field names against `src/pitcher_narratives/models.py` before running; adjust the constructor kwargs to match if they differ.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_capsule_audit_records_usage -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'tracker'`.

- [ ] **Step 3: Add the tracker params and recording**

Add `tracker: UsageTracker | None = None, tracker_model: str = ""` to the signature. Add the same `_rec` helper as Task 1.1. Record:
- after the initial `result = await auditor.run(...)` → `_rec(result, "fact_audit")`
- after `revision = await writer_agent.run(...)` → `_rec(revision, "fact_revision")`
- after `recheck = await auditor.run(...)` → `_rec(recheck, "fact_audit")`

Leave the early-return / empty-revision guard branches unchanged (no recording on the skipped paths).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -k capsule_audit -v`
Expected: PASS (new test + existing `_run_capsule_audit` tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(observability): record capsule fact-check token usage"
```

### Task 1.3: Add `flag_summary` and persist it from the morning run

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add `flag_summary`, export in `__all__`)
- Modify: `src/pitcher_narratives/morning.py` (write `validation.json`)
- Test: `tests/test_pipeline.py` (unit test for `flag_summary`); `tests/test_morning.py` (artifact assertion)

**Interfaces:**
- Produces: `flag_summary(result: PipelineResult) -> dict[str, int | bool]` returning keys `revision_count`, `capsule_revised`, `n_capsule_audit_flags`, `n_anchor_warnings`, `n_value_parity_warnings`, `n_audit_flags`.

- [ ] **Step 1: Write the failing unit test**

```python
def test_flag_summary_counts_fields():
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.pipeline import PipelineResult, flag_summary

    result = PipelineResult(
        narrative="n",
        specialists=SpecialistOutputs(
            stuff="s", location="l", runvalue="r", trends="t", game_shape="g"),
        revision_count=2,
        capsule_revised=True,
        anchor_warnings=[],
        value_parity_warnings=["[capsule] 1.23"],
    )
    summary = flag_summary(result)
    assert summary == {
        "revision_count": 2,
        "capsule_revised": True,
        "n_capsule_audit_flags": 0,
        "n_anchor_warnings": 0,
        "n_value_parity_warnings": 1,
        "n_audit_flags": 0,
    }
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_flag_summary_counts_fields -v`
Expected: FAIL — `ImportError: cannot import name 'flag_summary'`.

- [ ] **Step 3: Implement `flag_summary`**

Add to `pipeline.py` (and add `"flag_summary"` to `__all__`):

```python
def flag_summary(result: PipelineResult) -> dict[str, int | bool]:
    """Countable validation outcomes for a finished pipeline result.

    Persisted per run so the capsule flag/revision rate — never recorded
    before — becomes measurable and the per-mode revision depth can be
    calibrated from real data rather than guessed.
    """
    return {
        "revision_count": result.revision_count,
        "capsule_revised": result.capsule_revised,
        "n_capsule_audit_flags": len(result.capsule_audit_flags),
        "n_anchor_warnings": len(result.anchor_warnings),
        "n_value_parity_warnings": len(result.value_parity_warnings),
        "n_audit_flags": len(result.audit_flags),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_pipeline.py::test_flag_summary_counts_fields -v`
Expected: PASS.

- [ ] **Step 5: Persist it from morning**

Morning digest items are produced by `write_pick_summaries` and do not currently run the capsule loops, so there are no per-item flag counts yet (those arrive in a later phase). For now, write an empty-but-present `validation.json` so the artifact contract exists and downstream tooling can rely on it. In `morning.py`, after the other artifacts are written (near `usage.json`), add:

```python
    (run_dir / "validation.json").write_text(json.dumps(
        {"picks": {}, "note": "per-item validation lands with Mode RECAP parity"},
        indent=2,
    ))
```

- [ ] **Step 6: Test the artifact is written**

In `tests/test_morning.py`, locate the existing override-driven `run_morning` test (it asserts on files under the returned `run_dir`) and add, in the same test or a sibling that reuses its setup:

```python
    assert (run_dir / "validation.json").exists()
    import json
    data = json.loads((run_dir / "validation.json").read_text())
    assert "picks" in data
```

Run: `uv run pytest tests/test_morning.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/pipeline.py src/pitcher_narratives/morning.py tests/test_pipeline.py tests/test_morning.py
git commit -m "feat(observability): flag_summary + morning validation.json artifact"
```

---

## Phase 2 — Multi-frame context wrapper

### Task 2.1: Add the `TemporalFrame` enum (leaf module)

**Files:**
- Create: `src/pitcher_narratives/temporal.py`
- Test: `tests/test_temporal.py`

**Interfaces:**
- Produces: `class TemporalFrame(StrEnum)` with members `MOST_RECENT="most_recent"`, `RECENT="recent"`, `PRIOR="prior"`, `SEASON="season"`, `WINDOW_DAYS="window_days"`.

- [ ] **Step 1: Write the failing test**

```python
def test_temporal_frame_members():
    from pitcher_narratives.temporal import TemporalFrame

    assert TemporalFrame.WINDOW_DAYS == "window_days"
    assert TemporalFrame.MOST_RECENT == "most_recent"
    assert {f.value for f in TemporalFrame} == {
        "most_recent", "recent", "prior", "season", "window_days"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_temporal.py::test_temporal_frame_members -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pitcher_narratives.temporal'`.

- [ ] **Step 3: Create the module**

```python
"""Temporal frame identifiers for multi-window context assembly.

Leaf module (no project imports) so it can be referenced by both the
context layer and the pipeline without import cycles. WINDOW_DAYS is the
existing day-based lookback and is transitional — it is removed when the
slicer swaps to appearance-count (see the mode-narration design, §5).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["TemporalFrame"]


class TemporalFrame(StrEnum):
    MOST_RECENT = "most_recent"   # the single latest appearance (RECAP)
    RECENT = "recent"             # recent N appearances (REPORT span / CHANGES recent-X)
    PRIOR = "prior"               # prior M appearances (CHANGES)
    SEASON = "season"             # full season baseline
    WINDOW_DAYS = "window_days"   # TRANSITIONAL day-based lookback; removed at the slicer swap
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_temporal.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/temporal.py tests/test_temporal.py
git commit -m "feat(context): add TemporalFrame enum"
```

### Task 2.2: Add the `MultiFrameContext` wrapper

**Files:**
- Modify: `src/pitcher_narratives/context.py` (add `MultiFrameContext`, extend `__all__`)
- Test: `tests/test_context.py`

**Interfaces:**
- Consumes: `TemporalFrame` (Task 2.1), `PitcherContext` (existing).
- Produces: `class MultiFrameContext(BaseModel)` with `frames: dict[TemporalFrame, PitcherContext]`, a `for_frame(frame: TemporalFrame) -> PitcherContext` method (raises `KeyError`-style `ValueError` with the available frames listed if absent), and a `primary` property returning the `WINDOW_DAYS` frame.

- [ ] **Step 1: Write the failing test**

```python
def test_multi_frame_context_primary_and_for_frame(ctx):
    from pitcher_narratives.context import MultiFrameContext
    from pitcher_narratives.temporal import TemporalFrame

    mfc = MultiFrameContext(frames={TemporalFrame.WINDOW_DAYS: ctx})
    assert mfc.primary is ctx
    assert mfc.for_frame(TemporalFrame.WINDOW_DAYS) is ctx

    import pytest
    with pytest.raises(ValueError, match="season"):
        mfc.for_frame(TemporalFrame.SEASON)
```

(The `ctx` fixture already exists in `tests/test_context.py`, scope="module", built from `load_pitcher_data(592155)`.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_context.py::test_multi_frame_context_primary_and_for_frame -v`
Expected: FAIL — `ImportError: cannot import name 'MultiFrameContext'`.

- [ ] **Step 3: Implement the wrapper**

Add to `context.py` (and add `"MultiFrameContext"` to `__all__`; add `from pitcher_narratives.temporal import TemporalFrame` to the imports):

```python
class MultiFrameContext(BaseModel):
    """One PitcherContext per temporal frame.

    Wrapper shape (not per-field) so every PitcherContext field keeps its
    type and all render_/_build_*_input helpers stay unchanged. Today only
    WINDOW_DAYS is populated; later phases add appearance-count frames.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    frames: dict[TemporalFrame, PitcherContext]

    def for_frame(self, frame: TemporalFrame) -> PitcherContext:
        try:
            return self.frames[frame]
        except KeyError:
            available = ", ".join(sorted(f.value for f in self.frames))
            raise ValueError(
                f"frame {frame.value!r} not assembled; available: {available}"
            ) from None

    @property
    def primary(self) -> PitcherContext:
        """The default frame current call sites read (the day-window)."""
        return self.for_frame(TemporalFrame.WINDOW_DAYS)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/context.py tests/test_context.py
git commit -m "feat(context): add MultiFrameContext wrapper"
```

### Task 2.3: Add `assemble_multi_frame_context` (behavior-preserving)

**Files:**
- Modify: `src/pitcher_narratives/context.py` (add `assemble_multi_frame_context`, extend `__all__`)
- Test: `tests/test_context.py`

**Interfaces:**
- Consumes: `assemble_pitcher_context(data)` (existing), `MultiFrameContext` (Task 2.2).
- Produces: `assemble_multi_frame_context(data: PitcherData) -> MultiFrameContext` whose `WINDOW_DAYS` frame equals today's `assemble_pitcher_context(data)`. No other frame is populated yet.

- [ ] **Step 1: Write the failing test**

```python
def test_assemble_multi_frame_primary_matches_single(ctx):
    from pitcher_narratives.context import assemble_multi_frame_context
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.temporal import TemporalFrame

    data = load_pitcher_data(592155, window_days=30)
    mfc = assemble_multi_frame_context(data)

    assert set(mfc.frames) == {TemporalFrame.WINDOW_DAYS}
    # Behavior-preserving: the wrapped frame matches the existing assembly.
    assert mfc.primary.pitcher_id == ctx.pitcher_id
    assert mfc.primary.to_prompt() == ctx.to_prompt()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_context.py::test_assemble_multi_frame_primary_matches_single -v`
Expected: FAIL — `ImportError: cannot import name 'assemble_multi_frame_context'`.

- [ ] **Step 3: Implement the assembler**

Add to `context.py` (and `__all__`):

```python
def assemble_multi_frame_context(data: PitcherData) -> MultiFrameContext:
    """Assemble the multi-frame context.

    Behavior-preserving cut: only the day-window frame is built (it equals
    today's assemble_pitcher_context output). Appearance-count frames
    (RECENT / PRIOR / MOST_RECENT) are added when the slicer lands.
    """
    return MultiFrameContext(
        frames={TemporalFrame.WINDOW_DAYS: assemble_pitcher_context(data)},
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_context.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `uv run pytest -q`
Expected: PASS — no existing test changes behavior; only new tests and new symbols were added.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/context.py tests/test_context.py
git commit -m "feat(context): assemble_multi_frame_context (day-window only)"
```

---

## Self-Review

**Spec coverage (this plan's slice):**
- §8 Observability — Tasks 1.1, 1.2 (loop usage recording), 1.3 (`flag_summary` + `validation.json`). ✓ The "persist `PipelineResult` flag counts" requirement is seeded; full per-item morning counts depend on the RECAP-parity phase (out of this plan's scope, noted in Task 1.3 Step 5).
- §5 Multi-frame context (wrapper decision) — Tasks 2.1–2.3 (enum, wrapper, behavior-preserving assembler). ✓ The appearance-count slicer + cold-start re-expression are Phase 6 (out of scope).
- Out of scope by design (separate plans): Phase 3 spine split, Phase 4 NarrationMode/REPORT, Phase 5 sufficiency/determinism guards, Phase 6 window swap, Phases 7–11.

**Placeholder scan:** No "TBD/handle edge cases/similar-to" — every code step shows real code. ✓

**Type consistency:** `tracker`/`tracker_model` parameter names and the `_rec` helper are identical across Tasks 1.1 and 1.2; `TemporalFrame` members and `MultiFrameContext.primary`/`for_frame` names match between Tasks 2.1, 2.2, 2.3. `flag_summary` keys match between the function and its test. ✓

**Caveat to verify during execution:** Task 1.2's `AuditFlag` constructor kwargs and Task 1.3's `PipelineResult`/`SpecialistOutputs` required fields must be checked against `src/pitcher_narratives/models.py` before running each failing test; adjust the constructor calls to the actual field names if they differ (the test intent is unchanged).
