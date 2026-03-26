# Project Research Summary

**Project:** pitcher-narratives
**Domain:** LLM-powered pitcher scouting report CLI (Statcast + Pitching+ data to narrative)
**Researched:** 2026-03-26
**Confidence:** HIGH

## Executive Summary

pitcher-narratives is a Python CLI tool that transforms raw MLB Statcast pitch-level data and Pitching+ aggregation metrics into scout-voice narrative reports using Claude. The expert approach for this class of tool -- data-to-narrative via LLM -- centers on one non-negotiable principle: **pre-compute everything, let the LLM write insight**. The Python layer (polars) must compute all deltas, trends, baselines, and qualitative labels before the LLM sees any data. The LLM receives pre-digested statements like "Slider usage: 32% (+12pp, Significant Increase from baseline)" and writes prose around them. This architecture is well-documented across multiple sources and is the single most important design decision for report quality.

The recommended stack is lean and already partially constrained by the existing pyproject.toml: Python 3.14, polars for data processing, pydantic-ai with Claude Sonnet 4.6 for report generation, and rich for terminal rendering. The architecture follows a strict pipeline -- Loader, Delta Engine, Schema Assembler, Report Generator, Output Formatter -- where each component has clear boundaries and no component crosses its lane. Pydantic models define the data contract between Python computation and LLM input. The LLM output should be plain text (`output_type=str`), not structured Pydantic output, because narrative prose quality degrades significantly when forced into JSON field slots.

The primary risks are: (1) the LLM reciting statistics instead of generating insight -- mitigated by aggressive preprocessing and anti-recitation prompt design, (2) hallucinated trends and fabricated causal claims -- mitigated by pre-computing ALL trend directions in Python so the LLM never does math, and (3) context window bloat from raw data dumps -- mitigated by targeting under 2,000 tokens for the data context through curated summaries rather than DataFrame dumps. A secondary risk is polars 3.14 compatibility (not officially classified yet), which should be verified as the very first development task.

## Key Findings

### Recommended Stack

The stack is compact with no unnecessary abstractions. All core dependencies are already declared in pyproject.toml. No framework overhead (no LangChain, no Jinja templating, no pandas).

**Core technologies:**
- **polars >=1.39.3**: Columnar data engine -- handles 145K-row Statcast parquet with lazy evaluation and predicate pushdown; 5-30x faster than pandas for this workload
- **pydantic-ai >=1.72.0**: LLM agent framework -- type-safe structured input via dependency injection, dynamic instructions via `@agent.instructions`, native Anthropic support
- **rich >=14.3.3**: Terminal rendering -- styled markdown prose sections and formatted data tables side-by-side
- **Claude Sonnet 4.6**: LLM model -- near-Opus quality for analytical writing at 5x lower cost; configured via `anthropic:claude-sonnet-4-6` model string
- **argparse (stdlib)**: CLI -- two arguments (`-p pitcher_id`, `-w lookback_window`) do not justify pulling in typer/click

**Critical version note:** polars does not officially list Python 3.14 support in PyPI classifiers (stops at 3.13). The project requires Python >=3.14. This likely works but must be verified before any other development.

### Expected Features

**Must have (table stakes -- v1):**
- Starter/reliever auto-detection (per appearance, not per pitcher) -- structural foundation
- Appearance-level performance summary -- report anchor
- Fastball quality summary (velo baseline, trend, within-game variance, shape) -- most important analysis
- Arsenal inventory with usage rate deltas (recent vs. season baseline) -- second most important
- P+/S+/L+ scores per pitch type at season and appearance grain -- the project's data advantage
- Platoon split awareness -- essential for arsenal completeness
- Trend context framing (deltas with qualitative strings) -- what makes it a scout report, not a stat dump
- Data tables alongside prose -- output format requirement

**Should have (differentiators -- v1.x):**
- Execution metrics (CSW%, zone rate, chase rate)
- Within-game velocity arc narrative
- Movement shape change detection
- xRV100-driven pitch effectiveness ranking
- Qualitative scout-language vocabulary mapping
- Rest and workload context for relievers

**Defer (v2+):**
- Count-state tendencies (HIGH complexity, requires Statcast count reconstruction)
- Times through order analysis (HIGH complexity, requires batting order reconstruction)
- Key matchup highlights (HIGH complexity, requires batter identification + WPA)
- Pitch-level P+/S+/L+ outlier detection (queries 143K-row all_pitches file)

### Architecture Approach

The system is a synchronous five-stage pipeline: CLI parses args, Loader reads and filters data, Delta Engine computes baselines/trends/qualitative labels, Schema Assembler packages computed data into layered Pydantic models with `to_prompt()` methods, and Report Generator sends the context to Claude via pydantic-ai dependency injection and returns prose. Each engine module (classify, fastball, arsenal, execution, context) maps to one section of the scouting report and is a pure function: DataFrames in, Pydantic models out.

**Major components:**
1. **Data Loader** (`loader.py`) -- reads parquet + CSVs, filters to target pitcher, returns typed DataFrames
2. **Delta Engine** (`engine/`) -- five modules computing baselines, deltas, and qualitative trend strings; pure polars, no LLM
3. **Schema Assembler** (`models/context.py`) -- layered Pydantic models with `to_prompt()` that render the LLM's input context
4. **Report Generator** (`agent.py`) -- pydantic-ai Agent with `output_type=str`, deps injection, dynamic instructions
5. **Output Formatter** (`formatting.py`) -- rich Console for terminal, plain text for file output

**Key architectural decision:** Use `output_type=str` (free-form prose), NOT a structured Pydantic output model. All structure lives in the INPUT schemas. The output is free-form narrative that reads like a human scout wrote it. This is explicitly called out as a critical anti-pattern to avoid (structured output for prose generation) in both the architecture and pitfalls research.

### Critical Pitfalls

1. **Number recitation instead of insight** -- Pre-compute qualitative trend strings in Python; add anti-recitation instructions and few-shot exemplars to the system prompt; omit unchanged metrics entirely from context
2. **Hallucinated trends and fabricated causation** -- Pre-compute ALL trend directions in polars so the LLM never does arithmetic; add data grounding constraints ("every claim must reference a provided metric"); zero tolerance for trends not in input
3. **Context window bloat** -- Target under 2,000 tokens for data context; pass 20-40 pre-computed insights, not 1,000 rows; use markdown tables (34-38% more token-efficient than JSON); filter Statcast to ~15-20 of 114 columns
4. **Starter/reliever detection edge cases** -- Classify each APPEARANCE, not the pitcher; 25% of pitchers have dual roles; check first-inning entry rather than innings thresholds; handle openers explicitly
5. **Statcast data quality silent failures** -- Audit null rates per column before building pipeline; set minimum pitch count thresholds for per-type analysis; normalize pitch type naming ("FF" vs "4-Seam Fastball"); handle first-appearance cold start (no baseline)

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Data Foundation and Pipeline Skeleton

**Rationale:** Every other component depends on the data layer being correct. The architecture research identifies models and loader as Phase 1 dependencies. The pitfalls research identifies data quality, null handling, and starter/reliever classification as Phase 1 concerns. Nothing can be tested without data flowing.
**Delivers:** Working data pipeline from parquet/CSV to filtered, validated, pitcher-scoped DataFrames; starter/reliever classification; project skeleton with module structure
**Addresses features:** Starter/reliever detection, appearance-level performance summary (data layer)
**Avoids pitfalls:** Statcast data quality silent failures (Pitfall 6), starter/reliever edge cases (Pitfall 5)
**Stack elements:** polars, Pydantic models (`models/context.py`), argparse CLI skeleton
**Notes:** Verify polars 3.14 compatibility as the FIRST task. Build data quality assertions before any computation.

### Phase 2: Delta Engine and Context Assembly

**Rationale:** The delta computation layer is the "most important engineering phase" per pitfalls research. It is the primary defense against the top two pitfalls (number recitation and hallucinated trends). The architecture research places all engine modules in Phase 2 and notes they are parallelizable (no inter-dependencies).
**Delivers:** Complete preprocessing pipeline producing the `PitcherContext` Pydantic model with `to_prompt()` output; all baselines, deltas, qualitative trend strings computed in Python
**Addresses features:** Fastball quality summary, arsenal inventory + usage deltas, P+/S+/L+ scores, platoon split awareness, trend context framing
**Avoids pitfalls:** Number recitation (Pitfall 1), hallucinated trends (Pitfall 2), context window bloat (Pitfall 4)
**Stack elements:** polars (aggregation/delta computation), Pydantic models (layered context hierarchy)
**Notes:** Target under 2,000 tokens for the assembled context document. This phase is testable WITHOUT the LLM -- validate context output independently.

### Phase 3: LLM Agent and Report Generation

**Rationale:** The agent depends on finalized PitcherContext shape from Phase 2. Prompt design is the secondary defense against recitation and hallucination. The structured vs. unstructured output decision must be made here (answer: `output_type=str`).
**Delivers:** Working end-to-end report generation; pydantic-ai Agent with system prompt, dependency injection, and Claude API integration; rich terminal output
**Addresses features:** Data tables alongside prose, appearance-level performance summary (complete)
**Avoids pitfalls:** Over-structured output killing prose quality (Pitfall 3), number recitation (prompt-level defense)
**Stack elements:** pydantic-ai, Claude Sonnet 4.6, rich, python-dotenv
**Notes:** Invest heavily in the system prompt -- include anti-recitation instructions and few-shot exemplar of good scouting prose. Use `run_sync()` (not streaming) for structured output validation.

### Phase 4: Report Enhancement and Polish

**Rationale:** With the core pipeline validated, layer in differentiator features that elevate report quality. These features follow the same engine pattern (DataFrames in, Pydantic models out) and slot into the existing context hierarchy.
**Delivers:** Execution metrics, velocity arc narrative, movement shape detection, xRV100 rankings, scout-language vocabulary, reliever workload context
**Addresses features:** All "should have" / v1.x features from FEATURES.md
**Avoids pitfalls:** Empty report sections for relievers (adapt to actual arsenal); inconsistent report length between roles
**Notes:** Each feature can be added independently. Prioritize execution metrics (CSW/zone/chase) and xRV100 ranking (low cost, high value) first.

### Phase Ordering Rationale

- **Data before computation:** You cannot compute deltas without validated data flowing. Phase 1 must complete before Phase 2 begins.
- **Computation before LLM:** The context assembly quality sets the ceiling for report quality. Phase 2 is testable without the LLM, allowing rapid iteration on data preprocessing.
- **LLM integration is a thin layer:** Phase 3 is intentionally narrow -- it is "just" wiring the agent and writing the prompt. Most engineering effort should go into Phases 1 and 2.
- **Enhancements layer onto a stable foundation:** Phase 4 features follow the exact same engine pattern established in Phase 2. No architectural changes needed.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Delta computation patterns for each report section (fastball, arsenal, execution, context) need specific research into which Statcast columns and P+ metrics map to which narrative insights. The current research identifies the PATTERN but not the exact column-to-insight mappings.
- **Phase 3:** Prompt engineering for scouting voice requires iterative testing. The anti-recitation and data-grounding instructions need empirical tuning. Consider `/gsd:research-phase` for prompt design specifically.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Data loading with polars is well-documented. Starter/reliever classification is a straightforward heuristic. Standard patterns apply.
- **Phase 4:** Enhancement features follow the same engine module pattern from Phase 2. No new architectural decisions.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core libraries verified against official docs and PyPI. Only risk is polars 3.14 compatibility (easily verified). |
| Features | HIGH | Feature landscape sourced from FanGraphs, Baseball Savant, Simple Sabermetrics, and academic literature. Clear prioritization with dependency mapping. |
| Architecture | HIGH | Pipeline pattern well-established for data-to-narrative LLM tools. pydantic-ai patterns verified against official docs. Build order derives directly from component dependencies. |
| Pitfalls | MEDIUM-HIGH | Top pitfalls verified across multiple sources (pydantic-ai issues, Statcast data quality research, LLM hallucination studies). Some pydantic-ai streaming edge cases sourced from GitHub issues rather than official docs. |

**Overall confidence:** HIGH

### Gaps to Address

- **Polars 3.14 compatibility:** Not officially classified. Must verify `import polars` works on Python 3.14 before committing to the Python version requirement. Fallback: pin to Python 3.13.
- **Exact Statcast column selection:** Research identifies that ~15-20 of 114 columns are needed but does not enumerate the exact set. Resolve during Phase 1 implementation by auditing the data files.
- **System prompt tuning:** No exemplar of ideal scouting prose was produced during research. The prompt will need iterative refinement during Phase 3. Consider sourcing 2-3 real scouting report examples for few-shot prompting.
- **pydantic-ai streaming + structured output interaction:** Known bug (issue #3393) with `ModelRetry` in output validators during streaming. Not relevant for MVP (`run_sync` + `output_type=str`) but matters if streaming is added later.
- **First-appearance cold start:** What does the report look like for a pitcher's FIRST appearance of the season (no baseline to compare against)? The preprocessing layer needs a fallback, but this edge case was flagged without a concrete solution.

## Sources

### Primary (HIGH confidence)
- [pydantic-ai official docs](https://ai.pydantic.dev/) -- Agent API, output types, dependency injection, Anthropic provider
- [pydantic-ai Anthropic provider](https://ai.pydantic.dev/models/anthropic/) -- model strings, settings
- [Polars user guide](https://docs.pola.rs/user-guide/) -- lazy API, aggregation, scan_parquet, I/O patterns
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview) -- Claude Sonnet 4.6
- [FanGraphs: PitchingBot Pitch Modeling](https://library.fangraphs.com/pitching/pitchingbot-pitch-modeling-primer/) -- P+/S+/L+ metrics
- [Statcast CSV Documentation](https://baseballsavant.mlb.com/csv-docs) -- data schema, pitch type classifications
- [pydantic-ai GitHub issues #839, #3393, #200](https://github.com/pydantic/pydantic-ai/issues/) -- known limitations and bugs
- [LLM Hallucination Mitigation via Prompt Engineering](https://pmc.ncbi.nlm.nih.gov/articles/PMC12518350/) -- structured prompting reduces hallucination

### Secondary (MEDIUM confidence)
- [Simple Sabermetrics: Elite Opposing Pitcher Scouting Report](https://simplesabermetrics.com/blogs/simple-sabermetrics-blog/how-to-build-an-elite-opposing-pitcher-advanced-scouting-report) -- scouting report structure
- [Imputing Missing Statcast Data](https://www.mattefay.com/imputing-missing-statcast-data) -- null rates and non-random missingness
- [Markdown vs JSON Token Efficiency](https://community.openai.com/t/markdown-is-15-more-token-efficient-than-json/841742) -- formatting efficiency
- [NAACL 2025: LLM-Based Insight Generation](https://aclanthology.org/2025.naacl-long.24.pdf) -- multi-stage LLM patterns
- [pydantic-ai streaming docs (DeepWiki)](https://deepwiki.com/pydantic/pydantic-ai/4.1-streaming-and-real-time-processing) -- run_stream_sync patterns
- [Polars + Python 3.14 (polars-bio)](https://biodatageeks.org/polars-bio/blog/2026/02/14/polars-bio-0230-faster-parsing-and-python-314-support/) -- adjacent project 3.14 confirmation

### Tertiary (LOW confidence)
- None -- all findings corroborated by at least two sources

---
*Research completed: 2026-03-26*
*Ready for roadmap: yes*
