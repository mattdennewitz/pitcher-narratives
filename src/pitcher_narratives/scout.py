"""Appearance interest scoring for triage.

Scans all pitcher appearances in a date window and scores each one
for "interestingness" — velocity swings, P+ outliers, usage shifts,
new/dropped pitches, development opportunities, etc.

Does NOT invoke the LLM pipeline. This is a cheap pre-filter that
ranks appearances so you only generate capsules for the interesting ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import cast

import polars as pl

from pitcher_narratives.data import AGGS_DIR

__all__ = ["ScoredAppearance", "scout_appearances"]

# ── Scoring weights ──────────────────────────────────────────────────

_WEIGHTS = {
    "velo_delta": 3.0,
    "pplus_swing": 2.5,
    "splus_lplus_divergence": 3.0,
    "usage_shift": 2.0,
    "new_pitch": 4.0,
    "dropped_pitch": 3.0,
    "hard_hit_spike": 1.5,
    "walk_rate_pplus_contradiction": 2.5,
    "development_opportunity": 3.5,
    "workload_flag": 1.0,
}

# ── Thresholds ───────────────────────────────────────────────────────

_VELO_THRESHOLD = 1.5  # mph from season avg
_PPLUS_THRESHOLD = 15  # points from season
_DIVERGENCE_THRESHOLD = 10  # S+ and L+ moving opposite directions, each ≥ this
_USAGE_THRESHOLD = 8.0  # percentage points
_NEW_PITCH_SEASON_MAX = 1.0  # season usage % below which = "new"
_NEW_PITCH_GAME_MIN = 5.0  # game usage % above which = meaningful
_DROPPED_PITCH_SEASON_MIN = 10.0  # season usage % above which = established
_HARD_HIT_SPIKE = 10.0  # pp above season
_WALK_RATE_THRESHOLD = 0.15  # 15% BB rate
_PPLUS_GOOD = 105  # P+ above which walk contradiction fires
_DEV_SPLUS_MIN = 110  # high stuff threshold
_DEV_LPLUS_MAX = 80  # low command threshold
_CONSECUTIVE_DAYS_FLAG = 3


@dataclass
class Signal:
    """A single interest signal fired for an appearance."""

    name: str
    weight: float
    detail: str


@dataclass
class ScoredAppearance:
    """A scored pitcher appearance with interest signals."""

    pitcher_id: int
    pitcher_name: str
    throws: str
    game_date: date
    game_pk: int
    n_pitches: int
    score: float
    signals: list[Signal] = field(default_factory=list)

    @property
    def signal_summary(self) -> str:
        """One-line summary of fired signals."""
        return " | ".join(f"{s.name}: {s.detail}" for s in self.signals)


def _load_csv(filename: str) -> pl.DataFrame:
    """Load a CSV from the aggs directory with date parsing."""
    path = AGGS_DIR / filename
    df = pl.read_csv(path)
    if "game_date" in df.columns:
        df = df.with_columns(pl.col("game_date").str.to_date("%Y-%m-%d"))
    return df


def _get_max_date(appearance_df: pl.DataFrame) -> date:
    """Get the most recent date in the appearance data."""
    val = appearance_df["game_date"].max()
    if val is None:
        raise ValueError("No appearances found")
    return cast(date, val)


def scout_appearances(
    *,
    window_days: int = 1,
    top_n: int = 20,
    min_pitches: int = 20,
) -> list[ScoredAppearance]:
    """Score all pitcher appearances in a date window by interestingness.

    Args:
        window_days: How many days back to scan (default: 1 = most recent date only).
        top_n: Return the top N most interesting appearances.
        min_pitches: Minimum pitches in an appearance to consider.

    Returns:
        Ranked list of ScoredAppearance, highest score first.
    """
    # Load data
    app_df = _load_csv("2026-pitcher_appearance.csv")
    app_type_df = _load_csv("2026-pitcher_type_appearance.csv")
    season_type_df = _load_csv("2026-pitcher_type.csv")
    season_df = _load_csv("2026-pitcher.csv")

    # Filter to MLB regular season
    app_df = app_df.filter(pl.col("level") == "MLB")
    app_type_df = app_type_df.filter(pl.col("level") == "MLB")
    season_type_df = season_type_df.filter(pl.col("level") == "MLB")
    season_df = season_df.filter(pl.col("level") == "MLB")

    # Determine date window
    max_date = _get_max_date(app_df)
    cutoff = max_date - timedelta(days=window_days - 1)
    app_window = app_df.filter(
        (pl.col("game_date") >= cutoff) & (pl.col("n_pitches") >= min_pitches)
    )

    # Build season baselines per pitcher (weighted across game types)
    season_baseline = _build_season_baseline(season_df)
    season_type_baseline = _build_season_type_baseline(season_type_df)

    # Compute velocity baselines from statcast
    velo_baselines = _compute_velo_baselines()

    # Score all appearances in recent date(s) that had enough appearances to
    # build a season baseline
    app_type_window = app_type_df.filter(
        (pl.col("game_date") >= cutoff)
        & (pl.col("pitch_type") != "")
    )

    # Track consecutive-day pitchers
    consecutive_days = _find_consecutive_day_pitchers(app_df)

    results: list[ScoredAppearance] = []
    for row in app_window.iter_rows(named=True):
        pitcher_id = row["pitcher"]
        game_pk = row["game_pk"]
        game_date = row["game_date"]

        # Get this pitcher's season baseline
        pitcher_baseline = season_baseline.filter(pl.col("pitcher") == pitcher_id)
        if pitcher_baseline.is_empty():
            continue

        # Get per-pitch-type data for this appearance
        game_types = app_type_window.filter(
            (pl.col("pitcher") == pitcher_id) & (pl.col("game_pk") == game_pk)
        )

        # Get pitcher's season pitch type baselines
        pitcher_type_bl = season_type_baseline.filter(pl.col("pitcher") == pitcher_id)

        signals: list[Signal] = []

        # --- Signal: Velocity delta ---
        velo_signals = _check_velo_delta(pitcher_id, game_pk, game_date, velo_baselines)
        signals.extend(velo_signals)

        # --- Signal: P+ swing ---
        pplus_signals = _check_pplus_swing(row, pitcher_baseline)
        signals.extend(pplus_signals)

        # --- Signal: S+/L+ divergence (per pitch type) ---
        div_signals = _check_splus_lplus_divergence(game_types, pitcher_type_bl)
        signals.extend(div_signals)

        # --- Signal: Usage shifts ---
        usage_signals = _check_usage_shifts(game_types, pitcher_type_bl, row["n_pitches"])
        signals.extend(usage_signals)

        # --- Signal: New/dropped pitches ---
        repertoire_signals = _check_repertoire_changes(game_types, pitcher_type_bl, row["n_pitches"])
        signals.extend(repertoire_signals)

        # --- Signal: Walk rate + high P+ contradiction ---
        walk_signals = _check_walk_contradiction(row, pitcher_baseline)
        signals.extend(walk_signals)

        # --- Signal: Development opportunity (high S+, low L+) ---
        dev_signals = _check_development_opportunity(game_types, pitcher_type_bl)
        signals.extend(dev_signals)

        # --- Signal: Workload flag ---
        consec = consecutive_days.get(pitcher_id, 0)
        if consec >= _CONSECUTIVE_DAYS_FLAG:
            signals.append(Signal(
                "workload_flag",
                _WEIGHTS["workload_flag"],
                f"{consec} consecutive days",
            ))

        # Compute total score
        total = sum(s.weight for s in signals)

        if total > 0:
            results.append(ScoredAppearance(
                pitcher_id=pitcher_id,
                pitcher_name=row["player_name"],
                throws=row["p_throws"],
                game_date=game_date,
                game_pk=game_pk,
                n_pitches=row["n_pitches"],
                score=total,
                signals=signals,
            ))

    # Sort by score descending, return top N
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:top_n]


# ── Season baseline helpers ──────────────────────────────────────────


def _build_season_baseline(season_df: pl.DataFrame) -> pl.DataFrame:
    """Weighted season baseline per pitcher across game types."""
    id_cols = {"season", "level", "game_type", "pitcher", "player_name",
               "p_throws", "team_code", "n_pitches"}
    metric_cols = [c for c in season_df.columns if c not in id_cols]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return season_df.group_by("pitcher").agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        *weighted_exprs,
    )


def _build_season_type_baseline(season_type_df: pl.DataFrame) -> pl.DataFrame:
    """Weighted season baseline per pitcher per pitch type."""
    df = season_type_df.filter(pl.col("pitch_type") != "")
    id_cols = {"season", "level", "game_type", "pitcher", "player_name",
               "p_throws", "team_code", "pitch_type", "n_pitches"}
    metric_cols = [c for c in df.columns if c not in id_cols]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    # Also compute total pitches across all types for usage %
    pitcher_totals = df.group_by("pitcher").agg(
        pl.col("n_pitches").sum().alias("total_pitches"),
    )
    result = df.group_by(["pitcher", "pitch_type"]).agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        *weighted_exprs,
    )
    return result.join(pitcher_totals, on="pitcher").with_columns(
        (pl.col("n_pitches") / pl.col("total_pitches") * 100).alias("usage_pct"),
    )


def _compute_velo_baselines() -> pl.DataFrame:
    """Compute season avg fastball velocity per pitcher from statcast.

    Returns DataFrame with columns: pitcher, season_velo, and per-game velos.
    """
    from pitcher_narratives.data import PARQUET_PATH

    if not PARQUET_PATH.exists():
        return pl.DataFrame(schema={"pitcher": pl.Int64, "season_velo": pl.Float64})

    # Only load the columns we need
    df = pl.read_parquet(
        PARQUET_PATH,
        columns=["pitcher", "game_pk", "game_date", "pitch_type", "release_speed"],
    )
    fastballs = df.filter(pl.col("pitch_type").is_in(["FF", "SI", "FC"]))

    season = fastballs.group_by("pitcher").agg(
        pl.col("release_speed").mean().alias("season_velo"),
    )

    game = fastballs.group_by(["pitcher", "game_pk"]).agg(
        pl.col("release_speed").mean().alias("game_velo"),
        pl.col("game_date").first(),
    )

    return game.join(season, on="pitcher")


def _find_consecutive_day_pitchers(app_df: pl.DataFrame) -> dict[int, int]:
    """Find pitchers with consecutive-day appearances ending on the most recent date."""
    max_date = _get_max_date(app_df)
    # Get unique pitcher-date pairs
    pitcher_dates = (
        app_df.select("pitcher", "game_date")
        .unique()
        .sort(["pitcher", "game_date"])
    )

    result: dict[int, int] = {}
    for pitcher_id in pitcher_dates["pitcher"].unique().to_list():
        dates = sorted(
            pitcher_dates.filter(pl.col("pitcher") == pitcher_id)["game_date"].to_list()
        )
        if not dates or dates[-1] != max_date:
            continue
        consec = 1
        for i in range(len(dates) - 2, -1, -1):
            if (dates[i + 1] - dates[i]).days == 1:
                consec += 1
            else:
                break
        result[pitcher_id] = consec

    return result


# ── Signal checkers ──────────────────────────────────────────────────


def _check_velo_delta(
    pitcher_id: int,
    game_pk: int,
    game_date: date,
    velo_df: pl.DataFrame,
) -> list[Signal]:
    """Check fastball velocity delta vs season."""
    if velo_df.is_empty():
        return []
    game_row = velo_df.filter(
        (pl.col("pitcher") == pitcher_id) & (pl.col("game_pk") == game_pk)
    )
    if game_row.is_empty():
        return []

    game_velo = game_row["game_velo"][0]
    season_velo = game_row["season_velo"][0]
    if game_velo is None or season_velo is None:
        return []

    delta = float(game_velo) - float(season_velo)
    if abs(delta) >= _VELO_THRESHOLD:
        direction = "up" if delta > 0 else "down"
        return [Signal(
            "velo_delta",
            _WEIGHTS["velo_delta"],
            f"FB velo {direction} {abs(delta):.1f} mph "
            f"({float(game_velo):.1f} vs {float(season_velo):.1f} season)",
        )]
    return []


def _check_pplus_swing(
    app_row: dict,
    pitcher_baseline: pl.DataFrame,
) -> list[Signal]:
    """Check overall P+ swing vs season baseline."""
    signals: list[Signal] = []
    game_pplus = app_row.get("P+")
    if game_pplus is None:
        return signals

    bl = pitcher_baseline.row(0, named=True)
    season_pplus = bl.get("P+")
    if season_pplus is None:
        return signals

    delta = float(game_pplus) - float(season_pplus)
    if abs(delta) >= _PPLUS_THRESHOLD:
        direction = "up" if delta > 0 else "down"
        signals.append(Signal(
            "pplus_swing",
            _WEIGHTS["pplus_swing"],
            f"P+ {direction} {abs(delta):.0f} pts "
            f"({float(game_pplus):.0f} vs {float(season_pplus):.0f} season)",
        ))
    return signals


def _check_splus_lplus_divergence(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
) -> list[Signal]:
    """Check for S+ and L+ moving in opposite directions on any pitch type."""
    signals: list[Signal] = []
    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        bl_row = pitcher_type_bl.filter(pl.col("pitch_type") == pt)
        if bl_row.is_empty():
            continue

        bl = bl_row.row(0, named=True)
        game_s = row.get("S+")
        game_l = row.get("L+")
        season_s = bl.get("S+")
        season_l = bl.get("L+")

        if any(v is None for v in (game_s, game_l, season_s, season_l)):
            continue

        s_delta = float(game_s) - float(season_s)
        l_delta = float(game_l) - float(season_l)

        # Opposite directions, both meaningful magnitude
        if (s_delta > _DIVERGENCE_THRESHOLD and l_delta < -_DIVERGENCE_THRESHOLD) or \
           (s_delta < -_DIVERGENCE_THRESHOLD and l_delta > _DIVERGENCE_THRESHOLD):
            pitch_name = row.get("pitch_type", pt)
            signals.append(Signal(
                "splus_lplus_divergence",
                _WEIGHTS["splus_lplus_divergence"],
                f"{pitch_name}: S+ {s_delta:+.0f}, L+ {l_delta:+.0f} (stuff/command split)",
            ))
    return signals


def _check_usage_shifts(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
    total_pitches: int,
) -> list[Signal]:
    """Check for large pitch usage shifts vs season."""
    signals: list[Signal] = []
    if total_pitches == 0:
        return signals

    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        bl_row = pitcher_type_bl.filter(pl.col("pitch_type") == pt)
        if bl_row.is_empty():
            continue

        bl = bl_row.row(0, named=True)
        game_usage = (row["n_pitches"] / total_pitches) * 100
        season_usage = bl.get("usage_pct")
        if season_usage is None:
            continue

        delta = game_usage - float(season_usage)
        if abs(delta) >= _USAGE_THRESHOLD:
            direction = "up" if delta > 0 else "down"
            signals.append(Signal(
                "usage_shift",
                _WEIGHTS["usage_shift"],
                f"{pt} usage {direction} {abs(delta):.1f}pp "
                f"({game_usage:.1f}% vs {float(season_usage):.1f}% season)",
            ))
    return signals


def _check_repertoire_changes(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
    total_pitches: int,
) -> list[Signal]:
    """Check for new or dropped pitches."""
    signals: list[Signal] = []
    if total_pitches == 0:
        return signals

    game_pitch_types = set(game_types["pitch_type"].to_list())

    # New pitches: appeared in game but not in season (or < 1% season usage)
    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        game_usage = (row["n_pitches"] / total_pitches) * 100
        if game_usage < _NEW_PITCH_GAME_MIN:
            continue

        bl_row = pitcher_type_bl.filter(pl.col("pitch_type") == pt)
        if bl_row.is_empty() or float(bl_row["usage_pct"][0]) < _NEW_PITCH_SEASON_MAX:
            signals.append(Signal(
                "new_pitch",
                _WEIGHTS["new_pitch"],
                f"{pt} appeared at {game_usage:.1f}% (new or rarely used)",
            ))

    # Dropped pitches: in season but not in game
    for bl_row in pitcher_type_bl.iter_rows(named=True):
        pt = bl_row["pitch_type"]
        if pt not in game_pitch_types and float(bl_row["usage_pct"]) >= _DROPPED_PITCH_SEASON_MIN:
            signals.append(Signal(
                "dropped_pitch",
                _WEIGHTS["dropped_pitch"],
                f"{pt} dropped (was {float(bl_row['usage_pct']):.1f}% of season mix)",
            ))

    return signals


def _check_walk_contradiction(
    app_row: dict,
    pitcher_baseline: pl.DataFrame,
) -> list[Signal]:
    """Check for high walk rate with good P+ (the command contradiction)."""
    # We need to estimate walk rate from the appearance data.
    # The appearance CSV doesn't have BB count directly, but we can
    # approximate from the statcast data or use a proxy.
    # For now, we'll use the P+ vs L+ divergence at the appearance level
    # as a proxy — high P+ with very low L+ suggests the contradiction.
    game_pplus = app_row.get("P+")
    game_lplus = app_row.get("L+")
    if game_pplus is None or game_lplus is None:
        return []

    # High overall P+ but poor location = stuff is good, command is not
    if float(game_pplus) >= _PPLUS_GOOD and float(game_lplus) < 85:
        return [Signal(
            "walk_rate_pplus_contradiction",
            _WEIGHTS["walk_rate_pplus_contradiction"],
            f"P+ {float(game_pplus):.0f} but L+ only {float(game_lplus):.0f} (stuff without command)",
        )]
    return []


def _check_development_opportunity(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
) -> list[Signal]:
    """Check for pitches with high S+ but low L+ — development candidates."""
    signals: list[Signal] = []
    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        game_s = row.get("S+")
        game_l = row.get("L+")
        if game_s is None or game_l is None:
            continue

        if float(game_s) >= _DEV_SPLUS_MIN and float(game_l) <= _DEV_LPLUS_MAX:
            signals.append(Signal(
                "development_opportunity",
                _WEIGHTS["development_opportunity"],
                f"{pt}: S+ {float(game_s):.0f} / L+ {float(game_l):.0f} (stuff without feel)",
            ))
    return signals
