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
from pitcher_narratives.personas import PERSONAS, REPORT, get_narration_mode
from pitcher_narratives.temporal import _DEFAULT_RECENT_APPEARANCES

if TYPE_CHECKING:
    from pitcher_narratives.data import PitcherData
    from pitcher_narratives.personas import NarrationMode

log = logging.getLogger("pitcher_narratives")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments (subcommands: report, morning)."""
    parser = argparse.ArgumentParser(
        description="Pitcher scouting reports and morning digests from Statcast data",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Generate one pitcher's scouting report")
    # Note: required=False so `--list-personas` works standalone.
    # _run_report_command() re-asserts that -p is present when --list-personas is not used.
    report.add_argument("-p", "--pitcher", type=int, required=False, help="MLB pitcher ID (e.g., 592155)")
    report.add_argument(
        "-n",
        "--recent",
        type=int,
        default=_DEFAULT_RECENT_APPEARANCES,
        help=f"Analysis window in most-recent appearances (default: {_DEFAULT_RECENT_APPEARANCES})",
    )
    report.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show pitcher name, game dates, and pitch counts before generating report",
    )
    report.add_argument(
        "--print-prompts",
        action="store_true",
        help="Print the pipeline prompts that would be sent to the LLM, then exit without calling the model",
    )
    report.add_argument(
        "--provider",
        choices=["gemini", "claude"],
        default="gemini",
        help="LLM provider (default: gemini)"
    )
    report.add_argument(
        "--thinking",
        choices=["minimal", "low", "medium", "high", "xhigh"],
        default="medium",
        help="Thinking/reasoning effort level (default: medium)",
    )
    report.add_argument(
        "--persona",
        type=str.lower,
        choices=sorted(PERSONAS.keys()),
        default="scout",
        help="Writer persona to use (default: scout)",
    )
    report.add_argument(
        "--list-personas",
        action="store_true",
        help="List available personas (id, display name, description) and exit",
    )
    report.add_argument(
        "--mode",
        default=None,
        help=(
            "Narration mode(s), comma-separated. Phase 4: only 'report' is "
            "available (changes/recap land in later phases). Default: report."
        ),
    )

    morning = sub.add_parser("morning", help="Scout, select, and write the morning digest")
    morning.add_argument(
        "-w",
        "--window",
        type=int,
        default=1,
        help="Days to scan back from the most recent game date (default: 1)",
    )
    morning.add_argument(
        "--candidates",
        type=int,
        default=25,
        help="Scout candidates per role fed to the selector (default: 25)",
    )
    morning.add_argument(
        "--min-pitches",
        type=int,
        default=20,
        help="Minimum pitches for an appearance to be scored (default: 20)",
    )
    morning.add_argument(
        "--provider",
        choices=["gemini", "claude"],
        default="gemini",
        help="LLM provider (default: gemini)",
    )
    morning.add_argument(
        "--persona",
        type=str.lower,
        choices=sorted(PERSONAS.keys()),
        default="scout",
        help="Writer persona (default: scout)",
    )
    morning.add_argument(
        "--out",
        default="morning-runs",
        help="Output directory root (default: morning-runs)",
    )

    return parser.parse_args()


def _resolve_modes(raw: str | None) -> list["NarrationMode"]:
    """Parse the ``--mode`` flag into a list of NarrationMode instances.

    None (flag omitted) resolves to [REPORT]. Comma-separated ids are looked
    up via get_narration_mode; an unknown/not-yet-available id — or a non-None
    but empty value (e.g. "," or " ") — logs an error and exits non-zero
    (SystemExit code 2).
    """
    if raw is None:
        return [REPORT]

    ids = [m.strip() for m in raw.split(",") if m.strip()]
    if not ids:
        log.error("--mode was given but empty; expected comma-separated mode id(s).")
        sys.exit(2)
    modes = []
    for mode_id in ids:
        try:
            modes.append(get_narration_mode(mode_id))
        except ValueError as e:
            log.error("%s", e)
            sys.exit(2)
    return modes


def _print_personas() -> None:
    """Print all personas to stdout, sorted by id.

    Plain text output — one block per persona (id line, 4-space-indented
    display_name, 4-space-indented description), blank line between blocks.
    Pipe-friendly (no color codes).
    """
    items = sorted(PERSONAS.items(), key=lambda kv: kv[0])
    blocks = []
    for persona_id, persona in items:
        blocks.append(
            f"{persona_id}\n"
            f"    {persona.display_name}\n"
            f"    {persona.description}"
        )
    print("\n\n".join(blocks))


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
    """Entry point: dispatch to the report or morning subcommand."""
    load_dotenv()
    args = parse_args()
    if args.command == "morning":
        _run_morning_command(args)
    else:
        _run_report_command(args)


def _emit_mode_result(pipe_result, *, persona: str) -> bool:
    """Print one mode's post-stream sections and return whether unverified.

    Byte-identical to the report command's single-mode output. The
    empty-narrative case short-circuits the remaining sections for THIS
    mode only (it no longer aborts sibling modes in the caller's loop).
    """
    from pitcher_narratives.pipeline import check_hallucinated_metrics, is_unverified

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

    # Brief — a 2-3 sentence recent-vs-window summary. Always emit the heading
    # to keep the output format stable; show a fallback if the (non-critical)
    # brief agent produced nothing.
    print("\n\n# Brief\n")
    if pipe_result.brief:
        print(pipe_result.brief)
    else:
        print("_Brief unavailable — no text produced._")

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

    # Capsule fact-check (B). capsule_audit_flags is the post-re-audit residual:
    # issues that REMAIN in the saved report. Three states:
    #   revised + no residual  -> corrected and re-audit verified clean
    #   residual flags present -> still-unresolved issues (list them)
    #   neither                -> clean on first pass
    print("\n\n# Capsule Fact-Check\n")
    if pipe_result.capsule_revised and not pipe_result.capsule_audit_flags:
        # The streamed report above is the pre-correction draft; the corrected
        # text is the saved report (PipelineResult.narrative).
        print(
            "Auditor flagged issue(s); the fact-revision corrected them and the "
            "re-audit is clean. (The streamed report above is the pre-correction "
            "draft; the saved report is corrected.)"
        )
    elif pipe_result.capsule_audit_flags:
        n = len(pipe_result.capsule_audit_flags)
        if pipe_result.capsule_revised:
            print(
                f"Auditor revised the report, but {n} issue(s) remain after "
                "re-audit (saved report; the streamed draft above is pre-revision):"
            )
        else:
            print(f"Auditor flagged {n} issue(s) (not auto-corrected):")
        for f in pipe_result.capsule_audit_flags:
            print(f"- **[{f.category}]** {f.claim}")
            print(f"  - Data shows: {f.data_shows}")
    else:
        print("Clean — no factual issues found.")

    # Value parity (A, advisory). Covers the capsule and the reader-facing
    # summary/brief; each warning is prefixed with its surface.
    if pipe_result.value_parity_warnings:
        print("\n\n# Value Parity (advisory)\n")
        print("Report numbers with no match in the source data:")
        for w in pipe_result.value_parity_warnings:
            print(f"- {w}")

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
        return is_unverified(pipe_result)

    hallucination_report = check_hallucinated_metrics(
        pipe_result.narrative, persona=persona
    )

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

    return is_unverified(pipe_result)


def _run_report_command(args: argparse.Namespace) -> None:
    """Generate one pitcher's report (the pre-subcommand behavior)."""
    # --list-personas short-circuits BEFORE setup_logging, data loading,
    # and API key check. No LLM, no data file, no network.
    if args.list_personas:
        _print_personas()
        sys.exit(0)

    if args.pitcher is None:
        print(
            "pitcher-narratives: error: -p/--pitcher is required",
            file=sys.stderr,
        )
        sys.exit(2)

    setup_logging()

    # Lazy imports: polars is heavy (~90ms) and only referenced in the
    # except clause below. Keep module-level imports minimal so
    # `pitcher-narratives --help` stays fast.
    import polars as pl
    from pitcher_narratives.data import load_pitcher_data

    try:
        pitcher_data = load_pitcher_data(args.pitcher, args.recent)
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
        log.info("persona=%s", args.persona)
        _print_verbose_summary(pitcher_data)

    # Support test mode: use TestModel when env var is set
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        from pydantic_ai.models.test import TestModel

        # call_tools=[] so the deterministic test model does not blindly
        # invoke agents' reference tools (e.g. the skills toolset's
        # load_skill), which would fail on placeholder arguments.
        model_override = TestModel(call_tools=[])

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
        residual_banner,
        run_narration_modes,
        write_pipeline_data_file,
    )

    ctx = assemble_pitcher_context(pitcher_data)
    selected_modes = _resolve_modes(getattr(args, "mode", None))

    try:
        data_file, data_text = write_pipeline_data_file(
            ctx, args.pitcher, args.provider, persona=args.persona
        )
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
        results = run_narration_modes(
            ctx,
            modes=selected_modes,
            provider=args.provider,
            thinking=args.thinking,
            persona=args.persona,
            _model_override=model_override,
        )
    except AgentRunError as e:
        log.error("LLM call failed: %s", e)
        sys.exit(2)
    # Soft block: each mode's report is fully printed/saved, but if the
    # fact-check loop (B) could not ground every claim, warn loudly and exit
    # non-zero so callers/CI catch an UNVERIFIED report rather than treating
    # it as clean. The deterministic TestModel always emits synthetic audit
    # flags, so the hard exit is suppressed in test mode (the banner still
    # prints). Aggregated across all selected modes (G4): every mode's
    # sections are printed, banners for each unverified mode are emitted,
    # and the process exits non-zero once at the end if any mode was
    # unverified.
    any_unverified = False
    for mode in selected_modes:
        pipe_result = results[mode.id]
        if _emit_mode_result(pipe_result, persona=args.persona):
            any_unverified = True
            banner = residual_banner(pipe_result, label=mode.id.upper())
            print(f"\n{banner}", file=sys.stderr)

    if any_unverified and not os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        sys.exit(1)


def _run_morning_command(args: argparse.Namespace) -> None:
    """Run the morning editorial workflow."""
    env_var = API_KEYS[args.provider]
    if not os.environ.get(env_var):
        print(f"Error: {env_var} not set.", file=sys.stderr)
        sys.exit(1)
    setup_logging()

    from pathlib import Path

    # Lazy imports: pydantic_ai (~330ms) and polars (~90ms) are heavy, and
    # run_morning pulls in both. Importing at call time keeps
    # `pitcher-narratives --help` fast.
    import polars as pl
    from pydantic_ai.exceptions import AgentRunError

    from pitcher_narratives.morning import run_morning

    try:
        run_dir = run_morning(
            window_days=args.window,
            top_n=args.candidates,
            min_pitches=args.min_pitches,
            provider=args.provider,
            persona_id=args.persona,
            out_root=Path(args.out),
        )
    except AgentRunError as exc:
        print(f"Morning run failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, FileNotFoundError, pl.exceptions.PolarsError, OSError) as exc:
        print(f"Morning run failed: {exc}", file=sys.stderr)
        sys.exit(1)
    if run_dir is not None:
        print(f"\nRun artifacts: {run_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
