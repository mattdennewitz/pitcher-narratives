# Mode-Based Report Narration — Design

**Date:** 2026-06-29
**Status:** Approved design, pending implementation plan
**Topic:** Split the single report-narration path into three first-class narration modes that share one grounded analysis spine.

---

## 1. Problem

Report narration is "all in one" today. A single writer pass composes the
CAPSULE, then anchor-revises it, then report-then-summarize distills the BRIEF
and executive summary — one prompt carrying too many concerns. We want three
distinct narration modes, each with a focused prompt, **without** duplicating
the grounding (league baselines, NORMAL/OUTLIER tags, temporal context) or the
"first-wave" specialist analysis. Targets: **increased accuracy** and **overall
maintainability**.

### The three modes

1. **REPORT** — analyze a span of time; overall analysis; the scouting report.
   Roughly what exists today.
2. **CHANGES** — observations and key insights from the most recent *X*
   appearances vs the prior *Y* appearances; focus on changes / trends.
3. **RECAP** — website executive brief: trends from the *most recent* appearance.

---

## 2. Key facts established (with evidence)

These shaped the design and are recorded so the plan doesn't re-litigate them.

- The analysis spine already returns a shared `AnalyzedContext` and is already
  called by **both** the report path (`pipeline.py:1343` via `_run_pipeline`)
  and morning (`morning.py:113`). We are formalizing a boundary that exists, not
  inventing one. **But the spine consumes a single `PitcherContext` today** —
  the multi-window enrichment (§5) is genuinely new work, not a side effect of
  the layering.
- Window model today is **day-based only**: `filter_to_window(df, window_days)`
  (`data.py:433`) is the sole slicer; there is **no appearance-count slicer**.
  `PitcherData.window_appearances` is one pre-filtered frame consumed directly
  by the engine (`tto.py:117`, `engine/_common.py:273`). `assemble_pitcher_context`
  (`context.py:106`) runs every `compute_*` exactly once. `PitchTypeSummary`
  carries paired `window_*`/`season_*` fields (`engine/arsenal.py`). Making
  context "multi-window" is a real shape change.
- There is **no 2,000-token budget test**; the budget is enforced structurally
  by `_MAX_PITCH_TYPES = 4` (`context.py:48`). Any refactor must preserve the
  per-frame top-4 truncation.
- Validation pieces are **partly reusable already**: `check_value_parity`
  (`value_parity.py:102`) and `check_hallucinated_metrics` (`pipeline.py:1943`)
  are pure and exported. `_run_anchor_revision_loop` (`pipeline.py:1399`) and
  `_run_capsule_audit` (`pipeline.py:1526`) are private but **already
  dependency-injected** (agents + per-call depths are parameters) — reuse means
  *publish + supply agents from `make_pipeline_agents`*, not "extract bound logic."
- Morning deliberately **skips** anchor + hallucination checks for speed
  (`morning.py:8-14`). Editorial fields (`category`/`angle`/`conviction`) live
  **only** on `CurationPick` (`curator.py:43`) — selector output, **not**
  reconstructable from `AnalyzedContext`/`PitcherContext`.
- **Observability gap:** the anchor and capsule loops emit no `tracker.record(...)`
  and nothing persists `PipelineResult`'s flag counts. The capsule flag/revision
  rate has therefore **never been measured**. The closest on-disk proxy is the
  *specialist* audit→revise loop: **35.3% flag rate, 1.0 revision per flagged**
  (60/170 across 34 pitchers, 4 runs; range 27–45%). Capsule rubric differs
  (anchor fidelity + fact-check on synthesized prose), so treat 35% as an upper
  stand-in, not a measured capsule rate.
- `build_story_cue` (the raw-DataFrame variant, `digest.py:47`) is **dead** in
  production — referenced only by its own `__all__` entry and `test_digest.py`.
  The live path is `build_story_cue_from_context` (`digest.py:101`).
- `test_fact_parity.py:451` asserts string-containment on the **cue string** from
  `build_story_cue_from_context`. A RECAP that writes from `AnalyzedContext`
  instead of a cue invalidates the test's premise → **rewrite, not tweak**.

---

## 3. Target architecture

```
load_pitcher_data(frames)              ← enriched: build all temporal slices
        ↓
MultiFrameContext { frames: dict[TemporalFrame, PitcherContext] }   ← wrapper (§5)
        ↓
FRAME-AGNOSTIC CORE  ──────────────────  RUNS ONCE per pitcher
  stuff · location · run-value · game-shape (within-game)
  → per-specialist audit/revise        + grounding (baselines, N-aware tags §15)
        ↓
   CoreAnalysis (shared, frame-neutral)
        ↓
┌──────────────┬─────────────────────────┬──────────────┐
│ Mode REPORT  │      Mode CHANGES        │  Mode RECAP   │
│ native frame │  FRAME-SENSITIVE TAIL    │ native frame  │
│ (win vs szn) │  re-runs trends spec +   │ (recent vs    │
│ reuse signals│  signal-extract + anchor │  window)      │
│ + anchor     │  on the X-vs-Y frame     │ reuse signals │
└──────────────┴─────────────────────────┴──────────────┘
        ↓ (mode × persona writer)
Shared validation stack                 ← SAME checks on every mode:
  anchor + capsule fact-check + value-parity + hallucination
  + LOUD residual surfacing (never ship a flagged item silently)
  (revision DEPTH is per-mode; the checks are identical)
```

**The spine is NOT purely "run once, writers select a frame."** Design review
(G1, §15) found the trends specialist, signal extractor, and anchor are
**frame-coupled** — the anchor actively reverts an off-frame capsule. So the
spine splits: a **frame-agnostic core** (stuff/location/run-value/game-shape +
grounding) runs **once** and is shared by all modes; a small **frame-sensitive
tail** (trends specialist + signal extraction + anchor) runs on the mode's
frame. REPORT (window-vs-season) and RECAP (recent-vs-window, what BRIEF already
does) use the **native** frame, so they reuse the tail directly. Only **CHANGES**
(the novel recent-X-vs-prior-Y frame) re-runs the cheap tail. The expensive 80%
(four specialists + their audits + grounding) is shared; the user's intent —
don't repeat grounding/first-wave — holds.

`game-shape` is in the core because it analyzes *within-game* shape (TTO,
velocity arc), which is orthogonal to the across-appearance comparison frame.

---

## 4. The `NarrationMode` abstraction

A new top-level selector composed with the existing `Persona` × `OutputContract`
machinery, which we **keep** (voice stays orthogonal to shape). A `NarrationMode`
bundles **four** first-class members:

```python
@dataclass(frozen=True)
class NarrationMode:
    id: str                          # "report" | "changes" | "recap"
    temporal_frame: TemporalFrameSpec # which slice(s) the writer foregrounds
    focus: str                       # synthesis | change-detection | exec-brief directive
    contracts: dict[str, OutputContract]   # per-persona structure (reuses today's contracts)
    input_assembler: InputAssembler  # (ctx, analyzed, overlay?) -> writer_input
    validation: ValidationPolicy     # check set (always full) + per-mode revision depths
```

**`input_assembler` is first-class because the modes genuinely diverge at writer
input** — REPORT assembles via `build_writer_input` from `AnalyzedContext`
(`pipeline.py:808`); morning RECAP assembles via `build_story_cue_from_context`
+ `enrich_cue_with_signals` (`digest.py:101,153`). Without this on the mode, the
overlay logic leaks into a call-site switch.

Persona still picks voice; mode picks frame + focus + per-persona contract +
assembler + validation policy.

---

## 5. Enriched multi-window context (the real new work)

**Decision: WRAPPER, not per-field.** Introduce a `MultiFrameContext` (or
`PitcherContext.frames: dict[TemporalFrame, PitcherContext]`) holding one
fully-shaped `PitcherContext` per frame. This keeps every `PitcherContext` /
`PitchTypeSummary` field shape stable, so all `render_*` helpers and every
`_build_*_input` compile unchanged. Per-field (`window_s_plus: dict[Frame, ...]`)
was rejected: it ripples into every engine dataclass, their compute functions,
and every read site, and multiplies table rows against the structural 4-pitch
budget.

### Window model: appearance-count (end state)

**Decision: unify every mode on appearance-count windows, staged.** A scout
reasons in appearances ("last 3 starts"), not calendar days, and a day-window has
*variable* sample size (IL stints, rotation skips, rainouts) — so a fixed
appearance count yields a more stable sample for the `window_*` weighted
averages, NORMAL/OUTLIER tags, and deltas. This is an accuracy win for REPORT,
not only CHANGES. It is a contained change: `filter_to_window` (`data.py:433`)
is the *sole* slicer, called once in `load_pitcher_data`; everything downstream
consumes `window_appearances` regardless of how it was sliced. Nothing
downstream needs the day boundary — workload/rest-days and the prior-year
relevance tier come from appearance dates/counts already. Cold-start even
simplifies to "season has ≤ N appearances."

The swap is **staged** to bound risk: day-windows are retained through the
behavior-preserving `NarrationMode` refactor (phase 3), then the slicer is
swapped to appearance-count in its **own** phase (§13) with updated golden tests
and recalibration. `WINDOW_DAYS` below is **transitional scaffolding**, removed
when the slicer swaps; it is not part of the end state.

### Frames

```python
class TemporalFrame(StrEnum):
    MOST_RECENT = "most_recent"   # the single latest appearance (RECAP)
    RECENT      = "recent"        # recent N appearances, N per-mode (REPORT span, CHANGES recent-X)
    PRIOR       = "prior"         # prior M appearances (CHANGES)
    SEASON      = "season"        # full season (today's baseline)
    WINDOW_DAYS = "window_days"   # TRANSITIONAL: existing day-based lookback; removed after the slicer swap
```

End state is appearance-count throughout: `RECENT` carries a per-mode count
(REPORT's span window vs CHANGES' small recent-X both draw from it with
different N), `PRIOR` is CHANGES' prior-M window, `MOST_RECENT` is N=1.
`WINDOW_DAYS` exists only until the window-model swap (phase 6).

- **New capability:** an **appearance-count slicer** (sibling to `filter_to_window`)
  that selects the last N appearances by `game_date` ordering, feeding RECENT_X /
  PRIOR_Y. Deltas between frames are computed **in code** (engine), never by the
  LLM — consistent with the project's "give the model deltas, not arithmetic" value.
- `assemble_pitcher_context` runs **N times** (once per frame), or is refactored
  to assemble multiple frames in one pass. The plan picks one; running N times is
  the lower-risk first cut.
- **Frame selection is a per-specialist call-site choice.** The "stuff/location/
  run-value are frame-agnostic" mitigation is only *partly* true — `_build_stuff_input`
  already pulls cross-season YoY deltas (`pipeline.py:606-631`) and all specialists
  read the single `window_*` snapshot. So: stuff/location/run-value stay on the
  `RECENT` frame (their current "window" semantics — day-window through phase 3,
  appearance-count after the swap); **trends** and **game-shape** receive the
  multi-frame block (the relevant subset of RECENT / PRIOR / SEASON for the
  active mode). This keeps specialist input from ballooning while giving the
  change-sensitive specialists the comparison they need.

### Mode 2 windows (configurable, flat default)

- CLI `--recent N` / `--prior M` (appearance counts), threaded into the
  `TemporalFrameSpec`.
- **Flat default: recent 3 / prior 10 appearances**, overridable. The SP/RP
  asymmetry (prior-10 ≈ 2 months for a starter, ≈ 2–3 weeks for a reliever) is
  **documented** at the flag and in the mode docstring. (Role-aware defaults were
  considered and declined in favor of a simple, documented surface.)
- REPORT's `RECENT` span also becomes an appearance count after the swap; its
  default maps from today's 30-day window to the equivalent appearance count
  (set during the window-model swap, phase 6).

---

## 6. The three modes concretely

| Mode | Frame foregrounded | Focus | Persona → contract | Replaces |
|---|---|---|---|---|
| **report** | RECENT vs SEASON | full multi-thread synthesis | scout→SCOUT_REPORT, analyst→NEWSLETTER, generic→SECTIONED | today's report path |
| **changes** | RECENT vs PRIOR | changes/trends only; lead with the biggest shift | new CHANGES contracts (one per persona, reuse lengths) | — (net new) |
| **recap** | MOST_RECENT vs trend | executive brief; one thread; optional editor angle | evolved BRIEF→RECAP contract | BRIEF + DIGEST_ITEM |

- **report** subsumes today's CAPSULE/NEWSLETTER/SECTIONED as one "span report" ×
  persona. The existing `REPORT_CONTRACTS` map folds into REPORT's `contracts`.
- **recap** absorbs BRIEF and the morning DIGEST_ITEM. When run with an editorial
  overlay (morning), it leads with the angle; standalone (web capsule), it leads
  with the most-recent slice's own thread.

---

## 7. Shared validation stack (parity requirement)

**Requirement (user): the same fact-checking and accuracy on every mode.** The
*checks* are identical for all modes; only the revision *depth* varies.

### Principle: detection is mandatory; only remediation is tuned

No mode ever skips checking. The morning path's historical "skip anchor +
hallucination for speed" (`morning.py:8-14`) was a **false economy** — it
conflated two separable things:

- **Detection** (finding problems) is free or cheap. `check_hallucinated_metrics`
  and `check_value_parity` are **pure functions** (regex/string, no LLM) — there
  is *no* speed argument to ever skip them. The anchor + fact-check detection pass
  is **one cheap mini-model call** each.
- **Remediation** (auto-fixing) is the only expensive part — the writer re-calls
  in the revision loops.

Both loops already support detect-without-remediate: `_run_anchor_revision_loop`
and `_run_capsule_audit` at `depth=0` run their detection pass, surface the
flags, and never revise. Therefore:

> **Detection + loud residual surfacing are mandatory and universal on every
> output. Only remediation depth is tuned, and depth 0 is valid.** The cheapest
> mode still detects, still surfaces, and merely declines to auto-fix — it never
> ships an unverified item silently.

This is what "same fact-checking on every mode" actually means: identical
detection everywhere, never skipped; remediation depth is the single knob.

- Publish and reuse: `_run_anchor_revision_loop`, `_run_capsule_audit`, and their
  private prompt helpers (`build_anchor_message`, `build_revision_message`,
  `_build_capsule_audit_input`, `build_fact_revision_message`). `check_value_parity`
  / `check_hallucinated_metrics` are already public.
- Every mode's output runs the full suite against its own ground-truth union (the
  frames + clean specialists + signals it actually saw).
- **Per-mode revision depth (config knobs):**
  - REPORT: anchor 5 / fact 2 (today's `MAX_REVISIONS` / `MAX_FACT_REVISIONS`).
  - RECAP (incl. morning digest items): **anchor 1 / fact 2.** Rationale: the
    fact loop's re-audit (`pipeline.py:1582`) can catch a revision-introduced
    error; fact-depth 2 gives it one recovery pass (the specialist loop is
    single-pass and that is exactly the "ships residual" failure we avoid).
    Anchor (signal fidelity on a short brief) caps to 1.
  - New CLI knobs `--recap-anchor-depth` / `--recap-fact-depth` (morning passes
    the digest default) so "high accuracy" is recoverable per-run without code
    changes.
- **LOUD residual surfacing on EVERY mode (the real accuracy guarantee).**
  `cli.py:379-387` already prints the `⚠️ REPORT UNVERIFIED` banner + non-zero
  exit for the report path. **Morning must mirror it:** a digest item carrying
  residual `capsule_audit_flags` / `value_parity_warnings` is **marked in the
  digest and in the run summary**, never silently shipped. Parity is "never ship a
  flagged item unmarked," not the depth number.

### Why the 8× never materializes

Checks always run (cheap mini-model); writer re-calls fire only on a flag and are
capped. With the cap, the hard ceiling is `picks × (anchor_depth + fact_depth)`
(8 × 3 = 24 on an 8-pick slate) vs the uncapped 8×30×7 ≈ 210. Expected added
writer calls ≈ `picks × flag_rate × ~1` ≈ ~3 on an 8-pick slate at the 35% proxy.

---

## 8. Observability (prerequisite for calibration)

The capsule flag/revision rate has never been recorded. As part of this work:

- Add `tracker.record(...)` to the anchor loop (`pipeline.py:1399`) and capsule
  fact-check (`pipeline.py:1526`) so revision passes appear in `usage.json`.
- Persist `PipelineResult` flag counts (`revision_count`, `capsule_revised`,
  `capsule_audit_flags`, `anchor_warnings`, `value_parity_warnings`) to the run
  artifacts (report stdout already prints them; morning must dump them).
- **Calibrate the RECAP depth default from the first instrumented runs** rather
  than guessing. The defaults above are provisional until measured.

---

## 9. Morning / digest integration

- Morning becomes: scout → select → **one spine run per pick** → render **Mode
  RECAP** with the `CurationPick` as a **typed overlay** (`recap(analyzed, pick:
  CurationPick | None)`), not a prose cue.
- `DIGEST_ITEM` contract + `_CUE_FRAMING` (separate writer path) are retired; the
  digest item is Mode RECAP with parity validation + residual surfacing.
- **Preserved:** `assemble_digest` (`digest.py:312`) scaffolding — category
  grouping, badges, conviction ranking — is independent of which contract produces
  the item text and stays as-is.
- Editorial `category`/`angle`/`conviction` flow in via the overlay (they cannot
  come from `AnalyzedContext`).

---

## 10. CLI surface

- **report** subcommand gains `--mode report,changes,recap` (one or many). When
  multiple are requested, the spine runs **once** and each selected mode renders
  from the shared `AnalyzedContext` — the payoff of the multi-window design.
- `--recent N` / `--prior M` feed Mode CHANGES.
- `--recap-anchor-depth` / `--recap-fact-depth` expose the depth knobs.
- **morning** subcommand: **fixed to RECAP** (no `--mode`); document this
  explicitly. (Neither subcommand has `--mode` today; report gains it, morning
  does not.)
- Resolve the `# Brief` CLI section (`cli.py:285`, consuming `PipelineResult.brief`):
  it is replaced by RECAP output. The plan states the exact rerouting.

---

## 11. Naming / collisions

- Mode ids: `report` / `changes` / `recap` (all collision-free; `capsule` and
  `brief` were rejected — they collide with the `CAPSULE`/`BRIEF` contracts).
- Rename the existing `CAPSULE` OutputContract → `SCOUT_REPORT` so the
  contract/mode namespaces stay unambiguous. `BRIEF` contract evolves into the
  RECAP contract.

---

## 12. Retired / migrated

- `build_story_cue` (`digest.py:47`) — delete (dead): definition, `__all__` entry,
  and `test_digest.py` uses.
- `DIGEST_ITEM` + `_CUE_FRAMING` (`personas.py`) — folded into Mode RECAP overlay.
- `REPORT_CONTRACTS` map — absorbed into Mode REPORT's `contracts`.
- `CAPSULE` contract — renamed `SCOUT_REPORT`.
- **`test_fact_parity.py:451`** — **rewrite** (its premise asserts on the cue
  string, which RECAP no longer produces). Re-express the fact-parity guarantee
  against RECAP's `AnalyzedContext`-sourced input.
- Voice-golden / persona-wiring / characterization tests updated; **new golden
  tests per mode**.

---

## 13. Phased rollout (for the implementation plan)

The work is large; sequence it so each phase is independently shippable and the
existing report path keeps working throughout.

1. **Observability first** (§8): add `tracker.record` to the two loops + persist
   flag counts. Cheap, unblocks calibration, no behavior change.
2. **Multi-frame context** (§5): `MultiFrameContext` wrapper +
   `assemble_pitcher_context` per-frame, frames still sliced by the existing
   day-window. Spine still consumes the day-window `RECENT` for existing
   specialists; no narration change yet. Preserve the 4-pitch budget.
3. **Split the spine: frame-agnostic core + frame-sensitive tail** (§3, G1):
   factor `run_analysis_spine` into a shared core (stuff/location/run-value/
   game-shape + grounding) and a tail (trends specialist + signal extraction +
   anchor) that takes a frame argument. REPORT still runs on the native frame —
   behavior-preserving. This makes CHANGES possible later without re-touching the
   core.
4. **`NarrationMode` abstraction + REPORT** (§4, §6): refactor today's report path
   onto the mode (rename CAPSULE→SCOUT_REPORT, fold REPORT_CONTRACTS). Introduce
   the per-mode `PipelineResult` shape (G10) + CLI multi-mode output/exit policy
   scaffolding for a single mode (G4, G9). Behavior-preserving; characterization
   tests guard it. Day-window still in force.
5. **Frame sufficiency + determinism guards** (§15, G2/G5/G6/G7/G8): empty-frame
   guard on `compute_fastball_summary`, N-aware outlier tags + small-sample
   suppression, frame-aware insufficiency gate, `game_pk` tiebreak on all
   appearance ordering. **Prerequisite for any appearance-count frame** — must
   land before phase 6.
6. **Window-model swap** (§5): add the appearance-count slicer, make it primary in
   `load_pitcher_data`, re-express cold-start in appearance terms, remove
   `WINDOW_DAYS`, map REPORT's default span count from the old 30d. **Not
   output-neutral** — rewrite golden/characterization tests and recalibrate here.
7. **Shared validation stack** (§7): publish loops, parameterize depth, add LOUD
   residual surfacing API + aggregate multi-mode exit policy (G4). Wire REPORT
   through it (no behavior change).
8. **Mode RECAP** (§6, §9): evolve BRIEF→RECAP, typed overlay, morning integration
   (single-event-loop safe per G3, agent reuse per G11), retire DIGEST_ITEM/cue,
   rewrite `test_fact_parity`. Morning gains parity + residual marking.
9. **Mode CHANGES** (§6): new contracts, `--recent`/`--prior`, the frame-sensitive
   tail on the RECENT-vs-PRIOR frame. Net-new mode. Depends on phases 3 + 5.
10. **Bench + golden coverage** (G12, G13): extend `CapturedRun.outputs` +
    ground-truths per mode, `--mode` on bench; add per-mode×persona goldens.
11. **Calibrate** RECAP depth defaults + REPORT span count from instrumented runs
    (§8).

---

## 14. Open risks

- **Specialist input noise** from the multi-frame block: mitigated by scoping the
  block to trends/game-shape only (§5). Watch the golden tests for drift.
- **Capsule flag rate is unmeasured** for the capsule rubric; the 35% proxy is
  specialist-level. Phase 1 (observability) + phase 7 (calibration) address this;
  until then RECAP depth defaults are provisional.
- **Morning latency** rises (validation now runs per pick). Bounded by the depth
  cap; the knobs let an operator trade accuracy for speed per run.
- **Window-model swap is not output-neutral** (phase 6): REPORT goldens change,
  and existing morning-runs / the 35% specialist proxy become non-comparable
  (sliced under day-windows). Mitigated by isolating the swap to one phase with a
  legible diff + explicit recalibration; the abstraction refactor (phase 4) lands
  first and behavior-preserving so the two sources of change never tangle.

---

## 15. Frame sufficiency & determinism policy (design-review gaps)

Appearance-count frames break an invariant the day-window guaranteed: a frame can
be **empty** (CHANGES PRIOR in early April), **tiny** (RECAP N=1 ≈ a 15-pitch
relief outing), or **overlapping**. The engine was written assuming the window is
never empty and always contains the most-recent appearance. These guards are
**prerequisites** for any appearance-count frame (phase 5).

- **G2 — empty-frame crash (hard).** `compute_fastball_summary` does
  `_float(window_fb[...].mean())`; an empty frame yields `None` → `TypeError`
  (`arsenal.py:334,373`). `compute_arsenal_summary` is already guarded
  (`arsenal.py:565`); fastball never was. Add the `n>0 → fall back to season`
  guard, and define a **frame-empty contract**: an empty frame renders explicit
  "no data for this frame," never a computed number.
- **G6 — tiny frame, confident deltas (silent accuracy).** `_weighted_window_metrics`
  (`_common.py:320`) returns a full weighted average from ≥1 pitch; `small_sample`
  (`_MIN_PITCHES=10`) only appends a cosmetic `*` (`prompt_builder.py:208`).
  Policy: below the floor, **suppress the delta string** (render "insufficient
  sample," not "Down sharply (-15)"), don't just mark it.
- **G7 — outlier tags ignore N (silent accuracy, amplified).** `outlier_tag`
  (`baselines.py:157`) tags off a single-outing mean with no shrinkage, and the
  specialist prompt orders the LLM to "RESPECT THE TAGS" (`pipeline.py:154`).
  Pass N to `outlier_tag`; **suppress the OUTLIER tag below the sample floor**
  (emit NORMAL or an explicit "small-sample, untagged"), so single-outing noise
  is not amplified into a grade driver.
- **G8 — cold-start logic is day-window-shaped.** `_is_cold_start`
  (`_common.py:276`) compares window-appearance count vs total — meaningless for
  count frames, and it mis-fires both directions. Replace with a **frame-aware
  sufficiency gate**: each frame reports `sufficient | thin | empty`, and the
  trends/CHANGES narration is told when a comparison is underpowered (ties into
  the existing `<10 appearances` relevance tier, `workload.py:338`, which today
  is prose-only).
- **G5 — determinism (correctness).** Appearance ordering sorts on `game_date`
  alone then `.row(0)` (`context.py:133`, `arsenal.py:436`); doubleheaders (two
  `game_pk` on one date) make "most recent" non-deterministic, and count-slice
  boundaries inherit it. Add `game_pk` as a secondary sort key on **every**
  appearance ordering / single-appearance pick. The deterministic-tiebreak
  pattern already exists at `data.py:350`.

**Sufficiency is surfaced, never silent.** Mirroring §7's residual principle: a
thin/empty frame is *marked in the output* (and the narration hedged), never
rendered as a confident finding. RECAP on a single noisy outing must read
tentative; CHANGES with an empty PRIOR must say so, not invent a comparison.

---

## 16. Surface / integration resolutions (design-review gaps)

- **G9 — CLI multi-mode output.** Today the writer streams raw deltas to stdout
  under one hardcoded `# Scouting Report` header (`pipeline.py:1637`, `cli.py:257`),
  and the whole post-stream assembly assumes one `PipelineResult`. Multi-mode
  needs a per-mode delimiter/header and a defined stream policy (sequential,
  each mode fully streamed under its own header). `--print-prompts` renders N
  writer-prompt sections, not one.
- **G10 — per-mode result shape.** `PipelineResult` is scalar
  (`.narrative/.brief`, `pipeline.py:1140`). Return `dict[mode, PipelineResult]`
  (or `list`) from the multi-mode entry point. Churns ~4 consumers (`cli.py`,
  `bench/runner.py:100`, `tests/test_personas.py` smoke tests); mechanical.
- **G4 — aggregate exit policy.** Run **all** requested modes, OR their residual
  flags, print every mode, then exit non-zero if *any* mode is unverified. The
  current first-failure `sys.exit` (`cli.py:379`) and hallucination early-`return`
  (`cli.py:353`) must not abort sibling modes.
- **G3 — morning single-event-loop.** Unified morning must reuse
  `run_analysis_spine` once per pick and `await` the RECAP writer on the shared
  loop (`morning.py:96`), never call the `asyncio.run`-wrapping
  `generate_pipeline_streaming` per mode inside the loop.
- **G11 — agent reuse.** Build the core/auditor/anchor agents once; only
  writer/summary/brief are mode-specific. Modes branch **after**
  `run_analysis_spine`, reusing one agent set — the pattern morning already uses
  (`morning.py:97`). Avoids 12×(modes) agent builds.
- **G12 — bench coverage.** `CapturedRun.outputs` + per-tier ground-truths
  (`bench/runner.py:45,117`) are single-capsule; add per-mode capsules + ground
  truths and a `--mode` on bench, or CHANGES/RECAP ship unjudged.
- **G13 — golden combinatorics.** Voice-golden + persona-wiring tests are
  persona-keyed (`test_voice_golden.py`, `test_personas.py`); per-mode writer
  prompts make them persona×mode. Add the mode axis to the parametrization and
  fixtures.
- **G14 — CLI plumbing.** `--mode report,changes,recap` (comma-split + validate,
  mirroring bench's `--providers`); thread `--mode` (or fix RECAP) through
  `run_morning` (`morning.py:58`) and `write_pick_summaries`.
