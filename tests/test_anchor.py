"""Tests for anchor.py — revision message builder and result models.

Revived from the old test_report.py coverage after v1.9 consolidation
removed that file. These exercise `build_revision_message`, the
`AnchorResult.is_clean` property, and `AnchorWarning` category
validation — all live functionality consumed by pipeline.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai import CachePoint

from pitcher_narratives.anchor import (
    AnchorResult,
    AnchorWarning,
    build_revision_message,
)


# ── AnchorWarning ─────────────────────────────────────────────────────────


def test_anchor_warning_accepts_known_categories():
    """All five documented categories are accepted."""
    for category in ("MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED", "UNDERWEIGHTED"):
        w = AnchorWarning(category=category, description="test")
        assert w.category == category


def test_anchor_warning_rejects_invalid_category():
    """Invalid categories are rejected by the Literal type."""
    with pytest.raises(ValidationError):
        AnchorWarning(category="TYPO_CATEGORY", description="bad")  # type: ignore[arg-type]


def test_anchor_warning_description_required():
    """description field is mandatory."""
    with pytest.raises(ValidationError):
        AnchorWarning(category="MISSED_SIGNAL")  # type: ignore[call-arg]


# ── AnchorResult ──────────────────────────────────────────────────────────


def test_anchor_result_is_clean_when_empty():
    """Empty warnings list → is_clean True."""
    result = AnchorResult(warnings=[])
    assert result.is_clean is True


def test_anchor_result_is_not_clean_with_warnings():
    """Any warning → is_clean False."""
    result = AnchorResult(
        warnings=[AnchorWarning(category="MISSED_SIGNAL", description="missed top concern")]
    )
    assert result.is_clean is False


def test_anchor_result_preserves_multiple_warnings():
    """Multiple warnings are preserved in order."""
    warnings = [
        AnchorWarning(category="MISSED_SIGNAL", description="first"),
        AnchorWarning(category="UNSUPPORTED", description="second"),
        AnchorWarning(category="DIRECTION_ERROR", description="third"),
    ]
    result = AnchorResult(warnings=warnings)
    assert len(result.warnings) == 3
    assert [w.category for w in result.warnings] == [
        "MISSED_SIGNAL",
        "UNSUPPORTED",
        "DIRECTION_ERROR",
    ]
    assert result.is_clean is False


# ── build_revision_message ────────────────────────────────────────────────


def _sample_warnings() -> list[AnchorWarning]:
    return [
        AnchorWarning(category="MISSED_SIGNAL", description="Top concern about velocity drop was not addressed"),
        AnchorWarning(category="DIRECTION_ERROR", description="Said S+ went up but it went down"),
    ]


def test_revision_message_contains_synthesis():
    """Synthesis appears in the output and is labeled."""
    synthesis = "SYNTH_BODY_TEXT_MARKER"
    parts = build_revision_message(synthesis, "capsule", _sample_warnings())
    joined = "\n".join(p for p in parts if isinstance(p, str))
    assert "Data Analyst's Briefing" in joined
    assert "SYNTH_BODY_TEXT_MARKER" in joined


def test_revision_message_contains_capsule():
    """Current capsule appears in the output and is labeled."""
    capsule = "CAPSULE_BODY_TEXT_MARKER"
    parts = build_revision_message("synth", capsule, _sample_warnings())
    joined = "\n".join(p for p in parts if isinstance(p, str))
    assert "Current Capsule" in joined
    assert "CAPSULE_BODY_TEXT_MARKER" in joined


def test_revision_message_formats_warnings_with_categories():
    """Each warning appears with its category in bracketed format."""
    parts = build_revision_message("s", "c", _sample_warnings())
    joined = "\n".join(p for p in parts if isinstance(p, str))
    assert "[MISSED_SIGNAL] Top concern about velocity drop was not addressed" in joined
    assert "[DIRECTION_ERROR] Said S+ went up but it went down" in joined


def test_revision_message_has_targeted_instruction():
    """The revision instruction is explicit about addressing only flagged warnings."""
    parts = build_revision_message("s", "c", _sample_warnings())
    joined = "\n".join(p for p in parts if isinstance(p, str))
    assert "ONLY the warnings listed above" in joined
    assert "Preserve the voice" in joined


def test_revision_message_has_cache_point():
    """A CachePoint is placed between the synthesis and the capsule/warnings."""
    parts = build_revision_message("s", "c", _sample_warnings())
    cache_positions = [i for i, p in enumerate(parts) if isinstance(p, CachePoint)]
    assert len(cache_positions) == 1, "Expected exactly one CachePoint"
    # CachePoint must come after the synthesis and before the capsule block
    assert cache_positions[0] == 1, "CachePoint should be at index 1 (after synthesis)"


def test_revision_message_returns_list():
    """Return type is a list of prompt parts."""
    parts = build_revision_message("s", "c", _sample_warnings())
    assert isinstance(parts, list)
    # synthesis, cachepoint, capsule+warnings → 3 parts
    assert len(parts) == 3


def test_revision_message_handles_empty_warnings():
    """Empty warnings list still produces a valid message (no crash)."""
    parts = build_revision_message("s", "c", [])
    joined = "\n".join(p for p in parts if isinstance(p, str))
    assert "Anchor Check Warnings" in joined
    # Formatted warnings block is empty but the section header is still present
    assert "Current Capsule" in joined


# ── build_reconcile_message ────────────────────────────────────────────────


def test_reconcile_message_contains_parts():
    from pitcher_narratives.anchor import AnchorWarning, build_reconcile_message

    w = AnchorWarning(category="UNSUPPORTED", description="capsule says 6, synthesis says 15")
    msg = build_reconcile_message("THE SYNTHESIS", "THE CAPSULE", [w])
    assert "THE SYNTHESIS" in msg
    assert "THE CAPSULE" in msg
    assert "capsule says 6, synthesis says 15" in msg


def test_reconcile_message_forbids_numeric_changes():
    from pitcher_narratives.anchor import AnchorWarning, build_reconcile_message

    w = AnchorWarning(category="UNSUPPORTED", description="d")
    msg = build_reconcile_message("s", "c", [w])
    assert "do not change any numeric value" in msg.lower()
    assert "fact-check" in msg.lower()


# ── Anchor tolerance for generic sectioned + table format ──


def test_anchor_prompt_contains_summary_table_addendum():
    """Literal-string regression guard on the ANCHOR_PROMPT addendum.

    The generic persona's fixed section + summary table format would
    otherwise trip OVERSTATED/UNSUPPORTED warnings from the anchor agent.
    A one-sentence addendum teaches the anchor to treat intentional
    structure as non-violation. Accidental deletion of that sentence
    during a future prompt edit must fail CI.

    Behavioral validation with a real LLM is out of scope for automated
    tests (TestModel returns canned AnchorResult regardless of prompt).
    This check locks the prompt text; end-to-end verification happens
    via manual smoke runs.
    """
    from pitcher_narratives.anchor import ANCHOR_PROMPT

    addendum = (
        "Summary tables in a fixed section format are intentional "
        "structure, not narrative violations."
    )
    assert addendum in ANCHOR_PROMPT, (
        "ANCHOR_PROMPT is missing the summary-table tolerance addendum. "
        "This sentence prevents the anchor from flagging the generic "
        "persona's summary table as an UNSUPPORTED narrative violation."
    )
