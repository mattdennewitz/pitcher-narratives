# Select-by-Flag: Category-Bucketed Slate — Design

**Date:** 2026-06-14
**Status:** Approved for planning

## Goal

Replace the morning slate's **role-based** selection structure (up to 10 starters + up to 10 relievers) with a **category-based** one: up to **5 picks per editorial category**, no minimum. This caps any single category and, paired with an explicit anti-clustering nudge in the selector prompt, pushes the slate toward variety instead of a block of near-identical stories.

## Motivation

A model-comparison review of the 2026-06-13 digest found the slate collapsed into one repeated angle: ~7 of 10 capsules were `lab_project` ("elite stuff, no command"), reading like photocopies. The current schema caps **per role** but never **per category**, so nothing stops over-representation. Bucketing the cap by category fixes this at the selection layer.

The four categories already exist on every pick (`CurationPick.category`) and drive the digest header badges; they are simply not used as a selection constraint today.

## Current State

- **`curator.py`** — the selector LLM receives candidates bucketed by role (`STARTERS` / `RELIEVERS` sections) and returns a `CurationSlate` with `starters: list[CurationPick]` and `relievers: list[CurationPick]`, each capped at `_MAX_PICKS_PER_ROLE = 10`. Each `CurationPick` carries `category ∈ {clean_breakout, lab_project, identity_crisis, red_flag}`. A `make_selector_agent` output validator enforces (a) picks are valid candidate IDs and (b) starters come from the STARTERS section / relievers from RELIEVERS.
- **`morning.py`** — iterates `[*slate.starters, *slate.relievers]`, builds a cue per pick, writes summaries, and serializes `slate.model_dump()` into `slate.json`.
- **`digest.py`** — `assemble_digest` renders `_section("Starters", slate.starters)` and `_section("Relievers", slate.relievers)`; `_section` already renders each pick under its category badge via `_CATEGORY_BADGES`. `render_full_board` lists the raw scored board grouped by role.
- **`scout_cli.py`** (`--curate`) — prints the slate grouped as `STARTERS` / `RELIEVERS`.

## New Behavior (the contract)

1. The slate is selected and organized by **category**, not role.
2. **Up to 5 picks per category** (`clean_breakout`, `lab_project`, `identity_crisis`, `red_flag`). Maximum slate size = 20.
3. **No minimum.** A category with no qualifying candidates contributes zero picks; the digest omits empty categories. (Unchanged: the slate must contain at least one pick overall.)
4. **Role (SP/RP) is no longer a selection axis.** It remains available to the writer as a capsule detail (via the appearance/cue), and the raw **Full Board stays role-grouped** (it is the scout's raw output, where role is a real attribute) — out of scope for this change.
5. Categories never pad: as today, ordinary/average outings are not selected just to fill a category.

## Design

### Schema (`curator.py`) — Approach A: flat list + cap validator

`CurationSlate` becomes a single flat list; `category` on each pick stays the single source of truth.

```python
_MAX_PICKS_PER_CATEGORY = 5

class CurationSlate(BaseModel):
    """The morning slate: up to 5 picks per category, at least one overall."""

    picks: list[CurationPick] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "CurationSlate":
        if not self.picks:
            raise ValueError("slate must contain at least one pick")
        counts = Counter(p.category for p in self.picks)
        over = {c: n for c, n in counts.items() if n > _MAX_PICKS_PER_CATEGORY}
        if over:
            raise ValueError(
                f"Too many picks in categories {over}; "
                f"cap is {_MAX_PICKS_PER_CATEGORY} per category."
            )
        return self
```

- `CurationPick` is unchanged (`pitcher_id`, `category`, `angle`, `conviction`, `conviction_reason`).
- `_MAX_PICKS_PER_ROLE` is removed.
- Validation failures raise `ValueError`, which pydantic-ai surfaces to the model as a retry (same mechanism as the existing candidate-membership validator), so an over-quota slate self-corrects.

### Briefing (`curator.py`)

`build_selector_briefing` no longer buckets by role. Candidates are not pre-categorized (the LLM assigns category at selection time), so the briefing is a **single flat, score-ranked list** of scored candidates, each with its fired signals. Role may be shown inline as a per-candidate detail (e.g. `(RHP, RP)`), but there are no `STARTERS` / `RELIEVERS` sections.

### Selector prompt (`curator.py`)

`_SELECTOR_PROMPT` updated:
- Instruction: "select up to **5 per category** across the four categories below" (replacing "up to 10 STARTERS and up to 10 RELIEVERS").
- Keep the existing category hierarchy/definitions (clean_breakout → lab_project → identity_crisis → red_flag) and the "never pad ordinary outings" / "ignore average outings" rules.
- Remove the role-section rules ("starters come ONLY from the STARTERS section…").
- **Add an anti-clustering nudge.** The cap bounds over-representation; this nudge pushes for *variety* so the slate doesn't become a block of near-identical stories. Add a rule to the effect of: "Favor variety. Prefer a spread across categories and distinct stories over many look-alikes. Within a category, when several candidates tell the same story (e.g. multiple 'elite breaking ball, no command' lab projects), keep only the most distinctive or highest-conviction few rather than filling the cap with duplicates. A shorter, varied slate beats a long, repetitive one." This is the only behavioral lever for angle diversity; the per-capsule writer template is out of scope.

### Membership validator (`curator.py`)

`make_selector_agent`'s output validator keeps the **candidate-membership** check (every `pitcher_id` is one of the briefed candidates) and the **no-duplicate-pitcher** check, but drops the role-section enforcement. The per-category cap is handled by the `CurationSlate` validator above.

### Orchestration (`morning.py`)

- `picks = slate.picks` (replacing `[*slate.starters, *slate.relievers]`).
- Log line: "Slate: N picks across K categories" with a per-category breakdown.
- `slate.json` shape changes to `{"game_date", "picks": [ <pick dicts> ], "names": {...}}`. To avoid a double-nested `picks.picks`, serialize the list directly (`slate.model_dump()["picks"]`) under the top-level `"picks"` key rather than dumping the whole model. (Run artifacts are ephemeral outputs, not a stable API; the format change is acceptable.)

### Digest assembly (`digest.py`)

`assemble_digest` renders **one section per non-empty category**, in the editorial hierarchy order, reusing the existing `_section` + `_CATEGORY_BADGES` machinery:

```
## Clean Breakouts      (clean_breakout)
## Lab Projects         (lab_project)
## Identity Crises      (identity_crisis)
## Red Flags            (red_flag)
```

- Section order: `clean_breakout, lab_project, identity_crisis, red_flag` (the prompt hierarchy). Empty categories are omitted.
- Within a category, order picks by **conviction** (high → medium → low), ties broken by the appearance's **interest score** descending (`assemble_digest` already receives `board`/`appearances` to look up scores).
- `render_full_board` is **unchanged** (still role-grouped raw board).

### CLI (`scout_cli.py`, `--curate`)

The `--curate` print loop groups by category instead of `STARTERS`/`RELIEVERS`, using the same hierarchy order and per-pick `[category] name (conviction): angle` line format.

## Out of Scope

- The raw **Full Board** rendering (stays role-grouped).
- The **scout signal** set and scoring (`scout.py`) — unchanged; signals still feed the briefing.
- Any change to the writer/persona prompts or the per-capsule prose.
- A `--per-category-cap` CLI flag — the cap is a fixed constant (5) for now.

## Testing

- **`test_curator.py`**: `CurationSlate` accepts ≤5 per category; rejects >5 in any category (ValueError); rejects empty `picks`; membership + duplicate validators still fire. `build_selector_briefing` emits a flat (non-role-bucketed) list.
- **`test_digest.py`**: `assemble_digest` produces one section per non-empty category in hierarchy order; omits empty categories; orders within a category by conviction then score; `render_full_board` unchanged.
- **`test_morning.py`**: the morning flow iterates `slate.picks`; `slate.json` carries the flat picks; existing `_selector_override` / `_writer_override` test seams still work.
- **`test_scout_cli.py`** (if it covers `--curate`): category-grouped output.
- Update any fixtures/builders that construct a `CurationSlate(starters=…, relievers=…)` to `CurationSlate(picks=…)`.

## Migration Notes

This is a breaking change to the `CurationSlate` shape and the `slate.json` artifact. There are no external consumers of these (run artifacts are regenerated daily; the slate is internal to the pipeline), so no compatibility shim is needed. All in-repo construction/consumption sites (`morning.py`, `digest.py`, `scout_cli.py`, tests) are updated in the same change.
