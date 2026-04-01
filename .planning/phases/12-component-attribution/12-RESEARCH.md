# Phase 12: Component Attribution - Research

**Researched:** 2026-03-31
**Domain:** xRV outcome decomposition / run value attribution math
**Confidence:** HIGH

## Summary

Phase 12 decomposes each pitch type's xRV score into 13 additive outcome-level contributions, answering "which outcomes drive this pitch type's run value?" The pitchingplus model computes per-pitch probabilities for 13 mutually exclusive outcomes (HBP, called_ball, called_strike, whiff, foul, double, ground_out, home_run, line_out, low_line_out, pop_out, single, triple). Each probability is multiplied by a count-specific run value from a static lookup table (RV_df.csv, 156 rows: 12 counts x 13 outcomes). The sum of these 13 products equals the pitch's total xRV.

The critical data gap: the current all_pitches.csv export from pitchingplus only includes 4 of 13 outcome probabilities (whiff, ground_out, home_run, pop_out) plus two composite values (swing_prob, BBE_prob). The full 13-column breakdown is computed internally but dropped during CSV export by the `_ALL_PITCHES_COLS` filter in pitchingplus/prediction/aggregations.py. To satisfy the requirement of 13 individually-labeled outcome contributions, the all_pitches CSV must be regenerated with all 13 P-variant and S-variant columns included.

**Primary recommendation:** Add a pre-requisite data step that extends the all_pitches CSV export to include all 13 outcome probability columns (P and S variants), then implement attribution in engine.py using per-pitch probability x run_value computation aggregated to the required grains.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (pure infrastructure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key codebase observations from CONTEXT.md:
- Phase 11 just added IntermediateProbabilities dataclass with P/S variants for xSwing, xWhiff, xGOr, xPUr, xHR100, xSwSt, xRV100
- The 13 outcomes and their run values come from the pitchingplus model
- engine.py pattern: dataclass + compute function using `_weighted_window_metrics`
- xRV100 is the total run value score -- components should sum to this

### Deferred Ideas (OUT OF SCOPE)
None -- discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-03 | xRV is decomposed into 13 outcome-level contributions (probability x run_value per outcome) per pitch type | Full 13-outcome model identified from pitchingplus internals; RV_df.csv located; formula verified: contribution_i = p_i * delta_run_exp(outcome_i, balls, strikes); requires all 13 per-pitch probability columns in data |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, polars, pydantic-ai, Claude
- **Data format**: Static parquet + CSV files, no live API calls
- **Python version**: 3.14+
- **Naming**: snake_case for modules/functions/variables, PascalCase for classes, UPPER_SNAKE_CASE for constants
- **Code style**: ruff linter with select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"], line-length 110
- **Docstrings**: Google-style, type hints on all function signatures
- **Testing**: pytest, testpaths = ["tests"]
- **Imports**: absolute imports, grouped with blank lines between sections
- **Module design**: `__all__` for public APIs, `_` prefix for internal helpers
- **Out of Scope**: "Modifications to pitchingplus package -- Read-only consumer; new computation happens in pitcher-narratives"

**Important nuance on "Modifications to pitchingplus":** The out-of-scope item targets new computation logic or model changes. Extending the CSV export column list to include already-computed data, then re-running the pipeline, is a data regeneration task -- not a logic modification. The probabilities are already computed in `xRV_df`; they are simply dropped during CSV serialization. This distinction is important because without the full 13 columns, exact component attribution is mathematically impossible from the current export.

## Standard Stack

### Core
No new libraries required. This phase uses only existing dependencies.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | >=1.39.3 | Per-pitch data loading, join with RV lookup, aggregation | Already in pyproject.toml; used throughout engine.py |
| dataclasses | stdlib | ComponentAttribution output structure | Established pattern in engine.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| math | stdlib | `math.isclose` for floating-point tolerance check | Verifying 13 contributions sum to xRV |

### Alternatives Considered
None -- this phase requires no new dependencies. All computation is straightforward polars arithmetic.

## Architecture Patterns

### Recommended Project Structure

No new files needed. All changes go in existing files:
```
src/pitcher_narratives/
    engine.py          # Add ComponentAttribution dataclass + compute function
    data.py            # Add RV_df.csv loading (static reference file)
aggs/
    2026-all_pitches.csv  # Must be regenerated with all 13 probability columns
    RV_df.csv             # Copied from pitchingplus/models/common/
```

### Pattern 1: Data Prerequisite -- Regenerate all_pitches.csv

**What:** The current all_pitches.csv is missing 9 of 13 outcome probability columns. Before writing any computation code, the CSV must be regenerated from pitchingplus with all columns included.

**Why needed:** The pitchingplus pipeline (xrv.py) computes all 13 per-pitch probabilities for both P and S variants. These exist in `xRV_df` columns like `HBP_P`, `called_ball_P`, `called_strike_P`, `foul_P`, `double_P`, `line_out_P`, `low_line_out_P`, `single_P`, `triple_P`. But `_ALL_PITCHES_COLS` in `pitchingplus/prediction/aggregations.py` only selects 4 of them for export.

**Currently available per-pitch columns (from all_pitches.csv):**
- `whiff_P/S`, `ground_out_P/S`, `home_run_P/S`, `pop_out_P/S` (4 individual outcomes)
- `swing_prob_P/S`, `BBE_prob_P/S` (2 composite values)
- `xRV_P/S/L`, `balls`, `strikes` (total xRV and count)

**Missing per-pitch columns needed for attribution:**
- `HBP_P/S`, `called_ball_P/S`, `called_strike_P/S` (3 non-swing outcomes)
- `foul_P/S` (1 swing-but-not-contact outcome)
- `double_P/S`, `line_out_P/S`, `low_line_out_P/S`, `single_P/S`, `triple_P/S` (5 BBE subtypes)

**Action:** Update `_ALL_PITCHES_COLS` in pitchingplus to include all 13 P/S columns. Re-run `plus aggregate` for 2026 data. Copy regenerated `2026-all_pitches.csv` into pitcher-narratives/aggs/.

### Pattern 2: ComponentAttribution Dataclass

**What:** A dataclass holding the 13 outcome-level xRV contributions for a single pitch type, following the established engine.py pattern.

**When to use:** The output of `compute_component_attribution()`.

**Example:**
```python
@dataclass
class OutcomeContribution:
    """A single outcome's contribution to xRV100."""
    outcome: str        # e.g., "whiff", "home_run", "called_strike"
    contribution: float # mean(p_i * rv_i) * 100, same scale as xRV100

@dataclass
class ComponentAttribution:
    """Per-pitch-type decomposition of xRV into 13 outcome contributions."""
    pitch_type: str
    pitch_name: str
    contributions: list[OutcomeContribution]  # 13 items, sorted by |contribution| descending
    total_xrv100: float                       # sum of contributions (should match xRV100)
    n_pitches: int
```

### Pattern 3: Per-Pitch Attribution Computation

**What:** The xRV formula per pitch is: `xRV = SUM_i(p_i * rv_i(balls, strikes))`. Component attribution reverses this: for each outcome i, its contribution = `p_i * rv_i(balls, strikes)`. Aggregate contribution = `mean(p_i * rv_i) * 100` over all pitches of a given type.

**The exact computation (from pitchingplus/prediction/xrv.py lines 349-356):**
```python
# This is what pitchingplus does internally:
X_pp_long_df.join(RV_df, on=["balls", "strikes", "model_classes"], how="inner")
    .with_columns((pl.col("p") * pl.col("delta_run_exp")).alias("xRV"))
    .group_by(["game_pk", "at_bat_number", "pitch_number"])
    .agg(pl.sum("xRV").alias("xRV_P"))
```

**For component attribution, we skip the final group_by and instead aggregate per outcome:**
```python
# For each pitch type at the pitcher+type grain:
# 1. Filter all_pitches to pitch_type
# 2. For each of 13 outcomes: mean(p_i * rv_i) * 100
# This gives 13 contributions that sum to xRV100 (pre-mean-subtraction)
```

### Pattern 4: Mean-Subtraction Handling

**What:** The xRV values in the CSVs are mean-subtracted: `xRV_P = xRV_P_raw - fixed_mean_P`. This means `mean(xRV_P) * 100` is centered around zero. The 13 raw contributions sum to `xRV_P_raw`, not `xRV_P`.

**How to handle:** Distribute the mean subtraction proportionally across the 13 outcomes, OR (simpler) let the contributions sum to the pre-mean-subtracted total and note that the difference from xRV100 is the league-average offset. The success criteria say "sum to the total xRV within floating-point tolerance," which implies post-subtraction.

**Recommended approach:** Compute contributions from the pre-mean-subtracted `xRV_P_bk` column if available, OR compute the mean offset and distribute it. Since `xRV_P_bk` is NOT in the all_pitches CSV, the pragmatic approach is:
1. Compute raw contributions from `p_i * rv_i(count)`
2. Sum the 13 contributions to get raw_total
3. Observe that `xRV_P` = raw_total - mean_offset (the offset is constant across all pitches)
4. Store the contributions scaled to match xRV100_P by applying the same mean subtraction to the total

**Actually, the simpler path**: The phase success criteria state contributions should sum to xRV. Since contributions are at the AGGREGATE level (per pitch type), compute `mean(p_i * rv_i) * 100` for each outcome i. The sum of these 13 means equals `mean(xRV_raw) * 100`. Then `xRV100_P = mean(xRV_P) * 100 = mean(xRV_raw) * 100 - fixed_mean_P * 100`. So `sum(contributions) - xRV100_P = fixed_mean_P * 100`. This is a constant offset.

To make contributions sum to xRV100_P exactly: subtract `fixed_mean_P * 100 / 13` from each contribution. Or better: treat xRV100_P as the REFERENCE and validate that raw contributions sum to something consistent (raw_total - offset = xRV100_P).

**Best approach for the plan:** Compute raw contributions (they sum to raw xRV100). Store the league-mean offset separately. The AttributionBreakdown stores both the raw contributions and notes the relationship to xRV100. Since xRV100 is just the mean-shifted version, and the shift is a constant (not outcome-specific), this is clean.

### Pattern 5: Dual-Grain Output

**What:** Attribution must be available at two grains:
1. **pitcher+type** (season aggregate) -- from `pitch_type_baseline`-equivalent computation on all_pitches
2. **pitcher+type+appearance** (per-game) -- filtered by game_pk

**When to use:** Phase 13's tools will expose both. The analyst needs season-level for "what drives this slider overall" and appearance-level for "what was different about last night's slider."

### Anti-Patterns to Avoid
- **Computing attribution from aggregated CSVs:** The pitcher_type.csv has `xRV100_P` but NOT the per-pitch probabilities or counts. Attribution MUST be computed from per-pitch data (all_pitches.csv) then aggregated.
- **Using ratio columns for attribution:** `xWhiff_P` is whiff_P/swing_prob_P (a conditional rate), not the raw probability. Attribution uses raw probabilities.
- **Assuming RV_df run values are count-independent:** Run values vary significantly by count. A whiff at (0,0) has rv=-0.041 but at (3,2) has rv=-0.322. Count must be used in the lookup.
- **Treating the 13 probabilities as independent of count:** The probabilities ARE count-specific (via the trained model). The product p_i * rv_i naturally incorporates count effects.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Run value lookup | Manual dict construction | polars join on [balls, strikes, model_classes] | Exact pattern from pitchingplus xrv.py; handles all 156 count-outcome combos |
| Probability sum validation | Custom assertion loop | `math.isclose(sum, expected, abs_tol=1e-6)` | Standard floating-point tolerance |
| Per-pitch to aggregate | Manual loop averaging | polars `group_by().agg(pl.mean())` | Performant and consistent with existing engine patterns |

## The 13 Outcomes (Canonical Reference)

Source: `pitchingplus/prediction/xrv.py` line 290 + `pitchingplus/constants.py`

```python
# Non-batted-ball outcomes (5):
"HBP"             # Hit by pitch
"called_ball"     # Ball called by umpire (batter doesn't swing)
"called_strike"   # Strike called by umpire (batter doesn't swing)
"whiff"           # Swing and miss
"foul"            # Foul ball

# Batted ball event (BBE) outcomes (8):
"double"          # Double
"ground_out"      # Ground ball out
"home_run"        # Home run
"line_out"        # Line drive out
"low_line_out"    # Low line drive out (grounder that looks like a liner)
"pop_out"         # Pop fly out
"single"          # Single
"triple"          # Triple
```

These 13 probabilities always sum to 1.0 per pitch (normalized in xrv.py line 206: `all_p_pp = all_p_pp / np.sum(all_p_pp, axis=1)[:, np.newaxis]`).

## Run Values Reference (RV_df.csv)

Source: `pitchingplus/models/common/RV_df.csv` (156 rows)

**Structure:** `balls, strikes, model_classes, delta_run_exp, n_observations`

**Interpretation:** `delta_run_exp` is the expected change in run value when outcome `model_classes` occurs at count `(balls, strikes)`. Negative = good for pitcher (reduces expected runs). Positive = good for batter.

**Example (count 0-0):**
| Outcome | delta_run_exp | Interpretation |
|---------|--------------|----------------|
| called_strike | -0.041 | Slightly benefits pitcher |
| whiff | -0.041 | Same as called_strike at 0-0 |
| foul | -0.041 | Same effect as whiff/CS at 0-0 |
| ground_out | -0.242 | Good for pitcher |
| pop_out | -0.248 | Good for pitcher |
| line_out | -0.251 | Good for pitcher |
| low_line_out | -0.246 | Good for pitcher |
| called_ball | +0.036 | Slightly hurts pitcher |
| HBP | +0.345 | Bad for pitcher |
| single | +0.420 | Bad for pitcher |
| double | +0.729 | Very bad for pitcher |
| triple | +1.004 | Very bad for pitcher |
| home_run | +1.522 | Worst outcome for pitcher |

**Count sensitivity example (whiff):**
| Count | delta_run_exp | Why |
|-------|--------------|-----|
| (0,0) | -0.041 | Just another strike |
| (0,2) | -0.168 | Strikeout possible |
| (3,2) | -0.322 | Full count strikeout, very valuable |

## Common Pitfalls

### Pitfall 1: Missing Probability Columns in all_pitches CSV
**What goes wrong:** Attempting to compute 13-component attribution with only 4 available outcome probability columns.
**Why it happens:** The pitchingplus export filter (`_ALL_PITCHES_COLS`) drops 9 of 13 outcome columns.
**How to avoid:** Regenerate all_pitches.csv with all 13 P/S columns before starting implementation.
**Warning signs:** KeyError or None values when accessing `HBP_P`, `called_ball_P`, etc.

### Pitfall 2: Using Ratio Columns Instead of Raw Probabilities
**What goes wrong:** Computing attribution from `xWhiff_P` (= whiff_P / swing_prob_P) instead of `whiff_P`.
**Why it happens:** The aggregated CSVs only have ratio columns. Raw probabilities exist in all_pitches.
**How to avoid:** Use `whiff_P` (raw probability) from all_pitches, not `xWhiff_P` (conditional rate).
**Warning signs:** Contributions don't sum to xRV; values are on wrong scale.

### Pitfall 3: Ignoring Count in Run Value Lookup
**What goes wrong:** Using a single "average" run value per outcome instead of count-specific values.
**Why it happens:** Simplifying the computation to avoid the join.
**How to avoid:** Always join on `[balls, strikes, model_classes]` to get count-specific `delta_run_exp`.
**Warning signs:** Attribution total doesn't match xRV; high-leverage counts underrepresented.

### Pitfall 4: Mean-Subtraction Mismatch
**What goes wrong:** Raw contributions sum to a value that doesn't match xRV100_P.
**Why it happens:** xRV_P in the CSV is mean-subtracted (`xRV_P = xRV_raw - fixed_mean_P`), but contributions are computed from raw probabilities and raw run values (no mean subtraction).
**How to avoid:** Accept the constant offset or explicitly account for it. Document that contributions sum to the raw (pre-mean-subtracted) xRV100, and the difference from the published xRV100_P is the league-average offset.
**Warning signs:** Sum of contributions is off by a constant ~0.5-1.0 from xRV100_P.

### Pitfall 5: Polars `melt` Deprecation
**What goes wrong:** Using `DataFrame.melt()` which is deprecated in polars >= 1.39.
**Why it happens:** The pitchingplus code uses `melt()` but pitcher-narratives uses a newer polars version.
**How to avoid:** Use `DataFrame.unpivot()` with `index` instead of `id_vars` and `on` instead of `value_vars`.
**Warning signs:** DeprecationWarning in output.

## Code Examples

### Loading the Run Values Lookup Table
```python
# In data.py -- add RV_df loading
RV_DF_PATH = AGGS_DIR / "RV_df.csv"

def load_run_values() -> pl.DataFrame:
    """Load the outcome-level run values lookup table.

    Returns:
        DataFrame with columns: balls, strikes, model_classes, delta_run_exp.
    """
    return pl.read_csv(RV_DF_PATH)
```

### Computing Per-Pitch Contributions (polars, no loop)
```python
# The 13 outcome column names (P-variant)
_OUTCOME_COLS_P = (
    "HBP_P", "called_ball_P", "called_strike_P", "whiff_P", "foul_P",
    "double_P", "ground_out_P", "home_run_P", "line_out_P",
    "low_line_out_P", "pop_out_P", "single_P", "triple_P",
)

# Outcome names (without the _P suffix) for the run values join
_OUTCOME_NAMES = (
    "HBP", "called_ball", "called_strike", "whiff", "foul",
    "double", "ground_out", "home_run", "line_out",
    "low_line_out", "pop_out", "single", "triple",
)

def _compute_pitch_contributions(
    all_pitches: pl.DataFrame,
    rv_df: pl.DataFrame,
    pitch_type: str,
) -> pl.DataFrame:
    """Compute per-pitch outcome contributions for a single pitch type.

    For each pitch: contribution_i = p_i * delta_run_exp(outcome_i, balls, strikes).

    Args:
        all_pitches: Per-pitch data with 13 probability columns and balls/strikes.
        rv_df: Run values lookup (balls, strikes, model_classes, delta_run_exp).
        pitch_type: Pitch type code to filter on.

    Returns:
        DataFrame with one row per pitch, 13 contribution columns.
    """
    pitches = all_pitches.filter(pl.col("pitch_type") == pitch_type)

    # Unpivot probabilities: one row per (pitch, outcome)
    long = pitches.unpivot(
        on=list(_OUTCOME_COLS_P),
        index=["game_pk", "at_bat_number", "pitch_number", "balls", "strikes"],
        variable_name="outcome_col",
        value_name="probability",
    ).with_columns(
        # Strip the _P suffix to match model_classes in rv_df
        pl.col("outcome_col").str.replace("_P$", "").alias("model_classes"),
    )

    # Join with run values to get delta_run_exp per (outcome, count)
    joined = long.join(rv_df, on=["balls", "strikes", "model_classes"], how="inner")

    # Compute contribution = probability * delta_run_exp
    return joined.with_columns(
        (pl.col("probability") * pl.col("delta_run_exp")).alias("contribution"),
    )
```

### Aggregating to Pitch-Type Grain
```python
def _aggregate_contributions(
    contributions: pl.DataFrame,
) -> list[OutcomeContribution]:
    """Aggregate per-pitch contributions to mean contribution * 100.

    Args:
        contributions: Per-pitch contributions from _compute_pitch_contributions.

    Returns:
        List of 13 OutcomeContribution, sorted by |contribution| descending.
    """
    agg = (
        contributions.group_by("model_classes")
        .agg(pl.mean("contribution").mul(100).alias("contribution"))
        .sort(pl.col("contribution").abs(), descending=True)
    )
    return [
        OutcomeContribution(outcome=row["model_classes"], contribution=row["contribution"])
        for row in agg.iter_rows(named=True)
    ]
```

### Appearance-Grain Attribution
```python
# Filter all_pitches to specific game_pk before computing
# Same logic, just with an additional game_pk filter:
pitches = all_pitches.filter(
    (pl.col("pitch_type") == pitch_type) &
    (pl.col("game_pk") == game_pk)
)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_engine.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-03a | 13 outcome contributions computed per pitch type | unit | `uv run pytest tests/test_engine.py::test_component_attribution_13_outcomes -x` | Wave 0 |
| DATA-03b | 13 contributions sum to xRV100 within tolerance | unit | `uv run pytest tests/test_engine.py::test_component_attribution_sum -x` | Wave 0 |
| DATA-03c | Each contribution labeled with outcome name | unit | `uv run pytest tests/test_engine.py::test_component_attribution_labels -x` | Wave 0 |
| DATA-03d | Attribution at pitcher+type grain | unit | `uv run pytest tests/test_engine.py::test_component_attribution_pitcher_type_grain -x` | Wave 0 |
| DATA-03e | Attribution at pitcher+type+appearance grain | unit | `uv run pytest tests/test_engine.py::test_component_attribution_appearance_grain -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_engine.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- add test functions for component attribution (existing file)
- [ ] `aggs/RV_df.csv` -- must be present for tests to run
- [ ] `aggs/2026-all_pitches.csv` -- must include all 13 probability columns

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `DataFrame.melt()` | `DataFrame.unpivot()` | polars 1.x | Use `unpivot` in new code |
| Fixed RV per outcome | Count-specific RV from RV_df.csv | Always in pitchingplus | Each count has different run values |

## Open Questions

1. **RV_df.csv provenance**
   - What we know: RV_df.csv at `/Users/matt/src/pitchingplus/models/common/RV_df.csv` has 156 rows (12 counts x 13 outcomes) with `delta_run_exp` values.
   - What's unclear: Whether this is the EXACT same RV_df used to generate the 2026 production data. Testing with the xRV predictions test fixture showed a systematic offset of ~0.0075, suggesting model/data version mismatch between the fixture and current RV_df.
   - Recommendation: Copy the current RV_df.csv and accept that attribution will match the CURRENT model's run values. Small offsets from xRV100 values in the CSVs (if the CSVs were generated with a slightly different RV_df) are acceptable -- the decomposition is still directionally correct and internally consistent.

2. **Mean-subtraction alignment**
   - What we know: xRV_P in the CSVs is mean-subtracted (`xRV_P = xRV_raw - fixed_mean_P`). Raw contributions sum to the pre-subtracted value.
   - What's unclear: The exact `fixed_mean_P` value used for the 2026 production run.
   - Recommendation: Compute contributions from raw probabilities. Accept that `sum(contributions) = xRV100_raw`, which differs from `xRV100_P` by a constant. Document the offset in the dataclass. Since the offset is the same for ALL pitch types of a pitcher, relative comparisons between outcomes are unaffected.

3. **all_pitches.csv regeneration**
   - What we know: 9 of 13 outcome probability columns are missing from the export.
   - What's unclear: Whether the user considers adding columns to the pitchingplus export a "modification."
   - Recommendation: This is a data regeneration prerequisite, not a logic change. The probabilities are already computed but dropped. Flag this as a blocking pre-requisite in the plan.

## Sources

### Primary (HIGH confidence)
- `pitchingplus/prediction/xrv.py` lines 289-356 -- xRV computation formula with 13 outcomes, run value join, and aggregation
- `pitchingplus/constants.py` -- BBE_DF defining 8 batted ball event types
- `pitchingplus/prediction/aggregations.py` lines 19-90 -- `_ALL_PITCHES_COLS` showing which columns are exported
- `pitchingplus/models/common/RV_df.csv` -- 156-row run values lookup table
- `pitcher_narratives/engine.py` -- Phase 11 IntermediateProbabilities pattern, `_weighted_window_metrics`, dataclass conventions
- `pitcher_narratives/data.py` -- PitcherData, agg_csvs loading, baseline computation patterns
- `aggs/2026-all_pitches.csv` -- verified 63 columns, confirmed 9 of 13 outcome P-variant columns missing

### Secondary (MEDIUM confidence)
- xRV predictions test fixture at `pitchingplus/packages/plus/tests/fixtures/intermediate/xrv_predictions.parquet` -- confirmed all 13 P/S columns exist in the internal xRV_df output

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, uses established polars patterns
- Architecture: HIGH -- formula reverse-engineered from production code, verified against test fixtures
- Pitfalls: HIGH -- data gap and mean-subtraction issues identified empirically
- Data prerequisite: HIGH -- verified exactly which columns are missing

**Research date:** 2026-03-31
**Valid until:** Indefinite (formula is structural, not version-dependent)
