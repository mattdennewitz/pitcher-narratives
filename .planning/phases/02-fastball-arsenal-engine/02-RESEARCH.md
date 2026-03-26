# Phase 2: Fastball & Arsenal Engine - Research

**Researched:** 2026-03-26
**Domain:** Polars computation engine -- transforming loaded pitcher data into pre-computed fastball quality analysis and arsenal breakdowns with qualitative trend strings
**Confidence:** HIGH

## Summary

This phase builds a pure computation layer (`engine.py`) that consumes the `PitcherData` bundle from Phase 1 and produces structured dicts/dataclasses with pre-computed deltas and qualitative trend strings ready for LLM consumption. The core challenge is computing baselines, window averages, and deltas across multiple data sources (Statcast pitch-level parquet and P+ CSV aggregations) while handling edge cases like single-inning relievers, small samples, and cold-start pitchers.

The data layer from Phase 1 is solid and well-tested. The engine needs to: (1) identify the primary fastball, (2) compute velocity/movement/P+ deltas for it, (3) compute within-game velocity arcs, (4) build per-pitch-type arsenal breakdowns with usage deltas, (5) compute platoon mix shifts, and (6) analyze first-pitch weaponry changes. All outputs are string-enriched dicts -- directional delta vocabulary like "Up 1.2 mph", "Down sharply (-3.1)", "Steady (+0.2)" -- not raw numbers.

**Primary recommendation:** Build `engine.py` with focused, composable functions that each compute one analysis facet, using the existing `PitcherData` bundle as input and returning dataclasses with string fields. Use n_pitches-weighted averaging for all P+ window computations (same pattern already established in `data.py`). Handle edge cases explicitly with fallback strings rather than errors.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- New `engine.py` module -- separates computation from data loading; imports PitcherData from data.py
- Primary fastball identified as highest-usage fastball type (FF, SI, FC) from pitcher_type season baseline
- Fastball pitch types: FF (Four-Seam), SI (Sinker), FC (Cutter) -- standard Statcast classification
- Engine functions return plain dicts/dataclasses with string fields -- qualitative trend strings ready for LLM, not DataFrames
- Notable velocity change threshold: 0.5 mph (below is noise in Statcast data)
- Notable usage rate change threshold: 5 percentage points
- Qualitative delta vocabulary: directional + magnitude -- "Up 1.2 mph", "Down sharply (-3.1)", "Steady (+0.2)"
- Within-game velocity arc: compare avg velo in first 2 innings vs last 2 innings of the appearance
- Platoon mix shifts: compare pitch type usage % vs RHB and vs LHB from platoon appearance data, delta vs season platoon baseline
- First pitch: pitch_number == 1 in Statcast data (first pitch of each at-bat)
- First-pitch weaponry changes: compare % of first pitches that are each pitch type in recent window vs season
- Minimum pitch count for per-pitch-type analysis: 10 pitches of that type in window; below this flag "small sample" but still include

### Claude's Discretion
- Internal function signatures and helper naming
- Exact dataclass field names for engine output
- How to handle pitchers with only 1 pitch type (no arsenal analysis needed)
- Ordering of pitch types in output (by usage? alphabetical?)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FB-01 | Average fastball velocity for season baseline vs. recent window | Statcast `release_speed` column available; primary fastball identified via highest-usage FB type in pitch_type_baseline; season velo from Statcast full data, window velo from window-filtered Statcast |
| FB-02 | P+/S+/L+ for primary fastball: season baseline vs. recent window with delta | `pitch_type_baseline` provides season P+/S+/L+ per type; `pitcher_type_appearance` CSV filtered to window dates provides window P+ via n_pitches-weighted averaging |
| FB-03 | Movement deltas (pfx_x/pfx_z) for fastball: season baseline vs. recent | Statcast `pfx_x` and `pfx_z` columns available; compute mean from full Statcast vs window-filtered Statcast |
| FB-04 | Within-game velocity arc analysis (early vs. late innings drop-off) | Statcast `inning` and `release_speed` available; decision specifies first 2 vs last 2 innings; edge case: single-inning relievers have no arc |
| ARSL-01 | Usage rate per pitch type with delta vs. season baseline | Count pitch_type in Statcast, divide by total; compare season vs window proportions |
| ARSL-02 | P+/S+/L+ per pitch type: season baseline vs. recent window with delta | Same approach as FB-02 but for all pitch types, not just primary fastball |
| ARSL-03 | Platoon mix shifts (usage changes by batter handedness) | Statcast `stand` column maps to P+ `platoon_matchup` (same/opposite); compute usage % per type per platoon in window vs season |
| ARSL-04 | First-pitch strike weaponry analysis | Statcast `pitch_number == 1` identifies first pitches; compute pitch type distribution for first pitches in window vs season |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | All DataFrame computation | Already used in data.py; columnar operations are the right tool for aggregation/grouping |
| dataclasses | stdlib | Engine output structures | Locked decision: return dataclasses with string fields |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 | Test framework | Already configured in pyproject.toml |

No new dependencies needed. This phase uses only polars (already installed) and stdlib dataclasses.

## Architecture Patterns

### Recommended Project Structure
```
pitcher-narratives/
  data.py             # Phase 1 -- data loading (unchanged)
  engine.py            # Phase 2 -- NEW: computation engine
  main.py              # CLI entry point (minor update to exercise engine)
  tests/
    test_data.py       # Phase 1 tests (unchanged)
    test_engine.py     # Phase 2 -- NEW: engine tests
```

### Pattern 1: Composable Engine Functions
**What:** Each engine function computes one analysis facet and returns a dataclass. A top-level orchestrator calls them all.
**When to use:** Every engine computation.
**Example:**
```python
from dataclasses import dataclass
from data import PitcherData

@dataclass
class FastballSummary:
    """Pre-computed fastball quality analysis ready for LLM."""
    pitch_type: str           # e.g., "FF"
    pitch_name: str           # e.g., "Four-Seam Fastball"
    season_velo: float
    window_velo: float
    velo_delta: str           # e.g., "Down 1.2 mph from baseline"
    season_p_plus: float
    window_p_plus: float
    p_plus_delta: str         # e.g., "Up 8 points"
    # ... more fields
    small_sample: bool

def compute_fastball_summary(data: PitcherData, window_days: int) -> FastballSummary:
    """Compute fastball quality analysis with deltas and trend strings."""
    ...
```

### Pattern 2: Delta String Generation
**What:** A reusable helper that converts numeric deltas into qualitative trend strings.
**When to use:** Every delta computation (velocity, P+, usage rate, movement).
**Example:**
```python
def _velo_delta_string(delta: float, threshold: float = 0.5) -> str:
    """Convert velocity delta to qualitative string.

    Args:
        delta: window_value - season_value (positive = faster)
        threshold: below this magnitude, report as "Steady"
    """
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f})"
    direction = "Up" if delta > 0 else "Down"
    magnitude = abs(delta)
    if magnitude >= 2.0:
        return f"{direction} sharply ({delta:+.1f} mph)"
    return f"{direction} {magnitude:.1f} mph"
```

### Pattern 3: N-Pitches Weighted Window Averaging
**What:** Compute window-level P+ metrics by n_pitches-weighted average of per-appearance rows, same pattern as `compute_pitch_type_baseline` in data.py.
**When to use:** Any time you need window P+/S+/L+ from appearance-level CSV data.
**Example:**
```python
def _weighted_window_metrics(
    appearance_df: pl.DataFrame,
    window_dates: list,
    group_cols: list[str],
    metric_cols: list[str],
) -> pl.DataFrame:
    """Compute n_pitches-weighted averages for appearances in window."""
    window = appearance_df.filter(pl.col("game_date").is_in(window_dates))
    weighted_exprs = [
        (pl.col(c) * pl.col("n_pitches")).sum().truediv(pl.col("n_pitches").sum()).alias(c)
        for c in metric_cols
    ]
    return window.group_by(group_cols).agg(
        pl.col("n_pitches").sum(),
        *weighted_exprs,
    )
```

### Pattern 4: Platoon Mapping
**What:** Map Statcast `stand` + pitcher `p_throws` to P+ `platoon_matchup` values.
**When to use:** ARSL-03 platoon mix shift computation.
**Verified mapping:**
- For LHP (p_throws=L): stand=L -> "same", stand=R -> "opposite"
- For RHP (p_throws=R): stand=R -> "same", stand=L -> "opposite"
```python
def _stand_to_platoon(stand: str, p_throws: str) -> str:
    """Map batter handedness to platoon matchup label."""
    return "same" if stand == p_throws else "opposite"
```

### Anti-Patterns to Avoid
- **Returning DataFrames from engine functions:** Decision explicitly locks output as dicts/dataclasses with string fields. Engine consumes DataFrames internally but never exposes them.
- **Computing season baseline in engine:** Season baselines are already computed in `data.py` (`pitch_type_baseline`, `season_baseline`). Engine should use these, not recompute.
- **Silently dropping small samples:** Decision says minimum 10 pitches to compute per-type analysis, but below threshold flag "small sample" and still include. Never silently omit.
- **Using date.today() for window filtering:** Data is static. Window dates come from `window_appearances` game_dates which are already computed from max date in data.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Weighted averaging | Manual loop over rows | Polars `(col * weight).sum() / weight.sum()` expression | Already proven in data.py; vectorized; handles NaN correctly |
| Date windowing | Custom date math | `PitcherData.window_appearances["game_date"]` list | Phase 1 already computed the window; reuse those dates to filter P+ CSVs |
| Pitch type name mapping | Hardcoded dict | Statcast `pitch_name` column | Already available in parquet data |

## Common Pitfalls

### Pitfall 1: Game Type Splits in P+ Season Baselines
**What goes wrong:** P+ CSVs have multiple rows per pitch_type due to game_type (S=spring, C=cactus/grapefruit). Taking a simple mean without weighting by n_pitches gives incorrect baselines.
**Why it happens:** The raw CSV data splits by game_type, which is an artifact of the P+ computation pipeline.
**How to avoid:** Always use n_pitches-weighted averaging when combining game_type rows. Phase 1's `compute_pitch_type_baseline` already does this correctly -- use its output as the season baseline.
**Warning signs:** Seeing duplicate pitch_type rows in baseline computations.

### Pitfall 2: Single-Inning Reliever Velocity Arc
**What goes wrong:** The velocity arc (first 2 innings vs last 2 innings) is undefined for a pitcher who only pitched 1 inning in a game.
**Why it happens:** Short relievers routinely pitch only 1 inning. The test pitcher (Booser) has 12 appearances, all single-inning except his SP outing which was also 1 inning.
**How to avoid:** Check `first_inning != last_inning` before computing arc. If single inning, return a fallback string like "Single inning -- no velocity arc available". For starters who pitch 2+ innings but fewer than 4 (so "first 2 vs last 2" overlaps), handle gracefully.
**Warning signs:** Getting identical early/late velo (same inning counted in both halves).

### Pitfall 3: Cold Start -- No Prior Baseline
**What goes wrong:** When window contains ALL of a pitcher's appearances (e.g., pitcher has only 1 or 2 total appearances), window metrics equal season metrics and all deltas are zero.
**Why it happens:** STATE.md flagged this: "First-appearance cold start (no baseline to compare against) needs a fallback strategy in Phase 2."
**How to avoid:** Detect when `len(window_appearances) == len(appearances)` (window covers entire season). In that case, include season stats but note "Window covers full season -- no baseline comparison available" in trend strings.
**Warning signs:** All deltas are exactly 0.0 or very close. 412 pitchers in the dataset have only 1 appearance.

### Pitfall 4: Platoon Data Sparsity
**What goes wrong:** Not all pitch types appear against both platoon sides. E.g., Booser's CH is only thrown to opposite-hand batters (26 pitches, 0 same-side). Attempting to compute same-side CH usage gives a division-by-zero or missing row.
**Why it happens:** Pitchers legitimately throw certain pitches almost exclusively to one batter handedness (changeups to opposite side, sliders to same side).
**How to avoid:** Before computing platoon deltas, check if data exists for that pitch_type+platoon_matchup combination. If missing, report "Not thrown to [same/opposite]-side batters" rather than computing a zero-usage delta.
**Warning signs:** Missing rows after groupby, null values in division results.

### Pitfall 5: Pitch Name Mapping from Statcast
**What goes wrong:** Using pitch_type codes (FF, SI, FC) in LLM-facing output instead of human-readable names.
**Why it happens:** P+ CSVs only have `pitch_type` codes. Statcast has both `pitch_type` and `pitch_name`.
**How to avoid:** Build a pitch_type-to-name mapping from Statcast data: `statcast.select(["pitch_type", "pitch_name"]).unique()`.
**Warning signs:** Output strings containing "FF" instead of "Four-Seam Fastball".

### Pitfall 6: First Pitch Identification
**What goes wrong:** Using `at_bat_number == 1` or similar instead of `pitch_number == 1`.
**Why it happens:** Confusing "first at-bat" with "first pitch of each at-bat". The decision document specifies `pitch_number == 1`.
**How to avoid:** Verified in data: `pitch_number == 1` correctly identifies the first pitch of each plate appearance. For test pitcher Booser, this gives 42 first pitches across 42 at-bats faced.
**Warning signs:** Pitch counts not matching number of batters faced.

## Code Examples

### Identifying Primary Fastball
```python
# From pitch_type_baseline (already computed by data.py)
# Filter to fastball types, take highest-usage
_FASTBALL_TYPES = frozenset({"FF", "SI", "FC"})

def _identify_primary_fastball(pitch_type_baseline: pl.DataFrame) -> str | None:
    """Return the pitch_type code of the highest-usage fastball type.

    Returns None if pitcher throws no fastball-classified pitches.
    """
    fb_rows = pitch_type_baseline.filter(
        pl.col("pitch_type").is_in(_FASTBALL_TYPES)
    )
    if fb_rows.is_empty():
        return None
    return str(fb_rows.sort("n_pitches", descending=True)["pitch_type"][0])
```

### Computing Velocity Delta with Qualitative String
```python
def _compute_velo_delta(
    statcast: pl.DataFrame,
    window_game_dates: list,
    pitch_type: str,
) -> tuple[float, float, str]:
    """Compute season vs window avg velocity for a pitch type.

    Returns:
        (season_velo, window_velo, delta_string)
    """
    typed = statcast.filter(pl.col("pitch_type") == pitch_type)
    season_velo = typed["release_speed"].mean()

    window = typed.filter(pl.col("game_date").is_in(window_game_dates))
    window_velo = window["release_speed"].mean()

    delta = window_velo - season_velo
    delta_str = _velo_delta_string(delta, threshold=0.5)
    return season_velo, window_velo, delta_str
```

### Computing Usage Rates with Deltas
```python
def _compute_usage_rates(
    statcast: pl.DataFrame,
    window_game_dates: list,
) -> pl.DataFrame:
    """Compute pitch type usage rates for season and window."""
    # Season usage
    season_counts = statcast["pitch_type"].value_counts()
    season_total = len(statcast)
    season_usage = season_counts.with_columns(
        (pl.col("count") / season_total * 100).alias("season_pct")
    )

    # Window usage
    window = statcast.filter(pl.col("game_date").is_in(window_game_dates))
    window_counts = window["pitch_type"].value_counts()
    window_total = len(window)
    window_usage = window_counts.with_columns(
        (pl.col("count") / window_total * 100).alias("window_pct")
    )

    # Join and compute delta
    return season_usage.join(window_usage, on="pitch_type", how="outer_coalesce")
```

### Computing Velocity Arc (with Single-Inning Fallback)
```python
def _compute_velocity_arc(
    statcast: pl.DataFrame,
    game_pk: int,
    fastball_type: str,
) -> dict:
    """Compute early vs late inning velocity for a single game.

    Returns dict with early_velo, late_velo, drop_string, or fallback
    message if single-inning appearance.
    """
    game = statcast.filter(
        (pl.col("game_pk") == game_pk)
        & (pl.col("pitch_type") == fastball_type)
    )
    innings = game["inning"].unique().sort().to_list()

    if len(innings) < 2:
        return {
            "available": False,
            "note": "Single inning -- no velocity arc available",
        }

    # First 2 and last 2 innings (may overlap if only 2-3 innings)
    early_innings = innings[:2]
    late_innings = innings[-2:]
    early_velo = game.filter(pl.col("inning").is_in(early_innings))["release_speed"].mean()
    late_velo = game.filter(pl.col("inning").is_in(late_innings))["release_speed"].mean()
    drop = late_velo - early_velo  # negative = velocity dropped
    # ...
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_engine.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FB-01 | Season vs window fastball velocity with delta string | unit | `uv run pytest tests/test_engine.py::test_fastball_velocity_delta -x` | Wave 0 |
| FB-02 | P+/S+/L+ for primary fastball season vs window with delta | unit | `uv run pytest tests/test_engine.py::test_fastball_pplus_delta -x` | Wave 0 |
| FB-03 | Movement deltas (pfx_x/pfx_z) season vs window | unit | `uv run pytest tests/test_engine.py::test_fastball_movement_delta -x` | Wave 0 |
| FB-04 | Within-game velocity arc early vs late innings | unit | `uv run pytest tests/test_engine.py::test_velocity_arc -x` | Wave 0 |
| FB-04 | Velocity arc single-inning fallback | unit | `uv run pytest tests/test_engine.py::test_velocity_arc_single_inning -x` | Wave 0 |
| ARSL-01 | Usage rate per pitch type with delta vs season | unit | `uv run pytest tests/test_engine.py::test_usage_rate_deltas -x` | Wave 0 |
| ARSL-02 | P+/S+/L+ per pitch type season vs window | unit | `uv run pytest tests/test_engine.py::test_arsenal_pplus_deltas -x` | Wave 0 |
| ARSL-03 | Platoon mix shifts by batter handedness | unit | `uv run pytest tests/test_engine.py::test_platoon_mix_shifts -x` | Wave 0 |
| ARSL-04 | First-pitch weaponry analysis window vs season | unit | `uv run pytest tests/test_engine.py::test_first_pitch_weaponry -x` | Wave 0 |
| Edge | Small sample flagging (<10 pitches) | unit | `uv run pytest tests/test_engine.py::test_small_sample_flag -x` | Wave 0 |
| Edge | Cold start (window == full season) | unit | `uv run pytest tests/test_engine.py::test_cold_start_fallback -x` | Wave 0 |
| Edge | Pitcher with only 1 pitch type | unit | `uv run pytest tests/test_engine.py::test_single_pitch_type -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_engine.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- all engine tests (new file, covers FB-01 through ARSL-04 plus edge cases)
- No framework install needed -- pytest 9.0.2 already configured

## Data Inventory (Verified Against Real Data)

### Statcast Columns Used by Engine
| Column | Type | Purpose | Verified |
|--------|------|---------|----------|
| `pitch_type` | str | Pitch classification (FF, SI, FC, CH, ST, etc.) | Yes -- 4 types for test pitcher |
| `pitch_name` | str | Human-readable name ("Four-Seam Fastball") | Yes -- available in parquet |
| `release_speed` | f64 | Pitch velocity in mph | Yes -- typical values 87-95 |
| `pfx_x` | f64 | Horizontal movement (inches) | Yes -- available |
| `pfx_z` | f64 | Vertical movement (inches) | Yes -- available |
| `inning` | i64 | Inning number | Yes -- used for velocity arc |
| `pitch_number` | i64 | Pitch number within plate appearance | Yes -- ==1 for first pitch of AB |
| `stand` | str | Batter handedness (L/R) | Yes -- maps to platoon_matchup |
| `game_pk` | i64 | Game ID | Yes -- links to appearances |
| `game_date` | date | Game date | Yes -- used for window filtering |
| `p_throws` | str | Pitcher handedness (L/R) | Yes -- needed for platoon mapping |

### P+ CSV Columns Used by Engine
| Column | Type | CSVs | Purpose |
|--------|------|------|---------|
| `P+` | f64 | all | Pitching+ overall grade (100=average) |
| `S+` | f64 | all | Stuff+ grade |
| `L+` | f64 | all | Location+ grade |
| `n_pitches` | i64 | all | Pitch count (used as weight) |
| `pitch_type` | str | _type, _type_appearance, _type_platoon* | Pitch classification |
| `platoon_matchup` | str | _platoon, _platoon_appearance | "same" or "opposite" |
| `game_date` | date | _appearance variants | For window filtering |
| `game_type` | str | season-level CSVs | S/C/R splits (need weighted average) |

### Key Data Characteristics (from test pitcher Booser, 592155)
- **Pitcher:** Left-handed (L), 12 appearances, 173 total pitches
- **Arsenal:** FC (77), FF (48), CH (26), ST (22) -- FC is primary fastball (highest usage among FB types)
- **Appearances:** 11 RP + 1 SP, all single-inning outings
- **Window (30d):** 11 of 12 appearances fall in window
- **First pitches:** 42 total (one per at-bat faced), FC dominates (25/42 = 59.5%)
- **Platoon:** 105 vs RHB (opposite), 68 vs LHB (same) -- CH exclusively opposite-side
- **Edge case:** All appearances are single-inning, so velocity arc always falls back to "no arc"

### Platoon Mapping (Verified)
- For LHP: stand=L -> "same", stand=R -> "opposite"
- For RHP: stand=R -> "same", stand=L -> "opposite"
- P+ `platoon_matchup` values are exactly `"same"` and `"opposite"` (not "L"/"R")
- P+ platoon season data has game_type splits -- must use n_pitches-weighted averaging (same as all other baselines)

## Design Decisions (Discretion Areas)

### Dataclass Field Naming Convention
**Recommendation:** Use descriptive names with the grain prefix and suffix pattern:
- `season_velo`, `window_velo`, `velo_delta` (the qualitative string)
- `season_p_plus`, `window_p_plus`, `p_plus_delta`
- Use `_str` suffix only when a field has both numeric and string versions

### Pitch Type Ordering
**Recommendation:** Order by season usage (descending). This puts the most important pitch first, which is natural for both human readers and LLM consumption.

### Single Pitch Type Pitchers
**Recommendation:** 13 pitchers in the dataset throw only 1 pitch type. For these:
- Arsenal analysis returns a list with 1 entry
- Platoon analysis still applies (they may change usage of their one pitch by handedness)
- First-pitch analysis is trivial (100% one type) -- note this explicitly
- Skip usage delta computation (meaningless with 1 type)

### Cold Start Strategy
**Recommendation:** When `len(window_appearances) >= len(appearances)` (window covers most/all of season):
- Still compute season stats
- Set all delta strings to "Full season in window -- no trend comparison"
- Flag `cold_start: bool = True` on the output dataclass

## Open Questions

1. **How should the most recent appearance be selected for velocity arc?**
   - What we know: Decision says "within-game velocity arc" but does not specify which game. Most recent appearance is the natural choice.
   - What's unclear: Should velocity arc be computed for ALL window appearances or just the most recent?
   - Recommendation: Most recent appearance only (the arc shows "how did he hold velocity in his last outing"). If it is a single-inning outing, report the fallback string.

2. **Threshold for "sharply" in delta vocabulary**
   - What we know: Decision specifies "Down sharply (-3.1)" as an example but does not define the cutoff between normal and sharp.
   - What's unclear: At what magnitude does "Down 1.5 mph" become "Down sharply"?
   - Recommendation: Use 2.0 mph as the "sharply" threshold for velocity (2+ mph is a meaningful velo change). For P+, use 10 points. For usage rate, use 10 percentage points.

3. **P+ platoon baseline computation**
   - What we know: `compute_pitch_type_baseline` in data.py combines game_type rows for pitch_type. There is no equivalent for pitch_type_platoon.
   - What's unclear: Should the engine call `compute_pitch_type_baseline`-style weighting on the platoon data, or use the raw pitcher_type_platoon CSV?
   - Recommendation: Build a small helper (or generalize the existing pattern) to compute n_pitches-weighted platoon baselines from `pitcher_type_platoon`. The raw CSV has game_type splits that need combining.

## Sources

### Primary (HIGH confidence)
- Verified all Statcast column names and types against `statcast_2026.parquet` directly
- Verified all P+ CSV column names against actual CSV files in `aggs/` directory
- Verified pitch_number == 1 correctly identifies first pitches (42 first pitches = 42 at-bats for test pitcher)
- Verified platoon_matchup mapping (same/opposite) against Statcast stand values
- Verified game_type splits exist in P+ season data and require weighted averaging
- Verified all single-inning appearances for test pitcher (edge case is real)
- Verified 412 single-appearance pitchers (cold start is real)
- Verified 13 single-pitch-type pitchers (edge case is real)

### Secondary (MEDIUM confidence)
- Velocity "sharply" threshold of 2.0 mph is based on general baseball analytics convention (1+ mph is notable, 2+ is significant)
- P+ scale: 100 is average, above is better -- standard Pitching+ definition

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, polars patterns proven in Phase 1
- Architecture: HIGH -- follows established data.py patterns, clear composable function structure
- Pitfalls: HIGH -- all edge cases verified against real data (single-inning, cold start, platoon sparsity, game_type splits)

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (stable domain, static data files)
