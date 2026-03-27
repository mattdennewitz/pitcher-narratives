"""Four-phase report generation pipeline.

Phase 1 (Synthesizer): Extracts signal from noise — structured bullet
points of key findings, deltas, and trends. No narrative.

Phase 2 (Editor): Weaves those facts into a skeptical, two-paragraph
capsule with decisive projection. Elite sabermetric analyst voice.

Phase 3 (Hook Writer): Distills synthesis into a 1-2 sentence social
media hook for front-office audiences.

Phase 4 (Fantasy Analyst): Produces 3 actionable fantasy baseball
insights with specific metric citations.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, CachePoint
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.settings import ModelSettings, ThinkingEffort

from pitcher_narratives.context import PitcherContext

__all__ = [
    "PROVIDERS",
    "THINKING_LEVELS",
    "HallucinationReport",
    "ReportResult",
    "check_hallucinated_metrics",
    "generate_report_streaming",
    "print_prompts",
    "write_data_file",
]

THINKING_LEVELS: list[ThinkingEffort] = ["minimal", "low", "medium", "high", "xhigh"]
PROVIDERS = {
    "openai": "openai:gpt-5.4-mini",
    "claude": "anthropic:claude-sonnet-4-6",
    "gemini": "google-gla:gemini-3.1-pro-preview",
}


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: THE DATA SYNTHESIZER (THE SCOUT)
# ═══════════════════════════════════════════════════════════════════════

_SYNTHESIZER_PROMPT = """\
You are an elite MLB data analyst. Your job is to parse pitch-tracking \
data for a given pitcher over a recent window and extract the objective, \
mathematical signals from the noise. You are not writing a story. You \
are preparing a factual briefing document for a senior sabermetric writer.

INSTRUCTIONS:

1. Identify the Fastball Baseline: Note the average velocity and the \
full Pitching+ triad — P+ (overall), S+ (stuff/shape), L+ (location/command) \
— plus movement deltas for the primary fastball over the recent sample \
versus the season baseline. Distinguish between stuff changes (S+) and \
command changes (L+) — they have different implications. Flag gains AND \
drops equally.

2. Track Intra-Game Stamina: Look at the TTO data and appearance logs. \
Flag velocity drops, velocity gains, or P+ changes in later passes or \
at higher pitch counts. Note if stuff holds, improves, or degrades.

3. Isolate Usage Shifts: Find the largest positive and negative deltas \
in pitch usage percentage compared to the season average. Flag any pitch \
that was abandoned or newly introduced.

4. Pinpoint Execution Changes: Identify which pitches are generating \
the highest CSW% and Chase%. Note if a pitch with a high P+ score is \
suffering from low Zone% (stuff without command). Note if a pitch with \
low P+ is succeeding on location alone.

5. Extract Platoon Specifics: Document exactly how the pitch mix and \
P+ change against LHB versus RHB. Identify platoon-specific weapons \
and vulnerabilities.

6. Flag Breakout Indicators: New pitches gaining traction, velocity \
gains backed by movement changes, P+ improvements that suggest a real \
development — not just noise.

7. Flag Regression Risks: Small sample caveats, unsustainable chase \
rates, high P+ with poor zone rates, or results that outpace stuff.

8. Evaluate Release Point Mechanics: Compare each pitch type's \
release position (horizontal, vertical) and extension against that \
pitcher's own season baseline — NOT league averages. Consistent \
release points across pitch types suggest clean mechanics and \
deception. Shifts in a single pitch type may indicate tinkering or \
development. Shifts across ALL pitch types suggest a mechanical \
change, fatigue, or potential injury concern. Flag the magnitude \
and direction of any meaningful delta.

9. Absolute Objectivity: Do not use subjective adjectives. Do not \
project future performance. Report the math and the physical pitch \
characteristics. State sample sizes.

OUTPUT FORMAT — Use this exact structure:

## Fastball Quality & Velocity Trends
[Bulleted facts: baseline vs recent velo, P+/S+/L+ triad, movement, within-game arc]

## Pitching+ Profile
[Bulleted facts: per-pitch-type P+, S+, L+ scores and deltas vs season. \
Identify which pitches have elite stuff (S+ > 115) but poor command (L+ < 90) \
or vice versa. Flag divergences between S+ and L+ — they tell different stories.]

## Pitch Mix & Usage Shifts
[Bulleted facts: largest usage deltas, new/abandoned pitches, mix evolution]

## Execution & Outcomes
[Bulleted facts: CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 by pitch type]

## Platoon Splits
[Bulleted facts: pitch mix and P+ vs LHB and vs RHB separately]

## Release Point Mechanics
[Bulleted facts: per-pitch-type release x/z/extension deltas vs pitcher's own \
season baseline, consistency across types, mechanical flags]

## Workload & Stamina
[Bulleted facts: pitch counts, rest days, TTO degradation/improvement, IP trends]

## Key Signal
[1-2 bullets: the single most important improvement AND the single most \
important concern — the two facts that should anchor the editorial]"""

_SP_SYNTH_GUIDANCE = """\
Additional focus for this starter:
- TTO pass breakdown: which pitches gain or lose effectiveness by pass?
- Pitch mix evolution across passes: is he leaning on something new late?
- Platoon-specific TTO patterns (what does he throw vs LHB in pass 3?)
- Stamina trajectory: does velocity, S+, or L+ hold, improve, or cliff?
- Pitching+ triad per pitch: cite P+, S+, L+ — flag stuff-command divergences
- New weapons: any pitch showing a breakout S+ or P+ trend or usage surge?"""

_RP_SYNTH_GUIDANCE = """\
Additional focus for this reliever:
- Rest day impact on velocity, S+, and L+ (back-to-back vs rested — better or worse?)
- Primary weapon identification: what is the put-away pitch? Cite its P+/S+/L+ triad
- Pitch count efficiency: how many pitches per batter faced?
- Platoon-specific strengths and vulnerabilities by handedness
- Workload trajectory: S+ improving as he stretches out, or degrading? L+ fading?
- Any pitch showing a breakout trend (S+ surge, shape change, usage surge)?"""


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: THE EDITOR (THE ANALYST)
# ═══════════════════════════════════════════════════════════════════════

_EDITOR_PROMPT = """\
You are an elite, sabermetrically inclined baseball writer. You write \
for front offices, advanced fantasy players, and data-driven fans. Your \
tone is objective, mildly skeptical, and highly analytical. You are not \
a cheerleader. You do not use clichés.

INPUT: A structured briefing document from your data analyst containing \
objective facts about a pitcher's recent window, including Pitching+ \
scores, velocity changes, usage shifts, and execution metrics.

INSTRUCTIONS:

1. Structure — The 2-3 Paragraph Capsule:

Paragraph 1 (The Setup): Identify the core change or the current state \
of the stuff. Did they add a pitch? Did velocity drop or gain? How are \
the raw shapes grading out (P+, S+, movement)? Ground the reader in \
what is physically different about this pitcher right now.

Paragraph 2+ (The Verdict): Explain how that stuff is playing in the \
zone. Address platoon splits directly — what works vs LHB vs RHB. \
Highlight the glaring weakness or the path to sustained success. \
Deliver a definitive conclusion on the pitcher's immediate future.

Use a third paragraph only when the Setup needs separation (e.g., \
fastball changes warrant one paragraph, arsenal evolution warrants \
another, before the Verdict).

2. Contextualize Every Metric: Never state a metric (velocity, movement, \
chase rate, P+) without grounding it against the MLB average (100 for \
P+/S+/L+) or the pitcher's prior baseline. Always cite the full Pitching+ \
triad (P+, S+, L+) when discussing pitch quality — S+ tells you about raw \
stuff (shape, movement, velocity), L+ tells you about command and location. \
A pitcher with 120 S+ and 85 L+ has elite stuff but poor command — very \
different from 95 S+ and 120 L+ (command artist, mediocre stuff).

3. Diagnose, Do Not Just Describe: Connect the outcome to the physical \
input. If strikeout rates are down, explain that it is tied to a drop \
in vertical break or lost velocity. Link the "what" to the "why."

4. Be Skeptical: Do not trust small samples blindly. Flag profiles as \
regression risks if run prevention is good but zone rates are poor or \
velocity is fading. Use phrases like "small-sample issues," "I'm not \
convinced," "prone to blow-ups" where warranted.

5. Platoon Everything: Disaggregate pitch mix and success by batter \
handedness. Note what the pitcher does differently against LHB versus \
RHB. A sweeping slider's success must be framed by who is in the box.

6. Integrate Release Point Changes: When the data shows release \
point shifts, weave them into the mechanical narrative. A uniform \
shift across all pitch types suggests a delivery change — connect \
it to velocity or movement changes. A shift in one pitch type \
suggests tinkering with that offering. All baselines are the \
pitcher's own season averages, not league norms.

7. Take a Stance: End the report with a decisive, unsentimental \
projection of the pitcher's value. Define their tier clearly (e.g., \
"profiles as a low-leverage reliever," "looks like a #4 starter until \
command improves," "a high-variance, blow-up candidate"). Do not hedge.

8. Voice: No clichés ("bulldog mentality," "pitches to contact," \
"electric stuff"). Avoid "not just X, it's Y" or "it's a X — not \
just a Y" constructions — state what something IS, don't define it \
by what it isn't. Rely on metrics: K-BB%, SwStr%, CSW%, P+/S+/L+, \
xRV100. Write with authority and economy — every sentence must earn \
its place.

STRICT CONSTRAINTS:
- Rely entirely on the data provided in the input. Do not hallucinate \
metrics or trends.
- Ignore traditional outcome stats like Wins and basic ERA unless \
provided as context. Base analysis on underlying metrics.
- No bullet points. No headers. No introductory fluff.
- Start immediately with the analysis. Your first sentence should be \
about the pitcher's stuff, not about "looking at the data."
- Do not soften your conclusions. Be direct."""


_AgentTuple = tuple[Agent[None, str], Agent[None, str], Agent[None, str], Agent[None, str]]
_agent_cache: dict[tuple[str, ThinkingEffort], _AgentTuple] = {}


def _make_agents(
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
) -> _AgentTuple:
    """Create (or return cached) four pipeline agents for the given provider and thinking level."""
    key = (provider, thinking)
    if key in _agent_cache:
        return _agent_cache[key]

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}, expected one of: {', '.join(PROVIDERS)}")
    model = PROVIDERS[provider]

    if provider == "gemini":
        # Gemini 3 uses GoogleModelSettings with thinking_level ('low' or 'high')
        gemini_level = "high" if thinking in ("high", "xhigh") else "low"
        settings: ModelSettings = GoogleModelSettings(
            google_thinking_config={"thinking_level": gemini_level},
            temperature=1.0,
            max_tokens=16384,
        )
    elif provider == "claude":
        # Anthropic's default max_tokens (4096) is too low when thinking is enabled
        settings = ModelSettings(thinking=thinking, max_tokens=16384)
    else:
        settings = ModelSettings(thinking=thinking)
    prompts = (_SYNTHESIZER_PROMPT, _EDITOR_PROMPT, _HOOK_PROMPT, _FANTASY_PROMPT)
    agents: _AgentTuple = tuple(  # type: ignore[assignment]
        Agent(model, output_type=str, system_prompt=p, model_settings=settings, defer_model_check=True)
        for p in prompts
    )
    _agent_cache[key] = agents
    return agents


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: THE HOOK WRITER (SOCIAL MEDIA)
# ═══════════════════════════════════════════════════════════════════════

_HOOK_PROMPT = """\
You are a sharp, analytically-minded baseball writer crafting a single \
headline or social post. Given key findings from a pitcher's latest \
appearance, write ONE sentence — a headline, not a paragraph. It must \
fit in a Bluesky post or X/Twitter post (under 280 characters).

Rules:
- One sentence. Period. No run-on sentences joined by dashes or semicolons.
- Name the pitcher, name the pitch or metric, state the direction.
- Write like a wire service headline: punchy, specific, authoritative.
- No hashtags, no emojis, no hype words, no questions.
- It must stand alone without any other context."""


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: THE FANTASY ANALYST
# ═══════════════════════════════════════════════════════════════════════

_FANTASY_PROMPT = """\
You are a fantasy baseball analyst who writes like a news wire. Your \
audience is competitive league managers scanning for actionable intel. \
Given key findings from a pitcher's latest appearance, write exactly 3 \
bullet points — Axios-style: short, declarative, news-first.

Voice and perspective:
- Write as an analyst reporting news, not as an advisor issuing commands.
- Lead with the fact or trend, then explain why it matters for fantasy.
- Cite one specific metric per bullet (P+, velocity delta, usage shift, \
platoon split, workload flag).
- No run-on sentences. No semicolons joining two thoughts. One idea per \
bullet.

What matters for fantasy: ownership changes, streaming value, matchup \
dependency, injury/workload red flags, category impact (Ks, ERA, WHIP).

Format: exactly 3 lines, each starting with "- ". Plain text — no bold, \
no labels, no prefixes. Just the insight. Nothing else — no intro, no \
summary, no headers."""


class ReportResult(BaseModel):
    """Structured output from the multi-phase report pipeline."""

    narrative: str
    social_hook: str
    fantasy_insights: str


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════


_UserPrompt = list[str | CachePoint]
"""Type alias for user prompts with cache breakpoints."""


def _build_synthesizer_message(ctx: PitcherContext) -> _UserPrompt:
    """Build the Phase 1 user message with cache breakpoint after role guidance.

    Role guidance is stable across all pitchers of the same role (SP/RP),
    so caching it avoids re-processing ~120 tokens per pitcher.
    """
    guidance = _SP_SYNTH_GUIDANCE if ctx.role == "SP" else _RP_SYNTH_GUIDANCE
    return [
        f"## Role-Specific Focus\n{guidance}",
        CachePoint(),
        f"## Pitcher Data\n{ctx.to_prompt()}",
    ]


def _build_editor_message(ctx: PitcherContext, synthesis: str) -> _UserPrompt:
    """Build the Phase 2 user message with cache breakpoint after synthesis.

    Synthesis output is shared across Phases 2/3/4, so caching it here
    means Phases 3 and 4 get a cache hit on the same prefix.
    """
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Key Findings From Data Analysis\n{synthesis}",
        CachePoint(),
        "Write the two-paragraph scouting capsule now.",
    ]


def _build_hook_message(ctx: PitcherContext, synthesis: str) -> _UserPrompt:
    """Build the Phase 3 user message with cache breakpoint after synthesis."""
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n## Key Findings\n{synthesis}",
        CachePoint(),
        "Write one social media hook (1-2 sentences). Focus on the single most notable change.",
    ]


def _build_fantasy_message(ctx: PitcherContext, synthesis: str) -> _UserPrompt:
    """Build the Phase 4 user message with cache breakpoint after synthesis."""
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n## Key Findings\n{synthesis}",
        CachePoint(),
        "Write exactly 3 bullet points of fantasy baseball insights. "
        "Each bullet must be actionable and cite a specific metric or trend.",
    ]


def _render_user_prompt(parts: _UserPrompt) -> str:
    """Render a user prompt (with CachePoints) as readable text."""
    return "\n".join("  ── [cache breakpoint] ──" if isinstance(p, CachePoint) else p for p in parts)


def _build_all_phases(ctx: PitcherContext) -> list[tuple[str, str, _UserPrompt]]:
    """Build (label, system_prompt, user_prompt) for all 4 phases."""
    placeholder = "<synthesis output would go here>"
    return [
        ("PHASE 1: SYNTHESIZER", _SYNTHESIZER_PROMPT, _build_synthesizer_message(ctx)),
        ("PHASE 2: EDITOR", _EDITOR_PROMPT, _build_editor_message(ctx, placeholder)),
        ("PHASE 3: HOOK WRITER", _HOOK_PROMPT, _build_hook_message(ctx, placeholder)),
        ("PHASE 4: FANTASY ANALYST", _FANTASY_PROMPT, _build_fantasy_message(ctx, placeholder)),
    ]


def write_data_file(ctx: PitcherContext, pitcher_id: int, provider: str) -> str:
    """Write all prompt data to data-{pitcherid}-{provider}.md and return the path."""
    sep = "═" * 72
    sections: list[str] = []
    for label, system, user in _build_all_phases(ctx):
        sections.append(f"\n{sep}\n{label}\n{sep}\n")
        sections.append(f"## System Prompt\n\n{system}\n")
        sections.append(f"## User Message\n\n{_render_user_prompt(user)}\n")

    filename = f"data-{pitcher_id}-{provider}.md"
    Path(filename).write_text("\n".join(sections))
    return filename


def print_prompts(ctx: PitcherContext) -> None:
    """Print all LLM prompts (system + user) to stderr and exit."""
    sep = "═" * 72
    for label, system, user in _build_all_phases(ctx):
        print(f"\n{sep}", file=sys.stderr)
        print(label, file=sys.stderr)
        print(f"{sep}\n", file=sys.stderr)
        print("── System Prompt ──\n", file=sys.stderr)
        print(system, file=sys.stderr)
        print("\n── User Message ──\n", file=sys.stderr)
        print(_render_user_prompt(user), file=sys.stderr)


def generate_report_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
    _model_override: Any = None,
) -> ReportResult:
    """Generate a four-phase scouting report and stream the editorial output.

    Phase 1 (Synthesizer): Extracts key findings as structured bullets.
    Phase 2 (Editor): Writes the final two-paragraph capsule.
    Phase 3 (Hook Writer): Distills synthesis into a 1-2 sentence social hook.
    Phase 4 (Fantasy Analyst): Produces 3 actionable fantasy baseball bullets.

    Only Phase 2 output is streamed to stdout. Phases 1, 3, and 4 run silently.

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key ('openai' or 'claude').
        thinking: Thinking effort level.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        ReportResult with narrative, social_hook, and fantasy_insights.
    """
    synthesizer, editor, hook_writer, fantasy_analyst = _make_agents(provider, thinking)

    synth_kwargs: dict[str, Any] = {"user_prompt": _build_synthesizer_message(ctx)}
    if _model_override is not None:
        synth_kwargs["model"] = _model_override

    # Phase 1: Silent synthesis
    synth_result = synthesizer.run_sync(**synth_kwargs)
    synthesis = synth_result.output

    # Phase 2: Streamed editorial
    editor_kwargs: dict[str, Any] = {
        "user_prompt": _build_editor_message(ctx, synthesis),
    }
    if _model_override is not None:
        editor_kwargs["model"] = _model_override

    stream = editor.run_stream_sync(**editor_kwargs)
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end="", flush=True)
        chunks.append(delta)
    print()  # Final newline

    # Phase 3: Social media hook (silent)
    hook_kwargs: dict[str, Any] = {
        "user_prompt": _build_hook_message(ctx, synthesis),
    }
    if _model_override is not None:
        hook_kwargs["model"] = _model_override

    hook_result = hook_writer.run_sync(**hook_kwargs)

    # Phase 4: Fantasy analyst (silent)
    fantasy_kwargs: dict[str, Any] = {
        "user_prompt": _build_fantasy_message(ctx, synthesis),
    }
    if _model_override is not None:
        fantasy_kwargs["model"] = _model_override

    fantasy_result = fantasy_analyst.run_sync(**fantasy_kwargs)

    return ReportResult(
        narrative="".join(chunks),
        social_hook=hook_result.output,
        fantasy_insights=fantasy_result.output,
    )


# ═══════════════════════════════════════════════════════════════════════
# METRIC HALLUCINATION GUARD
# ═══════════════════════════════════════════════════════════════════════


class HallucinationReport(BaseModel):
    """Structured result from metric hallucination checking.

    Separates unknown (possibly hallucinated) metrics from traditional
    outcome stats that the editor prompt warns against using.
    """

    unknown_metrics: list[str]
    outcome_stat_warnings: list[str]

    @property
    def is_clean(self) -> bool:
        """True when no unknown metrics and no outcome stat warnings found."""
        return not self.unknown_metrics and not self.outcome_stat_warnings


# Metrics that appear in the prompt payload and are safe to reference
_KNOWN_METRICS = frozenset(
    {
        # Core Pitching+ family
        "P+",
        "S+",
        "L+",
        "Pitching+",
        "Stuff+",
        "Location+",
        "P+2080",
        "S+2080",
        "L+2080",
        # Run value
        "xRV100",
        "xRV",
        # Expected outcomes
        "xWhiff",
        "xSwing",
        "xGOr",
        "xPUr",
        "xBA",
        "xwOBA",
        "xSLG",
        "xERA",
        "xSwSt",
        # Batted ball / approach
        "CSW%",
        "CSW",
        "O-Swing%",
        "Zone%",
        "Chase%",
        "HardHit%",
        "Barrel%",
        "xHR100",
        # Velocity / movement
        "IVB",
        "HB",
        "pfx_x",
        "pfx_z",
        # Statcast standard
        "wOBA",
        "BABIP",
        "ISO",
        # Commonly referenced in editorial voice
        "SwStr%",
        "K-BB%",
        "xFIP",
    }
)

# Traditional outcome stats that the editor prompt warns against citing.
# These aren't "hallucinated" but should be flagged as potentially
# inappropriate for a scouting report focused on process metrics.
_TRADITIONAL_STATS = frozenset(
    {
        "ERA",
        "FIP",
        "WHIP",
        "WAR",
        "W-L",
        "K%",
        "BB%",
        "HR/9",
        "K/9",
        "BB/9",
        "ERA+",
        "FIP-",
        "Wins",
        "Losses",
        "Saves",
        "IP",
    }
)

_METRIC_PATTERN = re.compile(
    r"\b("
    # xMetric pattern (xBA, xWhiff, xwOBA, xRV100, etc.)
    r"x[A-Za-z][A-Za-z0-9]*"
    r"|"
    # Acronym+% pattern (CSW%, O-Swing%, Zone%, K-BB%, SwStr%, Barrel%)
    r"[A-Z][A-Za-z]*-?[A-Z]*%"
    r"|"
    # Pitching+ family (P+, S+, L+, P+2080, etc.)
    r"[PSL]\+(?:2080)?"
    r"|"
    # Other named advanced metrics
    r"(?:IVB|HB|pfx_[xz]|wOBA|BABIP|ISO|xRV100|xFIP|Pitching\+|Stuff\+|Location\+)"
    r")(?=[\s,.);\-:]|$)"
)

_TRADITIONAL_PATTERN = re.compile(
    r"(?<![A-Za-z\-])("
    r"ERA\+?"
    r"|FIP-?"
    r"|WHIP"
    r"|WAR"
    r"|W-L"
    r"|K%"
    r"|BB%"
    r"|HR/9"
    r"|K/9"
    r"|BB/9"
    r"|Wins"
    r"|Losses"
    r"|Saves"
    r"|IP"
    r")(?=[\s,.);\-:]|$)"
)


def check_hallucinated_metrics(report_text: str) -> HallucinationReport:
    """Find metric-like and traditional stat terms in report text.

    Scans the LLM output for patterns that look like advanced baseball
    metrics (xMetric, Acronym%, P+/S+/L+ family) and flags any not
    present in _KNOWN_METRICS as unknown. Also detects traditional
    outcome stats that the editor prompt warns against using.

    Args:
        report_text: The LLM-generated report text.

    Returns:
        HallucinationReport with unknown_metrics and outcome_stat_warnings.
    """
    found = set(_METRIC_PATTERN.findall(report_text))
    unknown = sorted(found - _KNOWN_METRICS - _TRADITIONAL_STATS)

    traditional_found = set(_TRADITIONAL_PATTERN.findall(report_text))
    outcome_warnings = sorted(traditional_found & _TRADITIONAL_STATS)

    return HallucinationReport(
        unknown_metrics=unknown,
        outcome_stat_warnings=outcome_warnings,
    )
