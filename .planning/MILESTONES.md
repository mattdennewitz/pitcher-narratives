# Milestones

## v1.9 Pipeline Consolidation (Shipped: 2026-04-10)

**Phases completed:** 2 phases, 3 plans, 6 tasks

**Key accomplishments:**

- Hallucination guard relocated to pipeline.py, both CLIs rewritten to use pipeline path exclusively with --pipeline flag removed
- Old single-agent report.py and its tests deleted, pipeline.py confirmed as sole reporting path with all imports clean
- Post-removal verification: all import chains intact, CLI features confirmed through pipeline path, stale report.py docstring references cleaned

---

## v1.8 Cross-Season Trend Analysis (Shipped: 2026-04-08)

**Phases completed:** 4 phases, 5 plans, 11 tasks

**Key accomplishments:**

- Prior-season baseline fields on PitcherData via N-1 filtering of existing multi-season baseline DataFrames
- Working compute_cross_season_summary() with _per_season_velo helper producing YoY deltas for velocity, P+, S+, L+ using existing qualitative delta-string functions
- YoY per-pitch-type delta engine identifying added/dropped/continued pitches with qualitative usage, P+/S+/L+, and velocity delta strings
- Typed cross-season fields on PitcherContext with _render_yoy_section() rendering velocity/P+/S+/L+ deltas and arsenal changes for multi-season pitchers
- Fixed specialist prompt builders to use correct ArsenalTrends attribute names (added, dropped, continued) and removed dead pfx_x_delta/pfx_z_delta code

---

## v1.7 Multi-Year Data & Game Type Filtering (Shipped: 2026-04-03)

**Phases completed:** 10 phases, 16 plans, 24 tasks

**Key accomplishments:**

- Polars data pipeline loading Statcast parquet + 8 Pitching+ CSVs with SP/RP classification, n_pitches-weighted baselines, and configurable lookback window filtering
- argparse CLI wiring with -p/-w flags, data pipeline connection, clean exit codes, and 10 unit+integration tests
- Fastball quality engine with velocity/P+/movement delta strings, velocity arc analysis, cold start detection, and small sample flagging using polars computation on PitcherData
- Per-pitch-type arsenal breakdown with usage rate/P+ deltas, platoon mix shift analysis with missing combo handling, and first-pitch weaponry distribution using polars computation on PitcherData
- Per-pitch-type CSW%, zone/chase rates, xWhiff/xSwing, xRV100 league percentile, plus rest-day/IP/consecutive-day workload tracking via Statcast event counting
- PitcherContext Pydantic model assembling all engine outputs with to_prompt() markdown rendering at ~544 tokens (well under 2,000 budget)
- Pydantic-ai Agent with claude-sonnet-4-6, scout-voice system prompt, role-conditional SP/RP guidance, and streaming output via run_stream_sync
- Full CLI pipeline wired: data -> context -> streaming report via Claude, with UserError catch for missing API key and PITCHER_NARRATIVES_TEST_MODEL env var for API-free integration testing
- AnchorWarning/AnchorResult Pydantic models with structured anchor agent output_type, revision_count metadata, and typed CLI warning formatting
- Pure function _build_revision_message() assembling fixed-size revision prompt from synthesis, capsule, and typed anchor warnings with CachePoint caching
- Editor-anchor for/else revision loop wired into generate_report_streaming() with MAX_REVISIONS=2, silent run_sync revisions, and downstream capsule handoff verified by Agent.run_sync patch test
- Three-branch _print_revision_status helper replacing unconditional anchor block with clean/converged/exhausted stderr output
- Game type filtering at load time (R/F/D/L/W allowlist) and year-parameterized path generation via _YEARS constant
- Multi-year parquet/CSV loading across _YEARS=[2025,2026] with missing-file graceful skip and per-season baseline computation via pitcher+season grouping
- Two new league-wide data loaders (load_all_statcast, load_full_agg) for consumer module refactoring
- Eliminated all direct CSV/parquet reads from engine.py, resolver.py, and scout.py -- all data access now routes through data.py functions with game-type filtering and multi-year support

---

## v1.6 Multi-Agent Pipeline (Shipped: 2026-04-03)

**Phases completed:** 1 phase (prototyped), 23 commits, 8 architecture refactors

**Key accomplishments:**

- Multi-agent specialist pipeline: 5 parallel micro-agents (stuff, location, run value, trends, game shape) each producing focused analysis with league baselines injected for grounding
- Per-specialist audit loop: independent data auditor verifies each specialist's output against raw data before the writer sees it
- Anti-hallucination guardrails: NORMAL/OUTLIER tags on every metric, directional consistency enforcement, temperature splitting (specialists=0.3, writer=0.7, auditor=0.1)
- Architecture cleanup (PLUS-1 through PLUS-15): extracted config.py, anchor.py; promoted private APIs to public; consolidated duplicated baseline logic; eliminated 20+ encapsulation violations
- Pipeline Q&A integration: specialist pipeline available via `pitcher-ask --pipeline` with audit flags and stuff summary in output

---

## v1.4 Interactive Pitcher Q&A (Shipped: 2026-03-30)

**Phases completed:** 10 phases, 15 plans, 21 tasks

**Key accomplishments:**

- Polars data pipeline loading Statcast parquet + 8 Pitching+ CSVs with SP/RP classification, n_pitches-weighted baselines, and configurable lookback window filtering
- argparse CLI wiring with -p/-w flags, data pipeline connection, clean exit codes, and 10 unit+integration tests
- Fastball quality engine with velocity/P+/movement delta strings, velocity arc analysis, cold start detection, and small sample flagging using polars computation on PitcherData
- Per-pitch-type arsenal breakdown with usage rate/P+ deltas, platoon mix shift analysis with missing combo handling, and first-pitch weaponry distribution using polars computation on PitcherData
- Per-pitch-type CSW%, zone/chase rates, xWhiff/xSwing, xRV100 league percentile, plus rest-day/IP/consecutive-day workload tracking via Statcast event counting
- PitcherContext Pydantic model assembling all engine outputs with to_prompt() markdown rendering at ~544 tokens (well under 2,000 budget)
- Pydantic-ai Agent with claude-sonnet-4-6, scout-voice system prompt, role-conditional SP/RP guidance, and streaming output via run_stream_sync
- Full CLI pipeline wired: data -> context -> streaming report via Claude, with UserError catch for missing API key and PITCHER_NARRATIVES_TEST_MODEL env var for API-free integration testing
- AnchorWarning/AnchorResult Pydantic models with structured anchor agent output_type, revision_count metadata, and typed CLI warning formatting
- Pure function _build_revision_message() assembling fixed-size revision prompt from synthesis, capsule, and typed anchor warnings with CachePoint caching
- Editor-anchor for/else revision loop wired into generate_report_streaming() with MAX_REVISIONS=2, silent run_sync revisions, and downstream capsule handoff verified by Agent.run_sync patch test
- Three-branch _print_revision_status helper replacing unconditional anchor block with clean/converged/exhausted stderr output
- Fuzzy pitcher name resolution with rapidfuzz WRatio scorer, dual-index lookup table, and 5-tier pipeline supporting exact, last-name, fuzzy, and disambiguation matching
- Tool-calling pydantic-ai agent with get_pitcher_summary and get_pitch_detail tools, static PITCH_TYPE_MAP with 12 Statcast codes + 26 synonyms, and streaming output via run_stream_sync
- pitcher-ask CLI entry point composing name resolver and analyst agent into a natural-language Q&A command with capitalization-aware name extraction

---

## v1.3 Editor-Anchor Reflection Loop (Shipped: 2026-03-28)

**Phases completed:** 7 phases, 12 plans, 16 tasks

**Key accomplishments:**

- Polars data pipeline loading Statcast parquet + 8 Pitching+ CSVs with SP/RP classification, n_pitches-weighted baselines, and configurable lookback window filtering
- argparse CLI wiring with -p/-w flags, data pipeline connection, clean exit codes, and 10 unit+integration tests
- Fastball quality engine with velocity/P+/movement delta strings, velocity arc analysis, cold start detection, and small sample flagging using polars computation on PitcherData
- Per-pitch-type arsenal breakdown with usage rate/P+ deltas, platoon mix shift analysis with missing combo handling, and first-pitch weaponry distribution using polars computation on PitcherData
- Per-pitch-type CSW%, zone/chase rates, xWhiff/xSwing, xRV100 league percentile, plus rest-day/IP/consecutive-day workload tracking via Statcast event counting
- PitcherContext Pydantic model assembling all engine outputs with to_prompt() markdown rendering at ~544 tokens (well under 2,000 budget)
- Pydantic-ai Agent with claude-sonnet-4-6, scout-voice system prompt, role-conditional SP/RP guidance, and streaming output via run_stream_sync
- Full CLI pipeline wired: data -> context -> streaming report via Claude, with UserError catch for missing API key and PITCHER_NARRATIVES_TEST_MODEL env var for API-free integration testing
- AnchorWarning/AnchorResult Pydantic models with structured anchor agent output_type, revision_count metadata, and typed CLI warning formatting
- Pure function _build_revision_message() assembling fixed-size revision prompt from synthesis, capsule, and typed anchor warnings with CachePoint caching
- Editor-anchor for/else revision loop wired into generate_report_streaming() with MAX_REVISIONS=2, silent run_sync revisions, and downstream capsule handoff verified by Agent.run_sync patch test
- Three-branch _print_revision_status helper replacing unconditional anchor block with clean/converged/exhausted stderr output

---

## v1.0 MVP (Shipped: 2026-03-26)

**Phases completed:** 4 phases, 8 plans, 9 tasks

**Key accomplishments:**

- Polars data pipeline loading Statcast parquet + 8 Pitching+ CSVs with SP/RP classification, n_pitches-weighted baselines, and configurable lookback window filtering
- argparse CLI wiring with -p/-w flags, data pipeline connection, clean exit codes, and 10 unit+integration tests
- Fastball quality engine with velocity/P+/movement delta strings, velocity arc analysis, cold start detection, and small sample flagging using polars computation on PitcherData
- Per-pitch-type arsenal breakdown with usage rate/P+ deltas, platoon mix shift analysis with missing combo handling, and first-pitch weaponry distribution using polars computation on PitcherData
- Per-pitch-type CSW%, zone/chase rates, xWhiff/xSwing, xRV100 league percentile, plus rest-day/IP/consecutive-day workload tracking via Statcast event counting
- PitcherContext Pydantic model assembling all engine outputs with to_prompt() markdown rendering at ~544 tokens (well under 2,000 budget)
- Pydantic-ai Agent with claude-sonnet-4-6, scout-voice system prompt, role-conditional SP/RP guidance, and streaming output via run_stream_sync
- Full CLI pipeline wired: data -> context -> streaming report via Claude, with UserError catch for missing API key and PITCHER_NARRATIVES_TEST_MODEL env var for API-free integration testing

---
