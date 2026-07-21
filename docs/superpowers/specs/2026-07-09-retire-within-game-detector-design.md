# Retire the Within-Game (Game-Shape) Detector — Design

**Date:** 2026-07-09
**Status:** Approved design, pending implementation plan
**Supersedes:** `2026-07-08-game-shape-deviation-gate-design.md` (v1 deviation gate — do NOT merge/ship it).
**Topic:** Remove the per-pitcher within-game (times-through-order) analysis
entirely — the deviation gate *and* the underlying game-shape specialist —
because the signal it reports is not reliable.

---

## 1. Why (the evidence)

A four-step empirical investigation (harnesses in `scripts/tto_*.py`; Linear
PLUS-139/140) established that per-pitcher within-game shape is not a reportable
signal:

- **Face validity fails.** Within-game ΔP+ by pass has ~zero correlation with
  actual outcome change (corr(ΔP+, Δrun-value) = +0.065 / +0.073 at passes 2/3;
  worst-ΔP+ concordance with worse results = 49.5% at pass 2 — a coin flip). The
  ΔP+ "signal" is pitch-mix drift, not performance.
- **Deep findings are censored.** Only 2.9% of appearances reach pass 4, and
  96.3% of the worst late-game damage occurs in appearances pulled before pass 4
  — the deep-pass sample is survivor-biased.
- **The signal does not repeat (decisive).** Split-half reliability of the
  within-game outcome deltas is ≈ 0 (Δ run value pass 2/3: 0.032 / −0.051;
  Δ xwOBA pass 2/3: 0.064 / −0.021; n=422), while positive controls in the same
  data are high (overall velocity 0.986; overall xwOBA 0.419). A pitcher's
  within-game shape in one random half of his starts predicts nothing in the
  other half.

**Conclusion:** the individual times-through-order penalty is regression-to-mean
noise; only the *league* TTO effect is real. No metric rebuild (P+ → outcomes)
can recover a signal that isn't there — the controls prove the machinery would
detect one if it existed. The honest model does not report per-pitcher
within-game shape at all.

## 2. Decision

Retire the entire within-game analysis:

1. Delete the v1 deviation-gate machinery (unmerged).
2. **Cut the game-shape specialist** — the analysis spine goes from 5 specialists
   to 4 (stuff, location, run value, trends). Reverting its prompt is not an
   option: the pre-v1 prompt produced the universal late-fade narrative that
   started this whole effort. The specialist has no reliable insight to
   contribute, so it is removed, not reworded.
3. Delete the TTO engine and its context wiring — the specialist was its only
   consumer.

The population-baseline → residual → gate *architecture* was sound; only its
input (within-game shape) was noise. Per decision, the generic
`evaluate_deviation` primitive is **deleted** (YAGNI — reintroduce if a
reliable population-relative signal ever appears; the git history + harnesses
preserve the pattern).

## 3. What is removed

**Deviation-gate machinery (v1, unmerged):**
- `src/pitcher_narratives/engine/deviation.py` (+ `tests/test_deviation.py`).
- `src/pitcher_narratives/tto_baseline.py`; `data.tto_baseline_path` /
  `load_tto_baseline`; the `var/tto_baseline.parquet` artifact
  (+ `tests/test_tto_baseline.py`, `tests/test_tto_deviation.py`,
  `tests/test_tto_deviation_golden.py`).
- `engine/tto.py::evaluate_tto_deviations`, `TTODeviation`, `_MIN_BASELINE_N`.
- `pipeline.py::_render_deviation_block`; the deviation wiring in
  `_build_game_shape_input`; the `TTODeviation`/`evaluate_tto_deviations`/
  `load_tto_baseline` imports.

**Game-shape specialist + TTO engine (5 → 4 spine):**
- `engine/tto.py` entirely (`TTOAnalysis`, `TTOSplit`, `TTOPitchType`,
  `TTOPlatoonSplit`, `compute_tto_analysis`) and its `engine/__init__.py` exports.
- `context.py`: the `tto: TTOAnalysis | None` field and the
  `tto = compute_tto_analysis(data)` call (context.py:94, 137) + the import.
- `pipeline.py`: `_GAME_SHAPE_SPECIALIST_PROMPT`, `_SP_GAME_SHAPE_GUIDANCE`,
  `_RP_GAME_SHAPE_GUIDANCE`, `_role_game_shape_guidance`,
  `_build_game_shape_input`, `render_tto_section` (import + definition wherever
  it lives), the `game_shape` agent in `make_pipeline_agents`, and its entries in
  the specialist `names` list (pipeline.py:551) and `run_specialists`/results
  wiring (pipeline.py:591).
- `models.py`: the `game_shape: str` field on both specialist-output models
  (models.py:54, 92).
- `personas.py` `_SYNTHESIS_RULES`: "Five specialist analyses" → "Four", and drop
  the "5. Game shape" line (and any other five-count references).
- `bench/runner.py`: the `_build_game_shape_input` import, the
  `specialist:game_shape` bench entries, and `specialists.game_shape` references.

## 4. What is kept

- The three diagnostic harnesses (`scripts/tto_operating_envelope.py`,
  `tto_validity.py`, `tto_reliability.py`) — the institutional record + reusable
  reliability tooling for future signals.
- The design/plan docs and Linear PLUS-139/140. Add a one-paragraph
  **"RETIRED — and why"** banner to `2026-07-08-game-shape-deviation-gate-design.md`
  pointing at this spec and the reliability result.
- The four reliable specialists and the rest of the pipeline. The reader words
  game-shape consumed are reinvested implicitly (the writer synthesizes four
  analyses instead of five).
- The single-voice narratives + WS4 work on the branch — independent, stays.

## 5. Architecture / ripple

- **Spine 5 → 4.** `run_specialists`, `make_pipeline_agents`, `PipelineAgents`,
  the `names` list, and the `SpecialistOutputs`-style models all lose their
  game-shape slot. The concurrency/orchestration is otherwise unchanged.
- **Synthesis framing.** `_SYNTHESIS_RULES` must describe four analyses; the
  writer/signal-extractor framing that enumerates specialists is updated. This is
  a composed-prompt change → the writer-prompt fixtures re-baseline deliberately.
- **No new abstractions.** This is purely subtractive; do not refactor the
  remaining four specialists.

## 6. Testing

- Full suite green after removal; the 3 documented pre-existing baseline failures
  are the only ones permitted.
- Specialist-count / spine tests updated to expect 4 (drop game-shape assertions).
- Writer/synthesis-framing fixtures re-baselined (four-analyses wording) with the
  diff reviewed.
- `grep` gate: no residual references to `game_shape`, `TTOAnalysis`,
  `compute_tto_analysis`, `evaluate_tto_deviations`, `TTODeviation`,
  `load_tto_baseline`, `render_tto_section`, `_build_game_shape_input`,
  `deviation` (engine) anywhere in `src/`, `tests/`, `bench/` (comments/docs
  excepted).
- A pipeline smoke test confirms a report still generates end-to-end from four
  specialists.

## 7. Non-goals

- No change to the four remaining specialists, the writer voice (single-voice),
  the validation stack, or WS4.
- No replacement within-game feature. Within-game shape is not reported; that is
  the deliverable.
- Not deleting the diagnostic harnesses or the evidence trail.
