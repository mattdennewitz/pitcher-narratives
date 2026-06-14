"""Structured editorial selection of scouted appearances.

Stage 1 of the morning run: one LLM call ("the editor") reads the
role-bucketed candidate briefing and returns a CurationSlate — up to
10 starters and up to 10 relievers, each with a story category, a
one-sentence angle, and a conviction level. The angle is the cue the
Stage 2 writers build from.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent, ModelRetry

from pitcher_narratives.config import PROVIDERS, make_model_settings
from pitcher_narratives.costs import UsageTracker
from pitcher_narratives.scout import ScoredAppearance

__all__ = [
    "CurationPick",
    "CurationSlate",
    "build_selector_briefing",
    "select_slate",
    "select_slate_async",
]

_MAX_PICKS_PER_CATEGORY = 5
_SELECTOR_TEMPERATURE = 0.2
"""Low temperature: selection should be near-deterministic."""
_SELECTOR_MAX_TOKENS = 8192


class CurationPick(BaseModel):
    """One selected story: the pitcher and the editorial framing."""

    pitcher_id: int
    category: Literal[
        "clean_breakout", "lab_project", "identity_crisis", "red_flag"
    ]
    angle: str = Field(min_length=1)
    conviction: Literal["low", "medium", "high"]
    conviction_reason: str = Field(min_length=1)


class CurationSlate(BaseModel):
    """The morning slate: up to 5 picks per category, at least one overall."""

    picks: list[CurationPick] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> CurationSlate:
        if not self.picks:
            raise ValueError("slate must contain at least one pick")
        over = {
            cat: n
            for cat, n in Counter(p.category for p in self.picks).items()
            if n > _MAX_PICKS_PER_CATEGORY
        }
        if over:
            raise ValueError(
                f"Too many picks in categories {over}; "
                f"cap is {_MAX_PICKS_PER_CATEGORY} per category."
            )
        return self


_SELECTOR_PROMPT = """\
You are the editor of a data-driven baseball morning report. From the
scored candidate appearances below, select up to 10 STARTERS and up to
10 RELIEVERS whose outings are the most compelling stories, focusing on
process over results.

Use this hierarchy of signal when choosing:

1. clean_breakout: A significant velocity gain (1.5+ mph) coupled with
a jump in overall stuff (P+ or S+). A physical change backed by data.

2. lab_project: Top-tier raw stuff (S+ 130+) with poor command
(L+ < 80). High-upside development stories — the pitch has the shape,
the feel hasn't arrived.

3. identity_crisis: A radically altered pitch mix — shelving a primary,
doubling a secondary, or introducing something new. Plan or problem?

4. red_flag: Statistical anomalies that look like gains but might be
tracking errors. A single-game velocity spike of 3+ mph, or a P+ jump
the underlying stuff metrics don't support. Flag honestly.

RULES:
- Pick ONLY from the listed candidates, using their exact pitcher_id.
- Starters come ONLY from the STARTERS section, relievers ONLY from
  the RELIEVERS section.
- If a bucket is thin, pick fewer. Never pad with ordinary outings.
- Ignore "good" outings where the data matches the season average.
- For each pick: category from the hierarchy above; angle is ONE
  sentence stating the story; conviction scaled to the sample with a
  one-sentence reason. Be pragmatic, not breathless.
- Frame each angle for front offices and data-driven fans — what to
  watch, not what to do.
"""


def build_selector_briefing(candidates: list[ScoredAppearance]) -> str:
    """Render role-bucketed candidates as the selector's briefing."""

    def _bucket(label: str, apps: list[ScoredAppearance]) -> list[str]:
        lines = [f"=== {label} ({len(apps)} candidates) ==="]
        if not apps:
            lines.append("(none)")
        for r in apps:
            lines.append(
                f"## {r.pitcher_name} (id={r.pitcher_id}, {r.throws}HP) — "
                f"{r.game_date}, {r.n_pitches} pitches, score {r.score:.1f}"
            )
            for s in r.signals:
                lines.append(f"- [{s.name}] {s.detail}")
            lines.append("")
        return lines

    sp = [r for r in candidates if r.role == "SP"]
    rp = [r for r in candidates if r.role == "RP"]
    return "\n".join(_bucket("STARTERS", sp) + _bucket("RELIEVERS", rp))


def make_selector_agent(
    provider: str, candidates: list[ScoredAppearance]
) -> Agent[None, CurationSlate]:
    """Build the selector agent with candidate-membership validation."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}, expected: {', '.join(PROVIDERS)}")

    sp_ids = {r.pitcher_id for r in candidates if r.role == "SP"}
    rp_ids = {r.pitcher_id for r in candidates if r.role == "RP"}

    agent: Agent[None, CurationSlate] = Agent(
        PROVIDERS[provider],
        output_type=CurationSlate,
        system_prompt=_SELECTOR_PROMPT,
        model_settings=make_model_settings(
            provider, "medium", _SELECTOR_TEMPERATURE, max_tokens=_SELECTOR_MAX_TOKENS,
        ),
        retries=3,
        defer_model_check=True,
    )

    @agent.output_validator
    def _picks_are_candidates(output: CurationSlate) -> CurationSlate:
        bad_sp = [p.pitcher_id for p in output.starters if p.pitcher_id not in sp_ids]
        bad_rp = [p.pitcher_id for p in output.relievers if p.pitcher_id not in rp_ids]
        if bad_sp or bad_rp:
            raise ModelRetry(
                f"Invalid picks — not candidates in that role bucket: "
                f"starters {bad_sp}, relievers {bad_rp}. "
                f"Use only the listed pitcher_id values."
            )
        all_ids = [p.pitcher_id for p in (*output.starters, *output.relievers)]
        if len(all_ids) != len(set(all_ids)):
            raise ModelRetry(
                "Duplicate pitcher_id picks; select each pitcher at most once."
            )
        return output

    return agent


async def select_slate_async(
    candidates: list[ScoredAppearance],
    *,
    provider: str = "gemini",
    tracker: UsageTracker | None = None,
    briefing: str | None = None,
    _model_override: object = None,
) -> CurationSlate:
    """Async core of select_slate; see select_slate for the contract."""
    if not candidates:
        raise ValueError("no scored candidates to select from")
    agent = make_selector_agent(provider, candidates)
    if briefing is None:
        briefing = build_selector_briefing(candidates)
    user_msg = "Select the slate from these scored candidates.\n\n" + briefing
    kwargs: dict = {"user_prompt": user_msg}
    if _model_override is not None:
        kwargs["model"] = _model_override
    result = await agent.run(**kwargs)
    if tracker is not None:
        usage = result.usage()
        tracker.record(
            PROVIDERS[provider],
            usage.input_tokens or 0,
            usage.output_tokens or 0,
            stage="selector",
        )
    return result.output


def select_slate(
    candidates: list[ScoredAppearance],
    *,
    provider: str = "gemini",
    tracker: UsageTracker | None = None,
    briefing: str | None = None,
    _model_override: object = None,
) -> CurationSlate:
    """Run the selector over the candidates and return the validated slate.

    Args:
        candidates: Role-tagged ranked output of scout_appearances.
        provider: Contestant provider key.
        tracker: Optional costs.UsageTracker; records the call as 'selector'.
        briefing: Pre-built selector briefing; if None, one is built from
            candidates.  Pass the same briefing written to briefing.md so the
            selector sees exactly what was persisted.
        _model_override: Test-only model override.
    """
    return asyncio.run(select_slate_async(
        candidates,
        provider=provider,
        tracker=tracker,
        briefing=briefing,
        _model_override=_model_override,
    ))
