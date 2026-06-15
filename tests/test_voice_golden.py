"""Characterization tests for writer-voice invariants (Phase 0 safety net).

These tests lock the current composed system-prompt behaviour for every
writer path x persona so that later refactor phases cannot silently
regress structure or wiring.  Voice *text* will change intentionally in
later phases; these tests assert invariants (key substrings), not
byte-identity.

This file will grow in a later phase to assert invariants on the unified
composition after voice consolidation.
"""

from __future__ import annotations

import pytest

from pitcher_narratives.analyst import ANALYST_INSTRUCTIONS
from pitcher_narratives.digest import _build_writer_prompt
from pitcher_narratives.personas import (
    PERSONAS,
    build_writer_system_prompt,
    get_persona,
)

# ── Helpers ──────────────────────────────────────────────────────────

def _report_prompt(persona_id: str) -> str:
    """Return the composed report-writer system prompt for a persona."""
    return build_writer_system_prompt(get_persona(persona_id))


def _digest_prompt(persona_id: str) -> str:
    """Return the composed digest-writer system prompt for a persona."""
    return _build_writer_prompt(get_persona(persona_id))


# ── Report-writer invariants (build_writer_system_prompt) ─────────────


class TestReportWriterInvariants:
    """Invariants for the report-writer (build_writer_system_prompt) path.

    Covers all three registered personas: scout, analyst, generic.
    """

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_directional_consistency(self, persona_id: str) -> None:
        """Composed report-writer prompt carries a DIRECTIONAL CONSISTENCY directive."""
        prompt = _report_prompt(persona_id)
        assert "DIRECTIONAL CONSISTENCY" in prompt, (
            f"report({persona_id}): missing DIRECTIONAL CONSISTENCY block"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_temporal_grounding(self, persona_id: str) -> None:
        """Composed report-writer prompt carries a TEMPORAL GROUNDING directive."""
        prompt = _report_prompt(persona_id)
        assert "TEMPORAL GROUNDING" in prompt, (
            f"report({persona_id}): missing TEMPORAL GROUNDING block"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_banned_word_degradation(self, persona_id: str) -> None:
        """Composed report-writer prompt carries a banned-word directive (degradation)."""
        prompt = _report_prompt(persona_id)
        assert "degradation" in prompt, (
            f"report({persona_id}): banned-word 'degradation' not mentioned in prompt"
        )

    @pytest.mark.parametrize("persona_id,expected_phrase", [
        # scout expresses length as paragraph count, not word count
        ("scout", "2-3 paragraph"),
        # analyst overlay explicitly states the word-count window
        ("analyst", "450-800 words"),
        # generic overlay explicitly states the word-count window
        ("generic", "300-500 words"),
    ])
    def test_contains_expected_length_target(
        self, persona_id: str, expected_phrase: str
    ) -> None:
        """Composed report-writer prompt mentions the persona's length target.

        NOTE: The scout persona expresses length as paragraph count ("2-3 paragraph")
        rather than a word-count range.  The analyst and generic overlays use explicit
        word-count windows.  Each assertion matches today's actual text.
        """
        prompt = _report_prompt(persona_id)
        assert expected_phrase in prompt, (
            f"report({persona_id}): expected length phrase {expected_phrase!r} "
            "not found in composed prompt"
        )

    def test_all_personas_registered(self) -> None:
        """The three personas under test are all registered in PERSONAS."""
        for pid in ("scout", "analyst", "generic"):
            assert pid in PERSONAS, f"Persona {pid!r} missing from PERSONAS registry"


# ── Analyst ask-voice invariants (ANALYST_INSTRUCTIONS) ───────────────


class TestAnalystAskVoiceInvariants:
    """Invariants for the surviving analyst ask-path voice (ANALYST_INSTRUCTIONS).

    ANALYST_INSTRUCTIONS is the live ask-path voice (distinct from the now-deleted
    ANSWERER_INSTRUCTIONS). A later phase centralizes these analytical rules into
    the shared writer base and rewires this voice through the prompt composer; at
    that point these assertions move from the raw constant to the composed prompt.
    Locking them on today's constant is the whole point of the safety net.

    ANALYST_INSTRUCTIONS is a flat persona-agnostic constant, so there is nothing
    to parametrize over — one assertion per invariant.
    """

    def test_contains_directional_consistency(self) -> None:
        """ANALYST_INSTRUCTIONS carries a DIRECTIONAL CONSISTENCY directive."""
        assert "DIRECTIONAL CONSISTENCY" in ANALYST_INSTRUCTIONS, (
            "ANALYST_INSTRUCTIONS: missing DIRECTIONAL CONSISTENCY block"
        )

    def test_contains_temporal_grounding(self) -> None:
        """ANALYST_INSTRUCTIONS carries a TEMPORAL GROUNDING directive."""
        assert "TEMPORAL GROUNDING" in ANALYST_INSTRUCTIONS, (
            "ANALYST_INSTRUCTIONS: missing TEMPORAL GROUNDING block"
        )

    def test_contains_banned_word_degradation(self) -> None:
        """ANALYST_INSTRUCTIONS carries the banned-word 'degradation'."""
        assert "degradation" in ANALYST_INSTRUCTIONS, (
            "ANALYST_INSTRUCTIONS: banned-word 'degradation' not mentioned"
        )


# ── Digest-writer invariants (_build_writer_prompt) ───────────────────


class TestDigestWriterInvariants:
    """Invariants for the digest-writer (_build_writer_prompt) path.

    A later phase will rewrite this voice; these assertions capture
    today's reality so regressions are detectable.

    NOTE: The digest writer prompt currently does NOT carry
    DIRECTIONAL CONSISTENCY or TEMPORAL GROUNDING directives — those
    blocks are absent from _DIGEST_WRITER_BASE and none of the persona
    overlays inject them into the digest path.  These are documented gaps
    that a later phase should address; do not silently assume they exist.
    """

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_banned_word_degradation(self, persona_id: str) -> None:
        """Digest writer prompt carries the banned-word 'degradation' (via persona overlay)."""
        prompt = _digest_prompt(persona_id)
        assert "degradation" in prompt, (
            f"digest({persona_id}): banned-word 'degradation' not found in composed digest prompt"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_directional_consistency_absent_today(self, persona_id: str) -> None:
        """Digest writer prompt does NOT carry DIRECTIONAL CONSISTENCY today (gap to close later).

        NOTE: This assertion documents a current gap — the digest writer lacks
        this invariant.  When a later phase adds it, this test should be
        converted to assert presence, not absence.
        """
        prompt = _digest_prompt(persona_id)
        # NOTE: gap — digest writer prompt missing DIRECTIONAL CONSISTENCY
        assert "DIRECTIONAL CONSISTENCY" not in prompt, (
            f"digest({persona_id}): DIRECTIONAL CONSISTENCY now present — "
            "update this test to assert presence (gap closed)"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_temporal_grounding_absent_today(self, persona_id: str) -> None:
        """Digest writer prompt does NOT carry TEMPORAL GROUNDING today (gap to close later).

        NOTE: This assertion documents a current gap — the digest writer lacks
        this invariant.  When a later phase adds it, this test should be
        converted to assert presence, not absence.
        """
        prompt = _digest_prompt(persona_id)
        # NOTE: gap — digest writer prompt missing TEMPORAL GROUNDING
        assert "TEMPORAL GROUNDING" not in prompt, (
            f"digest({persona_id}): TEMPORAL GROUNDING now present — "
            "update this test to assert presence (gap closed)"
        )
