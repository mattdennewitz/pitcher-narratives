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


def test_hallucination_guard_variant_suffix_metrics_known():
    """Stuff/Pitch-side variants (xRV100_S, xRV100_P, xWhiff_S) are not flagged.

    The specialist and writer prompts teach paired _S/_P variants of base
    metrics. The known-metrics allowlist holds only the bare base (xRV100,
    xWhiff); the guard strips a trailing _S/_P before testing membership so
    these legitimate variants pass clean (regression for the live false
    positive "Unknown metrics referenced: xRV100_S").
    """
    text = (
        "S+ below 100 with xRV100_S of +1.4 confirms the slider bleeds runs, "
        "while xRV100_P sits at -0.8 and xWhiff_S holds at 0.30."
    )
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert result.is_clean


def test_hallucination_guard_unknown_base_with_variant_suffix_flagged():
    """A variant suffix on an unknown base is still flagged, with the original token.

    Stripping _S/_P only forgives variants whose base is known. An invented
    base (xBogus) must remain flagged, and the reported token keeps its
    original spelling rather than the normalized form.
    """
    result = check_hallucinated_metrics("His xBogus_S of 9.9 is off the charts.")
    assert "xBogus_S" in result.unknown_metrics
    assert "xBogus" not in result.unknown_metrics


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


def test_hallucination_guard_workload_ip_not_flagged():
    """Bare 'IP' in a workload line (e.g. '5.2 IP') is not a false-positive
    traditional-stat flag."""
    text = "He went 5.2 IP over 89 pitches, his longest outing of the year."
    result = check_hallucinated_metrics(text)
    assert "IP" not in result.outcome_stat_warnings
    assert result.is_clean


def test_hallucination_guard_other_traditional_stats_still_flagged():
    """Dropping IP from the pattern must not affect ERA/WHIP/W-L detection."""
    text = "ERA of 3.50, WHIP of 1.20, and a W-L of 12-8."
    result = check_hallucinated_metrics(text)
    assert "ERA" in result.outcome_stat_warnings
    assert "WHIP" in result.outcome_stat_warnings
    assert "W-L" in result.outcome_stat_warnings


# -- Per-persona regression vectors (Phase 07: TEST-07, analyst portion) --


def test_analyst_vocab_not_flagged_with_persona():
    """TEST-07: Analyst vocabulary terms are not flagged when persona='analyst'."""
    text = (
        "The playability of this slider comes down to the tunneling gap "
        "created by his pitch tree. The arsenal depth gives him four "
        "viable options."
    )
    result = check_hallucinated_metrics(text, persona="analyst")
    assert result.is_clean, (
        f"Analyst vocabulary flagged with persona='analyst': "
        f"unknown={result.unknown_metrics}, warnings={result.outcome_stat_warnings}"
    )


def test_analyst_vocab_without_persona_still_clean():
    """TEST-07: Analyst vocabulary terms don't match _METRIC_PATTERN anyway.

    This confirms the terms are plain English that the regex does not catch.
    The per-persona allowlist is a safety net for forward compatibility.
    """
    text = (
        "The playability and tunneling gap are key. "
        "His pitch tree and arsenal depth look solid."
    )
    result = check_hallucinated_metrics(text)
    assert result.is_clean, (
        f"Analyst vocabulary flagged without persona: "
        f"unknown={result.unknown_metrics}"
    )


def test_analyst_persona_does_not_suppress_real_unknowns():
    """TEST-07: Per-persona allowlist only covers persona vocabulary, not fabricated metrics."""
    text = "His xDominance score and playability are both impressive."
    result = check_hallucinated_metrics(text, persona="analyst")
    assert "xDominance" in result.unknown_metrics
    assert not result.is_clean


def test_no_persona_backward_compat():
    """PERSONA-10: Calls without persona arg produce identical results to v1.9 behavior."""
    text = "His P+ of 112 and xWhiff of 0.35 suggest elite stuff. ERA of 3.50."
    result = check_hallucinated_metrics(text)
    assert result.unknown_metrics == []
    assert "ERA" in result.outcome_stat_warnings
    assert not result.is_clean


# ── Per-persona regression vectors (Phase 08: TEST-07, generic portion) ──


def test_generic_persona_key_in_allowlist():
    """PERSONA-10 (generic): _PERSONA_KNOWN_METRICS has a 'generic' frozenset entry."""
    from pitcher_narratives.pipeline import _PERSONA_KNOWN_METRICS
    assert "generic" in _PERSONA_KNOWN_METRICS
    assert isinstance(_PERSONA_KNOWN_METRICS["generic"], frozenset)


def test_generic_synthetic_capsule_clean():
    """TEST-07 (generic): synthetic generic capsule (sections + table) passes clean."""
    text = (
        "## Stuff\nThe slider graded S+ 112; the model credited vertical break.\n\n"
        "## Location\nFastball L+ 94 below league average.\n\n"
        "## Run Value & Execution\nxRV100 of -0.5 shows the arsenal saves runs.\n\n"
        "## Trend\nVelocity stable; Pitching+ up 4 points.\n\n"
        "## Game Shape\nThird-time-through gap manageable.\n\n"
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        "| Top Improvement | Slider vertical break gain | S+ 112 |\n"
        "| Top Concern | Fastball command slipped | L+ 94 |\n"
    )
    result = check_hallucinated_metrics(text, persona="generic")
    assert result.is_clean, (
        f"Generic synthetic capsule flagged: "
        f"unknown={result.unknown_metrics}, warnings={result.outcome_stat_warnings}"
    )


def test_generic_table_row_invented_metric_flagged():
    """TEST-07 (generic): invented metric inside a table row is still caught."""
    text = (
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        "| Top Improvement | xDominance score up on slider | xDominance 128 |\n"
    )
    result = check_hallucinated_metrics(text, persona="generic")
    assert "xDominance" in result.unknown_metrics
    assert not result.is_clean


def test_generic_fabricated_section_metric_flagged():
    """TEST-07 (generic): invented metric inside a section (not table) is still caught."""
    text = "## Stuff\nHis xFakeMetric of 95 is notable."
    result = check_hallucinated_metrics(text, persona="generic")
    assert "xFakeMetric" in result.unknown_metrics
    assert not result.is_clean


def test_generic_persona_does_not_suppress_real_unknowns():
    """TEST-07 (generic): per-persona allowlist only covers generic vocab, not fabricated metrics."""
    text = "## Stuff\nHis xMadeUpMetric score is 95 and S+ is 110."
    result = check_hallucinated_metrics(text, persona="generic")
    assert "xMadeUpMetric" in result.unknown_metrics
    assert not result.is_clean


def test_persona_known_metrics_keys_are_registered_personas():
    """Every key in _PERSONA_KNOWN_METRICS must be a valid persona id.

    Catches typos like 'analsyt' vs 'analyst' that would silently disable
    the per-persona allowlist for the real persona.
    """
    from pitcher_narratives.personas import PERSONAS
    from pitcher_narratives.pipeline import _PERSONA_KNOWN_METRICS

    unknown_keys = set(_PERSONA_KNOWN_METRICS.keys()) - set(PERSONAS.keys())
    assert not unknown_keys, (
        f"_PERSONA_KNOWN_METRICS has keys not in PERSONAS: {unknown_keys}"
    )


def test_unknown_persona_logs_debug_and_returns_empty_allowlist(caplog):
    """Unknown persona id triggers a debug log and falls back to empty allowlist.

    Tests the graceful-miss path for programmatic callers (CLI is guarded
    by argparse choices). A typo should not crash — it should log and
    treat the persona as having no allowlist.
    """
    import logging

    with caplog.at_level(logging.DEBUG, logger="pitcher_narratives.pipeline"):
        result = check_hallucinated_metrics(
            "His P+ is 110.", persona="analsyt"
        )
    assert result.is_clean
    assert any(
        "no persona-specific metric allowlist" in rec.message
        and "analsyt" in rec.message
        for rec in caplog.records
    )
