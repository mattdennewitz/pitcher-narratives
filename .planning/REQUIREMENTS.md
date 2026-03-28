# Requirements: Pitcher Narratives v1.3

**Defined:** 2026-03-28
**Core Value:** Reports must read like a scout wrote them — surfacing changes, adaptations, and execution trends rather than reciting numbers.

## v1.3 Requirements

### Loop Infrastructure

- [ ] **LOOP-01**: Editor-anchor loop iterates until anchor returns CLEAN or max revision cap (2) is reached
- [x] **LOOP-02**: Revision prompt tells editor to fix specific flagged issues while preserving the rest of the capsule
- [ ] **LOOP-03**: Warnings that survive all iterations are passed through to stderr (same format as current anchor output)
- [ ] **LOOP-04**: Loop terminates immediately when anchor returns CLEAN (no unnecessary iterations)

### Data Model

- [x] **MODEL-01**: Anchor check returns structured AnchorResult (Pydantic model with is_clean + typed warnings) instead of raw string
- [x] **MODEL-02**: ReportResult includes revision_count (0 = passed first try, 1-2 = revised N times)

### UX & Integration

- [ ] **UX-01**: Loop runs by default on all narrative generations
- [ ] **UX-02**: Only the final capsule streams to stdout (revision passes run silently)
- [ ] **UX-03**: Stderr shows revision status ("Passed anchor check" or "Revised N times — [surviving warnings]")
- [ ] **UX-04**: Downstream phases (hook, fantasy) receive the final revised capsule

## Future Requirements

### Quality Enhancements

- **QUAL-01**: Oscillation detection — terminate early when warnings cycle (disappear then reappear)
- **QUAL-02**: Revision diff tracking — record what changed in each pass
- **QUAL-03**: ReflectionTrace with per-iteration token usage tracking
- **QUAL-04**: Anchor calibration examples — few-shot examples of correct severity levels
- **QUAL-05**: `--no-refine` flag to skip the loop for speed/cost when desired

## Out of Scope

| Feature | Reason |
|---------|--------|
| pydantic-graph state machine | Async-only, overkill for 2-node cycle — simple while loop is correct |
| Message history for revision | Creates anchoring bias and doubles token cost — fresh prompt is cleaner |
| Streaming revision passes | Confusing UX to stream then replace — only final capsule streams |
| Expanding anchor scope across iterations | Moving goalposts guarantee non-convergence — anchor checks same criteria every pass |
| Different model for anchor | Cost optimization deferred — same model ensures consistent severity |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MODEL-01 | Phase 5 | Complete |
| MODEL-02 | Phase 5 | Complete |
| LOOP-02 | Phase 5 | Complete |
| LOOP-01 | Phase 6 | Pending |
| LOOP-04 | Phase 6 | Pending |
| UX-01 | Phase 6 | Pending |
| UX-02 | Phase 6 | Pending |
| UX-04 | Phase 6 | Pending |
| LOOP-03 | Phase 7 | Pending |
| UX-03 | Phase 7 | Pending |

**Coverage:**
- v1.3 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 after roadmap creation*
