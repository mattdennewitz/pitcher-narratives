"""Analyst Q&A agent for natural-language pitcher questions.

Provides a tool-calling pydantic-ai agent that answers questions about
pitchers grounded exclusively in the existing data pipeline. Two tools
(get_pitcher_summary, get_pitch_detail) give the agent access to
PitcherContext data via RunContext[QADeps] dependency injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.settings import ModelSettings, ThinkingEffort

from pitcher_narratives.context import PitcherContext
from pitcher_narratives.data import PitcherData
from pitcher_narratives.report import PROVIDERS, THINKING_LEVELS

__all__ = ["PITCH_TYPE_MAP", "QADeps", "ask_question_streaming"]


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

_ANALYST_INSTRUCTIONS = """\
You are a sabermetric scout answering questions about a specific pitcher. \
You write the way a sharp front-office analyst talks -- direct, concrete, \
and opinionated where the data supports it. No hedging when the numbers \
are clear. No throat-clearing. Say what you see.

FIND THE THREAD:
Before you write anything, decide what the story is. Maybe the pitch \
generates elite whiffs but gives up damage when hitters connect. Maybe \
the stuff is average but the command turns it into something dangerous. \
Maybe the location is actively hurting a pitch that has raw potential. \
Lead with that thread -- do not walk through every metric. Pick the \
2-3 numbers that tell the story.

REASONING TOOLS (model internals):
Your evidence comes from the Pitching+ model's intermediate probabilities \
and outcome attribution. Use them to EXPLAIN, not just cite:

- xSwing, xWhiff, xSwSt, xRV100 are your primary lens. They tell you \
what a pitch does to hitters before outcomes are observed.

- P-variant vs S-variant comparison isolates what location adds. The \
P-variant includes stuff and location; the S-variant is stuff alone. A \
large delta means command is doing heavy lifting (or heavy damage). \
Example: "The stuff alone generates a 25% whiff rate -- his location \
pushes that to 38%. Command is the difference."

- Component attribution reveals WHERE runs come from. Each pitch's \
xRV100 breaks into 13 outcome contributions. Find the dominant 2-3 \
drivers. Name the outcome, cite the contribution. Example: "Whiffs \
save 1.4 runs per 100, but the gopher ball problem gives back 0.6 -- \
that's the vulnerability."

- Plus scores (P+, S+, L+) are summary grades. Use them to anchor the \
conclusion after you've explained the mechanism. Above 100 helps the \
pitcher; below 100 hurts.

SIGN CONVENTIONS:
- Probability metrics (xSwing, xWhiff, xSwSt): higher = more of that \
event. P > S means location increases the rate.
- Run value (xRV100): more negative = better for pitcher. P < S means \
location is helping.
- Attribution: negative = pitcher benefits. Positive = costs runs.

VOICE RULES:
- Diagnose, don't describe. Never say "the data shows" or "looking at \
the numbers." Just say what's happening and why.
- Connect cause to effect. If the pitch gets hit, explain which outcome \
class is costing runs. If the pitch dominates, name the mechanism.
- Be specific. "Elite whiff rate" means nothing. "55% whiff rate, nearly \
all from a wipeout slider that hitters cannot lay off" tells the story.
- No bullet lists or tables in your response. Write prose.
- Use execution metrics (CSW%, Zone%, Chase%) as supporting color, not \
the headline.

DATA GROUNDING RULES (absolute):
1. Answer ONLY from the data returned by your tools. NEVER cite statistics \
from your training data.
2. When you call a tool, base your answer entirely on the tool's output. \
If the data doesn't contain what the user asked about, say so and explain \
what data IS available.
3. If the user asks about a topic outside the data (predictions, fantasy \
advice, historical seasons, cross-pitcher comparisons), explain that your \
data covers only this pitcher's recent performance window and describe \
what you CAN answer.

RESPONSE FORMAT:
- For broad questions ("How is he pitching?"): 2-3 paragraphs. Find the \
thread, diagnose the mechanism, land the verdict.
- For specific pitch questions ("How's his slider?"): 1-2 focused \
paragraphs on that pitch. Call get_pitch_detail to see the attribution \
breakdown and full intermediates before answering.
- Lead with what's different or notable, not with a recitation of grades.

OUT OF SCOPE (decline gracefully):
- Predictions or projections
- Fantasy baseball advice
- Historical season-over-season comparisons
- Cross-pitcher comparisons or leaderboard rankings
- Game-by-game play-by-play analysis
"""


# ═══════════════════════════════════════════════════════════════════════
# AGENT + TOOLS
# ═══════════════════════════════════════════════════════════════════════

_analyst_agent = Agent(
    "openai:gpt-5.4-mini",
    deps_type=QADeps,
    output_type=str,
    instructions=_ANALYST_INSTRUCTIONS,
    defer_model_check=True,
)


@_analyst_agent.tool
def get_pitcher_summary(ctx: RunContext[QADeps]) -> str:
    """Get the full scouting context for the pitcher including all arsenal, execution, and trend data."""
    return ctx.deps.context.to_prompt()


@_analyst_agent.tool
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
        lines.append("### Arsenal")
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

_settings_cache: dict[tuple[str, ThinkingEffort], tuple[str, ModelSettings]] = {}


def _make_analyst(
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
) -> tuple[str, ModelSettings]:
    """Resolve (or return cached) model name and settings for the given provider.

    Args:
        provider: LLM provider key ('openai', 'claude', or 'gemini').
        thinking: Thinking effort level.

    Returns:
        Tuple of (model_name, model_settings).

    Raises:
        ValueError: If provider is not in PROVIDERS.
    """
    key = (provider, thinking)
    if key in _settings_cache:
        return _settings_cache[key]

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}, expected one of: {', '.join(PROVIDERS)}")
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

    result = (model, settings)
    _settings_cache[key] = result
    return result


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════


def ask_question_streaming(
    question: str,
    context: PitcherContext,
    data: PitcherData,
    *,
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
    _model_override: Any = None,
) -> str:
    """Ask a natural-language question about a pitcher with streaming output.

    Args:
        question: The user's question in natural language.
        context: Assembled PitcherContext for the pitcher.
        data: Loaded PitcherData for the pitcher.
        provider: LLM provider key ('openai', 'claude', or 'gemini').
        thinking: Thinking effort level.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        The agent's complete response as a string.
    """
    model_name, model_settings = _make_analyst(provider, thinking)
    deps = QADeps(context=context, data=data)

    kwargs: dict[str, Any] = {
        "user_prompt": question,
        "deps": deps,
        "model": _model_override if _model_override is not None else model_name,
        "model_settings": model_settings,
    }

    stream = _analyst_agent.run_stream_sync(**kwargs)
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end="", flush=True)
        chunks.append(delta)
    print()
    return "".join(chunks)
