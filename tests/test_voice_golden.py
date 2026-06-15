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

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_banned_word_block_appears_exactly_once(self, persona_id: str) -> None:
        """The banned-word directive is single-sourced (universal base) — appears once.

        Phase 1A dedup goal: the writer-voice banned-word list lives only in
        SHARED_WRITER_BASE, not duplicated across persona overlays.
        """
        prompt = _report_prompt(persona_id)
        assert prompt.count('Never use: "degradation,"') == 1, (
            f"report({persona_id}): banned-word block must appear exactly once"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_composed_layering_order(self, persona_id: str) -> None:
        """Composed report prompt layers universal base, then synthesis framing.

        The universal analytical rules lead; the five-specialist synthesis
        framing (EXPLAIN THE MODEL) follows. This locks the composer's layer
        order so a refactor cannot silently scramble it.
        """
        from pitcher_narratives.personas import SHARED_WRITER_BASE

        prompt = _report_prompt(persona_id)
        assert prompt.startswith(SHARED_WRITER_BASE)
        assert "five specialist analyses" in prompt.lower()
        assert "EXPLAIN THE MODEL" in prompt
        assert prompt.index("DIRECTIONAL CONSISTENCY") < prompt.index(
            "EXPLAIN THE MODEL"
        )


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

    Phase 1A repointed the digest writer through the shared voice composer
    (build_system_prompt(persona, DIGEST_ITEM)). The digest prompt now draws
    the universal analytical rules from SHARED_WRITER_BASE, closing the gaps
    where it previously lacked DIRECTIONAL CONSISTENCY and TEMPORAL GROUNDING.
    """

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_banned_word_degradation(self, persona_id: str) -> None:
        """Digest writer prompt carries the banned-word 'degradation' (universal base)."""
        prompt = _digest_prompt(persona_id)
        assert "degradation" in prompt, (
            f"digest({persona_id}): banned-word 'degradation' not found in composed digest prompt"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_directional_consistency_present(self, persona_id: str) -> None:
        """Digest writer prompt now carries DIRECTIONAL CONSISTENCY (gap closed in Phase 1A).

        The directive flows from the universal SHARED_WRITER_BASE that the
        DIGEST_ITEM composition now includes.
        """
        prompt = _digest_prompt(persona_id)
        assert "DIRECTIONAL CONSISTENCY" in prompt, (
            f"digest({persona_id}): DIRECTIONAL CONSISTENCY missing — "
            "the universal base should now supply it"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_temporal_grounding_present(self, persona_id: str) -> None:
        """Digest writer prompt now carries TEMPORAL GROUNDING (gap closed in Phase 1A).

        The directive flows from the universal SHARED_WRITER_BASE that the
        DIGEST_ITEM composition now includes.
        """
        prompt = _digest_prompt(persona_id)
        assert "TEMPORAL GROUNDING" in prompt, (
            f"digest({persona_id}): TEMPORAL GROUNDING missing — "
            "the universal base should now supply it"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_uses_cue_framing_not_synthesis(self, persona_id: str) -> None:
        """Digest uses cue framing, NOT the five-specialist synthesis framing."""
        prompt = _digest_prompt(persona_id)
        assert "morning digest" in prompt
        assert "five specialist analyses" not in prompt.lower()
