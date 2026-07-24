"""Multi-agent specialist→auditor→writer report pipeline (v1.7 prototype).

Architecture:
  Phase 1: 4 specialist agents run in parallel, each producing a focused
  micro-analysis with producer-backed evidence injected for grounding:
    - Stuff Explainer: velocity/movement → S+ grades via S-variant predictions
    - Location Analyst: formal L+ plus pitcher-relative region distributions
    - Run Value Decomposer: 13-outcome attribution, dominant value drivers
    - Trend Spotter: window vs season deltas in velocity, movement, usage, grades

  Phase 1.5: Per-specialist audit + revision loop. Each specialist's output
  is audited independently (4 audits run in parallel) against the raw data
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
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import BaseModel, Field
from pydantic_ai import Agent, CachePoint
from pydantic_ai.settings import ModelSettings, ThinkingEffort

from pitcher_narratives.agent_skills import skill_toolset
from pitcher_narratives.anchor import (
    ANCHOR_PROMPT,
    AnchorResult,
    AnchorWarning,
    build_anchor_message,
    build_reconcile_message,
    build_revision_message,
)
from pitcher_narratives.claim_guard import find_unsupported_claims
from pitcher_narratives.claims import (
    AnalysisCapabilities,
    SpecialistAnalysis,
    enforce_analysis_capabilities,
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
from pitcher_narratives.context import PitcherContext
from pitcher_narratives.costs import UsageTracker, model_label
from pitcher_narratives.engine import (
    format_s_variant_comparisons,
    outlier_tag,
    render_league_baselines,
    render_location_evidence,
)
from pitcher_narratives.facts import (
    AnalysisClaim,
    ClaimType,
    Fact,
    FactRegistry,
    NarrativeArtifact,
    NarrativeClaim,
)
from pitcher_narratives.frame_delta import (
    build_trend_frame_comparison,
    render_trend_frame_comparison,
)
from pitcher_narratives.model_explainer import (
    ModelExplanation,
    ProducerModelSemantics,
    compose_model_explanation,
    render_model_explanation,
)
from pitcher_narratives.personas import (
    DEFAULT_MODE,
    RECAP,
    NarrationMode,
    build_writer_system_prompt,
)
from pitcher_narratives.temporal import TemporalFrame

if TYPE_CHECKING:
    from pitcher_narratives.curator import CurationPick
from pitcher_narratives.models import (
    AnalyzedContext,
    AuditFlag,
    AuditResult,
    ClaimDraft,
    CoreContext,
    NarrativeArtifactDraft,
    NarrativeClaimDraft,
    SpecialistAnalysisDraft,
    SpecialistOutputs,
    VerificationState,
    empty_narrative_draft,
    empty_specialist_analysis,
    render_specialist_analysis,
)
from pitcher_narratives.prompt_builder import (
    render_arsenal_section,
    render_calibration_section,
    render_fastball_section,
    render_hard_hit_section,
    render_release_point_section,
    render_temporal_section,
    render_yoy_section,
)
from pitcher_narratives.shape import render_pitch_shape
from pitcher_narratives.signals import (
    SIGNAL_EXTRACTOR_PROMPT,
    KeySignals,
    Signal,
    count_secondary_signals,
    render_key_signals,
)
from pitcher_narratives.value_parity import check_value_parity

__all__ = [
    "AnalyzedContext",
    "AuditFlag",
    "AuditResult",
    "CoreContext",
    "HallucinationReport",
    "KeySignals",
    "PipelineAgents",
    "PipelineResult",
    "UserPrompt",
    "audit_and_revise_specialists",
    "build_capsule_audit_input",
    "build_fact_revision_message",
    "build_grade_input",
    "build_recap_overlay",
    "build_summary_input",
    "build_writer_input",
    "check_hallucinated_metrics",
    "flag_record",
    "flag_summary",
    "generate_pipeline_streaming",
    "is_unverified",
    "make_pipeline_agents",
    "render_recap",
    "residual_banner",
    "run_analysis_spine",
    "run_anchor_revision_loop",
    "run_capsule_audit",
    "run_data_audit",
    "run_narration_modes",
    "run_specialists",
    "run_spine_core",
    "run_spine_tail",
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
    return "\n".join("  -- [cache breakpoint] --" if isinstance(p, CachePoint) else p for p in parts)


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

# Appended to every specialist system prompt. The bracketed z-score tags
# ([NORMAL], [OUTLIER], [SMALL SAMPLE ...]) are computed in engine.baselines
# and fed into specialist *inputs* as internal annotations. Specialists must
# interpret them, never echo the literal token into prose. Centralized here so
# the rule stays identical across all four specialists.
_NO_TAG_ECHO_RULE = """

TAG HYGIENE (absolute): The bracketed tags in the data — [NORMAL], \
[OUTLIER], [SMALL SAMPLE ...] — describe physical rarity only. Neither NORMAL \
nor OUTLIER determines model importance or whether a separately supported \
observation should be selected. NEVER reproduce a bracketed tag token in a \
claim; remove only the literal token and preserve any observation independently \
supported by cited facts."""

# Matches any bracketed internal tag token that leaked into prose, e.g.
# "[NORMAL]", "[OUTLIER]", "[OUTLIER (above avg, z=+3.2)]",
# "[SMALL SAMPLE, N=3 -- untagged]". These are produced by
# engine.baselines.outlier_tag and must never survive in final narrative.
_TAG_TOKEN_RE = re.compile(r"\s*\[\s*(?:NORMAL|OUTLIER|SMALL SAMPLE)[^\]]*\]")


def _strip_tag_tokens(text: str, *, specialist: str = "") -> str:
    """Remove leaked internal z-score tag tokens from specialist prose.

    Belt-and-suspenders behind ``_NO_TAG_ECHO_RULE``: the bracketed tags
    ([NORMAL]/[OUTLIER]/[SMALL SAMPLE ...]) are ground-truth annotations fed
    into specialist inputs and must never reach the reader. The prompt rule
    reduces the leak; this guarantees it. A removal is logged so regressions
    stay visible rather than being silently scrubbed.
    """
    cleaned, n = _TAG_TOKEN_RE.subn("", text)
    if n:
        # Collapse whitespace/punctuation gaps left where a token was removed.
        cleaned = re.sub(r"  +", " ", cleaned)
        cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
        log.warning(
            "Stripped %d leaked tag token(s) from %s specialist output.",
            n,
            specialist or "unknown",
        )
    return cleaned


_STUFF_SPECIALIST_PROMPT = """\
You are a pitch-physics analyst. Describe producer-backed physical aggregates \
and S-model outputs without inventing model drivers or causal mechanisms.

MODEL BOUNDARY:
- S omits realized plate_x and plate_z, but it is not "pure velocity and \
movement," a tunneling model, or count-neutral. It also uses release traits, \
arm angle, derived acceleration/spin coordinates, handedness/platoon context, \
fastball velocity context, coarse repertoire shares, and count processing.
- S+ is a predictive grade, not feature attribution. Without an explicit \
feature-attribution capability and cited facts, the supplied aggregate profile \
does not identify the model driver.

EVIDENCE RULES:
- NORMAL and OUTLIER tags describe physical rarity only. NORMAL does not mean \
irrelevant; OUTLIER does not mean important to the model.
- Use the "Pitch Shape vs Arm Slot" section to compare movement with the \
expectation for the pitcher's arm angle. A DEAD ZONE label means the \
fastball's movement matches its slot expectation on both axes. Describe \
physical rarity only; do not turn this label into quality, intent, mechanics, \
or causal attribution.
- Never substitute an unshown explanation such as movement interaction, \
tunneling, deception, intent, command, target execution, or mechanics.
- Tunneling, deception, intent, command, biomechanical, and feature-importance \
claims require the matching AVAILABLE capability plus its cited fact IDs. An \
unavailable capability cannot be recovered from raw averages or prose.
- Do not apply a universal expected-whiff threshold. Compare a rate only with \
the supplied pitch-type, season, and population reference fact.
- Preserve sign semantics: below-100 S+ should pair with costly positive \
xRV100_S; above-100 S+ should pair with run-saving negative xRV100_S. Report a \
supplied discrepancy instead of forcing an explanation.
- Every quantitative, directional, comparative, or behavioral observation must \
cite the exact supplied fact IDs. Never cite generated prose as evidence.

OUTPUT:
Return the structured draft fields observations, supported_interpretations, \
and limitations. Every claim supplies claim_type, confidence, and exact \
fact_ids. A supported interpretation must stay within enabled capabilities. \
When aggregates do not reconcile with S+, use this limitation exactly: \
"The supplied aggregate profile does not identify the model driver." Do not \
include internal NORMAL/OUTLIER tag tokens in claim text."""

_LOCATION_SPECIALIST_PROMPT = """\
You are a pitch location analyst. Report exactly two producer-backed \
evidence types for each pitch:

1. Formal Location+: the selected appearance aggregate's emitted L+ and \
xRV100_L values. These are the formal L-variant model outputs; do not \
reconstruct them from P and S values.
2. Pitcher-relative location distribution: exact shares of the emitted \
region labels, with numerator, denominator, coverage, frame, and cited \
fact IDs.

INTERPRETATION RULES:
- L+ is 100-centered and higher is better. xRV100_L is runs per 100 \
pitches and lower is better.
- Keep overall, left-handed-batter, and right-handed-batter distributions \
separate. Never silently pool a batter-side split.
- A distribution marked unavailable cannot support any spatial pattern.
- State exact shares and samples. Do not add qualitative labels that the \
evidence does not provide.
- Do not infer intended aim, execution skill, hitter behavior, or a causal \
mechanism from a region distribution.
- Do not use zone rate, chase rate, CSW, or P-minus-S differences as spatial \
evidence.
- Cover every pitch with available evidence. Return structured observations, \
supported_interpretations, and limitations; every claim supplies claim_type, \
confidence, and exact fact_ids."""

_RUNVALUE_SPECIALIST_PROMPT = """\
You are a run value decomposition analyst. Use the producer-emitted \
13-outcome P-model attribution to describe which modeled outcomes contribute \
most to each pitch type's raw expected run value.

The three totals have different semantics:
- Raw pre-centering xRV100 is the sum of the 13 outcome contributions.
- The league-centering offset is a producer-emitted normalization term.
- Centered P xRV100 equals raw total plus the offset. Only this centered value \
supports above/below-average effectiveness language.

Sign convention for raw outcome contributions:
- Negative contribution = the modeled outcome saves runs.
- Positive contribution = the modeled outcome costs runs.

Rules:
- Cover every pitch with available attribution, prioritizing the 2-3 largest \
absolute outcome contributions.
- Name specific outcomes, magnitudes, and their supplied fact IDs.
- Never label the raw total as ordinary xRV100 or use it for effectiveness.
- Never infer that movement, velocity, location, intent, hitter behavior, or \
execution caused an outcome contribution. No such causal evidence is supplied.
- Use only the fact-tagged values provided. Preserve their fact IDs so later \
stages can audit every claim.
- If attribution is absent, state that it is unavailable; do not reconstruct it.
- Return structured observations, supported_interpretations, and limitations; \
every claim supplies claim_type, confidence, and exact fact_ids.
- No redundant S+/P+ discussion."""

_TREND_SPECIALIST_PROMPT = """\
You are a trend analyst. Your job is to identify what has changed in \
the pitcher's recent window compared to season baseline and flag the \
direction and magnitude of those changes.

Look at:
- Velocity deltas (up, down, steady)
- P+/S+/L+ deltas per pitch type
- Usage rate shifts (biggest increases/decreases)
- Movement changes for the primary fastball (pfx_x/pfx_z deltas are provided \
only there; assess other pitches via their P+/S+/L+ deltas, and do not derive \
movement deltas from raw values)
- Release point shifts
- Hard-hit rate shifts

Rules:
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section. \
Respect the prior-year relevance level. Do not frame window-vs-season \
deltas as long-term trends when the current season has few appearances. \
Do not connect prior-season workload to current-season patterns as \
cause-and-effect.
- Lead with the single most important change.
- Report sample size and comparison design before a directional interpretation. \
If release, shape, velocity, grade, or contact measures move together, describe \
only the co-movement and cited magnitudes. It may be consistent with a possible \
adjustment, but it does not identify a cause, intent, or mechanism.
- One focused paragraph covering the key trends. Skip what's steady.
- No projection or prediction — just what changed and by how much.
- Return structured observations, supported_interpretations, and limitations; \
every claim supplies claim_type, confidence, and exact fact_ids."""

# ═══════════════════════════════════════════════════════════════════════
# DATA AUDITOR PROMPT
# ═══════════════════════════════════════════════════════════════════════

_DATA_AUDITOR_PROMPT = """\
You are a data auditor for a baseball analytics pipeline. You receive \
ONE specialist's analysis alongside the raw data it was based on. \
Your job is to flag every instance where the prose contradicts, \
misrepresents, or hallucinates beyond the data.

CHECK FOR THESE SPECIFIC PROBLEMS:

1. RARITY_MISSTATEMENT: The prose contradicts the supplied comparison or \
NORMAL/OUTLIER rarity tag. NORMAL does not mean irrelevant to the model, and \
OUTLIER does not mean important.

2. DIRECTION_ERROR: The prose reverses a supplied grade, run-value, rate, or \
delta sign. Do not apply an unsupplied domain heuristic as evidence.

3. SIGN_INCONSISTENCY: S+ and xRV100_S point in opposite directions \
in the prose. If S+ < 100, xRV100_S should be positive (costs runs). \
If S+ > 100, xRV100_S should be negative (saves runs).

4. UNSUPPORTED_RECONCILIATION: The prose uses a universal threshold or \
unsupplied pitch-class ordering. A rate is strong or weak only against the \
supplied pitch-type, season, and population reference.

5. HALLUCINATED_CAUSATION: The prose invents a model driver, feature \
importance, intent, command, tunneling, deception, biomechanical explanation, \
or other causal mechanism without the matching AVAILABLE capability and cited \
fact IDs. Physical rarity and outcome contribution are not causal evidence.

6. FABRICATED_DATA: The prose cites a specific number that does not \
appear in the typed fact input.

7. UNCITED_CLAIM: A quantitative, directional, comparative, spatial, platoon, \
behavioral, model-semantic, or causal claim lacks exact same-frame fact IDs. \
Model probabilities must be described as modeled estimates, not observed hitter \
behavior.

For each problem found, report:
- The exact claim ID(s) being rejected
- The exact same-frame fact ID(s) that establish the contradiction
- The specific claim that is wrong
- What the data actually shows
- A suggested correction

Checks that reference [NORMAL]/[OUTLIER] tags or S-variant metrics \
(xRV100_S, xWhiff_S) apply ONLY when those artifacts appear in the ground \
truth data. When the ground truth has no such tags or metrics (e.g. trends \
data), skip those checks — do not flag their absence.

If everything checks out, return an empty list."""


# AuditFlag and AuditResult are defined in models.py and imported above.

_CAPSULE_AUDITOR_PROMPT = """\
You are a fact-checker for a baseball scouting report. You receive only \
producer-backed ground-truth data and the finished narrative (the capsule). \
Generated specialist prose and key signals are not new factual authority. \
Verify every metric, direction, and factual claim in the capsule against the \
producer-backed source material.

Flag these problems (reuse the audit categories):
- METRIC_CONTRADICTION: the capsule states exact rarity wording that contradicts \
the supplied NORMAL/OUTLIER tag. Do not treat importance or selection as a \
rarity contradiction.
- DIRECTION_ERROR: the capsule states a metric/trend went one way but the source \
shows the other.
- FABRICATED_DATA: the capsule cites a specific number that appears nowhere in \
the source material.
- UNRECONCILED / HALLUCINATED_CAUSATION: a causal claim the source does not support.

TEMPORAL FRAMES: The source material can contain TWO baselines for the same \
metric: recent-window-vs-SEASON deltas in the context tables, and a \
"Recent vs Prior Window (code-computed deltas)" block comparing the recent \
window to the window just before it. These legitimately disagree in magnitude \
and even direction (the season average includes the recent games). A capsule \
claim that matches EITHER baseline is grounded — verify it against the \
baseline it narrates, and NEVER flag or "correct" a number from one baseline \
using the other. A change-focused capsule narrates the recent-vs-prior block \
by default.

Only flag genuine factual errors against the source — not style or emphasis. \
Computed deltas and contrasts from the producer-backed context and specialist \
input tables are valid evidence (for example, "S+ up 8 points"); generated \
specialist analyses and key signals are not evidence and never appear in this \
ground-truth payload. For every flag, return the rejected claim IDs and the \
exact same-frame fact IDs
that establish the contradiction. If the capsule is faithful, return an empty
list of flags."""


def _build_capsule_ground_truth(ctx: PitcherContext, *, trend_frame_comparison: str | None = None) -> str:
    """Combined raw ground truth (all four specialists' input tables).

    ``trend_frame_comparison`` threads the CHANGES-mode recent-vs-prior block
    into the trends input exactly as the trends specialist saw it — the same
    mechanism as the per-specialist audit (see _get_specialist_input). Without
    it the capsule auditor sees only recent-vs-season deltas and "corrects"
    correct prior-frame numbers into the season frame.
    """
    names = ["stuff", "location", "runvalue", "trends"]
    return "\n\n".join(
        _get_specialist_input_text(name, ctx, trend_frame_comparison=trend_frame_comparison) for name in names
    )


def _build_parity_union(
    ctx: PitcherContext,
    specialists: SpecialistOutputs,
    key_signals: KeySignals | None,
    *,
    exclude: frozenset[str] = frozenset(),
    trend_frame_comparison: str | None = None,
) -> str:
    """Build capsule fact-check ground truth from producer-backed evidence only.

    Validated specialist analyses and key signals are writer inputs, not new
    facts. They are deliberately excluded here so generated prose can never
    become factual authority for the capsule auditor.
    """
    parts = [_build_capsule_ground_truth(ctx, trend_frame_comparison=trend_frame_comparison)]
    return "\n\n".join(parts)


def build_capsule_audit_input(ground_truth: str, capsule: str) -> str:
    """Auditor input: ground truth + the finished capsule to verify."""
    return f"## GROUND TRUTH DATA\n{ground_truth}\n\n## FINISHED CAPSULE TO FACT-CHECK\n{capsule}"


def build_fact_revision_message(ground_truth: str, capsule: str, flags: list[AuditFlag]) -> UserPrompt:
    """Ask the writer to correct ONLY the capsule's flagged factual errors.

    Carries the ground truth alongside the auditor's flagged claims (mirrors
    ``anchor.build_revision_message``) so the writer can check the auditor's
    claim strings against the source instead of faithfully inserting a
    mis-stated value. Cache breakpoint after the ground-truth part.
    """
    formatted = "\n".join(
        f'- [{f.category}] "{f.claim}" → Data shows: {f.data_shows}. Fix: {f.suggested_fix}' for f in flags
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
- Do not call normal metrics unusual. If the report or attached analyses tag \
a metric [NORMAL], treat it as normal.
- Output ONLY the 3 bullet points. No headers, no intro, no outro.
- Format: each line starts with "- " followed by the insight."""

_NARRATIVE_ARTIFACT_PROMPT = """\
Return a structured narrative artifact with `content` and `claims`. The content \
follows the requested editorial format. Every quantitative, directional, \
comparative, spatial, platoon, causal, and model-semantic statement must have \
one claim whose text appears verbatim in content. Each claim copies exact \
fact_ids and source_claim_ids from the verified input; never cite generated \
Key Signal text as a source claim. Omit a statement when no verified source \
claim and same-frame facts support it."""


# render_league_baselines and outlier_tag are imported from engine.py


# ═══════════════════════════════════════════════════════════════════════
# DATA BUILDERS
# ═══════════════════════════════════════════════════════════════════════


_REQUIRED_CAPABILITY_NAMES = (
    "feature_attribution",
    "location_regions",
    "pitch_targets",
    "biomechanical_causality",
    "tunneling_measurement",
    "platoon_splits",
)
_RUNVALUE_MECHANISM_LIMITATION = (
    "Run-value component attribution describes modeled contribution only; "
    "it does not identify a causal, physical, or location mechanism."
)


def _analysis_capabilities(
    registry: FactRegistry,
    *,
    frame_id: str,
) -> AnalysisCapabilities:
    """Load a complete same-frame typed capability manifest or fail closed."""
    capabilities = AnalysisCapabilities.from_registry(registry, frame_id=frame_id)
    missing = [name for name in _REQUIRED_CAPABILITY_NAMES if capabilities.evidence_fact_id(name) is None]
    if missing:
        raise ValueError("missing typed availability facts for required capabilities: " + ", ".join(missing))
    return capabilities


def _reader_claim_provenance(
    ctx: PitcherContext,
    text: str,
) -> tuple[AnalysisCapabilities, tuple[str, ...]]:
    """Return closed capabilities and exact registry citations in reader prose."""
    capabilities = _analysis_capabilities(ctx.facts, frame_id=ctx.frame_id)
    registered_ids = {fact.id for fact in ctx.facts.facts() if fact.frame_id == ctx.frame_id}
    cited_ids = tuple(
        sorted({token for token in re.findall(r"\[([^\[\]\s]+)\]", text) if token in registered_ids})
    )
    return capabilities, cited_ids


def _render_fact_catalog(
    registry: FactRegistry,
    *,
    fact_ids: Iterable[str],
) -> str:
    """Render only surfaced citable roots; base lineage remains registry-internal."""
    requested = tuple(dict.fromkeys(fact_ids))
    unknown = tuple(fact_id for fact_id in requested if fact_id not in registry)
    if unknown:
        raise ValueError("fact catalog contains unknown root IDs: " + ", ".join(unknown))
    lines = ["## Citable Fact Registry"]
    for fact_id in sorted(requested):
        fact = registry.get(fact_id)
        unit = f" {fact.unit}" if fact.unit else ""
        sample = f"; n={fact.sample_size}" if fact.sample_size is not None else ""
        lines.append(
            f"- [{fact.id}] {fact.metric} ({fact.entity}; {fact.population}) = {fact.value}{unit}{sample}"
        )
    return "\n".join(lines)


def _calibration_evidence_ids(
    ctx: PitcherContext,
    *,
    specialist: str,
) -> set[str]:
    """Select only calibration facts whose rendered rows reach a specialist."""
    selected = {fact_id for path, fact_id in ctx.fact_ids.items() if path.startswith("calibration.metadata.")}
    table_prefixes = {
        "stuff": ("calibration.S.",),
        "grade": ("calibration.P.",),
        "runvalue": (
            "calibration.P.final_outcome.",
            "calibration.S.final_outcome.",
        ),
        "location": (),
        "trends": (),
    }
    if specialist not in table_prefixes:
        raise ValueError(f"unknown specialist fact surface {specialist!r}")
    selected.update(
        fact_id for path, fact_id in ctx.fact_ids.items() if path.startswith(table_prefixes[specialist])
    )
    return selected


def _render_specialist_evidence(
    ctx: PitcherContext,
    *,
    specialist: str,
    surfaced_text: str,
) -> str:
    """Render the exact root-fact closure exposed by one specialist handoff."""
    registry = ctx.facts
    capabilities = _analysis_capabilities(registry, frame_id=ctx.frame_id)
    prefixes = {
        "stuff": (
            "arsenal[",
            "intermediates[",
            "pitch_shape.",
            "cross_season_summary.",
            "arsenal_trend.",
            "league_baselines[",
        ),
        "location": ("formal_location[", "location_distributions["),
        "runvalue": ("league_baselines[",),
        "trends": (
            "temporal.",
            "fastball.",
            "arsenal[",
            "release_point.",
            "hard_hit_rate.",
            "cross_season_summary.",
            "arsenal_trend.",
            "league_baselines[",
        ),
        "grade": (
            "arsenal[",
            "intermediates[",
            "pitch_shape.",
            "formal_location[",
            "location_distributions[",
            "league_baselines[",
        ),
    }
    if specialist not in prefixes:
        raise ValueError(f"unknown specialist fact surface {specialist!r}")
    surfaced_ids = {
        fact_id for path, fact_id in ctx.fact_ids.items() if path.startswith(prefixes[specialist])
    }
    surfaced_ids.update(_calibration_evidence_ids(ctx, specialist=specialist))
    surfaced_ids.update(
        token for token in re.findall(r"\[([^\[\]\s]+)\]", surfaced_text) if token in registry
    )
    surfaced_ids.update(fact_id for _, fact_id in capabilities.evidence_fact_ids)
    return f"{capabilities.render()}\n\n{_render_fact_catalog(registry, fact_ids=surfaced_ids)}"


def _materialize_claim(
    draft: ClaimDraft,
    *,
    frame_id: str,
    registry: FactRegistry,
) -> AnalysisClaim:
    manifest_version = registry.manifest_version
    if manifest_version is None or not manifest_version.strip():
        raise ValueError("specialist claim registry requires a manifest version")
    return AnalysisClaim.create(
        text=draft.text,
        fact_ids=draft.fact_ids,
        frame_id=frame_id,
        manifest_version=manifest_version,
        fact_registry_version=registry.version,
        claim_type=draft.claim_type,
        confidence=draft.confidence,
    ).validate(registry)


def _is_split_specific_fact(fact: Fact) -> bool:
    evidence = f"{fact.population}|{fact.semantic_key}|{fact.metric}".lower()
    return any(
        marker in evidence
        for marker in (
            "batter_side=",
            "platoon",
            "vs_lhb",
            "vs_rhb",
            "same_side",
            "opposite_side",
        )
    )


def _materialize_specialist_draft(
    draft: SpecialistAnalysisDraft,
    *,
    specialist: str,
    registry: FactRegistry,
    frame_id: str,
) -> SpecialistAnalysis:
    """Bind an untrusted draft to one exact evidence registry and enforce policy."""
    analysis = SpecialistAnalysis(
        observations=tuple(
            _materialize_claim(claim, frame_id=frame_id, registry=registry) for claim in draft.observations
        ),
        supported_interpretations=tuple(
            _materialize_claim(claim, frame_id=frame_id, registry=registry)
            for claim in draft.supported_interpretations
        ),
        limitations=tuple(
            _materialize_claim(claim, frame_id=frame_id, registry=registry) for claim in draft.limitations
        ),
    ).validate(registry)
    capabilities = _analysis_capabilities(registry, frame_id=frame_id)

    for claim in analysis.observations:
        if claim.claim_type in {
            ClaimType.MODEL_DRIVER,
            ClaimType.SPATIAL,
            ClaimType.PLATOON,
            ClaimType.TUNNELING,
            ClaimType.DECEPTION,
            ClaimType.INTENT,
            ClaimType.COMMAND,
            ClaimType.BIOMECHANICAL,
            ClaimType.CAUSAL,
        }:
            raise ValueError(f"{claim.claim_type.value} claim belongs in supported interpretations")

    for claim in analysis.supported_interpretations:
        if claim.claim_type is not ClaimType.PLATOON:
            continue
        capability_id = capabilities.evidence_fact_id("platoon_splits")
        cited_split_facts = (registry.get(fact_id) for fact_id in claim.fact_ids if fact_id != capability_id)
        if not any(_is_split_specific_fact(fact) for fact in cited_split_facts):
            raise ValueError("platoon claim requires a split-specific cited fact")

    if specialist == "trends":
        for claim in analysis.claims:
            if claim.claim_type is not ClaimType.COMPARATIVE:
                continue
            if not any(
                registry.get(fact_id).transform
                in {
                    "comparison:delta",
                    "comparison:difference",
                    "comparison:ratio",
                    "comparison:percent_change",
                }
                for fact_id in claim.fact_ids
            ):
                raise ValueError("comparative trend claim requires an exact recent-vs-prior comparison fact")

    if specialist == "runvalue":
        rejected_components = tuple(
            claim
            for claim in analysis.supported_interpretations
            if claim.claim_type is ClaimType.VALUE_COMPONENT
        )
        if rejected_components:
            accepted = tuple(
                claim
                for claim in analysis.supported_interpretations
                if claim.claim_type is not ClaimType.VALUE_COMPONENT
            )
            generated_limitations = tuple(
                AnalysisClaim.create(
                    text=_RUNVALUE_MECHANISM_LIMITATION,
                    fact_ids=claim.fact_ids,
                    frame_id=frame_id,
                    manifest_version=registry.manifest_version or "",
                    fact_registry_version=registry.version,
                    claim_type=ClaimType.MODEL_SEMANTIC,
                    confidence="deterministic_policy",
                ).validate(registry)
                for claim in rejected_components
            )
            analysis = SpecialistAnalysis(
                observations=analysis.observations,
                supported_interpretations=accepted,
                limitations=analysis.limitations + generated_limitations,
            )

    return enforce_analysis_capabilities(analysis, capabilities, registry)


def _materialize_narrative_claim(
    draft: NarrativeClaimDraft,
    *,
    registry: FactRegistry,
    frame_id: str,
) -> NarrativeClaim:
    manifest_version = registry.manifest_version
    if manifest_version is None or not manifest_version.strip():
        raise ValueError("narrative claim registry requires a manifest version")
    return NarrativeClaim.create(
        text=draft.text,
        fact_ids=draft.fact_ids,
        source_claim_ids=draft.source_claim_ids,
        frame_id=frame_id,
        manifest_version=manifest_version,
        fact_registry_version=registry.version,
        claim_type=draft.claim_type,
    )


def _materialize_narrative_artifact(
    draft: NarrativeArtifactDraft,
    *,
    registry: FactRegistry,
    frame_id: str,
    source_claims: tuple[AnalysisClaim | NarrativeClaim, ...],
) -> NarrativeArtifact:
    manifest_version = registry.manifest_version
    if manifest_version is None or not manifest_version.strip():
        raise ValueError("narrative artifact registry requires a manifest version")
    claims = tuple(
        _materialize_narrative_claim(
            claim,
            registry=registry,
            frame_id=frame_id,
        )
        for claim in draft.claims
    )
    return NarrativeArtifact.create(
        content=draft.content,
        claims=claims,
        frame_id=frame_id,
        manifest_version=manifest_version,
        fact_registry_version=registry.version,
    ).validate(registry, source_claims=source_claims)


def _specialist_claims(specialists: SpecialistOutputs) -> tuple[AnalysisClaim, ...]:
    return tuple(
        claim
        for analysis in (
            specialists.stuff,
            specialists.location,
            specialists.runvalue,
            specialists.trends,
        )
        for claim in analysis.claims
    )


def _validate_key_signals(
    signals: KeySignals,
    *,
    specialists: SpecialistOutputs,
    registry: FactRegistry,
    frame_id: str,
) -> KeySignals:
    """Reject signal prose that cannot trace to verified specialist claims."""
    source_claims = {claim.id: claim for claim in _specialist_claims(specialists)}
    manifest_version = registry.manifest_version
    if manifest_version is None or not manifest_version.strip():
        raise ValueError("key signals require a manifest-bound fact registry")
    values: tuple[Signal, ...] = tuple(
        signal
        for signal in (
            signals.top_improvement,
            signals.top_concern,
            *signals.secondary,
        )
        if signal is not None
    )
    for signal in values:
        unknown_claims = tuple(
            claim_id for claim_id in signal.source_claim_ids if claim_id not in source_claims
        )
        if unknown_claims:
            raise ValueError("key signal cites unknown specialist claim IDs: " + ", ".join(unknown_claims))
        cited_claims = tuple(source_claims[claim_id] for claim_id in signal.source_claim_ids)
        for claim in cited_claims:
            claim.validate(registry)
        allowed_fact_ids = {fact_id for claim in cited_claims for fact_id in claim.fact_ids}
        if not set(signal.fact_ids).issubset(allowed_fact_ids):
            raise ValueError("key signal facts are not a subset of its specialist claim evidence")
        facts = registry.validate_fact_ids(
            signal.fact_ids,
            frame_id=frame_id,
            manifest_version=manifest_version,
            claim_type=ClaimType.OBSERVATION,
        )
        samples = tuple(fact.sample_size for fact in facts if fact.sample_size is not None)
        if samples and signal.sample_size != min(samples):
            raise ValueError("key signal sample size does not match cited facts")
        populations = {fact.population for fact in facts}
        if populations != {signal.comparison_population}:
            raise ValueError("key signal cited facts must share its exact comparison population")
    return signals


def _strip_analysis_tag_tokens(
    analysis: SpecialistAnalysis,
    *,
    specialist: str,
    registry: FactRegistry,
) -> SpecialistAnalysis:
    """Remove literal internal tags while preserving each validated claim."""

    def _clean(claim: AnalysisClaim) -> AnalysisClaim:
        text = _strip_tag_tokens(claim.text, specialist=specialist)
        if text == claim.text:
            return claim
        return AnalysisClaim.create(
            text=text,
            fact_ids=claim.fact_ids,
            frame_id=claim.frame_id,
            manifest_version=claim.manifest_version,
            fact_registry_version=claim.fact_registry_version,
            claim_type=claim.claim_type,
            confidence=claim.confidence,
        ).validate(registry)

    return SpecialistAnalysis(
        observations=tuple(_clean(claim) for claim in analysis.observations),
        supported_interpretations=tuple(_clean(claim) for claim in analysis.supported_interpretations),
        limitations=tuple(_clean(claim) for claim in analysis.limitations),
    ).validate(registry)


async def _read_specialist_analysis(
    agent: Agent[None, SpecialistAnalysisDraft],
    prompt: str | UserPrompt,
    *,
    specialist: str,
    registry: FactRegistry,
    frame_id: str,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> SpecialistAnalysis:
    """Read, bind, and validate one structured specialist response."""
    result = await agent.run(**agent_kwargs(prompt, _model_override))
    _record_usage(
        tracker,
        tracker_model,
        result,
        f"specialist:{specialist}",
    )
    return _materialize_specialist_draft(
        result.output,
        specialist=specialist,
        registry=registry,
        frame_id=frame_id,
    )


def _pitch_types(ctx: PitcherContext) -> list[str]:
    """Extract pitch type codes from the arsenal."""
    return [p.pitch_type for p in ctx.arsenal]


def _build_stuff_input(
    ctx: PitcherContext,
    *,
    include_evidence: bool = True,
) -> UserPrompt:
    """Build input for the stuff specialist with pre-computed outlier annotations.

    Each metric is annotated with its delta from league average and an
    explicit NORMAL/OUTLIER tag so the LLM does not need to compute
    z-scores itself.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix (cacheable across same-pitcher reruns) and the data section.
    """
    baselines = ctx.league_baselines
    baseline_lookup = {b.pitch_type: b for b in baselines}

    header_lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    header_lines.append(render_league_baselines(_pitch_types(ctx), ctx.league_baselines))
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
            arm_side_pfx_x = p.window_pfx_x if ctx.throws == "L" else -p.window_pfx_x
            pfx_x_delta = arm_side_pfx_x - b.avg_arm_side_pfx_x
            pfx_x_tag = outlier_tag(
                arm_side_pfx_x,
                b.avg_arm_side_pfx_x,
                b.arm_side_pfx_x_std,
                p.n_pitches_window,
            )
            pfx_z_delta = p.window_pfx_z - b.avg_pfx_z
            pfx_z_tag = outlier_tag(p.window_pfx_z, b.avg_pfx_z, b.pfx_z_std, p.n_pitches_window)
            data_lines.append(
                f"- {p.pitch_name} ({p.pitch_type}):\n"
                f"    Velocity: {p.window_velo:.1f} mph ({velo_delta:+.1f} vs league avg) [{velo_tag}]\n"
                f"    arm_side_pfx_x: {arm_side_pfx_x:.1f} in ({pfx_x_delta:+.1f} vs avg) [{pfx_x_tag}]\n"
                f"    pfx_z: {p.window_pfx_z:.1f} in ({pfx_z_delta:+.1f} vs avg) [{pfx_z_tag}]\n"
                f"    S+: {sp} (season {p.season_s_plus:.0f}, {p.s_plus_delta})"
            )
        else:
            data_lines.append(
                f"- {p.pitch_name} ({p.pitch_type}): "
                f"{p.window_velo:.1f} mph ({p.velo_delta}), "
                f"catcher-view pfx_x {p.window_pfx_x:.1f} in ({p.pfx_x_delta}), "
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

    data_lines.append("\n" + render_calibration_section(ctx, variants=("S",)))
    if include_evidence:
        surfaced = "\n".join((*header_lines, *data_lines))
        data_lines.append(
            "\n"
            + _render_specialist_evidence(
                ctx,
                specialist="stuff",
                surfaced_text=surfaced,
            )
        )
    return ["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]


def _build_location_input(
    ctx: PitcherContext,
    *,
    include_evidence: bool = True,
) -> UserPrompt:
    """Build the location handoff from formal L and emitted region evidence."""
    header = f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"
    evidence = render_location_evidence(
        ctx.formal_location,
        ctx.location_distributions,
    )
    sections = [f"{evidence}\n\n{render_calibration_section(ctx, include_table=False)}"]
    if include_evidence:
        sections.append(
            _render_specialist_evidence(
                ctx,
                specialist="location",
                surfaced_text=f"{header}\n\n{sections[0]}",
            )
        )
    return [header, CachePoint(), "\n\n".join(sections)]


def build_grade_input(ctx: PitcherContext, family: str) -> UserPrompt:
    """Public dispatcher: the grounded specialist input for a grade family.

    S -> stuff input (S+ evidence); L -> formal L+ and location distributions;
    P -> the combined producer-emitted S and L evidence surfaces.
    Reused verbatim from the analysis spine so the ask command and the
    report share one grounded evidence surface.
    """
    if family == "S":
        return _build_stuff_input(ctx)
    if family == "L":
        return _build_location_input(ctx)
    if family == "P":
        return [
            *_build_stuff_input(ctx, include_evidence=False),
            *_build_location_input(ctx, include_evidence=False),
            render_calibration_section(ctx, variants=("P",)),
            _render_specialist_evidence(
                ctx,
                specialist="grade",
                surfaced_text="",
            ),
        ]
    raise ValueError(f"Unknown grade family {family!r}; expected 'S', 'L', or 'P'")


def _build_runvalue_input(
    ctx: PitcherContext,
    *,
    include_evidence: bool = True,
) -> UserPrompt:
    """Build input for the run value specialist from attributions.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix and the attribution data section.
    """
    header_lines = [f"## {ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n"]
    header_lines.append(render_league_baselines(_pitch_types(ctx), ctx.league_baselines))
    header_lines.append("")

    data_lines: list[str] = []
    data_lines.append("## Producer-Emitted P Attribution (raw components reconciled to centered P xRV100)")
    if not ctx.attributions:
        data_lines.append("Attribution unavailable: no producer-emitted rows cover this frame.")
    for attr in ctx.attributions:
        data_lines.extend(
            [
                f"\n### {attr.pitch_name} ({attr.pitch_type})",
                (f"  raw pre-centering xRV100: {attr.raw_total_xrv100:+.3f} [{attr.raw_total_fact_id}]"),
                (
                    f"  league-centering offset: "
                    f"{attr.league_centering_offset_xrv100:+.3f} "
                    f"[{attr.league_centering_offset_fact_id}]"
                ),
                (f"  centered P xRV100: {attr.centered_xrv100_p:+.3f} [{attr.centered_xrv100_p_fact_id}]"),
                (
                    f"  producer manifest: {attr.manifest_id}; "
                    f"run-value table: {attr.run_value_table_version}; "
                    f"reference population: {attr.reference_population}; "
                    f"n={attr.n_pitches}"
                ),
            ]
        )
        for contribution in attr.contributions:
            data_lines.append(
                f"  {contribution.outcome}: {contribution.contribution:+.3f} [{contribution.fact_id}]"
            )
    data_lines.append(
        "\n"
        + render_calibration_section(
            ctx,
            families=("final_outcome",),
        )
    )
    if include_evidence:
        surfaced = "\n".join((*header_lines, *data_lines))
        data_lines.append(
            "\n"
            + _render_specialist_evidence(
                ctx,
                specialist="runvalue",
                surfaced_text=surfaced,
            )
        )
    return ["\n".join(header_lines), CachePoint(), "\n".join(data_lines)]


def _build_trend_input(
    ctx: PitcherContext,
    *,
    frame_comparison: str | None = None,
    include_evidence: bool = True,
) -> UserPrompt:
    """Build input for the trend specialist -- arsenal deltas, release point, hard-hit.

    Returns a UserPrompt list with a CachePoint between the header+baselines
    prefix and the trend data sections.
    """
    baselines = render_league_baselines(_pitch_types(ctx), ctx.league_baselines)
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
        render_calibration_section(ctx, include_table=False),
    ]
    # Cross-season context (when available) — trends specialist gets full YoY section
    if ctx.cross_season_summary is not None or ctx.arsenal_trend is not None:
        data_sections.append(render_yoy_section(ctx))
    if frame_comparison is not None:
        data_sections.append(frame_comparison)
    if include_evidence:
        surfaced = "\n\n".join((*prefix_sections, *data_sections))
        data_sections.append(
            _render_specialist_evidence(
                ctx,
                specialist="trends",
                surfaced_text=surfaced,
            )
        )
    return [
        "\n\n".join(s for s in prefix_sections if s),
        CachePoint(),
        "\n\n".join(s for s in data_sections if s),
    ]


def build_writer_input(
    ctx: PitcherContext,
    specialists: SpecialistOutputs,
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
    parts.append(render_calibration_section(ctx) + "\n")
    if key_signals is not None:
        parts.append(render_key_signals(key_signals) + "\n")
    parts.extend(
        [
            f"## Specialist Analysis 1: Stuff\n{render_specialist_analysis(specialists.stuff)}\n",
            f"## Specialist Analysis 2: Location\n{render_specialist_analysis(specialists.location)}\n",
            f"## Specialist Analysis 3: Run Value\n{render_specialist_analysis(specialists.runvalue)}\n",
            f"## Specialist Analysis 4: Trends\n{render_specialist_analysis(specialists.trends)}",
        ]
    )
    return "\n\n".join(parts)


def _build_signal_input(
    ctx: PitcherContext,
    specialists: SpecialistOutputs,
) -> str:
    """Expose only verified claims and their exact fact metadata to signals."""
    claims = _specialist_claims(specialists)
    return "\n\n".join(
        (
            "## Verified Stuff Claims\n" + render_specialist_analysis(specialists.stuff),
            "## Verified Location Claims\n" + render_specialist_analysis(specialists.location),
            "## Verified Run Value Claims\n" + render_specialist_analysis(specialists.runvalue),
            "## Verified Trends Claims\n" + render_specialist_analysis(specialists.trends),
            _render_fact_catalog(
                ctx.facts,
                fact_ids=(fact_id for claim in claims for fact_id in claim.fact_ids),
            ),
        )
    )


def build_summary_input(
    capsule: str,
    writer_input: str,
    source_claim_ledger: str,
) -> str:
    """Frame the finished report and expose the claim IDs a summary may cite."""
    return (
        "## FINISHED REPORT (summarize THIS; cite its numbers exactly as written)\n"
        f"{capsule}\n\n"
        "## VERIFIED CAPSULE CLAIMS (every summary claim must cite one of these)\n"
        f"{source_claim_ledger}\n\n"
        "## SOURCE ANALYSES (the clean specialist analyses the report was built "
        "from — reference ONLY to recover a metric the report stated "
        "qualitatively; do NOT correct the report's numbers and do NOT add "
        "findings absent from the report)\n"
        f"{writer_input}"
    )


def _render_summary_source_claims(claims: tuple[NarrativeClaim, ...]) -> str:
    """Render final capsule claims with their exact fact and claim identities."""
    return "\n".join(
        f"- [claim:{claim.id}] {claim.text} " + " ".join(f"[{fact_id}]" for fact_id in claim.fact_ids)
        for claim in claims
    )


def _build_specialist_audit_input(ground_truth: str, specialist_output: str) -> str:
    """Build auditor input for a single specialist."""
    return f"## GROUND TRUTH DATA\n{ground_truth}\n\n## SPECIALIST OUTPUT TO AUDIT\n{specialist_output}"


def _build_specialist_revision_input(
    original_input: str,
    specialist_output: str,
    flags: list[AuditFlag],
) -> str:
    """Build a revision prompt for a specialist to fix its own flagged issues."""
    formatted = "\n".join(
        f'- [{f.category}] "{f.claim}" → Data shows: {f.data_shows}. Fix: {f.suggested_fix}' for f in flags
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
    }
    return builders[name](ctx)


def _get_specialist_input_text(
    name: str, ctx: PitcherContext, *, trend_frame_comparison: str | None = None
) -> str:
    """Get specialist data input as plain text (no CachePoints)."""
    return _flatten_prompt(_get_specialist_input(name, ctx, trend_frame_comparison=trend_frame_comparison))


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
        state=VerificationState.PROVIDER_FAILED,
    )


def _tag_leak_flag(specialist: str = "") -> AuditFlag:
    """Synthetic flag: the specialist echoed an internal z-score tag into prose.

    Folds tag-leak repair into the existing audit/revise loop so the specialist
    rewrites the offending sentence (grammar intact) rather than having the
    token deleted by ``_strip_tag_tokens`` (which can leave a hole where the
    model used the tag as a sentence constituent). Cosmetic, not a verification
    failure: TAG_LEAK is not in the gating categories, so it does not trip
    is_unverified/residual_banner — the regex strip remains the last-resort net.
    """
    return AuditFlag(
        category="TAG_LEAK",
        specialist=specialist,
        claim="prose reproduces an internal tag token (e.g. [OUTLIER], [NORMAL])",
        data_shows="bracketed tags are internal annotations, never display text",
        suggested_fix=(
            "rewrite the affected sentence so the judgment is expressed in scout "
            "language, leaving no bracketed tag token in the prose"
        ),
    )


async def audit_and_revise_specialists(
    specialists: SpecialistOutputs,
    specialist_agents: dict[str, Agent[None, SpecialistAnalysisDraft]],
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

    Phase 1.5a: Run 4 per-specialist audits concurrently.
    Phase 1.5b: For any flagged specialist, re-run with audit feedback.
    Phase 1.5c: Re-audit the revised specialists ONCE (bounded — no loop) and
    collect a ``residual`` set of specialists whose revision still flagged or
    whose re-audit itself failed. Their prose is unverified, so a downstream
    fact-check must not treat it as ground truth.

    Args:
        names: Optional subset of specialist names to audit/revise. When
            omitted, all four specialists are audited (current behavior).
            The returned SpecialistOutputs always carries all four fields;
            unlisted specialists pass through unchanged.
        trend_frame_comparison: CHANGES-mode frame-comparison block threaded
            into the trends specialist's audit ground truth so the auditor sees
            the same source the specialist did.

    Returns:
        Tuple of (clean SpecialistOutputs, all collected AuditFlags, residual
        specialist-name set).
    """
    all_names = ["stuff", "location", "runvalue", "trends"]
    audit_names = names if names is not None else all_names

    # Full typed output map (all four) so only validated claims can reach audit.
    outputs: dict[str, SpecialistAnalysis] = {name: getattr(specialists, name) for name in all_names}

    # Build ground truth input only for the specialists we audit.
    ground_truths = {
        name: _get_specialist_input_text(name, ctx, trend_frame_comparison=trend_frame_comparison)
        for name in audit_names
    }

    # Phase 1.5a: Audit all 5 in parallel. Fail closed: a failed audit call
    # (provider error, rate limit) does not pass that specialist through
    # un-audited. It returns (name, None), which the collector below turns
    # into an AUDIT_FAILED sentinel flag on the report — the specialist is
    # never revised against a nonexistent audit result, and the sentinel
    # is visible in the pipeline's audit_flags rather than being silently
    # swallowed.
    async def _audit_one(
        name: str,
        analysis: SpecialistAnalysis,
    ) -> tuple[str, AuditResult | None]:
        try:
            audit_input = _build_specialist_audit_input(
                ground_truths[name],
                render_specialist_analysis(analysis),
            )
            result = await auditor.run(**agent_kwargs(audit_input, _model_override))
            _record_usage(tracker, tracker_model, result, "audit")
            return name, result.output
        except Exception:
            # Fail closed: the auditor crashed, so this specialist's prose was
            # never fact-checked. Signal failure with a None sentinel; the
            # collector surfaces an AUDIT_FAILED flag (visible in audit_flags)
            # without triggering a bogus revision against a nonexistent flag.
            log.error("Audit failed for %s specialist; surfacing AUDIT_FAILED.", name, exc_info=True)
            return name, None

    audit_tasks = [_audit_one(name, outputs[name]) for name in audit_names]
    audit_results = await asyncio.gather(*audit_tasks)

    # Collect all flags, tag with specialist name
    all_flags: list[AuditFlag] = []
    flagged: dict[str, list[AuditFlag]] = {}
    residual: set[str] = set()
    for name, audit_result in audit_results:
        if audit_result is None:
            # Auditor failure is surfaced explicitly and the analysis is
            # replaced with an unavailable value before downstream use.
            all_flags.append(_audit_failed_flag(name))
            residual.add(name)
            continue
        if not audit_result.is_clean:
            for flag in audit_result.flags:
                flag.specialist = name
                all_flags.append(flag)
            flagged[name] = audit_result.flags
            log.info("Audit flagged %s: %d issue(s)", name, len(audit_result.flags))

    # Independently scan the deterministic rendering for leaked internal tags.
    for name in audit_names:
        if _TAG_TOKEN_RE.search(render_specialist_analysis(outputs[name])):
            leak_flag = _tag_leak_flag(name)
            all_flags.append(leak_flag)
            flagged.setdefault(name, []).append(leak_flag)
            log.warning("Tag leak in %s specialist prose; flagging for revision.", name)

    if not flagged:
        log.info("All available specialist audits passed.")
        clean_outputs = dict(outputs)
        for name in residual:
            clean_outputs[name] = empty_specialist_analysis()
        return SpecialistOutputs(**clean_outputs), all_flags, residual

    # Phase 1.5b: Revise flagged specialists in parallel
    log.info("Revising %d flagged specialist(s)...", len(flagged))

    async def _revise_one(
        name: str,
        flags: list[AuditFlag],
    ) -> tuple[str, SpecialistAnalysis]:
        try:
            revision_input = _build_specialist_revision_input(
                ground_truths[name],
                render_specialist_analysis(outputs[name]),
                flags,
            )
            agent = specialist_agents[name]
            result = await agent.run(**agent_kwargs(revision_input, _model_override))
            _record_usage(tracker, tracker_model, result, "revision")
            revised = _materialize_specialist_draft(
                result.output,
                specialist=name,
                registry=ctx.facts,
                frame_id=ctx.frame_id,
            )
            return name, _strip_analysis_tag_tokens(
                revised,
                specialist=name,
                registry=ctx.facts,
            )
        except Exception:
            log.warning(
                "Revision failed for %s specialist, keeping original.",
                name,
                exc_info=True,
            )
            return name, _strip_analysis_tag_tokens(
                outputs[name],
                specialist=name,
                registry=ctx.facts,
            )

    revision_tasks = [_revise_one(name, flags) for name, flags in flagged.items()]
    revisions = await asyncio.gather(*revision_tasks)

    # Apply revisions
    clean_outputs = dict(outputs)
    revised_names: list[str] = []
    for name, revised_analysis in revisions:
        clean_outputs[name] = revised_analysis
        revised_names.append(name)
        log.info("Revised %s specialist.", name)

    # Phase 1.5c: ONE bounded re-audit of the revised specialists (no loop).
    # A revision is never re-checked today, so a fabricated number introduced
    # by the revision ships un-audited. Re-audit the revised text once; any
    # specialist still flagged — or whose re-audit itself raises — is residual:
    # its prose is unverified and must be excluded from the fact-check ground
    # truth. A raising re-audit also surfaces an AUDIT_FAILED sentinel (fail
    # closed, mirroring the first pass).
    # A provider failure or rejected re-audit makes that specialist unavailable
    # to every downstream consumer. Do not let unverified prose enter signals,
    # writer synthesis, or fact-check ground truth.
    reaudit_results = await asyncio.gather(*(_audit_one(name, clean_outputs[name]) for name in revised_names))
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
            log.info("Re-audit still flagged %s: %d issue(s)", name, len(audit_result.flags))

    for name in residual:
        clean_outputs[name] = empty_specialist_analysis()

    return SpecialistOutputs(**clean_outputs), all_flags, residual


async def run_data_audit(
    ground_truth: str,
    answer: str,
    *,
    provider: str = "gemini",
    model_override: Any = None,
) -> AuditResult:
    """Fact-check a single free-form answer against its ground-truth input.

    Reuses the spine's data-auditor agent so a Q&A answer gets the same
    anti-fabrication guard as a report specialist.
    """
    agents = make_pipeline_agents(provider)
    audit_input = _build_specialist_audit_input(ground_truth, answer)
    result = await agents.auditor.run(**agent_kwargs(audit_input, model_override))
    return result.output


# ═══════════════════════════════════════════════════════════════════════
# PROMPT DATA FILE (for traceability)
# ═══════════════════════════════════════════════════════════════════════


def _render_pipeline_data_sections(
    ctx: PitcherContext,
    *,
    prior_ctx: PitcherContext | None = None,
) -> list[str]:
    """Render all pipeline prompt sections as a list of strings.

    Pure rendering helper — no I/O. Used by write_pipeline_data_file and
    by callers that want the rendered text without a disk roundtrip
    (e.g. cli.py --print-prompts).

    The WRITER section renders the single mode-composed writer prompt.
    When prior_ctx is provided, the TRENDS specialist input includes the
    RECENT-vs-PRIOR comparison block; when None (the default), output is
    unchanged from before this parameter existed.
    """
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
        (
            "SPECIALIST 2: LOCATION",
            _LOCATION_SPECIALIST_PROMPT,
            _render_user_prompt(_build_location_input(ctx)),
        ),
        (
            "SPECIALIST 3: RUN VALUE",
            _RUNVALUE_SPECIALIST_PROMPT,
            _render_user_prompt(_build_runvalue_input(ctx)),
        ),
        (
            "SPECIALIST 4: TRENDS",
            _TREND_SPECIALIST_PROMPT,
            _render_user_prompt(_build_trend_input(ctx, frame_comparison=trend_frame_comparison)),
        ),
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
        "all 4 specialist outputs for validation]\n"
    )

    # Signal extractor
    sections.append(f"\n{sep}\nSIGNAL EXTRACTOR\n{sep}\n")
    sections.append(f"## System Prompt\n\n{SIGNAL_EXTRACTOR_PROMPT}\n")
    sections.append("## User Message\n\n[Receives: all 4 specialist outputs (without key signals)]\n")

    # Narrative pipeline: writer + anchor + executive summary
    sections.append(f"\n{sep}\nWRITER\n{sep}\n")
    sections.append(f"## System Prompt\n\n{build_writer_system_prompt(DEFAULT_MODE)}\n")
    sections.append("## User Message\n\n[Receives: key signals + all 4 specialist outputs]\n")

    sections.append(f"\n{sep}\nEXECUTIVE SUMMARY (second step — summarizes the final report)\n{sep}\n")
    sections.append(f"## System Prompt\n\n{_EXECUTIVE_SUMMARY_PROMPT}\n")
    sections.append(
        "## User Message\n\n"
        + build_summary_input(
            "[final report capsule, post anchor-revision]",
            "[writer input: key signals + clean specialist analyses]",
            "[verified final capsule claim IDs and fact IDs]",
        )
        + "\n"
    )

    sections.append(f"\n{sep}\nANCHOR CHECK\n{sep}\n")
    sections.append(f"## System Prompt\n\n{ANCHOR_PROMPT}\n")
    sections.append(
        "## User Message\n\n[Receives: key signals + concatenated specialist outputs + writer capsule]\n"
    )

    return sections


def write_pipeline_data_file(
    ctx: PitcherContext,
    pitcher_id: int,
    provider: str,
    *,
    prior_ctx: PitcherContext | None = None,
) -> tuple[str, str]:
    """Write all pipeline prompts to a data file for end-to-end tracing.

    Dumps every system prompt and user message that would be sent to the
    LLM at each phase of the pipeline.

    Args:
        ctx: Assembled pitcher context.
        pitcher_id: MLB pitcher ID for the filename.
        provider: LLM provider key for the filename.
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

    sections = _render_pipeline_data_sections(ctx, prior_ctx=prior_ctx)
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
    specialists: SpecialistOutputs
    key_signals: KeySignals | None = None
    audit_flags: list[AuditFlag] = []
    anchor_warnings: list[AnchorWarning] = []
    revision_count: int = 0
    capsule_audit_flags: list[AuditFlag] = []
    capsule_revised: bool = False
    value_parity_warnings: list[str] = []
    reader_claim_warnings: list[str] = []
    signals_failed: bool = False
    signals_state: VerificationState = VerificationState.VERIFIED
    residual_specialists: list[str] = []
    analysis_capabilities: AnalysisCapabilities = Field(default_factory=AnalysisCapabilities)
    narrative_fact_ids: tuple[str, ...] = ()
    narrative_artifact: NarrativeArtifact | None = None
    summary_artifact: NarrativeArtifact | None = None
    model_explanation: ModelExplanation | None = None


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


_GATING_ANCHOR_CATEGORIES: tuple[str, ...] = (
    "MISSED_SIGNAL",
    "DIRECTION_ERROR",
    "UNSUPPORTED",
    "OVERSTATED",
)
"""Anchor outcomes that represent correctness or required-primary coverage.

UNDERWEIGHTED remains editorial coverage advice; unsupported, overstated,
directionally wrong, or missing-primary claims cannot carry a Verified stamp.
"""


def is_unverified(result: PipelineResult) -> bool:
    """Whether a mode lacks a publishable, fully validated capsule."""
    return (
        not result.narrative.strip()
        or bool(result.capsule_audit_flags)
        or bool(result.value_parity_warnings)
        or bool(result.reader_claim_warnings)
        or bool(result.residual_specialists)
        or any(w.category in _GATING_ANCHOR_CATEGORIES for w in result.anchor_warnings)
    )


def residual_banner(result: PipelineResult, *, label: str = "REPORT") -> str | None:
    """The loud UNVERIFIED banner for an unverified result, else ``None``.

    ``label`` names the surface (REPORT / CHANGES / RECAP / a digest item) so
    the same wording marks residual flags on every mode.
    """
    if not result.narrative.strip():
        return (
            f"⚠️  {label} UNVERIFIED — no validated capsule was produced. Review diagnostics before retrying."
        )
    if result.value_parity_warnings:
        return (
            f"⚠️  {label} UNVERIFIED — {len(result.value_parity_warnings)} "
            "value-parity warning(s) survived validation. Review before use."
        )
    if result.reader_claim_warnings:
        return (
            f"⚠️  {label} UNVERIFIED — {len(result.reader_claim_warnings)} "
            "reader claim/metric warning(s) survived validation. Review before use."
        )
    if result.residual_specialists:
        specialists = ", ".join(sorted(result.residual_specialists))
        return (
            f"⚠️  {label} UNVERIFIED — unresolved specialist audit/provider "
            f"state remains for: {specialists}. Review before use."
        )
    n = len(result.capsule_audit_flags)
    m = sum(1 for w in result.anchor_warnings if w.category in _GATING_ANCHOR_CATEGORIES)
    if not n and not m:
        return None
    return (
        f"⚠️  {label} UNVERIFIED — {n} flagged claim(s) and/or {m} unresolved "
        "gating anchor warning(s) survived validation. Review before use."
    )


# ═══════════════════════════════════════════════════════════════════════
# AGENT FACTORY
# ═══════════════════════════════════════════════════════════════════════


class PipelineAgents(NamedTuple):
    """All agents used by the multi-agent pipeline."""

    stuff: Agent[None, SpecialistAnalysisDraft]
    location: Agent[None, SpecialistAnalysisDraft]
    runvalue: Agent[None, SpecialistAnalysisDraft]
    trends: Agent[None, SpecialistAnalysisDraft]
    writer: Agent[None, NarrativeArtifactDraft]
    auditor: Agent[None, AuditResult]
    capsule_auditor: Agent[None, AuditResult]
    anchor: Agent[None, AnchorResult]
    summary: Agent[None, NarrativeArtifactDraft]
    signal_extractor: Agent[None, KeySignals]
    mini_model_name: str = ""  # bare model name for UsageTracker calls in the spine

    def specialist_dict(
        self,
    ) -> dict[str, Agent[None, SpecialistAnalysisDraft]]:
        """Return the four specialist agents keyed by name.

        Used to pass specialists to audit_and_revise_specialists. Adding a
        new specialist only requires updating PipelineAgents — callers never
        need to repeat the mapping.
        """
        return {
            "stuff": self.stuff,
            "location": self.location,
            "runvalue": self.runvalue,
            "trends": self.trends,
        }


def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
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
    # requested here. Any settings block below that wants a specific
    # temperature to actually take effect on Claude must also pass
    # disable_thinking=True (see curator._SELECTOR_TEMPERATURE for the
    stuff_settings = make_model_settings(
        provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE
    )
    mini_specialist_settings = make_model_settings(
        provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE, mini=True
    )
    mini_specialist_compact_settings = make_model_settings(
        provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True
    )
    writer_settings = make_model_settings(provider, thinking, 0.7, max_tokens=TOKEN_BUDGET_LARGE)
    checker_settings = make_model_settings(
        provider, cap_thinking(thinking, "low"), 0.1, max_tokens=TOKEN_BUDGET_SMALL, mini=True
    )
    # Capsule auditor (B): checks the finished capsule against ALL ground truth
    # at once — a large input. MEDIUM budget + thinking medium so thinking can't
    # truncate the structured AuditResult (the report-then-summarize truncation
    # lesson); the existing per-specialist auditor stays on SMALL because its
    # input is one specialist's data.
    capsule_auditor_settings = make_model_settings(
        provider, cap_thinking(thinking, "medium"), 0.1, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True
    )
    # signal_extractor does structured cross-specialist extraction from the same
    # large specialist-analyses payload the summarizers see. On Gemini thinking
    # is kept (extraction benefits from reasoning) but the MEDIUM budget gives
    # it headroom so thinking tokens can't truncate the structured KeySignals
    # output; on Claude mini=True already disables thinking, leaving the full
    # MEDIUM budget for output.
    signal_settings = make_model_settings(
        provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True
    )

    # Second-step summarizer (executive summary) distills the finished report
    # from a large grounded input. Thinking is disabled so its tokens don't
    # consume the output budget (which truncated the response); the cap is
    # MEDIUM for headroom.
    def _distillation_settings(temperature: float) -> ModelSettings:
        return make_model_settings(
            provider,
            cap_thinking(thinking, "low"),
            temperature,
            max_tokens=TOKEN_BUDGET_MEDIUM,
            mini=True,
            disable_thinking=True,
        )

    report_summary_settings = _distillation_settings(0.3)

    # Prose agents can load the runtime PitchingPlus interpretation contract.
    # Builder-only data skills never enter model context. The library injects
    # skill names/descriptions into instructions rather than the frozen prompts.
    skills = [skill_toolset()]

    def _specialist(prompt: str) -> Agent[None, SpecialistAnalysisDraft]:
        return Agent(
            model,
            output_type=SpecialistAnalysisDraft,
            system_prompt=prompt + _NO_TAG_ECHO_RULE,
            model_settings=stuff_settings,
            toolsets=skills,
            defer_model_check=True,
        )

    def _mini_specialist(prompt: str) -> Agent[None, SpecialistAnalysisDraft]:
        return Agent(
            mini_model,
            output_type=SpecialistAnalysisDraft,
            system_prompt=prompt + _NO_TAG_ECHO_RULE,
            model_settings=mini_specialist_settings,
            toolsets=skills,
            defer_model_check=True,
        )

    def _mini_specialist_compact(
        prompt: str,
    ) -> Agent[None, SpecialistAnalysisDraft]:
        return Agent(
            mini_model,
            output_type=SpecialistAnalysisDraft,
            system_prompt=prompt + _NO_TAG_ECHO_RULE,
            model_settings=mini_specialist_compact_settings,
            toolsets=skills,
            defer_model_check=True,
        )

    def _writer(prompt: str) -> Agent[None, NarrativeArtifactDraft]:
        # retries=3: a single malformed skills tool call must not kill
        # the structured writer phase.
        return Agent(
            model,
            output_type=NarrativeArtifactDraft,
            system_prompt=f"{prompt}\n\n{_NARRATIVE_ARTIFACT_PROMPT}",
            model_settings=writer_settings,
            toolsets=skills,
            retries=3,
            defer_model_check=True,
        )

    return PipelineAgents(
        stuff=_specialist(_STUFF_SPECIALIST_PROMPT),
        location=_mini_specialist(_LOCATION_SPECIALIST_PROMPT),
        runvalue=_mini_specialist(_RUNVALUE_SPECIALIST_PROMPT),
        trends=_mini_specialist_compact(_TREND_SPECIALIST_PROMPT),
        writer=_writer(build_writer_system_prompt(mode)),
        auditor=Agent(
            mini_model,
            output_type=AuditResult,
            system_prompt=_DATA_AUDITOR_PROMPT,
            model_settings=checker_settings,
            retries=5,
            defer_model_check=True,
        ),
        capsule_auditor=Agent(
            mini_model,
            output_type=AuditResult,
            system_prompt=_CAPSULE_AUDITOR_PROMPT,
            model_settings=capsule_auditor_settings,
            retries=5,
            defer_model_check=True,
        ),
        anchor=Agent(
            mini_model,
            output_type=AnchorResult,
            system_prompt=(
                ANCHOR_PROMPT + "\n\n" + mode.anchor_guidance if mode.anchor_guidance else ANCHOR_PROMPT
            ),
            model_settings=checker_settings,
            retries=3,
            defer_model_check=True,
        ),
        summary=Agent(
            mini_model,
            output_type=NarrativeArtifactDraft,
            system_prompt=f"{_EXECUTIVE_SUMMARY_PROMPT}\n\n{_NARRATIVE_ARTIFACT_PROMPT}",
            model_settings=report_summary_settings,
            retries=3,
            defer_model_check=True,
        ),
        signal_extractor=Agent(
            mini_model,
            output_type=KeySignals,
            system_prompt=SIGNAL_EXTRACTOR_PROMPT,
            model_settings=signal_settings,
            retries=3,
            defer_model_check=True,
        ),
        mini_model_name=model_label(mini_model),
    )


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════


async def run_specialists(
    stuff_agent: Agent[None, SpecialistAnalysisDraft],
    location_agent: Agent[None, SpecialistAnalysisDraft],
    runvalue_agent: Agent[None, SpecialistAnalysisDraft],
    trends_agent: Agent[None, SpecialistAnalysisDraft],
    ctx: PitcherContext,
    _model_override: Any = None,
    *,
    names: list[str] | None = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
    trend_frame_comparison: str | None = None,
) -> SpecialistOutputs:
    """Run the specialists concurrently.

    By default all four run. Pass ``names`` to run only a subset (used by the
    core/tail spine split); unlisted specialists use a typed empty analysis.
    """
    all_inputs = {
        "stuff": (stuff_agent, _build_stuff_input(ctx)),
        "location": (location_agent, _build_location_input(ctx)),
        "runvalue": (runvalue_agent, _build_runvalue_input(ctx)),
        "trends": (
            trends_agent,
            _build_trend_input(ctx, frame_comparison=trend_frame_comparison),
        ),
    }
    selected = list(all_inputs) if names is None else names

    async def _run(
        name: str,
        agent: Agent[None, SpecialistAnalysisDraft],
        prompt: str | UserPrompt,
    ) -> tuple[str, SpecialistAnalysis]:
        analysis = await _read_specialist_analysis(
            agent,
            prompt,
            specialist=name,
            registry=ctx.facts,
            frame_id=ctx.frame_id,
            _model_override=_model_override,
            tracker=tracker,
            tracker_model=tracker_model,
        )
        return name, analysis

    results = await asyncio.gather(*(_run(name, *all_inputs[name]) for name in selected))

    outputs = {name: empty_specialist_analysis() for name in all_inputs}
    for name, analysis in results:
        outputs[name] = analysis
    return SpecialistOutputs(**outputs)


_CORE_SPECIALISTS = ["stuff", "location", "runvalue"]
_TAIL_SPECIALISTS = ["trends"]


async def run_spine_core(
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> CoreContext:
    """Run the frame-agnostic core of the analysis spine.

    Runs the stuff/location/run-value specialists and audits them.
    Frame-agnostic: these specialists read a single window snapshot, so the
    core can be computed once and shared across narration modes. Trends,
    signal extraction, and the anchor check are frame-sensitive — see
    run_spine_tail.
    """
    mini = agents.mini_model_name
    raw = await run_specialists(
        agents.stuff,
        agents.location,
        agents.runvalue,
        agents.trends,
        ctx,
        _model_override,
        names=_CORE_SPECIALISTS,
        tracker=tracker,
        tracker_model=mini,
    )
    clean, flags, residual = await audit_and_revise_specialists(
        raw,
        agents.specialist_dict(),
        agents.auditor,
        ctx,
        _model_override,
        names=_CORE_SPECIALISTS,
        tracker=tracker,
        tracker_model=mini,
    )
    return CoreContext(
        stuff=clean.stuff,
        location=clean.location,
        runvalue=clean.runvalue,
        audit_flags=flags,
        residual_specialists=sorted(residual),
    )


_SPECIALIST_ORDER = {
    "stuff": 0,
    "location": 1,
    "runvalue": 2,
    "trends": 3,
}


def _order_flags(flags: list[AuditFlag]) -> list[AuditFlag]:
    """Sort audit flags into the canonical specialist order.

    The core/tail split collects core flags (stuff/location/run-value)
    then trends flags, so a naive concatenation would place trends
    last. Sorting restores the canonical stuff→location→run-value→trends
    order, keeping run_analysis_spine output identical. Stable, so
    multiple flags from the same specialist keep their relative order.
    """
    return sorted(flags, key=lambda f: _SPECIALIST_ORDER.get(f.specialist, 99))


def _rebind_analysis_registry(
    analysis: SpecialistAnalysis,
    registry: FactRegistry,
) -> SpecialistAnalysis:
    """Rebind clean claims after deterministic evidence extends the registry."""

    def rebind(claim: AnalysisClaim) -> AnalysisClaim:
        return AnalysisClaim.create(
            text=claim.text,
            fact_ids=claim.fact_ids,
            frame_id=claim.frame_id,
            manifest_version=claim.manifest_version,
            fact_registry_version=registry.version,
            claim_type=claim.claim_type,
            confidence=claim.confidence,
        )

    return SpecialistAnalysis(
        observations=tuple(rebind(claim) for claim in analysis.observations),
        supported_interpretations=tuple(rebind(claim) for claim in analysis.supported_interpretations),
        limitations=tuple(rebind(claim) for claim in analysis.limitations),
    ).validate(registry)


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
    core's three specialists plus trends. Takes ``ctx`` explicitly so a later
    phase can re-run the tail on a different temporal frame while reusing a
    single shared core. In this phase the tail runs on the same ctx as the
    core, so output is identical to the pre-split spine.
    """
    mini = agents.mini_model_name
    registry_version = ctx.facts.version
    trend_frame_comparison = (
        render_trend_frame_comparison(build_trend_frame_comparison(ctx, prior_ctx))
        if prior_ctx is not None
        else None
    )
    if ctx.facts.version != registry_version:
        core = core.model_copy(
            update={
                "stuff": _rebind_analysis_registry(core.stuff, ctx.facts),
                "location": _rebind_analysis_registry(core.location, ctx.facts),
                "runvalue": _rebind_analysis_registry(core.runvalue, ctx.facts),
            }
        )
    raw = await run_specialists(
        agents.stuff,
        agents.location,
        agents.runvalue,
        agents.trends,
        ctx,
        _model_override,
        names=_TAIL_SPECIALISTS,
        tracker=tracker,
        tracker_model=mini,
        trend_frame_comparison=trend_frame_comparison,
    )
    merged = SpecialistOutputs(
        stuff=core.stuff,
        location=core.location,
        runvalue=core.runvalue,
        trends=raw.trends,
    )
    specialists, trends_flags, trends_residual = await audit_and_revise_specialists(
        merged,
        agents.specialist_dict(),
        agents.auditor,
        ctx,
        _model_override,
        names=_TAIL_SPECIALISTS,
        tracker=tracker,
        tracker_model=mini,
        trend_frame_comparison=trend_frame_comparison,
    )

    combined_residual = set(core.residual_specialists) | trends_residual
    signals_failed = False
    if combined_residual:
        # Cross-specialist synthesis requires the complete verified handoff.
        # Missing/rejected specialists are not silently replaced with raw facts
        # or generated prose.
        key_signals = None
        signals_state = VerificationState.UNAVAILABLE
    else:
        signal_input = _build_signal_input(ctx, specialists)
        try:
            signal_result = await agents.signal_extractor.run(**agent_kwargs(signal_input, _model_override))
            if tracker is not None:
                u = signal_result.usage()
                tracker.record(mini, u.input_tokens or 0, u.output_tokens or 0, stage="signals")
        except Exception:
            log.warning("Signal extractor provider failed; continuing without signals.", exc_info=True)
            key_signals = None
            signals_failed = True
            signals_state = VerificationState.PROVIDER_FAILED
        else:
            try:
                key_signals = _validate_key_signals(
                    signal_result.output,
                    specialists=specialists,
                    registry=ctx.facts,
                    frame_id=ctx.frame_id,
                )
            except ValueError:
                log.warning("Signal extractor output failed evidence validation.", exc_info=True)
                key_signals = None
                signals_state = VerificationState.REJECTED
            else:
                signals_state = VerificationState.VERIFIED

    return AnalyzedContext(
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=_order_flags(list(core.audit_flags) + trends_flags),
        signals_failed=signals_failed,
        signals_state=signals_state,
        residual_specialists=sorted(combined_residual),
        trend_frame_comparison=trend_frame_comparison,
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
    their audit/revision finish, whereas the pre-split spine ran all four
    specialists (and all four audits) concurrently. The added serial latency is
    the deliberate cost of a reusable core — a later multi-frame mode (CHANGES)
    runs the core once and re-runs only the tail per frame.

    Args:
        ctx: Assembled pitcher context (facts, baselines, arsenal data).
        agents: Pre-built pipeline agents (create once, reuse across picks).
        _model_override: Optional model override for deterministic testing.
        tracker: Optional usage tracker for accumulating per-call token costs.
    """
    if prior_ctx is not None:
        # Materialize comparison evidence before any claim binds to the registry
        # version. The tail recomputes the deterministic rendering idempotently.
        build_trend_frame_comparison(ctx, prior_ctx)
    core = await run_spine_core(
        ctx,
        agents=agents,
        _model_override=_model_override,
        tracker=tracker,
    )
    return await run_spine_tail(
        core,
        ctx,
        agents=agents,
        _model_override=_model_override,
        tracker=tracker,
        prior_ctx=prior_ctx,
    )


async def run_anchor_revision_loop(
    *,
    anchor_agent: Agent[None, AnchorResult],
    writer_agent: Agent[None, NarrativeArtifactDraft],
    synthesis: str,
    capsule: NarrativeArtifactDraft,
    max_revisions: int,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> tuple[NarrativeArtifactDraft, AnchorResult, int]:
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
            **agent_kwargs(build_anchor_message(synthesis, capsule.content), _model_override)
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
                build_revision_message(
                    synthesis,
                    capsule.content,
                    anchor_check.warnings,
                ),
                _model_override,
            )
        )
        _record_usage(tracker, tracker_model, revision_result, "anchor_revision")
        capsule = revision_result.output
        revision_count += 1

    # Exhausted max_revisions without a clean pass — final check captures
    # surviving warnings for the caller to surface.
    final_result = await anchor_agent.run(
        **agent_kwargs(build_anchor_message(synthesis, capsule.content), _model_override)
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
    summary_agent: Agent[None, NarrativeArtifactDraft],
    capsule: NarrativeArtifact | None,
    writer_input: str,
    registry: FactRegistry,
    frame_id: str,
    _model_override: Any = None,
) -> NarrativeArtifact | None:
    """Second-step summarization of the FINISHED capsule.

    Runs the executive summary against the final capsule plus recover-only
    grounding (see build_summary_input). Returns [] without calling the agent
    when the capsule is empty/whitespace. The summarizer catches its own
    failure and degrades to an empty list rather than killing the run.
    """
    if capsule is None or not capsule.content.strip():
        log.warning("Final capsule is unavailable; skipping summarization.")
        return None

    summary_input = build_summary_input(
        capsule.content,
        writer_input,
        _render_summary_source_claims(capsule.claims),
    )

    try:
        result = await summary_agent.run(**agent_kwargs(summary_input, _model_override))
        summary = _materialize_narrative_artifact(
            result.output,
            registry=registry,
            frame_id=frame_id,
            source_claims=capsule.claims,
        )
        summary.validate_summary(registry, final_verified_capsule=capsule)
        return summary
    except Exception:
        log.warning("Executive summary validation failed, skipping.", exc_info=True)
        return None


async def run_capsule_audit(
    *,
    auditor: Agent[None, AuditResult],
    writer_agent: Agent[None, NarrativeArtifactDraft],
    ground_truth: str,
    capsule: NarrativeArtifactDraft,
    max_fact_revisions: int = MAX_FACT_REVISIONS,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> tuple[NarrativeArtifactDraft, list[AuditFlag], bool]:
    """B: fact-check the capsule against ground truth, looping audit → revise →
    re-audit up to ``max_fact_revisions`` times to converge.

    Returns (final_capsule, residual_flags, revised):
      - residual_flags are the issues that REMAIN in final_capsule. Empty means
        the report is verified clean (clean on the first audit, or a revision
        converged). Non-empty means the loop was exhausted with flags still
        standing — the caller should treat the report as UNVERIFIED rather than
        ship it silently.
      - revised is True iff at least one fact-revision was applied.
    Fails closed to an empty capsule whenever no clean verdict is available.

    Args:
        tracker: Optional UsageTracker; when set, each auditor run records
            stage="fact_audit" and each writer revision records
            stage="fact_revision".
        tracker_model: Bare model name passed to tracker.record(). Ignored
            when tracker is None.
    """
    try:
        result = await auditor.run(
            **agent_kwargs(
                build_capsule_audit_input(ground_truth, capsule.content),
                _model_override,
            )
        )
    except Exception:
        # Fail closed: the auditor never produced a verdict, so the capsule
        # cannot be published or reused as evidence.
        log.warning("Capsule auditor failed; withholding unverified report.", exc_info=True)
        return empty_narrative_draft(), [_audit_failed_flag()], False

    _record_usage(tracker, tracker_model, result, "fact_audit")
    flags = result.output.flags

    if not flags:
        return capsule, [], False

    revised = False
    for attempt in range(1, max_fact_revisions + 1):
        log.info(
            "Capsule auditor flagged %d issue(s); fact revision %d/%d.",
            len(flags),
            attempt,
            max_fact_revisions,
        )
        try:
            revision = await writer_agent.run(
                **agent_kwargs(
                    build_fact_revision_message(
                        ground_truth,
                        capsule.content,
                        flags,
                    ),
                    _model_override,
                )
            )
            _record_usage(tracker, tracker_model, revision, "fact_revision")
        except Exception:
            log.warning("Fact revision failed; withholding rejected capsule.", exc_info=True)
            return empty_narrative_draft(), flags, revised

        # Empty output is not a verified revision. Withhold the rejected source
        # capsule instead of publishing it as merely advisory-unverified.
        if not revision.output.content.strip():
            log.warning("Fact revision returned empty output; withholding rejected capsule.")
            return empty_narrative_draft(), flags, revised

        capsule = revision.output
        revised = True

        # Re-audit the revision: it can leave issues unfixed or introduce new
        # ungrounded numbers. The residual is what actually remains.
        try:
            recheck = await auditor.run(
                **agent_kwargs(
                    build_capsule_audit_input(ground_truth, capsule.content),
                    _model_override,
                )
            )
        except Exception:
            log.warning("Capsule re-audit failed; withholding unverified revision.", exc_info=True)
            return empty_narrative_draft(), [*flags, _audit_failed_flag()], revised

        _record_usage(tracker, tracker_model, recheck, "fact_audit")
        flags = recheck.output.flags

        if not flags:
            log.info("Capsule re-audit clean after %d revision(s).", attempt)
            return capsule, [], revised

    log.warning(
        "Capsule fact-check exhausted %d revision(s); %d issue(s) remain.", max_fact_revisions, len(flags)
    )
    return empty_narrative_draft(), flags, revised


@dataclass
class _RenderedCapsule:
    """Result of the shared writer + anchor + capsule-audit core."""

    draft: NarrativeArtifactDraft
    artifact: NarrativeArtifact | None
    writer_input: str
    fact_check_source: str
    anchor_check: AnchorResult
    revision_count: int
    capsule_audit_flags: list[AuditFlag]
    capsule_revised: bool

    @property
    def capsule(self) -> str:
        return self.artifact.content if self.artifact is not None else ""


async def _reconcile_anchor_warnings(
    *,
    anchor_agent: Agent[None, AnchorResult],
    writer_agent: Agent[None, NarrativeArtifactDraft],
    capsule_auditor: Agent[None, AuditResult],
    synthesis: str,
    capsule: NarrativeArtifactDraft,
    fact_check_source: str,
    prior_anchor: AnchorResult,
    remaining: int,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
    tracker_model: str = "",
) -> tuple[NarrativeArtifactDraft, AnchorResult, int]:
    """Re-anchor a fact-revised capsule and reconcile any new warnings.

    A data fact-revision rewrites the capsule against source data, which can
    invalidate the anchor pass captured earlier in `_render_capsule`. Detection
    alone (the old behavior) shipped those warnings as advisory with "Revised 0
    time(s)". This helper instead spends the mode's REMAINING anchor budget on
    reconcile revisions that do NOT touch numeric values (the fact-check already
    verified them), then runs one detection-only capsule re-audit as a
    regression guard: if the reconciled text regresses a verified fact, the
    fact-revised capsule wins and its warnings ship as before. Ground truth
    always outranks the specialist synthesis.

    Returns (final_capsule, merged_anchor_result, reconcile_passes_used).
    """

    def _merge(base: AnchorResult, extra: list[AnchorWarning]) -> AnchorResult:
        seen = {(w.category, w.description) for w in base.warnings}
        merged = list(base.warnings)
        for w in extra:
            key = (w.category, w.description)
            if key not in seen:
                seen.add(key)
                merged.append(w)
        return AnchorResult(warnings=merged)

    # Re-anchor the fact-revised capsule once against the final text.
    recheck = await anchor_agent.run(
        **agent_kwargs(
            build_anchor_message(synthesis, capsule.content),
            _model_override,
        )
    )
    _record_usage(tracker, tracker_model, recheck, "anchor")
    current = recheck.output

    # Rule 1: clean recheck → nothing to reconcile (today's clean path).
    if current.is_clean:
        return capsule, prior_anchor, 0

    # Rule 2: no remaining budget → merge new warnings advisory-only, deduped
    # by (category, description) — exactly today's merge behavior.
    if remaining <= 0:
        return capsule, _merge(prior_anchor, current.warnings), 0

    # Rule 3: spend the remaining budget on prose-only reconcile revisions.
    original = capsule
    original_warnings = list(current.warnings)
    candidate = capsule
    passes = 0
    prev_signature = {(w.category, w.description) for w in current.warnings}

    for _ in range(remaining):
        # build_reconcile_message returns a plain string (no CachePoints) —
        # intentionally uncached. Worst case is anchor_depth passes; revisit
        # if cost calibration shows this matters.
        revision = await writer_agent.run(
            **agent_kwargs(
                build_reconcile_message(
                    synthesis,
                    candidate.content,
                    current.warnings,
                ),
                _model_override,
            )
        )
        _record_usage(tracker, tracker_model, revision, "anchor_revision")
        candidate = revision.output
        passes += 1

        recheck = await anchor_agent.run(
            **agent_kwargs(
                build_anchor_message(synthesis, candidate.content),
                _model_override,
            )
        )
        _record_usage(tracker, tracker_model, recheck, "anchor")
        current = recheck.output
        if current.is_clean:
            break
        signature = {(w.category, w.description) for w in current.warnings}
        if signature == prev_signature:
            # Intentional divergence from run_anchor_revision_loop: reconcile's
            # first anchor check happens before this loop, so a stall here
            # always costs one writer pass (vs. a zero-pass stall there).
            log.info("Reconcile loop stalled (identical warnings); stopping early.")
            break
        prev_signature = signature

    # Rule 4: regression guard — one detection-only (max_fact_revisions=0) audit
    # of the reconciled text against ground truth. If the reconcile prose
    # regressed a verified fact, revert to the fact-revised capsule and ship the
    # original recheck warnings as advisory. Ground truth wins.
    _, guard_flags, _ = await run_capsule_audit(
        auditor=capsule_auditor,
        writer_agent=writer_agent,
        ground_truth=fact_check_source,
        capsule=candidate,
        max_fact_revisions=0,
        _model_override=_model_override,
        tracker=tracker,
        tracker_model=tracker_model,
    )
    if guard_flags:
        log.warning(
            "Reconcile revision regressed ground-truth facts (%d flag(s)); "
            "reverting to the fact-revised capsule and shipping anchor "
            "warnings as advisory.",
            len(guard_flags),
        )
        return original, _merge(prior_anchor, original_warnings), passes

    return candidate, _merge(prior_anchor, current.warnings), passes


async def _render_capsule(
    ctx: PitcherContext,
    analyzed: AnalyzedContext,
    *,
    agents: PipelineAgents,
    anchor_depth: int,
    fact_depth: int,
    overlay: str | None = None,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> _RenderedCapsule:
    """Writer + anchor + capsule-audit core shared by report and recap.

    The generated artifact is buffered and validated before any deterministic
    reader-facing model explanation is composed outside it.
    """
    specialists = analyzed.specialists
    key_signals = analyzed.key_signals

    # Phase 2: Writer streams the initial capsule from clean specialist
    # outputs + key signals. Summarization is a separate second step that
    # runs after the anchor revision loop (see _run_summaries below).
    writer_input = build_writer_input(
        ctx,
        specialists,
        key_signals=key_signals,
    )
    if overlay:
        writer_input = f"{overlay}\n\n{writer_input}"
    writer_kwargs = agent_kwargs(writer_input, _model_override)

    _res = await agents.writer.run(**writer_kwargs)
    capsule = _res.output

    # Anchor check + revision loop
    specialist_synthesis = (
        f"STUFF:\n{render_specialist_analysis(specialists.stuff)}\n\n"
        f"LOCATION:\n{render_specialist_analysis(specialists.location)}\n\n"
        f"RUN VALUE:\n{render_specialist_analysis(specialists.runvalue)}\n\n"
        f"TRENDS:\n{render_specialist_analysis(specialists.trends)}"
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

    # Fact-check the draft against producer-backed ground truth only. Generated
    # specialist and Key Signal prose can prioritize claims, but never becomes
    # factual authority.
    log.info("Fact-checking the capsule against ground truth...")
    fact_check_source = _build_parity_union(
        ctx,
        specialists,
        key_signals,
        exclude=frozenset(analyzed.residual_specialists),
        trend_frame_comparison=analyzed.trend_frame_comparison,
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

    # A fact revision creates a new artifact version, so the anchor result for
    # the pre-revision text is stale. Re-anchor the rewritten capsule; a
    # provider failure cannot reuse the prior verdict and therefore fails
    # closed.
    if capsule_revised and capsule.content.strip() and not capsule_audit_flags:
        try:
            capsule, anchor_check, reconcile_passes = await _reconcile_anchor_warnings(
                anchor_agent=agents.anchor,
                writer_agent=agents.writer,
                capsule_auditor=agents.capsule_auditor,
                synthesis=synthesis,
                capsule=capsule,
                fact_check_source=fact_check_source,
                prior_anchor=anchor_check,
                remaining=max(anchor_depth - revision_count, 0),
                _model_override=_model_override,
                tracker=tracker,
                tracker_model=agents.mini_model_name,
            )
            # Reconcile passes are anchor-budget revisions: count them so the
            # CLI's "Revised N time(s)" reflects reconciled runs. The tuple
            # assignment above is atomic w.r.t. an await failure, so on
            # exception nothing here has been touched.
            revision_count += reconcile_passes
        except Exception:
            log.warning(
                "Post-fact-revision anchor reconcile failed; withholding stale artifact.",
                exc_info=True,
            )
            capsule = empty_narrative_draft()
            capsule_audit_flags.append(_audit_failed_flag("anchor"))

    artifact: NarrativeArtifact | None = None
    if capsule.content.strip() and not capsule_audit_flags:
        try:
            artifact = _materialize_narrative_artifact(
                capsule,
                registry=ctx.facts,
                frame_id=ctx.frame_id,
                source_claims=_specialist_claims(specialists),
            )
        except ValueError as exc:
            log.warning("Narrative provenance validation failed: %s", exc)
            capsule_audit_flags.append(
                AuditFlag(
                    category="CITATION_INVALID",
                    claim="The reader artifact did not validate against its cited claims.",
                    data_shows=str(exc),
                    suggested_fix="Regenerate with same-frame fact and source-claim IDs.",
                    state=VerificationState.REJECTED,
                )
            )
            capsule = empty_narrative_draft()

    return _RenderedCapsule(
        draft=capsule,
        artifact=artifact,
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
    pick: CurationPick | None = None,
    _model_override: Any = None,
    tracker: UsageTracker | None = None,
) -> PipelineResult:
    """Render a Mode RECAP brief from a pre-computed AnalyzedContext.

    Reuses the shared buffered writer and validation core. RECAP intentionally
    omits the separate deterministic model explanation. A morning pick may
    prepend its editorial angle without changing evidence validation.
    """
    overlay = build_recap_overlay(angle=pick.angle, category=pick.category) if pick is not None else None
    rc = await _render_capsule(
        ctx,
        analyzed,
        agents=agents,
        anchor_depth=RECAP.validation.anchor_depth,
        fact_depth=RECAP.validation.fact_depth,
        overlay=overlay,
        _model_override=_model_override,
        tracker=tracker,
    )
    value_parity = check_value_parity(rc.capsule, rc.fact_check_source)
    analysis_capabilities, _ = _reader_claim_provenance(
        ctx,
        rc.capsule,
    )
    narrative_fact_ids = (
        tuple(sorted({fact_id for claim in rc.artifact.claims for fact_id in claim.fact_ids}))
        if rc.artifact is not None
        else ()
    )
    reader_claim_warnings = _reader_guard_warnings(
        rc.capsule,
        artifact=rc.artifact,
        capabilities=analysis_capabilities,
    )
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
        reader_claim_warnings=reader_claim_warnings,
        signals_failed=analyzed.signals_failed,
        signals_state=analyzed.signals_state,
        residual_specialists=analyzed.residual_specialists,
        analysis_capabilities=analysis_capabilities,
        narrative_fact_ids=narrative_fact_ids,
        narrative_artifact=rc.artifact,
    )


async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    mode: NarrationMode = DEFAULT_MODE,
    explain_model: bool = True,
    _model_override: Any = None,
    prior_ctx: PitcherContext | None = None,
) -> PipelineResult:
    """Async core of the multi-agent pipeline.

    Phase 1: 4 specialists run concurrently.
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 1.75: Signal extractor identifies cross-specialist patterns.
    Phase 2: Writer composes capsule from specialist outputs + key signals.
    Phase 2.5: Anchor check + revision loop.
    """
    agents = make_pipeline_agents(provider, thinking, mode)

    # Phases 1 → 1.75: specialist → audit → signal extraction
    log.info("Running analysis spine...")
    analyzed = await run_analysis_spine(
        ctx,
        agents=agents,
        _model_override=_model_override,
        prior_ctx=prior_ctx,
    )
    specialists = analyzed.specialists
    audit_flags = analyzed.audit_flags
    key_signals = analyzed.key_signals
    log.info("Analysis spine complete.")

    rc = await _render_capsule(
        ctx,
        analyzed,
        agents=agents,
        anchor_depth=mode.validation.anchor_depth,
        fact_depth=mode.validation.fact_depth,
        overlay=None,
        _model_override=_model_override,
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
    # so distilling it further would duplicate (and cost an extra agent call).
    summary_artifact: NarrativeArtifact | None = None
    if mode.distill and rc.artifact is not None:
        log.info("Writing executive summary from the final report...")
        summary_artifact = await _run_summaries(
            summary_agent=agents.summary,
            capsule=rc.artifact,
            writer_input=writer_input,
            registry=ctx.facts,
            frame_id=ctx.frame_id,
            _model_override=_model_override,
        )
        summary_bullets = (
            _parse_summary_bullets(summary_artifact.content) if summary_artifact is not None else []
        )
        summary_parity = check_value_parity(
            summary_artifact.content if summary_artifact is not None else "",
            fact_check_source,
        )
        value_parity_warnings = [f"[capsule] {w}" for w in value_parity.unmatched] + [
            f"[summary] {w}" for w in summary_parity.unmatched
        ]
    else:
        summary_bullets = []
        value_parity_warnings = [f"[capsule] {w}" for w in value_parity.unmatched]

    analysis_capabilities, _ = _reader_claim_provenance(ctx, capsule)
    narrative_fact_ids = (
        tuple(sorted({fact_id for claim in rc.artifact.claims for fact_id in claim.fact_ids}))
        if rc.artifact is not None
        else ()
    )
    reader_claim_warnings = _publication_reader_guard_warnings(
        capsule=capsule,
        capsule_artifact=rc.artifact,
        summary_artifact=summary_artifact,
        capabilities=analysis_capabilities,
    )
    producer_identity = getattr(ctx, "producer_identity", None)
    producer_semantics = (
        ProducerModelSemantics.from_identity(
            producer_identity,
            artifact_grains=frozenset(getattr(ctx, "producer_artifact_grains", ())),
        )
        if producer_identity is not None
        else None
    )
    model_explanation = (
        render_model_explanation(
            mode.id,
            producer_semantics=producer_semantics,
            calibration=ctx.calibration,
        )
        if explain_model and mode.explains_model
        else None
    )
    rendered_narrative = compose_model_explanation(capsule, model_explanation)
    return PipelineResult(
        narrative=rendered_narrative,
        executive_summary=summary_bullets,
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=audit_flags,
        anchor_warnings=anchor_check.warnings,
        revision_count=revision_count,
        capsule_audit_flags=capsule_audit_flags,
        capsule_revised=capsule_revised,
        value_parity_warnings=value_parity_warnings,
        reader_claim_warnings=reader_claim_warnings,
        signals_failed=analyzed.signals_failed,
        signals_state=analyzed.signals_state,
        residual_specialists=analyzed.residual_specialists,
        analysis_capabilities=analysis_capabilities,
        narrative_fact_ids=narrative_fact_ids,
        narrative_artifact=rc.artifact,
        summary_artifact=summary_artifact,
        model_explanation=model_explanation,
    )


def generate_pipeline_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    mode: NarrationMode = DEFAULT_MODE,
    explain_model: bool = True,
    _model_override: Any = None,
    prior_ctx: PitcherContext | None = None,
) -> PipelineResult:
    """Generate a report using the specialist→auditor→writer multi-agent pipeline.

    Phase 1: 4 specialists run concurrently (silent).
    Phase 1.5: Data auditor validates specialist outputs against ground truth.
    Phase 1.75: Signal extractor identifies cross-specialist patterns.
    Phase 2: Writer composes capsule from specialist outputs + key signals (streamed).
    Phase 2.5: Anchor check + revision loop.

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key.
        thinking: Thinking effort level.
        mode: Narration mode controlling writer prompt selection.
        _model_override: Optional model override for testing.

    Returns:
        PipelineResult with narrative, specialist outputs, and anchor warnings.
    """
    return asyncio.run(
        _run_pipeline(
            ctx,
            provider=provider,
            thinking=thinking,
            mode=mode,
            explain_model=explain_model,
            _model_override=_model_override,
            prior_ctx=prior_ctx,
        )
    )


def run_narration_modes(
    ctx: PitcherContext,
    *,
    modes: list[NarrationMode] | None = None,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    explain_model: bool = True,
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
        _model_override: Optional model override for testing.
        prior_ctx: Optional prior-window context; forwarded only to modes
            whose temporal_frame includes PRIOR (CHANGES). None for
            report/recap.

    Returns:
        Mapping of mode id -> PipelineResult, insertion-ordered by ``modes``.
    """
    selected = modes if modes is not None else [DEFAULT_MODE]
    if prior_ctx is not None and any(TemporalFrame.PRIOR in mode.temporal_frame for mode in selected):
        # Stabilize the shared registry before the first mode binds claims to
        # its version. CHANGES then reads the already-materialized facts
        # idempotently instead of invalidating an earlier REPORT artifact.
        build_trend_frame_comparison(ctx, prior_ctx)
    results: dict[str, PipelineResult] = {}
    for mode in selected:
        # Dedupe by mode id: a repeated mode (e.g. --mode report,report) must
        # not re-run the whole LLM pipeline and stream the report twice.
        if mode.id in results:
            continue
        mode_prior = prior_ctx if TemporalFrame.PRIOR in mode.temporal_frame else None
        results[mode.id] = generate_pipeline_streaming(
            ctx,
            provider=provider,
            thinking=thinking,
            mode=mode,
            explain_model=explain_model,
            _model_override=_model_override,
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
    unsupported_claim_warnings: list[str] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True only when metric, outcome-stat, and claim checks are clean."""
        return not (self.unknown_metrics or self.outcome_stat_warnings or self.unsupported_claim_warnings)


def _reader_guard_warnings(
    report_text: str,
    *,
    artifact: NarrativeArtifact | None,
    capabilities: AnalysisCapabilities,
) -> list[str]:
    """Flatten exact materialized-claim failures into gating diagnostics."""
    if not report_text.strip() or artifact is None:
        return ["No generated capsule was available for reader-claim validation."]
    report = check_hallucinated_metrics(
        report_text,
        capabilities=capabilities,
        reader_claims=artifact.claims,
    )
    return [
        *(f"Unknown metric: {metric}" for metric in report.unknown_metrics),
        *(f"Unsupported outcome statistic: {metric}" for metric in report.outcome_stat_warnings),
        *report.unsupported_claim_warnings,
    ]


def _publication_reader_guard_warnings(
    *,
    capsule: str,
    capsule_artifact: NarrativeArtifact | None,
    summary_artifact: NarrativeArtifact | None,
    capabilities: AnalysisCapabilities,
) -> list[str]:
    """Gate every generated reader artifact, including distilled summaries."""
    warnings = _reader_guard_warnings(
        capsule,
        artifact=capsule_artifact,
        capabilities=capabilities,
    )
    if summary_artifact is not None:
        warnings.extend(
            f"[summary] {warning}"
            for warning in _reader_guard_warnings(
                summary_artifact.content,
                artifact=summary_artifact,
                capabilities=capabilities,
            )
        )
    return warnings


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


@dataclass(frozen=True)
class _GuardClaim:
    id: str
    text: str
    fact_ids: tuple[str, ...]


def check_hallucinated_metrics(
    report_text: str,
    *,
    capabilities: AnalysisCapabilities | None = None,
    cited_fact_ids: tuple[str, ...] = (),
    reader_claims: Iterable[NarrativeClaim] = (),
) -> HallucinationReport:
    """Find unknown metrics, discouraged stats, and unsupported claim classes.

    Capability-gated language is accepted only when the matching capability is
    AVAILABLE and its exact evidence fact ID appears in ``cited_fact_ids``.

    Args:
        report_text: The LLM-generated report text. Must be a non-empty
            string — an empty narrative is a pipeline failure, not a
            "clean" report, so the caller should check before invoking.

    Returns:
        HallucinationReport with all reader-boundary warnings.

    Raises:
        TypeError: If report_text is not a string.
        ValueError: If report_text is empty. An empty narrative means the
            pipeline produced nothing to check — a misleading `is_clean`
            result would hide that failure, so we fail loudly.
    """
    if not isinstance(report_text, str):
        raise TypeError(f"report_text must be str, got {type(report_text).__name__}")
    if not report_text:
        raise ValueError(
            "report_text is empty — cannot check hallucinations on an "
            "empty narrative (likely a pipeline failure)"
        )

    found = set(_METRIC_PATTERN.findall(report_text))

    def _is_known(metric: str) -> bool:
        if metric in _KNOWN_METRICS or metric in _TRADITIONAL_STATS:
            return True
        # Tolerate Stuff/Pitch-side variant suffixes (xRV100_S, xWhiff_P) when
        # the base metric is known. The original token is still reported if the
        # base is genuinely unknown, so faithful flagging is preserved.
        return _VARIANT_SUFFIX.sub("", metric) in _KNOWN_METRICS

    unknown = sorted(m for m in found if not _is_known(m))

    traditional_found = set(_TRADITIONAL_PATTERN.findall(report_text))
    outcome_warnings = sorted(traditional_found & _TRADITIONAL_STATS)
    materialized = tuple(reader_claims)
    guarded_claims: Iterable[NarrativeClaim | _GuardClaim] = (
        materialized
        if materialized
        else (_GuardClaim(id="unmaterialized-reader-text", text=report_text, fact_ids=cited_fact_ids),)
    )
    unsupported_claim_warnings = find_unsupported_claims(
        guarded_claims,
        capabilities=capabilities,
    )

    return HallucinationReport(
        unknown_metrics=unknown,
        outcome_stat_warnings=outcome_warnings,
        unsupported_claim_warnings=unsupported_claim_warnings,
    )
