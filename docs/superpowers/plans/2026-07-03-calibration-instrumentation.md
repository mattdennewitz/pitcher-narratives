# Calibration Instrumentation & Aggregator (Phase 11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the dead `flag_summary()` feed into persisted per-mode flag records, and add an offline aggregator so an operator can read revision/flag rates across accumulated runs — without running any live LLM calls or changing any depth constant this phase.

**Architecture:** A new pure helper `flag_record()` wraps `flag_summary()` with calibration context (mode id, pitcher, span, revision-depth caps). Morning persists one record per pick to a real `validation.json` (replacing today's stub). The `report` subcommand gains an opt-in `--metrics-out PATH` that appends one JSONL record per `(pitcher, mode)` run. A new `calibration` module + `python -m pitcher_narratives.calibration` reads accumulated records, groups by mode, and prints per-mode revision/flag/hit-cap stats. A runbook doc explains how to accumulate runs and which constants to edit.

**Tech Stack:** Python 3.14, polars, pydantic-ai, pytest. No LLM calls in any test (all tests construct `PipelineResult`/record dicts directly).

## Global Constraints

- Python 3.14+ (`requires-python = ">=3.14"`); `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- No live Baseball Savant calls; static parquet + CSV only.
- Data-dependent tests need `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives` when run in this worktree. **None of the tests in this plan are data-gated** — they construct results/records in-memory.
- This phase changes NO depth constants. `personas.py` RECAP `ValidationPolicy(anchor_depth=1, fact_depth=2)` and REPORT/CHANGES `5/2` stay as-is; they are calibrated later from the data this plumbing collects.
- REPORT span (`_DEFAULT_RECENT_APPEARANCES = 10`, `temporal.py`) is already empirically measured — not re-derived here.

---

## Task 1: `flag_record` — pure calibration-record helper

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (add `flag_record` directly after `flag_summary`, ends `pipeline.py:1220`; add `"flag_record"` to `__all__` at `pipeline.py:130`)
- Test: `tests/test_pipeline.py` (add beside `test_flag_summary_counts_fields`, `pipeline.py`… `tests/test_pipeline.py:1916`)

**Interfaces:**
- Consumes: `flag_summary(result: PipelineResult) -> dict[str, int | bool]` (already at `pipeline.py:1206`); `NarrationMode` (already imported `pipeline.py:87`), whose `.id: str` and `.validation.anchor_depth: int` / `.validation.fact_depth: int` are read.
- Produces: `flag_record(mode: NarrationMode, pitcher_id: int, result: PipelineResult, *, span: int) -> dict[str, object]`. Returns a JSON-serializable dict: the six `flag_summary` keys plus `mode` (mode id), `pitcher_id`, `span`, `anchor_depth_cap`, `fact_depth_cap`. Later tasks (2, 3, 4) rely on exactly these key names.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`:

```python
def test_flag_record_stamps_mode_context_onto_summary():
    """flag_record = flag_summary(result) + mode id, pitcher, span, and caps."""
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.personas import RECAP
    from pitcher_narratives.pipeline import PipelineResult, flag_record

    result = PipelineResult(
        narrative="n",
        specialists=SpecialistOutputs(
            stuff="s", location="l", runvalue="r", trends="t", game_shape="g"),
        revision_count=1,
        capsule_revised=False,
        value_parity_warnings=["[capsule] 1.23"],
    )
    record = flag_record(RECAP, pitcher_id=592155, result=result, span=10)
    assert record == {
        "mode": "recap",
        "pitcher_id": 592155,
        "span": 10,
        "anchor_depth_cap": 1,
        "fact_depth_cap": 2,
        "revision_count": 1,
        "capsule_revised": False,
        "n_capsule_audit_flags": 0,
        "n_anchor_warnings": 0,
        "n_value_parity_warnings": 1,
        "n_audit_flags": 0,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/test_pipeline.py::test_flag_record_stamps_mode_context_onto_summary" -v`
Expected: FAIL — `ImportError: cannot import name 'flag_record'`.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/pipeline.py`, directly after the `flag_summary` function (after `pipeline.py:1220`):

```python
def flag_record(
    mode: NarrationMode,
    pitcher_id: int,
    result: PipelineResult,
    *,
    span: int,
) -> dict[str, object]:
    """A persisted calibration record: flag_summary + calibration context.

    Stamps the mode id, pitcher, analysis span (recent-appearance count), and
    the mode's configured revision-depth caps onto ``flag_summary(result)`` so
    the offline aggregator (``pitcher_narratives.calibration``) can compute
    per-mode revision rates and anchor/fact hit-cap rates from real runs.
    """
    return {
        "mode": mode.id,
        "pitcher_id": pitcher_id,
        "span": span,
        "anchor_depth_cap": mode.validation.anchor_depth,
        "fact_depth_cap": mode.validation.fact_depth,
        **flag_summary(result),
    }
```

Add `"flag_record"` to the `__all__` list at `pipeline.py:130` (next to the existing `"flag_summary"` entry).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest "tests/test_pipeline.py::test_flag_record_stamps_mode_context_onto_summary" "tests/test_pipeline.py::test_flag_summary_counts_fields" -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/pipeline.py tests/test_pipeline.py
git commit -m "feat(calibrate): flag_record stamps mode context onto flag_summary (P11 T1)"
```

---

## Task 2: Morning persists real per-pick flag records to `validation.json`

**Files:**
- Modify: `src/pitcher_narratives/morning.py` (`_llm_stages` loop `morning.py:132-159`; return tuple; `validation.json` write `morning.py:193-196`)
- Test: `tests/test_morning.py`

**Interfaces:**
- Consumes: `flag_record` (Task 1); `RECAP` from `pitcher_narratives.personas`; `_DEFAULT_RECENT_APPEARANCES` from `pitcher_narratives.temporal`; the per-pick `recap_result: PipelineResult` already available in the `_llm_stages` loop (`morning.py:137`).
- Produces: `validation.json` with shape `{"game_date": "<date>", "picks": {"<pitcher_id>": <flag_record dict>}}`. Only picks that survived (are in `summaries`) get a record. Task 4's aggregator reads this file.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_morning.py` (a pure serialization test — no LLM, no data files):

```python
def test_build_validation_payload_records_flags_per_pick():
    """The validation.json payload carries one flag_record per surviving pick."""
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.morning import _build_validation_payload
    from pitcher_narratives.pipeline import PipelineResult

    result = PipelineResult(
        narrative="n",
        specialists=SpecialistOutputs(
            stuff="s", location="l", runvalue="r", trends="t", game_shape="g"),
        revision_count=1,
        capsule_revised=True,
    )
    payload = _build_validation_payload("2026-07-03", {592155: result})
    assert payload["game_date"] == "2026-07-03"
    rec = payload["picks"]["592155"]
    assert rec["mode"] == "recap"
    assert rec["pitcher_id"] == 592155
    assert rec["revision_count"] == 1
    assert rec["capsule_revised"] is True
    assert rec["anchor_depth_cap"] == 1
    assert rec["fact_depth_cap"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/test_morning.py::test_build_validation_payload_records_flags_per_pick" -v`
Expected: FAIL — `ImportError: cannot import name '_build_validation_payload'`.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/morning.py`, add these imports near the existing `from pitcher_narratives.personas import ...` / `from pitcher_narratives.pipeline import ...` blocks (add each name to whichever import already exists; do not duplicate the `import` line):

```python
from pitcher_narratives.personas import RECAP
from pitcher_narratives.pipeline import flag_record
from pitcher_narratives.temporal import _DEFAULT_RECENT_APPEARANCES
```

Add a module-level helper (place it above `run_morning`):

```python
def _build_validation_payload(
    game_date: str, recap_results: dict[int, "PipelineResult"]
) -> dict[str, object]:
    """Per-pick calibration records for validation.json.

    One ``flag_record`` per surviving pick, keyed by stringified pitcher id
    (JSON object keys must be strings). Morning always runs RECAP on the
    default recent-appearance span.
    """
    return {
        "game_date": game_date,
        "picks": {
            str(pid): flag_record(
                RECAP, pid, result, span=_DEFAULT_RECENT_APPEARANCES
            )
            for pid, result in recap_results.items()
        },
    }
```

In `_llm_stages`, capture each surviving pick's `recap_result` into a dict. In the loop at `morning.py:134-149`, add a `recap_results: dict[int, PipelineResult] = {}` initializer beside `summaries` (near `morning.py:132`), and inside the loop after `summaries[pid] = text` (`morning.py:149`) add:

```python
            recap_results[pid] = recap_result
```

Change the `_llm_stages` return (`morning.py:159`) from:

```python
        return slate, picks, summaries, dropped_names, n_unverified
```

to:

```python
        return slate, picks, summaries, dropped_names, n_unverified, recap_results
```

and update the unpacking at `morning.py:161`:

```python
    slate, picks, summaries, dropped_names, n_unverified, recap_results = asyncio.run(_llm_stages())
```

Replace the `validation.json` stub write (`morning.py:193-196`) with:

```python
    (run_dir / "validation.json").write_text(json.dumps(
        _build_validation_payload(str(game_date), recap_results),
        indent=2,
    ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest "tests/test_morning.py::test_build_validation_payload_records_flags_per_pick" -v`
Expected: PASS.

- [ ] **Step 5: Run the morning test module to catch regressions in the return-tuple change**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/test_morning.py -q`
Expected: PASS (any pre-existing skips unchanged). If a test unpacks `_llm_stages`'s return or asserts on `validation.json`'s old stub shape, update it to the new 6-tuple / new payload — do not revert the source.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/morning.py tests/test_morning.py
git commit -m "feat(calibrate): morning persists per-pick flag records to validation.json (P11 T2)"
```

---

## Task 3: `report --metrics-out PATH` appends per-mode JSONL records

**Files:**
- Modify: `src/pitcher_narratives/cli.py` (add `--metrics-out` arg to the `report` parser after `--mode`, `cli.py:91-98`; append records after the results loop, `cli.py:456-463`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `flag_record` (Task 1); `selected_modes: list[NarrationMode]` and `results: dict[str, PipelineResult]` already in `_run_report_command` scope (`cli.py:432`, `cli.py:456`); `args.pitcher: int`, `args.recent: int`.
- Produces: when `args.metrics_out` is set, appends one JSON object per line (JSONL) — one per `(pitcher, mode)` — to that path, each the output of `flag_record(mode, args.pitcher, result, span=args.recent)`. When unset, report behavior is byte-identical to today.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_report_parser_metrics_out_defaults_none(monkeypatch):
    import sys

    from pitcher_narratives.cli import parse_args

    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.metrics_out is None


def test_append_metrics_records_writes_jsonl(tmp_path):
    """_append_metrics_records writes one flag_record JSON line per mode."""
    import json

    from pitcher_narratives.cli import _append_metrics_records
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.personas import RECAP, REPORT
    from pitcher_narratives.pipeline import PipelineResult

    def _r(rev):
        return PipelineResult(
            narrative="n",
            specialists=SpecialistOutputs(
                stuff="s", location="l", runvalue="r", trends="t", game_shape="g"),
            revision_count=rev,
        )

    out = tmp_path / "metrics.jsonl"
    _append_metrics_records(
        out, pitcher_id=592155, span=10,
        modes=[REPORT, RECAP],
        results={"report": _r(4), "recap": _r(1)},
    )
    # Append again to prove it does not truncate.
    _append_metrics_records(
        out, pitcher_id=592155, span=10,
        modes=[REPORT], results={"report": _r(2)},
    )
    lines = out.read_text().splitlines()
    assert len(lines) == 3
    recs = [json.loads(x) for x in lines]
    assert [r["mode"] for r in recs] == ["report", "recap", "report"]
    assert recs[0]["revision_count"] == 4
    assert recs[0]["anchor_depth_cap"] == 5  # REPORT keeps 5/2
    assert recs[1]["anchor_depth_cap"] == 1  # RECAP caps anchor at 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest "tests/test_cli.py::test_report_parser_metrics_out_defaults_none" "tests/test_cli.py::test_append_metrics_records_writes_jsonl" -v`
Expected: FAIL — `args` has no `metrics_out`; `_append_metrics_records` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `src/pitcher_narratives/cli.py`, add the argument to the `report` parser immediately after the `--mode` block (`cli.py:98`):

```python
    report.add_argument(
        "--metrics-out",
        default=None,
        help=(
            "Append one JSON line per (pitcher, mode) run to this path for "
            "offline depth calibration (see docs/calibration.md). Off by default."
        ),
    )
```

Add a module-level helper (place it near `_emit_mode_result`):

```python
def _append_metrics_records(
    path,
    *,
    pitcher_id: int,
    span: int,
    modes: "list[NarrationMode]",
    results: "dict[str, PipelineResult]",
) -> None:
    """Append per-mode calibration records (JSONL) to ``path``.

    One line per result, so repeated report runs accumulate rather than
    overwrite. Mode objects supply the depth caps recorded by flag_record.
    """
    import json
    from pathlib import Path

    from pitcher_narratives.pipeline import flag_record

    modes_by_id = {m.id: m for m in modes}
    lines = [
        json.dumps(flag_record(modes_by_id[mode_id], pitcher_id, result, span=span))
        for mode_id, result in results.items()
    ]
    with Path(path).open("a") as f:
        for line in lines:
            f.write(line + "\n")
```

In `_run_report_command`, after the results loop and before the `any_unverified` exit check (after `cli.py:460`, before `cli.py:462`), add:

```python
    if args.metrics_out:
        _append_metrics_records(
            args.metrics_out,
            pitcher_id=args.pitcher,
            span=args.recent,
            modes=selected_modes,
            results=results,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest "tests/test_cli.py::test_report_parser_metrics_out_defaults_none" "tests/test_cli.py::test_append_metrics_records_writes_jsonl" -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add src/pitcher_narratives/cli.py tests/test_cli.py
git commit -m "feat(calibrate): report --metrics-out appends per-mode JSONL records (P11 T3)"
```

---

## Task 4: `calibration` aggregator module + `python -m` entry point

**Files:**
- Create: `src/pitcher_narratives/calibration.py` — a single module (not a package). It exposes `main()` behind an `if __name__ == "__main__"` guard, which makes it directly runnable as `python -m pitcher_narratives.calibration`; no separate `__main__.py` is needed.
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: record dicts produced by Tasks 1–3 (keys: `mode`, `pitcher_id`, `span`, `anchor_depth_cap`, `fact_depth_cap`, `revision_count`, `capsule_revised`, `n_capsule_audit_flags`, `n_anchor_warnings`, `n_value_parity_warnings`, `n_audit_flags`).
- Produces:
  - `load_records(paths: list[str]) -> list[dict]` — reads each path; `*.jsonl` → one record per line; `validation.json` (a `{"picks": {...}}` object) → the record values; a bare JSON array → its elements. Directories are walked for `validation.json` and `*.jsonl` files.
  - `aggregate(records: list[dict]) -> dict[str, ModeStats]` — groups by `mode`.
  - `ModeStats` dataclass: `n:int`, `mean_revision_count:float`, `median_revision_count:float`, `capsule_revised_rate:float`, `mean_capsule_audit_flags:float`, `mean_anchor_warnings:float`, `mean_value_parity_warnings:float`, `anchor_hit_cap_rate:float`, `fact_hit_cap_rate:float`.
  - `format_table(stats: dict[str, ModeStats]) -> str`.
  - `main(argv: list[str] | None = None) -> int`.

**Definitions (make the stats unambiguous):**
- `anchor_hit_cap_rate` = fraction of records where `revision_count >= anchor_depth_cap` AND `anchor_depth_cap > 0`. (Signals whether the anchor cap is a real ceiling.)
- `fact_hit_cap_rate` = fraction of records where `capsule_revised is True` AND `fact_depth_cap > 0`. (`capsule_revised` marks that the fact loop ran a remediation pass; a proxy for pressure on the fact cap, since exact fact-pass count is not persisted.)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calibration.py`:

```python
import json

from pitcher_narratives.calibration import (
    aggregate,
    format_table,
    load_records,
    main,
)


def _rec(mode, rev, *, anchor_cap, fact_cap, capsule_revised=False):
    return {
        "mode": mode, "pitcher_id": 1, "span": 10,
        "anchor_depth_cap": anchor_cap, "fact_depth_cap": fact_cap,
        "revision_count": rev, "capsule_revised": capsule_revised,
        "n_capsule_audit_flags": 0, "n_anchor_warnings": 0,
        "n_value_parity_warnings": 0, "n_audit_flags": 0,
    }


def test_aggregate_groups_by_mode_and_computes_rates():
    records = [
        _rec("recap", 0, anchor_cap=1, fact_cap=2),
        _rec("recap", 1, anchor_cap=1, fact_cap=2, capsule_revised=True),
        _rec("report", 5, anchor_cap=5, fact_cap=2),
    ]
    stats = aggregate(records)
    assert set(stats) == {"recap", "report"}
    assert stats["recap"].n == 2
    assert stats["recap"].mean_revision_count == 0.5
    assert stats["recap"].capsule_revised_rate == 0.5
    # one of two recap records hit the anchor cap of 1 (revision_count 1 >= 1)
    assert stats["recap"].anchor_hit_cap_rate == 0.5
    assert stats["recap"].fact_hit_cap_rate == 0.5
    assert stats["report"].anchor_hit_cap_rate == 1.0  # 5 >= 5


def test_load_records_from_jsonl_and_validation_json(tmp_path):
    jl = tmp_path / "metrics.jsonl"
    jl.write_text(
        json.dumps(_rec("report", 2, anchor_cap=5, fact_cap=2)) + "\n"
        + json.dumps(_rec("recap", 1, anchor_cap=1, fact_cap=2)) + "\n"
    )
    vj = tmp_path / "validation.json"
    vj.write_text(json.dumps({
        "game_date": "2026-07-03",
        "picks": {"592155": _rec("recap", 0, anchor_cap=1, fact_cap=2)},
    }))
    records = load_records([str(jl), str(vj)])
    assert len(records) == 3
    assert sum(r["mode"] == "recap" for r in records) == 2


def test_load_records_walks_directory(tmp_path):
    (tmp_path / "2026-07-03").mkdir()
    (tmp_path / "2026-07-03" / "validation.json").write_text(json.dumps({
        "game_date": "2026-07-03",
        "picks": {"1": _rec("recap", 1, anchor_cap=1, fact_cap=2)},
    }))
    records = load_records([str(tmp_path)])
    assert len(records) == 1


def test_format_table_lists_each_mode():
    stats = aggregate([_rec("recap", 1, anchor_cap=1, fact_cap=2)])
    table = format_table(stats)
    assert "recap" in table
    assert "anchor_hit_cap" in table


def test_main_prints_table(tmp_path, capsys):
    jl = tmp_path / "m.jsonl"
    jl.write_text(json.dumps(_rec("report", 2, anchor_cap=5, fact_cap=2)) + "\n")
    rc = main([str(jl)])
    assert rc == 0
    assert "report" in capsys.readouterr().out


def test_main_no_records_returns_nonzero(tmp_path, capsys):
    rc = main([str(tmp_path)])
    assert rc == 1
    assert "no records" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_calibration.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pitcher_narratives.calibration'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/pitcher_narratives/calibration.py`:

```python
"""Offline aggregator for per-mode revision/flag calibration records.

Reads the records persisted by the morning run (``validation.json``) and by
``report --metrics-out`` (JSONL), groups them by narration mode, and prints
per-mode revision rates and anchor/fact hit-cap rates. The output tells an
operator whether a mode's provisional revision-depth caps
(``personas.py`` ValidationPolicy) are ever a binding ceiling — the signal
for setting Phase 11's depth constants from data rather than guesses.

No LLM calls; pure analysis over on-disk records.
Usage: ``python -m pitcher_narratives.calibration PATH [PATH ...]``
where each PATH is a validation.json, a *.jsonl file, or a directory.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ModeStats",
    "aggregate",
    "format_table",
    "load_records",
    "main",
]


@dataclass(frozen=True)
class ModeStats:
    """Aggregated calibration stats for one narration mode."""

    n: int
    mean_revision_count: float
    median_revision_count: float
    capsule_revised_rate: float
    mean_capsule_audit_flags: float
    mean_anchor_warnings: float
    mean_value_parity_warnings: float
    anchor_hit_cap_rate: float
    fact_hit_cap_rate: float


def _records_from_obj(obj: object) -> list[dict]:
    """Extract record dicts from one parsed JSON document."""
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    if isinstance(obj, dict) and isinstance(obj.get("picks"), dict):
        return [r for r in obj["picks"].values() if isinstance(r, dict)]
    if isinstance(obj, dict):
        return [obj]
    return []


def _records_from_file(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text().splitlines()
            if line.strip()
        ]
    return _records_from_obj(json.loads(path.read_text()))


def load_records(paths: list[str]) -> list[dict]:
    """Load records from files and directories.

    Files: ``*.jsonl`` (one record per line) or a JSON document (a record,
    an array of records, or a ``{"picks": {...}}`` object). Directories are
    walked for ``validation.json`` and ``*.jsonl`` files.
    """
    records: list[dict] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("validation.json")):
                records.extend(_records_from_file(f))
            for f in sorted(p.rglob("*.jsonl")):
                records.extend(_records_from_file(f))
        elif p.exists():
            records.extend(_records_from_file(p))
    return records


def _rate(predicate_true: int, n: int) -> float:
    return predicate_true / n if n else 0.0


def aggregate(records: list[dict]) -> dict[str, ModeStats]:
    """Group records by ``mode`` and compute per-mode stats."""
    by_mode: dict[str, list[dict]] = {}
    for r in records:
        by_mode.setdefault(r["mode"], []).append(r)

    stats: dict[str, ModeStats] = {}
    for mode, rs in by_mode.items():
        n = len(rs)
        revs = [r["revision_count"] for r in rs]
        anchor_hits = sum(
            1 for r in rs
            if r["anchor_depth_cap"] > 0
            and r["revision_count"] >= r["anchor_depth_cap"]
        )
        fact_hits = sum(
            1 for r in rs
            if r["fact_depth_cap"] > 0 and r["capsule_revised"]
        )
        stats[mode] = ModeStats(
            n=n,
            mean_revision_count=statistics.fmean(revs),
            median_revision_count=statistics.median(revs),
            capsule_revised_rate=_rate(
                sum(1 for r in rs if r["capsule_revised"]), n),
            mean_capsule_audit_flags=statistics.fmean(
                [r["n_capsule_audit_flags"] for r in rs]),
            mean_anchor_warnings=statistics.fmean(
                [r["n_anchor_warnings"] for r in rs]),
            mean_value_parity_warnings=statistics.fmean(
                [r["n_value_parity_warnings"] for r in rs]),
            anchor_hit_cap_rate=_rate(anchor_hits, n),
            fact_hit_cap_rate=_rate(fact_hits, n),
        )
    return stats


def format_table(stats: dict[str, ModeStats]) -> str:
    """Render a fixed-width per-mode calibration table."""
    header = (
        f"{'mode':<8} {'n':>4} {'rev_mean':>9} {'rev_med':>8} "
        f"{'caps_rev':>9} {'anchor_hit_cap':>15} {'fact_hit_cap':>13}"
    )
    lines = [header, "-" * len(header)]
    for mode in sorted(stats):
        s = stats[mode]
        lines.append(
            f"{mode:<8} {s.n:>4} {s.mean_revision_count:>9.2f} "
            f"{s.median_revision_count:>8.1f} {s.capsule_revised_rate:>9.2f} "
            f"{s.anchor_hit_cap_rate:>15.2f} {s.fact_hit_cap_rate:>13.2f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m pitcher_narratives.calibration PATH [PATH ...]",
              file=sys.stderr)
        return 2
    records = load_records(args)
    if not records:
        print("no records found in the given paths", file=sys.stderr)
        return 1
    print(format_table(aggregate(records)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_calibration.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Verify the entry point runs end to end**

Run: `printf '{"mode":"report","pitcher_id":1,"span":10,"anchor_depth_cap":5,"fact_depth_cap":2,"revision_count":3,"capsule_revised":false,"n_capsule_audit_flags":0,"n_anchor_warnings":0,"n_value_parity_warnings":0,"n_audit_flags":0}\n' > /tmp/p11_metrics.jsonl && uv run python -m pitcher_narratives.calibration /tmp/p11_metrics.jsonl`
Expected: a table with a `report` row, `n` = 1, `rev_mean` = 3.00, `anchor_hit_cap` = 0.00.

- [ ] **Step 6: Commit**

```bash
git add src/pitcher_narratives/calibration.py tests/test_calibration.py
git commit -m "feat(calibrate): offline per-mode revision/hit-cap aggregator (P11 T4)"
```

---

## Task 5: Calibration runbook doc + full-suite wrap-up

**Files:**
- Create: `docs/calibration.md`
- Test: none (documentation); full suite is the gate.

**Interfaces:**
- Consumes: everything from Tasks 1–4 (the artifacts, the aggregator, the constants it points at). No code produced.

- [ ] **Step 1: Write the runbook**

Create `docs/calibration.md`:

```markdown
# Depth Calibration Runbook (Phase 11)

The per-mode revision-depth caps in `personas.py` are **provisional** — set by
judgment, not measurement. This runbook explains how to collect real
revision/flag data and read it, so the caps can be set from evidence.

## What is calibrated

| Constant | Location | Current (provisional) |
| --- | --- | --- |
| RECAP anchor / fact depth | `personas.py` `RECAP` `ValidationPolicy(anchor_depth=1, fact_depth=2)` | 1 / 2 |
| REPORT / CHANGES anchor / fact depth | `config.py` `MAX_REVISIONS` / `MAX_FACT_REVISIONS` via `personas.py` REPORT & CHANGES | 5 / 2 |
| REPORT span (recent appearances) | `temporal.py` `_DEFAULT_RECENT_APPEARANCES` | 10 — **already measured 2026-07-01**, not re-derived here |

This phase changes none of these numbers. It builds the plumbing that produces
the evidence for a later, separate change.

## Collecting data (instrumented runs)

Two sources feed the aggregator; both persist a `flag_record` per
`(pitcher, mode)` run (`pitcher_narratives.pipeline.flag_record`):

1. **Morning runs (RECAP, organic).** Every `pitcher-narratives morning`
   writes real per-pick records to `<out>/<game_date>/validation.json`.
   Just accumulate morning runs over days.
2. **Report runs (any mode, on demand).** Pass `--metrics-out PATH` to append
   JSONL records. Sweep pitchers and modes to build a sample, e.g.:

   ```bash
   for pid in 592155 693433 605483; do
     pitcher-narratives report -p "$pid" --mode report,recap,changes \
       --metrics-out var/calibration/metrics.jsonl
   done
   ```

## Reading the data

```bash
python -m pitcher_narratives.calibration var/calibration/metrics.jsonl <out>/2026-07-*/
```

Paths may be `*.jsonl` files, `validation.json` files, or directories (walked
for both). The output is a per-mode table:

- `rev_mean` / `rev_med` — anchor-revision passes per run.
- `caps_rev` — fraction of runs where the capsule fact loop ran a remediation
  pass.
- `anchor_hit_cap` — fraction of runs where `revision_count` reached the mode's
  anchor cap. **This is the key signal.**
- `fact_hit_cap` — fraction of runs that ran a fact-remediation pass under a
  non-zero fact cap.

## Interpreting → setting the constants

- **`anchor_hit_cap` ≈ 0 for a mode** → the cap is never binding; it can be
  lowered (cheaper runs) with no loss. E.g. if RECAP's `anchor_hit_cap` is 0
  across a healthy sample, `anchor_depth=1` is already slack.
- **`anchor_hit_cap` high (e.g. > 0.3)** → runs are hitting the ceiling and may
  ship under-revised; consider raising the cap.
- **`caps_rev` / `fact_hit_cap` high** → the fact loop is doing real work; keep
  `fact_depth` where it is or raise it.

Edit the constant in `personas.py` (RECAP/CHANGES `ValidationPolicy`) or
`config.py` (`MAX_REVISIONS` / `MAX_FACT_REVISIONS` for REPORT), then
regenerate any affected golden fixtures and re-run the suite. That numeric
change is deliberately **out of scope for Phase 11** — it belongs to a
follow-up once a representative sample has accrued.
```

- [ ] **Step 2: Run the full suite**

Run: `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest -q`
Expected: pass except the single pre-existing `test_to_prompt_token_budget` failure noted in the Phase 10 plan. The new calibration/morning/cli/pipeline tests pass.

- [ ] **Step 3: Commit**

```bash
git add docs/calibration.md
git commit -m "docs(calibrate): depth-calibration runbook + Phase 11 wrap-up (P11 T5)"
```

---

## Self-Review

**Spec coverage (design §8 / §13 item 11):**
- §8 "add tracker.record to anchor + capsule loops" — already present (`pipeline.py:167,1424,1540`); this phase adds the *flag-count* feed §8 also demands.
- §8 "persist PipelineResult flag counts to run artifacts" — Task 2 (morning `validation.json`), Task 3 (`report --metrics-out`). The dead `flag_summary` (`pipeline.py:1206`) is now reachable via `flag_record` (Task 1).
- §8/§13.11 "calibrate the RECAP depth default from instrumented runs rather than guessing" — Task 4 aggregator + Task 5 runbook produce the evidence and the procedure. Setting the number is explicitly deferred (approved scope: instrumentation + harness only).
- REPORT span already measured (`temporal.py`) — documented, not touched.

**Placeholder scan:** No TBD/TODO in task steps; every code step shows full code. (Task 4's Files block discusses the module-vs-package entry-point choice and resolves it: a single `calibration.py` module IS runnable via `python -m pitcher_narratives.calibration`.)

**Type consistency:** `flag_record(mode, pitcher_id, result, *, span)` and its 11 output keys are defined in Task 1 and consumed identically in Tasks 2 (`_build_validation_payload`), 3 (`_append_metrics_records`), and 4 (`aggregate` reads exactly those keys). `ModeStats` fields match between `aggregate` (producer) and `format_table` (consumer). `_llm_stages` return arity changed from 5-tuple to 6-tuple in both the `return` and the unpack site (Task 2).

**Out of scope (YAGNI, from approved design):** no live runs, no depth-number changes, no active calibration driver, no changes to bench `scores.json`.
