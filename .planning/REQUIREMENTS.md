# Requirements: Pitcher Narratives

**Defined:** 2026-03-26
**Core Value:** Reports must read like a scout wrote them — surfacing changes, adaptations, and execution trends rather than reciting numbers.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Pipeline

- [x] **DATA-01**: System can load Statcast parquet and filter pitch-level data by pitcher ID
- [x] **DATA-02**: System can load and join Pitching+ CSV aggregations at all grains (season, appearance, pitch type, platoon, and their combinations)
- [x] **DATA-03**: System can compute season-level baselines from pitcher.csv and pitcher_type.csv for a given pitcher
- [x] **DATA-04**: System can filter appearances to a configurable lookback window in days (via `-w` CLI arg)

### Pitcher Classification

- [x] **ROLE-01**: System can auto-detect whether each appearance is a start or relief outing
- [x] **ROLE-02**: Report structure adapts based on detected role (starter report vs. reliever report)
- [x] **ROLE-03**: System correctly handles swingmen/openers who switch roles between appearances

### Fastball Quality

- [x] **FB-01**: Report includes average fastball velocity for season baseline vs. recent window
- [x] **FB-02**: Report includes P+/S+/L+ for primary fastball: season baseline vs. recent window with delta
- [x] **FB-03**: Report includes movement deltas (pfx_x/pfx_z) for fastball: season baseline vs. recent
- [x] **FB-04**: Report includes within-game velocity arc analysis (early vs. late innings drop-off)

### Arsenal Analysis

- [ ] **ARSL-01**: Report includes usage rate per pitch type with delta vs. season baseline
- [ ] **ARSL-02**: Report includes P+/S+/L+ per pitch type: season baseline vs. recent window with delta
- [ ] **ARSL-03**: Report includes platoon mix shifts (usage changes by batter handedness)
- [ ] **ARSL-04**: Report includes first-pitch strike weaponry analysis (which pitch used to get ahead recently vs. norm)

### Execution Metrics

- [ ] **EXEC-01**: Report includes CSW% (called + swinging strike rate) by pitch type for recent window
- [ ] **EXEC-02**: Report includes xWhiff and xSwing rates per pitch type
- [ ] **EXEC-03**: Report includes zone rate vs. chase rate (O-Swing%) analysis
- [ ] **EXEC-04**: Report includes xRV100 ranking showing how pitches grade relative to league

### Workload & Context

- [ ] **CTX-01**: Report includes rest days between appearances
- [ ] **CTX-02**: Report includes innings pitched and pitch count per appearance
- [ ] **CTX-03**: Report includes consecutive days pitched tracking for relievers

### Report Generation

- [ ] **RPT-01**: Pydantic models define structured context schema for LLM input with pre-computed deltas and qualitative trend strings
- [ ] **RPT-02**: Claude generates report via pydantic-ai agent with str output type
- [ ] **RPT-03**: System prompt uses anti-recitation prompt engineering for scout-voice narrative
- [ ] **RPT-04**: Report output contains prose paragraphs with data tables where sensible — exemplary quality

### CLI

- [x] **CLI-01**: Script accepts `-p` argument for pitcher ID
- [x] **CLI-02**: Script accepts `-w` argument for lookback window in days (with sensible default)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Output Enhancements

- **OUT-01**: Rich terminal formatting with markdown rendering and colored tables
- **OUT-02**: Export report to markdown file
- **OUT-03**: Pitcher name lookup (resolve name string to pitcher ID)

### Advanced Analytics

- **ADV-01**: Times-through-order penalty analysis for starters
- **ADV-02**: Count-state tendencies (ahead vs. behind in count)
- **ADV-03**: Pitch-level outlier detection (individual pitches with extreme P+ scores)
- **ADV-04**: Key matchup highlights from recent appearances

### Data Quality

- **DQ-01**: Data quality assertions (null rates, pitch type consistency checks)
- **DQ-02**: Pitch count reliability thresholds (flag small sample sizes)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI or API | CLI script only — keep it simple |
| Season-over-season comparisons | Single-season 2026 data only |
| Batter-side analysis | Pitcher-focused reports only |
| Real-time data ingestion | Works against static parquet/CSV files |
| Team-level reports | Individual pitcher reports only |
| Pitch-by-pitch game replay narrative | LLM could generate this but no one would read it |
| Visualizations / charts | Text-based output only for v1 |
| Projections / forecasting | Descriptive analysis, not predictive |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| ROLE-01 | Phase 1 | Complete |
| ROLE-02 | Phase 1 | Complete |
| ROLE-03 | Phase 1 | Complete |
| CLI-01 | Phase 1 | Complete |
| CLI-02 | Phase 1 | Complete |
| FB-01 | Phase 2 | Complete |
| FB-02 | Phase 2 | Complete |
| FB-03 | Phase 2 | Complete |
| FB-04 | Phase 2 | Complete |
| ARSL-01 | Phase 2 | Pending |
| ARSL-02 | Phase 2 | Pending |
| ARSL-03 | Phase 2 | Pending |
| ARSL-04 | Phase 2 | Pending |
| EXEC-01 | Phase 3 | Pending |
| EXEC-02 | Phase 3 | Pending |
| EXEC-03 | Phase 3 | Pending |
| EXEC-04 | Phase 3 | Pending |
| CTX-01 | Phase 3 | Pending |
| CTX-02 | Phase 3 | Pending |
| CTX-03 | Phase 3 | Pending |
| RPT-01 | Phase 4 | Pending |
| RPT-02 | Phase 4 | Pending |
| RPT-03 | Phase 4 | Pending |
| RPT-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0

---
*Requirements defined: 2026-03-26*
*Last updated: 2026-03-26 after roadmap creation*
