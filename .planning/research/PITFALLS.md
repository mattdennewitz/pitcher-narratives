# Pitfalls Research

**Domain:** LLM-based baseball pitching report generation (Statcast + Pitching+ to narrative)
**Researched:** 2026-03-26
**Confidence:** MEDIUM-HIGH (multiple verified sources; some pydantic-ai patterns from official docs, baseball domain from practitioner experience)

## Critical Pitfalls

### Pitfall 1: Number Recitation Instead of Insight

**What goes wrong:**
The LLM produces reports that mechanically restate every metric fed to it: "His slider usage was 32%. His fastball velocity was 94.2 mph. His CSW% was 31.4%." The output reads like a stat sheet with conjunctions, not a scouting report. This is the single most common failure mode in data-to-narrative LLM systems and the exact opposite of what the project aims to produce.

**Why it happens:**
When the LLM receives structured data, its default behavior is to summarize what it sees. Without explicit guidance to interpret, compare, and editorialize, it treats every field as equally important and dutifully reports each one. The more data columns you pass, the worse this gets -- the model tries to "cover" everything rather than surface what matters.

**How to avoid:**
- Pre-compute qualitative trend strings in Python (e.g., "Sharp Increase", "Stable", "Career Low") rather than passing raw numbers. The LLM should receive "Slider usage: Sharp Increase from 20% baseline to 32%" not just two numbers.
- In the system prompt, explicitly instruct: "Do NOT enumerate statistics. Identify the 2-3 most significant changes and build narrative around them. A stat mentioned without interpretation is a failure."
- Provide exemplar output in the system prompt showing what good scouting prose looks like -- a few-shot example is far more effective than abstract instructions.
- Limit the context to pre-filtered "notable" data points rather than dumping all metrics. If a metric shows no meaningful change, omit it from the context entirely.

**Warning signs:**
- Generated reports mention more than 5-6 distinct statistics per paragraph.
- Every section starts with "His [metric] was [number]" patterns.
- The report length scales linearly with the number of data fields provided.
- No sentences contain causal reasoning or comparative language ("because", "suggesting", "which explains").

**Phase to address:**
Phase 1 (data preprocessing) and Phase 2 (prompt design). The delta computation layer is the primary defense -- if you get this right, the LLM has less opportunity to recite. The prompt design is the secondary defense.

---

### Pitfall 2: Hallucinated Trends and Fabricated Causal Claims

**What goes wrong:**
The LLM invents trends that do not exist in the data ("His velocity has been steadily declining over the past month" when it has been stable) or fabricates causal explanations ("The drop in slider effectiveness is likely due to his recent oblique injury" when no injury information was provided). Research shows hallucination rates on numerical/analytical tasks can reach 53% without mitigation, and early errors compound as the model builds narrative around them.

**Why it happens:**
LLMs are trained to produce coherent, interesting narratives. A flat dataset with no trends is boring, so the model manufactures drama. Claude is particularly prone to constructing plausible-sounding analytical narratives because it writes well -- the hallucinations sound authoritative. Additionally, when the LLM sees correlated metrics, it may infer causation that doesn't exist.

**How to avoid:**
- Pre-compute ALL trend directions in Python. The LLM should never calculate a trend -- it should only narrate a trend that has been computed and labeled for it.
- Include explicit guardrails in the prompt: "Only reference trends and comparisons that are explicitly provided in the data context. Do not infer causation unless the data explicitly supports it. If no notable change exists for a metric, say so briefly or omit it."
- Add a data grounding constraint: "Every claim about a pitcher's performance must reference a specific metric from the provided context."
- For the automated data journalism use case, research shows that multi-stage LLM calls with verification steps (a second pass checking claims against source data) reduce hallucination significantly.

**Warning signs:**
- Reports mention injuries, game situations, or opponent quality not present in the input data.
- Trend language ("steadily", "consistently", "increasingly") appears for metrics that were only provided as point-in-time values.
- The report sounds more interesting and dramatic than the data warrants.
- Numbers in the output don't match numbers in the input (a critical red flag).

**Phase to address:**
Phase 1 (delta computation -- compute trends so the LLM doesn't have to) and Phase 2 (prompt guardrails). Consider a Phase 3 validation step where output claims are spot-checked against input data.

---

### Pitfall 3: Over-Structured Output Killing Prose Quality

**What goes wrong:**
Using pydantic-ai's `output_type` with a deeply nested Pydantic model for the report structure (e.g., `FastballSection`, `ArsenalSection`, `ExecutionSection` each with multiple typed fields) forces the LLM into filling slots rather than writing prose. The output becomes robotic and formulaic because the model is constrained to populate JSON fields rather than compose flowing narrative.

**Why it happens:**
Pydantic-ai's structured output is powerful for extraction tasks where you want typed, validated data. But scouting reports are fundamentally a prose artifact. When you define `fastball_assessment: str` and `arsenal_analysis: str` as separate fields, the model treats each as an independent slot to fill rather than building a cohesive narrative where fastball quality flows into arsenal analysis. The tool calling / JSON schema mechanism used by pydantic-ai for structured output adds overhead that works against natural language fluency.

**How to avoid:**
- Use `str` as the output type (plain text) for the final report generation, not a structured Pydantic model. Let the LLM write prose freely.
- Use structured Pydantic models for the INPUT schema (the data context) but NOT for the output. This gives you type safety on the data pipeline side without constraining narrative quality.
- If you need some structure in the output (e.g., guaranteed section headers), use light constraints in the prompt ("Your report should include sections on: Fastball Quality, Arsenal Adjustments, Execution") rather than a Pydantic output schema.
- Reserve structured output_type for metadata extraction (e.g., a confidence score or a list of key takeaways) as a separate, second agent call -- not the main narrative generation.

**Warning signs:**
- Every report has exactly the same section structure regardless of what the data shows.
- Sections feel disconnected -- the arsenal section doesn't reference the fastball section.
- Prose within structured fields is short and formulaic (because the model is "filling a form").
- Cross-referencing between sections is absent.

**Phase to address:**
Phase 2 (prompt and agent design). This is an architectural decision that must be made before building the agent. Getting this wrong means rewriting the entire output pipeline.

---

### Pitfall 4: Context Window Bloat from Raw Data Dumps

**What goes wrong:**
Passing too much raw data to the LLM -- full pitch-level Statcast rows, all appearance data, all platoon splits -- consumes tokens without improving output quality. A single pitcher's season of pitch-level data (hundreds to thousands of rows with 114 columns) easily exceeds useful context. Even with Claude's large context window, attention degrades on long structured data contexts, and the model "drowns" in numbers it cannot meaningfully process.

**Why it happens:**
The instinct is "more data = better analysis." Developers dump entire DataFrames into prompts thinking the LLM will find the patterns. But LLMs are weak at scanning tabular data for patterns -- they need the patterns pre-identified and the supporting evidence curated. Research shows markdown tables are 34-38% more token-efficient than JSON, but even efficient formatting cannot save a fundamentally oversized context.

**How to avoid:**
- The Python preprocessing layer should be aggressive about summarization. The LLM should receive 20-40 pre-computed insights, not 1,000 rows of raw data.
- Structure the context document as: (1) pitcher identity and role, (2) pre-computed deltas with trend labels, (3) notable outliers only, (4) minimal supporting detail. Target under 2,000 tokens for the data context.
- Use markdown tables (not JSON) for any tabular data that does need to be passed -- 34-38% fewer tokens and better model comprehension.
- Never pass columns the LLM does not need. Of 114 Statcast columns, the report likely needs ~15-20. Filter ruthlessly in the data layer.

**Warning signs:**
- Context token count exceeds 3,000 tokens for a single pitcher report.
- The LLM mentions metrics you did not intend to include (it found them in the raw data dump).
- Response latency is noticeably high.
- Reports cherry-pick random details from the data rather than following the intended analytical structure.

**Phase to address:**
Phase 1 (data preprocessing and context assembly). This is the most important engineering phase. The quality ceiling of the final report is set by the quality of the preprocessed context.

---

### Pitfall 5: Starter/Reliever Detection Edge Cases

**What goes wrong:**
The auto-detection of starter vs. reliever produces incorrect classifications for openers, bulk relievers, swingmen, and pitchers transitioning between roles. 25% of MLB pitchers since 2018 have made both starts and relief appearances. An incorrect classification means the wrong report template is applied -- a reliever gets deep pitch-mix stamina analysis, or a starter gets workload/rest-day analysis that makes no sense for a 6-inning outing.

**Why it happens:**
Binary starter/reliever classification is a solved problem for 75% of pitchers but breaks for the interesting edge cases. Simple heuristics ("started the game = starter") fail for openers. Threshold-based approaches ("more than 4 IP = start") misclassify short starts. Looking at historical role without recency weighting misclassifies pitchers who changed roles mid-season.

**How to avoid:**
- Classify each APPEARANCE, not the pitcher. A pitcher who started 3 games and relieved 20 times should get a starter report for his starts and a reliever report for his relief outings.
- Use the actual appearance data: if the pitcher entered in the first inning and no other pitcher preceded them, it's a start. This is more reliable than innings thresholds.
- For the "opener" case (1-2 innings, entered first, pulled early), consider a third report template or at minimum, note it in the report context.
- For the lookback window analysis, weight recent role more heavily than season totals.

**Warning signs:**
- Reports reference "rest days since last appearance" for a pitcher who just made a start (irrelevant context).
- The report structure feels wrong for what you know about the pitcher.
- Openers get full stamina/innings-depth analysis that reads absurdly.
- A pitcher who was recently converted to the bullpen gets starter-style analysis.

**Phase to address:**
Phase 1 (data processing). Build the classification logic early and test it against known edge cases (openers, swingmen, recent role changes) before the prompt layer depends on it.

---

### Pitfall 6: Statcast Data Quality Silent Failures

**What goes wrong:**
Statcast data contains systematic missing values (10-15% of batted ball events), automated pitch type classifications that get revised retroactively, and null values for tracking data that are NOT random (sensors fail more on steep groundballs and pop-ups). If the preprocessing layer treats nulls as zeros or silently drops rows, computed baselines and deltas will be wrong, and the LLM will narrate incorrect trends.

**Why it happens:**
Developers unfamiliar with Statcast data assume it is clean and complete. Polars will silently propagate nulls through aggregations (e.g., `mean()` ignores nulls by default, which is correct, but `sum()` with nulls may surprise). Pitch type reclassifications mean a "sinker" in March data might become a "four-seam" in June data, breaking pitch-type trend analysis.

**How to avoid:**
- Audit null rates per column before building the preprocessing pipeline. Key columns to check: `pfx_x`, `pfx_z`, `release_speed`, `launch_speed`, `launch_angle`, `pitch_type`.
- Set minimum pitch count thresholds for per-pitch-type analysis. A pitcher who threw 3 changeups in a game should not get changeup trend analysis.
- Handle Pitching+ metric nulls explicitly -- P+/S+/L+ values may be null for pitch types with insufficient sample size.
- Document which Statcast columns are used and their expected null rates. Build assertions into the data layer.

**Warning signs:**
- Deltas that seem implausibly large (often caused by comparing a full-data baseline against a sparse-data recent window).
- Reports making claims about pitch types with very few observations.
- NaN or null values appearing in the LLM context (the model will either ignore them or confabulate).
- Pitch types appearing/disappearing across appearances due to reclassification.

**Phase to address:**
Phase 1 (data ingestion and preprocessing). This must be addressed before any delta computation. Build data quality checks as the first step of the pipeline.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcoding pitch type names | Quick to implement | Breaks when Statcast adds/renames types (e.g., "sweeper" was added in 2023) | Never -- use the data's own pitch type vocabulary |
| Single monolithic prompt | Faster iteration | Cannot independently tune data framing vs. narrative instructions | MVP only -- refactor to layered prompt before v1 |
| String concatenation for context building | Simple to read | Impossible to test, no type safety, easy to introduce formatting bugs | Never -- use Pydantic models for context assembly |
| Skipping min-sample-size checks | More data in reports | Wildly unstable metrics (3-pitch averages treated as meaningful) | Never |
| Raw floats in context (e.g., "0.31428571") | No formatting code needed | LLM wastes tokens parsing precision; output looks robotic | Never -- format to 1 decimal place or use percentages |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pydantic-ai + Claude | Using `output_type=ReportModel` for prose generation | Use `output_type=str` for narrative; use structured types only for metadata extraction |
| pydantic-ai retries | Leaving default `retries=1`, getting `UnexpectedModelBehavior` on validation failures | Set `retries=3` for structured output agents; for `str` output, retries are rarely needed |
| pydantic-ai system_prompt | Putting all context in a static system prompt string | Use `@agent.system_prompt` decorator with `RunContext[Deps]` to inject pitcher-specific data dynamically per run |
| pydantic-ai + streaming | Raising `ModelRetry` in output validators during streaming | Known bug (issue #3393) -- `ModelRetry` in output validators crashes during `stream_output`. Use `run_sync` or `run` for validated output |
| Polars parquet reading | Reading all 114 columns with `pl.read_parquet()` | Use `columns=` parameter to read only needed columns; reduces memory and avoids passing unused data downstream |
| Polars null handling | Assuming `sum()` and `mean()` handle nulls identically | `mean()` ignores nulls (correct), but chained operations like `.fill_null(0).mean()` silently corrupt averages. Be explicit about null strategy per column |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Passing full pitch-level data to LLM | 5-10 second response times, high token costs, degraded output quality | Pre-aggregate in Polars, pass only summary stats and deltas | >500 rows in context |
| Re-reading parquet per CLI invocation | 1-2 second startup latency per report | Load parquet once, filter by pitcher_id; or use LazyFrame with predicate pushdown | First report is slow; noticeable when generating multiple reports |
| Unfiltered Statcast columns in Polars operations | Memory usage spikes, slow joins | Select only needed columns immediately after read | Dataset >500K rows |
| No caching of Pitching+ aggregation joins | Re-joining 8 CSV files per invocation | Join once at startup, store as single DataFrame keyed by pitcher_id | When generating multiple reports in sequence |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Report says nothing when data is boring | User gets a report full of "stable" and "no change" for a pitcher who had an unremarkable outing | Explicitly handle the "nothing interesting happened" case -- note consistency as a finding, highlight the few minor variations, keep it short |
| Generic scouting language | "He showed good command of his fastball" -- could describe any pitcher | Anchor every claim to a specific data point. "His zone rate of 52% (up from 44% baseline) suggests he was attacking the zone more aggressively" |
| Inconsistent report length | Starter reports are 800 words, reliever reports are 150 words | Set target length ranges per role. Relievers need less but should still have substance (300-400 words minimum) |
| No date/game context in report | User cannot tell which appearance the report covers | Always include game date, opponent, and appearance number in the report header |
| Metrics without league context | "His Stuff+ was 115" means nothing without "league average is 100" | Always frame P+/S+/L+ relative to 100 baseline and ideally note what range is "elite" (120+) vs. "below average" (<90) |

## "Looks Done But Isn't" Checklist

- [ ] **Delta computation:** Often missing handling for a pitcher's FIRST appearance (no baseline to compare against) -- verify the pipeline handles the cold-start case with a sensible fallback
- [ ] **Platoon splits:** Often computed but never passed to the LLM -- verify the prompt context includes L/R split deltas when they are meaningful
- [ ] **Rest day calculation:** Often computed as calendar days, but misses doubleheaders and does not account for the reliever appearing in both games -- verify using actual game dates from appearances
- [ ] **Pitch type normalization:** "4-Seam Fastball" vs "FF" vs "Fastball" -- verify a single canonical naming convention is used throughout the pipeline
- [ ] **Within-game velocity trends:** The prompt might include "average velo" but miss the more insightful "first inning velo vs. last inning velo" for starters -- verify the preprocessing captures this
- [ ] **Empty report sections:** A reliever who throws only fastball + slider should not have empty "Changeup Analysis" and "Curveball Analysis" sections -- verify the report adapts to the pitcher's actual arsenal
- [ ] **The "what changed" narrative:** Report covers what IS but not what CHANGED. Verify every section addresses the delta, not just the current state

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Number recitation (Pitfall 1) | LOW | Revise system prompt with explicit anti-recitation instructions and few-shot examples; add qualitative trend strings to preprocessing |
| Hallucinated trends (Pitfall 2) | MEDIUM | Add post-generation validation step comparing output claims to input data; tighten prompt guardrails |
| Over-structured output (Pitfall 3) | HIGH | Requires rewriting the agent from structured output_type to str output; may need to redesign the entire output pipeline |
| Context bloat (Pitfall 4) | MEDIUM | Refactor preprocessing to produce curated summaries instead of data dumps; the LLM call itself does not change |
| Starter/reliever edge cases (Pitfall 5) | LOW | Add per-appearance classification logic; existing reports for correctly classified pitchers remain valid |
| Data quality failures (Pitfall 6) | HIGH | If null handling was wrong from the start, all computed baselines and deltas are suspect; requires revalidation of the entire data pipeline |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Number recitation | Phase 1 (preprocessing) + Phase 2 (prompt) | Read 5 generated reports; count ratio of insight sentences to stat-recitation sentences. Target: >3:1 |
| Hallucinated trends | Phase 1 (delta computation) + Phase 2 (guardrails) | Compare 10 generated claims against source data; zero tolerance for fabricated trends |
| Over-structured output | Phase 2 (agent design) | Read reports aloud; they should flow as natural prose, not read like a filled-in form |
| Context bloat | Phase 1 (context assembly) | Measure token count of assembled context; target <2,000 tokens per pitcher |
| Starter/reliever edge cases | Phase 1 (classification) | Test against known openers, swingmen, and recently-converted pitchers |
| Data quality failures | Phase 1 (data ingestion) | Assert null rates per column; assert min pitch counts before computing per-type metrics |

## Sources

- [Pydantic AI Output Documentation](https://ai.pydantic.dev/output/) -- output modes, validation, streaming behavior (HIGH confidence)
- [Pydantic AI Dependencies Documentation](https://ai.pydantic.dev/dependencies/) -- RunContext, dynamic system prompts (HIGH confidence)
- [Pydantic AI GitHub Issue #839](https://github.com/pydantic/pydantic-ai/issues/839) -- dynamic system prompt refresh limitation (HIGH confidence)
- [Pydantic AI GitHub Issue #3393](https://github.com/pydantic/pydantic-ai/issues/3393) -- ModelRetry crash during streaming (HIGH confidence)
- [Pydantic AI GitHub Issue #200](https://github.com/pydantic/pydantic-ai/issues/200) -- exceeded maximum retries for result validation (HIGH confidence)
- [Imputing Missing Statcast Data](https://www.mattefay.com/imputing-missing-statcast-data) -- 10-15% missing batted ball data, non-random missingness (MEDIUM confidence)
- [Statcast CSV Documentation](https://baseballsavant.mlb.com/csv-docs) -- pitch type reclassification, data revision notices (HIGH confidence)
- [Markdown vs JSON Token Efficiency](https://community.openai.com/t/markdown-is-15-more-token-efficient-than-json/841742) -- 34-38% token savings with markdown (MEDIUM confidence)
- [Which Nested Data Format Do LLMs Understand Best?](https://www.improvingagents.com/blog/best-nested-data-format) -- format comparison for LLM comprehension (MEDIUM confidence)
- [LLM Hallucination Mitigation via Prompt Engineering](https://pmc.ncbi.nlm.nih.gov/articles/PMC12518350/) -- structured prompting reduces hallucination from 53% to 23% (HIGH confidence)
- [NAACL 2025: LLM-Based Insight Generation in Data Analysis](https://aclanthology.org/2025.naacl-long.24.pdf) -- multi-stage LLM calls for insight quality (MEDIUM confidence)
- [Bix Tech: PydanticAI Data Validation Guide](https://bix-tech.com/pydanticai-in-practice-a-complete-guide-to-data-validation-and-quality-control-for-ai-systems/) -- validation patterns and retry strategies (MEDIUM confidence)
- [FanGraphs: Starter/Reliever Classification](https://www.fangraphs.com/leaders/major-league?month=0&pos=all&type=8&stats=rel) -- 25% of pitchers have dual roles since 2018 (HIGH confidence)

---
*Pitfalls research for: LLM-based baseball pitching report generation*
*Researched: 2026-03-26*
