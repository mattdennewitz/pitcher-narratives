# Phase 3 Sub-Plan: Converge the Analysis Spine

> **Gate:** This document must be committed before any Phase 3 coding begins.
> Parent plan: `docs/superpowers/plans/2026-06-15-narrative-consolidation.md` §Phase 3.
> Implementation issues: PLUS-105, PLUS-106, PLUS-107.

---

## Decisions resolved

### Decision 1 — What lives on `AnalyzedContext`

**Resolution: three fields only.**

```python
class AnalyzedContext(BaseModel):
    """Grounded specialist analysis produced by run_analysis_spine."""
    specialists: SpecialistOutputs   # clean outputs, post-audit
    key_signals: KeySignals | None = None  # None if signal extractor failed
    audit_flags: list[AuditFlag] = []     # empty if no specialist was flagged
```

No writer-input string, no terminal-layer artifacts. `build_writer_input(ctx, analyzed)` is
called by each terminal renderer at write time — the spine produces the analysis, not the
rendered prompt. Executive summary, anchor result, and `HallucinationReport` stay at the
terminal layer because they all depend on a specific capsule that the spine never sees.

Keeping the type narrow makes `run_analysis_spine` independently testable under TestModel
and avoids leaking terminal concerns into the shared path.

### Decision 2 — Morning: full spine, anchor + hallucination check opt-in and skipped

**Resolution: morning runs the full spine (specialists → audit → signal extraction) per
selected pick; anchor loop and hallucination check are not called.**

The anchor loop enforces KEY SIGNALS fidelity in a long-form capsule. The DIGEST_ITEM
contract (150–250 words, cue-grounded) is shorter and produced under tighter editorial
focus — enforcing the same anchor pass on a 200-word item adds overhead without meaningful
quality upside. The hallucination check likewise targets the longer-form capsule.

The high-value change for morning is the specialist spine itself: richer, grounded facts and
cross-specialist signals replace the current cue-only briefing. That is the Phase 3 goal.
Anchor and hallucination check remain available to morning as a future opt-in.

**Concurrency:** morning runs the spine for all selected picks concurrently
(`asyncio.gather`), then writes all summaries concurrently. Wall-clock stays dominated by
the single slowest pick, not the sum across picks.

**Thinking level:** use `"medium"` for morning's spine agents (vs. `"high"` for report).
Morning digest items are shorter and don't need maximum reasoning depth; `"medium"` cuts
latency without degrading the analytical signal.

**Expected cost impact:**
- Per pick: 5 specialist calls + 5 audit calls + 1 signal extraction = 11 LLM calls (vs. 1
  writer call today).
- Per-pick wall-clock: ~60–90 s for the spine phases (specialists/audits/signals in parallel
  waves).
- With concurrent picks: dominated by the slowest single pick.
- Token cost: roughly 15–20× per pick; acceptable given the small N of selected picks (~5–10).

**Profile validation:** capture `morning-runs/*/usage.json` before and after. Flag if
wall-clock exceeds 3× the pre-Phase-3 baseline — that signals sequential rather than
concurrent spine execution.

### Decision 3 — Post-processor threading

**Resolution: post-processors are explicit call sites at the terminal layer; the spine has
no knowledge of them.**

Both post-processors already exist as standalone functions:

- `_run_anchor_revision_loop(anchor_agent, writer_agent, synthesis, capsule, max_revisions)`
  → `(str, AnchorResult, int)` — `pipeline.py:1176`
- `check_hallucinated_metrics(capsule, ctx)` → `HallucinationReport` — `pipeline.py:1570`

Each terminal calls them explicitly after writing a capsule:

| Terminal | Anchor loop | Hallucination check |
|----------|-------------|---------------------|
| Report (`_run_pipeline`) | yes (current) | yes (current) |
| Ask (`ask_question_streaming`) | no | no |
| Morning (`write_pick_summaries`) | no | no |

No callbacks, no injection, no strategy objects. The spine is clean.

### Decision 4 — Ask path scope in PLUS-106

**Resolution: `ask_question_streaming` does not run the spine; PLUS-106's ask-path scope is
narrowed to a verification step only.**

`ask_question_streaming` is a tool-calling agent — it queries `PitcherContext` via
`get_pitcher_summary` / `get_pitch_detail` on demand. It has no inline specialist phase to
replace. The parent plan's reference to a shared spine in the ask path was written when the
now-deleted `ask_question_pipeline` still existed.

In PLUS-106, ask-path work is: confirm `ask_question_streaming` already uses
`build_system_prompt(persona, ANSWER)` (Phase 1 work; already the case) and that no
inline spine code exists. No `run_analysis_spine` call is added. The tool-calling approach
is already self-grounding and does not need pre-computed specialist analyses.

---

## Task split

| Step | Issue | Key files | Depends on |
|------|-------|-----------|------------|
| Step 1: Extract spine + define `AnalyzedContext` | PLUS-105 | `pipeline.py` | — |
| Step 2: Repoint report; verify ask clean | PLUS-106 | `pipeline.py`, `analyst.py` | PLUS-105 |
| Step 3: Morning opts into spine | PLUS-107 | `morning.py`, `digest.py`, `tests/test_morning.py` | PLUS-105 (not 106) |

Steps 2 and 3 can run in parallel worktrees after PLUS-105 lands.

---

## Steps (detailed)

### Step 1 — Define `AnalyzedContext`; extract `run_analysis_spine` (PLUS-105)

**File:** `src/pitcher_narratives/pipeline.py`

Add `AnalyzedContext` model (after `SpecialistOutputs`, before `PipelineResult`):

```python
class AnalyzedContext(BaseModel):
    """Grounded specialist analysis produced by run_analysis_spine."""
    specialists: SpecialistOutputs
    key_signals: KeySignals | None = None
    audit_flags: list[AuditFlag] = []
```

Add to `__all__`.

Extract `run_analysis_spine` (takes `agents: PipelineAgents` so morning can create agents
once and reuse across picks):

```python
async def run_analysis_spine(
    ctx: PitcherContext,
    *,
    agents: PipelineAgents,
    _model_override: Any = None,
) -> AnalyzedContext:
    """Specialist → audit → signal-extraction spine.

    Behavior-preserving extraction of the shared analysis phases.
    Does not run the writer, anchor check, or hallucination check.
    """
    raw = await run_specialists(
        agents.stuff, agents.location, agents.runvalue,
        agents.trends, agents.game_shape, ctx, _model_override,
    )
    specialist_agents = {
        "stuff": agents.stuff, "location": agents.location,
        "runvalue": agents.runvalue, "trends": agents.trends,
        "game_shape": agents.game_shape,
    }
    specialists, audit_flags = await audit_and_revise_specialists(
        raw, specialist_agents, agents.auditor, ctx, _model_override,
    )
    signal_input = build_writer_input(
        ctx, specialists.stuff, specialists.location,
        specialists.runvalue, specialists.trends, specialists.game_shape,
    )
    try:
        signal_result = await agents.signal_extractor.run(
            **agent_kwargs(signal_input, _model_override)
        )
        key_signals = signal_result.output
    except Exception:
        log.warning("Signal extractor failed, continuing without key signals.",
                    exc_info=True)
        key_signals = None
    return AnalyzedContext(
        specialists=specialists,
        key_signals=key_signals,
        audit_flags=audit_flags,
    )
```

**Keep existing `_run_pipeline` inlined sequence in place** — it is not touched in this
step. The new function lands beside the old code; no callers change yet.

**Test:** `tests/test_pipeline.py::test_run_analysis_spine`

Under `PITCHER_NARRATIVES_TEST_MODEL=1`:
- Call `run_analysis_spine(ctx, agents=agents)` for a fixed pitcher.
- Assert result is an `AnalyzedContext` instance.
- Assert all five `specialists.*` fields are non-empty strings.
- Assert `audit_flags` is a list.
- Assert the function produces the same specialist outputs as calling `run_specialists`
  directly with the same agents and context (deterministic under TestModel).

### Step 2 — Repoint report to spine; verify ask (PLUS-106)

**Files:** `src/pitcher_narratives/pipeline.py`, `src/pitcher_narratives/analyst.py`

In `_run_pipeline`, replace the inlined Phase 1 → 1.5 → 1.75 block:

```python
# Replace all of:
#   raw_specialists = await run_specialists(...)
#   specialists, audit_flags = await audit_and_revise_specialists(...)
#   signal_result = await agents.signal_extractor.run(...)
#   key_signals = ...
# With:
analyzed = await run_analysis_spine(ctx, agents=agents, _model_override=_model_override)
specialists = analyzed.specialists
audit_flags = analyzed.audit_flags
key_signals = analyzed.key_signals
```

Everything from Phase 2 onward (writer, summary, anchor, explainer check) is unchanged.

In `analyst.py`:
- Confirm `ask_question_streaming` uses `build_system_prompt(persona, ANSWER)` ✓
- Confirm no inline `run_specialists` / `audit_and_revise_specialists` calls exist ✓
- No code changes needed.

**Verification:**

```bash
# One def, one call site (report). Ask has zero.
grep -rn "run_analysis_spine" src
# → pipeline.py: 1 def, 1 call

# No inline run_specialists outside of run_analysis_spine itself
grep -n "await run_specialists\|await audit_and_revise_specialists" src/pitcher_narratives/pipeline.py
# → exactly 1 each, both inside run_analysis_spine

PITCHER_NARRATIVES_TEST_MODEL=1 uv run pytest -q tests/test_pipeline.py tests/test_analyst.py
```

### Step 3 — Morning opts into the spine (PLUS-107)

**Files:** `src/pitcher_narratives/morning.py`, `src/pitcher_narratives/digest.py`,
`tests/test_morning.py`

**Sub-step 3a — Create shared agents once per morning run.**

In `run_morning`, before `_llm_stages`, create a single `PipelineAgents` instance:

```python
from pitcher_narratives.pipeline import make_pipeline_agents, run_analysis_spine

spine_agents = make_pipeline_agents(provider, "medium", persona)
```

`"medium"` thinking for morning (lighter than report's `"high"`).

**Sub-step 3b — Run spine concurrently across picks.**

Inside `_llm_stages`, replace the sequential per-pick cue-building loop with a concurrent
spine run:

```python
async def _build_pick(
    p: CurationPick,
) -> tuple[int, str, PitcherContext, AnalyzedContext] | None:
    try:
        ctx = _load_pitcher_context(p.pitcher_id)
        analyzed = await run_analysis_spine(
            ctx, agents=spine_agents, _model_override=_writer_override,
        )
        cue = build_story_cue_from_context(appearances[p.pitcher_id], p, ctx)
        return p.pitcher_id, cue, ctx, analyzed
    except Exception:
        log.error(
            "Spine failed for pitcher_id=%d (%s); skipping pick.",
            p.pitcher_id, appearances[p.pitcher_id].pitcher_name, exc_info=True,
        )
        return None

build_results = await asyncio.gather(*[_build_pick(p) for p in picks])

cues: dict[int, str] = {}
analyzed_contexts: dict[int, AnalyzedContext] = {}
for result in build_results:
    if result is None:
        continue
    pid, cue, _ctx, analyzed = result
    cues[pid] = cue
    analyzed_contexts[pid] = analyzed

picks = [p for p in picks if p.pitcher_id in cues]
```

**Sub-step 3c — Enrich the cue with key signals before writing.**

In `digest.py`, add a helper:

```python
def enrich_cue_with_signals(cue: str, analyzed: AnalyzedContext) -> str:
    """Prepend key signals to a story cue if the spine produced them."""
    if analyzed.key_signals is None:
        return cue
    return render_key_signals(analyzed.key_signals) + "\n\n" + cue
```

Apply it in `write_pick_summaries` (or in the caller loop) before passing the cue to the
writer agent. The DIGEST_ITEM writer now sees both the cue facts and the cross-specialist
signals — it can weave signals into the "what-to-watch" close without changing its system
prompt.

**Sub-step 3d — Thread `analyzed_contexts` into `write_pick_summaries`.**

```python
async def write_pick_summaries(
    picks: list[CurationPick],
    cues: dict[int, str],
    appearances: dict[int, ScoredAppearance],
    *,
    analyzed_contexts: dict[int, AnalyzedContext] | None = None,  # new
    provider: str,
    persona: Persona,
    tracker: UsageTracker,
    _model_override: object = None,
) -> dict[int, str]:
```

When `analyzed_contexts` is provided, enrich each cue before passing it to the writer.
When absent (legacy / test fallback), cue is used as-is — backward-compatible.

**Test:** `tests/test_morning.py::test_morning_spine_integration`

Under `PITCHER_NARRATIVES_TEST_MODEL=1`:
- Call the `_llm_stages` inner function with `_writer_override=TestModel(...)`.
- Assert `analyzed_contexts` is populated with one entry per pick.
- Assert each `AnalyzedContext.specialists.stuff` is non-empty.
- Assert `write_pick_summaries` receives a non-empty `analyzed_contexts`.
- Assert the returned `summaries` dict has one entry per pick (digest.md renders successfully).

---

## Verification (matches parent plan §Phase 3)

```bash
# Full targeted suite
PITCHER_NARRATIVES_TEST_MODEL=1 uv run pytest -q \
    tests/test_pipeline.py tests/test_analyst.py tests/test_morning.py

# One def, two call sites (report + morning); ask has zero
grep -rn "run_analysis_spine" src
# → pipeline.py: 1 def, 1 call
# → morning.py:  1 call

# No duplicated inline spine phases
grep -n "await run_specialists\|await audit_and_revise_specialists" src/pitcher_narratives/pipeline.py
# → exactly 1 each, inside run_analysis_spine

# Lint + types clean
uv run ruff check src tests
uv run ty check 2>&1 | tail -1
```

**Green when:**
- `AnalyzedContext` defined; `run_analysis_spine` has one `def` and two callers.
- `_run_pipeline` (report) has no inline specialist/audit/signal blocks — they live in the spine.
- Morning builds `AnalyzedContext` per pick concurrently; passes enriched cues to writers.
- Anchor loop and hallucination check are not called from morning (verified by grep or test mock).
- `ask_question_streaming` unchanged (no spine call added).
- Full suite green under TestModel. ruff + ty clean.

---

## Out of scope

- Adding anchor loop or hallucination check to morning (future opt-in; not Phase 3).
- Pre-computing the spine for the ask path (ask remains tool-calling; self-grounding).
- Changing `PipelineAgents` fields, agent prompts, or `_WEIGHTS`.
- Streaming individual specialist outputs during morning (blocking gather is fine).
- Any change to `build_story_cue_from_context` section names (writer prompts rely on them).
- Phase 4 entry-point merge.
