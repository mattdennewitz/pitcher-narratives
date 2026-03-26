"""Report generation module using pydantic-ai Agent with Claude.

Configures a pydantic-ai Agent with scout-voice system prompt and
role-conditional guidance. Provides streaming output for CLI usage.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from context import PitcherContext

__all__ = ["generate_report_streaming", "check_hallucinated_metrics"]


# -- System prompt -------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a veteran MLB pitching analyst writing a scouting report. Your audience \
is a front office that values insight over stat sheets.

Write insight, not stat lines. Reference numbers to support observations, \
don't list them. If a delta is small, say so and move on.

Write in prose paragraphs. Use a data table only where it genuinely aids \
comprehension -- never as a substitute for analysis. Aim for 3-6 paragraphs \
depending on how much is genuinely noteworthy.

Never fabricate trends or claims not present in the provided context data. \
Every observation must be traceable to the pitcher data below."""


# -- Role-conditional guidance -------------------------------------------------

_SP_GUIDANCE = """\
For this starter, emphasize:
- Pitch mix depth and evolution across recent starts
- Stamina indicators: velocity arc, late-inning command, workload trends
- How secondary offerings play off the primary fastball
- Times-through-order preparation and adjustment patterns"""

_RP_GUIDANCE = """\
For this reliever, emphasize:
- Workload patterns: consecutive days pitched, rest-day impact on stuff
- Short-window weapon deployment: what is the put-away pitch?
- Leverage readiness and reliability signals
- How efficiently he attacks hitters in limited exposure"""


# -- Agent construction --------------------------------------------------------

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    output_type=str,
    system_prompt=_SYSTEM_PROMPT,
    model_settings=ModelSettings(max_tokens=4096),
    defer_model_check=True,
)


# -- User message builder ------------------------------------------------------

def _build_user_message(ctx: PitcherContext) -> str:
    """Build role-conditional user message from PitcherContext.

    Combines role-specific analysis guidance with the rendered prompt
    data from ctx.to_prompt().

    Args:
        ctx: Assembled pitcher context with role, arsenal, etc.

    Returns:
        Combined user message string for the Agent.
    """
    guidance = _SP_GUIDANCE if ctx.role == "SP" else _RP_GUIDANCE
    return f"## Analysis Focus\n{guidance}\n\n## Pitcher Data\n{ctx.to_prompt()}"


# -- Streaming generation ------------------------------------------------------

def generate_report_streaming(
    ctx: PitcherContext,
    *,
    _model_override=None,
) -> str:
    """Generate and stream a scouting report to stdout.

    Builds a role-conditional user message from the PitcherContext,
    sends it to the Agent via streaming, and prints tokens as they
    arrive. Returns the full report text.

    Args:
        ctx: Assembled pitcher context.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        The complete report text as a string.
    """
    user_message = _build_user_message(ctx)

    kwargs: dict = {"user_prompt": user_message}
    if _model_override is not None:
        kwargs["model"] = _model_override

    stream = agent.run_stream_sync(**kwargs)
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end='', flush=True)
        chunks.append(delta)
    print()  # Final newline
    return ''.join(chunks)


# -- Metric hallucination guard ------------------------------------------------

import re

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
})

_METRIC_PATTERN = re.compile(
    r'\b('
    # xMetric pattern (xBA, xWhiff, xRV100, etc.)
    r'x[A-Z][A-Za-z0-9]*'
    r'|'
    # Acronym+% pattern (CSW%, O-Swing%, Zone%)
    r'[A-Z][A-Za-z]*-?[A-Z]*%'
    r'|'
    # Pitching+ family (P+, S+2080, etc.)
    r'[PSL]\+(?:2080)?'
    r'|'
    # Other named advanced metrics (IVB, HB, wOBA, BABIP, ISO, pfx_x/z)
    r'(?:IVB|HB|pfx_[xz]|wOBA|BABIP|ISO|xRV100|Pitching\+|Stuff\+|Location\+)'
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
