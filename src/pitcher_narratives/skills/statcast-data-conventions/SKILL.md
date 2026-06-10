---
name: statcast-data-conventions
description: Use when reading or computing from the Statcast parquet files or data.statcast in this repo — movement (pfx_x/pfx_z), arm_angle, release or effective speed, handedness pooling, league baselines, or writing tests that assert on measured data values.
audience: runtime
---

# Statcast Data Conventions

Facts verified empirically against this repo's parquet files. When a fact below matters to your task, trust it; when designing on a column not listed here, run a quick polars probe first — never assume units, signs, or coverage.

## Units and columns

- `pfx_x`/`pfx_z` are in **FEET** in the raw parquet (range ±2.5). Multiply by 12 for inches. The engine converts at aggregation (`_FEET_TO_INCHES` in `engine.py` and `shape.py`), so `LeagueBaseline` and all summary dataclasses store **inches** — but any new computation reading raw frames must convert explicitly.
- `pfx_z` is **induced** vertical break (gravity removed, "ride"), not total drop. Label it accordingly.
- `effective_speed` exists in the parquet — Statcast's extension-adjusted perceived velocity. Don't recompute it from `release_extension` unless it's null.
- `arm_angle`: 0° = sidearm, 90° = straight over the top. Hand-symmetric — no L/R mirroring needed.

## Sign conventions (raw = catcher's perspective)

- `pfx_x` positive = toward the catcher's right.
- A RHP's arm-side run is **negative** raw `pfx_x`; a LHP's arm-side is positive.
- To pool handedness into one table: `arm_side_run = pfx_x` for LHP, `-pfx_x` for RHP. Sanity check: league sinker `pfx_x` means mirror at ±1.24 ft by handedness.
- Baseball Savant's website displays pitcher's-view movement — flipped from raw. Don't reconcile against the UI without flipping.

## Coverage and quality

- `arm_angle` nulls: ~8.5% in the 2025 file, ~58% in the 2026 file (early-season tracking gaps). Nulls cluster by park/outage — always check the null rate for *your* pitcher before per-pitcher use.
- `arm_angle` has garbage outliers (observed min −134°). Filter to `is_between(-90, 95)` for league aggregations.
- `pfx_*` nulls ~3%; `mean()` skips them.
- Multi-year loads concatenate with `diagonal_relaxed`: a column missing from one year's file silently fills null. Check per-year coverage when a column's null rate surprises you.
- `data.statcast` (from `load_pitcher_data`) spans **all loaded seasons**. Never build test assertions from probing a single parquet — measure against the same frame the code uses.
- Key id/grouping columns: `pitcher` (MLBAM id), `game_year` (exists in parquet; `engine.py` also derives season via `game_date.dt.year()`), `p_throws`, `pitch_type`/`pitch_name`.
- The ±1.24 ft sinker check, explicitly: RHP SI mean `pfx_x` ≈ −1.24 ft, LHP ≈ +1.24 ft.

## Probe recipe

```python
df = pl.scan_parquet("statcast_2026.parquet").select(cols).collect()
df["col"].min(), df["col"].max()          # units (feet vs inches ranges)
df.group_by("p_throws").agg(pl.col("pfx_x").mean())  # sign/mirroring
df["col"].null_count() / len(df)          # coverage
```

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Treating `pfx_*` as inches | ×12, and say "in" only after converting |
| Pooling L/R movement without mirroring | Flip `pfx_x` for one hand first |
| Test counts from one parquet | Measure via `load_pitcher_data` (multi-year) |
| Using `arm_angle` without null/outlier checks | Null-rate + `is_between(-90, 95)` first |
