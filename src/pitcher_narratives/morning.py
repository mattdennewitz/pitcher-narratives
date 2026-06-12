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
from pathlib import Path

import polars as pl

from pitcher_narratives.costs import UsageTracker
from pitcher_narratives.curator import build_selector_briefing, select_slate_async
from pitcher_narratives.data import (
    compute_pitch_type_baseline,
    compute_season_baseline,
    load_full_agg,
)
from pitcher_narratives.digest import (
    assemble_digest,
    build_story_cue,
    is_fallback_summary,
    write_pick_summaries,
)
from pitcher_narratives.personas import PERSONAS
from pitcher_narratives.scout import (
    ScoredAppearance,
    _compute_velo_baselines,
    _top_per_role,
    scout_appearances,
)

__all__ = ["run_morning"]

log = logging.getLogger("pitcher_narratives.morning")


def _load_baselines() -> tuple[pl.DataFrame, pl.DataFrame, dict[int, float]]:
    """Season + pitch-type baselines and per-pitcher season fastball velo."""
    season_df = load_full_agg("pitcher").filter(pl.col("level") == "MLB")
    type_df = load_full_agg("pitcher_type").filter(pl.col("level") == "MLB")
    season_baseline = compute_season_baseline(season_df)
    type_baseline = compute_pitch_type_baseline(type_df)

    velo = _compute_velo_baselines()
    season_velo: dict[int, float] = {}
    if not velo.is_empty():
        per_pitcher = (
            velo.sort("game_date")
            .group_by("pitcher", maintain_order=True)
            .agg(pl.col("season_velo").last())
        )
        season_velo = {
            row["pitcher"]: row["season_velo"]
            for row in per_pitcher.iter_rows(named=True)
        }
    return season_baseline, type_baseline, season_velo


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
    candidates = _top_per_role(all_scored, top_n)
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
        slate = await select_slate_async(
            candidates, provider=provider, tracker=tracker, briefing=briefing,
            _model_override=_selector_override,
        )
        picks = [*slate.starters, *slate.relievers]
        log.info("Slate: %d starters, %d relievers.",
                 len(slate.starters), len(slate.relievers))

        season_baseline, type_baseline, season_velo = _load_baselines()
        cues = {
            p.pitcher_id: build_story_cue(
                appearances[p.pitcher_id], p,
                season_baseline=season_baseline,
                type_baseline=type_baseline,
                season_velo=season_velo.get(p.pitcher_id),
            )
            for p in picks
        }

        log.info("Writing %d summaries...", len(picks))
        summaries = await write_pick_summaries(
            picks, cues, appearances, provider=provider, persona=persona,
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
            "picks": slate.model_dump(),
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
