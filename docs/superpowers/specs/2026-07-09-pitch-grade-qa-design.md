# Pitch-Grade Q&A (`ask` command) — Design

**Date:** 2026-07-09
**Status:** Approved for planning

## Goal

Add a CLI command that answers, in prose, **why a pitcher's pitch earns a particular Pitching+ grade** — e.g. `pn ask "why does Jared Jones's fastball grade 92 stuff+"`. This is the first of an intended **library of runtime skills** exposed to a single question-answering tool: the growth surface is skills, not per-question code.

The answer must be **grounded** (every number from pre-computed data, no LLM arithmetic) and **fact-checked** (reuse the existing data-auditor), matching the discipline of the report pipeline.

## Scope

**In scope (v1):** grade-explanation questions only — "why does `<pitcher>`'s `<pitch>` grade `<P+ / S+ / L+ value>`". Covers any pitcher, any pitch in their arsenal, and all three grade families (S+, L+, P+).

**Out of scope (v1):** arsenal comparisons, appearance/trend/workload questions, free-form pitcher chat, interactive REPL. The command declines out-of-scope questions briefly. (These become later skills on the same substrate.)

## Key decision: reuse the spine's front-half (R1)

Grade explanation is **frame-agnostic**, so it maps onto the analysis spine's frame-agnostic core rather than the tail. The evidence a grade explanation needs is **already assembled** by the spine's specialist-input builders:

- `pipeline._build_stuff_input(ctx)` renders per-pitch **S+** (window/season/delta), velocity & pfx_x/pfx_z with **delta-vs-league and NORMAL/OUTLIER tags** (`outlier_tag`), **stuff-only predictions** (xWhiff/xSwing/xRV100) with league comparison, **arm-slot shape vs slot expectation** (`render_pitch_shape`), and rendered league baselines (`compute_league_baselines`).
- `_build_location_input` is the L+ analogue. (`_build_runvalue_input` exists for the run-value specialist but is **not** wired in v1 — the stuff input already surfaces the `xRV100_S` pricing a grade explanation needs.)

Therefore `ask` builds **no new data-tool layer and no `grades.py`**. It is a thin front-end over the spine's front-half.

**R1 (chosen):** run one **focused Q&A agent** over the reused grade-family input (not the full 5-specialist spine), then the data-auditor. Cheaper and scoped to the question, still fully grounded and fact-checked. Rejected **R2** (run `run_spine_core`, extract a specialist slice) as heavier per question and requiring a scoping step over whole-arsenal output.

## Architecture

**Flow (`qa.answer_question`):**

1. **Parse** the question → `(pitcher_id, pitch_type, grade_family)`.
   - Pitcher: `resolver.extract_pitcher_from_question` → `resolver.resolve` (deterministic, existing). Ambiguous → return candidate list; not found → error.
   - Pitch: deterministic synonym map (`fastball`→`FF`, `sinker`/`two-seam`→`SI`, `slider`→`SL`, `curve`/`curveball`→`CU`, `change`/`changeup`→`CH`, `cutter`→`FC`, `sweeper`→`ST`, …). `fastball` when the pitcher throws both FF and SI resolves to the **most-thrown** of the two, and the answer notes the choice.
   - Grade family: deterministic map (`stuff+`/`stuff`/`s+`→`S`; `location+`/`command`/`l+`→`L`; `pitching+`/`p+`→`P`). Default `S` if unspecified.
   - The cited value (e.g. "92") is **optional** and not required — the tool explains the *actual* grade and notes if the cited number disagrees.
2. **Build context:** `data.load_pitcher_data(pitcher_id, …)` → `context.assemble_pitcher_context(data)` → `PitcherContext`. Same assembly as the report; default window; grade read from the frame-agnostic `season_s_plus`.
3. **Select the grade-family input:** new public dispatcher `pipeline.build_grade_input(ctx, family)`:
   - `S` → `_build_stuff_input(ctx)`
   - `L` → `_build_location_input(ctx)`
   - `P` → `_build_stuff_input(ctx)` **+** `_build_location_input(ctx)` (P+ = stuff + location; `P − S` isolates location, per `pitching-plus-conventions`).
4. **Run the focused agent:** `Agent(model, output_type=str, system_prompt=<scoped Q&A prompt>, toolsets=[skill_toolset()], retries=3)`, capable model from `config` (not mini — the `run_skill_script`/DeepSeek incident shows weak models mishandle skill tooling). Input = the reused UserPrompt + a scoping instruction naming the target pitch and grade. The agent consults the `explaining-pitch-grades` runtime skill for method and narrates an answer about **that pitch**, using the rest of the arsenal as the secondaries contrast.
5. **Fact-check:** run the existing **data-auditor** over `ground_truth = rendered input`, `answer`. On flags, do **one revision pass** (reuse `build_fact_revision_message` + a revision run), mirroring the report's single-revision pattern.
6. **Return / print** the final prose answer to stdout.

**The reasoning lives in the skill, not the agent prompt.** The system prompt is a thin orchestration shell (resolve → consult skill → narrate the named pitch → never compute → decline out-of-scope → say so if data missing). Adding a future skill extends what `ask` (and the report specialists, which already carry `skill_toolset()`) can reason about, with no new code.

## Reuse map

| Need | Reused symbol | New? |
|---|---|---|
| Pitcher resolution from NL | `resolver.extract_pitcher_from_question`, `resolver.resolve` | reuse |
| Context assembly | `data.load_pitcher_data`, `context.assemble_pitcher_context` | reuse |
| Grade + baseline + NORMAL/OUTLIER + shape evidence | `pipeline._build_stuff_input` (S), `_build_location_input` (L) — both for P, `compute_league_baselines`, `outlier_tag`, `render_pitch_shape` | reuse (via new public dispatcher) |
| Skill library exposure | `agent_skills.skill_toolset()` | reuse |
| Model / settings | `config` provider+model, `make_model_settings` | reuse |
| Anti-fabrication | data-auditor agent, `_build_specialist_audit_input`, `build_fact_revision_message`, `AuditResult` | reuse (via public audit runner) |
| CLI | argparse subparser pattern in `cli.py` | reuse |

## New components

- **`cli.py`** — `ask` subparser: positional `question`, optional `--season`, `--model`. Dispatches to `qa.answer_question`.
- **`qa.py`** (new, focused module — keeps this out of the 2,898-line `pipeline.py`) — `answer_question(question, *, season, model_override)`: parsing, context build, input selection, focused-agent construction, audit + one-revision, formatting. Deterministic parsing helpers (`PITCH_SYNONYMS`, `GRADE_SYNONYMS`, `parse_grade_question`).
- **`src/pitcher_narratives/skills/explaining-pitch-grades/SKILL.md`** (new, `audience: runtime`) — the reasoning discipline written for the reused-input flow: anchor the grade to the **class baseline, not 100**; a NORMAL trait is **not** a driver; reconcile grade↔`xRV100` sign; cite `xWhiff_S`/`xSwing_S` for behavioral claims; **no velocity-causation**; contrast with the arsenal. Cross-references `pitching-plus-conventions`. (The existing `.claude/skills/explaining-pitch-grades` Claude-Code skill, with its `explain_grade.py`, stays for repo investigation — same reasoning, different substrate.)

### Public seams to add (targeted, in-scope)

- `pipeline.build_grade_input(ctx, family) -> UserPrompt` — public dispatcher over the existing private `_build_*_input` builders; added to `pipeline.__all__`. Avoids `qa.py` importing module-privates.
- A public audit runner (reuse the spine's auditor + `_build_specialist_audit_input`) callable standalone as `run_data_audit(ground_truth, answer) -> AuditResult`, exported from `pipeline`.

## Error handling

| Case | Behavior |
|---|---|
| Pitcher not found | Message: couldn't identify a pitcher in the question. |
| Ambiguous pitcher | List candidate names for disambiguation. |
| Pitch not in arsenal | Message listing the pitches the pitcher actually throws. |
| `fastball` with FF+SI | Resolve to most-thrown; answer notes the choice. |
| No MLB data for pitcher/pitch | Say so; do not fabricate. |
| Out-of-scope question | Brief decline (grade-explanation only in v1). |
| Auditor flags after one revision | Return the revised, grounded answer; omit any unsupported claim. |

## Module boundaries

- `qa.py` depends on `resolver`, `data`, `context`, `pipeline` (public seams), `agent_skills`, `config`. It owns orchestration only; all computation stays in the reused modules.
- `pipeline.py` gains two small public functions; its internals are otherwise untouched.
- The runtime skill is pure reference text; it ships in the package skills dir and loads via the existing `audience: runtime` gate.

## Testing (TDD)

- **Deterministic parse tests** (`parse_grade_question`): `"why does Jared Jones's fastball grade 92 stuff+"` → `(683003, "FF", "S")`; location and pitching variants; `sinker`→`SI`; `fastball` ambiguity → most-thrown + note; unknown pitch → error; out-of-scope phrasing → declined.
- **Reuse-contract test:** assemble context for 683003, `build_grade_input(ctx, "S")`, assert the rendered text contains the FF **S+** and NORMAL/OUTLIER tags — locks the evidence contract the agent depends on.
- **Auditor integration test:** feed a deliberately fabricated answer + ground truth to `run_data_audit`, assert it flags (reuse existing auditor test patterns).
- **Behavioral eval (smoke, non-blocking):** `ask` about Luis Medina's FF → answer anchors to the class baseline, uses the MLB grade, avoids velocity-causation. Kept as an eval given LLM nondeterminism, mirroring the skill's GREEN check.

## Open detail for planning

- Exact `load_pitcher_data` parameters for a frame-agnostic (season-level) build — confirm the default window is acceptable and that `season_s_plus` is the grade the answer cites.
