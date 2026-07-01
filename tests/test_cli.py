"""Tests for CLI argument parsing and integration."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from pitcher_narratives.cli import _resolve_modes, parse_args


def test_parse_pitcher_flag(monkeypatch):
    """CLI-01: -p flag accepted and parsed as int."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.pitcher == 592155


def test_parse_pitcher_long_flag(monkeypatch):
    """CLI-01: --pitcher long flag works."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "--pitcher", "592155"])
    args = parse_args()
    assert args.pitcher == 592155


def test_window_default(monkeypatch):
    """CLI-02: -w defaults to 30 when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.window == 30


def test_window_custom(monkeypatch):
    """CLI-02: -w flag overrides default."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155", "-w", "14"])
    args = parse_args()
    assert args.window == 14


def test_verbose_flag_default(monkeypatch):
    """CLI: -v flag defaults to False when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.verbose is False


def test_verbose_flag_set(monkeypatch):
    """CLI: -v flag sets verbose to True."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155", "-v"])
    args = parse_args()
    assert args.verbose is True


def test_provider_default_is_gemini(monkeypatch):
    """Provider defaults to gemini (OpenAI removed)."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.provider == "gemini"


def test_provider_openai_rejected(monkeypatch):
    """--provider openai is no longer a valid choice."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155", "--provider", "openai"])
    with pytest.raises(SystemExit):
        parse_args()


def test_pitcher_required(monkeypatch):
    """CLI-01: Missing -p flag under 'report' subcommand leaves pitcher as None.

    Note: argparse allows -p to be absent (required=False) so that
    --list-personas can run standalone. _run_report_command() re-asserts
    the -p requirement for the normal pipeline path and exits 2.
    """
    monkeypatch.setattr(sys, "argv", ["main.py", "report"])
    args = parse_args()
    # parse_args does not raise — pitcher is None when omitted under report.
    assert args.pitcher is None
    # _run_report_command() exits 2 with a clear error message (verified by
    # test_cli_no_args_shows_help integration test).


# ── Unit: --persona parsing ──


def test_persona_default(monkeypatch):
    """CLI-01/CLI-05: --persona defaults to 'scout' when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.persona == "scout"


def test_persona_flag_accepted(monkeypatch):
    """CLI-01: --persona analyst parses into args.persona."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "report", "-p", "592155", "--persona", "analyst"]
    )
    args = parse_args()
    assert args.persona == "analyst"


def test_persona_case_normalization(monkeypatch):
    """CLI-01: --persona SCOUT normalizes to 'scout' via type=str.lower."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "report", "-p", "592155", "--persona", "SCOUT"]
    )
    args = parse_args()
    assert args.persona == "scout"


def test_persona_invalid_exits_2(monkeypatch):
    """CLI-01: --persona bogus is rejected by argparse with exit code 2."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "report", "-p", "592155", "--persona", "bogus"]
    )
    with pytest.raises(SystemExit) as exc_info:
        parse_args()
    assert exc_info.value.code == 2


def test_list_personas_flag_default(monkeypatch):
    """CLI-02: --list-personas defaults to False when omitted."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.list_personas is False


def test_list_personas_flag_set(monkeypatch):
    """CLI-02: --list-personas sets list_personas True (no -p required)."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "--list-personas"])
    args = parse_args()
    assert args.list_personas is True


def _test_env(**extra: str) -> dict[str, str]:
    """Build a clean subprocess environment with optional overrides.

    Starts from os.environ so PATH and other essentials are preserved,
    then empties every provider API key (tests shouldn't hit the real
    API) and applies any extra key-value pairs.
    """
    strip = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}
    env = {k: v for k, v in os.environ.items() if k not in strip}
    # Set empty keys so load_dotenv() won't fill them from .env
    for key in strip:
        env.setdefault(key, "")
    env.update(extra)
    return env


def test_cli_valid_pitcher_exit_0():
    """Integration: Valid pitcher ID with test model exits 0 and produces output."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
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
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "9999999"],
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
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155", "-w", "7"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0


def test_cli_no_args_shows_help():
    """Integration: No args exits 2 with subcommand-required error.

    With subparsers required=True, argparse exits 2 when no subcommand
    is given. The error message indicates that a subcommand is required.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    # argparse emits a usage error when the required subcommand is absent.
    assert "usage:" in result.stderr


def test_cli_produces_report():
    """Integration: Test model produces non-empty prose report output."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert len(result.stdout.strip()) > 0


def test_cli_unverified_banner_on_residual_flags():
    """Under TestModel the capsule auditor emits synthetic flags every pass, so
    the fact-check loop exhausts with residual flags; the UNVERIFIED banner
    prints to stderr. (The hard exit is suppressed in test mode, so returncode
    stays 0 — the banner is the observable soft-block signal here.)"""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert "REPORT UNVERIFIED" in result.stderr


def test_cli_verbose_shows_pitcher_info():
    """Integration: -v flag shows pitcher name and game dates on stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155", "-v"],
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
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
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
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
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
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert "# Anchor Check" in result.stdout


def test_cli_narrative_output_has_required_sections():
    """Narrative CLI must produce all required sections.

    The narrative report format is:
      1. # Scouting Report       (streamed writer capsule — 'report context')
      2. # Executive Summary     (3 bullets from the summary agent)
      3. # Brief                 (2-3 sentence recent-vs-window summary)
      4. # Stuff Analysis        (the stuff specialist's output)
      5. # Data Audit            (audit flags or 'Clean — no issues found.')
      6. # Capsule Fact-Check    (capsule audit flags or 'Clean — no factual issues found.')

    This test locks the format in. Also verified: # Anchor Check is
    present (separate test above) since it stays in the narrative
    output as a debug/QA section.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
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
    assert "\n# Brief\n" in stdout, "missing Brief heading"
    assert "\n# Stuff Analysis\n" in stdout, "missing Stuff Analysis heading"
    assert "\n# Data Audit\n" in stdout, "missing Data Audit heading"
    assert "\n# Capsule Fact-Check\n" in stdout, "missing Capsule Fact-Check heading"


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
            "report",
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


# ── Integration: --list-personas ──


def test_cli_list_personas_exits_0_without_data():
    """CLI-02: --list-personas exits 0, bypasses data loading and LLM.

    Uses _test_env() with no API key and no PITCHER_NARRATIVES_TEST_MODEL —
    proves the short-circuit is early enough that neither the preflight
    API-key check nor the TestModel path are reached.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "--list-personas"],
        capture_output=True,
        text=True,
        timeout=30,
        env=_test_env(),  # No API key, no TEST_MODEL — proves LLM bypass
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "analyst" in result.stdout
    assert "generic" in result.stdout
    assert "scout" in result.stdout
    # Alphabetical order
    assert (
        result.stdout.index("analyst")
        < result.stdout.index("generic")
        < result.stdout.index("scout")
    )
    # Data loader never ran — no pitcher summary lines landed on stderr.
    assert "Booser" not in result.stderr


def test_cli_list_personas_contains_display_names_and_descriptions():
    """CLI-02: --list-personas output contains display_name and description."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "--list-personas"],
        capture_output=True,
        text=True,
        timeout=30,
        env=_test_env(),
    )
    assert result.returncode == 0
    assert "Newsletter" in result.stdout  # analyst description substring
    assert "Front-office" in result.stdout  # scout description substring
    assert "Structured breakdown" in result.stdout  # generic description


# ── Integration: --persona selection ──


def test_cli_persona_analyst_exits_0():
    """CLI-01: --persona analyst with TestModel completes successfully."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--persona",
            "analyst",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout.strip()) > 0


def test_cli_persona_uppercase_normalizes():
    """CLI-01: --persona SCOUT normalizes via type=str.lower and runs."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--persona",
            "SCOUT",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_cli_invalid_persona_exits_2():
    """CLI-01: --persona bogus exits 2 with choices listed in stderr."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--persona",
            "bogus",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 2
    # argparse lists valid choices in its error message.
    assert "scout" in result.stderr
    assert "analyst" in result.stderr
    assert "generic" in result.stderr


def test_cli_persona_scout_and_no_flag_are_identical():
    """CLI-05: --persona scout and no --persona flag both exit 0.

    Observational equivalence: since TestModel output is canned,
    deeper output equality is fragile. We assert both runs exit 0
    and both stdouts are non-empty. Prompt-level equivalence is
    locked by the unit tests (test_persona_default) and by
    test_cli_print_prompts_uses_selected_persona.
    """
    run_args = {
        "capture_output": True,
        "text": True,
        "timeout": 60,
        "env": _test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    }
    no_flag = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
        **run_args,
    )
    with_scout = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--persona",
            "scout",
        ],
        **run_args,
    )
    assert no_flag.returncode == 0, f"stderr: {no_flag.stderr}"
    assert with_scout.returncode == 0, f"stderr: {with_scout.stderr}"
    assert no_flag.stdout.strip()
    assert with_scout.stdout.strip()


# ── Integration: verbose persona logging ──


def test_cli_verbose_logs_persona():
    """CLI-04: -v logs persona=<id> to stderr."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "-v",
            "--persona",
            "analyst",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "persona=analyst" in result.stderr


def test_cli_no_verbose_no_persona_log():
    """CLI-04: without -v, stderr does NOT contain the persona= log line."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--persona",
            "analyst",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "persona=analyst" not in result.stderr


# ── Integration: --print-prompts renders the selected persona ──


def test_cli_print_prompts_uses_selected_persona(tmp_path):
    """CLI-03: --print-prompts renders the SELECTED persona's writer prompt."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--persona",
            "analyst",
            "--print-prompts",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        env=_test_env(),  # --print-prompts bypasses API-key check
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Analyst overlay uniquely mentions "newsletter" voice.
    assert "newsletter" in result.stderr.lower()
    # Sanity: generic-only structural marker must NOT appear.
    assert "## Summary Table" not in result.stderr


def test_cli_print_prompts_uses_generic_persona(tmp_path):
    """CLI-03: --print-prompts --persona generic renders the generic overlay."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--persona",
            "generic",
            "--print-prompts",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        env=_test_env(),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Generic overlay's unique structural marker.
    assert "## Summary Table" in result.stderr


# ── Subcommand routing ──────────────────────────────────────────────


def test_bare_invocation_errors(monkeypatch):
    """Without a subcommand, argparse exits with a usage error."""
    monkeypatch.setattr(sys, "argv", ["cli"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_old_style_invocation_errors(monkeypatch):
    """Pre-subcommand style 'cli -p 123' is rejected with a usage error."""
    monkeypatch.setattr(sys, "argv", ["cli", "-p", "123"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_report_subcommand_parses(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "report", "-p", "123"])
    args = parse_args()
    assert args.command == "report"
    assert args.pitcher == 123
    assert args.window == 30


# ── --mode scaffolding (G9/G4, phase 4: single-mode only) ──────────


def test_mode_flag_defaults_to_none(monkeypatch):
    """No --mode passed; argparse default is None (resolved by _resolve_modes)."""
    monkeypatch.setattr(sys, "argv", ["cli", "report", "-p", "592155"])
    args = parse_args()
    assert args.mode is None


def test_resolve_modes_defaults_to_report():
    from pitcher_narratives.personas import REPORT

    assert _resolve_modes(None) == [REPORT]


def test_resolve_modes_report_explicit():
    from pitcher_narratives.personas import REPORT

    assert _resolve_modes("report") == [REPORT]


def test_mode_flag_rejects_unavailable_mode():
    """--mode changes is rejected in phase 4 (only 'report' is registered)."""
    with pytest.raises(SystemExit) as exc:
        _resolve_modes("changes")
    assert exc.value.code == 2


def test_mode_flag_rejects_empty_value():
    """A non-None but empty --mode (e.g. ',' or ' ') exits 2, not a silent report."""
    for raw in (",", " ", " , "):
        with pytest.raises(SystemExit) as exc:
            _resolve_modes(raw)
        assert exc.value.code == 2


def test_morning_subcommand_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "morning"])
    args = parse_args()
    assert args.command == "morning"
    assert args.window == 1
    assert args.candidates == 25
    assert args.min_pitches == 20
    assert args.provider == "gemini"
    assert args.persona == "scout"
    assert args.out == "morning-runs"
