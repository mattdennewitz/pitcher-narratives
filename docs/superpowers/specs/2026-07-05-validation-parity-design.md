# Validation Parity (WS4) — Design

**Date:** 2026-07-05
**Status:** Approved design, pending implementation plan
**Topic:** Make the report-vs-morning validation difference explicit and
user-controllable instead of a hardcoded skip.

---

## 1. Problem

The same RECAP capsule is validated differently depending on which command
emitted it:

- **`report --mode recap`** runs the full terminal-layer gate: anchor-revision
  loop and `check_hallucinated_metrics` (invoked in `cli.py`'s report path),
  bounded by the mode's `ValidationPolicy` (`RECAP` = `anchor_depth=1,
  fact_depth=2`, `personas.py:559-561`).
- **`morning`** deliberately **skips** the anchor-revision loop and hallucination
  check for speed (documented at `morning.py:8-16`). Each entry is still run
  through the specialist audit/revise loop inside `run_analysis_spine`, but the
  synthesized capsule is not anchor-checked or metric-cross-validated.

This is an intentional trade-off, but it is:
1. **Invisible to users** — surfaced only in a module docstring, not in `--help`,
   the digest, or any artifact.
2. **Not toggleable** — a user who wants a fully-validated morning digest (e.g.
   for a published newsletter) has no path to it.

## 2. Key facts established (with evidence)

- `NarrationMode` already carries a `ValidationPolicy`
  (`personas.py:521-523`): `anchor_depth`, `fact_depth`. The report path threads
  it into the anchor + capsule-audit loops. The mechanism exists; morning just
  doesn't consume it.
- The validation building blocks are pure/exported and dependency-injected:
  `check_hallucinated_metrics` and `check_value_parity` are pure; the anchor and
  capsule-audit loops take agents + depths as parameters (per the mode-narration
  design, `2026-06-29-mode-based-narration-design.md` §2). Reaching parity is
  *"supply agents + policy to the morning path,"* not new logic.
- `morning` writes a `validation.json` artifact already (`morning.py:4-6`), so
  there is a natural home for per-entry validation results if the strict path
  runs.
- Morning fans out entries concurrently (`morning.py` uses `asyncio`); the strict
  gate adds LLM round-trips per entry, so it must stay opt-in for the default
  fast path.

## 3. Target design

### 3.1 Thread the policy through morning

- Morning consumes the same `ValidationPolicy` the mode defines, instead of a
  hardcoded skip. Default morning uses a `ValidationPolicy(anchor_depth=0,
  fact_depth=0)` (or an explicit `SKIP` sentinel) — i.e. the current behavior,
  but *named and derived from policy* rather than an omission in code.
- The anchor/hallucination invocation logic used by the report path is shared so
  morning entries can run it when policy depth > 0.

### 3.2 Expose `morning --strict`

- `--strict` selects the full RECAP `ValidationPolicy` (`anchor_depth=1,
  fact_depth=2`) for every entry, and records per-entry results into
  `validation.json`.
- Without `--strict`, behavior is byte-identical to today (fast path).

### 3.3 Surface the choice

- `morning --help` states that the default digest skips anchor/hallucination
  validation and points to `--strict`.
- The digest footer (already carries a cost/note block, `digest.py:152-155`)
  gains a one-line validation-mode stamp: `validation: fast (anchor/hallucination
  checks skipped)` vs `validation: strict`.

## 4. Migration / plan sketch

1. Define the fast/skip policy explicitly (sentinel or zero-depth) and make
   morning read `mode.validation` (or a CLI override) instead of skipping in code.
2. Share the report path's anchor + hallucination invocation so morning can call
   it under policy.
3. Add `--strict` to the `morning` subcommand (`cli.py:121`); thread into
   `run_morning` (`morning.py:80`).
4. Add the footer stamp + `--help` note.

## 5. Testing

- `test_morning`: default path makes no anchor/hallucination calls (behavior
  preserved); `--strict` runs them and populates `validation.json`; footer stamp
  reflects the mode.

## 6. Open questions

- Represent "skip" as `ValidationPolicy(0, 0)` vs a distinct `SKIP` sentinel?
  Zero-depth is simpler if the loops already no-op at depth 0 — verify the loop
  guards before choosing.
- Should `--strict` be a boolean, or a `--validation {fast,strict}` choice to
  leave room for intermediate policies? Boolean now; widen only if a third policy
  emerges.
