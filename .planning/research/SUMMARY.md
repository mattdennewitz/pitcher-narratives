# v1.10 Output Personas — Research Synthesis

**Project:** Pitcher Narratives
**Milestone:** v1.10 Output Personas
**Researched:** 2026-04-11
**Overall confidence:** HIGH on code-grounded claims; MEDIUM on LLM-behavior predictions that can only be validated by running the pipeline.

Source files (read these for detail — this document does not duplicate their content):
- [STACK.md](./STACK.md) — library landscape, pydantic-ai composition options, provider-by-provider cache analysis
- [FEATURES.md](./FEATURES.md) — persona schema, voice targets, CLI affordances, testing surfaces, "explain the model" delivery
- [ARCHITECTURE.md](./ARCHITECTURE.md) — module layout, `make_pipeline_agents` signature, CLI threading path, phase ordering
- [PITFALLS.md](./PITFALLS.md) — 20 numbered pitfalls (12 critical) with runnable verifications

---

## Executive Summary (one screen)

**What v1.10 is.** A pure writer-layer additive milestone. It introduces `--persona {scout,analyst,generic}` on the `pitcher-narratives` CLI, routed through `generate_pipeline_streaming → _run_pipeline → make_pipeline_agents` as a plain string kwarg that resolves to a persona object at the factory boundary. Every specialist, every audit pass, the signal extractor, the anchor check, the hallucination guard, the revision loop, and the three-bullet executive summary are shared infrastructure. `pitcher-ask`, `pitcher-scout`, `analyst.py`, `resolver.py`, `data.py`, `engine.py`, and `context.py` stay untouched.

**Recommended mechanism.** One `personas.py` module owning a frozen `Persona` dataclass, a `SHARED_WRITER_BASE` constant (the voice-free analytical contract extracted from the current `_WRITER_PROMPT`), three overlay constants, a `PERSONAS` registry, and a `build_writer_system_prompt(persona) -> str` composer. Three writer Agent instances (one per persona) are built inside `make_pipeline_agents(..., persona=SCOUT)` at construction time — not a shared agent with per-run `instructions=` overrides, not `Agent.override()`, not a templating engine. Plain string concatenation at import time. Zero new dependencies. The four researchers converged on this unanimously.

**Top-three risks** (ordered by severity):

1. **Scout byte-parity breaks during prompt extraction.** The moment `_WRITER_PROMPT` is split into `BASE + "\n\n" + SCOUT_OVERLAY`, whitespace or section-ordering drift can materially shift LLM output. Mitigation: freeze the v1.9 `_WRITER_PROMPT` into a fixture file and assert byte-identity between composed-scout and fixture in `tests/test_personas.py` before any other v1.10 test runs. This is a phase-exit gate, not a passing concern.
2. **Anchor check misfires on generic persona's summary table.** The `ANCHOR_PROMPT` has only ever seen prose capsules. A markdown table of grades ("IMPROVED" vs. synthesis's "dropped") can produce false-positive `UNSUPPORTED` warnings, triggering revision passes that damage the table. Mitigation: a minimal, static addendum to `ANCHOR_PROMPT` instructing the checker to treat table cells as structured restatement of findings (see Disagreement 1 below for why this is preferred over a persona-aware `build_anchor_message` branch).
3. **Generic persona sectioned format encourages padding.** Sectioned outputs have a natural gravity toward "fill every section" — writers will invent `## Putaway Pitch` sections or pad summary tables to five rows when only three signals exist. Mitigation: the generic overlay ties table row count deterministically to populated `KeySignals`, and a targeted hallucination test uses a known-dirty fixture (fabricated section) to validate the guard still discriminates on the new format.

**Recommended phase ordering.** A → B → C → D → E, where A extracts the base prompt, B wires the pipeline with scout-only (phase-exit gate: byte-parity), C adds analyst, D adds generic (which is where the one `anchor.py` edit lives, if any), E adds CLI surface + docs. C and D can run in parallel across contributors because they share no code. CLI wiring intentionally comes last so personas can be validated via direct function calls before surface area is committed.

---

## Decisions locked by research (all four researchers agree)

| Decision | Rationale |
|---|---|
| **New `src/pitcher_narratives/personas.py` module.** Mirrors `signals.py` and `anchor.py` layout. Not in `pipeline.py` (already ~1,400 lines), not in `config.py` (zero prompt content today). | STACK §3, ARCHITECTURE §1, FEATURES Cat 1, PITFALLS 13 |
| **Frozen `@dataclass` for `Persona`, not pydantic BaseModel, not TOML.** No validation needed — personas are hand-authored code constants. No serialization. Dataclass is stdlib-light and frozen is hashable for module-level singletons. | STACK §3, ARCHITECTURE §1 |
| **Shared base prompt + trailing overlay, concatenated with `\n\n`.** No anchor-tag splicing. No Jinja/Mustache. No `Agent.override()`. No per-run `instructions=`. The eventual bytes sent to the provider are identical to a single `system_prompt=` string; extra machinery buys nothing. | STACK §1-2, ARCHITECTURE §2, FEATURES Cat 2 |
| **Overlay goes LAST in the composed prompt**, not prepended. LLMs rank the last block as most salient, which is where voice instructions should land — correctness rules live above them in the base. | FEATURES Cat 2, PITFALLS 1 |
| **One writer `Agent` per persona, built inside `make_pipeline_agents(..., persona=SCOUT)` with a default.** Not a factory, not `dict[name, Agent]`, not runtime override. Default preserves `analyst.py:618`'s two-positional-arg call unchanged. | STACK §4, ARCHITECTURE §2 |
| **Revision loop (`_run_anchor_revision_loop`) is persona-agnostic by construction.** It already takes `writer_agent` as an opaque dependency; whichever writer the caller built is whichever writer does revisions. Zero changes to the loop itself. | ARCHITECTURE §3 |
| **`build_writer_input` stays `str`-typed and shared across all personas.** The input is the raw material (key signals + five specialist outputs in fixed order); the persona is about how the writer *renders* that material, not about which material arrives. | ARCHITECTURE §4, FEATURES Cat 3 |
| **CLI threading path: string at boundaries, `Persona` object inside `make_pipeline_agents`.** `cli.py` → `generate_pipeline_streaming(persona: str = "scout")` → `_run_pipeline` → resolves to `Persona` via `get_persona()` → `make_pipeline_agents`. | ARCHITECTURE §5 |
| **`# Scouting Report` wrapper heading is stable across all personas.** The generic persona's `##` sub-headings nest correctly under it. `cli.py` prints the capsule opaquely via `stream.stream_text(delta=True)` and does not parse, reformat, or re-heading the content. | ARCHITECTURE §6 |
| **Generic overlay forbids `#` (h1) headings inside the capsule.** The outer report owns h1; generic uses `##` and `###` only. Enforced by overlay text plus a regex assertion in shape helpers. | ARCHITECTURE §6, PITFALLS 3 |
| **No user-defined personas, no env-var defaults, no `--custom-persona` flag.** Custom personas would bypass quality gates and break anchor/hallucination invariants. Explicitly a v2.x concern. | FEATURES Cat 4, PITFALLS 11 |
| **Scout must be byte-identical-ish to v1.9.** Enforced at the prompt level, not at LLM-output level — `build_writer_system_prompt(SCOUT).strip() == <frozen v1.9 _WRITER_PROMPT text>`. The fixture lives in a diff-visible file (`tests/fixtures/writer_prompt_scout.txt` or similar). | STACK "Phase 1+2", ARCHITECTURE §7, FEATURES Cat 5 §3a, PITFALLS 9 |
| **`--list-personas` ships in v1.10; `--describe-persona`, `--compare`, `--voice` alias, `--custom-persona`, `--length` are deferred or rejected.** | FEATURES Cat 4, PITFALLS 11 |
| **No new anchor `WarningCategory`.** The existing five (MISSED_SIGNAL, UNSUPPORTED, DIRECTION_ERROR, OVERSTATED, UNDERWEIGHTED) stay persona-agnostic. See Disagreement 1 for the `EXPLAINER_MISSING` resolution. | FEATURES Cat 5, Cat 6 |
| **"Explain the model" rule lives in the shared base, not the overlays.** Overlays modulate depth (terse / full / once-per-section), not presence. The rule is a correctness obligation, not a stylistic preference. | FEATURES Cat 6, PITFALLS 12 |
| **Scout banned-word list is in the SCOUT overlay, not in the base.** The base has zero voice words so overlays can't inherit scout idioms. Prevents voice bleed in both directions. | PITFALLS 1 |
| **Phase ordering: A persona module → B pipeline wiring (scout parity gate) → C analyst → D generic → E CLI + docs.** C and D are independent; CLI deliberately comes last so personas are reachable for testing before committing to surface area. | ARCHITECTURE §7, PITFALLS phase table |

---

## Disagreements that the researchers did NOT resolve (decided here)

### Disagreement 1: Where to touch `anchor.py`

| Researcher | Proposal |
|---|---|
| **Architecture** | One-line addendum to `ANCHOR_PROMPT` telling the checker "the capsule may contain markdown headings and tables; validate semantic content against the synthesis, not formatting." Static, always active, zero branching. |
| **Pitfalls** | Persona-aware `build_anchor_message(..., persona_hints: dict)` branch + extend `WarningCategory` with `EXPLAINER_MISSING`. More principled; more invasive. |
| **Features** | Read-only. No touch. Test the existing anchor's tolerance against a synthetic generic capsule and fix only if test fails. |

**Decision: Minimal-touch, conditional on Phase D test results. Ladder, not branch.**

1. **Default position: treat `anchor.py` as read-only.** The Features researcher is right that the existing `ANCHOR_PROMPT` doesn't explicitly enforce "no tables, no headings" — it enforces faithfulness claims. So in principle the prompt is already persona-neutral. The first thing Phase D does is run a synthetic generic capsule (headings + summary table) through `check_hallucinated_metrics` AND the anchor check with `TestModel` or a minimal real call, then observe whether the anchor false-fires on table cells.

2. **If the test passes clean: ship zero changes to `anchor.py`.** This is the cheapest outcome. It is also plausible — the anchor agent is a reasonable model and the `ANCHOR_PROMPT` phrasing doesn't hard-assume prose.

3. **If the test produces false positives (predicted failure mode: `IMPROVED` vs. `dropped` token mismatch on table cells): apply the Architecture researcher's one-line addendum to `ANCHOR_PROMPT`.** One line. No new function signature. No new `persona_hints` parameter threading through `build_anchor_message`. The addendum is universally active; for prose personas it is a no-op because there are no tables to tolerate. This preserves the "zero refactors outside the writer layer" milestone posture.

4. **Reject the persona-aware `build_anchor_message` branch.** Threading a `persona_hints` dict through the call site introduces a new coupling from the pipeline orchestrator into the anchor module for a problem that a single line of prompt text solves. It is the principled option in isolation but the wrong trade-off inside a milestone whose explicit constraint is "no cross-cutting changes."

5. **Reject the `EXPLAINER_MISSING` anchor category extension.** Two independent reasons:
   - The anchor's job is faithfulness-to-synthesis, not meta-rule enforcement. Adding editorial obligations to the fact-checker conflates two different contracts — Features Cat 6 calls this out explicitly.
   - `WarningCategory` is a `Literal` type; adding a value changes the anchor prompt surface and requires the anchor model to learn the new category name from the prompt, with first-run false-negative risk (PITFALLS §"What Might I Have Missed" flags this).
   - v1.10's "explain the model" enforcement should be a base-prompt rule + a manual golden-sample review (FEATURES Cat 6) + optionally a pipeline-level `check_explainer_present(capsule) -> bool` post-processor that logs a warning (PITFALLS 12 item 2). The dedicated editorial agent idea is a v1.11 concern.

**Phase ownership:** Phase D runs the test and owns the conditional addendum. Phase A-C must not touch `anchor.py`.

**Verification if the addendum ships:** PITFALLS §3 verification 1 — assert the anchor prompt contains the tolerance language; plus a synthetic-capsule smoke test that feeds known-clean and known-noisy generic captions and asserts expected clean/warning outcomes.

---

### Disagreement 2: Prompt-cache optimization scope

| Researcher | Proposal |
|---|---|
| **Stack** | Cache optimization is OUT of v1.10 scope. `anthropic_cache_instructions` is unset today, so the writer's system prompt is NOT cached. OpenAI caching is implicit and persona-prefix-lineage-safe by construction. Google caching is off (`google_cached_content` unset). No cache benefit currently exists to protect. |
| **Pitfalls §8** | Cache optimization is IN scope. Move base to `system_prompt`, overlay to user message, `CachePoint()` between synthesis and overlay to reuse base across personas. |

**Decision: Deferred. Stack researcher wins on current-state evidence.**

Rationale:

1. **The proposed problem does not exist today.** STACK §5 directly inspected `pydantic_ai/models/anthropic.py:775-1036` and grepped `src/pitcher_narratives/` for `anthropic_cache_instructions` — zero hits. The writer's system prompt is re-encoded from scratch on every call, persona or not. Swapping to three per-persona agents cannot regress a cache that is not turned on.

2. **The Pitfall 8 fix is a structural refactor dressed as a preventive measure.** Moving the overlay out of `system_prompt` and into a user message `CachePoint`-bracketed block changes the Agent API surface we depend on (`system_prompt=` is load-bearing in every existing agent), and would require every existing persona-agnostic caller path to know about it. This is exactly the "cross-cutting change" the milestone forbids.

3. **OpenAI implicit caching and Google non-caching are evidence-backed.** STACK §5 read `openai.py:1322-1324` (CachePoint no-op) and `google.py:917-921` (no inline cache mechanism) directly. Each persona will form its own cache lineage on OpenAI automatically; Google has nothing to invalidate.

4. **Even if we later turn Anthropic system-prompt caching on, the three-per-persona-agent layout is cache-correct by construction.** Anthropic caches match on exact prefix of the combined system string. `f"{BASE}\n\n{SCOUT_OVERLAY}"`, `f"{BASE}\n\n{ANALYST_OVERLAY}"`, and `f"{BASE}\n\n{GENERIC_OVERLAY}"` are three distinct stable prefixes. Each hits its own cache entry; no cross-persona invalidation is possible because each persona uses a different agent. Opting into `anthropic_cache_instructions=True` in a future milestone is a one-line change on `AnthropicModelSettings` — no refactor of the persona plumbing needed.

5. **Premature optimization cost.** Phase 2 already has enough risk (scout byte-parity, factory signature change, default-argument ordering). Adding a cache refactor to the same phase is exactly the kind of scope creep that breaks milestones.

**Action:** File a follow-up ticket — "v1.11+: measure writer system-prompt re-encode cost on Anthropic and decide whether to enable `anthropic_cache_instructions=True`." Do not touch cache plumbing in v1.10.

**Verification that the decision holds:** PITFALLS §8 verification 1 is kept ("assert `_WRITER_BASE_PROMPT` is a module-level string constant, not constructed at runtime") because it is a cheap future-proofing check regardless of cache strategy. PITFALLS §8 verification 2 and 3 are deferred.

---

## Decisions that surface in the plan (genuine forks for the requirements step)

These are NOT paper-over-able. The planner must pick a direction and write a REQ against it.

### Fork 1: Hallucination guard table-cell stripping strategy

PITFALLS §2 proposes a `DISCLAIMER_BEGIN ... DISCLAIMER_END` sentinel block with `strip_disclaimers: bool = False` parameter on `check_hallucinated_metrics`. This handles the "generic persona has a table row disclaiming ERA and the regex catches it" failure mode.

**Alternatives the planner must consider:**

- **(a) Sentinel block** (PITFALLS §2 proposal). Cleanest separation, but requires the generic overlay to teach the model to emit the sentinels reliably, and adds a parameter to `check_hallucinated_metrics`.
- **(b) Pre-strip all markdown table cells** from the capsule before regex scanning, for ALL personas. Simpler, no overlay work, but risks false negatives if a prose persona ever accidentally includes a pipe character.
- **(c) Persona-aware allowlist extension** (PITFALLS §5 proposal): `check_hallucinated_metrics(..., persona: str | None = None)` reads a per-persona `_PERSONA_KNOWN_METRICS` dict of safe phrases. Doesn't solve the table-disclaimer case but solves the analyst newsletter vocabulary case (`playability`, `tunneling gap`).
- **(d) Do nothing** until a real false-positive is observed in Phase D testing.

**Recommended default for the requirements step: (c) + (d).** Ship per-persona allowlist extension (it's clearly needed for analyst vocabulary and is cheap — a frozenset lookup), and defer table-cell stripping until Phase D produces a real false positive. If it does, prefer (b) pre-strip over (a) sentinel because it requires zero overlay changes and zero new guardrail state. REQ should pin the `persona` parameter on `check_hallucinated_metrics` but leave disclaimer handling undecided until evidence.

### Fork 2: Does `build_writer_input` need a "Summary Table Facts" block for generic?

ARCHITECTURE §4 flags this: if the generic persona's summary table needs specific pre-computed values (velocity delta, xRV100 delta, etc.) that aren't cleanly surfaced in the specialist prose, the writer will need those facts appended to its input — or it will invent them.

**Two options:**

- **(a)** Pull the values from `ctx` directly in `pipeline.py` and append a `## Summary Table Facts` block to `build_writer_input`. Prose personas ignore it because their overlays never reference it. Low risk.
- **(b)** Require generic overlay to cite values only from existing specialist output. Writer discipline, no input change. Higher hallucination risk.

**Recommended default: (a), conditional on Phase D table design.** Do not implement until the generic overlay's table schema is nailed down. If every table column maps to a value already in specialist prose, (b) wins by default (less machinery). If even one column needs a standalone numeric fact, (a) is mandatory because (b) is indistinguishable from "writer makes up a number that looks right." REQ should mark this as "implement iff Phase D table schema requires it."

### Fork 3: Scout byte-parity test strategy

PITFALLS §9 proposes four layered strategies:

1. Prompt-level byte-identical assertion (composed scout prompt vs. frozen v1.9 fixture).
2. Structural output shape assertion via `TestModel`.
3. Sampling-robust golden on a fixed pitcher (gated behind `--real-llm`).
4. Diff-on-upgrade convention (human review of fixture updates).

**Recommended default: ship 1, 2, and 4 in v1.10. Defer 3.**

- (1) and (2) are deterministic, cheap, run in CI, and catch the most common failure modes (whitespace drift, accidental section reordering, accidental shape change).
- (3) depends on `RUN_LIVE_LLM=1` or similar CI gating that costs money every commit. The milestone goal is regression safety, not LLM-drift detection — and LLM drift is a v1.11+ concern anyway.
- (4) is a PR review convention, not code. Document in CLAUDE.md or the v1.10 plan header, not as a test.

REQ should explicitly name the fixture file path (`tests/fixtures/writer_prompt_scout.txt`) and the test name so reviewers know exactly what to look for on scout-regression PRs.

### Fork 4: Per-persona `MAX_REVISIONS` cap

PITFALLS §4 proposes `MAX_REVISIONS_PER_PERSONA = {"scout": 3, "analyst": 2, "generic": 2}` on the grounds that overlay richness scales revision risk — each revision pass has a chance to damage the sectioned format or newsletter callouts.

**Recommended default: defer. Ship with the shared `MAX_REVISIONS = 3`** (current value in config.py) **for all three personas.** Lowering the cap is a premature optimization; raising it per-persona requires evidence from real runs. If Phase D or E shows generic is producing visibly more anchor warnings per persona than scout, revisit in a follow-up. REQ should pin revision cap behavior unchanged for v1.10.

### Fork 5: Persona name — `generic` vs. `structured` vs. `sectioned`

PITFALLS §11 argues `generic` is a meaningless label that confuses users. Recommends `structured` or `sectioned`.

**Recommended default: ship as `generic` in v1.10; open a follow-up ticket for user-feedback-driven rename in v1.11.** The milestone spec and PROJECT.md already use `generic` — renaming costs docs, tests, and user-muscle-memory for a name that hasn't been tested with users yet. A rename should be evidence-driven, not preemptive. If renamed later, `generic` should remain as an alias to avoid breaking scripts.

---

## Scout byte-parity strategy (explicit framing)

Scout byte-parity is the single most-cited invariant across all four research files. It deserves explicit framing because "byte-identical-ish" is doing a lot of work in the milestone constraint, and the planner needs a precise definition.

**What "byte-identical-ish" actually means:**

- **Prompt level: byte-identical, hard.** The string `build_writer_system_prompt(SCOUT)` must equal the v1.9 `_WRITER_PROMPT` verbatim — same characters, same whitespace, same line endings. This is the tightest guarantee and is the one hard test the milestone hinges on. Implementation: Phase A extracts a candidate base + overlay split, runs the composer, diffs against the frozen fixture, iterates the split until the diff is empty. Fixture lives at `tests/fixtures/writer_prompt_scout.txt` (diff-visible, reviewer-friendly).

- **Agent level: identical construction.** `make_pipeline_agents(provider, thinking)` (no persona arg, using the default) and `make_pipeline_agents(provider, thinking, SCOUT)` must produce writer Agents whose `system_prompt` fields are identical strings. Test: assert equality at the Agent object level.

- **Output level: shape-identical, not byte-identical.** LLM sampling at temperature 0.7 produces different tokens on every call. The guarantee is structural (no tables, no `##` headers, 200-700 word range, no bullet lists, etc.) enforced by shape assertions from PITFALLS §10's helpers, not by diffing against a golden.

- **Behavior level: `pitcher-narratives -p X -w Y` and `pitcher-narratives --persona scout -p X -w Y` are observationally identical.** The CLI default resolves to `"scout"` and both paths route through the same code — no special-casing of the unflagged invocation. Test: `tests/test_cli.py::test_persona_default_is_scout` and a second test asserting the two invocations land on the same `args.persona` string.

**What byte-parity does NOT protect against:** a future edit to the base prompt (or the scout overlay) that accidentally changes scout behavior. That is what the diff-on-upgrade convention (PITFALLS §9 item 4) and human PR review are for. The test just makes the regression visible — it cannot prevent a deliberate edit.

**Phase ownership:** Phase A writes the fixture and the byte-identity test. Phase B runs the full pipeline test suite and confirms `analyst.py`'s `pitcher-ask --pipeline` path (the one that calls `make_pipeline_agents(provider, thinking)` positionally at `analyst.py:618`) still works with the new default argument. Phase B cannot exit until both tests pass.

---

## Risk register

| # | Risk | Severity | Owning phase | Mitigation |
|---|---|---|---|---|
| 1 | Scout prompt byte-parity breaks during extraction (whitespace drift, section reordering) | **Critical** | A/B | Frozen `_WRITER_PROMPT` fixture + byte-identity test; phase-exit gate on Phase B |
| 2 | `analyst.py:618` positional call breaks when `make_pipeline_agents` signature changes | **Critical** | B | Default `persona=SCOUT`; run `pitcher-ask --pipeline` integration test after Phase B |
| 3 | Anchor check false-positives on generic summary-table cells | **High** | D | Conditional one-line `ANCHOR_PROMPT` addendum (see Disagreement 1); synthetic generic-capsule test |
| 4 | Generic persona invents summary-table rows to "fill" the structure | **High** | D | Overlay rule: one row per populated `KeySignals` signal; row-count assertion test with `TestModel` fixtures |
| 5 | Hallucination guard false positives on analyst newsletter vocabulary (`playability`, `tunneling gap`) | **High** | D | Per-persona allowlist extension on `check_hallucinated_metrics(persona: str \| None)`; test vectors per persona |
| 6 | Voice bleed from SCOUT_OVERLAY vocabulary back into BASE during iteration | **High** | A/D | Base-prompt "no voice words" string assertion test (`test_base_prompt_has_no_voice_words`) |
| 7 | Generic persona emits `#` (h1) heading that collides with CLI wrapper heading | **Medium** | D | Overlay negative constraint + regex assertion in shape helper |
| 8 | Revision loop damages generic table on revision pass (row drop, row reorder) | **Medium** | D | Structural invariant check post-revision (PITFALLS §4 item 2) OR persona-aware revision-message phrasing |
| 9 | "Explain the model" rule dropped under scout length pressure (2-3 paragraph cap) | **Medium** | A/D | Base-prompt mandatory paragraph on explainer presence; optional `check_explainer_present(capsule)` post-processor that logs a warning; manual golden-sample review during D/E |
| 10 | `--persona` flag accidentally added to `pitcher-ask` or `pitcher-scout` via copy-paste | **Medium** | E | `tests/test_ask_cli.py::test_ask_cli_does_not_accept_persona` (and equivalent for scout_cli) |
| 11 | Token-budget blowout on analyst persona with thinking enabled (overflow `max_tokens=4096`) | **Medium** | B/D | Per-persona `PERSONA_TOKEN_BUDGETS` dict in `config.py`; analyst overlay hard-length cap; post-stream word-count sanity check |
| 12 | Golden-output samples rot on every model upgrade | **Low** | E | Shape assertions not text matches; gate any real-LLM test behind `RUN_LIVE_LLM=1` env var (not per-commit CI) |
| 13 | Markdown-table streaming UX looks broken on terminal auto-wrap | **Low** | D | Per-persona streaming strategy (scout delta, analyst line-buffered, generic hybrid with placeholder); validate in narrow and wide terminals |
| 14 | User types `--persona SCOUT` (uppercase) and hits ungraceful deep error | **Low** | E | `type=str.lower` on argparse + `choices=` list for early rejection |
| 15 | Docs (`README.md`, `METHODOLOGY.md`) lag feature | **Low** | E | Required doc updates in the same PR as CLI wiring; reviewer checklist item |

---

## Features mapped to phases

The requirements-definition step will read this section to structure REQ-IDs. Each row below is a candidate REQ bucket; the requirements-definition step is free to split or merge as needed. Feature detail lives in FEATURES.md — this section only maps features to phases.

### Phase A — Persona module scaffolding

Single responsibility: extract `SHARED_WRITER_BASE` from the current `_WRITER_PROMPT` and define `SCOUT` overlay such that `build_writer_system_prompt(SCOUT) == <v1.9 _WRITER_PROMPT>` byte-for-byte.

- REQ: `src/pitcher_narratives/personas.py` exists with `Persona` frozen dataclass, `SHARED_WRITER_BASE` constant, `SCOUT` constant, `PERSONAS` dict, `DEFAULT_PERSONA`, `build_writer_system_prompt`, `get_persona` (raises ValueError).
- REQ: `_WRITER_BASE_PROMPT` contains zero scout voice words (asserted via `test_base_prompt_has_no_voice_words`).
- REQ: Base prompt contains "EXPLAIN THE MODEL" section (or equivalent named section) and the existing KeySignals / directional-consistency / temporal-grounding rules (asserted by base-prompt contract test).
- REQ: `tests/fixtures/writer_prompt_scout.txt` frozen to v1.9 `_WRITER_PROMPT`.
- REQ: `tests/test_personas.py::test_scout_composed_prompt_is_byte_identical_to_v19` passes.
- REQ: Registry completeness test (at this stage, only `SCOUT` is populated — analyst and generic stubs are TODO).

**Pitfalls addressed:** 1 (voice bleed), 9 (scout regression), 12 (explain-the-model base rule), 13 (co-located config).

### Phase B — Pipeline integration (scout parity gate)

Single responsibility: make the pipeline persona-aware while keeping scout behavior byte-identical. NO new personas yet, NO CLI changes yet.

- REQ: `make_pipeline_agents(provider, thinking, persona: Persona = DEFAULT_PERSONA)` — defaulted, positional-compatible.
- REQ: `_WRITER_PROMPT` deleted from `pipeline.py`; writer agent built via `build_writer_system_prompt(persona)`.
- REQ: `_run_pipeline(..., persona: str = "scout")` and `generate_pipeline_streaming(..., persona: str = "scout")` — string kwarg with default.
- REQ: `_run_pipeline` resolves the string to a `Persona` object via `get_persona()` before passing to `make_pipeline_agents`.
- REQ: Existing pipeline tests pass unchanged.
- REQ: `pitcher-ask --pipeline` integration test passes (`analyst.py:618`'s positional call still works).
- REQ: Golden regression test: run fixture pitcher through `generate_pipeline_streaming` with no persona arg, verify writer's `system_prompt` equals the fixture file byte-for-byte.
- REQ: `cli.py`, `analyst.py`, `anchor.py` are NOT touched in this phase.

**Pitfalls addressed:** 2 (hallucination false negatives are latent here but not introduced), 9 (scout regression — phase-exit gate), 19 (positional signature compatibility).

### Phase C — Analyst persona

Single responsibility: add the newsletter voice. Reachable via `generate_pipeline_streaming(ctx, persona="analyst")` directly; CLI wiring still deferred.

- REQ: `ANALYST` persona constant added to `personas.py` with overlay text targeting 450-800 word newsletter voice (see FEATURES §3b for voice specification).
- REQ: `PERSONAS` registry updated; `get_persona("analyst")` returns it.
- REQ: Analyst overlay contains explicit "explain the model" depth instruction (full sentence, not terse) per FEATURES Cat 6.
- REQ: Analyst overlay contains the scout-inherited banned-word list plus teaching-vocabulary permissions (FEATURES §3b).
- REQ: Analyst overlay contains a hard length cap instruction ("if you approach 2000 words, wrap up") per PITFALLS §7.
- REQ: `check_hallucinated_metrics(..., persona: str | None = None)` gains persona parameter; `_PERSONA_KNOWN_METRICS` dict includes analyst safe phrases (`playability`, `tunneling gap`, `pitch tree`, `arsenal depth`).
- REQ: Analyst smoke test via `TestModel` — runs the pipeline with `persona="analyst"` and asserts no crash, non-empty narrative, composed prompt starts with `SHARED_WRITER_BASE`.
- REQ: Hallucination guard test: analyst vocabulary not flagged as unknown.
- REQ: Shape helper `assert_analyst_shape(text)` per PITFALLS §10 — 1000-3000 words (or calibrated range), allowed callouts, known metrics cited.

**Pitfalls addressed:** 1 (overlay owns its voice), 5 (persona allowlist), 7 (length cap), 12 (explainer depth).

### Phase D — Generic persona (highest-risk phase)

Single responsibility: add the sectioned-with-table format and validate it against the shared quality gates (anchor, hallucination, revision loop). This is the phase where the `anchor.py` touch happens, conditionally.

- REQ: `GENERIC` persona constant added with overlay targeting 400-700 word sectioned format with summary table (see FEATURES §3c).
- REQ: Generic overlay fixes the section set: `## Stuff`, `## Location`, `## Run Value & Execution`, `## Trend`, `## Game Shape`, `## Summary Table` — in that order.
- REQ: Generic overlay explicitly forbids `#` (h1) headings (collision with `# Scouting Report` wrapper).
- REQ: Generic overlay ties summary-table row count deterministically to populated `KeySignals` (one row per signal actually referenced in prose).
- REQ: Anchor check tolerance test: synthetic generic capsule (headings + table) passes `check_hallucinated_metrics` and anchor check clean. If it fails, apply one-line `ANCHOR_PROMPT` addendum per Disagreement 1 and re-run. This is the ONLY touch to `anchor.py` in the entire milestone.
- REQ: Hallucination guard regression test: known-clean generic capsule passes; known-dirty capsule (with fabricated `## Putaway Pitch` section or invented metric in a table row) is flagged.
- REQ: Shape helper `assert_generic_shape(text)` — exactly one markdown table, correct row count, allowed section set, no h1 headings.
- REQ: Table-fact flow: IF the table schema requires values not cleanly surfaced in specialist prose, append a `## Summary Table Facts` block to `build_writer_input` (see Fork 2). ELSE leave `build_writer_input` unchanged.
- REQ: Streaming UX test: generic stream does NOT emit mid-cell breaks (PITFALLS §6). Implementation only if the terminal test confirms the issue on a real run.
- REQ: Per-persona token budget: `PERSONA_TOKEN_BUDGETS["generic"] = 5120` in `config.py` if Phase B did not already add the dict. Writer uses the persona's budget via `make_model_settings`.

**Pitfalls addressed:** 2 (table-cell disclaimers), 3 (anchor brittleness), 4 (revision loop damages table), 6 (streaming UX), 7 (token budget), 10 (shape assertions), 12 (explainer once per section), 15 (signal filtering).

### Phase E — CLI wiring + `--list-personas` + docs

Single responsibility: expose the three personas via CLI surface.

- REQ: `cli.py` argparse adds `--persona` with `choices=sorted(PERSONAS.keys())`, `default="scout"`, `type=str.lower`.
- REQ: `cli.py` argparse adds `--list-personas` as `action="store_true"` that prints the registry and exits 0. No LLM call.
- REQ: `args.persona` threads into `generate_pipeline_streaming(persona=args.persona)`.
- REQ: `--print-prompts` output for the writer section uses `build_writer_system_prompt(selected_persona)` so operators see the composed prompt.
- REQ: Verbose mode logs `persona=<id>` to stderr.
- REQ: CLI tests: `--persona bogus` exits 2 with error naming valid choices; `--persona SCOUT` (uppercase) normalizes and succeeds; `--persona scout` and no-flag produce identical behavior; `--list-personas` exits 0 and contains all three ids.
- REQ: `pitcher-ask` and `pitcher-scout` CLIs do NOT accept `--persona` (explicit rejection test).
- REQ: `README.md` updated with `--persona` section and a one-line description of each persona.
- REQ: `METHODOLOGY.md` mentions persona-aware writer prompts.

**Pitfalls addressed:** 11 (naming/help discoverability), 14 (silent default switch), 16 (uppercase normalization), 17 (docs), 18 (pitcher-ask isolation).

---

## Confidence assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | **HIGH** | STACK.md grounded in direct reads of `pydantic_ai/agent/__init__.py`, `pydantic_ai/models/{anthropic,openai,google}.py`, and our own `pipeline.py`. The cache-semantics claims are MEDIUM because they rely on training-data knowledge of Anthropic/OpenAI cache APIs, which were not re-verified this session. |
| Features | **HIGH on codebase claims, MEDIUM on voice targets** | Schema, overlay mechanism, testing surfaces, and "explain the model" contract are all codebase-verifiable. Voice-target descriptions (Baseball Prospectus newsletter tone, default-LLM sectioned format) are training-data-based and explicitly flagged as "sanity-check against real exemplars during execution." |
| Architecture | **HIGH** | Grounded entirely in direct reads of `pipeline.py`, `cli.py`, `anchor.py`, `config.py`, `signals.py`, `analyst.py`. Every function signature and line number cited has been verified. Anchor-tolerance prediction (MEDIUM) is the only LLM-behavior claim in the file. |
| Pitfalls | **HIGH on code-grounded prevention, MEDIUM on LLM-behavior predictions** | 20 pitfalls with runnable verifications. Regex patterns, prompt structures, and file locations are verified. Predictions about streaming UX (§6), cache API shape (§8), and user naming confusion (§11) are explicitly marked LOW-to-MEDIUM confidence. |

**Overall confidence:** HIGH for shipping the plan. The genuine unknowns are all Phase D LLM-behavior questions ("will the anchor false-fire on tables?", "will streaming break on wide terminals?") that can only be answered by running the pipeline with the new overlay — and Phase D is structured so those questions get answered before code is shipped, not after.

---

*Research completed: 2026-04-11*
*Ready for requirements definition: yes*
*Two disagreements resolved in-document (anchor.py touch strategy: minimal-touch conditional addendum; cache optimization: deferred to v1.11+).*
