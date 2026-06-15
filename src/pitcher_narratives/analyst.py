"""Analyst Q&A agent for natural-language pitcher questions.

Provides a tool-calling pydantic-ai agent that answers questions about
pitchers grounded exclusively in the existing data pipeline. Two tools
(get_pitcher_summary, get_pitch_detail) give the agent access to
PitcherContext data via RunContext[QADeps] dependency injection.

Voice and format are composed via build_system_prompt(persona, ANSWER).
ANALYST_MECHANICS carries domain-specific non-voice concerns: the model
reasoning chain, sign conventions, tool-grounding rules, and out-of-scope
handling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ThinkingEffort

from pitcher_narratives.agent_skills import skill_toolset
from pitcher_narratives.config import PROVIDERS, TOKEN_BUDGET_LARGE, make_model_settings
from pitcher_narratives.context import PitcherContext
from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine import compute_league_baselines
from pitcher_narratives.personas import (
    ANSWER,
    DEFAULT_PERSONA,
    Persona,
    build_system_prompt,
)

__all__ = [
    "ANALYST_MECHANICS",
    "PITCH_TYPE_MAP",
    "QADeps",
    "ask_question_streaming",
]

log = logging.getLogger("pitcher_narratives.analyst")


# ═══════════════════════════════════════════════════════════════════════
# PITCH TYPE SYNONYM MAP
# ═══════════════════════════════════════════════════════════════════════

PITCH_TYPE_MAP: dict[str, str] = {
    # Statcast codes (lowercase -> uppercase)
    "ff": "FF",
    "si": "SI",
    "fc": "FC",
    "sl": "SL",
    "st": "ST",
    "cu": "CU",
    "kc": "KC",
    "ch": "CH",
    "fs": "FS",
    "kn": "KN",
    "sc": "SC",
    "ep": "EP",
    # Common synonyms
    "fastball": "FF",
    "four-seam": "FF",
    "four seam": "FF",
    "4-seam": "FF",
    "sinker": "SI",
    "two-seam": "SI",
    "two seam": "SI",
    "2-seam": "SI",
    "cutter": "FC",
    "cut fastball": "FC",
    "slider": "SL",
    "sweeper": "ST",
    "sweep": "ST",
    "curveball": "CU",
    "curve": "CU",
    "knuckle curve": "KC",
    "knuckle-curve": "KC",
    "changeup": "CH",
    "change": "CH",
    "change-up": "CH",
    "splitter": "FS",
    "split-finger": "FS",
    "split finger": "FS",
    "knuckleball": "KN",
    "knuckle ball": "KN",
    "screwball": "SC",
    "eephus": "EP",
}


# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class QADeps:
    """Dependencies for the analyst Q&A agent."""

    context: PitcherContext
    data: PitcherData


# ═══════════════════════════════════════════════════════════════════════
# AGENT INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════════════

ANALYST_MECHANICS = """\
HOW THE MODEL THINKS (your reasoning chain):
The Pitching+ model grades pitches by predicting 13 outcome probabilities \
from the pitch's physical characteristics, then pricing each outcome in \
runs. Your job is to trace that chain -- from the physical pitch to the \
model's predictions to the grade -- so the reader understands WHY, not \
just WHAT.

1. Start with the pitch itself. Velocity, movement shape (pfx_x/pfx_z), \
release point, and zone location are what the model sees. These physical \
inputs drive every prediction downstream. When a model output is \
surprising, look here first -- a movement change, a velo shift, or a \
location pattern explains what the model is reacting to.

2. Explain Stuff+ (S+) through the physical profile. S+ is the model's \
grade on the pitch's raw characteristics -- velocity and movement -- \
ignoring location. An 83 mph curveball with modest break will grade \
lower than a 79 mph curve with sharp 2-plane movement because the model \
sees less swing-and-miss potential in the velocity/movement combination. \
Read the S-variant probabilities (xSwing_S, xWhiff_S, xRV100_S) as what \
the model expects from stuff alone. Then connect those predictions to \
the physical inputs: what about the velocity and movement shape explains \
why the model rates the stuff the way it does? A low xWhiff_S means the \
movement profile does not generate enough swing-and-miss on its own. A \
poor xRV100_S means the velocity/movement combination is hittable.

3. Compare P-variant (stuff + location) vs S-variant (stuff only) to \
isolate what location adds. But explain the mechanism -- WHERE is he \
putting it that changes the prediction? A zone rate of 21% with 6.7% \
chase rate tells you the pitch is landing in dead zones where hitters \
neither swing nor get called strikes. That is the physical explanation \
for why the model's P-variant prediction diverges from the S-variant.

4. Read the component attribution to see where runs come from. Each \
pitch's xRV100 breaks into 13 outcome contributions. Find the 2-3 \
largest drivers, but connect them back to the pitch: called balls dominate \
because of poor location, whiffs dominate because of sharp movement, \
home runs bleed through because of hittable velocity in the zone.

5. Land on plus scores (P+, S+, L+) as the summary. By this point the \
reader already knows why the grade is what it is. Above 100 helps the \
pitcher; below 100 hurts.

SIGN CONVENTIONS:
- Probability metrics (xSwing, xWhiff, xSwSt): higher = more of that \
event. P > S means location increases the rate.
- Run value (xRV100): more negative = better for pitcher. P < S means \
location is helping.
- Attribution: negative = pitcher benefits. Positive = costs runs.

DATA GROUNDING RULES (absolute):
1. Answer ONLY from the data returned by your tools. NEVER cite statistics \
from your training data.
2. When you call a tool, base your answer entirely on the tool's output. \
If the data does not contain what the user asked about, say so and explain \
what data IS available.
3. If the user asks about a topic outside the data (predictions, fantasy \
advice, historical seasons, cross-pitcher comparisons), explain that your \
data covers only this pitcher's recent performance window and describe \
what you CAN answer.
4. LEAGUE BASELINE COMPARISON: The tool output includes league baselines \
with standard deviations. If a metric is within ±1.5 stddev of the \
league average for that pitch type, it is NORMAL — do not characterize \
it as unusually high or low. Only flag metrics that are genuine outliers.
5. If xWhiff_S ≥ 25%, that is a meaningful whiff rate. Reconcile this \
strength before labeling any pitch as detrimental or poor.

OUT OF SCOPE (decline gracefully):
- Predictions or projections
- Fantasy baseball advice
- Historical season-over-season comparisons
- Cross-pitcher comparisons or leaderboard rankings
- Game-by-game play-by-play analysis\
"""


# ═══════════════════════════════════════════════════════════════════════
# AGENT + TOOLS
# ═══════════════════════════════════════════════════════════════════════

def get_pitcher_summary(ctx: RunContext[QADeps]) -> str:
    """Get the full scouting context for the pitcher including all arsenal, execution, and trend data."""
    # Inject league baselines so the agent can ground claims
    baselines = compute_league_baselines()
    lookup = {b.pitch_type: b for b in baselines}
    pitch_types = [p.pitch_type for p in ctx.deps.context.arsenal]

    baseline_lines = [
        "## League Baselines (2026, all pitchers)",
        "Use these to determine whether a metric is an outlier or normal.",
        "A metric within ±1.5 stddev of the league average is NORMAL.\n",
    ]
    for pt in pitch_types:
        b = lookup.get(pt)
        if b is None:
            continue
        baseline_lines.append(f"### {b.pitch_name} ({b.pitch_type})")
        baseline_lines.append(
            f"- Velocity: {b.avg_velo:.1f} mph (stddev {b.velo_std:.1f}, "
            f"normal range {b.avg_velo - 1.5 * b.velo_std:.1f}–{b.avg_velo + 1.5 * b.velo_std:.1f})"
        )
        baseline_lines.append(f"- pfx_x: {b.avg_pfx_x:.1f} in (stddev {b.pfx_x_std:.1f})")
        baseline_lines.append(f"- pfx_z: {b.avg_pfx_z:.1f} in (stddev {b.pfx_z_std:.1f})")
        if b.avg_s_plus is not None:
            xw = f"{b.avg_xwhiff_s * 100:.1f}%" if b.avg_xwhiff_s else "--"
            xr = f"{b.avg_xrv100_s:.2f}" if b.avg_xrv100_s else "--"
            baseline_lines.append(f"- S-variant avg: S+ {b.avg_s_plus:.0f}, xWhiff_S {xw}, xRV100_S {xr}")
        baseline_lines.append("")

    return "\n".join(baseline_lines) + "\n\n" + ctx.deps.context.to_prompt()


def get_pitch_detail(ctx: RunContext[QADeps], pitch_type: str) -> str:
    """Get detailed arsenal, execution, and platoon data for one specific pitch type.

    Args:
        pitch_type: Pitch type name or Statcast code (e.g., 'slider', 'SL', 'knuckle curve').
    """
    code = PITCH_TYPE_MAP.get(pitch_type.strip().lower(), pitch_type.strip().upper())
    pc = ctx.deps.context

    # Filter each list by pitch_type code
    arsenal_match = [a for a in pc.arsenal if a.pitch_type == code]
    execution_match = [e for e in pc.execution if e.pitch_type == code]
    platoon_match = [s for s in pc.platoon_mix.splits if s.pitch_type == code]
    attribution_match = [a for a in pc.attributions if a.pitch_type == code]
    intermediates_match = [i for i in pc.intermediates if i.pitch_type == code]

    if not arsenal_match:
        available = [f"{a.pitch_name} ({a.pitch_type})" for a in pc.arsenal]
        return (
            f"No data for {pitch_type} ({code}) in {pc.pitcher_name}'s arsenal. "
            f"Available pitches: {', '.join(available)}"
        )

    return _render_pitch_detail(
        code,
        arsenal_match,
        execution_match,
        platoon_match,
        attribution_rows=attribution_match,
        intermediates_rows=intermediates_match,
    )


def _render_pitch_detail(
    code: str,
    arsenal_rows: list[Any],
    execution_rows: list[Any],
    platoon_rows: list[Any],
    *,
    attribution_rows: list[Any] | None = None,
    intermediates_rows: list[Any] | None = None,
) -> str:
    """Build focused markdown for a single pitch type.

    Args:
        code: Statcast pitch type code (e.g., 'SL').
        arsenal_rows: Matching PitchTypeSummary items.
        execution_rows: Matching ExecutionMetrics items.
        platoon_rows: Matching PlatoonSplit items.
        attribution_rows: Matching ComponentAttribution items.
        intermediates_rows: Matching IntermediateProbabilities items.

    Returns:
        Markdown string with arsenal, execution, platoon, intermediates,
        and attribution data.
    """
    lines: list[str] = []

    # Arsenal section
    for a in arsenal_rows:
        lines.append(f"## {a.pitch_name} ({code}) Detail")
        lines.append("")
        lines.append("### Physical Profile")
        lines.append(f"- Velocity: {a.window_velo:.1f} mph (season {a.season_velo:.1f}) -- {a.velo_delta}")
        lines.append(f"- Horizontal movement (pfx_x): {a.window_pfx_x:.1f} in (season {a.season_pfx_x:.1f}) -- {a.pfx_x_delta}")
        lines.append(f"- Vertical movement (pfx_z): {a.window_pfx_z:.1f} in (season {a.season_pfx_z:.1f}) -- {a.pfx_z_delta}")
        lines.append("")
        lines.append("### Grades")
        lines.append(f"- Usage: {a.window_usage_pct:.1f}% (season {a.season_usage_pct:.1f}%) -- {a.usage_delta}")
        wp = f"{a.window_p_plus:.0f}" if a.window_p_plus is not None else "--"
        ws = f"{a.window_s_plus:.0f}" if a.window_s_plus is not None else "--"
        wl = f"{a.window_l_plus:.0f}" if a.window_l_plus is not None else "--"
        lines.append(f"- P+: {wp} (season {a.season_p_plus:.0f}) -- {a.p_plus_delta}")
        lines.append(f"- S+: {ws} (season {a.season_s_plus:.0f}) -- {a.s_plus_delta}")
        lines.append(f"- L+: {wl} (season {a.season_l_plus:.0f}) -- {a.l_plus_delta}")
        if a.small_sample:
            lines.append("- *Small sample*")

    # Execution section
    if execution_rows:
        lines.append("")
        lines.append("### Execution")
        for e in execution_rows:
            lines.append(f"- CSW%: {e.csw_pct:.1f}")
            lines.append(f"- Zone%: {e.zone_rate:.1f}")
            lines.append(f"- Chase%: {e.chase_rate:.1f}")
            xwhiff = f"{e.xwhiff_p:.3f}" if e.xwhiff_p is not None else "--"
            xswing = f"{e.xswing_p:.3f}" if e.xswing_p is not None else "--"
            lines.append(f"- xWhiff P+: {xwhiff}")
            lines.append(f"- xSwing P+: {xswing}")
            pctl = f"{e.xrv100_percentile}" if e.xrv100_percentile is not None else "--"
            lines.append(f"- xRV100 percentile: {pctl}")

    # Platoon section
    if platoon_rows:
        lines.append("")
        lines.append("### Platoon Splits")
        for s in platoon_rows:
            if s.available:
                usage = f"{s.window_usage_pct:.1f}%" if s.window_usage_pct is not None else "--"
                pp = f"P+ {s.window_p_plus:.0f}" if s.window_p_plus is not None else ""
                lines.append(
                    f"- vs {s.platoon_side}: {usage} (season {s.season_usage_pct:.1f}%) "
                    f"-- {s.usage_delta} {pp}"
                )

    # Intermediates section (P vs S location impact)
    if intermediates_rows:
        lines.append("")
        lines.append("### Model Internals: Location Impact")
        for im in intermediates_rows:
            lines.append(_ps_line("xSwing", im.xswing_p, im.xswing_s))
            lines.append(_ps_line("xWhiff", im.xwhiff_p, im.xwhiff_s))
            lines.append(_ps_line("xSwSt", im.xswst_p, im.xswst_s))
            lines.append(_ps_line_rv("xRV100", im.xrv100_p, im.xrv100_s))

    # Attribution section (13-outcome xRV decomposition)
    if attribution_rows:
        lines.append("")
        lines.append("### Component Attribution (xRV100 Decomposition)")
        for attr in attribution_rows:
            lines.append(f"Total raw xRV100: {attr.total_xrv100:.2f}")
            lines.append("")
            lines.append("| Outcome | Contribution | Share |")
            lines.append("|---------|-------------|-------|")
            for oc in attr.contributions:
                share = (
                    f"{(oc.contribution / attr.total_xrv100 * 100):+.1f}%"
                    if attr.total_xrv100 != 0
                    else f"{0:.1f}%"
                )
                lines.append(f"| {oc.outcome} | {oc.contribution:+.3f} | {share} |")

    return "\n".join(lines)


def _ps_line(label: str, p: float | None, s: float | None) -> str:
    """Format a P vs S comparison line for probability metrics."""
    p_str = f"{p * 100:.1f}%" if p is not None else "--"
    s_str = f"{s * 100:.1f}%" if s is not None else "--"
    if p is not None and s is not None:
        delta = (p - s) * 100
        return f"- {label}: P {p_str}, S {s_str}, location delta {delta:+.1f}pp"
    return f"- {label}: P {p_str}, S {s_str}"


def _ps_line_rv(label: str, p: float | None, s: float | None) -> str:
    """Format a P vs S comparison line for run-value metrics (xRV100 scale)."""
    p_str = f"{p:.2f}" if p is not None else "--"
    s_str = f"{s:.2f}" if s is not None else "--"
    if p is not None and s is not None:
        delta = p - s
        return f"- {label}: P {p_str}, S {s_str}, location delta {delta:+.2f}"
    return f"- {label}: P {p_str}, S {s_str}"


# ═══════════════════════════════════════════════════════════════════════
# AGENT FACTORY
# ═══════════════════════════════════════════════════════════════════════

_qa_agent_cache: dict[tuple[str, str, ThinkingEffort], Agent[QADeps, str]] = {}


def _make_qa_agent(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona | None = None,
) -> Agent[QADeps, str]:
    """Create (or return cached) QA agent for the given provider, thinking, and persona.

    Args:
        provider: LLM provider key ('gemini' or 'claude').
        thinking: Thinking effort level.
        persona: Writer voice persona. Defaults to DEFAULT_PERSONA.

    Returns:
        Configured Agent with get_pitcher_summary and get_pitch_detail tools.

    Raises:
        ValueError: If provider is not in PROVIDERS.
    """
    resolved = persona or DEFAULT_PERSONA
    key = (provider, resolved.id, thinking)
    if key in _qa_agent_cache:
        return _qa_agent_cache[key]

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}, expected one of: {', '.join(PROVIDERS)}")

    model = PROVIDERS[provider]
    settings = make_model_settings(provider, thinking, 0.3, max_tokens=TOKEN_BUDGET_LARGE)
    instructions = build_system_prompt(resolved, ANSWER) + "\n\n" + ANALYST_MECHANICS

    agent: Agent[QADeps, str] = Agent(
        model,
        deps_type=QADeps,
        output_type=str,
        instructions=instructions,
        model_settings=settings,
        tools=[get_pitcher_summary, get_pitch_detail],
        toolsets=[skill_toolset()],
        defer_model_check=True,
    )
    _qa_agent_cache[key] = agent
    return agent


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════


def ask_question_streaming(
    question: str,
    context: PitcherContext,
    data: PitcherData,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona | None = None,
    _model_override: Any = None,
) -> str:
    """Ask a natural-language question about a pitcher with streaming output.

    Args:
        question: The user's question in natural language.
        context: Assembled PitcherContext for the pitcher.
        data: Loaded PitcherData for the pitcher.
        provider: LLM provider key ('gemini' or 'claude').
        thinking: Thinking effort level.
        persona: Writer voice persona. Defaults to DEFAULT_PERSONA.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        The agent's complete response as a string.
    """
    agent = _make_qa_agent(provider, thinking, persona)
    deps = QADeps(context=context, data=data)

    kwargs: dict[str, Any] = {"user_prompt": question, "deps": deps}
    if _model_override is not None:
        kwargs["model"] = _model_override

    stream = agent.run_stream_sync(**kwargs)
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end="", flush=True)
        chunks.append(delta)
    print()
    return "".join(chunks)

