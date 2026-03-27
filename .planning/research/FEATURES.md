# Feature Landscape: Editor-Anchor Reflection Loop

**Domain:** LLM self-refinement / actor-critic feedback loop for narrative quality
**Researched:** 2026-03-27
**Confidence:** MEDIUM (training data only -- no web verification available; patterns well-established in literature through mid-2025)

## Context

The existing v1.2 pipeline runs five phases linearly: synthesizer produces structured bullets, editor writes a capsule, anchor checker verifies fidelity (outputs CLEAN or bracketed warnings), then hook writer and fantasy analyst derive from the capsule. Anchor warnings currently print to stderr and are ignored by the pipeline. The v1.3 milestone closes the loop: anchor feedback goes back to the editor, the editor revises, and the cycle repeats until the anchor returns CLEAN or a cap is hit.

This research focuses exclusively on the NEW features needed for the reflection loop -- not the existing pipeline features documented in the v1.0 FEATURES.md.

## Table Stakes

Features the reflection loop must have. Missing any of these makes the loop either dangerous (unbounded cost) or useless (no convergence signal).

| Feature | Why Expected | Complexity | Depends On |
|---------|--------------|------------|------------|
| **Iteration cap (max_retries)** | Without a hard ceiling, a stubborn anchor checker and a non-converging editor can loop indefinitely, burning API tokens and wall-clock time. Every production LLM loop in practice uses an iteration cap. The standard range is 2-3 retries (so 3-4 total passes). | LOW | Nothing new -- pure control flow in `generate_report_streaming` |
| **Convergence detection (CLEAN exit)** | The anchor already returns "CLEAN" when the capsule passes. The loop must check this after each anchor pass and break early. Without it, every run burns max iterations even when the first capsule was fine. | LOW | Existing anchor output format (already returns CLEAN vs warnings) |
| **Warning pass-through to editor** | The editor cannot fix what it cannot see. Anchor warnings (bracketed lines like `[MISSED SIGNAL] ...`) must be injected into the editor's revision prompt so the LLM knows exactly what to address. | LOW | Existing anchor output format, new editor revision prompt |
| **Editor revision prompt (distinct from initial prompt)** | The revision pass needs a different instruction than the initial write. The initial prompt says "find the thread and write a capsule." The revision prompt says "here is your capsule, here are the problems -- fix these specific issues while preserving what works." Reusing the initial prompt causes the editor to rewrite from scratch, losing good material. | MEDIUM | New prompt text, inserted into editor agent's user message |
| **Surviving warnings surfaced to user** | If the loop exhausts its iteration cap with warnings still present, those warnings must reach the user (currently via stderr). The user needs to know the capsule was not fully validated. | LOW | Existing anchor_warnings field in ReportResult |
| **Iteration metadata tracking** | The user (and developer) needs to know: how many passes did it take? Did it converge or hit the cap? This is essential for debugging prompt quality and tuning the cap. Minimum: iteration count in ReportResult or stderr output. | LOW | New field on ReportResult or stderr logging |

## Differentiators

Features that elevate the loop from "retry until clean" to "smart, targeted revision." Not required for v1.3 launch but significantly improve quality and cost-efficiency.

| Feature | Value Proposition | Complexity | Depends On |
|---------|-------------------|------------|------------|
| **Targeted revision (fix-only prompt)** | Instead of "rewrite the capsule," the revision prompt says "here is the capsule, here are the specific problems -- revise ONLY the affected passages." This prevents quality regression: the editor does not rewrite paragraphs that were already good. In practice, targeted revision converges faster (usually 1 retry) and preserves prose quality better than full rewrites. | MEDIUM | Editor revision prompt design, anchor warning format (already structured with brackets) |
| **Warning-type prioritization** | Not all anchor warnings are equal. `[DIRECTION ERROR]` (saying up when data says down) is a factual error that must be fixed. `[OVERSTATED]` (confidence exceeds sample size) is a tone issue that may be acceptable. Categorizing warnings by severity lets the loop focus on critical fixes and accept minor imperfections rather than iterating endlessly on stylistic nuances. | MEDIUM | Anchor warning categories (already defined: MISSED SIGNAL, UNSUPPORTED, DIRECTION ERROR, OVERSTATED) |
| **Diff tracking between passes** | Log what changed between the original capsule and the revised version. This serves two purposes: (1) developer insight into whether the editor is making targeted fixes or wholesale rewrites, (2) regression detection if a fix introduces new problems. Simple implementation: character-level or sentence-level diff stored in metadata. | MEDIUM | Two capsule strings to diff, a diff utility |
| **Partial convergence acceptance** | After N iterations, if only low-severity warnings remain (e.g., OVERSTATED but no DIRECTION ERROR or UNSUPPORTED), accept the capsule as "good enough." This prevents burning retries on subjective disagreements between the anchor checker and editor. | LOW | Warning-type prioritization (above) |
| **Anchor check caching on CLEAN** | If the first anchor check returns CLEAN, skip the loop entirely with zero overhead. Currently this is trivially true (break on CLEAN), but explicitly short-circuiting before any revision prompt construction saves a few milliseconds and keeps the code path clear. | LOW | Convergence detection |
| **Per-warning fix verification** | After a revision, check whether each specific warning from the previous pass was addressed. If the editor fixed 2 of 3 warnings but one persists, only pass the remaining warning back. This prevents the editor from oscillating (fixing A introduces B, fixing B reintroduces A). | HIGH | Semantic comparison between warning sets across iterations, anchor re-check |

## Anti-Features

Features that seem obviously good but cause real problems in LLM reflection loops. These are drawn from known failure modes in self-refinement systems.

| Anti-Feature | Why Tempting | Why Problematic | What to Do Instead |
|--------------|--------------|-----------------|-------------------|
| **Unlimited iteration** | "Just keep going until it's perfect." | LLMs do not monotonically improve with more passes. After 2-3 revisions, quality plateaus or degrades. Each pass costs ~5-15s and API tokens. Diminishing returns hit fast. Research consistently shows that self-refinement beyond 2-3 rounds rarely improves and often worsens output. | Hard cap of 3 iterations (initial write + 2 revisions). Make this configurable but default to 3. |
| **Full rewrite on each revision** | Simpler to implement -- just re-run the editor with the same initial prompt plus "also fix these issues." | The editor loses good material. Prose quality is non-monotonic: a capsule that nailed paragraph 1 but fumbled paragraph 2 becomes mediocre in both paragraphs after a full rewrite. The "fix" for one warning introduces new problems. This is the single most common failure mode in LLM reflection loops. | Targeted revision prompt: "Here is the capsule. Here are the problems. Revise the affected sections. Preserve everything else." |
| **LLM-as-judge with no ground truth** | "Let the anchor checker grade on a 1-10 scale and iterate until score > 8." | The anchor checker was designed for binary verification against the synthesis (ground truth). Expanding it to subjective quality scoring removes its grounding. An LLM judging another LLM's prose without factual anchoring produces noise, not signal. The anchor's power comes from comparing capsule claims against synthesis facts. | Keep the anchor checker's role narrow: factual fidelity only. Do not expand it to style or quality grading. |
| **Self-refinement without external anchor** | "Let the editor critique its own work." | Self-critique without external reference is unreliable. The same model that wrote the error will rationalize it. The actor-critic pattern works because the critic has different information (the synthesis) and different instructions (verify facts, not write prose). Merging the two roles defeats the purpose. | Keep editor and anchor as separate agents with separate prompts. The anchor's value is that it checks against the synthesis, not against its own aesthetic preferences. |
| **Expanding anchor scope per iteration** | "On retry 2, also check for style violations and metric-count limits." | Moving the goalposts guarantees non-convergence. If the anchor checks more things on pass 2 than pass 1, the editor can never satisfy an expanding set of requirements. Each iteration should check the SAME criteria. | Anchor prompt is identical on every pass. The only thing that changes is the capsule being checked. |
| **Streaming the revision passes** | "Stream every revision to stdout so the user sees progress." | The user sees a capsule, then sees it change, then change again. This is confusing and erodes trust. The revision loop is an internal quality mechanism. The user should see the final capsule (streamed) and a count of how many passes it took (on stderr). | Stream only the final accepted capsule. Log iteration count and surviving warnings to stderr. |
| **Temperature escalation across retries** | "If the first revision didn't fix it, increase temperature for more creative solutions." | Higher temperature increases randomness, not insight. A factual error (`[DIRECTION ERROR]`) is not fixed by creativity -- it's fixed by the editor reading the anchor feedback carefully. Temperature escalation introduces new hallucinations. | Keep temperature constant across all passes. The revision prompt, not the temperature, should drive different output. |

## Feature Dependencies

```
[Iteration cap] ──────────────────────┐
                                       ├── Required by: [Loop orchestration in generate_report_streaming]
[Convergence detection (CLEAN exit)] ──┘
        |
        v
[Warning pass-through to editor] ── Required for meaningful revision
        |
        v
[Editor revision prompt] ── The new prompt text that makes revision work
        |
        ├──> [Targeted revision] ── Enhancement: fix-only vs full rewrite
        |
        ├──> [Diff tracking] ── Enhancement: observe what changed
        |
        └──> [Per-warning fix verification] ── Enhancement: track individual fixes

[Warning-type prioritization] ──> [Partial convergence acceptance]
        |
        └── Depends on: existing anchor warning categories (already structured)

[Surviving warnings surfaced] ── Independent, already partially built (stderr output exists)

[Iteration metadata tracking] ── Independent, small addition to ReportResult
```

### Dependency Notes

- **Loop orchestration is the foundation:** The while-loop with iteration cap and CLEAN break is the skeleton everything else hangs on. Build this first.
- **Revision prompt is the critical design decision:** The quality of the entire reflection loop depends on how well the revision prompt instructs the editor. This is the piece that requires the most iteration and testing.
- **Targeted revision and diff tracking are independent enhancements** that can be added after the basic loop works. They improve quality but are not required for the loop to function.
- **Warning-type prioritization enables partial convergence** but also has standalone value for the stderr output (showing severity to the user).
- **Downstream phases (hook writer, fantasy analyst) are unaffected** -- they continue to derive from the final capsule. The loop is internal to the editor-anchor interaction.

## MVP Recommendation

### v1.3 Launch (Reflection Loop MVP)

Build the loop with table stakes features. This is the minimum that makes the loop functional and safe.

1. **Iteration cap** -- Hard ceiling of 3 total passes (initial + 2 revisions), configurable via constant
2. **Convergence detection** -- Break on CLEAN
3. **Warning pass-through** -- Inject anchor warnings into editor revision message
4. **Editor revision prompt** -- New prompt text for revision passes (distinct from initial editor prompt)
5. **Surviving warnings surfaced** -- Existing stderr output, now reports "after N iterations"
6. **Iteration metadata** -- Add `anchor_iterations: int` and `anchor_converged: bool` to ReportResult

### v1.3 Fast-Follow (Quality Improvements)

Add after the basic loop is validated against real pitcher data.

7. **Targeted revision prompt** -- Refine the revision prompt to say "fix only the flagged issues"
8. **Warning-type prioritization** -- Categorize warnings by severity, accept partial convergence for low-severity-only
9. **Diff tracking** -- Log sentence-level changes between passes for developer insight

### Defer (v1.4+)

10. **Per-warning fix verification** -- Track which specific warnings were resolved per pass. High complexity, requires semantic matching between warning sets.

## Complexity Assessment

| Feature | Lines of Code (Est.) | LLM Calls Added | Risk |
|---------|---------------------|------------------|------|
| Iteration cap + convergence | ~15 (while loop + break) | 0 extra when CLEAN on first pass | Very low -- pure control flow |
| Warning pass-through | ~5 (string formatting) | 0 | Very low |
| Editor revision prompt | ~30 (new prompt constant + message builder) | 0 (replaces existing editor call) | Medium -- prompt quality is testable only by running the pipeline |
| Surviving warnings + metadata | ~10 (fields + stderr print) | 0 | Very low |
| Loop orchestration total | ~60 lines changed in report.py | 0-4 extra LLM calls worst case (2 editor + 2 anchor retries) | Low overall, prompt quality is main risk |

**Cost impact:** Best case (CLEAN on first pass): zero additional LLM calls. Worst case (2 revisions): 4 additional calls (2 editor + 2 anchor). At ~5s per call, worst case adds ~20s. Average case with well-tuned prompts: 0-2 additional calls.

## Sources

- Training data on LLM self-refinement patterns (Madaan et al. "Self-Refine" 2023, Shinn et al. "Reflexion" 2023, Pan et al. "Automatically Correcting Large Language Models" 2024) -- LOW confidence on specific details, HIGH confidence on general patterns
- Direct inspection of existing report.py anchor check implementation
- Direct inspection of pydantic-ai retry mechanisms (structural retries, not semantic -- confirms custom loop is needed)
- Project-specific context from PROJECT.md and existing pipeline architecture

---
*Feature research for: Editor-Anchor Reflection Loop (v1.3 milestone)*
*Researched: 2026-03-27*
