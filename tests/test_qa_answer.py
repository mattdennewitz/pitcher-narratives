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


class SeqAgent:
    """Returns successive outputs on successive .run calls (last repeats)."""
    def __init__(self, outs): self._outs = list(outs); self.n = 0
    async def run(self, **kwargs):
        out = self._outs[min(self.n, len(self._outs) - 1)]; self.n += 1
        return types.SimpleNamespace(output=out)


class CapturingAgent:
    def __init__(self, out): self._out = out; self.prompts = []
    async def run(self, **kwargs):
        self.prompts.append(kwargs.get("user_prompt")); return types.SimpleNamespace(output=self._out)


def test_revises_when_audit_flags(monkeypatch):
    from pitcher_narratives.models import AuditFlag, AuditResult
    monkeypatch.setattr(qa, "build_qa_agent", lambda provider="gemini": SeqAgent(["FIRST", "REVISED"]))
    async def _flagged(*a, **k):
        return AuditResult(flags=[AuditFlag(category="X", specialist="qa", claim="c", data_shows="d", suggested_fix="f")])
    monkeypatch.setattr(qa, "run_data_audit", _flagged)
    out = asyncio.run(qa.answer_question("why does Jared Jones's fastball grade 92 stuff+"))
    assert out == "REVISED"


def test_degrades_to_first_answer_when_audit_raises(monkeypatch):
    monkeypatch.setattr(qa, "build_qa_agent", lambda provider="gemini": SeqAgent(["FIRST", "REVISED"]))
    async def _boom(*a, **k):
        raise RuntimeError("auditor down")
    monkeypatch.setattr(qa, "run_data_audit", _boom)
    out = asyncio.run(qa.answer_question("why does Jared Jones's fastball grade 92 stuff+"))
    assert out == "FIRST"


def test_cited_value_reaches_prompt(monkeypatch):
    from pitcher_narratives.models import AuditResult
    agent = CapturingAgent("ANSWER")
    monkeypatch.setattr(qa, "build_qa_agent", lambda provider="gemini": agent)
    async def _clean(*a, **k): return AuditResult(flags=[])
    monkeypatch.setattr(qa, "run_data_audit", _clean)
    asyncio.run(qa.answer_question("why does Jared Jones's fastball grade 92 stuff+"))
    prompt = agent.prompts[0]
    scoping = prompt[0] if isinstance(prompt, list) else str(prompt)
    assert "92" in scoping  # cited value threaded into the scoping instruction
