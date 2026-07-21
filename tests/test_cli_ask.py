"""The `ask` subcommand parses and dispatches to qa.answer_question."""

import pytest

from pitcher_narratives import cli, qa


def test_ask_subparser_parses(monkeypatch):
    monkeypatch.setattr("sys.argv", ["pn", "ask", "why does Jared Jones's fastball grade 92 stuff+"])
    args = cli.parse_args()
    assert args.command == "ask"
    assert "Jared Jones" in args.question
    assert args.provider == "gemini"


def test_ask_command_prints_answer(monkeypatch, capsys):
    async def _fake(question, *, provider="gemini", model_override=None):
        return "ANSWER TEXT"
    monkeypatch.setattr(qa, "answer_question", _fake)
    ns = type("NS", (), {"command": "ask", "question": "Jared Jones fastball stuff+", "provider": "gemini"})()
    cli._run_ask_command(ns)
    assert "ANSWER TEXT" in capsys.readouterr().out


def test_ask_command_reports_question_error(monkeypatch, capsys):
    async def _boom(question, *, provider="gemini", model_override=None):
        raise qa.QuestionError("Couldn't find a pitcher in that question.")
    monkeypatch.setattr(qa, "answer_question", _boom)
    ns = type("NS", (), {"command": "ask", "question": "nonsense", "provider": "gemini"})()
    with pytest.raises(SystemExit):
        cli._run_ask_command(ns)
    assert "pitcher" in capsys.readouterr().err
