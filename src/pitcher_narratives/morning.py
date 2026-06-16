"""Morning editorial run orchestration.

scout -> selector -> cue builder -> concurrent writers -> assembler,
with artifacts written to <out_root>/<game-date>/: digest.md,
slate.json, briefing.md, usage.json. See
docs/superpowers/specs/2026-06-12-morning-run-design.md.
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
from pitcher_narratives.digest import (
    assemble_digest,
    build_story_cue_from_context,
    is_fallback_summary,
    write_pick_summaries,
)
from pitcher_narratives.personas import PERSONAS
from pitcher_narratives.models import AnalyzedContext
from pitcher_narratives.pipeline import make_pipeline_agents, run_analysis_spine
from pitcher_narratives.scout import (
    ScoredAppearance,
    scout_appearances,
    top_per_role,
)

__all__ = ["run_morning"]

log = logging.getLogger("pitcher_narratives.morning")


def _load_pitcher_context(pitcher_id: int) -> PitcherContext:
    """Isolated so the morning run loads context per-pick post-selection, not upfront for all pitchers."""
    log.debug("Loading pitcher context for pitcher_id=%d", pitcher_id)
    data = load_pitcher_data(pitcher_id)
    return assemble_pitcher_context(data)


def run_morning(
    *,
    window_days: int,
    top_n: int,
    min_pitches: int,
    provider: str,
    persona_id: str,
    out_root: Path,
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
    spine_agents = make_pipeline_agents(provider, "medium", persona)

    async def _llm_stages():
        slate = await select_slate_async(
            candidates, provider=provider, tracker=tracker, briefing=briefing,
            _model_override=_selector_override,
        )
        picks = slate.picks
        by_cat = Counter(p.category for p in picks)
        log.info("Slate: %d picks across categories %s.", len(picks), dict(by_cat))

        async def _build_pick(p) -> tuple[int, str, AnalyzedContext] | None:
            try:
                ctx = _load_pitcher_context(p.pitcher_id)
                analyzed = await run_analysis_spine(
                    ctx, agents=spine_agents, _model_override=_writer_override,
                )
                cue = build_story_cue_from_context(appearances[p.pitcher_id], p, ctx)
                return p.pitcher_id, cue, analyzed
            except Exception:
                log.error(
                    "Spine failed for pitcher_id=%d (%s); skipping pick.",
                    p.pitcher_id, appearances[p.pitcher_id].pitcher_name, exc_info=True,
                )
                return None

        log.info("Running analysis spine for %d picks...", len(picks))
        build_results = await asyncio.gather(*(_build_pick(p) for p in picks))

        cues: dict[int, str] = {}
        analyzed_contexts: dict[int, AnalyzedContext] = {}
        for result in build_results:
            if result is None:
                continue
            pid, cue, analyzed = result
            cues[pid] = cue
            analyzed_contexts[pid] = analyzed
        picks = [p for p in picks if p.pitcher_id in cues]

        log.info("Writing %d summaries...", len(picks))
        summaries = await write_pick_summaries(
            picks, cues, appearances,
            analyzed_contexts=analyzed_contexts,
            provider=provider, persona=persona,
            tracker=tracker, _model_override=_writer_override,
        )
        return slate, picks, summaries

    slate, picks, summaries = asyncio.run(_llm_stages())

    # ── Assemble + persist ────────────────────────────────────────
    wall_s = time.monotonic() - started
    cost_block = tracker.render_cost_block(wall_s=wall_s)
    failed = sum(1 for text in summaries.values() if is_fallback_summary(text))
    if failed:
        cost_block += (
            f"\nnote: {failed} writer call(s) failed and fell back; "
            f"their token cost is not captured above"
        )
    digest = assemble_digest(
        slate=slate, summaries=summaries, appearances=appearances,
        board=all_scored, game_date=game_date, cost_block=cost_block,
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

    print(digest)
    return run_dir
