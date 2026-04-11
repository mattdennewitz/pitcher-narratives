---
quick_id: 260411-hxm
type: quick
mode: docs
autonomous: true
files_modified:
  - README.md
  - METHODOLOGY.md
---

# Quick: Rewrite README.md and METHODOLOGY.md from scratch

## Accuracy Bar (read this before touching either file)

The two existing docs are stale and MUST NOT be used as a template. Both
will be fully overwritten via the `Write` tool. The rewrite is graded
against `260411-hxm-REFERENCE.md` and the source files listed under each
task — the executor must NOT introduce any of the following stale claims:

- `report.py` (file does not exist)
- `--pipeline` CLI flag (does not exist; there is one pipeline)
- "simple pipeline" / "four-phase pipeline" wording
- "Social Hook" output section (does not exist)
- "Fantasy Insights" output section (does not exist)
- "3 Axios-style bullets" wording
- "12-section context" (it's 15)
- "9 scout signals" (it's 10)
- "4 anchor warning categories" (it's 5)
- "pitcher-ask defaults to openai" (it defaults to **gemini**)

Source-verified facts as of commit 174cf44:

- Entry points: `pitcher-narratives` (cli.py:main), `pitcher-scout`
  (scout_cli.py:main), `pitcher-ask` (ask_cli.py:main).
- `pitcher-narratives` and `pitcher-scout` default `--provider` is
  `openai`. `pitcher-ask` defaults to `gemini`. Do not conflate.
- `pitcher-narratives` prints exactly six sections in this order:
  Scouting Report, Executive Summary, Stuff Analysis, Data Audit,
  Anchor Check, Hallucination Check (last only when not clean).
- Pipeline phases: 1 (5 specialists in parallel), 1.5 (per-specialist
  audit + revise), 1.75 (signal extractor — non-critical), 2 (writer
  + executive summary in parallel), 2.5 (anchor check + revision loop,
  `MAX_REVISIONS = 3`).
- The five specialists are `stuff` (Pro tier), `location`, `runvalue`,
  `trends`, `game_shape` (all Mini tier).
- Anchor warning categories (5): `MISSED_SIGNAL`, `UNDERWEIGHTED`,
  `UNSUPPORTED`, `DIRECTION_ERROR`, `OVERSTATED`.
- `KeySignals` model: 2 primary required fields (`top_improvement`,
  `top_concern`) and 6 optional secondary fields (`development_pitch`,
  `specialist_tension`, `arsenal_dependency`, `connected_changes`,
  `platoon_vulnerability`, `sample_size_caution`).
- `PitcherContext.to_prompt()` renders up to 15 sections (Title +
  Temporal + Executive Summary + Role + Primary Fastball + TTO +
  Arsenal + Execution + Model Internals + Release Point + Contact
  Quality + Platoon Shifts + First-Pitch + Recent Appearances + YoY).
  Empty sections are skipped. `attributions` is NOT in `to_prompt()` —
  it is consumed directly by the run-value specialist input builder.
- Scout has **10** signals in `_WEIGHTS`: `velo_delta`, `pplus_swing`,
  `splus_lplus_divergence`, `usage_shift`, `new_pitch`, `dropped_pitch`,
  `hard_hit_spike`, `walk_rate_pplus_contradiction`,
  `development_opportunity`, `workload_flag`. **Verified**:
  `hard_hit_spike` is defined in the weights table but no code path in
  `scout.py` emits a `Signal` with that name — it is a documented
  no-op stub. The rewrite must say so plainly (something like "listed
  in the weights table but not yet wired into the scanner").
- Q&A analyst exposes exactly **two** tools (verified at
  `analyst.py:464`): `get_pitcher_summary` and `get_pitch_detail`.
  There is also a separate `ask_question_pipeline` multi-agent path
  (`PipelineAnswer`) that reuses the specialist→audit→signal→answerer
  flow — METHODOLOGY may mention it but README does not need to.
- Makefile targets that still exist: `run`, `scout`, `curate`. No others.
- `pyproject.toml`: `requires-python = ">=3.14"`. Runtime deps:
  `logfire`, `nameparser`, `polars>=1.39.3`, `pydantic-ai>=1.72.0`,
  `pydantic-ai-slim[google]`, `python-dotenv`, `rapidfuzz`. Dev:
  `pre-commit`, `pytest`, `ruff`, `ty`.
- Provider models (`config.py`): openai → `openai:gpt-5.4` /
  `openai:gpt-5.4-mini`; claude → `anthropic:claude-sonnet-4-6` /
  `anthropic:claude-haiku-4-5`; gemini →
  `google-gla:gemini-3.1-pro-preview` /
  `google-gla:gemini-flash-latest`.
- Token budgets: SMALL=1024 (anchor / auditor / summary / signal
  extractor), MEDIUM=2048 (trends / game_shape specialists), LARGE=4096
  (writer + stuff/location/runvalue specialists).
- Thinking levels: `minimal`, `low`, `medium`, `high`, `xhigh`. Per-role
  ceilings via `cap_thinking` (writer is uncapped at user level).
- Provider quirks: Gemini always uses `GoogleModelSettings` with
  thinking_level high|low; Claude disables thinking when `mini=True`
  or `max_tokens <= TOKEN_BUDGET_MEDIUM` and forces `temperature=1`
  when thinking is on; OpenAI omits `reasoning_effort` for mini models
  and omits `max_tokens` when budget `<= TOKEN_BUDGET_MEDIUM`.

Style rules for both files:

- No emojis. No marketing fluff. No unicode box-drawing in prose.
- No "we built this" voice. Document what the code does, not its history.
- Code blocks for shell commands and CLI invocations only; no fake JSON.
- Both files are full overwrites via the `Write` tool, NOT `Edit`. Do
  not read the existing files first to "preserve structure" — the
  whole point is that their structure is wrong.

---

<context>
@.planning/quick/260411-hxm-rewrite-readme-and-methodology-to-match-/260411-hxm-REFERENCE.md
@pyproject.toml
@src/pitcher_narratives/cli.py
@src/pitcher_narratives/scout_cli.py
@src/pitcher_narratives/ask_cli.py
@src/pitcher_narratives/config.py
@src/pitcher_narratives/anchor.py
@src/pitcher_narratives/signals.py
@src/pitcher_narratives/scout.py
@src/pitcher_narratives/analyst.py
@src/pitcher_narratives/context.py
@src/pitcher_narratives/pipeline.py
@Makefile
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite README.md from scratch</name>
  <files>README.md</files>
  <action>
Overwrite `README.md` with a short, practical README using the `Write`
tool (NOT `Edit`). Do NOT read the existing README first — its content
is stale and would contaminate the rewrite. Use the REFERENCE file and
the source files listed in `<context>` as the only inputs.

Required structure (in this order, no extra sections):

1. **Title and one-paragraph elevator pitch.** "Pitcher Narratives is a
   CLI that turns Statcast and Pitching+ data into LLM-written scouting
   reports for MLB pitchers." Mention that the report is grounded in
   pre-computed deltas/baselines so the LLM focuses on insight, not
   arithmetic. No marketing language, no emojis.

2. **Requirements.** Python 3.14+, `uv`, an API key for at least one
   of `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (loaded
   via `python-dotenv` from a `.env` file). Static parquet + CSVs in
   the project root and `aggs/` (point at the data layout — do not
   list every CSV; that's METHODOLOGY's job).

3. **Install / quick start.** `uv sync`, then `uv run pitcher-narratives
   -p <pitcher_id> -w 30`. Show a minimal real-looking command, e.g.
   `uv run pitcher-narratives -p 657277 -w 5`. Mention the `make run`
   shortcut and that it's defined in the Makefile.

4. **The three CLIs.** One short subsection each. For each CLI, show
   the actual flag table (verify against the matching `parse_args` in
   source — every row must match the real argparse definition) and one
   example invocation. Required content per CLI:

   - **`pitcher-narratives`** — flags `-p/--pitcher` (int, required),
     `-w/--window` (int, default 30), `-v/--verbose` (flag),
     `--print-prompts` (flag), `--provider` (`openai`|`claude`|`gemini`,
     default `openai`), `--thinking`
     (`minimal`|`low`|`medium`|`high`|`xhigh`, default `medium`).
     Mention the six stdout sections in order: Scouting Report,
     Executive Summary, Stuff Analysis, Data Audit, Anchor Check,
     Hallucination Check (last is conditional). Mention the
     `data-{pitcher}-{provider}.md` side-effect file and that
     `--print-prompts` dumps the rendered prompts to stderr and exits.

   - **`pitcher-scout`** — flags `-w/--window` (default 1),
     `-n/--top` (default 20), `--min-pitches` (default 20),
     `--min-score` (default 0.0), `-v/--verbose`, `--curate`,
     `--provider` (default `openai`). One sentence: scans recent
     appearances, scores them with the 10-signal heuristic, prints a
     ranked table; `--curate` sends the top results to an LLM via
     `curator.py`.

   - **`pitcher-ask`** — positional `question`, `-w/--window` (default
     30), `--provider` (default **`gemini`** — call this out
     explicitly so nobody assumes it's openai), `--thinking` (default
     `medium`). One sentence: natural-language Q&A grounded in the
     same context, served by a tool-calling agent that exposes
     `get_pitcher_summary` and `get_pitch_detail`.

5. **Pipeline at a glance.** Three to five sentences max — name the
   five phases (1, 1.5, 1.75, 2, 2.5) and what each does. Point at
   METHODOLOGY for the deep version. Do NOT use the words "simple
   pipeline" or "four-phase pipeline." Do NOT mention `report.py`.

6. **Project layout.** A small file tree showing the actual current
   layout (verify against the `src/pitcher_narratives/` listing in
   the REFERENCE — must include `analyst.py`, `anchor.py`, `ask_cli.py`,
   `cli.py`, `config.py`, `context.py`, `curator.py`, `data.py`,
   `engine.py`, `pipeline.py`, `resolver.py`, `scout_cli.py`,
   `scout.py`, `signals.py`). Do NOT list `report.py`. Briefly note
   `aggs/` for the Pitching+ CSVs and the parquet at the project root
   for Statcast data.

7. **Dev commands.** `uv sync`, `uv run pytest`, `uv run ruff check`,
   `uv run ty check src`, plus the three `make` targets that actually
   exist: `make run`, `make scout`, `make curate`. Do not list make
   targets that aren't in the Makefile.

8. **Link to METHODOLOGY.md** for the deep dive.

Anti-regression — these strings must NOT appear in the rewrite:
`report.py`, `--pipeline`, `simple pipeline`, `four-phase`, `Social
Hook`, `Fantasy Insights`, `Axios`, `12-section`, `12 sections`,
`9 signals`, `nine signals`, `4 anchor`, `four anchor`. Also: do NOT
write that `pitcher-ask` defaults to openai — it defaults to gemini.

Length target: ~150–220 lines of markdown. Practical and skimmable.
  </action>
  <verify>
    <automated>
# 1. README must exist and be a fresh write (no stale terms).
test -f README.md
! grep -niE 'report\.py|--pipeline|simple pipeline|four-phase|Social Hook|Fantasy Insights|Axios|12-section|12 sections|nine signals|9 signals|four anchor|4 anchor warning' README.md
# 2. pitcher-ask must be documented as defaulting to gemini, not openai.
grep -nE 'pitcher-ask.*gemini|--provider.*gemini.*pitcher-ask|defaults to .?gemini' README.md
! grep -nE 'pitcher-ask[^\n]{0,80}defaults? to .?openai' README.md
# 3. The six output sections must be named in the README.
grep -q 'Scouting Report' README.md && grep -q 'Executive Summary' README.md && grep -q 'Stuff Analysis' README.md && grep -q 'Data Audit' README.md && grep -q 'Anchor Check' README.md && grep -q 'Hallucination Check' README.md
# 4. The three CLI entry points must all be present.
grep -q 'pitcher-narratives' README.md && grep -q 'pitcher-scout' README.md && grep -q 'pitcher-ask' README.md
# 5. Make targets that exist must be referenced; report.py file must not.
grep -qE 'make (run|scout|curate)' README.md
! grep -q 'report\.py' README.md
# 6. Five pipeline phases must be referenced (allow either "1.5" or "phase 1.5" wording).
grep -q '1\.5' README.md && grep -q '1\.75' README.md && grep -q '2\.5' README.md
    </automated>
  </verify>
  <done>
README.md exists, is a complete overwrite (not a patch of the old file),
contains the three CLI flag tables matching the real argparse
definitions in source, names the six output sections in order, calls
out that `pitcher-ask` defaults to gemini, references the actual
Makefile targets, and contains none of the listed stale strings.
  </done>
</task>

<task type="auto">
  <name>Task 2: Rewrite METHODOLOGY.md from scratch</name>
  <files>METHODOLOGY.md</files>
  <action>
Overwrite `METHODOLOGY.md` with a deep technical document using the
`Write` tool (NOT `Edit`). Do NOT read the existing METHODOLOGY.md
first. Use the REFERENCE file and the source files listed in
`<context>` as the only inputs.

Required sections (in this order):

1. **Overview.** Two paragraphs. What the system does, what the input
   is (static parquet + Pitching+ CSVs in `aggs/`), what the output is
   (scout-voice scouting capsule + structured side artifacts), and
   the design principle: pre-compute deltas and outlier tags so the
   LLM focuses on insight, not arithmetic.

2. **Data sources.** List the parquet (Statcast pitch-level) at the
   project root and the eight 2026 Pitching+ CSVs in `aggs/`
   (`2026-pitcher.csv`, `2026-pitcher_type.csv`,
   `2026-pitcher_appearance.csv`, `2026-pitcher_type_appearance.csv`,
   `2026-pitcher_type_platoon.csv`,
   `2026-pitcher_type_platoon_appearance.csv`, `2026-all_pitches.csv`,
   `2026-team.csv`), plus the 2025 analogues for year-over-year. Note
   the two key behavioral choices from `data.py`: (a) the lookback
   window is computed relative to the most recent date in the dataset
   (not wall clock — keeps behavior stable against static files), and
   (b) starter vs reliever is classified per-appearance from the first
   inning, so openers end up labeled SP. Note that season baselines
   across game types are `n_pitches`-weighted, not simple means.

3. **Engine (`engine.py`).** One paragraph. Describes the role: it
   computes every metric, delta, baseline, and outlier flag the
   downstream stages consume. Include the delta vocabulary table from
   the REFERENCE (Velocity / P+/S+/L+ / Usage / Movement bands and
   "steady"/"up-down"/"sharply" cutoffs), the small-sample threshold
   (per-pitch-type analyses flag `small_sample: true` below 10
   pitches in the window), and the full-window-no-baseline fallback
   (`"Full season in window — no trend comparison."`).

4. **Context assembly (`context.py`).** Document `PitcherContext` and
   `to_prompt()`. Explicitly state that `to_prompt()` renders **up
   to 15 sections** (NOT 12), and list them in render order:
   1. Title — `# {pitcher_name} ({L/R}HP) -- Scouting Context`
   2. Temporal Context (analysis date, season phase, prior-year
      workload relevance level)
   3. Executive Summary (key changes from most recent appearance)
   4. Role (most recent SP/RP, appearance count, consecutive days)
   5. Primary Fastball (velo, P+/S+/L+ triad + deltas, movement
      deltas, within-game velocity arc; falls back to "No standard
      fastball identified")
   6. Times Through Order (skipped when no TTO data)
   7. Arsenal (top pitch types by usage, deltas, P+/S+/L+ vs season)
   8. Execution (CSW%, Zone%, Chase%, xWhiff, xSwing, xRV100 percentile)
   9. Model Internals: Location Impact (S-variant probabilities and
      P-vs-S deltas)
   10. Release Point (release x/z/extension vs the pitcher's own
       season baseline)
   11. Contact Quality (hard-hit rate window vs season + delta)
   12. Platoon Shifts (per-pitch-type usage and P+ by batter hand)
   13. First-Pitch Tendencies (top first-pitch types, recent vs
       season share)
   14. Recent Appearances (date, IP, pitch count, rest days)
   15. Year-over-Year (cross-season pitcher-level deltas + added/
       dropped pitches; skipped for single-season pitchers)

   State explicitly that `attributions` (the 13-outcome xRV100
   decomposition) is **NOT** rendered by `to_prompt()` — it is
   consumed directly by `_build_runvalue_input` in `pipeline.py`
   for the run-value specialist.

5. **Scout (`scout.py`).** Document the 10 signals, weights,
   thresholds, and intent. Use the REFERENCE table verbatim or rebuild
   it — but it MUST contain ten rows. List in this order to match
   `_WEIGHTS` priority (highest weight first): `new_pitch` (4.0),
   `development_opportunity` (3.5), `velo_delta` (3.0),
   `splus_lplus_divergence` (3.0), `dropped_pitch` (3.0),
   `pplus_swing` (2.5), `walk_rate_pplus_contradiction` (2.5),
   `usage_shift` (2.0), `hard_hit_spike` (1.5), `workload_flag` (1.0).

   IMPORTANT: For `hard_hit_spike`, state plainly that the entry exists
   in the `_WEIGHTS` table at `scout.py:37` but no code path in
   `scout.py` actually emits a `Signal` with that name — it is a
   documented stub awaiting implementation. Do not invent a threshold
   for it. (This was source-verified by grepping `scout.py`.)

6. **Curator (`curator.py`).** Two sentences. The `--curate` flag on
   `pitcher-scout` sends top scout results to an LLM (provider
   selected via `--provider`) for editorial selection of the most
   compelling 3–5 stories.

7. **Pipeline (`pipeline.py`).** This is the deep section. Walk
   through the five phases in order:

   - **Phase 1 — specialists in parallel.** Five specialist agents:
     `stuff` (Pro tier, temp 0.3, LARGE budget),
     `location` (Mini, 0.3, LARGE),
     `runvalue` (Mini, 0.3, LARGE),
     `trends` (Mini, 0.3, MEDIUM),
     `game_shape` (Mini, 0.3, MEDIUM). Each receives a bespoke input
     built by its `_build_*_input` helper, with every metric annotated
     with a delta from league average and an explicit `NORMAL`/
     `OUTLIER` z-score tag from `engine.outlier_tag`.

   - **Phase 1.5 — audit + revise.** `audit_and_revise_specialists`
     runs the auditor (Mini, temp 0.1, `retries=5`, SMALL budget) on
     each specialist's output in parallel. Flagged specialists are
     re-run with their original input plus the audit corrections.
     The writer never sees flawed prose. `AuditFlag` and `AuditResult`
     are defined in `pipeline.py`.

   - **Phase 1.75 — signal extractor.** A Mini-tier signal extractor
     agent (SMALL budget, `retries=3`) reads the clean specialist
     outputs and returns a `KeySignals` object from `signals.py`.
     Document the model's two primary required fields (`top_improvement`,
     `top_concern`) and the six optional secondary fields
     (`development_pitch`, `specialist_tension`, `arsenal_dependency`,
     `connected_changes`, `platoon_vulnerability`,
     `sample_size_caution`). State explicitly that this phase is
     non-critical: on any exception the pipeline continues with
     `key_signals=None` and the anchor check degrades gracefully.

   - **Phase 2 — writer + summary in parallel.** Writer (Pro tier,
     temp 0.7, LARGE budget) runs from `build_writer_input(ctx,
     specialists, key_signals)` and streams to stdout. Executive
     summary agent (Mini tier, temp 0.3, SMALL budget) runs
     concurrently from the same input. Summary failures are non-fatal
     (empty bullet list).

   - **Phase 2.5 — anchor check + revision loop.**
     `_run_anchor_revision_loop` drives the anchor agent (Mini, temp
     0.1, SMALL budget) via `anchor.ANCHOR_PROMPT`. The synthesis is
     `render_key_signals(key_signals) + specialist outputs`. When the
     anchor is not clean, the writer revises via
     `anchor.build_revision_message` — a fresh prompt with no history,
     a cache breakpoint after the synthesis, and an instruction to
     "fix only the listed warnings." Up to `MAX_REVISIONS` (3) passes,
     then a final anchor check captures any surviving warnings.

   List the **five** anchor warning categories with their exact meaning:
   `MISSED_SIGNAL`, `UNDERWEIGHTED`, `UNSUPPORTED`, `DIRECTION_ERROR`,
   `OVERSTATED`. Categories MUST be the literals from
   `anchor.WarningCategory`.

8. **Hallucination guard.** `check_hallucinated_metrics` in
   `pipeline.py` regex-scans the final narrative and returns a
   `HallucinationReport` with two fields: `unknown_metrics` (metric-like
   patterns — xMetric, Acronym%, P+/S+/L+ family — that are not in a
   known-safe set) and `outcome_stat_warnings` (traditional outcome
   stats the prompts warn against, like ERA, WHIP, W-L). The CLI emits
   the `# Hallucination Check` section only when the report is not
   clean.

9. **Caching and prompt cache breakpoints.** Document where
   `pydantic_ai.CachePoint` is used: in `anchor.build_anchor_message`
   and `anchor.build_revision_message`, between the synthesis and the
   capsule, so the synthesis half of the prompt is cacheable across
   the anchor check and each revision pass.

10. **Model table (from `config.py`).** Provider models for both
    tiers, plus the role → tier / temp / max_tokens / thinking-cap
    table from the REFERENCE (Stuff, Location/RunValue, Trends/Game
    Shape, Writer, Auditor, Anchor, Executive Summary, Signal
    Extractor). Then document provider quirks from
    `make_model_settings`:
    - **Gemini**: always `GoogleModelSettings` with
      `google_thinking_config={"thinking_level": "high" | "low"}`.
      CLI levels `high`/`xhigh` map to `"high"`, everything else maps
      to `"low"`.
    - **Claude**: thinking disabled when `mini=True` or
      `max_tokens <= TOKEN_BUDGET_MEDIUM`; temperature forced to `1`
      when thinking is on.
    - **OpenAI**: `reasoning_effort` disabled for mini-tier models;
      `max_tokens` omitted when budget `<= TOKEN_BUDGET_MEDIUM`
      (reasoning tokens count against the cap and small budgets choke
      the model).

11. **Q&A analyst (`analyst.py`).** Document the `pitcher-ask` flow.
    Pro tier, temp 0.3, default provider **gemini**. The agent is
    instructed via `ANALYST_INSTRUCTIONS` and exposes exactly **two**
    tools (verified at `analyst.py:464`):
    - `get_pitcher_summary(ctx)` — returns league baselines (per-pitch
      type, with stddev) plus the full `PitcherContext.to_prompt()`
      output.
    - `get_pitch_detail(ctx, pitch_type)` — returns focused arsenal,
      execution, platoon, intermediates, and 13-outcome attribution
      data for one specific pitch type. Accepts pitch type names or
      Statcast codes via the `PITCH_TYPE_MAP` synonym table.

    Mention `resolver.py` (uses `rapidfuzz` to fuzzy-match the pitcher
    name out of the question text). Optionally mention that
    `analyst.py` also defines `ask_question_pipeline` /
    `PipelineAnswer`, a multi-agent Q&A path that reuses the
    specialist→audit→signal flow before answering — but the CLI
    (`pitcher-ask`) currently calls `ask_question_streaming`, the
    single-agent tool-calling path.

12. **End-to-end diagram.** A simple ASCII pipeline diagram from
    `load_pitcher_data` → `assemble_pitcher_context` →
    Phase 1 (5 specialists) → Phase 1.5 (audit/revise) →
    Phase 1.75 (signal extractor) → Phase 2 (writer + summary) →
    Phase 2.5 (anchor + revisions) → hallucination guard → stdout.
    Keep it ASCII, no unicode box-drawing decoration.

Anti-regression — these strings must NOT appear in the rewrite:
`report.py`, `--pipeline`, `simple pipeline`, `four-phase`, `Social
Hook`, `Fantasy Insights`, `Axios`, `12-section`, `12 sections`,
`nine signals`, `9 signals`, `four anchor`, `4 anchor`. Also: anchor
categories MUST be exactly five and MUST include `UNDERWEIGHTED`. The
analyst tool list MUST be exactly two entries — do not invent
`get_arsenal`, `get_execution`, etc.

Length target: ~400–650 lines. Detailed but not padded.
  </action>
  <verify>
    <automated>
# 1. METHODOLOGY must exist and be a fresh write (no stale terms).
test -f METHODOLOGY.md
! grep -niE 'report\.py|--pipeline|simple pipeline|four-phase|Social Hook|Fantasy Insights|Axios|12-section|12 sections|nine signals|9 signals|four anchor|4 anchor warning' METHODOLOGY.md
# 2. All five anchor categories must appear (the literal token names).
grep -q 'MISSED_SIGNAL' METHODOLOGY.md
grep -q 'UNDERWEIGHTED' METHODOLOGY.md
grep -q 'UNSUPPORTED' METHODOLOGY.md
grep -q 'DIRECTION_ERROR' METHODOLOGY.md
grep -q 'OVERSTATED' METHODOLOGY.md
# 3. All five pipeline phases must be referenced.
grep -q 'Phase 1' METHODOLOGY.md && grep -q '1\.5' METHODOLOGY.md && grep -q '1\.75' METHODOLOGY.md && grep -q 'Phase 2' METHODOLOGY.md && grep -q '2\.5' METHODOLOGY.md
# 4. The five specialist names must appear.
grep -q 'stuff' METHODOLOGY.md && grep -q 'location' METHODOLOGY.md && grep -q 'runvalue\|run value\|run_value' METHODOLOGY.md && grep -q 'trends' METHODOLOGY.md && grep -q 'game.shape\|game_shape' METHODOLOGY.md
# 5. KeySignals: both primary fields named, plus all six secondary fields.
grep -q 'top_improvement' METHODOLOGY.md && grep -q 'top_concern' METHODOLOGY.md
grep -q 'development_pitch' METHODOLOGY.md && grep -q 'specialist_tension' METHODOLOGY.md && grep -q 'arsenal_dependency' METHODOLOGY.md && grep -q 'connected_changes' METHODOLOGY.md && grep -q 'platoon_vulnerability' METHODOLOGY.md && grep -q 'sample_size_caution' METHODOLOGY.md
# 6. Q&A analyst must list exactly two tools, no more, no less.
grep -q 'get_pitcher_summary' METHODOLOGY.md && grep -q 'get_pitch_detail' METHODOLOGY.md
! grep -qE 'get_arsenal|get_execution|get_platoon|get_release_point|get_contact_quality'  METHODOLOGY.md
# 7. Scout signal table must list all ten signal names from _WEIGHTS.
for sig in velo_delta pplus_swing splus_lplus_divergence usage_shift new_pitch dropped_pitch hard_hit_spike walk_rate_pplus_contradiction development_opportunity workload_flag; do
  grep -q "$sig" METHODOLOGY.md || { echo "MISSING SIGNAL: $sig" >&2; exit 1; }
done
# 8. hard_hit_spike must be flagged as a stub (any of: stub / not wired / no-op / not yet).
grep -niE 'hard_hit_spike[^\n]{0,200}(stub|not wired|no-op|not yet|placeholder)' METHODOLOGY.md
# 9. to_prompt section count: must say 15 (or "fifteen"), must NOT say 12.
grep -niE '(up to )?(15|fifteen) sections?' METHODOLOGY.md
! grep -qE '(up to )?(12|twelve) sections?' METHODOLOGY.md
# 10. pitcher-ask must be documented as gemini-default.
grep -nE 'pitcher-ask[^\n]{0,200}gemini' METHODOLOGY.md
# 11. report.py must not appear anywhere.
! grep -q 'report\.py' METHODOLOGY.md
    </automated>
  </verify>
  <done>
METHODOLOGY.md exists, is a complete overwrite (not a patch of the old
file), names all five anchor categories, walks all five pipeline
phases, lists all ten scout signals (with `hard_hit_spike` explicitly
marked as a stub that is not yet wired into the scanner), lists both
primary and all six secondary KeySignals fields, names exactly two
Q&A analyst tools, says `to_prompt()` renders up to 15 sections, says
`pitcher-ask` defaults to gemini, and contains none of the listed
stale strings.
  </done>
</task>

</tasks>

<verification>
After both tasks complete, run a single combined sanity check on both
files to confirm zero stale terminology slipped through and that the
defaults are correctly attributed:

```bash
# No stale strings in either file.
! grep -niE 'report\.py|--pipeline|simple pipeline|four-phase|Social Hook|Fantasy Insights|Axios|12-section|12 sections|nine signals|9 signals|four anchor|4 anchor warning' README.md METHODOLOGY.md

# pitcher-ask is correctly gemini-defaulted in both files.
grep -nE 'pitcher-ask[^\n]{0,200}gemini' README.md
grep -nE 'pitcher-ask[^\n]{0,200}gemini' METHODOLOGY.md

# Every CLI in pyproject.toml [project.scripts] is mentioned in README.
for cli in pitcher-narratives pitcher-scout pitcher-ask; do
  grep -q "$cli" README.md || { echo "README missing $cli" >&2; exit 1; }
done

# Both files build cleanly (no broken markdown link to a missing local file).
test -f README.md && test -f METHODOLOGY.md
```
</verification>

<success_criteria>
1. README.md and METHODOLOGY.md both exist and are full overwrites
   produced via the `Write` tool.
2. Neither file references `report.py`, `--pipeline`, "simple
   pipeline", "four-phase", "Social Hook", "Fantasy Insights",
   "Axios", "12-section", "9 signals", or "4 anchor warning categories".
3. README.md documents all three CLIs with flag tables that match the
   real `argparse` definitions in `cli.py`, `scout_cli.py`, and
   `ask_cli.py` — including `pitcher-ask`'s **gemini** default.
4. README.md names the six stdout sections of `pitcher-narratives` in
   order, references the five pipeline phases (1, 1.5, 1.75, 2, 2.5),
   lists the actual Makefile targets (`run`, `scout`, `curate`), and
   does not invent any others.
5. METHODOLOGY.md walks all five pipeline phases, lists all five
   anchor warning categories (including `UNDERWEIGHTED`), lists all
   ten scout signals (with `hard_hit_spike` explicitly noted as a
   stub that is not yet wired into the scanner), lists both primary
   and all six secondary `KeySignals` fields, names exactly the two
   Q&A analyst tools (`get_pitcher_summary`, `get_pitch_detail`), and
   states that `to_prompt()` renders up to 15 sections.
6. No emojis in either file.
7. No code changes anywhere outside README.md and METHODOLOGY.md.
</success_criteria>

<output>
Two files written:
- `/Users/matt/src/pitcher-narratives/README.md`
- `/Users/matt/src/pitcher-narratives/METHODOLOGY.md`

No other files modified.
</output>
