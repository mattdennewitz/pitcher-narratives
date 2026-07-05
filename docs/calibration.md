# Depth Calibration Runbook (Phase 11)

The per-mode revision-depth caps in `personas.py` are **provisional** — set by
judgment, not measurement. This runbook explains how to collect real
revision/flag data and read it, so the caps can be set from evidence.

## What is calibrated

| Constant | Location | Current (provisional) |
| --- | --- | --- |
| RECAP anchor / fact depth | `personas.py` `RECAP` `ValidationPolicy(anchor_depth=1, fact_depth=2)` | 1 / 2 |
| REPORT / CHANGES anchor / fact depth | `config.py` `MAX_REVISIONS` / `MAX_FACT_REVISIONS` via `personas.py` REPORT & CHANGES | 5 / 2 |
| REPORT span (recent appearances) | `temporal.py` `_DEFAULT_RECENT_APPEARANCES` | 10 — **already measured 2026-07-01**, not re-derived here |

This phase changes none of these numbers. It builds the plumbing that produces
the evidence for a later, separate change.

## Collecting data (instrumented runs)

Two sources feed the aggregator; both persist a `flag_record` per
`(pitcher, mode)` run (`pitcher_narratives.pipeline.flag_record`):

1. **Morning runs (RECAP, organic).** Every `pitcher-narratives morning`
   writes real per-pick records to `<out>/<game_date>/validation.json`.
   Just accumulate morning runs over days.
2. **Report runs (any mode, on demand).** Pass `--metrics-out PATH` to append
   JSONL records. Sweep pitchers and modes to build a sample, e.g.:

   ```bash
   for pid in 592155 693433 605483; do
     pitcher-narratives report -p "$pid" --mode report,recap,changes \
       --metrics-out var/calibration/metrics.jsonl
   done
   ```

## Reading the data

```bash
python -m pitcher_narratives.calibration var/calibration/metrics.jsonl <out>/2026-07-*/
```

Paths may be `*.jsonl` files, `validation.json` files, or directories (walked
for both). The output is a per-mode table:

- `rev_mean` / `rev_med` — anchor-revision passes per run.
- `caps_rev` — fraction of runs where the capsule fact loop ran a remediation
  pass.
- `anchor_hit_cap` — fraction of runs where `revision_count` reached the mode's
  anchor cap. **This is the key signal.**
- `fact_hit_cap` — fraction of runs that ran a fact-remediation pass under a
  non-zero fact cap.

## Interpreting → setting the constants

- **`anchor_hit_cap` ≈ 0 for a mode** → the cap is never binding; it can be
  lowered (cheaper runs) with no loss. E.g. if RECAP's `anchor_hit_cap` is 0
  across a healthy sample, `anchor_depth=1` is already slack.
- **`anchor_hit_cap` high (e.g. > 0.3)** → runs are hitting the ceiling and may
  ship under-revised; consider raising the cap.
- **`caps_rev` / `fact_hit_cap` high** → the fact loop is doing real work; keep
  `fact_depth` where it is or raise it.

Edit the constant in `personas.py` (RECAP/CHANGES `ValidationPolicy`) or
`config.py` (`MAX_REVISIONS` / `MAX_FACT_REVISIONS` for REPORT), then
regenerate any affected golden fixtures and re-run the suite. That numeric
change is deliberately **out of scope for Phase 11** — it belongs to a
follow-up once a representative sample has accrued.
