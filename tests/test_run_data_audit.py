"""run_data_audit routes ground-truth + answer through the spine's auditor."""

import asyncio
import types

from pitcher_narratives import pipeline
from pitcher_narratives.models import AuditFlag, AuditResult


def test_run_data_audit_uses_auditor(monkeypatch):
    captured = {}

    class StubAuditor:
        async def run(self, **kwargs):
            captured["user_prompt"] = kwargs.get("user_prompt")
            return types.SimpleNamespace(
                output=AuditResult(
                    flags=[
                        AuditFlag(
                            category="FABRICATED_DATA",
                            specialist="qa",
                            claim="c",
                            data_shows="d",
                            suggested_fix="f",
                        ),
                    ]
                )
            )

    monkeypatch.setattr(
        pipeline,
        "make_pipeline_agents",
        lambda *a, **k: types.SimpleNamespace(auditor=StubAuditor()),
    )

    result = asyncio.run(pipeline.run_data_audit("GROUND", "ANSWER", provider="gemini"))
    assert not result.is_clean
    assert "GROUND" in captured["user_prompt"] and "ANSWER" in captured["user_prompt"]
