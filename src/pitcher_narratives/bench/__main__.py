"""CLI for the LLM benchmarking harness.

Runs the full pipeline per provider, judges every captured output with
the rubric (panel by default, self-judging excluded), and writes raw
outputs, scores.json, and report.md to a timestamped run directory.

Usage:
    python -m pitcher_narratives.bench -p 693433 [--providers gemini,claude]
        [--judges panel|gemini|claude] [--thinking medium] [--persona scout]
        [--out bench-runs]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pitcher_narratives.bench.judge import JUDGE_MODELS, _with_retry, judge_text, judges_for
from pitcher_narratives.bench.rubric import AGENT_RUBRIC, CAPSULE_RUBRIC
from pitcher_narratives.bench.runner import run_provider
from pitcher_narratives.bench.scorecard import JudgedRecord, aggregate, render_report
from pitcher_narratives.config import PROVIDERS, setup_logging


def parse_args() -> argparse.Namespace:
    """Parse bench CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Benchmark LLM providers across pipeline agents and final output",
    )
    parser.add_argument("-p", "--pitcher", type=int, required=True, help="MLB pitcher ID")
    parser.add_argument(
        "--providers",
        default=",".join(PROVIDERS),
        help=f"Comma-separated providers to benchmark (default: {','.join(PROVIDERS)})",
    )
    parser.add_argument(
        "--judges",
        default="deepseek",
        help="Judge: a non-contestant model key (default: deepseek = DeepSeek v4 Pro "
             "via OpenRouter, high effort), a contestant provider name, or 'panel' "
             "(each output judged by every other contestant)",
    )
    parser.add_argument("--thinking", default="medium", help="Thinking effort for contestants")
    parser.add_argument("--persona", default="scout", help="Writer persona")
    parser.add_argument("-w", "--window", type=int, default=30, help="Lookback window days")
    parser.add_argument("--out", default="bench-runs", help="Output directory root")
    return parser.parse_args()


def main() -> None:
    """Entry point: generate per provider, judge, aggregate, report."""
    from dotenv import load_dotenv

    load_dotenv()
    setup_logging()
    args = parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    unknown = [p for p in providers if p not in PROVIDERS]
    if unknown:
        print(f"Unknown providers: {', '.join(unknown)}", file=sys.stderr)
        sys.exit(2)
    if args.judges != "panel" and args.judges not in PROVIDERS and args.judges not in JUDGE_MODELS:
        print(f"Unknown judge: {args.judges}", file=sys.stderr)
        sys.exit(2)

    run_dir = Path(args.out) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    # ── Generate ──────────────────────────────────────────────────
    runs = []
    for provider in providers:
        print(f"\n=== Generating with {provider} ===", file=sys.stderr)
        run = run_provider(
            args.pitcher,
            provider=provider,
            thinking=args.thinking,
            persona=args.persona,
            window_days=args.window,
        )
        if not run.ok:
            # One retry: provider failures observed so far are transient
            # network timeouts, not deterministic errors.
            print(f"=== {provider} failed ({run.error}); retrying once ===", file=sys.stderr)
            run = run_provider(
                args.pitcher,
                provider=provider,
                thinking=args.thinking,
                persona=args.persona,
                window_days=args.window,
            )
        runs.append(run)
        pdir = run_dir / provider
        pdir.mkdir(exist_ok=True)
        for tier, text in run.outputs.items():
            (pdir / f"{tier.replace(':', '_')}.md").write_text(text)
        status = "ok" if run.ok else f"FAILED: {run.error}"
        print(f"=== {provider}: {status} ({run.wall_s:.0f}s) ===", file=sys.stderr)

    ok_runs = [r for r in runs if r.ok]
    if not ok_runs:
        print("All provider runs failed; nothing to judge.", file=sys.stderr)
        sys.exit(1)
    (run_dir / "ground_truth.md").write_text(ok_runs[0].ground_truth)
    for run in ok_runs:
        gt_dir = run_dir / run.provider / "ground_truths"
        gt_dir.mkdir(exist_ok=True)
        for tier, gt_text in run.ground_truths.items():
            (gt_dir / f"{tier.replace(':', '_')}.md").write_text(gt_text)

    # ── Judge ─────────────────────────────────────────────────────
    # exec_summary is captured but not judged: the specialist rubric's
    # mechanism/citation dimensions do not fit a bullet list.
    records: list[JudgedRecord] = []
    for run in ok_runs:
        for tier, text in run.outputs.items():
            if tier == "exec_summary":
                continue
            rubric = CAPSULE_RUBRIC if tier == "capsule" else AGENT_RUBRIC
            for judge in judges_for(run.provider, providers, args.judges):
                print(f"Judging {run.provider}/{tier} with {judge}...", file=sys.stderr)
                try:
                    judged = _with_retry(lambda: judge_text(
                        ground_truth=run.ground_truths[tier],
                        output_text=text,
                        tier_label=tier,
                        rubric=rubric,
                        judge_provider=judge,
                    ))
                except Exception as exc:  # noqa: BLE001 -- drop a failed judge, keep the bench
                    print(f"  judge failed after retries ({type(exc).__name__}: {str(exc)[:120]}); dropped",
                          file=sys.stderr)
                    continue
                records.append(JudgedRecord(
                    provider=run.provider, tier=tier, judge=judge, judged=judged,
                ))

    # ── Aggregate + report ────────────────────────────────────────
    agg = aggregate(records)
    meta = {
        "pitcher": ok_runs[0].pitcher_name or str(args.pitcher),
        "providers": ", ".join(providers),
        "judge_mode": args.judges,
        "thinking": args.thinking,
        "persona": args.persona,
        "wall_clock": ", ".join(f"{r.provider} {r.wall_s:.0f}s" for r in runs),
        "failures": ", ".join(f"{r.provider}: {r.error}" for r in runs if not r.ok) or "none",
    }
    report = render_report(agg, meta=meta)

    (run_dir / "report.md").write_text(report)
    (run_dir / "scores.json").write_text(json.dumps(
        [
            {
                "provider": r.provider, "tier": r.tier, "judge": r.judge,
                "scores": [s.model_dump() for s in r.judged.scores],
                "overall_comment": r.judged.overall_comment,
            }
            for r in records
        ],
        indent=2,
    ))

    print(f"\n{report}")
    print(f"\nRun artifacts: {run_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
