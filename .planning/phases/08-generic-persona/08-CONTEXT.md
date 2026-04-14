# Phase 08: Generic Persona - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

A GENERIC persona exists with a sectioned-with-summary-table format, validated against the shared anchor check and hallucination guard. The only phase that may conditionally touch anchor.py — via a single-sentence tolerance addendum applied test-first.

</domain>

<decisions>
## Implementation Decisions

### Voice & Tone
- Target audience: general fan with moderate baseball literacy — neutral-analytical, accessible but not simplified
- Length target: 300–500 words (fixed sections + summary table carry the structural weight)
- Voice: concise declarative prose, 2–4 sentences per section — no newsletter teaching tone (analyst), no scout-ear conversational style
- Inherits scout's banned-word list and factual-discipline rules via `parent="scout"`

### Summary Table Design
- 3 columns: **Signal | Key Finding | Grade**
- Signal labels sourced from `_FIELD_LABELS` in `signals.py` (e.g. "Top Improvement", "Top Concern", "Development Pitch")
- Skip rows for unpopulated optional KeySignals fields (one row per *populated* entry, per VOICE-03)
- Grade cell = primary Pitching+ metric if available (e.g. "S+ 112"), else `—`

### check_explainer_present Keywords
- Present = ANY of: `S+`, `L+`, `P+`, `Pitching+`, `Stuff+`, `Location+` found in capsule
- Scope: ALL personas (general quality gate in `_run_pipeline`, not generic-only)
- Warning message: `"[{persona_id}] capsule is missing model explanation content"` logged to stderr (non-fatal)
- Location in pipeline: after writer capsule lands, before anchor check runs

### anchor.py Tolerance Addendum
- Test-first: write synthetic-capsule test (headings + summary table), run anchor check against it
- Add one-sentence addendum to `ANCHOR_PROMPT` ONLY if the test fails with false positives
- Addendum text: `"Summary tables in a fixed section format are intentional structure, not narrative violations."`
- If synthetic-capsule test passes clean: do NOT touch anchor.py

### Claude's Discretion
- Per-persona allowlist entries for generic vocabulary (PERSONA-10 generic portion): decide based on what vocabulary appears in the generic overlay that might match `_METRIC_PATTERN` but is safe
- Specific keyword to scan in `check_explainer_present` can be expanded if initial set proves insufficient during testing

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `personas.py` — `Persona` frozen dataclass, `ANALYST` as pattern for child persona with `parent="scout"`, `build_writer_system_prompt()` composer, `PERSONAS` registry
- `signals.py` — `KeySignals` model with primary (`top_improvement`, `top_concern`) and 6 optional fields; `_FIELD_LABELS` dict mapping field names to human-readable labels
- `anchor.py` — `ANCHOR_PROMPT` constant (lines 26–56), `AnchorWarning`, `WarningCategory` Literal
- `pipeline.py:check_hallucinated_metrics()` — `_PERSONA_KNOWN_METRICS` dict pattern from Phase 07 for per-persona allowlist
- `tests/test_personas.py` — `assert_analyst_shape` and smoke test patterns to replicate for generic

### Established Patterns
- Persona overlay = string constant with clear sections, parent="scout" for factual inheritance
- `PERSONAS` dict updated, `__all__` updated
- TestModel-based smoke test via `generate_pipeline_streaming(..., _model_override=TestModel())`
- Shape assertion helper (`assert_generic_shape`) validates structural constraints

### Integration Points
- `personas.py` — add `_GENERIC_OVERLAY` + `GENERIC` constant + update `PERSONAS` + update `__all__`
- `pipeline.py` — add `check_explainer_present()` function, call after writer capsule, update `_PERSONA_KNOWN_METRICS` for generic
- `anchor.py` — conditional one-line addendum (test-first, only if needed)
- `tests/test_personas.py` — add `assert_generic_shape`, `test_generic_pipeline_smoke`, update `test_registry_contains_scout_and_analyst`
- `tests/test_hallucination_guard.py` — add generic persona regression vectors

</code_context>

<specifics>
## Specific Ideas

- Summary table columns: **Signal | Key Finding | Grade** (3 columns, clean and scannable)
- Anchor addendum wording if needed: "Summary tables in a fixed section format are intentional structure, not narrative violations."
- `check_explainer_present` keyword set: `{"S+", "L+", "P+", "Pitching+", "Stuff+", "Location+"}` — any match = present

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
