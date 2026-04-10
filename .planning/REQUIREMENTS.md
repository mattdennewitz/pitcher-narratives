# Requirements: Pitcher Narratives

**Defined:** 2026-04-09
**Core Value:** Scout-voice scouting reports surfacing changes, adaptations, and execution trends

## v1.9 Requirements

Requirements for Pipeline Consolidation milestone. Remove old single-agent reporting infrastructure.

### Code Removal

- [ ] **REM-01**: report.py is deleted — old single-agent pipeline and reflection loop removed entirely
- [ ] **REM-02**: test_report.py is deleted — old pipeline tests removed
- [ ] **REM-03**: All imports of report.py removed from cli.py and any other consumers

### CLI Consolidation

- [ ] **CLI-01**: `--pipeline` flag removed from CLI — multi-agent pipeline is the only reporting path
- [ ] **CLI-02**: CLI generates reports via pipeline.py by default with no flag required
- [ ] **CLI-03**: All existing CLI features (hallucination check, streaming, info mode) work through pipeline path

### Verification

- [ ] **VER-01**: All remaining tests pass after removal
- [ ] **VER-02**: anchor.py remains intact and functional (shared with pipeline.py)

## Future Requirements

None — this is a cleanup milestone.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Refactoring pipeline.py internals | Separate concern; this milestone is removal only |
| Adding new pipeline features | Separate milestone |
| Removing anchor.py | Shared with pipeline.py; still in use |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REM-01 | — | Pending |
| REM-02 | — | Pending |
| REM-03 | — | Pending |
| CLI-01 | — | Pending |
| CLI-02 | — | Pending |
| CLI-03 | — | Pending |
| VER-01 | — | Pending |
| VER-02 | — | Pending |

**Coverage:**
- v1.9 requirements: 8 total
- Mapped to phases: 0
- Unmapped: 8 (pending roadmap)

---
*Requirements defined: 2026-04-09*
*Last updated: 2026-04-09 after initial definition*
