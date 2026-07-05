# Report / Diagnostics Separation (WS2) — Design

**Date:** 2026-07-05
**Status:** Approved design, pending implementation plan
**Topic:** Split the `report` command's reader-facing document from its QA/diagnostics appendix, and stop printing the capsule twice.

---

## 1. Problem

`_emit_mode_result` (`cli.py:264-393`) prints one interleaved stdout stream per
mode that mixes two audiences:

**Reader-facing:** `# <mode.title>` (`cli.py:537`), streamed capsule,
`## Executive Summary` + `## Brief` (`cli.py:299-311`), `**Verification:**` stamp
(`cli.py:288-295`).

**QA/pipeline:** `## Corrected Capsule` (`cli.py:276`), then
`--- / ## Diagnostics` with `### Stuff Analysis`, `### Data Audit`,
`### Capsule Fact-Check`, `### Value Parity (advisory)`, `### Anchor Check`,
`### Hallucination Check` (`cli.py:315-390`).

Two specific reader-hostile behaviors:

1. **The capsule prints twice on revision.** When `capsule_revised` is true, the
   draft is streamed live, then the verified capsule is *reprinted* under
   `## Corrected Capsule` (`cli.py:275-281`). The reader sees the narrative twice
   and must know the second is authoritative.
2. **QA noise is inline.** Diagnostics is emitted to the same stream as the
   report on every run, so the deliverable is buried in fact-check tables even
   when everything passes.

For contrast, `morning` already writes QA to a *separate artifact*
(`validation.json`, `morning.py:4-6`) and keeps `digest.md` clean.

## 2. Key facts established (with evidence)

- The QA data all lives on `PipelineResult` (fields consumed at
  `cli.py:275-390`): `capsule_revised`, `narrative`, `audit_flags`,
  `capsule_audit_flags`, `anchor_warnings`, `revision_count`,
  `value_parity_warnings`, `specialists`. Nothing new needs computing — this is
  a *rendering/routing* change.
- The `**Verification:**` stamp is intentionally reader-facing ("travels with the
  document", `cli.py:283-284`); the UNVERIFIED banner + exit code remain the
  CI-facing signals. Keep the stamp in the reader doc.
- The double-capsule exists because the capsule is *streamed* before the
  fact-revision loop resolves. The comment at `cli.py:271-274` documents this as
  deliberate ("never let the headline text be the stale one"). Fixing it means
  changing *when* we stream, not just what we print.
- `morning` is the precedent for the target split: reader artifact + sidecar QM
  file, QA checks omitted from the reader surface (`morning.py:2-16`).

## 3. Target design

### 3.1 Route diagnostics off the reader stream

- Default `report` stdout = reader document only: title, capsule, executive
  summary, brief, verification stamp.
- Diagnostics appendix emitted only under `-v/--verbose` (already an arg,
  `cli.py`) **or** written to a sidecar (`--diagnostics <path>` / an artifact dir
  mirroring morning). Recommend: `-v` prints the appendix to **stderr**; a
  `--diagnostics-file` writes structured JSON (parity with `validation.json`).
- The UNVERIFIED path still prints its one-line banner to stderr and sets the
  exit code regardless of verbosity (unchanged CI contract).

### 3.2 Kill the double capsule

Two options; pick at plan time:

- **(A) Buffer-then-emit (preferred):** don't stream the capsule live; run the
  fact-revision loop, then print the final capsule once. Simplest reader output;
  loses live streaming UX.
- **(B) Stream + in-place correction marker:** keep streaming, but on revision
  print a single terse note ("_capsule fact-revised; showing corrected
  version_") followed by the final capsule, and drop the second full-width
  `## Corrected Capsule` heading. Retains streaming; still one authoritative
  block.

Preference is **(A)** for report (the document is the product; streaming matters
less than a clean artifact), keeping streaming available under a flag if desired.

### 3.3 Result

- `report` stdout is the report — nothing else — by default.
- Diagnostics is opt-in and/or a sidecar, matching `morning`.
- The capsule appears exactly once.

## 4. Migration / plan sketch

1. Extract the diagnostics block (`cli.py:315-390`) into a
   `render_diagnostics(pipe_result) -> str` helper (pure, testable).
2. Gate its emission on `-v`/`--diagnostics-file`; route to stderr/file.
3. Implement the double-capsule fix (option A) in `_emit_mode_result` +/‑ the
   streaming call in `pipeline.py`.
4. Update `docs/daily-runs.md` if it shows report stdout with diagnostics inline.

## 5. Testing

- `test_cli`: default stdout contains reader sections and **not** `## Diagnostics`;
  `-v` (or `--diagnostics-file`) surfaces it; capsule appears once on both the
  revised and unrevised paths; UNVERIFIED banner + exit code unchanged.

## 6. Open questions

- **A vs B** for streaming (§3.2). If live streaming is a valued UX today,
  prefer B.
- Diagnostics sink: stderr-under-`-v` vs a JSON sidecar vs both. Sidecar gives
  parity with morning's `validation.json` and is machine-consumable — likely
  worth doing even if `-v` also prints a human view.
