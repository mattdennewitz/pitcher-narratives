"""Arsenal analysis: fastball summary, velocity arc, per-pitch-type
breakdowns, year-over-year arsenal trends, platoon mix, and first-pitch
weaponry.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _COLD_START_STRING,
    _FEET_TO_INCHES,
    _MIN_PITCHES,
    _PPLUS_METRICS,
    _build_name_map,
    _compute_platoon_baseline,
    _float,
    _get_window_game_dates,
    _identify_primary_fastball,
    _is_cold_start,
    _movement_delta_string,
    _pplus_delta_string,
    _pplus_delta_strings,
    _safe_metric,
    _usage_delta_string,
    _velo_delta_string,
    _weighted_window_metrics,
    _window_date_type_filter,
)


@dataclass
class FastballSummary:
    """Pre-computed fastball quality analysis ready for LLM."""

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    season_velo: float
    window_velo: float
    velo_delta: str
    """E.g., 'Down 1.2 mph'."""

    season_p_plus: float
    window_p_plus: float | None
    p_plus_delta: str

    season_s_plus: float
    window_s_plus: float | None
    s_plus_delta: str

    season_l_plus: float
    window_l_plus: float | None
    l_plus_delta: str

    season_pfx_x: float
    window_pfx_x: float
    pfx_x_delta: str

    season_pfx_z: float
    window_pfx_z: float
    pfx_z_delta: str

    velo_delta_mph: float
    """Raw velocity delta (window - season) in mph. Negative = velocity dropped."""

    p_plus_delta_pts: float | None
    """Raw P+ delta (window - season) in points. None when window P+ is unavailable."""

    small_sample: bool
    """True when fewer than _MIN_PITCHES fastballs in window."""

    cold_start: bool
    """True when window covers the full season."""


@dataclass
class VelocityArc:
    """Within-game velocity progression for most recent appearance."""

    game_pk: int
    game_date: str
    """ISO date string."""

    available: bool
    early_velo: float | None
    late_velo: float | None
    drop: float | None
    """late - early (negative = velocity dropped)."""

    drop_string: str
    """E.g., 'Dropped 1.3 mph' or 'Single inning -- no velocity arc available'."""

    innings_pitched: int


@dataclass
class PitchTypeSummary:
    """Per-pitch-type arsenal breakdown ready for LLM."""

    pitch_type: str
    """Pitch type code, e.g., 'FC'."""

    pitch_name: str
    """Human-readable name, e.g., 'Cutter'."""

    season_usage_pct: float
    """Season usage as percentage, e.g., 44.5."""

    window_usage_pct: float
    """Window usage as percentage."""

    usage_delta: str
    """Qualitative usage delta, e.g., 'Up 3.2 pp'."""

    season_p_plus: float
    window_p_plus: float | None
    p_plus_delta: str

    season_s_plus: float
    window_s_plus: float | None
    s_plus_delta: str

    season_l_plus: float
    window_l_plus: float | None
    l_plus_delta: str

    season_velo: float
    """Season average velocity (mph)."""
    window_velo: float
    """Window average velocity (mph)."""
    velo_delta: str
    """Qualitative velocity delta, e.g., 'Up 1.5 mph'."""

    season_pfx_x: float
    """Season average horizontal movement (inches)."""
    window_pfx_x: float
    """Window average horizontal movement (inches)."""
    pfx_x_delta: str

    season_pfx_z: float
    """Season average vertical movement (inches)."""
    window_pfx_z: float
    """Window average vertical movement (inches)."""
    pfx_z_delta: str

    n_pitches_season: int
    n_pitches_window: int
    small_sample: bool
    """True when fewer than _MIN_PITCHES of this type in window."""

    cold_start: bool
    """True when window covers the full season."""

    usage_delta_pp: float
    """Raw usage delta (window - season) in percentage points."""

    s_plus_delta_pts: float | None
    """Raw S+ delta (window - season) in points. None when window S+ is unavailable."""

    l_plus_delta_pts: float | None
    """Raw L+ delta (window - season) in points. None when window L+ is unavailable."""


@dataclass
class ArsenalPitchTrend:
    """Year-over-year trend for a single pitch type."""

    pitch_type: str
    """Pitch type code, e.g., 'SL'."""

    pitch_name: str
    """Human-readable name, e.g., 'Slider'."""

    status: str
    """One of 'added', 'dropped', or 'continued'."""

    prior_season: int | None
    """Prior season year, e.g., 2025."""

    current_season: int | None
    """Current season year, e.g., 2026."""

    # Usage
    prior_usage_pct: float | None
    """Usage percentage in prior season."""

    current_usage_pct: float | None
    """Usage percentage in current season."""

    usage_delta: str | None
    """Qualitative usage delta string, e.g., 'Up 7.0 pp'."""

    # P+/S+/L+
    prior_p_plus: float | None
    current_p_plus: float | None
    p_plus_delta: str | None

    prior_s_plus: float | None
    current_s_plus: float | None
    s_plus_delta: str | None

    prior_l_plus: float | None
    current_l_plus: float | None
    l_plus_delta: str | None

    # Velocity
    prior_velo: float | None
    current_velo: float | None
    velo_delta: str | None

    n_pitches_prior: int | None
    """Pitch count in prior season."""

    n_pitches_current: int | None
    """Pitch count in current season."""


@dataclass
class ArsenalTrends:
    """Container for all year-over-year arsenal changes."""

    added: list[ArsenalPitchTrend]
    """Pitches present in current season but absent in prior."""

    dropped: list[ArsenalPitchTrend]
    """Pitches present in prior season but absent in current."""

    continued: list[ArsenalPitchTrend]
    """Pitches present in both seasons, with YoY deltas."""

    prior_season: int
    """Prior season year."""

    current_season: int
    """Current season year."""

    @property
    def has_changes(self) -> bool:
        """True when at least one pitch was added, dropped, or changed."""
        return bool(self.added or self.dropped or self.continued)


@dataclass
class PlatoonSplit:
    """Usage breakdown for one pitch type against one platoon side."""

    pitch_type: str
    pitch_name: str
    platoon_side: str
    """'same' or 'opposite'."""

    season_usage_pct: float
    window_usage_pct: float | None
    usage_delta: str

    season_p_plus: float | None
    window_p_plus: float | None
    p_plus_delta: str

    available: bool
    """False if pitch not thrown to this side."""


@dataclass
class PlatoonMix:
    """Platoon mix shift analysis ready for LLM."""

    splits: list[PlatoonSplit]
    cold_start: bool


@dataclass
class FirstPitchEntry:
    """First-pitch usage for one pitch type."""

    pitch_type: str
    pitch_name: str
    season_pct: float
    window_pct: float
    delta: str
    n_first_pitches_season: int
    n_first_pitches_window: int


@dataclass
class FirstPitchWeaponry:
    """First-pitch strike weaponry analysis ready for LLM."""

    entries: list[FirstPitchEntry]
    """Ordered by window_pct descending."""

    total_first_pitches_season: int
    total_first_pitches_window: int
    cold_start: bool


def compute_fastball_summary(data: PitcherData) -> FastballSummary | None:
    """Compute fastball quality analysis with deltas and trend strings.

    Identifies the primary fastball type, computes season vs. window
    deltas for velocity, P+/S+/L+, and movement, and flags cold start
    and small sample conditions.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        FastballSummary dataclass or None if pitcher has no fastball types.
    """
    # Identify primary fastball
    primary = _identify_primary_fastball(data.pitch_type_baseline)
    if primary is None:
        return None

    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    # Filter statcast to primary fastball type
    fb_statcast = data.statcast.filter(pl.col("pitch_type") == primary)

    # ── Velocity ──────────────────────────────────────────────────
    season_velo = _float(fb_statcast["release_speed"].mean())
    window_fb = fb_statcast.filter(pl.col("game_date").is_in(window_dates))
    window_velo = _float(window_fb["release_speed"].mean())
    velo_delta = window_velo - season_velo

    velo_delta_str = _COLD_START_STRING if cold_start else _velo_delta_string(velo_delta)

    # ── Small sample ──────────────────────────────────────────────
    small_sample = len(window_fb) < _MIN_PITCHES

    # ── P+/S+/L+ ─────────────────────────────────────────────────
    # Season values from pitch_type_baseline
    pt_baseline = data.pitch_type_baseline.filter(pl.col("pitch_type") == primary)
    season_p_plus = _safe_metric(pt_baseline, "P+")
    season_s_plus = _safe_metric(pt_baseline, "S+")
    season_l_plus = _safe_metric(pt_baseline, "L+")

    # Window values from pitcher_type_appearance CSV
    window_pplus = _weighted_window_metrics(
        data.agg_csvs["pitcher_type_appearance"],
        _PPLUS_METRICS,
        _window_date_type_filter(window_dates, primary),
    )

    window_p_plus = window_pplus["P+"]
    window_s_plus = window_pplus["S+"]
    window_l_plus = window_pplus["L+"]

    p_plus_delta_str, s_plus_delta_str, l_plus_delta_str = _pplus_delta_strings(
        cold_start,
        season_p_plus,
        season_s_plus,
        season_l_plus,
        window_p_plus,
        window_s_plus,
        window_l_plus,
    )

    # ── Movement ──────────────────────────────────────────────────
    season_pfx_x = _float(fb_statcast["pfx_x"].mean()) * _FEET_TO_INCHES
    season_pfx_z = _float(fb_statcast["pfx_z"].mean()) * _FEET_TO_INCHES
    window_pfx_x = _float(window_fb["pfx_x"].mean()) * _FEET_TO_INCHES
    window_pfx_z = _float(window_fb["pfx_z"].mean()) * _FEET_TO_INCHES

    if cold_start:
        pfx_x_delta_str = _COLD_START_STRING
        pfx_z_delta_str = _COLD_START_STRING
    else:
        pfx_x_delta_str = _movement_delta_string(window_pfx_x - season_pfx_x)
        pfx_z_delta_str = _movement_delta_string(window_pfx_z - season_pfx_z)

    # ── Pitch name ────────────────────────────────────────────────
    name_rows = fb_statcast.select("pitch_name").unique()
    pitch_name = str(name_rows["pitch_name"][0]) if not name_rows.is_empty() else primary

    p_plus_delta_pts = (
        window_p_plus - season_p_plus
        if window_p_plus is not None
        else None
    )

    return FastballSummary(
        pitch_type=primary,
        pitch_name=pitch_name,
        season_velo=season_velo,
        window_velo=window_velo,
        velo_delta=velo_delta_str,
        velo_delta_mph=velo_delta,
        season_p_plus=season_p_plus,
        window_p_plus=window_p_plus,
        p_plus_delta=p_plus_delta_str,
        p_plus_delta_pts=p_plus_delta_pts,
        season_s_plus=season_s_plus,
        window_s_plus=window_s_plus,
        s_plus_delta=s_plus_delta_str,
        season_l_plus=season_l_plus,
        window_l_plus=window_l_plus,
        l_plus_delta=l_plus_delta_str,
        season_pfx_x=season_pfx_x,
        window_pfx_x=window_pfx_x,
        pfx_x_delta=pfx_x_delta_str,
        season_pfx_z=season_pfx_z,
        window_pfx_z=window_pfx_z,
        pfx_z_delta=pfx_z_delta_str,
        small_sample=small_sample,
        cold_start=cold_start,
    )


def compute_velocity_arc(data: PitcherData, fastball_type: str) -> VelocityArc:
    """Compute within-game velocity progression for most recent appearance.

    Compares average fastball velocity in the first two innings vs. the last
    two innings of the most recent appearance. Returns a fallback message
    for single-inning outings.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.
        fastball_type: Pitch type code for the primary fastball (e.g., 'FC').

    Returns:
        VelocityArc dataclass with early/late velocity and drop string.
    """
    # Find most recent appearance
    recent = data.appearances.sort("game_date", descending=True).row(0, named=True)
    game_pk = int(recent["game_pk"])
    game_date = str(recent["game_date"])

    # Filter statcast to that game and fastball type
    game_fb = data.statcast.filter((pl.col("game_pk") == game_pk) & (pl.col("pitch_type") == fastball_type))

    innings = sorted(game_fb["inning"].unique().to_list())
    innings_pitched = len(innings)

    if innings_pitched < 2:
        return VelocityArc(
            game_pk=game_pk,
            game_date=game_date,
            available=False,
            early_velo=None,
            late_velo=None,
            drop=None,
            drop_string="Single inning -- no velocity arc available",
            innings_pitched=innings_pitched,
        )

    # First 2 and last 2 innings (may overlap if 2-3 innings total)
    early_innings = innings[:2]
    late_innings = innings[-2:]

    early_velo = _float(game_fb.filter(pl.col("inning").is_in(early_innings))["release_speed"].mean())
    late_velo = _float(game_fb.filter(pl.col("inning").is_in(late_innings))["release_speed"].mean())
    drop = late_velo - early_velo

    if abs(drop) < 0.5:
        drop_string = "Held steady"
    elif drop < 0:
        drop_string = f"Dropped {abs(drop):.1f} mph"
    else:
        drop_string = f"Gained {drop:.1f} mph"

    return VelocityArc(
        game_pk=game_pk,
        game_date=game_date,
        available=True,
        early_velo=early_velo,
        late_velo=late_velo,
        drop=drop,
        drop_string=drop_string,
        innings_pitched=innings_pitched,
    )


def compute_arsenal_summary(data: PitcherData) -> list[PitchTypeSummary]:
    """Compute per-pitch-type arsenal breakdown with usage and P+ deltas.

    Builds a PitchTypeSummary for every pitch type the pitcher throws,
    sorted by season usage descending. Each entry includes usage rates,
    P+/S+/L+ season vs window deltas, small sample flags, and cold start
    detection.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        List of PitchTypeSummary dataclasses ordered by season_usage_pct
        descending.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    # Get all pitch types from baseline sorted by n_pitches descending
    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    name_map = _build_name_map(data.statcast)

    # Total pitch counts
    total_season = len(data.statcast)
    window_statcast = data.statcast.filter(pl.col("game_date").is_in(window_dates))
    total_window = len(window_statcast)

    single_type = len(pitch_types) == 1

    results: list[PitchTypeSummary] = []
    for pt in pitch_types:
        # ── Usage rates ──────────────────────────────────────────
        pt_season = data.statcast.filter(pl.col("pitch_type") == pt)
        n_season = len(pt_season)
        season_usage_pct = n_season / total_season * 100.0

        pt_window = window_statcast.filter(pl.col("pitch_type") == pt)
        n_window = len(pt_window)
        window_usage_pct = n_window / total_window * 100.0 if total_window > 0 else 0.0

        # ── Usage delta ──────────────────────────────────────────
        if cold_start:
            usage_delta = _COLD_START_STRING
        elif single_type:
            usage_delta = "Only pitch type"
        else:
            usage_delta = _usage_delta_string(window_usage_pct - season_usage_pct)

        # ── P+/S+/L+ ────────────────────────────────────────────
        pt_baseline_row = baseline.filter(pl.col("pitch_type") == pt)
        season_p_plus = _safe_metric(pt_baseline_row, "P+")
        season_s_plus = _safe_metric(pt_baseline_row, "S+")
        season_l_plus = _safe_metric(pt_baseline_row, "L+")

        window_pplus = _weighted_window_metrics(
            data.agg_csvs["pitcher_type_appearance"],
            _PPLUS_METRICS,
            _window_date_type_filter(window_dates, pt),
        )
        window_p_plus = window_pplus["P+"]
        window_s_plus = window_pplus["S+"]
        window_l_plus = window_pplus["L+"]

        p_plus_delta, s_plus_delta, l_plus_delta = _pplus_delta_strings(
            cold_start,
            season_p_plus,
            season_s_plus,
            season_l_plus,
            window_p_plus,
            window_s_plus,
            window_l_plus,
        )

        # ── Pitch name ───────────────────────────────────────────
        pitch_name = name_map.get(pt, pt)

        # ── Velocity & movement ──────────────────────────────────
        season_velo = _float(pt_season["release_speed"].mean())
        window_velo = _float(pt_window["release_speed"].mean()) if n_window > 0 else season_velo

        season_pfx_x = _float(pt_season["pfx_x"].mean()) * _FEET_TO_INCHES
        window_pfx_x = _float(pt_window["pfx_x"].mean()) * _FEET_TO_INCHES if n_window > 0 else season_pfx_x
        season_pfx_z = _float(pt_season["pfx_z"].mean()) * _FEET_TO_INCHES
        window_pfx_z = _float(pt_window["pfx_z"].mean()) * _FEET_TO_INCHES if n_window > 0 else season_pfx_z

        if cold_start:
            velo_delta_str = _COLD_START_STRING
            pfx_x_delta_str = _COLD_START_STRING
            pfx_z_delta_str = _COLD_START_STRING
        else:
            velo_delta_str = _velo_delta_string(window_velo - season_velo)
            pfx_x_delta_str = _movement_delta_string(window_pfx_x - season_pfx_x)
            pfx_z_delta_str = _movement_delta_string(window_pfx_z - season_pfx_z)

        # ── Small sample ─────────────────────────────────────────
        small_sample = n_window < _MIN_PITCHES

        usage_delta_pp = window_usage_pct - season_usage_pct
        s_plus_delta_pts = (
            window_s_plus - season_s_plus if window_s_plus is not None else None
        )
        l_plus_delta_pts = (
            window_l_plus - season_l_plus if window_l_plus is not None else None
        )

        results.append(
            PitchTypeSummary(
                pitch_type=pt,
                pitch_name=pitch_name,
                season_usage_pct=season_usage_pct,
                window_usage_pct=window_usage_pct,
                usage_delta=usage_delta,
                season_p_plus=season_p_plus,
                window_p_plus=window_p_plus,
                p_plus_delta=p_plus_delta,
                season_s_plus=season_s_plus,
                window_s_plus=window_s_plus,
                s_plus_delta=s_plus_delta,
                season_l_plus=season_l_plus,
                window_l_plus=window_l_plus,
                l_plus_delta=l_plus_delta,
                season_velo=season_velo,
                window_velo=window_velo,
                velo_delta=velo_delta_str,
                season_pfx_x=season_pfx_x,
                window_pfx_x=window_pfx_x,
                pfx_x_delta=pfx_x_delta_str,
                season_pfx_z=season_pfx_z,
                window_pfx_z=window_pfx_z,
                pfx_z_delta=pfx_z_delta_str,
                n_pitches_season=n_season,
                n_pitches_window=n_window,
                small_sample=small_sample,
                cold_start=cold_start,
                usage_delta_pp=usage_delta_pp,
                s_plus_delta_pts=s_plus_delta_pts,
                l_plus_delta_pts=l_plus_delta_pts,
            )
        )

    # Sort by season usage descending
    results.sort(key=lambda x: x.season_usage_pct, reverse=True)
    return results


def compute_arsenal_trends(data: PitcherData) -> ArsenalTrends | None:
    """Compute year-over-year per-pitch-type arsenal changes.

    Identifies pitches added (present in current season, absent in prior),
    dropped (present in prior, absent in current), and continued (present
    in both with YoY deltas for usage, P+/S+/L+, and velocity).

    Uses ``compute_pitch_type_baseline()`` on the pitcher_type aggregation
    CSV to build per-season pitch-type baselines, then compares the two
    most recent seasons.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        ArsenalTrends container, or None when the pitcher has only one
        season of data.
    """
    current_df = data.pitch_type_baseline
    prior_df = data.prior_pitch_type_baseline

    if prior_df.is_empty():
        return None

    if "season" not in current_df.columns or current_df.is_empty():
        return None

    current_season = int(current_df["season"].max())
    prior_season = int(prior_df["season"].max())

    current_types = set(current_df["pitch_type"].to_list())
    prior_types = set(prior_df["pitch_type"].to_list())

    # Filter out types below minimum pitch threshold
    current_types = {
        pt
        for pt in current_types
        if int(current_df.filter(pl.col("pitch_type") == pt)["n_pitches"][0]) >= _MIN_PITCHES
    }
    prior_types = {
        pt
        for pt in prior_types
        if int(prior_df.filter(pl.col("pitch_type") == pt)["n_pitches"][0]) >= _MIN_PITCHES
    }

    name_map = _build_name_map(data.statcast)

    added_types = current_types - prior_types
    dropped_types = prior_types - current_types
    continued_types = current_types & prior_types

    added: list[ArsenalPitchTrend] = []
    for pt in sorted(added_types):
        row = current_df.filter(pl.col("pitch_type") == pt)
        added.append(
            ArsenalPitchTrend(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                status="added",
                prior_season=int(prior_season),
                current_season=int(current_season),
                prior_usage_pct=None,
                current_usage_pct=_safe_metric(row, "usage_pct"),
                usage_delta=None,
                prior_p_plus=None,
                current_p_plus=_safe_metric(row, "P+"),
                p_plus_delta=None,
                prior_s_plus=None,
                current_s_plus=_safe_metric(row, "S+"),
                s_plus_delta=None,
                prior_l_plus=None,
                current_l_plus=_safe_metric(row, "L+"),
                l_plus_delta=None,
                prior_velo=None,
                current_velo=None,
                velo_delta=None,
                n_pitches_prior=None,
                n_pitches_current=int(row["n_pitches"][0]),
            )
        )

    dropped: list[ArsenalPitchTrend] = []
    for pt in sorted(dropped_types):
        row = prior_df.filter(pl.col("pitch_type") == pt)
        dropped.append(
            ArsenalPitchTrend(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                status="dropped",
                prior_season=int(prior_season),
                current_season=int(current_season),
                prior_usage_pct=_safe_metric(row, "usage_pct"),
                current_usage_pct=None,
                usage_delta=None,
                prior_p_plus=_safe_metric(row, "P+"),
                current_p_plus=None,
                p_plus_delta=None,
                prior_s_plus=_safe_metric(row, "S+"),
                current_s_plus=None,
                s_plus_delta=None,
                prior_l_plus=_safe_metric(row, "L+"),
                current_l_plus=None,
                l_plus_delta=None,
                prior_velo=None,
                current_velo=None,
                velo_delta=None,
                n_pitches_prior=int(row["n_pitches"][0]),
                n_pitches_current=None,
            )
        )

    continued: list[ArsenalPitchTrend] = []
    for pt in sorted(continued_types):
        curr_row = current_df.filter(pl.col("pitch_type") == pt)
        prior_row = prior_df.filter(pl.col("pitch_type") == pt)

        curr_usage = _safe_metric(curr_row, "usage_pct")
        prior_usage = _safe_metric(prior_row, "usage_pct")

        curr_p = _safe_metric(curr_row, "P+")
        prior_p = _safe_metric(prior_row, "P+")

        curr_s = _safe_metric(curr_row, "S+")
        prior_s = _safe_metric(prior_row, "S+")

        curr_l = _safe_metric(curr_row, "L+")
        prior_l = _safe_metric(prior_row, "L+")

        # Velocity from statcast (more accurate than CSV aggregations)
        curr_statcast = data.statcast.filter(
            (pl.col("pitch_type") == pt) & (pl.col("game_date").dt.year() == current_season)
        )
        prior_statcast = data.statcast.filter(
            (pl.col("pitch_type") == pt) & (pl.col("game_date").dt.year() == prior_season)
        )
        curr_velo = (
            _float(curr_statcast["release_speed"].mean())
            if not curr_statcast.is_empty()
            else None
        )
        prior_velo = (
            _float(prior_statcast["release_speed"].mean())
            if not prior_statcast.is_empty()
            else None
        )
        velo_delta_str = (
            _velo_delta_string(curr_velo - prior_velo)
            if curr_velo is not None and prior_velo is not None
            else None
        )

        continued.append(
            ArsenalPitchTrend(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                status="continued",
                prior_season=int(prior_season),
                current_season=int(current_season),
                prior_usage_pct=prior_usage,
                current_usage_pct=curr_usage,
                usage_delta=_usage_delta_string(curr_usage - prior_usage),
                prior_p_plus=prior_p,
                current_p_plus=curr_p,
                p_plus_delta=_pplus_delta_string(curr_p - prior_p),
                prior_s_plus=prior_s,
                current_s_plus=curr_s,
                s_plus_delta=_pplus_delta_string(curr_s - prior_s),
                prior_l_plus=prior_l,
                current_l_plus=curr_l,
                l_plus_delta=_pplus_delta_string(curr_l - prior_l),
                prior_velo=prior_velo,
                current_velo=curr_velo,
                velo_delta=velo_delta_str,
                n_pitches_prior=int(prior_row["n_pitches"][0]),
                n_pitches_current=int(curr_row["n_pitches"][0]),
            )
        )

    # Sort continued by current usage descending
    continued.sort(key=lambda x: x.current_usage_pct or 0, reverse=True)

    return ArsenalTrends(
        added=added,
        dropped=dropped,
        continued=continued,
        prior_season=int(prior_season),
        current_season=int(current_season),
    )


def compute_platoon_mix(data: PitcherData) -> PlatoonMix:
    """Compute platoon mix shift analysis with per-type per-side splits.

    For each pitch type and each platoon side (same/opposite), computes
    usage rates and P+ deltas. Handles missing combinations (e.g., a
    changeup only thrown to opposite-side batters).

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        PlatoonMix dataclass with list of PlatoonSplit entries.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    name_map = _build_name_map(data.statcast)

    # Add platoon_matchup column to statcast
    statcast_with_platoon = data.statcast.with_columns(
        pl.when(pl.col("stand") == pl.col("p_throws"))
        .then(pl.lit("same"))
        .otherwise(pl.lit("opposite"))
        .alias("platoon_matchup")
    )
    window_sc = statcast_with_platoon.filter(pl.col("game_date").is_in(window_dates))

    # Compute platoon baseline from season CSV
    platoon_baseline = _compute_platoon_baseline(data.agg_csvs["pitcher_type_platoon"])

    # Get pitch types ordered by usage
    baseline = data.pitch_type_baseline.sort("n_pitches", descending=True)
    pitch_types = baseline["pitch_type"].to_list()

    splits: list[PlatoonSplit] = []

    for pt in pitch_types:
        for side in ("same", "opposite"):
            # ── Season usage: % of pitches to this side that are this type ──
            season_side = statcast_with_platoon.filter(pl.col("platoon_matchup") == side)
            season_side_total = len(season_side)
            season_side_type = season_side.filter(pl.col("pitch_type") == pt)
            n_season_side_type = len(season_side_type)

            if n_season_side_type == 0:
                # Pitch not thrown to this side at all
                splits.append(
                    PlatoonSplit(
                        pitch_type=pt,
                        pitch_name=name_map.get(pt, pt),
                        platoon_side=side,
                        season_usage_pct=0.0,
                        window_usage_pct=None,
                        usage_delta=f"Not thrown to {side}-side batters",
                        season_p_plus=None,
                        window_p_plus=None,
                        p_plus_delta=f"Not thrown to {side}-side batters",
                        available=False,
                    )
                )
                continue

            season_usage_pct = n_season_side_type / season_side_total * 100.0

            # ── Window usage ──
            window_side = window_sc.filter(pl.col("platoon_matchup") == side)
            window_side_total = len(window_side)
            window_side_type = window_side.filter(pl.col("pitch_type") == pt)
            n_window_side_type = len(window_side_type)

            if window_side_total > 0:
                window_usage_pct = n_window_side_type / window_side_total * 100.0
            else:
                window_usage_pct = None

            # ── Usage delta ──
            if cold_start:
                usage_delta = _COLD_START_STRING
            elif window_usage_pct is not None:
                usage_delta = _usage_delta_string(window_usage_pct - season_usage_pct)
            else:
                usage_delta = "No window data"

            # ── Season P+ from platoon baseline ──
            plat_row = platoon_baseline.filter(
                (pl.col("pitch_type") == pt) & (pl.col("platoon_matchup") == side)
            )
            season_p_plus: float | None = None
            if not plat_row.is_empty() and "P+" in plat_row.columns:
                season_p_plus = float(plat_row["P+"][0])

            # ── Window P+ from platoon appearance data ──
            window_plat_pplus = _weighted_window_metrics(
                data.agg_csvs["pitcher_type_platoon_appearance"],
                _PPLUS_METRICS,
                _window_date_type_filter(window_dates, pt) & (pl.col("platoon_matchup") == side),
            )
            window_p_plus = window_plat_pplus["P+"]

            # ── P+ delta ──
            if cold_start:
                p_plus_delta = _COLD_START_STRING
            elif season_p_plus is not None and window_p_plus is not None:
                p_plus_delta = _pplus_delta_string(window_p_plus - season_p_plus)
            else:
                p_plus_delta = "No window data"

            splits.append(
                PlatoonSplit(
                    pitch_type=pt,
                    pitch_name=name_map.get(pt, pt),
                    platoon_side=side,
                    season_usage_pct=season_usage_pct,
                    window_usage_pct=window_usage_pct,
                    usage_delta=usage_delta,
                    season_p_plus=season_p_plus,
                    window_p_plus=window_p_plus,
                    p_plus_delta=p_plus_delta,
                    available=True,
                )
            )

    return PlatoonMix(splits=splits, cold_start=cold_start)


def compute_first_pitch_weaponry(data: PitcherData) -> FirstPitchWeaponry:
    """Compute first-pitch strike weaponry analysis.

    Filters statcast to pitch_number == 1 (first pitch of each at-bat),
    computes per-type distribution for season vs window, and produces
    delta strings.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        FirstPitchWeaponry dataclass with entries ordered by window_pct
        descending.
    """
    window_dates = _get_window_game_dates(data)
    cold_start = _is_cold_start(data)

    name_map = _build_name_map(data.statcast)

    # Filter to first pitches
    first_pitches = data.statcast.filter(pl.col("pitch_number") == 1)
    total_season = len(first_pitches)

    # Window first pitches
    fp_window = first_pitches.filter(pl.col("game_date").is_in(window_dates))
    total_window = len(fp_window)

    # Season counts by type
    season_counts = first_pitches["pitch_type"].value_counts().sort("pitch_type")

    # Window counts by type
    window_counts = fp_window["pitch_type"].value_counts().sort("pitch_type")
    window_count_map: dict[str, int] = {}
    for row in window_counts.iter_rows(named=True):
        window_count_map[row["pitch_type"]] = row["count"]

    entries: list[FirstPitchEntry] = []
    for row in season_counts.iter_rows(named=True):
        pt = row["pitch_type"]
        n_season = row["count"]
        season_pct = n_season / total_season * 100.0

        n_window = window_count_map.get(pt, 0)
        window_pct = n_window / total_window * 100.0 if total_window > 0 else 0.0

        delta = _COLD_START_STRING if cold_start else _usage_delta_string(window_pct - season_pct)

        entries.append(
            FirstPitchEntry(
                pitch_type=pt,
                pitch_name=name_map.get(pt, pt),
                season_pct=season_pct,
                window_pct=window_pct,
                delta=delta,
                n_first_pitches_season=n_season,
                n_first_pitches_window=n_window,
            )
        )

    # Sort by window_pct descending
    entries.sort(key=lambda x: x.window_pct, reverse=True)

    return FirstPitchWeaponry(
        entries=entries,
        total_first_pitches_season=total_season,
        total_first_pitches_window=total_window,
        cold_start=cold_start,
    )


