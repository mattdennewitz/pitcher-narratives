# Requirements: Pitcher Narratives

**Defined:** 2026-04-04
**Core Value:** Reports must read like a scout wrote them — surfacing changes, adaptations, and execution trends rather than reciting numbers.

## v1.9 Requirements

Requirements for Multi-Agent Narrative Upgrade. Each maps to roadmap phases.

### Engine & Data Enrichment

- [x] **ENG-01**: Engine computes per-pitch-type usage across count states (ahead/behind/even/two-strike) with window vs season deltas
- [x] **ENG-02**: Engine computes arm angle from release_x/release_z via atan2, with window vs season delta strings
- [x] **ENG-03**: Outlier tags include percentile rank (e.g., "98th percentile") instead of raw z-score notation
- [x] **ENG-04**: CountSplits and arm angle fields wired into PitcherContext and rendered in prompt output
- [x] **ENG-05**: Count bucket with fewer than 10 pitches flagged as small sample (no usage delta computed)

### Pipeline Architecture

- [x] **PIPE-01**: Approach Specialist agent receives platoon mix, count splits, and first-pitch data as input
- [x] **PIPE-02**: Approach Specialist prompt prioritizes 10+ pp platoon/count usage shifts as lead stories
- [x] **PIPE-03**: Location Specialist no longer receives platoon data (moved to Approach Specialist)
- [x] **PIPE-04**: Game Shape specialist skipped for relievers (ctx.role == "RP"), replaced with static placeholder
- [ ] **PIPE-05**: Stuff and Trend specialist inputs include raw data appendix with PitchTypeSummary deltas
- [x] **PIPE-06**: Writer input includes Approach Specialist output as 6th specialist analysis
- [x] **PIPE-07**: Auditor runs against Approach Specialist output (6 audits total, up from 5)

### Prompt Heuristics

- [x] **PROMPT-01**: Stuff Specialist prompt includes trade-off detection directive (inverse velo/movement → S+ improvement)
- [x] **PROMPT-02**: Location Specialist prompt includes contradiction detection directive (low zone + high whiff = expanding zone)
- [x] **PROMPT-03**: Trend Specialist prompt includes release point framing vocabulary (arm angle, deception, approach angle)
- [x] **PROMPT-04**: Writer prompt includes causal hook requirement (S+ change ≥ 10 pts must cite physical driver)
- [x] **PROMPT-05**: Data Auditor prompt whitelists sabermetric heuristics (inverse correlations, zone expansion) as valid analysis
- [ ] **PROMPT-06**: Location Specialist input places xWhiff and zone_rate adjacent for contradiction visibility

## Future Requirements

- **FUT-01**: Count-state effectiveness metrics (P+ per count bucket, not just usage)
- **FUT-02**: Release point percentile ranks vs league distribution
- **FUT-03**: Sequence analysis (pitch-pair tunneling metrics)
- **FUT-04**: Cross-pitcher comparison in Q&A mode

## Out of Scope

| Feature | Reason |
|---------|--------|
| Grip/mechanical inference | LLM cannot see video; only physical profile data available |
| Count-state P+ computation | Requires pitchingplus model recomputation at count grain; usage-only for v1.9 |
| New LLM providers | Current 3-provider support sufficient |
| Web UI | CLI-only project |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENG-01 | Phase 23 | Complete |
| ENG-02 | Phase 23 | Complete |
| ENG-03 | Phase 23 | Complete |
| ENG-04 | Phase 23 | Complete |
| ENG-05 | Phase 23 | Complete |
| PIPE-01 | Phase 24 | Complete |
| PIPE-02 | Phase 24 | Complete |
| PIPE-03 | Phase 24 | Complete |
| PIPE-04 | Phase 24 | Complete |
| PIPE-05 | Phase 24 | Pending |
| PIPE-06 | Phase 24 | Complete |
| PIPE-07 | Phase 24 | Complete |
| PROMPT-01 | Phase 25 | Complete |
| PROMPT-02 | Phase 25 | Complete |
| PROMPT-03 | Phase 25 | Complete |
| PROMPT-04 | Phase 25 | Complete |
| PROMPT-05 | Phase 25 | Complete |
| PROMPT-06 | Phase 25 | Pending |

**Coverage:**
- v1.9 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-04*
*Last updated: 2026-04-04 after initial definition*
