# Phase 7: Revision UX & Validation - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Surface the reflection loop's behavior to stderr so users know what happened: first-try pass, revision count, or surviving warnings. Uses the same stderr format as existing anchor output — no new output channels.

</domain>

<decisions>
## Implementation Decisions

### Stderr Output Format (from requirements + success criteria)
- First-try clean: stderr shows "Passed anchor check" (or equivalent)
- Revisions that converge: stderr shows "Revised N time(s) -- anchor check passed"
- Max revisions exhausted with surviving warnings: stderr shows each surviving warning description
- Surviving warnings use same format as existing anchor check stderr output (see cli.py current pattern: `[CATEGORY] description`)

### Output Channel
- All revision status messages go to stderr (not stdout)
- No new output channels or formats — reuse existing patterns from cli.py
- Stdout reserved exclusively for the narrative report (already established)

### Claude's Discretion
- Exact stderr message wording beyond what success criteria specify
- Whether to print revision status from within generate_report_streaming() or from cli.py
- Whether to add a helper function for formatting or inline the prints

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cli.py` lines ~140-143 — existing anchor warning printer: `print(f"  [{w.category}] {w.description}", file=sys.stderr)`
- `report.py` — generate_report_streaming() returns ReportResult with revision_count and anchor_warnings
- `report.py` — AnchorWarning objects with .category and .description fields

### Established Patterns
- cli.py prints "ANCHOR CHECK:" header then indented warnings to stderr
- All stderr output in cli.py uses `print(..., file=sys.stderr)`
- report.py does NOT print anything to stderr — only cli.py does

### Integration Points
- cli.py already prints anchor warnings after generate_report_streaming() returns
- Need to modify cli.py to check revision_count and print appropriate status message
- May need to conditionally suppress or modify existing anchor warning output based on revision outcome

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond what the success criteria define.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
