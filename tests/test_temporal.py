from datetime import date

import pytest

from pitcher_narratives.temporal import FrameSelection, GameKey, TemporalFrame


def test_temporal_frame_members():
    from pitcher_narratives.temporal import TemporalFrame

    assert TemporalFrame.MOST_RECENT == "most_recent"
    assert {f.value for f in TemporalFrame} == {"most_recent", "recent", "prior", "season"}


def test_window_days_frame_removed():
    from pitcher_narratives.temporal import TemporalFrame

    assert not hasattr(TemporalFrame, "WINDOW_DAYS")
    assert "window_days" not in [f.value for f in TemporalFrame]


def test_frame_id_is_deterministic_from_sorted_game_keys():
    games = frozenset(
        {
            GameKey(2026, date(2026, 7, 2), 12),
            GameKey(2026, date(2026, 7, 1), 10),
        }
    )

    first = FrameSelection.create(
        temporal_frame=TemporalFrame.RECENT,
        games=games,
        as_of=date(2026, 7, 2),
        source_population="pitchingplus:2026",
    )
    second = FrameSelection.create(
        temporal_frame=TemporalFrame.RECENT,
        games=frozenset(reversed(sorted(games))),
        as_of=date(2026, 7, 2),
        source_population="pitchingplus:2026",
    )

    assert first.id == second.id


def test_frame_rejects_games_after_as_of_boundary():
    with pytest.raises(ValueError, match="after as_of"):
        FrameSelection.create(
            temporal_frame=TemporalFrame.RECENT,
            games=frozenset({GameKey(2026, date(2026, 7, 3), 13)}),
            as_of=date(2026, 7, 2),
            source_population="pitchingplus:2026",
        )


def test_frame_identity_includes_authoritative_scoring_season():
    games = frozenset({GameKey(2026, date(2026, 7, 1), 10)})

    frame = FrameSelection.create(
        temporal_frame=TemporalFrame.RECENT,
        games=games,
        as_of=date(2026, 7, 1),
        source_population="pitchingplus:2025,2026",
        scoring_season=2026,
    )

    assert frame.scoring_season == 2026
    other = FrameSelection.create(
        temporal_frame=TemporalFrame.RECENT,
        games=frozenset(),
        as_of=date(2026, 7, 1),
        source_population="pitchingplus:2025,2026",
        scoring_season=2025,
    )
    empty_current = FrameSelection.create(
        temporal_frame=TemporalFrame.RECENT,
        games=frozenset(),
        as_of=date(2026, 7, 1),
        source_population="pitchingplus:2025,2026",
        scoring_season=2026,
    )
    assert other.id != empty_current.id


def test_frame_rejects_mixed_scoring_seasons():
    with pytest.raises(ValueError, match="cannot blend scoring seasons"):
        FrameSelection.create(
            temporal_frame=TemporalFrame.SEASON,
            games=frozenset(
                {
                    GameKey(2025, date(2025, 9, 1), 10),
                    GameKey(2026, date(2026, 4, 1), 11),
                }
            ),
            as_of=date(2026, 4, 1),
            source_population="pitchingplus:2025,2026",
        )
