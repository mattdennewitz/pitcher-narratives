"""RED phase tests for Task 1: pipeline persona wiring.

These tests verify that:
1. _WRITER_PROMPT is deleted from pipeline.py
2. make_pipeline_agents backward compat (2-arg)
3. Default == explicit SCOUT parity
4. Writer receives composed persona prompt
5. generate_pipeline_streaming accepts persona kwarg
6. test_signals.py tests still pass (tested separately via pytest)
"""

import pytest

from pitcher_narratives.personas import SCOUT, build_writer_system_prompt


class TestPipelinePersonaWiring:
    def test_writer_prompt_deleted(self):
        """_WRITER_PROMPT no longer importable from pipeline."""
        with pytest.raises(ImportError):
            from pitcher_narratives.pipeline import _WRITER_PROMPT  # noqa: F401

    def test_backward_compat_two_arg(self):
        """make_pipeline_agents('gemini', 'high') still works (analyst.py:618)."""
        from pitcher_narratives.pipeline import make_pipeline_agents
        agents = make_pipeline_agents("gemini", "high")
        assert agents.writer is not None

    def test_default_equals_explicit_scout(self):
        """No-arg and explicit-SCOUT produce identical writer prompts."""
        from pitcher_narratives.pipeline import make_pipeline_agents
        agents_default = make_pipeline_agents("gemini", "high")
        agents_explicit = make_pipeline_agents("gemini", "high", SCOUT)
        assert agents_default.writer._system_prompts == agents_explicit.writer._system_prompts

    def test_writer_receives_composed_prompt(self):
        """Writer agent's system prompt is the full composed persona prompt."""
        from pitcher_narratives.pipeline import make_pipeline_agents
        agents = make_pipeline_agents("gemini", "high")
        expected = build_writer_system_prompt(SCOUT)
        assert agents.writer._system_prompts == (expected,)

    def test_generate_pipeline_streaming_accepts_persona(self):
        """generate_pipeline_streaming accepts persona keyword argument."""
        import inspect
        from pitcher_narratives.pipeline import generate_pipeline_streaming
        sig = inspect.signature(generate_pipeline_streaming)
        assert "persona" in sig.parameters

    def test_make_pipeline_agents_accepts_mode(self):
        """make_pipeline_agents accepts a mode keyword defaulting to REPORT."""
        import inspect
        from pitcher_narratives.pipeline import make_pipeline_agents
        from pitcher_narratives.personas import REPORT
        sig = inspect.signature(make_pipeline_agents)
        assert "mode" in sig.parameters
        assert sig.parameters["mode"].default is REPORT

    def test_generate_pipeline_streaming_accepts_mode(self):
        """generate_pipeline_streaming accepts a mode keyword."""
        import inspect
        from pitcher_narratives.pipeline import generate_pipeline_streaming
        assert "mode" in inspect.signature(generate_pipeline_streaming).parameters

    def test_anchor_prompt_carries_changes_guidance(self):
        """CHANGES mode's anchor guidance overlay lands on the anchor agent's
        system prompt; REPORT's anchor prompt stays byte-identical to the
        base prompt (no guidance overlay)."""
        from pitcher_narratives.anchor import ANCHOR_PROMPT
        from pitcher_narratives.personas import CHANGES, REPORT, get_persona
        from pitcher_narratives.pipeline import make_pipeline_agents

        changes_agents = make_pipeline_agents("gemini", "high", get_persona("scout"), CHANGES)
        report_agents = make_pipeline_agents("gemini", "high", get_persona("scout"), REPORT)
        changes_prompt = changes_agents.anchor._system_prompts[0]
        report_prompt = report_agents.anchor._system_prompts[0]

        assert CHANGES.anchor_guidance in changes_prompt
        assert CHANGES.anchor_guidance not in report_prompt
        assert report_prompt == ANCHOR_PROMPT
