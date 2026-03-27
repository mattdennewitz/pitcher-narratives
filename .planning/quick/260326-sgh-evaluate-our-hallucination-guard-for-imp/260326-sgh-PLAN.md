---
phase: quick
plan: 260326-sgh
type: execute
wave: 1
depends_on: []
files_modified:
  - report.py
  - tests/test_report.py
autonomous: true
must_haves:
  truths:
    - "P+, S+, L+ are detected when appearing before space/punctuation/end-of-string"
    - "xwOBA and other x-lowercase metrics are matched by the regex"
    - "Traditional outcome stats (ERA, FIP, WHIP, K%, BB%, HR/9) are detected and categorized separately from unknown metrics"
    - "xERA, Barrel%, xHR100 are recognized as known metrics"
    - "Return type distinguishes unknown metrics from outcome stat warnings"
  artifacts:
    - path: "report.py"
      provides: "Fixed hallucination guard with structured return, improved regex, traditional stat detection"
      contains: "class HallucinationReport"
    - path: "tests/test_report.py"
      provides: "Comprehensive tests for all guard improvements"
      contains: "test_hallucination_guard_plus_metrics_in_sentence"
  key_links:
    - from: "report.py"
      to: "tests/test_report.py"
      via: "check_hallucinated_metrics function and HallucinationReport model"
      pattern: "check_hallucinated_metrics"
---

<objective>
Fix six identified gaps in the metric hallucination guard in report.py.

Purpose: The guard currently misses P+/S+/L+ in sentence context, fails to match xwOBA, ignores traditional outcome stats, and returns an unstructured list. These gaps let hallucinated or prohibited metrics pass through to reports undetected.

Output: Hardened hallucination guard with structured HallucinationReport return type, fixed regex patterns, traditional stat detection, and expanded known metric set -- all with comprehensive test coverage.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@report.py (lines 262-317 — hallucination guard section)
@tests/test_report.py (lines 196-228 — hallucination guard tests)
</context>

<interfaces>
<!-- Key types and contracts the executor needs. -->

From report.py (current exports):
```python
__all__ = ["generate_report_streaming", "check_hallucinated_metrics"]

def check_hallucinated_metrics(report_text: str) -> list[str]:
    """Find metric-like terms in report that aren't in the known set."""
```

After this plan, the function signature changes to return HallucinationReport (new Pydantic model).
The function name stays the same for backward compatibility but callers should handle the new return type.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix regex, expand known metrics, add structured return type</name>
  <files>report.py, tests/test_report.py</files>
  <behavior>
    - Test: P+ detected in "His P+ of 112 was solid" (space after +)
    - Test: S+ detected in "S+, L+ both above average" (comma after +)
    - Test: L+ detected at end of string "great L+"
    - Test: xwOBA matched by regex (lowercase w after x)
    - Test: xERA recognized as known (no flag)
    - Test: Barrel% recognized as known (no flag)
    - Test: xHR100 recognized as known (no flag)
    - Test: ERA in report text flagged as outcome_stat_warnings, not unknown_metrics
    - Test: FIP, WHIP, WAR, K%, BB%, HR/9 all flagged as outcome stat warnings
    - Test: HallucinationReport has unknown_metrics: list[str] and outcome_stat_warnings: list[str]
    - Test: HallucinationReport.is_clean property returns True when both lists empty
    - Test: Existing clean-text test still passes (no regressions)
    - Test: xDominance still caught as unknown metric
    - Test: HardHit% still passes as known
  </behavior>
  <action>
  In report.py, make these changes to the hallucination guard section (lines 262-317):

  1. **Add HallucinationReport model** (above the constants): A small Pydantic BaseModel with two fields:
     - `unknown_metrics: list[str]` — metric-like terms not in _KNOWN_METRICS
     - `outcome_stat_warnings: list[str]` — traditional stats the editor prompt warns against
     - `@property def is_clean(self) -> bool` — True when both lists empty
     Add `HallucinationReport` to `__all__`.

  2. **Fix _METRIC_PATTERN regex**: Replace the trailing `\b` with a lookahead `(?=[\s,.);\-:]|$)`. The `\b` fails after `+` and `%` because those aren't word characters. The lookahead correctly matches when followed by whitespace, punctuation, or end-of-string. Also fix the leading `\b` — for the `[PSL]\+` branch, use `(?<![A-Za-z])` lookbehind instead (since `\b` before `P` is fine but the overall group uses `\b` which is OK for the start). Actually the leading `\b` is fine for `P`, `S`, `L`, `x`, `[A-Z]` since those are all word characters. Only the trailing boundary needs fixing.

  3. **Fix xMetric pattern**: Change `x[A-Z][A-Za-z0-9]*` to `x[A-Za-z][A-Za-z0-9]*` to match xwOBA, xERA, etc.

  4. **Add _KNOWN_METRICS entries**: Add `xERA`, `Barrel%`, `xHR100`, `xSwSt` to the frozenset.

  5. **Add _TRADITIONAL_STATS**: New frozenset containing `ERA`, `FIP`, `WHIP`, `WAR`, `W-L`, `K%`, `BB%`, `HR/9`, `K/9`, `BB/9`, `ERA+`, `FIP-`, `Wins`, `Losses`, `Saves`, `IP`.

  6. **Add _TRADITIONAL_PATTERN**: New regex matching these traditional stat patterns. Something like: `\b(ERA\+?|FIP-?|WHIP|WAR|W-L|[KBH][A-Z]?[%/][A-Z0-9]*|Wins|Losses|Saves|IP)(?=[\s,.);\-:]|$)`. Be precise — test it. The pattern should NOT match partial words (e.g., "WHIP" in "WHIPped" should not match, but the lookahead handles that).

  7. **Update check_hallucinated_metrics**: Return `HallucinationReport` instead of `list[str]`. Find advanced metric matches (existing logic with fixed regex), find traditional stat matches, return structured result.

  8. **Update caller in report.py**: Search for any place `check_hallucinated_metrics` is called in report.py itself. If the return is used as a list (e.g., `if check_hallucinated_metrics(text):`), update to use `.is_clean` or `.unknown_metrics`. Based on reading the file, the function is defined but likely called from main.py — check main.py too.

  In tests/test_report.py, update the hallucination guard test section:

  9. **Update imports**: Add `HallucinationReport` to the import list from report.

  10. **Update existing tests**: The five existing tests check `== []` or `"xDominance" in result`. Update these to use the new return type: `result.unknown_metrics == []`, `result.is_clean`, `"xDominance" in result.unknown_metrics`.

  11. **Add new tests**:
      - `test_hallucination_guard_plus_metrics_in_sentence`: P+ in "His P+ of 112 was solid" should be detected and clean (it's known).
      - `test_hallucination_guard_plus_after_comma`: "S+, L+ both above 100" — both detected, both clean.
      - `test_hallucination_guard_xwoba_matched`: "xwOBA of .320" should be detected and clean.
      - `test_hallucination_guard_xera_known`: "xERA near 3.50" should be clean.
      - `test_hallucination_guard_barrel_pct_known`: "Barrel% at 12%" should be clean.
      - `test_hallucination_guard_traditional_stats_warned`: "ERA of 3.50 and WHIP of 1.20" should produce outcome_stat_warnings containing ERA and WHIP, but unknown_metrics should be empty.
      - `test_hallucination_guard_mixed_issues`: Text with both a fabricated metric AND a traditional stat should populate both lists.
      - `test_hallucination_guard_is_clean_property`: Clean text returns is_clean=True; dirty text returns is_clean=False.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run pytest tests/test_report.py -x -v -k hallucination</automated>
  </verify>
  <done>
    - All existing hallucination guard tests pass (updated for new return type)
    - P+/S+/L+ detected in natural sentence context (not just at word boundary)
    - xwOBA matched by regex
    - xERA, Barrel%, xHR100 in known set
    - Traditional stats (ERA, FIP, WHIP, etc.) detected and returned in outcome_stat_warnings
    - check_hallucinated_metrics returns HallucinationReport with unknown_metrics, outcome_stat_warnings, is_clean
    - No regressions in other test_report.py tests
  </done>
</task>

<task type="auto">
  <name>Task 2: Update callers and verify full test suite</name>
  <files>main.py</files>
  <action>
  Check main.py for any usage of check_hallucinated_metrics. If it calls the function and checks the return value as a list, update to use the new HallucinationReport interface:

  - If `hallucinated = check_hallucinated_metrics(text)` then `if hallucinated:` becomes `if not hallucinated.is_clean:`
  - If it prints the list, update to print both `unknown_metrics` and `outcome_stat_warnings` with different severity labels (e.g., "WARNING: Unknown metrics referenced: ..." and "NOTE: Traditional outcome stats referenced (prompt warns against these): ...")
  - If check_hallucinated_metrics is not called in main.py, skip this file

  Run the full test suite to ensure no regressions across all test files.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run pytest tests/ -x -v</automated>
  </verify>
  <done>
    - All callers updated to use HallucinationReport
    - Full test suite passes with zero failures
    - No import errors or type mismatches from the signature change
  </done>
</task>

</tasks>

<verification>
Run the full test suite and confirm:
1. All hallucination guard tests pass (both old and new)
2. No regressions in synthesizer, editor, message builder, or pipeline tests
3. The regex correctly handles P+/S+/L+ in sentence context (not just isolated)
</verification>

<success_criteria>
- check_hallucinated_metrics returns structured HallucinationReport (not list[str])
- P+, S+, L+ matched when followed by space, comma, period, or end-of-string
- xwOBA and other x-lowercase metrics matched by regex
- xERA, Barrel%, xHR100, xSwSt added to known metrics
- Traditional stats (ERA, FIP, WHIP, etc.) detected and categorized separately
- All tests pass: `uv run pytest tests/ -x -v` exits 0
</success_criteria>

<output>
After completion, create `.planning/quick/260326-sgh-evaluate-our-hallucination-guard-for-imp/260326-sgh-SUMMARY.md`
</output>
