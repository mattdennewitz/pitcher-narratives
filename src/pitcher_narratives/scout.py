"""Appearance interest scoring for triage.

Scans all pitcher appearances in a date window and scores each one
for "interestingness" — velocity swings, P+ outliers, usage shifts,
new/dropped pitches, development opportunities, etc.

Does NOT invoke the LLM pipeline. This is a cheap pre-filter that
ranks appearances so you only generate capsules for the interesting ones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import cast

import polars as pl

from pitcher_narratives.data import (
    classify_game_roles,
    compute_pitch_type_baseline,
    compute_season_baseline,
    load_all_statcast,
    load_full_agg,
)

__all__ = [
    "ScoredAppearance",
    "compute_pitch_profiles",
    "compute_velo_baselines",
    "scout_appearances",
    "top_per_role",
]

log = logging.getLogger("pitcher_narratives.scout")

# ── Scoring weights ──────────────────────────────────────────────────

_WEIGHTS = {
    "velo_delta": 3.0,
    "velo_decline": 3.5,  # in-game velo cliff -- strong acute-injury tell
    "spin_drop": 2.0,  # fastball spin loss -- corroborates arm trouble
    "pplus_swing": 2.5,
    "splus_lplus_divergence": 3.0,
    "usage_shift": 2.0,
    "new_pitch": 4.0,
    "dropped_pitch": 3.0,
    "hard_hit_spike": 1.5,
    "walk_rate_pplus_contradiction": 2.5,
    "development_opportunity": 3.5,
    "command_surge": 3.5,
    "workload_flag": 1.0,
}

# ── Thresholds ───────────────────────────────────────────────────────

_VELO_THRESHOLD = 1.5  # mph from season avg (population flat floor)
_VELO_Z_THRESHOLD = 2.0  # robust (median/MAD) sigmas from a pitcher's own game-to-game velo
_VELO_DECLINE_THRESHOLD = 1.5  # mph drop within a start (first-third -> last-third FB velo)
_SPIN_Z_THRESHOLD = 1.5  # robust sigmas of fastball spin below a pitcher's own norm
_MIN_FB_FOR_DECLINE = 9  # fastballs needed before an in-game decline is trustworthy
_MAD_TO_STD = 1.4826  # scales median-absolute-deviation to a normal-consistent std
_FB_TYPES = ["FF", "SI", "FC"]  # four/two-seam + cutter -- the "fastball" family
_MIN_GAMES_FOR_Z = 5  # other games a pitcher needs before a robust z is trusted
_VELO_RSTD_FLOOR = 0.4  # mph floor on the robust velo scale (thin baselines can't manufacture z)
_SPIN_RSTD_FLOOR = 40.0  # rpm floor on the robust spin scale
_PPLUS_THRESHOLD = 15  # points from season
_DIVERGENCE_THRESHOLD = 10  # S+ and L+ moving opposite directions, each ≥ this
_MIN_TYPE_PITCHES = 3
"""Minimum pitches of a type in an outing before its S+/L+ grades are trusted.
Per-pitch-type Stuff+/Location+ are model outputs that blow up on tiny samples
(a single sinker once produced a -138 Location+, a phantom -261 'divergence')."""
_USAGE_THRESHOLD = 8.0  # percentage points
_NEW_PITCH_SEASON_MAX = 1.0  # season usage % below which = "new"
_NEW_PITCH_GAME_MIN = 5.0  # game usage % above which = meaningful
_DROPPED_PITCH_SEASON_MIN = 10.0  # season usage % above which = established
_PPLUS_GOOD = 105  # P+ above which walk contradiction fires
_DEV_SPLUS_MIN = 110  # high stuff threshold
_DEV_LPLUS_MAX = 80  # low command threshold
_COMMAND_POOR_LPLUS = 90  # season L+ below which the pitch was a command liability
_COMMAND_GOOD_LPLUS = 110  # game L+ at/above which command is now a genuine strength
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
    role: str = "RP"
    signals: list[Signal] = field(default_factory=list)

    @property
    def signal_summary(self) -> str:
        """One-line summary of fired signals."""
        return " | ".join(f"{s.name}: {s.detail}" for s in self.signals)




def top_per_role(results: list[ScoredAppearance], top_n: int) -> list[ScoredAppearance]:
    """Keep the top N per role, merged and sorted by score descending."""
    ranked = sorted(results, key=lambda x: x.score, reverse=True)
    sp = [r for r in ranked if r.role == "SP"][:top_n]
    rp = [r for r in ranked if r.role == "RP"][:top_n]
    merged = sp + rp
    merged.sort(key=lambda x: x.score, reverse=True)
    return merged


def _statcast_max_mlb_date() -> date | None:
    """Most recent MLB game date in the statcast parquet, or None if unavailable."""
    df = load_all_statcast(columns=["game_date", "level"])
    if df.is_empty():
        return None
    val = df.filter(pl.col("level") == "MLB")["game_date"].max()
    return cast(date, val) if val is not None else None


def _get_max_date(appearance_df: pl.DataFrame) -> date:
    """Get the most recent date in the appearance data."""
    val = appearance_df["game_date"].max()
    if val is None:
        raise ValueError("No appearances found")
    return cast(date, val)


def scout_appearances(
    *,
    window_days: int = 1,
    min_pitches: int = 20,
) -> list[ScoredAppearance]:
    """Score all pitcher appearances in a date window by interestingness.

    Args:
        window_days: How many days back to scan (default: 1 = most recent date only).
        min_pitches: Minimum pitches in an appearance to consider.

    Returns:
        Every scored appearance in the window, highest score first.
    """
    # Load data
    app_df = load_full_agg("pitcher_appearance")
    app_type_df = load_full_agg("pitcher_type_appearance")
    season_type_df = load_full_agg("pitcher_type")
    season_df = load_full_agg("pitcher")

    # Filter to MLB regular season
    app_df = app_df.filter(pl.col("level") == "MLB")
    app_type_df = app_type_df.filter(pl.col("level") == "MLB")
    season_type_df = season_type_df.filter(pl.col("level") == "MLB")
    season_df = season_df.filter(pl.col("level") == "MLB")

    # Determine date window
    max_date = _get_max_date(app_df)

    # Guard against a stale appearance aggregate. The scout iterates the
    # appearance aggregates, but velocity and role signals are sourced from the
    # statcast parquet. If statcast leads the aggregates (e.g. `make pull-statcast`
    # ran without `make pull-aggs`), the most recent outings exist in statcast but
    # never enter the window -- they are silently invisible to scoring. This is
    # the mirror image of the role-map guard below, which handles statcast lagging.
    statcast_max = _statcast_max_mlb_date()
    if statcast_max is not None and statcast_max > max_date:
        log.warning(
            "Appearance aggregate is stale: statcast has MLB games through %s but the "
            "appearance aggregate stops at %s. Outings after %s are invisible to the "
            "scout -- run `make pull-aggs` (or `make pull-data`) to refresh.",
            statcast_max, max_date, max_date,
        )

    cutoff = max_date - timedelta(days=window_days - 1)
    app_window = app_df.filter(
        (pl.col("game_date") >= cutoff) & (pl.col("n_pitches") >= min_pitches)
    )

    # Build season baselines per pitcher (weighted across game types)
    season_baseline = compute_season_baseline(season_df)
    season_type_baseline = compute_pitch_type_baseline(season_type_df)

    # Velocity + spin profiles from statcast (game velo/spin, per-pitcher robust
    # center/scale, and in-game velo decline) feed the velo-change, in-game
    # velo-decline, and spin-drop checkers.
    pitch_profiles = compute_pitch_profiles()

    # Score all appearances in recent date(s) that had enough appearances to
    # build a season baseline
    app_type_window = app_type_df.filter(
        (pl.col("game_date") >= cutoff)
        & (pl.col("pitch_type") != "")
    )

    # Track consecutive-day pitchers
    consecutive_days = _find_consecutive_day_pitchers(app_df)

    role_map = _compute_role_map()

    # Guard against a silent role-classification failure. The role map is built
    # from the statcast parquet, while appearances come from the aggregates. If
    # the parquet lags the aggs (e.g. `make pull-aggs` ran without
    # `make pull-statcast`), recent game_pks are absent from the map and every
    # appearance silently defaults to "RP" -- turning starters into relievers.
    window_keys = [
        (r["pitcher"], r["game_pk"])
        for r in app_window.select("pitcher", "game_pk").iter_rows(named=True)
    ]
    missing = sum(1 for k in window_keys if k not in role_map)
    if window_keys and missing / len(window_keys) > 0.5:
        log.warning(
            "Role classification degraded: %d/%d window appearances (%.0f%%) are "
            "missing from the role map and will default to RP. The statcast parquet "
            "is likely stale relative to the aggregates -- run `make pull-statcast` "
            "(or `make pull-data`).",
            missing, len(window_keys), 100.0 * missing / len(window_keys),
        )

    results: list[ScoredAppearance] = []
    for row in app_window.iter_rows(named=True):
        pitcher_id = row["pitcher"]
        game_pk = row["game_pk"]
        game_date = row["game_date"]

        # Get this pitcher's season baseline (most recent season only)
        pitcher_baseline = season_baseline.filter(pl.col("pitcher") == pitcher_id)
        if pitcher_baseline.is_empty():
            continue
        pitcher_baseline = pitcher_baseline.sort("season", descending=True).head(1)

        # Get per-pitch-type data for this appearance
        game_types = app_type_window.filter(
            (pl.col("pitcher") == pitcher_id) & (pl.col("game_pk") == game_pk)
        )

        # Get pitcher's season pitch type baselines (most recent season only)
        pitcher_type_bl = season_type_baseline.filter(pl.col("pitcher") == pitcher_id)
        max_season = pitcher_type_bl["season"].max()
        if max_season is not None:
            pitcher_type_bl = pitcher_type_bl.filter(pl.col("season") == max_season)

        signals: list[Signal] = []

        # --- Signal: Velocity change (flat + per-pitcher robust z) ---
        signals.extend(_check_velo_change(pitcher_id, game_pk, pitch_profiles))

        # --- Signal: In-game velocity decline (acute-injury tell) ---
        signals.extend(_check_velo_decline(pitcher_id, game_pk, pitch_profiles))

        # --- Signal: Fastball spin drop ---
        signals.extend(_check_spin_drop(pitcher_id, game_pk, pitch_profiles))

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

        # --- Signal: Command surge (Location+ jump) ---
        command_signals = _check_command_surge(game_types, pitcher_type_bl)
        signals.extend(command_signals)

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
                role=role_map.get((pitcher_id, game_pk), "RP"),
                signals=signals,
            ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results




def compute_velo_baselines() -> pl.DataFrame:
    """Compute season avg fastball velocity per pitcher from statcast.

    Returns DataFrame with columns: pitcher, season_velo, and per-game velos.
    """
    df = load_all_statcast(
        columns=["pitcher", "game_pk", "game_date", "pitch_type", "release_speed", "level"],
    )
    if df.is_empty():
        return pl.DataFrame(schema={"pitcher": pl.Int64, "season_velo": pl.Float64})
    # MLB-only norm: exclude minor-league (A/AAA) and WBC pitches so the
    # season velocity baseline is not diluted by non-MLB outings.
    df = df.filter(pl.col("level") == "MLB")
    fastballs = df.filter(pl.col("pitch_type").is_in(["FF", "SI", "FC"]))
    fastballs = fastballs.with_columns(pl.col("game_date").dt.year().alias("_year"))

    season = fastballs.group_by(["pitcher", "_year"]).agg(
        pl.col("release_speed").mean().alias("season_velo"),
    )

    game = fastballs.group_by(["pitcher", "game_pk"]).agg(
        pl.col("release_speed").mean().alias("game_velo"),
        pl.col("game_date").first(),
        pl.col("_year").first(),
    )

    return game.join(season, on=["pitcher", "_year"]).drop("_year")


def _leave_one_out_robust(per_game: pl.DataFrame) -> pl.DataFrame:
    """Per-game robust center/scale over a pitcher's OTHER same-year games.

    For each (pitcher, game_pk) returns the median and MAD-derived std of the
    pitcher's remaining games' fastball velo/spin -- leave-one-out, so the game
    under evaluation never dilutes its own z-score. Requires ``_MIN_GAMES_FOR_Z``
    other games and floors the scale (``_VELO_RSTD_FLOOR`` / ``_SPIN_RSTD_FLOOR``);
    below the game count, center/scale are null so the z path stays inert and
    only the population-flat floor fires.
    """
    pg = per_game.select("pitcher", "_year", "game_pk", "game_velo", "game_spin")
    other = pg.select(
        "pitcher", "_year",
        pl.col("game_pk").alias("_og"),
        pl.col("game_velo").alias("_ov"),
        pl.col("game_spin").alias("_os"),
    )
    # All same-year game pairs, minus self -> each row's "other games" set.
    pairs = pg.join(other, on=["pitcher", "_year"]).filter(
        pl.col("game_pk") != pl.col("_og")
    )
    med = pairs.group_by(["pitcher", "_year", "game_pk"]).agg(
        pl.col("_ov").median().alias("velo_median"),
        pl.col("_os").median().alias("spin_median"),
        pl.len().alias("_n_other"),
    )
    dev = pairs.join(med, on=["pitcher", "_year", "game_pk"]).with_columns(
        (pl.col("_ov") - pl.col("velo_median")).abs().alias("_adv"),
        (pl.col("_os") - pl.col("spin_median")).abs().alias("_ads"),
    )
    mad = dev.group_by(["pitcher", "_year", "game_pk"]).agg(
        (pl.col("_adv").median() * _MAD_TO_STD).alias("velo_rstd"),
        (pl.col("_ads").median() * _MAD_TO_STD).alias("spin_rstd"),
    )
    loo = med.join(mad, on=["pitcher", "_year", "game_pk"])
    enough = pl.col("_n_other") >= _MIN_GAMES_FOR_Z
    return loo.with_columns(
        pl.when(enough).then(pl.col("velo_median")).alias("velo_median"),
        pl.when(enough).then(pl.col("spin_median")).alias("spin_median"),
        pl.when(enough).then(
            pl.max_horizontal(pl.col("velo_rstd"), pl.lit(_VELO_RSTD_FLOOR))
        ).alias("velo_rstd"),
        pl.when(enough).then(
            pl.max_horizontal(pl.col("spin_rstd"), pl.lit(_SPIN_RSTD_FLOOR))
        ).alias("spin_rstd"),
    ).select("pitcher", "game_pk", "velo_median", "velo_rstd", "spin_median", "spin_rstd")


def _in_game_velo_decline(raw: pl.DataFrame) -> pl.DataFrame:
    """Fastball velo in the last third of a start minus the first third.

    Buckets thirds over ALL pitches by throw order (at-bat, then pitch number),
    then averages fastball velo within the first and last thirds. Bucketing over
    every pitch -- not just fastballs -- keeps a late velo cliff visible even when
    the pitcher goes soft (fewer fastballs) late, the exact compensation pattern
    that a fastball-position split would smear away.
    """
    is_fb = pl.col("pitch_type").is_in(_FB_TYPES)
    allp = raw.sort(["pitcher", "game_pk", "at_bat_number", "pitch_number"]).with_columns(
        pl.int_range(pl.len()).over(["pitcher", "game_pk"]).alias("_idx"),
        pl.len().over(["pitcher", "game_pk"]).alias("_n"),
    ).with_columns((pl.col("_idx") * 3 // pl.col("_n")).alias("_third"))
    wide = (
        allp.filter(is_fb & pl.col("_third").is_in([0, 2]))
        .group_by(["pitcher", "game_pk", "_third"])
        .agg(pl.col("release_speed").mean().alias("_tv"))
        .pivot(on="_third", index=["pitcher", "game_pk"], values="_tv")
    )
    for col in ("0", "2"):  # a game may lack fastballs in one third
        if col not in wide.columns:
            wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(col))
    return wide.rename({"0": "velo_first_third", "2": "velo_last_third"}).with_columns(
        (pl.col("velo_last_third") - pl.col("velo_first_third")).alias("velo_decline")
    ).select("pitcher", "game_pk", "velo_first_third", "velo_last_third", "velo_decline")


def compute_pitch_profiles() -> pl.DataFrame:
    """Per-(pitcher, game_pk) fastball velocity and spin profiles from statcast.

    Richer than :func:`compute_velo_baselines`: alongside each game's fastball
    velocity it carries the pitcher's own leave-one-out robust game-to-game
    center/scale (median + MAD-derived std) for velocity and spin, the season
    spin mean, and the in-game velocity decline. These feed the injury-oriented
    checkers -- in-game velo cliff, spin drop, and the per-pitcher robust-z
    velocity change -- which the population-flat ``_check_velo_delta`` cannot
    express.

    Columns: pitcher, game_pk, game_date, game_velo, season_velo, velo_median,
    velo_rstd, game_spin, season_spin, spin_median, spin_rstd, velo_first_third,
    velo_last_third, velo_decline. Empty frame when no statcast is available.
    """
    raw = load_all_statcast(columns=[
        "pitcher", "game_pk", "game_date", "pitch_type", "release_speed",
        "release_spin_rate", "at_bat_number", "pitch_number", "level",
    ])
    if raw.is_empty():
        return pl.DataFrame()
    # MLB pitches with a recorded velocity. Kept at all pitch types so the
    # in-game decline can bucket thirds over the whole outing; fastball-only
    # views are derived below.
    raw = raw.filter(
        (pl.col("level") == "MLB") & pl.col("release_speed").is_not_null()
    ).with_columns(pl.col("game_date").dt.year().alias("_year"))
    fb = raw.filter(pl.col("pitch_type").is_in(_FB_TYPES))
    if fb.is_empty():
        return pl.DataFrame()

    per_game = fb.group_by(["pitcher", "game_pk"]).agg(
        pl.col("release_speed").mean().alias("game_velo"),
        pl.col("release_spin_rate").mean().alias("game_spin"),
        pl.col("game_date").first(),
        pl.col("_year").first(),
        pl.len().alias("_n_fb"),
    )

    # Pitch-weighted season means (per pitcher-year) -- flat floor + reporting.
    season = fb.group_by(["pitcher", "_year"]).agg(
        pl.col("release_speed").mean().alias("season_velo"),
        pl.col("release_spin_rate").mean().alias("season_spin"),
    )

    loo = _leave_one_out_robust(per_game)
    thirds = _in_game_velo_decline(raw)

    out = (
        per_game
        .join(season, on=["pitcher", "_year"])
        .join(loo, on=["pitcher", "game_pk"], how="left")
        .join(thirds, on=["pitcher", "game_pk"], how="left")
    )
    # Suppress the decline for outings with too few fastballs to trust a trend.
    thin = pl.col("_n_fb") < _MIN_FB_FOR_DECLINE
    out = out.with_columns(
        pl.when(thin).then(None).otherwise(pl.col(col)).alias(col)
        for col in ("velo_decline", "velo_first_third", "velo_last_third")
    )
    return out.drop("_year", "_n_fb")


def _compute_role_map() -> dict[tuple[int, int], str]:
    """Map (pitcher_id, game_pk) -> 'SP'/'RP' from league-wide statcast."""
    df = load_all_statcast(
        columns=["pitcher", "game_pk", "inning_topbot", "at_bat_number"],
    )
    if df.is_empty():
        return {}
    roles = classify_game_roles(df)
    return {
        (row["pitcher"], row["game_pk"]): row["role"]
        for row in roles.iter_rows(named=True)
    }


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


def _profile_row(pitcher_id: int, game_pk: int, profiles: pl.DataFrame) -> dict | None:
    """Look up a pitcher's game row in a compute_pitch_profiles frame, or None."""
    if profiles.is_empty():
        return None
    row = profiles.filter(
        (pl.col("pitcher") == pitcher_id) & (pl.col("game_pk") == game_pk)
    )
    return row.row(0, named=True) if not row.is_empty() else None


def _check_velo_change(
    pitcher_id: int,
    game_pk: int,
    profiles: pl.DataFrame,
) -> list[Signal]:
    """Fastball velocity change vs season -- population-flat OR pitcher-relative.

    Supersedes the flat-only :func:`_check_velo_delta` in the scoring loop: it
    fires on the same absolute 1.5 mph floor AND on a robust (median/MAD)
    z-score, so a drop that is small in absolute terms but large for a
    low-variance pitcher is still caught. The robust center resists a prior
    aborted start that would desensitize a plain std.
    """
    r = _profile_row(pitcher_id, game_pk, profiles)
    if r is None or r["game_velo"] is None or r["season_velo"] is None:
        return []
    game_velo, season_velo = float(r["game_velo"]), float(r["season_velo"])
    delta = game_velo - season_velo

    z = None
    if r["velo_median"] is not None and r["velo_rstd"] not in (None, 0.0):
        z = (game_velo - float(r["velo_median"])) / float(r["velo_rstd"])

    flat_fires = abs(delta) >= _VELO_THRESHOLD
    z_fires = z is not None and abs(z) >= _VELO_Z_THRESHOLD
    if not (flat_fires or z_fires):
        return []

    direction = "up" if delta > 0 else "down"
    z_note = f", z={z:+.1f}" if z is not None else ""
    return [Signal(
        "velo_delta",
        _WEIGHTS["velo_delta"],
        f"FB velo {direction} {abs(delta):.1f} mph "
        f"({game_velo:.1f} vs {season_velo:.1f} season{z_note})",
    )]


def _check_velo_decline(
    pitcher_id: int,
    game_pk: int,
    profiles: pl.DataFrame,
) -> list[Signal]:
    """In-game velocity cliff: fastball velo fell within the start itself.

    Compares first-third to last-third fastball velo by pitch order. A decline
    beyond normal end-of-start fatigue is a strong acute-injury tell that a
    game-average-vs-season comparison smears away -- exactly the signature that
    a game-average drop understates.
    """
    r = _profile_row(pitcher_id, game_pk, profiles)
    if r is None or r["velo_decline"] is None:
        return []
    decline = float(r["velo_decline"])
    if decline > -_VELO_DECLINE_THRESHOLD:
        return []
    first = r.get("velo_first_third")
    last = r.get("velo_last_third")
    where = (
        f" ({float(first):.1f} -> {float(last):.1f})"
        if first is not None and last is not None else ""
    )
    return [Signal(
        "velo_decline",
        _WEIGHTS["velo_decline"],
        f"FB velo fell {abs(decline):.1f} mph within the outing{where}",
    )]


def _check_spin_drop(
    pitcher_id: int,
    game_pk: int,
    profiles: pl.DataFrame,
) -> list[Signal]:
    """Fastball spin loss vs a pitcher's own norm (robust z).

    Spin dropping alongside velocity corroborates reduced arm output. Uses a
    robust z so a genuinely large spin cliff fires while a normal game-to-game
    wobble does not.
    """
    r = _profile_row(pitcher_id, game_pk, profiles)
    if r is None or r["game_spin"] is None or r["spin_median"] is None:
        return []
    if r["spin_rstd"] in (None, 0.0):
        return []
    game_spin = float(r["game_spin"])
    z = (game_spin - float(r["spin_median"])) / float(r["spin_rstd"])
    if z > -_SPIN_Z_THRESHOLD:
        return []
    season_spin = r.get("season_spin")
    ref = float(season_spin) if season_spin is not None else float(r["spin_median"])
    return [Signal(
        "spin_drop",
        _WEIGHTS["spin_drop"],
        f"FB spin down {abs(game_spin - ref):.0f} rpm "
        f"({game_spin:.0f} vs {ref:.0f} season, z={z:+.1f})",
    )]


def _check_pplus_swing(
    app_row: dict,
    pitcher_baseline: pl.DataFrame,
) -> list[Signal]:
    """Check overall P+ swing vs season baseline."""
    game_pplus = app_row.get("P+")
    if game_pplus is None:
        return []

    season_pplus = pitcher_baseline.row(0, named=True).get("P+")
    if season_pplus is None:
        return []

    delta = float(game_pplus) - float(season_pplus)
    if abs(delta) >= _PPLUS_THRESHOLD:
        direction = "up" if delta > 0 else "down"
        return [Signal(
            "pplus_swing",
            _WEIGHTS["pplus_swing"],
            f"P+ {direction} {abs(delta):.0f} pts "
            f"({float(game_pplus):.0f} vs {float(season_pplus):.0f} season)",
        )]
    return []


def _check_splus_lplus_divergence(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
) -> list[Signal]:
    """Check for S+ and L+ moving in opposite directions on any pitch type."""
    signals: list[Signal] = []
    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        if row.get("n_pitches", 0) < _MIN_TYPE_PITCHES:
            continue  # too few pitches for a reliable S+/L+ grade
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
        opposite = (
            (s_delta > _DIVERGENCE_THRESHOLD and l_delta < -_DIVERGENCE_THRESHOLD)
            or (s_delta < -_DIVERGENCE_THRESHOLD and l_delta > _DIVERGENCE_THRESHOLD)
        )
        if opposite:
            signals.append(Signal(
                "splus_lplus_divergence",
                _WEIGHTS["splus_lplus_divergence"],
                f"{pt}: S+ {s_delta:+.0f}, L+ {l_delta:+.0f} (stuff/command split)",
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
    """Check for high P+ with poor L+ at the appearance level."""
    game_pplus = app_row.get("P+")
    game_lplus = app_row.get("L+")
    if game_pplus is None or game_lplus is None:
        return []

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
        if row.get("n_pitches", 0) < _MIN_TYPE_PITCHES:
            continue  # too few pitches for a reliable S+/L+ grade
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


def _check_command_surge(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
) -> list[Signal]:
    """Check for pitches that were a command liability and now locate well.

    The inverse of development_opportunity (elite stuff it can't command): a pitch
    whose season command was poor (low season L+) is suddenly located well (high
    game L+). Two decorrelated conditions — a prior deficit and a good outing —
    so the jump is a genuine arrival, not just a high-variance good-command day.
    """
    signals: list[Signal] = []
    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        if row.get("n_pitches", 0) < _MIN_TYPE_PITCHES:
            continue  # too few pitches for a reliable L+ grade
        bl_row = pitcher_type_bl.filter(pl.col("pitch_type") == pt)
        if bl_row.is_empty():
            continue

        bl = bl_row.row(0, named=True)
        game_l = row.get("L+")
        season_l = bl.get("L+")
        if game_l is None or season_l is None:
            continue

        if float(season_l) < _COMMAND_POOR_LPLUS and float(game_l) >= _COMMAND_GOOD_LPLUS:
            signals.append(Signal(
                "command_surge",
                _WEIGHTS["command_surge"],
                f"{pt}: L+ {float(season_l):.0f} → {float(game_l):.0f} — found the zone",
            ))
    return signals
