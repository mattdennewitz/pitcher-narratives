"""Four-phase report generation pipeline.

Phase 1 (Synthesizer): Extracts signal from noise — structured bullet
points of key findings, deltas, and trends. No narrative.

Phase 2 (Editor): Weaves those facts into a pragmatic, two-paragraph
capsule with clear projection. Elite sabermetric analyst voice.

Phase 2.5 (Anchor Check + Revision Loop): Verifies the capsule is faithful
to the synthesis. If warnings are found, the editor revises silently and the
anchor re-checks -- up to MAX_REVISIONS passes. Only the final capsule
proceeds to downstream phases.

Phase 3 (Stuff Explainer): Traces each pitch's S+ grade to its physical
profile via stuff-only model predictions.

Phase 3+ (Executive Summary): 3 metrics-focused bullet points from the
synthesis.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, CachePoint
from pydantic_ai.settings import ThinkingEffort

from pitcher_narratives.anchor import (
    ANCHOR_PROMPT,
    AnchorResult,
    AnchorWarning,
    WarningCategory,
    build_anchor_message,
    build_revision_message,
)
from pitcher_narratives.config import (
    MAX_REVISIONS,
    MINI_PROVIDERS,
    PROVIDERS,
    THINKING_LEVELS,
    TOKEN_BUDGET_LARGE,
    TOKEN_BUDGET_MEDIUM,
    TOKEN_BUDGET_SMALL,
    agent_kwargs,
    cap_thinking,
    make_model_settings,
)
from pitcher_narratives.context import PitcherContext
from pitcher_narratives.engine import (
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)

__all__ = [
    "HallucinationReport",
    "ReportResult",
    "check_hallucinated_metrics",
    "generate_report_streaming",
    "print_prompts",
    "write_data_file",
]



# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: THE DATA SYNTHESIZER (THE SCOUT)
# ═══════════════════════════════════════════════════════════════════════

_SYNTHESIZER_PROMPT = """\
You are an elite MLB data analyst. Your job is to parse pitch-tracking \
data for a given pitcher over a recent window and extract the objective, \
mathematical signals from the noise. You are not writing a story. You \
are preparing a factual briefing document for a senior sabermetric writer.

INSTRUCTIONS:

0. Temporal Grounding: Read the "Temporal Context" section in the data \
first. The "prior-year workload relevance" level tells you how much \
weight to give last season's workload in your analysis. When it says \
LOW, do not build workload narratives from prior-season data. When it \
says HIGH, prior-year workload is plausible residual context but the \
two seasons are NOT a continuous timeline -- an offseason separates \
them. A pitcher with a handful of early-April appearances is not \
fatigued from this season's workload.

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
that was abandoned or newly introduced. Before attributing a usage shift \
to fatigue or mechanical causes, check the platoon data — a lineup \
heavy on one handedness can explain a mix change on its own.

4. Pinpoint Execution Changes: Identify which pitches are generating \
the highest CSW% and Chase%. Note if a pitch with a high P+ score is \
suffering from low Zone% (stuff without command). Note if a pitch with \
low P+ is succeeding on location alone. If pitch locations cluster on \
a specific edge or zone, note it — this may reflect a targeted plan \
against the opposing lineup rather than a mechanical pattern.

5. Extract Platoon Specifics: Document exactly how the pitch mix and \
P+ change against LHB versus RHB. Identify platoon-specific weapons \
and vulnerabilities.

6. Audit the Arsenal as a Portfolio: Do not evaluate each pitch in \
isolation. Cross-reference stuff quality (S+) with command (L+) and \
platoon splits to find the full picture:
- Breakout indicators: New pitches gaining traction, velocity gains \
backed by movement changes, P+ improvements that suggest real \
development — not just noise.
- Regression risks: Small sample caveats, unsustainable chase rates, \
high P+ with poor zone rates, or results that outpace stuff.
- Development opportunities: If a pitch has high S+ (>110) but low \
L+ (<80), do not dismiss it as a failure. Flag it as a pitch with \
the stuff but not the feel yet. Then check the platoon data — does \
the pitcher need this specific pitch to handle a handedness split? \
If so, note the connection: this is the pitch that would change the \
platoon picture if the command develops.

7. Evaluate Release Point Mechanics: Compare each pitch type's \
release position (horizontal, vertical) and extension against that \
pitcher's own season baseline — NOT league averages. Consistent \
release points across pitch types suggest clean mechanics and \
deception. Shifts in a single pitch type may indicate tinkering or \
development. Shifts across ALL pitch types suggest a mechanical \
change or fatigue. Flag the magnitude and direction of any \
meaningful delta.

8. Consider Intent: The pitcher is not operating in a vacuum. When \
you see usage shifts, location clustering, or pitch selection changes, \
consider whether the opponent's handedness mix or platoon profile \
explains the pattern before defaulting to fatigue or mechanical causes. \
Note when the data suggests a game plan rather than a trend. Use your \
judgement — flag plausible intent without overstating confidence.

9. Plausibility Filter — sanity-check your own findings before \
reporting them:
- Velocity outliers: If a velocity change exceeds 3 mph from the \
season baseline, consider whether pitch misclassification explains \
it before reporting it as a real gain or loss. Note the possibility.
- Intent before injury: When you see a change, first ask "is the \
pitcher trying something new?" before "is something wrong?" Check \
usage shifts, grip/shape changes, and opponent context before \
defaulting to physical explanations.
- Command vs targeting: A high L+ on one pitch does not mean the \
pitcher has command. If walks exceed 2 per 4 IP (roughly 12%+ of \
batters faced), frame high L+ as precise targeting or pitch \
placement on that specific offering — not overall command. He may \
be painting edges that hitters are not chasing, or locating his \
secondary stuff well while struggling to find the zone with his \
fastball. Report the L+ number, but contextualize it against the \
walk rate. Both facts belong together.

10. Absolute Objectivity: Do not use subjective adjectives. Do not \
project future performance. Report the math and the pitch \
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

## Opponent Context & Intent
[Bulleted facts: platoon composition of opposing lineups, usage or location \
patterns that appear opponent-driven rather than mechanical. Note when a \
shift looks like a game plan vs a trend. Skip this section if nothing \
stands out.]

## Key Signal
[Up to 3 bullets:
- The single most important improvement
- The single most important concern
- The development pitch: if there is a high-S+/low-L+ pitch that would \
solve a documented platoon weakness, name it here. If nothing fits, skip it.]"""

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
for front offices and data-driven fans. Your \
tone is pragmatic, cautious, and highly analytical. You do not use clichés.

INPUT: A structured briefing document from your data analyst containing \
objective facts about a pitcher's recent window, including Pitching+ \
scores, velocity changes, usage shifts, and execution metrics.

INSTRUCTIONS:

1. Find the Thread: Read the entire briefing, then decide what the \
story is. Maybe it is a new pitch reshaping the arsenal. Maybe it is \
a velocity trend that changes the projection. Maybe it is a platoon \
split that defines his role. Maybe it is a high-stuff pitch that \
lacks feel — the one thing standing between the current profile and \
a different tier. Lead with that thread — do not march through the \
briefing section by section. The synthesizer organizes data by \
category; your job is to reorganize it by narrative importance. \
Pay particular attention to the Key Signal section — if the \
synthesizer flagged a development pitch, consider whether that is \
the most interesting thread.

1.5. Temporal Grounding: The data includes a "Temporal Context" section \
with a prior-year relevance level. Follow it. Do not infer cumulative \
fatigue, late-season workload, or mechanical drift across season \
boundaries unless the relevance level supports it. Scale seasonal \
narrative to the actual sample: a handful of early-season appearances \
does not support a workload story.

2. Structure — The 2-3 Paragraph Capsule:

Paragraph 1 (The Setup): Tell the reader what is different about \
this pitcher right now. Lead with what happened — the concrete \
change — not with a theory about why it happened or what didn't \
change. Save the "why" for after the "what" is established.

Paragraph 2+ (The Verdict): Explain how the stuff is playing in \
practice. Weave in platoon splits where they matter to the story. \
Deliver a clear-eyed conclusion on the pitcher's current trajectory.

Use a third paragraph only when the Setup needs separation (e.g., \
fastball changes warrant one paragraph, arsenal evolution warrants \
another, before the Verdict).

3. Three Primary Metrics: Choose at most three metrics to carry your \
narrative. These are the numbers that tell the story — everything else \
stays in the briefing. When you cite a metric, always ground it against \
the MLB average (100 for P+/S+/L+) or the pitcher's own baseline. Use \
the Pitching+ triad (P+, S+, L+) when discussing pitch quality — S+ \
measures stuff (shape, movement, velocity), L+ measures pitch-level \
location quality. Important: L+ grades individual pitch placement, \
not overall command. A pitcher can have a high L+ on his slider while \
walking 18% of batters — that means the slider is landing in good \
spots, not that the pitcher has command. Always pair L+ with the \
walk rate to give the full picture.

4. Link Mechanics to Outcomes: If you mention a mechanical change \
(extension, release point, arm slot), you must immediately connect it \
to a tactical result — a specific pitch's zone rate, a movement change, \
a platoon split. No orphaned mechanical observations.

5. Diagnose, Do Not Just Describe: Connect the outcome to the physical \
input. If strikeout rates are down, explain that it is tied to a drop \
in vertical break or lost velocity. Link the "what" to the "why."

6. Consider Intent — Lightly: The pitcher does not operate in a \
vacuum. When the data shows usage shifts, consider whether the \
opposing lineup's handedness explains the pattern before defaulting \
to fatigue. But do not build a theory around every mix change. \
Sometimes a pitcher just threw more changeups. Mention intent as \
a possibility ("may reflect the lineup" or "could be a matchup \
adjustment") — never as a confident conclusion from one game.

7. Scale Confidence to Sample Size: Match the strength of your language \
to the amount of data. A three-start window gets "trending toward," \
"early signs of," or "worth watching." A full-season baseline can \
support firmer assessments. Do not declare what a pitcher "profiles as" \
from a handful of appearances.

8. Take a Stance: End with a clear assessment of where the pitcher \
sits and what to watch going forward. Be direct, not dramatic — and \
scale the conviction to the data (see #7).

9. Voice: Write the way an analyst talks to another analyst — plain, \
specific, conversational. Not the way a research paper reads.
- No clichés ("bulldog mentality," "pitches to contact," "electric stuff").
- No formulaic transitions ("Meanwhile," "However," "The stark gap \
between"). Just start the next thought.
- Vary sentence length. Let a short sentence land a point. Then \
explain in a longer one when the idea needs room.
- Use conversational scouting language: stuff, feel, finding a groove, \
keeping them off-balance, getting tagged, working the edges.
- Never use: "degradation," "binary," "physical characteristics," \
"extreme variance," "profiles as," "metrics are grim," \
"navigating a lineup," "elite," "dominant," "massive spike."
- Avoid "not just X, it's Y" or "it's a X — not just a Y" \
constructions — state what something IS.

10. Spot-Check Yourself: Before finishing, verify:
(a) You used no more than three primary metrics.
(b) Every mechanical observation connects to a tactical outcome.
(c) Your confidence matches the sample size.
(d) If you described any pitch as having great command, precision, \
or location, check the walk rate — if it is above 12% of batters \
faced, reframe as pitch-level placement, not overall command.
(e) Read the capsule as a reader, not as the writer. Does it lead \
with what happened, or with a theory about why? If you are spending \
more words explaining the mechanism behind a change than describing \
the change itself, rebalance. The reader needs to know what is \
different before they care about why. Do not open with what is NOT \
happening — start with what IS.

STRICT CONSTRAINTS:
- Rely entirely on the data provided in the input. Do not hallucinate \
metrics or trends.
- DIRECTIONAL CONSISTENCY: If the synthesis says a pitch is effective \
(S+ above 100, negative xRV100), do not flip the narrative to negative. \
If the synthesis says a pitch is weak, do not spin it positive. \
Preserve the direction of each assessment.
- If the synthesis shows a pitch has a meaningful strength (e.g., \
xWhiff ≥ 25%), you must reconcile that strength before labeling the \
pitch as poor or detrimental.
- Ignore traditional outcome stats like Wins and basic ERA unless \
provided as context. Base analysis on underlying metrics.
- No bullet points. No headers. No introductory fluff.
- Start immediately with the analysis. Your first sentence should be \
about the pitcher's stuff, not about "looking at the data."
- Be direct without being dismissive or alarmist."""



# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: THE STUFF EXPLAINER (TECHNICAL SUMMARY)
# ═══════════════════════════════════════════════════════════════════════

_STUFF_EXPLAINER_PROMPT = """\
You are a sabermetric analyst writing a brief technical summary that \
traces each pitch's Stuff+ (S+) grade back to its physical characteristics.

For each pitch type in the arsenal, write one sentence that connects \
velocity and movement shape (pfx_x/pfx_z) to the S+ grade via the \
model's stuff-only predictions (xWhiff_S, xSwing_S, xRV100_S).

The chain is: physical pitch → model prediction → S+ grade. Your job \
is to make that chain legible in plain language.

INTERPRETATION RULES (use the League Baselines provided):
- Compare every metric to the league baseline for that pitch type. \
Cite the delta from average when claiming a metric is unusual.
- If a pitch's velocity is within ±1.5 stddev of the league average, \
it is NORMAL — do not cite velocity as a primary reason for a poor S+.
- More vertical break on curveballs/sliders is typically POSITIVE. \
Check the sign convention before calling a deviation good or bad.
- DIRECTIONAL CONSISTENCY: S+ below 100 → xRV100_S positive (costly). \
S+ above 100 → xRV100_S negative (saves runs). Do not contradict this.
- If xWhiff_S ≥ 25%, reconcile this strength before calling the pitch \
weak.

Rules:
- Cover the 2-3 most notable pitches (best, worst, or most changed S+).
- Cite velocity, movement values, and S-variant probabilities by name.
- One short paragraph. No bullet lists.
- No location analysis — this is stuff only.
- No clichés, no hype, no hedging. Just the mechanism."""


# ═══════════════════════════════════════════════════════════════════════
# EXECUTIVE SUMMARY
# ═══════════════════════════════════════════════════════════════════════

_EXECUTIVE_SUMMARY_PROMPT = """\
You are a concise analyst producing a metrics-focused executive \
summary for a front office reader.

Given a structured data synthesis of a pitcher's recent window, produce \
exactly 3 bullet points. Each bullet states a finding and cites \
the metric that supports it.

RULES:
- Exactly 3 bullets. Each is ONE sentence.
- Every bullet MUST cite a specific number from the data \
(S+, P+, xRV100, xWhiff_S, velocity, usage%, etc.).
- State the finding directly. No labels like "Best outcome:" or \
"Key trend:" — just the analytical observation.
- DIRECTIONAL CONSISTENCY: S+ below 100 is below average. S+ above \
100 is above average. Negative xRV100 is good for the pitcher.
- Do not call normal metrics unusual. If a metric is within ±1.5 \
stddev of the league average, it is normal.
- Output ONLY the 3 bullet points. No headers, no intro, no outro.
- Format: each line starts with "- " followed by the insight."""


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2.5: THE ANCHOR CHECK (FACT-CHECKER)
# ═══════════════════════════════════════════════════════════════════════

class ReportResult(BaseModel):
    """Structured output from the multi-phase report pipeline."""

    narrative: str
    executive_summary: list[str] = []
    stuff_summary: str
    anchor_warnings: list[AnchorWarning]
    revision_count: int = 0
    """Number of revision passes (0 = passed first try)."""


# ═══════════════════════════════════════════════════════════════════════
# AGENT FACTORY
# ═══════════════════════════════════════════════════════════════════════

_StrAgents = tuple[Agent[None, str], Agent[None, str], Agent[None, str], Agent[None, str]]
_AgentSet = tuple[_StrAgents, Agent[None, AnchorResult]]
_agent_cache: dict[tuple[str, ThinkingEffort], _AgentSet] = {}


def _make_agents(
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
) -> _AgentSet:
    """Create (or return cached) pipeline agents with role-specific temperatures.

    Temperature split: synthesizer/stuff/summary=0.3 (data precision),
    editor=0.7 (prose quality), anchor=0.1 (fact-checking).
    """
    key = (provider, thinking)
    if key in _agent_cache:
        return _agent_cache[key]

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}, expected one of: {', '.join(PROVIDERS)}")
    model = PROVIDERS[provider]
    mini_model = MINI_PROVIDERS[provider]

    analyst_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)
    writer_settings = make_model_settings(provider, thinking, 0.7, max_tokens=TOKEN_BUDGET_LARGE)
    checker_settings = make_model_settings(provider, cap_thinking(thinking, "low"), 0.1, max_tokens=TOKEN_BUDGET_SMALL, mini=True)
    stuff_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE)
    summary_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_SMALL, mini=True)

    str_agents: _StrAgents = (
        Agent(mini_model, output_type=str, system_prompt=_SYNTHESIZER_PROMPT,
              model_settings=analyst_settings, defer_model_check=True),
        Agent(model, output_type=str, system_prompt=_EDITOR_PROMPT,
              model_settings=writer_settings, defer_model_check=True),
        Agent(model, output_type=str, system_prompt=_STUFF_EXPLAINER_PROMPT,
              model_settings=stuff_settings, defer_model_check=True),
        Agent(mini_model, output_type=str, system_prompt=_EXECUTIVE_SUMMARY_PROMPT,
              model_settings=summary_settings, defer_model_check=True),
    )
    anchor_agent = Agent(
        mini_model, output_type=AnchorResult, system_prompt=ANCHOR_PROMPT,
        model_settings=checker_settings, defer_model_check=True,
    )
    result: _AgentSet = (str_agents, anchor_agent)
    _agent_cache[key] = result
    return result


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════


_UserPrompt = list[str | CachePoint]
"""Type alias for user prompts with cache breakpoints."""


def _build_synthesizer_message(ctx: PitcherContext) -> _UserPrompt:
    """Build the Phase 1 user message with league baselines and role guidance.

    Includes league-average baselines so the synthesizer can ground claims
    about velocity, movement, and S-variant metrics against league norms.
    """
    guidance = _SP_SYNTH_GUIDANCE if ctx.role == "SP" else _RP_SYNTH_GUIDANCE
    pitch_types = [p.pitch_type for p in ctx.arsenal]
    baselines = render_league_baselines(pitch_types)
    return [
        f"## Role-Specific Focus\n{guidance}",
        CachePoint(),
        f"{baselines}\n\n## Pitcher Data\n{ctx.to_prompt()}",
    ]


def _build_editor_message(ctx: PitcherContext, synthesis: str) -> _UserPrompt:
    """Build the Phase 2 user message with cache breakpoint after synthesis."""
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Key Findings From Data Analysis\n{synthesis}",
        CachePoint(),
        "Write the two-paragraph scouting capsule now.",
    ]




def _build_stuff_message(ctx: PitcherContext, capsule: str) -> _UserPrompt:
    """Build the Phase 3 user message with pre-computed outlier annotations."""
    pitch_types = [p.pitch_type for p in ctx.arsenal]
    rendered_baselines = render_league_baselines(pitch_types)
    league_baselines = compute_league_baselines()
    baseline_lookup = {b.pitch_type: b for b in league_baselines}

    arsenal_lines: list[str] = []
    for p in ctx.arsenal:
        sp = f"{p.window_s_plus:.0f}" if p.window_s_plus is not None else "--"
        b = baseline_lookup.get(p.pitch_type)
        if b is not None:
            velo_d = p.window_velo - b.avg_velo
            velo_t = outlier_tag(p.window_velo, b.avg_velo, b.velo_std)
            pfx_x_d = p.window_pfx_x - b.avg_pfx_x
            pfx_x_t = outlier_tag(p.window_pfx_x, b.avg_pfx_x, b.pfx_x_std)
            pfx_z_d = p.window_pfx_z - b.avg_pfx_z
            pfx_z_t = outlier_tag(p.window_pfx_z, b.avg_pfx_z, b.pfx_z_std)
            arsenal_lines.append(
                f"- {p.pitch_name} ({p.pitch_type}):\n"
                f"    Velocity: {p.window_velo:.1f} mph ({velo_d:+.1f} vs avg) [{velo_t}]\n"
                f"    pfx_x: {p.window_pfx_x:.1f} in ({pfx_x_d:+.1f} vs avg) [{pfx_x_t}]\n"
                f"    pfx_z: {p.window_pfx_z:.1f} in ({pfx_z_d:+.1f} vs avg) [{pfx_z_t}]\n"
                f"    S+: {sp}"
            )
        else:
            arsenal_lines.append(
                f"- {p.pitch_name} ({p.pitch_type}): "
                f"{p.window_velo:.1f} mph, pfx_x {p.window_pfx_x:.1f} in, "
                f"pfx_z {p.window_pfx_z:.1f} in, S+ {sp}"
            )

    intermediates_lines: list[str] = []
    for im in ctx.intermediates:
        b = baseline_lookup.get(im.pitch_type)
        parts = format_s_variant_comparisons(b, im.xswing_s, im.xwhiff_s, im.xrv100_s)
        intermediates_lines.append(f"- {im.pitch_name} ({im.pitch_type}): {', '.join(parts)}")

    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"{rendered_baselines}\n\n"
        f"## Arsenal Physical Profile (with league comparison)\n"
        f"Each metric shows: value (delta from avg) [NORMAL/OUTLIER tag]\n"
        + "\n".join(arsenal_lines) + "\n\n"
        f"## Stuff-Only Model Predictions (S-variant, with league comparison)\n"
        + "\n".join(intermediates_lines) + "\n\n"
        f"## Scouting Capsule\n{capsule}",
        CachePoint(),
        "Write a brief technical summary explaining each notable pitch's S+ grade "
        "through its velocity, movement, and stuff-only model predictions. "
        "If a metric is tagged NORMAL, do not cite it as a driver of the grade. "
        "Every behavioral claim (e.g., 'hitters take it', 'generates swings') "
        "must cite the specific metric (xSwing_S, xWhiff_S) that supports it.",
    ]


def _render_user_prompt(parts: _UserPrompt) -> str:
    """Render a user prompt (with CachePoints) as readable text."""
    return "\n".join("  ── [cache breakpoint] ──" if isinstance(p, CachePoint) else p for p in parts)


def _build_all_phases(ctx: PitcherContext) -> list[tuple[str, str, _UserPrompt]]:
    """Build (label, system_prompt, user_prompt) for all phases."""
    synth_placeholder = "<synthesis output would go here>"
    capsule_placeholder = "<editor capsule would go here>"
    return [
        ("PHASE 1: SYNTHESIZER", _SYNTHESIZER_PROMPT, _build_synthesizer_message(ctx)),
        ("PHASE 2: EDITOR", _EDITOR_PROMPT, _build_editor_message(ctx, synth_placeholder)),
        (
            "PHASE 2.5: ANCHOR CHECK", ANCHOR_PROMPT,
            build_anchor_message(synth_placeholder, capsule_placeholder),
        ),
        ("PHASE 3: STUFF EXPLAINER", _STUFF_EXPLAINER_PROMPT, _build_stuff_message(ctx, capsule_placeholder)),
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
    """Generate a five-phase scouting report with anchor-driven revision loop.

    Phase 1 (Synthesizer): Extracts key findings as structured bullets.
    Phase 2 (Editor): Writes the first-draft capsule from synthesis (streamed).
    Phase 2.5 (Anchor Check + Revision Loop): Checks capsule against synthesis.
        If warnings are found, the editor revises silently (run_sync) and the
        anchor re-checks -- up to MAX_REVISIONS passes. Exits immediately when
        the anchor returns clean.
    Phase 3 (Stuff Explainer): Traces each pitch's S+ grade to its physical profile.
    Phase 3+ (Executive Summary): 3 metrics-focused bullet points.

    Phase 3 and summary receive the final capsule (post-revision if any), so
    they inherit the editor's plausibility filters and any anchor-driven
    corrections.

    Only Phase 2 first draft is streamed to stdout. Revision passes run silently.

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key ('openai' or 'claude').
        thinking: Thinking effort level.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        ReportResult with narrative, stuff_summary, and anchor_warnings.
    """
    (synthesizer, editor, stuff_explainer, summary_agent), anchor_checker = _make_agents(provider, thinking)

    # Phase 1: Silent synthesis
    synth_result = synthesizer.run_sync(**agent_kwargs(_build_synthesizer_message(ctx), _model_override))
    synthesis = synth_result.output

    # Phase 2: Streamed editorial
    stream = editor.run_stream_sync(**agent_kwargs(_build_editor_message(ctx, synthesis), _model_override))
    chunks: list[str] = []
    for delta in stream.stream_text(delta=True):
        print(delta, end="", flush=True)
        chunks.append(delta)
    print()  # Final newline

    capsule = "".join(chunks)

    # Phase 2.5: Anchor check + revision loop
    revision_count = 0
    for _ in range(MAX_REVISIONS):
        anchor_result = anchor_checker.run_sync(
            **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
        )
        anchor_check = anchor_result.output

        if anchor_check.is_clean:
            break

        # Revise silently (no streaming)
        revision_result = editor.run_sync(
            **agent_kwargs(build_revision_message(synthesis, capsule, anchor_check.warnings), _model_override)
        )
        capsule = revision_result.output
        revision_count += 1
    else:
        # Exhausted MAX_REVISIONS — final anchor check for surviving warnings
        anchor_result = anchor_checker.run_sync(
            **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
        )
        anchor_check = anchor_result.output

    # Phase 3 + Summary: Run after capsule is finalized
    stuff_result = stuff_explainer.run_sync(**agent_kwargs(_build_stuff_message(ctx, capsule), _model_override))
    summary_result = summary_agent.run_sync(**agent_kwargs(f"## Synthesis\n{synthesis}", _model_override))

    # Parse bullet lines from raw summary output
    summary_bullets = [
        line.lstrip("- ").strip()
        for line in summary_result.output.strip().splitlines()
        if line.strip().startswith("- ")
    ]

    return ReportResult(
        narrative=capsule,
        executive_summary=summary_bullets,
        stuff_summary=stuff_result.output,
        anchor_warnings=anchor_check.warnings,
        revision_count=revision_count,
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
