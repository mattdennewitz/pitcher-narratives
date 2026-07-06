"""Single-voice composition invariants (design §4-5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pitcher_narratives.personas import (
    CHANGES,
    NarrationMode,
    RECAP,
    REPORT,
    SHARED_WRITER_BASE,
    WRITER_VOICE,
    build_writer_system_prompt,
)

_FIX = Path(__file__).parent / "fixtures"
_MODES = {"report": REPORT, "changes": CHANGES, "recap": RECAP}


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_prompt_starts_with_base_then_contains_voice(mode_id):
    p = build_writer_system_prompt(_MODES[mode_id])
    assert p.startswith(SHARED_WRITER_BASE)
    assert WRITER_VOICE in p


@pytest.mark.parametrize("mode_id,present", [
    ("report", True), ("changes", True), ("recap", False),
])
def test_explain_the_model_presence_by_mode(mode_id, present):
    p = build_writer_system_prompt(_MODES[mode_id])
    assert ("EXPLAIN THE MODEL" in p) is present


def test_explain_model_false_strips_mandate_for_report():
    p = build_writer_system_prompt(REPORT, explain_model=False)
    assert "EXPLAIN THE MODEL" not in p


def test_explain_model_false_strips_mandate_for_changes():
    """CHANGES also carries EXPLAIN THE MODEL; explain_model=False strips it
    while the change mandate itself survives."""
    p = build_writer_system_prompt(CHANGES, explain_model=False)
    assert "EXPLAIN THE MODEL" not in p
    # The change mandate is a separate block and must not be stripped.
    assert "Report what has CHANGED" in p


def test_changes_framing_carries_the_change_mandate():
    p = build_writer_system_prompt(CHANGES)
    # Matches the existing _CHANGES_MANDATE text verbatim (case-sensitive).
    assert "Report what has CHANGED" in p


@pytest.mark.parametrize("mode_id,phrase", [
    ("report", "350-600 words"),
    ("changes", "250-450 words"),
    ("recap", "60-120 words"),
])
def test_structure_length_phrase_present(mode_id, phrase):
    assert phrase in build_writer_system_prompt(_MODES[mode_id])


def test_three_modes_produce_distinct_prompts():
    prompts = {m: build_writer_system_prompt(mode) for m, mode in _MODES.items()}
    assert len(set(prompts.values())) == 3


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_matches_frozen_fixture(mode_id):
    expected = (_FIX / f"writer_prompt_{mode_id}.txt").read_text()
    assert build_writer_system_prompt(_MODES[mode_id]) == expected


# ── Universal directive manifest (folded from the retired test_voice_golden) ──
# Every canonical writer directive must survive in the composed report prompt.
# Markers are stable substrings that prove the concern they guard was not
# dropped from SHARED_WRITER_BASE or the synthesis framing.
_UNIVERSAL_MANIFEST = [
    "degradation",             # banned-word list
    "DIRECTIONAL CONSISTENCY",
    "TEMPORAL GROUNDING",
    "sample size",             # sample-size calibration
    "DEAD ZONE",               # arm-slot insight
    "Find the thread",         # synthesis rule
    "EXPLAIN THE MODEL",       # model-teaching rule (report/changes)
]


@pytest.mark.parametrize("marker", _UNIVERSAL_MANIFEST)
def test_report_prompt_carries_universal_directive(marker):
    """Every universal directive marker survives in the composed report prompt."""
    assert marker in build_writer_system_prompt(REPORT), (
        f"report prompt is missing directive marker {marker!r}"
    )


# ── NarrationMode length-target validation (ported from the old contract) ──


def test_narration_mode_rejects_inverted_length_target():
    """length_target min > max raises at construction."""
    with pytest.raises(ValueError, match="min<=max"):
        NarrationMode(id="bad", length_target=(500, 100))


def test_narration_mode_rejects_non_positive_length_target():
    """length_target with a zero/negative bound raises at construction."""
    with pytest.raises(ValueError, match="positive"):
        NarrationMode(id="bad", length_target=(0, 100))


@pytest.mark.parametrize("mode_id", ["report", "changes"])
def test_explain_model_false_leaves_no_dangling_blank_lines(mode_id):
    """Stripping EXPLAIN THE MODEL must not leave a triple newline gap."""
    off = build_writer_system_prompt(_MODES[mode_id], explain_model=False)
    assert "\n\n\n" not in off
