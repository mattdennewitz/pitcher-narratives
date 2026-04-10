# Phase 23: Remove Old Pipeline - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The old single-agent reporting path is completely removed and the CLI routes all report generation through pipeline.py

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key removals:
- Delete `report.py` (old single-agent path)
- Delete `test_report.py` (old tests)
- Move shared utilities (`check_hallucinated_metrics`, `HallucinationReport`, `write_data_file`, `print_prompts`) to appropriate modules before deletion
- Update `cli.py` to remove `--pipeline` flag and always use pipeline path
- Update `ask_cli.py` to remove `--pipeline` flag and always use pipeline path
- `anchor.py` must remain unchanged

</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `src/pitcher_narratives/report.py` — old 4-phase report pipeline, exports `check_hallucinated_metrics`, `generate_report_streaming`, `print_prompts`, `write_data_file`
- `src/pitcher_narratives/pipeline.py` — new multi-agent specialist pipeline
- `src/pitcher_narratives/cli.py` — main CLI, has `--pipeline` flag branching at line 125
- `src/pitcher_narratives/ask_cli.py` — Q&A CLI, has `--pipeline` flag branching at line 122
- `src/pitcher_narratives/anchor.py` — shared by both paths, must stay intact
- `tests/test_report.py` — tests for old report path
- `tests/test_pipeline.py` — tests for new pipeline path

### Import Dependencies on report.py
- `cli.py:96` imports `check_hallucinated_metrics`, `generate_report_streaming`, `print_prompts`, `write_data_file`
- `tests/test_report.py:20` imports from report
- No other modules import from report.py

### Integration Points
- `cli.py` must be rewritten to always use pipeline.py path
- `ask_cli.py` must be rewritten to always use pipeline path
- `check_hallucinated_metrics` is used in cli.py for both paths — needs to be relocated

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
