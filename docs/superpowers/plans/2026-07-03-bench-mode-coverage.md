# Bench Per-Mode Coverage (Phase 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the LLM bench harness to run, capture, and judge every narration mode (REPORT / RECAP / CHANGES) instead of REPORT-only, and lock the per-mode×persona writer-prompt golden matrix in one place.

**Architecture:** `run_provider` stops calling `generate_pipeline_streaming` (single REPORT) and instead calls the production dispatcher `run_narration_modes`, capturing each mode's capsule + executive summary under namespaced tier keys (`capsule:<mode>`, `exec_summary:<mode>`) while keeping the five specialist tiers captured once (they are mode-agnostic spine-core outputs). The bench CLI gains `--mode` (comma-split + validate, mirroring `--providers`) and `--prior` (needed when CHANGES is requested). The two `tier == "capsule"` special-cases (judge-loop rubric selection, scorecard `_rubric_for`) switch to prefix detection so namespaced capsule keys resolve to `CAPSULE_RUBRIC`.

**Tech Stack:** Python 3.14, polars, pydantic-ai, pytest, `pydantic_ai.models.test.TestModel` for LLM-free runs.

## Global Constraints

- Python 3.14+ (`requires-python = ">=3.14"`); `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- No live Baseball Savant calls; static parquet + CSV only.
- Data-dependent tests need `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` when run from this worktree (gitignored `var/` data lives in the original repo). Existing data-gated bench test uses a `skipif` for absent statcast files — mirror that gate; do not un-gate.
- Pre-existing known failure: `test_to_prompt_token_budget` (2063 > 2000). It is NOT introduced by this work; do not "fix" it.
- Bench is internal tooling with **no golden output** — changing tier key names / report layout is allowed. Production narration paths (`cli`, `pipeline`, `personas`) must stay byte-identical: this plan touches only `src/pitcher_narratives/bench/**` and `tests/**`.
- Mode ids are `"report"`, `"recap"`, `"changes"`; resolve via `get_narration_mode(id)` (raises `ValueError` on unknown). `NarrationMode.id` yields the id string. `NarrationMode.temporal_frame` is a `frozenset[TemporalFrame]`; CHANGES contains `TemporalFrame.PRIOR`.

---

## File Structure

- `src/pitcher_narratives/bench/scorecard.py` — `_rubric_for(tier)` prefix detection (Task 1).
- `src/pitcher_narratives/bench/runner.py` — `run_provider` per-mode capture via `run_narration_modes` (Task 2).
- `src/pitcher_narratives/bench/__main__.py` — `--mode`/`--prior` CLI, prior-ctx wiring, judge-loop prefix skips (Task 3).
- `tests/test_bench.py` — unit tests for Tasks 1–3.
- `tests/test_personas.py` — consolidated (mode×persona) golden matrix test (Task 4).

---

## Task 1: Scorecard rubric selection tolerates namespaced capsule tiers

**Files:**
- Modify: `src/pitcher_narratives/bench/scorecard.py:38-39` (`_rubric_for`)
- Test: `tests/test_bench.py`

**Interfaces:**
- Consumes: `AGENT_RUBRIC`, `CAPSULE_RUBRIC` (already imported in `scorecard.py`).
- Produces: `_rubric_for(tier: str)` returns `CAPSULE_RUBRIC` for any tier whose colon-split head is `"capsule"` (`"capsule"`, `"capsule:report"`, `"capsule:recap"`, `"capsule:changes"`), else `AGENT_RUBRIC`. Behavior for existing `"capsule"` and `"specialist:*"` keys is unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_bench.py`:

```python
from pitcher_narratives.bench.rubric import AGENT_RUBRIC, CAPSULE_RUBRIC
from pitcher_narratives.bench.scorecard import _rubric_for


def test_rubric_for_namespaced_capsule_tiers():
    """Namespaced capsule tiers resolve to CAPSULE_RUBRIC; specialists to AGENT."""
    assert _rubric_for("capsule") is CAPSULE_RUBRIC
    assert _rubric_for("capsule:report") is CAPSULE_RUBRIC
    assert _rubric_for("capsule:recap") is CAPSULE_RUBRIC
    assert _rubric_for("capsule:changes") is CAPSULE_RUBRIC
    assert _rubric_for("specialist:stuff") is AGENT_RUBRIC
    assert _rubric_for("specialist:trends") is AGENT_RUBRIC
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench.py::test_rubric_for_namespaced_capsule_tiers -v`
Expected: FAIL — `_rubric_for("capsule:report")` returns `AGENT_RUBRIC` (assert fails).

- [ ] **Step 3: Write minimal implementation**

Replace `_rubric_for` in `src/pitcher_narratives/bench/scorecard.py`:

```python
def _rubric_for(tier: str):
    return CAPSULE_RUBRIC if tier.split(":", 1)[0] == "capsule" else AGENT_RUBRIC
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bench.py::test_rubric_for_namespaced_capsule_tiers -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/bench/scorecard.py tests/test_bench.py
git commit -m "feat(bench): rubric selection tolerates namespaced capsule tiers (P10 T1)"
```

---

## Task 2: `run_provider` captures every requested mode

**Files:**
- Modify: `src/pitcher_narratives/bench/runner.py` (imports, `run_provider` signature + body)
- Test: `tests/test_bench.py`

**Interfaces:**
- Consumes: `run_narration_modes(ctx, *, modes, provider, thinking, persona, _model_override, prior_ctx) -> dict[str, PipelineResult]` from `pitcher_narratives.pipeline`; `get_narration_mode(id) -> NarrationMode` and `REPORT` from `pitcher_narratives.personas`; `assemble_prior_context(data, recent, prior) -> PitcherContext` from `pitcher_narratives.context`; `build_writer_input`, `_flatten_prompt`, `_build_*_input` (already imported).
- Produces: `run_provider(pitcher_id, *, provider, thinking="medium", persona="scout", recent_appearances=_DEFAULT_RECENT_APPEARANCES, modes: list[NarrationMode] | None = None, prior: int = _DEFAULT_PRIOR_APPEARANCES, _model_override=None) -> CapturedRun`. `modes=None` defaults to `[REPORT]`. `CapturedRun.outputs` keys: `specialist:{stuff,location,runvalue,trends,game_shape}` (from the first captured mode's result), plus per mode `capsule:{mode.id}` and, when non-empty, `exec_summary:{mode.id}`. `CapturedRun.ground_truths` carries a matching key for every output key.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_bench.py` (near the existing `test_run_provider_captures_all_tiers`, reuse its `TEST_PITCHER` constant). The existing test guards with an **inline** decorator — copy it verbatim onto the new test (there is no named alias):

```python
@pytest.mark.skipif(
    not __import__("pitcher_narratives.data", fromlist=["statcast_parquet_path"]).statcast_parquet_path(2026).exists(),
    reason="statcast parquet files not present (set STATCAST_PATH)",
)
def test_run_provider_captures_per_mode_capsules():
    """A multi-mode run captures a namespaced capsule + exec summary per mode
    and one shared set of specialist tiers, each with a ground truth."""
    from pitcher_narratives.personas import get_narration_mode

    modes = [get_narration_mode("report"), get_narration_mode("recap")]
    captured = run_provider(
        TEST_PITCHER, provider="gemini", thinking="low", persona="scout",
        modes=modes, _model_override=TestModel(call_tools=[]),
    )
    assert captured.ok
    for spec in ("specialist:stuff", "specialist:location", "specialist:runvalue",
                 "specialist:trends", "specialist:game_shape"):
        assert captured.outputs[spec]
        assert captured.ground_truths.get(spec), f"missing ground truth for {spec}"
    for mode_id in ("report", "recap"):
        cap = f"capsule:{mode_id}"
        assert captured.outputs.get(cap), f"missing {cap}"
        assert "Specialist Analysis" in captured.ground_truths[cap]
    # No bare "capsule" key survives the namespacing.
    assert "capsule" not in captured.outputs
```

Also update the existing `test_run_provider_captures_all_tiers` so its capsule assertions use the namespaced key (default single-mode run now emits `capsule:report`):

```python
    for key in ("specialist:stuff", "specialist:location", "specialist:runvalue",
                "specialist:trends", "specialist:game_shape", "capsule:report"):
        assert key in captured.outputs, f"missing {key}"
        assert captured.outputs[key]
        assert captured.ground_truths.get(key), f"missing ground truth for {key}"
    assert "Arsenal Physical Profile" in captured.ground_truths["specialist:stuff"]
    assert "Specialist Analysis" in captured.ground_truths["capsule:report"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest "tests/test_bench.py::test_run_provider_captures_per_mode_capsules" "tests/test_bench.py::test_run_provider_captures_all_tiers" -v`
Expected: FAIL — `run_provider` has no `modes` kwarg / emits `"capsule"` not `"capsule:report"`.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/bench/runner.py`, replace the imports block and `run_provider`. Update the `from pitcher_narratives.pipeline import (...)` to drop `generate_pipeline_streaming` and add nothing there; add these imports at module top:

```python
from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context
from pitcher_narratives.personas import REPORT, NarrationMode
from pitcher_narratives.pipeline import (
    _build_game_shape_input,
    _build_location_input,
    _build_runvalue_input,
    _build_stuff_input,
    _build_trend_input,
    _flatten_prompt,
    build_writer_input,
    run_narration_modes,
)
from pitcher_narratives.temporal import (
    _DEFAULT_PRIOR_APPEARANCES,
    _DEFAULT_RECENT_APPEARANCES,
    TemporalFrame,
)
```

Then rewrite `run_provider`:

```python
def run_provider(
    pitcher_id: int,
    *,
    provider: str,
    thinking: str = "medium",
    persona: str = "scout",
    recent_appearances: int = _DEFAULT_RECENT_APPEARANCES,
    modes: list[NarrationMode] | None = None,
    prior: int = _DEFAULT_PRIOR_APPEARANCES,
    _model_override: object = None,
) -> CapturedRun:
    """Run the pipeline for one provider across every requested mode.

    Each mode's capsule and executive summary are captured under
    namespaced tier keys (``capsule:<id>``, ``exec_summary:<id>``); the
    five specialist tiers are captured once (they are mode-agnostic
    spine-core outputs). A failed run is returned as ok=False.
    """
    selected = modes if modes is not None else [REPORT]
    data = load_pitcher_data(pitcher_id, recent_appearances=recent_appearances)
    ctx = assemble_pitcher_context(data)
    ground_truth = ctx.to_prompt()

    needs_prior = any(TemporalFrame.PRIOR in m.temporal_frame for m in selected)
    prior_ctx = (
        assemble_prior_context(data, recent_appearances, prior) if needs_prior else None
    )

    start = time.monotonic()
    try:
        results = run_narration_modes(
            ctx,
            modes=selected,
            provider=provider,
            thinking=thinking,  # type: ignore[arg-type]
            persona=persona,
            _model_override=_model_override,
            prior_ctx=prior_ctx,
        )
    except Exception as exc:  # noqa: BLE001 -- a provider failure must not kill the bench
        log.error("bench: %s run failed: %s", provider, exc)
        return CapturedRun(
            provider=provider,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            wall_s=time.monotonic() - start,
            ground_truth=ground_truth,
            pitcher_name=data.pitcher_name,
        )
    wall_s = time.monotonic() - start

    # Specialist tiers are mode-agnostic; capture them once from the first
    # result. Their ground truths are deterministic functions of ctx.
    first = next(iter(results.values()))
    outputs = {
        "specialist:stuff": first.specialists.stuff,
        "specialist:location": first.specialists.location,
        "specialist:runvalue": first.specialists.runvalue,
        "specialist:trends": first.specialists.trends,
        "specialist:game_shape": first.specialists.game_shape,
    }
    ground_truths = {
        "specialist:stuff": _flatten_prompt(_build_stuff_input(ctx)),
        "specialist:location": _flatten_prompt(_build_location_input(ctx)),
        "specialist:runvalue": _flatten_prompt(_build_runvalue_input(ctx)),
        "specialist:trends": _flatten_prompt(_build_trend_input(ctx)),
        "specialist:game_shape": _flatten_prompt(_build_game_shape_input(ctx)),
    }

    # Per-mode capsule + exec summary. The writer-input ground truth is
    # rebuilt from THAT mode's specialists + key signals.
    for mode_id, result in results.items():
        writer_input = build_writer_input(
            ctx,
            result.specialists.stuff,
            result.specialists.location,
            result.specialists.runvalue,
            result.specialists.trends,
            result.specialists.game_shape,
            key_signals=result.key_signals,
        )
        outputs[f"capsule:{mode_id}"] = result.narrative
        ground_truths[f"capsule:{mode_id}"] = writer_input
        if result.executive_summary:
            outputs[f"exec_summary:{mode_id}"] = "\n".join(
                f"- {b}" for b in result.executive_summary
            )
            ground_truths[f"exec_summary:{mode_id}"] = writer_input

    return CapturedRun(
        provider=provider,
        ok=True,
        error=None,
        wall_s=wall_s,
        ground_truth=ground_truth,
        outputs=outputs,
        ground_truths=ground_truths,
        pitcher_name=data.pitcher_name,
    )
```

Note: keep the existing `load_pitcher_data` import; only the pipeline-import list and top-of-file imports change as shown. Verify `assemble_prior_context` and `_DEFAULT_PRIOR_APPEARANCES` exist at those paths before relying on them (`grep -n "def assemble_prior_context" src/pitcher_narratives/context.py`; `grep -n "_DEFAULT_PRIOR_APPEARANCES" src/pitcher_narratives/temporal.py`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest "tests/test_bench.py::test_run_provider_captures_per_mode_capsules" "tests/test_bench.py::test_run_provider_captures_all_tiers" -v`
Expected: PASS (or SKIP if statcast data absent — if skipped, note it and rely on the Task 4 full-suite run in the data dir).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/bench/runner.py tests/test_bench.py
git commit -m "feat(bench): run_provider captures every requested mode (P10 T2)"
```

---

## Task 3: Bench CLI `--mode` / `--prior` and per-mode judging

**Files:**
- Modify: `src/pitcher_narratives/bench/__main__.py` (`parse_args`, `main` generate + judge loop + meta)
- Test: `tests/test_bench.py`

**Interfaces:**
- Consumes: `get_narration_mode(id)` from `pitcher_narratives.personas`; `_DEFAULT_PRIOR_APPEARANCES` from `pitcher_narratives.temporal`; `run_provider(..., modes=..., prior=...)` from Task 2.
- Produces: `parse_args()` yields `args.mode` (default `"report"`) and `args.prior` (default `_DEFAULT_PRIOR_APPEARANCES`). `main()` resolves modes with a local helper `_resolve_bench_modes(raw: str) -> list[NarrationMode]` that comma-splits, validates via `get_narration_mode`, and `sys.exit(2)` on unknown id or empty result. The judge loop skips any tier whose colon-split head is `"exec_summary"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bench.py`:

```python
def test_parse_args_mode_and_prior_defaults(monkeypatch):
    import sys as _sys

    from pitcher_narratives.temporal import _DEFAULT_PRIOR_APPEARANCES

    monkeypatch.setattr(_sys, "argv", ["bench", "-p", "693433"])
    args = parse_args()
    assert args.mode == "report"
    assert args.prior == _DEFAULT_PRIOR_APPEARANCES


def test_parse_args_accepts_comma_mode(monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys, "argv", ["bench", "-p", "693433", "--mode", "report,recap"])
    args = parse_args()
    assert args.mode == "report,recap"


def test_resolve_bench_modes_valid_and_invalid():
    from pitcher_narratives.bench.__main__ import _resolve_bench_modes

    modes = _resolve_bench_modes("report,changes")
    assert [m.id for m in modes] == ["report", "changes"]
    with pytest.raises(SystemExit) as exc:
        _resolve_bench_modes("bogus")
    assert exc.value.code == 2
    with pytest.raises(SystemExit):
        _resolve_bench_modes(" , ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest "tests/test_bench.py::test_parse_args_mode_and_prior_defaults" "tests/test_bench.py::test_parse_args_accepts_comma_mode" "tests/test_bench.py::test_resolve_bench_modes_valid_and_invalid" -v`
Expected: FAIL — `args.mode`/`args.prior` and `_resolve_bench_modes` do not exist.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/bench/__main__.py`:

Add imports near the top:

```python
from pitcher_narratives.personas import NarrationMode, get_narration_mode
from pitcher_narratives.temporal import _DEFAULT_PRIOR_APPEARANCES
```

In `parse_args`, add before the `--out` argument:

```python
    parser.add_argument(
        "--mode",
        default="report",
        help="Comma-separated narration modes to bench (report,recap,changes)",
    )
    parser.add_argument(
        "--prior",
        type=int,
        default=_DEFAULT_PRIOR_APPEARANCES,
        help="Prior-window appearances for CHANGES mode",
    )
```

Add a module-level helper (above `main`):

```python
def _resolve_bench_modes(raw: str) -> list[NarrationMode]:
    """Parse --mode into NarrationMode instances; exit(2) on bad input."""
    ids = [m.strip() for m in raw.split(",") if m.strip()]
    if not ids:
        print("--mode was empty; expected comma-separated mode id(s).", file=sys.stderr)
        sys.exit(2)
    modes = []
    for mode_id in ids:
        try:
            modes.append(get_narration_mode(mode_id))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
    return modes
```

In `main`, after the provider/judge validation block, resolve modes:

```python
    modes = _resolve_bench_modes(args.mode)
```

Update BOTH `run_provider(...)` calls in the generate loop to pass modes + prior:

```python
        run = run_provider(
            args.pitcher,
            provider=provider,
            thinking=args.thinking,
            persona=args.persona,
            recent_appearances=args.recent,
            modes=modes,
            prior=args.prior,
        )
```

(apply the same four added kwargs to the retry call).

In the judge loop, replace the exec-summary skip with prefix detection:

```python
            if tier.split(":", 1)[0] == "exec_summary":
                continue
            rubric = CAPSULE_RUBRIC if tier.split(":", 1)[0] == "capsule" else AGENT_RUBRIC
```

Add modes to `meta`:

```python
        "modes": ", ".join(m.id for m in modes),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest "tests/test_bench.py::test_parse_args_mode_and_prior_defaults" "tests/test_bench.py::test_parse_args_accepts_comma_mode" "tests/test_bench.py::test_resolve_bench_modes_valid_and_invalid" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/bench/__main__.py tests/test_bench.py
git commit -m "feat(bench): --mode/--prior CLI and per-mode judging (P10 T3)"
```

---

## Task 4: Lock the (mode × persona) writer-prompt golden matrix + full-suite wrap-up

**Files:**
- Modify: `tests/test_personas.py` (add one consolidated parametrized golden test)
- Test: same file

**Interfaces:**
- Consumes: `build_writer_system_prompt(persona, mode)` and `get_persona`, `get_narration_mode` from `pitcher_narratives.personas`; fixtures in `tests/fixtures/`. The three report goldens are named `writer_prompt_{persona}.txt`; recap `recap_writer_prompt_{persona}.txt`; changes `changes_writer_prompt_{persona}.txt`.
- Produces: `test_writer_prompt_golden_matrix[mode-persona]` asserting all 3×3 composed writer prompts equal their on-disk goldens — a single failure surface that catches any future mode/persona that ships without a golden.

Context: G13 (per-mode×persona goldens) is already satisfied by `test_recap_writer_prompt_golden`, `test_changes_writer_prompt_golden`, and the report `writer_prompt_*` assertions. This task adds ONE consolidated matrix test so the mode axis is explicit and future-proof; it must agree byte-for-byte with the existing per-mode tests (no new fixtures).

- [ ] **Step 1: Write the test (expected to pass immediately — goldens exist)**

Add to `tests/test_personas.py`:

```python
_MODE_FIXTURE_PREFIX = {"report": "writer_prompt", "recap": "recap_writer_prompt",
                        "changes": "changes_writer_prompt"}


@pytest.mark.parametrize("mode_id", ["report", "recap", "changes"])
@pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
def test_writer_prompt_golden_matrix(mode_id, persona_id):
    """Every (mode, persona) writer prompt matches its committed golden."""
    prompt = build_writer_system_prompt(get_persona(persona_id), get_narration_mode(mode_id))
    fixture = _FIXTURES / f"{_MODE_FIXTURE_PREFIX[mode_id]}_{persona_id}.txt"
    assert fixture.exists(), f"missing golden {fixture}"
    assert prompt == fixture.read_text()
```

(`_FIXTURES = Path(__file__).parent / "fixtures"` already exists in the file; reuse it. Confirm `get_narration_mode` is imported — it is, per the existing imports.)

- [ ] **Step 2: Run the matrix test**

Run: `uv run pytest "tests/test_personas.py::test_writer_prompt_golden_matrix" -v`
Expected: 9 PASS. If any FAILS, the composed prompt diverged from a committed golden — investigate whether an earlier phase changed a writer prompt without regenerating its fixture; do NOT blindly overwrite the golden.

- [ ] **Step 3: Run the full suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: all pass except the single pre-existing `test_to_prompt_token_budget` failure. Any data-gated bench test should now execute (not skip) under the data dir and pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_personas.py
git commit -m "test(bench): lock mode×persona writer-prompt golden matrix (P10 T4)"
```

---

## Self-Review

**Spec coverage (§13.10 / G12 / G13):**
- G12 "add per-mode capsules + ground truths" → Task 2 (`capsule:<id>` + `exec_summary:<id>` + per-mode writer-input ground truths). ✓
- G12 "a `--mode` on bench" → Task 3 (`--mode` comma-split + validate; `--prior` for CHANGES). ✓
- G12 rubric/judging fitting per-mode capsule keys → Task 1 (`_rubric_for` prefix) + Task 3 (judge-loop rubric + exec-summary skip prefix). ✓
- G13 "per-mode×persona goldens" → already present; Task 4 consolidates + future-proofs. ✓
- §11 Calibrate is a SEPARATE downstream phase (uses instrumented runs); explicitly out of scope here.

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**Type consistency:** `modes: list[NarrationMode] | None` and `prior: int` are used identically in Task 2 (definition) and Task 3 (call sites). Tier-head detection uses `tier.split(":", 1)[0]` consistently in Tasks 1 and 3. `_resolve_bench_modes` returns `list[NarrationMode]` (Task 3) matching `run_provider`'s `modes` param (Task 2). ✓

**Risk:** RECAP via `run_narration_modes` uses the CLI dispatch path (no editorial overlay; RECAP validation depths) — this matches what `--mode recap` users receive, which is the correct bench target (morning's `render_recap` overlay path is not the mode-CLI surface). Noted so a reviewer does not flag the overlay absence as a bug.
