"""Code-computed RECENT-vs-PRIOR window deltas for the trends specialist.

Deltas are computed here (never by the LLM), consistent with the project's
"give the model deltas, not arithmetic" value. Consumed by CHANGES mode's
two-frame engine; imported by pipeline._build_trend_input. Also surfaces
pitches thrown meaningfully in the prior window but absent from the recent
window ("dropped" pitches) rather than silently omitting them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .context import PitcherContext
from .engine._common import _MIN_PITCHES

__all__ = [
    "PitchFrameDelta",
    "TrendFrameComparison",
    "build_trend_frame_comparison",
    "render_trend_frame_comparison",
]

_HEADER = "## Recent vs Prior Window (code-computed deltas)"


@dataclass(frozen=True)
class PitchFrameDelta:
    pitch_name: str
    velo_delta: float | None
    s_plus_delta: float | None
    l_plus_delta: float | None
    usage_delta: float | None
    sufficient: bool
    dropped: bool = False
    release_x_delta: float | None = None
    release_z_delta: float | None = None
    extension_delta: float | None = None
    """Release-point deltas (feet), recent minus prior. Mechanism signal:
    a release-point/extension shift alongside a velo or shape change points
    to a deliberate mechanical adjustment rather than a pitch-mix change."""


@dataclass(frozen=True)
class TrendFrameComparison:
    deltas: list[PitchFrameDelta]
    prior_insufficient: bool


def _opt_delta(a: float | None, b: float | None) -> float | None:
    return (a - b) if (a is not None and b is not None) else None


def build_trend_frame_comparison(
    recent: PitcherContext, prior: PitcherContext
) -> TrendFrameComparison:
    """Compute per-pitch recent-minus-prior deltas, matched by pitch name.

    A delta is suppressed (``sufficient=False``, fields ``None``) when either
    frame has fewer than ``_MIN_PITCHES`` window pitches for that pitch type,
    or the pitch is absent from the prior frame. A pitch thrown meaningfully
    in the prior window but absent from the recent window is surfaced as a
    ``dropped=True`` entry rather than silently omitted. The prior frame is
    flagged insufficient when it has no arsenal or no pitch clears the
    sample floor and no dropped pitch was found.
    """
    prior_by_name = {p.pitch_name: p for p in prior.arsenal}
    recent_release_by_name = {rp.pitch_name: rp for rp in recent.release_point.pitch_types}
    prior_release_by_name = {rp.pitch_name: rp for rp in prior.release_point.pitch_types}
    deltas: list[PitchFrameDelta] = []
    for r in recent.arsenal:
        p = prior_by_name.get(r.pitch_name)
        suff = (
            p is not None
            and r.n_pitches_window >= _MIN_PITCHES
            and p.n_pitches_window >= _MIN_PITCHES
        )
        r_release = recent_release_by_name.get(r.pitch_name)
        p_release = prior_release_by_name.get(r.pitch_name)
        release_suff = suff and r_release is not None and p_release is not None
        deltas.append(
            PitchFrameDelta(
                pitch_name=r.pitch_name,
                velo_delta=_opt_delta(r.window_velo, p.window_velo) if suff else None,
                s_plus_delta=_opt_delta(r.window_s_plus, p.window_s_plus) if suff else None,
                l_plus_delta=_opt_delta(r.window_l_plus, p.window_l_plus) if suff else None,
                usage_delta=_opt_delta(r.window_usage_pct, p.window_usage_pct) if suff else None,
                sufficient=suff,
                release_x_delta=(
                    _opt_delta(r_release.window_release_x, p_release.window_release_x)
                    if release_suff else None
                ),
                release_z_delta=(
                    _opt_delta(r_release.window_release_z, p_release.window_release_z)
                    if release_suff else None
                ),
                extension_delta=(
                    _opt_delta(r_release.window_extension, p_release.window_extension)
                    if release_suff else None
                ),
            ),
        )
    recent_names = {r.pitch_name for r in recent.arsenal}
    for p in prior.arsenal:
        if p.pitch_name not in recent_names and p.n_pitches_window >= _MIN_PITCHES:
            deltas.append(
                PitchFrameDelta(
                    pitch_name=p.pitch_name,
                    velo_delta=None, s_plus_delta=None, l_plus_delta=None,
                    usage_delta=None, sufficient=False, dropped=True,
                ),
            )
    prior_insufficient = not prior.arsenal or all(not d.sufficient and not d.dropped for d in deltas)
    return TrendFrameComparison(deltas=deltas, prior_insufficient=prior_insufficient)


def render_trend_frame_comparison(cmp: TrendFrameComparison) -> str:
    """Render the comparison as a markdown block for the trends specialist."""
    if cmp.prior_insufficient:
        return (
            f"{_HEADER}\n\n"
            "Prior window insufficient for comparison (too few prior "
            "appearances). Report recent-window findings without a prior "
            "contrast; do not invent a change."
        )
    lines = [
        _HEADER,
        "",
        "Deltas are recent minus prior; positive = higher in the recent window.",
        "",
    ]
    for d in cmp.deltas:
        if d.dropped:
            lines.append(f"- {d.pitch_name}: no longer thrown (present in prior window, absent in recent)")
            continue
        if not d.sufficient:
            lines.append(f"- {d.pitch_name}: insufficient sample for a recent-vs-prior delta")
            continue
        parts: list[str] = []
        if d.velo_delta is not None:
            parts.append(f"velo {d.velo_delta:+.1f} mph")
        if d.s_plus_delta is not None:
            parts.append(f"S+ {d.s_plus_delta:+.0f}")
        if d.l_plus_delta is not None:
            parts.append(f"L+ {d.l_plus_delta:+.0f}")
        if d.usage_delta is not None:
            parts.append(f"usage {d.usage_delta:+.1f} pts")
        if d.release_x_delta is not None:
            parts.append(f"release x {d.release_x_delta:+.2f} ft")
        if d.release_z_delta is not None:
            parts.append(f"release z {d.release_z_delta:+.2f} ft")
        if d.extension_delta is not None:
            parts.append(f"extension {d.extension_delta:+.2f} ft")
        lines.append(f"- {d.pitch_name}: {', '.join(parts) if parts else 'no meaningful change'}")
    if any(d.release_x_delta is not None or d.release_z_delta is not None or d.extension_delta is not None for d in cmp.deltas):
        lines.append("")
        lines.append(
            "Release-point/extension shifts alongside a velo or shape change are a "
            "mechanism signal — a deliberate mechanical adjustment, not just a "
            "pitch-mix change. A shift with no accompanying velo/shape movement is "
            "more likely mound rhythm or measurement noise; do not over-read it."
        )
    return "\n".join(lines)
