# Phase 3: Execution & Context Engine - Research

**Researched:** 2026-03-26
**Domain:** Baseball execution metrics computation, workload tracking, Pydantic model assembly
**Confidence:** HIGH

## Summary

Phase 3 adds execution metrics (CSW%, xWhiff, xSwing, zone/chase rates, xRV100 ranking) and workload context (rest days, innings pitched, pitch counts, consecutive-days tracking) to the existing engine, then assembles ALL outputs into a single PitcherContext Pydantic model with a `to_prompt()` method that renders prompt-ready markdown under 2,000 tokens.

The data investigation confirms all required columns exist. CSW% is computed from Statcast `description` values (`called_strike`, `swinging_strike`, `swinging_strike_blocked`). Zone rate uses zones 1-9 (strike zone) vs 11-14 (outside). xWhiff/xSwing/xRV100 come from the Pitching+ CSV aggregations (`pitcher_type.csv` for season, `pitcher_type_appearance.csv` for window). Rest days must be computed from appearance dates since Statcast's `pitcher_days_since_prev_game` column is entirely null. The PitcherContext model uses Pydantic v2.12.5 (already installed) and lives in a new `context.py` module.

**Primary recommendation:** Add execution metric functions to `engine.py` following the established dataclass + compute function pattern, create `context.py` with a Pydantic model that imports from both `data.py` and `engine.py`, and implement `to_prompt()` as a method that renders structured markdown. Keep top 4 pitch types to stay within the 2,000-token budget.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Add execution metrics to engine.py -- keeps all computation in one module
- CSW%: count called_strike + swinging_strike descriptions in Statcast, divide by total pitches per type in window
- Zone rate: pitches in zone 1-9 / total; Chase rate (O-Swing%): swings on pitches outside zone / pitches outside zone -- uses Statcast `zone` and `description` columns
- xRV100 ranking: percentile rank against 2026-team.csv averages for league context
- Rest days: days between consecutive game_dates in appearance data
- Innings pitched: count unique (game_pk, inning) pairs + partial innings from outs recorded in Statcast
- Consecutive days pitched flag: 3+ consecutive days triggers reliever workload concern
- Pitch count per appearance: count rows in Statcast per (pitcher, game_pk)
- New `context.py` module -- Pydantic model separate from polars computation in engine.py
- `to_prompt()` renders as markdown with headers, bullet points, and small tables
- Token budget: truncate lower-usage pitch types (keep top 4), abbreviate where possible, test with ~4 chars/token heuristic
- PitcherContext assembles ALL engine outputs (fastball, arsenal, execution, workload) into one prompt-ready document

### Claude's Discretion
- Exact Pydantic field names and nesting structure
- Markdown formatting details in to_prompt()
- How to handle missing data gracefully in the prompt (e.g., no platoon data available)
- Ordering of sections in the rendered prompt

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | CSW% (called + swinging strike rate) by pitch type for recent window | Statcast `description` column contains `called_strike`, `swinging_strike`, `swinging_strike_blocked` -- confirmed via data inspection. Compute per pitch_type in window dates. |
| EXEC-02 | xWhiff and xSwing rates per pitch type | `pitcher_type.csv` has `xWhiff_P`, `xWhiff_S`, `xSwing_P`, `xSwing_S` at season level; `pitcher_type_appearance.csv` has same at per-appearance level for window computation. Use existing `_weighted_window_pplus`-style pattern. |
| EXEC-03 | Zone rate vs chase rate (O-Swing%) analysis | Statcast `zone` column: 1-9 = strike zone, 11-14 = outside. Swing descriptions for chase: `swinging_strike`, `swinging_strike_blocked`, `foul`, `foul_tip`, `hit_into_play`, `foul_bunt`, `bunt_foul_tip`, `missed_bunt`. Verified 27.2% league chase rate. |
| EXEC-04 | xRV100 ranking showing how pitches grade relative to league | `pitcher_type.csv` has `xRV100_P` per pitch type per pitcher (1,651 unique pitchers). Compute weighted baseline per pitcher, then percentile rank against all pitchers throwing that type. Team CSV provides overall league reference. |
| CTX-01 | Rest days between appearances | Compute from `appearances` DataFrame `game_date` column. Statcast `pitcher_days_since_prev_game` is null. Simple date arithmetic: `(date[i] - date[i-1]).days - 1`. |
| CTX-02 | Innings pitched and pitch count per appearance | Appearances already have `n_pitches`. Innings: count unique innings per game_pk in Statcast + partial inning from max `outs_when_up` in final inning. |
| CTX-03 | Consecutive days pitched tracking for relievers | Date arithmetic on sorted appearance dates. Flag when 3+ consecutive days detected. Test pitcher has max 1 consecutive day. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.39.3 | All DataFrame computation for execution metrics | Already used throughout engine.py and data.py |
| pydantic | 2.12.5 | PitcherContext model definition and validation | Already installed (transitive via pydantic-ai); decision specifies Pydantic model |
| dataclasses (stdlib) | 3.14 | Execution metric return types in engine.py | Established pattern from Phase 2 (FastballSummary, PitchTypeSummary, etc.) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| datetime (stdlib) | 3.14 | Date arithmetic for rest days and consecutive days | Workload context computation |

No new dependencies needed. Everything required is already in pyproject.toml or stdlib.

## Architecture Patterns

### Recommended Project Structure
```
pitcher-narratives/
  data.py          # Data loading (Phase 1, unchanged)
  engine.py        # All computation (Phase 2 + new execution/workload functions)
  context.py       # NEW: PitcherContext Pydantic model + to_prompt()
  main.py          # CLI entry point
  tests/
    test_data.py
    test_engine.py  # Extended with execution/workload tests
    test_context.py # NEW: PitcherContext assembly and to_prompt() tests
```

### Pattern 1: Dataclass Return Type for Engine Functions
**What:** Each compute function returns a frozen dataclass with pre-computed values and qualitative strings.
**When to use:** All new engine functions (execution metrics, workload context).
**Example:**
```python
# Follow established pattern from engine.py
@dataclass
class ExecutionMetrics:
    """Per-pitch-type execution metrics for the recent window."""
    pitch_type: str
    pitch_name: str
    csw_pct: float
    zone_rate: float
    chase_rate: float
    xwhiff_p: float | None
    xswing_p: float | None
    xrv100_p: float | None
    xrv100_percentile: int | None
    n_pitches: int
    small_sample: bool
```

### Pattern 2: Window-Filtered Computation
**What:** Filter Statcast or CSV data to window dates, compute metric, return alongside season baseline.
**When to use:** CSW%, zone/chase rates, xWhiff/xSwing.
**Example:**
```python
# Reuse existing _get_window_game_dates helper
window_dates = _get_window_game_dates(data)
window_statcast = data.statcast.filter(pl.col("game_date").is_in(window_dates))
# Then compute per-type metrics on window_statcast
```

### Pattern 3: Pydantic Model with Render Method
**What:** PitcherContext Pydantic BaseModel with a `to_prompt() -> str` method that renders markdown.
**When to use:** The context.py module assembles all engine outputs.
**Example:**
```python
from pydantic import BaseModel

class PitcherContext(BaseModel):
    """Complete context document for LLM prompt generation."""
    pitcher_name: str
    throws: str
    # ... nested models or direct fields ...

    def to_prompt(self) -> str:
        """Render as prompt-ready markdown under 2,000 tokens."""
        sections = []
        sections.append(f"# {self.pitcher_name} ({self.throws}HP)")
        # ... render each section ...
        return "\n\n".join(sections)
```

### Pattern 4: Percentile Rank via Polars
**What:** Rank a pitcher's xRV100 against all pitchers throwing that type.
**When to use:** EXEC-04 xRV100 ranking.
**Example:**
```python
# For each pitch type, compute weighted baseline xRV100 per pitcher
# Then find percentile rank
all_pitchers = pitcher_type_csv.group_by(["pitcher", "pitch_type"]).agg(
    (pl.col("xRV100_P") * pl.col("n_pitches")).sum() / pl.col("n_pitches").sum()
)
# Filter to pitch type, compute rank
type_dist = all_pitchers.filter(pl.col("pitch_type") == pt)
n_below = type_dist.filter(pl.col("xRV100_P") > pitcher_xrv100).height  # negative is better
percentile = int(n_below / len(type_dist) * 100)
```

### Anti-Patterns to Avoid
- **Mixing Polars and Pydantic in context.py:** Keep polars computation in engine.py. context.py should only assemble pre-computed values into the Pydantic model.
- **Hardcoding description strings:** Use constants for CSW descriptions (`_CSW_DESCRIPTIONS = frozenset({"called_strike", "swinging_strike", "swinging_strike_blocked"})`) to match the existing constants pattern.
- **Computing zone rate on null zones:** 1,179 of 145,307 pitches have null zones. Always filter nulls before zone rate computation.
- **Using team.csv without game_type weighting:** Team CSV has separate rows per game_type (S/R/C). Must weight-average like the existing baseline pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token counting | Character-level tokenizer | ~4 chars/token heuristic + manual testing | CONTEXT.md explicitly specifies this approach; real tokenizer is overkill |
| Percentile rank | Manual sort + binary search | Polars filter + count | Polars handles this in one expression; manual implementation is error-prone |
| Date difference | Manual date math | Python `datetime.timedelta` | Already used in data.py `filter_to_window` |
| Weighted averages | Loop-based accumulation | Polars `(col * weight).sum() / weight.sum()` | Established pattern throughout engine.py |

## Common Pitfalls

### Pitfall 1: Null Zones in Zone Rate Computation
**What goes wrong:** Including null-zone pitches in denominator deflates zone rate.
**Why it happens:** 1,179 of 145,307 pitches (0.8%) have null zones in Statcast.
**How to avoid:** Filter `pl.col("zone").is_not_null()` before computing zone rate and chase rate.
**Warning signs:** Zone rate + out-of-zone rate don't sum to 100%.

### Pitfall 2: CSW% Description Values Must Be Exact
**What goes wrong:** Missing `swinging_strike_blocked` in the CSW filter undercounts strikes.
**Why it happens:** There are 3 strike descriptions, not 2. `swinging_strike_blocked` is a swing-and-miss where the catcher blocks the ball.
**How to avoid:** Use constant: `_CSW_DESCRIPTIONS = frozenset({"called_strike", "swinging_strike", "swinging_strike_blocked"})`.
**Warning signs:** CSW% seems low compared to expected MLB averages (~28-32%).

### Pitfall 3: xRV100 Polarity (Negative = Better for Pitchers)
**What goes wrong:** Percentile ranking inverted -- showing elite pitchers as bad.
**Why it happens:** xRV100 measures run value from the batter's perspective. Negative xRV100 means the pitcher prevents runs (good for pitcher). Lower is better.
**How to avoid:** When computing percentile, count pitchers with HIGHER (worse) xRV100: `pctl = n_above / total * 100`.
**Warning signs:** Elite pitchers showing low percentiles, bad pitchers showing high.

### Pitfall 4: IP Estimation for Partial Innings
**What goes wrong:** Counting unique innings gives whole innings only, missing partial innings.
**Why it happens:** A reliever who gets 1 out in the 7th inning pitched 0.1 IP, not 1.0 IP.
**How to avoid:** For each appearance: full innings = (last_inning - first_inning) counted from Statcast, plus partial from outs recorded. Use `outs_when_up` at final pitch of the appearance's final inning to compute partial. Standard formula: `IP = full_innings + (outs_in_final_inning / 3)`. Display as traditional baseball notation (e.g., "1.2" means 1 and 2/3 innings).
**Warning signs:** Reliever showing 1.0 IP when they only got 1 out.

### Pitfall 5: Consecutive Days Off-by-One
**What goes wrong:** Adjacent dates (Mar 9 and Mar 10) counted as 1 day apart, not consecutive.
**Why it happens:** `(date2 - date1).days == 1` means consecutive days, not "1 day rest."
**How to avoid:** Consecutive days pitched means `(date[i] - date[i-1]).days == 1`. Rest days = `(date[i] - date[i-1]).days - 1`. Two appearances on consecutive calendar days = 0 rest days.
**Warning signs:** Rest day counts don't match calendar inspection.

### Pitfall 6: Game Type Weighting for xRV100 Percentile
**What goes wrong:** Spring training (S) and regular season (R) and WBC (C) rows treated as separate pitchers.
**Why it happens:** pitcher_type.csv has multiple rows per pitcher per pitch_type (one per game_type).
**How to avoid:** Compute weighted-average xRV100 per (pitcher, pitch_type) across game_types before ranking, using the same n_pitches weighting pattern as `compute_pitch_type_baseline`.
**Warning signs:** Pitcher appearing multiple times in the distribution for a single pitch type.

### Pitfall 7: Token Budget Overflow
**What goes wrong:** to_prompt() output exceeds 2,000 tokens, wasting LLM context window.
**Why it happens:** Including all pitch types, all platoon splits, verbose formatting.
**How to avoid:** Keep top 4 pitch types only (decision). Use abbreviated labels. Estimate with `len(output) / 4` and assert in tests. Sample rendering came to ~392 tokens for a comprehensive format, so budget is comfortable.
**Warning signs:** Test assertion failing on token estimate.

## Code Examples

### CSW% Computation per Pitch Type in Window
```python
# Source: Verified from Statcast data inspection
_CSW_DESCRIPTIONS = frozenset({
    "called_strike", "swinging_strike", "swinging_strike_blocked"
})

def _compute_csw_per_type(statcast: pl.DataFrame, window_dates: list) -> dict[str, float]:
    """CSW% per pitch_type in the window."""
    window = statcast.filter(pl.col("game_date").is_in(window_dates))
    result = {}
    for pt in window["pitch_type"].unique().to_list():
        pt_pitches = window.filter(pl.col("pitch_type") == pt)
        total = len(pt_pitches)
        csw = pt_pitches.filter(
            pl.col("description").is_in(list(_CSW_DESCRIPTIONS))
        ).height
        result[pt] = csw / total * 100.0 if total > 0 else 0.0
    return result
```

### Zone Rate and Chase Rate
```python
# Source: Verified from Statcast zone values (1-9 = zone, 11-14 = outside)
_ZONE_IN = list(range(1, 10))      # Zones 1-9
_ZONE_OUT = [11, 12, 13, 14]       # Outside zones

_SWING_DESCRIPTIONS = frozenset({
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip",
    "hit_into_play", "foul_bunt", "bunt_foul_tip", "missed_bunt",
})

def _compute_zone_chase(statcast: pl.DataFrame, window_dates: list) -> tuple[float, float]:
    """Zone rate and chase rate (O-Swing%) for the window."""
    window = statcast.filter(
        (pl.col("game_date").is_in(window_dates))
        & pl.col("zone").is_not_null()
    )
    total = len(window)
    in_zone = window.filter(pl.col("zone").is_in(_ZONE_IN)).height
    zone_rate = in_zone / total * 100.0 if total > 0 else 0.0

    outside = window.filter(pl.col("zone").is_in(_ZONE_OUT))
    outside_total = len(outside)
    outside_swings = outside.filter(
        pl.col("description").is_in(list(_SWING_DESCRIPTIONS))
    ).height
    chase_rate = outside_swings / outside_total * 100.0 if outside_total > 0 else 0.0

    return zone_rate, chase_rate
```

### Rest Days and Consecutive Days Computation
```python
# Source: Data inspection -- pitcher_days_since_prev_game is null, must compute
from datetime import date

def _compute_rest_days(appearance_dates: list[date]) -> list[int | None]:
    """Rest days between consecutive appearances. First appearance = None."""
    sorted_dates = sorted(appearance_dates)
    result: list[int | None] = [None]
    for i in range(1, len(sorted_dates)):
        rest = (sorted_dates[i] - sorted_dates[i - 1]).days - 1
        result.append(rest)
    return result

def _max_consecutive_days(appearance_dates: list[date]) -> int:
    """Maximum consecutive days pitched."""
    sorted_dates = sorted(appearance_dates)
    consecutive = 1
    max_run = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            consecutive += 1
            max_run = max(max_run, consecutive)
        else:
            consecutive = 1
    return max_run
```

### xRV100 Percentile Ranking
```python
# Source: Data inspection -- pitcher_type.csv has 1,651 unique pitchers
# xRV100 is negative-is-better (prevents runs)
def _compute_xrv100_percentile(
    pitcher_type_csv: pl.DataFrame,
    pitcher_xrv100: float,
    pitch_type: str,
    min_pitches: int = 10,
) -> int:
    """Percentile rank of pitcher's xRV100 for a pitch type vs league."""
    # Weight-average across game_types per pitcher
    type_data = pitcher_type_csv.filter(
        (pl.col("pitch_type") == pitch_type)
        & (pl.col("n_pitches") >= min_pitches)
    )
    weighted = type_data.group_by("pitcher").agg(
        (pl.col("xRV100_P") * pl.col("n_pitches")).sum()
        / pl.col("n_pitches").sum()
    )
    # Count pitchers with worse (higher) xRV100
    n_worse = weighted.filter(pl.col("xRV100_P") > pitcher_xrv100).height
    total = len(weighted)
    return int(n_worse / total * 100) if total > 0 else 50
```

### IP Estimation
```python
# Source: Statcast data -- outs_when_up tracks outs at time of each pitch
def _compute_ip(statcast: pl.DataFrame, game_pk: int) -> str:
    """Compute innings pitched for a single appearance as baseball notation."""
    game = statcast.filter(pl.col("game_pk") == game_pk)
    innings = sorted(game["inning"].unique().to_list())
    n_full_innings = len(innings) - 1  # All but the last are complete

    # Outs in the final inning: max outs_when_up at end of final inning
    # plus outs generated by final-inning events
    final_inning = game.filter(pl.col("inning") == innings[-1])
    # Count out-producing events in the final inning
    out_events = {"strikeout", "field_out", "grounded_into_double_play",
                  "force_out", "sac_fly", "sac_bunt", "fielders_choice"}
    outs_made = final_inning.filter(
        pl.col("events").is_in(list(out_events))
    ).height
    # GIDP counts as 2 outs
    gidp = final_inning.filter(pl.col("events") == "grounded_into_double_play").height
    outs_in_final = outs_made + gidp  # extra out for each GIDP

    total_thirds = n_full_innings * 3 + outs_in_final
    whole = total_thirds // 3
    remainder = total_thirds % 3
    return f"{whole}.{remainder}"
```

## Data Column Reference

### Statcast Columns Used in Phase 3
| Column | Type | Use | Notes |
|--------|------|-----|-------|
| `description` | str | CSW% computation | Values: `called_strike`, `swinging_strike`, `swinging_strike_blocked` for CSW |
| `zone` | int/null | Zone rate, chase rate | 1-9 = in zone, 11-14 = outside, null = ~0.8% of pitches |
| `pitch_type` | str | Per-type breakdowns | Same codes as Phase 2 |
| `game_date` | date | Window filtering | Same pattern as Phase 2 |
| `game_pk` | int | Per-appearance grouping | Unique game identifier |
| `inning` | int | IP computation | Inning number |
| `outs_when_up` | int | Partial IP | Outs recorded at time of pitch |
| `events` | str/null | Out counting for IP | `strikeout`, `field_out`, `grounded_into_double_play`, etc. |

### CSV Columns Used in Phase 3
| File | Column | Use |
|------|--------|-----|
| `pitcher_type.csv` | `xRV100_P`, `xSwing_P`, `xWhiff_P` | Season baseline per pitch type |
| `pitcher_type_appearance.csv` | `xRV100_P`, `xSwing_P`, `xWhiff_P` | Window-level per pitch type per appearance |
| `pitcher_type.csv` (all pitchers) | `xRV100_P`, `n_pitches` | League distribution for percentile ranking |
| `team.csv` | `xRV100_P` | League-average reference point |

### Swing Description Classification
| Description | Is Swing? | Is CSW? | Notes |
|-------------|-----------|---------|-------|
| `called_strike` | No | Yes | Called strike, no swing |
| `swinging_strike` | Yes | Yes | Swing and miss |
| `swinging_strike_blocked` | Yes | Yes | Swing and miss, catcher blocks |
| `foul` | Yes | No | Foul ball |
| `foul_tip` | Yes | No | Foul tip |
| `foul_bunt` | Yes | No | Foul bunt attempt |
| `bunt_foul_tip` | Yes | No | Bunt foul tip |
| `missed_bunt` | Yes | No | Missed bunt attempt |
| `hit_into_play` | Yes | No | Ball put in play |
| `ball` | No | No | Ball |
| `blocked_ball` | No | No | Wild pitch/passed ball |
| `hit_by_pitch` | No | No | HBP |
| `automatic_ball` | No | No | Pitch clock violation |
| `automatic_strike` | No | No | Pitch clock violation |
| `pitchout` | No | No | Intentional ball |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Dict return types | Dataclass return types | Phase 2 decision | All engine functions use dataclasses |
| Separate baseline computation | `_weighted_window_pplus` shared helper | Phase 2 | Reuse for xWhiff/xSwing window computation |
| Print-based output | Structured context model | Phase 3 (this phase) | PitcherContext Pydantic model replaces ad-hoc output |

## Open Questions

1. **IP partial inning edge case: pitcher enters mid-inning**
   - What we know: `outs_when_up` tracks outs at pitch time. Appearances show `first_inning == last_inning` for most of test pitcher's games.
   - What's unclear: If a pitcher enters with 1 out already recorded, `outs_when_up` on their first pitch will be 1. Do they get credit for the full inning or only the outs they recorded?
   - Recommendation: Count only outs generated by the pitcher's events (strikeout, field_out, etc.) rather than relying on outs_when_up difference. This is more accurate for mid-inning entries.

2. **xRV100 minimum pitch threshold for percentile ranking**
   - What we know: pitcher_type.csv has pitchers with as few as 1 pitch of a type. Including them pollutes the distribution.
   - What's unclear: Exact threshold. 10 pitches matches `_MIN_PITCHES` constant but may be too low for stable xRV100.
   - Recommendation: Use 10 pitches (consistent with existing `_MIN_PITCHES`) for now. Can increase later if distributions look noisy.

3. **Token budget validation accuracy**
   - What we know: ~4 chars/token is a rough heuristic. Sample rendering was ~392 tokens for a full context.
   - What's unclear: Exact token count depends on Claude's tokenizer (likely ~3.5-4.5 chars/token for English text with numbers).
   - Recommendation: Use 4 chars/token as specified in decisions. Add a test assertion that `len(to_prompt()) / 4 < 2000`. Actual token count will be validated in Phase 4 when the agent runs.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | CSW% per pitch type in window | unit | `uv run pytest tests/test_engine.py::test_csw_per_type -x` | Wave 0 |
| EXEC-02 | xWhiff and xSwing per pitch type | unit | `uv run pytest tests/test_engine.py::test_xwhiff_xswing_per_type -x` | Wave 0 |
| EXEC-03 | Zone rate vs chase rate | unit | `uv run pytest tests/test_engine.py::test_zone_chase_rate -x` | Wave 0 |
| EXEC-04 | xRV100 percentile ranking | unit | `uv run pytest tests/test_engine.py::test_xrv100_percentile -x` | Wave 0 |
| CTX-01 | Rest days between appearances | unit | `uv run pytest tests/test_engine.py::test_rest_days -x` | Wave 0 |
| CTX-02 | IP and pitch count per appearance | unit | `uv run pytest tests/test_engine.py::test_ip_and_pitch_count -x` | Wave 0 |
| CTX-03 | Consecutive days tracking | unit | `uv run pytest tests/test_engine.py::test_consecutive_days -x` | Wave 0 |
| RPT-01 (partial) | PitcherContext Pydantic model assembly | unit | `uv run pytest tests/test_context.py::test_pitcher_context_assembly -x` | Wave 0 |
| RPT-01 (partial) | to_prompt() renders markdown under 2k tokens | unit | `uv run pytest tests/test_context.py::test_to_prompt_token_budget -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- extend with execution metrics and workload tests (EXEC-01 through CTX-03)
- [ ] `tests/test_context.py` -- new file for PitcherContext model and to_prompt() tests

## Sources

### Primary (HIGH confidence)
- Direct Statcast parquet inspection -- confirmed `description`, `zone`, `outs_when_up`, `events` column values and null rates
- Direct CSV inspection -- confirmed `xRV100_P`, `xWhiff_P`, `xSwing_P`, `xSwSt_P` columns across all 8 aggregation files
- `engine.py` source code -- confirmed dataclass patterns, delta string helpers, `_weighted_window_pplus` helper, `_MIN_PITCHES`, `_COLD_START_STRING` constants
- `data.py` source code -- confirmed PitcherData structure, `_ID_COLS`, weighting pattern
- `tests/test_engine.py` source code -- confirmed TDD pattern with real pitcher 592155 (Booser), assertion style

### Secondary (MEDIUM confidence)
- Token budget heuristic (~4 chars/token) -- specified in CONTEXT.md decisions; approximately correct for Claude's tokenizer on mixed English/numeric text

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all libraries already in use and verified
- Architecture: HIGH - follows established patterns from Phase 2, data columns verified by inspection
- Pitfalls: HIGH - all verified through direct data inspection (null zones counted, description values enumerated, xRV100 polarity confirmed)

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (stable -- static data, no external API changes)
