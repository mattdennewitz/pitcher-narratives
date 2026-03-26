# Building a Two-Phase LLM Pipeline That Writes Like an Elite Baseball Analyst

I've been working on a system that takes raw Statcast pitch-tracking data and Pitching+ model outputs and turns them into scouting capsules: the kind of tight, opinionated, two-paragraph analytical summaries you see from top sabermetric writers. The kind that diagnose *why* a pitcher's slider stopped working, not just that his ERA went up.

The core problem: LLMs are terrible at math but excellent at interpretation. If you give Claude a JSON payload of 145,000 pitch-level rows and ask it to "write a scouting report," you get hallucinated metrics, invented trends, and prose that sounds confident about numbers it computed incorrectly. The solution is a pipeline that does all the math in Python, then hands the LLM a pre-digested briefing and says: interpret this.

Here is what I built and what I learned along the way.

## The Data: Statcast + Pitching+

The system ingests two data sources for each pitcher:

1. **Statcast pitch-level data** (from Baseball Savant): velocity, movement, location zones, pitch outcomes, batter handedness, times-through-order tracking. About 145,000 rows across 114 columns for the 2026 season.

2. **Pitching+ aggregations**: pre-computed P+ (Pitching+), S+ (Stuff+), and L+ (Location+) scores at eight different grains, from individual pitch scores all the way up to season-level team averages. These are scaled to 100 = MLB average, so a P+ of 112 means 12% better than league-average stuff quality.

The aggregations come pre-computed at multiple levels of detail:

```
Season per pitcher          → Baselines
Season per pitcher/type     → Per-pitch baselines
Per game per pitcher        → Game-level trends
Per game per pitcher/type   → Per-pitch game trends
Season per pitcher/platoon  → Platoon baselines
Per game per pitcher/platoon→ Platoon game trends
Individual pitch            → Pitch-level P+/S+/L+
Team season                 → League context
```

Everything joins on `pitcher` (the integer MLB player ID). The parquet file uses polars Date types; the CSVs store dates as strings, so one of the first things the loader does is parse them with `str.to_date("%Y-%m-%d")` to avoid silent join failures.

## The Computation Engine: Never Let the LLM Do Math

This is the architectural decision that everything else depends on. The Python pipeline pre-computes every delta, every trend string, every comparison the LLM might need. The model receives something like:

```
Fastball velo: Down 1.2 mph vs season
Slider P+: Up sharply (+15 points) vs season
Changeup usage: +21pp by pass 3
```

It never sees "93.6 mph season, 92.4 mph recent" and tries to subtract. The delta strings use a fixed vocabulary with magnitude thresholds:

| Type | "Steady" | "Up/Down" | "Sharply" |
|------|----------|-----------|-----------|
| Velocity | < 0.5 mph | 0.5-2.0 mph | > 2.0 mph |
| P+/S+/L+ | < 5 points | 5-10 points | > 10 points |
| Usage | < 5pp | 5-10pp | > 10pp |

I found that this vocabulary layer is surprisingly important. Without it, you get the LLM saying things like "velocity decreased by a small amount" (vague) or "velocity dropped 0.3 mph" (precise but not meaningful in Statcast data where 0.3 mph is sensor noise). The thresholds encode domain knowledge about what constitutes a real signal.

### Times Through Order: The Analysis That Made It Click

The most interesting computation is the TTO (times-through-order) analysis. This joins Statcast's `n_thruorder_pitcher` column with the pitch-level P+ scores from `all_pitches.csv` to show how a starter's stuff quality changes across passes through the lineup.

The naive version just averaged P+ by TTO pass. It produced summaries like "P+ holds steady through 3 passes." The problem: it was masking the real story. When I split TTO into **fastball P+ vs. secondary P+**, the picture changed completely:

```
Pass 1: FB P+ 112, Sec P+ 109
Pass 2: FB P+ 96,  Sec P+ 103
Pass 3: FB P+ 98,  Sec P+ 100
```

The fastball is collapsing by 14 points while the secondaries hold. That is a completely different scouting conclusion: this pitcher's fastball deteriorates, but he compensates by leaning into his offspeed.

I then added a per-pitch-type breakdown with usage percentages across passes, which surfaced mix shifts:

```
CH: 20% → 30% → 41% by pass 3
SI: 35% → 35% → 9% by pass 3
```

He is abandoning his sinker and leaning on his changeup. The final layer: platoon splits within TTO. Against lefties in pass 3, he drops the fastball and sinker entirely and goes changeup/slider only. That is the kind of finding that makes a scouting report worth reading.

### Starter vs. Reliever: Per-Appearance, Not Per-Pitcher

One early mistake: classifying pitchers as SP or RP at the pitcher level. It turns out about 25% of MLB pitchers have made both starts and relief appearances. The fix was simple: classify each appearance independently by checking if the pitcher's first inning in that game was inning 1. Openers get classified as SP (they started the game), swingmen get the correct label per outing, and the report adapts its structure accordingly.

## The Two-Phase LLM Architecture

This is where it gets interesting. Instead of one LLM call, the pipeline uses two sequential calls with completely different personalities.

### Phase 1: The Data Synthesizer

The first agent is instructed to be "an elite MLB data analyst preparing a factual briefing document for a senior sabermetric writer." It is explicitly told: you are not writing a story. No subjective adjectives. No projections. Just extract the signal.

The key design choice: a **rigid output template**. The synthesizer must produce this exact structure:

```
## Fastball Quality & Velocity Trends
[bulleted facts]

## Pitch Mix & Usage Shifts
[bulleted facts]

## Execution & Outcomes
[bulleted facts]

## Platoon Splits
[bulleted facts]

## Workload & Stamina
[bulleted facts]

## Key Signal
[the single most important improvement AND concern]
```

I arrived at this after comparing two approaches. The first version said "separate findings into clear categories" and let the LLM pick its own structure. The output was inconsistent: different headers per pitcher, different ordering, sometimes burying the most important finding in the middle of a paragraph. The rigid template solved this. Phase 2 always receives the same shape of briefing.

The **Key Signal** section at the bottom is the other breakthrough. It forces the synthesizer to commit: what is THE most important positive trend and THE most important red flag? This gives Phase 2 an explicit anchor for its editorial.

The synthesizer also gets role-conditional guidance. Starters get prompts about TTO breakdown and stamina trajectory. Relievers get prompts about rest day impact and put-away pitch identification.

### Phase 2: The Editor

The second agent is "an elite, sabermetrically inclined baseball writer" who writes "for front offices, advanced fantasy players, and data-driven fans." The tone directive: "objective, mildly skeptical, and highly analytical. You are not a cheerleader."

The editorial rules took several iterations to get right. The ones that made the biggest difference:

**"Start immediately with the analysis."** Without this, the LLM opens with "Looking at the recent data for Logan Webb..." every single time. That is exactly the throat-clearing the rule kills.

**"Anchor every metric."** This was the single most impactful content heuristic. The instruction says: never state a velocity, P+ score, or usage rate without contextualizing it against the MLB average or the pitcher's baseline. Before this rule, the LLM would write "his slider P+ came in at 108." After: "his slider is grading out at a 108 P+, eight points above the league-average secondary."

**"Diagnose, do not just describe."** This shifts the output from "his velocity dropped 1.5 mph" to "his velocity dropped 1.5 mph, and with it, two inches of induced vertical break on the four-seam, which explains why the chase rate on elevated fastballs collapsed from 35% to 22%."

**"Take a stance."** The instruction is to end with "a decisive, unsentimental projection." Examples in the prompt: "profiles as a low-leverage reliever," "looks like a #4 starter until command improves," "a high-variance, blow-up candidate." Without this, you get hedged non-conclusions.

The output format is enforced as a 2-3 paragraph capsule. Paragraph 1 is the Setup (what changed physically), Paragraph 2+ is the Verdict (how it plays in the zone, plus the projection). A third paragraph is allowed when the setup genuinely needs separation, like when fastball changes and arsenal evolution each warrant their own paragraph.

One voice constraint I found necessary to add explicitly: **no negative comparison constructions**. The LLM loves writing "it's grading out as a legitimate weapon, not just a contact-manager." The rule says: state what something IS, do not define it by what it is not.

### Why Two Phases?

The separation gives you two things:

1. **Phase 2 never does math.** It receives pre-extracted findings and focuses entirely on interpretation and voice. This is the primary defense against hallucinated metrics. An LLM that is computing "32% minus 20% equals 12 percentage points" while simultaneously trying to write in a skeptical analytical voice will get one of those things wrong.

2. **Phase 1 does not have to be interesting.** It can produce boring, repetitive, bullet-pointed analysis because it is not the output the user sees. The creative overhead is zero, which means it can focus entirely on accurate extraction.

## The Hallucination Guard

After Phase 2 produces the final capsule, a regex-based scanner checks the output for metric-like patterns (anything matching `xMetric`, `Acronym%`, or `P+/S+/L+` family) and flags terms not in a known-safe set. This catches fabricated metrics like "xDominance" or "xVAA" that the LLM invents to make a sentence flow better.

```python
_METRIC_PATTERN = re.compile(
    r'\b('
    r'x[A-Z][A-Za-z0-9]*'        # xBA, xWhiff, xRV100
    r'|[A-Z][A-Za-z]*-?[A-Z]*%'  # CSW%, O-Swing%, K-BB%
    r'|[PSL]\+(?:2080)?'          # P+, S+2080
    r'|(?:IVB|HB|wOBA|BABIP|...)'
    r')\b'
)
```

It is a simple check, but it catches the most common failure mode: the LLM creating a plausible-sounding advanced metric to support a claim it wants to make.

## The Pipeline

The full flow:

```
python main.py -p 686799 -w 14

→ Load Statcast parquet + 8 Pitching+ CSVs (polars)
→ Filter to pitcher, classify SP/RP per appearance
→ Compute: fastball quality, arsenal, platoon, execution,
  workload, TTO (7 modules, all in Python)
→ Assemble PitcherContext (Pydantic model, ~1,000 tokens)
→ Phase 1: Synthesizer extracts structured findings (silent)
→ Phase 2: Editor writes 2-3 paragraph capsule (streamed)
→ Hallucination guard scans for unknown metrics
→ Output to terminal
```

Every number in the final output traces back through this pipeline to a specific Statcast column or Pitching+ aggregation. The LLM interprets and articulates. It does not compute.

## What I Would Do Differently

The delta string vocabulary (Steady/Up/Down/Sharply) works well for the current use case, but it discards magnitude information that a more sophisticated system might want. A future version could pass both the qualitative string and the raw numeric delta, letting the LLM decide how precisely to reference the number.

The hallucination guard is regex-based and only catches metric-name fabrication. It does not catch the LLM attributing a real metric to the wrong pitch type or inventing a trend direction. A more robust approach would compare every factual claim in the output against the Phase 1 synthesis, but that requires a third LLM call and the economics get tricky.

I also think the rigid synthesizer template could be extended with a **"What I Cannot Determine"** section, forcing the model to explicitly state what the data does not support rather than silently omitting gaps.

## The Stack

- Python 3.14, polars 1.39 for all data work
- pydantic-ai 1.72 for the two-agent pipeline
- Claude Sonnet 4.6 for both phases
- Pydantic for the context schema
- 126 tests, zero API key dependency (pydantic-ai's TestModel)

The whole thing is about 2,800 lines of Python (not counting tests). Most of that is the computation engine. The LLM integration is about 300 lines.

---

*Tags: Python, LLMs, pydantic-ai, Claude, baseball, Statcast, Pitching+, prompt-engineering, two-phase-pipeline*
