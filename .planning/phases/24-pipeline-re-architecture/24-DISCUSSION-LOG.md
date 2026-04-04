# Phase 24: Pipeline Re-Architecture - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 24-pipeline-re-architecture
**Areas discussed:** Approach Specialist prompt design, RP Game Shape replacement, Raw data appendix scope, Auditor expansion strategy

---

## Approach Specialist Prompt Design

### Framing Style

| Option | Description | Selected |
|--------|-------------|----------|
| Strategy-first | Lead with approach pattern, then cite data | ✓ |
| Data-first | Lead with largest shifts, then interpret | |
| Matchup-first | Organize by opponent handedness | |

**User's choice:** Strategy-first
**Notes:** Reads like a scout describing how the pitcher thinks.

### Data Connection

| Option | Description | Selected |
|--------|-------------|----------|
| Cross-reference | Connect platoon + count patterns explicitly | ✓ |
| Keep separate | Report independently | |
| Claude's discretion | Let LLM decide | |

**User's choice:** Cross-reference
**Notes:** "When a pitcher throws more X vs lefties AND more X when behind, connect these."

### Output Length

| Option | Description | Selected |
|--------|-------------|----------|
| 2-3 paragraphs | Fixed length like other specialists | |
| Bullet-point format | Structured bullets | |
| Adaptive | Match length to signal density | ✓ |

**User's choice:** Adaptive with anti-padding directive
**Notes:** User provided explicit prompt language: "Match your output length to the density of the data... Under no circumstances should you pad the response with filler or repeat data points to increase length."

### Input Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Notable shifts only | Pre-filtered 10+ pp shifts + baseline mix | ✓ |
| Full appendix tables | All 5 bucket tables | |
| Both, labeled | Shifts as leads, tables as supporting | |

**User's choice:** Notable shifts only
**Notes:** Must include baseline overall pitch mix alongside shifts for significance weighting. "A 12pp shift on a 40% pitch is the headline; on a 5% pitch it's a footnote."

---

## RP Game Shape Replacement

### Replacement Content

| Option | Description | Selected |
|--------|-------------|----------|
| Workload-only stub | Deterministic data block, no LLM call | ✓ |
| Explicit skip note | One-line "not applicable" note | |
| Role-adapted specialist | RP-specific Game Shape prompt | |

**User's choice:** Workload-only stub
**Notes:** Appearance frequency, pitch count trends, rest days from PitcherContext.

### Writer Awareness

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, explicitly | Conditional RP note in writer prompt | ✓ |
| No, transparent | Same section count, different content | |

**User's choice:** Explicit with conditional prompt
**Notes:** User specified implementation: use string interpolation in single writer prompt, not two separate prompts. "You are synthesizing a scouting report for a {Role}. {If Role == Reliever: [negative constraint]}."

---

## Raw Data Appendix Scope

### Stuff Specialist Appendix

| Option | Description | Selected |
|--------|-------------|----------|
| Per-pitch delta table | Full delta table with key metrics | ✓ |
| Minimal anchoring | Just hardest-to-get-right values | |
| Full PitchTypeSummary dump | Every field serialized | |

**User's choice:** Per-pitch delta table
**Notes:** User added anti-recalculation directive: "Refer specifically to the data in the Per-Pitch Delta Table when discussing movement or velocity changes. Do not attempt to recalculate these numbers."

### Labeling Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Cite requirement | Label as ground truth, mandate citation | ✓ |
| Available but optional | Label as supporting data | |
| Claude's discretion | Let planner decide | |

**User's choice:** Cite requirement

### Trend Specialist Appendix

| Option | Description | Selected |
|--------|-------------|----------|
| Same format, different fields | Static per-pitch table | |
| Trend-specific format | Per-appearance timeline snapshots | ✓ |
| Claude's discretion | Let planner decide | |

**User's choice:** Timeline-oriented format
**Notes:** Extensive rationale from user: static deltas cause Stuff and Trend to produce identical analysis. Timeline forces temporal narratives ("ramping up", "fading", "plateauing"). Cap at 5-7 appearances, primary pitches only (>10% usage). Existing 30-day window handles IL returns naturally.

---

## Auditor Expansion Strategy

### Audit Categories

| Option | Description | Selected |
|--------|-------------|----------|
| Same + platoon/count checks | 7 existing + 2 domain-specific | ✓ |
| Same categories only | Identical audit for all 6 | |
| Fully custom audit | Separate audit prompt | |

**User's choice:** Same + 2 domain-specific
**Notes:** User specified chain-of-thought format: (1) state claim, (2) cite exact numbers from data table, (3) Boolean Pass/Fail. "Forcing this step-by-step extraction drastically improves an LLM's accuracy as an auditor."

### Audit Input

| Option | Description | Selected |
|--------|-------------|----------|
| Input + output | Both source data and specialist prose | ✓ |
| Output only | Just specialist prose | |

**User's choice:** Input + output

---

## Claude's Discretion

- Exact Approach Specialist system prompt wording
- Per-appearance timeline table column selection
- Workload stub formatting details
- Conditional RP writer prompt syntax

## Deferred Ideas

None — discussion stayed within phase scope.
