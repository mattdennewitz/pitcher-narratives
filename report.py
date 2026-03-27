"""Two-phase report generation: Data Synthesizer → Editor/Analyst.

Phase 1 (Synthesizer): Extracts signal from noise — structured bullet
points of key findings, deltas, and trends. No narrative.

Phase 2 (Editor): Weaves those facts into a skeptical, two-paragraph
capsule with decisive projection. Elite sabermetric analyst voice.
"""

from __future__ import annotations

import re
import sys

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings, ThinkingEffort

from context import PitcherContext

__all__ = ["generate_report_streaming", "check_hallucinated_metrics", "print_prompts", "HallucinationReport", "THINKING_LEVELS", "PROVIDERS"]

THINKING_LEVELS: list[ThinkingEffort] = ['minimal', 'low', 'medium', 'high', 'xhigh']
PROVIDERS = {
    'openai': 'openai:gpt-5.4-mini',
    'claude': 'anthropic:claude-sonnet-4-6',
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

1. Identify the Fastball Baseline: Note the average velocity, Pitching+ \
score, and shape (movement deltas) of the primary fastball over the \
recent sample versus the season baseline. Flag gains AND drops equally.

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

8. Absolute Objectivity: Do not use subjective adjectives. Do not \
project future performance. Report the math and the physical pitch \
characteristics. State sample sizes.

OUTPUT FORMAT — Use this exact structure:

## Fastball Quality & Velocity Trends
[Bulleted facts: baseline vs recent velo, P+, movement, within-game arc]

## Pitch Mix & Usage Shifts
[Bulleted facts: largest usage deltas, new/abandoned pitches, mix evolution]

## Execution & Outcomes
[Bulleted facts: CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 by pitch type]

## Platoon Splits
[Bulleted facts: pitch mix and P+ vs LHB and vs RHB separately]

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
- Stamina trajectory: does velocity or P+ hold, improve, or cliff?
- New weapons: any pitch showing a breakout P+ trend or usage surge?"""

_RP_SYNTH_GUIDANCE = """\
Additional focus for this reliever:
- Rest day impact on velocity and P+ (back-to-back vs rested — better or worse?)
- Primary weapon identification: what is the put-away pitch? Is it improving?
- Pitch count efficiency: how many pitches per batter faced?
- Platoon-specific strengths and vulnerabilities by handedness
- Workload trajectory: stuff improving as he stretches out, or degrading?
- Any pitch showing a breakout trend (new addition, shape change, usage surge)?"""


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
P+/S+/L+) or the pitcher's prior baseline.

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

6. Take a Stance: End the report with a decisive, unsentimental \
projection of the pitcher's value. Define their tier clearly (e.g., \
"profiles as a low-leverage reliever," "looks like a #4 starter until \
command improves," "a high-variance, blow-up candidate"). Do not hedge.

7. Voice: No clichés ("bulldog mentality," "pitches to contact," \
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


def _make_agents(
    provider: str = 'openai',
    thinking: ThinkingEffort = 'high',
) -> tuple[Agent[None, str], Agent[None, str]]:
    """Create synthesizer and editor agents for the given provider and thinking level."""
    model = PROVIDERS[provider]
    # Anthropic's default max_tokens (4096) is too low when thinking is enabled
    # because thinking tokens count against the budget.
    extra = {'max_tokens': 16384} if provider == 'claude' else {}
    settings = ModelSettings(thinking=thinking, **extra)
    synth = Agent(
        model,
        output_type=str,
        system_prompt=_SYNTHESIZER_PROMPT,
        model_settings=settings,
        defer_model_check=True,
    )
    ed = Agent(
        model,
        output_type=str,
        system_prompt=_EDITOR_PROMPT,
        model_settings=settings,
        defer_model_check=True,
    )
    return synth, ed


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════

def _build_synthesizer_message(ctx: PitcherContext) -> str:
    """Build the Phase 1 user message with role-conditional guidance."""
    guidance = _SP_SYNTH_GUIDANCE if ctx.role == "SP" else _RP_SYNTH_GUIDANCE
    return (
        f"## Role-Specific Focus\n{guidance}\n\n"
        f"## Pitcher Data\n{ctx.to_prompt()}"
    )


def _build_editor_message(
    ctx: PitcherContext,
    synthesis: str,
) -> str:
    """Build the Phase 2 user message with synthesis output."""
    return (
        f"## Pitcher\n"
        f"{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Key Findings From Data Analysis\n{synthesis}\n\n"
        f"Write the two-paragraph scouting capsule now."
    )


def print_prompts(ctx: PitcherContext) -> None:
    """Print both LLM prompts (system + user) to stderr and exit."""
    synth_user = _build_synthesizer_message(ctx)
    editor_user = _build_editor_message(ctx, "<synthesis output would go here>")

    sep = "═" * 72
    print(f"\n{sep}", file=sys.stderr)
    print("PHASE 1: SYNTHESIZER", file=sys.stderr)
    print(f"{sep}\n", file=sys.stderr)
    print("── System Prompt ──\n", file=sys.stderr)
    print(_SYNTHESIZER_PROMPT, file=sys.stderr)
    print("\n── User Message ──\n", file=sys.stderr)
    print(synth_user, file=sys.stderr)

    print(f"\n{sep}", file=sys.stderr)
    print("PHASE 2: EDITOR", file=sys.stderr)
    print(f"{sep}\n", file=sys.stderr)
    print("── System Prompt ──\n", file=sys.stderr)
    print(_EDITOR_PROMPT, file=sys.stderr)
    print("\n── User Message ──\n", file=sys.stderr)
    print(editor_user, file=sys.stderr)


def generate_report_streaming(
    ctx: PitcherContext,
    *,
    provider: str = 'openai',
    thinking: ThinkingEffort = 'high',
    _model_override=None,
) -> str:
    """Generate a two-phase scouting report and stream the final output.

    Phase 1 (Synthesizer): Extracts key findings as structured bullets.
    Phase 2 (Editor): Writes the final two-paragraph capsule.

    Only Phase 2 output is streamed to stdout. Phase 1 runs silently.

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key ('openai' or 'claude').
        thinking: Thinking effort level.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        The complete report text (Phase 2 output) as a string.
    """
    synthesizer, editor = _make_agents(provider, thinking)

    synth_kwargs: dict = {"user_prompt": _build_synthesizer_message(ctx)}
    if _model_override is not None:
        synth_kwargs["model"] = _model_override

    # Phase 1: Silent synthesis
    synth_result = synthesizer.run_sync(**synth_kwargs)
    synthesis = synth_result.output

    # Phase 2: Streamed editorial
    editor_kwargs: dict = {
        "user_prompt": _build_editor_message(ctx, synthesis),
    }
    if _model_override is not None:
        editor_kwargs["model"] = _model_override

    stream = editor.run_stream_sync(**editor_kwargs)
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end='', flush=True)
        chunks.append(delta)
    print()  # Final newline
    return ''.join(chunks)


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
_KNOWN_METRICS = frozenset({
    # Core Pitching+ family
    "P+", "S+", "L+", "Pitching+", "Stuff+", "Location+",
    "P+2080", "S+2080", "L+2080",
    # Run value
    "xRV100", "xRV",
    # Expected outcomes
    "xWhiff", "xSwing", "xGOr", "xPUr", "xBA", "xwOBA", "xSLG",
    "xERA", "xSwSt",
    # Batted ball / approach
    "CSW%", "CSW", "O-Swing%", "Zone%", "Chase%", "HardHit%",
    "Barrel%", "xHR100",
    # Velocity / movement
    "IVB", "HB", "pfx_x", "pfx_z",
    # Statcast standard
    "wOBA", "BABIP", "ISO",
    # Commonly referenced in editorial voice
    "SwStr%", "K-BB%", "xFIP",
})

# Traditional outcome stats that the editor prompt warns against citing.
# These aren't "hallucinated" but should be flagged as potentially
# inappropriate for a scouting report focused on process metrics.
_TRADITIONAL_STATS = frozenset({
    "ERA", "FIP", "WHIP", "WAR", "W-L",
    "K%", "BB%", "HR/9", "K/9", "BB/9",
    "ERA+", "FIP-", "Wins", "Losses", "Saves", "IP",
})

_METRIC_PATTERN = re.compile(
    r'\b('
    # xMetric pattern (xBA, xWhiff, xwOBA, xRV100, etc.)
    r'x[A-Za-z][A-Za-z0-9]*'
    r'|'
    # Acronym+% pattern (CSW%, O-Swing%, Zone%, K-BB%, SwStr%, Barrel%)
    r'[A-Z][A-Za-z]*-?[A-Z]*%'
    r'|'
    # Pitching+ family (P+, S+, L+, P+2080, etc.)
    r'[PSL]\+(?:2080)?'
    r'|'
    # Other named advanced metrics
    r'(?:IVB|HB|pfx_[xz]|wOBA|BABIP|ISO|xRV100|xFIP|Pitching\+|Stuff\+|Location\+)'
    r')(?=[\s,.);\-:]|$)'
)

_TRADITIONAL_PATTERN = re.compile(
    r'(?<![A-Za-z\-])('
    r'ERA\+?'
    r'|FIP-?'
    r'|WHIP'
    r'|WAR'
    r'|W-L'
    r'|K%'
    r'|BB%'
    r'|HR/9'
    r'|K/9'
    r'|BB/9'
    r'|Wins'
    r'|Losses'
    r'|Saves'
    r'|IP'
    r')(?=[\s,.);\-:]|$)'
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
