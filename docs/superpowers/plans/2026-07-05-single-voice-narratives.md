# Single-Voice Narratives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the three writer voices (scout/analyst/generic) into one fixed voice, bind output structure to the deliverable (mode), and drop the separate brief — so the tool produces three purpose-built deliverables (scouting report, changes report, morning report) off one shared analytical spine.

**Architecture:** `personas.py` collapses from `Persona × OutputContract × NarrationMode.contracts` to a single `WRITER_VOICE` string constant plus three `NarrationMode`s that each own their `structure`, `input_framing`, and `length_target`. Composition flattens to `build_writer_system_prompt(mode)`. The `persona` parameter is removed from every pipeline/CLI signature. Done additively-then-delete: introduce the new composer alongside the old, cut the pipeline/CLI over, then delete the dead machinery — every task ends with a green suite.

**Tech Stack:** Python 3.14, polars, pydantic-ai, pytest, `uv`.

## Global Constraints

- Python 3.14+; run everything via `uv run` (e.g. `uv run pytest ...`).
- Tests that load pitcher data need `PITCHER_NARRATIVES_DATA_DIR` pointed at the original repo checkout when run from this worktree. Prefix data-loading test commands with `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` if a "data file not found" error appears.
- The scouting report and changes report are **model-focused**: they explain the pitcher *through the lens of the model* (`EXPLAIN THE MODEL` is core to their framing). The morning report is a bare capsule (no `EXPLAIN THE MODEL`).
- Single voice only. No `--persona`, no `--format`, no per-voice branching anywhere.
- Deliverable lengths: scouting report 350–600 words; changes report 250–450; morning capsule 60–120.
- This is a **full re-baseline**, not byte-identity: composed prompts change intentionally. Regenerate fixtures deliberately and review each diff.
- Spec: `docs/superpowers/specs/2026-07-05-single-voice-narratives-design.md`.

---

## File Structure

| File | Responsibility after this plan |
|------|-------------------------------|
| `src/pitcher_narratives/personas.py` | One `WRITER_VOICE` constant; `SHARED_WRITER_BASE`; the synthesis-framing constants; three `NarrationMode`s owning `structure`/`input_framing`/`length_target`; `build_writer_system_prompt(mode)`. No `Persona`, no registry, no `OutputContract`. |
| `src/pitcher_narratives/pipeline.py` | Spine + agents composed from `mode` only; no `persona`; no separate brief; hallucination check with a single fixed allowlist. |
| `src/pitcher_narratives/cli.py` | `report`/`morning` without `--persona`/`--list-personas`; diagnostics without persona. |
| `src/pitcher_narratives/morning.py` | Morning digest builds recap capsules off the shared spine, no persona. |
| `src/pitcher_narratives/grounding.py` (or wherever `_KNOWN_METRICS` lives) | Single metric allowlist including the former analyst teaching terms. |
| `bench/runner.py`, `bench/__main__.py` | No persona threading. |
| `tests/fixtures/*.txt` | 3 fixtures (`writer_prompt_report.txt`, `writer_prompt_changes.txt`, `writer_prompt_recap.txt`); the 9 persona×mode fixtures deleted. |
| `tests/test_*.py` | Rewritten per the inventories embedded below. |

> **Note on `_PERSONA_KNOWN_METRICS` / `_KNOWN_METRICS` location:** the persona-blast-radius scan places `check_hallucinated_metrics`, `_KNOWN_METRICS`, and `_PERSONA_KNOWN_METRICS` in `pipeline.py` (~2755–2860). Confirm with `grep -n "_PERSONA_KNOWN_METRICS\|_KNOWN_METRICS\|def check_hallucinated_metrics" src/pitcher_narratives/*.py` at the start of Task 3 and edit whichever file holds them.

---

## Task 1: Single voice + mode-owned structure + new composer (additive)

Introduce the new voice, the mode-owned structure/framing/length, and a new composer **alongside** the existing machinery. Nothing is deleted; the old fixtures/tests stay green. This task's deliverable is a new function `build_mode_writer_prompt(mode)` whose output is pinned to three freshly-authored fixtures.

**Files:**
- Modify: `src/pitcher_narratives/personas.py` (add constants, add `NarrationMode` fields, add composer)
- Create: `tests/fixtures/writer_prompt_report.txt`, `tests/fixtures/writer_prompt_changes.txt`, `tests/fixtures/writer_prompt_recap.txt`
- Create: `tests/test_single_voice.py`

**Interfaces:**
- Produces: `WRITER_VOICE: str`; `NarrationMode.structure: str`, `NarrationMode.input_framing: str`, `NarrationMode.length_target: tuple[int, int]` (new fields, defaulted); `build_mode_writer_prompt(mode: NarrationMode, *, explain_model: bool = True) -> str`.
- Consumes: existing `SHARED_WRITER_BASE`, `_SYNTHESIS_RULES`, `_SYNTHESIS_FRAMING`, `_EXPLAIN_THE_MODEL`, `_CHANGES_MANDATE`, `REPORT`, `CHANGES`, `RECAP`.

- [ ] **Step 1: Add the voice + structure + framing constants**

In `personas.py`, after the existing framing constants (below `_CHANGES_MANDATE`, before the `OutputContract` constants block ~line 412), add:

```python
# ═══════════════════════════════════════════════════════════════════════
# SINGLE WRITER VOICE — the field-facing analyst/scout hybrid (design §3)
# ═══════════════════════════════════════════════════════════════════════

WRITER_VOICE = """\
You are a field-facing baseball analyst — the voice that sits between the \
analytics department and the coaching staff, translating what the model sees \
into language a front office and a pitching coach both trust.

VOICE:
- Direct and specific. Analyst-to-analyst, not fan-facing. Vary sentence \
length; short sentences land points.
- Use scouting language: stuff, feel, finding a groove, getting tagged.
- Explain the model as you go. When you name S+, L+, or P+, take a clause or \
a sentence to say what it measures and what the model decided — enough that \
the read stands on the model, not on assertion. Explain to illuminate the \
pitcher, never to admire the model.
- No cheerleading, no clichés, no formulaic transitions, no "the data shows," \
no newsletter framing ("what we're seeing here"). Start immediately with the \
analysis.\
"""

# ═══════════════════════════════════════════════════════════════════════
# PER-MODE OUTPUT STRUCTURES (design §4) — one structure per deliverable
# ═══════════════════════════════════════════════════════════════════════

_REPORT_STRUCTURE = """\
Compose a flowing prose narrative — 350-600 words, 3-5 paragraphs — that \
explains this pitcher through the lens of the model.

STRUCTURE:
- Lead with what the model sees: the single most important read on this \
pitcher right now, grounded in the grade that drives it.
- Develop the read across the arsenal — how the stuff plays, where location \
helps or hurts, what the run-value and trend picture add. Thread the \
specialist findings into one story; do not section them.
- Weave platoon splits where they matter. Close on a clear-eyed verdict.
- Prose only. No headings, no bullet lists, no tables.
- At most three primary metrics carry any single paragraph; you may cite a \
metric twice if the second citation explains the first.

HARD LIMIT: 600 words. If you approach 550, wrap up.\
"""

_CHANGES_STRUCTURE = """\
Compose a medium-length change report — 250-450 words — framed as what MOVED \
in the recent window versus the longer historical period.

STRUCTURE:
- Lead with the single biggest shift, stated concretely, with the one grade \
or metric that proves it — and what the model reads into it.
- Walk the connected changes in order of consequence. Report only what moved; \
a stable trait earns a sentence only when it frames a change.
- Prefer deltas to states. Distinguish a mechanical adjustment (a release or \
extension shift alongside a velo or shape change) from a pitch-mix change.
- Prose only. No headings, no bullet lists, no tables.
- Three-metric maximum per change.

HARD LIMIT: 450 words. If you approach 400, wrap up.\
"""

_RECAP_CAPSULE_STRUCTURE = """\
Write a tight capsule on the pitcher's most recent appearance — 3 to 5 \
sentences, one continuous thread, no headings or bullets.

- Lead with the single most important thing the model saw in the most recent \
appearance (the biggest change, adaptation, or execution read).
- Support it with one or two grounding metrics drawn straight from the \
analyses.
- Close on what it means going forward. Keep it scannable and quotable.

Target 60-120 words; never exceed 5 sentences.\
"""

# Per-mode input framing (design §4.1). report/changes carry EXPLAIN THE MODEL
# (model-focused); recap is bare synthesis. The changes mandate rides in the
# framing now (not the structure). EXPLAIN THE MODEL stays appended last so the
# explain_model=False strip in build_mode_writer_prompt removes it cleanly.
_REPORT_FRAMING = _SYNTHESIS_FRAMING  # _SYNTHESIS_RULES + "\n\n" + _EXPLAIN_THE_MODEL
_CHANGES_FRAMING = (
    _SYNTHESIS_RULES + "\n\n" + _CHANGES_MANDATE + "\n\n" + _EXPLAIN_THE_MODEL
)
_RECAP_FRAMING = _SYNTHESIS_RULES
```

- [ ] **Step 2: Add the three mode fields (defaulted) and set them on the modes**

In `personas.py`, add three fields to `NarrationMode` (after `anchor_guidance`, ~line 528). Defaults keep every existing `NarrationMode(...)` construction valid:

```python
    structure: str = ""
    input_framing: str = ""
    length_target: tuple[int, int] = (0, 0)
```

Then set them on the three module-level modes. For `REPORT` (~line 537), add inside the constructor call:

```python
    structure=_REPORT_STRUCTURE,
    input_framing=_REPORT_FRAMING,
    length_target=(350, 600),
```

For `RECAP` (~line 553) add:

```python
    structure=_RECAP_CAPSULE_STRUCTURE,
    input_framing=_RECAP_FRAMING,
    length_target=(60, 120),
```

For `CHANGES` (~line 569) add:

```python
    structure=_CHANGES_STRUCTURE,
    input_framing=_CHANGES_FRAMING,
    length_target=(250, 450),
```

Leave the existing `contracts=` maps in place for now (deleted in Task 5).

- [ ] **Step 3: Add the new composer**

In `personas.py`, add near `build_writer_system_prompt` (~line 819):

```python
def build_mode_writer_prompt(
    mode: NarrationMode, *, explain_model: bool = True
) -> str:
    """Compose the writer system prompt for a deliverable (mode).

    Order: universal analytical rules + mode input framing + the single
    writer voice + mode structure. ``explain_model=False`` strips the
    EXPLAIN THE MODEL mandate from the framing (report/changes only; recap
    never carries it).
    """
    framing = mode.input_framing
    if not explain_model:
        framing = framing.replace("\n\n" + _EXPLAIN_THE_MODEL, "").replace(
            _EXPLAIN_THE_MODEL, ""
        )
    return "\n\n".join([SHARED_WRITER_BASE, framing, WRITER_VOICE, mode.structure])
```

Add `"WRITER_VOICE"` and `"build_mode_writer_prompt"` to `__all__`.

- [ ] **Step 4: Write the invariant tests (failing)**

Create `tests/test_single_voice.py`:

```python
"""Single-voice composition invariants (design §4-5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pitcher_narratives.personas import (
    CHANGES,
    RECAP,
    REPORT,
    SHARED_WRITER_BASE,
    WRITER_VOICE,
    build_mode_writer_prompt,
)

_FIX = Path(__file__).parent / "fixtures"
_MODES = {"report": REPORT, "changes": CHANGES, "recap": RECAP}


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_prompt_starts_with_base_then_contains_voice(mode_id):
    p = build_mode_writer_prompt(_MODES[mode_id])
    assert p.startswith(SHARED_WRITER_BASE)
    assert WRITER_VOICE in p


@pytest.mark.parametrize("mode_id,present", [
    ("report", True), ("changes", True), ("recap", False),
])
def test_explain_the_model_presence_by_mode(mode_id, present):
    p = build_mode_writer_prompt(_MODES[mode_id])
    assert ("EXPLAIN THE MODEL" in p) is present


def test_explain_model_false_strips_mandate_for_report():
    p = build_mode_writer_prompt(REPORT, explain_model=False)
    assert "EXPLAIN THE MODEL" not in p


def test_changes_framing_carries_the_change_mandate():
    p = build_mode_writer_prompt(CHANGES)
    assert "report what has CHANGED" in p or "what MOVED" in p


@pytest.mark.parametrize("mode_id,phrase", [
    ("report", "350-600 words"),
    ("changes", "250-450 words"),
    ("recap", "60-120 words"),
])
def test_structure_length_phrase_present(mode_id, phrase):
    assert phrase in build_mode_writer_prompt(_MODES[mode_id])


def test_three_modes_produce_distinct_prompts():
    prompts = {m: build_mode_writer_prompt(mode) for m, mode in _MODES.items()}
    assert len(set(prompts.values())) == 3


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_matches_frozen_fixture(mode_id):
    expected = (_FIX / f"writer_prompt_{mode_id}.txt").read_text()
    assert build_mode_writer_prompt(_MODES[mode_id]) == expected
```

- [ ] **Step 5: Run tests — fixtures missing, some pass**

Run: `uv run pytest tests/test_single_voice.py -v`
Expected: the invariant tests PASS; the three `test_matches_frozen_fixture` cases FAIL with `FileNotFoundError` (fixtures not yet created).

- [ ] **Step 6: Generate the three fixtures**

Run this to author the fixtures from the composer output, then eyeball each for voice/structure correctness:

```bash
uv run python -c "
from pathlib import Path
from pitcher_narratives.personas import REPORT, CHANGES, RECAP, build_mode_writer_prompt
fix = Path('tests/fixtures')
for mid, mode in {'report': REPORT, 'changes': CHANGES, 'recap': RECAP}.items():
    (fix / f'writer_prompt_{mid}.txt').write_text(build_mode_writer_prompt(mode))
    print('wrote', mid)
"
```

Then review: `git diff --stat` and open each new fixture. Confirm the report/changes prompts read model-focused and the recap is a bare capsule.

- [ ] **Step 7: Run tests — all pass**

Run: `uv run pytest tests/test_single_voice.py -v`
Expected: PASS (all cases).

- [ ] **Step 8: Run the full suite — still green (old machinery untouched)**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: no NEW failures vs. the pre-task baseline. (The 3 known pre-existing failures noted in `.superpowers/sdd/progress.md` may persist; nothing new breaks.)

- [ ] **Step 9: Commit**

```bash
git add src/pitcher_narratives/personas.py tests/test_single_voice.py tests/fixtures/writer_prompt_report.txt tests/fixtures/writer_prompt_changes.txt tests/fixtures/writer_prompt_recap.txt
git commit -m "feat(personas): single voice + mode-owned structure (additive)

Add WRITER_VOICE, per-mode structure/framing/length, and
build_mode_writer_prompt alongside the existing persona machinery.
Three new fixtures pin the composed prompts. Old paths untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Cut the pipeline over to the mode composer + drop the separate brief

Switch the writer agent to `build_mode_writer_prompt(mode)`, remove `persona` from `make_pipeline_agents`, delete the separate brief agent and `PipelineResult.brief`, and turn `persona_label` into a plain `label`. The public pipeline entry points keep a `persona` kwarg **as an ignored no-op** for now (removed in Task 4) so the CLI keeps working.

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py`
- Modify: `tests/test_pipeline.py`, `tests/test_pipeline_persona_wiring.py`, `tests/test_agent_skills.py`, `tests/test_signals.py`, `tests/test_morning.py`

**Interfaces:**
- Consumes: `build_mode_writer_prompt` (Task 1).
- Produces: `make_pipeline_agents(provider, thinking, mode=DEFAULT_MODE, *, explain_model=True)` (no `persona`); `PipelineAgents` without `brief`; `PipelineResult` without `brief`; `_render_capsule(..., label="", ...)`.

- [ ] **Step 1: Write the failing wiring test**

Replace the persona-parity tests in `tests/test_pipeline_persona_wiring.py` with mode-based ones. Add:

```python
def test_make_pipeline_agents_has_no_persona_param():
    import inspect
    from pitcher_narratives.pipeline import make_pipeline_agents
    assert "persona" not in inspect.signature(make_pipeline_agents).parameters


def test_writer_prompt_is_mode_composed():
    from pitcher_narratives.pipeline import make_pipeline_agents
    from pitcher_narratives.personas import REPORT, build_mode_writer_prompt
    agents = make_pipeline_agents("gemini", "high", REPORT)
    assert agents.writer._system_prompts == (build_mode_writer_prompt(REPORT),)


def test_pipeline_agents_has_no_brief():
    from pitcher_narratives.pipeline import make_pipeline_agents
    from pitcher_narratives.personas import REPORT
    agents = make_pipeline_agents("gemini", "high", REPORT)
    assert not hasattr(agents, "brief")
```

Delete the old `test_make_pipeline_agents_accepts_mode` default-`is REPORT` positional check, the `persona` parity tests, and the `signature has "persona"` assertions in this file.

Run: `uv run pytest tests/test_pipeline_persona_wiring.py::test_make_pipeline_agents_has_no_persona_param -v`
Expected: FAIL (`persona` still a parameter).

- [ ] **Step 2: Rewrite `make_pipeline_agents`**

In `pipeline.py:1563`, change the signature to drop `persona`:

```python
def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    mode: NarrationMode = DEFAULT_MODE,
    explain_model: bool = True,
) -> PipelineAgents:
```

At the writer wiring (1655) use the mode composer:

```python
        writer=_writer(build_mode_writer_prompt(mode, explain_model=explain_model)),
```

Delete the `brief=_brief(build_system_prompt(persona, BRIEF))` line (1670) and the `_brief` inner function (1639–1647). Remove `brief` from the `PipelineAgents` dataclass definition and from `mini_model_name`-adjacent construction. Update the top-of-file import (86–95) to drop `build_system_prompt`, `build_writer_system_prompt`, `get_persona`, `DEFAULT_PERSONA`, `BRIEF` **only if now unused** (they are still used by `_render_pipeline_data_sections` until Step 6 — keep whatever is still referenced; remove the rest). Add `build_mode_writer_prompt`, `DEFAULT_MODE` to the import.

- [ ] **Step 3: Remove the brief from `PipelineResult` and the summaries path**

Find `PipelineResult` (grep `class PipelineResult`) and remove its `brief` field. In `_run_summaries` (~2531) and its caller in `_run_pipeline` (~2529–2544), stop producing/threading `brief_text`: keep the executive-summary bullets, drop the brief agent call and the `brief_parity` value-parity block. `distill=True` now yields only `summary_bullets`.

- [ ] **Step 4: Turn `persona_label` into `label`**

In `_render_capsule` (2262) rename the param `persona_label: str = ""` → `label: str = ""` and update the three `log.warning` sites (2307, 2342, 2372) to use `label`. Update the two callers: `render_recap` (2459) `label="recap"`; `_run_pipeline` (2513) `label="report"` (report/changes share the report label — or pass `mode.id`; use `mode.id` for precision).

- [ ] **Step 5: Keep entry-point `persona` kwargs as ignored no-ops**

`_run_pipeline` (2476), `generate_pipeline_streaming` (2570), `run_narration_modes` (2607) keep their `persona: str = "scout"` parameter **but stop using it**: delete `persona_obj = get_persona(persona)` (2495) and pass `mode` (not `persona_obj`) into `make_pipeline_agents` (2496 → `make_pipeline_agents(provider, thinking, mode, explain_model=explain_model)`). Leave the `persona=` kwarg in the signature accepting-but-ignoring (a short-lived shim removed in Task 4). Add a one-line comment: `# persona kwarg retained as no-op until CLI de-persona (Task 4); single voice now`.

- [ ] **Step 6: Point the data-file dump at the mode composer**

In `_render_pipeline_data_sections` (1283) and `write_pipeline_data_file` (1380): keep the `persona` kwarg as an ignored no-op for now, but change the dumped system-prompt section (1342) to `build_mode_writer_prompt(DEFAULT_MODE)` and **delete** the brief system-prompt dump (1360, which referenced `BRIEF`).

- [ ] **Step 7: Fix the positional-arg call sites in tests**

Update these calls from `make_pipeline_agents(provider, thinking, persona_obj, mode)` (4 positional) to `make_pipeline_agents(provider, thinking, mode)` (3 positional):
- `tests/test_morning.py:482` → `make_pipeline_agents("gemini","medium", RECAP)` (drop `get_persona("scout")`).
- `tests/test_pipeline_persona_wiring.py:65-80` → `make_pipeline_agents("gemini","high", CHANGES)`.
Update `tests/test_pipeline.py`: delete `test_brief_uses_mini_model` (292–296) and any `PipelineResult.brief` assertions (the `r.brief == ""`/`len(r.brief) > 0` distillation checks at 530–556 become `summary`-based — assert `r.summary`/exec-bullets present for report, and that recap still skips distillation via `mode.distill`). `tests/test_agent_skills.py:81,89` `make_pipeline_agents()` no-arg still valid (writer stays in prose set). `tests/test_signals.py:206-212` change `build_writer_system_prompt(SCOUT)` → `build_mode_writer_prompt(REPORT)` and adjust imports.

- [ ] **Step 8: Run the affected tests**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_pipeline.py tests/test_pipeline_persona_wiring.py tests/test_agent_skills.py tests/test_signals.py tests/test_morning.py -q`
Expected: PASS.

- [ ] **Step 9: Run the full suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: no new failures beyond the known pre-existing 3. `test_personas.py` old fixture tests still pass (old `build_writer_system_prompt` untouched).

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor(pipeline): compose writer from mode; drop separate brief

make_pipeline_agents loses persona and composes the writer from
build_mode_writer_prompt(mode). Brief agent, PipelineResult.brief, and
the brief data-file dump removed. persona_label -> label. Entry-point
persona kwargs kept as short-lived no-ops.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Fold the hallucination allowlist to a single voice

Delete the persona-keyed `_PERSONA_KNOWN_METRICS`, fold the four analyst teaching terms into the base `_KNOWN_METRICS`, and drop `persona` from `check_hallucinated_metrics` and its CLI callers.

**Files:**
- Modify: the file holding `_KNOWN_METRICS`/`check_hallucinated_metrics` (confirm via grep — expected `src/pitcher_narratives/pipeline.py`)
- Modify: `src/pitcher_narratives/cli.py` (`build_diagnostics_dict`, `_emit_mode_result`)
- Modify: `tests/` hallucination tests + `tests/test_cli.py`

**Interfaces:**
- Produces: `check_hallucinated_metrics(report_text: str) -> HallucinationReport` (no `persona`); `build_diagnostics_dict(pipe_result) -> dict`; `_emit_mode_result(pipe_result, *, mode, verbose=False) -> tuple[bool, dict]`.

- [ ] **Step 1: Confirm location + write the failing test**

Run: `grep -n "_PERSONA_KNOWN_METRICS\|_KNOWN_METRICS =\|def check_hallucinated_metrics" src/pitcher_narratives/*.py`

Find the existing hallucination test file (`grep -rln "check_hallucinated_metrics" tests/`). Add a test asserting the analyst teaching terms are now globally allowed and persona is gone:

```python
def test_check_hallucinated_metrics_has_no_persona_param():
    import inspect
    from pitcher_narratives.pipeline import check_hallucinated_metrics
    assert "persona" not in inspect.signature(check_hallucinated_metrics).parameters


def test_teaching_terms_are_globally_allowlisted():
    from pitcher_narratives.pipeline import check_hallucinated_metrics
    report = "The playability improved; the tunneling gap tightened."
    hr = check_hallucinated_metrics(report)
    flagged = {m.lower() for m in hr.flagged_metrics} if hasattr(hr, "flagged_metrics") else set()
    assert "playability" not in flagged and "tunneling gap" not in flagged
```

(Adjust `hr` attribute access to the real `HallucinationReport` shape — inspect it first.)

Run: `uv run pytest <that_file>::test_check_hallucinated_metrics_has_no_persona_param -v`
Expected: FAIL.

- [ ] **Step 2: Fold the allowlist**

In the metrics-allowlist file: add the four terms to `_KNOWN_METRICS` (or the traditional-stats set that feeds `_is_known`):

```python
# Teaching vocabulary the single field-analyst voice may use (formerly the
# per-persona analyst allowlist).
_KNOWN_METRICS |= frozenset({"playability", "tunneling gap", "pitch tree", "arsenal depth"})
```

(If `_KNOWN_METRICS` is a frozenset literal, add the four terms into the literal instead of `|=`.) Delete `_PERSONA_KNOWN_METRICS` (2755). In `check_hallucinated_metrics` (2810) drop the `persona` param and the `persona_known` block (2849–2857); in `_is_known` (2860) drop `or metric in persona_known`.

- [ ] **Step 3: De-persona the CLI diagnostics**

In `cli.py`: `build_diagnostics_dict(pipe_result, persona)` → `build_diagnostics_dict(pipe_result)`; the call at 337 becomes `check_hallucinated_metrics(pipe_result.narrative)`. `_emit_mode_result(..., persona: str, mode, ...)` → drop `persona`; its call to `build_diagnostics_dict` (420) drops the arg. Update the caller at 653–654 to `_emit_mode_result(pipe_result, mode=mode, verbose=args.verbose)`. Remove the `log.info("persona=%s", args.persona)` line (563).

- [ ] **Step 4: Update coupled tests**

In `tests/test_cli.py` update any `build_diagnostics_dict(..., persona=...)`/`_emit_mode_result(..., persona=...)` calls to drop the arg (grep the file). The scoreboard `--format` tests are unrelated — leave them.

- [ ] **Step 5: Run affected + full suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py <hallucination_test_file> -q`
Expected: PASS.
Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(grounding): single hallucination allowlist, drop persona

Fold the analyst teaching terms into _KNOWN_METRICS, delete
_PERSONA_KNOWN_METRICS, and remove persona from check_hallucinated_metrics
and the CLI diagnostics helpers.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Remove persona threading, CLI flags, and morning/bench persona

Strip the now-unused `persona` kwargs from the pipeline entry points and remove the CLI `--persona`/`--list-personas` flags, `_print_personas`, the `morning --persona` flag, `run_morning`'s `persona_id`, and bench persona.

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (entry-point signatures, data-file kwargs)
- Modify: `src/pitcher_narratives/cli.py` (report + morning parsers, `_run_report_command`, `_print_personas`)
- Modify: `src/pitcher_narratives/morning.py`
- Modify: `bench/runner.py`, `bench/__main__.py`
- Modify: `tests/test_cli.py`, `tests/test_morning.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: `generate_pipeline_streaming(ctx, *, provider, thinking, mode=DEFAULT_MODE, explain_model=True, _model_override=None, prior_ctx=None)` and `run_narration_modes(...)` — both without `persona`; `write_pipeline_data_file(ctx, pitcher_id, provider, *, prior_ctx=None)`; `run_morning(...)` without `persona_id`.

- [ ] **Step 1: Write the failing signature test**

In `tests/test_pipeline_persona_wiring.py` add:

```python
def test_entry_points_have_no_persona():
    import inspect
    from pitcher_narratives.pipeline import (
        generate_pipeline_streaming, run_narration_modes, write_pipeline_data_file,
    )
    for fn in (generate_pipeline_streaming, run_narration_modes, write_pipeline_data_file):
        assert "persona" not in inspect.signature(fn).parameters, fn.__name__
```

Run: `uv run pytest tests/test_pipeline_persona_wiring.py::test_entry_points_have_no_persona -v`
Expected: FAIL.

- [ ] **Step 2: Strip persona from the pipeline entry points**

Remove `persona` from `_run_pipeline` (2481), `generate_pipeline_streaming` (2575), `run_narration_modes` (2613), `_render_pipeline_data_sections` (1286/1385), and `write_pipeline_data_file`. Remove their pass-through forwarding. Delete the now-dead docstring `persona:` lines. `_run_pipeline` passes `label=mode.id` into `_render_capsule` (already done in Task 2).

- [ ] **Step 3: De-persona the CLI report path**

In `cli.py`: remove the `--persona` (81–86) and `--list-personas` (88–90) arguments from the `report` parser; delete `_print_personas` (260–273) and the `if args.list_personas:` short-circuit (525–529). Remove the `PERSONAS` import (18) — keep `REPORT`, `get_narration_mode`. Update the report calls: `write_pipeline_data_file(ctx, args.pitcher, args.provider, prior_ctx=prior_ctx)` (608, no persona); `run_narration_modes(ctx, modes=[mode], provider=..., thinking=..., explain_model=..., _model_override=..., prior_ctx=...)` (638, no persona).

- [ ] **Step 4: De-persona the morning command**

In `cli.py`: remove `--persona` from the `morning` parser (160–166). In `morning.py`: remove `persona_id` from `run_morning` (80–86); delete `persona = PERSONAS[persona_id]` (101); change `make_pipeline_agents(provider, "medium", persona, RECAP)` (134) → `make_pipeline_agents(provider, "medium", RECAP)`. Remove the `PERSONAS` import. Update `_run_morning_command` to stop passing `persona_id`.

- [ ] **Step 5: De-persona bench**

In `bench/runner.py`: remove `persona` from `run_provider` (72) and its `run_narration_modes` forward (113). In `bench/__main__.py`: remove the `--persona` arg (53), the forwards (121/134), and the `"persona"` results field (193).

- [ ] **Step 6: Update tests**

`tests/test_cli.py`: remove `--list-personas`/`--persona` coverage for `report` and `morning`; remove any `_print_personas` test; add a smoke test that `report` runs with no `--persona`. `tests/test_morning.py`: drop `persona_id=`/`persona=` from `run_morning` calls. `tests/test_pipeline.py`: drop `persona=` from `generate_pipeline_streaming`/`run_narration_modes` calls (the `_fake_stream(**_kw)` monkeypatch already tolerates removed kwargs).

- [ ] **Step 7: Run affected + full suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py tests/test_morning.py tests/test_pipeline.py tests/test_pipeline_persona_wiring.py -q`
Expected: PASS.
Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: no new failures. (Old `test_personas.py` fixture tests still pass — deleted next task.)

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove persona threading, CLI flags, morning/bench persona

Strip the no-op persona kwargs from the pipeline entry points; remove
--persona/--list-personas (report) and --persona (morning); drop
run_morning persona_id and bench persona.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Delete the dead voice machinery

Remove everything the single voice made obsolete and rename the composer to its final name.

**Files:**
- Modify: `src/pitcher_narratives/personas.py`
- Modify: `src/pitcher_narratives/pipeline.py` (final import cleanup), `curator.py` (comment), `src/pitcher_narratives/skills/derived-signal-feature/SKILL.md`
- Modify/Delete: `tests/test_personas.py`; delete 6 old fixtures
- Rename: `build_mode_writer_prompt` → `build_writer_system_prompt`

**Interfaces:**
- Produces: final `build_writer_system_prompt(mode: NarrationMode, *, explain_model=True) -> str`. `personas.py` exports: `WRITER_VOICE`, `SHARED_WRITER_BASE`, `NarrationMode`, `ValidationPolicy`, `NARRATION_MODES`, `REPORT`, `RECAP`, `CHANGES`, `DEFAULT_MODE`, `get_narration_mode`, `build_writer_system_prompt`.

- [ ] **Step 1: Delete the dead symbols from `personas.py`**

Remove: the `Persona` dataclass; `OutputContract` dataclass; all `_SCOUT_OVERLAY`/`_ANALYST_OVERLAY`/`_GENERIC_OVERLAY` + their `_*_EXPLAIN_THE_MODEL_ADDENDUM`; `SCOUT`/`ANALYST`/`GENERIC`; `_PERSONAS_INTERNAL`/`PERSONAS`/`DEFAULT_PERSONA`/`get_persona`; the invariant loop over personas; the `OutputContract` constants `BRIEF`/`RECAP_BRIEF`/`SCOUT_REPORT`/`NEWSLETTER`/`SECTIONED`/`CHANGES_SCOUT`/`CHANGES_ANALYST`/`CHANGES_GENERIC`; the `_CAPSULE_STRUCTURE`/`_NEWSLETTER_STRUCTURE`/`_SECTIONED_STRUCTURE`/`_BRIEF_STRUCTURE`/`_RECAP_STRUCTURE`/`_CHANGES_*_STRUCTURE`/`_BRIEF_FRAMING_FROM_REPORT`/`_CHANGES_ANCHOR_GUIDANCE` constants that are now unused (keep `_CHANGES_MANDATE` — it feeds `_CHANGES_FRAMING`; keep `_SYNTHESIS_RULES`/`_SYNTHESIS_FRAMING`/`_EXPLAIN_THE_MODEL`); the old `build_system_prompt` and old `build_writer_system_prompt`. Remove the `contracts` field and its `__post_init__` `MappingProxyType` handling from `NarrationMode`, and drop `contracts=` from `REPORT`/`RECAP`/`CHANGES`. Rewrite `__all__` to the final export list above.

> Keep `anchor_guidance` on `CHANGES`: it still feeds `pipeline.py:1661`. `_CHANGES_ANCHOR_GUIDANCE` text stays if still referenced there — verify with grep before deleting it.

- [ ] **Step 2: Port the length-target validation**

Add to `NarrationMode.__post_init__` (so the deleted `OutputContract` validation isn't lost):

```python
        lo, hi = self.length_target
        if lo <= 0 or hi <= 0 or lo > hi:
            raise ValueError(
                f"NarrationMode {self.id!r} length_target must be positive and "
                f"min<=max, got {self.length_target}"
            )
```

- [ ] **Step 3: Rename the composer**

Rename `build_mode_writer_prompt` → `build_writer_system_prompt` in `personas.py`. Update references in `pipeline.py` (writer wiring, data-file dump) and `tests/test_single_voice.py`. Update `__all__`.

- [ ] **Step 4: Rewrite `test_personas.py`**

Delete every test coupled to the removed symbols (per the WS3 inventory): the `OutputContract` rejection tests (67–86 → moved to `test_single_voice.py` as `NarrationMode` length validation), the `REPORT.contracts[...] is ...` identity tests (117–144, 364, 500, 646, 905–906, 1040–1050, 1142), the 9 persona×mode byte-identical fixture tests (172–216, 323–352, 997–1116), the persona-overlay/registry tests (219–290, 358–552, 893–930), the BRIEF framing tests (558–646), and the `build_system_prompt(..., explain_model=...)` tests (1149–1179 → re-express against `build_writer_system_prompt(REPORT, explain_model=False)` in `test_single_voice.py`). Keep and adapt: `get_narration_mode` valid/invalid tests, `NARRATION_MODES` registry-key invariant, `NarrationMode.title` default (1140–1143 → construct without `contracts`), `RECAP.distill is False`/`REPORT.distill is True`, the mode `validation`/`temporal_frame`/`anchor_guidance` tests. Move any still-relevant length-validation assertion into `test_single_voice.py`.

- [ ] **Step 5: Delete the 6 old fixtures + fold voice-golden**

```bash
git rm tests/fixtures/writer_prompt_scout.txt tests/fixtures/writer_prompt_analyst.txt tests/fixtures/writer_prompt_generic.txt tests/fixtures/recap_writer_prompt_scout.txt tests/fixtures/recap_writer_prompt_analyst.txt tests/fixtures/recap_writer_prompt_generic.txt tests/fixtures/changes_writer_prompt_scout.txt tests/fixtures/changes_writer_prompt_analyst.txt tests/fixtures/changes_writer_prompt_generic.txt
```

Rewrite `tests/test_voice_golden.py`: drop the per-persona parametrization; keep the universal-directive manifest but assert it against `build_writer_system_prompt(REPORT)` (single voice), and assert the per-mode structure phrases against the three modes. (Overlaps `test_single_voice.py`; consolidate — prefer deleting `test_voice_golden.py` and folding its unique manifest markers into `test_single_voice.py`.)

- [ ] **Step 6: Clean up stray references**

Run: `grep -rn "get_persona\|PERSONAS\|OutputContract\|SCOUT_REPORT\|build_system_prompt\|\.contracts\b\|persona" src/ tests/ bench/`
Fix every remaining hit: update `curator.py:106` comment; update `SKILL.md:17` (regenerate `tests/fixtures/writer_prompt_*.txt` via `build_writer_system_prompt`, single voice). No runtime reference to a deleted symbol may remain.

- [ ] **Step 7: Run the full suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: PASS (only the 3 known pre-existing failures, if still present, remain).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(personas): delete dead voice machinery

Remove Persona/registry/OutputContract and the 8 contract constants,
the per-persona overlays, and the old composers. Rename
build_mode_writer_prompt -> build_writer_system_prompt. Delete the 6
obsolete persona fixtures; port length validation to NarrationMode.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Verify morning + refresh docs

Confirm the morning command emits a per-pitcher morning capsule off the shared spine (spec §4/§8 phase 4), and update user-facing docs for the single voice and removed flags.

**Files:**
- Modify: `tests/test_morning.py`
- Modify: `README.md` (and any `docs/*.md` referencing `--persona`/voices/brief)

- [ ] **Step 1: Write the morning end-to-end verification test**

In `tests/test_morning.py` add (using `TestModel`, mirroring existing morning smoke tests — copy the fixture/setup pattern already in that file):

```python
def test_morning_emits_recap_capsule_per_selected_pitcher(monkeypatch):
    """Morning runs the shared spine and yields a recap-shaped capsule per pick."""
    from pitcher_narratives.personas import RECAP
    # Arrange: stub selection to a known small set; run_morning with a TestModel.
    # Assert: one PipelineResult per selected pitcher; each ran RECAP mode
    # (r.mode_id == "recap" or distill skipped -> no exec bullets); narrative non-empty.
    ...  # fill from the existing morning smoke-test harness in this file
```

Replace the `...` with the concrete arrangement used by the nearest existing morning test (same data fixture, same `TestModel(call_tools=[])`, same selection stub). Assert: number of results == number of selected pitchers; each result's narrative is non-empty; recap distillation was skipped.

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py::test_morning_emits_recap_capsule_per_selected_pitcher -v`
Expected: PASS (morning already wires this; the test documents/guards it).

- [ ] **Step 2: Update the docs**

In `README.md` and any doc that mentions personas/voices/`--persona`/the brief: remove the `--persona`/`--list-personas` references; describe the single voice and the three deliverables (scouting report = bullets + prose; changes = bullets + prose; morning = capsule). Remove any "brief" output description. Grep to be sure: `grep -rn "persona\|--format\b\| brief\b" README.md docs/*.md`.

- [ ] **Step 3: Run the full suite one last time**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(morning): guard per-pitcher recap capsule; docs: single voice

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §2 one voice → Task 1 (`WRITER_VOICE`), Task 5 (delete others). ✓
- §2 three deliverables/one spine → mode-owned structure (Task 1); spine untouched. ✓
- §2 structure binds to mode → Task 1 fields + Task 2 composer cutover. ✓
- §2/§4.1 model-focused report/changes → `_REPORT_FRAMING`/`_CHANGES_FRAMING` carry `EXPLAIN THE MODEL`; recap bare (Task 1, tested). ✓
- §4 lengths 350–600 / 250–450 / 60–120 → Task 1 structures + `length_target`. ✓
- §5.3 drop separate brief → Task 2. ✓
- §5.4 remove `--persona`/`--list-personas`; keep `--mode` → Task 4. ✓
- §6 deletions → Task 5. ✓
- §7 full re-baseline (3 fixtures, rewrite coupled tests) → Tasks 1/2/5. ✓
- §8 phase 4 morning wiring → already satisfied; guarded in Task 6. ✓
- §9 model breakdown = future → not built (correct). ✓

**Placeholder scan:** Task 6 Step 1 leaves the test body to fill from the file's existing harness — flagged explicitly with what to assert; not a silent TBD. All source changes carry full code.

**Type consistency:** `build_mode_writer_prompt` (Tasks 1–4) → renamed to `build_writer_system_prompt` (Task 5) consistently; `make_pipeline_agents(provider, thinking, mode, ...)` used identically in Tasks 2/4 tests; `label` param name consistent across `_render_capsule` callers.
