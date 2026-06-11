# Morning Editorial Run — Design

**Date:** 2026-06-12
**Status:** Approved for planning

## Purpose

A morning workflow that scans the most recent game date(s), identifies the
most interesting pitcher appearances, and produces a single editorial
digest: tailored, persona-voiced summaries of up to 10 starters and up to
10 relievers, grounded in scout signals and season context. The deliverable
is the digest only — no full per-pitcher pipeline runs.

The core idea is an **editorial workflow, not a one-shot**: a selector
(editor) chooses the slate and sets each story's angle; per-pick writers
turn each angle plus its supporting data into a short summary; deterministic
code assembles the digest.

## Flow

```
scout_appearances()           existing deterministic scoring (+ new role field)
        │  ranked ScoredAppearances per role, with fired signals
        ▼
Stage 1: SELECTOR             one LLM call, structured output
        │  CurationSlate: ≤10 SP picks + ≤10 RP picks
        │  (pitcher, category, angle, conviction)
        ▼
cue builder                   deterministic, polars — no LLM
        │  per pick: StoryCue = fired signals + selector angle
        │  + season context slice
        ▼
Stage 2: WRITERS              one LLM call per pick, concurrent
        │  tailored ~150–250 word summary each
        ▼
assembler                     deterministic
        └─► morning-runs/<game-date>/digest.md, slate.json,
            briefing.md, usage.json
```

## Components

### Role classification (new helper, `scout.py` or `data.py`)

No SP/RP column exists in the aggs. Derive role exactly from the statcast
parquet: filter to the window's game dates, group by
`(game_pk, inning_topbot)`, and take the pitcher with the minimum
`at_bat_number` in each group — that pitcher started for that side; every
other appearance in the game is a relief appearance. Openers classify as SP
(they started the game; that is what the field means).

`ScoredAppearance` gains `role: Literal["SP", "RP"]`.

### Scout changes (`scout.py`, `scout_cli.py`)

- `scout_appearances` ranks per role: the top N starters and top N
  relievers (default 25 each) feed the selector so both buckets have real
  competition. Scoring logic is unchanged.
- The scout CLI table gains a role column; `-n/--top` becomes per-role.
- `--curate` is repointed at the new structured selector and prints the
  slate (picks, categories, angles, convictions) without running Stage 2.
  The current streaming-prose curation path is deleted.

### Stage 1 — Selector (`curator.py`, evolved in place)

Keeps the existing signal-hierarchy editorial prompt (Clean Breakout /
Lab Project / Identity Crisis / Red Flag; process over results; pragmatic,
not breathless) but switches from streamed prose to structured output:

```python
class CurationPick(BaseModel):
    pitcher_id: int
    category: Literal["clean_breakout", "lab_project",
                      "identity_crisis", "red_flag"]
    angle: str = Field(min_length=1)   # one-sentence editorial angle — THE cue
    conviction: Literal["low", "medium", "high"]
    conviction_reason: str

class CurationSlate(BaseModel):
    starters: list[CurationPick]   # max 10
    relievers: list[CurationPick]  # max 10
```

- One call, full-tier model, low temperature (~0.2).
- The briefing presents SP and RP candidates in separately labeled
  sections, each with score, fired signals, and details.
- **Validation via `ModelRetry`:** every pick's `pitcher_id` must exist in
  the matching role bucket of the briefing; each list is capped at 10; the
  slate must contain at least one pick overall.
- On a thin day the selector picks fewer than 10 per role rather than
  padding — the prompt says this explicitly. "Up to 10" is the contract.
- The previous design's near-misses section is dropped: the Full Board
  section (below) covers non-picks deterministically.

### Cue builder (new `digest.py`, pure function)

For each pick, assemble a `StoryCue` briefing for the writer:

- appearance line: date, pitch count, role;
- every fired scout `Signal` (name, weight, detail);
- the selector's category, angle, conviction, and conviction reason;
- a compact season-context slice reusing `compute_season_baseline` and
  `compute_pitch_type_baseline`: season P+/S+/L+, velocity baseline, and
  per-pitch-type usage mix.

Deterministic and unit-testable with small polars fixtures. Enrichment is
built only for actual picks, never for the whole candidate board.

### Stage 2 — Per-pick writers (`digest.py`)

- One `Agent[None, str]` call per pick, all picks run concurrently via
  `asyncio.gather`.
- Full-tier model, temperature 0.7 (matching the pipeline writer's voice
  settings), plain model settings (no extended thinking), modest
  max_tokens (~2048).
- Persona-aware via the existing `personas.py` registry; default `scout`.
- Prompt contract: lead with the angle; ground every claim in the cue's
  numbers; scale tone to the stated conviction; close with what to watch
  next outing. Target 150–250 words.

### Assembler (`digest.py`, deterministic)

Renders `digest.md`:

```
# Morning Digest — <game-date>

## Starters         up to 10 summaries, slate order, category badges
## Relievers        up to 10 summaries, slate order, category badges
## The Full Board   every scored appearance from the window, grouped
                    SP/RP, sorted by score: name, score, and each fired
                    signal with its detail — deterministic, no LLM
<run cost footer>
```

### Cost tracking (new `costs.py`, promoted from `compare.py`)

- `PRICING`: per-1M-token input/output rates for the four models in play
  (claude-sonnet-4-6, claude-haiku-4-5, gemini-3.1-pro-preview,
  gemini-flash-latest).
- `UsageTracker`: records `result.usage()` per call, tagged by stage
  (`selector`, `writer:<pitcher>`). Unknown models still get token counts;
  their cost renders as `n/a` instead of crashing.
- Rendered cost block appears in the digest footer and on stdout:
  per-stage tokens in/out, per-model subtotal, grand total in dollars,
  wall clock. Raw per-call records go to `usage.json`.
- `compare.py` is refactored to import `PRICING`/`UsageTracker` from
  `costs.py` instead of carrying its own copies. It remains a standalone
  script otherwise.

### CLI (`cli.py` restructured with subparsers)

No new console script. The existing `pitcher-narratives` entry point gains
subcommands:

- `pitcher-narratives report -p 693433 ...` — the existing report flags,
  moved under an explicit subcommand. **Breaking change:** bare
  `pitcher-narratives -p ...` no longer works.
- `pitcher-narratives morning [--window 1] [--min-pitches 20]
  [--candidates 25] [--provider gemini] [--persona scout]
  [--out morning-runs]` — the morning run. `--candidates` is per role.

`pitcher-scout` and `pitcher-ask` stay untouched; folding them into
subcommands is a possible later cleanup, out of scope here.

## Outputs

Run directory is named by the **game date** of the scouted window's most
recent date (data is static, so wall-clock dates would lie):
`morning-runs/<YYYY-MM-DD>/`. Reruns of the same game date overwrite.

| File | Contents |
|------|----------|
| `digest.md` | The deliverable (also printed to stdout) |
| `slate.json` | Structured `CurationSlate` — persisted cues, enabling later cue-seeded full reports without rework |
| `briefing.md` | Exactly what the selector saw, for debugging (bench ground-truth pattern) |
| `usage.json` | Raw per-call token/cost records |

## Error handling

- No scored appearances in the window → friendly message, exit 0
  (a quiet day is not an error).
- Selector failure → pydantic-ai retries, then exit 1. No slate means
  nothing useful to salvage.
- A per-pick writer failure → degrade, don't die: that section falls back
  to a deterministic rendering of the cue (signals, angle, conviction),
  visibly marked as unwritten. Matches the pipeline's audit-degradation
  philosophy.
- Missing API key for the chosen provider → checked up front, exit 1.

## Testing

Existing patterns apply directly (`TestModel`/`FunctionModel` from
pydantic-ai):

- role classification against a small statcast fixture (starter, reliever,
  opener-replaced-mid-first edge);
- slate validation: per-role 10-cap, unknown-id → `ModelRetry`, empty-slate
  rejection, thin-day fewer-than-10 acceptance;
- cue builder against polars fixtures (signals + baselines rendered);
- writer fallback on a raising agent;
- assembler golden rendering (sections, ordering, Full Board grouping,
  cost footer);
- `UsageTracker` arithmetic and unknown-model `n/a`;
- CLI: subcommand routing, defaults, breaking-change behavior
  (bare `-p` errors with a useful message).

Cost: a normal morning is 1 selector call + up to 20 concurrent writer
calls — roughly comparable to one full pipeline run.

## Out of scope (deliberately)

- Cue-seeded full per-pitcher reports (`slate.json` makes this possible
  later; no pipeline changes now).
- Folding `pitcher-scout` / `pitcher-ask` into subcommands.
- Benching the digest with the judge harness (the seams line up:
  cue package = ground truth; nothing needed now).
- Scheduling/cron — the CLI is cron-friendly by construction, but no
  scheduler config ships with this work.
