# Output Cleanup — Overview & Design

**Date:** 2026-07-05
**Status:** Approved design, pending implementation plans
**Topic:** Make the tool's user-facing outputs (report, morning digest, scoreboard, scout table) consistent by fixing three binding/rendering seams — without re-architecting the narration pipeline.

---

## 1. Problem

The outputs "feel messy and inconsistent." Investigation shows the underlying
type system is **already clean** — `Persona` (voice), `OutputContract`
(structure/length/framing), and `NarrationMode` (analytical framing) are
correctly separated (`personas.py:64-107`, `personas.py:496`). The inconsistency
lives at three edges, not in the architecture:

1. **Structure rides on persona.** `NarrationMode.contracts` maps
   `persona_id → OutputContract` (`personas.py:539`), so `--persona generic`
   silently swaps *structure* (six `##` sections + a table), not just *voice* —
   contradicting `Persona`'s own docstring: "carries tone/vocabulary only — no
   length or structure" (`personas.py:66`).
2. **The board is rendered by two binaries, three renderers, and three copies of
   the category list.** `pitcher-scout` (`scout_cli.py`) and
   `pitcher-narratives scoreboard` (`cli.py:622`) overlap ~90%.
3. **Reader content and QA content share one stdout stream** in the report path
   (`cli.py:264-393`), and the capsule is printed twice when fact-revision fires.

## 2. Workstreams

Each has its own design spec (this doc is the umbrella):

| WS | Spec | Risk | Scope |
|----|------|------|-------|
| 1 | `2026-07-05-board-category-unification-design.md` | low | One category registry; delete `pitcher-scout`; `scoreboard --format table\|md\|json` |
| 2 | `2026-07-05-report-diagnostics-separation-design.md` | low–med | Reader doc vs diagnostics on separate surfaces; kill double-capsule |
| 3 | `2026-07-05-format-axis-decoupling-design.md` | med–high | New `Format` axis orthogonal to `Persona`; collapse 8 contracts → 3 framings + 3 voices + 4 formats |
| 4 | `2026-07-05-validation-parity-design.md` | med | Thread `ValidationPolicy` through morning; expose `morning --strict` |

## 3. Decisions (2026-07-05)

Recorded so plans don't re-litigate them:

- **WS3 — full decouple.** Structure becomes an orthogonal `--format` flag;
  persona is voice-only, matching the types' existing claim. The
  general-fan-gets-sections coupling was *not* intentional product design.
- **`pitcher-scout` — remove outright.** No deprecation alias. Only
  `pitcher-narratives scoreboard` remains; the fixed-width table survives as
  `scoreboard --format table`.
- **Deliverable — specs for all four**, then implement per-workstream plans.

## 4. Recommended sequencing

1. **WS1** — highest clarity-per-effort, no prompt/LLM risk. Do first.
2. **WS2** — independent; mostly mechanical except the streaming fix.
3. **WS4** — small, independent.
4. **WS3** — the real refactor; do last, behind the `test_voice_golden.py`
   guardrail, once the cheap wins are banked.

WS1/2/4 are each a focused PR. WS3 warrants its own implementation plan under
`docs/superpowers/plans/`.

## 5. Non-goals

- No change to the analysis spine, specialists, signal extraction, or the
  grounding stack.
- No change to what the modes *mean* (report/recap/changes) or their validation
  *policy values* — WS4 only makes the existing policy reach the morning path.
- No new personas or modes.
