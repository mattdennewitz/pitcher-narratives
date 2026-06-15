# Narrative Consolidation Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan phase-by-phase. Steps use checkbox (`- [ ]`) syntax for tracking. Phases 0–1 are specified to task detail; Phases 2–4 carry design decisions that must be resolved at the start of each phase (each gets its own detailed sub-plan before execution — see "Phase gating").

**Goal:** Collapse the three forked fact engines and four duplicated agent voices into **one fact layer** and **one voice composition**, so that (a) every delta/baseline is computed exactly once and (b) the writer voice holds steady as the output target changes (capsule, digest item, answer).

**Architecture:** `PitcherContext` (`engine/` + `context.py`) becomes the only source of computed facts; `scout.py` becomes thresholding/scoring over engine outputs and `digest.build_story_cue` becomes a projection of `PitcherContext`. Every writing agent composes its system prompt from `SHARED_WRITER_BASE` (analytical rules, defined once) × a `Persona` (tone/vocab) × a new `OutputContract` (length/structure). The report and ask pipelines already share a specialist→audit→signal spine; that spine is extracted to `run_analysis_spine(ctx) → AnalyzedContext` and feeds all three terminal renderers.

**Tech Stack:** Python 3.14, pydantic + pydantic-ai, polars, pytest, uv, ruff, ty. Deterministic LLM testing via `PITCHER_NARRATIVES_TEST_MODEL` (TestModel). Quality gate via `bench/` (per-provider pipeline runs + rubric judge, incl. `directional_consistency` dimension).

**Visual / rationale:** `docs/superpowers/plans/2026-06-15-narrative-consolidation.html` — current-state swimlanes, divergence callouts, target diagram.

---

## Critical Context for the Implementer

### What is forked today (the thing being fixed)

**Three fact engines:**
- **A** — `engine/` (10 concern modules) + `context.py` → `PitcherContext`. Feeds `report` and `ask`. The only substrate with anti-hallucination grounding (`outlier_tag`, S-variant baselines).
- **B** — `scout.py` signal scoring (`_check_velo_delta`, `_check_pplus_swing`, `_check_usage_shifts`, `_check_splus_lplus_divergence`, `_check_repertoire_changes`, `compute_velo_baselines`). Feeds `morning` and `pitcher-scout`. Recomputes deltas from raw aggs with its own thresholds.
- **C** — `digest.build_story_cue` (digest.py:42–93). A third rendering of "season baseline + per-pitch usage" for the morning writers.

**Four voices (one logical "sabermetric scout" voice):**
- **V1** — `personas.SHARED_WRITER_BASE` + overlays (canonical; report path).
- **V2** — `digest._DIGEST_WRITER_BASE` + `_PRECEDENCE_RULE` (morning; reuses overlays but suppresses their length/structure directives).
- **V3** — `analyst.ANALYST_INSTRUCTIONS` (ask streaming; ignores `--persona`).
- **V4** — `analyst.ANSWERER_INSTRUCTIONS` (ask-pipeline; orphaned from CLI).

The banned-word list (`degradation, binary, profiles as, dominant, elite, massive spike`) is verbatim in `personas.py` and `analyst.py`; "directional consistency" / "temporal grounding" / "find the thread" recur across `personas.py`, `analyst.py`, `pipeline.py`, `prompt_builder.py`.

### What is already shared (keep and extend)

`report` and `ask_question_pipeline` run the **identical** `run_specialists` → `audit_and_revise_specialists` → signal-extractor spine. That is the correct shared bone; Phase 3 names it.

### Guiding tactics (apply in every phase)

1. **Strangler, not big-bang.** New code lands beside old; parity is proven; *then* old is deleted. Never cut over in one commit.
2. **Exploit the deterministic seam.** Prompt composition (`write_pipeline_data_file` / `--print-prompts`) and fact math are both deterministic — test them exactly, offline, no model. Reserve `bench/` evals for the irreducibly non-deterministic prose quality.
3. **Each phase ships green.** Every phase ends with the full suite passing and is independently revertible (one commit / one merge).
4. **Phases 1 and 2 are independent** and may be run in parallel worktrees.

### Baseline (capture before starting)

```bash
uv run pytest -q 2>&1 | tail -1          # record N passed — the contract for every phase
uv run ruff check src tests              # must stay clean
uv run ty check 2>&1 | tail -1           # record type-check baseline
```

Record the pass count and a sample of LLM output for later eval comparison:

```bash
# Fix a 3-pitcher cohort for before/after quality comparison (pick 3 IDs with data)
uv run pitcher-narratives morning > /tmp/morning.before.md         # capture digest + usage
cp morning-runs/*/usage.json /tmp/usage.before.json                # cost/latency baseline
```

---

## Phase gating

| Phase | Detail level here | Sub-plan before executing? |
|------|-------------------|----------------------------|
| 0 Safety net | task-complete | no |
| 1 Voice | task-complete | no |
| 2 Facts | sketch + decisions | **yes** — write `…/plans/<date>-consolidation-facts.md` |
| 3 Spine | sketch + decisions | **yes** — write `…/plans/<date>-consolidation-spine.md` |
| 4 Surface | sketch | optional |

---

## Phase 0: Safety net & dead-code removal  ·  risk: low

**Goal:** Make the refactor verifiable and remove the orphaned voice copy.

### Files
- Modify: `src/pitcher_narratives/analyst.py`, `src/pitcher_narratives/pipeline.py`
- Add: `tests/test_voice_golden.py`, `tests/test_fact_parity.py` (skeleton)

- [ ] **Step 1: Confirm the orphan is safe to delete.**
  `ask_question_pipeline` + `ANSWERER_INSTRUCTIONS` references: their definitions, the `__all__` export (`analyst.py:26,28`), the ask-path `--print-prompts` dump (`pipeline.py:967,970`), and a test *comment* (`tests/test_pipeline.py:151`). Verify `ask_cli.py` calls only `ask_question_streaming` (it does — `ask_cli.py:170`), and that nothing in `bench/` imports the pipeline variant.
  ```bash
  grep -rn "ask_question_pipeline\|ANSWERER_INSTRUCTIONS" src tests
  ```

- [ ] **Step 2: Delete the orphan.** Remove `ask_question_pipeline`, `ANSWERER_INSTRUCTIONS`, `PipelineAnswer` (if unused elsewhere), and their `__all__` entries. In `pipeline.py::_render_pipeline_data_sections`, the ask-path branch (`question is not None`) renders `ANSWERER_INSTRUCTIONS` — if the ask `--print-prompts` path is itself unreachable, remove the branch; if reachable, repoint it to the new ANSWER contract in Phase 1 (leave a `# TODO(phase1)` and keep it compiling for now). Update the `test_pipeline.py:151` comment.

- [ ] **Step 3: Characterization tests (the net).** Lock current behavior with deterministic snapshots — these prove later phases don't *silently* regress structure/wiring (voice text will change intentionally; assert invariants, not byte-identity):
  - `test_voice_golden.py`: for each path × persona, render the composed system prompt via `write_pipeline_data_file` / `build_writer_system_prompt` under `PITCHER_NARRATIVES_TEST_MODEL` and assert invariants (banned-word block present, directional/temporal blocks present, expected length target). This file grows in Phase 1.
  - `test_fact_parity.py`: skeleton only — a placeholder that Phase 2 fills with old-vs-new delta parity assertions.

### Verification
```bash
uv run pytest -q 2>&1 | tail -1     # == baseline N (minus any deleted orphan tests)
uv run ruff check src tests
grep -rn "ANSWERER_INSTRUCTIONS\|ask_question_pipeline" src   # → no hits
```
**Green when:** orphan gone, suite green, characterization net committed as the baseline.

---

## Phase 1: Unify the voice layer  ·  risk: medium

**Goal:** One analytical base, composed as `Persona × OutputContract`. `--persona` works on every path. Banned-word list exists once.

### Files
- Modify: `src/pitcher_narratives/personas.py` (add `OutputContract`, `build_system_prompt`; move analytical rules into `SHARED_WRITER_BASE`; strip length from `Persona`)
- Modify: `src/pitcher_narratives/pipeline.py` (writer + exec-summary use new composer)
- Modify: `src/pitcher_narratives/digest.py` (delete `_DIGEST_WRITER_BASE` voice text + `_PRECEDENCE_RULE`; `_build_writer_prompt` → composer with `DIGEST_ITEM` contract)
- Modify: `src/pitcher_narratives/analyst.py` (answerer/ask voice rules sourced from base via `ANSWER` contract; keep tool-use + data-grounding *mechanics* local)
- Test: `tests/test_personas.py`, `tests/test_digest.py`, `tests/test_analyst.py`, `tests/test_voice_golden.py`

- [ ] **Step 1: Introduce `OutputContract`.** A frozen dataclass sibling to `Persona`: `id`, `length_target: tuple[int,int]`, `structure: str` (the length/format/heading rules that today live scattered across overlays and `_DIGEST_WRITER_BASE`). Define instances: `CAPSULE` (2–3 ¶, prose-only), `DIGEST_ITEM` (150–250w, lead with angle, close with what-to-watch), `ANSWER` (1–3 ¶, no preamble, answer-only). Move `length_target` off `Persona` onto the contract; `Persona` keeps only tone + vocabulary.

- [ ] **Step 2: Centralize analytical rules in `SHARED_WRITER_BASE`.** The banned-word list, directional-consistency, temporal-grounding, and find-the-thread rules become single blocks in the base. Remove their duplicates from the scout/analyst overlays and from `ANALYST_INSTRUCTIONS`.

- [ ] **Step 3: `build_system_prompt(persona, contract) → str`.** Compose base + parent-overlay-chain + persona overlay + contract.structure. Replaces `build_writer_system_prompt` (keep a thin shim or update all callers) and `digest._build_writer_prompt`. The `_PRECEDENCE_RULE` hack is deleted — contract and voice no longer conflict because structure is owned by the contract, not the overlay.

- [ ] **Step 4: Repoint the three writers.**
  - `pipeline.make_pipeline_agents` writer → `build_system_prompt(persona, CAPSULE)`.
  - `digest._make_writer_agent` → `build_system_prompt(persona, DIGEST_ITEM)`. `write_pick_summaries` now honors `--persona` cleanly.
  - `analyst` ask answerer → `build_system_prompt(persona, ANSWER)` for *voice*; its tool-use and "answer only from tool output" *mechanics* stay in a local mechanics block (not voice). Thread `persona` through `ask_question_streaming` / `_make_qa_agent` and `ask_cli.py` (add `--persona`, matching `report`'s arg).

- [ ] **Step 5: Update golden + unit tests.** `test_voice_golden.py` asserts each composed prompt = base-block ∪ persona-block ∪ contract-block, with the banned-word block appearing exactly once. Update frozen writer-prompt fixtures deliberately and review the diff by eye (the repo keeps these byte-stable on purpose).

### Verification
```bash
uv run pytest -q 2>&1 | tail -1
uv run ruff check src tests
grep -rc "degradation" src/pitcher_narratives/*.py | grep -v ':0'   # → personas.py only (one hit)
uv run pitcher-ask --persona analyst -p <ID> "how's his slider?"    # persona now changes ask output
uv run pitcher-narratives report -p <ID> --print-prompts | less     # eyeball composed writer prompt
```
**Quality gate:** run `bench/` on the fixed cohort, compare `directional_consistency` scores to baseline (no regression).
**Green when:** `--persona` affects ask & morning; banned-word list has one source; `_PRECEDENCE_RULE` gone; V2/V3/V4 voice text gone.

---

## Phase 2: Unify the fact layer  ·  risk: high  ·  **write sub-plan first**

**Goal:** `PitcherContext` is the only computed-fact source. `scout.py` = thresholding over engine outputs. `digest` cue = projection of `PitcherContext`. Morning-written picks rest on substrate A.

### Decisions to resolve in the sub-plan (before coding)
1. **Loading strategy / cost.** `PitcherContext` is per-pitcher and heavier than B's bulk scan. Recommended: keep the cheap bulk scan for **triage** (scoring all appearances), then build full `PitcherContext` only for the ~N **selected** picks (lazy, post-selection). Confirm against `/tmp/usage.before.json` that this keeps morning's token/wall-clock profile.
2. **Where shared delta math lives.** Lift velo-delta / P+-delta / usage-shift / S+L+-divergence into single engine functions (likely `engine/arsenal.py` already has `compute_arsenal_trends` / `ArsenalTrends` — prefer extending those over net-new). Decide whether scout consumes them via a thin per-appearance projection or via direct engine calls.

### Files (expected)
- Modify: `src/pitcher_narratives/engine/` (one canonical delta fn each), `scout.py`, `digest.py`, `morning.py`
- Test: `tests/test_fact_parity.py`, `tests/test_scout.py`, `tests/test_digest.py`, `tests/test_morning.py`

- [ ] **Step 1: Extract shared deltas into the engine** (new code beside old). Old `scout._check_*` stays alive.
- [ ] **Step 2: Parity tests (the exact net).** Feed identical inputs to old `scout._check_*` and the new engine fns; assert equal within rounding across a representative pitcher set. Deterministic ⇒ exact proof, not a sample.
- [ ] **Step 3: Repoint scout** to score over engine outputs; keep `_WEIGHTS` + signal taxonomy. Delete old threshold math only after parity is green.
- [ ] **Step 4: Cue becomes a projection.** Rewrite `build_story_cue` to render a subset of `PitcherContext` (no independent baseline math). Wire morning's lazy per-pick `PitcherContext`.
- [ ] **Step 5: Cross-path identity test.** Assert a morning cue and a `report` context for the same pitcher cite identical numbers (deterministic — no model).

### Verification
```bash
uv run pytest -q tests/test_fact_parity.py tests/test_scout.py tests/test_digest.py tests/test_morning.py
# velo/P+/usage delta each have exactly one implementation:
grep -rn "def .*velo.*delta\|def .*usage.*shift" src/pitcher_narratives
uv run pitcher-narratives morning > /tmp/morning.after.md
# diff cost: compare /tmp/usage.before.json vs new usage.json (tokens + wall_s within tolerance)
```
**Green when:** one impl per delta; morning picks built from `PitcherContext`; same-pitcher numbers identical across morning/report; morning cost within tolerance of baseline.

---

## Phase 3: Converge the analysis spine  ·  risk: medium  ·  **write sub-plan first**

**Goal:** Compute the specialist analysis once; render it three ways. Per-target divergence collapses to the terminal renderer.

### Files (expected)
- Modify: `src/pitcher_narratives/pipeline.py` (add `run_analysis_spine`, `AnalyzedContext`), `analyst.py`, `morning.py`

- [ ] **Step 1: Extract `run_analysis_spine(ctx, *, provider, thinking, model_override) → AnalyzedContext`** wrapping `run_specialists` → `audit_and_revise_specialists` → signal extraction (clean outputs + `KeySignals` + audit flags). Behavior-preserving.
- [ ] **Step 2: Repoint report and ask** to the spine; delete the duplicated phase code in `_run_pipeline`.
- [ ] **Step 3: Terminals consume `AnalyzedContext` + (persona, contract).** Capsule writer, digest-item writer, answerer become thin.
- [ ] **Step 4: Morning opts into the spine** (full or reduced) per pick; same return type. Anchor loop + hallucination check become opt-in post-processors usable by any terminal.

### Verification
```bash
PITCHER_NARRATIVES_TEST_MODEL=1 uv run pytest -q tests/test_pipeline.py tests/test_analyst.py tests/test_morning.py
grep -rn "run_analysis_spine" src   # → one def, three call sites
```
**Green when:** one spine fn with three callers; report & ask share it with no duplicated phase code; morning can opt into report-grade grounding. TestModel proves the refactor is behavior-preserving offline.

---

## Phase 4: Collapse entry points  ·  optional

- [ ] Evaluate folding `pitcher-scout` / `pitcher-ask` into `pitcher-narratives` subcommands (the morning-run design doc weighed and deferred this). Low value; keeping `pitcher-scout` standalone for triage is legitimate. Do last, behavior-neutral.

---

## Self-Review Checklist

- [ ] Each phase committed/merged independently; suite green at every phase boundary.
- [ ] `grep` confirms: one banned-word source, one impl per delta, one `run_analysis_spine`.
- [ ] `--persona` works on `report`, `morning`, **and** `ask`.
- [ ] No `_PRECEDENCE_RULE`; no `_DIGEST_WRITER_BASE` voice text; no `ANALYST_INSTRUCTIONS`/`ANSWERER_INSTRUCTIONS` voice duplication.
- [ ] Morning capsule and `report` capsule for one pitcher cite identical numbers.
- [ ] `bench/` quality (`directional_consistency`) not regressed vs baseline.
- [ ] Morning token/wall-clock within tolerance of `/tmp/usage.before.json`.
- [ ] `ruff` + `ty` clean.

## Out of Scope (do not implement here)

- Changing the Pitching+ model, the 13-outcome attribution, or any metric definition.
- New personas or new output targets (the composer makes these cheap *later*).
- Provider/model routing changes (`config.PROVIDERS` / `MINI_PROVIDERS`).
- Reworking the scout signal taxonomy or `_WEIGHTS` (Phase 2 changes *where* facts come from, not *what* counts as interesting).
- The deferred entry-point merge beyond the Phase 4 evaluation.
