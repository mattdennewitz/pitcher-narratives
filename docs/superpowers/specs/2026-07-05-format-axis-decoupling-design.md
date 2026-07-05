# Format Axis Decoupling (WS3) — Design

**Date:** 2026-07-05
**Status:** Approved design (full decouple), pending implementation plan
**Topic:** Make output *structure* an axis orthogonal to *voice* (`Persona`) and
*analytical framing* (`NarrationMode`), collapsing the multiplying
`OutputContract` constants into a composable set.

---

## 1. Problem

`NarrationMode.contracts` binds `persona_id → OutputContract` (`personas.py:539`),
so choosing a persona also chooses a *structure*:

- `report + scout` → `SCOUT_REPORT` → prose capsule (`personas.py:435`,
  `_CAPSULE_STRUCTURE` `personas.py:216`)
- `report + analyst` → `NEWSLETTER` → 450–800-word prose (`personas.py:442`,
  `_NEWSLETTER_STRUCTURE` `personas.py:230`)
- `report + generic` → `SECTIONED` → six `##` sections + a summary table
  (`personas.py:449`, `_SECTIONED_STRUCTURE` `personas.py:251`)

So the "same" scouting report has three structurally different bodies depending
on `--persona`, even though `Persona` claims to carry "tone/vocabulary only — no
length or structure" (`personas.py:66`). The coupling also **multiplies
contracts per mode**: there are **8** `OutputContract` instances today —

| Contract | Structure | Line |
|---|---|---|
| `SCOUT_REPORT` | `_CAPSULE_STRUCTURE` | `personas.py:435` |
| `NEWSLETTER` | `_NEWSLETTER_STRUCTURE` | `personas.py:442` |
| `SECTIONED` | `_SECTIONED_STRUCTURE` | `personas.py:449` |
| `BRIEF` | `_BRIEF_STRUCTURE` | `personas.py:417` |
| `RECAP_BRIEF` | `_RECAP_STRUCTURE` | `personas.py:428` |
| `CHANGES_SCOUT` | `_CHANGES_SCOUT_STRUCTURE` | `personas.py:456` |
| `CHANGES_ANALYST` | `_CHANGES_NEWSLETTER_STRUCTURE` | `personas.py:463` |
| `CHANGES_GENERIC` | `_CHANGES_SUMMARY_STRUCTURE` | `personas.py:470` |

`CHANGES_*` mirror the three report contracts; `BRIEF`/`RECAP_BRIEF` are
near-identical (the comment at `personas.py:412-416` notes they "never
co-occur"). Every new `mode × persona` cell needs a new hand-written constant.
`_SECTIONED_STRUCTURE` even carries a `STRUCTURE OVERRIDE` block
(`personas.py:255-260`) to countermand the scout overlay's "no headers/tables"
rule — a direct symptom of voice and structure being tangled.

## 2. Decision

**Full decouple** (2026-07-05). Structure becomes an orthogonal `Format` axis
selectable via `--format`; `Persona` reverts to voice-only in fact, not just in
docstring. The general-fan-gets-sections behavior was an artifact of the binding,
not intended product design; after this change it is reachable as
`--persona generic --format sectioned` but not implied by the persona.

## 3. Key facts established (with evidence)

- `build_system_prompt` (`personas.py:778-816`) already composes the prompt as an
  ordered concatenation: `SHARED_WRITER_BASE` + `contract.input_framing` +
  persona voice chain (parent overlay → own overlay, with EXPLAIN-THE-MODEL
  addenda) + `contract.structure`. The `Format` axis is a *decomposition of
  `contract`*, not a new composition mechanism.
- `OutputContract` bundles three concerns today (`personas.py:80-93`):
  `length_target`, `structure`, `input_framing`. `input_framing` is a
  **mode-level** concern (synthesis vs brief-from-report vs synthesis-no-explain),
  while `structure`/`length_target` are **format-level**.
- EXPLAIN-THE-MODEL addenda are gated on the *framing* carrying the mandate
  (`personas.py:800-814`), and `explain_model=False` strips it
  (`personas.py:800-804`). This logic keys off framing text, so it survives a
  framing-moves-to-mode refactor unchanged.
- `build_writer_system_prompt` already falls back to `SCOUT_REPORT` for personas
  absent from a mode's contract map (`personas.py:832-840`) — proof the
  persona↔contract binding is loose and safe to replace.
- `test_voice_golden.py` pins composed-prompt bytes; `test_personas.py` and
  `test_role_guidance.py` exercise composition. These are the guardrails.

## 4. Target design

Three orthogonal axes, composed at build time:

| Axis | Owns | Members |
|------|------|---------|
| **`NarrationMode`** | `input_framing`, `validation`, `temporal_frame`, focus, `title`, `distill` | report, recap, changes |
| **`Persona`** | voice overlay + explain-model addendum *(unchanged)* | scout, analyst, generic |
| **`Format`** *(new)* | `structure` template + `length_target` | prose, newsletter, sectioned, brief |

```python
@dataclass(frozen=True)
class Format:
    id: str
    length_target: tuple[int, int]
    structure: str

# input_framing moves onto NarrationMode:
#   report/changes → _SYNTHESIS_FRAMING (with EXPLAIN THE MODEL)
#   recap          → _SYNTHESIS_RULES   (bare, no EXPLAIN THE MODEL)
```

New signature:

```python
def build_writer_system_prompt(
    persona: Persona, mode: NarrationMode, fmt: Format, *, explain_model=True
) -> str:
    # SHARED_WRITER_BASE + mode.input_framing + persona voice chain + fmt.structure
```

### 4.1 Contract collapse

- 8 `OutputContract` constants → **3 mode framings + 3 persona voices + 4
  Formats** (additive, not multiplicative).
- `BRIEF` and `RECAP_BRIEF` merge into one `brief` Format; the
  "distill-from-report" vs "write-from-analyses" difference is a *mode framing*
  concern, not a structure concern.
- `CHANGES_*` disappear entirely — `changes` mode reuses the same Formats;
  "report only what moved" lives in the mode's framing/focus, not in a per-persona
  structure clone. Verify the `_CHANGES_MANDATE` (`personas.py:333`) is
  framing-level (it is: it's about *what* to write, not *how* to shape it).
- Delete the `_SECTIONED_STRUCTURE` `STRUCTURE OVERRIDE` (`personas.py:255-260`):
  once structure isn't fighting a persona overlay, the sectioned Format simply
  *is* the structure.

### 4.2 Default bindings (behavior preservation)

`NarrationMode` keeps a `default_format` per persona so today's output is
reproduced when `--format` is omitted:

| mode | scout | analyst | generic |
|------|-------|---------|---------|
| report | prose | newsletter | sectioned |
| recap | brief | brief | brief |
| changes | prose | newsletter | sectioned |

`--format` overrides the default. The default map is the *only* place the old
coupling survives — now explicit and overridable, not baked into the type.

### 4.3 CLI

- Add `--format {prose,newsletter,sectioned,brief}` to `report` (`cli.py:36`).
- Guardrails: warn (don't error) on odd combos, e.g. `recap + sectioned`
  (a 40–90-word brief with six headings is incoherent) — or clamp recap to
  `brief`. Decide at plan time.

## 5. Migration strategy (byte-identity first)

1. Introduce `Format` + move `input_framing` to `NarrationMode`, but keep the
   old `OutputContract` constants as *derived* values so
   `build_writer_system_prompt` produces **byte-identical** prompts under default
   bindings. Run `test_voice_golden.py` green with **no re-baseline**.
2. Only then wire `--format` and delete the redundant `CHANGES_*` / `BRIEF`
   duplicates, re-baselining goldens *deliberately* if any bytes shift.
3. TDD throughout: the golden suite is the contract that behavior didn't change.

## 6. Testing

- `test_personas`: new axis registry invariants; `default_format` map covers
  every `(mode, persona)`; composition order preserved.
- `test_voice_golden`: byte-identical under defaults in phase 1; re-baselined
  intentionally in phase 2 with the diff reviewed.
- `test_cli`: `--format` override; incoherent-combo handling.

## 7. Open questions

- `recap + sectioned`: warn, or hard-clamp recap to `brief`? (Clamp is safer.)
- Does `length_target` belong to `Format` alone, or can a persona tighten it?
  Today lengths are per-contract (i.e. per persona+mode). Proposal puts length on
  `Format`; if analyst's newsletter length must differ from a generic newsletter,
  that argues length is `(Format, Persona)` — resolve by inspecting whether any
  two personas share a Format with different `length_target` today. (They do not:
  each structure maps 1:1 to a persona currently, so `Format`-owned length is
  safe.)
