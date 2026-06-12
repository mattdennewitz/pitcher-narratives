#!/usr/bin/env python3
"""Run pitcher narratives for Claude and Gemini with cost tracking.

Usage:
    uv run python compare.py -p 573124
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from pitcher_narratives.costs import UsageTracker


_tracker = UsageTracker()


# ── Agent monkey-patching ──────────────────────────────────────────


def _model_name(model) -> str:
    if model is None:
        return "unknown"
    if isinstance(model, str):
        return model
    for attr in ("model_name", "name"):
        val = getattr(model, attr, None)
        if val is not None:
            return str(val() if callable(val) else val)
    return str(model)


def _install_tracking() -> None:
    """Monkey-patch pydantic-ai Agent to accumulate token usage."""
    from pydantic_ai import Agent

    orig_run = Agent.run

    async def tracked_run(self, *args, **kwargs):
        result = await orig_run(self, *args, **kwargs)
        usage = result.usage()
        _tracker.record(
            _model_name(kwargs.get("model") or self.model),
            usage.input_tokens or 0,
            usage.output_tokens or 0,
        )
        return result

    Agent.run = tracked_run  # type: ignore[method-assign]

    orig_run_stream = Agent.run_stream

    @asynccontextmanager
    async def tracked_run_stream(self, *args, **kwargs):
        async with orig_run_stream(self, *args, **kwargs) as stream:
            yield stream
        usage = stream.usage()
        _tracker.record(
            _model_name(kwargs.get("model") or self.model),
            usage.input_tokens or 0,
            usage.output_tokens or 0,
        )

    Agent.run_stream = tracked_run_stream  # type: ignore[method-assign]


# ── Helpers ─────────────────────────────────────────────────────────


def status(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _run_provider(provider: str, ctx) -> tuple[dict, dict]:
    from pitcher_narratives.pipeline import generate_pipeline_streaming

    _tracker.records.clear()
    t0 = time.time()

    # Suppress streaming output (the pipeline prints to stdout)
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        result = generate_pipeline_streaming(
            ctx, provider=provider, thinking="medium"
        )
    finally:
        sys.stdout = saved

    elapsed = time.time() - t0

    sections = {
        "narrative": result.narrative,
        "executive_summary": result.executive_summary,
        "stuff": result.specialists.stuff,
    }
    cost = {
        "table": _tracker.format_table(),
        "total": _tracker.total_cost(),
        "input": _tracker.total_input(),
        "output": _tracker.total_output(),
        "elapsed": elapsed,
    }
    return sections, cost


def _build_report(pitcher_id: int, results: dict) -> str:
    parts: list[str] = []

    for provider in ("claude", "gemini"):
        s = results[provider]["sections"]

        parts.append(f"# {provider}\n")

        parts.append("## executive summary\n")
        for bullet in s["executive_summary"]:
            parts.append(f"- {bullet}")
        parts.append("")

        parts.append("## report\n")
        parts.append(s["narrative"])
        parts.append("")

        parts.append("## stuff analysis\n")
        parts.append(s["stuff"])
        parts.append("\n")

    # ── Cost section ────────────────────────────────────────────
    parts.append("---\n")
    parts.append("# costs\n")

    for provider in ("claude", "gemini"):
        c = results[provider]["cost"]
        parts.append(f"## {provider}\n")
        parts.append(c["table"])
        parts.append(f"\n*{c['elapsed']:.1f}s elapsed*\n")

    grand = sum(r["cost"]["total"] for r in results.values())
    grand_in = sum(r["cost"]["input"] for r in results.values())
    grand_out = sum(r["cost"]["output"] for r in results.values())
    parts.append("## grand total\n")
    parts.append(f"- Input tokens: {grand_in:,}")
    parts.append(f"- Output tokens: {grand_out:,}")
    parts.append(f"- **Total cost: ${grand:.4f}**")

    return "\n".join(parts) + "\n"


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Compare pitcher reports: Claude vs Gemini"
    )
    parser.add_argument(
        "-p", "--pitcher", type=int, required=True, help="MLB pitcher ID"
    )
    args = parser.parse_args()

    from pitcher_narratives.config import API_KEYS, setup_logging

    # Pre-flight: check both API keys
    for provider in ("claude", "gemini"):
        key = API_KEYS[provider]
        if not os.environ.get(key):
            status(f"ERROR: {key} not set.")
            sys.exit(1)

    setup_logging()
    _install_tracking()

    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data

    status(f"Loading data for pitcher {args.pitcher}...")
    pitcher_data = load_pitcher_data(args.pitcher, 30)
    ctx = assemble_pitcher_context(pitcher_data)
    status(f"Loaded: {pitcher_data.pitcher_name}\n")

    results: dict = {}

    for provider in ("claude", "gemini"):
        status(f"{'─' * 50}")
        status(f" {provider.upper()} pipeline")
        status(f"{'─' * 50}")

        sections, cost = _run_provider(provider, ctx)
        results[provider] = {"sections": sections, "cost": cost}

        status(
            f"  {cost['input']:,} in / {cost['output']:,} out "
            f"= ${cost['total']:.4f} ({cost['elapsed']:.1f}s)\n"
        )

    report = _build_report(args.pitcher, results)
    outfile = f"report-{args.pitcher}.md"
    with open(outfile, "w") as f:
        f.write(report)

    status(f"Wrote {outfile}")
    grand = sum(r["cost"]["total"] for r in results.values())
    status(f"Total cost: ${grand:.4f}")


if __name__ == "__main__":
    main()
