# Requirements: Pitcher Narratives v1.4

**Defined:** 2026-03-30
**Core Value:** The report must read like a scout wrote it — surfacing changes, adaptations, and execution trends rather than reciting numbers.

## v1.4 Requirements

Requirements for Interactive Pitcher Q&A milestone. Each maps to roadmap phases.

### Name Resolution

- [ ] **RESOLVE-01**: User can identify a pitcher by partial name, full name, or last name (fuzzy matching via rapidfuzz)
- [ ] **RESOLVE-02**: User sees a disambiguation list when multiple pitchers match (e.g., "Johnson" → candidates)

### Agent

- [ ] **AGENT-01**: Tool-calling pydantic-ai agent answers questions using only provided pitcher data (no training-data hallucination)
- [ ] **AGENT-02**: Agent has `get_pitcher_summary` tool returning full PitcherContext for broad questions
- [ ] **AGENT-03**: Agent has `get_pitch_detail` tool returning focused arsenal/execution/platoon data for a specific pitch type
- [ ] **AGENT-04**: Agent declines questions about data it doesn't have (predictions, fantasy advice, historical seasons, cross-pitcher comparisons)
- [ ] **AGENT-05**: Pitch type extraction maps natural language ("knuckle curve", "slider") to Statcast codes (KC, SL)
- [ ] **AGENT-06**: Agent streams answer to stdout as it generates

### CLI

- [ ] **CLI-01**: User can ask a question via CLI entry point (e.g., `pitcher-ask "Why is Cease's knuckle curve bad?"`)
- [ ] **CLI-02**: CLI supports `--provider` and `--thinking` flags matching existing report CLI

## v1.5 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Cross-Pitcher Analysis

- **CROSS-01**: Agent has `search_pitchers` tool to scan dataset with filters (e.g., S+ > 120, L+ < 80)
- **CROSS-02**: Agent has `compare_metric` tool for side-by-side pitcher comparisons
- **CROSS-03**: Agent has `get_leaderboard` tool to rank pitchers by any metric

### Conversational Mode

- **CONV-01**: Multi-turn Q&A with session state and message history

### Quality Enhancements (from v1.3)

- **QUAL-01**: Oscillation detection — terminate early when warnings cycle (disappear then reappear)
- **QUAL-02**: Revision diff tracking — record what changed in each pass
- **QUAL-03**: ReflectionTrace with per-iteration token usage tracking
- **QUAL-04**: Anchor calibration examples — few-shot examples of correct severity levels
- **QUAL-05**: `--no-refine` flag to skip the loop for speed/cost when desired

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| SQL generation from natural language | Existing engine computes meaningful derived metrics — bypassing it loses pre-computed deltas and baselines |
| Fantasy advice in Q&A answers | Speculative and ungrounded — use full report pipeline for fantasy analysis |
| LLM-powered name resolution | Slow, expensive, unreliable — name resolution is a lookup problem, not a reasoning problem |
| Historical season-over-season trends | Single-season 2026 data only per PROJECT.md constraints |
| Question rewriting/rephrasing | Extra LLM call adds latency — analyst agent interprets questions directly |
| Cross-pitcher comparison (v1.4) | Needs new data scanning layer — defer to v1.5 |
| Multi-turn conversation (v1.4) | Session state management, different UX paradigm — defer to v1.5+ |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| RESOLVE-01 | — | Pending |
| RESOLVE-02 | — | Pending |
| AGENT-01 | — | Pending |
| AGENT-02 | — | Pending |
| AGENT-03 | — | Pending |
| AGENT-04 | — | Pending |
| AGENT-05 | — | Pending |
| AGENT-06 | — | Pending |
| CLI-01 | — | Pending |
| CLI-02 | — | Pending |

**Coverage:**
- v1.4 requirements: 10 total
- Mapped to phases: 0
- Unmapped: 10 ⚠️

---
*Requirements defined: 2026-03-30*
*Last updated: 2026-03-30 after initial definition*
