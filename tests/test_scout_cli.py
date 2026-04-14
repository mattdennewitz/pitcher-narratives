"""Tests for pitcher-scout CLI argument parsing and scope-guard coverage.

Covers basic parse_args smoke tests (previously uncovered) and the
TEST-08 scope guard asserting that --persona is rejected (v1.10 is
writer-layer-only).
"""

from __future__ import annotations

import os
import subprocess
import sys

from pitcher_narratives.scout_cli import parse_args


# ── Helper ──


def _test_env(**extra: str) -> dict[str, str]:
    """Build a clean subprocess environment with optional overrides.

    Strips API keys so tests never hit a real provider, then applies
    extras. Mirrors the helper in tests/test_cli.py and tests/test_ask_cli.py.
    """
    strip = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}
    env = {k: v for k, v in os.environ.items() if k not in strip}
    env.setdefault("ANTHROPIC_API_KEY", "")
    env.setdefault("OPENAI_API_KEY", "")
    env.setdefault("GEMINI_API_KEY", "")
    env.update(extra)
    return env


# ══════════════════════════════════════════════════════════════════════
# UNIT TESTS: parse_args
# ══════════════════════════════════════════════════════════════════════


def test_parse_window_default(monkeypatch):
    """-w defaults to 1 day when omitted."""
    monkeypatch.setattr(sys, "argv", ["scout_cli"])
    args = parse_args()
    assert args.window == 1


def test_parse_window_flag(monkeypatch):
    """-w flag overrides default."""
    monkeypatch.setattr(sys, "argv", ["scout_cli", "-w", "7"])
    args = parse_args()
    assert args.window == 7


def test_parse_top_default(monkeypatch):
    """-n defaults to 20."""
    monkeypatch.setattr(sys, "argv", ["scout_cli"])
    args = parse_args()
    assert args.top == 20


def test_parse_top_flag(monkeypatch):
    """-n flag overrides default."""
    monkeypatch.setattr(sys, "argv", ["scout_cli", "-n", "5"])
    args = parse_args()
    assert args.top == 5


def test_parse_verbose_flag(monkeypatch):
    """-v sets verbose True."""
    monkeypatch.setattr(sys, "argv", ["scout_cli", "-v"])
    args = parse_args()
    assert args.verbose is True


# ══════════════════════════════════════════════════════════════════════
# CLI-06 / TEST-08: scope guard — pitcher-scout must NOT accept --persona
# ══════════════════════════════════════════════════════════════════════


def test_scout_cli_does_not_accept_persona():
    """TEST-08: --persona on pitcher-scout exits 2 (argparse rejection).

    v1.10 is writer-layer-only: the narrative CLI gets --persona; the
    scout scanner is a no-LLM signal tool and does not. Argparse's
    default behavior rejects unknown flags with exit 2 and an
    "unrecognized arguments" message. This test guards against
    accidental copy-paste of the flag definition into scout_cli.py.
    """
    result = subprocess.run(
        [
            sys.executable, "-m", "pitcher_narratives.scout_cli",
            "--persona", "scout",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=_test_env(),
    )
    assert result.returncode == 2
    # Argparse emits "unrecognized arguments: --persona ..." on stderr.
    assert "--persona" in result.stderr or "unrecognized" in result.stderr
