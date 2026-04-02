"""CLI entry point for pitcher Q&A.

Parses a natural-language question, resolves the pitcher name,
loads data, and streams an answer from the analyst agent.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from dotenv import load_dotenv

__all__ = ["main", "parse_args"]

_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _extract_pitcher_name(
    question: str,
) -> tuple[str | None, "ResolveResult | None"]:
    """Extract a pitcher name from a question by trying phrases against the resolver.

    Tokenizes the question, strips possessives, and tries contiguous 3-word,
    2-word, then 1-word subsequences through the resolver. Returns the first
    definite match (exact, exact_last, fuzzy). If only ambiguous results are
    found, returns those for disambiguation. If nothing matches, returns
    (None, None).

    Args:
        question: Natural-language question containing a pitcher name.

    Returns:
        Tuple of (matched_query, ResolveResult) on success, or (None, result)
        for ambiguous, or (None, None) for not found.
    """
    from pitcher_narratives.resolver import ResolveResult, resolve  # noqa: F811

    # Tokenize and strip possessives, tracking capitalization
    words = question.split()
    cleaned: list[str] = []
    is_capitalized: list[bool] = []
    for idx, word in enumerate(words):
        # Remove trailing punctuation for matching, but keep the word itself
        w = re.sub(r"[?.!,;:]+$", "", word)
        # Strip possessives: "Cease's" -> "Cease", "Cease'" -> "Cease"
        w = re.sub(r"'s$", "", w)
        w = re.sub(r"'$", "", w)
        if w:
            cleaned.append(w)
            # Track if word was capitalized (proper noun indicator);
            # skip first word since sentence-initial caps are unreliable
            is_capitalized.append(idx > 0 and w[0].isupper())

    best_ambiguous: tuple[str | None, ResolveResult | None] = (None, None)

    # Try progressively shorter phrases: 3-word, 2-word, 1-word
    # Exact/exact_last matches are always accepted (high confidence).
    # Fuzzy and ambiguous results require at least one capitalized word
    # in the candidate phrase (proper noun heuristic) to avoid false
    # positives like "about" -> "Abbott" or "Tell me" -> ambiguous.
    for width in (3, 2, 1):
        for i in range(len(cleaned) - width + 1):
            candidate = " ".join(cleaned[i : i + width])
            result = resolve(candidate)
            if result.match_type in ("exact", "exact_last"):
                return (candidate, result)
            # For fuzzy/ambiguous, check capitalization:
            # - Single words: must be capitalized (proper noun heuristic)
            # - Multi-word: ALL words must be capitalized (e.g., "Dylan Cease"
            #   yes, "Johnson pitching" no -- "pitching" isn't a name)
            if width == 1:
                has_capital = is_capitalized[i]
            else:
                has_capital = all(is_capitalized[i + j] for j in range(width) if i + j < len(is_capitalized))
            if result.match_type == "fuzzy" and has_capital:
                return (candidate, result)
            if result.match_type == "ambiguous" and best_ambiguous[1] is None and has_capital:
                best_ambiguous = (None, result)

    # Return best ambiguous result or (None, None)
    return best_ambiguous


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
        default="high",
        help="Thinking/reasoning effort level (default: high)",
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

    if not args.question:
        print(
            'Usage: pitcher-ask "How is Cease pitching?"',
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve pitcher name from question text
    query, result = _extract_pitcher_name(args.question)

    if result is None:
        print(f"No pitcher found matching '{args.question}'", file=sys.stderr)
        sys.exit(1)

    if result.match_type == "ambiguous":
        print(
            "Multiple pitchers matched. Use a more specific name.",
            file=sys.stderr,
        )
        for i, (pid, name) in enumerate(result.candidates, 1):
            print(f"  {i}. {name} (ID: {pid})", file=sys.stderr)
        sys.exit(1)

    pitcher_id = result.pitcher_id
    print(f"Resolved: {result.pitcher_name} (ID: {pitcher_id})", file=sys.stderr)

    # Support test mode: use TestModel when env var is set
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        from pydantic_ai.models.test import TestModel

        model_override = TestModel()

    # Pre-flight API key check -- fail fast instead of hanging on missing key
    if model_override is None and not os.environ.get(_API_KEYS[args.provider]):
        env_var = _API_KEYS[args.provider]
        print(f"Error: {env_var} not set.", file=sys.stderr)
        sys.exit(1)

    # Lazy imports for fast startup
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(pitcher_id, args.window)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    ctx = assemble_pitcher_context(pitcher_data)

    if args.pipeline:
        from pitcher_narratives.pipeline import write_pipeline_data_file

        data_file = write_pipeline_data_file(
            ctx, pitcher_id, args.provider, question=args.question,
        )
        print(f"Wrote prompt data to {data_file}", file=sys.stderr)

        from pitcher_narratives.analyst import ask_question_pipeline

        result = ask_question_pipeline(
            args.question,
            ctx,
            pitcher_data,
            provider=args.provider,
            thinking=args.thinking,
            _model_override=model_override,
        )

        # Print audit flags
        if result.audit_flags:
            print(f"\nData audit flagged {len(result.audit_flags)} issue(s):", file=sys.stderr)
            for f in result.audit_flags:
                print(f"  [{f.category}] {f.specialist}: {f.claim}", file=sys.stderr)
        else:
            print("\nData audit: clean", file=sys.stderr)

        print(f"\n---\n{result.stuff_summary}")
    else:
        from pitcher_narratives.analyst import _ANALYST_INSTRUCTIONS, ask_question_streaming
        from pathlib import Path

        # Write prompt data for single-agent path
        data_sections = [
            f"{'═' * 72}\nANALYST AGENT\n{'═' * 72}\n",
            f"## System Prompt\n\n{_ANALYST_INSTRUCTIONS}\n",
            f"## User Question\n\n{args.question}\n",
            f"## Tool: get_pitcher_summary\n\n[Returns full pitcher context with league baselines]\n",
            f"## Tool: get_pitch_detail\n\n[Returns per-pitch detail on demand]\n",
        ]
        data_file = f"data-{pitcher_id}-{args.provider}-ask-single.md"
        Path(data_file).write_text("\n".join(data_sections))
        print(f"Wrote prompt data to {data_file}", file=sys.stderr)

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
