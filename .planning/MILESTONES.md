# Milestones

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
