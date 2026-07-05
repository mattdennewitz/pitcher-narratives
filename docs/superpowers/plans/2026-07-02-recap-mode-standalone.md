# RECAP Mode + Standalone Selectability (Phase 8A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add RECAP as a first-class `NarrationMode` — an executive-brief writer contract that rides the existing spine+writer+validation pipeline and is selectable via `report --mode recap` — without changing the `report` path's own output.

**Architecture:** RECAP is `NarrationMode(id="recap")` whose per-persona contract is a new short-exec-brief `OutputContract` (`RECAP_BRIEF`) using the existing `_SYNTHESIS_FRAMING` (write from the analyses) with a new brief-shaped structure. The pipeline writer already writes from the shared `AnalyzedContext` via `build_writer_input`, so a mode only needs its writer contract + validation depths to work end-to-end through `_run_pipeline` — no pipeline branching required. RECAP carries `ValidationPolicy(anchor_depth=1, fact_depth=2)` per design §7. `--mode recap` and `--mode report,recap` already resolve through the Phase-7 `_resolve_modes`/`run_narration_modes`/aggregate-exit plumbing; this phase just registers the mode and proves it renders a validated brief.

**Tech Stack:** Python 3.14, polars, pydantic-ai, pytest. No new dependencies.

## Global Constraints

- Python 3.14+; run everything via `uv run` against the project `.venv`.
- **Data/CLI tests need `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives`** (worktree lacks the gitignored data). CLI integration tests are subprocess-based and set `PITCHER_NARRATIVES_TEST_MODEL=1` via `_test_env(...)` already in test_cli.py.
- One pre-existing unrelated suite failure is expected: `test_to_prompt_token_budget` (Phase-4 vintage). Any other failure is real.
- `snake_case` functions/modules, `PascalCase` types, `UPPER_SNAKE_CASE` constants; Google-style docstrings; type hints on signatures.
- Frozen dataclasses (`OutputContract`, `NarrationMode`) for structured config, not dicts.
- **`report` (no `--mode`, i.e. default REPORT) output and exit MUST stay byte-identical.** RECAP is purely additive: a new registry entry + a new contract. Do not touch REPORT, BRIEF, SCOUT_REPORT, `_run_pipeline`, or the `# Brief` section. If a `report`-path golden changes, something is wrong — stop.
- **Out of scope (deferred, do NOT build):** the render/spine-once extraction and typed `recap(analyzed, pick)` morning overlay (Phase 8B); retiring `build_story_cue`/`DIGEST_ITEM`/`_CUE_FRAMING` and the `test_fact_parity` rewrite (8B); morning residual marking (8B); per-mode stdout headers G9 (recap will stream under the existing `# Scouting Report` header — accepted for now, note it); `--recap-anchor-depth`/`--recap-fact-depth` CLI knobs (8B, morning passes the digest default). `--mode changes` stays unregistered (Phase 9).
- SDD ledger: append to `.superpowers/sdd/progress.md` under "## Phase 8A". Commit the plan first (`docs(plan): ...`), then one commit per task.
- Work only in this worktree; never `cd` to the data dir. Set `PITCHER_NARRATIVES_DATA_DIR` inline per command.

---

## File Structure

- `src/pitcher_narratives/personas.py` — **primary change site.** Add `_RECAP_STRUCTURE` constant; `RECAP_BRIEF` OutputContract; `RECAP` NarrationMode; register in `_NARRATION_MODES_INTERNAL`; extend `__all__` (Task 1).
- `src/pitcher_narratives/cli.py` — update the `--mode` help text so `recap` is documented as available (Task 2). `_resolve_modes` needs no change (it resolves via `get_narration_mode`).
- `tests/` — `test_personas.py` (contract + mode + registry + prompt-composition), `test_cli.py` (end-to-end `--mode recap` subprocess run), `tests/fixtures/recap_writer_prompt_{scout,analyst,generic}.txt` (new per-persona goldens).
- `.superpowers/sdd/progress.md` — Phase-8A ledger (Task 3).

**Explicitly NOT touched:** `morning.py`, `digest.py`, `curator.py`, `pipeline.py` (RECAP rides the existing `_run_pipeline` unchanged), and everything under REPORT/BRIEF.

---

## Task 1: RECAP contract + NarrationMode + registry

**Files:**
- Modify: `src/pitcher_narratives/personas.py` — add `_RECAP_STRUCTURE` (near `_BRIEF_STRUCTURE:309`), `RECAP_BRIEF` (near `BRIEF:327`), `RECAP` NarrationMode + registry entry (near `REPORT:405`, `_NARRATION_MODES_INTERNAL:417`), and `__all__` (`:32-54`).
- Test: `tests/test_personas.py`

**Interfaces:**
- Consumes: `OutputContract` (personas.py:74-98, fields `id`, `length_target`, `structure`, `input_framing`), `_SYNTHESIS_FRAMING` (personas.py:132), `NarrationMode`/`ValidationPolicy` (Phase 7).
- Produces:
  - `RECAP_BRIEF: OutputContract` — `id="recap"`, `length_target=(40, 90)`, `structure=_RECAP_STRUCTURE`, `input_framing=_SYNTHESIS_FRAMING`.
  - `RECAP: NarrationMode` — `id="recap"`, `contracts={"scout": RECAP_BRIEF, "analyst": RECAP_BRIEF, "generic": RECAP_BRIEF}`, `validation=ValidationPolicy(anchor_depth=1, fact_depth=2)`.
  - `NARRATION_MODES` now has keys `{"report", "recap"}`; `get_narration_mode("recap")` returns `RECAP`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_personas.py`:

```python
def test_recap_mode_registered_and_resolvable():
    from pitcher_narratives.personas import (
        NARRATION_MODES,
        RECAP,
        get_narration_mode,
    )

    assert set(NARRATION_MODES) == {"report", "recap"}
    assert get_narration_mode("recap") is RECAP
    assert RECAP.id == "recap"


def test_recap_validation_depths():
    """RECAP caps anchor at 1, keeps fact at 2 (design §7)."""
    from pitcher_narratives.personas import RECAP

    assert (RECAP.validation.anchor_depth, RECAP.validation.fact_depth) == (1, 2)


def test_recap_contract_shape_and_all_personas_mapped():
    from pitcher_narratives.personas import RECAP, RECAP_BRIEF
    from pitcher_narratives.personas import _SYNTHESIS_FRAMING

    assert RECAP_BRIEF.id == "recap"
    assert RECAP_BRIEF.length_target == (40, 90)
    # RECAP writes FROM the analyses (synthesis framing), not by distilling a
    # finished report — that is what lets it render off the shared spine.
    assert RECAP_BRIEF.input_framing is _SYNTHESIS_FRAMING
    # Every persona is mapped, so build_writer_system_prompt never falls back.
    assert set(RECAP.contracts) == {"scout", "analyst", "generic"}
    assert all(c is RECAP_BRIEF for c in RECAP.contracts.values())


def test_recap_writer_prompt_uses_brief_structure_not_report_structure():
    """The composed RECAP writer prompt must carry the brief structure and the
    synthesis framing — proving the mode selects the recap contract, not the
    report capsule structure."""
    from pitcher_narratives.personas import (
        PERSONAS,
        RECAP,
        REPORT,
        build_writer_system_prompt,
    )

    recap_prompt = build_writer_system_prompt(PERSONAS["scout"], RECAP)
    report_prompt = build_writer_system_prompt(PERSONAS["scout"], REPORT)
    # A distinctive phrase from _RECAP_STRUCTURE appears only in recap.
    assert "executive brief" in recap_prompt.lower()
    assert recap_prompt != report_prompt
```

**Note for implementer:** `PERSONAS` is the persona registry (personas.py `__all__`). If its access pattern differs (e.g. a `get_persona`/attribute), mirror how existing `test_personas.py` tests obtain a persona — grep `build_writer_system_prompt(` in that file. The `"executive brief"` phrase must actually appear in `_RECAP_STRUCTURE` you author in Step 3 — keep them in sync.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_personas.py -k recap -v`
Expected: FAIL — `ImportError: cannot import name 'RECAP'`.

- [ ] **Step 3: Add the structure, contract, mode, registry, exports**

In `src/pitcher_narratives/personas.py`:

Add `_RECAP_STRUCTURE` next to `_BRIEF_STRUCTURE` (~line 309). Author it as the brief-shaped output directive, written to be sourced from the analyses (read `_BRIEF_STRUCTURE` first and match its tone/format):

```python
_RECAP_STRUCTURE = """\
Write a tight executive brief — 2 to 4 sentences, one continuous thread, no \
headings or bullets.

- Lead with the single most important recent development for this pitcher \
  (the biggest change, adaptation, or execution trend in the analyses).
- Support it with at most one or two grounding metrics drawn straight from \
  the analyses. Do not invent numbers or reach for a second storyline.
- Close on what it means going forward. Keep it scannable and quotable.

This is a recap, not a full scouting report: depth is traded for a single \
clear takeaway. Target 40-90 words; never exceed 4 sentences."""
```

Add `RECAP_BRIEF` next to `BRIEF` (~line 327):

```python
# RECAP: an executive-brief writer contract. Same grounded synthesis framing
# as the scouting report (writes FROM the analyses), but a brief-shaped
# structure. Voice still comes from the persona overlay, so one contract
# serves all personas.
RECAP_BRIEF = OutputContract(
    id="recap",
    length_target=(40, 90),
    structure=_RECAP_STRUCTURE,
    input_framing=_SYNTHESIS_FRAMING,
)
```

Add the `RECAP` NarrationMode next to `REPORT` (~line 405) and register it:

```python
# RECAP reproduces the executive-brief path as a first-class mode. It caps the
# anchor loop at 1 (short brief, less to drift) and keeps the fact loop at 2
# (design §7). Standalone via `report --mode recap`; morning adopts it in 8B.
RECAP = NarrationMode(
    id="recap",
    contracts={
        "scout": RECAP_BRIEF,
        "analyst": RECAP_BRIEF,
        "generic": RECAP_BRIEF,
    },
    validation=ValidationPolicy(anchor_depth=1, fact_depth=2),
)
```

Change the registry line (currently `_NARRATION_MODES_INTERNAL: dict[str, NarrationMode] = {"report": REPORT}`, ~line 417) to:

```python
_NARRATION_MODES_INTERNAL: dict[str, NarrationMode] = {"report": REPORT, "recap": RECAP}
```

The existing import-time `key == mode.id` invariant loop (~419-425) now also validates RECAP — no change needed.

Add `"RECAP"` and `"RECAP_BRIEF"` to `__all__` (~line 32-54), keeping alphabetization within the existing grouping (they sort near `REPORT`/`SCOUT`).

- [ ] **Step 4: Run the recap tests**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_personas.py -k recap -v
```
Expected: PASS (4 tests).

- [ ] **Step 5: Fix any registry-shape assumption elsewhere in the suite**

Some existing tests may assert `NARRATION_MODES` contains only `"report"`, or that `get_narration_mode` rejects `"recap"`. Find and update them to the new reality (recap is now valid):

```bash
rg -n '"report"|get_narration_mode|NARRATION_MODES|only .report.|recap' tests/test_personas.py tests/test_cli.py
```
Recompute any such assertion to include `recap` (do not weaken — assert the exact new set `{"report", "recap"}`). Then run the full personas + cli mode-resolution tests:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_personas.py tests/test_cli.py -q
```
Expected: PASS (aside from any unrelated pre-existing failure — there are none in these two files).

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/personas.py tests/test_personas.py tests/test_cli.py
git commit -m "feat(narration): register RECAP mode + RECAP_BRIEF contract (P8A)"
```

---

## Task 2: CLI selectability + end-to-end validated recap + goldens

**Files:**
- Modify: `src/pitcher_narratives/cli.py` — `--mode` help text (~lines 81-88) so `recap` reads as available.
- Test: `tests/test_cli.py`; new goldens `tests/fixtures/recap_writer_prompt_{scout,analyst,generic}.txt`.

**Interfaces:**
- Consumes: `RECAP` (Task 1); the Phase-7 `_resolve_modes` (cli.py:132-154, already resolves any registered id), `run_narration_modes`, and the aggregate-exit report command.
- Produces: `report --mode recap` runs end-to-end and emits a validated brief; `report --mode report,recap` runs both modes.

- [ ] **Step 1: Update the `--mode` help text**

In `src/pitcher_narratives/cli.py` (~lines 81-88), the `--mode` argument help/comment currently says only `report` is available (`changes`/`recap` land later). Edit the help string and any adjacent comment so `recap` is listed as available and only `changes` remains pending. Do not change the flag's parsing or `_resolve_modes` — those already handle any registered id. Keep the help concise (e.g. `"Comma-separated narration modes: report, recap (default: report). changes lands in a later phase."`).

- [ ] **Step 2: Write the failing end-to-end test**

Add to `tests/test_cli.py`, mirroring the existing subprocess pattern (`_test_env(...)`, `PITCHER_NARRATIVES_TEST_MODEL="1"`, pitcher `592155`; grep `test_cli_unverified_banner_on_residual_flags` for the exact shape):

```python
def test_cli_recap_mode_runs_and_produces_output():
    """`report --mode recap` renders a recap through the full validation stack
    and exits cleanly under TestModel."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "recap"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # The recap mode still emits the executive-summary section (shared emitter)
    # and produced a non-empty narrative body.
    assert len(result.stdout.strip()) > 0
    assert "# Executive Summary" in result.stdout


def test_cli_report_and_recap_both_run():
    """`--mode report,recap` runs both modes; the process completes."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "report,recap"],
        capture_output=True,
        text=True,
        timeout=90,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout.strip()) > 0
```

- [ ] **Step 3: Run the end-to-end tests**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_cli.py -k "recap" -v
```
Expected: PASS. (After Task 1, `recap` is registered and resolvable; the Phase-7 command loop renders it. If it fails on mode resolution, Task 1 is incomplete.) If it fails only because the streamed header reads `# Scouting Report` for a recap — that is the deferred G9 issue; do NOT assert on that header, and do not fix it here.

- [ ] **Step 4: Add the per-persona recap writer-prompt goldens**

Add a parametrized golden test + a content-signature guard (the guard keeps the golden from being a tautology) to `tests/test_personas.py`:

```python
import pathlib

import pytest

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
def test_recap_writer_prompt_golden(persona_id):
    from pitcher_narratives.personas import PERSONAS, RECAP, build_writer_system_prompt

    prompt = build_writer_system_prompt(PERSONAS[persona_id], RECAP)
    golden = (_FIXTURES / f"recap_writer_prompt_{persona_id}.txt").read_text()
    assert prompt == golden
    # Anti-tautology guard: the golden must actually be recap-shaped.
    assert "executive brief" in prompt.lower()
```

Generate the three fixtures from the real composed prompts and commit them. One way:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run python -c "
from pitcher_narratives.personas import PERSONAS, RECAP, build_writer_system_prompt
import pathlib
d = pathlib.Path('tests/fixtures')
for pid in ('scout','analyst','generic'):
    (d / f'recap_writer_prompt_{pid}.txt').write_text(build_writer_system_prompt(PERSONAS[pid], RECAP))
"
```
Then eyeball each fixture: it must read like an executive-brief writer prompt (synthesis framing + `_RECAP_STRUCTURE` + the persona's voice overlay), NOT the full scouting-report capsule structure. If it looks wrong, the contract wiring in Task 1 is wrong — fix there, do not hand-edit the fixture.

- [ ] **Step 5: Run the golden + full persona/cli tests**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_personas.py tests/test_cli.py -q
```
Expected: PASS. Confirm the REPORT-path guard tests (`test_cli_narrative_output_has_required_sections`, `test_cli_unverified_banner_on_residual_flags`) are still green — proving `report` (no `--mode`) is unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py tests/test_personas.py tests/fixtures/recap_writer_prompt_scout.txt tests/fixtures/recap_writer_prompt_analyst.txt tests/fixtures/recap_writer_prompt_generic.txt
git commit -m "feat(cli): report --mode recap end-to-end + per-persona goldens (P8A)"
```

---

## Task 3: Phase-8A wrap-up — full-suite gate + ledger

**Files:**
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: Run the full suite**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q
```
Expected: all pass except the documented `test_to_prompt_token_budget`. Any other failure is a real regression — fix before proceeding.

- [ ] **Step 2: Confirm `report` behavior is unchanged**

```bash
git diff --stat <PLAN_COMMIT>..HEAD -- tests/
```
Expected: test changes are ADDITIONS (new recap tests + fixtures) — no edits to REPORT-path golden literals except a possible registry-set assertion widened to `{"report","recap"}` (Task 1 Step 5). Confirm no `report`/BRIEF/pipeline source file changed:
```bash
git diff --stat <PLAN_COMMIT>..HEAD -- src/
```
Expected: only `personas.py` and `cli.py` (help text) changed. `pipeline.py`, `morning.py`, `digest.py` untouched.

- [ ] **Step 3: Update the ledger**

Append a `## Phase 8A: RECAP mode + standalone` section to `.superpowers/sdd/progress.md`: plan path, base commit, the 2 task commit SHAs, note that `report` stayed byte-identical and RECAP rides the existing `_run_pipeline` (no pipeline branch), the RECAP validation depths (1/2), and the seams deferred to 8B (render/spine-once extraction, typed `recap(analyzed, pick)` overlay, retire cue/DIGEST_ITEM, rewrite test_fact_parity, morning residual marking, G9 headers, recap-depth CLI knobs).

- [ ] **Step 4: Commit**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(sdd): Phase 8A recap-mode wrap-up"
```

---

## Self-Review (spec coverage)

- **§6 recap = executive brief, one thread, evolved from BRIEF** → Task 1 (`RECAP_BRIEF` with `_RECAP_STRUCTURE` + synthesis framing). ✓
- **§7 RECAP validation depths anchor 1 / fact 2** → Task 1 (`ValidationPolicy(anchor_depth=1, fact_depth=2)`), asserted in `test_recap_validation_depths`. ✓
- **§10 `report` subcommand gains `--mode … recap`** → Task 2 (help text + end-to-end; `_resolve_modes` already supported it post-Phase 7). ✓
- **§11 mode id `recap`; contract name distinct from mode** → Task 1 (mode `RECAP`, contract `RECAP_BRIEF`, id `"recap"`; no collision with the `RECAP` mode symbol). ✓
- **§12 "new golden tests per mode"** → Task 2 (per-persona recap writer-prompt goldens + anti-tautology guard). ✓
- **`report` byte-identical (behavior-preserving for the default path)** → Global Constraint + Task 3 Step 2 (no pipeline/BRIEF/REPORT edits; only additive registry + contract). ✓
- **Deferred correctly (8B / 9):** render-extraction + spine-once, typed `recap(analyzed, pick)` overlay, retire `build_story_cue`/`DIGEST_ITEM`/`_CUE_FRAMING`, `test_fact_parity` rewrite, morning residual marking, G9 per-mode headers, `--recap-*-depth` knobs, `--mode changes`. Listed in Global Constraints. ✓
- **Placeholder scan:** the only implementer-judgment points are the persona-access pattern (Task 1 note points at existing tests) and the golden bytes (generated + eyeballed, with a content-signature guard) — no unspecified logic. ✓
- **Type consistency:** `RECAP_BRIEF: OutputContract` and `RECAP: NarrationMode` names used identically across Task 1 (definition), Task 1 tests, and Task 2 goldens; `build_writer_system_prompt(persona, mode)` signature matches the mapped Phase-7 usage. ✓
