"""Tests for key signal extraction model and rendering."""

import pytest
from pydantic import ValidationError

from pitcher_narratives.anchor import AnchorWarning
from pitcher_narratives.models import SpecialistOutputs
from pitcher_narratives.signals import (
    SIGNAL_EXTRACTOR_PROMPT,
    KeySignals,
    Signal,
    SignalState,
    count_secondary_signals,
    render_key_signals,
)


def _signal(text: str, *, fact_id: str = "fact:one") -> Signal:
    return Signal(
        text=text,
        fact_ids=(fact_id,),
        source_claim_ids=("analysis-claim:one",),
        sample_size=25,
        comparison_population="2026 same-frame pitches",
    )


class TestCountSecondarySignals:
    def test_none_signals_counts_zero(self):
        assert count_secondary_signals(None) == 0

    def test_only_primary_populated_counts_zero(self):
        ks = KeySignals(
            state=SignalState.MATERIAL,
            top_improvement=_signal("Slider S+ jumped"),
        )
        assert count_secondary_signals(ks) == 0

    def test_counts_secondary_tuple(self):
        ks = KeySignals(
            state=SignalState.MATERIAL,
            top_improvement=_signal("Slider S+ jumped"),
            secondary=(
                _signal("Changeup usage rising", fact_id="fact:two"),
                _signal("Cutter sample thin", fact_id="fact:three"),
            ),
        )
        assert count_secondary_signals(ks) == 2


class TestAnchorWarningCategory:
    def test_underweighted_is_valid(self):
        w = AnchorWarning(category="UNDERWEIGHTED", description="test")
        assert w.category == "UNDERWEIGHTED"

    def test_missed_signal_still_valid(self):
        w = AnchorWarning(category="MISSED_SIGNAL", description="test")
        assert w.category == "MISSED_SIGNAL"


class TestKeySignals:
    def test_signal_requires_citations(self):
        with pytest.raises(ValidationError):
            Signal(
                text="Fastball velocity declined.",
                fact_ids=(),
                source_claim_ids=("analysis-claim:one",),
                sample_size=25,
                comparison_population="2026 same-frame pitches",
            )

    def test_signal_rejects_model_authored_materiality(self):
        with pytest.raises(ValidationError, match="materiality"):
            Signal(
                text="Fastball velocity declined.",
                fact_ids=("fact:one",),
                source_claim_ids=("analysis-claim:one",),
                sample_size=25,
                comparison_population="2026 same-frame pitches",
                materiality="invented threshold passed",
            )

    def test_insufficient_evidence_cannot_carry_directional_signal(self):
        with pytest.raises(ValidationError, match="insufficient_evidence"):
            KeySignals(
                state=SignalState.INSUFFICIENT_EVIDENCE,
                top_improvement=_signal("Fastball velocity improved."),
            )

    def test_conflicting_evidence_may_carry_cited_conflict(self):
        signals = KeySignals(
            state=SignalState.CONFLICTING_EVIDENCE,
            secondary=(_signal("Stuff and run value point in opposite directions."),),
        )

        assert len(signals.secondary) == 1

    def test_material_state_requires_a_signal(self):
        with pytest.raises(ValidationError):
            KeySignals(state=SignalState.MATERIAL)

    def test_no_material_state_is_nullable(self):
        ks = KeySignals(state=SignalState.NO_MATERIAL_SIGNAL)
        assert ks.top_improvement is None
        assert ks.top_concern is None
        assert ks.secondary == ()

    def test_all_signal_positions_populated(self):
        ks = KeySignals(
            state=SignalState.MATERIAL,
            top_improvement=_signal("Slider S+ jumped to 135"),
            top_concern=_signal("Fastball velo down 2.1 mph", fact_id="fact:two"),
            secondary=(
                _signal(
                    "Stuff and run value disagree on the curveball.",
                    fact_id="fact:three",
                ),
            ),
        )
        assert ks.top_improvement is not None
        assert ks.top_concern is not None
        assert len(ks.secondary) == 1


class TestRenderKeySignals:
    def test_nullable_state_renders_without_manufactured_primaries(self):
        rendered = render_key_signals(KeySignals(state=SignalState.NO_MATERIAL_SIGNAL))
        assert "## Key Signals" in rendered
        assert "- State: no_material_signal" in rendered
        assert "Top Improvement" not in rendered
        assert "Top Concern" not in rendered

    def test_includes_citations_and_evidence_metadata(self):
        ks = KeySignals(
            state=SignalState.MATERIAL,
            top_improvement=_signal("Slider S+ jumped to 135"),
            secondary=(
                _signal(
                    "Stuff and run value disagree on the curveball.",
                    fact_id="fact:three",
                ),
            ),
        )
        rendered = render_key_signals(ks)
        assert "- Top Improvement: Slider S+ jumped to 135" in rendered
        assert "[fact:one]" in rendered
        assert "[claim:analysis-claim:one]" in rendered
        assert "n=25" in rendered
        assert "- Secondary:" in rendered


class TestBuildWriterInputWithSignals:
    def test_includes_key_signals_section(self):
        ks = KeySignals(
            state=SignalState.MATERIAL,
            top_improvement=_signal("Slider S+ jumped to 135"),
            top_concern=_signal("Fastball velo down 2.1 mph", fact_id="fact:two"),
        )

        # Minimal context intentionally omits optional calibration data; the
        # builder must render explicit unavailability rather than infer reliability.
        from types import SimpleNamespace

        from pitcher_narratives.pipeline import build_writer_input

        ctx = SimpleNamespace(pitcher_name="Test Pitcher", throws="R", role="SP")

        result = build_writer_input(
            ctx,
            SpecialistOutputs(),
            key_signals=ks,
        )
        assert "Calibration unavailable: no manifest-covered calibration artifact." in result
        assert "predictive reliability as unknown" in result
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

        result = build_writer_input(ctx, SpecialistOutputs())
        assert "Calibration unavailable: no manifest-covered calibration artifact." in result
        assert "predictive reliability as unknown" in result
        assert "## Key Signals" not in result

    def test_missing_temporal_attr_does_not_raise(self):
        """ctx without a .temporal attribute (as used by other unit tests here)
        must not blow up build_writer_input — the temporal section is simply
        omitted."""
        from types import SimpleNamespace

        from pitcher_narratives.pipeline import build_writer_input

        ctx = SimpleNamespace(pitcher_name="Test Pitcher", throws="R", role="SP")

        result = build_writer_input(ctx, SpecialistOutputs())
        assert "Calibration unavailable: no manifest-covered calibration artifact." in result
        assert "predictive reliability as unknown" in result
        assert "## Temporal Context" not in result

    def test_includes_temporal_section_when_present(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from pitcher_narratives.pipeline import build_writer_input

        temporal = MagicMock()
        temporal.recent_frame_appearances = 12
        temporal.recent_frame_ip = "55.0"
        temporal.scoring_season = 2026
        temporal.recent_frame_first_date = "2026-04-01"
        temporal.analysis_date = "2026-07-03"

        ctx = SimpleNamespace(pitcher_name="Test Pitcher", throws="R", role="SP", temporal=temporal)

        result = build_writer_input(ctx, SpecialistOutputs())
        assert "Calibration unavailable: no manifest-covered calibration artifact." in result
        assert "predictive reliability as unknown" in result
        assert "## Temporal Context" in result
        # Should appear before the specialist analyses.
        temporal_pos = result.index("## Temporal Context")
        stuff_pos = result.index("## Specialist Analysis 1")
        assert temporal_pos < stuff_pos


class TestWriterPromptKeySignals:
    def test_references_key_signals(self):
        from pitcher_narratives.personas import REPORT, build_writer_system_prompt

        prompt = build_writer_system_prompt(REPORT)
        assert "Key Signals" in prompt

    def test_distinguishes_primary_secondary(self):
        from pitcher_narratives.personas import REPORT, build_writer_system_prompt

        prompt = build_writer_system_prompt(REPORT)
        assert "Primary" in prompt or "primary" in prompt
        assert "Secondary" in prompt or "secondary" in prompt


class TestSignalExtractorPrompt:
    def test_mentions_structured_evidence_fields(self):
        for keyword in [
            "state",
            "top_improvement",
            "top_concern",
            "secondary",
            "fact_ids",
            "source_claim_ids",
            "sample_size",
            "comparison_population",
        ]:
            assert keyword in SIGNAL_EXTRACTOR_PROMPT
        assert "materiality" not in SIGNAL_EXTRACTOR_PROMPT

    def test_instructs_null_for_absent(self):
        assert "null" in SIGNAL_EXTRACTOR_PROMPT

    def test_instructs_no_manufactured_signals(self):
        assert "manufacture" in SIGNAL_EXTRACTOR_PROMPT.lower()


class TestDataFileSignalExtractor:
    def test_includes_signal_extractor_section(self, tmp_path):
        import os

        os.chdir(tmp_path)
        from pitcher_narratives.context import assemble_pitcher_context
        from pitcher_narratives.data import load_pitcher_data
        from pitcher_narratives.pipeline import write_pipeline_data_file

        data = load_pitcher_data(592155, recent_appearances=10)
        ctx = assemble_pitcher_context(data)
        _path, content = write_pipeline_data_file(ctx, 592155, "gemini")
        assert "SIGNAL EXTRACTOR" in content
        assert "SIGNAL_EXTRACTOR_PROMPT" in content or "cross-specialist" in content.lower()

    def test_signal_extractor_appears_before_writer(self, tmp_path):
        import os

        os.chdir(tmp_path)
        from pitcher_narratives.context import assemble_pitcher_context
        from pitcher_narratives.data import load_pitcher_data
        from pitcher_narratives.pipeline import write_pipeline_data_file

        data = load_pitcher_data(592155, recent_appearances=10)
        ctx = assemble_pitcher_context(data)
        _path, content = write_pipeline_data_file(ctx, 592155, "gemini")
        signal_pos = content.index("SIGNAL EXTRACTOR")
        writer_pos = content.index("WRITER")
        assert signal_pos < writer_pos
