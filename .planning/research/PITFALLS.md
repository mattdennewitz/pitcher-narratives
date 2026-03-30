# Pitfalls Research

**Domain:** Interactive Q&A over structured baseball data -- adding natural language questioning to an existing analytics CLI pipeline
**Researched:** 2026-03-30
**Confidence:** MEDIUM-HIGH (grounded in direct codebase analysis of 9 source modules and 200 tests, actual dataset analysis of 1,651 pitcher names showing real collision patterns, web-verified LLM tool-calling failure modes from Arize AI production field analysis and academic research, and pydantic-ai documentation)

## Critical Pitfalls

### Pitfall 1: Fuzzy Name Resolution Returning the Wrong Pitcher

**What goes wrong:**
A user types `ask "What's Rodriguez throwing?"` and the system picks the first Rodriguez match -- say, Bradgley Rodriguez -- when the user meant Grayson Rodriguez, the Orioles ace. The system confidently generates an analytical response about the wrong pitcher. The user has no reason to doubt the answer because the system never indicated ambiguity. This is worse than an error message: it is a silent wrong answer.

The actual dataset contains **168 duplicate last-name families** across 1,651 pitchers. Rodriguez alone has **12 entries**. Garcia has 11. Anderson and Smith each have 9. Martinez has 8. These are not edge cases -- they are the most commonly searched names.

Additionally, the dataset stores names with accented characters inconsistently: "Ramirez, Kelvin" (no accent) coexists with "Ramirez, Erasmo" (accent on i). "Perez, Adonys" coexists with "Perez, Cionel" (accent on e). A user typing "Perez" must match both "Perez" and "Perez" variants, but naive string comparison treats them as different names.

**Why it happens:**
Developers reach for `rapidfuzz.process.extractOne()` with a threshold and call it done. This works for datasets with unique names but silently picks the highest-scoring match from a set of near-equal candidates. When "Rodriguez" matches 12 entries with the same last-name score, the "winner" is arbitrary -- determined by which first name happens to score slightly higher against the empty first-name input.

The accent problem compounds this: fuzzy matchers like Levenshtein or Jaro-Winkler treat "e" and "e" as different characters. Without Unicode normalization (NFKD decomposition + accent stripping), "Perez" matches "Perez, Adonys" at 100% but "Perez, Cionel" at ~85%. The user gets a false confidence match against the less well-known pitcher.

**How to avoid:**
- **Require disambiguation when multiple candidates score above threshold.** If `extractOne()` returns a score of 85+ AND `extract()` returns 2+ candidates within 5 points of each other, present the list: "Multiple matches for 'Rodriguez': Grayson Rodriguez (BAL), Bradgley Rodriguez (NYY)... Which one?" This is not a failure -- it is correct behavior.
- **Normalize Unicode before matching.** Apply `unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()` to both the query and the dataset names before scoring. This collapses "Perez" and "Perez" into the same candidate pool.
- **Index by both "First Last" and "Last, First" forms.** Users will type "Grayson Rodriguez", but the data stores "Rodriguez, Grayson". Build the matcher against both forms. Also index common short forms (first initial + last name).
- **Include team code or pitcher ID as disambiguation.** When multiple matches exist, show team affiliation from the data: "Rodriguez, Grayson (BAL)" vs "Rodriguez, Bradgley (NYY)". The user can then specify.
- **Never auto-select from ambiguous results in a CLI tool.** The cost of a wrong answer is higher than the cost of asking for clarification. The existing report pipeline fails fast with "Pitcher not found" on bad IDs -- the Q&A pipeline should be equally strict about ambiguous names.

**Warning signs:**
- Tests only cover unique-name lookups (e.g., "Ohtani" which has no collisions) and never test common surnames.
- No test for accented-character queries.
- The name resolver has no "multiple match" code path -- only "found" and "not found."
- Users report getting answers about pitchers they did not ask about.

**Phase to address:**
Phase 1 (Name Resolution) -- this must be built with disambiguation from the start. Retrofitting disambiguation into a resolver that returns a single ID requires changing the entire downstream call chain.

---

### Pitfall 2: Context Window Bloat -- Sending Full PitcherContext for Narrow Questions

**What goes wrong:**
The user asks "What is Corbin Burnes' fastball velocity?" -- a question answerable from 2 lines of the PitcherContext. But the system sends the entire `to_prompt()` output (~2,000 tokens of markdown covering 12 sections: executive summary, role, fastball, TTO, arsenal, execution, release point, hard-hit rate, platoon, first pitch, appearances, and workload). The LLM processes all 2,000 tokens, most of which are irrelevant, increasing latency and cost while diluting the model's attention on the actually relevant data.

For a Q&A agent that handles many questions per session, this waste compounds. Ten questions about the same pitcher at 2,000 tokens each is 20,000 input tokens. With question-aware filtering, the same ten questions might use 500-800 tokens each -- a 60-75% reduction.

Worse, the "lost in the middle" phenomenon means the LLM may actually answer less accurately with more context: research consistently shows that when relevant information is buried in a large context, LLMs miss it more often than when it is presented in isolation (Arize AI field analysis, 2025).

**Why it happens:**
The existing `PitcherContext.to_prompt()` method is designed for narrative generation, where every section is potentially relevant because the LLM needs the full picture to find narrative threads. Developers reuse it for Q&A because it already works and "more context is better" feels intuitively correct. It is not. The report pipeline and Q&A pipeline have opposite context needs: reports need breadth (all sections), Q&A needs depth (the right section).

**How to avoid:**
- **Build a question-aware context filter.** Before sending context to the LLM, classify the question into one of the existing PitcherContext sections (fastball, arsenal, execution, platoon, workload, etc.) and send only those sections. This can be a simple keyword/pattern match -- not an LLM call. "fastball velocity" maps to the fastball section. "pitch mix" maps to arsenal. "splits" maps to platoon. "workload" maps to workload + appearances.
- **Create `PitcherContext.to_prompt_sections()` that returns a dict of section name to markdown.** The Q&A agent selects which sections to include. The report pipeline continues to use `to_prompt()` which joins all sections.
- **Default to sending 2-3 relevant sections plus the executive summary**, not the full context. The executive summary provides enough meta-context for the LLM to frame the answer without reading every detail.
- **Test with narrow questions.** If "What is his fastball velocity?" includes TTO data, platoon splits, and release point mechanics in the prompt, the filtering is not working.

**Warning signs:**
- All Q&A responses take roughly the same time regardless of question specificity.
- Token usage per Q&A call is comparable to a full report generation call.
- The LLM includes irrelevant details in its answer ("His fastball sits at 95.2 mph... and his platoon splits show...") when the user only asked about velocity.
- Narrow questions get worse answers than expected because the LLM is "lost in the middle."

**Phase to address:**
Phase 2 or 3 (Context Filtering) -- this requires `PitcherContext` refactoring, which is a cross-cutting change. Build the Q&A agent first with full context (Phase 1-2), then add filtering as an optimization phase. But plan for it architecturally from the start: the Q&A agent should accept a `sections: list[str]` parameter even if Phase 1 passes `["all"]`.

---

### Pitfall 3: Tool-Calling Agent Hallucinating Data Lookups

**What goes wrong:**
If the Q&A agent is built with pydantic-ai tools (e.g., a `lookup_pitcher` tool and a `get_pitch_metrics` tool), the LLM can hallucinate tool calls in several ways:

1. **Fabricated parameters:** The LLM calls `get_pitch_metrics(pitcher_id=999999, pitch_type="KN")` with an ID it invented because it "knows" the pitcher throws a knuckleball from its training data, even though the pitcher is not in the dataset or does not throw that pitch in 2026.

2. **Tool call when none is needed:** The user asks a general question ("What makes a good changeup?") and the LLM calls `lookup_pitcher()` anyway because it has been trained to use tools when available.

3. **Skipping the tool entirely:** The LLM has training-data knowledge about the pitcher and answers from memory instead of calling the data lookup tool. "Corbin Burnes throws his cutter at 88 mph" -- but the data says 86.4 mph. The answer sounds authoritative but is stale training data, not grounded in the actual dataset.

4. **Wrong tool sequence:** In a multi-tool setup, the LLM calls `get_pitch_metrics()` before `lookup_pitcher()`, passing a fabricated pitcher_id instead of resolving the name first.

Research from Arize AI (2025) confirms that hallucinated arguments are a primary production failure mode: "Agents confidently invent parameters that 'feel' correct rather than admitting uncertainty."

**Why it happens:**
LLMs treat tools as suggestions, not constraints. A tool called `get_pitch_metrics` with a parameter `pitcher_id: int` tells the LLM "you need an integer here" but does not tell it which integers are valid. The LLM fills in plausible-looking values from its training distribution. This is the tool-calling equivalent of hallucination.

The "skip the tool" failure is particularly insidious with baseball data because LLMs have extensive baseball knowledge in their training data. The model can generate a plausible-sounding answer about any well-known pitcher without ever touching the tools.

**How to avoid:**
- **Prefer a single-tool or zero-tool architecture for v1.4.** The simplest Q&A agent receives the PitcherContext as user-message context (not via a tool) and answers questions directly. No tool calls, no hallucinated parameters, no wrong sequences. The data pipeline runs before the agent, not inside it. This matches the existing report pipeline pattern.
- **If tools are used, validate all parameters against the dataset.** A `lookup_pitcher` tool should raise `ModelRetry("Pitcher ID 999999 not found in dataset")` so the LLM gets a clear error and can self-correct. pydantic-ai's `ModelRetry` exception is designed exactly for this.
- **Explicitly instruct the agent NOT to use training data.** The system prompt must say: "Answer ONLY from the provided data. If the data does not contain information to answer the question, say so. Never fill in details from your general knowledge."
- **Limit the tool count.** Research shows accuracy drops with more tools available. Keep to 2-3 tools maximum. The Q&A agent should need at most: (1) a name resolver and (2) a data lookup. Ideally, zero tools -- just context in the prompt.
- **Add a grounding check.** After the LLM answers, verify that any numbers it cites actually appear in the context. The existing `check_hallucinated_metrics()` regex scanner from the report pipeline is a starting model.

**Warning signs:**
- The agent produces answers about pitchers not in the dataset.
- The agent cites specific velocities or percentages that do not appear in the PitcherContext.
- Tool call logs show fabricated pitcher IDs or pitch types.
- The agent answers general baseball questions that are not grounded in data (working as a chatbot, not an analyst).

**Phase to address:**
Phase 2 (Q&A Agent Design) -- the tool vs. no-tool architecture decision must be made here. The recommendation is strongly toward no-tool (context-in-prompt) for v1.4 to avoid this entire category of failure.

---

### Pitfall 4: Breaking the Existing Report Pipeline While Adding Q&A

**What goes wrong:**
The Q&A feature shares modules with the report pipeline: `data.py`, `engine.py`, and `context.py`. A developer modifying `data.py` to add a `resolve_pitcher_name()` function accidentally changes the import order, modifies `PitcherData` to add an optional field that breaks existing unpacking, or alters `load_pitcher_data()` to accept a name string alongside an ID, introducing a code path that existing tests do not cover. The 200 existing tests continue to pass because they test the ID-based path, but the shared module now has a regression that surfaces only in edge cases.

More subtly, adding a Q&A entry point to `cli.py` (or a new `ask_cli.py`) that shares `parse_args()` can break the existing report CLI if argument parsing is modified to accommodate question input. argparse is sensitive to required/optional argument changes -- making `-p` optional (because Q&A might resolve by name) breaks every test that expects `-p` to be required.

**Why it happens:**
The existing codebase is a well-tested monolith with tightly coupled modules. The modules were designed for a single use case (ID-based report generation) and their interfaces reflect that assumption. Adding a second use case (name-based Q&A) requires touching the same modules, and "just add a parameter" changes ripple through the call chain.

The danger is amplified because the existing 200 tests all pass -- creating false confidence that changes are safe. The tests cover the report pipeline thoroughly but do not exercise the Q&A code paths.

**How to avoid:**
- **Create new modules for Q&A-specific logic.** Name resolution goes in `resolver.py`, not `data.py`. The Q&A agent goes in `qa.py`, not `report.py`. The Q&A CLI goes in `ask_cli.py`, not `cli.py`. The shared modules (`data.py`, `engine.py`, `context.py`) should not be modified unless absolutely necessary.
- **Compose, do not modify.** The Q&A pipeline should call `load_pitcher_data(pitcher_id, window_days)` with a resolved ID, not modify `load_pitcher_data` to accept names. Name resolution happens upstream of the data pipeline.
- **Separate CLI entry points.** Add a new `ask` subcommand or a separate `ask_cli.py` with its own `parse_args()`. Do not modify the existing `cli.py:parse_args()`. If both CLIs share a common runner, extract that to a shared module.
- **Run the full existing test suite after every change.** This sounds obvious, but in practice developers run only the new Q&A tests during development and discover report regressions late.
- **Add integration tests that exercise the report pipeline end-to-end** (not just unit tests) before starting Q&A work. If any Q&A change breaks the report pipeline, these tests catch it immediately.

**Warning signs:**
- Any diff to `data.py`, `engine.py`, or `context.py` in a Q&A PR.
- The existing `cli.py:parse_args()` function is modified.
- New optional parameters added to `load_pitcher_data()` or `assemble_pitcher_context()`.
- Test suite passes but a manual `uv run python -m pitcher_narratives.cli -p 592155` fails.

**Phase to address:**
All phases -- this is a cross-cutting concern. The module boundary decision (new modules vs. modifying existing) must be made in Phase 1 (Architecture). Every subsequent phase must be verified against the existing test suite.

---

### Pitfall 5: Over-Engineering Question Understanding

**What goes wrong:**
A developer builds a full NLU pipeline for question classification: intent detection, entity extraction, slot filling, follow-up resolution, multi-turn state management. The Q&A agent gets a tool for each question type (velocity tool, arsenal tool, platoon tool, workload tool). The system prompt becomes a 3,000-token instruction manual explaining 15 question categories. The result is a fragile Rube Goldberg machine that fails on questions that do not fit neatly into a category ("Is he tipping his pitches?"), while a simple prompt with full context would have answered it directly.

The academic research is clear on this: "Modern models handle JSON generation reliably enough that isolating schema generation into a separate tool wasn't worth the delegation cost. When in doubt, cutting hard logic and taking advantage of the multi-billion parameter model is often the right approach" (Elastic, 2025). For question answering over a 2,000-token context, the LLM does not need help understanding the question -- it needs the right context and clear instructions.

**Why it happens:**
Developers with NLP backgrounds default to structured classification pipelines. They decompose "What is his fastball velocity?" into `intent=velocity, entity=fastball, metric=speed` and route to a handler function. This was the right approach in 2020 with weak language models. With Claude Sonnet 4.6, the model can read 2,000 tokens of structured baseball data and answer any reasonable question about it without explicit routing.

The over-engineering instinct is also driven by the fear of Pitfall 2 (context bloat). "If I classify the question, I can send less context." This is true but solves a $0.001 problem with a $100 solution. The context budget for Q&A (~2K tokens) is small enough that sending the full context is cheaper than building and maintaining a classification pipeline.

**How to avoid:**
- **Start with the simplest possible architecture: one agent, one prompt, full context.** The user's question goes into the user message. The PitcherContext goes into the user message. The system prompt says "You are an analytical baseball assistant. Answer the question using only the provided data." No tools, no routing, no classification.
- **Add complexity only when the simple approach measurably fails.** If the simple agent cannot answer a specific class of questions, add targeted context filtering for that class. Do not pre-build routing for hypothetical question types.
- **The Q&A agent should be a single pydantic-ai Agent with `output_type=str`.** This matches the existing editor agent pattern. No structured output needed for free-form Q&A responses.
- **If context filtering is needed later, use keyword matching, not LLM classification.** A simple dict mapping `{"velocity": ["fastball"], "arsenal": ["arsenal", "mix", "pitch type"], ...}` is deterministic, zero-cost, and testable. An LLM classifier for the same task is non-deterministic, costs tokens, and adds latency.

**Warning signs:**
- The Q&A module has more lines of question-routing code than actual agent interaction code.
- There are more than 2 tools registered on the Q&A agent.
- The system prompt for Q&A is longer than the system prompt for the synthesizer (currently ~3,000 tokens).
- Questions that seem simple ("How is he doing?") fail because they do not match a recognized intent category.

**Phase to address:**
Phase 2 (Q&A Agent Design) -- this is an architecture decision. The recommendation is to start with the simplest possible agent and resist adding complexity until there is evidence it is needed.

---

### Pitfall 6: Answering Questions the Data Cannot Support

**What goes wrong:**
The user asks "Will Corbin Burnes get a Cy Young vote?" or "How does he compare to Gerrit Cole?" or "What happened in his game against the Dodgers last night?" The Q&A agent gamely attempts to answer, drawing on LLM training data rather than the provided context. The response sounds authoritative but is completely ungrounded: the dataset contains pitch-level Statcast data and Pitching+ metrics for 2026, not awards predictions, cross-pitcher comparisons, or game narratives.

This is the Q&A equivalent of the report pipeline's hallucination problem, but worse: the report pipeline has an anchor checker that catches drift. The Q&A pipeline has no equivalent guard because each question is independent -- there is no synthesis to check against.

**Why it happens:**
LLMs are trained to be helpful. When asked a question, they answer it. They do not say "I cannot answer this from the provided data" unless explicitly instructed to do so, and even then they sometimes answer anyway. The instinct to be helpful overrides the instruction to be grounded.

The boundary between "answerable from data" and "requires external knowledge" is fuzzy. "Is his slider improving?" is answerable (Pitching+ trend data). "Is his slider the best in baseball?" is not (requires cross-pitcher comparison the dataset does not support). "Is his slider good enough to start?" is borderline (requires interpretation beyond the data).

**How to avoid:**
- **Define scope explicitly in the system prompt.** "You can answer questions about this pitcher's velocity, pitch mix, Pitching+ metrics, platoon splits, workload, and execution. You CANNOT answer questions about: other pitchers, future predictions, awards, game narratives, or anything not in the provided data. If the question falls outside your scope, say so clearly."
- **Include a "What I can answer" section in the help output.** The CLI should print a brief guide when invoked with `--help` or when the user's first question is ambiguous.
- **Add scope-boundary examples to the system prompt.** Few-shot examples of out-of-scope questions with the correct refusal response anchor the model's behavior better than instructions alone.
- **Reuse the anti-recitation patterns from the report pipeline.** The existing synthesizer and editor prompts have explicit "do not project future performance" and "report the math" instructions. Adapt these for Q&A.
- **Test with deliberately out-of-scope questions.** "Who is the best pitcher in baseball?", "Will he make the All-Star team?", "How does he compare to [other pitcher]?" should all produce clear refusals.

**Warning signs:**
- The Q&A agent answers comparative questions ("better than X") without flagging that it cannot compare pitchers.
- The agent makes predictions ("He is likely to...") despite having only historical data.
- The agent cites statistics that do not appear in the PitcherContext.
- The agent answers about games, opponents, or events not in the Statcast data.

**Phase to address:**
Phase 2 (Q&A Agent Prompt Design) -- the scope boundary must be in the system prompt from the first version. Testing with out-of-scope questions should be in Phase 3 (Validation).

---

### Pitfall 7: Accent and Unicode Handling Silently Dropping Pitchers

**What goes wrong:**
A user types `ask "How is Jose Berrios doing?"` and the system returns "No pitcher found matching 'Jose Berrios'" -- even though Jose Berrios (pitcher 621244) is in the dataset as "Berrios, Jose" with an accent on the e. The fuzzy matcher scores "Jose" vs "Jose" at ~90% (close but not identical), and the combined name score drops below threshold.

The problem is asymmetric: 71 pitchers in the dataset have accented characters. Users typing on an English keyboard will never type those accents. The system must match "Ramirez" to both "Ramirez" (no accent, 1 pitcher) and "Ramirez" (accent, 5 pitchers) or it silently excludes ~4% of the roster.

More insidiously, names with suffixes add noise: "Edwards Jr., Carl" should match "Carl Edwards", "Edwards Jr", and "Carl Edwards Jr" but not "Carl Edwards III" (a different fictional person). The dataset has 10 suffixed names (Jr., II, III, IV). Fuzzy matching on raw strings penalizes queries that omit suffixes.

**Why it happens:**
String matching operates on bytes/codepoints by default. "e" (U+0065 + U+0301, combining acute) and "e" (U+0065) are different codepoints. Developers test with ASCII names and the matcher works perfectly. Accented names fail silently because the threshold drops them just below the match cutoff -- they do not throw errors, they just return "not found."

Suffix handling fails because "Edwards Jr., Carl" contains "Jr." as literal text that inflates the edit distance when the query omits it.

**How to avoid:**
- **Normalize all names to ASCII before matching.** `unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()` strips all accents. Match against normalized names, then map back to the original accented form for display.
- **Strip suffixes before matching.** Remove "Jr.", "Sr.", "II", "III", "IV" from both query and candidate names before scoring. Store the suffix separately for display.
- **Build a test suite with every accented name in the dataset.** All 71 accented names should be matchable by their ASCII equivalent. All 10 suffixed names should be matchable without the suffix.
- **Use `rapidfuzz` with `processor=rapidfuzz.utils.default_process`** which lowercases and strips non-alphanumeric characters. This helps but does not solve the accent problem -- explicit normalization is still needed.

**Warning signs:**
- A user searches for a well-known pitcher with an accented name and gets "not found."
- The name resolver's test suite uses only ASCII names.
- No `unicodedata` import exists in the resolver module.
- Suffixed names require the exact suffix to match.

**Phase to address:**
Phase 1 (Name Resolution) -- Unicode normalization must be in the matching pipeline from day one. It is trivial to add but impossible to retrofit without re-testing all name matching logic.

---

### Pitfall 8: Q&A Agent Reciting Numbers Instead of Providing Insight

**What goes wrong:**
The user asks "How is his fastball doing?" and the Q&A agent responds: "His four-seam fastball averages 95.2 mph, with a P+ of 108, S+ of 112, L+ of 98. His movement is +0.3 inches horizontal and -0.2 inches vertical. His CSW% is 28.4% and his zone rate is 52.1%." This is a data dump, not an answer. The user could have read the PitcherContext themselves for the same information.

The existing report pipeline spent three milestones (v1.0, v1.1, v1.3) building anti-recitation prompting patterns to prevent exactly this. The synthesizer has "absolute objectivity" and "report the math" instructions. The editor has "find the thread" and "pragmatic voice" instructions. These patterns are the core value of the project. If the Q&A agent regresses to number recitation, it undermines the entire product philosophy.

**Why it happens:**
The Q&A agent prompt is written from scratch without incorporating the hard-won anti-recitation patterns from the report pipeline. The developer thinks "Q&A is simpler than reports -- just answer the question." But "just answering" a question about structured data defaults to reciting the data, because that is what the data contains. Insight requires the same prompt engineering that the report pipeline invested in.

**How to avoid:**
- **Inherit the editorial voice from the report pipeline.** The Q&A system prompt should include the same anti-recitation principles: "Do not recite numbers. Interpret them. Tell the user what the numbers mean, not what the numbers are. Use the same pragmatic, analytical voice as a front-office analyst."
- **Include delta-first framing.** "When discussing metrics, lead with the change (delta) and its significance, not the absolute value. 'His fastball has gained 1.5 mph since his season average, and his S+ is up 12 points, suggesting a real stuff improvement' -- not 'His fastball averages 95.2 mph with an S+ of 112.'"
- **Test with a rubric.** For each Q&A test case, check: Does the answer contain more than 3 raw numbers? Does it start with a data point or with an insight? Does it use words like "suggests," "indicates," "this means" or just lists values?
- **Consider reusing the synthesizer prompt's framing for the Q&A agent.** The synthesizer already knows how to extract signal from noise in PitcherContext data. The Q&A agent can be a targeted version of the same thing.

**Warning signs:**
- Q&A responses read like formatted tables or bullet-point lists of metrics.
- The word "suggests" or "indicates" never appears in Q&A output.
- Q&A output is shorter than 2 sentences (data dumps are terse; insights require explanation).
- Users say "I could have read the data myself."

**Phase to address:**
Phase 2 (Q&A Agent Prompt Design) -- the anti-recitation patterns must be in the system prompt from the first version. This is a prompt engineering task, not a code change, but it requires intentional design.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Sending full PitcherContext for every question | No need to build context filtering; reuse `to_prompt()` directly | ~60-75% wasted tokens per query; slower responses; "lost in the middle" accuracy degradation | v1.4 MVP only -- add section-level filtering before v1.5 |
| Single-match name resolution (no disambiguation) | Simpler code, no interactive disambiguation flow | Silent wrong-pitcher answers for common names; trust erosion | Never -- disambiguation is table stakes for name resolution |
| No scope boundary in Q&A prompt | Faster to write the prompt; model seems to "just work" in demos | Agent answers out-of-scope questions with hallucinated content; no way to detect this automatically | Never -- scope boundary must exist from first prompt version |
| Reusing `cli.py:parse_args()` for Q&A arguments | Less code duplication; one CLI entry point | Report CLI breaks when Q&A-specific arguments are added; argparse changes ripple through tests | Never -- create separate entry point from day one |
| No grounding check on Q&A output | Faster iteration; trust the model | No detection of training-data leakage into answers; users get stale data | v1.4 MVP only -- add grounding check before v1.5 |
| Hardcoding name resolution to current parquet file | Works for single-season data; no need for data versioning | Breaks when 2027 data is loaded (different pitcher roster); name index is stale | Acceptable for v1.4 (single-season tool) but document the assumption |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Name resolver + `load_pitcher_data()` | Modifying `load_pitcher_data()` to accept a name string, coupling name resolution to data loading | Keep name resolution separate: `resolve_name("Rodriguez") -> [pitcher_ids]`, then `load_pitcher_data(pitcher_id)`. The data loader should only accept IDs. |
| Q&A agent + PitcherContext | Creating a new context assembly function for Q&A instead of reusing `assemble_pitcher_context()` | Reuse the existing function. If section filtering is needed, add it as a post-processing step: `ctx = assemble_pitcher_context(data); filtered_prompt = ctx.to_prompt_sections(["fastball", "arsenal"])` |
| Q&A CLI + report CLI | Adding Q&A subcommand by modifying `cli.py:parse_args()` with argparse subparsers | Create `ask_cli.py` with its own `parse_args()`. If subcommands are desired, create a new top-level `main_cli.py` that dispatches to both. |
| Q&A prompt + existing anti-recitation patterns | Writing the Q&A system prompt from scratch, losing the editorial voice patterns from `_EDITOR_PROMPT` and `_SYNTHESIZER_PROMPT` | Extract the reusable anti-recitation principles into a shared prompt fragment. Both the report pipeline and Q&A agent import from the same source. |
| Fuzzy matching library + existing dependencies | Adding `rapidfuzz` to `pyproject.toml` when a simpler approach (polars string operations + Levenshtein from stdlib) might suffice | Evaluate whether polars' built-in string similarity functions or `difflib.SequenceMatcher` (stdlib) are sufficient for 1,651 names before adding a dependency. For 1,651 entries, even O(n) brute-force is instant. |
| pydantic-ai tool registration + existing agents | Registering data-lookup tools on the Q&A agent that overlap with the report pipeline's agent capabilities | Q&A agent should be a standalone Agent instance, not sharing tools with report agents. Different use case, different tool set (or no tools). |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading full parquet for every question | 2-3 second latency before the LLM even starts; 145K rows read for a single name lookup | Cache the name-to-ID index in memory (1,651 entries, <100KB). Only load full pitcher data after ID resolution. | Immediately -- perceptible on first use |
| Re-loading pitcher data for each question in a session | If the user asks multiple questions about the same pitcher, `load_pitcher_data()` re-reads parquet + 8 CSVs each time | Cache `PitcherData` by pitcher_id. A simple dict cache is sufficient for a CLI session. | After 2-3 questions about the same pitcher |
| Full PitcherContext assembly for every question | `assemble_pitcher_context()` calls 10 engine functions, each doing polars computations. Unnecessary if the context was already assembled for the same pitcher+window. | Cache the assembled PitcherContext alongside PitcherData. | After 2-3 questions about the same pitcher |
| Eager name index building on every CLI invocation | Building the full name index from parquet at startup adds 2-3 seconds even when the user already knows the pitcher ID | Build name index lazily on first name-based query, or build it once and cache to a lightweight file (JSON or pickle). | On every invocation if the user uses `--pitcher` ID directly |
| Unicode normalization on every fuzzy match | Normalizing 1,651 names per query is O(n) string operations | Pre-normalize names when building the index. Normalize the query once. | Never a real bottleneck at this scale, but wasteful |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silently picking the wrong pitcher from ambiguous name | User gets a confident, detailed answer about the wrong person. Trust destroyed. | Show disambiguation prompt: "Found 12 pitchers matching 'Rodriguez'. Did you mean: [list with team codes]?" |
| No indication of data scope | User asks about 2025 data or a pitcher not in the dataset; gets a vague "I don't have that information" | State scope upfront: "I have 2026 Statcast data for [pitcher name]. Ask me about their velocity, pitch mix, Pitching+ metrics, splits, or workload." |
| Error messages that do not suggest next steps | "Pitcher not found" with no guidance | "No pitcher found matching 'Rodriguex'. Did you mean 'Rodriguez'? (12 pitchers). Try a more specific name like 'Grayson Rodriguez'." |
| Q&A output format inconsistent with report output | Reports are polished prose; Q&A responses are terse one-liners or data dumps | Q&A responses should match the report's analytical voice. Not as long, but same quality of insight. |
| No way to see what data the agent is working with | User cannot verify whether the agent has the right pitcher or the right data | After name resolution, print: "Analyzing [pitcher name] (ID: [id], [team], [throws]HP) -- [N] appearances in [window] day window" to stderr, matching the existing verbose output. |
| Asking for a pitcher with no recent data | User asks about a pitcher who was DFA'd or injured and has no appearances in the lookback window | Handle gracefully: "Cam Booser has no appearances in the last 30 days. Try a longer window with --window 90." |

## "Looks Done But Isn't" Checklist

- [ ] **Name disambiguation:** Test with "Rodriguez", "Garcia", "Smith", "Anderson", "Martinez" -- all have 8+ collisions in the dataset. A single-match return is a bug for these names.
- [ ] **Accent normalization:** Test with "Berrios", "Ramirez", "Perez", "Diaz", "Dominguez" -- all have accented variants in the dataset. Unaccented query must match accented entries.
- [ ] **Suffix handling:** Test with "Edwards" (should match "Edwards Jr., Carl"), "Leiter" (should match "Leiter Jr., Mark"), "Lynch" (should match "Lynch IV, Daniel").
- [ ] **Out-of-scope refusal:** Ask "Who is the best pitcher in baseball?", "How does he compare to [other pitcher]?", "Will he make the All-Star team?" -- all must be refused with a clear explanation, not answered.
- [ ] **Grounding check:** Ask about a well-known pitcher and verify no answer content comes from LLM training data rather than the PitcherContext. Check that cited numbers appear in the context document.
- [ ] **Existing tests pass:** All 200 existing tests pass with zero modifications to `data.py`, `engine.py`, `context.py`, or `report.py`.
- [ ] **Report pipeline still works:** `uv run python -m pitcher_narratives.cli -p 592155 --provider openai` produces the same output as before Q&A was added.
- [ ] **Empty result handling:** Ask about a pitcher with no appearances in the window. The system should explain the data gap, not crash or return a vague error.
- [ ] **First-name-only queries:** "Grayson" should not match (too ambiguous). "Shohei" might match uniquely. Test both cases.
- [ ] **Case insensitivity:** "grayson rodriguez", "GRAYSON RODRIGUEZ", "Grayson Rodriguez" should all produce the same result.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong pitcher from ambiguous name (Pitfall 1) | LOW | Add disambiguation flow; change resolver to return list instead of single result; add interactive selection |
| Context bloat (Pitfall 2) | MEDIUM | Refactor `PitcherContext.to_prompt()` into section-level methods; add section selection to Q&A agent call; requires touching context.py |
| Tool hallucination (Pitfall 3) | LOW-MEDIUM | Remove tools and switch to context-in-prompt pattern (if over-engineered); add ModelRetry validation (if keeping tools) |
| Report pipeline regression (Pitfall 4) | HIGH | Diagnose which module change caused the regression; may require reverting and re-implementing with proper module boundaries |
| Over-engineered NLU (Pitfall 5) | MEDIUM | Remove classification pipeline; replace with simple agent + full context; discard routing code |
| Out-of-scope answers (Pitfall 6) | LOW | Add scope boundary examples to system prompt; add out-of-scope test cases |
| Unicode/accent failures (Pitfall 7) | LOW | Add `unicodedata.normalize()` to the resolver; add suffix stripping; add test cases for all 71 accented names |
| Number recitation (Pitfall 8) | LOW | Revise system prompt with anti-recitation patterns from report pipeline; add insight-quality test rubric |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Wrong pitcher from ambiguous name | Phase 1 (Name Resolution) | Test with all 168 duplicate-last-name families. Disambiguation flow works for "Rodriguez" (12 matches). Single-name pitchers resolve directly. |
| Context bloat | Phase 2/3 (Context Filtering) | Measure token count per Q&A call. Narrow questions (fastball velocity) should use <50% of full context tokens. Broad questions can use full context. |
| Tool hallucination | Phase 2 (Agent Architecture) | If tools are used: verify all tool calls use valid pitcher IDs from the dataset. If no-tool: verify no tool registration on Q&A agent. Run 10 diverse questions and check no training-data leakage. |
| Report pipeline regression | All Phases | Full test suite (200 tests) passes after every phase. Manual smoke test of report pipeline after each phase. Zero modifications to existing shared modules. |
| Over-engineered NLU | Phase 2 (Agent Design) | Q&A module has fewer lines of code than report module's `_SYNTHESIZER_PROMPT`. No intent-classification code. Agent has 0-2 tools max. |
| Out-of-scope answers | Phase 2 (Prompt Design) + Phase 3 (Validation) | 5+ out-of-scope test questions all produce clear refusals. No comparative or predictive answers. |
| Unicode/accent failures | Phase 1 (Name Resolution) | All 71 accented names matchable by ASCII equivalent. All 10 suffixed names matchable without suffix. Automated test coverage for both. |
| Number recitation | Phase 2 (Prompt Design) | 5+ Q&A test responses checked against rubric: fewer than 3 raw numbers, opens with insight not data point, uses interpretive language. |

## Sources

- Direct dataset analysis: `statcast_2026.parquet` -- 1,651 unique pitchers, 168 duplicate last-name families, 71 accented names, 10 suffixed names (HIGH confidence -- read directly from data)
- Direct codebase analysis: `data.py`, `engine.py`, `context.py`, `report.py`, `cli.py`, all 6 test files (HIGH confidence -- read directly)
- [Arize AI: Why AI Agents Break: A Field Analysis of Production Failures](https://arize.com/blog/common-ai-agent-failures/) -- tool hallucination, context overload, instruction drift (MEDIUM confidence -- web source, 2025)
- [DEV Community: Why LLM Agents Break When You Give Them Tools](https://dev.to/terzioglub/why-llm-agents-break-when-you-give-them-tools-and-what-to-do-about-it-f5) -- tool composition failures, prevention strategies (MEDIUM confidence -- web source)
- [DEV Community: 3 Patterns That Fix LLM API Calling](https://dev.to/docat0209/3-patterns-that-fix-llm-api-calling-stop-getting-hallucinated-parameters-4n3b) -- hallucinated parameters, schema simplification (MEDIUM confidence -- web source, 2026)
- [ArXiv: Are We Asking the Right Questions? On Ambiguity in NL Queries for Tabular Data Analysis](https://arxiv.org/html/2511.04584) -- question ambiguity taxonomy, five dimensions of procedural/data specification (MEDIUM confidence -- academic, 2025)
- [ArXiv: Reducing Tool Hallucination via Reliability Alignment](https://arxiv.org/html/2412.04141v1) -- tool selection vs. tool usage hallucination taxonomy (MEDIUM confidence -- academic, 2024)
- [Fuzzy Name Matching (Compass True North)](https://medium.com/compass-true-north/fuzzy-name-matching-dd7593754f19) -- practical fuzzy matching patterns, false positive risk (LOW confidence -- blog)
- [RapidFuzz Documentation](https://rapidfuzz.github.io/RapidFuzz/) -- API reference, preprocessing defaults, scoring functions (HIGH confidence -- official docs)
- [Pydantic AI Tools Documentation](https://ai.pydantic.dev/tools/) -- tool registration patterns, RunContext, ModelRetry (HIGH confidence -- official docs)
- [Pydantic AI Function Tools](https://ai.pydantic.dev/tools/) -- best practices for tool definitions, docstring extraction (HIGH confidence -- official docs)
- [Elastic: Context Engineering vs Prompt Engineering](https://www.elastic.co/search-labs/blog/context-engineering-vs-prompt-engineering) -- when to use tools vs direct prompting (MEDIUM confidence -- vendor blog, 2025)

---
*Pitfalls research for: Interactive Q&A over structured baseball data (v1.4 milestone)*
*Researched: 2026-03-30*
