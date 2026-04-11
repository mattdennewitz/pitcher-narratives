# v1.10 Output Personas — Pitfalls

**Domain:** Adding a persona/voice overlay system to an existing LLM-writer pipeline with a shared anchor check, per-specialist audit, hallucination guard, and revision loop.
**Researched:** 2026-04-11
**Confidence:** HIGH on code-grounded claims (verified against `pipeline.py`, `anchor.py`, `signals.py`, `config.py`). MEDIUM–LOW on cross-product persona-system patterns (web search was unavailable; those items are flagged inline).

**How to read this file.** Every pitfall is: **Failure mode → Prevention → Verification → Phase owner.** Nothing vague. Every verification is a runnable command, a named test, or a file-level assertion. The "Phase owner" column names which v1.10 phase should actually own the fix.

Assumed v1.10 phase structure (from the milestone doc):

- **P1 persona module** — new `personas.py` defining overlays, registry, prompt composer.
- **P2 pipeline integration** — `pipeline.py` wired to accept a `persona` parameter and build writer prompts from base + overlay.
- **P3 CLI surface** — `--persona {scout,analyst,generic}` on `pitcher-narratives`, help text, errors.
- **P4 per-persona build-out** — the three overlay prompts themselves, hallucination allowlist updates, token budgets.
- **P5 test + hardening** — goldens, shape assertions, scout regression, streaming, cache verification.

---

## Critical Pitfalls

### Pitfall 1: Voice bleed between personas

**Failure mode.** The shared base prompt in P4 contains scout-flavored phrasing from the existing `_WRITER_PROMPT` ("find the thread", "finding a groove", "getting tagged", the entire VOICE block with the five banned words). The analyst overlay adds newsletter instructions on top, but the base is loud enough that the analyst output sounds like a scout who learned to use bullet callouts. Conversely, once the analyst overlay normalises the phrase "model says," the scout persona starts echoing it on the next run because the base prompt was edited during development to accommodate the analyst. Bleed is bidirectional: base → overlay (analyst sounds scouty) and overlay → base (scout picks up analyst idioms during iteration).

**Root cause.** The existing `_WRITER_PROMPT` at `pipeline.py:408` mixes three concerns in one string: (a) analytical contract ("use Key Signals", "directional consistency", "temporal grounding"), (b) voice ("scouting language: stuff, feel…"), (c) structure ("2-3 paragraph", "no bullets, no headers, no tables"). When that string becomes the shared base, every voice-y line leaks into every persona.

**Prevention (code-level).** Split `_WRITER_PROMPT` into two strict slices before composing:

- `_WRITER_BASE_PROMPT` — contract only. Analytical rules, directional consistency, temporal grounding, Key Signals contract, model-explainer requirement, hallucination warning against traditional outcome stats. **Zero voice words. Zero structure words.**
- `_SCOUT_OVERLAY` / `_ANALYST_OVERLAY` / `_GENERIC_OVERLAY` — voice words + structure rules + length target. Each overlay owns its banned-word list.

The composer in `personas.py` concatenates `base + "\n\n" + overlay`, and the scout overlay is the ONLY place where "stuff, feel, finding a groove" lives.

**Verification.**

1. `tests/test_personas.py::test_base_prompt_has_no_voice_words` — literal-string assertion: `for word in ("stuff", "feel", "groove", "tagged", "elite", "massive"): assert word not in _WRITER_BASE_PROMPT.lower()`.
2. `tests/test_personas.py::test_scout_overlay_owns_banned_words` — assert the "Never use: 'degradation', 'binary', 'profiles as', 'dominant', 'elite', 'massive spike'" line appears in the scout overlay and NOT in the base.
3. Manual smoke (P5): `uv run pitcher-narratives --persona analyst -p 657277 -w 10` and grep the output for the scout vocabulary list. Zero hits.

**Phase owner.** P1 (split) + P4 (overlays).

---

### Pitfall 2: Overlay-overrides-base constraint drift (hallucination-guard false negative)

**Failure mode.** The analyst overlay says things like "tell the reader *why* the model is interested in this pitcher — mention the story the numbers are telling." The model interprets "story" as permission to cite narrative baseball context, and writes a sentence like *"His 3.42 ERA on the season is hiding a Stuff+ surge in the last three starts."* The base rule from `_WRITER_PROMPT:462` ("use ONLY data from the specialist analyses") is silently overridden. Worse: `_TRADITIONAL_PATTERN` at `pipeline.py:1546` will catch `ERA` in that sentence (it's bounded by space on the left, space on the right). Good. **But** if the analyst writes `3.42-ERA` (hyphenated), the negative lookbehind `(?<![A-Za-z\-])` excludes matches preceded by a hyphen, so `-ERA` is a false negative and the guard misses it. Same hole for `3.42/ERA`, `(ERA 3.42)` where the opening paren is fine but `ERA)` matches the closing lookahead — actually that matches, so that one is safe.

**Second failure mode.** The generic persona's summary table has a row `| ERA | Not used by this report |`. That's a legitimate disclaimer but the regex catches the literal `ERA` token and flags it. The CLI surfaces an outcome-stat warning on a persona whose explicit design is to disclaim those stats. Users lose trust in the guard and start ignoring its warnings.

**Prevention.**

1. **Tighten the hyphen exclusion.** In `_TRADITIONAL_PATTERN`, `(?<![A-Za-z\-])` excludes `-` because legitimate constructs like `non-ERA` should not match. But it also hides `3.42-ERA` which IS a match. Replace with `(?<![A-Za-z])` (drop hyphen exclusion) and add a separate safelist for known compound prefixes (`non-`, `pre-`) if false positives appear. Document the trade-off in a comment.
2. **Add a "disclaimer context" carve-out for the generic persona.** The generic overlay must instruct the model to put any traditional-stat disclaimer INSIDE a sentinel block: `DISCLAIMER_BEGIN ... DISCLAIMER_END`. The hallucination guard's `check_hallucinated_metrics` gets an optional `strip_disclaimers: bool = False` parameter (default off for scout/analyst). The generic-persona caller in `pipeline.py` invokes it as `check_hallucinated_metrics(capsule, strip_disclaimers=True)` which regex-deletes any `DISCLAIMER_BEGIN...DISCLAIMER_END` block before scanning.
3. **Base prompt must explicitly invalidate "story" interpretations.** Add a sentence to `_WRITER_BASE_PROMPT`: *"'Story' means the thread across the specialist analyses, not baseball context from outside the data. Traditional outcome stats (ERA, FIP, WHIP, WAR, W-L, K/9, BB/9) are NEVER cited as analysis, only as explicit disclaimers in the format a persona overlay allows."*

**Verification.**

1. `tests/test_hallucination_guard.py::test_hyphenated_era_is_caught` — `assert "ERA" in check_hallucinated_metrics("his 3.42-ERA season").outcome_stat_warnings`.
2. `tests/test_hallucination_guard.py::test_strip_disclaimers_flag_removes_generic_table` — feeds a fake generic capsule containing `DISCLAIMER_BEGIN\n| ERA | not used |\nDISCLAIMER_END` and asserts the report is clean.
3. `tests/test_hallucination_guard.py::test_strip_disclaimers_default_still_catches_era` — same input but default flag, asserts ERA IS flagged (defends against accidentally flipping the default).
4. Manual: `uv run pitcher-narratives --persona analyst -p 657277 -w 10` and verify the capsule contains zero traditional-stat warnings on stderr.

**Phase owner.** P4 (regex hardening, disclaimer sentinel in generic overlay, base-prompt language) + P5 (tests).

---

### Pitfall 3: Anchor-check brittleness against structural variation

**Failure mode.** `ANCHOR_PROMPT` at `anchor.py:26` was written for "the editor's finished narrative (the capsule)" — it assumes prose paragraphs. Three concrete breaks for the generic persona:

- **UNSUPPORTED over-fire on summary table cells.** The generic persona emits a row like `| Slider xRV100 | -1.8 | IMPROVED |`. The anchor agent reads `IMPROVED` as a capsule claim and looks for it verbatim in the synthesis. The synthesis says "Slider xRV100 dropped from -0.2 to -1.8 (improvement)" — different token. The anchor flags `IMPROVED` as UNSUPPORTED. False positive, revision loop runs, writer tries to fix a non-issue and sometimes damages the table.
- **MISSED_SIGNAL under-fire on sectioned output.** The generic persona has labeled sections like `## Stuff` / `## Location` / `## Verdict`. The anchor agent reads them as independent subdocuments and checks each one against the synthesis. A primary signal (Top Improvement) mentioned once in the Verdict section is enough for the agent to call it "covered," even if the Stuff section was the right place for it. Conversely, if Top Improvement is in the Stuff section and the Verdict doesn't restate it, the anchor reads the Verdict as incomplete and flags MISSED_SIGNAL. Anchor inconsistency is a function of section layout, not fidelity.
- **Summary table encourages row invention.** Writers asked for "a summary table with the key metrics" reliably pad rows to reach a visual target (~5 rows). If the specialists only gave 3 data points worth citing, the writer invents 2 more. The hallucination guard catches invented metric NAMES, but not invented ROWS whose values are slightly-wrong paraphrases of real specialist numbers.

**Prevention.**

1. **Anchor prompt gets a structural tolerance amendment for table-bearing personas.** Add a branch to `build_anchor_message` that accepts an optional `persona_hints: dict | None` parameter. For the generic persona, prepend: *"The capsule may contain a markdown table. Treat table cells as the author's structured restatement of synthesis findings — cell contents should align in DIRECTION and IDENTITY with the synthesis, but exact wording (e.g. 'IMPROVED' vs 'dropped') is acceptable. A row is UNSUPPORTED only if the specialist analyses do not mention that metric at all."*
2. **Cap generic persona table at N rows tied to real specialist findings.** The generic overlay must say: *"The summary table has EXACTLY one row per populated Key Signal (top_improvement, top_concern, plus any secondary signal the narrative uses). Do not add rows for stylistic completeness."* This makes N deterministic from the `KeySignals` object the writer already receives.
3. **Anchor agent reads the whole capsule as one document, not section-by-section.** Since `anchor.py` already feeds the capsule as a single string, the concern is that the anchor *model* self-segments. Add a sentence to the anchor prompt: *"Read the capsule as a single document. Headers and sections are structural scaffolding, not independent contexts. A signal cited anywhere in the capsule counts as addressed."*

**Verification.**

1. `tests/test_anchor.py::test_anchor_prompt_mentions_table_tolerance_for_generic` — once the persona-aware `build_anchor_message` is added, assert the generic branch includes the "DIRECTION and IDENTITY" language.
2. `tests/test_pipeline.py::test_generic_persona_table_row_count_matches_key_signals` — run pipeline with `TestModel` fixtures that emit a KeySignals with 1 top_improvement + 1 top_concern + 1 secondary, and assert the generic capsule's table has exactly 3 rows (regex: `capsule.count("\n|") - header_rows`).
3. Manual: `uv run pitcher-narratives --persona generic -p 657277 -w 10` — inspect stderr for `[UNSUPPORTED]` warnings on table cells. Zero tolerated.
4. Ratio check in P5: run the pipeline 5 times across all three personas with fixed seed/model; count revision passes per persona. If `generic` averages more than `scout + 0.5` revisions, structural brittleness is the cause and the anchor prompt needs further tuning.

**Phase owner.** P2 (anchor plumbing) + P4 (overlay row-count rule) + P5 (tests, smoke).

---

### Pitfall 4: Revision-loop instability per persona

**Failure mode.** `build_revision_message` in `anchor.py:88` ends with: *"Preserve the voice, structure, and all unflagged material. Do not add new analysis or metrics not in the briefing."* This prompt is **persona-agnostic** — the revising writer agent already has the persona overlay baked into its system prompt, so in theory "preserve the voice" means "preserve whatever voice my system prompt tells me." In practice, three drifts occur:

- The revision prompt appears in the user message slot. The writer's system prompt (with overlay) is stable, but the revision user message overwhelms the overlay because it's close to the decoder in context. The writer reverts to a neutral-LLM voice ("The slider's xRV100 of -1.8 indicates above-average run prevention"), which is scout-ish regardless of the persona set.
- The newsletter persona includes inline callouts (`> **Why this matters:** ...`). Revision-pass writers strip callouts because the warning says "fix the flagged claim" and the callout isn't flagged, but it's also not load-bearing to the claim, so it feels safe to cut. Second revision pass loses the callout entirely. Voice degrades.
- The generic persona's table rows are emitted as markdown. On a revision pass flagging a prose claim, the writer rebuilds the prose and accidentally drops or re-orders the table. Anchor passes clean on pass 2 but the table is now inconsistent with the prose.

**Prevention.**

1. **Make `build_revision_message` persona-aware.** Signature change: `build_revision_message(synthesis, capsule, warnings, persona_id: str)`. For each persona, the final instruction is explicit:
   - `scout`: "Preserve the 2-3 paragraph prose structure and scout voice."
   - `analyst`: "Preserve the newsletter structure including any `> **Why this matters:**` callouts and inline aside formatting."
   - `generic`: "Preserve the section headings and the summary table — both the row set and the row order must remain identical unless a flagged claim explicitly targets a table row."
2. **Add a structural diff assertion inside the revision loop.** After each writer revision, before the next anchor check, call a cheap `_structural_invariant_check(capsule_before, capsule_after, persona)` that compares: header count, bullet count, table row count (if applicable). If any diverge in a non-flagged way, log a warning and keep the previous capsule. Implementation is 20 lines of string parsing.
3. **Cap revisions per persona.** `MAX_REVISIONS = 3` is fine for scout, but overlay richness scales revision risk. Config change: `MAX_REVISIONS_PER_PERSONA = {"scout": 3, "analyst": 2, "generic": 2}`. Rationale: fewer revisions = less structural rot for overlay-heavy personas; trade-off is slightly more surviving anchor warnings on edge cases, which is the correct trade — a surfaced warning is less bad than a silently broken table.

**Verification.**

1. `tests/test_anchor.py::test_revision_message_mentions_callouts_for_analyst` — assert `build_revision_message(synth, caps, warns, persona_id="analyst")` contains the substring "Why this matters".
2. `tests/test_pipeline.py::test_revision_loop_preserves_table_row_count` — use `TestModel` to simulate anchor returning one MISSED_SIGNAL warning for a generic capsule with a 3-row table; fake a revision that drops a row; assert `_structural_invariant_check` rejects the revision.
3. `tests/test_pipeline.py::test_max_revisions_per_persona_respected` — assert the loop stops at 2 revisions for analyst and generic.
4. Manual: run `uv run pitcher-narratives --persona analyst -p 657277 -w 10 --verbose` and visually confirm callouts survive any revision pass reported in stderr.

**Phase owner.** P2 (revision-loop plumbing, invariant check) + P4 (per-persona phrasing) + P5 (tests).

---

### Pitfall 5: Hallucination guard false positives on persona-specific vocabulary

**Failure mode.** Two directions:

- **Analyst vocabulary looks metric-ish.** Newsletter writers use phrases like `playability`, `pitch tree`, `tunneling gap`, `arsenal depth score`, `usage share`. Most are safe because they don't match `_METRIC_PATTERN`. But `K/BB ratio`, `SwSt%` (already allowed), and invented analyst shorthand like `WhiffShare%` or `StuffGap+` would match the `[A-Z][A-Za-z]*-?[A-Z]*%` or `[PSL]\+(?:2080)?` branches and get flagged as unknown. If the analyst persona ships with instructions to use "playability," the model sometimes generates `Playability%` as a variant, which trips `Acronym+%` and is flagged.
- **Generic persona disclaimer block.** Already covered under Pitfall 2 (`DISCLAIMER_BEGIN/END` sentinel + `strip_disclaimers=True` flag). Listed here for completeness.

**Prevention.**

1. **Per-persona allowlist extension.** `HallucinationReport` gains a `persona: str | None = None` parameter on `check_hallucinated_metrics`. A new `_PERSONA_KNOWN_METRICS` dict maps each persona to its additional safe terms:
   - `scout`: `{}` — default `_KNOWN_METRICS` only (preserves v1.9 behavior exactly).
   - `analyst`: `{"playability", "tunneling gap", "pitch tree", "arsenal depth"}` — added as whole-phrase string checks, not regex. These are safe because `_METRIC_PATTERN` is anchored to token shapes, not English phrases.
   - `generic`: `{}` — relies on disclaimer stripping, not allowlist.
2. **Ban invented compounds at the overlay level.** Analyst overlay rule: *"Do not invent compound metrics. If you want to describe a concept, use English prose, not a new acronym. Allowed prose terms: playability, tunneling, pitch tree, arsenal depth."* This keeps the overlay honest about which vocabulary the allowlist covers.
3. **Scout persona allowlist must be byte-identical to v1.9.** Covered by Pitfall 9's regression harness.

**Verification.**

1. `tests/test_hallucination_guard.py::test_analyst_playability_not_flagged` — `check_hallucinated_metrics("His curveball has real playability now.", persona="analyst").is_clean == True`.
2. `tests/test_hallucination_guard.py::test_scout_playability_still_clean_because_token_shape` — same input with `persona="scout"`, still clean (the word "playability" doesn't match any regex branch). This test exists to catch future regex changes that might start matching English words.
3. `tests/test_hallucination_guard.py::test_invented_compound_stuffgapplus_flagged` — `StuffGap+` IS flagged as unknown under all personas.

**Phase owner.** P4 (allowlist extension, overlay rule) + P5 (tests).

---

### Pitfall 6: Streaming UX regression — markdown tables streaming character-by-character

**Failure mode.** `pipeline.py:1346` streams the writer output via `run_stream` and prints each delta with `print(delta, end="", flush=True)`. For scout (prose), this is fine. For generic (emits a markdown table), the user sees:

```
| Pitch Ty
pe | Sample | Tren
d |
| ---
| ---
| ---
```

Terminal auto-wrap makes it worse: a table whose rendered width exceeds the terminal gets chopped mid-cell because the LLM's token stream hits newlines before the row closes. Users report the output looks broken; some terminals (especially iTerm2 with ligatures) misrender the partial `| ---` as a divider and then fail to re-render when the rest arrives. Confidence: MEDIUM — based on general terminal-streaming knowledge, not verified against a specific terminal.

**Prevention.** Three-tier strategy by persona:

1. **Scout persona:** keep current `print(delta, ...)` behavior. No change. Byte-identical to v1.9.
2. **Analyst persona:** line-buffered flush. Accumulate deltas until a newline is seen, then print the full line. Callouts (`> **Why this matters:**`) look stable; prose paragraphs still feel live because paragraph breaks are relatively frequent. Trade-off: first-byte latency increases from ~200ms to ~800ms.
3. **Generic persona:** hybrid — stream the prose sections delta-by-delta, but when a `|` character is seen at the start of a line, switch to full-document buffering for the rest of the table (detected by a closing blank line or EOF). Before buffering, print a placeholder: `\n[summary table generating...]\n`. When the buffer is complete, overwrite the placeholder with an ANSI cursor-up + clear-line sequence and print the rendered table.

Implementation hook: refactor the streaming loop in `_run_pipeline` around line 1346 into a `_stream_writer_output(stream, persona: str)` helper that owns the buffering strategy.

**Verification.**

1. `tests/test_pipeline.py::test_scout_stream_prints_each_delta` — using a fake stream that yields known chunks, assert that print was called once per chunk for scout.
2. `tests/test_pipeline.py::test_analyst_stream_flushes_on_newline` — assert `print` is called only on newline boundaries.
3. `tests/test_pipeline.py::test_generic_stream_buffers_table_region` — assert the table region is emitted as a single `print` call after the closing blank line of the table.
4. Manual: `uv run pitcher-narratives --persona generic -p 657277 -w 10 | tee /tmp/generic.out` in a narrow terminal (80 cols) and a wide terminal (200 cols). Table must render correctly in both; no `|` chars mid-stream.

**Phase owner.** P2 (streaming helper refactor) + P4 (per-persona buffering config) + P5 (manual terminal checks).

---

### Pitfall 7: Token-budget blowout on longer personas

**Failure mode.** `config.py:53` sets `TOKEN_BUDGET_LARGE = 4096`. Scout persona's current output is ~400-700 output tokens (2-3 paragraphs). The analyst newsletter persona targets 1500-2500 tokens (intro + sections + callouts + conclusion). The generic persona targets 1000-1800 tokens (sections + summary table + verdict). Both are within 4096 in the happy path, but:

- With Claude Sonnet 4.6 thinking enabled, thinking tokens count against `max_tokens` on some providers. `make_model_settings` at `config.py:66` has complex branches: Gemini uses `google_thinking_config`, Claude with `max_tokens <= TOKEN_BUDGET_MEDIUM (2048)` disables thinking, OpenAI with `max_tokens > TOKEN_BUDGET_MEDIUM` passes `max_tokens` through. The writer currently runs at 4096 with thinking `high` — an analyst persona targeting 2500 output tokens + 1000 thinking tokens is at the cliff.
- Revision passes compound the risk: on revision, the writer receives the prior capsule AS INPUT in the user message (via `build_revision_message`), which increases its effective context window consumption, and is asked to output a similar-length capsule again. Analyst persona at 2500 output × 3 revision passes = 7500 total output tokens across the loop. Not a single-call blowout, but a cumulative latency and cost hit.

**Prevention.**

1. **Per-persona token budget, keyed by persona id.** New constant in `config.py`:
   ```
   PERSONA_TOKEN_BUDGETS = {"scout": 4096, "analyst": 6144, "generic": 5120}
   ```
   `make_pipeline_agents` in `pipeline.py:1112` takes a `persona_id` argument and passes `max_tokens=PERSONA_TOKEN_BUDGETS[persona_id]` to the writer's `make_model_settings`. Executive summary, specialists, anchor, auditor keep their existing budgets unchanged — they're persona-agnostic.
2. **Hard length cap in the overlay prompt, not just a "target."** Each overlay ends with: *"Hard limit: analyst target is 2500 words — if you approach 2000 words, wrap up."* Prevents runaway generation that would crash `max_tokens`.
3. **Add a budget-exhausted detector.** After streaming, compare `len(capsule.split())` against the persona's soft limit. If exceeded by more than 20%, log a warning. Cheap sanity check, no user-visible impact in the happy path.

**Verification.**

1. `tests/test_config.py::test_persona_token_budgets_keyed_for_all_personas` — assert all three persona ids are present.
2. `tests/test_pipeline.py::test_writer_settings_use_persona_budget` — fake `make_model_settings` with a spy, run pipeline with `persona="analyst"`, assert the writer got `max_tokens=6144`.
3. Manual: `uv run pitcher-narratives --persona analyst -p 657277 -w 10 --verbose 2>&1 | grep -i "truncat\|length"` — zero truncation warnings.
4. Cost sanity check: run all three personas on the same pitcher with `--verbose` logging the token usage. Analyst + generic must be within 2.5× scout's total token cost. If >3×, cost profile is unhealthy.

**Phase owner.** P2 (pipeline integration wires budgets) + P4 (overlay length caps) + P5 (detector, smoke).

---

### Pitfall 8: Prompt-cache invalidation on persona selection

**Failure mode.** The shared base prompt is stable across personas. Overlays differ per persona. If the persona system naively concatenates `base + overlay` into the system_prompt of the writer agent, the Anthropic/Google prompt cache sees the full concatenation as one unit, and any overlay change invalidates the cache. In practice: running scout then analyst back-to-back recomputes the base prompt from scratch for the analyst call, missing the cache benefit that `CachePoint` was supposed to provide. The CachePoints in `_build_stuff_input` and `build_anchor_message` are NOT affected — they're on specialist/anchor user messages — but the writer's system prompt is the big one, and it's the one that invalidates.

`anchor.py:80` puts a `CachePoint()` AFTER the synthesis in the user message, which is stable per pitcher but not per persona because the anchor agent runs on every persona and the capsule that follows is persona-specific. The synthesis prefix is still cacheable across revision passes of the SAME persona run, so that's fine. But the writer's system prompt has no CachePoint at all.

**Prevention.**

1. **Move the base prompt into the writer's system_prompt as a stable prefix, and put the overlay in the USER message with a `CachePoint()` breakpoint between synthesis and overlay.** Concretely:
   - Writer agent system_prompt = `_WRITER_BASE_PROMPT` only (stable across personas, caches forever).
   - Writer user message = `[specialist_synthesis, CachePoint(), persona_overlay_instructions, "Compose the capsule."]`.
   - The synthesis prefix caches ACROSS both same-persona revisions AND across-persona comparison runs on the same pitcher. Cache hit on base prompt is free; cache hit on synthesis+cachepoint is the bulk win.
2. **If pydantic-ai's Agent API requires the system_prompt to hold the overlay (because overlays define output shape), alternative: split the writer into three agents.** `writer_scout`, `writer_analyst`, `writer_generic` are three `Agent` instances, each with its own system_prompt (base + its overlay). Each agent caches its own system_prompt independently. Users don't cross-persona often, so the cost of three agents is minimal. Less elegant than single-agent overlay routing, but works around API constraints.
3. **Do NOT place `CachePoint()` inside the system_prompt construction.** That's the mistake the question calls out: any template change anywhere before the cache point invalidates the cache. Keep cache boundaries in USER messages only, and keep system prompts as literal string constants.

**Verification.** Confidence: LOW on specific verification — prompt-cache introspection varies by provider.

1. `tests/test_personas.py::test_writer_base_prompt_is_literal_constant` — assert `_WRITER_BASE_PROMPT` is a module-level string constant, not constructed at runtime. Catches future refactors that accidentally f-string the base prompt.
2. `tests/test_personas.py::test_overlay_lives_in_user_message_not_system_prompt` — inspect the pipeline's writer call path and assert the overlay text appears in the user-message builder, not in the Agent constructor. Implementation: grep the writer input builder for known overlay substrings.
3. Manual, provider-dependent: Anthropic SDK exposes `cache_creation_input_tokens` and `cache_read_input_tokens` on usage. Run scout then analyst back-to-back on the same pitcher, capture usage, verify `cache_read_input_tokens > 0` on the analyst call (indicating the base prompt cached across personas). LOW confidence on exact API shape — needs validation when wiring up.

**Phase owner.** P2 (prompt composition architecture, cache-point placement) + P5 (tests + manual cache validation).

---

### Pitfall 9: Scout-persona regression

**Failure mode.** Milestone constraint says scout must be "byte-identical-ish" — users who never pass `--persona` see no change. But the moment you introduce a shared base + empty-overlay composition, the writer's system_prompt becomes `_WRITER_BASE_PROMPT + "\n\n" + _SCOUT_OVERLAY` instead of the literal `_WRITER_PROMPT` constant. Even if the concatenation is intended to equal the old string, whitespace, trailing newlines, or the accidental inclusion of a section that used to be one blob creates a different hash. LLMs are sensitive to prompt formatting — an extra blank line can shift token boundaries and produce materially different output.

The tempting verification "run it and eyeball it" doesn't scale and is not reproducible. Golden-output comparison is also fragile because LLM sampling has variance even at temperature 0.7.

**Prevention — layered.**

1. **Prompt-level byte-identical assertion.** The v1.9 `_WRITER_PROMPT` string is frozen as `_SCOUT_EXPECTED_PROMPT` in a new `tests/test_scout_regression.py` file. The v1.10 composer `compose_writer_system_prompt("scout")` must return a string equal to `_SCOUT_EXPECTED_PROMPT` byte-for-byte. This is the tightest possible guarantee: if the composed prompt matches the old one character-for-character, the LLM sees the same input and (modulo sampling noise on the non-deterministic writer temperature 0.7) produces statistically similar output.
2. **Structural output assertion with `TestModel`.** `tests/test_pipeline.py::test_scout_pipeline_output_shape` already exists for v1.9 behavior (or add it). With `TestModel`-injected writer, assert the output is a single prose blob: no `|` characters (no table), no `##` headers, at most 4 blank lines (paragraph separators), 100-800 words.
3. **Sampling-robust golden on a single fixed pitcher.** Create `tests/fixtures/scout_golden_657277_w10.txt` — NOT an exact text match, but a hashable set of shape invariants: `{"word_count_range": (200, 700), "has_headers": False, "has_tables": False, "mentions_metric_count": >=2, "starts_with_capital": True}`. Run `uv run pitcher-narratives --persona scout -p 657277 -w 10` in CI (guarded by a `--real-llm` flag) and assert the shape invariants hold. Confidence: MEDIUM — CI cost may block this; maybe run weekly rather than per-commit.
4. **Diff-on-upgrade convention.** When `_WRITER_BASE_PROMPT` or `_SCOUT_OVERLAY` is edited, the edit author MUST update `_SCOUT_EXPECTED_PROMPT` in the same commit. Reviewer asserts the diff is intentional.

**Verification.**

1. `tests/test_scout_regression.py::test_scout_composed_prompt_is_byte_identical_to_v19_writer_prompt` — string equality assertion.
2. `tests/test_pipeline.py::test_scout_output_shape_with_test_model` — structural shape assertions.
3. Manual, optional: `uv run pitcher-narratives -p 657277 -w 10` (no persona flag) and `uv run pitcher-narratives --persona scout -p 657277 -w 10` — the two invocations should route to the same code path. Instrument both with `--verbose` and confirm the writer system prompts in the output are identical.

**Phase owner.** P1 (composer returns identical string) + P5 (regression test suite).

---

### Pitfall 10: Golden-sample rot vs shape assertions

**Failure mode.** "Golden outputs" (fixture files of expected LLM text) break on every model upgrade, every prompt tweak, every temperature-adjacent change. For three personas, three goldens × N pitchers = a constant treadmill of rebaselining. Worse: rebaselining hides regressions, because once a developer regenerates the golden after a prompt change, any quality drop in the new output becomes invisible.

Conversely, "skip goldens, trust prompt changes in review" means zero safety net — a subtle overlay bug that makes the analyst persona emit scout-style paragraphs ships silently.

**Prevention — shape assertions, not text matches.** Defensible hybrid:

1. **Per-persona shape assertion helpers** in `tests/persona_shapes.py`:
   - `assert_scout_shape(text)` — prose only, 200-700 words, no markdown tables, no headers, no bullet lists with `-` or `*`, no `##` markers.
   - `assert_analyst_shape(text)` — 1000-3000 words, has at least one `> **Why this matters:**` callout, optional `##` section headers, mentions at least 3 known metrics from `_KNOWN_METRICS`.
   - `assert_generic_shape(text)` — 800-2000 words, contains exactly one markdown table with a row count matching the number of populated Key Signals, has 2-4 `##` section headers, has a final "Verdict" section.
2. **Snapshot the SHAPE, not the TEXT.** A golden file is a JSON dict of shape properties, not a text blob: `{"word_count": 847, "callout_count": 2, "section_count": 4, "metrics_cited": ["S+", "xRV100", "CSW%"]}`. On each run, extract shape properties from the capsule and compare dict-to-dict with tolerance ranges. Rebaselining is explicit and meaningful — "this persona's output got longer" is a conversation, not a silent regen.
3. **One small real-LLM smoke test per persona**, gated behind `RUN_LIVE_LLM=1`, not run in default CI. Produces the shape JSON and asserts invariants. Cheap (one pitcher × three personas × one real call each).

**Verification.**

1. `tests/test_persona_shapes.py::test_scout_shape_helper_rejects_markdown_table` — synthetic capsule containing `| a | b |` fails `assert_scout_shape`.
2. `tests/test_persona_shapes.py::test_generic_shape_helper_requires_table` — synthetic capsule without a `|` fails `assert_generic_shape`.
3. `tests/test_persona_shapes.py::test_analyst_shape_helper_requires_callout` — synthetic capsule without `> **Why this matters:**` fails `assert_analyst_shape`.
4. CI-gated: `RUN_LIVE_LLM=1 uv run pytest tests/test_live_personas.py` — three real calls, three shape assertions. Not run per-commit.

**Phase owner.** P5 (shape helpers, gated live test).

---

### Pitfall 11: User confusion across personas

**Failure mode.** `--persona generic` emits a ChatGPT-like sectioned block with a table. `--persona scout` emits a 2-paragraph scout blurb. A user who doesn't read `--help` runs `--persona generic` expecting "generic = safe default, won't surprise me" and gets the most LLM-ish output. Confidence: LOW on user-research specifics — based on general CLI-UX intuition, not verified against comparable tools.

**Prevention.**

1. **Name `generic` → `sectioned` or `structured`.** "Generic" is meaningless vocabulary; users don't map it to "sectioned format with a summary table." A descriptive name is a zero-cost prevention. Alternative: keep `generic` as an alias for backward compatibility if the milestone doc already exposed it, but make `--persona structured` the canonical name in `--help`.
2. **`--help` shows one-line descriptions and a short example per persona.** The `--persona` argument help text:
   ```
   --persona {scout,analyst,structured}
       scout      — 2-3 paragraph scout capsule (default, current voice)
       analyst    — Newsletter-style long-form with teaching callouts
       structured — Sectioned breakdown with a summary table (LLM-typical)
   ```
3. **`--list-personas` subcommand.** Prints the three names, a one-paragraph description, and a 3-line sample output for each. Cheap discoverability, no runtime cost.
4. **Error messages surface the choice.** If the user types `--persona scoutt` (typo), the error is: `unknown persona 'scoutt'. Choose from: scout, analyst, structured. Run 'pitcher-narratives --list-personas' for descriptions.`

**Verification.**

1. `tests/test_cli.py::test_persona_list_command` — `pitcher-narratives --list-personas` exits 0 and prints all three persona names.
2. `tests/test_cli.py::test_unknown_persona_error_message` — invalid persona name produces a helpful error mentioning the valid choices.
3. `tests/test_cli.py::test_help_text_includes_persona_descriptions` — `--help` output contains each persona's one-line description.
4. Manual: `uv run pitcher-narratives --help | grep persona` — readable, no jargon.

**Phase owner.** P3 (CLI surface).

---

### Pitfall 12: "Explain the model" contract slipping

**Failure mode.** The v1.10 milestone requires every persona to "always explain how the Pitching+ model works and the decisions it made." This is a shared-base contract. Three drift patterns:

- **Length pressure.** Scout's 2-3 paragraph format is already tight — adding an explainer sentence displaces analysis. The writer decides the explainer is "fluff" and drops it to hit the word cap.
- **Analyst redundancy suppression.** The analyst newsletter naturally explains things as it goes ("Stuff+ measures physical pitch characteristics — velocity, movement, release point"). The writer conflates "explaining while analyzing" with "the explainer requirement" and omits a dedicated explainer passage, even though the requirement was for an explicit one.
- **Generic persona dilutes it into a row.** The generic summary table tempts the writer to put `| Pitching+ | A model of pitch quality |` in the table and call it done. That is not an explanation, it is a tooltip. The anchor check has no category for "explainer quality" — it only checks faithfulness to synthesis, not adherence to writer-prompt meta-rules.

**Prevention.**

1. **Base prompt makes the requirement unambiguous.** `_WRITER_BASE_PROMPT` includes a dedicated paragraph: *"Every capsule MUST contain an explicit model-explainer passage. The explainer is one or more sentences (not a table row, not a parenthetical) that (a) names the relevant Pitching+ component(s) this capsule cites (Stuff+, Location+, or Pitching+), (b) says in plain English what the component measures, and (c) connects the model's grade to the specific observation the capsule is making. If multiple components are cited, the explainer covers each."*
2. **Post-generation explainer detector.** A new function `check_explainer_present(capsule: str) -> bool` that returns True iff the capsule contains at least one sentence-length span (15+ words) co-mentioning a Pitching+ component name (`Stuff+`, `Location+`, `Pitching+`) and a plain-English verb like "measures", "models", "reflects", "captures", "grades", "represents". If False, the pipeline logs a warning and (optionally, behind a flag) triggers one additional revision pass with a targeted instruction: *"The capsule is missing the required model explainer. Add one sentence that explains what Pitching+ measures and how it connects to your lead observation."*
3. **Extend anchor check with a new warning category: `EXPLAINER_MISSING`.** Because the explainer is a shared-base rule, the anchor check is the right enforcement surface. `WarningCategory` gains `"EXPLAINER_MISSING"` in `anchor.py:56`. The anchor prompt gains: *"5. Missing Model Explainer: The capsule must contain a sentence-length explanation of what Pitching+ / Stuff+ / Location+ measure in plain English. A table cell or parenthetical is not enough. If missing, flag EXPLAINER_MISSING."* Trade-off: adding a category changes the anchor prompt shape, which is a Pitfall 3 structural variation — must be verified doesn't break existing MISSED_SIGNAL behavior.
4. **Shape assertion in Pitfall 10's helpers.** Each `assert_*_shape` helper calls `check_explainer_present` and fails if it returns False.

**Verification.**

1. `tests/test_pipeline.py::test_check_explainer_present_accepts_scout_style` — fixture: a capsule with "Stuff+ grades the physical quality of each pitch by modeling velocity and movement against a league baseline" passes.
2. `tests/test_pipeline.py::test_check_explainer_present_rejects_tooltip_only` — fixture: a capsule with `| Pitching+ | model grade |` (table row only) fails.
3. `tests/test_pipeline.py::test_check_explainer_present_rejects_no_model_mention` — fixture: a capsule with pure analysis but no `Stuff+`/`Location+`/`Pitching+` mention fails.
4. `tests/test_anchor.py::test_anchor_warning_explainer_missing_category_valid` — `AnchorWarning(category="EXPLAINER_MISSING", description="...")` validates.
5. Manual: `uv run pitcher-narratives --persona analyst -p 657277 -w 10` and visually confirm a standalone explainer sentence exists in the output. Grep for `Stuff\+|Location\+|Pitching\+`.

**Phase owner.** P1 (base prompt rule) + P2 (anchor category extension, detector) + P5 (tests).

---

## Moderate Pitfalls

### Pitfall 13: Persona overlay drift between environments

**Failure mode.** Overlay strings live in `personas.py` as module constants. A developer tweaks the analyst overlay on a feature branch, ships it, but the hallucination guard's persona allowlist (in `pipeline.py`) wasn't updated in the same commit. The analyst persona now emits `arsenal depth score` as a term the overlay told it to use, but the allowlist still doesn't cover the word. The guard false-positives and users see spurious warnings on perfectly valid output.

**Prevention.** Co-locate per-persona config. New `personas.py` structure:

```
PERSONAS = {
    "scout":   PersonaConfig(overlay=..., allowed_terms=frozenset(), token_budget=4096, max_revisions=3, ...),
    "analyst": PersonaConfig(overlay=..., allowed_terms=frozenset({"playability", ...}), ...),
    ...
}
```

`pipeline.py` reads from `PERSONAS[persona_id]` for ALL persona-varying config — overlay text, allowlist, token budget, max revisions, streaming strategy. One file to review per persona change.

**Verification.** `tests/test_personas.py::test_persona_config_completeness` — assert every `PersonaConfig` has non-None values for all required fields.

**Phase owner.** P1.

### Pitfall 14: Scout default silent switch

**Failure mode.** Users have scripts invoking `pitcher-narratives -p 657277 -w 10` with no persona flag. If the default isn't explicitly `scout`, or if a later refactor changes the default, those scripts silently shift to a new format.

**Prevention.** The CLI argparser declares `--persona scout` as the literal default. A test asserts the default: `tests/test_cli.py::test_persona_default_is_scout`. A second test asserts that `pitcher-narratives -p X -w Y` and `pitcher-narratives --persona scout -p X -w Y` resolve to the same persona id (no special-casing).

**Phase owner.** P3.

### Pitfall 15: Signal extractor is persona-agnostic and might need per-persona hints

**Failure mode.** `signals.py::SIGNAL_EXTRACTOR_PROMPT` outputs `KeySignals` regardless of downstream persona. For scout, the secondary signals are "advisory." For generic, every populated secondary signal might become a table row. If the signal extractor is too enthusiastic (populating all 6 secondary fields), generic gets a 7-row table; if too conservative, analyst runs short on callout material.

**Prevention.** Do not edit `SIGNAL_EXTRACTOR_PROMPT` for v1.10. Instead, downstream persona builders filter `KeySignals` before rendering:

- `scout`: render all populated signals (current behavior).
- `analyst`: render all populated signals.
- `generic`: render only top_improvement, top_concern, and secondary signals the writer explicitly references in prose. Determined post-hoc by scanning the prose for signal keywords, then trimming unreferenced rows before the table is built.

This keeps the signal extractor stable and lets the persona layer own the trimming.

**Verification.** `tests/test_pipeline.py::test_generic_persona_trims_unreferenced_signals_from_table`.

**Phase owner.** P2 + P4.

### Pitfall 16: Missing persona validation at CLI edge

**Failure mode.** User passes `--persona SCOUT` (uppercase). The CLI doesn't normalize and errors ungracefully somewhere deep in the pipeline.

**Prevention.** `--persona` uses `type=str.lower` in argparse and `choices=["scout", "analyst", "structured"]` (assuming Pitfall 11's renaming). Invalid names caught at argparse boundary.

**Verification.** `tests/test_cli.py::test_persona_uppercase_normalized`, `tests/test_cli.py::test_persona_unknown_rejected_by_argparse`.

**Phase owner.** P3.

---

## Minor Pitfalls

### Pitfall 17: Documentation lags feature

**Failure mode.** `README.md` and `CLAUDE.md` describe only the scout behavior. Users reading docs don't know the other personas exist.

**Prevention.** P5 updates `README.md` with a `--persona` section and an example of each persona's output.

**Verification.** Manual doc review in the PR that ships v1.10.

**Phase owner.** P5.

### Pitfall 18: `pitcher-ask` accidentally inherits persona flag

**Failure mode.** A developer copies CLI arg-parsing boilerplate from `pitcher-narratives` to `pitcher-ask` and brings `--persona` with it. The milestone explicitly scopes `pitcher-ask` as untouched.

**Prevention.** `tests/test_ask_cli.py::test_ask_cli_does_not_accept_persona` — assert `--persona foo` fails argparse on `pitcher-ask`.

**Phase owner.** P3.

### Pitfall 19: `make_pipeline_agents` signature break propagates to `pitcher-ask`

**Failure mode.** Adding `persona_id` to `make_pipeline_agents` breaks callers. `pitcher-ask` imports this function (or a close cousin) and breaks silently.

**Prevention.** `persona_id: str = "scout"` has a default. All existing callers work unchanged. Explicit type hint.

**Verification.** Run the existing test suite after the change — no new test needed, existing tests will catch any regression.

**Phase owner.** P2.

### Pitfall 20: Generic persona's table in a plain-text pipe

**Failure mode.** `uv run pitcher-narratives --persona generic -p 657277 -w 10 > out.txt` pipes the capsule to a file. Raw markdown table `| a | b |` in `out.txt` is fine for a user who opens it in an editor but ugly for anyone piping to a log. No terminal-rendering trick helps here; it's just the nature of markdown.

**Prevention.** Accept the trade-off and document it. Alternatively, a `--format {markdown,plain}` flag that, for `plain`, converts markdown tables to ASCII-box tables or strips them. Probably out of scope for v1.10 — note in PROJECT.md as potential v1.11 work.

**Verification.** Manual.

**Phase owner.** P5 (documentation only).

---

## Phase-Specific Warnings (summary table)

| Phase | Pitfalls Owned | Critical Checks Before Phase Exits |
|---|---|---|
| P1 persona module | 1, 9, 12 (base rule), 13, 15 (overlay hints) | base prompt has zero voice words; scout-composed prompt byte-identical to v1.9; PERSONAS dict complete |
| P2 pipeline integration | 3, 4, 6, 7, 8, 12 (anchor category), 15, 19 | anchor prompt has persona-aware branch; revision loop has structural invariant check; writer cache point is in user message; `persona_id` defaults to scout |
| P3 CLI surface | 11, 14, 16, 18 | `--persona` default is scout; unknown persona errors clearly; pitcher-ask does NOT accept `--persona` |
| P4 per-persona build-out | 1 (overlays), 2 (regex + disclaimer sentinel), 5 (allowlist), 7 (length cap), 4 (overlay phrasing) | hallucination guard `--persona` flag tested; disclaimer sentinel implemented; overlay length cap explicit |
| P5 test + hardening | 9 (regression), 10 (shape), 17, 20, all manual smoke | scout regression test passes; shape helpers cover all 3 personas; docs mention personas |

## "What Might I Have Missed?" Review

- **Confidence gaps.** Pitfalls 6, 8, and 11 relied on training-data intuition about terminal streaming behavior, Anthropic cache-API shape, and CLI UX research because web search was unavailable. The code-level prevention advice still holds, but the "why" stories are LOW confidence until validated against the actual streaming output / cache metrics / user feedback.
- **Unverified assumption.** I assumed `pydantic-ai`'s `Agent.run_stream` streams tokens deltas such that a multi-character chunk could split a markdown `|` delimiter from its neighboring cell content. This is provider-dependent. If Gemini streams line-buffered already, Pitfall 6's generic-persona hybrid strategy is over-engineered. Worth measuring on a real run before committing to the refactor.
- **Anchor-category extension risk (Pitfall 12).** Adding `EXPLAINER_MISSING` to `WarningCategory` changes the anchor prompt surface. Existing tests in `test_anchor.py` use `Literal` types — a new category is additive and safe, but the anchor mini-tier agent must learn the new category name from the prompt. First-run false negatives until the category is well-understood by the model.
- **Not addressed.** Per-persona latency tracking, per-persona cost tracking, and observability via logfire. The existing pipeline has `setup_logging()` and `logfire.instrument_pydantic_ai()` — persona should become a span attribute on every writer run so cost analysis can group by persona. Out of scope for pitfalls but worth a note in P5.

## Sources

- **Code-grounded (HIGH confidence).** `src/pitcher_narratives/pipeline.py` (verified `_WRITER_PROMPT` at L408, `build_writer_input` at L782, `_run_anchor_revision_loop` at L1209, `check_hallucinated_metrics` at L1566, regex patterns at L1527 and L1546, `make_pipeline_agents` at L1112); `src/pitcher_narratives/anchor.py` (verified `ANCHOR_PROMPT`, `build_revision_message`, `WarningCategory` Literal, CachePoint placement); `src/pitcher_narratives/signals.py` (verified `KeySignals` primary/secondary structure, `SIGNAL_EXTRACTOR_PROMPT`); `src/pitcher_narratives/config.py` (verified `TOKEN_BUDGET_LARGE`, `MAX_REVISIONS`, `make_model_settings` per-provider branches); existing tests in `tests/test_hallucination_guard.py` and `tests/test_anchor.py`.
- **Milestone-grounded (HIGH confidence).** `.planning/PROJECT.md` Current Milestone section for v1.10 Output Personas scope and constraints.
- **Training data (MEDIUM–LOW confidence).** Generic LLM-prompt-overlay failure patterns, prompt-cache invalidation theory, markdown-streaming terminal rendering. Web search was unavailable for verification; advice is conservative and code-level, not dependent on specific tool versions.
