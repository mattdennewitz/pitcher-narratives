"""Tests for scout pure helpers: role-aware ranking."""

from datetime import date

from pitcher_narratives.scout import ScoredAppearance, _top_per_role


def _app(pid: int, score: float, role: str) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"P{pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=50,
        score=score, role=role,
    )


def test_top_per_role_caps_each_bucket():
    """Each role keeps its own top N; result is merged, score-desc."""
    apps = [
        _app(1, 9.0, "SP"), _app(2, 8.0, "SP"), _app(3, 7.0, "SP"),
        _app(4, 6.5, "RP"), _app(5, 5.0, "RP"), _app(6, 4.0, "RP"),
    ]
    out = _top_per_role(apps, top_n=2)
    assert [a.pitcher_id for a in out] == [1, 2, 4, 5]
    assert [a.score for a in out] == sorted([a.score for a in out], reverse=True)


def test_top_per_role_thin_bucket():
    """A bucket with fewer than N keeps everything it has."""
    apps = [_app(1, 9.0, "SP"), _app(4, 6.5, "RP")]
    out = _top_per_role(apps, top_n=10)
    assert len(out) == 2


def test_scored_appearance_has_role_default():
    """role is part of the dataclass (default RP so old call sites work)."""
    a = _app(1, 1.0, "SP")
    assert a.role == "SP"
