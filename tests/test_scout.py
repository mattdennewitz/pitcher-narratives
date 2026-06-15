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
