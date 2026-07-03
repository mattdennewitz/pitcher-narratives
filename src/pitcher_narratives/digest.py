"""Morning digest: full-board assembly.

Stage 2 of the morning run. Deterministic code assembles the digest
document from the scored board and the recap summaries produced upstream
by render_recap (see pipeline.py).
"""

from __future__ import annotations

import logging
from datetime import date

from pitcher_narratives.curator import CurationPick, CurationSlate
from pitcher_narratives.scout import ScoredAppearance

__all__ = [
    "assemble_digest",
    "render_full_board",
]

log = logging.getLogger("pitcher_narratives.digest")


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
    dropped_picks: list[str] | None = None,
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
        if pick.pitcher_id in summaries:
            by_cat[pick.category].append(pick)

    parts = [f"# Morning Digest — {game_date}", ""]
    for cat in _CATEGORY_ORDER:
        if by_cat[cat]:
            parts += _section(_CATEGORY_SECTION_TITLES[cat], by_cat[cat])
    parts.append(render_full_board(board))
    footer = cost_block
    if dropped_picks:
        footer += f"\nnote: analysis unavailable for {', '.join(dropped_picks)}"
    parts += ["", footer]
    return "\n".join(parts)
