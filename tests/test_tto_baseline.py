"""Tests for the offline league-SP TTO baseline build + artifact loader."""

import polars as pl

from pitcher_narratives.tto_baseline import build_tto_baseline


def _synthetic():
    # 2 SP appearances (game 1,2), pitcher 100, first inning == 1 (SP).
    # pass1 velo 96, pass2 velo 95 (Δ−1) in game1; pass2 velo 93 (Δ−3) in game2.
    rows = []

    def add(game, pitch_no, tto, velo, pplus, inning):
        rows.append(
            dict(
                pitcher=100,
                game_pk=game,
                pitch_number=pitch_no,
                n_thruorder_pitcher=tto,
                release_speed=velo,
                pitch_type="FF",
                stand="R",
                inning=inning,
                inning_topbot="Top",
                at_bat_number=pitch_no,
                P_plus=pplus,
            )
        )

    # game 1
    add(1, 1, 1, 96.0, 105.0, 1)
    add(1, 2, 2, 95.0, 101.0, 5)
    # game 2
    add(2, 1, 1, 96.0, 105.0, 1)
    add(2, 2, 2, 93.0, 97.0, 5)
    sc = pl.DataFrame(rows).select(
        "pitcher",
        "game_pk",
        "pitch_number",
        "n_thruorder_pitcher",
        "release_speed",
        "pitch_type",
        "stand",
        "inning",
        "inning_topbot",
        "at_bat_number",
    )
    ap = pl.DataFrame(rows).select("pitcher", "game_pk", "pitch_number").with_columns(
        pl.Series("P+", [r["P_plus"] for r in rows])
    )
    return sc, ap


def test_build_emits_long_form_league_sp_rows():
    sc, ap = _synthetic()
    base = build_tto_baseline(sc, ap)
    assert set(base.columns) == {"cohort_key", "pass_num", "metric", "median_exp_delta", "mad", "n"}
    assert base["cohort_key"].unique().to_list() == ["LEAGUE_SP"]
    # pass 1 is the Δ≡0 reference and is NOT stored
    assert 1 not in base["pass_num"].to_list()
    velo2 = base.filter((pl.col("pass_num") == 2) & (pl.col("metric") == "velo"))
    # per-appearance velo deltas at pass2: −1.0 and −3.0 → median −2.0
    assert round(velo2["median_exp_delta"][0], 3) == -2.0
    assert velo2["n"][0] == 2
    # MAD = median(|−1−(−2)|, |−3−(−2)|) = median(1, 1) = 1.0
    assert round(velo2["mad"][0], 3) == 1.0
    pplus2 = base.filter((pl.col("pass_num") == 2) & (pl.col("metric") == "pplus"))
    # pplus deltas: (101−105)=−4, (97−105)=−8 → median −6.0
    assert round(pplus2["median_exp_delta"][0], 3) == -6.0
    # MAD = median(|−4−(−6)|, |−8−(−6)|) = median(2, 2) = 2.0
    assert round(pplus2["mad"][0], 3) == 2.0


def test_load_tto_baseline_missing_returns_none(tmp_path, monkeypatch):
    import pitcher_narratives.data as d

    d.load_tto_baseline.cache_clear()
    monkeypatch.setenv("PITCHER_NARRATIVES_TTO_BASELINE", str(tmp_path / "nope.parquet"))
    assert d.load_tto_baseline() is None
    d.load_tto_baseline.cache_clear()


def test_load_tto_baseline_present_returns_dataframe(tmp_path, monkeypatch):
    import pitcher_narratives.data as d
    from pitcher_narratives.tto_baseline import write_tto_baseline

    sc, ap = _synthetic()
    base = build_tto_baseline(sc, ap)
    path = tmp_path / "tto_baseline.parquet"
    write_tto_baseline(base, path)

    d.load_tto_baseline.cache_clear()
    monkeypatch.setenv("PITCHER_NARRATIVES_TTO_BASELINE", str(path))
    loaded = d.load_tto_baseline()
    assert loaded is not None
    assert loaded.height == base.height
    d.load_tto_baseline.cache_clear()
