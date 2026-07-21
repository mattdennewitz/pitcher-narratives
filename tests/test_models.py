def test_core_context_holds_four_specialists_and_flags():
    from pitcher_narratives.models import CoreContext, AuditFlag

    core = CoreContext(
        stuff="s", location="l", runvalue="r",
        audit_flags=[AuditFlag(category="X", specialist="stuff",
                               claim="c", data_shows="d", suggested_fix="f")],
    )
    assert core.stuff == "s"
    assert len(core.audit_flags) == 1
    # Defaults to empty flag list.
    assert CoreContext(stuff="s", location="l", runvalue="r").audit_flags == []
    # Frame-sensitive fields are intentionally absent.
    assert not hasattr(CoreContext(stuff="s", location="l", runvalue="r"), "trends")


def test_analyzed_context_frame_comparison_defaults_none():
    from pitcher_narratives.models import AnalyzedContext, SpecialistOutputs

    ac = AnalyzedContext(
        specialists=SpecialistOutputs(
            stuff="s", location="l", runvalue="r", trends="t"
        ),
    )
    assert ac.trend_frame_comparison is None
