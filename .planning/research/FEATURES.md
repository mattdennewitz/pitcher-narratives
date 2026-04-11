# Feature Landscape — v1.10 Output Personas

**Project:** Pitcher Narratives
**Milestone:** v1.10 — Output Personas
**Domain:** Persona / voice system layered on an existing multi-agent LLM writing CLI
**Researched:** 2026-04-11
**Confidence:** HIGH for codebase-grounded findings (schema, overlay mechanism, voice targets against existing `_WRITER_PROMPT`), MEDIUM for sports-writing voice references (based on training data, not live fetches — WebSearch unavailable in this environment)

## Scope Guardrail

Every feature below touches ONLY these surfaces:
- `src/pitcher_narratives/cli.py` (new `--persona` flag and related CLI affordances)
- `src/pitcher_narratives/pipeline.py` (writer prompt assembly, shared base, per-persona overlay injection)
- A NEW module, `src/pitcher_narratives/personas.py` (persona registry, schemas, and overlay text)
- Persona fixtures under `tests/fixtures/personas/` (new) and test files under `tests/test_personas.py` / `tests/test_pipeline_persona.py` (new)

EXPLICITLY untouched: `ask_cli.py`, `analyst.py`, `scout.py`, `scout_cli.py`, `resolver.py`, `data.py`, `engine.py`, `context.py`, `anchor.py` (module stays read-only — we only wrap its outputs at the pipeline level). No changes to any specialist prompt, the data auditor prompt, the signal extractor prompt, or the executive summary prompt.

---

## Category 1: Persona Definition Schema

### Table Stakes

- **Persona is a typed object, not a free-form string.** A new `Persona` pydantic BaseModel in `personas.py` with fields: `id: Literal["scout","analyst","generic"]`, `display_name: str`, `overlay_prompt: str`, `length_target: LengthTarget`, `format_mode: Literal["prose","sectioned"]`, `description: str` (one-line `--describe-persona` text).
- **Length targets are bounded, not open-ended.** `LengthTarget` carries `min_words: int`, `max_words: int`, and an advisory `target_words: int`. Scout ≈ 180–320 words (matches current 2–3 paragraph capsule). Analyst ≈ 450–800 words. Generic ≈ 400–700 words including the summary table. Word counts enforced post-hoc by a smoke test, not by the writer prompt (writers are bad at counting — see PITFALLS.md).
- **Every persona has a single canonical overlay string.** Not a templating DSL, not a partial-prompt builder. The overlay is one self-contained block of natural-language guidance that the pipeline concatenates onto the shared base.
- **Format mode is explicit.** `"prose"` tells the hallucination check to use the current regex pass unchanged. `"sectioned"` tells the hallucination check to pre-strip Markdown table cells before regex scanning (the generic persona is the only current consumer, but the field exists so future personas can opt in).
- **A single registry exports personas.** `PERSONAS: dict[str, Persona]` keyed by id, plus a `get_persona(id: str) -> Persona` function that raises a typed error on unknown id with a helpful "did you mean" message. No dynamic discovery, no plugin system.
- **Persona id → display name and description are stored once.** The `--list-personas` and `--describe-persona` CLI commands and any test fixtures all read from the same registry so docs and behavior never drift.

### Differentiators (defensible to defer to v1.11)

- **Persona exemplars (few-shot snippets).** A `exemplars: list[str] | None` field holding 1–2 hand-written paragraphs in the target voice, injected as a user-message few-shot. Deferred because v1.10's overlay prompts can ship voice guidance in plain English and because exemplars are expensive to maintain (every change to the underlying data shape risks making exemplars contradict reality).
- **Vocabulary allow/deny lists per persona.** Structured `vocabulary_avoid: frozenset[str]` and `vocabulary_prefer: frozenset[str]`. The current `_WRITER_PROMPT` embeds a "Never use" list inline and it works. Structuring it is cleaner but doesn't unblock v1.10.
- **Per-persona temperature override.** A `temperature: float | None = None` field. Analyst might benefit from 0.8 (more associative prose), generic might benefit from 0.5 (more predictable structure). Defer until we measure — v1.10 ships with the existing 0.7 for all three.
- **Per-persona `max_tokens` override.** The analyst persona plausibly wants a larger token budget than `TOKEN_BUDGET_LARGE`. Deferred — start with the shared budget and raise it in v1.11 only if golden samples show clipping.

### Anti-Features

- **Persona inheritance / "extends" relationships.** Rejected: three personas, one level. A class hierarchy is gold-plating until we have ≥5 personas or a clear child-of-child pattern.
- **User-defined personas from a config file or environment variable.** Rejected: every persona must pass the anchor check and the hallucination guard; opening it up to user overrides breaks the quality gates before they even run. Custom personas are a v2.x concern, not v1.10.
- **Persona defined as a Jinja/Mustache template over the base prompt.** Rejected: templating adds a second grammar on top of the prompt and makes the writer prompt harder to read in isolation. Plain-string concatenation is sufficient for three personas.
- **Persona registry as a Python plugin entry point.** Rejected: personas are internal, versioned with the codebase, and need to be tested as a unit with the writer prompt. Entry-point discovery adds complexity without delivering anything v1.10 needs.

---

## Category 2: Overlay Mechanism

### Table Stakes

- **Shared base prompt + trailing overlay.** The current `_WRITER_PROMPT` constant is refactored into `_WRITER_BASE_PROMPT` (shared, mandatory, defines the "explain the model" contract and the directional-consistency / anti-hallucination rules) plus a per-persona overlay. At pipeline-build time, the writer's `system_prompt` is `f"{_WRITER_BASE_PROMPT}\n\n{persona.overlay_prompt}"`. Simple, debuggable, one code path.
- **The base owns everything that cannot be safely overridden.** Directional consistency, "use only specialist data", KeySignals obligations (top_improvement and top_concern must each be addressed), the temporal-grounding rule, the "explain Pitching+ model decisions" contract. These live in the base and cannot be weakened by any overlay.
- **The overlay owns everything the persona controls.** Voice, sentence rhythm, length target, structural template (prose vs. sectioned), vocabulary preferences, what the reader is assumed to know, how much to teach the Pitching+ framework.
- **Overlay is appended, not spliced.** No anchor tags in the base (`<<VOICE>>`, etc.), no search-and-replace. LLMs interpret the last block of the system prompt as the most salient, which is exactly where persona voice should land.
- **Writer agent is built per-request with the selected persona.** `make_pipeline_agents(..., persona: Persona)` takes the persona and constructs the writer agent with the composed prompt. `_WRITER_PROMPT` the constant goes away; `build_writer_prompt(persona: Persona) -> str` replaces it. `make_pipeline_agents` default arg is `PERSONAS["scout"]` so every existing caller is unchanged.
- **The base prompt's rules are self-describing and the overlay can reference them by section name.** E.g. the base has a section header "DIRECTIONAL CONSISTENCY" and the analyst overlay can say "Explain decisions in the tone described below, but never soften the DIRECTIONAL CONSISTENCY rule above." This keeps the two halves coherent without introducing a templating mechanism.
- **`pipeline.py` exposes a single public helper for prompt assembly.** `build_writer_prompt(persona)` returns the fully-composed writer system prompt. `--print-prompts` uses it so operators can see the exact composed prompt per persona without rerunning the model.

### Differentiators

- **Overlay validation at import time.** A module-level assertion that every registered persona's composed prompt contains the KeySignals obligations and the directional-consistency rule (easy substring check). Catches a malformed overlay before any test runs. Cheap and worth it — move to table stakes if it takes <30 minutes to implement.
- **Per-section caching of the base prompt via `CachePoint`.** The base prompt is identical across all three personas, so inserting a `CachePoint` between base and overlay lets pydantic-ai reuse the cached prefix across per-persona runs. Defer — measurable only under `--compare` batch runs, which is itself deferred.

### Anti-Features

- **Anchor-tag splicing.** Overlays with `{{VOICE}}` / `{{STRUCTURE}}` placeholders inside the base prompt. Rejected: introduces a template engine and obscures the actual prompt text for debugging.
- **Overlay as a system-prompt prepend.** Rejected: putting voice guidance BEFORE the hard rules makes the model rank voice higher than correctness. Overlays must come last.
- **Two-message system prompt (base as system, overlay as user preamble).** Rejected: pydantic-ai's `system_prompt=` takes a single string, mixing levels is a footgun, and the anchor check would have to know about the split.
- **Overlay as a function that mutates the base prompt string.** Rejected: makes the composed prompt impossible to predict without running Python. Overlays are data, not code.

---

## Category 3: Voice / Format Differentiation (per persona)

**Reference sources (MEDIUM confidence, training data, not live-fetched):** Baseball Prospectus feature articles and Effectively Wild show notes (conversational sabermetric tone; explains model internals; assumes sophisticated-but-not-specialist readers), Pitcher List pitch-by-pitch analytical pieces (heavier lean on GIFs and specific-pitch callouts; more playful voice), FanGraphs community research posts (longer, model-explaining, teaching tone), and the current `_WRITER_PROMPT` itself (for the scout persona, which must be preserved byte-identically in voice).

### 3a. Scout persona (default)

**Voice target (HIGH confidence — codified in the current `_WRITER_PROMPT`):**
Analyst-to-analyst voice. Front-office tone. Short-form. 2–3 paragraphs, prose only, no headings inside the capsule. Leads with the thread — the single most important story across the five specialists. Varies sentence length, short sentences land points. Scouting vocabulary ("stuff", "feel", "finding a groove", "getting tagged"). Avoids the banned vocabulary list ("degradation", "binary", "profiles as", "dominant", "elite", "massive spike"). At most three primary metrics across the whole capsule. No bullet points, no headers, no tables.

**Length target:** 180–320 words, 2–3 paragraphs. Matches current behavior.

**Structural elements:** Pure prose capsule. No internal headings. No tables. Followed (by the CLI, not the writer) by the three-bullet executive summary, Stuff Analysis, Data Audit, and Anchor Check sections.

**How much Pitching+ model explanation:** Light. Assumes the reader knows S+ = stuff-only and L+ = location-given-the-stuff. Explains ONLY the specific decision that the pipeline reached (e.g. "The slider's S+ of 128 is driven by the new vertical break, not the velocity"). Does not teach the framework from scratch.

**What it leads with:** The concrete change. "The two-seamer lost an inch of arm-side run last start and the whiff rate on it halved" — never "This report examines the recent performance of X".

**Preservation test:** A regression test (`tests/test_personas.py::test_scout_overlay_byte_identical_to_v1_9_writer_prompt`) asserts that `build_writer_prompt(PERSONAS["scout"]).strip() == _LEGACY_WRITER_PROMPT_SNAPSHOT.strip()` where the snapshot is the v1.9 `_WRITER_PROMPT` verbatim. This is the "byte-identical-ish" guarantee the milestone requires.

### 3b. Analyst persona (newsletter for analytically-inclined fans)

**Voice target (MEDIUM confidence — modeled on Baseball Prospectus + Effectively Wild + FanGraphs community research tone):**
Newsletter voice. First-person plural optional ("what we're seeing here is…"). Teaches as it analyzes — when it names S+ or L+, it takes a sentence to remind the reader what the metric measures and why the specialist reached its grade. Reader is assumed to be a fan with strong baseball literacy but NOT a working analyst. Longer sentences, more subordinate clauses than the scout voice, but still conversational. Similes and analogies are allowed ("think of L+ as the grade the command gets after the stuff is already priced in"). Can digress briefly to contextualize a finding ("for reference, league-average S+ on a sweeper is close to 100"). Still avoids cheerleading, still enforces directional consistency.

**Length target:** 450–800 words, 4–6 paragraphs. Long enough to teach, short enough to read over coffee.

**Structural elements:** Prose with optional narrative section markers (a bolded leading phrase at the start of each paragraph is allowed; full Markdown `##` headings are NOT — headings invite "meanwhile" energy that contradicts the base prompt's one-voice rule). No tables. No bullet lists. The expanded word budget is spent on explanation and context, not on more sections.

**Vocabulary shift:** Keeps the scout-persona banned-word list (still no "elite", no "dominant"). ADDS permission for teaching vocabulary: "model", "credit", "grade", "below-average", "holds up", "pencils out". Still three-metric-maximum per paragraph, but allowed to cite the same metric twice if the second citation is explaining the first.

**How much Pitching+ model explanation:** Heavy. The analyst overlay explicitly asks the writer to explain — in the reader's first encounter with each plus-metric — what the metric measures and why the pipeline's grade is what it is. "S+ of 128 on the slider means the stuff-only model scored it 28 percent above league average on physical characteristics alone; the vertical break is the driver."

**What it leads with:** The narrative hook, which can be a question or a setup ("Something changed in X's slider last start, and it isn't what you'd expect"). Still anchored to the top_improvement or top_concern signal per the base prompt, just dressed in a slower opening.

### 3c. Generic persona (sectioned + summary table)

**Voice target (MEDIUM confidence — modeled on default-LLM structured responses and front-office internal report layouts):**
Structured, category-first, teaching tone. This is the persona for the user who asks an LLM a question and wants the kind of sectioned response LLMs produce by default. Reader could be anyone — from a fantasy manager to a coach to a data consumer pasting the output into a shared doc. Each section stands on its own. Tone is informative, not conversational, but still avoids recitation (the three-metric cap still applies per section, not per capsule — the sectioning expands the total budget).

**Length target:** 400–700 words total across all sections, with a final summary table.

**Structural elements (HIGH importance — this is the one persona that breaks the "prose only" rule):**
- Markdown `##` headings for exactly these sections, in this order: `## Stuff`, `## Location`, `## Run Value & Execution`, `## Trend`, `## Game Shape`, `## Summary Table`. The section names are fixed by the persona so the anchor check and tests can rely on them.
- Each section is 2–4 sentences. No bullet lists inside sections (bullet lists encourage the writer to pad with category labels — see PITFALLS.md, pitfall 2).
- The final `## Summary Table` is a Markdown table with columns `Category | Grade | Note`, and rows `Stuff | ... | ...`, `Location | ... | ...`, `Run Value | ... | ...`, `Trend | ... | ...`, `Game Shape | ... | ...`. Grades are short scout-scale tags ("plus", "average", "below-average", "no change", "improving", "slipping"). Notes are one short phrase each. The table is tightly bounded — no free-form columns.
- The generic persona MUST NOT introduce section headings the writer invented. The allowed set is fixed by the overlay and enforced by a test.

**Vocabulary shift:** Same banned list as scout. Teaches a little less than analyst (the structure does the teaching — the reader can skim to the section they care about). Allowed to use the model names ("Stuff+", "Location+", "Pitching+") as section subjects without introducing them.

**How much Pitching+ model explanation:** Medium. Each section explains, in one sentence, what its column of the Pitching+ model measures, before citing the pipeline's finding. The summary table itself stands as a quick-reference explanation of the framework.

**What it leads with:** The Stuff section. There is no "lead" in the scout sense — the structure is the lead.

**Summary table tolerance rules (see Category 6 for testing implications):**
- Table cells are allowed to contain plus-metric names without triggering hallucination warnings (they're section subjects, not inventions).
- Table rows must correspond 1:1 with the five specialists. No extra rows, no missing rows.
- Anchor check sees the full generic-persona output, including the table. The base prompt's "do not invent data" rule still applies inside table cells.

### Shared (across all three personas)

- **All three personas must satisfy the KeySignals obligation.** Top improvement and top concern are both addressed in every persona. The base prompt enforces this and the anchor check validates it.
- **All three personas explain the model's decisions, not just its outputs.** The shared base owns this rule (see Category 6).
- **All three personas inherit the banned-word list and the three-metric cap.** The overlay can add to the banned list but cannot remove from it.
- **All three personas run through the same executive summary, data audit, anchor check, hallucination guard, and revision loop.** Persona affects ONLY the writer agent's system prompt and (for the generic persona) the hallucination-guard pre-processing step.

---

## Category 4: CLI & UX Affordances

### Table Stakes

- **`--persona {scout,analyst,generic}`** flag on `pitcher-narratives`. Default is `scout`. Invalid values produce an error that names the three valid choices plus the output of `--list-personas`.
- **Default is scout and existing scripts keep working.** No persona = scout persona. The CLI default value is not a hardcoded string; it reads from a `DEFAULT_PERSONA_ID = "scout"` module constant in `personas.py`.
- **`--list-personas`** — prints each persona's id, display name, and one-line description, then exits 0. No LLM call. Reads from the registry. Used by docs and by users who forgot the flag values.
- **`--print-prompts` includes the composed writer prompt for the selected persona.** The existing `--print-prompts` flow already dumps every phase's system prompt via `write_pipeline_data_file`. The writer section must use the composed prompt for the selected persona so operators can see exactly what the model will receive.
- **Provider + persona are independent.** `--persona analyst --provider claude` is valid. All 3 personas × 3 providers = 9 configurations, all supported.
- **Report output still prefixes with `# Scouting Report\n`** regardless of persona. The CLI header is persona-agnostic so downstream tooling that greps for section markers doesn't break.
- **The persona id is logged to stderr in verbose mode.** `log.info("persona=%s", args.persona)` in the verbose summary so operators can tell at a glance which overlay produced which output.

### Differentiators

- **`--describe-persona <id>`** — prints the persona's full overlay prompt plus length target. Useful for explaining the system to new users, but `--print-prompts` already exposes this via the composed prompt dump. Defer.
- **`--compare` mode that runs two or three personas in one invocation and prints them side-by-side.** Genuinely useful for evaluating the persona system but it triples the LLM cost and the test surface. Defer — operators can script it with `for p in scout analyst generic; do pitcher-narratives --persona $p -p 592155; done`.
- **Persona alias: `--voice` as a synonym for `--persona`.** One-line change, some users will type `--voice` reflexively. Cheap to add later; not needed for v1.10.
- **Per-persona default length override on the CLI.** `--length short|medium|long`. Defer — each persona has a length target already and the CLI flag would need to reconcile with the overlay's written guidance.

### Anti-Features

- **`--custom-persona path/to/overlay.txt`** — loads a user-supplied overlay file. Rejected: breaks the quality gates, bypasses the registry, and invites the anchor check to fail on prompts no one tested.
- **Persona set via environment variable (`PITCHER_NARRATIVES_PERSONA`).** Rejected: scripts that assumed the default scout voice would silently change output if someone exported the env var in their shell. Flags are explicit and traceable; env defaults are invisible.
- **Interactive persona picker when no flag is given.** Rejected: v1.10 needs to be a pure superset of v1.9 behavior. Prompting breaks non-TTY scripts and `--help` pipelines.
- **Persona flag on `pitcher-ask` or `pitcher-scout`.** Rejected: milestone constraint. `pitcher-ask` and `pitcher-scout` are out of scope. Even if someone argues "analyst persona would be nice for ask", that's a v1.11 feature and needs a different design because the ask agent's output contract is different.
- **Per-persona output filename suffix on the `data-*.md` file written by `write_pipeline_data_file`.** Rejected for v1.10 — the filename already includes provider and mode; adding persona changes every integration that greps for the filename pattern. The persona is written into the file contents, not the name.

---

## Category 5: Testing & Golden Samples

### Table Stakes

- **Per-persona smoke test using `TestModel`.** For each of the three personas, run `generate_pipeline_streaming` under `PITCHER_NARRATIVES_TEST_MODEL=1` with a frozen pitcher fixture and assert the pipeline returns a non-empty narrative, that the composed writer prompt contains the persona overlay, and that `PipelineResult.narrative` is produced without raising.
- **Scout byte-identical regression test.** As described in 3a: `build_writer_prompt(PERSONAS["scout"]).strip() == _LEGACY_WRITER_PROMPT_SNAPSHOT.strip()`. This is the guarantee that scout users see zero behavior change. The snapshot constant is imported from a `tests/fixtures/personas/legacy_writer_prompt.txt` file so it's diff-visible.
- **Overlay composition test.** For each persona: assert `build_writer_prompt(p).startswith(_WRITER_BASE_PROMPT)` and `build_writer_prompt(p).endswith(p.overlay_prompt)`. Catches any future accidental reordering.
- **Base-prompt contract test.** Assert that `_WRITER_BASE_PROMPT` contains known substrings for: the KeySignals obligation, the directional-consistency rule, the "explain how the Pitching+ model works" rule, and the temporal-grounding rule. This is a canary — if someone removes one of these from the base, the test fails loudly.
- **Persona registry test.** Assert `set(PERSONAS.keys()) == {"scout", "analyst", "generic"}` and that every persona has a non-empty overlay, a display name, a length target, and a format mode. Catches import-time errors and partial additions.
- **Hallucination check tolerance for generic persona's summary table.** A test that feeds a synthetic generic-persona narrative with a complete `## Summary Table` section through `check_hallucinated_metrics` and asserts it returns clean. Implementation-wise this may require a pre-pass that strips Markdown table cells before regex scanning, or it may "just work" if the table cells use only `_KNOWN_METRICS`; the test is the forcing function.
- **Anchor check structural tolerance for generic persona.** A test that runs the anchor check over a synthetic generic-persona capsule (headings + table) against a matching synthesis and asserts the anchor returns clean. The anchor prompt doesn't know about sections yet — the test will tell us whether the prompt needs a note like "the capsule may contain section headings and a summary table; treat them as prose."
- **Generic persona section-set test.** Assert that the generic persona's overlay prompt text contains all six required section names (`## Stuff`, `## Location`, `## Run Value & Execution`, `## Trend`, `## Game Shape`, `## Summary Table`). Separately, a smoke test using `TestModel` can validate the overlay reaches the writer; actual section enforcement is deferred to golden samples.
- **CLI flag test.** Argparse-level test that `pitcher-narratives --persona bogus` exits non-zero with a message listing valid choices, and that `--persona analyst` sets `args.persona == "analyst"`. No LLM call needed.
- **`--list-personas` test.** Subprocess (or click-runner-style) test that asserts the output contains all three ids and exits 0.

### Differentiators

- **Golden-output regression samples per persona.** Commit three reference outputs (one per persona) generated against a frozen pitcher fixture and a fixed provider, and diff them in CI. Differentiator (not table stakes) because golden samples on LLM output are flaky — the diff is noise-prone even at temperature 0.7 — and a flaky CI is worse than no CI. Revisit once the persona system has stabilized, or add only for the scout persona (which is supposed to be byte-identical anyway).
- **Cross-persona shared-infrastructure test.** Run the same pitcher through all three personas and assert that the executive summary bullets are identical (they come from the shared `_EXECUTIVE_SUMMARY_PROMPT`, not from the writer). Nice correctness canary. Defer — the base-prompt contract test already covers the conceptual case.
- **Word-count enforcement test per persona.** Run `TestModel` (deterministic) output through the writer and assert `min_words ≤ word_count ≤ max_words`. `TestModel` output is too canned to exercise real length targets, so this test would only catch the most egregious drift. Defer.
- **Vocabulary-ban test per persona.** Assert that the banned-word list in each composed prompt is a superset of the scout banned-word list. Cheap but low value — the base-prompt contract test already owns the vocabulary lineage.

### Anti-Features

- **End-to-end LLM tests that actually call Anthropic/OpenAI/Gemini.** Rejected: cost, flakiness, rate limiting. Tests use `TestModel` only. Golden samples (if added) are regenerated manually, not in CI.
- **Property-based tests that fuzz the persona schema.** Rejected: three personas, no user-defined personas, zero fuzz value.
- **Persona-specific anchor warning categories.** Rejected: the existing five categories (MISSED_SIGNAL, UNSUPPORTED, DIRECTION_ERROR, OVERSTATED, UNDERWEIGHTED) are shared. Adding `GENERIC_STRUCTURE_VIOLATION` would proliferate anchor types that the anchor agent was never trained to emit and would require a separate revision prompt path. The anchor check stays persona-agnostic.
- **Snapshot tests of the full CLI output per persona.** Rejected: the output includes the LLM-generated narrative, which is non-deterministic even at the same seed for some providers. Snapshot the composed writer prompt, not the model output.

---

## Category 6: "Explain the Model" Delivery

This is the milestone's load-bearing editorial constraint: every persona must contextualize its findings by explaining how Pitching+ works (S+ = stuff-only physical characteristics, L+ = location given the stuff, P+ = combined grade) and WHY the pipeline reached the specific grades it did.

### Recommendation: Shared base-prompt rule, per-persona overlay controls depth

**Delivery mechanism:**
1. The shared `_WRITER_BASE_PROMPT` carries the rule in a new section titled "EXPLAIN THE MODEL." This section states: "Every plus-metric you cite must be accompanied, somewhere in the capsule, by (a) a one-phrase reminder of what the metric measures and (b) the pipeline's reason for the specific grade. The reason must come from the specialist analyses — do not speculate."
2. Each persona overlay modulates **depth**, not **presence**:
   - Scout overlay: "Explain the model tersely and only the first time a metric appears. One clause is enough. Example: 'the slider's S+ of 128, driven by the new vertical break'."
   - Analyst overlay: "Explain the model in full the first time each metric appears. A sentence is expected. Assume the reader is a literate fan but not a working analyst. The teaching is part of the value."
   - Generic overlay: "Explain the model once per section, at the start. The summary table columns do not need re-explaining. Example: 'S+ is the stuff-only grade from the physical characteristics of the pitch — for the slider, the pipeline credited 128, citing the new vertical break.'"
3. The anchor check gets a new warning category — NO. The anchor check does NOT get a new warning category. See "Why not structured output" below.

**Why shared base, not per-persona toggle:** The rule is a correctness / truth-in-labeling obligation, not a stylistic preference. Making it per-persona means someone could ship a persona that skips it, which defeats the whole point. The base owning the rule means the anchor check can (eventually) enforce it without knowing which persona is in play.

**Why not structured output:** A structured output type (e.g., `WriterResult = {capsule: str, model_explanation: str}`) would guarantee the explanation is present but would also fragment the narrative voice — readers would see the explanation as a separate block, which is the opposite of how the scout persona wants it delivered (inline, one clause). Keeping the rule in free prose lets each persona deliver the explanation in its own voice.

**Why not add an anchor warning category for "explanation missing":** The anchor check operates on "is this capsule faithful to the synthesis." Adding an editorial obligation (did the writer teach the model) to the anchor agent conflates fact-checking with style enforcement. An editorial check for explanation presence is a future concern (v1.11?) and would belong in a new agent, not inside the anchor.

**Testing this rule in v1.10:** The base-prompt contract test (Category 5) asserts the "EXPLAIN THE MODEL" section is present in the composed prompt for every persona. That's the full test surface for v1.10. Validation that the writer actually follows the rule is a manual golden-sample review during the v1.10 milestone, not an automated test.

### Table Stakes (for this category)

- **The "EXPLAIN THE MODEL" rule lives in the shared base prompt and applies to all three personas.**
- **Each persona overlay states its depth expectation (terse / full / once-per-section).**
- **The base-prompt contract test asserts the rule is present in every composed prompt.**
- **No structured output type is introduced for the explanation — it is prose-integrated per persona.**
- **No new anchor warning category is introduced for explanation presence.**
- **A manual golden-sample review during milestone execution confirms that each persona's output actually explains the model at its declared depth.** This is a human validation step, not an automated test, and the milestone plan should allocate time for it.

### Differentiators

- **A separate "editorial check" agent (sibling to the anchor check) that validates the writer explained the model.** Deferred to v1.11 or later. Worth exploring once the persona system proves stable, but adds a third verification agent to the pipeline and a fourth regex-heavy test file. Not v1.10.
- **Machine-readable markers in the capsule (e.g. invisible `<!-- EXPLAINED: S+ -->` HTML comments) that a post-processor can validate.** Too clever. Fails the "would a human scout write this" smell test.

### Anti-Features

- **Per-persona toggle for the explanation rule.** Rejected: a persona that opts out of explaining the model is not a persona we want to ship.
- **Splitting the explanation into its own CLI section (like Executive Summary).** Rejected: the rule is specifically about inline contextualization. Pulling the explanation out of the narrative defeats the purpose.

---

## Requirements Mapping Hint

Each table-stakes bullet above is intended to map to one REQ line in the requirements-definition step. Expected REQ count from this document: roughly 40–48 lines across the six categories, weighted toward Category 3 (voice differentiation has the most concrete sub-requirements) and Category 5 (testing has the most independently verifiable line items). Anti-features should map to "Out of Scope" lines in PROJECT.md, not REQs.

## Sources & Confidence

- **HIGH confidence — codebase-grounded:**
  - `src/pitcher_narratives/pipeline.py` (`_WRITER_PROMPT` constant, lines 408–477; `make_pipeline_agents`, lines 1112–1162; `write_pipeline_data_file`, lines 1030–1067; `check_hallucinated_metrics`, lines 1566–1606; metric allow-list, lines 1453–1525)
  - `src/pitcher_narratives/anchor.py` (full file — `ANCHOR_PROMPT`, `AnchorWarning`, `WarningCategory`)
  - `src/pitcher_narratives/signals.py` (full file — `KeySignals`, `SIGNAL_EXTRACTOR_PROMPT`)
  - `src/pitcher_narratives/cli.py` (full file — argparse surface, `--print-prompts` flow, output section ordering)
  - `.planning/PROJECT.md` (v1.10 milestone section, constraints, validated requirements history)
- **MEDIUM confidence — training data for sports-analytics writing voices:**
  - Baseball Prospectus feature-article voice (training data, not live-fetched in this session; WebSearch was not available)
  - Pitcher List analytical-article voice (training data)
  - FanGraphs community research voice (training data)
  - Effectively Wild show-notes voice (training data)
  - Default-LLM sectioned response format (training data, universal pattern)
  - Front-office internal scouting report layout (training data, no public exemplars referenced)
  - Confidence caveat: the voice-target descriptions are defensible but should be sanity-checked against 1–2 real articles from each source during milestone execution. Flag this as a golden-sample review task.
- **LOW confidence — none.** All claims are either codebase-verifiable or are editorial recommendations grounded in well-known sports-writing conventions.
