# Capsule Fact-Checking Layer (A + B) — Design

**Date:** 2026-06-28
**Scope:** Single-pitcher report path (`pipeline._run_pipeline`, consumed by `cli.py`). Morning/digest path untouched.

## Problem

There is no numeric backstop on the final capsule. `check_hallucinated_metrics`
(cli.py:320) is a metric-*name* check, not a *value* check. The anchor checker
validates the capsule only against the specialist *prose* synthesis, not against
ground truth (see [the report-then-summarize design](2026-06-26-report-then-summarize-design.md)).
The writer recombines across specialists, so it can introduce a numeric error or
fabrication that no single-specialist auditor ever saw, and nothing downstream
catches it.

This adds a two-check fact-checking layer that runs on the final capsule, after
the anchor revision loop:

- **A — deterministic value-parity:** a cheap, wide advisory net.
- **B — one-shot LLM capsule auditor:** a precise semantic check that can drive
  one corrective revision.

They are complementary: A is the cheap wide net (advisory), B is the narrow
precise one (can revise). Blocking logic lives in B, never in A.

## Flow

```
anchor loop → final capsule
   → B: capsule audit (1 mini call vs ground truth)
        └─ if flagged: 1 writer revision → corrected capsule
   → A: value-parity on the corrected capsule → advisory warnings
   → _run_summaries (already runs here; reflects the corrected capsule)
```

B runs before A so the LLM gets first crack and A scores the shipped capsule.
Summaries already run after the anchor loop on the final capsule (current
branch), so with B before `_run_summaries` the summaries reflect B's corrected
capsule — desired, no scheduling change.

## Check A — deterministic value-parity (advisory, never blocking)

A pure function, no I/O, heavily unit-tested with real-capsule fixtures:

```python
def check_value_parity(capsule: str, union: ValueUnion) -> ValueParityReport: ...
```

### Source-of-truth union — "everything the writer legitimately saw"

Built from three legs (all text the writer's input was drawn from):

1. the rendered specialist **inputs** (raw ground truth: `_get_specialist_input_text(name, ctx)` for all five — these carry the NORMAL/OUTLIER tables),
2. the clean specialist **outputs** (post-audit prose),
3. the rendered **key-signals** block (`render_key_signals`) — included because the signal extractor reformulates ("S+ 128" → "128 on the slider") and that drift would otherwise false-flag the very signals the writer must surface.

A capsule value that traces to any leg is legitimate: leg 1 catches direct
ground-truth citations, legs 2–3 catch faithful restatements of already-audited
paraphrase. A pure fabrication (a number in neither set) is what A exists to
catch. A's structural blind spot — a specialist hallucination the auditor missed
is faithfully present in leg 2 — is closed by B, not by tightening A.

### Matching: class-aware (metric_class, value) tuples

**Requirement:** union and capsule values are compared as `(metric_class, value)`
tuples, NOT a global number pool. A capsule `(velo, 81)` must not be satisfied by
a union `(zone_pct, 81)` — "81 mph" cannot match "81% zone rate." Only flag a
capsule value when its class is determinable AND no same-class union value
matches within tolerance. If a capsule number's class is indeterminate, do NOT
flag it (advisory wide net favors precision over recall).

**Requirement (bidirectional paraphrase):** matching must work in both
directions — a capsule "X% above average" must match a union plus-grade via
`(S+ − 100)/100`, and a capsule plus-grade must match a union "X% above average".
Do not assume one canonical form.

### Tolerance by semantic class (inside advisory)

No single global epsilon. Split by class:

- **Direct grades/values** (S+/P+/L+, xRV100, velo, pfx_x/pfx_z, zone%/chase%/CSW%): rounding tolerance ±0.5, or ±1 for whole-number grades (S+/P+/L+). "81 mph" for 81.3 passes; "80 mph" for 81.3 flags.
- **Deltas/derived** ("-1.6 mph", "+5pp", "28% above average"): match against a value already in the union with ±1-unit tolerance; accept the plus-grade paraphrase "X% above average" ↔ `(S+ − 100)/100`. Do NOT verify arithmetic — flag only if the underlying plus-grade is nowhere in the union.
- **Hedged numbers** ("roughly/about/around N"): relax tolerance further or skip flagging entirely — a hedge is the writer signaling uncertainty, which is desirable.

### Output

```python
class ValueParityReport(BaseModel):
    unmatched: list[str]   # flagged value tokens with surrounding context
    @property
    def is_clean(self) -> bool: return not self.unmatched
```

Advisory only: surfaced in `PipelineResult.value_parity_warnings` and printed by
cli (mirroring `check_hallucinated_metrics`). Never triggers a revision. Rationale:
deterministic extraction is inherently noisy (the existing `_METRIC_PATTERN`
already tolerates `_S/_P` suffixes; "two-seamer"→"two", "mid-80s", "around 81" are
edge cases), and the revision loop has no degeneration detection — a blocking
matcher would burn revisions degrading the capsule on regex false positives.

## Check B — one-shot LLM capsule auditor (drives one revision)

A capsule-oriented variant of the data auditor, run **once** (not looped).

- **Prompt:** new `_CAPSULE_AUDITOR_PROMPT` — same spirit as `_DATA_AUDITOR_PROMPT` (flag METRIC_CONTRADICTION, DIRECTION_ERROR, FABRICATED_DATA, etc.) but framed for a finished narrative checked against the combined ground truth. Reuses `AuditResult`/`AuditFlag`.
- **Ground truth fed to B:** the raw specialist **inputs** only (the data tables via `_get_specialist_input_text` ×5) — the actual data, not the specialist prose. (Distinct from A's union, which intentionally includes specialist outputs.)
- **Input builder:** `_build_capsule_audit_input(ground_truth, capsule) -> str`.
- **Model/settings:** mini model, dedicated `capsule_auditor_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.1, max_tokens=TOKEN_BUDGET_MEDIUM, mini=True)`. MEDIUM (not SMALL) because B's input is large (all ground truth + capsule); the report-then-summarize session proved Gemini thinking consumes the SMALL budget and truncates large-input calls. Thinking kept (medium) for semantic reasoning; MEDIUM gives headroom so the structured `AuditResult` can't truncate. `retries=5` (mirrors the existing auditor).
- **On flags:** if `AuditResult` is not clean, run **one** writer revision with the flags via a new `build_fact_revision_message(capsule, flags) -> str` (capsule + flags → "correct only these factual issues, preserve everything else"), producing the corrected capsule. No loop.
- **Degrade-safe:** if B's agent call raises, log a warning and skip (capsule unchanged) — non-fatal, like the other auxiliary agents.

## Data flow & results

`PipelineResult` gains:

- `capsule_audit_flags: list[AuditFlag] = []` — B's findings.
- `capsule_revised: bool = False` — whether B triggered a revision.
- `value_parity_warnings: list[str] = []` — A's advisory unmatched values.

`cli.py` prints both B's flags (if any) and A's warnings, mirroring the existing
hallucination-report surfacing. `data.py`/the data file include them for tracing.

## Error handling

- B agent raises → log warning, capsule unchanged, `capsule_revised=False`, empty flags.
- B writer revision raises → log warning, keep the pre-revision (post-anchor) capsule.
- A is pure; on an empty capsule it returns no warnings (the pipeline already guards empty capsules upstream).

## Testing

- **A:** unit tests with real-capsule fixtures — direct-grade match within/outside tolerance; delta/paraphrase bidirectional match; the `(velo,81)` vs `(zone_pct,81)` cross-class collision must NOT match; hedged-number relaxation; indeterminate-class values are not flagged; a genuinely fabricated value IS flagged.
- **B:** TestModel smoke (clean → no revision; flagged → one revision, `capsule_revised=True`); degrade-on-error; input builder shape.
- Existing `test_pipeline.py` / `test_morning.py` stay green; morning path unaffected.

## Non-goals (related, separate follow-ups)

- Re-auditing revised specialist outputs (critique #3) — closes A's leg-2 blind spot at the source; separate.
- Revision-loop degeneration detection (critique #9) — separate.
- No change to the anchor checker, the summarizers, or the morning/digest path.
