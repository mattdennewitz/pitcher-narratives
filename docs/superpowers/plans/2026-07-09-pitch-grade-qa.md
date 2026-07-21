# Pitch-Grade Q&A (`ask` command) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI `ask` command that explains, in grounded scout prose, why a pitcher's pitch earns its P+/S+/L+ grade — as the first skill in a growing skill-driven Q&A library.

**Architecture:** `ask` is a thin front-end over the analysis spine's frame-agnostic front-half. It resolves the pitcher, builds the same `PitcherContext` the report uses, reuses the spine's `_build_stuff_input`/`_build_location_input` evidence (already baseline-annotated with NORMAL/OUTLIER tags and the S+ class average via `render_league_baselines`), runs one focused Q&A agent that consults a new `audience: runtime` skill, then fact-checks the answer with the existing data-auditor. No parallel data-tool layer.

**Tech Stack:** Python 3.14, polars, pydantic-ai, argparse, pytest, uv.

## Global Constraints

- Python 3.14+; run everything with `uv run` (bare `python` lacks polars).
- Tests run with `uv run pytest`; `testpaths = ["tests"]`. Tests must be **offline** — never call a live LLM; stub agents.
- The LLM never computes statistics — all numbers come from the reused, pre-computed input.
- Deterministic question parsing mirrors the existing `resolver.extract_pitcher_from_question` pattern (no LLM extraction).
- Reuse over rebuild: no new `grades.py`, no bespoke data tools.
- The runtime skill must declare `audience: runtime` (the gate in `agent_skills._audience`).
- Provider default is `gemini` (matches existing subcommands); the ask agent uses the capable model `PROVIDERS[provider]`, not a mini model.
- v1 grades the **latest season present in the data** — `load_pitcher_data` keys off max season, so there is no `--season` flag (spec's optional `--season` is deferred; note this deviation).

---

### Task 1: Deterministic question parsing

**Files:**
- Create: `src/pitcher_narratives/qa.py`
- Test: `tests/test_qa_parse.py`

**Interfaces:**
- Consumes: `resolver.extract_pitcher_from_question(question) -> tuple[str | None, ResolveResult | None]`; `ResolveResult(pitcher_id, pitcher_name, candidates, match_type)`.
- Produces: `parse_grade_question(question: str) -> GradeQuestion`; `class GradeQuestion` (fields: `pitcher_id: int`, `pitcher_name: str`, `grade_family: str` in `{"S","L","P"}`, `pitch_noun: str`, `pitch_candidates: list[str]`, `cited_value: float | None`); `class QuestionError(Exception)`. Also module constants `PITCH_SYNONYMS`, `GRADE_SYNONYMS`, `GRADE_LABELS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_qa_parse.py
"""Deterministic parsing of grade-explanation questions (no LLM, real resolver)."""

import pytest

from pitcher_narratives.qa import GradeQuestion, QuestionError, parse_grade_question


def test_parses_jones_fastball_stuff():
    q = parse_grade_question("why does Jared Jones's fastball grade 92 stuff+")
    assert q.pitcher_id == 683003
    assert q.grade_family == "S"
    assert q.pitch_candidates == ["FF", "SI"]  # "fastball" is ambiguous; reconciled later
    assert q.cited_value == 92.0


def test_grade_family_location_and_pitching():
    assert parse_grade_question("Jared Jones slider location+").grade_family == "L"
    assert parse_grade_question("Jared Jones curveball pitching+").grade_family == "P"


def test_grade_family_defaults_to_stuff():
    assert parse_grade_question("Jared Jones changeup").grade_family == "S"


def test_specific_pitch_beats_generic():
    # "four-seam" must win over the substring "fastball" logic and map to FF only.
    assert parse_grade_question("Jared Jones four-seam stuff+").pitch_candidates == ["FF"]


def test_unknown_pitcher_raises():
    with pytest.raises(QuestionError, match="pitcher"):
        parse_grade_question("why does the fastball grade 92 stuff+")


def test_no_pitch_raises():
    with pytest.raises(QuestionError, match="pitch"):
        parse_grade_question("how good is Jared Jones")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_qa_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pitcher_narratives.qa'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/pitcher_narratives/qa.py
"""Grade-explanation Q&A: parse a natural-language question, then narrate a
grounded answer over the analysis spine's reused specialist input.

Public: parse_grade_question, answer_question, QuestionError, GradeQuestion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pitcher_narratives.resolver import extract_pitcher_from_question

__all__ = ["GradeQuestion", "QuestionError", "answer_question", "parse_grade_question"]


class QuestionError(Exception):
    """A user-facing problem with the question (bad pitcher, missing pitch, out of scope)."""


# Pitch nouns -> Statcast pitch-type codes. "fastball"/"heater" are ambiguous
# (FF or SI) and get reconciled against the pitcher's actual arsenal later.
PITCH_SYNONYMS: dict[str, list[str]] = {
    "four-seam": ["FF"], "four seam": ["FF"], "4-seam": ["FF"], "4 seam": ["FF"],
    "fastball": ["FF", "SI"], "heater": ["FF", "SI"], "fourseam": ["FF"],
    "sinker": ["SI"], "two-seam": ["SI"], "two seam": ["SI"], "twoseam": ["SI"],
    "cutter": ["FC"], "cut fastball": ["FC"],
    "sweeper": ["ST"], "slider": ["SL"],
    "knuckle curve": ["KC"], "knuckle-curve": ["KC"],
    "curveball": ["CU"], "curve": ["CU"],
    "changeup": ["CH"], "change-up": ["CH"], "change up": ["CH"], "change": ["CH"],
    "splitter": ["FS"], "split-finger": ["FS"], "split": ["FS"],
}

# Grade family detection. Order within each family is longest-first so
# "stuff+" is preferred over a bare "stuff".
GRADE_SYNONYMS: list[tuple[str, str]] = [
    ("location+", "L"), ("location plus", "L"), ("command", "L"), ("location", "L"), ("l+", "L"),
    ("pitching+", "P"), ("pitching plus", "P"), ("pitching", "P"), ("p+", "P"),
    ("stuff+", "S"), ("stuff plus", "S"), ("stuff", "S"), ("s+", "S"),
]

GRADE_LABELS: dict[str, str] = {
    "S": "Stuff+ (S+)", "L": "Location+ (L+)", "P": "Pitching+ (P+)",
}


@dataclass
class GradeQuestion:
    """A parsed grade-explanation question, before arsenal reconciliation."""

    pitcher_id: int
    pitcher_name: str
    grade_family: str
    pitch_noun: str
    pitch_candidates: list[str] = field(default_factory=list)
    cited_value: float | None = None


def _detect_grade(q: str) -> str:
    for phrase, family in GRADE_SYNONYMS:
        if phrase in q:
            return family
    return "S"  # default: Stuff+


def _detect_pitch(q: str) -> tuple[str, list[str]]:
    # Longest key first so "four-seam" wins over "fastball", "curveball" over "curve".
    for noun in sorted(PITCH_SYNONYMS, key=len, reverse=True):
        if noun in q:
            return noun, PITCH_SYNONYMS[noun]
    return "", []


def _detect_value(q: str) -> float | None:
    m = re.search(r"\b(\d{2,3})\b", q)
    return float(m.group(1)) if m else None


def parse_grade_question(question: str) -> GradeQuestion:
    """Parse a 'why does X's <pitch> grade <value> <grade>' question.

    Deterministic: pitcher via the resolver, pitch + grade via keyword maps.
    Raises QuestionError for an unresolvable pitcher or a missing pitch noun.
    """
    _matched, res = extract_pitcher_from_question(question)
    if res is None or res.pitcher_id is None:
        if res is not None and res.match_type == "ambiguous":
            names = ", ".join(name for _pid, name in res.candidates)
            raise QuestionError(f"Ambiguous pitcher — did you mean: {names}?")
        raise QuestionError("Couldn't find a pitcher in that question.")

    lowered = question.lower()
    pitch_noun, candidates = _detect_pitch(lowered)
    if not candidates:
        raise QuestionError(
            "Couldn't tell which pitch — name one, e.g. 'fastball' or 'slider'."
        )
    return GradeQuestion(
        pitcher_id=res.pitcher_id,
        pitcher_name=res.pitcher_name or "",
        grade_family=_detect_grade(lowered),
        pitch_noun=pitch_noun,
        pitch_candidates=candidates,
        cited_value=_detect_value(question),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_qa_parse.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/qa.py tests/test_qa_parse.py
git commit -m "feat(qa): deterministic grade-question parsing"
```

---

### Task 2: `build_grade_input` — public grade-family input dispatcher

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add function + `__all__` entry near the other `_build_*_input` builders and the `__all__` block around line 132)
- Test: `tests/test_grade_input.py`

**Interfaces:**
- Consumes: `pipeline._build_stuff_input(ctx) -> UserPrompt`, `pipeline._build_location_input(ctx) -> UserPrompt` (existing, private); `context.assemble_pitcher_context`, `data.load_pitcher_data`.
- Produces: `pipeline.build_grade_input(ctx: PitcherContext, family: str) -> UserPrompt`. `family` in `{"S","L","P"}`; `"P"` returns stuff-input concatenated with location-input.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grade_input.py
"""build_grade_input reuses the spine's specialist inputs and surfaces the
grade + S+ class baseline the ask agent anchors to."""

import pytest

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.pipeline import build_grade_input


@pytest.fixture(scope="module")
def jones_ctx():
    return assemble_pitcher_context(load_pitcher_data(683003))  # Jones, Jared


def _text(parts):
    return "\n".join(p for p in parts if isinstance(p, str))


def test_stuff_input_contains_ff_grade_and_class_baseline(jones_ctx):
    text = _text(build_grade_input(jones_ctx, "S"))
    assert "FF" in text
    assert "S+" in text                 # per-pitch grade present
    assert "S-variant league avg" in text  # class baseline (avg_s_plus) present


def test_pitching_input_includes_both_stuff_and_location(jones_ctx):
    text = _text(build_grade_input(jones_ctx, "P"))
    assert "Arsenal Physical Profile" in text          # from stuff input
    assert "Location" in text or "location" in text     # from location input


def test_unknown_family_raises(jones_ctx):
    with pytest.raises(ValueError, match="family"):
        build_grade_input(jones_ctx, "X")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grade_input.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_grade_input'`

- [ ] **Step 3: Write minimal implementation**

Add this function next to `_build_location_input` in `src/pitcher_narratives/pipeline.py`:

```python
def build_grade_input(ctx: PitcherContext, family: str) -> UserPrompt:
    """Public dispatcher: the grounded specialist input for a grade family.

    S -> stuff input (S+ evidence); L -> location input (L+ evidence);
    P -> stuff + location (P+ = stuff + location; P - S isolates location).
    Reused verbatim from the analysis spine so the ask command and the
    report share one grounded evidence surface.
    """
    if family == "S":
        return _build_stuff_input(ctx)
    if family == "L":
        return _build_location_input(ctx)
    if family == "P":
        return [*_build_stuff_input(ctx), *_build_location_input(ctx)]
    raise ValueError(f"Unknown grade family {family!r}; expected 'S', 'L', or 'P'")
```

Then add `"build_grade_input"` to the `__all__` list (around `pipeline.py:132`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grade_input.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_grade_input.py
git commit -m "feat(pipeline): public build_grade_input dispatcher for grade Q&A"
```

---

### Task 3: `run_data_audit` — public standalone fact-check

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add async function + `__all__` entry)
- Test: `tests/test_run_data_audit.py`

**Interfaces:**
- Consumes: `pipeline.make_pipeline_agents(provider) -> PipelineAgents` (has `.auditor`); `pipeline._build_specialist_audit_input(ground_truth, specialist_output) -> str` (existing, private, same module); `config.agent_kwargs`; `models.AuditResult`.
- Produces: `async pipeline.run_data_audit(ground_truth: str, answer: str, *, provider: str = "gemini", model_override=None) -> AuditResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_data_audit.py
"""run_data_audit routes ground-truth + answer through the spine's auditor."""

import asyncio
import types

from pitcher_narratives import pipeline
from pitcher_narratives.models import AuditFlag, AuditResult


def test_run_data_audit_uses_auditor(monkeypatch):
    captured = {}

    class StubAuditor:
        async def run(self, **kwargs):
            captured["user_prompt"] = kwargs.get("user_prompt")
            return types.SimpleNamespace(
                output=AuditResult(flags=[
                    AuditFlag(category="FABRICATED_DATA", specialist="qa",
                              claim="c", data_shows="d", suggested_fix="f"),
                ])
            )

    monkeypatch.setattr(
        pipeline, "make_pipeline_agents",
        lambda *a, **k: types.SimpleNamespace(auditor=StubAuditor()),
    )

    result = asyncio.run(pipeline.run_data_audit("GROUND", "ANSWER", provider="gemini"))
    assert not result.is_clean
    assert "GROUND" in captured["user_prompt"] and "ANSWER" in captured["user_prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_data_audit.py -v`
Expected: FAIL with `AttributeError: module 'pitcher_narratives.pipeline' has no attribute 'run_data_audit'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/pitcher_narratives/pipeline.py` (near `audit_and_revise_specialists`), and add `"run_data_audit"` to `__all__`:

```python
async def run_data_audit(
    ground_truth: str,
    answer: str,
    *,
    provider: str = "gemini",
    model_override: Any = None,
) -> AuditResult:
    """Fact-check a single free-form answer against its ground-truth input.

    Reuses the spine's data-auditor agent so a Q&A answer gets the same
    anti-fabrication guard as a report specialist.
    """
    agents = make_pipeline_agents(provider)
    audit_input = _build_specialist_audit_input(ground_truth, answer)
    result = await agents.auditor.run(**agent_kwargs(audit_input, model_override))
    return result.output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_data_audit.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_run_data_audit.py
git commit -m "feat(pipeline): public run_data_audit for standalone fact-checks"
```

---

### Task 4: The `explaining-pitch-grades` runtime skill

**Files:**
- Create: `src/pitcher_narratives/skills/explaining-pitch-grades/SKILL.md`
- Test: `tests/test_qa_skill.py`

**Interfaces:**
- Consumes: `agent_skills.runtime_skill_names()` (existing).
- Produces: a runtime-audience skill discoverable by name `explaining-pitch-grades`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_qa_skill.py
"""The grade-explanation skill loads into runtime agents."""

from pitcher_narratives.agent_skills import runtime_skill_names


def test_explaining_pitch_grades_is_runtime_skill():
    assert "explaining-pitch-grades" in runtime_skill_names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_qa_skill.py -v`
Expected: FAIL (`assert 'explaining-pitch-grades' in [...]`)

- [ ] **Step 3: Write the skill**

```markdown
<!-- src/pitcher_narratives/skills/explaining-pitch-grades/SKILL.md -->
---
name: explaining-pitch-grades
description: Use when explaining why a specific pitch earns its Pitching+ grade (P+, S+/Stuff+, or L+/Location+) from the provided arsenal data — anchoring the grade to its pitch-type class baseline, reading NORMAL/OUTLIER shape, and reconciling the grade with xRV100.
audience: runtime
---

# Explaining a pitch's P+ / S+ / L+ grade

A grade is the end of a chain: physical pitch -> the model's outcome
predictions -> grade. Explain it by walking that chain over the data you were
given. Do not compute anything — every number is already in the input.

## Method

1. **Anchor to the pitch-type class baseline, not 100.** The input's
   "S-variant league avg: S+ ..." line is the average grade *for that pitch
   type*. Four-seam fastballs sit below the all-pitch 100; breaking balls sit
   above. Read the pitch's grade against its own class line, then explain the
   gap from there — "92 vs the ~97 fastball average" beats "92 vs 100".
2. **A NORMAL trait is not a driver.** Each physical trait is tagged NORMAL or
   OUTLIER. If velocity/spin is an OUTLIER but the grade is unremarkable, the
   story is that the *shape* (movement, ride, arm-slot fit) doesn't separate
   from expectation — the model prices the shape, not the radar reading. Never
   invent a velocity-causation story.
3. **Reconcile the sign.** Sub-100 S+ should pair with a positive (costly)
   xRV100_S; above-100 with negative (run-saving). If they disagree, report the
   discrepancy honestly rather than forcing a story.
4. **Cite the metric behind each claim.** "misses bats" -> xWhiff_S; "hitters
   attack it" -> xSwing_S; "hittable" -> xRV100_S.
5. **Contrast with the arsenal.** A grade reads differently next to the
   pitcher's other pitches — a plus breaker beside an average fastball tells a
   tunneling story.

See the `pitching-plus-conventions` skill for the authoritative sign
conventions and the NORMAL/OUTLIER rule.

## Output

1-3 tight paragraphs of scout prose about the ONE pitch named in the leading
instruction. No preamble, no restating the question.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_qa_skill.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/skills/explaining-pitch-grades/SKILL.md tests/test_qa_skill.py
git commit -m "feat(skills): explaining-pitch-grades runtime skill"
```

---

### Task 5: `answer_question` orchestration

**Files:**
- Modify: `src/pitcher_narratives/qa.py` (add agent factory + orchestration; extend `__all__`)
- Test: `tests/test_qa_answer.py`

**Interfaces:**
- Consumes: `parse_grade_question` (Task 1); `data.load_pitcher_data`; `context.assemble_pitcher_context`; `pipeline.build_grade_input` (Task 2), `pipeline.run_data_audit` (Task 3), `pipeline.build_fact_revision_message` (existing); `agent_skills.skill_toolset`; `config.PROVIDERS`, `config.make_model_settings`, `config.agent_kwargs`, `config.TOKEN_BUDGET_LARGE`; `PitchTypeSummary` fields `.pitch_type`, `.pitch_name`, `.n_pitches_window`.
- Produces: `async answer_question(question, *, provider="gemini", model_override=None) -> str`; `build_qa_agent(provider="gemini") -> Agent`; `resolve_pitch_against_arsenal(candidates, arsenal) -> tuple[str, str]`; `QA_SYSTEM_PROMPT`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_qa_answer.py
"""answer_question resolves the pitch against the arsenal, runs the (stubbed)
agent over reused input, and fact-checks — all offline."""

import asyncio
import types

import pytest

from pitcher_narratives import qa
from pitcher_narratives.models import AuditResult


class StubAgent:
    def __init__(self, out): self._out = out
    async def run(self, **kwargs):
        return types.SimpleNamespace(output=self._out)


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setattr(qa, "build_qa_agent", lambda provider="gemini": StubAgent("STUB ANSWER"))
    async def _clean(*a, **k): return AuditResult(flags=[])
    monkeypatch.setattr(qa, "run_data_audit", _clean)


def test_answer_returns_agent_output():
    out = asyncio.run(qa.answer_question("why does Jared Jones's fastball grade 92 stuff+"))
    assert out == "STUB ANSWER"


def test_pitch_not_in_arsenal_raises():
    # Jones (683003) throws no splitter.
    with pytest.raises(qa.QuestionError, match="throw"):
        asyncio.run(qa.answer_question("why does Jared Jones's splitter grade 90 stuff+"))


def test_resolve_pitch_prefers_most_thrown():
    arsenal = [
        types.SimpleNamespace(pitch_type="SI", pitch_name="Sinker", n_pitches_window=20),
        types.SimpleNamespace(pitch_type="FF", pitch_name="Four-Seam", n_pitches_window=200),
    ]
    assert qa.resolve_pitch_against_arsenal(["FF", "SI"], arsenal) == ("FF", "Four-Seam")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_qa_answer.py -v`
Expected: FAIL with `AttributeError: module 'pitcher_narratives.qa' has no attribute 'build_qa_agent'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/pitcher_narratives/qa.py` (and add `"build_qa_agent"`, `"resolve_pitch_against_arsenal"` to `__all__`):

```python
from pydantic_ai import Agent

from pitcher_narratives.agent_skills import skill_toolset
from pitcher_narratives.config import (
    PROVIDERS,
    TOKEN_BUDGET_LARGE,
    agent_kwargs,
    make_model_settings,
)
from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.pipeline import (
    build_fact_revision_message,
    build_grade_input,
    run_data_audit,
)

QA_SYSTEM_PROMPT = """\
You explain why a single pitch earns its Pitching+ grade (P+/S+/L+), for a \
front-office reader.

You are given pre-computed data for the pitcher's full arsenal: per-pitch \
grades, each physical trait tagged NORMAL or OUTLIER versus league, the \
S-variant league average for each pitch type, stuff-model predictions \
(xWhiff/xSwing/xRV100), and arm-slot shape. A leading instruction names the \
ONE pitch and grade to explain.

Consult the `explaining-pitch-grades` skill for the method before answering.

Rules:
- Explain ONLY the named pitch and grade; use the rest of the arsenal as contrast.
- Every number comes from the provided data — never compute or invent a statistic.
- If the data needed is missing, say so plainly.
- Answer in 1-3 tight paragraphs of scout prose. No preamble."""


def build_qa_agent(provider: str = "gemini") -> Agent[None, str]:
    """The focused grade-explanation agent: capable model + the skill library."""
    return Agent(
        PROVIDERS[provider],
        output_type=str,
        system_prompt=QA_SYSTEM_PROMPT,
        model_settings=make_model_settings(provider, "medium", 0.3, max_tokens=TOKEN_BUDGET_LARGE),
        toolsets=[skill_toolset()],
        retries=3,
        defer_model_check=True,
    )


def resolve_pitch_against_arsenal(candidates: list[str], arsenal: list) -> tuple[str, str]:
    """Pick the arsenal pitch matching the parsed candidates (most-thrown wins).

    Raises QuestionError listing the real arsenal if none of the candidates
    are thrown (e.g. asking about a splitter he doesn't have).
    """
    present = [p for p in arsenal if p.pitch_type in candidates]
    if not present:
        thrown = ", ".join(f"{p.pitch_name} ({p.pitch_type})" for p in arsenal)
        raise QuestionError(f"He doesn't throw that. Pitches: {thrown}.")
    best = max(present, key=lambda p: p.n_pitches_window)
    return best.pitch_type, best.pitch_name


async def answer_question(
    question: str,
    *,
    provider: str = "gemini",
    model_override=None,
) -> str:
    """Answer 'why does <pitcher>'s <pitch> grade <value> <grade>' in prose."""
    q = parse_grade_question(question)
    data = load_pitcher_data(q.pitcher_id)
    ctx = assemble_pitcher_context(data)
    pitch_type, pitch_name = resolve_pitch_against_arsenal(q.pitch_candidates, ctx.arsenal)

    grade_input = build_grade_input(ctx, q.grade_family)
    ground_truth = "\n".join(p for p in grade_input if isinstance(p, str))
    scoping = (
        f"Explain ONLY the {pitch_name} ({pitch_type}) and its "
        f"{GRADE_LABELS[q.grade_family]}. Use the rest of the arsenal as contrast."
    )

    agent = build_qa_agent(provider)
    result = await agent.run(**agent_kwargs([scoping, *grade_input], model_override))
    answer = result.output

    audit = await run_data_audit(ground_truth, answer, provider=provider, model_override=model_override)
    if not audit.is_clean:
        revision = build_fact_revision_message(ground_truth, answer, audit.flags)
        result = await agent.run(**agent_kwargs(revision, model_override))
        answer = result.output
    return answer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_qa_answer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/qa.py tests/test_qa_answer.py
git commit -m "feat(qa): answer_question orchestration over the reused spine input"
```

---

### Task 6: `ask` CLI subcommand

**Files:**
- Modify: `src/pitcher_narratives/cli.py` (add `ask` subparser in `parse_args`; add `_run_ask_command`; add dispatch branch in `main`)
- Test: `tests/test_cli_ask.py`

**Interfaces:**
- Consumes: `qa.answer_question`, `qa.QuestionError`; `config.PROVIDERS` (for `--provider` choices).
- Produces: CLI command `pn ask "<question>" [--provider gemini]` printing the answer to stdout.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_ask.py
"""The `ask` subcommand parses and dispatches to qa.answer_question."""

import pytest

from pitcher_narratives import cli, qa


def test_ask_subparser_parses(monkeypatch):
    monkeypatch.setattr("sys.argv", ["pn", "ask", "why does Jared Jones's fastball grade 92 stuff+"])
    args = cli.parse_args()
    assert args.command == "ask"
    assert "Jared Jones" in args.question
    assert args.provider == "gemini"


def test_ask_command_prints_answer(monkeypatch, capsys):
    async def _fake(question, *, provider="gemini", model_override=None):
        return "ANSWER TEXT"
    monkeypatch.setattr(qa, "answer_question", _fake)
    ns = type("NS", (), {"command": "ask", "question": "Jared Jones fastball stuff+", "provider": "gemini"})()
    cli._run_ask_command(ns)
    assert "ANSWER TEXT" in capsys.readouterr().out


def test_ask_command_reports_question_error(monkeypatch, capsys):
    async def _boom(question, *, provider="gemini", model_override=None):
        raise qa.QuestionError("Couldn't find a pitcher in that question.")
    monkeypatch.setattr(qa, "answer_question", _boom)
    ns = type("NS", (), {"command": "ask", "question": "nonsense", "provider": "gemini"})()
    with pytest.raises(SystemExit):
        cli._run_ask_command(ns)
    assert "pitcher" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_ask.py -v`
Expected: FAIL (`AttributeError: ... has no attribute '_run_ask_command'`, or the subparser assertion fails)

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/cli.py`, add the subparser inside `parse_args` (after the existing subparsers, before `return parser.parse_args()`):

```python
    ask = sub.add_parser("ask", help="Explain why a pitcher's pitch earns its P+/S+/L+ grade")
    ask.add_argument("question", help='e.g. "why does Jared Jones\'s fastball grade 92 stuff+"')
    ask.add_argument("--provider", default="gemini", choices=sorted(PROVIDERS),
                     help="LLM provider (default: gemini)")
```

Ensure `PROVIDERS` is imported at the top of `cli.py`:

```python
from pitcher_narratives.config import PROVIDERS
```

Add the command handler:

```python
def _run_ask_command(args: argparse.Namespace) -> None:
    """Answer a single grade-explanation question and print the prose."""
    import asyncio

    from pitcher_narratives.qa import QuestionError, answer_question

    setup_logging()
    try:
        answer = asyncio.run(answer_question(args.question, provider=args.provider))
    except QuestionError as e:
        print(f"pitcher-narratives: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:  # pitcher id not present in Statcast data
        print(f"pitcher-narratives: {e}", file=sys.stderr)
        sys.exit(1)
    print(answer)
```

Add the dispatch branch in `main`:

```python
    elif args.command == "ask":
        _run_ask_command(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_ask.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite + a live smoke check**

Run: `uv run pytest tests/test_qa_parse.py tests/test_grade_input.py tests/test_run_data_audit.py tests/test_qa_skill.py tests/test_qa_answer.py tests/test_cli_ask.py -v`
Expected: all PASS.

Live smoke (requires provider API key; not part of CI):
Run: `uv run pn ask "why does Jared Jones's fastball grade 92 stuff+"`
Expected: 1-3 paragraphs that anchor to the ~97 fastball class baseline, read the shape as NORMAL despite OUTLIER velocity, and avoid a velocity-causation story.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli_ask.py
git commit -m "feat(cli): ask subcommand for pitch-grade Q&A"
```

---

## Self-Review

**Spec coverage:**
- Command & UX → Task 6 (`--season` deferred, noted in Global Constraints).
- Reuse the spine's front-half (context + `_build_*_input` + auditor) → Tasks 2, 3, 5.
- Focused Q&A agent carrying the skill library → Task 5 (`build_qa_agent`).
- Runtime skill (skill #1) → Task 4.
- Deterministic parsing → Task 1.
- P+ = stuff + location → Task 2.
- One revision on auditor flags → Task 5.
- Error handling (not found / ambiguous / not-in-arsenal / out-of-scope) → Tasks 1, 5, 6.
- Testing (parse, reuse-contract, auditor integration, behavioral smoke) → Tasks 1–6.

**Placeholder scan:** none — every step carries runnable code/commands.

**Type consistency:** `GradeQuestion.grade_family` ∈ {"S","L","P"} used consistently by `build_grade_input` and `GRADE_LABELS`; `resolve_pitch_against_arsenal` reads `.pitch_type/.pitch_name/.n_pitches_window` (the fields `_build_stuff_input` uses); `run_data_audit` returns `AuditResult` whose `.is_clean`/`.flags` Task 5 consumes; `build_fact_revision_message(ground_truth, answer, flags)` matches its existing signature.

**Open item confirmed during planning:** the S+ class baseline the skill anchors to is already in the reused input via `render_league_baselines` (`LeagueBaseline.avg_s_plus`) — no enrichment task needed. Frame is the latest-season window from `load_pitcher_data`; the cited grade is `season_s_plus` as rendered by `_build_stuff_input`.
