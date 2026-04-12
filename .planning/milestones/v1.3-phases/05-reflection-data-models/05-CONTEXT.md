# Phase 5: Reflection Data Models - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning
**Mode:** Infrastructure phase — discuss skipped (pure types + prompt builder, no user-facing behavior)

<domain>
## Phase Boundary

The codebase has structured types for anchor check results, revision metadata, and a prompt builder that constructs targeted revision instructions from anchor warnings.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key architectural decisions were already made during v1.3 research:
- Fresh prompt per revision (no message history — avoids anchoring bias and token bloat)
- Fixed-size revision context (synthesis + current capsule + current warnings only)
- MAX_REVISIONS=2 default (3 total passes); configurable
- Streaming only on final capsule (revision passes run silently)

Use ROADMAP phase goal, success criteria, and codebase conventions to guide remaining decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `report.py` — ReportResult (Pydantic BaseModel with narrative, social_hook, fantasy_insights, anchor_warnings: list[str])
- `report.py` — _ANCHOR_PROMPT defines four warning categories: MISSED SIGNAL, UNSUPPORTED, DIRECTION ERROR, OVERSTATED
- `report.py` — _build_anchor_message(synthesis, capsule) builds the anchor check user prompt
- `report.py` — generate_report_streaming() orchestrates the 5-phase pipeline
- `report.py` — HallucinationReport (Pydantic BaseModel with is_clean property pattern)

### Established Patterns
- Pydantic BaseModel for all structured types (ReportResult, HallucinationReport, PitcherContext)
- is_clean boolean property pattern (HallucinationReport.is_clean)
- _build_*_message() functions for prompt construction
- _UserPrompt type alias for list[str | CachePoint]
- Warning parsing: split anchor output on newlines, strip whitespace

### Integration Points
- ReportResult needs revision_count field added
- Anchor check currently returns raw str parsed into list[str] — needs to return AnchorResult instead
- Revision prompt builder needs synthesis str + capsule str + AnchorWarning list as inputs
- generate_report_streaming() will be modified in Phase 6 to use the loop

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
