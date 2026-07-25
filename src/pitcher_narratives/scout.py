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
from typing import Literal, cast

import polars as pl

from pitcher_narratives.data import (
    FrameIntegrityError,
    compute_pitch_type_baseline,
    compute_season_baseline,
    load_emitted_grain,
    load_pitchingplus_bundle,
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
    "velo_decline": 3.5,  # in-game velocity decline
    "spin_drop": 2.0,  # fastball spin decline
    "pplus_swing": 2.5,
    "splus_lplus_divergence": 3.0,
    "usage_shift": 2.0,
    "new_pitch": 4.0,
    "dropped_pitch": 3.0,
    "hard_hit_spike": 1.5,
    "pplus_lplus_split": 2.5,
    "splus_lplus_level_gap": 3.5,
    "location_grade_surge": 3.5,
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
"""Minimum per-type outing sample eligible for an editorial scout signal.
This publication floor does not change the model output's validity."""
_USAGE_THRESHOLD = 8.0  # percentage points
_NEW_PITCH_SEASON_MAX = 1.0  # season usage % below which = "new"
_NEW_PITCH_GAME_MIN = 5.0  # game usage % above which = meaningful
_DROPPED_PITCH_SEASON_MIN = 10.0  # season usage % above which = established
_PPLUS_GOOD = 105  # P+ above which walk contradiction fires
_DEV_SPLUS_MIN = 110  # high Stuff+ threshold
_DEV_LPLUS_MAX = 80  # low Location+ threshold
_LOCATION_BASELINE_MAX = 90
_LOCATION_OUTING_MIN = 110
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
    role: Literal["SP", "RP"]
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


def _latest_emitted_mlb_date(all_pitches: pl.DataFrame) -> date | None:
    """Return the latest emitted MLB game date."""
    if all_pitches.is_empty():
        return None
    value = all_pitches.filter(pl.col("level") == "MLB")["game_date"].max()
    return cast(date, value) if value is not None else None


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
    bundle = load_pitchingplus_bundle()
    app_df = bundle.frame("pitcher_appearance")
    app_type_df = bundle.frame("pitcher_type_appearance")
    season_type_df = bundle.frame("pitcher_type")
    season_df = bundle.frame("pitcher")
    all_pitches = bundle.frame("all_pitches")

    # Filter to MLB regular season
    app_df = app_df.filter(pl.col("level") == "MLB")
    app_type_df = app_type_df.filter(pl.col("level") == "MLB")
    season_type_df = season_type_df.filter(pl.col("level") == "MLB")
    season_df = season_df.filter(pl.col("level") == "MLB")

    # Determine date window
    max_date = _get_max_date(app_df)

    # All grains came from one validated bundle. A cross-grain date mismatch is
    # therefore a producer-contract failure, not a condition to paper over.
    latest_pitch_date = _latest_emitted_mlb_date(all_pitches)
    if latest_pitch_date is not None and latest_pitch_date > max_date:
        raise FrameIntegrityError(
            "PitchingPlus bundle grains disagree: all_pitches has MLB games "
            f"through {latest_pitch_date}, but pitcher_appearance stops at "
            f"{max_date}"
        )

    cutoff = max_date - timedelta(days=window_days - 1)
    app_window = app_df.filter((pl.col("game_date") >= cutoff) & (pl.col("n_pitches") >= min_pitches))

    # Build season baselines per pitcher (weighted across game types)
    season_baseline = compute_season_baseline(season_df)
    season_type_baseline = compute_pitch_type_baseline(season_type_df)

    # Pitch profiles consume the manifest-covered all_pitches grain.
    pitch_profiles = compute_pitch_profiles(all_pitches)

    # Score all appearances in recent date(s) that had enough appearances to
    # build a season baseline
    app_type_window = app_type_df.filter((pl.col("game_date") >= cutoff) & (pl.col("pitch_type") != ""))

    # Track consecutive-day pitchers
    consecutive_days = _find_consecutive_day_pitchers(app_df)

    role_map = _compute_role_map(all_pitches)

    # Missing role keys would silently turn starters into relievers. Reject the
    # inconsistent bundle instead of inventing a fallback role.
    window_keys = [
        (r["pitcher"], r["game_pk"]) for r in app_window.select("pitcher", "game_pk").iter_rows(named=True)
    ]
    missing_keys = sorted(key for key in window_keys if key not in role_map)
    if missing_keys:
        raise FrameIntegrityError(
            f"PitchingPlus all_pitches cannot classify roles for emitted appearances: {missing_keys}"
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

        # --- Signal: P+/L+ appearance-level split ---
        split_signals = _check_pplus_lplus_split(row)
        signals.extend(split_signals)

        # --- Signal: High-S+/low-L+ level gap ---
        gap_signals = _check_splus_lplus_level_gap(game_types)
        signals.extend(gap_signals)

        # --- Signal: Location+ surge ---
        location_signals = _check_location_grade_surge(game_types, pitcher_type_bl)
        signals.extend(location_signals)

        # --- Signal: Workload flag ---
        consec = consecutive_days.get(pitcher_id, 0)
        if consec >= _CONSECUTIVE_DAYS_FLAG:
            signals.append(
                Signal(
                    "workload_flag",
                    _WEIGHTS["workload_flag"],
                    f"{consec} consecutive days",
                )
            )

        # Compute total score
        total = sum(s.weight for s in signals)

        if total > 0:
            results.append(
                ScoredAppearance(
                    pitcher_id=pitcher_id,
                    pitcher_name=row["player_name"],
                    throws=row["p_throws"],
                    game_date=game_date,
                    game_pk=game_pk,
                    n_pitches=row["n_pitches"],
                    score=total,
                    role=role_map[(pitcher_id, game_pk)],
                    signals=signals,
                )
            )

    results.sort(key=lambda x: x.score, reverse=True)
    return results


def compute_velo_baselines(
    all_pitches: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Compute season average fastball velocity from emitted pitches."""
    df = load_emitted_grain("all_pitches") if all_pitches is None else all_pitches
    if df.is_empty():
        return pl.DataFrame(schema={"pitcher": pl.Int64, "season_velo": pl.Float64})
    # MLB-only norm: exclude minor-league (A/AAA) and WBC pitches so the
    # season velocity baseline is not diluted by non-MLB outings.
    df = df.filter(pl.col("level") == "MLB")
    fastballs = df.filter(pl.col("pitch_type").is_in(["FF", "SI", "FC"]))
    season_column = "season" if "season" in fastballs.columns else "game_year"
    fastballs = fastballs.with_columns(pl.col(season_column).alias("_year"))

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
        "pitcher",
        "_year",
        pl.col("game_pk").alias("_og"),
        pl.col("game_velo").alias("_ov"),
        pl.col("game_spin").alias("_os"),
    )
    # All same-year game pairs, minus self -> each row's "other games" set.
    pairs = pg.join(other, on=["pitcher", "_year"]).filter(pl.col("game_pk") != pl.col("_og"))
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
        pl.when(enough)
        .then(pl.max_horizontal(pl.col("velo_rstd"), pl.lit(_VELO_RSTD_FLOOR)))
        .alias("velo_rstd"),
        pl.when(enough)
        .then(pl.max_horizontal(pl.col("spin_rstd"), pl.lit(_SPIN_RSTD_FLOOR)))
        .alias("spin_rstd"),
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
    allp = (
        raw.sort(["pitcher", "game_pk", "at_bat_number", "pitch_number"])
        .with_columns(
            pl.int_range(pl.len()).over(["pitcher", "game_pk"]).alias("_idx"),
            pl.len().over(["pitcher", "game_pk"]).alias("_n"),
        )
        .with_columns((pl.col("_idx") * 3 // pl.col("_n")).alias("_third"))
    )
    wide = (
        allp.filter(is_fb & pl.col("_third").is_in([0, 2]))
        .group_by(["pitcher", "game_pk", "_third"])
        .agg(pl.col("release_speed").mean().alias("_tv"))
        .pivot(on="_third", index=["pitcher", "game_pk"], values="_tv")
    )
    for col in ("0", "2"):  # a game may lack fastballs in one third
        if col not in wide.columns:
            wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(col))
    return (
        wide.rename({"0": "velo_first_third", "2": "velo_last_third"})
        .with_columns((pl.col("velo_last_third") - pl.col("velo_first_third")).alias("velo_decline"))
        .select("pitcher", "game_pk", "velo_first_third", "velo_last_third", "velo_decline")
    )


def compute_pitch_profiles(
    all_pitches: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Build emitted per-game velocity and spin profiles.

    Columns: pitcher, game_pk, game_date, game_velo, season_velo,
    velo_median, velo_rstd, game_spin, season_spin, spin_median,
    spin_rstd, velo_first_third, velo_last_third, and velo_decline.
    """
    raw = load_emitted_grain("all_pitches") if all_pitches is None else all_pitches
    if raw.is_empty():
        return pl.DataFrame()
    # MLB pitches with a recorded velocity. Kept at all pitch types so the
    # in-game decline can bucket thirds over the whole outing; fastball-only
    # views are derived below.
    raw = raw.filter((pl.col("level") == "MLB") & pl.col("release_speed").is_not_null())
    season_column = "season" if "season" in raw.columns else "game_year"
    raw = raw.with_columns(pl.col(season_column).alias("_year"))
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
        per_game.join(season, on=["pitcher", "_year"])
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


def _compute_role_map(
    all_pitches: pl.DataFrame | None = None,
) -> dict[tuple[int, int], str]:
    """Map emitted pitcher appearances to starter/reliever roles."""
    df = load_emitted_grain("all_pitches") if all_pitches is None else all_pitches
    if df.is_empty():
        return {}
    roles = (
        df.group_by(["pitcher", "game_pk"])
        .agg(pl.col("inning").min().alias("first_inning"))
        .with_columns(
            pl.when(pl.col("first_inning") == 1).then(pl.lit("SP")).otherwise(pl.lit("RP")).alias("role")
        )
    )
    return {(row["pitcher"], row["game_pk"]): row["role"] for row in roles.iter_rows(named=True)}


def _find_consecutive_day_pitchers(app_df: pl.DataFrame) -> dict[int, int]:
    """Find pitchers with consecutive-day appearances ending on the most recent date."""
    max_date = _get_max_date(app_df)
    # Get unique pitcher-date pairs
    pitcher_dates = app_df.select("pitcher", "game_date").unique().sort(["pitcher", "game_date"])

    result: dict[int, int] = {}
    for pitcher_id in pitcher_dates["pitcher"].unique().to_list():
        dates = sorted(pitcher_dates.filter(pl.col("pitcher") == pitcher_id)["game_date"].to_list())
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
    game_row = velo_df.filter((pl.col("pitcher") == pitcher_id) & (pl.col("game_pk") == game_pk))
    if game_row.is_empty():
        return []

    game_velo = game_row["game_velo"][0]
    season_velo = game_row["season_velo"][0]
    if game_velo is None or season_velo is None:
        return []

    delta = float(game_velo) - float(season_velo)
    if abs(delta) >= _VELO_THRESHOLD:
        direction = "up" if delta > 0 else "down"
        return [
            Signal(
                "velo_delta",
                _WEIGHTS["velo_delta"],
                f"FB velo {direction} {abs(delta):.1f} mph "
                f"({float(game_velo):.1f} vs {float(season_velo):.1f} season)",
            )
        ]
    return []


def _profile_row(pitcher_id: int, game_pk: int, profiles: pl.DataFrame) -> dict | None:
    """Look up a pitcher's game row in a compute_pitch_profiles frame, or None."""
    if profiles.is_empty():
        return None
    row = profiles.filter((pl.col("pitcher") == pitcher_id) & (pl.col("game_pk") == game_pk))
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
    return [
        Signal(
            "velo_delta",
            _WEIGHTS["velo_delta"],
            f"FB velo {direction} {abs(delta):.1f} mph ({game_velo:.1f} vs {season_velo:.1f} season{z_note})",
        )
    ]


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
    where = f" ({float(first):.1f} -> {float(last):.1f})" if first is not None and last is not None else ""
    return [
        Signal(
            "velo_decline",
            _WEIGHTS["velo_decline"],
            f"FB velo fell {abs(decline):.1f} mph within the outing{where}",
        )
    ]


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
    return [
        Signal(
            "spin_drop",
            _WEIGHTS["spin_drop"],
            f"FB spin down {abs(game_spin - ref):.0f} rpm ({game_spin:.0f} vs {ref:.0f} season, z={z:+.1f})",
        )
    ]


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
        return [
            Signal(
                "pplus_swing",
                _WEIGHTS["pplus_swing"],
                f"P+ {direction} {abs(delta):.0f} pts "
                f"({float(game_pplus):.0f} vs {float(season_pplus):.0f} season)",
            )
        ]
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
        opposite = (s_delta > _DIVERGENCE_THRESHOLD and l_delta < -_DIVERGENCE_THRESHOLD) or (
            s_delta < -_DIVERGENCE_THRESHOLD and l_delta > _DIVERGENCE_THRESHOLD
        )
        if opposite:
            signals.append(
                Signal(
                    "splus_lplus_divergence",
                    _WEIGHTS["splus_lplus_divergence"],
                    f"{pt}: S+ {s_delta:+.0f}, L+ {l_delta:+.0f} (S+/L+ divergence)",
                )
            )
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
            signals.append(
                Signal(
                    "usage_shift",
                    _WEIGHTS["usage_shift"],
                    f"{pt} usage {direction} {abs(delta):.1f}pp "
                    f"({game_usage:.1f}% vs {float(season_usage):.1f}% season)",
                )
            )
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
            signals.append(
                Signal(
                    "new_pitch",
                    _WEIGHTS["new_pitch"],
                    f"{pt} appeared at {game_usage:.1f}% (new or rarely used)",
                )
            )

    # Dropped pitches: in season but not in game
    for bl_row in pitcher_type_bl.iter_rows(named=True):
        pt = bl_row["pitch_type"]
        if pt not in game_pitch_types and float(bl_row["usage_pct"]) >= _DROPPED_PITCH_SEASON_MIN:
            signals.append(
                Signal(
                    "dropped_pitch",
                    _WEIGHTS["dropped_pitch"],
                    f"{pt} dropped (was {float(bl_row['usage_pct']):.1f}% of season mix)",
                )
            )

    return signals


def _check_pplus_lplus_split(app_row: dict) -> list[Signal]:
    """Check for high P+ paired with low L+ at the appearance level."""
    game_pplus = app_row.get("P+")
    game_lplus = app_row.get("L+")
    if game_pplus is None or game_lplus is None:
        return []

    if float(game_pplus) >= _PPLUS_GOOD and float(game_lplus) < 85:
        return [
            Signal(
                "pplus_lplus_split",
                _WEIGHTS["pplus_lplus_split"],
                f"P+ {float(game_pplus):.0f} but L+ only {float(game_lplus):.0f} (P+/L+ split)",
            )
        ]
    return []


def _check_splus_lplus_level_gap(game_types: pl.DataFrame) -> list[Signal]:
    """Check for sufficiently sampled pitches with high S+ and low L+."""
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
            signals.append(
                Signal(
                    "splus_lplus_level_gap",
                    _WEIGHTS["splus_lplus_level_gap"],
                    f"{pt}: S+ {float(game_s):.0f} / L+ {float(game_l):.0f} (grade divergence)",
                )
            )
    return signals


def _check_location_grade_surge(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
) -> list[Signal]:
    """Check for a pitch whose Location+ moved from a weak season to a strong outing.

    Location+ is a realized-location model contrast, not target, intent, command,
    or execution evidence. The signal reports only the grade comparison.
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

        if float(season_l) < _LOCATION_BASELINE_MAX and float(game_l) >= _LOCATION_OUTING_MIN:
            signals.append(
                Signal(
                    "location_grade_surge",
                    _WEIGHTS["location_grade_surge"],
                    f"{pt}: Location+ {float(season_l):.0f} → {float(game_l):.0f}",
                )
            )
    return signals
