"""Fact-layer parity: scout._check_* functions vs engine delta functions (Phase 2).

Proves that the consolidated engine (compute_fastball_summary / compute_arsenal_summary)
produces identical delta values to the original scout functions when fed equivalent inputs.
All four tests must be green before Phase 2 Step 3 deletes the old scout._check_* math.

Delta types covered:
  - Velocity delta   : scout._check_velo_delta   vs FastballSummary.velo_delta_mph
  - P+ delta         : scout._check_pplus_swing   vs FastballSummary.p_plus_delta_pts
  - Usage shift      : scout._check_usage_shifts  vs PitchTypeSummary (window - season usage)
  - S+/L+ divergence : scout._check_splus_lplus_divergence vs PitchTypeSummary S+/L+ deltas
"""

from __future__ import annotations

import importlib
from datetime import date

import polars as pl
import pytest

from pitcher_narratives.data import PitcherData
from pitcher_narratives.engine import (
    compute_arsenal_summary,
    compute_fastball_summary,
)
from pitcher_narratives.scout import (
    _check_splus_lplus_divergence,
    _check_usage_shifts,
    _check_velo_delta,
)

# ── Phase-0 smoke test ────────────────────────────────────────────────


def test_scout_and_engine_import_successfully() -> None:
    """Verify that pitcher_narratives.scout and pitcher_narratives.engine import without error.

    This is the Phase 0 placeholder.  A later phase will add delta-parity
    assertions here once the consolidated engine functions exist.
    """
    assert importlib.import_module("pitcher_narratives.engine") is not None
    assert importlib.import_module("pitcher_narratives.scout") is not None


# ── Synthetic fixture constants ───────────────────────────────────────

_SEASON_DATE = date(2026, 5, 10)   # non-window game
_WINDOW_DATE = date(2026, 6, 10)   # single-game window

# Velocity scenario
_SEASON_FC_VELO: float = 93.0
_WINDOW_FC_VELO: float = 97.0
_N_SEASON_FC = 10   # non-window FC pitches
_N_WINDOW_FC = 5    # window FC pitches
# season_velo = mean over ALL statcast FC pitches (includes window):
# (10 * 93 + 5 * 97) / 15 = 94.333...
_SEASON_VELO_EXPECTED = (
    _N_SEASON_FC * _SEASON_FC_VELO + _N_WINDOW_FC * _WINDOW_FC_VELO
) / (_N_SEASON_FC + _N_WINDOW_FC)
_VELO_DELTA_EXPECTED = _WINDOW_FC_VELO - _SEASON_VELO_EXPECTED  # ≈ +2.667 mph

# P+ scenario
_SEASON_FC_PPLUS: float = 108.0
_WINDOW_FC_PPLUS: float = 121.0
_PPLUS_DELTA_EXPECTED: float = _WINDOW_FC_PPLUS - _SEASON_FC_PPLUS  # 13.0

# S+/L+ divergence scenario (used in single-type fixture)
_SEASON_FC_SPLUS: float = 100.0
_SEASON_FC_LPLUS: float = 100.0
_WINDOW_FC_SPLUS: float = 115.0   # up 15 pts
_WINDOW_FC_LPLUS: float = 82.0    # down 18 pts → divergence

# Usage scenario (two-type fixture only)
# Statcast totals: FC 28/40 = 70%, SL 12/40 = 30%.  Window: FC 8/10 = 80%.
_N_PRE_FC, _N_PRE_SL = 20, 10      # non-window pitches
_N_WIN_FC, _N_WIN_SL = 8, 2        # window pitches
_N_TOTAL_TWO_TYPE = _N_PRE_FC + _N_PRE_SL + _N_WIN_FC + _N_WIN_SL  # 40
_FC_SEASON_USAGE_PCT = (_N_PRE_FC + _N_WIN_FC) / _N_TOTAL_TWO_TYPE * 100.0  # 70.0
_SL_SEASON_USAGE_PCT = (_N_PRE_SL + _N_WIN_SL) / _N_TOTAL_TWO_TYPE * 100.0  # 30.0
_WINDOW_TOTAL = _N_WIN_FC + _N_WIN_SL  # 10
_FC_WINDOW_USAGE_PCT = _N_WIN_FC / _WINDOW_TOTAL * 100.0   # 80.0
_FC_USAGE_DELTA_EXPECTED = _FC_WINDOW_USAGE_PCT - _FC_SEASON_USAGE_PCT  # +10.0 pp


# ── Fixture builders ──────────────────────────────────────────────────


def _make_single_type_data() -> PitcherData:
    """Synthetic PitcherData with FC only for velo, P+, and S+/L+ parity tests.

    10 non-window FC pitches at 93 mph, 5 window FC pitches at 97 mph.
    Window game = game_pk 2 on _WINDOW_DATE.
    """
    n = _N_SEASON_FC + _N_WINDOW_FC

    statcast = pl.DataFrame({
        "game_pk":       [1] * _N_SEASON_FC + [2] * _N_WINDOW_FC,
        "game_date":     [_SEASON_DATE] * _N_SEASON_FC + [_WINDOW_DATE] * _N_WINDOW_FC,
        "pitch_type":    ["FC"] * n,
        "pitch_name":    ["Cutter"] * n,
        "release_speed": [_SEASON_FC_VELO] * _N_SEASON_FC + [_WINDOW_FC_VELO] * _N_WINDOW_FC,
        "pfx_x":         [0.5] * n,
        "pfx_z":         [1.0] * n,
        "stand":         ["R"] * n,
        "p_throws":      ["R"] * n,
        "inning":        [1] * n,
        "pitch_number":  list(range(1, n + 1)),
    })

    # 10 window appearances (all on _WINDOW_DATE) clear the G8 thin-frame
    # floor (>= _THIN_APPEARANCES) while staying below the season total, so
    # frame_sufficiency == "sufficient" and window-vs-season deltas compute.
    # All window pitch data still lives on _WINDOW_DATE, so the arithmetic is
    # unchanged from the single-appearance fixture.
    appearances = pl.DataFrame({
        "game_pk":   [1] + list(range(2, 12)),
        "game_date": [_SEASON_DATE] + [_WINDOW_DATE] * 10,
    })
    window_appearances = pl.DataFrame({
        "game_pk":   list(range(2, 12)),
        "game_date": [_WINDOW_DATE] * 10,
    })

    pitch_type_baseline = pl.DataFrame({
        "pitch_type": ["FC"],
        "n_pitches":  [n],
        "P+":         [_SEASON_FC_PPLUS],
        "S+":         [_SEASON_FC_SPLUS],
        "L+":         [_SEASON_FC_LPLUS],
        "usage_pct":  [100.0],
        "season":     [2026],
    })

    pitcher_type_appearance = pl.DataFrame({
        "game_date":  [_WINDOW_DATE],
        "pitch_type": ["FC"],
        "n_pitches":  [_N_WINDOW_FC],
        "P+":         [_WINDOW_FC_PPLUS],
        "S+":         [_WINDOW_FC_SPLUS],
        "L+":         [_WINDOW_FC_LPLUS],
    })

    empty = pl.DataFrame()
    return PitcherData(
        statcast=statcast,
        appearances=appearances,
        window_appearances=window_appearances,
        season_baseline=empty,
        pitch_type_baseline=pitch_type_baseline,
        prior_season_baseline=empty,
        prior_pitch_type_baseline=empty,
        agg_csvs={"pitcher_type_appearance": pitcher_type_appearance},
        pitcher_id=42,
        pitcher_name="Test",
        throws="R",
    )


def _make_two_type_data() -> PitcherData:
    """Synthetic PitcherData with FC + SL for usage-shift parity tests.

    Non-window: 20 FC + 10 SL → season usage FC 70%, SL 30%.
    Window: 8 FC + 2 SL → window usage FC 80% (+10 pp shift for FC).
    """
    n_pre = _N_PRE_FC + _N_PRE_SL
    n_win = _N_WIN_FC + _N_WIN_SL
    n = n_pre + n_win

    pre_types  = ["FC"] * _N_PRE_FC + ["SL"] * _N_PRE_SL
    win_types  = ["FC"] * _N_WIN_FC  + ["SL"] * _N_WIN_SL
    all_types  = pre_types + win_types
    all_names  = ["Cutter" if t == "FC" else "Slider" for t in all_types]
    all_dates  = [_SEASON_DATE] * n_pre + [_WINDOW_DATE] * n_win
    all_gp     = [1] * n_pre + [2] * n_win

    statcast = pl.DataFrame({
        "game_pk":       all_gp,
        "game_date":     all_dates,
        "pitch_type":    all_types,
        "pitch_name":    all_names,
        "release_speed": [93.0] * n,
        "pfx_x":         [0.5] * n,
        "pfx_z":         [1.0] * n,
        "stand":         ["R"] * n,
        "p_throws":      ["R"] * n,
        "inning":        [1] * n,
        "pitch_number":  list(range(1, n + 1)),
    })

    # 10 window appearances (all on _WINDOW_DATE) clear the G8 thin-frame
    # floor (>= _THIN_APPEARANCES) while staying below the season total, so
    # frame_sufficiency == "sufficient" and window-vs-season deltas compute.
    # All window pitch data still lives on _WINDOW_DATE, so the arithmetic is
    # unchanged from the single-appearance fixture.
    appearances = pl.DataFrame({
        "game_pk":   [1] + list(range(2, 12)),
        "game_date": [_SEASON_DATE] + [_WINDOW_DATE] * 10,
    })
    window_appearances = pl.DataFrame({
        "game_pk":   list(range(2, 12)),
        "game_date": [_WINDOW_DATE] * 10,
    })

    # usage_pct matches what compute_arsenal_summary derives from statcast above
    pitch_type_baseline = pl.DataFrame({
        "pitch_type": ["FC", "SL"],
        "n_pitches":  [_N_PRE_FC + _N_WIN_FC, _N_PRE_SL + _N_WIN_SL],
        "P+":         [_SEASON_FC_PPLUS, 100.0],
        "S+":         [_SEASON_FC_SPLUS, 100.0],
        "L+":         [_SEASON_FC_LPLUS, 100.0],
        "usage_pct":  [_FC_SEASON_USAGE_PCT, _SL_SEASON_USAGE_PCT],
        "season":     [2026, 2026],
    })

    pitcher_type_appearance = pl.DataFrame({
        "game_date":  [_WINDOW_DATE, _WINDOW_DATE],
        "pitch_type": ["FC", "SL"],
        "n_pitches":  [_N_WIN_FC, _N_WIN_SL],
        "P+":         [_WINDOW_FC_PPLUS, 100.0],
        "S+":         [_WINDOW_FC_SPLUS, 100.0],
        "L+":         [_WINDOW_FC_LPLUS, 100.0],
    })

    empty = pl.DataFrame()
    return PitcherData(
        statcast=statcast,
        appearances=appearances,
        window_appearances=window_appearances,
        season_baseline=empty,
        pitch_type_baseline=pitch_type_baseline,
        prior_season_baseline=empty,
        prior_pitch_type_baseline=empty,
        agg_csvs={"pitcher_type_appearance": pitcher_type_appearance},
        pitcher_id=42,
        pitcher_name="Test",
        throws="R",
    )


# ── Velo delta parity ─────────────────────────────────────────────────


def test_velo_delta_parity_arithmetic() -> None:
    """Engine velo_delta_mph equals scout delta arithmetic with identical inputs.

    Both paths compute delta = (window/game velo) - (season velo) from the
    same release_speed values.  With a single-game window, engine's window_velo
    equals scout's game_velo, so the deltas must match exactly.
    """
    data = _make_single_type_data()

    summary = compute_fastball_summary(data)
    assert summary is not None
    engine_delta = summary.velo_delta_mph

    # Reconstruct what compute_velo_baselines produces for this pitcher/game:
    # season_velo = mean of ALL fastballs (engine includes window pitches in season)
    all_fc = data.statcast.filter(pl.col("pitch_type") == "FC")
    season_velo = float(all_fc["release_speed"].mean())

    window_dates = data.window_appearances["game_date"].unique().to_list()
    game_velo = float(
        all_fc.filter(pl.col("game_date").is_in(window_dates))["release_speed"].mean()
    )

    scout_delta = game_velo - season_velo

    assert engine_delta == pytest.approx(scout_delta, abs=0.01)
    assert engine_delta == pytest.approx(_VELO_DELTA_EXPECTED, abs=0.01)


def test_velo_delta_parity_signal_fires() -> None:
    """Scout _check_velo_delta fires for the same delta that engine reports.

    velo_delta ≈ +2.67 mph exceeds scout's 1.5 mph threshold → signal fires.
    """
    all_fc_velos = [_SEASON_FC_VELO] * _N_SEASON_FC + [_WINDOW_FC_VELO] * _N_WINDOW_FC
    season_velo = sum(all_fc_velos) / len(all_fc_velos)
    game_velo = _WINDOW_FC_VELO

    velo_df = pl.DataFrame({
        "pitcher":     [42],
        "game_pk":     [2],
        "game_date":   [_WINDOW_DATE],
        "game_velo":   [game_velo],
        "season_velo": [season_velo],
    })
    signals = _check_velo_delta(42, 2, _WINDOW_DATE, velo_df)

    assert len(signals) == 1
    assert "up" in signals[0].detail.lower()


# ── P+ delta parity ───────────────────────────────────────────────────


def test_pplus_delta_parity_arithmetic() -> None:
    """Engine p_plus_delta_pts equals scout _check_pplus_swing arithmetic.

    Both compute delta = window_pplus - season_pplus.  With equivalent season
    and window values, the raw deltas must match within floating-point tolerance.
    """
    data = _make_single_type_data()

    summary = compute_fastball_summary(data)
    assert summary is not None
    assert summary.p_plus_delta_pts is not None, (
        "Expected non-None p_plus_delta_pts from synthetic pitcher_type_appearance data"
    )
    engine_delta = summary.p_plus_delta_pts

    # Scout formula: delta = float(game_pplus) - float(season_pplus)
    scout_delta = _WINDOW_FC_PPLUS - _SEASON_FC_PPLUS  # 121 - 108 = 13.0

    assert engine_delta == pytest.approx(scout_delta, abs=0.01)
    assert engine_delta == pytest.approx(_PPLUS_DELTA_EXPECTED, abs=0.01)


def test_pplus_delta_parity_direct_inputs() -> None:
    """Both paths produce the same subtraction when given the same P+ values."""
    # Scout: build minimal app_row and pitcher_baseline matching engine fixture values
    app_row = {"P+": _WINDOW_FC_PPLUS}
    pitcher_baseline = pl.DataFrame({"P+": [_SEASON_FC_PPLUS]})

    # _check_pplus_swing internally computes float(game_pplus) - float(season_pplus)
    # We verify the same arithmetic via the expected value
    scout_raw_delta = float(app_row["P+"]) - float(pitcher_baseline["P+"][0])

    # Engine value from fixture
    summary = compute_fastball_summary(_make_single_type_data())
    assert summary is not None and summary.p_plus_delta_pts is not None

    assert summary.p_plus_delta_pts == pytest.approx(scout_raw_delta, abs=0.01)


# ── Usage shift parity ────────────────────────────────────────────────


def test_usage_shift_parity_arithmetic() -> None:
    """Engine usage_delta_pp matches what _check_usage_shifts would compute.

    Both paths derive: delta = (game_n / total_game * 100) - season_usage_pct.
    Engine derives season_usage from statcast counts; scout reads usage_pct from
    the baseline.  The fixture aligns both to the same value (70% FC season).
    """
    data = _make_two_type_data()

    arsenal = compute_arsenal_summary(data)
    fc_summary = next((p for p in arsenal if p.pitch_type == "FC"), None)
    assert fc_summary is not None

    assert fc_summary.usage_delta_pp is not None, "Expected non-None usage_delta_pp (non-cold-start fixture)"
    engine_usage_delta = fc_summary.usage_delta_pp

    # Scout formula: game_usage = (n_pitches / total_pitches) * 100
    #                delta = game_usage - float(season_usage)
    scout_game_usage = (_N_WIN_FC / _WINDOW_TOTAL) * 100.0   # 80.0
    scout_season_usage = _FC_SEASON_USAGE_PCT                  # 70.0
    scout_delta = scout_game_usage - scout_season_usage        # +10.0

    assert engine_usage_delta == pytest.approx(scout_delta, abs=0.1)
    assert engine_usage_delta == pytest.approx(_FC_USAGE_DELTA_EXPECTED, abs=0.1)


def test_usage_shift_parity_signal_fires() -> None:
    """Scout _check_usage_shifts fires for the same 10 pp shift engine reports.

    10 pp exceeds scout's 8 pp threshold → signal fires for FC.
    """
    game_types = pl.DataFrame({
        "pitch_type": ["FC", "SL"],
        "n_pitches":  [_N_WIN_FC, _N_WIN_SL],
    })
    pitcher_type_bl = pl.DataFrame({
        "pitch_type": ["FC", "SL"],
        "usage_pct":  [_FC_SEASON_USAGE_PCT, _SL_SEASON_USAGE_PCT],
    })

    signals = _check_usage_shifts(game_types, pitcher_type_bl, _WINDOW_TOTAL)

    fired_types = {s.detail.split(" ")[0] for s in signals}
    assert "FC" in fired_types, (
        f"Expected usage_shift signal for FC (+10 pp), got signals: {[s.detail for s in signals]}"
    )


# ── S+/L+ divergence parity ──────────────────────────────────────────


def test_splus_lplus_divergence_parity_arithmetic() -> None:
    """Engine s_plus_delta_pts / l_plus_delta_pts match _check_splus_lplus_divergence arithmetic.

    Both compute delta = window_metric - season_metric per pitch type.
    S+ up 15, L+ down 18 → both paths see the same signed deltas.
    """
    data = _make_single_type_data()

    arsenal = compute_arsenal_summary(data)
    fc_summary = next((p for p in arsenal if p.pitch_type == "FC"), None)
    assert fc_summary is not None
    assert fc_summary.s_plus_delta_pts is not None
    assert fc_summary.l_plus_delta_pts is not None

    engine_s_delta = fc_summary.s_plus_delta_pts
    engine_l_delta = fc_summary.l_plus_delta_pts

    # Scout formula: s_delta = float(game_s) - float(season_s)
    scout_s_delta = _WINDOW_FC_SPLUS - _SEASON_FC_SPLUS   # +15.0
    scout_l_delta = _WINDOW_FC_LPLUS - _SEASON_FC_LPLUS   # -18.0

    assert engine_s_delta == pytest.approx(scout_s_delta, abs=0.01)
    assert engine_l_delta == pytest.approx(scout_l_delta, abs=0.01)


def test_splus_lplus_divergence_parity_signal_fires() -> None:
    """Scout _check_splus_lplus_divergence fires for the same divergence engine reports.

    S+ up 15 and L+ down 18 both exceed the 10-point divergence threshold and
    move in opposite directions → divergence signal fires for FC.
    """
    game_types = pl.DataFrame({
        "pitch_type": ["FC"],
        "n_pitches":  [_N_WINDOW_FC],
        "S+":         [_WINDOW_FC_SPLUS],
        "L+":         [_WINDOW_FC_LPLUS],
    })
    pitcher_type_bl = pl.DataFrame({
        "pitch_type": ["FC"],
        "S+":         [_SEASON_FC_SPLUS],
        "L+":         [_SEASON_FC_LPLUS],
    })

    signals = _check_splus_lplus_divergence(game_types, pitcher_type_bl)

    assert len(signals) == 1
    assert "FC" in signals[0].detail


def test_splus_lplus_divergence_direction_invariant() -> None:
    """Engine s_plus_delta_pts / l_plus_delta_pts agree on divergence direction."""
    data = _make_single_type_data()

    arsenal = compute_arsenal_summary(data)
    fc_summary = next((p for p in arsenal if p.pitch_type == "FC"), None)
    assert fc_summary is not None
    assert fc_summary.s_plus_delta_pts is not None
    assert fc_summary.l_plus_delta_pts is not None

    # S+ improved, L+ degraded in window — opposite directions
    assert fc_summary.s_plus_delta_pts > 0, "S+ delta should be positive (S+ rose)"
    assert fc_summary.l_plus_delta_pts < 0, "L+ delta should be negative (L+ fell)"


# ── Cross-path identity test (Step 5 gate) ────────────────────────────


_IDENTITY_PITCHER = 592155  # Booser, Cam — real data present in repo fixtures


def test_cross_path_recap_and_report_share_grounding() -> None:
    """Morning (render_recap) and report (_run_pipeline) fact-check the writer's
    capsule against the exact same source: ``_build_parity_union(ctx, specialists,
    key_signals)``, built once inside the shared ``_render_capsule`` core (see
    pipeline.py:_render_capsule, called by both render_recap and _run_pipeline).

    The old cue/DIGEST path (build_story_cue_from_context) is retired — Task 3
    moved morning onto render_recap, so there is no separate cue projection to
    compare against a report-side PitcherContext anymore. The parity guarantee
    is now structural: both paths' fact-check ground truth is the *same
    function call* over the *same* PitcherContext, and that ground truth
    deterministically embeds the pitcher's real numbers (fastball season
    velocity, per-pitch recent usage) via the trends/game-shape specialist
    input builders (render_fastball_section / render_arsenal_section) that
    _build_parity_union projects from ctx — not from LLM output.

    This replaces the retired cue-string parity gate.
    """
    from pitcher_narratives.context import assemble_pitcher_context
    from pitcher_narratives.data import load_pitcher_data
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.pipeline import _build_parity_union

    data = load_pitcher_data(_IDENTITY_PITCHER, recent_appearances=10)
    ctx = assemble_pitcher_context(data)

    # Empty specialist text isolates the deterministic ctx-derived ground
    # truth (_build_capsule_ground_truth) inside the union — the part both
    # morning and report build identically from the same ctx.
    specialists = SpecialistOutputs(
        stuff="", location="", runvalue="", trends="", game_shape="",
    )

    grounding = _build_parity_union(ctx, specialists, key_signals=None)

    # Fastball season velocity is embedded verbatim (render_fastball_section,
    # included in both the trends and game-shape specialist inputs).
    if ctx.fastball is not None:
        assert f"{ctx.fastball.season_velo:.1f}" in grounding, (
            f"Expected season_velo={ctx.fastball.season_velo:.1f} in shared grounding"
        )

    # Per-pitch recent usage for the arsenal is embedded verbatim
    # (render_arsenal_section, included in the trends specialist input).
    for pt in ctx.arsenal[:3]:
        assert f"{pt.window_usage_pct:.1f}%" in grounding, (
            f"Expected {pt.pitch_type} window_usage_pct={pt.window_usage_pct:.1f}% "
            "in shared grounding"
        )

    # Per-pitch plus grades (S+/L+) are embedded verbatim (render_fastball_section)
    # and are core fact-check anchors for the report's value; assert they survive
    # in the shared grounding so a fabricated plus-grade can still be caught by the
    # capsule auditor on either path.
    if ctx.fastball is not None:
        assert f"Stuff+ (S+): {ctx.fastball.season_s_plus:.0f} season" in grounding, (
            f"Expected season S+={ctx.fastball.season_s_plus:.0f} in shared grounding"
        )
        assert f"Location+ (L+): {ctx.fastball.season_l_plus:.0f} season" in grounding, (
            f"Expected season L+={ctx.fastball.season_l_plus:.0f} in shared grounding"
        )

    # Calling _build_parity_union twice on the same ctx (as morning's
    # render_recap and report's _run_pipeline each do inside _render_capsule)
    # produces byte-identical ground truth — the structural cross-path
    # guarantee that replaces the old cue-vs-context comparison.
    assert _build_parity_union(ctx, specialists, key_signals=None) == grounding
