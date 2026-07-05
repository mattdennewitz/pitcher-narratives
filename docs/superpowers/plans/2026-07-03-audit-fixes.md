# Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all findings from the 2026-07-03 agent-prompt / model-settings / editorial-loop audit: prompt inaccuracies, a silent temperature override, wrong pricing, fail-open auditor paths, a hallucination-laundering path, non-composing validation loops, and a calibration metric bug.

**Architecture:** All changes are surgical edits to the existing pydantic-ai pipeline (`src/pitcher_narratives/`). No new modules. Behavioral changes to the editorial loop fail CLOSED (auditor failure ⇒ UNVERIFIED, never silently verified).

**Tech Stack:** Python 3.14, pydantic-ai 1.72, polars, pytest via uv.

## Global Constraints

- Run tests from the worktree root with the data dir env var (worktree lacks gitignored `var/`):
  `PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest tests/<file> -q`
- Pre-existing known failure: `test_context.py::test_to_prompt_token_budget` — do not try to fix it; everything else must pass.
- Conventional commit messages (`fix:`, `feat:`, `test:` with scope), one commit per task.
- Do not reformat or reflow text you are not changing. Prompt constants are long wrapped strings — edit only the targeted lines.
- If a test asserts old prompt text or old pricing, update the test to the new value in the same commit.
- `AuditFlag`/`AuditResult` live in `src/pitcher_narratives/models.py`; check field types there before adding a new category value.
- The sentinel audit category introduced in Task 7 is the exact string `"AUDIT_FAILED"` — Tasks 7 and 8 both use it.

---

### Task 1: Pricing + calibration metric corrections (mechanical)

**Files:**
- Modify: `src/pitcher_narratives/costs.py:16`
- Modify: `src/pitcher_narratives/calibration.py:111-114`
- Test: `tests/test_costs.py`, `tests/test_calibration.py`

**Why:** Haiku 4.5 is $1.00/$5.00 per MTok (current table has Haiku 3.5's $0.80/$4.00 — every mini-model call under-costed ~20%). `fact_hit_cap_rate` currently counts ANY successful fact revision (`capsule_revised`) as "hit the cap"; hitting the cap means the loop exhausted with residual flags (`n_capsule_audit_flags > 0`). Also the pricing test asserts the stale `gemini-3.1-pro-preview` instead of the actual run model `gemini-3.5-flash`.

- [ ] **Step 1: Write/adjust failing tests.** In `tests/test_costs.py`: assert `PRICING["claude-haiku-4-5"] == {"input": 1.00, "output": 5.00}` and that every model in `PROVIDERS`/`MINI_PROVIDERS` (bare names via `model_label`) has a PRICING row — replace any assertion listing `gemini-3.1-pro-preview` as a run model (keep its PRICING row as legacy). In `tests/test_calibration.py`: add a test where a record has `fact_depth_cap=2, capsule_revised=True, n_capsule_audit_flags=0` → `fact_hit_cap_rate == 0.0`, and one with `n_capsule_audit_flags=2` → `1.0`.
- [ ] **Step 2: Run tests, verify the new ones fail.**
- [ ] **Step 3: Implement.** `costs.py:16` → `"claude-haiku-4-5": {"input": 1.00, "output": 5.00},`. `calibration.py` fact_hits →

```python
        fact_hits = sum(
            1 for r in rs
            if r["fact_depth_cap"] > 0 and r["n_capsule_audit_flags"] > 0
        )
```

- [ ] **Step 4: Run `tests/test_costs.py tests/test_calibration.py` — all pass.**
- [ ] **Step 5: Commit** `fix(costs,calibrate): correct Haiku 4.5 pricing; fact_hit_cap_rate counts residual flags, not any revision`

### Task 2: Prompt text corrections in pipeline.py / anchor.py / curator.py

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` (lines ~27, ~280, ~337, ~403-410, ~417-458, ~530-561)
- Modify: `src/pitcher_narratives/anchor.py:87`
- Modify: `src/pitcher_narratives/curator.py:5`
- Test: `tests/test_pipeline.py`, `tests/test_role_guidance.py`, `tests/test_anchor.py` (update any assertions on old text)

Exact edits (all prompt-text only; preserve surrounding wrapping):

1. `_LOCATION_SPECIALIST_PROMPT` (~line 280): `"L+ above 0 means location helps"` → `"L+ above 100 means location helps (L+ is 100-centered, like S+/P+)"`.
2. `_TREND_SPECIALIST_PROMPT` (~line 337): `- Movement changes (pfx_x/pfx_z deltas)` → `- Movement changes for the primary fastball (pfx_x/pfx_z deltas are provided only there; assess other pitches via their P+/S+/L+ deltas, do not derive movement deltas from raw values)`.
3. `_RP_GAME_SHAPE_GUIDANCE` (~403-410): delete the `Pitch count efficiency: how many pitches per batter faced?` bullet (batters-faced is not in the input). Change the platoon bullet to `- Platoon-specific strengths and vulnerabilities by handedness — only when the input includes TTO/platoon splits; if absent, skip this angle rather than inferring it`.
4. `_DATA_AUDITOR_PROMPT` (~417-458): append a final paragraph before the closing `If everything checks out` line:
   `Checks that reference [NORMAL]/[OUTLIER] tags or S-variant metrics (xRV100_S, xWhiff_S) apply ONLY when those artifacts appear in the ground truth data. When the ground truth has no such tags or metrics (e.g. trends or game-shape data), skip those checks — do not flag their absence.`
5. `_EXECUTIVE_SUMMARY_PROMPT` (~552-553): replace the `If metric within ±1.5 stddev of league average, normal.` sentence with `If the report or attached analyses tag a metric [NORMAL], treat it as normal.` (the summarizer has no stddev tables — only the report + specialist prose with tags).
6. Delete the unused `class ExecutiveSummary(BaseModel)` (~558-561) — first `grep -rn "ExecutiveSummary" src tests` to confirm nothing imports it (remove from `__all__` if listed).
7. Module docstring (~line 27): fix the stale claim that the executive summary runs "concurrently with the writer" — it runs as a second step after the anchor loop (see `_run_summaries`).
8. `anchor.py:87`: `"Check the capsule against the synthesis. Report any issues or respond CLEAN."` → `"Check the capsule against the synthesis. Report any issues, or return an empty warnings list if everything checks out."`
9. `curator.py:5` docstring: `across four categories` → `across six categories`.

- [ ] **Step 1:** `grep -rn "above 0 means\|pitches per batter\|respond CLEAN\|four categories\|ExecutiveSummary\|±1.5 stddev" src tests` to find every assertion site.
- [ ] **Step 2: Apply edits above; update test assertions to the new text.**
- [ ] **Step 3: Run `tests/test_pipeline.py tests/test_role_guidance.py tests/test_anchor.py -q` — pass.**
- [ ] **Step 4: Commit** `fix(prompts): correct L+ scale, unexecutable data requests, stale docs in specialist/auditor/anchor prompts`

### Task 3: Signal extractor prompt alignment

**Files:**
- Modify: `src/pitcher_narratives/signals.py:105-116` (SIGNAL_EXTRACTOR_PROMPT)
- Test: `tests/test_signals.py`

Edits:
1. `development_pitch`: `high S+ (>110) but low L+ (<90)` → `high S+ (110 or above) but low L+ (80 or below)` — matches the scout's canonical thresholds (`scout.py:62-63`).
2. `specialist_tension` example: `stuff says the curveball is elite (S+ 128)` → `stuff grades the curveball highly (S+ 128)` — "elite" is banned by SHARED_WRITER_BASE and signal text is quoted into the writer input.
3. `arsenal_dependency` evidence example: `(e.g., whiff share, xRV100 gap)` → `(e.g., xRV100 gap, xWhiff contrast across pitches)` — "whiff share" is not a metric any specialist input carries.

- [ ] **Step 1: Update any test assertions on the old text (`grep -n "whiff share\|elite\|>110\|<90" tests/test_signals.py src/pitcher_narratives/signals.py`).**
- [ ] **Step 2: Apply edits; run `tests/test_signals.py -q` — pass.**
- [ ] **Step 3: Commit** `fix(signals): align extractor thresholds with scout canon; drop banned word and unavailable metric from examples`

### Task 4: Claude thinking-effort clamp + curator determinism

**Files:**
- Modify: `src/pitcher_narratives/config.py` (claude branch of `make_model_settings`, ~104-121)
- Modify: `src/pitcher_narratives/curator.py:150-156`
- Modify: `src/pitcher_narratives/pipeline.py:1323-1325` (comment only)
- Test: `tests/test_config.py`, `tests/test_curator.py`

**Why:** (a) Sonnet 4.6 accepts thinking efforts low/medium/high/max; `--thinking xhigh` or `minimal` reaches the writer unclamped and can 400. (b) The curator requests temperature 0.0 for determinism but `thinking="medium"` + max_tokens 8192 takes the Claude thinking branch which forces temperature=1 — defeating its documented design.

- [ ] **Step 1: Write failing tests** in `tests/test_config.py`:

```python
def test_claude_thinking_clamped_to_supported_efforts():
    s = make_model_settings("claude", "xhigh", 0.7, max_tokens=4096)
    assert s["thinking"] == "high"
    s = make_model_settings("claude", "minimal", 0.7, max_tokens=4096)
    # minimal is not a valid Anthropic effort; clamps to low — and low
    # still routes through the thinking branch only if max_tokens > 2048
    assert s["thinking"] == "low"
```

and in `tests/test_curator.py`: build the selector agent for provider `"claude"` and assert its `model_settings["temperature"] == 0.0` and `"thinking" not in model_settings` (exact access pattern: mirror how existing tests inspect settings).
- [ ] **Step 2: Run — fail.**
- [ ] **Step 3: Implement.** In `config.py`, at the top of the claude thinking branch (after the mini/disable/small-budget early return):

```python
        # Anthropic accepts low/medium/high/max efforts; clamp the CLI's
        # wider scale so xhigh/minimal never reach the API and 400.
        _CLAUDE_EFFORTS = {"minimal": "low", "xhigh": "high"}
        thinking = _CLAUDE_EFFORTS.get(thinking, thinking)
```

In `curator.py`, pass `disable_thinking=True` in the `make_model_settings(...)` call and extend the `_SELECTOR_TEMPERATURE` docstring: `Thinking is disabled so the Claude path honors temperature 0 (Anthropic forces temperature=1 when thinking is on).` In `pipeline.py:1323`, extend the comment: `On the Claude provider, thinking-enabled agents (stuff, writer) run at temperature 1 by API constraint; the split below is fully honored on Gemini and on Haiku-tier (thinking-off) agents.`
- [ ] **Step 4: Run `tests/test_config.py tests/test_curator.py -q` — pass.**
- [ ] **Step 5: Commit** `fix(config,curator): clamp Claude thinking efforts to supported set; restore curator temp-0 determinism via disable_thinking`

### Task 5: Temporal Context plumbing to trend/game-shape/writer inputs

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — `_build_trend_input` (~733-759), `_build_game_shape_input` (~780-837), `build_writer_input` (~840-866)
- Test: `tests/test_pipeline.py` (and `tests/test_temporal.py`, `tests/test_voice_golden.py` if input fixtures shift)

**Why:** The trend/game-shape system prompts and SHARED_WRITER_BASE all instruct "the data includes a 'Temporal Context' section — respect the prior-year relevance level", but `render_temporal_section(ctx)` (prompt_builder.py:57) is only emitted on the single-agent path. The instruction is currently unexecutable for these agents.

- [ ] **Step 1: Write failing tests:** flatten each builder's output (`_flatten_prompt`) for a ctx with temporal data and assert the rendered temporal section text is present in `_build_trend_input`, `_build_game_shape_input`, and `build_writer_input` output. Reuse an existing ctx fixture from `tests/test_pipeline.py`.
- [ ] **Step 2: Implement.** Import `render_temporal_section` (already imported in pipeline.py for the single-agent path — verify; else add to the prompt_builder import block). In `_build_trend_input`, insert `render_temporal_section(ctx)` as the FIRST entry of `data_sections` (empty strings are already filtered). Same in `_build_game_shape_input`. In `build_writer_input`, insert after the pitcher header line:

```python
    temporal = render_temporal_section(ctx)
    if temporal:
        parts.append(temporal + "\n")
```

- [ ] **Step 3: Run `tests/test_pipeline.py tests/test_temporal.py tests/test_voice_golden.py -q`; update any exact-input fixtures the change legitimately shifts.**
- [ ] **Step 4: Commit** `feat(pipeline): provide Temporal Context section to trend/game-shape specialists and writer, satisfying their temporal-grounding rules`

### Task 6: Personas — RECAP framing variant + CHANGES mandate reword

**Files:**
- Modify: `src/pitcher_narratives/personas.py` (`_SYNTHESIS_FRAMING` ~150-180, `RECAP_BRIEF` ~495-505, `_CHANGES_MANDATE` ~330-345)
- Test: `tests/test_personas.py`

**Why:** (a) RECAP's contract uses `_SYNTHESIS_FRAMING`, whose mandatory "EXPLAIN THE MODEL" block conflicts with the 40-90-word recap cap (the pipeline already sets `check_explainer=False` for recap). (b) `_CHANGES_MANDATE` tells the writer to react to "the Recent vs Prior Window block", which only the trends specialist sees — the writer gets specialist prose, not the block.

- [ ] **Step 1: Write failing tests:** `RECAP_BRIEF.input_framing` does not contain `"EXPLAIN THE MODEL"` but does contain the Key Signals rule; `_CHANGES_MANDATE` (via the CHANGES contracts' structure text) does not contain `"Recent vs Prior Window block"` and does contain `"trend analysis"`.
- [ ] **Step 2: Implement.** Split `_SYNTHESIS_FRAMING` into `_SYNTHESIS_RULES` (everything up to and excluding the `EXPLAIN THE MODEL:` paragraph) and redefine `_SYNTHESIS_FRAMING = _SYNTHESIS_RULES + "\n\n" + _EXPLAIN_THE_MODEL` (extract the explain block as its own constant so nothing is duplicated). Set `RECAP_BRIEF`'s `input_framing=_SYNTHESIS_RULES`. All other contracts keep `_SYNTHESIS_FRAMING` — byte-identical composed text for REPORT/CHANGES personas (verify against any golden prompt tests). In `_CHANGES_MANDATE`, reword the release-point sentence to reference what the writer can see, e.g.: `When the trend analysis reports a release-point or extension shift alongside a velo or shape change, pair it as a mechanical-adjustment signal and name it as such… A usage shift with no reported release-point movement reads as a pitch-mix or game-plan change instead. Never claim a mechanical cause the analyses don't support; hedge explicitly when the trend analysis says not to over-read the release-point move.`
- [ ] **Step 3: Run `tests/test_personas.py tests/test_voice_golden.py -q` — pass (REPORT/CHANGES framing must be byte-identical to before).**
- [ ] **Step 4: Commit** `fix(personas): recap framing drops unmeetable EXPLAIN-THE-MODEL demand; CHANGES mandate references writer-visible trend analysis`

### Task 7: Fail closed on auditor errors

**Files:**
- Modify: `src/pitcher_narratives/models.py` (AuditFlag.category — add `"AUDIT_FAILED"` if category is a Literal; if plain str, no change)
- Modify: `src/pitcher_narratives/pipeline.py` — `_audit_one` (~978-989), `run_capsule_audit` first-audit except (~1786-1792)
- Test: `tests/test_pipeline.py`

**Why:** Today a capsule-auditor crash returns `(capsule, [], False)` → `is_unverified()` False → an entirely unaudited report ships as verified. A specialist-audit crash returns `AuditResult(is_clean=True)` → flawed prose flows to the writer marked clean with no trace.

- [ ] **Step 1: Write failing tests** with a stub auditor whose `run` raises: (a) `run_capsule_audit` returns exactly one residual flag with `category == "AUDIT_FAILED"` (so `is_unverified` → True and `residual_banner` fires); (b) `audit_and_revise_specialists` returns the specialist's original text unchanged, appends one `AUDIT_FAILED` flag tagged with the specialist name to the returned flags, and does NOT invoke the revision path for that specialist (assert the specialist agent's run was not called a second time).
- [ ] **Step 2: Implement.** In `run_capsule_audit`:

```python
    except Exception:
        log.warning("Capsule auditor failed; marking report UNVERIFIED.", exc_info=True)
        return capsule, [_audit_failed_flag()], False
```

with a small module-level helper:

```python
def _audit_failed_flag(specialist: str = "") -> AuditFlag:
    """Sentinel flag: the auditor itself crashed, so nothing was verified.
    Fail closed — an unaudited report must surface as UNVERIFIED."""
    return AuditFlag(
        category="AUDIT_FAILED",
        claim="(auditor call failed — report not fact-checked)",
        data_shows="the audit agent raised before producing a verdict",
        suggested_fix="re-run, or review the report manually",
        specialist=specialist,
    )
```

(match AuditFlag's actual required fields from models.py). In `_audit_one`, replace `return name, AuditResult(is_clean=True, flags=[])` with returning a sentinel result the collector recognizes: `return name, None`. In the collection loop, `if audit_result is None: all_flags.append(_audit_failed_flag(name)); continue` — the sentinel joins `all_flags` (visible in `PipelineResult.audit_flags` and calibration `n_audit_flags`) but never enters `flagged`, so no bogus revision runs. Adjust `_audit_one`'s return type annotation to `tuple[str, AuditResult | None]`.
- [ ] **Step 3: Run `tests/test_pipeline.py -q` — pass.**
- [ ] **Step 4: Commit** `fix(pipeline): auditor crashes fail closed — sentinel AUDIT_FAILED flag instead of silently-verified output`

### Task 8: Re-audit specialist revisions; exclude unverified prose from the parity union

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — `audit_and_revise_specialists` (~935-1038), `_build_parity_union` (~492-500), `_render_capsule` (~1959), `models.py` (`CoreContext`/`AnalyzedContext` gain `residual_specialists: list[str] = []`), `run_spine_core`/`run_spine_tail` plumb it
- Test: `tests/test_pipeline.py`

**Why (hallucination laundering):** a flagged specialist gets ONE revision that is never re-checked, and the fact-check "ground truth" (`_build_parity_union`) includes all specialist prose — so a fabricated number in an unverified revision becomes citable truth for the capsule auditor.

- [ ] **Step 1: Write failing tests:** (a) stub auditor flags a specialist, specialist returns a revision, auditor (call 2 for that specialist) still flags it → the returned flags include the residual re-audit flags AND the specialist name appears in the returned residual set; when the re-audit is clean → residual set empty. (b) `_build_parity_union(ctx, specialists, key_signals, exclude={"trends"})` output does not contain the trends prose but still contains the raw ground truth and other specialists.
- [ ] **Step 2: Implement.**
  - In `audit_and_revise_specialists`, after applying revisions, re-audit ONLY the revised specialists (one bounded extra pass, reuse `_audit_one` against the revised text). Append any re-audit flags to `all_flags` (specialist-tagged). Build `residual = {name for name in revised if re-audit flagged or re-audit failed}`. Change the return to `tuple[SpecialistOutputs, list[AuditFlag], set[str]]` and update the two call sites (`run_spine_core`, `run_spine_tail`) — store on `CoreContext.residual_specialists` / `AnalyzedContext.residual_specialists` (new list field, default empty, so existing constructors elsewhere stay valid).
  - `_build_parity_union(ctx, specialists, key_signals, *, exclude: set[str] = frozenset())`: skip prose of excluded specialists (raw ground truth + key signals always included).
  - `_render_capsule` passes `exclude=set(analyzed.residual_specialists)`.
  - **Ground-truth completeness for trends audits:** `run_spine_tail` passes `trend_frame_comparison` into `run_specialists`, but `audit_and_revise_specialists` builds its `ground_truths` via `_get_specialist_input_text(name, ctx)` — WITHOUT the frame block. So the trends auditor (and now the re-audit) sees ground truth missing a section the specialist legitimately cited, false-flagging frame-block numbers as FABRICATED_DATA. Add an optional `trend_frame_comparison: str | None = None` parameter to `audit_and_revise_specialists`; when set and `"trends"` is in `audit_names`, append it to the trends ground truth. Pass it from `run_spine_tail` (which already has it in scope). Add a test: trends ground truth handed to the auditor contains the frame-comparison text when provided.
- [ ] **Step 3: Run `tests/test_pipeline.py -q` and the full suite touching the spine (`tests/test_pipeline.py tests/test_morning.py -q`) — pass.**
- [ ] **Step 4: Commit** `fix(pipeline): re-audit specialist revisions; unverified specialist prose no longer counts as fact-check ground truth`

### Task 9: Compose the anchor and fact loops

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — `is_unverified` (~1249-1257), `residual_banner` (~1260-1272), `_render_capsule` (after the fact loop, ~1969), `run_anchor_revision_loop` (~1668-1696)
- Test: `tests/test_pipeline.py`

**Why:** (a) Residual primary anchor warnings (MISSED_SIGNAL, DIRECTION_ERROR) never gate shipping. (b) The fact loop runs after the anchor loop and can rewrite the capsule with no anchor re-check. (c) The anchor loop has no stall detection — identical warnings can recur until the cap, wasting tokens.

- [ ] **Step 1: Write failing tests:** (a) `is_unverified(PipelineResult(... anchor_warnings=[AnchorWarning(category="MISSED_SIGNAL", ...)]))` is True; `UNDERWEIGHTED`-only stays False; `residual_banner` mentions the surviving warning count. (b) with a fake fact auditor that forces one revision and a fake anchor agent, `_render_capsule` runs one extra anchor check after the fact revision and merges its warnings (assert the anchor agent call count and the merged warnings on the result). (c) an anchor agent returning the SAME warnings twice in a row breaks the loop early (writer revision called once, not `max_revisions` times).
- [ ] **Step 2: Implement.**
  - `_GATING_ANCHOR_CATEGORIES = ("MISSED_SIGNAL", "DIRECTION_ERROR")`; `is_unverified` → `bool(result.capsule_audit_flags) or any(w.category in _GATING_ANCHOR_CATEGORIES for w in result.anchor_warnings)`. `residual_banner` mirrors the same condition and words both sources (`{n} flagged claim(s) and/or {m} unresolved primary anchor warning(s) survived validation`).
  - In `_render_capsule`, after `run_capsule_audit`: `if capsule_revised:` run one anchor check (no revision) via `agents.anchor.run(build_anchor_message(synthesis, capsule))`, record usage stage `"anchor"`, and replace `anchor_check` with a merged result (existing warnings + new ones, deduped by `(category, description)`).
  - In `run_anchor_revision_loop`: track `prev = {(w.category, w.description) for w in anchor_check.warnings}`; if the new iteration's set equals `prev`, log `"Anchor loop stalled (identical warnings); stopping early."` and return `(capsule, anchor_check, revision_count)` immediately.
- [ ] **Step 3: Run `tests/test_pipeline.py tests/test_morning.py -q` — pass.**
- [ ] **Step 4: Commit** `feat(pipeline): gate on residual primary anchor warnings, re-anchor after fact revision, stall-break the anchor loop`

### Task 10: Ground-truth-carrying fact revisions + signals_failed propagation + guard on all modes

**Files:**
- Modify: `src/pitcher_narratives/pipeline.py` — `build_fact_revision_message` (~511-524), `run_capsule_audit` call site of it (~1806), `PipelineResult` (~1192), `flag_summary` (~1207), `_run_pipeline` (~2115), `render_recap` (~2030), `_TRADITIONAL_PATTERN` (~2342)
- Modify: `src/pitcher_narratives/cli.py` (~316 area)
- Test: `tests/test_pipeline.py`, `tests/test_hallucination_guard.py`, `tests/test_cli.py`

**Why:** (a) The fact-revision prompt gives the writer only the capsule + the auditor's claim strings — if the auditor mis-states a value the writer faithfully inserts it, with no ground truth to check against. (b) `signals_failed` is set on `AnalyzedContext` but never reaches `PipelineResult`/calibration records, so "extractor crashed" is indistinguishable from "no secondary signals". (c) The regex hallucination guard runs only on the report path; CHANGES/RECAP never get it despite it being pure regex. (d) `_TRADITIONAL_PATTERN` flags bare `IP`, which appears legitimately in workload lines.

- [ ] **Step 1: Write failing tests:** (a) `build_fact_revision_message(ground_truth, capsule, flags)` returns a UserPrompt list whose first element contains the ground truth and a `CachePoint()` separator (mirror `build_revision_message` in anchor.py) and whose instruction still says correct ONLY the flagged errors against the ground truth. (b) `flag_summary` includes `"signals_failed": False` and a `PipelineResult(signals_failed=True)` round-trips it. (c) recap/changes CLI paths invoke `check_hallucinated_metrics` (test at whatever seam `tests/test_cli.py` already stubs — follow the existing report-path test's pattern). (d) `check_hallucinated_metrics("went 5.2 IP over 89 pitches")` does NOT flag `IP` (adjust pattern: drop bare `IP` from `_TRADITIONAL_PATTERN` or require it not preceded by a decimal-numbered workload figure — read the pattern and the existing tests first and keep the rest of the pattern's behavior).
- [ ] **Step 2: Implement:**
  - `build_fact_revision_message(ground_truth: str, capsule: str, flags: list[AuditFlag]) -> UserPrompt` returning `[f"## Ground Truth\n{ground_truth}", CachePoint(), f"## Your Capsule\n{capsule}\n\n## Factual Errors Found\n{formatted}\n\n" + instruction]`, instruction extended with `Use the Ground Truth section for the correct values; if a listed fix contradicts the ground truth, follow the ground truth.` Update the caller in `run_capsule_audit` to pass its `ground_truth` argument.
  - Add `signals_failed: bool = False` to `PipelineResult`; set it from `analyzed.signals_failed` in `_run_pipeline` and `render_recap`; add to `flag_summary`.
  - In cli.py, run the `check_hallucinated_metrics` block for all narration modes, not only report (keep output formatting identical).
  - `_TRADITIONAL_PATTERN`: apply the minimal change that stops flagging workload `IP` while keeping other traditional-stat detection intact.
- [ ] **Step 3: Run `tests/test_pipeline.py tests/test_hallucination_guard.py tests/test_cli.py tests/test_morning.py -q` — pass.**
- [ ] **Step 4: Commit** `feat(pipeline,cli): fact revisions carry ground truth; propagate signals_failed; hallucination guard on every mode; IP false-positive fix`

---

**Deliberately NOT fixed (rationale, for the final reviewer):**
- `deepseek/deepseek-v4-pro` PRICING row: no authoritative price in-repo; `test_costs.py:40` documents the "n/a" rendering as intended.
- `gemini-3.5-flash` $1.50/$9.00 rate re-verification: needs an external source; flagged to the user instead.
- Report-path UsageTracker for anchor/fact stages: `_run_pipeline` has no tracker at all; adding one is a feature, out of audit scope.
- pfx deltas for secondary pitches in the arsenal table: engine change; Task 2's prompt reword removes the unexecutable instruction instead.
