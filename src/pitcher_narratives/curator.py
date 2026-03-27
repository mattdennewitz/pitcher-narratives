"""LLM-powered curation of scouted appearances.

Takes the ranked output from scout.scout_appearances and asks an LLM
to select the 3-5 most compelling stories using a signal hierarchy.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from pitcher_narratives.report import PROVIDERS
from pitcher_narratives.scout import ScoredAppearance

__all__ = ["curate_appearances"]

_CURATOR_PROMPT = """\
You are a Lead Sabermetric Analyst for a data-driven baseball newsletter. \
Your job is to select the 3-5 most compelling pitchers from a scored list \
of recent appearances, focusing on process over results.

Use this hierarchy of signal when choosing:

1. Clean Breakout: A pitcher showing a significant velocity gain (1.5+ mph) \
coupled with a jump in overall stuff (P+ or S+). This is the strongest \
signal — a physical change backed by data.

2. Lab Project: Pitchers with top-tier raw stuff (S+ 130+) but poor command \
(L+ < 80). These are the high-upside development stories — the pitch has \
the shape, the feel hasn't arrived yet.

3. Identity Crisis: A pitcher who radically altered their pitch mix — \
shelving a primary pitch, doubling a secondary, or introducing something \
new. The question is whether it's a plan or a problem.

4. Red Flag: Statistical anomalies that look like gains but might be \
tracking errors. A single-game velocity spike of 3+ mph, or a P+ jump \
that doesn't match the underlying stuff metrics. Flag these honestly.

IMPORTANT:
- Ignore "good" outings where the data matches the season average. \
Only select the outliers.
- Be pragmatic and cautious, not breathless. Scale your conviction to \
the sample.
- Write for fans and fantasy managers who want to know what to watch, \
not what to do.
- Use conversational scouting language. No clinical jargon.

For each selection, use this exact format:

**[Pitcher Name]**: [One sentence: the core "why"]

- Signal: [The specific S+, L+, velo, or usage numbers that matter]
- Narrative: [2 sentences — why should a fan or fantasy manager care \
about this specific outing? Frame as observation, not advice.]
- Conviction: [Low / Medium / High] — [One sentence: is this a \
sustainable physical change or a one-day outlier?]

After your selections, add:

**Also worth tracking:** [2-3 pitchers that just missed the cut \
and why in a sentence each.]

**Why not the others:** Go through every pitcher you did NOT select \
and explain in one sentence each why they didn't make the cut. Be \
specific — "too small a sample," "signals cancel out," "the numbers \
are loud but it's spring training noise," etc. Group them if several \
share the same reason. This section helps the reader understand your \
filter, not just your picks."""


def _format_appearances_for_llm(appearances: list[ScoredAppearance]) -> str:
    """Format scored appearances as a readable briefing for the LLM."""
    lines: list[str] = []
    for r in appearances:
        lines.append(
            f"## {r.pitcher_name} ({r.throws}HP) — "
            f"{r.game_date}, {r.n_pitches} pitches, score {r.score:.1f}"
        )
        for s in r.signals:
            lines.append(f"- [{s.name}] {s.detail}")
        lines.append("")
    return "\n".join(lines)


def curate_appearances(
    appearances: list[ScoredAppearance],
    *,
    provider: str = "openai",
) -> None:
    """Send scored appearances to an LLM for curation and stream the output.

    Args:
        appearances: Ranked list from scout_appearances.
        provider: LLM provider key.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}, expected: {', '.join(PROVIDERS)}")

    model = PROVIDERS[provider]
    settings = ModelSettings(max_tokens=4096)
    agent = Agent(model, output_type=str, system_prompt=_CURATOR_PROMPT,
                  model_settings=settings, defer_model_check=True)

    briefing = _format_appearances_for_llm(appearances)
    user_msg = (
        f"Here are {len(appearances)} scored pitcher appearances from recent games. "
        f"Select the 3-5 most compelling based on the signal hierarchy.\n\n"
        f"{briefing}"
    )

    stream = agent.run_stream_sync(user_prompt=user_msg)
    for delta in stream.stream_text(delta=True):
        print(delta, end="", flush=True)
    print()
