# Capsule Fact-Checking Layer (A + B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fact-checking layer on the final capsule — a deterministic value-parity advisory check (A) and a one-shot LLM capsule auditor that can drive one revision (B) — running after the anchor loop and before summarization.

**Architecture:** A is a pure module (`value_parity.py`) that flags capsule numbers not traceable to what the writer saw. B is a capsule-oriented data auditor in `pipeline.py` (mini model, MEDIUM budget) that semantically checks the capsule against raw ground truth and, on findings, triggers exactly one writer revision. Both wire into `_run_pipeline` between the anchor loop and `_run_summaries`; the corrected capsule flows to the summaries (which already run there).

**Tech Stack:** Python 3.14, pydantic / pydantic-ai (`Agent`, `TestModel`), pytest, `uv`.

## Global Constraints

- Python 3.14+; run via `uv run`. snake_case funcs, PascalCase Pydantic models, UPPER_SNAKE_CASE constants.
- Scope: single-pitcher report path only (`pipeline._run_pipeline`, `cli.py`). Do NOT touch `morning.py` / digest.
- **A is advisory — never blocks or triggers a revision.** Surfaced as `PipelineResult.value_parity_warnings` and printed by cli.
- **A matches as (metric_class, value) tuples, never a global number pool** — a `(velo, 81)` must NOT be satisfied by a `(pct, 81)`.
- **A matching is bidirectional** — a capsule "X% above average" matches a union grade via `100 + X` (and below-average via `100 − X`), and vice-versa.
- **A union = everything the writer saw**: rendered specialist inputs (ground truth) ∪ clean specialist outputs ∪ rendered key signals.
- **B ground truth = raw specialist inputs only** (the data tables) — NOT specialist prose.
- **B = mini model, `TOKEN_BUDGET_MEDIUM`, thinking capped medium, `retries=5`, run once**; on flags → exactly one writer revision; degrade-safe (errors logged, capsule unchanged).
- B runs before A; summaries reflect the B-corrected capsule.

---

### Task 1: A — metric-value extraction (`value_parity.py`)

**Files:**
- Create: `src/pitcher_narratives/value_parity.py`
- Test: `tests/test_value_parity.py`

**Interfaces:**
- Produces: `MetricValue = tuple[str, float]`; `extract_metric_values(text: str) -> set[MetricValue]`. Classes: `"grade"`, `"velo"`, `"pct"`, `"xrv100"`, `"pfx"`, `"delta"`. "X% above/below average" normalizes to a `("grade", 100±X)` tuple.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_value_parity.py`:

```python
from pitcher_narratives.value_parity import extract_metric_values


class TestExtractMetricValues:
    def test_grades_both_orders(self):
        v = extract_metric_values("a 130 Stuff+ pitch with S+ 112 and Location+ 97")
        assert ("grade", 130.0) in v
        assert ("grade", 112.0) in v
        assert ("grade", 97.0) in v

    def test_velocity(self):
        assert ("velo", 95.9) in extract_metric_values("sat 95.9 mph")

    def test_percent(self):
        assert ("pct", 25.0) in extract_metric_values("a 25.0% zone rate")

    def test_velo_and_pct_are_distinct_classes(self):
        v = extract_metric_values("81 mph fastball, 81% zone rate")
        assert ("velo", 81.0) in v
        assert ("pct", 81.0) in v  # same number, different class

    def test_xrv100_signed(self):
        v = extract_metric_values("xRV100 of -1.50 versus +0.32 xRV100")
        assert ("xrv100", -1.50) in v
        assert ("xrv100", 0.32) in v

    def test_percent_above_average_normalizes_to_grade(self):
        # "28% above average" == S+ 128
        assert ("grade", 128.0) in extract_metric_values("28% above average")

    def test_percent_below_average_normalizes_to_grade(self):
        assert ("grade", 87.0) in extract_metric_values("13% below average")

    def test_does_not_extract_word_numbers(self):
        # "two-seamer" must not yield a bogus value; no mph/%/grade context.
        assert extract_metric_values("his two-seamer and four-seamer") == set()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_value_parity.py -v`
Expected: FAIL — `ModuleNotFoundError: value_parity`.

- [ ] **Step 3: Implement extraction**

Create `src/pitcher_narratives/value_parity.py`:

```python
"""Deterministic value-parity check (advisory): flags capsule numbers that do
not trace to anything the writer saw. See the 2026-06-28 capsule-fact-checking
design. Advisory only — never blocks or triggers a revision."""

from __future__ import annotations

import re

from pydantic import BaseModel

__all__ = ["MetricValue", "ValueParityReport", "extract_metric_values", "check_value_parity"]

MetricValue = tuple[str, float]
"""(metric_class, value). Cross-class values never match; within-class match by tolerance."""

# "28% above average" -> ("grade", 128); "13% below average" -> ("grade", 87).
_PCT_VS_AVG = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%?\s+(above|below)\s+(?:league\s+)?average", re.I)
# grade: "S+ 130", "Stuff+ 130", "130 Stuff+", "130 S+"
_GRADE_AFTER = re.compile(r"(?:S\+|P\+|L\+|Stuff\+|Location\+|Pitching\+)\D{0,8}(\d{2,3})\b")
_GRADE_BEFORE = re.compile(r"\b(\d{2,3})\s+(?:S\+|P\+|L\+|Stuff\+|Location\+|Pitching\+)")
_VELO = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*mph")
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)")
_XRV = re.compile(r"xRV100\D{0,14}(-?\d+\.\d{1,2})|(-?\d+\.\d{1,2})\D{0,14}xRV100")
_PFX = re.compile(r"(-?\d+\.\d)\s*(?:in\b|inches)")


def extract_metric_values(text: str) -> set[MetricValue]:
    """Extract (metric_class, value) tuples from prose or rendered tables."""
    out: set[MetricValue] = set()
    for m in _PCT_VS_AVG.finditer(text):
        x = float(m.group(1))
        out.add(("grade", 100.0 + x if m.group(2).lower() == "above" else 100.0 - x))
    for rx in (_GRADE_AFTER, _GRADE_BEFORE):
        out.update(("grade", float(g)) for g in rx.findall(text))
    out.update(("velo", float(g)) for g in _VELO.findall(text))
    out.update(("pct", float(g)) for g in _PCT.findall(text))
    for a, b in _XRV.findall(text):
        out.add(("xrv100", float(a or b)))
    out.update(("pfx", float(g)) for g in _PFX.findall(text))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_value_parity.py -v`
Expected: PASS (8 tests). Adjust the regexes only as needed to make these exact cases pass.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/value_parity.py tests/test_value_parity.py
git commit -m "feat: add metric-value extraction for value-parity check"
```

---

### Task 2: A — class-aware tolerance matching (`check_value_parity`)

**Files:**
- Modify: `src/pitcher_narratives/value_parity.py`
- Test: `tests/test_value_parity.py`

**Interfaces:**
- Consumes: `extract_metric_values` (Task 1).
- Produces: `class ValueParityReport(BaseModel)` with `unmatched: list[str]` and `is_clean` property; `check_value_parity(capsule: str, union: str) -> ValueParityReport`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_value_parity.py`:

```python
from pitcher_narratives.value_parity import check_value_parity


class TestCheckValueParity:
    def test_clean_when_all_values_trace_to_union(self):
        union = "Velocity 81.3 mph. S+ 130. zone 25.0%."
        capsule = "an 81 mph pitch grading 130 S+ in the zone 25% of the time"
        assert check_value_parity(capsule, union).is_clean

    def test_cross_class_collision_is_flagged(self):
        # capsule cites a 95 mph velo; union only has 95 as a percentage.
        union = "chase rate 95%"
        report = check_value_parity("sat 95 mph", union)
        assert not report.is_clean  # (velo,95) must NOT match (pct,95)

    def test_out_of_tolerance_grade_flagged(self):
        union = "S+ 130"
        assert not check_value_parity("a 124 S+ slider", "S+ 130").is_clean

    def test_within_tolerance_grade_clean(self):
        # whole-number grade tolerance is +/-1
        assert check_value_parity("a 131 S+ slider", "S+ 130").is_clean

    def test_paraphrase_grade_matches_pct_above_average(self):
        # capsule says "28% above average"; union has the grade 128.
        assert check_value_parity("28% above average", "S+ 128").is_clean

    def test_hedged_number_not_flagged(self):
        # "around 90" is hedged; even with no union support it is not flagged.
        assert check_value_parity("around 90 mph", "velocity 95.0 mph").is_clean

    def test_fabricated_value_flagged(self):
        report = check_value_parity("a 145 S+ monster", "S+ 130. velo 95 mph.")
        assert not report.is_clean
        assert any("145" in u for u in report.unmatched)

    def test_indeterminate_class_not_flagged(self):
        # a bare number with no metric context has no class -> never flagged.
        assert check_value_parity("he threw 17 pitches", "").is_clean
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_value_parity.py::TestCheckValueParity -v`
Expected: FAIL — `cannot import name 'check_value_parity'`.

- [ ] **Step 3: Implement matching**

Append to `value_parity.py` (add `ValueParityReport` and `check_value_parity`; extend `__all__` already lists them):

```python
class ValueParityReport(BaseModel):
    """Advisory result: capsule values not traceable to the union."""

    unmatched: list[str]

    @property
    def is_clean(self) -> bool:
        return not self.unmatched


# Per-class match tolerance. Grades are whole-number (+/-1); others +/-0.5.
_TOLERANCE = {"grade": 1.0, "velo": 0.5, "pct": 0.5, "xrv100": 0.05, "pfx": 0.5, "delta": 1.0}

# Hedge markers: a number within ~20 chars before is the writer signaling
# uncertainty; not flagged regardless of union support.
_HEDGE = re.compile(r"\b(roughly|about|around|approximately)\b\s*~?\s*-?\d", re.I)


def _hedged_values(text: str) -> set[float]:
    out: set[float] = set()
    for m in _HEDGE.finditer(text):
        num = re.search(r"-?\d+(?:\.\d+)?", m.group(0))
        if num:
            out.add(float(num.group(0)))
    return out


def check_value_parity(capsule: str, union: str) -> ValueParityReport:
    """Flag capsule metric-values with no same-class match (within tolerance)
    anywhere in the union. Advisory; cross-class values never satisfy each
    other; hedged and indeterminate-class numbers are not flagged."""
    union_values = extract_metric_values(union)
    hedged = _hedged_values(capsule)
    unmatched: list[str] = []
    for cls, val in sorted(extract_metric_values(capsule)):
        if val in hedged:
            continue
        tol = _TOLERANCE[cls]
        if any(u_cls == cls and abs(u_val - val) <= tol for u_cls, u_val in union_values):
            continue
        unmatched.append(f"{cls}={val:g} (no match in source data)")
    return ValueParityReport(unmatched=unmatched)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_value_parity.py -v`
Expected: PASS (all Task 1 + Task 2 tests). If `test_hedged_number_not_flagged` fails because the velo regex also captured the hedged "90", confirm `_hedged_values` includes 90.0 and the skip works; adjust the hedge window if needed.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/value_parity.py tests/test_value_parity.py
git commit -m "feat: class-aware tolerance matching for value-parity (advisory)"
```

---

### Task 3: B — capsule-auditor prompt + input/revision builders

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add near `_DATA_AUDITOR_PROMPT`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `AuditFlag` (already imported from models).
- Produces: `_CAPSULE_AUDITOR_PROMPT: str`; `_build_capsule_ground_truth(ctx) -> str`; `_build_capsule_audit_input(ground_truth: str, capsule: str) -> str`; `build_fact_revision_message(capsule: str, flags: list[AuditFlag]) -> str` (add `build_fact_revision_message` to `__all__`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py` (import the new symbols):

```python
class TestCapsuleAuditBuilders:
    def test_capsule_ground_truth_concatenates_all_specialists(self, ctx):
        from pitcher_narratives.pipeline import _build_capsule_ground_truth
        gt = _build_capsule_ground_truth(ctx)
        # The stuff specialist's ground truth has the arsenal physical profile.
        assert "Arsenal Physical Profile" in gt
        assert "P vs S Location Impact" in gt  # location specialist's input

    def test_capsule_audit_input_has_both_sections(self):
        from pitcher_narratives.pipeline import _build_capsule_audit_input
        out = _build_capsule_audit_input("GROUND_TRUTH", "CAPSULE_TEXT")
        assert "GROUND_TRUTH" in out
        assert "CAPSULE_TEXT" in out
        assert out.index("GROUND_TRUTH") < out.index("CAPSULE_TEXT") or "GROUND TRUTH" in out

    def test_fact_revision_message_lists_flags(self):
        from pitcher_narratives.pipeline import build_fact_revision_message
        from pitcher_narratives.models import AuditFlag
        flags = [AuditFlag(category="FABRICATED_DATA", claim="98 mph", data_shows="95.9 mph", suggested_fix="use 95.9")]
        msg = build_fact_revision_message("the capsule text", flags)
        assert "the capsule text" in msg
        assert "FABRICATED_DATA" in msg
        assert "95.9 mph" in msg
        assert "ONLY" in msg  # instructs to fix only flagged issues
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pipeline.py::TestCapsuleAuditBuilders -v`
Expected: FAIL — import errors.

- [ ] **Step 3: Implement prompt + builders**

In `pipeline.py`, after `_DATA_AUDITOR_PROMPT`, add:

```python
_CAPSULE_AUDITOR_PROMPT = """\
You are a fact-checker for a baseball scouting report. You receive the raw \
ground-truth data for a pitcher and the finished narrative (the capsule). \
Verify every metric, direction, and factual claim in the capsule against the \
ground truth.

Flag these problems (reuse the audit categories):
- METRIC_CONTRADICTION: the capsule characterizes a metric in a way the data \
contradicts (calls a NORMAL metric extreme, etc.).
- DIRECTION_ERROR: the capsule states a metric/trend went one way but the data \
shows the other.
- FABRICATED_DATA: the capsule cites a specific number that does not appear in \
the ground truth.
- UNRECONCILED / HALLUCINATED_CAUSATION: a causal claim the data does not support.

Only flag genuine factual errors against the ground truth — not style, emphasis, \
or legitimate synthesis (deltas, contrasts, paraphrases of grades). If the \
capsule is faithful, return an empty list of flags."""


def _build_capsule_ground_truth(ctx: PitcherContext) -> str:
    """Combined raw ground truth (all five specialists' input tables)."""
    names = ["stuff", "location", "runvalue", "trends", "game_shape"]
    return "\n\n".join(_get_specialist_input_text(name, ctx) for name in names)


def _build_capsule_audit_input(ground_truth: str, capsule: str) -> str:
    """Auditor input: ground truth + the finished capsule to verify."""
    return (
        f"## GROUND TRUTH DATA\n{ground_truth}\n\n"
        f"## FINISHED CAPSULE TO FACT-CHECK\n{capsule}"
    )


def build_fact_revision_message(capsule: str, flags: list[AuditFlag]) -> str:
    """Ask the writer to correct ONLY the capsule's flagged factual errors."""
    formatted = "\n".join(
        f"- [{f.category}] \"{f.claim}\" → Data shows: {f.data_shows}. "
        f"Fix: {f.suggested_fix}"
        for f in flags
    )
    return (
        f"## Your Capsule\n{capsule}\n\n"
        f"## Factual Errors Found\n{formatted}\n\n"
        "Revise the capsule to correct ONLY these factual errors. Keep all "
        "other content, structure, voice, and length unchanged."
    )
```

Add `"build_fact_revision_message"` to `__all__`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pipeline.py::TestCapsuleAuditBuilders -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: capsule-auditor prompt, ground-truth + revision builders"
```

---

### Task 4: B — capsule_auditor agent + settings

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`PipelineAgents`, `make_pipeline_agents`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `_CAPSULE_AUDITOR_PROMPT` (Task 3), `make_model_settings`, `TOKEN_BUDGET_MEDIUM`, `AuditResult`.
- Produces: `PipelineAgents.capsule_auditor: Agent[None, AuditResult]`.

- [ ] **Step 1: Write the failing test**

Add to `TestMakePipelineAgents` in `tests/test_pipeline.py`:

```python
    def test_has_capsule_auditor_on_mini_model(self):
        agents = make_pipeline_agents("gemini", "high")
        assert agents.capsule_auditor is not None
        # Same mini tier as the other checker agents, distinct from the writer.
        assert agents.capsule_auditor.model == agents.auditor.model
        assert agents.capsule_auditor.model != agents.writer.model
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest "tests/test_pipeline.py::TestMakePipelineAgents::test_has_capsule_auditor_on_mini_model" -v`
Expected: FAIL — `PipelineAgents` has no field `capsule_auditor`.

- [ ] **Step 3: Implement**

In `PipelineAgents(NamedTuple)`, add a field after `auditor`:

```python
    capsule_auditor: Agent[None, AuditResult]
```

In `make_pipeline_agents`, add settings near `checker_settings`:

```python
    # Capsule auditor (B): checks the finished capsule against ALL ground truth
    # at once — a large input. MEDIUM budget + thinking medium so thinking can't
    # truncate the structured AuditResult (the report-then-summarize truncation
    # lesson); the existing per-specialist auditor stays on SMALL because its
    # input is one specialist's data.
    capsule_auditor_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.1, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)
```

And construct the agent in the returned `PipelineAgents(...)` (after `auditor=`):

```python
        capsule_auditor=Agent(mini_model, output_type=AuditResult, system_prompt=_CAPSULE_AUDITOR_PROMPT,
                              model_settings=capsule_auditor_settings, retries=5, defer_model_check=True),
```

(`NamedTuple` fields are positional — place the `capsule_auditor=` kwarg consistently; all constructor args here are keyword, so ordering is safe.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pipeline.py::TestMakePipelineAgents -v`
Expected: PASS (new test + existing factory tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: add capsule_auditor agent (mini, MEDIUM budget)"
```

---

### Task 5: B — `_run_capsule_audit` orchestration helper

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add helper before `_run_pipeline`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `_build_capsule_audit_input`, `build_fact_revision_message`, `agent_kwargs`.
- Produces: `async _run_capsule_audit(*, auditor, writer_agent, ground_truth, capsule, _model_override=None) -> tuple[str, list[AuditFlag], bool]` → `(corrected_capsule, flags, revised)`. Clean audit → `(capsule, [], False)`. Flagged → one writer revision → `(revised_capsule, flags, True)`. Any exception → `(capsule, [], False)` with a warning.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
class TestRunCapsuleAudit:
    class _CleanAuditor:
        async def run(self, **kwargs):
            from pitcher_narratives.models import AuditResult
            class _R:
                output = AuditResult(flags=[])
            return _R()

    class _FlaggingAuditor:
        async def run(self, **kwargs):
            from pitcher_narratives.models import AuditResult, AuditFlag
            class _R:
                output = AuditResult(flags=[AuditFlag(category="FABRICATED_DATA", claim="98 mph", data_shows="95.9", suggested_fix="use 95.9")])
            return _R()

    class _Writer:
        async def run(self, **kwargs):
            class _R:
                output = "corrected capsule"
            return _R()

    def test_clean_audit_no_revision(self):
        from pitcher_narratives.pipeline import _run_capsule_audit
        cap, flags, revised = asyncio.run(_run_capsule_audit(
            auditor=self._CleanAuditor(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "original capsule"
        assert flags == []
        assert revised is False

    def test_flagged_audit_triggers_one_revision(self):
        from pitcher_narratives.pipeline import _run_capsule_audit
        cap, flags, revised = asyncio.run(_run_capsule_audit(
            auditor=self._FlaggingAuditor(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "corrected capsule"
        assert len(flags) == 1
        assert revised is True

    def test_auditor_error_degrades_to_unchanged(self):
        from pitcher_narratives.pipeline import _run_capsule_audit
        class _Boom:
            async def run(self, **kwargs):
                raise RuntimeError("boom")
        cap, flags, revised = asyncio.run(_run_capsule_audit(
            auditor=_Boom(), writer_agent=self._Writer(),
            ground_truth="gt", capsule="original capsule",
        ))
        assert cap == "original capsule"
        assert flags == []
        assert revised is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pipeline.py::TestRunCapsuleAudit -v`
Expected: FAIL — `cannot import name '_run_capsule_audit'`.

- [ ] **Step 3: Implement the helper**

In `pipeline.py`, before `_run_pipeline`:

```python
async def _run_capsule_audit(
    *,
    auditor: Agent[None, AuditResult],
    writer_agent: Agent[None, str],
    ground_truth: str,
    capsule: str,
    _model_override: Any = None,
) -> tuple[str, list[AuditFlag], bool]:
    """B: fact-check the capsule against ground truth once; on flags, run one
    writer revision. Returns (corrected_capsule, flags, revised). Degrades to
    (capsule, [], False) on any error — non-fatal."""
    try:
        result = await auditor.run(
            **agent_kwargs(_build_capsule_audit_input(ground_truth, capsule), _model_override)
        )
        audit = result.output
    except Exception:
        log.warning("Capsule auditor failed, skipping fact-check.", exc_info=True)
        return capsule, [], False

    if audit.is_clean:
        return capsule, [], False

    log.info("Capsule auditor flagged %d issue(s); running one fact revision.", len(audit.flags))
    try:
        revision = await writer_agent.run(
            **agent_kwargs(build_fact_revision_message(capsule, audit.flags), _model_override)
        )
        return revision.output, audit.flags, True
    except Exception:
        log.warning("Fact revision failed, keeping pre-revision capsule.", exc_info=True)
        return capsule, audit.flags, False
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pipeline.py::TestRunCapsuleAudit -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: add _run_capsule_audit (one-shot fact-check + single revision)"
```

---

### Task 6: Wire B + A into `_run_pipeline`; extend `PipelineResult`

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`PipelineResult`, `_run_pipeline`, `__all__`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `_run_capsule_audit` (Task 5), `_build_capsule_ground_truth` (Task 3), `check_value_parity` + `_build_parity_union` (A).
- Produces: `PipelineResult.capsule_audit_flags: list[AuditFlag]`, `.capsule_revised: bool`, `.value_parity_warnings: list[str]`; `_build_parity_union(ctx, specialists, key_signals) -> str`.

- [ ] **Step 1: Write the failing test**

Add to `TestGeneratePipelineStreaming` in `tests/test_pipeline.py`:

```python
    def test_pipeline_result_has_fact_check_fields(self, ctx):
        test_model = TestModel(call_tools=[])
        result = generate_pipeline_streaming(
            ctx, provider="gemini", thinking="high", _model_override=test_model,
        )
        assert isinstance(result.capsule_audit_flags, list)
        assert isinstance(result.capsule_revised, bool)
        assert isinstance(result.value_parity_warnings, list)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest "tests/test_pipeline.py::TestGeneratePipelineStreaming::test_pipeline_result_has_fact_check_fields" -v`
Expected: FAIL — `PipelineResult` has no `capsule_audit_flags`.

- [ ] **Step 3: Implement**

Add imports at the top of `pipeline.py`:

```python
from pitcher_narratives.value_parity import ValueParityReport, check_value_parity
```

Extend `PipelineResult`:

```python
    capsule_audit_flags: list[AuditFlag] = []
    capsule_revised: bool = False
    value_parity_warnings: list[str] = []
```

Add the union builder (near `_build_capsule_ground_truth`):

```python
def _build_parity_union(ctx: PitcherContext, specialists: SpecialistOutputs, key_signals: KeySignals | None) -> str:
    """A's source-of-truth union: everything the writer saw — raw ground truth,
    clean specialist outputs, and the rendered key signals."""
    parts = [_build_capsule_ground_truth(ctx)]
    parts.extend([specialists.stuff, specialists.location, specialists.runvalue,
                  specialists.trends, specialists.game_shape])
    if key_signals is not None:
        parts.append(render_key_signals(key_signals))
    return "\n\n".join(parts)
```

In `_run_pipeline`, **between** the anchor-loop explainer re-check and the `_run_summaries` call, insert B then A:

```python
    # Fact-checking layer (B then A) on the final capsule.
    log.info("Fact-checking the capsule against ground truth...")
    capsule, capsule_audit_flags, capsule_revised = await _run_capsule_audit(
        auditor=agents.capsule_auditor,
        writer_agent=agents.writer,
        ground_truth=_build_capsule_ground_truth(ctx),
        capsule=capsule,
        _model_override=_model_override,
    )
    value_parity = check_value_parity(
        capsule, _build_parity_union(ctx, specialists, key_signals)
    )
```

The `_run_summaries(... capsule=capsule ...)` call is unchanged — it now receives the corrected capsule. Update the final `PipelineResult(...)` to pass `narrative=capsule` (already does) plus:

```python
        capsule_audit_flags=capsule_audit_flags,
        capsule_revised=capsule_revised,
        value_parity_warnings=value_parity.unmatched,
```

Add `"ValueParityReport"` is not needed in pipeline `__all__`; leave A's exports in its own module.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: PASS (new field test + all existing pipeline tests, including the anchor-loop and summary tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire capsule fact-check (B then A) into the pipeline"
```

---

### Task 7: cli surfacing + full-suite regression

**Files:**
- Modify: `src/pitcher_narratives/cli.py`
- Test: full suite; manual live run.

**Interfaces:**
- Consumes: `PipelineResult.capsule_audit_flags`, `.capsule_revised`, `.value_parity_warnings`.

- [ ] **Step 1: Add cli surfacing**

In `cli.py`, after the existing `# Data audit` block (which prints `pipe_result.audit_flags`), add a capsule fact-check section and a value-parity section, mirroring the style:

```python
    # Capsule fact-check (B)
    print("\n\n# Capsule Fact-Check\n")
    if pipe_result.capsule_audit_flags:
        verb = "corrected" if pipe_result.capsule_revised else "flagged (not auto-corrected)"
        print(f"Auditor {verb} {len(pipe_result.capsule_audit_flags)} issue(s):")
        for f in pipe_result.capsule_audit_flags:
            print(f"- **[{f.category}]** {f.claim}")
            print(f"  - Data shows: {f.data_shows}")
    else:
        print("Clean — no factual issues found.")

    # Value parity (A, advisory)
    if pipe_result.value_parity_warnings:
        print("\n\n# Value Parity (advisory)\n")
        print("Capsule numbers with no match in the source data:")
        for w in pipe_result.value_parity_warnings:
            print(f"- {w}")
```

- [ ] **Step 2: Verify the print path compiles + unit suite green**

Run: `uv run pytest tests/test_cli.py tests/test_pipeline.py tests/test_value_parity.py -q`
Expected: PASS. (If `test_cli.py` asserts exact output sections, update those expectations to include the new headings.)

- [ ] **Step 3: Full-suite regression**

Run: `uv run pytest -q`
Expected: PASS except the known pre-existing `tests/test_context.py::test_to_prompt_token_budget` failure (fails identically on `main`; unrelated). `tests/test_morning.py` must pass unmodified (B/A are report-path only).

- [ ] **Step 4: Manual live run (recommended)**

Run a real report for a known pitcher (e.g. `uv run python -m pitcher_narratives.cli report -p 592155`) and confirm the new `# Capsule Fact-Check` section renders, the report still completes, and value-parity advisories (if any) look sane (not flagging obviously-legitimate derived numbers).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat: surface capsule fact-check + value-parity advisories in cli"
```

---

## Self-Review

**1. Spec coverage:**
- A extraction → Task 1; A matching (class-aware, tolerance, paraphrase, hedge, indeterminate) → Task 2; A union + integration + surfacing → Tasks 6, 7. ✓
- B prompt + ground-truth (raw inputs only) + revision builder → Task 3; B agent (mini, MEDIUM, thinking medium, retries=5) → Task 4; B one-shot + single revision + degrade-safe → Task 5; B wiring before A, before summaries → Task 6. ✓
- Bidirectional paraphrase → Task 2 (`test_paraphrase_grade_matches_pct_above_average` + extraction normalization). ✓
- (metric_class, value) tuples, no global pool → Task 1/2 (`test_velo_and_pct_are_distinct_classes`, `test_cross_class_collision_is_flagged`). ✓
- A advisory only (no revision) → Tasks 6/7 (warnings surfaced, never fed to a revision). ✓
- Summaries reflect corrected capsule → Task 6 (B updates `capsule` before the unchanged `_run_summaries` call). ✓
- Result fields + cli → Tasks 6, 7. ✓
- Scope (report path only); morning untouched → Task 7 Step 3. ✓
- Non-goals (#3, #9) → not implemented, per spec. ✓

**2. Placeholder scan:** No TBD/"add error handling"/"similar to Task N" — every code step shows full code; regex tasks lead with concrete passing test cases as the contract. ✓

**3. Type consistency:** `check_value_parity(capsule, union) -> ValueParityReport` and `.unmatched: list[str]` used consistently (Tasks 2, 6, 7). `_run_capsule_audit(...) -> (str, list[AuditFlag], bool)` matches the `_run_pipeline` unpacking and the `PipelineResult` fields (Tasks 5, 6). `_build_capsule_ground_truth(ctx)` feeds both B (Task 6) and A's union (`_build_parity_union`). `extract_metric_values` returns `set[tuple[str, float]]` consumed by `check_value_parity`. ✓
