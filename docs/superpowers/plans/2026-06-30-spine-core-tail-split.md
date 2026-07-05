# Spine Core/Tail Split (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Factor `run_analysis_spine` into a frame-agnostic **core** (stuff/location/run-value/game-shape specialists + their audit + grounding) and a frame-sensitive **tail** (trends specialist + signal extraction), where the tail takes the assembled context so a later phase can re-run only the tail on a different temporal frame — all behavior-preserving.

**Architecture:** Two existing orchestration helpers (`run_specialists`, `audit_and_revise_specialists`) gain an opt-in `names` selector so they can operate on a subset of the five specialists while still returning a full `SpecialistOutputs`. A new `CoreContext` model carries the four core specialist outputs plus their audit flags. `run_spine_core` produces a `CoreContext`; `run_spine_tail` consumes it, runs the trends specialist + its audit + signal extraction, and assembles the final `AnalyzedContext`. `run_analysis_spine` becomes a thin `core → tail` composition on a single frame, producing a byte-identical `AnalyzedContext` (including canonical audit-flag ordering). No prompt bytes, no narrative, no public signature of `run_analysis_spine` changes — `morning.py` and the report path are untouched.

**Tech Stack:** Python 3.14, polars, pydantic / pydantic-ai (`TestModel`, `AsyncMock` agent injection), pytest, `uv` env + test running.

## Global Constraints

- Python `>=3.14`; run everything via `uv run`.
- `snake_case` modules/functions, `PascalCase` Pydantic models / type aliases, `UPPER_SNAKE_CASE` constants.
- Structured data as Pydantic models / dataclasses, not dicts (dict use confined to internal orchestration keyed by specialist name, as today).
- **Behavior-preserving:** no change to any generated narrative, prompt bytes, or existing test's expected output. New behavior is reachable only through new parameters (`names=`) and new functions (`run_spine_core`, `run_spine_tail`); every new parameter defaults to the current all-five behavior.
- Token-usage recording stays opt-in: the `tracker` parameter defaults to `None`; new helpers thread `tracker`/`tracker_model` through unchanged, recording only when `tracker is not None`.
- Frame-sensitivity is **structural only** in this phase: the tail still runs on the same `ctx` the core ran on (day-window `RECENT`). No appearance-count slicing, no new frames — that is Phase 5/6.

---

## Task 1: Add `names` selector to `audit_and_revise_specialists`

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`audit_and_revise_specialists`, ~916–1009)
- Test: `tests/test_pipeline.py` (near existing audit tests, ~1240)

**Interfaces:**
- Consumes: existing `SpecialistOutputs`, `_get_specialist_input_text`, `_build_specialist_audit_input`, `_build_specialist_revision_input`.
- Produces: `audit_and_revise_specialists(specialists, specialist_agents, auditor, ctx, _model_override=None, *, names: list[str] | None = None, tracker=None, tracker_model="") -> tuple[SpecialistOutputs, list[AuditFlag]]`. When `names` is given, only those specialists are audited/revised; the returned `SpecialistOutputs` still carries all five fields (unlisted specialists pass through unchanged). `names=None` preserves the current all-five behavior.

- [ ] **Step 1: Write the failing test**

```python
def test_audit_names_audits_only_selected(ctx):
    """With names=['trends'], only trends is audited; other specialists
    pass through unchanged and no flags are raised for them."""
    import asyncio
    from pitcher_narratives.models import SpecialistOutputs, AuditResult
    from pitcher_narratives.pipeline import audit_and_revise_specialists

    outputs = SpecialistOutputs(stuff="s", location="l", runvalue="r",
                                trends="t", game_shape="g")

    class _CountingAuditor:
        def __init__(self):
            self.calls = 0
        async def run(self, **kwargs):
            self.calls += 1
            class _R:
                output = AuditResult(flags=[])
            return _R()

    auditor = _CountingAuditor()
    clean, flags = asyncio.run(audit_and_revise_specialists(
        outputs, {}, auditor, ctx, names=["trends"],
    ))
    assert auditor.calls == 1          # only one specialist audited
    assert clean == outputs            # all five fields preserved, unchanged
    assert flags == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_audit_names_audits_only_selected -v`
Expected: FAIL — `TypeError: audit_and_revise_specialists() got an unexpected keyword argument 'names'`.

- [ ] **Step 3: Add the `names` selector**

In `audit_and_revise_specialists`, add the keyword-only parameter and split "which to audit" from "which to include in the returned output". Replace the signature and the body's name handling:

Change the signature (keep all existing params, add `names`):

```python
async def audit_and_revise_specialists(
    specialists: SpecialistOutputs,
    specialist_agents: dict[str, Agent[None, str]],
    auditor: Agent[None, AuditResult],
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    names: list[str] | None = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> tuple[SpecialistOutputs, list[AuditFlag]]:
```

Replace the name/outputs/ground-truth setup block (currently the `specialist_names = [...]`, `outputs = {...}`, `ground_truths = {...}` lines) with:

```python
    all_names = ["stuff", "location", "runvalue", "trends", "game_shape"]
    audit_names = names if names is not None else all_names

    # Full output map (all five) so the returned SpecialistOutputs is always
    # complete; only the audit_names subset is actually audited/revised.
    outputs: dict[str, str] = {
        name: getattr(specialists, name) for name in all_names
    }

    # Build ground truth input only for the specialists we audit.
    ground_truths = {
        name: _get_specialist_input_text(name, ctx) for name in audit_names
    }
```

Then change the two loops that iterate `specialist_names` to iterate `audit_names`:

```python
    audit_tasks = [_audit_one(name) for name in audit_names]
```

(The `_audit_one`, flag-collection, `_revise_one`, and revision-application blocks are unchanged — they already key off `outputs`/`ground_truths`/`flagged` by name. The final `return SpecialistOutputs(**clean_outputs), all_flags` is unchanged because `clean_outputs = dict(outputs)` still holds all five fields.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -k "audit" -v`
Expected: PASS — the new `test_audit_names_audits_only_selected` plus all existing audit tests (`test_audit_failure_degrades_to_unaudited`, the `TestAudit*` cases, and the Task 1.2 usage test), which pass no `names` and therefore audit all five as before.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "refactor(spine): add names selector to audit_and_revise_specialists"
```

---

## Task 2: Add `names` selector to `run_specialists`

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`run_specialists`, ~1322–1366)
- Test: `tests/test_pipeline.py` (near existing `test_run_specialists_fan_out_concurrently`, ~1225)

**Interfaces:**
- Consumes: existing `_build_stuff_input` / `_build_location_input` / `_build_runvalue_input` / `_build_trend_input` / `_build_game_shape_input`, `agent_kwargs`.
- Produces: `run_specialists(stuff_agent, location_agent, runvalue_agent, trends_agent, game_shape_agent, ctx, _model_override=None, *, names: list[str] | None = None, tracker=None, tracker_model="") -> SpecialistOutputs`. When `names` is given, only those specialists' agents are invoked; unlisted fields default to `""` in the returned `SpecialistOutputs`. `names=None` runs all five concurrently, exactly as today.

- [ ] **Step 1: Write the failing test**

```python
def test_run_specialists_names_runs_only_selected(ctx):
    """With names=['trends'], only the trends agent is invoked and the other
    SpecialistOutputs fields default to empty strings."""
    import asyncio

    class _MarkAgent:
        def __init__(self, mark):
            self.mark = mark
            self.calls = 0
        async def run(self, **kwargs):
            self.calls += 1
            class _R:
                pass
            r = _R()
            r.output = self.mark
            return r

    stuff = _MarkAgent("STUFF")
    location = _MarkAgent("LOC")
    runvalue = _MarkAgent("RV")
    trends = _MarkAgent("TRENDS")
    game_shape = _MarkAgent("GS")

    out = asyncio.run(run_specialists(
        stuff, location, runvalue, trends, game_shape, ctx,
        names=["trends"],
    ))
    assert trends.calls == 1
    assert stuff.calls == 0
    assert location.calls == 0
    assert runvalue.calls == 0
    assert game_shape.calls == 0
    assert out.trends == "TRENDS"
    assert out.stuff == ""
    assert out.location == ""
    assert out.runvalue == ""
    assert out.game_shape == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_run_specialists_names_runs_only_selected -v`
Expected: FAIL — `TypeError: run_specialists() got an unexpected keyword argument 'names'`.

- [ ] **Step 3: Rewrite `run_specialists` with a name-keyed fan-out**

Replace the whole `run_specialists` body so it selects by name, gathers by name, and fills unlisted fields with `""`:

```python
async def run_specialists(
    stuff_agent: Agent[None, str],
    location_agent: Agent[None, str],
    runvalue_agent: Agent[None, str],
    trends_agent: Agent[None, str],
    game_shape_agent: Agent[None, str],
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    names: list[str] | None = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> SpecialistOutputs:
    """Run the specialists concurrently.

    By default all five run. Pass ``names`` to run only a subset (used by the
    core/tail spine split); unlisted specialists default to an empty string in
    the returned SpecialistOutputs.
    """
    all_inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (trends_agent, _build_trend_input(ctx)),
        "game_shape": (game_shape_agent, _build_game_shape_input(ctx)),
    }
    selected = list(all_inputs) if names is None else names

    async def _run(name: str, agent: Agent[None, str], prompt: str | UserPrompt) -> tuple[str, str]:
        result = await agent.run(**agent_kwargs(prompt, _model_override))
        if tracker is not None:
            u = result.usage()
            tracker.record(tracker_model, u.input_tokens or 0, u.output_tokens or 0,
                           stage=f"specialist:{name}")
        return name, result.output

    results = await asyncio.gather(
        *(_run(name, *all_inputs[name]) for name in selected)
    )

    outputs = {name: "" for name in all_inputs}
    for name, text in results:
        outputs[name] = text
    return SpecialistOutputs(**outputs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -k "run_specialists" -v`
Expected: PASS — the new subset test plus `test_run_specialists_fan_out_concurrently` (default all-five still fans out concurrently, peak > 1).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "refactor(spine): add names selector to run_specialists"
```

---

## Task 3: Add `CoreContext` model

**Files:**
- Modify: `src/pitcher_narratives/models.py` (add `CoreContext` after `AnalyzedContext`, ~71)
- Test: `tests/test_models.py` (create if absent; otherwise append)

**Interfaces:**
- Consumes: existing `AuditFlag`.
- Produces: `class CoreContext(BaseModel)` with fields `stuff: str`, `location: str`, `runvalue: str`, `game_shape: str`, `audit_flags: list[AuditFlag] = []`. This is the frame-agnostic output of `run_spine_core` (no trends, no key signals — those are frame-sensitive tail artifacts).

- [ ] **Step 1: Write the failing test**

```python
def test_core_context_holds_four_specialists_and_flags():
    from pitcher_narratives.models import CoreContext, AuditFlag

    core = CoreContext(
        stuff="s", location="l", runvalue="r", game_shape="g",
        audit_flags=[AuditFlag(category="X", specialist="stuff",
                               claim="c", data_shows="d", suggested_fix="f")],
    )
    assert core.stuff == "s"
    assert core.game_shape == "g"
    assert len(core.audit_flags) == 1
    # Defaults to empty flag list.
    assert CoreContext(stuff="s", location="l", runvalue="r",
                       game_shape="g").audit_flags == []
    # Frame-sensitive fields are intentionally absent.
    assert not hasattr(CoreContext(stuff="s", location="l", runvalue="r",
                                   game_shape="g"), "trends")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::test_core_context_holds_four_specialists_and_flags -v`
Expected: FAIL — `ImportError: cannot import name 'CoreContext'`.

- [ ] **Step 3: Add the model**

In `src/pitcher_narratives/models.py`, immediately after `AnalyzedContext`:

```python
class CoreContext(BaseModel):
    """Frame-agnostic core of the analysis spine.

    Holds the clean stuff/location/run-value/game-shape specialist outputs and
    their audit flags. Trends analysis, key-signal extraction, and the anchor
    check are frame-sensitive and produced by the tail (see run_spine_tail);
    they are deliberately absent here so the core can be computed once and
    shared across narration modes that differ only in temporal frame.
    """

    stuff: str
    location: str
    runvalue: str
    game_shape: str
    audit_flags: list[AuditFlag] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py::test_core_context_holds_four_specialists_and_flags -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/models.py tests/test_models.py
git commit -m "feat(spine): add CoreContext model for frame-agnostic core"
```

---

## Task 4: Implement `run_spine_core`

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add module constants + `run_spine_core` just above `run_analysis_spine`, ~1368; add `"CoreContext"`, `"run_spine_core"` to `__all__` at ~111–118; add `from pitcher_narratives.models import ... CoreContext` to the existing models import)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `run_specialists` (Task 2, `names=`), `audit_and_revise_specialists` (Task 1, `names=`), `CoreContext` (Task 3), existing `PipelineAgents`.
- Produces: module constants `_CORE_SPECIALISTS = ["stuff", "location", "runvalue", "game_shape"]` and `_TAIL_SPECIALISTS = ["trends"]`; `async def run_spine_core(ctx: PitcherContext, *, agents: PipelineAgents, _model_override=None, tracker: UsageTracker | None = None) -> CoreContext`. Runs the four core specialists + audits them, returns a `CoreContext`.

- [ ] **Step 1: Write the failing test**

```python
def test_run_spine_core_returns_four_clean_specialists(ctx):
    """run_spine_core runs only the four core specialists under TestModel and
    returns a CoreContext with all four populated."""
    import asyncio
    from pitcher_narratives.models import CoreContext
    from pitcher_narratives.pipeline import run_spine_core, make_pipeline_agents

    agents = make_pipeline_agents("gemini", "high")
    model = TestModel(call_tools=[], custom_output_text="Core analysis.")
    core = asyncio.run(run_spine_core(ctx, agents=agents, _model_override=model))

    assert isinstance(core, CoreContext)
    assert core.stuff != ""
    assert core.location != ""
    assert core.runvalue != ""
    assert core.game_shape != ""
    assert isinstance(core.audit_flags, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_run_spine_core_returns_four_clean_specialists -v`
Expected: FAIL — `ImportError: cannot import name 'run_spine_core'`.

- [ ] **Step 3: Implement `run_spine_core`**

First extend the imports and `__all__` in `pipeline.py`. Add `CoreContext` to the existing `from pitcher_narratives.models import (... AnalyzedContext, ...)` group, and add the two new public names to `__all__`:

```python
    "AnalyzedContext", "CoreContext",
    ...
    "make_pipeline_agents", "run_analysis_spine", "run_spine_core", "run_spine_tail",
    "run_specialists",
```

Then, immediately above `run_analysis_spine`, add the constants and function:

```python
_CORE_SPECIALISTS = ["stuff", "location", "runvalue", "game_shape"]
_TAIL_SPECIALISTS = ["trends"]


async def run_spine_core(
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> CoreContext:
    """Run the frame-agnostic core of the analysis spine.

    Runs the stuff/location/run-value/game-shape specialists and audits them.
    Frame-agnostic: these specialists read a single window snapshot, so the
    core can be computed once and shared across narration modes. Trends,
    signal extraction, and the anchor check are frame-sensitive — see
    run_spine_tail.
    """
    mini = agents.mini_model_name
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, agents.game_shape, ctx, _model_override,
        names=_CORE_SPECIALISTS, tracker=tracker, tracker_model=mini,
    )
    clean, flags = await audit_and_revise_specialists(
        raw, agents.specialist_dict(), agents.auditor, ctx, _model_override,
        names=_CORE_SPECIALISTS, tracker=tracker, tracker_model=mini,
    )
    return CoreContext(
        stuff=clean.stuff, location=clean.location,
        runvalue=clean.runvalue, game_shape=clean.game_shape,
        audit_flags=flags,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py::test_run_spine_core_returns_four_clean_specialists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(spine): add run_spine_core (frame-agnostic core)"
```

---

## Task 5: Implement `run_spine_tail`

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add `_SPECIALIST_ORDER`, `_order_flags`, and `run_spine_tail` just below `run_spine_core`; `run_spine_tail` already added to `__all__` in Task 4)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `CoreContext` (Task 3), `run_specialists` / `audit_and_revise_specialists` (`names=`), existing `build_writer_input`, `SpecialistOutputs`, `AnalyzedContext`, `agents.signal_extractor`.
- Produces: `_SPECIALIST_ORDER: dict[str, int]`, `_order_flags(flags: list[AuditFlag]) -> list[AuditFlag]` (stable sort into canonical stuff→location→run-value→trends→game-shape order), and `async def run_spine_tail(core: CoreContext, ctx: PitcherContext, *, agents: PipelineAgents, _model_override=None, tracker: UsageTracker | None = None) -> AnalyzedContext`. Runs the trends specialist + its audit + signal extraction over the core's four specialists plus trends, returning the full `AnalyzedContext` (audit flags = core flags + trends flags, ordered canonically).

- [ ] **Step 1: Write the failing test**

```python
def test_run_spine_tail_assembles_full_analyzed_context(ctx):
    """run_spine_tail runs trends + signal extraction over a CoreContext and
    returns a complete AnalyzedContext preserving the core specialist text."""
    import asyncio
    from pitcher_narratives.models import CoreContext, AnalyzedContext
    from pitcher_narratives.pipeline import run_spine_tail, make_pipeline_agents

    agents = make_pipeline_agents("gemini", "high")
    model = TestModel(call_tools=[], custom_output_text="Tail analysis.")
    core = CoreContext(stuff="CORE_STUFF", location="CORE_LOC",
                       runvalue="CORE_RV", game_shape="CORE_GS")

    analyzed = asyncio.run(
        run_spine_tail(core, ctx, agents=agents, _model_override=model)
    )
    assert isinstance(analyzed, AnalyzedContext)
    # Core specialist text is carried through verbatim.
    assert analyzed.specialists.stuff == "CORE_STUFF"
    assert analyzed.specialists.game_shape == "CORE_GS"
    # Trends was produced by the tail.
    assert analyzed.specialists.trends != ""


def test_order_flags_puts_specialists_in_canonical_order():
    from pitcher_narratives.models import AuditFlag
    from pitcher_narratives.pipeline import _order_flags

    def flag(spec):
        return AuditFlag(category="X", specialist=spec, claim="c",
                         data_shows="d", suggested_fix="f")

    # Core-first + trends-last input (as run_spine_tail concatenates) must be
    # reordered to the legacy stuff/location/runvalue/trends/game_shape order.
    ordered = _order_flags([flag("game_shape"), flag("trends"), flag("stuff")])
    assert [f.specialist for f in ordered] == ["stuff", "trends", "game_shape"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_run_spine_tail_assembles_full_analyzed_context tests/test_pipeline.py::test_order_flags_puts_specialists_in_canonical_order -v`
Expected: FAIL — `ImportError: cannot import name 'run_spine_tail'` (and `_order_flags`).

- [ ] **Step 3: Implement `_order_flags` and `run_spine_tail`**

Add directly below `run_spine_core`:

```python
_SPECIALIST_ORDER = {
    "stuff": 0, "location": 1, "runvalue": 2, "trends": 3, "game_shape": 4,
}


def _order_flags(flags: list[AuditFlag]) -> list[AuditFlag]:
    """Sort audit flags into the canonical specialist order.

    The core/tail split collects core flags (stuff/location/run-value/
    game-shape) then trends flags, so a naive concatenation would place trends
    last. Sorting restores the legacy stuff→location→run-value→trends→
    game-shape order, keeping run_analysis_spine output identical. Stable, so
    multiple flags from the same specialist keep their relative order.
    """
    return sorted(flags, key=lambda f: _SPECIALIST_ORDER.get(f.specialist, 99))


async def run_spine_tail(
    core: CoreContext,
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> AnalyzedContext:
    """Run the frame-sensitive tail of the analysis spine.

    Runs the trends specialist (+ its audit) and signal extraction over the
    core's four specialists plus trends. Takes ``ctx`` explicitly so a later
    phase can re-run the tail on a different temporal frame while reusing a
    single shared core. In this phase the tail runs on the same ctx as the
    core, so output is identical to the pre-split spine.
    """
    mini = agents.mini_model_name
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, agents.game_shape, ctx, _model_override,
        names=_TAIL_SPECIALISTS, tracker=tracker, tracker_model=mini,
    )
    merged = SpecialistOutputs(
        stuff=core.stuff, location=core.location, runvalue=core.runvalue,
        game_shape=core.game_shape, trends=raw.trends,
    )
    specialists, trends_flags = await audit_and_revise_specialists(
        merged, agents.specialist_dict(), agents.auditor, ctx, _model_override,
        names=_TAIL_SPECIALISTS, tracker=tracker, tracker_model=mini,
    )

    signal_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
    )
    signals_failed = False
    try:
        signal_result = await agents.signal_extractor.run(
            **agent_kwargs(signal_input, _model_override)
        )
        if tracker is not None:
            u = signal_result.usage()
            tracker.record(mini, u.input_tokens or 0, u.output_tokens or 0, stage="signals")
        key_signals = signal_result.output
    except Exception:
        log.warning("Signal extractor failed, continuing without key signals.", exc_info=True)
        key_signals = None
        signals_failed = True

    return AnalyzedContext(
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=_order_flags(list(core.audit_flags) + trends_flags),
        signals_failed=signals_failed,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py::test_run_spine_tail_assembles_full_analyzed_context tests/test_pipeline.py::test_order_flags_puts_specialists_in_canonical_order -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(spine): add run_spine_tail (frame-sensitive tail)"
```

---

## Task 6: Recompose `run_analysis_spine` as core → tail

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`run_analysis_spine`, ~1369–1422)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `run_spine_core` (Task 4), `run_spine_tail` (Task 5).
- Produces: unchanged public signature `async def run_analysis_spine(ctx, *, agents, _model_override=None, tracker=None) -> AnalyzedContext`, now implemented as `core = run_spine_core(...)` then `run_spine_tail(core, ctx, ...)`. Behavior-preserving.

- [ ] **Step 1: Write the failing test**

```python
def test_run_analysis_spine_composes_core_then_tail(ctx, monkeypatch):
    """run_analysis_spine must delegate to run_spine_core then run_spine_tail,
    passing the produced CoreContext and the same ctx into the tail."""
    import asyncio
    import pitcher_narratives.pipeline as _pl
    from pitcher_narratives.models import CoreContext, AnalyzedContext, SpecialistOutputs
    from unittest.mock import AsyncMock

    sentinel_core = CoreContext(stuff="s", location="l", runvalue="r", game_shape="g")
    sentinel_analyzed = AnalyzedContext(
        specialists=SpecialistOutputs(stuff="s", location="l", runvalue="r",
                                      trends="t", game_shape="g"),
    )
    core_mock = AsyncMock(return_value=sentinel_core)
    tail_mock = AsyncMock(return_value=sentinel_analyzed)
    monkeypatch.setattr(_pl, "run_spine_core", core_mock)
    monkeypatch.setattr(_pl, "run_spine_tail", tail_mock)

    class _Agents:
        mini_model_name = ""

    result = asyncio.run(_pl.run_analysis_spine(ctx, agents=_Agents()))
    assert result is sentinel_analyzed
    core_mock.assert_awaited_once()
    tail_mock.assert_awaited_once()
    # The CoreContext from core is threaded into the tail as its first arg,
    # and the same ctx is passed through.
    tail_args, tail_kwargs = tail_mock.call_args
    assert tail_args[0] is sentinel_core
    assert tail_args[1] is ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_run_analysis_spine_composes_core_then_tail -v`
Expected: FAIL — the current `run_analysis_spine` calls `run_specialists`/`audit_and_revise_specialists` directly, so `run_spine_core`/`run_spine_tail` are never awaited (`AssertionError: Expected 'run_spine_core' to have been awaited once. Awaited 0 times`).

- [ ] **Step 3: Recompose `run_analysis_spine`**

Replace the body of `run_analysis_spine` (keep the signature and docstring intro) with the two-line composition:

```python
async def run_analysis_spine(
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> AnalyzedContext:
    """Run the specialist → audit → signal-extraction spine.

    Shared analysis path for report and morning. Composes the frame-agnostic
    core (run_spine_core) with the frame-sensitive tail (run_spine_tail) on a
    single frame; the returned AnalyzedContext is identical to the pre-split
    spine. Does not run the writer, anchor check, or hallucination check —
    those are terminal-layer concerns.

    Args:
        ctx: Assembled pitcher context (facts, baselines, arsenal data).
        agents: Pre-built pipeline agents (create once, reuse across picks).
        _model_override: Optional model override for deterministic testing.
        tracker: Optional usage tracker for accumulating per-call token costs.
    """
    core = await run_spine_core(
        ctx, agents=agents, _model_override=_model_override, tracker=tracker,
    )
    return await run_spine_tail(
        core, ctx, agents=agents, _model_override=_model_override, tracker=tracker,
    )
```

- [ ] **Step 4: Run the full spine + morning suites to verify behavior-preservation**

Run: `uv run pytest tests/test_pipeline.py tests/test_morning.py -v`
Expected: PASS — including the pre-existing `test_run_analysis_spine_returns_analyzed_context` (unchanged assertions) and `test_signals_failed_flag_set_on_extractor_failure` (module-level `run_specialists`/`audit_and_revise_specialists` are still monkeypatched and now invoked twice — once by core, once by the tail — with the extractor still raising, so `signals_failed` remains `True`).

- [ ] **Step 5: Run the whole suite (real-data equivalence + no regressions)**

Run: `uv run pytest -q`
Expected: PASS — the real-data `592155` pipeline/context tests exercise the composed spine end-to-end and must be green, confirming the split is behavior-preserving.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "refactor(spine): recompose run_analysis_spine as core then tail"
```

---

## Self-Review

**Spec coverage (§13 phase 3 + §3/G1 load-bearing decision):**
- "Factor `run_analysis_spine` into a shared core (stuff/location/run-value/game-shape + grounding)" → Tasks 3–4 (`CoreContext`, `run_spine_core`, which runs those four specialists + their audit).
- "and a tail (trends specialist + signal extraction + anchor) that takes a frame argument" → Task 5 (`run_spine_tail` runs trends + audit + signal extraction and takes `ctx` explicitly as the frame it operates on). The anchor check lives in the terminal layer (`_run_anchor_revision_loop`), not inside `run_analysis_spine` today, so it is out of scope for this spine-internal split; the tail's explicit-`ctx` seam is what a later phase (CHANGES, phase 9) uses to re-run trends/signals/anchor on the RECENT-vs-PRIOR frame.
- "REPORT still runs on the native frame — behavior-preserving" → Task 6 composes core→tail on one `ctx`; `_order_flags` preserves legacy audit-flag order; full-suite + real-data run gates it.
- "This makes CHANGES possible later without re-touching core" → `run_spine_core` returns a reusable `CoreContext`; `run_spine_tail(core, ctx, ...)` accepts any `ctx`, so a future caller runs the core once and the tail per frame.
- Preserve 4-pitch cache budget / prompt bytes → no specialist input builder, `build_writer_input`, or prompt constant is touched; only orchestration changes.

**Known latency trade (output-preserving, not latency-preserving):** the composed spine serializes the tail's trends specialist *after* the core's specialists + audit, whereas the pre-split spine ran all five specialists (and all five audits) concurrently. On the single-frame REPORT/morning path this adds serial latency with no offsetting benefit yet; it pays off once a multi-frame mode (CHANGES) reuses one core across frames. Accepted deliberately and documented in `run_analysis_spine`'s docstring.

**Placeholder scan:** No "TBD/handle edge cases/similar-to" — every code step shows complete code. ✓

**Type consistency:** `names: list[str] | None = None` identical in Tasks 1 and 2; `_CORE_SPECIALISTS`/`_TAIL_SPECIALISTS` defined in Task 4 and consumed in Tasks 4–5; `CoreContext` fields (`stuff/location/runvalue/game_shape/audit_flags`) match across Tasks 3–5; `run_spine_core`/`run_spine_tail` names match `__all__` additions (Task 4) and Task 6 composition; `_order_flags`/`_SPECIALIST_ORDER` defined and used in Task 5, tested in Task 5. `AuditFlag.specialist` field confirmed present (`models.py:31`). ✓

**Caveat to verify during execution:** Task 2's Step-1 test stub `_MarkAgent` sets `r.output` on the returned object — confirm the pipeline reads `result.output` (it does, `run_specialists` uses `result.output`). Task 1's `_RecordingAuditor` is illustrative; the asserting stub is `_CountingAuditor` — drop the unused `_RecordingAuditor` if the implementer prefers, it does not affect the assertion.
