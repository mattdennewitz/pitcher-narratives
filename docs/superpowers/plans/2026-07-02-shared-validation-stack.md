# Shared Validation Stack (Phase 7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the anchor + capsule-audit validation loops as a reusable, per-mode-tunable stack; carry the revision-depth knobs on `NarrationMode`; extract a LOUD residual-surfacing API; and replace the report command's first-mode-only, first-failure exit with an aggregate multi-mode policy — all while REPORT stays byte-for-byte behavior-identical.

**Architecture:** The two revision loops (`_run_anchor_revision_loop`, `_run_capsule_audit`) and the helper `_build_capsule_audit_input` are already dependency-injected (agents + depths passed in). Phase 7 does four things: (1) **publish** them (drop the leading underscore, add to `__all__`) so phases 8/9 can reuse them without importing privates; (2) add a `ValidationPolicy(anchor_depth, fact_depth)` member to `NarrationMode`, source REPORT's depths from the existing `config.MAX_REVISIONS`/`MAX_FACT_REVISIONS`, and thread `mode.validation` into `_run_pipeline` so the loop calls read per-mode depths (REPORT = 5/2, unchanged); (3) add pure `is_unverified(result)` + `residual_banner(result, *, label)` primitives to `pipeline.py`; (4) refactor the report command so it iterates **all** selected modes, ORs their unverified status, and exits non-zero once at the end instead of aborting on the first. Because only the `report` mode is registered today and REPORT's depths equal the current constants, every change is output-neutral now; the machinery is what phases 8 (RECAP) and 9 (CHANGES) plug into.

**Tech Stack:** Python 3.14, polars, pydantic-ai, pytest. No new dependencies.

## Global Constraints

- Python 3.14+; run everything via `uv run` against the project `.venv`.
- **Data-dependent tests need `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives`** (this worktree lacks the gitignored `var/` data). Prefix every data-touching `uv run pytest` invocation with it. Without it ~25 tests fail "Pitcher not found" (environmental, not real).
- One pre-existing suite failure is expected and unrelated: `test_to_prompt_token_budget` (Phase-4 vintage, `2063 > 2000`). Any *other* failure is real.
- `snake_case` functions/modules, `PascalCase` types/Pydantic models, `UPPER_SNAKE_CASE` constants; Google-style docstrings; type hints on every signature.
- Pydantic models / frozen dataclasses for structured data, not dicts.
- Absolute imports for project modules. `config.py` is already imported at `cli.py:17` top-level, so `personas.py → config` (Task 2) adds **no** `--help` latency and introduces no import cycle (config imports only stdlib + logfire + pydantic_ai; it does not import personas).
- **Behavior-preserving phase.** REPORT single-mode CLI output and exit code must stay byte-identical. This phase moves **no** goldens. If a golden/characterization assertion changes, something is wrong — stop and reconcile, do not "recalibrate."
- SDD ledger: append progress to `.superpowers/sdd/progress.md` under a new "## Phase 7" section. Commit the plan first (`docs(plan): ...`), then one commit per task.
- Guardrail (per Phase-4 incident): implementers work **only** in this worktree; never `cd` into the data dir. Set `PITCHER_NARRATIVES_DATA_DIR` inline per command.

---

## File Structure

- `src/pitcher_narratives/pipeline.py` — **primary change site.** Rename `_run_anchor_revision_loop → run_anchor_revision_loop`, `_run_capsule_audit → run_capsule_audit`, `_build_capsule_audit_input → build_capsule_audit_input`; add all three to `__all__` (Task 1). Thread `mode.validation` depths into the two loop calls in `_run_pipeline` (Task 2). Add pure `is_unverified` + `residual_banner` and export them (Task 3).
- `src/pitcher_narratives/personas.py` — add `ValidationPolicy` frozen dataclass + `validation` field on `NarrationMode`; set `REPORT.validation` from `config.MAX_REVISIONS`/`MAX_FACT_REVISIONS`; add `ValidationPolicy` to `__all__` (Task 2).
- `src/pitcher_narratives/cli.py` — refactor `_run_report_command`'s post-stream block (L308–425) into a per-mode emitter + aggregate exit loop (Task 4).
- `tests/` — `test_pipeline.py` (renamed-symbol imports, depth-threading capture, `is_unverified`/`residual_banner` units), `test_personas.py` (ValidationPolicy + REPORT.validation), `test_cli.py` (single-mode byte-identical + aggregate exit).
- `.superpowers/sdd/progress.md` — Phase-7 ledger (Task 5).

**Explicitly NOT in scope (deferred):** RECAP's `--recap-anchor-depth`/`--recap-fact-depth` CLI knobs and morning residual marking (Phase 8); per-mode stdout headers / streaming policy G9 (Phase 8/9); CHANGES `--recent`/`--prior` (Phase 9); bench per-mode ground-truths G12 (Phase 10). `check_value_parity`/`check_hallucinated_metrics` are already public — no work.

---

## Task ordering rationale

1. **Task 1** (publish) is a pure rename — smallest, unblocks reuse, independently reviewable.
2. **Task 2** (ValidationPolicy + threading) depends on nothing from Task 1 but is grouped after it; REPORT depths unchanged.
3. **Task 3** (residual API) is a pure addition consumed by Task 4.
4. **Task 4** (aggregate CLI exit) consumes Task 3; largest behavior-surface, reviewed last.
5. **Task 5** wrap-up: full-suite gate + ledger.

---

## Task 1: Publish the two revision loops + audit-input helper

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — rename defs at L490 (`_build_capsule_audit_input`), L1530 (`_run_anchor_revision_loop`), L1667 (`_run_capsule_audit`); update every internal reference; extend `__all__` (L113–124).
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces (new public names, signatures unchanged):
  - `run_anchor_revision_loop(*, anchor_agent, writer_agent, synthesis, capsule, max_revisions, _model_override=None, tracker=None, tracker_model="") -> tuple[str, AnchorResult, int]`
  - `run_capsule_audit(*, auditor, writer_agent, ground_truth, capsule, max_fact_revisions=MAX_FACT_REVISIONS, _model_override=None, tracker=None, tracker_model="") -> tuple[str, list[AuditFlag], bool]`
  - `build_capsule_audit_input(ground_truth: str, capsule: str) -> str`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py` (near the other import-surface tests):

```python
def test_validation_loops_are_public():
    """Phases 8/9 reuse these by name; they must be importable + exported."""
    from pitcher_narratives import pipeline

    for name in (
        "run_anchor_revision_loop",
        "run_capsule_audit",
        "build_capsule_audit_input",
    ):
        assert hasattr(pipeline, name), f"{name} missing from pipeline"
        assert name in pipeline.__all__, f"{name} not exported in __all__"

    # The old private names must be fully gone (no aliases left behind).
    for old in (
        "_run_anchor_revision_loop",
        "_run_capsule_audit",
        "_build_capsule_audit_input",
    ):
        assert not hasattr(pipeline, old), f"stale private alias {old} remains"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py::test_validation_loops_are_public -v`
Expected: FAIL — `run_anchor_revision_loop missing from pipeline` (still underscore-prefixed).

- [ ] **Step 3: Rename the three symbols and their references**

In `src/pitcher_narratives/pipeline.py`, rename each definition and **every** reference (do a whole-file, whole-word replace per name so call sites update too):

- `_run_anchor_revision_loop` → `run_anchor_revision_loop` (def L1530; call site L1830).
- `_run_capsule_audit` → `run_capsule_audit` (def L1667; call site L1856).
- `_build_capsule_audit_input` → `build_capsule_audit_input` (def L490; any caller inside `run_capsule_audit` / `_run_pipeline`).

Confirm no reference survives:

```bash
rg -n '_run_anchor_revision_loop|_run_capsule_audit|_build_capsule_audit_input' src/ tests/
```

Expected: no matches (in `src/`; a test may reference the old names — update those too).

Then add the three public names to `__all__` (L113–124), keeping the list alphabetized within its existing grouping. The list should now also contain:

```python
    "build_capsule_audit_input",
    "run_anchor_revision_loop",
    "run_capsule_audit",
```

(`build_fact_revision_message`, `check_hallucinated_metrics`, `flag_summary`, `run_narration_modes` are already present — do not duplicate.)

- [ ] **Step 4: Run the new test + the pipeline suite**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_pipeline.py -q
```
Expected: PASS (including `test_validation_loops_are_public`). The rename is symbol-only — every existing pipeline test stays green.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "refactor(pipeline): publish anchor/capsule validation loops (P7)"
```

---

## Task 2: `ValidationPolicy` on `NarrationMode`; thread per-mode depths

**Files:**
- Modify: `src/pitcher_narratives/personas.py` — add `ValidationPolicy` dataclass; add `validation` field to `NarrationMode`; set `REPORT.validation`; extend `__all__` (L45 region).
- Modify: `src/pitcher_narratives/pipeline.py` — in `_run_pipeline`, replace `max_revisions=MAX_REVISIONS` (L1835) with `max_revisions=mode.validation.anchor_depth` and add `max_fact_revisions=mode.validation.fact_depth` to the `run_capsule_audit(...)` call (L1856).
- Test: `tests/test_personas.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `config.MAX_REVISIONS` (=5), `config.MAX_FACT_REVISIONS` (=2); `run_anchor_revision_loop` / `run_capsule_audit` (Task 1).
- Produces:
  - `ValidationPolicy` — `@dataclass(frozen=True)` with `anchor_depth: int`, `fact_depth: int`.
  - `NarrationMode.validation: ValidationPolicy` — new field with a default so existing construction stays valid.
  - `REPORT.validation == ValidationPolicy(anchor_depth=5, fact_depth=2)`.

- [ ] **Step 1: Write the failing test (personas)**

Add to `tests/test_personas.py`:

```python
def test_report_validation_policy_matches_config_depths():
    """REPORT keeps today's depths; config is the single source of truth."""
    from pitcher_narratives.config import MAX_FACT_REVISIONS, MAX_REVISIONS
    from pitcher_narratives.personas import REPORT, ValidationPolicy

    assert REPORT.validation == ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    )
    assert (REPORT.validation.anchor_depth, REPORT.validation.fact_depth) == (5, 2)


def test_validation_policy_is_frozen():
    from dataclasses import FrozenInstanceError

    import pytest

    from pitcher_narratives.personas import ValidationPolicy

    policy = ValidationPolicy(anchor_depth=1, fact_depth=2)
    with pytest.raises(FrozenInstanceError):
        policy.anchor_depth = 3  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_personas.py -k "validation_policy" -v`
Expected: FAIL — `ImportError: cannot import name 'ValidationPolicy'`.

- [ ] **Step 3: Add `ValidationPolicy` + `validation` field**

In `src/pitcher_narratives/personas.py`, add the import near the top (config is already loaded elsewhere; no latency cost):

```python
from pitcher_narratives.config import MAX_FACT_REVISIONS, MAX_REVISIONS
```

Define the policy above `class NarrationMode` (near L359):

```python
@dataclass(frozen=True)
class ValidationPolicy:
    """Per-mode revision-depth knobs for the shared validation stack.

    Detection always runs (cheap, mandatory); only remediation depth is
    tuned. ``depth == 0`` is valid: the loop runs its detection pass, surfaces
    residual flags, and declines to auto-fix (design §7).

    Attributes:
        anchor_depth: Max anchor-revision passes (``max_revisions``).
        fact_depth: Max capsule fact-revision passes (``max_fact_revisions``).
    """

    anchor_depth: int
    fact_depth: int
```

Add the field to `NarrationMode` (after `contracts`, with a default so existing construction is unaffected):

```python
    id: str
    contracts: Mapping[str, OutputContract]
    validation: ValidationPolicy = ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    )
```

Update the class docstring's "Phase 4 carries only `id` and `contracts`" note to record that Phase 7 adds `validation`. `REPORT` needs no explicit `validation=` argument — the default is exactly its policy — but set it explicitly for readability:

```python
REPORT = NarrationMode(
    id="report",
    contracts={
        "scout": SCOUT_REPORT,
        "analyst": NEWSLETTER,
        "generic": SECTIONED,
    },
    validation=ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    ),
)
```

Add `"ValidationPolicy"` to the module `__all__` (the list containing `"NarrationMode"` at L45).

- [ ] **Step 4: Run the personas test**

Run: `uv run pytest tests/test_personas.py -k "validation_policy" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing depth-threading test (pipeline)**

Add to `tests/test_pipeline.py`. This captures the depths actually passed into the loops when the pipeline runs, proving REPORT threads 5/2:

```python
def test_pipeline_threads_report_validation_depths(monkeypatch):
    """_run_pipeline must read depths from mode.validation, not the constants."""
    import asyncio

    from pitcher_narratives import pipeline
    from pitcher_narratives.personas import REPORT

    captured: dict[str, int] = {}

    real_anchor = pipeline.run_anchor_revision_loop
    real_audit = pipeline.run_capsule_audit

    async def anchor_spy(*args, **kwargs):
        captured["anchor"] = kwargs["max_revisions"]
        return await real_anchor(*args, **kwargs)

    async def audit_spy(*args, **kwargs):
        captured["fact"] = kwargs["max_fact_revisions"]
        return await real_audit(*args, **kwargs)

    monkeypatch.setattr(pipeline, "run_anchor_revision_loop", anchor_spy)
    monkeypatch.setattr(pipeline, "run_capsule_audit", audit_spy)

    ctx = _make_test_context()  # existing helper in test_pipeline.py
    pipeline.generate_pipeline_streaming(
        ctx, mode=REPORT, _model_override=_make_test_model()  # existing helpers
    )

    assert captured["anchor"] == REPORT.validation.anchor_depth == 5
    assert captured["fact"] == REPORT.validation.fact_depth == 2
```

**Note for implementer:** `_make_test_context()` / `_make_test_model()` are placeholders — use whatever TestModel + context fixtures `test_pipeline.py` already uses to drive `generate_pipeline_streaming` in its existing tests (grep for `generate_pipeline_streaming(` in that file and copy the setup). The `run_capsule_audit` call site does not currently pass `max_fact_revisions`, so before this change `captured["fact"]` would be absent — that is the failing condition.

- [ ] **Step 6: Run test to verify it fails**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_pipeline.py -k threads_report_validation_depths -v
```
Expected: FAIL — `KeyError: 'fact'` (audit call omits `max_fact_revisions`, so the spy never records it).

- [ ] **Step 7: Thread the depths in `_run_pipeline`**

In `src/pitcher_narratives/pipeline.py`, `_run_pipeline`:

At the anchor call (L1830–1837), change:
```python
        max_revisions=MAX_REVISIONS,
```
to:
```python
        max_revisions=mode.validation.anchor_depth,
```

At the capsule-audit call (L1856–1862), add the depth argument:
```python
        max_fact_revisions=mode.validation.fact_depth,
```

`mode` is already a parameter of `_run_pipeline` (`mode: NarrationMode = DEFAULT_MODE`), so it is in scope. Do not remove the `MAX_REVISIONS`/`MAX_FACT_REVISIONS` imports — `MAX_FACT_REVISIONS` remains the default of `run_capsule_audit`'s parameter, and `config` still owns the numbers.

- [ ] **Step 8: Run the threading test + full pipeline suite**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_pipeline.py tests/test_personas.py -q
```
Expected: PASS. REPORT threads 5/2 (identical to the old constants) → no behavior change.

- [ ] **Step 9: Commit**

```bash
git add src/pitcher_narratives/personas.py src/pitcher_narratives/pipeline.py tests/test_personas.py tests/test_pipeline.py
git commit -m "feat(narration): per-mode ValidationPolicy depths threaded through pipeline (P7)"
```

---

## Task 3: LOUD residual-surfacing API

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — add `is_unverified` + `residual_banner` (near `flag_summary`, L1179); extend `__all__`.
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces:
  - `is_unverified(result: PipelineResult) -> bool` — True iff residual fact-check flags survived (`bool(result.capsule_audit_flags)`). This is exactly today's CLI hard-exit trigger, extracted so every mode (and morning, Phase 8) shares one definition.
  - `residual_banner(result: PipelineResult, *, label: str = "REPORT") -> str | None` — the loud one-line UNVERIFIED banner, or `None` when clean. Byte-matches today's `cli.py:420–422` text when `label="REPORT"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
def _result_with_flags(n: int):
    """Minimal PipelineResult carrying n residual capsule-audit flags."""
    from pitcher_narratives.pipeline import AuditFlag, PipelineResult, SpecialistOutputs

    flags = [
        AuditFlag(category="velocity", specialist="stuff", claim=f"c{i}", data_shows="d")
        for i in range(n)
    ]
    return PipelineResult(
        narrative="x",
        specialists=SpecialistOutputs.model_construct(),  # empty smoke value
        capsule_audit_flags=flags,
    )


def test_is_unverified_tracks_residual_flags():
    from pitcher_narratives.pipeline import is_unverified

    assert is_unverified(_result_with_flags(0)) is False
    assert is_unverified(_result_with_flags(3)) is True


def test_residual_banner_matches_report_wording():
    from pitcher_narratives.pipeline import residual_banner

    assert residual_banner(_result_with_flags(0)) is None
    banner = residual_banner(_result_with_flags(2))
    assert banner == (
        "⚠️  REPORT UNVERIFIED — 2 flagged claim(s) survived the "
        "fact-check loop. Review before use."
    )
    # label parameterizes the surface for RECAP/CHANGES/morning reuse.
    assert residual_banner(_result_with_flags(1), label="RECAP").startswith(
        "⚠️  RECAP UNVERIFIED — 1 flagged claim(s)"
    )
```

**Note for implementer:** if `SpecialistOutputs.model_construct()` cannot stand in (required fields), copy the `SpecialistOutputs(...)` construction from an existing `PipelineResult(...)` in `test_pipeline.py` instead — the residual functions only read `capsule_audit_flags`, so the specialists value is irrelevant.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_pipeline.py -k "is_unverified or residual_banner" -v
```
Expected: FAIL — `ImportError: cannot import name 'is_unverified'`.

- [ ] **Step 3: Add the two functions**

In `src/pitcher_narratives/pipeline.py`, next to `flag_summary` (L1179):

```python
def is_unverified(result: PipelineResult) -> bool:
    """Whether a mode's output shipped with unresolved fact-check flags.

    A result is unverified when residual capsule-audit flags survived the
    fact-revision loop — the same condition that soft-blocks the report CLI.
    Extracted so every narration mode (and morning, Phase 8) shares one
    definition for the aggregate exit policy (design §7, G4).
    """
    return bool(result.capsule_audit_flags)


def residual_banner(result: PipelineResult, *, label: str = "REPORT") -> str | None:
    """The loud UNVERIFIED banner for an unverified result, else ``None``.

    ``label`` names the surface (REPORT / CHANGES / RECAP / a digest item) so
    the same wording marks residual flags on every mode.
    """
    if not result.capsule_audit_flags:
        return None
    n = len(result.capsule_audit_flags)
    return (
        f"⚠️  {label} UNVERIFIED — {n} flagged claim(s) survived the "
        "fact-check loop. Review before use."
    )
```

Add `"is_unverified"` and `"residual_banner"` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_pipeline.py -k "is_unverified or residual_banner" -v
```
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): residual-surfacing API (is_unverified, residual_banner) (P7)"
```

---

## Task 4: Aggregate multi-mode exit policy in the report command

**Files:**
- Modify: `src/pitcher_narratives/cli.py` — refactor `_run_report_command` L306–425 into a per-mode emitter + aggregate loop.
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `is_unverified`, `residual_banner` (Task 3); `run_narration_modes` returning `dict[str, PipelineResult]`.
- Produces: `_emit_mode_result(result: PipelineResult, *, persona: str) -> bool` (module-private CLI helper) — prints one mode's post-stream sections exactly as today and returns whether that mode is unverified. The report command loops over **all** `selected_modes`, ORs the returned flags, prints each banner, and calls `sys.exit(1)` **once** at the end if any mode is unverified (suppressed under `PITCHER_NARRATIVES_TEST_MODEL`).

**Design note (why this is behavior-preserving now):** Only `report` is registered, and `_resolve_modes` dedupes, so `selected_modes` is always length 1 today → the loop body runs exactly once and its output is the current L308–425 text verbatim. The hallucination empty-narrative case still short-circuits *that mode* (returns `False`, not unverified) instead of `return`-ing out of the whole command, so it can no longer abort siblings (G4) — and for a single mode the observable result (exit 0, warning logged, sections skipped) is unchanged. Per-mode stdout headers and the multi-mode streaming policy (G9) are deferred to Phase 8/9; this task changes only the exit aggregation.

- [ ] **Step 1: Characterize current single-mode behavior (guard test)**

First confirm what `test_cli.py` already asserts about the report command's stdout/exit, so the refactor is provably byte-identical:

```bash
rg -n "REPORT UNVERIFIED|Capsule Fact-Check|_run_report_command|capsule_audit_flags|SystemExit" tests/test_cli.py
```

If an end-to-end report-command stdout/exit test exists, note its name — Step 4 re-runs it unchanged. If none asserts the UNVERIFIED soft-block, add this guard test to `tests/test_cli.py` (mirror the harness the neighboring report-command tests use — TestModel via `PITCHER_NARRATIVES_TEST_MODEL`, `capsys`, and the arg parser):

```python
def test_report_single_mode_soft_blocks_on_residual_flags(monkeypatch, capsys):
    """UNVERIFIED banner prints for a single REPORT with residual flags;
    exit is suppressed under test-model but the banner is unconditional."""
    # Reuse the existing report-command invocation pattern in this file
    # (grep for _run_report_command / run_narration_modes monkeypatch).
    # Force a result carrying one residual capsule_audit_flag and assert the
    # banner text lands on stderr.
    ...
```

**Implementer:** flesh `...` out using this file's established pattern for driving `_run_report_command` (monkeypatch `run_narration_modes` to return a dict with a crafted `PipelineResult`). The assertion is: `"⚠️  REPORT UNVERIFIED — 1 flagged claim(s)"` appears in `capsys.readouterr().err`. Keep the test at parity with the existing report-command tests' setup; do not invent new scaffolding.

- [ ] **Step 2: Run the guard test (baseline green)**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_cli.py -k "report" -q
```
Expected: PASS against the current code (this is a characterization test — it must be green *before* the refactor so we can prove the refactor preserves it).

- [ ] **Step 3: Refactor into emitter + aggregate loop**

In `src/pitcher_narratives/cli.py`:

Add the residual-API import to the lazy pipeline import block already present at L263–268 (the `from pitcher_narratives.pipeline import (...)` block that brings in `check_hallucinated_metrics`, `run_narration_modes`, `write_pipeline_data_file`):

```python
        is_unverified,
        residual_banner,
```

Extract L308–411 (the executive-summary through hallucination-check printing) verbatim into a module-level helper. It takes the result + persona, prints the sections exactly as today, and returns `is_unverified(result)`:

```python
def _emit_mode_result(pipe_result, *, persona: str) -> bool:
    """Print one mode's post-stream sections and return whether it is unverified.

    Byte-identical to the report command's historical single-mode output. The
    empty-narrative (hallucination) case skips the remaining sections for THIS
    mode but does not abort siblings (design G4).
    """
    from pitcher_narratives.pipeline import check_hallucinated_metrics, is_unverified

    # <<< paste L308-387 verbatim: Executive Summary, Brief, Stuff Analysis,
    #     Data Audit, Capsule Fact-Check, Value Parity, Anchor Check >>>

    # Hallucination check — skipped if the narrative is empty.
    if not pipe_result.narrative:
        log.warning("Pipeline produced empty narrative — skipping hallucination check")
        return is_unverified(pipe_result)

    # <<< paste L395-410 verbatim: hallucination check printing >>>

    return is_unverified(pipe_result)
```

Then replace L306–425 in `_run_report_command` with the aggregate loop:

```python
    from pitcher_narratives.pipeline import residual_banner

    any_unverified = False
    for mode in selected_modes:
        pipe_result = results[mode.id]
        if _emit_mode_result(pipe_result, persona=args.persona):
            any_unverified = True
            banner = residual_banner(pipe_result, label=mode.id.upper())
            print(f"\n{banner}", file=sys.stderr)

    if any_unverified and not os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        sys.exit(1)
```

Notes:
- `_emit_mode_result` returning `is_unverified` folds the old L417 `if pipe_result.capsule_audit_flags:` trigger into the aggregate — the banner is emitted per unverified mode, the exit fires once at the end. For a single REPORT mode the banner text and stderr routing match L419–423 exactly (`label="REPORT"`).
- Do not keep the old `return` at L393 or the old `sys.exit(1)` at L425 — both are now handled by the loop/aggregate.
- Keep the `# Scouting Report` header at L293 and the `run_narration_modes` streaming call as-is (G9 multi-header streaming is deferred).

- [ ] **Step 4: Run the guard test + CLI suite (prove byte-identical)**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_cli.py -q
```
Expected: PASS — the Step-1 characterization test and every existing report-command test stay green, proving the single-mode output/exit is unchanged.

- [ ] **Step 5: Add an aggregate-policy test (multi-mode OR)**

Because only `report` is registered, exercise the aggregate through `_emit_mode_result` + the loop logic directly rather than end-to-end. Add to `tests/test_cli.py`:

```python
def test_emit_mode_result_returns_unverified_status(capsys):
    """The emitter reports unverified iff residual flags survived — the
    signal the aggregate exit policy ORs across modes."""
    from pitcher_narratives.cli import _emit_mode_result

    clean = _result_with_flags(0)      # reuse helper or inline construction
    flagged = _result_with_flags(2)

    assert _emit_mode_result(clean, persona="scout") is False
    assert _emit_mode_result(flagged, persona="scout") is True
```

**Implementer:** `_result_with_flags` is the Task-3 test helper; either import it, lift it to a shared conftest, or inline the `PipelineResult(...)` construction. This proves the OR-input; a full two-real-mode CLI run lands with CHANGES/RECAP (Phases 8/9), which is where the second registered mode first exists.

- [ ] **Step 6: Run the aggregate test**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives \
  uv run pytest tests/test_cli.py -k "emit_mode_result or report" -q
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat(cli): aggregate multi-mode residual exit policy (P7, G4)"
```

---

## Task 5: Phase-7 wrap-up — full-suite green gate + ledger

**Files:**
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: Run the full suite**

Run:
```bash
PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q
```
Expected: all pass except the one documented pre-existing failure `test_to_prompt_token_budget`. Any other failure is a real regression — fix before proceeding.

- [ ] **Step 2: Grep-confirm the publish is clean**

```bash
rg -n '_run_anchor_revision_loop|_run_capsule_audit|_build_capsule_audit_input' src/ tests/
```
Expected: no matches (all references migrated to the public names).

- [ ] **Step 3: Confirm no behavior drift**

Confirm no golden/characterization fixture changed in this phase:
```bash
git diff --stat f7d9903..HEAD -- tests/
```
Expected: only *added* tests (Tasks 1–4) — no edits to pinned golden literals. If a golden moved, a change was not behavior-preserving; investigate before sign-off.

- [ ] **Step 4: Update the ledger**

Append a `## Phase 7: Shared Validation Stack` section to `.superpowers/sdd/progress.md`: plan path (`docs/superpowers/plans/2026-07-02-shared-validation-stack.md`), base commit (`2320a70`), the 4 task commit SHAs, note that REPORT stayed byte-identical (depths 5/2 unchanged, no goldens moved), that `main` (`f9ea1ce`) is untouched and the branch is not pushed, and that the published loops + `ValidationPolicy` + `residual_banner` are the seams Phases 8 (RECAP/morning) and 9 (CHANGES) consume.

- [ ] **Step 5: Commit**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(sdd): Phase 7 shared-validation-stack wrap-up"
```

---

## Self-Review (spec coverage)

- **§7 publish `_run_anchor_revision_loop`, `_run_capsule_audit`, `_build_capsule_audit_input`** → Task 1. `build_anchor_message`/`build_revision_message` (anchor.py) and `build_fact_revision_message` (pipeline.py) are **already public + exported** — verified in the code map; no work needed. ✓
- **§7 parameterize revision depth per mode; REPORT = anchor 5 / fact 2** → Task 2 (`ValidationPolicy`, `NarrationMode.validation`, threaded into `_run_pipeline`; REPORT sources depths from `config`). ✓
- **§7 LOUD residual surfacing API (reusable so morning can mirror it)** → Task 3 (`is_unverified`, `residual_banner`). ✓
- **§16 G4 aggregate exit policy: run all modes, OR flags, print each, exit non-zero if any unverified; no first-failure abort / hallucination early-return killing siblings** → Task 4. ✓
- **"Wire REPORT through (no behavior change)"** → Tasks 2 + 4 keep REPORT depths 5/2 and single-mode CLI output/exit byte-identical; Task 5 Step 3 gates on zero golden drift. ✓
- **Deferred (correctly, to later phases):** RECAP `--recap-anchor-depth`/`--recap-fact-depth` + morning residual marking (Phase 8, §7); per-mode headers / streaming G9 (Phase 8/9); CHANGES frames (Phase 9); bench per-mode ground-truths G12 (Phase 10). Noted in File Structure. ✓
- **Placeholder scan:** the only `...`/`<<< paste >>>` markers are in Task 4 (verbatim relocation of existing L308–411) and the two CLI test bodies, each with an explicit implementer note pointing at the exact existing lines/pattern to copy — no logic is left unspecified. ✓
- **Type consistency:** `ValidationPolicy(anchor_depth, fact_depth)` used identically in Tasks 2; `is_unverified(result)`/`residual_banner(result, *, label)` signatures match between Task 3 definition and Task 4 consumption; renamed loop names consistent between Task 1 and Task 2's threading. ✓
