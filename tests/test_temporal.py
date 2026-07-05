def test_temporal_frame_members():
    from pitcher_narratives.temporal import TemporalFrame

    assert TemporalFrame.MOST_RECENT == "most_recent"
    assert {f.value for f in TemporalFrame} == {
        "most_recent", "recent", "prior", "season"}


def test_window_days_frame_removed():
    from pitcher_narratives.temporal import TemporalFrame

    assert not hasattr(TemporalFrame, "WINDOW_DAYS")
    assert "window_days" not in [f.value for f in TemporalFrame]
