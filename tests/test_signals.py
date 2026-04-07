"""Tests for key signal extraction model and rendering."""

from pitcher_narratives.signals import KeySignals, SIGNAL_EXTRACTOR_PROMPT, render_key_signals
from pitcher_narratives.anchor import AnchorWarning, WarningCategory


class TestAnchorWarningCategory:
    def test_underweighted_is_valid(self):
        w = AnchorWarning(category="UNDERWEIGHTED", description="test")
        assert w.category == "UNDERWEIGHTED"

    def test_missed_signal_still_valid(self):
        w = AnchorWarning(category="MISSED_SIGNAL", description="test")
        assert w.category == "MISSED_SIGNAL"


class TestKeySignals:
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
