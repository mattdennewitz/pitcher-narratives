"""CLI entry point for pitcher scouting reports.

Parses command-line arguments, loads pitcher data via the data pipeline,
and outputs a brief verification summary.
"""

from __future__ import annotations

import argparse
import sys


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
    """Entry point: load pitcher data and generate report."""
    args = parse_args()

    from data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(args.pitcher, args.window)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    # Temporary verification output (replaced by report in Phase 4)
    n_total = len(pitcher_data.appearances)
    n_window = len(pitcher_data.window_appearances)
    roles = pitcher_data.appearances["role"].unique().sort().to_list()
    print(
        f"{pitcher_data.pitcher_name} ({pitcher_data.throws}HP) | "
        f"{n_total} appearances ({n_window} in {args.window}d window) | "
        f"Roles: {', '.join(roles)}"
    )


if __name__ == "__main__":
    main()
