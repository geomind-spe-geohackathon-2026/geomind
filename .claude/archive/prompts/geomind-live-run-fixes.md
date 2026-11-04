# geomind: fixes from the first live runs

Repository: geomind (GitHub `geomind-spe-geohackathon-2026/geomind`; the old `crust-team/geomind` URL redirects). Work on `main`. You start at `c9a5c1c` (geomind 0.4.1), with gemini at `../gemini` (dev, 0.5.1).
This prompt is self-contained: everything you need is here.

## 0. What happened

The app ran three live tests of geomind 0.4.1 on the competition case, on a real model (`deepseek/deepseek-v4.1-flash-1017` through OpenRouter, provider Relace). These are the problems it found, most important first.

1. **Design loop.** The prompt was "Size the plant, then optimise LCTS, and explain the result", with a cap of 0.50 USD. The run stopped at the cap, at 0.547 USD, after 321k input tokens and 51 s. No study had run yet.
   - a. `size_plant` failed twice. First the model passed `hphp2` where `design/<name>` is required. Then gemini said `size.doublets.range` was missing. The model learns the reference form and the ranges sizing needs only from errors.
   - b. The Designer built its own plant instead of using the project's existing plant (`HeatingHeatPumpCoolingPlant`, listed under `project_plants` by `list_plants`).
2. **After a budget stop the user gets nothing:** no partial answer and no summary of what was done.
3. **`save_profile`:** the model passed the step unit `day`, while gemini accepts `d`. The error did not say which units are valid.
4. **`update_state`:** it failed 3 times on `/results`, first on the path form and then on the value shape. The input schema is `list[dict[str, Any]]`, so the model has to guess. The shapes are only described in prose in the docstring.
5. **Cost:** a simple `save_profile` request took about 14 steps, 190k input tokens and 0.34 USD. The context per step is very large.
6. **Thread claim:** the docs say `UsageLedger.spent` and `save_profile`'s artifact reads run in a worker thread, but they run on the event loop. The app had to work around this.
7. **Budget overshoot:** the budget is checked only before each LLM call, so a run overshoots by one call: 9% in the design run, and 63% with a 0.01 USD cap.
7b. **Crash before the Economist (found on a DeepSeek design chat, the most urgent bug).** The coordinator, Designer and Verifier ran, and the Verifier passed a feasible design. Then the run failed with `sequence item 0: expected str instance, dict found`. The cause is `geomind/loops/design.py:economist_task` (around line 289-293), which joins `design.start_result` and `alternatives[].result` as reference strings while the Designer recorded a dict. Any model can do this, so every design chat can crash just before the Economist.
7c. **A budget stop looks like a crash.** It reaches the user as `{"code":"internal","message":"designer: the nested run stopped with denied"}`. It should say that the run or project budget was reached, give what was spent and the cap, and use a budget code, not `internal`.
7d. **The Designer invented ranges.** After `size_plant` failed on a missing `size.doublets.range`, the Designer set ranges itself with `set_ranges`, for example depth 2000-3500 m, doublets 1-3 and heat pump capacity 3-30 MW. Ranges are design bounds that only the user or the case gives, under Sahand's no-defaults rule. When one is missing, the agent asks the user with `ask_user`, proposing values with a one-line reason and asking for confirmation. In a run with no user to ask (`--mode auto`), the run stops with that question as its partial answer. It never sets a range that nobody confirmed.
7e. **Context growth, measured in run `c45d1c19`.** Every Designer call resent the full outputs of `build_plant` and `read_plant`, 31-36k characters each, so the input per call grew from 12k to 66k tokens over 8 calls.
8a. **A silent default model:** in those tests `GEOMIND_MODEL` was not set, so the agents ran on geomind's built-in default model (`anthropic/claude-sonnet-5.5`) and only the coordinator ran on deepseek. Nobody noticed. The errors above happened even with Sonnet, so a weaker model will hit them more often. Under the no-defaults rule, a live run must name its models: with a real provider and no model set for a role, the run refuses to start and names the setting that is missing (`GEOMIND_MODEL`, `GEOMIND_CHEAP_MODEL`, or the per-role setting). `geomind check-live` reports it. Scripted and fake runs are unchanged. Every run's log and its export header show the model of every role. This is section B's work.
8. **Flaky tests (found with 0.4.1):** a few tests on the gemini example `hackathon_2026` (in `test_results`, `test_runs` and `test_plants`) fail under xdist and pass alone. gemini 0.5.1 at `4095ec6` may be slower.

## 0b. Rules (all of them apply)

- **NO LIVE RUNS (Sahand, 2026-11-02 21:50).** Spend no LLM tokens. Make no call to OpenRouter or any real model provider: no live run, no `geomind check-live` against the network, no live eval and no live recording. Fix the bugs only, and check them only with the fake and scripted providers and offline tests. Unset `OPENROUTER_API_KEY` in your shell before you start (`unset OPENROUTER_API_KEY`). If a step seems to need a live call, skip it and list it in the report.
- **Coordinator.** The main session only plans, dispatches, reviews diffs and merges. Workers run as subagents: sonnet for code, haiku for read-only search. Each worker has its own git worktree (`../geomind-<name>`, branch `live-<name>`) and owns a disjoint set of files. Workers write details to `.tmp/live/<name>.md` and report back in at most 15 lines. Remove the worktrees and branches after their merge.
- **gemini is the source of truth and is read-only.** Change nothing in `../gemini`. geomind adds no aliases for gemini names or units. If gemini should accept something, such as the unit `day`, write it to `.tmp/live/gemini-requests.md`. geomind's job is to make gemini's own error and its accepted values visible to the model.
- **General.** Every fix works for any case, plant and request. Nothing is tuned to the competition case or to one model.
- **No defaults in package code.** A new setting, such as a budget reserve, has no default: with no value it is off, and the docs say so.
- **Backward compatible.** Logs, stores and recordings from 0.4.x still load, replay and export. A tightened input schema must still accept every input that was valid before.
- **No comments in code.** Explanations go in docstrings. Section-header comments and tool directives are allowed.
- **Quality.** Write a failing test before each fix. Keep nesting at 3 levels or fewer and functions around 40 lines or fewer. Use guard clauses. Leave no dead code and use full-word names.
- **Tests.** Use the development profile while working: tests of the changed files and of everything that imports them, run in parallel, with fast-tier tests at 1 s or less. Run `make test-all`, `make lint` and every recording's replay (`tests/integration/test_eval_replay.py`, slow tier included) once before the push. Never shrink or delete recordings or goldens.
- **Docs in the same commit.** Update `.claude/docs/` (tools, prompts, hooks, runtime), the contract map and `CHANGELOG.md`.
- **Temporary files** go only in `.tmp/live/`.

## 1. Setup and measurement (coordinator, with a haiku worker)

1. Run `git pull --ff-only origin main` and `git -C ../gemini pull --ff-only`. Record both commits.
2. Run the fast tier once as a baseline. Record the flaky tests from item 8 with their durations under xdist and alone.
3. Measure where the context goes, offline only, with no real model call. Use the scripted design run and a scripted `save_profile` chat on the competition case. For every step, write to `.tmp/live/context.md` the input tokens split into:
   - the system prompt;
   - the skills;
   - the tool schemas, per tool;
   - the history, split into messages and tool results, per tool.

   Use geomind's own token counting if it has one; otherwise count characters divided by 4 and say so. Name the five largest items. This measurement decides what section C cuts.

## 2. Section T: tools tell the model what they need (worker T)

T owns `geomind/tools/gemini/study.py`, `plants.py` and `profiles.py` (or wherever `save_profile` lives), `geomind/tools/state.py`, and their tests.

1. **References.** Every tool argument that takes a stored reference gets a JSON Schema `pattern`, such as `^design/[^/]+$` for designs, `^study/[^/]+$` and `^result/[^/]+$`, plus a description with one example. A wrong reference gets an error that lists the stored references of that kind in the chat. Apply this to every tool, not only `size_plant`.
2. **What sizing needs.** The `size_plant` description says that sizing reads the plant's ranges and `params.backup`. When gemini reports a missing range, the tool error names each missing path. It also gives the `set_ranges` call that would add it, with the parameter's unit taken from gemini's `capabilities()` or `plant.ranges`. It never suggests a numeric value. Do the same for `optimize`, `run_study` with `prepare: ["size"]`, and any other tool that gemini can reject for a missing range or option.
3. **Units.** When gemini rejects a unit, as with the step unit `day` in `save_profile`, the error gives gemini's own message plus the units gemini accepts for that quantity, read from gemini and not hard-coded. Apply this in the shared error path for gemini unit errors, so every tool gets it. File `day`, `h` and `hour` as a gemini request.
4. **`update_state` schema.** Replace `list[dict[str, Any]]` with a typed schema: `op` as an enum; `path` with a pattern for the allowed roots; and `value` as `oneOf` the existing pydantic models of a requirement, assumption, result and question, so the shapes come from the models. Every input that was valid before stays valid. A rejected change returns the expected shape for that path in the error. Add a test for each of the three failures the live run hit on `/results`.
5. **Tests:** a wrong reference lists the stored ones; a missing range names the path and the `set_ranges` call; a bad unit lists gemini's units; and each `update_state` failure gives the shape.

## 3. Section D: the Designer starts from the project's plant (worker D)

D owns `geomind/prompts/design/`, the designing skill, `geomind/loops/design.py` (the task texts), the `design` model in `geomind/context/state.py` and the design recordings.

1. When the project has plants (`list_plants` returns `project_plants`), the Designer starts from one of them. It loads the plant with `read_plant(project_plant=...)` and stores it as a design before it sizes or optimizes. It builds a new plant only when no project plant fits the request, and then it says why in an assumption.
2. The DesignLoop's first task tells the Designer the names of the project's plants when there are any, so the Designer does not have to discover them with extra steps.
3. The Designer prompt shows the size-then-optimize path as one short worked sequence. It covers storing the project plant, checking ranges and backup, `set_ranges` if needed, `size_plant`, `optimize`, `simulate` and `check_results`, with the reference forms used.
4. Re-record the design recordings whose decisions change, with the scripted model, and keep the old ones' replay tests passing (logs from 0.4.x).
5. Tests: with a project plant present, the scripted Designer's first study call uses a design stored from it.
7. **Ranges (item 7d).** The Designer prompt, the designing skill and the `set_ranges` description all say that a range comes from the user or the case. When one is missing, `ask_user` proposes it and waits for confirmation, and an auto run stops with the question. Add a scripted test: a missing range leads to `ask_user`, not `set_ranges`. Check the other agents' prompts for the same gap, including the Economist with `sample_uncertainty` and `sensitivity` ranges.
6. **The crash (item 7b), with a failing test first.** Type the `design` section of the problem state: `reference`, `result` and `start_result` are references matching `^(design|result)/[^/]+$`, and `alternatives` is a list of `{family, design, result}` with the same patterns. `update_state` then rejects a dict there, and the error shows the expected shape. T's typed schema covers the path; D owns the model in `geomind/context/state.py`, so agree on it with T. Every loop function that reads the state (`first_task`, `economist_task`, `explainer_task` and any others) reads only through the typed model and never joins raw values. Test it with a scripted Designer that records a dict as `start_result`: the change is refused with the shape, and the loop never crashes. Check that a 0.4.x state holding a dict still loads, either converted or reported as an issue, but never crashing.

## 4. Section C: a smaller context (worker C)

C owns `geomind/engine/context.py`, `geomind/engine/compaction.py`, the tool-result rendering, the system prompts' shared parts, and their tests. If a cut needs a prompt file that D owns, C waits for D's merge.

1. Cut the five largest items from the measurement, whichever they are. Likely candidates, to confirm or drop:
   - large tool results kept whole in history, such as `read_case` with its `schema` section, `read_plant`, simulation results and gemini schemas. Keep a short summary plus the stored reference in history, and let the model read the full content again by reference;
   - big JSON schemas inside tool definitions, such as `build_plant`'s `gm.plants.schema()`. Give the tool a small schema and a `read_schema` tool or reference instead;
   - skills loaded whole when only one part is needed;
   - repeated system text across nested runs.
   Whatever the measurement shows, old tool results must not stay whole in history (item 7e). A tool result older than the current step is replaced by a short summary plus its stored reference, which the model can read again. Use the existing compaction or tool-result rendering, not a second mechanism. Test it with a scripted run of 8 Designer calls: the input of call 8 is at most 1.5 times that of call 1.
2. Keep the prompt prefix stable across steps (system prompt, tools, then history), so provider prompt caching can work. Record the cached input tokens per step, which the export already shows.
3. Targets, measured on the same scripted runs as in setup step 3:
   - the scripted `save_profile` request takes 5 steps or fewer and less than a quarter of today's input tokens;
   - the scripted design run's input tokens fall by at least half.

   Report before and after. If a target is not reached, say what remains and why.
4. Nothing is lost: the agents can still reach every stored artifact, and every recording still replays.

## 5. Section B: budgets and the answer after a stop (worker B)

B owns `geomind/engine/hooks.py` (the budget hooks), `geomind/engine/engine.py` and `run.py` (only the stop path), the ledger and stores code for item 6, and their tests.

1. **No overshoot.** Before each LLM call, the budget hooks estimate that call's cost: its input tokens (counted as the provider will count them, or as an upper bound) times the price, plus the `max_tokens` output limit times the output price.
   - If the estimate would pass the cap, they lower the call's `max_tokens` to what fits. If even the input does not fit, they deny the call.
   - Use the model's prices from wherever geomind already reads them, with no new price table.
   - A run then ends at or below its cap. Test it with a 0.01 USD cap.
1b. **A budget stop is not internal (item 7c).** A stop on a run budget or project budget, in a nested run or at the top, reaches the user and the parent run with a budget code (`budget_exceeded`, or the code geomind already uses for budgets). Its message says which budget was reached, what was spent and the cap. Never use `internal`. Test both cases, nested and top level.
2. **An answer after a stop.** When a run stops on a budget, step limit or time limit, the user gets a partial answer built without an LLM call, from the problem state and the log:
   - what was asked;
   - which designs, studies and results exist, with their references;
   - which checks passed or failed;
   - the open questions and unconfirmed assumptions;
   - why the run stopped and what a rerun with a higher cap would do next.

   It is the run's answer with `stop_reason` unchanged, it is shown by the CLI and the export, and it is streamed like any answer. Also add an optional setting `answer_reserve`, a cost or token amount kept back so the Explainer can write a short real answer at the end. It has no default and is off when unset.
3. **Thread claims (item 6).** Make code and docs agree. Run `UsageLedger.spent` and the artifact reads of `save_profile` in a worker thread (`asyncio.to_thread`) if the docs' contract is the right one. Otherwise correct the docs and the contract map. Choose the first unless it breaks something, and say which.
4. **Models named (item 8a).** A live run with no model set for a role refuses to start, and the refusal names the missing setting. `check-live` reports it too. Remove the built-in model fallbacks from package code, or make them apply only to the fake and scripted providers. Test that a live run with no `GEOMIND_MODEL` is refused.
5. Tests: no overshoot with a small cap; the partial answer after each kind of stop; the reserve when set; ledger and artifact calls off the event loop.

## 5b. Section M: no Anthropic model anywhere (worker M, Sahand's hard rule)

Sahand's rule (2026-11-02 21:48): never use Sonnet or any Anthropic model for the agents; use DeepSeek everywhere, and check every place carefully. Together with the no-defaults rule, this means geomind holds no model id as a fallback. The deploy config names the models (production uses `deepseek/deepseek-v4.1-flash-1017`), and a live run without them refuses to start.

M owns `geomind/runtime.py`, `geomind/providers/`, `geomind/context/compaction.py`, and the docs, tests, evals and samples that name a model. B's item 4 (a refusal when no model is set) is part of M; B does not touch these files.

Found at `c9a5c1c` (re-check with the grep below; the list may be incomplete):
- `geomind/runtime.py:15-16`: `FIXED_DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"` and `FIXED_CHEAP_MODEL = "anthropic/claude-haiku-5.5"`. Remove both. Every role's model comes from settings (`GEOMIND_MODEL`, `GEOMIND_CHEAP_MODEL`, per role if geomind has that). A live run with a role unset refuses to start and names the setting. Fake and scripted runs need no model.
- `geomind/context/compaction.py:11-13`: context window sizes for three Anthropic models only, so a DeepSeek model gets whatever the unknown-model path does. Read the context length from the provider (OpenRouter's model list gives `context_length`) or from an explicit setting. When neither gives it, return a clear error, not a guessed number. Check what the unknown-model path does today and say so.
- `geomind/providers/openrouter.py:14`: `CACHED_MODELS = ("anthropic/",)`. Caching is decided by an Anthropic prefix. Make it general: send cache markers only for providers that need them, and rely on automatic caching where the provider does it. Report the cached tokens per step either way. Check what OpenRouter documents for DeepSeek caching, and do not guess.
- Docs, tests, samples, evals and snapshots that name Anthropic models: `AGENTS.md`, `.claude/docs/providers.md`, `testing.md`, `tools.md` and `plan.md`, `schemas/samples/*.json`, `tests/unit/providers/test_openrouter.py`, `test_live.py`, `context/test_compaction.py`, and `conftest.py`. Recorded logs keep the model they really ran on, since that is history; samples and examples that show a model use DeepSeek.

Then:
1. `geomind check-live` lists every role with the model it would use, and fails if any role has none or if any model id starts with `anthropic/`.
2. Add a fast test that greps the package, `evals/`, `examples/` (if present) and `.claude/docs/` for `anthropic/`, `claude-`, `sonnet`, `haiku` and `opus` used as model ids. It allows only recorded run logs, the CHANGELOG history and git attribution lines.
3. Report every place changed, plus the grep output after the change.

## 6. Flaky tests (coordinator, after the merges)

Make the item 8 tests stable under xdist with no loss of coverage. Share a cached session fixture for the gemini example, use the short-window case, or move a test that truly needs the whole year to the slow tier. Never raise the 1 s budget.

## 7. Merge and finish (coordinator)

1. Merge order: first M (Sahand's hard rule) and D's crash fix (item 7b, as its own commit), pushed together as soon as they pass so the app can switch; then T, then the rest of D, then C (C may need D's prompt files), then B. Review every diff against the rules in 0b.
2. Run `make test-all`, `make lint` and every recording's replay.
3. Version: geomind `0.4.2`, unless a change breaks a public input. In that case use `0.5.0` and say why. Update `CHANGELOG.md`, the snapshots, the schemas, the contract map and `plan.md`.
4. Push `origin main`. Remove the worker worktrees and branches.

## 8. Done when

- Every reference argument has a pattern. Missing ranges, bad units and bad state changes get errors that say exactly what is valid, with gemini's values.
- The Designer starts from the project's plant when one exists.
- The context measurement is in the report, with the before and after numbers for both scripted runs.
- A run never ends above its cap, and every stopped run gives a partial answer.
- Code and docs agree on what runs in a worker thread.
- No Anthropic model id is left as a default or fallback anywhere; a live run with no model set refuses to start; the grep test guards it.
- The flaky tests pass under xdist.
- `make test-all`, `make lint` and every replay pass, and the new version is pushed.

## 9. Final report (at most 40 lines)

- The commits, with one line each.
- The tests (fast, slow, e2e, docker, replays) and the fast-tier time.
- The context table: the five largest items before and after, and the input tokens and steps of both scripted runs before and after.
- For the app thread: what changed for the backend (the budget estimate, the partial answer, `answer_reserve`, threads), and the exact steps to rerun its three live tests.
- Gemini requests, and anything still open.
