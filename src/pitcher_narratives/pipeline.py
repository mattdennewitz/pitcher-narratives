"""Multi-agent specialist→writer report pipeline (v1.6 prototype).

Architecture:
  4 specialist agents run in parallel, each producing a focused micro-analysis:
    - Stuff Explainer: velocity/movement → S+ grades via S-variant predictions
    - Location Analyst: P vs S divergence, zone/chase rates, location impact
    - Run Value Decomposer: 13-outcome attribution, dominant value drivers
    - Trend Spotter: window vs season deltas, what's changing and direction

  Writer agent receives all 4 specialist blurbs + pitcher context, finds the
  thread, and composes a unified capsule.

  Anchor check + fantasy analyst remain from the existing pipeline.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.settings import ModelSettings, ThinkingEffort

from pitcher_narratives.context import PitcherContext
from pitcher_narratives.report import (
    MAX_REVISIONS,
    PROVIDERS,
    AnchorResult,
    AnchorWarning,
    _ANCHOR_PROMPT,
    _FANTASY_PROMPT,
    _build_anchor_message,
    _build_fantasy_message,
    _build_revision_message,
)

__all__ = ["PipelineResult", "generate_pipeline_streaming"]


# ═══════════════════════════════════════════════════════════════════════
# SPECIALIST PROMPTS
# ═══════════════════════════════════════════════════════════════════════

_STUFF_SPECIALIST_PROMPT = """\
You are a pitch physics analyst. Your job is to explain each pitch's \
raw stuff quality by tracing from physical characteristics to the \
model's stuff-only grade.

For each pitch type in the arsenal, explain why the Stuff+ (S+) grade \
is what it is by connecting velocity and movement shape (pfx_x/pfx_z) \
to the S-variant model predictions (xSwing_S, xWhiff_S, xRV100_S).

The chain is: physical pitch → model prediction → S+ grade.

Rules:
- Cover every pitch in the arsenal, prioritizing the most interesting \
(extreme S+, surprising grades given the physical profile).
- Cite velocity, movement values, and S-variant probabilities.
- Explain the mechanism: why does that velocity/movement combination \
produce that whiff rate or swing rate?
- No location analysis — this is stuff only.
- One paragraph per pitch. Plain prose, no bullet lists.
- No clichés, no hype. Just the mechanism."""

_LOCATION_SPECIALIST_PROMPT = """\
You are a pitch location analyst. Your job is to diagnose what \
location is adding (or subtracting) from each pitch's effectiveness.

For each pitch type, compare the P-variant (stuff + location) against \
the S-variant (stuff only) predictions to isolate the location impact. \
Then explain the mechanism: WHERE is the pitcher putting the pitch, \
and how does that change hitter behavior?

Key data points:
- Zone rate: what fraction lands in the strike zone?
- Chase rate: are hitters expanding to swing at pitches out of zone?
- xSwing P vs S: does location increase or decrease swing likelihood?
- xWhiff P vs S: does location improve or hurt whiff rate?
- xRV100 P vs S: net location impact in run value terms.

Rules:
- Cover every pitch, prioritizing the most extreme location impacts.
- A pitch with great stuff but terrible location (S+ >> P+) needs \
more explanation than a pitch where they're similar.
- Explain the physical location pattern, not just the delta.
- One paragraph per pitch or group. Plain prose, no bullet lists.
- No stuff analysis — this is location only."""

_RUNVALUE_SPECIALIST_PROMPT = """\
You are a run value decomposition analyst. Your job is to explain \
WHERE each pitch's run value comes from by reading the 13-outcome \
component attribution.

For each pitch type, identify the 2-3 dominant outcome contributors \
(the largest positive and negative values in the attribution table). \
Then connect them to the pitch: called balls dominate because of poor \
location, whiffs dominate because of sharp movement, home runs bleed \
through because of hittable velocity in the zone.

Sign convention:
- Negative contribution = pitcher benefits (saves runs)
- Positive contribution = costs the pitcher runs

Rules:
- Cover every pitch, prioritizing the most lopsided attributions.
- Name the specific outcomes and their contribution magnitudes.
- Connect each outcome back to the pitch's physical characteristics \
or location pattern.
- One paragraph per pitch. Plain prose, no bullet lists.
- No redundant S+/P+ discussion — focus on the outcome-level story."""

_TREND_SPECIALIST_PROMPT = """\
You are a trend analyst. Your job is to identify what has changed in \
the pitcher's recent window compared to season baseline and flag the \
direction and magnitude of those changes.

Look at:
- Velocity deltas (up, down, steady)
- P+/S+/L+ deltas per pitch type
- Usage rate shifts (biggest increases/decreases)
- Movement changes (pfx_x/pfx_z deltas)
- Release point shifts
- Workload context (consecutive days, rest, pitch counts)
- Hard-hit rate shifts
- TTO patterns for starters (stamina trajectory)

Rules:
- Lead with the single most important change.
- Separate real trends from noise: flag sample size concerns, note \
when a delta is within the "steady" threshold.
- Identify if changes are connected (e.g., velo drop + S+ drop + \
more hard contact = likely related).
- One focused paragraph covering the key trends. Skip what's steady.
- No projection or prediction — just what changed and by how much.
- Plain prose, no bullet lists."""


# ═══════════════════════════════════════════════════════════════════════
# WRITER PROMPT
# ═══════════════════════════════════════════════════════════════════════

_WRITER_PROMPT = """\
You are an elite, sabermetrically inclined baseball writer. You write \
for front offices, advanced fantasy players, and data-driven fans.

INPUT: Four specialist analyses of a pitcher's recent window:
1. Stuff analysis — physical pitch characteristics and S+ grades
2. Location analysis — P vs S location impact per pitch
3. Run value decomposition — which outcomes drive each pitch's value
4. Trend analysis — what has changed vs season baseline

Your job is to compose a single, unified 2-3 paragraph scouting capsule \
from these building blocks. The specialists did the analysis; you do \
the writing.

CRITICAL: These are INGREDIENTS, not sections to preserve. You must:
- Find the thread. What is the single most important story across \
all four analyses? Maybe the stuff is fine but location is killing a \
pitch. Maybe a velocity trend is changing the entire arsenal picture. \
Maybe one pitch is carrying the whole profile.
- Write as one voice. The reader should not be able to tell that four \
separate analysts contributed. No section breaks, no "meanwhile," no \
"turning to the location data."
- Drop what's redundant. If stuff and run value both say the slider \
is elite, say it once with the best evidence from either.
- Prioritize the surprising. If three specialists agree on something \
obvious, give it one sentence. If one specialist found something \
the others didn't highlight, that's probably the lead.

STRUCTURE:
Paragraph 1 (The Setup): What is different about this pitcher right now. \
Lead with what happened — the concrete change — not a theory.
Paragraph 2+ (The Verdict): How the stuff plays in practice. Weave in \
platoon splits where they matter. Clear-eyed conclusion.

VOICE:
- Write like an analyst talking to another analyst. Plain, specific, \
conversational.
- Vary sentence length. Short sentences land points.
- Use scouting language: stuff, feel, finding a groove, getting tagged.
- No clichés, no formulaic transitions, no "the data shows."
- Never use: "degradation," "binary," "profiles as," "dominant," \
"elite," "massive spike."
- Start immediately with analysis. No introductory fluff.
- At most three primary metrics carry the narrative.

CONSTRAINTS:
- Use ONLY data from the specialist analyses and the context provided. \
Do not invent metrics.
- No bullet points, no headers, no tables. Prose only.
- Scale confidence to sample size. Small windows get tentative language."""


# ═══════════════════════════════════════════════════════════════════════
# DATA BUILDERS
# ═══════════════════════════════════════════════════════════════════════

def _build_stuff_input(ctx: PitcherContext) -> str:
    """Build input for the stuff specialist from arsenal + intermediates."""
    lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    lines.append("## Arsenal Physical Profile")
    for p in ctx.arsenal:
        sp = f"{p.window_s_plus:.0f}" if p.window_s_plus is not None else "--"
        lines.append(
            f"- {p.pitch_name} ({p.pitch_type}): "
            f"{p.window_velo:.1f} mph ({p.velo_delta}), "
            f"pfx_x {p.window_pfx_x:.1f} in ({p.pfx_x_delta}), "
            f"pfx_z {p.window_pfx_z:.1f} in ({p.pfx_z_delta}), "
            f"S+ {sp} (season {p.season_s_plus:.0f}, {p.s_plus_delta})"
        )
    lines.append("\n## Stuff-Only Model Predictions (S-variant)")
    for im in ctx.intermediates:
        xswing_s = f"{im.xswing_s * 100:.1f}%" if im.xswing_s is not None else "--"
        xwhiff_s = f"{im.xwhiff_s * 100:.1f}%" if im.xwhiff_s is not None else "--"
        xrv_s = f"{im.xrv100_s:.2f}" if im.xrv100_s is not None else "--"
        lines.append(
            f"- {im.pitch_name} ({im.pitch_type}): "
            f"xSwing_S {xswing_s}, xWhiff_S {xwhiff_s}, xRV100_S {xrv_s}"
        )
    return "\n".join(lines)


def _build_location_input(ctx: PitcherContext) -> str:
    """Build input for the location specialist from intermediates + execution."""
    lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    lines.append("## P vs S Location Impact")
    for im in ctx.intermediates:
        def _d(p: float | None, s: float | None) -> str:
            if p is not None and s is not None:
                return f"{(p - s) * 100:+.1f}pp"
            return "--"
        def _drv(p: float | None, s: float | None) -> str:
            if p is not None and s is not None:
                return f"{(p - s):+.2f}"
            return "--"
        lines.append(
            f"- {im.pitch_name} ({im.pitch_type}): "
            f"xSwing P {im.xswing_p * 100:.1f}% S {im.xswing_s * 100:.1f}% (delta {_d(im.xswing_p, im.xswing_s)}), "
            f"xWhiff P {im.xwhiff_p * 100:.1f}% S {im.xwhiff_s * 100:.1f}% (delta {_d(im.xwhiff_p, im.xwhiff_s)}), "
            f"xRV100 P {im.xrv100_p:.2f} S {im.xrv100_s:.2f} (delta {_drv(im.xrv100_p, im.xrv100_s)})"
            if im.xswing_p is not None else f"- {im.pitch_name} ({im.pitch_type}): no data"
        )
    lines.append("\n## Execution Metrics")
    for e in ctx.execution:
        lines.append(
            f"- {e.pitch_name} ({e.pitch_type}): "
            f"Zone% {e.zone_rate:.1f}, Chase% {e.chase_rate:.1f}, CSW% {e.csw_pct:.1f}"
        )
    lines.append("\n## Plus Scores (P+ vs S+ vs L+)")
    for p in ctx.arsenal:
        wp = f"{p.window_p_plus:.0f}" if p.window_p_plus is not None else "--"
        ws = f"{p.window_s_plus:.0f}" if p.window_s_plus is not None else "--"
        wl = f"{p.window_l_plus:.0f}" if p.window_l_plus is not None else "--"
        lines.append(f"- {p.pitch_name} ({p.pitch_type}): P+ {wp}, S+ {ws}, L+ {wl}")
    return "\n".join(lines)


def _build_runvalue_input(ctx: PitcherContext) -> str:
    """Build input for the run value specialist from attributions."""
    lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    lines.append("## Component Attribution (xRV100 Decomposition)")
    for attr in ctx.attributions:
        lines.append(f"\n### {attr.pitch_name} ({attr.pitch_type}) — total xRV100: {attr.total_xrv100:.2f}")
        for oc in attr.contributions:
            share = (
                f"{(oc.contribution / attr.total_xrv100 * 100):+.1f}%"
                if attr.total_xrv100 != 0
                else f"{0:.1f}%"
            )
            lines.append(f"  {oc.outcome}: {oc.contribution:+.3f} ({share})")
    return "\n".join(lines)


def _build_trend_input(ctx: PitcherContext) -> str:
    """Build input for the trend specialist from full context."""
    return ctx.to_prompt()


def _build_writer_input(
    ctx: PitcherContext,
    stuff: str,
    location: str,
    runvalue: str,
    trends: str,
) -> str:
    """Compose all specialist outputs into writer input."""
    return (
        f"## Pitcher: {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Specialist Analysis 1: Stuff\n{stuff}\n\n"
        f"## Specialist Analysis 2: Location\n{location}\n\n"
        f"## Specialist Analysis 3: Run Value\n{runvalue}\n\n"
        f"## Specialist Analysis 4: Trends\n{trends}"
    )


# ═══════════════════════════════════════════════════════════════════════
# RESULT MODEL
# ═══════════════════════════════════════════════════════════════════════

class SpecialistOutputs(BaseModel):
    """Raw outputs from each specialist agent."""
    stuff: str
    location: str
    runvalue: str
    trends: str


class PipelineResult(BaseModel):
    """Result from the multi-agent pipeline."""
    narrative: str
    specialists: SpecialistOutputs
    fantasy_insights: str
    anchor_warnings: list[AnchorWarning]
    revision_count: int = 0


# ═══════════════════════════════════════════════════════════════════════
# AGENT FACTORY
# ═══════════════════════════════════════════════════════════════════════

def _make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
) -> tuple[
    Agent[None, str],  # stuff
    Agent[None, str],  # location
    Agent[None, str],  # runvalue
    Agent[None, str],  # trends
    Agent[None, str],  # writer
    Agent[None, AnchorResult],  # anchor
    Agent[None, str],  # fantasy
]:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}")
    model = PROVIDERS[provider]

    if provider == "gemini":
        gemini_level = "high" if thinking in ("high", "xhigh") else "low"
        settings: ModelSettings = GoogleModelSettings(
            google_thinking_config={"thinking_level": gemini_level},
            temperature=1.0,
            max_tokens=16384,
        )
    elif provider == "claude":
        settings = ModelSettings(thinking=thinking, max_tokens=16384)
    else:
        settings = ModelSettings(thinking=thinking)

    def _str_agent(prompt: str) -> Agent[None, str]:
        return Agent(model, output_type=str, system_prompt=prompt,
                     model_settings=settings, defer_model_check=True)

    return (
        _str_agent(_STUFF_SPECIALIST_PROMPT),
        _str_agent(_LOCATION_SPECIALIST_PROMPT),
        _str_agent(_RUNVALUE_SPECIALIST_PROMPT),
        _str_agent(_TREND_SPECIALIST_PROMPT),
        _str_agent(_WRITER_PROMPT),
        Agent(model, output_type=AnchorResult, system_prompt=_ANCHOR_PROMPT,
              model_settings=settings, defer_model_check=True),
        _str_agent(_FANTASY_PROMPT),
    )


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════

async def _run_specialists(
    stuff_agent: Agent[None, str],
    location_agent: Agent[None, str],
    runvalue_agent: Agent[None, str],
    trends_agent: Agent[None, str],
    ctx: PitcherContext,
    _model_override: Any = None,
) -> SpecialistOutputs:
    """Run all 4 specialists concurrently."""
    inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (trends_agent, _build_trend_input(ctx)),
    }

    async def _run(agent: Agent[None, str], prompt: str) -> str:
        kwargs: dict[str, Any] = {"user_prompt": prompt}
        if _model_override is not None:
            kwargs["model"] = _model_override
        result = await agent.run(**kwargs)
        return result.output

    tasks = {
        name: _run(agent, prompt)
        for name, (agent, prompt) in inputs.items()
    }

    results = await asyncio.gather(
        tasks["stuff"], tasks["location"],
        tasks["runvalue"], tasks["trends"],
    )

    return SpecialistOutputs(
        stuff=results[0], location=results[1],
        runvalue=results[2], trends=results[3],
    )


async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    _model_override: Any = None,
) -> PipelineResult:
    """Async core of the multi-agent pipeline.

    Runs everything on a single event loop to avoid closed-loop errors
    from httpx connections shared across phases.
    """
    (
        stuff_agent, location_agent, runvalue_agent, trends_agent,
        writer, anchor_checker, fantasy_analyst,
    ) = _make_pipeline_agents(provider, thinking)

    # Phase 1: Run specialists concurrently
    print("Running specialists...", file=sys.stderr, flush=True)
    specialists = await _run_specialists(
        stuff_agent, location_agent, runvalue_agent, trends_agent,
        ctx, _model_override,
    )
    print("Specialists complete. Composing narrative...", file=sys.stderr, flush=True)

    # Phase 2: Writer composes from specialist outputs (streamed)
    writer_input = _build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends,
    )
    writer_kwargs: dict[str, Any] = {"user_prompt": writer_input}
    if _model_override is not None:
        writer_kwargs["model"] = _model_override

    async with writer.run_stream(**writer_kwargs) as stream:
        chunks: list[str] = []
        async for delta in stream.stream_text(delta=True):
            print(delta, end="", flush=True)
            chunks.append(delta)
    print()

    capsule = "".join(chunks)

    # Phase 2.5: Anchor check + revision loop
    revision_count = 0
    synthesis = (
        f"STUFF:\n{specialists.stuff}\n\n"
        f"LOCATION:\n{specialists.location}\n\n"
        f"RUN VALUE:\n{specialists.runvalue}\n\n"
        f"TRENDS:\n{specialists.trends}"
    )

    for _ in range(MAX_REVISIONS):
        anchor_kwargs: dict[str, Any] = {
            "user_prompt": _build_anchor_message(synthesis, capsule),
        }
        if _model_override is not None:
            anchor_kwargs["model"] = _model_override

        anchor_result = await anchor_checker.run(**anchor_kwargs)
        anchor_check = anchor_result.output

        if anchor_check.is_clean:
            break

        revision_kwargs: dict[str, Any] = {
            "user_prompt": _build_revision_message(synthesis, capsule, anchor_check.warnings),
        }
        if _model_override is not None:
            revision_kwargs["model"] = _model_override

        revision_result = await writer.run(**revision_kwargs)
        capsule = revision_result.output
        revision_count += 1
    else:
        anchor_kwargs = {
            "user_prompt": _build_anchor_message(synthesis, capsule),
        }
        if _model_override is not None:
            anchor_kwargs["model"] = _model_override
        anchor_result = await anchor_checker.run(**anchor_kwargs)
        anchor_check = anchor_result.output

    # Phase 3: Fantasy analyst
    fantasy_kwargs: dict[str, Any] = {
        "user_prompt": _build_fantasy_message(ctx, capsule),
    }
    if _model_override is not None:
        fantasy_kwargs["model"] = _model_override

    fantasy_result = await fantasy_analyst.run(**fantasy_kwargs)

    return PipelineResult(
        narrative=capsule,
        specialists=specialists,
        fantasy_insights=fantasy_result.output,
        anchor_warnings=anchor_check.warnings,
        revision_count=revision_count,
    )


def generate_pipeline_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    _model_override: Any = None,
) -> PipelineResult:
    """Generate a report using the specialist→writer multi-agent pipeline.

    Phase 1: 4 specialists run concurrently (silent).
    Phase 2: Writer composes capsule from specialist outputs (streamed).
    Phase 2.5: Anchor check + revision loop.
    Phase 3: Fantasy analyst (silent).

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key.
        thinking: Thinking effort level.
        _model_override: Optional model override for testing.

    Returns:
        PipelineResult with narrative, specialist outputs, fantasy insights,
        and anchor warnings.
    """
    return asyncio.run(
        _run_pipeline(ctx, provider=provider, thinking=thinking, _model_override=_model_override)
    )
