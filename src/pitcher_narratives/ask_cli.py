"""CLI entry point for pitcher Q&A.

Parses a natural-language question, resolves the pitcher name,
loads data, and streams an answer from the analyst agent.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from pitcher_narratives.config import API_KEYS, setup_logging

__all__ = ["main", "parse_args"]

log = logging.getLogger("pitcher_narratives")




def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for pitcher Q&A.

    Returns:
        Parsed argument namespace with question, window, provider, and thinking.
    """
    parser = argparse.ArgumentParser(
        description="Ask a question about a pitcher's recent performance",
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Natural-language question about a pitcher (e.g., \"How is Cease pitching?\")",
    )
    parser.add_argument(
        "-w",
        "--window",
        type=int,
        default=30,
        help="Lookback window in days (default: 30)",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "claude", "gemini"],
        default="gemini",
        help="LLM provider (default: gemini)",
    )
    parser.add_argument(
        "--thinking",
        choices=["minimal", "low", "medium", "high", "xhigh"],
        default="medium",
        help="Thinking/reasoning effort level (default: medium)",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: parse question, resolve pitcher, load data, stream answer."""
    load_dotenv()
    args = parse_args()
    setup_logging()

    if not args.question:
        print(
            'Usage: pitcher-ask "How is Cease pitching?"',
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve pitcher name from question text
    from pitcher_narratives.resolver import extract_pitcher_from_question

    query, result = extract_pitcher_from_question(args.question)

    if result is None:
        log.error("No pitcher found matching '%s'", args.question)
        sys.exit(1)

    if result.match_type == "ambiguous":
        log.error("Multiple pitchers matched. Use a more specific name.")
        for i, (pid, name) in enumerate(result.candidates, 1):
            log.error("  %d. %s (ID: %s)", i, name, pid)
        sys.exit(1)

    pitcher_id = result.pitcher_id
    log.info("Resolved: %s (ID: %s)", result.pitcher_name, pitcher_id)

    # Support test mode: use TestModel when env var is set
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        from pydantic_ai.models.test import TestModel

        model_override = TestModel()

    # Pre-flight API key check -- fail fast instead of hanging on missing key
    if model_override is None and not os.environ.get(API_KEYS[args.provider]):
        env_var = API_KEYS[args.provider]
        log.error("%s not set.", env_var)
        sys.exit(1)

    # Lazy imports for fast startup — polars is ~90ms, and we only need
    # its exception type for the except clause below.
    import polars as pl
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(pitcher_id, args.window)
    except ValueError as e:
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

    ctx = assemble_pitcher_context(pitcher_data)

    from pitcher_narratives.analyst import ask_question_pipeline
    from pitcher_narratives.pipeline import write_pipeline_data_file

    try:
        data_file, _data_text = write_pipeline_data_file(
            ctx, pitcher_id, args.provider, question=args.question,
        )
    except OSError as e:
        log.error("Failed to write prompt data file: %s", e)
        sys.exit(1)
    log.info("Wrote prompt data to %s", data_file)

    # Lazy import: pydantic_ai.exceptions pulls in the whole package
    # (~330ms) and is only used in the except clause below.
    from pydantic_ai.exceptions import AgentRunError

    # The answer streams to stdout during this call
    print("# Answer\n")
    try:
        pipeline_result = ask_question_pipeline(
            args.question,
            ctx,
            provider=args.provider,
            thinking=args.thinking,
            _model_override=model_override,
        )
    except AgentRunError as e:
        log.error("LLM call failed: %s", e)
        sys.exit(2)

    # Executive summary
    if pipeline_result.executive_summary:
        print("\n\n# Executive Summary\n")
        for bullet in pipeline_result.executive_summary:
            print(f"- {bullet}")

    # Data audit
    print("\n\n# Data Audit\n")
    if pipeline_result.audit_flags:
        for f in pipeline_result.audit_flags:
            print(f"- **[{f.category}]** {f.specialist}: {f.claim}")
            print(f"  - Data shows: {f.data_shows}")
    else:
        print("Clean — no issues found.")

    # Stuff analysis
    print(f"\n\n# Stuff Analysis\n\n{pipeline_result.stuff_summary}")


if __name__ == "__main__":
    main()
