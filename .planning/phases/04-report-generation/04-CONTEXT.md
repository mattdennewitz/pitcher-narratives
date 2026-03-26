# Phase 4: Report Generation - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the pydantic-ai agent with Claude to generate scout-voice narrative scouting reports. Connect the full pipeline: CLI invocation -> data loading -> engine computation -> context assembly -> LLM generation -> terminal output. Starter and reliever reports have visibly different structure.

</domain>

<decisions>
## Implementation Decisions

### LLM Agent Configuration
- Claude model: claude-sonnet-4-6 (good quality/cost ratio for narrative generation)
- Context passing: system prompt with role instructions + user message with to_prompt() output
- Output type: str (free-form prose) — structured output constrains narrative quality
- Max tokens: 4096 (enough for comprehensive report)

### System Prompt & Report Structure
- Persona: "You are a veteran MLB pitching analyst writing a scouting report"
- Anti-recitation: explicit instructions — "Write insight, not stat lines. Reference numbers to support observations, don't list them. If a delta is small, say so and move on."
- SP vs RP differentiation: include role in system prompt + conditional section guidance (starters get stamina/pitch mix depth, relievers get workload/leverage/short-window focus)
- Agent code lives in new `report.py` module — separates LLM interaction from data/compute layers

### Claude's Discretion
- Exact system prompt wording beyond the persona and anti-recitation core
- How to handle API errors (retry? fallback message?)
- Whether to stream output or wait for complete response
- Report length guidance in the prompt

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py` — load_pitcher_data(pitcher_id, window_days) -> PitcherData
- `engine.py` — compute_fastball_summary, compute_velocity_arc, compute_arsenal_summary, compute_platoon_mix, compute_first_pitch_weaponry, compute_execution_metrics, compute_workload_context
- `context.py` — PitcherContext (Pydantic BaseModel), assemble_pitcher_context(data) -> PitcherContext, to_prompt() -> str (~544 tokens)
- `main.py` — CLI with argparse (-p, -w), currently prints summary line

### Established Patterns
- Pipeline: data.load_pitcher_data() -> context.assemble_pitcher_context() -> context.to_prompt()
- PitcherContext.role field contains "SP" or "RP" for the most recent appearance
- PitcherContext.pitcher_name, .throws, .recent_appearances available for report header

### Integration Points
- main.py needs to: load data -> assemble context -> generate report -> print
- report.py imports from context.py (PitcherContext)
- pydantic-ai Agent configured with anthropic model
- ANTHROPIC_API_KEY environment variable needed

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
