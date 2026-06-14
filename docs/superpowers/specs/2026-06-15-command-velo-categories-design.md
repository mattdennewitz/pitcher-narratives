# command_breakout + velo_drop Categories — Design

**Date:** 2026-06-15
**Status:** Approved for planning

## Goal

Add two editorial categories to the morning slate — `command_breakout` ("found the zone") and `velo_drop` (durability watch) — to drain the chronically over-cap `lab_project` / `red_flag` buckets into more specific stories and fill the structurally under-filled positive-development and concern axes.

## Motivation

A 14-day day-by-day scout analysis (2026-05-31 → 06-13) of category demand against the per-category cap of 5 found:

| | clean_breakout | lab_project | identity_crisis | red_flag (P+ swing pool) |
|---|---|---|---|---|
| avg eligible/day | 1.1 | 9.6 | 2.3 | 16.7 |
| days over cap-5 (of 14) | 0 | 13 | 0 | 14 |

The cap is not too small — it is **mis-sized across unequal categories**. `clean_breakout` and `identity_crisis` chronically under-fill while `lab_project` overflows every single day (the "photocopy" problem the cap was built to bound). Raising `lab_project`'s cap would re-break the variety the cap protects. The correct lever is **subdividing the overloaded buckets into more specific categories**, not longer caps.

Two specific gaps surfaced:

1. **No home for a command surge.** `splus_lplus_divergence` only fires on *opposite* S+/L+ moves; `development_opportunity` only on stuff-up/command-down. A pitcher whose Location+ jumped (command arrived) is measured by *nothing* and never reaches the curator. This is the inverse of `lab_project` ("elite stuff, no feel") and is high fantasy value — command stabilization → fewer walks → better ratios.

2. **No home for a velocity loss.** `velo_delta` is symmetric (±1.5 mph) but `clean_breakout` only consumes the *up* direction. A velo loss lands in `red_flag` at best, but `red_flag` means "tracking artifact," not "arm health." These are different stories, and a velo-loss flag is roster-actionable.

## Current State

- **`scout.py`** — emits signals from per-family `_check_*` functions, weighted by `_WEIGHTS`. `_check_velo_delta` compares **fastball** game velo vs season, symmetric at `_VELO_THRESHOLD = 1.5`, emitting `velo_delta` with an "up"/"down" direction in its detail. `_check_development_opportunity` emits `development_opportunity` per pitch type when `S+ >= _DEV_SPLUS_MIN (110)` and `L+ <= _DEV_LPLUS_MAX (80)`, gated by `n_pitches >= _MIN_TYPE_PITCHES (3)`. There is **no** Location+ surge check.
- **`curator.py`** — the LLM selector reads a flat, score-ranked briefing of scored candidates (each with its fired signals) and returns a `CurationSlate` of `CurationPick`s. `CurationPick.category` is a `Literal[...]` over the four categories. `_SELECTOR_PROMPT` defines a four-item category hierarchy. `_MAX_PICKS_PER_CATEGORY = 5`. `clean_breakout` is **not** a scout signal — it is a category the LLM *infers* from `velo_delta`(up) + `pplus_swing`(up).
- **`digest.py`** — `_CATEGORY_ORDER`, `_CATEGORY_SECTION_TITLES`, `_CATEGORY_BADGES` (all four-keyed) drive section grouping; `assemble_digest` renders one section per non-empty category in order, picks ordered by `_CONVICTION_RANK` then interest score.
- **`scout_cli.py`** (`--curate`) — groups printed picks by category, driven off the same order.

## New Behavior (the contract)

1. Two new categories exist end-to-end: `command_breakout` and `velo_drop`.
2. A new scout signal `command_surge` makes Location+ surges visible to the scorer and curator.
3. `velo_drop` adds **no** scout signal — it is a curator-inferred category, the exact structural mirror of `clean_breakout`.
4. The per-category cap is unchanged (`_MAX_PICKS_PER_CATEGORY = 5`); the slate may now hold up to 6 categories (max 30 picks).
5. The editorial hierarchy/order becomes: `clean_breakout`, `command_breakout`, `lab_project`, `identity_crisis`, `velo_drop`, `red_flag` (positive development → ambiguous → concern).

## Design

### The driving asymmetry

`clean_breakout` is a curator *category* inferred from signals that already fire (`velo_delta`, `pplus_swing`). The two new categories split on whether their ingredients are already measured:

| Category | New scout signal? | Why |
|---|---|---|
| `command_breakout` | **Yes** — `command_surge` | An L+ jump is measured by nothing today; without a signal these outings never score and never reach the curator. |
| `velo_drop` | **No** | `velo_delta`(down) and `pplus_swing`(down) already fire and already score; pure curator-layer category. |

### New `command_surge` signal (`scout.py`)

Delta-based mirror of `development_opportunity` (a breakout is a change, so it keys on the jump, not a static snapshot):

```python
_COMMAND_SURGE_DELTA = 15   # L+ points gained vs season baseline
_COMMAND_GOOD_LPLUS = 110   # game L+ floor — command is now a genuine strength

def _check_command_surge(
    game_types: pl.DataFrame,
    pitcher_type_bl: pl.DataFrame,
) -> list[Signal]:
    """Check for pitches whose Location+ surged vs season — command arrived."""
    signals: list[Signal] = []
    for row in game_types.iter_rows(named=True):
        pt = row["pitch_type"]
        if row.get("n_pitches", 0) < _MIN_TYPE_PITCHES:
            continue  # too few pitches for a reliable L+ grade
        bl_row = pitcher_type_bl.filter(pl.col("pitch_type") == pt)
        if bl_row.is_empty():
            continue
        bl = bl_row.row(0, named=True)
        game_l = row.get("L+")
        season_l = bl.get("L+")
        if game_l is None or season_l is None:
            continue
        l_delta = float(game_l) - float(season_l)
        if l_delta >= _COMMAND_SURGE_DELTA and float(game_l) >= _COMMAND_GOOD_LPLUS:
            signals.append(Signal(
                "command_surge",
                _WEIGHTS["command_surge"],
                f"{pt}: L+ {l_delta:+.0f} (now {float(game_l):.0f}) — found the zone",
            ))
    return signals
```

- `_WEIGHTS["command_surge"] = 3.5` (matches `development_opportunity`).
- Wired into the scout's per-appearance signal assembly alongside the other `_check_*` calls (same pattern; reads the same `game_types` / `pitcher_type_bl` frames `_check_development_opportunity` already receives).
- Reuses `_MIN_TYPE_PITCHES = 3` for small-sample protection (consistent with the existing per-pitch-type checks).

### `velo_drop` — curator-inferred, no scout change

No signal, no constant. Defined in `_SELECTOR_PROMPT` as the mirror of `clean_breakout`: **FB velo ↓1.5 + overall stuff down (P+/S+)**. The curator reads the existing `velo_delta`(down) + `pplus_swing`(down) lines in the briefing and assigns the category. A dip where the stuff held does not carry `pplus_swing`(down), so it correctly does not qualify (the corroboration filters benign one-game dips — cold day, more breaking balls, normal fatigue).

### Curator (`curator.py`)

- `CurationPick.category` `Literal` gains `"command_breakout"` and `"velo_drop"`.
- `_SELECTOR_PROMPT` category hierarchy is rewritten to six items in editorial order, adding:
  - `command_breakout`: "A jump in command (Location+) on a pitch that now locates well — the inverse of a lab project. Command has arrived even if the stuff was already there."
  - `velo_drop`: "A fastball velocity loss (1.5+ mph) where the stuff eroded with it (P+/S+ down) — a durability concern, distinct from a tracking artifact. If the velo dipped but the stuff held, it is NOT a velo_drop."
- The existing rules block (pick only from candidates, ≤5 per category, never pad, favor variety, one-sentence angle + conviction) is unchanged.
- `_MAX_PICKS_PER_CATEGORY` unchanged at 5.

### Digest + CLI (`digest.py`, `scout_cli.py`)

- `_CATEGORY_ORDER` becomes `["clean_breakout", "command_breakout", "lab_project", "identity_crisis", "velo_drop", "red_flag"]`.
- `_CATEGORY_SECTION_TITLES` gains `command_breakout → "Command Breakouts"`, `velo_drop → "Velocity Drops"`.
- `_CATEGORY_BADGES` gains `command_breakout → "[COMMAND BREAKOUT]"`, `velo_drop → "[VELO DROP]"`.
- `assemble_digest`, `_section`, and `scout_cli --curate` grouping require no logic change — they iterate `_CATEGORY_ORDER` and key into the maps, so adding entries is sufficient. Empty categories are still omitted.

## Testing

- **`test_scout.py`**:
  - `command_surge` fires when a pitch type's `L+` is `+15` or more above season and game `L+ >= 110`, with `n_pitches >= 3`.
  - Does not fire on a sub-15 surge, on a surge that lands below 110, or on a pitch type with `n_pitches < 3` (small-sample gate).
  - A built appearance carrying a qualifying surge exposes the `command_surge` signal and a non-zero score contribution.
- **`test_curator.py`**:
  - `CurationPick(category="command_breakout")` and `CurationPick(category="velo_drop")` validate; an invalid category still rejects.
  - The cap validator still rejects a 6th pick within any single category.
  - A slate mixing the new categories round-trips through `select_slate`.
- **`test_digest.py`**:
  - `assemble_digest` renders "Command Breakouts" and "Velocity Drops" sections in hierarchy order when picks of those categories are present.
  - Empty new categories are omitted.
  - Within a new category, picks order by conviction then score (existing behavior, now exercised on the new keys).

## Out of Scope

- `quiet_riser` (the third proposed category from the analysis) — deferred to a later spec.
- The dead `walk_rate_pplus_contradiction` (0 fires in 14 days), and the `hard_hit_spike` / `workload_flag` weights that have no `_check_*` function — these are adjacent dead-signal cleanup, tracked separately.
- Any retuning of existing thresholds, weights, or the cap value beyond adding `command_surge`.
- Changes to the writer/persona prompts or per-capsule prose.

## Migration Notes

`command_surge` is purely additive (new signal, new weight key, new categories). The `slate.json` artifact gains two possible `category` values but its shape is unchanged. The `CurationSlate` schema change (two new Literal members) is backward-compatible with existing four-category slates. No external consumers; run artifacts regenerate daily.
