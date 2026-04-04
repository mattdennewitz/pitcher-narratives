# Phase 23: Engine Foundation & Data Enrichment - Research

**Researched:** 2026-04-04
**Domain:** Python/Polars computation engine, baseball analytics (count states, arm angle, percentile ranking)
**Confidence:** HIGH

## Summary

Phase 23 adds three new computation capabilities to the existing engine: count-state usage splits, per-pitch-type arm angle metrics, and percentile-ranked outlier tags. The codebase is mature (3,400 lines in engine.py, 741 in context.py, 113 passing tests) with well-established patterns for adding new computations: Polars-based aggregation, Python dataclasses for output models, qualitative delta strings for window-vs-season comparisons, and prompt rendering via PitcherContext.to_prompt().

All five requirements (ENG-01 through ENG-05) are achievable within the existing architecture. The Statcast parquet contains `balls`, `strikes`, `release_pos_x`, `release_pos_z`, and `p_throws` columns needed for all computations. No new dependencies are required. The main technical risk is the arm angle slot thresholds in D-06 -- raw atan2(release_z, abs(release_x)) produces angles from ~21-90 degrees (mean 71.8), making the CONTEXT.md thresholds (Overhand >50, 3/4 35-50, Sidearm 15-35, Submarine <15) functionally useless (99% classified as "Overhand"). Corrected thresholds are recommended below under Claude's discretion.

**Primary recommendation:** Follow the existing engine pattern (compute function + dataclass + delta string + PitcherContext field + to_prompt rendering) for each of the three new features. Implement count splits first (most complex, most lines), then arm angle (depends on existing release point data), then percentile tags (surgical change to outlier_tag + LeagueBaseline extension).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Standard sabermetric buckets: Ahead (strikes > balls), Behind (balls > strikes), Even (balls == strikes), Two-strike (any count with 2 strikes). Two-strike overlaps with other buckets -- a pitch can appear in both its primary bucket and two-strike.
- **D-02:** Separate first-pitch (0-0) tracking as a 5th bucket dimension, in addition to 0-0 appearing in the Even bucket. Five total buckets: ahead, behind, even, two_strike, first_pitch.
- **D-03:** Small sample threshold (<10 pitches) suppresses the delta only, not the entire bucket. Raw usage rates still shown with a "small sample" flag.
- **D-04:** Bucket-level threshold only -- no per-pitch-type inner threshold. All pitch type rates shown regardless of individual count within a bucket, as long as the bucket total >= 10.
- **D-05:** Arm angle computed per pitch type (not a single aggregate per appearance). Uses atan2 on existing per-type release_x/release_z averages already in PitchTypeSummary.
- **D-06:** Arm angle includes both numeric degrees and a human-readable slot label. Slot ranges: Overhand (>50), 3/4 (35-50), Sidearm (15-35), Submarine (<15). **NOTE: These thresholds are wrong for atan2(z, |x|) -- see Architecture Patterns for corrected values under Claude's discretion.**
- **D-07:** Window-vs-season delta string computed per pitch type for arm angle, following the existing delta string pattern.
- **D-07a:** Phase 23 uses raw atan2(release_z, abs(release_x)) -- no height normalization.
- **D-08:** Outlier tags include percentile rank, direction, AND z-score (all three). Format: `OUTLIER - 98th percentile (above avg, z=+2.3)` / `NORMAL - 65th percentile (z=+0.4)`.
- **D-09:** Percentile computed split by pitcher handedness (LHP vs RHP), not full-league.
- **D-10:** Hybrid rendering: notable shifts (10+ pp from season average) in the main context section, full usage table in a raw data appendix.
- **D-11:** Notable shift threshold is 10 percentage points.
- **D-12:** LeagueBaseline must be extended with release point physical averages and standard deviations: `avg_release_x`, `release_x_std`, `avg_release_z`, `release_z_std`, `avg_extension`, `extension_std`.
- **D-13:** CountSplits summary (10pp shifts) MUST render directly adjacent to PlatoonMix in the prompt -- not separated by release point or other data.

### Claude's Discretion
- Slot label boundary fine-tuning (exact degree thresholds)
- CountSplits Pydantic model field naming and structure
- How arm angle fields attach to PitchTypeSummary vs a separate model
- League baseline handedness grouping implementation details
- Extension column availability check (avg_extension/extension_std may need graceful fallback if column missing from some datasets)

### Deferred Ideas (OUT OF SCOPE)
- **Height-normalized arm angle** -- Normalize release_z against pitcher height to isolate arm slot from stature. Deferred to Phase 25.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-01 | Engine computes per-pitch-type usage across count states (ahead/behind/even/two-strike) with window vs season deltas | Statcast has `balls` and `strikes` Int64 columns; bucket definitions confirmed against data (176K pitches); existing _usage_delta_string pattern for deltas |
| ENG-02 | Engine computes arm angle from release_x/release_z via atan2, with window vs season delta strings | Statcast has `release_pos_x`/`release_pos_z` Float64 columns; existing ReleasePointPitchType already computes per-type window/season averages; atan2 math verified; slot thresholds corrected |
| ENG-03 | Outlier tags include percentile rank instead of raw z-score notation | Current `outlier_tag()` at engine.py:294 has simple z-score format; needs extension to accept handedness and compute percentile against league population; `p_throws` column available; no scipy needed (manual percentile like `_compute_xrv100_percentile`) |
| ENG-04 | CountSplits and arm angle fields wired into PitcherContext and rendered in prompt output | PitcherContext is a Pydantic BaseModel at context.py:52; assemble_pitcher_context at context.py:692 orchestrates compute calls; to_prompt() at context.py:91 renders sections; D-13 requires count splits adjacent to platoon section |
| ENG-05 | Count bucket with fewer than 10 pitches flagged as small sample (no usage delta computed) | Existing `_MIN_PITCHES = 10` constant at engine.py:99 and `small_sample` bool pattern used throughout (PitchTypeSummary, ReleasePointPitchType, HardHitRate) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python, polars, pydantic-ai, Claude -- already in pyproject.toml
- **Python version:** 3.14+
- **Data format:** Static parquet + CSV files, no live API calls
- **Naming:** snake_case for modules/functions/variables, PascalCase for classes, UPPER_SNAKE_CASE for constants
- **Code style:** ruff for formatting (line-length 110), Google-style docstrings, type hints on all signatures
- **Error handling:** Specific exception types, handle `pl.exceptions.ComputeError` for Polars
- **Modules:** Use `__all__` for public APIs, prefix internal helpers with `_`
- **Testing:** pytest >= 9.0.2, testpaths = `tests/`
- **GSD workflow:** Use entry points for file changes

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | DataFrame operations for count-state aggregation, release point analysis | Already used throughout engine.py for all computations |
| Python math | stdlib | `math.atan2`, `math.degrees` for arm angle | No external dependency needed |
| Python dataclasses | stdlib | Output model definitions (CountSplits, ArmAngle) | Existing pattern: all engine output models are `@dataclass` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.12.5 | PitcherContext model (BaseModel) | Only in context.py for the context assembly layer |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual percentile | scipy.stats.percentileofscore | scipy not installed; manual approach already used in _compute_xrv100_percentile |
| numpy atan2 | math.atan2 | numpy not needed for scalar operations; polars handles vectorized if needed |

No new dependencies needed. All computation uses polars (already installed) and Python stdlib math.

## Architecture Patterns

### Existing Engine Pattern (follow for all three features)

Every computation in engine.py follows this pattern:

1. **Dataclass** -- Define output model with typed fields, docstrings, and any flags (small_sample, cold_start)
2. **Compute function** -- `compute_X(data: PitcherData) -> X` that accepts PitcherData and returns the dataclass
3. **Delta string helper** -- `_X_delta_string(delta: float, threshold: float) -> str` for qualitative comparisons
4. **Constants** -- Module-level `_THRESHOLD` constants for delta string noise floors
5. **__all__ export** -- Add dataclass and compute function to module `__all__`
6. **PitcherContext field** -- Add field to PitcherContext BaseModel in context.py
7. **assemble_pitcher_context** -- Wire compute call in the orchestrator function
8. **to_prompt rendering** -- Add `_render_X_section()` private method to PitcherContext

### Count Splits Data Model (recommended structure)

```python
@dataclass
class CountBucketUsage:
    """Per-pitch-type usage rate within a single count-state bucket."""
    pitch_type: str
    pitch_name: str
    usage_pct: float
    """Usage as percentage of all pitches in this bucket."""

@dataclass
class CountBucket:
    """Usage breakdown for a single count state (ahead/behind/even/two_strike/first_pitch)."""
    bucket: str
    """One of: 'ahead', 'behind', 'even', 'two_strike', 'first_pitch'."""
    n_pitches_window: int
    n_pitches_season: int
    small_sample: bool
    """True when n_pitches_window < 10."""
    pitch_types: list[CountBucketUsage]
    """Per-pitch-type usage rates, sorted by usage descending."""
    season_pitch_types: list[CountBucketUsage]
    """Season-level usage rates for delta computation."""

@dataclass
class CountSplits:
    """Per-pitch-type usage across count states with window vs season deltas."""
    buckets: list[CountBucket]
    """Five buckets: ahead, behind, even, two_strike, first_pitch."""
    notable_shifts: list[str]
    """Pre-rendered strings for shifts >= 10pp, for inline rendering."""
```

### Arm Angle Model (recommended: add to ReleasePointPitchType)

Since arm angle is computed from the same release_x/release_z data already on ReleasePointPitchType, the most natural attachment is as additional fields on that existing dataclass:

```python
# Add to existing ReleasePointPitchType dataclass:
    window_arm_angle: float
    """Arm angle in degrees from horizontal, computed as atan2(release_z, |release_x|)."""
    season_arm_angle: float
    """Season average arm angle in degrees."""
    arm_angle_delta: str
    """Qualitative delta string for arm angle change."""
    arm_slot: str
    """Human-readable slot label: 'Overhand', 'High 3/4', 'Low 3/4', 'Sidearm', 'Submarine'."""
```

Alternative: a separate `ArmAngleEntry` dataclass -- cleaner separation but duplicates pitch_type/pitch_name fields and requires a separate compute function. Recommended approach: extend ReleasePointPitchType since the data source is identical.

### Corrected Arm Angle Slot Thresholds (Claude's discretion)

The CONTEXT.md D-06 thresholds are incorrect for `atan2(release_z, abs(release_x))`. Real data analysis (987 pitchers, 2026 Statcast):

| Percentile | Angle |
|-----------|-------|
| P1 | 48.0 |
| P5 | 57.6 |
| P10 | 61.3 |
| P25 | 66.9 |
| P50 (median) | 71.8 |
| P75 | 76.6 |
| P90 | 80.2 |
| P95 | 83.5 |

**Recommended slot thresholds:**

| Slot | Threshold | Distribution | Rationale |
|------|-----------|-------------|-----------|
| Overhand | >= 78 deg | ~19% of pitchers | ~P75 and above |
| High 3/4 | 65-78 deg | ~64% of pitchers | Bulk of the league |
| Low 3/4 | 55-65 deg | ~15% of pitchers | Below P25 but above sidearm |
| Sidearm | 40-55 deg | ~3% of pitchers | Rare, distinctive delivery |
| Submarine | < 40 deg | <1% of pitchers | Tyler Rogers territory |

These align with scouting convention: most MLB pitchers throw from a 3/4 slot, with true overhand and sidearm being the minority.

### Percentile Tag Architecture

The current `outlier_tag(value, avg, std)` function signature must change to include percentile. Two approaches:

**Recommended approach:** Add a `p_throws` parameter and compute percentile internally against the league population. This requires access to the full Statcast dataset within `outlier_tag()`, which violates the current "pure function" design.

**Better approach:** Pre-compute percentile externally and pass it in:

```python
def outlier_tag(value: float, avg: float, std: float, percentile: int | None = None) -> str:
    """Return OUTLIER or NORMAL tag with percentile rank.
    
    Args:
        value: Pitcher's metric value.
        avg: League average for this metric.
        std: League standard deviation.
        percentile: Pre-computed percentile (0-100). If None, percentile
            is omitted from the tag.
    """
    if std == 0:
        return "NORMAL"
    z = (value - avg) / std
    pctl_str = f"{percentile}th percentile " if percentile is not None else ""
    if abs(z) > 1.5:
        direction = "above" if z > 0 else "below"
        return f"OUTLIER - {pctl_str}({direction} avg, z={z:+.1f})"
    return f"NORMAL - {pctl_str}(z={z:+.1f})"
```

The percentile itself is computed with a helper similar to `_compute_xrv100_percentile()`, but against the Statcast parquet population grouped by `p_throws`. This keeps `outlier_tag` pure and testable.

### LeagueBaseline Extension for Release Point (D-12)

The `compute_league_baselines()` function at engine.py:195 already loads Statcast with specific columns. Extension requires:

1. Add `release_pos_x`, `release_pos_z`, `release_extension` to the `columns` list in the `load_all_statcast()` call
2. Add `.mean()` and `.std()` aggregations for each
3. Add 6 new fields to `LeagueBaseline` dataclass
4. Handle `release_extension` nulls gracefully (173,767/176,380 non-null -- 1.5% null rate)

**Handedness split (D-09):** The current `compute_league_baselines()` groups by `pitch_type` only. For handedness-split percentiles, add `p_throws` to the grouping. This changes the return type to include handedness -- recommend adding `p_throws` to LeagueBaseline and filtering at call sites. Since `outlier_tag` callers already know the pitcher's handedness (from `data.throws`), this is straightforward.

### Prompt Rendering Order (D-13)

Current `to_prompt()` section order in context.py:91-140:

```
1. Executive Summary
2. Role & Workload
3. Primary Fastball
4. Times Through Order
5. Arsenal
6. Appearance Pitch Trends
7. Execution
8. Model Internals
9. Release Point          <-- arm angle goes here (extends existing)
10. Contact Quality
11. Platoon Shifts         <-- count splits MUST go adjacent (D-13)
12. First-Pitch Tendencies
13. YoY Changes
14. Recent Appearances
```

Count splits should render immediately after Platoon Shifts (or immediately before, as long as adjacent). The appendix with full usage tables goes at the end, before Recent Appearances.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Percentile computation | Custom ranking algorithm | Pattern from `_compute_xrv100_percentile` (engine.py:1867) | Already handles edge cases (empty data, min_pitches threshold) |
| Delta strings | New formatting logic | Existing `_usage_delta_string` pattern | Consistent language across the prompt |
| Cold start handling | New special-case logic | Existing `_is_cold_start()` + `_COLD_START_STRING` pattern | Window=season detection already solved |
| Pitch type name mapping | Inline lookups | Existing `_build_name_map()` helper | Returns dict[pitch_type_code, human_name] |
| Window date filtering | Manual date arithmetic | Existing `_get_window_game_dates()` helper | Returns list of game dates in window |

**Key insight:** Every pattern needed for Phase 23 already exists in engine.py. The implementation is composition and extension, not invention.

## Common Pitfalls

### Pitfall 1: Arm Angle Slot Thresholds Using Wrong Scale
**What goes wrong:** Using the CONTEXT.md D-06 thresholds (Overhand >50) with atan2(z, |x|) classifies 99% of pitchers as "Overhand".
**Why it happens:** The thresholds appear to be written for a different angle measurement system (angle from vertical, or a different coordinate reference).
**How to avoid:** Use the empirically-derived thresholds from this research: Overhand >= 78, High 3/4 65-78, Low 3/4 55-65, Sidearm 40-55, Submarine < 40.
**Warning signs:** All pitchers getting the same slot label in output.

### Pitfall 2: Two-Strike Overlap Double-Counting in Usage Rates
**What goes wrong:** When computing usage percentages, a pitch at 0-2 appears in both "ahead" and "two_strike" buckets. If usage rates are computed as fraction of ALL pitches, the percentages won't sum to 100% across the primary buckets.
**Why it happens:** Two-strike is an overlapping dimension per D-01.
**How to avoid:** Compute usage_pct as fraction of pitches *within that bucket*, not across all buckets. Each bucket independently sums to 100% across pitch types. Document the overlap in prompt text so the LLM understands.
**Warning signs:** Usage percentages that don't add to ~100% within a bucket.

### Pitfall 3: League Baseline Cache Invalidation with Handedness Split
**What goes wrong:** The current `compute_league_baselines()` uses a module-level cache (`_league_baselines_cache`). If extended to split by handedness, the cache structure changes and old callers may break.
**Why it happens:** Cache returns `list[LeagueBaseline]` -- adding handedness means the list now has ~2x entries.
**How to avoid:** Either (a) add `p_throws` as a field on LeagueBaseline and let callers filter, or (b) change cache to `dict[str, list[LeagueBaseline]]` keyed by handedness. Option (a) is simpler and backward-compatible -- callers that don't care about handedness can ignore the field.
**Warning signs:** Tests failing because baseline lookup returns None for pitch types that previously worked.

### Pitfall 4: Count Splits Prompt Rendering Separated from Platoon
**What goes wrong:** Count splits rendered far from Platoon Shifts in the prompt, breaking the causal analysis capability (D-13).
**Why it happens:** Adding a new section at the end of to_prompt() instead of adjacent to the platoon section.
**How to avoid:** Insert `_render_count_splits_section()` call immediately after `_render_platoon_section()` in to_prompt(). Verify by checking rendered output.
**Warning signs:** More than ~200 tokens between platoon and count-split sections in rendered output.

### Pitfall 5: Small Sample Flag Applied to Bucket Total vs Per-Pitch-Type
**What goes wrong:** Flagging small_sample per pitch type within a bucket, when D-04 specifies bucket-level threshold only.
**Why it happens:** Natural instinct to apply _MIN_PITCHES at the most granular level.
**How to avoid:** Check `bucket.n_pitches_window >= 10` for the entire bucket, not per pitch type within the bucket. All pitch type rates shown if bucket total meets threshold.
**Warning signs:** Buckets showing "small sample" when total pitches in the bucket is well above 10.

### Pitfall 6: outlier_tag Backward Compatibility
**What goes wrong:** Changing outlier_tag's signature breaks existing callers (pipeline.py, report.py) that pass positional args.
**Why it happens:** Adding required parameters to the function.
**How to avoid:** Make `percentile` parameter optional with default `None`. When None, omit percentile from the tag but keep the rest of the format. This way existing callers continue to work until they're updated.
**Warning signs:** Import errors or unexpected tag format in existing tests.

## Code Examples

### Count State Bucket Classification (verified pattern from Statcast schema)

```python
# Source: Verified against Statcast parquet schema (balls: Int64, strikes: Int64)
_COUNT_BUCKETS = {
    "ahead": pl.col("strikes") > pl.col("balls"),
    "behind": pl.col("balls") > pl.col("strikes"),
    "even": pl.col("balls") == pl.col("strikes"),
    "two_strike": pl.col("strikes") == 2,
    "first_pitch": (pl.col("balls") == 0) & (pl.col("strikes") == 0),
}
```

### Arm Angle Computation (verified with real data)

```python
# Source: Verified against 987 pitchers in 2026 Statcast
import math

def _compute_arm_angle(release_x: float, release_z: float) -> float:
    """Compute arm angle in degrees from release point coordinates.
    
    Uses atan2(release_z, abs(release_x)) to measure angle from horizontal.
    Higher values = more overhand delivery.
    abs(release_x) ensures same scale for LHP and RHP.
    """
    return math.degrees(math.atan2(release_z, abs(release_x)))

def _arm_slot_label(angle: float) -> str:
    """Map arm angle degrees to human-readable slot label."""
    if angle >= 78:
        return "Overhand"
    elif angle >= 65:
        return "High 3/4"
    elif angle >= 55:
        return "Low 3/4"
    elif angle >= 40:
        return "Sidearm"
    else:
        return "Submarine"
```

### Arm Angle Delta String (follows existing pattern)

```python
# Source: Follows _release_delta_string pattern at engine.py:1188
_ARM_ANGLE_THRESHOLD = 2.0
"""Degrees below which arm angle delta is 'Steady'."""

def _arm_angle_delta_string(delta: float, threshold: float = _ARM_ANGLE_THRESHOLD) -> str:
    """Convert arm angle delta (degrees) to qualitative string."""
    if abs(delta) < threshold:
        return f"Steady ({delta:+.1f} deg)"
    direction = "Up" if delta > 0 else "Down"
    return f"{direction} {abs(delta):.1f} deg"
```

### Percentile Computation (follows existing _compute_xrv100_percentile pattern)

```python
# Source: Follows pattern at engine.py:1867
def _compute_metric_percentile(
    value: float,
    population: list[float],
    higher_is_better: bool = True,
) -> int:
    """Compute percentile rank of value within population.
    
    Args:
        value: The metric value to rank.
        population: List of all league values for this metric.
        higher_is_better: If True, higher value = higher percentile.
            For velocity, True. For xRV100, False (already handled separately).
    """
    if not population:
        return 50
    if higher_is_better:
        n_worse = sum(1 for v in population if v < value)
    else:
        n_worse = sum(1 for v in population if v > value)
    return int(n_worse / len(population) * 100)
```

### Updated outlier_tag (backward-compatible)

```python
# Source: Extension of existing engine.py:294
def outlier_tag(value: float, avg: float, std: float, percentile: int | None = None) -> str:
    """Return OUTLIER or NORMAL tag with optional percentile rank.
    
    Format: 'OUTLIER - 98th percentile (above avg, z=+2.3)'
            'NORMAL - 65th percentile (z=+0.4)'
    """
    if std == 0:
        return "NORMAL"
    z = (value - avg) / std
    pctl_str = f"{percentile}th percentile " if percentile is not None else ""
    if abs(z) > 1.5:
        direction = "above" if z > 0 else "below"
        return f"OUTLIER - {pctl_str}({direction} avg, z={z:+.1f})"
    return f"NORMAL - {pctl_str}(z={z:+.1f})"
```

### Handedness-Split Baseline Computation

```python
# Source: Extension of compute_league_baselines at engine.py:195
# Add p_throws to grouping and to the load columns
df = load_all_statcast(
    columns=[
        "pitch_type", "pitch_name", "release_speed", "pfx_x", "pfx_z",
        "zone", "description", "p_throws",
        "release_pos_x", "release_pos_z", "release_extension",  # D-12
    ],
)

# Group by pitch_type AND p_throws
agg = (
    df.group_by("pitch_type", "pitch_name", "p_throws")
    .agg(
        # ... existing aggregations ...
        pl.col("release_pos_x").mean().alias("avg_release_x"),
        pl.col("release_pos_x").std().alias("release_x_std"),
        pl.col("release_pos_z").mean().alias("avg_release_z"),
        pl.col("release_pos_z").std().alias("release_z_std"),
        pl.col("release_extension").mean().alias("avg_extension"),
        pl.col("release_extension").std().alias("extension_std"),
    )
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| z-score only in outlier_tag | z-score + percentile + direction | Phase 23 | More interpretable tags for LLM; existing callers backward-compatible with None percentile |
| No count-state analysis | Five-bucket count splits | Phase 23 | Enables approach-level analysis (how pitcher adjusts strategy by count) |
| No arm angle metric | Per-pitch-type atan2 arm angle | Phase 23 | Physical profile enrichment for release point deception analysis |
| Full-league baselines | Handedness-split baselines | Phase 23 | More accurate outlier detection (LHP/RHP distributions differ for velo, movement, release point) |

## Open Questions

1. **Arm angle threshold: 2.0 degrees as "Steady" threshold**
   - What we know: Release position uses 0.1 ft (~1.2 in) threshold. Movement uses 0.5 in. The arm angle combines both dimensions.
   - What's unclear: Whether 2.0 degrees is the right noise floor. Typical per-pitch-type arm angle std dev is unknown.
   - Recommendation: Start with 2.0 degrees, adjust after seeing real output. A 2-degree change in arm angle is roughly a 0.2 ft change in release point at typical distances.

2. **Handedness split for all baselines or just percentile computation**
   - What we know: D-09 specifies handedness split for percentile computation. The broader question is whether `compute_league_baselines()` should return handedness-split data for ALL metrics or just for percentile.
   - What's unclear: Whether splitting all baseline rendering by handedness improves the prompt.
   - Recommendation: Split the underlying data by handedness (add `p_throws` field to LeagueBaseline), but continue rendering baselines without handedness split in `render_league_baselines()`. Only use the handedness split when computing percentiles for outlier_tag.

3. **Extension column fallback (discretion area)**
   - What we know: `release_extension` is 98.5% non-null in the 2026 parquet. Some datasets might have lower coverage.
   - What's unclear: Whether older parquets or test fixtures lack this column entirely.
   - Recommendation: Check for column existence before computing `avg_extension`/`extension_std`. If missing, set to None. The LeagueBaseline fields should be `float | None`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_engine.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENG-01 | Count splits computation (5 buckets, per-type usage, window/season deltas) | unit | `uv run pytest tests/test_engine.py -x -k "count_split" -q` | Wave 0 |
| ENG-02 | Arm angle atan2 computation + slot label + delta string | unit | `uv run pytest tests/test_engine.py -x -k "arm_angle" -q` | Wave 0 |
| ENG-03 | outlier_tag percentile format + handedness-split percentile computation | unit | `uv run pytest tests/test_engine.py -x -k "outlier_tag or percentile" -q` | Wave 0 (outlier_tag tests exist; percentile format tests new) |
| ENG-04 | PitcherContext wiring + to_prompt rendering (count splits adjacent to platoon, arm angle in release point) | integration | `uv run pytest tests/test_context.py -x -k "count_split or arm_angle" -q` | Wave 0 |
| ENG-05 | Small sample flag (<10 pitches) suppresses delta only | unit | `uv run pytest tests/test_engine.py -x -k "small_sample and count" -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_engine.py tests/test_context.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- new test functions for count splits computation (5 buckets, usage rates, deltas, notable shifts)
- [ ] `tests/test_engine.py` -- new test functions for arm angle (atan2 math, slot labels, delta strings, per-pitch-type)
- [ ] `tests/test_engine.py` -- update existing outlier_tag tests for new percentile format + backward compat
- [ ] `tests/test_engine.py` -- test handedness-split percentile computation
- [ ] `tests/test_engine.py` -- test small sample behavior (delta suppressed, usage still shown)
- [ ] `tests/test_engine.py` -- test LeagueBaseline extension with release point fields
- [ ] `tests/test_context.py` -- test PitcherContext includes count_splits and arm angle fields
- [ ] `tests/test_context.py` -- test to_prompt() renders count splits adjacent to platoon section

## Sources

### Primary (HIGH confidence)
- Statcast parquet schema: verified `balls` (Int64), `strikes` (Int64), `release_pos_x` (Float64), `release_pos_z` (Float64), `release_extension` (Float64), `p_throws` (String) columns via direct inspection
- engine.py (3,400 lines): all existing patterns (dataclass, compute function, delta string, cold start, small sample) verified by reading source
- context.py (741 lines): PitcherContext model, assemble_pitcher_context, to_prompt() rendering order verified
- Arm angle distribution: 987 pitchers from 2026 Statcast, mean 71.8 deg, range 21.4-89.9 deg
- Count state data: 176,380 pitches verified with balls/strikes cross-tabulation
- Release extension coverage: 173,767/176,380 (98.5%) non-null verified

### Secondary (MEDIUM confidence)
- Arm angle slot thresholds: empirically derived from data, matches scouting convention (most pitchers are 3/4 slot)
- 2.0 degree steady threshold for arm angle: reasonable based on release point threshold analogy but not validated against appearance-to-appearance variance

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all computation uses existing polars + stdlib
- Architecture: HIGH - all patterns verified by reading existing engine.py code
- Pitfalls: HIGH - slot threshold issue verified empirically with real data (99% classified as Overhand with D-06 thresholds)
- Count state definitions: HIGH - verified against Statcast schema and real data
- Arm angle thresholds: MEDIUM - empirically derived but not validated against scouting literature
- Percentile computation: HIGH - follows existing _compute_xrv100_percentile pattern

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable domain -- baseball analytics, established codebase patterns)
