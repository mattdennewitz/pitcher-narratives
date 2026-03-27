"""CLI for scouting interesting pitcher appearances.

Scans recent appearances, scores them for interestingness, and prints
a ranked table. Optionally sends the top results to an LLM for curation.
"""

from __future__ import annotations

import argparse
import os
import sys

from pitcher_narratives.scout import scout_appearances


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the scout command."""
    parser = argparse.ArgumentParser(
        description="Find interesting pitcher appearances from recent games",
    )
    parser.add_argument(
        "-w",
        "--window",
        type=int,
        default=1,
        help="Number of days to scan (default: 1 = most recent game date)",
    )
    parser.add_argument(
        "-n",
        "--top",
        type=int,
        default=20,
        help="Number of results to show (default: 20)",
    )
    parser.add_argument(
        "--min-pitches",
        type=int,
        default=20,
        help="Minimum pitches for an appearance to be scored (default: 20)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum interest score to display (default: 0 = show all)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show signal details for each appearance",
    )
    parser.add_argument(
        "--curate",
        action="store_true",
        help="Send top results to an LLM to select the 3-5 most compelling stories",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "claude", "gemini"],
        default="openai",
        help="LLM provider for --curate (default: openai)",
    )
    return parser.parse_args()


def _print_table(results: list, *, verbose: bool) -> None:
    """Print the scored appearances table."""
    print(f"{'Score':>5}  {'Pitcher':<25} {'T':>1}  {'Date':<10}  {'#P':>3}  {'Signals'}")
    print(f"{'─' * 5}  {'─' * 25} {'─':>1}  {'─' * 10}  {'─' * 3}  {'─' * 40}")

    for r in results:
        signal_names = ", ".join(s.name for s in r.signals)
        print(
            f"{r.score:5.1f}  {r.pitcher_name:<25} {r.throws:>1}  {r.game_date!s:<10}  "
            f"{r.n_pitches:>3}  {signal_names}"
        )

        if verbose:
            for s in r.signals:
                print(f"       └─ {s.name} ({s.weight:.1f}): {s.detail}")
            print()


def main() -> None:
    """Entry point: scan appearances and print ranked results."""
    from dotenv import load_dotenv

    load_dotenv()
    args = parse_args()

    print("Scanning appearances...", file=sys.stderr)
    results = scout_appearances(
        window_days=args.window,
        top_n=args.top,
        min_pitches=args.min_pitches,
    )

    if args.min_score > 0:
        results = [r for r in results if r.score >= args.min_score]

    if not results:
        print("No interesting appearances found.", file=sys.stderr)
        sys.exit(0)

    # Print date range
    dates = sorted({r.game_date for r in results})
    if len(dates) == 1:
        print(f"\nAppearances from {dates[0]}", file=sys.stderr)
    else:
        print(f"\nAppearances from {dates[0]} to {dates[-1]}", file=sys.stderr)

    print(f"Showing top {len(results)} by interest score\n", file=sys.stderr)

    _print_table(results, verbose=args.verbose)

    if args.curate:
        # Check API key
        _API_KEYS = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
        env_var = _API_KEYS[args.provider]
        if not os.environ.get(env_var):
            print(f"\nError: {env_var} not set.", file=sys.stderr)
            sys.exit(1)

        from pitcher_narratives.curator import curate_appearances

        print(f"\n{'═' * 72}", file=sys.stderr)
        print("CURATOR — selecting top stories...", file=sys.stderr)
        print(f"{'═' * 72}\n", file=sys.stderr)

        curate_appearances(results, provider=args.provider)


if __name__ == "__main__":
    main()
