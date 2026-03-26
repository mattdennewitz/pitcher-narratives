# Pitcher Narratives

## What This Is

A CLI tool that generates LLM-written scouting reports for MLB pitchers. Given a pitcher ID, it assembles pitch-level Statcast data and pre-computed Pitching+ aggregations, computes deltas and trend strings across a configurable lookback window, and streams a scout-voice narrative report from Claude via pydantic-ai.

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

### Active

(None — v1.0 shipped. Define next milestone requirements via `/gsd:new-milestone`.)

### Out of Scope

- Web UI or API — this is a CLI script
- Historical season-over-season comparisons — single-season 2026 data only
- Batter-side analysis — pitcher-focused reports only
- Real-time data ingestion — works against static parquet/CSV files
- Team-level reports — individual pitcher reports only
- Rich terminal formatting — plain text output for v1.0

## Context

### Current State (v1.0 shipped)

3,270 LOC Python across 4 modules + 4 test files. 104 tests passing.

**Modules:** data.py (loading/classification), engine.py (computation), context.py (Pydantic assembly), report.py (LLM generation), main.py (CLI entry point).

**Tech stack:** Python 3.14, polars 1.39, pydantic-ai 1.72, Claude Sonnet 4.6.

### Data Sources

**Statcast parquet** (`statcast_2026.parquet`): 145K pitch-level rows, 114 columns. Standard Baseball Savant schema.

**Pitching+ aggregations** (`aggs/`): Pre-computed P+, S+, L+ metrics at 8 grains (season, appearance, pitch type, platoon, and combinations).

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
*Last updated: 2026-03-26 after v1.0 milestone*
