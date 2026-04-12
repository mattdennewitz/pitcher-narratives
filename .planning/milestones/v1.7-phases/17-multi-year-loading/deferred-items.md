# Deferred Items - Phase 17

## Pre-existing Test Failures (Not Phase 17 Scope)

1. **test_fastball_velocity_delta** (tests/test_engine.py): Cold-start detection triggers for TEST_PITCHER (592155) because Phase 16 game_type filtering reduced the pitcher's data to a single regular-season appearance, which fits entirely within the 30-day window. The test expects directional vocabulary ("Up"/"Down"/"Steady") but gets cold-start string. This is a Phase 16 regression, not caused by Phase 17 changes.

2. **Missing RV_df.csv** (aggs/RV_df.csv): Multiple test modules (test_analyst.py, test_ask_cli.py, test_context.py, test_pipeline.py, test_report.py) fail because `RV_df.csv` does not exist in the data directory. This is a pre-existing data availability issue unrelated to Phase 17 changes.
