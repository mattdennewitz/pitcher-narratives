def test_core_context_holds_four_specialists_and_flags():
    from pitcher_narratives.models import (
        AuditFlag,
        CoreContext,
        empty_specialist_analysis,
    )

    analysis = empty_specialist_analysis()
    core = CoreContext(
        stuff=analysis,
        location=analysis,
        runvalue=analysis,
        audit_flags=[
            AuditFlag(category="X", specialist="stuff", claim="c", data_shows="d", suggested_fix="f")
        ],
    )
    assert core.stuff is analysis
    assert len(core.audit_flags) == 1
    # Defaults to empty flag list.
    assert CoreContext(stuff=analysis, location=analysis, runvalue=analysis).audit_flags == []
    # Frame-sensitive fields are intentionally absent.
    assert not hasattr(
        CoreContext(stuff=analysis, location=analysis, runvalue=analysis),
        "trends",
    )


def test_analyzed_context_frame_comparison_defaults_none():
    from pitcher_narratives.models import (
        AnalyzedContext,
        SpecialistOutputs,
        empty_specialist_analysis,
    )

    analysis = empty_specialist_analysis()
    ac = AnalyzedContext(
        specialists=SpecialistOutputs(
            stuff=analysis,
            location=analysis,
            runvalue=analysis,
            trends=analysis,
        ),
    )
    assert ac.trend_frame_comparison is None
