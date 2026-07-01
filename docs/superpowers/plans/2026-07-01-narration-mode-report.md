# NarrationMode Abstraction + REPORT (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a first-class `NarrationMode` abstraction, port today's report path onto it (rename the `CAPSULE` OutputContract → `SCOUT_REPORT`, fold `REPORT_CONTRACTS` into `REPORT.contracts`), thread a `mode` selector through the pipeline, and add the per-mode `dict[str, PipelineResult]` return shape + single-mode `--mode` CLI scaffolding — all **behavior-preserving** under the existing day-window.

**Architecture:** `NarrationMode` is a frozen dataclass carrying `id` + `contracts: dict[persona_id, OutputContract]`. It lives in `personas.py` (where `OutputContract`, `Persona`, and `build_writer_system_prompt` already live), so it adds **no new import edge** and cannot create a `pipeline`↔`personas` cycle. The single `REPORT` mode reproduces today's persona→contract mapping exactly. `build_writer_system_prompt(persona, mode=REPORT)` reads `mode.contracts` instead of the retired module-global `REPORT_CONTRACTS`. The pipeline threads `mode` from `make_pipeline_agents` → `_run_pipeline` → `generate_pipeline_streaming`, and a new `run_narration_modes(...) -> dict[str, PipelineResult]` is the multi-mode entry point the CLI consumes (with one entry in phase 4). The byte-identical writer-prompt fixture tests (`test_personas.py:145-182`) are the primary characterization guard: no prompt bytes, structure block, framing, or overlay is touched.

**Tech Stack:** Python 3.14, dataclasses, pydantic / pydantic-ai (`TestModel` / `_model_override` injection), pytest, `uv` env + test running.

## Global Constraints

- Python `>=3.14`; run everything via `uv run`.
- `snake_case` modules/functions, `PascalCase` classes / Pydantic models / type aliases, `UPPER_SNAKE_CASE` constants.
- Structured data via Pydantic models / frozen dataclasses, never bare dicts for domain objects.
- **Behavior-preserving:** no writer/specialist/auditor prompt bytes, structure block, framing string, overlay, or streamed CLI output changes. The frozen writer-prompt fixtures (`tests/fixtures/writer_prompt_*.txt` via `test_personas.py:145-182`) and the full existing suite must stay green. New behavior is additive (a `mode` param defaulting to `REPORT`; a new dict entry point).
- **Day-window still in force.** No appearance-count slicing, no new temporal frames, no `TemporalFrameSpec` — those are phases 5/6/9.
- **Scope discipline (YAGNI):** `NarrationMode` carries only the members `REPORT` actually consumes now — `id` and `contracts`. `input_assembler`, `focus`, `temporal_frame`, and `validation` (the other §4 members) are **deferred** to the phases that consume them (RECAP/CHANGES phases 8–9 for the assembler & frame; validation-stack phase 7). Frozen-dataclass fields with defaults can be added later without breaking existing construction, so deferral is safe. See Self-Review §"Deferrals" for the rationale.
- **Rename disambiguation — do NOT touch these look-alikes:** only the `CAPSULE` *OutputContract* symbol (`personas.py:326`) is renamed. Leave `_CAPSULE_STRUCTURE` (`personas.py:211`), `CAPSULE_RUBRIC` (`bench/rubric.py`), `_CAPSULE_AUDITOR_PROMPT` (`pipeline.py:448`), and the bench `"capsule"` **tier** key (`bench/runner.py:100,123`, `bench/scorecard.py:39`, etc.) unchanged — they are different "capsule" meanings (structure block, bench rubric, auditor prompt, bench output tier), not the report contract.

---

## Task 1: Rename the `CAPSULE` OutputContract → `SCOUT_REPORT`

**Files:**
- Modify: `src/pitcher_narratives/personas.py` (`__all__` :32; contract def :326-331; `REPORT_CONTRACTS` value :357; `build_writer_system_prompt` docstring + fallback :537-548)
- Modify: `tests/test_personas.py` (import :14; `test_scout_report_contract_is_capsule` :114-119; RT-4 fallback test :795-814)

**Interfaces:**
- Consumes: existing `OutputContract`, `_CAPSULE_STRUCTURE`, `_SYNTHESIS_FRAMING`.
- Produces: module symbol `SCOUT_REPORT: OutputContract` (`id="scout_report"`, `length_target=(150, 350)`, `structure=_CAPSULE_STRUCTURE`, `input_framing=_SYNTHESIS_FRAMING`). `CAPSULE` no longer exists. `REPORT_CONTRACTS["scout"] is SCOUT_REPORT`. The composed writer prompt for every persona is **byte-identical** to before (only the Python symbol + the contract's `id` string change; neither is in the prompt bytes).

- [ ] **Step 1: Update the failing characterization test to the new name**

In `tests/test_personas.py`, change the import at line 14 `CAPSULE,` → `SCOUT_REPORT,` (keep alphabetical grouping — it moves down; place it before `SECTIONED,`). Then rewrite `test_scout_report_contract_is_capsule` (:114-119):

```python
def test_scout_report_contract_is_scout_report():
    """The scout report contract is SCOUT_REPORT with length_target (150, 350)."""
    contract = REPORT_CONTRACTS["scout"]
    assert contract is SCOUT_REPORT
    assert contract.length_target == (150, 350)
    assert all(isinstance(v, int) for v in contract.length_target)
```

And rewrite the RT-4 fallback test (:795-814) — the fallback contract is now `SCOUT_REPORT`; its structure fingerprint phrase (`"2-3 paragraph"`) is unchanged because `_CAPSULE_STRUCTURE` is untouched:

```python
def test_build_writer_system_prompt_falls_back_to_scout_report_for_unknown_persona():
    """RT-4: build_writer_system_prompt uses SCOUT_REPORT for personas not in REPORT_CONTRACTS.

    A newly added voice persona whose id is not yet in REPORT_CONTRACTS must
    not raise a KeyError.  It should produce a SCOUT_REPORT-shaped prompt (i.e.
    contain the structure fingerprint phrase) rather than crashing.
    """
    unknown = Persona(
        id="future_voice",
        display_name="Future Voice",
        description="A persona not yet mapped to a report contract",
        overlay="Write in a future style.",
    )
    # Must not raise KeyError
    prompt = build_writer_system_prompt(unknown)
    # SCOUT_REPORT structure is "2-3 paragraph" — the fallback contract's fingerprint
    assert "2-3 paragraph" in prompt, (
        "build_writer_system_prompt should fall back to SCOUT_REPORT for unmapped "
        "personas; expected structure phrase '2-3 paragraph' in composed prompt"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_personas.py -k "scout_report_contract or falls_back" -v`
Expected: FAIL — `ImportError: cannot import name 'SCOUT_REPORT'`.

- [ ] **Step 3: Rename the contract in `personas.py`**

Change the contract definition (:326-331):

```python
SCOUT_REPORT = OutputContract(
    id="scout_report",
    length_target=(150, 350),
    structure=_CAPSULE_STRUCTURE,
    input_framing=_SYNTHESIS_FRAMING,
)
```

Change the `__all__` entry (:32) `"CAPSULE",` → `"SCOUT_REPORT",` (re-sort: it moves below `PERSONAS`/`REPORT_CONTRACTS`, above `SECTIONED`). Change the `REPORT_CONTRACTS` value (:357) `"scout": CAPSULE,` → `"scout": SCOUT_REPORT,`. Update `build_writer_system_prompt` docstring + fallback (:537-548): replace the two `CAPSULE` mentions in the docstring with `SCOUT_REPORT`, the warning string `"falling back to CAPSULE"` → `"falling back to SCOUT_REPORT"`, and `contract = CAPSULE` → `contract = SCOUT_REPORT`.

- [ ] **Step 4: Grep to confirm the contract symbol is fully renamed (and look-alikes are untouched)**

Run: `cd src/pitcher_narratives && grep -rn "\bCAPSULE\b" . ../../tests`
Expected: the only remaining `CAPSULE` matches are `CAPSULE_RUBRIC` (bench) and the `CAPSULE_BODY_TEXT_MARKER` string literal in `tests/test_anchor.py` — **no bare `CAPSULE` contract references**. `_CAPSULE_STRUCTURE`, `_CAPSULE_AUDITOR_PROMPT`, and `"capsule"` tier strings are expected and correct to remain.

- [ ] **Step 5: Run the persona + prompt-fixture suites to prove byte-identical prompts**

Run: `uv run pytest tests/test_personas.py tests/test_voice_golden.py tests/test_pipeline_persona_wiring.py -v`
Expected: PASS — including the byte-identical fixture tests (`test_scout_composed_prompt_is_byte_identical_to_v19` and the analyst/generic variants), proving the rename changed no prompt bytes.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/personas.py tests/test_personas.py
git commit -m "refactor(narration): rename CAPSULE OutputContract to SCOUT_REPORT"
```

---

## Task 2: Introduce `NarrationMode` + `REPORT`; fold `REPORT_CONTRACTS` into `REPORT.contracts`

**Files:**
- Modify: `src/pitcher_narratives/personas.py` (add `NarrationMode` dataclass + `REPORT` + registry after the contract instances, ~:361; retire `REPORT_CONTRACTS` standalone dict :356-360; update `build_writer_system_prompt` :530-549; extend `__all__` :29-47)
- Modify: `tests/test_personas.py` (import :19; `REPORT_CONTRACTS` references — see Step 4)
- Test: `tests/test_personas.py` (new `NarrationMode` tests)

**Interfaces:**
- Consumes: `SCOUT_REPORT`, `NEWSLETTER`, `SECTIONED` (Task 1 + existing), `OutputContract`, `Persona`, `build_system_prompt`.
- Produces:
  - `@dataclass(frozen=True) class NarrationMode: id: str; contracts: dict[str, OutputContract]`.
  - `REPORT: NarrationMode` with `id="report"`, `contracts={"scout": SCOUT_REPORT, "analyst": NEWSLETTER, "generic": SECTIONED}`.
  - `NARRATION_MODES: MappingProxyType[str, NarrationMode]` (read-only view), `DEFAULT_MODE: NarrationMode = REPORT`, `get_narration_mode(mode_id: str) -> NarrationMode` (raises `ValueError` with valid-ids list, mirroring `get_persona`).
  - `build_writer_system_prompt(persona: Persona, mode: NarrationMode = REPORT) -> str` now reads `mode.contracts` (fallback `SCOUT_REPORT`). Single-arg calls are unchanged in behavior.
  - `REPORT_CONTRACTS` **module global is removed**; `REPORT.contracts` is the single source of truth.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_personas.py` (near the other registry tests, after `test_get_persona_unknown_raises_valueerror` ~:135). Also add `NarrationMode`, `REPORT`, `get_narration_mode` to the existing `pitcher_narratives.personas` import block:

```python
def test_report_mode_maps_personas_to_report_contracts():
    """REPORT.contracts reproduces the legacy REPORT_CONTRACTS mapping."""
    assert REPORT.id == "report"
    assert REPORT.contracts["scout"] is SCOUT_REPORT
    assert REPORT.contracts["analyst"] is NEWSLETTER
    assert REPORT.contracts["generic"] is SECTIONED


def test_narration_mode_is_frozen():
    """NarrationMode is immutable so registry identity is stable."""
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        REPORT.id = "changed"  # type: ignore[misc]


def test_get_narration_mode_returns_report():
    """get_narration_mode('report') resolves to the REPORT instance."""
    assert get_narration_mode("report") is REPORT


def test_get_narration_mode_unknown_raises_valueerror():
    """Unknown mode ids raise ValueError listing valid ids (not KeyError)."""
    with pytest.raises(ValueError, match="bogus"):
        get_narration_mode("bogus")


def test_build_writer_system_prompt_mode_arg_is_byte_identical_to_default():
    """Passing mode=REPORT explicitly equals the default single-arg call."""
    for pid in ("scout", "analyst", "generic"):
        p = get_persona(pid)
        assert build_writer_system_prompt(p, REPORT) == build_writer_system_prompt(p)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_personas.py -k "narration_mode or report_mode or get_narration" -v`
Expected: FAIL — `ImportError: cannot import name 'NarrationMode'`.

- [ ] **Step 3: Add `NarrationMode`, `REPORT`, registry, and rewire `build_writer_system_prompt`**

In `personas.py`, **replace** the `REPORT_CONTRACTS` standalone block (:354-360) with the mode abstraction:

```python
@dataclass(frozen=True)
class NarrationMode:
    """A top-level narration selector composed with the Persona × OutputContract
    machinery. A mode owns the persona → report-contract mapping (which output
    structure each voice writes in). Voice stays orthogonal: Persona picks tone,
    NarrationMode picks the output shape.

    Phase 4 carries only ``id`` and ``contracts`` — the members the REPORT path
    consumes today. The frame selector, focus directive, input assembler, and
    validation policy (design §4) are added by later phases (5/7/8/9) that
    consume them; frozen-dataclass fields with defaults can be appended without
    breaking existing construction.
    """

    id: str
    contracts: dict[str, OutputContract]


# REPORT reproduces today's report path: each persona's canonical output contract.
REPORT = NarrationMode(
    id="report",
    contracts={
        "scout": SCOUT_REPORT,
        "analyst": NEWSLETTER,
        "generic": SECTIONED,
    },
)

_NARRATION_MODES_INTERNAL: dict[str, NarrationMode] = {"report": REPORT}

# Import-time invariant: registry key must match mode.id.
for _mid, _mode in _NARRATION_MODES_INTERNAL.items():
    if _mode.id != _mid:
        raise ValueError(
            f"Registry key {_mid!r} does not match mode.id {_mode.id!r}"
        )
del _mid, _mode

NARRATION_MODES: MappingProxyType[str, NarrationMode] = MappingProxyType(
    _NARRATION_MODES_INTERNAL
)

DEFAULT_MODE: NarrationMode = NARRATION_MODES["report"]


def get_narration_mode(mode_id: str) -> NarrationMode:
    """Resolve a narration-mode id to its NarrationMode instance.

    Raises ValueError (not KeyError) with the valid ids, mirroring get_persona.
    """
    try:
        return NARRATION_MODES[mode_id]
    except KeyError:
        valid = ", ".join(sorted(NARRATION_MODES.keys()))
        raise ValueError(f"Unknown narration mode {mode_id!r}; valid: {valid}") from None
```

Then update `build_writer_system_prompt` (:530-549) to take the mode and read `mode.contracts`:

```python
def build_writer_system_prompt(persona: Persona, mode: NarrationMode = REPORT) -> str:
    """Compose the report-writer prompt for a persona within a narration mode.

    Thin shim over build_system_prompt that pairs the persona with the mode's
    output contract for its voice, keeping report call sites and behaviour
    unchanged (mode defaults to REPORT).

    Personas not present in the mode's contracts (e.g. newly added voice
    personas) fall back to SCOUT_REPORT — the default report format — rather
    than raising a KeyError.
    """
    contract = mode.contracts.get(persona.id)
    if contract is None:
        log.warning(
            "Persona %r has no contract in mode %r; falling back to SCOUT_REPORT. "
            "Add an entry to the mode's contracts to suppress this warning.",
            persona.id,
            mode.id,
        )
        contract = SCOUT_REPORT
    return build_system_prompt(persona, contract)
```

Finally, in `__all__` (:29-47) remove `"REPORT_CONTRACTS",` and add (sorted) `"DEFAULT_MODE",`, `"NARRATION_MODES",`, `"NarrationMode",`, `"REPORT",`, and `"get_narration_mode",`.

- [ ] **Step 4: Update the remaining `REPORT_CONTRACTS` test references to `REPORT.contracts`**

Run: `grep -rn "REPORT_CONTRACTS" src tests`
Expected before: only `tests/test_personas.py` hits remain (the `src/personas.py` global is gone). Update each in `tests/test_personas.py`:
- Import line (:19): remove `REPORT_CONTRACTS,` (add `REPORT,` and `get_narration_mode,` if not already added in Step 1).
- `test_scout_report_contract_is_scout_report` (:116, from Task 1): `REPORT_CONTRACTS["scout"]` → `REPORT.contracts["scout"]`.
- `assert REPORT_CONTRACTS["analyst"] is NEWSLETTER` (:330) → `REPORT.contracts["analyst"]`.
- `assert REPORT_CONTRACTS["generic"] is SECTIONED` (:466) → `REPORT.contracts["generic"]`.
- Any remaining prose/docstring mentions (RT-4 test docstring, and ~2 others surfaced by grep): reword `REPORT_CONTRACTS` → `the mode's contracts`.

Re-run: `grep -rn "REPORT_CONTRACTS" src tests` → Expected: **zero matches**.

- [ ] **Step 5: Run the persona suite (behavior preservation)**

Run: `uv run pytest tests/test_personas.py tests/test_voice_golden.py tests/test_pipeline_persona_wiring.py tests/test_signals.py -v`
Expected: PASS — new `NarrationMode` tests + all fixture/byte-identical tests green.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/personas.py tests/test_personas.py
git commit -m "feat(narration): add NarrationMode + REPORT; fold REPORT_CONTRACTS"
```

---

## Task 3: Thread `mode` through the pipeline writer selection

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (import :83; `make_pipeline_agents` :1231-1235,:1315; `--print-prompts` render :1079; `_run_pipeline` :1752-1769; `generate_pipeline_streaming` :1908-1937)
- Test: `tests/test_pipeline_persona_wiring.py` (new mode-threading test)

**Interfaces:**
- Consumes: `NarrationMode`, `DEFAULT_MODE`/`REPORT`, `build_writer_system_prompt(persona, mode)`, `get_persona` (existing).
- Produces:
  - `make_pipeline_agents(provider="gemini", thinking="high", persona=DEFAULT_PERSONA, mode: NarrationMode = REPORT) -> PipelineAgents` — writer built via `build_writer_system_prompt(persona, mode)`.
  - `_run_pipeline(..., mode: NarrationMode = REPORT)` and `generate_pipeline_streaming(..., mode: NarrationMode = REPORT)` accept + forward the mode.
  - Defaulting to `REPORT` reproduces today exactly.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline_persona_wiring.py`:

```python
def test_make_pipeline_agents_accepts_mode(self):
    """make_pipeline_agents accepts a mode keyword defaulting to REPORT."""
    import inspect
    from pitcher_narratives.pipeline import make_pipeline_agents
    from pitcher_narratives.personas import REPORT
    sig = inspect.signature(make_pipeline_agents)
    assert "mode" in sig.parameters
    assert sig.parameters["mode"].default is REPORT


def test_generate_pipeline_streaming_accepts_mode(self):
    """generate_pipeline_streaming accepts a mode keyword."""
    import inspect
    from pitcher_narratives.pipeline import generate_pipeline_streaming
    assert "mode" in inspect.signature(generate_pipeline_streaming).parameters
```

(Match the existing class/method style in that file — the report shows sibling `test_generate_pipeline_streaming_accepts_persona` at :43-47.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pipeline_persona_wiring.py -k "accepts_mode" -v`
Expected: FAIL — `assert 'mode' in sig.parameters`.

- [ ] **Step 3: Thread the mode**

In `pipeline.py`, extend the `from pitcher_narratives.personas import (...)` group (:83 region) to include `NarrationMode,` and `REPORT,`.

`make_pipeline_agents` (:1231-1235) — add the param:

```python
def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona = DEFAULT_PERSONA,
    mode: NarrationMode = REPORT,
) -> PipelineAgents:
```

and its writer construction (:1315):

```python
        writer=_writer(build_writer_system_prompt(persona, mode)),
```

`_run_pipeline` (:1752-1769) — add `mode: NarrationMode = REPORT` to the signature (after `persona`) and pass it through:

```python
    agents = make_pipeline_agents(provider, thinking, persona_obj, mode)
```

`generate_pipeline_streaming` (:1908-1937) — add `mode: NarrationMode = REPORT` to the signature (after `persona`) and forward it:

```python
    return asyncio.run(
        _run_pipeline(ctx, provider=provider, thinking=thinking,
                      persona=persona, mode=mode, _model_override=_model_override)
    )
```

The `--print-prompts` render at `pipeline.py:1079` (`build_writer_system_prompt(persona_obj)`) — leave the single-arg call as-is; it defaults to `REPORT` and stays byte-identical. (No `mode` is plumbed into that debug render path in phase 4; the CLI `--mode` is single-mode `report`.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pipeline_persona_wiring.py tests/test_pipeline.py -k "mode or persona or spine" -v`
Expected: PASS — new mode tests + existing persona-wiring/spine tests unaffected.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline_persona_wiring.py
git commit -m "feat(narration): thread NarrationMode through pipeline writer selection"
```

---

## Task 4: Add the multi-mode entry point `run_narration_modes` (per-mode result shape, G10)

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add `run_narration_modes` beside `generate_pipeline_streaming` ~:1938; extend `__all__` :118 region)
- Test: `tests/test_pipeline.py` (new entry-point test near the existing `generate_pipeline_streaming` tests ~:390)

**Interfaces:**
- Consumes: `generate_pipeline_streaming` (Task 3), `NarrationMode`, `REPORT`, `PipelineResult`.
- Produces:
  - `run_narration_modes(ctx: PitcherContext, *, modes: list[NarrationMode] | None = None, provider="gemini", thinking: ThinkingEffort="high", persona: str="scout", _model_override=None) -> dict[str, PipelineResult]`. Runs each mode sequentially via `generate_pipeline_streaming(mode=...)`, keyed by `mode.id`, preserving requested order (dict preserves insertion order). `modes=None` defaults to `[REPORT]`.
  - This is **the** multi-mode entry point (design G10). `generate_pipeline_streaming` remains the single-result convenience used by bench/tests — unchanged return type.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py` (use the existing `TestModel`/`ctx` fixture idiom in that file — the streaming tests at :391/:432 show the pattern):

```python
def test_run_narration_modes_returns_dict_keyed_by_mode_id(ctx):
    """run_narration_modes returns {mode.id: PipelineResult}; default is REPORT only."""
    from pitcher_narratives.pipeline import run_narration_modes, PipelineResult
    from pitcher_narratives.personas import REPORT
    from pydantic_ai.models.test import TestModel

    model = TestModel(call_tools=[], custom_output_text="Report body.")
    results = run_narration_modes(ctx, _model_override=model)

    assert set(results) == {"report"}
    assert isinstance(results["report"], PipelineResult)


def test_run_narration_modes_explicit_report_matches_single_entry(ctx):
    """Explicitly passing [REPORT] yields the same single 'report' key."""
    from pitcher_narratives.pipeline import run_narration_modes
    from pitcher_narratives.personas import REPORT
    from pydantic_ai.models.test import TestModel

    model = TestModel(call_tools=[], custom_output_text="Report body.")
    results = run_narration_modes(ctx, modes=[REPORT], _model_override=model)
    assert list(results) == ["report"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pipeline.py -k "run_narration_modes" -v`
Expected: FAIL — `ImportError: cannot import name 'run_narration_modes'`.

- [ ] **Step 3: Implement `run_narration_modes`**

Directly below `generate_pipeline_streaming` (~:1938) in `pipeline.py`:

```python
def run_narration_modes(
    ctx: PitcherContext,
    *,
    modes: list[NarrationMode] | None = None,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    _model_override: Any = None,
) -> dict[str, PipelineResult]:
    """Run one or more narration modes over a single pitcher context.

    The multi-mode entry point (design G10): returns a PipelineResult per mode,
    keyed by ``mode.id`` in requested order. Each mode runs its own writer +
    validation via generate_pipeline_streaming; the shared analysis spine is
    re-run per mode in phase 4 (single-mode in practice). Reuse of one spine
    across modes is a later-phase optimization (design §10).

    Args:
        ctx: Assembled pitcher context.
        modes: Narration modes to render; defaults to [REPORT].
        provider: LLM provider key.
        thinking: Thinking effort level.
        persona: Persona id string.
        _model_override: Optional model override for testing.

    Returns:
        Mapping of mode id -> PipelineResult, insertion-ordered by ``modes``.
    """
    selected = modes if modes is not None else [REPORT]
    results: dict[str, PipelineResult] = {}
    for mode in selected:
        results[mode.id] = generate_pipeline_streaming(
            ctx, provider=provider, thinking=thinking,
            persona=persona, mode=mode, _model_override=_model_override,
        )
    return results
```

Add `"run_narration_modes",` to `__all__` (near `"generate_pipeline_streaming"` :118).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pipeline.py -k "run_narration_modes" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(narration): add run_narration_modes dict entry point (G10)"
```

---

## Task 5: CLI `--mode` scaffolding (single-mode, G9/G4)

**Files:**
- Modify: `src/pitcher_narratives/cli.py` (argparse `--mode` addition near the other report args; import :231; the report block :256-387)
- Test: `tests/test_cli.py` (new `--mode` parse/validate tests; if the file does not exist, create it — check first with `ls tests/test_cli.py`)

**Interfaces:**
- Consumes: `run_narration_modes` (Task 4), `get_narration_mode`, `NARRATION_MODES`.
- Produces: `report` subcommand accepts `--mode report` (comma-split, validated against `NARRATION_MODES`; unknown/not-yet-available ids exit non-zero with a clear message). Default (no `--mode`) = `["report"]`, and the streamed output + section prints + exit code are **byte-identical to today** for the single REPORT mode.

- [ ] **Step 1: Write the failing test**

First check the harness: `ls tests/test_cli.py` (many CLI tests invoke `main` with `PITCHER_NARRATIVES_TEST_MODEL` set — mirror the existing pattern if the file exists). Add a parse/validation test that does not require the LLM:

```python
def test_mode_flag_rejects_unavailable_mode(capsys):
    """--mode changes is rejected in phase 4 (only 'report' is registered)."""
    import pytest
    from pitcher_narratives.cli import build_parser  # or the arg-parsing entry used elsewhere
    parser = build_parser()
    args = parser.parse_args(["report", "592155", "--mode", "changes"])
    # validation happens in the command handler; assert the validator raises/exits
    from pitcher_narratives.cli import _resolve_modes  # helper added in Step 3
    with pytest.raises(SystemExit):
        _resolve_modes(args.mode)


def test_mode_flag_defaults_to_report():
    from pitcher_narratives.cli import _resolve_modes
    from pitcher_narratives.personas import REPORT
    assert _resolve_modes(None) == [REPORT]
    assert _resolve_modes("report") == [REPORT]
```

(If `cli.py` has no `build_parser`/handler seam to import, adapt the test to the actual argparse construction in the file — read `cli.py` around the `report` subparser first and target the real symbols. The two behaviors to lock are: default → `[REPORT]`; unavailable id → `SystemExit`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -k "mode_flag" -v`
Expected: FAIL — `_resolve_modes` / `--mode` not defined.

- [ ] **Step 3: Add `--mode` and the resolver; consume the dict**

In `cli.py`:

1. Add the argument to the `report` subparser (near `--persona`):

```python
    report_parser.add_argument(
        "--mode",
        default=None,
        help="Narration mode(s), comma-separated. Phase 4: only 'report' is "
             "available (changes/recap land in later phases). Default: report.",
    )
```

2. Add a module-level resolver (comma-split + validate, mirroring bench's `--providers`):

```python
def _resolve_modes(raw: str | None) -> list["NarrationMode"]:
    """Parse the --mode flag into NarrationMode instances.

    None -> [REPORT]. Unknown or not-yet-available ids exit non-zero with the
    valid set (get_narration_mode raises ValueError; we translate to exit 2).
    """
    from pitcher_narratives.personas import REPORT, get_narration_mode
    if raw is None:
        return [REPORT]
    ids = [m.strip() for m in raw.split(",") if m.strip()]
    modes = []
    for mid in ids:
        try:
            modes.append(get_narration_mode(mid))
        except ValueError as e:
            log.error("%s", e)
            sys.exit(2)
    return modes or [REPORT]
```

3. In the report command body (:256-268), replace the direct `generate_pipeline_streaming(...)` call with the resolved-mode dict entry point. For phase 4 the header + section block stay exactly as-is, consuming the single `"report"` result:

```python
    selected_modes = _resolve_modes(getattr(args, "mode", None))

    # The narrative streams to stdout during this call
    print("# Scouting Report\n")
    try:
        results = run_narration_modes(
            ctx,
            modes=selected_modes,
            provider=args.provider,
            thinking=args.thinking,
            persona=args.persona,
            _model_override=model_override,
        )
    except AgentRunError as e:
        log.error("LLM call failed: %s", e)
        sys.exit(2)

    pipe_result = results["report"]
```

Update the import (:231) to `run_narration_modes` (replacing `generate_pipeline_streaming` in the `from pitcher_narratives.pipeline import (...)` group; keep `check_hallucinated_metrics`, `write_pipeline_data_file`). Leave the entire section-printing + exit block (:270-387) unchanged — with one mode it reproduces today's output and exit code exactly.

**Note (deferred to later phases):** true multi-mode output (per-mode headers, G9) and cross-mode aggregate exit (run all modes, OR residual flags, single non-zero exit — G4) are only exercised once CHANGES/RECAP exist (phases 8–9). Phase 4 registers only `report`, so the current single-result print/exit path IS the correct single-mode behavior; do not restructure it speculatively.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS — new `--mode` tests + all existing CLI tests (default path unchanged).

- [ ] **Step 5: Full-suite behavior-preservation gate**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: PASS — same green/xfail profile as before the branch (pre-existing `test_to_prompt_token_budget` fail is the only known exception, per the SDD ledger). Confirm no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat(narration): add single-mode --mode CLI scaffolding (G9/G4)"
```

---

## Self-Review

**Spec coverage (design §13 phase 4 = §4 + §6 + §11 + G4/G9/G10):**
- "refactor today's report path onto the mode" → Tasks 2–3 (`REPORT` mode owns persona→contract; pipeline threads `mode`).
- "rename CAPSULE→SCOUT_REPORT" (§11) → Task 1.
- "fold REPORT_CONTRACTS" (§11/§12) → Task 2 (retired global; `REPORT.contracts` is the single source).
- "Introduce the per-mode PipelineResult shape (G10)" → Task 4 (`run_narration_modes -> dict[str, PipelineResult]`).
- "CLI multi-mode output/exit policy scaffolding for a single mode (G4, G9)" → Task 5 (`--mode` parse/validate + dict consumption; full multi-mode header/aggregate-exit explicitly deferred, as "for a single mode" directs).
- "Behavior-preserving; characterization tests guard it" → byte-identical fixture tests (Task 1 Step 5, Task 2 Step 5) + full-suite gate (Task 5 Step 5).
- "Day-window still in force" → Global Constraints; no slicer/frame changes anywhere.

**Deferrals (documented scope decisions, not gaps):** `NarrationMode` omits `input_assembler`, `focus`, `temporal_frame`, and `validation` from §4's six-member design. Rationale: (1) YAGNI — nothing in the REPORT-only path consumes them yet; adding inert fields is dead scaffolding. (2) `input_assembler` binding `build_writer_input` (in `pipeline.py`) into a mode defined in `personas.py` would force either a `pipeline`↔`personas` import cycle or a premature module move; the assembler seam earns its keep at RECAP (phase 8), where a *second* assembler (`build_story_cue_from_context`) actually diverges. (3) `validation` (`ValidationPolicy`) is defined and wired in the shared-validation phase (§7, phase 7). (4) `temporal_frame`/`focus` become live when appearance-count frames + per-mode focus directives land (phases 5/6/9). Frozen-dataclass fields with defaults append non-breakingly, so deferral costs nothing later. **This is the one place the plan narrows §4's literal shape — flagged here for reviewer sign-off.**

**Placeholder scan:** No "TBD/handle edge cases/similar-to-Task-N". Every code step shows full code. Task 5 Step 1/3 note the one legitimate unknown (exact `cli.py` argparse seam names) and instruct reading the file to target real symbols rather than inventing them — the two required behaviors are stated concretely.

**Type consistency:** `NarrationMode(id, contracts)` is constructed identically in Task 2 and referenced as `mode.contracts`/`mode.id` in Tasks 2–5. `build_writer_system_prompt(persona, mode=REPORT)` signature matches all call sites (`make_pipeline_agents` :1315, single-arg :1079/:148). `run_narration_modes(...) -> dict[str, PipelineResult]` keyed by `mode.id` matches Task 5's `results["report"]`. `SCOUT_REPORT` replaces `CAPSULE` uniformly (Task 1 grep-guarded).

**Post-implementation:** after Task 5, update `.superpowers/sdd/progress.md` with a Phase 4 section + task ledger, and update the `project-mode-based-narration` memory (`Next: Phase 5`).
