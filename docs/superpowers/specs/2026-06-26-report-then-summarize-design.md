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
- Summarizers receive **report + data grounding**: the final capsule is the
  subject; `writer_input` (Key Signals + clean specialist analyses) is attached
  as reference for accurate metric values only — not as additional findings.
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

## Changes

### 1. `config.py`
`MAX_REVISIONS = 3 → 5`.

### 2. `pipeline.py` — `_run_pipeline`
- Remove the two `asyncio.create_task(...)` launches for `summary` and `brief`
  that precede the writer (currently ~lines 1379-1384).
- After `_run_anchor_revision_loop` yields the final capsule, build a combined
  summary input and run `summary` + `brief` concurrently via `asyncio.gather`.
- Skip both (empty result) if the final capsule is empty/whitespace.
- Keep the existing per-agent try/except so a failed summary/brief degrades to
  an empty value rather than crashing the run.

New helper:
```python
def build_summary_input(capsule: str, writer_input: str) -> str:
    """Frame the finished report as the summary subject, with source data
    attached as metric-grounding reference (not new findings)."""
```
Rendered shape:
```
## FINISHED REPORT (summarize THIS)
{capsule}

## SOURCE DATA (reference only — exact metric values; do NOT introduce
## findings the report did not make)
{writer_input}
```

### 3. Prompts
- `_EXECUTIVE_SUMMARY_PROMPT`: reframe from "Given specialist analyses..." to
  "Given a finished scouting report (with its source data attached for
  reference)...". Keep the "every bullet cites a specific number" rule; clarify
  that bullets summarize the report and use source data only to verify exact
  values, never to add findings absent from the report.
- BRIEF input framing: add a report-oriented variant (e.g.
  `_BRIEF_FRAMING_FROM_REPORT`) used to build the BRIEF agent's system prompt.
  "INPUT: a finished scouting capsule (distill THIS), followed by the source
  data it was built from (reference for exact metric values only). Distill the
  report to 2-3 sentences leading with its central thread; do not introduce
  findings the report did not make." `_BRIEF_STRUCTURE` (length/voice rules) is
  unchanged.

### 4. `make_pipeline_agents`
- BRIEF agent switches from the main-model `_brief` factory to a mini model.
  Add `brief_settings` = mini model, `cap_thinking(thinking, "medium")`, a
  voice-leaning temperature (~0.6), `TOKEN_BUDGET_SMALL`. Keep `retries=3`;
  agent stays tool-free.
- BRIEF system prompt built from the new report-oriented framing contract.

### 5. `_render_pipeline_data_sections`
Update the EXECUTIVE SUMMARY and BRIEF "User Message" notes from "Receives:
same input as writer" to "Receives: the final report narrative + source data."

### 6. Tests
- `test_pipeline.py`: update ordering/wiring — summaries run after the anchor
  loop and are fed the final capsule; `MAX_REVISIONS` is 5.
- `test_personas.py` / `test_voice_golden.py`: update BRIEF framing expectations
  and any fixture asserting BRIEF input.
- Confirm `morning.py` tests are unaffected (it uses `run_analysis_spine` +
  digest summaries, not these two agents).

## Error handling
- Final capsule empty/whitespace → skip summarization, return empty
  `executive_summary` / `brief` (no crash).
- summary or brief agent raises → log warning, degrade that field to empty
  (existing behavior preserved).

## Tradeoff
Summary + brief no longer overlap writer streaming; they run after the anchor
loop. Net added latency is one concurrent summary-pair on mini models — the
accepted cost of summarizing the report that actually ships.

## Non-goals
- No change to the morning/digest path.
- No separate revision/critique loop for the summary step.
- No change to the writer, specialists, audit, or signal-extraction spine.
