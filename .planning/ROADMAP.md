# Roadmap: Pitcher Narratives

## Milestones

- ✅ **v1.0 MVP** — Phases 1-4 (shipped 2026-03-26)
- ✅ **v1.3 Editor-Anchor Reflection Loop** — Phases 5-7 (shipped 2026-03-28)
- ✅ **v1.4 Interactive Pitcher Q&A** — Phases 8-10 (shipped 2026-03-30)
- ✅ **v1.5 Model-Explainable Narratives** — Phases 11-14 (shipped 2026-04-01)
- ✅ **v1.6 Multi-Agent Pipeline** — Phase 15 (shipped 2026-04-03)
- **v1.7 Multi-Year Data & Game Type Filtering** — Phases 16-18

</details>

### Phase 17: Multi-Year Loading
**Goal**: The data pipeline loads and concatenates parquet and CSV files across all configured years, with per-season baselines that prevent cross-season averaging artifacts
**Depends on**: Phase 16
**Requirements**: MYLD-01, MYLD-02, MYLD-03, MYLD-04
**Success Criteria** (what must be TRUE):
  1. `load_statcast()` reads parquet files for all years in `_YEARS` and returns a single concatenated DataFrame spanning both 2025 and 2026
  2. `load_agg_csvs()` reads year-prefixed CSV files for all configured years and returns concatenated DataFrames per grain
  3. When a year's files are missing (e.g., 2025 parquet does not exist), the pipeline skips that year without crashing and loads available years
  4. Season baselines are computed per-season -- a pitcher who threw 95 mph in 2025 and 97 mph in 2026 has a 2026 baseline of 97, not 96
**Plans:** 1/1 plans complete
Plans:
- [x] 17-01-PLAN.md -- Multi-year parquet/CSV loading with missing-file handling and per-season baselines

### Phase 18: Consumer Module Updates
**Goal**: All modules that bypass data.py to read CSV or parquet files directly are refactored to use data.py's loading functions, ensuring game type filtering and multi-year support are applied consistently everywhere
**Depends on**: Phase 16, Phase 17
**Requirements**: CSMR-01, CSMR-02, CSMR-03
**Success Criteria** (what must be TRUE):
  1. `engine.py` no longer contains any direct `read_csv` or `read_parquet` calls -- all data access routes through `data.py` functions
  2. `resolver.py` builds its pitcher name table from all available parquet files (not just 2026), so pitchers who appeared only in 2025 are discoverable
  3. `scout.py` no longer contains any direct CSV or parquet reads -- all data access routes through `data.py` functions including the velocity baseline computation
  4. Running `grep "read_csv\|read_parquet" src/pitcher_narratives/ | grep -v data.py` returns zero results (no bypass loads remain)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 16 -> 17 -> 18

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Data Pipeline & Classification | v1.0 | 2/2 | Complete | 2026-03-26 |
| 2. Fastball & Arsenal Engine | v1.0 | 2/2 | Complete | 2026-03-26 |
| 3. Execution & Context Engine | v1.0 | 2/2 | Complete | 2026-03-26 |
| 4. Report Generation | v1.0 | 2/2 | Complete | 2026-03-26 |
| 5. Reflection Data Models | v1.3 | 2/2 | Complete | 2026-03-28 |
| 6. Loop Mechanics | v1.3 | 1/1 | Complete | 2026-03-28 |
| 7. Revision UX & Validation | v1.3 | 1/1 | Complete | 2026-03-28 |
| 8. Name Resolution | v1.4 | 1/1 | Complete | 2026-03-30 |
| 9. Analyst Agent & Tools | v1.4 | 1/1 | Complete | 2026-03-30 |
| 10. Ask CLI | v1.4 | 1/1 | Complete | 2026-03-30 |
| 11. Intermediate Probability Pipeline | v1.5 | 1/1 | Complete | 2026-03-31 |
| 12. Component Attribution | v1.5 | 2/2 | Complete | 2026-03-31 |
| 13. Tool Interface Updates | v1.5 | 1/1 | Complete | 2026-03-31 |
| 14. Analyst Prompt Rewrite | v1.5 | 1/1 | Complete | 2026-03-31 |
| 15. Specialist-Writer Architecture | v1.6 | prototyped | Complete | 2026-04-03 |
| 16. Data Foundation | v1.7 | 1/1 | Complete    | 2026-04-03 |
| 17. Multi-Year Loading | v1.7 | 1/1 | Complete   | 2026-04-03 |
| 18. Consumer Module Updates | v1.7 | 0/0 | Not started | -- |

---
*Full phase details archived in `.planning/milestones/`*
