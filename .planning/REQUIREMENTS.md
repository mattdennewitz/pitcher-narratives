# v1.10 Output Personas — Requirements

**Milestone:** v1.10 Output Personas
**Defined:** 2026-04-11
**Previous milestone:** v1.9 Pipeline Consolidation (shipped 2026-04-10)

---

## Milestone Goal

Let users pick the voice and output shape of the `pitcher-narratives` writer via a `--persona` flag, without changing the underlying multi-agent analysis pipeline or the `pitcher-ask` / `pitcher-scout` paths.

## Scope

This milestone is **writer-layer-only**. It adds a new `personas.py` module, changes the writer agent construction in `pipeline.py`, and wires a CLI flag through `cli.py`. Every other module — specialists, auditor, signal extractor, anchor check infrastructure, hallucination guard regex, executive summary, data pipeline, engine, context assembly, resolver, analyst agent — stays behavioral as-is. The one possible exception is a single-line tolerance addendum to `ANCHOR_PROMPT` in `anchor.py`, applied in Phase 08 **only if** a synthetic-generic-capsule test produces false positives (see `research/SUMMARY.md` Disagreement 1).

---

## v1.10 Requirements

### PERSONA — Persona Definition Schema, Overlay Mechanism, and Shared-Base Enforcement

- [ ] **PERSONA-01**: A `Persona` frozen dataclass exists in a new `src/pitcher_narratives/personas.py` module carrying `id`, `display_name`, `description`, `overlay` (string), `length_target` (word-count range), and an optional `parent` field for overlay inheritance.
- [ ] **PERSONA-02**: `src/pitcher_narratives/personas.py` exposes a `PERSONAS: dict[str, Persona]` registry plus a `get_persona(persona_id: str) -> Persona` lookup that raises `ValueError` on unknown ids.
- [ ] **PERSONA-03**: `src/pitcher_narratives/personas.py` exposes `DEFAULT_PERSONA = PERSONAS["scout"]` as a module-level constant usable as a default argument.
- [ ] **PERSONA-04**: A `SHARED_WRITER_BASE` string constant in `personas.py` is extracted from the v1.9 `_WRITER_PROMPT` with all scout-specific voice words lifted out into the scout overlay. The base contains the analytical contract only (directional consistency, KeySignals obligations, temporal grounding, "no outcome stats" guardrail).
- [ ] **PERSONA-05**: A `build_writer_system_prompt(persona: Persona) -> str` composer function in `personas.py` concatenates `SHARED_WRITER_BASE` + the persona's overlay with `\n\n` as separator. When `persona.parent` is set, the parent's overlay is composed first, then the child's overlay is appended — supporting multi-level overlay inheritance.
- [ ] **PERSONA-06**: `SHARED_WRITER_BASE` contains a named "EXPLAIN THE MODEL" instruction (present in every composed persona prompt by construction) that requires the writer to contextualize Pitching+ grades (S+ = stuff, L+ = location, P+ = combined) and the decisions the model made. The base has zero scout-specific voice words.
- [x] **PERSONA-07**: The `_WRITER_PROMPT` constant is removed from `pipeline.py`; the writer agent in `make_pipeline_agents` is built from `build_writer_system_prompt(persona)` instead.
- [x] **PERSONA-08**: `make_pipeline_agents(provider, thinking, persona: Persona = DEFAULT_PERSONA)` accepts an optional persona argument with a default that preserves the existing positional call at `analyst.py:618`.
- [x] **PERSONA-09**: `generate_pipeline_streaming(..., persona: str = "scout")` and `_run_pipeline(..., persona: str = "scout")` accept a string persona id and resolve it to a `Persona` object via `get_persona()` before passing to `make_pipeline_agents`.
- [x] **PERSONA-10**: `check_hallucinated_metrics(narrative: str, persona: str | None = None)` gains an optional `persona` parameter. When set, a `_PERSONA_KNOWN_METRICS` dict adds per-persona safe phrases (e.g. analyst newsletter vocabulary `playability`, `tunneling gap`, `pitch tree`, `arsenal depth`) to the allowlist for that run. Calls without the persona argument behave identically to v1.9.
- [ ] **PERSONA-11**: A `check_explainer_present(capsule: str) -> bool` post-processor runs after the writer's capsule lands in `_run_pipeline`. When it returns `False`, the CLI logs a warning to stderr (non-fatal, informational) so operators see when a persona silently dropped the "explain the model" content. The check is a pragmatic keyword scan, not a new LLM call.

### VOICE — The Three Personas

- [ ] **VOICE-01**: A `SCOUT` persona constant in `personas.py` whose overlay captures the current v1.9 scout voice (banned-word list, three-metric-maximum rule, 2-3 paragraph capsule, conversational lead, plausibility filters). Composing `build_writer_system_prompt(SCOUT)` produces the canonical v1.10 composed scout prompt (SHARED_WRITER_BASE + scout overlay) that is byte-identical to the frozen fixture at `tests/fixtures/writer_prompt_scout.txt`. (Resolution 1: the fixture captures the composed v1.10 prompt, not the raw v1.9 `_WRITER_PROMPT`, because PERSONA-06's "EXPLAIN THE MODEL" section is new content added to the shared base.)
- [x] **VOICE-02**: An `ANALYST` persona constant in `personas.py` shipping the newsletter voice targeting 450-800 words for analytically-inclined fans. The overlay inherits from SCOUT's voice-quality rules via the `parent` field (or equivalent mechanism), adds teaching-vocabulary permissions (`playability`, `tunneling gap`, `pitch tree`, `arsenal depth`), sets a full-sentence depth requirement for the "explain the model" rule, and enforces a hard word-count ceiling so the agent wraps up before blowing the token budget.
- [x] **VOICE-03**: A `GENERIC` persona constant in `personas.py` shipping the sectioned-with-summary-table format. The overlay fixes the section set in this order — `## Stuff`, `## Location`, `## Run Value & Execution`, `## Trend`, `## Game Shape`, `## Summary Table`. The summary table has exactly one row per populated `KeySignals` entry (not a fixed five). The overlay explicitly forbids `#` (h1) headings inside the capsule. The overlay inherits the analytical contract from the shared base and the factual-discipline rules from SCOUT's overlay (via `parent`).

### CLI — Command-Line Surface on `pitcher-narratives`

- [ ] **CLI-01**: `pitcher-narratives` accepts `--persona {scout,analyst,generic}` with `default="scout"`, `type=str.lower` (case-normalized), and `choices=sorted(PERSONAS.keys())`. Invalid values exit 2 with an argparse error naming the valid choices.
- [ ] **CLI-02**: `pitcher-narratives` accepts `--list-personas` as an `action="store_true"` flag that prints the registry (id, display_name, description) to stdout and exits 0 without calling the LLM or loading pitcher data.
- [ ] **CLI-03**: `pitcher-narratives --print-prompts` renders the composed writer prompt for the selected persona — it reads from `build_writer_system_prompt(get_persona(args.persona))` instead of the deleted `_WRITER_PROMPT` constant.
- [ ] **CLI-04**: `pitcher-narratives -v/--verbose` logs `persona=<id>` to stderr alongside the existing pitcher name, game dates, and pitch counts.
- [ ] **CLI-05**: `pitcher-narratives -p X -w Y` (no `--persona` flag) and `pitcher-narratives --persona scout -p X -w Y` are observationally identical — they resolve to the same `args.persona` string, the same composed writer prompt, and the same LLM agent instance.
- [ ] **CLI-06**: `pitcher-ask` and `pitcher-scout` do **not** accept `--persona`; attempting to pass the flag exits 2 with an argparse error. This guards against accidental copy-paste.

### TEST — Regression and Shape-Assertion Coverage

- [ ] **TEST-01**: A frozen fixture at `tests/fixtures/writer_prompt_scout.txt` contains the canonical v1.10 composed scout prompt (`build_writer_system_prompt(SCOUT)` output — SHARED_WRITER_BASE + scout overlay, same bytes, same line endings). The fixture is reviewer-friendly and diff-visible in PRs. (Resolution 1: fixture captures composed v1.10 prompt, not raw v1.9 `_WRITER_PROMPT`.)
- [ ] **TEST-02**: `tests/test_personas.py::test_scout_composed_prompt_is_byte_identical_to_v19` asserts `build_writer_system_prompt(SCOUT) == <fixture contents>`. This test is the phase-exit gate for Phase 06.
- [ ] **TEST-03**: `tests/test_personas.py::test_base_prompt_has_no_voice_words` asserts `SHARED_WRITER_BASE` does not contain the scout-specific voice words lifted into the SCOUT overlay (explicit banned-word list).
- [ ] **TEST-04**: `tests/test_personas.py::test_base_prompt_has_explainer_section` asserts `SHARED_WRITER_BASE` contains the "EXPLAIN THE MODEL" instruction block.
- [x] **TEST-05**: `tests/test_personas.py` contains one `TestModel`-based smoke test per persona (scout, analyst, generic). Each test runs the pipeline end-to-end via `PITCHER_NARRATIVES_TEST_MODEL=1` without a real LLM call and asserts: the composed writer prompt starts with `SHARED_WRITER_BASE`, the narrative is non-empty, the anchor check runs to completion, and the hallucination guard does not fire.
- [x] **TEST-06**: `tests/test_personas.py` contains three shape-assertion helpers — `assert_scout_shape(text)`, `assert_analyst_shape(text)`, `assert_generic_shape(text)` — that check word-count bounds, allowed structural elements, and banned elements per persona. The smoke tests from TEST-05 use them.
- [x] **TEST-07**: `tests/test_hallucination_guard.py` gains per-persona regression vectors — analyst newsletter vocabulary (`playability`, `tunneling gap`, etc.) does not false-positive when `persona="analyst"`, and a fabricated generic-persona section or invented metric in a table row is still caught by the guard.
- [ ] **TEST-08**: `tests/test_ask_cli.py::test_ask_cli_does_not_accept_persona` and `tests/test_scout_cli.py::test_scout_cli_does_not_accept_persona` (or equivalent existing test module) assert the two other CLIs reject the flag with an argparse error.

---

## Future Requirements (deferred)

The following features were considered for v1.10 and deferred, with reasoning:

- **Per-persona token budget override** (`PERSONA_TOKEN_BUDGETS` dict). Deferred — only needed if analyst/generic actually exceed `TOKEN_BUDGET_LARGE = 4096` in practice. Phase D will measure.
- **Per-persona streaming strategy field** (delta vs. line-buffered). Deferred — only needed if the generic persona's summary table streaming looks broken in a real terminal. Phase D will measure.
- **`--describe-persona <id>` flag.** Deferred to v1.11 — `--list-personas` covers the discoverability gap for now and users can read `personas.py` for full overlay text.
- **`--compare` flag (runs all three personas in one invocation).** Deferred to v1.11 — useful for eval and side-by-side review, but adds orthogonal complexity to the CLI layer. Better as a follow-up once the three personas are stable.
- **`RUN_LIVE_LLM=1` gated real-model golden samples per persona.** Deferred to v1.11+ — real-model goldens are LLM-drift detection, not regression safety, and belong in a separate CI lane.
- **Sentinel-block or table-cell-stripping mode on `check_hallucinated_metrics`.** Deferred — the per-persona allowlist (PERSONA-10) solves the analyst vocabulary case; table-cell stripping only becomes necessary if Phase D produces a real false positive on the generic persona's summary table. Flagged as a Phase D decision.
- **Per-persona `MAX_REVISIONS` cap.** Deferred — ship with the shared `MAX_REVISIONS = 3` for all three personas in v1.10. Revisit in a follow-up only if generic produces visibly more anchor revisions than scout.
- **`anchor.py` persona-aware `build_anchor_message` branch.** Rejected — see `research/SUMMARY.md` Disagreement 1. A one-line `ANCHOR_PROMPT` tolerance addendum is applied in Phase D **only if** testing surfaces false positives on the generic persona.
- **`EXPLAINER_MISSING` anchor `WarningCategory`.** Rejected — the anchor's job is fact-checking, not editorial enforcement. The `check_explainer_present` post-processor (PERSONA-11) handles this orthogonally.
- **Persona rename (`generic` -> `structured` or `sectioned`).** Deferred to v1.11 — evidence-driven rename based on user feedback, with `generic` kept as an alias if renamed.

---

## Out of Scope

The following are explicitly **not** in v1.10 and will be rejected in review:

- **Persona support in `pitcher-ask`.** The Q&A path does not get a `--persona` flag. Q&A is fundamentally different from narrative generation (tool-calling, streaming answers to questions), and voice selection there is a separate design problem. Explicit rejection test in TEST-08.
- **Persona support in `pitcher-scout`.** Scout is a no-LLM signal scanner; the `--curate` LLM path is editorial, not generative. No persona knob.
- **User-defined or customizable personas.** No TOML config files, no `--custom-persona` flag, no env-var overrides for persona content. Personas are authored in code by project maintainers so quality gates (overlay-contract tests, byte-parity gate) can enforce invariants. Customizable personas would bypass those gates.
- **Anchor-check restructuring for structural tolerance beyond a single prompt-text addendum.** If the generic persona triggers false positives, the mitigation is a one-line prompt tweak, not a `persona_hints` parameter, not a branching `build_anchor_message`, and not a new `WarningCategory`.
- **Cache-plumbing refactoring.** Anthropic system-prompt caching (`anthropic_cache_instructions`) is off today; this milestone does not turn it on or restructure the writer agent to accommodate caching of a shared base. Deferred to v1.11+ as an optimization with evidence.
- **Changes to specialists, auditor, signal extractor, signal extractor prompt, anchor revision-loop mechanics, hallucination regex internals, executive summary agent, data loaders, engine metrics, context assembly, resolver, analyst agent, scout scoring, or curator.** Anything outside the writer layer and its CLI surface is untouched.
- **Multi-voice output in a single run** (producing scout + analyst + generic in one invocation). `--compare` is deferred; today's CLI runs exactly one persona per invocation.
- **Voice drift regression detection via LLM output comparison.** We assert shape (word count, structural elements, allowed metrics) not exact text. Real-LLM output golden tests are deferred per TEST scope above.

---

## Traceability (Requirements -> Phases)

| REQ-ID | Phase | Status | Notes |
|--------|-------|--------|-------|
| PERSONA-01 | Phase 05 | Pending | Persona frozen dataclass in personas.py |
| PERSONA-02 | Phase 05 | Pending | PERSONAS registry + get_persona lookup |
| PERSONA-03 | Phase 05 | Pending | DEFAULT_PERSONA = PERSONAS["scout"] |
| PERSONA-04 | Phase 05 | Pending | SHARED_WRITER_BASE extraction |
| PERSONA-05 | Phase 05 | Pending | build_writer_system_prompt composer |
| PERSONA-06 | Phase 05 | Pending | "EXPLAIN THE MODEL" instruction in base |
| PERSONA-07 | Phase 06 | Complete | _WRITER_PROMPT removed, writer built from composer |
| PERSONA-08 | Phase 06 | Complete | make_pipeline_agents gains persona kwarg |
| PERSONA-09 | Phase 06 | Complete | generate_pipeline_streaming / _run_pipeline gain persona kwarg |
| PERSONA-10 | Phase 07 + 08 | Complete | Analyst allowlist (Phase 07), generic allowlist (Phase 08) |
| PERSONA-11 | Phase 08 | Pending | check_explainer_present post-processor |
| VOICE-01 | Phase 05 | Pending | SCOUT persona constant (byte-identical to v1.9) |
| VOICE-02 | Phase 07 | Complete | ANALYST persona constant (newsletter voice) |
| VOICE-03 | Phase 08 | Complete | GENERIC persona constant (sectioned + table) |
| CLI-01 | Phase 09 | Pending | --persona flag on pitcher-narratives |
| CLI-02 | Phase 09 | Pending | --list-personas flag |
| CLI-03 | Phase 09 | Pending | --print-prompts uses composed prompt |
| CLI-04 | Phase 09 | Pending | --verbose logs persona id |
| CLI-05 | Phase 09 | Pending | No-flag and --persona scout are identical |
| CLI-06 | Phase 09 | Pending | pitcher-ask and pitcher-scout reject --persona |
| TEST-01 | Phase 05 | Pending | Frozen fixture writer_prompt_scout.txt |
| TEST-02 | Phase 05 | Pending | Byte-identity test (phase-exit gate for Phase 06) |
| TEST-03 | Phase 05 | Pending | Base prompt no-voice-words test |
| TEST-04 | Phase 05 | Pending | Base prompt explainer-section test |
| TEST-05 | Phase 06 + 07 + 08 | Complete | Scout smoke (06), analyst smoke (07), generic smoke (08) |
| TEST-06 | Phase 06 + 07 + 08 | Complete | Scout shape (06), analyst shape (07), generic shape (08) |
| TEST-07 | Phase 07 + 08 | Complete | Analyst guard vectors (07), generic guard vectors (08) |
| TEST-08 | Phase 09 | Pending | pitcher-ask and pitcher-scout reject --persona |
