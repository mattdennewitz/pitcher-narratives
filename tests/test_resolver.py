"""Tests for pitcher name resolution module.

Covers RESOLVE-01 (name matching) and RESOLVE-02 (disambiguation).
Tests run against the real Statcast parquet files (see STATCAST_PATH).
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


def test_last_name_only():
    """RESOLVE-01c: Last-name-only 'Cease' returns correct pitcher."""
    r = resolve("Cease")
    assert r.pitcher_id == 656302
    assert r.match_type == "exact_last"


def test_comma_format():
    """RESOLVE-01d: Comma-separated 'cease, dylan' resolves correctly."""
    r = resolve("cease, dylan")
    assert r.pitcher_id == 656302


def test_unicode_normalization():
    """RESOLVE-01e: Unicode input 'Munoz' matches accented name in dataset."""
    r = resolve("Munoz")
    assert r.pitcher_id is not None or r.match_type == "ambiguous"
    assert r.match_type != "not_found"


def test_fuzzy_typo():
    """RESOLVE-01f: Typo 'Cese' fuzzy-matches to 'Cease, Dylan'."""
    r = resolve("Cese")
    assert r.match_type == "fuzzy"
    assert r.pitcher_name is not None
    assert "Cease" in r.pitcher_name


def test_suffix_handling():
    """RESOLVE-01g: 'Mark Leiter' matches 'Leiter Jr., Mark'."""
    r = resolve("Mark Leiter")
    assert r.pitcher_id is not None
    assert r.pitcher_name is not None
    assert "Leiter" in r.pitcher_name


def test_disambiguation_list():
    """RESOLVE-02a: Ambiguous 'Johnson' returns ranked disambiguation list."""
    r = resolve("Johnson")
    assert r.match_type == "ambiguous"
    assert len(r.candidates) > 1
    assert r.pitcher_id is None


def test_max_candidates():
    """RESOLVE-02b: Disambiguation list has at most 5 entries."""
    r = resolve("Johnson")
    assert len(r.candidates) <= 5


def test_not_found():
    """RESOLVE-02c: Unknown name returns not_found with empty candidates."""
    r = resolve("Zzzznotapitcher")
    assert r.match_type == "not_found"
    assert r.pitcher_id is None
    assert r.pitcher_name is None
    assert r.candidates == []


def test_disambiguation_deterministic():
    """RESOLVE-02: Two calls to resolve return identical candidate lists."""
    r1 = resolve("Rodriguez")
    r2 = resolve("Rodriguez")
    assert r1.candidates == r2.candidates
    assert r1.match_type == r2.match_type


def test_resolve_result_fields():
    """Verify ResolveResult has all four fields and is constructable."""
    r = ResolveResult(
        pitcher_id=1,
        pitcher_name="Test, Player",
        candidates=[],
        match_type="exact",
    )
    assert r.pitcher_id == 1
    assert r.pitcher_name == "Test, Player"
    assert r.candidates == []
    assert r.match_type == "exact"
