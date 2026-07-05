# Morning → Mode RECAP Integration (Phase 8B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the morning digest onto Mode RECAP: each pick's item is rendered from the shared `AnalyzedContext` through the RECAP writer + full validation stack (with a typed editorial overlay from the `CurationPick`), residual-flagged items are marked, and the old prose-cue path (`build_story_cue*`, `DIGEST_ITEM`, `_CUE_FRAMING`, `write_pick_summaries`) is retired.

**Architecture:** Extract the shared **writer + validation core** of `_run_pipeline` into `_render_capsule` (writer → explainer → anchor loop → parity union → capsule audit), leaving the report-only summaries in `_run_pipeline`. `report` stays byte-identical (streams, no overlay, explainer on). Add a public `render_recap(ctx, analyzed, *, agents, pick=None)` that reuses `_render_capsule` non-streaming, with a `CurationPick`-derived editorial overlay, RECAP validation depths (anchor 1 / fact 2), and the explainer check off (a 2-4 sentence brief does not teach the grading system — resolves the 8A seam note). Morning builds RECAP agents once, folds `render_recap` into its existing per-pick coroutine (which already runs the spine once under a semaphore), marks any residual-flagged item with the Phase-7 `residual_banner`/`is_unverified`, and reports the count in the run summary. The retired cue path and its tests are deleted; the `test_fact_parity` cross-path gate is re-expressed against the shared grounding both paths now use.

**Tech Stack:** Python 3.14, polars, pydantic-ai, pytest. No new dependencies.

## Global Constraints

- Python 3.14+; run everything via `uv run` against the project `.venv`.
- **Data/CLI/morning tests need `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives`.** Subprocess CLI/morning tests set `PITCHER_NARRATIVES_TEST_MODEL=1` via `_test_env(...)`. The full suite takes ~4 min (subprocess tests) — use a generous timeout / background run.
- One pre-existing unrelated suite failure is expected: `test_to_prompt_token_budget`. Any other failure is real.
- `snake_case`/`PascalCase`/`UPPER_SNAKE_CASE`; Google-style docstrings; type hints on signatures.
- **`report` (default REPORT) output and exit MUST stay byte-identical.** The Task-1 extraction is behavior-preserving; the guard is the existing subprocess golden tests (`test_cli_narrative_output_has_required_sections`, `test_cli_unverified_banner_on_residual_flags`, `test_cli_anchor_check_in_output`) plus `test_pipeline_threads_report_validation_depths`. If any of these change, the extraction is wrong — stop.
- **Reuse, don't duplicate.** Phase 7 published `run_anchor_revision_loop`, `run_capsule_audit`, `is_unverified`, `residual_banner`; 8A added the `RECAP` mode. Compose these — do not re-implement validation or banner logic.
- Morning already runs a single event loop with agents built once (G3/G11 satisfied). Do NOT introduce a second `asyncio.run` or per-pick agent builds.
- SDD ledger: append to `.superpowers/sdd/progress.md` under "## Phase 8B". Commit the plan first (`docs(plan): ...`), then one commit per task.
- Work only in this worktree; never `cd` to the data dir. Set `PITCHER_NARRATIVES_DATA_DIR` inline per command.

---

## File Structure

- `src/pitcher_narratives/pipeline.py` — **primary change site.** Task 1: extract `_render_capsule` + `_RenderedCapsule`; rewire `_run_pipeline` to call it. Task 2: add public `render_recap` + `build_recap_overlay`; extend `__all__`.
- `src/pitcher_narratives/morning.py` — Task 3: build RECAP agents, render each pick via `render_recap`, mark residuals, drop the cue/`write_pick_summaries` path.
- `src/pitcher_narratives/digest.py` — Task 4: delete `build_story_cue`, `build_story_cue_from_context`, `enrich_cue_with_signals`, `write_pick_summaries`; trim `__all__`. Keep `assemble_digest`, `render_full_board`, `is_fallback_summary`, `FALLBACK_MARKER`.
- `src/pitcher_narratives/personas.py` — Task 4: delete `DIGEST_ITEM`, `_CUE_FRAMING`, `_DIGEST_STRUCTURE`; trim `__all__`.
- `tests/` — Task 1/2 pipeline tests; Task 3 morning tests; Task 4 deletes cue tests (`test_digest.py`), rewrites the `test_fact_parity.py` cross-path gate.

**Explicitly NOT touched:** `curator.py` (`CurationPick` unchanged), the REPORT/BRIEF contracts, `assemble_digest`'s formatting. **Deferred (Phase 9 / later):** the `--mode report,recap` spine-once optimization (that combo still double-runs the spine — acceptable; morning and single-mode recap each run the spine once); G9 per-mode stdout headers; `--recap-anchor-depth`/`--recap-fact-depth` CLI knobs; `--mode changes`.

---

## Task 1: Extract `_render_capsule` from `_run_pipeline` (report byte-identical)

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — add `_RenderedCapsule` dataclass + `_render_capsule`; rewrite `_run_pipeline` body (currently lines 1782-1937) to call it.
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `build_writer_input`, `agent_kwargs`, `check_explainer_present`, `_explainer_dropped`, `run_anchor_revision_loop`, `_build_parity_union`, `run_capsule_audit`, `render_key_signals` (all existing in pipeline.py), `AnchorResult`/`AuditFlag`/`AnalyzedContext`/`PipelineAgents`/`PitcherContext` types.
- Produces (private, consumed by Task 2 and `_run_pipeline`):
  ```python
  @dataclass
  class _RenderedCapsule:
      capsule: str
      writer_input: str
      fact_check_source: str
      anchor_check: AnchorResult
      revision_count: int
      capsule_audit_flags: list[AuditFlag]
      capsule_revised: bool

  async def _render_capsule(
      ctx: PitcherContext,
      analyzed: AnalyzedContext,
      *,
      agents: PipelineAgents,
      anchor_depth: int,
      fact_depth: int,
      stream: bool,
      check_explainer: bool = True,
      overlay: str | None = None,
      persona_label: str = "",
      _model_override: Any = None,
      tracker: UsageTracker | None = None,
  ) -> _RenderedCapsule: ...
  ```

- [ ] **Step 1: Write the characterization test (guard the extraction)**

The report-path byte-identity is already guarded by existing subprocess tests. Add ONE focused test that both modes render through the shared core, so the extraction's shape is pinned. Add to `tests/test_pipeline.py`:

```python
def test_render_capsule_non_streaming_returns_capsule(monkeypatch, capsys):
    """_render_capsule(stream=False) captures the writer output without
    printing to stdout, and runs the anchor + capsule-audit loops."""
    import asyncio

    from pitcher_narratives import pipeline
    from pitcher_narratives.personas import REPORT, get_persona

    # Reuse the existing pipeline test scaffolding (TestModel + real ctx).
    ctx = _load_test_context()          # mirror an existing test's setup
    agents = pipeline.make_pipeline_agents(
        "gemini", "medium", get_persona("scout"), REPORT,
        _model_override=_test_model(),   # mirror existing usage
    )

    async def _go():
        analyzed = await pipeline.run_analysis_spine(
            ctx, agents=agents, _model_override=_test_model()
        )
        return await pipeline._render_capsule(
            ctx, analyzed, agents=agents, anchor_depth=1, fact_depth=1,
            stream=False, check_explainer=False, _model_override=_test_model(),
        )

    rc = asyncio.run(_go())
    assert isinstance(rc.capsule, str) and rc.capsule  # non-empty
    assert rc.writer_input and rc.fact_check_source
    # stream=False must NOT print the capsule to stdout.
    assert rc.capsule not in capsys.readouterr().out
```

**Note for implementer:** `_load_test_context()`/`_test_model()`/`make_pipeline_agents` model-override are placeholders — copy the exact TestModel + context + `make_pipeline_agents(...)` setup an existing `test_pipeline.py` test uses (grep `make_pipeline_agents(` and `run_analysis_spine(` in that file). If `make_pipeline_agents` has no `_model_override` param, obtain the TestModel the way existing tests do (they set it via env `PITCHER_NARRATIVES_TEST_MODEL` or a fixture). The assertion that matters: non-empty capsule, and nothing printed when `stream=False`.

- [ ] **Step 2: Run it to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_pipeline.py -k render_capsule -v`
Expected: FAIL — `AttributeError: module 'pitcher_narratives.pipeline' has no attribute '_render_capsule'`.

- [ ] **Step 3: Add `_RenderedCapsule` + `_render_capsule`**

In `src/pitcher_narratives/pipeline.py`, add the dataclass (near the other module dataclasses) and the function. The body is lifted verbatim from `_run_pipeline` lines 1813-1897 (build_writer_input → capsule audit), with three parameterizations: `stream`, `check_explainer`, `overlay`. Use the current `_run_pipeline` code as the source of truth for the exact strings (the `specialist_synthesis`/`synthesis` construction, the log messages, the explainer guards):

```python
async def _render_capsule(
    ctx, analyzed, *, agents, anchor_depth, fact_depth, stream,
    check_explainer=True, overlay=None, persona_label="",
    _model_override=None, tracker=None,
) -> _RenderedCapsule:
    """Writer + anchor + capsule-audit core, shared by the report pipeline and
    the recap render. Report streams (stream=True); recap does not. ``overlay``
    prepends editorial direction to the writer input; ``check_explainer`` gates
    the Pitching+ explainer warnings (off for the short recap brief)."""
    specialists = analyzed.specialists
    key_signals = analyzed.key_signals

    writer_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
        key_signals=key_signals,
    )
    if overlay:
        writer_input = f"{overlay}\n\n{writer_input}"
    writer_kwargs = agent_kwargs(writer_input, _model_override)

    if stream:
        async with agents.writer.run_stream(**writer_kwargs) as _s:
            chunks: list[str] = []
            async for delta in _s.stream_text(delta=True):
                print(delta, end="", flush=True)
                chunks.append(delta)
        print()
        capsule = "".join(chunks)
    else:
        _res = await agents.writer.run(**writer_kwargs)
        capsule = _res.output   # mirror how _run_summaries reads its result

    pre_ok = bool(capsule.strip()) and (
        not check_explainer or check_explainer_present(capsule)
    )
    if check_explainer and not pre_ok:
        log.warning("[%s] capsule is missing model explanation content", persona_label)

    specialist_synthesis = (
        f"STUFF:\n{specialists.stuff}\n\n"
        f"LOCATION:\n{specialists.location}\n\n"
        f"RUN VALUE:\n{specialists.runvalue}\n\n"
        f"TRENDS:\n{specialists.trends}\n\n"
        f"GAME SHAPE:\n{specialists.game_shape}"
    )
    synthesis = (
        f"{render_key_signals(key_signals)}\n\n{specialist_synthesis}"
        if key_signals is not None else specialist_synthesis
    )

    capsule, anchor_check, revision_count = await run_anchor_revision_loop(
        anchor_agent=agents.anchor, writer_agent=agents.writer,
        synthesis=synthesis, capsule=capsule, max_revisions=anchor_depth,
        _model_override=_model_override, tracker=tracker,
    )
    if check_explainer and revision_count > 0 and pre_ok and _explainer_dropped(capsule):
        log.warning("[%s] anchor revision removed model explanation content from capsule", persona_label)

    fact_check_source = _build_parity_union(ctx, specialists, key_signals)
    capsule, capsule_audit_flags, capsule_revised = await run_capsule_audit(
        auditor=agents.capsule_auditor, writer_agent=agents.writer,
        ground_truth=fact_check_source, capsule=capsule,
        max_fact_revisions=fact_depth, _model_override=_model_override, tracker=tracker,
    )
    if check_explainer and capsule_revised and pre_ok and _explainer_dropped(capsule):
        log.warning("[%s] capsule fact-revision removed model explanation content from capsule", persona_label)

    return _RenderedCapsule(
        capsule=capsule, writer_input=writer_input, fact_check_source=fact_check_source,
        anchor_check=anchor_check, revision_count=revision_count,
        capsule_audit_flags=capsule_audit_flags, capsule_revised=capsule_revised,
    )
```

**Verify `_res.output`:** confirm the writer's non-streaming result attribute by checking how `_run_summaries`/the brief agent reads `agent.run(...)` output (grep `.run(` in pipeline.py and use the same attribute — `.output` in current pydantic-ai). If it differs, use whatever `_run_summaries` uses.

- [ ] **Step 4: Rewrite `_run_pipeline` to call `_render_capsule`**

Replace `_run_pipeline` lines 1810-1899 (the writer stream through `check_value_parity(capsule, ...)`) with:

```python
    rc = await _render_capsule(
        ctx, analyzed, agents=agents,
        anchor_depth=mode.validation.anchor_depth,
        fact_depth=mode.validation.fact_depth,
        stream=True, check_explainer=True, overlay=None,
        persona_label=persona, _model_override=_model_override,
    )
    capsule = rc.capsule
    fact_check_source = rc.fact_check_source
    value_parity = check_value_parity(capsule, fact_check_source)
```

Then keep the existing summaries block (lines 1904-1937) but source from `rc`:
- `_run_summaries(..., capsule=capsule, writer_input=rc.writer_input, ...)`,
- `anchor_warnings=rc.anchor_check.warnings`, `revision_count=rc.revision_count`,
- `capsule_audit_flags=rc.capsule_audit_flags`, `capsule_revised=rc.capsule_revised`.

Note: `_run_pipeline` passes `tracker` implicitly as `None` (the original never passed a tracker to the loops) — leave `tracker` unset in this call so behavior is byte-identical. `audit_flags`/`specialists`/`key_signals` still come from `analyzed`.

- [ ] **Step 5: Run the new test + the byte-identity guards**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_pipeline.py -k "render_capsule or threads_report_validation_depths" tests/test_cli.py -q
```
Expected: PASS, including `test_cli_narrative_output_has_required_sections`, `test_cli_unverified_banner_on_residual_flags`, `test_cli_anchor_check_in_output`, `test_pipeline_threads_report_validation_depths` — proving `report` is unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "refactor(pipeline): extract _render_capsule; report byte-identical (P8B)"
```

---

## Task 2: `render_recap` + editorial overlay (the typed recap path)

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — add `build_recap_overlay`, `render_recap`; import `RECAP`; extend `__all__`.
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `_render_capsule` (Task 1), `RECAP` (personas, 8A), `check_value_parity`, `PipelineResult`, `is_unverified`.
- Produces:
  ```python
  def build_recap_overlay(*, angle: str, category: str) -> str
  async def render_recap(
      ctx: PitcherContext, analyzed: AnalyzedContext, *,
      agents: PipelineAgents, pick: "CurationPick | None" = None,
      _model_override: Any = None, tracker: UsageTracker | None = None,
  ) -> PipelineResult
  ```

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
def test_build_recap_overlay_leads_with_angle():
    from pitcher_narratives.pipeline import build_recap_overlay

    overlay = build_recap_overlay(angle="Sweeper usage doubled", category="command_breakout")
    assert "Sweeper usage doubled" in overlay
    assert "command_breakout" in overlay


def test_render_recap_produces_validated_pipeline_result():
    """render_recap renders a recap from a pre-computed AnalyzedContext and runs
    the validation stack (recap depths), returning a PipelineResult."""
    import asyncio

    from pitcher_narratives import pipeline
    from pitcher_narratives.personas import RECAP, get_persona

    ctx = _load_test_context()
    agents = pipeline.make_pipeline_agents(
        "gemini", "medium", get_persona("scout"), RECAP, _model_override=_test_model()
    )

    async def _go():
        analyzed = await pipeline.run_analysis_spine(ctx, agents=agents, _model_override=_test_model())
        return await pipeline.render_recap(ctx, analyzed, agents=agents, pick=None, _model_override=_test_model())

    result = asyncio.run(_go())
    from pitcher_narratives.pipeline import PipelineResult
    assert isinstance(result, PipelineResult)
    assert result.narrative                              # recap text present
    assert result.executive_summary == []                # recap has no exec summary
    assert result.brief == ""                             # recap has no # Brief
    # is_unverified applies to a recap result just like a report result.
    from pitcher_narratives.pipeline import is_unverified
    assert isinstance(is_unverified(result), bool)
```

Reuse the same `_load_test_context()`/`_test_model()` scaffolding as Task 1.

- [ ] **Step 2: Run to verify failure**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_pipeline.py -k "recap_overlay or render_recap" -v`
Expected: FAIL — `ImportError`/`AttributeError` for `build_recap_overlay`/`render_recap`.

- [ ] **Step 3: Implement**

In `src/pitcher_narratives/pipeline.py`. To avoid a runtime import cycle with `curator`, import `CurationPick` under `TYPE_CHECKING` only (the module already uses `from __future__ import annotations`):

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pitcher_narratives.curator import CurationPick
```

Add the RECAP import to the existing personas import line (`from pitcher_narratives.personas import ... RECAP`).

```python
def build_recap_overlay(*, angle: str, category: str) -> str:
    """Editorial direction prepended to the recap writer input (morning path).

    The recap leads with the editor's angle, grounded in the analyses.
    """
    return (
        "EDITORIAL DIRECTION — lead the recap with this angle, grounded in the "
        "analyses below (never contradict them):\n"
        f"  Angle: {angle}\n"
        f"  Category: {category}"
    )


async def render_recap(
    ctx, analyzed, *, agents, pick=None, _model_override=None, tracker=None,
) -> PipelineResult:
    """Render a Mode RECAP executive brief from a pre-computed AnalyzedContext.

    Reuses the shared writer+validation core (recap depths, explainer off,
    non-streaming). When ``pick`` is provided (morning), its angle/category
    lead the brief; standalone (pick=None) the brief leads with the analyses'
    own thread. Returns a PipelineResult so is_unverified/residual_banner apply.
    """
    overlay = (
        build_recap_overlay(angle=pick.angle, category=pick.category)
        if pick is not None else None
    )
    rc = await _render_capsule(
        ctx, analyzed, agents=agents,
        anchor_depth=RECAP.validation.anchor_depth,
        fact_depth=RECAP.validation.fact_depth,
        stream=False, check_explainer=False, overlay=overlay,
        persona_label="recap", _model_override=_model_override, tracker=tracker,
    )
    value_parity = check_value_parity(rc.capsule, rc.fact_check_source)
    return PipelineResult(
        narrative=rc.capsule,
        specialists=analyzed.specialists,
        key_signals=analyzed.key_signals,
        audit_flags=analyzed.audit_flags,
        anchor_warnings=rc.anchor_check.warnings,
        revision_count=rc.revision_count,
        capsule_audit_flags=rc.capsule_audit_flags,
        capsule_revised=rc.capsule_revised,
        value_parity_warnings=[f"[recap] {w}" for w in value_parity.unmatched],
    )
```

Add `"build_recap_overlay"` and `"render_recap"` to `__all__`.

- [ ] **Step 4: Run the tests**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_pipeline.py -k "recap_overlay or render_recap" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): render_recap + editorial overlay from AnalyzedContext (P8B)"
```

---

## Task 3: Wire morning onto `render_recap` + residual marking

**Files:**
- Modify: `src/pitcher_narratives/morning.py` — build RECAP agents; render each pick via `render_recap` inside `_build_pick`; mark residual-flagged items; drop the cue + `write_pick_summaries` path; report the unverified count.
- Test: `tests/test_morning.py`

**Interfaces:**
- Consumes: `render_recap`, `is_unverified`, `residual_banner` (pipeline), `RECAP` (personas), `make_pipeline_agents`, `run_analysis_spine`.
- Produces: `run_morning` unchanged signature; digest items now RECAP-rendered + validated + residual-marked.

- [ ] **Step 1: Write/adjust the failing test**

`tests/test_morning.py` drives `run_morning` under TestModel. Add a test that a residual-flagged recap item is marked. Since TestModel's capsule auditor emits synthetic flags (as it does for the report path — see `test_cli_unverified_banner_on_residual_flags`), a morning run under TestModel should mark items. Add:

```python
def test_morning_marks_unverified_recap_items(tmp_path):
    """Under TestModel the capsule audit leaves residual flags, so morning must
    mark the digest item as UNVERIFIED (never ship a flagged item unmarked)."""
    # Mirror the existing test_morning.py run_morning invocation (TestModel via
    # overrides / env). Grep this file for the existing run_morning(...) call.
    digest_path = run_morning(
        window_days=1, top_n=2, min_pitches=1, provider="gemini",
        persona_id="scout", out_root=tmp_path,
        _selector_override=_test_selector(), _writer_override=_test_model(),
    )
    assert digest_path is not None
    text = digest_path.read_text()
    assert "UNVERIFIED" in text
```

**Note for implementer:** copy the exact `run_morning(...)` override arguments an existing `test_morning.py` test uses (`_selector_override`, `_writer_override`, and how they build the TestModel/selector). If TestModel does NOT reliably produce residual flags in the morning path, weaken to asserting the run completes and produces a digest with the picks rendered (non-empty items) — but first check whether the report path's `test_cli_unverified_banner_on_residual_flags` mechanism carries over (it should, since morning now uses the same capsule audit). Do not fabricate a passing assertion.

- [ ] **Step 2: Run to verify failure**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py -k unverified -v`
Expected: FAIL (marking not yet implemented / morning still uses the cue path).

- [ ] **Step 3: Rewire `_llm_stages`**

In `src/pitcher_narratives/morning.py`, inside `_llm_stages` (lines ~96-150):

1. Build RECAP agents once — change `spine_agents = make_pipeline_agents(provider, "medium", persona)` to:
   ```python
   from pitcher_narratives.personas import RECAP
   agents = make_pipeline_agents(provider, "medium", persona, RECAP)
   ```
   (Keep the single build — G11. The specialists are mode-independent; the writer is now the RECAP writer.)

2. Fold the recap render into `_build_pick` — it already holds `ctx` and `analyzed` under the semaphore. Replace the `cue = build_story_cue_from_context(...)` line and the return with:
   ```python
   from pitcher_narratives.pipeline import render_recap
   recap_result = await render_recap(
       ctx, analyzed, agents=agents, pick=p,
       _model_override=_writer_override, tracker=tracker,
   )
   return p.pitcher_id, recap_result
   ```
   Update `_build_pick`'s return type annotation to `tuple[int, PipelineResult] | None` (import `PipelineResult` from pipeline).

3. Replace the post-gather assembly (the `cues`/`analyzed_contexts` dicts + `write_pick_summaries` call) with direct residual-marked summaries:
   ```python
   from pitcher_narratives.pipeline import is_unverified, residual_banner
   summaries: dict[int, str] = {}
   n_unverified = 0
   for result in build_results:
       if result is None:
           continue
       pid, recap_result = result
       text = recap_result.narrative
       banner = residual_banner(recap_result, label="RECAP")
       if banner is None and recap_result.value_parity_warnings:
           banner = ("⚠️  RECAP UNVERIFIED — value-parity flags present; "
                     "review before use.")
       if banner:
           text = f"{banner}\n\n{text}"
           n_unverified += 1
       summaries[pid] = text
   dropped_names = [
       appearances[p.pitcher_id].pitcher_name
       for p in picks if p.pitcher_id not in summaries
   ]
   picks = [p for p in picks if p.pitcher_id in summaries]
   if n_unverified:
       log.warning("%d recap item(s) shipped UNVERIFIED (residual flags).", n_unverified)
   return slate, picks, summaries, dropped_names
   ```
   Remove the now-unused `cues`/`analyzed_contexts` locals and the `write_pick_summaries` call and its import.

4. Surface the count in the run summary — after `asyncio.run(_llm_stages())`, the existing `cost_block` gets a `failed` note; add an unverified note similarly. Thread `n_unverified` out of `_llm_stages` (return it, or recompute from marked summaries by counting `"UNVERIFIED"` prefixes). Simplest: have `_llm_stages` also return `n_unverified` and append to `cost_block`:
   ```python
   if n_unverified:
       cost_block += f"\nnote: {n_unverified} recap item(s) shipped UNVERIFIED (residual fact-check flags)"
   ```

Keep `assemble_digest(...)` unchanged (it consumes the `summaries` dict as before).

- [ ] **Step 4: Run morning tests**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py -q`
Expected: PASS (including the new marking test). Some existing morning tests may assert on the old cue/summary wording — update them to the RECAP reality (recompute expected, don't weaken). If a test asserted `write_pick_summaries` was called, it moves to asserting `render_recap` behavior.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/morning.py tests/test_morning.py
git commit -m "feat(morning): render digest items via Mode RECAP + residual marking (P8B)"
```

---

## Task 4: Retire the cue / DIGEST path + rewrite the fact-parity gate

**Files:**
- Modify: `src/pitcher_narratives/digest.py` — delete `build_story_cue`, `build_story_cue_from_context`, `enrich_cue_with_signals`, `write_pick_summaries`; trim `__all__` and now-unused imports.
- Modify: `src/pitcher_narratives/personas.py` — delete `DIGEST_ITEM`, `_CUE_FRAMING`, `_DIGEST_STRUCTURE`; trim `__all__`.
- Modify: `tests/test_digest.py` — delete the cue tests; `tests/test_fact_parity.py` — rewrite the cross-path gate.

**Interfaces:** removals only; no new public surface.

- [ ] **Step 1: Confirm the retirees are dead in `src/`**

After Task 3, morning no longer imports the cue path. Confirm nothing in `src/` still references the retirees:
```bash
rg -n 'build_story_cue|enrich_cue_with_signals|write_pick_summaries|DIGEST_ITEM|_CUE_FRAMING|_DIGEST_STRUCTURE' src/
```
Expected: only their own definitions (`digest.py`, `personas.py`). If morning still references any, Task 3 is incomplete — fix there first.

- [ ] **Step 2: Delete the code**

- `digest.py`: remove the functions `build_story_cue`, `build_story_cue_from_context`, `enrich_cue_with_signals`, `write_pick_summaries` and their entries in `__all__` (lines 27-36). Remove any import now unused (e.g. `CurationPick`, `Persona`, `render_key_signals`, baseline params) — run `rg` to confirm before deleting each import. KEEP `assemble_digest`, `render_full_board`, `is_fallback_summary`, `FALLBACK_MARKER`.
- `personas.py`: remove `DIGEST_ITEM`, `_CUE_FRAMING`, `_DIGEST_STRUCTURE` and the `DIGEST_ITEM` entry in `__all__`. Confirm nothing else references them (`rg 'DIGEST_ITEM|_CUE_FRAMING|_DIGEST_STRUCTURE' src/ tests/`).

- [ ] **Step 3: Delete the dead cue tests**

In `tests/test_digest.py`, remove the tests that call the deleted functions: `test_story_cue_contains_all_layers`, `test_story_cue_handles_missing_baselines` (the dead `build_story_cue`), and the `build_story_cue_from_context` tests (`test_story_cue_from_context_*`). Remove the now-invalid imports. Keep tests for `assemble_digest`/`render_full_board`/`is_fallback_summary`.

- [ ] **Step 4: Rewrite the cross-path fact-parity gate**

`tests/test_fact_parity.py::test_cross_path_morning_cue_and_report_context_cite_same_numbers` (line ~461) asserts a cue string cites the same fastball velo / usage as the report `PitcherContext`. The cue is gone, but the underlying guarantee is now structural: **both the report pipeline and `render_recap` derive their writer grounding from the same `build_writer_input(ctx, ...)` and validate against the same `_build_parity_union(ctx, ...)`** — so cross-path drift is impossible by construction. Re-express the test to assert that shared grounding cites the same numbers. Rename it (e.g. `test_cross_path_recap_and_report_share_grounding`) and rewrite:

```python
def test_cross_path_recap_and_report_share_grounding():
    """The recap (morning) and report paths both ground the writer in the same
    build_writer_input(ctx, ...) for the same pitcher — so they cite identical
    fastball velocity and per-pitch usage. This replaces the retired cue-string
    parity gate."""
    from pitcher_narratives.pipeline import build_writer_input

    ctx = _load_context(_IDENTITY_PITCHER)   # reuse this file's existing loader
    # Build the writer grounding with empty specialist text — the ctx-derived
    # facts (fastball velo, arsenal usage) are what both paths share.
    grounding = build_writer_input(
        ctx, "", "", "", "", "", key_signals=None,
    )
    if ctx.fastball is not None:
        assert f"{ctx.fastball.season_velo:.1f} mph" in grounding
    for pt in ctx.arsenal[:3]:
        assert f"{pt.season_usage_pct:.1f}%" in grounding
```

**Note for implementer:** confirm `build_writer_input` actually embeds `ctx.fastball.season_velo` and `pt.season_usage_pct` in its output (read `build_writer_input` at pipeline.py:826). If those numbers live in a different shared function (e.g. they only appear in `_build_parity_union`), assert against that shared function instead — the point is to assert on the grounding BOTH paths use, not to reproduce the old cue projection. Reuse the existing `_IDENTITY_PITCHER`/context-loading helper already in `test_fact_parity.py`. Do NOT weaken the numeric assertions — recompute against the real shared grounding.

- [ ] **Step 5: Run the affected suites**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_digest.py tests/test_fact_parity.py tests/test_personas.py tests/test_morning.py -q
```
Expected: PASS. Grep-confirm the retirees are gone everywhere:
```bash
rg -n 'build_story_cue|enrich_cue_with_signals|write_pick_summaries|DIGEST_ITEM|_CUE_FRAMING' src/ tests/
```
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/digest.py src/pitcher_narratives/personas.py tests/test_digest.py tests/test_fact_parity.py
git commit -m "refactor: retire cue/DIGEST_ITEM path; re-express cross-path parity gate (P8B)"
```

---

## Task 5: Phase-8B wrap-up — full-suite gate + ledger

**Files:**
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: Run the full suite** (generous timeout — subprocess tests are slow)

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q
```
Expected: all pass except the documented `test_to_prompt_token_budget`. Any other failure is a real regression — fix before proceeding.

- [ ] **Step 2: Confirm `report` unchanged + retirements complete**

```bash
rg -n 'build_story_cue|enrich_cue_with_signals|write_pick_summaries|DIGEST_ITEM|_CUE_FRAMING' src/ tests/    # expect: none
git diff --stat <PLAN_COMMIT>..HEAD -- tests/test_cli.py    # expect: no edits to REPORT-path golden assertions
```

- [ ] **Step 3: Update the ledger**

Append `## Phase 8B: Morning → Mode RECAP` to `.superpowers/sdd/progress.md`: plan path, base commit, the 4 task commit SHAs, note that `report` stayed byte-identical (via `_render_capsule` extraction), morning now renders validated RECAP items with residual marking, the cue/`DIGEST_ITEM` path is retired, the fact-parity gate was re-expressed against shared `build_writer_input` grounding, and that the 8A explainer seam is resolved (recap runs with `check_explainer=False`). Note the deferred items (spine-once for `--mode report,recap`, G9 headers, recap-depth CLI knobs, `--mode changes`).

- [ ] **Step 4: Commit ledger note (if tracked) — else skip**

`.superpowers/sdd/progress.md` is gitignored scratch; do not `git add` it. This step is a no-op — the ledger edit persists on disk.

---

## Self-Review (spec coverage)

- **§9 morning becomes scout → select → one spine run per pick → Mode RECAP with typed `recap(analyzed, pick)` overlay** → Task 2 (`render_recap(ctx, analyzed, pick=)`) + Task 3 (morning calls it per pick, spine already once). ✓
- **§9 DIGEST_ITEM + _CUE_FRAMING retired; digest item gets Mode RECAP parity validation + residual surfacing** → Task 3 (validation via render_recap + residual marking) + Task 4 (retire). ✓
- **§9 assemble_digest scaffolding preserved** → untouched (Global Constraints + Task 3 keeps the `summaries` dict contract). ✓
- **§9 editorial category/angle/conviction via overlay (not from AnalyzedContext)** → Task 2 (`build_recap_overlay` from `pick.angle`/`pick.category`). ✓
- **§7 detection mandatory on every mode; only remediation depth tuned; LOUD residual surfacing** → Task 2 (recap runs anchor+capsule audit at depths 1/2, value_parity) + Task 3 (mark + run-summary count). ✓
- **§12 delete `build_story_cue`; retire cue path; rewrite `test_fact_parity`** → Task 4. ✓
- **§13.8 single-event-loop (G3) / agent reuse (G11)** → preserved: morning keeps one `asyncio.run`, one agent build (Task 3 Step 3). ✓
- **8A seam note #2 (explainer mandate vs brief)** → resolved: recap renders with `check_explainer=False` (Task 1/2). ✓
- **`report` byte-identical** → Task 1 extraction guarded by existing subprocess/threading tests (Global Constraints, Task 1 Step 5). ✓
- **Deferred correctly:** spine-once for `--mode report,recap`, G9 headers, `--recap-*-depth` knobs, `--mode changes` — Global Constraints. ✓
- **Placeholder scan:** implementer-judgment points (TestModel scaffolding in Tasks 1-3, the exact shared-grounding assertion in Task 4) each carry a note pointing at the existing code/test to mirror; no unspecified logic. ✓
- **Type consistency:** `_render_capsule`/`_RenderedCapsule`/`render_recap`/`build_recap_overlay` signatures match across their definition (Tasks 1-2) and consumers (`_run_pipeline`, morning Task 3); `PipelineResult` fields populated by `render_recap` match the model. ✓
