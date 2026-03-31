"""Tests for analyst Q&A agent."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.data import load_pitcher_data

# Imported after module exists -- tests should fail with ImportError initially
from pitcher_narratives.analyst import (
    PITCH_TYPE_MAP,
    QADeps,
    _analyst_agent,
    _make_analyst,
    ask_question_streaming,
    get_pitch_detail,
    get_pitcher_summary,
)


TEST_PITCHER = 592155  # Booser, Cam


@pytest.fixture(scope="module")
def data():
    """Load pitcher data once per module."""
    return load_pitcher_data(TEST_PITCHER, window_days=30)


@pytest.fixture(scope="module")
def ctx(data):
    """Assemble pitcher context once per module."""
    return assemble_pitcher_context(data)


@pytest.fixture(scope="module")
def deps(ctx, data):
    """Build QADeps for tool testing."""
    return QADeps(context=ctx, data=data)


# -- AGENT-05: PITCH_TYPE_MAP tests -------------------------------------------


STATCAST_CODES = {"FF", "SI", "FC", "SL", "ST", "CU", "KC", "CH", "FS", "KN", "SC", "EP"}


def test_pitch_type_map_contains_all_statcast_codes():
    """PITCH_TYPE_MAP values cover all 12 Statcast pitch type codes."""
    values = set(PITCH_TYPE_MAP.values())
    for code in STATCAST_CODES:
        assert code in values, f"Missing Statcast code {code} in PITCH_TYPE_MAP values"


def test_pitch_type_map_synonyms():
    """Key synonyms resolve to the correct Statcast codes."""
    expected = {
        "fastball": "FF",
        "knuckle curve": "KC",
        "sweeper": "ST",
        "slider": "SL",
        "changeup": "CH",
        "cutter": "FC",
        "sinker": "SI",
        "splitter": "FS",
    }
    for synonym, code in expected.items():
        assert PITCH_TYPE_MAP[synonym] == code, (
            f"PITCH_TYPE_MAP[{synonym!r}] = {PITCH_TYPE_MAP.get(synonym)!r}, expected {code!r}"
        )


# -- AGENT-02: get_pitcher_summary tests --------------------------------------


def test_get_pitcher_summary_returns_context(deps):
    """get_pitcher_summary returns the to_prompt() string containing pitcher name."""
    # Build a mock RunContext-like object for direct tool invocation
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    result = get_pitcher_summary(mock_ctx)
    assert isinstance(result, str)
    assert deps.context.pitcher_name in result
    assert "Scouting Context" in result


# -- AGENT-03: get_pitch_detail tests -----------------------------------------


def test_get_pitch_detail_filters_by_type(deps):
    """get_pitch_detail with a known pitch type code returns data for that pitch."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    # Use the first pitch in the arsenal
    first_pitch = deps.context.arsenal[0]
    result = get_pitch_detail(mock_ctx, first_pitch.pitch_type)
    assert isinstance(result, str)
    assert first_pitch.pitch_name in result
    assert "No data for" not in result


def test_get_pitch_detail_synonym_resolution(deps):
    """get_pitch_detail resolves a synonym to the correct Statcast code."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    # Find a synonym that maps to a pitch in the arsenal
    arsenal_codes = {a.pitch_type for a in deps.context.arsenal}
    synonym_found = None
    for syn, code in PITCH_TYPE_MAP.items():
        if code in arsenal_codes and len(syn) > 2:  # skip raw codes
            synonym_found = syn
            break

    assert synonym_found is not None, "No synonym maps to an arsenal pitch"
    result = get_pitch_detail(mock_ctx, synonym_found)
    assert "No data for" not in result


def test_get_pitch_detail_missing_pitch(deps):
    """get_pitch_detail with eephus (no pitcher throws this) returns available pitches."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    result = get_pitch_detail(mock_ctx, "EP")
    assert result.startswith("No data for")
    # Should list available pitches
    for a in deps.context.arsenal:
        assert a.pitch_name in result


def test_get_pitch_detail_case_insensitive(deps):
    """get_pitch_detail is case-insensitive for pitch type codes."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    first_pitch = deps.context.arsenal[0]
    code_lower = first_pitch.pitch_type.lower()
    result = get_pitch_detail(mock_ctx, code_lower)
    assert "No data for" not in result
    assert first_pitch.pitch_name in result


# -- AGENT-01/04: Agent config tests ------------------------------------------


def test_agent_uses_instructions_not_system_prompt():
    """Agent uses instructions parameter, not system_prompt."""
    # pydantic-ai stores instructions in _instructions list, system_prompt in _system_prompts tuple
    assert len(_analyst_agent._instructions) > 0
    assert isinstance(_analyst_agent._instructions[0], str)
    assert len(_analyst_agent._instructions[0]) > 0
    # No system_prompt should be set
    assert len(_analyst_agent._system_prompts) == 0


def test_qadeps_has_required_fields():
    """QADeps dataclass has context and data fields."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(QADeps)}
    assert "context" in fields
    assert "data" in fields


# -- AGENT-01 + AGENT-06: Integration tests -----------------------------------


def test_ask_question_streaming(ctx, data):
    """ask_question_streaming returns a non-empty string with TestModel."""
    result = ask_question_streaming(
        "What's his best pitch?",
        context=ctx,
        data=data,
        _model_override=TestModel(),
    )
    assert isinstance(result, str)
    assert len(result) > 0


# -- TOOL-01/02: Intermediates and Attribution tests ---------------------------


def test_get_pitch_detail_includes_attribution(deps):
    """get_pitch_detail output for a known pitch type contains 'Component Attribution'."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    first_pitch = deps.context.arsenal[0]
    result = get_pitch_detail(mock_ctx, first_pitch.pitch_type)
    assert "Component Attribution" in result


def test_get_pitch_detail_attribution_has_outcomes(deps):
    """Attribution section contains at least 5 outcome rows (from 13 canonical outcomes)."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    first_pitch = deps.context.arsenal[0]
    result = get_pitch_detail(mock_ctx, first_pitch.pitch_type)

    # Count data rows in the attribution table (lines starting with | but not header/separator)
    in_attribution = False
    outcome_rows = 0
    for line in result.split("\n"):
        if "Component Attribution" in line:
            in_attribution = True
            continue
        if in_attribution and line.startswith("## ") or (in_attribution and line.startswith("### ") and "Component" not in line):
            break
        if in_attribution and line.startswith("|") and "Outcome" not in line and "---" not in line:
            outcome_rows += 1
    assert outcome_rows >= 5, f"Found {outcome_rows} outcome rows, expected >= 5"


def test_get_pitch_detail_includes_intermediates(deps):
    """get_pitch_detail output for a known pitch type contains 'Location Impact'."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    first_pitch = deps.context.arsenal[0]
    result = get_pitch_detail(mock_ctx, first_pitch.pitch_type)
    assert "Location Impact" in result


def test_get_pitcher_summary_includes_intermediates(deps):
    """get_pitcher_summary output contains 'Model Internals' (from to_prompt)."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    result = get_pitcher_summary(mock_ctx)
    assert "Model Internals" in result


def test_get_pitch_detail_existing_sections_preserved(deps):
    """get_pitch_detail still contains Arsenal and Execution sections."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.deps = deps

    first_pitch = deps.context.arsenal[0]
    result = get_pitch_detail(mock_ctx, first_pitch.pitch_type)
    assert "Arsenal" in result
    assert "Execution" in result
