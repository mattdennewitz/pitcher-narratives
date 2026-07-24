"""Code-computed RECENT-vs-PRIOR window deltas for the trends specialist.

Deltas are computed here (never by the LLM), consistent with the project's
"give the model deltas, not arithmetic" value. Consumed by CHANGES mode's
two-frame engine; imported by pipeline._build_trend_input. Also surfaces
pitches thrown meaningfully in the prior window but absent from the recent
window ("dropped" pitches) rather than silently omitting them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .context import PitcherContext
from .engine._common import _MIN_PITCHES
from .facts import DERIVED_FACT_SOURCE, Fact, FactKind, FactRegistry

__all__ = [
    "PitchFrameDelta",
    "TrendFrameComparison",
    "build_trend_frame_comparison",
    "render_trend_frame_comparison",
]

_HEADER = "## Recent vs Prior Window (code-computed deltas)"
_RELEASE_DELTA_FLOOR_FT = 0.05
_VELOCITY_DELTA_FLOOR_MPH = 0.5


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
    fact_ids: tuple[str, ...] = ()
    """Release-point deltas (feet), recent minus prior.

    Co-movement with velocity or shape is descriptive association only.
    """


@dataclass(frozen=True)
class TrendFrameComparison:
    deltas: list[PitchFrameDelta]
    prior_insufficient: bool
    recent_frame_id: str
    prior_frame_id: str
    recent_row_count: int
    prior_row_count: int


def _opt_delta(a: float | None, b: float | None) -> float | None:
    return (a - b) if (a is not None and b is not None) else None


_DELTA_FIELDS = (
    ("window_velo", "velo_delta", "trend.velocity_delta", "mph", None),
    ("window_s_plus", "s_plus_delta", "trend.s_plus_delta", "plus_points", "S"),
    ("window_l_plus", "l_plus_delta", "trend.l_plus_delta", "plus_points", "L"),
    ("window_usage_pct", "usage_delta", "trend.usage_delta", "percentage_points", None),
)
_RELEASE_DELTA_FIELDS = (
    ("window_release_x", "release_x_delta", "trend.release_x_delta", "feet"),
    ("window_release_z", "release_z_delta", "trend.release_z_delta", "feet"),
    ("window_extension", "extension_delta", "trend.extension_delta", "feet"),
)


def _context_registry(ctx: PitcherContext) -> FactRegistry | None:
    registry = getattr(ctx, "facts", None)
    return registry if isinstance(registry, FactRegistry) else None


def _context_fact_id(ctx: PitcherContext, path: str) -> str | None:
    fact_ids = getattr(ctx, "fact_ids", None)
    return fact_ids.get(path) if isinstance(fact_ids, dict) else None


def _comparison_fact(
    *,
    registry: FactRegistry,
    recent: PitcherContext,
    prior: PitcherContext,
    recent_fact_id: str | None,
    prior_fact_id: str | None,
    metric: str,
    variant: str | None,
    entity: str,
    value: float | None,
    unit: str,
    sample_size: int,
) -> Fact | None:
    if value is None:
        return None
    if recent_fact_id is None or prior_fact_id is None:
        raise ValueError(f"trend comparison lacks exact source fact IDs for {metric}")
    if recent_fact_id not in registry or prior_fact_id not in registry:
        raise ValueError(f"trend comparison source facts are not registered for {metric}")
    recent_fact = registry.get(recent_fact_id)
    prior_fact = registry.get(prior_fact_id)
    if recent_fact.frame_id != recent.frame_id or prior_fact.frame_id != prior.frame_id:
        raise ValueError(f"trend comparison source facts use the wrong frame for {metric}")
    return registry.add(
        Fact.create(
            kind=FactKind.COMPUTED,
            metric=metric,
            variant=variant,
            entity=entity,
            value=value,
            unit=unit,
            frame_id=recent.frame_id,
            population=f"recent={recent.frame_id};prior={prior.frame_id}",
            sample_size=sample_size,
            sufficiency="available",
            source=DERIVED_FACT_SOURCE,
            source_fact_ids=(recent_fact_id, prior_fact_id),
            transform="comparison:delta",
            semantic_key=f"{entity}|{recent.frame_id}|{prior.frame_id}|{metric}",
            manifest_version=registry.manifest_version,
        )
    )


def _pitch_index(rows: list[Any], pitch_name: str) -> int | None:
    return next(
        (index for index, row in enumerate(rows) if row.pitch_name == pitch_name),
        None,
    )


def build_trend_frame_comparison(recent: PitcherContext, prior: PitcherContext) -> TrendFrameComparison:
    """Compute and register exact recent-minus-prior comparison facts."""
    if recent.frame_type.value != "recent":
        raise ValueError("recent comparison input must use the RECENT frame")
    if prior.frame_type.value != "prior":
        raise ValueError("prior comparison input must use the PRIOR frame")
    if recent.source_population != prior.source_population:
        raise ValueError("trend frames must share one source population")
    if recent.as_of != prior.as_of:
        raise ValueError("trend frames must share one as-of boundary")
    if recent.frame_id == prior.frame_id:
        raise ValueError("recent and prior frame identities must differ")

    registry = _context_registry(recent)
    prior_registry = _context_registry(prior)
    if (registry is None) != (prior_registry is None):
        raise ValueError("trend frames must both provide typed fact registries")
    if registry is not None and prior_registry is not None:
        registry.merge(prior_registry)

    prior_by_name = {p.pitch_name: p for p in prior.arsenal}
    recent_release_by_name = {rp.pitch_name: rp for rp in recent.release_point.pitch_types}
    prior_release_by_name = {rp.pitch_name: rp for rp in prior.release_point.pitch_types}
    deltas: list[PitchFrameDelta] = []
    for recent_index, r in enumerate(recent.arsenal):
        p = prior_by_name.get(r.pitch_name)
        prior_index = _pitch_index(prior.arsenal, r.pitch_name)
        suff = p is not None and r.n_pitches_window >= _MIN_PITCHES and p.n_pitches_window >= _MIN_PITCHES
        r_release = recent_release_by_name.get(r.pitch_name)
        p_release = prior_release_by_name.get(r.pitch_name)
        recent_release_index = _pitch_index(recent.release_point.pitch_types, r.pitch_name)
        prior_release_index = _pitch_index(prior.release_point.pitch_types, r.pitch_name)
        release_suff = suff and r_release is not None and p_release is not None
        values = {
            "velo_delta": _opt_delta(r.window_velo, p.window_velo) if suff else None,
            "s_plus_delta": _opt_delta(r.window_s_plus, p.window_s_plus) if suff else None,
            "l_plus_delta": _opt_delta(r.window_l_plus, p.window_l_plus) if suff else None,
            "usage_delta": _opt_delta(r.window_usage_pct, p.window_usage_pct) if suff else None,
            "release_x_delta": (
                _opt_delta(r_release.window_release_x, p_release.window_release_x) if release_suff else None
            ),
            "release_z_delta": (
                _opt_delta(r_release.window_release_z, p_release.window_release_z) if release_suff else None
            ),
            "extension_delta": (
                _opt_delta(r_release.window_extension, p_release.window_extension) if release_suff else None
            ),
        }
        fact_ids: list[str] = []
        if registry is not None and suff and prior_index is not None:
            sample_size = min(r.n_pitches_window, p.n_pitches_window)
            for source_field, value_field, metric, unit, variant in _DELTA_FIELDS:
                fact = _comparison_fact(
                    registry=registry,
                    recent=recent,
                    prior=prior,
                    recent_fact_id=_context_fact_id(recent, f"arsenal[{recent_index}].{source_field}"),
                    prior_fact_id=_context_fact_id(prior, f"arsenal[{prior_index}].{source_field}"),
                    metric=metric,
                    variant=variant,
                    entity=r.pitch_name,
                    value=values[value_field],
                    unit=unit,
                    sample_size=sample_size,
                )
                if fact is not None:
                    fact_ids.append(fact.id)
            if release_suff and recent_release_index is not None and prior_release_index is not None:
                for source_field, value_field, metric, unit in _RELEASE_DELTA_FIELDS:
                    fact = _comparison_fact(
                        registry=registry,
                        recent=recent,
                        prior=prior,
                        recent_fact_id=_context_fact_id(
                            recent,
                            f"release_point.pitch_types[{recent_release_index}].{source_field}",
                        ),
                        prior_fact_id=_context_fact_id(
                            prior,
                            f"release_point.pitch_types[{prior_release_index}].{source_field}",
                        ),
                        metric=metric,
                        variant=None,
                        entity=r.pitch_name,
                        value=values[value_field],
                        unit=unit,
                        sample_size=sample_size,
                    )
                    if fact is not None:
                        fact_ids.append(fact.id)
        deltas.append(
            PitchFrameDelta(
                pitch_name=r.pitch_name,
                sufficient=suff,
                fact_ids=tuple(sorted(fact_ids)),
                **values,
            )
        )

    # A display-truncated arsenal cannot establish absence. Dropped-pitch claims
    # remain disabled until a complete per-frame pitch-presence contract exists.
    prior_insufficient = not prior.arsenal or all(not d.sufficient for d in deltas)
    return TrendFrameComparison(
        deltas=deltas,
        prior_insufficient=prior_insufficient,
        recent_frame_id=recent.frame_id,
        prior_frame_id=prior.frame_id,
        recent_row_count=recent.frame_row_count,
        prior_row_count=prior.frame_row_count,
    )


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
        if d.fact_ids:
            lines[-1] += " " + " ".join(f"[{fact_id}]" for fact_id in d.fact_ids)
    has_release_velocity_comovement = any(
        d.sufficient
        and d.velo_delta is not None
        and abs(d.velo_delta) >= _VELOCITY_DELTA_FLOOR_MPH
        and any(
            value is not None and abs(value) >= _RELEASE_DELTA_FLOOR_FT
            for value in (
                d.release_x_delta,
                d.release_z_delta,
                d.extension_delta,
            )
        )
        for d in cmp.deltas
    )
    if has_release_velocity_comovement:
        lines.append("")
        lines.append(
            "Release-point or extension and velocity changed in the same comparison. "
            "That association is consistent with a possible adjustment, but these "
            "aggregates do not identify a mechanism or establish a cause-and-effect "
            "relationship between the changes."
        )
    return "\n".join(lines)
