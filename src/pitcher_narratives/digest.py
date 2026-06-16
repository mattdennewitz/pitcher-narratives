"""Morning digest: story cues, per-pick writers, and assembly.

Stage 2 of the morning run. Each selected pick gets a deterministic
cue package (scout signals + the selector's angle + a season context
slice); a writer call turns each cue into a short tailored summary;
deterministic code assembles the digest document.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import polars as pl
from pydantic_ai import Agent

from pitcher_narratives.config import PROVIDERS, TOKEN_BUDGET_LARGE, make_model_settings
from pitcher_narratives.context import PitcherContext
from pitcher_narratives.costs import UsageTracker
from pitcher_narratives.curator import CurationPick, CurationSlate
from pitcher_narratives.personas import DIGEST_ITEM, Persona, build_system_prompt
from pitcher_narratives.pipeline import AnalyzedContext
from pitcher_narratives.scout import ScoredAppearance
from pitcher_narratives.signals import render_key_signals

__all__ = [
    "FALLBACK_MARKER",
    "assemble_digest",
    "build_story_cue",
    "build_story_cue_from_context",
    "enrich_cue_with_signals",
    "is_fallback_summary",
    "render_full_board",
    "write_pick_summaries",
]

log = logging.getLogger("pitcher_narratives.digest")

_WRITER_TEMPERATURE = 0.7
"""Match the pipeline writer's voice settings."""


# ── Cue builder ─────────────────────────────────────────────────────


def build_story_cue(
    app: ScoredAppearance,
    pick: CurationPick,
    *,
    season_baseline: pl.DataFrame,
    type_baseline: pl.DataFrame,
    season_velo: float | None,
) -> str:
    """Render the writer's briefing for one pick.

    Layers: appearance line, fired scout signals, the selector's
    editorial framing, and a compact season context slice.
    """
    lines = [
        f"PITCHER: {app.pitcher_name} ({app.throws}HP, {app.role})",
        f"APPEARANCE: {app.game_date}, {app.n_pitches} pitches",
        "",
        "FIRED SIGNALS (from deterministic scouting):",
    ]
    for s in app.signals:
        lines.append(f"- [{s.name}, w={s.weight:.1f}] {s.detail}")
    lines += [
        "",
        "EDITORIAL FRAMING (from the selector):",
        f"- Category: {pick.category}",
        f"- Angle: {pick.angle}",
        f"- Conviction: {pick.conviction} — {pick.conviction_reason}",
        "",
        "SEASON CONTEXT:",
    ]

    season_row = season_baseline.filter(pl.col("pitcher") == app.pitcher_id)
    if season_row.is_empty():
        lines.append("- no season baseline available")
    else:
        row = season_row.sort("season", descending=True).head(1).row(0, named=True)
        lines.append(
            f"- Season ({row['n_pitches']} pitches): "
            f"P+ {row['P+']:.0f}, S+ {row['S+']:.0f}, L+ {row['L+']:.0f}"
        )
        if season_velo is not None:
            lines.append(f"- Season avg fastball velocity: {season_velo:.1f} mph")
        types = type_baseline.filter(pl.col("pitcher") == app.pitcher_id)
        if not types.is_empty():
            max_season = types["season"].max()
            types = types.filter(pl.col("season") == max_season)
            for trow in types.sort("usage_pct", descending=True).iter_rows(named=True):
                lines.append(
                    f"- {trow['pitch_type']}: {trow['usage_pct']:.1f}% usage, "
                    f"S+ {trow['S+']:.0f}, L+ {trow['L+']:.0f}"
                )
    return "\n".join(lines)


def build_story_cue_from_context(
    app: ScoredAppearance,
    pick: CurationPick,
    ctx: PitcherContext,
) -> str:
    """Render the writer's briefing for one pick from a PitcherContext.

    Projects the engine-computed facts (fastball velocity, arsenal grades and
    usage) into the same top-level sections as build_story_cue — preserving
    downstream writer compatibility — but reads from PitcherContext instead of
    raw DataFrames.
    """
    lines = [
        f"PITCHER: {app.pitcher_name} ({app.throws}HP, {app.role})",
        f"APPEARANCE: {app.game_date}, {app.n_pitches} pitches",
        "",
        "FIRED SIGNALS (from deterministic scouting):",
    ]
    for s in app.signals:
        lines.append(f"- [{s.name}, w={s.weight:.1f}] {s.detail}")
    lines += [
        "",
        "EDITORIAL FRAMING (from the selector):",
        f"- Category: {pick.category}",
        f"- Angle: {pick.angle}",
        f"- Conviction: {pick.conviction} — {pick.conviction_reason}",
        "",
        "SEASON CONTEXT:",
    ]

    total_pitches = sum(pt.n_pitches_season for pt in ctx.arsenal)
    if total_pitches > 0:
        weighted_p = sum(pt.season_p_plus * pt.n_pitches_season for pt in ctx.arsenal) / total_pitches
        weighted_s = sum(pt.season_s_plus * pt.n_pitches_season for pt in ctx.arsenal) / total_pitches
        weighted_l = sum(pt.season_l_plus * pt.n_pitches_season for pt in ctx.arsenal) / total_pitches
        lines.append(
            f"- Season ({total_pitches} pitches): "
            f"P+ {weighted_p:.0f}, S+ {weighted_s:.0f}, L+ {weighted_l:.0f}"
        )
        if ctx.fastball is not None:
            lines.append(f"- Season avg fastball velocity: {ctx.fastball.season_velo:.1f} mph")
        for pt in ctx.arsenal:
            lines.append(
                f"- {pt.pitch_type}: {pt.season_usage_pct:.1f}% usage, "
                f"S+ {pt.season_s_plus:.0f}, L+ {pt.season_l_plus:.0f}"
            )
    else:
        lines.append("- no season baseline available")

    return "\n".join(lines)


def enrich_cue_with_signals(cue: str, analyzed: AnalyzedContext) -> str:
    """Prepend key signals to a story cue if the spine produced them.

    The DIGEST_ITEM writer sees both the cue facts and the cross-specialist
    signals, letting it weave the top finding into the what-to-watch close
    without changing its system prompt.
    """
    if analyzed.key_signals is None:
        return cue
    return render_key_signals(analyzed.key_signals) + "\n\n" + cue


# ── Per-pick writers ────────────────────────────────────────────────


def _build_writer_prompt(persona: Persona) -> str:
    """Compose the digest writer system prompt for the given persona using the DIGEST_ITEM contract."""
    return build_system_prompt(persona, DIGEST_ITEM)


def _make_writer_agent(provider: str, persona: Persona) -> Agent[None, str]:
    """Build the per-pick digest writer agent.

    Settings go through the shared provider-aware factory so gemini
    gets an explicit thinking level (its default thinking would
    otherwise consume the output budget) and claude gets thinking
    headroom, matching the pipeline writer's convention.
    """
    return Agent(
        PROVIDERS[provider],
        output_type=str,
        system_prompt=_build_writer_prompt(persona),
        model_settings=make_model_settings(
            provider, "low", _WRITER_TEMPERATURE, max_tokens=TOKEN_BUDGET_LARGE,
        ),
        retries=3,
        defer_model_check=True,
    )


FALLBACK_MARKER = "*[summary unavailable"
"""Prefix marking a deterministic fallback summary (writer call failed)."""


def is_fallback_summary(text: str) -> bool:
    """True when a summary is the deterministic fallback, not written prose."""
    return text.startswith(FALLBACK_MARKER)


def _fallback_summary(pick: CurationPick, cue: str) -> str:
    """Deterministic stand-in when a writer call fails."""
    return (
        f"{FALLBACK_MARKER} — writer call failed; cue data follows]*\n\n"
        f"**Angle:** {pick.angle}\n"
        f"**Conviction:** {pick.conviction} — {pick.conviction_reason}\n\n"
        f"```\n{cue}\n```"
    )


async def write_pick_summaries(
    picks: list[CurationPick],
    cues: dict[int, str],
    appearances: dict[int, ScoredAppearance],
    *,
    analyzed_contexts: dict[int, AnalyzedContext] | None = None,
    provider: str,
    persona: Persona,
    tracker: UsageTracker | None = None,
    _model_override: object = None,
) -> dict[int, str]:
    """Write all pick summaries concurrently. Failures degrade to fallback.

    When analyzed_contexts is provided, cues are enriched with key signals
    from the analysis spine before being passed to the writer.

    Returns:
        Mapping of pitcher_id to summary text (written or fallback).
    """
    agent = _make_writer_agent(provider, persona)

    async def _write_one(pick: CurationPick) -> tuple[int, str]:
        name = appearances[pick.pitcher_id].pitcher_name
        cue = cues[pick.pitcher_id]
        if analyzed_contexts is not None and pick.pitcher_id in analyzed_contexts:
            cue = enrich_cue_with_signals(cue, analyzed_contexts[pick.pitcher_id])
        kwargs: dict = {"user_prompt": cue}
        if _model_override is not None:
            kwargs["model"] = _model_override
        try:
            result = await agent.run(**kwargs)
        except Exception:
            log.error("Writer failed for %s; using fallback.", name, exc_info=True)
            return pick.pitcher_id, _fallback_summary(pick, cue)
        if tracker is not None:
            usage = result.usage()
            tracker.record(
                PROVIDERS[provider],
                usage.input_tokens or 0,
                usage.output_tokens or 0,
                stage=f"writer:{name}",
            )
        return pick.pitcher_id, result.output

    results = await asyncio.gather(*(_write_one(p) for p in picks))
    return dict(results)


# ── Assembly ────────────────────────────────────────────────────────


_CATEGORY_BADGES = {
    "clean_breakout": "CLEAN BREAKOUT",
    "command_breakout": "COMMAND BREAKOUT",
    "lab_project": "LAB PROJECT",
    "identity_crisis": "IDENTITY CRISIS",
    "velo_drop": "VELO DROP",
    "red_flag": "RED FLAG",
}

_CATEGORY_ORDER = [
    "clean_breakout", "command_breakout", "lab_project",
    "identity_crisis", "velo_drop", "red_flag",
]
_CATEGORY_SECTION_TITLES = {
    "clean_breakout": "Clean Breakouts",
    "command_breakout": "Command Breakouts",
    "lab_project": "Lab Projects",
    "identity_crisis": "Identity Crises",
    "velo_drop": "Velocity Drops",
    "red_flag": "Red Flags",
}
_CONVICTION_RANK = {"high": 0, "medium": 1, "low": 2}


def render_full_board(board: list[ScoredAppearance]) -> str:
    """Deterministic listing of every scored appearance, grouped by role."""
    lines = ["## The Full Board", ""]
    for label, role in (("### Starters", "SP"), ("### Relievers", "RP")):
        group = sorted(
            (a for a in board if a.role == role),
            key=lambda a: a.score, reverse=True,
        )
        lines.append(label)
        if not group:
            lines.append("*(none scored)*")
        for a in group:
            lines.append(
                f"- **{a.pitcher_name}** ({a.score:.1f}) — "
                f"{a.game_date}, {a.n_pitches} pitches"
            )
            for s in a.signals:
                lines.append(f"  - `{s.name}`: {s.detail}")
        lines.append("")
    return "\n".join(lines)


def assemble_digest(
    *,
    slate: CurationSlate,
    summaries: dict[int, str],
    appearances: dict[int, ScoredAppearance],
    board: list[ScoredAppearance],
    game_date: date,
    cost_block: str,
) -> str:
    """Render the final digest document, grouped by category."""

    def _ordered(picks: list[CurationPick]) -> list[CurationPick]:
        return sorted(
            picks,
            key=lambda p: (
                _CONVICTION_RANK.get(p.conviction, 99),
                -appearances[p.pitcher_id].score,
            ),
        )

    def _section(title: str, picks: list[CurationPick]) -> list[str]:
        lines = [f"## {title}", ""]
        for pick in _ordered(picks):
            name = appearances[pick.pitcher_id].pitcher_name
            badge = _CATEGORY_BADGES.get(pick.category, pick.category.upper().replace("_", " "))
            if pick.category not in _CATEGORY_BADGES:
                log.warning("Unknown pick category %r for %s; using raw name as badge.", pick.category, name)
            lines += [
                f"### {name} — `{pick.category}` [{badge}]",
                "",
                summaries[pick.pitcher_id],
                "",
            ]
        return lines

    by_cat: dict[str, list[CurationPick]] = {c: [] for c in _CATEGORY_ORDER}
    for pick in slate.picks:
        by_cat[pick.category].append(pick)

    parts = [f"# Morning Digest — {game_date}", ""]
    for cat in _CATEGORY_ORDER:
        if by_cat[cat]:
            parts += _section(_CATEGORY_SECTION_TITLES[cat], by_cat[cat])
    parts.append(render_full_board(board))
    parts += ["", cost_block]
    return "\n".join(parts)
