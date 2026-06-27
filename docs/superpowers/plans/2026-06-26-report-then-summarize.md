# Report-then-Summarize + Wider Revision Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make report summarization a second step that summarizes the *finished, anchored* narrative (not pre-revision specialist data), and raise the report's anchor revision ceiling from 3 to 5.

**Architecture:** In `pipeline._run_pipeline`, the executive summary and BRIEF stop running concurrently-with-and-before the writer. The writer streams, the anchor revision loop runs to convergence, and *then* both summarizers run concurrently against the final capsule plus recover-only grounding. BRIEF moves to a mini model. `MAX_REVISIONS` becomes 5.

**Tech Stack:** Python 3.14, pydantic-ai (`Agent`, `TestModel`), polars (unaffected), pytest, `uv` for running.

## Global Constraints

- Python 3.14+; run everything via `uv run`.
- snake_case modules/functions, PascalCase classes/Pydantic models, UPPER_SNAKE_CASE constants.
- Scope is the **single-pitcher report path** (`pipeline._run_pipeline`, consumed by `cli.py`). Do **not** touch `morning.py` / the digest path — it uses `run_analysis_spine` + digest summaries, not `agents.summary` / `agents.brief`.
- Grounding contract (verbatim intent): the **report is the summary's source of truth**; cite its numbers exactly as written; attached analyses are **recover-only** (supply a number the report stated qualitatively) — never correct a report number, never flag discrepancies, never add a finding the report did not make.
- No separate revision/critique loop for the summary step.
- `MAX_REVISIONS = 5` is an unvalidated ceiling (no telemetry); the anchor loop early-exits on the first clean check.

---

### Task 1: Raise MAX_REVISIONS to 5

**Files:**
- Modify: `src/pitcher_narratives/config.py:54`
- Test: `tests/test_pipeline.py` (add to `TestGeneratePipelineStreaming` or a small standalone test)

**Interfaces:**
- Consumes: nothing.
- Produces: `MAX_REVISIONS == 5` (already imported by `pipeline._run_pipeline` and existing tests).

- [ ] **Step 1: Write the failing test**

Add near the existing `test_max_revisions_constant_is_nonzero` in `tests/test_pipeline.py`:

```python
    def test_max_revisions_is_five(self):
        """The report anchor loop allows up to 5 revision passes."""
        from pitcher_narratives.config import MAX_REVISIONS
        assert MAX_REVISIONS == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/test_pipeline.py::TestGeneratePipelineStreaming::test_max_revisions_is_five" -v`
Expected: FAIL — `assert 3 == 5`.

- [ ] **Step 3: Make the change**

In `src/pitcher_narratives/config.py`, line 54:

```python
MAX_REVISIONS = 5
"""Maximum number of editor revision passes before accepting the capsule."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest "tests/test_pipeline.py::TestGeneratePipelineStreaming::test_max_revisions_is_five" tests/test_pipeline.py::TestGeneratePipelineStreaming -v`
Expected: PASS (and the existing `test_revision_count_within_bounds` / `test_max_revisions_constant_is_nonzero` still pass).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/config.py tests/test_pipeline.py
git commit -m "feat: raise MAX_REVISIONS to 5 for the report anchor loop"
```

---

### Task 2: Repoint BRIEF input framing at the finished report

**Files:**
- Modify: `src/pitcher_narratives/personas.py:183-208` (rename + rewrite `_BRIEF_FRAMING` → `_BRIEF_FRAMING_FROM_REPORT`) and `:327` (point `BRIEF.input_framing` at it)
- Test: `tests/test_personas.py` (rewrite 3 tests, keep 2)

**Interfaces:**
- Consumes: nothing.
- Produces: `BRIEF.input_framing` now describes a finished-capsule subject with recover-only grounding. `_BRIEF_STRUCTURE` is unchanged.

- [ ] **Step 1: Rewrite the affected tests (failing)**

In `tests/test_personas.py`, **replace** the three tests
`test_brief_framing_pins_thread_to_top_signals`,
`test_brief_framing_honors_sample_size_caution`,
`test_brief_framing_has_fallback_when_signals_absent`
with these (leave `test_brief_framing_contrasts_recent_against_window` and
`test_brief_framing_suppresses_model_teaching` untouched — they must keep passing):

```python
def test_brief_framing_leads_with_the_reports_thread():
    """BRIEF distills an already-anchored report, so it inherits the report's
    thread instead of re-deriving one from raw signals."""
    framing = BRIEF.input_framing
    assert "central thread" in framing
    assert "Do not re-derive a thread of your own" in framing


def test_brief_framing_preserves_report_hedging():
    """A finding the report stated tentatively must stay tentative."""
    framing = BRIEF.input_framing
    assert "tentative" in framing
    assert "never harden" in framing


def test_brief_framing_forbids_new_findings():
    """Grounding is recover-only: no finding the report did not make."""
    framing = BRIEF.input_framing
    assert "did not make" in framing
    # The raw-signal selection machinery is gone.
    assert "Do not pick by your own judgment" not in framing
    assert "fall back" not in framing
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_personas.py -k brief_framing -v`
Expected: the 3 new tests FAIL (old framing lacks the new tokens / still has the removed ones); the 2 surviving framing tests still PASS.

- [ ] **Step 3: Rewrite the framing constant**

In `src/pitcher_narratives/personas.py`, replace the `_BRIEF_FRAMING = """..."""` block (lines ~183-208) with:

```python
_BRIEF_FRAMING_FROM_REPORT = """\
INPUT: a finished scouting capsule (the report — distill THIS), followed by \
the clean specialist analyses it was built from (reference ONLY, to recover a \
metric the report states qualitatively). The capsule already contrasts the \
MOST RECENT appearance against how the pitcher has been trending across the \
window; your brief preserves that frame.

LEADING THE BRIEF: Lead with the report's central thread — its opening claim. \
Do not re-derive a thread of your own, and do not surface a finding the report \
did not make. The attached analyses exist only to supply an exact number when \
the report made a finding without one — never to correct a number the report \
gives, and never to flag a discrepancy.

PRESERVE THE REPORT'S CONFIDENCE: If the report states a finding tentatively \
(hedged language), keep it tentative; never harden a hedged claim into a \
settled one.

Write as one voice — do not name, number, or sequence the specialists. Unlike \
the full capsule, do NOT pause to explain the grading model; there is no room. \
Name a metric and move on.\
"""
```

Then update the `BRIEF` contract (line ~327):

```python
BRIEF = OutputContract(
    id="brief",
    length_target=(40, 90),
    structure=_BRIEF_STRUCTURE,
    input_framing=_BRIEF_FRAMING_FROM_REPORT,
)
```

- [ ] **Step 4: Run the full personas suite to verify pass + no regressions**

Run: `uv run pytest tests/test_personas.py -v`
Expected: PASS, including the 2 surviving framing tests and all `test_brief_structure_*` tests (structure is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/personas.py tests/test_personas.py
git commit -m "feat: repoint BRIEF framing at the finished report (recover-only grounding)"
```

---

### Task 3: Add `build_summary_input` helper

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add helper near `build_writer_input` ~line 763; add name to `__all__` ~line 108)
- Test: `tests/test_pipeline.py` (new `TestBuildSummaryInput` class)

**Interfaces:**
- Consumes: nothing.
- Produces: `build_summary_input(capsule: str, writer_input: str) -> str`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py` (import `build_summary_input` in the existing `from pitcher_narratives.pipeline import (...)` block):

```python
class TestBuildSummaryInput:
    def test_frames_capsule_as_subject_with_grounding(self):
        from pitcher_narratives.pipeline import build_summary_input
        out = build_summary_input("CAPSULE_TEXT", "WRITER_INPUT_TEXT")
        # Both payloads present.
        assert "CAPSULE_TEXT" in out
        assert "WRITER_INPUT_TEXT" in out
        # Capsule is the subject and comes first.
        assert out.index("CAPSULE_TEXT") < out.index("WRITER_INPUT_TEXT")
        # Contract markers present.
        assert "FINISHED REPORT" in out
        assert "reference ONLY" in out.replace("reference only", "reference ONLY")
        assert "do NOT add" in out or "do NOT correct" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::TestBuildSummaryInput -v`
Expected: FAIL — `ImportError: cannot import name 'build_summary_input'`.

- [ ] **Step 3: Implement the helper**

In `src/pitcher_narratives/pipeline.py`, add after `build_writer_input` (after line ~763):

```python
def build_summary_input(capsule: str, writer_input: str) -> str:
    """Frame the finished report as the summary subject, with the clean
    specialist analyses attached as recover-only grounding.

    The capsule is the source of truth: summaries cite its numbers as
    written. ``writer_input`` (Key Signals + clean specialist analyses) is
    reference ONLY — to recover a metric the report stated qualitatively,
    never to correct the report's numbers and never to add findings.
    """
    return (
        "## FINISHED REPORT (summarize THIS; cite its numbers exactly as written)\n"
        f"{capsule}\n\n"
        "## SOURCE ANALYSES (the clean specialist analyses the report was built "
        "from — reference ONLY to recover a metric the report stated "
        "qualitatively; do NOT correct the report's numbers and do NOT add "
        "findings absent from the report)\n"
        f"{writer_input}"
    )
```

Add `"build_summary_input"` to the `__all__` list (~line 108-117), keeping it alphabetically adjacent to `build_writer_input`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py::TestBuildSummaryInput -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: add build_summary_input (report subject + recover-only grounding)"
```

---

### Task 4: Reframe the executive summary prompt

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py:434-454` (`_EXECUTIVE_SUMMARY_PROMPT`)
- Test: `tests/test_pipeline.py` (new `TestExecutiveSummaryPrompt` class)

**Interfaces:**
- Consumes: nothing.
- Produces: `_EXECUTIVE_SUMMARY_PROMPT` now frames input as a finished report with recover-only grounding.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py` (import `_EXECUTIVE_SUMMARY_PROMPT` in the pipeline import block):

```python
class TestExecutiveSummaryPrompt:
    def test_prompt_targets_finished_report_with_recover_only_grounding(self):
        from pitcher_narratives.pipeline import _EXECUTIVE_SUMMARY_PROMPT
        p = _EXECUTIVE_SUMMARY_PROMPT
        assert "finished scouting report" in p.lower()
        # Recover-only grounding contract.
        assert "never change a number the report gives" in p
        assert "do not introduce a finding" in p.lower()
        # Old framing is gone.
        assert "Given specialist analyses" not in p
        # Citation requirement preserved.
        assert "cite a specific number" in p.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::TestExecutiveSummaryPrompt -v`
Expected: FAIL — current prompt says "Given specialist analyses" and lacks the new phrases.

- [ ] **Step 3: Rewrite the prompt**

Replace `_EXECUTIVE_SUMMARY_PROMPT` (lines ~434-454) with:

```python
_EXECUTIVE_SUMMARY_PROMPT = """\
You are a concise analyst producing a metrics-focused executive summary for \
a front office reader.

You are given a finished scouting report, followed by the clean specialist \
analyses it was built from (reference only). Produce exactly 3 bullet points \
that summarize the report. Each bullet states a finding the report makes and \
cites the metric that supports it.

RULES:
- Exactly 3 bullets. Each is ONE sentence.
- Summarize ONLY findings the report makes. Do not introduce a finding from \
the attached analyses that the report did not state.
- Every bullet MUST cite a specific number (S+, P+, xRV100, xWhiff_S, \
velocity, usage%, etc.), AS THE REPORT STATES IT. If the report makes a \
finding qualitatively without a figure, you may recover the supporting number \
from the attached analyses — but never change a number the report gives, and \
never flag a discrepancy.
- State the finding directly. No labels like "Best outcome:" or "Key trend:" \
— just the analytical observation.
- DIRECTIONAL CONSISTENCY: S+ below 100 is below average. S+ above 100 is \
above average. Negative xRV100 is good for the pitcher.
- Do not call normal metrics unusual. If a metric is within ±1.5 stddev of \
the league average, it is normal.
- Output ONLY the 3 bullet points. No headers, no intro, no outro.
- Format: each line starts with "- " followed by the insight."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py::TestExecutiveSummaryPrompt -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: reframe executive summary prompt to summarize the finished report"
```

---

### Task 5: Move BRIEF onto a mini model

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — `make_pipeline_agents` (`_brief` factory ~line 1134-1142; brief settings ~line 1102-1107; brief construction ~line 1159)
- Test: `tests/test_pipeline.py` (add to `TestMakePipelineAgents`)

**Interfaces:**
- Consumes: `make_model_settings`, `cap_thinking`, `TOKEN_BUDGET_SMALL`, `MINI_PROVIDERS` (all already imported).
- Produces: `make_pipeline_agents(...).brief` runs on the mini model and stays tool-free.

- [ ] **Step 1: Write the failing tests**

Add to `TestMakePipelineAgents` in `tests/test_pipeline.py`:

```python
    def test_brief_uses_mini_model(self):
        agents = make_pipeline_agents("gemini", "high")
        # BRIEF distills an already-written report — a mini model suffices.
        assert agents.brief.model == agents.summary.model
        assert agents.brief.model != agents.writer.model
```

(The existing `test_brief_agent_has_no_skill_toolset` must keep passing — BRIEF stays tool-free.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest "tests/test_pipeline.py::TestMakePipelineAgents::test_brief_uses_mini_model" -v`
Expected: FAIL — `agents.brief.model` is the main model (`google-gla:gemini-3.5-flash`), not the mini model.

- [ ] **Step 3: Implement the mini-model switch**

In `make_pipeline_agents`, add a `brief_settings` next to `summary_settings` (~line 1107):

```python
    brief_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.6, max_tokens=TOKEN_BUDGET_SMALL, mini=True)
```

Replace the `_brief` factory (~lines 1134-1142) with a mini version:

```python
    def _brief(prompt: str) -> Agent[None, str]:
        # Mini model: BRIEF distills an already-written, anchored report —
        # cheaper than composing it. Persona voice instructions still apply
        # via build_system_prompt(persona, BRIEF). Tool-free (a hallucinated
        # skill call must not kill this non-critical extra); retries=3 mirrors
        # the writer's resilience.
        return Agent(mini_model, output_type=str, system_prompt=prompt,
                     model_settings=brief_settings, retries=3,
                     defer_model_check=True)
```

The `brief=_brief(build_system_prompt(persona, BRIEF))` construction (~line 1159) is unchanged — it already routes through the new factory.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py::TestMakePipelineAgents -v`
Expected: PASS (new mini test + existing factory tests). Also: `uv run pytest "tests/test_pipeline.py::TestGeneratePipelineStreaming::test_brief_agent_has_no_skill_toolset" -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: move BRIEF agent onto the mini model"
```

---

### Task 6: Add the `_run_summaries` second-step helper

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — add `_parse_summary_bullets` and `_run_summaries` (place near `_run_anchor_revision_loop`, before `_run_pipeline`)
- Test: `tests/test_pipeline.py` — point `TestSummaryBulletParsing` at the real parser; add `TestRunSummaries`

**Interfaces:**
- Consumes: `build_summary_input` (Task 3), `agent_kwargs`, `asyncio`, `log`.
- Produces:
  - `_parse_summary_bullets(raw: str) -> list[str]`
  - `async _run_summaries(*, summary_agent, brief_agent, capsule: str, writer_input: str, _model_override=None) -> tuple[list[str], str]` — returns `([], "")` for an empty/whitespace capsule without calling either agent; otherwise runs both concurrently, each catching its own failure and degrading to its empty value.

- [ ] **Step 1: Write the failing tests**

First, replace the private `_parse` method body in `TestSummaryBulletParsing` so it calls the real function (keeps the existing 4 assertions honest):

```python
class TestSummaryBulletParsing:
    """Test the bullet parsing logic used by the summary step."""

    def _parse(self, raw: str) -> list[str]:
        from pitcher_narratives.pipeline import _parse_summary_bullets
        return _parse_summary_bullets(raw)
    # (existing test_standard_bullets / test_ignores_non_bullet_lines /
    #  test_strips_whitespace / test_empty_input methods stay as-is)
```

Then add a new class:

```python
class TestRunSummaries:
    class _BoomAgent:
        """Stand-in agent whose run() always raises (and proves non-call)."""
        async def run(self, **kwargs):
            raise RuntimeError("boom")

    def test_empty_capsule_skips_both_agents(self):
        from pitcher_narratives.pipeline import _run_summaries
        boom = self._BoomAgent()
        bullets, brief = asyncio.run(_run_summaries(
            summary_agent=boom, brief_agent=boom,
            capsule="   \n  ", writer_input="ignored",
        ))
        assert bullets == []
        assert brief == ""

    def test_populated_capsule_runs_both(self):
        from pitcher_narratives.pipeline import _run_summaries
        agents = make_pipeline_agents("gemini", "high")
        tm = TestModel(call_tools=[], custom_output_text="- one\n- two")
        bullets, brief = asyncio.run(_run_summaries(
            summary_agent=agents.summary, brief_agent=agents.brief,
            capsule="A real capsule.", writer_input="grounding",
            _model_override=tm,
        ))
        assert bullets == ["one", "two"]
        assert brief == "- one\n- two"

    def test_one_failure_degrades_without_cancelling_sibling(self):
        from pitcher_narratives.pipeline import _run_summaries
        agents = make_pipeline_agents("gemini", "high")
        tm = TestModel(call_tools=[], custom_output_text="- kept")
        # Summary agent booms; brief must still produce output.
        bullets, brief = asyncio.run(_run_summaries(
            summary_agent=self._BoomAgent(), brief_agent=agents.brief,
            capsule="A real capsule.", writer_input="grounding",
            _model_override=tm,
        ))
        assert bullets == []
        assert brief == "- kept"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py::TestRunSummaries tests/test_pipeline.py::TestSummaryBulletParsing -v`
Expected: FAIL — `ImportError: cannot import name '_parse_summary_bullets' / '_run_summaries'`.

- [ ] **Step 3: Implement the helpers**

In `src/pitcher_narratives/pipeline.py`, add before `_run_pipeline` (after `_run_anchor_revision_loop`):

```python
def _parse_summary_bullets(raw: str) -> list[str]:
    """Parse '- '-prefixed lines from summary output into clean bullets."""
    return [
        line.lstrip("- ").strip()
        for line in raw.strip().splitlines()
        if line.strip().startswith("- ")
    ]


async def _run_summaries(
    *,
    summary_agent: Agent[None, str],
    brief_agent: Agent[None, str],
    capsule: str,
    writer_input: str,
    _model_override: Any = None,
) -> tuple[list[str], str]:
    """Second-step summarization of the FINISHED capsule.

    Runs the executive summary and BRIEF concurrently, each fed the final
    capsule plus recover-only grounding (see build_summary_input). Returns
    ([], "") without calling either agent when the capsule is empty/
    whitespace. Each summarizer catches its own failure and degrades to an
    empty value, so one failing agent never cancels the other.
    """
    if not capsule.strip():
        log.warning("Final capsule is empty; skipping summarization.")
        return [], ""

    summary_input = build_summary_input(capsule, writer_input)

    async def _run_summary() -> list[str]:
        try:
            result = await summary_agent.run(**agent_kwargs(summary_input, _model_override))
            return _parse_summary_bullets(result.output)
        except Exception:
            log.warning("Executive summary agent failed, skipping.", exc_info=True)
            return []

    async def _run_brief() -> str:
        try:
            result = await brief_agent.run(**agent_kwargs(summary_input, _model_override))
            return result.output.strip()
        except Exception:
            log.warning("Brief agent failed, skipping.", exc_info=True)
            return ""

    bullets, brief = await asyncio.gather(_run_summary(), _run_brief())
    return bullets, brief
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py::TestRunSummaries tests/test_pipeline.py::TestSummaryBulletParsing -v`
Expected: PASS (all parsing tests + the 3 new helper tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: add _run_summaries second-step helper (empty guard + degrade-safe gather)"
```

---

### Task 7: Wire the second step into `_run_pipeline`

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — `_run_pipeline` (~lines 1368-1467) and `_render_pipeline_data_sections` (~lines 972-984)
- Test: `tests/test_pipeline.py` (existing `TestGeneratePipelineStreaming` smoke tests must still pass; add an exec-summary smoke assertion)

**Interfaces:**
- Consumes: `_run_summaries` (Task 6), `build_summary_input` (Task 3), the mini BRIEF agent (Task 5), `MAX_REVISIONS == 5` (Task 1).
- Produces: `PipelineResult` whose `executive_summary` / `brief` are derived from the **final** capsule.

- [ ] **Step 1: Write/extend the failing test**

Add to `TestGeneratePipelineStreaming` in `tests/test_pipeline.py`:

```python
    def test_pipeline_result_includes_executive_summary(self, ctx):
        """The terminal layer runs the executive summary against the final
        capsule and returns parsed bullets."""
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert isinstance(result.executive_summary, list)
```

(With `TestModel(call_tools=[])` the model emits its default str output; bullets may parse to an empty list, so assert the type/structure — the wiring, not the content.)

- [ ] **Step 2: Run test to verify current behavior**

Run: `uv run pytest tests/test_pipeline.py::TestGeneratePipelineStreaming -v`
Expected: the new test passes structurally even before wiring (the field already exists), so this task is verified primarily by **no regression** in `test_pipeline_result_includes_brief` after the reorder. Proceed to the implementation and rely on Step 4's full-suite run as the gate.

- [ ] **Step 3: Reorder `_run_pipeline`**

In `src/pitcher_narratives/pipeline.py`, in `_run_pipeline`:

(a) **Remove** the two pre-writer background launches (currently ~lines 1376-1384):

```python
    # Run summary and brief in background while writer streams (same input as
    # the writer: key signals block + clean specialist analyses).
    summary_task = asyncio.create_task(
        agents.summary.run(**agent_kwargs(writer_input, _model_override))
    )
    brief_task = asyncio.create_task(
        agents.brief.run(**agent_kwargs(writer_input, _model_override))
    )
```

So the block from building `writer_kwargs` flows straight into the writer stream. Keep `writer_input` and `writer_kwargs` — `writer_input` is now also the grounding for summaries.

(b) **Remove** the post-writer await/parse blocks for summary and brief (currently ~lines 1395-1414, the two `try/except` blocks producing `summary_bullets` and `brief_text`).

(c) **Add** a progress log before the anchor loop call (~line 1440):

```python
    log.info("Revising report (anchor check loop)...")
    capsule, anchor_check, revision_count = await _run_anchor_revision_loop(
        anchor_agent=agents.anchor,
        writer_agent=agents.writer,
        synthesis=synthesis,
        capsule=capsule,
        max_revisions=MAX_REVISIONS,
        _model_override=_model_override,
    )
```

(d) **After** the post-revision explainer re-check (~line 1457), and **before** the `return PipelineResult(...)`, add the second-step summarization:

```python
    # Second step: summarize the FINISHED, anchored report (not the
    # pre-revision specialist data). writer_input is attached as recover-only
    # grounding inside _run_summaries.
    log.info("Writing summary and brief from the final report...")
    summary_bullets, brief_text = await _run_summaries(
        summary_agent=agents.summary,
        brief_agent=agents.brief,
        capsule=capsule,
        writer_input=writer_input,
        _model_override=_model_override,
    )
```

(e) The `return PipelineResult(...)` is unchanged — it already references `summary_bullets` and `brief_text`.

- [ ] **Step 4: Update `_render_pipeline_data_sections` trace notes**

Replace the EXECUTIVE SUMMARY and BRIEF "User Message" notes (~lines 972-984) so the trace shows the real second-step input shape:

```python
    sections.append(f"\n{sep}\nEXECUTIVE SUMMARY (second step — summarizes the final report)\n{sep}\n")
    sections.append(f"## System Prompt\n\n{_EXECUTIVE_SUMMARY_PROMPT}\n")
    sections.append(
        "## User Message\n\n"
        + build_summary_input(
            "[final report capsule, post anchor-revision]",
            "[writer input: key signals + clean specialist analyses]",
        )
        + "\n"
    )

    sections.append(f"\n{sep}\nBRIEF (second step — summarizes the final report)\n{sep}\n")
    sections.append(f"## System Prompt\n\n{build_system_prompt(persona_obj, BRIEF)}\n")
    sections.append(
        "## User Message\n\n"
        + build_summary_input(
            "[final report capsule, post anchor-revision]",
            "[writer input: key signals + clean specialist analyses]",
        )
        + "\n"
    )
```

- [ ] **Step 5: Run the full pipeline + persona suites**

Run: `uv run pytest tests/test_pipeline.py tests/test_personas.py -v`
Expected: PASS — notably `test_pipeline_result_includes_brief`, `test_pipeline_result_includes_executive_summary`, the anchor-loop tests, and the key-signals tests. No regressions.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: summarize the finished report as a second step after the anchor loop"
```

---

### Task 8: Full-suite regression + manual smoke

**Files:**
- Test: entire `tests/` suite; optional manual CLI smoke.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: green suite; confirmation the morning path is untouched.

- [ ] **Step 1: Run the whole test suite**

Run: `uv run pytest -q`
Expected: PASS. Pay attention to `tests/test_morning.py` and `tests/test_voice_golden.py` — both must pass **unmodified** (morning uses `run_analysis_spine`/digest; no BRIEF golden exists in `test_voice_golden.py`).

- [ ] **Step 2: Manual prompt-trace smoke (optional but recommended)**

Run: `uv run python -m pitcher_narratives.cli --help` then a `--print-prompts` run for a known pitcher (per `cli.py` flags) and visually confirm the EXECUTIVE SUMMARY / BRIEF sections now render the `build_summary_input` shape (FINISHED REPORT + SOURCE ANALYSES).

- [ ] **Step 3: Commit (if any trace/doc tweaks were needed)**

```bash
git add -A
git commit -m "test: full-suite regression for report-then-summarize"
```

---

## Self-Review

**1. Spec coverage:**
- `MAX_REVISIONS` 3→5 → Task 1. ✓
- Summarizers fed final capsule + recover-only grounding → Tasks 3 (helper), 6 (`_run_summaries`), 7 (wiring). ✓
- Grounding named honestly / recover-not-correct / no-new-findings → Tasks 3, 4, 2 (prompt + framing text). ✓
- BRIEF framing survive/drop list → Task 2 (rewrite + tests). ✓
- BRIEF → mini model → Task 5. ✓
- gather degrade-to-empty semantics → Task 6 (per-coroutine try/except). ✓
- Empty-capsule guard; anchor-loop-on-empty non-goal → Task 6 (guard) + Global Constraints. ✓
- Progress/perceived-hang → Task 7 (log.info before anchor loop + before summary; goes to stderr via setup_logging). ✓
- `_render_pipeline_data_sections` renders real input shape → Task 7 Step 4. ✓
- Tests for mini switch + new framing → Tasks 5, 2. ✓
- Morning path untouched → Task 8 verification. ✓

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" — every code step shows full code. The Task 7 Step 2 note explains *why* the structural test is weak (TestModel ignores input) rather than leaving a gap. ✓

**3. Type consistency:** `build_summary_input(capsule, writer_input) -> str` used identically in Tasks 3, 6, 7. `_run_summaries(... ) -> tuple[list[str], str]` returns `(summary_bullets, brief_text)`, matching the `PipelineResult(executive_summary=..., brief=...)` fields. `_parse_summary_bullets` signature consistent between Task 6 definition and `TestSummaryBulletParsing` usage. `agents.brief.model == agents.summary.model` assertion matches the probed string-valued `Agent.model`. ✓
