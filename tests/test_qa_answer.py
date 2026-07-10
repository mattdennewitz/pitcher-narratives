"""answer_question resolves the pitch against the arsenal, runs the (stubbed)
agent over reused input, and fact-checks — all offline."""

import asyncio
import types

import pytest

from pitcher_narratives import qa
from pitcher_narratives.models import AuditResult


class StubAgent:
    def __init__(self, out): self._out = out
    async def run(self, **kwargs):
        return types.SimpleNamespace(output=self._out)


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setattr(qa, "build_qa_agent", lambda provider="gemini": StubAgent("STUB ANSWER"))
    async def _clean(*a, **k): return AuditResult(flags=[])
    monkeypatch.setattr(qa, "run_data_audit", _clean)


def test_answer_returns_agent_output():
    out = asyncio.run(qa.answer_question("why does Jared Jones's fastball grade 92 stuff+"))
    assert out == "STUB ANSWER"


def test_pitch_not_in_arsenal_raises():
    # Jones (683003) throws no splitter.
    with pytest.raises(qa.QuestionError, match="throw"):
        asyncio.run(qa.answer_question("why does Jared Jones's splitter grade 90 stuff+"))


def test_resolve_pitch_prefers_most_thrown():
    arsenal = [
        types.SimpleNamespace(pitch_type="SI", pitch_name="Sinker", n_pitches_window=20),
        types.SimpleNamespace(pitch_type="FF", pitch_name="Four-Seam", n_pitches_window=200),
    ]
    assert qa.resolve_pitch_against_arsenal(["FF", "SI"], arsenal) == ("FF", "Four-Seam")
