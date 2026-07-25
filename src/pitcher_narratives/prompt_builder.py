"""Prompt rendering for PitcherContext.

Renders an assembled PitcherContext into prompt-ready markdown (under
~2,000 tokens). Split out of context.py so the PitcherContext model stays
a focused data container. Each ``render_*_section`` is a pure function of
the context; ``build_pitcher_prompt`` orchestrates them in display order.
"""

from __future__ import annotations

from pitcher_narratives.context import _MAX_PITCH_TYPES, PitcherContext
from pitcher_narratives.shape import render_pitch_shape

__all__ = [
    "build_pitcher_prompt",
    "render_appearances_section",
    "render_arsenal_section",
    "render_calibration_section",
    "render_execution_section",
    "render_executive_summary",
    "render_fastball_section",
    "render_first_pitch_section",
    "render_hard_hit_section",
    "render_intermediates_section",
    "render_pitch_shape_section",
    "render_platoon_section",
    "render_release_point_section",
    "render_role_section",
    "render_temporal_section",
    "render_yoy_section",
]


def build_pitcher_prompt(ctx: PitcherContext) -> str:
    """Render the context as prompt-ready markdown under 2,000 tokens."""
    sections: list[str] = []
    sections.append(f"# {ctx.pitcher_name} ({ctx.throws}HP) -- Scouting Context")
    sections.append(render_temporal_section(ctx))
    sections.append(render_executive_summary(ctx))
    sections.append(render_role_section(ctx))
    sections.append(render_fastball_section(ctx))
    sections.append(render_arsenal_section(ctx))
    sections.append(render_execution_section(ctx))
    sections.append(render_intermediates_section(ctx))
    sections.append(render_calibration_section(ctx))
    sections.append(render_release_point_section(ctx))
    sections.append(render_pitch_shape_section(ctx))
    sections.append(render_hard_hit_section(ctx))
    sections.append(render_platoon_section(ctx))
    sections.append(render_first_pitch_section(ctx))
    sections.append(render_appearances_section(ctx))
    sections.append(render_yoy_section(ctx))
    return "\n\n".join(s for s in sections if s)


def render_calibration_section(
    ctx: PitcherContext,
    *,
    variants: tuple[str, ...] | None = None,
    families: tuple[str, ...] | None = None,
    include_table: bool = True,
) -> str:
    """Render held-out reliability evidence or explicit unavailability."""
    lines = ["## Model Validation and Uncertainty"]
    report = getattr(ctx, "calibration", None)
    if report is None:
        reason = (
            getattr(ctx, "calibration_unavailable_reason", None) or "no manifest-covered calibration artifact"
        )
        lines.append(f"- Calibration unavailable: {reason}.")
        lines.append(
            "- Treat predictive reliability as unknown; do not describe "
            "model grades as validated or confident."
        )
        return "\n".join(lines)

    metadata = report.metadata
    lines.append(
        f"- Held-out population: {metadata.scoring_population}; "
        f"temporal holdout {metadata.split_policy.temporal_holdout_year}; "
        f"as of {metadata.as_of}."
    )
    lines.append(
        f"- Split policy: {metadata.split_policy.validation}; learned "
        f"artifacts fit on {metadata.split_policy.learned_artifacts_fit_on}."
    )
    lines.append(
        "- These are population-level held-out diagnostics, not confidence intervals for this pitcher."
    )
    if not include_table:
        return "\n".join(lines)
    selected_models = {
        key: model_report
        for key, model_report in report.models.items()
        if (variants is None or key.split(".", maxsplit=1)[0] in variants)
        and (families is None or key.split(".", maxsplit=1)[1] in families)
    }
    lines.append("| Model | N | Log loss | Prior | Brier | ECE |")
    lines.append("|-------|---:|---------:|------:|------:|----:|")
    for model_key, model_report in sorted(selected_models.items()):
        metrics = model_report.overall
        lines.append(
            f"| {model_key} | {metrics.n_observations} | "
            f"{metrics.log_loss:.4f} | "
            f"{metrics.empirical_prior_log_loss:.4f} | "
            f"{metrics.brier_score:.4f} | "
            f"{metrics.expected_calibration_error:.4f} |"
        )
    return "\n".join(lines)


def render_temporal_section(ctx: PitcherContext) -> str:
    """Render only the exact recent canonical frame."""
    temporal = ctx.temporal
    return "\n".join(
        (
            "## Temporal Context",
            f"- Analysis date: {temporal.analysis_date}",
            (
                f"- Recent canonical frame ({temporal.scoring_season}): "
                f"{temporal.recent_frame_appearances} appearances, "
                f"{temporal.recent_frame_ip} IP from "
                f"{temporal.recent_frame_first_date} through "
                f"{temporal.analysis_date}"
            ),
        )
    )


def render_executive_summary(ctx: PitcherContext) -> str:
    """Build a bullet-point executive summary of key observations."""
    bullets: list[str] = []

    # Most recent appearance context
    wl = ctx.workload
    if wl.appearances:
        latest = max(wl.appearances, key=lambda a: a.game_date)
        bullets.append(
            f"Last outing: {latest.game_date} ({latest.ip} IP, {latest.pitch_count} pitches, {ctx.role})"
        )

    # Fastball velocity trend
    fb = ctx.fastball
    if fb and fb.velo_delta and fb.velo_delta != "--":
        bullets.append(f"Fastball velo: {fb.velo_delta} vs season")

    # Pitching+ triad trends
    if fb and fb.p_plus_delta and fb.p_plus_delta != "--":
        p_plus_parts = [f"P+ {fb.p_plus_delta}"]
        if fb.s_plus_delta and fb.s_plus_delta != "--":
            p_plus_parts.append(f"S+ {fb.s_plus_delta}")
        if fb.l_plus_delta and fb.l_plus_delta != "--":
            p_plus_parts.append(f"L+ {fb.l_plus_delta}")
        bullets.append(f"Fastball Pitching+: {', '.join(p_plus_parts)} vs season")

    # Biggest arsenal usage shift
    if ctx.arsenal:
        biggest_shift = max(
            ctx.arsenal,
            key=lambda p: (
                abs(p.window_usage_pct - p.season_usage_pct)
                if p.window_usage_pct is not None and p.season_usage_pct is not None
                else 0
            ),
        )
        if biggest_shift.window_usage_pct is not None and biggest_shift.season_usage_pct is not None:
            shift = biggest_shift.window_usage_pct - biggest_shift.season_usage_pct
            if abs(shift) >= 5.0:
                bullets.append(
                    f"Notable mix change: {biggest_shift.pitch_name} usage {shift:+.1f}pp vs season"
                )

    # Velocity arc from last outing
    va = ctx.velocity_arc
    if va and va.available and va.drop_string:
        bullets.append(f"Velocity arc: {va.drop_string}")

    # Hard-hit rate shift
    hhr = ctx.hard_hit_rate
    if (
        not hhr.cold_start
        and "Steady" not in hhr.delta
        and abs(hhr.hard_hit_pct - hhr.season_hard_hit_pct) >= 5.0
    ):
        bullets.append(f"Hard-hit rate: {hhr.delta} vs season ({hhr.hard_hit_pct:.1f}%)")

    # Workload concern
    if wl.workload_concern:
        bullets.append("**Workload flag: 3+ consecutive days pitched**")

    if not bullets:
        return ""

    lines = ["## Executive Summary"]
    for b in bullets:
        lines.append(f"- {b}")
    return "\n".join(lines)


def render_role_section(ctx: PitcherContext) -> str:
    lines = ["## Role"]
    lines.append(f"- Most recent: {ctx.role}")
    wl = ctx.workload
    lines.append(f"- Appearances: {len(wl.appearances)}")
    if wl.max_consecutive_days >= 2:
        lines.append(f"- Max consecutive days: {wl.max_consecutive_days}")
    if wl.workload_concern:
        lines.append("- **Workload concern: 3+ consecutive days**")
    return "\n".join(lines)


def render_fastball_section(ctx: PitcherContext) -> str:
    fb = ctx.fastball
    if fb is None:
        return "## Primary Fastball\n- No standard fastball identified"

    lines = [f"## Primary Fastball: {fb.pitch_name} ({fb.pitch_type})"]
    if fb.window_empty:
        lines.append(f"- {fb.pitch_name} ({fb.pitch_type}): No data for this frame")
        return "\n".join(lines)
    lines.append(f"- Velo: {fb.season_velo:.1f} season / {fb.window_velo:.1f} recent -- {fb.velo_delta}")
    # Pitching+ triad: P+ (overall), S+ (stuff), L+ (location)
    if fb.window_p_plus is not None:
        lines.append(
            f"- Pitching+ (P+): {fb.season_p_plus:.0f} season / "
            f"{fb.window_p_plus:.0f} recent -- {fb.p_plus_delta}"
        )
    else:
        lines.append(f"- Pitching+ (P+): {fb.season_p_plus:.0f} season -- {fb.p_plus_delta}")
    if fb.window_s_plus is not None:
        lines.append(
            f"- Stuff+ (S+): {fb.season_s_plus:.0f} season / "
            f"{fb.window_s_plus:.0f} recent -- {fb.s_plus_delta}"
        )
    else:
        lines.append(f"- Stuff+ (S+): {fb.season_s_plus:.0f} season -- {fb.s_plus_delta}")
    if fb.window_l_plus is not None:
        lines.append(
            f"- Location+ (L+): {fb.season_l_plus:.0f} season / "
            f"{fb.window_l_plus:.0f} recent -- {fb.l_plus_delta}"
        )
    else:
        lines.append(f"- Location+ (L+): {fb.season_l_plus:.0f} season -- {fb.l_plus_delta}")
    lines.append(f"- Movement: H {fb.pfx_x_delta}, V {fb.pfx_z_delta}")

    # Velocity arc from last outing
    va = ctx.velocity_arc
    if va is not None and va.available:
        lines.append(f"- Velocity arc (last outing): {va.drop_string}")
    elif va is not None:
        lines.append(f"- Velocity arc: {va.drop_string}")

    if fb.small_sample:
        lines.append("- *Small sample*")
    return "\n".join(lines)


def render_arsenal_section(ctx: PitcherContext) -> str:
    lines = ["## Arsenal"]
    lines.append("| Pitch | Velo | H-mov | V-mov | Usage | P+ | S+ | L+ | Deltas |")
    lines.append("|-------|------|-------|-------|-------|----|----|----|---------  |")
    for p in ctx.arsenal[:_MAX_PITCH_TYPES]:
        wp = f"{p.window_p_plus:.0f}" if p.window_p_plus is not None else "--"
        ws = f"{p.window_s_plus:.0f}" if p.window_s_plus is not None else "--"
        wl = f"{p.window_l_plus:.0f}" if p.window_l_plus is not None else "--"
        lines.append(
            f"| {p.pitch_name} ({p.pitch_type}) "
            f"| {p.window_velo:.1f} "
            f"| {p.window_pfx_x:.1f} "
            f"| {p.window_pfx_z:.1f} "
            f"| {p.window_usage_pct:.1f}% "
            f"| {wp} "
            f"| {ws} "
            f"| {wl} "
            f"| P+ {p.p_plus_delta}, S+ {p.s_plus_delta}, L+ {p.l_plus_delta} |"
        )
    return "\n".join(lines)


def render_execution_section(ctx: PitcherContext) -> str:
    lines = ["## Execution"]
    lines.append("| Pitch | CSW% | Zone% | Chase% | xWhiff | xSwing | xRV100 pctl |")
    lines.append("|-------|------|-------|--------|--------|--------|-------------|")
    for e in ctx.execution[:_MAX_PITCH_TYPES]:
        pctl = f"{e.xrv100_percentile}" if e.xrv100_percentile is not None else "--"
        xwhiff = f"{e.xwhiff_p:.3f}" if e.xwhiff_p is not None else "--"
        xswing = f"{e.xswing_p:.3f}" if e.xswing_p is not None else "--"
        lines.append(
            f"| {e.pitch_name} ({e.pitch_type}) "
            f"| {e.csw_pct:.1f} "
            f"| {e.zone_rate:.1f} "
            f"| {e.chase_rate:.1f} "
            f"| {xwhiff} "
            f"| {xswing} "
            f"| {pctl} |"
        )
    return "\n".join(lines)


def render_intermediates_section(ctx: PitcherContext) -> str:
    """Render count-marginalized S values and non-formal P/S diagnostics.

    P and S are preserved as producer-emitted values. Their displayed
    difference is not formal Location+, which is independently emitted as L.
    """
    if not ctx.intermediates:
        return ""

    def _pct(v: float | None) -> str:
        return f"{v * 100:.1f}%" if v is not None else "--"

    def _rv(v: float | None) -> str:
        return f"{v:.2f}" if v is not None else "--"

    def _delta_pct(p: float | None, s: float | None) -> str:
        if p is not None and s is not None:
            return f"{(p - s) * 100:+.1f}pp"
        return "--"

    def _delta_rv(p: float | None, s: float | None) -> str:
        if p is not None and s is not None:
            return f"{(p - s):+.2f}"
        return "--"

    lines = ["## Model Internals: P vs Count-Marginalized S (Not Location+)"]
    lines.append("Displayed deltas are diagnostics only; they are not formal Location+.")
    lines.append(
        "| Pitch | xSwing S | diagnostic delta | xWhiff S | diagnostic delta "
        "| xSwSt S | diagnostic delta | xRV100 S | diagnostic delta |"
    )
    lines.append("|-------|----------|-------|----------|-------|---------|-------|----------|-------|")

    for im in ctx.intermediates[:_MAX_PITCH_TYPES]:
        lines.append(
            f"| {im.pitch_name} ({im.pitch_type}) "
            f"| {_pct(im.xswing_s)} "
            f"| {_delta_pct(im.xswing_p, im.xswing_s)} "
            f"| {_pct(im.xwhiff_s)} "
            f"| {_delta_pct(im.xwhiff_p, im.xwhiff_s)} "
            f"| {_pct(im.xswst_s)} "
            f"| {_delta_pct(im.xswst_p, im.xswst_s)} "
            f"| {_rv(im.xrv100_s)} "
            f"| {_delta_rv(im.xrv100_p, im.xrv100_s)} |"
        )

    return "\n".join(lines)


def render_release_point_section(ctx: PitcherContext) -> str:
    """Render release point table with per-pitch-type x/z/extension."""
    rp = ctx.release_point
    if not rp.pitch_types:
        return ""

    entries = rp.pitch_types[:_MAX_PITCH_TYPES]
    all_cold = all(pt.cold_start for pt in entries)

    lines = ["## Release Point"]

    if all_cold:
        # No baseline available -- show window values only
        lines.append("| Pitch | Horiz (ft) | Vert (ft) | Ext (ft) |")
        lines.append("|-------|------------|-----------|----------|")
        for pt in entries:
            name = f"{pt.pitch_name} ({pt.pitch_type})"
            if pt.small_sample:
                name += " *"
            lines.append(
                f"| {name} "
                f"| {pt.window_release_x:.2f} "
                f"| {pt.window_release_z:.2f} "
                f"| {pt.window_extension:.2f} |"
            )
        lines.append("*(season = window -- no baseline)*")
        lines.append("*Note: window is underpowered -- treat trend comparisons as directional only.*")
    else:
        lines.append("| Pitch | Horiz (ft) | Delta | Vert (ft) | Delta | Ext (ft) | Delta |")
        lines.append("|-------|------------|-------|-----------|-------|----------|-------|")
        for pt in entries:
            name = f"{pt.pitch_name} ({pt.pitch_type})"
            if pt.small_sample:
                name += " *"
            lines.append(
                f"| {name} "
                f"| {pt.window_release_x:.2f} "
                f"| {pt.release_x_delta} "
                f"| {pt.window_release_z:.2f} "
                f"| {pt.release_z_delta} "
                f"| {pt.window_extension:.2f} "
                f"| {pt.extension_delta} |"
            )

    return "\n".join(lines)


def render_pitch_shape_section(ctx: PitcherContext) -> str:
    """Render movement-vs-arm-slot residuals with shape classification."""
    return render_pitch_shape(ctx.pitch_shape)


def render_hard_hit_section(ctx: PitcherContext) -> str:
    """Render contact quality section with hard-hit rate."""
    hhr = ctx.hard_hit_rate
    if hhr.n_batted_balls == 0:
        return ""
    lines = ["## Contact Quality"]
    lines.append(
        f"- Hard-hit rate: {hhr.hard_hit_pct:.1f}% ({hhr.n_hard_hit}/{hhr.n_batted_balls} BIP) -- {hhr.delta}"
    )
    lines.append(f"- Season: {hhr.season_hard_hit_pct:.1f}%")
    if hhr.small_sample:
        lines.append(f"- *Small sample ({hhr.n_batted_balls} BIP)*")
    return "\n".join(lines)


def render_platoon_section(ctx: PitcherContext) -> str:
    lines = ["## Platoon Shifts"]
    available = [s for s in ctx.platoon_mix.splits if s.available]
    if not available:
        lines.append("- No platoon data available")
        return "\n".join(lines)
    for s in available:
        lines.append(
            f"- {s.pitch_name} vs {s.platoon_side}: "
            f"{s.season_usage_pct:.1f}% season"
            + (f" / {s.window_usage_pct:.1f}% recent" if s.window_usage_pct is not None else "")
            + f" -- {s.usage_delta}"
        )
    return "\n".join(lines)


def render_first_pitch_section(ctx: PitcherContext) -> str:
    lines = ["## First-Pitch Tendencies"]
    top = ctx.first_pitch.entries[:3]
    if not top:
        lines.append("- No first-pitch data")
        return "\n".join(lines)
    for fp in top:
        lines.append(
            f"- {fp.pitch_name} ({fp.pitch_type}): "
            f"{fp.window_pct:.1f}% recent / "
            f"{fp.season_pct:.1f}% season -- {fp.delta}"
        )
    return "\n".join(lines)


def render_appearances_section(ctx: PitcherContext) -> str:
    lines = ["## Recent Appearances"]
    lines.append("| Date | IP | Pitches | Rest |")
    lines.append("|------|----|---------|------|")
    # Most recent first
    sorted_apps = sorted(
        ctx.workload.appearances,
        key=lambda a: a.game_date,
        reverse=True,
    )
    for a in sorted_apps:
        rest = f"{a.rest_days}d" if a.rest_days is not None else "--"
        lines.append(f"| {a.game_date} | {a.ip} | {a.pitch_count} | {rest} |")
    return "\n".join(lines)


def render_yoy_section(ctx: PitcherContext) -> str:
    """Render year-over-year section with top-level deltas and arsenal changes.

    Omitted entirely for single-season pitchers (per CPMT-02).
    """
    css = ctx.cross_season_summary
    at = ctx.arsenal_trend
    if css is None and at is None:
        return ""

    lines: list[str] = ["## Year-over-Year"]

    if css is not None:
        lines.append(f"Comparing {css.current_season} vs {css.prior_season}:")
        lines.append(f"- Velocity: {css.velo_delta}")
        lines.append(f"- Pitching+ (P+): {css.p_plus_delta}")
        lines.append(f"- Stuff+ (S+): {css.s_plus_delta}")
        lines.append(f"- Location+ (L+): {css.l_plus_delta}")

    if at is not None:
        if at.added:
            names = ", ".join(p.pitch_name for p in at.added)
            lines.append(f"- Added pitches: {names}")
        if at.dropped:
            names = ", ".join(p.pitch_name for p in at.dropped)
            lines.append(f"- Dropped pitches: {names}")
        if at.continued:
            lines.append("Pitch-level changes:")
            for pt in at.continued:
                parts: list[str] = []
                if pt.usage_delta and "Steady" not in pt.usage_delta:
                    parts.append(f"usage {pt.usage_delta}")
                if pt.velo_delta and "Steady" not in pt.velo_delta:
                    parts.append(f"velo {pt.velo_delta}")
                if pt.p_plus_delta and "Steady" not in pt.p_plus_delta:
                    parts.append(f"P+ {pt.p_plus_delta}")
                if pt.s_plus_delta and "Steady" not in pt.s_plus_delta:
                    parts.append(f"S+ {pt.s_plus_delta}")
                if parts:
                    lines.append(f"- {pt.pitch_name}: {', '.join(parts)}")

    return "\n".join(lines)
