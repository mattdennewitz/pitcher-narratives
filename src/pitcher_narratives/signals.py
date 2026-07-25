"""Key signal extraction model and rendering.

The signal extractor identifies cross-specialist patterns that no single
specialist can see: tensions between analysts, arsenal dependencies,
connected changes, and sample size caveats. These signals guide the
writer's narrative priorities and give the anchor checker concrete
validation targets.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "SIGNAL_EXTRACTOR_PROMPT",
    "KeySignals",
    "Signal",
    "SignalState",
    "count_secondary_signals",
    "render_key_signals",
]


class SignalState(StrEnum):
    """Evidence state for the cross-specialist signal stage."""

    MATERIAL = "material"
    NO_MATERIAL_SIGNAL = "no_material_signal"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class Signal(BaseModel):
    """One evidence-bound cross-specialist finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    fact_ids: tuple[str, ...] = Field(min_length=1)
    source_claim_ids: tuple[str, ...] = Field(min_length=1)
    sample_size: int = Field(ge=0)
    comparison_population: str = Field(min_length=1)


class KeySignals(BaseModel):
    """Nullable, evidence-bound cross-specialist findings."""

    state: SignalState
    top_improvement: Signal | None = None
    top_concern: Signal | None = None
    secondary: tuple[Signal, ...] = ()

    @model_validator(mode="after")
    def validate_state(self) -> KeySignals:
        has_signal = self.top_improvement is not None or self.top_concern is not None or bool(self.secondary)
        if self.state is SignalState.MATERIAL and not has_signal:
            raise ValueError("material signal state requires at least one signal")
        if (
            self.state
            in {
                SignalState.NO_MATERIAL_SIGNAL,
                SignalState.INSUFFICIENT_EVIDENCE,
            }
            and has_signal
        ):
            raise ValueError(f"{self.state.value} signal state cannot contain signals")
        return self


def count_secondary_signals(signals: KeySignals | None) -> int:
    """Count evidence-bound secondary signals."""
    return 0 if signals is None else len(signals.secondary)


def _render_signal(label: str, signal: Signal) -> str:
    facts = " ".join(f"[{fact_id}]" for fact_id in signal.fact_ids)
    claims = " ".join(f"[claim:{claim_id}]" for claim_id in signal.source_claim_ids)
    return (
        f"- {label}: {signal.text} {facts} {claims} "
        f"(n={signal.sample_size}; population={signal.comparison_population})"
    )


def render_key_signals(signals: KeySignals) -> str:
    """Render the explicit state and only the signals that exist."""
    lines = ["## Key Signals", f"- State: {signals.state.value}"]
    if signals.top_improvement is not None:
        lines.append(_render_signal("Top Improvement", signals.top_improvement))
    if signals.top_concern is not None:
        lines.append(_render_signal("Top Concern", signals.top_concern))
    lines.extend(_render_signal("Secondary", signal) for signal in signals.secondary)
    return "\n".join(lines)


SIGNAL_EXTRACTOR_PROMPT = """\
You are a cross-specialist pattern detector. You receive only verified \
specialist claims and the exact same-frame fact registry behind them.

Return:
- state: material when at least one fully evidence-bound cross-specialist \
finding is present; no_material_signal when none is present; insufficient_evidence \
when samples are too thin; conflicting_evidence when verified claims conflict.
- top_improvement and top_concern: either may be null.
- secondary: zero or more non-duplicative supported signals.

Every populated signal must contain:
- one concise sentence;
- exact fact_ids copied from the registry;
- exact source_claim_ids copied from the specialist claims;
- sample_size equal to the smallest cited fact sample;
- comparison_population copied exactly from a cited fact;

Never manufacture a positive or negative finding to fill a field. Never use a \
universal whiff threshold, unsupplied pitch-class ordering, absolute rarity tag, \
or generated prose as evidence. Thin evidence is insufficient, not a material \
directional signal. Only cite facts already cited by the named source claims."""
