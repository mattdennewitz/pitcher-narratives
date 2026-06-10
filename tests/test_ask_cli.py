"""Tests for ask CLI argument parsing and integration.

Covers unit tests for parse_args and extract_pitcher_from_question, plus
subprocess-based integration tests for the full CLI lifecycle.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from pitcher_narratives.ask_cli import parse_args
from pitcher_narratives.resolver import extract_pitcher_from_question


# ── Helper ──


def _test_env(**extra: str) -> dict[str, str]:
    """Build a clean subprocess environment with optional overrides.

    Starts from os.environ so PATH and other essentials are preserved,
    then removes API keys (tests shouldn't hit the real API) and applies
    any extra key-value pairs.
    """
    strip = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}
    env = {k: v for k, v in os.environ.items() if k not in strip}
    # Set empty keys so load_dotenv() won't fill them from .env
    env.setdefault("ANTHROPIC_API_KEY", "")
    env.setdefault("OPENAI_API_KEY", "")
    env.setdefault("GEMINI_API_KEY", "")
    env.update(extra)
    return env


# ══════════════════════════════════════════════════════════════════════
# UNIT TESTS: parse_args
# ══════════════════════════════════════════════════════════════════════


def test_parse_question_positional(monkeypatch):
    """parse_args captures a positional question string."""
    monkeypatch.setattr(sys, "argv", ["ask_cli", "How is Cease?"])
    args = parse_args()
    assert args.question == "How is Cease?"


def test_parse_provider_flag(monkeypatch):
    """parse_args captures --provider flag."""
    monkeypatch.setattr(sys, "argv", ["ask_cli", "--provider", "claude", "Q?"])
    args = parse_args()
    assert args.provider == "claude"


def test_parse_thinking_flag(monkeypatch):
    """parse_args captures --thinking flag."""
    monkeypatch.setattr(sys, "argv", ["ask_cli", "--thinking", "low", "Q?"])
    args = parse_args()
    assert args.thinking == "low"


def test_parse_window_flag(monkeypatch):
    """parse_args captures -w flag."""
    monkeypatch.setattr(sys, "argv", ["ask_cli", "-w", "14", "Q?"])
    args = parse_args()
    assert args.window == 14


def test_parse_defaults(monkeypatch):
    """parse_args defaults: provider=gemini, thinking=medium, window=30."""
    monkeypatch.setattr(sys, "argv", ["ask_cli", "Q?"])
    args = parse_args()
    assert args.provider == "gemini"
    assert args.thinking == "medium"
    assert args.window == 30


# ══════════════════════════════════════════════════════════════════════
# UNIT TESTS: extract_pitcher_from_question
# ══════════════════════════════════════════════════════════════════════


def test_extract_exact_full_name():
    """Full name 'Dylan Cease' resolves with a definite match."""
    query, result = extract_pitcher_from_question("How is Dylan Cease pitching?")
    assert query is not None
    assert "Dylan Cease" in query
    assert result is not None
    assert result.match_type in ("exact", "exact_last", "fuzzy")
    assert result.pitcher_id is not None


def test_extract_last_name_only():
    """Last name 'Cease' resolves to a pitcher containing 'Cease'."""
    query, result = extract_pitcher_from_question("How is Cease pitching?")
    assert result is not None
    assert result.match_type in ("exact_last", "fuzzy")
    assert result.pitcher_name is not None
    assert "Cease" in result.pitcher_name


def test_extract_possessive():
    """Possessive 'Cease's' is stripped and resolves correctly."""
    query, result = extract_pitcher_from_question("Cease's knuckle curve is bad")
    assert result is not None
    assert result.pitcher_name is not None
    assert "Cease" in result.pitcher_name


def test_extract_not_found():
    """Gibberish question returns (None, None)."""
    query, result = extract_pitcher_from_question("Tell me about xyzzyplugh")
    assert query is None
    assert result is None


def test_extract_ambiguous():
    """Ambiguous name 'Johnson' returns ambiguous result with candidates."""
    query, result = extract_pitcher_from_question("How is Johnson pitching?")
    assert result is not None
    assert result.match_type == "ambiguous"
    assert len(result.candidates) > 1


# ══════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS (subprocess)
# ══════════════════════════════════════════════════════════════════════


def test_ask_cli_valid_question_exit_0():
    """Integration: Valid pitcher question with test model exits 0 and produces output."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.ask_cli", "How is Cease pitching?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert result.stdout.strip()  # Non-empty output


def test_ask_cli_output_is_just_the_answer():
    """Ask output must NOT contain narrative-CLI sections as top-level headings.

    The ask CLI is focused Q&A — users want just the answer. The
    Executive Summary, Data Audit, and Stuff Analysis sections belong
    to the narrative CLI (`pitcher-narratives`), not here.

    The assertions use `\\n# Heading\\n` patterns rather than bare
    `# Heading` to avoid false matches against `## Heading` subsections
    that appear inside the rendered pitcher context (which TestModel
    echoes back from tool calls).
    """
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.ask_cli", "How is Cease pitching?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    # The narrative CLI emits top-level H1 headings with a leading newline,
    # e.g. print("\n\n# Executive Summary\n"). Match that exact pattern so
    # we don't false-positive on H2 data sections.
    assert "\n# Executive Summary\n" not in result.stdout
    assert "\n# Data Audit\n" not in result.stdout
    assert "\n# Stuff Analysis\n" not in result.stdout
    # Also check they're not at the very start of stdout (no leading newline)
    assert not result.stdout.startswith("# Executive Summary")
    assert not result.stdout.startswith("# Data Audit")
    assert not result.stdout.startswith("# Stuff Analysis")


def test_ask_cli_not_found_exit_1():
    """Integration: Non-existent pitcher exits 1 with 'No pitcher found' message."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.ask_cli", "How is Xyzzyplugh pitching?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 1
    assert "No pitcher found" in result.stderr


def test_ask_cli_ambiguous_exit_1():
    """Integration: Ambiguous name exits 1 with disambiguation list."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.ask_cli", "How is Johnson pitching?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 1
    assert "Multiple pitchers matched" in result.stderr
    # Check for numbered list
    assert "1." in result.stderr


def test_ask_cli_no_question_exit_1():
    """Integration: No question argument exits 1 with usage hint."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.ask_cli"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 1
    assert "usage" in result.stderr.lower()


def test_ask_cli_missing_api_key_exit_1():
    """Integration: Missing API key without test model exits 1."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.ask_cli", "How is Cease pitching?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(),
    )
    assert result.returncode == 1
    assert "API_KEY" in result.stderr


def test_ask_cli_provider_flag():
    """Integration: --provider claude accepted with test model, exits 0."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pitcher_narratives.ask_cli",
            "--provider", "claude", "How is Cease pitching?",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0


def test_ask_cli_thinking_flag():
    """Integration: --thinking low accepted with test model, exits 0."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pitcher_narratives.ask_cli",
            "--thinking", "low", "How is Cease pitching?",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0


# ══════════════════════════════════════════════════════════════════════
# CLI-06 / TEST-08: scope guard — pitcher-ask must NOT accept --persona
# ══════════════════════════════════════════════════════════════════════


def test_ask_cli_does_not_accept_persona():
    """TEST-08: --persona on pitcher-ask exits 2 (argparse rejection).

    v1.10 is writer-layer-only: the narrative CLI gets --persona; the
    Q&A CLI does not. Argparse's default behavior rejects unknown flags
    with exit 2 and an "unrecognized arguments" message. This test
    guards against accidental copy-paste of the flag definition into
    ask_cli.py.
    """
    result = subprocess.run(
        [
            sys.executable, "-m", "pitcher_narratives.ask_cli",
            "--persona", "scout", "How is Cease pitching?",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 2
    # Argparse emits "unrecognized arguments: --persona ..." on stderr.
    assert "--persona" in result.stderr or "unrecognized" in result.stderr
