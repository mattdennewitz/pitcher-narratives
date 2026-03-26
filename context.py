"""PitcherContext assembly for LLM prompt generation.

Assembles all engine outputs into a single Pydantic model with a
to_prompt() method that renders prompt-ready markdown under 2,000 tokens.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from data import PitcherData
from engine import (
    compute_fastball_summary,
    compute_velocity_arc,
    compute_arsenal_summary,
    compute_platoon_mix,
    compute_first_pitch_weaponry,
    compute_execution_metrics,
    compute_workload_context,
    compute_tto_analysis,
    compute_hard_hit_rate,
    FastballSummary,
    VelocityArc,
    PitchTypeSummary,
    PlatoonMix,
    FirstPitchWeaponry,
    ExecutionMetrics,
    WorkloadContext,
    HardHitRate,
    TTOAnalysis,
    TTOPitchType,
    TTOPlatoonSplit,
)

__all__ = ["PitcherContext", "assemble_pitcher_context"]

_MAX_PITCH_TYPES = 4
"""Token budget: keep top 4 pitch types only in arsenal and execution tables."""


class PitcherContext(BaseModel):
    """Complete context document for LLM prompt generation.

    Assembles all engine outputs (fastball, arsenal, execution, workload)
    into one Pydantic model with a to_prompt() method.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pitcher_name: str
    pitcher_id: int
    throws: str
    role: str
    """Most recent appearance role: 'SP' or 'RP'."""

    fastball: FastballSummary | None
    velocity_arc: VelocityArc | None
    arsenal: list[PitchTypeSummary]
    platoon_mix: PlatoonMix
    first_pitch: FirstPitchWeaponry
    execution: list[ExecutionMetrics]
    hard_hit_rate: HardHitRate
    workload: WorkloadContext
    tto: TTOAnalysis | None

    def to_prompt(self) -> str:
        """Render as prompt-ready markdown under 2,000 tokens."""
        sections: list[str] = []

        # Title
        sections.append(
            f"# {self.pitcher_name} ({self.throws}HP) -- Scouting Context"
        )

        # Executive summary — key changes from most recent appearance
        sections.append(self._render_executive_summary())

        # Role & Workload summary
        sections.append(self._render_role_section())

        # Primary Fastball
        sections.append(self._render_fastball_section())

        # Times through order (starters)
        sections.append(self._render_tto_section())

        # Arsenal table
        sections.append(self._render_arsenal_section())

        # Execution table
        sections.append(self._render_execution_section())

        # Contact quality (hard-hit rate)
        sections.append(self._render_hard_hit_section())

        # Platoon shifts
        sections.append(self._render_platoon_section())

        # First-pitch tendencies
        sections.append(self._render_first_pitch_section())

        # Recent appearances
        sections.append(self._render_appearances_section())

        return "\n\n".join(s for s in sections if s)

    # ── Private render helpers ────────────────────────────────────────

    def _render_executive_summary(self) -> str:
        """Build a bullet-point executive summary of key observations."""
        bullets: list[str] = []

        # Most recent appearance context
        wl = self.workload
        if wl.appearances:
            latest = max(wl.appearances, key=lambda a: a.game_date)
            bullets.append(
                f"Last outing: {latest.game_date} ({latest.ip} IP, "
                f"{latest.pitch_count} pitches, {self.role})"
            )

        # Fastball velocity trend
        fb = self.fastball
        if fb and fb.velo_delta and fb.velo_delta != "--":
            bullets.append(f"Fastball velo: {fb.velo_delta} vs season")

        # Overall P+ trend
        if fb and fb.p_plus_delta and fb.p_plus_delta != "--":
            bullets.append(f"Fastball P+: {fb.p_plus_delta} vs season")

        # Biggest arsenal usage shift
        if self.arsenal:
            biggest_shift = max(
                self.arsenal,
                key=lambda p: abs(p.window_usage_pct - p.season_usage_pct)
                if p.window_usage_pct is not None and p.season_usage_pct is not None
                else 0,
            )
            if (
                biggest_shift.window_usage_pct is not None
                and biggest_shift.season_usage_pct is not None
            ):
                shift = biggest_shift.window_usage_pct - biggest_shift.season_usage_pct
                if abs(shift) >= 5.0:
                    bullets.append(
                        f"Notable mix change: {biggest_shift.pitch_name} "
                        f"usage {shift:+.1f}pp vs season"
                    )

        # TTO insight for starters
        tto = self.tto
        if tto and tto.available and tto.summary:
            bullets.append(f"TTO: {tto.summary}")

        # Velocity arc from last outing
        va = self.velocity_arc
        if va and va.available and va.drop_string:
            bullets.append(f"Velocity arc: {va.drop_string}")

        # Hard-hit rate shift
        hhr = self.hard_hit_rate
        if (
            not hhr.cold_start
            and "Steady" not in hhr.delta
            and abs(hhr.hard_hit_pct - hhr.season_hard_hit_pct) >= 5.0
        ):
            bullets.append(
                f"Hard-hit rate: {hhr.delta} vs season "
                f"({hhr.hard_hit_pct:.1f}%)"
            )

        # Workload concern
        if wl.workload_concern:
            bullets.append("**Workload flag: 3+ consecutive days pitched**")

        if not bullets:
            return ""

        lines = ["## Executive Summary"]
        for b in bullets:
            lines.append(f"- {b}")
        return "\n".join(lines)

    def _render_role_section(self) -> str:
        lines = [f"## Role"]
        lines.append(f"- Most recent: {self.role}")
        wl = self.workload
        lines.append(f"- Appearances: {len(wl.appearances)}")
        if wl.max_consecutive_days >= 2:
            lines.append(
                f"- Max consecutive days: {wl.max_consecutive_days}"
            )
        if wl.workload_concern:
            lines.append("- **Workload concern: 3+ consecutive days**")
        return "\n".join(lines)

    def _render_fastball_section(self) -> str:
        fb = self.fastball
        if fb is None:
            return "## Primary Fastball\n- No standard fastball identified"

        lines = [f"## Primary Fastball: {fb.pitch_name} ({fb.pitch_type})"]
        lines.append(
            f"- Velo: {fb.season_velo:.1f} season / "
            f"{fb.window_velo:.1f} recent -- {fb.velo_delta}"
        )
        if fb.window_p_plus is not None:
            lines.append(
                f"- Stuff+ (P+): {fb.season_p_plus:.0f} season / "
                f"{fb.window_p_plus:.0f} recent -- {fb.p_plus_delta}"
            )
        else:
            lines.append(
                f"- Stuff+ (P+): {fb.season_p_plus:.0f} season -- "
                f"{fb.p_plus_delta}"
            )
        lines.append(
            f"- Movement: H {fb.pfx_x_delta}, V {fb.pfx_z_delta}"
        )

        # Velocity arc from last outing
        va = self.velocity_arc
        if va is not None and va.available:
            lines.append(f"- Velocity arc (last outing): {va.drop_string}")
        elif va is not None:
            lines.append(f"- Velocity arc: {va.drop_string}")

        if fb.small_sample:
            lines.append("- *Small sample*")
        return "\n".join(lines)

    def _render_tto_section(self) -> str:
        tto = self.tto
        if tto is None or not tto.available:
            return ""
        lines = ["## Times Through Order"]
        lines.append(f"- {tto.summary}")

        # Mix shift flags
        if tto.mix_shifts:
            for ms in tto.mix_shifts:
                lines.append(f"- **Mix shift:** {ms}")

        # Main table with FB/Secondary P+ split
        lines.append("")
        lines.append("| Pass | Pitches | Velo | P+ | FB P+ | Sec P+ | Velo Delta | P+ Delta |")
        lines.append("|------|---------|------|----|-------|--------|------------|----------|")
        for s in tto.splits:
            velo = f"{s.avg_velo:.1f}" if s.avg_velo else "--"
            pp = f"{s.avg_p_plus:.0f}" if s.avg_p_plus else "--"
            fb = f"{s.fb_p_plus:.0f}" if s.fb_p_plus else "--"
            sec = f"{s.sec_p_plus:.0f}" if s.sec_p_plus else "--"
            sample = " *" if s.small_sample else ""
            lines.append(
                f"| {s.pass_number}{sample} "
                f"| {s.pitches} "
                f"| {velo} "
                f"| {pp} "
                f"| {fb} ({s.fb_p_plus_delta}) "
                f"| {sec} ({s.sec_p_plus_delta}) "
                f"| {s.velo_delta} "
                f"| {s.p_plus_delta} |"
            )

        # Per-pitch-type breakdown with usage %
        lines.append("")
        lines.append("**Pitch mix & P+ by pass:**")
        all_types: dict[str, dict[int, TTOPitchType]] = {}
        for s in tto.splits:
            for pt in s.pitch_types:
                if pt.pitch_type not in all_types:
                    all_types[pt.pitch_type] = {}
                all_types[pt.pitch_type][s.pass_number] = pt

        pass_nums = [s.pass_number for s in tto.splits]
        header_passes = " | ".join(f"Pass {n}" for n in pass_nums)
        lines.append(f"| Pitch | {header_passes} |")
        sep_passes = " | ".join("---" for _ in pass_nums)
        lines.append(f"|-------|{sep_passes}|")

        for pt_name, by_pass in sorted(all_types.items()):
            cells: list[str] = []
            for pn in pass_nums:
                if pn in by_pass:
                    entry = by_pass[pn]
                    pp = f"{entry.avg_p_plus:.0f}" if entry.avg_p_plus else "--"
                    cells.append(
                        f"{entry.usage_pct:.0f}% P+{pp} "
                        f"({entry.usage_delta}, {entry.p_plus_delta})"
                    )
                else:
                    cells.append("dropped")
            lines.append(f"| {pt_name} | {' | '.join(cells)} |")

        # Platoon within TTO — only render if meaningful data exists
        has_platoon = any(len(s.platoon) > 0 for s in tto.splits)
        if has_platoon:
            lines.append("")
            lines.append("**Platoon mix by pass:**")
            for stand_label, stand_val in [("vs LHB", "L"), ("vs RHB", "R")]:
                # Collect per-pass data for this side
                stand_data: dict[str, dict[int, TTOPlatoonSplit]] = {}
                for s in tto.splits:
                    for p in s.platoon:
                        if p.stand == stand_val:
                            if p.pitch_type not in stand_data:
                                stand_data[p.pitch_type] = {}
                            stand_data[p.pitch_type][s.pass_number] = p
                if not stand_data:
                    continue
                lines.append(f"*{stand_label}:*")
                lines.append(f"| Pitch | {header_passes} |")
                lines.append(f"|-------|{sep_passes}|")
                for pt_name, by_pass in sorted(stand_data.items()):
                    cells = []
                    for pn in pass_nums:
                        if pn in by_pass:
                            e = by_pass[pn]
                            pp = f"P+{e.avg_p_plus:.0f}" if e.avg_p_plus else ""
                            cells.append(f"{e.usage_pct:.0f}% {pp} ({e.pitches}p)")
                        else:
                            cells.append("--")
                    lines.append(f"| {pt_name} | {' | '.join(cells)} |")

        return "\n".join(lines)

    def _render_arsenal_section(self) -> str:
        lines = ["## Arsenal"]
        lines.append("| Pitch | Usage | Delta | P+ | Delta |")
        lines.append("|-------|-------|-------|----|-------|")
        for p in self.arsenal[:_MAX_PITCH_TYPES]:
            wp = f"{p.window_p_plus:.0f}" if p.window_p_plus is not None else "--"
            lines.append(
                f"| {p.pitch_name} ({p.pitch_type}) "
                f"| {p.window_usage_pct:.1f}% "
                f"| {p.usage_delta} "
                f"| {wp} "
                f"| {p.p_plus_delta} |"
            )
        return "\n".join(lines)

    def _render_execution_section(self) -> str:
        lines = ["## Execution"]
        lines.append("| Pitch | CSW% | Zone% | Chase% | xWhiff | xSwing | xRV100 pctl |")
        lines.append("|-------|------|-------|--------|--------|--------|-------------|")
        for e in self.execution[:_MAX_PITCH_TYPES]:
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

    def _render_hard_hit_section(self) -> str:
        """Render contact quality section with hard-hit rate."""
        hhr = self.hard_hit_rate
        if hhr.n_batted_balls == 0:
            return ""
        lines = ["## Contact Quality"]
        lines.append(
            f"- Hard-hit rate: {hhr.hard_hit_pct:.1f}% "
            f"({hhr.n_hard_hit}/{hhr.n_batted_balls} BIP) -- {hhr.delta}"
        )
        lines.append(f"- Season: {hhr.season_hard_hit_pct:.1f}%")
        if hhr.small_sample:
            lines.append(f"- *Small sample ({hhr.n_batted_balls} BIP)*")
        return "\n".join(lines)

    def _render_platoon_section(self) -> str:
        lines = ["## Platoon Shifts"]
        available = [s for s in self.platoon_mix.splits if s.available]
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

    def _render_first_pitch_section(self) -> str:
        lines = ["## First-Pitch Tendencies"]
        top = self.first_pitch.entries[:3]
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

    def _render_appearances_section(self) -> str:
        lines = ["## Recent Appearances"]
        lines.append("| Date | IP | Pitches | Rest |")
        lines.append("|------|----|---------|------|")
        # Most recent first
        sorted_apps = sorted(
            self.workload.appearances,
            key=lambda a: a.game_date,
            reverse=True,
        )
        for a in sorted_apps:
            rest = f"{a.rest_days}d" if a.rest_days is not None else "--"
            lines.append(
                f"| {a.game_date} | {a.ip} | {a.pitch_count} | {rest} |"
            )
        return "\n".join(lines)


def assemble_pitcher_context(data: PitcherData) -> PitcherContext:
    """Orchestrate all engine compute functions into a PitcherContext.

    Args:
        data: PitcherData bundle from data.load_pitcher_data.

    Returns:
        PitcherContext with all sections populated, ready for to_prompt().
    """
    fastball = compute_fastball_summary(data)
    velocity_arc = (
        compute_velocity_arc(data, fastball.pitch_type) if fastball else None
    )
    arsenal = compute_arsenal_summary(data)[:_MAX_PITCH_TYPES]
    platoon_mix = compute_platoon_mix(data)
    first_pitch = compute_first_pitch_weaponry(data)
    execution = compute_execution_metrics(data)[:_MAX_PITCH_TYPES]
    hard_hit_rate = compute_hard_hit_rate(data)
    workload = compute_workload_context(data)
    tto = compute_tto_analysis(data)

    # Determine role from most recent appearance
    most_recent = data.appearances.sort("game_date", descending=True).row(
        0, named=True
    )
    role = most_recent["role"]

    return PitcherContext(
        pitcher_name=data.pitcher_name,
        pitcher_id=data.pitcher_id,
        throws=data.throws,
        role=role,
        fastball=fastball,
        velocity_arc=velocity_arc,
        arsenal=arsenal,
        platoon_mix=platoon_mix,
        first_pitch=first_pitch,
        execution=execution,
        hard_hit_rate=hard_hit_rate,
        workload=workload,
        tto=tto,
    )
