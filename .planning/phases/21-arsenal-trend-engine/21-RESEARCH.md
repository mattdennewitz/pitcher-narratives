# Phase 21: Arsenal Trend Engine - Research

**Researched:** 2026-04-03
**Domain:** Per-pitch-type year-over-year arsenal analysis (added/dropped/changed pitches)
**Confidence:** HIGH

## Summary

Phase 21 extends the cross-season analysis from pitcher-level (Phase 20) down to per-pitch-type granularity. The engine identifies pitches a pitcher added, dropped, or significantly changed between seasons, and computes YoY deltas for usage rate, P+, S+, and velocity on pitches present in both seasons. This is the pitch-type counterpart to `CrossSeasonSummary`.

All input data is already available from Phase 19: `PitcherData.pitch_type_baseline` (current season, one row per pitch_type with columns `pitch_type`, `n_pitches`, `usage_pct`, `P+`, `S+`, and all metric columns) and `PitcherData.prior_pitch_type_baseline` (prior season, same schema). The `_MIN_PITCHES = 10` threshold constant, all three delta string functions (`_velo_delta_string`, `_pplus_delta_string`, `_usage_delta_string`), and the `_safe_metric` helper are already implemented in engine.py. The frozen-dataclass + `compute_*()` function pattern is well-established. Velocity per pitch type per season requires computing from statcast `release_speed` grouped by `game_year` and `pitch_type`, following the same approach used in `compute_arsenal_summary`.

The implementation is straightforward: join current and prior pitch_type_baselines on `pitch_type`, apply the minimum-pitch threshold to classify pitches as added/dropped/changed, compute deltas for changed pitches, and return `None` when `prior_pitch_type_baseline.is_empty()`.

**Primary recommendation:** Add an `ArsenalTrend` dataclass (with nested `PitchTypeChange` records), a `compute_arsenal_trend(data: PitcherData) -> ArsenalTrend | None` function to `engine.py`, and matching tests. Return `None` when `data.prior_pitch_type_baseline.is_empty()`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Minimum-pitch threshold for added/dropped: reuse existing `_MIN_PITCHES = 10` constant (consistency with per-type analysis)
- A pitch type is "added" if present in current season with >= _MIN_PITCHES but absent or below threshold in prior season
- A pitch type is "dropped" if present in prior season with >= _MIN_PITCHES but absent or below threshold in current season
- "Changed" means present in both seasons with >= _MIN_PITCHES each
- Output is a dataclass with lists of added/dropped pitch type names, plus a list of per-pitch-type change records
- Each change record: pitch_type, usage_delta_str, pplus_delta_str, splus_delta_str, velo_delta_str
- Matches CrossSeasonSummary pattern from Phase 20
- Reuse `_pplus_delta_string` for P+/S+ deltas (same thresholds as within-season)
- Reuse `_usage_delta_string` for usage rate deltas
- Reuse `_velo_delta_string` for velocity deltas
- Consistent with SDLT-02 language decision from Phase 20
- Arsenal trend output is None when pitcher has only one season of data (ATRN-03)
- Returns None when `prior_pitch_type_baseline.is_empty()`

### Claude's Discretion
- Exact dataclass and field naming
- Helper function organization
- Whether to include raw numeric deltas alongside qualitative strings

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ATRN-01 | Engine identifies pitches added (present in current season, absent in prior) and dropped (present in prior, absent in current) using a minimum-pitch threshold | `pitch_type_baseline` and `prior_pitch_type_baseline` DataFrames both have `pitch_type` and `n_pitches` columns. Filter each to `n_pitches >= _MIN_PITCHES`, then set-difference the pitch_type lists. `_MIN_PITCHES = 10` already defined at engine.py:92. |
| ATRN-02 | Engine computes per-pitch-type YoY deltas for usage rate, P+, S+, and velocity for pitches present in both seasons | `usage_pct` computed by `compute_pitch_type_baseline` (data.py:380-382). `P+` and `S+` are direct columns. Velocity per pitch_type per season computed from statcast `release_speed` grouped by `game_year` and `pitch_type` (same approach as `compute_arsenal_summary` at engine.py:1520). Delta functions: `_usage_delta_string`, `_pplus_delta_string`, `_velo_delta_string` all available. |
| ATRN-03 | Arsenal trend output is None when pitcher has only one season of data | `prior_pitch_type_baseline.is_empty()` guard, same pattern as `compute_cross_season_summary` (engine.py:2164). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame operations for pitch_type_baseline comparison | Already used throughout engine.py and data.py |
| dataclasses (stdlib) | 3.14 | Output types | Matches all existing engine output types |
| pytest | (installed) | Test framework | Already configured in pyproject.toml |

No new dependencies needed. This phase uses only existing libraries.

## Architecture Patterns

### Recommended Project Structure
```
src/pitcher_narratives/
  engine.py          # ADD: ArsenalTrend, PitchTypeChange, compute_arsenal_trend()
  data.py            # NO CHANGES
  context.py         # NO CHANGES THIS PHASE (Phase 22 will consume)

tests/
  test_engine.py     # ADD: arsenal trend tests
```

### Pattern 1: Dataclass Output from Engine Compute Function
**What:** Every engine analysis facet follows: a `@dataclass` for the output shape, and a `compute_*()` function that takes `PitcherData` and returns the dataclass (or `None`).
**When to use:** Always -- this is the established pattern in engine.py.
**Example (from Phase 20):**
```python
# Source: engine.py:1106-1144
@dataclass
class CrossSeasonSummary:
    """Year-over-year pitcher-level metric deltas."""
    current_season: int
    prior_season: int
    current_velo: float
    prior_velo: float
    velo_delta: str
    # ... etc

def compute_cross_season_summary(data: PitcherData) -> CrossSeasonSummary | None:
    if data.prior_season_baseline.is_empty():
        return None
    # ... compute and return
```

### Pattern 2: Minimum-Pitch Threshold for Validity
**What:** Pitch types with fewer than `_MIN_PITCHES` (10) are considered insufficient data.
**When to use:** When deciding whether a pitch type "exists" in a season for classification purposes.
**How it applies here:** A pitch type is "present" in a season only if `n_pitches >= _MIN_PITCHES` in the pitch_type_baseline for that season.

### Pattern 3: Set-Based Added/Dropped Detection
**What:** Compare the set of pitch types meeting the threshold in current vs prior season.
**Implementation:**
```python
# Filter baselines to pitch types with enough data
current_types = set(
    current_baseline.filter(pl.col("n_pitches") >= _MIN_PITCHES)["pitch_type"].to_list()
)
prior_types = set(
    prior_baseline.filter(pl.col("n_pitches") >= _MIN_PITCHES)["pitch_type"].to_list()
)

added = current_types - prior_types      # ATRN-01: present now, absent before
dropped = prior_types - current_types    # ATRN-01: absent now, present before
changed = current_types & prior_types    # ATRN-02: present in both
```

### Pattern 4: Velocity from Statcast, Not CSV Baselines
**What:** The pitcher_type CSV has P+/S+ but no velocity column. Per-pitch-type velocity must be computed from statcast `release_speed`.
**When to use:** Any time velocity is needed at the pitch-type level.
**Example (from `compute_arsenal_summary` at engine.py:1520):**
```python
# Per-pitch-type velocity from statcast
season_velo = _float(pt_season["release_speed"].mean())
```
**For cross-season:** Group statcast by `game_year` and `pitch_type`, compute mean `release_speed` for each combination.

### Anti-Patterns to Avoid
- **Fabricating trends for single-season pitchers:** Always guard with `if data.prior_pitch_type_baseline.is_empty(): return None`.
- **Using CSV velocity columns:** The pitcher_type CSV does not have a velocity column. Always compute from statcast.
- **Comparing below-threshold pitch types:** A pitch_type with 3 pitches in the prior season and 50 in the current season is "added," not "changed." Apply `_MIN_PITCHES` threshold before classification.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Qualitative velocity deltas | Custom string formatting | `_velo_delta_string(delta)` at engine.py:378 | Consistency with all other velocity deltas in the system |
| Qualitative P+/S+ deltas | Custom string formatting | `_pplus_delta_string(delta)` at engine.py:397 | Same thresholds (5/10 points) used everywhere |
| Qualitative usage deltas | Custom string formatting | `_usage_delta_string(delta)` at engine.py:416 | Same thresholds (5/10 pp) used everywhere |
| Safe metric extraction | Manual None/empty checks | `_safe_metric(df, col)` at engine.py:454 | Handles empty DataFrames and missing columns |
| Pitch name lookup | Manual mapping | `_build_name_map(data.statcast)` at engine.py:579 | Established pattern for pitch_type -> pitch_name |

**Key insight:** All delta string functions and helper utilities already exist. The arsenal trend engine is primarily composition of existing helpers applied to per-pitch-type cross-season data.

## Common Pitfalls

### Pitfall 1: Threshold Boundary for Added/Dropped
**What goes wrong:** Using `n_pitches > _MIN_PITCHES` instead of `n_pitches >= _MIN_PITCHES`, or comparing raw presence (any n_pitches) instead of threshold presence.
**Why it happens:** The constant name suggests a minimum, but the boundary condition matters.
**How to avoid:** Use `n_pitches >= _MIN_PITCHES` consistently, matching how `small_sample` is checked elsewhere (engine.py:1538 uses `n_window < _MIN_PITCHES`).
**Warning signs:** Tests pass for obvious cases but edge cases with exactly 10 pitches misclassify.

### Pitfall 2: Velocity Computation for Missing Pitch Types
**What goes wrong:** Trying to compute velocity delta for a pitch type that has zero rows in one season's statcast data.
**Why it happens:** A "changed" pitch type has baseline rows in both seasons, but statcast could theoretically be missing (unlikely but possible with data issues).
**How to avoid:** Always guard velocity computation: `if pt_statcast.is_empty(): velo_delta = "No velocity data"` or handle gracefully.
**Warning signs:** ZeroDivisionError or NaN in velocity delta strings.

### Pitfall 3: Usage Percentage Source Mismatch
**What goes wrong:** Computing usage_pct from statcast pitch counts (like `compute_arsenal_summary` does for within-season) vs using the `usage_pct` column already in `pitch_type_baseline`.
**Why it happens:** The existing arsenal summary computes usage from statcast for window vs season comparison. For YoY, the natural source is the pre-computed `usage_pct` in each season's baseline.
**How to avoid:** Use `usage_pct` from `pitch_type_baseline` and `prior_pitch_type_baseline` -- it is already computed by `compute_pitch_type_baseline` in data.py:380-382. This is the correct source for season-level usage comparison.
**Warning signs:** Slightly different usage percentages due to filtering differences between statcast and CSV aggregations.

### Pitfall 4: Multiple Prior Seasons in prior_pitch_type_baseline
**What goes wrong:** The `prior_pitch_type_baseline` may contain rows from multiple prior seasons if 3+ years of data exist (though currently only 2 years exist).
**Why it happens:** `load_pitcher_data` filters `prior_pitch_type_baseline` to `season < max_season`, which could include multiple seasons.
**How to avoid:** When extracting prior-season data, filter to `max(prior seasons)` only, matching how `compute_cross_season_summary` does it (engine.py:2169-2170).
**Warning signs:** Duplicate pitch_type rows in prior baseline, incorrect delta computation.

## Code Examples

### Complete compute_arsenal_trend Skeleton
```python
# Source: extrapolated from engine.py patterns

@dataclass
class PitchTypeChange:
    """Per-pitch-type YoY delta for a pitch present in both seasons."""
    pitch_type: str
    pitch_name: str
    usage_delta_str: str
    pplus_delta_str: str
    splus_delta_str: str
    velo_delta_str: str

@dataclass
class ArsenalTrend:
    """Year-over-year arsenal changes at the pitch-type level.

    Produced by compute_arsenal_trend(). None when the pitcher
    has only one season of data.
    """
    current_season: int
    prior_season: int
    added: list[str]       # Pitch type codes added
    dropped: list[str]     # Pitch type codes dropped
    changes: list[PitchTypeChange]  # Per-pitch-type deltas


def compute_arsenal_trend(data: PitcherData) -> ArsenalTrend | None:
    if data.prior_pitch_type_baseline.is_empty():
        return None

    # Extract season years
    current_season = int(data.pitch_type_baseline["season"].unique()[0])
    prior_seasons = data.prior_pitch_type_baseline["season"].unique().to_list()
    prior_season = int(max(prior_seasons))

    # Filter prior to most recent prior season only
    prior_baseline = data.prior_pitch_type_baseline.filter(
        pl.col("season") == prior_season
    )

    # Threshold-qualified pitch type sets
    current_qualified = set(
        data.pitch_type_baseline
        .filter(pl.col("n_pitches") >= _MIN_PITCHES)["pitch_type"].to_list()
    )
    prior_qualified = set(
        prior_baseline
        .filter(pl.col("n_pitches") >= _MIN_PITCHES)["pitch_type"].to_list()
    )

    added = sorted(current_qualified - prior_qualified)
    dropped = sorted(prior_qualified - current_qualified)
    changed = sorted(current_qualified & prior_qualified)

    # Per-pitch-type velocity from statcast
    velo_lookup = _per_pitch_type_season_velo(data.statcast)

    # Build change records
    changes = []
    for pt in changed:
        # usage_pct from baselines
        current_row = data.pitch_type_baseline.filter(pl.col("pitch_type") == pt)
        prior_row = prior_baseline.filter(pl.col("pitch_type") == pt)

        current_usage = _safe_metric(current_row, "usage_pct")
        prior_usage = _safe_metric(prior_row, "usage_pct")
        usage_delta = _usage_delta_string(current_usage - prior_usage)

        # P+ / S+ from baselines
        current_p = _safe_metric(current_row, "P+")
        prior_p = _safe_metric(prior_row, "P+")
        pplus_delta = _pplus_delta_string(current_p - prior_p)

        current_s = _safe_metric(current_row, "S+")
        prior_s = _safe_metric(prior_row, "S+")
        splus_delta = _pplus_delta_string(current_s - prior_s)

        # Velocity from statcast
        current_velo = velo_lookup.get((current_season, pt), 0.0)
        prior_velo = velo_lookup.get((prior_season, pt), 0.0)
        velo_delta = _velo_delta_string(current_velo - prior_velo)

        changes.append(PitchTypeChange(
            pitch_type=pt,
            pitch_name=name_map.get(pt, pt),
            usage_delta_str=usage_delta,
            pplus_delta_str=pplus_delta,
            splus_delta_str=splus_delta,
            velo_delta_str=velo_delta,
        ))

    return ArsenalTrend(
        current_season=current_season,
        prior_season=prior_season,
        added=added,
        dropped=dropped,
        changes=changes,
    )
```

### Helper: Per-Pitch-Type Season Velocity
```python
# New helper needed -- extends _per_season_velo to pitch_type granularity
def _per_pitch_type_season_velo(statcast: pl.DataFrame) -> dict[tuple[int, str], float]:
    """Compute mean velocity per season per pitch_type from statcast release_speed.

    Returns dict keyed by (game_year, pitch_type) -> mean velocity.
    """
    if statcast.is_empty() or "release_speed" not in statcast.columns:
        return {}
    result = statcast.group_by(["game_year", "pitch_type"]).agg(
        pl.col("release_speed").mean().alias("avg_velo")
    )
    return {
        (int(row["game_year"]), str(row["pitch_type"])): float(row["avg_velo"])
        for row in result.iter_rows(named=True)
    }
```

### Test Data Pattern for Multi-Pitch-Type Cross-Season
```python
# Extends _create_cross_season_pitcher_data to include multiple pitch types
# with different scenarios: changed, added, dropped

# Year 2025: FF (100 pitches), SL (80 pitches), CH (50 pitches)
# Year 2026: FF (100 pitches), SL (80 pitches), CU (60 pitches)
# Result: FF and SL are "changed", CH is "dropped", CU is "added"

# Also test below-threshold: add a pitch type with 5 pitches (<10)
# to verify it is NOT classified as "present"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-season analysis only | Phase 19 exposed prior-season baselines | v1.8 Phase 19 | Enables all cross-season analysis |
| Pitcher-level YoY only | Phase 20 added CrossSeasonSummary | v1.8 Phase 20 | Phase 21 extends to pitch-type level |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed via uv) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_engine.py -x -q -k arsenal_trend` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ATRN-01 | Identifies added/dropped pitches by threshold | unit | `uv run pytest tests/test_engine.py -x -q -k "test_arsenal_trend_added_dropped"` | Wave 0 |
| ATRN-01 | Below-threshold pitch not classified as present | unit | `uv run pytest tests/test_engine.py -x -q -k "test_arsenal_trend_below_threshold"` | Wave 0 |
| ATRN-02 | Per-pitch-type YoY deltas for usage, P+, S+, velo | unit | `uv run pytest tests/test_engine.py -x -q -k "test_arsenal_trend_change_deltas"` | Wave 0 |
| ATRN-02 | Delta strings use same format as within-season | unit | `uv run pytest tests/test_engine.py -x -q -k "test_arsenal_trend_delta_format"` | Wave 0 |
| ATRN-03 | Returns None for single-season pitcher | unit | `uv run pytest tests/test_engine.py -x -q -k "test_arsenal_trend_none_single_season"` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_engine.py -x -q -k arsenal_trend`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- add arsenal trend test section with `_create_multi_pitch_type_cross_season_data` helper
- Framework install: not needed -- pytest already installed and 325 tests pass

## Open Questions

1. **Whether to include raw numeric deltas alongside qualitative strings (discretionary)**
   - What we know: CrossSeasonSummary includes both (e.g., `current_p_plus` and `p_plus_delta` string). PitchTypeChange in CONTEXT.md only specifies qualitative strings.
   - What's unclear: Whether Phase 22 context assembly will need raw numbers for formatting.
   - Recommendation: Include raw numeric values (current/prior for usage_pct, P+, S+, velo) alongside qualitative strings, matching CrossSeasonSummary pattern. This gives Phase 22 maximum flexibility for prompt rendering at minimal cost. The dataclass fields are cheap; missing them would require a Phase 22 rework.

2. **Sort order of the changes list**
   - What we know: Arsenal summary sorts by `season_usage_pct` descending.
   - Recommendation: Sort changes by current-season `usage_pct` descending (highest-usage pitches first), matching the arsenal summary convention.

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python, polars, pydantic-ai, Claude -- no new dependencies
- **Data format:** Static parquet + CSV files, no live API calls
- **Python version:** 3.14+
- **Naming:** snake_case for functions/variables, PascalCase for classes
- **Testing:** Use pytest, synthetic data (not real MLB data)
- **Code style:** Google-style docstrings, type hints on all function signatures
- **Module design:** Use `__all__` for public APIs, prefix internal helpers with `_`
- **Error handling:** Specific exception types, handle `pl.exceptions.ComputeError`

## Sources

### Primary (HIGH confidence)
- `src/pitcher_narratives/engine.py` -- Direct code inspection of CrossSeasonSummary (lines 1106-1144), compute_cross_season_summary (lines 2149-2218), delta string functions (lines 378-432), _MIN_PITCHES (line 92), _safe_metric (lines 454-458)
- `src/pitcher_narratives/data.py` -- Direct code inspection of PitcherData (lines 71-94), compute_pitch_type_baseline (lines 349-382), load_pitcher_data (lines 406-470)
- `tests/test_engine.py` -- Direct code inspection of _create_cross_season_pitcher_data (lines 1090-1180), cross-season test patterns (lines 1188-1272)
- `.planning/phases/20-season-delta-engine/20-01-PLAN.md` -- Phase 20 plan structure and patterns
- `.planning/phases/21-arsenal-trend-engine/21-CONTEXT.md` -- User decisions for Phase 21
- `aggs/2025-pitcher_type.csv` -- Column headers confirming P+, S+ column names (no velocity column)

### Secondary (MEDIUM confidence)
- Phase 20 research document -- architectural patterns and testing approach

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing
- Architecture: HIGH -- direct extension of established Phase 20 pattern
- Pitfalls: HIGH -- identified from direct code inspection of edge cases
- Code examples: HIGH -- derived from existing codebase patterns, not hypothetical

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable -- internal codebase patterns, no external API changes)
