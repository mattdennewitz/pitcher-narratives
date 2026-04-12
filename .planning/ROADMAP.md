# Roadmap: Pitcher Narratives

## Milestones

- ✅ **v1.0 MVP** — Phases 1-4 (shipped 2026-03-26)
- ✅ **v1.3 Editor-Anchor Reflection Loop** — Phases 5-11 (shipped 2026-03-28)
- ✅ **v1.4 Interactive Pitcher Q&A** — Phases 12-14 (shipped 2026-03-30)
- ✅ **v1.6 Multi-Agent Pipeline** — Phase 15 (shipped 2026-04-03)
- ✅ **v1.7 Multi-Year Data & Game Type Filtering** — Phases 16-18 (shipped 2026-04-03)
- ✅ **v1.8 Cross-Season Trend Analysis** — Phases 19-22 (shipped 2026-04-08)
- ✅ **v1.9 Pipeline Consolidation** — Phases 23-24 (shipped 2026-04-10) — see [archive](milestones/v1.9-ROADMAP.md)
- 🚧 **v1.10 Output Personas** — Phases 05-09 (in progress)

## Phases

<details>
<summary>✅ v1.9 Pipeline Consolidation (Phases 23-24) — SHIPPED 2026-04-10</summary>

- [x] Phase 23: Remove Old Pipeline (2/2 plans) — completed 2026-04-10
- [x] Phase 24: Verification & Cleanup (1/1 plans) — completed 2026-04-10

</details>

### 🚧 v1.10 Output Personas (In Progress)

**Milestone Goal:** Let users pick the voice and output shape of the `pitcher-narratives` writer via a `--persona` flag, without changing the underlying multi-agent analysis pipeline.

- [ ] **Phase 05: Persona Module Scaffolding** - Extract shared base prompt, define SCOUT overlay, build composer with byte-parity fixture
- [ ] **Phase 06: Pipeline Integration & Scout Parity Gate** - Wire persona through pipeline factory with scout-default; phase-exit gate on byte-parity
- [ ] **Phase 07: Analyst Persona** - Build newsletter voice overlay with teaching vocabulary and hallucination-guard allowlist
- [ ] **Phase 08: Generic Persona** - Build sectioned-with-table format, validate against anchor check and hallucination guard (highest-risk phase)
- [ ] **Phase 09: CLI Wiring** - Expose --persona and --list-personas on pitcher-narratives, guard other CLIs

## Phase Details

### Phase 05: Persona Module Scaffolding
**Goal**: A new `personas.py` module exists with the Persona dataclass, SHARED_WRITER_BASE, SCOUT overlay, registry, and composer -- and the composed scout prompt is byte-identical to the v1.9 writer prompt
**Depends on**: Phase 24 (v1.9 complete)
**Requirements**: PERSONA-01, PERSONA-02, PERSONA-03, PERSONA-04, PERSONA-05, PERSONA-06, VOICE-01, TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. `from pitcher_narratives.personas import Persona, PERSONAS, DEFAULT_PERSONA, SHARED_WRITER_BASE, build_writer_system_prompt, get_persona` succeeds without error
  2. `build_writer_system_prompt(PERSONAS["scout"])` returns a string byte-identical to the frozen fixture at `tests/fixtures/writer_prompt_scout.txt`
  3. `SHARED_WRITER_BASE` contains the "EXPLAIN THE MODEL" instruction and contains zero scout-specific voice words (both verified by passing tests)
  4. `get_persona("bogus")` raises `ValueError`; `get_persona("scout")` returns `DEFAULT_PERSONA`
  5. `test_scout_composed_prompt_is_byte_identical_to_v19`, `test_base_prompt_has_no_voice_words`, and `test_base_prompt_has_explainer_section` all pass green
**Plans**: TBD

### Phase 06: Pipeline Integration & Scout Parity Gate
**Goal**: The pipeline is persona-aware -- `make_pipeline_agents` accepts a persona argument, the old `_WRITER_PROMPT` constant is deleted from pipeline.py, and scout behavior is byte-identical to v1.9 through the full pipeline path
**Depends on**: Phase 05
**Requirements**: PERSONA-07, PERSONA-08, PERSONA-09, TEST-05 (scout portion)
**Success Criteria** (what must be TRUE):
  1. `_WRITER_PROMPT` no longer exists in `pipeline.py`; the writer agent is built from `build_writer_system_prompt(persona)`
  2. `make_pipeline_agents(provider, thinking)` (no persona arg) and `make_pipeline_agents(provider, thinking, SCOUT)` produce writer agents with identical system prompts
  3. `pitcher-ask --pipeline` (the `analyst.py:618` positional call) works without modification -- the new default argument preserves backward compatibility
  4. A TestModel-based scout smoke test runs the pipeline end-to-end and the composed writer prompt equals the frozen fixture
  5. All existing pipeline tests pass unchanged
**Plans**: TBD

**NOTE: Phase-exit gate.** Phase 06 cannot be marked complete until `test_scout_composed_prompt_is_byte_identical_to_v19` passes through the full pipeline integration path. This is the milestone's hardest invariant -- scout byte-parity.

### Phase 07: Analyst Persona
**Goal**: An ANALYST persona exists with a newsletter voice targeting analytically-inclined fans, inheriting factual discipline from scout, with teaching vocabulary permissions and a per-persona hallucination-guard allowlist
**Depends on**: Phase 06
**Requirements**: VOICE-02, PERSONA-10 (analyst portion), TEST-05 (analyst portion), TEST-06 (analyst portion), TEST-07 (analyst portion)
**Success Criteria** (what must be TRUE):
  1. `get_persona("analyst")` returns the ANALYST persona whose overlay targets 450-800 words with newsletter voice and teaching vocabulary permissions
  2. `build_writer_system_prompt(ANALYST)` starts with `SHARED_WRITER_BASE` and includes the parent (scout) overlay's factual-discipline rules
  3. `check_hallucinated_metrics(text, persona="analyst")` does not false-positive on analyst vocabulary (`playability`, `tunneling gap`, `pitch tree`, `arsenal depth`)
  4. A TestModel-based analyst smoke test runs the pipeline and produces a non-empty narrative that passes the anchor check and hallucination guard
  5. `assert_analyst_shape(text)` validates word-count bounds and allowed structural elements
**Plans**: TBD

### Phase 08: Generic Persona
**Goal**: A GENERIC persona exists with a sectioned-with-summary-table format, validated against the shared anchor check and hallucination guard -- the only phase that may conditionally touch anchor.py
**Depends on**: Phase 06
**Requirements**: VOICE-03, PERSONA-10 (generic portion), PERSONA-11, TEST-05 (generic portion), TEST-06 (generic portion), TEST-07 (generic portion)
**Success Criteria** (what must be TRUE):
  1. `get_persona("generic")` returns the GENERIC persona whose overlay fixes sections in order (Stuff, Location, Run Value & Execution, Trend, Game Shape, Summary Table) and forbids h1 headings
  2. A synthetic generic capsule (with headings + summary table) passes both the hallucination guard and anchor check without false positives -- OR, if false positives occur, a one-line `ANCHOR_PROMPT` addendum has been applied and the re-test passes clean
  3. `check_explainer_present(capsule)` post-processor runs after the writer's capsule and logs a warning to stderr when the "explain the model" content is missing
  4. A TestModel-based generic smoke test runs the pipeline and `assert_generic_shape(text)` validates exactly one markdown table, correct row count tied to KeySignals, allowed section set, and no h1 headings
  5. Hallucination guard regression: a known-dirty capsule (fabricated section or invented metric in a table row) is correctly flagged
**Plans**: TBD

**NOTE: Highest-risk phase.** Phase 08 is the only phase that *may* touch `anchor.py` (a conditional one-line addendum to `ANCHOR_PROMPT` if the generic persona's summary table produces false positives). Phase 08 also owns the `check_explainer_present` post-processor (PERSONA-11) and the hallucination guard's per-persona allowlist wiring for the generic persona. Phases 05-07 and 09 must NOT touch `anchor.py`.

### Phase 09: CLI Wiring
**Goal**: Users can select a persona via `--persona {scout,analyst,generic}` on `pitcher-narratives`, list available personas via `--list-personas`, and the other two CLIs explicitly reject the flag
**Depends on**: Phase 07, Phase 08
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, TEST-08
**Success Criteria** (what must be TRUE):
  1. `pitcher-narratives --persona analyst -p 656302 -w 10` generates a report using the analyst persona (and `--persona scout` / no flag are observationally identical)
  2. `pitcher-narratives --list-personas` prints all three personas (id, display_name, description) to stdout and exits 0 without calling the LLM
  3. `pitcher-narratives --persona bogus` exits 2 with an argparse error naming valid choices; `--persona SCOUT` (uppercase) normalizes to `scout` and succeeds
  4. `pitcher-ask --persona scout` and `pitcher-scout --persona scout` both exit 2 with argparse errors
  5. `pitcher-narratives -v --persona analyst -p 656302 -w 10` logs `persona=analyst` to stderr alongside existing verbose output
**Plans**: TBD

## Progress

**Execution Order:** 05 -> 06 -> 07 -> 08 -> 09

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 05. Persona Module Scaffolding | v1.10 | 0/TBD | Not started | - |
| 06. Pipeline Integration & Scout Parity Gate | v1.10 | 0/TBD | Not started | - |
| 07. Analyst Persona | v1.10 | 0/TBD | Not started | - |
| 08. Generic Persona | v1.10 | 0/TBD | Not started | - |
| 09. CLI Wiring | v1.10 | 0/TBD | Not started | - |
