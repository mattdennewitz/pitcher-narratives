"""Tests for key signal extraction model and rendering."""

import pytest
from pydantic import ValidationError

from pitcher_narratives.signals import KeySignals, SIGNAL_EXTRACTOR_PROMPT, _FIELD_LABELS, render_key_signals
from pitcher_narratives.anchor import AnchorWarning


class TestAnchorWarningCategory:
    def test_underweighted_is_valid(self):
        w = AnchorWarning(category="UNDERWEIGHTED", description="test")
        assert w.category == "UNDERWEIGHTED"

    def test_missed_signal_still_valid(self):
        w = AnchorWarning(category="MISSED_SIGNAL", description="test")
        assert w.category == "MISSED_SIGNAL"


class TestFieldLabelsSync:
    def test_field_labels_match_model_fields(self):
        """_FIELD_LABELS keys must exactly match KeySignals model fields."""
        assert set(_FIELD_LABELS.keys()) == set(KeySignals.model_fields.keys())


class TestKeySignals:
    def test_required_fields_reject_empty_string(self):
        """Primary signals must be non-empty."""
        with pytest.raises(ValidationError):
            KeySignals(top_improvement="", top_concern="Fastball velo down")
        with pytest.raises(ValidationError):
            KeySignals(top_improvement="Slider S+ jumped", top_concern="")

    def test_required_fields_only(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135 with new gyro shape",
            top_concern="Fastball velo down 2.1 mph from season baseline",
        )
        assert ks.top_improvement is not None
        assert ks.top_concern is not None
        assert ks.development_pitch is None
        assert ks.specialist_tension is None
        assert ks.arsenal_dependency is None
        assert ks.connected_changes is None
        assert ks.platoon_vulnerability is None
        assert ks.sample_size_caution is None

    def test_all_fields_populated(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
            development_pitch="Changeup has S+ 118 but L+ 72, would solve RHB platoon gap",
            specialist_tension="Stuff says curveball is elite (S+ 128) but run value shows +1.2 xRV100",
            arsenal_dependency="Slider accounts for 68% of whiffs, rest of arsenal is replacement-level",
            connected_changes="Velo drop, S+ drop, and increased hard contact all point to fatigue pattern",
            platoon_vulnerability="P+ vs LHB is 82 with no secondary weapon to that side",
            sample_size_caution="Slider S+ spike based on 34 pitches over 2 appearances",
        )
        assert ks.development_pitch is not None
        assert ks.specialist_tension is not None


class TestRenderKeySignals:
    def test_required_only(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
        )
        rendered = render_key_signals(ks)
        assert "## Key Signals" in rendered
        assert "- Top Improvement:" in rendered
        assert "- Top Concern:" in rendered
        assert "Development Pitch" not in rendered
        assert "Specialist Tension" not in rendered

    def test_includes_populated_optional(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
            specialist_tension="Stuff says curveball elite but run value disagrees",
        )
        rendered = render_key_signals(ks)
        assert "- Specialist Tension:" in rendered

    def test_omits_none_fields(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
            development_pitch=None,
        )
        rendered = render_key_signals(ks)
        assert "Development Pitch" not in rendered


class TestBuildWriterInputWithSignals:
    def test_includes_key_signals_section(self):
        ks = KeySignals(
            top_improvement="Slider S+ jumped to 135",
            top_concern="Fastball velo down 2.1 mph",
        )

        # Minimal PitcherContext mock — build_writer_input only reads
        # ctx.pitcher_name, ctx.throws, ctx.role from the context.
        from types import SimpleNamespace
        from pitcher_narratives.pipeline import build_writer_input

        ctx = SimpleNamespace(pitcher_name="Test Pitcher", throws="R", role="SP")

        result = build_writer_input(
            ctx, "stuff output", "location output", "runvalue output",
            "trends output", "game_shape output", key_signals=ks,
        )
        assert "## Key Signals" in result
        assert "- Top Improvement: Slider S+ jumped to 135" in result
        assert "- Top Concern: Fastball velo down 2.1 mph" in result
        # Key Signals should appear before specialist analyses
        signals_pos = result.index("## Key Signals")
        stuff_pos = result.index("## Specialist Analysis 1")
        assert signals_pos < stuff_pos

    def test_no_signals_omits_section(self):
        from types import SimpleNamespace
        from pitcher_narratives.pipeline import build_writer_input

        ctx = SimpleNamespace(pitcher_name="Test Pitcher", throws="R", role="SP")

        result = build_writer_input(
            ctx, "stuff output", "location output", "runvalue output",
            "trends output", "game_shape output",
        )
        assert "## Key Signals" not in result


class TestWriterPromptKeySignals:
    def test_references_key_signals(self):
        from pitcher_narratives.pipeline import _WRITER_PROMPT
        assert "Key Signals" in _WRITER_PROMPT

    def test_distinguishes_primary_secondary(self):
        from pitcher_narratives.pipeline import _WRITER_PROMPT
        assert "Primary" in _WRITER_PROMPT or "primary" in _WRITER_PROMPT
        assert "Secondary" in _WRITER_PROMPT or "secondary" in _WRITER_PROMPT


class TestSignalExtractorPrompt:
    def test_mentions_all_signal_types(self):
        for keyword in [
            "top_improvement", "top_concern", "development_pitch",
            "specialist_tension", "arsenal_dependency", "connected_changes",
            "platoon_vulnerability", "sample_size_caution",
        ]:
            assert keyword in SIGNAL_EXTRACTOR_PROMPT

    def test_instructs_null_for_absent(self):
        assert "null" in SIGNAL_EXTRACTOR_PROMPT

    def test_instructs_no_invention(self):
        assert "invent" in SIGNAL_EXTRACTOR_PROMPT.lower()


class TestDataFileSignalExtractor:
    def test_includes_signal_extractor_section(self, tmp_path):
        import os
        os.chdir(tmp_path)
        from pitcher_narratives.data import load_pitcher_data
        from pitcher_narratives.context import assemble_pitcher_context
        from pitcher_narratives.pipeline import write_pipeline_data_file
        data = load_pitcher_data(592155, window_days=30)
        ctx = assemble_pitcher_context(data)
        path = write_pipeline_data_file(ctx, 592155, "gemini")
        content = open(path).read()
        assert "SIGNAL EXTRACTOR" in content
        assert "SIGNAL_EXTRACTOR_PROMPT" in content or "cross-specialist" in content.lower()

    def test_signal_extractor_appears_before_writer(self, tmp_path):
        import os
        os.chdir(tmp_path)
        from pitcher_narratives.data import load_pitcher_data
        from pitcher_narratives.context import assemble_pitcher_context
        from pitcher_narratives.pipeline import write_pipeline_data_file
        data = load_pitcher_data(592155, window_days=30)
        ctx = assemble_pitcher_context(data)
        path = write_pipeline_data_file(ctx, 592155, "gemini")
        content = open(path).read()
        signal_pos = content.index("SIGNAL EXTRACTOR")
        writer_pos = content.index("WRITER")
        assert signal_pos < writer_pos
