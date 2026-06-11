# LLM Benchmarking Harness (bench) — Design

Date: 2026-06-11. Status: approved (scope: end-to-end; scoring: absolute
rubric; judge: panel with self-judging excluded, configurable).

## Purpose

Compare multiple LLM providers for text-writing quality across BOTH
tiers of the system — the five individual pipeline specialists and the
final scouting capsule — automatically: one command runs the full
pipeline per provider, captures every output, judges each against a
comprehensive rubric, and emits a scorecard.

## Invocation

```
python -m pitcher_narratives.bench -p <pitcher_id> [--providers gemini,claude]
    [--judges panel|<provider>] [--thinking medium] [--persona scout]
    [--out bench-runs/]
```

## Architecture (5 isolated units, `src/pitcher_narratives/bench/`)

1. **runner.py** — runs `generate_pipeline_streaming` once per
   provider; captures `PipelineResult.specialists.*` (stuff, location,
   runvalue, trends, game_shape), `executive_summary`, and `narrative`,
   plus wall-clock seconds per provider. Also captures the pitcher
   context document (`ctx.to_prompt()`) ONCE — it is the judge's ground
   truth. No pipeline changes needed: `PipelineResult` already exposes
   all per-agent text.
2. **rubric.py** — pydantic models (`DimensionScore` 1–5 with
   justification + verbatim evidence quote; `JudgedOutput`) and the two
   rubric definitions (below) with per-dimension weights and 1/3/5
   anchor descriptors. Builds the judge prompt from a rubric.
3. **judge.py** — a pydantic-ai agent with structured output
   (`JudgedOutput`). Input = ground-truth context + the output under
   evaluation + the rubric. Panel logic: by default each output is
   judged by every configured provider EXCEPT its author (cancels
   self-preference bias); with 2 providers this degenerates to
   cross-judging, which is stated honestly in the report. `--judges
   <provider>` forces a single judge. Judge settings: low temperature,
   no extended thinking, max_tokens 4096.
4. **scorecard.py** — pure aggregation (mean score per provider × tier ×
   dimension across judges; weighted overall per tier) and markdown
   report rendering.
5. **__main__.py** — CLI; writes `bench-runs/<timestamp>/` containing
   raw outputs per provider (re-judgeable), `scores.json`, `report.md`.

## Rubrics (absolute 1–5, anchored, weighted)

Shared core (both tiers): **grounding/faithfulness** (w3 — every claim
traceable to the context; invented metrics = automatic 1),
**directional consistency** (w2 — S+/xRV100 sign logic, P-vs-S math),
**sample-size calibration** (w1.5).

Specialist tier adds: **analytical mechanism** (w2 — traces physical →
prediction → grade), **citation discipline** (w1.5), **no hallucinated
causation** (w2), **focus** (w1).

Capsule tier adds: **thread coherence** (w2 — one story, one voice),
**insight/synthesis** (w2), **scout voice** (w1.5), **model
explanation** (w1), **readability** (w1).

Each dimension is scored with a justification and a verbatim quote from
the judged text as evidence; the judge must quote the ground truth when
alleging a grounding violation.

## Prerequisite fix (app side)

`make_model_settings("claude", ...)` enables extended thinking with
`max_tokens=4096`; Anthropic thinking budget counts against max_tokens,
so generation can die before emitting text ("token limit exceeded
before any response"). Fix: add thinking headroom to max_tokens when
thinking is enabled for Claude. Without this, Claude cannot complete a
pipeline run and cannot be benchmarked.

## Instrumentation

Wall-clock per provider run now (reported in the scorecard). Per-agent
token usage/cost is a noted follow-up — it requires threading
`result.usage()` collection through `pipeline.py` (a split the user has
pre-approved) and is out of scope for v1.

## Error handling

A provider run that raises is recorded as failed in the scorecard (with
the error) and excluded from judging; the bench continues with the
rest. A judge call that fails structured-output validation retries via
pydantic-ai's `retries`; a judge that fails entirely is dropped from
the panel average for that output (noted in the report).

## Testing

TDD. Rubric model validation (score bounds, weights); judge prompt
content (literal-string, house convention); panel-exclusion logic (pure
function); scorecard aggregation math (synthetic inputs); runner via
`_model_override=TestModel(call_tools=[])` (per pipeline-agent-testing
skill); CLI parse tests. Final verification = one real bench run on
pitcher 693433 with both providers.
