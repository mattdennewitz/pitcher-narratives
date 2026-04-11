---
quick_id: 260411-hxm
type: quick
mode: docs
completed_at: "2026-04-11"
files_modified:
  - README.md
  - METHODOLOGY.md
commits:
  - d5b8784
  - 1e0c76b
---

# Quick 260411-hxm — Rewrite README.md and METHODOLOGY.md

Full-overwrite rewrite of both documentation files to match the current
codebase (commit `174cf44`). Neither file's existing content was used
as a template; both were rebuilt from the plan's REFERENCE document
plus direct reads of the relevant source files.

## Files touched

| File | Lines before | Lines after | Commit |
|---|---|---|---|
| `README.md` | 248 | 231 | `d5b8784` |
| `METHODOLOGY.md` | 527 | 527 | `1e0c76b` |

(METHODOLOGY.md's line count is a coincidence — the rewrite replaced
all 519 non-whitespace lines in a single pass, so `git show --stat`
reports `519 insertions, 519 deletions`.)

## What changed

The existing docs were carrying forward multiple stale claims from an
earlier single-agent implementation that no longer exists in the tree.
Both rewrites eliminate these stale terms and replace them with facts
verified against the current source files:

- `README.md` now documents the three installed CLI entry points
  (`pitcher-narratives`, `pitcher-scout`, `pitcher-ask`) with flag
  tables that match the real `argparse` definitions in `cli.py`,
  `scout_cli.py`, and `ask_cli.py`. It names the six stdout sections
  of `pitcher-narratives` in the order they are printed, references
  the five-phase pipeline (`1` / `1.5` / `1.75` / `2` / `2.5`), lists
  the actual Makefile targets (`run`, `scout`, `curate`), and calls
  out that `pitcher-ask` defaults to `gemini` — a fact the old README
  got wrong.
- `METHODOLOGY.md` now walks all five pipeline phases in detail, lists
  all five anchor warning categories as defined in
  `anchor.WarningCategory` (`MISSED_SIGNAL`, `UNDERWEIGHTED`,
  `UNSUPPORTED`, `DIRECTION_ERROR`, `OVERSTATED`), documents all ten
  scout signals with `hard_hit_spike` explicitly flagged as a stub
  that is not yet wired into the scanner (source-verified at
  `scout.py:37`), enumerates both primary and all six secondary
  `KeySignals` fields from `signals.py`, names exactly the two Q&A
  analyst tools from `analyst.py:464` (`get_pitcher_summary`,
  `get_pitch_detail`), states that `to_prompt()` renders up to 15
  sections (not 12), documents the model tier table and provider
  quirks from `config.py`, and includes an ASCII end-to-end pipeline
  diagram.

All of the plan's anti-regression greps and per-task verification
blocks pass on both files, plus the combined plan-level sanity check.
During verification one BSD-grep quirk was caught and corrected
inline: the `hard_hit_spike` table row originally had an em-dash and
the word "not" between the signal name and "stub", and BSD grep's
`[^\n]` bracket expression is byte-based (not character-based) so
the plan's stub-detection grep was not matching. Moving `(stub)`
adjacent to the signal name resolved the gate.

## Self-Check: PASSED

- `README.md` — FOUND
- `METHODOLOGY.md` — FOUND
- `.planning/quick/260411-hxm-rewrite-readme-and-methodology-to-match-/260411-hxm-SUMMARY.md` — FOUND
- commit `d5b8784` (README rewrite) — FOUND in git history
- commit `1e0c76b` (METHODOLOGY rewrite) — FOUND in git history
