def test_temporal_frame_members():
    from pitcher_narratives.temporal import TemporalFrame

    assert TemporalFrame.WINDOW_DAYS == "window_days"
    assert TemporalFrame.MOST_RECENT == "most_recent"
    assert {f.value for f in TemporalFrame} == {
        "most_recent", "recent", "prior", "season", "window_days"}
