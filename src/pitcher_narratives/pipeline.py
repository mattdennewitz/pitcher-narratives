"""Multi-agent specialist→auditor→writer report pipeline (v1.6 prototype).

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

  Phase 2: Writer composes a unified capsule from clean specialist outputs.
  Executive summary agent runs concurrently with writer.

  Phase 2.5: Anchor check + revision loop.

Anti-hallucination guardrails:
  - Specialists receive pre-computed NORMAL/OUTLIER tags on every metric.
  - Per-specialist audit loop catches and corrects errors before synthesis.
  - Directional consistency enforced: S+ below 100 → xRV100 positive, etc.
  - Temperature split: specialists=0.3, writer=0.7, auditor/anchor=0.1.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, NamedTuple

from pydantic import BaseModel
from pydantic_ai import Agent, CachePoint
from pydantic_ai.settings import ThinkingEffort

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
from pitcher_narratives.context import PitcherContext
from pitcher_narratives.engine import (
    LeagueBaseline,
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
from pitcher_narratives.anchor import (
    ANCHOR_PROMPT,
    AnchorResult,
    AnchorWarning,
    build_anchor_message,
    build_revision_message,
)

__all__ = [
    "AuditFlag", "AuditResult", "ExecutiveSummary", "PipelineAgents", "PipelineResult",
    "UserPrompt", "audit_and_revise_specialists", "build_writer_input",
    "generate_pipeline_streaming", "make_pipeline_agents", "run_specialists",
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


class AuditFlag(BaseModel):
    """A single data audit flag."""

    category: str
    specialist: str = ""
    claim: str
    data_shows: str
    suggested_fix: str


class AuditResult(BaseModel):
    """Structured output from the data auditor agent."""

    flags: list[AuditFlag]

    @property
    def is_clean(self) -> bool:
        return len(self.flags) == 0


# ═══════════════════════════════════════════════════════════════════════
# WRITER PROMPT
# ═══════════════════════════════════════════════════════════════════════

_WRITER_PROMPT = """\
You are an elite, sabermetrically inclined baseball writer. You write \
for front offices and data-driven fans.

INPUT: Five specialist analyses of a pitcher's recent window:
1. Stuff analysis — physical pitch characteristics and S+ grades
2. Location analysis — P vs S location impact per pitch
3. Run value decomposition — which outcomes drive each pitch's value
4. Trend analysis — what has changed vs season baseline
5. Game shape — how effectiveness changes within a game (TTO, velocity arc)

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
- DIRECTIONAL CONSISTENCY: If a specialist says a pitch is effective \
(negative xRV100, S+ above 100, strong whiff rate), do not flip the \
narrative to negative. If a specialist says a pitch is weak, do not \
spin it as a strength. Preserve the direction of each specialist's \
assessment.
- If specialists contradict each other on a pitch, acknowledge the \
tension rather than silently picking one side.
- No bullet points, no headers, no tables. Prose only.
- Scale confidence to sample size. Small windows get tentative language.
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section \
with a prior-year relevance level. Follow it. When relevance is LOW, \
prior-season workload does not drive narrative. When relevance is HIGH, \
prior year is residual context but two seasons are NOT a continuous \
timeline. Do not hallucinate cumulative fatigue across an offseason."""


# ═══════════════════════════════════════════════════════════════════════
# EXECUTIVE SUMMARY PROMPT
# ═══════════════════════════════════════════════════════════════════════

_EXECUTIVE_SUMMARY_PROMPT = """\
You are a concise analyst producing a metrics-focused executive \
summary for a front office reader.

Given specialist analyses of a pitcher's recent window, produce \
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
- If data audit flags are present, do NOT repeat any flagged claims.
- Do not call normal metrics unusual. If a metric is within ±1.5 \
stddev of the league average, it is normal.
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
            if at.added_pitches:
                added = ", ".join(p.pitch_name for p in at.added_pitches)
                data_lines.append(f"- Added pitches: {added}")
            if at.dropped_pitches:
                dropped = ", ".join(p.pitch_name for p in at.dropped_pitches)
                data_lines.append(f"- Dropped pitches: {dropped}")
            for pt in at.pitch_trends[:4]:
                mov_parts = []
                if "Steady" not in pt.pfx_x_delta:
                    mov_parts.append(f"H-mov {pt.pfx_x_delta}")
                if "Steady" not in pt.pfx_z_delta:
                    mov_parts.append(f"V-mov {pt.pfx_z_delta}")
                if mov_parts:
                    data_lines.append(f"- {pt.pitch_name} movement: {', '.join(mov_parts)}")

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
        ctx._render_fastball_section(),
        ctx._render_arsenal_section(),
        ctx._render_release_point_section(),
        ctx._render_hard_hit_section(),
    ]
    # Per-appearance pitch trends (three-way comparison)
    if ctx.appearance_pitch_trends is not None:
        data_sections.append(ctx._render_appearance_pitch_trends_section())
    # Cross-season context (when available) — trends specialist gets full YoY section
    if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
        data_sections.append(ctx._render_yoy_section())
    return [
        "\n\n".join(s for s in prefix_sections if s),
        CachePoint(),
        "\n\n".join(s for s in data_sections if s),
    ]


def _build_game_shape_input(ctx: PitcherContext) -> UserPrompt:
    """Build input for the game shape specialist -- TTO, velocity arc, workload.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix and the game shape data sections.
    """
    baselines = render_league_baselines(_pitch_types(ctx))
    prefix_sections = [
        f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
        baselines,
    ]
    data_sections = [
        ctx._render_tto_section(),
        ctx._render_fastball_section(),
        ctx._render_appearances_section(),
        ctx._render_role_section(),
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
            for pt in at.pitch_trends[:4]:
                parts = []
                if "Steady" not in pt.usage_delta:
                    parts.append(f"usage {pt.usage_delta}")
                if "Steady" not in pt.pfx_x_delta:
                    parts.append(f"H-mov {pt.pfx_x_delta}")
                if "Steady" not in pt.pfx_z_delta:
                    parts.append(f"V-mov {pt.pfx_z_delta}")
                if parts:
                    yoy_lines.append(f"- {pt.pitch_name}: {', '.join(parts)}")
            if at.added_pitches:
                yoy_lines.append(
                    f"- Added: {', '.join(p.pitch_name for p in at.added_pitches)}"
                )
            if at.dropped_pitches:
                yoy_lines.append(
                    f"- Dropped: {', '.join(p.pitch_name for p in at.dropped_pitches)}"
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
) -> str:
    """Compose all specialist outputs into writer input.

    Specialist outputs should already be clean (post-audit revision),
    so no audit flags are needed here.
    """
    return "\n\n".join([
        f"## Pitcher: {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n",
        f"## Specialist Analysis 1: Stuff\n{stuff}\n",
        f"## Specialist Analysis 2: Location\n{location}\n",
        f"## Specialist Analysis 3: Run Value\n{runvalue}\n",
        f"## Specialist Analysis 4: Trends\n{trends}\n",
        f"## Specialist Analysis 5: Game Shape\n{game_shape}",
    ])


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
    specialists: "SpecialistOutputs",
    specialist_agents: dict[str, "Agent[None, str]"],
    auditor: "Agent[None, AuditResult]",
    ctx: PitcherContext,
    _model_override: Any = None,
) -> tuple["SpecialistOutputs", list[AuditFlag]]:
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

    # Phase 1.5a: Audit all 5 in parallel
    async def _audit_one(name: str) -> tuple[str, AuditResult]:
        try:
            audit_input = _build_specialist_audit_input(
                ground_truths[name], outputs[name],
            )
            result = await auditor.run(**agent_kwargs(audit_input, _model_override))
            return name, result.output
        except Exception:
            log.error("Audit failed for %s specialist.", name, exc_info=True)
            raise

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

def write_pipeline_data_file(
    ctx: PitcherContext,
    pitcher_id: int,
    provider: str,
    *,
    question: str | None = None,
) -> str:
    """Write all pipeline prompts to a data file for end-to-end tracing.

    Dumps every system prompt and user message that would be sent to the
    LLM at each phase of the pipeline. For the ask pipeline, also includes
    the user's question and the answerer prompt.

    Args:
        ctx: Assembled pitcher context.
        pitcher_id: MLB pitcher ID for the filename.
        provider: LLM provider key for the filename.
        question: If provided, includes the ask-pipeline answerer phase.

    Returns:
        Path to the written file.
    """
    from pathlib import Path

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

    if question is not None:
        # Ask pipeline: answerer phase
        from pitcher_narratives.analyst import ANSWERER_INSTRUCTIONS

        sections.append(f"\n{sep}\nANSWERER\n{sep}\n")
        sections.append(f"## System Prompt\n\n{ANSWERER_INSTRUCTIONS}\n")
        sections.append(
            f"## User Message\n\n"
            f"## Question\n{question}\n\n"
            f"## Pitcher: {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
            f"[Receives: all 5 specialist outputs + any audit flags]\n"
        )
    else:
        # Narrative pipeline: writer + anchor + executive summary
        sections.append(f"\n{sep}\nWRITER\n{sep}\n")
        sections.append(f"## System Prompt\n\n{_WRITER_PROMPT}\n")
        sections.append(
            "## User Message\n\n"
            "[Receives: all 5 specialist outputs + any audit flags]\n"
        )

        sections.append(f"\n{sep}\nEXECUTIVE SUMMARY\n{sep}\n")
        sections.append(f"## System Prompt\n\n{_EXECUTIVE_SUMMARY_PROMPT}\n")
        sections.append(
            "## User Message\n\n"
            "[Receives: same input as writer]\n"
        )

        sections.append(f"\n{sep}\nANCHOR CHECK\n{sep}\n")
        sections.append(f"## System Prompt\n\n{ANCHOR_PROMPT}\n")
        sections.append(
            "## User Message\n\n"
            "[Receives: concatenated specialist outputs + writer capsule]\n"
        )

    mode = "ask" if question else "pipeline"
    filename = f"data-{pitcher_id}-{provider}-{mode}.md"
    Path(filename).write_text("\n".join(sections))
    return filename


# ═══════════════════════════════════════════════════════════════════════
# RESULT MODEL
# ═══════════════════════════════════════════════════════════════════════

class SpecialistOutputs(BaseModel):
    """Raw outputs from each specialist agent."""
    stuff: str
    location: str
    runvalue: str
    trends: str
    game_shape: str


class PipelineResult(BaseModel):
    """Result from the multi-agent pipeline."""
    narrative: str
    executive_summary: list[str] = []
    specialists: SpecialistOutputs
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


def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
) -> PipelineAgents:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}")
    model = PROVIDERS[provider]
    mini_model = MINI_PROVIDERS[provider]

    # Split temperature by role: specialists need precision, writer needs voice,
    # auditor/anchor need maximum determinism.
    # Thinking caps: checker=low, specialist=medium, writer=uncapped.
    stuff_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM)
    mini_specialist_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)
    writer_settings = make_model_settings(provider, thinking, 0.7, max_tokens=TOKEN_BUDGET_LARGE)
    checker_settings = make_model_settings(provider, cap_thinking(thinking, "low"), 0.1, max_tokens=TOKEN_BUDGET_SMALL, mini=True)
    summary_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_SMALL, mini=True)

    def _specialist(prompt: str) -> Agent[None, str]:
        return Agent(model, output_type=str, system_prompt=prompt,
                     model_settings=stuff_settings, defer_model_check=True)

    def _mini_specialist(prompt: str) -> Agent[None, str]:
        return Agent(mini_model, output_type=str, system_prompt=prompt,
                     model_settings=mini_specialist_settings, defer_model_check=True)

    def _writer(prompt: str) -> Agent[None, str]:
        return Agent(model, output_type=str, system_prompt=prompt,
                     model_settings=writer_settings, defer_model_check=True)

    return PipelineAgents(
        stuff=_specialist(_STUFF_SPECIALIST_PROMPT),
        location=_mini_specialist(_LOCATION_SPECIALIST_PROMPT),
        runvalue=_mini_specialist(_RUNVALUE_SPECIALIST_PROMPT),
        trends=_mini_specialist(_TREND_SPECIALIST_PROMPT),
        game_shape=_mini_specialist(_GAME_SHAPE_SPECIALIST_PROMPT),
        writer=_writer(_WRITER_PROMPT),
        auditor=Agent(mini_model, output_type=AuditResult, system_prompt=_DATA_AUDITOR_PROMPT,
                      model_settings=checker_settings, retries=5, defer_model_check=True),
        anchor=Agent(mini_model, output_type=AnchorResult, system_prompt=ANCHOR_PROMPT,
                     model_settings=checker_settings, defer_model_check=True),
        summary=Agent(mini_model, output_type=str, system_prompt=_EXECUTIVE_SUMMARY_PROMPT,
                      model_settings=summary_settings, defer_model_check=True),
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
) -> SpecialistOutputs:
    """Run all 5 specialists concurrently."""
    inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (trends_agent, _build_trend_input(ctx)),
        "game_shape": (game_shape_agent, _build_game_shape_input(ctx)),
    }

    async def _run(agent: Agent[None, str], prompt: str | UserPrompt) -> str:
        result = await agent.run(**agent_kwargs(prompt, _model_override))
        return result.output

    tasks = {
        name: _run(agent, prompt)
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


async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    _model_override: Any = None,
) -> PipelineResult:
    """Async core of the multi-agent pipeline.

    Phase 1: 5 specialists run concurrently.
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 2: Writer composes capsule (with audit flags if any).
    Phase 2.5: Anchor check + revision loop.
    """
    agents = make_pipeline_agents(provider, thinking)

    # Phase 1: Run specialists concurrently
    log.info("Running specialists...")
    raw_specialists = await run_specialists(
        agents.stuff, agents.location, agents.runvalue, agents.trends,
        agents.game_shape, ctx, _model_override,
    )
    log.info("Specialists complete.")

    # Phase 1.5: Per-specialist audit + revision loop
    log.info("Auditing specialist outputs...")
    specialist_agents = {
        "stuff": agents.stuff, "location": agents.location,
        "runvalue": agents.runvalue, "trends": agents.trends,
        "game_shape": agents.game_shape,
    }
    specialists, audit_flags = await audit_and_revise_specialists(
        raw_specialists, specialist_agents, agents.auditor, ctx, _model_override,
    )

    # Phase 2: Writer + Executive Summary run concurrently
    # Writer gets clean specialist outputs (flagged claims already revised).
    writer_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
    )
    writer_kwargs = agent_kwargs(writer_input, _model_override)

    # Run summary in background while writer streams (same input as writer)
    summary_task = asyncio.create_task(
        agents.summary.run(**agent_kwargs(writer_input, _model_override))
    )

    async with agents.writer.run_stream(**writer_kwargs) as stream:
        chunks: list[str] = []
        async for delta in stream.stream_text(delta=True):
            print(delta, end="", flush=True)
            chunks.append(delta)
    print()

    capsule = "".join(chunks)

    # Await executive summary — non-critical, don't crash if it fails
    try:
        summary_result = await summary_task
        summary_raw = summary_result.output
        summary_bullets = [
            line.lstrip("- ").strip()
            for line in summary_raw.strip().splitlines()
            if line.strip().startswith("- ")
        ]
    except Exception:
        log.warning("Executive summary agent failed, skipping.", exc_info=True)
        summary_bullets = []

    # Phase 2.5: Anchor check + revision loop
    revision_count = 0
    synthesis = (
        f"STUFF:\n{specialists.stuff}\n\n"
        f"LOCATION:\n{specialists.location}\n\n"
        f"RUN VALUE:\n{specialists.runvalue}\n\n"
        f"TRENDS:\n{specialists.trends}\n\n"
        f"GAME SHAPE:\n{specialists.game_shape}"
    )

    for _ in range(MAX_REVISIONS):
        anchor_result = await agents.anchor.run(
            **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
        )
        anchor_check = anchor_result.output

        if anchor_check.is_clean:
            break

        revision_result = await agents.writer.run(
            **agent_kwargs(build_revision_message(synthesis, capsule, anchor_check.warnings), _model_override)
        )
        capsule = revision_result.output
        revision_count += 1
    else:
        # Exhausted MAX_REVISIONS without a clean pass — final check for surviving warnings
        anchor_result = await agents.anchor.run(
            **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
        )
        anchor_check = anchor_result.output

    return PipelineResult(
        narrative=capsule,
        executive_summary=summary_bullets,
        specialists=specialists,
        audit_flags=audit_flags,
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
    """Generate a report using the specialist→auditor→writer multi-agent pipeline.

    Phase 1: 5 specialists run concurrently (silent).
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 2: Writer composes capsule from specialist outputs + audit flags (streamed).
    Phase 2.5: Anchor check + revision loop.

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key.
        thinking: Thinking effort level.
        _model_override: Optional model override for testing.

    Returns:
        PipelineResult with narrative, specialist outputs, and anchor warnings.
    """
    return asyncio.run(
        _run_pipeline(ctx, provider=provider, thinking=thinking, _model_override=_model_override)
    )
