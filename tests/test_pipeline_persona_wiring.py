"""Wiring tests for the mode-composed writer (single-voice refactor, Task 2).

These tests verify that:
1. _WRITER_PROMPT is deleted from pipeline.py
2. make_pipeline_agents backward compat (2-arg)
3. make_pipeline_agents has no `persona` parameter
4. The writer agent's system prompt is composed from the mode
5. PipelineAgents no longer carries a `brief` agent
6. generate_pipeline_streaming still accepts a `mode` kwarg
7. CHANGES anchor guidance lands on the anchor agent
"""

import pytest


class TestPipelinePersonaWiring:
    def test_writer_prompt_deleted(self):
        """_WRITER_PROMPT no longer importable from pipeline."""
        with pytest.raises(ImportError):
            from pitcher_narratives.pipeline import _WRITER_PROMPT  # noqa: F401

    def test_backward_compat_two_arg(self):
        """make_pipeline_agents('gemini', 'high') still works."""
        from pitcher_narratives.pipeline import make_pipeline_agents

        agents = make_pipeline_agents("gemini", "high")
        assert agents.writer is not None

    def test_make_pipeline_agents_has_no_persona_param(self):
        """The single voice is fixed; no persona knob on the factory."""
        import inspect

        from pitcher_narratives.pipeline import make_pipeline_agents

        assert "persona" not in inspect.signature(make_pipeline_agents).parameters

    def test_writer_prompt_is_mode_composed(self):
        """The mode prompt and structured provenance contract reach the writer."""
        from pitcher_narratives.personas import REPORT, build_writer_system_prompt
        from pitcher_narratives.pipeline import (
            _NARRATIVE_ARTIFACT_PROMPT,
            make_pipeline_agents,
        )

        agents = make_pipeline_agents("gemini", "high", REPORT)
        assert agents.writer._system_prompts == (
            f"{build_writer_system_prompt(REPORT)}\n\n{_NARRATIVE_ARTIFACT_PROMPT}",
        )

    def test_pipeline_agents_has_no_brief(self):
        """The separate brief agent is gone from PipelineAgents."""
        from pitcher_narratives.personas import REPORT
        from pitcher_narratives.pipeline import make_pipeline_agents

        agents = make_pipeline_agents("gemini", "high", REPORT)
        assert not hasattr(agents, "brief")

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
        from pitcher_narratives.personas import CHANGES, REPORT
        from pitcher_narratives.pipeline import make_pipeline_agents

        changes_agents = make_pipeline_agents("gemini", "high", CHANGES)
        report_agents = make_pipeline_agents("gemini", "high", REPORT)
        changes_prompt = changes_agents.anchor._system_prompts[0]
        report_prompt = report_agents.anchor._system_prompts[0]

        assert CHANGES.anchor_guidance in changes_prompt
        assert CHANGES.anchor_guidance not in report_prompt
        assert report_prompt == ANCHOR_PROMPT


def test_entry_points_have_no_persona():
    import inspect

    from pitcher_narratives.pipeline import (
        generate_pipeline_streaming,
        run_narration_modes,
        write_pipeline_data_file,
    )

    for fn in (generate_pipeline_streaming, run_narration_modes, write_pipeline_data_file):
        assert "persona" not in inspect.signature(fn).parameters, fn.__name__
