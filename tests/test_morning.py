"""Tests for morning-run orchestration: artifacts, quiet days."""

import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock

from pydantic_ai.models.test import TestModel

from pitcher_narratives import morning
from pitcher_narratives.models import AnalyzedContext, SpecialistOutputs
from pitcher_narratives.scout import ScoredAppearance, Signal


def _fake_analyzed() -> AnalyzedContext:
    """Minimal AnalyzedContext for test stubs."""
    return AnalyzedContext(
        specialists=SpecialistOutputs(
            stuff="Stuff analysis.", location="Location analysis.",
            runvalue="Run value analysis.", trends="Trends analysis.",
            game_shape="Game shape analysis.",
        ),
    )


def _app(pid: int, role: str) -> ScoredAppearance:
    return ScoredAppearance(
        pitcher_id=pid, pitcher_name=f"Pitcher {pid}", throws="R",
        game_date=date(2026, 6, 10), game_pk=1, n_pitches=80, score=5.0,
        role=role,
        signals=[Signal("velo_delta", 3.0, "+2.1 mph vs season")],
    )


def _make_minimal_context():
    """Build a minimal PitcherContext suitable for morning-run unit tests."""
    from pitcher_narratives.context import PitcherContext
    from pitcher_narratives.engine import (
        FirstPitchWeaponry,
        HardHitRate,
        PlatoonMix,
        ReleasePointMetrics,
        TemporalContext,
        WorkloadContext,
    )

    return PitcherContext(
        pitcher_name="Pitcher", pitcher_id=0, throws="R", role="SP",
        fastball=None, velocity_arc=None, arsenal=[],
        platoon_mix=PlatoonMix(splits=[], cold_start=True),
        first_pitch=FirstPitchWeaponry(
            entries=[], total_first_pitches_season=0,
            total_first_pitches_window=0, cold_start=True,
        ),
        execution=[], intermediates=[], attributions=[],
        hard_hit_rate=HardHitRate(
            hard_hit_pct=0, season_hard_hit_pct=0, delta="Steady",
            n_batted_balls=0, n_hard_hit=0, small_sample=True, cold_start=True,
        ),
        release_point=ReleasePointMetrics(pitch_types=[], cold_start=True),
        workload=WorkloadContext(appearances=[], max_consecutive_days=0, workload_concern=False),
        temporal=TemporalContext(
            analysis_date=date(2026, 6, 10), current_season=2026,
            current_season_appearances=10, current_season_ip="20.0",
            current_season_first_date="2026-03-28",
            prior_season=2025, prior_season_appearances=0, prior_season_ip="0.0",
            prior_year_relevance="LOW", prior_year_relevance_reason="No data",
        ),
        tto=None, cross_season_summary=None, arsenal_trend=None,
    )


def _patch_data(monkeypatch, *, patch_spine: bool = True):
    """Stub all data-loading and LLM seams in morning.py.

    patch_spine=True (default) replaces run_analysis_spine with a synchronous
    stub returning a fake AnalyzedContext. Tests that specifically exercise the
    spine integration should pass patch_spine=False and configure _writer_override
    with call_tools=[] to avoid SkillNotFoundError from the skill toolset.
    """
    monkeypatch.setattr(
        morning, "scout_appearances",
        lambda **kw: [_app(1, "SP"), _app(2, "RP")],
    )
    monkeypatch.setattr(morning, "_load_pitcher_context", lambda pid: _make_minimal_context())
    if patch_spine:
        monkeypatch.setattr(morning, "run_analysis_spine", AsyncMock(return_value=_fake_analyzed()))


def _selector_model():
    return TestModel(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
            {
                "pitcher_id": 2, "category": "red_flag",
                "angle": "Suspicious spike", "conviction": "low",
                "conviction_reason": "Single game.",
            },
        ],
    })


def test_run_morning_writes_all_artifacts(tmp_path, monkeypatch):
    _patch_data(monkeypatch)
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(call_tools=[]),
    )
    assert run_dir == tmp_path / "2026-06-10"
    digest = (run_dir / "digest.md").read_text()
    assert digest.startswith("# Morning Digest — 2026-06-10")
    assert "success (no tool calls)" in digest  # TestModel-generated recap narrative
    assert "## The Full Board" in digest
    assert "Run cost" in digest

    slate = json.loads((run_dir / "slate.json").read_text())
    assert slate["game_date"] == "2026-06-10"
    assert slate["picks"][0]["pitcher_id"] == 1
    assert slate["names"]["1"] == "Pitcher 1"

    assert "CANDIDATES" in (run_dir / "briefing.md").read_text()
    usage = json.loads((run_dir / "usage.json").read_text())
    assert any(rec["stage"] == "selector" for rec in usage)

    assert (run_dir / "validation.json").exists()
    validation = json.loads((run_dir / "validation.json").read_text())
    assert "picks" in validation


def test_run_morning_starters_only_filters_board(tmp_path, monkeypatch):
    """starters_only drops relievers before selection: the RP appearance never
    reaches candidates, the board, or the digest."""
    _patch_data(monkeypatch)  # yields SP pitcher 1 and RP pitcher 2
    starters_selector = TestModel(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
        ],
    })
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        starters_only=True,
        _selector_override=starters_selector,
        _writer_override=TestModel(call_tools=[]),
    )
    digest = (run_dir / "digest.md").read_text()
    assert "Pitcher 1" in digest
    assert "Pitcher 2" not in digest  # RP filtered out everywhere
    briefing = (run_dir / "briefing.md").read_text()
    assert "Pitcher 2" not in briefing  # RP excluded from selector candidates


def test_run_morning_starters_only_quiet_when_no_starters(tmp_path, monkeypatch):
    """A board of only relievers under starters_only is a quiet day (no run dir)."""
    monkeypatch.setattr(
        morning, "scout_appearances", lambda **kw: [_app(2, "RP"), _app(3, "RP")],
    )
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        starters_only=True,
        _selector_override=_selector_model(),
        _writer_override=TestModel(call_tools=[]),
    )
    assert run_dir is None


def test_run_morning_single_event_loop(tmp_path, monkeypatch):
    """Selector and writers share one event loop: provider-client state
    created during selection must not leak into a second loop (observed
    live: the first writer call failed with 'Event bound to a different
    event loop' and the top pick always fell back)."""
    import asyncio

    loops: list = []

    class _LoopRecorder(TestModel):
        async def request(self, messages, model_settings, model_request_parameters):
            loops.append(asyncio.get_running_loop())
            return await super().request(
                messages, model_settings, model_request_parameters
            )

    selector = _LoopRecorder(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
        ],
    })
    writer = _LoopRecorder(call_tools=[], custom_output_text="A summary.")

    _patch_data(monkeypatch)
    morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=selector, _writer_override=writer,
    )
    assert len(loops) >= 2
    assert all(lp is loops[0] for lp in loops)


def test_run_morning_drops_picks_when_recap_render_fails(tmp_path, monkeypatch):
    """A failing writer/render call drops the pick entirely (surfaced in the
    dropped-picks footer), rather than shipping FALLBACK_MARKER text.

    Behavior change (P8B Task 3): render_recap is folded into _build_pick,
    whose existing try/except drops the pick on any exception. There is no
    fallback-summary path any more for render failures — write_pick_summaries
    (and its FALLBACK_MARKER) are retired from the morning flow.
    """

    class _ExplodingWriter(TestModel):
        async def request(self, messages, model_settings, model_request_parameters):
            raise RuntimeError("provider error")

    _patch_data(monkeypatch)
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=_ExplodingWriter(),
    )
    digest = (run_dir / "digest.md").read_text()
    assert "analysis unavailable for" in digest
    assert "Pitcher 1" in digest[digest.index("analysis unavailable for"):]
    assert "Pitcher 2" in digest[digest.index("analysis unavailable for"):]


def test_run_morning_quiet_day_returns_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(morning, "scout_appearances", lambda **kw: [])
    result = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
    )
    assert result is None
    assert not list(tmp_path.iterdir())


def test_full_board_lists_beyond_candidate_cap(tmp_path, monkeypatch):
    """The Full Board shows every scored appearance even when the
    selector only sees the top N per role."""
    apps = [_app(1, "SP")] + [
        ScoredAppearance(
            pitcher_id=pid, pitcher_name=f"Pitcher {pid}", throws="R",
            game_date=date(2026, 6, 10), game_pk=pid, n_pitches=40,
            score=float(5 - pid), role="SP",
            signals=[Signal("velo_delta", 3.0, "+1.6 mph vs season")],
        )
        for pid in range(2, 5)
    ]
    monkeypatch.setattr(morning, "scout_appearances", lambda **kw: apps)
    monkeypatch.setattr(morning, "_load_pitcher_context", lambda pid: _make_minimal_context())
    monkeypatch.setattr(morning, "run_analysis_spine", AsyncMock(return_value=_fake_analyzed()))
    selector = TestModel(custom_output_args={
        "picks": [
            {
                "pitcher_id": 1, "category": "clean_breakout",
                "angle": "Velo spike", "conviction": "medium",
                "conviction_reason": "Shape agrees.",
            },
        ],
    })
    run_dir = morning.run_morning(
        window_days=1, top_n=1, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=selector,
        _writer_override=TestModel(call_tools=[]),
    )
    digest = (run_dir / "digest.md").read_text()
    board = digest[digest.index("## The Full Board"):]
    for pid in range(1, 5):
        assert f"Pitcher {pid}" in board       # all scored, not just top_n=1
    briefing = (run_dir / "briefing.md").read_text()
    assert "Pitcher 4" not in briefing          # selector saw only the cap


def test_morning_renders_recap_from_real_spine(tmp_path, monkeypatch):
    """Morning runs the real analysis spine, then renders each pick through
    render_recap (replaces the retired build_story_cue_from_context +
    write_pick_summaries path)."""
    captured: dict = {}
    from pitcher_narratives import pipeline as _pl
    _real_render_recap = _pl.render_recap

    async def _spy_render_recap(ctx, analyzed, *, agents, pick=None, **kw):
        captured.setdefault("analyzed", []).append(analyzed)
        return await _real_render_recap(ctx, analyzed, agents=agents, pick=pick, **kw)

    # patch_spine=False: let run_analysis_spine run for real under TestModel.
    # call_tools=[] suppresses the automatic skill-toolset calls TestModel generates.
    _patch_data(monkeypatch, patch_spine=False)
    monkeypatch.setattr(morning, "render_recap", _spy_render_recap)
    model = TestModel(call_tools=[])
    morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=model,
    )
    assert len(captured.get("analyzed", [])) > 0
    for analyzed in captured["analyzed"]:
        assert isinstance(analyzed, AnalyzedContext)
        assert analyzed.specialists.stuff != ""


def test_run_morning_duplicate_pitcher_keeps_highest_scored(tmp_path, monkeypatch):
    """A pitcher with two scored appearances keys to the higher-scored one."""
    high = _app(1, "SP")
    low = ScoredAppearance(
        pitcher_id=1, pitcher_name="Pitcher 1", throws="R",
        game_date=date(2026, 6, 9), game_pk=2, n_pitches=30, score=2.0,
        role="SP",
        signals=[Signal("workload_flag", 1.0, "2 consecutive days")],
    )
    monkeypatch.setattr(
        morning, "scout_appearances",
        lambda **kw: [high, low, _app(2, "RP")],
    )
    monkeypatch.setattr(morning, "_load_pitcher_context", lambda pid: _make_minimal_context())
    monkeypatch.setattr(morning, "run_analysis_spine", AsyncMock(return_value=_fake_analyzed()))
    run_dir = morning.run_morning(
        window_days=2, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(call_tools=[]),
    )
    briefing = (run_dir / "briefing.md").read_text()
    assert "80 pitches" in briefing            # high-scored appearance present
    digest = (run_dir / "digest.md").read_text()
    assert run_dir == tmp_path / "2026-06-10"  # game date = max date


def test_spine_failure_drops_pick_and_discloses_in_footer(tmp_path, monkeypatch):
    """When the spine fails for one pitcher, that pick is absent from the digest
    body but named in the footer disclosure; the surviving pick renders normally."""
    def _context_or_raise(pid):
        if pid == 1:
            raise RuntimeError("simulated context failure for pitcher 1")
        return _make_minimal_context()

    monkeypatch.setattr(morning, "scout_appearances", lambda **kw: [_app(1, "SP"), _app(2, "RP")])
    monkeypatch.setattr(morning, "_load_pitcher_context", _context_or_raise)
    monkeypatch.setattr(morning, "run_analysis_spine", AsyncMock(return_value=_fake_analyzed()))

    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(call_tools=[]),
    )
    assert run_dir is not None
    digest = (run_dir / "digest.md").read_text()

    # Surviving pick renders; failed pick is absent from body sections.
    assert "Pitcher 2" in digest
    body_end = digest.index("## The Full Board")
    body = digest[:body_end]
    assert "Pitcher 1" not in body

    # Footer discloses the dropped pick by name.
    assert "analysis unavailable for" in digest
    assert "Pitcher 1" in digest[digest.index("analysis unavailable for"):]


def test_semaphore_bounds_concurrency(tmp_path, monkeypatch):
    """The spine semaphore limits peak concurrent _build_pick executions."""
    max_concurrency = 2
    peak: list[int] = [0]
    current: list[int] = [0]

    async def _counting_spine(ctx, *, agents, _model_override=None):
        current[0] += 1
        peak[0] = max(peak[0], current[0])
        await asyncio.sleep(0)  # yield so all coroutines can enter if uncapped
        current[0] -= 1
        return _fake_analyzed()

    # Use 4 picks to ensure concurrency pressure.
    apps = [_app(pid, "SP") for pid in range(1, 5)]
    monkeypatch.setattr(morning, "scout_appearances", lambda **kw: apps)
    monkeypatch.setattr(morning, "_load_pitcher_context", lambda pid: _make_minimal_context())
    monkeypatch.setattr(morning, "run_analysis_spine", _counting_spine)

    selector = TestModel(custom_output_args={
        "picks": [
            {"pitcher_id": pid, "category": "clean_breakout",
             "angle": "Velo spike", "conviction": "medium",
             "conviction_reason": "Shape agrees."}
            for pid in range(1, 5)
        ],
    })

    morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        max_concurrency=max_concurrency,
        _selector_override=selector,
        _writer_override=TestModel(call_tools=[]),
    )
    assert peak[0] <= max_concurrency, f"peak concurrency {peak[0]} exceeded cap {max_concurrency}"


def test_signals_failed_flag_set_on_extractor_failure(monkeypatch):
    """AnalyzedContext.signals_failed=True when signal extractor raises.

    Tested directly against run_analysis_spine (no full morning stack needed)
    by monkeypatching the two internal async helpers so only the extractor path
    is live. The extractor mock raises, which should set signals_failed=True.
    """
    import asyncio
    import unittest.mock
    import pitcher_narratives.pipeline as _pl
    from pitcher_narratives.pipeline import run_analysis_spine
    from pitcher_narratives.models import SpecialistOutputs

    fake_specs = SpecialistOutputs(
        stuff="S", location="L", runvalue="R", trends="T", game_shape="G"
    )
    monkeypatch.setattr(_pl, "run_specialists", AsyncMock(return_value=fake_specs))
    monkeypatch.setattr(
        _pl, "audit_and_revise_specialists",
        AsyncMock(return_value=(fake_specs, [], set())),
    )
    monkeypatch.setattr(_pl, "build_writer_input", lambda *a, **kw: "")

    bad_extractor = unittest.mock.MagicMock()
    bad_extractor.run = AsyncMock(side_effect=RuntimeError("extractor down"))
    _noop = unittest.mock.MagicMock()

    class _FakeAgents:
        # Specialist/auditor attrs are passed as args to monkeypatched helpers;
        # they must exist but are never actually called.
        stuff = location = runvalue = trends = game_shape = auditor = _noop
        signal_extractor = bad_extractor
        mini_model_name = ""
        def specialist_dict(self):
            return {}

    result = asyncio.run(run_analysis_spine(_make_minimal_context(), agents=_FakeAgents()))
    assert result.signals_failed is True
    assert result.key_signals is None


def test_morning_marks_unverified_recap_items(tmp_path, monkeypatch):
    """Under TestModel the capsule auditor emits synthetic residual flags
    (same mechanism as test_cli_unverified_banner_on_residual_flags in
    test_cli.py); morning must mark such digest items UNVERIFIED rather than
    ship a flagged recap unmarked."""
    _patch_data(monkeypatch)
    run_dir = morning.run_morning(
        window_days=1, top_n=2, min_pitches=1,
        provider="gemini", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(call_tools=[]),
    )
    assert run_dir is not None
    digest = (run_dir / "digest.md").read_text()
    assert "UNVERIFIED" in digest


def test_render_recap_threads_pick_angle_into_writer_input():
    """P8B-M1: the editorial overlay (pick.angle) built for a CurationPick
    must reach the writer's input, so a morning digest item leads with the
    editor's angle rather than the analyses' own default thread."""
    from pitcher_narratives import pipeline as _pl
    from pitcher_narratives.curator import CurationPick
    from pitcher_narratives.personas import RECAP

    agents = _pl.make_pipeline_agents("gemini", "medium", RECAP)
    ctx = _make_minimal_context()
    analyzed = _fake_analyzed()
    pick = CurationPick(
        pitcher_id=0, category="clean_breakout",
        angle="A very distinctive angle marker XYZ123",
        conviction="medium", conviction_reason="Shape agrees.",
    )

    captured: dict = {}
    _real_render_capsule = _pl._render_capsule

    async def _spy_render_capsule(*args, overlay=None, **kwargs):
        captured["overlay"] = overlay
        return await _real_render_capsule(*args, overlay=overlay, **kwargs)

    import unittest.mock as _mock
    with _mock.patch.object(_pl, "_render_capsule", _spy_render_capsule):
        asyncio.run(_pl.render_recap(
            ctx, analyzed, agents=agents, pick=pick,
            _model_override=TestModel(call_tools=[]),
        ))

    assert captured["overlay"] is not None
    assert "A very distinctive angle marker XYZ123" in captured["overlay"]


def test_morning_emits_recap_capsule_per_selected_pitcher(tmp_path, monkeypatch):
    """Morning runs the shared spine and yields a recap-shaped capsule per pick.

    Regression guard for spec §4/§8 phase 4: morning already wires each
    selected pitcher through render_recap (RECAP mode), whose capsule skips
    distillation (no executive-summary bullets) and produces a non-empty
    narrative. This test locks that shape in.
    """
    from pitcher_narratives import pipeline as _pl

    captured: list = []
    _real_render_recap = _pl.render_recap

    async def _spy_render_recap(ctx, analyzed, *, agents, pick=None, **kw):
        result = await _real_render_recap(ctx, analyzed, agents=agents, pick=pick, **kw)
        captured.append(result)
        return result

    _patch_data(monkeypatch)
    monkeypatch.setattr(morning, "render_recap", _spy_render_recap)
    run_dir = morning.run_morning(
        window_days=1, top_n=25, min_pitches=20,
        provider="gemini", out_root=tmp_path,
        _selector_override=_selector_model(),
        _writer_override=TestModel(call_tools=[]),
    )
    assert run_dir is not None

    # _selector_model() picks pitcher_id 1 and 2 -> one recap capsule each.
    assert len(captured) == 2
    for result in captured:
        assert result.narrative  # non-empty narrative
        assert result.executive_summary == []  # RECAP mode skips distill: no exec bullets


def test_build_validation_payload_records_flags_per_pick():
    """The validation.json payload carries one flag_record per surviving pick."""
    from pitcher_narratives.models import SpecialistOutputs
    from pitcher_narratives.morning import _build_validation_payload
    from pitcher_narratives.pipeline import PipelineResult

    result = PipelineResult(
        narrative="n",
        specialists=SpecialistOutputs(
            stuff="s", location="l", runvalue="r", trends="t", game_shape="g"),
        revision_count=1,
        capsule_revised=True,
    )
    payload = _build_validation_payload("2026-07-03", {592155: result})
    assert payload["game_date"] == "2026-07-03"
    rec = payload["picks"]["592155"]
    assert rec["mode"] == "recap"
    assert rec["pitcher_id"] == 592155
    assert rec["revision_count"] == 1
    assert rec["capsule_revised"] is True
    assert rec["anchor_depth_cap"] == 1
    assert rec["fact_depth_cap"] == 2
