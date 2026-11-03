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
harness the engine, tools, permissions, hooks, sandbox and log, and a loop decides which run comes
next and when the goal is met. geomind copies gemini's structure on purpose, so one mental model
covers both: see [the gemini parallels](../../AGENTS.md#the-gemini-parallels).

| # | Decision | Why | Detail |
|---|---|---|---|
| 1 | The event log is the only source of truth, with no checkpoints; resume, crash recovery and replay are one mechanism | Three mechanisms would drift apart; any process can continue a run | [engine.md](engine.md#recovery-and-resume) |
| 2 | The core is async and the facade is sync | Parallel tool calls and delegates need it, and changing it later would touch every layer | [conventions.md](conventions.md#departures-from-gemini) |
| 3 | LLM calls and tool calls are the only side effects | Everything else is deterministic over the log, so a durable executor could wrap them later | [engine.md](engine.md#harness-principles) |
| 4 | Context is explicit: a tool whose first parameter is `context` gets the run; `runtime.py` holds settings only | No hidden active-run variable | [tools.md](tools.md#dispatch) |
| 5 | Hooks and permissions are separate; every tool declares an effect; every decision is a `permission` event | Hooks are code, rules are data, and both must be auditable | [hooks.md](hooks.md), [permissions.md](permissions.md) |
| 6 | Model-written code runs only in a sandbox, never in the harness process | Credentials and the harness stay out of its reach | [sandbox.md](sandbox.md) |
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
| S2 | `read_result`, `search_documents` | `aa4b01e` | done |
| S2 | `Analyst` (complete sample, the default agent without a sandbox), `Summarizer`; skeletons of `Coordinator`, `Designer`, `Verifier`, `Economist`, `Explainer`, each with a six-heading prompt file | `ad01b96` | done |
| S2 | `geomind chat` and the eval runner | `55296c1` | done |
| S2b | `FileWorkspace.plant` through `gm.plants.from_dict` | `957c119` | done |
| Freeze | Every interface below, pinned by snapshots; the tool catalogue and the loops as stubs; see [CHANGELOG.md](../../docs/CHANGELOG.md) | `fab5524`, `09096d8` | done |
| S2b.1 | `list_modules`, `describe_module`, `evaluate_module` over `gm.modules` and `gm.evaluate` | `599a660` | done |
| S2b.2 | `list_plants`, `read_plant`, `build_plant` over `gm.plants`; a plant file builds with `Plant.from_dict` and is stored with its issues | `2d3efa1` | done |
| S2b.3 | `list_profiles`, `read_profile`, `simulate` (`gm.schedule` and `gm.simulate`, failed days recorded) | `f4732aa` | done |
| S2b.4 | the `Analyst` with the gemini tools, its prompt, and the `gemini-units` skill checked against `gm.units.names()` | `05dd940` | done |
| S2b.5 | five analyst eval tasks on the example doublet, passing offline; recordings written by hand until S2b.6 | `40a8d72` | done |
| S2b.6 | one live run, recorded, with its token cost | none | **open**: needs `OPENROUTER_API_KEY` and a cap; `geomind check-live` checks the models first |
| S3.1 | `gd.verify.verify`, `check_results`, `compute_kpis`: gemini's report on the run's case, with failure domains | `7afb1d0` | done |
| S3.2 | the `Verified` hook: gemini's checks run again on the design's stored run before any answer | `8ee1444` | done |
| S3.3 | `estimate_costs`: gemini's economics with the assumptions used, and LCTS | `cf07cdc` | done |
| S3.4 | `Designer`, `Verifier`, `Economist`, `Explainer`, `Coordinator` filled, with the `designing-a-plant` skill and one offline task each (hand-written recordings); `read_plant` reads examples and templates (`253bf05`); co-produced gas check (`e7719f4`) | `ef7c64b` | done |
| S3.5 | `DesignLoop`: a rule-based driver delegates design, verification, costs and explanation in one root run, routes failures by domain, and replays offline (nested state changes and artifacts reused) | `4fc16ed` | done |
| S3.7 | Routing: `Run.start` asks the `Coordinator` (a nested run logged first) and follows its `Route`; `geomind run --loop/--project/--recording/--record` | `27f3161` | done |
| S3 e2e | the official case through `geomind run --loop design`, offline from a scripted recording, replays | `b1c9cd3` | done; the live run waits for `OPENROUTER_API_KEY` |
| S4.5 | `geomind show --format md`: tokens by agent, by step and in total, each prompt once, full answers | `1ac2af1` | done |
| Manifest | `run_manifest.json` beside each `geomind run`: commits, versions, input hashes, models per agent, settings, seeds | `0af2695` | done |
| Replay | parallel calls matched by their place in the step; nested state changes by the call that started them | `55632cc` | done |
| Usage | `RunResult.usage` counts every nested run, the routing call included, after a resume too | `4971938` | done |
| Case | the problem as data: a `gm.Case` in the problem state (`set_case`, `read_case`), its files stored as `case/<file name>`; `save_profile` adds a user's demand to the case; the design loop asks the user when there is no case or no demand | `7e74274`, `164eb62`, adaptation | done |
| Skill | `designing-a-plant` general for any case, with no challenge number in the package; Designer and Explainer prompts without the hand-found answer | `fb93b32` | done |
| Evals | `challenge2`: the hackathon case and three variants through the design loop, offline; the `verified` criterion | `6cf623c` | done |
| Caching | OpenRouter prompt caching on the system prompt of Anthropic models; `Usage.cached_tokens` | `7286e6d` | done |
| Spending cap | `geomind run --max-tokens/--max-cost`; budgets count the whole run, nested runs included | `65c576a` | done |
| Terminal | `geomind run` no longer prints the coordinator's route JSON; plan corrections from the audit | this commit | done |
| gemini 0.5 | geomind 0.3.0 on gemini `>=0.5,<0.6`: project folder case with `economics.json`, verdict, ranges and `run_study`, `Workspace.plants`, chat-scoped artifacts, `write_module`/`test_module` in the gemini sandbox, `CompareLoop`, the competition export, `check-live`, the loop report ([CHANGELOG.md](../../docs/CHANGELOG.md)) | merged sections A to P | done |
| Log and replay | geomind 0.3.1: `run.started` records the geomind, gemini and python versions and the export reads them; the export header shows the run's own request; a replay runs every nested run again with its own completions and compares every run | merged sections V and R | done |
| Studies, budget, replays | geomind 0.4.0: every study tool stores `study/<name>` (gemini's study and result form) and emits `study.recorded`; `list_studies`, `read_study`; `ProjectBudget` with `UsageLedger`; replay matches results by step and call id, and a log of another geomind version checks decisions, not tool outputs; every eval recording replays in a test | merged sections P, S and B | done |
| Released on the wheel | geomind 0.4.2 on the gemini 0.5.5 release wheel: shorter context, Designer asks for a missing range, no model id in the package, tests read a copy of gemini's examples; `README.md` and `docs/` for people | `v0.4.2` | done |
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
- **Plant runs with an agent-written module.** `test_module` checks a module in the sandbox, but
  `build_plant` and `simulate` cannot load it: a plant run with it needs `simulate` in the sandbox.
  The Designer records such a family as blocked.
- **Replay of a run with a project, without `--project`** reuses its nested runs (their answer
  and state changes), as the log holds no workspace; with the folder every nested run runs again.
- **Versions of a 0.3.0 log are not in the event log**; the export reads them from
  `run_manifest.json` (runs from 0.3.1 record them on `run.started`).
- The Docker tests of the module sandbox need the `gemini-sandbox:<gemini version>` image
  (`make sandbox-image` pulls it); they passed on 2026-11-03 with `gemini-sandbox:0.5.10`.
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
4. **The Analyst.** Done. Added the tools to `geomind/agents/analysis/analyst.py` and its prompt, and update
   the `gemini-units` skill to the units gemini accepts.
   - Tests: `tests/unit/agents/analysis/test_analyst.py`.
   - Done when: `test_its_prompt_names_only_tools_it_has` passes with the new tools.
5. **First eval tasks.** Done; the recordings are hand-written until S2b.6. On the example doublet, in `evals/tasks/analyst/`: the operating point, heat
   delivered at 150 m³/h, a missing parameter that needs `ask_user`, a module lookup, and the ESP at
   another frequency.
   - Done when: `python -m evals.run --agent analyst` passes offline from recordings.
6. **One live run.** `geomind chat --agent analyst --live`, recorded, with the token cost reported.

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
     reaches the user without passing every verifier**.
3. **Costs.** Done; see [tools.md](tools.md#costs). Replaced the stub `estimate_costs` in `geomind/tools/gemini/assessment.py`.
   - Done when: capex, opex, LCOH, LCOC, LCTS, NPV, payback and CO₂ come back as Values from the case's assumptions.
4. **Fill the skeleton agents.** Done. of [agents.md](agents.md#shipped-agents): prompts, tools and eval
   tasks. `Designer` proposes configurations and sizes, `Verifier` runs the checks and reviews,
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
6. **`MakerCheckerLoop`.** Removed: the design loop already has a maker (Designer) and a checker
   (Verifier), and `CompareLoop` is built on it.
7. **Routing.** Done. `Run.astart` calls the `Coordinator` and follows its `Route` with `loop_of` in
   `geomind/run.py`. A stub loop already gives `stop_reason="not_implemented"`.
   - Tests: `tests/unit/test_run.py`.
   - Done when: the backend starts a design run without naming a loop or an agent.
8. **Agent-written modules (Challenge 1).** Done. `write_module` stores the module and
   `test_module` runs `gm.modules.check` in the gemini sandbox
   ([sandbox.md](sandbox.md#dockersandbox)); the `writing-a-gemini-module` skill teaches the flow.
   Open: a plant run with the module (see the open items above).

### S4: compare, uncertainty, evals and export

1. **`CompareLoop`.** Done, and rebuilt in 0.4.6: see [engine.md](engine.md). `Route.loop` can be
   `compare`.
2. **Optimisation (bonus).** Done: `optimize` and `run_study` over `gm.Study` in
   `geomind/tools/gemini/study.py`.
3. **Uncertainty (bonus).** Done: `sample_uncertainty`, `sensitivity` and `compare` in `study.py`,
   with the distributions of the case's `uncertainty`.
4. **Evals.** Done: `evals/tasks/` holds the `challenge2`, `compare`, analyst, designer, verifier and
   economist tasks, passing offline, and `python -m evals.run --report` writes
   `evals/reports/summary.md` ([evals.md](evals.md#suites)).
5. **Export.** Done. `geomind show <run> --format md` writes the competition export: every LLM call
   with its messages, each agent's prompt once, and the token tables.

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
- **Credentials** never go into prompts, events, logs, the sandbox or memory.
- **Testing an agent:** by hand with `geomind chat` ([api.md](api.md#command-line)), by tasks with
  `python -m evals.run` ([evals.md](evals.md)).
- **Adding or filling an agent:** follow [agents.md](agents.md#how-to-add-or-fill-an-agent). The
  `Analyst` is the worked example.

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
