---
name: derived-signal-feature
description: Use when adding a new pre-computed insight, metric, signal, classification, or tag that must reach the LLM-written narrative in this repo — or when a report "should mention X" and X is derivable from the data.
audience: builder
---

# Adding a Derived Signal End-to-End

Core principle: the engine does arithmetic, the LLM does narration. A new insight ships as raw numbers + a deterministic label + an inline definition, threaded through every pipeline hop. Worked example: `shape.py` (dead-zone fastballs) — read it alongside this recipe.

## Recipe (in order, TDD at every step)

1. **Compute module** (`src/pitcher_narratives/<name>.py`): dataclasses + `compute_<x>(data: PitcherData) -> Profile | None`. League baseline table with a module-level cache (see `_slot_expectations_cache`); min-sample constants (`_MIN_*`) with graceful skips; deterministic tag strings from thresholds. Decide season vs window: physical traits use full season, trends use the window.
2. **Renderer in the same module**: `render_<x>(profile) -> str` returning `"## Section"` + one self-documenting explanation line (define every label inline — consumers have no outside knowledge) + ≤4 entries. Empty string when no data, so callers skip the section.
3. **Context** (`context.py`): add field to `PitcherContext` **with `= None` default** (tests construct it manually); call the renderer in `to_prompt()`; wire `compute_<x>(data)` into `assemble_pitcher_context` (the single assembly point). Keep total prompt under the 2,000-token budget test.
4. **Specialist** (`pipeline.py`): append the rendered section to the relevant `_build_*_input` (stuff = physics, trend = deltas, etc.); add an UPPERCASE interpretation rule to that specialist's prompt — scope it "when the section is present" and make citation mandatory ("every fastball paragraph MUST...").
5. **Writer** (`personas.py` `SHARED_WRITER_BASE`): one bullet telling the single writer voice to keep the insight during synthesis. Then **regenerate** the per-mode `tests/fixtures/writer_prompt_{report,changes,recap}.txt` via `build_writer_system_prompt(mode)` — the byte-identical fixture tests exist to catch *accidental* drift; intentional prompt changes regenerate them.
6. **Guarantee tier** (only when "must mention when notable" is a hard requirement): compute a `notable` flag in the engine; add a `KeySignals` field + `_FIELD_LABELS` entry (`signals.py`); in `pipeline.py`'s run functions, immediately after the Phase 1.75 signal-extraction step, deterministically override the field with the engine's summary when notable (read the run function first — both streaming and non-streaming paths); add it to `ANCHOR_PROMPT`'s mandatory tier so MISSED_SIGNAL triggers the revision loop. This makes mention a guarantee instead of a hope.
7. **Tests**: literal-string assertions on prompt rules (house convention); section-presence tests on `to_prompt()` and the specialist input (including the `pitch_shape=None` omission path via `ctx.model_copy(update=...)`); real-data profile tests against `TEST_PITCHER = 592155`.

## Common mistakes

| Mistake | Consequence |
|---------|-------------|
| Context field without `= None` default | Manually-constructed `PitcherContext` tests break |
| Editing `SHARED_WRITER_BASE` without regenerating fixtures | 4+ byte-identical tests fail |
| Test assertions probed from one parquet | `data.statcast` is multi-year; counts differ |
| Literal `None` reaching `to_prompt()` output | Guard test fails |
| Skipping the specialist prompt rule | Data present but narrative ignores it |

Data conventions (units, signs, coverage): **REQUIRED BACKGROUND:** statcast-data-conventions skill.
