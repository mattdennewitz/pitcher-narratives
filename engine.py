"""Computation engine for pitcher narratives.

Transforms PitcherData into pre-computed analysis with qualitative trend
strings ready for LLM consumption. Computes fastball quality deltas
(velocity, P+/S+/L+, movement), within-game velocity arcs, and shared
delta helpers used across all analysis facets.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from data import PitcherData

__all__ = [
    "compute_fastball_summary",
    "compute_velocity_arc",
    "compute_arsenal_summary",
    "compute_platoon_mix",
    "compute_first_pitch_weaponry",
    "FastballSummary",
    "VelocityArc",
    "PitchTypeSummary",
    "PlatoonMix",
    "PlatoonSplit",
    "FirstPitchEntry",
    "FirstPitchWeaponry",
]

# ── Constants ─────────────────────────────────────────────────────────

_FASTBALL_TYPES = frozenset({"FF", "SI", "FC"})
"""Standard Statcast fastball classification codes."""

_VELO_THRESHOLD = 0.5
"""MPH below which velocity delta is 'Steady' (noise floor)."""

_PPLUS_THRESHOLD = 5
"""Points below which P+/S+/L+ delta is 'Steady'."""

_SHARP_VELO_THRESHOLD = 2.0
"""MPH above which velocity delta is 'sharply'."""

_SHARP_PPLUS_THRESHOLD = 10
"""Points above which P+/S+/L+ delta is 'sharply'."""

_USAGE_THRESHOLD = 5.0
"""Percentage points below which usage delta is 'Steady'."""

_MOVEMENT_THRESHOLD = 0.5
"""Inches below which movement delta is 'Steady'."""

_MIN_PITCHES = 10
"""Minimum pitches for per-type analysis; below this flag small_sample=True."""

_COLD_START_STRING = "Full season in window -- no trend comparison"
"""Delta string used when window covers entire season."""


# ── Delta string helpers (private) ────────────────────────────────────


def _velo_delta_string(delta: float, threshold: float = _VELO_THRESHOLD) -> str:
    """Convert velocity delta to qualitative string.

    Args:
        delta: window_value - season_value (positive = faster).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 1.5 mph', 'Down sharply (-2.5 mph)',
        or 'Steady (+0.3)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f})"
    direction = "Up" if delta > 0 else "Down"
    if abs(delta) >= _SHARP_VELO_THRESHOLD:
        return f"{direction} sharply ({delta:+.1f} mph)"
    return f"{direction} {abs(delta):.1f} mph"


def _pplus_delta_string(delta: float, threshold: float = _PPLUS_THRESHOLD) -> str:
    """Convert P+/S+/L+ delta to qualitative string.

    Args:
        delta: window_value - season_value (positive = improved).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 8 points', 'Down sharply (-15 points)',
        or 'Steady (+3)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.0f})"
    direction = "Up" if delta > 0 else "Down"
    if abs(delta) >= _SHARP_PPLUS_THRESHOLD:
        return f"{direction} sharply ({delta:+.0f} points)"
    return f"{direction} {abs(delta):.0f} points"


def _usage_delta_string(delta: float, threshold: float = _USAGE_THRESHOLD) -> str:
    """Convert usage rate delta (percentage points) to qualitative string.

    Args:
        delta: window_pct - season_pct (positive = more usage).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up sharply (+12.0 pp)', 'Up 7.0 pp',
        or 'Steady (+2.0 pp)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f} pp)"
    direction = "Up" if delta > 0 else "Down"
    if abs(delta) >= 10.0:
        return f"{direction} sharply ({delta:+.1f} pp)"
    return f"{direction} {abs(delta):.1f} pp"


def _movement_delta_string(delta: float, threshold: float = _MOVEMENT_THRESHOLD) -> str:
    """Convert movement delta (inches) to qualitative string.

    Args:
        delta: window_value - season_value (positive = more movement).
        threshold: Below this magnitude, report as 'Steady'.

    Returns:
        Qualitative string like 'Up 1.5 in' or 'Steady (+0.2 in)'.
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f} in)"
    direction = "Up" if delta > 0 else "Down"
    return f"{direction} {abs(delta):.1f} in"


# ── Internal helpers ──────────────────────────────────────────────────


def _identify_primary_fastball(pitch_type_baseline: pl.DataFrame) -> str | None:
    """Return the pitch_type code of the highest-usage fastball type.

    Filters pitch_type_baseline to rows where pitch_type is in
    _FASTBALL_TYPES, sorts by n_pitches descending, and returns the first.

    Args:
        pitch_type_baseline: Per-pitch-type weighted baselines from data.py.

    Returns:
        Pitch type code (e.g., 'FC') or None if no fastball types found.
    """
    fb_rows = pitch_type_baseline.filter(
        pl.col("pitch_type").is_in(list(_FASTBALL_TYPES))
    )
    if fb_rows.is_empty():
        return None
    return str(fb_rows.sort("n_pitches", descending=True)["pitch_type"][0])


def _get_window_game_dates(data: PitcherData) -> list:
    """Extract unique game_date values from window_appearances.

    Args:
        data: PitcherData bundle.

    Returns:
        List of game dates within the lookback window.
    """
    return data.window_appearances["game_date"].unique().to_list()


def _is_cold_start(data: PitcherData) -> bool:
    """Check if window covers the full season (cold start).

    Args:
        data: PitcherData bundle.

    Returns:
        True when window_appearances covers all appearances.
    """
    return len(data.window_appearances) >= len(data.appearances)


def _weighted_window_pplus(
    appearance_type_df: pl.DataFrame,
    window_dates: list,
    pitch_type: str,
) -> dict[str, float | int | None]:
    """Compute n_pitches-weighted P+/S+/L+ for a pitch type in window.

    Filters pitcher_type_appearance CSV to window_dates and pitch_type,
    then computes weighted averages.

    Args:
        appearance_type_df: The pitcher_type_appearance CSV DataFrame.
        window_dates: List of game dates in the window.
        pitch_type: Pitch type code to filter on.

    Returns:
        Dict with keys 'P+', 'S+', 'L+', 'n_pitches'. Values are None
        if no data found.
    """
    window = appearance_type_df.filter(
        (pl.col("game_date").is_in(window_dates))
        & (pl.col("pitch_type") == pitch_type)
    )

    if window.is_empty():
        return {"P+": None, "S+": None, "L+": None, "n_pitches": 0}

    total_pitches = window["n_pitches"].sum()
    if total_pitches == 0:
        return {"P+": None, "S+": None, "L+": None, "n_pitches": 0}

    result: dict[str, float | int | None] = {"n_pitches": int(total_pitches)}
    for metric in ("P+", "S+", "L+"):
        if metric in window.columns:
            weighted = (window[metric] * window["n_pitches"]).sum() / total_pitches
            result[metric] = float(weighted)
        else:
            result[metric] = None

    return result


def _stand_to_platoon(stand: str, p_throws: str) -> str:
    """Map batter handedness + pitcher handedness to platoon matchup label.

    Args:
        stand: Batter handedness ('L' or 'R').
        p_throws: Pitcher handedness ('L' or 'R').

    Returns:
        'same' if stand == p_throws, else 'opposite'.
    """
    return "same" if stand == p_throws else "opposite"


def _compute_platoon_baseline(pitcher_type_platoon_df: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted baseline per (pitch_type, platoon_matchup).

    Combines game_type rows using pitch-count weighting, same pattern as
    compute_pitch_type_baseline in data.py but grouped by platoon_matchup.

    Args:
        pitcher_type_platoon_df: The pitcher_type_platoon CSV DataFrame
            filtered to one pitcher.

    Returns:
        DataFrame with one row per (pitch_type, platoon_matchup) and
        weighted average metrics.
    """
    df = pitcher_type_platoon_df.filter(pl.col("pitch_type") != "")
    id_cols = frozenset({
        "season", "level", "game_type", "pitcher", "player_name",
        "p_throws", "team_code", "n_pitches", "pitch_type", "platoon_matchup",
    })
    metric_cols = [c for c in df.columns if c not in id_cols]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches"))
        .sum()
        .truediv(pl.col("n_pitches").sum())
        .alias(c)
        for c in metric_cols
    ]
    return df.group_by(["pitcher", "pitch_type", "platoon_matchup"]).agg(
        pl.col("n_pitches").sum(),
        *weighted_exprs,
    )


def _weighted_window_platoon_pplus(
    platoon_appearance_df: pl.DataFrame,
    window_dates: list,
    pitch_type: str,
    platoon_matchup: str,
) -> dict[str, float | int | None]:
    """Compute n_pitches-weighted P+/S+/L+ for a pitch type + platoon in window.

    Args:
        platoon_appearance_df: The pitcher_type_platoon_appearance CSV.
        window_dates: List of game dates in the window.
        pitch_type: Pitch type code to filter on.
        platoon_matchup: 'same' or 'opposite'.

    Returns:
        Dict with keys 'P+', 'S+', 'L+', 'n_pitches'.
    """
    window = platoon_appearance_df.filter(
        (pl.col("game_date").is_in(window_dates))
        & (pl.col("pitch_type") == pitch_type)
        & (pl.col("platoon_matchup") == platoon_matchup)
    )

    if window.is_empty():
        return {"P+": None, "S+": None, "L+": None, "n_pitches": 0}

    total_pitches = window["n_pitches"].sum()
    if total_pitches == 0:
        return {"P+": None, "S+": None, "L+": None, "n_pitches": 0}

    result: dict[str, float | int | None] = {"n_pitches": int(total_pitches)}
    for metric in ("P+", "S+", "L+"):
        if metric in window.columns:
            weighted = (window[metric] * window["n_pitches"]).sum() / total_pitches
            result[metric] = float(weighted)
        else:
            result[metric] = None

    return result


# ── Dataclasses ───────────────────────────────────────────────────────


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

    n_pitches_season: int
    n_pitches_window: int
    small_sample: bool
    """True when fewer than _MIN_PITCHES of this type in window."""

    cold_start: bool
    """True when window covers the full season."""


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


# ── Public API ────────────────────────────────────────────────────────


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
    season_velo = float(fb_statcast["release_speed"].mean())
    window_fb = fb_statcast.filter(pl.col("game_date").is_in(window_dates))
    window_velo = float(window_fb["release_speed"].mean())
    velo_delta = window_velo - season_velo

    if cold_start:
        velo_delta_str = _COLD_START_STRING
    else:
        velo_delta_str = _velo_delta_string(velo_delta)

    # ── Small sample ──────────────────────────────────────────────
    small_sample = len(window_fb) < _MIN_PITCHES

    # ── P+/S+/L+ ─────────────────────────────────────────────────
    # Season values from pitch_type_baseline
    pt_baseline = data.pitch_type_baseline.filter(
        pl.col("pitch_type") == primary
    )
    season_p_plus = float(pt_baseline["P+"][0]) if not pt_baseline.is_empty() and "P+" in pt_baseline.columns else 0.0
    season_s_plus = float(pt_baseline["S+"][0]) if not pt_baseline.is_empty() and "S+" in pt_baseline.columns else 0.0
    season_l_plus = float(pt_baseline["L+"][0]) if not pt_baseline.is_empty() and "L+" in pt_baseline.columns else 0.0

    # Window values from pitcher_type_appearance CSV
    window_pplus = _weighted_window_pplus(
        data.agg_csvs["pitcher_type_appearance"],
        window_dates,
        primary,
    )

    window_p_plus = window_pplus["P+"]
    window_s_plus = window_pplus["S+"]
    window_l_plus = window_pplus["L+"]

    if cold_start:
        p_plus_delta_str = _COLD_START_STRING
        s_plus_delta_str = _COLD_START_STRING
        l_plus_delta_str = _COLD_START_STRING
    elif window_p_plus is not None:
        p_plus_delta_str = _pplus_delta_string(window_p_plus - season_p_plus)
        s_plus_delta_str = _pplus_delta_string(window_s_plus - season_s_plus) if window_s_plus is not None else "No window data"
        l_plus_delta_str = _pplus_delta_string(window_l_plus - season_l_plus) if window_l_plus is not None else "No window data"
    else:
        p_plus_delta_str = "No window data"
        s_plus_delta_str = "No window data"
        l_plus_delta_str = "No window data"

    # ── Movement ──────────────────────────────────────────────────
    season_pfx_x = float(fb_statcast["pfx_x"].mean())
    season_pfx_z = float(fb_statcast["pfx_z"].mean())
    window_pfx_x = float(window_fb["pfx_x"].mean())
    window_pfx_z = float(window_fb["pfx_z"].mean())

    if cold_start:
        pfx_x_delta_str = _COLD_START_STRING
        pfx_z_delta_str = _COLD_START_STRING
    else:
        pfx_x_delta_str = _movement_delta_string(window_pfx_x - season_pfx_x)
        pfx_z_delta_str = _movement_delta_string(window_pfx_z - season_pfx_z)

    # ── Pitch name ────────────────────────────────────────────────
    name_rows = fb_statcast.select("pitch_name").unique()
    pitch_name = str(name_rows["pitch_name"][0]) if not name_rows.is_empty() else primary

    return FastballSummary(
        pitch_type=primary,
        pitch_name=pitch_name,
        season_velo=season_velo,
        window_velo=window_velo,
        velo_delta=velo_delta_str,
        season_p_plus=season_p_plus,
        window_p_plus=window_p_plus,
        p_plus_delta=p_plus_delta_str,
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
    game_fb = data.statcast.filter(
        (pl.col("game_pk") == game_pk)
        & (pl.col("pitch_type") == fastball_type)
    )

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

    early_velo = float(
        game_fb.filter(pl.col("inning").is_in(early_innings))["release_speed"].mean()
    )
    late_velo = float(
        game_fb.filter(pl.col("inning").is_in(late_innings))["release_speed"].mean()
    )
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

    # Build pitch_type -> pitch_name mapping from statcast
    name_map: dict[str, str] = {}
    name_df = data.statcast.select(["pitch_type", "pitch_name"]).unique()
    for row in name_df.iter_rows(named=True):
        name_map[row["pitch_type"]] = row["pitch_name"]

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
        season_p_plus = float(pt_baseline_row["P+"][0]) if not pt_baseline_row.is_empty() and "P+" in pt_baseline_row.columns else 0.0
        season_s_plus = float(pt_baseline_row["S+"][0]) if not pt_baseline_row.is_empty() and "S+" in pt_baseline_row.columns else 0.0
        season_l_plus = float(pt_baseline_row["L+"][0]) if not pt_baseline_row.is_empty() and "L+" in pt_baseline_row.columns else 0.0

        window_pplus = _weighted_window_pplus(
            data.agg_csvs["pitcher_type_appearance"],
            window_dates,
            pt,
        )
        window_p_plus = window_pplus["P+"]
        window_s_plus = window_pplus["S+"]
        window_l_plus = window_pplus["L+"]

        if cold_start:
            p_plus_delta = _COLD_START_STRING
            s_plus_delta = _COLD_START_STRING
            l_plus_delta = _COLD_START_STRING
        elif window_p_plus is not None:
            p_plus_delta = _pplus_delta_string(window_p_plus - season_p_plus)
            s_plus_delta = _pplus_delta_string(window_s_plus - season_s_plus) if window_s_plus is not None else "No window data"
            l_plus_delta = _pplus_delta_string(window_l_plus - season_l_plus) if window_l_plus is not None else "No window data"
        else:
            p_plus_delta = "No window data"
            s_plus_delta = "No window data"
            l_plus_delta = "No window data"

        # ── Pitch name ───────────────────────────────────────────
        pitch_name = name_map.get(pt, pt)

        # ── Small sample ─────────────────────────────────────────
        small_sample = n_window < _MIN_PITCHES

        results.append(PitchTypeSummary(
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
            n_pitches_season=n_season,
            n_pitches_window=n_window,
            small_sample=small_sample,
            cold_start=cold_start,
        ))

    # Sort by season usage descending
    results.sort(key=lambda x: x.season_usage_pct, reverse=True)
    return results


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

    # Build pitch_type -> pitch_name mapping
    name_map: dict[str, str] = {}
    name_df = data.statcast.select(["pitch_type", "pitch_name"]).unique()
    for row in name_df.iter_rows(named=True):
        name_map[row["pitch_type"]] = row["pitch_name"]

    # Add platoon_matchup column to statcast
    statcast_with_platoon = data.statcast.with_columns(
        pl.struct(["stand", "p_throws"]).map_elements(
            lambda s: _stand_to_platoon(s["stand"], s["p_throws"]),
            return_dtype=pl.Utf8,
        ).alias("platoon_matchup")
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
            season_side = statcast_with_platoon.filter(
                pl.col("platoon_matchup") == side
            )
            season_side_total = len(season_side)
            season_side_type = season_side.filter(pl.col("pitch_type") == pt)
            n_season_side_type = len(season_side_type)

            if n_season_side_type == 0:
                # Pitch not thrown to this side at all
                splits.append(PlatoonSplit(
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
                ))
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
                (pl.col("pitch_type") == pt)
                & (pl.col("platoon_matchup") == side)
            )
            season_p_plus: float | None = None
            if not plat_row.is_empty() and "P+" in plat_row.columns:
                season_p_plus = float(plat_row["P+"][0])

            # ── Window P+ from platoon appearance data ──
            window_plat_pplus = _weighted_window_platoon_pplus(
                data.agg_csvs["pitcher_type_platoon_appearance"],
                window_dates,
                pt,
                side,
            )
            window_p_plus = window_plat_pplus["P+"]

            # ── P+ delta ──
            if cold_start:
                p_plus_delta = _COLD_START_STRING
            elif season_p_plus is not None and window_p_plus is not None:
                p_plus_delta = _pplus_delta_string(window_p_plus - season_p_plus)
            else:
                p_plus_delta = "No window data"

            splits.append(PlatoonSplit(
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
            ))

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

    # Build pitch_type -> pitch_name mapping
    name_map: dict[str, str] = {}
    name_df = data.statcast.select(["pitch_type", "pitch_name"]).unique()
    for row in name_df.iter_rows(named=True):
        name_map[row["pitch_type"]] = row["pitch_name"]

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

        if cold_start:
            delta = _COLD_START_STRING
        else:
            delta = _usage_delta_string(window_pct - season_pct)

        entries.append(FirstPitchEntry(
            pitch_type=pt,
            pitch_name=name_map.get(pt, pt),
            season_pct=season_pct,
            window_pct=window_pct,
            delta=delta,
            n_first_pitches_season=n_season,
            n_first_pitches_window=n_window,
        ))

    # Sort by window_pct descending
    entries.sort(key=lambda x: x.window_pct, reverse=True)

    return FirstPitchWeaponry(
        entries=entries,
        total_first_pitches_season=total_season,
        total_first_pitches_window=total_window,
        cold_start=cold_start,
    )
