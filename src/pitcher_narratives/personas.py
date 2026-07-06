"""Writer-voice composition for the pitcher-narratives writer agent.

A single field-facing analyst voice writes every deliverable; the narration
mode selects the output shape. The pieces compose at build time:

- ``WRITER_VOICE`` is the one writer voice — tone/register and how deep to go
  when explaining the grading model.
- ``NarrationMode`` carries the per-deliverable output target — length,
  structure, and the input-framing that tells the writer what material it is
  synthesizing (a bundle of specialist analyses, with or without a model-
  teaching mandate).
- ``SHARED_WRITER_BASE`` holds the universal analytical rules every composed
  writer prompt must obey, exactly once.
- ``_SYNTHESIS_FRAMING`` holds the framing shared by the specialist-synthesis
  modes (report/changes writers).

``build_writer_system_prompt(mode)`` composes:
``universal base + mode input framing + writer voice + mode structure``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from pitcher_narratives.config import MAX_FACT_REVISIONS, MAX_REVISIONS
from pitcher_narratives.temporal import TemporalFrame

__all__ = [
    "CHANGES",
    "DEFAULT_MODE",
    "NARRATION_MODES",
    "RECAP",
    "REPORT",
    "SHARED_WRITER_BASE",
    "WRITER_VOICE",
    "NarrationMode",
    "ValidationPolicy",
    "build_writer_system_prompt",
    "get_narration_mode",
]


# ═══════════════════════════════════════════════════════════════════════
# UNIVERSAL ANALYTICAL RULES — applies to every composed writer prompt
# ═══════════════════════════════════════════════════════════════════════

SHARED_WRITER_BASE = """\
ANALYTICAL RULES (these apply no matter what you are writing):
- Use ONLY the data provided to you. Do not invent metrics.
- DIRECTIONAL CONSISTENCY: If the analysis says a pitch is effective \
(negative xRV100, S+ above 100, strong whiff rate), do not flip the \
narrative to negative. If the analysis says a pitch is weak, do not \
spin it as a strength. Preserve the direction of each assessment.
- Surface arm slot shape insight. When a pitch's movement is tied to its \
arm slot (a DEAD ZONE fastball, ride above slot expectation), that is \
high-value mechanism evidence -- work it into the narrative rather than \
dropping it.
- Scale confidence to sample size. Small windows get tentative language.
- TEMPORAL GROUNDING: The data includes a "Temporal Context" section \
with a prior-year relevance level. Follow it. When relevance is LOW, \
prior-season workload does not drive narrative. When relevance is HIGH, \
prior year is residual context but two seasons are NOT a continuous \
timeline. Do not hallucinate cumulative fatigue across an offseason.
- Never use: "degradation," "binary," "profiles as," "dominant," \
"elite," "massive spike."\
"""


# ═══════════════════════════════════════════════════════════════════════
# SYNTHESIS-INPUT FRAMING — shared by the specialist-synthesis modes
# ═══════════════════════════════════════════════════════════════════════

_SYNTHESIS_RULES = """\
INPUT: Five specialist analyses of a pitcher's recent window:
1. Pitch quality analysis — physical pitch characteristics and S+ grades
2. Location analysis — P vs S location impact per pitch
3. Run value decomposition — which outcomes drive each pitch's value
4. Trend analysis — what has changed vs season baseline
5. Game shape — how effectiveness changes within a game (TTO, velocity arc)

CRITICAL: These are INGREDIENTS, not sections to preserve. The specialists \
did the analysis; you do the writing. You must:
- Find the thread. What is the single most important story across \
all five analyses? Maybe the pitch characteristics are fine but \
location is killing a pitch. Maybe a velocity trend is changing the \
entire arsenal picture. Maybe one pitch is carrying the whole profile.
- Write as one voice. The reader should not be able to tell that five \
separate analysts contributed. No section breaks, no "meanwhile," no \
"turning to the location data."
- Drop what's redundant. If two specialists agree a pitch grades out \
well, say it once with the best evidence from either.
- Prioritize the surprising. If three specialists agree on something \
obvious, give it one sentence. If one specialist found something \
the others didn't highlight, that's probably the lead.
- Use the Key Signals. The Key Signals section contains cross-specialist \
patterns identified by a signal extractor. Primary signals (Top \
Improvement, Top Concern) are your narrative priorities — your lead \
must address one. Secondary signals (Specialist Tension, Connected \
Changes, etc.) are high-value if they serve the thread — use your \
judgment on weight. You are not required to mention every secondary \
signal.
- If specialists contradict each other on a pitch, acknowledge the \
tension rather than silently picking one side.\
"""

_EXPLAIN_THE_MODEL = """\
EXPLAIN THE MODEL: Every capsule must contextualize the grading system \
when first referenced. S+ measures pitch physical quality, L+ measures \
location, P+ is the combined Pitching+ grade. Explain what decisions \
the model made — which pitches were weighted, what baselines were \
used — so the reader understands the analytical foundation, not just \
the conclusions.\
"""

_SYNTHESIS_FRAMING = _SYNTHESIS_RULES + "\n\n" + _EXPLAIN_THE_MODEL


# ═══════════════════════════════════════════════════════════════════════
# CHANGES-MODE MANDATE — feeds the changes-mode input framing (design §6).
# The writer is directed to report only what MOVED and lead with the biggest
# shift.
# ═══════════════════════════════════════════════════════════════════════

_CHANGES_MANDATE = """\
FOCUS — CHANGES ONLY: Report what has CHANGED for this pitcher in the recent \
window relative to his season baseline. This is not a full scouting report; it \
is a change log written with a scout's eye.
- Lead with the single biggest shift — the largest, most consequential change \
across the five analyses. Your first sentence names it.
- Report only what moved. A stable, unchanged trait is not a story here; omit \
it unless it directly frames a change (e.g. a steady fastball that makes a \
slider's new shape stand out).
- Prefer deltas to states. "The slider added three inches of drop" beats "the \
slider has good drop." If a metric did not change, it does not earn a sentence.
- A quiet window is itself the finding. If little moved, say so plainly and \
tentatively rather than manufacturing movement out of noise.
- Distinguish mechanism from mix. When the trend analysis shows a \
release-point or extension shift alongside a velo or shape change, that pairing \
is a mechanical-adjustment signal — name it as such (e.g. "a lower slot is \
driving the added run"). A usage shift with no release-point movement is a \
pitch-mix or game-plan change instead. Never claim a mechanical cause the data \
doesn't support, and hedge explicitly when the trend analysis itself says not to \
over-read a release-point move.\
"""

_CHANGES_ANCHOR_GUIDANCE = """\
CHANGE-FOCUSED CAPSULE: This capsule is a change log — its mandate is to \
report what MOVED in the recent window versus the prior window, and to omit \
or deprioritize stable traits. Apply your emphasis rules accordingly: a \
primary or secondary signal that describes a STEADY state (an unchanged \
strength, a stable grade) may legitimately be deprioritized or mentioned \
only in passing — do not flag that as MISSED_SIGNAL or UNDERWEIGHTED. \
Reserve those flags for signals that themselves describe a CHANGE the \
capsule ignores or buries. Numeric deltas in this capsule are stated against \
the PRIOR window unless the capsule says otherwise; do not flag them for \
disagreeing with season-baseline figures."""

# ═══════════════════════════════════════════════════════════════════════
# SINGLE WRITER VOICE — the field-facing analyst/scout hybrid (design §3)
# ═══════════════════════════════════════════════════════════════════════

WRITER_VOICE = """\
You are a field-facing baseball analyst — the voice that sits between the \
analytics department and the coaching staff, translating what the model sees \
into language a front office and a pitching coach both trust.

VOICE:
- Direct and specific. Analyst-to-analyst, not fan-facing. Vary sentence \
length; short sentences land points.
- Use scouting language: stuff, feel, finding a groove, getting tagged.
- Explain the model as you go. When you name S+, L+, or P+, take a clause or \
a sentence to say what it measures and what the model decided — enough that \
the read stands on the model, not on assertion. Explain to illuminate the \
pitcher, never to admire the model.
- No cheerleading, no clichés, no formulaic transitions, no "the data shows," \
no newsletter framing ("what we're seeing here"). Start immediately with the \
analysis.\
"""

# ═══════════════════════════════════════════════════════════════════════
# PER-MODE OUTPUT STRUCTURES (design §4) — one structure per deliverable
# ═══════════════════════════════════════════════════════════════════════

_REPORT_STRUCTURE = """\
Compose a flowing prose narrative — 350-600 words, 3-5 paragraphs — that \
explains this pitcher through the lens of the model.

STRUCTURE:
- Lead with what the model sees: the single most important read on this \
pitcher right now, grounded in the grade that drives it.
- Develop the read across the arsenal — how the stuff plays, where location \
helps or hurts, what the run-value and trend picture add. Thread the \
specialist findings into one story; do not section them.
- Weave platoon splits where they matter. Close on a clear-eyed verdict.
- Prose only. No headings, no bullet lists, no tables.
- At most three primary metrics carry any single paragraph; you may cite a \
metric twice if the second citation explains the first.

HARD LIMIT: 600 words. If you approach 550, wrap up.\
"""

_CHANGES_STRUCTURE = """\
Compose a medium-length change report — 250-450 words — framed as what MOVED \
in the recent window versus the longer historical period.

STRUCTURE:
- Lead with the single biggest shift, stated concretely, with the one grade \
or metric that proves it — and what the model reads into it.
- Walk the connected changes in order of consequence. Report only what moved; \
a stable trait earns a sentence only when it frames a change.
- Prefer deltas to states. Distinguish a mechanical adjustment (a release or \
extension shift alongside a velo or shape change) from a pitch-mix change.
- Prose only. No headings, no bullet lists, no tables.
- Three-metric maximum per change.

HARD LIMIT: 450 words. If you approach 400, wrap up.\
"""

_RECAP_CAPSULE_STRUCTURE = """\
Write a tight capsule on the pitcher's most recent appearance — 3 to 5 \
sentences, one continuous thread, no headings or bullets.

- Lead with the single most important thing the model saw in the most recent \
appearance (the biggest change, adaptation, or execution read).
- Support it with one or two grounding metrics drawn straight from the \
analyses.
- Close on what it means going forward. Keep it scannable and quotable.

Target 60-120 words; never exceed 5 sentences.\
"""

# Per-mode input framing (design §4.1). report/changes carry EXPLAIN THE MODEL
# (model-focused); recap is bare synthesis. The changes mandate rides in the
# framing now. EXPLAIN THE MODEL stays appended last so the explain_model=False
# strip in build_writer_system_prompt removes it cleanly.
_REPORT_FRAMING = _SYNTHESIS_FRAMING  # _SYNTHESIS_RULES + "\n\n" + _EXPLAIN_THE_MODEL
_CHANGES_FRAMING = (
    _SYNTHESIS_RULES + "\n\n" + _CHANGES_MANDATE + "\n\n" + _EXPLAIN_THE_MODEL
)
_RECAP_FRAMING = _SYNTHESIS_RULES


@dataclass(frozen=True)
class ValidationPolicy:
    """Per-mode revision-depth knobs for the shared validation stack.

    Detection always runs (cheap, mandatory); only remediation depth is
    tuned. ``depth == 0`` is valid: the loop runs its detection pass, surfaces
    residual flags, and declines to auto-fix (design §7).

    Attributes:
        anchor_depth: Max anchor-revision passes (``max_revisions``).
        fact_depth: Max capsule fact-revision passes (``max_fact_revisions``).
    """

    anchor_depth: int
    fact_depth: int


@dataclass(frozen=True)
class NarrationMode:
    """A top-level narration selector: one deliverable (report/recap/changes).

    A mode owns the output shape the single writer voice renders in — its
    ``structure`` (length + format rules), its ``input_framing`` (what material
    the writer is synthesizing, with or without the EXPLAIN THE MODEL mandate),
    and its ``length_target`` (the (min, max) word window). Voice is fixed
    (``WRITER_VOICE``); the mode only picks the shape.

    ``validation`` carries the per-mode revision-depth knobs threaded into the
    shared validation stack. ``temporal_frame`` declares which windows the mode
    narrates.

    ``title`` is the reader-facing H1 the CLI prints above the mode's streamed
    capsule. ``distill`` controls whether the pipeline runs the second-step
    summarizers (executive summary + brief); RECAP's capsule *is* a brief, so
    it skips them.

    ``anchor_guidance`` is an optional mode-specific overlay appended to the
    anchor agent's system prompt — modes whose narrative mandate legitimately
    reweights signals (CHANGES) use it to keep the anchor's emphasis rules
    consistent with the writer's mandate.
    """

    id: str
    validation: ValidationPolicy = ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    )
    temporal_frame: frozenset[TemporalFrame] = frozenset({TemporalFrame.RECENT})
    title: str = ""
    distill: bool = True
    anchor_guidance: str = ""
    structure: str = ""
    input_framing: str = ""
    length_target: tuple[int, int] = (0, 0)

    def __post_init__(self) -> None:
        if not self.title:
            object.__setattr__(self, "title", self.id.title())
        lo, hi = self.length_target
        if lo <= 0 or hi <= 0 or lo > hi:
            raise ValueError(
                f"NarrationMode {self.id!r} length_target must be positive and "
                f"min<=max, got {self.length_target}"
            )


# REPORT is the full scouting narrative — the default deliverable.
REPORT = NarrationMode(
    id="report",
    validation=ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    ),
    title="Scouting Report",
    structure=_REPORT_STRUCTURE,
    input_framing=_REPORT_FRAMING,
    length_target=(350, 600),
)

# RECAP is the executive-brief deliverable. It caps the anchor loop at 1 (short
# brief, less to drift) and keeps the fact loop at 2 (design §7). Standalone via
# `report --mode recap`; morning adopts it in 8B.
RECAP = NarrationMode(
    id="recap",
    validation=ValidationPolicy(anchor_depth=1, fact_depth=2),
    title="Recap",
    distill=False,
    structure=_RECAP_CAPSULE_STRUCTURE,
    input_framing=_RECAP_FRAMING,
    length_target=(60, 120),
)

# CHANGES foregrounds what moved in the recent window (design §6). In 9A it
# rides the same RECENT-vs-SEASON spine as REPORT and differs only in the writer
# mandate; the recent-X-vs-prior-Y two-frame engine lands in 9B. Full-length
# synthesis, so it keeps REPORT's 5/2 revision depths (calibrated in Phase 11).
CHANGES = NarrationMode(
    id="changes",
    validation=ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    ),
    temporal_frame=frozenset({TemporalFrame.RECENT, TemporalFrame.PRIOR}),
    title="Change Report",
    anchor_guidance=_CHANGES_ANCHOR_GUIDANCE,
    structure=_CHANGES_STRUCTURE,
    input_framing=_CHANGES_FRAMING,
    length_target=(250, 450),
)

_NARRATION_MODES_INTERNAL: dict[str, NarrationMode] = {
    "report": REPORT,
    "recap": RECAP,
    "changes": CHANGES,
}

# Import-time invariant: registry key must match mode.id.
for _mid, _mode in _NARRATION_MODES_INTERNAL.items():
    if _mode.id != _mid:
        raise ValueError(
            f"Registry key {_mid!r} does not match mode.id {_mode.id!r}"
        )
del _mid, _mode

NARRATION_MODES: MappingProxyType[str, NarrationMode] = MappingProxyType(
    _NARRATION_MODES_INTERNAL
)

DEFAULT_MODE: NarrationMode = NARRATION_MODES["report"]


def get_narration_mode(mode_id: str) -> NarrationMode:
    """Resolve a narration-mode id to its NarrationMode instance.

    Raises ValueError (not KeyError) with the valid ids.
    """
    try:
        return NARRATION_MODES[mode_id]
    except KeyError:
        valid = ", ".join(sorted(NARRATION_MODES.keys()))
        raise ValueError(f"Unknown narration mode {mode_id!r}; valid: {valid}") from None


def build_writer_system_prompt(
    mode: NarrationMode, *, explain_model: bool = True
) -> str:
    """Compose the writer system prompt for a deliverable (mode).

    Order: universal analytical rules + mode input framing + the single
    writer voice + mode structure. ``explain_model=False`` strips the
    EXPLAIN THE MODEL mandate from the framing (report/changes only; recap
    never carries it).
    """
    framing = mode.input_framing
    if not explain_model:
        framing = framing.replace("\n\n" + _EXPLAIN_THE_MODEL, "").replace(
            _EXPLAIN_THE_MODEL, ""
        )
    return "\n\n".join([SHARED_WRITER_BASE, framing, WRITER_VOICE, mode.structure])
