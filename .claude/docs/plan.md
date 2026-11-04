# Plan

This file is the roadmap. Update it in the same commit that finishes or changes a task.

Everything decided, built and still to do. A new session or a new team member reads this first, then
the other files of `.claude/docs/`. Where a fact has its own document, this file links to it. Where
this file and the code differ, the code wins: correct this file.

## 1. The goal and the inputs

The project is the SPE Europe Energy GeoHackathon Express, built on the GEMINI geothermal digital
twin.

- **Challenge 1 (50 %):** an agentic AI workflow. It analyses the problem, drives GEMINI, chooses and
  runs models, fills in missing models, compares alternatives and explains the configuration.
- **Challenge 2 (50 %):** an integrated deep-geothermal heating and cooling design. Report the
  capacities, the design and the agent log: prompts, answers and token usage.
- **Bonus:** multi-agent work, optimisation, uncertainty, techno-economics and automatic
  verification.
- **Deliverables:** a report of at most 5 pages or 10 slides, a video of at most 5 minutes, and
  everything committed and pushed to GitHub.

### Official inputs (released 2026-10-29)

The files are `GEMINI_Heating_Demand_Daily_2027.csv`, `GEMINI_Cooling_Demand_Daily_2027.csv` and
`GEMINI_Hackathon_Challenge_Requirements.pdf`. gemini ships both CSV files as package data and
ships them in its example cases (`hackathon_2026` and others), so an agent reads the demand through
the tools of the state's case and never through a path.

| Item | Value |
|---|---|
| Heating demand | 365 daily values; peak 30.0 MWth (28 Jan), minimum 2.67, 111.7 GWh per year |
| Cooling demand | peak 10.0 MW (19 Jul), 23.7 GWh per year, above 0 on 219 days; heating + cooling ≤ 30 on any day |
| Reservoir | mid depth 2500 m TVD, 100 m thick, gradient 30 °C/km, surface 12 °C (so 87 °C at 2500 m), 250 barg, 200 mD; the depth may be chosen |
| Brine | 1030 kg/m³ and 0.40 mPa·s; gas-liquid ratio 0.8 Nm³/m³; gas is 80 % CH₄ and 20 % CO₂ |
| Hard limits | 1 to 3 doublets; 50 to 300 m³/h per doublet while active; brine cooling ≤ 40 K; pump efficiency 70 %; production volume = injection volume; 330 operating days |
| Supply temperatures | 100 °C for heating, 20 °C for cooling (return temperatures are not given) |

What this implies: 87 °C is below the 100 °C supply, so the design needs a heat pump, a gas boiler
burning the co-produced gas, or deeper wells (about 3000 m gives about 102 °C). One doublet gives at
most about 14 MW at 40 K, so the peak needs 2 to 3 doublets or top-up heat.

## 2. Repositories

The local workspace `crust-team/` holds `gemini/`, `geomind/`, `backend/`, `frontend/`,
`infrastructure/` and `docs/`.

```text
frontend (React + Vite) -> backend (FastAPI, Celery) -> geomind (agents) -> gemini (physics)
```

- **gemini** (`import gemini as gm`) is the physics library and engine: modules, plants, units,
  simulation, results, economics and checks. It is the only place where physics and numbers live.
  It is developed in its own repository and installed from its release wheel.
- **geomind** (`import geomind as gd`, `git@github.com:crust-team/geomind.git`) is this repository.
  **geomind computes no physics.** Every number comes from a gemini tool.
- **backend** stores chats, runs, events and plants, queues runs on Celery and streams events by SSE.
  It implements geomind's `RunStore` and `Workspace` and never chooses agents or loops.
- **docs/** holds the shared documents. `contracts.md` is the one every repository follows; its
  geomind part is mapped in [contracts.md](contracts.md).
- The product and the infrastructure have their own name, in the shared
  [contracts](../../tests/fixtures/contracts/shared.md) section 3. The only Python packages are the ones above.

## 3. Design decisions

Each decision is settled; change one only with Sahand. The layers are prompt ⊂ context ⊂ harness ⊂
loop: the prompt is one agent's instructions, the context everything sent in one LLM call, the
harness the engine, tools, permissions, hooks and log, and a loop decides which run comes
next and when the goal is met. geomind copies gemini's structure on purpose, so one mental model
covers both: see [the gemini parallels](../../AGENTS.md#the-gemini-parallels).

| # | Decision | Why | Detail |
|---|---|---|---|
| 1 | The event log is the only source of truth, with no checkpoints; resume, crash recovery and replay are one mechanism | Three mechanisms would drift apart; any process can continue a run | [engine.md](engine.md#recovery-and-resume) |
| 2 | The core is async and the facade is sync | Parallel tool calls and delegates need it, and changing it later would touch every layer | [conventions.md](conventions.md#departures-from-gemini) |
| 3 | LLM calls and tool calls are the only side effects | Everything else is deterministic over the log, so a durable executor could wrap them later | [engine.md](engine.md#harness-principles) |
| 4 | Context is explicit: a tool whose first parameter is `context` gets the run; `runtime.py` holds settings only | No hidden active-run variable | [tools.md](tools.md#dispatch) |
| 5 | Hooks and permissions are separate; every tool declares an effect; every decision is a `permission` event | Hooks are code, rules are data, and both must be auditable | [hooks.md](hooks.md), [permissions.md](permissions.md) |
| 6 | No code runs in geomind: no code tools and no sandbox (removed in 0.4.22); a model gemini lacks makes a family `blocked` | The agents engineer with gemini's modules; written code was never usable in a plant run | [tools.md](tools.md#no-code-tools) |
| 7 | Few generic tools, not one per gemini module; errors are results | About 45 modules as 45 tools is the bloated-tool-set failure; a model can fix its call from a result | [tools.md](tools.md) |
| 8 | The problem state lives outside the messages, is written only through `update_state`, and is rendered last | The cached prefix stays stable and compaction never touches it | [context.md](context.md#problem-state) |
| 9 | Past 60 % of the model window, older turns become one summary; skills load on demand | The context stays small, and a chat compacts once | [context.md](context.md#long-conversations) |
| 10 | An agent's constructor declares `# Agents`, `# Prompt`, `# Tools`, `# Output`, `# Model`; there is no `Team` class | The order of agents is a policy, and policies are loops. An agent says which model, the run which provider | [agents.md](agents.md) |
| 11 | `run.py` holds the tables `LOOPS` and `AGENTS`; later the `Coordinator` returns a typed `Route`. **The backend never chooses the loop or the agent.** `gd.Run(agent=...)` exists only for manual testing | Routing is one cheap, logged LLM call, and a new agent is one table row | [agents.md](agents.md#shipped-agents) |
| 12 | Public events go to the browser, internal ones stay in the log; `text.delta` is never stored; nested runs share the root log | One stream, one log | [events.md](events.md) |
| 13 | geomind uses only gemini's public API, `import gemini as gm`, and never an internal path | gemini's internals change; `gemini/.claude/docs/api.md` is the reference for every gemini tool | [conventions.md](conventions.md#dependencies) |

## 4. gemini's conventions that geomind's tools follow

These were agreed in the gemini threads on 2026-10-30. `gemini/.claude/docs/api.md` is the reference;
check it before writing a tool, because gemini's names change.

- **Versioning.** `gm.__version__`, semver below 1.0: a breaking change raises the minor version.
  Adding or removing modules in the catalogue is not an API change.
- **Three return shapes only:**
  - **Value** `{value, unit}`, where `value` is a number, an array or `null` (with a `reason` when it
    is `null`). A series adds `time`, and statistics are `{min, max, mean}`, each a Value.
  - **Problem** `{path, code, message, suggestions}`, for every error and validation result. `path`
    may be `null`.
  - **Check** `{name, passed, value, limit}`.
- **Errors.** `on_error="raise" | "record"`, `raise` by default. Seven classes: `GeminiError`,
  `ValidationError`, `DefinitionError`, `PhysicsError`, `RunError`, `Cancelled` and
  `NotImplementedYet`. The detail is in `code`.
- **Running.** `gm.simulate`, `gm.replay` and `gm.live(plant, ...)` are thin functions over
  `gm.Engine`, which stays public. `gm.evaluate` runs one module.
- **Plants.** `gm.Plant.from_dict`, `plant.to_dict`, `plant.check()`, `gm.check(plant, case)`,
  `plant.set_range` and `plant.set_options`. Well-known plants are registered `gm.Plant` subclasses;
  the backup policy is `params.backup` of the plant.
- **Wiring.** Every port is named `<role>_in` or `<role>_out`, and no port may be left unconnected.
  Everything in the energy flow is a module. Grids (`ElectricityGrid`, `GasGrid`, `HeatingGrid`,
  `CoolingGrid`, `WasteGrid`, `ChemicalGrid`) and `Atmosphere` are the plant's boundaries, and plant
  totals come from the boundary ports.
- **The case.** `gm.Case` is a project folder: `case.json` (time, environment, demand,
  requirements, uncertainty), `economics.json` and the data files they name. `gm.simulate(plant,
  case)` runs it, `gm.evaluate.verdict` judges it (`feasible`, `reasons`), `gm.evaluate` also gives
  the report, totals and costs, `gm.Study` and `gm.study` size, optimise, sample and compare, and
  `gm.modules.check` tests a module.

## 5. What is built

| Phase | What | Commits | State |
|---|---|---|---|
| S1 | Engine, run facade, events, stores, providers (`OpenRouter`, `FakeLLM`), hooks, permissions, sandbox, CLI, replay | `faa2990`…`94d0f57` | done |
| S1b | Rename to geomind, top-level packages, contract alignment | `079b04a`, `f1b320a`, `a9ec1cf` | done |
| S1c | Simplification: explicit context, no checkpoints, stores out of the engine, delegation in one place | `6b4ee23`…`9dccd85` | done |
| S2 | `step.finished.text`; `text.delta` not stored | `51a8f9b` | done |
| S2 | `ProblemState` and `update_state` | `ad60954` | done |
| S2 | Compaction and skills; the 50-turn test compacts once and still answers turn 3 | `b0ec535` | done |
| S2 | `read_result`, `rag_search` | `aa4b01e` | done |
| S2 | `AnalysisLead` (complete sample, the default agent without a sandbox), `Summarizer`; skeletons of `Coordinator`, `DesignLead`, `Reviewer`, `Economist`, `Explainer`, each with a six-heading prompt file | `ad01b96` | done |
| S2 | `geomind chat` and the eval runner | `55296c1` | done |
| S2b | `FileWorkspace.plant` through `gm.plants.from_dict` | `957c119` | done |
| Freeze | Every interface below, pinned by snapshots; the tool catalogue and the loops as stubs; see [CHANGELOG.md](../../docs/CHANGELOG.md) | `fab5524`, `09096d8` | done |
| S2b.1 | `list_modules`, `describe_module`, `evaluate_module` over `gm.modules` and `gm.evaluate` | `599a660` | done |
| S2b.2 | `list_plants`, `read_plant`, `build_plant` over `gm.plants`; a plant file builds with `Plant.from_dict` and is stored with its issues | `2d3efa1` | done |
| S2b.3 | `list_profiles`, `read_profile`, `simulate` (`gm.schedule` and `gm.simulate`, failed days recorded) | `f4732aa` | done |
| S2b.4 | the `AnalysisLead` with the gemini tools, its prompt, and the `gemini-units` skill checked against `gm.units.names()` | `05dd940` | done |
| S2b.5 | five analysis lead eval tasks on the example doublet, passing offline; recordings written by hand until S2b.6 | `40a8d72` | done |
| S2b.6 | one live run, recorded, with its token cost | none | **open**: needs `OPENROUTER_API_KEY` and a cap; `geomind check-live` checks the models first |
| S3.1 | `gd.verify.verify`, `check_results`, `compute_kpis`: gemini's report on the run's case, with failure domains | `7afb1d0` | done |
| S3.2 | the `Verified` hook: gemini's checks run again on the design's stored run before any answer | `8ee1444` | done |
| S3.3 | `estimate_costs`: gemini's economics with the assumptions used, and LCTS | `cf07cdc` | done |
| S3.4 | `DesignLead`, `Reviewer`, `Economist`, `Explainer`, `Coordinator` filled, with the `designing-a-plant` skill and one offline task each (hand-written recordings); `read_plant` reads examples and templates (`253bf05`); co-produced gas check (`e7719f4`) | `ef7c64b` | done |
| S3.5 | `DesignLoop`: a rule-based driver delegates design, verification, costs and explanation in one root run, routes failures by domain, and replays offline (nested state changes and artifacts reused) | `4fc16ed` | done |
| S3.7 | Routing: `Run.start` asks the `Coordinator` (a nested run logged first) and follows its `Route`; `geomind run --loop/--project/--recording/--record` | `27f3161` | done |
| S3 e2e | the official case through `geomind run --loop design`, offline from a scripted recording, replays | `b1c9cd3` | done; the live run waits for `OPENROUTER_API_KEY` |
| S4.5 | `geomind show --format md`: tokens by agent, by step and in total, each prompt once, full answers | `1ac2af1` | done |
| Manifest | `run_manifest.json` beside each `geomind run`: commits, versions, input hashes, models per agent, settings, seeds | `0af2695` | done |
| Replay | parallel calls matched by their place in the step; nested state changes by the call that started them | `55632cc` | done |
| Usage | `RunResult.usage` counts every nested run, the routing call included, after a resume too | `4971938` | done |
| Case | the problem as data: a `gm.Case` in the problem state (`set_case`, `read_case`), its files stored as `case/<file name>`; `save_profile` adds a user's demand to the case; the design loop asks the user when there is no case or no demand | `7e74274`, `164eb62`, adaptation | done |
| Skill | `designing-a-plant` general for any case, with no challenge number in the package; DesignLead and Explainer prompts without the hand-found answer | `fb93b32` | done |
| Evals | `challenge2`: the hackathon case and three variants through the design loop, offline; the `verified` criterion | `6cf623c` | done |
| Caching | OpenRouter prompt caching on the system prompt of Anthropic models; `Usage.cached_tokens` | `7286e6d` | done |
| Spending cap | `geomind run --max-tokens/--max-cost`; budgets count the whole run, nested runs included | `65c576a` | done |
| Terminal | `geomind run` no longer prints the coordinator's route JSON; plan corrections from the audit | this commit | done |
| gemini 0.5 | geomind 0.3.0 on gemini `>=0.5,<0.6`: project folder case with `economics.json`, verdict, ranges and `run_study`, `Workspace.plants`, chat-scoped artifacts, `write_module`/`test_module` in the gemini sandbox, `CompareLoop`, the competition export, `check-live`, the loop report ([CHANGELOG.md](../../docs/CHANGELOG.md)) | merged sections A to P | done |
| Log and replay | geomind 0.3.1: `run.started` records the geomind, gemini and python versions and the export reads them; the export header shows the run's own request; a replay runs every nested run again with its own completions and compares every run | merged sections V and R | done |
| Studies, budget, replays | geomind 0.4.0: every study tool stores `study/<name>` (gemini's study and result form) and emits `study.recorded`; `list_studies`, `read_study`; `ProjectBudget` with `UsageLedger`; replay matches results by step and call id, and a log of another geomind version checks decisions, not tool outputs; every eval recording replays in a test | merged sections P, S and B | done |
| Released on the wheel | geomind 0.4.2 on the gemini 0.5.5 release wheel: shorter context, DesignLead asks for a missing range, no model id in the package, tests read a copy of gemini's examples; `README.md` and `docs/` for people | `v0.4.2` | done |
| Real comparison | geomind 0.4.6: `CompareLoop` designs each family in its own nested run, side by side up to `compare_concurrency`, verifies each, compares and explains; `StudyCompareLoop` keeps the old form | `v0.4.6` | done |

No live OpenRouter run has been made yet. It needs `OPENROUTER_API_KEY` in geomind's own
environment, never the backend's key.

## 6. Frozen interfaces

Sahand's rule: **the interfaces are fixed now, so the backend never breaks later.** What is frozen,
where it is pinned and the rule for changing it are in
[api.md](api.md#frozen-interfaces). The tools are in [tools.md](tools.md#catalogue), and the
contract map in [contracts.md](contracts.md).

## 7. Remaining work

The tasks are in order. Each one replaces a stub whose name, schema and effect are frozen: fill the
body, and remove its `stub` status in the table of [tools.md](tools.md#catalogue). A task that needs
a different signature follows the [change rule](api.md#frozen-interfaces). Task tests go in the
mirrored `tests/unit/...` file that already exists for the stub.

### Task list (updated 2026-11-03, live loop)

Done on `dev` (0.4.22.dev23), each with tests; 41 bugs of the live loop found and fixed:

- [x] CaseLead: one agent sets the case, from the chat and any files; the project's
  `case.json` is loaded by rule; values no file gives are confirmed by the user in one question
  with their source or reason and kept as assumptions with a citation.
- [x] The DesignLead reads the case and never sets it; a case it lacks goes back as
  `case change needed: <path>: <why>`.
- [x] Key trees from gemini's public schemas in the system prompts: case and economics
  (CaseLead), plant file and study (DesignLead), study (Economist); compact `describe_module`.
- [x] Shared memory: `knowledge` (cited values; gemini's cost catalogue copied into
  `data/knowledge/`, now a document of the knowledge base since 0.4.22.dev35) and `experience` (verified designs,
  written by the loop in code, recalled only above `memory_similarity`).
- [x] Step limit asks to continue; `geomind resume`; replay then live (`--replay`).
- [x] Required settings with no default: `GEOMIND_MAX_STEPS`, `GEOMIND_MAX_OUTPUT_TOKENS`,
  `GEOMIND_MEMORY` (with its folder and similarity), `GEOMIND_CASELEAD_MODEL`, the retries.
- [x] `patch_plant`: a plant built in small checked steps, one module's values at a time.

Open, in order (the team layout agreed with Sahand on 2026-11-03, started on his word at 16:11):

1. [ ] The engineering team ([agents.md](agents.md#shipped-agents)), each step its own commit:
   - [x] 1. Renames, removals and the team layout (now `agents/<team>/<name>.py` and
     `prompts/<team>/<name>.md`)
     (`Formulator` to `CaseLead`, `Designer` to `DesignLead`, `Verifier` to `Reviewer`, `Analyst`
     to `AnalysisLead`; `Assistant`, `CodeAssistant`, `FamilyDesigner`, the code tools and the
     sandbox removed; one required `GEOMIND_<ROLE>_MODEL` per agent; knowledge-only memory for the
     Reviewer and the Explainer).
   - [x] 2. `Geoscientist` in `case/`.
   - [x] 3. The design team (`process`, `integration`, `reservoir`, `well`, `energy`) with parallel
     `patch_plant`.
   - [x] 4. `ProjectLead`, `SupportLead`, `Curator`.
   - [ ] 5. Each agent tested alone on a fixed input from earlier runs, then end to end.
2. [ ] A live run to a verified, costed and explained design, with replay from each failure.
3. [ ] One full run from the start, the memory off, then the full suite, the release (an
   annotated tag) and the version for the backend.
4. [x] MCP for every agent (`gd.mcp`, `<server>__<tool>`, 0.4.22.dev37) and the knowledge base (0.4.22.dev35): contract v2 and v3.
5. [ ] gemini needs for Sahand to approve: `gm.Plant.from_dict` raises `KeyError('')` instead of
   `ValidationError` for an inlet given as a bare value such as `{"flue_out": "gas"}`.

### Live runs of the agent team and their bugs

DeepSeek only (`deepseek/deepseek-v4.1-flash-1017`), every live run capped; the live loop's total
cap is 5 USD (1.66 USD spent before the team).

| Run | What | Cost (USD) | Total (USD) | Outcome |
|---|---|---|---|---|
| A1 | each of the 15 agents alone, in parallel, on a fixed input from the earlier runs (`setup`), 0.10 cap each | 0.43 | 2.09 | 15 of 15 passed their criteria; bugs #42 to #50 |
| E1 | end to end from the coordinator, memory off, 1 USD cap, three answers by the test operator | 1.00 | 3.38 | stopped at its cap before a verified design: two families planned, process, integration and reservoir engineers done; bugs #53 to #55 |
| C1 | the case lead and the geoscientist alone, six tasks (files, chat, one change, a question, a flawed case, the geoscientist on the brief) | 0.06 | 3.69 | 6 of 6 passed; every flaw caught and asked; no invented value; bugs #61 to #63 |
| C2 | the case team alone again, after #61 to #63 | 0.08 | 3.77 | 6 of 6 passed; one self-computed dew point (#64) |
| TA1 | Track A after dev43 (compact tree, run-long pages, columns), six tasks | 0.16 | 4.20 | 4 of 6; from_files at its cap; cache cold after the prompt change, 10 `read_stored` left |
| TA2 | Track A after dev44, provider pinned to DeepSeek (`GEOMIND_PROVIDER=deepseek`) | 0.035 | 4.24 | 4 of 6 by the criteria; from_files 39 → 15 model calls and 0.069 → 0.011 USD, but stopped on #65; total 0.112 → 0.035 USD |
| A2 | the 6 agents the fixes touched, alone again | 0.29 | 2.38 | 5 passed; the case lead now asks for the values with no source (#44 working), so its task's fixed answer must change |
| D1 | the design team alone: process, integration, reservoir, well and energy engineers and the design lead, one task each on the C1 case, 0.08 cap each | 0.38 | — | 1 of 6 passed (integration); four engineers stopped at their cap; bugs #70 to #72 |
| D2 | the same six after #70 to #72, 0.065 cap each | 0.26 | — | the lead's verdict and records right at a third of D1's cost; the engineers still at their cap; bugs #73 and #74 |
| D3 | the process and well engineers after #73 and #74, 0.06 cap each | 0.09 | — | the well engineer's failed module calls fell from 8 to 1 and it patched; the process engineer's run still ended on two garbled calls (#75) |

Bugs found by the team's runs (the earlier 41 are in [CHANGELOG.md](../../docs/CHANGELOG.md)):

| # | Found in | Bug | Fix | Commit |
|---|---|---|---|---|
| 42 | A1, every agent | memory tools offered while the memory is off; refused calls again and again | not offered, nor their prompt sections | `768f396` |
| 43 | A1, case lead | computed the reservoir temperature from the gradient itself | computes nothing; a derived value stays unset for gemini | `768f396` |
| 44 | A1, case lead | proposed capex unit costs with no source | knowledge with its source, else a question; no number of its own | `768f396` |
| 45 | A1, reservoir engineer | computed a productivity index by Darcy's law by hand | engineers and the design lead compute nothing; top-level values first | `768f396` |
| 46 | A1, energy systems engineer | ended with an empty answer, accepted as done | an empty text is no answer | `768f396` |
| 47 | A1, engineers | `evaluate_module` inlets sent in a wrong form | the description shows a whole inlet with gemini's fluid fields | `768f396` |
| 48 | A1, explainer | a reference in quotes refused | read as the reference | `768f396` |
| 49 | A1, explainer | a made-up reference asked for six times with another `path` each | the same bad value counts as the same failure | `768f396` |
| 51 | A2, well engineer | a name stored with other content refused with no way on; its last steps lost | the refusal suggests a free name | this commit |
| 53 | E1, project lead | asked again about a value approved through the case lead | a confirmed change is accepted | this commit |
| 54 | E1, design lead | made up a grid gas composition and put the case value under plant paths | handed over at once, never into the plant | this commit |
| 55 | E1, design lead | the three side-by-side engineers called one by one | `fill_parts` runs them at the same time in code | this commit |
| 56 | E1, all engineers | owners written as `params.<path>`; every engineer's patch refused (61 times) | a prefix with or without `params.` is found | this commit |
| 57 | E1, design lead | `"format": "1"` refused four times as an old header | read as its number | this commit |
| 58 | E2, case lead | read a year ending at an exclusive 31 Dec as 364 values and proposed to cut a day | knows `time.end` is exclusive | this commit |
| 59 | E2, case lead | asked for a typed path and value with options, three times | `ask_user` says a typed answer needs no options | this commit |
| 60 | E2, case lead | `read_profile` showed the clipped series as the file | shows the case window and the file's own rows | this commit |
| 61 | C1, case lead | the data files `case.json` names were no project files | listed and read beside `files/` | this commit |
| 62 | C1, case lead | reported a value before a change it never read | reads before and after | this commit |
| 63 | C1, evals | an eval workspace had no knowledge base | the settings' knowledge base | this commit |
| 64 | C2, case lead | worked out a room dew point (14.6 degC) inside a question; with the new `sourced` criterion also a temperature from the gradient, a GWP from memory, an end date and a step count | prompt forbids any number it worked out or knows from memory; `read_rag`'s table gives the case span; eval criterion `sourced` | de37595 |
| 65 | Track A, case lead | told `changes=<the same changes>` after a missing file, sent the files alone three times and the run stopped | the retry names everything to send again; files alone on no case say they go with the changes | dev45 |
| 66 | Track A, case lead | a gradient in `degC/km` got `{'unit': 'degC'}` and the units of temperature as its fix | the quantity of a two-word unit message (`temperature gradient`) is read whole | dev45 |
| 85 | C1 (Track C), economist | told to cost a design, it sampled 200 draws and a sensitivity with a seed it chose (192 s) | uncertainty and sensitivity only when the task asks for them | track-c |
| 86 | C1 (Track C), evals | the `sourced` criterion left out the problem state's `Case:` line, so the case's own years counted as made up | the state's `Case:` line is read; the agent's notes and questions stay out | track-c |
| 87 | C2 (Track C), economist and analysis lead on nemotron | sent `update_state`'s `changes` as a JSON string; two refusals in a row stopped the economist's nested run, and the lead finished without it | `Tool.validate` reads a list or an object given as its JSON text (model-agnostic) | track-c |
| 88 | C2 (Track C), analysis lead on DeepSeek | asked `compute_kpis` for `annualised_cost`, a cost metric it lacks, because the reference listed the metrics under `compute_kpis` too | the reference says `compute_kpis` has names of its own: call it without `names`; costs come from `estimate_costs` | track-c |
| 70 | D1, process engineer | DeepSeek leaked tool-call markup into an argument (`">HeatingCoolingPlant</</parameter name=`) and sent it again three times | an input holding markup is refused before the tool runs, with the value before the markup as the suggestion | track-b |
| 71 | D1, design engineers | each engineer read the case 4 to 16 times and its profiles again and again: a long result shrinks to an outline after one step | the engineers keep the case, the plant and the module descriptions whole for a few turns (`Tool.kept()`); `read_profile` gives a `summary` (peak, minimum, mean, energy) computed by code | track-b |
| 72 | D1, design lead | checked a design handed to it complete, then recorded it only as a note, not as `design.reference` and `design.result` | the prompt says a checked handed design is final too | track-b |
| 73 | D2, process engineer | parallel `read_plant` calls came back with every argument null until the run stopped on repeated failures | it compares plants with `list_plants` and reads only the one it chooses, in one call | track-b |
| 74 | D2, well engineer | 8 failed `evaluate_module` calls on a well path's section lists: gemini's `describe()` gives them as `number`, and its error asks for a Quantity for a list and for a list for a Quantity | the well engineer's prompt gives the form `{"value": [..], "unit": "m"}`; gemini request 14 | track-b |
| 75 | D3, process engineer | two garbled calls in a row (`">site</</parameter_name...`) counted as invalid calls and ended the run as failed; `">HackathonPlant</` was not caught | a markup slip is an error but no validation failure; a lone `</` or a leading `">` counts as markup; prose tools (`finish`, `ask_user`, `update_state`, `write_lesson`) are not checked | track-b |
| 50 | A1, all | models saw only the first paragraph of each tool's docstring | the whole docstring but its `NOTE:` paragraphs | `768f396` |

### The adaptation to gemini 0.5 (done) and what is open

geomind 0.3.0 runs on gemini 0.5: the case is a project folder (`set_case`, `read_case`,
`save_profile`; [context.md](context.md#the-case)); a plant is a file built with `build_plant`,
ranged with `set_ranges` and searched with `optimize` or `run_study`; pass or fail is
`gm.evaluate.verdict`; artifacts live in the chat; modules the model writes are tested in the
gemini sandbox; `CompareLoop` ranks plant families. The full list of changes is in
[CHANGELOG.md](../../docs/CHANGELOG.md).

Open geomind items:

- **The live run.** It needs `OPENROUTER_API_KEY` in geomind's environment and a spending cap
  (`--max-tokens`, `--max-cost`); run `geomind check-live` first. Unknown role model ids fall back
  to the default model.
- **Replay of a run with a project, without `--project`** reuses its nested runs (their answer
  and state changes), as the log holds no workspace; with the folder every nested run runs again.
- **Versions of a 0.3.0 log are not in the event log**; the export reads them from
  `run_manifest.json` (runs from 0.3.1 record them on `run.started`).
- **A log of another geomind version** replays with recorded tool results (pure tools are not run
  again), so it checks the agents' decisions, not the tools' outputs.
- **`ProjectBudget`** reads the ledger once per run: runs of one project running at the same time
  are not counted against each other.

Open requests to gemini (full text in the adaptation notes):

1. `units="display"` on `Results.get` and `Results.summary` (geomind keeps a small `READ_UNITS`
   map), with pressure and mass flow in the display table.
2. `Comparison.to_dict(units="display")` (`compare` reads each report's display values instead).
3. `capabilities()["ranges"]` is incomplete (example plant files range leaves it does not name),
   and `set_range` accepts any numeric leaf; make the list complete or refuse leaves not meant to
   be searched.
4. The parts of a value (capex modules, opex components) in display money units.
5. A `job` argument on `gm.case.missing`, so it can list what one job needs (it exists without one
   and gives `case_incomplete` its paths).
6. `gm.evaluate` copies the plant and applies the case for each metric (about ten times per
   report), most of a tool call's time.
7. A size-only study method (`size_plant` stores its study as method `run` with `prepare: ["size"]`).
8. A public `to_dict()` for the result of `gm.study.minimize`, history included (`optimize` stores
   the best without its plant and drops the history).
9. `Plant.to_dict()` carrying `sizing` with quantities (geomind converts the sizing notes itself).
10. Time units `day` and `hour`: `gm.units` accepts only `d` and `h`, so a `save_profile` step of
    `day` is refused (geomind adds the accepted units to the error).
11. The plant check of a class plant (`HeatingHeatPumpCoolingPlant` built from its header) lists
    inner doublet values as missing (`d0.reservoir.permeability`, `aquifer_thickness`, `top_depth`,
    `skin`, `wellbore_radius`, the same under `d0.sink`) after the doublet's top-level values are
    set and checked against a case that gives them, while the complete `HackathonPlant` needs none
    of them; the engineers then copy case values into the plant by hand (found in run A2).
12. `Case.schema()` does not say that `time.end` is exclusive (a year of daily values ends on the
    next year's first day); the case lead read a year ending on 31 Dec as 364 steps and proposed
    to drop a day of data (found in run E2).
13. A way to validate a whole case at once: `Case.from_dict` raises the first wrong value only
    (`gm.case.missing` lists every missing path, but not wrong units or values), so a case lead
    that sets the case in one call learns its errors one call at a time (Track A).
14. `describe()` gives a list parameter of quantities (`ProductionWell.section_length`,
    `section_diameter`, ...: one value per section) as `type: number` with a unit, and
    `gemini/units/bare.py`'s error for a list of quantities asks for a Quantity, for a Quantity
    asks for a list; the form that works, `{"value": [500, 2000], "unit": "m"}`, is said nowhere.
    Asked: `type: array` with the item's quantity and unit in `describe()`, and that form in the
    error (found in run D2, bug #74).
15. `site.fluid.dissolved_gas.*` take a bare `{value}` (a mole fraction) with no unit, while
    briefs give `mol%`: the agents must turn 20 mol% into 0.2 by hand, which their rules forbid.
    A `unit` (`mol%`, `-`) on those fields, converted by gemini (Track A).

### S2b: gemini tools (the first job; the text below is the original plan)

Return gemini's three shapes unchanged, and let gemini's errors through to dispatch, which turns them
into results. Use only `import gemini as gm`, inside the function, so `import geomind` stays free of
gemini.

1. **Module tools.** Done. Replaced the stubs `list_modules`, `describe_module` and `evaluate_module` in
   `geomind/tools/gemini/catalogue.py`.
   - Tests: `tests/unit/tools/gemini/test_catalogue.py`, against real gemini modules.
   - Done when: the three tools return gemini's shapes, and an unknown name is a result with
     `unknown_name` and suggestions.
2. **Plant tools.** Done. Replaced the stubs `list_plants`, `read_plant` and `build_plant` in
   `geomind/tools/gemini/plants.py`.
   - Tests: `tests/unit/tools/gemini/test_plants.py`.
   - Done when: `read_plant()` describes `Workspace.plant`, a plant that fails
     `build_plant` of a bad file returns gemini's error and stores nothing, and a
     valid one is read back through its `design/<name>` reference.
3. **Profiles and simulation.** Done. The numbers are checked on `HackathonPlant`, because
   gemini's example doublet fails every day of the demand year (`out_of_range`); its failures are
   checked instead. Replaced the stubs `list_profiles`, `read_profile` and `simulate` in
   `geomind/tools/gemini/runs.py`.
   - `simulate` stores the [result format](tools.md#references) under `result/<id>`, and beside it
     what the S3 tools need: `Results.to_bytes()` and the plant. The keys of those two are free.
   - `read_result` in `geomind/tools/gemini/results.py` is already built and reads that format.
   - Tests: `tests/unit/tools/gemini/test_runs.py`, on the example doublet.
   - Done when: a `simulate` of `HackathonPlant` stores a result that `read_result` reads, with the
     numbers equal to gemini's own run (`test_simulate_stores_what_read_result_reads_with_gemini_s_numbers`);
     the example doublet's failed days are gemini's problems in the summary.
4. **The AnalysisLead.** Done. Added the tools to `geomind/agents/analysis/analysis lead.py` and its prompt, and update
   the `gemini-units` skill to the units gemini accepts.
   - Tests: `tests/unit/agents/analysis/test_analyst.py`.
   - Done when: `test_its_prompt_names_only_tools_it_has` passes with the new tools.
5. **First eval tasks.** Done; the recordings are hand-written until S2b.6. On the example doublet, in `evals/tasks/analysis lead/`: the operating point, heat
   delivered at 150 m³/h, a missing parameter that needs `ask_user`, a module lookup, and the ESP at
   another frequency.
   - Done when: `python -m evals.run --agent analysis lead` passes offline from recordings.
6. **One live run.** `geomind chat --agent analysis lead --live`, recorded, with the token cost reported.

### S3: design agents and verified loops (Challenge 2)

1. **Verification.** Done; see [tools.md](tools.md#verification). Replaced the stub `gd.verify.verify` in `geomind/verify/verify.py` and the stubs
   `check_results`, `compute_kpis` in `geomind/tools/gemini/assessment.py`.
   - The checks are gemini's and never an LLM: energy and mass balances, demand coverage per day,
     bounds and the constraints of the case. Units are checked by gemini when a value is set or
     bound.
   - Tests: `tests/unit/verify/test_verify.py`, `tests/unit/tools/gemini/test_assessment.py`.
   - Done when: a design that breaks a constraint of the case fails with a check that names it.
2. **The `Verified` hook.** Done. Replaced the stub in `geomind/engine/hooks.py`.
   - Tests: `tests/unit/engine/test_hooks.py`.
   - Done when: `before_finish` refuses to finish while the last verification failed, so **no design
     reaches the user without passing every reviewer**.
3. **Costs.** Done; see [tools.md](tools.md#costs). Replaced the stub `estimate_costs` in `geomind/tools/gemini/assessment.py`.
   - Done when: capex, opex, LCOH, LCOC, LCTS, NPV, payback and CO₂ come back as Values from the case's assumptions.
4. **Fill the skeleton agents.** Done. of [agents.md](agents.md#shipped-agents): prompts, tools and eval
   tasks. `DesignLead` proposes configurations and sizes, `Reviewer` runs the checks and reviews,
   `Economist` gives the costs, `Explainer` writes the explanation, and `Coordinator` routes.
   - Done when: each agent's status in the table is complete, with its tasks passing offline.
5. **`DesignLoop`.** Done. Replaced the stub in `geomind/loops/design.py`: propose, simulate, verify, write
   the failures to the problem state, and repeat until everything passes, the budget runs out, the
   round limit is reached, the same check fails repeatedly, or a question goes to the user. Every
   stop reason is explicit and logged.
   - Tests: `tests/unit/loops/test_design.py`.
   - Done when: `geomind run --loop design <request>` returns a verified design with capacities, a
     description of the schematic, the numbers and an explanation, for the official case
     (`tests/e2e/test_official_brief.py`, offline; the live run waits for the key).
6. **`MakerCheckerLoop`.** Removed: the design loop already has a maker (DesignLead) and a checker
   (Reviewer), and `CompareLoop` is built on it.
7. **Routing.** Done. `Run.astart` calls the `Coordinator` and follows its `Route` with `loop_of` in
   `geomind/run.py`. A stub loop already gives `stop_reason="not_implemented"`.
   - Tests: `tests/unit/test_run.py`.
   - Done when: the backend starts a design run without naming a loop or an agent.
8. **Agent-written modules (Challenge 1).** Built, then removed in 0.4.22 with the code sandbox:
   no code runs in geomind.
   Open: a plant run with the module (see the open items above).

### S4: compare, uncertainty, evals and export

1. **`CompareLoop`.** Done, and rebuilt in 0.4.6: see [engine.md](engine.md). `Route.loop` can be
   `compare`.
2. **Optimisation (bonus).** Done: `optimize` and `run_study` over `gm.Study` in
   `geomind/tools/gemini/study.py`.
3. **Uncertainty (bonus).** Done: `sample_uncertainty`, `sensitivity` and `compare` in `study.py`,
   with the distributions of the case's `uncertainty`.
4. **Evals.** Done: `evals/tasks/` holds the `challenge2`, `compare`, analysis lead, design lead, reviewer and
   economist tasks, passing offline, and `python -m evals.run --report` writes
   `evals/reports/summary.md` ([evals.md](evals.md#suites)).
5. **Export.** Done. `geomind show <run> --format md` writes the competition export: every LLM call
   with its messages, each agent's prompt once, and the token tables.

### S5: connectors (MCP) for every agent (planned, after the memory)

- A generic MCP client in geomind: every agent can use the tools of the MCP servers a run is
  given, to gather information. The servers come from a required setting
  (`GEOMIND_MCP_SERVERS`, no default); a backend gives the ones a user added in the frontend
  through the workspace contract. geomind builds no backend or frontend part.
- A server's tools are named with the server's name in front (`<server>.<tool>`), so they never
  clash with geomind's tools.
- A value from an MCP tool is handled like a knowledge entry: shown with its origin (server, tool,
  time) in the CaseLead's confirmation question and set in the case only after the user
  confirms it, recorded as an assumption with that citation.

## 8. How to work in this repository

- **Read first:** `AGENTS.md` and every file in `.claude/docs/`.
- **Branch, tests and quality:** see [AGENTS.md](../../docs/rules.md#branches-and-worktrees),
  [testing.md](testing.md) and [conventions.md](conventions.md#code-quality).
- **Docs:** a commit that changes behaviour updates `AGENTS.md` or `.claude/docs/` in the same commit.
- **Temporary files** go to `.tmp/`.
- **Subagents** use lighter models.
- **Stop and say so** when something is missing or risky. Never guess a gemini name.
- **Never change** `gemini/`, `backend/`, `frontend/`, `infrastructure/` or `docs/contracts.md` from
  this repository. Report what they need to Sahand.
- **Credentials** never go into prompts, events, logs or memory.
- **Testing an agent:** by hand with `geomind chat` ([api.md](api.md#command-line)), by tasks with
  `python -m evals.run` ([evals.md](evals.md)).
- **Adding or filling an agent:** follow [agents.md](agents.md#how-to-add-or-fill-an-agent). The
  `AnalysisLead` is the worked example.

## 9. Open questions (ask Sahand)

Settled (Sahand, 2026-11-02): no Anthropic model anywhere; DeepSeek everywhere. geomind holds no
model id as a fallback: the deploy config names every model (production uses
`deepseek/deepseek-v4.1-flash-1017`), and a live run without them refuses to start.

- Return temperatures of the heating and cooling networks (assumed 60 °C and 25 °C until Sahand
  confirms).
- Whether outage days are chosen automatically (lowest demand) or by date. `gm.schedule` raises
  `NotImplementedYet` for `operating_days` until the meaning of the organisers' "330 daily steps" is
  decided.
- Cost data sources for economics (ThermoGIS, DoubletCalc or GEOPHIRES-X defaults).
