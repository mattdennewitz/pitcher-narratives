---
name: statcast-data-conventions
description: Use when implementing deterministic movement, release, velocity, or handedness computations over the manifest-covered all_pitches grain.
audience: builder
---

# Emitted Pitch Data Conventions

Pitcher Narratives never opens raw Statcast. Load the validated PitchingPlus
bundle, then compute only from manifest-covered `all_pitches` rows.

## Units and signs

- The emitted `pfx_x` and `pfx_z` fields retain Statcast feet; convert to inches
  exactly once at a typed output boundary.
- `pfx_z` is induced vertical break, not total drop.
- Positive `pfx_x` is toward the catcher's right. Mirror horizontal movement
  before pooling hands: `pfx_x` for LHP, `-pfx_x` for RHP.
- `arm_angle` is hand-symmetric: 0° is sidearm and 90° is over the top.

## Source and frame rules

- Use `load_pitchingplus_bundle`, `load_emitted_grain`, or
  `load_pitcher_data`; never derive a filesystem path for an upstream input.
- `PitcherData.pitches` contains emitted rows across requested scoring seasons.
- Select exact games with the canonical `FrameSelection`; a calendar date alone
  is not an appearance identity.
- Treat absent columns, manifest mismatch, and cross-grain row loss as
  unavailable or incompatible data. Never fall back to another file.

## Probe recipe

```python
from pitcher_narratives.data import load_emitted_grain

pitches = load_emitted_grain("all_pitches")
sample = pitches.select(cols)
```

Assertions must use the same manifest-covered frame as production code. Do not
encode values measured from an unregistered upstream file.
