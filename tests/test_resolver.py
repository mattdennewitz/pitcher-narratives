"""Tests for pitcher name resolution module.

Covers RESOLVE-01 (name matching) and RESOLVE-02 (disambiguation).
Tests run against the real statcast_2026.parquet file.
"""

from pitcher_narratives.resolver import ResolveResult, resolve


def test_exact_full_name():
    """RESOLVE-01a: Exact full name returns correct pitcher ID."""
    r = resolve("Dylan Cease")
    assert r.pitcher_id == 656302
    assert r.pitcher_name == "Cease, Dylan"
    assert r.candidates == []
    assert r.match_type == "exact"


def test_case_insensitive():
    """RESOLVE-01b: Case-insensitive match returns correct pitcher ID."""
    r = resolve("dylan cease")
    assert r.pitcher_id == 656302
    assert r.match_type == "exact"
