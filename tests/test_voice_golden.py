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

from pitcher_narratives.analyst import ANALYST_MECHANICS
from pitcher_narratives.digest import _build_writer_prompt
from pitcher_narratives.personas import (
    ANSWER,
    PERSONAS,
    build_system_prompt,
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

        Robustness: we count the banned token ``"degradation,"`` (the word
        with its enclosing quotes and trailing comma, as it appears in the
        banned list) rather than the full surrounding sentence, so the
        assertion survives rewording of the directive without giving false
        confidence.
        """
        prompt = _report_prompt(persona_id)
        assert prompt.count('"degradation,"') == 1, (
            f"report({persona_id}): banned token '\"degradation,\"' must appear "
            "exactly once — the banned-word list must be single-sourced in "
            "SHARED_WRITER_BASE"
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


# ── Analyst ask-voice invariants (composed ask prompt) ────────────────


def _ask_prompt(persona_id: str) -> str:
    """Return the composed ask-agent system prompt for a persona."""
    return build_system_prompt(get_persona(persona_id), ANSWER) + "\n\n" + ANALYST_MECHANICS


class TestAnalystAskVoiceInvariants:
    """Invariants for the composed analyst ask-path voice (Phase 1B).

    Phase 1B rewired the ask path through build_system_prompt(persona, ANSWER).
    The composed prompt = SHARED_WRITER_BASE + ANSWER.input_framing + persona
    voice chain + ANSWER.structure + ANALYST_MECHANICS.

    Parametrized over all three registered personas so persona choice cannot
    silently drop a directive.
    """

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_directional_consistency(self, persona_id: str) -> None:
        """Composed ask prompt carries DIRECTIONAL CONSISTENCY from universal base."""
        prompt = _ask_prompt(persona_id)
        assert "DIRECTIONAL CONSISTENCY" in prompt, (
            f"ask({persona_id}): missing DIRECTIONAL CONSISTENCY "
            "(should flow from SHARED_WRITER_BASE)"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_temporal_grounding(self, persona_id: str) -> None:
        """Composed ask prompt carries TEMPORAL GROUNDING from universal base."""
        prompt = _ask_prompt(persona_id)
        assert "TEMPORAL GROUNDING" in prompt, (
            f"ask({persona_id}): missing TEMPORAL GROUNDING "
            "(should flow from SHARED_WRITER_BASE)"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_banned_word_single_sourced(self, persona_id: str) -> None:
        """RT-10: banned-word token appears exactly once in the composed ask prompt.

        The banned list lives solely in SHARED_WRITER_BASE; ANALYST_MECHANICS
        must not duplicate it.  Count the stable token '"degradation,"' (quoted
        + comma as it appears in the banned list) so the check survives minor
        rewording of the surrounding sentence.
        """
        prompt = _ask_prompt(persona_id)
        assert '"degradation,"' in prompt, (
            f"ask({persona_id}): banned token '\"degradation,\"' not found"
        )
        assert prompt.count('"degradation,"') == 1, (
            f"ask({persona_id}): banned token '\"degradation,\"' appears more "
            "than once — ANALYST_MECHANICS must not duplicate the banned-word list"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_model_mechanics(self, persona_id: str) -> None:
        """Composed ask prompt carries HOW THE MODEL THINKS from ANALYST_MECHANICS."""
        prompt = _ask_prompt(persona_id)
        assert "HOW THE MODEL THINKS" in prompt, (
            f"ask({persona_id}): missing HOW THE MODEL THINKS block from ANALYST_MECHANICS"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_contains_sign_conventions(self, persona_id: str) -> None:
        """Composed ask prompt carries SIGN CONVENTIONS from ANALYST_MECHANICS."""
        prompt = _ask_prompt(persona_id)
        assert "SIGN CONVENTIONS" in prompt, (
            f"ask({persona_id}): missing SIGN CONVENTIONS block from ANALYST_MECHANICS"
        )

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    def test_uses_ask_framing_not_synthesis(self, persona_id: str) -> None:
        """Composed ask prompt uses ask-specific input framing, not synthesis framing.

        The ANSWER contract uses _ANSWER_FRAMING; the five-specialist synthesis
        framing belongs to CAPSULE/NEWSLETTER/SECTIONED contracts only.
        """
        prompt = _ask_prompt(persona_id)
        assert "five specialist analyses" not in prompt.lower(), (
            f"ask({persona_id}): found 'five specialist analyses' — "
            "ANSWER contract must not use _SYNTHESIS_FRAMING"
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


# ── RT-1: Directive-manifest completeness guard ───────────────────────


# Per-persona structure phrase that must appear in the composed report prompt.
# Each entry maps persona id → a stable substring from that persona's contract
# structure block.  These differ by design (different output formats).
_STRUCTURE_PHRASE: dict[str, str] = {
    "scout": "2-3 paragraph",
    "analyst": "450-800 words",
    "generic": "300-500 words",
}

# Universal directives that EVERY composed report prompt must contain,
# regardless of persona.  Chosen as stable, minimally-phrased substrings
# that survive rewordings of surrounding sentences while still proving that
# the concern they guard has not been dropped.
#
# Verification: each marker was confirmed present by running:
#   uv run python -c "from pitcher_narratives.personas import get_persona, \
#       build_writer_system_prompt; print(build_writer_system_prompt(get_persona('<pid>')))"
# for all three personas before this test was written.
_UNIVERSAL_MANIFEST: list[str] = [
    # Banned-word list
    "degradation",
    # Directional-consistency rule
    "DIRECTIONAL CONSISTENCY",
    # Temporal-grounding rule
    "TEMPORAL GROUNDING",
    # Sample-size calibration
    "sample size",
    # Arm-slot insight (DEAD ZONE is the concrete example used)
    "DEAD ZONE",
    # Find-the-thread synthesis rule
    "Find the thread",
    # Explain-the-model rule
    "EXPLAIN THE MODEL",
]


class TestReportDirectiveManifest:
    """RT-1 completeness guard for the report-writer composed prompt.

    Asserts that every canonical writer directive survives in the composed
    report prompt for each persona.  This is a permanent guard: if a future
    refactor silently drops a directive (e.g. moves SHARED_WRITER_BASE content
    into an overlay and forgets to include it), this test catches it.

    Markers are stable substrings verified against the actual composed prompts
    at the time this test was written.  Per-persona structure phrases are
    checked separately because they legitimately differ by output contract.
    """

    @pytest.mark.parametrize("persona_id", ["scout", "analyst", "generic"])
    @pytest.mark.parametrize("marker", _UNIVERSAL_MANIFEST)
    def test_universal_directive_present(self, persona_id: str, marker: str) -> None:
        """Every universal directive marker survives in every persona's report prompt."""
        prompt = _report_prompt(persona_id)
        assert marker in prompt, (
            f"RT-1: report({persona_id}) is missing directive marker {marker!r}. "
            "A refactor may have dropped or relocated a universal directive from "
            "SHARED_WRITER_BASE or the synthesis framing."
        )

    @pytest.mark.parametrize("persona_id,structure_phrase", list(_STRUCTURE_PHRASE.items()))
    def test_structure_phrase_present(
        self, persona_id: str, structure_phrase: str
    ) -> None:
        """Each persona's expected structure/length phrase appears in its report prompt."""
        prompt = _report_prompt(persona_id)
        assert structure_phrase in prompt, (
            f"RT-1: report({persona_id}) is missing structure phrase "
            f"{structure_phrase!r}. The output contract for this persona may "
            "have been swapped or the structure block may have been reworded."
        )
