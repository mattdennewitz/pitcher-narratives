"""Morning digest: full-board assembly.

Stage 2 of the morning run. Deterministic code assembles the digest
document from the scored board and the recap summaries produced upstream
by render_recap (see pipeline.py).
"""

from __future__ import annotations

import json
import logging
from datetime import date

from pitcher_narratives.curator import CATEGORIES, CurationPick, CurationSlate
from pitcher_narratives.scout import ScoredAppearance

__all__ = [
    "assemble_digest",
    "render_full_board",
    "render_full_board_json",
]

log = logging.getLogger("pitcher_narratives.digest")


# ── Assembly ────────────────────────────────────────────────────────


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


def render_full_board_json(board: list[ScoredAppearance]) -> str:
    """Serialize the scored board to a JSON string.

    Flat list of appearances sorted by interest score descending (consumers
    group by the ``role`` field). ``game_date`` is the most recent game date
    on the board, or null when the board is empty.
    """
    ranked = sorted(board, key=lambda a: a.score, reverse=True)
    payload = {
        "game_date": max((a.game_date for a in board), default=None),
        "appearances": [
            {
                "pitcher_id": a.pitcher_id,
                "pitcher_name": a.pitcher_name,
                "throws": a.throws,
                "role": a.role,
                "game_date": a.game_date,
                "game_pk": a.game_pk,
                "n_pitches": a.n_pitches,
                "score": a.score,
                "signals": [
                    {"name": s.name, "weight": s.weight, "detail": s.detail}
                    for s in a.signals
                ],
            }
            for a in ranked
        ],
    }
    return json.dumps(payload, indent=2, default=str)


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

    def _section(cat, picks: list[CurationPick]) -> list[str]:
        lines = [f"## {cat.section_title}", ""]
        for pick in _ordered(picks):
            name = appearances[pick.pitcher_id].pitcher_name
            lines += [
                f"### {name} — `{pick.category}` [{cat.badge}]",
                "",
                summaries[pick.pitcher_id],
                "",
            ]
        return lines

    by_cat: dict[str, list[CurationPick]] = {c.id: [] for c in CATEGORIES}
    for pick in slate.picks:
        if pick.pitcher_id in summaries:
            by_cat[pick.category].append(pick)

    parts = [f"# Morning Digest — {game_date}", ""]
    for cat in CATEGORIES:
        if by_cat[cat.id]:
            parts += _section(cat, by_cat[cat.id])
    parts.append(render_full_board(board))
    footer = cost_block
    if dropped_picks:
        footer += f"\nnote: analysis unavailable for {', '.join(dropped_picks)}"
    parts += ["", footer]
    return "\n".join(parts)
