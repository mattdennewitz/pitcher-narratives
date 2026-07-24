"""Immutable temporal frame identities for point-in-time analysis."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

__all__ = [
    "_DEFAULT_PRIOR_APPEARANCES",
    "_DEFAULT_RECENT_APPEARANCES",
    "FrameSelection",
    "GameKey",
    "TemporalFrame",
]


class TemporalFrame(StrEnum):
    MOST_RECENT = "most_recent"
    RECENT = "recent"
    PRIOR = "prior"
    SEASON = "season"


@dataclass(frozen=True, order=True)
class GameKey:
    """Authoritative identity of one game in one scoring season."""

    season: int
    game_date: date
    game_pk: int


@dataclass(frozen=True)
class FrameSelection:
    """Exact immutable game population available at an as-of boundary."""

    temporal_frame: TemporalFrame
    games: frozenset[GameKey]
    as_of: date
    source_population: str
    scoring_season: int | None = None
    id: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.source_population.strip():
            raise ValueError("frame source_population cannot be empty")
        game_seasons = {game.season for game in self.games}
        if len(game_seasons) > 1:
            raise ValueError(f"frame cannot blend scoring seasons: {sorted(game_seasons)}")
        if self.scoring_season is None and game_seasons:
            object.__setattr__(self, "scoring_season", next(iter(game_seasons)))
        if game_seasons and self.scoring_season not in game_seasons:
            raise ValueError("frame scoring_season disagrees with its game identities")
        future_games = sorted(game for game in self.games if game.game_date > self.as_of)
        if future_games:
            raise ValueError(f"frame contains games after as_of {self.as_of}: {future_games}")
        canonical_keys = ";".join(
            f"{game.season}:{game.game_date.isoformat()}:{game.game_pk}" for game in sorted(self.games)
        )
        identity = (
            f"{self.temporal_frame.value}|{self.as_of.isoformat()}|"
            f"{self.source_population}|{self.scoring_season}|{canonical_keys}"
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
        object.__setattr__(self, "id", f"{self.temporal_frame.value}:{digest}")

    @classmethod
    def create(
        cls,
        *,
        temporal_frame: TemporalFrame,
        games: frozenset[GameKey],
        as_of: date,
        source_population: str,
        scoring_season: int | None = None,
    ) -> FrameSelection:
        return cls(
            temporal_frame=temporal_frame,
            games=games,
            as_of=as_of,
            source_population=source_population,
            scoring_season=scoring_season,
        )


_DEFAULT_RECENT_APPEARANCES = 10
_DEFAULT_PRIOR_APPEARANCES = 10
