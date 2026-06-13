"""Workload and temporal context: rest days, innings pitched, consecutive
appearances, season grounding, and cross-season metric deltas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine._common import (
    _DOUBLE_OUT_EVENTS,
    _OUT_EVENTS,
    _per_season_velo,
    _pplus_delta_string,
    _safe_metric,
    _velo_delta_string,
)


@dataclass
class AppearanceWorkload:
    """Workload data for a single appearance."""

    game_pk: int
    game_date: str
    """ISO date string."""

    role: str
    """'SP' or 'RP'."""

    ip: str
    """Baseball notation: '5.2', '1.0', '0.1'."""

    pitch_count: int
    rest_days: int | None
    """None for first appearance."""


@dataclass
class WorkloadContext:
    """Workload and rest context for the pitcher."""

    appearances: list[AppearanceWorkload]
    max_consecutive_days: int
    """Maximum consecutive calendar days pitched."""

    workload_concern: bool
    """True when max_consecutive_days >= 3."""


@dataclass
class TemporalContext:
    """Temporal grounding for LLM narratives -- prevents cross-season hallucination."""

    analysis_date: date
    current_season: int
    current_season_appearances: int
    current_season_first_date: str
    """ISO date of first appearance this season."""
    current_season_ip: str
    """Baseball-notation IP total for current season."""
    prior_season: int
    prior_season_appearances: int
    prior_season_ip: str
    """Baseball-notation IP total for prior season."""
    prior_year_relevance: str
    """'HIGH', 'MODERATE', or 'LOW'."""
    prior_year_relevance_reason: str
    """Human-readable explanation for the LLM."""


@dataclass
class CrossSeasonSummary:
    """Year-over-year pitcher-level metric deltas.

    Produced by compute_cross_season_summary(). None when the pitcher
    has only one season of data.
    """

    current_season: int
    prior_season: int

    # Velocity
    current_velo: float | None
    prior_velo: float | None
    velo_delta: str
    """Qualitative YoY velocity delta, e.g., 'Up 1.2 mph' or 'N/A'."""

    # P+ / S+ / L+
    current_p_plus: float
    prior_p_plus: float
    p_plus_delta: str

    current_s_plus: float
    prior_s_plus: float
    s_plus_delta: str

    current_l_plus: float
    prior_l_plus: float
    l_plus_delta: str



def _compute_ip_all_games(statcast: pl.DataFrame) -> dict[int, str]:
    """Compute innings pitched for every game in one pass.

    Groups by game_pk, then for each game counts full innings (all
    innings except the last) and event-based outs in the final inning.

    Returns:
        dict mapping game_pk → IP in baseball notation ('5.1', '1.0', etc.).
    """
    out_list = list(_OUT_EVENTS)
    double_out_list = list(_DOUBLE_OUT_EVENTS)

    result: dict[int, str] = {}
    for game_pk, game in statcast.group_by("game_pk"):
        gpk = int(game_pk[0])  # type: ignore[index]
        innings = sorted(game["inning"].unique().to_list())
        if not innings:
            result[gpk] = "0.0"
            continue

        n_full_innings = max(0, len(innings) - 1)
        final_inning = game.filter(pl.col("inning") == innings[-1])
        outs_in_final = final_inning.filter(
            pl.col("events").is_in(out_list)
        ).height
        outs_in_final += final_inning.filter(
            pl.col("events").is_in(double_out_list)
        ).height

        total_thirds = n_full_innings * 3 + outs_in_final
        result[gpk] = f"{total_thirds // 3}.{total_thirds % 3}"

    return result


def _compute_ip(statcast: pl.DataFrame, game_pk: int) -> str:
    """Compute innings pitched for a single appearance as baseball notation.

    Prefer _compute_ip_all_games() for batch use. This wrapper exists
    for call sites that need IP for one game only.
    """
    return _compute_ip_all_games(statcast.filter(pl.col("game_pk") == game_pk)).get(
        game_pk, "0.0"
    )


def _compute_rest_days(appearance_dates: list[Any]) -> list[int | None]:
    """Compute rest days between consecutive appearances.

    First appearance returns None. Subsequent appearances return
    (date[i] - date[i-1]).days - 1 so that consecutive calendar days
    yield 0 rest days.

    Args:
        appearance_dates: List of date objects (will be sorted).

    Returns:
        List of rest day counts, same length as input.
    """
    sorted_dates = sorted(appearance_dates)
    result: list[int | None] = [None]
    for i in range(1, len(sorted_dates)):
        rest = (sorted_dates[i] - sorted_dates[i - 1]).days - 1
        result.append(rest)
    return result


def _max_consecutive_days(appearance_dates: list[Any]) -> int:
    """Compute maximum consecutive calendar days pitched.

    Args:
        appearance_dates: List of date objects (will be sorted).

    Returns:
        Maximum consecutive days (1 = single day, 2 = two consecutive days, etc.).
    """
    if not appearance_dates:
        return 0
    sorted_dates = sorted(appearance_dates)
    consecutive = 1
    max_run = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            consecutive += 1
            max_run = max(max_run, consecutive)
        else:
            consecutive = 1
    return max_run




def compute_workload_context(data: PitcherData) -> WorkloadContext:
    """Compute workload and rest context for the pitcher.

    Builds appearance workload entries with IP (baseball notation), pitch
    counts, rest days, and consecutive-days tracking.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        WorkloadContext dataclass with appearance list and flags.
    """
    # Sort appearances by game_date ascending
    appearances = data.appearances.sort("game_date")

    # Extract appearance dates for rest days and consecutive days
    appearance_dates = appearances["game_date"].to_list()
    rest_days_list = _compute_rest_days(appearance_dates)
    max_consec = _max_consecutive_days(appearance_dates)

    # Batch compute IP and pitch counts in one pass each
    ip_by_game = _compute_ip_all_games(data.statcast)
    pitch_counts = (
        data.statcast.group_by("game_pk")
        .agg(pl.len().alias("n"))
    )
    pc_map = dict(zip(
        pitch_counts["game_pk"].to_list(),
        pitch_counts["n"].to_list(),
        strict=False,
    ))

    workload_entries: list[AppearanceWorkload] = []

    for i, row in enumerate(appearances.iter_rows(named=True)):
        game_pk = int(row["game_pk"])
        workload_entries.append(
            AppearanceWorkload(
                game_pk=game_pk,
                game_date=str(row["game_date"]),
                role=str(row["role"]),
                ip=ip_by_game.get(game_pk, "0.0"),
                pitch_count=pc_map.get(game_pk, 0),
                rest_days=rest_days_list[i],
            )
        )

    return WorkloadContext(
        appearances=workload_entries,
        max_consecutive_days=max_consec,
        workload_concern=max_consec >= 3,
    )


def _sum_baseball_ip(ip_strings: list[str]) -> str:
    """Sum a list of baseball-notation IP strings.

    Each IP string is in the format "W.R" where W is whole innings and
    R is the remainder (0, 1, or 2 thirds of an inning). Converts each
    to thirds, sums, and converts back.

    Args:
        ip_strings: List of IP strings, e.g., ["5.1", "3.2", "6.0"].

    Returns:
        Summed IP in baseball notation, e.g., "15.0".
    """
    total_thirds = 0
    for ip in ip_strings:
        parts = ip.split(".")
        whole = int(parts[0])
        remainder = int(parts[1]) if len(parts) > 1 else 0
        total_thirds += whole * 3 + remainder
    return f"{total_thirds // 3}.{total_thirds % 3}"


def compute_temporal_context(
    data: PitcherData,
    workload: WorkloadContext,
) -> TemporalContext:
    """Compute temporal grounding for LLM narratives.

    Splits appearances by season year, counts per-season appearances and
    IP totals, and assigns a prior-year relevance tier that gates how
    much weight the LLM gives to last season's workload.

    Reuses IP values already computed by compute_workload_context() to
    avoid redundant statcast scans.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.
        workload: Pre-computed workload context (provides per-game IP).

    Returns:
        TemporalContext with per-season stats and relevance tier.
    """
    appearances = data.appearances.with_columns(
        pl.col("game_date").dt.year().alias("season_year")
    )

    current_season = int(appearances["season_year"].max())
    prior_season = current_season - 1

    # Build game_pk → IP lookup from workload (already computed)
    ip_by_game = {a.game_pk: a.ip for a in workload.appearances}

    # Current season appearances
    current_apps = appearances.filter(pl.col("season_year") == current_season)
    current_season_appearances = current_apps.height

    # Current season first date
    current_first_date = str(current_apps["game_date"].min())

    # Current season IP from workload lookup
    current_game_pks = current_apps["game_pk"].to_list()
    current_ip_strings = [ip_by_game.get(int(gpk), "0.0") for gpk in current_game_pks]
    current_season_ip = _sum_baseball_ip(current_ip_strings) if current_ip_strings else "0.0"

    # Prior season appearances
    prior_apps = appearances.filter(pl.col("season_year") == prior_season)
    prior_season_appearances = prior_apps.height

    # Prior season IP from workload lookup
    if prior_season_appearances > 0:
        prior_game_pks = prior_apps["game_pk"].to_list()
        prior_ip_strings = [ip_by_game.get(int(gpk), "0.0") for gpk in prior_game_pks]
        prior_season_ip = _sum_baseball_ip(prior_ip_strings)
    else:
        prior_season_ip = "0.0"

    # Prior-year relevance tier
    if prior_season_appearances == 0:
        relevance = "N/A"
        relevance_reason = (
            f"No {prior_season} data available. Current season sample "
            f"({current_season_appearances} appearances) stands alone -- "
            f"prior-year workload is not a factor."
        )
    elif current_season_appearances < 10:
        relevance = "HIGH"
        relevance_reason = (
            f"Current season sample is too small to establish its own workload "
            f"narrative. {prior_season} workload ({prior_season_appearances} G / "
            f"{prior_season_ip} IP) is plausible residual context, but do not "
            f"treat the two seasons as a continuous timeline."
        )
    elif current_season_appearances <= 30:
        relevance = "MODERATE"
        relevance_reason = (
            "Patterns are emerging but sample is still growing. Prior year "
            "adds context for year-over-year comparison."
        )
    else:
        relevance = "LOW"
        relevance_reason = (
            "Current season has enough volume to carry its own workload "
            "narrative. Use prior year for trend comparison only, not "
            "workload narrative."
        )

    return TemporalContext(
        analysis_date=date.today(),
        current_season=current_season,
        current_season_appearances=current_season_appearances,
        current_season_first_date=current_first_date,
        current_season_ip=current_season_ip,
        prior_season=prior_season,
        prior_season_appearances=prior_season_appearances,
        prior_season_ip=prior_season_ip,
        prior_year_relevance=relevance,
        prior_year_relevance_reason=relevance_reason,
    )


def compute_cross_season_summary(data: PitcherData) -> CrossSeasonSummary | None:
    """Compute cross-season YoY deltas for pitcher-level metrics.

    Compares current (max) season baselines with prior-season baselines
    to produce year-over-year delta strings for velocity, P+, S+, and L+.

    Per-season workload (appearances, IP) lives in TemporalContext — this
    function focuses on the metric deltas that TemporalContext does not cover.

    Returns None when prior-season data is missing (SDLT-03).

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        CrossSeasonSummary with YoY deltas, or None for single-season pitchers.
    """
    if data.prior_season_baseline.is_empty():
        return None

    # Extract season years
    current_season = int(data.season_baseline["season"][0])
    prior_seasons = data.prior_season_baseline["season"].unique().to_list()
    prior_season = int(max(prior_seasons))

    # P+ / S+ / L+ from season baselines (SDLT-01)
    current_p_plus = _safe_metric(data.season_baseline, "P+")
    current_s_plus = _safe_metric(data.season_baseline, "S+")
    current_l_plus = _safe_metric(data.season_baseline, "L+")

    prior_p_plus = _safe_metric(data.prior_season_baseline, "P+")
    prior_s_plus = _safe_metric(data.prior_season_baseline, "S+")
    prior_l_plus = _safe_metric(data.prior_season_baseline, "L+")

    # Velocity from statcast release_speed per season (SDLT-01)
    velo_by_season = _per_season_velo(data.statcast)
    current_velo = velo_by_season.get(current_season)
    prior_velo = velo_by_season.get(prior_season)

    # Delta strings reusing existing functions (SDLT-02)
    velo_delta = (
        _velo_delta_string(current_velo - prior_velo)
        if current_velo is not None and prior_velo is not None
        else "N/A"
    )
    p_plus_delta = _pplus_delta_string(current_p_plus - prior_p_plus)
    s_plus_delta = _pplus_delta_string(current_s_plus - prior_s_plus)
    l_plus_delta = _pplus_delta_string(current_l_plus - prior_l_plus)

    return CrossSeasonSummary(
        current_season=current_season,
        prior_season=prior_season,
        current_velo=current_velo,
        prior_velo=prior_velo,
        velo_delta=velo_delta,
        current_p_plus=current_p_plus,
        prior_p_plus=prior_p_plus,
        p_plus_delta=p_plus_delta,
        current_s_plus=current_s_plus,
        prior_s_plus=prior_s_plus,
        s_plus_delta=s_plus_delta,
        current_l_plus=current_l_plus,
        prior_l_plus=prior_l_plus,
        l_plus_delta=l_plus_delta,
    )


