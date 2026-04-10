"""Hallucination guard tests — relocated from test_report.py.

Tests for check_hallucinated_metrics and HallucinationReport, now
imported from pipeline.py where the hallucination guard lives.
"""

import pytest

from pitcher_narratives.pipeline import HallucinationReport, check_hallucinated_metrics


def test_check_hallucinated_metrics_rejects_empty_string():
    """Empty narrative is a pipeline failure, not a clean report."""
    with pytest.raises(ValueError, match="empty"):
        check_hallucinated_metrics("")


def test_check_hallucinated_metrics_rejects_non_string():
    """Non-string input raises TypeError with a clear message."""
    with pytest.raises(TypeError, match="must be str"):
        check_hallucinated_metrics(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be str"):
        check_hallucinated_metrics(42)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be str"):
        check_hallucinated_metrics(b"bytes not str")  # type: ignore[arg-type]


def test_hallucination_guard_clean():
    """Known metrics in output produce no warnings."""
    text = "His P+ of 112 and xWhiff of 0.35 suggest elite stuff. CSW% at 32%."
    result = check_hallucinated_metrics(text)
    assert isinstance(result, HallucinationReport)
    assert result.unknown_metrics == []
    assert result.outcome_stat_warnings == []
    assert result.is_clean


def test_hallucination_guard_catches_unknown():
    """Fabricated metrics are flagged."""
    text = "His xDominance score of 95 suggests elite stuff."
    result = check_hallucinated_metrics(text)
    assert isinstance(result, HallucinationReport)
    assert "xDominance" in result.unknown_metrics


def test_hallucination_guard_known_metrics():
    """All standard Pitching+ metrics pass without flags."""
    text = "S+ at 110, L+ at 105, xRV100 of -2.3, xGOr at 0.45."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_percentage_metrics():
    """CSW%, Zone%, Chase% are all known."""
    text = "CSW% of 32.1%, Zone% at 48%, Chase% near 30%."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_editorial_metrics():
    """Metrics used in editorial voice (K-BB%, SwStr%, xFIP) are known."""
    text = "K-BB% at 15%, SwStr% of 12%, xFIP near 3.50."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_plus_metrics_in_sentence():
    """P+ detected in natural sentence context (space after +)."""
    text = "His P+ of 112 was solid"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_plus_after_comma():
    """S+, L+ detected when followed by comma or space."""
    text = "S+, L+ both above 100"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_plus_at_end_of_string():
    """L+ detected at end of string."""
    text = "great L+"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_xwoba_matched():
    """xwOBA (lowercase w after x) is matched and recognized as known."""
    text = "xwOBA of .320"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_xera_known():
    """xERA recognized as known metric."""
    text = "xERA near 3.50"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_barrel_pct_known():
    """Barrel% recognized as known metric."""
    text = "Barrel% at 12%"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_traditional_stats_warned():
    """Traditional outcome stats flagged as outcome_stat_warnings, not unknown."""
    text = "ERA of 3.50 and WHIP of 1.20"
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert "ERA" in result.outcome_stat_warnings
    assert "WHIP" in result.outcome_stat_warnings
    assert not result.is_clean


def test_hallucination_guard_mixed_issues():
    """Text with fabricated metric AND traditional stat populates both lists."""
    text = "His xDominance of 95 and ERA of 3.50 are both notable."
    result = check_hallucinated_metrics(text)
    assert "xDominance" in result.unknown_metrics
    assert "ERA" in result.outcome_stat_warnings
    assert not result.is_clean


def test_hallucination_guard_is_clean_property():
    """is_clean True for clean text, False for dirty text."""
    clean = check_hallucinated_metrics("Nothing metric-like here.")
    assert clean.is_clean

    dirty = check_hallucinated_metrics("His xFakeMetric is off the charts.")
    assert not dirty.is_clean


def test_hallucination_guard_all_traditional_stats():
    """FIP, WAR, K%, BB%, HR/9 all flagged as outcome stat warnings."""
    text = "FIP at 3.20, WAR of 2.5, K% at 28%, BB% at 7%, HR/9 at 1.1."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    for stat in ["FIP", "WAR", "K%", "BB%", "HR/9"]:
        assert stat in result.outcome_stat_warnings, f"{stat} not in outcome_stat_warnings"


def test_hallucination_guard_xdominance_still_unknown():
    """xDominance still caught as unknown metric (regression check)."""
    text = "xDominance score was 95."
    result = check_hallucinated_metrics(text)
    assert "xDominance" in result.unknown_metrics


def test_hallucination_guard_hardhit_pct_still_known():
    """HardHit% still passes as known (regression check)."""
    text = "HardHit% at 42%."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean
