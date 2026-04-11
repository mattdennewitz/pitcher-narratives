# Architecture Research: v1.10 Output Personas

**Milestone:** v1.10 Output Personas
**Researched:** 2026-04-11
**Scope:** How the `--persona {scout,analyst,generic}` flag should integrate into the existing multi-agent pipeline without disturbing specialists, anchor check, hallucination guard, or `pitcher-ask`.
**Confidence:** HIGH (grounded entirely in current source; no external API/library speculation).

## TL;DR Recommendation

1. New module `src/pitcher_narratives/personas.py` holds persona data (frozen dataclasses + a registry dict) and a single composer function `build_writer_system_prompt(persona) -> str`.
2. `make_pipeline_agents(provider, thinking, persona=SCOUT)` takes an optional persona argument with a default that preserves the current call graph for `analyst.py`. Writer Agent is constructed once with the composed system prompt baked in. No runtime `override()` games, no writer factory.
3. `_run_anchor_revision_loop` stays byte-identical. It already accepts the writer Agent as a parameter, so whichever writer the caller built is whichever writer does revisions. The generic instruction in `build_revision_message` is persona-agnostic and survives unchanged.
4. `build_writer_input` stays `str`-typed and stays shared across personas. Persona-specific output shape lives in the prompt, not the input.
5. CLI threading: `--persona` parses in `cli.parse_args`, threads through `generate_pipeline_streaming(ctx, provider, thinking, persona, _model_override)` as a new kwarg with default `"scout"`, forwards to `_run_pipeline`, forwards to `make_pipeline_agents`.
6. Output formatting: `# Scouting Report` heading stays as the outer wrapper for all personas. The generic persona emits sectioned markdown (`## Command`, `## Stuff`, summary table, etc.) as its capsule body. `cli.py` prints the capsule verbatim. Least-invasive.
7. Phase order: persona data module → pipeline wiring (scout parity gate) → analyst overlay → generic overlay (with anchor tolerance + hallucination-guard regression) → CLI wiring + `--list-personas` + docs. See Phase Ordering section for dependency rationale.

---

## 1. Persona Module Location & Shape

**Decision:** New file `src/pitcher_narratives/personas.py`.

### Rejected: inline in `pipeline.py`
`pipeline.py` is already ~1,400 lines across specialist prompts, writer prompt, data builders, agent factory, and orchestration. Adding three overlay strings plus a composer and a registry inside `pipeline.py` pushes it further toward the "everything bucket" anti-pattern. The v1.9 archive notes already flagged pipeline.py as the codebase's largest module.

### Rejected: in `config.py`
`config.py` is a hard constants + provider-map file (PROVIDERS, MINI_PROVIDERS, TOKEN_BUDGET_*, API_KEYS, `make_model_settings`, `cap_thinking`, `agent_kwargs`, `setup_logging`). It has zero prompt content today. Putting three large overlay strings there breaks its single responsibility ("shared constants and utilities shared by pipeline.py, analyst.py, and the CLI modules") and creates a weird import loop where pipeline.py imports prompt text from config.py.

### Accepted: new `personas.py`
Mirrors `signals.py` (which owns `KeySignals`, `SIGNAL_EXTRACTOR_PROMPT`, and `render_key_signals`) and `anchor.py` (which owns `ANCHOR_PROMPT`, `AnchorResult`, `AnchorWarning`, `build_anchor_message`, `build_revision_message`). Each of those modules owns "one agent role's data + prompts + helpers." Personas is the same shape: a new dimension of writer configuration.

### Responsibility
- Define a `Persona` frozen dataclass (not a pydantic BaseModel — personas are static code constants, not validated input, and dataclasses keep the import graph light).
- Define persona instances as module-level constants: `SCOUT`, `ANALYST`, `GENERIC`.
- Define a `PERSONAS: dict[str, Persona]` registry keyed by name for CLI lookup.
- Define `build_writer_system_prompt(persona: Persona) -> str` composer: `SHARED_WRITER_BASE + "\n\n" + persona.overlay`.
- Define `SHARED_WRITER_BASE` as the subset of `_WRITER_PROMPT` that every persona shares (the "always explain how Pitching+ works and the decisions it made" contract, directional consistency, temporal grounding, no-fabricated-metrics, key signals contract).
- Each persona's `.overlay` is the voice + length + shape instructions (scout's current "elite sabermetrically inclined baseball writer" framing, analyst's newsletter-teaching frame, generic's sectioned-format-with-summary-table frame).

### Dataclass (not pydantic) rationale
- No validation logic needed — personas are hand-authored code constants, not untrusted input.
- No `model_dump`/`model_validate` roundtrip needed — no serialization.
- Dataclasses import from stdlib; pydantic is heavier. The `pitcher-narratives --help` path is already careful about lazy imports (see `cli.py` lines 82-85).
- Frozen dataclasses are hashable and safely module-level — pydantic BaseModel instances are not frozen by default and create gotchas for module-level singletons.

### Proposed signatures
```python
# personas.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Persona:
    name: str                       # "scout", "analyst", "generic"
    display_name: str               # "Scout" for --list-personas
    overlay: str                    # voice/length/shape system-prompt fragment
    description: str                # one-liner for --list-personas help text

SHARED_WRITER_BASE: str             # module-level constant
SCOUT: Persona                      # module-level singleton
ANALYST: Persona
GENERIC: Persona
PERSONAS: dict[str, Persona]        # {"scout": SCOUT, "analyst": ANALYST, "generic": GENERIC}
DEFAULT_PERSONA: Persona = SCOUT

def build_writer_system_prompt(persona: Persona) -> str: ...
def get_persona(name: str) -> Persona: ...  # raises ValueError with known keys on miss
```

### Confidence: HIGH
Mirrors two existing precedents (`signals.py`, `anchor.py`). No novel patterns.

---

## 2. Writer Agent Construction

**Decision:** Option (a) with a default. `make_pipeline_agents(provider, thinking, persona=SCOUT)` takes an optional persona and bakes the composed system_prompt into the writer Agent at construction time.

### Why option (a) wins

#### Matches the existing factory contract exactly
`pipeline.py:1112-1162` constructs agents with `system_prompt=...` at instantiation. Every other agent in `PipelineAgents` follows this pattern. Option (a) extends the existing pattern with a single new parameter — one argument flows in, one Agent flows out, the rest of the pipeline is untouched.

```python
def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona = DEFAULT_PERSONA,  # NEW
) -> PipelineAgents:
    ...
    writer_prompt = build_writer_system_prompt(persona)  # NEW
    ...
    return PipelineAgents(
        ...
        writer=_writer(writer_prompt),  # was: _writer(_WRITER_PROMPT)
        ...
    )
```

#### The default matters for `analyst.py`
`analyst.py:618` calls `make_pipeline_agents(provider, thinking)` with two positional args as part of `pitcher-ask --pipeline`. The milestone explicitly forbids touching `ask_cli.py` or `analyst.py`. Defaulting `persona=SCOUT` in the factory signature means `analyst.py`'s existing call continues to work byte-identically. Without the default, the milestone's "no cross-cutting changes" quality gate fails.

#### Revision loop compatibility is free
`_run_anchor_revision_loop` already takes the writer Agent as a parameter (`writer_agent: Agent[None, str]`). Whatever writer Agent the caller constructed is the one that does revisions. If `make_pipeline_agents` baked the analyst overlay into the writer prompt, the revision loop automatically gets an analyst-voiced revision. Zero changes to `anchor.py`, zero changes to the revision loop, zero changes to `build_revision_message`.

### Why option (b) loses
A writer factory or a `dict[persona_name, Agent]` adds a level of indirection for no benefit. Only one writer runs per pipeline invocation — pre-constructing three and picking one is wasted work and wasted import-time token budget (system prompts are potentially 4-10KB each at the mid-case). It also forces `_run_pipeline` to carry the persona name through to pick the right agent, re-introducing the coupling option (a) avoids.

### Why option (c) loses
Runtime `Agent.override(system_prompt=...)` or `with_instructions(...)` is an advanced pydantic-ai pattern that the Stack researcher is investigating in parallel. Even if it exists and works:
- It's a mutation pattern — harder to test, harder to reason about, harder to snapshot in traces.
- It couples the pipeline orchestrator to the persona concept. Today the orchestrator only knows "a writer agent." Option (c) would require the orchestrator to know which persona to override with, which is strictly worse factoring than option (a) where the persona is fully absorbed at construction time.
- The existing codebase does not use `Agent.override` anywhere (grep confirms — the only `override` matches are `_model_override` parameters and the word "override" in prose comments). Introducing a new pydantic-ai concept for no benefit violates "least-invasive path."

### Confidence: HIGH
The factory pattern is the dominant idiom in `make_pipeline_agents`; option (a) slots in cleanly. The analyst.py constraint is load-bearing and confirmed by direct grep.

---

## 3. Revision Loop Compatibility

**Decision:** Zero changes to `_run_anchor_revision_loop`, zero changes to `anchor.py`.

### The loop is already persona-agnostic
`pipeline.py:1209-1276` signature:
```python
async def _run_anchor_revision_loop(
    *,
    anchor_agent: "Agent[None, AnchorResult]",
    writer_agent: "Agent[None, str]",
    synthesis: str,
    capsule: str,
    max_revisions: int,
    _model_override: Any = None,
) -> tuple[str, AnchorResult, int]:
```

The loop receives the writer Agent as an injected dependency. It has no idea whether that writer has the scout overlay, the analyst overlay, or the generic overlay baked in. It just calls `writer_agent.run(user_prompt=build_revision_message(...))` and trusts the Agent to speak in its own voice.

This is *exactly* the shape option (a) needs. Nothing to refactor.

### Is `build_revision_message` generic enough across all three personas?
The instruction text (`anchor.py:113-116`):
> "Revise the capsule to address ONLY the warnings listed above. Preserve the voice, structure, and all unflagged material. Do not add new analysis or metrics not in the briefing."

Yes, this is generic enough. It says "preserve the voice" (personas supply their own voice via system prompt), "preserve the structure" (personas emit different structures and this instruction lets each persona preserve its own), "preserve unflagged material." None of this is scout-specific.

### The real risk is the anchor check, not the revision loop
`ANCHOR_PROMPT` (`anchor.py:26-53`) was written assuming the writer emits prose paragraphs. It knows about:
- Missed key signals (persona-agnostic — all personas consume the same KeySignals)
- Unsupported claims (persona-agnostic)
- Directional errors (persona-agnostic)
- Overstated confidence (persona-agnostic)

The anchor prompt does NOT enforce "no bullet points" or "no headers" or "no tables." So in principle the prompt is persona-neutral. BUT — the `generic` persona emits a summary table INSIDE the capsule, and the anchor checker has never seen a structured table before. There's a non-zero risk the anchor agent returns a false-positive warning like "UNSUPPORTED: the capsule contains a '|—|—|' row not in the synthesis" or trips on numeric cells it treats as novel metric claims.

**Recommendation:** For the generic persona phase specifically, add a single sentence to `ANCHOR_PROMPT` or to the anchor user-message builder that says "the capsule may contain markdown headings and tables; validate their semantic content against the synthesis, not their formatting." This is the one place where the anchor check touches persona concerns, and it should be scoped to the phase that introduces the risk. Everything else stays intact.

An alternative is to pass a "format hint" through `build_anchor_message` (e.g., `build_anchor_message(synthesis, capsule, capsule_format="sectioned")`) and let the anchor prompt branch on it. This is more invasive but cleaner. **Flag for planner:** choose between (i) a one-line static prompt addendum that's always active, or (ii) a conditional format hint threaded through. (i) is least-invasive; (ii) is most principled. I lean toward (i) because the addendum costs nothing when the capsule is plain prose.

### Confidence: HIGH on loop compatibility, MEDIUM on anchor-check tolerance.
The loop compatibility claim is verified by reading the function signature directly. The anchor-tolerance claim is a prediction about LLM behavior that should be validated with goldens in Phase D.

---

## 4. `build_writer_input` Changes

**Decision:** No changes. The input stays `str`, stays shared across all personas.

### Rationale
`build_writer_input` at `pipeline.py:782-808` currently composes:
1. A pitcher header
2. An optional rendered Key Signals section (from `render_key_signals(key_signals)`)
3. Five specialist-output sections in a fixed order (stuff, location, run value, trends, game shape)

None of these pieces are persona-specific. They are the raw material. The persona is about how the writer *renders* that raw material, not about which raw material the writer receives.

Specifically:
- **Key signals rendering:** `render_key_signals` in `signals.py:53-64` produces a labeled bullet list. This is the briefing format the writer reads, not the output format the user reads. The analyst persona doesn't need a different input rendering — it needs a different output format (which comes from its system prompt).
- **Specialist order:** The writer prompt explicitly says "CRITICAL: These are INGREDIENTS, not sections to preserve." The fixed order (stuff → location → runvalue → trends → game_shape) is the writer's buffet, not the user's menu. Reordering them per persona would make the three personas solve different analytical problems, which is not what personas are for.
- **Bullets vs paragraphs in signals:** The key signals section is always a bulleted briefing in the writer's input. The generic persona rendering a table in its output is an output-shape decision (persona overlay), not an input-shape decision.
- **UserPrompt vs str:** The writer input is str today and the specialist inputs are UserPrompt (with CachePoints) for Gemini context caching. There's no persona reason to promote the writer input to UserPrompt — the persona doesn't affect cache boundaries. The only reason to change this is if we discover that caching specialist outputs across personas is valuable, which is out of scope for v1.10.

### The one place persona *could* touch the input
If the generic persona's "summary table" needs to cite specific pre-computed values that the specialists would not naturally mention, the writer would need those values explicitly in the input. For example, a table row like "Velocity | 94.2 mph | +0.3 vs season" requires the writer to know the velocity delta as a distinct fact, not just as prose buried in a specialist's paragraph.

**Flag for planner:** inspect the proposed generic-persona table schema during Phase D. If the table needs values that aren't already surfaced cleanly in the specialist outputs, two options:
1. Extract the needed values from `ctx` directly (low cost, keeps input unified) and append them to `build_writer_input` as a "Summary Table Facts" block that all personas ignore except generic.
2. Pipe the specialist outputs through a small extraction step. More architectural churn.

Default to option 1. Don't implement until the generic overlay is drafted and the table columns are nailed down.

### Confidence: HIGH on "no changes needed for scout + analyst." MEDIUM on "no changes needed for generic" — depends on final table spec.

---

## 5. CLI Threading Path

**Decision:** `persona` is a plain string kwarg that threads through cli → generate_pipeline_streaming → _run_pipeline → make_pipeline_agents, resolved to a `Persona` object at the `make_pipeline_agents` boundary.

### Full path

**`cli.py:parse_args`** — add the argparse argument, choices taken from `PERSONAS.keys()`:
```python
from pitcher_narratives.personas import PERSONAS
parser.add_argument(
    "--persona",
    choices=sorted(PERSONAS.keys()),
    default="scout",
    help="Writer voice and output shape (default: scout)",
)
```
Also add `--list-personas` as an `action="store_true"` flag that prints the registry and exits.

**`cli.py:main`** — pass `args.persona` into the pipeline call:
```python
pipe_result = generate_pipeline_streaming(
    ctx,
    provider=args.provider,
    thinking=args.thinking,
    persona=args.persona,  # NEW
    _model_override=model_override,
)
```

**`pipeline.generate_pipeline_streaming`** — new kwarg with default `"scout"` for backward compatibility with `analyst.py`:
```python
def generate_pipeline_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",  # NEW
    _model_override: Any = None,
) -> PipelineResult:
```

**`pipeline._run_pipeline`** — same shape:
```python
async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",  # NEW
    _model_override: Any = None,
) -> PipelineResult:
    ...
    from pitcher_narratives.personas import get_persona
    persona_obj = get_persona(persona)  # raises ValueError on bad name
    agents = make_pipeline_agents(provider, thinking, persona_obj)
```

**`pipeline.make_pipeline_agents`** — accepts the resolved `Persona` object:
```python
def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: "Persona" = ...,  # see below
) -> PipelineAgents:
```

### Why string at the boundary, Persona object inside
- **CLI and public API**: strings are stable, simple, and don't leak internal types. `generate_pipeline_streaming` is the public function; it should not force callers to import `Persona` from `personas.py`.
- **Factory internals**: the factory needs the overlay string and the name, which `Persona` carries. Resolving the string to the object at the `_run_pipeline` boundary is the correct seam.
- **`analyst.py` unchanged**: `analyst.py:618` calls `make_pipeline_agents(provider, thinking)` — the `persona` parameter defaults to the SCOUT singleton, `analyst.py` needs zero changes. For `make_pipeline_agents` to use a module-level `SCOUT` singleton as a default, import personas.py at the top of pipeline.py (negligible overhead, same module layer).

### Default value gotcha
The default `persona: "Persona" = SCOUT` in `make_pipeline_agents` creates a module-load-order dependency (pipeline.py must import personas.py before defining the function signature). This is fine — `personas.py` has no pipeline.py imports, so the dependency is one-way. Verify during implementation by running the test suite after adding the import.

### `--list-personas`
Lightweight: prints name, display_name, one-liner description from the registry and exits 0. No pipeline work.

### Confidence: HIGH
Threading path is mechanical and follows existing patterns (`--provider`, `--thinking` have the same shape).

---

## 6. Output Formatting (CLI Heading Stability)

**Decision:** `# Scouting Report` stays as the outer wrapper heading for all three personas. The capsule body is whatever the persona's writer prompt emits. `cli.py` prints the capsule verbatim — no restructuring.

### Current `cli.py:main` output sections (lines 152-218):
1. `# Scouting Report` (wrapper heading)
2. `<streamed capsule from writer>` (currently plain prose)
3. `# Executive Summary` + bullets
4. `# Stuff Analysis` + specialist output
5. `# Data Audit` + audit flags
6. `# Anchor Check` + revision status
7. `# Hallucination Check` (only if dirty)

### The generic persona's inner format
The milestone spec says generic wants "section breakouts + a summary table INSIDE the capsule, between `# Scouting Report` and the next heading." Translation: the writer's output *is* the sectioned content. Scout emits paragraphs, analyst emits paragraphs (newsletter voice), generic emits markdown with `##` sub-headings and a table.

### Why least-invasive is the right call
- `cli.py` already treats the capsule as an opaque streamed blob via `stream.stream_text(delta=True)`. It doesn't parse it, doesn't reformat it, doesn't re-heading it.
- The downstream sections (`# Executive Summary`, `# Stuff Analysis`, etc.) are CLI-owned wrapper content — they're stable across personas because they render pipeline metadata (audit flags, revision counts), not writer output.
- The generic persona's `##` sub-headings nest correctly under `# Scouting Report`. Markdown is hierarchical; `# Scouting Report` → `## Command` → (content) → `## Stuff` → (content) → table works out of the box.

### What NOT to do
- Do not add a `capsule_format` field to `PipelineResult` and branch in `cli.py`. That pushes persona awareness up into the CLI and creates a new surface area for regressions.
- Do not restructure `cli.py` to emit different heading sequences per persona. The milestone spec says `scout` must be byte-identical, and different heading sequences break that immediately.
- Do not inject the summary table after-the-fact in `cli.py`. The writer composes the capsule; the CLI prints it. Splitting responsibility is a maintenance nightmare.

### The one structural risk
If the generic persona emits `# Scouting Report` or `# Executive Summary` headings INSIDE its capsule (because it's a large LLM and those tokens are "natural" closing sections), the output becomes garbled. **Mitigation:** the generic persona's overlay system prompt must explicitly forbid `#` (h1) headings inside the capsule. Only `##` (h2) and below. This is a one-line constraint in the overlay string.

**Flag for planner:** the generic overlay must include: "Use `##` and `###` markdown headings for sections. Never use `#` (h1) — the outer report already owns h1."

### Confidence: HIGH on least-invasive path. MEDIUM on "LLM won't emit h1 headings even with a negative constraint" — this is a known failure mode and should be covered by a regex assertion in a golden test.

---

## 7. Phase Ordering

**Decision:** The proposed A → B → C → D → E ordering is correct, with one refinement and one dependency callout.

### Recommended order

**Phase A: Persona data module**
- Create `src/pitcher_narratives/personas.py` with `Persona` dataclass, `SHARED_WRITER_BASE` (extracted from `_WRITER_PROMPT`), `SCOUT` constant only, `PERSONAS` registry, `DEFAULT_PERSONA`, `build_writer_system_prompt`, `get_persona`.
- Tests: unit test that `build_writer_system_prompt(SCOUT)` produces a string equivalent to today's `_WRITER_PROMPT` (byte-for-byte or semantically equivalent, per the milestone's scout-preservation gate).
- No pipeline integration yet. Pipeline still uses `_WRITER_PROMPT` inline.
- **Exit gate:** test suite still green; personas.py importable; `SHARED_WRITER_BASE + SCOUT.overlay == _WRITER_PROMPT` (or a documented delta).

**Phase B: Pipeline integration (scout parity)**
- Modify `pipeline.py`: delete `_WRITER_PROMPT`, import from personas.py, add `persona` param to `make_pipeline_agents` with default SCOUT singleton, add `persona` kwarg to `_run_pipeline` and `generate_pipeline_streaming` with default `"scout"`.
- Do NOT touch `cli.py` yet. Do NOT touch `analyst.py`.
- Tests: existing pipeline tests still pass. Add a test that explicitly asserts `make_pipeline_agents("gemini", "high")` (no persona arg) and `make_pipeline_agents("gemini", "high", SCOUT)` produce writer agents with identical system prompts.
- Add a golden-output regression test: run the pipeline against a fixture pitcher with `--persona scout` and verify the output diff against a pre-v1.10 baseline is within tolerance.
- **Exit gate:** scout byte-parity regression test passes. `analyst.py` `pitcher-ask --pipeline` test still passes (confirms analyst.py's call site still works without modification).

**Phase C: Analyst persona**
- Add `ANALYST` to `personas.py` with its overlay string and a teaching-voice description.
- No pipeline changes (the plumbing already routes persona by name).
- Tests: golden output for `--persona analyst` (run one fixture pitcher, snapshot the output, verify the voice differs from scout, verify hallucination guard still clean, verify anchor check still clean).
- Early hook for wiring: Phase C can be run without CLI wiring by using `generate_pipeline_streaming(ctx, persona="analyst")` directly in a test. This lets us validate the analyst persona before committing to CLI surface area.
- **Exit gate:** analyst persona produces clean output against the hallucination guard; anchor check clean; tone-differs-from-scout golden matches.

**Phase D: Generic persona (highest-risk phase)**
- Add `GENERIC` to `personas.py` with its overlay string, including the "no h1 headings" constraint and the "use tables for summary" instruction.
- **Anchor-check tolerance work happens here, not earlier:** add the one-line addendum to `ANCHOR_PROMPT` in `anchor.py` that tells the anchor agent to validate semantic content of markdown tables and headings, not their formatting. This is the single touch to `anchor.py` in the entire milestone.
- **Hallucination-guard regression work happens here:** the generic persona's sectioned format makes it easier to hallucinate category labels ("## Putaway Pitch" with no supporting data from the specialists). Add targeted golden tests that check the generic capsule doesn't cite metrics or pitch behaviors that the specialists didn't mention.
- If `build_writer_input` needs to surface additional values for the summary table (see section 4), that work happens here. Add to `build_writer_input` only if the table cannot be filled from existing specialist text.
- **Exit gate:** generic persona produces clean output; no h1 headings in capsule; summary table renders; hallucination guard is clean; anchor check is clean (including table content); golden passes.

**Phase E: CLI wiring + --list-personas + docs**
- Add `--persona` and `--list-personas` to `cli.parse_args`.
- Thread `args.persona` into `generate_pipeline_streaming`.
- Update README.md persona documentation under `pitcher-narratives` section (the flag table around README line 67-75).
- Update METHODOLOGY.md to mention persona-aware writer prompts (line ~400 near the make_pipeline_agents description).
- Tests: CLI integration tests for `--persona scout`, `--persona analyst`, `--persona generic`, `--list-personas`, invalid persona name → exit 2.
- **Exit gate:** `pitcher-narratives -p 657277` (no persona flag) produces scout output byte-identical to pre-v1.10; `pitcher-narratives -p 657277 --persona generic` produces sectioned output; `pitcher-narratives --list-personas` lists the three personas.

### Should CLI wiring come earlier?
**No.** The default-argument strategy means the personas are reachable from the pipeline before the CLI knows about them. Running the pipeline via a test or a REPL with `persona="analyst"` is sufficient to validate Phases C and D without committing to CLI surface area. If Phase C or D reveals that the analyst/generic persona doesn't work and needs different plumbing, the CLI change hasn't shipped yet and there's nothing to roll back.

This also provides a useful "escape hatch": if the generic persona fails hard in Phase D, Phase E can ship with only scout + analyst available via `--persona`, and generic stays behind a feature flag until later. That optionality is worth preserving until the last phase.

### Dependency notes
- Phase A blocks B (B imports from personas.py).
- Phase B blocks C and D (C and D add overlays to personas.py but rely on the pipeline being persona-aware).
- C and D are **independent** of each other and can run in parallel if the planner wants to split them across two sub-phases or two contributors. They share no code.
- Phase E blocks on B, C, and D.

### What I'd add to the plan
1. **A hard byte-parity test between Phase A and Phase B.** Without it, you can't tell whether scout parity broke during the prompt extraction. Add a test that constructs a scout writer agent via Phase B's factory and diffs its system_prompt against a snapshot of `_WRITER_PROMPT` stored in a fixture file.
2. **An early spike in Phase A** to decide whether `SHARED_WRITER_BASE` is literally a substring of `_WRITER_PROMPT` or a rewrite. A substring is cheapest and safest; a rewrite risks silent scout regressions. Default to substring.
3. **A hallucination-guard test fixture specific to the generic persona** because the sectioned format has never been exercised. Add a known-clean capsule and a known-dirty capsule (with fabricated `## Putaway Pitch` section) and assert the guard flags the dirty one. This validates the guard still works against the new format.

### Confidence: HIGH
Dependency graph is mechanical. Phase D's risk flags are genuine and grounded in the anti-hallucination design of the pipeline.

---

## Files: New, Modified, and Don't-Touch

### NEW
| File | Responsibility |
|---|---|
| `src/pitcher_narratives/personas.py` | `Persona` dataclass, `SHARED_WRITER_BASE`, `SCOUT`/`ANALYST`/`GENERIC` constants, `PERSONAS` registry, `build_writer_system_prompt`, `get_persona`. |
| `tests/test_personas.py` | Unit tests for persona composer, registry lookup, scout byte-parity snapshot. |
| `tests/fixtures/writer_prompt_scout.txt` | Snapshot of pre-v1.10 `_WRITER_PROMPT` for scout parity test. |

### MODIFIED
| File | Changes |
|---|---|
| `src/pitcher_narratives/pipeline.py` | Delete `_WRITER_PROMPT`, import from personas.py, add `persona` param to `make_pipeline_agents`, add `persona` kwarg to `_run_pipeline` and `generate_pipeline_streaming`. |
| `src/pitcher_narratives/cli.py` | Add `--persona` and `--list-personas` argparse args, thread `args.persona` into `generate_pipeline_streaming`. |
| `src/pitcher_narratives/anchor.py` | **Phase D only.** One-line addendum to `ANCHOR_PROMPT` to tolerate tables and headings semantically. |
| `tests/test_pipeline.py` | Add persona-parity tests, persona-threading tests. |
| `tests/test_cli.py` | Add CLI arg tests for `--persona`. |
| `README.md` | Document `--persona` flag in the `pitcher-narratives` section. |
| `METHODOLOGY.md` | Mention persona-aware writer prompts in the pipeline architecture section. |

### DON'T TOUCH
Explicit call-outs from the milestone context, verified against the codebase:
- `src/pitcher_narratives/ask_cli.py` — Q&A CLI, milestone explicitly says untouched.
- `src/pitcher_narratives/analyst.py` — Q&A agent. Calls `make_pipeline_agents(provider, thinking)` at line 618; our default-argument strategy preserves this call site.
- `src/pitcher_narratives/scout.py` — Appearance scoring, unrelated to writer.
- `src/pitcher_narratives/scout_cli.py` — Scout CLI, unrelated.
- `src/pitcher_narratives/resolver.py` — Name resolver, unrelated.
- `src/pitcher_narratives/data.py` — Data loading, unrelated.
- `src/pitcher_narratives/engine.py` — Computation, unrelated.
- `src/pitcher_narratives/context.py` — Context assembly, unrelated.
- `src/pitcher_narratives/signals.py` — Shared by all personas; `KeySignals` and `render_key_signals` stay identical.
- Specialist prompts in `pipeline.py` (`_STUFF_SPECIALIST_PROMPT`, `_LOCATION_SPECIALIST_PROMPT`, etc.) — personas are writer-only.
- `_DATA_AUDITOR_PROMPT`, `_EXECUTIVE_SUMMARY_PROMPT` — both shared across personas.
- Hallucination guard (`check_hallucinated_metrics` in pipeline.py) — shared, unchanged.

---

## Function Signatures for Planner

### New (personas.py)
```python
@dataclass(frozen=True)
class Persona:
    name: str
    display_name: str
    overlay: str
    description: str

SHARED_WRITER_BASE: str
SCOUT: Persona
ANALYST: Persona
GENERIC: Persona
PERSONAS: dict[str, Persona]
DEFAULT_PERSONA: Persona  # = SCOUT

def build_writer_system_prompt(persona: Persona) -> str: ...
def get_persona(name: str) -> Persona: ...  # raises ValueError
```

### Modified (pipeline.py)
```python
def make_pipeline_agents(
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: Persona = DEFAULT_PERSONA,  # NEW, positional-compatible default
) -> PipelineAgents: ...

async def _run_pipeline(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",  # NEW
    _model_override: Any = None,
) -> PipelineResult: ...

def generate_pipeline_streaming(
    ctx: PitcherContext,
    *,
    provider: str = "gemini",
    thinking: ThinkingEffort = "high",
    persona: str = "scout",  # NEW
    _model_override: Any = None,
) -> PipelineResult: ...
```

### Unchanged (but called out for planner)
```python
# pipeline.py — UNCHANGED despite being in the writer path
def build_writer_input(
    ctx: PitcherContext,
    stuff: str, location: str, runvalue: str, trends: str, game_shape: str,
    *, key_signals: KeySignals | None = None,
) -> str: ...

# pipeline.py — UNCHANGED
async def _run_anchor_revision_loop(
    *, anchor_agent, writer_agent, synthesis, capsule, max_revisions, _model_override=None,
) -> tuple[str, AnchorResult, int]: ...

# anchor.py — UNCHANGED in Phases A-C; ONE-LINE prompt addendum in Phase D
ANCHOR_PROMPT: str

def build_revision_message(
    synthesis: str, capsule: str, warnings: list[AnchorWarning],
) -> UserPrompt: ...
```

---

## Risk Register (for Planner)

| Risk | Phase | Mitigation |
|---|---|---|
| Scout byte-parity broken during prompt extraction into `SHARED_WRITER_BASE + SCOUT.overlay` | A/B | Snapshot `_WRITER_PROMPT` to a fixture file; test asserts `build_writer_system_prompt(SCOUT) == fixture_text`. |
| Anchor check false-positives on generic persona's summary table | D | One-line addendum to `ANCHOR_PROMPT` (tolerate semantic-not-formatting); golden test with a known-clean generic capsule. |
| Hallucination guard false-negatives on generic persona's sectioned format | D | Targeted golden: known-clean capsule + known-dirty capsule (with fabricated section) to validate the guard still discriminates. |
| Generic persona emits h1 headings that collide with CLI wrapper headings | D | Explicit negative constraint in the generic overlay + regex assertion in the golden test. |
| `make_pipeline_agents` signature change breaks `analyst.py:618` | B | Default `persona=DEFAULT_PERSONA` in the signature. Verified: `analyst.py` calls with two positional args only. Test: run `pitcher-ask --pipeline` integration test after Phase B. |
| Summary table needs values not surfaced by specialists | D | Append a "Summary Table Facts" block to `build_writer_input` pulled from `ctx` directly; all personas ignore it except generic. |
| Persona name typo at CLI silently falls through | E | argparse `choices=sorted(PERSONAS.keys())` — invalid name exits 2 with a clear error. |

---

## Sources

All findings grounded in direct reads of the v1.10 codebase:
- `src/pitcher_narratives/pipeline.py` (writer prompt at 408-477, `build_writer_input` at 782-808, `PipelineAgents` at 1097-1109, `make_pipeline_agents` at 1112-1162, `_run_anchor_revision_loop` at 1209-1276, `_run_pipeline` at 1279-1399, `generate_pipeline_streaming` at 1402-1428)
- `src/pitcher_narratives/cli.py` (full file, 1-222)
- `src/pitcher_narratives/anchor.py` (full file, 1-117)
- `src/pitcher_narratives/config.py` (full file, 1-130)
- `src/pitcher_narratives/signals.py` (full file, 1-111)
- `src/pitcher_narratives/analyst.py` (line 618 — the load-bearing `make_pipeline_agents(provider, thinking)` call that pins the default-argument strategy)
- `.planning/PROJECT.md` (v1.10 milestone goal and constraints)

No external web sources consulted. No Context7 lookups required. All recommendations are grounded in existing code patterns (the `anchor.py` and `signals.py` modules serve as precedents for the proposed `personas.py` layout).
