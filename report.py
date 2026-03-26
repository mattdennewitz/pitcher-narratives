"""Two-phase report generation: Data Synthesizer → Editor/Analyst.

Phase 1 (Synthesizer): Extracts signal from noise — structured bullet
points of key findings, deltas, and trends. No narrative.

Phase 2 (Editor): Weaves those facts into a skeptical, two-paragraph
capsule with decisive projection. Elite sabermetric analyst voice.
"""

from __future__ import annotations

import re

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from context import PitcherContext

__all__ = ["generate_report_streaming", "check_hallucinated_metrics"]


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

synthesizer = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=str,
    system_prompt=_SYNTHESIZER_PROMPT,
    model_settings=ModelSettings(max_tokens=2048),
    defer_model_check=True,
)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: THE EDITOR (THE ANALYST)
# ═══════════════════════════════════════════════════════════════════════

_EDITOR_PROMPT = """\
You are an elite, sabermetrically inclined baseball analyst. You write \
for front offices and advanced fantasy players — not casual fans.

EDITORIAL GUIDELINES:

1. Anchor Every Metric: If you cite a pitch's velocity, shape, Pitching+ \
score, or usage, you MUST contextualize it against the MLB average (100 \
for P+/S+/L+) or the pitcher's prior baseline. Never state a metric in \
isolation.

2. Diagnose, Do Not Just Describe: Connect outcomes to physical pitch \
characteristics. If strikeouts are up, explain WHY — added break, \
velocity gain, usage shift. Link the "what" to the "why."

3. Be Skeptical: Do not trust small samples blindly. If a pitcher has a \
great stretch but poor zone rates and dropping velocity, flag it as a \
regression risk. Use phrases like "small-sample issues," "I'm not \
convinced," "prone to blow-ups" where warranted.

4. Platoon Everything: Treat the arsenal as two separate entities — how \
it works against righties and how it works against lefties. A sweeping \
slider's success must be framed by who is standing in the box.

5. Take a Stance: End with a decisive, unsentimental projection of the \
pitcher's value. Assign a concrete tier: "a low 4s ERA arm," "a #5 \
starter," "a leverage reliever," "mostly a ~4.30 ERA pitcher." Do not \
hedge with "it depends" — commit to a read.

6. Voice: No clichés ("bulldog mentality," "pitches to contact"). Rely \
on metrics: K-BB%, SwStr%, CSW%, P+/S+/L+, xRV100. Write with \
authority and economy — every sentence must earn its place.

STRUCTURE — The Two-Paragraph Punch:

Paragraph 1 (The Setup): Identify the core change or current state of \
the stuff. New pitch? Lost velocity? Usage shift? Mechanical adjustment? \
Ground the reader in what is physically different about this pitcher \
right now.

Paragraph 2 (The Verdict): Explain how that stuff is playing in the \
zone. Highlight the glaring weakness or the path to sustained success. \
Deliver the final projection — where does this pitcher slot?

CONSTRAINTS:
- Exactly two paragraphs. No headers, no tables, no bullet points.
- De-emphasize traditional box score stats (ERA, W/L) in the body. \
Base analysis on underlying metrics.
- Never fabricate metrics or trends not present in the provided data.
- Do not soften your conclusions. Be direct."""

editor = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=str,
    system_prompt=_EDITOR_PROMPT,
    model_settings=ModelSettings(max_tokens=2048),
    defer_model_check=True,
)


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


def generate_report_streaming(
    ctx: PitcherContext,
    *,
    _model_override=None,
) -> str:
    """Generate a two-phase scouting report and stream the final output.

    Phase 1 (Synthesizer): Extracts key findings as structured bullets.
    Phase 2 (Editor): Writes the final two-paragraph capsule.

    Only Phase 2 output is streamed to stdout. Phase 1 runs silently.

    Args:
        ctx: Assembled pitcher context.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        The complete report text (Phase 2 output) as a string.
    """
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

# Metrics that appear in the prompt payload and are safe to reference
_KNOWN_METRICS = frozenset({
    # Core Pitching+ family
    "P+", "S+", "L+", "Pitching+", "Stuff+", "Location+",
    "P+2080", "S+2080", "L+2080",
    # Run value
    "xRV100", "xRV",
    # Expected outcomes
    "xWhiff", "xSwing", "xGOr", "xPUr", "xBA", "xwOBA", "xSLG",
    # Batted ball / approach
    "CSW%", "CSW", "O-Swing%", "Zone%", "Chase%",
    # Velocity / movement
    "IVB", "HB", "pfx_x", "pfx_z",
    # Statcast standard
    "wOBA", "BABIP", "ISO",
    # Commonly referenced in editorial voice
    "SwStr%", "K-BB%", "xFIP",
})

_METRIC_PATTERN = re.compile(
    r'\b('
    # xMetric pattern (xBA, xWhiff, xRV100, etc.)
    r'x[A-Z][A-Za-z0-9]*'
    r'|'
    # Acronym+% pattern (CSW%, O-Swing%, Zone%, K-BB%, SwStr%)
    r'[A-Z][A-Za-z]*-?[A-Z]*%'
    r'|'
    # Pitching+ family (P+, S+2080, etc.)
    r'[PSL]\+(?:2080)?'
    r'|'
    # Other named advanced metrics
    r'(?:IVB|HB|pfx_[xz]|wOBA|BABIP|ISO|xRV100|xFIP|Pitching\+|Stuff\+|Location\+)'
    r')\b'
)


def check_hallucinated_metrics(report_text: str) -> list[str]:
    """Find metric-like terms in report that aren't in the known set.

    Scans the LLM output for patterns that look like advanced baseball
    metrics (xMetric, Acronym%, P+/S+/L+ family) and flags any not
    present in _KNOWN_METRICS.

    Args:
        report_text: The LLM-generated report text.

    Returns:
        List of potentially hallucinated metric names. Empty if clean.
    """
    found = set(_METRIC_PATTERN.findall(report_text))
    unknown = sorted(found - _KNOWN_METRICS)
    return unknown
