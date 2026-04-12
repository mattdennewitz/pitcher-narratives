# Phase 6: Loop Mechanics - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the editor-anchor reflection loop into generate_report_streaming(). After the editor produces a capsule, the anchor checks it. If warnings are found, the editor revises using _build_revision_message() and the anchor re-checks — up to 2 revision passes. Only the final capsule streams to stdout; revision passes run silently. Downstream phases (hook writer, fantasy analyst) receive the final revised capsule.

</domain>

<decisions>
## Implementation Decisions

### Loop Structure (from v1.3 research)
- Plain while-loop inside generate_report_streaming() (not pydantic-graph — async-only, overkill for 2-node cycle)
- MAX_REVISIONS = 2 constant (3 total passes including first draft); configurable via constant
- Loop exits immediately when anchor returns is_clean == True
- Fresh prompt per revision (no message history — avoids anchoring bias and token bloat)
- Fixed-size revision context: synthesis + current capsule + current warnings only (via _build_revision_message)

### Streaming Control (from v1.3 research)
- First draft: editor runs via run_stream_sync (streams to stdout as currently implemented)
- Revision passes: editor runs via run_sync (silent — no output to stdout)
- Only the final capsule (first draft or last revision) is the one that was streamed/returned
- If revision occurs, the first draft was already streamed — but the final capsule replaces it in ReportResult

### Pipeline Integration
- Hook writer and fantasy analyst receive the final capsule (post-revision), not the original first draft
- ReportResult.revision_count tracks how many revision passes occurred (0 = passed first try)
- Loop runs by default on every call to generate_report_streaming() — no flag needed

### Claude's Discretion
- Exact placement of the while-loop within generate_report_streaming()
- Whether MAX_REVISIONS is a module constant or a parameter
- How to handle anchor agent errors during the loop (retry? break? propagate?)
- Whether to update the _make_agents cache or agent factory for the revision editor calls

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `report.py` — generate_report_streaming() is the 5-phase pipeline orchestration function
- `report.py` — AnchorResult.is_clean property for clean check
- `report.py` — _build_revision_message(synthesis, capsule, warnings) returns _UserPrompt for revision
- `report.py` — _build_anchor_message(synthesis, capsule) for re-checking
- `report.py` — ReportResult with revision_count field (defaults to 0)
- `report.py` — _make_agents() returns (_StrAgents, anchor_agent) tuple

### Established Patterns
- Pipeline: synth → editor (streamed) → anchor → hook → fantasy
- Editor uses run_stream_sync for streaming; other phases use run_sync
- _model_override passed to each agent via kwargs dict
- anchor_checker.run_sync returns result.output as AnchorResult

### Integration Points
- generate_report_streaming() needs a while-loop between editor and hook phases
- Editor agent (from _StrAgents[1]) handles both first draft and revisions
- After loop: capsule variable holds the final version, anchor_check holds final result
- Hook and fantasy phases already use capsule variable — just need loop to update it before they run

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond what the research decisions and success criteria define.

</specifics>

<deferred>
## Deferred Ideas

- --no-refine flag to skip the loop (QUAL-05 — future requirement)
- Oscillation detection (QUAL-01 — terminate early when warnings cycle)
- Revision diff tracking (QUAL-02 — record what changed per pass)
- ReflectionTrace with per-iteration token usage (QUAL-03)

</deferred>
