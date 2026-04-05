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
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Use multi-agent specialist→answerer pipeline",
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

    # Lazy imports for fast startup
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(pitcher_id, args.window)
    except ValueError as e:
        log.error("%s", e)
        sys.exit(1)

    ctx = assemble_pitcher_context(pitcher_data)

    if args.pipeline:
        from pitcher_narratives.pipeline import write_pipeline_data_file

        data_file = write_pipeline_data_file(
            ctx, pitcher_id, args.provider, question=args.question,
        )
        log.info("Wrote prompt data to %s", data_file)

        from pitcher_narratives.analyst import ask_question_pipeline

        # The answer streams to stdout during this call
        print("# Answer\n")
        pipeline_result = ask_question_pipeline(
            args.question,
            ctx,
            pitcher_data,
            provider=args.provider,
            thinking=args.thinking,
            _model_override=model_override,
        )

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
    else:
        from pitcher_narratives.analyst import ANALYST_INSTRUCTIONS, ask_question_streaming
        from pathlib import Path

        # Write prompt data for single-agent path
        data_sections = [
            f"{'═' * 72}\nANALYST AGENT\n{'═' * 72}\n",
            f"## System Prompt\n\n{ANALYST_INSTRUCTIONS}\n",
            f"## User Question\n\n{args.question}\n",
            f"## Tool: get_pitcher_summary\n\n[Returns full pitcher context with league baselines]\n",
            f"## Tool: get_pitch_detail\n\n[Returns per-pitch detail on demand]\n",
        ]
        data_file = f"data-{pitcher_id}-{args.provider}-ask-single.md"
        Path(data_file).write_text("\n".join(data_sections))
        log.info("Wrote prompt data to %s", data_file)

        # The answer streams to stdout during this call
        print("# Answer\n")
        ask_question_streaming(
            args.question,
            ctx,
            pitcher_data,
            provider=args.provider,
            thinking=args.thinking,
            _model_override=model_override,
        )


if __name__ == "__main__":
    main()
