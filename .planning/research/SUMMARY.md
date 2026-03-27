# Project Research Summary

**Project:** Pitcher Narratives — v1.3 Editor-Anchor Reflection Loop
**Domain:** LLM self-refinement / actor-critic feedback loop for narrative quality
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

The v1.3 milestone adds a bounded editor-anchor reflection loop to the existing five-phase pipeline. The current architecture already has the necessary actor-critic structure: the editor (actor) writes a narrative capsule and the anchor checker (critic) verifies factual fidelity against the synthesis. What v1.3 adds is closing the loop — anchor warnings feed back to the editor, the editor revises, and the cycle repeats until the capsule is clean or an iteration cap is hit. Research across both the installed pydantic-ai 1.72 source and LLM self-refinement literature confirms the pattern is sound and the existing codebase requires zero new dependencies.

The recommended implementation is a plain Python while-loop inside `generate_report_streaming()`, using `AnchorResult` structured Pydantic output (replacing the current text-parsed string) with fresh editor prompt construction per revision pass. `CachePoint` avoids reprocessing the static synthesis context on each revision. The maximum iteration cap defaults to 3 total passes (initial + 2 revisions), the first pass streams to stdout while revisions run silently, and all changes are localized to `report.py` and `cli.py` — no new files, no new packages, no async conversion required.

The key risks are not engineering risks but prompt design risks: quality regression (the editor over-corrects and strips voice on revision), anchor drift (the checker's severity calibration is inconsistent without example grounding), and editor gaming (the editor learns to satisfy the anchor rubric rather than inform the reader). These pitfalls are documented in NeurIPS 2023-2024 self-refinement research and share a common prevention: the revision prompt must be surgical, pass only the current capsule plus current warnings (no accumulated history), explicitly preserve editorial voice, and allow the editor to acknowledge rather than force-fix every warning. Getting the revision prompt right is more important than the loop mechanics themselves.

## Key Findings

### Recommended Stack

No new dependencies are needed. The v1.3 reflection loop is implementable entirely with pydantic-ai 1.72 primitives already present in the codebase. The anchor agent's `output_type` changes from `str` to `AnchorResult` (a new Pydantic model) to enable programmatic loop control. All other agents, models, and configuration remain unchanged. `pydantic-graph` was evaluated and ruled out: its `BaseNode` API is async-only, converting the synchronous pipeline would require an `asyncio.run()` bridge throughout `generate_report_streaming()` for zero functional benefit — the loop topology is literally `while not done`, which does not justify the ~80 lines of async boilerplate.

**Core technologies:**
- `pydantic-ai 1.72` Agent with `output_type=AnchorResult` — structured anchor output enabling programmatic convergence checks; verified against installed source (`agent/abstract.py`, `run.py`)
- `pydantic.BaseModel` (`AnchorResult`, `AnchorWarning`) — typed warning categories (MISSED_SIGNAL, UNSUPPORTED, DIRECTION_ERROR, OVERSTATED) replacing free-text parsing; enables loop control without fragile string matching
- Python `dataclass` (`ReflectionTrace`) — iteration tracking with `RunUsage.incr()` for per-iteration token aggregation; zero overhead, trivially debuggable; `RunUsage.incr()` verified in installed `pydantic_ai/usage.py`
- `CachePoint` (already imported in codebase) — cache the synthesis prefix in revision prompts so the static portion is free across all revision passes

### Expected Features

**Must have (table stakes):**
- Iteration cap (MAX_REVISIONS=2, so 3 total passes) — without a hard ceiling the loop is undeployable; LLM loops do not monotonically improve past 2-3 iterations
- Convergence detection (CLEAN exit) — break immediately when anchor returns clean; clean first pass should add zero overhead (expected 50-70% of first drafts)
- Warning pass-through to editor — anchor findings must appear in the revision prompt; the editor cannot fix what it cannot see
- Distinct editor revision prompt — says "fix these specific issues, preserve everything else" rather than re-running the initial write prompt (which causes full rewrites that destroy good material)
- Surviving warnings surfaced to user — when the loop hits max iterations with unresolved issues, report them to stderr with iteration count
- Iteration metadata in ReportResult — `revision_count: int` and `anchor_converged: bool` for cost tracking and diagnostics

**Should have (quality improvements, v1.3 fast-follow after baseline loop is validated):**
- Targeted revision instruction — explicit "revise ONLY the flagged passages" wording preventing wholesale rewrite quality regression
- Warning-type prioritization — factual errors (DIRECTION_ERROR, UNSUPPORTED) trigger revision; editorial issues (OVERSTATED) surface as warnings without burning another iteration
- Diff tracking between passes — developer insight into whether the editor is making surgical fixes or wholesale rewrites (length change, hedging word count)

**Defer (v1.4+):**
- Per-warning fix verification — tracking which specific warnings resolved per pass requires semantic comparison across warning sets; high complexity for marginal benefit
- Separate cheaper model for anchor — anchor check does not need the same model as the editor; use Haiku/mini for factual classification once the loop behavior is understood

**Anti-features (never build):**
- Unlimited iteration — quality plateaus or degrades after 2-3 passes; every production LLM loop uses a hard cap
- Full rewrite on each revision — the single most common failure mode; always use targeted revision prompts
- LLM-as-judge without ground truth — the anchor's value comes from checking against the synthesis (external anchor); do not expand it to subjective quality scoring
- Streaming revision passes — confusing UX; the user should never see a capsule stream and then be replaced
- Temperature escalation across retries — higher temperature introduces new hallucinations; factual errors are fixed by prompt clarity, not randomness

### Architecture Approach

The reflection loop is a localized change entirely within `generate_report_streaming()` in `report.py`. Phases 1, 3, and 4 (synthesizer, hook writer, fantasy analyst) are completely unchanged and run sequentially after the loop completes. The loop is internal to the Phase 2/2.5 editor-anchor block. Three architectural options were evaluated: simple while-loop (recommended), pydantic-graph state machine (overengineered), and custom `ReflectionLoop` orchestrator class (premature abstraction for a 1-method class). The build order follows natural dependency: pure helper functions first, then loop mechanics, then consumer updates.

**Major components:**
1. `AnchorResult` / `AnchorWarning` Pydantic models — replace free-text anchor output; `is_clean: bool` drives loop exit; typed `category` enum enables severity filtering without string parsing
2. `ReflectionTrace` dataclass — holds `iterations`, `history: list[AnchorResult]`, `usage_per_iteration: list[RunUsage]`; `.converged`, `.exhausted`, `.surviving_warnings`, `.total_usage` properties encapsulate convergence logic cleanly
3. `_build_revision_message(ctx, synthesis, capsule, warnings)` — fixed-size revision prompt: synthesis (CachePoint-cached) + previous capsule + formatted warnings + targeted revision instruction; no history accumulation across iterations
4. `_run_editor_first_pass()` / `_run_editor_revision()` — first pass uses `run_stream_sync()` to stdout; revision passes use `run_sync()` silently; streaming only on the final capsule
5. Reflection while-loop in `generate_report_streaming()` — anchor check, break on clean, editor revision; phases 3/4 receive the final capsule unchanged

### Critical Pitfalls

1. **Quality regression on revision (the polishing paradox)** — the editor over-corrects, strips voice, and hedges everything; LLMs optimize for satisfying the checker, not maintaining voice. Prevent by passing only the current capsule (not revision history), instructing "revise ONLY the flagged passages", and capping at 2 revisions. Warn if the revised capsule is >20% shorter or hedging word density increases.

2. **Anchor drift (too strict or too lenient)** — the anchor LLM's calibration is inconsistent without example guidance; fluent prose masks factual errors. Prevent by adding 2-3 calibration examples to the anchor prompt showing what SHOULD vs. SHOULD NOT be flagged, and by separating factual checks (trigger revision) from editorial checks (surface as warnings only). Target 20-40% first-draft flag rate.

3. **Editor gaming the checker** — after revisions, the editor learns to satisfy the anchor rubric rather than inform the reader; produces a "proof" capsule that mentions every synthesis bullet in synthesis order. Prevent by reformatting anchor warnings as editorial suggestions ("find a natural place for X") rather than error reports, and by explicitly reinstating voice/thread requirements in every revision prompt.

4. **Cost and latency explosion** — worst case adds 4 LLM calls (+~$0.012, +~32s). Prevent with hard iteration cap, CLEAN short-circuit (no overhead when first draft passes), and streaming only the final version. If >30% of reports iterate to max, the anchor is too strict.

5. **Non-deterministic anchor making testing impossible** — the loop logic must be tested using `FunctionModel` (a callable mock returning scripted per-call outputs), not real LLM calls. Real anchor calibration is a separate post-implementation concern requiring a corpus of real reports.

6. **Oscillation without convergence** — the editor fixes issue A, introducing issue B; the anchor flags B; the editor reintroduces A. Prevent with oscillation detection: if a warning from iteration N reappears in iteration N+2, terminate immediately rather than burning through the cap.

7. **Context accumulation bloat** — naively appending previous capsules and warning sets grows the revision prompt ~30% per iteration, diluting editor attention away from the synthesis. Prevent with fixed-size revision context: synthesis + current capsule + current warnings only; no iteration history.

## Implications for Roadmap

Based on combined research, the implementation has a clear three-phase build order determined by dependency relationships.

### Phase 1: Foundation — Helper Functions and Data Models

**Rationale:** All loop mechanics depend on these data models and helpers being correct. Every component in this phase is a pure function or a data model with zero side effects — independently testable with no LLM calls and no risk of breaking the existing pipeline. Build confidence here before touching the orchestration.

**Delivers:** `AnchorResult`/`AnchorWarning` Pydantic models, `ReflectionTrace` dataclass, `_parse_anchor_output()` (extracted from existing inline code), `_build_revision_message()` (new prompt builder), `ReportResult.revision_count` and `ReportResult.anchor_converged` field additions.

**Addresses:** Structured output requirement, context bloat prevention (fixed-size prompt template baked in from the start), non-deterministic testing (pure functions have deterministic unit tests), downstream metadata (ReportResult fields).

**Avoids:** Pitfall 6 (context accumulation) by designing the fixed-size revision prompt template upfront. Pitfall 8 (non-deterministic testing) by making all foundation components pure functions. Pitfall 3 (editor gaming) by crafting the revision prompt to reformat warnings as suggestions rather than error reports.

**Research flag:** Standard patterns. All APIs verified against installed source at HIGH confidence. No additional research needed.

### Phase 2: Loop Mechanics and Orchestration

**Rationale:** With foundation in place, the loop is a straightforward assembly. The streaming decision (stream only the final capsule) must be locked in here because it affects the function signature; reversing it later requires caller changes. The `anchor_checker` output type change to `AnchorResult` is a breaking change in `_make_agents()` and must be done atomically with the type definition.

**Delivers:** `_run_editor_first_pass()` (extract existing streaming block), `_run_editor_revision()` (new silent revision helper), reflection while-loop in `generate_report_streaming()`, `MAX_REVISIONS` constant, `--max-revisions` CLI flag, anchor agent `output_type` change to `AnchorResult`.

**Addresses:** All table stakes features — iteration cap, convergence detection, warning pass-through, surviving warnings, iteration metadata. Default cap set to 2 revisions (3 total passes); configurable via flag.

**Avoids:** Pitfall 4 (cost/latency) through CLEAN short-circuit. Pitfall 2 (anchor drift) by keeping anchor prompt identical across all passes. Pitfall 1 (quality regression) through the targeted revision prompt from Phase 1. Pitfall 5 (infinite loops) through hard cap.

**Research flag:** Needs real-data validation after implementation. The revision prompt quality cannot be verified with mock models — plan for one prompt tuning pass after running against 5-10 real pitcher reports.

### Phase 3: Integration Testing and Quality Validation

**Rationale:** The loop is feature-complete after Phase 2, but Pitfall 7 (downstream phase invalidation) and Pitfall 2 (anchor calibration) cannot be caught by unit tests. End-to-end validation with real data is required before the feature is considered production-ready.

**Delivers:** Comparison of 10 reports with and without the loop (capsule voice quality, hook quality, fantasy insight specificity), anchor calibration assessment (first-draft flag rate, consistency across repeated runs), CLI integration for iteration progress display on stderr, comprehensive test suite using `FunctionModel` for loop convergence scenarios.

**Addresses:** Full "Looks Done But Isn't" checklist from PITFALLS.md — iteration cap termination, oscillation detection, voice preservation, downstream quality, streaming UX, cost tracking, surviving warnings, CLEAN short-circuit, deterministic tests, anchor consistency.

**Avoids:** Pitfall 7 (downstream invalidation — hook/fantasy phases must be re-tested after loop is added). Pitfall 2 (anchor calibration — add few-shot examples if flag rate is outside 20-40%). Pitfall 1 (voice regression — read 10 revised capsules aloud; they should not sound noticeably more hedged).

**Research flag:** Anchor prompt calibration examples must be derived from real flag rates observed during this phase. Cannot be specified in advance. If first-draft flag rate is >50%, the anchor needs calibration examples before shipping.

### Phase Ordering Rationale

- Foundation before loop mechanics because `AnchorResult` is a breaking type change in `_make_agents()`; all consumers must be updated atomically with the model definition
- Loop mechanics before integration testing because the streaming UX decision is architectural and must be validated in full pipeline context; unit tests cannot confirm the user experience is not confusing
- Targeted revision prompt wording (differentiator feature) is intentionally omitted from Phase 2 and folded into Phase 3 validation — implement basic "fix these issues" first, refine to surgical "fix only these passages" after seeing real editor behavior on real data
- Warning-type prioritization is deferred to Phase 3 or fast-follow; the basic loop works without it and implementing it prematurely adds complexity before seeing which warning types actually cause problems

### Research Flags

Phases needing deeper research or empirical validation during planning:
- **Phase 3 (anchor calibration):** Calibration examples depend on observed real flag rates. Cannot pre-specify without data. Plan for one calibration iteration after 10+ real reports.
- **Phase 2 (revision prompt wording):** The highest-risk single artifact. Structure is settled; exact instruction tone must be tuned against real pitcher data. Reserve explicit time for this.

Phases with standard patterns (skip additional research):
- **Phase 1:** All data model and helper patterns verified against installed pydantic-ai source at HIGH confidence.
- **Phase 2 loop mechanics:** The while-loop structure is idiomatic; the only open question (pydantic-graph vs while-loop) is conclusively resolved.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All pydantic-ai 1.72 APIs verified against installed source (`agent/abstract.py`, `run.py`, `usage.py`, `pydantic_graph/`). Zero new dependencies confirmed. |
| Features | MEDIUM | Table stakes features are clear and well-scoped. Differentiator features (targeted revision, warning prioritization) are grounded in LLM self-refinement literature but specific prompt designs are empirically untested against this codebase. |
| Architecture | HIGH | Build order and component boundaries verified against existing `report.py`. All three architectural alternatives evaluated with specific rationale for rejection. Anti-patterns documented with root cause analysis. |
| Pitfalls | MEDIUM-HIGH | Core pitfalls (quality regression, oscillation, context bloat) grounded in NeurIPS 2023-2024 research. Severity specific to this pipeline is inferred, not measured. Prevention strategies are concrete and actionable. |

**Overall confidence:** HIGH for implementation approach; MEDIUM for prompt quality outcomes (must be empirically validated).

### Gaps to Address

- **Revision prompt surgical precision:** The difference between "revise the capsule" and "revise only the flagged passages" is significant for voice quality. Exact prompt language should be tested against 5-10 real capsule+warning pairs during Phase 2 validation. This is the main deliverable risk.
- **Anchor calibration threshold:** Target 20-40% first-draft flag rate. Current anchor strictness is unknown without running the loop on real data. If flag rate is outside target, Phase 3 calibration work expands significantly.
- **MAX_REVISIONS default (2 vs 3):** STACK.md recommends 3, ARCHITECTURE.md recommends 2. Both agree it should be configurable. Start at 2 (cheaper, more conservative); raise to 3 if data shows a third pass has net positive quality impact.
- **TestModel multi-response:** pydantic-ai's `TestModel` returns the same output every call; `FunctionModel` (callable that varies per call) is required for loop convergence tests. Verified to exist in installed source; must be used in Phase 1/2 test infrastructure.

## Sources

### Primary (HIGH confidence)

- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/agent/abstract.py` — `run_sync` signature, `output_type`, `message_history` parameters
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_ai/usage.py` — `RunUsage.incr()` for per-iteration token aggregation
- `/Users/matt/src/pitcher-narratives/.venv/lib/python3.14/site-packages/pydantic_graph/nodes.py`, `graph.py`, `beta/` — `BaseNode` async-only constraint; `Fork`/`Join`/`Decision` nodes; confirmed plain while-loop is correct choice
- `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/report.py` — current 5-phase pipeline structure, `CachePoint` usage, `_make_agents` pattern, anchor warning categories
- `/Users/matt/src/pitcher-narratives/tests/test_report.py` — `TestModel` / `FunctionModel` usage patterns for loop testing

### Secondary (MEDIUM confidence)

- Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet" (2024) — quality regression after 2-3 revision passes; self-correction without external feedback degrades performance
- Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback" (NeurIPS 2023) — diminishing returns after 2-3 iterations; targeted feedback outperforms holistic feedback
- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning" (NeurIPS 2023) — actor-critic loop design; reward hacking risks when critic has no external ground truth
- Pan et al., "Automatically Correcting Large Language Models" (2024) — external verification (anchor against synthesis) more reliable than intrinsic self-critique

### Tertiary (LOW confidence)

- Cost estimates ($0.003/call, ~8s/call, worst case +$0.012 per report) — based on general Sonnet 4.6 pricing; validate against actual API billing after Phase 2

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
