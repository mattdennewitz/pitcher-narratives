# Validation Parity (WS4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `morning --strict` flag that runs the `check_hallucinated_metrics` cross-check per digest entry (the one terminal check morning omits vs. the report path), folds its flags into the UNVERIFIED logic, records results in `validation.json`, and stamps the digest footer `fast`/`strict` — plus fix the stale `morning.py` docstring.

**Architecture:** Morning already runs the anchor + fact-audit loops (RECAP `ValidationPolicy` depths) and value-parity via `render_recap`; the only gap is `check_hallucinated_metrics` (pure, in-process, no LLM). This adds an opt-in boolean threaded from the CLI into `run_morning`, invokes the check per entry in the existing result-assembly loop, and extends the existing footer + `validation.json` artifact. No new types, no `ValidationPolicy` changes.

**Tech Stack:** Python 3.14, pytest, `uv`.

## Global Constraints

- Python 3.14+; run everything via `uv run`.
- Tests loading pitcher data need `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` when run from this worktree.
- `--strict` is a plain boolean on the `morning` subcommand; default off. No `ValidationPolicy(0,0)`/`SKIP` sentinel, no new `ValidationPolicy` field (see spec §3.4).
- Fast mode (default): **no** `check_hallucinated_metrics` call, **no** new UNVERIFIED flags. The only default-mode output change is one added footer line `validation: fast (hallucination check skipped)`.
- Strict mode: `validation: strict` footer; runs the check per entry; not-clean → entry marked UNVERIFIED; per-entry result recorded in `validation.json`.
- `check_hallucinated_metrics(report_text: str) -> HallucinationReport` (`pipeline.py:2745`) is persona-free; `HallucinationReport` has `unknown_metrics: list[str]`, `outcome_stat_warnings: list[str]`, and `.is_clean`.
- Spec: `docs/superpowers/specs/2026-07-05-validation-parity-design.md`.

---

## File Structure

| File | Change |
|------|--------|
| `src/pitcher_narratives/morning.py` | Fix module docstring; add `strict: bool = False` to `run_morning`; import + call `check_hallucinated_metrics` per entry in the assembly loop when strict; fold into UNVERIFIED banner; footer stamp; thread hallucination results into `_build_validation_payload`. |
| `src/pitcher_narratives/cli.py` | Add `--strict` to the `morning` parser; pass `strict=args.strict` into `run_morning`. |
| `tests/test_morning.py` | Tests for fast (no call, fast stamp), strict (call, UNVERIFIED fold, strict stamp, `validation.json` record). |

Single task — the flag, its behavior, the footer, the artifact, and the docstring fix are one cohesive, independently-testable deliverable.

---

## Task 1: `morning --strict` hallucination cross-check + transparency

**Files:**
- Modify: `src/pitcher_narratives/morning.py` (docstring ~8-14; `_build_validation_payload` ~60; `run_morning` ~80; assembly loop ~170-186; footer ~202)
- Modify: `src/pitcher_narratives/cli.py` (morning parser ~146; `_run_morning_command` ~658)
- Test: `tests/test_morning.py`

**Interfaces:**
- Consumes: `check_hallucinated_metrics(report_text: str) -> HallucinationReport` and `HallucinationReport` (both from `pitcher_narratives.pipeline`).
- Produces: `run_morning(..., strict: bool = False, ...)`; `_build_validation_payload(game_date, recap_results, hallucination=None)`; digest footer line `validation: fast (hallucination check skipped)` | `validation: strict`.

- [ ] **Step 1: Fix the stale module docstring**

In `src/pitcher_narratives/morning.py`, replace the "Validation parity note" paragraph (lines ~8-14) with text that matches reality:

```python
"""Morning editorial run orchestration.

scout -> selector -> cue builder -> concurrent writers -> assembler,
with artifacts written to <out_root>/<game-date>/: digest.md,
slate.json, briefing.md, usage.json. See
docs/superpowers/specs/2026-06-12-morning-run-design.md.

Validation: each digest entry runs the full RECAP validation core via
render_recap -- the anchor-revision loop and capsule fact-audit loop at
RECAP's ValidationPolicy depths (anchor_depth=1, fact_depth=2) plus
value-parity. By default it omits only the terminal metric-hallucination
cross-check (check_hallucinated_metrics) to keep the high-volume run fast;
pass `morning --strict` to run it per entry (design: validation-parity spec).
"""
```

- [ ] **Step 2: Write the failing fast-mode test**

Add to `tests/test_morning.py`, reusing the file's existing morning harness (the same data-load/selector/`TestModel(call_tools=[])` fixtures the other `run_morning` tests use — copy that setup verbatim). This test asserts the DEFAULT path makes no hallucination call and the footer carries the fast stamp:

```python
def test_morning_fast_mode_skips_hallucination_and_stamps_footer(tmp_path, monkeypatch):
    """Default morning: no check_hallucinated_metrics call; footer says 'validation: fast'."""
    import pitcher_narratives.morning as m
    calls = []
    monkeypatch.setattr(
        m, "check_hallucinated_metrics",
        lambda text: (_ for _ in ()).throw(AssertionError("must not be called in fast mode")),
        raising=False,
    )
    run_dir = _run_morning_with_stubs(m, tmp_path, strict=False)  # helper from existing harness
    digest = (run_dir / "digest.md").read_text()
    assert "validation: fast (hallucination check skipped)" in digest
    assert "validation: strict" not in digest
```

If the file has no reusable `_run_morning_with_stubs`-style helper, build the arrangement from the nearest existing `run_morning` test in the file (same stubs) and inline it. The key assertions are the two above.

- [ ] **Step 3: Run it — fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py::test_morning_fast_mode_skips_hallucination_and_stamps_footer -v`
Expected: FAIL — `run_morning` has no `strict` kwarg (TypeError) or the footer stamp is absent.

- [ ] **Step 4: Add the `strict` param, the footer stamp, and the import**

In `morning.py`, add `check_hallucinated_metrics` to the existing `from pitcher_narratives.pipeline import (...)` block (the one importing `render_recap`, ~line 37).

Change `run_morning`'s signature to add `strict` (after `starters_only`, before the `_`-prefixed overrides):

```python
def run_morning(
    *,
    window_days: int,
    top_n: int,
    min_pitches: int,
    provider: str,
    out_root: Path,
    max_concurrency: int = 4,
    starters_only: bool = False,
    strict: bool = False,
    _selector_override: object = None,
    _writer_override: object = None,
) -> Path | None:
```

After `cost_block` is computed (currently `cost_block = tracker.render_cost_block(wall_s=wall_s)`, ~line 202, and the `if n_unverified:` note block that follows it), append the validation stamp:

```python
    cost_block += (
        "\nvalidation: strict"
        if strict
        else "\nvalidation: fast (hallucination check skipped)"
    )
```

Place this AFTER the existing `if n_unverified: cost_block += ...` block so both notes appear.

- [ ] **Step 5: Run it — passes**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py::test_morning_fast_mode_skips_hallucination_and_stamps_footer -v`
Expected: PASS.

- [ ] **Step 6: Write the failing strict-mode test**

Add to `tests/test_morning.py` (same harness). Force a hallucinated metric so the entry becomes UNVERIFIED and lands in `validation.json`:

```python
def test_morning_strict_runs_hallucination_check_and_records(tmp_path, monkeypatch):
    """--strict: runs the check per entry, marks not-clean entries UNVERIFIED, records in validation.json."""
    import json
    import pitcher_narratives.morning as m
    from pitcher_narratives.pipeline import HallucinationReport

    seen = []
    def fake_check(text):
        seen.append(text)
        return HallucinationReport(unknown_metrics=["fabricated+"], outcome_stat_warnings=[])
    monkeypatch.setattr(m, "check_hallucinated_metrics", fake_check, raising=False)

    run_dir = _run_morning_with_stubs(m, tmp_path, strict=True)  # helper from existing harness
    digest = (run_dir / "digest.md").read_text()
    assert "validation: strict" in digest
    assert seen, "check_hallucinated_metrics must run per entry in strict mode"
    assert "UNVERIFIED" in digest  # not-clean entry banner-flagged

    payload = json.loads((run_dir / "validation.json").read_text())
    # every recorded pick carries its hallucination result under strict mode
    for rec in payload["picks"].values():
        assert rec["hallucination"]["unknown_metrics"] == ["fabricated+"]
        assert rec["hallucination"]["is_clean"] is False
```

- [ ] **Step 7: Run it — fails**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py::test_morning_strict_runs_hallucination_check_and_records -v`
Expected: FAIL — check not called / no `hallucination` key in `validation.json`.

- [ ] **Step 8: Implement the strict path — check per entry, fold into UNVERIFIED, collect results**

In `morning.py`'s result-assembly loop (currently ~170-186), collect a per-pid hallucination map and fold a not-clean result into the UNVERIFIED banner. Replace the loop body so it reads:

```python
        summaries: dict[int, str] = {}
        recap_results: dict[int, PipelineResult] = {}
        hallucination_by_pid: dict[int, "HallucinationReport"] = {}
        n_unverified = 0
        for result in build_results:
            if result is None:
                continue
            pid, recap_result = result
            text = recap_result.narrative
            banner = residual_banner(recap_result, label="RECAP")
            # Deliberately louder than is_unverified(): value-parity warnings also mark an item UNVERIFIED so no ungrounded number ships silently.
            if banner is None and recap_result.value_parity_warnings:
                banner = (
                    "⚠️  RECAP UNVERIFIED — value-parity flags present; "
                    "review before use."
                )
            if strict:
                hr = check_hallucinated_metrics(recap_result.narrative)
                hallucination_by_pid[pid] = hr
                if banner is None and not hr.is_clean:
                    banner = (
                        "⚠️  RECAP UNVERIFIED — hallucinated-metric flags present; "
                        "review before use."
                    )
            if banner:
                text = f"{banner}\n\n{text}"
                n_unverified += 1
            summaries[pid] = text
            recap_results[pid] = recap_result
```

Add `hallucination_by_pid` to what `_llm_stages()` returns, and to its unpacking at the call site (`... = asyncio.run(_llm_stages())`). Then thread it into the `validation.json` write.

- [ ] **Step 9: Extend `_build_validation_payload` to record hallucination results**

Change `_build_validation_payload` (~60) to accept the map and merge a `hallucination` sub-record per pick when present:

```python
def _build_validation_payload(
    game_date: str,
    recap_results: dict[int, "PipelineResult"],
    hallucination: dict[int, "HallucinationReport"] | None = None,
) -> dict[str, object]:
    """Per-pick calibration records for validation.json.

    One ``flag_record`` per surviving pick, keyed by stringified pitcher id
    (JSON object keys must be strings). Under ``morning --strict`` each record
    also carries the per-entry metric-hallucination result.
    """
    hallucination = hallucination or {}

    def _record(pid: int, result: "PipelineResult") -> dict[str, object]:
        rec = flag_record(RECAP, pid, result, span=_DEFAULT_RECENT_APPEARANCES)
        hr = hallucination.get(pid)
        if hr is not None:
            rec["hallucination"] = {
                "unknown_metrics": hr.unknown_metrics,
                "outcome_stat_warnings": hr.outcome_stat_warnings,
                "is_clean": hr.is_clean,
            }
        return rec

    return {
        "game_date": game_date,
        "picks": {str(pid): _record(pid, result) for pid, result in recap_results.items()},
    }
```

Update the `validation.json` write call (~230) to pass the map:

```python
    (run_dir / "validation.json").write_text(json.dumps(
        _build_validation_payload(str(game_date), recap_results, hallucination_by_pid),
        indent=2,
    ))
```

(Match the existing `json.dumps(...)` arguments/indent already used at that call site.)

- [ ] **Step 10: Run the strict test — passes**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py::test_morning_strict_runs_hallucination_check_and_records -v`
Expected: PASS.

- [ ] **Step 11: Add the CLI `--strict` flag and thread it**

In `cli.py`, add to the `morning` parser (after the `--out` argument, ~line 150):

```python
    morning.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Run the metric-hallucination cross-check on every digest entry "
            "(fully validates the run, at a small per-entry cost). Off by "
            "default: the fast digest runs the anchor + fact-audit loops but "
            "skips this cross-check."
        ),
    )
```

In `_run_morning_command` (~658), pass it through:

```python
        run_dir = run_morning(
            window_days=args.window,
            top_n=args.candidates,
            min_pitches=args.min_pitches,
            provider=args.provider,
            out_root=Path(args.out),
            starters_only=args.starters_only,
            strict=args.strict,
        )
```

- [ ] **Step 12: Add a CLI flag test**

Add to `tests/test_cli.py` (argparse-level, no LLM):

```python
def test_morning_parser_accepts_strict_flag():
    from pitcher_narratives.cli import parse_args
    import sys
    argv = ["prog", "morning", "--strict"]
    old = sys.argv
    sys.argv = argv
    try:
        args = parse_args()
    finally:
        sys.argv = old
    assert args.strict is True


def test_morning_parser_strict_defaults_false():
    from pitcher_narratives.cli import parse_args
    import sys
    old = sys.argv
    sys.argv = ["prog", "morning"]
    try:
        args = parse_args()
    finally:
        sys.argv = old
    assert args.strict is False
```

(If `parse_args` reads `sys.argv` differently — e.g. takes an argv list — match the existing `test_cli.py` invocation pattern for the `morning` subcommand.)

- [ ] **Step 13: Run the full suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: PASS with only the documented pre-existing baseline failures (`test_to_prompt_token_budget`, `test_changes_trend_comparison_golden`, and the order-dependent `test_assemble_multi_frame_primary_matches_single` flake). No new failures.

- [ ] **Step 14: Commit**

```bash
git add src/pitcher_narratives/morning.py src/pitcher_narratives/cli.py tests/test_morning.py tests/test_cli.py
git commit -m "feat(morning): add --strict for the metric-hallucination cross-check

Morning already runs the anchor + fact-audit loops at RECAP depths; --strict
adds the one terminal check it omits (check_hallucinated_metrics) per entry,
folds flags into UNVERIFIED, records results in validation.json, and stamps
the digest footer fast/strict. Fixes the stale module docstring. (WS4)"
```

---

## Self-Review

**Spec coverage:**
- §3.1 `morning --strict` runs the hallucination check per entry, folds into UNVERIFIED → Steps 6-8. ✓
- §3.2 record results in `validation.json` → Step 9. ✓
- §3.3 footer stamp (both modes) + `--help` note + fix stale docstring → Steps 4, 11, 1. ✓
- §3.4 no sentinel / no `ValidationPolicy` field → honored (plain boolean). ✓
- §5 fast makes no call / no new flags; strict runs + records → Steps 2, 6. ✓

**Placeholder scan:** Steps 2/6 reuse the existing morning test harness (named explicitly, with the exact assertions that matter) rather than inventing a data fixture — the setup that varies by harness is delegated, the behavior asserted is concrete. Not a silent TODO.

**Type consistency:** `strict: bool` threads CLI → `run_morning` → loop consistently; `hallucination_by_pid: dict[int, HallucinationReport]` is produced in the loop (Step 8), returned from `_llm_stages`, and consumed by `_build_validation_payload`'s new `hallucination` param (Step 9); `HallucinationReport` fields (`unknown_metrics`, `outcome_stat_warnings`, `is_clean`) match `pipeline.py:2603`.
