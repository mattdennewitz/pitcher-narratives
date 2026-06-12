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
from pitcher_narratives.costs import UsageTracker
from pitcher_narratives.curator import CurationPick, CurationSlate
from pitcher_narratives.personas import PERSONAS, Persona
from pitcher_narratives.scout import ScoredAppearance

__all__ = [
    "FALLBACK_MARKER",
    "assemble_digest",
    "build_story_cue",
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


# ── Per-pick writers ────────────────────────────────────────────────


_DIGEST_WRITER_BASE = """\
You write one short item for a data-driven baseball morning digest.

INPUT: a cue package for one pitcher's recent appearance — fired
scouting signals, the editor's framing (category, angle, conviction),
and season context.

CONTRACT:
- Lead with the editor's angle. It is the story; do not bury it.
- Ground every claim in the cue's numbers. Do not invent statistics.
- Scale your tone to the stated conviction: a 'low' conviction story
  is framed as something to monitor, not a breakout.
- Close with one sentence on what to watch in the next outing.
- 150-250 words. No headline; prose only — the document supplies
  headings.
"""


_PRECEDENCE_RULE = """\
PRECEDENCE: The CONTRACT above governs length and document structure.
Where the VOICE overlay specifies different lengths, headings, tables,
or section requirements, ignore those — keep only its tone and
vocabulary guidance."""


def _build_writer_prompt(persona: Persona) -> str:
    """Compose the digest writer system prompt for the given persona.

    Walks the persona's parent chain (parent-first) via the PERSONAS registry
    and appends each overlay as a VOICE section. The digest CONTRACT governs
    length and structure; a PRECEDENCE rule at the end of the prompt prevents
    capsule-specific directives in the overlays from overriding it.
    """
    # Collect overlays parent-first, then own overlay.
    overlays: list[str] = []
    if persona.parent is not None:
        overlays.append(PERSONAS[persona.parent].overlay)
    overlays.append(persona.overlay)

    voice_block = "\n\n".join(overlays)
    return (
        _DIGEST_WRITER_BASE
        + "\nVOICE:\n"
        + voice_block
        + "\n\n"
        + _PRECEDENCE_RULE
    )


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
    provider: str,
    persona: Persona,
    tracker: UsageTracker | None = None,
    _model_override: object = None,
) -> dict[int, str]:
    """Write all pick summaries concurrently. Failures degrade to fallback.

    Returns:
        Mapping of pitcher_id to summary text (written or fallback).
    """
    agent = _make_writer_agent(provider, persona)

    async def _write_one(pick: CurationPick) -> tuple[int, str]:
        name = appearances[pick.pitcher_id].pitcher_name
        kwargs: dict = {"user_prompt": cues[pick.pitcher_id]}
        if _model_override is not None:
            kwargs["model"] = _model_override
        try:
            result = await agent.run(**kwargs)
        except Exception:
            log.error("Writer failed for %s; using fallback.", name, exc_info=True)
            return pick.pitcher_id, _fallback_summary(pick, cues[pick.pitcher_id])
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
    "lab_project": "LAB PROJECT",
    "identity_crisis": "IDENTITY CRISIS",
    "red_flag": "RED FLAG",
}


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
    """Render the final digest document."""

    def _section(title: str, picks: list[CurationPick]) -> list[str]:
        lines = [f"## {title}", ""]
        if not picks:
            lines += ["*(no picks today)*", ""]
        for pick in picks:
            name = appearances[pick.pitcher_id].pitcher_name
            badge = _CATEGORY_BADGES[pick.category]
            lines += [
                f"### {name} — `{pick.category}` [{badge}]",
                "",
                summaries[pick.pitcher_id],
                "",
            ]
        return lines

    parts = [f"# Morning Digest — {game_date}", ""]
    parts += _section("Starters", slate.starters)
    parts += _section("Relievers", slate.relievers)
    parts.append(render_full_board(board))
    parts += ["", cost_block]
    return "\n".join(parts)
