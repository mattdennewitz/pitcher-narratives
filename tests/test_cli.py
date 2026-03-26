"""Tests for CLI argument parsing and integration."""

from __future__ import annotations

import subprocess
import sys

import pytest

from main import parse_args


def test_parse_pitcher_flag():
    """CLI-01: -p flag accepted and parsed as int."""
    sys.argv = ["main.py", "-p", "592155"]
    args = parse_args()
    assert args.pitcher == 592155


def test_parse_pitcher_long_flag():
    """CLI-01: --pitcher long flag works."""
    sys.argv = ["main.py", "--pitcher", "592155"]
    args = parse_args()
    assert args.pitcher == 592155


def test_window_default():
    """CLI-02: -w defaults to 30 when omitted."""
    sys.argv = ["main.py", "-p", "592155"]
    args = parse_args()
    assert args.window == 30


def test_window_custom():
    """CLI-02: -w flag overrides default."""
    sys.argv = ["main.py", "-p", "592155", "-w", "14"]
    args = parse_args()
    assert args.window == 14


def test_pitcher_required():
    """CLI-01: Missing -p flag causes SystemExit (argparse error)."""
    sys.argv = ["main.py"]
    with pytest.raises(SystemExit) as exc_info:
        parse_args()
    assert exc_info.value.code == 2


def test_cli_valid_pitcher_exit_0():
    """Integration: Valid pitcher ID exits 0 and produces output."""
    result = subprocess.run(
        [sys.executable, "main.py", "-p", "592155"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "Booser, Cam" in result.stdout
    assert "appearances" in result.stdout


def test_cli_invalid_pitcher_exit_1():
    """Integration: Invalid pitcher ID exits 1 with error message."""
    result = subprocess.run(
        [sys.executable, "main.py", "-p", "9999999"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 1
    assert "Pitcher 9999999 not found" in result.stderr


def test_cli_custom_window():
    """Integration: -w flag changes lookback window."""
    result = subprocess.run(
        [sys.executable, "main.py", "-p", "592155", "-w", "7"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "7d window" in result.stdout


def test_cli_no_args_shows_help():
    """Integration: No args shows usage and exits 2."""
    result = subprocess.run(
        [sys.executable, "main.py"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr.lower()


def test_cli_output_has_role():
    """ROLE-02: Output includes role information."""
    result = subprocess.run(
        [sys.executable, "main.py", "-p", "592155"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "Roles:" in result.stdout
    # Booser has both SP and RP
    assert "SP" in result.stdout
    assert "RP" in result.stdout
