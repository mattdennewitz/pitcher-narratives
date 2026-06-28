"""Multi-agent specialist→auditor→writer report pipeline (v1.7 prototype).

Architecture:
  Phase 1: 5 specialist agents run in parallel, each producing a focused
  micro-analysis with league baselines (including stddev and S-variant
  benchmarks) injected for grounding:
    - Stuff Explainer: velocity/movement → S+ grades via S-variant predictions
    - Location Analyst: P vs S divergence, zone/chase rates, location impact
    - Run Value Decomposer: 13-outcome attribution, dominant value drivers
    - Trend Spotter: window vs season deltas in velocity, movement, usage, grades
    - Game Shape Analyst: TTO degradation, velocity arc, within-game mix shifts

  Phase 1.5: Per-specialist audit + revision loop. Each specialist's output
  is audited independently (5 audits run in parallel) against the raw data
  and league baselines. Flagged specialists are re-run with their original
  input + audit corrections to produce clean output. The writer never sees
  flawed prose — only corrected versions.

  Phase 1.75: Signal extractor reads clean specialist outputs and identifies
  cross-specialist patterns (top improvement, top concern, development pitch,
  specialist tensions, arsenal dependency, connected changes, platoon
  vulnerability, sample size caveats). These key signals feed both the
  writer (as narrative priorities) and the anchor checker (as validation
  targets).

  Phase 2: Writer composes a unified capsule from clean specialist outputs
  + key signals. Executive summary agent runs concurrently with writer.

  Phase 2.5: Anchor check + revision loop. Primary signals are enforced
  (MISSED_SIGNAL), secondary signals are advisory (UNDERWEIGHTED).

Anti-hallucination guardrails:
  - Specialists receive pre-computed NORMAL/OUTLIER tags on every metric.
  - Per-specialist audit loop catches and corrects errors before synthesis.
  - Directional consistency enforced: S+ below 100 → xRV100 positive, etc.
  - Temperature split: specialists=0.3, writer=0.7, auditor/anchor=0.1.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, NamedTuple

from pydantic import BaseModel
from pydantic_ai import Agent, CachePoint
from pydantic_ai.settings import ModelSettings, ThinkingEffort

from pitcher_narratives.agent_skills import skill_toolset
from pitcher_narratives.anchor import (
    ANCHOR_PROMPT,
    AnchorResult,
    AnchorWarning,
    build_anchor_message,
    build_revision_message,
)
from pitcher_narratives.config import (
    MAX_REVISIONS,
    MINI_PROVIDERS,
    PROVIDERS,
    TOKEN_BUDGET_LARGE,
    TOKEN_BUDGET_MEDIUM,
    TOKEN_BUDGET_SMALL,
    agent_kwargs,
    cap_thinking,
    make_model_settings,
)
from pitcher_narratives.costs import UsageTracker, model_label
from pitcher_narratives.context import PitcherContext
from pitcher_narratives.engine import (
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
from pitcher_narratives.personas import (
    BRIEF,
    DEFAULT_PERSONA,
    Persona,
    build_system_prompt,
    build_writer_system_prompt,
    get_persona,
)
from pitcher_narratives.prompt_builder import (
    render_appearances_section,
    render_arsenal_section,
    render_fastball_section,
    render_hard_hit_section,
    render_release_point_section,
    render_role_section,
    render_tto_section,
    render_yoy_section,
)
from pitcher_narratives.shape import render_pitch_shape
from pitcher_narratives.models import (
    AnalyzedContext,
    AuditFlag,
    AuditResult,
    SpecialistOutputs,
)
from pitcher_narratives.signals import (
    SIGNAL_EXTRACTOR_PROMPT,
    KeySignals,
    render_key_signals,
)

__all__ = [
    "AnalyzedContext",
    "AuditFlag", "AuditResult", "ExecutiveSummary", "HallucinationReport",
    "KeySignals", "PipelineAgents", "PipelineResult",
    "UserPrompt", "audit_and_revise_specialists", "build_summary_input",
    "build_writer_input", "check_explainer_present", "check_hallucinated_metrics",
    "generate_pipeline_streaming",
    "make_pipeline_agents", "run_analysis_spine", "run_specialists",
    "write_pipeline_data_file",
]

log = logging.getLogger("pitcher_narratives.pipeline")

UserPrompt = list[str | CachePoint]
"""Type alias for user prompts with cache breakpoints."""


def _flatten_prompt(parts: UserPrompt) -> str:
    """Join text parts of a user prompt, stripping CachePoints."""
    return "\n".join(p for p in parts if isinstance(p, str))


def _render_user_prompt(parts: UserPrompt) -> str:
    """Render a user prompt (with CachePoints) as readable text for tracing."""
    return "\n".join(
        "  -- [cache breakpoint] --" if isinstance(p, CachePoint) else p
        for p in parts
    )


# ═══════════════════════════════════════════════════════════════════════
# SPECIALIST PROMPTS
# ═══════════════════════════════════════════════════════════════════════

_STUFF_SPECIALIST_PROMPT = """\
You are a pitch physics analyst. Your job is to explain each pitch's \
raw stuff quality by tracing from physical characteristics to the \
model's stuff-only grade.

HOW TO READ THE DATA:
The Arsenal Physical Profile has pre-computed league comparisons for \
every metric. Each metric shows:
  value (delta from league avg) [NORMAL or OUTLIER tag with z-score]
The NORMAL/OUTLIER tags are computed from actual league data. Trust \
them. If a metric says [NORMAL], treat it as unremarkable for that \
pitch type — do not describe it as slow, weak, or unusual.

INTERPRETATION RULES (these are absolute — override any intuition):
- RESPECT THE TAGS: If a metric is tagged [NORMAL], you MUST NOT cite \
it as a primary driver of a poor (or good) grade. Many factors beyond \
velocity drive S+ — movement shape, movement *interaction* (horizontal \
× vertical), spin characteristics, and how the pitch tunnels off the \
fastball. When velocity is NORMAL, look to these other factors to \
explain the grade.
- SECONDARY PITCH CONTEXT: Offspeed and breaking pitches (curveballs, \
sliders, changeups, splitters) derive value from deception, movement \
shape, and tunneling — NOT primarily from velocity. An 81 mph knuckle \
curve and an 84 mph knuckle curve can have wildly different S+ grades \
based on movement profile alone. Do not default to velocity explanations \
for secondary pitches unless it is a genuine [OUTLIER].
- MOVEMENT CONTEXT: More vertical break (more negative pfx_z) on a \
curveball/slider is typically a POSITIVE attribute. More horizontal \
movement on a sweeper is positive. Check the S-variant league \
comparisons: if xWhiff_S is below league avg, the movement shape is \
not generating enough deception regardless of velocity.
- DIRECTIONAL CONSISTENCY: S+ below 100 means the pitch grades below \
average and xRV100_S should be positive (costly to the pitcher). S+ \
above 100 means above average and xRV100_S should be negative (saves \
runs). If these signs don't align in the data, flag the discrepancy \
rather than forcing a narrative.
- xWHIFF RECONCILIATION: If xWhiff_S ≥ 25%, this is a meaningful whiff \
rate. You MUST reconcile this success before labeling a pitch as \
"detrimental" or "poor." A pitch that generates whiffs has value even \
if other metrics are weak.
- CITATION REQUIREMENT: Every behavioral claim MUST cite the specific \
metric that supports it. Examples of behavioral claims that need data:
  × "hitters can identify the shape easily" → MUST cite xSwing_S
  × "practically an automatic take" → MUST cite xSwing_S
  × "generates swing-and-miss" → MUST cite xWhiff_S
  × "hittable" → MUST cite xRV100_S or batted ball data
  If you cannot cite a specific metric from the data provided, do not \
  make the claim.
- NO HALLUCINATED CAUSATION: Do not invent reasons for a S+ grade that \
are not supported by the data provided. If the physical profile looks \
average but S+ is extreme, say so honestly rather than fabricating an \
explanation. "The model sees something in the movement interaction \
that the raw averages don't capture" is more honest than inventing \
a story about velocity.
- ARM SLOT CONTEXT: When a "Pitch Shape vs Arm Slot" section is \
present, it compares each pitch's movement to the league expectation \
for the same arm angle, standardized by how much pitchers actually \
vary at that slot. These tags are pre-computed -- trust them. A \
fastball tagged DEAD ZONE has the shape hitters' eyes predict from the \
release slot. This is a RISK FACTOR, not a verdict: a dead-zone \
fastball can still grade well on velocity or command, so do NOT assume \
the tag means the pitch is hittable. Note the slot context where it \
genuinely informs the grade -- a dead-zone shape is one plausible \
reason a fastball whiffs less than its velocity suggests ("given his \
arm angle, the fastball's movement profile is dead zone") -- but only \
when the data supports it; never invent a causal story from the tag \
alone. Movement flagged well above or below slot expectation is \
deception the raw averages hide (ride that beats slot expectation \
plays up; extra sink or run from a high slot surprises hitters); \
surface those when present.

OUTPUT FORMAT:
- For each pitch type, explain why the S+ grade is what it is by \
connecting velocity and movement shape to the S-variant predictions.
- The chain is: physical pitch → model prediction → S+ grade.
- Cover every pitch, prioritizing the most interesting (extreme S+, \
surprising grades given the physical profile).
- Use the pre-computed deltas and tags from the data. Do not recompute. \
Example: "81.3 mph (-1.6 vs league avg, NORMAL for knuckle curves)."
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

INTERPRETATION RULES:
- Compare zone% and chase% against the league baselines provided. \
Only flag a rate as high/low if it deviates meaningfully from the \
league average for that pitch type.
- DIRECTIONAL CONSISTENCY: L+ above 0 means location helps. The \
P-variant xRV100 should be more negative (better) than S-variant. \
If the data contradicts this, note the discrepancy honestly.
- Cite deltas from league average for zone% and chase% when claiming \
a rate is unusual.
- Do not invent location patterns not supported by the data.

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

INTERPRETATION RULES:
- DIRECTIONAL CONSISTENCY: If total xRV100 is negative (good), the \
pitch saves runs overall. Do not describe a pitch with negative xRV100 \
as "detrimental" or "costly." If total xRV100 is positive (bad), do \
not describe it as "effective."
- When connecting outcomes to physical characteristics, check those \
claims against the league baselines. Do not say "hittable velocity" \
if the velocity is normal for that pitch type.
- Only cite the data provided. Do not invent outcome contributions.

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
- Hard-hit rate shifts

Rules:
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section. \
Respect the prior-year relevance level. Do not frame window-vs-season \
deltas as long-term trends when the current season has few appearances. \
Do not connect prior-season workload to current-season patterns as \
cause-and-effect.
- Lead with the single most important change.
- Separate real trends from noise: flag sample size concerns, note \
when a delta is within the "steady" threshold.
- Identify if changes are connected (e.g., velo drop + S+ drop + \
more hard contact = likely related).
- One focused paragraph covering the key trends. Skip what's steady.
- No projection or prediction — just what changed and by how much.
- Do NOT analyze TTO patterns, velocity arcs, or within-game \
progression — a separate specialist handles that.
- Plain prose, no bullet lists."""

_GAME_SHAPE_SPECIALIST_PROMPT = """\
You are a game shape analyst. Your job is to describe how the pitcher's \
effectiveness and approach change WITHIN a game — from first pitch to last.

Look at:
- TTO splits: how do velocity, P+, and pitch mix change by pass?
- Velocity arc: does velocity hold, build, or drop within the outing?
- Mix shifts by pass: does the pitcher abandon or introduce pitches \
as the game progresses?
- Platoon-specific TTO patterns: does the mix shift differently \
against LHB vs RHB in later passes?
- Workload context: pitch counts, rest days, consecutive days pitched.

Rules:
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section. \
Respect the prior-year relevance level. Do not attribute within-game \
patterns to cumulative seasonal fatigue if the current season is young. \
A pitcher with 5 early-April appearances is not showing late-season wear.
- Lead with the most notable within-game pattern.
- Connect mix shifts to effectiveness: if he ramps the sinker in \
pass 2, does that help or hurt?
- Flag stamina signals: velo cliff, S+ drop, command loss in later \
passes.
- One focused paragraph. Skip what's unremarkable.
- Do NOT analyze window-vs-season trends — a separate specialist \
handles that.
- Plain prose, no bullet lists."""


# Role-specific guidance injected into the Game Shape specialist's USER
# message based on `ctx.role`. These blocks reinstate the SP/RP focus
# that the old single-agent synthesizer had before v1.9 consolidation —
# the multi-agent architecture implicitly covers these concerns, but
# explicit role guidance keeps reliever reports from drifting into
# starter-shaped analysis (and vice versa).

_SP_GAME_SHAPE_GUIDANCE = """\
## Role Focus: STARTER

Additional focus for this starter:
- TTO pass breakdown: which pitches gain or lose effectiveness by pass?
- Pitch mix evolution across passes: is he leaning on something new late?
- Platoon-specific TTO patterns (what does he throw vs LHB in pass 3?)
- Stamina trajectory: does velocity, S+, or L+ hold, improve, or cliff?"""

_RP_GAME_SHAPE_GUIDANCE = """\
## Role Focus: RELIEVER

Additional focus for this reliever:
- Rest day impact on velocity, S+, and L+ (back-to-back vs rested — better or worse?)
- Primary weapon identification: what is the put-away pitch? Cite its P+/S+/L+ triad
- Pitch count efficiency: how many pitches per batter faced?
- Platoon-specific strengths and vulnerabilities by handedness"""


# ═══════════════════════════════════════════════════════════════════════
# DATA AUDITOR PROMPT
# ═══════════════════════════════════════════════════════════════════════

_DATA_AUDITOR_PROMPT = """\
You are a data auditor for a baseball analytics pipeline. You receive \
ONE specialist's analysis alongside the raw data it was based on. \
Your job is to flag every instance where the prose contradicts, \
misrepresents, or hallucinates beyond the data.

CHECK FOR THESE SPECIFIC PROBLEMS:

1. METRIC_CONTRADICTION: The prose characterizes a metric as high/low, \
good/bad, but the data shows it is within the normal range \
(±1.5 stddev) or tagged [NORMAL]. Example: calling 81 mph "slow" \
for a curveball when the data tags it [NORMAL (z=-0.4)].

2. DIRECTION_ERROR: The prose says a metric is bad but the data shows \
it is good (or vice versa). Example: calling more vertical break on \
a curveball "detrimental" when more depth is typically positive.

3. SIGN_INCONSISTENCY: S+ and xRV100_S point in opposite directions \
in the prose. If S+ < 100, xRV100_S should be positive (costs runs). \
If S+ > 100, xRV100_S should be negative (saves runs).

4. UNRECONCILED_STRENGTH: The prose labels a pitch as "detrimental" or \
"poor" without acknowledging a meaningful strength in the data. \
Example: xWhiff_S ≥ 25% being ignored when calling a pitch poor.

5. HALLUCINATED_CAUSATION: The prose invents a causal mechanism not \
supported by the data. Also flag when a [NORMAL]-tagged metric is \
cited as a primary driver of a grade.

6. FABRICATED_DATA: The prose cites a specific number that does not \
appear in the input data.

7. UNCITED_BEHAVIORAL_CLAIM: A claim about hitter behavior (e.g., \
"hitters take it," "automatic take") without citing the specific \
metric (xSwing_S, xWhiff_S, CSW%) that supports it.

For each problem found, report:
- The specific claim that is wrong
- What the data actually shows
- A suggested correction

If everything checks out, return an empty list."""


# AuditFlag and AuditResult are defined in models.py and imported above.

# ═══════════════════════════════════════════════════════════════════════
# EXECUTIVE SUMMARY PROMPT
# ═══════════════════════════════════════════════════════════════════════

_EXECUTIVE_SUMMARY_PROMPT = """\
You are a concise analyst producing a metrics-focused executive summary for \
a front office reader.

You are given a finished scouting report, followed by the clean specialist \
analyses it was built from (reference only). Produce exactly 3 bullet points \
that summarize the report. Each bullet states a finding the report makes and \
cites the metric that supports it.

RULES:
- Exactly 3 bullets. Each is ONE sentence.
- Summarize ONLY findings the report makes. Do not introduce a finding from \
the attached analyses that the report did not state.
- Every bullet MUST cite a specific number (S+, P+, xRV100, xWhiff_S, \
velocity, usage%, etc.), AS THE REPORT STATES IT. If the report makes a \
finding qualitatively without a figure, you may recover the supporting number \
from the attached analyses — but never change a number the report gives, and \
never flag a discrepancy.
- State the finding directly. No labels like "Best outcome:" or "Key trend:" \
— just the analytical observation.
- DIRECTIONAL CONSISTENCY: S+ below 100 is below average. S+ above 100 is \
above average. Negative xRV100 is good for the pitcher.
- Do not call normal metrics unusual. If a metric is within ±1.5 stddev of \
the league average, it is normal.
- Output ONLY the 3 bullet points. No headers, no intro, no outro.
- Format: each line starts with "- " followed by the insight."""


class ExecutiveSummary(BaseModel):
    """Structured executive summary bullet points."""

    bullets: list[str]



# render_league_baselines and outlier_tag are imported from engine.py


# ═══════════════════════════════════════════════════════════════════════
# DATA BUILDERS
# ═══════════════════════════════════════════════════════════════════════

def _pitch_types(ctx: PitcherContext) -> list[str]:
    """Extract pitch type codes from the arsenal."""
    return [p.pitch_type for p in ctx.arsenal]


def _build_stuff_input(ctx: PitcherContext) -> UserPrompt:
    """Build input for the stuff specialist with pre-computed outlier annotations.

    Each metric is annotated with its delta from league average and an
    explicit NORMAL/OUTLIER tag so the LLM does not need to compute
    z-scores itself.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix (cacheable across same-pitcher reruns) and the data section.
    """
    baselines = compute_league_baselines()
    baseline_lookup = {b.pitch_type: b for b in baselines}

    header_lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    header_lines.append(render_league_baselines(_pitch_types(ctx)))
    header_lines.append("")

    data_lines: list[str] = []
    data_lines.append("## Arsenal Physical Profile (with league comparison)")
    data_lines.append("Each metric shows: value (delta from league avg) [NORMAL/OUTLIER tag]")
    data_lines.append("")
    for p in ctx.arsenal:
        sp = f"{p.window_s_plus:.0f}" if p.window_s_plus is not None else "--"
        b = baseline_lookup.get(p.pitch_type)
        if b is not None:
            velo_delta = p.window_velo - b.avg_velo
            velo_tag = outlier_tag(p.window_velo, b.avg_velo, b.velo_std)
            pfx_x_delta = p.window_pfx_x - b.avg_pfx_x
            pfx_x_tag = outlier_tag(p.window_pfx_x, b.avg_pfx_x, b.pfx_x_std)
            pfx_z_delta = p.window_pfx_z - b.avg_pfx_z
            pfx_z_tag = outlier_tag(p.window_pfx_z, b.avg_pfx_z, b.pfx_z_std)
            data_lines.append(
                f"- {p.pitch_name} ({p.pitch_type}):\n"
                f"    Velocity: {p.window_velo:.1f} mph ({velo_delta:+.1f} vs league avg) [{velo_tag}]\n"
                f"    pfx_x: {p.window_pfx_x:.1f} in ({pfx_x_delta:+.1f} vs avg) [{pfx_x_tag}]\n"
                f"    pfx_z: {p.window_pfx_z:.1f} in ({pfx_z_delta:+.1f} vs avg) [{pfx_z_tag}]\n"
                f"    S+: {sp} (season {p.season_s_plus:.0f}, {p.s_plus_delta})"
            )
        else:
            data_lines.append(
                f"- {p.pitch_name} ({p.pitch_type}): "
                f"{p.window_velo:.1f} mph ({p.velo_delta}), "
                f"pfx_x {p.window_pfx_x:.1f} in ({p.pfx_x_delta}), "
                f"pfx_z {p.window_pfx_z:.1f} in ({p.pfx_z_delta}), "
                f"S+ {sp} (season {p.season_s_plus:.0f}, {p.s_plus_delta})"
            )

    data_lines.append("\n## Stuff-Only Model Predictions (S-variant, with league comparison)")
    for im in ctx.intermediates:
        b = baseline_lookup.get(im.pitch_type)
        comparisons = format_s_variant_comparisons(b, im.xswing_s, im.xwhiff_s, im.xrv100_s)
        data_lines.append(f"- {im.pitch_name} ({im.pitch_type}): {', '.join(comparisons)}")

    # Arm-slot shape context (movement vs slot expectation, dead zone tags)
    shape_section = render_pitch_shape(ctx.pitch_shape)
    if shape_section:
        data_lines.append("\n" + shape_section)

    # Cross-season context (when available)
    if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
        data_lines.append("\n## Year-over-Year Context")
        css = ctx.cross_season_summary
        if css is not None:
            data_lines.append(f"Comparing {css.current_season} vs {css.prior_season}:")
            data_lines.append(f"- Velocity YoY: {css.velo_delta}")
            data_lines.append(f"- P+ YoY: {css.p_plus_delta}")
            data_lines.append(f"- S+ YoY: {css.s_plus_delta}")
        at = ctx.arsenal_trend
        if at is not None:
            if at.added:
                added = ", ".join(p.pitch_name for p in at.added)
                data_lines.append(f"- Added pitches: {added}")
            if at.dropped:
                dropped = ", ".join(p.pitch_name for p in at.dropped)
                data_lines.append(f"- Dropped pitches: {dropped}")
            for pt in at.continued[:4]:
                parts = []
                if pt.usage_delta and "Steady" not in pt.usage_delta:
                    parts.append(f"usage {pt.usage_delta}")
                if pt.velo_delta and "Steady" not in pt.velo_delta:
                    parts.append(f"velo {pt.velo_delta}")
                if pt.s_plus_delta and "Steady" not in pt.s_plus_delta:
                    parts.append(f"S+ {pt.s_plus_delta}")
                if parts:
                    data_lines.append(f"- {pt.pitch_name}: {', '.join(parts)}")

    return ["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]


def _build_location_input(ctx: PitcherContext) -> UserPrompt:
    """Build input for the location specialist from intermediates + execution.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix and the location data section.
    """
    header_lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    header_lines.append(render_league_baselines(_pitch_types(ctx)))
    header_lines.append("")

    data_lines: list[str] = []
    data_lines.append("## P vs S Location Impact")
    for im in ctx.intermediates:
        def _d(p: float | None, s: float | None) -> str:
            if p is not None and s is not None:
                return f"{(p - s) * 100:+.1f}pp"
            return "--"
        def _drv(p: float | None, s: float | None) -> str:
            if p is not None and s is not None:
                return f"{(p - s):+.2f}"
            return "--"
        data_lines.append(
            f"- {im.pitch_name} ({im.pitch_type}): "
            f"xSwing P {im.xswing_p * 100:.1f}% S {im.xswing_s * 100:.1f}% (delta {_d(im.xswing_p, im.xswing_s)}), "
            f"xWhiff P {im.xwhiff_p * 100:.1f}% S {im.xwhiff_s * 100:.1f}% (delta {_d(im.xwhiff_p, im.xwhiff_s)}), "
            f"xRV100 P {im.xrv100_p:.2f} S {im.xrv100_s:.2f} (delta {_drv(im.xrv100_p, im.xrv100_s)})"
            if im.xswing_p is not None else f"- {im.pitch_name} ({im.pitch_type}): no data"
        )
    data_lines.append("\n## Execution Metrics")
    for e in ctx.execution:
        data_lines.append(
            f"- {e.pitch_name} ({e.pitch_type}): "
            f"Zone% {e.zone_rate:.1f}, Chase% {e.chase_rate:.1f}, CSW% {e.csw_pct:.1f}"
        )
    data_lines.append("\n## Plus Scores (P+ vs S+ vs L+)")
    for p in ctx.arsenal:
        wp = f"{p.window_p_plus:.0f}" if p.window_p_plus is not None else "--"
        ws = f"{p.window_s_plus:.0f}" if p.window_s_plus is not None else "--"
        wl = f"{p.window_l_plus:.0f}" if p.window_l_plus is not None else "--"
        data_lines.append(f"- {p.pitch_name} ({p.pitch_type}): P+ {wp}, S+ {ws}, L+ {wl}")
    return ["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]


def _build_runvalue_input(ctx: PitcherContext) -> UserPrompt:
    """Build input for the run value specialist from attributions.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix and the attribution data section.
    """
    header_lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    header_lines.append(render_league_baselines(_pitch_types(ctx)))
    header_lines.append("")

    data_lines: list[str] = []
    data_lines.append("## Component Attribution (xRV100 Decomposition)")
    for attr in ctx.attributions:
        data_lines.append(f"\n### {attr.pitch_name} ({attr.pitch_type}) — total xRV100: {attr.total_xrv100:.2f}")
        for oc in attr.contributions:
            share = (
                f"{(oc.contribution / attr.total_xrv100 * 100):+.1f}%"
                if attr.total_xrv100 != 0
                else f"{0:.1f}%"
            )
            data_lines.append(f"  {oc.outcome}: {oc.contribution:+.3f} ({share})")
    return ["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]


def _build_trend_input(ctx: PitcherContext) -> UserPrompt:
    """Build input for the trend specialist -- arsenal deltas, release point, hard-hit.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix and the trend data sections.
    """
    baselines = render_league_baselines(_pitch_types(ctx))
    prefix_sections = [
        f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
        baselines,
    ]
    data_sections = [
        render_fastball_section(ctx),
        render_arsenal_section(ctx),
        render_release_point_section(ctx),
        render_hard_hit_section(ctx),
    ]
    # Cross-season context (when available) — trends specialist gets full YoY section
    if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
        data_sections.append(render_yoy_section(ctx))
    return [
        "\n\n".join(s for s in prefix_sections if s),
        CachePoint(),
        "\n\n".join(s for s in data_sections if s),
    ]


def _role_game_shape_guidance(role: str) -> str | None:
    """Return role-specific game shape guidance, or None if role is unknown.

    Starter and reliever reports need different emphasis — starters care
    about TTO progression and stamina, relievers care about rest-day
    impact and put-away pitches. This guidance is injected into the Game
    Shape specialist's user message so it biases the analysis toward
    role-appropriate signals without hard-coding role branches into the
    system prompt.
    """
    normalized = role.upper() if role else ""
    if normalized in ("SP", "STARTER"):
        return _SP_GAME_SHAPE_GUIDANCE
    if normalized in ("RP", "RELIEVER"):
        return _RP_GAME_SHAPE_GUIDANCE
    return None


def _build_game_shape_input(ctx: PitcherContext) -> UserPrompt:
    """Build input for the game shape specialist -- TTO, velocity arc, workload.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix and the game shape data sections. Role-specific guidance (SP or
    RP) is injected into the prefix so it sits above the cache breakpoint
    and biases the whole specialist analysis.
    """
    baselines = render_league_baselines(_pitch_types(ctx))
    prefix_sections: list[str] = [
        f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
    ]
    role_guidance = _role_game_shape_guidance(ctx.role)
    if role_guidance is not None:
        prefix_sections.append(role_guidance)
    prefix_sections.append(baselines)

    data_sections = [
        render_tto_section(ctx),
        render_fastball_section(ctx),
        render_appearances_section(ctx),
        render_role_section(ctx),
    ]
    # Cross-season context (when available) — game shape gets workload + usage shifts
    css = ctx.cross_season_summary
    at = ctx.arsenal_trend
    if css is not None or at is not None:
        yoy_lines = ["## Year-over-Year Context"]
        if css is not None:
            # Workload comes from TemporalContext (single source of truth)
            t = ctx.temporal
            yoy_lines.append(
                f"- Workload: {t.current_season_appearances} app / {t.current_season_ip} IP "
                f"(prior {t.prior_season}: {t.prior_season_appearances} app / {t.prior_season_ip} IP)"
            )
        if at is not None:
            for pt in at.continued[:4]:
                parts = []
                if pt.usage_delta and "Steady" not in pt.usage_delta:
                    parts.append(f"usage {pt.usage_delta}")
                if pt.velo_delta and "Steady" not in pt.velo_delta:
                    parts.append(f"velo {pt.velo_delta}")
                if parts:
                    yoy_lines.append(f"- {pt.pitch_name}: {', '.join(parts)}")
            if at.added:
                yoy_lines.append(
                    f"- Added: {', '.join(p.pitch_name for p in at.added)}"
                )
            if at.dropped:
                yoy_lines.append(
                    f"- Dropped: {', '.join(p.pitch_name for p in at.dropped)}"
                )
        data_sections.append("\n".join(yoy_lines))
    return [
        "\n\n".join(s for s in prefix_sections if s),
        CachePoint(),
        "\n\n".join(s for s in data_sections if s),
    ]


def build_writer_input(
    ctx: PitcherContext,
    stuff: str,
    location: str,
    runvalue: str,
    trends: str,
    game_shape: str,
    *,
    key_signals: KeySignals | None = None,
) -> str:
    """Compose all specialist outputs into writer input.

    Specialist outputs should already be clean (post-audit revision),
    so no audit flags are needed here. If key_signals is provided,
    a Key Signals section is prepended before the specialist analyses.
    """
    parts = [f"## Pitcher: {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    if key_signals is not None:
        parts.append(render_key_signals(key_signals) + "\n")
    parts.extend([
        f"## Specialist Analysis 1: Stuff\n{stuff}\n",
        f"## Specialist Analysis 2: Location\n{location}\n",
        f"## Specialist Analysis 3: Run Value\n{runvalue}\n",
        f"## Specialist Analysis 4: Trends\n{trends}\n",
        f"## Specialist Analysis 5: Game Shape\n{game_shape}",
    ])
    return "\n\n".join(parts)


def build_summary_input(capsule: str, writer_input: str) -> str:
    """Frame the finished report as the summary subject, with the clean
    specialist analyses attached as recover-only grounding.

    The capsule is the source of truth: summaries cite its numbers as
    written. ``writer_input`` (Key Signals + clean specialist analyses) is
    reference ONLY — to recover a metric the report stated qualitatively,
    never to correct the report's numbers and never to add findings.
    """
    return (
        "## FINISHED REPORT (summarize THIS; cite its numbers exactly as written)\n"
        f"{capsule}\n\n"
        "## SOURCE ANALYSES (the clean specialist analyses the report was built "
        "from — reference ONLY to recover a metric the report stated "
        "qualitatively; do NOT correct the report's numbers and do NOT add "
        "findings absent from the report)\n"
        f"{writer_input}"
    )


def _build_specialist_audit_input(ground_truth: str, specialist_output: str) -> str:
    """Build auditor input for a single specialist."""
    return (
        f"## GROUND TRUTH DATA\n{ground_truth}\n\n"
        f"## SPECIALIST OUTPUT TO AUDIT\n{specialist_output}"
    )


def _build_specialist_revision_input(
    original_input: str,
    specialist_output: str,
    flags: list[AuditFlag],
) -> str:
    """Build a revision prompt for a specialist to fix its own flagged issues."""
    formatted = "\n".join(
        f"- [{f.category}] \"{f.claim}\" → Data shows: {f.data_shows}. "
        f"Fix: {f.suggested_fix}"
        for f in flags
    )
    return (
        f"## Original Data\n{original_input}\n\n"
        f"## Your Previous Analysis\n{specialist_output}\n\n"
        f"## Issues Found by Data Auditor\n{formatted}\n\n"
        "Revise your analysis to correct ONLY the flagged issues. "
        "Keep all unflagged material unchanged. Preserve the same "
        "format and length."
    )


def _get_specialist_input(name: str, ctx: PitcherContext) -> UserPrompt:
    """Get the data input for a named specialist as a UserPrompt (with CachePoints)."""
    builders = {
        "stuff": _build_stuff_input,
        "location": _build_location_input,
        "runvalue": _build_runvalue_input,
        "trends": _build_trend_input,
        "game_shape": _build_game_shape_input,
    }
    return builders[name](ctx)


def _get_specialist_input_text(name: str, ctx: PitcherContext) -> str:
    """Get specialist data input as plain text (no CachePoints)."""
    return _flatten_prompt(_get_specialist_input(name, ctx))


async def audit_and_revise_specialists(
    specialists: SpecialistOutputs,
    specialist_agents: dict[str, Agent[None, str]],
    auditor: Agent[None, AuditResult],
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> tuple[SpecialistOutputs, list[AuditFlag]]:
    """Audit each specialist's output independently, revise any with flags.

    Phase 1.5a: Run 5 per-specialist audits concurrently.
    Phase 1.5b: For any flagged specialist, re-run with audit feedback.

    Returns:
        Tuple of (clean SpecialistOutputs, all collected AuditFlags).
    """
    specialist_names = ["stuff", "location", "runvalue", "trends", "game_shape"]
    outputs: dict[str, str] = {
        name: getattr(specialists, name) for name in specialist_names
    }

    # Build ground truth input per specialist (plain text for audit f-strings)
    ground_truths = {
        name: _get_specialist_input_text(name, ctx) for name in specialist_names
    }

    # Phase 1.5a: Audit all 5 in parallel. The audit is an enhancement,
    # not core: a failed audit call (provider error, rate limit) degrades
    # to passing that specialist through un-audited rather than killing
    # the whole pipeline run.
    async def _audit_one(name: str) -> tuple[str, AuditResult]:
        try:
            audit_input = _build_specialist_audit_input(
                ground_truths[name], outputs[name],
            )
            result = await auditor.run(**agent_kwargs(audit_input, _model_override))
            if tracker is not None:
                u = result.usage()
                tracker.record(tracker_model, u.input_tokens or 0, u.output_tokens or 0, stage="audit")
            return name, result.output
        except Exception:
            log.error("Audit failed for %s specialist; passing through un-audited.",
                      name, exc_info=True)
            return name, AuditResult(is_clean=True, flags=[])

    audit_tasks = [_audit_one(name) for name in specialist_names]
    audit_results = await asyncio.gather(*audit_tasks)

    # Collect all flags, tag with specialist name
    all_flags: list[AuditFlag] = []
    flagged: dict[str, list[AuditFlag]] = {}
    for name, audit_result in audit_results:
        if not audit_result.is_clean:
            for flag in audit_result.flags:
                flag.specialist = name
                all_flags.append(flag)
            flagged[name] = audit_result.flags
            log.info("Audit flagged %s: %d issue(s)", name, len(audit_result.flags))

    if not flagged:
        log.info("All specialists passed audit.")
        return specialists, all_flags

    # Phase 1.5b: Revise flagged specialists in parallel
    log.info("Revising %d flagged specialist(s)...", len(flagged))

    async def _revise_one(name: str, flags: list[AuditFlag]) -> tuple[str, str]:
        try:
            revision_input = _build_specialist_revision_input(
                ground_truths[name], outputs[name], flags,
            )
            agent = specialist_agents[name]
            result = await agent.run(**agent_kwargs(revision_input, _model_override))
            if tracker is not None:
                u = result.usage()
                tracker.record(tracker_model, u.input_tokens or 0, u.output_tokens or 0, stage="revision")
            return name, result.output
        except Exception:
            log.warning("Revision failed for %s specialist, keeping original.", name, exc_info=True)
            return name, outputs[name]

    revision_tasks = [
        _revise_one(name, flags) for name, flags in flagged.items()
    ]
    revisions = await asyncio.gather(*revision_tasks)

    # Apply revisions
    clean_outputs = dict(outputs)
    for name, revised_text in revisions:
        clean_outputs[name] = revised_text
        log.info("Revised %s specialist.", name)

    return (
        SpecialistOutputs(**clean_outputs),
        all_flags,
    )


# ═══════════════════════════════════════════════════════════════════════
# PROMPT DATA FILE (for traceability)
# ═══════════════════════════════════════════════════════════════════════

def _render_pipeline_data_sections(
    ctx: PitcherContext,
    *,
    persona: str = "scout",
) -> list[str]:
    """Render all pipeline prompt sections as a list of strings.

    Pure rendering helper — no I/O. Used by write_pipeline_data_file and
    by callers that want the rendered text without a disk roundtrip
    (e.g. cli.py --print-prompts).

    The persona arg controls which composed writer prompt is rendered in
    the WRITER section.
    """
    persona_obj = get_persona(persona)
    sep = "═" * 72
    sections: list[str] = []

    # Phase 1: Specialist prompts + inputs
    specialist_phases = [
        ("SPECIALIST 1: STUFF", _STUFF_SPECIALIST_PROMPT, _render_user_prompt(_build_stuff_input(ctx))),
        ("SPECIALIST 2: LOCATION", _LOCATION_SPECIALIST_PROMPT, _render_user_prompt(_build_location_input(ctx))),
        ("SPECIALIST 3: RUN VALUE", _RUNVALUE_SPECIALIST_PROMPT, _render_user_prompt(_build_runvalue_input(ctx))),
        ("SPECIALIST 4: TRENDS", _TREND_SPECIALIST_PROMPT, _render_user_prompt(_build_trend_input(ctx))),
        ("SPECIALIST 5: GAME SHAPE", _GAME_SHAPE_SPECIALIST_PROMPT, _render_user_prompt(_build_game_shape_input(ctx))),
    ]
    for label, system, user in specialist_phases:
        sections.append(f"\n{sep}\n{label}\n{sep}\n")
        sections.append(f"## System Prompt\n\n{system}\n")
        sections.append(f"## User Message\n\n{user}\n")

    # Phase 1.5: Data auditor (user message uses placeholder since specialist output isn't known yet)
    sections.append(f"\n{sep}\nDATA AUDITOR\n{sep}\n")
    sections.append(f"## System Prompt\n\n{_DATA_AUDITOR_PROMPT}\n")
    sections.append(
        "## User Message\n\n"
        "[Receives: ground truth data (same as stuff specialist input) + "
        "all 5 specialist outputs for validation]\n"
    )

    # Signal extractor
    sections.append(f"\n{sep}\nSIGNAL EXTRACTOR\n{sep}\n")
    sections.append(f"## System Prompt\n\n{SIGNAL_EXTRACTOR_PROMPT}\n")
    sections.append(
        "## User Message\n\n"
        "[Receives: all 5 specialist outputs (without key signals)]\n"
    )

    # Narrative pipeline: writer + anchor + executive summary
    sections.append(f"\n{sep}\nWRITER\n{sep}\n")
    sections.append(f"## System Prompt\n\n{build_writer_system_prompt(persona_obj)}\n")
    sections.append(
        "## User Message\n\n"
        "[Receives: key signals + all 5 specialist outputs]\n"
    )

    sections.append(f"\n{sep}\nEXECUTIVE SUMMARY (second step — summarizes the final report)\n{sep}\n")
    sections.append(f"## System Prompt\n\n{_EXECUTIVE_SUMMARY_PROMPT}\n")
    sections.append(
        "## User Message\n\n"
        + build_summary_input(
            "[final report capsule, post anchor-revision]",
            "[writer input: key signals + clean specialist analyses]",
        )
        + "\n"
    )

    sections.append(f"\n{sep}\nBRIEF (second step — summarizes the final report)\n{sep}\n")
    sections.append(f"## System Prompt\n\n{build_system_prompt(persona_obj, BRIEF)}\n")
    sections.append(
        "## User Message\n\n"
        + build_summary_input(
            "[final report capsule, post anchor-revision]",
            "[writer input: key signals + clean specialist analyses]",
        )
        + "\n"
    )

    sections.append(f"\n{sep}\nANCHOR CHECK\n{sep}\n")
    sections.append(f"## System Prompt\n\n{ANCHOR_PROMPT}\n")
    sections.append(
        "## User Message\n\n"
        "[Receives: key signals + concatenated specialist outputs + writer capsule]\n"
    )

    return sections


def write_pipeline_data_file(
    ctx: PitcherContext,
    pitcher_id: int,
    provider: str,
    *,
    persona: str = "scout",
) -> tuple[str, str]:
    """Write all pipeline prompts to a data file for end-to-end tracing.

    Dumps every system prompt and user message that would be sent to the
    LLM at each phase of the pipeline.

    Args:
        ctx: Assembled pitcher context.
        pitcher_id: MLB pitcher ID for the filename.
        provider: LLM provider key for the filename.
        persona: Persona id string (default "scout"); controls which
            composed writer prompt is rendered in the WRITER section.

    Returns:
        Tuple of (filename, rendered_text). Callers that need to display
        the text (e.g. --print-prompts) should use the returned string
        directly rather than re-reading the file from disk.

    Raises:
        OSError: If writing the file fails (disk full, permissions, etc.).
            The caller should log and exit with a clear message.
    """
    from pathlib import Path

    sections = _render_pipeline_data_sections(ctx, persona=persona)
    text = "\n".join(sections)

    filename = f"data-{pitcher_id}-{provider}-pipeline.md"
    Path(filename).write_text(text, encoding="utf-8")
    return filename, text


# ═══════════════════════════════════════════════════════════════════════
# RESULT MODEL
# ═══════════════════════════════════════════════════════════════════════

# SpecialistOutputs and AnalyzedContext are defined in models.py and imported above.


class PipelineResult(BaseModel):
    """Result from the multi-agent pipeline."""
    narrative: str
    executive_summary: list[str] = []
    brief: str = ""
    specialists: SpecialistOutputs
    key_signals: KeySignals | None = None
    audit_flags: list[AuditFlag] = []
    anchor_warnings: list[AnchorWarning] = []
    revision_count: int = 0


# ═══════════════════════════════════════════════════════════════════════
# AGENT FACTORY
# ═══════════════════════════════════════════════════════════════════════

class PipelineAgents(NamedTuple):
    """All agents used by the multi-agent pipeline."""

    stuff: Agent[None, str]
    location: Agent[None, str]
    runvalue: Agent[None, str]
    trends: Agent[None, str]
    game_shape: Agent[None, str]
    writer: Agent[None, str]
    auditor: Agent[None, AuditResult]
    anchor: Agent[None, AnchorResult]
    summary: Agent[None, str]
    signal_extractor: Agent[None, KeySignals]
    brief: Agent[None, str]
    mini_model_name: str = ""  # bare model name for UsageTracker calls in the spine

    def specialist_dict(self) -> dict[str, Agent[None, str]]:
        """Return the five specialist agents keyed by name.

        Used to pass specialists to audit_and_revise_specialists. Adding a
        new specialist only requires updating PipelineAgents — callers never
        need to repeat the mapping.
        """
        return {
            "stuff": self.stuff,
            "location": self.location,
            "runvalue": self.runvalue,
            "trends": self.trends,
            "game_shape": self.game_shape,
        }


def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona = DEFAULT_PERSONA,
) -> PipelineAgents:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}")
    model = PROVIDERS[provider]
    mini_model = MINI_PROVIDERS[provider]

    # Split temperature by role: specialists need precision, writer needs voice,
    # auditor/anchor need maximum determinism.
    # Thinking caps: checker=low, specialist=medium, writer=uncapped.
    stuff_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE)
    mini_specialist_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE, mini=True)
    mini_specialist_compact_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)
    writer_settings = make_model_settings(provider, thinking, 0.7, max_tokens=TOKEN_BUDGET_LARGE)
    checker_settings = make_model_settings(provider, cap_thinking(thinking, "low"), 0.1, max_tokens=TOKEN_BUDGET_SMALL, mini=True)
    # signal_extractor does structured cross-specialist extraction from the same
    # large specialist-analyses payload the summarizers see. On Gemini thinking
    # is kept (extraction benefits from reasoning) but the MEDIUM budget gives
    # it headroom so thinking tokens can't truncate the structured KeySignals
    # output; on Claude mini=True already disables thinking, leaving the full
    # MEDIUM budget for output.
    signal_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)
    # Second-step summarizers (executive summary + brief) distill the finished
    # report from a large grounded input. Thinking is disabled so its tokens
    # don't consume the output budget (which truncated the response); the cap is
    # MEDIUM for headroom. They differ only in temperature.
    def _distillation_settings(temperature: float) -> ModelSettings:
        return make_model_settings(
            provider, cap_thinking(thinking, "low"), temperature,
            max_tokens=TOKEN_BUDGET_MEDIUM, mini=True, disable_thinking=True,
        )
    report_summary_settings = _distillation_settings(0.3)
    brief_settings = _distillation_settings(0.6)

    # Prose agents carry the shared skills toolset so they can consult
    # project skills (e.g. statcast-data-conventions) on demand. The
    # library injects skill names/descriptions into instructions, not
    # system_prompt, so frozen writer-prompt fixtures stay byte-identical.
    skills = [skill_toolset()]

    def _specialist(prompt: str) -> Agent[None, str]:
        return Agent(model, output_type=str, system_prompt=prompt,
                     model_settings=stuff_settings, toolsets=skills, defer_model_check=True)

    def _mini_specialist(prompt: str) -> Agent[None, str]:
        return Agent(mini_model, output_type=str, system_prompt=prompt,
                     model_settings=mini_specialist_settings, toolsets=skills, defer_model_check=True)

    def _mini_specialist_compact(prompt: str) -> Agent[None, str]:
        return Agent(mini_model, output_type=str, system_prompt=prompt,
                     model_settings=mini_specialist_compact_settings, toolsets=skills, defer_model_check=True)

    def _writer(prompt: str) -> Agent[None, str]:
        # retries=3: a single malformed skills tool call must not kill
        # the streaming writer phase.
        return Agent(model, output_type=str, system_prompt=prompt,
                     model_settings=writer_settings, toolsets=skills, retries=3,
                     defer_model_check=True)

    def _brief(prompt: str) -> Agent[None, str]:
        # Mini model: BRIEF distills an already-written, anchored report —
        # cheaper than composing it. Persona voice instructions still apply
        # via build_system_prompt(persona, BRIEF). Tool-free (a hallucinated
        # skill call must not kill this non-critical extra); retries=3 mirrors
        # the writer's resilience.
        return Agent(mini_model, output_type=str, system_prompt=prompt,
                     model_settings=brief_settings, retries=3,
                     defer_model_check=True)

    return PipelineAgents(
        stuff=_specialist(_STUFF_SPECIALIST_PROMPT),
        location=_mini_specialist(_LOCATION_SPECIALIST_PROMPT),
        runvalue=_mini_specialist(_RUNVALUE_SPECIALIST_PROMPT),
        trends=_mini_specialist_compact(_TREND_SPECIALIST_PROMPT),
        game_shape=_mini_specialist_compact(_GAME_SHAPE_SPECIALIST_PROMPT),
        writer=_writer(build_writer_system_prompt(persona)),
        auditor=Agent(mini_model, output_type=AuditResult, system_prompt=_DATA_AUDITOR_PROMPT,
                      model_settings=checker_settings, retries=5, defer_model_check=True),
        anchor=Agent(mini_model, output_type=AnchorResult, system_prompt=ANCHOR_PROMPT,
                     model_settings=checker_settings, retries=3, defer_model_check=True),
        summary=Agent(mini_model, output_type=str, system_prompt=_EXECUTIVE_SUMMARY_PROMPT,
                      model_settings=report_summary_settings, retries=3, defer_model_check=True),
        signal_extractor=Agent(mini_model, output_type=KeySignals, system_prompt=SIGNAL_EXTRACTOR_PROMPT,
                               model_settings=signal_settings, retries=3, defer_model_check=True),
        brief=_brief(build_system_prompt(persona, BRIEF)),
        mini_model_name=model_label(mini_model),
    )


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════

async def run_specialists(
    stuff_agent: Agent[None, str],
    location_agent: Agent[None, str],
    runvalue_agent: Agent[None, str],
    trends_agent: Agent[None, str],
    game_shape_agent: Agent[None, str],
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> SpecialistOutputs:
    """Run all 5 specialists concurrently."""
    inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (trends_agent, _build_trend_input(ctx)),
        "game_shape": (game_shape_agent, _build_game_shape_input(ctx)),
    }

    async def _run(name: str, agent: Agent[None, str], prompt: str | UserPrompt) -> str:
        result = await agent.run(**agent_kwargs(prompt, _model_override))
        if tracker is not None:
            u = result.usage()
            tracker.record(tracker_model, u.input_tokens or 0, u.output_tokens or 0,
                           stage=f"specialist:{name}")
        return result.output

    tasks = {
        name: _run(name, agent, prompt)
        for name, (agent, prompt) in inputs.items()
    }

    results = await asyncio.gather(
        tasks["stuff"], tasks["location"],
        tasks["runvalue"], tasks["trends"],
        tasks["game_shape"],
    )

    return SpecialistOutputs(
        stuff=results[0], location=results[1],
        runvalue=results[2], trends=results[3],
        game_shape=results[4],
    )


async def run_analysis_spine(
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> AnalyzedContext:
    """Run the specialist → audit → signal-extraction spine.

    Shared analysis path for report and morning. Returns a grounded
    AnalyzedContext; does not run the writer, anchor check, or hallucination
    check — those are terminal-layer concerns.

    Args:
        ctx: Assembled pitcher context (facts, baselines, arsenal data).
        agents: Pre-built pipeline agents (create once, reuse across picks).
        _model_override: Optional model override for deterministic testing.
        tracker: Optional usage tracker for accumulating per-call token costs.
    """
    mini = agents.mini_model_name
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, agents.game_shape, ctx, _model_override,
        tracker=tracker, tracker_model=mini,
    )
    specialists, audit_flags = await audit_and_revise_specialists(
        raw, agents.specialist_dict(), agents.auditor, ctx, _model_override,
        tracker=tracker, tracker_model=mini,
    )

    signal_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
    )
    signals_failed = False
    try:
        signal_result = await agents.signal_extractor.run(
            **agent_kwargs(signal_input, _model_override)
        )
        if tracker is not None:
            u = signal_result.usage()
            tracker.record(mini, u.input_tokens or 0, u.output_tokens or 0, stage="signals")
        key_signals = signal_result.output
    except Exception:
        log.warning("Signal extractor failed, continuing without key signals.", exc_info=True)
        key_signals = None
        signals_failed = True

    return AnalyzedContext(
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=audit_flags,
        signals_failed=signals_failed,
    )


async def _run_anchor_revision_loop(
    *,
    anchor_agent: Agent[None, AnchorResult],
    writer_agent: Agent[None, str],
    synthesis: str,
    capsule: str,
    max_revisions: int,
    _model_override: Any = None,
) -> tuple[str, AnchorResult, int]:
    """Run the anchor check + writer revision loop to convergence.

    Up to `max_revisions` passes: each iteration asks the anchor agent
    whether the current `capsule` is faithful to the `synthesis`. If
    clean, exit immediately. If the anchor returns warnings, the writer
    is asked to revise (fresh prompt per pass, no history) and the loop
    re-checks the new capsule.

    If `max_revisions` is exhausted without a clean pass, a final anchor
    check captures the surviving warnings so they bubble up in the
    result — the caller will see them in `PipelineResult.anchor_warnings`.

    Extracting this loop makes it unit-testable: the agents are injected
    as parameters, so tests can pass stateful fakes that return dirty-
    then-clean without needing to spin up the full pipeline.

    Args:
        anchor_agent: The anchor check agent (returns AnchorResult).
        writer_agent: The writer agent used for revisions.
        synthesis: The rendered key signals + concatenated specialist outputs.
        capsule: The current writer capsule to check.
        max_revisions: Maximum number of revision passes to attempt.
        _model_override: Optional model override (for testing with TestModel).

    Returns:
        Tuple of (final_capsule, final_anchor_result, revision_count).
        `final_capsule` is the capsule after any revisions (original if
        anchor passed on the first check). `final_anchor_result` is
        either the clean result that ended the loop early, or the final
        check after exhausting max_revisions — surviving warnings live
        in `final_anchor_result.warnings`. `revision_count` is the
        number of revision passes actually run (0 = passed first try).
    """
    revision_count = 0

    for _ in range(max_revisions):
        anchor_result = await anchor_agent.run(
            **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
        )
        anchor_check = anchor_result.output

        if anchor_check.is_clean:
            return capsule, anchor_check, revision_count

        revision_result = await writer_agent.run(
            **agent_kwargs(
                build_revision_message(synthesis, capsule, anchor_check.warnings),
                _model_override,
            )
        )
        capsule = revision_result.output
        revision_count += 1

    # Exhausted max_revisions without a clean pass — final check captures
    # surviving warnings for the caller to surface.
    final_result = await anchor_agent.run(
        **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
    )
    return capsule, final_result.output, revision_count


def _parse_summary_bullets(raw: str) -> list[str]:
    """Parse '- '-prefixed lines from summary output into clean bullets.

    Strips only the literal ``"- "`` marker via ``removeprefix`` — not a
    character set — so a bullet whose content starts with a minus (e.g. a
    negative ``-0.77 xRV100``) keeps its sign. ``lstrip("- ")`` would eat it
    and silently invert the metric's direction.
    """
    return [
        stripped.removeprefix("- ").strip()
        for line in raw.strip().splitlines()
        if (stripped := line.strip()).startswith("- ")
    ]


async def _run_summaries(
    *,
    summary_agent: Agent[None, str],
    brief_agent: Agent[None, str],
    capsule: str,
    writer_input: str,
    _model_override: Any = None,
) -> tuple[list[str], str]:
    """Second-step summarization of the FINISHED capsule.

    Runs the executive summary and BRIEF concurrently, each fed the final
    capsule plus recover-only grounding (see build_summary_input). Returns
    ([], "") without calling either agent when the capsule is empty/
    whitespace. Each summarizer catches its own failure and degrades to an
    empty value, so one failing agent never cancels the other.
    """
    if not capsule.strip():
        log.warning("Final capsule is empty; skipping summarization.")
        return [], ""

    summary_input = build_summary_input(capsule, writer_input)

    async def _run_summary() -> list[str]:
        try:
            result = await summary_agent.run(**agent_kwargs(summary_input, _model_override))
            return _parse_summary_bullets(result.output)
        except Exception:
            log.warning("Executive summary agent failed, skipping.", exc_info=True)
            return []

    async def _run_brief() -> str:
        try:
            result = await brief_agent.run(**agent_kwargs(summary_input, _model_override))
            return result.output.strip()
        except Exception:
            log.warning("Brief agent failed, skipping.", exc_info=True)
            return ""

    bullets, brief = await asyncio.gather(_run_summary(), _run_brief())
    return bullets, brief


async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    _model_override: Any = None,
) -> PipelineResult:
    """Async core of the multi-agent pipeline.

    Phase 1: 5 specialists run concurrently.
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 1.75: Signal extractor identifies cross-specialist patterns.
    Phase 2: Writer composes capsule from specialist outputs + key signals.
    Phase 2.5: Anchor check + revision loop.
    """
    persona_obj = get_persona(persona)
    agents = make_pipeline_agents(provider, thinking, persona_obj)

    # Phases 1 → 1.75: specialist → audit → signal extraction
    log.info("Running analysis spine...")
    analyzed = await run_analysis_spine(ctx, agents=agents, _model_override=_model_override)
    specialists = analyzed.specialists
    audit_flags = analyzed.audit_flags
    key_signals = analyzed.key_signals
    log.info("Analysis spine complete.")

    # Phase 2: Writer streams the initial capsule from clean specialist
    # outputs + key signals. Summarization is a separate second step that
    # runs after the anchor revision loop (see _run_summaries below).
    writer_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
        key_signals=key_signals,
    )
    writer_kwargs = agent_kwargs(writer_input, _model_override)

    async with agents.writer.run_stream(**writer_kwargs) as stream:
        chunks: list[str] = []
        async for delta in stream.stream_text(delta=True):
            print(delta, end="", flush=True)
            chunks.append(delta)
    print()

    capsule = "".join(chunks)

    # EXPLAIN THE MODEL post-processor (non-fatal quality gate).
    # Runs for all personas — a persona that silently drops Pitching+
    # context produces a warning but does not fail the pipeline.
    pre_revision_explainer_ok = check_explainer_present(capsule)
    if not pre_revision_explainer_ok:
        log.warning(
            "[%s] capsule is missing model explanation content",
            persona,
        )

    # Anchor check + revision loop
    specialist_synthesis = (
        f"STUFF:\n{specialists.stuff}\n\n"
        f"LOCATION:\n{specialists.location}\n\n"
        f"RUN VALUE:\n{specialists.runvalue}\n\n"
        f"TRENDS:\n{specialists.trends}\n\n"
        f"GAME SHAPE:\n{specialists.game_shape}"
    )
    synthesis = (
        f"{render_key_signals(key_signals)}\n\n{specialist_synthesis}"
        if key_signals is not None
        else specialist_synthesis
    )

    log.info("Revising report (anchor check loop)...")
    capsule, anchor_check, revision_count = await _run_anchor_revision_loop(
        anchor_agent=agents.anchor,
        writer_agent=agents.writer,
        synthesis=synthesis,
        capsule=capsule,
        max_revisions=MAX_REVISIONS,
        _model_override=_model_override,
    )

    # Re-check explainer after revision loop. The anchor revision can rewrite
    # the capsule entirely, potentially dropping Pitching+ context that was
    # present before. Warn again only if state changed, to avoid duplicate logs.
    if revision_count > 0 and pre_revision_explainer_ok and not check_explainer_present(capsule):
        log.warning(
            "[%s] anchor revision removed model explanation content from capsule",
            persona,
        )

    # Second step: summarize the FINISHED, anchored report (not the
    # pre-revision specialist data). writer_input is attached as recover-only
    # grounding inside _run_summaries.
    log.info("Writing summary and brief from the final report...")
    summary_bullets, brief_text = await _run_summaries(
        summary_agent=agents.summary,
        brief_agent=agents.brief,
        capsule=capsule,
        writer_input=writer_input,
        _model_override=_model_override,
    )

    return PipelineResult(
        narrative=capsule,
        executive_summary=summary_bullets,
        brief=brief_text,
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=audit_flags,
        anchor_warnings=anchor_check.warnings,
        revision_count=revision_count,
    )


def generate_pipeline_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    _model_override: Any = None,
) -> PipelineResult:
    """Generate a report using the specialist→auditor→writer multi-agent pipeline.

    Phase 1: 5 specialists run concurrently (silent).
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 1.75: Signal extractor identifies cross-specialist patterns.
    Phase 2: Writer composes capsule from specialist outputs + key signals (streamed).
    Phase 2.5: Anchor check + revision loop.

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key.
        thinking: Thinking effort level.
        persona: Persona id string (resolved to Persona object internally).
        _model_override: Optional model override for testing.

    Returns:
        PipelineResult with narrative, specialist outputs, and anchor warnings.
    """
    return asyncio.run(
        _run_pipeline(ctx, provider=provider, thinking=thinking,
                      persona=persona, _model_override=_model_override)
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

# Per-persona teaching vocabulary that should not be flagged as unknown.
# Each persona adds domain-specific terms that are safe in that persona's
# voice but not part of the standard _KNOWN_METRICS set.
_PERSONA_KNOWN_METRICS: dict[str, frozenset[str]] = {
    "analyst": frozenset({
        "playability",
        "tunneling gap",
        "pitch tree",
        "arsenal depth",
    }),
    "generic": frozenset(),
}

_METRIC_PATTERN = re.compile(
    r"\b("
    # xMetric pattern (xBA, xWhiff, xwOBA, xRV100, x_whiff, etc.)
    # Underscores are tolerated for variant spellings that sometimes appear
    # in technical writing (e.g. x_whiff) — false positives simply get
    # flagged as "unknown" and can be manually verified.
    r"x[A-Za-z_][A-Za-z0-9_]*"
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

# Stuff-side / Pitch-side variant suffix on x-metrics. The specialist and
# writer prompts teach paired variants — xRV100_S vs xRV100_P, xWhiff_S vs
# xWhiff_P — but _KNOWN_METRICS lists only the bare base (xRV100, xWhiff).
# Strip a trailing _S/_P before testing membership so legitimate variants
# the prompts themselves use don't get flagged as hallucinated.
_VARIANT_SUFFIX = re.compile(r"_[SP]$")


def check_hallucinated_metrics(
    report_text: str,
    persona: str | None = None,
) -> HallucinationReport:
    """Find metric-like and traditional stat terms in report text.

    Scans the LLM output for patterns that look like advanced baseball
    metrics (xMetric, Acronym%, P+/S+/L+ family) and flags any not
    present in _KNOWN_METRICS as unknown. Also detects traditional
    outcome stats that the editor prompt warns against using.

    Args:
        report_text: The LLM-generated report text. Must be a non-empty
            string — an empty narrative is a pipeline failure, not a
            "clean" report, so the caller should check before invoking.
        persona: Optional persona id. When set, per-persona vocabulary from
            _PERSONA_KNOWN_METRICS is added to the allowlist for this check.
            When None, only _KNOWN_METRICS and _TRADITIONAL_STATS are consulted.

    Returns:
        HallucinationReport with unknown_metrics and outcome_stat_warnings.

    Raises:
        TypeError: If report_text is not a string.
        ValueError: If report_text is empty. An empty narrative means the
            pipeline produced nothing to check — a misleading `is_clean`
            result would hide that failure, so we fail loudly.
    """
    if not isinstance(report_text, str):
        raise TypeError(
            f"report_text must be str, got {type(report_text).__name__}"
        )
    if not report_text:
        raise ValueError(
            "report_text is empty — cannot check hallucinations on an "
            "empty narrative (likely a pipeline failure)"
        )

    found = set(_METRIC_PATTERN.findall(report_text))
    if persona:
        if persona not in _PERSONA_KNOWN_METRICS:
            log.debug(
                "no persona-specific metric allowlist for %r (typo or unregistered persona?)",
                persona,
            )
        persona_known = _PERSONA_KNOWN_METRICS.get(persona, frozenset())
    else:
        persona_known = frozenset()

    def _is_known(metric: str) -> bool:
        if metric in _KNOWN_METRICS or metric in _TRADITIONAL_STATS or metric in persona_known:
            return True
        # Tolerate Stuff/Pitch-side variant suffixes (xRV100_S, xWhiff_P) when
        # the base metric is known. The original token is still reported if the
        # base is genuinely unknown, so faithful flagging is preserved.
        return _VARIANT_SUFFIX.sub("", metric) in _KNOWN_METRICS

    unknown = sorted(m for m in found if not _is_known(m))

    traditional_found = set(_TRADITIONAL_PATTERN.findall(report_text))
    outcome_warnings = sorted(traditional_found & _TRADITIONAL_STATS)

    return HallucinationReport(
        unknown_metrics=unknown,
        outcome_stat_warnings=outcome_warnings,
    )


_EXPLAINER_KEYWORDS: frozenset[str] = frozenset({
    "S+", "L+", "P+", "Pitching+", "Stuff+", "Location+",
})


def check_explainer_present(capsule: str) -> bool:
    """Check whether the capsule contains Pitching+ model explanation content.

    Pragmatic keyword scan (not an LLM call). Returns True when any of
    the Pitching+ family tokens appears in the capsule — a proxy for
    "the writer referenced the grading framework." A False return
    triggers a non-fatal stderr warning in the pipeline so operators
    can see when a persona silently dropped the EXPLAIN THE MODEL
    content. Called both before and after the anchor revision loop so
    explainer drift introduced during revision is also surfaced.

    Args:
        capsule: The writer agent's narrative output.

    Returns:
        True if any explainer keyword is present, False otherwise.

    Raises:
        TypeError: If capsule is not a str.
        ValueError: If capsule is empty (pipeline failure, not clean).
    """
    if not isinstance(capsule, str):
        raise TypeError(
            f"capsule must be str, got {type(capsule).__name__}"
        )
    if not capsule:
        raise ValueError(
            "capsule is empty — cannot check for explainer content"
        )

    return any(keyword in capsule for keyword in _EXPLAINER_KEYWORDS)
