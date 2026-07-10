# Retire Within-Game (Game-Shape) Detector — Progress Ledger

Plan: docs/superpowers/plans/2026-07-09-retire-within-game-detector.md
Spec: docs/superpowers/specs/2026-07-09-retire-within-game-detector-design.md
Worktree: .claude/worktrees/retire-within-game (branch refactor/retire-within-game-detector)
Base: 0740cfc (retire design commit) → plan commit 67af36f
Why isolated: the concurrent Pitch-Grade QA session has uncommitted work in the
feat/pitch-grade-qa worktree; this removal is independent (design §7) so it runs
on its own branch off 0740cfc to avoid entangling the two features.

Test cmd: PITCHER_NARRATIVES_DATA_DIR=/Users/matt/src/pitcher-narratives uv run pytest

## Known pre-existing baseline failures (NOT regressions)
CONFIRMED baseline (2026-07-09, on 0740cfc): **821 passed, 2 failed** in ~19 min:
- test_context.py::test_to_prompt_token_budget (golden/token drift)
- test_frame_delta.py::test_changes_trend_comparison_golden (golden drift)
(The 3rd documented flake, test_assemble_multi_frame_primary_matches_single, PASSED this run — order-dependent; may appear/disappear.)
"No new failures" means this 2-failure set is unchanged (a reappearing flake is not a regression).
NOTE: full suite ~19 min — implementers use targeted test files during iteration, full suite once at task end.

## Tasks
- [x] Task 1: Cut the game-shape specialist (spine 5 → 4) — complete (commit de8bb4a, review clean: spec ✅, quality Approved). Suite 799 passed / 2 baseline. Implementer also (correctly, in-scope) fixed test_cli.py + test_fact_parity.py construction sites and deleted TestGameShapeSpecialistReceivesYoyData (tests-for-deleted-code).
- [ ] Task 2: Delete the TTO engine, deviation gate, and context/prompt wiring
- [ ] Task 3: Grep gate + full-suite + end-to-end verification

## Notes / Minor findings (for final whole-branch review)
Task 1 (2 Minor, none blocking):
- pipeline.py data-auditor prompt: "e.g. trends or game-shape data" → "e.g. trends data" — correct bonus cleanup, not itemized in brief. Harmless.
- Implementer report notes Edit/Write tool intermittently false-errored "file not read yet"; edits done via py_compile-verified scripts. No code artifacts; process note only.
