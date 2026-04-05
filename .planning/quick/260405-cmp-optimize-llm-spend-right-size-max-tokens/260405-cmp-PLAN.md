---
phase: quick
plan: 260405-cmp
type: execute
wave: 1
depends_on: []
files_modified:
  - src/pitcher_narratives/config.py
  - src/pitcher_narratives/pipeline.py
  - src/pitcher_narratives/report.py
  - src/pitcher_narratives/analyst.py
  - src/pitcher_narratives/ask_cli.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Each agent role gets a right-sized max_tokens (1024/2048/4096) instead of the 16384 default"
    - "analyst.py QA agent uses dynamic provider/thinking instead of hardcoded openai:gpt-5.4-mini"
    - "Thinking effort is capped per role (checker=low, specialist=medium, writer=uncapped)"
    - "pitcher-ask CLI defaults to medium thinking instead of high"
  artifacts:
    - path: "src/pitcher_narratives/config.py"
      provides: "TOKEN_BUDGET_* constants, cap_thinking helper"
      contains: "TOKEN_BUDGET_SMALL"
    - path: "src/pitcher_narratives/analyst.py"
      provides: "Dynamic _make_qa_agent factory replacing hardcoded singleton"
      contains: "_make_qa_agent"
  key_links:
    - from: "src/pitcher_narratives/pipeline.py"
      to: "src/pitcher_narratives/config.py"
      via: "import cap_thinking, TOKEN_BUDGET_*"
      pattern: "cap_thinking|TOKEN_BUDGET"
    - from: "src/pitcher_narratives/report.py"
      to: "src/pitcher_narratives/config.py"
      via: "import cap_thinking, TOKEN_BUDGET_*"
      pattern: "cap_thinking|TOKEN_BUDGET"
    - from: "src/pitcher_narratives/analyst.py"
      to: "src/pitcher_narratives/config.py"
      via: "import cap_thinking, TOKEN_BUDGET_*"
      pattern: "cap_thinking|TOKEN_BUDGET"
---

<objective>
Optimize LLM spend across pitcher-narratives by right-sizing max_tokens per agent role,
capping thinking effort by role, refactoring the analyst.py hardcoded agent to a dynamic
factory, and lowering the pitcher-ask CLI default thinking level.

Purpose: Cut token waste — most roles (anchor, auditor, specialists) produce short structured
output but currently get 16384 max_tokens and uncapped thinking. This change applies
role-appropriate budgets without degrading output quality.

Output: Updated config.py, pipeline.py, report.py, analyst.py, ask_cli.py
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@src/pitcher_narratives/config.py
@src/pitcher_narratives/pipeline.py
@src/pitcher_narratives/report.py
@src/pitcher_narratives/analyst.py
@src/pitcher_narratives/ask_cli.py

<interfaces>
From src/pitcher_narratives/config.py:
```python
PROVIDERS = {
    "openai": "openai:gpt-5.4",
    "claude": "anthropic:claude-sonnet-4-6",
    "gemini": "google-gla:gemini-3.1-pro-preview",
}
THINKING_LEVELS: list[ThinkingEffort] = ["minimal", "low", "medium", "high", "xhigh"]

def make_model_settings(
    provider: str, thinking: ThinkingEffort, temperature: float,
    *, max_tokens: int = 16384,
) -> ModelSettings: ...
```

From src/pitcher_narratives/analyst.py (current shape — will be refactored):
```python
_analyst_agent = Agent("openai:gpt-5.4-mini", deps_type=QADeps, ...)

@_analyst_agent.tool
def get_pitcher_summary(ctx: RunContext[QADeps]) -> str: ...

@_analyst_agent.tool
def get_pitch_detail(ctx: RunContext[QADeps], pitch_type: str) -> str: ...

_settings_cache: dict[tuple[str, ThinkingEffort], tuple[str, ModelSettings]] = {}

def _make_analyst(provider, thinking) -> tuple[str, ModelSettings]: ...
def ask_question_streaming(...) -> str: ...
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add token budget constants, cap_thinking helper, and fix OpenAI max_tokens passthrough in config.py</name>
  <files>src/pitcher_narratives/config.py</files>
  <action>
  Add three token budget constants after the THINKING_LEVELS line:

  ```python
  TOKEN_BUDGET_SMALL = 1024
  """Anchor, auditor, executive summary — short structured output."""

  TOKEN_BUDGET_MEDIUM = 2048
  """Specialist builders — moderate analytical output."""

  TOKEN_BUDGET_LARGE = 4096
  """Writer, editor, answerer, stuff explainer — long-form prose."""
  ```

  Add a `cap_thinking` helper function after `make_model_settings`:

  ```python
  def cap_thinking(thinking: ThinkingEffort, ceiling: ThinkingEffort) -> ThinkingEffort:
      """Clamp thinking effort to the lower of the given level and the ceiling.

      Uses THINKING_LEVELS index ordering: minimal < low < medium < high < xhigh.
      """
      return thinking if THINKING_LEVELS.index(thinking) <= THINKING_LEVELS.index(ceiling) else ceiling
  ```

  Fix the OpenAI branch in `make_model_settings` (line 69) to also pass `max_tokens`:
  ```python
  return ModelSettings(temperature=temperature, max_tokens=max_tokens)
  ```
  Without this fix, token budgets silently have no effect for the OpenAI provider.

  Update `__all__` to export `TOKEN_BUDGET_SMALL`, `TOKEN_BUDGET_MEDIUM`, `TOKEN_BUDGET_LARGE`, and `cap_thinking`.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "from pitcher_narratives.config import TOKEN_BUDGET_SMALL, TOKEN_BUDGET_MEDIUM, TOKEN_BUDGET_LARGE, cap_thinking, THINKING_LEVELS; assert TOKEN_BUDGET_SMALL == 1024; assert TOKEN_BUDGET_MEDIUM == 2048; assert TOKEN_BUDGET_LARGE == 4096; assert cap_thinking('high', 'low') == 'low'; assert cap_thinking('low', 'high') == 'low'; assert cap_thinking('medium', 'medium') == 'medium'; print('config OK')"</automated>
  </verify>
  <done>
  - TOKEN_BUDGET_SMALL=1024, TOKEN_BUDGET_MEDIUM=2048, TOKEN_BUDGET_LARGE=4096 exported
  - cap_thinking clamps to lower of two levels
  - OpenAI branch in make_model_settings passes max_tokens
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire token budgets and thinking caps into pipeline.py and report.py factories</name>
  <files>src/pitcher_narratives/pipeline.py, src/pitcher_narratives/report.py, src/pitcher_narratives/ask_cli.py</files>
  <action>
  **pipeline.py — `make_pipeline_agents()` (line ~986):**

  Add imports: `cap_thinking`, `TOKEN_BUDGET_SMALL`, `TOKEN_BUDGET_MEDIUM`, `TOKEN_BUDGET_LARGE` from `pitcher_narratives.config`.

  Replace the three settings lines with thinking-capped, token-budgeted versions:
  ```python
  specialist_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM)
  writer_settings = make_model_settings(provider, thinking, 0.7, max_tokens=TOKEN_BUDGET_LARGE)
  checker_settings = make_model_settings(provider, cap_thinking(thinking, "low"), 0.1, max_tokens=TOKEN_BUDGET_SMALL)
  ```

  The `summary` agent uses `_specialist` but should get SMALL budget. Change the summary agent line to use its own settings:
  ```python
  summary_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_SMALL)
  ```
  And construct the summary agent directly instead of via `_specialist`:
  ```python
  summary=Agent(model, output_type=str, system_prompt=_EXECUTIVE_SUMMARY_PROMPT,
                model_settings=summary_settings, defer_model_check=True),
  ```

  **report.py — `_make_agents()` (line ~431):**

  Add imports: `cap_thinking`, `TOKEN_BUDGET_SMALL`, `TOKEN_BUDGET_MEDIUM`, `TOKEN_BUDGET_LARGE` from `pitcher_narratives.config`.

  Replace the three settings lines:
  ```python
  analyst_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_MEDIUM)
  writer_settings = make_model_settings(provider, thinking, 0.7, max_tokens=TOKEN_BUDGET_LARGE)
  checker_settings = make_model_settings(provider, cap_thinking(thinking, "low"), 0.1, max_tokens=TOKEN_BUDGET_SMALL)
  ```

  The stuff explainer (index 2 in str_prompts_and_settings) should use TOKEN_BUDGET_LARGE and the executive summary (index 3) should use TOKEN_BUDGET_SMALL. Refactor str_prompts_and_settings to use per-role settings:
  ```python
  summary_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_SMALL)
  stuff_settings = make_model_settings(provider, cap_thinking(thinking, "medium"), 0.3, max_tokens=TOKEN_BUDGET_LARGE)

  str_prompts_and_settings = [
      (_SYNTHESIZER_PROMPT, analyst_settings),
      (_EDITOR_PROMPT, writer_settings),
      (_STUFF_EXPLAINER_PROMPT, stuff_settings),
      (_EXECUTIVE_SUMMARY_PROMPT, summary_settings),
  ]
  ```

  **ask_cli.py — line 54:**

  Change `default="high"` to `default="medium"` on the `--thinking` argument.
  Update the help string to `"Thinking/reasoning effort level (default: medium)"`.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "
from pitcher_narratives.pipeline import make_pipeline_agents
from pitcher_narratives.report import _make_agents
# Just verify factories still construct without error
pa = make_pipeline_agents('openai', 'high')
ra = _make_agents('openai', 'high')
print('pipeline agents:', type(pa).__name__)
print('report agents: str_agents=%d, anchor=%s' % (len(ra[0]), type(ra[1]).__name__))
print('factories OK')
"</automated>
  </verify>
  <done>
  - pipeline.py: checker capped at low/1024, specialist capped at medium/2048, summary capped at medium/1024, writer uncapped/4096
  - report.py: checker capped at low/1024, synthesizer capped at medium/2048, stuff explainer capped at medium/4096, summary capped at medium/1024, editor uncapped/4096
  - ask_cli.py: --thinking default changed from high to medium
  </done>
</task>

<task type="auto">
  <name>Task 3: Refactor analyst.py — replace hardcoded agent singleton with dynamic factory</name>
  <files>src/pitcher_narratives/analyst.py</files>
  <action>
  This task replaces the module-level `_analyst_agent = Agent("openai:gpt-5.4-mini", ...)` singleton
  with a cached factory that respects the caller's provider and thinking choices.

  **Step 1 — Convert tool functions to standalone functions:**

  Remove the `@_analyst_agent.tool` decorators from `get_pitcher_summary` and `get_pitch_detail`.
  Add `from pydantic_ai import Tool` to imports.

  Change function signatures to standalone (they already accept RunContext[QADeps] which works
  with pydantic-ai's tool system when passed as `tools=[...]`):
  ```python
  def get_pitcher_summary(ctx: RunContext[QADeps]) -> str:
      ...  # body unchanged

  def get_pitch_detail(ctx: RunContext[QADeps], pitch_type: str) -> str:
      ...  # body unchanged
  ```

  **Step 2 — Delete the module-level singleton:**

  Delete the `_analyst_agent = Agent("openai:gpt-5.4-mini", ...)` block (lines 225-231).

  **Step 3 — Create _make_qa_agent factory:**

  Replace the existing `_settings_cache` and `_make_analyst` function with:
  ```python
  _qa_agent_cache: dict[tuple[str, ThinkingEffort], Agent[QADeps, str]] = {}

  def _make_qa_agent(
      provider: str = "gemini",
      thinking: ThinkingEffort = "high",
  ) -> Agent[QADeps, str]:
      """Create (or return cached) QA agent for the given provider and thinking level."""
      key = (provider, thinking)
      if key in _qa_agent_cache:
          return _qa_agent_cache[key]

      if provider not in PROVIDERS:
          raise ValueError(f"Unknown provider {provider!r}, expected one of: {', '.join(PROVIDERS)}")

      model = PROVIDERS[provider]
      settings = make_model_settings(provider, thinking, 0.3, max_tokens=TOKEN_BUDGET_LARGE)

      agent = Agent(
          model,
          deps_type=QADeps,
          output_type=str,
          instructions=ANALYST_INSTRUCTIONS,
          model_settings=settings,
          tools=[get_pitcher_summary, get_pitch_detail],
          defer_model_check=True,
      )
      _qa_agent_cache[key] = agent
      return agent
  ```

  Add `TOKEN_BUDGET_LARGE` to the imports from `pitcher_narratives.config`.

  **Step 4 — Update ask_question_streaming:**

  Replace lines 489-499 in `ask_question_streaming`:
  ```python
  agent = _make_qa_agent(provider, thinking)
  deps = QADeps(context=context, data=data)

  kwargs: dict[str, Any] = {"user_prompt": question, "deps": deps}
  if _model_override is not None:
      kwargs["model"] = _model_override

  stream = agent.run_stream_sync(**kwargs)
  ```

  The function no longer passes `model_settings` per-call (it is baked into the agent).
  The function no longer passes `model` per-call (it is baked into the agent) unless _model_override is set.

  **Step 5 — Clean up:**

  Remove unused `ModelSettings` from imports if no longer referenced.
  Delete the old `_settings_cache` dict and `_make_analyst` function entirely.
  </action>
  <verify>
    <automated>cd /Users/matt/src/pitcher-narratives && uv run python -c "
from pitcher_narratives.analyst import _make_qa_agent, get_pitcher_summary, get_pitch_detail
# Verify factory creates agents for each provider
for p in ('openai', 'claude', 'gemini'):
    a = _make_qa_agent(p, 'medium')
    assert len(a._function_tools) == 2, f'{p}: expected 2 tools, got {len(a._function_tools)}'
    print(f'{p}: agent OK with {len(a._function_tools)} tools')
# Verify caching
a1 = _make_qa_agent('openai', 'medium')
a2 = _make_qa_agent('openai', 'medium')
assert a1 is a2, 'cache miss'
print('caching OK')
print('analyst refactor OK')
"</automated>
  </verify>
  <done>
  - Module-level _analyst_agent singleton deleted
  - get_pitcher_summary and get_pitch_detail are standalone functions (no @tool decorator)
  - _make_qa_agent factory creates cached Agent with dynamic provider, thinking, and TOKEN_BUDGET_LARGE
  - ask_question_streaming uses _make_qa_agent instead of _analyst_agent
  - _make_analyst and _settings_cache deleted
  </done>
</task>

</tasks>

<verification>
All three tasks verified individually. Final integration check:

```bash
cd /Users/matt/src/pitcher-narratives && uv run python -c "
from pitcher_narratives.config import TOKEN_BUDGET_SMALL, TOKEN_BUDGET_MEDIUM, TOKEN_BUDGET_LARGE, cap_thinking
from pitcher_narratives.pipeline import make_pipeline_agents
from pitcher_narratives.report import _make_agents
from pitcher_narratives.analyst import _make_qa_agent
print('All imports OK')
print(f'Budgets: {TOKEN_BUDGET_SMALL}/{TOKEN_BUDGET_MEDIUM}/{TOKEN_BUDGET_LARGE}')
print(f'cap_thinking(high, low) = {cap_thinking(\"high\", \"low\")}')
pa = make_pipeline_agents('openai', 'high')
ra = _make_agents('openai', 'high')
qa = _make_qa_agent('openai', 'medium')
print('All factories construct OK')
"
```
</verification>

<success_criteria>
- Token budgets: 1024 for anchor/auditor/summary, 2048 for specialists, 4096 for writer/editor/answerer/stuff-explainer
- Thinking caps: checker=low, specialist=medium, writer/answerer=uncapped
- analyst.py: no hardcoded model string, factory respects provider param
- ask_cli.py: --thinking defaults to medium
- All agent factories construct without error for all three providers
</success_criteria>

<output>
After completion, create `.planning/quick/260405-cmp-optimize-llm-spend-right-size-max-tokens/260405-cmp-SUMMARY.md`
</output>
