# Single-Voice Narratives — Design

**Date:** 2026-07-05
**Status:** Approved design, pending implementation plan
**Supersedes:** `2026-07-05-format-axis-decoupling-design.md` (WS3). The
format-axis approach (a `--format` axis orthogonal to `Persona`) is abandoned:
by collapsing to a single voice, output *structure* binds to the deliverable
(mode), so there is no orthogonal format to add.

---

## 1. Problem

The tool carries three writer voices (`scout`, `analyst`, `generic`) and eight
`OutputContract` constants wired through a `persona → contract` map per mode
(`personas.py`). Choosing a persona silently swaps *structure*, not just voice;
every `mode × persona` cell needs a hand-written contract; and the outputs
"feel messy and inconsistent" because the same deliverable has three different
bodies depending on `--persona`.

The real product need is narrower than the machinery: **one voice, a few
purpose-built deliverables, all off the same analytical spine.** The three
voices are not three products — they are accidental complexity. Eliminating two
of them (and the axes that multiply them) is the simplification.

## 2. Decision

- **One voice.** A single writer voice; `analyst` and `generic` are deleted.
- **Three deliverables, one spine.** Every deliverable runs the identical
  analytical spine (5 specialists → data audit → signal extraction → writer →
  anchor/fact validation). This is what makes all outputs internally accurate
  and mutually consistent: one analysis, one voice, different purposes.
- **Structure binds to the deliverable (mode), not the voice.** The `Persona ×
  OutputContract` matrix collapses; each mode owns its own structure, framing,
  and length.
- **The scouting report explains the player through the lens of the model.**
  The player is the subject; the model is *how* we explain him — what it sees,
  what it weighted, why it graded him as it did — used to illuminate the pitcher,
  not admired for its own sake. `EXPLAIN THE MODEL` is **core** to the report
  (and changes) framing, not decoration.

## 3. The voice

A field-facing analyst/scout hybrid — "the type who sits between the team and
the front office." It keeps the scout register (direct, sabermetric, analyst-to-
analyst, no cheerleading, no clichés) and folds in the *explain-the-model*
instinct (contextualize S+/L+/P+ on first reference; say what the model
decided), but **drops** the newsletter chattiness: no first-person-plural "what
we're seeing here," no coffee-table digressions, no dumbing-down.

Mechanically this becomes a single voice constant. The `Persona` dataclass, the
`PERSONAS` registry, `get_persona`, the parent-chain inheritance, and the
per-persona `explain_model_addendum` machinery are all retired — there is one
voice, so there is nothing to select, inherit, or disambiguate. Downstream
`persona=` parameters are removed from the pipeline and CLI signatures.

## 4. The three deliverables

| Deliverable | Mode id | Output | Length | `distill` |
|---|---|---|---|---|
| **Scouting report** | `report` | Exec-summary bullets **+** flowing prose narrative (model-focused) | 350–600 words | `True` (bullets) |
| **Changes report** | `changes` | Exec-summary bullets **+** medium prose on what moved (recent window vs longer history) | 250–450 words | `True` (bullets) |
| **Morning report** | `recap` | A single capsule on the most recent appearance. **No bullets.** | 60–120 words | `False` |

- **Scouting report** — a narrative that explains the pitcher through the lens
  of the model: the player is the subject, the model is how we read him, over a
  period. Public/newsletter-usable. Bullets are the at-a-glance layer; the prose
  is the read.
- **Changes report** — compares a short recent window against a longer
  historical period; leads with the biggest shift; reports what moved.
- **Morning report** — the per-pitcher capsule about yesterday's outing. The
  `morning` command selects pitchers off the scoreboard and emits one morning
  report per selected pitcher, all from the shared spine.

### 4.1 Per-mode framing (where "model-focused" lives)

- `report` → synthesis framing **+ EXPLAIN THE MODEL** (lead from the model's
  read).
- `changes` → synthesis framing + change-mandate ("report only what moved")
  **+ EXPLAIN THE MODEL**.
- `recap` → synthesis framing (bare); the capsule has no room to teach the
  model, so no `EXPLAIN THE MODEL`.

The existing `--no-explain-model` flag is retained: it strips the
`EXPLAIN THE MODEL` mandate from the composed prompt for readers who already
know the grading system. With one voice, the per-persona explain-model addenda
disappear; the single voice explains at the right depth inherently.

## 5. Architecture

### 5.1 `personas.py` collapse

- **One voice constant** replaces the `Persona` dataclass + registry.
- **Structure moves onto `NarrationMode`.** Each mode owns `structure`,
  `input_framing`, and `length_target` directly. The per-persona `contracts`
  map, the never-built `Format` axis, and 5 of the 8 `OutputContract` constants
  disappear.
- **Three modes, three structures.** `report`, `changes`, `recap`.
- **Composition flattens** to:

  ```python
  def build_writer_system_prompt(mode: NarrationMode, *, explain_model: bool = True) -> str:
      # SHARED_WRITER_BASE + mode.input_framing + WRITER_VOICE + mode.structure
  ```

  The `persona` argument is gone. `SHARED_WRITER_BASE` (universal analytical
  rules) and the synthesis-framing constants are unchanged in role.

### 5.2 Pipeline

- `make_pipeline_agents(provider, thinking, mode, *, explain_model)` — the
  `persona` parameter is removed; the writer prompt composes from `mode` alone
  (`pipeline.py:1655`). The same removal threads down through `_run_pipeline`,
  `generate_pipeline_streaming`, and `run_narration_modes`.
- The shared spine (specialists, auditor, capsule auditor, anchor, signal
  extractor) is unchanged.

### 5.3 Drop the separate short "brief"

Today `distill=True` produces **two** distillations: the executive-summary
bullets *and* a separate short "brief" (`BRIEF` contract, wired at
`pipeline.py:1670`, surfaced as `PipelineResult.brief`). The deliverable spec is
bullets + body — no third short-form — and the **morning** report now serves the
short-form need. So the separate brief is **dropped**: the `BRIEF` contract, its
`_brief` agent, the `brief` field on `PipelineResult`, and its call site are all
removed. Report/changes keep only exec-summary bullets + body. This deletes the
last `OutputContract` and one agent call per run.

### 5.4 CLI

- `report`: remove `--persona` and `--list-personas`. No `--format` (superseded).
  `--mode {report,changes,recap}` stays.
- `morning`: emits the morning-mode capsule per scoreboard-selected pitcher off
  the shared spine.

## 6. What gets deleted

- Personas `analyst`, `generic`; the `Persona` dataclass, `PERSONAS` registry,
  `get_persona`, parent-chain and per-persona explain-model addenda.
- `OutputContract` constants: `NEWSLETTER`, `SECTIONED`, `CHANGES_SCOUT`,
  `CHANGES_ANALYST`, `CHANGES_GENERIC`, `RECAP_BRIEF`, `BRIEF` (structure/framing
  absorbed onto the three modes; brief dropped entirely).
- The `persona` parameter across pipeline + CLI signatures; the `contracts`
  map on `NarrationMode`.
- `PipelineResult.brief` and the `_brief` distillation agent.
- The abandoned `Format` axis (never built).

## 7. Migration & testing — full re-baseline

Byte-identity does **not** apply here (unlike the abandoned WS3 plan): folding
explain-model into the voice and rebinding structure to the mode changes every
composed prompt intentionally.

- **Fixtures:** delete the 6 `analyst`/`generic` fixtures
  (`tests/fixtures/{writer,recap_writer,changes_writer}_prompt_{analyst,generic}.txt`);
  re-baseline **3** — one voice × `report`/`changes`/`recap` — with reviewed
  diffs. (Down from 9.)
- **Coupled tests to rewrite** (from the code inventory):
  - `test_personas.py` — contract-identity assertions (`REPORT.contracts[...] is
    NEWSLETTER`, etc.), `.input_framing` reads (~11 sites), `length_target`
    assertions, the `OutputContract` rejection tests, the golden-matrix and
    per-mode golden tests, BRIEF tests (8), the changes-contract trio test.
  - `test_voice_golden.py` — drop per-persona parametrization; assert
    single-voice invariants (voice present; `EXPLAIN THE MODEL` present for
    report/changes, absent for recap; each mode's structure phrase present;
    `SHARED_WRITER_BASE` leads).
  - `test_pipeline_persona_wiring.py` — `persona` arg removed; assert
    `make_pipeline_agents`/`generate_pipeline_streaming` signatures no longer
    carry `persona`; writer prompt composes from `mode`.
  - `test_pipeline.py` — remove BRIEF wiring assertions (`test_brief_uses_mini_model`,
    `PipelineResult.brief` populated); `run_narration_modes` still gates
    distillation by mode.
  - `test_signals.py`, `test_morning.py` — drop `persona=`/persona-positional
    calls; `test_cli.py` — remove `--persona`/`--list-personas` coverage, add
    single-voice report coverage.
- **TDD throughout:** each mode's new composed prompt is pinned to a
  deliberately-authored fixture; invariants (§ above) guard against silent drift.

## 8. Scope & phases

One coherent spec → one implementation plan with ordered phases:

1. **Voice collapse** — single voice constant; retire `Persona`/registry/addenda.
2. **Mode-owned structure** — move structure/framing/length onto the three
   modes; delete the contract constants and `contracts` map; rewrite
   `build_writer_system_prompt`.
3. **Pipeline + CLI cleanup** — remove `persona` params; drop the separate
   brief; remove `--persona`/`--list-personas`.
4. **Morning-command wiring** — emit morning-mode capsules per scoreboard-
   selected pitcher.

Each phase ends green with re-baselined fixtures and rewritten tests.

## 9. Future work (not built now)

**Model breakdown.** A distinct second output rendered from the same spine — the
diagnostic scouting sheet: labeled sections (`## Stuff / ## Location / ## Run
Value & Execution / ## Trend / ## Game Shape`) plus a summary table, for the
operator/analyst "pro view." Kept separate from the narrative on purpose: a
public narrative and a per-dimension audit sheet are read in different modes by
different people, and stapling them re-imports the prose-vs-sections tangle the
old `generic` persona suffered (its `STRUCTURE OVERRIDE` block existed only to
stop the sections fighting the voice). The old `_SECTIONED_STRUCTURE` is a
starting point for this future spec.

## 10. Non-goals

- No change to the analysis spine, specialists, signal extraction, or the
  grounding/validation stack.
- No change to what the modes *mean* (report/changes/recap) or their validation
  policy values.
- No new voices or modes.
- The model breakdown is designed here only in outline; it is a separate future
  spec + plan.
