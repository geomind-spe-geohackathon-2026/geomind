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
| 6 | No code runs in geomind: no code tools and no sandbox (removed in 0.4.22); a model gemini lacks makes a family `blocked` | The agents engineer with gemini's modules; written code was never usable in a plant run | [tools.md](tools.md#code-and-web-tools) |
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
| SD | the support team alone (support lead, summarizer, curator), nine tasks, rounds D0 to D3 and F on DeepSeek and nemotron | 0.04 | 6.99 | 9 of 9 on both models by the end; bugs #95 to #99 |
| C1 | the case lead and the geoscientist alone, six tasks (files, chat, one change, a question, a flawed case, the geoscientist on the brief) | 0.06 | 3.69 | 6 of 6 passed; every flaw caught and asked; no invented value; bugs #61 to #63 |
| C2 | the case team alone again, after #61 to #63 | 0.08 | 3.77 | 6 of 6 passed; one self-computed dew point (#64) |
| TA1 | Track A after dev43 (compact tree, run-long pages, columns), six tasks | 0.16 | 4.20 | 4 of 6; from_files at its cap; cache cold after the prompt change, 10 `read_stored` left |
| TA2 | Track A after dev44, provider pinned to DeepSeek (`GEOMIND_PROVIDER=deepseek`) | 0.035 | 4.24 | 4 of 6 by the criteria; from_files 39 → 15 model calls and 0.069 → 0.011 USD, but stopped on #65; total 0.112 → 0.035 USD |
| TC1-4 | Track C: the analysis lead and the economist alone, 5 tasks, rounds C1 to C4 (C2 on, both DeepSeek and nemotron) | 0.19 | | C1 2 of 4; C4 5 of 5 on both models; bugs #85 to #90 |
| A2 | the 6 agents the fixes touched, alone again | 0.29 | 2.38 | 5 passed; the case lead now asks for the values with no source (#44 working), so its task's fixed answer must change |
| D1 | the design team alone: process, integration, reservoir, well and energy engineers and the design lead, one task each on the C1 case, 0.08 cap each | 0.38 | — | 1 of 6 passed (integration); four engineers stopped at their cap; bugs #70 to #72 |
| D2 | the same six after #70 to #72, 0.065 cap each | 0.26 | — | the lead's verdict and records right at a third of D1's cost; the engineers still at their cap; bugs #73 and #74 |
| D3 | the process and well engineers after #73 and #74, 0.06 cap each | 0.09 | — | the well engineer's failed module calls fell from 8 to 1 and it patched; the process engineer's run still ended on two garbled calls (#75) |

### Model comparison

Each per-agent task on both models, the same fixtures, prompts and commit, no provider pin for nemotron. Correctness: every number checked against gemini's own (the `number` criteria), every value sourced and none worked out (`sourced`); for the curator, what its scratch memory holds. Tokens are input/cached/output.

| agent | track | model | pass | correctness | model calls | tool calls | failed | tokens | seconds | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| analysis_lead/costs | C | deepseek-v4.1-flash | pass | gemini's numbers, sourced, none computed | 10 | 15 | 0 | 136452/81874/12780 | 167.2 | 0.0083 |
| analysis_lead/costs | C | nemotron-3.5-super (free) | pass | gemini's numbers, sourced, none computed | 7 | 7 | 1 | 85421/39024/8146 | 46.7 | 0.0000 |
| analysis_lead/operating | C | deepseek-v4.1-flash | pass | gemini's numbers, sourced, none computed | 3 | 4 | 0 | 38089/32242/3900 | 33.0 | 0.0022 |
| analysis_lead/operating | C | nemotron-3.5-super (free) | pass | gemini's numbers, sourced, none computed | 3 | 3 | 0 | 36814/26016/977 | 15.0 | 0.0000 |
| analysis_lead/sensitivity | C | deepseek-v4.1-flash | pass | gemini's numbers, sourced, none computed | 22 | 34 | 1 | 327521/164281/25059 | 240.4 | 0.0181 |
| analysis_lead/sensitivity | C | nemotron-3.5-super (free) | pass | gemini's numbers, sourced, none computed | 10 | 11 | 0 | 131176/60704/5356 | 39.7 | 0.0000 |
| economist/cost | C | deepseek-v4.1-flash | pass | gemini's numbers, sourced, none computed | 4 | 5 | 0 | 42127/16373/5912 | 58.7 | 0.0037 |
| economist/cost | C | nemotron-3.5-super (free) | pass | gemini's numbers, sourced, none computed | 4 | 5 | 0 | 45870/34688/2827 | 17.1 | 0.0000 |
| economist/uncertainty | C | deepseek-v4.1-flash | pass | gemini's numbers, sourced, none computed | 8 | 10 | 0 | 101590/36332/10042 | 97.7 | 0.0071 |
| economist/uncertainty | C | nemotron-3.5-super (free) | pass | gemini's numbers, sourced, none computed | 6 | 8 | 1 | 74420/52032/2835 | 68.1 | 0.0000 |
| curator | D | deepseek-v4.1-flash | 3/3 | memory and summaries checked by code | 6 | 10 | 0 | 15917/7168/1822 | 52 | 0.0012 |
| summarizer | D | deepseek-v4.1-flash | 3/3 | memory and summaries checked by code | 3 | 0 | 0 | 4257/512/7892 | 140 | 0.0039 |
| support_lead | D | deepseek-v4.1-flash | 3/3 | memory and summaries checked by code | 10 | 11 | 1 | 23753/4096/7283 | 130 | 0.0042 |
| curator | D | nemotron-3.5-super (free) | 3/3 | memory and summaries checked by code | 6 | 10 | 0 | 16203/0/1895 | 25 | 0.0000 |
| summarizer | D | nemotron-3.5-super (free) | 3/3 | memory and summaries checked by code | 3 | 0 | 0 | 4493/0/8445 | 40 | 0.0000 |
| support_lead | D | nemotron-3.5-super (free) | 3/3 | memory and summaries checked by code | 9 | 9 | 0 | 21878/0/11345 | 64 | 0.0000 |
| design lead | B2 | deepseek | yes* | feasible verdict recorded; *`sourced` flags 0.999993 (a gemini ratio shortened to 6 decimals) | 7 | 8 | 0 | 129680/31744/2799 | 69 | 0.0047 |
| design lead | B2 | nemotron | yes | feasible verdict recorded (after #78) | 6 | 12 | 1 | 118096/69376/1525 | 26 | 0 |
| process | B2 | deepseek | yes | design 0 issues (after #77) | 5 | 7 | 0 | 64518/0/13508 | 238 | 0.0074 |
| process | B2 | nemotron | yes | design 0 issues | 6 | 8 | 1 | 86456/43360/12691 | 62 | 0 |
| integration | B2 | deepseek | yes | sound plant, streams traced (after #81) | 2 | 3 | 0 | 18451/0/5473 | 65 | 0.0032 |
| integration | B2 | nemotron | yes | sound plant, streams traced | 3 | 4 | 1 | 30605/8672/2607 | 18 | 0 |
| reservoir | B2 | deepseek | yes | design 0 issues | 6 | 9 | 0 | 120071/30206/25120 | 451 | 0.0146 |
| reservoir | B2 | nemotron | yes | design 0 issues | 4 | 5 | 0 | 77176/13008/9134 | 47 | 0 |
| well | B2 | deepseek | yes | design 0 issues | 4 | 5 | 1 | 49607/13312/16118 | 333 | 0.0086 |
| well | B2 | nemotron | yes* | design 0 issues; *`sourced` flags 0.0833333 (a plant value shortened to 7 decimals) | 4 | 4 | 0 | 50068/13008/23189 | 136 | 0 |
| energy | B2 | deepseek | yes | design 0 issues (after #76, #79, #80) | 11 | 19 | 0 | 359592/153160/39004 | 580 | 0.0261 |
| energy | B2 | nemotron | yes | design 0 issues | 5 | 8 | 1 | 102241/0/17315 | 112 | 0 |
| coordinator/case_question | E | deepseek (e6) | pass | yes | 1 | 0 | 0 | 1865/0/39 | 5.3 | 0.0001 |
| coordinator/case_question | E | nemotron (n1) | pass | yes | 1 | 0 | 0 | 1843/0/129 | 21.0 | 0.0000 |
| coordinator/cost | E | deepseek (e6) | pass | yes | 1 | 0 | 0 | 1870/0/39 | 4.9 | 0.0001 |
| coordinator/cost | E | nemotron (n1) | pass | yes | 1 | 0 | 0 | 1848/0/84 | 21.3 | 0.0000 |
| coordinator/design | E | deepseek (e6) | pass | yes | 1 | 0 | 0 | 1870/0/52 | 4.3 | 0.0001 |
| coordinator/design | E | nemotron (n1) | pass | yes | 1 | 0 | 0 | 1849/0/130 | 17.6 | 0.0000 |
| coordinator/greeting | E | deepseek (e6) | pass | yes | 1 | 0 | 0 | 1859/0/25 | 5.1 | 0.0001 |
| coordinator/greeting | E | nemotron (n1) | pass | yes | 1 | 0 | 0 | 1837/0/63 | 16.4 | 0.0000 |
| explainer/explain | E | deepseek (e3) | pass | yes | 6 | 15 | 1 | 97724/0/12851 | 243.5 | 0.0086 |
| explainer/explain | E | nemotron (n1) | pass | yes | 2 | 5 | 0 | 21115/0/15317 | 109.9 | 0.0000 |
| project_lead/case_change | E | deepseek (e3) | pass | yes | 13 | 14 | 0 | 75752/16892/4855 | 194.9 | 0.0042 |
| project_lead/case_change | E | nemotron (n1) | pass | yes | 11 | 17 | 2 | 81136/39024/5152 | 163.7 | 0.0000 |
| project_lead/needs_case | E | deepseek (e6) | pass | yes | 9 | 12 | 0 | 55444/8187/5450 | 175.8 | 0.0042 |
| project_lead/needs_case | E | nemotron (n1) | pass | yes | 7 | 15 | 0 | 52293/30352/4469 | 28.9 | 0.0000 |
| reviewer/fails | E | deepseek (e5) | pass | yes | 7 | 11 | 0 | 90195/12794/10898 | 98.0 | 0.0078 |
| reviewer/fails | E | nemotron (n3) | pass | yes | 4 | 6 | 0 | 45776/8672/7947 | 47.6 | 0.0000 |
| reviewer/passes | E | deepseek (e4) | pass | yes | 10 | 15 | 1 | 130589/44022/13019 | 161.0 | 0.0093 |
| reviewer/passes | E | nemotron (n2) | pass | yes | 3 | 6 | 0 | 34632/4336/4076 | 22.7 | 0.0000 |
| case_lead/project | A | deepseek-v4.1-flash | fail | no case: no set_case accepted; stopped by the repeat guard (same files-only set_case failed 3 times) | 34 | 78 | 18 | 1647092/1116919/64428 | 800 | 0.0536 |
| case_lead/from_files | A | deepseek-v4.1-flash | fail | no case; capped at 0.07; `sourced` flags the cap message's numbers | 31 | 90 | 14 | 1521181/1007755/68017 | 889 | 0.0542 |
| case_lead/from_chat | A | deepseek-v4.1-flash | fail | case accepted by gemini; capped at 0.03 before finishing; `sourced` flags the cap message's numbers | 8 | 35 | 1 | 293854/174117/18399 | 208 | 0.0136 |
| case_lead/flawed | A | deepseek-v4.1-flash | fail | capped at 0.03 before any question; `sourced` flags the cap message's numbers | 12 | 25 | 2 | 315193/104621/31755 | 388 | 0.0226 |
| case_lead/change_one | A | deepseek-v4.1-flash | pass | case accepted by gemini, sourced | 7 | 7 | 1 | 79659/69623/9768 | 76 | 0.0053 |
| case_lead/question | A | deepseek-v4.1-flash | pass | sourced | 3 | 4 | 1 | 31888/0/3911 | 39 | 0.0029 |
| geoscientist/brief | A | deepseek-v4.1-flash | pass | sourced | 6 | 10 | 1 | 69932/25088/14154 | 173 | 0.0083 |
| case_lead/project | A | nemotron-3.5-super (free) | fail | case accepted by gemini, sourced, no economics; fails `before` (no search_rag before ask_user) | 14 | 18 | 4 | 331361/268832/50318 | 281 | 0.0000 |
| case_lead/from_files | A | nemotron-3.5-super (free) | fail | case accepted (no economics); fails `before`; run error: economics sent twice as broken JSON text | 14 | 19 | 7 | 415328/260160/64253 | 318 | 0.0000 |
| case_lead/from_chat | A | nemotron-3.5-super (free) | pass | case accepted by gemini, sourced | 8 | 13 | 2 | 107806/73712/11742 | 72 | 0.0000 |
| case_lead/flawed | A | nemotron-3.5-super (free) | fail | no question asked: took the project as having no case file; flaws not raised | 5 | 8 | 3 | 103939/52032/8036 | 46 | 0.0000 |
| case_lead/change_one | A | nemotron-3.5-super (free) | pass | case accepted by gemini, sourced | 3 | 3 | 0 | 34282/17344/631 | 14 | 0.0000 |
| case_lead/question | A | nemotron-3.5-super (free) | pass | sourced | 3 | 3 | 1 | 33132/26016/1373 | 9 | 0.0000 |
| geoscientist/brief | A | nemotron-3.5-super (free) | pass | sourced | 4 | 4 | 1 | 31619/13008/5265 | 32 | 0.0000 |
| case_lead/project | A3 | deepseek-v4.1-flash | fail | no case: one files-only set_case (`case_incomplete`), never resent whole; step limit; geoscientist 4 times after `already_asked`, lower-cased file names again; no question | 35 | 83 | 10 | 1927191/1337099/45351 | 598 | 0.0475 |
| case_lead/from_files | A3 | deepseek-v4.1-flash | pass | case set by the criteria, but its answer says it never read the files (22 `read_rag`); step limit | 35 | 83 | 9 | 1863975/1354159/56263 | 715 | 0.0501 |
| case_lead/from_chat | A3 | deepseek-v4.1-flash | fail | stopped at the cap after 14 `search_rag`, before any set_case; the cap's answer no longer flagged by `sourced` (#116) | 6 | 30 | 3 | 285237/189908/25526 | 370 | 0.0162 |
| case_lead/flawed | A3 | deepseek-v4.1-flash | fail | loaded the project's case, then stopped at the cap reading (`read_stored` 7) before any question | 13 | 34 | 1 | 466650/250039/27492 | 325 | 0.0215 |
| case_lead/change_one | A3 | deepseek-v4.1-flash | pass | case accepted by gemini, sourced | 6 | 7 | 0 | 71682/32252/5564 | 57 | 0.0041 |
| case_lead/question | A3 | deepseek-v4.1-flash | pass | sourced | 3 | 4 | 1 | 32836/20476/1804 | 24 | 0.0014 |
| geoscientist/brief | A3 | deepseek-v4.1-flash | pass | sourced | 6 | 11 | 1 | 64053/6144/11725 | 160 | 0.0075 |
| case_lead/project | A3 | nemotron-3.5-super (free) | fail | no case: `set_case`'s `changes` as JSON text with a stray `}` mid-text, twice, ended the run (bug 3 of the rerun); it did read the cost catalogue and search before setting | 12 | 20 | 3 | 394187/208128/78724 | 481 | 0.0000 |
| case_lead/from_files | A3 | nemotron-3.5-super (free) | fail | case accepted with `°C/km` and mol% mapped by set_case, listed in its one question; no economics, fails `before`; run error: `update_state` JSON text broken twice | 14 | 19 | 6 | 398314/281840/64139 | 355 | 0.0000 |
| case_lead/from_chat | A3 | nemotron-3.5-super (free) | fail | case accepted; `sourced`: 365 (a day count it wrote) | 8 | 15 | 2 | 227042/138752/35134 | 207 | 0.0000 |
| case_lead/flawed | A3 | nemotron-3.5-super (free) | fail | loaded the case after the new `no_case` text (#68) and named the flaws (span, cooling return, ...) in its answer, but asked no question | 4 | 6 | 1 | 76303/17344/4947 | 31 | 0.0000 |
| case_lead/change_one | A3 | nemotron-3.5-super (free) | pass | case accepted by gemini, sourced | 3 | 3 | 0 | 36345/26016/802 | 10 | 0.0000 |
| case_lead/question | A3 | nemotron-3.5-super (free) | pass | sourced | 3 | 3 | 1 | 34083/8672/1131 | 10 | 0.0000 |
| geoscientist/brief | A3 | nemotron-3.5-super (free) | pass | sourced | 3 | 3 | 0 | 21512/8672/5960 | 36 | 0.0000 |
| case_lead/project | A4 | deepseek-v4.1-flash | fail | no case, cost cap; re-read loop (read_rag 48, search_rag 32); never called set_case | 33 | 100 | 17 | 1619171/1042312/85325 | 850 | 0.0647 |
| case_lead/from_files | A4 | deepseek-v4.1-flash | fail | no case: files-only set_case twice, step limit; same re-read loop | 36 | 92 | 14 | 1621086/976725/77613 | 978 | 0.0621 |
| case_lead/flawed | A4 | deepseek-v4.1-flash | pass | loaded, asked about the flaws, set the confirmed one | 13 | 19 | 1 | 274774/173550/40230 | 475 | 0.0233 |
| case_lead/project | A4 | nemotron-3.5-super (free) | pass | case set and accepted (4 broken JSON texts repaired, unit names mapped); searched and read the catalogue; no economics | 16 | 23 | 7 | 697623/303520/77210 | 448 | 0.0000 |
| case_lead/from_files | A4 | nemotron-3.5-super (free) | fail | case accepted; no search_rag before the first ask_user | 10 | 12 | 3 | 250804/173440/49047 | 301 | 0.0000 |
| case_lead/flawed | A4 | nemotron-3.5-super (free) | fail | one question with all 4 flaws; the criterion wants the word "doublet" | 6 | 9 | 1 | 136199/26016/24153 | 238 | 0.0000 |
| case_lead/project | A5 | deepseek-v4.1-flash | pass | case set and accepted, 9 requirements, economics set (23 keys with their row ids) | 34 | 80 | 9 | 1667135/1112805/79384 | 930 | 0.0633 |
| case_lead/from_files | A5 | deepseek-v4.1-flash | pass | case and economics set | 36 | 72 | 9 | 1662184/1194040/99855 | 975 | 0.0711 |
| case_lead/flawed | A5 | deepseek-v4.1-flash | fail | asked about all 4 flaws; then a question no answer rule takes, cost cap | 17 | 27 | 1 | 417441/167663/43635 | 716 | 0.0303 |
| case_lead/project | A5 | nemotron-3.5-super (free) | pass | case set and accepted, economics set (9 keys); 6 requirements, pump efficiency written 70 | 19 | 24 | 6 | 661715/338208/77821 | 506 | 0.0000 |
| case_lead/from_files | A5 | nemotron-3.5-super (free) | fail (pass with the float tolerance of dev58) | case and economics set; `sourced` flagged float noise in catalogue values | 21 | 28 | 2 | 739370/407584/86646 | 642 | 0.0000 |
| case_lead/flawed | A5 | nemotron-3.5-super (free) | pass | asked about the flaws | 10 | 14 | 1 | 286492/190784/23437 | 132 | 0.0000 |

Track C, round C4 at 39c4003: 5 of 5 on each model, no 429, no markup check firing. nemotron took fewer calls and a third to a half the time on the lead's two longer tasks; its failed calls are `update_state` slips (JSON text, a stray bracket), each corrected on the next call. Both models failed the same way only where the prompt was wrong (#85, #88, #90).

Track D notes: no 429 on nemotron (nine tasks two at a time). Nemotron called memory tools it was not offered when the memory was off (#99, fixed in the prompt; it passes now); it caches nothing, so its input is all uncached, but it is free and 2 to 3 times faster here.

Track B2 notes: Big differences: DeepSeek pinned to its own provider takes 30 to 90 s a call (reservoir 451 s for 6 calls), nemotron 4 to 20 s; that is the model and the provider, not the prompt. Before the prompt fixes DeepSeek also looped where nemotron did not (integration 18 calls, energy 18 calls); after #79 to #81 the counts are close, so that part was the prompt. Both models converted units in their answers (#80), a prompt matter. The markup check of #70/#75 never fired on nemotron.

Track E notes: `deepseek/deepseek-v4.1-flash-1017` (provider DeepSeek) and `nvidia/nemotron-3.5-super-vl:free` (no pin, two at a time, retries 6 x 10 s; no 429 in track E). Round in brackets; tokens are input/cached/output; DeepSeek's coordinator and lead `needs_case` rows are their E1/E2 recordings scored again with the corrected criteria (e6, no new call).

Track A notes (case team, dev51 at 1a50f61): DeepSeek (provider DeepSeek) capped at 0.15 for the project case and 0.03/0.07 for the six tasks; nemotron at no pin, two at a time, retries 6 x 10 s; no 429 on either. Model and tool calls count the geoscientist's calls inside the lead's run; failed counts every refused tool call and refused answer, from an offline replay. DeepSeek passes 3 of 6 tasks: three ran out of their caps, and its project case set nothing (four `already_asked` geoscientist calls, then a files-only `set_case` repeated until the repeat guard stopped the run). nemotron passes 4 of 6 and sets the project case gemini accepts, without economics, but never calls `search_rag` before asking. Both models first sent the gradient as °C/km and the gas fractions as mol% (80), which gemini's case keys refuse.

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
| 68 | Track A rerun (dev51), case lead on nemotron | `read_case`'s `no_case` read as "the project has no case file": it asked for every site value and raised none of the flaws of the project's case | `no_case` in a project with a case file says "the project has a case file: set_case(source='project') loads it" | track-a3 |
| 69 | Track A rerun (dev51), case lead on DeepSeek | after a refused full `set_case` it sent the files-only call `case_incomplete` had refused, three times, until the repeat guard stopped the run; called the geoscientist 4 times after `already_asked`; lower-cased file names in `read_rag` | prompt: after a refused full call fix the named keys and send the SAME full call, never files alone; never call the geoscientist after `already_asked`; file names as `list_files` gives them | track-a3 |
| 115 | Track A rerun (dev51), case lead on both models | wrote the gradient as `degC/km`/`°C/km` and the gas fractions in `mol%` (`CH4 80`), as the brief does; gemini 0.6.1 refuses both. nemotron never searched the knowledge base before asking, so the case got no economics (`before` failed) | `set_case` maps `°C/km`, `degC/km`, `C/km` to `K/km` (same number) and turns `%`/`mol%` on a gas fraction into the fraction, listing each in `converted` for the confirmation question (removed when gemini requests 15 and 31 land; the one unit-math line allowlisted). gemini 0.6.2 landed 15: `mol%` goes to gemini, `%` is only named `mol%`, and the allowlist is empty; the gradient mapping stays until 31; prompt: `search_rag` for each missing value and the cost catalogue, always, before the one question | track-a3 |
| 116 | Track A rerun (dev51), evals | `sourced` flagged the numbers of the engine's answer at a limit (cost used, the cap, tokens needed) as made up | `Outcome.partial`, set from the run's stop reason, leaves that answer out of `sourced`; questions are still checked | track-a3 |
| 117 | Track A3 rerun, case lead on nemotron | sent `set_case`'s `changes` (`..."°C"}}}}, "requirements"`) and `update_state`'s (`}}]}`) as JSON text with a stray closing bracket mid-text; the refusals ended the project and from_files runs | `parsed_json` deletes a closing bracket that closes nothing open where `json` stops, up to three, only when no bracket is made up; the recorded strings are fixtures | track-a4 |
| 118 | Track A3 rerun, case lead on nemotron | wrote `kg/m³`, `mPa·s`, `Nm³/m³`, `m³/h`, `MWth`/`MWcool` as the sources print them; refused, fixed one call later | `set_case` maps those names to gemini's (no factor) where the key's units hold the name; `converted` reason `unit name` | track-a4 |
| 119 | Track A3 rerun, case lead on nemotron (flawed) | named the loaded case's flaws in its answer and asked no question | prompt: a flaw is always an `ask_user` question before finishing, do/don't; checklist line | track-a4 |
| 120 | Track A3 rerun, case lead on DeepSeek (project) | 16 `read_stored` of pages still in its conversation: `read_rag`'s `already_read` note said "after a compaction, read_stored a reference" with a reference, and no compaction had happened | the note says to work from the conversation and shows no reference unless a compaction happened since the read | track-a4 |
| 121 | Track A4 rerun, case lead on nemotron (project) | set and accepted the case with no economics; said it would offer catalogue rows "in the next step" and finished | prompt: a numbered workflow, economics its required step 5 (catalogue read once, one question with each value's row, `set_case(economics=...)`); checklist line; evals: `state /case/economics` on the project and from_files case tasks | track-a5 |
| 122 | Track A4 rerun, case lead on DeepSeek (project, from_files) | 48 `read_rag` and 32 `search_rag`, the texts whole in its context, never a `set_case` | `read_rag`'s note on a page this run read: "already read at step N; its text is in your context; call set_case next" (`work from it` for an agent without `set_case`), `force` too unless a compaction happened since | track-a5 |
| 123 | Track A4 rerun, case lead on nemotron (flawed) | asked about the `annual_operation` flaw, failed `question contains doublet` | `question` criterion takes `contains_any`; the flawed task accepts `doublet`, `annual_operation` or `count` | track-a5 |
| 124 | e2e-final, case lead delegated by the project lead (nemotron) | read the cost catalogue, set the case with no economics and asked nothing: the brief listed no economics and said "report the missing values", and it ended with its question as text | code: `Agent.answer_problem`, checked before an answer is accepted; the case lead refuses once an answer of a run that called `set_case` and left the case with no economics and no `ask_user` naming economics, also a text answer, with step 5; prompts: a case brief asks for the economics and leaves the questions to the case lead, which follows its workflow in a delegated run too | track-h |
| 125 | e2e-final, design lead | `list_profiles` crashed (`float() ... 'NoneType'`) on a case with no return temperatures | a service with no return temperature lists it as `null` | track-h |
| 126 | e2e-final, design lead | `read_plant` with a made-up `with_schema` was a validation failure; two in a row ended two design-lead runs | an unknown argument is an error result naming the tool's real arguments, not counted toward "invalid calls in a row" | track-h |
| 127 | e2e-final, support lead and curator, memory off | the curator ran and called `search_memory` and `write_lesson` (3 `not_allowed`) | with the memory off the curator is not offered (`needs_memory`), and a call of a tool not offered is `not_allowed` without running; the support lead's prompt says so | track-h |
| 128 | e2e-final, project lead | its `finish` had three suggestions, `run.finished` two | no bug: stage `case` keeps one step from outside its own (`case_by_questions`); `other_case` is a later stage's; the event's items are `{label, message}` as the contract; `finish` says the rule | track-h |
| 129 | e2e-final, design lead on nemotron | `update_state changes` as JSON text was refused "Input should be a valid list": the text closed the change object before its last key (`"reason": "x"}, "citation": null}]`) | `parsed_json` deletes the `}` before a key that `json` meets inside a list | track-h |
| 130 | e2e-final, case lead on nemotron | `pump_efficiency` requirement `min 70, max 70` with no unit, read by gemini as 70, not 0.7 | `set_case` refuses an efficiency, fraction or share bound outside 0-1: "an efficiency is a fraction 0-1: 0.7, not 70" (no computed fraction: the no-unit-math rule) | track-h |
| 131 | e2e-final, replay | `geomind replay` of the resumed run failed on `search_rag`'s "already searched" note: two calls of one step with the same words ran together, and which got the note depended on which ran first (the base code passes 1 of 3 replays) | the note comes from the run's conversation in call order, which a resume and a replay rebuild; no in-process set | track-h |
| 132 | e2e-final3, reservoir, well and energy engineers on nemotron | 31 `patch_plant not_allowed`: the owners were recorded (state v4 reached every engineer), but the engineers wrote their parameters at the top (`d0`, `d0.well`, `degasser`) or inside `modules`, and `d0.nominal_flow` had no owner prefix | a module's parameters at the top or in `modules` are taken as under `params`; a path `design.owners` names no prefix of goes by its module's gemini type (`OWNED_MODULES`, then the category) | track-i |
| 133 | e2e-final3, case lead | the user's typed values to [approve all, change some, stop] were refused; after `change some` the case lead wrote its follow-up as answer text and moved on | a question with options takes typed text, marked typed for the model; the case lead's answer after `change some` with no follow-up question is refused once | track-i |
| 134 | e2e-final3, case lead | `approve all` on the economics stored only the single-row keys: no multi-row key, no currency, price year or discount rate, no row ids | `ask_economics`: the case lead's rows, the question written by code, and on approve all every value set by code with its row in `about.sources` and an assumption with its citation (`Tool.on_answer`, replayed from the log) | track-i |
| 135 | e2e-final3, design lead | three parallel `read_plant` calls (other `plant_class`, one unknown argument) ended the run "the same call failed 3 times" before the model saw an error | the repeat guard compares the tool and the whole input, and counts a failure once per step; #49's rule (only the input the error names) is gone | track-i |
| 136 | e2e-final3, design lead and well engineer | copied the history's `{"shortened": ...}` placeholder as a call (`well_engineer`, `update_state`) | an old long call shows an empty input and its outline in the message text; a `{"shortened": ...}` input is refused naming the real arguments | track-i |
| 137 | e2e-final3, project lead and case lead | `site.air.pressure` asked twice (request-1962, request-2055) | a tool's question naming exactly the case paths an earlier answered question of the tree named takes that answer, from the root's log | track-i |
| 138 | e2e-final4, design lead | one `set_ranges` call sent 37 times with success (3 distinct inputs in 40), until two step limits | a call identical to an earlier successful one of a tool that `repeats_same` (pure, or `sets_input`), with nothing not pure between, is answered "same result as step N" without running; three such steps in a row stop the run | track-j |
| 139 | e2e-final4, case lead | `ask_economics` approve all lost: "older shape; expected a header first" (seq 424) on a case without economics | a new economics file starts from its header | track-j |
| 140 | e2e-final4, case lead | `site.air.pressure`, item 4 of request-259, asked again alone (request-2872) | asked-once per path: only answered paths take the earlier answers; new ones are asked with the earlier answers under the question | track-j |
| 141 | e2e-final4, design lead and process engineer | invalid JSON text for `plant` and `changes` got "Input should be a valid dictionary/list"; resent unchanged | the error names json's message, line, column, char and an excerpt, and a Python literal there | track-j |
| 142 | e2e-final4, case lead | `ask_economics` refused `others: null` (21 errors) and `source: null` | null is accepted for every field but `key`; a null value is open | track-j |
| 143 | e2e-final4, process engineer | `thermal_storage` in `optional` of a class plant refused, then unconnected ports of a hand-copied free plant: step limit | `build_plant(from_class=...)` adds modules and connections to a class's structure; a class plant with a foreign module is refused naming it | track-j |
| 144 | prod c8bf2381 (B4), memory off | `search_memory` answered `internal`; prompts still spoke of the memory | cause: 0.4.22 used the bound `Workspace.memory` as the memory (0.4.23 calls it); pinned for every agent, nested runs and both off paths; memory-only prompt parts marked and left out; a failing store is `memory_unavailable` | prod-bugs |
| 145 | prod c8bf2381 (B6), case lead | read the whole cost catalogue: about 21 steps at 55-80k input tokens | `read_rag` `rows` filter; a table over `LARGE_TABLE_CHARACTERS` after `rows`/`columns` gives its outline and a note only; the prompt reads the missing keys' rows | prod-bugs |
| 146 | prod (B10), `gd.mcp.list_tools` | failed on the dict `{name, url, transport, headers}`; `failure()` read `server.name` and hid the real error | a dict is taken everywhere a server comes in; `failure()` names the server when it can and keeps the real error | prod-bugs |
| 147 | prod c8bf2381 (B3), case with `site.fluid.dissolved_gas.H2S` | `set_case` and `gm.check` took it, then `build_plant`/`simulate` failed with `gas composition: species = 'H2S'` | gemini's bug, fixed in gemini 0.6.4 (H2S burns, no CO2); geomind needed no change and had no workaround; pinned by `test_h2s_in_the_dissolved_gas_is_accepted_and_reaches_gemini_as_given` and `test_a_brine_gas_with_h2s_simulates_and_its_h2s_forms_no_co2` | gemini-064 |
| 85 | C1 (Track C), economist | told to cost a design, it sampled 200 draws and a sensitivity with a seed it chose (192 s) | uncertainty and sensitivity only when the task asks for them | track-c |
| 86 | C1 (Track C), evals | the `sourced` criterion left out the problem state's `Case:` line, so the case's own years counted as made up | the state's `Case:` line is read; the agent's notes and questions stay out | track-c |
| 87 | C2 (Track C), economist and analysis lead on nemotron | sent `update_state`'s `changes` as a JSON string; two refusals in a row stopped the economist's nested run, and the lead finished without it | `Tool.validate` reads a list or an object given as its JSON text (model-agnostic) | track-c |
| 88 | C2 (Track C), analysis lead on DeepSeek | asked `compute_kpis` for `annualised_cost`, a cost metric it lacks, because the reference listed the metrics under `compute_kpis` too | the reference says `compute_kpis` has names of its own: call it without `names`; costs come from `estimate_costs` | track-c |
| 89 | C3 (Track C), economist on nemotron | `changes` as JSON text missing its final `]`, twice, ended the run; `read_case(section="None")` | a JSON text missing only its closing brackets is read; `"None"`/`"null"` is null where the schema takes one | track-c |
| 90 | C3 (Track C), analysis lead on nemotron | sampled `capex` and `opex`, which a study refuses: the reference said a study takes every metric | the reference names what a study reads (the objectives and gemini's five study KPIs, pinned by a test); gemini request 26 | track-c |
| 67 | Track A, case lead | on nemotron, `set_case`'s `changes` sent as its JSON text twice; refused as no dictionary, and the run ended on 2 invalid calls in a row | a string for a parameter that takes an object or an array, and no string, is read as JSON when it gives that type (`Tool.validate`, every tool) | track-a2 |
| 70 | D1, process engineer | DeepSeek leaked tool-call markup into an argument (`">HeatingCoolingPlant</</parameter name=`) and sent it again three times | an input holding markup is refused before the tool runs, with the value before the markup as the suggestion | track-b |
| 71 | D1, design engineers | each engineer read the case 4 to 16 times and its profiles again and again: a long result shrinks to an outline after one step | the engineers keep the case, the plant and the module descriptions whole for a few turns (`Tool.kept()`); `read_profile` gives a `summary` (peak, minimum, mean, energy) computed by code | track-b |
| 72 | D1, design lead | checked a design handed to it complete, then recorded it only as a note, not as `design.reference` and `design.result` | the prompt says a checked handed design is final too | track-b |
| 73 | D2, process engineer | parallel `read_plant` calls came back with every argument null until the run stopped on repeated failures | it compares plants with `list_plants` and reads only the one it chooses, in one call | track-b |
| 74 | D2, well engineer | 8 failed `evaluate_module` calls on a well path's section lists: gemini's `describe()` gives them as `number`, and its error asks for a Quantity for a list and for a list for a Quantity | the well engineer's prompt gives the form `{"value": [..], "unit": "m"}`; gemini request 14 | track-b |
| 75 | D3, process engineer | two garbled calls in a row (`">site</</parameter_name...`) counted as invalid calls and ended the run as failed; `">HackathonPlant</` was not caught | a markup slip is an error but no validation failure; a lone `</` or a leading `">` counts as markup; prose tools (`finish`, `ask_user`, `update_state`, `write_lesson`) are not checked | track-b |
| 105 | E1, explainer | asked `compute_kpis` for `annualised_cost`: the prompt said the KPIs hold the costs | the metrics section says the costs come from `estimate_costs` and `compute_kpis` is called without `names` | track-e |
| 106 | E1, reviewer and explainer | 17 `read_stored` and 42 `read_result` calls; the explainer read its whole input set three times as each result shrank | the reviewer keeps its reads for a few turns, the explainer for the run | track-e |
| 107 | E1, reviewer | `read_case(section="about")` on a case without `about` answered "expected one of about, ...; did you mean 'about'?" | a known section the case has not set is `unknown_name`, "the case has no 'about'" | track-e |
| 108 | E1, reviewer | tried `read_stored("state")` to read the problem state | the prompt says the state is a message of the conversation | track-e |
| 109 | E1, project lead | briefed the case lead on a case already set, and a team 14 times on one answer | no case step for an accepted case; no third brief after two same answers | track-e |
| 110 | E2, explainer | wrote `1500000.0 W/K` as `1.5 MW/K` and `30000000.0 W` as `30 MW`, conversions of its own | capacities from `compute_kpis`, plant values in their own units; gemini request 30 | track-e |
| 112 | N1 (nemotron), reviewer | sent `update_state`'s `changes` as JSON text, twice, and the run stopped | JSON text of the array or object a schema wants is decoded before validation | track-e |
| 111 | E2, project lead | asked the user for the air humidity "in %, e.g. 70": a typical value | a case value is the case lead's to ask; a question offers no value | track-e |
| 76 | B2, energy engineer | `evaluate_module` with a control as a parameter (`temperature_setpoint`) gave `internal` (gemini's bare `KeyError`), then misleading "missing inlets", five times until the run stopped | names checked before gemini: `invalid_input` with where it goes | track-b2 |
| 77 | B2, process engineer | built from `read_plant(plant_class=...)`, a header with 110 values missing, while the project held the class's whole file | the prompt prefers the project plant of the class | track-b2 |
| 78 | B2, design lead (nemotron) | checked a handed design feasible, then finished without `design.reference` and `design.result`; DeepSeek records them | the prompt asks for the record before every `finish` | track-b2 |
| 79 | B2, energy engineer (DeepSeek) | `evaluate_module` on a heat pump without `inlets`, seven times (gemini: "missing required inlet(s)"), on a machine the plant file already sized | each missing stream inlet is named with its form before gemini; the prompt evaluates only a machine it changes | track-b2 |
| 80 | B2, energy engineer (both models) | wrote `320.15 K (47 degC)` and a pressure in Pa as `15.74 bar`: a unit conversion by the model, flagged by `sourced` | a don't example: copy each value with the unit of its source | track-b2 |
| 81 | B2, integration engineer (DeepSeek) | on a plant gemini checked clean: 18 model calls, 7 `read_plant`, 7 `describe_module`, 123k output tokens, 31 min (nemotron: 2 calls) | the prompt finishes with no patch when no issue names a connection, and ports come from the prompt | track-b2 |
| 95 | D0, curator | wrote a case lead's lesson the memory already held: `search_memory` gave it only the curator's own lessons | the curator reads every role's lessons; `write_lesson` refuses an unknown role | track-d |
| 96 | D0, curator | a lesson named the project's brief ("the GEMINI brief") | the prompt says every field of an entry, lists the roles, and gives do and don't examples | track-d |
| 97 | review, support lead | told to give the summarizer references, which it cannot read | hands the material itself, whole | track-d |
| 98 | D1, summarizer | 16,000 output tokens of reasoning and no text for a 2.7k-character handover | temperature 0; one pass | track-d |
| 99 | F, curator (nemotron) | with the memory off it called the memory tools it was not offered | the prompt says the memory is off when those tools are not offered | track-d |
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

Requests to gemini (full text in the adaptation notes; the status of each is in the table after
the list):

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
30. A plant file's parameters in display units (`Plant.to_dict(units="display")`, or units on
    `read_plant`'s values): the explainer quotes `1500000.0 W/K` and `30000000.0 W` from the
    plant file, and only `capacities` come in MW (found in run E2, bug #110).
27. `gm.call` (`evaluate_module`) raises a bare `KeyError: 'temperature_setpoint'` for a
    control given in `parameters`; a `ValidationError` naming the control and `controls` would
    let a caller fix it (geomind checks the names itself now, #76).
28. `read_plant`-style class files: `gm.modules.get(<plant class>)` gives a header and modules
    only, and a plant built from it lists every inner value as missing (`d0.well.section_length`,
    `d0.esp.head_coefficients`, ...), while the hackathon project file of the same class holds
    them; a class default file with every value, or the values derived from the doublet's
    top-level ones (request 11).
29. `gm.units` refuses `MW/K` for a thermal conductance (`heat_exchanger.thermal_conductance`
    takes `W/K` only), while it accepts `MW` for power; the energy engineer wrote `1.5 MW/K` and
    was refused. The prefixed units (`kW/K`, `MW/K`) for conductance.
26. A public list of the metrics a study reads: `gm.study` checks them against
    `gemini.study._utils.trial.KPI_NAMES` and `ECONOMICS`, private names, so geomind pins them in
    a test to tell the agents (`heating_coverage`, `cooling_coverage`, `cop`, `peak_heat`,
    `peak_cold` and the five objectives); `gm.evaluate.metrics()` does not say which a study reads
    (Track C, bug #90).
31. `site.ground.gradient` refuses `°C/km` and `degC/km`, the unit briefs write (only `K/km`,
    `K/m`); a temperature gradient is a temperature difference per length, so `°C/km` is `K/km`
    with the same number. Asked: accept `°C/km` and `degC/km` (and `/m`) as a temperature
    gradient; geomind's `set_case` maps them until then (Track A3, bug #115).
32. `site.air.pressure` has no default and no source in a brief: the end-to-end run (nemotron,
    memory off) stopped at `size_plant` with `site.air.pressure is missing; expected a value in
    the case (it has no default)` after the user answered "unknown". geomind's key tree says
    "from the site's elevation", but the case has no elevation key and gemini derives nothing.
    Asked: a `site.elevation` (m above sea level, default 0) and `site.air.pressure` derived from
    it by the standard atmosphere when unset, as `site.reservoir` derives its temperature from the
    gradient (found in e2e-final, piece e2e-fixes).
16. Economics units the cited cost data needs but the keys refuse: `capex.ice_storage` per MWh of
    cold (only EUR/m3), `capex.heat_exchanger` in EUR/W (only EUR/(W/K)), `capex.pipe` in EUR/MW/m
    (only EUR/m), `opex.fixed.*` as an amount per W or MW per year (only %/yr), and
    `revenue.subsidy.amount` per MWh of heat as SDE++ pays it (only EUR/yr).
17. gemini's own cost catalogue (`docs/cost-sources/sources.csv`) names paths that are no keys of
    `gm.case.Economics`: the prefix `assumptions.finance.*`, `emissions.CO2.electricity` (the
    case's `utilities.electricity.co2_intensity`), `opex.chemical`, `opex.waste_disposal`
    (`opex.variable.waste_disposal`).
18. `opex.variable.*` has no keys for `chp`, `scale_inhibitor` and `corrosion_inhibitor`, which
    cited sources price (EUR/MWh electric, EUR/kg).
22. Case schema descriptions: `Case.schema()` gives no description for `about`,
    `initial_state`, `economics.about` and `demand.{heating,cooling}.{minimum,maximum}_return_temperature`;
    geomind took their meaning from gemini's code (`geomind/tools/gemini/fields.py`, each text
    naming its module and function: `heating.maximum_return_temperature` and
    `cooling.minimum_return_temperature` are read but never used). Asked: a description of each
    in the schema (Track F).
33. (E2E-13, open, not sent: for Sahand) `gm.check` says "an empty list means ready", but two
    values it passes stop the run: `params.control.dispatch` and `params.control.outages`
    (optional `Parameter`s, `None` by default; `gm.schedule` raises `missing_value` only in
    `_stated_rules`) and a `ProductionWell` split at its pump (`segment` `below_esp` or
    `above_esp`) without `esp_depth` (optional, `None`; `_esp_depth` raises `invalid_design` in
    the run, with `path` None). Asked: `gm.check(plant, case)` lists both as `missing` with their
    paths (`params.control.outages`, `params.d0.riser.esp_depth`), and the run's `invalid_design`
    carries its path. geomind names them itself until then (`rule_issues`, and `run_issues`, a
    one-step run, in `geomind/tools/gemini/plants.py`).
34. (E2E-10, open, not sent: for Sahand) An `invalid_unit` problem of a case or
    economics leaf should carry the issue's `quantity` names and `accepted` units in `problem()` and
    `ValidationError.problems` (gemini's `units/inputs.py` `_unit_issue` builds both, then drops them),
    so geomind need not read "a unit of money per volume or money per energy" from the message text
    (`explain.quantities` splits it on " or " meanwhile).
35. (E2E-15, closed by gemini 0.6.11, 2026-11-05: the message names the negative curve windows) The ESP's `out_of_range` row names one flow ("flow =
    0.0097 m3/s gives head = -4.2e10 Pa"), not where the curve is valid: asked, the message or
    the problem names the flow range from zero to `maximum_flow` where the head or power curve is
    below zero. geomind computes it from `ESP.head_function`/`power_function` meanwhile
    (`runs.curve_ranges` in `geomind/tools/gemini/runs.py`).
36. (QA-040, open, not sent: for Sahand) `gm.check(plant, case)` does not name `params.backup`
    (the plant option `none` or `peak`, no default) when a plant lacks it, but sizing and a study
    stop on it at once: `study_failed: params.backup is missing; expected one of ('none',
    'peak') (it has no default)`. Asked: `gm.check` lists `params.backup` as `missing` with its
    path and options, as for any value a run needs. The backend lists it itself meanwhile
    (backend 1.1.39, `GET /plant/parameters/plant`).
37. (QA-039, open, not sent: for Sahand) A daily (or coarser) demand series with dates and no
    offset, read in a zone with daylight saving time (`time_zone: Europe/Amsterdam`), is refused:
    gemini checks the constant step on UTC instants, so the day of the clock change (23 or 25
    hours) breaks it. Asked: for a step of one day or more, check the step on the local calendar
    dates, so each row is one calendar day in the user's zone. geomind's case lead reads such
    dates as UTC meanwhile and says so in its question.
38. (QA-043, open, not sent: for Sahand) A dimensionless case leaf (`site.air.relative_humidity`,
    a fraction) refuses a value or a series in `%` (`invalid_unit`: "this value has no dimension,
    expected no unit"), and `gm.units` knows no `%`, while a weather server (open-meteo's
    `relative_humidity_2m_mean`) gives humidity in %. Asked: a fraction leaf accepts `%` and
    gemini converts it (80 % is 0.8), as it does for `mol%`. geomind's case lead leaves such a
    series out and asks the user meanwhile.

gemini 0.6.2 (2026-11-04) answers 13 (`Case.from_dict` lists every issue), 14 (`type: array`
and the list form), 15 (`mol%`), 16 (bases per unit: ice and thermal storage per MWh, heat
exchanger per W of duty, production pump per unit, `opex.fixed` per MW and year, subsidy per MWh;
`capex.pipe` per MW and m is still refused), 18 (`opex.variable.chemical` prices every inhibitor,
`opex.per_energy.chp`) and the economics descriptions; 17 by the descriptions only (its
`sources.csv` is unchanged; geomind's copy now names the keys, `data/knowledge/data-economics.md`).
The other requests of this list stay open.

Status after gemini 0.6.3 (2026-11-04, geomind 0.4.23). Sahand's rule (docs/rules.md): a
request is only a real bug, a unit problem or an unclear error; gemini provides no data, defaults
or derived inputs for other packages, so a request of that kind is dropped.

| # | Status |
|---|---|
| 1-10 | open (none is in 0.6.3's changelog) |
| 11 | closed, 0.6.3: a doublet names a missing design value alone; the design prompts no longer have the engineers copy case values |
| 12 | closed, 0.6.3: `time.end`'s description says it is excluded; the case lead's text points to it |
| 13, 14, 15, 18, 19/21 | closed, 0.6.2 |
| 16 | closed for `capex.pipe` per MW and m, 0.6.3 (the other bases 0.6.2); open: `opex.fixed.pipe` per MW and year (two catalogue rows) |
| 17 | closed, 0.6.3: gemini's catalogue paths are case keys; geomind's copy follows |
| 22 | closed, 0.6.3: every case key is described; `fields.py` keeps only sources and notes |
| 26 | closed, 0.6.3: `gm.study.metrics()` |
| 27 | closed, 0.6.3: `invalid_call` at `parameters.<name>` |
| 28 | dropped (class default values are data); its doublet part is answered by 11 |
| 29 | closed, 0.6.3: `kW/K`, `MW/K` |
| 30 | closed, 0.6.3: `Plant.to_dict(units="display")`, used by `read_plant` |
| 31 | closed, 0.6.3: `°C/km`, `degC/km`; geomind's gradient mapping is gone |
| 32 | dropped (a derived input): geomind sets the ISA pressure from the site's elevation itself (`air.py`) |
| 33, 36 | closed, gemini 0.6.5 (2026-11-05): `gm.check` names `params.control.dispatch`, `params.control.outages`, `params.backup` and a split well's `esp_depth`; the run's `invalid_design` path is still None |
| 34 | closed, 0.6.5: a unit problem carries `quantity` and `accepted` |
| 35 | open: the ESP's `out_of_range` still names one flow; geomind's `runs.curve_ranges` stays |
| 37 | closed, 0.6.5: a local daily series is matched by calendar date (QA-039) |
| 38 | closed, 0.6.5: a relative humidity takes `-` or `%` (QA-043) |

gemini 0.6.4 (2026-11-04) is a bug fix only: H2S in a gas composition (B3, row 147). None of
the requests above changes status.

A candidate for Sahand, not sent: gemini 0.6.3 describes each entry of a map as "The entry of
this map for <key>." (`opex.fixed.boiler`, `site.fluid.dissolved_gas.CO2`), which says nothing;
geomind skips that text so the map's own description shows.

Items 1 to 22 were merged into Sahand's list to gemini on 2026-11-04 00:30 (the coordinator's
16-21 overlap these numbers); new requests are numbered from 26 on.

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
