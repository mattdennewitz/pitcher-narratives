---
phase: quick
plan: 260326-t0k
subsystem: cli
tags: [cli, verbose, argparse]
key-files:
  modified:
    - main.py
    - tests/test_cli.py
duration: 1min
completed: 2026-03-27
---

# Quick Task 260326-t0k: Add -v verbose switch

Added `-v`/`--verbose` CLI flag that prints pitcher name, game dates, pitch counts, and roles to stderr before the LLM pipeline runs.

## What shipped
- `_print_verbose_summary()` in main.py prints a formatted table to stderr
- Output includes pitcher name, ID, handedness, per-game date/pitches/role, and totals
- 4 new tests (2 unit for flag parsing, 2 integration for output verification)
- 151/151 tests pass
