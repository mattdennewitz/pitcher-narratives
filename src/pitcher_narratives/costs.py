"""Shared LLM cost tracking: pricing table, usage tracker, renderers.

Used by the morning run (digest footer, usage.json) and by compare.py
(markdown table). Token extraction from pydantic-ai usage objects is the
caller's job; this module only does arithmetic and rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["PRICING", "UsageTracker", "model_label"]

PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.00},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
    "gemini-flash-latest": {"input": 0.15, "output": 0.60},
}
"""USD per 1M tokens. Keys are bare model names (no provider prefix)."""


def model_label(model: str) -> str:
    """Strip the pydantic-ai provider prefix: 'anthropic:x' -> 'x'."""
    return model.split(":", 1)[-1]


@dataclass
class CallRecord:
    """Token usage for one LLM call."""

    stage: str
    model: str  # bare model name
    input_tokens: int
    output_tokens: int

    def cost(self) -> float | None:
        """Dollar cost, or None when the model is not in PRICING."""
        p = PRICING.get(self.model)
        if p is None:
            return None
        return (
            self.input_tokens / 1_000_000 * p["input"]
            + self.output_tokens / 1_000_000 * p["output"]
        )


@dataclass
class UsageTracker:
    """Accumulates per-call token usage for cost reporting."""

    records: list[CallRecord] = field(default_factory=list)

    def record(self, model: str, input_tokens: int, output_tokens: int,
               *, stage: str = "") -> None:
        """Add one call's usage. `model` may carry a provider prefix."""
        self.records.append(CallRecord(
            stage=stage, model=model_label(model),
            input_tokens=input_tokens, output_tokens=output_tokens,
        ))

    def total_input(self) -> int:
        """Sum of input tokens across all recorded calls."""
        return sum(r.input_tokens for r in self.records)

    def total_output(self) -> int:
        """Sum of output tokens across all recorded calls."""
        return sum(r.output_tokens for r in self.records)

    def total_cost(self) -> float | None:
        """Sum of known-model costs; None if NO record has a priced model."""
        costs = [c for r in self.records if (c := r.cost()) is not None]
        if not costs:
            return None
        return sum(costs)

    def to_json(self) -> list[dict]:
        """Raw per-call records for usage.json.

        Each record carries stage, model, token counts, and the per-call
        dollar cost (None — JSON null — for unpriced models).
        """
        return [
            {
                "stage": r.stage,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost": r.cost(),
            }
            for r in self.records
        ]

    def _grouped(self) -> dict[tuple[str, str], list[CallRecord]]:
        """Group records by (stage group, model). writer:* → 'writers', specialist:* → 'specialists'."""
        groups: dict[tuple[str, str], list[CallRecord]] = {}
        for r in self.records:
            if r.stage.startswith("writer:"):
                stage = "writers"
            elif r.stage.startswith("specialist:"):
                stage = "specialists"
            else:
                stage = r.stage or "other"
            groups.setdefault((stage, r.model), []).append(r)
        return groups

    def render_cost_block(self, *, wall_s: float) -> str:
        """Compact run-cost block for the digest footer and stdout."""

        def _fmt_tokens(n: int) -> str:
            return f"{n / 1000:.1f}k" if n >= 1000 else str(n)

        def _fmt_cost(c: float | None) -> str:
            return f"${c:.3f}" if c is not None else "n/a"

        lines = ["── Run cost ─────────────────────────────"]
        for (stage, model), recs in self._grouped().items():
            tin = sum(r.input_tokens for r in recs)
            tout = sum(r.output_tokens for r in recs)
            costs = [c for r in recs if (c := r.cost()) is not None]
            cost = sum(costs) if costs else None
            count = f" ×{len(recs)}" if len(recs) > 1 else ""
            lines.append(
                f"{stage:<10} {model}{count}  "
                f"{_fmt_tokens(tin)} in / {_fmt_tokens(tout)} out  {_fmt_cost(cost)}"
            )
        lines.append(
            f"{'total':<10} {_fmt_cost(self.total_cost()):>40}   ({wall_s:.0f}s)"
        )
        return "\n".join(lines)

    def format_table(self) -> str:
        """Markdown per-model cost table (compare.py's format)."""
        by_model: dict[str, dict[str, int]] = {}
        for r in self.records:
            t = by_model.setdefault(r.model, {"input": 0, "output": 0})
            t["input"] += r.input_tokens
            t["output"] += r.output_tokens

        rows = [
            "| Model | Input | Output | Input Cost | Output Cost | Total |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        grand_in = grand_out = 0
        grand_cost = 0.0
        for model in sorted(by_model):
            t = by_model[model]
            p = PRICING.get(model, {"input": 0, "output": 0})
            ic = t["input"] / 1_000_000 * p["input"]
            oc = t["output"] / 1_000_000 * p["output"]
            rows.append(
                f"| {model} | {t['input']:,} | {t['output']:,} "
                f"| ${ic:.4f} | ${oc:.4f} | ${ic + oc:.4f} |"
            )
            grand_in += t["input"]
            grand_out += t["output"]
            grand_cost += ic + oc
        rows.append(
            f"| **Total** | **{grand_in:,}** | **{grand_out:,}** "
            f"| | | **${grand_cost:.4f}** |"
        )
        return "\n".join(rows)
