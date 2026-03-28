"""CLI entry point for pitcher scouting reports.

Parses command-line arguments, loads pitcher data, assembles context,
and generates an LLM-powered scouting report via streaming output.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from pitcher_narratives.data import PitcherData


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
    return parser.parse_args()


def _print_verbose_summary(data: PitcherData) -> None:
    """Print pitcher name, game dates, and pitch counts to stderr."""
    appearances = data.appearances.sort("game_date")
    print(
        f"\n{data.pitcher_name} (ID: {data.pitcher_id}, {data.throws}HP)",
        file=sys.stderr,
    )
    print(f"{'Date':<12} {'Pitches':>7}  Role", file=sys.stderr)
    print(f"{'─' * 12} {'─' * 7}  {'─' * 4}", file=sys.stderr)
    for row in appearances.iter_rows(named=True):
        print(
            f"{row['game_date']!s:<12} {row['n_pitches']:>7}  {row['role']}",
            file=sys.stderr,
        )
    total = appearances["n_pitches"].sum()
    print(f"{'─' * 12} {'─' * 7}", file=sys.stderr)
    print(
        f"{'Total':<12} {total:>7}  ({len(appearances)} appearances)\n",
        file=sys.stderr,
    )


def main() -> None:
    """Entry point: load pitcher data, assemble context, generate report."""
    load_dotenv()
    args = parse_args()

    from pitcher_narratives.data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(args.pitcher, args.window)
    except ValueError as e:
        print(str(e), file=sys.stderr)
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
    print(f"Wrote prompt data to {data_file}", file=sys.stderr)

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
        print(f"Error: {env_var} not set.", file=sys.stderr)
        sys.exit(1)

    result = generate_report_streaming(
        ctx,
        provider=args.provider,
        thinking=args.thinking,
        _model_override=model_override,
    )

    # Print social hook
    print(f"\n---\n{result.social_hook}")

    # Print fantasy insights
    print(f"\n---\n{result.fantasy_insights}")

    # Post-generation checks
    # 1. Anchor check warnings (from Phase 2.5)
    if result.anchor_warnings:
        print("\nANCHOR CHECK:", file=sys.stderr)
        for w in result.anchor_warnings:
            print(f"  [{w.category}] {w.description}", file=sys.stderr)

    # 2. Hallucination check (regex scan of narrative)
    hallucination_report = check_hallucinated_metrics(result.narrative)
    if not hallucination_report.is_clean:
        if hallucination_report.unknown_metrics:
            print(
                f"\nWARNING: Unknown metrics referenced: {', '.join(hallucination_report.unknown_metrics)}",
                file=sys.stderr,
            )
        if hallucination_report.outcome_stat_warnings:
            print(
                f"\nNOTE: Traditional outcome stats referenced "
                f"(prompt warns against these): "
                f"{', '.join(hallucination_report.outcome_stat_warnings)}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
