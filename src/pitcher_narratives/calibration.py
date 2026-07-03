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
    mean_secondary_signals: float
    """Mean populated secondary KeySignals fields (of 6 possible) per run.
    Low values mean narratives are running on the thin top_improvement/
    top_concern lead only, without the cross-specialist insight signals."""


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
            mean_secondary_signals=statistics.fmean(
                [r.get("n_secondary_signals", 0) for r in rs]),
        )
    return stats


def format_table(stats: dict[str, ModeStats]) -> str:
    """Render a fixed-width per-mode calibration table."""
    header = (
        f"{'mode':<8} {'n':>4} {'rev_mean':>9} {'rev_med':>8} "
        f"{'caps_rev':>9} {'anchor_hit_cap':>15} {'fact_hit_cap':>13} "
        f"{'sec_signals':>11}"
    )
    lines = [header, "-" * len(header)]
    for mode in sorted(stats):
        s = stats[mode]
        lines.append(
            f"{mode:<8} {s.n:>4} {s.mean_revision_count:>9.2f} "
            f"{s.median_revision_count:>8.1f} {s.capsule_revised_rate:>9.2f} "
            f"{s.anchor_hit_cap_rate:>15.2f} {s.fact_hit_cap_rate:>13.2f} "
            f"{s.mean_secondary_signals:>11.2f}"
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
