"""CLI entry point for pitcher scouting reports.

Parses command-line arguments, loads pitcher data, assembles context,
and generates an LLM-powered scouting report via streaming output.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from pitcher_narratives.data import PitcherData

log = logging.getLogger("pitcher_narratives")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for pitcher scouting reports."""
    parser = argparse.ArgumentParser(description="Generate pitcher scouting reports from Statcast data")
    parser.add_argument("-p", "--pitcher", type=int, required=True, help="MLB pitcher ID (e.g., 592155)")
    parser.add_argument(
        "-w",
        "--window",
        type=int,
        default=30,
        help="Lookback window in days (default: 30)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show pitcher name, game dates, and pitch counts before generating report",
    )
    parser.add_argument(
        "--print-prompts", action="store_true", help="Print both prompts as sent to the LLM, then exit"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "claude", "gemini"],
        default="openai",
        help="LLM provider (default: openai)"
    )
    parser.add_argument(
        "--thinking",
        choices=["minimal", "low", "medium", "high", "xhigh"],
        default="medium",
        help="Thinking/reasoning effort level (default: medium)",
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Use multi-agent specialist→writer pipeline (v1.6 prototype)",
    )
    return parser.parse_args()


def _print_verbose_summary(data: PitcherData) -> None:
    """Log pitcher name, game dates, and pitch counts."""
    appearances = data.appearances.sort("game_date")
    log.info("%s (ID: %s, %sHP)", data.pitcher_name, data.pitcher_id, data.throws)
    log.info("%-12s %7s  Role", "Date", "Pitches")
    log.info("%s %s  %s", "─" * 12, "─" * 7, "─" * 4)
    for row in appearances.iter_rows(named=True):
        log.info("%-12s %7d  %s", row["game_date"], row["n_pitches"], row["role"])
    total = appearances["n_pitches"].sum()
    log.info("%s %s", "─" * 12, "─" * 7)
    log.info("%-12s %7d  (%d appearances)", "Total", total, len(appearances))


def _setup_logging() -> None:
    """Configure logging for pitcher_narratives to stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root = logging.getLogger("pitcher_narratives")
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def main() -> None:
    """Entry point: load pitcher data, assemble context, generate report."""
    load_dotenv()
    args = parse_args()
    _setup_logging()

    from pitcher_narratives.data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(args.pitcher, args.window)
    except ValueError as e:
        log.error("%s", e)
        sys.exit(1)

    if args.verbose:
        _print_verbose_summary(pitcher_data)

    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.report import (
        check_hallucinated_metrics,
        generate_report_streaming,
        print_prompts,
        write_data_file,
    )

    ctx = assemble_pitcher_context(pitcher_data)

    data_file = write_data_file(ctx, args.pitcher, args.provider)
    log.info("Wrote prompt data to %s", data_file)

    if args.print_prompts:
        print_prompts(ctx)
        sys.exit(0)

    # Support test mode: use TestModel when env var is set
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        from pydantic_ai.models.test import TestModel

        model_override = TestModel()

    # Pre-flight API key check — fail fast instead of hanging on missing key
    _API_KEYS = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
    if model_override is None and not os.environ.get(_API_KEYS[args.provider]):
        env_var = _API_KEYS[args.provider]
        log.error("%s not set.", env_var)
        sys.exit(1)

    if args.pipeline:
        from pitcher_narratives.pipeline import generate_pipeline_streaming, write_pipeline_data_file

        data_file = write_pipeline_data_file(ctx, args.pitcher, args.provider)
        log.info("Wrote prompt data to %s", data_file)

        # The narrative streams to stdout during this call
        print("# Scouting Report\n")
        pipe_result = generate_pipeline_streaming(
            ctx,
            provider=args.provider,
            thinking=args.thinking,
            _model_override=model_override,
        )

        # Executive summary
        if pipe_result.executive_summary:
            print("\n\n# Executive Summary\n")
            for bullet in pipe_result.executive_summary:
                print(f"- {bullet}")

        # Stuff analysis
        print(f"\n\n# Stuff Analysis\n\n{pipe_result.specialists.stuff}")

        # Data audit
        print("\n\n# Data Audit\n")
        if pipe_result.audit_flags:
            for f in pipe_result.audit_flags:
                print(f"- **[{f.category}]** {f.specialist}: {f.claim}")
                print(f"  - Data shows: {f.data_shows}")
        else:
            print("Clean — no issues found.")

        # Anchor check
        print("\n\n# Anchor Check\n")
        if pipe_result.revision_count == 0 and not pipe_result.anchor_warnings:
            print("Passed on first draft.")
        elif pipe_result.anchor_warnings:
            print(f"Revised {pipe_result.revision_count} time(s) — remaining issues:")
            for w in pipe_result.anchor_warnings:
                print(f"- **[{w.category}]** {w.description}")
        else:
            print(f"Revised {pipe_result.revision_count} time(s) — passed.")

        # Hallucination check
        hallucination_report = check_hallucinated_metrics(pipe_result.narrative)
    else:
        # The narrative streams to stdout during this call
        print("# Scouting Report\n")
        result = generate_report_streaming(
            ctx,
            provider=args.provider,
            thinking=args.thinking,
            _model_override=model_override,
        )

        # Executive summary
        if result.executive_summary:
            print("\n\n# Executive Summary\n")
            for bullet in result.executive_summary:
                print(f"- {bullet}")

        # Stuff analysis
        print(f"\n\n# Stuff Analysis\n\n{result.stuff_summary}")

        # Anchor check
        print("\n\n# Anchor Check\n")
        if result.revision_count == 0 and not result.anchor_warnings:
            print("Passed on first draft.")
        elif result.anchor_warnings:
            print(f"Revised {result.revision_count} time(s) — remaining issues:")
            for w in result.anchor_warnings:
                print(f"- **[{w.category}]** {w.description}")
        else:
            print(f"Revised {result.revision_count} time(s) — passed.")

        # Hallucination check
        hallucination_report = check_hallucinated_metrics(result.narrative)

    # Hallucination check (shared across both paths)
    if not hallucination_report.is_clean:
        print("\n\n# Hallucination Check\n")
        if hallucination_report.unknown_metrics:
            print(f"Unknown metrics referenced: {', '.join(hallucination_report.unknown_metrics)}")
        if hallucination_report.outcome_stat_warnings:
            print(
                f"Traditional outcome stats referenced "
                f"(prompt warns against these): "
                f"{', '.join(hallucination_report.outcome_stat_warnings)}"
            )


if __name__ == "__main__":
    main()
