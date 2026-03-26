# Feature Research

**Domain:** LLM-generated pitcher scouting narrative reports (MLB, Statcast + Pitching+ data)
**Researched:** 2026-03-26
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

A pitcher report that omits any of these feels incomplete to anyone with sabermetric literacy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Fastball quality summary** | Foundation of every pitching assessment. Velo baseline, recent trend, within-game variance, and shape (IVB/HB) are the first things any analyst looks at. | LOW | Data available: `release_speed`, `pfx_x`, `pfx_z` from Statcast; S+ from aggs. Compute season baseline vs. appearance avg/peak. |
| **Arsenal inventory with usage rates** | Reader needs to know what the pitcher throws and how often. Standard in every Savant player page and scouting report. | LOW | Group by `pitch_type` in Statcast. P+ aggs have per-pitch-type breakdowns. Include velo ranges and primary movement profile per pitch. |
| **Usage rate deltas (recent vs. baseline)** | The *change* in arsenal mix is more interesting than the mix itself. "He's throwing more sliders" is the insight, not "he throws 22% sliders." | MEDIUM | Compare appearance-level usage from `pitcher_type_appearance` aggs against season baselines from `pitcher_type`. Compute delta + trend direction string. |
| **Platoon split awareness** | Pitchers adjust arsenals against LHB vs. RHB. A report that ignores platoon splits misses half the story. | MEDIUM | `pitcher_type_platoon` and `pitcher_type_platoon_appearance` aggs provide this directly. Narrative should flag when a pitch is used exclusively or predominantly against one side. |
| **Stuff+ / Location+ / Pitching+ scores per pitch** | These ARE the project's core data advantage. Omitting them defeats the purpose. Scale to 100 = average; 20-80 variants available. | LOW | Direct from aggs. Display at season, appearance, and per-pitch-type grain. Flag when appearance deviates significantly from season. |
| **Execution metrics: CSW%, zone rate, chase rate** | Standard modern pitcher evaluation metrics. CSW (called strikes + whiffs) is the single best quick-read on a pitcher's effectiveness. | MEDIUM | Derivable from Statcast pitch-level data (`description` field for called strikes, swinging strikes). xWhiff and xSwing from P+ aggs provide modeled versions. |
| **Appearance-level performance summary** | The report's anchor: how did this outing go? IP equivalent, batters faced, K/BB, runs, pitch count. | LOW | Aggregate from Statcast appearance data. Context for everything else. |
| **Starter vs. reliever detection and adapted structure** | Starters and relievers have fundamentally different report structures. A starter report discusses TTO penalty, stamina, deep pitch mix. A reliever report discusses workload, rest days, and shorter-window trends. | MEDIUM | Auto-detect from appearance patterns (IP per appearance). Already specified in PROJECT.md. Starters get "last start deep dive" + "recent starts trend." Relievers get "last N appearances" + rest pattern. |
| **Trend context (recent window vs. season)** | Raw numbers without context are meaningless. Every metric needs "compared to what?" framing. | MEDIUM | The lookback window (`-w` flag) defines "recent." Pre-compute deltas: appearance vs. season, recent window vs. season. Generate qualitative trend strings ("Significant Increase", "Stable", "Sharp Decline"). |
| **Data tables alongside prose** | Pure narrative buries the numbers. Pure tables lack insight. The combination is what scouts and analysts actually use. | LOW | Pydantic schema should support both prose sections and embedded data tables. Already specified in PROJECT.md active requirements. |

### Differentiators (Competitive Advantage)

These features move the report from "generated summary" to "genuinely insightful analysis." They align with the project's core value of reading like a scout wrote it.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Pitch-level P+/S+/L+ outlier detection** | The `all_pitches` agg has 143K individual pitch scores. Surfacing "his 3rd-inning slider to Judge was his best pitch of the season (P+ 142)" gives the report a granularity no human scout matches. | MEDIUM | Query `all_pitches` for appearance, find pitches >2 SD above/below pitcher's mean for that pitch type. Pair with game context (count, batter, outcome) from Statcast. |
| **Within-game velocity arc narrative** | Velocity typically peaks around pitch 20, then declines. Describing the *shape* of the velo curve ("held 95+ through 80 pitches, unusual for him" or "lost 2 mph in the 5th, earlier than typical") adds real analytical value. | MEDIUM | Bin pitches by game progression (inning or pitch count bucket). Compute mean fastball velo per bin. Compare to pitcher's typical arc from other appearances in window. |
| **Movement shape change detection** | "His slider lost 2 inches of horizontal sweep compared to season average" is the kind of observation that makes a report feel scouted. Shape changes often explain outcome changes. | MEDIUM | Compare appearance-level pfx_x/pfx_z means per pitch type against season baselines. Flag deviations beyond a threshold (e.g., >1 inch). Correlate with S+ changes. |
| **First-pitch and count-state tendencies** | Knowing a pitcher throws first-pitch fastballs 72% of the time (up from 60%) reveals strategic shifts. Two-strike pitch selection tells you about put-away confidence. | HIGH | Requires filtering Statcast by `balls`/`strikes` columns to reconstruct count states. Group pitch selection by count bucket (0-0, ahead, behind, even, two-strike). Compare appearance to season. |
| **xRV100-driven pitch effectiveness ranking** | Rather than grading pitches by vibes, rank by expected run value per 100 pitches. "His changeup was his best pitch by xRV100 despite throwing it only 14% of the time" is actionable. | LOW | xRV100 available directly in P+ aggs at per-pitch-type grain. Rank and narrate. |
| **Qualitative scout-language flags** | Instead of "IVB decreased 1.3 inches," write "fastball flattened out." Instead of "chase rate 38%," write "excellent chase generation." Translating numbers into scout vocabulary. | MEDIUM | Build a mapping layer: metric thresholds to qualitative descriptors. e.g., chase rate >35% = "elite chase," velo drop >2mph = "significant velocity fade." Embed in prompt schema. |
| **Rest and workload context (relievers)** | "Third appearance in four days, velocity down 1.5 mph from first appearance in the stretch" connects workload to performance. Critical for reliever assessment. | MEDIUM | Compute days between appearances from game dates. Correlate with velo/stuff metrics. Flag when workload is heavy (back-to-back, 3-in-4, etc.) and performance deviates. |
| **Times through order analysis (starters)** | Performance typically degrades 2nd and 3rd time through. Reporting whether *this pitcher* follows that pattern, and whether *this start* showed it, is analytically rich. | HIGH | Requires reconstructing batting order position from Statcast (using `at_bat_number` or `batter` sequence). Group metrics by 1st/2nd/3rd TTO. Compare to pitcher's season TTO splits. |
| **Key matchup highlights** | "Struck out Soto on three sliders after going fastball-only in their first meeting" adds narrative texture. Human scouts always note signature matchups. | HIGH | Requires joining pitcher appearance data with notable batter names. Identifying "notable" is subjective -- could use batter WAR/OPS thresholds or simply pick the highest-leverage ABs by WPA. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Season-over-season comparisons** | "How does 2026 compare to 2025?" is a natural question. | Out of scope per PROJECT.md (single-season 2026 data only). Adding multi-year data multiplies data pipeline complexity 3-4x and distracts from the core value of *recent appearance* analysis. | Frame everything relative to 2026 season baseline. "His slider is 15% better than his season average" is actionable without historical data. |
| **Batter-side analysis / matchup recommendations** | "What should the lineup do against this pitcher?" is the flip side of pitcher scouting. | Doubles the scope. Batter analysis requires different data models, different narrative structure, different expertise. Explicitly out of scope in PROJECT.md. | Mention batter handedness in platoon splits. Note high-leverage at-bat outcomes. Do not prescribe batting strategies. |
| **Pitch-by-pitch game replay narrative** | Every pitch described in sequence, like a play-by-play. | 90-120 pitches per start generates 3000+ words of monotonous sequence. No one reads this. The LLM will also struggle to maintain quality over that length. | Surface 3-5 key sequences or pitches (outlier P+ scores, turning points, high-leverage moments). Quality over quantity. |
| **Visualizations / charts / heatmaps** | Heatmaps and movement plots are standard in web-based tools. | This is a CLI tool producing text output. Generating images adds matplotlib/plotly dependency, terminal rendering complexity, and output format decisions. The LLM generates text, not images. | Use ASCII-style indicators or descriptive language: "located glove-side consistently," "clustered in upper-third of zone." Defer visualizations to a future web UI milestone. |
| **Real-time / live data ingestion** | "Run this during the game!" | Static parquet/CSV is the data contract. Live API calls to Savant add network dependency, rate limiting concerns, and data freshness complexity. Explicitly out of scope. | Run post-game against updated data files. The value is post-appearance analysis, not live commentary. |
| **Predictive projections** | "What will he do next start?" | Projection models require different methodology (regression, aging curves, rest effects). An LLM generating projections from a single-season sample is irresponsible and likely wrong. | Note trends that *suggest* direction: "declining velo trend warrants monitoring." Do not project future stats. |
| **Team-level aggregated reports** | "Give me a report on the whole pitching staff." | Multiplies scope by 12-15x per team. Different narrative structure needed. Explicitly out of scope. | Individual pitcher reports can be run sequentially via shell scripting. |
| **Comparison to other pitchers** | "How does his slider compare to league average sliders?" | Requires league-wide baselines, percentile rankings, peer grouping. The P+/S+/L+ scores (scaled to 100 = avg) already provide this implicitly. | Use the built-in scale: "S+ 120 slider (well above average)" communicates the comparison. Team-level aggs provide some league context. |

## Feature Dependencies

```
[Appearance-level performance summary]
    |
    |--requires--> [Starter vs. reliever detection]
    |                   |
    |                   |--shapes--> [Times through order analysis] (starters only)
    |                   |--shapes--> [Rest and workload context] (relievers only)
    |
    |--requires--> [Arsenal inventory with usage rates]
    |                   |
    |                   |--requires--> [Usage rate deltas]
    |                   |--requires--> [Platoon split awareness]
    |                   |--enhances--> [First-pitch and count-state tendencies]
    |
    |--requires--> [Fastball quality summary]
    |                   |
    |                   |--enhances--> [Within-game velocity arc narrative]
    |                   |--enhances--> [Movement shape change detection]
    |
    |--requires--> [P+/S+/L+ scores per pitch]
    |                   |
    |                   |--enhances--> [Pitch-level P+/S+/L+ outlier detection]
    |                   |--enhances--> [xRV100-driven pitch effectiveness ranking]
    |
    |--requires--> [Trend context (recent window vs. season)]
    |                   |
    |                   |--enhances--> [Qualitative scout-language flags]

[Data tables alongside prose] --independent-- (structural, applies to all sections)

[Key matchup highlights] --requires--> [Appearance-level performance summary]
                          --requires--> [P+/S+/L+ scores per pitch]
```

### Dependency Notes

- **Starter/reliever detection is foundational:** It determines the entire report structure, section ordering, and which features activate. Must be built first.
- **Arsenal inventory feeds most analysis:** Usage rates, platoon splits, count tendencies, and effectiveness rankings all depend on having the pitch-type breakdown working.
- **Trend context is the framing layer:** Every metric needs its delta and qualitative descriptor. This should be a reusable utility, not per-feature logic.
- **P+/S+/L+ integration is the data backbone:** The agg files are the primary data advantage. Loading and joining them correctly enables all the differentiating features.
- **Key matchup highlights depend on everything else:** This is a capstone feature that requires pitch-level data, batter context, P+ scores, and game context all working together.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what's needed to validate that the LLM can produce genuinely useful pitcher narratives.

- [ ] **Starter/reliever detection** -- structural foundation for everything
- [ ] **Appearance-level performance summary** -- anchors the report
- [ ] **Fastball quality summary** (velo baseline, trend, within-game) -- most important pitch analysis
- [ ] **Arsenal inventory with usage rates and deltas** -- second most important
- [ ] **P+/S+/L+ scores per pitch type** (season + appearance) -- the project's data advantage
- [ ] **Trend context framing** (recent vs. season deltas with qualitative strings) -- what makes it a *scout* report, not a stat dump
- [ ] **Data tables alongside prose** -- output format
- [ ] **Platoon split awareness** -- essential for arsenal analysis completeness

### Add After Validation (v1.x)

Features to add once the core narrative quality is validated.

- [ ] **Execution metrics (CSW%, zone rate, chase rate)** -- add when base report quality is confirmed
- [ ] **Within-game velocity arc narrative** -- add when fastball section is solid
- [ ] **Movement shape change detection** -- add when arsenal section is solid
- [ ] **xRV100-driven pitch effectiveness ranking** -- low-cost add once agg loading is working
- [ ] **Qualitative scout-language flags** -- iterative refinement of prompt vocabulary
- [ ] **Rest and workload context** -- add for reliever reports after starter flow is validated

### Future Consideration (v2+)

Features to defer until the core product is proven.

- [ ] **First-pitch and count-state tendencies** -- requires significant Statcast filtering logic; high value but high complexity
- [ ] **Times through order analysis** -- requires batting order reconstruction; valuable for starters but complex
- [ ] **Key matchup highlights** -- requires batter identification and WPA/leverage context; capstone feature
- [ ] **Pitch-level P+/S+/L+ outlier detection** -- requires querying 143K-row all_pitches file efficiently; high wow-factor

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Starter/reliever detection | HIGH | LOW | P1 |
| Appearance-level summary | HIGH | LOW | P1 |
| Fastball quality summary | HIGH | LOW | P1 |
| Arsenal inventory + usage deltas | HIGH | MEDIUM | P1 |
| P+/S+/L+ per pitch type | HIGH | LOW | P1 |
| Trend context framing | HIGH | MEDIUM | P1 |
| Platoon split awareness | HIGH | MEDIUM | P1 |
| Data tables + prose output | HIGH | LOW | P1 |
| Execution metrics (CSW/zone/chase) | HIGH | MEDIUM | P2 |
| Within-game velo arc | MEDIUM | MEDIUM | P2 |
| Movement shape changes | MEDIUM | MEDIUM | P2 |
| xRV100 pitch ranking | MEDIUM | LOW | P2 |
| Scout-language flags | MEDIUM | MEDIUM | P2 |
| Rest/workload context | MEDIUM | MEDIUM | P2 |
| Count-state tendencies | MEDIUM | HIGH | P3 |
| Times through order | MEDIUM | HIGH | P3 |
| Key matchup highlights | HIGH | HIGH | P3 |
| Pitch-level outlier detection | HIGH | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch -- the report is incomplete without these
- P2: Should have, add when possible -- elevates report from good to great
- P3: Nice to have, future consideration -- wow-factor features that require solid foundation

## Competitor Feature Analysis

| Feature | Baseball Savant (Player Page) | FanGraphs (PitchingBot) | PitchGrader | Our Approach |
|---------|-------------------------------|-------------------------|-------------|--------------|
| Pitch grades (Stuff/Command) | Percentile bars, no per-appearance | 20-80 scale, per pitch type, season-level | AI pitch grading, development focus | P+/S+/L+ at season AND appearance grain, with deltas -- more temporal granularity than any competitor |
| Arsenal breakdown | Usage %, velo, movement per pitch | Usage %, movement profiles | Arsenal optimization | Usage % with platoon splits AND count-state tendencies, framed as deltas from baseline |
| Velocity trends | Game-level averages | Season-level only | Session tracking | Within-game arc + cross-appearance trend with qualitative framing |
| Movement profiles | Scatter plots (visual) | Movement tables | 3D visualization | Narrative description with delta detection ("lost 2in of sweep") -- text-first since CLI |
| Narrative output | None (data only) | None (data only) | Brief text insights | Full scout-voice narrative with data tables -- this IS the product |
| Appearance-level analysis | Game feed (raw data) | Not available per-appearance | Session reports | First-class: the report IS about the appearance relative to trend |
| Platoon analysis | Available but separate page | Split tables | Not emphasized | Integrated into arsenal narrative: "abandoned changeup vs LHB" |
| Workload/rest context | Not shown | Not shown | Not shown | Built into reliever report structure -- genuinely novel |

## Sources

- [Simple Sabermetrics: How to Build an Elite Opposing Pitcher Advanced Scouting Report](https://simplesabermetrics.com/blogs/simple-sabermetrics-blog/how-to-build-an-elite-opposing-pitcher-advanced-scouting-report)
- [Simple Sabermetrics: The Key Aspects of A Good Scouting Report](https://simplesabermetrics.com/blogs/simple-sabermetrics-blog/the-key-aspects-of-a-good-scouting-report)
- [FanGraphs: PitchingBot Pitch Modeling Primer](https://library.fangraphs.com/pitching/pitchingbot-pitch-modeling-primer/)
- [FanGraphs: PitchingBot and Stuff+ Pitch Modeling](https://blogs.fangraphs.com/pitchingbot-and-stuff-pitch-modeling-are-now-on-fangraphs/)
- [FanGraphs: A Visual Scouting Primer: Pitching](https://blogs.fangraphs.com/a-visual-scouting-primer-pitching-part-one/)
- [FanGraphs: Are Pitchers Getting Better at Holding Their Velocity?](https://blogs.fangraphs.com/are-pitchers-getting-better-at-holding-their-velocity/)
- [FanGraphs: In Game Velocity Changes: When Fatigue Attacks](https://fantasy.fangraphs.com/in-game-velocity-changes-when-fatigue-attacks/)
- [FanGraphs: Plate Discipline Metrics](https://library.fangraphs.com/offense/plate-discipline/)
- [Baseball Savant: Statcast Player Pages](https://baseballsavant.mlb.com/)
- [Baseball Savant: Pitch Arsenal Stats](https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats)
- [MLB Glossary: Third Time Through the Order Penalty](https://www.mlb.com/glossary/miscellaneous/third-time-through-the-order-penalty)
- [Baseball Prospectus: Introducing Pitch Tunnels](https://www.baseballprospectus.com/news/article/31030/prospectus-feature-introducing-pitch-tunnels/)
- [DIAMOND: An LLM-Driven Agent for Context-Aware Baseball Highlight Summarization](https://arxiv.org/html/2506.02351v1)
- [PitchGrader](https://www.pitchgrader.com/)
- [Baseball America: Explaining the 20-80 Scouting Scale](https://www.baseballamerica.com/stories/explaining-the-20-80-baseball-scouting-scale/)
- [Bayesian Analysis of the Time Through the Order Penalty](https://arxiv.org/abs/2210.06724)

---
*Feature research for: LLM-generated pitcher scouting narrative reports*
*Researched: 2026-03-26*
