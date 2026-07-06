"""Tests for NarrationMode definitions, the mode registry, and mode fields.

The persona and output-contract machinery was deleted in the single-voice refactor;
what remains is the narration-mode surface (one voice, mode picks the shape).
"""

import dataclasses

import pytest

from pitcher_narratives.personas import (
    CHANGES,
    NARRATION_MODES,
    RECAP,
    REPORT,
    NarrationMode,
    ValidationPolicy,
    get_narration_mode,
)
from pitcher_narratives.temporal import TemporalFrame


# ── Mode registry / resolution ──────────────────────────────────────────


def test_get_narration_mode_returns_report():
    """get_narration_mode('report') resolves to the REPORT instance."""
    assert get_narration_mode("report") is REPORT


def test_get_narration_mode_unknown_raises_valueerror():
    """Unknown mode ids raise ValueError listing valid ids (not KeyError)."""
    with pytest.raises(ValueError, match="bogus"):
        get_narration_mode("bogus")


def test_narration_modes_registry_keys_match_ids():
    """NARRATION_MODES registry-key invariant: each key equals its mode.id."""
    assert set(NARRATION_MODES) == {"report", "recap", "changes"}
    for mid, mode in NARRATION_MODES.items():
        assert mode.id == mid, f"registry key {mid!r} != mode.id {mode.id!r}"


def test_recap_mode_registered_and_resolvable():
    assert get_narration_mode("recap") is RECAP
    assert RECAP.id == "recap"


def test_changes_mode_registered_and_resolvable():
    assert get_narration_mode("changes") is CHANGES
    assert CHANGES.id == "changes"


# ── NarrationMode dataclass behavior ────────────────────────────────────


def test_narration_mode_is_frozen():
    """NarrationMode is immutable so registry identity is stable."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        REPORT.id = "changed"  # type: ignore[misc]


def test_mode_title_defaults_to_id():
    """A mode constructed without a title falls back to id.title()."""
    m = NarrationMode(id="custom", length_target=(150, 350))
    assert m.title == "Custom"


def test_mode_titles():
    assert REPORT.title == "Scouting Report"
    assert CHANGES.title == "Change Report"
    assert RECAP.title == "Recap"


def test_mode_distill_flags():
    assert REPORT.distill is True
    assert CHANGES.distill is True
    assert RECAP.distill is False


def test_mode_explains_model_flags():
    """explains_model is the first-class fact the pipeline gates the capsule
    explainer-check on -- REPORT/CHANGES carry the EXPLAIN THE MODEL mandate,
    RECAP does not."""
    assert REPORT.explains_model is True
    assert CHANGES.explains_model is True
    assert RECAP.explains_model is False


# ── ValidationPolicy ─────────────────────────────────────────────────────


def test_report_validation_policy_matches_config_depths():
    """REPORT keeps today's depths; config is the single source of truth."""
    from pitcher_narratives.config import MAX_FACT_REVISIONS, MAX_REVISIONS

    assert REPORT.validation == ValidationPolicy(
        anchor_depth=MAX_REVISIONS, fact_depth=MAX_FACT_REVISIONS
    )
    assert (REPORT.validation.anchor_depth, REPORT.validation.fact_depth) == (5, 2)


def test_recap_validation_depths():
    """RECAP caps anchor at 1, keeps fact at 2 (design §7)."""
    assert (RECAP.validation.anchor_depth, RECAP.validation.fact_depth) == (1, 2)


def test_changes_validation_depths_match_report():
    """CHANGES is a full-length synthesis, so it uses REPORT's 5/2 depths."""
    from pitcher_narratives.config import MAX_FACT_REVISIONS, MAX_REVISIONS

    assert CHANGES.validation.anchor_depth == MAX_REVISIONS
    assert CHANGES.validation.fact_depth == MAX_FACT_REVISIONS


def test_validation_policy_is_frozen():
    policy = ValidationPolicy(anchor_depth=1, fact_depth=2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.anchor_depth = 3  # type: ignore[misc]


# ── Temporal frames ──────────────────────────────────────────────────────


def test_report_and_recap_are_single_frame():
    assert REPORT.temporal_frame == frozenset({TemporalFrame.RECENT})
    assert RECAP.temporal_frame == frozenset({TemporalFrame.RECENT})


def test_changes_declares_recent_and_prior_frames():
    assert CHANGES.temporal_frame == frozenset(
        {TemporalFrame.RECENT, TemporalFrame.PRIOR}
    )


# ── CHANGES anchor guidance ──────────────────────────────────────────────


def test_changes_mode_has_anchor_guidance():
    assert REPORT.anchor_guidance == ""
    assert RECAP.anchor_guidance == ""
    g = CHANGES.anchor_guidance
    assert "change" in g.lower()
    assert "UNDERWEIGHTED" in g


def test_changes_mandate_references_trend_analysis_not_specialist_block():
    """The writer only sees specialist prose, never the Recent vs Prior
    Window block itself (that's trends-specialist-internal) — so the
    mandate must reference 'the trend analysis' instead."""
    from pitcher_narratives.personas import _CHANGES_MANDATE

    assert "Recent vs Prior Window block" not in _CHANGES_MANDATE
    assert "the trend analysis" in _CHANGES_MANDATE
    # Hedging guidance must survive the reword.
    assert "hedge explicitly" in _CHANGES_MANDATE
    assert "over-read a release-point move" in _CHANGES_MANDATE


# ── Input-framing split invariants (drive the explain_model strip) ──────


def test_synthesis_framing_recomposes_from_rules_and_explain_the_model():
    """_SYNTHESIS_FRAMING splits into _SYNTHESIS_RULES + _EXPLAIN_THE_MODEL, and
    REPORT's framing ends with the mandate so the explain_model=False strip in
    build_writer_system_prompt removes it cleanly."""
    from pitcher_narratives.personas import (
        _EXPLAIN_THE_MODEL,
        _SYNTHESIS_FRAMING,
        _SYNTHESIS_RULES,
    )

    assert _SYNTHESIS_FRAMING == _SYNTHESIS_RULES + "\n\n" + _EXPLAIN_THE_MODEL
    assert REPORT.input_framing.endswith(_EXPLAIN_THE_MODEL)


def test_recap_framing_lacks_explain_the_model_but_keeps_key_signals_rule():
    """RECAP's framing must not carry the EXPLAIN THE MODEL exposition directive
    (incompatible with the 60-120 word cap), but must still carry the Key
    Signals synthesis rule."""
    assert "EXPLAIN THE MODEL" not in RECAP.input_framing
    assert "Use the Key Signals" in RECAP.input_framing
