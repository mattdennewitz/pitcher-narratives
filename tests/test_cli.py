"""Tests for CLI argument parsing and integration."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from pitcher_narratives.cli import parse_args


def test_parse_pitcher_flag(monkeypatch):
    """CLI-01: -p flag accepted and parsed as int."""
    monkeypatch.setattr(sys, "argv", ["main.py", "-p", "592155"])
    args = parse_args()
    assert args.pitcher == 592155


def test_parse_pitcher_long_flag(monkeypatch):
    """CLI-01: --pitcher long flag works."""
    monkeypatch.setattr(sys, "argv", ["main.py", "--pitcher", "592155"])
    args = parse_args()
    assert args.pitcher == 592155


def test_window_default(monkeypatch):
    """CLI-02: -w defaults to 30 when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "-p", "592155"])
    args = parse_args()
    assert args.window == 30


def test_window_custom(monkeypatch):
    """CLI-02: -w flag overrides default."""
    monkeypatch.setattr(sys, "argv", ["main.py", "-p", "592155", "-w", "14"])
    args = parse_args()
    assert args.window == 14


def test_verbose_flag_default(monkeypatch):
    """CLI: -v flag defaults to False when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "-p", "592155"])
    args = parse_args()
    assert args.verbose is False


def test_verbose_flag_set(monkeypatch):
    """CLI: -v flag sets verbose to True."""
    monkeypatch.setattr(sys, "argv", ["main.py", "-p", "592155", "-v"])
    args = parse_args()
    assert args.verbose is True


def test_pitcher_required(monkeypatch):
    """CLI-01: Missing -p flag causes SystemExit (argparse error)."""
    monkeypatch.setattr(sys, "argv", ["main.py"])
    with pytest.raises(SystemExit) as exc_info:
        parse_args()
    assert exc_info.value.code == 2


def _test_env(**extra: str) -> dict[str, str]:
    """Build a clean subprocess environment with optional overrides.

    Starts from os.environ so PATH and other essentials are preserved,
    then removes ANTHROPIC_API_KEY (tests shouldn't hit the real API)
    and applies any extra key-value pairs.
    """
    strip = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"}
    env = {k: v for k, v in os.environ.items() if k not in strip}
    # Set empty keys so load_dotenv() won't fill them from .env
    env.setdefault("ANTHROPIC_API_KEY", "")
    env.setdefault("OPENAI_API_KEY", "")
    env.update(extra)
    return env


def test_cli_valid_pitcher_exit_0():
    """Integration: Valid pitcher ID with test model exits 0 and produces output."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert result.stdout.strip()  # Non-empty output


def test_cli_invalid_pitcher_exit_1():
    """Integration: Invalid pitcher ID exits 1 with error message."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "9999999"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 1
    assert "Pitcher 9999999 not found" in result.stderr


def test_cli_custom_window():
    """Integration: -w flag changes lookback window (pipeline completes)."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155", "-w", "7"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0


def test_cli_no_args_shows_help():
    """Integration: No args shows usage and exits 2."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr.lower()


def test_cli_produces_report():
    """Integration: Test model produces non-empty prose report output."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert len(result.stdout.strip()) > 0


def test_cli_verbose_shows_pitcher_info():
    """Integration: -v flag shows pitcher name and game dates on stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155", "-v"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert "Booser, Cam" in result.stderr
    assert "Total" in result.stderr
    # Should still produce the report on stdout
    assert len(result.stdout.strip()) > 0


def test_cli_no_verbose_no_pitcher_info():
    """Integration: Without -v, stderr does not contain pitcher summary."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert "Booser, Cam" not in result.stderr


def test_cli_missing_api_key():
    """Integration: Missing API key without test model exits 1."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(),
    )
    assert result.returncode == 1
    assert "API_KEY" in result.stderr


# ── Integration: revision status in output ──


def test_cli_anchor_check_in_output():
    """Integration: Anchor check section appears in stdout output."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert "# Anchor Check" in result.stdout


# ── Integration: --print-prompts ──


def test_cli_print_prompts_exits_zero(tmp_path):
    """--print-prompts exits 0 and dumps pipeline prompts to stderr without calling LLM."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "-p",
            "592155",
            "--print-prompts",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,  # keep the data file out of the repo root
        env=_test_env(),  # No API key, no test model — --print-prompts must not need them
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Stdout should be empty (or nothing meaningful) — the report was never generated
    assert "# Scouting Report" not in result.stdout
    # Stderr should contain the specialist prompts that --print-prompts dumps
    assert "SPECIALIST 1: STUFF" in result.stderr
    assert "WRITER" in result.stderr
    assert "ANCHOR CHECK" in result.stderr


def test_cli_print_prompts_bypasses_api_key_check(tmp_path):
    """--print-prompts must work without any API key set (no LLM call happens)."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "-p",
            "592155",
            "--print-prompts",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        env=_test_env(),
    )
    # With no API key, the normal path exits 1 with "API_KEY not set".
    # --print-prompts must bypass that check and exit 0.
    assert result.returncode == 0
    assert "API_KEY" not in result.stderr or "not set" not in result.stderr
