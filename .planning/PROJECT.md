# Pitcher Narratives

## What This Is

A CLI tool that generates LLM-written scouting reports for MLB pitchers and answers natural-language questions about their performance. Given a pitcher ID or name, it assembles pitch-level Statcast data and pre-computed Pitching+ aggregations, computes deltas and trend strings across a configurable lookback window, and runs a multi-agent specialist pipeline (5 specialist micro-analysts → per-specialist audit → writer → anchor check). Also provides a tool-calling analyst agent for focused Q&A and a standalone scout CLI that scores appearances for interestingness.

## Core Value

The report must read like a scout wrote it — surfacing *changes, adaptations, and execution trends* rather than reciting numbers. The LLM gets pre-computed deltas and baselines so it can focus on insight, not arithmetic.

## Requirements

### Validated

- CLI accepts pitcher ID and optional lookback window (`-p pitcherid -w 10`) — v1.0
- Auto-detects starter vs. reliever per appearance — v1.0
- Assembles structured context from Statcast parquet + Pitching+ CSV aggregations — v1.0
- Computes deltas and qualitative trend strings for fastball quality & velo trends — v1.0
- Covers arsenal analysis (usage rate deltas, platoon mix shifts, first-pitch weaponry) — v1.0
- Covers execution metrics (CSW%, zone/chase rate, xWhiff/xSwing, xRV100) — v1.0
- Covers contextual factors (rest days, innings depth, consecutive days pitched) — v1.0
- Pydantic PitcherContext model assembles all outputs into prompt-ready document (~544 tokens) — v1.0
- Adapts report structure based on starter vs. reliever role (SP/RP guidance in prompt) — v1.0
- Generates scout-voice prose via Claude with anti-recitation prompting — v1.0
- Uses Claude via pydantic-ai as the LLM backend — v1.0
- Multi-provider support (OpenAI, Claude, Gemini) with configurable thinking levels — v1.1
- Five-phase pipeline: synthesizer → editor → anchor check → hook writer → fantasy analyst — v1.2
- Pragmatic/cautious voice with intent-based reasoning, plausibility filters, and 3-metric cap — v1.1
- Capsule-driven downstream: Phases 3/4 derive from editor capsule, not raw synthesis — v1.1
- Portfolio audit: synthesizer cross-references S+/L+ with platoon data for development opportunities — v1.1
- Anchor check (Phase 2.5) verifies narrative fidelity to synthesis — v1.2
- Scout CLI scores appearances across 9 signals without LLM calls — v1.2
- LLM curator selects 3-5 most compelling stories with signal hierarchy and rejection explanations — v1.2

- Structured AnchorResult/AnchorWarning types with typed warning categories — v1.3
- Editor-anchor reflection loop self-corrects capsule (up to 2 revision passes) — v1.3
- Revision prompt builder produces targeted fix instructions from anchor warnings — v1.3
- Surviving warnings surfaced to stderr in same format as anchor output — v1.3
- Downstream phases (hook, fantasy) receive final revised capsule — v1.3
- ReportResult.revision_count tracks iteration history — v1.3

- Fuzzy pitcher name resolution via rapidfuzz with 5-tier pipeline (exact, last-name, fuzzy-last, fuzzy-full, not-found) — v1.4
- Tool-calling analyst agent with get_pitcher_summary and get_pitch_detail tools, grounded exclusively in provided data — v1.4
- Static PITCH_TYPE_MAP covering all 12 Statcast codes + 26 common synonyms — v1.4
- `pitcher-ask` CLI entry point composing name resolver and analyst agent into natural-language Q&A — v1.4
- Disambiguation UX: numbered candidate list for ambiguous names — v1.4
- Streaming Q&A output via run_stream_sync matching report pipeline UX — v1.4

- Intermediate probabilities (P and S variants) loaded from pitchingplus aggregation CSVs — v1.5
- Component attribution: 13-outcome xRV decomposition per pitch type — v1.5
- Analyst tools return intermediates, P/S comparisons, and attribution alongside plus scores — v1.5
- Analyst prompt reasons from model internals (physical profile → stuff predictions → grade) — v1.5
- Per-pitch-type velocity and movement (pfx_x/pfx_z) in arsenal data for Stuff+ explanation — v1.5
- Stuff explainer phase replaces social hook: traces S+ grades to physical characteristics — v1.5

- Multi-agent specialist pipeline with 5 parallel micro-analysts (stuff, location, run value, trends, game shape) — v1.6
- Per-specialist audit loop: independent data auditor verifies each specialist before writer sees output — v1.6
- Anti-hallucination guardrails: NORMAL/OUTLIER tags, directional consistency, temperature splitting — v1.6
- Writer agent composes unified capsule from clean specialist outputs — v1.6
- Executive summary agent runs concurrently with writer — v1.6
- Pipeline Q&A mode via `pitcher-ask --pipeline` with audit flags and stuff summary — v1.6
- Architecture cleanup: config.py, anchor.py modules; public pipeline API; consolidated baseline logic — v1.6

- Game type filtering: allowlist (R/F/D/L/W) applied at load time, excluding spring training and exhibition data — v1.7
- Year-parameterized paths via `_YEARS` constant, no hardcoded year prefixes — v1.7
- Multi-year parquet and CSV loading across all configured years with graceful missing-file handling — v1.7
- Per-season baselines (not cross-season averaged) via pitcher+season grouping — v1.7
- All data access centralized through data.py: zero bypass reads in engine.py, resolver.py, scout.py — v1.7
- Resolver builds pitcher name table from all available years — v1.7

- Prior-season baselines exposed on PitcherData (current + N-1 season) — v1.8
- YoY deltas for velocity, P+, S+, L+ with qualitative language consistency — v1.8
- Arsenal trend detection: added/dropped/continued pitches with per-pitch-type YoY deltas — v1.8
- Year-over-Year prompt section with single-season omission — v1.8
- Specialist pipeline agents receive cross-season data — v1.8

- ✓ report.py (old single-agent pipeline) deleted — v1.9
- ✓ test_report.py deleted — v1.9
- ✓ --pipeline flag removed from both CLIs — pipeline.py is now the default and only path — v1.9
- ✓ HallucinationReport and check_hallucinated_metrics relocated to pipeline.py — v1.9
- ✓ anchor.py remains intact (shared by pipeline.py) — v1.9
- ✓ All CLI features (--verbose, --print-prompts, automatic hallucination check) route through pipeline.py — v1.9

### Active

No active requirements — awaiting next milestone definition.

## Current State (v1.9 shipped)

v1.9 Pipeline Consolidation shipped 2026-04-10. The old single-agent reporting path (report.py, ~850 lines) and its tests (test_report.py, ~635 lines) have been fully removed. The multi-agent specialist pipeline (pipeline.py) is now the sole report generation path.

**What shipped:**
- Deleted report.py and test_report.py (~1,485 lines removed)
- Relocated hallucination guard (HallucinationReport, check_hallucinated_metrics, regex patterns) to pipeline.py
- Rewrote cli.py and ask_cli.py to use pipeline.py exclusively, removing the `--pipeline` flag
- Created standalone tests/test_hallucination_guard.py with 17 passing tests
- Cleaned stale report.py references from anchor.py and config.py docstrings
- Verified all import chains intact, zero orphaned references

**Pre-existing issues carried forward** (not caused by v1.9): tests/test_analyst.py has a broken import (_analyst_agent) and tests/test_pipeline.py has one pydantic-ai TestModel assertion error. Both predate v1.9.

### Out of Scope

- Web UI or API — this is a CLI script
- Batter-side analysis — pitcher-focused reports only
- Real-time data ingestion — works against static parquet/CSV files
- Team-level reports — individual pitcher reports only
- Rich terminal formatting — plain text output for v1.0
- Cross-pitcher comparison in Q&A — needs new data scanning layer, deferred to v1.7+
- Multi-turn conversational Q&A — session state management, different UX paradigm, deferred to v1.7+
- SQL generation from natural language — existing engine computes meaningful derived metrics

## Context

### Codebase (v1.8)

**Modules:** config.py (shared constants), anchor.py (anchor quality gate, shared with pipeline.py), data.py (loading with multi-year support, game type filtering, prior-season baselines), engine.py (computation — including CrossSeasonSummary, ArsenalTrends), context.py (assembly with YoY rendering), pipeline.py (sole report generation path — multi-agent specialist pipeline + audit loop + hallucination guard), scout.py (appearance scoring via data.py), curator.py (LLM curation), cli.py (narrative CLI, pipeline-only), scout_cli.py (scout CLI), resolver.py (fuzzy name resolution via data.py), analyst.py (tool-calling Q&A agent), ask_cli.py (Q&A CLI, pipeline-only).

**Tech stack:** Python 3.14, polars 1.39, pydantic-ai 1.72, rapidfuzz 3.14, nameparser 1.1, multi-provider (OpenAI gpt-5.4-mini, Claude Sonnet 4.6, Gemini 3.1 Pro).
**LOC:** ~9,100 source + ~4,500 test

**Key v1.7 additions:** Game type filtering at load time (allowlist: R/F/D/L/W). Multi-year data loading via `_YEARS = [2025, 2026]` with graceful missing-file handling. Per-season baselines (group by pitcher+season). All data access centralized through data.py — zero direct `read_csv`/`read_parquet` calls outside data.py. New league-wide loading functions: `load_all_statcast()` and `load_full_agg()`. 179 tests passing across data/engine/resolver modules.

### Data Sources

**Statcast parquet** (`statcast_2025.parquet`, `statcast_2026.parquet`): Pitch-level rows, 114 columns. Standard Baseball Savant schema. game_type column distinguishes regular season ("R"), spring training ("S"), and exhibition ("E"). 75.9% of 2026 data is spring training — filtering is correctness-critical.

**Pitching+ aggregations** (`aggs/`): Pre-computed P+, S+, L+ metrics at 8 grains (season, appearance, pitch type, platoon, and combinations). Year-prefixed CSV files (e.g., `2025-pitcher.csv`, `2026-pitcher.csv`). All contain only game_type "R" rows.

### Report Philosophy

1. **Deltas over absolutes**: pre-computed qualitative trend strings
2. **Scout framing**: fastball quality as foundation, arsenal adjustments, execution, context
3. **Role-adaptive**: starters get pitch mix depth and stamina; relievers get workload and short-window focus

## Constraints

- **Tech stack**: Python, polars, pydantic-ai, Claude
- **Data format**: Static parquet + CSV files, no live API calls
- **Python version**: 3.14+

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Claude Sonnet 4.6 as LLM backend | Good quality/cost for narrative generation | ✓ Good |
| Polars for data processing | Fast columnar operations on 145K rows | ✓ Good |
| Lookback window in days (not appearances) | More intuitive for workload context | ✓ Good |
| Pre-compute deltas in Python, not LLM | LLMs write better insight when freed from arithmetic | ✓ Good |
| Pydantic schema for LLM input | Type-safe structured context, self-documenting | ✓ Good |
| str output type (not structured) | Free-form prose; structured output constrains narrative quality | ✓ Good |
| First inning = 1 for SP classification | Simple, accurate, handles swingmen per-appearance | ✓ Good |
| n_pitches-weighted averaging for baselines | Correctly handles multi-game-type rows | ✓ Good |
| Five-phase pipeline with anchor check | Separate fact-checker catches signal drift the editor misses | ✓ Good |
| Capsule-driven downstream phases | Hook/fantasy inherit editor's plausibility filters | ✓ Good |
| Separate scout CLI (no LLM) | Cheap triage before expensive narrative generation | ✓ Good |
| Pragmatic voice over skeptical | Reads like a scout, not a critic or a cheerleader | ✓ Good |
| Plain while-loop over pydantic-graph | Async-only graph is overkill for 2-node cycle | ✓ Good |
| Fresh prompt per revision (no history) | Avoids anchoring bias and token bloat | ✓ Good |
| MAX_REVISIONS=2 (3 total passes) | Balances cost vs. quality; configurable constant | ✓ Good |
| Streaming only on final capsule | Revision passes silent; no confusing duplicate output | ✓ Good |
| Tool-calling agent for Q&A (not pre-assembled context) | Agent chooses which tools to call based on question; extensible to cross-pitcher tools in v1.5 | ✓ Good |
| rapidfuzz for name resolution | Deterministic, fast (<5ms), no LLM cost; 70 score cutoff balances typo tolerance vs false positives | ✓ Good |
| `instructions` param over `system_prompt` | Excludes from message history; multi-turn Q&A a future freebie | ✓ Good |
| Separate CLI per concern (pitcher-ask) | Matches pitcher-narratives and pitcher-scout pattern; no subcommand pollution | ✓ Good |
| Capitalization heuristic for name extraction | Prevents common words like "about" from fuzzy-matching pitcher names like "Abbott" | ✓ Good |
| 5 parallel specialist agents over monolithic synthesizer | Each specialist focuses on one analytical lens; writer composes rather than analyzing | ✓ Good |
| Per-specialist audit before writer | Catches hallucinations early, before they compound in the writer's capsule | ✓ Good |
| Temperature splitting (0.3/0.7/0.1) | Specialists need precision, writer needs voice, auditor/anchor need determinism | ✓ Good |
| NORMAL/OUTLIER tags on all metrics | Prevents specialists from calling normal values "notable" | ✓ Good |
| Game Shape specialist (5th agent) | TTO degradation and within-game mix shifts were missing from 4-agent prototype | ✓ Good |
| Prototype Phase 15 without GSD plans | Experimental architecture; iteration faster than upfront planning | ✓ Good |
| Allowlist game types (is_in) over exclusion list | Unknown game types default to excluded; safer than denylist | ✓ Good |
| _YEARS constant over filesystem auto-discovery | Explicit control, sufficient for 2 years; auto-discovery is premature | ✓ Good |
| Per-season baseline grouping | Prevents cross-season averaging artifacts (e.g., season=2025.375) | ✓ Good |
| filter_game_type at load time (not computation) | Data flows clean from the gate; no unfiltered data escapes | ✓ Good |
| Centralize all data access through data.py | Game type filtering + multi-year applied consistently everywhere | ✓ Good |
| Relocate hallucination guard to pipeline.py (not separate module) | Single consumer, simpler import graph, co-located with its sole user | ✓ Good |
| Delete report.py entirely (not deprecate) | pipeline.py is strictly better; no migration path needed; removal simplifies the codebase | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-10 after v1.9 milestone shipped — Pipeline Consolidation*
