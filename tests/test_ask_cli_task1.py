"""RED phase tests for ask_cli.py Task 1 behavior."""

from __future__ import annotations

import sys

import pytest


def test_module_importable():
    """ask_cli module can be imported."""
    from pitcher_narratives.ask_cli import main, parse_args  # noqa: F401


def test_extract_pitcher_name_exists():
    """_extract_pitcher_name function exists."""
    from pitcher_narratives.ask_cli import _extract_pitcher_name  # noqa: F401


def test_extract_strips_possessive():
    """_extract_pitcher_name strips possessives like Cease's."""
    from pitcher_narratives.ask_cli import _extract_pitcher_name

    query, result = _extract_pitcher_name("Why is Cease's knuckle curve bad?")
    assert result is not None
    assert result.pitcher_name is not None
    assert "Cease" in result.pitcher_name


def test_extract_full_name():
    """_extract_pitcher_name resolves full name like Dylan Cease."""
    from pitcher_narratives.ask_cli import _extract_pitcher_name

    query, result = _extract_pitcher_name("How is Dylan Cease pitching?")
    assert query is not None
    assert "Dylan Cease" in query
    assert result is not None
    assert result.match_type == "exact"


def test_extract_not_found():
    """_extract_pitcher_name returns (None, None) for gibberish."""
    from pitcher_narratives.ask_cli import _extract_pitcher_name

    query, result = _extract_pitcher_name("Tell me about xyzzyplugh")
    assert query is None
    assert result is None


def test_parse_question_positional(monkeypatch):
    """parse_args captures positional question."""
    from pitcher_narratives.ask_cli import parse_args

    monkeypatch.setattr(sys, "argv", ["ask_cli", "How is Cease?"])
    args = parse_args()
    assert args.question == "How is Cease?"


def test_parse_provider_flag(monkeypatch):
    """parse_args captures --provider flag."""
    from pitcher_narratives.ask_cli import parse_args

    monkeypatch.setattr(sys, "argv", ["ask_cli", "--provider", "openai", "How?"])
    args = parse_args()
    assert args.provider == "openai"


def test_parse_thinking_flag(monkeypatch):
    """parse_args captures --thinking flag."""
    from pitcher_narratives.ask_cli import parse_args

    monkeypatch.setattr(sys, "argv", ["ask_cli", "--thinking", "low", "How?"])
    args = parse_args()
    assert args.thinking == "low"


def test_parse_window_flag(monkeypatch):
    """parse_args captures -w flag."""
    from pitcher_narratives.ask_cli import parse_args

    monkeypatch.setattr(sys, "argv", ["ask_cli", "-w", "14", "How?"])
    args = parse_args()
    assert args.window == 14


def test_parse_defaults(monkeypatch):
    """parse_args defaults: provider=claude, thinking=high, window=30."""
    from pitcher_narratives.ask_cli import parse_args

    monkeypatch.setattr(sys, "argv", ["ask_cli", "Q?"])
    args = parse_args()
    assert args.provider == "claude"
    assert args.thinking == "high"
    assert args.window == 30
