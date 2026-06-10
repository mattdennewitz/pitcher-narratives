---
name: pipeline-agent-testing
description: Use when writing or changing tests for the pydantic-ai agents in this repo (pipeline specialists, writer, Q&A, CLIs), adding tools/toolsets to an agent, switching providers, or when a green test suite still ships a runtime break.
audience: builder
---

# Testing the pydantic-ai Agents

The agents are tested with pydantic-ai `TestModel`/`FunctionModel`, which run no real API. That speed has sharp edges that have already shipped real bugs. Internalize these before touching agent tests or wiring.

## TestModel force-calls every tool

`TestModel()` invokes **every** function tool on the agent with placeholder args. So the moment an agent gains a toolset (e.g. the skills `SkillsToolset`), any TestModel-driven run calls those tools with junk and crashes (`load_skill('a')` -> `SkillNotFoundError`).

- **Fix:** use `TestModel(call_tools=[])` anywhere a tool-bearing agent is driven deterministically. Structured-output agents still produce their output with `call_tools=[]` (output tools are separate from function tools).
- The production test hook lives in `cli.py`/`ask_cli.py` behind `PITCHER_NARRATIVES_TEST_MODEL` — it already uses `call_tools=[]`. Keep it that way; the CLI integration tests depend on it.

## TestModel cannot see provider constraints — the blind spot that bites

`TestModel` does not model provider-specific limits. The real break it missed: attaching function tools to specialists made `gpt-5.4` 400 on `tools + reasoning_effort`, and **every test stayed green** — it was caught only by running the real app. (OpenAI was subsequently removed; providers are now gemini + claude.)

- A green suite does NOT prove the real providers accept the agent config. When you add tools, change `make_model_settings`, or touch reasoning, **run the real app once** (`python -m pitcher_narratives.cli -p 693433 --provider gemini`) before trusting it.
- Better: assert the invariant directly. If specialists must stay tool-free for a provider, test "specialist has no function toolset," not just "TestModel runs."

## Don't over-couple to framework internals

Wiring tests reach into `agent._user_toolsets` (a private accessor) to assert the tool/no-tool split. It works but rots on a pydantic-ai upgrade — and `pydantic-ai-skills==0.8.0` is pinned to `pydantic-ai 1.72.0`, so that upgrade is deferred, not gone. Prefer behavioral assertions (run with `FunctionModel` and check a tool fired) where practical; if you must use the private accessor, keep it in one helper so the upgrade touches one place.

## Conventions that already exist

- Real-pitcher fixture: `TEST_PITCHER = 592155`. Dead-zone demo pitcher: `693433` (Bryan Woo).
- `_test_env()` in `test_cli.py` empties **all** provider API keys so subprocess runs never hit a real API and `load_dotenv()` can't refill them — add new keys there if a provider is added.
- Prompt rules are pinned with literal-string assertions (e.g. `TestStuffPromptArmSlotRule`). When you change a specialist prompt, update or add the literal assertion in the same commit.
- `test_clean_audit_returns_originals` and `test_analyst.py` collection are known pre-existing failures — don't attribute them to your change.
