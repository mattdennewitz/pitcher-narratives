# Phase 7: Revision UX & Validation - Research

**Researched:** 2026-03-28
**Domain:** CLI stderr output for reflection loop status reporting
**Confidence:** HIGH

## Summary

Phase 7 is a pure UX wiring task: modify `cli.py` to print revision loop status messages to stderr after `generate_report_streaming()` returns. The data model already provides everything needed -- `ReportResult.revision_count` (0 = first-try pass, 1-2 = revised) and `ReportResult.anchor_warnings` (surviving warnings list). The phase adds no new dependencies, no new models, no new agent calls. It changes only how existing data is presented to the user.

The implementation is constrained to `cli.py` lines ~138-142 (the existing anchor check block) and must reuse the established `print(..., file=sys.stderr)` pattern with `[CATEGORY] description` warning formatting. Three distinct messages cover all loop outcomes: first-try clean, revised-and-converged, and exhausted-with-warnings.

**Primary recommendation:** Replace the current unconditional "ANCHOR CHECK:" stderr block in `cli.py` with conditional logic branching on `revision_count` and `anchor_warnings`, keeping the exact same warning format.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- First-try clean: stderr shows "Passed anchor check" (or equivalent)
- Revisions that converge: stderr shows "Revised N time(s) -- anchor check passed"
- Max revisions exhausted with surviving warnings: stderr shows each surviving warning description
- Surviving warnings use same format as existing anchor check stderr output (see cli.py current pattern: `[CATEGORY] description`)
- All revision status messages go to stderr (not stdout)
- No new output channels or formats -- reuse existing patterns from cli.py
- Stdout reserved exclusively for the narrative report (already established)

### Claude's Discretion
- Exact stderr message wording beyond what success criteria specify
- Whether to print revision status from within generate_report_streaming() or from cli.py
- Whether to add a helper function for formatting or inline the prints

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOOP-03 | Warnings that survive all iterations are passed through to stderr (same format as current anchor output) | ReportResult.anchor_warnings already contains surviving warnings as AnchorWarning objects; cli.py already has the `[CATEGORY] description` print pattern at line ~142 |
| UX-03 | Stderr shows revision status ("Passed anchor check" or "Revised N times -- [surviving warnings]") | ReportResult.revision_count (0/1/2) plus anchor_warnings list provide all data needed for the three-branch conditional |
</phase_requirements>

## Standard Stack

No new libraries. Phase 7 uses only Python builtins (`sys.stderr`, `print`).

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.14+ | `print(..., file=sys.stderr)` | Already used throughout cli.py |

### Supporting
No supporting libraries needed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| print() to stderr | logging module | Overkill -- project uses print to stderr for all user-facing diagnostics; logging adds config burden for no benefit |
| Inline prints | Helper function | Discretionary -- helper is cleaner if formatting logic exceeds ~5 lines, inline is fine otherwise |

## Architecture Patterns

### Recommended Approach: Conditional Block in cli.py

The current code at lines 138-142 of `cli.py` unconditionally prints anchor warnings:

```python
# 1. Anchor check warnings (from Phase 2.5)
if result.anchor_warnings:
    print("\nANCHOR CHECK:", file=sys.stderr)
    for w in result.anchor_warnings:
        print(f"  [{w.category}] {w.description}", file=sys.stderr)
```

Replace this with a three-branch conditional:

```python
# Revision loop status
if result.revision_count == 0 and not result.anchor_warnings:
    # First-try clean
    print("\nPassed anchor check", file=sys.stderr)
elif result.anchor_warnings:
    # Exhausted revisions with surviving warnings
    print(f"\nRevised {result.revision_count} time(s) -- anchor check found issues:", file=sys.stderr)
    for w in result.anchor_warnings:
        print(f"  [{w.category}] {w.description}", file=sys.stderr)
else:
    # Revised and converged to clean
    print(f"\nRevised {result.revision_count} time(s) -- anchor check passed", file=sys.stderr)
```

### Pattern: Keep Printing in cli.py, Not report.py

The CONTEXT.md notes this is Claude's discretion. The established pattern is clear: `report.py` does NOT print to stderr (it returns data), and `cli.py` handles all user-facing output. This separation should be maintained. Putting prints inside `generate_report_streaming()` would break the pattern and make testing harder (subprocess tests capture stderr; unit tests of report.py do not).

**Confidence:** HIGH -- this follows the existing separation visible in the codebase.

### Anti-Patterns to Avoid
- **Printing in report.py:** Breaks the data-return/presentation-layer separation that cli.py and report.py already follow.
- **New output format:** Success criteria explicitly require same format as existing anchor output. Do not introduce colors, prefixes, emoji, or structured formatting.
- **Suppressing warnings on convergence:** When `revision_count > 0` and `anchor_warnings` is empty, the user should see that revisions happened AND that the result is clean. Both facts matter.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stderr formatting | Custom formatter class | Inline `print(f"...", file=sys.stderr)` | Existing pattern, 3 lines max per branch |

**Key insight:** This phase is so small that the "don't hand-roll" risk is minimal. The danger is over-engineering, not under-engineering.

## Common Pitfalls

### Pitfall 1: Forgetting the revision_count=0 + warnings case
**What goes wrong:** If you only check `revision_count == 0` for "Passed anchor check", you miss the edge case where the first anchor check finds issues but then the code never enters the for-loop body (impossible with current code, but defensive).
**Why it happens:** Conflating "revision_count=0" with "clean". In the current for/else loop, revision_count=0 always means clean (the break happened on first anchor check), but the conditional should still check both fields for clarity.
**How to avoid:** Branch on `(revision_count, bool(anchor_warnings))` together, not on either alone.
**Warning signs:** Test passes for first-try clean but shows wrong message when revision_count > 0.

### Pitfall 2: Breaking the existing hallucination check output
**What goes wrong:** The hallucination check (`check_hallucinated_metrics`) runs AFTER the anchor check block (lines 145-158). If you restructure the anchor output block, you might accidentally delete or move the hallucination check.
**Why it happens:** The two stderr blocks are adjacent and both conditional.
**How to avoid:** Only modify lines 138-142 (the anchor check block). Leave lines 145-158 (hallucination check) untouched.
**Warning signs:** `test_cli_valid_pitcher_exit_0` passes but hallucination warnings disappear.

### Pitfall 3: Pluralization of "time(s)"
**What goes wrong:** "Revised 1 time(s)" looks unpolished.
**Why it happens:** Hardcoded pluralization string.
**How to avoid:** Use a conditional or `time` vs `times` based on count. Or just use `time(s)` which is acceptable and matches the success criteria phrasing.
**Warning signs:** Aesthetic nit, not a functional bug.

### Pitfall 4: TestModel always produces dirty anchor, making first-try-clean test require mocking
**What goes wrong:** The default `TestModel()` returns an `AnchorResult` with 1 warning (always dirty). A CLI integration test using `PITCHER_NARRATIVES_TEST_MODEL=1` will always exercise the revision-exhausted path, never the first-try-clean path.
**Why it happens:** `TestModel()` has a default output that includes a warning for structured types.
**How to avoid:** For unit-level testing of the conditional logic, construct `ReportResult` objects directly with different `revision_count`/`anchor_warnings` combinations. For integration tests, accept that TestModel only exercises one path and test the other paths at the unit level.
**Warning signs:** Cannot write an integration test that verifies "Passed anchor check" without mocking.

## Code Examples

### Current Anchor Check Block (to be replaced)
```python
# Source: cli.py lines 138-142 (current code)
if result.anchor_warnings:
    print("\nANCHOR CHECK:", file=sys.stderr)
    for w in result.anchor_warnings:
        print(f"  [{w.category}] {w.description}", file=sys.stderr)
```

### ReportResult Fields Available for Branching
```python
# Source: report.py lines 432-440
class ReportResult(BaseModel):
    narrative: str
    social_hook: str
    fantasy_insights: str
    anchor_warnings: list[AnchorWarning]
    revision_count: int = 0
```

### Three Outcome Scenarios

| Scenario | revision_count | anchor_warnings | Expected stderr |
|----------|---------------|-----------------|-----------------|
| First-try clean | 0 | [] | "Passed anchor check" |
| Revised and converged | 1 or 2 | [] | "Revised N time(s) -- anchor check passed" |
| Exhausted with warnings | 2 (= MAX_REVISIONS) | [AnchorWarning, ...] | "Revised N time(s) -- anchor check found issues:" + warning lines |

### Test Pattern: CLI Integration Tests
```python
# Source: tests/test_cli.py -- existing pattern for checking stderr
# Uses subprocess to capture stderr separately from stdout
result = subprocess.run(
    [sys.executable, "-m", "pitcher_narratives.cli", "-p", "592155"],
    capture_output=True,
    text=True,
    timeout=60,
    env=_test_env(PITCHER_NARRATIVES_TEST_MODEL="1"),
)
assert "expected text" in result.stderr
```

### Test Pattern: Unit Tests for Conditional Logic
```python
# Construct ReportResult directly to test each branch
# No LLM call needed -- just test the output formatting
from pitcher_narratives.report import AnchorWarning, ReportResult

# First-try clean
result = ReportResult(narrative="n", social_hook="s", fantasy_insights="f",
                      anchor_warnings=[], revision_count=0)
# Revised and converged
result = ReportResult(narrative="n", social_hook="s", fantasy_insights="f",
                      anchor_warnings=[], revision_count=2)
# Exhausted with warnings
result = ReportResult(narrative="n", social_hook="s", fantasy_insights="f",
                      anchor_warnings=[AnchorWarning(category="MISSED_SIGNAL", description="test")],
                      revision_count=2)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single anchor check, print all warnings | Revision loop with 3 outcome states | Phase 6 (this milestone) | cli.py must now distinguish clean/revised/exhausted |

**Deprecated/outdated:**
- The old unconditional `if result.anchor_warnings:` block (lines 138-142) is now insufficient -- it only handles the "has warnings" case and does not communicate revision count or first-try-clean status.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via uv) |
| Config file | none -- default discovery in tests/ |
| Quick run command | `uv run pytest tests/test_cli.py -x -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOOP-03 | Surviving warnings printed to stderr with [CATEGORY] format | integration | `uv run pytest tests/test_cli.py::test_cli_revision_exhausted_shows_warnings -x` | Wave 0 |
| UX-03 (clean) | First-try clean prints "Passed anchor check" to stderr | unit | `uv run pytest tests/test_cli.py::test_revision_status_first_try_clean -x` | Wave 0 |
| UX-03 (revised) | Revised-and-converged prints "Revised N time(s)" to stderr | unit | `uv run pytest tests/test_cli.py::test_revision_status_revised_and_converged -x` | Wave 0 |
| UX-03 (exhausted) | Exhausted prints count + surviving warnings to stderr | integration | `uv run pytest tests/test_cli.py::test_cli_revision_exhausted_shows_warnings -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_cli.py -x -q`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_cli.py::test_revision_status_first_try_clean` -- unit test constructing ReportResult with revision_count=0 and empty warnings, verifying stderr output
- [ ] `tests/test_cli.py::test_revision_status_revised_and_converged` -- unit test constructing ReportResult with revision_count=1 and empty warnings, verifying stderr output
- [ ] `tests/test_cli.py::test_cli_revision_exhausted_shows_warnings` -- integration test (subprocess with TestModel) verifying stderr contains "Revised" and `[CATEGORY]` warning lines

Note on testing strategy: The integration test using `PITCHER_NARRATIVES_TEST_MODEL=1` always exercises the exhausted-with-warnings path (TestModel always returns dirty anchor). The first-try-clean and revised-and-converged paths must be tested at the unit level by either (a) extracting the conditional logic into a testable function, or (b) patching `generate_report_streaming` to return a pre-built ReportResult. Approach (a) is cleaner -- extract a `_print_revision_status(result: ReportResult)` helper and test it directly with constructed ReportResult objects.

## Open Questions

1. **Should the helper be extracted?**
   - What we know: The conditional has 3 branches and ~8 lines. It can be inline or a helper.
   - What's unclear: Whether the planner/executor prefers inline or extracted.
   - Recommendation: Extract a `_print_revision_status(result: ReportResult)` function in cli.py. This makes unit testing trivial (call the function, capture stderr with `capsys` fixture) without needing subprocess tests for all three branches. The integration test covers the hot path (exhausted with warnings).

2. **Exact wording for exhausted-with-warnings header**
   - What we know: Success criteria say "stderr shows the surviving warning descriptions." The existing pattern uses "ANCHOR CHECK:" as header.
   - What's unclear: Whether to keep "ANCHOR CHECK:" header or change to "Revised N time(s) -- anchor check found issues:"
   - Recommendation: Use "Revised N time(s) -- anchor check found issues:" to communicate both the revision count AND that warnings remain. This is more informative than the old "ANCHOR CHECK:" header and stays within the "same format" constraint (same `[CATEGORY] description` indented lines).

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/cli.py` -- read in full, lines 1-163
- `src/pitcher_narratives/report.py` -- read in full, lines 1-913
- `tests/test_cli.py` -- read in full, lines 1-183
- `tests/test_report.py` -- read in full, lines 1-648
- `.planning/phases/06-loop-mechanics/06-01-PLAN.md` -- Phase 6 plan confirming loop implementation
- `.planning/phases/07-revision-ux-validation/07-CONTEXT.md` -- User decisions

### Secondary (MEDIUM confidence)
None needed -- this phase is entirely about existing codebase patterns.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, pure Python stdlib
- Architecture: HIGH -- existing patterns in cli.py are clear and established
- Pitfalls: HIGH -- all pitfalls identified from reading the actual implementation code

**Research date:** 2026-03-28
**Valid until:** Indefinite -- this phase has no external dependencies that could change
