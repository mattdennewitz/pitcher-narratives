# Phase 23: Engine Foundation & Data Enrichment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 23-engine-foundation-data-enrichment
**Areas discussed:** Count state bucket definitions, Arm angle computation & presentation, Percentile tag format, Count splits prompt density

---

## Count State Bucket Definitions

### Q1: How should balls/strikes counts map to the four buckets?

| Option | Description | Selected |
|--------|-------------|----------|
| Standard sabermetric | Ahead: strikes > balls. Behind: balls > strikes. Even: balls == strikes. Two-strike: any 2-strike count. Two-strike overlaps with other buckets. | ✓ |
| Mutually exclusive buckets | No overlap. Two-strike takes priority over ahead/even. Every pitch in exactly one bucket. | |
| You decide | Claude picks best approach. | |

**User's choice:** Standard sabermetric (overlapping two-strike)
**Notes:** None

### Q2: Should the first pitch (0-0) get its own tracking?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate first-pitch tracking | Track 0-0 separately as 5th bucket. 0-0 appears in both even and first_pitch. Feeds Phase 24 Approach Specialist. | ✓ |
| Just 'even' bucket | 0-0 stays in even with 1-1 and 2-2. Simpler model. | |
| You decide | Claude picks based on Phase 24 needs. | |

**User's choice:** Separate first-pitch tracking
**Notes:** None

### Q3: Small sample threshold — suppress delta only or entire bucket?

| Option | Description | Selected |
|--------|-------------|----------|
| Suppress delta only | Show raw usage rates, don't compute window-vs-season delta. | ✓ |
| Suppress entire bucket | Don't include bucket at all if under threshold. | |
| You decide | Claude picks. | |

**User's choice:** Suppress delta only
**Notes:** None

### Q4: Per-pitch-type inner filtering within buckets?

| Option | Description | Selected |
|--------|-------------|----------|
| Bucket-level threshold only | <10 threshold on bucket total. Individual pitch type rates always shown. | ✓ |
| Dual threshold | Both bucket-level (>=10) and per-pitch-type (>=3). | |
| You decide | Claude picks. | |

**User's choice:** Bucket-level threshold only
**Notes:** None

---

## Arm Angle Computation & Presentation

### Q1: Single per appearance or per pitch type?

| Option | Description | Selected |
|--------|-------------|----------|
| Single per appearance | One arm angle from mean release_x/release_z across all pitches. | |
| Per pitch type | Separate arm angle per pitch type from existing per-type release point data. | ✓ |
| Both | Single aggregate plus per-pitch-type. | |

**User's choice:** Per pitch type
**Notes:** None

### Q2: Include slot label or just numeric degrees?

| Option | Description | Selected |
|--------|-------------|----------|
| Degrees + slot label | Numeric angle plus human-readable slot (overhand, 3/4, sidearm, submarine). | ✓ |
| Degrees only | Just the numeric angle and delta. | |
| You decide | Claude picks for Phase 25 Trend Specialist support. | |

**User's choice:** Degrees + slot label
**Notes:** None

---

## Percentile Tag Format

### Q1: New outlier tag format?

| Option | Description | Selected |
|--------|-------------|----------|
| Percentile + direction | Replace z-score with percentile, keep direction. | |
| Percentile only | Just percentile with NORMAL/OUTLIER. Drop direction. | |
| Percentile + direction + z-score | Keep all three: percentile, direction, and z-score. | ✓ |

**User's choice:** Percentile + direction + z-score (maximum information)
**Notes:** None

### Q2: Percentile computed against full league or split by handedness?

| Option | Description | Selected |
|--------|-------------|----------|
| Full league | Against all pitchers for that pitch type. Matches existing xRV100 pattern. | |
| Split by handedness | LHP vs LHP, RHP vs RHP. More accurate for metrics where distributions differ. | ✓ |
| You decide | Claude picks based on data availability. | |

**User's choice:** Split by handedness
**Notes:** p_throws column already available in Statcast data (data.py:61)

---

## Count Splits Prompt Density

### Q1: How should count splits appear in the context document?

| Option | Description | Selected |
|--------|-------------|----------|
| Notable shifts only | Only render buckets where a pitch type shifted 10+ pp. | |
| Full table, all buckets | Complete usage rates for every pitch type in every bucket. | |
| Hybrid: summary + full appendix | Notable shifts in main section, full table in raw data appendix. | ✓ |

**User's choice:** Hybrid (summary + full appendix)
**Notes:** Aligns with Phase 24 PIPE-05 raw data appendix plan

### Q2: Notable shift threshold?

| Option | Description | Selected |
|--------|-------------|----------|
| 10+ percentage points | Matches Phase 24 PIPE-02 lead-story threshold. | ✓ |
| 5+ percentage points | Lower bar, catches more shifts. | |
| You decide | Claude picks based on PIPE-02 alignment. | |

**User's choice:** 10+ percentage points
**Notes:** Intentional alignment with Phase 24 PIPE-02

---

## Claude's Discretion

- atan2 formula specifics and slot label boundary fine-tuning
- CountSplits Pydantic model field naming and structure
- How arm angle fields attach to PitchTypeSummary vs separate model
- League baseline handedness grouping implementation details

## Deferred Ideas

None — discussion stayed within phase scope
