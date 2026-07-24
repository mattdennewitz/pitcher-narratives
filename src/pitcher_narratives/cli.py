"""CLI entry point for pitcher scouting reports.

Parses command-line arguments, loads pitcher data, assembles context,
and generates an LLM-powered scouting report printed to stdout.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from pitcher_narratives.config import API_KEYS, PROVIDERS, setup_logging
from pitcher_narratives.personas import REPORT, get_narration_mode
from pitcher_narratives.temporal import _DEFAULT_PRIOR_APPEARANCES, _DEFAULT_RECENT_APPEARANCES

if TYPE_CHECKING:
    from pitcher_narratives.data import PitcherData
    from pitcher_narratives.personas import NarrationMode
    from pitcher_narratives.pipeline import PipelineResult

log = logging.getLogger("pitcher_narratives")


def _make_grounded_test_model():
    """Return a deterministic model whose synthetic prose obeys provenance."""
    import hashlib
    import re

    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    def collect_text(messages) -> str:
        chunks: list[str] = []

        def visit(value) -> None:
            if isinstance(value, str):
                chunks.append(value)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)

        for message in messages:
            for part in message.parts:
                if getattr(part, "part_kind", None) == "user-prompt":
                    visit(getattr(part, "content", None))
        return "\n".join(chunks)

    def respond(messages, info):
        output_tool = info.output_tools[0]
        properties = output_tool.parameters_json_schema.get("properties", {})
        prompt = collect_text(messages)
        fact_ids = re.findall(r"\[(fact:[A-Za-z0-9_-]+)\]", prompt)

        if {"observations", "supported_interpretations", "limitations"}.issubset(properties):
            claims = []
            if fact_ids:
                claims.append(
                    {
                        "text": (
                            "The cited producer fact is available "
                            f"for prompt {hashlib.sha256(prompt.encode()).hexdigest()[:8]}."
                        ),
                        "claim_type": "observation",
                        "confidence": "high",
                        "fact_ids": [fact_ids[0]],
                    }
                )
            args = {
                "observations": claims,
                "supported_interpretations": [],
                "limitations": [],
            }
        elif "flags" in properties:
            args = {"flags": []}
        elif "warnings" in properties:
            args = {"warnings": []}
        elif {"state", "top_improvement", "top_concern", "secondary"}.issubset(properties):
            args = {
                "state": "no_material_signal",
                "top_improvement": None,
                "top_concern": None,
                "secondary": [],
            }
        elif {"content", "claims"}.issubset(properties):
            source = re.search(
                r"\[claim:([a-z-]+:[A-Za-z0-9_-]+)\][^\n]*\[(fact:[A-Za-z0-9_-]+)\]",
                prompt,
            )
            text = "Synthetic grounded output."
            args = {
                "content": f"- {text}" if source else "",
                "claims": (
                    [
                        {
                            "text": text,
                            "fact_ids": [source.group(2)],
                            "source_claim_ids": [source.group(1)],
                            "claim_type": "observation",
                        }
                    ]
                    if source
                    else []
                ),
            }
        else:
            args = {}
        return ModelResponse(parts=[ToolCallPart(tool_name=output_tool.name, args=args)])

    return FunctionModel(respond)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments (subcommands: report, morning)."""
    parser = argparse.ArgumentParser(
        description="Pitcher scouting reports and morning digests from PitchingPlus outputs",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Generate one pitcher's scouting report")
    report.add_argument("-p", "--pitcher", type=int, required=False, help="MLB pitcher ID (e.g., 592155)")
    report.add_argument(
        "-n",
        "--recent",
        type=int,
        default=_DEFAULT_RECENT_APPEARANCES,
        help=f"Analysis window in most-recent appearances (default: {_DEFAULT_RECENT_APPEARANCES})",
    )
    report.add_argument(
        "--prior",
        type=int,
        default=_DEFAULT_PRIOR_APPEARANCES,
        help=(
            "Prior-window size in appearances for CHANGES mode's recent-vs-prior "
            f"comparison (default: {_DEFAULT_PRIOR_APPEARANCES}). Ignored by "
            "report/recap modes."
        ),
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
        "--provider", choices=["gemini", "claude"], default="gemini", help="LLM provider (default: gemini)"
    )
    report.add_argument(
        "--thinking",
        choices=["minimal", "low", "medium", "high", "xhigh"],
        default="medium",
        help="Thinking/reasoning effort level (default: medium)",
    )
    report.add_argument(
        "--mode",
        default=None,
        help=("Comma-separated narration modes: report, recap, changes (default: report)."),
    )
    report.add_argument(
        "--metrics-out",
        default=None,
        help=(
            "Append one JSON line per (pitcher, mode) run to this path, for "
            "offline depth calibration (see docs/calibration.md). Off by default."
        ),
    )
    report.add_argument(
        "--diagnostics-file",
        default=None,
        help=(
            "Write the QA/diagnostics appendix as JSON to this path (one object "
            "per narration mode). Off by default; stdout stays the reader report."
        ),
    )

    report.add_argument(
        "--no-explain-model",
        action="store_false",
        dest="explain_model",
        default=True,
        help=(
            "Omit the deterministic Pitching+ model-and-data-boundary section "
            "for readers who already know the grading system. Included by default."
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
        "--starters-only",
        action="store_true",
        help="Restrict the board to starting pitchers (role SP) before selection",
    )
    morning.add_argument(
        "--provider",
        choices=["gemini", "claude"],
        default="gemini",
        help="LLM provider (default: gemini)",
    )
    morning.add_argument(
        "--out",
        default="morning-runs",
        help="Output directory root (default: morning-runs)",
    )
    morning.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Run the metric-hallucination cross-check on every digest entry "
            "(fully validates the run, at a small per-entry cost). Off by "
            "default: the fast digest runs the anchor + fact-audit loops but "
            "skips this cross-check."
        ),
    )

    scoreboard = sub.add_parser(
        "scoreboard",
        help="Print the scouted board only (no LLM) — the morning full board",
    )
    scoreboard.add_argument(
        "-w",
        "--window",
        type=int,
        default=1,
        help="Days to scan back from the most recent game date (default: 1)",
    )
    scoreboard.add_argument(
        "--min-pitches",
        type=int,
        default=20,
        help="Minimum pitches for an appearance to be scored (default: 20)",
    )
    scoreboard.add_argument(
        "--starters-only",
        action="store_true",
        help="Restrict the board to starting pitchers (role SP)",
    )
    scoreboard.add_argument(
        "--format",
        choices=["table", "md", "json"],
        default="md",
        help="Output format: fixed-width table, markdown board, or JSON (default: md)",
    )
    scoreboard.add_argument(
        "-n",
        "--top",
        type=int,
        default=0,
        help="Keep only the top N appearances per role by score (default: 0 = no limit)",
    )
    scoreboard.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Drop appearances below this interest score (default: 0.0 = keep all)",
    )
    scoreboard.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="In table format, show a per-signal detail row under each appearance",
    )
    scoreboard.add_argument(
        "--curate",
        action="store_true",
        help="Run the LLM selector on the board and print the selected slate",
    )
    scoreboard.add_argument(
        "--provider",
        choices=["gemini", "claude"],
        default="gemini",
        help="LLM provider for --curate (default: gemini)",
    )

    ask = sub.add_parser("ask", help="Explain why a pitcher's pitch earns its P+/S+/L+ grade")
    ask.add_argument("question", help='e.g. "why does Jared Jones\'s fastball grade 92 stuff+"')
    ask.add_argument(
        "--provider", default="gemini", choices=sorted(PROVIDERS), help="LLM provider (default: gemini)"
    )

    return parser.parse_args()


def _resolve_modes(raw: str | None) -> list[NarrationMode]:
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
    elif args.command == "scoreboard":
        _run_scoreboard_command(args)
    elif args.command == "ask":
        _run_ask_command(args)
    else:
        _run_report_command(args)


def build_diagnostics_dict(pipe_result) -> dict:
    """Collect a mode's QA/diagnostics data into a JSON-serializable dict.

    Runs the hallucination guard (only when the narrative is non-empty, matching
    the historical behavior). Pure apart from that read-only guard call.
    """
    from pitcher_narratives.models import render_specialist_analysis
    from pitcher_narratives.pipeline import check_hallucinated_metrics, is_unverified

    diag = {
        # A mode with no capsule is not "verified" — there's nothing to verify.
        # has_capsule lets a JSON consumer tell an empty/failed report apart
        # from a genuinely clean one (both would otherwise be verified=true).
        "has_capsule": bool(pipe_result.narrative),
        "verified": bool(pipe_result.narrative) and not is_unverified(pipe_result),
        "capsule_revised": pipe_result.capsule_revised,
        "revision_count": pipe_result.revision_count,
        "stuff_analysis": render_specialist_analysis(pipe_result.specialists.stuff),
        "data_audit": [
            {"category": f.category, "specialist": f.specialist, "claim": f.claim, "data_shows": f.data_shows}
            for f in pipe_result.audit_flags
        ],
        "capsule_fact_check": [
            {"category": f.category, "claim": f.claim, "data_shows": f.data_shows}
            for f in pipe_result.capsule_audit_flags
        ],
        "anchor_warnings": [
            {"category": w.category, "description": w.description} for w in pipe_result.anchor_warnings
        ],
        "value_parity_warnings": list(pipe_result.value_parity_warnings),
        "reader_claim_warnings": list(pipe_result.reader_claim_warnings),
        "hallucination": {
            "unknown_metrics": [],
            "outcome_stat_warnings": [],
            "unsupported_claim_warnings": [],
        },
    }
    generated_narrative = (
        pipe_result.narrative_artifact.content
        if pipe_result.narrative_artifact is not None
        else pipe_result.narrative
    )
    if generated_narrative:
        hr = check_hallucinated_metrics(
            generated_narrative,
            capabilities=pipe_result.analysis_capabilities,
            cited_fact_ids=pipe_result.narrative_fact_ids,
        )
        diag["hallucination"] = {
            "unknown_metrics": list(hr.unknown_metrics),
            "outcome_stat_warnings": list(hr.outcome_stat_warnings),
            "unsupported_claim_warnings": list(hr.unsupported_claim_warnings),
        }
        recomputed_warnings = [
            *(f"Unknown metric: {metric}" for metric in hr.unknown_metrics),
            *(f"Unsupported outcome statistic: {metric}" for metric in hr.outcome_stat_warnings),
            *hr.unsupported_claim_warnings,
        ]
        diag["reader_claim_warnings"] = list(
            dict.fromkeys([*diag["reader_claim_warnings"], *recomputed_warnings])
        )
    diag["verified"] = diag["verified"] and not diag["reader_claim_warnings"]
    return diag


def render_diagnostics_text(diag: dict) -> str:
    """Format a diagnostics dict as the markdown QA appendix."""
    lines = ["## Diagnostics", "", "### Stuff Analysis", "", diag["stuff_analysis"]]

    lines += ["", "### Data Audit", ""]
    if diag["data_audit"]:
        for f in diag["data_audit"]:
            lines.append(f"- **[{f['category']}]** {f['specialist']}: {f['claim']}")
            lines.append(f"  - Data shows: {f['data_shows']}")
    else:
        lines.append("Clean — no issues found.")

    lines += ["", "### Capsule Fact-Check", ""]
    if diag["capsule_revised"] and not diag["capsule_fact_check"]:
        lines.append("Auditor flagged issue(s); the fact-revision corrected them and the re-audit is clean.")
    elif diag["capsule_fact_check"]:
        n = len(diag["capsule_fact_check"])
        if diag["capsule_revised"]:
            lines.append(f"Auditor revised the report, but {n} issue(s) remain after re-audit:")
        else:
            lines.append(f"Auditor flagged {n} issue(s) (not auto-corrected):")
        for f in diag["capsule_fact_check"]:
            lines.append(f"- **[{f['category']}]** {f['claim']}")
            lines.append(f"  - Data shows: {f['data_shows']}")
    else:
        lines.append("Clean — no factual issues found.")

    if diag["value_parity_warnings"]:
        lines += ["", "### Value Parity (advisory)", "", "Report numbers with no match in the source data:"]
        for w in diag["value_parity_warnings"]:
            lines.append(f"- {w}")

    lines += ["", "### Anchor Check", ""]
    if diag["revision_count"] == 0 and not diag["anchor_warnings"]:
        lines.append("Passed on first draft.")
    elif diag["anchor_warnings"]:
        lines.append(f"Revised {diag['revision_count']} time(s) — remaining issues:")
        for w in diag["anchor_warnings"]:
            lines.append(f"- **[{w['category']}]** {w['description']}")
    else:
        lines.append(f"Revised {diag['revision_count']} time(s) — passed.")

    if diag["reader_claim_warnings"]:
        lines += ["", "### Reader Claim Guard", ""]
        lines.extend(f"- {warning}" for warning in diag["reader_claim_warnings"])

    return "\n".join(lines)


def _emit_mode_result(pipe_result, *, mode, verbose: bool = False) -> tuple[bool, dict]:
    """Print one mode's reader-facing sections to stdout; diagnostics stay off it.

    Returns (unverified, diagnostics_dict). Called immediately after the
    mode's capsule is rendered, so the whole mode block is contiguous on stdout.
    """
    from pitcher_narratives.pipeline import is_unverified

    # Diagnostics are built up front (this also runs the hallucination guard for
    # every mode) so the stdout hallucination pointer below can consult them;
    # they are only *displayed* on -v, or written to the JSON sidecar by the caller.
    diag = build_diagnostics_dict(pipe_result)

    # The capsule — the final, post-fact-revision narrative, printed exactly
    # once. The pipeline buffers the writer output (no live streaming), so this
    # is the single authoritative copy under the mode's H1 title.
    if pipe_result.narrative:
        print(pipe_result.narrative)
    else:
        # No generated capsule is a failed mode result, never a successful
        # no-op. Keep stdout explicit and let the caller return non-zero.
        log.warning("Pipeline produced an empty narrative — no capsule is publishable.")
        print("_No capsule was produced._")

    n_reader_claim_flags = len(diag["reader_claim_warnings"])
    unverified = is_unverified(pipe_result) or bool(n_reader_claim_flags)
    if unverified:
        n_fact = len(pipe_result.capsule_audit_flags)
        n_anchor = len(pipe_result.anchor_warnings)
        print(
            f"\n\n**Verification:** ⚠️ UNVERIFIED — {n_fact} residual "
            f"fact-check flag(s), {n_anchor} anchor warning(s), "
            f"{n_reader_claim_flags} reader claim/metric warning(s). "
            "See diagnostics (-v or --diagnostics-file)."
        )
    else:
        print("\n\n**Verification:** ✅ Verified — all gating checks clean.")

    # Reader-claim failures gate verification and remain visible without -v.
    if n_reader_claim_flags:
        print(
            f"\n\n**Note:** {n_reader_claim_flags} reader claim/metric flag(s) "
            "present — see diagnostics (-v or --diagnostics-file)."
        )

    # Distilled section — only for modes that ran the distillation agent.
    # RECAP's capsule is already a brief; a summary of a summary is noise.
    if mode.distill:
        print("\n\n## Executive Summary\n")
        if unverified:
            print("_Summary withheld — reader or validation checks are unverified._")
        elif pipe_result.executive_summary:
            for bullet in pipe_result.executive_summary:
                print(f"- {bullet}")
        else:
            print("_Summary unavailable — no bullets produced._")

    # ── Diagnostics: off the reader stream ──────────────────────────────
    # (diag was built up front — the hallucination guard has already run.)
    if verbose:
        print("\n\n---\n", file=sys.stderr)
        print(render_diagnostics_text(diag), file=sys.stderr)

    return unverified, diag


def _write_diagnostics_file(path, diagnostics_by_mode: dict) -> None:
    """Write per-mode diagnostics dicts to a JSON file (keyed by mode id)."""
    import json
    from pathlib import Path

    Path(path).write_text(json.dumps(diagnostics_by_mode, indent=2, default=str))


def _append_metrics_records(
    path,
    *,
    pitcher_id: int,
    span: int,
    modes: list[NarrationMode],
    results: dict[str, PipelineResult],
) -> None:
    """Append per-mode calibration records (JSONL) to ``path``.

    One line per result, opened in append mode so repeated runs accumulate
    rather than overwrite. Mode objects supply the depth caps recorded by
    ``flag_record``.
    """
    import json
    from pathlib import Path

    from pitcher_narratives.pipeline import flag_record

    modes_by_id = {m.id: m for m in modes}
    lines = [
        json.dumps(flag_record(modes_by_id[mode_id], pitcher_id, result, span=span))
        for mode_id, result in results.items()
    ]

    with Path(path).open("a") as f:
        for line in lines:
            f.write(line + "\n")


def _run_ask_command(args: argparse.Namespace) -> None:
    """Answer a single grade-explanation question and print the prose."""
    import asyncio

    from pitcher_narratives.qa import QuestionError, answer_question

    setup_logging()
    try:
        answer = asyncio.run(answer_question(args.question, provider=args.provider))
    except QuestionError as e:
        print(f"pitcher-narratives: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:  # pitcher id not present in Statcast data
        print(f"pitcher-narratives: {e}", file=sys.stderr)
        sys.exit(1)
    print(answer)


def _run_report_command(args: argparse.Namespace) -> None:
    """Generate one pitcher's report (the pre-subcommand behavior)."""
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
        _print_verbose_summary(pitcher_data)

    # Test mode still exercises every typed boundary. Its deterministic model
    # emits real prompt citations rather than bypassing provenance validation.
    model_override = None
    if os.environ.get("PITCHER_NARRATIVES_TEST_MODEL"):
        model_override = _make_grounded_test_model()

    # Pre-flight API key check — fail fast before writing files or hitting
    # the LLM. --print-prompts intentionally bypasses this check because it
    # never calls the model (it only renders the prompts that would be sent).
    if not args.print_prompts and model_override is None and not os.environ.get(API_KEYS[args.provider]):
        env_var = API_KEYS[args.provider]
        log.error("%s not set.", env_var)
        sys.exit(1)

    from pitcher_narratives.context import assemble_pitcher_context, assemble_prior_context
    from pitcher_narratives.pipeline import (
        residual_banner,
        run_narration_modes,
        write_pipeline_data_file,
    )
    from pitcher_narratives.temporal import TemporalFrame

    ctx = assemble_pitcher_context(pitcher_data)
    selected_modes = _resolve_modes(getattr(args, "mode", None))

    needs_prior = any(TemporalFrame.PRIOR in m.temporal_frame for m in selected_modes)
    prior_ctx = assemble_prior_context(pitcher_data, args.recent, args.prior) if needs_prior else None

    try:
        data_file, data_text = write_pipeline_data_file(ctx, args.pitcher, args.provider, prior_ctx=prior_ctx)
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

    # One contiguous labeled block per mode: H1 title, streamed capsule,
    # reader-facing sections, diagnostics appendix. Duplicate --mode ids
    # are deduped here so a mode never streams twice.
    any_unverified = False
    results: dict[str, PipelineResult] = {}
    diagnostics_by_mode: dict[str, dict] = {}
    first = True
    for mode in selected_modes:
        if mode.id in results:
            continue
        print(f"{'' if first else chr(10) * 2}# {mode.title}\n")
        first = False
        try:
            mode_results = run_narration_modes(
                ctx,
                modes=[mode],
                provider=args.provider,
                thinking=args.thinking,
                explain_model=args.explain_model,
                _model_override=model_override,
                prior_ctx=prior_ctx,
            )
        except AgentRunError as e:
            log.error("LLM call failed: %s", e)
            sys.exit(2)
        pipe_result = mode_results[mode.id]
        results[mode.id] = pipe_result
        unverified, diag = _emit_mode_result(
            pipe_result,
            mode=mode,
            verbose=args.verbose,
        )
        diagnostics_by_mode[mode.id] = diag
        if unverified:
            any_unverified = True
            banner = residual_banner(pipe_result, label=mode.id.upper())
            if banner is None:
                banner = (
                    f"⚠️  {mode.id.upper()} UNVERIFIED — deterministic reader "
                    "claim/metric guard failed. Review diagnostics before use."
                )
            print(f"\n{banner}", file=sys.stderr)

    if args.diagnostics_file:
        try:
            _write_diagnostics_file(args.diagnostics_file, diagnostics_by_mode)
        except OSError as e:
            log.error("Failed to write diagnostics file: %s", e)

    # Soft block: each mode's report is fully printed/saved, but if the
    # fact-check loop (B) could not ground every claim, warn loudly and exit
    # non-zero so callers/CI catch an UNVERIFIED report rather than treating
    # it as clean. The deterministic TestModel always emits synthetic audit
    # flags, so the hard exit is suppressed in test mode (the banner still
    # prints). Aggregated across all selected modes (G4): every mode's
    # sections are printed, banners for each unverified mode are emitted,
    # and the process exits non-zero once at the end if any mode was
    # unverified. The per-mode emit loop above already aggregated
    # ``any_unverified`` across the deduped results and printed each banner.

    if args.metrics_out:
        _append_metrics_records(
            args.metrics_out,
            pitcher_id=args.pitcher,
            span=args.recent,
            modes=selected_modes,
            results=results,
        )

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
            out_root=Path(args.out),
            starters_only=args.starters_only,
            strict=args.strict,
        )
    except AgentRunError as exc:
        print(f"Morning run failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, FileNotFoundError, pl.exceptions.PolarsError, OSError) as exc:
        print(f"Morning run failed: {exc}", file=sys.stderr)
        sys.exit(1)
    if run_dir is not None:
        print(f"\nRun artifacts: {run_dir}", file=sys.stderr)


def _run_scoreboard_command(args: argparse.Namespace) -> None:
    """Print the scouted full board to stdout — no LLM unless --curate is set."""
    setup_logging()

    # --curate produces a human-readable slate; it has no place in machine JSON,
    # and the JSON branch returns before the curate block. Fail fast rather than
    # silently ignoring the flag.
    if args.curate and args.format == "json":
        print(
            "Error: --curate is not supported with --format json (curation prints a human-readable slate).",
            file=sys.stderr,
        )
        sys.exit(2)

    # -v adds per-signal detail rows, which only the table renderer emits; under
    # any other format it would be a silent no-op, so say so.
    if args.verbose and args.format != "table":
        log.warning(
            "-v/--verbose only affects --format table; it is ignored for --format %s.",
            args.format,
        )

    # Lazy imports: polars (~90ms) and the scout/digest modules are heavy;
    # importing at call time keeps `pitcher-narratives --help` fast.
    import polars as pl

    from pitcher_narratives.digest import (
        render_curation_slate,
        render_full_board,
        render_full_board_json,
        render_full_board_table,
    )
    from pitcher_narratives.scout import scout_appearances, top_per_role

    try:
        board = scout_appearances(window_days=args.window, min_pitches=args.min_pitches)
    except (ValueError, FileNotFoundError, pl.exceptions.PolarsError, OSError) as exc:
        print(f"Scoreboard failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.starters_only:
        board = [a for a in board if a.role == "SP"]
    if args.top > 0:
        board = top_per_role(board, args.top)
    if args.min_score > 0:
        board = [a for a in board if a.score >= args.min_score]

    # JSON always emits valid output (empty board -> empty appearances list) so
    # downstream consumers can parse stdout unconditionally.
    if args.format == "json":
        print(render_full_board_json(board))
        return

    if not board:
        noun = "starter appearances" if args.starters_only else "appearances"
        print(f"No interesting {noun} found — quiet day.", file=sys.stderr)
        return

    game_date = max(a.game_date for a in board)
    print(f"# Scoreboard — {game_date}\n")
    if args.format == "table":
        print(render_full_board_table(board, verbose=args.verbose))
    else:
        print(render_full_board(board))

    if args.curate:
        env_var = API_KEYS[args.provider]
        if not os.environ.get(env_var):
            print(f"\nError: {env_var} not set.", file=sys.stderr)
            sys.exit(1)
        from pitcher_narratives.curator import select_slate

        print(f"\n{'═' * 72}", file=sys.stderr)
        print("SELECTOR — choosing the slate...", file=sys.stderr)
        print(f"{'═' * 72}\n", file=sys.stderr)
        slate = select_slate(board, provider=args.provider)
        names = {a.pitcher_id: a.pitcher_name for a in board}
        print(render_curation_slate(slate, names))


if __name__ == "__main__":
    main()
