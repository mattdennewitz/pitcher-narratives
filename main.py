"""CLI entry point for pitcher scouting reports.

Parses command-line arguments, loads pitcher data, assembles context,
and generates an LLM-powered scouting report via streaming output.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for pitcher scouting reports."""
    parser = argparse.ArgumentParser(
        description="Generate pitcher scouting reports from Statcast data"
    )
    parser.add_argument(
        "-p", "--pitcher", type=int, required=True,
        help="MLB pitcher ID (e.g., 592155)"
    )
    parser.add_argument(
        "-w", "--window", type=int, default=30,
        help="Lookback window in days (default: 30)"
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: load pitcher data, assemble context, generate report."""
    args = parse_args()

    from data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(args.pitcher, args.window)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    from context import assemble_pitcher_context
    from pydantic_ai.exceptions import UserError
    from report import generate_report_streaming, check_hallucinated_metrics

    ctx = assemble_pitcher_context(pitcher_data)

    # Support test mode: use TestModel when env var is set
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        from pydantic_ai.models.test import TestModel

        model_override = TestModel(
            custom_output_text="[Test mode] Scouting report would appear here."
        )

    try:
        report_text = generate_report_streaming(ctx, _model_override=model_override)
    except UserError as e:
        if "ANTHROPIC_API_KEY" in str(e):
            print(
                "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
                "Get your key from https://console.anthropic.com/",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    # Post-generation hallucination check
    suspect = check_hallucinated_metrics(report_text)
    if suspect:
        print(
            f"\n⚠ Possible hallucinated metrics: {', '.join(suspect)}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
