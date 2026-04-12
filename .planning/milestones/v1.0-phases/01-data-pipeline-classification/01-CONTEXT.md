# Phase 1: Data Pipeline & Classification - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the data loading pipeline and CLI skeleton. Load Statcast parquet and all Pitching+ CSV aggregations, filter by pitcher ID and lookback window, classify each appearance as start or relief, and compute season baselines. Output is filtered, classified polars DataFrames ready for downstream delta computation.

</domain>

<decisions>
## Implementation Decisions

### CLI & Defaults
- Default lookback window is 30 days when `-w` is omitted (covers ~5 starts for SP, plenty of RP appearances)
- Invalid pitcher ID exits with clear error: "Pitcher {id} not found" and exit(1)
- Include all game types (S/R/C) — spring training data is the bulk of what's available
- Silent CLI until report is ready — print only the final report, no progress messages

### Data Architecture
- Single `data.py` module for all data loading (project is small, one module with loader functions)
- Load all CSV agg files upfront and filter immediately (files are small, total < 100MB)
- Use polars DataFrames throughout Phase 1; Pydantic models come later in Phase 3
- Parse CSV game_date strings to Date type at load time for consistent joining/filtering

### Starter/Reliever Classification
- Primary heuristic: first inning pitched = 1 → Start; otherwise → Relief (derives from Statcast inning column)
- Openers classified as Start regardless of innings pitched — report notes short outing in workload section
- Add `role` column ("SP" / "RP") to the appearance DataFrame, computed during data loading
- Single appearance in window still generates a report — season baselines provide comparison context

### Claude's Discretion
- argparse argument naming and help text
- Internal function signatures and return types
- Error handling for malformed/missing data files

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `main.py` exists with hello-world scaffold — will be replaced with CLI entry point
- `pyproject.toml` has polars and pydantic-ai dependencies declared
- `.venv` exists with uv-managed virtual environment

### Established Patterns
- uv as package manager (uv run to execute)
- Python 3.14 specified in .python-version

### Integration Points
- `statcast_2026.parquet` at project root (145K rows, 114 cols, Date type for game_date)
- `aggs/*.csv` directory with 8 CSV files (String type for game_date — needs parsing)
- Join key: `pitcher` column in both parquet and CSVs

### Data Observations
- Date range: 2026-02-20 to 2026-03-25
- Game types: S (spring training, 133K pitches), C (college/exhibition, 11K), R (regular season, 258)
- 1,651 unique pitchers, 6,228 total appearances, avg 3.8 appearances per pitcher
- Pitch counts range 1-92 per appearance (median 18, mean 23)
- Starters identifiable by first_inning = 1 in Statcast data (confirmed with Weathers, Ryan example: innings [1,2,3,4], 74 pitches)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
