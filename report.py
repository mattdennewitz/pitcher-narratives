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
You are a purely objective baseball data analyst. Your job is to extract \
signal from noise in pitcher data. You have no editorial opinion — you \
identify facts and trends.

RULES:
- Output a structured bulleted list of the most important findings.
- Lead with the single biggest change or most notable trend — whether \
that is improvement or decline. Gains deserve the same weight as drops.
- For every metric, state the baseline and the delta. Do not state a \
number without context.
- Flag sample size concerns explicitly (e.g., "based on 30 pitches").
- Separate findings into clear categories: Fastball, Arsenal Mix, \
Execution, Platoon, Workload, TTO (if applicable).
- Do NOT write narrative prose. Do NOT editorialize. Just extract the \
analytical building blocks.
- Identify the 1-2 pitch characteristics that most explain the current \
performance level (the "why" behind the numbers). This could be a new \
weapon emerging, a mechanical improvement, OR a degradation.
- Call out anything that looks like a regression risk or unsustainable \
trend — but also flag breakout indicators (new pitch gaining traction, \
velocity gains, movement improvements that are backed by mechanical \
change)."""

_SP_SYNTH_GUIDANCE = """\
Focus areas for this starter:
- Velocity and P+ trajectory across the ramp-up window (gains AND drops)
- Which pitches are gaining or losing effectiveness by TTO pass
- Pitch mix evolution: is he leaning on something new or abandoning a pitch?
- Platoon-specific strengths and vulnerabilities by handedness
- Stamina signal: does velocity or P+ hold, improve, or cliff late?
- New weapons: any pitch showing a breakout P+ trend or usage surge?"""

_RP_SYNTH_GUIDANCE = """\
Focus areas for this reliever:
- Rest day impact on velocity and P+ (back-to-back vs rested — better or worse?)
- Primary weapon identification: what's the put-away pitch? Is it improving?
- How efficiently does he get through the order (pitch count per batter)?
- Platoon exposure: strengths and vulnerabilities by handedness
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
