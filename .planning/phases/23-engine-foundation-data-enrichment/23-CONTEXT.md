# Phase 23: Engine Foundation & Data Enrichment - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Engine produces count-state usage splits, arm angle metrics, and percentile-ranked outlier tags so downstream agents (specialists, writer, auditor) have richer analytical inputs. This phase adds computation and data model fields — no agent prompt changes or pipeline re-architecture.

</domain>

<decisions>
## Implementation Decisions

### Count State Bucket Definitions
- **D-01:** Standard sabermetric buckets: Ahead (strikes > balls), Behind (balls > strikes), Even (balls == strikes), Two-strike (any count with 2 strikes). Two-strike overlaps with other buckets — a pitch can appear in both its primary bucket and two-strike.
- **D-02:** Separate first-pitch (0-0) tracking as a 5th bucket dimension, in addition to 0-0 appearing in the Even bucket. Five total buckets: ahead, behind, even, two_strike, first_pitch.
- **D-03:** Small sample threshold (<10 pitches) suppresses the delta only, not the entire bucket. Raw usage rates still shown with a "small sample" flag.
- **D-04:** Bucket-level threshold only — no per-pitch-type inner threshold. All pitch type rates shown regardless of individual count within a bucket, as long as the bucket total >= 10.

### Arm Angle Computation
- **D-05:** Arm angle computed per pitch type (not a single aggregate per appearance). Uses atan2 on existing per-type release_x/release_z averages already in PitchTypeSummary.
- **D-06:** Arm angle includes both numeric degrees and a human-readable slot label. Slot ranges: Overhand (>50°), 3/4 (35-50°), Sidearm (15-35°), Submarine (<15°).
- **D-07:** Window-vs-season delta string computed per pitch type for arm angle, following the existing delta string pattern.
- **D-07a:** Phase 23 uses raw atan2(release_z, abs(release_x)) — no height normalization. Slot labels may shift for extreme-height pitchers (6'10" vs 5'10" same slot = different raw angle). Height-normalized arm angle deferred to Phase 25 if pitcher height data becomes available.

### Percentile Tag Format
- **D-08:** Outlier tags include percentile rank, direction, AND z-score (all three). Format: `OUTLIER - 98th percentile (above avg, z=+2.3)` / `NORMAL - 65th percentile (z=+0.4)`.
- **D-09:** Percentile computed split by pitcher handedness (LHP vs RHP), not full-league. Uses existing `p_throws` column from Statcast data to partition the league baseline population.

### Release Point Baseline Extension
- **D-12:** LeagueBaseline must be extended with release point physical averages and standard deviations: `avg_release_x`, `release_x_std`, `avg_release_z`, `release_z_std`, `avg_extension`, `extension_std`. Without these, `outlier_tag()` cannot compute percentiles for release point metrics — only velo and movement would get percentile tags. This is required to support claims like "99th percentile release point" in narratives.

### Count Splits Prompt Rendering
- **D-10:** Hybrid rendering: notable shifts (10+ pp from season average) in the main context section, full usage table in a raw data appendix. This aligns with Phase 24's PIPE-05 raw data appendix plan.
- **D-11:** Notable shift threshold is 10 percentage points, matching Phase 24's PIPE-02 Approach Specialist lead-story threshold.
- **D-13:** CountSplits summary (10pp shifts) MUST render directly adjacent to PlatoonMix in the prompt — not separated by release point or other data. Causal analysis (e.g., "usage against righties" + "usage when ahead") requires both data points within the same visual eye-span of the context window. If separated by 1000+ tokens, the LLM is less likely to connect platoon and count-state patterns.

### Claude's Discretion
- Slot label boundary fine-tuning (exact degree thresholds)
- CountSplits Pydantic model field naming and structure
- How arm angle fields attach to PitchTypeSummary vs a separate model
- League baseline handedness grouping implementation details
- Extension column availability check (avg_extension/extension_std may need graceful fallback if column missing from some datasets)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — ENG-01 through ENG-05 define the five deliverables for this phase

### Existing Engine Code
- `src/pitcher_narratives/engine.py` §294 — Current `outlier_tag()` function (z-score based, to be replaced with percentile)
- `src/pitcher_narratives/engine.py` §832 — `PitchTypeSummary` model (arm angle fields attach here or alongside)
- `src/pitcher_narratives/engine.py` §1227-1242 — Existing `release_x`/`release_z` fields on pitch type detail (arm angle input)
- `src/pitcher_narratives/engine.py` §1867 — `_compute_xrv100_percentile()` (existing percentile pattern to follow)
- `src/pitcher_narratives/engine.py` §2801 — `balls`/`strikes` columns in Statcast data (count splits input)

### Context Assembly
- `src/pitcher_narratives/context.py` §52 — `PitcherContext` model (new fields wired here)
- `src/pitcher_narratives/context.py` — `to_prompt()` rendering (count splits + arm angle rendering target)

### Pipeline (read-only reference)
- `src/pitcher_narratives/pipeline.py` §448 — Current NORMAL/OUTLIER tag rendering in specialist inputs (will consume new percentile format)

### Data Layer
- `src/pitcher_narratives/data.py` §61 — `p_throws` column loaded from Statcast (handedness for percentile splits)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `outlier_tag()` at engine.py:294 — function signature and call sites stay the same, implementation changes to add percentile
- `_compute_xrv100_percentile()` at engine.py:1867 — pattern for percentile computation against league population
- Per-type `window_release_x`/`window_release_z` and `season_release_x`/`season_release_z` already on PitchTypeSummary — direct input for atan2 arm angle
- `_stand_to_platoon()` at engine.py:677 — demonstrates existing handedness-aware logic
- `render_league_baselines()` at engine.py:305 — pattern for rendering engine output into prompt text
- Existing delta string pattern (qualitative trend strings) used throughout engine.py — arm angle deltas follow this

### Established Patterns
- Pydantic dataclasses for all engine output models (PitchTypeSummary, ExecutionMetrics, etc.)
- Window-vs-season comparison with qualitative delta strings
- `__all__` exports in engine.py for public API
- LeagueBaseline computation from pitcher_type CSVs with season grouping

### Integration Points
- PitcherContext.to_prompt() in context.py is the rendering target
- pipeline.py build_specialist_input() consumes NORMAL/OUTLIER tags — will see new percentile format automatically
- report.py also uses outlier_tag() — will inherit changes

</code_context>

<specifics>
## Specific Ideas

- 10pp threshold for "notable" count-state shifts aligns intentionally with Phase 24's PIPE-02 Approach Specialist lead story threshold — keep these in sync
- Hybrid prompt rendering (notable shifts + full appendix) is designed to feed Phase 24's raw data appendix pattern (PIPE-05) — the appendix structure should be reusable
- Handedness-split percentiles are more accurate for metrics like velocity where LHP/RHP distributions differ meaningfully
- CountSplits summary adjacent to PlatoonMix enables "Valdez-style" causal analysis — the LLM needs both in the same eye-span to connect platoon strategy with count-state behavior
- Release point baseline extension (D-12) enables "99th percentile release point" claims in the McLean/Skenes style — without it, only velo/movement get percentile tags
- Raw atan2 arm angle is a known approximation (tall vs short pitchers) but good enough for Phase 23; height normalization is a Phase 25 refinement if data exists

</specifics>

<deferred>
## Deferred Ideas

- **Height-normalized arm angle** — Normalize release_z against pitcher height to isolate arm slot from stature. Deferred to Phase 25 (requires pitcher height data, which may not be in Statcast). Raw atan2 is sufficient for Phase 23.

</deferred>

---

*Phase: 23-engine-foundation-data-enrichment*
*Context gathered: 2026-04-04*
