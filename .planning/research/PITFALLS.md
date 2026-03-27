# Pitfalls Research

**Domain:** LLM self-refinement / editor-anchor reflection loop for baseball narrative pipeline
**Researched:** 2026-03-27
**Confidence:** MEDIUM-HIGH (grounded in published LLM self-correction research, practical engineering experience with iterative LLM pipelines, and direct codebase analysis; no live web verification available for this session)

## Critical Pitfalls

### Pitfall 1: Quality Regression on Iteration (The Polishing Paradox)

**What goes wrong:**
The editor's first draft is actually the best version. Each revision pass degrades the capsule -- stripping out vivid scouting language, hedging confident claims into mush, or flattening the narrative into a bland, "safe" summary that passes the anchor check but reads like a committee wrote it. By iteration 3, the capsule has lost its voice. Research from Huang et al. (2024, "Large Language Models Cannot Self-Correct Reasoning Yet") demonstrates that LLM self-refinement frequently degrades correct answers into incorrect ones -- the model is not reliably able to distinguish "improvement" from "change."

In this specific codebase, the editor prompt explicitly cultivates a voice: "pragmatic, cautious, highly analytical... Write the way an analyst talks to another analyst -- plain, specific, conversational." Revision passes push the editor away from this voice toward generic, defensible prose because the model optimizes for satisfying the checker, not for maintaining voice.

**Why it happens:**
The editor sees anchor warnings as "things I got wrong" and over-corrects. If the anchor says `[OVERSTATED] The synthesis notes small sample on X but the capsule presents it as definitive`, the editor does not merely soften that one claim -- it preemptively hedges everything. LLMs have a strong "be helpful and comply" instinct. When told "you made mistakes," they become conservative across the board, not just on the flagged issues.

Additionally, each revision pass has less context about the *original editorial intent*. The editor wrote paragraph 1 to set up paragraph 2 with a specific thread. A surgical revision to paragraph 2 can break the thread that paragraph 1 established, but the editor does not re-read with fresh eyes -- it patches locally.

**How to avoid:**
- **Preserve the original capsule.** Always pass the original (iteration 0) capsule alongside the current revision and the anchor warnings. The revision prompt should say: "Revise ONLY the specific issues flagged below. Do not rewrite passages that were not flagged. Maintain the voice and thread of the original."
- **Diff-based revision instructions.** Instead of "rewrite the capsule addressing these warnings," say "For each warning, identify the specific sentence that needs to change and revise only that sentence. Return the full capsule with minimal changes."
- **Quality gate on revision.** After each revision, run a quick length/voice check: if the revised capsule is >20% shorter than the original, or if hedging language density spikes ("may," "could," "potentially" per sentence), reject the revision and keep the previous version.
- **Cap iterations at 2** (strongly recommended 1 preferred). Research consistently shows diminishing returns after the first revision pass. A second pass catches genuine misses from pass 1, but a third pass is almost always net-negative.

**Warning signs:**
- Capsule gets shorter with each iteration (content being stripped, not refined).
- Hedging words ("may," "could," "potentially," "appears to") increase across iterations.
- The narrative thread weakens -- paragraph 2 no longer follows from paragraph 1.
- Specific scouting language ("stuff," "feel," "finding a groove") is replaced with generic analytical language.
- The capsule reads the same regardless of whether the pitcher had a fascinating or boring outing.

**Phase to address:**
Phase 1 (reflection loop design) -- this must be baked into the revision prompt and iteration cap from day one. Cannot be fixed after the loop is built without redesigning the revision mechanism.

---

### Pitfall 2: Anchor Drift -- Checker Becomes Too Lenient or Too Strict

**What goes wrong:**
The anchor check, currently a single LLM call with a static prompt, does not have calibrated severity. Two failure modes:

*Too strict:* The anchor flags stylistic choices as factual errors. "The capsule says the slider 'has become his weapon' but the synthesis only shows a 4% usage increase" -- this is the anchor policing editorial interpretation, not factual fidelity. Every capsule gets flagged, the loop always runs to max iterations, and the final output is stripped of all editorial voice.

*Too lenient:* The anchor returns CLEAN on capsules that contain genuine directional errors or unsupported claims because the error is phrased in a way the anchor LLM does not catch. The anchor prompt currently checks for four specific patterns (missed signal, unsupported, direction error, overstated) but an LLM prompted to "check for problems" has a bias toward returning CLEAN when the capsule is well-written -- fluent prose masks factual errors.

**Why it happens:**
The anchor is an LLM, not a rule engine. Its judgment varies by run, by model temperature, and by how persuasively the capsule is written. A capsule that sounds confident and authoritative gets fewer flags than a tentative one, even if the tentative one is more factually accurate. This is the opposite of what you want.

In the current codebase, the anchor prompt asks for `[MISSED SIGNAL]`, `[UNSUPPORTED]`, `[DIRECTION ERROR]`, and `[OVERSTATED]` categories. But it provides no threshold guidance -- "how much of a usage increase warrants calling it a 'weapon'?" is left to the LLM's judgment, which is inconsistent.

**How to avoid:**
- **Add calibration examples to the anchor prompt.** Include 2-3 examples of issues that SHOULD be flagged and 2-3 examples of acceptable editorial interpretation that should NOT be flagged. This anchors (pun intended) the severity level.
- **Separate factual checks from editorial checks.** Factual: "The synthesis says velo was 94.2 but the capsule says 95.1." Editorial: "The capsule calls the slider a 'weapon' based on modest data." Only factual checks should trigger revision loops. Editorial flags get surfaced to the user as warnings but do not trigger revision.
- **Add deterministic pre-checks before the LLM anchor.** The existing `check_hallucinated_metrics()` function is a great model. Add deterministic checks for: (a) numbers in capsule that do not appear in synthesis, (b) directional words ("increase"/"decrease") that contradict synthesis trend strings. These catch the easy errors without LLM judgment variability.
- **Log anchor outputs across runs to calibrate.** If the anchor flags >50% of first-draft capsules, it is too strict. If it flags <10%, it is probably too lenient. Target 20-40% flag rate on first drafts.

**Warning signs:**
- The loop runs to max iterations on most pitchers (anchor too strict).
- The loop almost never iterates (anchor too lenient -- or the editor is perfect, but test this assumption).
- Anchor flags are inconsistent: the same capsule pattern gets flagged in one run but not another.
- Anchor flags stylistic issues: "The capsule uses the word 'weapon' but the synthesis does not use this word."
- Genuine errors in capsules that are obviously wrong when a human reads them pass the anchor check.

**Phase to address:**
Phase 1 (anchor prompt calibration) and Phase 2 (deterministic pre-checks). The calibration examples must exist before the loop is tested, or you will spend all of Phase 2 debugging false positives.

---

### Pitfall 3: The Editor Gaming the Checker

**What goes wrong:**
After one or two iterations, the editor learns (within the conversation context) what the anchor flags and starts writing to satisfy the checker rather than to inform the reader. The capsule becomes a "proof" that it addressed every synthesis bullet point rather than a narrative that tells a story. Every Key Signal gets explicitly mentioned, every metric gets a hedge, and the result reads like a checklist disguised as prose.

This is the LLM equivalent of "teaching to the test." The editor's revision pass sees the anchor's feedback format and optimizes for producing text that will parse as CLEAN, not text that reads well.

**Why it happens:**
The revision prompt necessarily includes the anchor warnings. The editor treats these as a rubric. LLMs are extremely good at satisfying explicit rubrics -- and extremely bad at satisfying implicit quality criteria (voice, flow, narrative thread) when those criteria conflict with the rubric. The anchor says "you missed the development pitch" so the editor jams in a sentence about the development pitch, even if it breaks the narrative flow.

In the current pipeline, the editor prompt says "Find the Thread" and "reorganize by narrative importance." But the revision prompt implicitly says "address these specific warnings." These two instructions conflict, and the explicit one wins.

**How to avoid:**
- **The revision prompt must explicitly say the editorial constraints still apply.** "You are still bound by all original instructions. Address the specific issues below WITHOUT abandoning your narrative thread. If an issue cannot be addressed without breaking the capsule's flow, note it as unresolvable and return the capsule unchanged for that issue."
- **Never pass the raw anchor output to the editor.** Reformat anchor warnings into targeted, minimal revision instructions. Instead of passing `[MISSED SIGNAL] The synthesis flagged X as the key concern but the capsule does not mention it`, pass: "The key concern from the synthesis (X) should be referenced somewhere in the capsule. Find a natural place for it." This is less rubric-like and more editorial.
- **Allow the editor to reject warnings.** The revision prompt should say: "If you believe a flagged issue is already adequately addressed through implication or narrative context, respond with [ACKNOWLEDGED] and explain why. Not every flag requires a text change." This prevents forced, unnatural insertions.

**Warning signs:**
- Revised capsules are longer than originals (stuffing in additional claims to satisfy warnings).
- The capsule mentions every Key Signal bullet point in the same order they appeared in the synthesis.
- Sentences like "It is worth noting that..." or "Additionally..." appear only in revised versions -- these are the editor's tell that it is satisfying a checklist.
- The narrative thread from paragraph 1 does not carry into paragraph 2 (the revision broke the connection).

**Phase to address:**
Phase 1 (revision prompt design). The prompt must be carefully crafted to subordinate checker satisfaction to editorial quality. This is the hardest prompt engineering problem in the entire reflection loop.

---

### Pitfall 4: Cost and Latency Explosion

**What goes wrong:**
Each iteration of the reflection loop adds two LLM calls (editor revision + anchor re-check). With the current five-phase pipeline, the base case is 5 LLM calls. A reflection loop with max_iterations=3 could add up to 6 more calls (3 editor + 3 anchor), tripling the cost and latency for the editor-anchor portion. At $0.003/1K input tokens with Claude Sonnet, a single report that previously cost ~$0.02 could cost ~$0.06. Across a full day's slate of 15 pitchers, that is meaningful.

More critically, latency matters for a CLI tool. The editor currently streams to stdout. If the loop means the user sees a streamed first draft, then silence while revision happens, then a *different* final version appears -- the UX is terrible.

**Why it happens:**
Reflection loops are cheap to implement ("just call the editor again") but expensive to run. The cost is invisible during development when you are testing one pitcher at a time but hits hard in production-like usage. Nobody models the cost before building the loop.

The streaming UX problem is architectural: the current `generate_report_streaming` function streams Phase 2 to stdout in real-time. A reflection loop means Phase 2 might run 2-3 times, and only the last iteration's output is "real."

**How to avoid:**
- **Do not stream the first draft if it might be revised.** Either: (a) run the editor silently on iteration 0, stream only the final iteration, or (b) stream iteration 0 with a visual indicator that revision is in progress, then print the final version. Option (a) is simpler but sacrifices the real-time feel. Option (b) preserves UX but is more complex.
- **Budget-aware iteration cap.** Track cumulative tokens across the loop. If total editor+anchor tokens exceed 2x the single-pass cost, stop iterating regardless of anchor status. This prevents runaway costs on edge cases where the anchor is being unreasonable.
- **Make the loop opt-in, not default.** Add a `--refine` flag to the CLI. Default behavior is the current single-pass pipeline. Users who want higher quality pay the latency/cost premium explicitly.
- **Consider cheaper models for the anchor.** The anchor check does not need the same model quality as the editor. A smaller, faster model (gpt-5.4-mini, or Claude Haiku) can do factual checking. The current codebase creates all agents with the same model -- the anchor agent should accept a separate model parameter.

**Warning signs:**
- Average report generation time increases >2x after adding the loop.
- Token costs per report increase >2x on average (some increase is expected, but >2x means the loop is usually iterating).
- Users complain about "the report changed after I started reading it" (streaming UX problem).
- The loop runs to max iterations for >30% of pitchers (the anchor is too strict, but the cost symptom appears first).

**Phase to address:**
Phase 1 (loop architecture and CLI flag) and Phase 2 (streaming UX redesign). The streaming decision must be made before implementation begins because it affects the function signature of `generate_report_streaming`.

---

### Pitfall 5: Infinite or Near-Infinite Loops

**What goes wrong:**
The anchor flags issue A. The editor fixes A but introduces issue B. The anchor flags B. The editor fixes B but reintroduces A. The loop oscillates without converging, hitting max_iterations every time and producing a capsule that is no better than the first draft.

A more subtle variant: the anchor flags a borderline issue. The editor makes a minimal change. The anchor flags the same issue again because the change was not sufficient. The editor makes another minimal change. The anchor is still not satisfied. This is not oscillation but gradual drift, and it burns through the iteration budget without resolution.

**Why it happens:**
LLMs do not have a stable notion of "fixed." Each editor call produces a *new* capsule, not a *patch* of the old one. The new capsule can introduce new issues anywhere, not just where the revision was targeted. The anchor checks the entire capsule each time, so new issues surface that were not present before.

The oscillation problem is especially acute when two anchor categories conflict. A capsule can be simultaneously flagged as `[OVERSTATED]` (too much confidence) and `[MISSED SIGNAL]` (not enough emphasis on a finding). The editor hedges to fix overstated, which triggers missed signal, which causes the editor to emphasize, which triggers overstated again.

**How to avoid:**
- **Hard iteration cap of 3, recommended 2.** This is not a bug -- it is a design decision. The loop exists to catch obvious errors, not to achieve perfection. Two passes (original + one revision) catches ~80% of fixable issues. A third pass has rapidly diminishing returns.
- **Track warnings across iterations.** If a warning that was present in iteration N reappears in iteration N+2 (after being absent in N+1), the loop is oscillating. Terminate immediately and surface the unresolved warning to the user.
- **Warn-set shrinking.** Each iteration should only check for warnings that were present in the previous iteration, not re-check the entire capsule for new issues. If iteration 1 found `[MISSED SIGNAL]` and `[DIRECTION ERROR]`, iteration 2's anchor check should ONLY verify those two issues were addressed. New issues introduced by the revision are handled as regular anchor warnings in the final output, not loop triggers.
- **Deterministic exit conditions.** The loop terminates when: (a) anchor returns CLEAN, (b) max iterations reached, (c) oscillation detected, or (d) the only remaining warnings are editorial (not factual). All four conditions must be implemented.

**Warning signs:**
- Average iteration count is close to max_iterations (the loop is always hitting the cap).
- The same warning text appears in both iteration 1 and iteration 3 (oscillation).
- Token usage per report varies wildly (some reports converge in 1 pass, others burn through 3).
- The final capsule is qualitatively worse than the first draft for >20% of pitchers.

**Phase to address:**
Phase 1 (loop termination logic). The termination conditions must be designed and implemented before the loop itself. Getting the termination wrong means the loop is undeployable.

---

### Pitfall 6: Revision Context Accumulation Bloat

**What goes wrong:**
Each iteration of the loop adds context: the original synthesis, the previous capsule, the anchor warnings, and possibly the revision history. By iteration 3, the editor's input prompt contains the synthesis (~2K tokens), the original capsule (~500 tokens), the revised capsule (~500 tokens), the first set of warnings (~200 tokens), the second set of warnings (~200 tokens), plus the revision instructions. The editor is now processing ~4K tokens of context that is mostly about its own previous failures, not about the pitcher.

This dilutes the editor's attention away from the source data and toward the meta-conversation about what it got wrong. The resulting capsule over-indexes on addressing warnings and under-indexes on the actual scouting insights.

**Why it happens:**
The natural implementation is to append: "Here is your previous capsule. Here are the warnings. Revise." Each iteration appends more. Nobody measures the context growth because each individual addition seems small.

**How to avoid:**
- **Fixed-size revision context.** The revision prompt should contain exactly: (1) the original synthesis (unchanged), (2) the CURRENT capsule (not history of all capsules), (3) the CURRENT anchor warnings. No revision history. The editor does not need to know what it wrote two iterations ago.
- **Keep the synthesis as the primary context.** The revision prompt should lead with the synthesis, then the capsule, then the warnings. Token-wise, the synthesis should always be >50% of the total context. If warnings are consuming more tokens than the synthesis, something is wrong.
- **Summarize warnings.** If the anchor produced 5 warnings, pass only the top 2-3 most severe. Minor warnings that survive the loop get surfaced to the user, not fed back to the editor.

**Warning signs:**
- Editor revision prompt token count grows >30% per iteration.
- The revised capsule references its own revision process ("Addressing the concern about..." or "As noted in the synthesis...").
- The capsule's primary metrics shift between iterations (the editor lost focus on the narrative thread and is now writing to the warnings).

**Phase to address:**
Phase 1 (revision prompt design). The prompt template must have a fixed structure that does not grow with iterations.

---

### Pitfall 7: Downstream Phase Invalidation

**What goes wrong:**
In the current pipeline, Phase 3 (Hook Writer) and Phase 4 (Fantasy Analyst) derive from the editor's capsule. If the reflection loop changes the capsule after the first draft, the downstream phases must re-run against the final capsule. But if the implementation naively runs the loop and then proceeds to downstream phases, this works fine. The dangerous case is if someone tries to parallelize: running downstream phases against the first-draft capsule while the loop is still running, then not re-running them when the capsule changes.

A more subtle issue: the hook writer and fantasy analyst were calibrated against single-draft capsules. A revised capsule that has been stripped of voice and hedged to satisfy the anchor may produce weaker hooks and blander fantasy insights -- the downstream phases inherit the quality regression from Pitfall 1.

**Why it happens:**
Performance optimization temptation. The loop adds latency, so a developer tries to overlap downstream phases with the revision loop. Or the reflection loop is added to the editor/anchor portion without re-testing downstream phase quality.

**How to avoid:**
- **Sequential execution is mandatory.** The loop must fully complete before downstream phases begin. This is already the natural implementation given the current codebase structure, but it should be explicitly documented and tested.
- **Test downstream phase quality after adding the loop.** Generate 10 reports with and without the loop. Compare hook quality and fantasy insight quality. If the loop degrades downstream output, the reflection loop is a net negative even if the capsule itself is more accurate.
- **The ReportResult model should track iteration metadata.** Add `revision_count: int` and `surviving_warnings: list[str]` to `ReportResult` so downstream consumers know whether the capsule was revised.

**Warning signs:**
- Hooks become generic after adding the reflection loop (they are derived from hedged, de-voiced capsules).
- Fantasy insights lose their specificity (the revised capsule mentions more metrics but with less conviction).
- The hook or fantasy output contradicts the final capsule (they were generated from an earlier draft).

**Phase to address:**
Phase 2 (integration testing). After the loop is working, re-test the full pipeline end-to-end. This is not a Phase 1 concern but it must be explicitly planned.

---

### Pitfall 8: Non-Deterministic Anchor Making Testing Impossible

**What goes wrong:**
The anchor check is an LLM call with inherent randomness. The same synthesis + capsule pair produces different anchor outputs on different runs. This makes it impossible to write deterministic tests for the reflection loop. You cannot assert "this capsule should trigger exactly 2 iterations" because the anchor might flag 0, 1, or 3 issues depending on the run.

**Why it happens:**
LLM outputs are stochastic even at low temperatures. The anchor's binary decision (CLEAN vs. warnings) means small probabilistic differences get amplified into completely different loop behavior. A warning that the anchor assigns 51% probability gets flagged; one at 49% does not. Across runs, this flip-flops.

**How to avoid:**
- **Test the loop logic with a mock anchor.** The reflection loop's iteration logic (termination conditions, oscillation detection, context management) should be testable with a deterministic mock that returns scripted anchor outputs. The pydantic-ai `TestModel` is perfect for this.
- **Test the anchor prompt separately.** Create a set of 5-10 synthesis+capsule pairs with known issues. Run the anchor against each one 5 times. If the same issue is flagged <80% of the time, the anchor prompt needs calibration examples for that issue type.
- **Log anchor outputs in production.** Every anchor check result should be logged (at minimum, the warning list). This creates a corpus for calibrating the anchor over time and for debugging "why did this report iterate 3 times?"
- **Set temperature=0 (or as low as the provider allows) for the anchor agent specifically.** The anchor is doing classification, not creative writing. Low temperature reduces variability.

**Warning signs:**
- The same pitcher's report varies significantly between runs (not in prose style, which is expected, but in iteration count and warning types).
- Tests that assert on anchor behavior are flaky.
- You cannot reproduce a bug report about "weird output for pitcher X" because re-running produces different results.

**Phase to address:**
Phase 1 (testing infrastructure). The mock anchor must be implemented before the loop logic is tested. Real anchor calibration is Phase 2.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Passing full anchor output directly to editor revision prompt | Simple to implement | Editor over-corrects, games the checker, revision quality degrades | Never -- always reformat warnings into minimal revision instructions |
| Using the same model for anchor and editor | One model config, simpler code | Anchor cost is unnecessarily high; same model may be "sympathetic" to its own writing style | MVP only -- use a cheaper/different model for anchor before v1.4 |
| No iteration cap | "Let it converge naturally" | Unbounded cost, oscillation risk, quality regression | Never -- cap at 2-3 from day one |
| Streaming the first draft when loop is enabled | Preserves the current UX feel | User sees text that gets replaced; confusing and wasteful | Never when loop is active -- stream only the final version |
| Skipping oscillation detection | Simpler termination logic | Loop burns through iterations without progress, wasting tokens and degrading quality | Never -- oscillation detection is cheap to implement and critical for loop health |
| Not tracking revision metadata in ReportResult | Simpler data model | Cannot diagnose loop behavior in production, cannot A/B test loop quality | Never -- add revision_count and surviving_warnings from day one |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Reflection loop + streaming | Streaming Phase 2 on every iteration, showing the user drafts that get replaced | Stream only the final iteration. Run prior iterations silently. Show a progress indicator ("Refining... pass 2/3") on stderr |
| Reflection loop + pydantic-ai agents | Creating a new Agent for each revision call | Reuse the existing editor Agent -- pydantic-ai agents are stateless between `run_sync` calls. The revision context goes in the user prompt, not the agent config |
| Reflection loop + CachePoint | Expecting cache hits on revision prompts | CachePoints work on prefix matching. Revision prompts have different prefixes (they include warnings). Cache the synthesis portion but expect no cache benefit on the revision-specific parts |
| Anchor check + model temperature | Using the same temperature for anchor as for editor | Editor benefits from temperature 0.7-1.0 (creative prose). Anchor should use temperature 0-0.3 (classification consistency). Override `model_settings` for the anchor agent |
| Anchor output parsing | Using string matching on LLM output to detect CLEAN vs. warnings | The anchor might return "CLEAN." or "Clean" or "The capsule is clean." Use case-insensitive matching and check for absence of bracket-prefixed lines, not just exact "CLEAN" string |
| Revision prompt + original editor prompt | Including the full editor system prompt in the revision call | The editor agent already has the system prompt. The revision context goes in the user message. Do not repeat system prompt content in the user message -- it wastes tokens and can create conflicting instructions |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded iteration count | Report generation takes 30+ seconds, token costs spike, user abandons CLI | Hard cap of 2-3 iterations; budget-aware early termination | Any iteration count >3 |
| Full re-check on every iteration | Anchor re-checks entire capsule instead of just the flagged issues, finds new issues each time | Targeted re-check: only verify the specific warnings from the previous iteration | When the capsule is long (>500 words) and the anchor is strict |
| Growing revision context | Editor prompt exceeds 5K tokens by iteration 3, attention diluted | Fixed-size revision prompt: synthesis + current capsule + current warnings only | By iteration 2-3 if revision history is accumulated |
| Same expensive model for all loop calls | 2-6 extra calls at full model price | Use a cheaper model for anchor (Haiku/gpt-5.4-mini), keep expensive model for editor only | Immediately -- anchor does not need creative writing ability |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent reflection loop with no progress indicator | User thinks the CLI hung after the synthesis phase completes | Print iteration progress to stderr: "Anchor check: 2 warnings found. Revising (pass 2/3)..." |
| Showing the first draft then replacing it | User starts reading, then text changes. Disorienting and erodes trust | Either stream only the final version, or clearly mark: "--- DRAFT (revision in progress) ---" |
| Not surfacing surviving warnings | User does not know the capsule has unresolved issues | Print surviving warnings to stderr after the capsule, as the current code already does. Add iteration count: "After 2 revision passes, 1 warning remains:" |
| Always running the loop even when the first draft is CLEAN | Unnecessary latency for reports that do not need revision | Skip the loop entirely when the first anchor check returns CLEAN (which should be 50-70% of the time if the editor prompt is good) |
| No way to disable the loop | Power users who trust the first draft and want speed cannot opt out | Add `--no-refine` flag, or make `--refine` opt-in until the loop is proven reliable |

## "Looks Done But Isn't" Checklist

- [ ] **Iteration cap:** Implemented and tested -- verify the loop actually terminates when max is reached, including when the anchor keeps finding new issues
- [ ] **Oscillation detection:** Verify the loop detects when warning A disappears in pass 2 but reappears in pass 3 -- this is the most common convergence failure
- [ ] **Voice preservation:** Generate 10 reports with and without the loop. Read them aloud. The loop versions should not sound noticeably more hedged or generic
- [ ] **Downstream quality:** Hook writer and fantasy analyst output quality has been compared pre- and post-loop. Regression means the loop is degrading capsule quality
- [ ] **Streaming UX:** Run the CLI with the loop enabled and verify the user experience is not confusing (no replaced text, clear progress indicators)
- [ ] **Cost tracking:** Measure total tokens per report with the loop. If average cost is >2x the non-loop cost, the anchor is too strict or the cap is too high
- [ ] **Surviving warnings surfaced:** When the loop hits max iterations with unresolved warnings, those warnings appear in the CLI output so the user knows
- [ ] **CLEAN short-circuit:** When the first anchor check returns CLEAN, the loop does not run (no wasted iterations). Verify this is the common case (>50%)
- [ ] **Deterministic tests exist:** The loop logic has tests using mock anchor outputs that cover: CLEAN on first pass, convergence in 2 passes, oscillation, max iterations hit
- [ ] **Anchor consistency:** The anchor flags the same known-bad capsule >80% of the time across 5 runs. If not, the anchor prompt needs calibration examples

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Quality regression (Pitfall 1) | MEDIUM | Redesign revision prompt to be surgical, not wholesale; add voice preservation checks; may need to reduce iteration cap to 1 |
| Anchor drift (Pitfall 2) | LOW | Add calibration examples to anchor prompt; add deterministic pre-checks; adjust severity by adding example-based few-shot |
| Editor gaming (Pitfall 3) | MEDIUM | Rewrite revision prompt to reformat warnings as editorial suggestions, not error reports; allow editor to reject warnings |
| Cost explosion (Pitfall 4) | LOW | Add budget-aware termination; use cheaper model for anchor; make loop opt-in |
| Infinite loops (Pitfall 5) | LOW | Add iteration cap (if missing) or reduce it; add oscillation detection; add targeted re-check |
| Context bloat (Pitfall 6) | LOW | Switch to fixed-size revision prompt (current capsule + current warnings only); drop revision history |
| Downstream invalidation (Pitfall 7) | MEDIUM | Ensure sequential execution; re-test downstream phases; may need to adjust hook/fantasy prompts if capsule voice changed |
| Non-deterministic testing (Pitfall 8) | LOW | Add mock anchor for loop logic tests; log real anchor outputs for calibration corpus |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Quality regression | Phase 1 (revision prompt design) | Read 10 loop-revised capsules vs 10 first-drafts. Voice quality should be indistinguishable. Hedging word count should not increase >20% |
| Anchor drift | Phase 1 (anchor calibration) + Phase 2 (deterministic checks) | Run anchor 5x on 5 known-issue capsules. Flag rate should be >80% per known issue. Run on 5 clean capsules. False positive rate should be <20% |
| Editor gaming | Phase 1 (revision prompt design) | Revised capsules should not mention all Key Signal bullets in synthesis order. Narrative thread from P1 to P2 should survive revision |
| Cost explosion | Phase 1 (loop architecture) | Measure: average tokens per report pre-loop vs post-loop. Target <1.8x increase. Average iteration count should be <1.5 |
| Infinite loops | Phase 1 (termination logic) | Unit tests with mock anchor: oscillation case terminates in 2 passes, not max. Convergence case terminates in 1 extra pass |
| Context bloat | Phase 1 (revision prompt template) | Assert: revision prompt token count is constant across iterations (within 10%). Synthesis is >50% of total revision context |
| Downstream invalidation | Phase 2 (integration testing) | Generate 10 reports end-to-end with loop. Hook quality and fantasy insight specificity compared to pre-loop baseline |
| Non-deterministic testing | Phase 1 (test infrastructure) | Loop logic test suite passes 100% of the time (no flakes). Uses mock anchors, not real LLM calls |

## Sources

- Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet" (2024) -- demonstrates that LLM self-correction without external feedback degrades performance; self-refinement works best when the critic provides genuinely new information, not just re-evaluating the same context (MEDIUM confidence -- from training data, not verified against live source)
- Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback" (NeurIPS 2023) -- shows self-refinement helps on some tasks but quality degrades after 2-3 iterations; diminishing returns are consistent across tasks (MEDIUM confidence -- from training data)
- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning" (NeurIPS 2023) -- demonstrates that verbal feedback loops can be effective but require careful design of the feedback mechanism to avoid reward hacking (MEDIUM confidence -- from training data)
- Pan et al., "Automatically Correcting Large Language Models" (2024) -- survey of LLM self-correction methods; finds that intrinsic self-correction (same model checking itself) is unreliable compared to external verification (MEDIUM confidence -- from training data)
- Direct codebase analysis of `/Users/matt/src/pitcher-narratives/src/pitcher_narratives/report.py` -- anchor prompt, editor prompt, pipeline orchestration (HIGH confidence -- read directly)
- Practical engineering experience with iterative LLM pipelines -- iteration caps, oscillation, context management patterns (MEDIUM confidence -- from training data, widely observed in practice)

---
*Pitfalls research for: LLM self-refinement / editor-anchor reflection loop*
*Researched: 2026-03-27*
