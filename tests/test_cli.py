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


# ── Unit: --persona parsing ──


def test_persona_default(monkeypatch):
    """CLI-01/CLI-05: --persona defaults to 'scout' when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "-p", "592155"])
    args = parse_args()
    assert args.persona == "scout"


def test_persona_flag_accepted(monkeypatch):
    """CLI-01: --persona analyst parses into args.persona."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "-p", "592155", "--persona", "analyst"]
    )
    args = parse_args()
    assert args.persona == "analyst"


def test_persona_case_normalization(monkeypatch):
    """CLI-01: --persona SCOUT normalizes to 'scout' via type=str.lower."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "-p", "592155", "--persona", "SCOUT"]
    )
    args = parse_args()
    assert args.persona == "scout"


def test_persona_invalid_exits_2(monkeypatch):
    """CLI-01: --persona bogus is rejected by argparse with exit code 2."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "-p", "592155", "--persona", "bogus"]
    )
    with pytest.raises(SystemExit) as exc_info:
        parse_args()
    assert exc_info.value.code == 2


def test_list_personas_flag_default(monkeypatch):
    """CLI-02: --list-personas defaults to False when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "-p", "592155"])
    args = parse_args()
    assert args.list_personas is False


def test_list_personas_flag_set(monkeypatch):
    """CLI-02: --list-personas sets list_personas True (no -p required)."""
    monkeypatch.setattr(sys, "argv", ["main.py", "--list-personas"])
    args = parse_args()
    assert args.list_personas is True


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


def test_cli_narrative_output_has_required_sections():
    """Narrative CLI must produce all four required sections.

    The narrative report format is:
      1. # Scouting Report       (streamed writer capsule — 'report context')
      2. # Executive Summary     (3 bullets from the summary agent)
      3. # Stuff Analysis        (the stuff specialist's output)
      4. # Data Audit            (audit flags or 'Clean — no issues found.')

    This test locks the format in. Also verified: # Anchor Check is
    present (separate test above) since it stays in the narrative
    output as a debug/QA section.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Use "\n# Heading\n" pattern to avoid false matches on "## Heading"
    # data subsections that may appear in the narrative prose.
    stdout = "\n" + result.stdout  # prepend so leading headings match

    assert "\n# Scouting Report\n" in stdout, "missing Scouting Report heading"
    assert "\n# Executive Summary\n" in stdout, "missing Executive Summary heading"
    assert "\n# Stuff Analysis\n" in stdout, "missing Stuff Analysis heading"
    assert "\n# Data Audit\n" in stdout, "missing Data Audit heading"


# ── Integration: --print-prompts ──


def test_cli_print_prompts_dumps_prompts_and_bypasses_api_key(tmp_path):
    """--print-prompts exits 0, dumps pipeline prompts to stderr, bypasses API key check.

    Uses _test_env() which has no API key set — proves the flag bypasses
    the preflight (the normal path would exit 1 with 'API_KEY not set').
    """
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
        env=_test_env(),  # No API key, no test model
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # The normal path would have logged "API_KEY not set" and exit 1.
    # --print-prompts must not trigger that branch.
    assert "API_KEY not set" not in result.stderr
    # Stdout should not contain the report — the LLM was never called.
    assert "# Scouting Report" not in result.stdout
    # Stderr should contain the specialist prompts that --print-prompts dumps.
    assert "SPECIALIST 1: STUFF" in result.stderr
    assert "WRITER" in result.stderr
    assert "ANCHOR CHECK" in result.stderr
