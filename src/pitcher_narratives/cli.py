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

from pitcher_narratives.config import API_KEYS, setup_logging

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
        "--print-prompts",
        action="store_true",
        help="Print the pipeline prompts that would be sent to the LLM, then exit without calling the model",
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


def main() -> None:
    """Entry point: load pitcher data, assemble context, generate report."""
    load_dotenv()
    args = parse_args()
    setup_logging()

    # Lazy imports: polars is heavy (~90ms) and only referenced in the
    # except clause below. Keep module-level imports minimal so
    # `pitcher-narratives --help` stays fast.
    import polars as pl
    from pitcher_narratives.data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(args.pitcher, args.window)
    except ValueError as e:
        # "Pitcher not found" and other user-input validation errors.
        log.error("%s", e)
        sys.exit(1)
    except FileNotFoundError as e:
        log.error("Data file not found: %s", e)
        sys.exit(1)
    except pl.exceptions.PolarsError as e:
        log.error("Failed to read pitcher data (polars): %s", e)
        sys.exit(1)
    except OSError as e:
        log.error("I/O error loading pitcher data: %s", e)
        sys.exit(1)

    if args.verbose:
        _print_verbose_summary(pitcher_data)

    # Support test mode: use TestModel when env var is set
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        from pydantic_ai.models.test import TestModel

        model_override = TestModel()

    # Pre-flight API key check — fail fast before writing files or hitting
    # the LLM. --print-prompts intentionally bypasses this check because it
    # never calls the model (it only renders the prompts that would be sent).
    if (
        not args.print_prompts
        and model_override is None
        and not os.environ.get(API_KEYS[args.provider])
    ):
        env_var = API_KEYS[args.provider]
        log.error("%s not set.", env_var)
        sys.exit(1)

    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.pipeline import (
        check_hallucinated_metrics,
        generate_pipeline_streaming,
        write_pipeline_data_file,
    )

    ctx = assemble_pitcher_context(pitcher_data)

    try:
        data_file, data_text = write_pipeline_data_file(ctx, args.pitcher, args.provider)
    except OSError as e:
        log.error("Failed to write prompt data file: %s", e)
        sys.exit(1)
    log.info("Wrote prompt data to %s", data_file)

    if args.print_prompts:
        # Use the text we just rendered — no disk roundtrip, no new failure
        # surface from re-reading the file we just wrote.
        print(data_text, file=sys.stderr)
        sys.exit(0)

    # Lazy import: pydantic_ai.exceptions pulls in the whole package
    # (~330ms) and is only used in the except clause below.
    from pydantic_ai.exceptions import AgentRunError

    # The narrative streams to stdout during this call
    print("# Scouting Report\n")
    try:
        pipe_result = generate_pipeline_streaming(
            ctx,
            provider=args.provider,
            thinking=args.thinking,
            _model_override=model_override,
        )
    except AgentRunError as e:
        log.error("LLM call failed: %s", e)
        sys.exit(2)

    # Executive summary — always emit the heading to keep the narrative
    # output format stable. If the summary agent failed to produce
    # bullets (empty list, parsing failure, or TestModel in tests), we
    # still show the section with a fallback message instead of silently
    # dropping it.
    print("\n\n# Executive Summary\n")
    if pipe_result.executive_summary:
        for bullet in pipe_result.executive_summary:
            print(f"- {bullet}")
    else:
        print("_Summary unavailable — no bullets produced._")

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

    # Hallucination check — skipped if the narrative is empty (pipeline
    # produced nothing, which is a failure worth flagging loudly).
    if not pipe_result.narrative:
        log.warning("Pipeline produced empty narrative — skipping hallucination check")
        return

    hallucination_report = check_hallucinated_metrics(pipe_result.narrative)

    if hallucination_report.is_clean:
        log.info("Hallucination check passed (no unknown metrics or outcome stats).")
    else:
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
