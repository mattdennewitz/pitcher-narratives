"""Five-phase report generation pipeline.

Phase 1 (Synthesizer): Extracts signal from noise — structured bullet
points of key findings, deltas, and trends. No narrative.

Phase 2 (Editor): Weaves those facts into a pragmatic, two-paragraph
capsule with clear projection. Elite sabermetric analyst voice.

Phase 2.5 (Anchor Check): Verifies the capsule is faithful to the
synthesis — flags missed key signals, unsupported claims, and
directional inversions. Prints warnings to stderr.

Phase 3 (Hook Writer): Distills the editor's capsule into a 1-2
sentence social media hook for front-office audiences.

Phase 4 (Fantasy Analyst): Produces 3 fantasy baseball insights
from the capsule with specific metric citations.
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
for front offices, advanced fantasy players, and data-driven fans. Your \
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
- Ignore traditional outcome stats like Wins and basic ERA unless \
provided as context. Base analysis on underlying metrics.
- No bullet points. No headers. No introductory fluff.
- Start immediately with the analysis. Your first sentence should be \
about the pitcher's stuff, not about "looking at the data."
- Be direct without being dismissive or alarmist."""


_AgentTuple = tuple[Agent[None, str], Agent[None, str], Agent[None, str], Agent[None, str], Agent[None, str]]
_agent_cache: dict[tuple[str, ThinkingEffort], _AgentTuple] = {}


def _make_agents(
    provider: str = "openai",
    thinking: ThinkingEffort = "high",
) -> _AgentTuple:
    """Create (or return cached) five pipeline agents for the given provider and thinking level."""
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
    prompts = (_SYNTHESIZER_PROMPT, _EDITOR_PROMPT, _HOOK_PROMPT, _FANTASY_PROMPT, _ANCHOR_PROMPT)
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
- Write as an analyst reporting news, not as a manager issuing roster moves.
- Lead with the fact or trend, then explain why it matters for fantasy.
- Frame implications as things to monitor ("keep an eye on," "worth watching") \
rather than directives ("pick him up," "move him to the bench").
- Cite one specific metric per bullet (P+, velocity delta, usage shift, \
platoon split, workload flag).
- No run-on sentences. No semicolons joining two thoughts. One idea per \
bullet.

What matters for fantasy: ownership changes, streaming value, matchup \
dependency, injury/workload red flags, category impact (Ks, ERA, WHIP).

Format: exactly 3 lines, each starting with "- ". Plain text — no bold, \
no labels, no prefixes. Just the insight. Nothing else — no intro, no \
summary, no headers."""


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2.5: THE ANCHOR CHECK (FACT-CHECKER)
# ═══════════════════════════════════════════════════════════════════════

_ANCHOR_PROMPT = """\
You are a fact-checker for a baseball analytics newsletter. You receive \
two documents: the data analyst's structured briefing (the synthesis) \
and the editor's finished narrative (the capsule). Your job is to verify \
that the capsule is faithfully anchored to the synthesis.

Check for these specific problems:

1. Missed Key Signals: The synthesis has a "Key Signal" section with the \
most important improvement, concern, and development pitch. If the capsule \
ignores any of these entirely, flag it.

2. Unsupported Claims: If the capsule states a metric, trend, or fact \
that does not appear anywhere in the synthesis, flag it. The capsule \
should not invent data.

3. Directional Errors: If the synthesis says a metric went up and the \
capsule says it went down (or vice versa), flag it.

4. Overstated Confidence: If the synthesis flags something as small \
sample or uncertain, but the capsule presents it as definitive, flag it.

OUTPUT FORMAT:
- If everything checks out, respond with exactly: CLEAN
- If there are problems, list each one on its own line starting with \
the problem type in brackets:
  [MISSED SIGNAL] The synthesis flagged X as the key concern but the capsule does not mention it.
  [UNSUPPORTED] The capsule claims X but this does not appear in the synthesis.
  [DIRECTION ERROR] The synthesis says X went up but the capsule says it went down.
  [OVERSTATED] The synthesis notes small sample on X but the capsule presents it as definitive.

Be concise. One line per issue. No preamble, no summary."""


class ReportResult(BaseModel):
    """Structured output from the multi-phase report pipeline."""

    narrative: str
    social_hook: str
    fantasy_insights: str
    anchor_warnings: list[str]


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
    """Build the Phase 2 user message with cache breakpoint after synthesis."""
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Key Findings From Data Analysis\n{synthesis}",
        CachePoint(),
        "Write the two-paragraph scouting capsule now.",
    ]


def _build_anchor_message(synthesis: str, capsule: str) -> _UserPrompt:
    """Build the Phase 2.5 user message for the anchor check."""
    return [
        f"## Synthesis (Data Analyst's Briefing)\n{synthesis}",
        CachePoint(),
        f"## Capsule (Editor's Narrative)\n{capsule}\n\n"
        "Check the capsule against the synthesis. Report any issues or respond CLEAN.",
    ]


def _build_hook_message(ctx: PitcherContext, capsule: str) -> _UserPrompt:
    """Build the Phase 3 user message from the editor's capsule."""
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Scouting Capsule\n{capsule}",
        CachePoint(),
        "Write one social media hook (1-2 sentences). Focus on the single most notable change.",
    ]


def _build_fantasy_message(ctx: PitcherContext, capsule: str) -> _UserPrompt:
    """Build the Phase 4 user message from the editor's capsule."""
    return [
        f"## Pitcher\n{ctx.pitcher_name} ({ctx.throws}HP, {ctx.role})\n\n"
        f"## Scouting Capsule\n{capsule}",
        CachePoint(),
        "Write exactly 3 bullet points of fantasy baseball insights. "
        "Each bullet should flag what to watch and cite a specific metric or trend.",
    ]


def _render_user_prompt(parts: _UserPrompt) -> str:
    """Render a user prompt (with CachePoints) as readable text."""
    return "\n".join("  ── [cache breakpoint] ──" if isinstance(p, CachePoint) else p for p in parts)


def _build_all_phases(ctx: PitcherContext) -> list[tuple[str, str, _UserPrompt]]:
    """Build (label, system_prompt, user_prompt) for all 5 phases."""
    synth_placeholder = "<synthesis output would go here>"
    capsule_placeholder = "<editor capsule would go here>"
    return [
        ("PHASE 1: SYNTHESIZER", _SYNTHESIZER_PROMPT, _build_synthesizer_message(ctx)),
        ("PHASE 2: EDITOR", _EDITOR_PROMPT, _build_editor_message(ctx, synth_placeholder)),
        (
            "PHASE 2.5: ANCHOR CHECK", _ANCHOR_PROMPT,
            _build_anchor_message(synth_placeholder, capsule_placeholder),
        ),
        ("PHASE 3: HOOK WRITER", _HOOK_PROMPT, _build_hook_message(ctx, capsule_placeholder)),
        ("PHASE 4: FANTASY ANALYST", _FANTASY_PROMPT, _build_fantasy_message(ctx, capsule_placeholder)),
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
    """Generate a five-phase scouting report and stream the editorial output.

    Phase 1 (Synthesizer): Extracts key findings as structured bullets.
    Phase 2 (Editor): Writes the final two-paragraph capsule from synthesis.
    Phase 2.5 (Anchor Check): Verifies capsule is faithful to synthesis.
    Phase 3 (Hook Writer): Distills the capsule into a 1-2 sentence social hook.
    Phase 4 (Fantasy Analyst): Produces 3 fantasy baseball bullets from the capsule.

    Phases 3 and 4 derive from the editor's capsule (not the raw synthesis),
    so they inherit the editor's plausibility filters and metric curation.

    Only Phase 2 output is streamed to stdout. All other phases run silently.

    Args:
        ctx: Assembled pitcher context.
        provider: LLM provider key ('openai' or 'claude').
        thinking: Thinking effort level.
        _model_override: Optional model override for testing (e.g., TestModel).

    Returns:
        ReportResult with narrative, social_hook, fantasy_insights, and anchor_warnings.
    """
    synthesizer, editor, hook_writer, fantasy_analyst, anchor_checker = _make_agents(provider, thinking)

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

    capsule = "".join(chunks)

    # Phase 2.5: Anchor check — verify capsule is faithful to synthesis
    anchor_kwargs: dict[str, Any] = {
        "user_prompt": _build_anchor_message(synthesis, capsule),
    }
    if _model_override is not None:
        anchor_kwargs["model"] = _model_override

    anchor_result = anchor_checker.run_sync(**anchor_kwargs)
    anchor_output = anchor_result.output.strip()
    anchor_warnings: list[str] = []
    if anchor_output != "CLEAN":
        anchor_warnings = [line.strip() for line in anchor_output.splitlines() if line.strip()]

    # Phase 3: Social media hook (silent) — derived from capsule, not synthesis
    hook_kwargs: dict[str, Any] = {
        "user_prompt": _build_hook_message(ctx, capsule),
    }
    if _model_override is not None:
        hook_kwargs["model"] = _model_override

    hook_result = hook_writer.run_sync(**hook_kwargs)

    # Phase 4: Fantasy analyst (silent) — derived from capsule, not synthesis
    fantasy_kwargs: dict[str, Any] = {
        "user_prompt": _build_fantasy_message(ctx, capsule),
    }
    if _model_override is not None:
        fantasy_kwargs["model"] = _model_override

    fantasy_result = fantasy_analyst.run_sync(**fantasy_kwargs)

    return ReportResult(
        narrative=capsule,
        social_hook=hook_result.output,
        fantasy_insights=fantasy_result.output,
        anchor_warnings=anchor_warnings,
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
