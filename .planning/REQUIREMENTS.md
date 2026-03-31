# Requirements: Pitcher Narratives v1.5

**Defined:** 2026-03-31
**Core Value:** The report must read like a scout wrote it -- surfacing changes, adaptations, and execution trends rather than reciting numbers.

## v1.5 Requirements

Requirements for Model-Explainable Narratives milestone. Each maps to roadmap phases.

### Data Pipeline

- [x] **DATA-01**: Analyst context includes per-pitch-type intermediate probabilities (xSwing, xWhiff, xGOr, xPUr, xHR100, BBE_prob) from pitchingplus aggregations
- [x] **DATA-02**: Analyst context includes P vs S variants of intermediates so location impact is quantifiable
- [x] **DATA-03**: xRV is decomposed into 13 outcome-level contributions (probability x run_value per outcome) per pitch type

### Analyst Intelligence

- [ ] **ANLST-01**: Analyst system prompt frames reasoning around model internals (outcome probabilities, component attribution) rather than opaque plus grades
- [ ] **ANLST-02**: Analyst diagnoses location impact by comparing P-variant vs S-variant probabilities (e.g., "swing rate drops 9% with location factored in")
- [ ] **ANLST-03**: Analyst identifies which outcome class is the dominant run-value driver for a given pitch type (e.g., "whiffs contribute 1.4 runs saved per 100")

### Tool Interface

- [ ] **TOOL-01**: get_pitcher_summary tool returns intermediate probabilities and P/S comparisons alongside existing plus scores
- [ ] **TOOL-02**: get_pitch_detail tool returns component attribution breakdown (13 outcome contributions to xRV) for a specific pitch type

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
| SHAP/feature-level explanations | Requires adding SHAP computation to pitchingplus pipeline; component attribution answers "why" without it |
| CatBoost feature importance export | Model debugging tool, not narrative generation |
| Modifications to pitchingplus package | Read-only consumer; new computation happens in pitcher-narratives |
| Per-pitch (non-aggregated) model outputs | Aggregated metrics are what narratives need; per-pitch is noise |
| SQL generation from natural language | Existing engine computes meaningful derived metrics |
| Fantasy advice in Q&A answers | Speculative and ungrounded -- use full report pipeline |
| Cross-pitcher comparison | Needs new data scanning layer -- deferred to v1.6+ |
| Multi-turn conversation | Session state management, different UX paradigm -- deferred to v1.6+ |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 11 | Complete |
| DATA-02 | Phase 11 | Complete |
| DATA-03 | Phase 12 | In Progress (data loaded, computation in 12-02) |
| ANLST-01 | Phase 14 | Pending |
| ANLST-02 | Phase 14 | Pending |
| ANLST-03 | Phase 14 | Pending |
| TOOL-01 | Phase 13 | Pending |
| TOOL-02 | Phase 13 | Pending |

**Coverage:**
- v1.5 requirements: 8 total
- Mapped to phases: 8
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-31*
*Last updated: 2026-03-31 after roadmap creation*
