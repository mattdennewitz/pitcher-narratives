# Key Signal Extractor — Design Spec

## Problem

The multi-agent pipeline (`pipeline.py`) replaced the old single-synthesizer pipeline (`report.py`). The old synthesizer produced an explicit `## Key Signal` section with three labeled bullets (top improvement, top concern, development pitch) that served two purposes:

1. **Writer guidance** — the editor used Key Signals to prioritize narrative.
2. **Anchor validation** — the anchor checker validated the capsule against Key Signals via its `MISSED_SIGNAL` check.

The new pipeline distributes synthesis across five specialists. No specialist produces a Key Signal section, so:

- The writer finds its own thread with no explicit priority guidance.
- The anchor checker's `MISSED_SIGNAL` check (anchor.py:34-36) references a "Key Signal section" that doesn't exist — the check is dead.

## Solution

Add a **Signal Extractor** agent between audit/revision (Phase 1.5) and the writer (Phase 2). It reads the five clean specialist outputs and produces a structured `KeySignals` model with eight fields — three always-present, five conditional. The signals feed both the writer (as narrative priorities) and the anchor checker (as validation targets).

## Data Model

```python
class KeySignals(BaseModel):
    # Primary signals (required — always present, anchor-enforced)
    top_improvement: str            # Single most important positive finding
    top_concern: str                # Single most important negative finding

    # Secondary signals (optional — present only when pattern exists, advisory)
    development_pitch: str | None   # High-S+/low-L+ pitch solving a platoon gap
    specialist_tension: str | None  # Two specialists disagree on the same pitch
    arsenal_dependency: str | None  # One pitch carrying the whole profile
    connected_changes: str | None   # Multiple specialists seeing facets of same shift
    platoon_vulnerability: str | None  # Clear handedness weakness not being addressed
    sample_size_caution: str | None # Strongest finding rests on thin data
```

- **Primary signals** (`top_improvement`, `top_concern`) are required — there is always a best and worst signal. The anchor checker enforces these via `MISSED_SIGNAL`.
- **Secondary signals** (remaining six) are optional (`None` when the pattern is not present). No forced findings. The anchor checker flags ignored secondary signals as `UNDERWEIGHTED_SIGNAL` — advisory, not blocking. This prevents the writer from being forced to cram eight signals into 2-3 paragraphs and losing the scouting voice.
- Each field is a single sentence citing specific pitch types and metrics.

## Signal Extractor Agent

**Model tier:** Mini model (same as auditor, anchor checker, summary agent).

**Temperature:** 0.1 — this is classification/extraction, not creative writing.

**Thinking:** Capped to "low".

**Token budget:** Small (`TOKEN_BUDGET_SMALL`) — the output is 3-8 sentences.

**Output type:** `KeySignals` (structured Pydantic output).

**Input:** The same concatenated specialist outputs the writer receives (stuff, location, run value, trends, game shape).

**Prompt:** Defines the agent as a cross-specialist pattern detector. For each of the eight signal types, provides a one-line definition and the evidence pattern to look for. Instructs the agent to:

- Cite specific pitch types and metrics in every field.
- Leave optional fields as `null` when the pattern is genuinely absent.
- Not invent patterns — only surface what the specialists explicitly reported.

## Pipeline Placement

Runs after Phase 1.5 (audit/revision), before Phase 2 (writer). This is a new serial step — the signal extractor must complete before the writer starts, since its output is part of the writer's input.

```
Phase 1:   5 specialists (concurrent)
Phase 1.5: Per-specialist audit + revision (concurrent per specialist)
NEW:       Signal extractor (serial, fast)
Phase 2:   Writer + executive summary (concurrent with each other)
Phase 2.5: Anchor check + revision loop
```

## Changes to Existing Code

### `pipeline.py`

**1. `PipelineAgents` NamedTuple** — Add `signal_extractor: Agent[None, KeySignals]` field.

**2. `make_pipeline_agents()`** — Create the signal extractor agent with checker-tier settings (mini model, 0.1 temp, low thinking, `TOKEN_BUDGET_SMALL`).

**3. `_run_pipeline()`** — Add a new step between audit/revision and writer:

```python
# Phase 1.75: Extract key signals from clean specialist outputs
signal_input = build_writer_input(ctx, specialists.stuff, ...)
signal_result = await agents.signal_extractor.run(**agent_kwargs(signal_input, _model_override))
key_signals = signal_result.output
```

Then pass `key_signals` to the writer input builder and prepend to the anchor synthesis string.

**4. `build_writer_input()`** — Add `key_signals: KeySignals` parameter. Render populated signals as a `## Key Signals` section at the top of the writer input, before the specialist analyses. Format: one labeled bullet per populated field (e.g., `- Top Improvement: <value>`). Omit `None` fields entirely — the writer and anchor checker should only see signals that are present.

**5. Anchor synthesis string** (line ~1165) — Prepend the rendered Key Signals section so the anchor checker can validate against it.

### `_WRITER_PROMPT`

Add after the existing "CRITICAL: These are INGREDIENTS" block:

> "The Key Signals section contains cross-specialist patterns. Primary signals (top improvement, top concern) are your narrative priorities — your lead must address one. Secondary signals (specialist tension, connected changes, etc.) are high-value if they serve the thread — use your judgment on weight. You are not required to mention every secondary signal."

### `anchor.py`

**`ANCHOR_PROMPT`** — Replace check #1 (lines 34-36):

**Before:**
> "Missed Key Signals: The synthesis has a 'Key Signal' section with the most important improvement, concern, and development pitch. If the capsule ignores any of these entirely, flag it."

**After:**
> "Missed Key Signals: The synthesis includes a Key Signals section with primary and secondary findings. Primary signals (Top Improvement, Top Concern) are mandatory — if the capsule ignores either entirely, flag it as MISSED_SIGNAL. Secondary signals (Development Pitch, Specialist Tension, Arsenal Dependency, Connected Changes, Platoon Vulnerability, Sample Size Caution) are advisory — if the capsule ignores a populated secondary signal, flag it as UNDERWEIGHTED_SIGNAL."

**`WarningCategory`** — Add `"UNDERWEIGHTED"` to the Literal type:

```python
WarningCategory = Literal["MISSED_SIGNAL", "UNSUPPORTED", "DIRECTION_ERROR", "OVERSTATED", "UNDERWEIGHTED"]
```

### `pipeline.py` — `write_pipeline_data_file()`

Add a signal extractor section between the data auditor and writer sections:

```python
sections.append(f"\n{sep}\nSIGNAL EXTRACTOR\n{sep}\n")
sections.append(f"## System Prompt\n\n{_SIGNAL_EXTRACTOR_PROMPT}\n")
sections.append(
    "## User Message\n\n"
    "[Receives: all 5 specialist outputs (same as writer input)]\n"
)
```

### `pipeline.py` — `PipelineResult`

Add `key_signals: KeySignals | None = None` field so downstream consumers (CLI output, data files) can inspect the extracted signals.

### No changes to:

- Specialist prompts or agents
- Data builders (`_build_stuff_input`, etc.)
- Data auditor prompt or agent
- Executive summary prompt or agent
- `report.py` (old pipeline)
