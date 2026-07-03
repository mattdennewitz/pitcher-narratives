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
  + key signals.

  Phase 2.5: Anchor check + revision loop. Primary signals are enforced
  (MISSED_SIGNAL), secondary signals are advisory (UNDERWEIGHTED).

  Phase 3: Executive summary agent runs as a second step after the anchor loop.

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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

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
    MAX_FACT_REVISIONS,
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
from pitcher_narratives.frame_delta import (
    build_trend_frame_comparison,
    render_trend_frame_comparison,
)
from pitcher_narratives.temporal import TemporalFrame
from pitcher_narratives.engine import (
    compute_league_baselines,
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
)
from pitcher_narratives.personas import (
    BRIEF,
    DEFAULT_MODE,
    DEFAULT_PERSONA,
    NarrationMode,
    Persona,
    RECAP,
    build_system_prompt,
    build_writer_system_prompt,
    get_persona,
)

if TYPE_CHECKING:
    from pitcher_narratives.curator import CurationPick
from pitcher_narratives.prompt_builder import (
    render_appearances_section,
    render_arsenal_section,
    render_fastball_section,
    render_hard_hit_section,
    render_release_point_section,
    render_role_section,
    render_temporal_section,
    render_tto_section,
    render_yoy_section,
)
from pitcher_narratives.shape import render_pitch_shape
from pitcher_narratives.models import (
    AnalyzedContext,
    AuditFlag,
    AuditResult,
    CoreContext,
    SpecialistOutputs,
)
from pitcher_narratives.signals import (
    SIGNAL_EXTRACTOR_PROMPT,
    KeySignals,
    count_secondary_signals,
    render_key_signals,
)
from pitcher_narratives.value_parity import check_value_parity

__all__ = [
    "AnalyzedContext", "CoreContext",
    "AuditFlag", "AuditResult", "HallucinationReport",
    "KeySignals", "PipelineAgents", "PipelineResult",
    "UserPrompt", "audit_and_revise_specialists", "build_capsule_audit_input",
    "build_fact_revision_message",
    "build_summary_input",
    "build_writer_input", "build_recap_overlay", "check_explainer_present", "check_hallucinated_metrics",
    "flag_record", "flag_summary", "generate_pipeline_streaming", "is_unverified",
    "make_pipeline_agents", "render_recap", "residual_banner", "run_analysis_spine",
    "run_anchor_revision_loop",
    "run_capsule_audit", "run_narration_modes", "run_spine_core", "run_spine_tail",
    "run_specialists",
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


def _record_usage(
    tracker: UsageTracker | None,
    tracker_model: str,
    result: Any,
    stage: str,
) -> None:
    """Record one agent call's token usage on the tracker, if tracking is on."""
    if tracker is None:
        return
    u = result.usage()
    tracker.record(tracker_model, u.input_tokens or 0, u.output_tokens or 0, stage=stage)


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
- DIRECTIONAL CONSISTENCY: L+ above 100 means location helps (L+ is 100-centered, like S+/P+). The \
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
- Movement changes for the primary fastball (pfx_x/pfx_z deltas are provided only there; assess other pitches via their P+/S+/L+ deltas, do not derive movement deltas from raw values)
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
- Platoon-specific strengths and vulnerabilities by handedness — only when the input includes TTO/platoon splits; if absent, skip this angle rather than inferring it"""


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

Checks that reference [NORMAL]/[OUTLIER] tags or S-variant metrics (xRV100_S, xWhiff_S) apply ONLY when those artifacts appear in the ground truth data. When the ground truth has no such tags or metrics (e.g. trends or game-shape data), skip those checks — do not flag their absence.

If everything checks out, return an empty list."""


# AuditFlag and AuditResult are defined in models.py and imported above.

_CAPSULE_AUDITOR_PROMPT = """\
You are a fact-checker for a baseball scouting report. You receive the source \
material the report was built from — raw ground-truth data tables, the \
specialists' analyses, and the key-signals summary — and the finished narrative \
(the capsule). Verify every metric, direction, and factual claim in the capsule \
against that source material.

Flag these problems (reuse the audit categories):
- METRIC_CONTRADICTION: the capsule characterizes a metric in a way the source \
contradicts (calls a NORMAL metric extreme, etc.).
- DIRECTION_ERROR: the capsule states a metric/trend went one way but the source \
shows the other.
- FABRICATED_DATA: the capsule cites a specific number that appears nowhere in \
the source material.
- UNRECONCILED / HALLUCINATED_CAUSATION: a causal claim the source does not support.

Only flag genuine factual errors against the source — not style, emphasis, or \
legitimate synthesis. The specialists' analyses already contain computed deltas, \
contrasts, and paraphrases of grades (e.g. "S+ up 8 points", "28% above \
average"); a number the capsule draws from those is faithful, NOT fabricated. \
If the capsule is faithful, return an empty list of flags."""


def _build_capsule_ground_truth(ctx: PitcherContext) -> str:
    """Combined raw ground truth (all five specialists' input tables)."""
    names = ["stuff", "location", "runvalue", "trends", "game_shape"]
    return "\n\n".join(_get_specialist_input_text(name, ctx) for name in names)


def _build_parity_union(
    ctx: PitcherContext,
    specialists: SpecialistOutputs,
    key_signals: KeySignals | None,
    *,
    exclude: frozenset[str] = frozenset(),
) -> str:
    """A's source-of-truth union: everything the writer saw — raw ground truth,
    clean specialist outputs, and the rendered key signals.

    ``exclude`` names specialists whose *prose* must NOT count as fact-check
    ground truth — a specialist whose revision failed re-audit is unverified, so
    a fabricated number in its prose must not launder into citable truth. Raw
    ground-truth tables and the key signals are always included; only the
    excluded specialists' analysis prose is dropped.
    """
    parts = [_build_capsule_ground_truth(ctx)]
    specialist_prose = {
        "stuff": specialists.stuff,
        "location": specialists.location,
        "runvalue": specialists.runvalue,
        "trends": specialists.trends,
        "game_shape": specialists.game_shape,
    }
    parts.extend(
        text for name, text in specialist_prose.items() if name not in exclude
    )
    if key_signals is not None:
        parts.append(render_key_signals(key_signals))
    return "\n\n".join(parts)


def build_capsule_audit_input(ground_truth: str, capsule: str) -> str:
    """Auditor input: ground truth + the finished capsule to verify."""
    return (
        f"## GROUND TRUTH DATA\n{ground_truth}\n\n"
        f"## FINISHED CAPSULE TO FACT-CHECK\n{capsule}"
    )


def build_fact_revision_message(
    ground_truth: str, capsule: str, flags: list[AuditFlag]
) -> UserPrompt:
    """Ask the writer to correct ONLY the capsule's flagged factual errors.

    Carries the ground truth alongside the auditor's flagged claims (mirrors
    ``anchor.build_revision_message``) so the writer can check the auditor's
    claim strings against the source instead of faithfully inserting a
    mis-stated value. Cache breakpoint after the ground-truth part.
    """
    formatted = "\n".join(
        f"- [{f.category}] \"{f.claim}\" → Data shows: {f.data_shows}. "
        f"Fix: {f.suggested_fix}"
        for f in flags
    )
    return [
        f"## Ground Truth\n{ground_truth}",
        CachePoint(),
        f"## Your Capsule\n{capsule}\n\n"
        f"## Factual Errors Found\n{formatted}\n\n"
        "Revise the capsule to correct ONLY these factual errors. Keep all "
        "other content, structure, voice, and length unchanged. Use the "
        "Ground Truth section for the correct values; if a listed fix "
        "contradicts the ground truth, follow the ground truth.",
    ]


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
- Do not call normal metrics unusual. If the report or attached analyses tag a metric [NORMAL], treat it as normal.
- Output ONLY the 3 bullet points. No headers, no intro, no outro.
- Format: each line starts with "- " followed by the insight."""


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
            velo_tag = outlier_tag(p.window_velo, b.avg_velo, b.velo_std, p.n_pitches_window)
            pfx_x_delta = p.window_pfx_x - b.avg_pfx_x
            pfx_x_tag = outlier_tag(p.window_pfx_x, b.avg_pfx_x, b.pfx_x_std, p.n_pitches_window)
            pfx_z_delta = p.window_pfx_z - b.avg_pfx_z
            pfx_z_tag = outlier_tag(p.window_pfx_z, b.avg_pfx_z, b.pfx_z_std, p.n_pitches_window)
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


def _build_trend_input(ctx: PitcherContext, *, frame_comparison: str | None = None) -> UserPrompt:
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
        render_temporal_section(ctx),
        render_fastball_section(ctx),
        render_arsenal_section(ctx),
        render_release_point_section(ctx),
        render_hard_hit_section(ctx),
    ]
    # Cross-season context (when available) — trends specialist gets full YoY section
    if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
        data_sections.append(render_yoy_section(ctx))
    if frame_comparison is not None:
        data_sections.append(frame_comparison)
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
        render_temporal_section(ctx),
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
    if getattr(ctx, "temporal", None) is not None:
        temporal = render_temporal_section(ctx)
        if temporal:
            parts.append(temporal + "\n")
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


def _get_specialist_input(
    name: str, ctx: PitcherContext, *, trend_frame_comparison: str | None = None
) -> UserPrompt:
    """Get the data input for a named specialist as a UserPrompt (with CachePoints).

    ``trend_frame_comparison`` (only meaningful for the trends specialist) is
    threaded into the trends input so audit ground truth matches what the
    trends specialist actually saw — a CHANGES-mode frame-comparison block the
    specialist cited must appear in the auditor's ground truth, or the auditor
    false-flags it as FABRICATED_DATA.
    """
    if name == "trends":
        return _build_trend_input(ctx, frame_comparison=trend_frame_comparison)
    builders = {
        "stuff": _build_stuff_input,
        "location": _build_location_input,
        "runvalue": _build_runvalue_input,
        "game_shape": _build_game_shape_input,
    }
    return builders[name](ctx)


def _get_specialist_input_text(
    name: str, ctx: PitcherContext, *, trend_frame_comparison: str | None = None
) -> str:
    """Get specialist data input as plain text (no CachePoints)."""
    return _flatten_prompt(
        _get_specialist_input(name, ctx, trend_frame_comparison=trend_frame_comparison)
    )


def _audit_failed_flag(specialist: str = "") -> AuditFlag:
    """Sentinel flag: the auditor itself crashed, so nothing was verified.

    Fail closed — an unaudited report must surface as UNVERIFIED rather than
    ship silently marked clean. Carries the AUDIT_FAILED category so it counts
    in audit_flags/capsule_audit_flags and trips is_unverified/residual_banner.
    """
    return AuditFlag(
        category="AUDIT_FAILED",
        specialist=specialist,
        claim="(auditor call failed — report not fact-checked)",
        data_shows="the audit agent raised before producing a verdict",
        suggested_fix="re-run, or review the report manually",
    )


async def audit_and_revise_specialists(
    specialists: SpecialistOutputs,
    specialist_agents: dict[str, Agent[None, str]],
    auditor: Agent[None, AuditResult],
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    names: list[str] | None = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
    trend_frame_comparison: str | None = None,
) -> tuple[SpecialistOutputs, list[AuditFlag], set[str]]:
    """Audit each specialist's output independently, revise any with flags.

    Phase 1.5a: Run 5 per-specialist audits concurrently.
    Phase 1.5b: For any flagged specialist, re-run with audit feedback.
    Phase 1.5c: Re-audit the revised specialists ONCE (bounded — no loop) and
    collect a ``residual`` set of specialists whose revision still flagged or
    whose re-audit itself failed. Their prose is unverified, so a downstream
    fact-check must not treat it as ground truth.

    Args:
        names: Optional subset of specialist names to audit/revise. When
            omitted, all five specialists are audited (current behavior).
            The returned SpecialistOutputs always carries all five fields;
            unlisted specialists pass through unchanged.
        trend_frame_comparison: CHANGES-mode frame-comparison block threaded
            into the trends specialist's audit ground truth so the auditor sees
            the same source the specialist did.

    Returns:
        Tuple of (clean SpecialistOutputs, all collected AuditFlags, residual
        specialist-name set).
    """
    all_names = ["stuff", "location", "runvalue", "trends", "game_shape"]
    audit_names = names if names is not None else all_names

    # Full output map (all five) so the returned SpecialistOutputs is always
    # complete; only the audit_names subset is actually audited/revised.
    outputs: dict[str, str] = {
        name: getattr(specialists, name) for name in all_names
    }

    # Build ground truth input only for the specialists we audit.
    ground_truths = {
        name: _get_specialist_input_text(
            name, ctx, trend_frame_comparison=trend_frame_comparison
        )
        for name in audit_names
    }

    # Phase 1.5a: Audit all 5 in parallel. Fail closed: a failed audit call
    # (provider error, rate limit) does not pass that specialist through
    # un-audited. It returns (name, None), which the collector below turns
    # into an AUDIT_FAILED sentinel flag on the report — the specialist is
    # never revised against a nonexistent audit result, and the sentinel
    # is visible in the pipeline's audit_flags rather than being silently
    # swallowed.
    async def _audit_one(name: str, text: str) -> tuple[str, AuditResult | None]:
        try:
            audit_input = _build_specialist_audit_input(
                ground_truths[name], text,
            )
            result = await auditor.run(**agent_kwargs(audit_input, _model_override))
            _record_usage(tracker, tracker_model, result, "audit")
            return name, result.output
        except Exception:
            # Fail closed: the auditor crashed, so this specialist's prose was
            # never fact-checked. Signal failure with a None sentinel; the
            # collector surfaces an AUDIT_FAILED flag (visible in audit_flags)
            # without triggering a bogus revision against a nonexistent flag.
            log.error("Audit failed for %s specialist; surfacing AUDIT_FAILED.",
                      name, exc_info=True)
            return name, None

    audit_tasks = [_audit_one(name, outputs[name]) for name in audit_names]
    audit_results = await asyncio.gather(*audit_tasks)

    # Collect all flags, tag with specialist name
    all_flags: list[AuditFlag] = []
    flagged: dict[str, list[AuditFlag]] = {}
    for name, audit_result in audit_results:
        if audit_result is None:
            # Auditor crashed for this specialist — surface the sentinel but
            # skip revision (nothing concrete to revise against). Note the
            # deliberate asymmetry: this FIRST-pass crash does NOT add the
            # specialist to `residual` — its prose stays in the parity
            # union used as fact-check ground truth. Excluding it here
            # would collapse that ground truth down to raw tables and
            # trigger false FABRICATED_DATA flags against otherwise-sound
            # prose; the AUDIT_FAILED sentinel already gates verification
            # of this specialist without penalizing the others. A crash
            # during the RE-audit pass below (post-revision) is different
            # and does mark the specialist residual — see there.
            all_flags.append(_audit_failed_flag(name))
            continue
        if not audit_result.is_clean:
            for flag in audit_result.flags:
                flag.specialist = name
                all_flags.append(flag)
            flagged[name] = audit_result.flags
            log.info("Audit flagged %s: %d issue(s)", name, len(audit_result.flags))

    if not flagged:
        log.info("All specialists passed audit.")
        return specialists, all_flags, set()

    # Phase 1.5b: Revise flagged specialists in parallel
    log.info("Revising %d flagged specialist(s)...", len(flagged))

    async def _revise_one(name: str, flags: list[AuditFlag]) -> tuple[str, str]:
        try:
            revision_input = _build_specialist_revision_input(
                ground_truths[name], outputs[name], flags,
            )
            agent = specialist_agents[name]
            result = await agent.run(**agent_kwargs(revision_input, _model_override))
            _record_usage(tracker, tracker_model, result, "revision")
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
    revised_names: list[str] = []
    for name, revised_text in revisions:
        clean_outputs[name] = revised_text
        revised_names.append(name)
        log.info("Revised %s specialist.", name)

    # Phase 1.5c: ONE bounded re-audit of the revised specialists (no loop).
    # A revision is never re-checked today, so a fabricated number introduced
    # by the revision ships un-audited. Re-audit the revised text once; any
    # specialist still flagged — or whose re-audit itself raises — is residual:
    # its prose is unverified and must be excluded from the fact-check ground
    # truth. A raising re-audit also surfaces an AUDIT_FAILED sentinel (fail
    # closed, mirroring the first pass).
    residual: set[str] = set()
    reaudit_results = await asyncio.gather(
        *(_audit_one(name, clean_outputs[name]) for name in revised_names)
    )
    for name, audit_result in reaudit_results:
        if audit_result is None:
            all_flags.append(_audit_failed_flag(name))
            residual.add(name)
            continue
        if not audit_result.is_clean:
            for flag in audit_result.flags:
                flag.specialist = name
                all_flags.append(flag)
            residual.add(name)
            log.info("Re-audit still flagged %s: %d issue(s)",
                     name, len(audit_result.flags))

    return (
        SpecialistOutputs(**clean_outputs),
        all_flags,
        residual,
    )


# ═══════════════════════════════════════════════════════════════════════
# PROMPT DATA FILE (for traceability)
# ═══════════════════════════════════════════════════════════════════════

def _render_pipeline_data_sections(
    ctx: PitcherContext,
    *,
    persona: str = "scout",
    prior_ctx: PitcherContext | None = None,
) -> list[str]:
    """Render all pipeline prompt sections as a list of strings.

    Pure rendering helper — no I/O. Used by write_pipeline_data_file and
    by callers that want the rendered text without a disk roundtrip
    (e.g. cli.py --print-prompts).

    The persona arg controls which composed writer prompt is rendered in
    the WRITER section. When prior_ctx is provided, the TRENDS specialist
    input includes the RECENT-vs-PRIOR comparison block; when None (the
    default), output is unchanged from before this parameter existed.
    """
    persona_obj = get_persona(persona)
    sep = "═" * 72
    sections: list[str] = []

    trend_frame_comparison = (
        render_trend_frame_comparison(build_trend_frame_comparison(ctx, prior_ctx))
        if prior_ctx is not None
        else None
    )

    # Phase 1: Specialist prompts + inputs
    specialist_phases = [
        ("SPECIALIST 1: STUFF", _STUFF_SPECIALIST_PROMPT, _render_user_prompt(_build_stuff_input(ctx))),
        ("SPECIALIST 2: LOCATION", _LOCATION_SPECIALIST_PROMPT, _render_user_prompt(_build_location_input(ctx))),
        ("SPECIALIST 3: RUN VALUE", _RUNVALUE_SPECIALIST_PROMPT, _render_user_prompt(_build_runvalue_input(ctx))),
        ("SPECIALIST 4: TRENDS", _TREND_SPECIALIST_PROMPT, _render_user_prompt(_build_trend_input(ctx, frame_comparison=trend_frame_comparison))),
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
    prior_ctx: PitcherContext | None = None,
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
        prior_ctx: Optional prior-window context; when provided, the
            TRENDS specialist section includes the RECENT-vs-PRIOR
            comparison block. None (default) leaves output unchanged.

    Returns:
        Tuple of (filename, rendered_text). Callers that need to display
        the text (e.g. --print-prompts) should use the returned string
        directly rather than re-reading the file from disk.

    Raises:
        OSError: If writing the file fails (disk full, permissions, etc.).
            The caller should log and exit with a clear message.
    """
    from pathlib import Path

    sections = _render_pipeline_data_sections(ctx, persona=persona, prior_ctx=prior_ctx)
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
    capsule_audit_flags: list[AuditFlag] = []
    capsule_revised: bool = False
    value_parity_warnings: list[str] = []
    signals_failed: bool = False


def flag_summary(result: PipelineResult) -> dict[str, int | bool]:
    """Countable validation outcomes for a finished pipeline result.

    Persisted per run so the capsule flag/revision rate — never recorded
    before — becomes measurable and the per-mode revision depth can be
    calibrated from real data rather than guessed.
    """
    return {
        "revision_count": result.revision_count,
        "capsule_revised": result.capsule_revised,
        "n_capsule_audit_flags": len(result.capsule_audit_flags),
        "n_anchor_warnings": len(result.anchor_warnings),
        "n_value_parity_warnings": len(result.value_parity_warnings),
        "n_audit_flags": len(result.audit_flags),
        "n_secondary_signals": count_secondary_signals(result.key_signals),
        "signals_failed": result.signals_failed,
    }


def flag_record(
    mode: NarrationMode,
    pitcher_id: int,
    result: PipelineResult,
    *,
    span: int,
) -> dict[str, object]:
    """A persisted calibration record: flag_summary + calibration context.

    Stamps the mode id, pitcher, analysis span (recent-appearance count), and
    the mode's configured revision-depth caps onto ``flag_summary(result)`` so
    the offline aggregator (``pitcher_narratives.calibration``) can compute
    per-mode revision rates and anchor/fact hit-cap rates from real runs.
    """
    return {
        "mode": mode.id,
        "pitcher_id": pitcher_id,
        "span": span,
        "anchor_depth_cap": mode.validation.anchor_depth,
        "fact_depth_cap": mode.validation.fact_depth,
        **flag_summary(result),
    }


_GATING_ANCHOR_CATEGORIES: tuple[str, ...] = ("MISSED_SIGNAL", "DIRECTION_ERROR")
"""Primary/direction anchor categories whose survival past the anchor and fact
loops means the report cannot be trusted, so they gate shipping alongside
residual capsule-audit flags. UNDERWEIGHTED/UNSUPPORTED/OVERSTATED stay advisory
(surfaced but non-blocking)."""


def is_unverified(result: PipelineResult) -> bool:
    """Whether a mode's output shipped with unresolved fact-check flags.

    A result is unverified when residual capsule-audit flags survived the
    fact-revision loop — the same condition that soft-blocks the report CLI.
    Extracted so every narration mode (and morning, Phase 8) shares one
    definition for the aggregate exit policy (design §7, G4).
    """
    return bool(result.capsule_audit_flags) or any(
        w.category in _GATING_ANCHOR_CATEGORIES for w in result.anchor_warnings
    )


def residual_banner(result: PipelineResult, *, label: str = "REPORT") -> str | None:
    """The loud UNVERIFIED banner for an unverified result, else ``None``.

    ``label`` names the surface (REPORT / CHANGES / RECAP / a digest item) so
    the same wording marks residual flags on every mode.
    """
    n = len(result.capsule_audit_flags)
    m = sum(
        1 for w in result.anchor_warnings if w.category in _GATING_ANCHOR_CATEGORIES
    )
    if not n and not m:
        return None
    return (
        f"⚠️  {label} UNVERIFIED — {n} flagged claim(s) and/or {m} unresolved "
        "primary anchor warning(s) survived validation. Review before use."
    )


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
    capsule_auditor: Agent[None, AuditResult]
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
    mode: NarrationMode = DEFAULT_MODE,
) -> PipelineAgents:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}")
    model = PROVIDERS[provider]
    mini_model = MINI_PROVIDERS[provider]

    # Split temperature by role: specialists need precision, writer needs voice,
    # auditor/anchor need maximum determinism.
    # Thinking caps: checker=low, specialist=medium, writer=uncapped.
    # Caveat (Claude provider): Anthropic forces temperature=1 whenever
    # extended thinking is enabled, overriding whatever temperature is
    # requested here. Any settings block below that wants a specific
    # temperature to actually take effect on Claude must also pass
    # disable_thinking=True (see curator._SELECTOR_TEMPERATURE for the
    # canonical example of this trap).
    stuff_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE)
    mini_specialist_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE, mini=True)
    mini_specialist_compact_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)
    writer_settings = make_model_settings(provider, thinking, 0.7, max_tokens=TOKEN_BUDGET_LARGE)
    checker_settings = make_model_settings(provider, cap_thinking(thinking, "low"), 0.1, max_tokens=TOKEN_BUDGET_SMALL, mini=True)
    # Capsule auditor (B): checks the finished capsule against ALL ground truth
    # at once — a large input. MEDIUM budget + thinking medium so thinking can't
    # truncate the structured AuditResult (the report-then-summarize truncation
    # lesson); the existing per-specialist auditor stays on SMALL because its
    # input is one specialist's data.
    capsule_auditor_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.1, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)
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
        writer=_writer(build_writer_system_prompt(persona, mode)),
        auditor=Agent(mini_model, output_type=AuditResult, system_prompt=_DATA_AUDITOR_PROMPT,
                      model_settings=checker_settings, retries=5, defer_model_check=True),
        capsule_auditor=Agent(mini_model, output_type=AuditResult, system_prompt=_CAPSULE_AUDITOR_PROMPT,
                              model_settings=capsule_auditor_settings, retries=5, defer_model_check=True),
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
    names: list[str] | None = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
    trend_frame_comparison: str | None = None,
) -> SpecialistOutputs:
    """Run the specialists concurrently.

    By default all five run. Pass ``names`` to run only a subset (used by the
    core/tail spine split); unlisted specialists default to an empty string in
    the returned SpecialistOutputs.
    """
    all_inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (trends_agent, _build_trend_input(ctx, frame_comparison=trend_frame_comparison)),
        "game_shape": (game_shape_agent, _build_game_shape_input(ctx)),
    }
    selected = list(all_inputs) if names is None else names

    async def _run(name: str, agent: Agent[None, str], prompt: str | UserPrompt) -> tuple[str, str]:
        result = await agent.run(**agent_kwargs(prompt, _model_override))
        if tracker is not None:
            u = result.usage()
            tracker.record(tracker_model, u.input_tokens or 0, u.output_tokens or 0,
                           stage=f"specialist:{name}")
        return name, result.output

    results = await asyncio.gather(
        *(_run(name, *all_inputs[name]) for name in selected)
    )

    outputs = {name: "" for name in all_inputs}
    for name, text in results:
        outputs[name] = text
    return SpecialistOutputs(**outputs)


_CORE_SPECIALISTS = ["stuff", "location", "runvalue", "game_shape"]
_TAIL_SPECIALISTS = ["trends"]


async def run_spine_core(
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> CoreContext:
    """Run the frame-agnostic core of the analysis spine.

    Runs the stuff/location/run-value/game-shape specialists and audits them.
    Frame-agnostic: these specialists read a single window snapshot, so the
    core can be computed once and shared across narration modes. Trends,
    signal extraction, and the anchor check are frame-sensitive — see
    run_spine_tail.
    """
    mini = agents.mini_model_name
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, agents.game_shape, ctx, _model_override,
        names=_CORE_SPECIALISTS, tracker=tracker, tracker_model=mini,
    )
    clean, flags, residual = await audit_and_revise_specialists(
        raw, agents.specialist_dict(), agents.auditor, ctx, _model_override,
        names=_CORE_SPECIALISTS, tracker=tracker, tracker_model=mini,
    )
    return CoreContext(
        stuff=clean.stuff, location=clean.location,
        runvalue=clean.runvalue, game_shape=clean.game_shape,
        audit_flags=flags,
        residual_specialists=sorted(residual),
    )


_SPECIALIST_ORDER = {
    "stuff": 0, "location": 1, "runvalue": 2, "trends": 3, "game_shape": 4,
}


def _order_flags(flags: list[AuditFlag]) -> list[AuditFlag]:
    """Sort audit flags into the canonical specialist order.

    The core/tail split collects core flags (stuff/location/run-value/
    game-shape) then trends flags, so a naive concatenation would place trends
    last. Sorting restores the legacy stuff→location→run-value→trends→
    game-shape order, keeping run_analysis_spine output identical. Stable, so
    multiple flags from the same specialist keep their relative order.
    """
    return sorted(flags, key=lambda f: _SPECIALIST_ORDER.get(f.specialist, 99))


async def run_spine_tail(
    core: CoreContext,
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    prior_ctx: PitcherContext | None = None,
) -> AnalyzedContext:
    """Run the frame-sensitive tail of the analysis spine.

    Runs the trends specialist (+ its audit) and signal extraction over the
    core's four specialists plus trends. Takes ``ctx`` explicitly so a later
    phase can re-run the tail on a different temporal frame while reusing a
    single shared core. In this phase the tail runs on the same ctx as the
    core, so output is identical to the pre-split spine.
    """
    mini = agents.mini_model_name
    trend_frame_comparison = (
        render_trend_frame_comparison(build_trend_frame_comparison(ctx, prior_ctx))
        if prior_ctx is not None
        else None
    )
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, agents.game_shape, ctx, _model_override,
        names=_TAIL_SPECIALISTS, tracker=tracker, tracker_model=mini,
        trend_frame_comparison=trend_frame_comparison,
    )
    merged = SpecialistOutputs(
        stuff=core.stuff, location=core.location, runvalue=core.runvalue,
        game_shape=core.game_shape, trends=raw.trends,
    )
    specialists, trends_flags, trends_residual = await audit_and_revise_specialists(
        merged, agents.specialist_dict(), agents.auditor, ctx, _model_override,
        names=_TAIL_SPECIALISTS, tracker=tracker, tracker_model=mini,
        trend_frame_comparison=trend_frame_comparison,
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
        audit_flags=_order_flags(list(core.audit_flags) + trends_flags),
        signals_failed=signals_failed,
        residual_specialists=sorted(
            set(core.residual_specialists) | trends_residual
        ),
    )


async def run_analysis_spine(
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    prior_ctx: PitcherContext | None = None,
) -> AnalyzedContext:
    """Run the specialist → audit → signal-extraction spine.

    Shared analysis path for report and morning. Composes the frame-agnostic
    core (run_spine_core) with the frame-sensitive tail (run_spine_tail) on a
    single frame; the returned AnalyzedContext is identical to the pre-split
    spine. Does not run the writer, anchor check, or hallucination check —
    those are terminal-layer concerns.

    Output-preserving but NOT latency-preserving on the single-frame path: the
    tail's trends specialist now starts only after the core's specialists and
    their audit/revision finish, whereas the pre-split spine ran all five
    specialists (and all five audits) concurrently. The added serial latency is
    the deliberate cost of a reusable core — a later multi-frame mode (CHANGES)
    runs the core once and re-runs only the tail per frame.

    Args:
        ctx: Assembled pitcher context (facts, baselines, arsenal data).
        agents: Pre-built pipeline agents (create once, reuse across picks).
        _model_override: Optional model override for deterministic testing.
        tracker: Optional usage tracker for accumulating per-call token costs.
    """
    core = await run_spine_core(
        ctx, agents=agents, _model_override=_model_override, tracker=tracker,
    )
    return await run_spine_tail(
        core, ctx, agents=agents, _model_override=_model_override, tracker=tracker,
        prior_ctx=prior_ctx,
    )


async def run_anchor_revision_loop(
    *,
    anchor_agent: Agent[None, AnchorResult],
    writer_agent: Agent[None, str],
    synthesis: str,
    capsule: str,
    max_revisions: int,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
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
        tracker: Optional UsageTracker; when set, each anchor check and
            writer revision records its token usage (stage="anchor" /
            "anchor_revision").
        tracker_model: Bare model name passed to tracker.record(). Ignored
            when tracker is None.

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
    prev_signature: set[tuple[str, str]] | None = None

    for _ in range(max_revisions):
        anchor_result = await anchor_agent.run(
            **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
        )
        _record_usage(tracker, tracker_model, anchor_result, "anchor")
        anchor_check = anchor_result.output

        if anchor_check.is_clean:
            return capsule, anchor_check, revision_count

        # Stall detection: if this pass reproduces the exact warnings of the
        # previous pass, revising again will not converge — stop early rather
        # than burn the remaining budget re-emitting the same corrections. The
        # current anchor_check IS the latest check, so skip the post-cap final.
        signature = {(w.category, w.description) for w in anchor_check.warnings}
        if signature == prev_signature:
            log.info("Anchor loop stalled (identical warnings); stopping early.")
            return capsule, anchor_check, revision_count
        prev_signature = signature

        revision_result = await writer_agent.run(
            **agent_kwargs(
                build_revision_message(synthesis, capsule, anchor_check.warnings),
                _model_override,
            )
        )
        _record_usage(tracker, tracker_model, revision_result, "anchor_revision")
        capsule = revision_result.output
        revision_count += 1

    # Exhausted max_revisions without a clean pass — final check captures
    # surviving warnings for the caller to surface.
    final_result = await anchor_agent.run(
        **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
    )
    _record_usage(tracker, tracker_model, final_result, "anchor")
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


async def run_capsule_audit(
    *,
    auditor: Agent[None, AuditResult],
    writer_agent: Agent[None, str],
    ground_truth: str,
    capsule: str,
    max_fact_revisions: int = MAX_FACT_REVISIONS,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> tuple[str, list[AuditFlag], bool]:
    """B: fact-check the capsule against ground truth, looping audit → revise →
    re-audit up to ``max_fact_revisions`` times to converge.

    Returns (final_capsule, residual_flags, revised):
      - residual_flags are the issues that REMAIN in final_capsule. Empty means
        the report is verified clean (clean on the first audit, or a revision
        converged). Non-empty means the loop was exhausted with flags still
        standing — the caller should treat the report as UNVERIFIED rather than
        ship it silently.
      - revised is True iff at least one fact-revision was applied.
    Degrades to (capsule, current_flags, revised_so_far) on any error — non-fatal.

    Args:
        tracker: Optional UsageTracker; when set, each auditor run records
            stage="fact_audit" and each writer revision records
            stage="fact_revision".
        tracker_model: Bare model name passed to tracker.record(). Ignored
            when tracker is None.
    """
    try:
        result = await auditor.run(
            **agent_kwargs(build_capsule_audit_input(ground_truth, capsule), _model_override)
        )
    except Exception:
        # Fail closed: the auditor never produced a verdict, so nothing in the
        # capsule was fact-checked. Returning [] would mark the report verified
        # (is_unverified → False) and ship it with no banner. Surface a single
        # AUDIT_FAILED residual flag so is_unverified → True and the loud
        # UNVERIFIED banner fires.
        log.warning("Capsule auditor failed; marking report UNVERIFIED.", exc_info=True)
        return capsule, [_audit_failed_flag()], False

    _record_usage(tracker, tracker_model, result, "fact_audit")
    flags = result.output.flags

    if not flags:
        return capsule, [], False

    revised = False
    for attempt in range(1, max_fact_revisions + 1):
        log.info("Capsule auditor flagged %d issue(s); fact revision %d/%d.",
                 len(flags), attempt, max_fact_revisions)
        try:
            revision = await writer_agent.run(
                **agent_kwargs(build_fact_revision_message(ground_truth, capsule, flags), _model_override)
            )
            _record_usage(tracker, tracker_model, revision, "fact_revision")
        except Exception:
            log.warning("Fact revision failed, keeping last capsule.", exc_info=True)
            return capsule, flags, revised

        # A degenerate (empty/whitespace) revision must not overwrite the
        # validated capsule — that would blank the report. Keep the last text.
        if not revision.output.strip():
            log.warning("Fact revision returned empty output; keeping last capsule.")
            return capsule, flags, revised

        capsule = revision.output
        revised = True

        # Re-audit the revision: it can leave issues unfixed or introduce new
        # ungrounded numbers. The residual is what actually remains.
        try:
            recheck = await auditor.run(
                **agent_kwargs(build_capsule_audit_input(ground_truth, capsule), _model_override)
            )
        except Exception:
            log.warning("Capsule re-audit failed; surfacing the last flags.", exc_info=True)
            return capsule, flags, revised

        _record_usage(tracker, tracker_model, recheck, "fact_audit")
        flags = recheck.output.flags

        if not flags:
            log.info("Capsule re-audit clean after %d revision(s).", attempt)
            return capsule, [], revised

    log.warning("Capsule fact-check exhausted %d revision(s); %d issue(s) remain.",
                max_fact_revisions, len(flags))
    return capsule, flags, revised


@dataclass
class _RenderedCapsule:
    """Result of the shared writer + anchor + capsule-audit core."""

    capsule: str
    writer_input: str
    fact_check_source: str
    anchor_check: AnchorResult
    revision_count: int
    capsule_audit_flags: list[AuditFlag]
    capsule_revised: bool


async def _render_capsule(
    ctx: PitcherContext,
    analyzed: AnalyzedContext,
    *,
    agents: PipelineAgents,
    anchor_depth: int,
    fact_depth: int,
    stream: bool,
    check_explainer: bool = True,
    overlay: str | None = None,
    persona_label: str = "",
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> _RenderedCapsule:
    """Writer + anchor + capsule-audit core, shared by the report pipeline and
    the recap render. Report streams (stream=True); recap does not. ``overlay``
    prepends editorial direction to the writer input; ``check_explainer`` gates
    the Pitching+ explainer warnings (off for the short recap brief)."""
    specialists = analyzed.specialists
    key_signals = analyzed.key_signals

    # Phase 2: Writer streams the initial capsule from clean specialist
    # outputs + key signals. Summarization is a separate second step that
    # runs after the anchor revision loop (see _run_summaries below).
    writer_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
        key_signals=key_signals,
    )
    if overlay:
        writer_input = f"{overlay}\n\n{writer_input}"
    writer_kwargs = agent_kwargs(writer_input, _model_override)

    if stream:
        async with agents.writer.run_stream(**writer_kwargs) as stream_ctx:
            chunks: list[str] = []
            async for delta in stream_ctx.stream_text(delta=True):
                print(delta, end="", flush=True)
                chunks.append(delta)
        print()
        capsule = "".join(chunks)
    else:
        _res = await agents.writer.run(**writer_kwargs)
        capsule = _res.output

    # EXPLAIN THE MODEL post-processor (non-fatal quality gate).
    # Runs for all personas — a persona that silently drops Pitching+
    # context produces a warning but does not fail the pipeline.
    # capsule.strip() guards check_explainer_present, which raises on an empty
    # capsule (writer stream yielded no text). An empty capsule degrades
    # downstream (summaries return empty) rather than crashing the run here.
    pre_revision_explainer_ok = bool(capsule.strip()) and (
        not check_explainer or check_explainer_present(capsule)
    )
    if check_explainer and not pre_revision_explainer_ok:
        log.warning(
            "[%s] capsule is missing model explanation content",
            persona_label,
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
    capsule, anchor_check, revision_count = await run_anchor_revision_loop(
        anchor_agent=agents.anchor,
        writer_agent=agents.writer,
        synthesis=synthesis,
        capsule=capsule,
        max_revisions=anchor_depth,
        _model_override=_model_override,
        tracker=tracker,
        tracker_model=agents.mini_model_name,
    )

    # Re-check explainer after revision loop. The anchor revision can rewrite
    # the capsule entirely, potentially dropping Pitching+ context that was
    # present before. Warn again only if state changed, to avoid duplicate logs.
    if check_explainer and revision_count > 0 and pre_revision_explainer_ok and _explainer_dropped(capsule):
        log.warning(
            "[%s] anchor revision removed model explanation content from capsule",
            persona_label,
        )

    # Fact-checking layer (B then A) on the final capsule. Both check against the
    # same source: the union of everything the writer actually saw (raw ground
    # truth + clean specialist outputs + key signals). Feeding B the union — not
    # just the raw tables — stops it from flagging legitimate derived numbers
    # (key-signal deltas, plus-grade paraphrases) as fabricated and triggering a
    # needless fact-revision. Built once and reused by B and A.
    log.info("Fact-checking the capsule against ground truth...")
    fact_check_source = _build_parity_union(
        ctx, specialists, key_signals,
        exclude=frozenset(analyzed.residual_specialists),
    )
    capsule, capsule_audit_flags, capsule_revised = await run_capsule_audit(
        auditor=agents.capsule_auditor,
        writer_agent=agents.writer,
        ground_truth=fact_check_source,
        capsule=capsule,
        max_fact_revisions=fact_depth,
        _model_override=_model_override,
        tracker=tracker,
        tracker_model=agents.mini_model_name,
    )
    # Re-check explainer after B's fact-revision, mirroring the anchor guard:
    # a fact-correction can rewrite the capsule and drop Pitching+ context.
    if check_explainer and capsule_revised and pre_revision_explainer_ok and _explainer_dropped(capsule):
        log.warning(
            "[%s] capsule fact-revision removed model explanation content from capsule",
            persona_label,
        )

    # A fact-revision can rewrite the capsule out from under the anchor result
    # captured above, so re-anchor once against the final text and merge any new
    # warnings into the stored result. Unlike the capsule audit (which fails
    # closed), an anchor crash here is advisory-plus: log and keep the prior
    # anchor_check rather than kill the pipeline.
    if capsule_revised:
        try:
            recheck = await agents.anchor.run(
                **agent_kwargs(build_anchor_message(synthesis, capsule), _model_override)
            )
            _record_usage(tracker, agents.mini_model_name, recheck, "anchor")
            seen = {(w.category, w.description) for w in anchor_check.warnings}
            merged = list(anchor_check.warnings)
            for w in recheck.output.warnings:
                key = (w.category, w.description)
                if key not in seen:
                    seen.add(key)
                    merged.append(w)
            anchor_check = AnchorResult(warnings=merged)
        except Exception:
            log.warning(
                "Post-fact-revision anchor re-check failed; keeping prior anchor result.",
                exc_info=True,
            )

    return _RenderedCapsule(
        capsule=capsule,
        writer_input=writer_input,
        fact_check_source=fact_check_source,
        anchor_check=anchor_check,
        revision_count=revision_count,
        capsule_audit_flags=capsule_audit_flags,
        capsule_revised=capsule_revised,
    )


def build_recap_overlay(*, angle: str, category: str) -> str:
    """Editorial direction prepended to the recap writer input (morning path).

    The recap leads with the editor's angle, grounded in the analyses.
    """
    return (
        "EDITORIAL DIRECTION — lead the recap with this angle, grounded in the "
        "analyses below (never contradict them):\n"
        f"  Angle: {angle}\n"
        f"  Category: {category}"
    )


async def render_recap(
    ctx: PitcherContext,
    analyzed: AnalyzedContext,
    *,
    agents: PipelineAgents,
    pick: "CurationPick | None" = None,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> PipelineResult:
    """Render a Mode RECAP executive brief from a pre-computed AnalyzedContext.

    Reuses the shared writer+validation core (recap depths, explainer off,
    non-streaming). When ``pick`` is provided (morning), its angle/category
    lead the brief; standalone (pick=None) the brief leads with the analyses'
    own thread. Returns a PipelineResult so is_unverified/residual_banner apply.
    """
    overlay = (
        build_recap_overlay(angle=pick.angle, category=pick.category)
        if pick is not None else None
    )
    rc = await _render_capsule(
        ctx, analyzed, agents=agents,
        anchor_depth=RECAP.validation.anchor_depth,
        fact_depth=RECAP.validation.fact_depth,
        stream=False, check_explainer=False, overlay=overlay,
        persona_label="recap", _model_override=_model_override, tracker=tracker,
    )
    value_parity = check_value_parity(rc.capsule, rc.fact_check_source)
    return PipelineResult(
        narrative=rc.capsule,
        specialists=analyzed.specialists,
        key_signals=analyzed.key_signals,
        audit_flags=analyzed.audit_flags,
        anchor_warnings=rc.anchor_check.warnings,
        revision_count=rc.revision_count,
        capsule_audit_flags=rc.capsule_audit_flags,
        capsule_revised=rc.capsule_revised,
        value_parity_warnings=[f"[recap] {w}" for w in value_parity.unmatched],
        signals_failed=analyzed.signals_failed,
    )


async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    mode: NarrationMode = DEFAULT_MODE,
    _model_override: Any = None,
    prior_ctx: PitcherContext | None = None,
) -> PipelineResult:
    """Async core of the multi-agent pipeline.

    Phase 1: 5 specialists run concurrently.
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 1.75: Signal extractor identifies cross-specialist patterns.
    Phase 2: Writer composes capsule from specialist outputs + key signals.
    Phase 2.5: Anchor check + revision loop.
    """
    persona_obj = get_persona(persona)
    agents = make_pipeline_agents(provider, thinking, persona_obj, mode)

    # Phases 1 → 1.75: specialist → audit → signal extraction
    log.info("Running analysis spine...")
    analyzed = await run_analysis_spine(
        ctx, agents=agents, _model_override=_model_override, prior_ctx=prior_ctx,
    )
    specialists = analyzed.specialists
    audit_flags = analyzed.audit_flags
    key_signals = analyzed.key_signals
    log.info("Analysis spine complete.")

    rc = await _render_capsule(
        ctx, analyzed, agents=agents,
        anchor_depth=mode.validation.anchor_depth,
        fact_depth=mode.validation.fact_depth,
        stream=True, check_explainer=True, overlay=None,
        persona_label=persona, _model_override=_model_override,
    )
    capsule = rc.capsule
    writer_input = rc.writer_input
    fact_check_source = rc.fact_check_source
    anchor_check = rc.anchor_check
    revision_count = rc.revision_count
    capsule_audit_flags = rc.capsule_audit_flags
    capsule_revised = rc.capsule_revised

    value_parity = check_value_parity(capsule, fact_check_source)

    # Second step: summarize the FINISHED, anchored report (not the
    # pre-revision specialist data). writer_input is attached as recover-only
    # grounding inside _run_summaries. RECAP is already a brief-length capsule,
    # so distilling it further would duplicate (and cost two agent calls).
    if mode.distill:
        log.info("Writing summary and brief from the final report...")
        summary_bullets, brief_text = await _run_summaries(
            summary_agent=agents.summary,
            brief_agent=agents.brief,
            capsule=capsule,
            writer_input=writer_input,
            _model_override=_model_override,
        )

        # The brief and executive summary are the reader-facing outputs and may
        # recover figures the capsule fact-check never saw, so value-parity them too
        # against the same source. Warnings are labeled by surface so an operator can
        # tell where an ungrounded number entered.
        summary_parity = check_value_parity("\n".join(summary_bullets), fact_check_source)
        brief_parity = check_value_parity(brief_text, fact_check_source)
        value_parity_warnings = (
            [f"[capsule] {w}" for w in value_parity.unmatched]
            + [f"[summary] {w}" for w in summary_parity.unmatched]
            + [f"[brief] {w}" for w in brief_parity.unmatched]
        )
    else:
        summary_bullets, brief_text = [], ""
        value_parity_warnings = [f"[capsule] {w}" for w in value_parity.unmatched]

    return PipelineResult(
        narrative=capsule,
        executive_summary=summary_bullets,
        brief=brief_text,
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=audit_flags,
        anchor_warnings=anchor_check.warnings,
        revision_count=revision_count,
        capsule_audit_flags=capsule_audit_flags,
        capsule_revised=capsule_revised,
        value_parity_warnings=value_parity_warnings,
        signals_failed=analyzed.signals_failed,
    )


def generate_pipeline_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    mode: NarrationMode = DEFAULT_MODE,
    _model_override: Any = None,
    prior_ctx: PitcherContext | None = None,
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
        mode: Narration mode controlling writer prompt selection.
        _model_override: Optional model override for testing.

    Returns:
        PipelineResult with narrative, specialist outputs, and anchor warnings.
    """
    return asyncio.run(
        _run_pipeline(ctx, provider=provider, thinking=thinking,
                      persona=persona, mode=mode, _model_override=_model_override,
                      prior_ctx=prior_ctx)
    )


def run_narration_modes(
    ctx: PitcherContext,
    *,
    modes: list[NarrationMode] | None = None,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",
    _model_override: Any = None,
    prior_ctx: PitcherContext | None = None,
) -> dict[str, PipelineResult]:
    """Run one or more narration modes over a single pitcher context.

    The multi-mode entry point (design G10): returns a PipelineResult per mode,
    keyed by ``mode.id`` in requested order. Each mode runs its own writer +
    validation via generate_pipeline_streaming; the shared analysis spine is
    re-run per mode in phase 4 (single-mode in practice). Reuse of one spine
    across modes is a later-phase optimization (design §10).

    Args:
        ctx: Assembled pitcher context.
        modes: Narration modes to render; defaults to [DEFAULT_MODE].
        provider: LLM provider key.
        thinking: Thinking effort level.
        persona: Persona id string.
        _model_override: Optional model override for testing.
        prior_ctx: Optional prior-window context; forwarded only to modes
            whose temporal_frame includes PRIOR (CHANGES). None for
            report/recap.

    Returns:
        Mapping of mode id -> PipelineResult, insertion-ordered by ``modes``.
    """
    selected = modes if modes is not None else [DEFAULT_MODE]
    results: dict[str, PipelineResult] = {}
    for mode in selected:
        # Dedupe by mode id: a repeated mode (e.g. --mode report,report) must
        # not re-run the whole LLM pipeline and stream the report twice.
        if mode.id in results:
            continue
        mode_prior = prior_ctx if TemporalFrame.PRIOR in mode.temporal_frame else None
        results[mode.id] = generate_pipeline_streaming(
            ctx, provider=provider, thinking=thinking,
            persona=persona, mode=mode, _model_override=_model_override,
            prior_ctx=mode_prior,
        )
    return results


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


def _explainer_dropped(capsule: str) -> bool:
    """True when a non-empty capsule no longer contains model-explanation content.

    The single guard for the "a revision removed the Pitching+ explainer"
    check, shared by every capsule-rewrite stage (anchor loop, fact-revision)
    so the empty-capsule guard can't be applied inconsistently. An empty or
    whitespace capsule returns False — there is nothing to drop, and
    check_explainer_present would otherwise raise on it.
    """
    return bool(capsule.strip()) and not check_explainer_present(capsule)
