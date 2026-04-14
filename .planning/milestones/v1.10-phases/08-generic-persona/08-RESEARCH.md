# Phase 08: Generic Persona - Research

**Researched:** 2026-04-14
**Domain:** Persona overlay definition (sectioned + table format), hallucination guard extension, explainer post-processor, conditional anchor prompt addendum, test scaffolding
**Confidence:** HIGH

## Summary

Phase 08 adds the GENERIC persona constant to `personas.py` with a sectioned + summary-table format, extends the per-persona hallucination allowlist for generic vocabulary, introduces a new `check_explainer_present(capsule)` post-processor in `pipeline.py`, and — conditionally — appends a one-sentence tolerance addendum to `ANCHOR_PROMPT` in `anchor.py` only if a synthetic-capsule test surfaces false positives. The phase is mostly additive but carries the single highest-risk artifact in v1.10: the one permitted touch of `anchor.py`.

The implementation pattern is fully established. SCOUT (Phase 05) and ANALYST (Phase 07) define the overlay + registry + per-persona allowlist shape; Phase 08 replicates that shape for a third entry and adds one net-new function (`check_explainer_present`) wired into `_run_pipeline` after the writer capsule lands. The only novel structural concern is that the GENERIC persona's writer output intentionally contains Markdown `##` headings and a pipe-delimited summary table, which is exactly why the anchor prompt might false-positive — hence the test-first protocol for the addendum.

**Primary recommendation:** Define `GENERIC` with `parent="scout"` (inheriting factual-discipline rules only; voice/structure rules in the scout overlay are superseded by the generic overlay's section mandate). Fix the six-section order and the three-column summary table shape in the overlay text. Add the `"generic"` entry to `_PERSONA_KNOWN_METRICS` with Pitching+ framework terms that appear in section subjects. Implement `check_explainer_present()` as a pragmatic keyword scan (not an LLM call) gated on `{"S+", "L+", "P+", "Pitching+", "Stuff+", "Location+"}`. Build the synthetic-capsule test against the current `ANCHOR_PROMPT` FIRST; only touch `anchor.py` if that test fails.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Voice & Tone**
- Target audience: general fan with moderate baseball literacy — neutral-analytical, accessible but not simplified
- Length target: 300–500 words (fixed sections + summary table carry the structural weight)
- Voice: concise declarative prose, 2–4 sentences per section — no newsletter teaching tone (analyst), no scout-ear conversational style
- Inherits scout's banned-word list and factual-discipline rules via `parent="scout"`

**Summary Table Design**
- 3 columns: **Signal | Key Finding | Grade**
- Signal labels sourced from `_FIELD_LABELS` in `signals.py` (e.g. "Top Improvement", "Top Concern", "Development Pitch")
- Skip rows for unpopulated optional KeySignals fields (one row per *populated* entry, per VOICE-03)
- Grade cell = primary Pitching+ metric if available (e.g. "S+ 112"), else `—`

**check_explainer_present Keywords**
- Present = ANY of: `S+`, `L+`, `P+`, `Pitching+`, `Stuff+`, `Location+` found in capsule
- Scope: ALL personas (general quality gate in `_run_pipeline`, not generic-only)
- Warning message: `"[{persona_id}] capsule is missing model explanation content"` logged to stderr (non-fatal)
- Location in pipeline: after writer capsule lands, before anchor check runs

**anchor.py Tolerance Addendum**
- Test-first: write synthetic-capsule test (headings + summary table), run anchor check against it
- Add one-sentence addendum to `ANCHOR_PROMPT` ONLY if the test fails with false positives
- Addendum text: `"Summary tables in a fixed section format are intentional structure, not narrative violations."`
- If synthetic-capsule test passes clean: do NOT touch anchor.py

### Claude's Discretion
- Per-persona allowlist entries for generic vocabulary (PERSONA-10 generic portion): decide based on what vocabulary appears in the generic overlay that might match `_METRIC_PATTERN` but is safe
- Specific keyword to scan in `check_explainer_present` can be expanded if initial set proves insufficient during testing

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VOICE-03 | GENERIC persona constant with sectioned format, six fixed sections in order, summary table with one row per populated KeySignals entry, forbids h1 headings, inherits scout factual-discipline via `parent` | Full pattern established by SCOUT/ANALYST in `personas.py`; `build_writer_system_prompt()` already handles parent inheritance; `_FIELD_LABELS` in `signals.py` provides the row-label source |
| PERSONA-10 (generic portion) | `_PERSONA_KNOWN_METRICS` dict gains a `"generic"` entry with any generic-specific safe vocabulary that might match `_METRIC_PATTERN` | Analyst portion completed in Phase 07; infrastructure exists at `pipeline.py:1466`. Generic table cell tokens like `S+`, `L+`, `P+`, `Pitching+`, `Stuff+`, `Location+` are already in `_KNOWN_METRICS` — additional allowlist is defensive forward-compat |
| PERSONA-11 | `check_explainer_present(capsule: str) -> bool` post-processor runs after writer capsule in `_run_pipeline`; logs warning to stderr (non-fatal) when False | Net-new function; simple keyword scan per CONTEXT.md locked decision; log location per `log = logging.getLogger("pitcher_narratives.pipeline")` at `pipeline.py:97` |
| TEST-05 (generic portion) | TestModel-based generic smoke test runs pipeline end-to-end via `PITCHER_NARRATIVES_TEST_MODEL=1` equivalent (`_model_override=TestModel()`), asserts composed prompt starts with SHARED_WRITER_BASE, narrative non-empty, anchor runs, hallucination guard does not fire | Exact pattern exists: `test_scout_pipeline_smoke` at `test_personas.py:170`, `test_analyst_pipeline_smoke` at `test_personas.py:300` |
| TEST-06 (generic portion) | `assert_generic_shape(text)` validates exactly one markdown table, correct row count tied to populated KeySignals, allowed section set, no h1 headings | `assert_analyst_shape` at `test_personas.py:236` provides template for structural checks; row-count check requires `KeySignals` fixture |
| TEST-07 (generic portion) | Regression vectors in `test_hallucination_guard.py`: synthetic generic capsule passes clean; fabricated section or invented metric in a table row is still flagged | Pattern exists: `test_analyst_vocab_not_flagged_with_persona`, `test_analyst_persona_does_not_suppress_real_unknowns` at `test_hallucination_guard.py:173, 204` |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python 3.14+, polars, pydantic-ai, Claude — already in pyproject.toml
- **Data format:** Static parquet + CSV files, no live API calls
- **Naming:** `snake_case.py` modules, `snake_case` functions/vars, `UPPER_SNAKE_CASE` constants, `PascalCase` classes and Pydantic models, `_` prefix for internals
- **Imports:** Absolute imports grouped with blank line between sections; sorted alphabetically within group
- **Docstrings:** Google-style, type hints on all function signatures
- **Module design:** `__all__` for public APIs
- **Error handling:** Specific exception types; use `pl.exceptions.ComputeError` for polars; use structured logging (not `print`) for errors
- **GSD Workflow:** All edits through GSD workflow — Phase 08 is `/gsd:execute-phase`

## Standard Stack

No new dependencies required. Phase 08 is purely additive Python code using existing project infrastructure.

### Core (already installed)
| Library | Version | Purpose | Role in Phase 08 |
|---------|---------|---------|-------------------|
| pydantic-ai | 1.72.0 | Agent framework | `TestModel` for generic smoke test via `_model_override` |
| pydantic | 2.12.5 | BaseModel | Existing `HallucinationReport`, `AnchorResult`, `KeySignals` |
| pytest | 9.0.2 | Test framework | All test execution |

**Version verification (2026-04-14):**
- `pydantic-ai 1.72.0` — confirmed via `uv run python -c "import pydantic_ai; print(pydantic_ai.__version__)"`
- `pydantic 2.12.5` — confirmed
- `pytest 9.0.2` — confirmed (declared in `pyproject.toml` dev group)

### Supporting (already used in the pipeline)
| Module | Purpose | When to Use |
|--------|---------|-------------|
| `pitcher_narratives.signals._FIELD_LABELS` | Human-readable label per KeySignals field | Summary table Signal column labels |
| `pitcher_narratives.signals.KeySignals` | Pydantic model for cross-specialist signals | Row-count source for `assert_generic_shape` |
| `pitcher_narratives.anchor.ANCHOR_PROMPT` | Anchor check system prompt constant | Conditional addendum target (test-first) |
| `pydantic_ai.models.test.TestModel` | Deterministic test model | Generic smoke test (no LLM call) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Keyword-scan `check_explainer_present` | LLM-based explainer check | CONTEXT.md locks the keyword scan; PERSONA-11 REQUIREMENTS explicitly says "pragmatic keyword scan, not a new LLM call" |
| Fixed six-row table | One-row-per-populated-signal | CONTEXT.md + VOICE-03 both mandate variable rows tied to `KeySignals`. FEATURES.md older text (five-row by specialist) is overridden by VOICE-03 |
| Three columns: `Category \| Grade \| Note` | Three columns: `Signal \| Key Finding \| Grade` | CONTEXT.md locks the Signal/Key Finding/Grade column set. FEATURES.md older text is overridden |
| Persona-aware `build_anchor_message` | Single-sentence `ANCHOR_PROMPT` addendum | REQUIREMENTS "Out of Scope" explicitly rejects persona-aware `build_anchor_message`, `persona_hints` parameter, branching logic, new `WarningCategory` |

## Architecture Patterns

### Files Modified in Phase 08

```
src/pitcher_narratives/
  personas.py          # ADD: _GENERIC_OVERLAY, GENERIC constant, update PERSONAS registry, update __all__
  pipeline.py          # ADD: check_explainer_present() post-processor, call site in _run_pipeline,
                       #      "generic" entry in _PERSONA_KNOWN_METRICS, export in __all__
  anchor.py            # CONDITIONAL: one-sentence addendum to ANCHOR_PROMPT (test-first; skip if synthetic test passes)

tests/
  test_personas.py     # ADD: test_generic_has_expected_fields, test_generic_composed_prompt_*,
                       #      test_generic_overlay_fixes_section_order, test_generic_overlay_forbids_h1,
                       #      assert_generic_shape(), test_assert_generic_shape_*,
                       #      test_generic_pipeline_smoke, update test_registry_contains_scout_and_analyst
                       #      -> test_registry_contains_all_three
  test_hallucination_guard.py  # ADD: test_generic_synthetic_capsule_clean,
                               #      test_generic_table_row_invented_metric_flagged,
                               #      test_generic_fabricated_section_metric_flagged
  test_pipeline.py     # ADD: test_check_explainer_present_detects_plus_family,
                       #      test_check_explainer_present_missing_logs_warning,
                       #      test_explainer_check_runs_before_anchor (smoke-level)
  test_anchor.py       # ADD: test_anchor_tolerates_generic_summary_table (the gate test for the addendum)
```

### Pattern 1: Generic Persona Constant

```python
# In personas.py
_GENERIC_OVERLAY = """\
You are writing a structured breakdown for a general baseball fan with \
moderate literacy. Neutral-analytical tone -- informative, not \
conversational; accessible, not simplified.

TARGET: 300-500 words total across all sections. Each section is \
2-4 sentences of concise declarative prose. The fixed sections and \
the summary table carry the structural weight -- do not pad.

STRUCTURE (fixed; do not reorder, rename, add, or drop):
## Stuff
## Location
## Run Value & Execution
## Trend
## Game Shape
## Summary Table

Each ## section is 2-4 sentences. No bullet lists inside sections. \
No sub-headings inside sections.

FORBIDDEN: Markdown h1 headings (single `#`). The `## Scouting Report` \
header is emitted by the CLI, not by you. Start with `## Stuff`.

SUMMARY TABLE:
- Exactly three columns: `Signal | Key Finding | Grade`.
- One row per populated Key Signal in the synthesis (skip any signal \
the synthesis did not provide; do not invent rows for completeness).
- Signal cell: use the exact label from the Key Signals list \
(e.g. "Top Improvement", "Top Concern", "Development Pitch").
- Key Finding cell: a single short phrase citing the pitch and metric.
- Grade cell: the primary Pitching+ metric if the finding cites one \
(e.g. "S+ 112"), otherwise an em dash `—`.
- Include the header row `| Signal | Key Finding | Grade |` and a \
separator row `|---|---|---|`.

VOCABULARY:
- Keep the scout banned-word list: never use "degradation," "binary," \
"profiles as," "dominant," "elite," "massive spike."
- Plain declarative voice. No newsletter framing ("what we're seeing \
here"), no conversational lead ("here's the thing about the slider").
- Three-metric maximum PER SECTION. The sections share the burden, so \
the total metric footprint across the capsule may exceed three.

For the EXPLAIN THE MODEL section: each ## section's first Pitching+ \
reference gets one sentence of context. "S+ measures physical pitch \
quality -- 112 for the slider means the model credited it 12 percent \
above league average on characteristics alone." Do not re-explain the \
same plus-metric within the same section.

HARD LIMIT: Do not exceed 500 words. Concision is the voice."""


GENERIC = Persona(
    id="generic",
    display_name="Generic",
    description=(
        "Structured breakdown -- six fixed sections plus a summary "
        "table, 300-500 words, neutral-analytical voice for general fans"
    ),
    overlay=_GENERIC_OVERLAY,
    length_target=(300, 500),
    parent="scout",
)
```

### Pattern 2: Registry + `__all__` Update

```python
PERSONAS: dict[str, Persona] = {
    "scout": SCOUT,
    "analyst": ANALYST,
    "generic": GENERIC,   # NEW
}

__all__ = [
    "ANALYST",
    "GENERIC",             # NEW
    "Persona",
    "PERSONAS",
    "SCOUT",
    "DEFAULT_PERSONA",
    "SHARED_WRITER_BASE",
    "build_writer_system_prompt",
    "get_persona",
]
```

Note: `SCOUT` was not in `__all__` originally. Phase 07 imports it in tests via `from pitcher_narratives.personas import SCOUT`, which works because `__all__` only affects `from X import *`, not explicit imports. Still, adding it improves discoverability — confirm with planner whether to include.

### Pattern 3: Per-Persona Hallucination Allowlist Extension

```python
# In pipeline.py near _PERSONA_KNOWN_METRICS (line 1466)
_PERSONA_KNOWN_METRICS: dict[str, frozenset[str]] = {
    "analyst": frozenset({
        "playability",
        "tunneling gap",
        "pitch tree",
        "arsenal depth",
    }),
    "generic": frozenset({
        # Section subjects that are definitional, not invented metrics.
        # Most are already in _KNOWN_METRICS but listed defensively in
        # case the regex evolves. Per-persona allowlist = additive only.
    }),
}
```

**Investigation result:** Running `_METRIC_PATTERN.findall` against the locked overlay text and a realistic synthetic generic capsule produces only tokens already in `_KNOWN_METRICS` (`S+`, `L+`, `P+`, `Pitching+`, `Stuff+`, `Location+`, `xRV100`, etc.). The locked vocabulary design avoids newsletter-style teaching phrases. Recommended value: leave the `"generic"` frozenset empty for now (or include `"Signal"`, `"Key Finding"`, `"Grade"` as column-header tokens if regex evolution ever catches them — though currently it doesn't). **Planner decision point:** empty frozenset vs. a small explicit "future-proof" set. Leaving empty is defensible because PERSONA-10 is satisfied the moment the key exists in the dict.

Safer alternative: `"generic": frozenset({"Signal", "Key Finding", "Grade"})` costs nothing and documents intent.

### Pattern 4: `check_explainer_present` Post-Processor

```python
# In pipeline.py, add near check_hallucinated_metrics (after line 1563)

_EXPLAINER_KEYWORDS: frozenset[str] = frozenset({
    "S+", "L+", "P+", "Pitching+", "Stuff+", "Location+",
})


def check_explainer_present(capsule: str) -> bool:
    """Check whether the capsule contains Pitching+ model explanation content.

    Pragmatic keyword scan (not an LLM call). Returns True when any of
    the Pitching+ family tokens appears in the capsule -- a proxy for
    "the writer referenced the grading framework." False triggers a
    non-fatal stderr warning in the pipeline so operators can see when
    a persona silently dropped the EXPLAIN THE MODEL content.

    Args:
        capsule: The writer agent's narrative output.

    Returns:
        True if any explainer keyword is present, False otherwise.

    Raises:
        TypeError: If capsule is not a str.
        ValueError: If capsule is empty (pipeline failure, not clean).
    """
    if not isinstance(capsule, str):
        raise TypeError(
            f"capsule must be str, got {type(capsule).__name__}"
        )
    if not capsule:
        raise ValueError(
            "capsule is empty -- cannot check for explainer content"
        )

    return any(keyword in capsule for keyword in _EXPLAINER_KEYWORDS)
```

Export in `__all__` at `pipeline.py:88-95`. Add `"check_explainer_present"` to the list.

### Pattern 5: `check_explainer_present` Call Site in `_run_pipeline`

CONTEXT.md locked: "Location in pipeline: after writer capsule lands, before anchor check runs." The capsule lands at `pipeline.py:1286` (`capsule = "".join(chunks)`). The anchor check begins at `pipeline.py:1315` (`_run_anchor_revision_loop`). The insertion point is between them, after the executive summary `await` at line 1299.

```python
# In _run_pipeline, after line 1299 (end of executive summary block),
# before line 1301 (Phase 2.5 anchor check comment).

    # Phase 2.25: Post-writer quality gate (non-fatal)
    # Log a warning when the capsule is missing EXPLAIN THE MODEL content.
    if not check_explainer_present(capsule):
        log.warning(
            "[%s] capsule is missing model explanation content",
            persona,
        )
```

**Rationale for log over print/stderr:** `pipeline.py:97` already has `log = logging.getLogger("pitcher_narratives.pipeline")`. Calling `log.warning` routes to stderr via the stdlib `logging` default handler when no other handler is configured (the CLI bootstraps logging in `cli.py`). This matches the existing `log.warning(...)` patterns at `pipeline.py:1262, 1298`. The CONTEXT.md message format `"[{persona_id}] capsule is missing model explanation content"` is satisfied by `log.warning("[%s] capsule is missing model explanation content", persona)`.

**Caveat:** The CLI must not suppress `WARNING` level. Verify `cli.py` logging config does not filter below WARNING.

### Pattern 6: Anchor Prompt Tolerance Addendum (CONDITIONAL)

The gate test comes first. File `tests/test_anchor.py` already exists (5.8K).

```python
# In tests/test_anchor.py (new test)
from pydantic_ai.models.test import TestModel
from pydantic_ai import Agent
from pitcher_narratives.anchor import (
    ANCHOR_PROMPT, AnchorResult, build_anchor_message
)


def test_anchor_tolerates_generic_summary_table():
    """TEST-06 gate: anchor accepts a synthetic generic capsule (headings + table).

    If this test fails with UNSUPPORTED/OVERSTATED warnings on table
    cells, the _GENERIC_OVERLAY-compatible addendum must be applied
    to ANCHOR_PROMPT. If it passes clean, anchor.py is untouched.
    """
    synthesis = (
        "## Key Signals\n"
        "- Top Improvement: Slider S+ jumped to 112 from season 98\n"
        "- Top Concern: Fastball L+ dropped to 94 from 102\n\n"
        "STUFF: Slider S+ 112 ...\n"
        "LOCATION: Fastball L+ 94 ...\n"
        # ... full synthesis ...
    )
    synthetic_capsule = (
        "## Stuff\nThe slider graded S+ 112 ...\n\n"
        "## Location\nFastball L+ 94 ...\n\n"
        "## Run Value & Execution\n...\n\n"
        "## Trend\n...\n\n"
        "## Game Shape\n...\n\n"
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        "| Top Improvement | Slider vertical break gain | S+ 112 |\n"
        "| Top Concern | Fastball command slipped | L+ 94 |\n"
    )

    agent = Agent(
        model=TestModel(custom_output_args={"warnings": []}),
        system_prompt=ANCHOR_PROMPT,
        output_type=AnchorResult,
    )
    result = agent.run_sync(build_anchor_message(synthesis, synthetic_capsule))
    assert result.output.is_clean, (
        f"Anchor flagged false positives on generic capsule: "
        f"{result.output.warnings}. "
        f"Apply the summary-table addendum to ANCHOR_PROMPT."
    )
```

**Caveat on this test:** `TestModel` returns a canned `AnchorResult(warnings=[])` by default for structured outputs — so this test may pass trivially without exercising the prompt. That makes the test a TYPE-LEVEL sanity check rather than a behavioral one. The honest forcing function is a **real-LLM smoke run** (manual; not in CI): `uv run pitcher-narratives --persona generic -p <pitcher_id> -v` and inspect stderr for anchor warnings. The research position is: write the TestModel-based test for CI (it documents the invariant), AND run a manual smoke with a real model to decide the addendum.

**Conditional addendum (only if manual smoke shows false positives):**

```python
# In anchor.py, append to ANCHOR_PROMPT immediately before the closing """
ANCHOR_PROMPT = """\
You are a fact-checker ...

... [existing text] ...

If everything checks out, return an empty list of warnings.

Summary tables in a fixed section format are intentional structure, \
not narrative violations."""
```

Adding one sentence costs < 20 tokens and does not change the warning-category schema. The `WarningCategory` Literal remains unchanged.

### Pattern 7: Generic Smoke Test

```python
# In tests/test_personas.py
def test_generic_pipeline_smoke(ctx):
    """TEST-05 (generic): Full pipeline with TestModel produces non-empty narrative."""
    test_model = TestModel()
    result = generate_pipeline_streaming(
        ctx,
        provider="gemini",
        thinking="high",
        persona="generic",
        _model_override=test_model,
    )
    assert isinstance(result, PipelineResult)
    assert len(result.narrative) > 0

    expected = build_writer_system_prompt(GENERIC)
    assert expected.startswith(SHARED_WRITER_BASE)
    assert "## Stuff" in expected
    assert "## Summary Table" in expected
```

### Pattern 8: `assert_generic_shape` Helper

```python
# In tests/test_personas.py
import re

_GENERIC_SECTIONS = (
    "## Stuff",
    "## Location",
    "## Run Value & Execution",
    "## Trend",
    "## Game Shape",
    "## Summary Table",
)


def assert_generic_shape(text: str, *, populated_signal_count: int | None = None) -> None:
    """TEST-06: Validate generic persona output shape.

    Checks structural constraints:
    - No h1 headings (single `#` lines).
    - All six allowed sections present in the overlay-fixed order.
    - Exactly one markdown table.
    - Table row count (data rows, excluding header + separator) equals
      populated_signal_count when provided.

    Args:
        text: Narrative text to validate.
        populated_signal_count: If given, asserts the table's data-row
            count equals this number. Omit on TestModel output (where
            the writer is a canned stub and row count is not meaningful).

    Raises:
        AssertionError: If structural constraints are violated.
    """
    lines = text.strip().splitlines()

    # No h1 headings (line starting with "# " but not "## ")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("##"):
            raise AssertionError(
                f"Generic output must not contain h1 headings: {stripped[:60]!r}"
            )

    # Allowed section set present, in order
    section_positions = [
        (s, text.find(s)) for s in _GENERIC_SECTIONS
    ]
    missing = [s for s, pos in section_positions if pos == -1]
    if missing:
        raise AssertionError(f"Generic output missing sections: {missing}")
    positions = [pos for _, pos in section_positions]
    if positions != sorted(positions):
        raise AssertionError(
            "Generic output sections are out of order. "
            f"Expected order: {list(_GENERIC_SECTIONS)}"
        )

    # Exactly one markdown table (pipe-delimited, with header separator)
    # A table is detected by a separator line matching /^\|[\s\-|:]+\|$/
    separator_re = re.compile(r"^\s*\|[\s\-|:]+\|\s*$")
    separator_lines = [l for l in lines if separator_re.match(l)]
    if len(separator_lines) != 1:
        raise AssertionError(
            f"Generic output must contain exactly one summary table, "
            f"found {len(separator_lines)} table separator lines"
        )

    # Row count check (only when caller provides the expected count)
    if populated_signal_count is not None:
        # Data rows = pipe-starting lines AFTER the separator, until
        # the first blank or non-pipe line.
        try:
            sep_idx = lines.index(separator_lines[0])
        except ValueError:
            sep_idx = next(
                i for i, l in enumerate(lines) if separator_re.match(l)
            )
        data_rows = 0
        for line in lines[sep_idx + 1:]:
            stripped = line.strip()
            if not stripped:
                break
            if not stripped.startswith("|"):
                break
            data_rows += 1
        if data_rows != populated_signal_count:
            raise AssertionError(
                f"Generic summary table has {data_rows} data rows, "
                f"expected {populated_signal_count} (one per populated KeySignals entry)"
            )
```

### Pattern 9: Hallucination Guard Regression Vectors

```python
# In tests/test_hallucination_guard.py
def test_generic_synthetic_capsule_clean():
    """TEST-07 (generic): synthetic generic capsule passes clean with persona='generic'."""
    text = (
        "## Stuff\nThe slider graded S+ 112 ...\n\n"
        "## Location\nFastball L+ 94 ...\n\n"
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        "| Top Improvement | Slider break | S+ 112 |\n"
        "| Top Concern | Fastball command | L+ 94 |\n"
    )
    result = check_hallucinated_metrics(text, persona="generic")
    assert result.is_clean, (
        f"Generic synthetic capsule flagged: "
        f"unknown={result.unknown_metrics}, warnings={result.outcome_stat_warnings}"
    )


def test_generic_table_row_invented_metric_flagged():
    """TEST-07 (generic): invented metric inside a table row is caught."""
    text = (
        "## Summary Table\n"
        "| Signal | Key Finding | Grade |\n"
        "|---|---|---|\n"
        "| Top Improvement | xDominance score up | xDominance 128 |\n"
    )
    result = check_hallucinated_metrics(text, persona="generic")
    assert "xDominance" in result.unknown_metrics
    assert not result.is_clean


def test_generic_persona_does_not_suppress_real_unknowns():
    """TEST-07 (generic): allowlist only covers generic vocab, not fabricated metrics."""
    text = "## Stuff\nHis xMadeUpMetric score is 95."
    result = check_hallucinated_metrics(text, persona="generic")
    assert "xMadeUpMetric" in result.unknown_metrics
```

### Anti-Patterns to Avoid

- **Do NOT touch `anchor.py` unconditionally.** Test first. Only apply the addendum if the synthetic-capsule test (or real-LLM smoke) demonstrates false positives. CONTEXT.md is explicit: "If synthetic-capsule test passes clean: do NOT touch anchor.py."
- **Do NOT add new `WarningCategory` values.** REQUIREMENTS explicitly rejects `EXPLAINER_MISSING` as an anchor category. The explainer check lives in `pipeline.py`, not `anchor.py`.
- **Do NOT make `check_explainer_present` generic-only.** CONTEXT.md: "Scope: ALL personas (general quality gate in `_run_pipeline`, not generic-only)." The check runs for scout + analyst + generic every run.
- **Do NOT make explainer absence fatal.** CONTEXT.md: "logged to stderr (non-fatal)." Use `log.warning`, do not raise.
- **Do NOT hardcode row count = 5 in `assert_generic_shape`.** VOICE-03 + CONTEXT.md: "one row per *populated* entry," which can be 2 (minimum: top_improvement + top_concern) up to 8 (all fields populated).
- **Do NOT change the summary table column set.** CONTEXT.md locks `Signal | Key Finding | Grade`. Ignore the older FEATURES.md `Category | Grade | Note` proposal.
- **Do NOT modify `build_anchor_message` to branch on persona.** REQUIREMENTS Out of Scope: "not a `persona_hints` parameter, not a branching `build_anchor_message`."
- **Do NOT pre-strip table cells in the hallucination guard.** The pre-strip design was deferred in REQUIREMENTS; per-persona allowlist is the mechanism.
- **Do NOT update `DEFAULT_PERSONA`.** It must remain `PERSONAS["scout"]`.
- **Do NOT add `--persona generic` wiring to `cli.py`.** That is Phase 09's job (CLI-01).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Overlay composition | Custom string concat | `build_writer_system_prompt(GENERIC)` | Already handles `parent="scout"` chain via the base + scout overlay + generic overlay order |
| Persona lookup | Manual dict access | `get_persona("generic")` | Raises ValueError with helpful message on unknown ids |
| Markdown table detection | Custom pipe-counting | `re.compile(r"^\s*\|[\s\-|:]+\|\s*$")` on separator line | Separator is the structural fingerprint of a markdown table; counting pipes alone false-positives on natural prose with `|` |
| Stderr logging | `print(..., file=sys.stderr)` | `log.warning(...)` via existing `log = logging.getLogger("pitcher_narratives.pipeline")` | Matches existing `log.warning` call sites at `pipeline.py:1262, 1298`; respects CLI logging config |
| Hallucination guard extension | New regex pass | `_PERSONA_KNOWN_METRICS["generic"] = frozenset({...})` | Mechanism already shipped in Phase 07 |
| Generic signal row source | New field enumeration | `from pitcher_narratives.signals import _FIELD_LABELS, KeySignals` | Single source of truth for signal labels and field set |
| Anchor structural tolerance | Persona-aware `build_anchor_message` | One-sentence addendum to `ANCHOR_PROMPT` constant | Rejected in REQUIREMENTS Out of Scope; simplest mitigation |
| Test pipeline without LLM | Mock HTTP, fake providers | `pydantic_ai.models.test.TestModel` passed via `_model_override` | Deterministic, free, already the established pattern in Phase 06 + 07 smoke tests |

**Key insight:** Phase 08 invents one new function (`check_explainer_present`) and one new Persona constant. Everything else is reuse. Over-engineering risk is highest on (a) the anchor addendum decision — resist adding before the test demands it, and (b) the `_PERSONA_KNOWN_METRICS["generic"]` entry — an empty frozenset is correct if the locked overlay vocabulary uses tokens already in `_KNOWN_METRICS`.

## Common Pitfalls

### Pitfall 1: TestModel Does Not Produce Sectioned Output
**What goes wrong:** `assert_generic_shape` fails on TestModel output because TestModel returns a canned placeholder string, not six sections with a table.
**Why it happens:** `TestModel` is provider-agnostic and outputs a generic stub — it is a deterministic fake, not a simulator of the prompt's intended behavior.
**How to avoid:** The generic smoke test (TEST-05 style) asserts pipeline runs + prompt composition + non-empty narrative. It does NOT call `assert_generic_shape` on TestModel output. The shape helper is used against **real-LLM goldens** (manual, not CI) or against handcrafted synthetic text. Pattern established in Phase 07: `test_analyst_pipeline_smoke` does not invoke `assert_analyst_shape` on TestModel output.
**Warning signs:** Smoke test passes then shape helper fails mysteriously because it ran on TestModel output.

### Pitfall 2: KeySignals Row Count Drift Between Extractor and Overlay
**What goes wrong:** The signal extractor populates 4 secondary signals; the writer invents 6 table rows or emits only 3. The table row count does not match the `KeySignals` object the writer received.
**Why it happens:** The overlay says "one row per populated Key Signal" but the writer infers what is "populated" from the rendered key-signals block in the synthesis, which already omits nulls via `render_key_signals`. If the writer counts commas or infers a default five rows, drift appears.
**How to avoid:** (a) Overlay wording — "Exactly one row per signal listed in the Key Signals section of the synthesis; do not add rows for completeness and do not drop rows if all signals are listed." (b) Test — `test_generic_table_row_count_matches_key_signals` using a `KeySignals` fixture with known populated-field count, asserted against `data_rows` parsed from the output. For TestModel, this test cannot be run behaviorally — it requires a handcrafted synthetic capsule from the fixture. Phase 08 should include the handcrafted-capsule version of this test.
**Warning signs:** Real-LLM runs produce tables with 5 rows every time regardless of how many signals are populated.

### Pitfall 3: `check_explainer_present` False Positive on Synthesis Leakage
**What goes wrong:** The writer echoes the synthesis section labels but never actually references `S+`/`L+`/`P+`. The keyword scan matches `Stuff+` embedded in a `## Stuff+` heading variant or in prose like "the Pitching+ framework" without the model actually explaining what the grade measures. Warning does not fire — but explainer content is missing.
**Why it happens:** A keyword scan cannot distinguish definition from mention.
**How to avoid:** Accept the false-negative rate as a known tradeoff. CONTEXT.md locked the scan design; PERSONA-11 REQUIREMENTS explicitly accepts "a pragmatic keyword scan, not a new LLM call." If false-negative rate is unacceptable later, escalate to v1.11 as a discretion item.
**Warning signs:** Manual review of shipped capsules shows missing explainer content but the warning never fires.

### Pitfall 4: Conditional Anchor Addendum Decision Made Too Early
**What goes wrong:** Developer assumes the addendum is needed (it is "scoped in"), applies it preemptively, then the test never exercises the unmodified prompt. The addendum ships untested.
**Why it happens:** It is easier to write the addendum once than to run the test first.
**How to avoid:** Test-first protocol: (1) write the test against unmodified `ANCHOR_PROMPT`, (2) run `uv run python -m pytest tests/test_anchor.py::test_anchor_tolerates_generic_summary_table -x -v`, (3) inspect output, (4) only if real-LLM smoke confirms false positives, apply the one-line addendum and re-run the test. CONTEXT.md is explicit: "Add one-sentence addendum to `ANCHOR_PROMPT` ONLY if the test fails with false positives."
**Warning signs:** `anchor.py` diff in the plan before the test has been written.

### Pitfall 5: Forgetting to Update Registry Test
**What goes wrong:** `tests/test_personas.py::test_registry_contains_scout_and_analyst` at line 120 asserts `len(PERSONAS) == 2`. After adding GENERIC, `len(PERSONAS) == 3` and the test fails.
**Why it happens:** Phase 07 wrote the test assuming only scout + analyst. Phase 08 must update it (or add a new test superseding it).
**How to avoid:** Rename to `test_registry_contains_all_three` and assert `len(PERSONAS) == 3` with keys `{"scout", "analyst", "generic"}`. Remove the line-120 test or update it in place.
**Warning signs:** Test failure immediately after adding `"generic"` to `PERSONAS`.

### Pitfall 6: Forgetting to Export GENERIC from `__all__`
**What goes wrong:** `from pitcher_narratives.personas import GENERIC` works in tests (explicit import bypasses `__all__`) but star-import or `--print-prompts` output may miss the constant.
**Why it happens:** `__all__` was extended in Phase 07 for ANALYST but not GENERIC.
**How to avoid:** Add `"GENERIC"` to `__all__` in `personas.py:7-15`.
**Warning signs:** `--list-personas` output (Phase 09) missing the generic persona.

### Pitfall 7: `check_explainer_present` Runs Before Anchor Revision Loop Has Produced the Final Capsule
**What goes wrong:** The CONTEXT.md-locked location says "after writer capsule lands, before anchor check runs" — which is the INITIAL writer output, not the post-anchor-revision capsule. If the anchor revision loop rewrites the capsule and drops the explainer content, the check has already passed on the original.
**Why it happens:** The revision loop at `pipeline.py:1315` can run up to `MAX_REVISIONS = 3` passes. Each pass replaces the capsule. The explainer check sees only the first version.
**How to avoid:** Phase 08 option — run the explainer check ONCE before the anchor loop (per CONTEXT.md) AND again on the final returned capsule, OR accept the risk and only run it pre-loop. CONTEXT.md locked pre-loop; the planner should not deviate. Document the limitation in the function docstring and move the second check to a deferred improvement.
**Warning signs:** Manual review shows post-revision capsules with missing explainer content but no warning was logged.

### Pitfall 8: Generic Overlay Conflicts with Scout Overlay Inherited Via `parent="scout"`
**What goes wrong:** SCOUT overlay says "No bullet points, no headers, no tables. Prose only." GENERIC overlay says "Use six `##` section headers and a summary table." The composed prompt contains both, contradicting itself.
**Why it happens:** Overlay ordering is base + scout + generic. LLMs weight last-mentioned rules higher, so the generic overlay's sectioned format should win — but the scout overlay's "No bullet points, no headers, no tables" rule is still in the prompt and may cause the writer to hedge.
**How to avoid:** (a) Accept that "last wins" is the established mechanism — Phase 07 did this for analyst (which also says "no tables, no bullets" but inherits scout). (b) Generic overlay must explicitly override: "This persona permits `##` headings and exactly one Markdown table — these override any prior prose-only constraint." (c) Include a test that asserts `"## Stuff" in build_writer_system_prompt(GENERIC)` and "permits" language is present.
**Warning signs:** Real-LLM generic output emits prose-only without sections because the scout overlay dominated.

### Pitfall 9: Streaming Artifacts Breaking the Table
**What goes wrong:** The writer streams output delta-by-delta via `print(delta, end="", flush=True)` at `pipeline.py:1282`. For a markdown table the user sees `|` characters appear mid-cell, which looks broken on narrow terminals but is cosmetic.
**Why it happens:** `run_stream` delivers tokens as they arrive; the pipe-char stream makes the table render progressively.
**How to avoid:** PITFALLS.md pitfall 6 acknowledges this and defers buffering. Phase 08 should NOT fix the streaming behavior; accept the cosmetic issue. The final `capsule = "".join(chunks)` is correct and well-formed.
**Warning signs:** User screenshot showing broken-looking table mid-stream; assertion that Phase 08 should fix streaming.

### Pitfall 10: Manual Real-LLM Smoke Requires API Key at Test Time
**What goes wrong:** Developer runs `uv run pitcher-narratives --persona generic ...` to force the anchor-addendum decision, but no `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` is configured, and the test cannot complete.
**Why it happens:** Generic is added to the registry but the CLI wiring (`--persona` flag) does not land until Phase 09 (CLI-01). Phase 08 developer has no clean entry point for a real-LLM run.
**How to avoid:** Two options — (a) manually patch `cli.py` locally to accept `persona="generic"` for the smoke run, then revert; (b) write a one-off script in `tests/` or a sandbox that calls `generate_pipeline_streaming(ctx, persona="generic")` directly without going through `cli.py`. Option (b) is cleaner and the research recommends it. The script is ephemeral and not committed.
**Warning signs:** Phase 08 slides into Phase 09 to get the smoke-test entry point.

## Runtime State Inventory

> Phase 08 is additive code/config changes. No external runtime state is stored, registered, or cached. Confirming each category:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the project uses only local parquet/CSV files; no database reads persona IDs | None — verified by grepping the codebase for persona-id persistence (none found) |
| Live service config | None — no deployed services store the persona id; logfire traces (if enabled) will just show a new value for `persona` but no config change needed | None |
| OS-registered state | None — no Task Scheduler / launchd / systemd unit references persona ids | None |
| Secrets/env vars | None — there is no `GENERIC_PERSONA_API_KEY`; all LLM API keys are shared | None |
| Build artifacts | None — Phase 08 adds one frozenset + one Persona constant + one function; no packaging changes. `pyproject.toml` is untouched | None |

The only "stale artifact" risk is if the user has already generated report files in the working directory with `report-*.md` naming (git status shows several). Those are historical outputs, not state Phase 08 must migrate.

## Environment Availability

> Phase 08 modifies Python source and tests only. No external tools or services are added.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All code | ✓ | 3.14 (via `.python-version`) | — |
| uv | Package manager | ✓ | (lockfile present) | — |
| pydantic-ai | TestModel, Agent | ✓ | 1.72.0 | — |
| pydantic | Models | ✓ | 2.12.5 | — |
| pytest | Test runner | ✓ | 9.0.2 | — |
| Real LLM API key | Manual anchor-addendum smoke (optional) | Unverified | — | Skip smoke and ship TestModel-only test; revisit if user reports false positives |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** Real-LLM API access for the anchor-addendum decision is optional. The TestModel-based test documents the invariant; the decision to apply the addendum can be made conservatively (apply it) OR deferred until a user reports a false positive in production. Recommended: **do not apply the addendum** until observed evidence exists, per CONTEXT.md.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` section (line 48-49) — `testpaths = ["tests"]` |
| Quick run command | `uv run python -m pytest tests/test_personas.py tests/test_hallucination_guard.py tests/test_anchor.py -x -q` |
| Full suite command | `uv run python -m pytest tests/ --ignore=tests/test_analyst.py -q` (excludes pre-existing broken `test_analyst.py` per STATE.md blockers) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VOICE-03 | GENERIC persona has id, display_name, parent="scout", length_target=(300, 500) | unit | `uv run python -m pytest tests/test_personas.py::test_generic_has_expected_fields -x` | Wave 0 |
| VOICE-03 | Composed GENERIC prompt starts with SHARED_WRITER_BASE and includes scout overlay | unit | `uv run python -m pytest tests/test_personas.py::test_generic_composed_prompt_includes_base_and_scout -x` | Wave 0 |
| VOICE-03 | GENERIC overlay fixes the six-section order | unit | `uv run python -m pytest tests/test_personas.py::test_generic_overlay_fixes_section_order -x` | Wave 0 |
| VOICE-03 | GENERIC overlay forbids h1 headings | unit | `uv run python -m pytest tests/test_personas.py::test_generic_overlay_forbids_h1 -x` | Wave 0 |
| PERSONA-10 (generic) | `_PERSONA_KNOWN_METRICS["generic"]` exists | unit | `uv run python -m pytest tests/test_hallucination_guard.py::test_generic_persona_key_in_allowlist -x` | Wave 0 |
| PERSONA-11 | `check_explainer_present` detects plus-family keywords | unit | `uv run python -m pytest tests/test_pipeline.py::test_check_explainer_present_detects_plus_family -x` | Wave 0 |
| PERSONA-11 | Missing explainer content logs a warning | unit | `uv run python -m pytest tests/test_pipeline.py::test_check_explainer_present_missing_logs_warning -x` | Wave 0 |
| PERSONA-11 | Explainer check runs inside `_run_pipeline` after capsule, before anchor | integration | `uv run python -m pytest tests/test_personas.py::test_generic_pipeline_smoke -x` (covered indirectly via smoke) | Wave 0 |
| TEST-05 (generic) | TestModel-based generic pipeline smoke | integration | `uv run python -m pytest tests/test_personas.py::test_generic_pipeline_smoke -x` | Wave 0 |
| TEST-06 (generic) | `assert_generic_shape` rejects h1, missing sections, multiple tables, wrong row count | unit | `uv run python -m pytest tests/test_personas.py::test_assert_generic_shape_* -x` | Wave 0 |
| TEST-07 (generic) | Synthetic generic capsule clean; invented metric in table row flagged | unit | `uv run python -m pytest tests/test_hallucination_guard.py::test_generic_synthetic_capsule_clean tests/test_hallucination_guard.py::test_generic_table_row_invented_metric_flagged -x` | Wave 0 |
| TEST-06 (anchor tolerance) | Anchor accepts synthetic generic capsule (gate for addendum decision) | integration | `uv run python -m pytest tests/test_anchor.py::test_anchor_tolerates_generic_summary_table -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/test_personas.py tests/test_hallucination_guard.py tests/test_anchor.py tests/test_pipeline_persona_wiring.py -x -q`
- **Per wave merge:** `uv run python -m pytest tests/ --ignore=tests/test_analyst.py -q`
- **Phase gate:** Full suite (minus pre-existing broken tests) green before `/gsd:verify-work`. Specifically verify: (a) `test_registry_contains_*` updated for three personas; (b) all three smoke tests pass; (c) the anchor-tolerance test passes with whichever ANCHOR_PROMPT is shipped (original or with addendum).

### Wave 0 Gaps

- [ ] `tests/test_personas.py::test_generic_has_expected_fields` — covers VOICE-03 field validation
- [ ] `tests/test_personas.py::test_generic_composed_prompt_includes_base_and_scout` — covers VOICE-03 composition
- [ ] `tests/test_personas.py::test_generic_overlay_fixes_section_order` — covers VOICE-03 section-order mandate
- [ ] `tests/test_personas.py::test_generic_overlay_forbids_h1` — covers VOICE-03 no-h1 rule
- [ ] `tests/test_personas.py::assert_generic_shape` — covers TEST-06 (helper function)
- [ ] `tests/test_personas.py::test_assert_generic_shape_rejects_h1` — exercises helper
- [ ] `tests/test_personas.py::test_assert_generic_shape_rejects_missing_section` — exercises helper
- [ ] `tests/test_personas.py::test_assert_generic_shape_rejects_wrong_row_count` — exercises helper (optional-arg path)
- [ ] `tests/test_personas.py::test_assert_generic_shape_accepts_valid_capsule` — exercises helper happy path
- [ ] `tests/test_personas.py::test_generic_pipeline_smoke` — covers TEST-05
- [ ] `tests/test_personas.py::test_registry_contains_all_three` — updates the phase-07 registry test
- [ ] `tests/test_hallucination_guard.py::test_generic_persona_key_in_allowlist` — covers PERSONA-10 generic portion
- [ ] `tests/test_hallucination_guard.py::test_generic_synthetic_capsule_clean` — covers TEST-07 (clean case)
- [ ] `tests/test_hallucination_guard.py::test_generic_table_row_invented_metric_flagged` — covers TEST-07 (dirty case)
- [ ] `tests/test_hallucination_guard.py::test_generic_persona_does_not_suppress_real_unknowns` — parity with analyst test
- [ ] `tests/test_pipeline.py::test_check_explainer_present_detects_plus_family` — covers PERSONA-11 (happy path)
- [ ] `tests/test_pipeline.py::test_check_explainer_present_rejects_empty` — covers PERSONA-11 (error path)
- [ ] `tests/test_pipeline.py::test_check_explainer_present_rejects_non_string` — covers PERSONA-11 (type path)
- [ ] `tests/test_pipeline.py::test_check_explainer_present_missing_logs_warning` — covers PERSONA-11 (log side-effect using caplog)
- [ ] `tests/test_anchor.py::test_anchor_tolerates_generic_summary_table` — gates the anchor-addendum decision

No new framework install needed — pytest 9.0.2 is already available.

## Key Implementation Details

### Overlay Composition Chain for GENERIC

When `build_writer_system_prompt(GENERIC)` is called, the result is:

```
SHARED_WRITER_BASE          (analytical contract, EXPLAIN THE MODEL, KeySignals obligation)
\n\n
_SCOUT_OVERLAY              (banned words, three-metric cap, plausibility, "no bullets, no headers, no tables" -- SUPERSEDED)
\n\n
_GENERIC_OVERLAY            (six-section mandate, summary-table shape, 300-500 words, no-h1 rule, "permits ## and one table" override)
```

The generic overlay must include an explicit override clause to counteract the scout overlay's "No bullet points, no headers, no tables" line. LLMs weight later rules higher, but explicit override language is still the safer pattern (established in analyst: "Bolded leading phrases at the start of paragraphs are allowed" overrides the scout no-bullets reading).

### Existing Test That Must Be Updated

`tests/test_personas.py::test_registry_contains_scout_and_analyst` (line 120-124) asserts `len(PERSONAS) == 2` and `"scout" in PERSONAS`, `"analyst" in PERSONAS`. Update to:

```python
def test_registry_contains_all_three():
    """After Phase 08 the registry contains scout, analyst, and generic personas."""
    assert len(PERSONAS) == 3
    assert "scout" in PERSONAS
    assert "analyst" in PERSONAS
    assert "generic" in PERSONAS
```

### `_FIELD_LABELS` as Summary-Table Row Source

The summary table's `Signal` column uses labels from `signals.py:41-50`. When the synthesis is rendered via `render_key_signals(signals)` (at `signals.py:53`), the output looks like:

```
## Key Signals
- Top Improvement: Slider S+ climbed 14 points ...
- Top Concern: Fastball L+ dropped to 94 ...
- Development Pitch: Curve shows P+ 108 ...
```

The writer reads these labels from the synthesis and uses them verbatim as the Signal cell. This is implicit in the overlay wording: "Signal cell: use the exact label from the Key Signals list." No code change in `signals.py` is needed.

### CLI Wiring is NOT Phase 08

`cli.py:205` currently calls `check_hallucinated_metrics(pipe_result.narrative)` without a persona argument. Phase 09 (CLI-01) will update this. Phase 08 does not modify `cli.py`.

Similarly, `--persona generic` as an argparse choice lands in Phase 09. The GENERIC persona exists in the registry starting Phase 08, but is only reachable programmatically via `generate_pipeline_streaming(ctx, persona="generic")` or via tests.

### check_explainer_present Call Site Detail

```python
# pipeline.py _run_pipeline, between lines 1299 and 1301:

    except Exception:
        log.warning("Executive summary agent failed, skipping.", exc_info=True)
        summary_bullets = []

    # Phase 2.25: EXPLAIN THE MODEL post-processor (non-fatal quality gate)
    if not check_explainer_present(capsule):
        log.warning(
            "[%s] capsule is missing model explanation content",
            persona,
        )

    # Phase 2.5: Anchor check + revision loop
    specialist_synthesis = (
```

The function is called on the INITIAL capsule (pre-revision). CONTEXT.md is explicit about timing.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single scout voice hardcoded in `_WRITER_PROMPT` | Composed overlay system with `Persona` dataclass | v1.10 Phase 05-06 | Generic is the third voice enabled by the new system |
| `check_hallucinated_metrics(text)` — single signature | `check_hallucinated_metrics(text, persona=None)` with `_PERSONA_KNOWN_METRICS` | v1.10 Phase 07 | Generic adds a third entry (likely empty set, mechanism-only) |
| Anchor prompt is prose-only | Anchor prompt will (conditionally) acknowledge tables as intentional structure | v1.10 Phase 08 if tests require | Generic is the first table-emitting persona |
| Explainer enforcement only via prompt instruction | Pragmatic keyword scan in `_run_pipeline` | v1.10 Phase 08 | Cross-persona quality gate |

**Deprecated / superseded:**
- FEATURES.md §3c column spec `Category | Grade | Note` → superseded by CONTEXT.md `Signal | Key Finding | Grade`
- FEATURES.md §3c fixed five-row table (one per specialist) → superseded by VOICE-03 + CONTEXT.md (one row per populated signal)
- PITFALLS.md §2 `DISCLAIMER_BEGIN/END` sentinel block → deferred; not in v1.10 scope
- PITFALLS.md §2 `strip_disclaimers=True` flag on hallucination guard → deferred; per-persona allowlist is the v1.10 mechanism

## Code Examples

### Running the Anchor Tolerance Gate Test

```bash
# After writing the synthetic-capsule test but BEFORE modifying anchor.py:
uv run python -m pytest tests/test_anchor.py::test_anchor_tolerates_generic_summary_table -x -v

# If it passes: skip the addendum. Commit only the test.
# If it fails with UNSUPPORTED/OVERSTATED on table cells: apply the addendum
#   to ANCHOR_PROMPT, re-run:
uv run python -m pytest tests/test_anchor.py::test_anchor_tolerates_generic_summary_table -x -v
# Now it should pass clean. Commit both anchor.py and the test together.
```

### Direct `generate_pipeline_streaming` Call for Real-LLM Smoke

```python
# tests/_smoke_generic.py (ephemeral, not committed)
from pitcher_narratives.data import load_pitcher_data
from pitcher_narratives.context import assemble_pitcher_context
from pitcher_narratives.pipeline import generate_pipeline_streaming

data = load_pitcher_data(592155, window_days=30)
ctx = assemble_pitcher_context(data)
result = generate_pipeline_streaming(
    ctx, provider="gemini", thinking="high", persona="generic"
)
print("---CAPSULE---")
print(result.narrative)
print("---WARNINGS---")
print(result.anchor_warnings)
```

Run with API key configured: `uv run python tests/_smoke_generic.py`. Inspect the output and the anchor warnings. If any `UNSUPPORTED` warning targets a table cell, apply the addendum.

## Open Questions

1. **Should `_PERSONA_KNOWN_METRICS["generic"]` be empty or prepopulated?**
   - What we know: Regex probe of the locked overlay + a realistic synthetic capsule returns only tokens already in `_KNOWN_METRICS`. An empty frozenset satisfies PERSONA-10 (the key exists).
   - What's unclear: Whether future vocabulary expansion (e.g., adding new pitch-family terms) will match the regex.
   - Recommendation: Start with empty frozenset. Document in the comment: "Currently empty — all generic overlay vocabulary is already in _KNOWN_METRICS. Populate if future regex changes catch generic-specific tokens."

2. **Should `check_explainer_present` also run on the FINAL (post-revision) capsule?**
   - What we know: CONTEXT.md locks the pre-revision timing. Revision loop can drop explainer content.
   - What's unclear: Whether the risk is meaningful in practice.
   - Recommendation: Honor CONTEXT.md. Document the limitation in the function docstring: "Runs on the pre-revision capsule only. Post-revision explainer drift is a deferred concern (v1.11+)." Raise the question to the user if observed in production.

3. **Should the summary-table gate test use a handcrafted KeySignals fixture?**
   - What we know: TestModel cannot emit sectioned output. Real-LLM runs are unstable/expensive for CI. Handcrafted synthetic text is the only tractable path.
   - What's unclear: Whether the handcrafted text should live in a fixture file (like `tests/fixtures/writer_prompt_scout.txt`) or inline in the test.
   - Recommendation: Inline for Phase 08 (smaller blast radius, easier to iterate). Extract to a fixture file if a second test consumes the same synthetic capsule.

4. **If the anchor addendum test trivially passes (TestModel returns canned empty), how do we actually validate the decision?**
   - What we know: `TestModel(custom_output_args={"warnings": []})` forces the output, making the test tautological.
   - What's unclear: The most honest mechanism for the decision.
   - Recommendation: The TestModel test documents the intended invariant (anchor should accept sectioned capsules). The honest forcing function is the manual real-LLM smoke run. Planner should explicitly include "manual smoke validation" as a task in the plan, even if CI cannot enforce it.

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/personas.py` — direct read (241 lines); Persona dataclass, SCOUT + ANALYST constants, build_writer_system_prompt pattern, registry
- `src/pitcher_narratives/pipeline.py` lines 1-100, 1150-1563 — direct read; _run_pipeline, check_hallucinated_metrics, _PERSONA_KNOWN_METRICS, _KNOWN_METRICS, _METRIC_PATTERN
- `src/pitcher_narratives/anchor.py` — direct read (118 lines); ANCHOR_PROMPT (lines 26-53), WarningCategory, build_anchor_message
- `src/pitcher_narratives/signals.py` — direct read (111 lines); KeySignals model, _FIELD_LABELS, render_key_signals, SIGNAL_EXTRACTOR_PROMPT
- `tests/test_personas.py` — direct read (324 lines); assert_analyst_shape, test_*_pipeline_smoke patterns, fixture loading
- `tests/test_hallucination_guard.py` — direct read (219 lines); per-persona regression vector patterns
- `.planning/REQUIREMENTS.md` — VOICE-03, PERSONA-10, PERSONA-11, TEST-05/06/07 specifications + Out of Scope
- `.planning/STATE.md` — Phase 08 entry + "highest risk" designation + blocker list
- `.planning/phases/08-generic-persona/08-CONTEXT.md` — locked decisions
- `.planning/phases/07-analyst-persona/07-RESEARCH.md` — prior-phase research pattern
- `.planning/phases/07-analyst-persona/07-01-PLAN.md` — prior-phase plan shape
- `pyproject.toml` — dependency versions, pytest config
- Runtime verification: `uv run python -c "import pydantic_ai ..."` → confirmed pydantic-ai 1.72.0, pydantic 2.12.5, pytest 9.0.2
- Runtime verification: `uv run python -c "from pitcher_narratives.signals import _FIELD_LABELS, KeySignals; ..."` → confirmed default KeySignals populates only `top_improvement` + `top_concern` (2 rows minimum)

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` §3c — original generic persona spec (superseded by VOICE-03 + CONTEXT.md on column set and row count)
- `.planning/research/PITFALLS.md` §2, §3, §6 — anchor prompt structural tolerance, revision loop table preservation, streaming issues
- Phase 07's prior guidance that the regex does not false-positive on plain-English terms

### Tertiary (LOW confidence — flagged for validation)
- TestModel behavior with `custom_output_args` — pydantic-ai 1.72.0 may not accept that form; falls back to calling the agent and catching the raw synthetic output. If the anchor-tolerance test cannot be written as a deterministic unit test, escalate to the planner. The real-LLM smoke is the authoritative validation either way.
- The claim that `log.warning` from `pipeline.py` routes to stderr under the CLI's logging config — based on reading `log = logging.getLogger("pitcher_narratives.pipeline")` and matching established call sites. `cli.py` logging config should be verified by the planner before the explainer-check test relies on `caplog`.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, versions confirmed via runtime probe
- Architecture: HIGH — all patterns established by Phase 05-07, direct code reads
- Pitfalls: HIGH — anchor addendum + explainer timing are the real risks; both have clear mitigations
- Overlay voice specification: MEDIUM — the locked overlay text is my recommendation based on CONTEXT.md decisions, not battle-tested against real LLM output. Refinement expected after manual smoke.
- `_PERSONA_KNOWN_METRICS["generic"]` contents: MEDIUM — empty is defensible, small explicit set is defensible; either passes tests

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable — no external dependencies to drift; locked decisions in CONTEXT.md unchanged)
