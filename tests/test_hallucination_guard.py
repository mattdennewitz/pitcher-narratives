"""Hallucination guard tests — relocated from test_report.py.

Tests for check_hallucinated_metrics and HallucinationReport, now
imported from pipeline.py where the hallucination guard lives.
"""

import pytest

from pitcher_narratives.claims import AnalysisCapabilities
from pitcher_narratives.pipeline import HallucinationReport, check_hallucinated_metrics


def test_check_hallucinated_metrics_has_no_persona_param():
    """Task 3: check_hallucinated_metrics no longer accepts a persona kwarg."""
    import inspect

    assert "persona" not in inspect.signature(check_hallucinated_metrics).parameters


def test_tunneling_language_requires_capability_and_citation():
    text = "The tunneling gap tightened."

    unavailable = check_hallucinated_metrics(text)
    available_but_uncited = check_hallucinated_metrics(
        text,
        capabilities=AnalysisCapabilities(
            has_tunneling_measurement=True,
            evidence_fact_ids=(("tunneling_measurement", "fact:tunnel"),),
        ),
    )
    cited = check_hallucinated_metrics(
        text,
        capabilities=AnalysisCapabilities(
            has_tunneling_measurement=True,
            evidence_fact_ids=(("tunneling_measurement", "fact:tunnel"),),
        ),
        cited_fact_ids=("fact:tunnel",),
    )

    assert unavailable.unsupported_claim_warnings
    assert available_but_uncited.unsupported_claim_warnings
    assert cited.unsupported_claim_warnings == []


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


# -- Capability-gated causal-language regressions --


def test_causal_teaching_vocabulary_is_not_globally_allowlisted():
    text = "The slider's tunneling gap deceived hitters, and that mechanism drove the result."
    result = check_hallucinated_metrics(text)

    assert result.unsupported_claim_warnings
    assert not result.is_clean


def test_teaching_vocab_does_not_suppress_real_unknowns():
    """The teaching-vocab allowlist only covers its own terms, not fabricated metrics."""
    text = "His xDominance score and playability are both impressive."
    result = check_hallucinated_metrics(text)
    assert "xDominance" in result.unknown_metrics
    assert not result.is_clean


def test_generic_capsule_rejects_driver_and_command_inference():
    text = (
        "## Stuff\nThe model credited vertical break for S+ 112.\n\n"
        "## Location\nFastball L+ 94 shows that command slipped.\n"
    )
    result = check_hallucinated_metrics(text)

    assert result.unsupported_claim_warnings
    assert not result.is_clean


def test_rarity_tag_cannot_supply_importance():
    result = check_hallucinated_metrics("Velocity was OUTLIER, so it was the important model driver.")

    assert result.unsupported_claim_warnings
    assert not result.is_clean


def test_explicit_model_driver_limitation_is_not_a_claim():
    result = check_hallucinated_metrics("The supplied aggregate profile does not identify the model driver.")

    assert result.unsupported_claim_warnings == []


def test_generic_table_row_invented_metric_flagged():
    """Invented metric inside a table row is still caught."""
    text = (
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        "| Top Improvement | xDominance score up on slider | xDominance 128 |\n"
    )
    result = check_hallucinated_metrics(text)
    assert "xDominance" in result.unknown_metrics
    assert not result.is_clean


def test_generic_fabricated_section_metric_flagged():
    """Invented metric inside a section (not table) is still caught."""
    text = "## Stuff\nHis xFakeMetric of 95 is notable."
    result = check_hallucinated_metrics(text)
    assert "xFakeMetric" in result.unknown_metrics
    assert not result.is_clean
