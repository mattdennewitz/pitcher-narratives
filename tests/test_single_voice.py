"""Single-voice composition invariants (design §4-5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pitcher_narratives.personas import (
    CHANGES,
    RECAP,
    REPORT,
    SHARED_WRITER_BASE,
    WRITER_VOICE,
    build_mode_writer_prompt,
)

_FIX = Path(__file__).parent / "fixtures"
_MODES = {"report": REPORT, "changes": CHANGES, "recap": RECAP}


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_prompt_starts_with_base_then_contains_voice(mode_id):
    p = build_mode_writer_prompt(_MODES[mode_id])
    assert p.startswith(SHARED_WRITER_BASE)
    assert WRITER_VOICE in p


@pytest.mark.parametrize("mode_id,present", [
    ("report", True), ("changes", True), ("recap", False),
])
def test_explain_the_model_presence_by_mode(mode_id, present):
    p = build_mode_writer_prompt(_MODES[mode_id])
    assert ("EXPLAIN THE MODEL" in p) is present


def test_explain_model_false_strips_mandate_for_report():
    p = build_mode_writer_prompt(REPORT, explain_model=False)
    assert "EXPLAIN THE MODEL" not in p


def test_changes_framing_carries_the_change_mandate():
    p = build_mode_writer_prompt(CHANGES)
    # Matches the existing _CHANGES_MANDATE text verbatim (case-sensitive).
    assert "Report what has CHANGED" in p


@pytest.mark.parametrize("mode_id,phrase", [
    ("report", "350-600 words"),
    ("changes", "250-450 words"),
    ("recap", "60-120 words"),
])
def test_structure_length_phrase_present(mode_id, phrase):
    assert phrase in build_mode_writer_prompt(_MODES[mode_id])


def test_three_modes_produce_distinct_prompts():
    prompts = {m: build_mode_writer_prompt(mode) for m, mode in _MODES.items()}
    assert len(set(prompts.values())) == 3


@pytest.mark.parametrize("mode_id", ["report", "changes", "recap"])
def test_matches_frozen_fixture(mode_id):
    expected = (_FIX / f"writer_prompt_{mode_id}.txt").read_text()
    assert build_mode_writer_prompt(_MODES[mode_id]) == expected
