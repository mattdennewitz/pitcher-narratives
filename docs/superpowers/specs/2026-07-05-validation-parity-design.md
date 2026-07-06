# Validation Parity (WS4) — Design

**Date:** 2026-07-05 (revised 2026-07-06 for the single-voice / recap-mode code)
**Status:** Approved design, pending implementation plan
**Topic:** Make the report-vs-morning validation difference explicit and
user-controllable instead of a hardcoded skip.

---

## 0. Revision note (2026-07-06)

The original spec's premise — "morning skips the anchor-revision loop **and**
the hallucination check" — is **stale**. Since the recap-mode / mode-based-
narration work landed, `render_recap` (the function morning calls per pick)
reuses the shared writer+validation core at RECAP's `ValidationPolicy` depths
(`anchor_depth=1, fact_depth=2`) and runs `check_value_parity`, exactly like
`report --mode recap`. Verified against current code (`pipeline.py:2404-2413`
vs `pipeline.py:2458-2473`).

**The only validation difference that remains** is `check_hallucinated_metrics`:
the report path calls it in `cli.py:298`; morning never does. So WS4 shrinks to
"expose the hallucination cross-check for morning," plus fixing the now-inaccurate
`morning.py` module docstring. The "thread a `ValidationPolicy(0,0)` skip through
morning" framing from the original §3.1 is obsolete and is dropped.

Single-voice (WS3) also removed `persona` from `check_hallucinated_metrics`
(`pipeline.py:2745`, now `check_hallucinated_metrics(report_text: str)`), so
invoking it per morning entry needs only the entry's narrative — no persona,
no extra plumbing.

## 1. Problem

The same RECAP capsule is validated *almost* identically by both commands, with
one deliberate gap:

- **`report --mode recap`** runs `_render_capsule` at RECAP's policy
  (`anchor_depth=1, fact_depth=2`), `check_value_parity`, **and**
  `check_hallucinated_metrics` (`cli.py:298`).
- **`morning`** runs the identical `_render_capsule` (via `render_recap`,
  `pipeline.py:2404`) and `check_value_parity` (`pipeline.py:2413`), but
  **omits `check_hallucinated_metrics`** to keep the high-volume daily run fast.

That single gap is:
1. **Invisible to users** — surfaced only in a `morning.py` module docstring
   (which is itself now *inaccurate*: it claims morning is "not anchor-checked,"
   but morning runs the anchor loop at depth 1).
2. **Not toggleable** — a user who wants a fully-cross-validated morning digest
   (e.g. for a published newsletter) has no path to it.

## 2. Key facts established (with evidence)

- `render_recap` (`pipeline.py:2384`) is the shared recap renderer for both
  morning (`pick` set) and standalone. It calls `_render_capsule` with
  `anchor_depth=RECAP.validation.anchor_depth` (=1) and
  `fact_depth=RECAP.validation.fact_depth` (=2) (`pipeline.py:2406-2407`) and
  `check_value_parity` (`pipeline.py:2413`). Morning therefore already
  anchor-checks and fact-audits each entry.
- `check_hallucinated_metrics(report_text: str) -> HallucinationReport`
  (`pipeline.py:2745`) is pure and persona-free (post-WS3). Its **only** caller
  is `cli.py:298` (report path, inside `build_diagnostics_dict`). It is never
  called from `morning.py`.
- `NarrationMode.validation` (`ValidationPolicy`, `personas.py:245`) carries
  `anchor_depth`/`fact_depth`. `RECAP.validation = (1, 2)` (`personas.py:332`).
  Morning already consumes this via `render_recap` — no threading gap for
  anchor/fact.
- Morning already writes a per-run `validation.json` via
  `_build_validation_payload` (`morning.py:60`, written at `morning.py:230`) —
  a natural home for per-entry hallucination results under strict mode.
- Morning fans entries out concurrently (`asyncio.gather`, `morning.py:165`).
  The hallucination check is a pure, in-process string scan (no LLM round-trip),
  so it is cheap; it stays opt-in only to preserve byte-identical default output
  and because flagging behavior changes the digest.
- The digest footer is `cost_block` (`morning.py:202`, assembled at
  `digest.py:190`) — the place to stamp the validation mode.

## 3. Target design

### 3.1 Expose `morning --strict`

- `--strict` (boolean flag on the `morning` subcommand, `cli.py:115`) runs
  `check_hallucinated_metrics` on each entry's narrative after `render_recap`,
  and folds any hallucinated-metric flags into the entry's UNVERIFIED
  determination (same treatment as residual/value-parity flags today,
  `morning.py:177-184`).
- Without `--strict`, behavior is **byte-identical to today** (no hallucination
  call, no new flags).

### 3.2 Record results

- Per-entry hallucination results (flagged metrics / clean) are recorded into the
  existing `validation.json` payload (`_build_validation_payload`, `morning.py:60`)
  when `--strict` is set. Fast mode records nothing new.

### 3.3 Surface the choice

- `morning --help` states that the default digest skips the hallucination
  cross-check and points to `--strict`.
- The digest footer (`cost_block`) gains a one-line stamp:
  `validation: fast (hallucination check skipped)` vs `validation: strict`.
- Fix the stale `morning.py` module docstring (`morning.py:8-14`) to say what is
  actually true: morning runs the anchor + fact-audit loops at RECAP depths and
  value-parity, and by default omits only the hallucination cross-check (opt in
  with `--strict`).

### 3.4 Deliberately NOT doing

- No new `ValidationPolicy(0,0)` / `SKIP` sentinel — there is no anchor/fact skip
  to represent (morning already runs them).
- No new field on `ValidationPolicy` for the hallucination check. The report path
  does not gate hallucination on policy either (it always runs it in `cli.py`);
  adding a policy field only for morning would be asymmetric. `--strict` is a
  plain boolean threaded into `run_morning`. Revisit only if a third validation
  tier emerges.

## 4. Migration / plan sketch

1. Fix the `morning.py` module docstring to reflect current validation reality.
2. Add `--strict` to the `morning` subcommand (`cli.py:115`); thread it into
   `run_morning` (`morning.py:80`) as a boolean param (default `False`).
3. When strict, call `check_hallucinated_metrics(recap_result.narrative)` per
   entry (in the `_build_pick`/result-assembly path, `morning.py:143-186`), fold
   its flags into the UNVERIFIED banner logic, and pass results to
   `_build_validation_payload` for `validation.json`.
4. Add the footer stamp (fast/strict) to `cost_block` and the `--help` note.

## 5. Testing

- `test_morning`: default path makes **no** `check_hallucinated_metrics` call
  (behavior preserved, output byte-identical); `--strict` calls it per entry,
  folds a synthetic hallucinated metric into the UNVERIFIED count, and records it
  in `validation.json`; the footer stamp reflects the mode.
- A regression test asserting the default digest text is unchanged by the flag's
  addition.

## 6. Open questions — resolved

- **Skip representation (`(0,0)` vs `SKIP` sentinel):** moot. There is no
  anchor/fact skip; the only toggle is the hallucination check, a boolean.
- **Boolean `--strict` vs `--validation {fast,strict}`:** boolean `--strict`.
  Widen only if a third policy emerges.
