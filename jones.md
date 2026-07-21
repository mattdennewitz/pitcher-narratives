# Why Jared Jones's fastball grades 92 Stuff+

**Short version:** A 92 S+ four-seamer is *slightly below average for a four-seam* — not the dramatic failure "92 vs 100" implies. Jones throws 98.5 with elite spin, but the pitch moves like an ordinary fastball, and the Stuff+ model prices pitches on the outcomes their **shape** predicts, not on the radar-gun reading. Ordinary shape → ordinary bat-missing → an ordinary, slightly-below-par grade, no matter how hard it's thrown.

Data: `var/aggs/2026-pitcher_type.csv` + `var/statcast/2026.parquet` (683003, 4-Seam, **MLB** 244-pitch grading row / 245 Statcast pitches). Baselines are **MLB four-seamers only** — mixing in his A/AAA rows contaminates the comparison.

---

## 1. Read the grade against the right baseline

Stuff+ is scaled so **100 = the average of *all* pitch types.** Four-seam fastballs, as a class, are among the most hittable pitches in baseball and grade *below* that line — the MLB four-seam average is about **97**, not 100:

| | Jones FF | MLB FF avg (n=465) |
|---|---|---|
| **S+ (Stuff+)** | **92.3** | **97.4** (mean), 10.8 SD |
| xRV100_S (runs/100, + = costly) | +0.39 | +0.13 |
| xWhiff_S | 22.0% | 22.9% |
| xSwing_S | 49.2% | 47.7% |

So Jones's fastball sits about **half a standard deviation below the four-seam average** — genuinely a touch below-par *for a fastball*, and a bit more costly than the class norm (+0.39 vs +0.13 xRV100). But the "92" looks far worse against the all-pitch 100 than it is against its own class. The gap only widens next to his own secondaries (curveball 115, slider 109) — but those are breaking balls, which live above the 100 line.

## 2. Why elite velocity doesn't rescue the grade

The model grades a chain: **physical pitch → predicted outcomes → runs.** Velocity only helps to the extent it buys missed bats and weak contact. Here's Jones's four-seam shape vs. the MLB four-seam distribution (±1.5 SD = OUTLIER):

| Trait | Jones | MLB FF mean | z | Verdict |
|---|---|---|---|---|
| Velocity | **98.6 mph** | 94.6 | **+1.78** | **OUTLIER** (plus-plus) |
| Spin | **2,559 rpm** | 2,310 | **+1.76** | **OUTLIER** (high) |
| Vertical break / "ride" (IVB) | 15.8 in | 15.6 | +0.07 | NORMAL |
| Horizontal break (arm-side run) | −8.6 in | −3.5 | −0.68 | NORMAL |

This is the whole story. The velocity and spin are genuinely elite, but **neither converts into unusual movement.** With 2,559 rpm you'd expect carry well above average; instead the ride is a completely ordinary 15.8 inches (+0.07 SD — dead league-average). The spin efficiency simply isn't there. So the pitch arrives at ~98 on a trajectory that looks like an average fastball's — no separation from what a hitter's eye expects out of that arm slot, and no deception to price.

## 3. The outcomes confirm it — hitters track it fine

Because the shape is generic, the model's outcome predictions come out around the fastball average, and the swing profile tilts slightly *against* him:

- **xWhiff_S 22.0%** — just below the four-seam average (22.9%). Elite velocity is buying an average, not elevated, whiff rate.
- **xSwing_S 49.2%** — *above* the 47.7% average. Hitters recognize the pitch and attack it a bit more, not less.
- Average-minus whiffs + above-average swings → a **positive (costly) xRV100_S of +0.39**, worse than the +0.13 class norm — exactly what a sub-average S+ prices to. The signs are internally consistent: sub-100 S+ pairs with a costly (positive) xRV100_S.

## 4. The takeaway (and the contrast)

The 92 is not the model flunking a 98-mph heater — it's the model correctly saying: *this is a slightly-below-average four-seamer that happens to be thrown very hard.* The elite velocity is what keeps it near the fastball average rather than dragging it down into Stuff+ basement territory, but at the major-league level, velocity without a bat-missing shape gets largely absorbed by hitters.

The proof is one row over in his own arsenal: the **curveball grades 115 S+ on utterly normal 85-mph velocity and normal break**, because it misses bats (xWhiff 44%) and keeps hitters defensive (xSwing 40%). Stuff+ rewards deception and empty swings — his fastball generates neither beyond the four-seam norm, so it grades as what it is: an ordinary fastball with an extraordinary radar reading.
