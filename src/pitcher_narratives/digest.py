"""Morning digest: full-board assembly.

Stage 2 of the morning run. Deterministic code assembles the digest
document from the scored board and the recap summaries produced upstream
by render_recap (see pipeline.py).
"""

from __future__ import annotations

import json
from datetime import date

from pitcher_narratives.curator import CATEGORIES, CurationPick, CurationSlate
from pitcher_narratives.scout import ScoredAppearance

__all__ = [
    "assemble_digest",
    "render_curation_slate",
    "render_full_board",
    "render_full_board_json",
    "render_full_board_table",
]



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



def render_full_board_table(
    board: list[ScoredAppearance], *, verbose: bool = False
) -> str:
    """Fixed-width table of scored appearances, flat-sorted by score descending.

    ``verbose`` appends an indented detail row per signal (name, weight, detail).
    """
    ranked = sorted(board, key=lambda a: a.score, reverse=True)
    lines = [
        f"{'Score':>5}  {'Pitcher':<25} {'T':>1} {'Role':<4}  "
        f"{'Date':<10}  {'#P':>3}  Signals",
        f"{'─' * 5}  {'─' * 25} {'─':>1} {'─' * 4}  "
        f"{'─' * 10}  {'─' * 3}  {'─' * 40}",
    ]
    for a in ranked:
        signal_names = ", ".join(s.name for s in a.signals)
        lines.append(
            f"{a.score:5.1f}  {a.pitcher_name:<25} {a.throws:>1} {a.role:<4}  "
            f"{a.game_date!s:<10}  {a.n_pitches:>3}  {signal_names}"
        )
        if verbose:
            for s in a.signals:
                lines.append(f"       └─ {s.name} ({s.weight:.1f}): {s.detail}")
    return "\n".join(lines)

def render_curation_slate(slate: CurationSlate, names: dict[int, str]) -> str:
    """Render a selected slate as category-grouped lines for terminal display.

    Categories appear in registry order under their badge; each pick is one
    line: ``<name> (<conviction>): <angle>``. Empty categories are skipped.
    """
    by_cat: dict[str, list[CurationPick]] = {c.id: [] for c in CATEGORIES}
    for pick in slate.picks:
        by_cat[pick.category].append(pick)
    blocks: list[str] = []
    for cat in CATEGORIES:
        picks = by_cat[cat.id]
        if not picks:
            continue
        lines = [cat.badge]
        for pick in picks:
            who = names.get(pick.pitcher_id, pick.pitcher_id)
            lines.append(f"  {who} ({pick.conviction}): {pick.angle}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)

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
