# Pitcher Narratives

## What This Is

A CLI tool that generates LLM-written scouting reports for MLB pitchers. Given a pitcher ID, it assembles pitch-level Statcast data and pre-computed Pitching+ aggregations into a structured context document, then sends it to Claude to produce an insightful narrative assessment of the pitcher's most recent appearance relative to recent trends.

## Core Value

The report must read like a scout wrote it — surfacing *changes, adaptations, and execution trends* rather than reciting numbers. The LLM gets pre-computed deltas and baselines so it can focus on insight, not arithmetic.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] CLI accepts pitcher ID and optional lookback window (`-p pitcherid -w 10`)
- [ ] Auto-detects starter vs. reliever and adapts report structure accordingly
- [ ] Assembles structured context from Statcast parquet + Pitching+ CSV aggregations
- [ ] Computes deltas and qualitative trend strings (not raw numbers) for LLM consumption
- [ ] Generates prose paragraphs with data tables where sensible — exemplary output quality
- [ ] Covers fastball quality & velo trends (baseline vs. recent, within-game variance, shape changes)
- [ ] Covers arsenal analysis (usage rate deltas, platoon mix shifts, first-pitch weaponry)
- [ ] Covers execution metrics (CSW%, zone rate vs. chase rate, secondary P+/S+/L+ scores)
- [ ] Covers contextual factors (rest days for relievers, innings depth for starters)
- [ ] Uses Claude via pydantic-ai as the LLM backend
- [ ] Pydantic models define the schema for structured LLM input

### Out of Scope

- Web UI or API — this is a CLI script
- Historical season-over-season comparisons — single-season 2026 data only
- Batter-side analysis — pitcher-focused reports only
- Real-time data ingestion — works against static parquet/CSV files
- Team-level reports — individual pitcher reports only

## Context

### Data Sources

**Statcast parquet** (`statcast_2026.parquet`): 145K pitch-level rows, 114 columns. Standard Baseball Savant schema with velo, movement (pfx_x/pfx_z), location (plate_x/plate_z), spin, arm angle, bat tracking, expected stats, win expectancy, and game context.

**Pitching+ aggregations** (`aggs/`): Pre-computed P+, S+, L+ metrics at multiple grains:

| File | Grain | Rows | Key Use |
|------|-------|------|---------|
| `2026-pitcher.csv` | Season per pitcher | 1,994 | Season baselines |
| `2026-pitcher_type.csv` | Season per pitcher/pitch type | 8,120 | Per-pitch baselines |
| `2026-pitcher_appearance.csv` | Per game per pitcher | 6,228 | Game-level trends |
| `2026-pitcher_type_appearance.csv` | Per game per pitcher/pitch type | 23,214 | Per-pitch game trends |
| `2026-pitcher_type_platoon.csv` | Season per pitcher/pitch type/platoon | 13,875 | Platoon baselines |
| `2026-pitcher_type_platoon_appearance.csv` | Per game per pitcher/pitch type/platoon | 35,549 | Platoon game trends |
| `2026-all_pitches.csv` | Individual pitch | 143,885 | Pitch-level P+/S+/L+ |
| `2026-team.csv` | Team season | 78 | League context |

**Join key**: `pitcher` (parquet) = `pitcher` (CSVs, also called `player_id` conceptually).

### Pitching+ Model

P+ (Pitching+), S+ (Stuff+), L+ (Location+) are pre-computed metrics scaled to 100 = average. Also includes xRV100 (expected run value per 100 pitches), xWhiff, xSwing, xGOr (ground out rate), xPUr (pop up rate), and 20-80 scouting scale variants (P+2080, S+2080, L+2080).

### Report Philosophy

The LLM prompt schema should emphasize:
1. **Deltas over absolutes**: "Slider Usage: 32%, Baseline: 20%, Trend: High Increase" not just "Slider Usage: 32%"
2. **Qualitative flags**: "Lost 2in of run", "Peak IVB for season", "Abandoned changeup vs LHB"
3. **Scout framing**: Fastball quality as foundation, arsenal adjustments, execution off the fastball, contextual factors

### Starter vs. Reliever Detection

Auto-detect from appearance data. Starters get "last start" analysis with deep pitch mix and stamina trends. Relievers get workload/rest patterns, consecutive days, and shorter-window analysis.

## Constraints

- **Tech stack**: Python, polars, pydantic-ai, Claude — already in pyproject.toml
- **Data format**: Static parquet + CSV files, no live API calls to Baseball Savant
- **Python version**: 3.14+

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Claude as LLM backend | User preference, pydantic-ai integration | -- Pending |
| Polars for data processing | Already in deps, fast for columnar operations on 145K rows | -- Pending |
| Lookback window in days (not appearances) | `-w 10` means last 10 days — more intuitive for understanding workload context | -- Pending |
| Pre-compute deltas in Python, not LLM | LLMs write better insight when freed from arithmetic | -- Pending |
| Pydantic schema for LLM input | Type-safe structured context, self-documenting | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-26 after initialization*
