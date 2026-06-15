"""CLI entry point for pitcher Q&A.

Parses a natural-language question, resolves the pitcher name,
loads data, and streams an answer from the tool-calling analyst agent.

The analyst agent is grounded in the pitcher's context and can call
`get_pitcher_summary` and `get_pitch_detail` tools on demand to answer
focused questions. Output is just the answer — no executive summary,
no audit dump, no stuff analysis (those belong to the narrative CLI).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from pitcher_narratives.config import API_KEYS, setup_logging
from pitcher_narratives.personas import ANSWER, PERSONAS, build_system_prompt, get_persona

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
        choices=["gemini", "claude"],
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
        "--persona",
        choices=list(PERSONAS.keys()),
        default="scout",
        help="Writer voice persona (default: scout)",
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

        # call_tools=[] so the deterministic test model does not blindly
        # invoke agents' reference tools (e.g. the skills toolset's
        # load_skill), which would fail on placeholder arguments.
        model_override = TestModel(call_tools=[])

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

    # Write prompt data for the analyst (tool-calling) path.
    # Unlike write_pipeline_data_file, this is simple: the analyst uses
    # tools dynamically at runtime, so the "prompt" is just the system
    # instructions plus the user question plus the tool descriptions.
    from pathlib import Path

    from pitcher_narratives.analyst import (
        ANALYST_MECHANICS,
        ask_question_streaming,
    )

    persona = get_persona(args.persona)
    composed_prompt = build_system_prompt(persona, ANSWER) + "\n\n" + ANALYST_MECHANICS

    data_sections = [
        f"{'═' * 72}\nANALYST AGENT\n{'═' * 72}\n",
        f"## Persona\n\n{persona.display_name} ({persona.id})\n",
        f"## System Prompt\n\n{composed_prompt}\n",
        f"## User Question\n\n{args.question}\n",
        "## Tool: get_pitcher_summary\n\n[Returns full pitcher context with league baselines]\n",
        "## Tool: get_pitch_detail\n\n[Returns per-pitch detail on demand]\n",
    ]
    data_file = f"data-{pitcher_id}-{args.provider}-ask.md"
    try:
        Path(data_file).write_text("\n".join(data_sections), encoding="utf-8")
    except OSError as e:
        log.error("Failed to write prompt data file: %s", e)
        sys.exit(1)
    log.info("Wrote prompt data to %s", data_file)

    # Lazy import: pydantic_ai.exceptions pulls in the whole package
    # (~330ms) and is only used in the except clause below.
    from pydantic_ai.exceptions import AgentRunError

    # Stream the answer to stdout. Output is just the answer — no
    # Executive Summary / Data Audit / Stuff Analysis sections (the
    # narrative CLI emits those; ask is focused Q&A).
    try:
        ask_question_streaming(
            args.question,
            ctx,
            pitcher_data,
            provider=args.provider,
            thinking=args.thinking,
            persona=persona,
            _model_override=model_override,
        )
    except AgentRunError as e:
        log.error("LLM call failed: %s", e)
        sys.exit(2)


if __name__ == "__main__":
    main()
