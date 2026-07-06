"""Tests for CLI argument parsing and integration."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from pitcher_narratives.cli import _resolve_modes, parse_args


def _scored(pid, name, role, score, throws="R"):
    from datetime import date

    from pitcher_narratives.scout import ScoredAppearance

    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=name, throws=throws,
        game_date=date(2026, 7, 4), game_pk=pid, n_pitches=90, score=score, role=role,
    )


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


def test_report_accepts_recent_appearance_count(monkeypatch):
    """-n/--recent parses as an int appearance count."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155", "--recent", "5"])
    args = parse_args()
    assert args.recent == 5


def test_report_recent_defaults_to_appearance_span(monkeypatch):
    """--recent defaults to the empirically-derived appearance count, not 30."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.recent >= 10


def test_report_subcommand_accepts_prior_flag(monkeypatch):
    """--prior parses as an int prior-window appearance count."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "report", "-p", "592155", "--mode", "changes", "--prior", "8"]
    )
    args = parse_args()
    assert args.prior == 8


def test_report_prior_defaults(monkeypatch):
    """--prior defaults to _DEFAULT_PRIOR_APPEARANCES (10)."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155", "--mode", "changes"])
    args = parse_args()
    assert args.prior == 10  # _DEFAULT_PRIOR_APPEARANCES


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

    Note: argparse allows -p to be absent (required=False); _run_report_command()
    re-asserts the -p requirement for the normal pipeline path and exits 2.
    """
    monkeypatch.setattr(sys, "argv", ["main.py", "report"])
    args = parse_args()
    # parse_args does not raise — pitcher is None when omitted under report.
    assert args.pitcher is None
    # _run_report_command() exits 2 with a clear error message (verified by
    # test_cli_no_args_shows_help integration test).


def test_persona_flag_no_longer_recognized(monkeypatch):
    """--persona/--list-personas were removed (Task 4, single-voice refactor);
    argparse now rejects both as unrecognized arguments."""
    monkeypatch.setattr(
        sys, "argv", ["main.py", "report", "-p", "592155", "--persona", "scout"]
    )
    with pytest.raises(SystemExit) as exc_info:
        parse_args()
    assert exc_info.value.code == 2


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


def test_cli_report_runs_with_no_persona_flag():
    """Smoke test (Task 4): `report` has no --persona flag anymore; the
    subcommand still runs to completion and produces output with just -p."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip()
    assert "--persona" not in result.stderr


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


def test_cli_custom_recent():
    """Integration: -n flag changes recent-appearances window (pipeline completes)."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155", "-n", "7"],
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


def test_cli_duplicate_mode_emits_sections_once():
    """A repeated mode id is deduped: `--mode report,report` runs the LLM once
    (run_narration_modes collapses by mode.id) and the emit loop must not
    double-print sections or the UNVERIFIED banner for the single result."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "report,report"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.count("# Executive Summary") == 1
    assert result.stderr.count("REPORT UNVERIFIED") == 1


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
    """Integration: Anchor check section appears in stderr output under -v."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155", "-v"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0
    assert "### Anchor Check" in result.stderr
    assert "### Anchor Check" not in result.stdout


def test_cli_narrative_output_has_required_sections():
    """Locks in the reader-first report format:

      1. # Scouting Report        (mode title H1, buffered capsule)
      2. **Verification:** line   (in-document verification stamp)
      3. ## Executive Summary     (distilled bullets)
      4. ## Diagnostics (stderr, under -v)
      5. ### Stuff Analysis / ### Data Audit / ### Capsule Fact-Check /
         ### Anchor Check         (demoted to appendix subsections)
    """
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155", "-v"],
        capture_output=True, text=True, timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    stdout = "\n" + result.stdout
    stderr = "\n" + result.stderr

    assert "\n# Scouting Report\n" in stdout
    assert "\n**Verification:**" in stdout
    assert "\n## Executive Summary\n" in stdout
    assert "\n## Brief\n" not in stdout             # the separate brief was removed
    assert "\n## Diagnostics\n" not in stdout       # off the reader stream
    assert "\n## Diagnostics\n" in stderr            # -v surfaces it
    assert "\n### Stuff Analysis\n" in stderr
    assert "\n### Data Audit\n" in stderr
    assert "\n### Capsule Fact-Check\n" in stderr
    assert "\n### Anchor Check\n" in stderr


def test_cli_mode_blocks_are_labeled_and_contiguous():
    """Multi-mode runs emit one labeled contiguous block per mode: each mode's
    H1 title is followed by ITS diagnostics before the next mode's H1."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155",
         "--mode", "report,changes", "-v"],
        capture_output=True, text=True, timeout=120,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    stdout = result.stdout
    i_report = stdout.index("# Scouting Report")
    i_changes = stdout.index("# Change Report")
    assert i_report < i_changes
    assert "## Diagnostics" not in stdout
    # Add -v to the argv above; both modes' diagnostics land on stderr.
    assert result.stderr.count("## Diagnostics") == 2


def test_cli_recap_mode_has_no_summary_or_brief_sections():
    """Recap's capsule IS the brief — no Executive Summary / Brief sections."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155",
         "--mode", "recap"],
        capture_output=True, text=True, timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "# Recap" in result.stdout
    assert "## Executive Summary" not in result.stdout
    assert "## Brief" not in result.stdout
    assert "**Verification:**" in result.stdout
    assert "## Diagnostics" not in result.stdout


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


def test_cli_print_prompts_changes_mode_includes_trend_comparison(tmp_path):
    """--print-prompts --mode changes includes the Recent vs Prior Window block."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitcher_narratives.cli",
            "report",
            "-p",
            "592155",
            "--mode",
            "changes",
            "--recent",
            "10",
            "--prior",
            "10",
            "--print-prompts",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        env=_test_env(),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Recent vs Prior Window" in result.stderr


def test_cli_print_prompts_report_mode_omits_trend_comparison(tmp_path):
    """--print-prompts on default (report) mode does NOT include the comparison block."""
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
        cwd=tmp_path,
        env=_test_env(),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Recent vs Prior Window" not in result.stderr


# ── Integration: --print-prompts renders the single voice ──


def test_cli_print_prompts_dump_is_single_voice(tmp_path):
    """The prompt dump renders the single mode-composed writer voice: the old
    persona-specific structures (e.g. the generic voice's "## Summary Table")
    no longer appear. --persona is gone (Task 4); there is only one voice."""
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
        cwd=tmp_path,
        env=_test_env(),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # The single writer voice is dumped (shared analytical rules preamble)...
    assert "ANALYTICAL RULES" in result.stderr
    # ...and the removed generic-voice structure is gone.
    assert "## Summary Table" not in result.stderr


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
    assert args.recent == 10


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
    """An unregistered mode id still exits 2 via _resolve_modes."""
    with pytest.raises(SystemExit) as exc:
        _resolve_modes("bogus")
    assert exc.value.code == 2


def test_mode_flag_resolves_changes():
    from pitcher_narratives.personas import CHANGES

    assert _resolve_modes("changes") == [CHANGES]


def test_mode_flag_rejects_empty_value():
    """A non-None but empty --mode (e.g. ',' or ' ') exits 2, not a silent report."""
    for raw in (",", " ", " , "):
        with pytest.raises(SystemExit) as exc:
            _resolve_modes(raw)
        assert exc.value.code == 2


def _pipe_result_with_flags(n: int):
    """Minimal PipelineResult carrying n residual capsule-audit flags.

    Mirrors tests/test_pipeline.py::_result_with_flags.
    """
    from pitcher_narratives.pipeline import AuditFlag, PipelineResult, SpecialistOutputs

    flags = [
        AuditFlag(category="velocity", specialist="stuff", claim=f"c{i}", data_shows="d", suggested_fix="")
        for i in range(n)
    ]
    return PipelineResult(
        narrative="x",
        specialists=SpecialistOutputs(
            stuff="", location="", runvalue="", trends="", game_shape=""
        ),
        capsule_audit_flags=flags,
    )


def test_emit_mode_result_returns_unverified_status(capsys):
    """_emit_mode_result returns is_unverified(result) — False when clean, True when flagged."""
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    clean = _pipe_result_with_flags(0)
    flagged = _pipe_result_with_flags(2)

    assert _emit_mode_result(clean, mode=REPORT)[0] is False
    assert _emit_mode_result(flagged, mode=REPORT)[0] is True
    capsys.readouterr()  # absorb printed sections


def test_emit_prints_capsule_once_and_no_corrected_section(capsys):
    """The final narrative prints exactly once; no separate 'Corrected Capsule'."""
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT
    from pitcher_narratives.pipeline import PipelineResult, SpecialistOutputs

    result = PipelineResult(
        narrative="THE FINAL CAPSULE BODY",
        specialists=SpecialistOutputs(
            stuff="s", location="", runvalue="", trends="", game_shape=""
        ),
        capsule_revised=True,  # previously triggered a second '## Corrected Capsule'
    )
    _emit_mode_result(result, mode=REPORT)
    out = capsys.readouterr().out
    assert out.count("THE FINAL CAPSULE BODY") == 1
    assert "Corrected Capsule" not in out


def test_emit_mode_result_empty_narrative_is_not_unverified(capsys):
    """Empty narrative always returns False, even with residual audit flags.

    Pins the pre-Phase-7 behavior: an empty narrative means the pipeline
    produced nothing to verify, so the REPORT command exits 0 with no
    UNVERIFIED banner — regardless of leftover capsule_audit_flags.
    """
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT
    from pitcher_narratives.pipeline import AuditFlag, PipelineResult, SpecialistOutputs

    flags = [
        AuditFlag(category="velocity", specialist="stuff", claim=f"c{i}", data_shows="d", suggested_fix="")
        for i in range(2)
    ]
    result = PipelineResult(
        narrative="",
        specialists=SpecialistOutputs.model_construct(
            stuff="", location="", runvalue="", trends="", game_shape=""
        ),
        capsule_audit_flags=flags,
    )

    assert _emit_mode_result(result, mode=REPORT)[0] is False
    capsys.readouterr()


def test_emit_mode_result_runs_hallucination_guard_for_any_mode(capsys, monkeypatch):
    """_emit_mode_result invokes check_hallucinated_metrics unconditionally.

    The guard runs regardless of the mode passed, so the single call site at
    cli.py's report-command dispatch loop already covers every selected
    narration mode (report, changes, recap) identically — there is no per-mode
    gate to bypass the guard.
    """
    import pitcher_narratives.cli as cli_module

    from pitcher_narratives.personas import REPORT

    calls = []
    from pitcher_narratives import pipeline as pipeline_module

    def _spy(text):
        calls.append(text)
        return pipeline_module.HallucinationReport(unknown_metrics=[], outcome_stat_warnings=[])

    monkeypatch.setattr(pipeline_module, "check_hallucinated_metrics", _spy)

    clean = _pipe_result_with_flags(0)
    cli_module._emit_mode_result(clean, mode=REPORT)
    capsys.readouterr()

    assert len(calls) == 1
    assert calls[0] == clean.narrative


def _diag_pipe_result(*, narrative="cap", revised=False, fact_flags=0):
    from pitcher_narratives.pipeline import AuditFlag, PipelineResult, SpecialistOutputs

    flags = [
        AuditFlag(category="velocity", specialist="stuff", claim=f"c{i}",
                  data_shows="d", suggested_fix="")
        for i in range(fact_flags)
    ]
    return PipelineResult(
        narrative=narrative,
        specialists=SpecialistOutputs(
            stuff="STUFF-TEXT", location="", runvalue="", trends="", game_shape=""
        ),
        capsule_revised=revised,
        capsule_audit_flags=flags,
    )


def test_build_diagnostics_dict_shape():
    from pitcher_narratives.cli import build_diagnostics_dict

    diag = build_diagnostics_dict(_diag_pipe_result(fact_flags=2, revised=True))
    assert diag["verified"] is False  # residual fact flags -> unverified
    assert diag["capsule_revised"] is True
    assert diag["stuff_analysis"] == "STUFF-TEXT"
    assert len(diag["capsule_fact_check"]) == 2
    assert diag["hallucination"] == {"unknown_metrics": [], "outcome_stat_warnings": []}


def test_build_diagnostics_dict_skips_guard_on_empty_narrative(monkeypatch):
    """No hallucination guard call when there's nothing to check."""
    from pitcher_narratives import pipeline as pipeline_module
    from pitcher_narratives.cli import build_diagnostics_dict

    calls = []
    monkeypatch.setattr(
        pipeline_module, "check_hallucinated_metrics",
        lambda text: calls.append(text)
        or pipeline_module.HallucinationReport(unknown_metrics=[], outcome_stat_warnings=[]),
    )
    build_diagnostics_dict(_diag_pipe_result(narrative=""))
    assert calls == []


def test_render_diagnostics_text_has_sections():
    from pitcher_narratives.cli import build_diagnostics_dict, render_diagnostics_text

    text = render_diagnostics_text(build_diagnostics_dict(_diag_pipe_result()))
    assert "## Diagnostics" in text
    assert "### Stuff Analysis" in text
    assert "### Data Audit" in text
    assert "### Capsule Fact-Check" in text
    assert "### Anchor Check" in text


def test_emit_default_stdout_has_no_diagnostics(capsys):
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    _emit_mode_result(_diag_pipe_result(), mode=REPORT, verbose=False)
    captured = capsys.readouterr()
    assert "## Diagnostics" not in captured.out
    assert "## Diagnostics" not in captured.err  # not verbose -> nowhere


def test_emit_verbose_puts_diagnostics_on_stderr(capsys):
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    _emit_mode_result(_diag_pipe_result(), mode=REPORT, verbose=True)
    captured = capsys.readouterr()
    assert "## Diagnostics" not in captured.out
    assert "## Diagnostics" in captured.err
    assert "### Anchor Check" in captured.err


def test_emit_returns_unverified_and_diag_dict(capsys):
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    unverified, diag = _emit_mode_result(
        _diag_pipe_result(fact_flags=2), mode=REPORT
    )
    capsys.readouterr()
    assert unverified is True
    assert isinstance(diag, dict) and "verified" in diag


def test_morning_subcommand_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "morning"])
    args = parse_args()
    assert args.command == "morning"
    assert args.window == 1
    assert args.candidates == 25
    assert args.min_pitches == 20
    assert args.provider == "gemini"
    assert args.out == "morning-runs"
    assert args.strict is False


def test_morning_parser_accepts_strict_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "morning", "--strict"])
    args = parse_args()
    assert args.strict is True


def test_cli_recap_mode_runs_and_produces_output():
    """`report --mode recap` renders a recap through the full validation stack
    and exits cleanly under TestModel."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "recap"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Recap's capsule is already a brief, so it skips the distilled
    # Executive Summary / Brief sections but still labels its block and
    # produces a non-empty narrative body.
    assert len(result.stdout.strip()) > 0
    assert "# Recap" in result.stdout
    assert "## Executive Summary" not in result.stdout


def test_cli_changes_mode_runs_and_produces_output():
    """`report --mode changes` renders through the full validation stack and
    exits cleanly under TestModel."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "changes"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout.strip()) > 0
    assert "# Executive Summary" in result.stdout


def test_cli_changes_two_frame_runs():
    """`report --mode changes --recent N --prior M` runs the two-frame
    CHANGES engine end-to-end and exits cleanly under TestModel."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "changes",
         "--recent", "10", "--prior", "10"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout.strip()) > 0
    assert "# Executive Summary" in result.stdout


def test_cli_report_and_recap_both_run():
    """`--mode report,recap` runs both modes; the process completes."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "report,recap"],
        capture_output=True,
        text=True,
        timeout=90,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout.strip()) > 0


def test_cli_report_changes_recap_all_run():
    """`--mode report,changes,recap` runs all three modes; the process
    completes. Only the distilling modes (report, changes) emit an Executive
    Summary section — recap's capsule is already a brief, so it skips it."""
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli",
         "report", "-p", "592155", "--mode", "report,changes,recap"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Two distilling modes (report, changes) → two Executive Summary sections;
    # recap does not distill.
    assert result.stdout.count("## Executive Summary") == 2


def test_report_writes_diagnostics_json_file(tmp_path):
    out = tmp_path / "diag.json"
    result = subprocess.run(
        [sys.executable, "-m", "pitcher_narratives.cli", "report", "-p", "592155",
         "--diagnostics-file", str(out)],
        capture_output=True, text=True, timeout=60,
        env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    import json
    payload = json.loads(out.read_text())
    assert "report" in payload
    assert "verified" in payload["report"]
    assert "## Diagnostics" not in result.stdout  # sidecar, not stdout


def test_report_parser_metrics_out_defaults_none(monkeypatch):
    """--metrics-out is off by default (no calibration output unless opted in)."""
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.metrics_out is None


def test_report_parse_diagnostics_file(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "report", "-p", "1", "--diagnostics-file", "d.json"])
    args = parse_args()
    assert args.diagnostics_file == "d.json"


def test_report_diagnostics_file_default_none(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli", "report", "-p", "1"])
    args = parse_args()
    assert args.diagnostics_file is None


def test_append_metrics_records_writes_jsonl(tmp_path):
    """_append_metrics_records writes one flag_record JSON line per mode."""
    import json

    from pitcher_narratives.cli import _append_metrics_records
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.personas import RECAP, REPORT
    from pitcher_narratives.pipeline import PipelineResult

    def _r(rev):
        return PipelineResult(
            narrative="x",
            specialists=SpecialistOutputs(
                stuff="", location="", runvalue="", trends="", game_shape=""
            ),
            revision_count=rev,
        )

    out = tmp_path / "metrics.jsonl"

    _append_metrics_records(
        out,
        pitcher_id=592155,
        span=10,
        modes=[REPORT, RECAP],
        results={"report": _r(4), "recap": _r(1)},
    )
    _append_metrics_records(
        out,
        pitcher_id=592155,
        span=10,
        modes=[REPORT],
        results={"report": _r(2)},
    )

    lines = out.read_text().splitlines()
    assert len(lines) == 3
    recs = [json.loads(x) for x in lines]

    assert recs[0]["revision_count"] == 4
    assert recs[0]["anchor_depth_cap"] == REPORT.validation.anchor_depth  # REPORT: 5
    assert recs[1]["anchor_depth_cap"] == RECAP.validation.anchor_depth  # RECAP: 1


def test_report_no_explain_model_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155", "--no-explain-model"])
    args = parse_args()
    assert args.explain_model is False


def test_report_explain_model_defaults_true(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "report", "-p", "592155"])
    args = parse_args()
    assert args.explain_model is True


# ── scoreboard subcommand ──


def _scoreboard_args(**over):
    import argparse

    base = dict(
        window=1, min_pitches=20, starters_only=False, format="md",
        top=0, min_score=0.0, verbose=False, curate=False, provider="gemini",
    )
    base.update(over)
    return argparse.Namespace(**base)


def test_scoreboard_parse_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "scoreboard"])
    args = parse_args()
    assert args.command == "scoreboard"
    assert args.window == 1
    assert args.min_pitches == 20
    assert args.starters_only is False
    assert args.format == "md"
    assert args.top == 0
    assert args.min_score == 0.0
    assert args.verbose is False
    assert args.curate is False
    assert args.provider == "gemini"


def test_scoreboard_parse_flags(monkeypatch):
    monkeypatch.setattr(
        sys, "argv",
        ["main.py", "scoreboard", "-w", "3", "--min-pitches", "10", "--starters-only"],
    )
    args = parse_args()
    assert (args.window, args.min_pitches, args.starters_only) == (3, 10, True)


def test_scoreboard_prints_full_board(monkeypatch, capsys):
    """scoreboard prints the render_full_board markdown, no LLM."""
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0), _scored(2, "Setup RP", "RP", 6.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    _run_scoreboard_command(_scoreboard_args())
    out = capsys.readouterr().out
    assert "# Scoreboard — 2026-07-04" in out
    assert "## The Full Board" in out
    assert "Ace SP" in out and "Setup RP" in out


def test_scoreboard_starters_only_drops_relievers(monkeypatch, capsys):
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0), _scored(2, "Setup RP", "RP", 6.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    _run_scoreboard_command(_scoreboard_args(starters_only=True))
    out = capsys.readouterr().out
    assert "Ace SP" in out
    assert "Setup RP" not in out


def test_scoreboard_quiet_day(monkeypatch, capsys):
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: [])
    _run_scoreboard_command(_scoreboard_args())
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "quiet day" in captured.err


def test_scoreboard_json_output(monkeypatch, capsys):
    """--format json emits parseable JSON with the scored appearances."""
    import json

    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0), _scored(2, "Setup RP", "RP", 6.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    _run_scoreboard_command(_scoreboard_args(format="json"))
    payload = json.loads(capsys.readouterr().out)
    assert payload["game_date"] == "2026-07-04"
    assert [a["pitcher_name"] for a in payload["appearances"]] == ["Ace SP", "Setup RP"]


def test_scoreboard_json_empty_is_valid(monkeypatch, capsys):
    """--format json on a quiet day still emits valid JSON to stdout (no stderr)."""
    import json

    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: [])
    _run_scoreboard_command(_scoreboard_args(format="json"))
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"game_date": None, "appearances": []}
    assert captured.err == ""


def test_scoreboard_parse_format_and_curate_flags(monkeypatch):
    monkeypatch.setattr(
        sys, "argv",
        ["main.py", "scoreboard", "--format", "table", "-n", "5",
         "--min-score", "4.0", "-v", "--curate", "--provider", "claude"],
    )
    args = parse_args()
    assert args.format == "table"
    assert args.top == 5
    assert args.min_score == 4.0
    assert args.verbose is True
    assert args.curate is True
    assert args.provider == "claude"


def test_scoreboard_table_format(monkeypatch, capsys):
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0), _scored(2, "Setup RP", "RP", 6.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    _run_scoreboard_command(_scoreboard_args(format="table"))
    out = capsys.readouterr().out
    assert "Score" in out and "Signals" in out
    assert "Ace SP" in out and "Setup RP" in out


def test_scoreboard_min_score_filter(monkeypatch, capsys):
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0), _scored(2, "Weak RP", "RP", 2.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    _run_scoreboard_command(_scoreboard_args(min_score=5.0))
    out = capsys.readouterr().out
    assert "Ace SP" in out
    assert "Weak RP" not in out


def test_scoreboard_curate_prints_slate(monkeypatch, capsys):
    from pitcher_narratives import curator as curator_mod
    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command
    from pitcher_narratives.curator import CurationPick, CurationSlate

    board = [_scored(1, "Ace SP", "SP", 12.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    slate = CurationSlate(picks=[CurationPick(
        pitcher_id=1, category="clean_breakout", angle="velo up",
        conviction="high", conviction_reason="shape agrees",
    )])
    monkeypatch.setattr(curator_mod, "select_slate", lambda *a, **k: slate)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    _run_scoreboard_command(_scoreboard_args(curate=True))
    out = capsys.readouterr().out
    assert "CLEAN BREAKOUT" in out
    assert "Ace SP (high): velo up" in out


# ── Code-review fixes (WS1/WS2 follow-up) ──


def test_build_diagnostics_dict_empty_narrative_not_verified():
    """An empty-narrative mode is not 'verified' and reports has_capsule=False."""
    from pitcher_narratives.cli import build_diagnostics_dict

    diag = build_diagnostics_dict(_diag_pipe_result(narrative=""))
    assert diag["has_capsule"] is False
    assert diag["verified"] is False


def test_emit_empty_narrative_logs_warning(caplog):
    """Empty-capsule failures are flagged loudly (repo convention)."""
    import logging

    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    with caplog.at_level(logging.WARNING):
        _emit_mode_result(_diag_pipe_result(narrative=""), mode=REPORT)
    assert any("empty narrative" in r.message.lower() for r in caplog.records)


def test_emit_hallucination_pointer_on_stdout(capsys, monkeypatch):
    """Hallucination flags surface a pointer on stdout even without -v."""
    from pitcher_narratives import pipeline as pipeline_module
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    monkeypatch.setattr(
        pipeline_module,
        "check_hallucinated_metrics",
        lambda text: pipeline_module.HallucinationReport(
            unknown_metrics=["FIP"], outcome_stat_warnings=[]
        ),
    )
    _emit_mode_result(_diag_pipe_result(narrative="cap"), mode=REPORT)
    out = capsys.readouterr().out
    assert "hallucinated-metric flag" in out


def test_emit_no_hallucination_pointer_when_clean(capsys):
    """No pointer when the guard is clean."""
    from pitcher_narratives.cli import _emit_mode_result
    from pitcher_narratives.personas import REPORT

    _emit_mode_result(_diag_pipe_result(narrative="cap"), mode=REPORT)
    out = capsys.readouterr().out
    assert "hallucinated-metric flag" not in out


def test_scoreboard_curate_json_conflict_exits_2():
    """--curate + --format json is a fail-fast error, not a silent no-op."""
    from pitcher_narratives.cli import _run_scoreboard_command

    with pytest.raises(SystemExit) as exc:
        _run_scoreboard_command(_scoreboard_args(curate=True, format="json"))
    assert exc.value.code == 2


def test_scoreboard_verbose_non_table_warns(monkeypatch, caplog):
    """`-v` under a non-table format warns instead of silently doing nothing."""
    import logging

    from pitcher_narratives import scout as scout_mod
    from pitcher_narratives.cli import _run_scoreboard_command

    board = [_scored(1, "Ace SP", "SP", 12.0)]
    monkeypatch.setattr(scout_mod, "scout_appearances", lambda **kw: list(board))
    with caplog.at_level(logging.WARNING):
        _run_scoreboard_command(_scoreboard_args(verbose=True, format="md"))
    assert any("only affects --format table" in r.message for r in caplog.records)
