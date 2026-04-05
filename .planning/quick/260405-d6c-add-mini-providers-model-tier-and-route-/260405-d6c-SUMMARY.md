---
phase: quick
plan: 260405-d6c
subsystem: config, pipeline, report
tags: [cost-optimization, model-routing, dual-tier]
dependency_graph:
  requires: []
  provides: [MINI_PROVIDERS constant, dual-model routing in pipeline.py and report.py]
  affects: [pipeline.py agent creation, report.py agent creation]
tech_stack:
  added: []
  patterns: [dual-tier model routing - Pro for prose/physics, mini for extraction/auditing]
key_files:
  created: []
  modified:
    - src/pitcher_narratives/config.py
    - src/pitcher_narratives/pipeline.py
    - src/pitcher_narratives/report.py
decisions:
  - "OpenAI mini tier maps to gpt-5.4-mini (same as Pro since provider only has one tier)"
  - "Stuff specialist stays on Pro -- physics reasoning requires stronger model"
  - "Writer and editor stay on Pro -- prose quality requires stronger model"
metrics:
  duration: ~3 minutes
  completed: "2026-04-05T13:36:17Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Quick Task 260405-d6c: Add MINI_PROVIDERS Model Tier and Route Summary

MINI_PROVIDERS constant with mini-tier models (gpt-5.4-mini, claude-haiku-4-5, gemini-3.1-flash) routed to lightweight agents while Pro-tier reserved for prose-heavy writer/editor and physics-heavy stuff specialist/explainer.

## Completed Tasks

| # | Task | Commit | Key Changes |
|---|------|--------|-------------|
| 1 | Add MINI_PROVIDERS to config.py | c943bd4 | New MINI_PROVIDERS dict, added to __all__ |
| 2 | Route mini models in pipeline.py and report.py | c43da35 | Dual-model routing in make_pipeline_agents and _make_agents |

## Model Routing Summary

### pipeline.py (make_pipeline_agents)

| Agent | Model Tier | Rationale |
|-------|-----------|-----------|
| stuff | Pro | Physics reasoning requires stronger model |
| location | Mini | Structured data extraction |
| runvalue | Mini | Structured data extraction |
| trends | Mini | Structured data extraction |
| game_shape | Mini | Structured data extraction |
| writer | Pro | Prose quality requires stronger model |
| auditor | Mini | Fact-checking / structured output |
| anchor | Mini | Fact-checking / structured output |
| summary | Mini | Structured bullet extraction |

### report.py (_make_agents)

| Agent | Model Tier | Rationale |
|-------|-----------|-----------|
| synthesizer | Mini | Structured data extraction |
| editor | Pro | Prose quality requires stronger model |
| stuff_explainer | Pro | Physics reasoning requires stronger model |
| executive_summary | Mini | Structured bullet extraction |
| anchor | Mini | Fact-checking / structured output |

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None.

## Verification Results

```
PROVIDERS: {'openai': 'openai:gpt-5.4-mini', 'claude': 'anthropic:claude-sonnet-4-6', 'gemini': 'google-gla:gemini-3.1-pro-preview'}
MINI_PROVIDERS: {'openai': 'openai:gpt-5.4-mini', 'claude': 'anthropic:claude-haiku-4-5', 'gemini': 'google-gla:gemini-3.1-flash'}
Pipeline agents created OK
  stuff model: google-gla:gemini-3.1-pro-preview
  location model: google-gla:gemini-3.1-flash
  writer model: google-gla:gemini-3.1-pro-preview
  auditor model: google-gla:gemini-3.1-flash
  summary model: google-gla:gemini-3.1-flash
Report agents created OK
  synthesizer model: google-gla:gemini-3.1-flash
  editor model: google-gla:gemini-3.1-pro-preview
  stuff explainer model: google-gla:gemini-3.1-pro-preview
  exec summary model: google-gla:gemini-3.1-flash
  anchor model: google-gla:gemini-3.1-flash
```

## Self-Check: PASSED

All 3 modified files exist. Both commit hashes (c943bd4, c43da35) verified in git log.
