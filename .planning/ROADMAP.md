# Roadmap: Pitcher Narratives

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-03-26)
- ✅ **v1.3 Editor-Anchor Reflection Loop** - Phases 5-11 (shipped 2026-03-28)
- ✅ **v1.4 Interactive Pitcher Q&A** - Phases 12-14 (shipped 2026-03-30)
- ✅ **v1.6 Multi-Agent Pipeline** - Phase 15 (shipped 2026-04-03)
- ✅ **v1.7 Multi-Year Data & Game Type Filtering** - Phases 16-18 (shipped 2026-04-03)
- ✅ **v1.8 Cross-Season Trend Analysis** - Phases 19-22 (shipped 2026-04-08)
- 🚧 **v1.9 Pipeline Consolidation** - Phases 23-24 (in progress)

## Phases

- [x] **Phase 23: Remove Old Pipeline** - Delete report.py, test_report.py, strip old-path imports, and consolidate CLI to use pipeline.py exclusively (completed 2026-04-10)
- [ ] **Phase 24: Verification & Cleanup** - Confirm all tests pass, anchor.py intact, and all CLI features work through the pipeline path

## Phase Details

### 🚧 v1.9 Pipeline Consolidation (In Progress)

**Milestone Goal:** Remove old single-agent reporting infrastructure so the multi-agent specialist pipeline is the sole reporting path.

### Phase 23: Remove Old Pipeline
**Goal**: The old single-agent reporting path is completely removed and the CLI routes all report generation through pipeline.py
**Depends on**: Phase 22
**Requirements**: REM-01, REM-02, REM-03, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. report.py does not exist in the repository
  2. test_report.py does not exist in the repository
  3. No module in the codebase imports from report.py
  4. Running the CLI without `--pipeline` generates a report via pipeline.py (flag is gone, pipeline is the default)
  5. anchor.py is unchanged and still importable by pipeline.py
**Plans**: 2 plans

Plans:
- [x] 23-01-PLAN.md — Relocate hallucination guard to pipeline.py, rewrite CLIs to use pipeline path exclusively
- [x] 23-02-PLAN.md — Delete report.py and test_report.py, verify clean state

### Phase 24: Verification & Cleanup
**Goal**: The codebase is clean post-removal -- all tests pass and every CLI feature works through the pipeline path
**Depends on**: Phase 23
**Requirements**: CLI-03, VER-01, VER-02
**Success Criteria** (what must be TRUE):
  1. Full test suite passes with zero failures (`uv run python -m pytest`)
  2. anchor.py functions (AnchorResult, AnchorWarning) are importable and used by pipeline.py
  3. CLI streaming output works for a report generated through pipeline.py
  4. CLI `--hallucination-check` flag works through the pipeline path
  5. CLI `--info` mode works through the pipeline path
**Plans**: 1 plan

Plans:
- [ ] 24-01-PLAN.md — Verify test suite, CLI features through pipeline path, clean stale docstrings

## Progress

**Execution Order:** 23 → 24

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 23. Remove Old Pipeline | v1.9 | 2/2 | Complete    | 2026-04-10 |
| 24. Verification & Cleanup | v1.9 | 0/1 | Not started | - |
