"""Morning editorial run orchestration.

scout -> selector -> cue builder -> concurrent writers -> assembler,
with artifacts written to <out_root>/<game-date>/: digest.md,
slate.json, briefing.md, usage.json. See
docs/superpowers/specs/2026-06-12-morning-run-design.md.

Validation parity note: digest entries are intentionally less validated
than single-pitcher reports. The anchor-revision loop and hallucination
check (check_hallucinated_metrics, invoked in cli.py for the report path)
are terminal-layer concerns that are omitted here to keep the morning run
fast. Each entry is produced from clean specialist outputs (run through
the audit/revision loop in run_analysis_spine), but is not anchor-checked
for signal fidelity or cross-validated for metric accuracy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from pitcher_narratives.context import PitcherContext, assemble_pitcher_context
from pitcher_narratives.costs import UsageTracker
from pitcher_narratives.curator import build_selector_briefing, select_slate_async
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.digest import assemble_digest
from pitcher_narratives.personas import PERSONAS, RECAP
from pitcher_narratives.pipeline import (
    PipelineResult,
    flag_record,
    make_pipeline_agents,
    render_recap,
    residual_banner,
    run_analysis_spine,
)
from pitcher_narratives.scout import (
    ScoredAppearance,
    scout_appearances,
    top_per_role,
)
from pitcher_narratives.temporal import _DEFAULT_RECENT_APPEARANCES

__all__ = ["run_morning"]

log = logging.getLogger("pitcher_narratives.morning")


def _load_pitcher_context(pitcher_id: int) -> PitcherContext:
    """Isolated so the morning run loads context per-pick post-selection, not upfront for all pitchers."""
    log.debug("Loading pitcher context for pitcher_id=%d", pitcher_id)
    data = load_pitcher_data(pitcher_id)
    return assemble_pitcher_context(data)


def _build_validation_payload(
    game_date: str, recap_results: dict[int, "PipelineResult"]
) -> dict[str, object]:
    """Per-pick calibration records for validation.json.

    One ``flag_record`` per surviving pick, keyed by stringified pitcher id
    (JSON object keys must be strings). Morning always runs RECAP on the
    default recent-appearance span.
    """
    return {
        "game_date": game_date,
        "picks": {
            str(pid): flag_record(
                RECAP, pid, result, span=_DEFAULT_RECENT_APPEARANCES
            )
            for pid, result in recap_results.items()
        },
    }


def run_morning(
    *,
    window_days: int,
    top_n: int,
    min_pitches: int,
    provider: str,
    persona_id: str,
    out_root: Path,
    max_concurrency: int = 4,
    _selector_override: object = None,
    _writer_override: object = None,
) -> Path | None:
    """Run the full morning workflow. Returns the run dir, or None on a quiet day."""
    started = time.monotonic()
    tracker = UsageTracker()
    persona = PERSONAS[persona_id]

    # ── Scout ─────────────────────────────────────────────────────
    log.info("Scouting appearances...")
    all_scored = scout_appearances(window_days=window_days, min_pitches=min_pitches)
    if not all_scored:
        print("No interesting appearances found — quiet day, no digest.", file=sys.stderr)
        return None
    candidates = top_per_role(all_scored, top_n)
    game_date = max(c.game_date for c in all_scored)
    appearances: dict[int, ScoredAppearance] = {}
    for c in all_scored:
        appearances.setdefault(c.pitcher_id, c)

    # ── Select + write (one event loop) ───────────────────────────
    # The selector and the writers must share a single event loop:
    # provider-client state (e.g. asyncio primitives inside the
    # google-genai/httpx stack) created during selection stays bound
    # to the loop it was created on, and a second asyncio.run loop
    # would fail the first writer call.
    log.info("Selecting the slate from %d candidates...", len(candidates))
    briefing = build_selector_briefing(candidates)

    async def _llm_stages():
        agents = make_pipeline_agents(provider, "medium", persona, RECAP)
        spine_sem = asyncio.Semaphore(min(max_concurrency, 2))

        slate = await select_slate_async(
            candidates, provider=provider, tracker=tracker, briefing=briefing,
            _model_override=_selector_override,
        )
        picks = slate.picks
        by_cat = Counter(p.category for p in picks)
        log.info("Slate: %d picks across categories %s.", len(picks), dict(by_cat))

        async def _build_pick(p) -> tuple[int, PipelineResult] | None:
            pitcher_name = appearances[p.pitcher_id].pitcher_name
            async with spine_sem:
                try:
                    ctx = _load_pitcher_context(p.pitcher_id)
                    analyzed = await run_analysis_spine(
                        ctx, agents=agents, _model_override=_writer_override,
                        tracker=tracker,
                    )
                    recap_result = await render_recap(
                        ctx, analyzed, agents=agents, pick=p,
                        _model_override=_writer_override, tracker=tracker,
                    )
                    return p.pitcher_id, recap_result
                except Exception:
                    log.error(
                        "Spine failed for pitcher_id=%d (%s); skipping pick.",
                        p.pitcher_id, pitcher_name, exc_info=True,
                    )
                    return None

        log.info("Running analysis spine for %d picks...", len(picks))
        build_results = await asyncio.gather(*(_build_pick(p) for p in picks))

        summaries: dict[int, str] = {}
        recap_results: dict[int, PipelineResult] = {}
        n_unverified = 0
        for result in build_results:
            if result is None:
                continue
            pid, recap_result = result
            text = recap_result.narrative
            banner = residual_banner(recap_result, label="RECAP")
            # Deliberately louder than is_unverified(): value-parity warnings also mark an item UNVERIFIED so no ungrounded number ships silently.
            if banner is None and recap_result.value_parity_warnings:
                banner = (
                    "⚠️  RECAP UNVERIFIED — value-parity flags present; "
                    "review before use."
                )
            if banner:
                text = f"{banner}\n\n{text}"
                n_unverified += 1
            summaries[pid] = text
            recap_results[pid] = recap_result
        dropped_names = [
            appearances[p.pitcher_id].pitcher_name
            for p in picks if p.pitcher_id not in summaries
        ]
        picks = [p for p in picks if p.pitcher_id in summaries]

        if n_unverified:
            log.warning("%d recap item(s) shipped UNVERIFIED (residual fact-check flags)", n_unverified)

        return slate, picks, summaries, dropped_names, n_unverified, recap_results

    slate, picks, summaries, dropped_names, n_unverified, recap_results = asyncio.run(_llm_stages())

    # ── Assemble + persist ────────────────────────────────────────
    wall_s = time.monotonic() - started
    cost_block = tracker.render_cost_block(wall_s=wall_s)
    if n_unverified:
        cost_block += (
            f"\nnote: {n_unverified} recap item(s) shipped UNVERIFIED "
            f"(residual validation flags)"
        )
    digest = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=all_scored, game_date=game_date, cost_block=cost_block,
        dropped_picks=dropped_names or None,
    )

    run_dir = out_root / str(game_date)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "digest.md").write_text(digest)
    (run_dir / "briefing.md").write_text(briefing)
    (run_dir / "slate.json").write_text(json.dumps(
        {
            "game_date": str(game_date),
            "picks": slate.model_dump()["picks"],
            "names": {
                str(p.pitcher_id): appearances[p.pitcher_id].pitcher_name
                for p in picks
            },
        },
        indent=2,
    ))
    (run_dir / "usage.json").write_text(json.dumps(tracker.to_json(), indent=2))
    (run_dir / "validation.json").write_text(json.dumps(
        _build_validation_payload(str(game_date), recap_results),
        indent=2,
    ))

    print(digest)
    return run_dir
