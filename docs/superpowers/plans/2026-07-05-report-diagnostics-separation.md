# Report / Diagnostics Separation (WS2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `report` stdout the reader document only — the final capsule printed exactly once, with the QA/diagnostics appendix moved off stdout to `-v` (stderr) and an optional `--diagnostics-file` JSON sidecar.

**Architecture:** Stop streaming the capsule to stdout during generation (the pipeline already buffers the writer output); print the final post-revision `narrative` once from the CLI. Extract the diagnostics appendix into pure `build_diagnostics_dict` / `render_diagnostics_text` helpers, then route them off the reader stream. No pipeline analysis logic changes — this is streaming + rendering + routing.

**Tech Stack:** Python 3.14, argparse, pytest, `uv`.

## Global Constraints

- Python **3.14+**; run everything via `uv run` (e.g. `uv run pytest`).
- In this worktree, data-backed subprocess tests need `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` in the environment. Set it for any `uv run pytest` that runs the `report` subprocess integration tests.
- `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE_CASE` constants; no bare `except:`.
- **Decision (2026-07-05): buffer, no live streaming.** The capsule is not streamed live; the final capsule prints once to stdout.
- **Decision (2026-07-05): both diagnostics sinks.** `-v/--verbose` prints the human-readable diagnostics block to **stderr**; `--diagnostics-file PATH` writes a structured JSON sidecar. Default stdout carries no diagnostics.
- The `**Verification:**` stamp stays in the reader document (stdout). The `UNVERIFIED` banner stays on stderr and the non-zero exit code is unchanged (CI contract).
- Reader-facing stdout sections stay: `# <mode.title>`, the capsule, `## Executive Summary` + `## Brief` (when `mode.distill`), `**Verification:**`.
- Branch: `worktree-report-cleanup` (already checked out).

---

### Task 1: Buffer the capsule — print it once, drop live streaming

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (`_render_capsule` ~2262-2306; `render_recap` call ~2464-2469; `_run_pipeline` call ~2518-2523)
- Modify: `src/pitcher_narratives/cli.py` (`_emit_mode_result` capsule block ~303-312; fact-check references ~367,374)
- Test: `tests/test_cli.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: `_render_capsule(...)` with **no `stream` parameter** (always buffers via `agents.writer.run`). `_emit_mode_result` prints `pipe_result.narrative` once at the top of the mode block.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (near the other `_emit_mode_result` unit tests, ~line 840):

```python
def test_emit_prints_capsule_once_and_no_corrected_section(capsys):
    """The final narrative prints exactly once; no separate 'Corrected Capsule'."""
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT
    from pitcher_narratives.pipeline import PipelineResult, SpecialistOutputs

    result = PipelineResult(
        narrative="THE FINAL CAPSULE BODY",
        specialists=SpecialistOutputs(
            stuff="s", location="", runvalue="", trends="", game_shape=""
        ),
        capsule_revised=True,  # previously triggered a second '## Corrected Capsule'
    )
    _emit_mode_result(result, persona="scout", mode=REPORT)
    out = capsys.readouterr().out
    assert out.count("THE FINAL CAPSULE BODY") == 1
    assert "Corrected Capsule" not in out
```

Add to `tests/test_pipeline.py` (a structural guard that streaming is gone):

```python
def test_render_capsule_has_no_stream_parameter():
    """WS2: the report path buffers the writer output — no live streaming."""
    import inspect

    from pitcher_narratives.pipeline import _render_capsule

    assert "stream" not in inspect.signature(_render_capsule).parameters
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_emit_prints_capsule_once_and_no_corrected_section tests/test_pipeline.py::test_render_capsule_has_no_stream_parameter -q`
Expected: both FAIL — the emit test finds "Corrected Capsule" / no narrative printed; the signature test finds a `stream` parameter.

- [ ] **Step 3: Remove streaming from the pipeline**

In `src/pitcher_narratives/pipeline.py`, edit `_render_capsule`:

Remove the `stream: bool,` line from its parameter list (currently line 2269).

Update the docstring line 2277 from:
```python
    the recap render. Report streams (stream=True); recap does not. ``overlay``
```
to:
```python
    the recap render. Both buffer the writer output (no live streaming). ``overlay``
```

Replace the streaming block (currently lines 2295-2305):
```python
    if stream:
        async with agents.writer.run_stream(**writer_kwargs) as stream_ctx:
            chunks: list[str] = []
            async for delta in stream_ctx.stream_text(delta=True):
                print(delta, end="", flush=True)
                chunks.append(delta)
        print()
        capsule = "".join(chunks)
    else:
        _res = await agents.writer.run(**writer_kwargs)
        capsule = _res.output
```
with:
```python
    _res = await agents.writer.run(**writer_kwargs)
    capsule = _res.output
```

In `_run_pipeline`, remove the `stream=True,` argument from its `_render_capsule(...)` call (currently line 2522).

In `render_recap`, remove the `stream=False,` argument from its `_render_capsule(...)` call (currently line 2468).

- [ ] **Step 4: Print the capsule once from the CLI**

In `src/pitcher_narratives/cli.py`, in `_emit_mode_result`, replace the "Corrected capsule" block (currently lines 303-312):
```python
    # Corrected capsule — the streamed text above is the pre-correction draft
    # whenever fact-revision fired. Never let the headline text be the stale
    # one: print the verified capsule as the authoritative version.
    if pipe_result.capsule_revised and pipe_result.narrative:
        print("\n\n## Corrected Capsule\n")
        print(
            "_The streamed text above is the pre-correction draft; this is the "
            "fact-revised capsule._\n"
        )
        print(pipe_result.narrative)
```
with:
```python
    # The capsule — the final, post-fact-revision narrative, printed exactly
    # once. The pipeline buffers the writer output (no live streaming), so this
    # is the single authoritative copy under the mode's H1 title.
    if pipe_result.narrative:
        print(pipe_result.narrative)
    else:
        print("_No capsule was produced._")
```

Still in `_emit_mode_result`, the Capsule Fact-Check text references a now-removed section. Update the two strings (currently lines 366-367 and 373-374):
- Change `"...corrected them and the re-audit is clean. (See the Corrected Capsule section above.)"` to `"...corrected them and the re-audit is clean."`
- Change `f"Auditor revised the report, but {n} issue(s) remain after re-audit (see the Corrected Capsule section above):"` to `f"Auditor revised the report, but {n} issue(s) remain after re-audit:"`

- [ ] **Step 5: Run tests to verify they pass**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py tests/test_pipeline.py -q`
Expected: PASS — including the two new tests and the existing report integration tests (`test_cli_produces_report`, `test_cli_narrative_output_has_required_sections`, etc. — diagnostics are still on stdout at this point, so their assertions hold).

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/pipeline.py src/pitcher_narratives/cli.py tests/test_cli.py tests/test_pipeline.py
git commit -m "feat(report): buffer the capsule and print it once (no live streaming)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Extract pure diagnostics renderers (behavior-preserving)

**Files:**
- Modify: `src/pitcher_narratives/cli.py` (add `build_diagnostics_dict`, `render_diagnostics_text`; rewrite the diagnostics tail of `_emit_mode_result` ~344-424 to delegate)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `build_diagnostics_dict(pipe_result, persona: str) -> dict` — pure; runs the hallucination guard (only when `narrative` is non-empty) and returns all QA data as a JSON-serializable dict.
  - `render_diagnostics_text(diag: dict) -> str` — pure; formats the dict as the markdown diagnostics appendix.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def _diag_pipe_result(*, narrative="cap", revised=False, fact_flags=0):
    from pitcher_narratives.pipeline import AuditFlag, PipelineResult, SpecialistOutputs

    flags = [
        AuditFlag(category="velocity", specialist="stuff", claim=f"c{i}",
                  data_shows="d", suggested_fix="")
        for i in range(fact_flags)
    ]
    return PipelineResult(
        narrative=narrative,
        specialists=SpecialistOutputs(
            stuff="STUFF-TEXT", location="", runvalue="", trends="", game_shape=""
        ),
        capsule_revised=revised,
        capsule_audit_flags=flags,
    )


def test_build_diagnostics_dict_shape():
    from pitcher_narratives.cli import build_diagnostics_dict

    diag = build_diagnostics_dict(_diag_pipe_result(fact_flags=2, revised=True), "scout")
    assert diag["verified"] is False  # residual fact flags → unverified
    assert diag["capsule_revised"] is True
    assert diag["stuff_analysis"] == "STUFF-TEXT"
    assert len(diag["capsule_fact_check"]) == 2
    assert diag["hallucination"] == {"unknown_metrics": [], "outcome_stat_warnings": []}


def test_build_diagnostics_dict_skips_guard_on_empty_narrative(monkeypatch):
    """No hallucination guard call when there's nothing to check."""
    from pitcher_narratives import pipeline as pipeline_module
    from pitcher_narratives.cli import build_diagnostics_dict

    calls = []
    monkeypatch.setattr(
        pipeline_module, "check_hallucinated_metrics",
        lambda text, *, persona=None: calls.append(text)
        or pipeline_module.HallucinationReport(unknown_metrics=[], outcome_stat_warnings=[]),
    )
    build_diagnostics_dict(_diag_pipe_result(narrative=""), "scout")
    assert calls == []


def test_render_diagnostics_text_has_sections():
    from pitcher_narratives.cli import build_diagnostics_dict, render_diagnostics_text

    text = render_diagnostics_text(build_diagnostics_dict(_diag_pipe_result(), "scout"))
    assert "## Diagnostics" in text
    assert "### Stuff Analysis" in text
    assert "### Data Audit" in text
    assert "### Capsule Fact-Check" in text
    assert "### Anchor Check" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k diagnostics_dict -q`
Expected: FAIL — `cannot import name 'build_diagnostics_dict'`.

- [ ] **Step 3: Add the pure helpers**

In `src/pitcher_narratives/cli.py`, add these two functions immediately above `_emit_mode_result`:

```python
def build_diagnostics_dict(pipe_result, persona: str) -> dict:
    """Collect a mode's QA/diagnostics data into a JSON-serializable dict.

    Runs the hallucination guard (only when the narrative is non-empty, matching
    the historical behavior). Pure apart from that read-only guard call.
    """
    from pitcher_narratives.pipeline import check_hallucinated_metrics, is_unverified

    diag = {
        "verified": not is_unverified(pipe_result),
        "capsule_revised": pipe_result.capsule_revised,
        "revision_count": pipe_result.revision_count,
        "stuff_analysis": pipe_result.specialists.stuff,
        "data_audit": [
            {"category": f.category, "specialist": f.specialist,
             "claim": f.claim, "data_shows": f.data_shows}
            for f in pipe_result.audit_flags
        ],
        "capsule_fact_check": [
            {"category": f.category, "claim": f.claim, "data_shows": f.data_shows}
            for f in pipe_result.capsule_audit_flags
        ],
        "anchor_warnings": [
            {"category": w.category, "description": w.description}
            for w in pipe_result.anchor_warnings
        ],
        "value_parity_warnings": list(pipe_result.value_parity_warnings),
        "hallucination": {"unknown_metrics": [], "outcome_stat_warnings": []},
    }
    if pipe_result.narrative:
        hr = check_hallucinated_metrics(pipe_result.narrative, persona=persona)
        diag["hallucination"] = {
            "unknown_metrics": list(hr.unknown_metrics),
            "outcome_stat_warnings": list(hr.outcome_stat_warnings),
        }
    return diag


def render_diagnostics_text(diag: dict) -> str:
    """Format a diagnostics dict as the markdown QA appendix."""
    lines = ["## Diagnostics", "", "### Stuff Analysis", "", diag["stuff_analysis"]]

    lines += ["", "### Data Audit", ""]
    if diag["data_audit"]:
        for f in diag["data_audit"]:
            lines.append(f"- **[{f['category']}]** {f['specialist']}: {f['claim']}")
            lines.append(f"  - Data shows: {f['data_shows']}")
    else:
        lines.append("Clean — no issues found.")

    lines += ["", "### Capsule Fact-Check", ""]
    if diag["capsule_revised"] and not diag["capsule_fact_check"]:
        lines.append(
            "Auditor flagged issue(s); the fact-revision corrected them and the "
            "re-audit is clean."
        )
    elif diag["capsule_fact_check"]:
        n = len(diag["capsule_fact_check"])
        if diag["capsule_revised"]:
            lines.append(
                f"Auditor revised the report, but {n} issue(s) remain after re-audit:"
            )
        else:
            lines.append(f"Auditor flagged {n} issue(s) (not auto-corrected):")
        for f in diag["capsule_fact_check"]:
            lines.append(f"- **[{f['category']}]** {f['claim']}")
            lines.append(f"  - Data shows: {f['data_shows']}")
    else:
        lines.append("Clean — no factual issues found.")

    if diag["value_parity_warnings"]:
        lines += ["", "### Value Parity (advisory)", "",
                  "Report numbers with no match in the source data:"]
        for w in diag["value_parity_warnings"]:
            lines.append(f"- {w}")

    lines += ["", "### Anchor Check", ""]
    if diag["revision_count"] == 0 and not diag["anchor_warnings"]:
        lines.append("Passed on first draft.")
    elif diag["anchor_warnings"]:
        lines.append(f"Revised {diag['revision_count']} time(s) — remaining issues:")
        for w in diag["anchor_warnings"]:
            lines.append(f"- **[{w['category']}]** {w['description']}")
    else:
        lines.append(f"Revised {diag['revision_count']} time(s) — passed.")

    hall = diag["hallucination"]
    if hall["unknown_metrics"] or hall["outcome_stat_warnings"]:
        lines += ["", "### Hallucination Check", ""]
        if hall["unknown_metrics"]:
            lines.append(
                f"Unknown metrics referenced: {', '.join(hall['unknown_metrics'])}"
            )
        if hall["outcome_stat_warnings"]:
            lines.append(
                "Traditional outcome stats referenced (prompt warns against these): "
                f"{', '.join(hall['outcome_stat_warnings'])}"
            )

    return "\n".join(lines)
```

- [ ] **Step 4: Delegate from `_emit_mode_result` (still to stdout)**

In `_emit_mode_result`, replace the entire diagnostics tail — from the comment `# ── Diagnostics appendix ──...` (currently line 344) through the final `return unverified` (currently line 424) — with:

```python
    # ── Diagnostics appendix (still on stdout in this step) ──────────────
    diag = build_diagnostics_dict(pipe_result, persona)
    print("\n\n---\n")
    print(render_diagnostics_text(diag))

    # Empty narrative → the pipeline produced nothing to verify; never
    # soft-block on it, regardless of residual flags. This preserves the
    # pre-WS2 early-return contract (test_emit_mode_result_empty_narrative_...).
    return unverified if pipe_result.narrative else False
```

(The hallucination guard now runs inside `build_diagnostics_dict`. **Important:** `is_unverified` returns `True` for an empty narrative that carries residual `capsule_audit_flags`, so the `if pipe_result.narrative else False` gate above is required — without it, `test_emit_mode_result_empty_narrative_is_not_unverified` fails. The `unverified` variable computed earlier at line ~316 still drives the printed `**Verification:**` stamp exactly as before.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py -q`
Expected: PASS — new diagnostics tests plus the existing integration tests that assert `## Diagnostics` / `### Stuff Analysis` / `### Anchor Check` on stdout (still emitted here), and `test_emit_mode_result_runs_hallucination_guard_for_any_mode` (the guard still runs once per `_emit_mode_result` via `build_diagnostics_dict`).

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "refactor(report): extract pure build_diagnostics_dict + render_diagnostics_text

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Route diagnostics off stdout (`-v` stderr + `--diagnostics-file` JSON)

**Files:**
- Modify: `src/pitcher_narratives/cli.py` (add `--diagnostics-file` arg ~107; `_emit_mode_result` signature + return; add `_write_diagnostics_file`; mode loop in `_run_report_command` ~562-589)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_diagnostics_dict`, `render_diagnostics_text` (Task 2).
- Produces:
  - `_emit_mode_result(pipe_result, *, persona, mode, verbose=False) -> tuple[bool, dict]` — prints the reader document to stdout; prints diagnostics to **stderr** only when `verbose`; returns `(unverified, diagnostics_dict)`.
  - `_write_diagnostics_file(path, diagnostics_by_mode: dict) -> None`.
  - `report --diagnostics-file PATH`.

- [ ] **Step 1: Write the failing tests**

Add the `--diagnostics-file` parse test and update the direct-call tests. In `tests/test_cli.py`:

```python
def test_report_parse_diagnostics_file(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "report", "-p", "1", "--diagnostics-file", "d.json"])
    args = parse_args()
    assert args.diagnostics_file == "d.json"


def test_report_diagnostics_file_default_none(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "report", "-p", "1"])
    args = parse_args()
    assert args.diagnostics_file is None


def test_emit_default_stdout_has_no_diagnostics(capsys):
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    _emit_mode_result(_diag_pipe_result(), persona="scout", mode=REPORT, verbose=False)
    captured = capsys.readouterr()
    assert "## Diagnostics" not in captured.out
    assert "## Diagnostics" not in captured.err  # not verbose → nowhere


def test_emit_verbose_puts_diagnostics_on_stderr(capsys):
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    _emit_mode_result(_diag_pipe_result(), persona="scout", mode=REPORT, verbose=True)
    captured = capsys.readouterr()
    assert "## Diagnostics" not in captured.out
    assert "## Diagnostics" in captured.err
    assert "### Anchor Check" in captured.err


def test_emit_returns_unverified_and_diag_dict(capsys):
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    unverified, diag = _emit_mode_result(
        _diag_pipe_result(fact_flags=2), persona="scout", mode=REPORT
    )
    capsys.readouterr()
    assert unverified is True
    assert isinstance(diag, dict) and "verified" in diag
```

Update the two existing direct-call tests to unpack the tuple:
- `test_emit_mode_result_returns_unverified_status` (currently line 849-850): change to
  ```python
      assert _emit_mode_result(clean, persona="scout", mode=REPORT)[0] is False
      assert _emit_mode_result(flagged, persona="scout", mode=REPORT)[0] is True
  ```
- `test_emit_mode_result_empty_narrative_is_not_unverified` (currently line 877): change to
  ```python
      assert _emit_mode_result(result, persona="scout", mode=REPORT)[0] is False
  ```
(`test_emit_mode_result_runs_hallucination_guard_for_any_mode` needs no change — it calls `_emit_mode_result` and only inspects the guard spy, which still fires once via `build_diagnostics_dict`.)

Update the four integration tests that assert diagnostics on stdout:
- `test_cli_anchor_check_in_output` (line 326): add `-v` to the argv and assert on **stderr**:
  ```python
      [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155", "-v"],
      ...
      assert "### Anchor Check" in result.stderr
      assert "### Anchor Check" not in result.stdout
  ```
- `test_cli_narrative_output_has_required_sections` (line 339): keep the reader-section asserts on stdout, move the diagnostics asserts to stderr under `-v`, and assert stdout has NO diagnostics. Replace the body's argv with `... "-p", "592155", "-v"` and replace lines 356-368 with:
  ```python
      stdout = "\n" + result.stdout
      stderr = "\n" + result.stderr

      assert "\n# Scouting Report\n" in stdout
      assert "\n**Verification:**" in stdout
      assert "\n## Executive Summary\n" in stdout
      assert "\n## Brief\n" in stdout
      assert "\n## Diagnostics\n" not in stdout       # off the reader stream
      assert "\n## Diagnostics\n" in stderr            # -v surfaces it
      assert "\n### Stuff Analysis\n" in stderr
      assert "\n### Data Audit\n" in stderr
      assert "\n### Capsule Fact-Check\n" in stderr
      assert "\n### Anchor Check\n" in stderr
  ```
  Also update the docstring's item 1 to "buffered capsule" and item 5 to "## Diagnostics (stderr, under -v)".
- `test_cli_mode_blocks_are_labeled_and_contiguous` (line 371): the reader H1 blocks stay on stdout; the diagnostics move to stderr. Replace lines 381-387 with:
  ```python
      stdout = result.stdout
      i_report = stdout.index("# Scouting Report")
      i_changes = stdout.index("# Change Report")
      assert i_report < i_changes
      assert "## Diagnostics" not in stdout
      # Add -v to the argv above; both modes' diagnostics land on stderr.
      assert result.stderr.count("## Diagnostics") == 2
  ```
  and add `"-v"` to the argv list on line 376.
- `test_cli_recap_mode_has_no_summary_or_brief_sections` (line 390): replace the final assert (line 403) `assert "## Diagnostics" in result.stdout` with:
  ```python
      assert "## Diagnostics" not in result.stdout
  ```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "diagnostics_file or emit_default_stdout or emit_verbose or emit_returns" -q`
Expected: FAIL — `--diagnostics-file` not parsed; `_emit_mode_result` returns a bool (not a tuple) and still prints to stdout.

- [ ] **Step 3: Add the `--diagnostics-file` argument**

In `src/pitcher_narratives/cli.py`, in the `report` subparser, add after the `--metrics-out` argument (currently ends line 107):

```python
    report.add_argument(
        "--diagnostics-file",
        default=None,
        help=(
            "Write the QA/diagnostics appendix as JSON to this path (one object "
            "per narration mode). Off by default; stdout stays the reader report."
        ),
    )
```

- [ ] **Step 4: Change `_emit_mode_result` to route diagnostics and return the dict**

Change the signature (currently line 295) to:
```python
def _emit_mode_result(pipe_result, *, persona: str, mode, verbose: bool = False) -> tuple[bool, dict]:
```
Replace the diagnostics tail added in Task 2 (the `# ── Diagnostics appendix (still on stdout...` block) with:
```python
    # ── Diagnostics: off the reader stream ──────────────────────────────
    # Built unconditionally (runs the hallucination guard for every mode) but
    # only *displayed* on -v; the JSON sidecar is written by the caller.
    diag = build_diagnostics_dict(pipe_result, persona)
    if verbose:
        print("\n\n---\n", file=sys.stderr)
        print(render_diagnostics_text(diag), file=sys.stderr)

    # Empty narrative → nothing to verify; never soft-block (pre-WS2 contract).
    return (unverified if pipe_result.narrative else False), diag
```

Add the file writer near `_append_metrics_records` (~line 427):
```python
def _write_diagnostics_file(path, diagnostics_by_mode: dict) -> None:
    """Write per-mode diagnostics dicts to a JSON file (keyed by mode id)."""
    import json
    from pathlib import Path

    Path(path).write_text(json.dumps(diagnostics_by_mode, indent=2, default=str))
```

- [ ] **Step 5: Update the mode loop in `_run_report_command`**

In `_run_report_command`, update the emit loop (currently lines 562-589). Add a `diagnostics_by_mode` accumulator and unpack the tuple:
```python
    any_unverified = False
    results: dict[str, PipelineResult] = {}
    diagnostics_by_mode: dict[str, dict] = {}
    first = True
    for mode in selected_modes:
        if mode.id in results:
            continue
        print(f"{'' if first else chr(10) * 2}# {mode.title}\n")
        first = False
        try:
            mode_results = run_narration_modes(
                ctx,
                modes=[mode],
                provider=args.provider,
                thinking=args.thinking,
                persona=args.persona,
                explain_model=args.explain_model,
                _model_override=model_override,
                prior_ctx=prior_ctx,
            )
        except AgentRunError as e:
            log.error("LLM call failed: %s", e)
            sys.exit(2)
        pipe_result = mode_results[mode.id]
        results[mode.id] = pipe_result
        unverified, diag = _emit_mode_result(
            pipe_result, persona=args.persona, mode=mode, verbose=args.verbose,
        )
        diagnostics_by_mode[mode.id] = diag
        if unverified:
            any_unverified = True
            banner = residual_banner(pipe_result, label=mode.id.upper())
            print(f"\n{banner}", file=sys.stderr)

    if args.diagnostics_file:
        try:
            _write_diagnostics_file(args.diagnostics_file, diagnostics_by_mode)
        except OSError as e:
            log.error("Failed to write diagnostics file: %s", e)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py -q`
Expected: PASS — new parse/routing tests, the updated integration tests, and the unchanged reader-section + UNVERIFIED-banner tests.

- [ ] **Step 7: Add a JSON-sidecar integration test**

Add to `tests/test_cli.py`:
```python
def test_report_writes_diagnostics_json_file(tmp_path):
    out = tmp_path / "diag.json"
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155",
         "--diagnostics-file", str(out)],
        capture_output=True, text=True, timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    import json
    payload = json.loads(out.read_text())
    assert "report" in payload
    assert "verified" in payload["report"]
    assert "## Diagnostics" not in result.stdout  # sidecar, not stdout
```

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_cli.py::test_report_writes_diagnostics_json_file -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat(report): route diagnostics to -v/stderr and --diagnostics-file JSON

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Update README

**Files:**
- Modify: `README.md` (the `### pitcher-narratives report` output description ~96-115; the flag table ~70-83)

**Interfaces:** none (docs only).

- [ ] **Step 1: Confirm the current description is stale**

Run: `grep -n "streamed capsule\|Corrected Capsule\|## Diagnostics" README.md`
Expected: matches in the report section (the text this task rewrites).

- [ ] **Step 2: Update the flag table**

In `README.md`, in the `pitcher-narratives report` flag table (the block starting near line 70), add a row after the `--no-explain-model` row:
```markdown
| `--diagnostics-file` | path | *none* | Write the QA/diagnostics appendix as JSON (one object per mode); stdout stays the reader report |
```
And update the `-v, --verbose` row (currently line 77) to:
```markdown
| `-v`, `--verbose` | flag | off | Print pitcher summary **and** the QA/diagnostics appendix to stderr (default stdout is the reader report only) |
```

- [ ] **Step 3: Rewrite the stdout description**

Replace the paragraph describing stdout (currently lines 96-107, beginning "Stdout emits one labeled block per requested mode...") with:
```markdown
Stdout emits one labeled block per requested mode, in `--mode` order — the
**reader document only**: `# <Mode Title>` (`Scouting Report` / `Change Report`
/ `Recap`), the final capsule (printed once — the pipeline buffers the writer
output rather than streaming it), a `**Verification:**` stamp (✅ verified / ⚠️
UNVERIFIED with counts), and a distilled `## Executive Summary` + `## Brief` for
`report`/`changes` only (recap's capsule is already the brief).

The QA/diagnostics appendix (`### Stuff Analysis`, `### Data Audit`,
`### Capsule Fact-Check`, `### Value Parity`, `### Anchor Check`,
`### Hallucination Check`) is **off the reader stream**: pass `-v` to print it to
stderr, or `--diagnostics-file PATH` to write it as JSON (one object per mode).
```

Leave the following paragraph (about the `UNVERIFIED` banner + `--print-prompts`, currently lines 109-115) unchanged — its contract is preserved.

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -n "streamed capsule\|Corrected Capsule" README.md`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: report stdout is the reader document; diagnostics via -v/--diagnostics-file

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (`2026-07-05-report-diagnostics-separation-design.md`):
- §3.1 default stdout = reader document only → Task 3 (diagnostics gated). ✅
- §3.1 diagnostics under `-v` to stderr + `--diagnostics-file` JSON → Task 3. ✅ (both sinks, per the 2026-07-05 decision)
- §3.1 UNVERIFIED banner + exit code unchanged → preserved (mode loop still prints banner to stderr, exit logic untouched). ✅
- §3.2 kill the double capsule — **Option A (buffer)** per decision → Task 1. ✅
- §3.3 capsule appears exactly once → Task 1 (`test_emit_prints_capsule_once_and_no_corrected_section`). ✅
- §4.1 extract `render_diagnostics` helper → Task 2 (`build_diagnostics_dict` + `render_diagnostics_text`). ✅
- §4.4 update docs → Task 4 (`daily-runs.md` verified to contain no diagnostics/streaming references, so README is the only doc to change). ✅
- §5 testing (default stdout has no diagnostics; `-v`/file surfaces it; capsule once; banner + exit unchanged) → Tasks 1 & 3 tests. ✅

**Placeholder scan:** none — every step has concrete code and exact commands.

**Type consistency:** `build_diagnostics_dict(pipe_result, persona) -> dict` and `render_diagnostics_text(diag) -> str` are defined in Task 2 and consumed identically in Task 3. `_emit_mode_result` return type changes bool → `tuple[bool, dict]` exactly once (Task 3), and every call site (the mode loop + the three direct-call tests) is updated in the same task. The diagnostics dict keys used by `render_diagnostics_text` (`stuff_analysis`, `data_audit`, `capsule_fact_check`, `capsule_revised`, `revision_count`, `anchor_warnings`, `value_parity_warnings`, `hallucination`) match the keys produced by `build_diagnostics_dict`.

**Resolved — `is_unverified` + empty narrative:** Verified against `pipeline.py:1495` — `is_unverified` returns `True` whenever `capsule_audit_flags` is non-empty, *regardless of narrative*. The old `_emit_mode_result` returned `False` for an empty narrative via an explicit early-return (old line 404-406), and `test_emit_mode_result_empty_narrative_is_not_unverified` pins exactly that. Both Task 2 and Task 3 therefore return `unverified if pipe_result.narrative else False` — the `else False` gate is load-bearing, not optional. The printed `**Verification:**` stamp continues to use the raw `unverified` (unchanged from today).
