# Requirements: Pitcher Narratives v1.8

**Defined:** 2026-04-02
**Core Value:** The report must read like a scout wrote it -- surfacing changes, adaptations, and execution trends rather than reciting numbers.

## v1.8 Requirements

Requirements for Cross-Season Trend Analysis milestone. Each maps to roadmap phases.

### Cross-Season Baselines

- [x] **XSBL-01**: PitcherData exposes prior-season baselines alongside current-season baselines (both season-level and pitch-type-level)
- [x] **XSBL-02**: load_pitcher_data() retains all per-season baseline rows instead of filtering to max season only
- [x] **XSBL-03**: Prior-season baselines are empty DataFrames (not crashes) when pitcher has only one season of data

### Season Deltas

- [ ] **SDLT-01**: Engine computes year-over-year deltas for pitcher-level metrics (velocity, P+, S+, L+) comparing current season baseline to prior season baseline
- [ ] **SDLT-02**: YoY delta strings use the same qualitative thresholds and language as within-season deltas (Steady / Up modestly / Down sharply / etc.)
- [ ] **SDLT-03**: Cross-season summary is None when prior-season data is missing (no fabricated comparisons)

### Arsenal Trends

- [ ] **ATRN-01**: Engine identifies pitches added (present in current season, absent in prior) and dropped (present in prior, absent in current) using a minimum-pitch threshold
- [ ] **ATRN-02**: Engine computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity for pitches present in both seasons
- [ ] **ATRN-03**: Arsenal trend output is None when pitcher has only one season of data

### Context & Prompt

- [ ] **CPMT-01**: PitcherContext model includes optional cross-season summary and arsenal trend fields
- [ ] **CPMT-02**: to_prompt() renders a Year-over-Year section with top-level deltas and arsenal changes when multi-season data exists, omits it entirely for single-season pitchers
- [ ] **CPMT-03**: Specialist pipeline agents (stuff, trends, game shape) receive cross-season data in their context blocks

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
| Cross-season trend for analyst Q&A tools | Analyst tools work on single-pitcher single-season; extend after v1.8 if needed |
| Automatic narrative style change for YoY data | LLM already adapts prose from context; no prompt engineering needed beyond data injection |
| Three-or-more season trend lines | Only 2 years of data exist; generalize when 3+ years available |
| Cross-season workload comparison | Workload is inherently recent-window; YoY workload comparison adds noise |
| Visual charts or sparklines | CLI text output; no terminal graphics |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| XSBL-01 | Phase 19 | Complete |
| XSBL-02 | Phase 19 | Complete |
| XSBL-03 | Phase 19 | Complete |
| SDLT-01 | Phase 20 | Pending |
| SDLT-02 | Phase 20 | Pending |
| SDLT-03 | Phase 20 | Pending |
| ATRN-01 | Phase 21 | Pending |
| ATRN-02 | Phase 21 | Pending |
| ATRN-03 | Phase 21 | Pending |
| CPMT-01 | Phase 22 | Pending |
| CPMT-02 | Phase 22 | Pending |
| CPMT-03 | Phase 22 | Pending |

**Coverage:**
- v1.8 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0

---
*Requirements defined: 2026-04-02*
*Last updated: 2026-04-03 after Phase 19 completion*
