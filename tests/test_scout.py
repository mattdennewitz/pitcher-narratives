"""Tests for scout pure helpers: role-aware ranking."""

from datetime import date

from pitcher_narratives.scout import ScoredAppearance, top_per_role


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
    out = top_per_role(apps, top_n=2)
    assert [a.pitcher_id for a in out] == [1, 2, 4, 5]
    assert [a.score for a in out] == sorted([a.score for a in out], reverse=True)


def test_top_per_role_thin_bucket():
    """A bucket with fewer than N keeps everything it has."""
    apps = [_app(1, 9.0, "SP"), _app(4, 6.5, "RP")]
    out = top_per_role(apps, top_n=10)
    assert len(out) == 2


def test_scored_appearance_has_role_default():
    """role is part of the dataclass (default RP so old call sites work)."""
    a = _app(1, 1.0, "SP")
    assert a.role == "SP"


def test_role_map_coverage_warning(monkeypatch, caplog):
    """Warns when most window appearances are missing from the role map.

    Reproduces the silent failure where a stale statcast parquet (vs fresh
    aggregates) leaves recent game_pks out of the role map, so every
    appearance defaults to RP. Monkeypatching the role map to empty forces
    100% misses.
    """
    import logging

    import pitcher_narratives.scout as scout

    monkeypatch.setattr(scout, "_compute_role_map", lambda: {})
    with caplog.at_level(logging.WARNING, logger="pitcher_narratives.scout"):
        scout.scout_appearances(window_days=1, min_pitches=20)
    assert any("missing from the role map" in r.message for r in caplog.records)


def test_stale_aggregate_warning_when_statcast_leads(monkeypatch, caplog):
    """Warns when the statcast parquet has games newer than the appearance agg.

    Mirror of the role-map guard: when statcast leads the aggregates, the most
    recent outings exist in statcast but never enter the scored window. Forcing
    a far-future statcast max guarantees the lead regardless of fixture dates.
    """
    import logging
    from datetime import date

    import pitcher_narratives.scout as scout

    monkeypatch.setattr(scout, "_statcast_max_mlb_date", lambda: date(2100, 1, 1))
    with caplog.at_level(logging.WARNING, logger="pitcher_narratives.scout"):
        scout.scout_appearances(window_days=1, min_pitches=20)
    assert any("Appearance aggregate is stale" in r.message for r in caplog.records)


def test_no_stale_warning_when_statcast_not_ahead(monkeypatch, caplog):
    """No stale-aggregate warning when statcast is not ahead of the aggregate."""
    import logging
    from datetime import date

    import pitcher_narratives.scout as scout

    monkeypatch.setattr(scout, "_statcast_max_mlb_date", lambda: date(2000, 1, 1))
    with caplog.at_level(logging.WARNING, logger="pitcher_narratives.scout"):
        scout.scout_appearances(window_days=1, min_pitches=20)
    assert not any("Appearance aggregate is stale" in r.message for r in caplog.records)


def _profile(**over):
    """One-row compute_pitch_profiles frame; override any column via kwargs."""
    import polars as pl

    base = {
        "pitcher": 42, "game_pk": 7, "game_date": date(2026, 7, 4),
        "game_velo": 90.0, "season_velo": 92.0,
        "velo_median": 92.0, "velo_rstd": 1.0,
        "game_spin": 2200.0, "season_spin": 2300.0,
        "spin_median": 2300.0, "spin_rstd": 60.0,
        "velo_first_third": 91.0, "velo_last_third": 88.0, "velo_decline": -3.0,
    }
    base.update(over)
    return pl.DataFrame([base])


def test_velo_change_fires_on_flat_floor():
    """A >=1.5 mph drop fires even when it is unremarkable for the pitcher (z small)."""
    from pitcher_narratives.scout import _check_velo_change
    # 2 mph drop, but the pitcher's own scale is wide so z is modest.
    sigs = _check_velo_change(42, 7, _profile(game_velo=90.0, season_velo=92.0,
                                              velo_median=92.0, velo_rstd=5.0))
    assert len(sigs) == 1 and sigs[0].name == "velo_delta"
    assert "down 2.0 mph" in sigs[0].detail


def test_velo_change_fires_on_robust_z_when_flat_misses():
    """A sub-1.5 mph drop that is large for a low-variance pitcher still fires (#4)."""
    from pitcher_narratives.scout import _check_velo_change
    # 0.9 mph drop (< 1.5 flat) but 3.0 robust sigmas on a tight arm.
    sigs = _check_velo_change(42, 7, _profile(game_velo=91.1, season_velo=92.0,
                                              velo_median=92.0, velo_rstd=0.3))
    assert len(sigs) == 1
    assert "z=-3.0" in sigs[0].detail


def test_velo_change_silent_when_quiet():
    """No signal when the drop is small both absolutely and relative to the pitcher."""
    from pitcher_narratives.scout import _check_velo_change
    sigs = _check_velo_change(42, 7, _profile(game_velo=91.7, season_velo=92.0,
                                              velo_median=92.0, velo_rstd=1.0))
    assert sigs == []


def test_velo_decline_fires_on_in_game_cliff():
    """An in-outing velo cliff beyond the threshold fires with the two thirds."""
    from pitcher_narratives.scout import _check_velo_decline
    sigs = _check_velo_decline(42, 7, _profile(velo_first_third=91.0,
                                               velo_last_third=88.0, velo_decline=-3.0))
    assert len(sigs) == 1 and sigs[0].name == "velo_decline"
    assert "91.0 -> 88.0" in sigs[0].detail


def test_velo_decline_ignores_mild_fatigue():
    """A normal end-of-start dip below the threshold does not fire."""
    from pitcher_narratives.scout import _check_velo_decline
    assert _check_velo_decline(42, 7, _profile(velo_decline=-0.8)) == []


def test_velo_decline_none_safe():
    """A thin outing (velo_decline suppressed to None) produces no signal."""
    from pitcher_narratives.scout import _check_velo_decline
    assert _check_velo_decline(42, 7, _profile(velo_decline=None)) == []


def test_spin_drop_fires_on_robust_z():
    """A spin drop beyond the robust-z threshold fires."""
    from pitcher_narratives.scout import _check_spin_drop
    # -150 rpm on a 60-rpm robust scale -> z = -2.5.
    sigs = _check_spin_drop(42, 7, _profile(game_spin=2150.0, spin_median=2300.0,
                                            season_spin=2300.0, spin_rstd=60.0))
    assert len(sigs) == 1 and sigs[0].name == "spin_drop"
    assert "down 150 rpm" in sigs[0].detail


def test_spin_drop_ignores_normal_wobble():
    """A within-variance spin dip (like Woodruff's -57 rpm ~ -0.7 sigma) stays quiet."""
    from pitcher_narratives.scout import _check_spin_drop
    sigs = _check_spin_drop(42, 7, _profile(game_spin=2272.0, spin_median=2320.0,
                                            season_spin=2329.0, spin_rstd=71.0))
    assert sigs == []  # z ~= -0.68, below the 1.5 bar


def test_spin_drop_ignores_spike():
    """A spin *increase* is not an injury tell -- only drops fire."""
    from pitcher_narratives.scout import _check_spin_drop
    assert _check_spin_drop(42, 7, _profile(game_spin=2500.0, spin_median=2300.0,
                                            spin_rstd=60.0)) == []


def _game_pitches(pitcher, game_pk, day, pitches):
    """Rows for one game. `pitches` is a list of (pitch_type, velo, spin) in throw order."""
    n = len(pitches)
    return {
        "pitcher": [pitcher] * n,
        "game_pk": [game_pk] * n,
        "game_date": [date(2026, 6, day)] * n,
        "pitch_type": [p[0] for p in pitches],
        "release_speed": [p[1] for p in pitches],
        "release_spin_rate": [p[2] for p in pitches],
        "at_bat_number": list(range(1, n + 1)),
        "pitch_number": [1] * n,
        "level": ["MLB"] * n,
    }


def _statcast(*games):
    import polars as pl

    frames = [pl.DataFrame(_game_pitches(*g)) for g in games]
    return pl.concat(frames)


def test_compute_pitch_profiles_decline_and_robust_stats(monkeypatch):
    """In-game decline plus non-null leave-one-out robust stats (enough games)."""
    import polars as pl

    import pitcher_narratives.scout as scout

    steady = [("FF", 93.0, 2400.0)] * 12
    cliff = [("FF", 93.0, 2200.0)] * 4 + [("FF", 90.5, 2200.0)] * 4 + [("FF", 88.0, 2200.0)] * 4
    # Six games so the cliff game has 5 others -> clears _MIN_GAMES_FOR_Z.
    games = [(1, 10 + i, i + 1, steady) for i in range(5)] + [(1, 20, 7, cliff)]
    monkeypatch.setattr(scout, "load_all_statcast", lambda columns=None: _statcast(*games))

    prof = scout.compute_pitch_profiles()
    row = prof.filter(pl.col("game_pk") == 20).row(0, named=True)
    assert row["velo_first_third"] == 93.0
    assert row["velo_last_third"] == 88.0
    assert row["velo_decline"] == -5.0
    assert row["velo_median"] is not None and row["velo_rstd"] is not None


def test_pitch_profiles_leave_one_out_excludes_self(monkeypatch):
    """The robust center for a game is the median of the pitcher's OTHER games."""
    import polars as pl

    import pitcher_narratives.scout as scout

    steady = [("FF", 93.0, 2400.0)] * 10
    cliff = [("FF", 85.0, 2400.0)] * 10
    games = [(1, 10 + i, i + 1, steady) for i in range(5)] + [(1, 20, 7, cliff)]
    monkeypatch.setattr(scout, "load_all_statcast", lambda columns=None: _statcast(*games))

    prof = scout.compute_pitch_profiles()
    row = prof.filter(pl.col("game_pk") == 20).row(0, named=True)
    # Median excludes the 85 mph cliff game itself -> sits at the 93 mph others,
    # so the game reads as a large outlier rather than dampening its own center.
    assert row["velo_median"] == 93.0


def test_pitch_profiles_robust_null_below_min_games(monkeypatch):
    """Too few other games -> robust center/scale null so only the flat floor fires."""
    import polars as pl

    import pitcher_narratives.scout as scout

    steady = [("FF", 93.0, 2400.0)] * 10
    games = [(1, 10, 1, steady), (1, 20, 7, steady)]  # only 2 games total
    monkeypatch.setattr(scout, "load_all_statcast", lambda columns=None: _statcast(*games))

    prof = scout.compute_pitch_profiles()
    row = prof.filter(pl.col("game_pk") == 20).row(0, named=True)
    assert row["velo_median"] is None and row["velo_rstd"] is None


def test_in_game_decline_survives_soft_late_fastball_usage(monkeypatch):
    """A late velo cliff is caught even when the pitcher throws few fastballs late.

    Fastballs are front-loaded and the final third is mostly changeups with only
    a couple of much slower fastballs. Bucketing thirds over ALL pitches keeps
    those late fastballs in the last window instead of averaging in healthy
    mid-game heaters -- the fix for soft-late compensation.
    """
    import polars as pl

    import pitcher_narratives.scout as scout

    # 27 pitches: first third all 93 mph fastballs, last third mostly changeups
    # with two 86 mph fastballs; a fastball-position split would miss the cliff.
    early = [("FF", 93.0, 2400.0)] * 9
    middle = [("FF", 92.0, 2400.0)] * 6 + [("CH", 84.0, 1700.0)] * 3
    late = [("CH", 84.0, 1700.0)] * 7 + [("FF", 86.0, 2400.0)] * 2
    game = (1, 20, 7, early + middle + late)
    # A few filler games so the row survives and joins cleanly.
    others = [(1, 10 + i, i + 1, [("FF", 93.0, 2400.0)] * 12) for i in range(5)]
    monkeypatch.setattr(scout, "load_all_statcast", lambda columns=None: _statcast(game, *others))

    prof = scout.compute_pitch_profiles()
    row = prof.filter(pl.col("game_pk") == 20).row(0, named=True)
    assert row["velo_first_third"] == 93.0     # early fastballs
    assert row["velo_last_third"] == 86.0      # the two late fastballs, not mid-game ones
    assert row["velo_decline"] == -7.0


def test_divergence_ignores_tiny_pitch_type_samples():
    """A pitch type thrown too few times can't establish a stuff/command split.

    Guards against phantom signals like a single sinker whose Location+ model
    output (-138) produced a -261 'divergence' that was pure small-sample noise.
    """
    import polars as pl

    from pitcher_narratives.scout import _check_splus_lplus_divergence

    game_types = pl.DataFrame({
        "pitch_type": ["SI", "SL"],
        "n_pitches": [1, 10],           # SI: 1 pitch (noise); SL: 10 (real)
        "S+": [110.0, 112.0],
        "L+": [-138.0, 60.0],
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SI", "SL"],
        "S+": [96.0, 100.0],
        "L+": [122.0, 100.0],
    })
    fired = {s.detail.split(":")[0] for s in _check_splus_lplus_divergence(game_types, baseline)}
    assert "SI" not in fired   # 1-pitch sample gated out
    assert "SL" in fired       # 10-pitch divergence still fires


def test_development_opportunity_ignores_tiny_samples():
    """High-S+/low-L+ 'stuff without feel' needs a real sample, not one pitch."""
    import polars as pl

    from pitcher_narratives.scout import _check_development_opportunity

    game_types = pl.DataFrame({
        "pitch_type": ["SI", "SL"],
        "n_pitches": [1, 10],
        "S+": [120.0, 130.0],
        "L+": [20.0, 30.0],
    })
    fired = {s.detail.split(":")[0] for s in _check_development_opportunity(game_types, pl.DataFrame())}
    assert "SI" not in fired
    assert "SL" in fired


def test_command_surge_fires_when_poor_command_locates_well():
    """A pitch that was a command liability (low season L+) now locating well fires."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SL"],
        "n_pitches": [12],
        "S+": [105.0],
        "L+": [118.0],          # game L+ well above the 110 floor
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SL"],
        "S+": [104.0],
        "L+": [82.0],           # season command was poor (< 90)
    })
    fired = {s.detail.split(":")[0] for s in _check_command_surge(game_types, baseline)}
    assert "SL" in fired


def test_command_surge_ignores_already_good_command():
    """A good outing on a pitch that already commanded well is not a breakout."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SL"],
        "n_pitches": [12],
        "S+": [105.0],
        "L+": [118.0],          # game L+ clears the floor
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SL"],
        "S+": [104.0],
        "L+": [96.0],           # season L+ >= 90 — no prior command deficit
    })
    assert _check_command_surge(game_types, baseline) == []


def test_command_surge_ignores_sub_floor_command():
    """Improvement off a poor baseline that still lands below the good-command floor."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SL"],
        "n_pitches": [12],
        "S+": [105.0],
        "L+": [104.0],          # better than season, but below the 110 floor
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SL"],
        "S+": [104.0],
        "L+": [82.0],           # season command was poor
    })
    assert _check_command_surge(game_types, baseline) == []


def test_command_surge_ignores_tiny_samples():
    """A one-pitch L+ can't establish a command jump (small-sample gate)."""
    import polars as pl

    from pitcher_narratives.scout import _check_command_surge

    game_types = pl.DataFrame({
        "pitch_type": ["SI", "SL"],
        "n_pitches": [1, 12],
        "S+": [105.0, 105.0],
        "L+": [125.0, 118.0],
    })
    baseline = pl.DataFrame({
        "pitch_type": ["SI", "SL"],
        "S+": [104.0, 104.0],
        "L+": [82.0, 82.0],     # both were poor; only the well-sampled SL fires
    })
    fired = {s.detail.split(":")[0] for s in _check_command_surge(game_types, baseline)}
    assert "SI" not in fired
    assert "SL" in fired


def test_command_surge_flows_through_scout_appearances():
    """End-to-end: a command_surge signal reaches scout_appearances and scores.

    Covers the per-appearance assembly wiring that the isolated
    _check_command_surge tests don't, using the on-disk aggregates the suite
    already scores against (cf. test_role_map_coverage_warning).
    """
    from pitcher_narratives.scout import _WEIGHTS, scout_appearances

    results = scout_appearances(window_days=14, min_pitches=20)
    surged = [a for a in results if any(s.name == "command_surge" for s in a.signals)]
    assert surged, "expected at least one command_surge appearance in a 14-day window"

    app = surged[0]
    # The signal is present at its configured weight ...
    assert any(
        s.name == "command_surge" and s.weight == _WEIGHTS["command_surge"]
        for s in app.signals
    )
    # ... and the score is the sum of all signal weights, so the surge contributes.
    assert app.score == sum(s.weight for s in app.signals)
    assert app.score >= _WEIGHTS["command_surge"]
