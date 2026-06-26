# Report-then-Summarize + Wider Revision Loop — Design

**Date:** 2026-06-26
**Scope:** Single-pitcher report path (`pipeline._run_pipeline`, consumed by `cli.py`). The morning path is untouched.

## Problem

Today the executive summary and BRIEF are written from the *specialist data*, in
parallel with a *pre-revision* writer. They never see the report that actually
ships — they summarize ingredients, not the finished narrative. Separately, the
anchor check → writer revision loop is capped at 3 passes.

Two goals:

1. **Summarization is a second step.** Write the report (including its anchor
   revision passes), *then* summarize the final narrative.
2. **Allow up to 5 revision passes** on the report's anchor/writer loop.

## Decisions (confirmed)

- Both the **executive summary** (3 metric bullets) and the **BRIEF** (2-3
  sentence voice summary) become second-step, fed the finished report.
- "5 revision passes" = bump `MAX_REVISIONS` 3 → 5 on the existing anchor loop.
  No separate revision loop for the summary step.
- Summarizers receive **report + grounding**: the final capsule is the subject;
  the clean specialist analyses + Key Signals the report was built from are
  attached as grounding. See the **Summary grounding contract** below for the
  exact, deterministic rules (this is where review gaps #1 and #2 are closed).
- BRIEF **moves to a mini model** (persona voice instructions still apply).

## Flow

**Before:**
```
spine → writer_input (signals + specialists)
      ├─ summary  (concurrent, fed writer_input, pre-revision)
      ├─ brief    (concurrent, fed writer_input, pre-revision)
      └─ writer → capsule → anchor loop (×3) → final capsule
```

**After:**
```
spine → writer_input → writer → capsule → anchor loop (×5) → FINAL capsule
                                                                └─ then, concurrently:
                                                                     ├─ summary (fed FINAL capsule + grounding)
                                                                     └─ brief   (fed FINAL capsule + grounding)
```

## Summary grounding contract (closes review #1, #2)

The grounding attached to each summarizer is **`writer_input`** — i.e. the
pitcher header + rendered Key Signals + the five **clean specialist prose
analyses** (post-audit). It is **not** the raw ground-truth metric tables
(those NORMAL/OUTLIER tables are the specialists' *inputs*, never assembled
into `writer_input`). The contract names it honestly and constrains its use:

1. **Subject of truth is the report.** The summary describes the finished
   capsule. Cite metric values **exactly as the report states them**.
2. **Grounding recovers, never corrects.** The attached analyses exist for one
   purpose: when the report makes a finding *qualitatively* ("the slider sharpened
   this outing") without a figure, the summarizer may pull the supporting metric
   from the analyses to anchor that same finding. The summarizer must **not**
   "correct" a number the report states, and must **not** flag report/grounding
   discrepancies — number-accuracy is the anchor loop's job, upstream.
3. **No new findings.** The summarizer must not introduce a finding the report
   did not make, even if the grounding contains one. If it isn't in the report,
   it isn't in the summary.

Rendered input shape (built by `build_summary_input(capsule, writer_input)`):
```
## FINISHED REPORT (summarize THIS; cite its numbers exactly as written)
{capsule}

## SOURCE ANALYSES (the clean specialist analyses the report was built from —
## reference ONLY to recover a metric the report stated qualitatively; do NOT
## correct the report's numbers and do NOT add findings absent from the report)
{writer_input}
```

## Changes

### 1. `config.py`
`MAX_REVISIONS = 3 → 5`.

### 2. `pipeline.py` — `_run_pipeline`
- Remove the two `asyncio.create_task(...)` launches for `summary` and `brief`
  that precede the writer (currently lines 1379-1384).
- After `_run_anchor_revision_loop` yields the final capsule, build
  `build_summary_input(final_capsule, writer_input)` and run `summary` + `brief`
  concurrently.
- **Empty-capsule guard:** if the final capsule is empty/whitespace, skip both
  summarizers and return empty `executive_summary` / `brief`. (The anchor loop
  itself short-circuiting on an empty capsule is a **non-goal** — an empty
  capsule is an upstream writer failure that the operator should see loudly
  elsewhere; the loop running harmlessly on empty is rare and not worth a
  branch here.)

New helper:
```python
def build_summary_input(capsule: str, writer_input: str) -> str:
    """Frame the finished report as the summary subject, with the clean
    specialist analyses attached as recover-only grounding (see contract)."""
```

### 3. Concurrency + error semantics (closes review #5)
Plain `asyncio.gather(..., return_exceptions=False)` raises on the first failure
and cancels the sibling — the opposite of degrade-to-empty. Therefore each
summarizer runs in its **own coroutine that catches its own exceptions and
returns the degraded empty value**, so no exception escapes to `gather`:
```python
async def _run_summary() -> list[str]:
    try:
        r = await agents.summary.run(**agent_kwargs(summary_input, _model_override))
        return _parse_bullets(r.output)
    except Exception:
        log.warning("Executive summary failed, skipping.", exc_info=True)
        return []

async def _run_brief() -> str:
    try:
        r = await agents.brief.run(**agent_kwargs(summary_input, _model_override))
        return r.output.strip()
    except Exception:
        log.warning("Brief failed, skipping.", exc_info=True)
        return ""

summary_bullets, brief_text = await asyncio.gather(_run_summary(), _run_brief())
```

### 4. Prompts
- `_EXECUTIVE_SUMMARY_PROMPT` (pipeline.py:434): reframe from "Given specialist
  analyses..." to "Given a finished scouting report (with the analyses it was
  built from attached as recover-only reference)...". Keep "every bullet cites a
  specific number"; add the grounding-contract rules verbatim in intent — cite
  the report's numbers, recover-don't-correct, no new findings.
- BRIEF input framing — **new contract `_BRIEF_FRAMING_FROM_REPORT`** that
  replaces `BRIEF.input_framing`. Because BRIEF now distills a finished,
  already-anchored report, thread selection and hedging have **already happened
  upstream in the writer**. Explicit survive/drop list:

  | Existing rule (`_BRIEF_FRAMING`) | Fate under report-distillation |
  |---|---|
  | Recent-appearance-vs-window is the frame | **Survives** — it's the report's frame; keep the "MOST RECENT appearance" + "trending/window" language |
  | Suppress EXPLAIN-THE-MODEL / "do NOT pause to explain the grading model" | **Survives** — still no room to teach the model in 2-3 sentences |
  | One voice; do not name/number/sequence specialists | **Survives** (the report is already one voice) |
  | Cite at most two metrics | **Survives** (lives in `_BRIEF_STRUCTURE`, unchanged) |
  | Pin thread to Key Signals Top Improvement/Concern; "Do not pick by your own judgment" | **Re-expressed** → "Lead with the report's central thread (its opening claim); do not re-derive a thread of your own." |
  | Hedge when Sample Size Caution present | **Re-expressed** → "Preserve the report's hedging — if the report states a finding tentatively, keep it tentative; never harden it." |
  | Fall back to single most important shift when signals absent | **Dropped** — the subject is always a concrete report; there is no signals-absent fallback case. |

- `_BRIEF_STRUCTURE` is **unchanged** (length/voice/2-metric/3-sentence rules).
  `test_brief_structure_*` assertions (which read `BRIEF.structure`) continue to
  pass unmodified.

### 5. `make_pipeline_agents`
- BRIEF agent switches from the main-model `_brief` factory to a mini model.
  Add `brief_settings` = mini model, `cap_thinking(thinking, "medium")`, a
  voice-leaning temperature (~0.6), `TOKEN_BUDGET_SMALL`. Keep `retries=3`;
  agent stays tool-free.
- BRIEF system prompt built from `build_system_prompt(persona, BRIEF)` with
  BRIEF now carrying `_BRIEF_FRAMING_FROM_REPORT`.

### 6. `_render_pipeline_data_sections` (closes review #9)
The EXECUTIVE SUMMARY and BRIEF sections currently render a one-line "Receives:
same input as writer" note. Replace each with a rendered example of the actual
runtime input — `build_summary_input("<final capsule>", "<writer_input>")` —
so `--print-prompts` / the data-file dump accurately reflect the summarizer
input shape for debugging.

### 7. Progress / perceived-hang (closes review #7)
Today the writer streams to stdout while summary/brief run in the background;
after this change the user sees the writer stream, then silence during the
anchor loop (up to 5 passes) and the summary pair. Emit a short **stderr**
progress line before the anchor loop ("revising report…") and before
summarization ("writing summary…") so the post-stream pause is not read as a
hang. stderr keeps the report on stdout clean.

### 8. Tests
- `test_pipeline.py`:
  - summaries run **after** the anchor loop and are fed the **final capsule**
    (not pre-revision `writer_input`); assert ordering/wiring.
  - `MAX_REVISIONS` is 5 (existing `test_max_revisions_constant_is_nonzero`
    still passes; bound assertions auto-track the constant).
  - **New:** BRIEF agent runs on the **mini** model (mirror how summary's mini
    wiring would be asserted) — guards against a silent regression to main.
  - **New:** BRIEF system prompt is built from `_BRIEF_FRAMING_FROM_REPORT`
    (assert a token unique to the new framing is present).
  - `test_brief_agent_has_no_skill_toolset` stays valid (mini BRIEF is still
    tool-free).
- `test_personas.py`:
  - `test_brief_framing_pins_thread_to_top_signals`,
    `test_brief_framing_honors_sample_size_caution`,
    `test_brief_framing_has_fallback_when_signals_absent` → **rewritten** to the
    re-expressed/dropped rules above (lead-with-report's-thread, preserve-report's-
    hedging, no signals-absent fallback).
  - `test_brief_framing_contrasts_recent_against_window` and
    `test_brief_framing_suppresses_model_teaching` → **survive unchanged**.
  - `test_brief_structure_*` → survive unchanged.
- `test_voice_golden.py`: regenerate/adjust any BRIEF golden tied to the old
  framing.
- Confirm `morning.py` tests are unaffected (it uses `run_analysis_spine` +
  digest summaries, not `agents.summary` / `agents.brief`).

## Error handling (summary)
- Final capsule empty/whitespace → skip summarization, return empty fields.
- summary or brief coroutine raises → caught inside its own coroutine, logs a
  warning, degrades that field to empty; the sibling is unaffected (see §3).

## Latency / cost (closes review #4)
Two compounding costs, stated honestly:
- **Summary step** no longer overlaps writer streaming; it runs after the anchor
  loop as one concurrent mini-model pair. Modest, bounded.
- **`MAX_REVISIONS` 3 → 5** raises the worst-case writer-revision count by two,
  and writer revisions use the **main** model (not mini). The anchor loop
  **early-exits the instant a check is clean** (pipeline.py:1321-1322), so in
  practice most runs revise 0-1 times and rarely approach the ceiling. We have
  **no revision-count telemetry** to quote a p95; 5 is therefore an
  **unvalidated ceiling**, chosen per the request, not from data. If runs are
  observed hitting 4-5 regularly, revisit the writer/anchor prompts rather than
  the cap.

## Non-goals
- No change to the morning/digest path.
- No separate revision/critique loop for the summary step.
- No change to the writer, specialists, audit, or signal-extraction spine.
- Anchor loop does not short-circuit on an empty capsule (see §2).
- Not switching `agents.summary` to `output_type=ExecutiveSummary` (the unused
  `ExecutiveSummary` model at pipeline.py:457 is a separate, optional cleanup).
