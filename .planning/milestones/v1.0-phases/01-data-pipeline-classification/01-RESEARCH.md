# Phase 1: Data Pipeline & Classification - Research

**Researched:** 2026-03-26
**Domain:** Python data pipeline with polars, argparse CLI, baseball pitch classification
**Confidence:** HIGH

## Summary

Phase 1 builds the foundation: a CLI entry point that accepts a pitcher ID and optional lookback window, loads Statcast parquet and Pitching+ CSV aggregations, filters to the target pitcher, classifies each appearance as start or relief, and computes season-level baselines. All data stays as polars DataFrames.

The data is well-structured and the tooling is verified. The parquet file (145K rows, 114 columns) has `game_date` as a native `Date` type and `pitcher` as `Int64`, making filtering efficient. The 8 CSV aggregation files use string dates that need parsing but share `pitcher` (Int64) and `game_pk` (Int64) as join keys. Starter/reliever classification using `first_inning == 1` is confirmed working -- 1,027 starts and 5,220 relief appearances detected, with 256 swingmen who have both role types.

**Primary recommendation:** Build a single `data.py` module with loader functions that return typed polars DataFrames. Use `game_pk` as the appearance identifier (not `game_date`, since doubleheaders exist). Compute season baselines via n_pitches-weighted averaging across game_type rows in `pitcher.csv` and `pitcher_type.csv`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Default lookback window is 30 days when `-w` is omitted (covers ~5 starts for SP, plenty of RP appearances)
- Invalid pitcher ID exits with clear error: "Pitcher {id} not found" and exit(1)
- Include all game types (S/R/C) -- spring training data is the bulk of what's available
- Silent CLI until report is ready -- print only the final report, no progress messages
- Single `data.py` module for all data loading (project is small, one module with loader functions)
- Load all CSV agg files upfront and filter immediately (files are small, total < 100MB)
- Use polars DataFrames throughout Phase 1; Pydantic models come later in Phase 3
- Parse CSV game_date strings to Date type at load time for consistent joining/filtering
- Primary heuristic: first inning pitched = 1 -> Start; otherwise -> Relief (derives from Statcast inning column)
- Openers classified as Start regardless of innings pitched -- report notes short outing in workload section
- Add `role` column ("SP" / "RP") to the appearance DataFrame, computed during data loading
- Single appearance in window still generates a report -- season baselines provide comparison context

### Claude's Discretion
- argparse argument naming and help text
- Internal function signatures and return types
- Error handling for malformed/missing data files

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Load Statcast parquet and filter pitch-level data by pitcher ID | Parquet has `pitcher` (Int64) and `game_date` (Date) columns; `pl.read_parquet()` with column selection + filter confirmed working |
| DATA-02 | Load and join Pitching+ CSV aggregations at all grains | 8 CSV files mapped: 4 season-level, 4 appearance-level; all share `pitcher` (Int64) join key; appearance CSVs also have `game_pk` (Int64) |
| DATA-03 | Compute season-level baselines from pitcher.csv and pitcher_type.csv | pitcher.csv has 1,994 rows (1,651 pitchers x game_type); pitcher_type.csv has 8,120 rows; n_pitches-weighted averaging across game_types confirmed to produce correct results |
| DATA-04 | Filter appearances to configurable lookback window in days | Date filtering via `pl.col('game_date') >= cutoff_date` using `datetime.date` arithmetic confirmed working |
| ROLE-01 | Auto-detect whether each appearance is start or relief | `first_inning == 1` heuristic validated: 1,027 starts, 5,220 reliefs across 6,247 appearances |
| ROLE-02 | Report structure adapts based on detected role | Role column ("SP"/"RP") per appearance enables downstream branching; Phase 1 adds the column, Phase 4 uses it for report structure |
| ROLE-03 | Correctly handle swingmen/openers who switch roles | 256 swingmen confirmed in dataset; per-appearance classification (not per-pitcher) handles this correctly |
| CLI-01 | Script accepts `-p` argument for pitcher ID | argparse with `type=int` for pitcher ID |
| CLI-02 | Script accepts `-w` argument for lookback window with sensible default | argparse with `type=int, default=30` for lookback days |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame operations for all data loading, filtering, aggregation | Already in pyproject.toml; Rust-backed, fast columnar ops; native Date type handling |
| argparse | stdlib | CLI argument parsing | Standard library, no extra dependency; sufficient for `-p` and `-w` flags |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| datetime | stdlib | Date arithmetic for lookback window computation | `date.today() - timedelta(days=window)` for cutoff date |
| sys | stdlib | `sys.exit(1)` for error exits | Invalid pitcher ID, missing data files |
| pathlib | stdlib | File path handling for data files | Locating parquet and CSV files relative to project root |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| argparse | typer (already in lockfile) | Overkill for 2 flags; argparse is zero-dependency and the CONTEXT says keep it simple |
| argparse | click | Extra dependency, not needed for this scope |
| polars read_csv | polars scan_csv (lazy) | Eager is fine -- CSVs are < 100MB total, loaded once |

**Installation:**
```bash
# No new packages needed -- polars already in pyproject.toml, argparse/datetime/sys/pathlib are stdlib
uv sync
```

**Version verification:** polars 1.39.3 confirmed installed and working with Python 3.14.3.

## Architecture Patterns

### Recommended Project Structure
```
pitcher-narratives/
+-- main.py              # CLI entry point: argparse, orchestration
+-- data.py              # All data loading functions (single module per CONTEXT decision)
+-- statcast_2026.parquet
+-- aggs/
|   +-- 2026-pitcher.csv
|   +-- 2026-pitcher_type.csv
|   +-- 2026-pitcher_appearance.csv
|   +-- 2026-pitcher_type_appearance.csv
|   +-- 2026-pitcher_type_platoon.csv
|   +-- 2026-pitcher_type_platoon_appearance.csv
|   +-- 2026-all_pitches.csv
|   +-- 2026-team.csv
+-- pyproject.toml
+-- .python-version
```

### Pattern 1: Data Loading with Eager Filtering
**What:** Load each data source and immediately filter to target pitcher. Return typed DataFrames.
**When to use:** Every data load function.
**Example:**
```python
import polars as pl
from pathlib import Path
from datetime import date, timedelta

DATA_DIR = Path(__file__).parent
PARQUET_PATH = DATA_DIR / "statcast_2026.parquet"
AGGS_DIR = DATA_DIR / "aggs"

def load_statcast(pitcher_id: int) -> pl.DataFrame:
    """Load Statcast pitch-level data filtered to a single pitcher."""
    df = pl.read_parquet(PARQUET_PATH)
    result = df.filter(pl.col("pitcher") == pitcher_id)
    if result.is_empty():
        raise ValueError(f"Pitcher {pitcher_id} not found")
    return result
```

### Pattern 2: CSV Date Parsing at Load Time
**What:** Parse string game_date columns to Date type immediately when loading CSVs.
**When to use:** Any CSV with a game_date column (4 of the 8 CSVs have it).
**Example:**
```python
def _load_csv_with_dates(filename: str, pitcher_id: int) -> pl.DataFrame:
    """Load a CSV agg file, parse dates, filter to pitcher."""
    path = AGGS_DIR / filename
    df = pl.read_csv(path)
    if "game_date" in df.columns:
        df = df.with_columns(
            pl.col("game_date").str.to_date("%Y-%m-%d")
        )
    return df.filter(pl.col("pitcher") == pitcher_id)
```

### Pattern 3: Appearance Classification via First Inning
**What:** Derive role from minimum inning pitched in each game appearance.
**When to use:** After loading Statcast data, before returning appearances.
**Example:**
```python
def classify_appearances(statcast: pl.DataFrame) -> pl.DataFrame:
    """Classify each appearance as SP or RP based on first inning pitched."""
    appearances = statcast.group_by(["game_pk", "game_date"]).agg(
        pl.col("inning").min().alias("first_inning"),
        pl.col("inning").max().alias("last_inning"),
        pl.len().alias("n_pitches"),
    ).with_columns(
        pl.when(pl.col("first_inning") == 1)
        .then(pl.lit("SP"))
        .otherwise(pl.lit("RP"))
        .alias("role")
    ).sort("game_date")
    return appearances
```

### Pattern 4: Season Baseline with n_pitches-Weighted Averaging
**What:** Combine game_type rows (S/C/R) into a single season baseline using pitch-count weighting.
**When to use:** Computing baselines from pitcher.csv and pitcher_type.csv.
**Why:** 337 pitchers have multiple game_type rows (e.g., spring + regular season). Weighting by n_pitches gives mathematically correct combined averages.
**Example:**
```python
def compute_season_baseline(pitcher_csv: pl.DataFrame) -> pl.DataFrame:
    """Compute n_pitches-weighted season baseline across all game types."""
    metric_cols = [c for c in pitcher_csv.columns
                   if c not in ("season", "level", "game_type", "pitcher",
                                "player_name", "p_throws", "team_code", "n_pitches")]
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return pitcher_csv.group_by("pitcher").agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted_exprs,
    )
```

### Pattern 5: Lookback Window Filtering
**What:** Filter appearance-level data to a date window relative to the most recent date in the dataset.
**When to use:** After loading, before analysis. Uses the max date in the data as "today" (not `date.today()`) since data may not be current.
**Example:**
```python
def filter_to_window(df: pl.DataFrame, window_days: int) -> pl.DataFrame:
    """Filter DataFrame to appearances within the lookback window."""
    max_date = df["game_date"].max()
    cutoff = max_date - timedelta(days=window_days)
    return df.filter(pl.col("game_date") >= cutoff)
```

### Anti-Patterns to Avoid
- **Using `date.today()` for window cutoff:** The dataset ends 2026-03-25. If run later, `date.today()` would filter out everything. Use the max date in the dataset instead.
- **Filtering by game_date alone for appearances:** Doubleheaders mean a pitcher could appear twice on the same date. Always use `game_pk` as the unique appearance identifier.
- **Loading parquet columns lazily then collecting:** For this data size (145K rows), eager loading with column selection is simpler and fast enough. LazyFrame adds complexity without benefit.
- **Aggregating pitcher.csv by simple mean:** Rows have different n_pitches counts per game_type. Simple mean of P+ across S/C/R rows gives wrong results. Must use n_pitches-weighted average.
- **Skipping game_type filtering:** The decision says include all game types. Do not filter out spring training (S) or college/exhibition (C) data.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parquet reading | Custom binary parser | `pl.read_parquet()` | Polars handles columnar format natively with zero-copy |
| CSV date parsing | Manual string splitting | `pl.col("game_date").str.to_date("%Y-%m-%d")` | Polars expression handles edge cases, vectorized |
| CLI argument parsing | Manual sys.argv parsing | `argparse.ArgumentParser` | Standard, handles help text, type validation, defaults |
| Weighted averaging | Manual loop with running totals | Polars `group_by().agg()` with weighted expressions | Vectorized, handles nulls, single expression |
| Date arithmetic | Manual day counting | `datetime.date - datetime.timedelta` | Handles month boundaries, leap years correctly |

**Key insight:** Polars expressions handle the heavy lifting. Every data transformation should be a polars expression chain, not a Python loop.

## Common Pitfalls

### Pitfall 1: Parquet Date Type vs CSV String Dates
**What goes wrong:** Joining parquet data (Date type) with CSV data (String type) silently produces zero rows or type errors.
**Why it happens:** The parquet has `game_date` as `Date`, CSVs have it as `String` ("2026-03-25" format).
**How to avoid:** Parse CSV game_date to Date at load time (Pattern 2 above). Verify dtype after parsing.
**Warning signs:** Empty join results, `SchemaError` on date comparisons.

### Pitfall 2: Multiple game_type Rows in Season CSVs
**What goes wrong:** Using `pitcher.csv` directly as a 1-row-per-pitcher baseline gives wrong results for 337 pitchers (20% of dataset).
**Why it happens:** pitcher.csv and pitcher_type.csv have separate rows per game_type (S/C/R). A pitcher with S and C data has 2 rows.
**How to avoid:** Always aggregate across game_types using n_pitches-weighted averaging (Pattern 4).
**Warning signs:** Duplicate pitcher IDs when you expect unique, assertion failures on row counts.

### Pitfall 3: all_pitches.csv vs Statcast Parquet Row Mismatch
**What goes wrong:** Assuming all_pitches.csv and statcast_2026.parquet have identical rows. They differ by 1,422 rows (143,885 vs 145,307).
**Why it happens:** The Pitching+ model likely filters out some pitches (intentional balls, pitchouts, etc.) before computing scores.
**How to avoid:** Treat them as complementary sources. Use parquet for raw Statcast data (velocity, movement), use all_pitches.csv when P+ scores are needed. Join on `pitcher + game_pk + pitch_number` if combining.
**Warning signs:** Row count mismatches after merges.

### Pitfall 4: Lookback Window Using Real Today vs Data Today
**What goes wrong:** Using `date.today()` in March 2026 works if data is current, but breaks if someone runs the tool in April with the same static dataset.
**Why it happens:** Static data files don't update. The latest game_date is 2026-03-25.
**How to avoid:** Use `df["game_date"].max()` as the reference date for window calculations.
**Warning signs:** Zero appearances in window, empty results.

### Pitfall 5: Empty Pitcher ID Handling
**What goes wrong:** A valid integer that's not in the dataset causes cryptic downstream errors instead of a clean exit.
**Why it happens:** Filter returns empty DataFrame, subsequent operations on empty frames produce confusing errors.
**How to avoid:** Check immediately after the first filter -- if empty, print "Pitcher {id} not found" and `sys.exit(1)` per the locked decision.
**Warning signs:** `ShapeError` or `ComputeError` deep in processing code.

### Pitfall 6: pitcher_type.csv Empty Pitch Type Strings
**What goes wrong:** Some rows in pitcher_type.csv have empty string `""` for pitch_type (confirmed in data exploration). These could pollute per-pitch-type baselines.
**Why it happens:** The source data includes unclassified pitches.
**How to avoid:** Filter out rows where `pitch_type == ""` when computing per-pitch-type baselines.
**Warning signs:** An extra "unknown" pitch type in results, NaN values in pitch type summaries.

## Code Examples

### Complete CLI Entry Point Pattern
```python
# main.py
import argparse
import sys

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate pitcher scouting reports from Statcast data"
    )
    parser.add_argument(
        "-p", "--pitcher", type=int, required=True,
        help="MLB pitcher ID (e.g., 592155)"
    )
    parser.add_argument(
        "-w", "--window", type=int, default=30,
        help="Lookback window in days (default: 30)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Phase 1: Load and classify data
    from data import load_pitcher_data
    try:
        pitcher_data = load_pitcher_data(args.pitcher, args.window)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    # Phase 1 temporary output for verification:
    # Print summary of what was loaded (will be replaced by report in Phase 4)


if __name__ == "__main__":
    main()
```

### Complete Data Module Pattern
```python
# data.py
import polars as pl
from pathlib import Path
from datetime import timedelta

DATA_DIR = Path(__file__).parent
PARQUET_PATH = DATA_DIR / "statcast_2026.parquet"
AGGS_DIR = DATA_DIR / "aggs"

# CSV filenames organized by grain
_SEASON_CSVS = {
    "pitcher": "2026-pitcher.csv",
    "pitcher_type": "2026-pitcher_type.csv",
    "pitcher_type_platoon": "2026-pitcher_type_platoon.csv",
    "team": "2026-team.csv",
}
_APPEARANCE_CSVS = {
    "pitcher_appearance": "2026-pitcher_appearance.csv",
    "pitcher_type_appearance": "2026-pitcher_type_appearance.csv",
    "pitcher_type_platoon_appearance": "2026-pitcher_type_platoon_appearance.csv",
    "all_pitches": "2026-all_pitches.csv",
}
```

### Weighted Baseline Computation (Verified)
```python
# Verified: produces identical results to pitch-level mean from all_pitches.csv
# For pitcher 592155 (Booser, Cam):
#   Weighted P+ from pitcher.csv: 106.22
#   Mean P+ from all_pitches.csv: 106.23 (rounding diff only)

def compute_season_baseline(df: pl.DataFrame) -> pl.DataFrame:
    """Weighted average across game_type rows."""
    id_cols = {"season", "level", "game_type", "pitcher", "player_name",
               "p_throws", "team_code", "n_pitches"}
    metric_cols = [c for c in df.columns if c not in id_cols]
    weighted = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(
            pl.col("n_pitches").sum()
        ).alias(c)
        for c in metric_cols
    ]
    return df.group_by("pitcher").agg(
        pl.col("n_pitches").sum(),
        pl.col("player_name").first(),
        pl.col("p_throws").first(),
        pl.col("team_code").first(),
        *weighted,
    )
```

### Appearance Classification (Verified)
```python
# Verified against dataset:
# - 1,027 starts (first_inning == 1)
# - 5,220 relief appearances (first_inning > 1)
# - 256 swingmen with both SP and RP appearances
# Sample: Booser, Cam (592155) has 1 start + 11 relief in 12 appearances

def classify_appearances(statcast: pl.DataFrame) -> pl.DataFrame:
    """Add role column to appearance-level aggregation."""
    return statcast.group_by(["game_pk", "game_date"]).agg(
        pl.col("inning").min().alias("first_inning"),
        pl.col("inning").max().alias("last_inning"),
        pl.len().alias("n_pitches"),
        pl.col("player_name").first(),
    ).with_columns(
        pl.when(pl.col("first_inning") == 1)
        .then(pl.lit("SP"))
        .otherwise(pl.lit("RP"))
        .alias("role")
    ).sort("game_date")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas for DataFrames | polars for columnar ops | 2023-2024 adoption wave | 10-100x faster, native Date types, expression API |
| Manual CSV date parsing with strptime | `pl.col().str.to_date()` | polars 0.18+ | Vectorized, handles edge cases |
| click/typer for CLIs | argparse still standard for simple tools | Always | Zero dependencies for 2-flag CLI |

**Deprecated/outdated:**
- polars `lazy()` then `collect()` for small datasets: Unnecessary complexity for < 1M rows. Eager is fine.
- `pl.col().apply()` for row-wise ops: Use native expressions instead. `apply` is the slow path.

## Open Questions

1. **Pitch type baseline for pitcher_type.csv with empty pitch_type**
   - What we know: Some rows have `pitch_type == ""` in pitcher_type.csv
   - What's unclear: Whether these represent intentional balls, unclassified pitches, or data errors
   - Recommendation: Filter out empty pitch_type rows when computing per-pitch-type baselines. Log a count if noisy.

2. **all_pitches.csv vs parquet: which is primary source?**
   - What we know: Parquet has 1,422 more rows, parquet has raw Statcast columns, all_pitches has P+ scores
   - What's unclear: Whether Phase 2+ needs both or can use all_pitches.csv exclusively
   - Recommendation: Phase 1 loads BOTH. Parquet for raw pitch data (velocity, movement). all_pitches.csv for P+ scores. They can be joined on pitcher + game_pk + pitch_number if needed later.

3. **Return type from data module**
   - What we know: The CONTEXT says polars DataFrames, no Pydantic until Phase 3
   - What's unclear: Whether to return individual DataFrames or a dict/namedtuple bundle
   - Recommendation: Return a simple dataclass or NamedTuple to bundle the DataFrames. Keeps the API clean without requiring Pydantic.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (needs installation) |
| Config file | none -- see Wave 0 |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Load parquet filtered by pitcher ID | unit | `uv run pytest tests/test_data.py::test_load_statcast_filters_by_pitcher -x` | Wave 0 |
| DATA-01 | Invalid pitcher ID raises ValueError | unit | `uv run pytest tests/test_data.py::test_load_statcast_invalid_pitcher -x` | Wave 0 |
| DATA-02 | Load all CSV agg files for a pitcher | unit | `uv run pytest tests/test_data.py::test_load_csvs_all_grains -x` | Wave 0 |
| DATA-02 | CSV game_date parsed to Date type | unit | `uv run pytest tests/test_data.py::test_csv_date_parsing -x` | Wave 0 |
| DATA-03 | Season baseline computed with weighted averaging | unit | `uv run pytest tests/test_data.py::test_season_baseline_weighted -x` | Wave 0 |
| DATA-03 | Baseline handles single game_type pitcher | unit | `uv run pytest tests/test_data.py::test_season_baseline_single_game_type -x` | Wave 0 |
| DATA-04 | Window filter restricts appearances by days | unit | `uv run pytest tests/test_data.py::test_window_filter -x` | Wave 0 |
| ROLE-01 | Appearances classified as SP when first_inning=1 | unit | `uv run pytest tests/test_data.py::test_classify_starter -x` | Wave 0 |
| ROLE-01 | Appearances classified as RP when first_inning>1 | unit | `uv run pytest tests/test_data.py::test_classify_reliever -x` | Wave 0 |
| ROLE-03 | Swingman gets both SP and RP across appearances | unit | `uv run pytest tests/test_data.py::test_swingman_classification -x` | Wave 0 |
| CLI-01 | -p flag accepted and parsed as int | unit | `uv run pytest tests/test_cli.py::test_parse_pitcher_flag -x` | Wave 0 |
| CLI-02 | -w flag defaults to 30 | unit | `uv run pytest tests/test_cli.py::test_window_default -x` | Wave 0 |
| ROLE-02 | Role column present in output | unit | `uv run pytest tests/test_data.py::test_role_column_exists -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Install pytest: `uv add --dev pytest`
- [ ] `tests/__init__.py` -- empty init for test package
- [ ] `tests/test_data.py` -- covers DATA-01, DATA-02, DATA-03, DATA-04, ROLE-01, ROLE-02, ROLE-03
- [ ] `tests/test_cli.py` -- covers CLI-01, CLI-02
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` section for config

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All code | Yes | 3.14.3 | -- |
| uv | Package management | Yes | 0.7.11 | -- |
| polars | Data loading/processing | Yes | 1.39.3 | -- |
| pytest | Testing | No | -- | `uv add --dev pytest` |
| statcast_2026.parquet | DATA-01 | Yes | 20MB file at project root | -- |
| aggs/*.csv (8 files) | DATA-02, DATA-03 | Yes | All 8 files present | -- |

**Missing dependencies with no fallback:**
- None -- all core dependencies available.

**Missing dependencies with fallback:**
- pytest: Not installed. Install with `uv add --dev pytest` as first task.

## Project Constraints (from CLAUDE.md)

- **Tech stack locked:** Python, polars, pydantic-ai, Claude (already in pyproject.toml)
- **Data format:** Static parquet + CSV files, no live API calls to Baseball Savant
- **Python version:** 3.14+ (verified: 3.14.3 installed)
- **Package manager:** uv (verified: 0.7.11 installed)
- **Naming:** snake_case for modules, functions, variables; PascalCase for classes; UPPER_SNAKE_CASE for constants
- **Docstrings:** Google-style on all public functions
- **Type hints:** On all function signatures
- **Error handling:** Specific exception types, not bare `except:`; handle `pl.exceptions.ComputeError` for polars
- **No print statements for logging** -- but Phase 1 CONTEXT says "Silent CLI until report is ready" so minimal output is fine during data loading
- **GSD workflow enforcement:** All code changes through GSD commands

## Data Schema Reference

### Statcast Parquet Key Columns (for Phase 1)
| Column | Type | Purpose |
|--------|------|---------|
| pitcher | Int64 | Pitcher ID -- primary filter key |
| game_date | Date | Game date -- native Date type, no parsing needed |
| game_pk | Int64 | Game identifier -- unique appearance key |
| game_type | String | S/C/R -- spring/college/regular |
| inning | Int64 | Inning number -- 1 means starter |
| player_name | String | "Last, First" format |
| pitch_type | String | FF/SI/CH/SL/etc |
| p_throws | String | L/R |

### CSV Aggregation File Map
| File | Grain | Key Columns | Has game_date | Phase 1 Use |
|------|-------|-------------|---------------|-------------|
| pitcher.csv | Season x game_type | pitcher | No | Season baseline (weighted across game_types) |
| pitcher_type.csv | Season x game_type x pitch_type | pitcher, pitch_type | No | Per-pitch-type season baseline |
| pitcher_appearance.csv | Appearance | pitcher, game_pk, game_date | Yes (String) | Appearance-level P+ scores |
| pitcher_type_appearance.csv | Appearance x pitch_type | pitcher, game_pk, game_date, pitch_type | Yes (String) | Per-pitch-type appearance scores |
| pitcher_type_platoon.csv | Season x pitch_type x platoon | pitcher, pitch_type, platoon_matchup | No | Platoon baselines (Phase 2+) |
| pitcher_type_platoon_appearance.csv | Appearance x pitch_type x platoon | pitcher, game_pk, game_date, pitch_type, platoon_matchup | Yes (String) | Platoon appearance scores (Phase 2+) |
| all_pitches.csv | Pitch-level | pitcher, game_pk, game_date, pitch_number | Yes (String) | Pitch-level P+ scores (143,885 rows) |
| team.csv | Team-level | team_code | No | League context (Phase 3+) |

## Sources

### Primary (HIGH confidence)
- Direct data exploration: statcast_2026.parquet schema, row counts, dtypes verified via polars
- Direct data exploration: All 8 CSV files -- columns, dtypes, row counts, join compatibility verified
- Polars 1.39.3 API: `read_parquet`, `read_csv`, `str.to_date`, `group_by`, `with_columns`, `when/then/otherwise` all tested against actual data
- Role classification heuristic: Validated against dataset (1,027 starts, 5,220 reliefs, 256 swingmen confirmed)
- Weighted baseline computation: Verified equivalence with pitch-level means (106.22 vs 106.23 for test pitcher)

### Secondary (MEDIUM confidence)
- Python 3.14.3 + polars 1.39.3 compatibility: Confirmed working (no issues found, contrary to STATE.md concern)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All packages already installed and verified working with Python 3.14
- Architecture: HIGH - Patterns tested against actual data, results verified
- Pitfalls: HIGH - Each pitfall discovered through direct data exploration (game_type grouping, date types, row count mismatches)
- Data schema: HIGH - Every column, type, and relationship verified through direct querying

**Research date:** 2026-03-26
**Valid until:** 2026-04-25 (stable -- static data files, locked polars version)
