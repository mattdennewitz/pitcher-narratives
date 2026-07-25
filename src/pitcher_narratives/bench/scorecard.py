"""Scorecard aggregation and report rendering for bench runs.

Pure functions: judged records in, per-provider/tier/dimension means and
a markdown report out. No LLM, no I/O.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from pitcher_narratives.bench.rubric import (
    AGENT_RUBRIC,
    CAPSULE_RUBRIC,
    JudgedOutput,
    weighted_overall,
)

__all__ = ["JudgedRecord", "aggregate", "render_report"]


@dataclass
class JudgedRecord:
    """One judge's verdict on one output."""

    provider: str
    """Author of the judged output."""

    tier: str
    """'specialist:<name>' or 'capsule:<mode>'."""

    judge: str
    """Provider that produced this verdict."""

    judged: JudgedOutput


def _rubric_for(tier: str):
    return CAPSULE_RUBRIC if tier.split(":", 1)[0] == "capsule" else AGENT_RUBRIC


def aggregate(records: list[JudgedRecord]) -> dict:
    """Aggregate judged records into per-provider/tier means.

    Returns:
        {provider: {tier: {"dimensions": {key: mean}, "overall": float,
                           "judges": [..]}}}
        Dimension means average across judges; overall is the weighted
        mean of the per-judge weighted overalls.
    """
    by_key: dict[tuple[str, str], list[JudgedRecord]] = defaultdict(list)
    for r in records:
        by_key[(r.provider, r.tier)].append(r)

    result: dict = {}
    for (provider, tier), recs in by_key.items():
        rubric = _rubric_for(tier)
        dim_scores: dict[str, list[int]] = defaultdict(list)
        overalls: list[float] = []
        for r in recs:
            for s in r.judged.scores:
                dim_scores[s.dimension].append(s.score)
            overalls.append(weighted_overall(r.judged.scores, rubric))
        result.setdefault(provider, {})[tier] = {
            "dimensions": {k: sum(v) / len(v) for k, v in dim_scores.items()},
            "overall": sum(overalls) / len(overalls) if overalls else 0.0,
            "judges": sorted({r.judge for r in recs}),
        }
    return result


def render_report(agg: dict, *, meta: dict) -> str:
    """Render the aggregate as a markdown scorecard report."""
    lines = ["# LLM Bench Scorecard", ""]
    for k, v in meta.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    providers = sorted(agg.keys())
    tiers = sorted({t for p in agg.values() for t in p})

    # Overall summary table: tier x provider
    lines.append("## Overall (weighted 1-5)")
    lines.append("")
    lines.append("| Tier | " + " | ".join(providers) + " |")
    lines.append("|------|" + "|".join(["------"] * len(providers)) + "|")
    for tier in tiers:
        row = [f"| {tier} "]
        for p in providers:
            cell = agg.get(p, {}).get(tier)
            row.append(f"| {cell['overall']:.2f} " if cell else "| -- ")
        lines.append("".join(row) + "|")
    lines.append("")

    # Per-tier dimension breakdown
    for tier in tiers:
        lines.append(f"## {tier}")
        lines.append("")
        dims = sorted({d for p in providers for d in agg.get(p, {}).get(tier, {}).get("dimensions", {})})
        lines.append("| Dimension | " + " | ".join(providers) + " |")
        lines.append("|-----------|" + "|".join(["------"] * len(providers)) + "|")
        for dim in dims:
            row = [f"| {dim} "]
            for p in providers:
                val = agg.get(p, {}).get(tier, {}).get("dimensions", {}).get(dim)
                row.append(f"| {val:.2f} " if val is not None else "| -- ")
            lines.append("".join(row) + "|")
        judges = {
            p: ", ".join(agg.get(p, {}).get(tier, {}).get("judges", []))
            for p in providers
            if agg.get(p, {}).get(tier)
        }
        for p, j in judges.items():
            lines.append(f"- {p} judged by: {j}")
        lines.append("")

    return "\n".join(lines)
