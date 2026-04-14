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


# ── Anchor tolerance for generic sectioned + table format (Phase 08) ──


@pytest.mark.xfail(
    reason=(
        "TestModel always returns a canned AnchorResult with non-empty warnings "
        "regardless of prompt content (RESEARCH.md Pitfall 4). The is_clean "
        "assertion documents the behavioral invariant; actual validation requires "
        "a manual real-LLM smoke run. The addendum was applied because the test "
        "cannot pass with TestModel: 'Summary tables in a fixed section format "
        "are intentional structure, not narrative violations.'"
    ),
    strict=False,
)
def test_anchor_tolerates_generic_summary_table():
    """Gate test for the conditional ANCHOR_PROMPT addendum.

    A synthetic generic capsule (six ## sections + one summary table)
    should pass the anchor check without UNSUPPORTED/OVERSTATED false
    positives on the structural elements (headings, table cells).

    Caveat (RESEARCH.md Pitfall 4): TestModel returns a canned
    AnchorResult with non-empty warnings, so this test is marked xfail.
    The one-sentence addendum has been applied to ANCHOR_PROMPT as a
    low-regret safety measure:
      "Summary tables in a fixed section format are intentional
       structure, not narrative violations."

    Behavioral validation of the addendum requires a manual real-LLM
    smoke run, which is out-of-scope for automated CI.
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    from pitcher_narratives.anchor import (
        ANCHOR_PROMPT,
        AnchorResult,
        build_anchor_message,
    )

    synthesis = (
        "## Key Signals\n"
        "- Top Improvement: Slider S+ jumped to 112 from season 98\n"
        "- Top Concern: Fastball L+ dropped to 94 from 102\n\n"
        "STUFF:\nSlider S+ 112 driven by vertical break gains.\n\n"
        "LOCATION:\nFastball L+ 94 — command slipped arm-side.\n\n"
        "RUN VALUE:\nArsenal xRV100 -0.5; slider is the driver.\n\n"
        "TRENDS:\nVelocity stable; Pitching+ up 4 points from season.\n\n"
        "GAME SHAPE:\nThird-time-through gap manageable."
    )
    synthetic_capsule = (
        "## Stuff\n"
        "The slider graded S+ 112 — the model credited vertical break.\n\n"
        "## Location\n"
        "Fastball L+ 94, below league average due to arm-side misses.\n\n"
        "## Run Value & Execution\n"
        "xRV100 of -0.5 shows the arsenal saves runs overall.\n\n"
        "## Trend\n"
        "Velocity stable; Pitching+ up 4 points from season baseline.\n\n"
        "## Game Shape\n"
        "Third-time-through gap manageable on current workload.\n\n"
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        "| Top Improvement | Slider vertical break gain | S+ 112 |\n"
        "| Top Concern | Fastball command slipped | L+ 94 |\n"
    )

    agent = Agent(
        model=TestModel(),
        system_prompt=ANCHOR_PROMPT,
        output_type=AnchorResult,
    )
    result = agent.run_sync(build_anchor_message(synthesis, synthetic_capsule))
    assert result.output.is_clean, (
        f"Anchor flagged false positives on generic capsule structure: "
        f"{result.output.warnings}. "
        f"Apply the summary-table addendum to ANCHOR_PROMPT."
    )
