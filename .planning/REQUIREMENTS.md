# Requirements: Pitcher Narratives v1.8

**Defined:** 2026-04-03
**Core Value:** The report must read like a scout wrote it -- surfacing changes, adaptations, and execution trends rather than reciting numbers.

## v1.8 Requirements

Requirements for Cross-Season Trend Analysis milestone. Each maps to roadmap phases.

### Cross-Season Baselines

- [ ] **XSBL-01**: `PitcherData` includes both current-season and prior-season baselines so engine consumers can compute year-over-year deltas
- [ ] **XSBL-02**: When a pitcher has only one season of data, cross-season fields are empty/None (no crash, no misleading comparison)

### Season-over-Season Deltas

- [ ] **SDLT-01**: Engine computes per-pitch-type usage shift between seasons (e.g., "sweeper usage to LHH dropped from 14% to 0%")
- [ ] **SDLT-02**: Engine computes per-pitch-type velocity and movement profile changes between seasons (e.g., "curveball 3 mph slower with 7 more inches of depth")
- [ ] **SDLT-03**: Engine computes platoon split changes between seasons -- per-handedness pitch mix, not just aggregate

### Appearance-over-Appearance Trends

- [ ] **ATRN-01**: Engine computes pitch-level trends across recent appearances within the current season -- velocity arc, shape drift, mix evolution per outing
- [ ] **ATRN-02**: Appearance trends distinguish between platoon splits (LHH vs RHH) per outing when data supports it

### Context & Prompt Integration

- [ ] **CPMT-01**: `PitcherContext.to_prompt()` includes a "Year-over-Year Changes" section when prior-season data exists
- [ ] **CPMT-02**: `PitcherContext.to_prompt()` includes a "Recent Appearance Trends" section showing outing-to-outing evolution
- [ ] **CPMT-03**: LLM system prompts updated to reason about what changed between seasons and across recent appearances, not just current-state description

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Cross-Pitcher Analysis

- **CROSS-01**: Agent has `search_pitchers` tool to scan dataset with filters (e.g., S+ > 120, L+ < 80)
- **CROSS-02**: Agent has `compare_metric` tool for side-by-side pitcher comparisons
- **CROSS-03**: Agent has `get_leaderboard` tool to rank pitchers by any metric

### Conversational Mode

- **CONV-01**: Multi-turn Q&A with session state and message history

### Quality Enhancements (from v1.3)

- **QUAL-01**: Oscillation detection -- terminate early when warnings cycle (disappear then reappear)
- **QUAL-02**: Revision diff tracking -- record what changed in each pass
- **QUAL-03**: ReflectionTrace with per-iteration token usage tracking
- **QUAL-04**: Anchor calibration examples -- few-shot examples of correct severity levels
- **QUAL-05**: `--no-refine` flag to skip the loop for speed/cost when desired

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Cross-season trend analysis across 3+ years | Two-year comparison is sufficient for current data |
| Automated scouting alerts | This milestone adds analysis, not notification |
| Batter-side analysis | Pitcher-focused reports only |
| Web UI or API | CLI tool only |
| Real-time data ingestion | Static parquet/CSV files |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| XSBL-01 | TBD | Pending |
| XSBL-02 | TBD | Pending |
| SDLT-01 | TBD | Pending |
| SDLT-02 | TBD | Pending |
| SDLT-03 | TBD | Pending |
| ATRN-01 | TBD | Pending |
| ATRN-02 | TBD | Pending |
| CPMT-01 | TBD | Pending |
| CPMT-02 | TBD | Pending |
| CPMT-03 | TBD | Pending |

**Coverage:**
- v1.8 requirements: 10 total
- Mapped to phases: 0
- Unmapped: 10

---
*Requirements defined: 2026-04-03*
